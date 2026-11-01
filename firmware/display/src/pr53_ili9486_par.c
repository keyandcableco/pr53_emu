// pr53_ili9486_par.c — 16-bit parallel (8080) driver for the HiLetgo
// ILI9486/ILI9488 3.5" 480x320 module.
//
// Write strategy: DB0-15 live on 16 consecutive GPIOs, so we set the whole
// bus with one masked SIO write, then pulse WR. That's the fast path this
// interface is built for — one write every ~3 instructions once inlined.
//
// Command set (0x11 sleep-out, 0x3A COLMOD, 0x36 MADCTL, 0x2A/0x2B/0x2C
// window+memory-write) is the SAME as the SPI ILI9488 chip family — only the
// transport differs, so this init sequence mirrors pr53_ili9488.c's.

#include "pr53_ili9486_par.h"

#if PICO_ON_DEVICE
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/structs/sio.h"

#define DB_MASK   (0xFFFFu << PAR_DB_BASE)

static inline void set_bus(uint16_t v) {
    // One masked write sets exactly DB0..DB15, leaving other GPIOs alone.
    uint32_t bits = ((uint32_t)v << PAR_DB_BASE) & DB_MASK;
    sio_hw->gpio_out = (sio_hw->gpio_out & ~DB_MASK) | bits;
}

static inline void pulse_wr(void) {
    // WR is active-low on this family: data is latched on the rising edge.
    gpio_put(PAR_PIN_WR, 0);
    __asm volatile("nop\nnop\nnop");   // >=15ns low pulse; NOPs are plenty at 150MHz+
    gpio_put(PAR_PIN_WR, 1);
}

static inline void wr_cmd(uint8_t c) {
    gpio_put(PAR_PIN_RS, 0);
    set_bus(c);
    pulse_wr();
}
static inline void wr_data16(uint16_t d) {
    gpio_put(PAR_PIN_RS, 1);
    set_bus(d);
    pulse_wr();
}
static inline void wr_param(uint8_t p) { wr_data16(p); }  // params are 8-bit-in-16

// Power, VCOM and gamma set-up: MCUFRIEND_kbv's ILI9486 table (github.com/
// prenticedavid/MCUFRIEND_kbv, case 0x9486, GAMMA9486 4). The chip's own
// defaults ("default GAMMA terrible" there) give a response that isn't even
// monotonic: on this panel a value of 1 lit brighter than 16 (test screen,
// 2026-10-31), which is what made every colour look wrong. Each entry is
// command, parameter count, parameters.
static const uint8_t PANEL_SETUP[] = {
    0xC0, 2, 0x0d, 0x0d,                 // power control 1
    0xC1, 2, 0x43, 0x00,                 // power control 2
    0xC2, 1, 0x00,                       // power control 3
    0xC5, 4, 0x00, 0x48, 0x00, 0x48,     // VCOM control
    0xB4, 1, 0x00,                       // inversion control
    0xB6, 3, 0x02, 0x02, 0x3B,           // display function control
    0xE0, 15,
        0x0F, 0x21, 0x1C, 0x0B, 0x0E, 0x08, 0x49, 0x98, 0x38, 0x09, 0x11, 0x03, 0x14, 0x10, 0x00,  // positive gamma
    0xE1, 15,
        0x0F, 0x2F, 0x2B, 0x0C, 0x0E, 0x06, 0x47, 0x76, 0x37, 0x07, 0x11, 0x04, 0x23, 0x1E, 0x00,  // negative gamma
};

void ili9488_init(void) {
    // Configure DB0-15 + control lines as outputs.
    for (int i = 0; i < 16; i++) {
        gpio_init(PAR_DB_BASE + i);
        gpio_set_dir(PAR_DB_BASE + i, true);
    }
    gpio_init(PAR_PIN_RS);  gpio_set_dir(PAR_PIN_RS, true);
    gpio_init(PAR_PIN_WR);  gpio_set_dir(PAR_PIN_WR, true); gpio_put(PAR_PIN_WR, 1);
    if (PAR_PIN_CS >= 0) {
        gpio_init(PAR_PIN_CS); gpio_set_dir(PAR_PIN_CS, true); gpio_put(PAR_PIN_CS, 0);
    }
    gpio_init(PAR_PIN_RST); gpio_set_dir(PAR_PIN_RST, true);
    if (PAR_PIN_BL >= 0) {
        gpio_init(PAR_PIN_BL); gpio_set_dir(PAR_PIN_BL, true); gpio_put(PAR_PIN_BL, 1);
    }

    // Hardware reset (active low per pin map: "LCD_RST Low level Enable").
    gpio_put(PAR_PIN_RST, 1); sleep_ms(5);
    gpio_put(PAR_PIN_RST, 0); sleep_ms(20);
    gpio_put(PAR_PIN_RST, 1); sleep_ms(150);

    wr_cmd(0x01); sleep_ms(150);        // software reset
    wr_cmd(0x28);                       // display off while it's set up
    wr_cmd(0x3A); wr_param(0x55);       // COLMOD = 16-bit RGB565
    for (size_t i = 0; i < sizeof(PANEL_SETUP); ) {
        wr_cmd(PANEL_SETUP[i]);
        uint8_t n = PANEL_SETUP[i + 1];
        for (uint8_t k = 0; k < n; k++) wr_param(PANEL_SETUP[i + 2 + k]);
        i += 2u + n;
    }
    wr_cmd(0x11); sleep_ms(150);        // sleep out
    wr_cmd(0x29);                       // display on
    wr_cmd(0x36); wr_param(theme_madctl());  // rotation + color order from pr53_theme.h
    wr_cmd(0x20);                       // inversion off
}

