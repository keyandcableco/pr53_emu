// pr53_decode.h — HD44780 bus emulation + segment decoders.
//
// 1:1 port of the decode logic in pr53_display.py. The bus-tap PIO feeds
// nibbles here; this reconstructs DDRAM + CGRAM, and on each 0x0C commit
// decodes the whole glass into DisplayState.

#ifndef PR53_DECODE_H
#define PR53_DECODE_H

#include <stdint.h>
#include <stdbool.h>
#include "pr53_state.h"

// The emulated controller memory.
typedef struct {
    uint8_t ddram[128];
    uint8_t cgram[64];   // 8 chars x 8 rows
    uint8_t ac;          // address counter
    bool    in_cgram;    // AC points into CGRAM vs DDRAM
    bool    display_on;
    bool    entry_inc;
    bool    hi_nibble_valid;
    uint8_t hi_nibble;   // latched high nibble awaiting its low half
} HD44780;

void hd44780_init(HD44780 *st);

// Feed one captured BYTE (already reassembled from two nibbles by the PIO
// front-end). is_cmd = RS line: false = command (RS=0), true = data (RS=1).
// Returns true if this byte was a DISP_CTRL (0x0C-class) commit — the caller
// should then run pr53_decode_all() + publish the frame.
bool hd44780_feed(HD44780 *st, uint8_t byte, bool is_data);

// Decode the entire glass from the current DDRAM/CGRAM into *out.
// (Does not touch frame_serial; the caller bumps that on publish.)
void pr53_decode_all(const HD44780 *st, DisplayState *out);

// Individual decoders (exposed for tests / partial use).
int  pr53_decode_tempo(const uint8_t *cgram);              // -1 if none
bool pr53_decode_chord(const uint8_t *cgram, char out[4]);
int  pr53_decode_bargraph_number(const uint8_t *cgram, int part); // -1 if none
int  pr53_decode_bargraph_level(const uint8_t *cgram, int part);  // 0..5

#endif // PR53_DECODE_H
