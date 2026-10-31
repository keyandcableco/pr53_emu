#!/usr/bin/env python3
"""
gen_board.py — builds pr53_carrier.kicad_pcb, the module-carrier board for
the SX-PR53 display replacement.

    /usr/bin/python3 gen_footprints.py && /usr/bin/python3 gen_board.py

(needs KiCad's own python, the one that can `import pcbnew`)

What it carries — all socketed on 2.54mm headers, nothing fine-pitch:
    A1  RP2350-Zero        tap: reads the piano's HD44780 bus, answers reads
    A2  Pico 2             display: drives the ILI9486 over 16-bit parallel
    U1  BSS138 4ch module  DB4-7   (bidirectional: the tap answers reads)
    U2  BSS138 4ch module  RS/RW/CS (+1 spare channel)
    J1  9-pos 3.5mm screw terminal   piano in
    J2  2x18 pin header              LCD out (ribbon to the HiLetgo panel)

Every net here mirrors the firmware: firmware/tap/src/pr53_emu.c (PIN_*),
firmware/display/src/pr53_ili9486_par.h (PAR_*), firmware/display/src/bus_tap.c.
"""
import os
import pcbnew
from pcbnew import VECTOR2I_MM as P, FromMM as mm

HERE = os.path.dirname(os.path.abspath(__file__))
KLIB = "/usr/share/kicad/footprints"
OUT = os.path.join(HERE, "pr53_carrier.kicad_pcb")

W, H = 100.0, 62.0          # board outline, mm
OX, OY = 100.0, 100.0      # where the board sits on the KiCad page

board = pcbnew.BOARD()
nets = {}


def net(name):
    if name not in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    return nets[name]


def place(lib, name, ref, value, x, y, rot=0, pins=None, back_text=False):
    path = os.path.join(HERE, lib) if lib.startswith("pr53") else os.path.join(KLIB, lib)
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib}:{name}")
    fp.SetReference(ref)
    fp.SetValue(value)
    board.Add(fp)
    fp.SetPosition(P(OX + x, OY + y))
    fp.SetOrientationDegrees(rot)
    for pad_num, net_name in (pins or {}).items():
        hit = [p for p in fp.Pads() if p.GetNumber() == str(pad_num)]
        if not hit:
            raise SystemExit(f"{ref} has no pad {pad_num}")
        for p in hit:
            p.SetNet(net(net_name))
    return fp


def silk(s, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(OX + x, OY + y))
    t.SetLayer(layer)
    t.SetTextSize(P(size, size))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(rot)
    board.Add(t)


def pad_pos(fp, num):
    p = [q for q in fp.Pads() if q.GetNumber() == str(num)][0].GetPosition()
    return pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY


# ---------------------------------------------------------------- outline
corners = [(0, 0), (W, 0), (W, H), (0, H)]
for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(OX + x0, OY + y0))
    s.SetEnd(P(OX + x1, OY + y1))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)

# ---------------------------------------------------------------- J1: piano in
# 9-way 3.5mm screw terminal on the left edge. Rotated 270 so the wire
# openings face off the board edge; pin 1 (GND) is then at the top. The
# signal order matches the shifter channels opposite, so nothing crosses.
J1_NETS = {1: "GND", 2: "+5V", 3: "CS", 4: "RW", 5: "RS", 6: "DB7", 7: "DB6",
           8: "DB5", 9: "DB4"}
j1 = place("TerminalBlock_Phoenix.pretty",
           "TerminalBlock_Phoenix_PT-1,5-9-3.5-H_1x09_P3.50mm_Horizontal",
           "J1", "PR53_IN", 5.6, 29.0, rot=270, pins=J1_NETS)
j1.Reference().SetVisible(False)

# R1: the DB7 busy-flag pulldown, on the 5V side. Load-bearing.
place("Resistor_THT.pretty", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
      "R1", "10k", 15.0, 46.0, rot=90, pins={1: "DB7", 2: "GND"})

# ---------------------------------------------------------------- shifters
# HV row faces J1, LV row faces the Zero. The Zero is mounted USB-down, so
# its signal column reads GP8 (top) .. GP0 (bottom); the shifter channels are
# assigned in that same top-to-bottom order so the lines run straight across.
place("pr53.pretty", "BSS138_4ch_Module", "U1", "BSS138_4ch (DB4-7)", 26.0, 51.6, pins={
    7: "DB7", 8: "DB6", 9: "GND", 10: "+5V", 11: "DB5", 12: "DB4",
    1: "T_DB7", 2: "T_DB6", 3: "GND", 4: "+3V3_TAP", 5: "T_DB5", 6: "T_DB4"})
place("pr53.pretty", "BSS138_4ch_Module", "U2", "BSS138_4ch (RS/RW/CS)", 26.0, 32.6, pins={
    7: "CS", 8: "RW", 9: "GND", 10: "+5V", 11: "RS",
    1: "T_CS", 2: "T_RW", 3: "GND", 4: "+3V3_TAP", 5: "T_RS"})
