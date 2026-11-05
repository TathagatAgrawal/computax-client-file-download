# PyInstaller spec for ITR Fetch. Runs without a terminal window.
#   Windows: one windowless "ITR Fetch.exe".
#   macOS:   "ITR Fetch.app", a background app (no Dock icon) that quits when its browser tab closes.
# Build with: uv run pyinstaller --noconfirm packaging/itr-fetch.spec
import os
import sys
import tomllib

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "src", "computax_client_file_download")
ICONS = os.path.join(SPECPATH, "icon")
APP_NAME = "ITR Fetch"
with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
    VERSION = tomllib.load(f)["project"]["version"]

# macOS uses osascript for the folder dialog, so Tk is only bundled on Windows.
excludes = ["tkinter", "_tkinter"] if sys.platform == "darwin" else []

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[(os.path.join(PKG, "static"), "computax_client_file_download/static")],
    excludes=excludes,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name=APP_NAME,
        console=False,
        upx=False,
        icon=os.path.join(ICONS, "icon.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=os.path.join(ICONS, "icon.icns"),
        bundle_identifier="io.github.tathagatagrawal.itr-fetch",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name=APP_NAME,
        console=False,
        upx=False,
        icon=os.path.join(ICONS, "icon.ico"),
    )
