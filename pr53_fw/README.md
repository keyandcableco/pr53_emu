# PR53 Display Firmware (RP2350)

C port of the Python display emulator, driving a real LCD panel from the
live HD44780 bus. Currently targets a **HiLetgo 3.5" ILI9486/ILI9488
480x320, 16-bit PARALLEL (8080-style) bus, non-touch** panel.

## What's here

    src/
      pr53_state.{h,c}        Shared DisplayState + seqlock handoff (decode<->render)
      pr53_decode.{h,c}       HD44780 emulation + segment decoders (1:1 port of Python)
      pr53_render.{h,c}       Three-zone renderer with per-field DIRTY TRACKING
      pr53_font.{h,c}         5x7 bitmap font + box/icon primitives
      pr53_ili9486_par.{h,c}  16-bit PARALLEL bus driver (bit-banged masked GPIO)
      main.c                  Dual-core wiring (core0 decode, core1 render)
      test_pipeline.c         Host test: feeds a real log through the C pipeline
    CMakeLists.txt            Pico SDK build -> pr53_fw.uf2
    host.mk                   Build/test the logic on a PC (no Pico needed)

## Wiring chart: RP2350 <-> HiLetgo 36-pin panel

| HiLetgo Pin | Signal    | Pico 2 GPIO | Notes |
|---|---|---|---|
| 1  | 5V       | VBUS/5V | power |
| 2  | 5V       | 5V     | tie w/ pin 1 |
| 3  | LCD_DB8  | GP8    | |
| 4  | LCD_DB9  | GP9    | |
| 5  | LCD_DB10 | GP10   | |
| 6  | LCD_DB11 | GP11   | |
| 7  | LCD_DB12 | GP12   | |
| 8  | LCD_DB13 | GP13   | |
| 9  | LCD_DB14 | GP14   | |
| 10 | LCD_DB15 | GP15   | |
| 11 | LCD_DB7  | GP7    | |
| 12 | LCD_DB6  | GP6    | |
| 13 | LCD_DB5  | GP5    | |
| 14 | LCD_DB4  | GP4    | |
| 15 | LCD_DB3  | GP3    | |
| 16 | LCD_DB2  | GP2    | |
| 17 | LCD_DB1  | GP1    | |
| 18 | LCD_DB0  | GP0    | |
| 19 | LCD_RS   | GP16   | command/data select |
| 20 | LCD_WR   | GP17   | write strobe |
| 21 | LCD_CS   | **GND** | tie LOW — always selected (no GPIO) |
| 22 | LCD_RST  | GP18   | reset, active low |
| 23-25 | NC    | —      | no connection |
| 26 | FLASH_CS | —      | onboard flash, leave open |
| 27-30 | NC    | —      | no connection |
| 31-34 | SPI_MISO/MOSI/CLK/SD_CS | — | onboard SD slot, UNUSED — leave open |
| 35 | GND      | GND    | |
| 36 | GND      | GND    | tie w/ pin 35 |

Plus the **UART link from the tap Pico** (not a panel pin):

| From TAP Pico | To DISPLAY Pico | Notes |
|---|---|---|
| GP8 (uart1 TX) | GP21 (uart1 RX) | one-way display link |
| GND | GND | shared ground required |

**Backlight (BL):** tie to 3V3 (or 5V) for always-on — not driven by a GPIO
in this map. If your board's BL pin isn't on the 36-pin header, it's on the
silkscreen; find it and tie it high.

