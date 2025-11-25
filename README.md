# cam-security-guard

An AI-powered multi-camera security system written in Python.

`cam-security-guard` combines OpenCV, YOLO, Telegram Bot API, and a modern Flask web interface to provide:

- Real-time human detection on one or more cameras
- Automatic video recording and time-based archiving
- Telegram alerts with snapshots and optional 5-minute video clips
- A browser-based monitoring and recordings panel

It is designed to run on a local machine (Linux/macOS/Windows), with storage on an internal or external drive (for example, `/media/user/hdd1/...` on Ubuntu).

## Outputs View
![Telegram Output](https://github.com/abdullah-seckin/CAM-SECURITY-GUARD/blob/main/Output.png)


---

## Features

- **Multi-camera support**
  - Configurable list of camera indices (`CAMERA_INDEXES`)
  - Each camera has its own recording queue and directory structure

- **Continuous recording**
  - Video files are written per minute in a structured folder layout:
    - `VIDEO_SAVE_DIR/<camera_index>/Year/Month/Day/Hour/Minute.avi`
  - Automatic directory creation

- **AI-based human detection**
  - YOLO model (configurable via `YOLO_MODEL_PATH`)
  - Person (class ID 0) detection with bounding boxes
  - Detection engine runs in its own thread

- **Telegram integration**
  - Instant alerts with image snapshots
  - Optional "last 5 minutes" merged video clip (Secure Level 2)
  - Commands to:
    - Mute notifications for a period
    - Request a snapshot
    - Download recordings for a specific time range
    - Delete all recordings
    - Change security level
    - Gracefully shut down the system

- **Web interface (Flask)**
  - Login-protected admin panel
  - Live MJPEG stream view
  - Recordings explorer (drill down by folders, download/delete files)
  - Snapshot capture and download from the browser

- **Config-driven behavior**
  - All core settings stored in `config.json` in the project root
  - Admin credentials and secret key also managed via config

- **Modular architecture**
  - Clean separation into modules:
    - `config`, `camera`, `recorder`, `detection`, `alerts`, `bot`, `webapp`, `main`
  - Threaded design with shared application state

---

## Architecture Overview

```text
cam-security-guard/
├─ config.json                 # Global configuration (token, paths, credentials, etc.)
├─ pyproject.toml              # Tooling configuration (Black, isort, Ruff, etc.)
└─ security_guard/
   ├─ __init__.py              # Package marker
   ├─ config.py                # Config loading, global constants, logging
   ├─ camera.py                # CameraStream: grab frames from cameras
   ├─ recorder.py              # VideoRecorder: write frames to .avi files
   ├─ detection.py             # DetectionEngine: YOLO-based human detection
   ├─ alerts.py                # AlertSystem: send alerts to Telegram
   ├─ bot.py                   # SecurityBot: Telegram command handlers
   ├─ webapp.py                # Flask app: login, live stream, recordings explorer
   └─ main.py                  # Application entry point (thread orchestration)
```

High-level flow:

1. `main.py` loads `config.json` and initializes the YOLO model and Telegram bot.
2. `CameraStream` threads capture frames and:
   - Store the latest frame per camera in shared state.
   - Push frames into per-camera recording queues.
3. `VideoRecorder` threads consume recording queues and write `.avi` files per minute.
4. `DetectionEngine` reads latest frames, runs YOLO, and:
   - On person detection, pushes annotated frames into an alert queue.
   - If `SECURE_LEVEL == 2`, merges the last few minutes of video and prepares a clip.
5. `AlertSystem` consumes annotated frames and sends Telegram alerts (respecting mute/cooldowns).
6. `SecurityBot` handles Telegram commands for control and download features.
7. `webapp.py` runs a Flask server providing:
   - Live MJPEG stream (using latest frames).
   - Recordings browser and file operations.
   - Login/logout and snapshot capture.

---

## Requirements

- **Python**: 3.10+ recommended
- **Operating System**:
  - Linux (Ubuntu tested)
  - macOS
  - Windows (with suitable camera and ffmpeg support)
- **System dependencies**:
  - `ffmpeg` (required for merging video segments into a single clip)
  - Cameras accessible via OpenCV (USB webcams, laptop camera, or IP cameras if configured)

**Python packages** (typical; your `requirements.txt` should match):

- `opencv-python`
- `ultralytics`
- `python-telegram-bot` (v20+ suggested)
- `Flask`
---

## Installation

Clone the repository:

```bash
git clone https://github.com/your-username/CAM-SECURITY-GUARD.git
cd cam-security-guard
```

(Optional) Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\\Scripts\\activate   # Windows (PowerShell/CMD)
```

Install dependencies (assuming you have a `requirements.txt`):

```bash
pip install -r requirements.txt
```

Make sure `ffmpeg` is installed and available in your `PATH`:

```bash
ffmpeg -version
```

If this command fails, install ffmpeg via your OS package manager (for example `apt`, `brew`, `choco`).

---

## Configuration

All runtime configuration is stored in `config.json` in the project root (same level as `security_guard/`).

Example `config.json`:

```json
{
  "TELEGRAM_TOKEN": "1234567890:YOUR_TELEGRAM_BOT_TOKEN_HERE",
  "AUTHORIZED_USER_ID": 123456789,

  "CAMERA_INDEXES": [0],

  "VIDEO_SAVE_DIR": "/media/user/hdd1/cam-security-guard/videos",

  "YOLO_MODEL_PATH": "/media/user/hdd1/cam-security-guard/models/yolo11n.pt",

  "MAX_RECORDER_QUEUE_SIZE": 300,
  "MAX_ALERT_QUEUE_SIZE": 50,

  "FRAME_SIZE": [640, 480],
  "FPS": 25,

  "MUTE_DURATIONS": {
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600
  },

  "SECURE_LEVEL": 1,

  "ADMIN_USERNAME": "username",
  "ADMIN_PASSWORD": "password",

  "SECRET_KEY": "change_this_to_a_long_random_string"
}
```

Field notes:

- **TELEGRAM_TOKEN**: Bot token from BotFather.
- **AUTHORIZED_USER_ID**: Your Telegram numeric user ID (only this user can control the system).
- **CAMERA_INDEXES**: List of OpenCV camera indices (for example `[0]`, `[0, 1]`).
- **VIDEO_SAVE_DIR**: Base directory for recordings and snapshots (here on an external drive).
- **YOLO_MODEL_PATH**: Path to the YOLO model file (for example `yolo11n.pt`).
- **MAX_RECORDER_QUEUE_SIZE / MAX_ALERT_QUEUE_SIZE**: Queue sizes for frame buffering and alerts.
- **FRAME_SIZE**: Width and height used for capture and recording.
- **FPS**: Capture/recording frame rate.
- **MUTE_DURATIONS**: Mapping of textual shortcuts (used in `/mute`) to seconds.
- **SECURE_LEVEL**:
  - `1` – send only snapshot alerts.
  - `2` – send snapshots plus merged last 5 minutes of video (heavier on disk/network).
- **ADMIN_USERNAME / ADMIN_PASSWORD**: Credentials for the Flask web admin panel.
- **SECRET_KEY**:
  - A long, random string used by Flask to sign session cookies.
  - This must be kept secret. To generate, for example:

    ```bash
    python -c "import secrets; print(secrets.token_hex(32))"
    ```

---

## Running the Application

From the project root:

```bash
python -m security_guard.main
```

This will:

- Load `config.json`
- Initialize the YOLO model and Telegram bot
- Start:
  - Camera capture threads
  - Recorder threads
  - Detection engine
  - Alert system
  - Flask web server (default `0.0.0.0:5001`)
  - Telegram bot polling loop

You should see log messages in the terminal and in `security_guard_logs.txt`.

---

## Web Interface

### Login

1. Open your browser and navigate to:

   ```text
   http://localhost:5001/login
   ```

2. Enter the `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `config.json`.

### Live Stream

- URL:

  ```text
  http://localhost:5001/live
  ```

- Features:
  - MJPEG live video feed (Camera 0 by default).
  - "Capture Photo & Download" button to save a snapshot.
  - "Stop Stream" button to stop the streaming loop from the web UI.
  - Quick link to the recordings page.

### Recordings Explorer

- URL:

  ```text
  http://localhost:5001/recordings
  ```

- Features:
  - Folder navigation (root → camera index → year → month → day → hour)
  - Table of recordings:
    - Date/Time
    - Camera index
    - Relative path
    - File size
    - Download + Delete actions

All web routes require a valid login session (`session["logged_in"]`).

---

## Telegram Bot Commands

The bot only accepts commands from `AUTHORIZED_USER_ID`.

Common commands (names based on the implementation):

- `/start`  
  Simple system status message.

- `/mute <duration-key>`  
  Mute alerts for a configured period.

  Examples:

  ```text
  /mute 5min
  /mute 15min
  /mute 1hour
  ```

- `/start_stream`  
  Mark the live stream as active and return a URL to the stream (you can customize the URL to your LAN IP or domain).

- `/frame`  
  Capture a snapshot from camera 0 and send it as a photo.

- `/delete`  
  Delete all recordings under `VIDEO_SAVE_DIR`. **Use with caution**.

- `/secure <level>`  
  Change security level:

  ```text
  /secure 1
  /secure 2
  ```

- `/download <YYYYMMDDHHmm> <YYYYMMDDHHmm>`  
  Collect recordings for the given time range, zip them, and send as a document.

  Example:

  ```text
  /download 202501222200 202501222230
  ```

- `/shutdown`  
  Gracefully shut down the system (sets `system_running = False` and exits).

---


## Security Considerations

- This project is intended for personal / small office use on a trusted network.
- Make sure:
  - Your `TELEGRAM_TOKEN`, `AUTHORIZED_USER_ID`, `ADMIN_PASSWORD`, and `SECRET_KEY` are kept private.
  - You do not expose the Flask server directly to the internet without proper hardening (reverse proxy, TLS, firewall rules).
  - You comply with local regulations regarding video surveillance and data retention.

---

## License
[MIT](https://choosealicense.com/licenses/mit/)

---

## Support

For support, questions, or feature requests:

- Email: `dev@abdullahseckin.com`
- Or open an issue in the repository (if this is hosted on GitHub).

---

## Badges



[![Platforms](https://img.shields.io/badge/Platforms-Linux_macOS_Windows-white)](https://opensource.org/licenses/)

[![Language](https://img.shields.io/badge/Language-Python-blue)](https://www.python.org/)

[![Category](https://img.shields.io/badge/Category-Computer_Vision_/_AI-green)](https://opencv.org/)

[![Alerts](https://img.shields.io/badge/Notifications-Telegram-blue)](https://core.telegram.org/bots/api)
