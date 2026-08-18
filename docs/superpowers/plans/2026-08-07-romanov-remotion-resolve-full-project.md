# Romanov Remotion → DaVinci Resolve Full Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện master documentary Romanov dài 52:55 bằng Remotion, sau đó import toàn bộ footage, narration, music và timeline assembly vào DaVinci Resolve để chỉnh tay/QC.

**Architecture:** Remotion JSON là nguồn sự thật cho timing, subtitle, archive look, footage/stills, narration và music. DaVinci Resolve nhận một project `.drp` độc lập để kiểm tra media, dựng assembly, color/audio finishing và lưu phiên bản chỉnh tay; Resolve không thay thế project Remotion.

**Tech Stack:** Remotion 4.0.484, React/TypeScript, Chromium ANGLE, FFmpeg/NVENC delivery encode, DaVinci Resolve Studio 21.0.2.4 `fuscript` Python API, SRT, `.drp` project backup.

---

## Current Baseline

- Full narration: `projects/dynasty-records-chap1-full/artifacts/narration_full.mp3`
- Sentence subtitles: `projects/dynasty-records-chap1-full/artifacts/chapter.sentences.srt`
- Editable master props: `projects/dynasty-records-chap1-full/artifacts/remotion_master.json`
- Background music: `music_library/Long Note Two.mp3`
- Remotion master render is already running in the background; never start a second master render over it.
- Resolve test project already exists as `Romanov Dynasty Records - Resolve Test` and has an initial assembly timeline.

## Task 1: Verify the Remotion master render

**Files:**
- Read: `projects/dynasty-records-chap1-full/renders/master_render.log`
- Output: `projects/dynasty-records-chap1-full/renders/master.mp4`

- [ ] Check the background render process and read the last 20 log lines.
- [ ] Confirm the render reaches `Rendered 95259/95259` and exits successfully.
- [ ] If the process fails, capture the exact error, fix only the failing path/component, and restart one master render.
- [ ] Verify the output with:

```powershell
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,codec_type -of json `
  projects\dynasty-records-chap1-full\renders\master.mp4
```

Expected: approximately `3175.3` seconds, 1920x1080, 30fps, H.264 video and AAC audio.

## Task 2: Run Remotion visual/audio QC

**Files:**
- Read: `projects/dynasty-records-chap1-full/artifacts/remotion_master.json`
- Create: `projects/dynasty-records-chap1-full/artifacts/master_qc_report.json`

- [ ] Extract representative frames at 0s, 349s, 773s, 1247s, 1818s, 2153s, 2684s and 3170s.
- [ ] Check that archive grade, vignette, subtitle outline and title-card fallbacks are visible.
- [ ] Check that subtitles have no rectangular background and remain inside the safe area.
- [ ] Check narration is present across the full duration and music is looped with low volume.
- [ ] Record any visual/audio issue in `master_qc_report.json`; do not silently alter the master without updating the JSON source.

## Task 3: Validate rights and provenance package

**Files:**
- Read: `projects/dynasty-records-chap1-full/artifacts/rights_report.json`
- Modify only if needed: `projects/dynasty-records-chap1-full/artifacts/build_rights_report.py`
- Create/update: `projects/dynasty-records-chap1-full/artifacts/resolve_source_manifest.json`

- [ ] Regenerate the rights report after the final master asset list is frozen.
- [ ] Ensure each footage/still has source URL, license/status, local path and fallback reason when applicable.
- [ ] Include music attribution exactly:

```text
Long Note Two — Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0
https://creativecommons.org/licenses/by/4.0/
```

- [ ] Flag unresolved/stand-in material as metaphor or title-card fallback instead of presenting it as archival evidence.

## Task 4: Build the Resolve import manifest

**Files:**
- Modify: `projects/dynasty-records-chap1-full/artifacts/resolve_import_project.py`
- Create: `projects/dynasty-records-chap1-full/artifacts/resolve_source_manifest.json`

- [ ] Read `remotion_master.json` and deduplicate all video/image scene sources.
- [ ] Resolve each Remotion public path to an absolute local source path.
- [ ] Keep narration and music as separate audio entries.
- [ ] Validate every path exists and has non-zero size before calling Resolve.
- [ ] Write a manifest containing scene id, section, source path, scene start, intended duration, media type and provenance.

## Task 5: Create the complete Resolve project with `fuscript`

**Files:**
- Modify: `projects/dynasty-records-chap1-full/artifacts/resolve_import_project.py`
- Output: DaVinci project `Romanov Dynasty Records - Resolve Full`
- Output: `projects/dynasty-records-chap1-full/artifacts/Romanov_Dynasty_Resolve_Full.drp`
- Output: `projects/dynasty-records-chap1-full/artifacts/resolve_full_import_report.json`

- [ ] Connect through Resolve's own interpreter:

```powershell
& 'C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe' `
  -l py3 `
  'D:\TOOLS\Openmontage\projects\dynasty-records-chap1-full\artifacts\resolve_import_project.py'
