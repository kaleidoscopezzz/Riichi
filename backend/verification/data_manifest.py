"""Read-only counts, canonical field digests and FK integrity for migration/restore.

Run with an explicitly selected settings module and database. Outputs no records,
password hashes, session keys or connection strings. Compare at the SAME code and
migration version, with writes stopped. Hashes are evidence, not a data backup.
"""
import hashlib
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
import django
django.setup()
from django.apps import apps
from django.core import serializers
from django.db import connection


def main():
    result = {"models": {}, "foreign_key_orphans": {}}
    for model in sorted(apps.get_models(), key=lambda m: m._meta.label_lower):
        rows = model._default_manager.order_by("pk")
        records = json.loads(serializers.serialize("json", rows))
        canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result["models"][model._meta.label_lower] = {"count": len(records), "sha256": hashlib.sha256(canonical.encode()).hexdigest()}
        for field in model._meta.fields:
            if field.many_to_one or field.one_to_one:
                related = field.remote_field.model._default_manager.values_list("pk", flat=True)
                orphans = rows.exclude(**{f"{field.attname}__in": related}).exclude(**{f"{field.attname}__isnull": True}).count()
                result["foreign_key_orphans"][f"{model._meta.label_lower}.{field.name}"] = orphans
    with connection.cursor():
        connection.check_constraints()
    if any(result["foreign_key_orphans"].values()):
        raise RuntimeError("Foreign key integrity failed")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
