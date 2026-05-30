from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from hashlib import sha1
from html import unescape
from typing import Any
from urllib import error, parse, request as urllib_request

from deep_research_agent.domain.models import PlanTask, ResearchRequest, SearchProvider, SearchResult
from deep_research_agent.services.llm import ProviderConfigurationError
from deep_research_agent.settings import AppSettings

_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "ref_src")
_ANCHOR_PATTERN = re.compile(r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")


class SearchService(ABC):
    @abstractmethod
    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]: ...


class DuckDuckGoSearchService(SearchService):
    def __init__(self, *, user_agent: str):
        self._user_agent = user_agent

    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]:
        query = parse.quote_plus(task.search_query)
        url = f"https://html.duckduckgo.com/html/?q={query}"

        def _fetch() -> str:
            req = urllib_request.Request(url, headers={"User-Agent": self._user_agent})
            with urllib_request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore")

        try:
            html = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=35)
        except (TimeoutError, asyncio.TimeoutError, Exception):  # pragma: no cover - network availability
            return []

        results: list[SearchResult] = []
        for match in _ANCHOR_PATTERN.finditer(html):
            href = unescape(match.group("href"))
            title = _clean_html(match.group("title"))
            if not title:
                continue
            parsed_href = parse.urlparse(href)
            if "duckduckgo.com" in parsed_href.netloc and parsed_href.path.startswith("/l/"):
                params = parse.parse_qs(parsed_href.query)
                candidate_url = params.get("uddg", [""])[0]
            else:
                candidate_url = href
            if not candidate_url.startswith("http"):
                continue
            canonical_url = canonicalize_url(candidate_url)
            if any(result.canonical_url == canonical_url for result in results):
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=candidate_url,
                    canonical_url=canonical_url,
                    provider=SearchProvider.NONE,
                    snippet=None,
                    metadata={"task_query": task.search_query, "query_fingerprint": stable_hash(task.search_query)},
                )
            )
            if len(results) >= limit:
                break
        return results


class TavilySearchService(SearchService):
    def __init__(self, *, api_key: str, user_agent: str):
        self._api_key = api_key
        self._user_agent = user_agent

    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": task.search_query,
            "max_results": limit,
            "search_depth": "advanced",
            "include_raw_content": False,
        }
        response = await _post_json(
            "https://api.tavily.com/search",
            payload,
            headers={"User-Agent": self._user_agent},
        )
        results: list[SearchResult] = []
        for item in response.get("results", []):
            url = item.get("url")
            title = item.get("title") or url
            if not url:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    canonical_url=canonicalize_url(url),
                    provider=SearchProvider.TAVILY,
                    snippet=item.get("content"),
                    metadata={"score": item.get("score")},
                )
            )
        return results


class SerperSearchService(SearchService):
    def __init__(self, *, api_key: str, user_agent: str):
        self._api_key = api_key
        self._user_agent = user_agent

    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]:
        response = await _post_json(
            "https://google.serper.dev/search",
            {"q": task.search_query, "num": limit},
            headers={"X-API-KEY": self._api_key, "User-Agent": self._user_agent},
        )
        results: list[SearchResult] = []
        for item in response.get("organic", []):
            url = item.get("link")
            title = item.get("title") or url
            if not url:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    canonical_url=canonicalize_url(url),
                    provider=SearchProvider.SERPER,
                    snippet=item.get("snippet"),
                    metadata={"position": item.get("position")},
                )
            )
        return results


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}

    def _send() -> dict[str, Any]:
        req = urllib_request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - provider/network behavior
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ProviderConfigurationError(f"Search request failed with HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - provider/network behavior
            raise ProviderConfigurationError(f"Search request failed: {exc.reason}") from exc

    task = asyncio.create_task(asyncio.to_thread(_send))
    try:
        return await asyncio.wait_for(task, timeout=35)
    except (asyncio.TimeoutError, TimeoutError):
        task.cancel()
        raise ProviderConfigurationError(f"Search request timed out after 35s: {url}")



def build_search_service(settings: AppSettings) -> SearchService:
    if settings.default_search_provider is SearchProvider.NONE:
        return DuckDuckGoSearchService(user_agent=settings.http_user_agent)
    if settings.default_search_provider is SearchProvider.TAVILY:
        if settings.tavily_api_key:
            return TavilySearchService(api_key=settings.tavily_api_key, user_agent=settings.http_user_agent)
        return DuckDuckGoSearchService(user_agent=settings.http_user_agent)
    if settings.default_search_provider is SearchProvider.SERPER:
        if settings.serper_api_key:
            return SerperSearchService(api_key=settings.serper_api_key, user_agent=settings.http_user_agent)
        return DuckDuckGoSearchService(user_agent=settings.http_user_agent)
    raise ProviderConfigurationError(
        "Search provider `firecrawl` is not supported as a search backend in the MVP runtime. "
        "Use tavily, serper, or none."
    )



def canonicalize_url(url: str) -> str:
    parsed = parse.urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    query_items = [
        (key, value)
        for key, value in parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    query = parse.urlencode(sorted(query_items))
    return parse.urlunparse((scheme, netloc, path.rstrip("/") or "/", "", query, ""))



def stable_hash(value: str, *, prefix: str = "") -> str:
    return f"{prefix}{sha1(value.encode('utf-8')).hexdigest()[:12]}"



def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", _TAG_PATTERN.sub(" ", value)).strip()
