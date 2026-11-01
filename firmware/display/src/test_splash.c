// test_splash.c — host test: when the start-up logo shows and hands back.
//
//   testsplash <restart_tap_v18 log> <startup log> [more logs...]
//
// Replays captures as the display sees them (frames published on DISP_CTRL
// or after 60 ms of bus quiet, as in main.c) through splash_step():
// - display and piano powered together: the logo holds through the blank
//   display and "Technics / SX-PR53" and hands back on the play screen, all
//   fields loaded (restart_tap_v18), or on "ALL INITIAL" (startup);
// - display left on while the piano restarts: the logo comes back for the
//   "Technics" screen only, and hands back on the next screen;
// - every other log: no logo except in place of a "Technics" screen, and a
//   display restarted mid-session hands back by the piano's first frame with
//   text (or after 30 s, when the piano sends nothing but blank frames);
// - the 30 s limit, and the generated logo and QR data.
//
// Build (host): see host.mk

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pr53_decode.h"
#include "pr53_splash.h"
#include "pr53_logo.h"

#define SETTLE_US 60000   // main.c's quiet-bus rule

static int parse_event(const char *ln, int *is_data, unsigned *byte, unsigned long *t_us) {
    if (!strstr(ln, " W ")) return 0;
    const char *cmd = strstr(ln, " CMD "), *dat = strstr(ln, " DAT "), *hx;
    if (cmd) { *is_data = 0; hx = cmd + 5; }
    else if (dat) { *is_data = 1; hx = dat + 5; }
    else return 0;
    unsigned v; if (sscanf(hx, "0x%x", &v) != 1) return 0;
    *byte = v & 0xFF;
    const char *t = strstr(ln, "t=");                   // at the start, or after t_wall=
    if (t && t != ln && t[-1] == '_') t = strstr(t + 2, " t=");
    if (!t || sscanf(t + (t[0] == ' ' ? 3 : 2), "%lu", t_us) != 1) return 0;
    return 1;
}

static const char *trim(const char *s) { while (*s == ' ') s++; return s; }

// The piano's start-up text, or part of it.
static int is_boot_text(const DisplayState *s) {
    return !strcmp(trim(s->line1), "Technics") || !strcmp(trim(s->line2), "SX-PR53");
}

// Line 1 has moved on ("SX-PR53" can linger on line 2 with older taps).
static int past_boot(const DisplayState *s) { return strcmp(trim(s->line1), "Technics") != 0; }

#define MAXEV 16
typedef struct {
    int writes;               // bus writes in the log
    int shows, ends;          // SHOW (after power-up) and END steps
    int capped;               // ENDs from the time limit, not a frame
    DisplayState show[MAXEV], end[MAXEV];
    unsigned long end_ms[MAXEV];
    unsigned long text_ms;    // first frame with text other than "Technics" (0: none)
} Trace;

static void step(Trace *tr, Splash *sp, const DisplayState *s, int fresh, unsigned long ms) {
    if (fresh && !tr->text_ms && s->line1[0] && strcmp(trim(s->line1), "Technics"))
        tr->text_ms = ms;
    SplashStep st = splash_step(sp, s, fresh, (uint32_t)ms);
    if (st == SPLASH_SHOW && tr->shows < MAXEV) tr->show[tr->shows++] = *s;
    if (st == SPLASH_END && tr->ends < MAXEV) {
        tr->end_ms[tr->ends] = ms;
        tr->end[tr->ends++] = *s;
        tr->capped += !fresh;
    }
}

// power_up: the display starts with the log's first bus write; otherwise it
// was already on, showing the glass.
static int replay(const char *path, int power_up, Trace *tr) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 0; }
    memset(tr, 0, sizeof(*tr));
    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    Splash sp = {0};
    int started = 0, dirty = 0;
    unsigned long last_t = 0;
    char ln[512];
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0; unsigned long t = 0;
        if (!parse_event(ln, &isd, &b, &t)) continue;
        tr->writes++;
        if (!started) { if (power_up) splash_start(&sp, t / 1000); started = 1; }
        if (dirty && t - last_t > SETTLE_US && hw.display_on) {
            pr53_decode_all(&hw, &frame);
            step(tr, &sp, &frame, 1, (last_t + SETTLE_US) / 1000);
        }
        step(tr, &sp, &frame, 0, t / 1000);
        last_t = t;
        dirty = 1;
        if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on) {
            pr53_decode_all(&hw, &frame);
            dirty = 0;
            step(tr, &sp, &frame, 1, t / 1000);
        }
    }
    fclose(f);
    return 1;
}

static int all_parts(const DisplayState *s) {
    for (int p = 0; p < PR53_NUM_PARTS; p++) if (s->part_value[p] < 0) return 0;
    return 1;
}

static int check(const char *what, int ok) {
    printf("CHECK %s: %s\n", what, ok ? "PASS" : "FAIL");
    return ok;
}

