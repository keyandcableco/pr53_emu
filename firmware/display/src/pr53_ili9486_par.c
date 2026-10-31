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

    wr_cmd(0x01); sleep_ms(120);        // software reset
    wr_cmd(0x11); sleep_ms(120);        // sleep out

    wr_cmd(0x3A); wr_param(0x55);       // COLMOD = 16-bit RGB565

    wr_cmd(0x36); wr_param(theme_madctl());  // rotation + color order from pr53_theme.h

    wr_cmd(0x29); sleep_ms(20);         // display on
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

void ili9488_fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                       uint16_t color) {
    if (!w || !h) return;
    ili9488_set_window(x, y, x + w - 1, y + h - 1);
    gpio_put(PAR_PIN_RS, 1);
    uint32_t n = (uint32_t)w * h;
    for (uint32_t i = 0; i < n; i++) { set_bus(color); pulse_wr(); }
}

void ili9488_blit(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                  const uint16_t *pixels) {
    if (!w || !h) return;
    ili9488_set_window(x, y, x + w - 1, y + h - 1);
    gpio_put(PAR_PIN_RS, 1);
    uint32_t n = (uint32_t)w * h;
    for (uint32_t i = 0; i < n; i++) { set_bus(pixels[i]); pulse_wr(); }
}

#else  // host build stubs (unit tests / decode-only builds)

void ili9488_init(void) {}
void ili9488_set_window(uint16_t a,uint16_t b,uint16_t c,uint16_t d){(void)a;(void)b;(void)c;(void)d;}
void ili9488_fill_rect(uint16_t x,uint16_t y,uint16_t w,uint16_t h,uint16_t col){(void)x;(void)y;(void)w;(void)h;(void)col;}
void ili9488_blit(uint16_t x,uint16_t y,uint16_t w,uint16_t h,const uint16_t*p){(void)x;(void)y;(void)w;(void)h;(void)p;}

#endif
