"""端到端测试：用真实 B站 API 验证 download_subtitle 修复 412"""
import sys
import tempfile
import logging
from pathlib import Path

sys.path.insert(0, "src")

# 启用 DEBUG 级别 logger，看完整 yt-dlp 命令
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

from bili_analyzer.api.auth import load_credentials
from bili_analyzer.downloader.ytdlp import download_subtitle

creds = load_credentials()
print(f"=== 端到端测试 BV1Rr5v6wE1F ===")
print(f"已登录 cookies: {list(creds.keys()) if creds else 'None'}")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    srt_path = download_subtitle(
        video_url="https://www.bilibili.com/video/BV1Rr5v6wE1F?p=1",
        output_dir=tmp_path,
        sub_langs="zh-CN,zh-Hans,zh-TW,ai-zh",
        cookies=creds,
        output_name="BV1Rr5v6wE1F",
    )
    if srt_path:
        print(f"\n✅ SUCCESS: 字幕下载成功: {srt_path}")
        content = srt_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        print(f"字幕行数: {len(lines)}")
        print(f"前 10 行:")
        for line in lines[:10]:
            print(f"  {line}")
    else:
        print(f"\n❌ FAILED: yt-dlp 字幕下载失败 (返回 None)")
        print(f"检查上方日志中的 yt-dlp 命令和错误")