# Pads by position, top to bottom: 1/7 = ch4, 2/8 = ch3, 3/9 = GND, 4/10 =
# LV/HV, 5/11 = ch2, 6/12 = ch1.
# U2 HV1/LV1 (pads 6/12) is the spare channel: left unconnected (module pull-ups hold it).

# ---------------------------------------------------------------- A1: tap
# RP2350-Zero, USB-C down at the bottom edge so it can be reflashed in place.
# Pads 10-18 = GP0..GP8.  GP6 skipped on purpose (CS must be base+7).
place("pr53.pretty", "RP2350-Zero_Socket", "A1", "RP2350-Zero (tap)", 46.0, 49.9, rot=180, pins={
    1: "+5V_TAP", 2: "GND", 3: "+3V3_TAP",
    10: "T_DB4", 11: "T_DB5", 12: "T_DB6", 13: "T_DB7", 14: "T_RS", 15: "T_RW",
    17: "T_CS", 18: "LINK"})

# ---------------------------------------------------------------- A2: display
# Pico 2, USB down at the bottom edge. Footprint origin is pad 1; rotated 180
# the pads span (-17.78..0, -48.26..0) from it.
pico = {38: "GND", 39: "+5V_DISP"}
for g in (3, 8, 13, 18, 23, 28, 33):
    pico[g] = "GND"
gp_pin = {0: 1, 1: 2, 2: 4, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11, 9: 12,
          10: 14, 11: 15, 12: 16, 13: 17, 14: 19, 15: 20}
for gp, pin in gp_pin.items():
    pico[pin] = f"LCD_DB{gp}"
pico.update({21: "LCD_RS", 22: "LCD_WR", 24: "LCD_RST", 27: "LINK"})
PICO_CX, PICO_CY = 69.6, 36.0
place("Module.pretty", "RaspberryPi_Pico_Common_THT", "A2", "Pico 2 (display)",
      PICO_CX + 8.89, PICO_CY + 24.13, rot=180, pins=pico)

# ---------------------------------------------------------------- J2: LCD out
# 2x18 male header, numbered exactly like the HiLetgo panel's 36-pin header,
# so a straight-through IDC ribbon maps pin n to pin n.
lcd = {1: "+5V", 2: "+5V", 21: "GND", 35: "GND", 36: "GND",
       19: "LCD_RS", 20: "LCD_WR", 22: "LCD_RST"}
for i in range(8):
    lcd[3 + i] = f"LCD_DB{8 + i}"   # pins 3-10  = DB8..DB15
    lcd[11 + i] = f"LCD_DB{7 - i}"  # pins 11-18 = DB7..DB0
j2 = place("Connector_PinHeader_2.54mm.pretty", "PinHeader_2x18_P2.54mm_Vertical",
           "J2", "LCD_OUT (HiLetgo 36p)", 92.2, 10.2, pins=lcd)

# ---------------------------------------------------------------- power
# One +5V rail from the piano. Each module gets it through a Schottky so a
# USB cable plugged in for reflashing can't back-feed the piano (or vice versa).
place("Diode_THT.pretty", "D_DO-41_SOD81_P10.16mm_Horizontal",
      "D1", "1N5819", 31.0, 7.0, pins={1: "+5V_TAP", 2: "+5V"})
place("Diode_THT.pretty", "D_DO-41_SOD81_P10.16mm_Horizontal",
      "D2", "1N5819", 31.0, 12.5, pins={1: "+5V_DISP", 2: "+5V"})
place("Capacitor_THT.pretty", "CP_Radial_D6.3mm_P2.50mm",
      "C1", "100u 10V", 15.0, 8.5, pins={1: "+5V", 2: "GND"})
place("Capacitor_THT.pretty", "C_Disc_D5.0mm_W2.5mm_P5.00mm",
      "C2", "100n", 15.0, 15.5, pins={1: "+5V", 2: "GND"})
place("LED_THT.pretty", "LED_D3.0mm", "D3", "PWR", 50.0, 10.0, pins={1: "GND", 2: "LED_A"})
place("Resistor_THT.pretty", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
      "R2", "1k", 38.5, 17.5, rot=0, pins={1: "+5V", 2: "LED_A"})

# ---------------------------------------------------------------- mounting
for i, (x, y) in enumerate([(3.4, 3.4), (W - 3.4, 3.4), (W - 3.4, H - 3.4), (47.0, 3.4)]):
    h = place("MountingHole.pretty", "MountingHole_3.2mm_M3", f"H{i + 1}", "M3", x, y)
    h.Reference().SetVisible(False)

# ---------------------------------------------------------------- silkscreen
for pin, label in J1_NETS.items():
    x, y = pad_pos(j1, pin)
    silk(label, x + 5.2, y, 1.0)
silk("J1 PIANO", 6.0, 23.0, 1.1, bold=True)
x, y = pad_pos(j2, 1)
silk("1", x - 2.2, y, 1.0, bold=True)
silk("LCD", 87.0, 32.0, 1.1, rot=90, bold=True)
silk("PR53 CARRIER v2", 70.0, 4.6, 1.4, bold=True)
silk("tap: RP2350-Zero  |  display: Pico 2", 70.0, 7.4, 0.8)
silk("piano 5V -> Schottky -> each module", 26.0, 2.4, 0.8)

