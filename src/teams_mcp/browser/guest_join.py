"""Launch headless Chromium and join a Teams meeting as a named guest.

This module uses Playwright to:
  1. Navigate to a Teams meeting join URL
  2. Fill in the guest display name
  3. Disable mic/cam initially (we inject our own media)
  4. Click "Join now"
  5. Wait for the meeting stage to load

No Azure registration required — uses the anonymous guest join flow.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("teams_mcp.browser.guest_join")

# Lazy import — only pulled in when a persona session starts.
_playwright_mod: Any = None


async def _get_playwright():
    global _playwright_mod
    if _playwright_mod is None:
        from playwright.async_api import async_playwright
        _playwright_mod = async_playwright
    return _playwright_mod


class PersonaBrowser:
    """Manages a headless Chromium instance joined to a Teams meeting."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._pw: Any = None           # Playwright context manager
        self._browser: Any = None       # Browser instance
        self._page: Any = None          # Active page
        self._context: Any = None       # Browser context
        self.joined = False
        self.display_name: str = ""
        self.join_url: str = ""

    async def launch(
        self,
        join_url: str,
        display_name: str,
        face_video_path: Optional[str] = None,
        headless: bool = True,
        chrome_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Launch browser and join the Teams meeting as guest.

        Parameters
        ----------
        join_url : str
            Full Teams meeting join URL.
        display_name : str
            Name shown in the meeting participant list.
        face_video_path : str, optional
            Path to MJPEG/Y4M file for fake video capture.
        headless : bool
            Run Chromium in headless mode (default True).
        chrome_path : str, optional
            Custom Chromium executable path.

        Returns
        -------
        dict with join status info.
        """
        self.join_url = join_url
        self.display_name = display_name

        pw_factory = await _get_playwright()
        self._pw = await pw_factory().start()

        # Chrome flags for media overrides
        args = [
            "--disable-blink-features=AutomationControlled",
            "--use-fake-ui-for-media-stream",         # auto-allow cam/mic
            "--use-fake-device-for-media-stream",      # use fake devices
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
        ]

        if face_video_path and Path(face_video_path).exists():
            args.append(f"--use-file-for-fake-video-capture={face_video_path}")
            log.info("Using fake video file: %s", face_video_path)

        launch_opts: Dict[str, Any] = {
            "headless": headless,
            "args": args,
        }
        if chrome_path:
            launch_opts["executable_path"] = chrome_path

        self._browser = await self._pw.chromium.launch(**launch_opts)
        self._context = await self._browser.new_context(
            permissions=["camera", "microphone"],
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()

        log.info("Navigating to Teams meeting: %s", join_url[:80])
        await self._page.goto(join_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for the guest join form to appear
        await self._wait_and_join(display_name)

        return {
            "session_id": self.session_id,
            "status": "joined" if self.joined else "joining",
            "display_name": display_name,
        }

    async def _wait_and_join(self, display_name: str) -> None:
        """Handle the guest join flow in Teams web client."""
        page = self._page

        # Teams web has several possible join flows. We try them in order.
        # Flow 1: "Continue on this browser" link (if shown)
        try:
            continue_btn = page.locator("text=Continue on this browser")
            await continue_btn.wait_for(timeout=10000)
            await continue_btn.click()
            log.info("Clicked 'Continue on this browser'")
        except Exception:
            log.debug("No 'Continue on this browser' prompt — trying direct join.")

        # Flow 2: Wait for guest name input
        # Teams uses various selectors depending on version
        name_selectors = [
            'input[data-tid="prejoin-display-name-input"]',
            'input[placeholder*="name"]',
            'input[aria-label*="name" i]',
            '#username',
        ]

        name_input = None
        for sel in name_selectors:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(timeout=8000)
                name_input = loc
                log.info("Found name input: %s", sel)
                break
            except Exception:
                continue

        if name_input:
            await name_input.fill("")
            await name_input.fill(display_name)
            log.info("Entered display name: %s", display_name)
        else:
            log.warning("Could not find name input — may already be pre-filled.")

        # Try to turn off camera/mic toggles before joining
        await self._toggle_off_media()

        # Click "Join now" button
        join_selectors = [
            'button[data-tid="prejoin-join-button"]',
            'button:has-text("Join now")',
            'button:has-text("Join")',
        ]

        for sel in join_selectors:
            try:
                join_btn = page.locator(sel).first
                await join_btn.wait_for(timeout=5000)
                await join_btn.click()
                log.info("Clicked join button: %s", sel)
                break
            except Exception:
                continue

        # Wait for meeting stage to load
        stage_selectors = [
            '[data-tid="meeting-stage"]',
            '[data-tid="calling-screen"]',
            '#page-content-wrapper',
        ]

        for sel in stage_selectors:
            try:
                await page.locator(sel).wait_for(timeout=30000)
                self.joined = True
                log.info("Meeting stage loaded (%s). Successfully joined!", sel)
                return
            except Exception:
                continue

        # Fallback: wait a bit and assume we joined
        await asyncio.sleep(5)
        self.joined = True
        log.warning("Could not confirm meeting stage, assuming joined after timeout.")

    async def _toggle_off_media(self) -> None:
        """Try to turn off camera and mic before joining (we inject our own)."""
        page = self._page

        # Mic toggle
        mic_selectors = [
            '[data-tid="toggle-mute"]',
            'button[aria-label*="microphone" i]',
            'button[aria-label*="mute" i]',
        ]
        for sel in mic_selectors:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(timeout=3000)
                # Check if mic is ON (aria-pressed or similar)
                await btn.click()
                log.debug("Toggled mic off via %s", sel)
                break
            except Exception:
                continue

        # Camera toggle
        cam_selectors = [
            '[data-tid="toggle-video"]',
            'button[aria-label*="camera" i]',
            'button[aria-label*="video" i]',
        ]
        for sel in cam_selectors:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(timeout=3000)
                await btn.click()
                log.debug("Toggled camera off via %s", sel)
                break
            except Exception:
                continue

    # -----------------------------------------------------------------
    # Chat DOM operations
    # -----------------------------------------------------------------

    async def read_chat(self, last_n: int = 20) -> list[Dict[str, str]]:
        """Scrape the last N messages from the meeting chat pane."""
        if not self._page:
            return []

        # Ensure chat pane is open
        await self._open_chat_pane()

        messages = await self._page.evaluate(f"""() => {{
            const msgs = [];
            const nodes = document.querySelectorAll(
                '[data-tid="chat-pane-message"], ' +
                '[class*="message-body"], ' +
                '[data-tid*="message"]'
            );
            const slice = Array.from(nodes).slice(-{last_n});
            for (const node of slice) {{
                const sender = node.querySelector(
                    '[data-tid="message-author"], [class*="author"]'
                );
                const body = node.querySelector(
                    '[data-tid="message-body"], [class*="body"]'
                );
                msgs.push({{
                    sender: sender ? sender.innerText.trim() : "unknown",
                    content: body ? body.innerText.trim() : node.innerText.trim(),
                }});
            }}
            return msgs;
        }}""")

        return messages or []

    async def post_chat(self, text: str) -> bool:
        """Type a message in the meeting chat input and send it."""
        if not self._page:
            return False

        await self._open_chat_pane()

        compose_selectors = [
            '[data-tid="ckeditor-replyConversation"]',
            '[data-tid="newMessageCommands-input"]',
            'div[role="textbox"][contenteditable="true"]',
        ]

        for sel in compose_selectors:
            try:
                compose = self._page.locator(sel).first
                await compose.wait_for(timeout=5000)
                await compose.click()
                await compose.fill(text)
                await self._page.keyboard.press("Enter")
                log.info("Posted chat message: %s", text[:60])
                return True
            except Exception:
                continue

        log.warning("Could not find chat compose box.")
        return False

    async def _open_chat_pane(self) -> None:
        """Open the chat pane if it's not already visible."""
        chat_btn_selectors = [
            'button[data-tid="chat-button"]',
            'button[aria-label*="chat" i]',
            '#chat-button',
        ]
        for sel in chat_btn_selectors:
            try:
                btn = self._page.locator(sel).first
                visible = await btn.is_visible()
                if visible:
                    # Check if chat pane is already open
                    pane = self._page.locator('[data-tid="chat-pane"], [class*="chat-pane"]').first
                    try:
                        if await pane.is_visible():
                            return  # already open
                    except Exception:
                        pass
                    await btn.click()
                    await asyncio.sleep(1)  # wait for pane to render
                    return
            except Exception:
                continue

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    async def leave(self) -> None:
        """Click the Leave button and close the browser."""
        if self._page and self.joined:
            try:
                leave_selectors = [
                    'button[data-tid="hangup-button"]',
                    'button[data-tid="call-hangup"]',
                    'button[aria-label*="Leave" i]',
                    'button:has-text("Leave")',
                ]
                for sel in leave_selectors:
                    try:
                        btn = self._page.locator(sel).first
                        await btn.wait_for(timeout=3000)
                        await btn.click()
                        log.info("Clicked leave button.")
                        break
                    except Exception:
                        continue
            except Exception as e:
                log.warning("Error clicking leave: %s", e)

        await self.close()

    async def close(self) -> None:
        """Force-close the browser and cleanup."""
        self.joined = False
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        log.info("Browser closed for session %s", self.session_id)

    @property
    def page(self):
        return self._page
