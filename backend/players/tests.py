from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, Client
from rest_framework.exceptions import ValidationError
from tournaments.services import create_tournament, mutate_tournament
from tournaments.models import TournamentParticipant
from .models import PlayerProfile
from .services import create_player, mutate_player, PlayerConflict


class ManagedPlayerTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username='qa_staff')
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']

    def write(self, path='', body=None, method='post'):
        return getattr(self.client, method)('/api/v1/players/' + path, body if body is not None else {}, content_type='application/json', HTTP_X_CSRFTOKEN=self.token)

    def test_create_internal_unusable_nonprivileged_and_strict(self):
        response = self.write(body={'nickname': '小明'})
        self.assertEqual(response.status_code, 201)
        profile = PlayerProfile.objects.get(pk=response.json()['data']['id'])
        user = profile.user
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.username.startswith('player_'))
        self.assertNotIn('username', response.json()['data'])
        for field in ['username', 'password', 'is_active', 'user', 'is_staff', 'is_superuser', 'id']:
            self.assertEqual(self.write(body={'nickname': '越权', field: True}).status_code, 400)
        for nick in ['', ' ' * 3, '超' * 81]:
            self.assertEqual(self.write(body={'nickname': nick}).status_code, 400)
        self.assertEqual(self.write(body=[]).status_code, 400)

    def test_list_search_pagination_and_status(self):
        for i in range(22):
            create_player(f'姓名{i}')
        p = create_player('归档人员')
        mutate_player(p.pk, action='archive')
        data = self.client.get('/api/v1/players/').json()['data']
        self.assertEqual(data['count'], 23)
        self.assertEqual(len(data['results']), 20)
        self.assertTrue(data['next'])
        self.assertEqual(self.client.get('/api/v1/players/?status=archived').json()['data']['count'], 1)
        self.assertEqual(self.client.get('/api/v1/players/?eligible=true').json()['data']['count'], 22)
        self.assertEqual(self.client.get('/api/v1/players/?search=归档人员').json()['data']['count'], 1)
        self.assertEqual(self.client.get('/api/v1/players/?status=bad').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/players/?page=999').status_code, 404)

    def test_edit_archive_restore_and_detail(self):
        p = create_player('旧名')
        self.assertEqual(self.write(f'{p.pk}/', {'nickname': '新名'}, 'patch').status_code, 200)
        self.assertEqual(self.client.get(f'/api/v1/players/{p.pk}/').json()['data']['nickname'], '新名')
        self.assertEqual(self.write(f'{p.pk}/archive/', {'confirmed': True}).status_code, 200)
        self.assertEqual(self.write(f'{p.pk}/archive/', {'confirmed': True}).status_code, 409)
        self.assertEqual(self.write(f'{p.pk}/restore/', {'confirmed': True}).status_code, 200)
        p.user.refresh_from_db()
        self.assertTrue(p.user.is_active)

    def test_unreferenced_delete_profile_preserves_identity_audits(self):
        p = create_player('无引用')
        uid, pk = p.user_id, p.pk
        self.assertEqual(self.write(f'{pk}/', {}, 'delete').status_code, 400)
        self.assertEqual(self.write(f'{pk}/', {'confirmed': True}, 'delete').status_code, 200)
        self.assertFalse(PlayerProfile.objects.filter(pk=pk).exists())
        user = get_user_model().objects.get(pk=uid)
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.client.get(f'/api/v1/players/{pk}/').status_code, 404)

    def test_draft_reference_blocks_delete_and_archived_cannot_start(self):
        profiles = [create_player(f'选手{i}') for i in range(4)]
        t = create_tournament(self.admin, {'name': '草稿', 'round_count': 1, 'participant_ids': [p.pk for p in profiles]})
        p = profiles[0]
        self.assertEqual(self.write(f'{p.pk}/', {'confirmed': True}, 'delete').json()['error']['code'], 'player_referenced')
        self.write(f'{p.pk}/archive/', {'confirmed': True})
        with self.assertRaises(ValidationError):
            mutate_tournament(t.pk, start=True)
        self.assertEqual(t.participants.count(), 4)

    def test_started_snapshot_preserved_after_edit_archive(self):
        profiles = [create_player(f'快照{i}') for i in range(4)]
        t = create_tournament(self.admin, {'name': '冻结档案', 'round_count': 1, 'participant_ids': [p.pk for p in profiles]})
        mutate_tournament(t.pk, start=True)
        before = list(TournamentParticipant.objects.filter(tournament=t).values('id', 'player_id', 'display_name_snapshot'))
        mutate_player(profiles[0].pk, nickname='新昵称')
        mutate_player(profiles[0].pk, action='archive')
        self.assertEqual(list(TournamentParticipant.objects.filter(tournament=t).values('id', 'player_id', 'display_name_snapshot')), before)
        self.assertFalse(self.client.get(f'/api/v1/players/{profiles[0].pk}/').json()['data']['can_delete'])

    def test_archived_or_admin_cannot_enter_new_tournament(self):
        p = create_player('停用')
        mutate_player(p.pk, action='archive')
        for pk in [p.pk, self.admin.player_profile.pk]:
            with self.assertRaises(ValidationError):
                create_tournament(self.admin, {'name': '拒绝', 'round_count': 1, 'participant_ids': [pk]})

    def test_admin_own_profile_protected(self):
        pk = self.admin.player_profile.pk
        self.assertEqual(self.client.get(f'/api/v1/players/{pk}/').status_code, 404)
        for path, body, method in [(f'{pk}/', {'nickname': '误改'}, 'patch'), (f'{pk}/archive/', {'confirmed': True}, 'post'), (f'{pk}/', {'confirmed': True}, 'delete')]:
            self.assertEqual(self.write(path, body, method).status_code, 409)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_permissions_csrf_and_confirmation(self):
        p = create_player('被保护')
        operations = [('post', '', {'nickname': '禁止'}), ('patch', f'{p.pk}/', {'nickname': '禁止'}), ('delete', f'{p.pk}/', {'confirmed': True}), ('post', f'{p.pk}/archive/', {'confirmed': True}), ('post', f'{p.pk}/restore/', {'confirmed': True})]
        for user in [None, p.user]:
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            token = client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
            for method, path, body in operations:
                self.assertEqual(getattr(client, method)('/api/v1/players/' + path, body, content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 403)
            for path in ['', f'{p.pk}/', 'me/']:
                self.assertEqual(client.get('/api/v1/players/' + path).status_code, 403)
        for method, path, body in operations:
            for headers in [{}, {'HTTP_X_CSRFTOKEN': 'invalid'}]:
                self.assertEqual(getattr(self.client, method)('/api/v1/players/' + path, body, content_type='application/json', **headers).status_code, 403)
        for body in [{}, {'confirmed': False}, {'confirmed': True, 'is_staff': True}]:
            self.assertEqual(self.write(f'{p.pk}/archive/', body).status_code, 400)

    def test_creation_failure_atomic(self):
        count = get_user_model().objects.count()
        with patch('players.signals.PlayerProfile.objects.create', side_effect=IntegrityError), self.assertRaises(PlayerConflict):
            create_player('注入失败')
        self.assertEqual(get_user_model().objects.count(), count)

    def test_invisible_or_control_nicknames_rejected(self):
        p = create_player('可见名称')
        invisible = ['\u200b', '\u200b\u200c\u200d', '\u2060\ufeff', '\u202e', '\u202eabc', 'ab\u200fc', '\u2066名\u2069', 'a\x00b', 'a\x07b', '\x1b[31m红', 'a\u0085b', '\u00ad']
        for nick in invisible:
            with self.subTest(nick=ascii(nick)):
                for path, method in [('', 'post'), (f'{p.pk}/', 'patch'), ('me/', 'patch')]:
                    response = self.write(path, {'nickname': nick}, method)
                    self.assertEqual(response.status_code, 400, (path, response.content))
                    self.assertIn('nickname', response.json()['error']['fields'])
        self.assertIn(self.write(body={'nickname': '\u202eabc'}).json()['error']['fields']['nickname'][0], ['名称不能包含控制字符或文字方向控制符。'])
        self.assertEqual(self.write(body={'nickname': '\u200b'}).json()['error']['fields']['nickname'], ['名称至少需要包含一个可见的文字、数字、标点或符号。'])
        for nick in ['\U0001f468\u200d\U0001f469\u200d\U0001f467', '❤\ufe0f', '张三', 'A-1', '★', '07', '「雀」', 'é\u0301', '超' * 80]:
            with self.subTest(nick=ascii(nick)):
                response = self.write(body={'nickname': nick})
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()['data']['nickname'], nick)
        self.assertEqual(self.write('me/', {'nickname': '\U0001f004 雀庄老板'}, 'patch').status_code, 200)
        self.assertEqual(self.write(body={'nickname': '超' * 81}).status_code, 400)

    def test_search_with_control_characters_is_400(self):
        create_player('搜索目标')
        for base in ['/api/v1/players/', '/api/v1/machines/', '/api/v1/tournaments/']:
            for value in ['%00', 'a%00b', '%07', '%1B', '%7F', '%C2%85']:
                with self.subTest(base=base, value=value):
                    response = self.client.get(f'{base}?search={value}')
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()['error']['fields'], {'search': ['搜索内容包含无效字符。']})
            self.assertEqual(self.client.get(base + '?search=%E6%90%9C%E7%B4%A2').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/players/?search=%20%E6%90%9C%E7%B4%A2%20').json()['data']['count'], 1)

    def test_admin_without_profile_gets_lazy_signal_profile(self):
        admin = get_user_model().objects.create_user(username='legacy_owner_' + 'x' * 80, is_staff=True)
        PlayerProfile.objects.filter(user=admin).delete()
        client = Client(enforce_csrf_checks=True); client.force_login(admin)
        token = client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
        response = client.get('/api/v1/players/me/')
        self.assertEqual(response.status_code, 200, response.content)
        profile = PlayerProfile.objects.get(user=admin)
        self.assertEqual((response.json()['data']['id'], response.json()['data']['nickname']), (profile.pk, admin.username[:80]))
        self.assertEqual(client.get('/api/v1/players/me/').json()['data']['id'], profile.pk)
        self.assertEqual(PlayerProfile.objects.filter(user=admin).count(), 1)
        PlayerProfile.objects.filter(user=admin).delete()
        response = client.patch('/api/v1/players/me/', {'nickname': '补建后的老板'}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual((response.status_code, response.json()['data']['nickname']), (200, '补建后的老板'))
        self.assertEqual(PlayerProfile.objects.get(user=admin).nickname, '补建后的老板')
        # The repaired administrator profile still stays out of player lists and CRUD.
        self.assertNotIn(PlayerProfile.objects.get(user=admin).pk, [p['id'] for p in self.client.get('/api/v1/players/').json()['data']['results']])
