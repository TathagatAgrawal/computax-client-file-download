# ITR Fetch

ITR Fetch copies a client's `ITRV_<id>.pdf` and `Computation_<id>_<year>_<n>.pdf` files out of a CompuTax data folder, for the years you pick, into one folder per client: `<destination>/<ID>/`. Files whose names don't include the year get it appended, for example `ITRV_109B_2021.pdf`. Files already in the destination are never overwritten. It runs on Windows and macOS (Apple Silicon) and needs nothing installed.

The design is in [docs/plan.html](docs/plan.html).

## Using it

1. Download the file for your computer from the [Releases](../../releases) page:
   - Windows: `ITR-Fetch-Windows.exe`
   - Mac (M1 or later): `ITR-Fetch-macOS.zip`. Double-click it to get **ITR Fetch.app**, and drag that into Applications.
2. Open it:
   - Windows: double-click the `.exe`. If SmartScreen warns about an unknown app, choose **More info → Run anyway**.
   - Mac: the first time, macOS blocks it because it isn't signed by Apple. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to ITR Fetch. After that it opens normally.
3. ITR Fetch opens in your browser. There is no other window: it runs in the background and quits on its own a few seconds after you close its browser tab. Opening it again while it's running just opens another tab.
4. The first time, choose your `CompuTax` folder (the one containing `2019`, `2020`, …). ITR Fetch remembers it.
5. Search for a client by ID or name, pick the years, choose where to save, and click **Copy files**.

ITR Fetch only listens on `127.0.0.1` and never changes anything inside the CompuTax folder. The only thing it saves is the CompuTax folder location, in `%APPDATA%\computax-downloader\settings.json` on Windows or `~/Library/Application Support/computax-downloader/settings.json` on macOS. If it fails to start, the reason is written to `error.log` in the same folder.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run itr-fetch                                   # start and open the browser; quits when the tab closes
uv run itr-fetch --root /path/to/CompuTax --no-browser --port 8765   # keeps running until Ctrl+C
uv run pytest                                      # Python tests
node --test tests/fuzzy.test.mjs                   # fuzzy-search tests
```

Build the app for the current OS (`dist/ITR Fetch.exe` on Windows, `dist/ITR Fetch.app` on macOS):

```sh
uv run pyinstaller --noconfirm packaging/itr-fetch.spec
```

The icon source is `packaging/icon/icon.svg`. After changing it, regenerate the `.icns`, `.ico` and favicon on a Mac with Chrome installed: `python3 packaging/icon/build_icons.py`.

## Releasing

Push a version tag. GitHub Actions builds the Windows and macOS apps and attaches them to a new release:

```sh
git tag v0.1.2
git push origin v0.1.2
```
