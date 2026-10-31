> **CAUTION:** this single-chip plan reads the piano through a one-way 74LVC245, but the tap firmware also *answers* read cycles on DB4-7 (PIO1 in `firmware/tap/src/pr53_emu.c`). A one-way buffer breaks that. Use bidirectional shifting (see `../carrier/`) or rework the read path before building this.

# PR53 Custom Board — KiCad Build Guide & Netlist

Single-board replacement display controller for the Technics SX-PR53.
One **RP2354B** (QFN-80, 48 GPIO, 2MB internal flash) does everything:
taps the piano's HD44780 bus AND drives the replacement LCD. No second MCU,
no UART link.

## Start here (don't draw from scratch)
1. Download Raspberry Pi's official **RP2350B Minimal KiCad design**:
   https://datasheets.raspberrypi.com/rp2350/Minimal-KiCAD.zip
   Use the **QFN-80** board. It has the MCU power, crystal, USB, RUN, and
   BOOTSEL already correct.
2. Swap the RP2350B for **RP2354B** (same footprint) and **delete the external
   QSPI flash** (2354B has internal flash). Leave the flash footprint as DNP if
   you want the option to fall back to RP2350B + W25Q16.
3. Add the three blocks below (245 buffer, connectors, DB7 pulldown).
4. JLCPCB layout notes: https://jlcpcb.com/blog/how-to-design-layout-with-rp2350

## Blocks to add to the reference design

