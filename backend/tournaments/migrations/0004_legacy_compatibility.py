"""Non-destructive defaults, first-order recovery and active occupancy bridges."""
from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Tournament = apps.get_model('tournaments', 'Tournament')
    Fixed = apps.get_model('tournaments', 'TournamentTable')
    Reservation = apps.get_model('tournaments', 'TournamentMachineReservation')
    alias = schema_editor.connection.alias
    winds = ['east', 'south', 'west', 'north']
    for t in Tournament.objects.using(alias).all().iterator():
        t.rules_source = 'legacy_default_backfill:0004'
        t.compatibility_audit = {'migration': '0004', 'identified_at': timezone.now().isoformat()}
        first = t.rounds.using(alias).order_by('round_number').first()
        if first:
            expected = set(t.participants.using(alias).values_list('id', flat=True))
            order = []
            valid = first.round_number == 1 and len(expected) in (4, 8, 12, 16)
            tables = list(first.tables.using(alias).order_by('table_number'))
            valid = valid and [x.table_number for x in tables] == list(range(1, len(expected)//4+1))
            for table in tables:
                fixed = Fixed.objects.using(alias).create(tournament_id=t.pk, ordinal=table.table_number)
                seats = list(table.seats.using(alias).all())
                by_wind = {s.seat_wind: s.participant_id for s in seats}
                if len(seats) == 4 and set(by_wind) == set(winds):
                    order.extend(by_wind[w] for w in winds)
                else:
                    valid = False
                current = table.allocations.using(alias).filter(status='active').select_related('machine').first()
                original = table.allocations.using(alias).order_by('id').first()
                table.tournament_table_id = fixed.pk
                table.machine_snapshot = {'machine_id': original.machine_id, 'machine_no': original.machine_no_snapshot, 'source': 'legacy_round_v1'} if original else {}
                table.save(using=alias, update_fields=['tournament_table', 'machine_snapshot'])
                if current:
                    Reservation.objects.using(alias).create(table_id=fixed.pk, machine_id=current.machine_id, legacy_allocation_id=current.pk, source='legacy_bridge_v1', machine_no_snapshot=current.machine_no_snapshot, created_by_id=current.allocated_by_id)
                valid = valid and current is not None and current.machine.status == 'available'
            valid_order = len(order) == len(expected) and len(set(order)) == len(expected) and set(order) == expected
            t.first_round_order = order if valid_order else []
            t.order_source = 'legacy_table_wind_v1' if valid_order else 'legacy_incomplete'
            t.resource_state = 'fixed' if valid and valid_order else 'review_required'
            t.compatibility_audit['valid_allocations'] = bool(valid and valid_order)
        t.save(using=alias, update_fields=['rules_source', 'compatibility_audit', 'first_round_order', 'order_source', 'resource_state'])


class Migration(migrations.Migration):
    dependencies = [('tournaments', '0003_lotteryrecord_tableresult_and_more'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot')]
    # Deliberately irreversible: removing bridges would expose occupied machines.
    operations = [migrations.RunPython(forwards)]
