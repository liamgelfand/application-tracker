"""
Job Application Tracker — system tray launcher.

Usage:
    python launcher.py            # default port 8000
    python launcher.py --port 9000

What it does:
  1. Builds the frontend if frontend/dist is missing.
  2. Starts the FastAPI/uvicorn server in a background thread.
  3. Shows a tray icon with Open / Start on Login / Quit options.
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import uvicorn

logger = logging.getLogger("tracker.launcher")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent          # backend/
ROOT = HERE.parent                    # project root
FRONTEND_DIST = ROOT / "frontend" / "dist"
FRONTEND_DIR = ROOT / "frontend"

# Make the backend package importable before anything below needs app.config.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _data_dir() -> Path:
    """Per-user data directory, falling back to the repo if config won't load."""
    try:
        from app.config import settings as app_settings

        return app_settings.data_path
    except Exception:  # noqa: BLE001 - logging must work even if config fails
        fallback = HERE / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


LOG_DIR = _data_dir()
LOG_FILE = LOG_DIR / "launcher.log"
FIRST_RUN_MARKER = LOG_DIR / ".welcomed"

# Windows Startup entries
_WIN_STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
_WIN_STARTUP_BAT = _WIN_STARTUP / "AppTracker.bat"
_WIN_STARTUP_VBS = _WIN_STARTUP / "AppTracker.vbs"


# ---------------------------------------------------------------------------
# Optional deps — pystray / Pillow are only needed for the tray icon.
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw
    import pystray
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Log to console when available, and always to a file (pythonw has no console)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Avoid duplicate StreamHandlers if main() is re-entered.
    if sys.stderr is not None and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    ):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def _build_frontend() -> None:
    """Run `npm run build` inside frontend/ if dist is absent."""
    # A packaged build ships the UI inside the bundle and has no npm or source
    # tree to build from; app.main serves it out of sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return
    if FRONTEND_DIST.is_dir():
        return
    logger.info("frontend/dist not found — building now (this takes ~10s)…")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Frontend build failed:\n%s", result.stderr)
        sys.exit(1)
    logger.info("Frontend built successfully.")


def _icon_path() -> Path | None:
    """Bundled icon, whether running from source or a PyInstaller build."""
    candidates = [HERE / "assets" / "icon.ico"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS) / "assets" / "icon.ico")
    return next((p for p in candidates if p.exists()), None)


