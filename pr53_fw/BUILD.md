# Building & Flashing pr53_fw

This is the **display-side** firmware (drives the LCD). It builds with the
same Pico SDK toolchain you already use for your v15 tap firmware — nothing
new to install.

## 0. One-time: confirm your toolchain (you already have this from v15)

    echo $PICO_SDK_PATH          # should point at your pico-sdk checkout
    # if empty:
    export PICO_SDK_PATH=~/pico-sdk

You also need the ARM cross-compiler + cmake, which you already installed to
build v15 (`arm-none-eabi-gcc`, `cmake`, `make`). If `which arm-none-eabi-gcc`
prints a path, you're set.

## 1. Build

    cd ~/pr53_fw            # wherever you put this folder
    mkdir -p build && cd build
    cmake -DPICO_BOARD=pico2 ..
    make -j

Success produces **`pr53_fw.uf2`** in the build directory. (It links out of
the box because `src/bus_tap.c` is a temporary stub — see step 4 to replace
it with the real bus tap.)

## 2. Flash (drag-and-drop UF2 — no extra tools)

1. Hold the **BOOTSEL** button on the display Pico 2 and plug it into USB
   (keep holding until it mounts).
2. It appears as a USB drive named **RP2350** (or RPI-RP2).
3. Copy `pr53_fw.uf2` onto that drive:

       cp pr53_fw.uf2 /media/$USER/RP2350/      # Linux (path varies)
       # or on macOS: cp pr53_fw.uf2 /Volumes/RP2350/
       # or just drag it in a file manager

4. The Pico reboots automatically and starts running. Done.

(If you prefer, `picotool load pr53_fw.uf2` works too — same tool you may
have used for v15.)

## 3. First light — panel test (no bus needed yet)

With the stub `bus_tap.c` in place, the firmware boots and paints the static
glass furniture (backlight field, zone rules, printed part labels
DRUMS/AC3/.../R1, empty boxes). If you SEE that on the LCD, your **wiring
and panel are good**. Colors/orientation off? Tweak the `0x36` MADCTL byte
in `pr53_ili9486_par.c` init and re-flash.

Nothing will animate yet — that's expected; there's no bus data.

## 4. Wire in the real bus (two-Pico UART bridge)

This build uses **two Picos**: your existing v15 TAP Pico (untouched) sends
each decoded access over a UART wire to this DISPLAY Pico.

**Wiring — 2 wires between the Picos:**

    TAP GP8 (uart1 TX)  ->  DISPLAY GP21 (uart1 RX)
    TAP GND             ->  DISPLAY GND             (shared ground REQUIRED)

**Display side (this firmware):** already done — `src/bus_tap.c` is the UART
receiver. Nothing to change; it reads the 2-byte protocol on GP21 at 1 Mbaud.

**Tap side (your v15 firmware):** already done for you — see
`../tap-pico/src/pr53_emu.c`. That's your v15 plus the UART sender (it's
"v16"). Just build and flash it like any Pico firmware:

    cd ../tap-pico && mkdir -p build && cd build
    cmake -DPICO_BOARD=pico2 .. && make -j
    # flash pr53_emu.uf2

Its CMakeLists already has the required setting
(`pico_enable_stdio_uart 0`) so stdio doesn't grab the capture/link pins while
USB logging keeps working.

**Protocol** (both sides already match): byte0 = tag (0x00 cmd / 0x01 data),
byte1 = value. The display resyncs automatically if it ever powers up
mid-packet.

Then reflash THIS Pico (steps 1-2) with the real `bus_tap.c` in place (it
already is) and the meters come alive.

## Order of bring-up (recommended)

1. **Panel-only test first.** Temporarily make `bus_get_byte()` return false
   (comment out the UART read, `return false;`) OR just flash before wiring
   the UART — with no bytes arriving it blocks, so instead swap in the
   original stub for this test. You want to confirm `render_static()` paints
   the glass furniture = wiring + panel good.
2. **Add the UART link + v15 sender**, reflash both Picos, and the live
   meters/text should appear.

## Rebuilding after edits

From the `build/` dir, just `make -j` again (no need to re-run cmake unless
you added/removed source files, in which case re-run the `cmake` line first).

## Quick sanity check WITHOUT hardware

You can prove the decode logic on your PC anytime (no Pico):

    cd ~/pr53_fw
    make -f host.mk test      # expect: CHECK P8 value == 127: PASS
