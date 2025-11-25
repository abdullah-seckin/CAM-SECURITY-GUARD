import queue
import threading
import time
from datetime import datetime

import cv2

from . import config
from .config import logger


class CameraStream:
    """Handle continuous frame capture for a single camera.

    Runs in its own thread, continuously reading frames, updating
    ``config.latest_frames[camera_index]`` and pushing frames into the
    corresponding recorder queue.
    """

    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_SIZE[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_SIZE[1])
        self.running = True

        # Shared dictionary and lock
        config.latest_frames[self.camera_index] = None
        config.camera_locks[self.camera_index] = threading.Lock()

        # Recording queue for this camera
        config.recorder_queues[self.camera_index] = queue.Queue(
            maxsize=config.MAX_RECORDER_QUEUE_SIZE
        )

    def run(self) -> None:
        """Main capture loop."""
        while self.running and config.system_running:
            try:
                ret, frame = self.cap.read()
                if ret:
                    # Fix frame size
                    frame = cv2.resize(frame, config.FRAME_SIZE)

                    # Add timestamp
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cv2.putText(
                        frame,
                        timestamp,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                    # Save latest frame to global dictionary
                    with config.camera_locks[self.camera_index]:
                        config.latest_frames[self.camera_index] = frame

                    # Add frame to recording queue
                    queue_ = config.recorder_queues[self.camera_index]
                    if not queue_.full():
                        queue_.put(frame)

                time.sleep(0.01)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Camera {self.camera_index} error: {str(e)}")
                self.stop()

    def stop(self) -> None:
        """Stop camera capture and release resources."""
        self.running = False
        time.sleep(0.5)
        self.cap.release()
