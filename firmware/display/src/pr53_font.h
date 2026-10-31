// pr53_font.h — text & glyph primitives used by the renderer.
//
// Deliberately simple: a 5x7 bitmap font for labels/text, plus box/icon
// helpers and an itoa. On hardware these draw by filling small rects (fast
// enough at this scale). Swap in a nicer 7-seg vector font later if you want
// the digits to look more like the original glass.

#ifndef PR53_FONT_H
#define PR53_FONT_H

#include <stdint.h>

// Draw NUL-terminated text at (x,y) top-left, integer scale, color.
void font_text(int x, int y, const char *s, int scale, uint16_t color);
// Same, horizontally centered on cx.
void font_text_centered(int cx, int y, const char *s, int scale, uint16_t color);

// Convert int to decimal string (into caller buffer >= 8 bytes).
void font_itoa(char *buf, int v);

// A hollow rectangle outline (box) in the given color.
void font_box(int x, int y, int w, int h, uint16_t color);

// Small icons drawn as line art.
void font_kbd_icon(int x, int y, uint16_t color);
void font_drum_icon(int x, int y, uint16_t color);

#endif // PR53_FONT_H
