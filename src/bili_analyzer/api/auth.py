"""B站扫码登录模块

提供二维码登录、Netscape 格式 Cookie 保存/加载功能。
--login 扫码成功后，cookie 写入项目根目录下的 cookies.txt，
格式与 yt-dlp 兼容，可同时被 B站 API 和 yt-dlp 复用。
"""

import logging
import time
import webbrowser
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

from bili_analyzer.ui.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    spinner,
)

logger = logging.getLogger("bili_analyzer")

_QRCODE_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
# 项目根目录 = src/bili_analyzer/api/auth.py → 向上 4 层
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# --login 默认写入位置：项目根目录下的 cookies.txt
PROJECT_ROOT_COOKIES_FILE = PROJECT_ROOT / "cookies.txt"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


def get_login_qrcode() -> Tuple[str, str]:
    """获取 B站登录二维码

    Returns:
        Tuple[str, str]: (qrcode_url, qrcode_key)

    Raises:
        RuntimeError: 获取二维码失败
    """
    session = requests.Session()
    session.headers.update(_HEADERS)
    resp = session.get(_QRCODE_GENERATE_URL, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取二维码失败: {data.get('message', '未知错误')}")

    qrcode_url = data["data"]["url"]
    qrcode_key = data["data"]["qrcode_key"]
    logger.info("已获取登录二维码")
    return qrcode_url, qrcode_key


def poll_login_status(qrcode_key: str) -> Tuple[bool, Dict[str, str]]:
    """轮询登录状态

    每 3 秒轮询一次，最多 60 次（3 分钟超时）。

    Args:
        qrcode_key: 二维码 key

    Returns:
        Tuple[bool, Dict[str, str]]: (是否成功, cookies 字典)
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    max_polls = 60
    interval = 3
    last_state = "等待扫码"

    with spinner("等待扫码…") as sp:
        for attempt in range(max_polls):
            resp = session.get(
                _QRCODE_POLL_URL,
                params={"qrcode_key": qrcode_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.warning(f"轮询接口错误: {data.get('message')}")
                time.sleep(interval)
                continue

            inner_data = data.get("data", {})
            code = inner_data.get("code", -1)
            message = inner_data.get("message", "")

            if code == 0:
                # 登录成功：把 URL query 灌进 session 后取全量 cookies
                # （与 outputs/videos/bili_login.py 的做法一致，保证 sid / first_domain 等
                #  Set-Cookie 下发的 cookie 也能被保留，绕开 B站 /x/player/v2 的 412 校验）
                url = inner_data.get("url", "")
                _set_url_cookies_to_session(session, url)
                cookies = _session_cookies_to_dict(session.cookies)
                if cookies:
                    logger.info(f"扫码登录成功（{len(cookies)} 项 cookie）")
                    return True, cookies
                else:
                    logger.warning("登录成功但 session 中无任何 cookie")
                    return False, {}
            elif code == 86038:
                sp.update("[bold red]二维码已过期[/]，[bold cyan]请重新运行 --login[/]")
                logger.warning("二维码已过期")
                return False, {}
            elif code == 86090:
                if last_state != "已扫码":
                    sp.update("[bold green]✅ 已扫码，等待手机端确认…[/]")
                    last_state = "已扫码"
                logger.info("已扫码，等待确认...")
            elif code == 86101:
                if attempt == 0:
                    logger.info("等待扫码...")
            else:
                logger.warning(f"未知状态码: {code}, message={message}")

            time.sleep(interval)

    logger.warning("登录轮询超时")
    return False, {}


def _set_url_cookies_to_session(session: requests.Session, url: str) -> None:
    """将登录回调 URL 的 query 参数全部灌进 session.cookies

    B站扫码登录成功后，会在 data.url 中以 query string 形式回传本次登录
    写入的关键 cookie（与 Set-Cookie 头下发的 cookie 有部分重叠）。本函数
    仅负责"URL query → session.cookies"这一步，让 session 累积所有可用
    cookie，最后由调用方统一从 session.cookies 提取。

    Args:
        session: 已完成登录轮询的 Session（已含 Set-Cookie 累积的 cookies）
        url: 登录回调 URL（含 ?SESSDATA=...&bili_jct=...&...）
    """
    if not url:
        return
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key, values in query.items():
        if values:
            session.cookies.set(key, values[0], domain=".bilibili.com")


def _session_cookies_to_dict(jar) -> Dict[str, str]:
    """把 requests Session 的 cookie jar 转为 {name: value} 字典

    Args:
        jar: requests.cookies.RequestsCookieJar 实例

    Returns:
        Dict[str, str]: cookie 名→值 字典
    """
    return {cookie.name: cookie.value for cookie in jar}


def save_cookies_netscape(cookies: Dict[str, str], filepath: Path) -> None:
    """将 cookie 字典以 Netscape HTTP Cookie File 格式写入文件

    格式与 yt-dlp 兼容：每行 7 个 tab 分隔字段
    (domain, flag, path, secure, expires, name, value)。

    Args:
        cookies: Cookie 字典 {name: value}
        filepath: 目标文件路径
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        # secure 列写 FALSE：与 B站原始 Set-Cookie 行为（无 Secure 标志）、
        # 与 yt-dlp 输出格式保持一致；HTTPS-only 限制对 B站全站 HTTPS 无影响
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"Cookies 已保存到: {filepath} ({len(cookies)} 项)")


