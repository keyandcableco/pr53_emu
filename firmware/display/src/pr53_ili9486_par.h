// pr53_ili9486_par.h — 16-bit parallel (8080-style) driver for the HiLetgo
// 3.5" ILI9486/ILI9488 480x320 module.
//
// Same public API as the old SPI driver (pr53_ili9488_init/fill_rect/blit)
// so pr53_render.c and everything above it needs NO changes — only main.c's
// #include and CMakeLists.txt change to point at this file instead.
//
// This panel is a 16-bit-wide "8080" parallel bus: RS/WR/CS/RST + DB0-15.
// No SPI, no MISO/MOSI here (this board's SPI pins are for its onboard SD
// card slot, unrelated to driving the LCD).

#ifndef PR53_ILI9486_PAR_H
#define PR53_ILI9486_PAR_H

#include <stdint.h>

// ---- Wiring for a display-only Pico 2 (26 GPIO) ----
// DB0..DB15 MUST be 16 CONSECUTIVE GPIO numbers, DB0 = lowest, so one masked
// GPIO write sets the whole bus. On a display-only board GP0-15 is the clean
// contiguous block; control lines go just above it.
//   CS is tied LOW to the panel (always selected) — not a GPIO here.
//   BL (backlight) is tied to 3V3/5V always-on — not a GPIO here.
#define PAR_DB_BASE   0      // DB0=GP0, DB1=GP1, ... DB15=GP15
#define PAR_PIN_RS    16
#define PAR_PIN_WR    17
#define PAR_PIN_RST   18
#define PAR_PIN_CS    -1     // tied low in hardware; -1 = driver won't touch it
#define PAR_PIN_BL    -1     // always-on in hardware; -1 = skip

// Panel native resolution is 480x320. When THEME_ROTATION does a 90/270 turn
// (row/col swap), the addressable width/height swap too. ILI_W/ILI_H below
// follow the theme so the layout always maps onto the panel correctly.
#include "pr53_theme.h"
#if THEME_PORTRAIT
#  define ILI_W  320
#  define ILI_H  480
#else
#  define ILI_W  480
#  define ILI_H  320
#endif

static inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

// Colors + rotation all come from pr53_theme.h — edit THAT file to restyle.
#include "pr53_theme.h"
#define COL_FIELD    THEME_COL_FIELD
#define COL_SEG      THEME_COL_SEG
#define COL_SEG_OFF  THEME_COL_SEG_OFF
#define COL_PRINT    THEME_COL_PRINT
#define COL_RULE     THEME_COL_RULE

// Same names as the old SPI driver so pr53_render.c is untouched.
void ili9488_init(void);
void ili9488_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);
void ili9488_fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                       uint16_t color);
void ili9488_blit(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                  const uint16_t *pixels);

#endif // PR53_ILI9486_PAR_H
