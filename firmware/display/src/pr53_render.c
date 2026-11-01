// pr53_render.c — glass renderer with per-field dirty tracking.
//
// Layout follows the original SX-PR53 glass (owner's manual p. 19-21, 32, and
// a photo of a working unit), scaled to 480x320:
//   TOP ROW   (y 4..74):   TEMPO box | CHORD box (+ transpose key at its right
//                          end) | PAGE box over TRANSPOSE box
//   TEXT BOX  (y 80..190): RIGHT 1 / RHYTHM labels with icons on the left
//                          (normal display only), two 12-character lines in a
//                          dot-matrix font on the right
//   METERS    (y 196..300): 8 wedge-shaped bargraphs between two dotted rules,
//                          slanted 7-segment part numbers, a pointer under each
// render_static() paints everything that never changes ONCE. render_frame()
// diffs against last_* and repaints only fields that moved.

#include "pr53_render.h"
#include "pr53_ili9486_par.h"
#include "pr53_font.h"
#include <string.h>

// ---- Geometry (480x320) ----
#define M        4                    // outer margin

// Top row
#define TOP_Y    M
#define TOP_H    70
#define TEMPO_X  M
#define TEMPO_W  136
#define CHORD_X  (TEMPO_X + TEMPO_W - 1)
#define CHORD_W  242
#define RIGHT_X  (CHORD_X + CHORD_W - 1)
#define RIGHT_W  (ILI_W - M - RIGHT_X)
#define HALF_H   (TOP_H / 2)

// Text box
#define TEXT_BOX_Y 80
#define TEXT_BOX_H 110
#define LABEL_X    (M + 8)
#define LINE1_Y    (TEXT_BOX_Y + 14)
#define LINE2_Y    (TEXT_BOX_Y + 66)
#define READOUT_X  (TEXT_X - 50)       // page / item readouts, just left of the text
#define TEXT_SCALE 4                  // 5x7 font at x4: 24 px advance, 28 px tall
#define TEXT_X     (ILI_W - M - 6 - 12 * 6 * TEXT_SCALE + TEXT_SCALE)

// Meter strip
#define RULE1_Y  198
#define BARS_Y   201                  // top of the widest (top) bar
#define BAR_H    4
#define BAR_GAP  3
#define RULE2_Y  (BARS_Y + 4 * (BAR_H + BAR_GAP) + BAR_H + 1)   // just below the fifth bar
#define NUM_Y    248
#define PTR_Y    282
#define COL_W    ((ILI_W - 2*M) / PR53_NUM_PARTS)

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

// Quarter note for "TEMPO ♩=": oval head with a stem, 8x16.
static void note_icon(int x, int y, uint16_t color) {
    ili9488_fill_rect(x + 1, y + 11, 5, 1, color);
    ili9488_fill_rect(x,     y + 12, 7, 3, color);
    ili9488_fill_rect(x + 1, y + 15, 5, 1, color);
    ili9488_fill_rect(x + 6, y,      1, 13, color);
}

// Downward pointer (the glass's ▼ under each part), w wide, w/2 tall.
static void pointer(int cx, int y, int w, uint16_t color) {
    for (int r = 0; r < w / 2; r++) {
        int half = w / 2 - r;
        ili9488_fill_rect(cx - half, y + r, 2 * half, 1, color);
    }
}

// Upward pointer (the PAGE arrow for a following page), w wide, w/2 tall.
static void pointer_up(int cx, int y, int w, uint16_t color) {
    for (int r = 0; r < w / 2; r++)
        ili9488_fill_rect(cx - r - 1, y + r, 2 * (r + 1), 1, color);
}

// Slanted 7-segment digit: a top, b top-right, c bottom-right, d bottom,
// e bottom-left, f top-left, g middle. Each row shifts right as it rises, by
// `slant` px over the digit's height. With `ghost` set, unlit segments show
// faintly; the original glass shows nothing, so the layout doesn't use it.
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
        case 'P': return SA|SB|SE|SF|SG;
        default:  return 0;
    }
}

static void slanted_rect(int x, int y, int w, int h, int top, int dh, int slant,
                         uint16_t color) {
    // (top, dh) = the digit's top row and height, for the slant offset
    for (int r = 0; r < h; r++) {
        int row = y + r;
        int off = slant * (top + dh - 1 - row) / dh;
        ili9488_fill_rect(x + off, row, w, 1, color);
    }
}

static void seg7(int x, int y, int w, int h, int t, int slant, char c, bool ghost) {
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
        slanted_rect(s[i].x, s[i].y, s[i].w, s[i].h, y, h, slant,
                     (on & s[i].bit) ? COL_SEG : off);
}