**Why GP0-15 for data:** 16 *consecutive* GPIOs let the firmware set the
whole 16-bit bus with one masked write — see `PAR_DB_BASE` in
`pr53_ili9486_par.h` (set to 0, matching this chart). Data on GP0-15,
control on GP16-18, and the tap UART on GP21 (uart1, clear of the data
block — uart0's RX would be GP1 = DB1).

**Pin budget:** 16 data + RS/WR/RST (3) + UART RX (1) = 20 of the Pico 2's
26 GPIO, with CS and BL tied in hardware. 6 pins to spare.

**Voltage:** the panel wants 5V power but reportedly has an onboard
5V/3.3V level shifter on its logic pins — verify this on your physical
board (look for a level-shifter IC near the header) before wiring Pico 2
GPIO directly to DB/RS/WR/RST. If there's no shifter, add one; RP2350
GPIO is not 5V-tolerant.

**SPI pins (31-34) are for the onboard SD card slot only** — unrelated to
driving the LCD. Leave them unconnected unless you want SD storage too.

## Architecture

    HD44780 bus --PIO--> core0: reassemble nibbles -> hd44780_feed()
                                on 0x0C commit -> pr53_decode_all() -> g_state
                                                                        |
                                                          seqlock (lock-free)
                                                                        v
                    core1: state_read() -> render_frame() -> parallel bus write

Two cores so bus decoding never stalls on display writes.

## Key design points

- **Commit gating:** a fresh frame publishes only on the piano's own
  DISP_CTRL (0x0C) command — same gating validated in the Python emulator.
  Shows settled frames, never mid-write flicker.
- **Dirty tracking:** `render_frame()` diffs against the last frame and
  repaints ONLY changed fields (a single number, a meter bar).
- **Parallel bus, bit-banged:** DB0-15 on 16 consecutive GPIOs means one
  masked SIO write sets the whole bus; a WR pulse latches it. This is
  simple and should be plenty fast for our ~75ms update cadence (region
  updates are a few hundred pixels, not full-screen). If profiling later
  shows it's not fast enough, a PIO program can drive the same bus faster
  without changing anything above `pr53_ili9486_par.c`.
- **Faithful decode:** `pr53_decode.c` is a direct port of the Python
  decoders. Verified: feeding session_092906.log through the C pipeline
  reproduces the exact frame (P8=127, all levels/values match).

## Build & test on a PC (now, no hardware)

    make -f host.mk check    # compile every module
    make -f host.mk test     # run the pipeline test against a captured log

Expect: `CHECK P8 value == 127: PASS`.

## Build for the Pico 2 (when ready)

    export PICO_SDK_PATH=~/pico-sdk
    mkdir build && cd build
    cmake -DPICO_BOARD=pico2 ..
    make
    # drag pr53_fw.uf2 onto the Pico

## Bring-up checklist

1. **Wire the panel** per the chart above. Confirm the level-shifter
   situation before connecting. Leave the UART wire (to the tap Pico)
   disconnected for now.
2. **Build & flash as-is.** The project links out of the box —
   `src/bus_tap.c` already defines `bus_get_byte()` (it's the UART
   receiver), so there's nothing to stub. See BUILD.md.
3. **Panel smoke test (no tap needed).** On boot, core1 runs
   `render_static()` immediately — it paints the glass furniture
   (backlight field, divider rules, part labels DRUMS/AC3/.../R1). Core0
   then blocks waiting for UART bytes that aren't coming yet — that's
   fine. **If you see the static glass layout, your wiring + panel +
   driver + pin map all work.** Nothing animates (no bus data) — expected.
   - Colors/orientation off? Tweak the `0x36` MADCTL byte in
     `pr53_ili9486_par.c` init and re-flash.
4. **Connect the two boards** and flash the tap Pico with its v16 firmware
   (`../tap-pico/`). Wire: TAP GP8 -> DISPLAY GP21, TAP GND -> DISPLAY GND.
   Now live meters/text appear.
5. **If updates feel slow** — the bit-banged writer uses a few NOPs per
   pulse for WR timing margin; once it's working, this is the first place
   to tune (shrink the NOP count, or move to PIO) if needed.

**Optional — test live rendering without the tap board.** If you want to
see decoded numbers/meters (not just the static furniture) before wiring
the two Picos, you can make `bus_get_byte()` replay one canned frame
instead of reading the UART. Ask for the `SELFTEST` toggle, or just wire
the two boards — either works.

## Notes / TODO

- Hundreds digits for parts 1-7 aren't mapped yet (same as the emulator) —
  numbers show tens+ones until then. When mapped in Python, mirror the
  change in `NUMBER_MAP[]` in `pr53_decode.c`.
- Small 2-digit displays render "--" until their decoder is added
  (`small_top`/`small_bot` in `pr53_decode_all`).
- The font is a functional 5x7 bitmap; swap for a 7-seg vector look later
  if you want the digits closer to the original glass.

