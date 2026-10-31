# The piano side: CN1 and the LCD bus

How the SX-PR53's main board talks to its display, and what the carrier
connects to. Sources: the Technics SX-PR53 service manual (Schematic
Diagram-1, "A MAIN (CPU) CIRCUIT", page 50 of the PDF) and bench measurements
on 2026-10-31.

## CN1 pinout

CN1 is the 14-pin connector on the main board marked "TO LCD". Pin 1 is
marked on the board.

| CN1 pin | Signal | Notes | Carrier J1 |
|---|---|---|---|
| 1 | GND | Marked "E" (earth) on the schematic. Measured: continuous with the ground foil. | GND |
| 2 | +5IP | +5D through IP101. Also feeds the front-panel boards. See Power below. | +5V |
| 3 | V0 | Contrast voltage for the old LCD. Not used. | — |
| 4 | RS | Through R3 (0 Ω) and a 100 Ω array. | RS |
| 5 | R/W | Through R4 (0 Ω) and a 100 Ω array. | RW |
| 6 | CS | The HD44780 E strobe. Through R5 (0 Ω) and a 100 Ω array. | CS |
| 7 | DB0 | Tied to GND on the main board. Measured: continuous with the ground foil. | — |
| 8 | DB1 | Tied to GND on the main board. Measured: continuous with the ground foil. | — |
| 9 | DB2 | Tied to GND on the main board (schematic). | — |
| 10 | DB3 | Not connected (schematic). | — |
| 11 | DB4 | Through a 100 Ω array (Z3). | DB4 |
| 12 | DB5 | Through Z3. | DB5 |
| 13 | DB6 | Through Z3. | DB6 |
| 14 | DB7 | Through Z3. Doubles as the busy flag. | DB7 |

Each signal line also has 47 pF to ground on the main board.

## The bus

The CPU drives an HD44780-compatible controller in 4-bit mode on DB4-DB7. A
clean start-up (`captures/startup_2026-10-31.log`):

    FUNC_SET 0x20 (x3), FUNC_SET 0x28 (4-bit, 2 lines), DISP_CTRL 0x08 (off),
    CLEAR 0x01, ENTRY_MODE 0x06, DISP_CTRL 0x0C (on), then CGRAM loads

The glass's segments and shaped labels are drawn through CGRAM, which is why
most of the display has to be decoded bit by bit (see the tools).

## Busy flag

The CPU reads the busy flag on DB7 before it writes. If nothing answers and
DB7 floats high, the piano never finishes starting: no sound, nothing on the
display. The tap firmware answers every read (PIO1). A pull-down on DB7 is the
backstop when nothing answers; on the carrier it's weakened by the shifter
module's own pull-up (see `hardware/carrier/README.md`, Bring-up).

## Power

+5IP is the piano's +5D through IP101, an ICP-N10 IC protector rated 0.4 A,
that also powers the front-panel boards (switches, LEDs, the panel
microcontrollers). On the piano this was built for, IP101 had failed open:
pin 2 read about 3 V and collapsed under any load, and the front-panel LEDs
misbehaved. Replacement: ICP-N10, or NTE15020E (same 0.4 A rating).

The carrier's own current draw (TFT backlight, two RP2350 boards) hasn't been
measured. Check it before putting the carrier on the same 0.4 A protector as
the front panel.

## Side effect worth knowing

With the front panel unpowered at power-on, the piano wrote "ALL INITIAL" to
the display and came up on the default "ConcertGrand": it most likely reset
its stored settings to factory defaults.

## Reading the service manual's schematics

The schematic pages have a text layer, but in an offset font: each character
is `chr(0x120 - ord(c))` of what `pdftotext` prints. Decode it that way to
search the pages for net and part names.
