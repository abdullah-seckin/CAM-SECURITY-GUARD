import asyncio
import os
import subprocess
import time
from datetime import datetime, timedelta

import cv2
from telegram import InputFile
from telegram.constants import ChatAction

from . import config
from .config import logger


class DetectionEngine:
    """Runs YOLO human detection on the latest frames and triggers alerts.

    Periodically copies frames from ``config.latest_frames`` and runs YOLO
    human detection. On detection, sends frames to ``config.alert_queue``.
    If ``config.SECURE_LEVEL`` is 2, merges and sends recent recordings.
    """

    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self.last_detection: datetime = datetime.min
        self.last_15min_sent: datetime = datetime.min
        self.cooldown: timedelta = timedelta(minutes=5)  # 5 minute cooldown

    def run(self) -> None:
        """Main detection loop."""
        while config.system_running:
            try:
                frame = None
                if self.camera_index in config.camera_locks:
                    with config.camera_locks[self.camera_index]:
                        if config.latest_frames.get(self.camera_index) is not None:
                            frame = config.latest_frames[self.camera_index].copy()

                if frame is not None:
                    results = config.model.track(frame, persist=True, verbose=False)

                    # Only proceed when a person is detected
                    if self.check_human_presence(results):
                        annotated_frame = self.plot_human_boxes(frame, results)

                        if not config.alert_queue.full():
                            config.alert_queue.put(annotated_frame)

                        if config.SECURE_LEVEL == 2:
                            config.executor.submit(self.send_last_15min_recording)

                time.sleep(0.1)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Detection error: {str(e)}")

    def check_human_presence(self, results) -> bool:
        """Return True if any person (class 0) is detected."""
        for result in results:
            if 0 in result.boxes.cls:
                logger.info("Person detected")
                self.last_detection = datetime.now()
                return True
        return False

    def plot_human_boxes(self, frame, results):
        """Draw bounding boxes only for the person class (ID=0)."""
        annotated_frame = frame.copy()

        for result in results:
            for box, cls in zip(result.boxes.xyxy, result.boxes.cls):
                if int(cls) == 0:  # 0 = person class ID
                    x1, y1, x2, y2 = map(int, box)

                    cv2.rectangle(
                        annotated_frame,
                        (x1, y1),
                        (x2, y2),
                        (0, 255, 0),
                        2,
                    )
                    cv2.putText(
                        annotated_frame,
                        "Human",
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )
        return annotated_frame

    def send_last_15min_recording(self) -> None:
        """Merge and send the last few minutes of recordings (5 minutes)."""
        try:
            with config.mute_until_lock:
                if (datetime.now() - self.last_15min_sent) < self.cooldown:
                    return

            end_time = datetime.now().replace(second=0, microsecond=0)
            start_time = end_time - timedelta(minutes=5)

            files = self.find_recordings(start_time, end_time)
            if files:
                self.merge_and_send(files)
                with config.mute_until_lock:
                    self.last_15min_sent = datetime.now()
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"15-minute recording error: {str(e)}")

    def find_recordings(self, start: datetime, end: datetime) -> list[str]:
        """Check for an .avi file for each minute in the start-end range."""
        files: list[str] = []
        current = start.replace(second=0, microsecond=0)
        while current <= end:
            path = os.path.join(
                config.VIDEO_SAVE_DIR,
                str(self.camera_index),
                f"{current.year}",
                f"{current.month:02d}",
                f"{current.day:02d}",
                f"{current.hour:02d}",
                f"{current.minute:02d}.avi",
            )
            if os.path.exists(path):
                files.append(path)
            current += timedelta(minutes=1)
        return files

    def merge_and_send(self, files: list[str]) -> None:
        """Merge the given files with ffmpeg and send as a single video."""
        try:
            merged_file = f"merged_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
            filelist_path = "filelist.txt"
            with open(filelist_path, "w", encoding="utf-8") as f:
                for file in files:
                    f.write(f"file '{file}'\n")

            asyncio.run_coroutine_threadsafe(
                self.send_merge_progress(True),
                loop=config.bot_loop,
            )

            cmd = [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                filelist_path,
                "-c",
                "copy",
                "-y",
                merged_file,
            ]
            subprocess.run(cmd, check=True, timeout=300)

            asyncio.run_coroutine_threadsafe(
                self.send_merge_progress(False),
                loop=config.bot_loop,
            )

            asyncio.run_coroutine_threadsafe(
                self.send_video(merged_file),
                loop=config.bot_loop,
            )
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timeout!")
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Video merge error: {str(e)}")
        finally:
            if os.path.exists("filelist.txt"):
                os.remove("filelist.txt")

    async def send_merge_progress(self, is_starting: bool):
        action = ChatAction.UPLOAD_VIDEO if is_starting else ChatAction.TYPING
        await config.bot.send_chat_action(
            chat_id=config.AUTHORIZED_USER_ID,
            action=action,
        )

    @staticmethod
    def get_mute_status():
        """Helper to read current mute-until timestamp."""
        with config.mute_until_lock:
            return config.mute_until

    @staticmethod
    def set_mute(duration: int) -> None:
        """Helper to set mute-until for the given duration in seconds."""
        with config.mute_until_lock:
            config.mute_until = datetime.now() + timedelta(seconds=duration)

    async def send_video(self, filename: str) -> None:
        """Send the merged video to Telegram and delete the file."""
        try:
            with open(filename, "rb") as video:
                await config.bot.send_video(
                    chat_id=config.AUTHORIZED_USER_ID,
                    video=InputFile(video),
                    caption="Last 15 minutes recording",
                    write_timeout=60,
                )
            os.remove(filename)
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Video could not be sent: {str(e)}")
