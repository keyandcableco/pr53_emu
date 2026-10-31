// main.c — RP2350 dual-core: core0 decodes the HD44780 bus, core1 renders.
//
//   core0: bus-tap PIO -> reassemble nibbles -> hd44780_feed() -> on 0x0C
//          commit, pr53_decode_all() into g_state (seqlock write).
//   core1: state_read() -> render_frame() (dirty-tracked) to the ILI9488.
//
// The bus-tap front-end is STUBBED here (bus_get_byte) — drop in your working
// v15 PIO capture. Everything downstream is complete and host-tested.

#include "pr53_state.h"
#include "pr53_decode.h"
#include "pr53_render.h"
#include "pr53_ili9486_par.h"

#if PICO_ON_DEVICE
#include "pico/stdlib.h"
#include "pico/multicore.h"

// ---- Bus-tap front-end (STUB) --------------------------------------------
// Replace this with your v15 PIO capture. It must return the next captured
// HD44780 access: the reassembled 8-bit value, and whether RS=1 (data) or
// RS=0 (command). Block until one is available.
//
// Your v15 firmware already does the nibble reassembly and RS classification;
// wire its ring-buffer pop here.
extern bool bus_get_byte(uint8_t *out_byte, bool *out_is_data);

// ---- core1: render loop ----
static void core1_main(void) {
    ili9488_init();
    render_static();

    DisplayState snap;
    uint32_t last_serial = 0xFFFFFFFF;
    for (;;) {
        state_read(&snap);
        if (snap.frame_serial != last_serial) {
            last_serial = snap.frame_serial;
            render_frame(&snap);
        } else {
            sleep_us(500);   // nothing new; nap briefly
        }
    }
}

int main(void) {
    stdio_init_all();
    state_init();

    // Bring up the render core.
    multicore_launch_core1(core1_main);

    // core0: decode loop.
    static HD44780 hw;
    hd44780_init(&hw);

    uint8_t byte; bool is_data;
    for (;;) {
        if (!bus_get_byte(&byte, &is_data)) continue;
        bool commit = hd44780_feed(&hw, byte, is_data);
        if (commit && hw.display_on) {
            // Publish a fresh decoded frame on the piano's own 0x0C commit —
            // exactly the gating we validated in the Python emulator.
            state_begin_write();
            pr53_decode_all(&hw, &g_state);
            state_end_write();
        }
    }
}

#else
// Host build: no main (unit tests provide their own). Keep the translation
// unit non-empty.
int pr53_main_placeholder;
#endif
