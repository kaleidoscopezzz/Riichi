import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from fractions import Fraction
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, IntegrityError, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.services import create_machine, change_machine, MachineConflict
from .models import Tournament, TournamentRound, RoundSeat, RoundTable, MachineAllocation, TableResult, LotteryRecord, TournamentMachineReservation as Reservation
from .services import create_tournament, mutate_tournament, TournamentConflict
from .competition_services import (generate, write_result, ranking, metric, source_versions, preview, record_lottery, confirm_lottery, void_lottery, finish, replace_machine, review_legacy, bridge_legacy, locked, mapping)
from .scoring import score, pack, unpack
from .legacy_test_fixture import generate_first_round
from .round_services import change_allocation


class Fixtures:
    def setup_data(self):
        self.admin = get_user_model().objects.create_user(username='competition_admin', is_staff=True)
        self.users = [get_user_model().objects.create_user(username=f'competitor{i}') for i in range(16)]
        self.machines = [create_machine({'machine_no': f'{i+1:03}', 'name': f'物理桌{i+1}'}) for i in range(7)]

    def tournament(self, n=4, rounds=1, **kw):
        t = create_tournament(self.admin, {'name': '真实领域服务测试', 'round_count': rounds, 'participant_ids': [u.player_profile.pk for u in self.users[:n]], **kw})
        return mutate_tournament(t.pk, start=True)

    def existing_swiss(self, n=4, rounds=1, strategy='swiss_scores_first_v1'):
        # Simulate a stored pre-0010 draft; new creation must no longer accept Swiss.
        t = create_tournament(self.admin, {'name': '既有瑞士轮赛事', 'round_count': rounds,
                             'participant_ids': [u.player_profile.pk for u in self.users[:n]]})
        Tournament.objects.filter(pk=t.pk).update(pairing_strategy=strategy)
        return mutate_tournament(t.pk, start=True)

    def first(self, t, ids=None):
        return generate(t.pk, self.admin, 1, machine_ids=ids or [m.pk for m in self.machines[:t.participants.count()//4]])

    def confirm(self, table, points=None):
        points = points or [40000, 30000, 20000, 10000]
        participants = [s.participant_id for s in table.seats.order_by('id')]
        return write_result(table.pk, self.admin, 0, points=[{'participant_id': pk, 'raw_points': p} for pk, p in zip(participants, points)], confirm=True)

    def resolve(self, t):
        for members in preview(t.pk)['unresolved_groups']:
            row = record_lottery(t.pk, self.admin, {'members': members, 'order': list(reversed(members)), 'method': '现场签条', 'description': '公开抽取顺序，测试真实记录服务', 'drawn_at': timezone.now(), 'source_versions': source_versions(t)})
            confirm_lottery(t.pk, row.pk, self.admin)

    def draw(self, t, order=None):
        members = preview(t.pk)['unresolved_groups'][0]
        return members, {'members': members, 'order': order or members, 'method': '纸签', 'description': '公开监督', 'drawn_at': timezone.now(), 'source_versions': source_versions(t)}

    def legacy_round(self, t, machines):
        # A still-running F0-05 process writing round 1 directly; one table per given machine.
        r = TournamentRound.objects.create(tournament=t, round_number=1, generated_by=self.admin)
        entries = list(t.participants.all())
        for i, machine in enumerate(machines):
            table = RoundTable.objects.create(round=r, table_number=i+1)
            RoundSeat.objects.bulk_create([RoundSeat(round=r, table=table, participant=p, seat_wind=w) for p, w in zip(entries[i*4:i*4+4], ['east', 'south', 'west', 'north'])])
            MachineAllocation.objects.create(table=table, machine=machine, machine_no_snapshot=machine.machine_no, allocated_by=self.admin)
        return r


class CompetitionTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def test_complete_four_eight_twelve_sixteen_and_reuse(self):
        for n, rounds in [(4, 1), (8, 3), (12, 2), (16, 6)]:
            t = self.tournament(n, rounds)
            first = self.first(t)
            fixed = list(Reservation.objects.filter(table__tournament=t).values_list('machine_id', flat=True))
            for number in range(1, rounds+1):
                r = first if number == 1 else generate(t.pk, self.admin, number)
                self.assertEqual(r.seats.count(), n)
                for table in r.tables.all():
                    self.confirm(table)
                self.assertEqual(list(Reservation.objects.filter(table__tournament=t, status='active').values_list('machine_id', flat=True)), fixed)
            self.resolve(t)
            snapshot = finish(t.pk, self.admin, source_versions(t))
            self.assertEqual(len(snapshot['standings']), n)
            self.assertEqual({r['rank'] for r in snapshot['standings']}, set(range(1, n+1)))
            self.assertEqual(sum(r['rank'] == 1 for r in snapshot['standings']), 1)
            self.assertFalse(Reservation.objects.filter(table__tournament=t, status='active').exists())
            t.refresh_from_db()
            self.assertEqual(t.status, 'completed')
            self.assertEqual(preview(t.pk)['standings'], snapshot['standings'])

    def test_all_tie_patterns_exact_bonus(self):
        t = self.tournament()
        for points, expected in [([40000,30000,20000,10000],[50,10,-10,-30]),([35000,35000,20000,10000],[30,30,-10,-30]),([40000,25000,25000,10000],[50,0,0,-30]),([40000,30000,15000,15000],[50,10,-20,-20]),([30000,30000,30000,10000],[Fraction(50,3)]*3+[-30]),([40000,20000,20000,20000],[50,-10,-10,-10]),([30000,30000,20000,20000],[30,30,-20,-20]),([25000]*4,[5]*4)]:
            result = score(t, dict(enumerate(points, 1)))
            self.assertEqual([unpack(x['bonus']) for x in result], expected)
            self.assertEqual(sum((unpack(x['score']) for x in result), Fraction()), 0)
            self.assertEqual([unpack(x['score']) for x in json.loads(json.dumps(result))], [unpack(x['score']) for x in result])

    def test_long_decimal_nonzero_uma_and_different_start(self):
        t = self.tournament(starting_points=30000, return_points=35000, uma=['30.12345678901234567890123456789','10','-10','-29'])
        results = score(t, dict(enumerate([40000,40000,40000,0],1)))
        self.assertEqual(unpack(results[0]['bonus']), (Fraction(t.uma[0])+20)/3)
        self.assertEqual(sum((unpack(r['score']) for r in results), Fraction()), sum(map(Fraction,t.uma)))

    def test_partial_draft_negative_zero_sum_and_locked_audit(self):
        t = self.tournament(); table = self.first(t).tables.get()
        p = list(table.seats.values_list('participant_id',flat=True))
        row = write_result(table.pk,self.admin,0,points=[{'participant_id':p[0],'raw_points':-1000}])
        self.assertEqual(row['version'],1)
        self.assertEqual(sum(x['confirmed_rounds'] for x in ranking(t)[0]),0)
        with self.assertRaises(ValidationError): write_result(table.pk,self.admin,1,confirm=True)
        with self.assertRaises(TournamentConflict): write_result(table.pk,self.admin,0,points=[])
        row = write_result(table.pk,self.admin,1,points=[{'participant_id':pk,'raw_points':v} for pk,v in zip(p,[-1000,0,51000,50000])],confirm=True)
        self.assertEqual(row['status'],'confirmed'); self.assertEqual(row['confirmed_by'],self.admin.pk)
        with self.assertRaises(TournamentConflict): write_result(table.pk,self.admin,2,points=[])

    def test_abnormal_total_only_draft_and_no_next(self):
        t = self.tournament(rounds=2); table=self.first(t).tables.get()
        values=[{'participant_id':s.participant_id,'raw_points':0} for s in table.seats.all()]
        write_result(table.pk,self.admin,0,points=values)
        with self.assertRaises(ValidationError): write_result(table.pk,self.admin,1,confirm=True)
        with self.assertRaises(TournamentConflict): generate(t.pk,self.admin,2)
        self.assertEqual(t.rounds.count(),1)

    def test_first_sequence_pairing_fallback_and_new_winds(self):
        class Reverse:
            def shuffle(self, rows): rows.reverse()
        t = self.tournament(8,2)
        first=generate(t.pk,self.admin,1,machine_ids=[self.machines[4].pk,self.machines[1].pk],rng=Reverse())
        for table in first.tables.all(): self.confirm(table,[25000]*4)
        t.refresh_from_db(); order=t.first_round_order
        second=generate(t.pk,self.admin,2,rng=Reverse())
        self.assertEqual(second.generation_snapshot['sorted_participants'],order)
        self.assertEqual(list(second.tables.first().seats.order_by('id').values_list('participant_id',flat=True)),list(reversed(order[:4])))
        self.assertEqual([x.machine_snapshot['machine_id'] for x in second.tables.all()],[self.machines[4].pk,self.machines[1].pk])
        for table in second.tables.all(): self.confirm(table,[25000]*4)
        self.assertEqual(len(preview(t.pk)['unresolved_groups'][0]),8)
        with self.assertRaises(TournamentConflict): finish(t.pk,self.admin,source_versions(t))

    def test_metric_each_tiebreak_level_is_exact(self):
        base={'total':pack(1),'first_count':1,'second_count':1,'rounds':[{'score':pack(1)},{'score':pack(2)}]}
        for change in [{'total':pack(Fraction(10**60+1,10**60))},{'first_count':2},{'second_count':2},{'rounds':[{'score':pack(0)},{'score':pack(3)}]},{'rounds':[{'score':pack(2)},{'score':pack(2)}]}]:
            self.assertGreater(metric(base|change),metric(base))

    def test_fraction_database_multi_round_accumulation_is_lossless(self):
        t = self.tournament(rounds=3)
        target = None
        for number in range(1, 4):
            r = self.first(t) if number == 1 else generate(t.pk, self.admin, number)
            table = r.tables.get()
            participants = list(table.seats.values_list('participant_id', flat=True))
            target = target or participants[0]
            # Same target receives 50/3 reward for three consecutive first ties.
            points = [{'participant_id': pk, 'raw_points': 10000 if pk == next(x for x in participants if x != target) else 30000} for pk in participants]
            write_result(table.pk, self.admin, 0, points=points, confirm=True)
        rows, _ = ranking(t)
        actual = next(row for row in rows if row['participant_id'] == target)
        self.assertEqual(unpack(actual['total']), 50)
        self.assertEqual(actual['first_count'], 3)
        self.assertEqual(actual['second_count'], 0)
        self.assertTrue(all(unpack(row['score']) == Fraction(50, 3) for row in actual['rounds']))

    def test_database_reservation_unique_constraints(self):
        t = self.tournament(8)
        self.first(t)
        first, second = list(Reservation.objects.filter(status='active'))
        for table, machine in [(second.table, first.machine), (first.table, self.machines[6])]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Reservation.objects.create(table=table, machine=machine, created_by=self.admin, machine_no_snapshot=machine.machine_no)

    def test_legacy_new_event_share_keeps_original_allocation(self):
        legacy = self.tournament()
        r = generate_first_round(legacy.pk, self.admin)
        allocation = r.tables.get().allocations.get()
        shared = self.tournament()
        self.first(shared, [allocation.machine_id])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status, 'active')
        new = self.tournament()
        self.first(new, [self.machines[6].pk])
        replacement = change_allocation(r.tables.get().pk, self.admin, machine_id=self.machines[6].pk)
        self.assertEqual(replacement.machine_id, self.machines[6].pk)
        self.assertTrue(Reservation.objects.filter(table__tournament=new, status='active').exists())

    def test_multiple_lottery_groups_all_required(self):
        t = self.tournament(8)
        for table in self.first(t).tables.all():
            self.confirm(table)
        groups = preview(t.pk)['unresolved_groups']
        self.assertEqual(len(groups), 4)
        for members in groups[:-1]:
            row = record_lottery(t.pk, self.admin, {'members': members, 'order': members[::-1], 'method': '签条', 'description': '分组公开记录', 'drawn_at': timezone.now(), 'source_versions': source_versions(t)})
            confirm_lottery(t.pk, row.pk, self.admin)
        with self.assertRaises(TournamentConflict):
            finish(t.pk, self.admin, source_versions(t))
        self.resolve(t)
        self.assertEqual(len(finish(t.pk, self.admin, source_versions(t))['standings']), 8)

    def test_lottery_full_order_audit_version_and_completion(self):
        t=self.tournament(); table=self.first(t).tables.get(); self.confirm(table,[25000]*4)
        members=preview(t.pk)['unresolved_groups'][0]
        values={'members':members,'order':members[:-1],'method':'纸签','description':'公开监督','drawn_at':timezone.now(),'source_versions':source_versions(t)}
        with self.assertRaises(ValidationError): record_lottery(t.pk,self.admin,values)
        row=record_lottery(t.pk,self.admin,values|{'order':list(reversed(members))})
        self.assertFalse(preview(t.pk)['ready'])
        confirm_lottery(t.pk,row.pk,self.admin)
        with self.assertRaises(TournamentConflict): confirm_lottery(t.pk,row.pk,self.admin)
        with self.assertRaises(TournamentConflict): finish(t.pk,self.admin,[])
        result=finish(t.pk,self.admin,source_versions(t))
        self.assertEqual(result['champion_id'],members[-1])
        row.refresh_from_db(); self.assertIsNotNone(row.confirmed_at)
        with self.assertRaises(TournamentConflict): finish(t.pk,self.admin,source_versions(t))

    def test_fixed_resource_shared_associations_and_old_release_guard(self):
        t=self.tournament(); table=self.first(t).tables.get()
        self.first(self.tournament())
        self.assertEqual(Reservation.objects.filter(machine=self.machines[0], status='active').count(), 2)
        change_machine(self.machines[0].pk, {'status': 'maintenance'})
        with self.assertRaises(TournamentConflict): change_allocation(table.pk,self.admin)
        before=table.machine_snapshot
        replace_machine(t.pk,1,self.admin,self.machines[5].pk,'物理故障')
        table.refresh_from_db(); self.assertEqual(table.machine_snapshot,before)
        self.assertEqual(Reservation.objects.filter(table__tournament=t,status='active').get().machine_id,self.machines[5].pk)
        change_machine(self.machines[0].pk, {'status': 'available'})
        self.first(self.tournament())

    def test_legacy_valid_inherits_and_keeps_history(self):
        t=self.tournament(8,2); r=generate_first_round(t.pk,self.admin)
        seats=list(RoundSeat.objects.values_list('id','table_id','participant_id','seat_wind'))
        allocations=list(MachineAllocation.objects.values_list('id','machine_id','status'))
        with locked(t.pk) as (t,_): bridge_legacy(t,self.admin)
        self.assertEqual(t.resource_state,'fixed')
        self.assertEqual(t.first_round_order,[s.participant_id for table in r.tables.all() for w in ['east','south','west','north'] for s in table.seats.filter(seat_wind=w)])
        self.assertEqual(list(RoundSeat.objects.values_list('id','table_id','participant_id','seat_wind')),seats)
        self.assertEqual(list(MachineAllocation.objects.values_list('id','machine_id','status')),allocations)
        for table in r.tables.all(): self.confirm(table)
        generate(t.pk,self.admin,2)

    def test_legacy_released_review_no_reclaim_and_historical_finish(self):
        t=self.tournament(); r=generate_first_round(t.pk,self.admin); table=r.tables.get()
        change_allocation(table.pk,self.admin,reason='旧版真实释放')
        other=self.tournament(); self.first(other)
        with locked(t.pk) as (t,_): bridge_legacy(t,self.admin)
        self.assertEqual(t.resource_state,'review_required')
        # Shared associations are now legal, but review never reclaims implicitly.
        self.assertFalse(Reservation.objects.filter(table__tournament=t, status='active').exists())
        review_legacy(t.pk,self.admin,historical_only=True,machine_ids=[],reason='所有实体对局已结束，仅补历史成绩')
        self.confirm(table); self.resolve(t); finish(t.pk,self.admin,source_versions(t))
        self.assertTrue(Reservation.objects.filter(table__tournament=other,status='active').exists())
        self.assertEqual(MachineAllocation.objects.get(table=table).release_reason,'旧版真实释放')

    def test_failure_rollbacks_generation_result_replacement_finish(self):
        t=self.tournament(8)
        with patch('tournaments.competition_services.RoundSeat.objects.bulk_create',side_effect=IntegrityError('injected')), self.assertRaises(TournamentConflict): self.first(t)
        self.assertFalse(t.rounds.exists()); self.assertFalse(Reservation.objects.exists())
        r=self.first(t)
        with patch('tournaments.competition_services.score',side_effect=IntegrityError('injected')),self.assertRaises(TournamentConflict): self.confirm(r.tables.first())
        self.assertFalse(TableResult.objects.exists())
        with patch('tournaments.competition_services.Reservation.objects.create',side_effect=IntegrityError('injected')),self.assertRaises(TournamentConflict): replace_machine(t.pk,1,self.admin,self.machines[6].pk,'故障')
        self.assertEqual(Reservation.objects.filter(status='active').count(),2)
        for table in r.tables.all(): self.confirm(table)
        self.resolve(t)
        with patch('tournaments.competition_services.release_reservation',side_effect=IntegrityError('injected')),self.assertRaises(TournamentConflict): finish(t.pk,self.admin,source_versions(t))
        t.refresh_from_db();self.assertEqual(t.status,'started');self.assertFalse(t.final_snapshot);self.assertEqual(Reservation.objects.filter(status='active').count(),2)

    def code(self, call):
        with self.assertRaises(TournamentConflict) as error:
            call()
        return error.exception.default_code

    def test_confirm_only_keeps_draft_editor_audit(self):
        other = get_user_model().objects.create_user(username='second_admin', is_staff=True)
        t = self.tournament(8); first, second = list(self.first(t).tables.all())
        for table in (first, second):
            write_result(table.pk, self.admin, 0, points=[{'participant_id': s.participant_id, 'raw_points': v} for s, v in zip(table.seats.order_by('id'), [40000, 30000, 20000, 10000])])
        past = timezone.now() - timedelta(days=1)
        TableResult.objects.update(edited_at=past)  # any auto_now rewrite becomes visible
        row = write_result(first.pk, other, 1, confirm=True)
        stored = TableResult.objects.get(table=first)
        self.assertEqual((stored.edited_by_id, stored.edited_at, stored.confirmed_by_id, stored.status, stored.version), (self.admin.pk, past, other.pk, 'confirmed', 2))
        self.assertEqual((row['edited_by'], row['edited_at'], row['confirmed_by']), (self.admin.pk, past, other.pk))
        # Confirming WITH points is an edit: the confirmer becomes the editor.
        points = [{'participant_id': s.participant_id, 'raw_points': 25000} for s in second.seats.all()]
        write_result(second.pk, other, 1, points=points, confirm=True)
        stored = TableResult.objects.get(table=second)
        self.assertEqual((stored.edited_by_id, stored.confirmed_by_id, stored.points), (other.pk, other.pk, {str(x['participant_id']): 25000 for x in points}))
        self.assertGreater(stored.edited_at, past)

    def test_lottery_pending_void_and_only_confirmed_ranks(self):
        other = self.tournament(); self.confirm(self.first(other, [self.machines[1].pk]).tables.get(), [25000]*4)
        foreign = record_lottery(other.pk, self.admin, self.draw(other)[1])
        t = self.tournament(); self.confirm(self.first(t).tables.get(), [25000]*4)
        members, values = self.draw(t)
        row = record_lottery(t.pk, self.admin, values)
        # Neither the same nor a "better" order may be recorded while one is open.
        for order in [members, members[::-1]]:
            self.assertEqual(self.code(lambda: record_lottery(t.pk, self.admin, values | {'order': order})), 'lottery_pending')
        with self.assertRaises(Http404):
            void_lottery(t.pk, foreign.pk, self.admin, '他场记录')
        voided = void_lottery(t.pk, row.pk, self.admin, '签条污损，重新公开抽取')
        self.assertEqual((voided.voided_by_id, voided.void_reason, voided.confirmed_at), (self.admin.pk, '签条污损，重新公开抽取', None))
        self.assertIsNotNone(voided.voided_at)
        self.assertEqual(self.code(lambda: void_lottery(t.pk, row.pk, self.admin, '重复作废')), 'lottery_voided')
        self.assertEqual(self.code(lambda: confirm_lottery(t.pk, row.pk, self.admin)), 'lottery_voided')
        # Voided and unconfirmed records never rank or complete.
        self.assertEqual([set(g) for g in preview(t.pk)['unresolved_groups']], [set(members)])
        self.assertEqual(self.code(lambda: finish(t.pk, self.admin, source_versions(t))), 'lottery_required')
        second = record_lottery(t.pk, self.admin, values | {'order': members[::-1]})
        confirm_lottery(t.pk, second.pk, self.admin)
        self.assertEqual(self.code(lambda: void_lottery(t.pk, second.pk, self.admin, '确认后作废')), 'lottery_conflict')
        result = finish(t.pk, self.admin, source_versions(t))
        self.assertEqual((result['champion_id'], result['lottery_ids']), (members[-1], [second.pk]))
        self.assertEqual(self.code(lambda: void_lottery(t.pk, row.pk, self.admin, '完赛后')), 'tournament_completed')
        self.assertEqual(list(t.lotteries.order_by('id').values_list('id', flat=True)), [row.pk, second.pk])

    def test_lottery_void_state_database_constraint(self):
        t = self.tournament(); self.confirm(self.first(t).tables.get(), [25000]*4)
        row = record_lottery(t.pk, self.admin, self.draw(t)[1])
        now = timezone.now()
        for values in [{'voided_at': now}, {'voided_by': self.admin}, {'void_reason': '仅有原因'}, {'voided_at': now, 'voided_by': self.admin}, {'voided_at': now, 'voided_by': self.admin, 'void_reason': '确认后作废', 'confirmed_at': now, 'confirmed_by': self.admin}]:
            with self.subTest(values=sorted(values)), self.assertRaises(IntegrityError), transaction.atomic():
                LotteryRecord.objects.filter(pk=row.pk).update(**values)
        self.assertEqual(LotteryRecord.objects.filter(pk=row.pk).update(voided_at=now, voided_by=self.admin, void_reason='合法作废'), 1)

    def test_fault_replacement_reason_survives_completion_release(self):
        t = self.tournament(); table = self.first(t).tables.get()
        replace_machine(t.pk, 1, self.admin, self.machines[5].pk, '实体故障：自动洗牌异常')
        self.confirm(table); finish(t.pk, self.admin, source_versions(t))
        original, replacement = Reservation.objects.filter(table__tournament=t).order_by('id')
        self.assertEqual((original.reason, original.release_reason), ('', '实体故障：自动洗牌异常'))
        self.assertEqual((replacement.source, replacement.status, replacement.reason, replacement.release_reason), ('fault_replacement_v1', 'released', '实体故障：自动洗牌异常', '正式完赛自动释放'))
        self.assertEqual([(h['reason'], h['release_reason']) for h in mapping(t)[0]['history']], [('', '实体故障：自动洗牌异常'), ('实体故障：自动洗牌异常', '正式完赛自动释放')])

    def test_historical_only_cannot_take_new_machine(self):
        t = self.tournament(8); kept, released = list(generate_first_round(t.pk, self.admin).tables.all())
        change_allocation(released.pk, self.admin, reason='旧版真实释放')
        review_legacy(t.pk, self.admin, historical_only=True, machine_ids=[], reason='实体对局均已结束，仅补历史成绩')
        t.refresh_from_db(); self.assertEqual(t.resource_state, 'historical_only')
        before = list(Reservation.objects.values_list('id', 'machine_id', 'status', 'reason'))
        # The bridged reservation of table A must not be swapped onto a new physical table.
        self.assertEqual(self.code(lambda: replace_machine(t.pk, 1, self.admin, self.machines[5].pk, '不应占用新桌')), 'historical_only')
        self.assertEqual(list(Reservation.objects.values_list('id', 'machine_id', 'status', 'reason')), before)

    def test_review_incomplete_legacy_tables_is_conflict(self):
        # One table recorded for eight players: only logical table A can exist.
        t = self.tournament(8); self.legacy_round(t, [self.machines[0]])
        with locked(t.pk) as (t, _): bridge_legacy(t, self.admin)
        self.assertEqual((t.resource_state, t.order_source, list(t.fixed_tables.values_list('ordinal', flat=True))), ('review_required', 'legacy_incomplete', [1]))
        self.assertEqual(self.code(lambda: review_legacy(t.pk, self.admin, historical_only=False, machine_ids=[self.machines[0].pk, self.machines[2].pk], reason='补选空闲桌')), 'legacy_structure_invalid')
        self.assertEqual(Reservation.objects.filter(source='legacy_review_v1').count(), 0)

    def test_bridge_malformed_first_round_written_after_migration(self):
        # Migrated as unselected without rounds; an old process then wrote a seat-incomplete round 1.
        t = self.tournament(8); r = generate_first_round(t.pk, self.admin)
        r.tables.get(table_number=2).seats.get(seat_wind='north').delete()
        seats = list(RoundSeat.objects.order_by('id').values_list('id', 'table_id', 'participant_id', 'seat_wind'))
        allocations = list(MachineAllocation.objects.order_by('id').values_list('id', 'machine_id', 'status'))
        with locked(t.pk) as (t, _): bridge_legacy(t, self.admin)  # formerly a 400 on every write path, forever
        self.assertEqual((t.resource_state, t.order_source, t.first_round_order, t.compatibility_audit['valid_allocations']), ('review_required', 'legacy_incomplete', [], False))
        self.assertEqual(list(t.fixed_tables.values_list('ordinal', flat=True)), [1, 2])
        self.assertEqual(sorted(Reservation.objects.filter(status='active', source='legacy_bridge_v1').values_list('legacy_allocation_id', 'machine_id')), [(a[0], a[1]) for a in allocations])
        self.assertEqual(list(RoundSeat.objects.order_by('id').values_list('id', 'table_id', 'participant_id', 'seat_wind')), seats)
        self.assertEqual(list(MachineAllocation.objects.order_by('id').values_list('id', 'machine_id', 'status')), allocations)
        shared = self.tournament(8)
        self.first(shared, [a[1] for a in allocations])
        self.assertEqual(Reservation.objects.filter(table__tournament=shared, status='active').count(), 2)
        self.assertEqual(list(MachineAllocation.objects.order_by('id').values_list('id', 'machine_id', 'status')), allocations)
        review_legacy(t.pk, self.admin, historical_only=True, machine_ids=[], reason='首轮记录异常，仅保留历史')
        t.refresh_from_db(); self.assertEqual(t.resource_state, 'historical_only')
        # Valid legacy data keeps exactly the previous bridge result.
        valid = self.tournament(4); r = generate_first_round(valid.pk, self.admin)
        with locked(valid.pk) as (valid, _): bridge_legacy(valid, self.admin)
        self.assertEqual((valid.resource_state, valid.order_source, set(valid.compatibility_audit), valid.compatibility_audit['valid_allocations']), ('fixed', 'legacy_table_wind_v1', {'source', 'identified_at', 'valid_allocations'}, True))
        self.assertEqual(valid.first_round_order, [r.tables.get().seats.get(seat_wind=w).participant_id for w in ['east', 'south', 'west', 'north']])


class CompetitionApiTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data();self.t=self.tournament();self.table=self.first(self.t).tables.get()
        self.client=Client(enforce_csrf_checks=True);self.client.force_login(self.admin)
        self.token=self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']

    def test_permissions_csrf_all_new_writes(self):
        paths=[f'tournaments/{self.t.pk}/workspace/',f'tournaments/{self.t.pk}/tables/replace/',f'tournaments/{self.t.pk}/compatibility-review/',f'tournaments/{self.t.pk}/lotteries/',f'tournaments/{self.t.pk}/lotteries/1/confirm/',f'tournaments/{self.t.pk}/lotteries/1/void/',f'tournaments/{self.t.pk}/complete/',f'round-tables/{self.table.pk}/result/',f'round-tables/{self.table.pk}/result/confirm/']
        for who in [None,self.users[0]]:
            client=Client(enforce_csrf_checks=True)
            if who: client.force_login(who)
            for path in paths:
                self.assertEqual(client.get('/api/v1/'+path).status_code,403)
                self.assertEqual(client.post('/api/v1/'+path,{},content_type='application/json').status_code,403)
        for path in paths[1:]:
            self.assertEqual(self.client.post('/api/v1/'+path,{},content_type='application/json').status_code,403)

    def test_strict_invalid_points_and_safe_json_roundtrip(self):
        url=f'/api/v1/round-tables/{self.table.pk}/result/'
        pk=self.table.seats.first().participant_id
        for body in [{'version':0,'points':[{'participant_id':pk,'raw_points':v}]} for v in [True,1.5,'1',2**53]] + [{'version':0,'points':[],'scores':[]},{'version':0,'points':[{'participant_id':pk,'raw_points':0,'seat_wind':'east'}]}]:
            self.assertEqual(self.client.put(url,body,content_type='application/json',HTTP_X_CSRFTOKEN=self.token).status_code,400)
        for values in [[{'participant_id':pk,'raw_points':0}]*2,[{'participant_id':9999,'raw_points':1}]]:
            self.assertEqual(self.client.put(url,{'version':0,'points':values},content_type='application/json',HTTP_X_CSRFTOKEN=self.token).status_code,400)
        row=self.confirm(self.table,[30000,30000,30000,10000])
        stored=TableResult.objects.get(table=self.table)
        self.assertEqual(stored.scores,row['scores'])
        data=self.client.get(url).json()['data'];self.assertEqual(unpack(data['scores'][0]['bonus']),Fraction(50,3))

    def post(self, path, body, client=None, token=None):
        return (client or self.client).post('/api/v1/' + path, body, content_type='application/json', HTTP_X_CSRFTOKEN=token or self.token)

    def test_http_result_confirm_lottery_void_complete_and_workspace(self):
        other = get_user_model().objects.create_user(username='http_second_admin', is_staff=True)
        confirmer = Client(enforce_csrf_checks=True); confirmer.force_login(other)
        token = confirmer.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
        url = f'round-tables/{self.table.pk}/result/'
        points = [{'participant_id': s.participant_id, 'raw_points': 25000} for s in self.table.seats.all()]
        draft = self.client.put('/api/v1/' + url, {'version': 0, 'points': points}, content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual((draft.status_code, draft.json()['data']['version'], draft.json()['data']['status']), (200, 1, 'draft'))
        confirmed = self.post(url + 'confirm/', {'version': 1}, confirmer, token)
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        data = confirmed.json()['data']
        self.assertEqual((data['status'], data['version'], data['edited_by'], data['confirmed_by'], data['edited_at']), ('confirmed', 2, self.admin.pk, other.pk, draft.json()['data']['edited_at']))
        self.assertEqual(self.post(url + 'confirm/', {'version': 2}).json()['error']['code'], 'result_locked')
        workspace = self.client.get(f'/api/v1/tournaments/{self.t.pk}/workspace/')
        self.assertEqual((workspace.status_code, workspace['Cache-Control']), (200, 'no-store'))
        ws = workspace.json()['data']
        self.assertEqual((ws['status'], ws['resource_state'], ws['ready'], ws['all_results_confirmed'], ws['lotteries'], ws['mapping'][0]['machine_id']), ('started', 'fixed', False, True, [], self.machines[0].pk))
        members = ws['unresolved_groups'][0]
        self.assertEqual(set(members), {s.participant_id for s in self.table.seats.all()})
        body = {'members': members, 'order': members, 'method': '现场签条', 'description': '公开抽取，全员见证', 'drawn_at': timezone.now().isoformat(), 'source_versions': ws['source_versions']}
        lottery = self.post(f'tournaments/{self.t.pk}/lotteries/', body)
        self.assertEqual(lottery.status_code, 201, lottery.content)
        first = lottery.json()['data']
        self.assertEqual((first['confirmed_at'], first['voided_by_id'], first['voided_at'], first['void_reason']), (None, None, None, ''))
        pending = self.post(f'tournaments/{self.t.pk}/lotteries/', body | {'order': members[::-1]})
        self.assertEqual((pending.status_code, pending.json()['error']['code'], pending.json()['error']['message']), (409, 'lottery_pending', '该并列组已有待确认的抽签记录，请先确认或作废后再录入。'))
        void = f'tournaments/{self.t.pk}/lotteries/{first["id"]}/void/'
        for bad in [{}, {'reason': ''}, {'reason': ' \t '}, {'reason': '长' * 501}, {'reason': 5}, {'reason': None}, {'reason': ['作废']}, {'reason': '原因', 'confirmed': True}, []]:
            self.assertEqual(self.post(void, bad).status_code, 400, bad)
        missing = self.post(f'tournaments/{self.t.pk}/lotteries/999999/void/', {'reason': '不存在'})
        self.assertEqual((missing.status_code, missing.json()['error']['code']), (404, 'not_found'))
        voided = self.post(void, {'reason': '  签条污损，重新公开抽取  '})
        self.assertEqual(voided.status_code, 200, voided.content)
        data = voided.json()['data']
        self.assertEqual((data['id'], data['voided_by_id'], data['void_reason'], data['confirmed_at']), (first['id'], self.admin.pk, '签条污损，重新公开抽取', None))
        self.assertIsNotNone(data['voided_at'])
        self.assertEqual(self.post(void, {'reason': '长' * 500}).json()['error']['code'], 'lottery_voided')
        self.assertEqual(self.post(f'tournaments/{self.t.pk}/lotteries/{first["id"]}/confirm/', {'confirmed': True}).json()['error']['code'], 'lottery_voided')
        second = self.post(f'tournaments/{self.t.pk}/lotteries/', body | {'order': members[::-1]})
        self.assertEqual(second.status_code, 201, second.content)
        second_id = second.json()['data']['id']
        approved = self.post(f'tournaments/{self.t.pk}/lotteries/{second_id}/confirm/', {'confirmed': True})
        self.assertEqual((approved.status_code, approved.json()['data']['confirmed_by_id']), (200, self.admin.pk))
        self.assertEqual(self.post(f'tournaments/{self.t.pk}/lotteries/{second_id}/void/', {'reason': '确认后作废'}).json()['error']['code'], 'lottery_conflict')
        ws = self.client.get(f'/api/v1/tournaments/{self.t.pk}/workspace/').json()['data']
        self.assertTrue(ws['ready'])
        self.assertEqual({x['id']: (x['void_reason'], x['confirmed_by_id']) for x in ws['lotteries']}, {first['id']: ('签条污损，重新公开抽取', None), second_id: ('', self.admin.pk)})
        complete = self.post(f'tournaments/{self.t.pk}/complete/', {'source_versions': ws['source_versions'], 'confirmed': True})
        self.assertEqual(complete.status_code, 200, complete.content)
        final = complete.json()['data']
        self.assertEqual((final['champion_id'], final['lottery_ids'], [r['rank'] for r in final['standings']]), (members[-1], [second_id], [1, 2, 3, 4]))
        done = self.client.get(f'/api/v1/tournaments/{self.t.pk}/workspace/').json()['data']
        self.assertEqual((done['status'], done['champion_id'], done['mapping'][0]['machine_id']), ('completed', members[-1], None))
        self.assertEqual(self.post(void, {'reason': '完赛后'}).json()['error']['code'], 'tournament_completed')
        self.assertEqual(self.post(f'tournaments/{self.t.pk}/complete/', {'source_versions': ws['source_versions'], 'confirmed': True}).status_code, 409)

    def test_http_fault_replacement_keeps_logical_table(self):
        response = self.post(f'tournaments/{self.t.pk}/tables/replace/', {'ordinal': 1, 'machine_id': self.machines[5].pk, 'reason': '实体故障'})
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()['data'][0]
        self.assertEqual((row['label'], row['machine_id'], row['reservation_id']), ('A', self.machines[5].pk, Reservation.objects.get(status='active').pk))
        self.assertEqual([(h['machine_id'], h['status'], h['reason'], h['release_reason']) for h in row['history']], [(self.machines[0].pk, 'released', '', '实体故障'), (self.machines[5].pk, 'active', '实体故障', '')])
        self.assertEqual(self.post(f'tournaments/{self.t.pk}/tables/replace/', {'ordinal': 1, 'machine_id': self.machines[5].pk, 'reason': '未改变'}).json()['error']['code'], 'machine_unchanged')
        self.assertEqual(self.post(f'tournaments/{self.t.pk}/tables/replace/', {'ordinal': 1, 'machine_id': self.machines[6].pk, 'reason': '多余字段', 'source': 'x'}).status_code, 400)
        self.table.refresh_from_db(); self.assertEqual(self.table.machine_snapshot['machine_id'], self.machines[0].pk)

    def test_http_compatibility_review_legacy(self):
        legacy = self.tournament(8); kept, released = list(generate_first_round(legacy.pk, self.admin).tables.all())
        change_allocation(released.pk, self.admin, reason='旧版真实释放')
        kept_machine = kept.allocations.get().machine_id
        body = {'historical_only': False, 'machine_ids': [kept_machine, self.machines[6].pk], 'reason': '保留有效占用，补选空闲桌'}
        response = self.post(f'tournaments/{legacy.pk}/compatibility-review/', body)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([(x['label'], x['machine_id']) for x in response.json()['data']], [('A', kept_machine), ('B', self.machines[6].pk)])
        legacy.refresh_from_db()
        self.assertEqual((legacy.resource_state, legacy.compatibility_audit['reviewed_by'], legacy.compatibility_audit['historical_only']), ('fixed', self.admin.pk, False))
        self.assertEqual(self.post(f'tournaments/{legacy.pk}/compatibility-review/', body).json()['error']['code'], 'review_not_required')
        self.assertEqual(MachineAllocation.objects.get(table=released).release_reason, '旧版真实释放')

    def test_http_incomplete_legacy_structure_is_409(self):
        legacy = self.tournament(8); self.legacy_round(legacy, [self.machines[3]])
        response = self.post(f'tournaments/{legacy.pk}/compatibility-review/', {'historical_only': False, 'machine_ids': [self.machines[3].pk, self.machines[4].pk], 'reason': '补选'})
        self.assertEqual((response.status_code, response.json()['error']['code']), (409, 'legacy_structure_invalid'))


class CompetitionConcurrencyTests(Fixtures, TransactionTestCase):
    def setUp(self): self.setup_data()

    def race(self, calls):
        barrier=Barrier(len(calls))
        def run(fn):
            close_old_connections()
            try: barrier.wait(timeout=15);fn();return 'ok'
            except (TournamentConflict,MachineConflict) as exc:return exc.default_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(run,calls))

    def test_same_round_and_cross_tournament_selection(self):
        a,b=self.tournament(),self.tournament()
        result=self.race([lambda:self.first(a),lambda:self.first(b)])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy'}, result)
        for tournament in (a, b):
            if not tournament.rounds.exists(): self.first(tournament)
        self.assertEqual(Reservation.objects.filter(status='active').count(), 2)

    def test_duplicate_confirm_next_finish(self):
        t=self.tournament(rounds=2);table=self.first(t).tables.get()
        result=self.race([lambda:self.confirm(table)]*2);self.assertEqual(result.count('ok'),1,result)
        result=self.race([lambda:generate(t.pk,self.admin,2)]*2);self.assertEqual(result.count('ok'),1,result)
        self.confirm(t.rounds.get(round_number=2).tables.get());self.resolve(t)
        versions=source_versions(t)
        result=self.race([lambda:finish(t.pk,self.admin,versions)]*2);self.assertEqual(result.count('ok'),1,result)
        self.assertFalse(Reservation.objects.filter(status='active').exists())

    def test_state_change_vs_selection(self):
        t=self.tournament()
        result=self.race([lambda:self.first(t),lambda:change_machine(self.machines[0].pk,{'status':'maintenance'})])
        self.assertGreaterEqual(result.count('ok'),1,result)
        active=Reservation.objects.filter(status='active').select_related('machine').first()
        # An association does not prevent subsequent maintenance; future generation rechecks state.
        if active:self.assertIn(active.machine.status, ('available', 'maintenance'))

    def test_confirmation_vs_next_round(self):
        t = self.tournament(rounds=2)
        table = self.first(t).tables.get()
        result = self.race([lambda: self.confirm(table), lambda: generate(t.pk, self.admin, 2)])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy', 'results_incomplete'}, result)
        # Shared-cache in-memory SQLite may reject the writer while the other
        # request observes an incomplete result and rolls back. Inspect before
        # an explicit new operation; never retry an uncertain transaction.
        if not TableResult.objects.filter(table=table, status='confirmed').exists():
            self.confirm(table)
        if t.rounds.filter(round_number=2).exists():
            self.assertEqual(TableResult.objects.get(table=table).status, 'confirmed')
        else:
            generate(t.pk, self.admin, 2)
        self.assertEqual(t.rounds.count(), 2)

    def test_confirmation_vs_finish(self):
        t = self.tournament()
        table = self.first(t).tables.get()
        result = self.race([lambda: self.confirm(table), lambda: finish(t.pk, self.admin, [{'table_id': table.pk, 'version': 1}])])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy', 'results_incomplete'}, result)
        if not TableResult.objects.filter(table=table, status='confirmed').exists():
            self.confirm(table)
        t.refresh_from_db()
        if t.status == 'started':
            finish(t.pk, self.admin, source_versions(t))
        self.assertFalse(Reservation.objects.filter(status='active').exists())

    def test_replacement_competes_with_selection(self):
        a, b = self.tournament(), self.tournament()
        self.first(a)
        target = self.machines[5].pk
        result = self.race([lambda: replace_machine(a.pk, 1, self.admin, target, '真实故障'), lambda: self.first(b, [target])])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy'}, result)
        if not Reservation.objects.filter(table__tournament=a, status='active', machine_id=target).exists():
            replace_machine(a.pk, 1, self.admin, target, '真实故障')
        if not b.rounds.exists(): self.first(b, [target])
        self.assertEqual(Reservation.objects.filter(status='active', machine_id=target).count(), 2)

    def test_finish_competes_with_reuse(self):
        a, b = self.tournament(), self.tournament()
        self.confirm(self.first(a).tables.get())
        versions = source_versions(a)
        result = self.race([lambda: finish(a.pk, self.admin, versions), lambda: self.first(b)])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy', 'machine_occupied'}, result)
        a.refresh_from_db()
        if a.status == 'started':
            finish(a.pk, self.admin, versions)
        self.assertFalse(Reservation.objects.filter(table__tournament=a, status='active').exists())
        if b.rounds.exists():
            self.assertEqual(Reservation.objects.filter(table__tournament=b, status='active').count(), 1)