```

- [ ] Create/load `Romanov Dynasty Records - Resolve Full` without deleting the existing test project.
- [ ] Import every validated visual source into the Media Pool.
- [ ] Import narration and `Long Note Two` into the Media Pool.
- [ ] Create a timeline named `Romanov Master Conform`.
- [ ] Place source clips at their intended record-frame positions where the Resolve API can verify source ranges; use explicit gaps for title-card-only scenes.
- [ ] Create a second timeline named `Romanov Imported Sources` containing a sequential assembly for quick browsing.
- [ ] Save the project and export a `.drp` backup.

## Task 6: Add Resolve finishing structure

**Files:**
- Modify: `projects/dynasty-records-chap1-full/artifacts/resolve_import_project.py`
- Create: `projects/dynasty-records-chap1-full/artifacts/resolve_finishing_notes.md`

- [ ] Add timeline markers at section boundaries: 1–8.
- [ ] Add markers for title-card fallbacks and unsupported historical claims.
- [ ] Add a color-page note describing the Remotion archive look: desaturation, warm highlights, vignette, subtle flicker and gate weave.
- [ ] Add an audio-page note: narration priority, music at approximately -18 to -24 dB under narration, fade-out at the final 4 seconds.
- [ ] Do not render a final Resolve replacement until the Remotion master passes QC.

## Task 7: Resolve media/timeline QC

**Files:**
- Create: `projects/dynasty-records-chap1-full/artifacts/resolve_full_qc_report.json`

- [ ] Reopen the saved `.drp` in Resolve.
- [ ] Confirm no imported clip is offline.
- [ ] Confirm the Media Pool count matches the import manifest.
- [ ] Confirm timeline names, section markers and audio items exist.
- [ ] Confirm the project can be saved/reopened without changing the Remotion master.
- [ ] Record Resolve version, project name, timeline item counts and any offline media in the QC report.

## Task 8: Delivery outputs

**Files:**
- Output: `projects/dynasty-records-chap1-full/renders/master.mp4`
- Output: `projects/dynasty-records-chap1-full/renders/master_nvenc.mp4`
- Output: `projects/dynasty-records-chap1-full/artifacts/publish_package.json`

- [ ] Keep the Remotion-rendered master as the canonical video.
- [ ] Run the NVIDIA NVENC delivery encode only after the Remotion master passes ffprobe/QC.
- [ ] Verify the NVENC output duration, resolution, frame rate, audio stream and H.264 codec.
- [ ] Package the canonical JSON, SRT, rights report, music attribution, Resolve `.drp`, QC reports and final MP4 paths.

## Acceptance Criteria

- [ ] Remotion master renders for the full 52:55 with no missing media or render errors.
- [ ] Subtitles are sentence-based, bold, outlined, and have no rectangular background.
- [ ] Music loops continuously and remains below narration.
- [ ] All unsupported claims are represented by labelled metaphor/title-card treatment.
- [ ] Resolve project imports all validated sources and reopens successfully.
- [ ] `.drp` backup exists and is linked to an import report.
- [ ] Final delivery passes ffprobe and rights/provenance review.
