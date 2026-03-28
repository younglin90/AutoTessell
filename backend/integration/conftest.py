"""
Integration test conftest — uses REAL SQLAlchemy + FastAPI TestClient.

Does NOT stub sqlalchemy/stripe/celery at the module level (unlike the unit
test conftest). Stripe and S3 calls are patched per-test using unittest.mock.
"""
import os
import sys

# Ensure we can import backend modules
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

# Stub pydantic_settings so Settings() reads class defaults without .env
class _BaseSettings:
    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        cls = type(self)
        for name in getattr(cls, "__annotations__", {}):
            val = kwargs.get(name, getattr(cls, name, ""))
            object.__setattr__(self, name, val)


import unittest.mock as _mock
_ps_mod = _mock.MagicMock()
_ps_mod.BaseSettings = _BaseSettings
sys.modules.setdefault("pydantic_settings", _ps_mod)

# Stub Stripe
_stripe_mod = _mock.MagicMock()
_stripe_mod.StripeError = Exception
sys.modules.setdefault("stripe", _stripe_mod)

# Stub boto3 / botocore
sys.modules.setdefault("boto3", _mock.MagicMock())
sys.modules.setdefault("botocore", _mock.MagicMock())

# Stub Celery
class _FakeTask:
    abstract = False
    request = _mock.MagicMock()

class _FakeSoftLimit(Exception):
    pass

_celery_mod = _mock.MagicMock()
_celery_mod.Task = _FakeTask
_celery_exc = _mock.MagicMock()
_celery_exc.SoftTimeLimitExceeded = _FakeSoftLimit
_fake_app = _mock.MagicMock()
_fake_app.task = lambda *a, **kw: (lambda f: f)
_celery_app_mod = _mock.MagicMock()
_celery_app_mod.celery_app = _fake_app
sys.modules.setdefault("celery", _celery_mod)
sys.modules.setdefault("celery.exceptions", _celery_exc)
sys.modules.setdefault("worker.celery_app", _celery_app_mod)
