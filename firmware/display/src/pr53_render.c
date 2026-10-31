// pr53_render.c — glass renderer with per-field dirty tracking.
//
// Layout follows the printed frame of the original SX-PR53 glass (480x320):
//   TOP ROW   (y 8..88):    TEMPO box | CHORD box | MENU/PAGE over TRANSPOSE
//   TEXT BOX  (y 96..198):  small 2-digit readout + 12-character line, x2
//   METERS    (y 206..312): 8 bargraphs and part numbers between two dotted
//                           rules, part names underneath
// Numbers are drawn as 7-segment digits with faint "ghost" segments, like the
// original LCD.
//
// render_static() paints everything that never changes ONCE. render_frame()
// diffs against last_* and repaints only fields that moved — so a single
// number ticking updates just that number's little rectangle.

#include "pr53_render.h"
#include "pr53_ili9486_par.h"
#include "pr53_font.h"
#include <string.h>

// ---- Geometry (480x320) ----
#define M        8                    // outer margin

// Top row
#define TOP_Y    M
#define TOP_H    80
#define TEMPO_X  M
#define TEMPO_W  160
#define CHORD_X  (TEMPO_X + TEMPO_W)
#define CHORD_W  200
#define RIGHT_X  (CHORD_X + CHORD_W)
#define RIGHT_W  (ILI_W - M - RIGHT_X)
#define HALF_H   (TOP_H / 2)

// Text box
#define TEXT_BOX_Y 96
#define TEXT_BOX_H 102
#define LINE1_Y    (TEXT_BOX_Y + 12)
#define LINE2_Y    (TEXT_BOX_Y + 58)
#define SMALL_X    (M + 10)
#define TEXT_X     (M + 64)
#define TEXT_SCALE 4                  // 5x7 font at x4: 24 px advance, 28 px tall

// Meter strip
#define RULE1_Y  206
#define BARS_Y   212                  // top of the tallest bar
#define BAR_H    6
#define BAR_GAP  3
#define NUM_Y    260
#define RULE2_Y  296
#define LABEL_Y  302
#define COL_W    ((ILI_W - 2*M) / PR53_NUM_PARTS)

static const char *PART_LABELS[PR53_NUM_PARTS] =
    { "DRUMS","AC3","AC2","AC1","BASS","LEFT","R2","R1" };

// Cached last-rendered state for dirty diffing.
static DisplayState last;
static bool have_last = false;

// ========================= PRIMITIVES =========================
static void clear_field(int x, int y, int w, int h) {
    ili9488_fill_rect(x, y, w, h, COL_FIELD);
}

static void dotted_rule(int x, int y, int w) {
    for (int i = 0; i < w; i += 5) ili9488_fill_rect(x + i, y, 2, 2, COL_RULE);
}

// 7-segment digit: a top, b top-right, c bottom-right, d bottom,
// e bottom-left, f top-left, g middle. Unlit segments are drawn as ghosts.
enum { SA = 1, SB = 2, SC = 4, SD = 8, SE = 16, SF = 32, SG = 64 };

static uint8_t seg_mask(char c) {
    switch (c) {
        case '0': return SA|SB|SC|SD|SE|SF;
        case '1': return SB|SC;
        case '2': return SA|SB|SD|SE|SG;
        case '3': return SA|SB|SC|SD|SG;
        case '4': return SB|SC|SF|SG;
        case '5': return SA|SC|SD|SF|SG;
        case '6': return SA|SC|SD|SE|SF|SG;
        case '7': return SA|SB|SC;
        case '8': return SA|SB|SC|SD|SE|SF|SG;
        case '9': return SA|SB|SC|SD|SF|SG;
        case '-': return SG;
        default:  return 0;
    }
}

static void seg7(int x, int y, int w, int h, int t, char c, bool ghost) {
    uint8_t on = seg_mask(c);
    uint16_t off = ghost ? COL_SEG_OFF : COL_FIELD;
    int mid = y + (h - t) / 2;
    struct { uint8_t bit; int x, y, w, h; } s[7] = {
        { SA, x + t,     y,         w - 2*t, t },
        { SB, x + w - t, y + t,     t,       mid - y - t },
        { SC, x + w - t, mid + t,   t,       y + h - t - mid - t },
        { SD, x + t,     y + h - t, w - 2*t, t },
        { SE, x,         mid + t,   t,       y + h - t - mid - t },
        { SF, x,         y + t,     t,       mid - y - t },
        { SG, x + t,     mid,       w - 2*t, t },
    };
    for (int i = 0; i < 7; i++)
        ili9488_fill_rect(s[i].x, s[i].y, s[i].w, s[i].h,
                          (on & s[i].bit) ? COL_SEG : off);
}

// Right-aligned number in n 7-segment cells; v < 0 shows no digits. With
// ghost set, unlit segments show faintly, like the original LCD.
static void seg7_number(int x, int y, int n, int w, int h, int t, int gap, int v,
                        bool ghost) {
    char buf[8];
    for (int i = 0; i < n; i++) buf[i] = ' ';
    buf[n] = 0;
    if (v >= 0) {
        for (int i = n - 1; i >= 0; i--) {
            buf[i] = (char)('0' + v % 10);
            v /= 10;
            if (!v) break;
        }
    }
    for (int i = 0; i < n; i++) seg7(x + i * (w + gap), y, w, h, t, buf[i], ghost);
}

