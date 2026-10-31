// test_numbers.c — host test: the eight part numbers, hundreds digits included.
//
// 1. Replays the volume sweeps in session_071830 ("bargraph min max pt 1-8":
//    each part taken down to 0 and back up, in steps of 4). Every committed
//    frame must read 0-127 or nothing, and each part must cross 100 in both
//    directions where the sweep did.
// 2. Replays the campaign log. Play-screen frames must show the values on the
//    photo of the original glass, 118 113 113 113 118 113 100 127. LEFT (P6)
//    is switched off for most of that session and shows "---"; the few frames
//    with it on read 113, as on the photo. While the piano
//    redraws the screen (after a menu or the RHYTHM screen) it writes the
//    custom characters over several refreshes, so a frame may show a value
//    with its leading digits not drawn yet (18 or 8 for 118), as the glass
//    does. Only the campaigns are checked (up to the last "# NOTE" line): the
//    log keeps recording free play afterwards, where volumes move. Those
//    stretches last 3-6 frames; any other value, or a stretch long
//    enough to be a steady screen (over 8 frames), fails. Complete frames must
//    also show the meters for those values: 5 bars at 118 and 127, 4 at 113
//    and 100 (a bar per ~23), or none where a meter isn't redrawn yet.
//
// Build (host): see host.mk

#include <stdio.h>
#include <string.h>
#include "pr53_decode.h"

static int parse_event(const char *ln, int *is_data, unsigned *byte) {
    if (!strstr(ln, " W ")) return 0;
    const char *cmd = strstr(ln, " CMD "), *dat = strstr(ln, " DAT "), *hx;
    if (cmd) { *is_data = 0; hx = cmd + 5; }
    else if (dat) { *is_data = 1; hx = dat + 5; }
    else return 0;
    unsigned v; if (sscanf(hx, "0x%x", &v) != 1) return 0;
    *byte = v & 0xFF;
    return 1;
}

// Calls fn on every frame the piano commits (DISP_CTRL with the display on),
// up to the last "# NOTE" line if notes_only is set.
static int replay(const char *path, int notes_only,
                  void (*fn)(const DisplayState *, void *), void *ctx) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return -1; }
    char ln[512];
    long last_note = -1, line = 0;
    while (notes_only && fgets(ln, sizeof(ln), f))
        if (line++, strstr(ln, "# NOTE ")) last_note = line;
    rewind(f);
    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    int n = 0;
    line = 0;
    while (fgets(ln, sizeof(ln), f) && (!notes_only || ++line <= last_note)) {
        int isd = 0; unsigned b = 0;
        if (!parse_event(ln, &isd, &b)) continue;
        if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on) {
            pr53_decode_all(&hw, &frame);
            fn(&frame, ctx);
            n++;
        }
    }
    fclose(f);
    return n;
}

typedef struct { unsigned char seen[PR53_NUM_PARTS][128]; int out_of_range; } Sweep;

static void on_sweep(const DisplayState *s, void *ctx) {
    Sweep *w = ctx;
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        int v = s->part_value[p];
        if (v > 127) w->out_of_range++;
        else if (v >= 0) w->seen[p][v] = 1;
    }
}

static const int GLASS[PR53_NUM_PARTS] = {118, 113, 113, 113, 118, 113, 100, 127};
#define LEFT 5
static const int BARS[PR53_NUM_PARTS] = {5, 4, 4, 4, 5, 4, 4, 5};
typedef struct { int play, match, wrong, run, longest, bars_off, bars_all; } Campaign;

static void on_campaign(const DisplayState *s, void *ctx) {
    Campaign *c = ctx;
    int play = 0;
    for (int p = 0; p < PR53_NUM_PARTS; p++) play |= s->part_value[p] >= 0;
    if (!play) { c->run = 0; return; }   // menus and the RHYTHM screen have no numbers
    c->play++;
    int same = 1, wrong = 0;
    for (int p = 0; p < PR53_NUM_PARTS; p++) {
        int v = s->part_value[p], g = GLASS[p];
        same &= v == g || (p == LEFT && v == -1);
        wrong |= !(v == g || v == -1 || v == g % 100 || v == g % 10);
    }
    c->match += same;
    if (same) {
        int all = 1, off = 0;
        for (int p = 0; p < PR53_NUM_PARTS; p++) {
            all &= s->part_level[p] == BARS[p];
            off |= s->part_level[p] != BARS[p] && s->part_level[p] != 0;
        }
        c->bars_all += all;
        c->bars_off += off;
    }
    c->run = same ? 0 : c->run + 1;
    if (c->run > c->longest) c->longest = c->run;
    if (wrong && c->wrong++ < 5) {
        printf("  wrong:");
        for (int p = 0; p < PR53_NUM_PARTS; p++) printf(" %d", s->part_value[p]);
        printf("\n");
    }
}

int main(int argc, char **argv) {
    if (argc < 3) { printf("usage: testnumbers <session_071830.log> <campaign.log>\n"); return 2; }
    int fails = 0;

    static Sweep w;
    if (replay(argv[1], 0, on_sweep, &w) < 0) return 1;
    // values each sweep passed through, either side of 100 (part, value).
    // P7's hundreds digit (C2) isn't written until late in that capture, so
    // its 114 and 118 read 14 and 18; with tens and ones swapped they'd read
    // 41 and 81, which is what those two entries catch.
    static const int MUST[][2] = {
        {0, 101}, {0, 97}, {0, 0}, {0, 117}, {1, 101}, {1, 92}, {3, 101}, {3, 90},
        {4, 101}, {4, 91}, {5, 127}, {5, 102}, {5, 98}, {5, 0},
        {6, 14}, {6, 18},
        {7, 127}, {7, 103}, {7, 99}, {7, 0}, {7, 100},
    };
    int missing = 0;
    for (size_t i = 0; i < sizeof(MUST) / sizeof(MUST[0]); i++)
        if (!w.seen[MUST[i][0]][MUST[i][1]]) {
            printf("  P%d never read %d\n", MUST[i][0] + 1, MUST[i][1]);
            missing++;
        }
    int ok = !missing && !w.out_of_range;
    printf("CHECK sweeps cross 100 both ways, nothing above 127 (%d out of range): %s\n",
           w.out_of_range, ok ? "PASS" : "FAIL");
    fails += !ok;

    Campaign c = {0, 0, 0, 0, 0, 0, 0};
    if (replay(argv[2], 1, on_campaign, &c) < 0) return 1;
    ok = c.match > 0 && !c.wrong && c.longest <= 8;
    printf("CHECK campaign reads 118 113 113 113 118 113/--- 100 127 (%d of %d play frames, the rest "
           "mid-redraw, longest %d; %d wrong): %s\n", c.match, c.play, c.longest, c.wrong, ok ? "PASS" : "FAIL");
    fails += !ok;
    ok = c.bars_all > c.match / 2 && !c.bars_off;
    printf("CHECK meters in those frames read 5 4 4 4 5 4 4 5 (%d of %d, %d wrong): %s\n",
           c.bars_all, c.match, c.bars_off, ok ? "PASS" : "FAIL");
    fails += !ok;
    return fails ? 1 : 0;
}
