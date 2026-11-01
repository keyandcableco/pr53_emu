// test_menus.c — host test: the menu page readout, the MENU and PAGE words,
// the PAGE arrows, the part pointers and the item number beside line 2.
//
// Replays captures/menus_2026-10-31.log, the menu_page_arrows campaign walked
// through the Sound menu from its last page (Chorus, P7) down. At each step's
// capture the frame must show the page and arrows the piano showed; after
// EXIT, none of them. Menus are written without a DISP_CTRL, and the firmware
// shows them after 60 ms of bus quiet, so the frame is decoded from the
// controller state at each capture, not at the last DISP_CTRL. Only LEFT's
// pointer shows on Sound-menu pages (as on p. 21 of the owner's manual), all
// eight on the play screen after EXIT.
//
// With a second log (restart_tap_v18_2026-10-31.log), also checks the item
// number on rhythm and voice screens: Soul 1, Pop Grand 1, Classic Gtr 1,
// Spanish Gtr 2. While a line is being rewritten the number can be blank, but
// never another digit.
//
// Build (host): see host.mk

#include <stdio.h>
#include <string.h>
#include "pr53_decode.h"

static const struct {
    const char *label, *page;
    bool menu, page_word, up, down;
    const char *pointers;   // DRUMS .. RIGHT 1
} EXPECT[] = {
    {"page_first",        "P7", true,  true,  false, true,  "00000100"},
    {"page_middle",       "P6", true,  true,  true,  true,  "00000100"},
    {"page_last",         "P1", true,  true,  true,  false, "00000100"},
    {"page_middle_again", "P2", true,  true,  true,  true,  "00000100"},
    {"page_exit",         "",   false, false, false, false, "11111111"},
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

static const char *skip_spaces(const char *s) { while (*s == ' ') s++; return s; }

// Item numbers on rhythm and voice screens, decoding after every write.
static int check_items(const char *path) {
    static const struct { const char *line1, *line2, *item; } ITEMS[] = {
        {"RHYTHM", "Soul", " 1"}, {"RIGHT1", "Pop Grand", " 1"},
        {"RIGHT1", "Classic Gtr", " 1"}, {"RIGHT1", "Spanish Gtr", " 2"},
    };
    enum { N = sizeof(ITEMS) / sizeof(ITEMS[0]) };
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 0; }
    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    char ln[512];
    int seen[N] = {0}, wrong = 0;
    while (fgets(ln, sizeof(ln), f)) {
        int isd = 0; unsigned b = 0;
        if (!parse_event(ln, &isd, &b)) continue;
        hd44780_feed(&hw, (uint8_t)b, isd != 0);
        pr53_decode_all(&hw, &frame);
        for (int i = 0; i < N; i++) {
            if (strcmp(skip_spaces(frame.line1), ITEMS[i].line1) ||
                strcmp(skip_spaces(frame.line2), ITEMS[i].line2)) continue;
            if (!strcmp(frame.item, ITEMS[i].item)) seen[i] = 1;
            else if (frame.item[0] && wrong++ < 5)
                printf("  %s / %s showed item '%s'\n", ITEMS[i].line1, ITEMS[i].line2, frame.item);
        }
    }
    fclose(f);
    int all = 1;
    for (int i = 0; i < N; i++) if (!seen[i]) { printf("  never saw %s / %s\n", ITEMS[i].line1, ITEMS[i].line2); all = 0; }
    int ok = all && !wrong;
    printf("CHECK item number beside line 2 (Soul 1, Pop Grand 1, Classic Gtr 1, Spanish Gtr 2): %s\n",
           ok ? "PASS" : "FAIL");
    return ok;
}

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "menus_2026-10-31.log";
    FILE *f = fopen(path, "r");
    if (!f) { printf("cannot open %s\n", path); return 1; }

    HD44780 hw; hd44780_init(&hw);
    DisplayState frame; memset(&frame, 0, sizeof(frame));
    char ln[512];
    int seen[NSTEPS] = {0}, fails = 0;
    static char msgs[16][192];   // failures of the current run, printed at the end
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
            char ptr[PR53_NUM_PARTS + 1];
            for (int p = 0; p < PR53_NUM_PARTS; p++) ptr[p] = frame.pointer[p] ? '1' : '0';
            ptr[PR53_NUM_PARTS] = 0;
            int ok = !strcmp(frame.page, EXPECT[i].page) && frame.menu_word == EXPECT[i].menu &&
                     frame.page_word == EXPECT[i].page_word && frame.page_up == EXPECT[i].up &&
                     frame.page_down == EXPECT[i].down && !strcmp(ptr, EXPECT[i].pointers) &&
                     !frame.item[0];
            if (!ok && fails < 16)
                snprintf(msgs[fails], sizeof(msgs[0]),
                         "  %-18s page='%s' menu=%d page=%d up=%d down=%d pointers=%s item='%s'  FAIL",
                         label, frame.page, frame.menu_word, frame.page_word, frame.page_up,
                         frame.page_down, ptr, frame.item);
            seen[i] = 1; fails += !ok;
        }
    }
    fclose(f);
    for (int i = 0; i < fails && i < 16; i++) printf("%s\n", msgs[i]);
    int all = 1;
    for (int i = 0; i < NSTEPS; i++) all &= seen[i];
    int ok = all && !fails;
    printf("CHECK menu page readout, MENU/PAGE, arrows and pointers (%d failed, all 5 steps seen: %s): %s\n",
           fails, all ? "yes" : "no", ok ? "PASS" : "FAIL");
    if (argc > 2) ok &= check_items(argv[2]);
    return ok ? 0 : 1;
}
