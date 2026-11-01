# Captures

Bus recordings from the SX-PR53, made with `tools/pr53_record.py` in July and
August 2026. Each `session_*.log` is the tap's USB event log plus the
`# NOTE` lines typed while recording (which button was pressed, what the
display showed).

- `startup_2026-10-31.log` is the tap's raw USB log of a full piano
  start-up on the carrier board: the LCD initialisation, the CGRAM loads, then
  "ALL INITIAL" and "ConcertGrand". It has no `# NOTE` lines.
- `lcd_test_mode_2026-10-31.log` is the service manual's LCD check, entered by
  holding G4 + G5 while switching on. The first try only set up the display
  and went quiet; the second lit every CGRAM pixel and filled both text lines
  with full blocks, then, after PIANO & E PIANO was pressed, scrolled the
  character set one code every ~3 s (reaching 0xAD). Sound buttons flashed
  "RIGHT1" plus the voice name and tempo "120"; 8 & 16 BEAT flashed a rhythm
  name. Raw tap log, no `# NOTE` lines.
- `campaign_2026-10-31.log` is the front-panel decode: the guided campaigns
  from `tools/pr53_campaign.py` (chord roots, panel sections, menus) with
  their `# NOTE` capture/saved lines, then free play. The display firmware's
  host tests replay it (`make -f host.mk test`). Recorded with tap v16.
- `menus_2026-10-31.log` is the menu_page_arrows campaign walked through the
  Sound menu (P7 down to P1, then EXIT; the second run is the complete one).
  `firmware/display/src/test_menus.c` replays it.
- `item_tens_2026-10-31.log` walks the GUITAR group's 20 voices up, partway
  down and up again, for the item number's tens digit (C5 c4).
- `restart_tap_v17_2026-10-31.log` and `restart_tap_v18_2026-10-31.log` are
  piano restarts recorded after flashing tap v17 and v18. With v17 the piano
  hit a 3.8 ms busy timeout before about half its data writes at addresses
  with bit 3 set and left every text line short ("Techni", "ConcertGran",
  line 2 untouched); with v18 it hit none and went from "Technics / SX-PR53"
  to "ConcertGrand / 8 Beat" in 3 s. See `firmware/tap/README.md`.
- `session_092906.log` is the ground-truth frame the display firmware's host
  test runs against (`make -f host.mk test`, expects Part 8 = 127).
- `capture.csv` is a sample in the older v13 multiplex-snapshot format, for
  `pr53_analyze.py`, `pr53_map.py` and `pr53_tempo.py`.
- `out.txt` is a saved `pr53_session.py` report.

Analyze one offline:

    python3 tools/pr53_session.py captures/session_071830.log --states
