# Tools

Python tools that read the tap's USB log, render the piano's display on a
laptop, and map the glass's segments. They need Python 3 and `pyserial`; the
windowed ones also need tkinter.

    pip install pyserial
    python3 tools/pr53_display.py            # auto-detects the serial port
    python3 tools/pr53_display.py --port /dev/ttyACM0

## Which tool for what

| Tool | What it does | Reads |
|---|---|---|
| `pr53_display.py` | Live mock of the display in a window: text lines, persistent voice/rhythm panel, raw DDRAM. The one you'll use most. | Live stream |
| `pr53_record.py` | Free-running recorder. Saves the stream to `session_HHMMSS.log`, with timestamped `# NOTE` lines you type while recording. Use it for menus that time out. | Live stream |
| `pr53_session.py` | Offline analyzer for recorder logs: `--states` groups frames by state, `--diff` compares them, `--to-mapping` writes labelled bit-diffs. | Recorder log |
| `pr53_campaign.py` | Guided mapping: walks you through a scripted list of panel actions and saves each CGRAM bit-diff to `mapping.csv`. | Live stream |
| `pr53_decode.py` | Live tempo and numeric readout decoder. | Live stream |
| `pr53_map.py` | Two-snapshot mapper: capture, press a button, capture again, label the changed bits, save to `mapping.csv`. | v13 CSV |
| `pr53_tempo.py` | Learns the tempo digits empirically from `mapping.csv`. | v13 CSV |
| `pr53_analyze.py` | Offline analyzer for v13 CSV captures (`--states`, `--diff`, `--raw`). | v13 CSV |
| `pr53_campaign_report.py` | Replays a campaign log (`pr53_campaign.py --raw-log`): text and changed segment bits per step, and a table of every bit that varies across a run. | Campaign log |

The `panel_*` campaigns in `pr53_campaign.py` cover every front-panel control,
section by section (see `docs/front-panel.md`); `chord_roots_all12` and
`chord_types_recognizer` cover the chord symbols.

"Live stream" is the event log the tap prints over USB (format in
`firmware/tap/README.md`); the current v16 tap firmware produces it. The
**v13 CSV** tools expect the older multiplex-snapshot format (sample in
`captures/capture.csv`); to use them live, flash a v13 build or update the
tool.

## The persistent-state heuristic

`pr53_display.py` keeps the last voice and rhythm names on screen when the
piano briefly shows a menu label. That classification is the only
Technics-specific logic; strip it out to use the tool on another device.
