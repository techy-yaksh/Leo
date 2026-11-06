"""
Configuration module for L.E.O. Assistant.
Loads environment variables safely from .env and exposes strongly typed application settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Define base directory (directory of this file)
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Ensure WebView2 transparent background
os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00000000"

# ==============================================================================
# AI & GROQ CONFIGURATION
# ==============================================================================
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_MAX_TOKENS: int = int(os.getenv("GROQ_MAX_TOKENS", "2048"))
MAX_CONVERSATION_HISTORY: int = int(os.getenv("MAX_CONVERSATION_HISTORY", "10"))

# ==============================================================================
# GEMINI MULTIMODAL VISION CONFIGURATION
# ==============================================================================
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# ==============================================================================
# SPOTIFY API CONFIGURATION
# ==============================================================================
SPOTIPY_CLIENT_ID: str = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
SPOTIPY_CLIENT_SECRET: str = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
SPOTIPY_REDIRECT_URI: str = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

# ==============================================================================
# FLASK & SERVER CONFIGURATION
# ==============================================================================
FLASK_HOST: str = os.getenv("FLASK_HOST", "127.0.0.1").strip()
FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "yes")
FRONTEND_TEMPLATE: str = "leo_frontend.html"

# ==============================================================================
# AUDIO & NEURAL TTS CONFIGURATION
# ==============================================================================
TTS_VOICE: str = os.getenv("TTS_VOICE", "en-US-AndrewNeural").strip()
TTS_RATE: str = os.getenv("TTS_RATE", "+5%").strip()
SPEECH_ENERGY_THRESHOLD: int = int(os.getenv("SPEECH_ENERGY_THRESHOLD", "150"))
SPEECH_DYNAMIC_ENERGY: bool = os.getenv("SPEECH_DYNAMIC_ENERGY", "False").lower() in ("true", "1", "yes")

# ==============================================================================
# WAKE-WORD CONFIGURATION
# ==============================================================================
WAKE_WORD_MODEL_FILE = BASE_DIR / "leo.onnx"
DEFAULT_WAKE_WORD_MODEL: str = "leo.onnx" if WAKE_WORD_MODEL_FILE.exists() else "hey_jarvis"
WAKE_WORD_CONFIDENCE_THRESHOLD: float = float(os.getenv("WAKE_WORD_CONFIDENCE_THRESHOLD", "0.3"))

# ==============================================================================
# DESKTOP HUD WINDOW CONFIGURATION
# ==============================================================================
WINDOW_MIN_SIZE: tuple[int, int] = (1024, 600)
WINDOW_DEFAULT_SIZE: tuple[int, int] = (1440, 900)
WINDOW_MAXIMIZED: bool = True
WINDOW_TITLE: str = "L.E.O. ORCHESTRATOR // CYBERNETIC HUD"
