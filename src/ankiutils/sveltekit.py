from __future__ import annotations

import mimetypes
import os
import threading
from http import HTTPStatus
from typing import TYPE_CHECKING, Callable

import flask
from flask import request
from structlog.stdlib import BoundLogger
from waitress.server import create_server

if TYPE_CHECKING:
    from ankiutils.gui.sveltekit_web import SveltekitWebDialog

from .consts import AddonConsts


def _text_response(code: HTTPStatus, text: str) -> flask.Response:
    resp = flask.make_response(text, code)
    resp.headers["Content-type"] = "text/plain"
    return resp


def get_addon_env_var(consts: AddonConsts, name: str, default: str = "") -> str:
    key = f"{consts.module}_{name}".upper()
    return os.environ.get(key, default)


def is_hmr_enabled(consts: AddonConsts) -> bool:
    return bool(get_addon_env_var(consts, "HMR"))


def get_api_host(consts: AddonConsts) -> str:
    return get_addon_env_var(consts, "API_HOST", "127.0.0.1")


def get_api_port(consts: AddonConsts) -> int:
    return int(get_addon_env_var(consts, "API_PORT", "0"))


class SveltekitServerError(Exception):
    pass


class SveltekitServerNotInitializedError(SveltekitServerError):
    def __init__(self) -> None:
        super().__init__("Sveltekit server is not initialized")


class SveltekitServer(threading.Thread):
    _ready = threading.Event()
    daemon = True

    def __init__(self, consts: AddonConsts, logger: BoundLogger) -> None:
        super().__init__()
        self.consts = consts
        self.logger = logger
        self.is_shutdown = False
        self.flask_app = flask.Flask(__name__)
        self.proto_handlers: dict[tuple[str, str], Callable[[bytes], bytes]] = {}
        self.proto_handlers_for_dialog: dict[
            int, dict[tuple[str, str], Callable[[bytes], bytes]]
        ] = {}
        self._register_routes()

    def _register_routes(self) -> None:
        self.flask_app.add_url_rule(
            "/api/<path:service>/<path:method>",
            methods=["POST"],
            view_func=self._handle_api_request,
        )
        self.flask_app.add_url_rule(
            "/<path:path>",
            methods=["GET", "POST"],
            view_func=self._handle_sveltekit_request,
        )

    def add_proto_handler(
        self, service: str, method: str, handler: Callable[[bytes], bytes]
    ) -> None:
        self.proto_handlers[(service, method)] = handler

    def add_proto_handler_for_dialog(
        self,
        dialog: SveltekitWebDialog,
        service: str,
        method: str,
        func: Callable[[bytes], bytes],
    ) -> None:
        dialog_id = id(dialog)
        self.proto_handlers_for_dialog.setdefault(dialog_id, {})
        handlers = self.proto_handlers_for_dialog[dialog_id]
        handlers[(service, method)] = func

    def remove_proto_handlers_for_dialog(self, dialog: SveltekitWebDialog) -> None:
        dialog_id = id(dialog)
        self.proto_handlers_for_dialog.pop(dialog_id, None)

    def _handle_api_request(self, service: str, method: str) -> flask.Response:
        dialog_id: str | None = request.headers.get("qt-widget-id", None)
        if dialog_id:
            handler = self.proto_handlers_for_dialog.get(int(dialog_id), {}).get(
                (service, method)
            )
        if not handler:
            handler = self.proto_handlers.get((service, method))
        if not handler:
            return _text_response(
                HTTPStatus.NOT_FOUND, f"No handler found for {service}/{method}"
            )
        response = flask.make_response(handler(request.data))
        response.headers["Content-type"] = "application/proto"
        return response

    def _handle_sveltekit_request(self, path: str) -> flask.Response:
        immutable = "immutable" in path
        if not immutable:
            path = "index.html"
        mimetype, _encoding = mimetypes.guess_type(path)
        if not mimetype:
            mimetype = "application/octet-stream"
        try:
            full_path = self.consts.dir / "web" / "sveltekit" / path
            data = full_path.read_bytes()
            response = flask.Response(data, mimetype=mimetype)
            if immutable:
                response.headers["Cache-Control"] = "max-age=31536000"
        except FileNotFoundError:
            self.logger.exception("Sveltekit request returned 404", path=path)
            resp = _text_response(HTTPStatus.NOT_FOUND, f"Invalid path: {path}")
            resp.headers["Content-type"] = "text/plain"
            return resp
        except Exception as error:
            self.logger.exception("Sveltekit server exception", path=path)
            return _text_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
        return response

    def run(self) -> None:
        try:
            desired_host = get_api_host(self.consts)
            desired_port = get_api_port(self.consts)
            self.server = create_server(
                self.flask_app,
                host=desired_host,
                port=desired_port,
                clear_untrusted_proxy_headers=True,
            )
            print(
                f"Started Sveltekit server at http://{self.server.effective_host}:{self.server.effective_port}",  # type: ignore
            )

            self._ready.set()
            self.server.run()

        except Exception:
            if not self.is_shutdown:
                raise

    def shutdown(self) -> None:
        if not self.server:
            return
        self.is_shutdown = True
        sockets = list(self.server._map.values())  # type: ignore
        for socket in sockets:
            socket.handle_close()
        self.server.task_dispatcher.shutdown()

    def get_port(self) -> int:
        self._ready.wait()
        return int(self.server.effective_port)  # type: ignore

    def get_host(self) -> str:
        self._ready.wait()
        return self.server.effective_host  # type: ignore

    def get_url(self) -> str:
        return f"http://{self.get_host()}:{self.get_port()}"


def init_server(
    consts: AddonConsts,
    logger: BoundLogger,
) -> SveltekitServer:
    server = SveltekitServer(consts, logger)
    server.start()
    return server
