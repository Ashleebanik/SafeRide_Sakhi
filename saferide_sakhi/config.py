"""
SafeRide Sakhi – Shared configuration and constants.
All settings read from .env via python-dotenv.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Project root ───────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent

# ── IBM watsonx / Granite 4 ────────────────────────────────────────────────────
WATSONX_API_KEY: str = os.environ.get("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID: str = os.environ.get("WATSONX_PROJECT_ID", "")
WATSONX_URL: str = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
GRANITE_MODEL_ID: str = "ibm/granite-4-dense-8b-instruct"   # update when GA

# ── Google Maps ────────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY: str = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# ── Google Gemini ──────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-1.5-flash"

# ── Groq ───────────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama3-70b-8192"

# ── Emergency / control room ───────────────────────────────────────────────────
EMERGENCY_NUMBER: str = os.environ.get("EMERGENCY_NUMBER", "112")
CONTROL_ROOM_WEBHOOK: str = os.environ.get("CONTROL_ROOM_WEBHOOK", "")

# ── App settings ───────────────────────────────────────────────────────────────
APP_ENV: str = os.environ.get("APP_ENV", "development")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TRIP_DATA_RETENTION_DAYS: int = int(os.environ.get("TRIP_DATA_RETENTION_DAYS", "7"))

# ── Vector store ───────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR: str = os.environ.get(
    "CHROMA_PERSIST_DIR", str(ROOT_DIR / "data" / "chroma_store")
)

# ── Risk thresholds ────────────────────────────────────────────────────────────
RISK_NUDGE_THRESHOLD: float = 0.35
RISK_ALERT_THRESHOLD: float = 0.60
RISK_EMERGENCY_THRESHOLD: float = 0.80

# ── Route deviation ────────────────────────────────────────────────────────────
MAX_ROUTE_DEVIATION_METRES: int = 300
UNPLANNED_STOP_SECONDS: int = 120   # stop > 2 min not at destination = flag
SILENCE_NUDGE_SECONDS: int = 300    # 5 min no check-in = nudge
SILENCE_ALERT_SECONDS: int = 600    # 10 min = alert

# ── ReAct loop cap ─────────────────────────────────────────────────────────────
REACT_MAX_ITERATIONS: int = 6
