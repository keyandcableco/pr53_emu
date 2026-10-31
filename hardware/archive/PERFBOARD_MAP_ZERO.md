> **SUPERSEDED** by `../carrier/`, which keeps this pin map on a PCB.

# PR53 Perfboard Map — RP2350-Zero tap + Pico 2 display

Matches the current firmware exactly. Tap = Waveshare RP2350-Zero (RP2350A,
builds with PICO_BOARD=pico2). Display = full Pico 2. All tap pins are on the
Zero's castellated EDGE (nothing on the back solder pads).

## Current tap pin map (from pr53_emu.c)
| Signal | GP | Notes |
|---|---|---|
| DB4 | GP0 | data (4-bit group GP0-3) |
| DB5 | GP1 | data |
| DB6 | GP2 | data |
| DB7 | GP3 | data |
| RS  | GP4 | control |
| RW  | GP5 | control (PIO jmp pin) |
| (unused) | GP6 | leave open |
| CS  | GP7 | must be base+7 for the PIO wait gate |
| link TX | GP8 | uart1 TX → display GP21 |
| GP9,10,11,12,13 | — | ALL UNUSED (kept clear for tidy routing) |

The 6 capture signals DB4,DB5,DB6,DB7,RS,RW MUST stay contiguous on GP0-5
(the PIO reads them as one 6-bit group). CS must be GP7 (base+7, the PIO's
hardcoded wait-gate). GP6 is skipped.

## RP2350-Zero edge pinout (USB-C at top)
```
LEFT edge (top→bottom):   5V, GND, 3V3, GP29, GP28, GP27, GP26, GP15, GP14
RIGHT edge (top→bottom):  GP0, GP1, GP2, GP3, GP4, GP5, GP6, GP7, GP8
BOTTOM edge (left→right): GP9, GP10, GP11, GP12, GP13
```
Verify against your board silk before soldering. GP16-25 are back-side pads
(unused).

## Where tap signals land on the Zero's edge
- Right edge, top→bottom: GP0-5 = DB4,DB5,DB6,DB7,RS,RW  (clean 6-wire ribbon
  from the shifter LV outputs), then GP6 (skip), GP7 = CS, GP8 = link TX.
- So the ENTIRE tap connection is one column down the right edge. The bottom
  edge (GP9-13) is completely free — no routing there.
- Power off the left edge: 5V, GND, 3V3 (top three).

## Placement
- Zero: USB-C up (for reflashing). Right edge faces the shifters + display.
- Shifters: just right of the Zero's right edge, LV outputs feeding GP0-5
  (+ GP7 for CS). Short parallel ribbon.
- PR53 input header: far left, 5V/piano side of the shifters.
- Pico 2 display: to the right, GP21 facing back toward the Zero's GP8.
- LCD output header: far right off the display.

## The 2-wire link (Zero → Pico 2)
| Wire | Zero (tap) | Pico 2 (display) |
|---|---|---|
| Signal | GP8 (uart1 TX) | GP21 (physical pin 27, uart1 RX) |
| Ground | GND (left edge) | GND (pin 28) |
No 5V/VSYS between boards. Shared ground required. Both sides use uart1 (they
are different chips — no conflict). 1 Mbaud.

## Level shifters (2× BSS138 4-ch)
- Shifter 1: DB4,DB5,DB6,DB7 → Zero GP0,GP1,GP2,GP3 (LV side)
- Shifter 2: RS,RW,CS → Zero GP4,GP5,GP7 (LV side); 4th channel spare
- HV = piano 5V, LV = Zero 3V3 pin, GND = common
- DB7 pulldown 10k on the 5V/HV side of DB7, at the input header

## Display Pico 2 + LCD (unchanged)
GP0-15 = LCD DB0-15, GP16 RS, GP17 WR, GP18 RST, GP21 = link RX,
LCD CS→GND, BL→3V3, LCD 5V from VBUS/5V rail.

## Power rails
- 5V:  piano 5V → shifter HV → LCD 5V
- 3V3: Zero 3V3 pin → shifter LV
- GND: one common rail — piano, shifters, both boards, DB7 pulldown, link, LCD

## Firmware
Build both with PICO_BOARD=pico2. Flash tap .uf2 to the Zero (hold BOOT, plug
USB-C, drag .uf2). Pin map above is already set in firmware/tap/src/pr53_emu.c.
