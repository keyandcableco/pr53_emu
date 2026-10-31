# First module-carrier netlist (archived)

The starting point for the carrier board, before `../../carrier/` replaced it
with a generated, routed board. Kept for reference.

- `pr53.net`: KiCad netlist with all seven parts footprinted. In the PCB
  editor, File > Import > Netlist brings them in with every connection as a
  ratsnest.
- `pr53_netlist.py`: the SKiDL script that generated it (needs
  `KICAD_SYMBOL_DIR` pointing at KiCad's symbol libraries).
- `pr53_placement.kicad_pcb`: a placement scaffold, about 100 x 55 mm, with the
  parts as labelled proxies in signal order.

## Parts

| Ref | What | Footprint |
|---|---|---|
| J1 | PR53 CN1 tap input (9-pin) | 1x09 header |
| U1 | BSS138 4-ch shifter (DB4-7) | 2x06 header |
| U2 | BSS138 4-ch shifter (RS/RW/CS) | 2x06 header |
| A1 | RP2350-Zero (tap) | 2x10 header |
| A2 | Pico 2 (display) | 2x20 header |
| J2 | HiLetgo LCD output | 2x18 header |
| R1 | 10k DB7 pull-down | 0603 SMD |

## Wiring in the netlist

- CN1: DB4-7 (pins 11-14 to J1 1-4), RS/RW/CS (CN1 4/5/6 to J1 5-7), +5V, GND
- R1: DB7 to GND, on the 5 V side
- Shifter 1: HV = DB4-7, LV to Zero GP0-3
- Shifter 2: HV = RS, RW, CS, LV to Zero GP4, GP5, GP7
- Zero GP8 (link) to Pico 2 GP21
- Pico 2 GP0-15 to LCD DB0-15, GP16/17/18 to LCD RS/WR/RST, LCD CS to GND
- Power: 5 V rail to shifter HV and the LCD; 3V3 from the Zero to shifter LV