def _make_tray_icon() -> "Image.Image":
    """The shared app mark, or a plain fallback if the asset is missing."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    path = _icon_path()
    if path is not None:
        try:
            return Image.open(path).convert("RGBA")
        except Exception:  # noqa: BLE001 - the tray must still appear
            logger.warning("Could not load %s; using fallback icon.", path)

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, 62, 62], radius=14, fill=(26, 25, 23, 255))
    for left, top, color in ((14, 37, (233, 229, 222, 255)),
                             (29, 26, (233, 229, 222, 255)),
                             (44, 14, (200, 115, 74, 255))):
        draw.rounded_rectangle([left, top, left + 8, 50], radius=3, fill=color)
    return img


def _health_ok(url: str, timeout_s: float = 2.0) -> bool:
    """True when something on this port answers as AppTracker."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8")).get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def _port_is_taken(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_health(url: str, timeout_s: float = 15.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _is_startup_enabled() -> bool:
    system = platform.system()
    if system == "Windows":
        return _WIN_STARTUP_VBS.exists() or _WIN_STARTUP_BAT.exists()
    if system == "Darwin":
        plist = Path.home() / "Library/LaunchAgents/com.apptracker.launcher.plist"
        return plist.exists()
    # Linux — systemd user service
    service = Path.home() / ".config/systemd/user/apptracker.service"
    return service.exists()


def _enable_startup(port: int) -> None:
    system = platform.system()
    python = sys.executable
    script = str(HERE / "launcher.py")

    if system == "Windows":
        # Prefer pythonw.exe — no console window.
        pythonw = Path(python).parent / "pythonw.exe"
        exe = str(pythonw) if pythonw.exists() else python
        work_dir = str(HERE)

        # VBScript launches hidden (window style 0) so no cmd flash on login.
        # Delay a few seconds so OneDrive / network paths are ready.
        vbs = (
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{work_dir}"\r\n'
            "WScript.Sleep 8000\r\n"
            f'sh.Run """{exe}"" ""{script}"" --port {port}", 0, False\r\n'
        )
        _WIN_STARTUP.mkdir(parents=True, exist_ok=True)
        _WIN_STARTUP_VBS.write_text(vbs, encoding="utf-8")
        # Remove the old .bat that flashed a console window.
        _WIN_STARTUP_BAT.unlink(missing_ok=True)
        logger.info("Start-on-login enabled (Windows Startup VBScript, silent).")

    elif system == "Darwin":
        agents = Path.home() / "Library/LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        plist = agents / "com.apptracker.launcher.plist"
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.apptracker.launcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>{script}</string>
    <string>--port</string><string>{port}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>
""",
            encoding="utf-8",
        )
        subprocess.run(["launchctl", "load", str(plist)], check=False)
        logger.info("Start-on-login enabled (macOS LaunchAgent).")

    else:
        service_dir = Path.home() / ".config/systemd/user"
        service_dir.mkdir(parents=True, exist_ok=True)
        service = service_dir / "apptracker.service"
        service.write_text(
            f"""[Unit]
Description=Job Application Tracker

[Service]
ExecStart={python} {script} --port {port}
Restart=on-failure

[Install]
WantedBy=default.target
""",
            encoding="utf-8",
        )
        subprocess.run(["systemctl", "--user", "enable", "apptracker"], check=False)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        logger.info("Start-on-login enabled (systemd user service).")


def _disable_startup() -> None:
    system = platform.system()
    if system == "Windows":
        _WIN_STARTUP_BAT.unlink(missing_ok=True)
        _WIN_STARTUP_VBS.unlink(missing_ok=True)
    elif system == "Darwin":
        plist = Path.home() / "Library/LaunchAgents/com.apptracker.launcher.plist"
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        plist.unlink(missing_ok=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "apptracker"], check=False)
        (Path.home() / ".config/systemd/user/apptracker.service").unlink(missing_ok=True)
    logger.info("Start-on-login disabled.")


def _migrate_windows_startup_if_needed(port: int) -> None:
    """Replace legacy AppTracker.bat (console flash) with silent .vbs."""
    if platform.system() != "Windows":
        return
    if _WIN_STARTUP_BAT.exists() and not _WIN_STARTUP_VBS.exists():
        logger.info("Migrating Start-on-Login from .bat to silent .vbs…")
        _enable_startup(port)


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------

class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True, name="uvicorn")
        self.port = port
        self._server: uvicorn.Server | None = None
        self.failed = False
        self.error: str | None = None

    def run(self) -> None:
        try:
            # Ensure the backend package is importable when launched from anywhere.
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))

            # Always run with a known working directory (Startup may start elsewhere).
            os.chdir(HERE)

            # DATA_DIR is intentionally left alone: app.config resolves it to a
            # per-user directory (%LOCALAPPDATA%\AppTracker) and migrates an
            # older repo-local database on first run.

            # pythonw has sys.stdout=None; uvicorn's default ColorFormatter
            # crashes on stdout.isatty() unless use_colors is forced off.
            config = uvicorn.Config(
                "app.main:app",
                host="127.0.0.1",
                port=self.port,
                log_level="info",
                use_colors=False,
            )
            self._server = uvicorn.Server(config)
            self._server.run()
        except Exception:
            self.failed = True
            self.error = traceback.format_exc()
            logger.exception("Uvicorn server crashed")

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _configure_logging()

    parser = argparse.ArgumentParser(description="Job Application Tracker launcher")
    parser.add_argument("--port", type=int, default=8000, help="Port for the backend server")
    parser.add_argument("--no-tray", action="store_true", help="Run without a tray icon (headless)")
    args = parser.parse_args()

    port = args.port
    url = f"http://127.0.0.1:{port}"

    # Starting twice used to die on "address already in use" and leave a tray
    # icon that reported a server it didn't own. Hand off to the live one.
    if _port_is_taken(port):
        if _health_ok(url):
            logger.info("AppTracker is already running at %s — opening it.", url)
            webbrowser.open(url)
        else:
            logger.error(
                "Port %s is in use by another program. Start AppTracker on a "
                "different port with --port, e.g. --port 8010.",
                port,
            )
        return

    _migrate_windows_startup_if_needed(port)
    _build_frontend()

    server = _ServerThread(port)
    server.start()

    healthy = _wait_for_health(url, timeout_s=20.0)
    if not healthy:
        logger.error(
            "Server did not become healthy at %s. See log: %s",
            url,
            LOG_FILE,
        )
        if server.error:
            logger.error("Server thread error:\n%s", server.error)
    elif not FIRST_RUN_MARKER.exists():
        # Subsequent launches stay silent in the tray; the first one needs to
        # show the user something happened.
        try:
            FIRST_RUN_MARKER.write_text("opened\n", encoding="utf-8")
        except OSError:
            pass
        webbrowser.open(url)

    if not _TRAY_AVAILABLE or args.no_tray:
        if healthy:
            logger.info("App running at %s  (Ctrl+C to quit)", url)
        try:
            server.join()
        except KeyboardInterrupt:
            server.stop()
        return

    # ---- tray icon ----
    icon_image = _make_tray_icon()

    def on_open(_icon, _item) -> None:
        if _wait_for_health(url, timeout_s=3.0):
            webbrowser.open(url)
        else:
            logger.error(
                "Cannot open app — server not responding at %s. See %s",
                url,
                LOG_FILE,
            )

    def on_toggle_startup(_icon, _item) -> None:
        if _is_startup_enabled():
            _disable_startup()
        else:
            _enable_startup(port)

    def on_quit(_icon, _item) -> None:
        server.stop()
        _icon.stop()

    def on_health(_icon, _item) -> None:
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            llm = data.get("llm") or {}
            email = data.get("email") or {}
            sync = data.get("sync") or {}
            if llm.get("configured"):
                llm_line = f"LLM: {llm.get('name')} ({llm.get('provider')}/{llm.get('model')})"
            else:
                llm_line = "LLM: not configured"
            email_line = (
                f"Email: {email.get('active', 0)}/{email.get('accounts', 0)} active"
            )
            if email.get("last_synced_at"):
                email_line += f" · last sync {email['last_synced_at']}"
            sync_line = (
                f"Sync: {sync.get('message') or sync.get('phase') or 'idle'}"
            )
            msg = f"{llm_line}\n{email_line}\n{sync_line}"
            title = "AppTracker — healthy"
            try:
                _icon.notify(msg, title)
            except Exception:
                logger.info("Health check:\n%s", msg)
        except Exception as exc:
            err = f"Server not responding at {url}\n{exc}"
            try:
                _icon.notify(err, "AppTracker — unhealthy")
            except Exception:
                logger.error(err)

    def startup_label(_item) -> str:
        return "✓ Start on Login" if _is_startup_enabled() else "Start on Login"

    menu = pystray.Menu(
        pystray.MenuItem("Open AppTracker", on_open, default=True),
        pystray.MenuItem("Health Check", on_health),
        pystray.MenuItem(startup_label, on_toggle_startup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("AppTracker", icon_image, "AppTracker", menu)
    logger.info("Tray ready. Server healthy=%s url=%s", healthy, url)
    icon.run()


if __name__ == "__main__":
    main()
