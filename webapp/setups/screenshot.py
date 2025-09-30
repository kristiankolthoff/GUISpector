from typing import Optional
import asyncio
from playwright.async_api import async_playwright


class PlaywrightScreenshotter:
    """Simple helper to capture a full-page PNG screenshot for a given URL using headless Chromium."""

    def __init__(self, viewport_width: int = 1280, viewport_height: int = 800, timeout_ms: int = 30000) -> None:
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms = timeout_ms

    async def _capture_to_bytes_async(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                ])
                context = await browser.new_context(viewport={"width": self.viewport_width, "height": self.viewport_height})
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                await page.wait_for_load_state("domcontentloaded")
                image_bytes = await page.screenshot(full_page=True, type="png")
                await context.close()
                await browser.close()
                return image_bytes
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    def capture_to_bytes(self, url: str) -> Optional[bytes]:
        """Navigate to the URL and return a PNG screenshot as bytes. Returns None on failure."""
        try:
            return asyncio.run(self._capture_to_bytes_async(url))
        except RuntimeError:
            # If an event loop is already running (e.g., within certain servers), use a dedicated loop
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self._capture_to_bytes_async(url))
            finally:
                try:
                    loop.close()
                finally:
                    asyncio.set_event_loop(None)


