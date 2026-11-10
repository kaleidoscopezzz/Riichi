"""Populated historical migration rehearsal on an EMPTY riichi_qa_legacy PostgreSQL.

Uses the same retained historical cases as migration_check.py, with portable
column introspection. Never touches Owner data or changes migration sources.
"""
import hashlib
import json
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from verification.review_migration_check import BEFORE_REVIEW, rehearse_review_migrations, require_empty_qa_postgres


def main():
    require_empty_qa_postgres(connection)
    old_targets = [('tournaments','0002_tournamentround_roundtable_roundseat_and_more'),('machines','0002_mahjongmachine_machine_number_digits_only')]
    executor = MigrationExecutor(connection)
    executor.migrate(old_targets)
    apps = executor.loader.project_state(old_targets).apps
    U=apps.get_model('accounts','User'); P=apps.get_model('players','PlayerProfile')
    T=apps.get_model('tournaments','Tournament'); E=apps.get_model('tournaments','TournamentParticipant')
    R=apps.get_model('tournaments','TournamentRound'); Table=apps.get_model('tournaments','RoundTable'); Seat=apps.get_model('tournaments','RoundSeat'); A=apps.get_model('tournaments','MachineAllocation'); M=apps.get_model('machines','MahjongMachine')
    admin=U.objects.create(username='migration_qa_admin',is_staff=True)
    profiles=[P.objects.create(user=U.objects.create(username=f'migration_player{i}'),nickname=f'迁移选手{i}') for i in range(16)]
    machines=[M.objects.create(machine_no=f'{i+1:03}',name=f'旧物理桌{i+1}',capacity_slot=i+1) for i in range(4)]
    retired=M.objects.create(machine_no='004',name='更早退役设备',status='retired')
    cases={}
    for kind,n in [('F0-04_started',4),('F0-05_valid',8),('F0-05_partial',8),('F0-05_released',4)]:
        t=T.objects.create(name=kind,round_count=1 if kind.endswith('released') else 2,created_by=admin,status='started',started_at=timezone.now(),uma=['30.12345678901234567890123456789','10','-10','-30'])
        entries=[E.objects.create(tournament=t,player=p,display_name_snapshot=p.nickname) for p in profiles[:n]]
        cases[kind]=t.pk
        if kind=='F0-04_started':continue
        r=R.objects.create(tournament=t,round_number=1,generated_by=admin)
        for i in range(n//4):
            table=Table.objects.create(round=r,table_number=i+1)
            for w,p in zip(['east','south','west','north'],entries[i*4:i*4+4]):Seat.objects.create(round=r,table=table,participant=p,seat_wind=w)
            m=machines[i] if kind.endswith('valid') else machines[2+i] if kind.endswith('partial') else machines[3]
            released=kind.endswith('released') or (kind.endswith('partial') and i==1)
            A.objects.create(table=table,machine=m,machine_no_snapshot=m.machine_no,allocated_by=admin,status='released' if released else 'active',released_by=admin if released else None,released_at=timezone.now() if released else None,release_reason='旧版真实释放' if released else '')

    # Seed original identities before taking the 0002 projection. The review
    # rehearsal adds only records in tables introduced by 0003 afterwards.
    review_tournament=T.objects.create(name='PR2迁移专用QA',round_count=1,created_by=admin,status='started',started_at=timezone.now())
    review_members=[E.objects.create(tournament=review_tournament,player=p,display_name_snapshot=p.nickname).pk for p in profiles[:4]]

    tables=['machines_mahjongmachine','tournaments_tournament','tournaments_tournamentparticipant','tournaments_tournamentround','tournaments_roundtable','tournaments_roundseat','tournaments_machineallocation']
    columns={}; before={}
    with connection.cursor() as c:
        for table in tables:
            columns[table]=[col.name for col in connection.introspection.get_table_description(c, table)]
            c.execute(f'SELECT {",".join(columns[table])} FROM {table} ORDER BY id')
            before[table]=c.fetchall()
    executor=MigrationExecutor(connection);executor.migrate(BEFORE_REVIEW)
    review=rehearse_review_migrations(connection,tournament_id=review_tournament.pk,admin_id=admin.pk,machine_id=machines[3].pk,members=review_members[:2])
    # Each historical helper stops at its own graph. Advance normally before
    # loading the current runtime models, including later personal/team fields.
    executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
    with connection.cursor() as c:
        for table in tables:
            c.execute(f'SELECT {",".join(columns[table])} FROM {table} ORDER BY id')
            assert c.fetchall()==before[table],table+' historical column drift'
    from tournaments.models import Tournament, TournamentMachineReservation
    from tournaments.competition_services import review_legacy, generate, occupied_ids
    from machines.services import create_machine
    from accounts.models import User
    admin=User.objects.get(pk=admin.pk)
    states={k:Tournament.objects.get(pk=pk).resource_state for k,pk in cases.items()}
    assert states=={'F0-04_started':'unselected','F0-05_valid':'fixed','F0-05_partial':'review_required','F0-05_released':'review_required'},states
    assert TournamentMachineReservation.objects.filter(status='active').count()==4
    extra=[create_machine({'machine_no':f'{i:03}','name':'新物理桌'}) for i in range(5,9)]
    generate(cases['F0-04_started'],admin,1,machine_ids=[extra[0].pk])
    review_legacy(cases['F0-05_released'],admin,historical_only=True,machine_ids=[],reason='无需后续实体对局')
    review_legacy(cases['F0-05_partial'],admin,historical_only=False,machine_ids=[machines[2].pk,extra[1].pk],reason='保留有效占用，明确补选空闲桌')
    # Event associations may share a machine; occupied_ids() now reports only
    # legacy active allocations, i.e. the three inherited active rows here.
    assert occupied_ids()=={machines[0].pk,machines[1].pk,machines[2].pk}, occupied_ids()
    print(json.dumps({'result':'PASS','states_after_migration':states,'historical_rows':{k:len(v) for k,v in before.items()},'all_original_columns_unchanged':True,'snapshot_sha256':hashlib.sha256(repr(before).encode()).hexdigest(),'new_machines_created':len(extra),'valid_inherited_reservations':3,'legacy_partial_and_released_review':'PASS','review_0005_0006':review},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
