// pr53_decode.c — HD44780 emulation + segment decoders.
// Faithful port of pr53_display.py. See that file for the reverse-engineering
// rationale behind every magic number here.

#include "pr53_decode.h"
#include <string.h>

// ---------------------------------------------------------------------------
// Segment tables (ported verbatim from pr53_display.py)
// ---------------------------------------------------------------------------
// Segments are encoded as bits in a uint8_t: a=1<<0, b=1<<1, c=1<<2,
// d=1<<3, e=1<<4, f=1<<5, g=1<<6.
enum { SA=1<<0, SB=1<<1, SC=1<<2, SD=1<<3, SE=1<<4, SF=1<<5, SG=1<<6 };

// TEMPO digits use rows 0-5 + 7 (row 6 unused). ROW_TO_SEG in Python.
// row -> segment bit, or 0 if that row is unused for this readout.
static const uint8_t TEMPO_ROW_SEG[8] = {
    SA, SB, SF, SG, SC, SE, 0, SD    // rows 0,1,2,3,4,5,(6 unused),7
};

// BARGRAPH digits use rows 0-6 (row 7 unused). BARGRAPH_ROW_TO_SEG in Python.
static const uint8_t BAR_ROW_SEG[8] = {
    SA, SB, SF, SG, SC, SE, SD, 0    // rows 0,1,2,3,4,5,6,(7 unused)
};

// Map a set-of-segments bitmask to a digit char, or '?' if unknown, ' ' if empty.
// Mirrors DIGIT_TABLE. Note both '1' variants (b+c and b+f) and both '2','7'
// variants are folded in.
static char segs_to_digit(uint8_t s) {
    switch (s) {
        case 0:                               return ' ';
        case (SA|SB|SC|SD|SE|SF):             return '0';
        case (SB|SC):                          return '1';
        case (SB|SF):                          return '1';
        case (SA|SB|SD|SE|SG):                return '2';
        case (SA|SB|SG):                       return '2';
        case (SA|SB|SC|SD|SG):                return '3';
        case (SB|SC|SF|SG):                   return '4';
        case (SA|SC|SD|SF|SG):                return '5';
        case (SA|SC|SD|SE|SF|SG):             return '6';
        case (SA|SB|SC|SF):                   return '7';
        case (SA|SB|SC|SD|SE|SF|SG):          return '8';
        case (SA|SB|SC|SD|SF|SG):             return '9';
        default:                               return '?';
    }
}

// CHORD_LETTER_TABLE — chord root / transpose note letters (shared font).
static char segs_to_letter(uint8_t s) {
    switch (s) {
        case 0:                               return ' ';
        case (SA|SF):                          return 'C';
        case (SA|SC|SD|SE|SF):                return 'D';
        case (SA|SB|SF|SG):                   return 'E';
        case (SB|SF|SG):                       return 'F';
        case (SA|SC|SD|SE|SF|SG):             return 'G';
        case (SA|SB|SC|SD|SE|SF|SG):          return 'A';  // note: Python 'A' = b,c,d,e,f,g
        case (SB|SC|SD|SE|SF|SG):             return 'A';
        case (SA|SB|SC|SD|SE|SF):             return 'B';  // placeholder; see note
        case (SA|SB|SC|SD|SF|SG):             return 'B';
        default:                               return 0;    // unknown letter
    }
}

// ---- Bargraph number map: [hundreds, tens, ones] as (char,col); -1 = none ----
// Ported from BARGRAPH_NUMBER_MAP. Each entry: {h_char,h_col, t_char,t_col,
// o_char,o_col}. A char of -1 means that digit isn't mapped (blank).
typedef struct { int8_t ch, col; } CellRef;
static const CellRef NUMBER_MAP[PR53_NUM_PARTS][3] = {
    // {hundreds},           {tens},    {ones}
    { {-1,-1}, {4,0}, {5,2} },  // P1 DRUMS
    { {-1,-1}, {4,1}, {5,1} },  // P2 AC3
    { {-1,-1}, {4,2}, {7,4} },  // P3 AC2
    { {-1,-1}, {4,3}, {7,3} },  // P4 AC1
    { {-1,-1}, {4,4}, {7,2} },  // P5 BASS
    { {-1,-1}, {-1,-1}, {3,2} },// P6 LEFT  (tens unknown)
    { {-1,-1}, {2,4}, {3,0} },  // P7 R2
    { {2,2},  {2,3}, {2,1} },   // P8 R1  (fully solved vs photo=127)
};

