// pr53_logo.h — the start-up screen's image data (pr53_logo.c, generated).
//
// Logo: the whole 480x320 screen, row by row from the top left, run-length
// coded: one byte per run, bits 7-6 the shade (0 = the glass field, 1 and 2
// two tints, 3 = the segment colour), bits 5-0 the run length minus 1 (1-64
// pixels). The runs add up to exactly 480x320 pixels.
//
// QR code for https://keyandcable.com: pr53_qr_n rows of pr53_qr_n modules,
// bit c of a row set for a dark module in column c (from the left).
//
// pr53_logo.c is made from logo/keyandcable_logo.svg by logo/logo_to_c.py:
// `make -f host.mk logo` after changing either.

#ifndef PR53_LOGO_H
#define PR53_LOGO_H

#include <stdint.h>

#define PR53_LOGO_WIDTH   480
#define PR53_LOGO_HEIGHT  320

extern const uint8_t  pr53_logo_rle[];
extern const uint32_t pr53_logo_rle_len;

extern const uint8_t  pr53_qr_n;
extern const uint32_t pr53_qr_rows[];

#endif // PR53_LOGO_H
