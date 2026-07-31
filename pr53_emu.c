// pr53_emu.c v15 — Raw bus dumper, writes only, bigger ring
//
// v14 dropped events during bursts. Symptom: display starts coherent
// ("Concert...") then goes garbled once a critical command byte (SET_CGRAM
// or SET_DDRAM) gets dropped, because state machine loses track of
// where writes are landing.
//
// Two fixes:
//   1. PIO0 skips reads (jmp pin, 0) same as v13 did. Reads are noise for
//      the display state machine and doubled the event rate.
//   2. Ring buffer 4x larger (2048 slots).
//
// Together that's ~8x more headroom against bursts. Output format is
// unchanged from v14 so pr53_display.py works as-is.

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "hardware/gpio.h"

#define PIN_DB4  4
#define PIN_DB7  7
#define PIN_RS   8
#define PIN_RW   9
#define PIN_CS  11

#define RING_SLOTS 2048

typedef struct {
    uint32_t us;
    uint8_t  byte;
    uint8_t  rs;
    uint8_t  rw;
} byte_event_t;

static byte_event_t event_ring[RING_SLOTS];
static volatile uint32_t ring_head;
static volatile uint32_t ring_tail;
static volatile uint32_t drop_count;

static uint pio_cap_sm;
static uint pio_rd_sm;
static volatile uint8_t current_ac;

// === PIO0: Skip reads, capture writes only (v13-style) ===
//   0: wait 1 pin 7
//   1: wait 0 pin 7
//   2: mov y, y [31]  (settle)
//   3: jmp pin, 0     (if R/W high → skip this pulse)
//   4: in pins, 6     (DB4-DB7 + RS + R/W = 6 bits; R/W always 0 here)
//   5: push
static void pio_capture_init(void) {
    uint16_t prog[6] = {
        0x20A7, 0x2027, 0xBF42, 0x00C0, 0x4006, 0x8000,
    };
    struct pio_program p = { .instructions = prog, .length = 6, .origin = -1 };
    uint offset = pio_add_program(pio0, &p);
    pio_cap_sm = pio_claim_unused_sm(pio0, true);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset, offset + 5);
    sm_config_set_in_pins(&c, PIN_DB4);
    sm_config_set_in_shift(&c, false, false, 6);
    sm_config_set_jmp_pin(&c, PIN_RW);
    sm_config_set_clkdiv(&c, 1.0f);

    for (int i = PIN_DB4; i <= PIN_CS; i++) {
        pio_gpio_init(pio0, i);
        gpio_set_dir(i, GPIO_IN);
    }
    for (int i = PIN_DB4; i <= PIN_DB7; i++) {
        gpio_pull_down(i);
    }
    pio_sm_init(pio0, pio_cap_sm, offset, &c);
    pio_sm_set_enabled(pio0, pio_cap_sm, true);
}

// === PIO1: Paired read response (unchanged) ===
static void pio_read_response_init(void) {
    uint16_t prog[17] = {
        0x20A7, 0x2027, 0x00C4, 0x0000, 0x8080,
        0xA027, 0x6004, 0xE08F, 0x20A7, 0xE080,
        0x2027, 0x00CD, 0x0000, 0x6004, 0xE08F,
        0x20A7, 0xE080,
    };
    struct pio_program p = { .instructions = prog, .length = 17, .origin = -1 };
    uint offset = pio_add_program(pio1, &p);
    pio_rd_sm = pio_claim_unused_sm(pio1, true);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset, offset + 16);
    sm_config_set_in_pins(&c, PIN_DB4);
    sm_config_set_out_pins(&c, PIN_DB4, 4);
    sm_config_set_set_pins(&c, PIN_DB4, 4);
    sm_config_set_out_shift(&c, true, false, 32);
    sm_config_set_jmp_pin(&c, PIN_RW);
    sm_config_set_clkdiv(&c, 1.0f);

    for (int i = PIN_DB4; i <= PIN_DB7; i++) {
        pio_gpio_init(pio1, i);
        gpio_set_drive_strength(i, GPIO_DRIVE_STRENGTH_12MA);
        gpio_set_slew_rate(i, GPIO_SLEW_RATE_FAST);
        gpio_pull_down(i);
    }
    pio_sm_init(pio1, pio_rd_sm, offset, &c);
    pio_sm_set_enabled(pio1, pio_rd_sm, true);
}

static inline uint32_t pack_ac(uint8_t ac_val) {
    uint8_t hi = (ac_val >> 4) & 0x07;
    uint8_t lo = ac_val & 0x0F;
    return (uint32_t)(lo << 4) | hi;
}

static void push_event(uint32_t us, uint8_t byte, uint8_t rs, uint8_t rw) {
    uint32_t h = ring_head;
    uint32_t t = ring_tail;
    if ((h - t) >= RING_SLOTS) {
        drop_count++;
        return;
    }
    byte_event_t *e = &event_ring[h % RING_SLOTS];
    e->us = us; e->byte = byte; e->rs = rs; e->rw = rw;
    __sync_synchronize();
    ring_head = h + 1;
}

