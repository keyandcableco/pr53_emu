// colour_test.c — colour bring-up screen for the panel, built as its own
// firmware (pr53_colour_test.uf2). It draws raw 16-bit bus words, bypassing
// the theme, so one straight-on photo shows how the panel turns bus values
// into colour:
//
//   top     one bar per data line, DB0..DB15, with only that line high
//   middle  R, G, B, W: 0xF800, 0x07E0, 0x001F, 0xFFFF (standard RGB565)
//   bottom  the PR53 palette (field, digits, a rule line) encoded 8 ways:
//           A plain, B red/blue swapped, C bytes swapped, D both (what the
//           main firmware sent until now), E-H the same four inverted
//
// Labels are white on black: all lines high or all low, which reads the same
// whatever order the data lines are in. Rotation is the theme's.

#include "pr53_ili9486_par.h"
#include "pr53_font.h"
#if PICO_ON_DEVICE
#include "pico/stdlib.h"
#endif

#define WHITE 0xFFFF
#define BLACK 0x0000

// Encoding n: bit 0 swaps red and blue, bit 1 swaps bytes, bit 2 inverts.
static uint16_t encode(int n, uint8_t r, uint8_t g, uint8_t b) {
    uint16_t v = (n & 1) ? rgb565(b, g, r) : rgb565(r, g, b);
    if (n & 2) v = (uint16_t)((v >> 8) | (v << 8));
    if (n & 4) v = (uint16_t)~v;
    return v;
}

static void colour_test_draw(void) {
    ili9488_fill_rect(0, 0, ILI_W, ILI_H, BLACK);

    for (int k = 0; k < 16; k++) {                       // data lines
        char lab[3] = { (char)(k < 10 ? '0' + k : '1'), (char)(k < 10 ? 0 : '0' + k - 10), 0 };
        font_text(k * 30 + 3, 2, lab, 2, WHITE);
        ili9488_fill_rect(k * 30 + 1, 20, 28, 110, (uint16_t)(1u << k));
    }

    static const struct { const char *label; uint16_t v; } REF[] = {
        {"R", 0xF800}, {"G", 0x07E0}, {"B", 0x001F}, {"W", 0xFFFF},
    };
    for (int i = 0; i < 4; i++) {                        // reference colours
        font_text(i * 120 + 54, 138, REF[i].label, 2, WHITE);
        ili9488_fill_rect(i * 120 + 2, 156, 116, 46, REF[i].v);
    }

    for (int n = 0; n < 8; n++) {                        // palette, 8 encodings
        int x = n * 60;
        char lab[2] = { (char)('A' + n), 0 };
        font_text(x + 24, 210, lab, 2, WHITE);
        ili9488_fill_rect(x + 2, 228, 56, 90, encode(n, 0xc4, 0xcf, 0x50));     // field
        font_text(x + 12, 240, "88", 3, encode(n, 0x38, 0x54, 0x3c));          // digits
        ili9488_fill_rect(x + 6, 290, 48, 3, encode(n, 0x48, 0x64, 0x4a));      // rule
    }
}

#if PICO_ON_DEVICE
int main(void) {
    stdio_init_all();      // keeps USB up, so a 1200-baud touch still reaches BOOTSEL
    ili9488_init();
    colour_test_draw();
    for (;;) sleep_ms(1000);
}
#else
int main(void) {           // host: layout check only (the preview un-swaps colours)
    colour_test_draw();
    return ili9488_host_save_ppm("build-host/colour_test.ppm");
}
#endif
