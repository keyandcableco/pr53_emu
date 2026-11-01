// pr53_splash.h — the start-up screen: the Key & Cable Co. logo, with
// "Technics SX-PR53", "LCD replacement", a QR code and keyandcable.com
// beside it (pr53_splash.c draws it, pr53_logo.c holds the image data).
//
// It goes up as soon as the panel is set up and stays through the
// piano's own start-up screens: the empty display after it sets up its LCD,
// then "Technics / SX-PR53", for as long as the piano holds it (2.7 s in the
// v18 restart capture, 12 s in one earlier one). The first other frame (the
// play screen, or "ALL INITIAL" after a factory reset) hands the screen back
// to the glass layout, repainted in full. If the piano restarts while the
// display stays powered (the carrier on USB), the logo comes back in place of
// its "Technics" screen. Nothing here touches decoding: core 1 just chooses
// between the logo and the glass. THEME_SPLASH in pr53_theme.h turns it off.

#ifndef PR53_SPLASH_H
#define PR53_SPLASH_H

#include <stdint.h>
#include <stdbool.h>
#include "pr53_state.h"

// Longest the logo stays up, in case the piano never gets past its start-up
// screens (the tap link down, the piano off, or stuck on "Technics").
#define SPLASH_MAX_MS  30000

typedef struct {
    bool     on;          // the logo is on the screen
    bool     boot_text;   // the last frame showed "Technics / SX-PR53"
    uint32_t since_ms;    // when the logo went up
} Splash;

typedef enum {
    SPLASH_IDLE,   // no logo: render frames as usual
    SPLASH_HOLD,   // logo up: leave the screen alone
    SPLASH_SHOW,   // put the logo up: splash_draw()
    SPLASH_END,    // logo done: render_static(), then render_frame()
} SplashStep;

// At power-up: SPLASH_SHOW, or SPLASH_IDLE with THEME_SPLASH off.
SplashStep splash_start(Splash *sp, uint32_t now_ms);

// Once per pass of the render loop, with the latest state; fresh = it's a
// frame not seen before.
SplashStep splash_step(Splash *sp, const DisplayState *s, bool fresh,
                       uint32_t now_ms);

// Paints the start-up screen: the logo as one full-screen window (153,600
// pixels), then the text and QR code over it.
void splash_draw(void);

#endif // PR53_SPLASH_H
