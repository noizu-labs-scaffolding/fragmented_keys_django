"""Pytest configuration for fragmented_keys_django tests."""

import os
import sys
from pathlib import Path

import pytest

# Add the parent directory to the path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configure Django settings before importing Django models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

# Minimal Django settings for testing
if 'test_settings' not in sys.modules:
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY='test-secret-key',
            INSTALLED_APPS=[
                'django.contrib.contenttypes',
                'django.contrib.auth',
            ],
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            },
            CACHES={
                'default': {
                    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                },
                'redis': {
                    'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                    'LOCATION': 'redis://127.0.0.1:6379/15',
                },
            },
            USE_TZ=True,
        )
        import django
        django.setup()


@pytest.fixture
def redis_cache():
    """Provide a clean Redis cache (db 15) for integration tests.

    Flushes the database before and after each test to ensure isolation.
    """
    from django.core.cache import caches

    cache = caches['redis']
    cache.clear()
    yield cache
    cache.clear()
