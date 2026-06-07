"""Whisper 模型对比测试脚本

对比 openai-whisper 和 faster-whisper 在不同模型大小下的识别速度和内存占用。
"""

import gc
import time
import tracemalloc
from pathlib import Path
from dataclasses import dataclass
from typing import List

# 测试音频路径
AUDIO_PATH = Path(r"C:\实用\视频内容总结\bili_analyzer\outputs\videos\世界上最难的验证码！没有人类能通过测试.mp3")

# 模型列表（跳过 medium，避免内存不足）
MODELS = ["tiny", "base", "small"]


@dataclass
class BenchmarkResult:
    model: str
    framework: str
    load_time: float = 0.0
    transcribe_time: float = 0.0
    total_time: float = 0.0
    memory_peak_mb: float = 0.0
    text_preview: str = ""
    error: str = ""


def benchmark_openai_whisper(model: str, audio_path: Path) -> BenchmarkResult:
    """测试 openai-whisper"""
    result = BenchmarkResult(model=model, framework="openai-whisper")

    try:
        import whisper
    except ImportError:
        result.error = "未安装 openai-whisper"
        return result

    # 模型加载
    print(f"  [openai-whisper] 加载 {model} 模型...")
    t0 = time.time()
    try:
        whisper_model = whisper.load_model(model)
    except Exception as e:
        result.error = f"模型加载失败: {e}"
        return result
    result.load_time = time.time() - t0

    # 语音识别 + 内存跟踪
    print(f"  [openai-whisper] 开始识别...")
    tracemalloc.start()
    t0 = time.time()
    try:
        output = whisper_model.transcribe(
            str(audio_path),
            language="zh",
            verbose=False,
        )
    except Exception as e:
        result.error = f"识别失败: {e}"
        tracemalloc.stop()
        return result
    result.transcribe_time = time.time() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result.memory_peak_mb = peak / (1024 * 1024)

    # 提取文本预览
    segments = output.get("segments", [])
    texts = [seg["text"].strip() for seg in segments[:20]]
    result.text_preview = "\n".join(texts)

    result.total_time = result.load_time + result.transcribe_time
    print(f"  [openai-whisper] {model} 完成，耗时 {result.total_time:.1f}s")

    # 释放内存
    del whisper_model
    gc.collect()
    return result


def benchmark_faster_whisper(model: str, audio_path: Path) -> BenchmarkResult:
    """测试 faster-whisper"""
    result = BenchmarkResult(model=model, framework="faster-whisper")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        result.error = "未安装 faster-whisper"
        return result

    # 本地模型路径
    model_path = Path(r"C:\实用\视频内容总结\bili_analyzer\models") / f"faster-whisper-{model}" / f"faster-whisper-{model}"

    # 模型加载
    print(f"  [faster-whisper] 加载 {model} 模型...")
    print(f"    模型路径: {model_path}")
    t0 = time.time()
    try:
        fw_model = WhisperModel(str(model_path), device="cpu", compute_type="int8")
    except Exception as e:
        result.error = f"模型加载失败: {e}"
        return result
    result.load_time = time.time() - t0

    # 语音识别 + 内存跟踪
    print(f"  [faster-whisper] 开始识别...")
    tracemalloc.start()
    t0 = time.time()
    try:
        segments, info = fw_model.transcribe(str(audio_path), language="zh", beam_size=5)
        segments = list(segments)
    except Exception as e:
        result.error = f"识别失败: {e}"
        tracemalloc.stop()
        return result
    result.transcribe_time = time.time() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result.memory_peak_mb = peak / (1024 * 1024)

    # 提取文本预览
    texts = [seg.text.strip() for seg in segments[:20]]
    result.text_preview = "\n".join(texts)

    result.total_time = result.load_time + result.transcribe_time
    print(f"  [faster-whisper] {model} 完成，耗时 {result.total_time:.1f}s")

    # 释放内存
    del fw_model
    gc.collect()
    return result


def generate_report(results: List[BenchmarkResult], output_path: Path):
    """生成 Markdown 对比报告"""
    lines = []
    lines.append("# Whisper 模型对比测试报告\n")
    lines.append(f"测试音频: `{AUDIO_PATH}`\n")
    lines.append(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n")

    # 速度对比表
    lines.append("## 速度对比\n")
    lines.append("| 模型 | 框架 | 加载时间 | 识别耗时 | 总耗时 | 内存峰值 | 状态 |")
    lines.append("|------|------|----------|----------|--------|----------|------|")
    for r in results:
        status = "✅ 成功" if not r.error else f"❌ {r.error}"
        lines.append(
            f"| {r.model} | {r.framework} | {r.load_time:.1f}s | {r.transcribe_time:.1f}s | "
            f"{r.total_time:.1f}s | {r.memory_peak_mb:.1f}MB | {status} |"
        )
    lines.append("")

    # 文本质量对比
    lines.append("## 识别文本对比（前20句）\n")
    for r in results:
        if r.error:
            continue
        lines.append(f"### {r.framework} - {r.model}\n")
        lines.append("```")
        lines.append(r.text_preview)
        lines.append("```\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")


def main():
    print("=" * 60)
    print("Whisper 模型对比测试")
    print("=" * 60)
    print(f"测试音频: {AUDIO_PATH}")
    if not AUDIO_PATH.exists():
        print(f"错误: 音频文件不存在: {AUDIO_PATH}")
        return

    results: List[BenchmarkResult] = []

    # 测试 openai-whisper
    print("\n--- 测试 openai-whisper ---")
    for model in MODELS:
        print(f"\n[{model}]")
        r = benchmark_openai_whisper(model, AUDIO_PATH)
        results.append(r)

    # 测试 faster-whisper
    print("\n--- 测试 faster-whisper ---")
    for model in MODELS:
        print(f"\n[{model}]")
        r = benchmark_faster_whisper(model, AUDIO_PATH)
        results.append(r)

    # 生成报告
    report_path = Path(__file__).parent / "whisper_benchmark_report.md"
    generate_report(results, report_path)

    # 打印摘要
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    for r in results:
        if r.error:
            print(f"{r.framework:20s} {r.model:10s} ❌ {r.error}")
        else:
            print(
                f"{r.framework:20s} {r.model:10s} "
                f"总耗时: {r.total_time:6.1f}s  内存: {r.memory_peak_mb:6.1f}MB"
            )


if __name__ == "__main__":
    main()
