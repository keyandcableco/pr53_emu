# Could the PR53 tap become a general display sniffer?

A feasibility study for Greg at Key & Cable, 2026-10-31. It asks whether the
SX-PR53's tap and display pair (an RP2350-Zero tapping the piano's HD44780
bus, a Pico 2 drawing on a 3.5" TFT, both on the carrier v2) could sniff and
redraw other vintage keyboards' displays, as a repair tool or a product.
Inputs: this repo (tap firmware v16, carrier v2 and its bring-up notes, the
captures) and web research into service manuals, MAME's driver source,
controller datasheets and repair forums.

## Not verified: confirm before relying on it

- **Nothing here is ready to order.** The v3 parts in 5.1 (SN74LVC16T245 and
  the rest) come from the maker's product page only; footprint, stock and
  price aren't checked.
- **RP2350 5 V tolerance** rests on news coverage of the A4 stepping and on
  forum readings of the datasheet. The datasheet itself was too large for the
  fetch tool. Which stepping Greg's Zero and Pico 2 carry isn't known.
- **The PR53's CS strobe polarity** is inferred from the PIO code, never
  measured (2.1).
- **The carrier's current draw** has never been measured.
- **Instrument rows** in 1.1 lean on MAME source and forums in many places;
  connector pinouts are mostly unknown and model years are mostly from
  memory. Each row says what its evidence is.
- **Shares in 1.2 and the effort figures in 5.3 are judgement**, not data.
- **Calculated, not measured:** the SED1335 panel pixel clock (2.2) and the
  BSS138 edge behaviour (2.2, 5.1).
- What rests only on training data is listed at the end.

## Short answer

- **Yes for the HD44780 family**, which is the biggest group: ordinary
  character LCDs (type A in section 1) and, the surprise, the icon-style
  displays of arrangers and digital pianos (type B): every one whose service
  manual could be read runs from the same kind of controller as the PR53. The
  v2 board has only been proven on the PR53. It should capture other 4-bit
  HD44780 buses on 5 V hosts once firmware handles strobe polarity, passive
  use and generic rendering; 8-bit and fast memory-mapped buses need a new
  front end (16 channels, a fast translator, no pull-ups).
- **Partly for graphic LCDs.** Each controller is its own job. The most
  useful case, the SED1335 instruments with bare glass (JV-2080, XP-60/80,
  EX5, RM1x), can be captured from the panel's scan signals without
  answering anything; the LC7981 Akais may work the same way (not checked).
- **Smaller jobs outside the HD44780 family:** Ensoniq's serial panel link (one
  wire at 62,500 baud on the VFX family; MAME models the ESQ-1, VFX, SD-1, TS
  and MR panels with one device) and the MT-32's
  write-only serial LCD.
- **Out of reach:** glass driven directly by the main CPU, where there's no
  bus to tap.
