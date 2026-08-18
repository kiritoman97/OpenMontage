"""Contract and regression tests for the Max Studio V3 video provider."""

from __future__ import annotations

import json
import sys
import types

import pytest

from tools.base_tool import ToolStatus


class FakeResponse:
    def __init__(self, body=None, *, content=b"", status_code=200):
        self._body = body
        self.content = content
        self.status_code = status_code
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


def _fake_requests(monkeypatch, *, posts=None, gets=None):
    calls = {"post": [], "get": []}
    post_items = list(posts or [])
    get_items = list(gets or [])
    module = types.ModuleType("requests")

    def post(url, headers=None, json=None, timeout=None, **kwargs):
        calls["post"].append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        item = post_items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(url, headers=None, timeout=None, **kwargs):
        calls["get"].append(
            {"url": url, "headers": headers, "timeout": timeout}
        )
        item = get_items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    module.post = post
    module.get = get
    monkeypatch.setitem(sys.modules, "requests", module)
    return calls


@pytest.fixture()
def max_env(monkeypatch):
    monkeypatch.setenv("MAX_STUDIO_API_KEY", "test-max-key")
    monkeypatch.setenv("MAX_STUDIO_COOKIE", "test-session-cookie")
    monkeypatch.delenv("MAX_STUDIO_BASE_URL", raising=False)
    monkeypatch.delenv("MAX_STUDIO_PROJECT_ID", raising=False)


def _created(task_id, *, amount=1.0, balance=99.0):
    return FakeResponse(
        {
            "code": 200,
            "status": "pending",
            "taskid": task_id,
            "amount": amount,
            "balance": balance,
        }
    )


def _completed(task_id, *, media_id="media-1", url=None, amount=1.0, balance=99.0):
    result = {"mediaGenerationId": media_id}
    if url:
        result["fifeUrl"] = url
    return FakeResponse(
        {
            "code": 200,
            "status": "successfully",
            "taskid": task_id,
            "amount": amount,
            "balance": balance,
            "result": result,
        }
    )


def test_provider_is_discovered_and_selector_routable():
    from tools.tool_registry import ToolRegistry
    from tools.video.video_selector import VideoSelector

    registry = ToolRegistry()
    registry.discover()
    tool = registry.get("max_studio_video")

    assert tool is not None
    assert tool.provider == "max_studio"
    assert tool.capability == "video_generation"
    assert set(tool.provider_matrix["reference_to_video"]) == {
        "Omni_Flash",
        "Veo_3.1-Lite",
        "Veo_3.1-Lite_Lower_Priority",
        "Veo_3.1-Fast",
    }
    assert "max_studio_video" in [provider.name for provider in VideoSelector()._providers()]


def test_status_requires_both_secrets(monkeypatch):
    from tools.video.max_studio_video import MaxStudioVideo

    monkeypatch.delenv("MAX_STUDIO_API_KEY", raising=False)
    monkeypatch.delenv("MAX_STUDIO_COOKIE", raising=False)
    assert MaxStudioVideo().get_status() == ToolStatus.UNAVAILABLE

    monkeypatch.setenv("MAX_STUDIO_API_KEY", "key")
    assert MaxStudioVideo().get_status() == ToolStatus.UNAVAILABLE

    monkeypatch.setenv("MAX_STUDIO_COOKIE", "cookie")
    assert MaxStudioVideo().get_status() == ToolStatus.AVAILABLE