// Right-aligned number in n slanted 7-segment cells. v == -1 shows no
// digits; v == -2 shows "---" (a muted part).
static void seg7_number(int x, int y, int n, int w, int h, int t, int gap, int slant,
                        int v, bool ghost) {
    char buf[8];
    for (int i = 0; i < n; i++) buf[i] = (v == -2) ? '-' : ' ';
    buf[n] = 0;
    if (v >= 0) {
        for (int i = n - 1; i >= 0; i--) {
            buf[i] = (char)('0' + v % 10);
            v /= 10;
            if (!v) break;
        }
    }
    clear_field(x, y, n * w + (n - 1) * gap + slant + 1, h);
    for (int i = 0; i < n; i++)
        seg7(x + i * (w + gap), y, w, h, t, slant, buf[i], ghost);
}

// ========================= SCREEN STATE =========================
// The glass shows the RIGHT 1 / RHYTHM labels, and "---" for a muted part, on
// the normal display, and hides them (with the meters) on RHYTHM and menu
// screens. Until the label segments are mapped, take "any part has a volume
// shown" to mean the normal display. (The pointers are decoded per part.)
static bool normal_display(const DisplayState *s) {
    for (int p = 0; p < PR53_NUM_PARTS; p++)
        if (s->part_value[p] >= 0) return true;
    return false;
}

// ========================= STATIC FURNITURE =========================
void render_static(void) {
    ili9488_fill_rect(0, 0, ILI_W, ILI_H, COL_FIELD);

    // Top row, as printed on the glass: three boxes, the right one split.
    font_box(TEMPO_X, TOP_Y, TEMPO_W, TOP_H, COL_RULE);
    font_box(CHORD_X, TOP_Y, CHORD_W, TOP_H, COL_RULE);
    font_box(RIGHT_X, TOP_Y, RIGHT_W, HALF_H, COL_RULE);
    font_box(RIGHT_X, TOP_Y + HALF_H - 1, RIGHT_W, TOP_H - HALF_H + 1, COL_RULE);
    font_text(TEMPO_X + 6, TOP_Y + 5, "TEMPO", 1, COL_PRINT);
    note_icon(TEMPO_X + 7, TOP_Y + 40, COL_SEG);
    font_text(TEMPO_X + 18, TOP_Y + 46, "=", 2, COL_SEG);

    // Text box.
    font_box(M, TEXT_BOX_Y, ILI_W - 2*M, TEXT_BOX_H, COL_RULE);

    // Meter strip: two dotted rules through the bargraphs.
    dotted_rule(M, RULE1_Y, ILI_W - 2*M);
    dotted_rule(M, RULE2_Y, ILI_W - 2*M);

    have_last = false;   // force a full field repaint on first frame
}

// ========================= PER-FRAME DIFF =========================
static void draw_tempo(int tempo) {
    seg7_number(TEMPO_X + 40, TOP_Y + 12, 3, 24, 50, 5, 5, 6, tempo, false);
}

static void draw_chord(const char *chord) {
    // root letter and flat/sharp, left part of the box
    clear_field(CHORD_X + 2, TOP_Y + 2, 168, TOP_H - 4);
    if (chord[0]) font_text(CHORD_X + 14, TOP_Y + 14, chord, 6, COL_SEG);
}

static void draw_transpose(const char *note) {
    // actual key at the right end of the CHORD box, "TRANSPOSE" beside it
    int kx = CHORD_X + CHORD_W - 66;
    clear_field(kx, TOP_Y + 2, 64, TOP_H - 4);
    clear_field(RIGHT_X + 2, TOP_Y + HALF_H + 1, RIGHT_W - 4, TOP_H - HALF_H - 3);
    if (!note[0]) return;
    font_text(kx + 4, TOP_Y + 20, note, 5, COL_SEG);
    font_text(RIGHT_X + 6, TOP_Y + HALF_H + 13, "TRANSPOSE", 1, COL_SEG);
}

// MENU and PAGE words with the PAGE arrows, in the top-right upper box
static void draw_page_box(bool menu, bool page, bool up, bool down) {
    clear_field(RIGHT_X + 2, TOP_Y + 2, RIGHT_W - 4, HALF_H - 4);
    if (menu) font_text(RIGHT_X + 8, TOP_Y + 7, "MENU", 1, COL_SEG);
    if (page) font_text(RIGHT_X + 8, TOP_Y + 21, "PAGE", 1, COL_SEG);
    if (up)   pointer_up(RIGHT_X + 48, TOP_Y + 22, 12, COL_SEG);
    if (down) pointer(RIGHT_X + 64, TOP_Y + 22, 12, COL_SEG);
}

