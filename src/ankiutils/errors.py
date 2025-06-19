"""
Error handling and Sentry integration.

Credit: Adapted from the AnkiHub add-on.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import sys
import traceback
from types import TracebackType
from typing import Any, Callable, Optional

import sentry_sdk
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
    logger: logging.Logger
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
    logger: logging.Logger,
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
    logger: logging.Logger,
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
        etype: type[BaseException], val: BaseException, tb: TracebackType | None
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
                return  # pylint: disable=lost-exception, return-in-finally

            if _this_addon_mentioned_in_tb(tb, args):
                try:
                    _maybe_report_exception(exception=val, args=args)
                except Exception as e:
                    args.logger.warning(
                        "There was an error while reporting the exception "
                        "or showing the feedback dialog.",
                        exc_info=e,
                    )
            elif not args.on_handle_exception:
                original_excepthook(etype, val, tb)  # pylint: disable=lost-exception

    original_excepthook = sys.excepthook
    sys.excepthook = excepthook


def _maybe_report_exception(
    exception: BaseException, args: _ErrorReportingArgs
) -> str | None:
    sentry_event_id: str | None = None
    if _error_reporting_enabled(args):
        sentry_event_id = _report_exception_and_upload_logs(
            exception=exception, args=args
        )
    # TODO: maybe set our own error dialog here
    if args.on_handle_exception:
        args.on_handle_exception(exception, sentry_event_id)
    return sentry_event_id


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
    if _obsolete_version_of_sentry_sdk():
        args.logger.info(
            "Obsolete version of sentry-sdk detected. Error reporting disabled."
        )
        return False

    result = (
        args.config.get("report_errors") and not os.getenv("REPORT_ERRORS", None) == "0"
    )
    return result


def _obsolete_version_of_sentry_sdk() -> bool:
    result = [int(x) for x in sentry_sdk.VERSION.split(".")] < [1, 5, 5]
    return result


def _upload_logs(args: _ErrorReportingArgs) -> dict[str, str] | None:
    addon = args.consts.module
    if not log_file_path(addon).exists():
        return None

    path = log_file_path(addon)
    name = f"{addon}_{checksum(path.read_text(encoding='utf-8'))}.log"
    try:
        return {"url": upload_file(path, name), "filename": name}
    except Exception as exc:
        _report_exception(exc, args, {})
        return None