### U2 — 74LVC245A (piano-bus read buffer), TSSOP-20
5V-tolerant inputs, powered at 3V3, so it level-shifts the piano's 5V bus down
to 3V3 for the MCU. Wire it ONE-WAY (piano A-side -> MCU B-side).
Datasheet TSSOP-20 pinout (verified): DIR=1, A1..A8=2..9, GND=10,
B8..B1=11..18, /OE=19, VCC=20.
- VCC (pin 20) -> 3V3
- GND (pin 10) -> GND
- DIR (pin 1)  -> 3V3   (A->B direction, fixed; we only READ the piano)
- /OE (pin 19) -> GND   (always enabled; datasheet suggests a pullup to VCC for
                         clean power-up Hi-Z, but for a permanent read buffer
                         tying to GND is fine — it's on whenever powered)
- A-side (inputs, 5V piano bus from J2):
    A1(pin2)=DB4  A2(pin3)=DB5  A3(pin4)=DB6  A4(pin5)=DB7
    A5(pin6)=RS   A6(pin7)=RW   A7(pin8)=CS   A8(pin9)=GND (unused, tie low)
- B-side (outputs, 3V3 to MCU):
    B1(pin18)=GPIO20  B2(pin17)=GPIO21  B3(pin16)=GPIO22  B4(pin15)=GPIO23
    B5(pin14)=GPIO24  B6(pin13)=GPIO25  B7(pin12)=GPIO26  B8(pin11)=NC
  (Channel n: A on the low-pin side, B on the high-pin side, mirrored.)

### R_DB7 — 10k, 0402  (the busy-flag pulldown)
From the PIANO DB7 line (U2 pin 5 / A4, the 5V side) to GND. This is the
load-bearing resistor. On-board placed part now, no loose leg.

### J2 — Piano tap connector (1x8, 2.54mm or JST-XH)
Pin 1: DB4   -> U2 A1 (pin2)
Pin 2: DB5   -> U2 A2 (pin3)
Pin 3: DB6   -> U2 A3 (pin4)
Pin 4: DB7   -> U2 A4 (pin5)  + R_DB7 to GND
Pin 5: RS    -> U2 A5 (pin6)
Pin 6: RW    -> U2 A6 (pin7)
Pin 7: CS    -> U2 A7 (pin8)
Pin 8: GND   -> board GND
(Piano 5V is NOT required by the board if USB/own-supply powers it; if you
 want to power FROM the piano, add a 9th pin for piano 5V -> VSYS/LDO input.)

### J3 — LCD connector (2x18 2.54mm header, matches the 36-pin panel)
Drive directly at 3V3 (panel has onboard shifters). Map per the panel's 36-pin
table (see firmware/display/README.md wiring chart), with:
  LCD_DB0..15 -> GPIO0..15
  LCD_RS      -> GPIO16
  LCD_WR      -> GPIO17
  LCD_RST     -> GPIO18
  LCD_CS      -> GND
  LCD_BL      -> 3V3 (or via a transistor if you want SW brightness later)
  5V, GND     -> board 5V/GND

### J1 — USB-C (power + reflash)
From the reference design. Powers the board (5V -> LDO -> 3V3) and does UF2
flashing. Keep it accessible in the enclosure.

### Power
- USB-C 5V (or piano 5V) -> U3 LDO (NCP1117-3.3 / AMS1117-3.3) -> 3V3
- 3V3 feeds RP2354B (all IOVDD, DVDD via reference decoupling), U2 VCC, LCD.
- The LCD's own 5V pin: feed from the board's 5V input (USB VBUS or piano 5V).

## Pin assignment (authoritative — matches pr53_board_pins.h)
| RP2354B GPIO | Net        | Goes to            |
|---|---|---|
| GPIO0..15   | LCD_DB0..15 | J3 (LCD data)      |
| GPIO16      | LCD_RS      | J3                 |
| GPIO17      | LCD_WR      | J3                 |
| GPIO18      | LCD_RST     | J3                 |
| GPIO20      | TAP_DB4     | U2 B1              |
| GPIO21      | TAP_DB5     | U2 B2              |
| GPIO22      | TAP_DB6     | U2 B3              |
| GPIO23      | TAP_DB7     | U2 B4              |
| GPIO24      | TAP_RS      | U2 B5              |
| GPIO25      | TAP_RW      | U2 B6              |
| GPIO26      | TAP_CS      | U2 B7              |
| GPIO28      | STATUS_LED  | LED1 + R           |
| USB_DM/DP   | USB         | J1 (27R series)    |
| XIN/XOUT    | 12MHz xtal  | Y1                 |

21 GPIO still free (GPIO19,27,29-47) for future features.

## BOM (JLCPCB — pick "basic/preferred" parts to avoid feeder fees)
| Ref | Part | Pkg | Note |
|---|---|---|---|
| U1  | RP2354B | QFN-80 | MCU + 2MB flash (or RP2350B + U4 flash) |
| U2  | SN74LVC245APW | TSSOP-20 | piano-bus buffer |
| U3  | AMS1117-3.3 or NCP1117-3.3 | SOT-223 | 5V->3V3 LDO |
| Y1  | 12MHz crystal | SMD 3225 | + 2x 27pF |
| U4  | W25Q16 (DNP) | SOIC-8 | only if using RP2350B |
| R_DB7 | 10k | 0402 | busy-flag pulldown |
| R USB | 27R x2 | 0402 | USB series |
| R boot/run | 1k, 10k | 0402 | BOOTSEL/RUN |
| C decoupling | 100n x8, 10u x2, 1u | 0402/0805 | per reference |
| C xtal | 27pF x2 | 0402 | crystal load |
| SW1 | tact | SMD | BOOTSEL |
| SW2 | tact | SMD | RUN/reset |
| J1 | USB-C 16P | SMD | power + data |
| J2 | 1x8 header/JST | 2.54 | piano tap |
| J3 | 2x18 header | 2.54 | LCD |
| LED1 | LED + R | 0402 | power/status |

## Firmware merge (when board arrives)
Combine the two firmwares into one binary:
- core0: PIO capture (from v16 tap) on GPIO20-26 — update PIN_DB4=20 etc.
- core1: LCD render (from display firmware) on GPIO0-18 — PAR_DB_BASE=0.
- Delete the UART link entirely (disp_uart_send, bus_tap.c UART receiver) —
  the two halves now hand off in-chip via the seqlock already in pr53_state.c.
- All pin numbers come from pr53_board_pins.h.
