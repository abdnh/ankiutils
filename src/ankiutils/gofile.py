from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from ._gofile_api_key import get_gofile_api_key

API_URL = "https://api.gofile.io"
LOGS_FOLDER_ID = "59e5ae0b-9c62-44f5-89e8-62f60777d7c4"
TIMEOUT = 20


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {}).copy()
    headers.update({"Authorization": f"Bearer {get_gofile_api_key()}"})
    response = requests.request(
        method=method,
        url=url,
        timeout=TIMEOUT,
        headers=headers,
        **kwargs,
    )
    response.raise_for_status()

    return response


def _api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    response = _request(
        method=method,
        url=f"{API_URL}/{path}",
        **kwargs,
    )
    response.raise_for_status()

    return response


def get_servers() -> list[dict]:
    response = _api_request(method="get", path="servers?zone=eu")
    return response.json()["data"]["servers"]


def upload_file(path: str | Path, name: str) -> str:
    server = get_servers()[0]["name"]
    with open(path, "rb") as file:
        upload_data = _request(
            method="post",
            url=f"https://{server}.gofile.io/contents/uploadfile",
            files={"file": file.read()},
            data={"folderId": LOGS_FOLDER_ID},
        ).json()["data"]
        file_id = upload_data["id"]
        _api_request(
            method="put",
            path=f"contents/{file_id}/update",
            data=json.dumps({"attribute": "name", "attributeValue": name}),
            headers={"Content-Type": "application/json"},
        )

    return upload_data["downloadPage"]
