"""Generate ephemeral browser fixtures ONLY in the already isolated QA project."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
from qa_support import load_qa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_qa(args.env_file, root)
    output = Path(args.output).resolve()
    assert output.is_relative_to(root / '.verification') and not output.exists()
    credentials = {'username': 'pwqa_' + secrets.token_hex(5), 'password': secrets.token_urlsafe(32), 'prefix': 'PWQA ' + secrets.token_hex(3)}
    code = '''
import json, sys, django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from players.services import create_player
from machines.models import MahjongMachine
assert settings.DATABASES['default']['NAME'] == 'riichi_qa'
v=json.load(sys.stdin)
admin=get_user_model().objects.create_superuser(username=v['username'],password=v['password'])
players=[create_player(nickname=f"{v['prefix']} {i+1:02}") for i in range(16)]
for i in range(4): MahjongMachine.objects.create(machine_no=str(800+i),name=f"{v['prefix']} 桌{i+1}",status='available')
from tournaments.models import Tournament
from tournaments.services import create_tournament, mutate_tournament
# Compatibility fixtures represent strategies saved before 0010. The new
# creation endpoint must reject them; the existing-event browser flow remains.
existing={}
for strategy in ('swiss_repeats_first_v1','swiss_scores_first_v1'):
    row=create_tournament(admin,{'name':f"{v['prefix']} existing {strategy}",'round_count':2,'participant_ids':[p.pk for p in players[:8]]})
    Tournament.objects.filter(pk=row.pk).update(pairing_strategy=strategy)
    mutate_tournament(row.pk,start=True)
    existing[strategy]=row.pk
sys.stdout.write(json.dumps({'existing_swiss_ids':existing}))
'''
    command = ['docker', 'compose', '--env-file', args.env_file, '-f', str(root / 'deploy/compose.yaml'), 'exec', '-T', 'api', 'python', '-c', code]
    seeded = subprocess.run(command, input=json.dumps(credentials), text=True, check=True, capture_output=True)
    credentials.update(json.loads(seeded.stdout))
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        os.chmod(output, 0o600)
        json.dump(credentials, stream)
    print('Isolated browser QA fixtures prepared; credentials remain in ignored private storage.')


if __name__ == '__main__':
    main()
