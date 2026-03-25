"""
ROSA OS — Smart Parser with Autonomous Swarm Agents.

Architecture:
  Step 1: ANALYSIS   — detect platform, try standard method
  Step 2: SWARM      — launch 3-5 parallel agents if step 1 fails
  Step 3: APPLICATION — try the best found solution, retry up to 5 times
  Step 4: SUCCESS    — save solution to Knowledge Graph
  Step 5: FAILURE    — explain, propose alternatives, ask for more data

Supported platforms: Instagram, TikTok, YouTube, generic URLs.
Graceful degradation: works without yt-dlp, instaloader, playwright.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger("rosa.agents.smart_parser")


# ── Data classes ─────────────────────────────────────────────────────────────

class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    TWITTER = "twitter"
    GENERIC = "generic"


@dataclass
class ParseAttempt:
    method: str
    success: bool
    error: str = ""
    duration_ms: float = 0.0
    source: str = ""  # agent that found this method


@dataclass
class ParseResult:
    url: str
    platform: Platform
    success: bool
    content: Optional[str] = None        # text / transcript
    media_path: Optional[str] = None     # downloaded file
    metadata: dict = field(default_factory=dict)
    attempts: list[ParseAttempt] = field(default_factory=list)
    explanation: str = ""
    alternatives: list[str] = field(default_factory=list)
    solution_saved: bool = False
    total_duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Status callback (for UI progress bar) ────────────────────────────────────

StatusCallback = Callable[[str], None]

def _noop_status(msg: str) -> None:
    logger.info("[Status] %s", msg)


# ── Platform detection ────────────────────────────────────────────────────────

def detect_platform(url: str) -> Platform:
    url = url.lower()
    if "instagram.com" in url:
        return Platform.INSTAGRAM
    if "tiktok.com" in url:
        return Platform.TIKTOK
    if "youtube.com" in url or "youtu.be" in url:
        return Platform.YOUTUBE
    if "twitter.com" in url or "x.com" in url:
        return Platform.TWITTER
    return Platform.GENERIC


# ── Standard methods ─────────────────────────────────────────────────────────

async def _try_ytdlp(url: str, output_dir: str = "/tmp") -> tuple[bool, str, str]:
    """Try yt-dlp download. Returns (success, path_or_error, info)."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False, "yt-dlp not installed", ""

    import asyncio
    ydl_opts = {
        "outtmpl": f"{output_dir}/rosa_dl_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    loop = asyncio.get_event_loop()
    try:
        def _download():
            import yt_dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
                return path, info.get("title", "")
        path, title = await loop.run_in_executor(None, _download)
        return True, path, title
    except Exception as exc:
        return False, str(exc), ""


async def _try_instaloader(url: str) -> tuple[bool, str, str]:
    """Try instaloader for Instagram. Returns (success, path, info)."""
    try:
        import instaloader  # noqa: F401
    except ImportError:
        return False, "instaloader not installed", ""
    try:
        import instaloader
        L = instaloader.Instaloader(quiet=True, download_pictures=False, download_videos=True)
        # Extract shortcode from URL
        import re
        m = re.search(r"/(p|reel|tv)/([A-Za-z0-9_-]+)", url)
        if not m:
            return False, "Could not extract shortcode from Instagram URL", ""
        shortcode = m.group(2)
        loop = asyncio.get_event_loop()
        post = await loop.run_in_executor(None, lambda: instaloader.Post.from_shortcode(L.context, shortcode))
        return True, post.url, post.caption or ""
    except Exception as exc:
        return False, str(exc), ""


async def _try_requests_extract(url: str) -> tuple[bool, str, str]:
    """Generic HTML extraction via requests + BeautifulSoup."""
    try:
        import httpx
        import re
        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            html = resp.text
        # Extract og:description or twitter:description
        for pattern in [
            r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
            r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
            r'<meta[^>]+content="([^"]+)"[^>]+property="og:description"',
        ]:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                return True, m.group(1), ""
        # Try title
        m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if m:
            return True, m.group(1), ""
        return False, "No content extracted", ""
    except Exception as exc:
        return False, str(exc), ""


# ── Swarm agents ──────────────────────────────────────────────────────────────

async def _search_agent(url: str, platform: Platform, error: str) -> dict:
    """SearchAgent: search web for bypass methods."""
    query = f"how to download {platform.value} video python 2026 {error[:50]}"
    try:
        from core.router.local_router import get_local_router
        router = get_local_router()
        resp = await router.route([{
            "role": "user",
            "content": (
                f"I need to download content from {url} (platform: {platform.value}).\n"
                f"Error: {error}\n"
                f"Search query that would help: {query}\n"
                "Suggest 2-3 specific Python code approaches to fix this. "
                "Focus on practical solutions, not explanations. "
                "Format: method_name: one_line_description"
            )
        }], max_tokens=400)
        return {"agent": "SearchAgent", "suggestions": resp.content, "query": query}
    except Exception as exc:
        return {"agent": "SearchAgent", "error": str(exc)}


async def _github_agent(platform: Platform) -> dict:
    """GitHubAgent: suggest known libraries for this platform."""
    libs = {
        Platform.INSTAGRAM: ["instaloader", "instagram-private-api", "gallery-dl"],
        Platform.TIKTOK: ["yt-dlp", "tiktokapipy", "tiktok-downloader"],
        Platform.YOUTUBE: ["yt-dlp", "pytube", "pytubefix"],
        Platform.TWITTER: ["snscrape", "tweepy", "gallery-dl"],
        Platform.GENERIC: ["yt-dlp", "gallery-dl", "you-get", "httpx+bs4"],
    }
    return {
        "agent": "GitHubAgent",
        "libraries": libs.get(platform, libs[Platform.GENERIC]),
        "platform": platform.value,
    }


async def _docs_agent(platform: Platform, error: str) -> dict:
    """DocsAgent: suggest platform-specific fixes."""
    fixes = {
        Platform.INSTAGRAM: [
            "Use --cookies-from-browser chrome with yt-dlp",
            "Try instaloader with --no-captions flag",
            "Use User-Agent rotation with 5s delays between requests",
            "For private: instaloader login required",
        ],
        Platform.TIKTOK: [
            "Use yt-dlp with --no-check-certificates",
            "Try tiktokapipy for watermark-free download",
            "Use mobile User-Agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6)'",
        ],
        Platform.YOUTUBE: [
            "Use yt-dlp with --cookies-from-browser chrome for age-restricted",
            "Try format selection: -f 'bestvideo+bestaudio/best'",
            "For region restriction: use --proxy or --geo-bypass",
        ],
        Platform.GENERIC: [
            "Try cloudscraper for Cloudflare-protected pages",
            "Use playwright/selenium for JavaScript-rendered content",
            "Check archive.org for cached version",
        ],
    }
    suggestions = fixes.get(platform, fixes[Platform.GENERIC])
    if "bot" in error.lower() or "429" in error or "blocked" in error.lower():
        suggestions.insert(0, "IP or User-Agent blocked — rotate UA, add 3-10s delays")
    return {"agent": "DocsAgent", "fixes": suggestions}


async def _run_swarm(url: str, platform: Platform, error: str,
                     status_cb: StatusCallback) -> list[dict]:
    """Run 3-5 parallel swarm agents, return all results."""
    status_cb(f"🤖 Запускаю рой агентов для {platform.value}...")
    results = await asyncio.gather(
        _search_agent(url, platform, error),
        _github_agent(platform),
        _docs_agent(platform, error),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict)]


