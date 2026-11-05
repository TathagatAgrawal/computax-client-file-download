# PyInstaller spec: one-file console build of the CompuTax downloader.
# Build with: uv run pyinstaller packaging/computax-downloader.spec
# Set BINARY_NAME to choose the output file name (default: computax-downloader).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "src", "computax_client_file_download")

# macOS uses osascript for the folder dialog, so Tk is only bundled on Windows.
excludes = ["tkinter", "_tkinter"] if sys.platform == "darwin" else []

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[(os.path.join(PKG, "static"), "computax_client_file_download/static")],
    excludes=excludes,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name=os.environ.get("BINARY_NAME", "computax-downloader"),
    console=True,
    upx=False,
)
