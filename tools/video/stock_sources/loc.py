"""Library of Congress stock source adapter.

Wraps the loc.gov JSON API behind the unified `StockSource` protocol.
The Library of Congress holds 25+ digital collections of film and video
materials including early cinema, newsreels, documentaries, and cultural
recordings. Many items are public domain (pre-1928 or U.S. government).

No API key required. Rate limiting is polite-crawl based.

Fetch pattern
-------------
Two-stage. The search endpoint (``loc.gov/search``) returns items with
links to detail pages. The detail page JSON contains downloadable
resources including video files. Items are filtered by ``original-format``
to target film/video content.

What Library of Congress is good for
------------------------------------
- Early American cinema (pre-1928, public domain)
- Historical newsreels and documentaries
- Cultural recordings, folk traditions
- Government and civic footage
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .base import Candidate, SearchFilters

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://www.loc.gov/search/"
_LICENSE_PD = "Public domain (Library of Congress)"
_LICENSE_CHECK = "Rights status varies — verify per item (Library of Congress)"

# loc.gov is routinely slow (10-60s) and occasionally drops the connection
# mid-body. A 30s single-shot request fails often enough to look like an
# outage, so search retries with a generous timeout.
_TIMEOUT = 90
_RETRIES = 3

# Video-related format filters for the LoC API
_VIDEO_FORMATS = ["film/video", "motion picture"]


class LibraryOfCongressSource:
    """Library of Congress adapter. Satisfies `StockSource`."""

    name = "loc"
    display_name = "Library of Congress"
    provider = "loc"
    priority = 40
    install_instructions = (
        "Library of Congress works without an API key. "
        "No setup needed."
    )
    supports = {"video": True, "image": True}

    def is_available(self) -> bool:
        return True

    def search(self, query: str, filters: SearchFilters) -> list[Candidate]:
        import requests

        kind = (filters.kind or "video").lower()

        params: dict[str, Any] = {
            "q": query,
            "fo": "json",
            "c": max(1, min(filters.per_page, 50)),
            "sp": max(1, filters.page),
        }

        # Filter by format
        if kind == "video":
            # The loc.gov facet value is literally "film, video" (comma),
            # not "film/video" -- the old value matched nothing.
            params["fa"] = "original-format:film, video"
        elif kind == "image":
            params["fa"] = "original-format:photo, print, drawing"

        headers = {
            "Accept": "application/json",
            # loc.gov throttles/blocks requests without a real UA.
            "User-Agent": "OpenMontage/1.0 (stock source adapter)",
        }

        data = None
        last_error: Exception | None = None
        for attempt in range(1, _RETRIES + 1):
            try:
                r = requests.get(
                    _SEARCH_URL, params=params, timeout=_TIMEOUT, headers=headers
                )
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # timeout, incomplete read, 5xx, bad JSON
                last_error = e
                _log.warning(
                    "Library of Congress search attempt %d/%d failed: %s",
                    attempt, _RETRIES, e,
                )
                if attempt < _RETRIES:
                    time.sleep(2 * attempt)

        if data is None:
            _log.warning("Library of Congress search failed: %s", last_error)
            return []

        results = data.get("results", []) or []
        out: list[Candidate] = []

        for item in results:
            candidates = self._extract_candidates(item, kind, filters)
            out.extend(candidates)

        return out

    def _extract_candidates(
        self, item: dict, kind: str, filters: SearchFilters
    ) -> list[Candidate]:
        """Extract downloadable candidates from a LoC search result."""
        item_id = item.get("id", "") or ""
        if not item_id:
            return []

        title = item.get("title", "") or ""
        description = ""
        desc_list = item.get("description", [])
        if isinstance(desc_list, list) and desc_list:
            description = desc_list[0] if isinstance(desc_list[0], str) else ""
        elif isinstance(desc_list, str):
            description = desc_list

        subjects = item.get("subject", []) or []
        if isinstance(subjects, list):
            subjects = " ".join(s for s in subjects if isinstance(s, str))
        source_tags = f"{title} {description} {subjects}".strip()

        source_url = item_id if item_id.startswith("http") else f"https://www.loc.gov{item_id}"

        # Determine rights
        rights = item.get("rights", []) or []
        if isinstance(rights, list):
            rights_str = " ".join(r for r in rights if isinstance(r, str)).lower()
        else:
            rights_str = str(rights).lower()
        lic = _LICENSE_PD if "public domain" in rights_str or "no known" in rights_str else _LICENSE_CHECK

        # Look for downloadable resources
        resources = item.get("resources", []) or []
        # Also check the item's direct links
        image_url = ""
        if isinstance(item.get("image_url"), list):
            urls = item["image_url"]
            image_url = urls[0] if urls else ""
        elif isinstance(item.get("image_url"), str):
            image_url = item["image_url"]

        out: list[Candidate] = []

        # Try resources first
        for res in resources:
            if not isinstance(res, dict):
                continue

            # Search-result shape: resources[] carry direct media keys and
            # `files` is an ITEM COUNT (int), not a list. Item-detail shape:
            # `files` is a list of lists of file dicts. Handle both -- the
            # old code assumed only the latter and crashed with
            # "TypeError: 'int' object is not iterable" on every search.
            direct = self._candidate_from_resource(
                res, kind, filters, source_url, source_tags, lic, image_url
            )
            if direct is not None:
                out.append(direct)
                continue

            files = res.get("files")
            if not isinstance(files, list):
                continue
            for file_group in files:
                group = file_group if isinstance(file_group, list) else [file_group]
                for f in group:
                    if not isinstance(f, dict):
                        continue
                    url = f.get("url", "") or f.get("download", "") or ""
                    mime = (f.get("mimetype", "") or "").lower()
                    if not url:
                        continue

                    is_video = "video" in mime or any(
                        url.lower().endswith(ext)
                        for ext in (".mp4", ".mov", ".avi", ".webm")
                    )
                    is_image = "image" in mime or any(
                        url.lower().endswith(ext)
                        for ext in (".jpg", ".jpeg", ".png", ".tif")
                    )

                    if kind == "video" and not is_video:
                        continue
                    if kind == "image" and not is_image:
                        continue
                    if not is_video and not is_image:
                        continue

                    full_url = url if url.startswith("http") else f"https://www.loc.gov{url}"

                    duration = float(res.get("duration") or 0)
                    if is_video and duration:
                        if filters.min_duration and duration < filters.min_duration:
                            continue
                        if filters.max_duration and duration > filters.max_duration:
                            continue

                    out.append(
                        Candidate(
                            source=self.name,
                            source_id=f"loc_{hash(full_url) & 0xFFFFFFFF:08x}",
                            source_url=source_url,
                            download_url=full_url,
                            kind="video" if is_video else "image",
                            width=int(f.get("width") or res.get("width") or 0),
                            height=int(f.get("height") or res.get("height") or 0),
                            duration=duration,
                            creator="Library of Congress",
                            license=lic,
                            source_tags=source_tags,
                            thumbnail_url=self._abs(res.get("poster")) or image_url,
                            extra={
                                "item_id": item_id,
                                "mime": mime,
                            },
                        )
                    )

        # If no resources found but we have an image_url for image kind
        if not out and kind in ("image", "any") and image_url:
            full_url = image_url if image_url.startswith("http") else f"https://www.loc.gov{image_url}"
            out.append(
                Candidate(
                    source=self.name,
                    source_id=f"loc_{hash(full_url) & 0xFFFFFFFF:08x}",
                    source_url=source_url,
                    download_url=full_url,
                    kind="image",
                    width=0,
                    height=0,
                    duration=0.0,
                    creator="Library of Congress",
                    license=lic,
                    source_tags=source_tags,
                    thumbnail_url=image_url,
                    extra={"item_id": item_id},
                )
            )

        return out

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        import requests

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(
            candidate.download_url, stream=True, timeout=180
        ) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        return out_path

    @staticmethod
    def _abs(url: Any) -> str:
        """Absolutise a loc.gov URL. Media URLs often come back protocol-relative."""
        if not isinstance(url, str) or not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        return f"https://www.loc.gov{url}"

    def _candidate_from_resource(
        self,
        res: dict,
        kind: str,
        filters: SearchFilters,
        source_url: str,
        source_tags: str,
        lic: str,
        fallback_thumb: str,
    ) -> Candidate | None:
        """Build a candidate from a search-result `resources[]` entry.

        Search results expose the playable file directly on the resource
        (`video` / `audio` / `image` keys) rather than in a nested
        `files` list. Returns None when this resource has no usable direct
        media for the requested kind.
        """
        video_url = self._abs(res.get("video"))
        image_direct = self._abs(res.get("image"))

        if kind == "video":
            if not video_url:
                return None
            media_url, candidate_kind = video_url, "video"
        elif kind == "image":
            if not image_direct:
                return None
            media_url, candidate_kind = image_direct, "image"
        else:
            if video_url:
                media_url, candidate_kind = video_url, "video"
            elif image_direct:
                media_url, candidate_kind = image_direct, "image"
            else:
                return None

        duration = float(res.get("duration") or 0)
        if candidate_kind == "video" and duration:
            if filters.min_duration and duration < filters.min_duration:
                return None
            if filters.max_duration and duration > filters.max_duration:
                return None

        width = int(res.get("width") or 0)
        if candidate_kind == "video" and filters.min_width and width and width < filters.min_width:
            return None

        return Candidate(
            source=self.name,
            source_id=f"loc_{hash(media_url) & 0xFFFFFFFF:08x}",
            source_url=source_url,
            download_url=media_url,
            kind=candidate_kind,
            width=width,
            height=int(res.get("height") or 0),
            duration=duration,
            creator="Library of Congress",
            license=lic,
            source_tags=source_tags,
            thumbnail_url=self._abs(res.get("poster")) or fallback_thumb,
            extra={
                "media_object_id": res.get("media_object_id"),
                "resource_url": res.get("url"),
                "video_stream": res.get("video_stream"),
            },
        )