# ---------------------------------------------------------------- back label
# Maker's mark on B.Silkscreen: three lines along the top edge, and the QR
# (https://keyandcable.com, from keyandcable_qr.txt) below them, between the
# Pico's pin rows where its antenna keepout leaves bare board. Coordinates
# are front-view; the QR columns are mirrored so it reads from the back.
LABEL_CX = PICO_CX
for text, y, size, bold in [("The Key & Cable Co.", 2.1, 1.6, True),
                            ("keyandcable.com", 4.5, 1.2, False),
                            ("Technics PR53 Carrier Board", 6.6, 1.2, False)]:
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(pcbnew.B_SilkS)
    t.SetMirrored(True)
    t.SetTextSize(P(size, size))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetPosition(P(OX + LABEL_CX, OY + y))
    board.Add(t)

QR_MODULE = 0.48           # mm per module: 25 x 0.48 = 12mm, ~14mm with quiet zone
QR_TOP = 10.2
with open(os.path.join(HERE, "keyandcable_qr.txt")) as f:
    qr = f.read().split()
qn = len(qr)
qx0 = LABEL_CX - qn * QR_MODULE / 2
for r, row in enumerate(qr):
    c = 0
    while c < qn:                       # one filled rect per run of dark modules
        if row[c] != "#":
            c += 1
            continue
        e = c
        while e < qn and row[e] == "#":
            e += 1
        x0 = qx0 + (qn - e) * QR_MODULE   # mirrored: column c lands at qn-1-c
        x1 = qx0 + (qn - c) * QR_MODULE
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_RECT)
        sh.SetStart(P(OX + x0, OY + QR_TOP + r * QR_MODULE))
        sh.SetEnd(P(OX + x1, OY + QR_TOP + (r + 1) * QR_MODULE))
        sh.SetFilled(True)
        sh.SetWidth(0)
        sh.SetLayer(pcbnew.B_SilkS)
        board.Add(sh)
        c = e

# No vias under the QR (a drilled hole would punch out modules). Tracks are fine.
q = 1.0
k = pcbnew.ZONE(board)
k.SetIsRuleArea(True)
k.SetDoNotAllowVias(True)
k.SetDoNotAllowTracks(False)
k.SetDoNotAllowPads(False)
k.SetDoNotAllowFootprints(False)
k.SetLayerSet(pcbnew.LSET.AllCuMask())
k.SetZoneName("QR no-via")
ol = k.Outline()
ol.NewOutline()
qy1 = QR_TOP + qn * QR_MODULE
for x, y in [(qx0 - q, QR_TOP - q), (qx0 + qn * QR_MODULE + q, QR_TOP - q),
             (qx0 + qn * QR_MODULE + q, qy1 + q), (qx0 - q, qy1 + q)]:
    ol.Append(mm(OX + x), mm(OY + y))
board.Add(k)

# ---------------------------------------------------------------- rules (JLCPCB-safe)
# KiCad 9 keeps rules and net classes in the .kicad_pro, so they're written
# there (see write_project) rather than set on the board.
POWER_NETS = ["GND", "+5V", "+5V_TAP", "+5V_DISP", "+3V3_TAP"]

# Keep the autorouter 0.6mm off the board edge (Freerouting doesn't read
# KiCad's copper-to-edge rule, but it does honour keepout areas).
for x0, y0, x1, y1 in [(0, 0, W, 0.6), (0, H - 0.6, W, H), (0, 0, 0.6, H), (W - 0.6, 0, W, H)]:
    k = pcbnew.ZONE(board)
    k.SetIsRuleArea(True)
    k.SetDoNotAllowTracks(True)
    k.SetDoNotAllowVias(True)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    k.SetLayerSet(pcbnew.LSET.AllCuMask())
    ol = k.Outline()
    ol.NewOutline()
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(k)

# GND pour on both layers.
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net("GND"))
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)


def write_project():
    import json
    nc = lambda name, w: {
        "name": name, "track_width": w, "clearance": 0.2, "via_diameter": 0.7,
        "via_drill": 0.35, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
        "wire_width": 6, "bus_width": 12, "line_style": 0, "priority": 0 if name == "Power" else 2147483647,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}
    pro = {
        "meta": {"filename": "pr53_carrier.kicad_pro", "version": 3},
        "board": {"design_settings": {"rules": {
            "min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
            "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.4,
            "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
            "min_annular_width": 0.13, "min_silk_clearance": 0.0,
            "min_text_height": 0.8, "min_text_thickness": 0.08}}},
        "net_settings": {
            "classes": [nc("Default", 0.25), nc("Power", 0.6)],
            "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in POWER_NETS],
            "meta": {"version": 4}},
    }
    with open(OUT.replace(".kicad_pcb", ".kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)


board.Save(OUT)
write_project()
print("wrote", OUT, "-", len(board.GetFootprints()), "footprints,", len(nets), "nets")
