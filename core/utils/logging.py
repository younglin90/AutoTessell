"""structlog 기반 JSON 로깅 설정."""

from __future__ import annotations

import logging
import sys

import structlog

#: configure_logging()과 반드시 동일해야 하는 프로세서 체인 — 별도 핸들러가
#: (예: 데스크톱 GUI 상세 로그 스트리밍) 같은 렌더링을 재사용할 때 이 상수를
#: import 해서 두 곳의 체인이 어긋나는 일이 없도록 한다.
SHARED_PROCESSORS: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
]


def make_processor_formatter(*, colors: bool = False) -> logging.Formatter:
    """(재사용 가능) structlog 렌더링 ``logging.Formatter``.

    ``configure_logging`` 의 루트 핸들러와 동일한 처리 체인을 쓰는 별도
    핸들러(예: 파이프라인 실행 동안만 붙는 GUI 상세-로그 핸들러)를 만들 때
    사용한다.
    """
    return structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=colors),
        foreign_pre_chain=SHARED_PROCESSORS,
    )


#: verbose=True 는 루트를 DEBUG 로 올려 core.*/desktop.* 의 세세한 엔진 로그를
#: 전부 살리기 위함이지, 이 서드파티 라이브러리들의 DEBUG 잡음까지 원하는 게
#: 아니다 (mesh export/eval 경로가 matplotlib·pyvista/vtk 를 실제로 import
#: 한다 — 둘 다 DEBUG 레벨에서 매우 수다스러운 것으로 알려져 있음).
_NOISY_THIRD_PARTY_LOGGERS = (
    "matplotlib", "PIL", "vtk", "pyvista", "trimesh",
    "urllib3", "websockets", "asyncio", "PySide6",
)


def configure_logging(*, verbose: bool = False, json: bool = False) -> None:
    """Auto-Tessell 전역 로깅 초기화.

    Args:
        verbose: True이면 DEBUG 레벨, 아니면 INFO. (서드파티 라이브러리는
            노이즈 방지를 위해 verbose 여부와 무관하게 WARNING 이상만 통과.)
        json: True이면 JSON 포맷 (서버/파이프), False이면 콘솔 포맷 (CLI).
    """
    level = logging.DEBUG if verbose else logging.INFO
    shared_processors = SHARED_PROCESSORS

    if json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    if verbose:
        for _name in _NOISY_THIRD_PARTY_LOGGERS:
            logging.getLogger(_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