// Core 1: Pair write nibbles (reads already filtered by PIO0)
static void __not_in_flash_func(core1_entry)(void) {
    int pending_nib = -1;
    int pending_rs = -1;
    uint32_t pending_us = 0;
    uint8_t ac = 0;
    bool cg = false;
    bool inc = true;

    while (true) {
        while (!pio_sm_is_rx_fifo_empty(pio0, pio_cap_sm)) {
            uint32_t w = pio_sm_get(pio0, pio_cap_sm);
            uint32_t us = to_us_since_boot(get_absolute_time());
            uint8_t nib = ((w>>0)&1)|((w>>1)&1)<<1|((w>>2)&1)<<2|((w>>3)&1)<<3;
            uint8_t rs = (w >> 4) & 1;

            if (pending_nib < 0) {
                pending_nib = nib; pending_rs = rs;
                pending_us = us;
                continue;
            }

            uint8_t b = ((uint8_t)pending_nib << 4) | nib;
            push_event(pending_us, b, pending_rs, 0);

            if (pending_rs == 0) {
                if (b <= 0x03) { ac = 0; cg = false; }
                else if ((b & 0xFC) == 0x04) inc = (b & 0x02) != 0;
                else if ((b & 0xC0) == 0x40) { ac = b & 0x3F; cg = true; }
                else if (b & 0x80) { ac = b & 0x7F; cg = false; }
            } else {
                if (cg) ac = (ac + (inc ? 1 : -1)) & 0x3F;
                else    ac = (ac + (inc ? 1 : -1)) & 0x7F;
            }
            current_ac = ac;

            pending_nib = -1; pending_rs = -1;
        }
        tight_loop_contents();
    }
}

static const char *decode_cmd(uint8_t b, char *buf, size_t bufsz) {
    if (b == 0x00) return "NOP";
    if (b == 0x01) return "CLEAR";
    if (b <= 0x03) return "HOME";
    if ((b & 0xFC) == 0x04) {
        snprintf(buf, bufsz, "ENTRY_MODE inc=%d shift=%d",
                 (b >> 1) & 1, b & 1);
        return buf;
    }
    if ((b & 0xF8) == 0x08) {
        snprintf(buf, bufsz, "DISP_CTRL disp=%d cur=%d blink=%d",
                 (b >> 2) & 1, (b >> 1) & 1, b & 1);
        return buf;
    }
    if ((b & 0xF0) == 0x10) {
        snprintf(buf, bufsz, "SHIFT %s %s",
                 (b >> 3) & 1 ? "disp" : "cur",
                 (b >> 2) & 1 ? "right" : "left");
        return buf;
    }
    if ((b & 0xE0) == 0x20) {
        snprintf(buf, bufsz, "FUNC_SET 8bit=%d 2line=%d 5x10=%d",
                 (b >> 4) & 1, (b >> 3) & 1, (b >> 2) & 1);
        return buf;
    }
    if ((b & 0xC0) == 0x40) {
        snprintf(buf, bufsz, "SET_CGRAM 0x%02X", b & 0x3F);
        return buf;
    }
    if (b & 0x80) {
        snprintf(buf, bufsz, "SET_DDRAM 0x%02X", b & 0x7F);
        return buf;
    }
    snprintf(buf, bufsz, "?");
    return buf;
}

int main(void) {
    stdio_init_all();
    for (int i = 0; i < 30 && !stdio_usb_connected(); i++)
        sleep_ms(100);

    printf("\n# SX-PR53 bus dumper v15 (writes only, 2048 ring)\n");
    printf("# format: t=<us> W CMD/DAT 0x<byte> [decoded]\n");
    printf("# ready — power-cycle piano now\n\n");

    current_ac = 0;
    ring_head = ring_tail = drop_count = 0;

    pio_capture_init();
    pio_read_response_init();
    pio_sm_put(pio1, pio_rd_sm, pack_ac(0));

    multicore_launch_core1(core1_entry);

    absolute_time_t next_alive = make_timeout_time_ms(2000);
    uint32_t last_drops = 0;

    while (true) {
        if (pio_sm_get_tx_fifo_level(pio1, pio_rd_sm) < 2) {
            pio_sm_put(pio1, pio_rd_sm, pack_ac(current_ac));
        }

        uint32_t h = ring_head;
        uint32_t t = ring_tail;
        while (t != h) {
            byte_event_t *e = &event_ring[t % RING_SLOTS];
            char buf[64];
            if (e->rs == 0) {
                const char *ann = decode_cmd(e->byte, buf, sizeof(buf));
                printf("t=%08lu W CMD 0x%02X [%s]\n",
                       (unsigned long)e->us, e->byte, ann);
            } else if (e->byte >= 32 && e->byte < 127) {
                printf("t=%08lu W DAT 0x%02X '%c'\n",
                       (unsigned long)e->us, e->byte, e->byte);
            } else if (e->byte < 8) {
                printf("t=%08lu W DAT 0x%02X (CGRAM ref #%d)\n",
                       (unsigned long)e->us, e->byte, e->byte);
            } else {
                printf("t=%08lu W DAT 0x%02X\n",
                       (unsigned long)e->us, e->byte);
            }
            t++;
        }
        ring_tail = t;

        if (time_reached(next_alive)) {
            uint32_t d = drop_count;
            uint32_t depth = h - ring_tail;
            printf("# ALIVE us=%lu ring_depth=%lu drops=%lu\n",
                   (unsigned long)to_us_since_boot(get_absolute_time()),
                   (unsigned long)depth, (unsigned long)d);
            if (d != last_drops) {
                printf("# WARN dropped %lu events since last ping — "
                       "state may be corrupted\n",
                       (unsigned long)(d - last_drops));
                last_drops = d;
            }
            next_alive = make_timeout_time_ms(2000);
        }
    }
}
