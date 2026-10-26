"""Core logic for the Field Technician Copilot demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATA_PATH = Path(__file__).parent / "data" / "manuals.json"
UNSAFE_PATTERNS = (
    re.compile(r"\b(?:bypass|disable|defeat|override|jumper|short)\b.{0,35}\b(?:safety|interlock|switch|sensor|limit|protection)\b", re.I),
    re.compile(r"\b(?:safety|interlock|switch|sensor|limit|protection)\b.{0,35}\b(?:bypass|disable|defeat|override|jumper|short)\b", re.I),
    re.compile(r"\b(?:work on|probe|touch|repair|open)\b.{0,30}\b(?:live|energized|high.voltage)\b", re.I),
)
STOP_WORDS = {
    "a", "an", "and", "are", "can", "do", "does", "for", "from", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "the", "this",
    "to", "what", "when", "where", "why", "with", "unit", "equipment",
}


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    section: str
    content: str
    checks: tuple[str, ...]
    keywords: tuple[str, ...]

    @property
    def citation(self) -> str:
        return f"{self.title}, {self.section} [{self.source_id}]"


@dataclass(frozen=True)
class RetrievedSource:
    source: Source
    score: int


def load_sources(path: Path = DATA_PATH) -> list[Source]:
    """Load the approved, local demo corpus and validate its basic shape."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load the approved documentation corpus: {exc}") from exc
    if not isinstance(raw, list):
        raise RuntimeError("The documentation corpus must contain a JSON list.")

    sources: list[Source] = []
    for item in raw:
        try:
            sources.append(
                Source(
                    source_id=str(item["source_id"]),
                    title=str(item["title"]),
                    section=str(item["section"]),
                    content=str(item["content"]),
                    checks=tuple(str(check) for check in item["checks"]),
                    keywords=tuple(str(word).lower() for word in item["keywords"]),
                )
            )
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Invalid documentation entry: {item!r}") from exc
    if not sources:
        raise RuntimeError("The approved documentation corpus is empty.")
    return sources


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9]+", text)
        if token.lower() not in STOP_WORDS and len(token) > 1
    }


def retrieve(query: str, sources: list[Source], limit: int = 3) -> list[RetrievedSource]:
    """Rank local corpus passages by transparent keyword overlap."""
    query_tokens = _tokens(query)
    ranked: list[RetrievedSource] = []
    for source in sources:
        searchable = _tokens(
            f"{source.title} {source.section} {source.content} {' '.join(source.keywords)}"
        )
        score = len(query_tokens & searchable)
        if score:
            ranked.append(RetrievedSource(source=source, score=score))
    return sorted(ranked, key=lambda item: (-item.score, item.source.source_id))[:limit]


def is_unsafe_request(text: str) -> bool:
    return any(pattern.search(text) for pattern in UNSAFE_PATTERNS)


def build_guidance(query: str, sources: list[Source]) -> dict[str, Any]:
    """Return only documentation-backed checks or an explicit limitation."""
    if is_unsafe_request(query):
        return {
            "status": "escalate",
            "message": (
                "I can't help bypass safety protections or work on energized equipment. "
                "Stop and follow your site's lockout/tagout and manufacturer safety "
                "procedures; contact a qualified supervisor."
            ),
            "evidence": [],
            "checks": [],
        }

    matches = retrieve(query, sources)
    if not matches:
        return {
            "status": "unsupported",
            "message": (
                "I couldn't find support for this question in the approved demo "
                "documents. I won't guess; check the manufacturer documentation or "
                "escalate to a qualified supervisor."
            ),
            "evidence": [],
            "checks": [],
        }

    checks: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    seen_checks: set[str] = set()
    for match in matches:
        source = match.source
        evidence.append(
            {
                "citation": source.citation,
                "excerpt": source.content,
                "source_id": source.source_id,
            }
        )
        for check in source.checks:
            if check not in seen_checks:
                checks.append({"text": check, "citation": source.citation})
                seen_checks.add(check)
    return {
        "status": "supported",
        "message": "Here are documentation-backed checks. Confirm the equipment model and follow site safety procedures.",
        "evidence": evidence,
        "checks": checks,
    }


