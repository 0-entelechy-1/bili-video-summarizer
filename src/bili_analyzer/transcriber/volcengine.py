"""火山引擎语音识别 API 转录"""

import json
import subprocess
import time
from pathlib import Path

import requests

from bili_analyzer.transcriber.base import BaseTranscriber
from bili_analyzer.ui.console import print_info, print_warning


class VolcengineTranscriber(BaseTranscriber):
    """火山引擎语音识别转录器"""

    def __init__(self, token: str, appid: str):
        """
        Args:
            token: 火山引擎 API Token
            appid: 火山引擎 App ID
        """
        self.token = token
        self.appid = appid

    @property
    def name(self) -> str:
        return "火山引擎"

    def transcribe(self, video_path: Path, output_dir: Path) -> Path:
        """使用火山引擎 API 转录视频生成 SRT 字幕

        Args:
            video_path: 视频文件路径
            output_dir: 输出目录

        Returns:
            Path: SRT 字幕文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 提取音频
        audio_path = output_dir / f"{video_path.stem}.mp3"
        if not audio_path.exists():
            self._extract_audio(video_path, audio_path)

        print_info("正在使用火山引擎语音识别…")

        # 提交转录任务
        task_id = self._submit(audio_path)
        print_info(f"转录任务已提交: {task_id}")

        # 轮询结果
        result = self._poll(task_id)

        # 生成 SRT 文件
        srt_path = output_dir / f"{video_path.stem}.srt"
        self._write_srt(result, srt_path)

        print_success(f"火山引擎语音识别完成: {srt_path.name}")
        return srt_path

    def _extract_audio(self, video_path: Path, audio_path: Path) -> None:
        """提取音频"""
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-q:a", "0", "-map", "a",
            "-y", str(audio_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

    def _submit(self, audio_path: Path) -> str:
        """提交转录任务"""
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        resp = requests.post(
            f"https://openspeech.bytedance.com/api/v1/vc/submit"
            f"?appid={self.appid}&language=zh-CN&words_per_line=20&max_lines=2",
            headers={
                "Content-Type": "audio/mpeg",
                "Authorization": f"Bearer;{self.token}",
            },
            data=audio_data,
            timeout=60,
        )

        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"火山引擎提交失败: {data.get('message', '未知错误')}")

        task_id = data["id"]
        return task_id

    def _poll(self, task_id: str, max_wait: int = 300) -> dict:
        """轮询转录结果（带 spinner 实时显示等待时长）"""
        start_time = time.time()

        with spinner("火山引擎处理中…") as sp:
            while time.time() - start_time < max_wait:
                resp = requests.get(
                    f"https://openspeech.bytedance.com/api/v1/vc/query"
                    f"?appid={self.appid}&id={task_id}",
                    headers={"Authorization": f"Bearer;{self.token}"},
                    timeout=30,
                )

                data = resp.json()
                code = data.get("code")

                elapsed = int(time.time() - start_time)
                sp.update(
                    f"火山引擎处理中…  已等待 {elapsed}s / {max_wait}s"
                )

                if code == 0:
                    return data
                elif code == 2000:
                    # 处理中
                    time.sleep(5)
                else:
                    raise RuntimeError(f"火山引擎语音识别失败: {data.get('message', '未知错误')}")

        raise RuntimeError("火山引擎语音识别超时")

    def _write_srt(self, result: dict, srt_path: Path) -> None:
        """将火山引擎结果写入 SRT 文件"""
        utterances = result.get("utterances", [])

        def _ms_to_srt(ms: int) -> str:
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            millis = ms % 1000
            return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"

        lines = []
        for i, u in enumerate(utterances, 1):
            lines.append(str(i))
            lines.append(f"{_ms_to_srt(u['start_time'])} --> {_ms_to_srt(u['end_time'])}")
            lines.append(u["text"])
            lines.append("")

        srt_path.write_text("\n".join(lines), encoding="utf-8")
