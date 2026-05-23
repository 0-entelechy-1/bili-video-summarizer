# B站视频分析器

自动分析 B站视频，提取知识点并生成 Markdown 学习笔记。

## 功能

- **CC 字幕优先**：视频有内挂字幕时自动获取，跳过语音识别，大幅节省时间
- **多种转录方式**：CC 字幕 → 本地 Whisper → 火山引擎 API，自动降级
- **多种 LLM 分析**：智谱 GLM-4.7-Flash（免费）/ DeepSeek / 交互式，自动降级
- **关键画面截图**：FFmpeg 并发截取，自动匹配知识点
- **Markdown 学习笔记**：知识点卡片风格，含核心概念、详细说明、关键要点和配图
- **视频自动清理**：分析完成后自动删除视频文件，节省磁盘空间
- **YAML 配置文件**：预配置 LLM 提供商、转录方式等，无需每次指定

## 安装

### 1. 前置依赖

| 依赖 | 说明 | 安装方式 |
|------|------|---------|
| Python 3.9+ | 运行环境 | [python.org](https://www.python.org/downloads/) |
| FFmpeg | 视频处理和截图 | [ffmpeg.org](https://ffmpeg.org/download.html)，下载后添加到 PATH |
| yt-dlp | B站视频下载 | 随项目自动安装 |

### 2. 安装项目

```bash
cd bili_analyzer
pip install -e .
```

如需安装所有可选依赖（智谱 SDK、DeepSeek SDK、Whisper）：

```bash
pip install -e ".[all]"
```

或按需安装：

```bash
pip install -e ".[zhipu]"      # 仅智谱 GLM
pip install -e ".[deepseek]"   # 仅 DeepSeek
pip install -e ".[whisper]"    # 仅本地 Whisper
```

### 3. 验证安装

```bash
bili-analyzer --version
```

## 配置

### 方式一：配置文件（推荐）

将 `config.yaml.example` 复制为 `config.yaml`，填入你的 API Key：

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
# LLM 配置
llm:
  provider: zhipu          # 选择 LLM 提供商: zhipu / deepseek / interactive
  zhipu:
    api_key: "你的智谱API密钥"    # 从 https://open.bigmodel.cn/ 获取
    model: glm-4.7-flash
  deepseek:
    api_key: "你的DeepSeek API密钥"  # 从 https://platform.deepseek.com/ 获取
    base_url: https://api.deepseek.com
    model: deepseek-chat

# 转录配置
transcriber:
  prefer: auto             # auto: CC字幕优先; whisper: 强制本地Whisper; volcengine: 强制火山引擎
  whisper:
    model: medium          # tiny/base/small/medium/large，越大越准但越慢
  volcengine:
    token: "你的火山引擎Token"
    appid: "你的火山引擎AppID"

# 清理配置
cleanup:
  auto_delete_video: true  # 分析完成后自动删除视频文件

# 下载配置
download:
  quality: 1080p           # 1080p / 720p / 480p / best

# 截图配置
screenshot:
  count: 10                # 关键截图数量
  quality: 2               # JPEG 质量 (1-31, 越小质量越高)
```

### 方式二：环境变量

将 `.env.example` 复制为 `.env`，或直接设置系统环境变量：

```bash
# 智谱 API Key (免费，推荐)
export ZHIPU_API_KEY="你的智谱API密钥"

# DeepSeek API Key (可选)
export DEEPSEEK_API_KEY="你的DeepSeek API密钥"

# 火山引擎语音识别 (可选，无CC字幕时使用)
export BYTEDANCE_VC_TOKEN="你的火山引擎Token"
export BYTEDANCE_VC_APPID="你的火山引擎AppID"
```

Windows PowerShell：

```powershell
$env:ZHIPU_API_KEY = "你的智谱API密钥"
```

### 配置优先级

命令行参数 > 环境变量 > 配置文件 > 默认值

## 使用方法

### 基本用法

```bash
# 使用 BV 号
bili-analyzer BV1ms4y1Y76i

# 使用完整链接
bili-analyzer https://www.bilibili.com/video/BV1ms4y1Y76i
```

### 指定输出目录

```bash
bili-analyzer BV1ms4y1Y76i --output ./my_reports
```

### 指定 LLM 提供商

```bash
# 使用智谱 GLM（免费）
bili-analyzer BV1ms4y1Y76i --llm zhipu

# 使用 DeepSeek
bili-analyzer BV1ms4y1Y76i --llm deepseek

# 交互式模式（手动复制 prompt 到任意 LLM）
bili-analyzer BV1ms4y1Y76i --llm interactive
```

### 保留视频文件

```bash
bili-analyzer BV1ms4y1Y76i --keep-video
```

### 也可以用 Python 模块方式运行

```bash
python -m bili_analyzer BV1ms4y1Y76i
```

## 完整流程

运行后自动执行以下 7 步：

```
1. 获取视频信息    → 标题、UP主、时长
2. 下载视频        → yt-dlp 下载到输出目录
3. 获取字幕        → 优先 CC 字幕，无则语音识别
4. LLM 分析        → 提取知识点、关键截图时间点
5. 截取关键画面    → FFmpeg 并发截图
6. 生成学习笔记    → Markdown 知识点卡片
7. 清理视频        → 自动删除视频文件（可配置）
```

## 输出结构

```
reports/
├── 视频标题.mp4                    # 视频文件（默认分析后自动删除）
├── 视频标题.srt                    # SRT 字幕
├── 视频标题_analysis.json          # LLM 分析结果
├── 视频标题_学习笔记.md            # 最终学习笔记
└── screenshots/                    # 关键截图
    ├── screenshot_001_83s.jpg
    ├── screenshot_002_280s.jpg
    └── ...
```

## API Key 获取

| 服务 | 用途 | 获取地址 | 费用 |
|------|------|---------|------|
| 智谱 GLM | LLM 内容分析（推荐） | [open.bigmodel.cn](https://open.bigmodel.cn/) | 免费 |
| DeepSeek | LLM 内容分析（备选） | [platform.deepseek.com](https://platform.deepseek.com/) | 低价 |
| 火山引擎 | 语音识别（无 CC 字幕时） | [volcengine.com](https://www.volcengine.com/) | 新用户赠送约 2 万次 |

> 有 CC 字幕的视频不需要火山引擎 API，也不需要本地 Whisper 模型。

## 常见问题

**Q: 提示"未找到 FFmpeg"**

下载 [FFmpeg](https://ffmpeg.org/download.html) 并添加到系统 PATH。Windows 用户可从 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 下载预编译版本。

**Q: 提示"未找到 yt-dlp"**

yt-dlp 随项目自动安装。如果仍找不到，手动安装：`pip install yt-dlp`

**Q: 视频下载失败**

B站视频下载需要网络能访问 bilibili.com。部分视频可能需要登录 Cookie，可在 `config.yaml` 中配置。

**Q: 智谱 API 报错 401**

检查 `ZHIPU_API_KEY` 是否正确。确保没有多余空格或引号。

**Q: Whisper 转录很慢**

Whisper medium 模型需要较多计算资源。可以改用更小的模型：在 `config.yaml` 中设置 `transcriber.whisper.model: small` 或 `tiny`。

**Q: 想保留视频文件**

使用 `--keep-video` 参数，或在 `config.yaml` 中设置 `cleanup.auto_delete_video: false`。

## 项目结构

```
bili_analyzer/
├── pyproject.toml
├── config.yaml.example
├── .env.example
└── src/bili_analyzer/
    ├── __init__.py          # 版本号
    ├── __main__.py          # python -m 入口
    ├── cli.py               # 命令行接口
    ├── config.py            # 配置管理
    ├── pipeline.py          # 主流程编排
    ├── api/                 # B站 API（视频信息、CC字幕、Wbi签名）
    ├── downloader/          # 视频下载（yt-dlp）
    ├── transcriber/         # 字幕转录（CC/Whisper/火山引擎）
    ├── analyzer/            # LLM 分析（智谱/DeepSeek/交互式）
    ├── parser/              # SRT 解析
    ├── screenshot/          # FFmpeg 截图
    └── reporter/            # Markdown 报告生成
```
