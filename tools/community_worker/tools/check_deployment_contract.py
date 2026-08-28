from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CONFIG = WORKER_ROOT / "wrangler.jsonc"
LOCAL_CONFIG = WORKER_ROOT / "wrangler.e2e.jsonc"
PLACEHOLDER = "REPLACE_WITH_"


def load_config(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read Worker configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Worker configuration must be a JSON object: {path}")
    return value


def identity(config: dict) -> tuple[str, str, str, str]:
    databases = list(config.get("d1_databases") or [])
    buckets = list(config.get("r2_buckets") or [])
    if len(databases) != 1 or len(buckets) != 1:
        raise RuntimeError("Each Community Worker configuration must bind exactly one D1 database and one R2 bucket.")
    database = dict(databases[0])
    bucket = dict(buckets[0])
    return (
        str(config.get("name") or ""),
        str(database.get("database_id") or ""),
        str(database.get("database_name") or ""),
        str(bucket.get("bucket_name") or ""),
    )


def require_vars(config: dict, expected: dict[str, str], label: str) -> None:
    variables = dict(config.get("vars") or {})
    for name, value in expected.items():
        if str(variables.get(name) or "") != value:
            raise RuntimeError(f"{label} must set {name}={value!r}.")


def check_migrations() -> list[str]:
    migrations = sorted((WORKER_ROOT / "migrations").glob("*.sql"))
    numbers = []
    for path in migrations:
        match = re.fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", path.name)
        if not match:
            raise RuntimeError(f"Migration name is not versioned correctly: {path.name}")
        numbers.append(int(match.group(1)))
        sql = path.read_text(encoding="utf-8")
        if re.search(r"\bDROP\s+(TABLE|COLUMN|INDEX)\b", sql, re.IGNORECASE):
            raise RuntimeError(f"Destructive migration requires an explicit compatibility review: {path.name}")
    if numbers != list(range(1, len(numbers) + 1)):
        raise RuntimeError(f"Community migrations are not contiguous: {numbers}")
    return [path.name for path in migrations]


def check_contract(staging_config: Path | None = None) -> dict:
    production = load_config(PRODUCTION_CONFIG)
    local = load_config(LOCAL_CONFIG)
    production_identity = identity(production)
    local_identity = identity(local)

    require_vars(production, {
        "API_PROTOCOL": "1",
        "DEPLOYMENT_ENVIRONMENT": "production",
        "ALLOW_TEST_AUTH": "0",
        "REQUIRE_MODERN_UPLOAD_CLIENT": "0",
        "COMPATIBILITY_MINIMUM_UPLOAD_VERSION": "3.0.81",
    }, "Production configuration")
    require_vars(local, {
        "API_PROTOCOL": "1",
        "DEPLOYMENT_ENVIRONMENT": "local-e2e",
        "ALLOW_TEST_AUTH": "1",
        "REQUIRE_MODERN_UPLOAD_CLIENT": "0",
        "COMPATIBILITY_MINIMUM_UPLOAD_VERSION": "3.0.81",
        "VERSION_SYNC_ENABLED": "0",
    }, "Local E2E configuration")
    if production_identity == local_identity or set(production_identity[1:]) & set(local_identity[1:]):
        raise RuntimeError("Local E2E bindings overlap production Community resources.")
    if "TEST_AUTH_TOKEN" in dict(production.get("vars") or {}):
        raise RuntimeError("Production configuration must not define the staging test-auth token.")
    if production.get("preview_urls") is not False or local.get("preview_urls") is not False:
        raise RuntimeError("Preview URLs must remain disabled.")

    result = {
        "production_worker": production_identity[0],
        "production_database": production_identity[2],
        "production_bucket": production_identity[3],
        "legacy_upload_bridge": True,
        "migrations": check_migrations(),
        "staging_checked": False,
    }
    if staging_config is not None:
        staging = load_config(staging_config.resolve())
        staging_identity = identity(staging)
        production_vars = dict(production.get("vars") or {})
        staging_vars = dict(staging.get("vars") or {})
        require_vars(staging, {
            "API_PROTOCOL": "1",
            "DEPLOYMENT_ENVIRONMENT": "staging",
            "ALLOW_TEST_AUTH": "1",
            "REQUIRE_MODERN_UPLOAD_CLIENT": "0",
            "COMPATIBILITY_MINIMUM_UPLOAD_VERSION": "3.0.81",
            "VERSION_SYNC_ENABLED": "0",
        }, "Staging configuration")
        if any(PLACEHOLDER in value for value in staging_identity):
            raise RuntimeError("Staging configuration still contains replacement placeholders.")
        if set(production_identity) & set(staging_identity):
            raise RuntimeError("Staging configuration reuses a production Worker, D1, or R2 identifier.")
        if staging.get("workers_dev") is not True or staging.get("preview_urls") is not False:
            raise RuntimeError("Staging must use workers.dev with preview URLs disabled.")
        if not staging_vars.get("GITHUB_CLIENT_ID") or staging_vars.get("GITHUB_CLIENT_ID") != production_vars.get("GITHUB_CLIENT_ID"):
            raise RuntimeError("Staging must use the production public GitHub OAuth application ID.")
        required_secrets = set(dict(staging.get("secrets") or {}).get("required") or [])
        if not {"ADMIN_TOKEN", "TEST_AUTH_TOKEN"}.issubset(required_secrets):
            raise RuntimeError("Staging must require separate admin and test-auth secrets.")
        result.update({
            "staging_checked": True,
            "staging_worker": staging_identity[0],
            "staging_database": staging_identity[2],
            "staging_bucket": staging_identity[3],
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Community Worker rollout and resource isolation.")
    parser.add_argument("--staging-config", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check_contract(args.staging_config)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("Community deployment contract passed.")
        print(f"Legacy upload bridge: {'enabled' if result['legacy_upload_bridge'] else 'disabled'}")
        print(f"Migrations checked: {len(result['migrations'])}")
        print(f"Staging isolation checked: {'yes' if result['staging_checked'] else 'not requested'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Community deployment contract FAILED: {error}")
        raise SystemExit(1)
