"""Evidence-tool regression tests on private, disposable SQLite connections."""
from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import Mock

from django.conf import settings
from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper

from .review_migration_check import require_empty_qa_postgres
from .schema_manifest import build_manifest


class SchemaManifestTests(TestCase):
    def setUp(self):
        configuration = {**settings.DATABASES["default"], "ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:", "OPTIONS": {}, "TIME_ZONE": None}
        self.db = DatabaseWrapper(configuration, alias="manifest_private")
        connections[self.db.alias] = self.db

    def tearDown(self):
        if self.db.connection is not None:
            self.db.connection.close()
        del connections[self.db.alias]

    def execute(self, query, values=None):
        with self.db.cursor() as cursor:
            cursor.execute(query, values)

    def fixture(self):
        self.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY, nickname TEXT NOT NULL)')
        self.execute('CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id), secret TEXT)')
        self.execute('INSERT INTO parent VALUES (1, %s)', ['私人业务昵称'])
        self.execute('INSERT INTO child VALUES (1, 1, %s)', ['private-session-key'])

    def test_empty_database_and_additive_schema_are_supported_without_disclosing_values(self):
        empty = build_manifest(self.db)
        self.assertEqual(empty["result"], "PASS")
        self.assertEqual(empty["tables"], {})
        self.fixture()
        baseline = build_manifest(self.db)
        self.assertNotIn('私人业务昵称', json.dumps(baseline, ensure_ascii=False))
        self.assertNotIn('private-session-key', json.dumps(baseline))
        self.assertEqual(build_manifest(self.db, empty)["result"], "PASS")
        self.execute('ALTER TABLE parent ADD COLUMN audit_reason TEXT NOT NULL DEFAULT \'\'')
        self.execute('UPDATE parent SET audit_reason = %s', ['new audit detail'])
        compared = build_manifest(self.db, baseline)
        self.assertEqual(compared["result"], "PASS")
        self.assertEqual(compared["additions"]["columns"], {"parent": ["audit_reason"]})
        self.execute('UPDATE parent SET nickname = %s', ['changed original'])
        self.assertEqual(build_manifest(self.db, baseline)["result"], "FAIL")

    def test_missing_original_table_column_and_new_rows_fail_closed(self):
        self.fixture()
        baseline = build_manifest(self.db)
        self.execute('INSERT INTO parent VALUES (2, %s)', ['another original row'])
        self.assertEqual(build_manifest(self.db, baseline)["result"], "FAIL")
        self.execute('DELETE FROM parent WHERE id = 2')
        malformed = deepcopy(baseline)
        malformed["tables"]["parent"]["columns"].append('missing_column')
        self.assertEqual(build_manifest(self.db, malformed)["result"], "FAIL")
        self.execute('DROP TABLE child')
        self.assertEqual(build_manifest(self.db, baseline)["result"], "FAIL")

    def test_foreign_key_orphans_are_rejected(self):
        self.fixture()
        self.execute('PRAGMA foreign_keys = OFF')
        self.execute('UPDATE child SET parent_id = 999')
        manifest = build_manifest(self.db)
        self.assertEqual(manifest["result"], "FAIL")
        self.assertTrue(any(manifest["tables"]["child"]["foreign_key_orphans"].values()))

    def test_migration_additions_allowed_but_original_migration_rewrites_rejected(self):
        self.execute('CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT, applied TEXT)')
        self.execute("INSERT INTO django_migrations VALUES (1, 'tournaments', '0004', '2026-01-01')")
        baseline = build_manifest(self.db)
        self.execute("INSERT INTO django_migrations VALUES (2, 'tournaments', '0005', '2026-01-02')")
        self.assertEqual(build_manifest(self.db, baseline)["result"], "PASS")
        self.execute("UPDATE django_migrations SET applied = 'changed' WHERE id = 1")
        self.assertEqual(build_manifest(self.db, baseline)["result"], "FAIL")

    def test_wrong_manifest_version_or_vendor_is_rejected(self):
        for reference in [{"format_version": 0, "vendor": "sqlite", "tables": {}}, {"format_version": 1, "vendor": "postgresql", "tables": {}}]:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                build_manifest(self.db, reference)

    def test_original_types_and_foreign_keys_cannot_be_removed_with_unchanged_data(self):
        self.fixture()
        baseline = build_manifest(self.db)
        self.execute('DROP TABLE child')
        self.execute('CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER, secret TEXT)')
        self.execute('INSERT INTO child VALUES (1, 1, %s)', ['private-session-key'])
        self.assertEqual(build_manifest(self.db, baseline)["result"], "FAIL")
        self.execute('CREATE TABLE typed (id INTEGER PRIMARY KEY, value TEXT)')
        self.execute('INSERT INTO typed VALUES (1, %s)', ['same value'])
        typed = build_manifest(self.db)
        self.execute('DROP TABLE typed')
        self.execute('CREATE TABLE typed (id INTEGER PRIMARY KEY, value BLOB)')
        self.execute('INSERT INTO typed VALUES (1, %s)', ['same value'])
        self.assertEqual(build_manifest(self.db, typed)["result"], "FAIL")


class MigrationGuardTests(TestCase):
    def test_non_postgresql_and_non_qa_database_rejected_before_schema_access(self):
        for vendor, name in [("sqlite", "riichi_qa_legacy"), ("postgresql", "riichi"), ("postgresql", "riichi_qa")]:
            connection = Mock(vendor=vendor, settings_dict={"NAME": name})
            with self.subTest(vendor=vendor, name=name), self.assertRaises(RuntimeError):
                require_empty_qa_postgres(connection)
            connection.introspection.table_names.assert_not_called()

    def test_existing_qa_schema_is_never_reset(self):
        connection = Mock(vendor="postgresql", settings_dict={"NAME": "riichi_qa_legacy"})
        connection.introspection.table_names.return_value = ["accounts_user"]
        with self.assertRaises(RuntimeError):
            require_empty_qa_postgres(connection)
        connection.introspection.table_names.return_value = []
        require_empty_qa_postgres(connection)
