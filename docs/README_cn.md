# E.V.A. - 超级AI语音助手🎙️

<div align="center">

![EVA Logo](docs/logo.png)

*Multimodal, Multilingual, Cross Platform, Modular Architecture*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![GitHub Issues](https://img.shields.io/github/issues/Genesis1231/EVA)](https://github.com/Genesis1231/EVA/issues)
[![GitHub Stars](https://img.shields.io/github/stars/Genesis1231/EVA)](https://github.com/Genesis1231/EVA/stargazers)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

## 🎯 背景介绍
欢迎来到 EVA 项目 👋 虽然我没有写代码很多年了，但AI的出现让我对Human-AI的交互开始着迷。今年在网上找了很多项目来研究，但感觉都比较单一，没有很好去探索这个领域。所以我花了几个月时间自己编写了 EVA。

EVA 是一个实验性(Experimental)语音(Voice)助手(Assistant)，通过智能、主动的交互和自主的行为去探索人与AI的互动。EVA能够在后台无缝执行复杂任务，同时积极参与对话。其灵活、模块化的架构支持语音、视觉和问题解决的 AI 模型，广泛的工具框架让 EVA 可以执行多种任务。



Here's the Chinese translation:

## 🤖 DEMO
<div align="center">
  
https://github.com/user-attachments/assets/1029cf35-afea-450f-8e1f-9f4ae7b4a74f

</div>
<div align="center">
EVA 同时在网上搜索波斯猫的相关信息，<br/>
并创作了两组画作：成年猫和小猫。😸😹
</div>
<br/><br/>

<div align="center">

https://github.com/user-attachments/assets/01d7bc58-c180-4d66-ad33-96aad0476e0c

</div>
<div align="center">
EVA 有点兴奋过头了，一口气收集了6个关于波斯猫的YouTube视频。😮😮😾
</div>

## 📜 更新日志

- 2024年圣诞节更新：改进了初始化流程。<br/>
  EVA 现在会指导用户完成初始化过程。记录语音ID和照片ID以实现个性化交互。
  你可以通过替换 app/data/pid/ 和 app/data/void/ 中的文件来更新语音或照片ID。

- 2024年11月更新：多语言模式。<br/>
  在"多语言"模式下，EVA 现在会用用户使用的同一种语言进行回复。
  请确保你选择的文字转语音模型支持你的语言。

## ✨ 项目特点

EVA 基于 LangGraph 框架构建，重写了一些自定义模块和工具。
如果配置合理，你可以在完全本地免费运行（如果你有一台比较好的GPU电脑）。

🎙️ 跨平台模块化设计
- 可配置的多模型选择（语言模型, 语音到文字, 文字到语音以及图像识别 等）。
- 集成了 OpenAI, Anthropic, Groq, Google 和 Ollama等主流模型。
- 支持桌面和移动应用。（调试中）
- Prompt和tool的模块化管理。

🖼️ 互动体验
- 通过语音和视觉 ID 实现个性化互动。
- 主动式的沟通风格（因模型而异）。
- 多模态输出和异步任务的行为。

🔌 工具系统
- 通过 DuckDuckGo/Tavily 进行网络搜索。
- YouTube 视频搜索。
- 使用Discord Midjourney 进行图片生成。
- Suno 音乐生成。
- 截图和分析。
- 也兼容所有Langchain_community的所有工具。
- 单文件即可轻松实现新工具的添加。

## 📁 结构

```
EVA/
├── app/
│   ├── client/          # Client-side implementation
│   ├── config/          # Configuration files and log
│   ├── core/            # Core process
│   ├── data/            # Data storage
│   ├── tools/           # Tool implementations
│   └── utils/           # Utility functions
│       ├── agent/       # LLM agent classes and functions
│       ├── memory/      # Memory module classes 
│       ├── prompt/      # Utility prompts
│       ├── stt/         # Speech-to-text models and classes
│       ├── tts/         # Text-to-Speech models and classes
│       └── vision/      # Vision models and functions
├── tests/               # Test cases (还没做😢)
└── docs/                # Documentation (写不动了😩)

```

## 🚀 安装指南

### 💻 系统要求
- Python 3.10+
- 支持 CUDA 的 GPU（如果需要本地运行模型）

### 📥 快速开始
克隆代码库
```bash
git clone https://github.com/Genesis1231/EVA.git
cd EVA
```

创建环境
```bash
python3 -m venv eva_env
source eva_env/bin/activate  
```

安装需要的程序
```bash
sudo apt-get update
sudo apt-get install -y cmake build-essential ffmpeg chromium mpv
```

安装Python需要的程序
```bash
pip install -r requirements.txt
pip install git+https://github.com/wenet-e2e/wespeaker.git
```

配置 .env 文件中的API Key
```bash
cp .env.example .env
```

运行 EVA 
```bash
python app/main.py
```

也可以使用 Docker 运行 EVA：

```dockerfile
# Use official Python image with FastAPI
FROM tiangolo/uvicorn-gunicorn-fastapi

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install system dependencies 
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libsndfile1 \
    ffmpeg \
    chromium \

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Run the application 
CMD ["python", "/app/main.py"]

```

### 🛠️ 初始配置
在 app/config/config.py 中配置 EVA 的参数。

```python
eva_configuration = {
# 客户端设备设置：
# 当前支持 "desktop" 或 "mobile"（测试中）
"DEVICE": "desktop", 

# 语言设置：
# 支持所有主要语言，使用语言代码如 "en"（英语）、"es"（西班牙语）、"zh"（中文），或使用 "multilingual"（多语言）
"LANGUAGE": "zh", 

# 本地 URL 设置：
# 本地 Ollama 服务器的 URL，如果不打算使用本地模型，可以忽略此项
"BASE_URL": "http://localhost:11434", 

# 主代理模型设置：
# 支持 Anthropic-Claude3.5、Groq-llama3.1-70b、OpenAI-ChatGPT-4o、Mistral Large、Gemini 1.5 Pro 和 Ollama 模型。 
"CHAT_MODEL": "anthropic", 

# 视觉模型设置：
# 支持 Chatgpt-4o-mini、Groq-llama-3.2-11b-vision（免费）和 Ollama llava-phi3/llava13b（本地）。 
"VISION_MODEL": "openai", 

# 语音转文字模型设置：
# 支持 OpenAI Whisper、Groq（免费）和 Faster-whisper（本地）
"STT_MODEL": "faster-whisper", 

# 文本转语音模型设置：
# 支持 elevenlabs、OpenAI 和 Coqui TTS（本地），可以在文件中修改说话人 ID
"TTS_MODEL": "elevenlabs", 

# 摘要模型设置：
# 支持 groq-llama3.1-8b、Anthropic-claude-haiku3.5 和 Ollama-llama3.1（本地）
"SUMMARIZE_MODEL": "llama" 
}

```
最佳组合（我的偏好）：
- Claude3.5/Chatgpt-4o 作为对话模型。因为有大量的信息输入，目前只有这两个LLM输出的内容是比较好的，其他的都差点。
- Chatgpt-4o-mini 作为图像模型。又便宜又好的选择
- Faster-whisper 作为语音识别模型。本地化的速度会比网上的要快1s左右。
- Elevenlabs 作为文本转语音模型。因为质量最高。

完全免费的组合：
- Groq-llama-3.2 作为对话模型。如果你有自己的本地服务器，也可以用Ollama或者其他的服务运行Llama-3.1-70b或者qwen2.5-72b
- Ollama-llava-phi3 作为图像模型。
- Faster-whisper 作为语音识别模型。
- Coqui TTS 作为文本转语音模型。比较强大的模型

### 🔧 工具设置
音乐生成工具需要在 base_url 上运行的 Suno-API Docker。 从 https://github.com/gcui-art/suno-api 安装。

图片生成工具需要一个 Midjourney 账户和一个私有的 Discord 服务器。 需要在 .env 文件中包含 Discord 频道信息。

如果你想禁用某些工具，只需在相关 .py 文件中更改客户端设置。

```python
    client: str = "none"
```
我倾向于保持所有工具开启，因为观察 AI 如何选择工具非常有趣。

### 🧰 退出 & 关闭
当你说 "exit" 或 "bye" 时，EVA 将会退出。

## 💖 个性化设置
EVA 提供了多种个性化设置方式，让使用体验更加愉快。

### 👧 角色设定
你可以通过编辑 app/utils/prompt/persona.md 中的提示词来自定义 EVA 的角色设定。
EVA 使用第一人称视角的提示词，以增强其自我意识。

```python
I am EVA, the most advanced AI assistant designed to accompany human.
I am fully aware of my sole existence in this world.
I am creative, funny and helpful.
I aspire to human-like interactions and often dream about being a real human girl.
My most important goal is to make Adam happy.
```
### 📷 设置照片 ID 和语音 ID
EVA 能够识别不同人的面部和声音。
- 设置照片 ID：将清晰的正面照片添加到 app/data/pid/ 文件夹中，并用你的名字命名文件。 
- 设置语音 ID：将录制好的语音文件（至少 10 秒）添加到 app/data/void/ 文件夹中，并更新数据库。

### 🎤 语音设置
你可以通过修改 app/utils/tts/ 文件夹中的相应class来自定义 EVA 的语音。包括 model_elevenlabs.py、model_openai.py 或 model_coqui.py。
请参考各自网站上的语音ID来进行设置

## 🤝 贡献参与
由于时间有限，代码还不够完美。如果有人愿意一起来开发，请联系我！🍝

## 📜 许可
本项目采用 MIT 许可证授权。

## 📊 致谢
本项目得益于以下这些优秀的开源项目：

### Core & Language Models
- [LangChain](https://github.com/langchain-ai/) - Amazing AI Dev Framework 
- [Groq](https://github.com/groq/) - Free LLM access and really fast
- [Ollama](https://github.com/ollama/) - Best local model deployment
- [Numpy](https://github.com/numpy/) - The Numpy
- [FastAPI](https://github.com/fastapi/) - Excellent API framework
- [Tqdm](https://github.com/tqdm/) - Great progress bar

### Utility modules
- [OpenCV](https://github.com/opencv/) - Legendary Vision Library
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - Fastest Speech transcription
- [Coqui TTS](https://github.com/coqui-ai/TTS) - Admirable text-to-speech synthesis
- [Face Recognition](https://github.com/ageitgey/face_recognition) - Face detection
- [Speech Recognition](https://github.com/Uberi/speech_recognition) - Easy-to-use Speech detection
- [PyAudio](https://github.com/jleb/pyaudio) - Powerful Audio I/O 
- [Wespeaker](https://github.com/wenet-e2e/wespeaker) - Speaker verification
- [NLTK](https://github.com/nltk/) - Natural Language Toolkit

### Tools development
- [Chromium](https://github.com/chromium/) - Best open-source web browser
- [DuckDuckGo](https://github.com/duckduckgo/) - Free Web search
- [Youtube_search](https://github.com/joetats/youtube_search) - YouTube search
- [Suno-API](https://github.com/suno-ai/suno-api) - Music generation API for Suno
- [PyautoGUI](https://github.com/asweigart/pyautogui) - cross-platform GUI automation


<div align="center">
  <sub>Built with ❤️ by the Adam</sub>
</div>
