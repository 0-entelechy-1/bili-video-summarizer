"""本地 Whisper 语音转录"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from bili_analyzer.transcriber.base import BaseTranscriber
from bili_analyzer.ui.console import (
    print_info,
    print_success,
    spinner,
)


class WhisperTranscriber(BaseTranscriber):

    def __init__(self, model: str = "medium", model_path: str = "./model"):
        self.model = model
        self.model_path = Path(model_path)

    @property
    def name(self) -> str:
        return f"Whisper ({self.model})"

    def _find_local_model(self) -> Optional[Path]:
        if not self.model_path.exists():
            return None
        for ext in (".pt", ".pth", ".bin"):
            candidates = list(self.model_path.glob(f"*{ext}"))
            if candidates:
                return candidates[0]
        return None

    def _get_whisper_cache_dir(self) -> Path:
        return Path.home() / ".cache" / "whisper"

    def _find_cached_model(self) -> Optional[Path]:
        cache_dir = self._get_whisper_cache_dir()
        cached_file = cache_dir / f"{self.model}.pt"
        if cached_file.exists():
            return cached_file
        return None

    def _get_model_download_url(self) -> str:
        try:
            import whisper
            version = getattr(whisper, "__version__", "v20231117")
        except ImportError:
            version = "v20231117"
        if not version.startswith("v"):
            version = f"v{version}"
        return f"https://github.com/openai/whisper/releases/download/{version}/{self.model}.pt"

    def transcribe(self, video_path: Path, output_dir: Path) -> Path:
        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "未安装 openai-whisper!\n"
                "请运行: pip install openai-whisper"
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        audio_path = output_dir / f"{video_path.stem}.mp3"
        if not audio_path.exists():
            self._extract_audio(video_path, audio_path)

        local_model = self._find_local_model()
        if local_model:
            print_info(f"正在从本地加载 Whisper 模型: {local_model.name}…")
            logging.getLogger("whisper").setLevel(logging.WARNING)
            whisper_model = whisper.load_model(str(local_model))
        else:
            cached_model = self._find_cached_model()
            if cached_model:
                print_info(f"正在从缓存加载模型: {cached_model.name}")
                logging.getLogger("whisper").setLevel(logging.WARNING)
                whisper_model = whisper.load_model(self.model)
            else:
                print_info(f"正在使用 Whisper ({self.model}) 转录…")
                print_info("提示: 本地未找到模型文件，将从网络下载")
                print_info(f"  下载地址: {self._get_model_download_url()}")
                print_info(f"  缓存目录: {self._get_whisper_cache_dir()}")
                logging.getLogger("whisper").setLevel(logging.WARNING)
                whisper_model = whisper.load_model(self.model)

        # 长任务包 spinner：显示累计等待时间
        # openai-whisper 没有 progress callback API；spinner + 累计时间是唯一可行的轻量方案
        with spinner(f"Whisper({self.model}) 语音识别中…") as sp:
            _t0 = time.time()
            result = whisper_model.transcribe(
                str(audio_path),
                language="zh",
                verbose=False,
            )
            sp.update(
                f"Whisper({self.model}) 识别完成（耗时 {int(time.time() - _t0)}s），正在写入 SRT…"
            )

        srt_path = output_dir / f"{video_path.stem}.srt"
        self._write_srt(result["segments"], srt_path)

        print_success(f"语音识别完成: {srt_path.name}")
        return srt_path

    def _extract_audio(self, video_path: Path, audio_path: Path) -> None:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-q:a", "0", "-map", "a",
            "-y", str(audio_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

    def _write_srt(self, segments: list, srt_path: Path) -> None:
        def _format_time(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines = []
        for i, seg in enumerate(segments, 1):
            lines.append(str(i))
            lines.append(f"{_format_time(seg['start'])} --> {_format_time(seg['end'])}")
            lines.append(seg["text"].strip())
            lines.append("")

        srt_path.write_text("\n".join(lines), encoding="utf-8")
