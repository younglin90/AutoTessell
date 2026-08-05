"""
Shared pytest fixtures and module-level mocks for the test suite.

Production-only dependencies (boto3, stripe, celery, sqlalchemy, pydantic_settings)
are not installed in the development environment. We stub them out at the
sys.modules level before any test module imports worker.tasks, so the import
succeeds and individual tests can patch the stubs as needed.
"""

import enum
import sys
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# pydantic_settings stub — BaseSettings reads class-level defaults
# ---------------------------------------------------------------------------

class _BaseSettings:
    """Minimal BaseSettings stub: reads class-level defaults, ignores env file."""

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        cls = type(self)
        for name, annotation in cls.__annotations__.items():
            val = kwargs.get(name, getattr(cls, name, ""))
            object.__setattr__(self, name, val)


_ps_mod = MagicMock()
_ps_mod.BaseSettings = _BaseSettings
sys.modules.setdefault("pydantic_settings", _ps_mod)


# ---------------------------------------------------------------------------
# sqlalchemy stub — enough for db.py to import cleanly
# ---------------------------------------------------------------------------

_sa_mod = MagicMock()
_sa_orm_mod = MagicMock()
_sa_dialects_pg = MagicMock()

# Column, DateTime, etc. must return something with a sensible __repr__
for _name in ("Column", "DateTime", "Enum", "ForeignKey", "Integer", "String", "Text",
              "create_engine"):
    setattr(_sa_mod, _name, MagicMock(return_value=MagicMock()))

_sa_mod.func = MagicMock()

# DeclarativeBase must be a real class so Job(Base) works
class _DeclarativeBase:
    metadata = MagicMock()

_sa_orm_mod.DeclarativeBase = _DeclarativeBase
_sa_orm_mod.sessionmaker = MagicMock(return_value=MagicMock())
_sa_orm_mod.Session = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mod)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mod)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg)


# ---------------------------------------------------------------------------
# celery stubs
# ---------------------------------------------------------------------------

class _FakeTask:
    """Minimal Task base class so MeshTask(Task) inherits cleanly."""
    abstract = False
    request = MagicMock()


class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_mod = MagicMock()
_celery_mod.Task = _FakeTask

_celery_exc_mod = MagicMock()
_celery_exc_mod.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded

# celery_app mock — must have .task() decorator
_fake_celery_app = MagicMock()
_fake_celery_app.task = lambda *a, **kw: (lambda f: f)  # identity decorator

_celery_app_mod = MagicMock()
_celery_app_mod.celery_app = _fake_celery_app

sys.modules.setdefault("celery", _celery_mod)
sys.modules.setdefault("celery.exceptions", _celery_exc_mod)
sys.modules.setdefault("worker.celery_app", _celery_app_mod)


# ---------------------------------------------------------------------------
# stripe stub
# ---------------------------------------------------------------------------

class _FakeStripeError(Exception):
    pass


_stripe_mod = MagicMock()
_stripe_mod.StripeError = _FakeStripeError
_stripe_mod.Refund = MagicMock()

sys.modules.setdefault("stripe", _stripe_mod)


# ---------------------------------------------------------------------------
# boto3 stub (lazy-imported in tasks, but stub here for safety)
# ---------------------------------------------------------------------------

sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
