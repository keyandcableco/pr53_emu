// pr53_theme.h — ALL the look & feel in one place.
//
// This is the ONLY file you edit to change how the display looks:
// rotation, color order, and the whole palette. No logic lives here —
// tweak, rebuild, reflash. Every value has a comment explaining it.

#ifndef PR53_THEME_H
#define PR53_THEME_H

#include <stdint.h>

// ===========================================================================
// 1. ROTATION  (wide layout, turned to match your horizontal mounting)
// ===========================================================================
// Layout is always WIDE (480x320); these just turn it on the glass. Your
// earlier flash looked 90 off, so you want one of the TURNED mappings:
//   1 = wide, turned 90
//   3 = wide, turned 90 the other way (use if 1 comes out upside-down)
// (0 and 2 are the un-turned wide pair — if BOTH 1 and 3 look wrong, the
//  image wasn't actually 90 off; try 0 or 2 instead.)
#define THEME_ROTATION   1

// ===========================================================================
// 2. COLOR ORDER  — fixes the "green looks blue/grey" swap.
// ===========================================================================
// If colors look wrong (red<->blue swapped), flip this. Panels vary: some
// want RGB, some BGR. Your symptom (green -> blue-grey) means the default
// was wrong, so this is set to the corrected value. If colors STILL look
// swapped after flashing, change 0 <-> 1.
//   0 = RGB order
//   1 = BGR order
#define THEME_BGR        0

// ---- Pixel byte order ----
// Some parallel ILI9486 boards latch the 16-bit pixel high-byte/low-byte
// opposite to what the SDK emits. That shuffles the color in a way BGR alone
// can't fix — the classic symptom is green coming out RED (or blue). If BGR
// flipping doesn't get you green, set this to 1.
//   0 = normal (hi byte, lo byte)
//   1 = swapped (lo byte, hi byte)
#define THEME_SWAP_BYTES 1

// ===========================================================================
// 3. PALETTE  — the actual colors, as R,G,B (0-255 each), like hex web colors.
// ===========================================================================
// These are converted to the panel's 16-bit format automatically. Edit the
// three numbers per line to recolor everything. A few ready-made themes are
// below — copy one into the ACTIVE block, or roll your own.

// ---- ACTIVE THEME (edit these) : "Technics green" (the original glass) ----
#define THEME_FIELD_R   0xc7   // backlight field (the lit background)
#define THEME_FIELD_G   0xd4
#define THEME_FIELD_B   0x3f

#define THEME_SEG_R     0x2b   // lit segments (digits, meters, text)
#define THEME_SEG_G     0x3a
#define THEME_SEG_B     0x12

#define THEME_SEGOFF_R  0xb3   // unlit segment "ghost" (faint on the field)
#define THEME_SEGOFF_G  0xc0
#define THEME_SEGOFF_B  0x4a

#define THEME_PRINT_R   0x5a   // printed labels (part names under the meters)
#define THEME_PRINT_G   0x6a
#define THEME_PRINT_B   0x34

#define THEME_RULE_R    0x2f   // divider lines / box outlines
#define THEME_RULE_G    0x3d
#define THEME_RULE_B    0x17

// ---------------------------------------------------------------------------
// READY-MADE THEMES — to use one, copy its 15 numbers over the ACTIVE block.
// ---------------------------------------------------------------------------
//
//  "Amber" (classic amber VFD look):
//     FIELD 0x1a 0x12 0x00 | SEG 0xff 0xb0 0x00 | SEGOFF 0x3a 0x28 0x00
//     PRINT 0xaa 0x77 0x00 | RULE 0x55 0x3a 0x00
//
//  "Blue LCD" (Nokia-ish blue backlight, dark text):
//     FIELD 0x3a 0x6e 0xa5 | SEG 0x08 0x14 0x22 | SEGOFF 0x2a 0x55 0x88
//     PRINT 0x12 0x2a 0x44 | RULE 0x18 0x30 0x50
//
//  "Green on black" (terminal / oscilloscope):
//     FIELD 0x00 0x0a 0x00 | SEG 0x33 0xff 0x66 | SEGOFF 0x0c 0x30 0x18
//     PRINT 0x1a 0x88 0x44 | RULE 0x10 0x40 0x22
//
//  "White on black" (clean modern):
//     FIELD 0x08 0x08 0x0a | SEG 0xe8 0xe8 0xf0 | SEGOFF 0x30 0x30 0x38
//     PRINT 0x88 0x88 0x92 | RULE 0x28 0x28 0x30
//
// ===========================================================================
// (below: machinery that turns the above into what the driver uses — you
//  don't need to touch anything past here)
// ===========================================================================

// RGB888 -> RGB565 packer, with optional byte swap (THEME_SWAP_BYTES).
static inline uint16_t theme_rgb(uint8_t r, uint8_t g, uint8_t b) {
    uint16_t v = (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
#if THEME_SWAP_BYTES
    v = (uint16_t)((v >> 8) | (v << 8));   // swap hi/lo byte
#endif
    return v;
}

#define THEME_COL_FIELD    theme_rgb(THEME_FIELD_R,  THEME_FIELD_G,  THEME_FIELD_B)
#define THEME_COL_SEG      theme_rgb(THEME_SEG_R,    THEME_SEG_G,    THEME_SEG_B)
#define THEME_COL_SEG_OFF  theme_rgb(THEME_SEGOFF_R, THEME_SEGOFF_G, THEME_SEGOFF_B)
#define THEME_COL_PRINT    theme_rgb(THEME_PRINT_R,  THEME_PRINT_G,  THEME_PRINT_B)
#define THEME_COL_RULE     theme_rgb(THEME_RULE_R,   THEME_RULE_G,   THEME_RULE_B)

// MADCTL byte computed from rotation + color order.
// Rotation bits: MY=0x80, MX=0x40, MV=0x20. BGR=0x08.
static inline uint8_t theme_madctl(void) {
    uint8_t m;
    switch (THEME_ROTATION & 3) {
        case 0:  m = 0x40; break;         // landscape
        case 1:  m = 0x20; break;         // portrait 90 CW
        case 2:  m = 0x80; break;         // landscape 180
        default: m = 0xE0; break;         // portrait 270 (MV+MX+MY)
    }
#if THEME_BGR
    m |= 0x08;
#endif
    return m;
}

// Whether this rotation swaps width/height (portrait modes).
// Panel mounts WIDE (long edge horizontal) — layout is always 480x320.
#define THEME_PORTRAIT  0

#endif // PR53_THEME_H
