from __future__ import annotations

from aqt import mw
from aqt.qt import QWidget
from aqt.utils import showInfo, tooltip

from ..errors import ErrorReportingArgs, LogsUpload, upload_logs_op


def upload_logs_and_notify_user(parent: QWidget, args: ErrorReportingArgs) -> None:
    def on_success(upload: LogsUpload | None) -> None:
        if not upload:
            tooltip("Failed to upload logs. Issue has been reported.", parent=parent)
            return
        mw.app.clipboard().setText(upload.filename)
        showInfo(
            f"Logs uploaded to file {upload.filename}. "
            "Filename was copied to your clipboard.<br>"
            "Please share it using one of the following support channels:<br><br>"
            + "<br>".join(
                f"<a href='{url}'>{url}</a>"
                for url in args.consts.support_channels.values()
            ),
            title=args.consts.name,
            parent=parent,
            textFormat="rich",
        )

    upload_logs_op(parent=parent, args=args, on_success=on_success).run_in_background()
