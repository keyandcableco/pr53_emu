// test_chords.c — host test: replay the chord-root campaign and check the
// decoded chord and tempo at every saved step. With a second log (the
// transpose sweep in session_064015), also check the transpose key.
//
// Reads a campaign raw log (pr53_campaign.py --raw-log). For each step saved
// in the last chord_roots_all12 run, the frame committed when that step was
// captured must show the chord the piano displayed, and the tempo must still
// read 120. (The capture is the right moment: the piano clears the chord a
// couple of seconds later, once the keys are released.)
//
// Build (host): see host.mk

#include <stdio.h>
#include <string.h>
#include "pr53_decode.h"

// What the piano showed for each step's label. It spells black keys as
// Db, Eb, F#, Ab, Bb. The "A" step caught Bb on screen (same as A#).
static const struct { const char *label, *chord; } EXPECT[] = {
    {"chord_root_C", "C"},  {"chord_root_C#", "Db"}, {"chord_root_D", "D"},
    {"chord_root_D#", "Eb"}, {"chord_root_E", "E"},  {"chord_root_F", "F"},
    {"chord_root_F#", "F#"}, {"chord_root_G", "G"},  {"chord_root_G#", "Ab"},
    {"chord_root_A", "Bb"},  {"chord_root_A#", "Bb"}, {"chord_root_B", "B"},
};

// A complete run saves all 12 roots; fewer means the run was cut short.
#define NSTEPS ((int)(sizeof(EXPECT) / sizeof(EXPECT[0])))

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

// Transpose sweep: every key the screen holds for 100 ms or more must be one
// of the 12 the piano shows, spelled its way, and all 12 must appear. (In
// between, for a few ms, the letter and accidental can disagree.)
static const char *const KEYS[] = {"G", "Ab", "A", "Bb", "B", "C", "Db", "D", "Eb", "E", "F", "F#"};
#define NKEYS ((int)(sizeof(KEYS) / sizeof(KEYS[0])))

static int key_index(const char *k) {
    for (int i = 0; i < NKEYS; i++) if (!strcmp(k, KEYS[i])) return i;
    return -1;
}

static int check_transpose(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 0; }
    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    char held[4] = "", ln[512];
    unsigned long since = 0;
    int seen[NKEYS] = {0}, wrong = 0;
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0;
        const char *tp = strstr(ln, " t=");
        unsigned long us = 0;
        if (!tp || sscanf(tp + 3, "%lu", &us) != 1 || !parse_event(ln, &isd, &b)) continue;
        if (!hd44780_feed(&hw, (uint8_t)b, isd != 0) || !hw.display_on) continue;
        pr53_decode_all(&hw, &frame);
        if (!strcmp(frame.transpose, held)) continue;
        if (held[0] && us - since >= 100000) {
            int i = key_index(held);
            if (i < 0) { printf("  held \"%s\" for %lu ms\n", held, (us - since) / 1000); wrong++; }
            else seen[i] = 1;
        }
        memcpy(held, frame.transpose, sizeof(held));
        since = us;
    }
    fclose(f);
    int missing = 0;
    for (int i = 0; i < NKEYS; i++) if (!seen[i]) { printf("  never held %s\n", KEYS[i]); missing++; }
    int ok = !wrong && !missing;
    printf("CHECK transpose keys G to F#, spelled Db Eb F# Ab Bb (%d wrong): %s\n",
           wrong, ok ? "PASS" : "FAIL");
    return ok;
}

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "campaign_2026-10-31.log";
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 1; }

    HD44780 hw; hd44780_init(&hw);
    hw.display_on = true;
    DisplayState frame, captured;
    memset(&frame, 0, sizeof(frame)); captured = frame;
    // Results of the current chord run; a new run of the campaign starts over.
    static char lines[32][96];
    int in_run = 0, checks = 0, fails = 0;
    char ln[512];

    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0;
        if (parse_event(ln, &isd, &b)) {
            if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on)
                pr53_decode_all(&hw, &frame);
            continue;
        }
        const char *note = strstr(ln, "# NOTE ");
        if (!note) continue;
        note += 7;
        if (!strncmp(note, "campaign ", 9)) {
            in_run = !strncmp(note + 9, "chord_roots_all12 ", 18);
            if (in_run) checks = fails = 0;
            continue;
        }
        if (!strncmp(note, "capture step ", 13)) { captured = frame; continue; }
        int step; char label[64];
        if (!in_run || sscanf(note, "saved step %d: %63s", &step, label) != 2) continue;
        for (size_t i = 0; i < sizeof(EXPECT) / sizeof(EXPECT[0]); i++) {
            if (strcmp(label, EXPECT[i].label) || checks >= 32) continue;
            int ok = !strcmp(captured.chord, EXPECT[i].chord) && captured.tempo == 120;
            snprintf(lines[checks], sizeof(lines[0]), "  %-14s chord='%s' tempo=%d  %s",
                     label, captured.chord, captured.tempo, ok ? "ok" : "FAIL");
            checks++; fails += !ok;
        }
    }
    fclose(f);

    for (int i = 0; i < checks; i++) printf("%s\n", lines[i]);
    printf("\nCHECK chord roots and tempo (%d steps): %s\n", checks,
           (checks == NSTEPS && !fails) ? "PASS" : "FAIL");
    int ok = checks == NSTEPS && !fails;
    if (argc > 2) ok &= check_transpose(argv[2]);
    return ok ? 0 : 1;
}
