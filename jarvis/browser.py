"""Browser automation for the assistant.

Playwright drives the browser that is already installed (Chrome by default), so
no second browser has to be downloaded and the profile - logins, cookies,
extensions - is the user's own. The profile and any downloads live on
``E:\\JARVIS`` to keep the system drive clean.

The session is lazy: nothing starts until the first browser action, and the
same page is reused afterwards so follow-up commands ("click Sign in", "type my
email") act on what the user is looking at.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.browser")

PROFILE_DIR = Path(os.environ.get("JARVIS_BROWSER_PROFILE", r"E:\JARVIS\browser-profile"))

# Order matters: the first one installed wins.
CHANNELS = [
    ("chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ("chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ("msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ("msedge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def _setting(key: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(key, default)
    except Exception:
        return default


def _flag(key: str, default: bool = False) -> bool:
    try:
        from jarvis import settings

        return settings.flag(key, default)
    except Exception:
        return default


def available() -> Dict[str, Any]:
    """Report whether the automation stack is installed, without launching it."""
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as exc:
        return {"ok": False, "error": "playwright is not installed: %s" % exc}
    installed = [c for c in CHANNELS if Path(c[1]).exists()]
    return {"ok": True, "browsers": installed, "profile": str(PROFILE_DIR)}


class _Session:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pw = None
        self._ctx = None
        self._page = None
        self._channel = ""

    # ---------------------------------------------------------------- lifecycle
    def _ensure(self):
        with self._lock:
            if self._page and not self._page.is_closed():
                return self._page
            from playwright.sync_api import sync_playwright

            if self._pw is None:
                self._pw = sync_playwright().start()

            channel, exe = None, None
            wanted = str(_setting("browser_channel", "") or "").strip()
            for name, path in CHANNELS:
                if wanted and wanted != name:
                    continue
                if Path(path).exists():
                    channel, exe = name, path
                    break
            if channel is None:
                raise RuntimeError("No supported browser found (Chrome or Edge).")

            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            headless = _flag("browser_headless", False)
            self._ctx = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel=channel,
                headless=headless,
                viewport={"width": 1360, "height": 860},
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            self._page.set_default_timeout(20000)
            self._channel = channel
            return self._page

    def close(self) -> Dict[str, Any]:
        with self._lock:
            try:
                if self._ctx:
                    self._ctx.close()
            except Exception:
                pass
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self._ctx = self._page = self._pw = None
            self._channel = ""
        return {"ok": True, "closed": True}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            page = self._page
            open_ = bool(page and not page.is_closed())
            return {
                "ok": True,
                "open": open_,
                "channel": self._channel or str(_setting("browser_channel", "") or "auto"),
                "url": page.url if open_ else "",
                "title": (page.title() if open_ else ""),
                "profile": str(PROFILE_DIR),
            }

    # ---------------------------------------------------------------- actions
    def go(self, url: str, timeout: int = 20000) -> Dict[str, Any]:
        target = str(url or "").strip()
        if not target:
            raise ValueError("a URL is required")
        if "://" not in target:
            target = "https://" + target
        with self._lock:
            page = self._ensure()
            page.goto(target, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            return {"ok": True, "url": page.url, "title": page.title(), "channel": self._channel}

    def search(self, query: str, engine: str = "duckduckgo") -> Dict[str, Any]:
        from urllib.parse import quote_plus

        q = str(query or "").strip()
        if not q:
            raise ValueError("a search query is required")
        bases = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "youtube": "https://www.youtube.com/results?search_query=",
        }
        base = bases.get((engine or "google").lower(), bases["google"])
        out = self.go(base + quote_plus(q))
        out["query"] = q
        return out

    def read(self, limit: int = 4000, selector: str = "") -> Dict[str, Any]:
        with self._lock:
            page = self._ensure()
            scope = page.locator(selector) if selector else page.locator("body")
            try:
                text = scope.inner_text(timeout=8000)
            except Exception:
                text = page.inner_text("body")
            links: List[Dict[str, str]] = []
            try:
                for a in page.locator("a").all()[:40]:
                    label = (a.inner_text(timeout=500) or "").strip()
                    href = a.get_attribute("href") or ""
                    if label and href:
                        links.append({"text": label[:80], "href": href[:200]})
            except Exception:
                pass
            clean = " ".join((text or "").split())
            return {
                "ok": True,
                "url": page.url,
                "title": page.title(),
                "text": clean[:limit],
                "links": links[:15],
            }

    def click(self, target: str, exact: bool = False) -> Dict[str, Any]:
        """Click by visible text first, then by CSS selector."""
        label = str(target or "").strip()
        if not label:
            raise ValueError("what should I click?")
        with self._lock:
            page = self._ensure()
            errors = []
            for build in (
                lambda: page.get_by_role("button", name=label, exact=exact),
                lambda: page.get_by_role("link", name=label, exact=exact),
                lambda: page.get_by_text(label, exact=exact),
                lambda: page.locator(label),
            ):
                try:
                    loc = build().first
                    loc.wait_for(state="visible", timeout=3500)
                    loc.click(timeout=5000)
                    return {"ok": True, "clicked": label, "url": page.url, "title": page.title()}
                except Exception as exc:
                    errors.append(str(exc).splitlines()[0][:120])
            return {"ok": False, "error": "could not click %r on %s" % (label, page.url), "tried": errors}

    def fill(self, field: str, value: str, submit: bool = False) -> Dict[str, Any]:
        """Type into a field identified by label, placeholder, name or selector."""
        name = str(field or "").strip()
        if not name:
            raise ValueError("which field?")
        with self._lock:
            page = self._ensure()
            candidates = (
                lambda: page.get_by_label(name).first,
                lambda: page.get_by_placeholder(name).first,
                lambda: page.locator('input[name="%s"], textarea[name="%s"]' % (name, name)).first,
                lambda: page.locator(name).first,
            )
            last = ""
            for build in candidates:
                try:
                    loc = build()
                    loc.wait_for(state="visible", timeout=3000)
                    loc.click(timeout=3000)
                    loc.fill(str(value))
                    if submit:
                        loc.press("Enter")
                    return {"ok": True, "field": name, "submitted": submit, "url": page.url}
                except Exception as exc:
                    last = str(exc).splitlines()[0][:140]
            return {"ok": False, "error": "could not find field %r: %s" % (name, last)}

    def press(self, keys: str) -> Dict[str, Any]:
        with self._lock:
            page = self._ensure()
            page.keyboard.press(keys)
            return {"ok": True, "keys": keys}

    def back(self) -> Dict[str, Any]:
        with self._lock:
            page = self._ensure()
            page.go_back()
            return {"ok": True, "url": page.url}

    def forward(self) -> Dict[str, Any]:
        with self._lock:
            page = self._ensure()
            page.go_forward()
            return {"ok": True, "url": page.url, "title": page.title()}

    def reload(self) -> Dict[str, Any]:
        with self._lock:
            page = self._ensure()
            page.reload()
            return {"ok": True, "url": page.url, "title": page.title(), "message": "Reloaded page."}

    def open_tab(self, url: str = "") -> Dict[str, Any]:
        with self._lock:
            self._ensure()
            page = self._ctx.new_page()
            if url:
                target = str(url).strip()
                if "://" not in target:
                    target = "https://" + target
                page.goto(target, wait_until="domcontentloaded")
            self._page = page
            title = page.title() if url else "New Tab"
            return {"ok": True, "title": title, "url": page.url, "tab_count": len(self._ctx.pages),
                    "message": "Opened new tab%s." % ((" on %s" % page.url) if url else "")}

    def close_tab(self, index: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._ctx or not self._ctx.pages:
                return {"ok": False, "error": "no open tabs"}
            pages = self._ctx.pages
            if index is not None and 0 <= index < len(pages):
                target = pages[index]
            else:
                target = self._page or pages[-1]
            title = target.title() or "tab"
            target.close()
            self._page = self._ctx.pages[-1] if self._ctx.pages else None
            return {"ok": True, "closed_title": title, "tab_count": len(self._ctx.pages),
                    "message": "Closed tab '%s'." % title}

    def close_duplicate_tabs(self) -> Dict[str, Any]:
        with self._lock:
            if not self._ctx or not self._ctx.pages:
                return {"ok": True, "closed_count": 0, "message": "No open browser tabs."}
            seen_urls = set()
            closed = []
            for p in list(self._ctx.pages):
                try:
                    u = (p.url or "").rstrip("/").lower()
                    if not u or u in ("about:blank", "chrome://newtab", "edge://newtab"):
                        continue
                    if u in seen_urls:
                        t = p.title() or u
                        closed.append({"title": t, "url": p.url})
                        p.close()
                    else:
                        seen_urls.add(u)
                except Exception:
                    pass
            self._page = self._ctx.pages[-1] if self._ctx.pages else None
            count = len(closed)
            msg = ("Closed %d duplicate tab%s." % (count, "s" if count != 1 else "")) if count else "No duplicate tabs found."
            return {"ok": True, "closed_count": count, "duplicates": closed, "tab_count": len(self._ctx.pages), "message": msg}

    def list_tabs(self) -> Dict[str, Any]:
        with self._lock:
            if not self._ctx or not self._ctx.pages:
                return {"ok": True, "tabs": [], "count": 0, "message": "No browser tabs open."}
            tabs = []
            for i, p in enumerate(self._ctx.pages):
                try:
                    tabs.append({"index": i, "title": p.title(), "url": p.url, "active": bool(p == self._page)})
                except Exception:
                    pass
            return {"ok": True, "tabs": tabs, "count": len(tabs), "message": "You have %d open tab%s." % (len(tabs), "s" if len(tabs) != 1 else "")}

    def switch_tab(self, target: Any = None) -> Dict[str, Any]:
        with self._lock:
            if not self._ctx or not self._ctx.pages:
                return {"ok": False, "error": "no open browser tabs"}
            pages = self._ctx.pages
            chosen = None
            try:
                idx = int(target)
                if 0 <= idx < len(pages):
                    chosen = pages[idx]
            except (ValueError, TypeError):
                pass
            if chosen is None and target is not None:
                q = str(target).strip().lower()
                for p in pages:
                    try:
                        if q in p.title().lower() or q in p.url.lower():
                            chosen = p
                            break
                    except Exception:
                        pass
            if chosen is None:
                chosen = pages[-1]
            self._page = chosen
            try:
                chosen.bring_to_front()
            except Exception:
                pass
            return {"ok": True, "title": chosen.title(), "url": chosen.url, "message": "Switched to tab '%s'." % chosen.title()}

    def screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        target = Path(path) if path else PROFILE_DIR.parent / "tmp" / ("page-%d.png" % int(time.time() * 1000))
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            page = self._ensure()
            page.screenshot(path=str(target), full_page=False)
            return {"ok": True, "path": str(target), "url": page.url}


_session = _Session()


def status() -> Dict[str, Any]:
    try:
        return _session.status()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "open": False}


def start(url: Optional[str] = None) -> Dict[str, Any]:
    """Open the browser (optionally on a URL)."""
    info = available()
    if not info.get("ok"):
        return info
    try:
        if url:
            return _session.go(url)
        page = _session._ensure()  # noqa: SLF001 - deliberate lazy start
        return {"ok": True, "url": page.url, "title": page.title()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def open_url(url: str) -> Dict[str, Any]:
    try:
        return _session.go(url)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def search(query: str, engine: str = "duckduckgo") -> Dict[str, Any]:
    try:
        return _session.search(query, engine)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def read(limit: int = 4000, selector: str = "") -> Dict[str, Any]:
    try:
        return _session.read(limit=limit, selector=selector)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def click(target: str, exact: bool = False) -> Dict[str, Any]:
    try:
        return _session.click(target, exact=exact)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fill(field: str, value: str, submit: bool = False) -> Dict[str, Any]:
    try:
        return _session.fill(field, value, submit=submit)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def press(keys: str) -> Dict[str, Any]:
    try:
        return _session.press(keys)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def screenshot(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        return _session.screenshot(path)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def open_tab(url: str = "") -> Dict[str, Any]:
    try:
        return _session.open_tab(url)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close_tab(index: Optional[int] = None) -> Dict[str, Any]:
    try:
        return _session.close_tab(index)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close_duplicate_tabs() -> Dict[str, Any]:
    try:
        return _session.close_duplicate_tabs()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_tabs() -> Dict[str, Any]:
    try:
        return _session.list_tabs()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def switch_tab(target: Any = None) -> Dict[str, Any]:
    try:
        return _session.switch_tab(target)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def reload() -> Dict[str, Any]:
    try:
        return _session.reload()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def back() -> Dict[str, Any]:
    try:
        return _session.back()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def forward() -> Dict[str, Any]:
    try:
        return _session.forward()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close() -> Dict[str, Any]:
    return _session.close()


def run(action: str, **kwargs: Any) -> Dict[str, Any]:
    """Single entry point used by the daemon, the tools and workflows."""
    handlers = {
        "open": lambda: open_url(kwargs.get("url") or kwargs.get("target") or ""),
        "go": lambda: open_url(kwargs.get("url") or kwargs.get("target") or ""),
        "search": lambda: search(kwargs.get("query") or kwargs.get("target") or "", kwargs.get("engine", "duckduckgo")),
        "read": lambda: read(int(kwargs.get("limit") or 4000), kwargs.get("selector", "")),
        "click": lambda: click(kwargs.get("target") or kwargs.get("text") or "", bool(kwargs.get("exact"))),
        "fill": lambda: fill(kwargs.get("field") or kwargs.get("target") or "", kwargs.get("value", ""), bool(kwargs.get("submit"))),
        "press": lambda: press(kwargs.get("keys") or "Enter"),
        "screenshot": lambda: screenshot(kwargs.get("path")),
        "status": status,
        "close": close,
        "open_tab": lambda: open_tab(kwargs.get("url") or kwargs.get("target") or ""),
        "new_tab": lambda: open_tab(kwargs.get("url") or kwargs.get("target") or ""),
        "close_tab": lambda: close_tab(kwargs.get("index")),
        "close_duplicate_tabs": close_duplicate_tabs,
        "close_duplicates": close_duplicate_tabs,
        "list_tabs": list_tabs,
        "tabs": list_tabs,
        "switch_tab": lambda: switch_tab(kwargs.get("target") or kwargs.get("index")),
        "reload": reload,
        "refresh": reload,
        "back": back,
        "forward": forward,
    }
    fn = handlers.get((action or "").lower())
    if not fn:
        return {"ok": False, "error": "unknown browser action %r" % action, "actions": sorted(handlers)}
    return fn()
