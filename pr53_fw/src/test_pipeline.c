// test_pipeline.c — host test: feed real bus events through the C HD44780
// emulation + decoder and print the decoded state on each 0x0C commit.
// Compares the final frame against the known ground-truth values.
//
// Build (host): see host.mk

#include <stdio.h>
#include <string.h>
#include "pr53_decode.h"

// Parse lines like:
//   t_wall=... t=... W CMD 0x0C [DISP_CTRL ...]
//   t_wall=... t=... W DAT 0x50 'P'
// We only need: W, CMD|DAT, the hex byte.
static int parse_line(const char *ln, int *is_write, int *is_data, unsigned *byte) {
    const char *w = strstr(ln, " W ");
    if (!w) return 0;
    *is_write = 1;
    const char *cmd = strstr(ln, " CMD ");
    const char *dat = strstr(ln, " DAT ");
    const char *hx;
    if (cmd) { *is_data = 0; hx = cmd + 5; }   // points at "0x.."
    else if (dat) { *is_data = 1; hx = dat + 5; }
    else return 0;
    unsigned v; if (sscanf(hx, "0x%x", &v) != 1) return 0;
    *byte = v & 0xFF;
    return 1;
}

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "session_092906.log";
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 1; }

    HD44780 hw; hd44780_init(&hw);
    hw.display_on = true;   // logs start mid-operation

    DisplayState st; int commits = 0;
    char ln[512];
    DisplayState lastframe; memset(&lastframe, 0, sizeof(lastframe));

    while (fgets(ln, sizeof(ln), f)) {
        int isw=0, isd=0; unsigned b=0;
        if (!parse_line(ln, &isw, &isd, &b)) continue;
        bool commit = hd44780_feed(&hw, (uint8_t)b, isd != 0);
        if (commit && hw.display_on) {
            pr53_decode_all(&hw, &st);
            lastframe = st;
            commits++;
        }
    }
    fclose(f);

    printf("commits: %d\n", commits);
    printf("FINAL decoded frame:\n");
    printf("  tempo   = %d\n", lastframe.tempo);
    printf("  line1   = '%s'\n", lastframe.line1);
    printf("  line2   = '%s'\n", lastframe.line2);
    printf("  chord   = '%s'\n", lastframe.chord);
    for (int p = 0; p < PR53_NUM_PARTS; p++)
        printf("  P%d: level=%d value=%d\n", p+1,
               lastframe.part_level[p], lastframe.part_value[p]);

    // Ground-truth check (part 8 = 127 fully solved).
    printf("\nCHECK P8 value == 127: %s\n",
           lastframe.part_value[7] == 127 ? "PASS" : "FAIL");
    return 0;
}
