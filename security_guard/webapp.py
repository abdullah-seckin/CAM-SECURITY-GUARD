import base64
import os
import threading
import time
from datetime import datetime

import cv2
from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)

from . import config
from .config import logger

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Global flags for HTTP live stream control
stream_active: bool = False
stream_lock = threading.Lock()

# Simple user authentication info (loaded from config.json via config module)
USERNAME = config.ADMIN_USERNAME
PASSWORD = config.ADMIN_PASSWORD


STREAM_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Security Guard – Live Stream</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      background: radial-gradient(circle at top, #020617, #020617 40%, #020617);
      min-height: 100vh;
    }
    .navbar-brand { font-weight: 600; letter-spacing: .06em; text-transform: uppercase; font-size: .8rem; }
    .live-wrapper { max-width: 1200px; margin: 1rem auto 2rem; }
    .card {
      border-radius: 0.9rem;
      border: 0;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.45);
    }
    .live-image {
      background: #000;
      max-height: 70vh;
      object-fit: contain;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: .35rem;
      padding: .1rem .65rem;
      border-radius: 999px;
      font-size: .7rem;
      background: rgba(34,197,94,.12);
      color: #16a34a;
      font-weight: 500;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #22c55e;
      box-shadow: 0 0 0 6px rgba(34,197,94,.25);
    }
    @media (max-width: 991.98px) {
      .live-wrapper { padding: 0 .75rem; }
      .live-image { max-height: 55vh; }
      .card-body { padding: 1rem; }
    }
    @media (max-width: 575.98px) {
      .navbar-brand { font-size: .75rem; }
    }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('live_stream') }}">SECURITY GUARD</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNavbar">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="mainNavbar">
      <ul class="navbar-nav ms-auto">
        <li class="nav-item">
          <a class="nav-link active" href="{{ url_for('live_stream') }}">Live Stream</a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="{{ url_for('recordings_page') }}">Recordings</a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="{{ url_for('logout') }}">Logout</a>
        </li>
      </ul>
    </div>
  </div>
</nav>

