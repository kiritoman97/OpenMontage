"""Max Studio V3 video generation for Gemini Omni Flash and Google Veo 3.1."""

from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

from tools import max_studio_client
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

MODELS = (
    "Omni_Flash",
    "Veo_3.1-Lite",
    "Veo_3.1-Lite_Lower_Priority",
    "Veo_3.1-Fast",
    "Veo_3.1-Quality",
)

OPERATIONS = (
    "text_to_video",
    "image_to_video",
    "reference_to_video",
    "first_last_frame_to_video",
    "extend_video",
    "edit_video",
)

ENDPOINTS = {
    "text_to_video": "text-to-video",
    "image_to_video": "image-to-video",
    "reference_to_video": "reference-images-to-video",
    "first_last_frame_to_video": "start-end-image-to-video",
    "extend_video": "extend-video",
    "edit_video": "edit-video",
}

REFERENCE_MODELS = (
    "Omni_Flash",
    "Veo_3.1-Lite",
    "Veo_3.1-Lite_Lower_Priority",
    "Veo_3.1-Fast",
)


class MaxStudioVideo(BaseTool):
    name = "max_studio_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "max_studio"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:MAX_STUDIO_API_KEY", "env:MAX_STUDIO_COOKIE"]
    install_instructions = max_studio_client.INSTALL_INSTRUCTIONS
    agent_skills = ["max-studio-v3", "ai-video-gen", "gemini-omni"]

    capabilities = list(OPERATIONS)
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "first_last_frame_to_video": True,
        "extend_video": True,
        "edit_video": True,
        "multiple_reference_images": True,
        "native_audio": True,
        "custom_duration": True,
        "aspect_ratio": True,
    }
    provider_matrix = {
        "text_to_video": list(MODELS),
        "image_to_video": list(MODELS),
        "reference_to_video": list(REFERENCE_MODELS),
        "first_last_frame_to_video": list(MODELS),
        "extend_video": list(MODELS),
        "edit_video": list(MODELS),
    }
    best_for = [
        "one Max Studio V3 gateway for Omni Flash and Veo 3.1",
        "text, image, multi-reference, first/last-frame, extend, and edit workflows",
    ]
    not_good_for = [
        "offline generation",
        "USD cost prediction because Max Studio reports provider credits, not a conversion rate",
        "long-lived unattended jobs because the Google Labs session cookie can expire",
    ]
    fallback_tools = [
        "gemini_omni_video",
        "gemini_omni_fal",
        "veo_video",
        "atlas_video",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": list(OPERATIONS),
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": list(MODELS),
                "default": "Veo_3.1-Fast",
            },
            "model_name": {
                "type": "string",
                "enum": list(MODELS),
                "description": "Selector-compatible alias for model.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "16:9",
            },
            "duration": {"type": ["integer", "string"], "default": 8},
            "seed": {"type": "integer"},
            "project_id": {"type": "string"},
            "generate_audio": {"type": "boolean", "default": True},
            "image_url": {"type": "string"},
            "image_path": {"type": "string"},
            "reference_image_url": {"type": "string"},
            "reference_image_path": {"type": "string"},
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "first_frame_url": {"type": "string"},
            "first_frame_path": {"type": "string"},
            "last_frame_url": {"type": "string"},
            "last_frame_path": {"type": "string"},
            "video_url": {"type": "string"},
            "video_path": {"type": "string"},
            "media_id": {"type": "string"},
            "paygate_tier": {"type": "string", "default": "default"},
            "start_second": {"type": "number"},
            "end_second": {"type": "number"},
            "poll_interval": {"type": "number", "minimum": 3, "default": 4},
            "poll_timeout": {"type": "number", "minimum": 1, "default": 1200},
            "request_timeout": {"type": "number", "minimum": 1, "default": 60},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1,
        ram_mb=512,
        vram_mb=0,
        disk_mb=1000,
        network_required=True,
    )
    # POST submissions are not safe to retry after an ambiguous response.
    retry_policy = RetryPolicy(max_retries=0, retryable_errors=[])
    idempotency_key_fields = ["prompt", "operation", "model", "aspect_ratio", "seed"]
    side_effects = [
        "creates billable Max Studio tasks",
        "writes a generated video to output_path",
    ]
    user_visible_verification = [
        "Watch the clip for prompt fidelity, motion coherence, and reference consistency",
        "Listen for requested dialogue, ambience, and audio synchronization",
    ]

    def get_status(self) -> ToolStatus:
        if max_studio_client.get_api_key() and max_studio_client.get_cookie():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # The supplied V3 guide exposes actual provider credits after task
        # creation but no USD conversion or preflight pricing table.
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        model = self._model(inputs)
        if model == "Veo_3.1-Lite_Lower_Priority":
            return 300.0
        if model in {"Veo_3.1-Fast", "Omni_Flash"}:
            return 120.0
        return 180.0

    @staticmethod
    def _file_to_data_uri(path_value: str, expected_kind: str) -> str:
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
        mime_type, _ = mimetypes.guess_type(path.name)
        mime_type = mime_type or "application/octet-stream"
        if not mime_type.startswith(f"{expected_kind}/"):
            raise ValueError(f"Expected a {expected_kind} file, got {mime_type}: {path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _remote_or_data(value: str, expected_kind: str) -> str:
        normalized = value.strip()
        if normalized.startswith(("https://", "http://", "data:")):
            return normalized
        return MaxStudioVideo._file_to_data_uri(normalized, expected_kind)

    @staticmethod
    def _task_options(inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "interval": float(inputs.get("poll_interval", 4.0)),
            "timeout": float(inputs.get("poll_timeout", 1200.0)),
            "request_timeout": float(inputs.get("request_timeout", 60.0)),
        }

    @staticmethod
    def _project_id(inputs: dict[str, Any]) -> str | None:
        return str(inputs.get("project_id") or max_studio_client.get_project_id() or "") or None

    @staticmethod
    def _model(inputs: dict[str, Any]) -> str:
        return str(inputs.get("model") or inputs.get("model_name") or "Veo_3.1-Fast")

    @staticmethod
    def _duration(inputs: dict[str, Any]) -> int:
        raw = str(inputs.get("duration", 8)).strip().lower()
        raw = raw.removesuffix("s")
        duration = int(float(raw))
        if duration < 1:
            raise ValueError("duration must be at least 1 second")
        return duration

    def _run_task(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        api_key: str,
        cookie: str,
        inputs: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        project_id = self._project_id(inputs)
        if project_id:
            payload["projectId"] = project_id
        return max_studio_client.submit_and_wait(
            endpoint,
            payload,
            api_key=api_key,
            cookie=cookie,
            **self._task_options(inputs),
        )

    def _upload_image(
        self,
        value: str,
        *,
        api_key: str,
        cookie: str,
        inputs: dict[str, Any],
    ) -> str:
        image_value = self._remote_or_data(value, "image")
        payload = {"imageUrl": image_value}
        upload_ratio = inputs.get("upload_image_ratio")
        if upload_ratio:
            payload["ratio"] = str(upload_ratio)
        _, completed = self._run_task(
            "upload-image",
            payload,
            api_key=api_key,
            cookie=cookie,
            inputs=inputs,
        )
        return max_studio_client.result_media_id(completed)

    def _upload_video(
        self,
        value: str,
        *,
        api_key: str,
        cookie: str,
        inputs: dict[str, Any],
    ) -> str:
        video_value = self._remote_or_data(value, "video")
        _, completed = self._run_task(
            "upload-video",
            {"video_input": video_value},
            api_key=api_key,
            cookie=cookie,
            inputs=inputs,
        )
        return max_studio_client.result_media_id(completed)

    @staticmethod
    def _pick(inputs: dict[str, Any], url_key: str, path_key: str) -> str | None:
        value = inputs.get(url_key) or inputs.get(path_key)
        return str(value) if value else None

    def _build_payload(
        self,
        inputs: dict[str, Any],
        *,
        api_key: str,
        cookie: str,
    ) -> dict[str, Any]:
        operation = str(inputs.get("operation", "text_to_video"))
        model = self._model(inputs)
        if operation not in ENDPOINTS:
            raise ValueError(f"Unsupported Max Studio operation: {operation}")
        if model not in MODELS:
            raise ValueError(f"Unsupported Max Studio model: {model}")
        if operation == "reference_to_video" and model not in REFERENCE_MODELS:
            raise ValueError(
                f"{model} is not documented for reference-images-to-video; "
                f"choose one of {list(REFERENCE_MODELS)}"
            )

        prompt = str(inputs.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("prompt is required")
        ratio = str(inputs.get("aspect_ratio", "16:9"))
        duration = self._duration(inputs)
        seed = inputs.get("seed")

        if operation == "edit_video":
            media_id = inputs.get("media_id")
            if not media_id:
                video = self._pick(inputs, "video_url", "video_path")
                if not video:
                    raise ValueError("edit_video requires media_id, video_url, or video_path")
                media_id = self._upload_video(
                    video,
                    api_key=api_key,
                    cookie=cookie,
                    inputs=inputs,
                )
            payload: dict[str, Any] = {
                "media_id": str(media_id),
                "prompt": prompt,
                "paygate_tier": str(inputs.get("paygate_tier", "default")),
                "video_length": duration,
                "ratio": ratio,
                "video_model_key": model,
            }
        else:
            payload = {
                "prompt": prompt,
                # V3 accepts a single model as either a string or array in the
                # field table, but the video endpoint examples consistently use
                # arrays and image/reference video routes reject some scalar
                # payloads as INVALID_PARAMS.
                "model": [model],
                "ratio": ratio,
                "length": duration,
            }

        if seed is not None:
            payload["seed"] = int(seed)

        if operation == "image_to_video":
            image = self._pick(inputs, "image_url", "image_path") or self._pick(
                inputs, "reference_image_url", "reference_image_path"
            )
            if not image:
                raise ValueError("image_to_video requires image_url or image_path")
            payload["mediaId"] = self._upload_image(
                image,
                api_key=api_key,
                cookie=cookie,
                inputs=inputs,
            )
        elif operation == "reference_to_video":
            references = [str(value) for value in inputs.get("reference_image_urls") or []]
            references.extend(str(value) for value in inputs.get("reference_image_paths") or [])
            if not references:
                image = self._pick(inputs, "image_url", "image_path") or self._pick(
                    inputs, "reference_image_url", "reference_image_path"
                )
                if image:
                    references.append(image)
            if not references:
                raise ValueError("reference_to_video requires at least one reference image")
            payload["mediaId"] = [
                self._upload_image(
                    value,
                    api_key=api_key,
                    cookie=cookie,
                    inputs=inputs,
                )
                for value in references
            ]
            if "generate_audio" in inputs:
                payload["audio"] = bool(inputs.get("generate_audio"))
        elif operation == "first_last_frame_to_video":
            first = self._pick(inputs, "first_frame_url", "first_frame_path")
            last = self._pick(inputs, "last_frame_url", "last_frame_path")
            if not first or not last:
                raise ValueError(
                    "first_last_frame_to_video requires first_frame_url/path and last_frame_url/path"
                )
            payload["start_image_media_id"] = self._upload_image(
                first,
                api_key=api_key,
                cookie=cookie,
                inputs=inputs,
            )
            payload["end_image_media_id"] = self._upload_image(
                last,
                api_key=api_key,
                cookie=cookie,
                inputs=inputs,
            )
        elif operation == "extend_video":
            media_id = inputs.get("media_id")
            if not media_id:
                video = self._pick(inputs, "video_url", "video_path")
                if not video:
                    raise ValueError("extend_video requires media_id, video_url, or video_path")
                media_id = self._upload_video(
                    video,
                    api_key=api_key,
                    cookie=cookie,
                    inputs=inputs,
                )
            payload["mediaId"] = str(media_id)
            if inputs.get("start_second") is not None:
                payload["start_second"] = float(inputs["start_second"])
            if inputs.get("end_second") is not None:
                payload["end_second"] = float(inputs["end_second"])

        return payload

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = max_studio_client.get_api_key()
        cookie = max_studio_client.get_cookie()
        if not api_key or not cookie:
            return ToolResult(success=False, error=self.install_instructions)

        started = time.time()
        operation = str(inputs.get("operation", "text_to_video"))
        model = self._model(inputs)
        output_path = Path(inputs.get("output_path", "max_studio_output.mp4"))

        try:
            payload = self._build_payload(
                inputs,
                api_key=api_key,
                cookie=cookie,
            )
            created, completed = self._run_task(
                ENDPOINTS[operation],
                payload,
                api_key=api_key,
                cookie=cookie,
                inputs=inputs,
            )
            media_url = max_studio_client.result_media_url(completed)
            max_studio_client.download(media_url, output_path)
            from tools.video._shared import probe_output

            result = completed.get("result") or {}
            provider_amount = completed.get("amount", created.get("amount"))
            provider_balance = completed.get("balance", created.get("balance"))
            data = {
                "provider": self.provider,
                "gateway": "Max Studio V3",
                "model": model,
                "operation": operation,
                "task_id": str(created["taskid"]),
                "media_generation_id": result.get("mediaGenerationId") or result.get("mediaId"),
                "output": str(output_path),
                "provider_amount_credits": provider_amount,
                "provider_balance_credits": provider_balance,
                "cost_note": "Max Studio credits; no USD conversion was supplied by the V3 guide.",
                **probe_output(output_path),
            }
            return ToolResult(
                success=True,
                data=data,
                artifacts=[str(output_path)],
                cost_usd=0.0,
                duration_seconds=round(time.time() - started, 2),
                seed=inputs.get("seed"),
                model=model,
            )
        except Exception as exc:
            # Client errors are already redacted. Avoid serializing payloads or
            # response bodies here because they may contain the session cookie.
            return ToolResult(
                success=False,
                error=f"Max Studio V3 {operation} failed: {exc}",
                duration_seconds=round(time.time() - started, 2),
                model=model,
            )
