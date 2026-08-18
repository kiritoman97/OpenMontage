from pathlib import Path

from tools.base_tool import ToolStatus
from tools.video.capcut_mate import CapCutMate, PINNED_COMMIT


def test_capcut_mate_contract_is_local_and_no_cloud_render():
    tool = CapCutMate()
    info = tool.get_info()
    assert info["provider"] == "capcut"
    assert info["capability"] == "video_post"
    assert info["supports"]["local_only"] is True
    assert info["supports"]["cloud_render"] is False
    assert "gen_video" not in tool.input_schema["properties"]["operation"]["enum"]
    assert "add_filter" in tool.input_schema["properties"]["operation"]["enum"]
    assert "capcut_add_filters" in info["capabilities"]


def test_add_filter_posts_capcut_mate_filter_payload(monkeypatch):
    tool = CapCutMate()
    captured = {}

    def fake_request(method, path, payload=None, **kwargs):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"code": 0, "filter_ids": ["filter-1"]}

    monkeypatch.setattr(tool, "_request", fake_request)
    result = tool.execute({
        "operation": "add_filter",
        "draft_url": "http://127.0.0.1:30000/openapi/capcut-mate/v1/get_draft?draft_id=probe",
        "filters": [{
            "filter_title": "纪实电影胶片",
            "start": 0,
            "end": 30_000_000,
            "intensity": 25,
        }],
    })

    assert result.success is True
    assert captured["method"] == "POST"
    assert captured["path"] == "/openapi/capcut-mate/v1/add_filters"
    assert captured["payload"]["draft_url"].endswith("draft_id=probe")
    import json

    assert json.loads(captured["payload"]["filter_infos"]) == [{
        "filter_title": "纪实电影胶片",
        "start": 0,
        "end": 30_000_000,
        "intensity": 25,
    }]


def test_local_url_rejects_media_outside_repo(tmp_path):
    path = tmp_path / "outside.mp4"
    path.write_bytes(b"probe")
    tool = CapCutMate()
    try:
        tool._local_url(str(path))
    except ValueError as exc:
        assert "Media must be staged" in str(exc)
    else:
        raise AssertionError("outside media should be rejected")


def test_pinned_commit_is_full_sha():
    assert len(PINNED_COMMIT) == 40
    assert all(ch in "0123456789abcdef" for ch in PINNED_COMMIT)


def test_status_is_not_available_without_both_runtime_and_app(monkeypatch, tmp_path):
    tool = CapCutMate()
    monkeypatch.setattr(CapCutMate, "runtime_home", property(lambda self: tmp_path / "missing"))
    monkeypatch.setattr(CapCutMate, "capcut_executable", property(lambda self: tmp_path / "CapCut.exe"))
    assert tool.get_status() == ToolStatus.UNAVAILABLE


def test_frame_alignment_removes_decimal_boundary_overlap():
    first_start, first_duration = CapCutMate._frame_aligned_interval(329.4667, 16.4667, 30)
    second_start, _ = CapCutMate._frame_aligned_interval(345.9333, 3.4997, 30)
    assert round((first_start + first_duration) * 1_000_000) == round(second_start * 1_000_000)


def test_rebase_draft_paths_makes_copy_self_contained(tmp_path):
    old_root = tmp_path / "runtime" / "draft-1"
    new_root = tmp_path / "package" / "draft-1"
    new_root.mkdir(parents=True)
    import json

    for filename in ("draft_content.json", "draft_info.json"):
        (new_root / filename).write_text(
            json.dumps({"path": str(old_root / "assets" / "clip.mp4")}), encoding="utf-8"
        )
    CapCutMate()._rebase_draft_paths(new_root, old_root, new_root)
    for filename in ("draft_content.json", "draft_info.json"):
        payload = json.loads((new_root / filename).read_text(encoding="utf-8"))
        assert payload["path"].startswith(str(new_root))
        assert not payload["path"].startswith(str(old_root))


def test_cover_scale_for_portrait_and_wide_images(monkeypatch):
    class Completed:
        stdout = '{"streams":[{"width":750,"height":1000}]}'

    monkeypatch.setattr("tools.video.capcut_mate.subprocess.run", lambda *args, **kwargs: Completed())
    assert CapCutMate._cover_scale("portrait.jpg", 1920, 1080) == (1920 / 1080) / 0.75

    Completed.stdout = '{"streams":[{"width":2400,"height":1000}]}'
    assert CapCutMate._cover_scale("wide.jpg", 1920, 1080) == 2.4 / (1920 / 1080)
