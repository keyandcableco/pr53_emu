// pr53_emu.c v18 — HD44780 bus tap for the SX-PR53, with display link
//
// PIO0 captures every write (reads are skipped at the PIO) into a 2048-slot
// ring. PIO1 answers every read with all zeros (busy clear), so the piano's
// CPU never stalls. Each write is logged over USB and forwarded to
// the display Pico over a one-way UART (uart1 TX on GP8, 1 Mbaud).
//
// History: v14 dropped events during bursts and the decoded display went
// garbled once a SET_CGRAM/SET_DDRAM byte was lost. v15 fixed that by
// skipping reads at the PIO and quadrupling the ring. v16 adds the display
// link. v17 starts at once instead of waiting up to 3 s for USB first. v18
// answers every read with all zeros: v16/v17 answered busy=0 plus the address
// counter, but the piano often reads the low half of that answer as its busy
// flag (address bit 3 on DB7), waits 3.8 ms for it to clear, and runs out of
// time to finish its text lines (seen: "ConcertGran", line 2 left on
// "SX-PR53"). Zeros read as "not busy" whichever half it reads. The USB log
// format is unchanged since v14.

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "hardware/gpio.h"
#include "hardware/uart.h"

#define PIN_DB4  0
#define PIN_DB7  3
#define PIN_RS   4
#define PIN_RW   5
// CS must sit at base+7 (=GP7): the capture PIO program has a hardcoded
// "wait pin 7" that gates on CS relative to in_base (PIN_DB4). GP6 is left
// unused so CS lands on GP7. Do NOT put CS on GP6 — the PIO would then wait
// on the wrong (floating) pin and capture would stall.
#define PIN_CS   7

// --- Display link: forward each decoded access to the DISPLAY Pico ---
// One-way UART display link (uart1 TX on GP8). Bus tap uses GP0-GP7.
// Protocol matches the display side's bus_tap.c:
//   byte0 = TAG (0x00 command / 0x01 data), byte1 = VALUE.
#define DISP_UART   uart1
// Display-link UART TX on GP8. Chosen so GP10-13 stay completely unused (less
// perfboard routing). GP8 sits at the bottom of the capture block on the Zero's
// right edge — adjacent to GP0-7, so the link jumper is short. GP8 is a valid
// uart1 TX pin (uart0's TX pins would land on GP0/GP12, both of which we're
// avoiding), hence DISP_UART = uart1. Capture uses GP0-5+GP7; GP6/GP9 unused.
#define DISP_TX_PIN 8
#define DISP_BAUD   1000000

static void disp_uart_init(void) {
    uart_init(DISP_UART, DISP_BAUD);
    gpio_set_function(DISP_TX_PIN, GPIO_FUNC_UART);
    uart_set_hw_flow(DISP_UART, false, false);
    uart_set_format(DISP_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(DISP_UART, true);
}

// NON-BLOCKING send. The old version used uart_putc_raw, which BLOCKS until
// the TX FIFO has space — at 1 Mbaud that stalled the drain loop, delayed PIO
// servicing, and scrambled nibble pairing (garbled capture, drops=0). Here we
// only write when BOTH tag+value fit in the FIFO right now; otherwise we skip
// this event on the display link. The USB capture log is unaffected either way.
// A skipped event just means one missed display update, self-corrected on the
// next DISP_CTRL commit — never corrupts the capture.
static inline void disp_uart_send(uint8_t rs, uint8_t byte) {
    // ATOMIC + NON-BLOCKING. This is the fix for the v16 garble: the old code
    // used uart_putc_raw, which BLOCKS on a full TX FIFO, stalling the capture
    // drain loop and scrambling nibble pairing (garbled stream, drops=0).
    //
    // Rule: only send when the TX FIFO is EMPTY. An empty 32-byte FIFO always
    // has room for our 2 bytes, so both writes are instant (never block), and
    // we never half-send a tag without its value (no receiver desync). If the
    // FIFO isn't empty, we skip this event on the DISPLAY link entirely — the
    // USB capture log is written separately and stays 100% complete. A skipped
    // display event just means one dropped screen update; the display resyncs
    // on the next DISP_CTRL (0x0C) commit, so nothing downstream corrupts.
    //
    // At 1 Mbaud, 2 bytes drain in ~20µs. HD44780 writes on this bus are ~40µs
    // apart, so in practice the FIFO is empty on essentially every event and
    // the display sees the full stream — but capture integrity no longer
    // depends on that being true.
    uart_hw_t *hw = uart_get_hw(DISP_UART);
    if (!(hw->fr & (1u << 7))) return;   // UARTFR TXFE (bit7): 1 = FIFO empty.
                                         // Not empty → skip, never block.
    hw->dr = rs ? 0x01 : 0x00;           // TAG   — instant, room guaranteed
    hw->dr = byte;                       // VALUE — instant, room guaranteed
}

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

// === PIO1: Paired read response ===
// Each paired read does one non-blocking pull: a queued answer if there is
// one, else the last answer again (kept in X). main() queues a single zero,
// so every nibble of every read is 0000.
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

    // Answer the piano's reads and capture its writes straight away: a piano
    // already running must not see its busy checks go unanswered.
    ring_head = ring_tail = drop_count = 0;

    pio_capture_init();
    pio_read_response_init();
    // Bring up the display link. IMPORTANT: your CMakeLists MUST have
    //   pico_enable_stdio_uart(<target> 0)
    // so stdio doesn't grab default UART pins. Capture now uses GP0/GP1
    // (DB4/DB5), and the display link is uart1 on GP8 — keep uart-stdio OFF so
    // nothing contends for those. Keep
    //   pico_enable_stdio_usb(<target> 1)
    // for your USB log. If uart-stdio is left on, console text could contend
    // with capture pins or the protocol bytes and corrupt the display stream.
    disp_uart_init();                 // bring up the display link
    pio_sm_put(pio1, pio_rd_sm, 0);   // every read answers 0000, 0000

    multicore_launch_core1(core1_entry);

    // No wait for a USB host: logging starts at once, and the banner is lost
    // if nothing is listening yet. The ring drains (and feeds the display)
    // from the start either way.
    printf("\n# SX-PR53 bus dumper v18 (reads answered with zeros)\n");
    printf("# format: t=<us> W CMD/DAT 0x<byte> [decoded]\n");
    printf("# ready\n\n");

    absolute_time_t next_alive = make_timeout_time_ms(2000);
    uint32_t last_drops = 0;

    while (true) {
        uint32_t h = ring_head;
        uint32_t t = ring_tail;
        while (t != h) {
            byte_event_t *e = &event_ring[t % RING_SLOTS];
            // Forward this access to the DISPLAY Pico. Fires for every event,
            // independent of the logging branches below — the USB log is
            // unchanged, so you keep the recorder workflow AND drive the LCD.
            disp_uart_send(e->rs, e->byte);
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
