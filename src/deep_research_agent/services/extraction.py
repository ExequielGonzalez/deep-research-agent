from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib import request as urllib_request

from deep_research_agent.domain.models import EvidenceRecord, PlanTask, ResearchRequest, SourceRecord
from deep_research_agent.services.search import stable_hash
from deep_research_agent.settings import AppSettings


@dataclass(slots=True)
class ExtractionResult:
    evidence: list[EvidenceRecord]
    notes: list[str]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        normalized = data.strip()
        if normalized:
            self.parts.append(normalized)

    def text(self) -> str:
        return " ".join(self.parts)


class ContentExtractor:
    def __init__(self, settings: AppSettings):
        self._settings = settings

    async def extract(self, *, source: SourceRecord, task: PlanTask, research_request: ResearchRequest) -> ExtractionResult:
        raw_text = source.metadata.get("raw_content") or source.metadata.get("content") or source.snippet or ""
        if not raw_text:
            raw_text = await self._fetch_text(source.url)
        if not raw_text:
            return ExtractionResult(evidence=[], notes=[f"No extractable content for {source.url}"])

        normalized_text = _normalize_text(raw_text)[: self._settings.max_content_chars_per_source]
        passages = _top_passages(
            normalized_text,
            keywords=_keywords(task.search_query, task.title, task.description, research_request.query),
            limit=2,
        )
        evidence: list[EvidenceRecord] = []
        for passage, score in passages:
            evidence.append(
                EvidenceRecord(
                    evidence_id=stable_hash(f"{source.source_id}:{task.task_id}:{passage}", prefix="evi_"),
                    source_id=source.source_id,
                    claim=_claim_from_passage(passage),
                    excerpt=passage,
                    rationale=f"Keyword overlap score {score:.2f} for task '{task.title}'.",
                    confidence=min(0.95, 0.35 + (score * 0.15)),
                    supports_task_id=task.task_id,
                )
            )
        notes = [f"Extracted {len(evidence)} evidence item(s) from {source.title} for task {task.task_id}."] if evidence else []
        return ExtractionResult(evidence=evidence, notes=notes)

    async def _fetch_text(self, url: str) -> str:
        def _fetch() -> str:
            req = urllib_request.Request(url, headers={"User-Agent": self._settings.http_user_agent})
            with urllib_request.urlopen(req, timeout=30) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read().decode("utf-8", errors="ignore")
            if "html" in content_type:
                parser = _TextExtractor()
                parser.feed(raw)
                return parser.text()
            return raw

        try:
            return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=35)
        except (TimeoutError, asyncio.TimeoutError, Exception):  # pragma: no cover - network availability
            return ""



def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()



def _claim_from_passage(passage: str) -> str:
    shortened = passage.strip()
    if len(shortened) <= 180:
        return shortened
    return f"{shortened[:177].rstrip()}..."



def _top_passages(text: str, *, keywords: set[str], limit: int) -> list[tuple[str, float]]:
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    scored: list[tuple[str, float]] = []
    for chunk in chunks:
        chunk_words = {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}", chunk)}
        if not chunk_words:
            continue
        overlap = len(chunk_words & keywords)
        if overlap <= 0:
            continue
        scored.append((chunk, overlap / max(len(keywords), 1)))
    scored.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
    return scored[:limit]



def _keywords(*parts: str) -> set[str]:
    merged = " ".join(parts)
    return {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}", merged)}