// (Bargraph meter levels are defined below as LEVELS[] with explicit rows.)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
static inline int cell_bit(const uint8_t *cgram, int ch, int row, int col) {
    return (cgram[ch * 8 + row] >> (4 - col)) & 1;
}

// Gather the segment bitmask for a (char,col) digit column using a row->seg map.
static uint8_t gather_segs(const uint8_t *cgram, int ch, int col,
                           const uint8_t *row_seg) {
    uint8_t s = 0;
    for (int r = 0; r < 8; r++) {
        if (cell_bit(cgram, ch, r, col)) s |= row_seg[r];
    }
    return s;
}

// Decode a single bargraph digit column, retrying with segment 'd' added if
// the first lookup fails (mirrors _decode_digit_segs(): Part 6/7 ones omit
// the bottom bar).
static char decode_digit_col(const uint8_t *cgram, int ch, int col) {
    uint8_t s = gather_segs(cgram, ch, col, BAR_ROW_SEG);
    char c = segs_to_digit(s);
    if (c == '?') {
        char c2 = segs_to_digit(s | SD);
        if (c2 != '?') return c2;
    }
    return c;
}

// ---------------------------------------------------------------------------
// Public decoders
// ---------------------------------------------------------------------------
int pr53_decode_tempo(const uint8_t *cgram) {
    // TEMPO_DIGITS = C1 c0, c1, c2
    int val = 0, seen = 0;
    for (int col = 0; col < 3; col++) {
        uint8_t s = gather_segs(cgram, 1, col, TEMPO_ROW_SEG);
        char c = segs_to_digit(s);
        if (c == ' ') continue;          // leading blank
        if (c < '0' || c > '9') return -1;
        val = val * 10 + (c - '0');
        seen = 1;
    }
    return seen ? val : -1;
}

bool pr53_decode_chord(const uint8_t *cgram, char out[4]) {
    // chord root letter lives in C5 c0, bargraph row convention.
    uint8_t s = gather_segs(cgram, 5, 0, BAR_ROW_SEG);
    char c = segs_to_letter(s);
    if (c == 0) { out[0] = 0; return false; }
    out[0] = (c == ' ') ? 0 : c;
    out[1] = 0;
    return out[0] != 0;
}

int pr53_decode_bargraph_number(const uint8_t *cgram, int part) {
    if (part < 0 || part >= PR53_NUM_PARTS) return -1;
    const CellRef *m = NUMBER_MAP[part];
    int val = 0, any = 0;
    for (int d = 0; d < 3; d++) {  // hundreds, tens, ones
        if (m[d].ch < 0) continue; // unmapped digit -> skip (acts as blank/0)
        char c = decode_digit_col(cgram, m[d].ch, m[d].col);
        if (c == ' ') continue;    // blank leading digit
        if (c < '0' || c > '9') return -1;   // undecodable -> whole number invalid
        // place value: fold in by shifting existing value. Because unmapped
        // higher digits are skipped, we accumulate left-to-right over the
        // digits that ARE present.
        val = val * 10 + (c - '0');
        any = 1;
    }
    return any ? val : -1;
}

// Bargraph meter level. In Python's BARGRAPH_LEVEL_MAP each part fills ONE
// CGRAM column bottom-up; level = count of lit rows. The structure: P1-5 use
// char C0 cols 0..4 (rows 5,4,3,2,1); P6 uses C6 col4; P7/P8 use C7 col0/col1
// (rows 7,6,5,4,3). Expressed cleanly as (char,col,rows[5]).
typedef struct { uint8_t ch, col; uint8_t rows[5]; } LevelDef;
static const LevelDef LEVELS[PR53_NUM_PARTS] = {
    {0,0,{5,4,3,2,1}}, {0,1,{5,4,3,2,1}}, {0,2,{5,4,3,2,1}},
    {0,3,{5,4,3,2,1}}, {0,4,{5,4,3,2,1}},
    {6,4,{7,6,5,4,3}}, {7,0,{7,6,5,4,3}}, {7,1,{7,6,5,4,3}},
};

static int level_count(const uint8_t *cgram, int part) {
    const LevelDef *L = &LEVELS[part];
    int n = 0;
    for (int i = 0; i < 5; i++)
        if (cell_bit(cgram, L->ch, L->rows[i], L->col)) n++;
    return n;
}

