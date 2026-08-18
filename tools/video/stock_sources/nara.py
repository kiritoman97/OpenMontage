"""U.S. National Archives (NARA) stock source adapter.

Wraps the NARA Catalog API (``catalog.archives.gov/api/v2``) behind the
unified `StockSource` protocol. NARA holds billions of records including
significant film and video holdings — all U.S. federal government work
and therefore public domain.

An API key IS required. The v2 Catalog API rejects unauthenticated
requests by serving the catalog's HTML single-page app instead of JSON,
which is why an unkeyed adapter appears to "work" and then dies with a
JSON decode error. Request a key by emailing Catalog_API@nara.gov and
set it as `NARA_API_KEY`. Rate limit: ~10,000 queries per month per key.

Fetch pattern
-------------
Two-stage like NASA. The search endpoint returns metadata records. Each
record may contain digital objects (files) in ``objects``. We follow
those to find downloadable video files.

What NARA is good for
---------------------
- U.S. historical footage (military, presidential, space, civil rights)
- WWII, Cold War, Apollo era footage
- Government program footage and newsreels
- Any "march of history" documentary sequence
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import Candidate, SearchFilters

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://catalog.archives.gov/api/v2/records/search"
_LICENSE = "Public domain (U.S. federal government work)"


class NARASource:
    """U.S. National Archives adapter. Satisfies `StockSource`."""

    name = "nara"
    display_name = "U.S. National Archives"
    provider = "nara"
    priority = 35
    install_instructions = (
        "NARA requires an API key. Email Catalog_API@nara.gov to request "
        "one, then set NARA_API_KEY in .env. Without it the v2 Catalog API "
        "returns HTML instead of JSON."
    )
    supports = {"video": True, "image": True}

    def is_available(self) -> bool:
        # The v2 Catalog API silently returns HTML without a key, so an
        # unkeyed adapter is worse than an absent one -- it burns a search
        # slot and returns nothing.
        return bool(os.environ.get("NARA_API_KEY"))

    def search(self, query: str, filters: SearchFilters) -> list[Candidate]:
        import requests

        kind = (filters.kind or "video").lower()

        api_key = os.environ.get("NARA_API_KEY")
        if not api_key:
            _log.warning(
                "NARA search skipped: NARA_API_KEY is not set (the v2 Catalog "
                "API returns HTML, not JSON, for unauthenticated requests)."
            )
            return []

        params: dict[str, Any] = {
            "q": query,
            "limit": max(1, min(filters.per_page, 50)),
            "offset": (max(1, filters.page) - 1) * filters.per_page,
            # Only records that actually have a viewable/downloadable file.
            "availableOnline": "true",
        }

        # Filter by type if possible
        if kind == "video":
            params["typeOfMaterials"] = "Moving Images"
        elif kind == "image":
            params["typeOfMaterials"] = "Photographs and Other Graphic Materials"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": api_key,
        }

        try:
            r = requests.get(
                _SEARCH_URL,
                headers=headers,
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                _log.warning(
                    "NARA search returned %s instead of JSON -- the API key is "
                    "probably missing or rejected.", ctype or "an unknown type"
                )
                return []
            data = r.json()
        except Exception as e:
            _log.warning("NARA search failed: %s", e)
            return []

        results = self._unwrap_hits(data)
        out: list[Candidate] = []

        for item in results:
            candidates = self._extract_candidates(item, kind, filters)
            out.extend(candidates)

        return out

    @staticmethod
    def _unwrap_hits(data: dict) -> list[dict]:
        """Pull the record list out of the v2 Elasticsearch-shaped envelope.

        v2 returns `{"body": {"hits": {"hits": [{"_source": {...}}]}}}`.
        Older/alternate shapes used a flat `results` list. Accept both so
        this keeps working if the envelope changes again.
        """
        if not isinstance(data, dict):
            return []

        flat = data.get("results")
        if isinstance(flat, list) and flat:
            return [x for x in flat if isinstance(x, dict)]

        hits = (
            (data.get("body") or {}).get("hits", {}).get("hits")
            if isinstance(data.get("body"), dict)
            else data.get("hits", {}).get("hits")
            if isinstance(data.get("hits"), dict)
            else None
        )
        if not isinstance(hits, list):
            return []

        out: list[dict] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            src = h.get("_source")
            if isinstance(src, dict):
                # v2 nests the descriptive record one more level down.
                record = src.get("record")
                out.append(record if isinstance(record, dict) else src)
            else:
                out.append(h)
        return out

    def _extract_candidates(
        self, item: dict, kind: str, filters: SearchFilters
    ) -> list[Candidate]:
        """Extract downloadable candidates from a NARA catalog record."""
        naid = str(item.get("naId") or item.get("naid") or "")
        if not naid:
            return []

        title = item.get("title", "") or ""
        description = (
            item.get("scopeAndContentNote")
            or item.get("generalNoteArray")
            or ""
        )
        if not isinstance(description, str):
            description = " ".join(
                str(x) for x in description if isinstance(x, (str, int, float))
            ) if isinstance(description, list) else str(description)
        source_tags = f"{title} {description}".strip()
        source_url = f"https://catalog.archives.gov/id/{naid}"

        # Look for digital objects
        objects = item.get("objects") or item.get("digitalObjects") or []
        if not objects:
            return []
        if not isinstance(objects, list):
            return []

        out: list[Candidate] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            nested = obj.get("file") if isinstance(obj.get("file"), dict) else {}
            file_url = (
                obj.get("url")
                or obj.get("fileUrl")
                or nested.get("url")
                or ""
            )
            if not file_url:
                continue

            # Determine kind from mime type or file extension
            mime = (obj.get("mimeType") or obj.get("objectType") or "").lower()
            ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""

            is_video = (
                "video" in mime
                or ext in ("mp4", "mov", "avi", "wmv", "mkv", "webm")
            )
            is_image = (
                "image" in mime
                or ext in ("jpg", "jpeg", "png", "tif", "tiff", "gif")
            )

            if kind == "video" and not is_video:
                continue
            if kind == "image" and not is_image:
                continue
            if not is_video and not is_image:
                continue

            candidate_kind = "video" if is_video else "image"
            width = int(obj.get("width") or 0)
            height = int(obj.get("height") or 0)
            duration = float(obj.get("duration") or 0)

            # Duration filters (client-side)
            if candidate_kind == "video":
                if filters.min_duration and duration and duration < filters.min_duration:
                    continue
                if filters.max_duration and duration and duration > filters.max_duration:
                    continue

            out.append(
                Candidate(
                    source=self.name,
                    source_id=f"{naid}_{obj.get('objectId', len(out))}",
                    source_url=source_url,
                    download_url=file_url,
                    kind=candidate_kind,
                    width=width,
                    height=height,
                    duration=duration,
                    creator="U.S. National Archives",
                    license=_LICENSE,
                    source_tags=source_tags,
                    thumbnail_url=obj.get("thumbnailUrl", "") or "",
                    extra={
                        "naId": naid,
                        "mime": mime,
                        "fileSize": obj.get("fileSize"),
                    },
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
