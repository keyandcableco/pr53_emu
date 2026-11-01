# Tap firmware (v18)

Runs on a Waveshare RP2350-Zero on the carrier board. It listens to the
piano's HD44780 bus, answers the CPU's read cycles so it never stalls, logs
every write over USB, and forwards each write to the display Pico.

- **PIO0** captures each write strobe (RS, R/W, DB4-DB7) into a 2048-slot
  ring buffer. Reads are skipped at the PIO.
- **PIO1** answers every read with all zeros: busy clear, address 0. Up to
  v17 it sent busy = 0 plus the address counter, but the piano often takes
  the low half of that answer as its busy flag (address bit 3 on DB7): about
  half its data writes at addresses with bit 3 set waited out a 3.8 ms
  timeout, and it ran out of time to finish text lines ("ConcertGran", line 2
  left on "SX-PR53", "MEM&CONTRO"). Zeros read as not busy either way. The
  piano has never been given a correct address and copes without one.
- **USB** carries a text log of every write (format below).
- **UART** (one-way, to the display) carries every write as two bytes.

## Pins

| GP | Signal | Notes |
|---|---|---|
| 0-3 | DB4-DB7 | From U1 (shifter). |
| 4 | RS | From U2. |
| 5 | R/W | From U2. Also the PIO jump pin. |
| 6 | — | Unused on purpose. |
| 7 | CS | From U2. Must be GP7. |
| 8 | Link TX | uart1 TX to the display Pico's GP21. |

GP0-GP5 must stay contiguous (PIO reads them as one group), and CS must sit at
base + 7 = GP7 because the capture program's `wait` gate is hardcoded to it.

## USB log

    t=50851143 W CMD 0x0C [DISP_CTRL disp=1 cur=0 blink=0]
    t=50851263 W DAT 0x00 (CGRAM ref #0)
    t=67174175 W DAT 0x6E 'n'
    # ALIVE us=153004577 ring_depth=0 drops=0

`t` is microseconds since boot. `# ALIVE` comes every 2 s; `drops` above 0
means the ring buffer overflowed. The format is unchanged since v14, so all
the stream tools in `tools/` read it.

## Display link

uart1 TX on GP8, 1 Mbaud, 8N1. Two bytes per write: a tag (`0x00` command,
`0x01` data), then the value. A write is only sent when the TX FIFO is empty,
so the link never blocks the capture; a skipped write costs one display update
and the display catches up on the piano's next DISP_CTRL commit.

## Build and flash

    export PICO_SDK_PATH=$HOME/pico-sdk
    cmake -S . -B build -DPICO_BOARD=pico2
    make -C build -j

Hold BOOT on the Zero while plugging in USB-C, then copy `build/pr53_emu.uf2`
onto the RP2350 drive.

## Start-up

It answers reads, captures and forwards writes as soon as it starts. (Up to
v16 it first waited up to 3 s for a USB host, so a piano already running saw its
busy checks go unanswered for that long.) The banner only reaches a host
that's already listening.
