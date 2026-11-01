// main.c — RP2350 dual-core: core0 decodes the HD44780 bus, core1 renders.
//
//   core0: tap UART (bus_get_byte) -> hd44780_feed() -> on 0x0C
//          commit, pr53_decode_all() into g_state (seqlock write).
//   core1: state_read() -> render_frame() (dirty-tracked) to the ILI9488.

#include "pr53_state.h"
#include "pr53_decode.h"
#include "pr53_render.h"
#include "pr53_splash.h"
#include "pr53_ili9486_par.h"

#if PICO_ON_DEVICE
#include "pico/stdlib.h"
#include "pico/multicore.h"

// ---- Bus-tap front-end ----------------------------------------------------
// bus_tap.c receives each HD44780 access from the tap over the UART link and
// returns it here: the 8-bit value, and whether RS=1 (data) or RS=0
// (command). Blocks until one is available.
extern bool bus_get_byte(uint8_t *out_byte, bool *out_is_data);
extern bool bus_get_byte_timeout(uint8_t *out_byte, bool *out_is_data, uint32_t timeout_us);

// If the piano writes and then goes quiet this long without a DISP_CTRL,
// publish anyway. In the 2026-10-31 captures, gaps inside one update reach
// 30 ms and the piano's refresh tick is ~105 ms, so 60 ms fires once an update
// is over and still well before the next tick.
#define SETTLE_US 60000

// ---- core1: render loop ----
static uint32_t now_ms(void) { return to_ms_since_boot(get_absolute_time()); }

static void core1_main(void) {
    ili9488_init();

    // Start-up logo (pr53_splash.h) until the piano's play screen; core 0
    // decodes as usual meanwhile.
    Splash splash;
    if (splash_start(&splash, now_ms()) == SPLASH_SHOW) splash_draw();
    else render_static();

    DisplayState snap;
    uint32_t last_serial = 0xFFFFFFFF;
    for (;;) {
        state_read(&snap);
        bool fresh = snap.frame_serial != last_serial;
        last_serial = snap.frame_serial;
        switch (splash_step(&splash, &snap, fresh, now_ms())) {
        case SPLASH_SHOW: splash_draw(); break;
        case SPLASH_END:  render_static(); render_frame(&snap); break;  // whole glass
        case SPLASH_HOLD: sleep_us(500); break;
        case SPLASH_IDLE:
            if (fresh) render_frame(&snap);
            else sleep_us(500);   // nothing new; nap briefly
            break;
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
    bool dirty = false;   // writes since the last published frame
    for (;;) {
        if (!bus_get_byte_timeout(&byte, &is_data, SETTLE_US)) {
            // Bus quiet. Menus are written without a DISP_CTRL afterwards, so
            // publish whatever is pending rather than freeze on the old view.
            if (dirty && hw.display_on) {
                state_begin_write();
                pr53_decode_all(&hw, &g_state);
                state_end_write();
            }
            dirty = false;
            continue;
        }
        bool commit = hd44780_feed(&hw, byte, is_data);
        dirty = true;
        if (commit && hw.display_on) {
            // Publish a fresh decoded frame on the piano's own 0x0C commit —
            // exactly the gating we validated in the Python emulator.
            state_begin_write();
            pr53_decode_all(&hw, &g_state);
            state_end_write();
            dirty = false;
        }
    }
}

#else
// Host build: no main (unit tests provide their own). Keep the translation
// unit non-empty.
int pr53_main_placeholder;
#endif
