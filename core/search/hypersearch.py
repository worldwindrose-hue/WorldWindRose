"""
ROSA OS — HyperSearch Engine (Phase 4).

Parallel multi-source search:
1. DuckDuckGo (free, always available)
2. Wikipedia API
3. HackerNews API
4. GitHub Search API
5. ArXiv API
6. Perplexity API (if key available)

Results ranked by freshness + relevance + authority.
Synthesized by Kimi K2.5 into a coherent answer.
Saved to Knowledge Graph.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger("rosa.search.hypersearch")


# ── Individual source searchers ───────────────────────────────────────────────

async def _search_duckduckgo(query: str) -> list[dict[str, Any]]:
    """Search via DuckDuckGo instant answers API (no key needed)."""
    try:
        import httpx
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            data = r.json()
        results = []
        # Abstract
        if data.get("AbstractText"):
            results.append({
                "source": "duckduckgo",
                "title": data.get("Heading", query),
                "text": data["AbstractText"][:500],
                "url": data.get("AbstractURL", ""),
                "score": 0.9,
            })
        # Related topics
        for topic in data.get("RelatedTopics", [])[:5]:
            text = topic.get("Text", "")
            if text:
                results.append({
                    "source": "duckduckgo",
                    "title": text[:80],
                    "text": text[:300],
                    "url": topic.get("FirstURL", ""),
                    "score": 0.6,
                })
        return results
    except Exception as exc:
        logger.debug("DuckDuckGo search failed: %s", exc)
        return []


async def _search_wikipedia(query: str) -> list[dict[str, Any]]:
    """Search Wikipedia API."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            # Search
            r = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 3},
            )
            data = r.json()
        items = data.get("query", {}).get("search", [])
        results = []
        for item in items:
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
            results.append({
                "source": "wikipedia",
                "title": item.get("title", ""),
                "text": snippet[:400],
                "url": f"https://en.wikipedia.org/wiki/{item['title'].replace(' ', '_')}",
                "score": 0.75,
            })
        return results
    except Exception as exc:
        logger.debug("Wikipedia search failed: %s", exc)
        return []


async def _search_hackernews(query: str) -> list[dict[str, Any]]:
    """Search HackerNews via Algolia API."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": query, "tags": "story", "hitsPerPage": 5},
            )
            data = r.json()
        results = []
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            url = hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID')}")
            results.append({
                "source": "hackernews",
                "title": title,
                "text": f"{title} (HN: {hit.get('num_comments', 0)} comments, {hit.get('points', 0)} pts)",
                "url": url,
                "score": 0.65,
            })
        return results
    except Exception as exc:
        logger.debug("HackerNews search failed: %s", exc)
        return []


async def _search_arxiv(query: str) -> list[dict[str, Any]]:
    """Search ArXiv for scientific papers."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "http://export.arxiv.org/api/query",
                params={"search_query": f"all:{query}", "max_results": 3, "sortBy": "relevance"},
            )
        # Parse minimal XML
        entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.DOTALL)
        results = []
        for entry in entries:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link = re.search(r'<id>(.*?)</id>', entry)
            if title and summary:
                results.append({
                    "source": "arxiv",
                    "title": title.group(1).strip().replace("\n", " "),
                    "text": summary.group(1).strip()[:400].replace("\n", " "),
                    "url": link.group(1).strip() if link else "",
                    "score": 0.8,
                })
        return results
    except Exception as exc:
        logger.debug("ArXiv search failed: %s", exc)
        return []


async def _search_github(query: str) -> list[dict[str, Any]]:
    """Search GitHub repos."""
    try:
        import httpx
        from core.config import get_settings
        settings = get_settings()
        headers = {"Accept": "application/vnd.github+json"}
        if getattr(settings, "github_token", ""):
            headers["Authorization"] = f"Bearer {settings.github_token}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "per_page": 3},
                headers=headers,
            )
            data = r.json()
        results = []
        for repo in data.get("items", []):
            results.append({
                "source": "github",
                "title": repo.get("full_name", ""),
                "text": f"{repo.get('description', '')} ⭐{repo.get('stargazers_count', 0)}",
                "url": repo.get("html_url", ""),
                "score": 0.7,
            })
        return results
    except Exception as exc:
        logger.debug("GitHub search failed: %s", exc)
        return []


# ── HyperSearch ───────────────────────────────────────────────────────────────

_SYNTHESIS_PROMPT = """На основе результатов поиска ответь на вопрос максимально полно.
Вопрос: {query}

Результаты поиска:
{results}

Дай структурированный ответ с указанием источников."""


class HyperSearch:
    """Parallel multi-source search with LLM synthesis."""

    async def search(
        self,
        query: str,
        depth: str = "normal",
        sources: list[str] | None = None,
        synthesize: bool = True,
    ) -> dict[str, Any]:
        """
        Parallel search across all available sources.
        depth: "fast" (DDG+Wiki only), "normal" (all free), "deep" (all + GitHub + ArXiv)
        """
        try:
            from core.status.tracker import set_status, RosaStatus
            set_status(RosaStatus.ACTING, f"Ищу: {query[:60]}")
        except Exception:
            pass

        # Select sources based on depth
        search_tasks = [
            _search_duckduckgo(query),
            _search_wikipedia(query),
        ]
        if depth in ("normal", "deep") or not sources:
            search_tasks.append(_search_hackernews(query))
        if depth == "deep" or (sources and "arxiv" in sources):
            search_tasks.append(_search_arxiv(query))
        if depth == "deep" or (sources and "github" in sources):
            search_tasks.append(_search_github(query))

        all_results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)

        all_results: list[dict] = []
        for r in all_results_lists:
            if isinstance(r, list):
                all_results.extend(r)

        # Sort by score
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = all_results[:10]

        synthesis = ""
        if synthesize and top:
            synthesis = await self._synthesize(query, top)
            # Save to knowledge graph
            try:
                from core.knowledge.graph import add_insight
                await add_insight(
                    text=f"Search: {query}\n\n{synthesis[:1000]}",
                    metadata={"source": "hypersearch", "query": query},
                    session_id="search",
                )
            except Exception:
                pass

        try:
            from core.status.tracker import set_status, RosaStatus
            set_status(RosaStatus.ONLINE, "Готова к работе")
        except Exception:
            pass

        return {
            "query": query,
            "results": top,
            "synthesis": synthesis,
            "total_results": len(all_results),
            "sources_used": list({r["source"] for r in top}),
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _synthesize(self, query: str, results: list[dict]) -> str:
        results_text = "\n\n".join(
            f"[{r['source'].upper()}] {r['title']}: {r['text']}"
            for r in results
        )
        try:
            from openai import AsyncOpenAI
            from core.config import get_settings
            settings = get_settings()
            client = AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
            resp = await client.chat.completions.create(
                model=settings.default_model,
                messages=[{
                    "role": "user",
                    "content": _SYNTHESIS_PROMPT.format(query=query, results=results_text),
                }],
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.debug("HyperSearch synthesis failed: %s", exc)
            return "\n".join(f"• {r['title']}: {r['text'][:100]}" for r in results[:5])


_hypersearch: HyperSearch | None = None


def get_hypersearch() -> HyperSearch:
    global _hypersearch
    if _hypersearch is None:
        _hypersearch = HyperSearch()
    return _hypersearch
