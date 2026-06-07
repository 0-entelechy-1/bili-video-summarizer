"""B站扫码登录模块

提供二维码登录、凭证保存/加载功能。
"""

import json
import logging
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger("bili_analyzer")

_QRCODE_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_CREDENTIALS_DIR = Path.home() / ".bili_analyzer"
_CREDENTIALS_FILE = _CREDENTIALS_DIR / "credentials.json"
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
            logger.warning("二维码已过期")
            return False, {}
        elif code == 86090:
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


def save_credentials(cookies: Dict[str, str]) -> None:
    """保存 Cookie 到本地文件

    Args:
        cookies: Cookie 字典
    """
    _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "cookies": cookies,
        "saved_at": datetime.now().isoformat(),
    }
    with open(_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"凭证已保存到 {_CREDENTIALS_FILE}")


def load_credentials() -> Optional[Dict[str, str]]:
    """从本地文件加载 Cookie

    Returns:
        Optional[Dict[str, str]]: Cookie 字典，文件不存在时返回 None
    """
    if not _CREDENTIALS_FILE.exists():
        return None

    with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cookies = payload.get("cookies")
    if cookies:
        logger.info(f"已从 {_CREDENTIALS_FILE} 加载凭证")
    return cookies


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

    获取二维码 -> 显示二维码 -> 轮询状态 -> 保存凭证

    Returns:
        Optional[Dict[str, str]]: 登录成功返回 cookies，失败返回 None
    """
    print("=" * 50)
    print("B站扫码登录")
    print("=" * 50)

    try:
        qrcode_url, qrcode_key = get_login_qrcode()
    except Exception as exc:
        print(f"❌ 获取二维码失败: {exc}")
        logger.error(f"获取二维码失败: {exc}")
        return None

    print("\n请使用 B站 App 扫描二维码登录:\n")

    # 优先尝试终端显示二维码
    if not display_qrcode_terminal(qrcode_url):
        print("正在用浏览器打开二维码页面...")
        display_qrcode_browser(qrcode_url)

    print("\n等待扫码...")
    success, cookies = poll_login_status(qrcode_key)
    if success and cookies:
        print("\n✅ 登录成功！")
        print(f"   已保存 Cookie ({len(cookies)} 项)")
        print(f"   凭证文件: {_CREDENTIALS_FILE}")
        print("\n下次运行程序时将自动加载此凭证")
        save_credentials(cookies)
        return cookies

    print("\n❌ 登录失败")
    return None
