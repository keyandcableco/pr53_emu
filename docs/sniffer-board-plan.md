# Display sniffer board: product plan

A plan for a stand-alone display sniffer, built on what the PR53 project and
[the feasibility study](display-sniffer-feasibility.md) found. The goal: one
board, with or without an enclosure, that a repair tech clips onto a vintage
keyboard's display bus to see, log and diagnose what the CPU sends to the
display, and that can stand in for a dead display while the instrument is on
the bench. The same board, without the enclosure, is the core of any
per-model replacement display later.

Type letters (A-G) and section numbers in parentheses refer to the
feasibility study.

## Not verified: confirm before ordering

- **PGA2350 module** (the proposed MCU for prototypes): specs from
  [Pimoroni's page](https://shop.pimoroni.com/products/pga2350): RP2350B,
  48 GPIO of which 8 are ADC-capable, 16 MB flash, 8 MB PSRAM with its chip
  select on GP47, 64-pin 2.54 mm grid, 25.4 mm square, 3V3 regulator good
  for 300 mA, 3-5.5 V in. Not checked: price and stock (the page showed a
  pre-order), which pins carry USB, SWD, RUN and BOOT, and which RP2350
  stepping it uses.
- **SN74LVC16T245** (main translator): the input tolerance the passive
  default relies on is checked in TI's datasheet (SCES636B, see 3.4). Not
  checked: price, stock, and the footprint of the 48-pin SSOP (DL).
- **Not chosen yet:** the 3.5" SPI TFT module (ST7796S-class is from memory)
  and its pinout and outline, the TVS and Schottky clamp parts, the ideal
  diodes, the break-before-make switch, the second 3V3 regulator. Pick and
  check real parts at schematic time.
- **Power figures** in 3.6 are estimates from memory; measure at rev A.
- **Instrument connectors** behind the adapter list: the JV-2080/XP flat
  cable as 14-way, 1.25 mm is my reading of an OCR'd part string; the RM1x's
  12-pin pinout is a forum post with some pins marked uncertain.
- **The SED1335 panel pixel clock** (about 0.5 MHz) is my calculation.
- **All costs and effort figures** are estimates from memory, not quotes.
- **The PR53's strobe direction** (2.1) is still unmeasured. The new board
  makes it a setting, but replace mode on the PR53 itself needs it measured.

## Changes from the feasibility study

- **One RP2350B instead of a tap module plus a display module** (3.2).
- **The translator's host side defaults to the tool's 3.3 V, not the host's
  supply.** The study had it follow the host. The datasheet allows 5 V
  inputs on a 3.3 V port whose outputs are off, so passive sniffing needs no
  connection to the host's supply at all; the host supply is used only to
  answer reads (3.4).
- **A 2x13 connector instead of 2x10**, for three analog inputs, the adapter
  ID and six grounds (3.7).

## 1. What the product is

Three things a tech gets from it, in the order they matter in the shop:

1. **Diagnosis.** Clip on, see what the CPU sends. If the bus is right and the
   glass is wrong, it's the display, its cable or its contrast supply; if the
   bus is wrong, it's the main board. Plus automatic checks: data lines that
   never move, strobes too short for the controller, writes while the
   controller says busy, the instrument's supply and the display's contrast
   voltage.
2. **A stand-in display.** Show the instrument's display on the tool's screen
   or a laptop, so a unit with dead glass can still be operated, tested, and
   have the customer's patches dumped before work starts.
3. **A logger.** Hours of time-stamped bus traffic on an SD card for
   intermittent faults.

What it is not: a logic analyzer replacement (it knows display controllers,
nothing else), and not a fix for glass driven directly by the main CPU
(type G).

### Two builds from one PCB

| Build | For | Contents |
|---|---|---|
| **Bench tool** | The shop, and other techs if it sells | Board, 3.5" screen, buttons, SD, enclosure, an adapter kit |
| **Bare core** | Permanent replacement displays, one model at a time | The same board with the host power path fitted, no enclosure, the screen or panel the model needs |

### Two modes, with a rule

- **Passive:** listen only. The original display can stay connected (Y
  adapters). Nothing on the tool drives the bus.
- **Replace:** answer the CPU's reads in place of the controller. **Only with
  the original controller removed or disconnected**, because two drivers on
  one bus fight. Replace mode also requires the translator's host side on
  the instrument's own supply, measured in range (3.4).

## 2. Coverage: which displays, how, when

Every display type the survey turned up, and how this board handles it.

| Type (study 1.1) | Examples | Lines | Passive | Replace answers | Adapter | Phase |
|---|---|---|---|---|---|---|
| A. HD44780 character LCD, 4- or 8-bit | DX7, M1, D-50, S900, Proteus, CZ-101 | 7-11 | Yes | Busy flag and address counter; RAM read-back from the tool's own copy | Standard 14/16-pin pass-through, 2x7 IDC | 1 |
| A. 40x4 modules with two E strobes (from memory; none found in keyboards) | — | 12 | Yes | Yes | As above | 1 |
| B. HD44780-class icon glass | SX-PR53, HP-535, PSR-140, CTK-811EX | 7-11 | Yes | As A | Pass-through or flying leads | 1 capture; per-model maps in 3 |
| C1. VFD module, HD44780-style | Emulator II, SP-1200, Prophet VS | 7-11 | Yes | As A | As A | 1 |
| C2. Ensoniq serial panel link | ESQ-1, SQ-80, VFX, SD-1, TS-10/12 | 1-2 (3 on EPS/ASR) | Yes | Not needed: the panel's own microcontroller keeps running | Flying leads | 2 |
| E. Serial write-only LCD | MT-32 | 2-3 | Yes | Not needed: write-only | Flying leads | 2 |
| D1. T6963C graphic module | 01/W, Wavestation, K2000, SY77 | 12-14 | Yes | Status before every byte (STA0/STA1, plus STA2/STA3 in auto modes); data read-back from the tool's copy, for firmware that tests or reads display RAM | 20-pin pass-through | 2 |
| D2. SED1335 bare glass | JV-2080, XP-60/80, EX5, RM1x, RS7000 | 7-8 at the panel connector; 12-13 with a clip on the controller chip when the connector can't be reached | Yes | Not needed: the controller stays on the main board | Flat-cable pass-through per pitch, or a chip clip | 2 |
| D2. LC7981 Akais | MPC60, MPC3000, S1000 | 8-12 | Probably: the controller is on the main board, but its scan signals differ from the SED1335's and it has a busy flag. Check on the first one | Not needed at the panel | Unknown until one is opened | 3 |
| KS0108 / SED1520 graphic | None found in period keyboards | 12-14 | Yes | Busy, status, data read-back with the dummy read these chips need | Flying leads | On demand |
| C3. Display-CPU VFDs | JX-8P, JX-10, MKS-70 | 2-4 | After reverse engineering | Model-specific | Flying leads | On demand |
| D3. Custom chipsets | FZ-1 (kit exists), MPC4000 | 8-12 | Model-specific | Model-specific | — | Not planned |
| F. Serial segment drivers, VFD controller chips | None found in keyboards | 3-4 | Yes | I2C ACK, BUSY line, key-scan data (PT6311's data-out is open drain, which the open-drain drivers can do) | Flying leads | On demand |
| G. Direct-drive glass | Cheap keyboards | — | No | No | — | Out of scope |

Sixteen bus lines cover every bus in the table; the widest are KS0108 and
T6963C at 14.

## 3. Hardware

### 3.1 Block diagram

```
                       ┌──────────────────────── board ─────────────────────────────┐
 instrument            │                                                            │
 display bus ──► 26-pin├─► R + clamps ──► SN74LVC16T245 ──────► GP0-15   RP2350B    │
 (via adapter)  keyed  │   100k bias      host side: VREF        (PIO capture,      │
                header │                  tool side: 3V3          read answers)     │
                       │  lines 14, 15 ◄── open-drain pull-downs ◄── 2 GPIO         │
                       │  VCC, V0, AUX ─► dividers ─► ADC (GP40-42)                 │
                       │  adapter ID ───────────────► ADC (GP43)                    │
                       │  VREF switch HOST / 3V3 ──► translator host side ─► ADC 44 │
                       │                                                            │
 USB-C ─► 5 V ─────────┼─► PGA2350 (VB) ─► 3V3        SPI0 ─► 3.5" TFT (480x320)    │
                       │   2nd 3V3 regulator ─► SD, TFT logic    SPI1 ─► microSD    │
                       │   backlight from 5 V         buttons x3, LED, scope trigger│
 (install builds only) │   host 5 V ─► jumper ─► polyfuse ─► ideal diode ─┐         │
                       │   USB 5 V ──────────────────────────► ideal diode ┴─► 5 V  │
                       │   SWD header, test points on GP0-15                        │
                       └────────────────────────────────────────────────────────────┘
```

### 3.2 MCU: one RP2350B instead of two boards

The PR53 uses two RP2350s because a 30-GPIO RP2350A can't drive a 16-bit
parallel TFT and a tap at once. An RP2350B has 48 GPIO and 12 PIO state
machines, and moving the screen to SPI frees most of the pins. One chip
means one firmware, one USB port, lower cost and a smaller board. The split
that mattered in the PR53 (real-time capture versus slow rendering) moves
onto the two cores: core 1 runs capture, the controller model and the read
answers; core 0 runs USB, SD, the screen and the buttons. The PIO programs
keep the bus timing independent of either core.

- **Prototypes: Pimoroni PGA2350.** RP2350B, 16 MB flash and 8 MB PSRAM on a
  2.54 mm pin grid that solders onto the carrier like any through-hole part.
  The PSRAM gives an 8 MB capture buffer for long logs and graphic bursts.
- **Production: RP2350B directly**, with flash and PSRAM, placed by the board
  house, once the design has settled. That's cheaper per unit but means QFN
  assembly and careful flash and USB layout; it's not worth it before the
  prototype has proven the rest.

### 3.3 GPIO budget (RP2350B, 48 GPIO)

| GPIO | Use | Count |
|---|---|---|
| GP0-GP7 | Bus byte 0 (data) through the translator; turned around by the PIO for read answers | 8 |
| GP8-GP15 | Bus byte 1 (control, chip selects, strobes, serial lines); normally input | 8 |
| GP16-GP19 | Translator OE and DIR for each byte, adjacent so the PIO can drive them as side-set pins | 4 |
| GP20-GP21 | Open-drain pull-downs on bus lines 14 and 15 | 2 |
| GP22-GP27 | SPI0 to the TFT (SCK on GP22, MOSI on GP23), CS, DC, RST, backlight PWM | 6 |
| GP28-GP32 | SPI1 to microSD (MISO GP28, CS GP29, SCK GP30, MOSI GP31), card detect | 5 |
| GP33-GP35 | Buttons (up, down, select) | 3 |
| GP36 | Status LED | 1 |
| GP37-GP38 | Spare pair: an extra UART (hardware or PIO) or expansion | 2 |
| GP39 | Scope trigger out: pulses on a diagnostic hit or a pattern match | 1 |
| GP40-GP43 | ADC: instrument VCC, contrast V0, aux analog, adapter ID | 4 |
| GP44 | ADC: the translator's host-side supply (VREF), for the interlock | 1 |
| GP45-GP46 | Spare (ADC-capable) | 2 |
| GP47 | PSRAM chip select (on the PGA2350) | 1 |

That's all 48. GP0-GP15 sit in one PIO pin window, so every front end reads
all 16 lines as one group and any of them can be the strobe. Check every
function against the RP2350B's pin table at schematic time; anything that
doesn't fit moves to a spare or a PIO.

### 3.4 The front end

**Translator: one SN74LVC16T245.** Figures from TI's datasheet (SCES636B):

- Each side runs from 1.65 to 5.5 V. Its I/O pins take up to 6.5 V
  (absolute maximum) whatever the supply, and 0-5.5 V is within the
  recommended conditions on a port whose outputs are off. So a host side
  running at 3.3 V can listen to a 5 V bus.
- Inputs read high above 2.0 V and low below 0.8 V with that side at
  3.0-3.6 V; above 0.7 x VCC and below 0.3 x VCC at 4.5-5.5 V.
- Delays with the tool side at 3.3 V: tool to host at most 4.4 ns (host
  side at 5 V), host to tool at most 6.1 ns (host side at 3.3 V); output
  enable or disable at most about 8.5 ns.
- Drive: 24 mA at 3.3 V, 32 mA at 5 V.
- Both sides go high-impedance if either supply is at 0 V (TI's product
  page); behaviour between 0 V and the 1.65 V minimum isn't specified, so
  firmware never enables outputs there.
- **Unused inputs must not float** (datasheet note), and input edges must be
  no slower than 10 ns/V at 3.3 V (5 ns/V at 5 V). Hence the bias resistors
  below, and a firmware deglitch for slow lines (see 4).

Each 8-bit half has its own OE and DIR. **At power-up and reset, both halves
are off and facing inward:** pull-ups on the OE pins, pulls on the DIR pins.
The data byte turns around under PIO control, always in the order outputs
off, flip DIR, outputs on, and back. The control byte stays input unless a
profile needs to drive a line. 48-pin SSOP (0.635 mm pitch) for hand
soldering, or let the board house place it.

**VREF switch for the host side: HOST or 3V3** (break-before-make, so the
instrument's rail and the tool's 3.3 V are never joined):

- *3V3* is the default for passive mode. Nothing on the board is referenced
  to the instrument, and an instrument that's switched off sees only the
  bias resistors.
- *HOST* follows the instrument's supply through the adapter. Required for
  replace mode: answers then come out at the instrument's levels (a 3.3 V
  answer doesn't meet a 5 V CMOS input's 3.5 V high), and it suits 1.8-2.5 V
  buses.
- **Interlock:** the ADC reads both the instrument's VCC (GP40) and the
  translator's host-side supply (GP44). Firmware enables outputs only in
  replace mode, with the switch on HOST, the host side above 2.7 V and
  within 10% of the instrument's VCC. Otherwise the outputs stay off.

**Read-answer timing.** Counting the input synchronisers and one PIO
instruction (about 20 ns), output enable (at most 8.5 ns), translator delay
(at most 4.4 ns) and the RC of 100 Ω into about 100 pF of host bus, an
answer should be on the bus about 35-45 ns after the CPU's strobe starts.
The tightest windows in the survey: the ST7066 clone gives data 100 ns
(its datasheet), the T6963C 150 ns, the HD44780U 160 ns. The answer value
must already be in the PIO's FIFO; core 1 refreshes it within about 1 µs of
each write, since some hosts poll status straight after writing. Release
takes about 30 ns after the strobe ends; the series resistors limit the
current if the host starts driving its next write sooner. Measure all of
this on the scope at rev A.

**Protection, per bus line:**

- **Series resistor: 100 Ω on every line, the same value on all 16.** A
  bigger resistor on the control lines would protect them better, but it
  would delay the strobes against the data by 10-30 ns, more than the 10 ns
  write hold time the sampling relies on. 100 Ω also keeps read answers
  fast.
- **A Schottky clamp to ground** after the resistor, rated for about
  150 mA (-15 V through 100 Ω), because a flipped 14-pin plug puts a
  negative contrast voltage on a data line, and **a TVS
  with at least 5.5 V standoff** for positive overvoltage. Positive clamps
  must not go to the host-side supply: at 3.3 V they would load a 5 V bus.
  How far above 6.5 V the translator stays protected depends on the TVS
  chosen; design target: survive a flipped plug (5 V or about -15 V on any
  line) indefinitely.
- **100 kΩ bias to ground** on the host side of every line, so unused lines
  don't float. That's 50 µA at 5 V, less than an HD44780's own internal
  pull-ups and harmless on a push-pull bus.
- **Not covered:** VFD grid and anode rails (30-60 V), backlight inverters,
  mains. Adapters must never bring those out, and the manual must say so.

**Two open-drain pull-downs** (small N-MOSFETs) on bus lines 14 and 15, on
the instrument side of the series resistors, for answers a push-pull output
can't give: an I2C ACK, a BUSY or READY line, PT6311-style open-drain key
data. The adapter routes the right signal there. Busy flags on a data line
(HD44780 DB7) don't need them: in replace mode the translator drives the
whole data byte.

### 3.5 Analog inputs

| Input | Range | Why |
|---|---|---|
| Instrument VCC | 0-6 V | Supply sag (the PR53's failed protector would have shown on day one); the interlock |
| Contrast V0 | about -30 to +30 V (offset divider) | A blank display is often a contrast supply fault; graphic LCD bias can run to 20-30 V |
| Aux | as V0 | Backlight supply, VEE, anything else |
| Adapter ID | 0-3.3 V | A resistor on each adapter selects its pin map |
| Translator host side | 0-6 V | The interlock |

About 100 kΩ in series keeps the inputs safe against a slip onto a
higher-voltage rail; a 10-100 nF capacitor at each ADC pin gives the ADC a
low-impedance source. Check divider accuracy at bring-up.

### 3.6 Power

- **USB-C, 5 V.** No power from the instrument in the bench build: the
  adapter's VCC pin only feeds the VREF switch and the ADC.
- **Budget (estimates, measure at rev A):**

  | Load | Rail | Estimate |
  |---|---|---|
  | RP2350B, both cores at 150 MHz | 3V3 (PGA2350) | 30-50 mA |
  | Flash and PSRAM, active | 3V3 (PGA2350) | 20-40 mA |
  | Translator tool side, LED, misc | 3V3 (PGA2350) | about 10 mA |
  | microSD writes | 3V3 (second regulator) | peaks 100-200 mA |
  | TFT logic | 3V3 (second regulator) | about 10 mA |
  | TFT backlight, through a transistor | 5 V | 60-100 mA |

  The SD card's peaks would push the PGA2350's 300 mA regulator too close,
  hence a second 3V3 regulator for the SD card and the TFT logic. The total
  stays under a USB 2.0 port's 500 mA.
- **Install builds:** two ideal diodes into the 5 V rail, one from USB and
  one from the instrument's 5 V (through a jumper and a polyfuse), so neither
  source can feed the other. This carries over the carrier's rule (never
  USB and instrument 5 V tied together) into hardware. Measure the board's
  draw against the old display's own before installing.
- **Boot time:** in an install, the tool powers up with the instrument and
  must answer busy checks within the HD44780's 15-40 ms init window. The
  responder starts first in `main()`; measure power-on to first answer at
  rev A (target under 10 ms).
- **Grounds:** the tool's ground is the instrument's logic ground, the same
  as a scope probe's. If a laptop is connected and the instrument has an odd
  ground (two-prong mains, leaky filters), an inline USB isolator is the
  cheap fix; the tool itself doesn't need isolation.

### 3.7 Connectors and adapters

The tool side is one keyed, shrouded 2x13 header: 16 bus lines, instrument
VCC, V0, aux analog, adapter ID, and six grounds between the signal groups.
Keep adapter cables short (up to about 30 cm). A Y adapter adds a stub to
the instrument's bus: keep the stub short and grounds next to the strobes.

Each adapter is a small PCB or cable with pin 1 marked on both ends, its ID
resistor, and in its documentation a pin-1 and "if flipped" table:

| Adapter | Covers | Notes |
|---|---|---|
| P1: 14/16-pin single-row HD44780 pass-through | Types A, B, C1 with the standard pinout (the PR53's CN1 follows it) | Male and female, so the original display stays connected |
| P2: 2x7 IDC pass-through | HD44780 modules with a dual-row header | |
| P3: 20-pin T6963C pass-through | 01/W, Wavestation, K2000, SY77 family | Check pin 1 per instrument |
| P4: flat-cable pass-through, per pitch | SED1335 panels (JV-2080/XP: 14-way, 1.25 mm, unconfirmed; RM1x: 12-pin) | One board per connector type; build as instruments come in |
| P5: flying leads | Everything else: Ensoniq, MT-32, chip clips, serial drivers | 16 labelled leads with micro-grabbers, VCC, V0, GND |
| P6: replace-mode plug | One per model, for permanent installs | Plugs in where the old display went; no Y |

The firmware's pin map comes from the adapter ID, so an adapter that swaps
two signal lines is a table entry, not a new board. Power pins can't be
fixed in firmware, which is why the tool never sources power on this
connector.

### 3.8 Screen, controls, storage, debug

- **3.5" 480 x 320 SPI TFT** (ST7796S-class, 16-bit colour over SPI). The
  PR53's 16-bit parallel panel would need 19 pins. SPI is slower to fill a
  whole screen, but character and graphic views repaint only what changed.
  A 40x2 fits at 2 px per dot; 240x64 at 2x (480 x 128); 320x80 at 1.5x.
- **Three buttons** for profile, mode and page. A rotary encoder is a
  reasonable alternative.
- **microSD** for logs, profiles and maps. Logs flush at least once a
  second, so pulling the power loses at most a second.
- **Status LED** for mode (passive, replace, error).
- **SWD header** and **test points on GP0-GP15** (the tool side of the
  translator), for debugging the tool itself. **Scope trigger out** on GP39.
- **Laptop view** over USB: a Web Serial page in Chrome (nothing to install),
  plus the existing Python tools reading the same log format.

### 3.9 Enclosure

Design the PCB to the TFT module's outline so the screen sits on standoffs
over the board. That one stack works three ways:

- **Bare:** standoffs and an acrylic top plate. Cheapest; fine for the shop.
- **3D-printed shell** around the stack: screen window and buttons on top,
  the 26-pin header at the front, USB-C and microSD on the sides, a slot for
  the trigger output and a ground post. Good for prototypes and small runs.
- **Extruded aluminium box** with a cut front panel if it sells in volume.

Leave room for the adapter kit in the case or a pouch; the adapters are half
the product.

## 4. Firmware

The architecture is the one in the study (5.2), now on one chip:

- **Core 1, real time:** PIO capture into a DMA ring (in PSRAM for long
  captures), the controller model, and the read-answer feed (status, address
  counter, next data byte, pre-loaded so the PIO answers inside the read
  window).
- **Core 0:** USB (log stream, commands, the Web Serial page's data), SD
  logging, the screen, buttons and diagnostics.
- **Front ends**, built at run time with the strobe GPIO patched in:
  6800-style (E with R/W), 8080-style (/WR and /RD), clocked serial,
  async serial (Ensoniq), I2C, and a panel-scan capture (clock plus 4-bit
  data plus line and frame pulses, straight into a framebuffer).
- **Latch like the chip does:** sample continuously while the strobe is
  active and keep the last sample. For slow open-drain and serial lines, a
  deglitch: a level counts only after it's stable for a set number of
  samples.
- **Translator handling in the PIO:** OE and DIR as side-set pins, in the
  order outputs off, flip DIR, outputs on.
- **Controller models in plain C**, shared with a PC build for tests against
  recorded captures, as `firmware/display/host.mk` already does for the
  PR53.
- **Profiles:** bus family, pin map (from the adapter ID), strobe polarity,
  chip-select levels, width, controller, geometry, character ROM, answer
  level, renderer. Built in at first, then files on the SD card.
- **Renderers:** character grid with the HD44780 character ROMs and CGRAM,
  bitmap for graphic controllers and panel scan, 16-segment for Ensoniq, and
  per-model layouts for custom glass.
- **Diagnostics:** stuck and shorted lines, strobe widths against the
  controller's minimum, writes during busy, init sequence checks, odd nibble
  counts, VCC and V0 against expected ranges. Each can pulse the scope
  trigger.
- **Logs:** a compact binary format, with the PR53's text format kept as an
  option so `tools/` keeps working.

## 5. Phases and effort

Effort in focused days with Claude pairing, my estimate. Board turnaround 1-2
weeks per spin.

| Phase | What | Effort |
|---|---|---|
| 0. De-risk on the v2 carrier | Passive mode, strobe polarity setting, generic HD44780 laptop view, Ensoniq UART decode if one is in the shop. Scope the PR53's strobe. Measure the carrier's current | 3-5 days |
| 1. Rev A board | Schematic and layout (PGA2350, translator, protection, analog inputs, 26-pin header, TFT, SD, buttons, USB-C). Firmware core: capture framework, HD44780 4/8-bit passive and replace, diagnostics, binary log, Web Serial view. Adapters P1, P2, P5 | 2 weeks design, fab, 1 week bring-up, 2-3 weeks firmware |
| 2. Graphic and serial | T6963C (passive and status answers), SED1335 panel scan, Ensoniq, MT-32. Adapters P3, P4 for whatever is in the shop | 4-6 weeks |
| 3. Rev B and enclosure | Fixes from rev A, the enclosure, LC7981, per-model maps for icon glass as jobs bring them | 2-3 weeks plus per-model work |
| 4. Product | Small batch (10-25), assembled boards, adapter kits, a manual with the safety notes, support | Decide once rev A has been used on real jobs |

## 6. Cost (rough, from memory)

| Item | Estimate per unit, small batch |
|---|---|
| PGA2350 | US$10-15 |
| Translator, clamps, TVS arrays, MOSFETs, regulators, ideal diodes, passives, connectors, microSD socket, USB-C | US$10-15 |
| PCB, small batch | US$2-5 |
| 3.5" SPI TFT | US$10-15 |
| Enclosure (printed) | US$5-10 |
| Adapter kit (P1, P2, P3, P5) | US$10-20 |
| **Total parts** | **about US$50-80** |

Moving to a bare RP2350B saves most of the PGA2350's cost at the price of
assembly setup. For comparison (from memory): cheap 8-channel logic analyzers
cost US$10-20 and show waveforms, not displays; Saleae's cost hundreds. No
tool found in the research does what this one does: the closest are one-off
projects (DoMSnif for KS0108, LCDJunoG for one Roland) and per-model
replacement kits.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Read answers too slow for the fastest controllers | Pre-loaded answers, about 35-45 ns estimated against a 100 ns tightest window; measure at rev A. Passive mode isn't affected |
| Replace mode with the original controller still connected | The mode rule (1), and the interlock |
| A wrong clip onto a high-voltage line | Adapters never bring out VFD or backlight rails; clamps and TVS for flipped plugs; the manual. The analog inputs survive more than the bus lines |
| Connecting a tool wipes a customer's memory (the PR53 reset itself once with its front panel unplugged) | The manual's first step: back up user data where the instrument can |
| Instrument connectors vary endlessly | Flying-lead adapter P5 as the fallback; build pass-through adapters only for repeat models |
| Slow edges on open-drain or long lines | Firmware deglitch; keep adapter cables short |
| RP2350 erratum E9 on A2 parts | No reliance on internal pull-downs; check the stepping on the modules bought |
| Unknown demand | Phase 0 and the shop's own jobs decide whether phases 3-4 happen |

## 8. Decisions for Greg

1. **PGA2350 for the prototype, or straight to a bare RP2350B?** PGA2350
   recommended: hand-solderable, PSRAM included.
2. **Built-in screen, or a cheaper laptop-only version?** Recommended: design
   for the screen, keep the laptop view working without it.
3. **Open or closed?** This repo is MIT and public. Open hardware sold as
   kits or assembled boards is one route; keeping the product files private
   is another. Either way, this plan sits in a branch of that public repo,
   so decide before the branch is pushed.
4. **What after HD44780?** For the tool, recommended by shop value: SED1335
   panel scan and the Ensoniq link (no replacements exist), then T6963C
   (diagnosis). For products, per-model replacement displays for icon glass
   (the PR53 family first) use the same board as a bare core.
