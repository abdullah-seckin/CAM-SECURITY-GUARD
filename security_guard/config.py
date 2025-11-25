import json
import logging
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from telegram import Bot
from ultralytics import YOLO

# Base directory of the project (cam-security-guard root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ------------------ Configuration Settings ------------------
with open(CONFIG_PATH, encoding="utf-8") as f:
    _config = json.load(f)

TELEGRAM_TOKEN = _config["TELEGRAM_TOKEN"]
AUTHORIZED_USER_ID = _config["AUTHORIZED_USER_ID"]
CAMERA_INDEXES = _config["CAMERA_INDEXES"]
VIDEO_SAVE_DIR = _config["VIDEO_SAVE_DIR"]
YOLO_MODEL_PATH = _config["YOLO_MODEL_PATH"]
MAX_RECORDER_QUEUE_SIZE = _config["MAX_RECORDER_QUEUE_SIZE"]
MAX_ALERT_QUEUE_SIZE = _config["MAX_ALERT_QUEUE_SIZE"]
FRAME_SIZE = tuple(_config["FRAME_SIZE"])
FPS = _config["FPS"]
MUTE_DURATIONS = _config["MUTE_DURATIONS"]
SECURE_LEVEL = _config["SECURE_LEVEL"]
SECRET_KEY = _config["SECRET_KEY"]

# --- Admin Panel Credentials ---
ADMIN_USERNAME = _config["ADMIN_USERNAME"]
ADMIN_PASSWORD = _config["ADMIN_PASSWORD"]

# ------------------ Locks for Thread Safety ------------------
system_running_lock = threading.Lock()
mute_until_lock = threading.Lock()
secure_level_lock = threading.Lock()
alert_lock = threading.Lock()


@dataclass
class AppState:
    """Mutable runtime state for the application."""

    system_running: bool = True
    mute_until: datetime = datetime.min
    last_alert_sent: datetime = datetime.min
    latest_frames: dict[int, Any] = field(default_factory=dict)
    camera_locks: dict[int, threading.Lock] = field(default_factory=dict)
    recorder_queues: dict[int, queue.Queue] = field(default_factory=dict)
    alert_queue: queue.Queue = field(
        default_factory=lambda: queue.Queue(maxsize=MAX_ALERT_QUEUE_SIZE)
    )
    bot_loop: Any = None


# Single shared state instance
state = AppState()

# Thread pool executor for background jobs
executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)

# YOLO model & Telegram bot
model = YOLO(YOLO_MODEL_PATH).float()
bot = Bot(token=TELEGRAM_TOKEN)

# ------------------ Logging configuration ------------------
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "security_guard_logs.txt"),
    filemode="a",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
