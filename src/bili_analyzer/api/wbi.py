"""B站 Wbi 签名算法

用于对 B站 API 请求进行签名鉴权。
"""

import hashlib
import time
import re
from typing import Dict, Optional
from urllib.parse import urlencode

import requests


# Wbi 混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# 缓存 mixin_key
_mixin_key_cache: Optional[str] = None
_mixin_key_expire: float = 0


def _get_mixin_key(orig: str) -> str:
    """从原始字符串提取 mixin key"""
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _fetch_wbi_keys() -> tuple:
    """从 B站 nav API 获取 img_url 和 sub_url

    Returns:
        tuple: (img_url, sub_url)
    """
    resp = requests.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
    data = resp.json().get("data", {})
    img_url = data.get("wbi_img", {}).get("img_url", "")
    sub_url = data.get("wbi_img", {}).get("sub_url", "")
    return img_url, sub_url


def get_mixin_key() -> str:
    """获取 mixin key（带缓存，10分钟过期）

    Returns:
        str: 32 字符的 mixin key
    """
    global _mixin_key_cache, _mixin_key_expire

    if _mixin_key_cache and time.time() < _mixin_key_expire:
        return _mixin_key_cache

    img_url, sub_url = _fetch_wbi_keys()
    # 提取文件名部分（去掉 URL 前缀和扩展名）
    img_key = re.search(r"([a-zA-Z0-9]+)\.png", img_url)
    sub_key = re.search(r"([a-zA-Z0-9]+)\.png", sub_url)

    if not img_key or not sub_key:
        raise RuntimeError("无法获取 Wbi 密钥")

    orig = img_key.group(1) + sub_key.group(1)
    _mixin_key_cache = _get_mixin_key(orig)
    _mixin_key_expire = time.time() + 600  # 10 分钟缓存

    return _mixin_key_cache


def sign_params(params: Dict[str, str]) -> Dict[str, str]:
    """对请求参数进行 Wbi 签名

    Args:
        params: 原始请求参数

    Returns:
        Dict: 添加了 w_rid 和 wts 的参数
    """
    mixin_key = get_mixin_key()
    wts = str(int(time.time()))

    # 过滤特殊字符
    sanitized = {}
    for key, value in params.items():
        sanitized[key] = re.sub(r"[!'()*]", "", str(value))
    sanitized["wts"] = wts

    # 按 key 字典序排列
    query = urlencode(sorted(sanitized.items()))

    # 计算 MD5
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()

    sanitized["w_rid"] = w_rid
    return sanitized