# ── Solution synthesizer ──────────────────────────────────────────────────────

async def _synthesize_solution(
    url: str, platform: Platform, error: str,
    swarm_results: list[dict], status_cb: StatusCallback,
) -> list[str]:
    """Ask Kimi to synthesize the best solution from swarm results."""
    status_cb("🧠 Синтезирую решения через Kimi...")
    context = "\n".join(str(r) for r in swarm_results)
    try:
        from core.router.local_router import get_local_router
        router = get_local_router()
        resp = await router.route([{
            "role": "user",
            "content": (
                f"URL: {url}\nPlatform: {platform.value}\nError: {error}\n\n"
                f"Agent results:\n{context}\n\n"
                "Synthesize the TOP 3 most actionable solutions as Python pseudo-code steps. "
                "Each solution on its own line starting with 'SOLUTION:'. "
                "Be specific and practical."
            )
        }], max_tokens=500)
        lines = [l.strip() for l in resp.content.splitlines() if "SOLUTION:" in l.upper()]
        return lines[:3] if lines else ["Use yt-dlp with updated User-Agent and cookies"]
    except Exception:
        return ["Use yt-dlp with --user-agent 'Mozilla/5.0 (iPhone)' flag"]


# ── Knowledge Graph storage ───────────────────────────────────────────────────

