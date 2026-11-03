#!/usr/bin/env python
"""Django command-line entry point; local settings are the development default."""
import os
import sys
from pathlib import Path


def main():
    import environ

    environ.Env.read_env(Path(__file__).resolve().parent / ".env", overwrite=False)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
