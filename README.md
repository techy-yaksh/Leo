# L.E.O. (Living Electronic Orchestrator)

> A high-performance, cybernetic desktop AI assistant featuring a modular architecture, real-time token streaming, dual LLM inference (Groq LPU + Google Gemini 3.8 Flash Vision), interruptible neural text-to-speech, and global hotkey control.

---

## 🌟 Key Features

- **Dual-State Cyberpunk Interface**:
  - **Base State (Floating Logo)**: 150x150 borderless, transparent, always-on-top desktop widget with an animated 3D gyroscopic SVG reactor core.
  - **Maximized Terminal HUD**: 1280x800 full-screen dark-tech operations dashboard toggled instantly with `F8`.
- **Multimodal Screen Vision**:
  - Captures the primary display via `mss` and sends high-resolution frames to **Google Gemini 3.8 Flash** (`gemini-3.8-flash`) for real-time visual analysis when asked *"What is on my screen?"* or *"Look at this"*.
- **Ultra-Fast LLM Reasoning**:
  - Powered by **Groq LPU** (`openai/gpt-oss-120b`) with Server-Sent Events (SSE) streaming tokens to the UI with sub-second latency and an increased `2048` token context limit.
- **Interruptible Neural Audio Pipeline**:
  - Primary **Microsoft Edge Neural TTS** streaming with sentence-level chunking.
  - Offline **Windows SAPI / pyttsx3** failover.
  - **Instant Interruption**: Tapping `Right Alt` while L.E.O. is speaking immediately cuts audio output and re-arms the microphone for Push-to-Talk.
- **Thread-Safe State Machine**:
  - Atomic transitions across `IDLE`, `LISTENING`, `PROCESSING`, and `SPEAKING` preventing UI desync and race conditions.
- **Local System Control & Tool Calling**:
  - Native volume adjustment via `pycaw`, system metrics monitoring (`psutil`), application launching, file search in Windows Explorer, and Spotify playback.
- **Security-First Configuration**:
  - Complete `.env` isolation using `python-dotenv`. No hardcoded credentials or API keys in tracked files.

---

## ⌨️ Global Controls & Hotkeys

| Key | Mode | Action |
| :--- | :--- | :--- |
| `F8` | Global Hotkey | Toggle between **Floating Logo (150x150)** and **Maximized HUD (1280x800)** |
| `Right Alt` | Global (Idle) | **Push-To-Talk (PTT)**: Hold to record, release to execute |
| `Right Alt` | Global (Speaking) | **Audio Interrupt**: Instantly cuts speech playback and switches to Listening |
| Wake Word | Voice | Say *"Hey Jarvis"* or custom *"Leo"* wake-word to activate |

---

## 📁 Project Architecture

```
LEO/
├── .env.example               # Environment variables template
├── .gitignore                 # Excludes .env, caches, audio temps
├── config.py                  # Strongly typed configuration & env loader
├── main.py                    # Primary application runner & webview orchestrator
├── leo_backend.py             # Backward-compatibility wrapper for Launch_LEO.vbs
├── Launch_LEO.vbs             # Silent background launcher
├── leo_frontend.html          # Cyberpunk 3D Gyroscopic HUD interface
├── requirements.txt           # Project dependencies
├── services/                  # Modular domain services
│   ├── __init__.py
│   ├── state_service.py       # Strict, thread-safe UI/Assistant State Machine
│   ├── vision_service.py      # mss screen capture & Gemini 3.8 Flash vision
│   ├── agent_service.py       # Groq LPU streaming, tool routing & memory
│   ├── audio_service.py       # Interruptible Edge TTS streaming + pyttsx3 failover
│   ├── speech_service.py      # openWakeWord listener & global hotkey hooks
│   ├── server_service.py      # Flask REST/SSE API & window geometry controller
│   └── system_service.py      # OS automation, hardware telemetry, Spotify
└── core/                      # Backward-compatibility adapter layer
    ├── __init__.py
    ├── ai_agent.py            # Adapter redirecting to services.agent_service
    └── system_tools.py        # Adapter redirecting to services.system_service
```

---

## 🚀 Quick Start

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/techy-yaksh/Leo.git
cd Leo

# Install dependencies in Python 3.10+ / Anaconda
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy the `.env.example` file to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:
- `GROQ_API_KEY`: Get a free key at [console.groq.com](https://console.groq.com/)
- `GEMINI_API_KEY`: Get a free key at [aistudio.google.com](https://aistudio.google.com/)

### 3. Launch L.E.O.

```bash
# Launch from terminal:
python main.py

# Or run silently in the background on Windows:
double-click Launch_LEO.vbs
```

---

## 🛡️ License

MIT License. Designed and maintained by [techy-yaksh](https://github.com/techy-yaksh).
