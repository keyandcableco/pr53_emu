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
      preview.c               Host tool: draws a capture moment as an image
    CMakeLists.txt            Pico SDK build -> pr53_fw.uf2
    host.mk                   Build, test and preview on a PC

## Architecture

    tap UART --> core0: bus_get_byte_timeout() -> hd44780_feed()
                        on DISP_CTRL 0x0C, or 30 ms of quiet after writes
                        -> pr53_decode_all() -> state
                                                                   |
                                                       seqlock (lock-free)
                                                                   v
                 core1: state_read() -> render_frame() -> parallel bus

- **Commit gating:** a frame is published on the piano's own DISP_CTRL (0x0C)
  command, so the screen shows settled frames, never half-written ones. Menus
  are written without a DISP_CTRL afterwards, so writes followed by 30 ms of
  quiet (`SETTLE_US` in `main.c`) are published too; the piano's own updates
  have ~4 ms gaps, so that only fires once a burst is over.
- **Layout:** follows the printed frame of the original glass: TEMPO, CHORD and
  PAGE/TRANSPOSE boxes on top, the two text lines in a big box, the part meters
  between two dotted rules. Numbers are 7-segment digits with faint ghost
  segments.
- **Dirty tracking:** `render_frame()` repaints only the fields that changed.
- **Panel set-up happens once, at boot** (`ili9488_init()` on core 1, then
  `render_static()` paints the fixed layout). Power the panel together with the
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
    make -f host.mk test       # expect: CHECK P8 value == 127: PASS
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

The preview shows true colours; RGB/BGR order is a panel setting it can't show.

## Not decoded yet

- Hundreds digits for Parts 1-7 (numbers show tens and ones). When they're
  mapped in Python, mirror the change in `NUMBER_MAP[]` in `pr53_decode.c`.
- The two small 2-digit displays (`small_top`/`small_bot` in
  `pr53_decode_all`) show "--".
- Part 6's meter, and many of the shaped labels on the glass.
