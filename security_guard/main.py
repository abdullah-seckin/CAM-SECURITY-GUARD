"""
 █████╗ ███████╗    ███████╗ ██████╗██████╗ ██╗   ██╗██████╗ ████████╗
██╔══██╗██╔════╝    ██╔════╝██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝
███████║███████╗    ███████╗██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   
██╔══██║╚════██║    ╚════██║██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   
██║  ██║███████║    ███████║╚██████╗██║  ██║   ██║   ██║        ██║   
╚═╝  ╚═╝╚══════╝    ╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝  

 AI-powered multi-camera security system with YOLO detection, Telegram alerts, and a Flask web dashboard.
    • Real-time human detection on one or more cameras
    • Automatic video recording and time-based archiving
    • Telegram alerts with snapshots and optional 5-minute video clips
    • A browser-based monitoring and recordings panel

Author:      Abdullah SECKIN
Version:     1.1.0
License:     MIT License
Date:        25.11.2025
Dependencies:
    - opencv-python
    - ultralytics
    - python-telegram-bot
    - Flask    
Compatibility:
    - Windows | Linux | macOS


# Example usage
>>> python -m security_guard.main
"""
import asyncio
import os
import platform
import threading
import time
from datetime import datetime

from . import config, webapp
from .alerts import AlertSystem
from .bot import SecurityBot
from .camera import CameraStream
from .config import logger
from .detection import DetectionEngine
from .recorder import VideoRecorder


def main() -> None:
    """Main entry point for cam-security-guard."""
    # Create a dedicated event loop for the Telegram bot
    config.bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(config.bot_loop)

    # Simple date check (copied from original script)
    current_year = datetime.now().year
    if current_year > 2025:
        logger.error("Invalid system clock! Please correct date and time.")
        raise SystemExit(1)

    os.makedirs(config.VIDEO_SAVE_DIR, exist_ok=True)

    cameras = [CameraStream(idx) for idx in config.CAMERA_INDEXES]
    recorders = [VideoRecorder(idx) for idx in config.CAMERA_INDEXES]

    detector = DetectionEngine(camera_index=0)
    alerts = AlertSystem()

    security_bot = SecurityBot()

    threads: list[threading.Thread] = []

    # Start camera threads
    for cam in cameras:
        t = threading.Thread(target=cam.run, name=f"Camera-{cam.camera_index}")
        t.daemon = True
        t.start()
        threads.append(t)

    # Start recorder threads
    for rec in recorders:
        t = threading.Thread(target=rec.run, name=f"Recorder-{rec.camera_index}")
        t.daemon = True
        t.start()
        threads.append(t)

    # Detection engine
    t_detector = threading.Thread(target=detector.run, name="DetectionEngine")
    t_detector.daemon = True
    t_detector.start()
    threads.append(t_detector)

    # Alert system
    t_alert = threading.Thread(target=alerts.run, name="AlertSystem")
    t_alert.daemon = True
    t_alert.start()
    threads.append(t_alert)

    # Flask web server (live stream & recordings)
    stream_thread = threading.Thread(
        target=webapp.run_stream_server,
        name="FlaskWebApp",
        daemon=True,
    )
    stream_thread.start()
    threads.append(stream_thread)

    # Telegram bot
    t_bot = threading.Thread(
        target=lambda: config.bot_loop.run_until_complete(security_bot.run_bot()),
        name="TelegramBot",
        daemon=True,
    )
    t_bot.start()
    threads.append(t_bot)

    # Send startup message
    time.sleep(2)
    try:
        future = asyncio.run_coroutine_threadsafe(
            config.bot.send_message(
                chat_id=config.AUTHORIZED_USER_ID,
                text="Service Started 🥳",
            ),
            config.bot_loop,
        )
        future.result(timeout=10)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Service started message has not been sent: {e}")

    # Main loop
    try:
        while config.system_running:
            time.sleep(1)
    except KeyboardInterrupt:
        with config.system_running_lock:
            config.system_running = False
        logger.info("Service Closing...")

    for cam in cameras:
        cam.stop()

    if config.bot_loop is not None:
        config.bot_loop.stop()
    logger.info("App Closed.")


if __name__ == "__main__":
    if platform.system() == "Windows":
        # Avoid asyncio warning on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    main()
