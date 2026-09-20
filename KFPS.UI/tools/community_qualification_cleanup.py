"""Audited cleanup of explicitly recorded synthetic production QA IDs only."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

REPO, RUN = (Path(value).resolve() for value in sys.argv[1:3])
MODE = sys.argv[3]
sys.path[:0] = [str(REPO / 'KFPS.UI/src'), str(REPO)]
from kfps_ui.community_credentials import CommunityCredentialStore
from kfps_ui.community_client import CommunityApiClient, CommunityApiError
from kfps_ui.community_service import configured_community_api_url

ledger = json.loads((RUN / 'created.json').read_text())
ids = [str(uuid.UUID(row['id'])) for row in ledger]
assert ids and len(ids) == len(set(ids)) and all(row['title'].startswith('KFPS SYNTHETIC QA ') for row in ledger)
sql_ids = ','.join("'" + ident + "'" for ident in ids)
worker = REPO / 'tools/community_worker'


def query(sql):
    result = subprocess.run(['npx.cmd', 'wrangler', 'd1', 'execute', 'kfps-community', '--remote',
        '--config', 'wrangler.jsonc', '--command', sql, '--json'], cwd=worker, capture_output=True, text=True, encoding='utf-8')
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)[0]['results']


rows = query(f'SELECT a.id,a.title,a.status,a.ends_at,a.purged_at,u.username FROM artworks a JOIN users u ON u.id=a.creator_id WHERE a.id IN ({sql_ids})')
assert len(rows) == len(ids)
endpoint = configured_community_api_url(REPO)
token = CommunityCredentialStore(REPO / 'runtime', endpoint).load_token()
client = CommunityApiClient(endpoint, token)
username = client.json('session', authenticated=True)['user']['username']
assert all(row['username'] == username and row['title'].startswith('KFPS SYNTHETIC QA ') for row in rows)

if MODE == 'inventory':
    keys = query(f'SELECT artwork_id,design_key,preview_key,thumbnail_key FROM artwork_revisions WHERE artwork_id IN ({sql_ids})')
    photos = query(f'SELECT artwork_id,object_key FROM artwork_photos WHERE artwork_id IN ({sql_ids})')
    inventory = sorted({value for row in keys+photos for key,value in row.items() if key.endswith('_key') and value})
    assert all(any(key.startswith(f'artworks/{ident}/') for ident in ids) for key in inventory)
    (RUN / 'cleanup-inventory.json').write_text(json.dumps({'rows': rows, 'keys': inventory}, indent=2), encoding='utf-8')
    print(json.dumps({'recorded_ids': len(ids), 'private_objects': len(inventory)}))
elif MODE == 'remove':
    for row in rows:
        if row['status'] != 'removed':
            try: client.json('artworks/' + row['id'], 'DELETE', authenticated=True)
            except CommunityApiError as error:
                assert error.status == 404 and row['ends_at'], error
    # Normal owner removal preserves revisions. Expire only these verified QA
    # tombstones so the actual scheduled purge can remove their private objects.
    query(f"UPDATE artworks SET ends_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), starts_at = NULL WHERE id IN ({sql_ids}) AND status='removed' AND ends_at IS NULL")
    (RUN / 'cleanup-started.json').write_text(json.dumps({'ids': ids, 'awaiting_real_cron': True}), encoding='utf-8')
    print(json.dumps({'removed_test_posts': len(ids), 'waiting_for_cron': True}))
elif MODE == 'verify':
    assert all(row['status'] == 'removed' and row['purged_at'] for row in rows), rows
    inventory = json.loads((RUN / 'cleanup-inventory.json').read_text())
    checked = []
    for i, key in enumerate(inventory['keys']):
        result = subprocess.run(['npx.cmd', 'wrangler', 'r2', 'object', 'get',
            'kfps-community-assets/' + key, '--remote', '--config', 'wrangler.jsonc',
            '--file', str(RUN / f'unexpected-retained-{i}.bin')], cwd=worker, capture_output=True, text=True, encoding='utf-8')
        message = result.stdout + result.stderr
        assert result.returncode != 0 and ('does not exist' in message or 'not found' in message or '[code: 10007]' in message), message
        checked.append(key)
    for ident in ids:
        try: client.binary(f'artworks/{ident}/download', authenticated=True)
        except CommunityApiError as error: assert error.status == 404
        else: raise AssertionError('Retained download ' + ident)
    (RUN / 'cleanup-verified.json').write_text(json.dumps({'passed': True, 'rows': rows,
        'objects_confirmed_absent': checked, 'existing_session_accepted': True}, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'purged_posts': len(rows), 'absent_objects': len(checked)}))
else:
    raise ValueError('Use inventory, remove or verify')
