# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EVA01 is an autonomous AI agent that lives on her own — with her own personality, goals, memory, and evolving inner world. She interacts through physical senses (voice + vision) and digital capabilities. Built on LangGraph, Python 3.10+ backend, React + Vite frontend.

Evolving from the original EVA voice assistant toward a fully autonomous agent with persistent state, proactive behavior, and a growing inner life.

## Planning & Research

Reference docs in `planning/` — consult these when working on architecture decisions:
- `planning/eva01-vision.md` — project vision, proposed graph topology, identity workspace design
- `planning/langgraph-latest.md` — LangGraph v1.0 features: checkpointers, Runtime context, interrupt(), Store, cron, multi-agent
- `planning/openclaw-patterns.md` — patterns from OpenClaw: SOUL.md, heartbeat daemon, hybrid memory, smart skill injection
- `planning/current-codebase-analysis.md` — what to keep, bugs to fix, coupling issues, missing capabilities
- `planning/cognitive-architecture.md` — three-layer mind model (autonomic/subconscious/conscious), drive engine, thought surfacing via convergence, consolidation

**IMPORTANT**: When doing research, use information no more than 3 month from [Current Date] 

## Commands

### Run EVA
```bash
python main.py
```
Entry point calls `EVA()` which builds a LangGraph, compiles it, and runs the conversation loop indefinitely.

### Run EVA API server (mobile mode)
```bash
python server.py
```
Starts the FastAPI/uvicorn server on port 8080. Requires the React frontend to connect.

### React frontend
```bash
cd frontend && npm install && npm run dev
```
Runs on http://localhost:3000. Requires EVA server running on port 8080 in mobile mode.

### Tests
```bash
python -m pytest test/
```

## Architecture

### Core Loop (`eva/core/eva.py`)

EVA is a LangGraph `StateGraph` with these nodes flowing in a cycle:

```
initialize → [setup (first-run only)] → converse → action → sense → converse → ...
```

- **converse**: Builds prompt via `PromptConstructor`, calls `agent.respond()`, sends speech to client, routes to action or sense
- **action**: Executes tool calls in parallel via `ThreadPoolExecutor`, routes back to converse with results
- **sense**: Gets next user input (speech + vision) from client, detects "bye"/"exit" for termination
- **setup**: Two-step first-run flow collecting user name, photo ID, voice ID, and "core life desire"

State is tracked in `EvaState` TypedDict with status enum: `THINKING | WAITING | ACTION | END | ERROR | SETUP`.

### Client Layer (`eva/client/`)

Two client implementations sharing the same interface (`initialize_modules`, `send`, `receive`, `start`, `send_over`, `deactivate`):

- **WSLClient**: Direct hardware access — local microphone, webcam (OpenCV/V4L2), speakers. Desktop only.
- **MobileClient**: Runs a FastAPI/uvicorn server on port 8080 with WebSocket (`/ws/{client_id}`) and file download endpoints. Communicates with the React frontend.

`DataManager` queues and processes incoming WebSocket messages by type (audio → STT transcription, frontImage/backImage → vision description, over → end-of-turn).

### LLM Agent (`eva/agent/`)

- **ChatAgent** (`chatagent.py`): Primary reasoning engine. Supports 9+ model providers (Claude, ChatGPT, Groq, Gemini, Mistral, Ollama, Grok, DeepSeek, Qwen). Output is structured JSON via `JsonOutputParser` → `AgentOutput` (analysis, strategy, response, premeditation, action list).
- **SmallAgent** (`smallagent.py`): Lightweight model for memory summarization. Pickle-safe with lazy LLM init.
- **PromptConstructor** (`constructor.py`): Assembles prompts with XML-tagged sections: `<PERSONA>`, `<TOOLS>`, `<CONVERSATION_HISTORY>`, `<CONTEXT>`, `<INSTRUCTIONS>`.

### Prompt Design

All prompts use **first-person perspective** ("I am EVA", "I see", "I hear") — this is an intentional design choice for self-awareness. Prompt templates are Markdown files in `eva/utils/prompt/` loaded via `load_prompt(name)` and updated via `update_prompt(name, text)`.

### Tools (`eva/tools/`)

Tools extend LangChain `BaseTool`. Each tool file is auto-discovered and instantiated by `ToolManager`. Tools are filtered by `client` attribute ("desktop", "mobile", "all", "none" to disable). Two-phase execution: `_run()` returns data dict for the LLM, optional `run_client()` triggers client-side UI actions (play music, show video, display images).

To add a new tool: create a `.py` file in `eva/tools/` following the LangChain `BaseTool` template. To disable: set `client = "none"`.

### Subsystems in `eva/utils/`

| Module | Purpose | Key pattern |
|--------|---------|-------------|
| `stt/` | Speech-to-text (faster-whisper, Whisper, Groq) | `Transcriber` dispatches to model; runs voice ID in parallel thread |
| `tts/` | Text-to-speech (ElevenLabs, OpenAI, Coqui) | `Speaker` factory; `speak()` for realtime, `get_audio()` for file output |
| `vision/` | Webcam + face recognition + image description | `Watcher.glance()` detects scene changes (>40% pixel diff); `Describer` runs face ID + vision model in parallel |
| `memory/` | Session history + SQLite logging | Async writes via threads; auto-summarizes after 10 entries using `SmallAgent` |
| `extension/` | Discord/Midjourney image gen, browser window launcher | `MidjourneyServer` polls Discord API; `Window` writes temp HTML + opens in Chromium |
