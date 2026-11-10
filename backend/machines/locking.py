"""Shared resource lock order for machine state and tournament allocations.

Caller must be inside atomic(). SQLite reserves its writer BEFORE any reads.
PostgreSQL locks the small physical pool by stable primary key, never by mutable
business number. Only the returned, locked rows may be allocated in this txn.
"""
from django.db import connection
from django.db.models import F
from .models import MahjongMachine


def lock_machine_pool():
    if connection.vendor == 'postgresql':
        # Row locks cannot serialize an empty pool. One database-local advisory
        # lock also protects first-machine numbering, and is released on rollback.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [0x52494348, 0x4D414348])
    if connection.vendor == "sqlite":
        # A no-op DML still obtains a SQLite write reservation, even for zero rows.
        # No timestamp/number/capacity value is changed by this reservation.
        MahjongMachine.objects.all().update(updated_at=F("updated_at"))
    return list(MahjongMachine.objects.select_for_update().order_by("pk"))
