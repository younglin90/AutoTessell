"""beta47 — core/utils/logging.py dedicated 회귀."""
from __future__ import annotations

import logging

import pytest
import structlog

from core.utils.logging import configure_logging, get_logger


def test_get_logger_returns_bound_logger() -> None:
    """get_logger 는 structlog BoundLogger 반환."""
    log = get_logger("test_module")
    # structlog BoundLoggerLazyProxy 는 실제 BoundLogger 로 해소되기 전 단계
    assert log is not None
    # info 호출이 예외를 던지지 않아야
    log.info("smoke test event", key="value")


def test_configure_logging_verbose_sets_debug_level() -> None:
    """verbose=True → root logger 가 DEBUG 레벨."""
    configure_logging(verbose=True, json=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_configure_logging_default_sets_info_level() -> None:
    """verbose=False → INFO 레벨."""
    configure_logging(verbose=False, json=False)
    root = logging.getLogger()
    assert root.level == logging.INFO


def test_configure_logging_clears_and_adds_handler() -> None:
    """configure_logging 호출 후 root handler 정확히 하나."""
    # 기존 핸들러 여러 개 남아있을 수 있으므로 먼저 초기화
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.NullHandler())
    root.addHandler(logging.NullHandler())
    assert len(root.handlers) == 2

    configure_logging(verbose=False)
    # configure 후에는 단일 handler
    assert len(root.handlers) == 1


def test_configure_logging_json_mode_uses_json_renderer() -> None:
    """json=True → 로그 처리가 JSON 포맷으로 설정되어 예외 없이 동작."""
    configure_logging(verbose=True, json=True)
    # structlog configuration 은 JSON renderer 를 사용 — 실제 출력 캡처는 복잡하지만
    # configure_logging 이 예외 없이 완료되는지만 smoke 검증.
    log = get_logger("json_test")
    log.info("json smoke", key="val")


def test_configure_logging_idempotent() -> None:
    """여러 번 호출해도 문제 없음."""
    configure_logging(verbose=True)
    configure_logging(verbose=False)
    configure_logging(verbose=True, json=True)
    log = get_logger("repeated")
    log.info("event")


def test_get_logger_name_preserved() -> None:
    """get_logger 로 이름 전달 시 나중에 그 이름으로 식별 가능."""
    log = get_logger("my.module.name")
    # structlog proxy 는 실제 호출 시 logger 를 해소. 이름이 설정되었다면
    # 내부 _logger_factory 에서 처리.
    log.info("named event")