<div class="container-fluid live-wrapper">
  <div class="row g-4">
    <div class="col-lg-8">
      <div class="card bg-dark text-white overflow-hidden">
        <div class="card-header bg-transparent border-0 d-flex justify-content-between align-items-center">
          <div>
            <h5 class="mb-0">Live Stream</h5>
            <small class="text-muted">Camera 0 • {{ datetime.utcnow().strftime('%Y-%m-%d') if datetime else '' }}</small>
          </div>
          <div class="status-pill">
            <span class="status-dot"></span>
            LIVE
          </div>
        </div>
        <div class="card-body text-center bg-black">
          <img src="{{ url_for('video_feed') }}" class="img-fluid live-image rounded" alt="Live Stream">
        </div>
      </div>
    </div>
    <div class="col-lg-4">
      <div class="card bg-light">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h6 class="mb-0">Actions</h6>
          <small class="text-muted">Quick access</small>
        </div>
        <div class="card-body">
          <div class="d-grid gap-2 mb-3">
            <form action="{{ url_for('capture_photo') }}" method="post">
              <button type="submit" class="btn btn-primary w-100">
                Capture Photo & Download
              </button>
            </form>
          </div>
          <div class="d-grid gap-2 mb-3">
            <form action="{{ url_for('stop_stream') }}" method="post">
              <button type="submit" class="btn btn-outline-danger w-100">
                Stop Stream
              </button>
            </form>
          </div>
          <hr class="my-3">
          <div class="d-grid gap-2">
            <a href="{{ url_for('recordings_page') }}" class="btn btn-outline-secondary w-100">
              Recordings
            </a>
          </div>
          <div class="mt-3 small text-muted">
            <div>• Browser-based video capture is supported.</div>
            <div>• For best mobile experience, landscape mode is recommended.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Security Guard – Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: radial-gradient(circle at top, #0f172a, #020617); color: #e5e7eb; }
    .card { border-radius: 1rem; }
    .brand-title { font-weight: 600; letter-spacing: .08em; text-transform: uppercase; font-size: .8rem; color: #6b7280; }
  </style>
</head>
<body>
<div class="container d-flex align-items-center justify-content-center min-vh-100">
  <div class="card shadow-lg p-4" style="max-width: 420px; width: 100%;">
    <div class="card-body">
      <div class="text-center mb-4">
        <div class="brand-title mb-1">Security Guard</div>
        <h1 class="h4 mb-0">Admin Panel</h1>
        <p class="text-muted small mb-0">Sign in to continue</p>
      </div>
      {% if error %}
      <div class="alert alert-danger small py-2 mb-3">
        Incorrect username or password.
      </div>
      {% endif %}
      <form method="post" autocomplete="off">
        <div class="mb-3">
          <label for="username" class="form-label">Username</label>
          <input type="text" class="form-control" id="username" name="username" required autofocus>
        </div>
        <div class="mb-3">
          <label for="password" class="form-label">Password</label>
          <input type="password" class="form-control" id="password" name="password" required>
        </div>
        <div class="d-grid gap-2">
          <button type="submit" class="btn btn-primary">Login</button>
        </div>
      </form>
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


RECORDINGS_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Security Guard – Recordings</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      background-color: #020617;
      min-height: 100vh;
    }
    .navbar-brand {
      font-weight: 600;
      letter-spacing: .06em;
      text-transform: uppercase;
      font-size: .8rem;
    }
    .main-wrapper {
      max-width: 1200px;
      margin: 1rem auto 2rem;
      padding: 0 .75rem;
    }
    .card {
      border-radius: 0.9rem;
      border: 0;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.45);
    }
    .badge-camera { font-size: .65rem; }
    .table-sm td, .table-sm th { padding-top: .45rem; padding-bottom: .45rem; }
    .dir-pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: .25rem .75rem;
      font-size: .8rem;
      text-decoration: none;
      border: 1px solid rgba(148, 163, 184, .6);
      color: #0f172a;
      background: #f8fafc;
    }
    .dir-pill:hover {
      background: #e5e7eb;
      border-color: rgba(148, 163, 184, 1);
      color: #020617;
      text-decoration: none;
    }
    .dir-icon {
      width: 16px;
      height: 16px;
      border-radius: 3px;
      background: linear-gradient(135deg, #38bdf8, #0ea5e9);
      margin-right: .4rem;
    }
    .file-badge {
      font-size: .7rem;
      text-transform: uppercase;
      letter-spacing: .06em;
    }
    @media (max-width: 767.98px) {
      .main-wrapper { padding: 0 .5rem; }
      .card-header { padding: .75rem 1rem; }
      .card-body { padding: .75rem 1rem 1rem; }
      .table-responsive { font-size: .85rem; }
      .breadcrumb { flex-wrap: wrap; }
    }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('live_stream') }}">SECURITY GUARD</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNavbar">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="mainNavbar">
      <ul class="navbar-nav ms-auto">
        <li class="nav-item">
          <a class="nav-link" href="{{ url_for('live_stream') }}">Live Stream</a>
        </li>
        <li class="nav-item">
          <a class="nav-link active" href="{{ url_for('recordings_page') }}">Recordings</a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="{{ url_for('logout') }}">Logout</a>
        </li>
      </ul>
    </div>
  </div>
</nav>

