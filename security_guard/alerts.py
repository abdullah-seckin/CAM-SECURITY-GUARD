import asyncio
import os
import time
from datetime import datetime, timedelta

import cv2

from . import config
from .config import logger


class AlertSystem:
    """Consumes detected frames from the alert queue and sends Telegram alerts.

    Respects a cooldown and the global mute period.
    """

    def __init__(self) -> None:
        self.cooldown: timedelta = timedelta(seconds=10)
        self.last_sent: datetime = datetime.min
        self.alert_lock = config.alert_lock

    def run(self) -> None:
        while config.system_running:
            try:
                # Respect mute window
                if datetime.now() < config.mute_until:
                    time.sleep(1)
                    continue

                if not config.alert_queue.empty():
                    frame = config.alert_queue.get()

                    with self.alert_lock:
                        current_time = datetime.now()
                        time_diff = (current_time - self.last_sent).total_seconds()

                        if time_diff > self.cooldown.total_seconds():
                            success = self.send_alert(frame)
                            if success:
                                self.last_sent = current_time
                            else:
                                logger.error(
                                    "Alert could not be sent; cooldown not updated"
                                )
                        else:
                            remaining = self.cooldown.total_seconds() - time_diff
                            logger.warning(
                                f"Cooldown active - Remaining: {remaining:.1f}s"
                            )

                time.sleep(0.1)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Alert system error: {str(e)}")

    def send_alert(self, frame) -> bool:
        filename = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        try:
            # Extra safety check for frame
            if frame is None or frame.size == 0 or len(frame.shape) != 3:
                logger.error("Invalid frame format")
                return False

            cv2.imwrite(filename, frame)

            future = asyncio.run_coroutine_threadsafe(
                self.async_send_alert(filename),
                loop=config.bot_loop,
            )

            try:
                future.result(timeout=10)
                return True
            except TimeoutError:
                logger.error("Alert timed out")
                return False

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Alert error: {str(e)}")
            return False
        finally:
            if os.path.exists(filename):
                os.remove(filename)

    async def async_send_alert(self, filename: str) -> bool:
        try:
            with open(filename, "rb") as photo:
                await config.bot.send_photo(
                    chat_id=config.AUTHORIZED_USER_ID,
                    photo=photo,
                    caption="🚨 Person detected!",
                )
            logger.info("Alert sent")
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Alert could not be sent: {str(e)}")
            return False
