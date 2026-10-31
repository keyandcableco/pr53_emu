> **SUPERSEDED** by `../carrier/`. This map describes an earlier layout (Pico 2 as the tap, capture on GP4-11, link on GP12); the RP2350-Zero perfboard build in `PERFBOARD_MAP_ZERO.md` came in between.

# PR53 Full Board Wiring Map (perfboard, complete signal chain)

Complete map: PR53 motherboard → input header → 2 level shifters (DB7 pulldown)
→ tap Pico → 2-wire link → display Pico → output header → LCD.

Signal flows straight left-to-right. The 5V→3.3V boundary is one vertical line
between the shifters and the tap Pico. Everything right of that line is 3.3V.

## Board zones (left to right)
```
[PR53 IN] → [Shifter 1] → | → [TAP PICO] --link--> [DISPLAY PICO] → [LCD OUT]
            [Shifter 2]   |
   5V   →    shift      3V3 boundary        3V3            3V3        3V3
```

## Economy note
7 piano signals need shifting. Two 4-channel BSS138 modules = 8 channels,
covers all 7 with 1 spare. A third module is unnecessary — omit it. (If you
keep a 3rd for spares, wire it like the others off the same 5V/3V3/GND rails
and leave its channels unused.)

---

## ZONE 1 — PR53 input header (J1)
1x9 header (or 2x5) carrying the piano bus in. Order for tidy routing:
| J1 pin | Signal | Goes to |
|---|---|---|
| 1 | DB4 | Shifter 1 A1 |
| 2 | DB5 | Shifter 1 A2 |
| 3 | DB6 | Shifter 1 A3 |
| 4 | DB7 | Shifter 1 A4  + 10k pulldown to GND |
| 5 | RS  | Shifter 2 A1 |
| 6 | RW  | Shifter 2 A2 |
| 7 | CS  | Shifter 2 A3 |
| 8 | 5V  | HV rail (both shifters' HV) |
| 9 | GND | common GND rail |

**DB7 pulldown (R1, 10k):** from J1 pin 4 (DB7, the 5V side) to GND. Place it
right at the header/Shifter-1 A4 input. This is the busy-flag pulldown.

---

## ZONE 2 — Level shifters (2x BSS138 4-channel)
Each module has: HV, LV, GND, and 4 channels (HVn=A side / LVn=B side).
Wire HV=5V, LV=3V3, GND=common, on BOTH modules.

### Shifter 1 — the 4 data lines
| Channel | HV side (5V, from piano) | LV side (3V3, to tap) |
|---|---|---|
| 1 | DB4 (J1.1) | GP4  (tap pin 6)  |
| 2 | DB5 (J1.2) | GP5  (tap pin 7)  |
| 3 | DB6 (J1.3) | GP6  (tap pin 9)  |
| 4 | DB7 (J1.4) | GP7  (tap pin 10) |

### Shifter 2 — the 3 control lines
| Channel | HV side (5V, from piano) | LV side (3V3, to tap) |
|---|---|---|
| 1 | RS (J1.5) | GP8  (tap pin 11) |
| 2 | RW (J1.6) | GP9  (tap pin 12) |
| 3 | CS (J1.7) | GP11 (tap pin 15) |
| 4 | (spare)   | (spare)           |

Power to both shifters:
- HV  ← 5V  (from J1.8)
- LV  ← 3V3 (from tap Pico 3V3(OUT), pin 36)
- GND ← common GND rail

---

## ZONE 3 — Tap Pico (capture)
| Signal | GP | Physical pin | From |
|---|---|---|---|
| DB4 | GP4  | 6  | Shifter1 LV1 |
| DB5 | GP5  | 7  | Shifter1 LV2 |
| DB6 | GP6  | 9  | Shifter1 LV3 |
| DB7 | GP7  | 10 | Shifter1 LV4 |
| RS  | GP8  | 11 | Shifter2 LV1 |
| RW  | GP9  | 12 | Shifter2 LV2 |
| CS  | GP11 | 15 | Shifter2 LV3 |
| link TX | GP12 | 16 | → Display GP21 |
| 3V3 out | — | 36 | feeds shifter LV rails |
| GND | — | 3/8/13/etc | common rail |

Power the tap Pico by its own USB, or 5V→VSYS (pin 39). Its 3V3(OUT) pin 36
conveniently powers the LV side of both shifters.

---

## ZONE 4 — the link (tap → display), 2 wires only
| Wire | Tap Pico | Display Pico |
|---|---|---|
| Signal | GP12 (pin 16) | GP21 (pin 27) |
| Ground | GND (pin 18) | GND (pin 28) |
No 5V/VSYS between the boards. Shared ground required.

---

## ZONE 5 — Display Pico (render) + LCD output header (J2)
Display drives the LCD at 3.3V directly (panel has onboard shifters).
| LCD signal | GP | Display pin | J2 pin |
|---|---|---|---|
| DB0..DB7  | GP0..GP7   | 1,2,4,5,6,7,9,10  | 1-8 |
| DB8..DB15 | GP8..GP15  | 11,12,14,15,16,17,19,20 | 9-16 |
| RS  | GP16 | 21 | 17 |
| WR  | GP17 | 22 | 18 |
| RST | GP18 | 24 | 19 |
| CS  | — (GND) | — | 20 → GND |
| BL  | — (3V3) | — | 21 → 3V3 |
| 5V  | — | VBUS pin 40 or 5V rail | 22 |
| GND | — | any GND | 23 |

Power the display Pico by its own USB, or 5V→VSYS (pin 39).

---

## POWER RAILS (run these as 2 bus strips down the board)
- **5V rail:** piano 5V (J1.8) → both shifter HV pins → LCD 5V (J2.22).
  Optionally → both Picos' VSYS if you want single-supply (then no USB).
- **3V3 rail:** tap Pico 3V3(OUT) pin 36 → both shifter LV pins.
  (Display's own 3V3 stays local; LCD logic is driven by GPIO, not the rail.)
- **GND rail:** ONE common ground everything ties to — piano GND, both
  shifters, both Picos, LCD GND, the DB7 pulldown, the link ground.
  A single ground rail down the center of the board is the tidiest.

## Wiring order for a clean build
1. Lay the 3 rails first (5V, 3V3, GND) as bus strips.
2. Solder the 2-wire link between the Picos (shortest, sets spacing).
3. Shifters + DB7 pulldown, wire HV/LV/GND to rails.
4. Piano input header → shifter HV sides.
5. Shifter LV sides → tap Pico capture pins.
6. Display Pico → LCD output header.
7. Keep the piano harness on the far LEFT, LCD ribbon on the far RIGHT —
   they never cross because the whole board flows one direction.

## The ONE firmware change (already applied)
Tap link TX moved GP0 → GP12 (pin 16). Capture pins unchanged (GP4-11).
Display unchanged (RX GP21, LCD GP0-18).
