// pr53_render.h — draws DisplayState onto the ILI9488, updating only the
// fields that changed since last frame (dirty tracking). This is what keeps
// updates smooth on real hardware: we never repaint the whole glass, only
// the digit/meter/text that moved.

#ifndef PR53_RENDER_H
#define PR53_RENDER_H

#include "pr53_state.h"

// Call once after ili9488_init(): paints the static furniture (backlight
// field, zone rules, printed labels, box outlines) that never changes.
void render_static(void);

// Call on each committed frame. Compares against the last rendered state and
// repaints only changed fields. Cheap when little changed.
void render_frame(const DisplayState *s);

#endif // PR53_RENDER_H
