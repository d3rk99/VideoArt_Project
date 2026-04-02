from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from installation_app.config import ComfyUIConfig

QUEUE_BUTTON_SELECTORS = [
    "button:has-text('Queue Prompt')",
    "button:has-text('Queue')",
    "button:has-text('Run')",
]


class ComfyUIBrowserTrigger:
    def __init__(self, config: ComfyUIConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Page | None = None

    def initialize(self) -> None:
        if self._page:
            return

        self._playwright = sync_playwright().start()
        browser_launcher = getattr(self._playwright, self.config.playwright_browser)
        self._browser = browser_launcher.launch(headless=self.config.playwright_headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.config.page_load_timeout_ms)
        self._page.goto(self.config.browser_url, wait_until="domcontentloaded")
        self._page.wait_for_load_state("networkidle")
        self.logger.info("Initialized ComfyUI browser trigger at %s", self.config.browser_url)

    def queue_current_workflow(self) -> None:
        self.initialize()
        last_error: Exception | None = None

        for attempt in range(1, self.config.ui_trigger_retry_count + 2):
            try:
                assert self._page is not None
                self._page.bring_to_front()
                self._page.wait_for_load_state("domcontentloaded")
                self._page.keyboard.press("Control+Enter")
                time.sleep(self.config.ui_trigger_delay_ms / 1000)
                self.logger.info("Triggered ComfyUI queue via Ctrl+Enter (attempt %s)", attempt)
                return
            except PlaywrightError as exc:
                last_error = exc
                self.logger.warning(
                    "Ctrl+Enter trigger failed (attempt %s/%s): %s",
                    attempt,
                    self.config.ui_trigger_retry_count + 1,
                    exc,
                )

                if self._try_click_fallback():
                    self.logger.info("Triggered ComfyUI queue via button-click fallback")
                    return

        raise RuntimeError(f"ComfyUI browser trigger failed after retries: {last_error}")

    def _try_click_fallback(self) -> bool:
        if not self._page:
            return False

        for selector in QUEUE_BUTTON_SELECTORS:
            try:
                button = self._page.locator(selector).first
                if button.is_visible(timeout=1200):
                    button.click(timeout=1500)
                    time.sleep(self.config.ui_trigger_delay_ms / 1000)
                    return True
            except PlaywrightError:
                continue
        return False

    def shutdown(self) -> None:
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._page = None
