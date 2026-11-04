"""File SQLite concurrency tests. Explicit unique TEST_DATABASE_NAME required."""
from pathlib import Path
from config.settings.local import *  # noqa: F403

name = Path(env('TEST_DATABASE_NAME')).resolve()  # noqa: F405
if not name.is_relative_to((BASE_DIR / '.verification').resolve()):  # noqa: F405
    raise ValueError('QA test database must live under backend/.verification')
DATABASES['default']['TEST'] = {'NAME': str(name)}  # noqa: F405
