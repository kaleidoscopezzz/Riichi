"""Guarded Linux deployment orchestration. Secrets stay in Compose's environment.

prepare only reads the already-running database; apply requires that exact plan.
It never creates administrators, imports local SQLite, or deletes a database/volume.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'deploy'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_json(path, value, exclusive=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


class Deployment:
    def __init__(self, qa=False, sha=None):
        self.env_file = Path(os.environ.get('RIICHI_ENV_FILE', DEPLOY / '.env')).resolve()
        if not self.env_file.is_file():
            raise RuntimeError('Missing ignored deployment environment file.')
        self.qa = qa
        self.environment = {**os.environ}
        if sha:
            self.environment['RIICHI_VERSION'] = sha
        self.compose = ['docker', 'compose', '--env-file', str(self.env_file), '-f', str(DEPLOY / 'compose.yaml')]
        self.config = json.loads(self.run(self.compose + ['config', '--format', 'json']))
        self.project = self.config['name']
        self.db = self.config['services']['db']['environment']['POSTGRES_DB']
        self.server = self.config['services']['nginx']['environment']['SERVER_NAME']
        if not re.fullmatch(r'[a-z_][a-z0-9_]{0,51}', self.db):
            raise RuntimeError('Automatic restore needs a lowercase DB identifier of at most 52 characters.')
        if qa:
            if self.db != 'riichi_qa' or not self.project.startswith('riichi-docker-qa') or self.server != 'localhost':
                raise RuntimeError('QA mode requires the isolated loopback riichi_qa project.')
        elif self.db.startswith('riichi_qa') or self.server in ('localhost', 'riichi.example', 'example.com'):
            raise RuntimeError('Production requires a real target; QA mode is separate.')
        self.identity_secrets = [str(value) for service in self.config['services'].values()
                                 for key, value in service.get('environment', {}).items()
                                 if ('PASSWORD' in key or 'SECRET_KEY' in key) and value]

    def run(self, command, *, input=None, output=None):
        result = subprocess.run(command, cwd=ROOT, env=self.environment, input=input,
                                text=True, encoding='utf-8', errors='replace', capture_output=True)
        if output:
            text = result.stdout + result.stderr
            for secret in getattr(self, 'identity_secrets', []):
                text = text.replace(secret, '[REDACTED]')
            Path(output).write_text(text, encoding='utf-8')
            os.chmod(output, 0o600)
        if result.returncode:
            # Docker stderr can include environment interpolation values; never echo it.
            raise RuntimeError(f'{Path(command[0]).name} failed (exit {result.returncode}); inspect private logs or service status.')
        return result.stdout

    def dc(self, *arguments, **kwargs):
        return self.run(self.compose + list(arguments), **kwargs)

    def api(self, *arguments, database=None, directory=None, output=None):
        options = ['run', '--rm', '--no-deps', '-T']
        if database:
            options += ['-e', 'POSTGRES_DB=' + database]
        if directory:
            options += ['--volume', str(Path(directory).resolve()) + ':/release:ro']
        return self.dc(*options, 'api', *arguments, output=output)

    def target(self):
        container = self.dc('ps', '-q', 'db').strip()
        if not container:
            raise RuntimeError('Start the explicitly identified database service first; no automatic volume selection.')
        info = json.loads(self.run(['docker', 'inspect', container]))[0]
        labels = info['Config']['Labels']
        if labels.get('com.docker.compose.project') != self.project:
            raise RuntimeError('Database project mismatch.')
        mounts = [m for m in info['Mounts'] if m['Destination'] == '/var/lib/postgresql/data']
        if (len(mounts) != 1 or mounts[0]['Type'] != 'volume'
                or mounts[0]['Name'] != self.config['volumes']['postgres_data']['name']):
            raise RuntimeError('Expected the inventoried PostgreSQL named volume.')
        actual = self.dc('exec', '-T', 'db', 'sh', '-eu', '-c',
                         'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "SELECT current_database(), oid, system_identifier FROM pg_database CROSS JOIN pg_control_system() WHERE datname=current_database()"')
        name, oid, cluster = actual.strip().split('|')
        if name != self.db:
            raise RuntimeError('Actual database identity differs from the selected target.')
        return {'project': self.project, 'database': name, 'oid': oid, 'cluster': cluster, 'volume': mounts[0]['Name']}

    def migration_plan(self):
        return self.api('python', 'manage.py', 'migrate', '--plan')

    def image_id(self, reference):
        return self.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', reference]).strip()

    def candidate_images(self):
        return {name: self.image_id(self.config['services'][name]['image']) for name in ('api', 'nginx')}

    def live_images(self):
        images = {}
        for name in ('api', 'nginx'):
            identifier = self.dc('ps', '-q', name).strip()
            if identifier:
                images[name] = self.run(['docker', 'inspect', '--format', '{{.Image}}', identifier]).strip()
        return images

    def schema(self):
        return json.loads(self.api('python', '-m', 'verification.schema_manifest'))

    def published_port_checks(self):
        owned = set()
        identifiers = self.run(['docker', 'ps', '-q']).split()
        for identifier in identifiers:
            text = self.run(['docker', 'inspect', '--format', '{"labels":{{json .Config.Labels}},"ports":{{json .NetworkSettings.Ports}}}', identifier])
            info = json.loads(text)
            labels = info['labels'] or {}
            if labels.get('com.docker.compose.project') == self.project and labels.get('com.docker.compose.service') in ('caddy', 'nginx'):
                for bindings in (info['ports'] or {}).values():
                    for binding in bindings or []:
                        owned.add((binding['HostIp'], int(binding['HostPort'])))
        for port in self.config['services']['caddy'].get('ports', []):
            host, number = port.get('host_ip', '0.0.0.0'), int(port['published'])
            family = socket.AF_INET6 if ':' in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind((host, number))
                except OSError:
                    if (host, number) not in owned:
                        raise RuntimeError('A public port is unavailable or owned by another service; no process will be stopped.') from None

    def preflight(self):
        services = self.config['services']
        if set(services) != {'db', 'api', 'nginx', 'caddy'}:
            raise RuntimeError('Unexpected Compose service topology.')
        for name in ('db', 'api', 'nginx'):
            if services[name].get('ports'):
                raise RuntimeError('Only Caddy may publish host ports.')
        for name in ('proxy', 'web', 'data'):
            if not self.config['networks'][name].get('internal'):
                raise RuntimeError('Private networks must be internal.')
        if set(services['caddy']['networks']) != {'edge', 'proxy'} or set(services['nginx']['networks']) != {'proxy', 'web'}:
            raise RuntimeError('Ingress network isolation differs from the reviewed topology.')
        caddy_env = services['caddy']['environment']
        config_name = caddy_env.get('CADDY_CONFIG', 'Caddyfile')
        if not self.qa and (config_name != 'Caddyfile' or caddy_env.get('ACME_CA') != 'https://acme-v02.api.letsencrypt.org/directory'):
            raise RuntimeError('Production must use the reviewed public Let\'s Encrypt configuration.')
        if self.qa and config_name != 'Caddyfile.qa':
            raise RuntimeError('QA must use the isolated internal CA configuration.')
        public_ports = services['caddy'].get('ports', [])
        tcp = {int(p['published']) for p in public_ports if p.get('protocol', 'tcp') == 'tcp'}
        if (not self.qa and tcp != {80, 443}) or (self.qa and any(p.get('host_ip') != '127.0.0.1' for p in public_ports)):
            raise RuntimeError('Unexpected ingress port binding.')
        proxy = self.config['networks']['proxy']
        ipam = proxy['ipam']['config'][0]
        subnet = ipaddress.ip_network(ipam['subnet'])
        dynamic = ipaddress.ip_network(ipam['ip_range'])
        address = ipaddress.ip_address(services['caddy']['networks']['proxy']['ipv4_address'])
        if not dynamic.subnet_of(subnet) or address in dynamic or address not in subnet or address in (subnet.network_address, subnet.network_address + 1, subnet.broadcast_address):
            raise RuntimeError('Caddy proxy address does not belong to the configured network.')
        network_ids = self.run(['docker', 'network', 'ls', '-q']).split()
        if network_ids:
            for network in json.loads(self.run(['docker', 'network', 'inspect', *network_ids])):
                for item in network.get('IPAM', {}).get('Config', []):
                    if item.get('Subnet') and ipaddress.ip_network(item['Subnet']).version == subnet.version:
                        if subnet.overlaps(ipaddress.ip_network(item['Subnet'])) and network['Name'] != proxy['name']:
                            raise RuntimeError('Proxy subnet overlaps another existing Docker network.')
        target = self.target()
        self.published_port_checks()
        snapshot = self.schema()
        migration_names = {(row['app'], row['name']) for row in snapshot['migration_state']}
        has_business_rows = any(row['count'] for table, row in snapshot['tables'].items()
                                if table.startswith(('accounts_', 'players_', 'machines_', 'tournaments_')))
        if has_business_rows and ('tournaments', '0004_legacy_compatibility') not in migration_names:
            raise RuntimeError('Populated pre-0004 databases require a separate compatibility migration rehearsal; automatic release refused.')
        size = int(self.dc('exec', '-T', 'db', 'sh', '-eu', '-c',
                           'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "SELECT pg_database_size(current_database())"').strip())
        docker_root = self.run(['docker', 'info', '--format', '{{.DockerRootDir}}']).strip()
        free = shutil.disk_usage(docker_root).free
        # Space for original, verified restore, compressed dump, parallel images and reserve.
        if free < 4 * size + 2 * 1024**3:
            raise RuntimeError('Insufficient free disk space for backup, restored DB and images.')
        return {'result': 'PASS', 'target': target, 'database_bytes': size, 'docker_disk_free_bytes': free,
                'environment_sha256': sha256(self.env_file), 'config_sha256': canonical_hash(self.config), 'qa': self.qa,
                'public_entry': 'Caddy only', 'proxy_subnet': str(subnet),
                'external_ports_dns_tls': 'separate external verification required'}


def check_source(deployment, sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise RuntimeError('A full 40-character commit SHA is required.')
    head = deployment.run(['git', 'rev-parse', 'HEAD']).strip()
    if head != sha or deployment.run(['git', 'status', '--porcelain']).strip():
        raise RuntimeError('Deployment checkout must be clean at the exact selected commit.')
    if not deployment.qa and deployment.run(['git', 'rev-parse', 'refs/remotes/origin/main']).strip() != sha:
        raise RuntimeError('Production source must equal the verified remote main ref.')


def prepare(arguments):
    deployment = Deployment(arguments.qa, arguments.sha)
    check_source(deployment, arguments.sha)
    checks = deployment.preflight()
    plan = deployment.migration_plan()
    result = {'format': 1, 'sha': arguments.sha, 'qa': arguments.qa, 'target': checks['target'],
              'environment_sha256': checks['environment_sha256'], 'migration_plan_sha256': canonical_hash(plan),
              'config_sha256': checks['config_sha256'], 'candidate_images': deployment.candidate_images(),
              'migration_plan': plan, 'prepared_at': datetime.now(timezone.utc).isoformat()}
    write_json(arguments.output, result)
    print('Prepared target-bound release plan. No migration or administrator initialization performed.')


def project_lock(deployment):
    # Independent of operator home/evidence location. All invocations for a
    # project on the same Linux Docker host share the lock.
    return (Path('/run/lock') / ('riichi-release-' + deployment.project + '.lock')).open('a')


def apply(arguments):
    import fcntl  # Linux release host only; Windows never hosts production containers.
    manifest_path = Path(arguments.manifest).resolve()
    plan = json.loads(manifest_path.read_text(encoding='utf-8'))
    if plan.get('format') != 1 or plan.get('qa') is not arguments.qa:
        raise RuntimeError('Release plan format/mode mismatch.')
    prepared_at = datetime.fromisoformat(plan['prepared_at'])
    age = (datetime.now(timezone.utc) - prepared_at).total_seconds()
    if age < 0 or age > 86400:
        raise RuntimeError('Release plan expired; re-inspect before preparing a fresh plan.')
    deployment = Deployment(arguments.qa, plan['sha'])
    lock_dir = Path(os.environ.get('RIICHI_RELEASE_DIR', Path.home() / 'riichi-releases')).resolve()
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with project_lock(deployment) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = manifest_path.with_suffix('.receipt.json')
        if receipt_path.exists():
            raise RuntimeError('This release was already attempted; inspect its receipt and prepare a new plan.')
        check_source(deployment, plan['sha'])
        checks = deployment.preflight()
        if (checks['target'] != plan['target'] or checks['environment_sha256'] != plan['environment_sha256']
                or checks['config_sha256'] != plan['config_sha256'] or deployment.candidate_images() != plan['candidate_images']
                or canonical_hash(deployment.migration_plan()) != plan['migration_plan_sha256']):
            raise RuntimeError('Target, environment or migration plan drifted; no changes applied.')
        work = lock_dir / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4))
        work.mkdir(mode=0o700)
        projection = work / 'projection'
        projection.mkdir()
        projection.chmod(0o755)
        # Bind only non-secret schema evidence into the non-root API container.
        # Backups, credentials and private operation logs remain outside this mount.
        receipt = {'sha': plan['sha'], 'target': plan['target'], 'state': 'APPLYING', 'private_artifacts': str(work), 'qa': arguments.qa}
        receipt['environment_sha256'] = plan['environment_sha256']
        receipt['config_sha256'] = plan['config_sha256']
        receipt['candidate_images'] = plan['candidate_images']
        receipt['previous_images'] = {}
        for service in ('api', 'nginx'):
            identifier = deployment.dc('ps', '-q', service).strip()
            if identifier:
                image = deployment.run(['docker', 'inspect', '--format', '{{.Image}}', identifier]).strip()
                exposed = json.loads(deployment.run(['docker', 'image', 'inspect', '--format', '{{json .Config.ExposedPorts}}', image])) or {}
                if service == 'nginx' and '8443/tcp' in exposed:
                    receipt['previous_ingress'] = 'legacy TLS: restore inventoried old deployment bundle manually'
                tag = 'riichi-rollback-' + deployment.project + '-' + service + ':' + image.removeprefix('sha256:')[:16]
                deployment.run(['docker', 'tag', image, tag])
                receipt['previous_images'][service] = {'id': image, 'tag': tag}
        shutil.copyfile(deployment.env_file, work / 'environment.env')
        os.chmod(work / 'environment.env', 0o600)
        shutil.copytree(DEPLOY / 'caddy', work / 'caddy-config')
        shutil.copyfile(DEPLOY / 'compose.yaml', work / 'compose.yaml')
        write_json(receipt_path, receipt)
        try:
            caddy = deployment.dc('ps', '-q', 'caddy').strip()
            maintenance = 'Caddyfile.qa.maintenance' if arguments.qa else 'Caddyfile.maintenance'
            normal = 'Caddyfile.qa' if arguments.qa else 'Caddyfile'
            if caddy:
                deployment.dc('exec', '-T', 'caddy', 'caddy', 'reload', '--config', '/etc/caddy/' + maintenance, '--adapter', 'caddyfile', output=work / 'maintenance.log')
            deployment.dc('stop', 'nginx', 'api', output=work / 'stop-writers.log')
            # Recheck after draining writers. No other operator/management write may run.
            if deployment.target() != plan['target'] or canonical_hash(deployment.migration_plan()) != plan['migration_plan_sha256']:
                raise RuntimeError('Target/schema changed while draining writers.')
            backup_receipt = work / 'backup.json'
            deployment.run(['bash', str(DEPLOY / 'backup.sh'), '--receipt', str(backup_receipt)], output=work / 'backup.log')
            archive = json.loads(backup_receipt.read_text())
            if sha256(archive['archive']) != archive['sha256']:
                raise RuntimeError('Final backup checksum mismatch.')
            baseline = deployment.schema()
            (projection / 'before.json').write_text(json.dumps(baseline), encoding='utf-8')
            os.chmod(projection / 'before.json', 0o644)
            target = deployment.db + '_restore_' + secrets.token_hex(4)[:63-len(deployment.db)-9]
            deployment.run(['bash', str(DEPLOY / 'restore.sh'), archive['archive'], target],
                           input='RESTORE ' + target + '\n', output=work / 'restore.log')
            for stage in ('restored-before-migration', 'restored-after-migration'):
                if stage.endswith('after-migration'):
                    deployment.api('python', 'manage.py', 'migrate', '--noinput', database=target, output=work / 'rehearsal-migrate.log')
                deployment.api('python', '-m', 'verification.schema_manifest', '--compare', '/release/before.json', database=target, directory=projection, output=work / (stage + '.json'))
            deployment.api('python', '-m', 'verification.data_manifest', database=target, output=work / 'restored-current.json')
            if (sha256(archive['archive']) != archive['sha256'] or deployment.target() != plan['target']
                    or canonical_hash(deployment.migration_plan()) != plan['migration_plan_sha256']
                    or deployment.candidate_images() != plan['candidate_images']):
                raise RuntimeError('Final target/plan/backup changed; refusing production migration.')
            deployment.api('python', 'manage.py', 'migrate', '--noinput', output=work / 'migrate.log')
            deployment.api('python', 'manage.py', 'migrate', '--check', output=work / 'migration-check.log')
            upgraded = json.loads(deployment.api('python', '-m', 'verification.schema_manifest', '--compare', '/release/before.json', directory=projection, output=work / 'production-projection.json'))
            receipt['migration_state_sha256'] = canonical_hash(upgraded['migration_state'])
            receipt['schema_changed'] = baseline['migration_state'] != upgraded['migration_state']
            current = deployment.api('python', '-m', 'verification.data_manifest')
            if json.loads(current) != json.loads((work / 'restored-current.json').read_text()):
                raise RuntimeError('Migrated production differs from the verified rehearsal.')
            (work / 'production-current.json').write_text(current, encoding='utf-8')
            deployment.api('python', 'manage.py', 'check', '--deploy', output=work / 'deploy-check.log')
            for service in ('api', 'nginx'):
                deployment.dc('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', service, output=work / (service + '-start.log'))
            if deployment.live_images() != plan['candidate_images'] or deployment.target() != plan['target']:
                raise RuntimeError('Running images or database do not match the reviewed candidate and target.')
            if not caddy:
                deployment.dc('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', 'caddy', output=work / 'start-ingress.log')
            deployment.dc('exec', '-T', 'caddy', 'caddy', 'reload', '--config', '/etc/caddy/' + normal, '--adapter', 'caddyfile', output=work / 'normal.log')
            if not arguments.qa:
                deployment.run([sys.executable, str(DEPLOY / 'smoke_production.py'), '--url', 'https://' + deployment.server], output=work / 'public-smoke.json')
            receipt.update(state='DEPLOYED', backup=archive, restore_database=target,
                           finished_at=datetime.now(timezone.utc).isoformat(), admin='preserved; no initialization/reset performed')
        except Exception:
            receipt['state'] = 'FAILED_MAINTENANCE_REQUIRED'
            try:
                deployment.dc('exec', '-T', 'caddy', 'caddy', 'reload', '--config', '/etc/caddy/' + maintenance, '--adapter', 'caddyfile', output=work / 'failed-maintenance.log')
            except Exception:
                receipt['maintenance'] = 'could not confirm; inspect private logs'
            try:
                deployment.dc('stop', 'nginx', 'api', output=work / 'failed-stop-writers.log')
            except Exception:
                receipt['writers'] = 'could not confirm stopped; inspect service status'
            # Never restore an older DB automatically or erase evidence after uncertainty.
            write_json(receipt_path, receipt, exclusive=False)
            raise
        write_json(receipt_path, receipt, exclusive=False)
        print('DEPLOYED: migration/recovery/health gates passed; Owner browser login remains separate.')


def rollback(arguments):
    """Revert compatible images only; never restore/rewind the live database."""
    import fcntl
    receipt_path = Path(arguments.receipt).resolve()
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('qa') is not arguments.qa or receipt.get('state') not in ('DEPLOYED', 'FAILED_MAINTENANCE_REQUIRED'):
        raise RuntimeError('Rollback requires an attempted release receipt in the matching mode.')
    deployment = Deployment(arguments.qa, receipt['sha'])
    work = Path(receipt['private_artifacts']).resolve()
    with project_lock(deployment) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_source(deployment, receipt['sha'])
        checks = deployment.preflight()
        if (checks['target'] != receipt['target'] or checks['environment_sha256'] != receipt['environment_sha256']
                or checks['config_sha256'] != receipt['config_sha256']):
            raise RuntimeError('Rollback target/environment drifted; refusing to guess.')
        if (receipt.get('schema_changed') is not False or deployment.live_images() != receipt['candidate_images']
                or canonical_hash(deployment.schema()['migration_state']) != receipt['migration_state_sha256']):
            raise RuntimeError('Rollback requires the current candidate and unchanged, verified migration state.')
        images = receipt.get('previous_images', {})
        if set(images) != {'api', 'nginx'} or receipt.get('previous_ingress'):
            raise RuntimeError('No compatible previous Caddy stack. Keep maintenance; use the inventoried old deployment bundle for legacy ingress.')
        for image in images.values():
            if deployment.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']]).strip() != image['id']:
                raise RuntimeError('Previous image identity changed.')
        override = work / 'rollback-images.json'
        write_json(override, {'services': {name: {'image': image['tag']} for name, image in images.items()}})
        command = deployment.compose + ['-f', str(override)]
        normal = 'Caddyfile.qa' if arguments.qa else 'Caddyfile'
        maintenance = normal + '.maintenance'
        deployment.dc('exec', '-T', 'caddy', 'caddy', 'reload', '--config', '/etc/caddy/' + maintenance, '--adapter', 'caddyfile')
        deployment.dc('stop', 'api', 'nginx')
        # Read-only schema compatibility check with the previous API image.
        deployment.run(command + ['run', '--rm', '--no-deps', '-T', 'api', 'python', 'manage.py', 'migrate', '--check'])
        for service in ('api', 'nginx'):
            deployment.run(command + ['up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', service])
        if deployment.target() != receipt['target'] or deployment.live_images() != {name: image['id'] for name, image in images.items()}:
            raise RuntimeError('Rollback service identity could not be verified; keep maintenance.')
        deployment.dc('exec', '-T', 'caddy', 'caddy', 'reload', '--config', '/etc/caddy/' + normal, '--adapter', 'caddyfile')
        receipt['state'] = 'ROLLED_BACK_IMAGES_ONLY'
        write_json(receipt_path, receipt, exclusive=False)
        print('Previous compatible images restored. Database and all post-release writes retained.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    pre = sub.add_parser('preflight')
    pre.add_argument('--qa', action='store_true')
    prep = sub.add_parser('prepare')
    prep.add_argument('--sha', required=True)
    prep.add_argument('--output', required=True)
    prep.add_argument('--qa', action='store_true')
    execute = sub.add_parser('apply')
    execute.add_argument('--manifest', required=True)
    execute.add_argument('--qa', action='store_true')
    revert = sub.add_parser('rollback')
    revert.add_argument('--receipt', required=True)
    revert.add_argument('--qa', action='store_true')
    args = parser.parse_args()
    if args.action == 'preflight':
        print(json.dumps(Deployment(args.qa).preflight(), ensure_ascii=False, indent=2))
    elif args.action == 'prepare':
        prepare(args)
    elif args.action == 'apply':
        apply(args)
    else:
        rollback(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Deployment stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
