"""Local CapCut Mate adapter for editable CapCut International drafts.

The upstream service is deliberately kept outside the source tree under
``.runtime/capcut-mate``.  This tool provides the OpenMontage contract,
starts both services on loopback only, and never calls CapCut Mate's cloud
rendering endpoints.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ResumeSupport,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_COMMIT = "dc4b342302926bce744b7e823138e62a79035603"
DEFAULT_BASE_URL = "http://127.0.0.1:30000"
DEFAULT_MEDIA_URL = "http://127.0.0.1:3012"


def _windows_creation_flags(hidden: bool = True) -> int:
    if os.name != "nt":
        return 0
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if hidden:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return flags


class CapCutMate(BaseTool):
    name = "capcut_mate"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "capcut"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    capabilities = [
        "capcut_doctor",
        "capcut_service_control",
        "capcut_create_draft",
        "capcut_add_media",
        "capcut_add_audio",
        "capcut_add_native_captions",
        "capcut_add_filters",
        "capcut_add_effects",
        "capcut_add_keyframes",
        "capcut_save_draft",
        "capcut_install_draft",
        "capcut_open_editor",
    ]
    supports = {
        "local_only": True,
        "cloud_render": False,
        "native_subtitles": True,
        "editable_project": True,
        "media_server_loopback_only": True,
    }
    best_for = [
        "Editable long-form timelines that need manual finishing in CapCut",
        "Native captions, still-image motion, transitions, and keyframes",
        "Exporting OpenMontage edit manifests to a desktop NLE project",
    ]
    not_good_for = [
        "Final color grading; use Resolve after picture lock",
        "Headless final rendering; local cloud-render endpoints are disabled",
    ]
    install_instructions = (
        "Install CapCut International with 'winget install ByteDance.CapCut', "
        "clone Hommy-master/capcut-mate into .runtime/capcut-mate at commit "
        f"{PINNED_COMMIT}, then run 'uv sync' and 'uv pip install -e .[windows]'."
    )
    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "doctor", "start", "stop", "create_draft", "add_media",
                    "add_audio", "add_captions", "add_transition", "add_effect",
                    "add_filter", "add_keyframes", "save_draft", "install_draft", "open_project",
                    "build_from_manifest",
                ],
            },
            "draft_url": {"type": "string"},
            "draft_id": {"type": "string"},
            "width": {"type": "integer", "default": 1920},
            "height": {"type": "integer", "default": 1080},
            "items": {"type": "array", "items": {"type": "object"}},
            "captions": {"type": "array", "items": {"type": "object"}},
            "effects": {"type": "array", "items": {"type": "object"}},
            "filters": {"type": "array", "items": {"type": "object"}},
            "keyframes": {"type": "array", "items": {"type": "object"}},
            "payload": {"type": "object"},
            "project_name": {"type": "string"},
            "project_dir": {"type": "string"},
            "manifest_path": {"type": "string"},
            "max_duration_seconds": {"type": "number"},
            "install": {"type": "boolean", "default": True},
            "open": {"type": "boolean", "default": False},
            "timeout_seconds": {"type": "number", "default": 120},
        },
    }
    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=1024, vram_mb=0, disk_mb=4096, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=2, backoff_seconds=1.0, retryable_errors=["timeout"])
    resume_support = ResumeSupport.FROM_CHECKPOINT
    idempotency_key_fields = ["operation", "draft_id", "project_name"]
    side_effects = [
        "starts loopback-only local processes",
        "writes CapCut draft files",
        "copies draft into CapCut's local project directory",
        "may launch the CapCut desktop application",
    ]
    user_visible_verification = [
        "Open the installed draft in CapCut and verify media, captions, timing, and keyframes",
    ]

    @property
    def runtime_home(self) -> Path:
        configured = os.environ.get("CAPCUT_MATE_HOME", ".runtime/capcut-mate")
        path = Path(configured)
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def base_url(self) -> str:
        return os.environ.get("CAPCUT_MATE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    @property
    def media_url(self) -> str:
        return os.environ.get("CAPCUT_MATE_MEDIA_URL", DEFAULT_MEDIA_URL).rstrip("/")

    @property
    def runtime_python(self) -> Path:
        if os.name == "nt":
            return self.runtime_home / ".venv" / "Scripts" / "python.exe"
        return self.runtime_home / ".venv" / "bin" / "python"

    @property
    def capcut_executable(self) -> Path:
        configured = os.environ.get("CAPCUT_EXE")
        if configured:
            return Path(configured)
        return Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps" / "CapCut.exe"

    @property
    def capcut_draft_dir(self) -> Path:
        configured = os.environ.get("CAPCUT_DRAFT_DIR")
        if configured:
            return Path(configured)
        return (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        )

    def get_status(self) -> ToolStatus:
        if self.runtime_python.is_file() and self.capcut_executable.is_file():
            return ToolStatus.AVAILABLE
        if self.runtime_home.is_dir() or self.capcut_executable.is_file():
            return ToolStatus.DEGRADED
        return ToolStatus.UNAVAILABLE

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        operation = inputs.get("operation")
        try:
            if operation == "doctor":
                data = self._doctor()
            elif operation == "start":
                data = self._start_services()
            elif operation == "stop":
                data = self._stop_services()
            elif operation == "create_draft":
                data = self._request("POST", "/openapi/capcut-mate/v1/create_draft", {
                    "width": int(inputs.get("width", 1920)),
                    "height": int(inputs.get("height", 1080)),
                }, timeout=float(inputs.get("timeout_seconds", 120)))
            elif operation == "add_media":
                data = self._add_media(inputs)
            elif operation == "add_audio":
                data = self._add_audio(inputs)
            elif operation == "add_captions":
                data = self._add_captions(inputs)
            elif operation == "add_transition":
                data = self._add_transition(inputs)
            elif operation == "add_effect":
                data = self._post_json_string(inputs, "effects", "effect_infos", "add_effects")
            elif operation == "add_filter":
                data = self._post_json_string(inputs, "filters", "filter_infos", "add_filters")
            elif operation == "add_keyframes":
                data = self._post_json_string(inputs, "keyframes", "keyframes", "add_keyframes")
            elif operation == "save_draft":
                data = self._request("POST", "/openapi/capcut-mate/v1/save_draft", {
                    "draft_url": self._require(inputs, "draft_url")
                })
            elif operation == "install_draft":
                data = self._install_draft(inputs)
            elif operation == "open_project":
                data = self._open_project(inputs)
            elif operation == "build_from_manifest":
                data = self._build_from_manifest(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
            return ToolResult(
                success=True,
                data=data,
                artifacts=[p for p in data.get("artifacts", []) if p],
                duration_seconds=round(time.time() - started, 2),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                duration_seconds=round(time.time() - started, 2),
            )

    def _doctor(self) -> dict[str, Any]:
        commit = None
        if (self.runtime_home / ".git").exists():
            proc = subprocess.run(
                ["git", "-C", str(self.runtime_home), "rev-parse", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc.returncode == 0:
                commit = proc.stdout.strip()
        service = self._healthy(self.base_url + "/openapi.json")
        media = self._healthy(self.media_url + "/")
        return {
            "status": self.get_status().value,
            "runtime_home": str(self.runtime_home),
            "runtime_python": str(self.runtime_python),
            "runtime_commit": commit,
            "pinned_commit": PINNED_COMMIT,
            "commit_matches": commit == PINNED_COMMIT,
            "capcut_executable": str(self.capcut_executable),
            "capcut_installed": self.capcut_executable.is_file(),
            "capcut_draft_dir": str(self.capcut_draft_dir),
            "service_url": self.base_url,
            "service_healthy": service,
            "media_url": self.media_url,
            "media_server_healthy": media,
            "cloud_render_enabled": False,
        }

    def _start_services(self) -> dict[str, Any]:
        if not self.runtime_python.is_file():
            raise FileNotFoundError(f"CapCut Mate runtime missing: {self.runtime_python}")
        self._start_process(
            "capcut-mate",
            [
                str(self.runtime_python), "-m", "uvicorn", "main:app",
                "--host", "127.0.0.1", "--port", "30000", "--log-level", "warning",
            ],
            cwd=self.runtime_home,
            env={
                "DRAFT_URL": self.base_url + "/openapi/capcut-mate/v1/get_draft",
                "DOWNLOAD_URL": self.base_url,
                "DOWNLOAD_FILE_SIZE_LIMIT": os.environ.get(
                    "CAPCUT_MATE_DOWNLOAD_LIMIT", "2147483648"
                ),
                "ENABLE_APIKEY": "false",
            },
            health_url=self.base_url + "/openapi.json",
        )
        self._start_process(
            "capcut-media",
            [
                sys.executable, "-m", "http.server", "3012", "--bind", "127.0.0.1",
                "--directory", str(REPO_ROOT),
            ],
            cwd=REPO_ROOT,
            env={},
            health_url=self.media_url + "/",
        )
        return self._doctor()

    def _stop_services(self) -> dict[str, Any]:
        stopped = []
        for name in ("capcut-mate", "capcut-media"):
            pid_file = self.runtime_home / f".{name}.pid"
            if not pid_file.exists():
                continue
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True, check=False,
                    )
                else:
                    os.kill(pid, 15)
                stopped.append(pid)
            finally:
                pid_file.unlink(missing_ok=True)
        return {"stopped_pids": stopped}

    def _start_process(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        health_url: str,
    ) -> None:
        if self._healthy(health_url):
            return
        full_env = os.environ.copy()
        full_env.update(env)
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=full_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_windows_creation_flags(hidden=True),
        )
        (self.runtime_home / f".{name}.pid").write_text(str(process.pid), encoding="utf-8")
        deadline = time.time() + 25
        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with code {process.returncode}")
            if self._healthy(health_url):
                return
            time.sleep(0.4)
        raise TimeoutError(f"{name} did not become healthy: {health_url}")

    @staticmethod
    def _healthy(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 120,
    ) -> dict[str, Any]:
        if not self._healthy(self.base_url + "/openapi.json"):
            self._start_services()
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept-Language": "en"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"CapCut Mate HTTP {exc.code}: {detail}") from exc
        code = result.get("code", 0)
        if code not in (0, 200, "0", "200"):
            raise RuntimeError(f"CapCut Mate error {code}: {result.get('message', result)}")
        return result

    def _local_url(self, raw_path: str) -> str:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            relative = path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise ValueError(f"Media must be staged inside {REPO_ROOT}: {path}") from exc
        encoded = "/".join(urllib.parse.quote(part) for part in relative.parts)
        return f"{self.media_url}/{encoded}"

    def _add_media(self, inputs: dict[str, Any]) -> dict[str, Any]:
        draft_url = self._require(inputs, "draft_url")
        items = inputs.get("items") or []
        if not items:
            raise ValueError("items is required")
        kinds = {str(item.get("kind", "video")) for item in items}
        if len(kinds) != 1:
            raise ValueError("add_media requires one media kind per call")
        kind = kinds.pop()
        if kind not in {"video", "image"}:
            raise ValueError(f"Unsupported media kind: {kind}")
        info_key = "video_infos" if kind == "video" else "image_infos"
        endpoint = "add_videos" if kind == "video" else "add_images"
        prepared = []
        for item in items:
            start = int(item["start"])
            end = int(item["end"])
            record = {
                f"{kind}_url": self._local_url(str(item["path"])),
                "start": start,
                "end": end,
                "duration": int(item.get("duration", end - start)),
            }
            for key in ("transition", "transition_duration", "mask", "volume"):
                if item.get(key) is not None:
                    record[key] = item[key]
            prepared.append(record)
        payload = {
            "draft_url": draft_url,
            info_key: json.dumps(prepared, ensure_ascii=False),
            "alpha": float(inputs.get("alpha", 1.0)),
            "scale_x": float(inputs.get("scale_x", 1.0)),
            "scale_y": float(inputs.get("scale_y", 1.0)),
            "transform_x": int(inputs.get("transform_x", 0)),
            "transform_y": int(inputs.get("transform_y", 0)),
        }
        if kind == "video" and inputs.get("scene_timelines"):
            payload["scene_timelines"] = inputs["scene_timelines"]
        return self._request(
            "POST", f"/openapi/capcut-mate/v1/{endpoint}", payload,
            timeout=float(inputs.get("timeout_seconds", 600)),
        )

    def _add_audio(self, inputs: dict[str, Any]) -> dict[str, Any]:
        items = inputs.get("items") or []
        prepared = []
        for item in items:
            start, end = int(item["start"]), int(item["end"])
            record = {
                "audio_url": self._local_url(str(item["path"])),
                "start": start,
                "end": end,
                "duration": int(item.get("duration", end - start)),
            }
            for key in ("volume", "fade_in", "fade_out"):
                if item.get(key) is not None:
                    record[key] = item[key]
            prepared.append(record)
        return self._request("POST", "/openapi/capcut-mate/v1/add_audios", {
            "draft_url": self._require(inputs, "draft_url"),
            "audio_infos": json.dumps(prepared, ensure_ascii=False),
        }, timeout=float(inputs.get("timeout_seconds", 600)))

    def _add_captions(self, inputs: dict[str, Any]) -> dict[str, Any]:
        captions = inputs.get("captions") or []
        payload = {
            "draft_url": self._require(inputs, "draft_url"),
            "captions": json.dumps(captions, ensure_ascii=False),
            "text_color": inputs.get("text_color", "#F4F1EA"),
            "border_color": inputs.get("border_color", "#070605"),
            "font_size": int(inputs.get("font_size", 6)),
            "alignment": int(inputs.get("alignment", 1)),
            "bold": bool(inputs.get("bold", True)),
            "has_shadow": bool(inputs.get("has_shadow", False)),
            "transform_x": float(inputs.get("transform_x", 0.0)),
            "transform_y": float(inputs.get("transform_y", -760)),
        }
        return self._request(
            "POST", "/openapi/capcut-mate/v1/add_captions", payload,
            timeout=float(inputs.get("timeout_seconds", 600)),
        )

    def _add_transition(self, inputs: dict[str, Any]) -> dict[str, Any]:
        items = inputs.get("items") or []
        if not items:
            raise ValueError(
                "CapCut Mate applies transitions while adding media; provide items "
                "with transition and transition_duration via add_media."
            )
        return self._add_media(inputs)

    def _post_json_string(
        self,
        inputs: dict[str, Any],
        input_key: str,
        api_key: str,
        endpoint: str,
    ) -> dict[str, Any]:
        values = inputs.get(input_key) or []
        return self._request("POST", f"/openapi/capcut-mate/v1/{endpoint}", {
            "draft_url": self._require(inputs, "draft_url"),
            api_key: json.dumps(values, ensure_ascii=False),
        })

    def _install_draft(self, inputs: dict[str, Any]) -> dict[str, Any]:
        draft_id = inputs.get("draft_id") or self._draft_id(inputs.get("draft_url", ""))
        if not draft_id:
            raise ValueError("draft_id or draft_url is required")
        source = self.runtime_home / "output" / "draft" / draft_id
        if not source.is_dir():
            raise FileNotFoundError(source)
        project_name = str(inputs.get("project_name") or draft_id).strip()
        safe_name = "".join(c if c not in '<>:"/\\|?*' else "_" for c in project_name)
        destination = self.capcut_draft_dir / safe_name
        if destination.exists():
            raise FileExistsError(f"CapCut draft already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        self._rebase_draft_paths(destination, source, destination)
        self._rewrite_meta(destination, safe_name)
        project_dir = inputs.get("project_dir")
        artifacts = [str(destination)]
        if project_dir:
            package = Path(project_dir) / "capcut" / safe_name
            package.parent.mkdir(parents=True, exist_ok=True)
            if package.exists():
                shutil.rmtree(package)
            shutil.copytree(destination, package)
            self._rebase_draft_paths(package, destination, package)
            self._rewrite_meta(package, safe_name, root=package.parent)
            artifacts.append(str(package))
        return {
            "draft_id": draft_id,
            "project_name": safe_name,
            "installed_path": str(destination),
            "artifacts": artifacts,
        }

    def _rewrite_meta(
        self, draft_dir: Path, project_name: str, root: Path | None = None
    ) -> None:
        meta_path = draft_dir / "draft_meta_info.json"
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        draft_root = (root or self.capcut_draft_dir).as_posix()
        meta.update({
            "draft_name": project_name,
            "draft_fold_path": draft_dir.as_posix(),
            "draft_root_path": draft_root,
        })
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def _rebase_draft_paths(self, draft_dir: Path, old_root: Path, new_root: Path) -> None:
        """Make a copied draft self-contained by rebasing absolute media paths."""
        old_windows = str(old_root.resolve())
        new_windows = str(new_root.resolve())
        old_posix = old_root.resolve().as_posix()
        new_posix = new_root.resolve().as_posix()

        def rewrite(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace(old_windows, new_windows).replace(old_posix, new_posix)
            if isinstance(value, list):
                return [rewrite(item) for item in value]
            if isinstance(value, dict):
                return {key: rewrite(item) for key, item in value.items()}
            return value

        filenames = {
            "draft_content.json", "draft_info.json", "draft_content.json.bak",
            "template-2.tmp", "mini_draft.json",
        }
        for path in draft_dir.rglob("*"):
            if not path.is_file() or path.name not in filenames:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            path.write_text(
                json.dumps(rewrite(payload), ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

    def _open_project(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if not self.capcut_executable.is_file():
            raise FileNotFoundError(self.capcut_executable)
        process = subprocess.Popen(
            [str(self.capcut_executable)],
            cwd=str(self.capcut_executable.parent),
            creationflags=_windows_creation_flags(hidden=False),
        )
        return {
            "pid": process.pid,
            "project_name": inputs.get("project_name"),
            "instruction": "Select the named local project in CapCut's project list.",
        }

    def _build_from_manifest(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Translate a runtime-neutral edit manifest into an editable draft."""
        manifest_path = Path(self._require(inputs, "manifest_path")).resolve()
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        canvas = manifest["canvas"]
        limit = float(inputs.get("max_duration_seconds") or manifest["durationSeconds"])
        project_name = str(inputs.get("project_name") or manifest["title"])
        created = self._request("POST", "/openapi/capcut-mate/v1/create_draft", {
            "width": int(canvas["width"]), "height": int(canvas["height"]),
        })
        draft_url = created["draft_url"]
        draft_id = self._draft_id(draft_url)
        if not draft_id:
            raise RuntimeError(f"Cannot parse draft id from {draft_url}")

        visual_items: dict[str, list[dict[str, Any]]] = {"video": [], "image": []}
        source_patches: dict[str, tuple[int, int]] = {}
        scene_records: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        fps = float(canvas["fps"])
        for scene in manifest["scenes"]:
            start = float(scene["timelineStartSeconds"])
            if start >= limit:
                continue
            duration = min(float(scene["timelineDurationSeconds"]), limit - start)
            # CapCut rejects even a 100 microsecond overlap.  The neutral
            # manifest stores decimal seconds rounded to four places, so two
            # adjacent 30 fps scenes can otherwise quantize to slightly
            # different boundaries (for example 345.9334 vs 345.9333).
            # Snap both edges through frame numbers before creating segments.
            start, duration = self._frame_aligned_interval(start, duration, fps)
            expanded = self._expand_scene(scene, start, duration)
            visual_items[scene["kind"]].extend(expanded)
            scene_records.append((scene, expanded))

        media_results: dict[str, dict[str, Any]] = {}
        segment_by_token: dict[str, str] = {}
        for kind in ("video", "image"):
            items = visual_items[kind]
            if not items:
                continue
            result = self._add_media({
                "draft_url": draft_url,
                "items": items,
                "timeout_seconds": inputs.get("timeout_seconds", 1800),
            })
            media_results[kind] = result
            for item, segment_id in zip(items, result.get("segment_ids", [])):
                segment_by_token[item["token"]] = segment_id
                if kind == "video":
                    source_patches[segment_id] = (
                        int(item.get("source_start", 0)), int(item["end"] - item["start"])
                    )

        keyframes = []
        for scene, expanded in scene_records:
            if scene["kind"] != "image" or not expanded:
                continue
            segment_id = segment_by_token.get(expanded[0]["token"])
            if not segment_id:
                continue
            amount = float(scene.get("motionAmount", 0.05))
            motion = scene.get("motion", "zoom-in")
            cover_scale = self._cover_scale(
                scene["assetPath"], int(canvas["width"]), int(canvas["height"])
            )
            start_scale, end_scale = (
                (cover_scale * (1.0 + amount), cover_scale)
                if motion == "zoom-out"
                else (cover_scale, cover_scale * (1.0 + amount))
            )
            end_offset = int(expanded[0]["duration"])
            keyframes.extend([
                {"segment_id": segment_id, "property": "KFTypeScaleX", "offset": 0.0, "value": start_scale},
                {"segment_id": segment_id, "property": "KFTypeScaleY", "offset": 0.0, "value": start_scale},
                # CapCut Mate commit dc4b342 documents 0-1 offsets but its
                # service actually divides the supplied value by the segment
                # duration.  Supplying duration_us is the compatible way to
                # place the final keyframe at the clip end.
                {"segment_id": segment_id, "property": "KFTypeScaleX", "offset": end_offset, "value": end_scale},
                {"segment_id": segment_id, "property": "KFTypeScaleY", "offset": end_offset, "value": end_scale},
            ])
        keyframe_result = None
        if keyframes:
            keyframe_result = self._post_json_string(
                {"draft_url": draft_url, "keyframes": keyframes},
                "keyframes", "keyframes", "add_keyframes",
            )

        narration = manifest["audio"]["narration"]
        narration_end = min(limit, float(narration["durationSeconds"]))
        narration_result = self._add_audio({
            "draft_url": draft_url,
            "items": [{
                "path": narration["path"], "start": 0, "end": self._us(narration_end),
                "duration": self._us(narration_end), "volume": narration.get("volume", 1.0),
            }],
            "timeout_seconds": inputs.get("timeout_seconds", 1800),
        })
        music = manifest["audio"]["music"]
        music_items = []
        cursor = 0.0
        source_duration = float(music["sourceDurationSeconds"])
        while cursor < limit - 1 / float(canvas["fps"]):
            length = min(source_duration, limit - cursor)
            music_items.append({
                "path": music["path"], "start": self._us(cursor),
                "end": self._us(cursor + length), "duration": self._us(length),
                "volume": music.get("volume", 0.12),
            })
            cursor += length
        music_result = self._add_audio({
            "draft_url": draft_url, "items": music_items,
            "timeout_seconds": inputs.get("timeout_seconds", 1800),
        })

        subtitle_data = manifest["subtitles"]
        captions = [
            {"start": self._us(c["startSeconds"]), "end": self._us(min(c["endSeconds"], limit)), "text": c["text"]}
            for c in subtitle_data["cues"] if float(c["startSeconds"]) < limit
        ]
        style = subtitle_data["style"]
        caption_result = self._add_captions({
            "draft_url": draft_url, "captions": captions,
            "text_color": style["color"], "border_color": style["borderColor"],
            "font_size": style["fontSize"], "bold": style["bold"],
            "has_shadow": False, "transform_y": style["verticalPositionPx"],
            "timeout_seconds": inputs.get("timeout_seconds", 1800),
        })
        labels = [
            {"start": self._us(x["startSeconds"]), "end": self._us(min(x["endSeconds"], limit)), "text": x["text"]}
            for x in manifest.get("labels", []) if float(x["startSeconds"]) < limit
        ]
        label_result = None
        if labels:
            label_result = self._add_captions({
                "draft_url": draft_url, "captions": labels,
                "text_color": "#E8D5A9", "border_color": "#070605",
                "font_size": 4, "bold": True, "has_shadow": False,
                "transform_x": -672, "transform_y": 760,
                "timeout_seconds": inputs.get("timeout_seconds", 1800),
            })
        self._request("POST", "/openapi/capcut-mate/v1/save_draft", {"draft_url": draft_url})
        self._patch_source_ranges(draft_id, source_patches)

        installed = None
        if inputs.get("install", True):
            installed = self._install_draft({
                "draft_id": draft_id, "project_name": project_name,
                "project_dir": inputs.get("project_dir"),
            })
        opened = None
        if inputs.get("open", False):
            opened = self._open_project({"project_name": project_name})
        return {
            "draft_id": draft_id,
            "draft_url": draft_url,
            "project_name": project_name,
            "duration_seconds": limit,
            "scene_count": len(scene_records),
            "video_segment_count": len(visual_items["video"]),
            "image_segment_count": len(visual_items["image"]),
            "native_caption_count": len(captions),
            "editorial_label_count": len(labels),
            "keyframe_count": len(keyframes),
            "source_trim_patch_count": len(source_patches),
            "review_audio": manifest.get("audioStatus"),
            "media_results": media_results,
            "keyframe_result": keyframe_result,
            "narration_result": narration_result,
            "music_result": music_result,
            "caption_result": caption_result,
            "label_result": label_result,
            "installed": installed,
            "opened": opened,
            "artifacts": (installed or {}).get("artifacts", []),
        }

    def _expand_scene(
        self, scene: dict[str, Any], start_seconds: float, duration_seconds: float
    ) -> list[dict[str, Any]]:
        if scene["kind"] == "image":
            return [{
                "token": f"{scene['id']}:0", "kind": "image", "path": scene["assetPath"],
                "start": self._us(start_seconds), "end": self._us(start_seconds + duration_seconds),
                "duration": self._us(duration_seconds),
                "transition": "叠化" if scene.get("transition") == "dissolve" else None,
                "transition_duration": self._frames_to_us(scene.get("transitionFrames", 0), 30),
            }]
        source_start = float(scene.get("sourceStartSeconds") or 0)
        source_end = float(scene.get("sourceEndSeconds") or scene.get("assetDurationSeconds") or 0)
        available = max(1 / 30, source_end - source_start)
        chunks = []
        remaining = duration_seconds
        cursor = start_seconds
        index = 0
        while remaining > 1 / 60:
            length = min(remaining, available) if scene.get("loop") else remaining
            chunks.append({
                "token": f"{scene['id']}:{index}", "kind": "video", "path": scene["assetPath"],
                "start": self._us(cursor), "end": self._us(cursor + length),
                "duration": self._us(length), "source_start": self._us(source_start),
                "volume": 0.0,
            })
            cursor += length
            remaining -= length
            index += 1
            if not scene.get("loop"):
                break
        return chunks

    def _patch_source_ranges(
        self, draft_id: str, patches: dict[str, tuple[int, int]]
    ) -> None:
        if not patches:
            return
        draft_dir = self.runtime_home / "output" / "draft" / draft_id
        for filename in ("draft_content.json", "draft_info.json"):
            path = draft_dir / filename
            if not path.exists():
                continue
            content = json.loads(path.read_text(encoding="utf-8"))
            changed = self._patch_segment_tree(content, patches)
            if changed:
                path.write_text(
                    json.dumps(content, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )

    def _patch_segment_tree(
        self, value: Any, patches: dict[str, tuple[int, int]]
    ) -> int:
        changed = 0
        if isinstance(value, dict):
            segment_id = value.get("id")
            if segment_id in patches and isinstance(value.get("source_timerange"), dict):
                start, duration = patches[segment_id]
                value["source_timerange"]["start"] = start
                value["source_timerange"]["duration"] = duration
                changed += 1
            for child in value.values():
                changed += self._patch_segment_tree(child, patches)
        elif isinstance(value, list):
            for child in value:
                changed += self._patch_segment_tree(child, patches)
        return changed

    @staticmethod
    def _us(seconds: float) -> int:
        return int(round(float(seconds) * 1_000_000))

    @staticmethod
    def _frame_aligned_interval(
        start_seconds: float, duration_seconds: float, fps: int | float
    ) -> tuple[float, float]:
        """Return a frame-exact interval so adjacent CapCut segments cannot overlap."""
        rate = float(fps)
        start_frame = round(float(start_seconds) * rate)
        end_frame = round((float(start_seconds) + float(duration_seconds)) * rate)
        return start_frame / rate, max(1.0 / rate, (end_frame - start_frame) / rate)

    @staticmethod
    def _cover_scale(path: str | Path, canvas_width: int, canvas_height: int) -> float:
        """Scale a contain-fitted still until it covers the whole canvas."""
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        stream = json.loads(completed.stdout)["streams"][0]
        image_aspect = float(stream["width"]) / float(stream["height"])
        canvas_aspect = float(canvas_width) / float(canvas_height)
        return max(canvas_aspect / image_aspect, image_aspect / canvas_aspect)

    @staticmethod
    def _frames_to_us(frames: int | float, fps: int | float) -> int:
        return int(round(float(frames) / float(fps) * 1_000_000))

    @staticmethod
    def _require(inputs: dict[str, Any], key: str) -> Any:
        value = inputs.get(key)
        if value in (None, ""):
            raise ValueError(f"{key} is required")
        return value

    @staticmethod
    def _draft_id(draft_url: str) -> str | None:
        return urllib.parse.parse_qs(urllib.parse.urlparse(draft_url).query).get("draft_id", [None])[0]