<div class="main-wrapper">
  <div class="card">
    <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
      <div>
        <h5 class="mb-0">{{ current_folder_name }}</h5>
        <small class="text-muted">
          {{ files|length }} recordings
          {% if current_path %}
          • <span class="file-badge text-primary">/{{ current_path }}</span>
          {% endif %}
        </small>
      </div>
      <div class="text-end small text-muted">
        <div>File explorer view</div>
        <div>You can drill down by Year / Month / Day</div>
      </div>
    </div>
    <div class="card-body">
      <nav aria-label="breadcrumb" class="mb-3">
        <ol class="breadcrumb small mb-1">
          <li class="breadcrumb-item">
            <a href="{{ url_for('recordings_page') }}">All Recordings</a>
          </li>
          {% for bc in breadcrumbs %}
          <li class="breadcrumb-item {% if loop.last %}active{% endif %}">
            {% if not loop.last %}
              <a href="{{ url_for('recordings_page', path=bc.path) }}">{{ bc.name }}</a>
            {% else %}
              {{ bc.name }}
            {% endif %}
          </li>
          {% endfor %}
        </ol>
      </nav>

      {% if dirs %}
      <div class="mb-3">
        <h6 class="text-muted text-uppercase small mb-2">Folders</h6>
        <div class="d-flex flex-wrap gap-2">
          {% for d in dirs %}
          <a href="{{ url_for('recordings_page', path=d.rel_path) }}" class="dir-pill">
            <span class="dir-icon"></span>
            {{ d.name }}
          </a>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      <div class="card shadow-sm border-0">
        <div class="card-body p-0">
          {% if files %}
          <div class="table-responsive">
            <table class="table table-sm mb-0 align-middle">
              <thead class="table-light">
                <tr>
                  <th style="width: 160px;">Date / Time</th>
                  <th style="width: 110px;">Camera</th>
                  <th>File</th>
                  <th style="width: 90px;">Size</th>
                  <th class="text-end" style="width: 170px;">Actions</th>
                </tr>
              </thead>
              <tbody>
                {% for f in files %}
                <tr>
                  <td>{{ f.mtime }}</td>
                  <td>
                    <span class="badge bg-secondary badge-camera">Camera {{ f.camera_index }}</span>
                  </td>
                  <td class="small text-truncate" style="max-width: 260px;">
                    {{ f.rel_path }}
                  </td>
                  <td>{{ f.size_mb }} MB</td>
                  <td class="text-end">
                    <a href="{{ url_for('download_recording', file_id=f.id) }}" class="btn btn-sm btn-outline-primary">
                      Download
                    </a>
                    <form action="{{ url_for('delete_recording', file_id=f.id) }}" method="post" class="d-inline"
                          onsubmit="return confirm('Are you sure you want to delete this recording?');">
                      <button type="submit" class="btn btn-sm btn-outline-danger">Delete</button>
                    </form>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          {% else %}
          <div class="p-4 text-center text-muted">
            No recordings found in this folder.
          </div>
          {% endif %}
        </div>
      </div>

      <div class="mt-3 small text-muted">
        <div>• Click on a folder name to navigate into subdirectories.</div>
        <div>• On mobile devices, the table can be scrolled horizontally.</div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


