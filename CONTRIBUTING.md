# Contributing

Thanks for helping! Bug reports, ideas and pull requests are welcome.

## Development setup

- **Windows (receiver):** `setup_windows.bat`, then run the window app with `.venv\Scripts\python.exe pc_app.py`.
- **macOS (sender):** `bash setup_mac.sh`, then run the menu bar app with `.venv/bin/python mac_app.py`.
- **No Mac at hand?** Run `python mac_sender.py --test-pattern` on any machine and connect to it.

Before opening a pull request, run the smoke test (it streams a test pattern over loopback at 30 and 60 fps):

```bash
python tests/smoke_test.py
```

## Code layout

| Path | What it is |
|---|---|
| `macbookcam/protocol.py` | wire protocol, discovery |
| `macbookcam/server.py` | Mac side: camera sources, TCP server |
| `macbookcam/avf_capture.py` | native AVFoundation capture on macOS (frame rate selection) |
| `macbookcam/client.py` | PC side: receiver, jitter buffer, virtual camera output |
| `macbookcam/i18n.py` | English and Russian UI strings |
| `pc_app.py`, `mac_app.py` | Windows window app, macOS menu bar app |
| `mac_sender.py`, `pc_receiver.py` | console versions |

## Translations

All UI strings live in `macbookcam/i18n.py`. To add a language, add it to `LANGUAGES` and copy the `"en"` block in `STRINGS`; the smoke test checks that every language has the same keys.

## Releases

Pushing a `v*` tag builds the Windows `.exe` and macOS `.dmg` files (Apple Silicon and Intel) in GitHub Actions and publishes a release.
