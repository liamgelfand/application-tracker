# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a tray-launched AppTracker.exe.

Build from the repo root:
    make dist
  or
    pyinstaller --noconfirm backend/apptracker.spec
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH is the directory holding this file, but PyInstaller has reported it
# differently across versions — locate the backend directory by its contents.
_spec_dir = Path(SPECPATH).resolve()
if (_spec_dir / "launcher.py").exists():
    BACKEND = _spec_dir
elif (_spec_dir / "backend" / "launcher.py").exists():
    BACKEND = _spec_dir / "backend"
else:
    raise SystemExit(f"Cannot locate backend/launcher.py relative to {_spec_dir}")

PROJECT = BACKEND.parent
FRONTEND_DIST = PROJECT / "frontend" / "dist"
ICON = BACKEND / "assets" / "icon.ico"

if not FRONTEND_DIST.is_dir():
    raise SystemExit(
        "frontend/dist is missing — run `npm run build` in frontend/ first, "
        "otherwise the packaged app has no UI to serve."
    )

datas = [(str(FRONTEND_DIST), "frontend/dist")]
if ICON.exists():
    datas.append((str(ICON), "assets"))

# litellm reads model_prices_and_context_window_backup.json at import. Without
# it the packaged app re-downloads the pricing map from GitHub on every call,
# which turns a network hiccup into a stalled inbox sync.
datas += collect_data_files("litellm")

# tiktoken resolves its encodings through importlib at runtime, so PyInstaller
# cannot see tiktoken_ext.openai_public or tiktoken.load by static analysis.
# Missing them makes `import litellm` fail in the packaged app only.
tiktoken_imports = (
    collect_submodules("tiktoken")
    + collect_submodules("tiktoken_ext")
    + ["tiktoken_ext.openai_public", "tiktoken.load", "tiktoken.registry"]
)

a = Analysis(
    [str(BACKEND / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "app.main",
        "app.api.applications",
        "app.api.analytics",
        "app.api.backup",
        "app.api.emails",
        "app.api.parse",
        "app.api.settings",
        "app.api.suggestions",
        "app.api.updates",
        "app.services.updater",
        *tiktoken_imports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AppTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)
