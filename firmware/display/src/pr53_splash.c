// pr53_splash.c — the start-up screen: when it shows (splash_step) and what
// it draws (splash_draw). See pr53_splash.h.

#include "pr53_splash.h"
#include "pr53_logo.h"
#include "pr53_font.h"
#include "pr53_ili9486_par.h"
#include <string.h>

_Static_assert(PR53_LOGO_WIDTH == ILI_W && PR53_LOGO_HEIGHT == ILI_H,
               "the logo image must be the size of the screen");

// The text column right of the logo (`make -f host.mk logo` puts the logo at
// x 12-271), centred on this x.
#define INFO_CX   378
#define QR_MODULE 4      // px per QR module: 25 modules = 100 px, about 15 mm

// ========================= WHEN =========================
static bool line_is(const char *line, const char *want) {
    while (*line == ' ') line++;          // the piano centres it with spaces
    return strcmp(line, want) == 0;
}

// The piano's start-up screen, "Technics" over "SX-PR53" (one line may still
// be blank between its writes). Meters and tempo load while it's up.
static bool boot_text(const DisplayState *s) {
    bool l1 = line_is(s->line1, "Technics"), l2 = line_is(s->line2, "SX-PR53");
    return (l1 || !s->line1[0]) && (l2 || !s->line2[0]) && (l1 || l2);
}

// Nothing lit at all: what the piano shows for ~2.6 s after it sets up its
// LCD, and the state before the first frame.
static bool blank(const DisplayState *s) {
    if (s->line1[0] || s->line2[0] || s->tempo >= 0 || s->chord[0] ||
        s->transpose[0] || s->page[0] || s->item[0] || s->menu_word ||
        s->page_word || s->page_up || s->page_down || s->split_left || s->split_right)
        return false;
    for (int p = 0; p < PR53_NUM_PARTS; p++)
        if (s->part_value[p] >= 0 || s->part_level[p] || s->pointer[p]) return false;
    return true;
}

SplashStep splash_start(Splash *sp, uint32_t now_ms) {
    sp->on = THEME_SPLASH;
    sp->boot_text = false;
    sp->starts = 0;
    sp->since_ms = now_ms;
    return sp->on ? SPLASH_SHOW : SPLASH_IDLE;
}

SplashStep splash_step(Splash *sp, const DisplayState *s, bool fresh,
                       uint32_t now_ms) {
    bool was_boot_text = sp->boot_text;
    // The piano started up: its LCD set-up sent a CLEAR. That frame still
    // shows the old tempo and meters (CLEAR wipes only the text); the piano
    // blanks them a few ms later, before its next frame.
    bool restarted = fresh && s->piano_starts != sp->starts;
    if (fresh) {
        sp->boot_text = boot_text(s);
        sp->starts = s->piano_starts;
    }
    if (sp->on) {
        if (restarted) sp->since_ms = now_ms;   // started again under the logo
        // Hand back on the first frame that isn't a start-up screen.
        if ((fresh && !restarted && !sp->boot_text && !blank(s)) ||
            now_ms - sp->since_ms >= SPLASH_MAX_MS) {
            sp->on = false;
            return SPLASH_END;
        }
        return SPLASH_HOLD;
    }
    // The piano restarted but the display didn't: the logo comes back from
    // its LCD set-up, or from its "Technics" screen if that CLEAR was lost.
    // Only on their arrival, so a long "Technics" screen isn't redrawn.
    if (THEME_SPLASH && fresh && (restarted || (sp->boot_text && !was_boot_text))) {
        sp->on = true;
        sp->since_ms = now_ms;
        return SPLASH_SHOW;
    }
    return SPLASH_IDLE;
}

// ========================= WHAT =========================
// Dot-matrix text like the glass's text lines, centred on cx.
static void dots_centered(int cx, int y, const char *s, int scale, uint16_t color) {
    font_text_dots(cx - (int)strlen(s) * 6 * scale / 2, y, s, scale, color);
}

#if THEME_SPLASH_QR
static void draw_qr(int x, int y) {
    for (int r = 0; r < pr53_qr_n; r++)
        for (int c = 0; c < pr53_qr_n; c++)
            if (pr53_qr_rows[r] >> c & 1)
                ili9488_fill_rect(x + c * QR_MODULE, y + r * QR_MODULE,
                                  QR_MODULE, QR_MODULE, COL_SEG);
}
#endif

void splash_draw(void) {
    // The logo fills the screen, field included, in one window.
    uint16_t shade[4];
    for (int k = 0; k < 4; k++) shade[k] = THEME_COL_LOGO(k);
    ili9488_set_window(0, 0, ILI_W - 1, ILI_H - 1);
    for (uint32_t i = 0; i < pr53_logo_rle_len; i++) {
        uint8_t run = pr53_logo_rle[i];
        ili9488_push(shade[run >> 6], (run & 63u) + 1);
    }

    // Beside it: the piano's own start-up text, what this display is, and
    // where it's from.
    int y = THEME_SPLASH_QR ? 40 : 96;
    dots_centered(INFO_CX, y, "Technics", 3, COL_SEG);                 y += 30;
    dots_centered(INFO_CX, y, "SX-PR53", 3, COL_SEG);                  y += 34;
    for (int x = INFO_CX - 88; x < INFO_CX + 88; x += 5)          // dotted rule
        ili9488_fill_rect(x, y, 2, 2, COL_RULE);
    y += 14;
    font_text_centered(INFO_CX, y, "LCD replacement", 2, COL_PRINT);   y += 34;
#if THEME_SPLASH_QR
    int qr_w = pr53_qr_n * QR_MODULE;
    draw_qr(INFO_CX - qr_w / 2, y);                                     y += qr_w + 18;
#endif
    font_text_centered(INFO_CX, y, "keyandcable.com", 2, COL_PRINT);
}
