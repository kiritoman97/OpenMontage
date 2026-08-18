"""Shared Max Studio V3 task API plumbing.

The V3 API uses an API key header plus a Google Labs session cookie in the
JSON body.  Both values are loaded from environment variables and are never
returned in errors, tool metadata, or artifacts.

Submission is deliberately not retried: an ambiguous POST failure may still
have created a billable task.  Status polling is safe to retry and tolerates a
small number of transient transport failures.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_BASE_URL = "https://max-studio.online"
TERMINAL_SUCCESS = {"successfully"}
TERMINAL_FAILURE = {"failed"}

INSTALL_INSTRUCTIONS = (
    "Configure MAX_STUDIO_API_KEY and MAX_STUDIO_COOKIE in a private environment "
    "or secret store. Never commit either value."
)


class MaxStudioError(RuntimeError):
    """Raised for Max Studio transport, envelope, or task failures."""


def get_api_key() -> str | None:
    return os.environ.get("MAX_STUDIO_API_KEY")


def get_cookie() -> str | None:
    return os.environ.get("MAX_STUDIO_COOKIE")


def get_base_url() -> str:
    return os.environ.get("MAX_STUDIO_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_project_id() -> str | None:
    return os.environ.get("MAX_STUDIO_PROJECT_ID")


def _redact(value: Any, *secrets: str | None) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _headers(api_key: str, *, json_body: bool = True) -> dict[str, str]:
    headers = {"X-API-Key": api_key}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _response_body(
    response: Any,
    *,
    context: str,
    api_key: str,
    cookie: str,
) -> dict[str, Any]:
    status_code = int(getattr(response, "status_code", 200))
    try:
        body = response.json()
    except Exception as exc:
        raise MaxStudioError(
            f"{context} returned non-JSON data (HTTP {status_code})."
        ) from exc

    if not isinstance(body, dict):
        raise MaxStudioError(f"{context} returned an unexpected response envelope.")

    envelope_code = body.get("code")
    failed = status_code >= 400
    if envelope_code is not None:
        try:
            failed = failed or int(envelope_code) != 200
        except (TypeError, ValueError):
            failed = True

    if failed:
        category = body.get("error_category") or "api"
        error_code = body.get("error_code") or envelope_code or status_code
        message = body.get("messages") or body.get("error") or "request failed"
        safe_message = _redact(message, api_key, cookie)[:500]
        raise MaxStudioError(
            f"{context} failed ({category}, code {error_code}): {safe_message}"
        )
    return body


def create_task(
    endpoint: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    cookie: str,
    request_timeout: float = 60.0,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Create one task without automatic POST retries."""
    import requests

    url = f"{(base_url or get_base_url()).rstrip('/')}/api/v3/create-task/{endpoint}"
    body = dict(payload)
    body["cookie"] = cookie
    try:
        response = requests.post(
            url,
            headers=_headers(api_key),
            json=body,
            timeout=request_timeout,
        )
    except Exception as exc:
        safe = _redact(exc, api_key, cookie)
        raise MaxStudioError(
            "Max Studio task submission had an ambiguous transport failure. "
            "The task may have been created; do not resubmit automatically. "
            f"Details: {safe[:300]}"
        ) from exc

    data = _response_body(
        response,
        context=f"Max Studio {endpoint} submission",
        api_key=api_key,
        cookie=cookie,
    )
    task_id = data.get("taskid")
    if not task_id:
        raise MaxStudioError(
            f"Max Studio {endpoint} submission returned no taskid."
        )
    return data


def check_status(
    task_id: str,
    *,
    api_key: str,
    cookie: str,
    request_timeout: float = 30.0,
    base_url: str | None = None,
) -> dict[str, Any]:
    import requests

    url = f"{(base_url or get_base_url()).rstrip('/')}/api/v3/check-status/{task_id}"
    try:
        response = requests.get(
            url,
            headers=_headers(api_key, json_body=False),
            timeout=request_timeout,
        )
    except Exception as exc:
        safe = _redact(exc, api_key, cookie)
        raise MaxStudioError(
            f"Max Studio status check for {task_id} failed: {safe[:300]}"
        ) from exc
    return _response_body(
        response,
        context=f"Max Studio status check for {task_id}",
        api_key=api_key,
        cookie=cookie,
    )


def poll_task(
    task_id: str,
    *,
    api_key: str,
    cookie: str,
    interval: float = 4.0,
    timeout: float = 1200.0,
    request_timeout: float = 30.0,
    base_url: str | None = None,
) -> dict[str, Any]:
    elapsed = 0.0
    last_status = "pending"
    transport_failures = 0

    while elapsed <= timeout:
        try:
            body = check_status(
                task_id,
                api_key=api_key,
                cookie=cookie,
                request_timeout=request_timeout,
                base_url=base_url,
            )
            transport_failures = 0
        except MaxStudioError:
            transport_failures += 1
            if transport_failures >= 5:
                raise
            time.sleep(interval)
            elapsed += interval
            continue

        last_status = str(body.get("status", "pending")).lower()
        if last_status in TERMINAL_SUCCESS:
            return body
        if last_status in TERMINAL_FAILURE:
            category = body.get("error_category") or "provider"
            error_code = body.get("error_code") or body.get("code") or "unknown"
            message = _redact(
                body.get("messages") or body.get("error") or "task failed",
                api_key,
                cookie,
            )[:500]
            raise MaxStudioError(
                f"Max Studio task {task_id} failed ({category}, code {error_code}): {message}"
            )

        time.sleep(interval)
        elapsed += interval

    raise MaxStudioError(
        f"Max Studio task {task_id} did not finish within {timeout:.0f}s "
        f"(last status: {last_status}). The task may still complete; check it by taskid."
    )


def submit_and_wait(
    endpoint: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    cookie: str,
    interval: float = 4.0,
    timeout: float = 1200.0,
    request_timeout: float = 60.0,
    base_url: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = create_task(
        endpoint,
        payload,
        api_key=api_key,
        cookie=cookie,
        request_timeout=request_timeout,
        base_url=base_url,
    )
    completed = poll_task(
        str(created["taskid"]),
        api_key=api_key,
        cookie=cookie,
        interval=interval,
        timeout=timeout,
        request_timeout=min(request_timeout, 30.0),
        base_url=base_url,
    )
    return created, completed


def result_media_id(body: dict[str, Any]) -> str:
    result = body.get("result") or {}
    if not isinstance(result, dict):
        raise MaxStudioError("Max Studio task returned an invalid result object.")
    media_id = result.get("mediaGenerationId") or result.get("mediaId")
    if not media_id:
        raise MaxStudioError("Max Studio upload completed without a media ID.")
    return str(media_id)


def result_media_url(body: dict[str, Any]) -> str:
    result = body.get("result") or {}
    if not isinstance(result, dict):
        raise MaxStudioError("Max Studio task returned an invalid result object.")
    url = result.get("fifeUrl")
    if not url:
        raise MaxStudioError("Max Studio generation completed without a fifeUrl.")
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"}:
        raise MaxStudioError("Max Studio returned an unsupported output URL scheme.")
    return str(url)


def download(url: str, output_path: str | Path, *, timeout: float = 300.0) -> Path:
    import requests

    try:
        response = requests.get(url, timeout=timeout)
        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 400:
            raise MaxStudioError(
                f"Max Studio output download failed with HTTP {status_code}."
            )
        content = bytes(getattr(response, "content", b""))
    except MaxStudioError:
        raise
    except Exception as exc:
        raise MaxStudioError(f"Max Studio output download failed: {exc}") from exc

    if not content:
        raise MaxStudioError("Max Studio output download returned an empty file.")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
