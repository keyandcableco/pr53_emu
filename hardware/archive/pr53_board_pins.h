// pr53_board_pins.h — SINGLE SOURCE OF TRUTH for the custom PR53 board.
//
// This header defines the RP2354B pin map for the merged single-board design.
// The KiCad schematic and the firmware BOTH reference these numbers, so the
// board and code can never disagree. When you lay out the schematic, wire the
// nets to exactly these GPIOs.
//
// Board: RP2354B (QFN-80, 48 GPIO, 2MB internal flash).
// LCD driven directly at 3.3V (panel has onboard level shifters — confirmed
// working on the bench). Piano 5V bus read through a 74LVC245 buffer.

#ifndef PR53_BOARD_PINS_H
#define PR53_BOARD_PINS_H

// ---- LCD 16-bit parallel data bus ----
// MUST be 16 CONTIGUOUS GPIOs starting at DB0 so the driver sets the whole
// bus with one masked write. GP0..GP15.
#define BOARD_LCD_DB_BASE   0     // DB0=GP0 ... DB15=GP15
// ---- LCD control ----
#define BOARD_LCD_RS        16
#define BOARD_LCD_WR        17
#define BOARD_LCD_RST       18
// LCD_CS  -> tied to GND on the board (always selected), no GPIO
// LCD_BL  -> tied to 3V3 on the board (always on),      no GPIO

// ---- Piano-bus tap (through 74LVC245, 5V in / 3V3 out) ----
// Contiguous block so PIO in_pins works like the v15/v16 firmware.
// in_pins base = TAP_DB4, jmp_pin = TAP_RW (unchanged capture structure).
#define BOARD_TAP_DB4       20
#define BOARD_TAP_DB5       21
#define BOARD_TAP_DB6       22
#define BOARD_TAP_DB7       23
#define BOARD_TAP_RS        24
#define BOARD_TAP_RW        25
#define BOARD_TAP_CS        26
// PIO: sm_config_set_in_pins(&c, BOARD_TAP_DB4);  // base
//      sm_config_set_jmp_pin(&c, BOARD_TAP_RW);
// DB7 external 10k pulldown: placed 0402 from the 245 INPUT pin for the
// piano's DB7 line to GND (the pulldown must sit on the 5V bus side, exactly
// as on the breadboard — it keeps the busy flag from floating).

// ---- Misc ----
#define BOARD_STATUS_LED    28    // optional activity LED

// ---- NOT GPIO (handled by the RP2354B reference circuit) ----
//   USB_DM / USB_DP   : USB-C, 27R series each
//   XIN / XOUT        : 12 MHz crystal + 2x 27pF
//   RUN               : reset button, 10k pullup, 100n
//   QSPI_SS/BOOTSEL   : BOOTSEL button to GND
//   internal flash    : RP2354B, no external flash chip needed

// NOTE: On the OLD two-board firmware the LCD data base was also GP0 and the
// tap was GP4-11. On THIS board the tap moves to GP20-26 so it doesn't collide
// with the 16-bit LCD bus. Update the firmware's PIN_DB4.. / PAR_DB_BASE to
// these values when you merge the two firmwares into one binary.

#endif // PR53_BOARD_PINS_H
