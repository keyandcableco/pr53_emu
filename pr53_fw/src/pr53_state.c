// pr53_state.c — single-writer/single-reader seqlock for the DisplayState
// handoff between the decode core (writer) and render core (reader).
//
// The writer bumps an odd sequence before writing and an even one after.
// The reader samples seq, copies, and re-checks seq; if it changed or was
// odd, it retries. Lock-free, no priority inversion, tiny.

#include "pr53_state.h"

#if PICO_ON_DEVICE
#include "pico/sync.h"
#include "hardware/sync.h"
#endif

DisplayState g_state;

static volatile uint32_t seq = 0;

static inline void mem_barrier(void) {
#if PICO_ON_DEVICE
    __dmb();
#else
    __sync_synchronize();
#endif
}

void state_init(void) {
    seq = 0;
    for (int i = 0; i < PR53_NUM_PARTS; i++) {
        g_state.part_value[i] = -1;
        g_state.part_level[i] = 0;
    }
    g_state.tempo = -1;
    g_state.chord[0] = 0;
    g_state.transpose[0] = 0;
    g_state.line1[0] = 0;
    g_state.line2[0] = 0;
    g_state.small_top = 0xFF;
    g_state.small_bot = 0xFF;
    g_state.frame_serial = 0;
}

void state_begin_write(void) {
    seq++;          // -> odd: "write in progress"
    mem_barrier();
}

void state_end_write(void) {
    g_state.frame_serial++;
    mem_barrier();
    seq++;          // -> even: "write complete"
}

void state_read(DisplayState *out) {
    uint32_t s0, s1;
    do {
        s0 = seq;
        mem_barrier();
        *out = g_state;             // struct copy
        mem_barrier();
        s1 = seq;
    } while ((s0 & 1) || s0 != s1);  // retry if mid-write or changed
}