def load_cookies_netscape(filepath: Path) -> Optional[Dict[str, str]]:
    """从 Netscape 格式的 cookies 文件中解析出 cookie 字典

    跳过空行与 `#` 开头行；按 tab 切分后取第 5/6 列（name/value）。

    Args:
        filepath: cookies 文件路径

    Returns:
        Optional[Dict[str, str]]: 解析得到的 cookie 字典，文件不存在时返回 None
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        return None
    cookies: Dict[str, str] = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            name, value = parts[5], parts[6]
            if name:
                cookies[name] = value
    if cookies:
        logger.info(f"已从 {filepath} 加载凭证 ({len(cookies)} 项)")
    return cookies or None


def display_qrcode_terminal(url: str) -> bool:
    """在终端显示 ASCII 二维码

    Args:
        url: 二维码内容 URL

    Returns:
        bool: 成功显示返回 True，qrcode 库未安装返回 False
    """
    try:
        import qrcode
    except ImportError:
        logger.warning("qrcode 库未安装，无法生成终端二维码")
        return False

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    # 使用 tty 友好的 ASCII 输出
    qr.print_ascii(invert=True)
    return True


def display_qrcode_browser(url: str) -> None:
    """在浏览器显示二维码

    Args:
        url: 二维码内容 URL
    """
    logger.info("正在用浏览器打开二维码页面...")
    webbrowser.open(url)


def perform_login() -> Optional[Dict[str, str]]:
    """完整的登录流程

    获取二维码 -> 显示二维码 -> 轮询状态 -> 保存 Cookie（项目根目录下 cookies.txt）

    Returns:
        Optional[Dict[str, str]]: 登录成功返回 cookies，失败返回 None
    """
    from rich.panel import Panel
    from rich.text import Text

    title = Text()
    title.append("🔐  ", style="bold cyan")
    title.append("B站扫码登录", style="bold bright_cyan")
    console.print(Panel(title, border_style="bright_cyan", expand=False))
    console.print()

    try:
        qrcode_url, qrcode_key = get_login_qrcode()
    except Exception as exc:
        print_error(f"获取二维码失败: {exc}")
        logger.error(f"获取二维码失败: {exc}")
        return None

    print_info("请使用 B站 App 扫描下方二维码登录:")
    console.print()

    # 优先尝试终端显示二维码
    if not display_qrcode_terminal(qrcode_url):
        print_info("qrcode 库未安装，回退到浏览器显示二维码…")
        display_qrcode_browser(qrcode_url)

    console.print()
    success, cookies = poll_login_status(qrcode_key)
    if success and cookies:
        console.print()
        print_success(f"✅ 登录成功！已保存 Cookie ({len(cookies)} 项)")
        print_info(f"凭证文件: {PROJECT_ROOT_COOKIES_FILE}")
        print_info("下次运行程序时将自动加载此凭证")
        save_cookies_netscape(cookies, PROJECT_ROOT_COOKIES_FILE)
        return cookies

    console.print()
    print_error("❌ 登录失败")
    return None