def test_text_to_video_submits_polls_downloads_and_reports_credits(
    monkeypatch, tmp_path, max_env
):
    from tools.video.max_studio_video import MaxStudioVideo

    calls = _fake_requests(
        monkeypatch,
        posts=[_created("task-video", amount=2.5, balance=47.5)],
        gets=[
            _completed(
                "task-video",
                media_id="video-media",
                url="https://cdn.example/video.mp4",
                amount=2.5,
                balance=47.5,
            ),
            FakeResponse(content=b"fake mp4 bytes"),
        ],
    )
    output = tmp_path / "result.mp4"
    result = MaxStudioVideo().execute(
        {
            "prompt": "A slow cinematic orbit around a glass sculpture.",
            "model_name": "Omni_Flash",
            "duration": "4s",
            "aspect_ratio": "9:16",
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    assert output.read_bytes() == b"fake mp4 bytes"
    payload = calls["post"][0]["json"]
    assert calls["post"][0]["url"].endswith("/api/v3/create-task/text-to-video")
    assert calls["post"][0]["headers"]["X-API-Key"] == "test-max-key"
    assert payload["cookie"] == "test-session-cookie"
    assert payload["model"] == "Omni_Flash"
    assert payload["length"] == 4
    assert payload["ratio"] == "9:16"
    assert result.data["provider_amount_credits"] == 2.5
    assert result.data["provider_balance_credits"] == 47.5
    assert result.data["task_id"] == "task-video"
    assert "cookie" not in json.dumps(result.data).lower()


def test_image_to_video_uploads_local_image_then_uses_media_id(
    monkeypatch, tmp_path, max_env
):
    from tools.video.max_studio_video import MaxStudioVideo

    image = tmp_path / "reference.png"
    image.write_bytes(b"png image")
    calls = _fake_requests(
        monkeypatch,
        posts=[_created("upload-1", amount=0), _created("video-1")],
        gets=[
            _completed("upload-1", media_id="image-media", amount=0, url=None),
            _completed("video-1", url="https://cdn.example/i2v.mp4"),
            FakeResponse(content=b"i2v mp4"),
        ],
    )
    result = MaxStudioVideo().execute(
        {
            "prompt": "Natural wind moves the fabric.",
            "operation": "image_to_video",
            "model": "Veo_3.1-Fast",
            "reference_image_path": str(image),
            "output_path": str(tmp_path / "i2v.mp4"),
        }
    )

    assert result.success, result.error
    upload = calls["post"][0]
    generation = calls["post"][1]
    assert upload["url"].endswith("/api/v3/create-task/upload-image")
    assert upload["json"]["imageUrl"].startswith("data:image/png;base64,")
    assert generation["url"].endswith("/api/v3/create-task/image-to-video")
    assert generation["json"]["mediaId"] == "image-media"


def test_reference_images_upload_in_order(monkeypatch, tmp_path, max_env):
    from tools.video.max_studio_video import MaxStudioVideo

    first = tmp_path / "one.jpg"
    second = tmp_path / "two.png"
    first.write_bytes(b"jpg")
    second.write_bytes(b"png")
    calls = _fake_requests(
        monkeypatch,
        posts=[_created("up-1", amount=0), _created("up-2", amount=0), _created("gen")],
        gets=[
            _completed("up-1", media_id="media-a", amount=0),
            _completed("up-2", media_id="media-b", amount=0),
            _completed("gen", url="https://cdn.example/ref.mp4"),
            FakeResponse(content=b"reference mp4"),
        ],
    )
    result = MaxStudioVideo().execute(
        {
            "prompt": "Keep both subjects consistent in one shot.",
            "operation": "reference_to_video",
            "model": "Omni_Flash",
            "reference_image_paths": [str(first), str(second)],
            "output_path": str(tmp_path / "reference.mp4"),
        }
    )

    assert result.success, result.error
    payload = calls["post"][2]["json"]
    assert payload["mediaId"] == ["media-a", "media-b"]
    assert payload["audio"] is True


def test_quality_model_is_rejected_for_reference_workflow(max_env):
    from tools.video.max_studio_video import MaxStudioVideo

    result = MaxStudioVideo().execute(
        {
            "prompt": "x",
            "operation": "reference_to_video",
            "model": "Veo_3.1-Quality",
            "reference_image_urls": ["https://example.com/a.png"],
        }
    )
    assert not result.success
    assert "not documented" in result.error


def test_edit_video_uses_documented_v3_fields(monkeypatch, tmp_path, max_env):
    from tools.video.max_studio_video import MaxStudioVideo

    calls = _fake_requests(
        monkeypatch,
        posts=[_created("edit-1")],
        gets=[
            _completed("edit-1", url="https://cdn.example/edit.mp4"),
            FakeResponse(content=b"edit mp4"),
        ],
    )
    result = MaxStudioVideo().execute(
        {
            "prompt": "Change the sky to sunset.",
            "operation": "edit_video",
            "model": "Omni_Flash",
            "media_id": "source-video",
            "duration": 8,
            "paygate_tier": "default",
            "output_path": str(tmp_path / "edit.mp4"),
        }
    )

    assert result.success, result.error
    payload = calls["post"][0]["json"]
    assert calls["post"][0]["url"].endswith("/api/v3/create-task/edit-video")
    assert payload["media_id"] == "source-video"
    assert payload["video_length"] == 8
    assert payload["video_model_key"] == "Omni_Flash"


def test_api_errors_redact_key_and_cookie(monkeypatch, max_env):
    from tools.video.max_studio_video import MaxStudioVideo

    _fake_requests(
        monkeypatch,
        posts=[
            FakeResponse(
                {
                    "code": 401,
                    "messages": "bad test-max-key and test-session-cookie",
                    "error_category": "auth",
                },
                status_code=401,
            )
        ],
    )
    result = MaxStudioVideo().execute({"prompt": "x"})

    assert not result.success
    assert "test-max-key" not in result.error
    assert "test-session-cookie" not in result.error
    assert result.error.count("[REDACTED]") == 2


def test_ambiguous_submission_is_not_retried(monkeypatch, max_env):
    from tools.video.max_studio_video import MaxStudioVideo

    calls = _fake_requests(monkeypatch, posts=[RuntimeError("connection reset")])
    result = MaxStudioVideo().execute({"prompt": "x"})

    assert not result.success
    assert "ambiguous transport failure" in result.error
    assert len(calls["post"]) == 1


def test_poll_timeout_preserves_task_id(monkeypatch, max_env):
    from tools import max_studio_client

    monkeypatch.setattr(max_studio_client.time, "sleep", lambda _seconds: None)
    _fake_requests(
        monkeypatch,
        gets=[FakeResponse({"code": 200, "status": "pending", "taskid": "slow-1"})],
    )

    with pytest.raises(max_studio_client.MaxStudioError, match="slow-1"):
        max_studio_client.poll_task(
            "slow-1",
            api_key="test-max-key",
            cookie="test-session-cookie",
            interval=1,
            timeout=0,
        )
