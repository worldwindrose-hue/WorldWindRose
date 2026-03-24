"""
ROSA OS — Web Handler.

Fetches and converts any URL to markdown text.
Has specialized extractors for Wikipedia, ArXiv, Reddit, and Twitter/X.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.web")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ROSABot/5.0; +https://rosa-os.ai)",
    "Accept-Language": "ru,en;q=0.9",
}
_TIMEOUT = 30


class WebHandler(BaseHandler):
    """Fetch and ingest any URL into the knowledge graph."""

    async def process(self, job) -> IngestResult:
        url = job.source
        self.update_progress(job, 5, f"Загружаю {url[:60]}...")
        try:
            host = urlparse(url).hostname or ""
            if "wikipedia.org" in host:
                text, title = await self._fetch_wikipedia(url)
            elif "arxiv.org" in host:
                text, title = await self._fetch_arxiv(url)
            elif "reddit.com" in host:
                text, title = await self._fetch_reddit(url)
            elif "twitter.com" in host or "x.com" in host:
                text, title = await self._fetch_generic(url)
            else:
                text, title = await self._fetch_generic(url)

            if not text.strip():
                raise ValueError("Страница не содержит текста")

            self.update_progress(job, 70, "Сохраняю...")
            chunks = self.chunk(text)
            tags = ["web", self._domain_tag(host)]
            nodes = await self.save_to_graph(
                chunks, source=url, tags=tags, extra_meta={"title": title, "host": host}
            )

            self.update_progress(job, 100)
            return IngestResult(
                type="url",
                source=url,
                nodes_created=nodes,
                chunks=len(chunks),
                summary=f"✅ {title[:60]}: {len(chunks)} чанков → {nodes} узлов",
                metadata={"title": title, "host": host},
            )
        except Exception as exc:
            logger.error("Web ingest failed for %s: %s", url, exc)
            raise

    async def _fetch_generic(self, url: str) -> tuple[str, str]:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return self._html_to_text(r.text, url), self._extract_title(r.text)

    async def _fetch_wikipedia(self, url: str) -> tuple[str, str]:
        # Use Wikipedia API for cleaner text
        match = re.search(r"/wiki/([^#?]+)", url)
        if not match:
            return await self._fetch_generic(url)
        title = match.group(1)
        lang = urlparse(url).hostname.split(".")[0]
        api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(api_url)
                if r.status_code == 200:
                    data = r.json()
                    summary = data.get("extract", "")
                    page_title = data.get("title", title)
                    # Also get full content
                    content_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/plain/{title}"
                    r2 = await client.get(content_url)
                    if r2.status_code == 200:
                        return r2.text, page_title
                    return summary, page_title
        except Exception:
            pass
        return await self._fetch_generic(url)

    async def _fetch_arxiv(self, url: str) -> tuple[str, str]:
        # Extract paper ID and use ArXiv API
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", url)
        if not match:
            return await self._fetch_generic(url)
        arxiv_id = match.group(1)
        api_url = f"https://export.arxiv.org/abs/{arxiv_id}"
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT) as client:
            r = await client.get(api_url)
            r.raise_for_status()
            text = self._html_to_text(r.text, url)
            title = self._extract_title(r.text)
            return text, title

    async def _fetch_reddit(self, url: str) -> tuple[str, str]:
        # Use Reddit JSON API
        json_url = url.rstrip("/") + ".json?limit=100"
        async with httpx.AsyncClient(
            headers={**_HEADERS, "User-Agent": "ROSABot/5.0"},
            timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            r = await client.get(json_url)
            if r.status_code == 200:
                try:
                    data = r.json()
                    parts = []
                    post = data[0]["data"]["children"][0]["data"]
                    title = post.get("title", "Reddit post")
                    if post.get("selftext"):
                        parts.append(f"# {title}\n\n{post['selftext']}")
                    comments = data[1]["data"]["children"]
                    for c in comments[:20]:
                        cd = c.get("data", {})
                        if cd.get("body") and cd.get("body") != "[deleted]":
                            parts.append(cd["body"])
                    return "\n\n---\n\n".join(parts), title
                except Exception:
                    pass
        return await self._fetch_generic(url)

    def _html_to_text(self, html: str, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # Try article/main first
            for selector in ["article", "main", '[role="main"]', ".content", "#content"]:
                el = soup.select_one(selector)
                if el:
                    return el.get_text(separator="\n", strip=True)
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            import html as html_lib
            clean = re.sub(r"<[^>]+>", " ", html)
            return html_lib.unescape(re.sub(r"\s+", " ", clean)).strip()

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        return match.group(1).strip() if match else "Веб-страница"

    def _domain_tag(self, host: str) -> str:
        parts = (host or "").split(".")
        return parts[-2] if len(parts) >= 2 else "web"
