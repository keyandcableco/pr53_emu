// preview.c — host tool: draw what the display firmware would show, as an image.
//
// Replays a capture through the decoder, stops at the end of the log or at
// the last "# NOTE" line containing the text given as the third argument,
// then runs the real render_static() + render_frame() into a framebuffer
// and saves it as a PPM.
//
//   preview <log> <out.ppm> ["note text"]
//
// Build (host): see host.mk (`make -f host.mk preview`).

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pr53_decode.h"
#include "pr53_render.h"
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
        printf("usage: preview <log> <out.ppm> [\"note text\"]\n");
        return 2;
    }
    const char *stop_at = (argc > 3 && argv[3][0]) ? argv[3] : NULL;
    FILE *f = fopen(argv[1], "r");
    if (!f) { printf("cannot open %s\n", argv[1]); return 1; }

    HD44780 hw; hd44780_init(&hw);
    hw.display_on = true;
    DisplayState frame, at_note;
    memset(&frame, 0, sizeof(frame)); at_note = frame;
    int have = 0, found = 0, dirty = 0;
    unsigned long last_t = 0;
    char ln[512];
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0; unsigned long t = 0;
        if (parse_event(ln, &isd, &b, &t)) {
            if (dirty && t - last_t > SETTLE_US && hw.display_on) {
                pr53_decode_all(&hw, &frame);   // quiet bus: publish pending
                have = 1;
            }
            last_t = t;
            dirty = 1;
            if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on) {
                pr53_decode_all(&hw, &frame);
                have = 1; dirty = 0;
            }
            continue;
        }
        if (!strstr(ln, "# NOTE")) continue;
        // A note comes long after the last write, so anything pending is shown.
        if (dirty && hw.display_on) { pr53_decode_all(&hw, &frame); have = 1; dirty = 0; }
        // Keep the LAST matching note: in a campaign log that's the last run.
        if (stop_at && strstr(ln, stop_at)) { at_note = frame; found = 1; }
    }
    fclose(f);
    if (!have) { printf("no committed frame in %s\n", argv[1]); return 1; }
    if (stop_at && !found) { printf("note \"%s\" not found\n", stop_at); return 1; }
    if (stop_at) frame = at_note;

    render_static();
    render_frame(&frame);
    if (ili9488_host_save_ppm(argv[2])) { printf("cannot write %s\n", argv[2]); return 1; }
    printf("tempo=%d chord='%s' line1='%s' line2='%s' -> %s\n",
           frame.tempo, frame.chord, frame.line1, frame.line2, argv[2]);
    return 0;
}
