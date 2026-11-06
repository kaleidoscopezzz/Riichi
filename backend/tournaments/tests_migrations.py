"""Populated upgrade 0003 -> 0004 -> 0005 -> 0006 with historical app states.

0004 is deliberately irreversible, so the already-migrated test database cannot
be rolled back to 0003. A private in-memory SQLite connection is migrated
forward from zero instead; Owner/QA databases are never touched.
"""
from django.db import IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

ALIAS = 'migration_history'
OLD = [('tournaments', '0003_lotteryrecord_tableresult_and_more'), ('machines', '0002_mahjongmachine_machine_number_digits_only')]
LOTTERY = [('tournaments', '0005_lottery_void'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot')]
WINDS = ['east', 'south', 'west', 'north']
SEATING = [2, 0, 3, 1]  # east..north take these group positions: order must follow winds, never IDs
HISTORY = ['machines_mahjongmachine', 'tournaments_tournament', 'tournaments_tournamentparticipant', 'tournaments_tournamentround', 'tournaments_roundtable', 'tournaments_roundseat', 'tournaments_machineallocation', 'tournaments_lotteryrecord']
# Columns 0004 is documented to backfill (all added by 0003); every other column must stay byte-identical, updated_at included.
BACKFILLED = {'tournaments_tournament': {'rules_source', 'compatibility_audit', 'first_round_order', 'order_source', 'resource_state'}, 'tournaments_roundtable': {'tournament_table_id', 'machine_snapshot'}}


class LegacyMigrationTests(TransactionTestCase):
    # The runner resolves `databases` (checks, test DB setup) before setUpClass, so the
    # private alias is registered and allowed only afterwards: it is never pre-migrated.
    databases = {'default'}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connections.settings[ALIAS] = {**connections['default'].settings_dict, 'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:', 'OPTIONS': {}, 'TEST': {'CHARSET': None, 'COLLATION': None, 'MIGRATE': True, 'MIRROR': None, 'NAME': None}}
        cls.databases = {'default', ALIAS}

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.databases = {'default'}
        del connections.settings[ALIAS]
        try:
            del connections[ALIAS]
        except AttributeError:
            pass

    def setUp(self):
        self.db = connections[ALIAS]

    def tearDown(self):
        # Django ignores close() for in-memory SQLite: drop the raw handle so the
        # framework's flush sees a fresh, empty database (flush skips missing tables).
        if self.db.connection is not None:
            self.db.connection.close()
            self.db.connection = None

    def migrate(self, targets=None):
        executor = MigrationExecutor(self.db)
        targets = targets or executor.loader.graph.leaf_nodes()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def snapshot(self, tables, skip=None):
        result = {}
        with self.db.cursor() as cursor:
            for table in tables:
                # Private alias is always SQLite; PRAGMA avoids Django's collation DDL parser.
                cursor.execute(f'PRAGMA table_info({self.db.ops.quote_name(table)})')
                columns = [c[1] for c in cursor.fetchall() if c[1] not in (skip or {}).get(table, ())]
                result[table] = (columns, self.rows(table, columns))
        return result

    def rows(self, table, columns):
        quote = self.db.ops.quote_name
        with self.db.cursor() as cursor:
            cursor.execute(f'SELECT {", ".join(map(quote, columns))} FROM {quote(table)} ORDER BY {quote("id")}')
            return cursor.fetchall()

    def assert_unchanged(self, snapshot):
        for table, (columns, rows) in snapshot.items():
            self.assertTrue(rows, table)
            self.assertEqual(self.rows(table, columns), rows, f'{table} historical column drift')

    def test_populated_upgrade_keeps_history_and_backfills(self):
        apps = self.migrate(OLD)
        model = lambda label: apps.get_model(*label.split('.')).objects.using(ALIAS)  # noqa: E731
        now = timezone.now()
        admin = model('accounts.User').create(username='migration_admin', is_staff=True)
        profiles = [model('players.PlayerProfile').create(user=model('accounts.User').create(username=f'migration_player{i}'), nickname=f'迁移选手{i}') for i in range(8)]
        machines = [model('machines.MahjongMachine').create(machine_no=f'{i+1:03}', name=f'旧物理桌{i+1}', capacity_slot=i+1) for i in range(4)]
        model('machines.MahjongMachine').create(machine_no='005', name='更早退役设备', status='retired')
        cases, orders, allocations = {}, {}, {}
        for kind, size in [('valid', 8), ('released', 4), ('unrounded', 4)]:
            t = model('tournaments.Tournament').create(name=kind, round_count=1, created_by=admin, status='started', started_at=now, uma=['30.12345678901234567890123456789', '10', '-10', '-30'])
            entries = [model('tournaments.TournamentParticipant').create(tournament=t, player=p, display_name_snapshot=p.nickname) for p in profiles[:size]]
            cases[kind], orders[kind], allocations[kind] = t.pk, [], []
            if kind == 'unrounded':
                continue
            r = model('tournaments.TournamentRound').create(tournament=t, round_number=1, generated_by=admin)
            for i in range(size // 4):
                table = model('tournaments.RoundTable').create(round=r, table_number=i+1)
                group = entries[i*4:i*4+4]
                for wind, position in reversed(list(zip(WINDS, SEATING))):  # north row first: never ID order
                    model('tournaments.RoundSeat').create(round=r, table=table, participant=group[position], seat_wind=wind)
                orders[kind].extend(group[position].pk for position in SEATING)
                machine, released = (machines[i], False) if kind == 'valid' else (machines[3], True)
                allocations[kind].append(model('tournaments.MachineAllocation').create(table=table, machine=machine, machine_no_snapshot=machine.machine_no, allocated_by=admin, status='released' if released else 'active', released_by=admin if released else None, released_at=now if released else None, release_reason='旧版真实释放' if released else '').pk)
        lottery = dict(tournament_id=cases['valid'], source_versions=[], members=orders['valid'][:2], order=orders['valid'][1::-1], method='旧签条', description='0003时代的抽签记录', drawn_at=now, created_by=admin)
        pending = model('tournaments.LotteryRecord').create(**lottery)
        confirmed = model('tournaments.LotteryRecord').create(**lottery, confirmed_by=admin, confirmed_at=now)
        history = self.snapshot(HISTORY, BACKFILLED)

        apps = self.migrate(LOTTERY)
        model = lambda label: apps.get_model(*label.split('.')).objects.using(ALIAS)  # noqa: E731
        state = {kind: model('tournaments.Tournament').get(pk=pk) for kind, pk in cases.items()}
        # 0004: complete active occupancy inherits fixed tables; released history needs review; first order from table number + winds.
        self.assertEqual([(t.resource_state, t.order_source, t.first_round_order) for t in state.values()], [('fixed', 'legacy_table_wind_v1', orders['valid']), ('review_required', 'legacy_table_wind_v1', orders['released']), ('unselected', '', [])])
        self.assertEqual([(t.rules_source, t.compatibility_audit['migration']) for t in state.values()], [('legacy_default_backfill:0004', '0004')] * 3)
        self.assertEqual((state['valid'].compatibility_audit['valid_allocations'], state['released'].compatibility_audit['valid_allocations']), (True, False))
        bridged = list(model('tournaments.TournamentMachineReservation').select_related('table').order_by('id'))
        self.assertEqual([(r.legacy_allocation_id, r.machine_id, r.status, r.source, r.table.ordinal, r.table.tournament_id) for r in bridged], [(allocations['valid'][i], machines[i].pk, 'active', 'legacy_bridge_v1', i+1, cases['valid']) for i in range(2)])
        self.assertEqual(sorted(model('tournaments.TournamentTable').values_list('tournament_id', 'ordinal')), sorted([(cases['valid'], 1), (cases['valid'], 2), (cases['released'], 1)]))
        snapshots = {x.pk: (x.tournament_table.ordinal, x.machine_snapshot) for x in model('tournaments.RoundTable').select_related('tournament_table')}
        self.assertEqual(sorted(snapshots.values(), key=lambda x: (x[1]['machine_id'], x[0])), [(1, {'machine_id': machines[0].pk, 'machine_no': '001', 'source': 'legacy_round_v1'}), (2, {'machine_id': machines[1].pk, 'machine_no': '002', 'source': 'legacy_round_v1'}), (1, {'machine_id': machines[3].pk, 'machine_no': '004', 'source': 'legacy_round_v1'})])
        # 0005: existing lottery rows are untouched and unvoided; the void-state CHECK is live.
        Lottery = model('tournaments.LotteryRecord')
        self.assertEqual(list(Lottery.order_by('id').values_list('id', 'voided_at', 'voided_by_id', 'void_reason')), [(pending.pk, None, None, ''), (confirmed.pk, None, None, '')])
        for values in [{'voided_at': now}, {'voided_at': now, 'voided_by_id': admin.pk}, {'voided_at': now, 'voided_by_id': admin.pk, 'void_reason': '已确认不能作废'}]:
            target = confirmed.pk if 'void_reason' in values else pending.pk
            with self.subTest(values=sorted(values)), self.assertRaises(IntegrityError), transaction.atomic(using=ALIAS):
                Lottery.filter(pk=target).update(**values)
        # Rows written by the pre-0006 code: release overwrote `reason`.
        fixed = model('tournaments.TournamentTable').create(tournament_id=cases['unrounded'], ordinal=1)
        Reservation = model('tournaments.TournamentMachineReservation')
        old = Reservation.create(table=fixed, machine_id=machines[2].pk, machine_no_snapshot='003', created_by_id=admin.pk, status='released', released_by_id=admin.pk, released_at=now, reason='正式完赛自动释放')
        live = Reservation.create(table=fixed, machine_id=machines[3].pk, machine_no_snapshot='004', created_by_id=admin.pk, source='fault_replacement_v1', reason='实体故障')
        reservations = self.snapshot(['tournaments_tournamentmachinereservation'])

        apps = self.migrate()
        Reservation = apps.get_model('tournaments', 'TournamentMachineReservation').objects.using(ALIAS)
        # 0006: only released rows copy their reason; `reason` itself is unchanged.
        self.assertEqual(list(Reservation.order_by('id').values_list('id', 'status', 'reason', 'release_reason')), [(r.pk, 'active', '', '') for r in bridged] + [(old.pk, 'released', '正式完赛自动释放', '正式完赛自动释放'), (live.pk, 'active', '实体故障', '')])
        self.assert_unchanged(history)
        self.assert_unchanged(reservations)
        # 0006 reverses as a pure column drop and re-applies identically.
        self.migrate([('tournaments', '0005_lottery_void')])
        self.assert_unchanged(reservations)
        apps = self.migrate()
        self.assertEqual(apps.get_model('tournaments', 'TournamentMachineReservation').objects.using(ALIAS).get(pk=old.pk).release_reason, '正式完赛自动释放')
        self.assert_unchanged(history)

    def test_shared_review_rehearsal_checks_original_schema_projection(self):
        from verification.review_migration_check import BEFORE_REVIEW, rehearse_review_migrations

        apps = self.migrate(BEFORE_REVIEW)
        model = lambda label: apps.get_model(*label.split('.')).objects.using(ALIAS)
        admin = model('accounts.User').create(username='review_qa_admin', is_staff=True)
        tournament = model('tournaments.Tournament').create(name='review QA', round_count=1, created_by=admin)
        machine = model('machines.MahjongMachine').create(machine_no='004', name='review QA table')
        members = [model('tournaments.TournamentParticipant').create(tournament=tournament, player=model('players.PlayerProfile').create(user=model('accounts.User').create(username=f'review_player{i}'), nickname=f'QA{i}'), display_name_snapshot=f'QA{i}').pk for i in range(2)]
        result = rehearse_review_migrations(self.db, tournament_id=tournament.pk, admin_id=admin.pk, machine_id=machine.pk, members=members)
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(result['database_vendor'], 'sqlite')
        self.assertEqual(result['invalid_void_states_rejected'], 3)
        self.assertTrue(result['released_only_copy'])
        self.assertTrue(result['migration_rerun_noop'])
