import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Manages Playwright browser contexts synchronously across extractors.
    - Synchronous Playwright lifecycle management
    - Cookie persistence per source
    - Viewport and timeout normalization
    - Graceful error handling and shutdown
    """

    def __init__(self):
        self._pw = None
        self._browser = None
        self._contexts: Dict[str, Any] = {}
        self.cookie_dir = Path(__file__).resolve().parent.parent / "data" / "raw"

    def _ensure_event_loop_windows(self):
        if sys.platform == "win32":
            import asyncio
            try:
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
            except Exception:
                pass

    def start(self):
        if self._browser is not None:
            return self._browser

        self._ensure_event_loop_windows()
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=bool(getattr(settings, "playwright_headless", True)),
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            return self._browser
        except Exception as e:
            logger.warning(f"Could not initialize Playwright browser: {e}")
            self.close()
            return None

    def get_cookie_path(self, source: str) -> Path:
        source_dir = self.cookie_dir / source
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir / ".cookies.json"

    def load_cookies(self, source: str, context: Any) -> bool:
        c_path = self.get_cookie_path(source)
        if c_path.exists():
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    if cookies and isinstance(cookies, list):
                        context.add_cookies(cookies)
                        return True
            except Exception as e:
                logger.debug(f"Failed to load cookies for {source}: {e}")
        return False

    def save_cookies(self, source: str, context: Any) -> bool:
        try:
            cookies = context.cookies()
            c_path = self.get_cookie_path(source)
            with open(c_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            return True
        except Exception as e:
            logger.debug(f"Failed to save cookies for {source}: {e}")
            return False

    def get_context(self, source: str, width: int = 1600, height: int = 950) -> Optional[Any]:
        if source in self._contexts:
            return self._contexts[source]

        if not self._browser:
            self.start()
        if not self._browser:
            return None

        try:
            ctx = self._browser.new_context(
                viewport={"width": width, "height": height},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self.load_cookies(source, ctx)
            self._contexts[source] = ctx
            return ctx
        except Exception as e:
            logger.error(f"Error creating browser context for {source}: {e}")
            return None

    def close(self):
        for s, ctx in list(self._contexts.items()):
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts.clear()

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
