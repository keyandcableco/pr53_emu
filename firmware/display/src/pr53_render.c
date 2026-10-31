// pr53_render.c — three-zone glass renderer with per-field dirty tracking.
//
// Layout mirrors pr53_display.py's App geometry (scaled to 480x320):
//   TOP    (y 0..96):   tempo | chord box | transpose box
//   MIDDLE (y 96..192): small displays | RIGHT1/RHYTHM labels | 12-char text
//   BOTTOM (y 192..320): 8 bargraph columns (meter + number + arrow + label)
//
// render_static() paints everything that never changes ONCE. render_frame()
// diffs against last_* and repaints only fields that moved — so a single
// number ticking updates just that number's little rectangle.

#include "pr53_render.h"
#include "pr53_ili9486_par.h"
#include "pr53_font.h"
#include <string.h>

// ---- Zone geometry (480x320) ----
#define PAD      10
#define Z_TOP    96
#define Z_MID    192

#define SMALL_X  14
#define SMALL_W  40
#define LABEL_X  (SMALL_X + SMALL_W + 8)
#define TEXT_X   (LABEL_X + 92)

// Bottom zone: 8 columns spanning SMALL_X..(480-PAD)
#define BOT_LEFT   SMALL_X
#define BOT_RIGHT  (ILI_W - PAD)
#define COL_W      ((BOT_RIGHT - BOT_LEFT) / PR53_NUM_PARTS)

static const char *PART_LABELS[PR53_NUM_PARTS] =
    { "DRUMS","AC3","AC2","AC1","BASS","LEFT","R2","R1" };

// Cached last-rendered state for dirty diffing.
static DisplayState last;
static bool have_last = false;

// ---- small helpers over the font module ----
// draw_text/draw_digits are provided by pr53_font.{h,c}: they render into the
// panel using COL_SEG on COL_FIELD, at a given pixel origin & scale.

// Clear a field's rectangle to the backlight color before repainting text.
static void clear_field(int x, int y, int w, int h) {
    ili9488_fill_rect(x, y, w, h, COL_FIELD);
}

// ========================= STATIC FURNITURE =========================
void render_static(void) {
    // Whole backlight field.
    ili9488_fill_rect(0, 0, ILI_W, ILI_H, COL_FIELD);

    // Zone rules.
    ili9488_fill_rect(PAD, Z_TOP, ILI_W - 2*PAD, 1, COL_RULE);
    ili9488_fill_rect(PAD, Z_MID, ILI_W - 2*PAD, 1, COL_RULE);

    // TOP: static labels + boxes
    font_text(PAD, 8, "TEMPO", 1, COL_SEG);
    font_text(PAD, 40, "\x01=", 2, COL_SEG);  // \x01 = quarter-note glyph in font

    // chord box
    font_box(230, 12, 120, 56, COL_RULE);
    // transpose box
    font_box(360, 12, 110, 56, COL_RULE);
    font_text(378, 16, "TRANSPOSE", 1, COL_SEG);

    // MIDDLE: small-display gutter boxes + RIGHT1/RHYTHM labels + icons
    font_box(SMALL_X, 108, SMALL_W, 26, COL_RULE);
    font_box(SMALL_X, 150, SMALL_W, 26, COL_RULE);
    font_text(LABEL_X, 112, "RIGHT 1", 1, COL_SEG);
    font_text(LABEL_X, 154, "RHYTHM",  1, COL_SEG);
    font_kbd_icon(LABEL_X + 66, 110, COL_RULE);
    font_drum_icon(LABEL_X + 66, 152, COL_RULE);

    // BOTTOM: printed panel labels (never change).
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        int cx = BOT_LEFT + COL_W * p + COL_W/2;
        font_text_centered(cx, ILI_H - 14, PART_LABELS[p], 1, COL_PRINT);
    }

    have_last = false;   // force a full field repaint on first frame
}

// ========================= PER-FRAME DIFF =========================
static void draw_tempo(int tempo) {
    clear_field(PAD + 34, 36, 110, 40);
    char buf[8];
    if (tempo < 0) { font_text(PAD + 34, 40, "---", 3, COL_SEG_OFF); return; }
    font_itoa(buf, tempo);
    font_text(PAD + 34, 40, buf, 3, COL_SEG);
}

