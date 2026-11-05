# CompuTax Client File Downloader

A local web app that copies a client's `ITRV_<id>.pdf` and `Computation_<id>_<year>_<n>.pdf` files out of a CompuTax data folder, for the years you pick, into `<destination>/<ID>/<year>/`. It runs on Windows and macOS (Apple Silicon) and needs nothing installed.

The design is in [docs/plan.html](docs/plan.html).

## Using it

1. Download the file for your computer from the [Releases](../../releases) page:
   - Windows: `computax-downloader-windows.exe`
   - Mac (M1 or later): `computax-downloader-macos-arm64.zip`, then double-click the zip to extract it.
2. Run it:
   - Windows: double-click the `.exe`. If SmartScreen warns about an unknown app, choose **More info → Run anyway**.
   - Mac: right-click the file and choose **Open**, then **Open** again. This is needed the first time only, because the app is not signed by Apple.
3. A small terminal window opens and the app opens in your browser. Keep the terminal window open while you use the app; closing it quits the app.
4. The first time, choose your `CompuTax` folder (the one containing `2019`, `2020`, …). The app remembers it.
5. Search for a client by ID or name, pick the years, choose where to save, and click **Copy files**.

The app only listens on `127.0.0.1`, never changes anything inside the CompuTax folder, and saves nothing except the CompuTax folder location (in `%APPDATA%\computax-downloader\settings.json` on Windows, or `~/Library/Application Support/computax-downloader/settings.json` on macOS).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run computax-client-file-download            # start the app and open the browser
uv run computax-client-file-download --root /path/to/CompuTax --no-browser --port 8765
uv run pytest                                   # Python tests
node --test tests/                              # fuzzy-search tests
```

Build a one-file executable for the current OS:

```sh
uv run pyinstaller --noconfirm packaging/computax-downloader.spec
```

## Releasing

Push a version tag. GitHub Actions builds the Windows and macOS executables and attaches them to a new release:

```sh
git tag v0.1.0
git push origin v0.1.0
```