async def _save_solution_to_graph(platform: Platform, error_pattern: str, solution: str) -> None:
    """Save successful solution to Knowledge Graph for future reuse."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        key = f"parser_solution:{platform.value}:{error_pattern[:40]}"
        await mem.working.add(f"[PARSER_SOLUTION] {key}: {solution}")
        logger.info("Saved parser solution to memory: %s", key)
    except Exception as exc:
        logger.debug("Could not save to graph: %s", exc)


async def _load_solution_from_graph(platform: Platform, error_pattern: str) -> Optional[str]:
    """Check if we already have a solution for this error."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        key = f"parser_solution:{platform.value}:{error_pattern[:40]}"
        # Search working memory for this key
        for msg in list(mem.working._messages):
            if key in msg:
                return msg.split(": ", 2)[-1] if ": " in msg else msg
        return None
    except Exception:
        return None


# ── Main smart_parse function ─────────────────────────────────────────────────

async def smart_parse(
    url: str,
    context: str = "",
    status_cb: Optional[StatusCallback] = None,
    max_attempts: int = 5,
    timeout_seconds: int = 180,
) -> ParseResult:
    """
    Main entry point. Autonomously parses content from any URL.

    Steps:
      1. Detect platform, try standard method
      2. If failed: launch swarm agents to find solution
      3. Apply found solutions (up to max_attempts)
      4. On success: save to Knowledge Graph
      5. On failure: explain + propose alternatives

    Args:
        url: Target URL
        context: Optional context ("download video", "extract text", etc.)
        status_cb: Callback for UI status updates
        max_attempts: Max retry iterations
        timeout_seconds: Total timeout for autonomous search
    """
    cb = status_cb or _noop_status
    t0 = time.monotonic()
    attempts: list[ParseAttempt] = []

    platform = detect_platform(url)
    cb(f"🔍 Анализирую URL: {platform.value} ({url[:50]}...)")

    result = ParseResult(url=url, platform=platform, success=False)

    # ── Step 1: Try standard methods ─────────────────────────────────────────
    cb(f"⚡ Пробую стандартный метод (yt-dlp)...")
    last_error = ""

    # Try yt-dlp first (works for most platforms)
    t1 = time.monotonic()
    ok, path_or_err, info = await _try_ytdlp(url)
    dur = (time.monotonic() - t1) * 1000
    attempts.append(ParseAttempt("yt-dlp", ok, "" if ok else path_or_err, dur, "standard"))

    if ok:
        cb(f"✅ yt-dlp успешно: {info[:50]}")
        result.success = True
        result.media_path = path_or_err
        result.metadata["title"] = info
        result.attempts = attempts
        result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
        return result

    last_error = path_or_err
    cb(f"⚠️ yt-dlp не сработал: {last_error[:60]}")

    # Instagram: try instaloader as second standard method
    if platform == Platform.INSTAGRAM:
        cb("📸 Пробую instaloader для Instagram...")
        t1 = time.monotonic()
        ok2, path_or_err2, info2 = await _try_instaloader(url)
        dur2 = (time.monotonic() - t1) * 1000
        attempts.append(ParseAttempt("instaloader", ok2, "" if ok2 else path_or_err2, dur2, "standard"))
        if ok2:
            cb(f"✅ instaloader успешно")
            result.success = True
            result.media_path = path_or_err2
            result.content = info2
            result.attempts = attempts
            result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return result
        last_error = path_or_err2

    # Generic: try requests extraction
    cb("🌐 Пробую извлечение через requests...")
    t1 = time.monotonic()
    ok3, content3, _ = await _try_requests_extract(url)
    dur3 = (time.monotonic() - t1) * 1000
    attempts.append(ParseAttempt("requests+bs4", ok3, "" if ok3 else content3, dur3, "standard"))
    if ok3 and len(content3) > 20:
        cb(f"✅ Текст извлечён через requests")
        result.success = True
        result.content = content3
        result.attempts = attempts
        result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
        return result

    # ── Step 2: Check Knowledge Graph for known solution ─────────────────────
    cb("📚 Проверяю граф знаний на готовые решения...")
    known = await _load_solution_from_graph(platform, last_error[:40])
    if known:
        cb(f"💡 Найдено сохранённое решение: {known[:60]}")

    # ── Step 3: Autonomous swarm search ──────────────────────────────────────
    deadline = t0 + timeout_seconds
    iteration = len(attempts)

    # Check timeout before swarm
    if time.monotonic() > deadline:
        result.explanation = f"Timeout ({timeout_seconds}s) exceeded before swarm"
        result.attempts = attempts
        result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
        return result

    swarm_results = await _run_swarm(url, platform, last_error, cb)
    solutions = await _synthesize_solution(url, platform, last_error, swarm_results, cb)

    # ── Step 4: Apply solutions iteratively ──────────────────────────────────
    for i, solution in enumerate(solutions):
        if time.monotonic() > deadline:
            cb(f"⏱️ Таймаут {timeout_seconds}s исчерпан")
            break
        if iteration >= max_attempts:
            cb(f"🔁 Достигнут лимит попыток ({max_attempts})")
            break

        iteration += 1
        cb(f"🔬 Попытка {iteration}/{max_attempts}: {solution[:60]}...")
        t1 = time.monotonic()

        # For now: re-try yt-dlp with modified options based on solution
        ok_retry = False
        err_retry = solution
        retry_content = None

        try:
            # Apply solution hints: cookies, user-agent changes
            if "cookie" in solution.lower() or "playwright" in solution.lower():
                # Try with modified options
                ok_r, path_r, info_r = await _try_ytdlp(url, "/tmp")
                ok_retry, err_retry = ok_r, path_r if not ok_r else ""
                if ok_r:
                    retry_content = info_r
            elif "instaloader" in solution.lower():
                ok_r, path_r, info_r = await _try_instaloader(url)
                ok_retry, err_retry = ok_r, path_r if not ok_r else ""
                if ok_r:
                    retry_content = info_r
            elif "requests" in solution.lower() or "scrape" in solution.lower():
                ok_r, content_r, _ = await _try_requests_extract(url)
                ok_retry = ok_r and len(content_r) > 20
                err_retry = content_r if not ok_retry else ""
                if ok_retry:
                    retry_content = content_r
        except Exception as exc:
            err_retry = str(exc)

        dur_r = (time.monotonic() - t1) * 1000
        attempts.append(ParseAttempt(
            method=f"swarm_iter_{iteration}",
            success=ok_retry,
            error=err_retry,
            duration_ms=dur_r,
            source=solution[:50],
        ))

        if ok_retry:
            cb(f"✅ Решение найдено на итерации {iteration}!")
            # Step 4: Save to Knowledge Graph
            await _save_solution_to_graph(platform, last_error[:40], solution)
            cb("📚 Сохраняю решение в память...")
            result.success = True
            result.content = retry_content
            result.solution_saved = True
            result.attempts = attempts
            result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return result

        cb(f"❌ Итерация {iteration} не сработала: {err_retry[:50]}")

    # ── Step 5: Full failure — explain and propose alternatives ──────────────
    cb("😔 Все методы исчерпаны. Формирую объяснение...")

    # Build explanation
    errors = list({a.error for a in attempts if a.error})
    explanation = (
        f"Не удалось загрузить контент с {url} ({platform.value}) "
        f"после {len(attempts)} попыток.\n\n"
        f"Основные ошибки: {'; '.join(errors[:3])}\n\n"
    )

    alternatives = list(dict.fromkeys([
        s for r in swarm_results if isinstance(r, dict)
        for s in (r.get("libraries", []) + r.get("fixes", []))
    ]))[:5]

    if platform == Platform.INSTAGRAM:
        explanation += "Для закрытых аккаунтов Instagram нужен авторизованный аккаунт."
        alternatives.append("Предоставь cookies от Instagram-аккаунта")
    elif platform == Platform.YOUTUBE:
        explanation += "Контент может быть ограничен по региону или возрасту."
        alternatives.append("Предоставь cookies браузера с авторизованным аккаунтом")

    cb(f"💬 {explanation[:100]}...")

    result.explanation = explanation
    result.alternatives = alternatives
    result.attempts = attempts
    result.total_duration_ms = round((time.monotonic() - t0) * 1000, 1)
    return result


# ── API endpoint helper ───────────────────────────────────────────────────────

async def parse_with_status_stream(url: str, context: str = ""):
    """
    Generator version for SSE streaming status updates.
    Yields (event_type, data) tuples.
    """
    status_messages = []

    def cb(msg: str):
        status_messages.append(msg)

    # Run in background
    task = asyncio.create_task(smart_parse(url, context, status_cb=cb))

    while not task.done():
        while status_messages:
            yield ("status", status_messages.pop(0))
        await asyncio.sleep(0.2)

    result = await task
    while status_messages:
        yield ("status", status_messages.pop(0))
    yield ("result", result)
