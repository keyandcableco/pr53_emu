# Archive

Earlier hardware plans, kept for reference. None of these is the current
build; that's `../carrier/`.

| File | What it was |
|---|---|
| `PERFBOARD_MAP_ZERO.md` | The hand-wired perfboard build the carrier replaced: RP2350-Zero tap, Pico 2 display. Same pin map as the carrier. |
| `PERFBOARD_MAP.md`, `FULL_BOARD_MAP.md` | An earlier perfboard layout with a Pico 2 as the tap (capture on GP4-11, link on GP12). |
| `KICAD_NETLIST.md`, `pr53_board_pins.h` | A plan for a single-chip RP2354B board. Its one-way 74LVC245 input would break the tap's read responses; rework that before building it. |
| `kicad/` | The first netlist (SKiDL) and placement scaffold for a module carrier, before the generated carrier in `../carrier/`. |
