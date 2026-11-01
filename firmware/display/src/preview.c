// preview.c — host tool: draw what the display firmware would show, as an image.
//
// Replays a capture through the decoder and the start-up logo's rules (the
// display powered up at the log's first bus write), stops at the end of the
// log, at the last "# NOTE" line containing the text given as the third
// argument, or at a tap time given as "@seconds", then runs the real render
// code (the logo, or render_static() + render_frame()) into a framebuffer and
// saves it as a PPM.
//
//   preview <log> <out.ppm> ["note text" | @seconds]
//
// Build (host): see host.mk (`make -f host.mk preview`).

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pr53_decode.h"
#include "pr53_render.h"
#include "pr53_splash.h"
#include "pr53_ili9486_par.h"

// Same quiet-bus rule as main.c: writes not followed by a DISP_CTRL are
// published once the bus has been quiet this long (tap timestamps, in us).
#define SETTLE_US 60000

static int parse_event(const char *ln, int *is_data, unsigned *byte, unsigned long *t_us) {
    if (!strstr(ln, " W ")) return 0;
    const char *cmd = strstr(ln, " CMD "), *dat = strstr(ln, " DAT "), *hx;
    if (cmd) { *is_data = 0; hx = cmd + 5; }
    else if (dat) { *is_data = 1; hx = dat + 5; }
    else return 0;
    unsigned v; if (sscanf(hx, "0x%x", &v) != 1) return 0;
    *byte = v & 0xFF;
    const char *t = strstr(ln, "t=");
    if (t && t != ln && t[-1] == '_') t = strstr(t + 2, " t=");   // skip t_wall=
    *t_us = t ? strtoul(t + (t[0] == ' ' ? 3 : 2), NULL, 10) : 0;
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        printf("usage: preview <log> <out.ppm> [\"note text\" | @seconds]\n");
        return 2;
    }
    const char *stop_at = (argc > 3 && argv[3][0]) ? argv[3] : NULL;
    unsigned long stop_us = 0;   // "@seconds": stop at this tap time instead
    if (stop_at && stop_at[0] == '@') {
        stop_us = (unsigned long)(atof(stop_at + 1) * 1e6);
        stop_at = NULL;
    }
    FILE *f = fopen(argv[1], "r");
    if (!f) { printf("cannot open %s\n", argv[1]); return 1; }

    HD44780 hw; hd44780_init(&hw);
    hw.display_on = true;
    DisplayState frame, at_note;
    memset(&frame, 0, sizeof(frame)); at_note = frame;
    int have = 0, found = 0, dirty = 0, started = 0;
    Splash sp = {0};
    bool logo = false, logo_at_note = false;   // the logo is up (at the note)
    unsigned long last_t = 0;
    char ln[512];
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0; unsigned long t = 0;
        if (parse_event(ln, &isd, &b, &t)) {
            if (stop_us && t >= stop_us) break;
            if (!started) { logo = splash_start(&sp, t / 1000) == SPLASH_SHOW; started = 1; }
            if (dirty && t - last_t > SETTLE_US && hw.display_on) {
                pr53_decode_all(&hw, &frame);   // quiet bus: publish pending
                have = 1;
                splash_step(&sp, &frame, true, last_t / 1000 + SETTLE_US / 1000);
            }
            splash_step(&sp, &frame, false, t / 1000);   // the time limit
            last_t = t;
            dirty = 1;
            if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on) {
                pr53_decode_all(&hw, &frame);
                have = 1; dirty = 0;
                splash_step(&sp, &frame, true, t / 1000);
            }
            logo = sp.on;
            continue;
        }
        if (!strstr(ln, "# NOTE")) continue;
        // A note comes long after the last write, so anything pending is shown.
        if (dirty && hw.display_on) {
            pr53_decode_all(&hw, &frame); have = 1; dirty = 0;
            splash_step(&sp, &frame, true, last_t / 1000 + SETTLE_US / 1000);
            logo = sp.on;
        }
        // Keep the LAST matching note: in a campaign log that's the last run.
        if (stop_at && strstr(ln, stop_at)) { at_note = frame; logo_at_note = logo; found = 1; }
    }
    fclose(f);
    if (!have && !logo) { printf("no committed frame in %s\n", argv[1]); return 1; }
    if (stop_at && !found) { printf("note \"%s\" not found\n", stop_at); return 1; }
    if (stop_at) { frame = at_note; logo = logo_at_note; }

    if (logo) {
        splash_draw();
    } else {
        render_static();
        render_frame(&frame);
    }
    if (ili9488_host_save_ppm(argv[2])) { printf("cannot write %s\n", argv[2]); return 1; }
    if (logo) printf("start-up logo (piano: line1='%s' line2='%s') -> %s\n",
                     frame.line1, frame.line2, argv[2]);
    else printf("tempo=%d chord='%s' line1='%s' line2='%s' -> %s\n",
                frame.tempo, frame.chord, frame.line1, frame.line2, argv[2]);
    return 0;
}