def generate_frames():
    """MJPEG stream generator – uses the global latest_frames[0] in config."""
    global stream_active
    while stream_active:
        with config.camera_locks.get(0, threading.Lock()):
            frame = config.latest_frames.get(0)
            if frame is None:
                time.sleep(0.05)
                continue
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                time.sleep(0.05)
                continue
            frame_bytes = buffer.tobytes()

        yield (
            b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(0.05)


def run_stream_server() -> None:
    """Start the Flask live streaming server."""
    logger.info("Starting Flask live streaming server...")
    try:
        app.run(
            host="0.0.0.0",
            port=5001,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Flask server error: {e}")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (
            request.form.get("username") == USERNAME
            and request.form.get("password") == PASSWORD
        ):
            session["logged_in"] = True
            return redirect(url_for("live_stream"))
        return render_template_string(LOGIN_PAGE, error=True), 401
    return render_template_string(LOGIN_PAGE, error=False)


@app.route("/live")
def live_stream():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template_string(STREAM_PAGE, datetime=datetime)


@app.route("/video_feed")
def video_feed():
    if not session.get("logged_in"):
        return "Unauthorized", 401
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/stop_stream", methods=["POST"])
def stop_stream():
    global stream_active
    if not session.get("logged_in"):
        return "Unauthorized", 401
    with stream_lock:
        stream_active = False
    return "Stream stopped.", 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/capture_photo", methods=["POST"])
def capture_photo():
    if not session.get("logged_in"):
        return "Unauthorized", 401

    cam_index = 0
    lock = config.camera_locks.get(cam_index)
    if lock is None:
        return "Camera lock not found.", 500

    with lock:
        frame = config.latest_frames.get(cam_index)

    if frame is None:
        return "No frame has been captured from the camera yet.", 500

    snapshots_dir = os.path.join(config.VIDEO_SAVE_DIR, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    full_path = os.path.join(snapshots_dir, filename)

    cv2.imwrite(full_path, frame)

    return send_file(full_path, as_attachment=True)


@app.route("/recordings")
def recordings_page():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    root_dir = os.path.abspath(config.VIDEO_SAVE_DIR)

    rel_path = request.args.get("path", "").strip().strip("/\\")
    current_dir = os.path.abspath(os.path.join(root_dir, rel_path))

    if not current_dir.startswith(root_dir) or not os.path.isdir(current_dir):
        current_dir = root_dir
        rel_path = ""

    dirs_list = []
    files = []

    try:
        for entry in os.scandir(current_dir):
            if entry.is_dir():
                rel_sub = os.path.relpath(entry.path, root_dir)
                dirs_list.append(
                    {
                        "name": entry.name,
                        "rel_path": rel_sub.replace(os.sep, "/"),
                    }
                )
            elif entry.is_file() and entry.name.lower().endswith((".avi", ".mp4")):
                full_path = os.path.abspath(entry.path)
                stat = entry.stat()
                size_mb = stat.st_size / (1024 * 1024)
                mtime = datetime.fromtimestamp(stat.st_mtime)

                rel_to_video = os.path.relpath(full_path, root_dir).replace(os.sep, "/")
                parts = rel_to_video.split("/")
                try:
                    camera_index = int(parts[0])
                except (ValueError, IndexError):
                    camera_index = "-"

                encoded = base64.urlsafe_b64encode(full_path.encode("utf-8")).decode(
                    "utf-8"
                )

                files.append(
                    {
                        "id": encoded,
                        "rel_path": rel_to_video,
                        "size_mb": f"{size_mb:.2f}",
                        "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
                        "camera_index": camera_index,
                    }
                )
    except FileNotFoundError:
        current_dir = root_dir
        dirs_list = []
        files = []

    files.sort(key=lambda x: x["mtime"], reverse=True)

    breadcrumbs = []
    if rel_path:
        cumulative: list[str] = []
        for part in rel_path.split("/"):
            cumulative.append(part)
            breadcrumbs.append({"name": part, "path": "/".join(cumulative)})

    current_folder_name = breadcrumbs[-1]["name"] if breadcrumbs else "All Recordings"

    return render_template_string(
        RECORDINGS_PAGE,
        files=files,
        dirs=dirs_list,
        breadcrumbs=breadcrumbs,
        current_path=rel_path,
        current_folder_name=current_folder_name,
    )


@app.route("/recordings/download/<file_id>")
def download_recording(file_id: str):
    if not session.get("logged_in"):
        return "Unauthorized", 401

    try:
        full_path = base64.urlsafe_b64decode(file_id.encode("utf-8")).decode("utf-8")
    except Exception:
        abort(400)

    root_dir = os.path.abspath(config.VIDEO_SAVE_DIR)
    full_path = os.path.abspath(full_path)

    if not full_path.startswith(root_dir) or not os.path.exists(full_path):
        abort(404)

    return send_file(full_path, as_attachment=True)


@app.route("/recordings/delete/<file_id>", methods=["POST"])
def delete_recording(file_id: str):
    if not session.get("logged_in"):
        return "Unauthorized", 401

    try:
        full_path = base64.urlsafe_b64decode(file_id.encode("utf-8")).decode("utf-8")
    except Exception:
        abort(400)

    root_dir = os.path.abspath(config.VIDEO_SAVE_DIR)
    full_path = os.path.abspath(full_path)

    if not full_path.startswith(root_dir) or not os.path.exists(full_path):
        abort(404)

    try:
        os.remove(full_path)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Recording delete error: {e}")
        return "An error occurred while deleting the recording.", 500

    return redirect(url_for("recordings_page"))
