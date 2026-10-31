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
        case (SA|SD|SE|SF|SG):                return 'G';  // measured 2026-10-31
        case (SA|SC|SD|SE|SF|SG):             return 'G';  // earlier guess, kept
        case (SB|SC|SD|SE|SF|SG):             return 'A';  // measured 2026-10-31
        case (SA|SB|SC|SD|SF|SG):             return 'B';  // measured 2026-10-31
        default:                               return 0;    // unknown letter
    }
}

// ---- Part numbers ----
// P1-P5 digits use the bargraph row order, and their hundreds place is a lone
// "1": one bit, kept away from the digits in row 6 of C1 and C3. P6-P8 sit in
// C2/C3, whose digits put d on row 7 like the tempo, and have a full hundreds
// digit, so a part that's switched off shows "---". Worked out from the volume
// sweeps in captures/session_071830.log and the campaign log.
typedef struct {
    int8_t h_ch, h_row, h_col;   // h_row >= 0: a lone "1" at that bit; -1: a digit
    int8_t t_ch, t_col, o_ch, o_col;
    const uint8_t *rows;         // row -> segment order of the digits
} NumberDef;
static const NumberDef NUMBERS[PR53_NUM_PARTS] = {
    // hundreds     tens   ones
    { 1, 6, 2,      4, 0,  5, 2,  BAR_ROW_SEG   },  // P1 DRUMS
    { 1, 6, 1,      4, 1,  5, 1,  BAR_ROW_SEG   },  // P2 AC3
    { 3, 6, 4,      4, 2,  7, 4,  BAR_ROW_SEG   },  // P3 AC2
    { 3, 6, 3,      4, 3,  7, 3,  BAR_ROW_SEG   },  // P4 AC1
    { 3, 6, 2,      4, 4,  7, 2,  BAR_ROW_SEG   },  // P5 BASS
    { 3, -1, 4,     3, 3,  3, 2,  TEMPO_ROW_SEG },  // P6 LEFT
    { 2, -1, 4,     3, 0,  3, 1,  TEMPO_ROW_SEG },  // P7 R2
    { 2, -1, 2,     2, 3,  2, 1,  TEMPO_ROW_SEG },  // P8 R1
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

static char digit_at(const uint8_t *cgram, int ch, int col, const uint8_t *rows) {
    return segs_to_digit(gather_segs(cgram, ch, col, rows));
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
        // Rows 6-7 of the hundreds column also carry the chord's flat/sharp
        // (row 7 maps to SD). If the column doesn't read as a digit, try again
        // without that row; no flat/sharp combination looks like a digit.
        if (col == 0 && c == '?') c = segs_to_digit(s & (uint8_t)~SD);
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
    if (c == 0 || c == ' ') { out[0] = 0; return false; }
    out[0] = c;
    // Accidental in the tempo hundreds column (C1 c0): row 7 alone is a flat,
    // rows 6+7 a sharp. The piano spells Db, Eb, F#, Ab, Bb.
    int r6 = cell_bit(cgram, 1, 6, 0), r7 = cell_bit(cgram, 1, 7, 0);
    out[1] = (r6 && r7) ? '#' : r7 ? 'b' : 0;
    out[2] = 0;
    return true;
}

int pr53_decode_bargraph_number(const uint8_t *cgram, int part) {
    if (part < 0 || part >= PR53_NUM_PARTS) return -1;
    const NumberDef *n = &NUMBERS[part];
    char d[3];
    d[0] = (n->h_row >= 0) ? (cell_bit(cgram, n->h_ch, n->h_row, n->h_col) ? '1' : ' ')
                           : digit_at(cgram, n->h_ch, n->h_col, n->rows);
    d[1] = digit_at(cgram, n->t_ch, n->t_col, n->rows);
    d[2] = digit_at(cgram, n->o_ch, n->o_col, n->rows);
    int val = 0, any = 0;
    for (int i = 0; i < 3; i++) {
        if (d[i] == ' ' && !any) continue;          // leading blank
        if (d[i] < '0' || d[i] > '9') return -1;    // "---", a gap, or not a digit
        val = val * 10 + (d[i] - '0');
        any = 1;
    }
    return any ? val : -1;
}

// Bargraph meter level. In Python's BARGRAPH_LEVEL_MAP each part fills ONE
// CGRAM column bottom-up; level = count of lit rows. The structure: P1-5 use
// char C0 cols 0..4 (rows 5,4,3,2,1); P6 uses C6 col4; P7/P8 use C7 col0/col1
// (rows 6,5,4,3,2; row 7 of those columns stays lit whatever the level, even at
// 0, so it isn't a bar). Expressed cleanly as (char,col,rows[5]).
typedef struct { uint8_t ch, col; uint8_t rows[5]; } LevelDef;
static const LevelDef LEVELS[PR53_NUM_PARTS] = {
    {0,0,{5,4,3,2,1}}, {0,1,{5,4,3,2,1}}, {0,2,{5,4,3,2,1}},
    {0,3,{5,4,3,2,1}}, {0,4,{5,4,3,2,1}},
    {6,4,{6,5,4,3,2}}, {7,0,{6,5,4,3,2}}, {7,1,{6,5,4,3,2}},
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

    char chord[4] = {0}; pr53_decode_chord(cg, chord);
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
