import json
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.services import create_machine, change_machine, MachineConflict
from .models import Tournament, TournamentRound, RoundSeat, RoundTable, MachineAllocation, TableResult, TournamentMachineReservation as Reservation
from .services import create_tournament, mutate_tournament, TournamentConflict
from .competition_services import (generate, write_result, ranking, metric, source_versions, preview, record_lottery, confirm_lottery, finish, replace_machine, review_legacy, bridge_legacy, locked)
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

    def test_legacy_new_resource_pool_cannot_double_occupy(self):
        legacy = self.tournament()
        r = generate_first_round(legacy.pk, self.admin)
        allocation = r.tables.get().allocations.get()
        with self.assertRaises(TournamentConflict):
            self.first(self.tournament(), [allocation.machine_id])
        new = self.tournament()
        self.first(new, [self.machines[6].pk])
        with self.assertRaises(TournamentConflict):
            change_allocation(r.tables.get().pk, self.admin, machine_id=self.machines[6].pk)

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

    def test_fixed_resource_mutual_exclusion_and_old_release_guard(self):
        t=self.tournament(); table=self.first(t).tables.get()
        with self.assertRaises(TournamentConflict): self.first(self.tournament())
        with self.assertRaises(MachineConflict): change_machine(self.machines[0].pk,retire=True)
        with self.assertRaises(TournamentConflict): change_allocation(table.pk,self.admin)
        before=table.machine_snapshot
        replace_machine(t.pk,1,self.admin,self.machines[5].pk,'物理故障')
        table.refresh_from_db(); self.assertEqual(table.machine_snapshot,before)
        self.assertEqual(Reservation.objects.filter(table__tournament=t,status='active').get().machine_id,self.machines[5].pk)
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
        with self.assertRaises(TournamentConflict): review_legacy(t.pk,self.admin,historical_only=False,machine_ids=[self.machines[0].pk],reason='不可抢占')
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


class CompetitionApiTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data();self.t=self.tournament();self.table=self.first(self.t).tables.get()
        self.client=Client(enforce_csrf_checks=True);self.client.force_login(self.admin)
        self.token=self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']

    def test_permissions_csrf_all_new_writes(self):
        paths=[f'tournaments/{self.t.pk}/workspace/',f'tournaments/{self.t.pk}/tables/replace/',f'tournaments/{self.t.pk}/compatibility-review/',f'tournaments/{self.t.pk}/lotteries/',f'tournaments/{self.t.pk}/lotteries/1/confirm/',f'tournaments/{self.t.pk}/complete/',f'round-tables/{self.table.pk}/result/',f'round-tables/{self.table.pk}/result/confirm/']
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
        self.assertEqual(result.count('ok'),1,result);self.assertEqual(Reservation.objects.filter(status='active').count(),1)

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
        if active:self.assertEqual(active.machine.status,'available')

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
        self.assertEqual(result.count('ok'), 1, result)
        self.assertEqual(Reservation.objects.filter(status='active', machine_id=target).count(), 1)

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