// ========================= STATIC FURNITURE =========================
void render_static(void) {
    ili9488_fill_rect(0, 0, ILI_W, ILI_H, COL_FIELD);

    // Top row, as printed on the glass: three boxes, the right one split.
    font_box(TEMPO_X, TOP_Y, TEMPO_W, TOP_H, COL_RULE);
    font_box(CHORD_X, TOP_Y, CHORD_W, TOP_H, COL_RULE);
    font_box(RIGHT_X, TOP_Y, RIGHT_W, HALF_H, COL_RULE);
    // lower box starts on the upper box's bottom line, so they share one rule
    font_box(RIGHT_X, TOP_Y + HALF_H - 1, RIGHT_W, TOP_H - HALF_H + 1, COL_RULE);
    font_text(TEMPO_X + 6, TOP_Y + 5, "TEMPO", 1, COL_PRINT);
    font_text(CHORD_X + 6, TOP_Y + 5, "CHORD", 1, COL_PRINT);
    font_text(RIGHT_X + 6, TOP_Y + 5, "PAGE", 1, COL_PRINT);
    font_text(RIGHT_X + 6, TOP_Y + HALF_H + 5, "TRANSPOSE", 1, COL_PRINT);

    // Text box with its two lines.
    font_box(M, TEXT_BOX_Y, ILI_W - 2*M, TEXT_BOX_H, COL_RULE);

    // Meter strip between two dotted rules, part names underneath.
    dotted_rule(M, RULE1_Y, ILI_W - 2*M);
    dotted_rule(M, RULE2_Y, ILI_W - 2*M);
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        int cx = M + COL_W * p + COL_W / 2;
        font_text_centered(cx, LABEL_Y, PART_LABELS[p], 1, COL_PRINT);
    }

    have_last = false;   // force a full field repaint on first frame
}

// ========================= PER-FRAME DIFF =========================
static void draw_tempo(int tempo) {
    // three 7-seg cells, 30x50, right half of the TEMPO box
    seg7_number(TEMPO_X + 40, TOP_Y + 20, 3, 30, 50, 6, 9, tempo, true);
}

static void draw_chord(const char *chord) {
    clear_field(CHORD_X + 2, TOP_Y + 16, CHORD_W - 4, TOP_H - 18);
    if (chord[0])
        font_text_centered(CHORD_X + CHORD_W / 2, TOP_Y + 26, chord, 6, COL_SEG);
}

static void draw_transpose(const char *note, bool sharp) {
    int y = TOP_Y + HALF_H;
    clear_field(RIGHT_X + 2, y + 15, RIGHT_W - 4, HALF_H - 17);
    char buf[4]; int i = 0;
    if (note[0]) { buf[i++] = note[0]; if (sharp) buf[i++] = '#'; }
    buf[i] = 0;
    if (i) font_text_centered(RIGHT_X + RIGHT_W / 2, y + 17, buf, 3, COL_SEG);
}

static void draw_line(int y, const char *text) {
    clear_field(TEXT_X, y, ILI_W - M - 4 - TEXT_X, 7 * TEXT_SCALE);
    if (text[0]) font_text(TEXT_X, y, text, TEXT_SCALE, COL_SEG);
}

static void draw_small(int y, uint8_t val) {
    // two 7-seg cells, 18x28, left of the text line
    seg7_number(SMALL_X, y, 2, 18, 28, 4, 6, val == 0xFF ? -1 : val, true);
}

static void draw_meter(int part, int level) {
    int cx = M + COL_W * part + COL_W / 2;
    const int bars = 5, bw = 34;
    for (int i = 0; i < bars; i++) {
        int y = BARS_Y + (bars - 1 - i) * (BAR_H + BAR_GAP);
        ili9488_fill_rect(cx - bw/2, y, bw, BAR_H, (i < level) ? COL_SEG : COL_SEG_OFF);
    }
}

static void draw_number(int part, int value) {
    // three 7-seg cells, 12x24, centred in the part's column; no ghosts, so
    // neighbouring columns stay apart
    int w = 12, gap = 5, total = 3 * w + 2 * gap;
    int x = M + COL_W * part + (COL_W - total) / 2;
    seg7_number(x, NUM_Y, 3, w, 24, 3, gap, value, false);
}

void render_frame(const DisplayState *s) {
    bool first = !have_last;

    // Top row
    if (first || s->tempo != last.tempo) draw_tempo(s->tempo);
    if (first || strcmp(s->chord, last.chord)) draw_chord(s->chord);
    if (first || strcmp(s->transpose, last.transpose) ||
        s->transpose_sharp != last.transpose_sharp)
        draw_transpose(s->transpose, s->transpose_sharp);

    // Text box
    if (first || strcmp(s->line1, last.line1)) draw_line(LINE1_Y, s->line1);
    if (first || strcmp(s->line2, last.line2)) draw_line(LINE2_Y, s->line2);
    if (first || s->small_top != last.small_top) draw_small(LINE1_Y, s->small_top);
    if (first || s->small_bot != last.small_bot) draw_small(LINE2_Y, s->small_bot);

    // Meter strip
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        if (first || s->part_level[p] != last.part_level[p])
            draw_meter(p, s->part_level[p]);
        if (first || s->part_value[p] != last.part_value[p])
            draw_number(p, s->part_value[p]);
    }

    last = *s;
    have_last = true;
}