int pr53_decode_bargraph_level(const uint8_t *cgram, int part) {
    if (part < 0 || part >= PR53_NUM_PARTS) return 0;
    return level_count(cgram, part);
}

// ---------------------------------------------------------------------------
// HD44780 emulation
// ---------------------------------------------------------------------------
void hd44780_init(HD44780 *st) {
    memset(st, 0, sizeof(*st));
    memset(st->ddram, 0x20, sizeof(st->ddram)); // spaces
    st->display_on = false;
    st->entry_inc  = true;
}

// Apply a fully-reassembled command byte.
static bool apply_cmd(HD44780 *st, uint8_t b) {
    bool is_dispctrl = (b & 0xF8) == 0x08;
    if (b == 0x01) {
        memset(st->ddram, 0x20, sizeof(st->ddram));
        st->ac = 0; st->in_cgram = false;
    } else if (b <= 0x03) {
        st->ac = 0; st->in_cgram = false;
    } else if ((b & 0xFC) == 0x04) {
        st->entry_inc = (b & 0x02) != 0;
    } else if ((b & 0xF8) == 0x08) {
        st->display_on = (b & 0x04) != 0;   // DISP_CTRL bit2
    } else if ((b & 0xC0) == 0x40) {
        st->ac = b & 0x3F; st->in_cgram = true;
    } else if (b & 0x80) {
        st->ac = b & 0x7F; st->in_cgram = false;
        // NOTE: no line-clear here — piano space-pads its fields; leftovers
        // in the display mean dropped writes upstream, not a piano quirk.
    }
    return is_dispctrl;
}

static void apply_data(HD44780 *st, uint8_t b) {
    if (st->in_cgram) {
        if (st->ac < 64) st->cgram[st->ac] = b;
        st->ac = (st->ac + 1) & 0x3F;
    } else {
        if (st->ac < 128) st->ddram[st->ac] = b;
        st->ac = (st->ac + 1) & 0x7F;
    }
}

bool hd44780_feed(HD44780 *st, uint8_t byte, bool is_data) {
    if (is_data) { apply_data(st, byte); return false; }
    return apply_cmd(st, byte);   // true if DISP_CTRL commit
}

// ---------------------------------------------------------------------------
// Full-glass decode
// ---------------------------------------------------------------------------
static void copy_line(char *dst, const uint8_t *ddram, int off) {
    int j = 0;
    for (int i = 0; i < PR53_TEXT_LEN; i++) {
        uint8_t c = ddram[off + i];
        dst[i] = (c >= 32 && c < 127) ? (char)c : ' ';
    }
    dst[PR53_TEXT_LEN] = 0;
    // rstrip for display cleanliness (buffer already settled via 0x0C gate)
    for (j = PR53_TEXT_LEN - 1; j >= 0 && dst[j] == ' '; j--) dst[j] = 0;
}

void pr53_decode_all(const HD44780 *st, DisplayState *out) {
    const uint8_t *cg = st->cgram;

    out->tempo = pr53_decode_tempo(cg);

    char chord[4]; pr53_decode_chord(cg, chord);
    memcpy(out->chord, chord, sizeof(out->chord));

    // Transpose: reuse chord-letter font at C6 c3 + sharp bit C2:r6:c3.
    {
        uint8_t s = gather_segs(cg, 6, 3, BAR_ROW_SEG);
        char c = segs_to_letter(s);
        out->transpose[0] = (c && c != ' ') ? c : 0;
        out->transpose[1] = 0;
        out->transpose_sharp = cell_bit(cg, 2, 6, 3);
    }

    copy_line(out->line1, st->ddram, 0x00);
    copy_line(out->line2, st->ddram, 0x40);

    // Small displays not yet mapped -> blank.
    out->small_top = 0xFF;
    out->small_bot = 0xFF;

    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        int v = pr53_decode_bargraph_number(cg, p);
        out->part_value[p] = (int16_t)v;
        out->part_level[p] = (uint8_t)level_count(cg, p);
    }

    // Split indicators (RIGHT=C0:r7:c4, LEFT=C1:r7:c4)
    out->split_right = cell_bit(cg, 0, 7, 4);
    out->split_left  = cell_bit(cg, 1, 7, 4);
}
