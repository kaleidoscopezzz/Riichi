"""Delegate password entry to Django; never accept a password on argv/env."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = '交互初始化本地admin超级管理员；已有普通/停用账号时拒绝提升或重置。'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default', choices=connections)

    def handle(self, *args, **options):
        alias = options['database']
        user = get_user_model().objects.using(alias).filter(username='admin').first()
        self.stdout.write(f'目标数据库别名：{alias}。请先确认当前DATABASE_URL和备份。')
        if user and not (user.is_active and user.is_staff and user.is_superuser):
            raise CommandError('admin已存在但不是有效超级管理员，已拒绝重置或提权；请Owner人工核对账号归属。')
        if user:
            self.stdout.write('已找到有效admin超级管理员，将通过Django交互修改密码。')
            call_command('changepassword', 'admin', database=alias, stdout=self.stdout, stderr=self.stderr)
        else:
            self.stdout.write('admin不存在，将通过Django交互创建；并发重名时Django会拒绝覆盖。')
            call_command('createsuperuser', username='admin', database=alias, interactive=True, stdout=self.stdout, stderr=self.stderr)