// A two-cell 7-segment readout just left of a text line: the menu page
// ("P1") beside line 1, the item number beside line 2.
static void draw_readout(int y, const char *s) {
    int w = 14, h = 28, gap = 4, slant = 3;
    clear_field(READOUT_X, y, 2 * w + gap + slant + 1, h);
    for (int i = 0; i < 2 && s[i]; i++)
        seg7(READOUT_X + i * (w + gap), y, w, h, 3, slant, s[i], false);
}

static void draw_line(int y, const char *text) {
    clear_field(TEXT_X, y, ILI_W - M - 4 - TEXT_X, 7 * TEXT_SCALE);
    // character positions as the piano wrote them (it pads with spaces)
    if (text[0]) font_text_dots(TEXT_X, y, text, TEXT_SCALE, COL_SEG);
}

static void draw_labels(bool show) {
    clear_field(LABEL_X, TEXT_BOX_Y + 4, 110, TEXT_BOX_H - 8);
    if (!show) return;
    font_text(LABEL_X, LINE1_Y + 6, "RIGHT 1", 1, COL_SEG);
    font_kbd_icon(LABEL_X + 50, LINE1_Y + 2, COL_SEG);
    ili9488_fill_rect(LABEL_X, TEXT_BOX_Y + TEXT_BOX_H / 2, 100, 1, COL_RULE);
    font_text(LABEL_X, LINE2_Y + 6, "RHYTHM", 1, COL_SEG);
    font_drum_icon(LABEL_X + 50, LINE2_Y + 2, COL_SEG);
}

static void draw_meter(int part, int level) {
    // five bars, widest at the top, like the glass
    int cx = M + COL_W * part + COL_W / 2;
    for (int i = 0; i < 5; i++) {               // i = 0 is the top bar
        int bw = 44 - 4 * i;
        int y = BARS_Y + i * (BAR_H + BAR_GAP);
        bool lit = (5 - i) <= level;
        ili9488_fill_rect(cx - 22, y, 44, BAR_H, COL_FIELD);
        if (lit) ili9488_fill_rect(cx - bw/2, y, bw, BAR_H, COL_SEG);
    }
}

static void draw_number(int part, int value, bool dashes, bool pointer_on) {
    int w = 12, gap = 4, slant = 3, total = 3 * w + 2 * gap + slant;
    int x = M + COL_W * part + (COL_W - total) / 2;
    // on the normal display a part without a readable volume shows "---",
    // as the glass does for a muted part
    seg7_number(x, NUM_Y, 3, w, 24, 3, gap, slant,
                (value < 0 && dashes) ? -2 : value, false);
    int cx = M + COL_W * part + COL_W / 2;
    clear_field(cx - 9, PTR_Y, 18, 9);
    if (pointer_on) pointer(cx, PTR_Y, 16, COL_SEG);
}

void render_frame(const DisplayState *s) {
    bool first = !have_last;
    bool normal = normal_display(s);
    bool was_normal = first ? !normal : normal_display(&last);

    // Top row
    if (first || s->tempo != last.tempo) draw_tempo(s->tempo);
    if (first || strcmp(s->chord, last.chord)) draw_chord(s->chord);
    if (first || strcmp(s->transpose, last.transpose))
        draw_transpose(s->transpose);
    if (first || s->menu_word != last.menu_word || s->page_word != last.page_word ||
        s->page_up != last.page_up || s->page_down != last.page_down)
        draw_page_box(s->menu_word, s->page_word, s->page_up, s->page_down);

    // Text box
    if (first || normal != was_normal) draw_labels(normal);
    if (first || strcmp(s->page, last.page)) draw_readout(LINE1_Y, s->page);
    if (first || strcmp(s->item, last.item)) draw_readout(LINE2_Y, s->item);
    if (first || strcmp(s->line1, last.line1)) draw_line(LINE1_Y, s->line1);
    if (first || strcmp(s->line2, last.line2)) draw_line(LINE2_Y, s->line2);

    // Meter strip
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        if (first || s->part_level[p] != last.part_level[p])
            draw_meter(p, s->part_level[p]);
        if (first || s->part_value[p] != last.part_value[p] || normal != was_normal ||
            s->pointer[p] != last.pointer[p])
            draw_number(p, s->part_value[p], normal, s->pointer[p]);
    }

    last = *s;
    have_last = true;
}