- **Where it pays.** In the shop: diagnosis ("is it the display or the
  board?") and a stand-in display, for instance to get a customer's patches
  out of an instrument whose display has died. A standard 16x2 or 40x2 is
  cheaper to replace with a new module than to sniff. As a product:
  replacement displays for the families nothing else serves (custom icon
  glass, Ensoniq VFDs, SED1335 glass).
- **Next step:** two or three days of firmware on the v2 board, tried on the
  next suitable instrument (5.3, stage 0), then decide.

## 1. What keyboards of 1980-2005 actually use

Evidence comes from service manuals on archive.org (read as OCR text), MAME's
driver source (which states how each machine's LCD is wired; reverse
engineered, so good but secondary), controller datasheets, and repair forums.
Rows say which. Model years are from memory unless a manual gave them.

### 1.1 The types, with examples

| Type | How the CPU reaches it | Examples (evidence) | Off-the-shelf replacement? |
|---|---|---|---|
| **A. HD44780-family character LCD** (Hitachi, or clones: KS0066, ST7066, SED1278, OKI MSM6222B), 16x1 to 40x2, one 4x20 | 4- or 8-bit parallel with RS, R/W, E. Three ways in: memory-mapped on the CPU bus, driven from port pins, or behind a gate array. At the module connector they all look the same | Yamaha DX7 (16x2, via an 8255 PPI), DX9, DX100, TX81Z, DX11, FB-01 (memory-mapped), DX7II and TX802 (40x2) [MAME, forum]. Korg M1 (40x2, port-driven through a CXD1095: data on port D, RS/RW/E on port E) [service manual, MAME], DS-8 (40x2), DSS-1, 05R/W (16x2), Prophecy (40x2) [service manuals]. Roland D-50/D-550 (40x2, EL backlight), D-110 (16x2, MSM6222B behind a gate array), JV-880 (24x2, memory-mapped), JV-80, JV-1080, XP-30 and XP-50 (40x2), Alpha Juno (1x16) [service notes, MAME]. Casio CZ-101 and CZ-1 (16x2, 8-bit, port-driven) [service manual, MAME]. Akai S900/S950 (40x2, Optrex DMC40218UE) [service notes]. E-mu Emax, Proteus family (16x2), Emulator III (4x20) [MAME]. Kurzweil K1000/K1200 (16x2) [vendor]. Access Virus (4-bit), Alesis HR-16/MMT-8, Kawai R-100 [MAME] | Yes, for most: standard 16x2/40x2 LCD or OLED modules, sometimes with an adapter for 14-pin vs 16-pin connectors, backlight pins or thickness [forum: DX/TX/TG, CZ, D-550; Kurzweil adapter PCB] |
| **B. HD44780-class controller behind custom icon glass** (the PR53 architecture) | Same bus as A. The glass's icons, meters and shaped labels come from CGRAM or from a segment extender the controller drives itself, so the CPU bus still carries plain HD44780 traffic | Technics SX-PR53 (this repo). Roland HP-535 ("large custom LCD", SED1278F0A plus an NJU6417 segment extender), Yamaha PSR-140 (KS0076B/KS0066U), PSR-C200 (NT3881D), Casio CTK-811EX (SED1278F2A, 4-bit, 10-pin connector: DG, VCC, CONT, LRS, LR/W, LE, DB4-DB7), Casio LD-50 (S6A0069, DB0-DB3 grounded) [service manuals; only the HP-535 manual calls the glass custom] | No. Custom glass is model-specific |
| **C1. Character VFD module with an HD44780-style parallel interface** | As A | E-mu Emulator II, SP-12/SP-1200, Sequential Prophet VS, Studio 440 (Noritake 2x16) [forum, search snippets only] | Yes: Noritake CU-U series modules use the HD44780 command set [Noritake] |
| **C2. Bare VFD glass behind a front-panel microcontroller, serial link from the main board** | Serial. VFX family: async 62,500 baud, main board to panel for display bytes and panel to main board for keys [MAME]. EPS-16+ and ASR: through the keyboard assembly, then a synchronous 3-line link to the display board [service manual] | All Ensoniq: ESQ-1, SQ-80, VFX, VFX-SD, SD-1, EPS, EPS-16+, ASR-10, TS-10/12, KT, MR (2x40 or 22-character VFD); SQ-1/SQ-2/KS-32 use a 2x16 LCD the same way [service manuals, MAME]. MAME runs the VFX-family panel link at 62,500 baud, 8N2, and documents the display byte codes | No. NOS NEC FIP80B5R glass only, rare and expensive [forum]. One unfinished hobby project decodes the EPS-16+ stream ([ensoniqdisplay](https://github.com/balamutang/ensoniqdisplay)) |
| **C3. VFD behind a dedicated display CPU with a private protocol** | Model-specific | Roland JX-8P (uPD7537 "display 4-bit CPU", FIP16A5R), JX-10 / MKS-70 (uPD7538A plus a uPD6300C latch driver) [service notes]. Oberheim Matrix-12/Xpander and Akai AX-80 custom VFDs [forum] | No |
| **D1. Graphic LCD, controller on the module** (Toshiba T6963C and clones), 240x64 | 8-bit 8080-style bus (/WR, /RD, /CE, C/D) on a 20-pin ribbon | Korg 01/W (Optrex DMF5005NS-EW1, T6963C pin set) [service manual], Wavestation (same display per a Korg tech) [forum], Kurzweil K2000 (20-pin ribbon, EL backlight; T6963 per forum) [service manual, forum], Yamaha SY77, SY99, TG77 (T6963C modules work as replacements) [service manual, forum], Roland D-70 (T6963C) [MAME] | Yes: 240x64 T6963C/RA6963 modules are still sold (Newhaven NHD-24064WG-ATMI-VZ#, BuyDisplay ERM24064 series) and there are kits for the TG77 family [vendor] |
| **D2. Graphic LCD, controller on the main board, glass gets raw scan signals** | CPU to controller on the main board; the panel connector carries 4-bit pixel data and clocks (XD0-XD3, XSCL, LP, YD, WF) | Epson SED1335F0B: Roland JV-2080, XP-60, XP-80 (320x80; XP-80's Sharp LCM32080YGV glass) [service notes], Yamaha EX5, RM1x (240x64, 12-pin connector) [service manual, forum], RS7000 [forum]. Sanyo LC7981 on the main board: Akai MPC60, MPC3000, S1000HD, VX600 [service manuals; that the glass has no controller is a forum snippet, and its scan signals differ from the SED1335's] | No generic one: the RM1x thread found no controller-less 240x64 replacement [forum] |
| **D3. Graphic LCD on a custom chipset or a raw pixel bus** | Model-specific | Casio FZ-1/FZ-10M/FZ-20M (96x64, HD44350 plus two HD44351, nibble stream through a GAL), Akai MPC4000 (320x240, pixel bus from the CPU) [service notes, buchty.net] | FZ-1: a commercial OLED kit exists (EMW, about US$249) |
| **E. Serial write-only character LCD** | Clocked serial | Roland MT-32 (20-character LCD, SED1200-type with an M5238 on the main board; the LCD's /RD is pulled high, so nothing is ever read) [service notes, MAME] | No |
| **F. Serial segment/icon drivers** (NEC uPD7225, PCF8576 on I2C, Sanyo LC75xxx on CCB, Holtek HT1621) and **VFD controller chips** (uPD16311/16312, PT6311, M66004) | 3-4 wire serial or I2C, 0.3-3 MHz | None found in any keyboard this research could read. The datasheets are well documented, so they'd be quick to support if one turns up | n/a |
| **G. Glass driven directly by the main CPU or a custom LSI** | No bus: multiplexed segment and common lines at several voltage levels | Casio VL-1 family (NEC D1867G) [forum]. Probably common in entry-level keyboards (judgement) | No |

Two findings change the usual picture:

- **Icon-style displays mostly use the PR53's own architecture.** Every
  icon-style LCD whose service manual could be read (HP-535, PSR-140,
  PSR-C200, CTK-811EX, LD-50) runs from an HD44780-class controller on the
  CPU bus. That's five manuals plus the PR53, and only the HP-535's says the
  glass is custom, so treat it as a strong lead rather than a census.
  The separate serial segment drivers (uPD7225, PCF8576 and the like) didn't
  show up in any keyboard.
- **The interesting graphic cases aren't the T6963C ones.** T6963C modules are
  still made, so those instruments can be fixed with a new module. The
  SED1335 instruments put the controller on the main board and send raw scan
  signals to bare glass (the LC7981 Akais probably do the same), and nothing
  off the shelf replaces that glass.

### 1.2 How common in the shop

There are no counts behind this; it's judgement from the survey and from
which displays have long repair threads. The best data would be Greg's own:
note the display controller on the next 30 jobs.

| Type | Share of display-related jobs (judgement) | Why |
|---|---|---|
| A. HD44780 character LCD | Large: most pro synths, samplers and drum machines 1983-1995 | The default 2-line display of the era. Usually fixed with a new module, so the sniffer's role here is diagnosis |
| B. HD44780-class custom icon glass | Large in arrangers and digital pianos 1990-2005 (Technics SX-PR/KN, Yamaha PSR, Roland HP/KR, Casio CTK) | Exactly where a dead display has no replacement part. The PR53 is one of these |
| D1/D2/D3. Graphic | Small by count, high by value: workstations and samplers 1988-2005 | EL backlight and glass-bond failures are common and the instruments are worth fixing |
| C2. Ensoniq serial VFD | Small but loyal; a big family on related protocols | VFDs wear out and there's no replacement glass |
| C1, C3, E | Small | Particular models only. The MT-32 is the most common of them |
| F. Serial segment drivers | Rare in keyboards (none found) | More common in car radios and appliances |
| G. Direct drive | Common in cheap keyboards | Rarely worth a display repair |

## 2. What the current board and firmware can do with each type

### 2.1 How the v2 tap actually works

These facts come from `firmware/tap/src/pr53_emu.c` and
`hardware/carrier/gen_board.py`. They decide what carries over.

| Part | What it does today | What that means for other instruments |
|---|---|---|
| Inputs | DB4-DB7 on GP0-GP3, RS on GP4, R/W on GP5, CS on GP7. DB0-DB3 aren't wired (the PR53 ties DB0-DB2 to ground). | 4-bit HD44780 only. 7 of the 8 shifter channels are used; one is spare. |
| Capture (PIO0) | Waits for CS to go high then low, waits 32 cycles (213 ns at 150 MHz), skips the cycle if R/W is high, then samples DB4-DB7, RS and R/W. With the input synchronisers the sample lands about 230-240 ns after CS falls at the pin. | Fixed strobe pin (the program has `wait pin 7` hard-coded relative to GP0), fixed polarity, fixed sample point. |
| Read answers (PIO1) | On every read cycle it drives DB4-DB7 with busy = 0 and the address counter, from CS falling until CS rises, for both nibbles. RS is ignored, so a data read gets the address counter too. | Right for HD44780 busy polling. Wrong for anything that reads data back, and wrong for controllers whose status bits mean "ready" when high (T6963C). It can't be switched off, so it fights a working display that's still connected. |
| Byte assembly (core 1) | Pairs nibbles by count: first nibble is the high half, second the low half. Tracks the address counter from the writes. | No resync. One lost or extra nibble swaps halves for every byte after it. Works on the PR53 because the tap is running before the piano starts and its init sequence has an even nibble count. |
| Buffer | 2048 events in RAM. | Plenty for character LCDs; a graphic LCD redraw is about 2000 writes in one burst. |
| USB log | One text line per write, about 30-60 bytes (median 29-38 in the two captures). | Readable and tool-friendly. Too fat for graphic LCD traffic. |
| Display link | uart1 at 1 Mbaud, 2 bytes per write, sent from the main loop as it drains the ring (one `printf` per event), only if the UART FIFO is empty, else skipped. | Works on the PR53, but losses have never been measured: `drops=` counts the ring, not the link. Bus writes are well spaced (in the start-up and LCD-test captures at least 33 µs apart, median 45-53 µs, at most 23 in a millisecond), but a USB stall builds a backlog that then drains faster than the link, and those sends are skipped silently. The display side doesn't resync: `DISP_CTRL 0x0C` only publishes a frame, so a skipped byte stays wrong until the piano rewrites that cell, and a skipped address command misplaces what follows. A general tool needs a lossless link. |
| Start-up | Waits up to 3 s for a USB host before it starts the PIO programs. | The host CPU's busy checks go unanswered for 3 s when there's no USB. |
| Pull-downs | Enables the RP2350's internal pull-downs on DB4-DB7. | On A2-stepping RP2350s these can latch at about 2.1 V (erratum E9, see 3.1). On the carrier the shifters' pull-ups override them anyway. |
| Level shifting | Two BSS138 modules, HV side on the board's +5 V rail, LV side on the Zero's 3.3 V. Each module has 10 kΩ pull-ups. | 5 V hosts only, slow edges (pull-up driven), and the pull-ups load every bus line. See 3.1 and 5.1. |

One thing I couldn't settle: **which way the PR53's strobe goes.** The
service manual calls CN1 pin 6 "CS"; `docs/piano-interface.md` calls it the
HD44780 E strobe, and CN1 follows the standard 14-pin pinout where pin 6 is
E. A textbook E is high during the access, and the controller latches the
data as E falls; the CPU only has to hold it 10 ns after. Both PIO programs
instead treat "CS low" as the access: capture samples after CS falls, and the
read answer is driven from CS falling until CS rises. Two readings:

- **CS is a normal active-high E.** Then capture works only because the
  PR53's CPU keeps the data on its port pins long after the strobe, and the
  read answer is driven *between* strobes, not while the CPU reads. It would
  reach the CPU only as charge left on the bus when the next strobe starts,
  which is fragile with the shifters' pull-ups and R1 pulling the line
  towards 2.5 V.
- **CS is active low** (the strobe idles high and pulses low). Then both
  programs line up with the access and the busy answer is clean, which fits
  how reliably the piano runs.

One scope shot of CS and DB7 during a busy read settles it. A general tool
needs strobe polarity and sample point as settings either way.

### 2.2 Interface by interface

"As-is" means the v2 carrier and v16 tap firmware unchanged (apart from
pointing the laptop viewer at a different geometry).

| Interface (type from 1.1) | As-is | Firmware changes | Hardware changes |
|---|---|---|---|
| HD44780-family, 4-bit, port-driven, 5 V (A, B: the PR53, CTK-811EX, LD-50, Access Virus) | Capture and busy answers work, if the strobe polarity and sample point match the PR53's and the tap starts before the host. Laptop view works once the geometry is changed; the TFT renderer is PR53-only | Passive mode (responder off) before using it on a working display. Responder first at boot. Pairing resync. Generic renderer | None, if DB4-DB7 come out on the connector |
| HD44780-family, 8-bit (A: DX7, M1, CZ-101, most 40x2 instruments) | No: DB0-DB3 aren't wired, and the capture pairs nibbles | 8-bit capture without pairing; 8-bit read answers | 4 more input channels (one spare today) |
| HD44780-family on a fast memory-mapped bus (A: TX81Z, DX11, Emax, Proteus, S900, JV-880) | Unlikely. At 5 V the HD44780U allows a 500 ns E cycle with a 230 ns pulse, the ST7066 clone 400 ns and 150 ns, and write data need only be held 10 ns after E falls. Sampling 213 ns after the edge misses that | Sample while the strobe is active and keep the last sample (5.2) | Fast buffers instead of BSS138 modules, whose pull-up driven rising edges are slow and skew data against the strobe |
| HD44780 behind a gate array (A: D-110, Alpha Juno) | As the rows above: at the module connector it's ordinary HD44780 timing, set by the gate array | As above | As above |
| Character VFD modules with HD44780-style parallel (C1) | As the HD44780 rows | Extra commands (brightness); writes can come closer together | As the HD44780 rows |
| HD44780-class controller behind custom icon glass (B) | Capture yes, as the HD44780 rows | Per-model map from CGRAM bits and DDRAM to icons and segments, done the PR53 way with the campaign tools | As the HD44780 rows |
| Ensoniq serial panel link (C2) | Hardware yes: on the VFX family one input line (main board to panel) at 62,500 baud. It can go through U2's spare channel, which isn't connected on either side today (two bodge wires), to a free GPIO such as GP6, received with a PIO UART (GP6 has no hardware UART). The EPS and ASR route display data differently (a synchronous link to the display board), so check per model. Firmware no | UART receive on that line, the Ensoniq display byte codes (documented in MAME's `esqvfd.cpp`), a 16-segment glyph renderer. Nothing to answer: the panel's own microcontroller keeps running and keeps scanning the keys | None for a tap; a replacement needs a display that fits the 2x40 window |
| Display CPU with a private protocol (C3: JX-8P, JX-10) | No | Reverse-engineer each model's link | Model-specific |
| Serial write-only LCD (E: MT-32) | No | Clocked-serial front end and an SED1200-type model. Write-only, so nothing to answer | 2-3 lines, fits v2 |
| T6963C module (D1) | No, and the v2 responder would hang a host with the module removed: it answers 0s, and T6963C status bits mean "ready" when high | 8080-style front end (/WR, /RD, /CE, C/D); model with text, graphic and CG areas and the auto modes. In replacement mode, status answers (STA0 and STA1 = 1 before every byte) within the 150 ns access time. New T6963C modules exist, so the main use is passive diagnosis | 12 lines |
| SED1335 controller on the main board (D2; the LC7981 Akais are similar but unchecked, and the LC7981 does have a busy flag) | No | Two ways in. (1) The panel connector's scan signals (on the SED1335: XD0-XD3, XSCL, LP, YD, WF): capture pixels directly into a framebuffer, no controller model, fully passive. (2) The CPU-to-controller bus on the main board (clip on the controller chip): the SED1335 has no busy flag and needs no handshake, so passive capture is enough there too, with a model of its layers and up to 64 KB of display RAM | (1) About 7 lines at 5 V; the pixel clock is low (my estimate: about 0.5 MHz for 320x80 at 70 Hz, 4 pixels per clock). (2) 12 lines and a chip clip |
| KS0108 / HD61202, SED1520 / SED15xx graphic | No | Front end with chip selects, model, bitmap renderer; in replacement mode, busy answers and data read-back with the dummy read these chips need after an address change. None found in a keyboard of the period (the 2006 Roland Juno-G uses KS0713-type chips, per [LCDJunoG](https://github.com/dpeddi/LCDJunoG)) | 12-14 lines |
| Custom chipsets (D3: FZ-1, MPC4000) | No | Model-specific. The FZ-1 already has a commercial OLED kit | Model-specific |
| Serial segment drivers and VFD controller chips (F) | No | Serial or I2C front ends and per-chip RAM models are quick (3-4 lines, at most about 3 MHz). Replacement mode would need I2C ACKs, the uPD7225's BUSY line, or the key-scan data some VFD chips (PT6311) return. None found in keyboards, so build only if one turns up | 3-4 lines fit v2 at low clock rates |
| Direct drive (G) | No: there's no bus, only multiplexed segment and common lines at several voltage levels | Out of scope | A different instrument: analog capture on 10-30 lines |

## 3. What the bring-up problems mean for a general tool

### 3.1 The DB7 pull-down and the shifter pull-ups

On the PR53 the pull-down only has to hold DB7 low while nothing answers the
busy check. On the carrier it can't: each BSS138 module carries its own 10 kΩ
pull-ups, so R1 (10 kΩ) holds DB7 at about half of 5 V. It works because the
tap is already answering when the piano starts.

For a general tool the lesson is wider: **every resistor the tool puts on the
host's bus is a guess about the host.**

- In **passive mode** (the original display still connected and working) the
  tool must add nothing: no pull-downs, no pull-ups, no read answers. The real
  controller drives the bus, and an HD44780's data outputs are weak (the
  HD44780U datasheet guarantees 2.4 V only at 0.205 mA sourced, 0.4 V at
  1.2 mA sunk), so a 10 kΩ pull-down plus a 10 kΩ pull-up is a real load.
  Worse, the v2 read responder can't be turned off. The BSS138 circuit pulls
  a 5 V line low through its transistor but lets it rise only through a
  10 kΩ pull-up, so when the tap and a real controller disagree the tap wins
  every low and loses every high: the CPU reads the AND of the two. On a live
  display it could see "not busy" while the real controller is still busy
  and write too early. That is, the tool could cause the very corruption
  you're trying to diagnose.
- In **replacement mode** (original display dead or removed) the busy line
  needs a defined low until the tool answers, and the tool should answer
  within milliseconds of power-up so the pull-down hardly matters.
- So a v3 front end should be high-impedance (no pull-ups), with the
  busy-line pull-down switchable (jumper or a GPIO-controlled MOSFET) and set
  by the target profile.
- Don't lean on the RP2350's internal pull-downs. On A2-stepping chips
  (erratum RP2350-E9) an input with the internal pull-down enabled can latch
  at about 2.1-2.2 V instead of reading low; Raspberry Pi's workaround is an
  external pull-down of 8.2 kΩ or less
  ([Hackaday](https://hackaday.com/2024/09/04/the-worsening-raspberry-pi-rp2350-e9-erratum-situation/),
  [Hackster](https://hackster.io/news/a-surprise-hardware-bug-in-raspberry-pi-s-rp2350-leads-to-unexpected-pull-down-behavior-76b51ec22ede)).
  The A4 stepping fixes E9
  ([CNX Software, 2025-07-29](https://www.cnx-software.com/?p=154587)).
  Which stepping is on Greg's Zero and Pico 2 isn't recorded; the chip marking
  says.

### 3.2 Power from the host

The PR53's 5 V feed to the display went through a 0.4 A IC protector that
also fed the front panel, and it had failed open. In a repair shop the host's
supply is a suspect, not a resource. For a general tool:

- **Bench and diagnostic use: power the tool from USB, never from the host.**
  Take only the host's logic supply as a voltage reference for the level
  translator (microamps) and measure it with an ADC through a divider. The
  tool would then have reported "host 5 V reads 3.0 V and sags" on the first
  day, which is itself a diagnosis.
- **No back-feeding.** On the v2 carrier the shifters' HV side and their 10 kΩ
  pull-ups sit on the board's own +5 V. Run from USB with D1 bridged and the
  piano off, that rail pulls every bus line of an unpowered host up through
  10 kΩ. The v3 translator should run its host side from the host's own
  supply, so an unpowered host sees nothing (the SN74LVC16T245 below puts
  both ports in high impedance when either supply is at 0 V).
- **Replacement mode** is the only time the tool runs from the instrument. The
  budget is what the old display drew, backlight included, so measure that
  before taking the old display out, and measure the tool (the carrier's draw
  still hasn't been measured).

### 3.3 Ribbon orientation

The display-side ribbon mirrored odd and even pins until J2 moved to the
underside. The host side of a general tool has the same trap many times over:
1x14 and 1x16 headers, 2x7 and 2x8 IDC ribbons that can be flipped, FFCs that
can be contacts-up or contacts-down. A pin map in firmware can fix swapped
signal lines but not swapped power pins. So:

- The tool never sources power on the host connector, and every host line goes
  through a series resistor into a translator with partial-power-down
  protection, so a wrong-way plug can't hurt either side.
- Each target family gets a small keyed adapter (cable or board) to one fixed
  tool connector, with pin 1 marked on both ends. The adapter can carry an ID
  (a resistor code or a small EEPROM) so the firmware picks the right pin map.
- For passive mode the adapter is a pass-through (Y), so the original display
  stays plugged in.
- On the display side, v3 mirrors J2's pin order or mounts the TFT directly.

### 3.4 The 3 s USB wait

The tap waits up to 3 s for a USB host before it starts capturing and
answering reads. On the PR53 that only works because the tap is usually
powered first. In replacement mode the host CPU and the tool power up
together, and the HD44780 datasheet lets the CPU start its init 15 ms after
the supply reaches 4.5 V (40 ms after 2.7 V); busy checks follow straight
after the first few commands. So the read responder has to be the first thing
`main()` starts, before USB. In passive mode it doesn't matter for the host,
but capture should still start first: the nibble pairing has no resync, so a
tap that starts mid-stream can stay misaligned (5.2 covers resync).

### 3.5 Smaller lessons

- **The panel only initialises at boot.** Fine in a fixed install; a bench
  tool should re-initialise the TFT on demand or periodically.
- **Unpowered front panel → "ALL INITIAL".** The PR53 reset its stored settings
  when it started with the front panel unpowered. Connecting a tool, or
  starting an instrument with something disconnected, can wipe a customer's
  user memory. Where an instrument can dump its memory (SysEx, disk, card),
  back it up before connecting anything.

## 4. Output options

| Output | What it gives | State today | Work to generalize | Best for |
|---|---|---|---|---|
| USB event log + laptop mock display | Every write, time-stamped; a live picture of the display on a laptop | Works. Text log; `pr53_display.py` has a generic HD44780 model and CGRAM glyph drawing, but the layout is the PR53's | Generic N x M character view with CGRAM and the right character ROM (HD44780 A00 Japanese or A02 European). A compact binary log mode for graphic LCDs. A Web Serial page in Chrome would save installing Python on a shop laptop. | Diagnosis, reverse engineering, recording |
| Generic on-board TFT renderer | The display on the bench with no laptop | PR53-only renderer (`pr53_render.c`). The font and panel driver are reusable; the HD44780 emulation is a start, but it always increments the address (entry-mode direction is stored, never used) and ignores display shift and function set | Character-grid renderer with CGROM and CGRAM; bitmap renderer for graphic controllers. On the 480 x 320 panel a 40x2 fits at 2 px per dot (12 px per character cell), 240x64 graphics at 2x (480 x 128), 256x64 only below 2x, 320x240 only at 1x | Bench use, a temporary display while parts are on order |
| SD logging | Hours of unattended capture to catch intermittent faults | None. The HiLetgo panel has an SD slot on pins 23-34, currently left open | Log on the tap, or make the link lossless first: the display Pico only sees what the lossy link delivers. Binary format, files rolled by time, markers when something odd happens (dropped events, timing violations, host supply dips) | Intermittent faults, "it only does it after an hour" |
| Replacement display (PR53 mode) | A permanent display in the instrument | Works for the PR53 | Read answers from power-on, a power budget from the host, mechanical fit, and for custom glass a per-model segment map and layout | Instruments whose glass is custom or unobtainable |

Two notes on the replacement mode:

- **For standard character LCDs it's the wrong tool.** A new 16x2 or 40x2
  LCD or OLED module with an HD44780-compatible controller costs little and
  fits the bezel. The sniffer route earns its keep where nothing else
  exists: custom icon glass on an HD44780-class bus (type B, the PR53),
  Ensoniq's serial-linked VFDs (C2), and controller-less graphic glass on the
  SED1335 and LC7981 instruments (D2).
- **The aspect ratio rarely matches.** A 40x2 window is about 10:1, the 3.5"
  TFT 3:2. Bar-format TFTs exist for that shape; check the bezel before
  promising a fit.

## 5. Recommended path

### 5.1 What a v3 "universal" board would change

Keep what worked: two RP2350 modules (tap and display), the PIO capture, the
UART link, the HiLetgo panel. Change the front end, power and connectors.

| Area | v2 carrier | v3 proposal | Why |
|---|---|---|---|
| Channels | 8 (7 used), 4-bit HD44780 only | 16 host lines: 8 data + 8 control (RS/A0/D-I, R/W or /WR, E or /RD, CS1, CS2, CS3, /RST, spare) | Covers 8-bit HD44780, KS0108 (3 chip selects on 192-wide panels), SED15xx, T6963C, SED1330, and 3-4 wire serial drivers on the same pins |
| Level translation | 2 x BSS138 modules, pull-up driven edges, 10 kΩ on every line, HV fixed at the board's 5 V | 1 x SN74LVC16T245 (16-bit, each side 1.65-5.5 V, 4.3 ns, partial-power-down, both ports high-impedance if either supply is at 0 V, [TI](https://www.ti.com/product/SN74LVC16T245)). Host side powered from the host's own logic supply. Control byte fixed host-to-tap; data byte's direction driven by the PIO, so read answers are timed by the same program that sees the strobe | Fast, symmetric edges; no pull-ups on the host bus; works on 3.3 V and 5 V hosts; an unpowered host is never driven |
| Busy pull-down | Fixed 10 kΩ, fighting the module pull-ups | Switchable (jumper or MOSFET), about 4.7 kΩ, only in replacement mode. Plus an open-drain transistor on the busy line for busy-only answers: the translator can only turn a whole byte around | Section 3.1 |
| Host power | +5 V from the host feeds everything | Tool runs from USB (or a separate 5 V input). Host supply only sensed: translator reference plus an ADC divider. A deliberate jumper, through a polyfuse and an ideal diode, for replacement installs | Section 3.2 |
| Host connector | 9-way screw terminal | One keyed 2x10 header to small per-target adapters (1x14/1x16 HD44780 standard pinout, 2x7, 2x8, FFC pass-through, clip leads), with an ID resistor or EEPROM on the adapter. Series resistors on every line | Section 3.3. The PR53's CN1 already follows the standard 14-pin HD44780 pinout, so that adapter covers many instruments |
| Tap GPIO | GP0-GP8 on the Zero's socketed edge | GP0-GP15 contiguous. On the Zero GP9-GP13 sit on the unsocketed bottom edge (`hardware/carrier/gen_footprints.py`), so either solder the Zero down / socket that edge too, or move the tap to a Pico 2 (GP0-GP22 along its edges) | PIO reads one contiguous pin group |
| Display side | J2 on top mirrors the ribbon | Mirror J2's pin order or mount the TFT on the board; wire the panel's SD slot to spare Pico pins (GP19, GP20, GP22, GP26-GP28 are free; not checked against the SPI pin options) | Section 3.3, SD logging |
| Status | Power LED | Status LED per mode (passive / replacement / error) and a mode button | A bench tool needs to say what it's doing |

The cheaper alternative to a translator is the RP2350's own 5 V tolerance.
Coverage of the A4 stepping lists 5 V-tolerant GPIOs, only while the chip is
powered (whether A2 parts are covered too is for the datasheet) ([CNX Software](https://www.cnx-software.com/?p=154587),
[The Register](https://www.theregister.com/2025/07/29/raspberry_pi_rp2350_update/));
forum readings of the datasheet put the limit at 5.5 V with IOVDD at 3.3 V
and exclude the ADC pins (GP26-GP29 on these boards). That would let a
passive-only tool wire host lines through series resistors straight to the
pins. It's not my pick for a general tool: a host can be on while the tool is
off, the 3.3 V highs don't meet 5 V CMOS input levels when answering reads,
and Greg's boards may be A2 parts. Worth confirming in the datasheet's
electrical section before anyone relies on it.

### 5.2 Firmware architecture for configurable targets

```
 host bus ──► front end (PIO) ──► raw events ──► controller model ──► display state ──► sinks
              par6800 / par8080      ring        HD44780, KS0108,     char grid +       USB log
              4/8-bit, serial,       buffer      SED15xx, T6963C,     fonts, bitmap,    SD file
              I2C, CCB                           SED1330, uPD7225,    segment RAM       link → TFT
                    ▲                            PCF8576 ...                │           renderer
                    │                                 │                     ▼
              read responder ◄── status / RAM image ──┘          per-model map (custom glass)
              off | busy only | status+AC | full read-back
```

- **Target profile.** One small record per instrument: bus family, pin map,
  strobe polarity, chip-select levels, data width, controller model,
  geometry (columns, rows, line start addresses), character ROM, responder
  level, pull-down on or off, and the renderer (generic grid, bitmap, or a
  per-model layout like the PR53's). Built into the firmware at first, picked
  over USB or with the mode button; a file on SD later if it's worth it.
- **Front ends as runtime-built PIO programs.** The tap already loads
  hand-assembled PIO words; patching the strobe's GPIO number into a
  `wait gpio` instruction at load time removes the "CS must be GP7" rule
  (RP2350 PIO also adds a `wait jmppin` source; not tried here). Variants:
  6800-style (E plus R/W), 8080-style (/WR and /RD), clocked serial (clock,
  data, strobe or chip select), I2C, Sanyo CCB.
- **Latch like the chip does.** Instead of sampling a fixed 213 ns after the
  strobe, sample continuously while the strobe is active and keep the last
  sample when it ends. A two-instruction loop at 150 MHz samples every 13 ns
  or so, and the sample kept is always one taken while the strobe was still
  active, well inside the HD44780's 80 ns write setup time, so it doesn't
  depend on the 10 ns hold. It works for slow port-driven buses and fast
  memory-mapped ones alike. Data, control and strobe pass through the same
  input synchronisers, so they stay aligned. This only helps once the edges
  arrive with ns-level skew, which is the translator's job.
- **4-bit assembly with resync.** Pair nibbles at the boundaries the bus
  gives away: the busy-check reads between bytes (which the PIO currently
  throws away) and the time gaps. Recognise the datasheet's init (0x3, 0x3,
  0x3, 0x2 as single nibbles) where it appears, but don't assume it: the
  PR53 starts with whole `0x20` pairs instead, and a rule that treated its
  first strobes as single nibbles would misalign it. Flag odd counts in the
  log.
- **Read responder levels.** Off (passive). Busy only: pull just the busy
  line low through an open-drain transistor, which works at any host
  voltage. Status plus address counter (what
  v2 does). Full read-back: the tap keeps its own copy of the controller's RAM
  and pre-loads both the next status word and the next data byte into the
  PIO's FIFO; the PIO picks by RS (or C/D, A0) in the cycle. Status
  semantics are per controller: HD44780 bit 7 low means ready, T6963C wants
  STA0 and STA1 high, KS0108 has busy, on/off and reset bits.
- **Controller models in plain C, shared.** The same model code runs on the
  tap (for the responder), on the display Pico (for rendering) and on a PC
  (for tests against captures), as the display firmware's `host.mk` test
  already does for the PR53 decoder.
- **Sinks.** Keep today's text log as a mode (all the `tools/` read it); add a
  binary log of fixed-size records; make the display link lossless (DMA ring,
  a few Mbaud) rather than dropping writes when the FIFO is busy; SD logging.
- **Diagnostics for the shop.** Cheap once the events are there, and the most
  useful part on the bench: data lines that never toggle (an open trace or
  ribbon conductor), strobes shorter than the controller's minimum, writes
  while the real controller reports busy, init sequences that don't match the
  datasheet, host supply voltage and dips. Shown on the TFT and in the log.

### 5.3 Stages and rough effort

Effort is my estimate, in focused working days for Greg with Claude pairing,
calibrated loosely on the PR53 (about four months part-time from first capture
to a working carrier, most of it decoding custom glass). Board turnaround
assumes JLCPCB-style 1-2 weeks.

| Stage | What | Hardware | Effort |
|---|---|---|---|
| 0 | Try v2 on the next 4-bit HD44780 instrument that comes in (mostly home keyboards and arrangers; most 40x2 pro synths are 8-bit). To tell: a 4-bit instrument has DB0-DB3 grounded or missing at the LCD connector, as on the PR53's CN1. Firmware: passive mode (read responder off), strobe polarity as a setting, responder started before the USB wait, a generic grid in the laptop viewer (strip the PR53 heuristic, set rows and columns). If an Ensoniq comes in first: the panel link through U2's spare channel to a PIO UART, and MAME's byte codes in the viewer. Separately, scope the PR53's CS polarity | v2 as built; a lead set from J1 to the instrument's LCD connector, J1's +5 V left unconnected; carrier on the Zero's USB with D1 bridged (the carrier README's rule: never both); power the instrument soon after the tool (the pull-ups back-feed an unpowered host, 3.2). Lift R1 for passive use; the shifters' own 10 kΩ pull-ups stay, which a push-pull 5 V bus tolerates | 2-3 days |
| 1 | Generic HD44780 firmware: configurable pins and polarity, latch-at-end sampling, 4/8-bit with resync, responder levels, binary log, lossless link, generic character renderer on the TFT with A00/A02 fonts | 8-bit needs 4 more channels: a bodged third shifter on v2 is possible but slow-edged; better to wait for v3 | 2-3 weeks |
| 2 | v3 board: translator front end, host sensing, switchable pull-down, adapter connector, SD, J2 fix. Two or three adapters (1x14/1x16 standard, 2x7 IDC, FFC pass-through) | New PCB, about two spins | 1-2 weeks design, plus fab, plus 2-3 days bring-up per spin |
| 3 | Per-model maps for custom icon glass (type B), done the PR53 way with the campaign tools | v2 or v3 | 1-4 weeks per instrument |
| 4 | Serial and scan-signal front ends, picked by what comes through the shop: the Ensoniq panel link (UART plus 16-segment renderer), SED1335 panel scan capture into a framebuffer (LC7981 if its panel turns out similar), the MT-32's serial LCD | v2 may do the Ensoniq and MT-32; v3 for the rest | About 1 week each |
| 4b | Bus-level graphic controllers (T6963C first, for diagnosis): front end, controller model, bitmap renderer, status answers | v3 | About 1 week each; the first one longer |
| 5 | Product: enclosure, adapter library, documentation, support | — | Months; decide after stage 2 shows how often it gets used |

### 5.4 What to do first

1. Do stage 0 on the bench with the next character-LCD instrument. It costs a
   few days and answers the real question: how often does the tool save time
   in the shop?
2. Decide between "shop tool" and "product" after that. A shop tool needs
   stages 1-2 and a few adapters. A product is more likely to be replacement
   displays for one family at a time, where nothing else exists, than a
   universal sniffer. Three candidates, in order of how much of the work is
   already done:
   - **HD44780-class custom icon glass** in arrangers and digital pianos,
     starting with the PR53 (other Technics SX-PR models may share its glass;
     not checked). The capture and display chain exists; each model needs
     its map and a mechanical fit.
   - **The Ensoniq VFD family**: closely related panel protocols from the
     ESQ-1 to the TS-12 (the EPS and ASR differ), a tap that needs one wire
     and answers nothing, and no replacement glass on the market. The hard part is a display that fits the 2x40 window.
   - **SED1335 controller-less glass** (JV-2080, XP-60, XP-80, EX5, RM1x,
     RS7000): capture the panel's scan signals and redraw them. No
     controller model needed.

   Before investing in any of them, look for existing products: this research
   found none for the last two, but replacement-display sellers come and go.
   The precedents show there's a market: a commercial OLED kit for the Casio
   FZ-1 that emulates its display chipset, an MPC2000 replacement LCD at
   US$199, and the LCDJunoG project, whose README points to a store selling a
   ready-made Juno-G replacement.

## Terms

- **PIO**: the RP2350's small programmable I/O state machines; they watch
  and drive pins with nanosecond timing while the CPU does other work.
- **FIFO, ring buffer**: queues. The PIO hands captured words to the CPU
  through a FIFO; the tap keeps events in a ring buffer until USB and the
  link have sent them.
- **DDRAM, CGRAM, AC**: the HD44780's text memory, its memory for up to 8
  user-defined characters (the PR53's icons live here), and the address
  counter that says where the next byte goes.
- **Busy flag**: bit 7 of the HD44780's status read; the CPU waits for it to
  read 0 before the next write.
- **Read responder**: the tap's PIO program that answers the CPU's reads in
  place of a missing controller.
- **Passive mode / replacement mode**: listening alongside a working display
  without driving anything, versus standing in for a dead or removed one.
- **6800-style / 8080-style bus**: an E strobe plus a R/W line, versus
  separate /WR and /RD strobes.
- **CCB**: Sanyo's 3-wire serial bus for its LCD drivers. **FFC**: flat
  flexible cable. **PPI**: a parallel I/O chip such as the 8255. **COG**:
  chip-on-glass. **EL**: electroluminescent backlight. **NOS**: new old stock.

## Sources

**This repo.** `firmware/tap/src/pr53_emu.c` (PIO programs, pairing, link),
`firmware/display/` (renderer, emulator, panel wiring),
`hardware/carrier/README.md` (bring-up), `hardware/carrier/gen_board.py` and
`gen_footprints.py` (nets, the Zero's pin rows), `docs/piano-interface.md`,
`captures/startup_2026-10-31.log` and `captures/lcd_test_mode_2026-10-31.log`
(write spacing).

**Datasheets.**
[Hitachi HD44780U](https://www.sparkfun.com/datasheets/LCD/HD44780.pdf)
(timing, DC levels, 4-bit init),
[Samsung KS0066U](https://hamblen.ece.gatech.edu/UP3/KS0066U.pdf),
[Sitronix ST7066](https://www.displayfuture.com/Display/datasheet/controller/ST7066.pdf),
[Toshiba T6963C](https://www.crystalfontz.com/controllers/uploaded/Toshiba_T6963C_v1997-04-07.pdf),
[Epson SED1335](https://download.epson-europe.com/pub/electronics-de/assp/sed1300/sed1335.pdf),
[Epson SED1520](https://download.epson-europe.com/pub/electronics-de/assp/sed1500/sed1520.pdf),
[Samsung KS0108B](https://surplustronics.co.nz/product/LA0335/info-1038.pdf?1502768508),
[Sanyo LC7981](https://www.crystalfontz.com/controllers/uploaded/Sanyo_LC7981.pdf),
[Hitachi HD61830](https://www.crystalfontz.com/controllers/uploaded/HD61830.pdf),
[NEC uPD7225](https://w140.com/tekwiki/images/f/f6/NEC_UPD7225.pdf),
[NXP PCF8576C](https://www.nxp.com/docs/en/data-sheet/PCF8576C.pdf),
[Noritake CU-U series](https://www.noritake-elec.com/products/vfd-display-module/character-display/cu-u-series),
[TI SN74LVC16T245](https://www.ti.com/product/SN74LVC16T245).

**RP2350.** A4 stepping, 5 V tolerance and the E9 fix:
[CNX Software](https://www.cnx-software.com/?p=154587),
[The Register](https://www.theregister.com/2025/07/29/raspberry_pi_rp2350_update/).
Erratum E9:
[Hackaday](https://hackaday.com/2024/09/04/the-worsening-raspberry-pi-rp2350-e9-erratum-situation/),
[Hackster](https://hackster.io/news/a-surprise-hardware-bug-in-raspberry-pi-s-rp2350-leads-to-unexpected-pull-down-behavior-76b51ec22ede).

**Service manuals** (archive.org, `https://archive.org/details/<id>`):
`korg_M1_SERVICE_MANUAL`, `korg_ds-8_service_manual_part_2`,
`korg_01W_WFD_SERVICE_MANUAL`, `roland_D-110_SERVICE_NOTES`,
`roland_D-550_SERVICE_NOTES`, `roland_JV-880_SERVICE_NOTES`,
`roland_JV-1080_SERVICE_NOTES`, `Roland_JV-2080_service_notes`,
`roland_XP-80_SERVICE_NOTES`, `roland_MT-32_SERVICE_NOTES-3rd`,
`roland_JX-8P_SERVICE_NOTES`, `roland_JX-10_SERVICE_NOTES`,
`roland_HP-535_SERVICE_NOTES`, `yamaha_SY-77_SERVICE_MANUAL`,
`Yamaha_SY99_Service_Manual`, `Yamaha_EX5_Service_Manual`,
`manualzilla-id-7347863` (PSR-140), `manualzilla-id-7384669` (PSR-C200),
`CasioCZ1Servicemanual`, `Casio_CTK-811EX_Service_Manual`, `casio-ld-50-sm`,
`Akai_S900_service_notes`, `sm_Service_Manual_MPC60`,
`akai_MPC3000_SERVICE_MANUAL`, `Akai_S1000HD_service_notes`,
`ensoniq_esq-1_esq-m_service_manual`, `ensoniq_SQ80_SERVICE_MANUAL`,
`sm_Ensoniq_EPS_16_Service_Manual`,
`kurzweil_K2000_K2000R_SERVICE_MANUAL`.

**MAME drivers** ([source tree](https://github.com/mamedev/mame/tree/master/src/mame)):
the `korg`, `roland`, `yamaha`, `casio`, `akai`, `emusys`, `ensoniq`,
`kawai`, `alesis` and `access` folders; `ensoniq/esqpanel.cpp` (62,500 baud
8N2 panel link) and `ensoniq/esqvfd.cpp` (display byte codes).

**Forums and projects.** yamahamusicians.com threads on
[replacement LCDs](https://yamahamusicians.com/forum/threads/replacement-lcd-screens.7960/),
[the DX11](https://yamahamusicians.com/forum/threads/dx11-lcd-replacement.8401/)
and [the RM1x](https://yamahamusicians.com/forum/threads/yamaha-rm1x-lcd-replacement.9146/);
[Ensoniq VFDs](https://forum.vintagesynth.com/viewtopic.php?t=96381&start=60);
[Korg 01/W display](https://indra.com/~cliffcan/01disp.htm);
[K2000R display upgrade](https://helium.deepgreen.ca/dave/K2000R_Display/K2000R_Display_Upgrade.html);
[Kurzweil K1000 adapter PCB](https://www.pcbway.com/project/shareproject/Kurzweil_K1000_K1200_Display_Replacement_PCB.html);
[Casio FZ-1 OLED kit](https://www.matrixsynth.com/2025/12/casio-fz-1-installing-new-oled-display.html);
[MPC2000 replacement LCD](https://www.mpcstuff.com/mpc2000-lcd-sc.html);
[LCDJunoG](https://github.com/dpeddi/LCDJunoG) (Pico PIO capture of a Juno-G's
display bus, redrawn on an ILI9488);
[ensoniqdisplay](https://github.com/balamutang/ensoniqdisplay);
[DoMSnif](https://hackaday.io/project/166220-domsnif-dot-matrix-lcd-sniffer-bluetooth-adapter)
(KS0108 sniffer);
[sigrok's decoder list](https://sigrok.org/wiki/Protocol_decoders) (HD44780
only "planned, 0%"; no decoder for any of these LCD chips).

## Rests only on training data

- Model years not taken from a manual.
- How BSS138 modules behave at speed (slow, pull-up driven rising edges): the
  circuit is well known, but no rise time was measured or looked up.
- RP2350 PIO details: the two-cycle input synchronisers that keep data and
  strobe aligned, patching a `wait gpio` instruction at load time. The
  `wait jmppin` source is from secondary sources (assembler projects), not
  the datasheet.
- The HD44780 character ROM variants (A00 Japanese, A02 European).
- That bar-format TFTs suit a 40x2 window.
- That entry-level keyboards often drive their glass directly (also
  judgement).