// A QR finder pattern (7x7 rings) with its top-left module at (r0, c0).
static int finder_at(int r0, int c0) {
    for (int r = 0; r < 7; r++)
        for (int c = 0; c < 7; c++) {
            int ring = (r == 0 || r == 6 || c == 0 || c == 6);
            int core = (r >= 2 && r <= 4 && c >= 2 && c <= 4);
            int dark = pr53_qr_rows[r0 + r] >> (c0 + c) & 1;
            if (dark != (ring || core)) return 0;
        }
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        printf("usage: testsplash <restart_tap_v18 log> <startup log> [more logs...]\n");
        return 2;
    }
    int ok = 1;
    Trace tr;

    // Generated data: runs cover the screen exactly; the QR code reads the
    // right way round (finders top-left, top-right, bottom-left only).
    uint32_t px = 0, ink = 0;
    for (uint32_t i = 0; i < pr53_logo_rle_len; i++) {
        px += (pr53_logo_rle[i] & 63u) + 1;
        if (pr53_logo_rle[i] >> 6 == 3) ink += (pr53_logo_rle[i] & 63u) + 1;
    }
    int n = pr53_qr_n;
    printf("  logo: %u bytes of runs, %u pixels, %u full ink; QR %dx%d\n",
           (unsigned)pr53_logo_rle_len, (unsigned)px, (unsigned)ink, n, n);
    ok &= check("logo runs fill the screen exactly, QR the right way round",
                px == PR53_LOGO_WIDTH * PR53_LOGO_HEIGHT && ink > 1000 && n >= 21 && n <= 32 &&
                finder_at(0, 0) && finder_at(0, n - 7) && finder_at(n - 7, 0) &&
                !finder_at(n - 7, n - 7));

    // Powered together: logo through the start-up, glass on the play screen.
    if (!replay(argv[1], 1, &tr)) return 1;
    printf("  power-up: %d ends, first on '%s' / '%s', tempo %d\n", tr.ends,
           tr.ends ? tr.end[0].line1 : "", tr.ends ? tr.end[0].line2 : "",
           tr.ends ? tr.end[0].tempo : -1);
    ok &= check("power-up: logo until the play screen, which arrives complete",
                tr.ends == 1 && !tr.shows && !tr.capped &&
                !strcmp(tr.end[0].line1, "ConcertGrand") && tr.end[0].tempo == 120 &&
                all_parts(&tr.end[0]));

    if (!replay(argv[2], 1, &tr)) return 1;
    ok &= check("power-up after a factory reset: logo until ALL INITIAL",
                tr.ends == 1 && !tr.shows && !tr.capped &&
                !strcmp(tr.end[0].line1, "ALL INITIAL"));

    // Display left on: the logo only stands in for the "Technics" screen.
    if (!replay(argv[1], 0, &tr)) return 1;
    ok &= check("piano restart, display on: logo for the Technics screen only",
                tr.shows == 1 && tr.ends == 1 && !tr.capped &&
                is_boot_text(&tr.show[0]) && !strcmp(tr.end[0].line1, "ConcertGrand"));

    // Every log, display left on and display restarted at the log's start.
    int bad = 0, shows = 0, empty = 0;
    for (int k = 1; k < argc; k++) {
        if (!replay(argv[k], 0, &tr)) return 1;
        if (!tr.writes) { empty++; continue; }
        int good = tr.ends == tr.shows && !tr.capped;
        for (int i = 0; i < tr.shows; i++)
            good &= is_boot_text(&tr.show[i]) && past_boot(&tr.end[i]);
        shows += tr.shows;
        Trace up;
        if (!replay(argv[k], 1, &up)) return 1;
        good &= up.ends >= 1 && past_boot(&up.end[0]) &&
                (!up.text_ms || up.end_ms[0] <= up.text_ms);
        if (!good || tr.shows || up.capped)
            printf("  %s: %d logos in place of Technics; from power-up, hands back %s on '%s'%s\n",
                   argv[k], tr.shows, up.capped ? "after 30 s" : "on a frame",
                   up.ends ? up.end[0].line1 : "(never)", good ? "" : "  FAIL");
        bad += !good;
    }
    printf("  %d logs (%d without bus writes), %d Technics screens replaced\n",
           argc - 1, empty, shows);
    ok &= check("all logs: logo only for Technics, never past the first frame with text",
                !bad);

    // The time limit, with nothing from the piano or only its start-up text.
    Splash sp;
    DisplayState s; memset(&s, 0, sizeof(s));
    for (int p = 0; p < PR53_NUM_PARTS; p++) s.part_value[p] = -1;
    s.tempo = -1;
    int lim = splash_start(&sp, 1000) == SPLASH_SHOW &&
              splash_step(&sp, &s, true, 1000) == SPLASH_HOLD &&
              splash_step(&sp, &s, false, 1000 + SPLASH_MAX_MS - 1) == SPLASH_HOLD &&
              splash_step(&sp, &s, false, 1000 + SPLASH_MAX_MS) == SPLASH_END;
    strcpy(s.line1, "  Technics");
    strcpy(s.line2, "  SX-PR53");
    lim &= splash_start(&sp, 0) == SPLASH_SHOW &&
           splash_step(&sp, &s, true, 5000) == SPLASH_HOLD &&
           splash_step(&sp, &s, true, SPLASH_MAX_MS) == SPLASH_END &&
           splash_step(&sp, &s, true, SPLASH_MAX_MS + 100) == SPLASH_IDLE;
    ok &= check("30 s limit, and no logo again for the same Technics screen", lim);

    return ok ? 0 : 1;
}
