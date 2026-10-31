// pr53_state.h — the decoded display state shared between the decode core
// and the render core.
//
// This mirrors, field-for-field, what pr53_display.py decodes from the bus.
// core0 (decode) owns the HD44780 emulation + decoders and writes this
// struct; core1 (render) reads it and pushes pixels to the ILI9488. The
// handoff uses a seqlock (see pr53_state.c) so the reader never sees a
// half-written struct without locking.
//
// KEEP IN SYNC with pr53_display.py — the decoders here are a 1:1 port of
// the Python ones. When a mapping is confirmed in Python (e.g. a hundreds
// digit), update BOTH.

#ifndef PR53_STATE_H
#define PR53_STATE_H

#include <stdint.h>
#include <stdbool.h>

#define PR53_NUM_PARTS   8
#define PR53_TEXT_LEN    12   // visible chars per DDRAM line (0..11)

// One decoded snapshot of the whole glass. All fields are "already decoded"
// — the render side does no bit-twiddling, it just draws these values.
typedef struct {
    // --- TOP zone ---
    int      tempo;              // 0..999, or -1 for blank/unknown
    char     chord[4];           // chord root letter(s), NUL-terminated ("" if none)
    char     transpose[4];       // transpose note name, NUL-terminated ("" if none)
    bool     transpose_sharp;    // sharp indicator in the transpose box

    // --- MIDDLE zone ---
    char     line1[PR53_TEXT_LEN + 1];  // voice name (DDRAM 0x00..0x0B)
    char     line2[PR53_TEXT_LEN + 1];  // rhythm name (DDRAM 0x40..0x4B)
    uint8_t  small_top;          // left-gutter 2-digit display (top). 0xFF = blank
    uint8_t  small_bot;          // left-gutter 2-digit display (bottom). 0xFF = blank

    // --- BOTTOM zone: 8 bargraphs ---
    int16_t  part_value[PR53_NUM_PARTS];  // 0..127, or -1 if not decodable
    uint8_t  part_level[PR53_NUM_PARTS];  // meter fill 0..5

    // Split indicators (LEFT/RIGHT keyboard graphic), if you wire them later.
    bool     split_left;
    bool     split_right;

    uint32_t frame_serial;       // bumped every commit; render skips if unchanged
} DisplayState;

// ---- Seqlock handoff (defined in pr53_state.c) ----
// Writer (decode core) brackets its update; reader (render core) retries if
// it caught a write in progress. Lock-free, single-writer/single-reader.
void          state_init(void);
void          state_begin_write(void);     // call before mutating g_state
void          state_end_write(void);        // call after; publishes the frame
void          state_read(DisplayState *out); // consistent snapshot for render

extern DisplayState g_state;  // the live struct (write only inside begin/end)

#endif // PR53_STATE_H
