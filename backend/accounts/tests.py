from unittest.mock import patch
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from players.models import PlayerProfile
from players.services import create_player, PlayerConflict
from .serializers import RegisterSerializer

User=get_user_model()

class AccountFlowTests(TestCase):
 def setUp(self):
  self.client=Client(enforce_csrf_checks=True)
  self.token=self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
  self.payload=dict(username='test_admin',nickname='测试管理员',password='Test-Only!39xM',password_confirm='Test-Only!39xM')

 def write(self,path,data,method='post',token=None):
  return getattr(self.client,method)('/api/v1/'+path,data,content_type='application/json',HTTP_X_CSRFTOKEN=token or self.token)

 def sign_in(self):
  User.objects.get_or_create(username=self.payload['username'],defaults={'is_staff':True})
  u=User.objects.get(username=self.payload['username']);u.set_password(self.payload['password']);u.save()
  result=self.write('auth/login/',{'username':u.username,'password':self.payload['password']})
  self.token=self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
  return result

 def test_public_registration_closed_no_hash_or_profile_created(self):
  for body in [self.payload,{},[],'bad',self.payload|{'is_staff':True}]:
   response=self.write('auth/register/',body)
   self.assertEqual(response.status_code,403)
  self.assertFalse(User.objects.exists());self.assertFalse(PlayerProfile.objects.exists())

 def test_duplicate_username_registration_still_closed(self):
  User.objects.create_user(username='test_admin')
  self.assertEqual(self.write('auth/register/',self.payload).status_code,403)
  self.assertEqual(User.objects.count(),1)

 def test_password_validation_and_confirmation_retained(self):
  # Former registration validation remains regression-tested; endpoint is closed.
  for values in [{'password_confirm':'different'},{'password':'12345678','password_confirm':'12345678'},{'password':'short','password_confirm':'short'}]:
   self.assertFalse(RegisterSerializer(data=self.payload|values).is_valid())

 def test_display_name_rejects_invisible_and_bidi_text(self):
  for nick in ['\u200b','\u202e管理员','管\x07理','\u2066\u2069']:
   serializer=RegisterSerializer(data=self.payload|{'nickname':nick})
   self.assertFalse(serializer.is_valid());self.assertIn('nickname',serializer.errors)
  self.assertTrue(RegisterSerializer(data=self.payload|{'nickname':'老板\U0001f004'}).is_valid())

 def test_strict_privilege_injection_cannot_register(self):
  for f in ['is_staff','is_superuser','is_active','id','groups']:
   self.assertEqual(self.write('auth/register/',self.payload|{f:True}).status_code,403)
  self.assertFalse(User.objects.exists())

 def test_managed_player_creation_atomic_on_profile_failure(self):
  with patch('players.signals.PlayerProfile.objects.create',side_effect=IntegrityError),self.assertRaises(PlayerConflict):
   create_player('事务回滚')
  self.assertFalse(User.objects.exists());self.assertFalse(PlayerProfile.objects.exists())

 def test_profile_unique_constraint(self):
  u=User.objects.create_user(username='profile_owner')
  with self.assertRaises(IntegrityError),transaction.atomic():PlayerProfile.objects.create(user=u,nickname='重复')

 def test_admin_login_restore_hash_and_logout(self):
  self.assertEqual(self.sign_in().status_code,200)
  u=User.objects.get();self.assertTrue(u.check_password(self.payload['password']));self.assertNotEqual(u.password,self.payload['password'])
  self.assertEqual(self.client.get('/api/v1/auth/me/').status_code,200)
  restored=Client(enforce_csrf_checks=True);restored.cookies=self.client.cookies.copy()
  self.assertEqual(restored.get('/api/v1/auth/me/').status_code,200)
  self.assertEqual(self.write('auth/logout/',{}).status_code,200)
  self.assertEqual(restored.get('/api/v1/auth/me/').status_code,403)

 def test_login_failure_inactive_and_nonstaff(self):
  self.sign_in();u=User.objects.get()
  self.assertEqual(self.write('auth/login/',{'username':u.username,'password':'wrong'}).status_code,400)
  u.is_active=False;u.save()
  self.assertEqual(self.write('auth/login/',{'username':u.username,'password':self.payload['password']}).status_code,400)
  u.is_active=True;u.is_staff=False;u.save()
  # Formerly 403 admin_required, which revealed a correct password; now identical to a wrong password.
  wrong=self.write('auth/login/',{'username':u.username,'password':'wrong'})
  correct=self.write('auth/login/',{'username':u.username,'password':self.payload['password']})
  self.assertEqual(correct.status_code,400);self.assertEqual(correct.json(),wrong.json())
  self.assertEqual(correct.json()['error'],{'code':'invalid_credentials','message':'用户名或密码错误，或账号不可用。','fields':{}})
  self.assertEqual(self.client.get('/api/v1/auth/me/').status_code,403)

 def test_anonymous_denied_health_public(self):
  for path in ['auth/me/','players/me/','players/']:
   self.assertEqual(self.client.get('/api/v1/'+path).status_code,403)
  self.assertEqual(self.client.get('/api/v1/health/').status_code,200)

 def test_anonymous_csrf_required_registration_and_login(self):
  for path in ['register','login']:
   for headers in [{},{'HTTP_X_CSRFTOKEN':'invalid'}]:
    result=self.client.post(f'/api/v1/auth/{path}/',self.payload,content_type='application/json',**headers)
    self.assertEqual(result.status_code,403);self.assertEqual(result.json()['error']['code'],'csrf_failed')

 def test_admin_writes_csrf_and_trusted_origin(self):
  self.sign_in()
  for path,method,payload in [('auth/logout/','post',{}),('players/me/','patch',{'nickname':'新名称'})]:
   self.assertEqual(getattr(self.client,method)('/api/v1/'+path,payload,content_type='application/json').status_code,403)
   self.assertEqual(self.write(path,payload,method,token='invalid').status_code,403)
  self.assertEqual(self.client.patch('/api/v1/players/me/',{'nickname':'危险'},content_type='application/json',HTTP_X_CSRFTOKEN=self.token,HTTP_ORIGIN='https://untrusted.example').status_code,403)

 def test_admin_account_profile_cannot_change_identity(self):
  self.sign_in();other=create_player('普通选手')
  self.assertEqual(self.write('players/me/',{'nickname':'老板名称'},'patch').status_code,200)
  self.assertEqual(self.write('players/me/',{'nickname':'试图改人','user':other.user_id},'patch').status_code,400)
  for value in ['', ' '*4, '长'*81]:self.assertEqual(self.write('players/me/',{'nickname':value},'patch').status_code,400)

 def test_admin_list_excludes_account_and_does_not_expose_usernames(self):
  self.sign_in()
  for i in range(21):create_player(f'选手{i}')
  data=self.client.get('/api/v1/players/').json()['data']
  self.assertEqual(data['count'],21);self.assertEqual(len(data['results']),20);self.assertIsNotNone(data['next'])
  self.assertNotIn('username',data['results'][0]);self.assertNotIn('password',str(data))

 def test_input_methods_remain_strict(self):
  self.assertEqual(self.client.get('/api/v1/auth/login/').status_code,405)
  self.sign_in()
  self.assertEqual(self.write('auth/login/',{'username':'a','password':'b','is_staff':True}).status_code,400)
  self.assertEqual(self.client.get('/api/v1/missing/').json()['error']['code'],'not_found')

 def test_init_admin_safe_interactive_delegation(self):
  output=StringIO()
  with patch('accounts.management.commands.init_admin.call_command') as delegate:
   call_command('init_admin',stdout=output)
   self.assertEqual(delegate.call_args.args,('createsuperuser',));self.assertTrue(delegate.call_args.kwargs['interactive'])
  ordinary=User.objects.create_user(username='admin')
  with self.assertRaises(CommandError),patch('accounts.management.commands.init_admin.call_command') as delegate:
   call_command('init_admin',stdout=output)
  delegate.assert_not_called();ordinary.refresh_from_db();self.assertFalse(ordinary.is_staff)
  ordinary.is_staff=ordinary.is_superuser=True;ordinary.save()
  with patch('accounts.management.commands.init_admin.call_command') as delegate:
   call_command('init_admin',stdout=output)
   self.assertEqual(delegate.call_args.args,('changepassword','admin'))
