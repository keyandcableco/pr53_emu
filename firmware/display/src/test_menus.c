// test_menus.c — host test: the menu page readout, the MENU and PAGE words
// and the PAGE arrows.
//
// Replays captures/menus_2026-10-31.log, the menu_page_arrows campaign walked
// through the Sound menu from its last page (Chorus, P7) down. At each step's
// capture the frame must show the page and arrows the piano showed; after
// EXIT, none of them. Menus are written without a DISP_CTRL, and the firmware
// shows them after 60 ms of bus quiet, so the frame is decoded from the
// controller state at each capture, not at the last DISP_CTRL.
//
// Build (host): see host.mk

#include <stdio.h>
#include <string.h>
#include "pr53_decode.h"

static const struct {
    const char *label, *page;
    bool menu, page_word, up, down;
} EXPECT[] = {
    {"page_first",        "P7", true,  true,  false, true },
    {"page_middle",       "P6", true,  true,  true,  true },
    {"page_last",         "P1", true,  true,  true,  false},
    {"page_middle_again", "P2", true,  true,  true,  true },
    {"page_exit",         "",   false, false, false, false},
};
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

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "menus_2026-10-31.log";
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 1; }

    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    char ln[512];
    int seen[NSTEPS] = {0}, fails = 0;
    static char msgs[16][128];   // failures of the current run, printed at the end
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0;
        if (parse_event(ln, &isd, &b)) {
            if (hd44780_feed(&hw, (uint8_t)b, isd != 0) && hw.display_on)
                pr53_decode_all(&hw, &frame);
            continue;
        }
        const char *note = strstr(ln, "# NOTE ");
        if (!note) continue;
        // a new run of the campaign starts the checks over; the last run counts
        if (strstr(note, "campaign menu_page_arrows start")) {
            memset(seen, 0, sizeof(seen)); fails = 0;
            continue;
        }
        int step; char label[64];
        if (sscanf(note + 7, "capture step %d: %63s", &step, label) != 2) continue;
        pr53_decode_all(&hw, &frame);
        for (int i = 0; i < NSTEPS; i++) {
            if (strcmp(label, EXPECT[i].label)) continue;
            int ok = !strcmp(frame.page, EXPECT[i].page) && frame.menu_word == EXPECT[i].menu &&
                     frame.page_word == EXPECT[i].page_word && frame.page_up == EXPECT[i].up &&
                     frame.page_down == EXPECT[i].down;
            if (!ok && fails < 16)
                snprintf(msgs[fails], sizeof(msgs[0]), "  %-18s page='%s' menu=%d page=%d up=%d down=%d  FAIL",
                         label, frame.page, frame.menu_word, frame.page_word, frame.page_up, frame.page_down);
            seen[i] = 1; fails += !ok;
        }
    }
    fclose(f);
    for (int i = 0; i < fails && i < 16; i++) printf("%s\n", msgs[i]);
    int all = 1;
    for (int i = 0; i < NSTEPS; i++) all &= seen[i];
    int ok = all && !fails;
    printf("CHECK menu page readout, MENU/PAGE and arrows (%d failed, all 5 steps seen: %s): %s\n",
           fails, all ? "yes" : "no", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
