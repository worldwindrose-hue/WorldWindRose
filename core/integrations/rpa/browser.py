"""
ROSA OS — Browser RPA Stub (Playwright).

Stub implementation for browser automation.
Requires: pip install playwright && playwright install

Provides safe, sandboxed browser automation for:
- Web scraping
- Form filling
- Screenshot capture of web pages
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.integrations.rpa.browser")


def is_available() -> bool:
    """Check if Playwright is installed."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


async def get_page_text(url: str, wait_for: str = "load") -> dict[str, Any]:
    """
    Navigate to URL and extract all visible text.

    Returns:
        {"success": bool, "text": str, "title": str, "url": str}
    """
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc or url
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.BROWSING, f"Открываю {domain}", url=url)
    except Exception:
        pass

    if not is_available():
        # Fallback to httpx for simple text extraction
        return await _httpx_fallback(url)

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until=wait_for, timeout=30000)
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()

        return {
            "success": True,
            "text": text[:10000],
            "title": title,
            "url": url,
        }
    except Exception as exc:
        logger.error("Browser get_page_text failed for %s: %s", url, exc)
        return {"success": False, "error": str(exc), "text": "", "title": "", "url": url}


async def take_screenshot(
    url: str,
    full_page: bool = True,
) -> dict[str, Any]:
    """
    Navigate to URL and take a screenshot.

    Returns:
        {"success": bool, "base64": str, "title": str}
    """
    if not is_available():
        return {"success": False, "error": "Playwright not installed. Run: pip install playwright && playwright install", "base64": ""}

    try:
        import base64
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="load", timeout=30000)
            title = await page.title()
            img_bytes = await page.screenshot(full_page=full_page)
            await browser.close()

        return {
            "success": True,
            "base64": base64.b64encode(img_bytes).decode(),
            "title": title,
            "url": url,
        }
    except Exception as exc:
        logger.error("Browser screenshot failed for %s: %s", url, exc)
        return {"success": False, "error": str(exc), "base64": ""}


async def fill_form(url: str, fields: dict[str, str], submit_selector: str | None = None) -> dict[str, Any]:
    """
    Fill a web form with provided fields.
    ⚠️ REQUIRES explicit user confirmation before use.

    Args:
        url: Form URL
        fields: {"css_selector": "value"} mapping
        submit_selector: CSS selector for submit button (None = don't submit)
    """
    if not is_available():
        return {"success": False, "error": "Playwright not installed", "filled": 0}

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="load", timeout=30000)

            filled = 0
            for selector, value in fields.items():
                try:
                    await page.fill(selector, value)
                    filled += 1
                except Exception as exc:
                    logger.debug("Field fill failed for %s: %s", selector, exc)

            submitted = False
            if submit_selector:
                try:
                    await page.click(submit_selector)
                    await page.wait_for_load_state("load")
                    submitted = True
                except Exception as exc:
                    logger.warning("Form submit failed: %s", exc)

            await browser.close()

        return {
            "success": True,
            "url": url,
            "filled": filled,
            "submitted": submitted,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "filled": 0, "submitted": False}


async def _httpx_fallback(url: str) -> dict[str, Any]:
    """Simple HTTP fallback when Playwright is not available."""
    try:
        import httpx
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            # Remove script and style
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            title = soup.find("title")
            title_text = title.string if title else ""
            return {
                "success": True,
                "text": text[:10000],
                "title": title_text,
                "url": url,
            }
    except Exception as exc:
        return {"success": False, "error": str(exc), "text": "", "title": "", "url": url}
