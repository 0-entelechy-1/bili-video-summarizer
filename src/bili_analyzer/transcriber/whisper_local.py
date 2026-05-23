"""本地 Whisper 语音转录"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from bili_analyzer.transcriber.base import BaseTranscriber


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
            print(f"正在从本地加载 Whisper 模型: {local_model.name}...")
            logging.getLogger("whisper").setLevel(logging.WARNING)
            whisper_model = whisper.load_model(str(local_model))
        else:
            print(f"正在使用 Whisper ({self.model}) 转录...")
            print("提示: 本地未找到模型文件，将从网络下载（首次使用需等待）")
            print(f"  可将模型文件放入 {self.model_path.resolve()} 目录以加速加载")
            logging.getLogger("whisper").setLevel(logging.WARNING)
            whisper_model = whisper.load_model(self.model)

        print("正在进行语音识别，请耐心等待...")
        result = whisper_model.transcribe(
            str(audio_path),
            language="zh",
            verbose=False,
        )

        srt_path = output_dir / f"{video_path.stem}.srt"
        self._write_srt(result["segments"], srt_path)

        print(f"语音识别完成: {srt_path.name}")
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
