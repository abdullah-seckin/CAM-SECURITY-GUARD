import os
import time
from datetime import datetime

import cv2

from . import config
from .config import logger


class VideoRecorder:
    """Consumes frames from the recording queue and writes them to disk.

    Creates a separate file for each minute (file names use
    year/month/day/hour/minute hierarchy).
    """

    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self.writer: cv2.VideoWriter | None = None
        self.start_time: datetime | None = None
        self.current_hour: int | None = None

    def get_file_path(self, timestamp: datetime) -> str:
        """Create folders and file path in Year/Month/Day/Hour/Minute hierarchy."""
        return os.path.join(
            config.VIDEO_SAVE_DIR,
            f"{self.camera_index}",
            f"{timestamp.year}",
            f"{timestamp.month:02d}",
            f"{timestamp.day:02d}",
            f"{timestamp.hour:02d}",
            f"{timestamp.minute:02d}.avi",
        )

    def run(self) -> None:
        """Continuously record frames from the queue.

        Switches to a new file when the hour changes.
        Closes the file and opens a new one every 60 seconds.
        """
        queue_ = config.recorder_queues[self.camera_index]

        while config.system_running:
            try:
                if not queue_.empty():
                    frame = queue_.get()

                    now = datetime.now()
                    # Determine if a new file should be created
                    if self.writer is None or now.hour != self.current_hour:
                        self.start_recording(now)

                    if self.writer is not None:
                        self.writer.write(frame)

                    # Switch to a new file after 1 minute
                    if (
                        self.start_time is not None
                        and (datetime.now() - self.start_time).seconds >= 60
                    ):
                        self.stop_recording()

                time.sleep(0.01)

            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Camera {self.camera_index} recording error: {str(e)}")

        # When loop ends, close the writer
        self.stop_recording()

    def start_recording(self, timestamp: datetime) -> None:
        """Open a new video file and start writing frames."""
        self.stop_recording()  # Close previous recording if any
        timestamp = timestamp.replace(second=0, microsecond=0)
        self.start_time = timestamp
        self.current_hour = timestamp.hour

        filename = self.get_file_path(timestamp)
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # If X264 fourcc is not compatible with .avi on some systems,
        # fall back to another codec.
        try:
            fourcc = cv2.VideoWriter_fourcc(*"X264")
            self.writer = cv2.VideoWriter(
                filename, fourcc, config.FPS, config.FRAME_SIZE
            )
        except Exception:  # pragma: no cover - codec fallback
            try:
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                self.writer = cv2.VideoWriter(
                    filename, fourcc, config.FPS, config.FRAME_SIZE
                )
                logger.warning("X264 codec error, falling back to MJPG")
            except Exception as e:
                logger.error(f"VideoWriter could not be created: {str(e)}")
                self.writer = None
                return

        logger.info(f"Camera {self.camera_index} - New recording started: {filename}")

    def stop_recording(self) -> None:
        """Close the current video file if open."""
        if self.writer:
            self.writer.release()
            self.writer = None
            logger.info(f"Video recording closed for camera {self.camera_index}.")