def lookup_mock_asset(asset_id: str) -> dict[str, Any] | None:
    """Return synthetic asset history only; no external systems are contacted."""
    assets = {
        "HVAC-RTU-104": {
            "asset_id": "HVAC-RTU-104",
            "equipment": "Demo rooftop unit",
            "history": [
                "2026-08-14: Routine filter replacement recorded.",
                "2026-09-02: Startup fault reported; cleared after restart (simulated record).",
            ],
        },
        "HVAC-RTU-205": {
            "asset_id": "HVAC-RTU-205",
            "equipment": "Demo rooftop unit",
            "history": ["2026-07-20: Preventive maintenance completed (simulated record)."],
        },
    }
    return assets.get(asset_id.strip().upper())


def build_service_report(case: dict[str, Any]) -> str:
    """Render an editable, explicitly draft report with evidence provenance."""
    lines = [
        "# Draft service report — technician review required",
        "",
        f"- **Case:** {case.get('case_id', 'Not assigned')}",
        f"- **Equipment:** {case.get('asset_id') or 'Not provided'}",
        f"- **Reported symptom:** {case.get('symptom') or 'Not provided'}",
        f"- **Created (UTC):** {case.get('created_at') or 'Not recorded'}",
        "",
        "## Confirmed observations",
    ]
    observations = case.get("observations", [])
    lines.extend([f"- {item}" for item in observations] or ["- None recorded."])
    lines.extend(["", "## Checks and outcomes"])
    checks = case.get("checks", [])
    if checks:
        for check in checks:
            lines.append(f"- **{check['check']}** — {check['outcome']}")
            if check.get("citation"):
                lines.append(f"  - Reference: {check['citation']}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## References"])
    references = case.get("references", [])
    lines.extend([f"- {ref}" for ref in references] or ["- None."])
    lines.extend(
        [
            "",
            "## Unresolved questions / follow-up",
            f"- {case.get('follow_up') or 'None recorded.'}",
            "",
            "> This report is a draft. Verify all details and references before use; it has not been submitted.",
        ]
    )
    return "\n".join(lines)


class VisionNotConfigured(RuntimeError):
    """Raised when Azure AI Vision credentials have not been configured."""


def analyze_image(image_bytes: bytes, endpoint: str, key: str, timeout: int = 20) -> list[str]:
    """Use Azure AI Vision OCR to return tentative text clues from an image."""
    if not endpoint or not key:
        raise VisionNotConfigured(
            "Image clue extraction is not configured. Set AZURE_VISION_ENDPOINT and "
            "AZURE_VISION_KEY, or have the technician read and confirm visible details manually."
        )
    if not image_bytes:
        raise ValueError("The uploaded image is empty.")

    base_url = endpoint.rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ValueError("AZURE_VISION_ENDPOINT must be an HTTP(S) URL.")
    url = f"{base_url}/computervision/imageanalysis:analyze?{urlencode({'api-version': '2024-02-01', 'features': 'read'})}"
    request = Request(
        url,
        data=image_bytes,
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/octet-stream",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Azure AI Vision returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Azure AI Vision request failed: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Azure AI Vision returned an invalid JSON response.") from exc

    try:
        lines = [
            line["text"].strip()
            for block in payload["readResult"]["blocks"]
            for line in block["lines"]
            if line.get("text", "").strip()
        ]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Azure AI Vision response did not contain the expected OCR results.") from exc
    return lines


def new_case(asset_id: str, symptom: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "case_id": f"CASE-{now.strftime('%Y%m%d-%H%M%S')}",
        "asset_id": asset_id.strip(),
        "symptom": symptom.strip(),
        "created_at": now.isoformat(timespec="seconds"),
        "observations": [],
        "checks": [],
        "references": [],
        "follow_up": "",
        "image_clues": [],
    }
