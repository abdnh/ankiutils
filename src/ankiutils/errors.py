"""
Error handling and Sentry integration.

Credit: Adapted from the AnkiHub add-on.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import re
import sys
import threading
import traceback
from types import TracebackType
from typing import Any, Callable, Optional

import sentry_sdk
import structlog
from anki.utils import checksum, pointVersion
from sentry_sdk import capture_exception, new_scope
from sentry_sdk.integrations.argv import ArgvIntegration
from sentry_sdk.integrations.dedupe import DedupeIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.stdlib import StdlibIntegration
from sentry_sdk.scope import Scope

from .config import Config
from .consts import AddonConsts
from .gofile import upload_file
from .log import log_file_path


@dataclasses.dataclass
class _ErrorReportingArgs:
    consts: AddonConsts
    config: Config
    logger: structlog.stdlib.BoundLogger
    on_handle_exception: Callable[[BaseException, str | None], None] | None
    on_sentry_scope: Callable[[Scope], None] | None


ExceptionCallback = Callable[
    [type[BaseException], BaseException, Optional[TracebackType]], None
]
exception_callbacks: list[ExceptionCallback] = []

DEFAULT_SENTRY_DSN = "https://a60ae1ebef99da387eed46e0fb114ea9@o4507277389201408.ingest.us.sentry.io/4507277391036416"


def setup_error_handler(  # noqa: PLR0913
    consts: AddonConsts,
    config: Config,
    logger: structlog.stdlib.BoundLogger,
    sentry_dsn: str | None = None,
    on_handle_exception: Callable[[BaseException, str | None], None] | None = None,
    on_sentry_scope: Callable[[Scope], None] | None = None,
) -> None:
    """Set up centralized exception handling and initialize Sentry."""

    args = _ErrorReportingArgs(
        consts=consts,
        config=config,
        logger=logger,
        on_handle_exception=on_handle_exception,
        on_sentry_scope=on_sentry_scope,
    )
    _setup_excepthook(args)
    _setup_threading_excepthook(args)
    if _error_reporting_enabled(args):
        _initialize_sentry(args, sentry_dsn)


def register_exception_callback(callback: ExceptionCallback) -> None:
    exception_callbacks.append(callback)


def _initialize_sentry(args: _ErrorReportingArgs, dsn: str | None = None) -> None:
    os.environ["SENTRY_RELEASE"] = args.consts.version

    sentry_sdk.init(
        dsn=dsn or DEFAULT_SENTRY_DSN,
        traces_sample_rate=1.0,
        release=args.consts.version,
        default_integrations=False,
        integrations=[
            ArgvIntegration(),
            DedupeIntegration(),
            LoggingIntegration(),
            StdlibIntegration(),
            # Causes problems with AnkiHub
            # ThreadingIntegration(),
        ],
        # This disable the AtexitIntegration because
        # it causes a RuntimeError when Anki is closed.
        shutdown_timeout=0,
        before_send=lambda event, hint: _before_send(args, event, hint),
    )


def _before_send(
    args: _ErrorReportingArgs, event: Any, hint: dict[str, Any]
) -> Any | None:
    """Filter out events created by the LoggingIntegration
    that are not related to this add-on."""
    if "log_record" in hint:
        logger_name = hint["log_record"].name
        if logger_name != args.logger.name:
            return None
    return event


def _report_exception_and_upload_logs(
    exception: BaseException,
    args: _ErrorReportingArgs,
    context: dict[str, Any] | None = None,
) -> str | None:
    """Report the exception to Sentry and upload the logs.
    Returns the Sentry event ID."""

    if not _error_reporting_enabled(args):
        return None

    if not context:
        context = {}
    sentry_id = _report_exception(
        exception=exception,
        args=args,
        context={**context, "logs": _upload_logs(args)},
    )

    return sentry_id


def report_exception_and_upload_logs(
    exception: BaseException,
    consts: AddonConsts,
    config: Config,
    logger: structlog.stdlib.BoundLogger,
    on_sentry_scope: Callable[[Scope], None] | None = None,
) -> str | None:
    return _report_exception_and_upload_logs(
        exception,
        _ErrorReportingArgs(
            consts=consts,
            config=config,
            logger=logger,
            on_handle_exception=None,
            on_sentry_scope=on_sentry_scope,
        ),
    )


def _report_exception_and_upload_logs_in_background(
    exception: BaseException,
    args: _ErrorReportingArgs,
    on_done: Callable[[str | None], None] | None = None,
) -> None:
    from aqt import mw  # noqa: PLC0415

    mw.taskman.with_progress(
        functools.partial(
            _report_exception_and_upload_logs,
            exception,
            args,
        ),
        on_done=lambda f: on_done(f.result()) if on_done else None,
        label="Reporting error...",
    )


def report_exception_and_upload_logs_in_background(
    exception: BaseException,
    consts: AddonConsts,
    config: Config,
    logger: structlog.stdlib.BoundLogger,
    on_sentry_scope: Callable[[Scope], None] | None = None,
    on_done: Callable[[str | None], None] | None = None,
) -> None:
    _report_exception_and_upload_logs_in_background(
        exception,
        _ErrorReportingArgs(
            consts=consts,
            config=config,
            logger=logger,
            on_handle_exception=None,
            on_sentry_scope=on_sentry_scope,
        ),
        on_done=on_done,
    )


def _setup_excepthook(args: _ErrorReportingArgs) -> None:
    """Set up centralized exception handling.
    Exceptions are are either handled by our exception handler
    or passed to the original excepthook which opens Anki's error dialog.
    If error reporting is enabled, unhandled exceptions
    (in which this add-on is involved)
    are reported to Sentry and the user is prompted to provide feedback
    (in addition to Anki's error dialog opening).
    """

    def excepthook(
        etype: type[BaseException], val: BaseException, tb: TracebackType
    ) -> Any:
        handled = False
        try:
            handled = _try_handle_exception(args, exc_type=etype, exc_value=val, tb=tb)
        except Exception as exc:
            # catching all exceptions here prevents a potential exception loop
            args.logger.exception(
                "The exception handler threw an exception.", exc_info=exc
            )
        finally:
            if handled:
                return

            if _this_addon_mentioned_in_tb(tb, args):
                if _error_reporting_enabled(args):
                    try:
                        _maybe_report_exception(exception=val, args=args)
                    except Exception as e:
                        args.logger.warning(
                            "Error while reporting exception",
                            exc_info=e,
                        )
                if args.on_handle_exception:
                    args.on_handle_exception(val, None)
                else:
                    original_excepthook(etype, val, tb)
            else:
                original_excepthook(etype, val, tb)

    original_excepthook = sys.excepthook
    sys.excepthook = excepthook


def _setup_threading_excepthook(args: _ErrorReportingArgs) -> None:
    """Set up a threading excepthook.
    This is used to report exceptions from threads.
    """

    def excepthook(
        exc_args: threading.ExceptHookArgs,
    ) -> Any:
        handled = False
        if not exc_args.exc_value:
            return original_excepthook(exc_args)
        try:
            handled = _try_handle_exception(
                args,
                exc_type=exc_args.exc_type,
                exc_value=exc_args.exc_value,
                tb=exc_args.exc_traceback,
            )
        except Exception as exc:
            # catching all exceptions here prevents a potential exception loop
            args.logger.exception(
                "The threading exception handler threw an exception.", exc_info=exc
            )
        finally:
            if handled:
                return

            if exc_args.exc_traceback and _this_addon_mentioned_in_tb(
                exc_args.exc_traceback, args
            ):
                if _error_reporting_enabled(args):
                    try:
                        _maybe_report_exception(exception=exc_args.exc_value, args=args)
                    except Exception as e:
                        args.logger.warning(
                            "There was an error while reporting the exception "
                            "or showing the feedback dialog.",
                            exc_info=e,
                        )
                if args.on_handle_exception:
                    args.on_handle_exception(exc_args.exc_value, None)
                else:
                    original_excepthook(exc_args)
            else:
                original_excepthook(exc_args)

    original_excepthook = threading.excepthook
    threading.excepthook = excepthook


def _maybe_report_exception(
    exception: BaseException, args: _ErrorReportingArgs
) -> None:
    def on_done(sentry_event_id: str | None) -> None:
        # TODO: maybe set our own error dialog here
        if args.on_handle_exception:
            from aqt import mw  # noqa: PLC0415

            mw.taskman.run_on_main(
                functools.partial(args.on_handle_exception, exception, sentry_event_id)
            )

    _report_exception_and_upload_logs_in_background(
        exception=exception, args=args, on_done=on_done
    )


def _try_handle_exception(
    args: _ErrorReportingArgs,
    exc_type: type[BaseException],
    exc_value: BaseException,
    tb: TracebackType | None,
) -> bool:
    """Try to handle the exception. Return True if the exception was handled,
    False otherwise."""
    args.logger.info(
        "From _try_handle_exception:\n"
        + "".join(traceback.format_exception(exc_type, value=exc_value, tb=tb))
    )

    for callback in exception_callbacks:
        if callback(exc_type, exc_value, tb):
            return True

    return False


def _this_addon_mentioned_in_tb(tb: TracebackType, args: _ErrorReportingArgs) -> bool:
    tb_str = "".join(traceback.format_tb(tb))
    result = _contains_path_to_this_addon(tb_str, args)
    return result


def _contains_path_to_this_addon(tb_str: str, args: _ErrorReportingArgs) -> bool:
    return bool(re.search(rf"(/|\\)addons21(/|\\){args.consts.module}(/|\\)", tb_str))


def _report_exception(
    exception: BaseException,
    args: _ErrorReportingArgs,
    context: dict[str, dict[str, Any]],
) -> str | None:
    """Report an exception to Sentry."""
    if not _error_reporting_enabled(args):
        return None

    with new_scope() as scope:
        scope.set_level("error")
        scope.set_tag("os", sys.platform)
        scope.set_tag("add-on", args.consts.module)
        scope.set_context("add-on version", {"version": args.consts.version})
        scope.set_context("anki version", {"version": pointVersion()})
        scope.set_context("add-on config", args.config.asdict())

        for key, value in context.items():
            scope.set_context(key, value)

        if exception.__traceback__:
            scope.set_tag(
                "addon_in_traceback",
                str(_this_addon_mentioned_in_tb(exception.__traceback__, args)),
            )
        else:
            args.logger.warning("Exception has no traceback.")

        if args.on_sentry_scope:
            args.on_sentry_scope(scope)

        sentry_id = capture_exception(exception)

    return sentry_id


def _error_reporting_enabled(args: _ErrorReportingArgs) -> bool:
    return (
        args.config.get("report_errors") and not os.getenv("REPORT_ERRORS", None) == "0"
    )


def _upload_logs(args: _ErrorReportingArgs) -> dict[str, str] | None:
    addon = args.consts.module
    if not log_file_path(addon).exists():
        return None

    for handler in args.logger.handlers:
        handler.flush()

    path = log_file_path(addon)
    name = f"{addon}_{checksum(path.read_text(encoding='utf-8'))}.log"
    try:
        return {"url": upload_file(path, name), "filename": name}
    except Exception as exc:
        _report_exception(exc, args, {})
        return None
