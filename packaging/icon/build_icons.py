"""Render icon.svg into the PNG, .icns (macOS) and .ico (Windows) app icons.

Needs Google Chrome (headless rendering) and, for .icns, macOS's sips and
iconutil. Run from anywhere: ``python packaging/icon/build_icons.py``.
"""

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_png(svg: Path, out: Path, work: Path) -> None:
    """Render the SVG at 1024x1024 with a transparent background using headless Chrome."""
    html = work / "icon.html"
    html.write_text(
        f'<html><body style="margin:0;background:transparent">'
        f'<img src="{svg.as_uri()}" width="1024" height="1024"></body></html>'
    )
    subprocess.run(
        [CHROME, "--headless=new", f"--user-data-dir={work / 'profile'}", f"--screenshot={out}",
         "--window-size=1024,1024", "--default-background-color=00000000", "--hide-scrollbars", html.as_uri()],
        check=True,
        capture_output=True,
    )


def resize(src: Path, size: int, out: Path) -> None:
    """Resize a PNG with sips."""
    subprocess.run(["sips", "-z", str(size), str(size), str(src), "--out", str(out)], check=True, capture_output=True)


def build_icns(master: Path, out: Path, work: Path) -> None:
    """Build a macOS .icns from the master PNG via an iconset."""
    iconset = work / "icon.iconset"
    iconset.mkdir()
    for size in ICNS_SIZES[:-1]:
        resize(master, size, iconset / f"icon_{size}x{size}.png")
        resize(master, size * 2, iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)


def build_ico(master: Path, out: Path, work: Path) -> None:
    """Build a Windows .ico that embeds one PNG per size."""
    images = []
    for size in ICO_SIZES:
        png = work / f"ico_{size}.png"
        resize(master, size, png)
        images.append((size, png.read_bytes()))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    out.write_bytes(header + entries + blobs)


def main() -> None:
    """Regenerate icon.png, icon.icns, icon.ico and the web favicon."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        master = HERE / "icon.png"
        render_png(HERE / "icon.svg", master, work)
        build_icns(master, HERE / "icon.icns", work)
        build_ico(master, HERE / "icon.ico", work)
    static = HERE.parent.parent / "src" / "computax_client_file_download" / "static"
    shutil.copy(HERE / "icon.svg", static / "favicon.svg")
    print("Wrote icon.png, icon.icns, icon.ico and static/favicon.svg", file=sys.stderr)


if __name__ == "__main__":
    main()
