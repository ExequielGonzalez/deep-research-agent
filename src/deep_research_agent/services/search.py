from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import random
import re
from abc import ABC, abstractmethod
from hashlib import sha1
from html import unescape
from typing import Any
from urllib import error, parse, request as urllib_request

from deep_research_agent.domain.models import PlanTask, ResearchRequest, SearchProvider, SearchResult
from deep_research_agent.services.llm import ProviderConfigurationError
from deep_research_agent.settings import AppSettings, load_persisted_app_settings, save_persisted_app_settings

_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "ref_src")
_ANCHOR_PATTERN = re.compile(r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_SEARXNG_RESULT_BLOCK_PATTERN = re.compile(r"<article class=\"result[^\"]*\".*?</article>", re.IGNORECASE | re.DOTALL)
_SEARXNG_URL_HEADER_PATTERN = re.compile(r'<a[^>]+href="(?P<href>https?://[^"]+)"[^>]*class="url_header"', re.IGNORECASE)
_SEARXNG_TITLE_PATTERN = re.compile(r"<h3>\s*<a[^>]+>(?P<title>.*?)</a>\s*</h3>", re.IGNORECASE | re.DOTALL)
_SEARXNG_SNIPPET_PATTERN = re.compile(r'<p[^>]+class="content[^\"]*"[^>]*>(?P<content>.*?)</p>', re.IGNORECASE | re.DOTALL)
_DUCKDUCKGO_ANOMALY_MARKERS = (
    "anomaly-modal__title",
    "Unfortunately, bots use DuckDuckGo too.",
    "/anomaly.js?",
)
_SEARXNG_HTML_CHALLENGE_MARKERS = (
    "checking you are not a bot",
    "making sure you're not a bot",
    "verify you are human",
    "checking if the site connection is secure",
)


class SearchService(ABC):
    @abstractmethod
    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]: ...


