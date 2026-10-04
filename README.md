# pr53_emu

Bus-emulating replacement for the failed LCD in a Technics SX-PR53 digital piano. RP2350 firmware intercepts the HD44780 4-bit bus between the piano's CPU and the (dead) chip-on-glass display, mirrors every write, responds to reads correctly, and streams the display state over USB. A Python tkinter app renders the piano's live text output on a laptop screen.

The technique generalizes to most HD44780-compatible LCDs. See [the writeup](https://keyandcable.com/blog/reviving-the-technics-sx-pr53.html) for the story and the reasoning behind the design.

---

## What's in here

### Firmware — `pr53_emu.c`

RP2350 firmware (Pico SDK). Captures every write pulse from the piano over PIO0, tracks the HD44780 Access Counter, responds to every read pulse over PIO1 with the correct value so the CPU doesn't stall waiting for BF=0. Streams a chronological event log over USB serial:

```
t=00123456 W CMD 0x80 [SET_DDRAM 0x00]
t=00124200 W DAT 0x43 'C'
t=00124215 W DAT 0x6F 'o'
```

Current version: **v15**. Skips reads at the PIO layer (they aren't needed for display state and doubled the event rate), 2048-slot ring buffer, drop reporting on the alive pings.

### Real-time display — `tools/pr53_display.py`

Live mock 16x2 LCD in tkinter. Reads the firmware's event log over USB, runs an HD44780 state machine in Python that mirrors DDRAM and CGRAM, renders a 16x2 grid using an embedded 5x8 pixel font. Tracks the display-on bit so bulk updates during off-cycles don't churn visibly on screen. Tracks "persistent" line 1 and line 2 content so brief menu labels don't wipe the running voice/rhythm display.

This is what you'll use most of the time.

### Segment mapping — `tools/pr53_map.py`

Interactive tool for anyone who wants to fully reproduce the original glass on a graphic display. Live LCD mock plus **Snapshot A / Snapshot B** buttons — capture piano state, press one button, capture again, diff auto-computes to show only the CGRAM bits that changed. Type a label, save to `mapping.csv`. Iterate for each button/indicator/segment. Notes: this tool expects the older v13 CSV snapshot format; if you're on v15 firmware you'll need to flash the v13 build for mapping sessions (or update the tool — pull requests welcome).

### Tempo learner — `tools/pr53_tempo.py`

The tempo digits on the Technics aren't standard 7-segment shapes, so instead of decoding them mathematically, this remembers "when these bits are set, tempo=120" empirically. Reads `mapping.csv` to find the tempo bits, then teach it values as you press TEMPO UP/DOWN. Persists in `tempo_learned.csv`. Same v13-format caveat as `pr53_map.py`.

### Offline analyzer — `tools/pr53_analyze.py`

For diffing saved captures offline. `--states` groups snapshots by unique text state, `--diff A B` compares CGRAM unions between two states with a strict/loose view. Same v13-format caveat.

---

## Hardware

- **Raspberry Pi Pico 2** (RP2350). Any RP2350 board works; PIO usage is generic.
- **10kΩ resistor** from DB7 to ground. Not optional — see below.
- **Wire.** Ribbon-friendly if you're tapping in without unsoldering the original LCD connector.

### Wiring

| Piano signal | CN1 pin | RP2350 GPIO |
| ------------ | ------- | ----------- |
| RS           | 4       | 8           |
| R/W          | 5       | 9           |
| CS           | 6       | 11          |
| DB4          | 11      | 4           |
| DB5          | 12      | 5           |
| DB6          | 13      | 6           |
| DB7          | 14      | 7           |
| GND          | any     | GND         |

**DB7 must have a pull-down resistor to ground.** DB7 doubles as the HD44780 Busy Flag. If it ever floats while nothing is driving it (which happens between transactions), the CPU sees BF=1 and stalls waiting for the display to un-busy — the piano boot never completes. A 5.6kΩ or 10kΩ resistor from GPIO 7 to GND fixes it. The Pico's internal pull-downs aren't strong enough; you need an external.

The other three data lines (DB4-DB6) don't need external pulls — the firmware enables the internal pulls on all four DBs as a safety net.

The original piano's DB0-DB3 are pulled to specific static levels on its interface board and don't route to the RP2350 at all.

---

## Build and flash

Requires the Pico SDK. See [Raspberry Pi's Getting Started](https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf) if you haven't set it up.

```bash
mkdir build && cd build
cmake -DPICO_BOARD=pico2 -DPICO_SDK_PATH=$PICO_SDK_PATH ..
make -j
```

Produces `pr53_emu.uf2`. Hold BOOTSEL on the Pico while plugging into USB, then drag the .uf2 onto the mass-storage drive that appears.

---

## Running the display

```bash
pip install pyserial
python3 tools/pr53_display.py
```

The tool auto-detects the RP2350's serial port. Override with `--port /dev/ttyACM0` (Linux/Mac) or `--port COM3` (Windows) if needed.

Power on the piano. You should see:

- Voice name showing on Line 1 in the persistent-state panel at the top
- Rhythm/mode info on Line 2
- Current mode (menu label or "playing")
- Raw LCD panel showing whatever the piano is writing to DDRAM in real time
- Status bar at the bottom with event count and `disp=on/OFF`

If you see `# WARN dropped N events` in the raw serial output, the ring buffer is overflowing — probably means a slower USB host or something else is throttling. Filesize implies things are working if `ring_depth` stays near 0 on the alive pings.

---

## What it doesn't do

The Technics glass has ~260 physical segments driven through the HD44780 controller's CGRAM. Roughly 30-40 of those are shaped labels (each mapped to a single CGRAM bit); the other ~220 are 7-segment digits for tempo, chord names, and per-bargraph numeric readouts. This repo maps zero of them by default — the display renders text portions (voice, rhythm, mode) but the CGRAM slots at DDRAM positions 12-15 (which drive the shaped labels and digits on the original glass) show as blank in the mock.

For a playable piano the text is enough. If you want the full segment display, `pr53_map.py` handles the mapping empirically. Expect roughly an hour for the shaped labels and another two or three for the numeric digits.

---

## Generalizing to other devices

This trick works on essentially any HD44780-compatible LCD. If you have a piece of vintage gear (synth, drum machine, industrial equipment, arcade board) with a dead text display and the CPU still runs, the same approach applies:

1. Wire the RP2350 to RS, R/W, CS, and DB4-DB7.
2. Add a pull-down on DB7.
3. Adjust `pio_read_response_init` timing if your target CPU's bus is faster than the SX-PR53's.
4. Rebuild the Python display's LCD dimensions if it's not 16x2.

The state machine and event log format are display-agnostic. The only Technics-specific behavior is the persistent-state heuristic in `pr53_display.py`, which classifies text as menu-label vs voice/rhythm name — easy to strip out or replace.

If you adapt this to another device I'd love to hear about it.

---

## Acknowledgments

Substantial pair-programming with [Claude Opus 4.7](https://www.anthropic.com/claude). The physical work — probing, cutting, wiring, verifying — was mine; the C firmware, the Python tools, the electrical debugging plans, and most of the pattern-matching on byte-level corruption came out of that collaboration. Neither side could have done it alone.

## Related

- [The Key & Cable Company](https://keyandcable.com) — the shop
- [openchord-project](https://github.com/keyandcableco/openchord-project) — earlier RP2350-based restoration for the Suzuki Omnichord OM-27
- [Full writeup](https://keyandcable.com/blog/reviving-the-technics-sx-pr53.html)

## License

MIT. See [LICENSE](LICENSE).

`pico_sdk_import.cmake` is from the Raspberry Pi Pico SDK and keeps its BSD-3-Clause licence (see the file header).
