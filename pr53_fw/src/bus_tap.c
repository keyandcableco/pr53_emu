// bus_tap.c (DISPLAY side) — receives HD44780 accesses from the TAP Pico
// over a one-way UART link and hands them to main.c via bus_get_byte().
//
// This REPLACES the first-light stub. Once this is in and the TAP Pico runs
// the matching sender, the meters come alive.
//
// Wire protocol (2 bytes per access):
//   byte 0: TAG   0x00 = command (RS=0),  0x01 = data (RS=1)
//   byte 1: VALUE the 8-bit bus value
// A "tag" byte that isn't 0x00/0x01 means we're out of frame sync: we drop
// it and keep reading until a valid tag appears, so a mid-stream power-up
// self-heals within one packet.
//
// WIRING (3 wires between the two Picos):
//   TAP UART TX  -> DISPLAY GP21 (uart1 RX)
//   TAP GND      -> DISPLAY GND            (shared ground REQUIRED)
//   (one-way link; no reverse wire needed)
//
// Pin choice: the parallel LCD data bus is GP0..GP15 and control GP16..GP18,
// so uart0 RX (GP1) would clash with DB1. We use uart1 RX on GP21, clear of
// the data block. USB stays free for debug prints (stdio over USB).

#include <stdbool.h>
#include <stdint.h>

#if PICO_ON_DEVICE
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"

// Pin choice: the parallel LCD data bus is on GP0..GP15, control on GP16-18.
// So uart0 RX (GP1) would collide with DB1 — we use uart1 RX on GP21 instead,
// which sits clear of the data block.
#define TAP_UART        uart1
#define TAP_UART_RX_PIN 21         // uart1 RX (clear of the GP0-15 data bus)
#define TAP_UART_BAUD   1000000    // 1 Mbaud: huge headroom, rock-solid on a short jumper

static bool s_inited = false;

static void ensure_init(void) {
    if (s_inited) return;
    uart_init(TAP_UART, TAP_UART_BAUD);
    gpio_set_function(TAP_UART_RX_PIN, GPIO_FUNC_UART);
    uart_set_hw_flow(TAP_UART, false, false);
    uart_set_format(TAP_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(TAP_UART, true);
    s_inited = true;
}

// Blocking read of one framed access. Resyncs automatically on a bad tag.
bool bus_get_byte(uint8_t *out_byte, bool *out_is_data) {
    ensure_init();
    for (;;) {
        uint8_t tag = uart_getc(TAP_UART);     // blocks until a byte arrives
        if (tag != 0x00 && tag != 0x01) {
            continue;                          // out of sync — skip, retry
        }
        uint8_t val = uart_getc(TAP_UART);     // the value byte
        *out_is_data = (tag == 0x01);
        *out_byte = val;
        return true;
    }
}

#else  // host build stub

bool bus_get_byte(uint8_t *out_byte, bool *out_is_data) {
    (void)out_byte; (void)out_is_data;
    return false;
}

#endif
