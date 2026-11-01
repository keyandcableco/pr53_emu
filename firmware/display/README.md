# Display firmware (Pico 2)

Receives the piano's display writes from the tap over a UART, runs them
through an HD44780 emulator and the segment decoders, and draws the PR53's
glass on a **HiLetgo 3.5" ILI9486/ILI9488 480x320 panel with a 16-bit
parallel (8080-style) bus**. It's a C port of the Python decoders in
`tools/`.

## Files

    src/
      bus_tap.c               UART receiver for the tap link (GP21)
      pr53_decode.{h,c}       HD44780 emulation + segment decoders
      pr53_state.{h,c}        Shared display state, seqlock handoff between cores
      pr53_render.{h,c}       Three-zone renderer with per-field dirty tracking
      pr53_font.{h,c}         5x7 bitmap font + box/icon primitives
      pr53_ili9486_par.{h,c}  16-bit parallel bus driver (masked GPIO writes)
      pr53_theme.h            Rotation, colour order and the whole palette
      main.c                  Core 0 decodes, core 1 renders
      test_pipeline.c         Host test: feeds a real capture through the decoder
      test_chords.c           Host test: replays the chord-root campaign
      test_numbers.c          Host test: part numbers and meters, from volume sweeps
      test_menus.c            Host test: menu page readout, MENU/PAGE and arrows
      preview.c               Host tool: draws a capture moment as an image
    CMakeLists.txt            Pico SDK build -> pr53_fw.uf2
    host.mk                   Build, test and preview on a PC

## Architecture

    tap UART --> core0: bus_get_byte_timeout() -> hd44780_feed()
                        on DISP_CTRL 0x0C, or 60 ms of quiet after writes
                        -> pr53_decode_all() -> state
                                                                   |
                                                       seqlock (lock-free)
                                                                   v
                 core1: state_read() -> render_frame() -> parallel bus

- **Commit gating:** a frame is published on the piano's own DISP_CTRL (0x0C)
  command, so the screen shows settled frames, never half-written ones. Menus
  are written without a DISP_CTRL afterwards, so writes followed by 60 ms of
  quiet (`SETTLE_US` in `main.c`) are published too. Gaps inside one update
  reach 30 ms and the piano refreshes every ~105 ms, so that fires once an
  update is over and before the next tick.
- **Layout:** follows the original glass (owner's manual pp. 19-21 and 32,
  and a photo of a working unit): TEMPO, CHORD and PAGE/TRANSPOSE boxes on
  top; RIGHT 1 / RHYTHM with their icons beside the two dot-matrix text lines;
  wedge-shaped part meters between two dotted rules, slanted 7-segment numbers
  and a pointer under each part. The labels, pointers and meters show on the
  normal display only, as on the glass. Transpose puts the actual key at the
  right end of the CHORD box and "TRANSPOSE" in the lower right box.
- **Dirty tracking:** `render_frame()` repaints only the fields that changed.
- **Panel set-up happens once, at boot** (`ili9488_init()` on core 1, then
  `render_static()` paints the fixed layout). It includes the power, VCOM and
  gamma settings from MCUFRIEND_kbv's ILI9486 table; without them the panel's
  brightness isn't even monotonic and no colour comes out right. Power the panel together with the
  Pico; a panel connected later stays blank until the Pico restarts.

## Wiring: Pico 2 to the HiLetgo 36-pin header

On the carrier this goes through J2 and a 2x18 ribbon (J2 must be on the
underside of the board; see `hardware/carrier/README.md`).

| Panel pin | Signal | Pico 2 | Notes |
|---|---|---|---|
| 1, 2 | 5V | — | From the 5 V rail |
| 3-10 | DB8-DB15 | GP8-GP15 | |
| 11-18 | DB7-DB0 | GP7-GP0 | Note the reversed order |
| 19 | RS | GP16 | Command/data select |
| 20 | WR | GP17 | Write strobe |
| 21 | CS | GND | Always selected |
| 22 | RST | GP18 | Active low |
| 23-34 | — | — | NC, onboard flash and SD card: leave open |
| 35, 36 | GND | GND | |

The tap link arrives on **GP21** (uart1 RX). The data bus sits on 16
consecutive GPIOs so one masked write sets it (`PAR_DB_BASE` in
`pr53_ili9486_par.h`). The panel has level shifters on its logic inputs, and
3.3 V drive from the Pico works (confirmed on the bench). Its backlight is on
whenever it has 5 V.

## Build, test, flash

    # On a PC, no hardware needed:
    make -f host.mk test       # expect every CHECK line to end in PASS
    make -f host.mk check      # compile every module

    # For the Pico 2:
    export PICO_SDK_PATH=$HOME/pico-sdk
    cmake -S . -B build -DPICO_BOARD=pico2
    make -C build -j

Hold BOOTSEL on the Pico 2 while plugging in USB, then copy
`build/pr53_fw.uf2` onto the RP2350 drive.

## Changing the look

Colours and orientation live in `src/pr53_theme.h`: rotation, RGB/BGR order,
pixel byte order (`THEME_SWAP_BYTES`) and the palette, with a few ready-made
themes in the comments. The layout is `src/pr53_render.c`.

Check a change on the PC before flashing: `make -f host.mk preview` draws what
the firmware would show for a capture moment, using the real render code, into
`build-host/preview.png`. Pick the moment with `NOTE="..."` (the last `# NOTE`
line containing that text) and the capture with `LOG=...`:

    make -f host.mk preview NOTE="capture step 5: menus_sound_setting"

The preview shows true colours. This panel lights bus bits 0-4 as red, so
`THEME_SWAP_RB` swaps red and blue in software. If colours ever look wrong
on a panel, flash `pr53_colour_test.uf2` (built alongside `pr53_fw.uf2`) and
photograph it: one bar per data line, raw R/G/B/W, and the palette encoded
eight ways (see `src/colour_test.c`).

## Not decoded yet

- The item number beside line 2 (the manual's "01" on a disk's file list).
- Chord types, the MIDI icon and most of the shaped labels on the glass.
  `docs/front-panel.md` lists what's known.

When a field is mapped in Python (`tools/pr53_display.py`), mirror it in
`pr53_decode.c`; `make -f host.mk test` replays real captures through both.
