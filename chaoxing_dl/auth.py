"""Playwright 登录与会话持久化。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.sync_api import Page

DEFAULT_LOGIN_URL = "https://i.chaoxing.com/"
SESSION_DIR_NAME = ".sessions"
SESSION_FILE = "storage_state.json"
BROWSERS_DIR_NAME = ".playwright-browsers"


def project_root(root: Optional[Path] = None) -> Path:
    return root or Path(__file__).resolve().parent.parent


def ensure_local_browsers_path(root: Optional[Path] = None) -> None:
    """优先使用项目内 .playwright-browsers，避免写到用户全局缓存。"""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    local = project_root(root) / BROWSERS_DIR_NAME
    if local.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local)


def default_session_dir(root: Optional[Path] = None) -> Path:
    path = project_root(root) / SESSION_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(root: Optional[Path] = None) -> Path:
    return default_session_dir(root) / SESSION_FILE


def has_session(root: Optional[Path] = None) -> bool:
    p = session_path(root)
    return p.is_file() and p.stat().st_size > 50


def clear_session(root: Optional[Path] = None) -> None:
    p = session_path(root)
    if p.exists():
        p.unlink()


def _looks_logged_in(page: Page) -> bool:
    url = page.url.lower()
    if "passport2" in url and "login" in url:
        return False
    try:
        content = page.content()
    except Exception:
        return False
    if "用户登录" in content[:3000]:
        return False
    # 登录后常见落地
    markers = (
        "i.chaoxing.com",
        "mooc1",
        "mooc2-ans",
        "space.chaoxing.com",
        "visit/interaction",
        "mycourse",
    )
    return any(m in url for m in markers) or "退出" in content or "我的课程" in content


def interactive_login(
    start_url: str = DEFAULT_LOGIN_URL,
    *,
    session_root: Optional[Path] = None,
    headless: bool = False,
    timeout_sec: int = 300,
) -> Path:
    """打开浏览器让用户手动登录，成功后保存 storage_state。

    支持：超星账号、学校统一认证、扫码等任意网页登录方式。
    """
    from playwright.sync_api import sync_playwright

    ensure_local_browsers_path(session_root)
    out = session_path(session_root)
    print("=" * 56)
    print("  请在弹出的浏览器中完成登录")
    print("  登录成功后回到本窗口按回车；或等待自动检测")
    print(f"  起始页: {start_url}")
    print("=" * 56)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)

        deadline = time.time() + timeout_sec
        print("\n登录完成后按 [Enter] 继续（也可等自动识别）...\n")

        import threading

        enter_event = threading.Event()

        def _wait_enter() -> None:
            try:
                input()
                enter_event.set()
            except EOFError:
                pass

        threading.Thread(target=_wait_enter, daemon=True).start()

        confirmed = False
        while time.time() < deadline:
            if enter_event.is_set():
                confirmed = True
                print("[*] 已确认（回车）")
                break
            if _looks_logged_in(page):
                time.sleep(1.5)  # 等 SSO 写完跨域 cookie
                if _looks_logged_in(page):
                    confirmed = True
                    print("[*] 已检测到登录态")
                    break
            time.sleep(0.5)

        if not confirmed:
            browser.close()
            raise TimeoutError("登录超时，请重试：python -m chaoxing_dl login")

        context.storage_state(path=str(out))
        # 额外存一份 cookie 列表，便于调试
        cookies = context.cookies()
        meta = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "start_url": start_url,
            "final_url": page.url,
            "cookie_count": len(cookies),
            "hosts": sorted({c.get("domain", "") for c in cookies}),
        }
        (out.parent / "session_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()

    print(f"[*] 会话已保存: {out}")
    return out


def load_context_cookies(session_root: Optional[Path] = None) -> list[dict]:
    """从 storage_state 读出 cookie（供 requests 使用）。"""
    path = session_path(session_root)
    if not path.is_file():
        raise FileNotFoundError(
            f"未找到登录会话: {path}\n请先运行: python -m chaoxing_dl login"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("cookies", [])


def cookies_for_requests(session_root: Optional[Path] = None) -> dict[str, str]:
    """转为 requests 可用的 name->value（同名后者覆盖；跨域场景够用）。"""
    jar: dict[str, str] = {}
    for c in load_context_cookies(session_root):
        name = c.get("name")
        value = c.get("value")
        if name is not None and value is not None:
            jar[name] = value
    return jar


def cookie_header(session_root: Optional[Path] = None) -> str:
    jar = cookies_for_requests(session_root)
    return "; ".join(f"{k}={v}" for k, v in jar.items())


def open_persistent_browser(
    start_url: str,
    *,
    session_root: Optional[Path] = None,
    headless: bool = False,
) -> tuple:
    """返回 (playwright, browser, context, page)，调用方负责关闭。"""
    from playwright.sync_api import sync_playwright

    ensure_local_browsers_path(session_root)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    state = session_path(session_root)
    kwargs = {
        "locale": "zh-CN",
        "viewport": {"width": 1280, "height": 800},
    }
    if state.is_file():
        kwargs["storage_state"] = str(state)
    context = browser.new_context(**kwargs)
    page = context.new_page()
    page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
    return pw, browser, context, page


def host_from_url(url: str) -> str:
    return urlparse(url).netloc or "mooc1.chaoxing.com"