void ili9488_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    wr_cmd(0x2A);
    wr_param(x0 >> 8); wr_param(x0 & 0xFF);
    wr_param(x1 >> 8); wr_param(x1 & 0xFF);
    wr_cmd(0x2B);
    wr_param(y0 >> 8); wr_param(y0 & 0xFF);
    wr_param(y1 >> 8); wr_param(y1 & 0xFF);
    wr_cmd(0x2C);
}

void ili9488_push(uint16_t color, uint32_t n) {
    gpio_put(PAR_PIN_RS, 1);
    for (uint32_t i = 0; i < n; i++) { set_bus(color); pulse_wr(); }
}

void ili9488_fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                       uint16_t color) {
    if (!w || !h) return;
    ili9488_set_window(x, y, x + w - 1, y + h - 1);
    ili9488_push(color, (uint32_t)w * h);
}

void ili9488_blit(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                  const uint16_t *pixels) {
    if (!w || !h) return;
    ili9488_set_window(x, y, x + w - 1, y + h - 1);
    gpio_put(PAR_PIN_RS, 1);
    uint32_t n = (uint32_t)w * h;
    for (uint32_t i = 0; i < n; i++) { set_bus(pixels[i]); pulse_wr(); }
}

#else  // host build: draw into a framebuffer so layouts can be previewed on a PC

#include <stdio.h>

static uint16_t fb[ILI_H][ILI_W];

void ili9488_init(void) {}

// The open window and where the next pushed pixel goes, as on the panel.
static uint16_t win_x0, win_x1, win_y1, cur_x, cur_y;

void ili9488_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    win_x0 = x0; win_x1 = x1; win_y1 = y1;
    cur_x = x0; cur_y = y0;
}

void ili9488_push(uint16_t col, uint32_t n) {
    for (; n && cur_y <= win_y1; n--) {
        if (cur_x < ILI_W && cur_y < ILI_H) fb[cur_y][cur_x] = col;
        if (++cur_x > win_x1) { cur_x = win_x0; cur_y++; }
    }
}

void ili9488_fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t col) {
    for (int yy = y; yy < y + h && yy < ILI_H; yy++)
        for (int xx = x; xx < x + w && xx < ILI_W; xx++)
            fb[yy][xx] = col;
}

void ili9488_blit(uint16_t x, uint16_t y, uint16_t w, uint16_t h, const uint16_t *p) {
    for (int yy = 0; yy < h; yy++)
        for (int xx = 0; xx < w; xx++)
            if (y + yy < ILI_H && x + xx < ILI_W) fb[y + yy][x + xx] = p[yy * w + xx];
}

// Write the framebuffer as a binary PPM, in true colours (undoing the theme's
// byte and red/blue swaps; the panel's own BGR bit isn't shown here).
int ili9488_host_save_ppm(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fprintf(f, "P6\n%d %d\n255\n", ILI_W, ILI_H);
    for (int y = 0; y < ILI_H; y++)
        for (int x = 0; x < ILI_W; x++) {
            uint16_t v = fb[y][x];
#if THEME_SWAP_BYTES
            v = (uint16_t)((v >> 8) | (v << 8));
#endif
            uint8_t rgb[3] = { (uint8_t)((v >> 11) << 3), (uint8_t)(((v >> 5) & 0x3F) << 2),
                               (uint8_t)((v & 0x1F) << 3) };
#if THEME_SWAP_RB
            uint8_t t = rgb[0]; rgb[0] = rgb[2]; rgb[2] = t;
#endif
            fwrite(rgb, 1, 3, f);
        }
    return fclose(f);
}

#endif
