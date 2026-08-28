from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from check_deployment_contract import check_contract, identity, load_config


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
TEMPLATE = WORKER_ROOT / "wrangler.staging.example.jsonc"
PRODUCTION_CONFIG = WORKER_ROOT / "wrangler.jsonc"
SUPPORTER_ISSUER = WORKER_ROOT / "tools" / "test_supporter_token.mjs"


def write_private(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an isolated Community Worker staging configuration.")
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--database-name", default="kfps-community-staging")
    parser.add_argument("--bucket-name", default="kfps-community-assets-staging")
    parser.add_argument("--worker-name", default="kfps-community-library-staging")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        database_id = str(uuid.UUID(args.database_id))
    except ValueError as error:
        raise RuntimeError("--database-id must be the UUID returned by Cloudflare D1 creation.") from error
    requested = {args.worker_name.strip(), database_id, args.database_name.strip(), args.bucket_name.strip()}
    if not all(requested):
        raise RuntimeError("Staging resource names cannot be empty.")
    production = set(identity(load_config(PRODUCTION_CONFIG)))
    production_config = load_config(PRODUCTION_CONFIG)
    github_client_id = str(dict(production_config.get("vars") or {}).get("GITHUB_CLIENT_ID") or "").strip()
    version_repository = str(dict(production_config.get("vars") or {}).get("VERSION_REPOSITORY") or "").strip()
    if not github_client_id:
        raise RuntimeError("Production does not define the public GitHub OAuth application ID.")
    if not version_repository:
        raise RuntimeError("Production does not define the public VERSION repository.")
    if production & requested:
        raise RuntimeError("Refusing to reuse a production Community resource in staging.")
    if not all("staging" in value.lower() for value in (args.worker_name, args.database_name, args.bucket_name)):
        raise RuntimeError("Every staging resource name must contain the word 'staging'.")

    state_dir = WORKER_ROOT / ".staging"
    config_path = WORKER_ROOT / "wrangler.staging.jsonc"
    if (state_dir.exists() or config_path.exists()) and not args.force:
        raise RuntimeError("Staging state already exists. Review it or rerun with --force to replace it.")
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)

    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js 20 or newer is required to prepare staging keys.")
    key_path = state_dir / "supporter-test-key.json"
    subprocess.run([node, str(SUPPORTER_ISSUER), "generate", str(key_path)], check=True, cwd=WORKER_ROOT)
    key = json.loads(key_path.read_text(encoding="utf-8"))
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    replacements = {
        "REPLACE_WITH_STAGING_WORKER_NAME": args.worker_name,
        "REPLACE_WITH_KFPS_VERSION": version,
        "REPLACE_WITH_SUPPORTER_KEY_ID": str(key["key_id"]),
        "REPLACE_WITH_SUPPORTER_MODULUS_HEX": str(key["modulus_hex"]),
        "REPLACE_WITH_STAGING_D1_NAME": args.database_name,
        "REPLACE_WITH_STAGING_D1_DATABASE_ID": database_id,
        "REPLACE_WITH_STAGING_R2_BUCKET": args.bucket_name,
        "REPLACE_WITH_GITHUB_CLIENT_ID": github_client_id,
        "REPLACE_WITH_VERSION_REPOSITORY": version_repository,
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for old, new in replacements.items():
        text = text.replace(old, new)
    config_path.write_text(text, encoding="utf-8")

    admin_token = secrets.token_urlsafe(48)
    test_token = secrets.token_urlsafe(48)
    secrets_path = state_dir / "deploy.secrets"
    write_private(secrets_path, f"ADMIN_TOKEN={admin_token}\nTEST_AUTH_TOKEN={test_token}\n")
    test_env = state_dir / "test.env"
    write_private(test_env, f"KFPS_COMMUNITY_TEST_AUTH_TOKEN={test_token}\n")
    check_contract(config_path)

    print("Isolated Community staging configuration prepared.")
    print(f"Configuration: {config_path}")
    print(f"Private staging state: {state_dir}")
    print("No Cloudflare resource was changed.")
    print("Next commands:")
    print(f"  npx wrangler d1 migrations apply DB --remote --config {config_path}")
    print(f"  npx wrangler deploy --config {config_path} --secrets-file {secrets_path}")
    print("Then validate the deployed workers.dev URL with run_kfps_staging_e2e.py.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Staging preparation FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
