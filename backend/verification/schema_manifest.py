"""Read-only database evidence, including databases older than the current models.

``python -m verification.schema_manifest`` writes a JSON baseline to stdout.
``python -m verification.schema_manifest --compare baseline.json`` verifies all
original table columns and rows; added columns/tables and applied migrations are
reported separately. Run with writes stopped. No record values, credentials,
password hashes or session keys are written to the manifest.
"""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID


FORMAT_VERSION = 1
# Django's post_migrate adds rows here when a migration introduces a model;
# these tables are compared by original-row inclusion rather than exact hash.
ADDITIVE_TABLES = {"auth_permission", "django_content_type"}


def canonical_value(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return {"float": value.hex()}
    if isinstance(value, (datetime, date, time)):
        return {type(value).__name__: value.isoformat()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, UUID):
        return {"uuid": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": bytes(value).hex()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical_value(item) for key, item in value.items()}
    raise ValueError("Unsupported database value type in manifest")


def canonical_json(value):
    return json.dumps(canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_digest(row):
    return hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()


def migration_state(connection, tables):
    if "django_migrations" not in tables:
        return []
    # Migration names are schema metadata. Hash all original columns as well, so
    # an existing migration row cannot be silently rewritten during comparison.
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, app, name, applied FROM django_migrations ORDER BY app, name, id")
        rows = cursor.fetchall()
    result = [{"app": row[1], "name": row[2], "sha256": row_digest(row)} for row in rows]
    if len({(row["app"], row["name"]) for row in result}) != len(result):
        raise ValueError("Duplicate applied migration records")
    return result


def table_manifest(connection, table, columns, constraints, include_rows=False):
    quote = connection.ops.quote_name
    primary = [column for constraint in constraints.values() if constraint.get("primary_key") for column in constraint["columns"]]
    with connection.cursor() as cursor:
        query = f"SELECT {', '.join(map(quote, columns))} FROM {quote(table)}"
        if primary:
            query += " ORDER BY " + ", ".join(map(quote, primary))
        cursor.execute(query)
        digest = hashlib.sha256()
        row_hashes = []
        count = 0
        if primary:
            while rows := cursor.fetchmany(1000):
                for row in rows:
                    digest.update(canonical_json(row).encode("utf-8") + b"\n")
                    if include_rows:
                        row_hashes.append(row_digest(row))
                    count += 1
        else:
            # Django tables have a PK. Sorting hashes also makes the rare
            # externally managed table deterministic without exposing its rows.
            row_hashes = sorted(row_digest(row) for row in cursor.fetchall())
            for value in row_hashes:
                digest.update(value.encode("ascii") + b"\n")
            count = len(row_hashes)
    orphans = {}
    for name, constraint in sorted(constraints.items()):
        target = constraint.get("foreign_key")
        if not target:
            continue
        source_columns = constraint["columns"]
        if len(source_columns) != 1:
            raise ValueError("Composite foreign keys need an explicit manifest implementation")
        target_table, target_column = target
        source_column = source_columns[0]
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {quote(table)} AS source "
                f"WHERE source.{quote(source_column)} IS NOT NULL AND NOT EXISTS "
                f"(SELECT 1 FROM {quote(target_table)} AS target "
                f"WHERE target.{quote(target_column)} = source.{quote(source_column)})"
            )
            orphans[name] = cursor.fetchone()[0]
    # SQLite renumbers anonymous FK names when AddField rebuilds a table.
    # Compare relationships rather than backend-generated constraint names.
    foreign_keys = sorted([{"columns": constraint["columns"], "target": list(constraint["foreign_key"])} for constraint in constraints.values() if constraint.get("foreign_key")], key=canonical_json)
    result = {"columns": columns, "primary_columns": primary, "count": count, "sha256": digest.hexdigest(), "foreign_keys": foreign_keys, "foreign_key_orphans": orphans}
    # auth_permission/content type rows may be legitimately added by
    # post_migrate when a migration introduces a model. Keep per-row hashes so
    # a reference can require its original rows without rejecting additions.
    if include_rows:
        result["row_hashes"] = sorted(row_hashes)
    return result


def build_manifest(connection, reference=None):
    if reference is not None:
        if reference.get("format_version") != FORMAT_VERSION or reference.get("vendor") != connection.vendor or not isinstance(reference.get("tables"), dict):
            raise ValueError("Unsupported reference manifest format or database vendor")
    with connection.cursor() as cursor:
        tables = sorted(connection.introspection.table_names(cursor))
    result = {"format_version": FORMAT_VERSION, "vendor": connection.vendor, "tables": {}, "migration_state": migration_state(connection, tables)}
    differences = []
    additions = {"tables": [], "columns": {}}
    expected_tables = reference["tables"] if reference is not None else {}
    for missing in sorted(set(expected_tables) - set(tables)):
        differences.append(f"Missing original table: {missing}")
    for table in tables:
        if table == "django_migrations":
            continue
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table)
            actual_columns = [column.name for column in description]
            column_types = {column.name: {"type": str(column.type_code), "null_ok": bool(column.null_ok)} for column in description}
            constraints = connection.introspection.get_constraints(cursor, table)
        expected = expected_tables.get(table)
        columns = expected.get("columns") if expected is not None else actual_columns
        if not isinstance(columns, list) or not columns or any(not isinstance(column, str) for column in columns):
            raise ValueError("Invalid reference column list")
        missing = set(columns) - set(actual_columns)
        if missing:
            differences.append(f"Missing original columns: {table}")
            continue
        current = table_manifest(connection, table, columns, constraints, include_rows=table in ADDITIVE_TABLES)
        current["column_types"] = {column: column_types[column] for column in columns}
        result["tables"][table] = current
        if any(current["foreign_key_orphans"].values()):
            differences.append(f"Foreign key integrity failed: {table}")
        if expected is not None:
            if current["column_types"] != expected["column_types"] or current["primary_columns"] != expected["primary_columns"]:
                differences.append(f"Original column types, nullability or primary key changed: {table}")
            if any(value not in current["foreign_keys"] for value in expected["foreign_keys"]):
                differences.append(f"Original foreign key changed: {table}")
            if table in ADDITIVE_TABLES and "row_hashes" in expected and "row_hashes" in current:
                # post_migrate may add permissions/content types for a new
                # model. Original rows must remain; additions are expected.
                if not set(expected["row_hashes"]).issubset(set(current["row_hashes"])):
                    differences.append(f"Original data changed: {table}")
            elif current["count"] != expected["count"] or current["sha256"] != expected["sha256"]:
                differences.append(f"Original data changed: {table}")
            added = sorted(set(actual_columns) - set(columns))
            if added:
                additions["columns"][table] = added
        elif reference is not None:
            additions["tables"].append(table)
    if reference is not None:
        applied = {(row["app"], row["name"]): row["sha256"] for row in result["migration_state"]}
        for row in reference.get("migration_state", []):
            if applied.get((row["app"], row["name"])) != row["sha256"]:
                differences.append("Original migration record missing or changed")
    result["result"] = "FAIL" if differences else "PASS"
    if reference is not None:
        result["additions"] = additions
    if differences:
        result["differences"] = sorted(set(differences))
    return result


@contextmanager
def readonly_transaction(connection):
    from django.db import transaction

    with transaction.atomic(using=connection.alias):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", type=Path, help="Original JSON manifest; its original columns must remain unchanged")
    arguments = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    import django
    django.setup()
    from django.db import connection

    try:
        reference = json.loads(arguments.compare.read_text(encoding="utf-8-sig")) if arguments.compare else None
        with readonly_transaction(connection):
            result = build_manifest(connection, reference)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["result"] == "PASS" else 1
    except Exception:
        # Connection errors may contain credentials or backend details. Operators
        # inspect private database logs rather than publishing an exception here.
        print("Schema manifest FAILED; check the reference, database connectivity and private service logs.", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
