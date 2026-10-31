# Captures

Bus recordings from the SX-PR53, made with `tools/pr53_record.py` in July and
August 2026. Each `session_*.log` is the tap's USB event log plus the
`# NOTE` lines typed while recording (which button was pressed, what the
display showed).

- `startup_2026-10-31.log` is the tap's raw USB log of a full piano
  start-up on the carrier board: the LCD initialisation, the CGRAM loads, then
  "ALL INITIAL" and "ConcertGrand". It has no `# NOTE` lines.
- `session_092906.log` is the ground-truth frame the display firmware's host
  test runs against (`make -f host.mk test`, expects Part 8 = 127).
- `capture.csv` is a sample in the older v13 multiplex-snapshot format, for
  `pr53_analyze.py`, `pr53_map.py` and `pr53_tempo.py`.
- `out.txt` is a saved `pr53_session.py` report.

Analyze one offline:

    python3 tools/pr53_session.py captures/session_071830.log --states
