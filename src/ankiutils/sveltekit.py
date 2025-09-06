from __future__ import annotations

import mimetypes
import os
import threading
from http import HTTPStatus

import flask
from structlog.stdlib import BoundLogger
from waitress.server import create_server

from .consts import AddonConsts


def _text_response(code: HTTPStatus, text: str) -> flask.Response:
    resp = flask.make_response(text, code)
    resp.headers["Content-type"] = "text/plain"
    return resp


def is_hmr_enabled(consts: AddonConsts) -> bool:
    key = f"{consts.module}_HMR".upper()
    return bool(os.environ.get(key, ""))


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
        if not is_hmr_enabled(self.consts):
            self.flask_app = flask.Flask(__name__)
            self._register_routes()

    def _register_routes(self) -> None:
        self.flask_app.add_url_rule(
            "/<path:path>", methods=["GET", "POST"], view_func=self._handle_request
        )

    def _handle_request(self, path: str) -> flask.Response:
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
        if is_hmr_enabled(self.consts):
            self._ready.set()
            self.logger.debug("HMR is enabled; skipping Sveltekit server start")
            return
        try:
            self.server = create_server(
                self.flask_app,
                host="127.0.0.1",
                port=0,
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
        if is_hmr_enabled(self.consts):
            return 5174
        self._ready.wait()
        return int(self.server.effective_port)  # type: ignore

    def get_host(self) -> str:
        if is_hmr_enabled(self.consts):
            return "127.0.0.1"
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
