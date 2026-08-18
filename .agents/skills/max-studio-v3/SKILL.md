---
name: max-studio-v3
description: Use Max Studio V3 for Omni_Flash/Veo 3.1 video generation, especially upload-image to mediaId and image/reference-to-video flows. Use before calling or updating max_studio_video, and when diagnosing Max Studio task payloads.
---

# Max Studio V3

Max Studio V3 is an async task gateway at `https://max-studio.online` for
`Omni_Flash` and Veo 3.1 video models. Use OpenMontage `max_studio_video`
through `video_selector` for production work, unless you are doing a narrow API
diagnostic against the V3 contract.

## Non-negotiables

- Do not log, echo, commit, or paste `MAX_STUDIO_API_KEY` or
  `MAX_STUDIO_COOKIE`.
- Before a paid call, state the tool/provider, exact endpoint, model, duration,
  ratio, and whether it is a sample or batch.
- Do not substitute text-to-video when the user asked for reference images.
  Use `reference-images-to-video` for multiple visual anchors, or
  `image-to-video` for one starting/reference image.
- Do not guess support from model names. If a task fails, report the endpoint,
  task id, terminal status, provider message, `amount`, and `balance`.

## V3 task contract

Create tasks with `POST /api/v3/create-task/{endpoint}` and header
`X-API-Key`; include the Google Labs session `cookie` in the JSON body. Check
tasks with `GET /api/v3/check-status/{task_id}` and the same API-key header.

Useful endpoints:

- `upload-image`
- `text-to-video`
- `image-to-video`
- `reference-images-to-video`
- `start-end-image-to-video`
- `extend-video`
- `edit-video`

The guide says `model` may be a string or array, but video examples use arrays.
Prefer `model: ["Omni_Flash"]` / `["Veo_3.1-Fast"]` for video payloads.

## Reference image flow that was verified

1. Upload each local image first:

```json
{
  "imageUrl": "data:image/jpeg;base64,..."
}
```

`upload-image` can succeed with only `result.mediaGenerationId`; a `fifeUrl` is
not required. Use that returned value as `mediaId` in the next video payload.
Do not send it under the field name `mediaGenerationId`.

2. For multiple reference images, call:

```json
{
  "mediaId": ["uploaded-image-media-id-1", "uploaded-image-media-id-2"],
  "prompt": "Use the uploaded reference images as visual anchors ...",
  "model": ["Omni_Flash"],
  "ratio": "LANDSCAPE",
  "length": 10
}
```

For a single reference/start image, use `image-to-video` with
`mediaId: "uploaded-image-media-id"`.

3. Omit optional fields unless needed. In particular, do not add `audio` by
default for `Omni_Flash` reference-image video; the successful 10s test omitted
`audio` and still returned an AAC audio stream.

## Empirical result, 2026-08-18

Verified from `D:\TOOLS\Openmontage\projects\what-happened-to-blockbuster`
using two uploaded storefront reference images and endpoint
`reference-images-to-video`:

- model: `Omni_Flash`
- ratio: `LANDSCAPE`
- length: `10`
- upload-image task ids:
  - `1afd65c4-e220-47e7-86a8-af5c3943968a`
  - `7a64c566-ea9d-48ca-afaf-8e22c2da8b81`
- video task id: `7e8f760d-f789-4a9f-9654-b1cc9e3d5e44`
- terminal status: `successfully`
- provider cost: `amount: 1.0`, balance after task: `1694.0`
- output:
  `D:\TOOLS\Openmontage\projects\what-happened-to-blockbuster\assets\video\diag_omni_flash_reference_images_10s_v3_exact.mp4`
- ffprobe: 1280x720, 24fps, 10.005s, H.264 video, AAC stereo audio.
- contact sheet:
  `D:\TOOLS\Openmontage\projects\what-happened-to-blockbuster\artifacts\diag_omni_flash_reference_images_10s_contact.jpg`

Observed visual behavior: the reference storefront was preserved well, no
people were introduced, and the sign remained non-readable/blank as prompted.

## Prompting notes for storefront/news footage

Use one continuous shot and tell Omni exactly what to keep from the references:
storefront geometry, time period, lighting palette, camera move, and what not to
introduce. For archival/documentary b-roll, explicitly say: "No people, no
readable text, no logos, no subtitles, no scene cuts."
