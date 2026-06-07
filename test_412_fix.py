"""验证 412 修复的单元测试"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, "src")

import requests
from bili_analyzer.downloader.ytdlp import _write_cookies_file, download_subtitle

# === 测试 5: 预热失败降级 ===
def mock_fail_get(*args, **kwargs):
    raise requests.exceptions.ConnectionError("mocked")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    with mock.patch("bili_analyzer.downloader.ytdlp.requests.Session") as MockSession:
        instance = MockSession.return_value
        instance.get.side_effect = mock_fail_get
        result = _write_cookies_file({"SESSDATA": "x"}, tmp_path)
        content = result.read_text(encoding="utf-8")
        assert "SESSDATA" in content
        print("PASS: 预热失败降级仍写入原 cookies")

# === 测试 6: yt-dlp 命令包含 UA/Referer，无 --no-warnings ===
captured_cmd = []

def fake_run(cmd, **kwargs):
    captured_cmd.extend(cmd)
    r = mock.MagicMock()
    r.returncode = 0
    return r

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / "video.zh-CN.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\ntest", encoding="utf-8")
    with mock.patch("bili_analyzer.downloader.ytdlp.subprocess.run", side_effect=fake_run):
        download_subtitle(
            video_url="https://www.bilibili.com/video/BV1?p=1",
            output_dir=tmp_path,
            sub_langs="zh-CN,ai-zh",
            cookies={"SESSDATA": "x"},
            output_name="video",
        )
        assert "--user-agent" in captured_cmd
        assert any("--add-headers" in c for c in captured_cmd)
        assert "Referer" in str(captured_cmd)
        assert "--no-warnings" not in captured_cmd
        cmd_str = " ".join(captured_cmd)
        print("PASS: yt-dlp 命令行前 200 字符: " + cmd_str[:200])

# === 测试 7: 外部 cookies_file 直接使用，不走预热 ===
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    external = tmp_path / "external.txt"
    external.write_text(
        "# Netscape\n.bilibili.com\tTRUE\t/\tTRUE\t0\tbuvid3\texternal_buvid3\n",
        encoding="utf-8",
    )
    captured_cmd = []
    (tmp_path / "video.zh-CN.srt").write_text("test", encoding="utf-8")
    with mock.patch("bili_analyzer.downloader.ytdlp.subprocess.run", side_effect=fake_run):
        download_subtitle(
            video_url="https://www.bilibili.com/video/BV1?p=1",
            output_dir=tmp_path,
            sub_langs="zh-CN",
            cookies={"SESSDATA": "auto"},
            cookies_file=str(external),
            output_name="video",
        )
        cookies_idx = captured_cmd.index("--cookies")
        assert captured_cmd[cookies_idx + 1] == str(external), (
            f"yt-dlp 应使用 external, 实际: {captured_cmd[cookies_idx + 1]}"
        )
        assert not (tmp_path / ".cookies.txt").exists(), "使用 external 时不应写出 .cookies.txt"
        print("PASS: 外部 cookies_file 直接使用，不走预热")

print("ALL_TESTS_PASS")
