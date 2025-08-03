"""
Logging setup.

Credit: Adapted from the AnkiHub add-on.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from anki.hooks import wrap
from aqt import mw
from aqt.addons import AddonManager
from structlog.processors import CallsiteParameter
from structlog.typing import Processor

from ._internal import is_devmode, is_testing


def _shared_log_processors(addon: str) -> list[Processor]:
    return [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.THREAD,
                CallsiteParameter.MODULE,
                CallsiteParameter.FUNC_NAME,
            ],
            additional_ignores=[f"{addon}.vendor.structlog"],
        ),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def _structlog_formatter(
    addon: str,
    renderer: structlog.dev.ConsoleRenderer | structlog.processors.JSONRenderer,
) -> logging.Formatter:
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_log_processors(addon),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    return formatter


def log_file_path(addon: str) -> Path:
    logs_dir = Path(mw.addonManager.addonsFolder(addon)) / "user_files" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{addon}.log"


def get_logger(module: str) -> structlog.stdlib.BoundLogger:
    addon_name = "addon"
    logger_name = addon_name
    if not is_testing():
        addon_name = mw.addonManager.addonFromModule(module)
        # This is a workaround to avoid handling logs from vendored modules.
        logger_name = f"{addon_name}_"
    std_logger = logging.getLogger(logger_name)
    std_logger.propagate = False
    std_logger.setLevel(logging.DEBUG)
    structlog.configure(
        processors=_shared_log_processors(addon_name)
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=lambda _: std_logger,
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(logging.DEBUG if is_devmode() else logging.INFO)
    stdout_handler.setFormatter(
        _structlog_formatter(
            addon_name,
            structlog.dev.ConsoleRenderer(colors=True),
        )
    )
    std_logger.addHandler(stdout_handler)

    file_handler: RotatingFileHandler | None = None

    # Prevent errors when deleting/updating the add-on on Windows
    def close_log_file(
        manager: AddonManager, m: str, *args: Any, **kwargs: Any
    ) -> None:
        if m == addon_name and file_handler:
            file_handler.close()

    if not is_testing():
        file_handler = RotatingFileHandler(
            log_file_path(addon_name),
            "a",
            maxBytes=3 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG if is_devmode() else logging.INFO)

        try:
            import orjson  # noqa: PLC0415

            def json_serializer(*args: Any, **kwargs: Any) -> str:
                return orjson.dumps(*args, **kwargs).decode()
        except ImportError:
            json_serializer = json.dumps
        file_handler.setFormatter(
            _structlog_formatter(
                addon_name,
                structlog.processors.JSONRenderer(serializer=json_serializer),
            )
        )
        std_logger.addHandler(file_handler)
        AddonManager.deleteAddon = wrap(  # type: ignore[method-assign]
            AddonManager.deleteAddon, close_log_file, "before"
        )
        AddonManager.backupUserFiles = wrap(  # type: ignore[method-assign]
            AddonManager.backupUserFiles, close_log_file, "before"
        )

    return structlog.stdlib.get_logger(addon_name)
