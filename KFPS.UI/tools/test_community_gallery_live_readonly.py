"""Read-only deployment checks using this installation's existing session."""
import hashlib
import json
from pathlib import Path
import sys

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / 'src'), str(UI.parent)]
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient, CommunityApiError
from kfps_ui.community_credentials import CommunityCredentialStore
from kfps_ui.community_service import configured_community_api_url


def main():
    paths = AppPaths.discover()
    endpoint = configured_community_api_url(paths.app_root)
    public = CommunityApiClient(endpoint)
    assert public.json('health')['status'] == 'ok'
    config = public.json('config')
    assert config['gallery']['version'] == 1 and not config['test_auth']
    legacy = public.json('artworks?scope=featured&limit=24')
    assert all(row.get('kind', 'vinyl') == 'vinyl' for row in legacy['items'])
    catalog = public.json('artworks?view=gallery&scope=browse&limit=48')
    assert catalog['items']
    ordinary = next(row for row in catalog['items'] if not row['supporter_only'])
    try:
        public.binary(ordinary['download_url'], maximum=1)
    except CommunityApiError as error:
        assert error.status == 401
    else:
        raise AssertionError('Anonymous download was not blocked')
    token = CommunityCredentialStore(paths.runtime_root, endpoint).load_token()
    assert token, 'No existing session available for this read-only check'
    client = CommunityApiClient(endpoint, token)
    session = client.json('session', authenticated=True)
    assert session.get('user')
    raw, _ = client.binary(ordinary['thumbnail_url'], authenticated=True, maximum=512 * 1024)
    assert hashlib.sha256(raw).hexdigest() == ordinary['thumbnail_sha256']
    timed = client.json('artworks?view=gallery&scope=timed&limit=1', authenticated=True)
    result = dict(passed=True, health=True, gallery_version=1, test_auth=False,
                  legacy_featured_count=legacy['total'], gallery_count=catalog['total'],
                  anonymous_download_blocked=True, existing_session_accepted=True,
                  authenticated_thumbnail_integrity=True, timed_catalog_count=timed['total'])
    output = paths.runtime_root / 'community-preview/integration-20260920/live-after.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