class SearchRequestError(ProviderConfigurationError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SearXNGPoolSearchService(SearchService):
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._selected_instances = list(settings.searxng_selected_instances)
        self._pool_lock = asyncio.Lock()

    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]:
        instance_pool = await self._get_instance_pool()
        results, errors_by_instance = await self._search_instance_pool(
            instance_pool,
            task=task,
            limit=limit,
        )
        if results is not None:
            return results
        local_fallback_error: ProviderConfigurationError | None = None
        if self._settings.searxng_local_url:
            try:
                return await self._search_local_instance(task=task, limit=limit)
            except ProviderConfigurationError as exc:
                local_fallback_error = exc
        if _all_errors_are_access_throttling(errors_by_instance):
            refreshed_pool = await self._refresh_instance_pool(exclude_urls=instance_pool)
            results, errors_by_instance = await self._search_instance_pool(
                refreshed_pool,
                task=task,
                limit=limit,
            )
            if results is not None:
                return results

        detail_parts = [
            f"{instance_url}: {exc}" for instance_url, exc in errors_by_instance
        ]
        if local_fallback_error is not None and self._settings.searxng_local_url:
            detail_parts.append(f"{self._settings.searxng_local_url}/: {local_fallback_error}")

        details = "; ".join(
            detail_parts
        ) if detail_parts else "No instances were available."
        raise ProviderConfigurationError(f"SearXNG search failed across all selected instances: {details}")

    async def _get_instance_pool(self) -> list[str]:
        if self._selected_instances:
            return list(self._selected_instances)

        async with self._pool_lock:
            if self._selected_instances:
                return list(self._selected_instances)
            refreshed = await refresh_searxng_instance_pool(self._settings)
            self._selected_instances = refreshed["instances"]
            return list(self._selected_instances)

    async def _refresh_instance_pool(self, *, exclude_urls: list[str] | None = None) -> list[str]:
        refreshed = await refresh_searxng_instance_pool(self._settings, exclude_urls=exclude_urls)
        self._selected_instances = refreshed["instances"]
        return list(self._selected_instances)

    async def _search_instance_pool(
        self,
        instance_pool: list[str],
        *,
        task: PlanTask,
        limit: int,
    ) -> tuple[list[SearchResult] | None, list[tuple[str, ProviderConfigurationError]]]:
        errors_by_instance: list[tuple[str, ProviderConfigurationError]] = []

        for instance_url in random.sample(instance_pool, k=len(instance_pool)):
            try:
                response = await _get_json(
                    _build_searxng_search_url(instance_url, task.search_query),
                    headers={
                        "Accept": "application/json,text/plain,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": instance_url,
                        "User-Agent": self._settings.http_user_agent,
                    },
                )
                return (
                    _searxng_results_from_payload(
                        response,
                        instance_url=instance_url,
                        task=task,
                        limit=limit,
                    ),
                    [],
                )
            except ProviderConfigurationError as exc:
                errors_by_instance.append((instance_url, exc))

        return None, errors_by_instance

    async def _search_local_instance(self, *, task: PlanTask, limit: int) -> list[SearchResult]:
        assert self._settings.searxng_local_url is not None
        html = await _get_text(
            _build_searxng_html_search_url(self._settings.searxng_local_url, task.search_query),
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"{self._settings.searxng_local_url}/",
                "User-Agent": self._settings.http_user_agent,
            },
        )
        _raise_for_searxng_html_challenge(html, self._settings.searxng_local_url)
        return _searxng_results_from_html(
            html,
            instance_url=f"{self._settings.searxng_local_url}/",
            task=task,
            limit=limit,
        )


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
        except (asyncio.TimeoutError, TimeoutError) as exc:  # pragma: no cover - network availability
            raise ProviderConfigurationError(
                f"DuckDuckGo search timed out after 35s for query: {task.search_query}"
            ) from exc
        except error.HTTPError as exc:  # pragma: no cover - network availability
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ProviderConfigurationError(
                f"DuckDuckGo search failed with HTTP {exc.code}: {detail or 'no response body'}"
            ) from exc
        except error.URLError as exc:  # pragma: no cover - network availability
            raise ProviderConfigurationError(f"DuckDuckGo search failed: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - network availability
            raise ProviderConfigurationError(
                f"DuckDuckGo search failed unexpectedly: {exc}"
            ) from exc

        _raise_for_duckduckgo_anomaly(html, task.search_query)

        results: list[SearchResult] = []
        for match in _ANCHOR_PATTERN.finditer(html):
            href = unescape(match.group("href"))
            title = _clean_html(match.group("title"))
            if not title:
                continue
            parsed_href = parse.urlparse(href)
            if "duckduckgo.com" in parsed_href.netloc:
                if not parsed_href.path.startswith("/l/"):
                    continue
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
            raise SearchRequestError(
                f"Search request failed with HTTP {exc.code}: {detail}",
                status_code=exc.code,
            ) from exc
        except error.URLError as exc:  # pragma: no cover - provider/network behavior
            raise SearchRequestError(f"Search request failed: {exc.reason}") from exc

    task = asyncio.create_task(asyncio.to_thread(_send))
    try:
        return await asyncio.wait_for(task, timeout=35)
    except (asyncio.TimeoutError, TimeoutError):
        task.cancel()
        raise SearchRequestError(f"Search request timed out after 35s: {url}")


async def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    def _send() -> dict[str, Any]:
        req = urllib_request.Request(url, headers=headers or {}, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SearchRequestError(f"Search request returned invalid JSON: {url}") from exc
        except error.HTTPError as exc:  # pragma: no cover - provider/network behavior
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SearchRequestError(
                f"Search request failed with HTTP {exc.code}: {detail}",
                status_code=exc.code,
            ) from exc
        except error.URLError as exc:  # pragma: no cover - provider/network behavior
            raise SearchRequestError(f"Search request failed: {exc.reason}") from exc

    task = asyncio.create_task(asyncio.to_thread(_send))
    try:
        return await asyncio.wait_for(task, timeout=35)
    except (asyncio.TimeoutError, TimeoutError):
        task.cancel()
        raise SearchRequestError(f"Search request timed out after 35s: {url}")


async def _get_text(url: str, headers: dict[str, str] | None = None) -> str:
    def _send() -> str:
        req = urllib_request.Request(url, headers=headers or {}, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore")
        except error.HTTPError as exc:  # pragma: no cover - provider/network behavior
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SearchRequestError(
                f"Search request failed with HTTP {exc.code}: {detail}",
                status_code=exc.code,
            ) from exc
        except error.URLError as exc:  # pragma: no cover - provider/network behavior
            raise SearchRequestError(f"Search request failed: {exc.reason}") from exc

    task = asyncio.create_task(asyncio.to_thread(_send))
    try:
        return await asyncio.wait_for(task, timeout=35)
    except (asyncio.TimeoutError, TimeoutError):
        task.cancel()
        raise SearchRequestError(f"Search request timed out after 35s: {url}")


async def refresh_searxng_instance_pool(
    settings: AppSettings,
    *,
    exclude_urls: list[str] | None = None,
) -> dict[str, Any]:
    payload = await _get_json(
        settings.searxng_registry_url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.http_user_agent,
        },
    )
    instances = _select_searxng_instances(
        payload,
        pool_size=settings.searxng_pool_size,
        exclude_urls=exclude_urls,
    )
    selected_at = datetime.now(timezone.utc).isoformat()
    persisted_settings = load_persisted_app_settings()
    persisted_settings["searxng_selected_instances"] = instances
    persisted_settings["searxng_selected_at"] = selected_at
    save_persisted_app_settings(persisted_settings)
    return {
        "instances": instances,
        "selected_at": selected_at,
    }



def build_search_service(settings: AppSettings) -> SearchService:
    if settings.default_search_provider is SearchProvider.NONE:
        return DuckDuckGoSearchService(user_agent=settings.http_user_agent)
    if settings.default_search_provider is SearchProvider.SEARXNG:
        return SearXNGPoolSearchService(settings)
    if settings.default_search_provider is SearchProvider.TAVILY:
        if settings.tavily_api_key:
            return TavilySearchService(api_key=settings.tavily_api_key, user_agent=settings.http_user_agent)
        raise ProviderConfigurationError(
            "Tavily search requires DEEP_RESEARCH_TAVILY_API_KEY when DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER=tavily."
        )
    if settings.default_search_provider is SearchProvider.SERPER:
        if settings.serper_api_key:
            return SerperSearchService(api_key=settings.serper_api_key, user_agent=settings.http_user_agent)
        raise ProviderConfigurationError(
            "Serper search requires DEEP_RESEARCH_SERPER_API_KEY when DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER=serper."
        )
    raise ProviderConfigurationError(
        "Search provider `firecrawl` is not supported as a search backend in the MVP runtime. "
        "Use searxng, tavily, serper, or none."
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


def _raise_for_duckduckgo_anomaly(html: str, query: str) -> None:
    if any(marker in html for marker in _DUCKDUCKGO_ANOMALY_MARKERS):
        raise ProviderConfigurationError(
            "DuckDuckGo blocked the automated search with a human verification challenge "
            f"for query: {query}"
        )


def _select_searxng_instances(
    payload: dict[str, Any],
    *,
    pool_size: int,
    exclude_urls: list[str] | None = None,
) -> list[str]:
    instances = payload.get("instances")
    if not isinstance(instances, dict):
        raise ProviderConfigurationError("SearXNG registry payload does not contain a valid instances map.")

    excluded = {item for item in (exclude_urls or [])}
    candidates: list[str] = []
    for instance_url, metadata in instances.items():
        normalized_url = _normalize_searxng_instance_url(instance_url)
        if normalized_url is None:
            continue
        if normalized_url in excluded:
            continue
        if not _is_viable_searxng_instance(metadata):
            continue
        candidates.append(normalized_url)

    if not candidates and excluded:
        return _select_searxng_instances(payload, pool_size=pool_size)

    if not candidates:
        raise ProviderConfigurationError("SearXNG registry did not provide any viable public HTTPS instances.")

    sample_size = min(pool_size, len(candidates))
    return sorted(random.sample(candidates, k=sample_size))


def _all_errors_are_access_throttling(errors_by_instance: list[tuple[str, ProviderConfigurationError]]) -> bool:
    if not errors_by_instance:
        return False
    for _, exc in errors_by_instance:
        if not isinstance(exc, SearchRequestError):
            return False
        if exc.status_code not in {403, 418, 429}:
            return False
    return True


def _normalize_searxng_instance_url(instance_url: Any) -> str | None:
    if not isinstance(instance_url, str):
        return None
    normalized = instance_url.strip()
    if not normalized.startswith("https://"):
        return None
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return normalized


def _is_viable_searxng_instance(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("network_type") != "normal":
        return False
    if metadata.get("main") is False:
        return False
    http_metadata = metadata.get("http")
    if not isinstance(http_metadata, dict):
        return False
    if http_metadata.get("status_code") != 200:
        return False
    if http_metadata.get("error") not in (None, "", False):
        return False
    return True


def _build_searxng_search_url(instance_url: str, query: str) -> str:
    base_url = instance_url if instance_url.endswith("/") else f"{instance_url}/"
    params = parse.urlencode(
        {
            "q": query,
            "format": "json",
            "language": "all",
            "safesearch": 0,
        }
    )
    return f"{parse.urljoin(base_url, 'search')}?{params}"


def _build_searxng_html_search_url(instance_url: str, query: str) -> str:
    base_url = instance_url if instance_url.endswith("/") else f"{instance_url}/"
    params = parse.urlencode(
        {
            "q": query,
            "language": "all",
            "safesearch": 0,
        }
    )
    return f"{parse.urljoin(base_url, 'search')}?{params}"


def _searxng_results_from_payload(
    payload: dict[str, Any], *, instance_url: str, task: PlanTask, limit: int
) -> list[SearchResult]:
    results_payload = payload.get("results")
    if results_payload is None:
        raise ProviderConfigurationError(f"SearXNG instance returned an unexpected payload: {instance_url}")
    if not isinstance(results_payload, list):
        raise ProviderConfigurationError(f"SearXNG instance returned a non-list results payload: {instance_url}")

    results: list[SearchResult] = []
    for item in results_payload:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        title = item.get("title") or url
        canonical_url = canonicalize_url(url)
        if any(result.canonical_url == canonical_url for result in results):
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                canonical_url=canonical_url,
                provider=SearchProvider.SEARXNG,
                snippet=item.get("content"),
                metadata={
                    "task_query": task.search_query,
                    "query_fingerprint": stable_hash(task.search_query),
                    "instance_url": instance_url,
                    "engines": item.get("engines") or [],
                    "score": item.get("score"),
                },
            )
        )
        if len(results) >= limit:
            break
    return results


def _searxng_results_from_html(
    html: str,
    *,
    instance_url: str,
    task: PlanTask,
    limit: int,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in _SEARXNG_RESULT_BLOCK_PATTERN.finditer(html):
        article = block.group(0)
        url_match = _SEARXNG_URL_HEADER_PATTERN.search(article)
        title_match = _SEARXNG_TITLE_PATTERN.search(article)
        if url_match is None or title_match is None:
            continue
        url = unescape(url_match.group("href"))
        if not url.startswith(("http://", "https://")):
            continue
        title = _clean_html(title_match.group("title"))
        if not title:
            continue
        snippet_match = _SEARXNG_SNIPPET_PATTERN.search(article)
        snippet = _clean_html(snippet_match.group("content")) if snippet_match else None
        canonical_url = canonicalize_url(url)
        if any(result.canonical_url == canonical_url for result in results):
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                canonical_url=canonical_url,
                provider=SearchProvider.SEARXNG,
                snippet=snippet,
                metadata={
                    "task_query": task.search_query,
                    "query_fingerprint": stable_hash(task.search_query),
                    "instance_url": instance_url,
                    "search_mode": "html",
                },
            )
        )
        if len(results) >= limit:
            break
    return results


def _raise_for_searxng_html_challenge(html: str, instance_url: str) -> None:
    lowered = html.lower()
    if any(marker in lowered for marker in _SEARXNG_HTML_CHALLENGE_MARKERS):
        raise ProviderConfigurationError(
            f"SearXNG instance returned an anti-bot or access challenge page: {instance_url}"
        )
