#!/usr/bin/env python3
"""
gen_footprints.py — writes pr53.pretty/, the two module footprints KiCad
doesn't ship: the Waveshare RP2350-Zero (on pin headers) and a generic
4-channel BSS138 level-shifter module.

Both are "socket" footprints: plain 2.54mm through-holes where you solder
header pins (or female sockets) and drop the module on top.

!! MEASURE BEFORE YOU FAB !!  The two row spacings below are the only
dimensions here that come from memory rather than a datasheet:
    ZERO_COL_SPACING    centre-to-centre of the Zero's two long pin rows
    SHIFTER_ROW_SPACING centre-to-centre of the shifter's HV and LV rows
Count the holes on your perfboard build: 6 holes over = 15.24, 5 = 12.70.
"""
import os

ZERO_COL_SPACING = 15.24      # RP2350-Zero: 0.6" between the long edges
SHIFTER_ROW_SPACING = 12.70   # generic BSS138 4-ch: 0.5" between HV and LV rows
PITCH = 2.54
PAD, DRILL = 1.7, 1.0

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr53.pretty")


def pad(num, x, y, square=False):
    shape = "rect" if square else "circle"
    return (f'  (pad "{num}" thru_hole {shape} (at {x:.3f} {y:.3f}) (size {PAD} {PAD}) '
            f'(drill {DRILL}) (layers "*.Cu" "*.Mask"))\n')


def rect(layer, x0, y0, x1, y1, w=0.12):
    return (f'  (fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f}) '
            f'(stroke (width {w}) (type solid)) (fill none) (layer "{layer}"))\n')


def line(layer, x0, y0, x1, y1, w=0.12):
    return (f'  (fp_line (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}"))\n')


def text(kind, s, x, y, layer, size=1.0, hide=False):
    h = " hide" if hide else ""
    if kind == "user":
        return (f'  (fp_text user "{s}" (at {x:.3f} {y:.3f}) (layer "{layer}")\n'
                f'    (effects (font (size {size} {size}) (thickness {size*0.15:.3f}))))\n')
    return (f'  (fp_text {kind} "{s}" (at {x:.3f} {y:.3f}) (layer "{layer}"){h}\n'
            f'    (effects (font (size {size} {size}) (thickness {size*0.15:.3f}))))\n')


def footprint(name, descr, body):
    return (f'(footprint "{name}" (version 20240108) (generator "pr53_gen")\n'
            f'  (layer "F.Cu")\n  (descr "{descr}")\n  (attr through_hole)\n'
            + body + ")\n")


# Waveshare RP2350-Zero, USB-C at the top, viewed from the component side.
# Only the two long edges are socketed; the 5-pin bottom edge (GP9-13) is
# unused and gets no holes.
ZERO_LEFT = ["5V", "GND", "3V3", "GP29", "GP28", "GP27", "GP26", "GP15", "GP14"]  # pads 1-9
ZERO_RIGHT = [f"GP{i}" for i in range(9)]                                          # pads 10-18


def zero():
    cx = ZERO_COL_SPACING / 2
    y0 = -4 * PITCH
    top, bot = y0 - 1.6, y0 - 1.6 + 23.5           # 18 x 23.5mm board outline
    b = text("reference", "REF**", 0, top - 1.5, "F.SilkS")
    b += text("value", "RP2350-Zero", 0, 0, "F.Fab")
    for i, n in enumerate(ZERO_LEFT):
        b += pad(i + 1, -cx, y0 + i * PITCH, square=(i == 0))
        b += text("user", n, -cx + 2.4, y0 + i * PITCH, "F.SilkS", 0.8)
    for i, n in enumerate(ZERO_RIGHT):
        b += pad(i + 10, cx, y0 + i * PITCH)
        b += text("user", n, cx - 2.2, y0 + i * PITCH, "F.SilkS", 0.8)
    b += rect("F.SilkS", -9.1, top - 0.1, 9.1, bot + 0.1)
    b += rect("F.Fab", -9.0, top, 9.0, bot, 0.1)
    b += rect("F.CrtYd", -9.35, top - 0.35, 9.35, bot + 0.35, 0.05)
    b += rect("F.SilkS", -3.4, top - 0.1, 3.4, top + 3.2)     # USB-C shell marker
    b += text("user", "USB", 0, top + 1.6, "F.SilkS", 1.0)
    return footprint("RP2350-Zero_Socket",
                     "Waveshare RP2350-Zero on 2x 1x9 2.54mm headers, long edges only", b)


# Generic BSS138 4-channel bidirectional shifter (SparkFun BOB-12009 pinout,
# which the cheap clones copy). HV row on the left, LV row on the right,
# channel n on the HV side directly opposite channel n on the LV side.
SHIFT_LV = ["LV1", "LV2", "LV", "GND", "LV3", "LV4"]   # pads 1-6
SHIFT_HV = ["HV1", "HV2", "HV", "GND", "HV3", "HV4"]   # pads 7-12


def shifter():
    cx = SHIFTER_ROW_SPACING / 2
    y0 = -2.5 * PITCH
    hw, hh = cx + 1.5, 3 * PITCH + 0.5
    b = text("reference", "REF**", 0, -hh - 1.2, "F.SilkS")
    b += text("value", "BSS138_4ch", 0, 0, "F.Fab")
    for i, n in enumerate(SHIFT_HV):
        b += pad(i + 7, -cx, y0 + i * PITCH, square=(i == 0))
        b += text("user", n, -cx + 2.3, y0 + i * PITCH, "F.SilkS", 0.8)
    for i, n in enumerate(SHIFT_LV):
        b += pad(i + 1, cx, y0 + i * PITCH)
        b += text("user", n, cx - 2.3, y0 + i * PITCH, "F.SilkS", 0.8)
    b += rect("F.SilkS", -hw - 0.1, -hh - 0.1, hw + 0.1, hh + 0.1)
    b += rect("F.Fab", -hw, -hh, hw, hh, 0.1)
    b += rect("F.CrtYd", -hw - 0.35, -hh - 0.35, hw + 0.35, hh + 0.35, 0.05)
    b += line("F.SilkS", 0, -hh + 0.6, 0, hh - 0.6)
    b += text("user", "5V", -1.1, hh - 1.4, "F.SilkS", 0.8)
    b += text("user", "3V3", 1.5, hh - 1.4, "F.SilkS", 0.8)
    return footprint("BSS138_4ch_Module",
                     "Generic 4-channel BSS138 level shifter module, 2x 1x6 2.54mm", b)


if __name__ == "__main__":
    os.makedirs(LIB, exist_ok=True)
    for name, src in (("RP2350-Zero_Socket", zero()), ("BSS138_4ch_Module", shifter())):
        with open(os.path.join(LIB, name + ".kicad_mod"), "w") as f:
            f.write(src)
    print("wrote", LIB)
