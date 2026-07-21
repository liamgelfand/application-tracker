"""
Job Application Tracker — system tray launcher.

Usage:
    python launcher.py            # default port 8000
    python launcher.py --port 9000

What it does:
  1. Builds the frontend if frontend/dist is missing.
  2. Starts the FastAPI/uvicorn server in a background thread.
  3. Opens the app in your default browser.
  4. Shows a tray icon with Open / Start on Login / Quit options.
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import platform
import subprocess
import sys
import threading
import time
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

def _build_frontend() -> None:
    """Run `npm run build` inside frontend/ if dist is absent."""
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


def _make_tray_icon() -> "Image.Image":
    """Draw a simple 64×64 icon in the brand indigo colour."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(99, 102, 241, 255))
    # Briefcase-ish shape
    draw.rectangle([18, 28, 46, 46], fill="white")
    draw.rectangle([24, 24, 40, 30], outline="white", width=2)
    return img


def _is_startup_enabled() -> bool:
    system = platform.system()
    if system == "Windows":
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        return (startup / "AppTracker.bat").exists()
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
        # Prefer pythonw.exe — runs without a console window flash.
        pythonw = Path(python).parent / "pythonw.exe"
        exe = str(pythonw) if pythonw.exists() else python
        work_dir = str(HERE)
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        bat = startup / "AppTracker.bat"
        # timeout gives Windows a few seconds to fully boot before the app starts.
        bat.write_text(
            f'@echo off\n'
            f'timeout /t 8 /nobreak >nul\n'
            f'cd /d "{work_dir}"\n'
            f'start "" "{exe}" "{script}" --port {port}\n',
            encoding="utf-8",
        )
        logger.info("Start-on-login enabled (Windows startup folder).")

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
        bat = (
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft/Windows/Start Menu/Programs/Startup/AppTracker.bat"
        )
        bat.unlink(missing_ok=True)
    elif system == "Darwin":
        plist = Path.home() / "Library/LaunchAgents/com.apptracker.launcher.plist"
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        plist.unlink(missing_ok=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "apptracker"], check=False)
        (Path.home() / ".config/systemd/user/apptracker.service").unlink(missing_ok=True)
    logger.info("Start-on-login disabled.")


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------

class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True, name="uvicorn")
        self.port = port
        self._server: uvicorn.Server | None = None

    def run(self) -> None:
        # Ensure the backend package is importable when launched from anywhere.
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))

        config = uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=self.port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        self._server.run()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Job Application Tracker launcher")
    parser.add_argument("--port", type=int, default=8000, help="Port for the backend server")
    parser.add_argument("--no-tray", action="store_true", help="Run without a tray icon (headless)")
    args = parser.parse_args()

    port = args.port
    url = f"http://localhost:{port}"

    _build_frontend()

    server = _ServerThread(port)
    server.start()

    # Wait up to 5 s for the server to be ready before opening the browser.
    for _ in range(50):
        time.sleep(0.1)
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except Exception:
            continue

    webbrowser.open(url)

    if not _TRAY_AVAILABLE or args.no_tray:
        logger.info("App running at %s  (Ctrl+C to quit)", url)
        try:
            server.join()
        except KeyboardInterrupt:
            server.stop()
        return

    # ---- tray icon ----
    icon_image = _make_tray_icon()

    def on_open(_icon, _item) -> None:
        webbrowser.open(url)

    def on_toggle_startup(_icon, _item) -> None:
        if _is_startup_enabled():
            _disable_startup()
        else:
            _enable_startup(port)

    def on_quit(_icon, _item) -> None:
        server.stop()
        _icon.stop()

    def startup_label(_item) -> str:
        return "✓ Start on Login" if _is_startup_enabled() else "Start on Login"

    menu = pystray.Menu(
        pystray.MenuItem("Open AppTracker", on_open, default=True),
        pystray.MenuItem(startup_label, on_toggle_startup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("AppTracker", icon_image, "AppTracker", menu)
    icon.run()


if __name__ == "__main__":
    main()
