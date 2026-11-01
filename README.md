# pr53_emu

A replacement display for a Technics SX-PR53 digital piano whose chip-on-glass
LCD died. A tap board sits on the HD44780 bus between the piano's CPU and the
dead display: it mirrors every write, answers the CPU's reads so it never
stalls, logs everything over USB, and forwards each write to a second board
that draws the piano's display on a 3.5" colour TFT. Python tools render the
same display on a laptop and were used to reverse-engineer the glass.

The technique generalizes to most HD44780-compatible LCDs. See
[the writeup](https://keyandcable.com/blog/reviving-the-technics-sx-pr53.html)
for the story and the reasoning behind the design.

```
piano CPU ── HD44780 bus (CN1) ──► carrier J1 ─ level shifters ─► tap (RP2350-Zero) ── USB log ──► tools/
                                                                    │ UART 1 Mbaud
                                                                    ▼
                                                     display (Pico 2) ── 16-bit parallel ──► 3.5" TFT
```

## Status (2026-10-31)

- **Working end to end on the piano.** The carrier board carries both
  RP2350s; the TFT draws the PR53 layout and shows the piano's text.
- **Decoded:** the text lines, tempo, chord root with its flat/sharp,
  transpose, all eight part meters and numbers (hundreds included), and the
  menu page and item readouts with MENU, PAGE, the PAGE arrows and the
  part pointers.
- **Not decoded yet:** chord types, the item number's tens digit, and many
  of the shaped labels on the glass (MIDI and more).
  [`docs/front-panel.md`](docs/front-panel.md) tracks the front-panel decode.
- **Carrier v2 works, with one change when you build it:** fit J2 on the
  underside of the board. DB7's pull-down is too weak to do its job on its
  own; the next revision should fix that. Details in
  [`hardware/carrier/README.md`](hardware/carrier/README.md).

## What's in here

| Path | What |
|---|---|
| [`firmware/tap/`](firmware/tap/) | Tap firmware (v18) for the RP2350-Zero: capture, read responses, USB log, display link |
| [`firmware/display/`](firmware/display/) | Display firmware for the Pico 2: decoders, renderer, panel driver, host test |
| [`tools/`](tools/) | Python: live display mock, recorder, offline analyzer, segment-mapping tools |
| [`captures/`](captures/) | Bus recordings from the piano, including the host test's ground-truth frame |
| [`hardware/carrier/`](hardware/carrier/) | The PR53 carrier v2 board: KiCad, generator scripts, Gerbers, bring-up notes (`rev1/` is the first fab) |
| [`hardware/archive/`](hardware/archive/) | Earlier perfboard maps and board plans |
| [`docs/piano-interface.md`](docs/piano-interface.md) | The piano side: CN1 pinout, the bus, busy flag, power |
| [`docs/front-panel.md`](docs/front-panel.md) | Every panel control and display field, decode status, service test modes |

## Build

Needs the [Pico SDK](https://github.com/raspberrypi/pico-sdk) (built with
2.3.0), `arm-none-eabi-gcc`, `cmake` and `make`. Both firmwares find the SDK
through `firmware/pico_sdk_import.cmake`, from `PICO_SDK_PATH` in the
environment or `-DPICO_SDK_PATH=...`.

```bash
export PICO_SDK_PATH=$HOME/pico-sdk
cmake -S firmware/tap     -B build/tap     -DPICO_BOARD=pico2 && make -C build/tap -j
cmake -S firmware/display -B build/display -DPICO_BOARD=pico2 && make -C build/display -j
make -C firmware/display -f host.mk test     # decoder test on the PC, no hardware
```

That gives `build/tap/pr53_emu.uf2` (for the Zero) and
`build/display/pr53_fw.uf2` (for the Pico 2).

## Flash

Hold BOOT (Zero) or BOOTSEL (Pico 2) while plugging in USB, then copy the UF2
onto the RP2350 drive that appears. Power the TFT and the display Pico
together: the display firmware sets up the panel once, at boot.

To check what's already on a board without changing it, use
`picotool verify -f <uf2>` with a picotool built with USB support (see
`hardware/carrier/README.md`, Bring-up).

## Laptop display

```bash
pip install pyserial
python3 tools/pr53_display.py
```

It auto-detects the tap's serial port (override with `--port /dev/ttyACM0` or
`--port COM3`). Power on the piano and you'll see the voice and rhythm names,
the current menu, the raw DDRAM, and a status bar with the event count. If the
log shows `# WARN dropped N events`, the tap's ring buffer overflowed; healthy
runs keep `ring_depth` near 0 on the `# ALIVE` lines. See
[`tools/README.md`](tools/README.md) for the other tools.

## Generalizing to other devices

This trick works on essentially any HD44780-compatible LCD. If you have a piece of vintage gear (synth, drum machine, industrial equipment, arcade board) with a dead text display and the CPU still runs, the same approach applies:

1. Wire the RP2350 to RS, R/W, CS, and DB4-DB7 (through level shifters if the bus is 5 V).
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

`firmware/pico_sdk_import.cmake` is from the Raspberry Pi Pico SDK and keeps its BSD-3-Clause licence (see the file header).
