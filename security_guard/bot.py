import asyncio
import os
import shutil
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import config, webapp
from .config import logger


class SecurityBot:
    """Manages Telegram bot commands for the security system."""

    def __init__(self) -> None:
        self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
        self.register_handlers()

    async def check_auth(self, update: Update) -> bool:
        if update.effective_user.id != config.AUTHORIZED_USER_ID:
            await update.message.reply_text("⛔ Unauthorized access!")
            return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_auth(update):
            return
        await update.message.reply_text("🛡️ Security system is active")

    async def mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_auth(update):
            return

        duration_key = context.args[0] if context.args else "15dk"
        duration = config.MUTE_DURATIONS.get(duration_key, 900)
        with config.mute_until_lock:
            config.mute_until = datetime.now() + timedelta(seconds=duration)
        await update.message.reply_text(
            f"🔇 Notifications muted for {duration // 60} minutes"
        )

    async def start_stream(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self.check_auth(update):
            return

        with webapp.stream_lock:
            if webapp.stream_active:
                await update.message.reply_text("Live stream is already active!")
                return
            webapp.stream_active = True

        # Put your static/accessible IP here
        stream_link = "http://192.168.1.125:1234/live"
        await update.message.reply_text(f"Live stream started. Watch at: {stream_link}")

    async def shutdown(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self.check_auth(update):
            return

        with config.system_running_lock:
            config.system_running = False
        await update.message.reply_text("⏳ Shutting down system...")
        os._exit(0)

    async def get_frame(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self.check_auth(update):
            return

        cam_index = 0
        try:
            lock = config.camera_locks.get(cam_index)
            if lock is None:
                await update.message.reply_text("⚠️ Camera not initialized yet.")
                return

            with lock:
                frame = (
                    config.latest_frames[cam_index].copy()
                    if config.latest_frames.get(cam_index) is not None
                    else None
                )

            if frame is None:
                await update.message.reply_text(
                    "⚠️ No frame has been captured from the camera yet."
                )
                return

            filename = f"snapshot_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            import cv2

            cv2.imwrite(filename, frame)

            with open(filename, "rb") as photo:
                await update.message.reply_photo(photo=photo)

            os.remove(filename)

        except Exception as e:  # pragma: no cover - defensive
            await update.message.reply_text(f"Error: {str(e)}")

    async def delete_recordings(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Delete all recorded videos (cleans the recordings directory)."""
        if not await self.check_auth(update):
            return

        try:
            config.executor.submit(self._delete_files)
            await update.message.reply_text("⏳ Recordings are being deleted...")
        except Exception as e:  # pragma: no cover - defensive
            await update.message.reply_text(f"Delete error: {str(e)}")

    def _delete_files(self) -> None:
        try:
            shutil.rmtree(config.VIDEO_SAVE_DIR)
            os.makedirs(config.VIDEO_SAVE_DIR, exist_ok=True)
            logger.info("All recordings deleted and directory recreated.")
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Delete error: {str(e)}")

    async def set_secure_level(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Set the security level (1 or 2)."""
        if not await self.check_auth(update):
            return

        try:
            level = int(context.args[0])
            if level not in [1, 2]:
                raise ValueError
            config.SECURE_LEVEL = level
            await update.message.reply_text(
                f"🔒 Security level set to {config.SECURE_LEVEL}"
            )
        except Exception:  # pragma: no cover - defensive
            await update.message.reply_text("⚠️ Invalid level! Please use 1 or 2.")

    async def download_recordings(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Zip recordings for a date-time range and send via Telegram.

        Usage: /download YYYYMMDDHHmm YYYYMMDDHHmm
        """
        if not await self.check_auth(update):
            return

        try:
            start_str = context.args[0]
            end_str = context.args[1]
            start = datetime.strptime(start_str, "%Y%m%d%H%M")
            end = datetime.strptime(end_str, "%Y%m%d%H%M")

            await update.message.reply_text("⏳ Download process started...")
            config.executor.submit(self._prepare_download, start, end, update)
        except Exception as e:  # pragma: no cover - defensive
            await update.message.reply_text(f"Download error: {str(e)}")

    def _prepare_download(self, start: datetime, end: datetime, update: Update) -> None:
        """Collect recordings for the given range, zip, and send via Telegram."""
        try:
            files: list[str] = []
            current = start.replace(second=0, microsecond=0)
            while current <= end:
                path = os.path.join(
                    config.VIDEO_SAVE_DIR,
                    "0",  # camera index
                    f"{current.year}",
                    f"{current.month:02d}",
                    f"{current.day:02d}",
                    f"{current.hour:02d}",
                    f"{current.minute:02d}.avi",
                )
                if os.path.exists(path):
                    files.append(path)
                current += timedelta(minutes=1)

            if files:
                temp_dir = "temp_download"
                os.makedirs(temp_dir, exist_ok=True)

                for file in files:
                    shutil.copy(file, temp_dir)

                zip_name = (
                    f"recordings_{start.strftime('%Y%m%d%H%M')}_"
                    f"{end.strftime('%Y%m%d%H%M')}.zip"
                )
                shutil.make_archive(zip_name[:-4], "zip", temp_dir)
                shutil.rmtree(temp_dir)

                asyncio.run_coroutine_threadsafe(
                    self._send_zip(zip_name, update),
                    loop=config.bot_loop,
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    update.message.reply_text(
                        "❌ No recordings found in the specified range"
                    ),
                    loop=config.bot_loop,
                )

        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Download error: {str(e)}")

    async def _send_zip(self, zip_name: str, update: Update) -> None:
        try:
            with open(zip_name, "rb") as zip_file:
                await update.message.reply_document(document=zip_file)
            os.remove(zip_name)
        except Exception as e:  # pragma: no cover - defensive
            await update.message.reply_text(f"Send error: {str(e)}")

    def register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("mute", self.mute))
        self.application.add_handler(CommandHandler("shutdown", self.shutdown))
        self.application.add_handler(CommandHandler("start_stream", self.start_stream))
        self.application.add_handler(CommandHandler("frame", self.get_frame))
        self.application.add_handler(CommandHandler("delete", self.delete_recordings))
        self.application.add_handler(CommandHandler("secure", self.set_secure_level))
        self.application.add_handler(
            CommandHandler("download", self.download_recordings)
        )

    async def run_bot(self) -> None:
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Bot is active and waiting for commands...")

        while config.system_running:
            await asyncio.sleep(3600)
