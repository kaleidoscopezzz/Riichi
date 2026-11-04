"""Create a local-only QA admin, players and machines. Credentials stay ignored."""
import json
import os
import secrets
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.local')
import django
django.setup()
from django.db import connection
from accounts.models import User
from machines.services import create_machine


def main():
    root=Path(__file__).resolve().parents[1]/'.verification'/'f0-06'
    if not Path(connection.settings_dict['NAME']).resolve().is_relative_to(root.resolve()):
        raise RuntimeError('Only isolated F0-06 QA database allowed')
    password=secrets.token_urlsafe(24)
    admin=User.objects.create_superuser(username='f006_qa_admin',password=password)
    for i in range(16):
        user=User.objects.create_user(username=f'f006_player{i+1:02}')
        user.player_profile.nickname=f'验收选手{i+1:02}'
        user.player_profile.save()
    for i in range(7):create_machine({'machine_no':f'{i+1:03}','name':f'验收物理桌{i+1}'})
    (root/'credentials.json').write_text(json.dumps({'username':admin.username,'password':password}),encoding='utf8')
    print('PASS: isolated QA seeded, 16 registered players, 7 machines. Credentials saved only in ignored path.')


if __name__=='__main__':main()