static void draw_chord(const char *chord) {
    clear_field(232, 24, 116, 40);
    if (chord[0])
        font_text_centered(290, 30, chord, 3, COL_SEG);
    else
        font_text_centered(290, 34, "--", 2, COL_SEG_OFF);
}

static void draw_transpose(const char *note, bool sharp) {
    clear_field(362, 30, 106, 36);
    char buf[6]; int i = 0;
    if (note[0]) { buf[i++] = note[0]; if (sharp) buf[i++] = '#'; }
    buf[i] = 0;
    font_text_centered(410, 34, i ? buf : "\x01", 2, i ? COL_SEG : COL_SEG_OFF);
}

static void draw_line(int y, const char *text) {
    clear_field(TEXT_X, y, ILI_W - PAD - TEXT_X, 30);
    if (text[0]) font_text(TEXT_X, y, text, 2, COL_SEG);
}

static void draw_small(int box_y, uint8_t val) {
    clear_field(SMALL_X + 2, box_y + 2, SMALL_W - 4, 22);
    char buf[4];
    if (val == 0xFF) { font_text_centered(SMALL_X + SMALL_W/2, box_y + 4, "--", 2, COL_SEG_OFF); return; }
    buf[0] = '0' + (val / 10) % 10;
    buf[1] = '0' + val % 10;
    buf[2] = 0;
    font_text_centered(SMALL_X + SMALL_W/2, box_y + 4, buf, 2, COL_SEG);
}

static void draw_meter(int part, int level) {
    int cx = BOT_LEFT + COL_W * part + COL_W/2;
    const int bars = 6, bw = 30, bh = 5, gap = 3;
    int top = Z_MID + 10;
    for (int i = 0; i < bars; i++) {
        int y = top + (bars - 1 - i) * (bh + gap);
        uint16_t c = (i < level) ? COL_SEG : COL_FIELD;
        ili9488_fill_rect(cx - bw/2, y, bw, bh, c);
        // thin outline so unlit bars still read as ghost cells
        if (i >= level) {
            ili9488_fill_rect(cx - bw/2, y, bw, 1, COL_SEG_OFF);
        }
    }
}

static void draw_number(int part, int value) {
    int cx = BOT_LEFT + COL_W * part + COL_W/2;
    int y = Z_MID + 10 + 6*(5+3) + 6;
    clear_field(cx - COL_W/2 + 2, y, COL_W - 4, 26);
    char buf[8];
    if (value < 0) { font_text_centered(cx, y, "---", 2, COL_SEG_OFF); return; }
    font_itoa(buf, value);
    font_text_centered(cx, y, buf, 2, COL_SEG);
    // down arrow beneath
    font_text_centered(cx, y + 24, "\x02", 1, COL_SEG);  // \x02 = down-arrow glyph
}

void render_frame(const DisplayState *s) {
    bool first = !have_last;

    // TOP zone
    if (first || s->tempo != last.tempo) draw_tempo(s->tempo);
    if (first || strcmp(s->chord, last.chord)) draw_chord(s->chord);
    if (first || strcmp(s->transpose, last.transpose) ||
        s->transpose_sharp != last.transpose_sharp)
        draw_transpose(s->transpose, s->transpose_sharp);

    // MIDDLE zone
    if (first || strcmp(s->line1, last.line1)) draw_line(140, s->line1);
    if (first || strcmp(s->line2, last.line2)) draw_line(178, s->line2);
    if (first || s->small_top != last.small_top) draw_small(108, s->small_top);
    if (first || s->small_bot != last.small_bot) draw_small(150, s->small_bot);

    // BOTTOM zone
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        if (first || s->part_level[p] != last.part_level[p])
            draw_meter(p, s->part_level[p]);
        if (first || s->part_value[p] != last.part_value[p])
            draw_number(p, s->part_value[p]);
    }

    last = *s;
    have_last = true;
}
