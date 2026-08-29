from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_production_with_report as deployment


class ProductionDeploymentTransitionTests(unittest.TestCase):
    def test_remote_table_names_accepts_wrangler_batch_json(self):
        response = json.dumps([{
            "results": [{"name": "users"}, {"name": "ignored_users"}],
            "success": True,
        }])
        with mock.patch.object(deployment, "command_output", return_value=response):
            self.assertEqual(deployment.remote_table_names("npx"), {"users", "ignored_users"})

    def test_first_ignore_migration_backs_up_the_existing_schema(self):
        existing = set(deployment.AUTHORITATIVE_TABLES) - {"ignored_users"}
        backup_tables = deployment.pre_migration_backup_tables(existing)
        self.assertNotIn("ignored_users", backup_tables)
        self.assertEqual(set(backup_tables), existing)

    def test_unexpected_missing_table_stops_deployment(self):
        existing = set(deployment.AUTHORITATIVE_TABLES) - {"users", "ignored_users"}
        with self.assertRaisesRegex(RuntimeError, "users"):
            deployment.pre_migration_backup_tables(existing)


if __name__ == "__main__":
    unittest.main()
