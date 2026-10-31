> **SUPERSEDED** by `../carrier/`. This map describes an earlier layout (Pico 2 as the tap, capture on GP4-11, link on GP12); the RP2350-Zero perfboard build in `PERFBOARD_MAP_ZERO.md` came in between.

# PR53 Perfboard Wiring Map (two-Pico one-off build)

A tidy side-by-side layout for a soldered perfboard job. Pin choices were
picked so the inter-board link is two short jumpers in the facing region —
no long leaps.

## Board placement

Place both Pico 2 boards on the perfboard **side by side, USB ports pointing
the SAME way (up/away from you)**, with the **DISPLAY board on the LEFT** and
the **TAP board on the RIGHT**, a 2-3 hole gap between them.

```
        DISPLAY PICO (left)                 TAP PICO (right)
        USB up                              USB up
     ┌───────┴────────┐                  ┌───────┴────────┐
     │ 1            40 │                  │ 1            40 │
     │ .              . │                 │ .              . │
     │ (LCD bus       ) │   the link      │ (piano bus     ) │
     │  GP0-15 = left  ) │   lives here    │  GP4-11 = left  ) │
     │  + top-right    ) │      ↓          │  edge           ) │
     │ 20            21 │  ┌─────────┐     │ 20            21 │
     │                  │  │ 2 wires │     │                  │
     │  RX=GP21 (pin27)─┼──┤  short  ├─────┼─TX=GP12 (pin16)  │
     │  GND    (pin28)──┼──┤ parallel├─────┼─GND    (pin18)   │
     │                  │  └─────────┘     │                  │
     └──────────────────┘                  └──────────────────┘
        right edge  ─────────gap─────────►    left edge
```

The DISPLAY's right edge faces the TAP's left edge. The link crosses the gap
at the lower-middle of both boards.

## THE INTER-BOARD LINK — only 2 wires

| Wire | From (TAP, right board) | To (DISPLAY, left board) | Notes |
|---|---|---|---|
| Signal | GP12 = **physical pin 16** (left edge) | GP21 = **physical pin 27** (right edge) | data, 1 Mbaud |
| Ground | GND = **physical pin 18** (left edge) | GND = **physical pin 28** (right edge) | shared ground (required) |

Both wires are short, parallel, and stay in the facing region. **Do NOT run
any 5V/VSYS wire between the boards** — each Pico gets its own power (see
below). Only these two wires cross the gap.

## TAP PICO — piano bus connections (right board)

These go to the Technics PR53 motherboard bus (your existing tap points).
Unchanged from your working setup — same GP4-11 capture pins.

| Signal | Pico GP | Physical pin | Notes |
|---|---|---|---|
| DB4 | GP4  | pin 6  | |
| DB5 | GP5  | pin 7  | |
| DB6 | GP6  | pin 9  | |
| DB7 | GP7  | pin 10 | **10k pulldown to GND here** (busy-flag) |
| RS  | GP8  | pin 11 | |
| RW  | GP9  | pin 12 | |
| CS  | GP11 | pin 15 | |
| bus GND | GND | pin 13 or 3/8 | common with piano ground |

**DB7 pulldown:** 10k resistor from GP7 (pin 10) to any GND pin. On perfboard,
place it right at pin 10 — a short resistor to the ground rail. This is the
one that stops the busy-flag stall.

Power the TAP Pico from USB (its own cable) OR from the piano 5V into VSYS
(pin 39) — your choice, but pick ONE.

## DISPLAY PICO — LCD connections (left board)

The 3.5" LCD is a separate module on a ribbon/header. Drive it at 3.3V.

| LCD signal | Pico GP | Physical pin |
|---|---|---|
| DB0..DB7   | GP0..GP7   | pins 1,2,4,5,6,7,9,10 |
| DB8..DB15  | GP8..GP15  | pins 11,12,14,15,16,17,19,20 |
| RS  | GP16 | pin 21 |
| WR  | GP17 | pin 22 |
| RST | GP18 | pin 24 |
| CS  | — | tie to a GND pin (always selected) |
| BL  | — | tie to 3V3 (pin 36) (always on) |
| LCD 5V | — | 5V/VBUS (pin 40) or your 5V rail |
| LCD GND | — | any GND |

Note: DB0-15 fills the DISPLAY's entire left edge (pins 1-20, skipping the
GND/power pins), so keep the LCD ribbon exiting to the LEFT/away from the gap.
That keeps the LCD wires and the inter-board link on opposite sides — no
crossing.

Power the DISPLAY Pico from its own USB, or from a shared 5V rail into VSYS
(pin 39). If you power both from one 5V supply, tie both VSYS pins to it and
all GNDs common — but then don't also plug in USB.

## Wiring discipline for a clean board

1. **LCD ribbon exits LEFT** (display board's outer edge). Link exits RIGHT.
2. **Piano bus exits RIGHT** (tap board's outer edge)... actually tap's bus is
   on its LEFT edge (GP4-11). So route the piano harness DOWN/out the bottom of
   the tap board to keep it clear of the inter-board link at pin 16/18.
3. **Grounds:** run one ground rail down the perfboard between the boards; both
   Picos' GND pins and the link ground tie to it.
4. **The only gap-crossing wires are the 2 link wires.** Everything else stays
   on its own board's outer side.

## Summary of the ONE firmware change
- TAP display-link TX moved GP0 → **GP12** (pin 16) so it faces the display's
  RX. This is already set in firmware/tap/src/pr53_emu.c (#define DISP_TX_PIN 12).
- DISPLAY RX stays GP21 (pin 27). No display-side change.
- All capture and LCD pins unchanged.
