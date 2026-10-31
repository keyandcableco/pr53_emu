#!/usr/bin/env python3
"""
pr53_display.py — Realtime mock-LCD display for SX-PR53 v14 firmware.

Reads the v14 raw bus dumper event log over USB serial, replays each event
through a HD44780 state machine to maintain live DDRAM+CGRAM, and renders
the mock 16x2 LCD in real time.

Because we process every write (not just 0x0C snapshots), this stays in
sync with the piano's current display state — no more "a few button clicks
behind".

Usage:
    python3 pr53_display.py                     # auto-detect port
    python3 pr53_display.py --port /dev/ttyACM0
    python3 pr53_display.py --port COM3         # Windows

Dependencies: pyserial (pip install pyserial). tkinter is stdlib.
"""
import argparse
import re
import sys
import threading
import time
import tkinter as tk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Need pyserial. Install with:  pip install pyserial")
    sys.exit(1)


# ---------- HD44780 state machine ----------

class HD44780State:
    """Mirror of the LCD controller's DDRAM + CGRAM + AC. Fed by each
    write event from the event log."""

    def __init__(self):
        self.ddram = bytearray(128)
        for i in range(128):
            self.ddram[i] = 0x20  # blank on power-on (matches firmware init)
        self.cgram = bytearray(64)
        self.ac = 0
        self.in_cgram = False
        self.entry_inc = True
        # Track HD44780's display-on bit. Piano typically does display-off,
        # bulk writes, then display-on. Rendering only when display_on is
        # True hides the intermediate garbage.
        self.display_on = False

    def apply_cmd(self, b):
        if b == 0x01:
            for i in range(128): self.ddram[i] = 0x20
            self.ac = 0; self.in_cgram = False
        elif b <= 0x03:
            self.ac = 0; self.in_cgram = False
        elif (b & 0xFC) == 0x04:
            self.entry_inc = (b & 0x02) != 0
        elif (b & 0xF8) == 0x08:
            # DISP_CTRL: bit 2 = display on/off
            self.display_on = (b & 0x04) != 0
        elif (b & 0xC0) == 0x40:
            self.ac = b & 0x3F; self.in_cgram = True
        elif b & 0x80:
            self.ac = b & 0x7F; self.in_cgram = False
            # NOTE: we deliberately do NOT blank the line here. The piano
            # space-pads its text fields (writes a full fixed-width field
            # every time), so faithfully capturing every write leaves no
            # leftovers on its own. If stale trailing chars appear in the
            # display, that's a symptom of DROPPED writes (ring overflow /
            # nibble mispair) — a firmware/capture problem to fix at the
            # source, not to paper over with a clear here. Blanking the line
            # would hide that data loss.
        # Function set, shift: don't touch RAM or display_on; skip.

    def apply_data(self, b):
        step = 1 if self.entry_inc else -1
        if self.in_cgram:
            if self.ac < 64:
                self.cgram[self.ac] = b & 0x1F
            self.ac = (self.ac + step) & 0x3F
        else:
            if self.ac < 128:
                self.ddram[self.ac] = b
            self.ac = (self.ac + step) & 0x7F


# ---------- Tempo decoder (empirical segment mapping) ----------
#
# Tempo digits live in CGRAM char C1 across columns c0 (hundreds),
# c1 (tens), c2 (ones). Row-to-segment mapping was worked out from a
# clean 20-step +1 BPM campaign — see pr53_decode.py for the full
# analysis. Same digit table.

ROW_TO_SEG = {
    0: 'a',  # top
    1: 'b',  # top-right
    2: 'f',  # top-left
    3: 'g',  # middle
    4: 'c',  # bottom-right
    5: 'e',  # bottom-left
    # row 6 unused
    7: 'd',  # bottom
}

# This piano's specific glyph shapes — note "7" includes segment f
# (European-style tail). Also includes an entry for the hundreds
# digit's "1" glyph, which lights r1+r2 in c0 — a b+f pattern
# rather than the standard b+c. Same physical "1" shape on the
# glass, just wired to different CGRAM bits.
DIGIT_TABLE = {
    frozenset():         ' ',
    frozenset('abcdef'): '0',
    frozenset('bc'):     '1',
    frozenset('bf'):     '1',   # hundreds-digit "1" glyph (stylized)
    frozenset('abdeg'):  '2',
    frozenset('abg'):    '2',   # hundreds-digit "2" glyph (stylized)
    frozenset('abcdg'):  '3',
    frozenset('bcfg'):   '4',
    frozenset('acdfg'):  '5',
    frozenset('acdefg'): '6',
    frozenset('abcf'):   '7',
    frozenset('abcdefg'):'8',
    frozenset('abcdfg'): '9',
}

TEMPO_DIGITS = [(1, 0), (1, 1), (1, 2)]   # (char, col) hundreds→ones


def decode_tempo(cgram):
    """Decode the 3 tempo digits from CGRAM. Return int or None."""
    chars = []
    for ch, col in TEMPO_DIGITS:
        segs = set()
        for row, seg in ROW_TO_SEG.items():
            if (cgram[ch * 8 + row] >> (4 - col)) & 1:
                segs.add(seg)
        chars.append(DIGIT_TABLE.get(frozenset(segs), '?'))
    text = ''.join(chars).lstrip()
    try:
        return int(text)
    except ValueError:
        return None


# ---------- Bargraph decoders (8 parts) ----------
#
# Each part has a 3-digit number and a 5-level vertical bar meter.
#
# IMPORTANT: bargraph digits use a DIFFERENT row-to-segment mapping than
# tempo digits. The glass designer wired those areas independently. From
# a clean 0→5 walk on part 2, bargraphs use rows r0-r6 (r7 unused), while
# tempo uses r0-r5+r7 (r6 unused).
BARGRAPH_ROW_TO_SEG = {
    0: 'a',  # top (or d, ambiguous — a chosen by convention)
    1: 'b',  # top-right
    2: 'f',  # top-left
    3: 'g',  # middle
    4: 'c',  # bottom-right
    5: 'e',  # bottom-left
    6: 'd',  # bottom (or a)
    # row 7 unused
}

# NUMBER decoders: each entry is a list of (char, col) or None for
# [hundreds, tens, ones]. None means "not yet mapped, show as blank".
# Ones digits identified for all 8 parts from bargraph_part_locate
# campaign. Part 1 and Part 5 tens digits confirmed from tens_boundary
# and 5step_walk campaigns respectively — both live in C4 with column
# matching the ones-digit's approximate horizontal position. Parts 2-4
# tens are HYPOTHESIZED to be in C4 c1/c2/c3 by symmetry (unverified);
# Parts 6-8 tens location entirely unknown.
BARGRAPH_NUMBER_MAP = {
    0: [None, (4, 0), (5, 2)],   # Part 1: tens C4c0 CONFIRMED
    1: [None, (4, 1), (5, 1)],   # Part 2: tens C4c1 CONFIRMED (sweep-window)
    2: [None, (4, 2), (7, 4)],   # Part 3: tens C4c2 CONFIRMED (sweep-window)
    3: [None, (4, 3), (7, 3)],   # Part 4: tens C4c3 CONFIRMED (sweep-window)
    4: [None, (4, 4), (7, 2)],   # Part 5: tens C4c4 CONFIRMED
    5: [None, None,   (3, 2)],   # Part 6: tens location unknown
    6: [None, (2, 4), (3, 0)],   # Part 7: ones=C3c0, tens=C2c4 (confirmed, value walk to 10)
    7: [(2, 2), (2, 3), (2, 1)],   # Part 8: hundreds=C2c2, tens=C2c3, ones=C2c1 (confirmed vs photo=127)
}

# BAR-LEVEL decoders: 5-level "thermometer" meter per part. SOLVED from
# free-running bar-meter sweeps. Each part's meter is ONE CGRAM column that
# fills bottom-up: level = number of lit rows in that column. Bottom bar
# lights first, each higher bar adds one more row.
#
# Layout (parts 1-5 in C0 cols c0-c4; parts 7-8 in C7 c0-c1):
#   Part 1 = C0 c0   Part 2 = C0 c1   Part 3 = C0 c2
#   Part 4 = C0 c3   Part 5 = C0 c4   Part 7 = C7 c0   Part 8 = C7 c1
# Parts 7 & 8 confirmed from a dedicated clean sweep (part 7 then 8,
# separated in time): C7c0 swings while C7c1 is flat during the part-7
# window, and vice-versa during part-8 — so C7c0=P7, C7c1=P8, unambiguous.
# Both fill rows 7->2 bottom-up.
#
# Part 6 (LEFT) meter is NOT mapped: an earlier guess of C7c1 turned out to
# be Part 8's column (proven by the isolated sweep above). Part 6's meter
# never got a clean isolated window. Redo: sweep Part 6 alone.
#
# Each entry is (char, [(row, col), ...]) for the level bits, bottom-to-top.
BARGRAPH_LEVEL_MAP = {
    0: (0, [(5, 0), (4, 0), (3, 0), (2, 0), (1, 0)]),   # Part 1 DRUMS  C0 c0
    1: (0, [(5, 1), (4, 1), (3, 1), (2, 1), (1, 1)]),   # Part 2 AC3    C0 c1
    2: (0, [(5, 2), (4, 2), (3, 2), (2, 2), (1, 2)]),   # Part 3 AC2    C0 c2 (row7=baseline, excluded)
    3: (0, [(5, 3), (4, 3), (3, 3), (2, 3), (1, 3)]),   # Part 4 AC1    C0 c3
    4: (0, [(5, 4), (4, 4), (3, 4), (2, 4), (1, 4)]),   # Part 5 BASS   C0 c4 (row7=baseline, excluded)
    5: (6, [(7, 4), (6, 4), (5, 4), (4, 4), (3, 4)]),   # Part 6 LEFT   C6 c4
    6: (7, [(7, 0), (6, 0), (5, 0), (4, 0), (3, 0)]),   # Part 7 R2     C7 c0
    7: (7, [(7, 1), (6, 1), (5, 1), (4, 1), (3, 1)]),   # Part 8 R1     C7 c1
}


# ---------- Chord letter decoder (C5 c0) ----------
#
# The chord root display area lives in C5 c0. Bit patterns for each
# chord letter don't match standard 7-seg letter shapes — this piano
# uses a stylized simplified glyph set. E.g. "C" is a "backwards 7"
# (a+f segments) + a small dash at the foot, but the dash appears to
# be a persistent decoration not toggled with the letter.
#
# Bit patterns below are derived from the chord_root_C..chord_root_B
# campaign. Row mapping assumed same as bargraph (r0=a, r1=b, r2=f,
# r3=g, r4=c, r5=e, r6=d). Numbers below reflect cumulative segment
# sets observed after each chord, minus the presumed always-on
# decoration bits.
CHORD_LETTER_TABLE = {
    frozenset():                    ' ',   # no chord
    frozenset({'a', 'f'}):          'C',
    frozenset({'a', 'c', 'd', 'e', 'f'}):      'D',
    frozenset({'a', 'b', 'f', 'g'}):           'E',
    frozenset({'b', 'f', 'g'}):                'F',
    frozenset({'a', 'c', 'd', 'e', 'f', 'g'}): 'G',
    frozenset({'b', 'c', 'd', 'e', 'f', 'g'}): 'A',
    frozenset({'a', 'b', 'c', 'd', 'f', 'g'}): 'B',
}


def decode_chord_letter(cgram):
    """Return the currently displayed chord root letter, or None if
    the pattern doesn't match a known letter."""
    segs = set()
    for row, seg in BARGRAPH_ROW_TO_SEG.items():
        if (cgram[5 * 8 + row] >> (4 - 0)) & 1:
            segs.add(seg)
    return CHORD_LETTER_TABLE.get(frozenset(segs))


# ---------- Transpose note-name decoder (C6 c3 + sharp at C2:r6:c3) ----------
#
# The TRANSPOSE box shows the target note name as you shift. From a clean
# free-running session sweep, the note LETTER lives in C6 c3 and reuses
# the SAME stylized letter font as the chord root display (CHORD_LETTER_
# TABLE), read with the bargraph row convention. A separate sharp
# indicator lives at C2:r6:c3 and toggles independently (ON for the black
# keys: C#, D#, F#, G#, A#). Six of seven observed glyphs matched the
# chord font exactly; the transpose readout and chord readout share a
# font. Transpose is OFF / shows nothing (or "C"/zero) at no-shift.
TRANSPOSE_SHARP_BIT = (2, 6, 3)   # C2:r6:c3


def decode_transpose_note(cgram):
    """Return the transpose target note name (e.g. 'C', 'F#', 'A') or
    None if nothing is displayed in the transpose note box."""
    segs = set()
    for row, seg in BARGRAPH_ROW_TO_SEG.items():
        if (cgram[6 * 8 + row] >> (4 - 3)) & 1:
            segs.add(seg)
    if not segs:
        return None
    letter = CHORD_LETTER_TABLE.get(frozenset(segs))
    if letter is None or not letter.strip():
        return None
    ch, r, c = TRANSPOSE_SHARP_BIT
    sharp = '#' if (cgram[ch * 8 + r] >> (4 - c)) & 1 else ''
    return letter + sharp


def _decode_digit_segs(segs):
    """Decode a set of lit segments to a digit char. Tries an exact
    DIGIT_TABLE match first; if that fails, retries with segment 'd'
    (the bottom bar) added. Some bargraph digit columns don't wire the
    'd'/bottom segment — e.g. Part 7's ones digit (C3 c0) renders 2,3,5,
    6,8,9 without their bottom bar. Adding 'd' recovers the standard
    glyph without polluting the shared table (which would risk collisions
    with the stylized hundreds glyphs)."""
    segs = frozenset(segs)
    d = DIGIT_TABLE.get(segs)
    if d is not None:
        return d
    if 'd' not in segs:
        d = DIGIT_TABLE.get(segs | {'d'})
        if d is not None:
            return d
    return '?'


def decode_bargraph_number(cgram, part_idx):
    """Return decoded int for the specified bargraph's number, or None
    if nothing decoded (all-blank or contains ?). Partial mappings show
    only the mapped digits."""
    m = BARGRAPH_NUMBER_MAP.get(part_idx)
    if m is None: return None
    digits = []
    for entry in m:
        if entry is None:
            digits.append(' ')
            continue
        char, col = entry
        segs = set()
        for row, seg in BARGRAPH_ROW_TO_SEG.items():
            if (cgram[char * 8 + row] >> (4 - col)) & 1:
                segs.add(seg)
        digits.append(_decode_digit_segs(segs))
    text = ''.join(digits).lstrip()
    if not text or '?' in text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def decode_bargraph_level(cgram, part_idx):
    """Return 0..5 (how many bars lit) for the specified part, or None
    if not mapped."""
    m = BARGRAPH_LEVEL_MAP.get(part_idx)
    if m is None: return None
    char, cells = m
    lit = 0
    for (row, col) in cells:
        if (cgram[char * 8 + row] >> (4 - col)) & 1:
            lit += 1
    return lit


# Semantic names for the 8 bargraph parts, matching the panel labels
# printed below the display on the actual instrument.
PART_NAMES = [
    'DRUMS',
    'AC3',    # ACCOMP 3
    'AC2',    # ACCOMP 2
    'AC1',    # ACCOMP 1
    'BASS',
    'LEFT',
    'R2',     # RIGHT 2
    'R1',     # RIGHT 1
]


# ---------- Shared live state (for UI thread) ----------

class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = HD44780State()
        self.status = 'starting...'
        self.updated = False
        self.event_count = 0
        # Persistent voice/rhythm/mode tracking
        self.persistent_l1 = '            '
        self.persistent_l2 = '            '
        self.current_mode = ''
        # Latch: only re-render committed state (display_on=True). We track
        # the last displayed DDRAM/CGRAM so quick display-off/write/display-on
        # cycles don't visibly churn.
        self.committed_ddram = bytearray(128)
        for i in range(128):
            self.committed_ddram[i] = 0x20
        self.committed_cgram = bytearray(64)


def looks_like_menu_label(text):
    """All-caps letters = menu label. Any lowercase = voice/rhythm name."""
    stripped = text.strip()
    if not stripped: return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters: return False
    return all(c.isupper() for c in letters)


# ---------- Serial reader ----------

def guess_port():
    for p in list(list_ports.comports()):
        n = ((p.device or '') + ' ' + (p.description or '') + ' '
             + (p.manufacturer or '')).upper()
        if 'ACM' in n or 'PICO' in n or 'RP2' in n or 'BOARD CDC' in n:
            return p.device
    ports = list(list_ports.comports())
    return ports[0].device if ports else None


# Line format from v14:
#   t=00123456 W CMD 0x0C [DISP_ON]
#   t=00124200 W DAT 0x43 'C'
#   t=00125000 R STA (byte we drove: 0x00)
#   t=00125090 R DAT (byte we drove: 0x00)
LINE_RE = re.compile(
    r'^t=\d+\s+([WR])\s+(CMD|DAT|STA)(?:\s+0x([0-9A-Fa-f]{2}))?')


def serial_reader(state, port_getter, baud):
    while True:
        port = port_getter()
        if not port:
            with state.lock:
                state.status = 'no serial port — plug in RP2350'
                state.updated = True
            time.sleep(2); continue
        try:
            with state.lock:
                state.status = f'connecting {port}...'
                state.updated = True
            ser = serial.Serial(port, baud, timeout=0.05)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
        except Exception as e:
            with state.lock:
                state.status = f'{port}: {e}'
                state.updated = True
            time.sleep(2); continue

        with state.lock:
            state.status = f'connected {port}'
            state.updated = True

        try:
            while True:
                raw = ser.readline()
                if not raw:
                    # Read timeout with no data — not a disconnect. The piano
                    # is event-driven and silent between button presses; just
                    # keep waiting. (Using ser.readline() instead of the
                    # `for raw in ser` iterator avoids pyserial's internal
                    # line-buffering, which otherwise holds bytes back and
                    # makes button presses feel laggy.)
                    continue
                try:
                    line = raw.decode('utf-8', errors='replace').rstrip()
                except Exception:
                    continue
                if not line: continue
                if line.startswith('#'):
                    if 'ALIVE' in line:
                        with state.lock:
                            state.status = (f'{port} — '
                                            + line.lstrip('# ').strip())
                            state.updated = True
                    continue

                m = LINE_RE.match(line)
                if not m: continue
                direction, kind, hexbyte = m.group(1), m.group(2), m.group(3)

                # Only writes affect state.
                if direction != 'W': continue
                if hexbyte is None: continue
                b = int(hexbyte, 16)

                with state.lock:
                    if kind == 'CMD':
                        was_on = state.state.display_on
                        is_dispctrl = (b & 0xF8) == 0x08
                        state.state.apply_cmd(b)
                        # Commit the visible buffers ONLY on a DISP_CTRL
                        # command (0x08-0x0F) — this is the piano's own
                        # "frame ready, show it now" signal, sent after it
                        # finishes writing a burst of characters/sprites.
                        # Committing here (not on every DAT) means we render
                        # only settled frames, exactly like the real STN glass
                        # whose slow persistence never shows the intermediate
                        # states as a name streams in over the previous one.
                        # (That mid-write flicker — e.g. "Pop GranOL" before
                        # the final "Pop Grand" — was our display commiting
                        # too eagerly, NOT dropped data or a piano quirk.)
                        if is_dispctrl and state.state.display_on:
                            state.committed_ddram[:] = state.state.ddram
                            state.committed_cgram[:] = state.state.cgram
                    elif kind == 'DAT':
                        state.state.apply_data(b)
                        # Do NOT commit here. Data writes stream in one char /
                        # sprite at a time; committing each one would show the
                        # half-written frame (e.g. a new name overwriting the
                        # old one character by character). We commit only on
                        # the piano's DISP_CTRL (0x0C) frame-ready signal
                        # above, so the display shows only settled frames —
                        # matching the real glass, which never flickers mid-
                        # write because of its slow STN persistence.
                    state.event_count += 1

                    # (Removed the persistent-name + menu-label classification
                    # that used to live here. The display now reads the two
                    # text lines straight from committed DDRAM, so there's
                    # nothing to latch or classify — simpler and correct. The
                    # all-caps "menu label" heuristic was also wrong for the
                    # boot splash "SX-PR53" and any all-caps voice name.)

                    state.status = (f'{port} — {state.event_count} events'
                                    f'  ac=0x{state.state.ac:02X}'
                                    f'  {"CG" if state.state.in_cgram else "DD"}'
                                    f'  disp={"on" if state.state.display_on else "OFF"}')
                    state.updated = True
        except Exception as e:
            with state.lock:
                state.status = f'{port} lost: {e}'
                state.updated = True
            try: ser.close()
            except Exception: pass
            time.sleep(2)


# ---------- Rendering ----------

BG_APP    = '#0a1410'
BG_PANEL  = '#0e2e18'
LCD_BG    = '#0d3d1a'
LCD_ON    = '#c8ffb0'
LCD_OFF   = '#124a20'
LCD_GRID  = '#0a2812'
FG_LABEL  = '#8ac48a'
FG_STATUS = '#5f8f5f'
CELL_PX   = 6

# --- Realistic Technics STN glass palette (matches the physical panel) ---
GLASS_FIELD   = '#c7d43f'   # yellow-green backlight field
GLASS_SEG     = '#2b3a12'   # dark lit segment
GLASS_SEG_OFF = '#b3c04a'   # unlit segment (faint on the field)
GLASS_PRINT   = '#5a6a34'   # printed (non-electrode) labels: panel names, box outlines
GLASS_RULE    = '#2f3d17'   # divider lines / box strokes
CHAR_W    = 5 * CELL_PX
CHAR_H    = 8 * CELL_PX
CHAR_GAP  = 4


def draw_char_grid(canvas, x, y, pattern_bytes,
                   on_col=LCD_ON, off_col=LCD_OFF):
    for row in range(8):
        b = pattern_bytes[row] if row < len(pattern_bytes) else 0
        for col in range(5):
            fill = on_col if (b >> (4 - col)) & 1 else off_col
            canvas.create_rectangle(
                x + col * CELL_PX, y + row * CELL_PX,
                x + (col + 1) * CELL_PX, y + (row + 1) * CELL_PX,
                fill=fill, outline='')


# Minimal 5x8 ASCII font (same as before).
def _b(*rows):
    return bytes(sum((1 << (4 - i)) for i, c in enumerate(r) if c == '#')
                 for r in rows) + b'\x00' * (8 - len(rows))

FONT = {}
def _f(ch, *rows): FONT[ch] = _b(*rows)

_f(' ', '.....','.....','.....','.....','.....','.....','.....','.....')
_f('!', '..#..','..#..','..#..','..#..','..#..','.....','..#..','.....')
_f('"', '.#.#.','.#.#.','.....','.....','.....','.....','.....','.....')
_f('#', '.#.#.','#####','.#.#.','#####','.#.#.','.....','.....','.....')
_f('$', '..#..','.####','#.#..','.###.','..#.#','####.','..#..','.....')
_f('%', '##..#','##.#.','..#..','.#.##','#..##','.....','.....','.....')
_f('&', '.##..','#..#.','.##..','#.#.#','#..#.','.##.#','.....','.....')
_f("'", '..#..','..#..','.....','.....','.....','.....','.....','.....')
_f('(', '...#.','..#..','..#..','..#..','..#..','..#..','...#.','.....')
_f(')', '.#...','..#..','..#..','..#..','..#..','..#..','.#...','.....')
_f('*', '.....','..#..','#.#.#','.###.','#.#.#','..#..','.....','.....')
_f('+', '.....','..#..','..#..','#####','..#..','..#..','.....','.....')
_f(',', '.....','.....','.....','.....','..#..','..#..','.#...','.....')
_f('-', '.....','.....','.....','#####','.....','.....','.....','.....')
_f('.', '.....','.....','.....','.....','.....','..#..','..#..','.....')
_f('/', '....#','...#.','..#..','.#...','#....','.....','.....','.....')
_f('0', '.###.','#...#','#..##','#.#.#','##..#','#...#','.###.','.....')
_f('1', '..#..','.##..','..#..','..#..','..#..','..#..','.###.','.....')
_f('2', '.###.','#...#','....#','...#.','..#..','.#...','#####','.....')
_f('3', '#####','...#.','..#..','...#.','....#','#...#','.###.','.....')
_f('4', '...#.','..##.','.#.#.','#..#.','#####','...#.','...#.','.....')
_f('5', '#####','#....','####.','....#','....#','#...#','.###.','.....')
_f('6', '..##.','.#...','#....','####.','#...#','#...#','.###.','.....')
_f('7', '#####','....#','...#.','..#..','.#...','.#...','.#...','.....')
_f('8', '.###.','#...#','#...#','.###.','#...#','#...#','.###.','.....')
_f('9', '.###.','#...#','#...#','.####','....#','...#.','.##..','.....')
_f(':', '.....','..#..','..#..','.....','..#..','..#..','.....','.....')
_f(';', '.....','..#..','..#..','.....','..#..','..#..','.#...','.....')
_f('<', '...#.','..#..','.#...','#....','.#...','..#..','...#.','.....')
_f('=', '.....','.....','#####','.....','#####','.....','.....','.....')
_f('>', '.#...','..#..','...#.','....#','...#.','..#..','.#...','.....')
_f('?', '.###.','#...#','....#','...#.','..#..','.....','..#..','.....')
_f('@', '.###.','#...#','#..##','#.#.#','#..##','#....','.###.','.....')
_f('A', '.###.','#...#','#...#','#####','#...#','#...#','#...#','.....')
_f('B', '####.','#...#','#...#','####.','#...#','#...#','####.','.....')
_f('C', '.###.','#...#','#....','#....','#....','#...#','.###.','.....')
_f('D', '###..','#..#.','#...#','#...#','#...#','#..#.','###..','.....')
_f('E', '#####','#....','#....','###..','#....','#....','#####','.....')
_f('F', '#####','#....','#....','###..','#....','#....','#....','.....')
_f('G', '.###.','#...#','#....','#..##','#...#','#...#','.####','.....')
_f('H', '#...#','#...#','#...#','#####','#...#','#...#','#...#','.....')
_f('I', '.###.','..#..','..#..','..#..','..#..','..#..','.###.','.....')
_f('J', '..###','...#.','...#.','...#.','...#.','#..#.','.##..','.....')
_f('K', '#...#','#..#.','#.#..','##...','#.#..','#..#.','#...#','.....')
_f('L', '#....','#....','#....','#....','#....','#....','#####','.....')
_f('M', '#...#','##.##','#.#.#','#.#.#','#...#','#...#','#...#','.....')
_f('N', '#...#','#...#','##..#','#.#.#','#..##','#...#','#...#','.....')
_f('O', '.###.','#...#','#...#','#...#','#...#','#...#','.###.','.....')
_f('P', '####.','#...#','#...#','####.','#....','#....','#....','.....')
_f('Q', '.###.','#...#','#...#','#...#','#.#.#','#..#.','.##.#','.....')
_f('R', '####.','#...#','#...#','####.','#.#..','#..#.','#...#','.....')
_f('S', '.###.','#...#','#....','.###.','....#','#...#','.###.','.....')
_f('T', '#####','..#..','..#..','..#..','..#..','..#..','..#..','.....')
_f('U', '#...#','#...#','#...#','#...#','#...#','#...#','.###.','.....')
_f('V', '#...#','#...#','#...#','#...#','#...#','.#.#.','..#..','.....')
_f('W', '#...#','#...#','#...#','#.#.#','#.#.#','##.##','#...#','.....')
_f('X', '#...#','#...#','.#.#.','..#..','.#.#.','#...#','#...#','.....')
_f('Y', '#...#','#...#','#...#','.#.#.','..#..','..#..','..#..','.....')
_f('Z', '#####','....#','...#.','..#..','.#...','#....','#####','.....')
_f('[', '.###.','.#...','.#...','.#...','.#...','.#...','.###.','.....')
_f('\\','#....','.#...','..#..','...#.','....#','.....','.....','.....')
_f(']', '.###.','...#.','...#.','...#.','...#.','...#.','.###.','.....')
_f('^', '..#..','.#.#.','#...#','.....','.....','.....','.....','.....')
_f('_', '.....','.....','.....','.....','.....','.....','#####','.....')
_f('`', '.#...','..#..','.....','.....','.....','.....','.....','.....')
_f('a', '.....','.....','.###.','....#','.####','#...#','.####','.....')
_f('b', '#....','#....','####.','#...#','#...#','#...#','####.','.....')
_f('c', '.....','.....','.###.','#....','#....','#...#','.###.','.....')
_f('d', '....#','....#','.####','#...#','#...#','#...#','.####','.....')
_f('e', '.....','.....','.###.','#...#','#####','#....','.###.','.....')
_f('f', '..##.','.#..#','.#...','###..','.#...','.#...','.#...','.....')
_f('g', '.....','.####','#...#','#...#','.####','....#','.###.','.....')
_f('h', '#....','#....','####.','#...#','#...#','#...#','#...#','.....')
_f('i', '..#..','.....','.##..','..#..','..#..','..#..','.###.','.....')
_f('j', '...#.','.....','...#.','...#.','...#.','#..#.','.##..','.....')
_f('k', '#....','#....','#..#.','#.#..','##...','#.#..','#..#.','.....')
_f('l', '.##..','..#..','..#..','..#..','..#..','..#..','.###.','.....')
_f('m', '.....','.....','##.#.','#.#.#','#.#.#','#.#.#','#...#','.....')
_f('n', '.....','.....','####.','#...#','#...#','#...#','#...#','.....')
_f('o', '.....','.....','.###.','#...#','#...#','#...#','.###.','.....')
_f('p', '.....','.....','####.','#...#','####.','#....','#....','.....')
_f('q', '.....','.....','.####','#...#','.####','....#','....#','.....')
_f('r', '.....','.....','#.###','##...','#....','#....','#....','.....')
_f('s', '.....','.....','.####','#....','.###.','....#','####.','.....')
_f('t', '.#...','.#...','###..','.#...','.#...','.#..#','..##.','.....')
_f('u', '.....','.....','#...#','#...#','#...#','#...#','.####','.....')
_f('v', '.....','.....','#...#','#...#','#...#','.#.#.','..#..','.....')
_f('w', '.....','.....','#...#','#...#','#.#.#','#.#.#','.#.#.','.....')
_f('x', '.....','.....','#...#','.#.#.','..#..','.#.#.','#...#','.....')
_f('y', '.....','.....','#...#','#...#','#...#','.####','....#','.###.')
_f('z', '.....','.....','#####','...#.','..#..','.#...','#####','.....')
_f('{', '..##.','..#..','..#..','.##..','..#..','..#..','..##.','.....')
_f('|', '..#..','..#..','..#..','..#..','..#..','..#..','..#..','.....')
_f('}', '.##..','..#..','..#..','..##.','..#..','..#..','.##..','.....')
_f('~', '.##.#','#.##.','.....','.....','.....','.....','.....','.....')

DEFAULT_GLYPH = _b('.###.','#...#','#..##','#.#.#','##..#','#...#','.###.')


def glyph_for(byte, cgram):
    # DDRAM values 0x00-0x07 (and their 0x08-0x0F aliases) are CGRAM
    # references. Rather than render the CGRAM sprite at those positions,
    # show blank so the 16x2 area reads as pure text.
    if byte < 16:
        return FONT[' ']
    ch = chr(byte) if 32 <= byte < 127 else None
    return FONT.get(ch, DEFAULT_GLYPH)


# ---------- App ----------

class App:
    """Realistic reproduction of the SX-PR53 glass.

    A single canvas draws the three physical zones of the panel:
      TOP    tempo readout (left) | chord box (center) | transpose box (right)
      MIDDLE two small 2-digit displays | RIGHT1/RHYTHM labels+icons | 12-char text
      BOTTOM 8 bargraph columns (meter + 3-digit number + down-arrow + panel label)

    Everything is decoded live from the committed CGRAM/DDRAM buffers.
    """

    # Canvas geometry (logical px). Kept in one place so tweaks are easy.
    W = 760
    H = 380
    PAD = 16
    Z_TOP = 112       # bottom y of the top zone
    Z_MID = 224       # bottom y of the middle zone
    # Middle zone gutter: two small 2-digit displays live to the LEFT of the
    # text lines (between the label/icon column and nothing — they sit in the
    # far-left margin above/below on the real glass). We give them a column.
    SMALL_X = 22          # left edge of the small-display gutter
    SMALL_W = 52          # width reserved for a 2-digit display
    LABEL_X = SMALL_X + SMALL_W + 12   # RIGHT1/RHYTHM label column
    ICON_X  = LABEL_X + 70
    TEXT_X  = ICON_X + 44              # 12-char DDRAM text starts here

    def __init__(self, root, state):
        self.state = state
        self.root = root
        root.title("SX-PR53 Live Display")
        root.configure(bg='#111')
        root.resizable(False, False)

        wrap = tk.Frame(root, bg='#111', padx=18, pady=18)
        wrap.pack()

        # The glass itself.
        self.g = tk.Canvas(wrap, width=self.W, height=self.H,
                           bg=GLASS_FIELD, highlightthickness=6,
                           highlightbackground='#1b1b1b')
        self.g.pack()

        # A tiny status strip below the glass (connection / drops).
        self.status = tk.Label(wrap, text='waiting for serial...',
                               bg='#111', fg='#7a7a7a',
                               font=('Courier', 9), anchor='w', justify='left')
        self.status.pack(fill='x', pady=(8, 0))

        self._render()

    # ---- segment-style text helpers ----
    def _seg_text(self, x, y, text, size, *, anchor='w', on=True,
                  bold=True, spacing=0, fill=None):
        if fill is None:
            fill = GLASS_SEG if on else GLASS_SEG_OFF
        f = ('Courier', size, 'bold' if bold else 'normal')
        if spacing and len(text) > 1:
            # manual letter spacing for the seven-seg feel
            cx = x
            for chdr in text:
                self.g.create_text(cx, y, text=chdr, fill=fill,
                                   font=f, anchor=anchor)
                cx += size * 0.72 + spacing
        else:
            self.g.create_text(x, y, text=text, fill=fill, font=f,
                               anchor=anchor)

    def _render(self):
        with self.state.lock:
            ddram = bytes(self.state.committed_ddram)
            cgram = bytes(self.state.committed_cgram)
            status = self.state.status
            dirty = self.state.updated
            self.state.updated = False

        # Only redraw when the committed frame actually changed. The piano
        # commits ~13x/sec, but many commits carry identical content (idle
        # CGRAM-refresh cycles). Hashing the committed buffers lets us skip
        # redundant full redraws — that's what made the bars/numbers appear
        # to "redraw every time" and added load/lag.
        frame_key = (ddram, cgram)
        if dirty and frame_key != getattr(self, '_last_frame', None):
            self._last_frame = frame_key
            self.g.delete('all')
            self._draw_top(cgram)
            self._draw_middle(cgram, ddram)
            self._draw_bottom(cgram)
            self.status.config(text=status)

        self.root.after(33, self._render)

    # ================= TOP ZONE =================
    def _draw_top(self, cgram):
        g = self.g
        # TEMPO label + note + digits
        self._seg_text(self.PAD, 30, 'TEMPO', 12, anchor='w', spacing=2)
        self._seg_text(self.PAD, 74, '\u2669=', 18, anchor='w')
        tempo = decode_tempo(cgram)
        ttxt = f'{tempo}' if tempo is not None else '---'
        self._seg_text(self.PAD + 44, 78, ttxt, 40, anchor='w', spacing=6,
                       on=tempo is not None)

        # Chord box (center)
        bx0, by0, bx1, by1 = 340, 20, 520, 92
        g.create_rectangle(bx0, by0, bx1, by1, outline=GLASS_RULE, width=2)
        chord = decode_chord_letter(cgram)
        if chord and chord.strip():
            self._seg_text((bx0 + bx1) / 2, (by0 + by1) / 2 + 8, chord, 30,
                           anchor='center')
        else:
            self._seg_text((bx0 + bx1) / 2, (by0 + by1) / 2 + 6, '(no chord)',
                           14, anchor='center', on=False, bold=False,
                           fill=GLASS_PRINT)

        # Transpose box (right)
        tx0, ty0, tx1, ty1 = 546, 20, 744, 92
        g.create_rectangle(tx0, ty0, tx1, ty1, outline=GLASS_RULE, width=2)
        self._seg_text((tx0 + tx1) / 2, ty0 + 18, 'TRANSPOSE', 11,
                       anchor='center', spacing=1)
        note = decode_transpose_note(cgram)
        ntxt = note if (note and note.strip()) else '\u2669'
        self._seg_text((tx0 + tx1) / 2 - 12, ty0 + 52, ntxt, 22,
                       anchor='center')
        self._seg_text((tx0 + tx1) / 2 + 34, ty0 + 40, '\u25B2', 12,
                       anchor='center', on=False)
        self._seg_text((tx0 + tx1) / 2 + 34, ty0 + 58, '\u25BC', 12,
                       anchor='center', on=False)

        g.create_line(self.PAD, self.Z_TOP, self.W - self.PAD, self.Z_TOP,
                      fill=GLASS_RULE, width=1)

    # ================= MIDDLE ZONE =================
    def _draw_middle(self, cgram, ddram):
        g = self.g
        y1 = 150   # baseline of text line 1
        y2 = 196   # baseline of text line 2

        # Text lines come STRAIGHT from committed DDRAM (positions 0-11 of
        # each line), gated on the piano's 0x0C commit. No menu-label
        # heuristic, no latched "persistent name" — just what the piano
        # actually committed. This fixes:
        #  - boot splash line 2 ("SX-PR53") not showing (it was wrongly
        #    classified as an all-caps "menu label" and suppressed)
        #  - stale/leftover text (the persistent-name latch could hold an
        #    old value; committed DDRAM always reflects the current frame)
        l1 = ''.join(chr(x) if 32 <= x < 127 else ' ' for x in ddram[0:12])
        l2 = ''.join(chr(x) if 32 <= x < 127 else ' '
                     for x in ddram[0x40:0x40 + 12])

        # --- Two small 2-digit displays in the left gutter ---
        # (top one aligns with line 1, bottom with line 2). Decoder not yet
        # mapped in this build, so they show '--' until decode_small_display
        # exists. The gutter box makes their position explicit.
        for (sy, tag) in ((y1, 'top'), (y2, 'bot')):
            g.create_rectangle(self.SMALL_X, sy - 22,
                               self.SMALL_X + self.SMALL_W, sy + 6,
                               outline=GLASS_RULE, width=1)
            val = self._small_display(cgram, tag)
            self._seg_text(self.SMALL_X + self.SMALL_W / 2, sy - 6,
                           val, 18, anchor='center',
                           on=val != '--')

        # --- RIGHT1 / RHYTHM labels + icons ---
        self._seg_text(self.LABEL_X, y1 - 6, 'RIGHT 1', 12, anchor='w',
                       spacing=1)
        # keyboard icon
        kx, ky = self.ICON_X, y1 - 20
        g.create_rectangle(kx, ky, kx + 34, ky + 20, outline=GLASS_RULE,
                           width=1.5)
        for i in range(1, 5):
            g.create_line(kx + i * 7, ky, kx + i * 7, ky + 20,
                          fill=GLASS_RULE, width=1)

        self._seg_text(self.LABEL_X, y2 - 6, 'RHYTHM', 12, anchor='w',
                       spacing=1)
        # drummer icon (simple)
        dx, dy = self.ICON_X + 17, y2 - 10
        g.create_oval(dx - 11, dy - 11, dx + 11, dy + 11, outline=GLASS_RULE,
                      width=1.5)
        g.create_oval(dx - 3, dy - 3, dx + 3, dy + 3, fill=GLASS_SEG,
                      outline='')

        # --- 12-char DDRAM text (voice line 1, rhythm line 2) ---
        # rstrip() only for display (drop trailing pad spaces); the committed
        # buffer already has the correct settled content thanks to 0x0C gating.
        self._seg_text(self.TEXT_X, y1 - 4, l1.rstrip()[:12], 26,
                       anchor='w', spacing=3, on=bool(l1.strip()))
        self._seg_text(self.TEXT_X, y2 - 4, l2.rstrip()[:12], 26,
                       anchor='w', spacing=3, on=bool(l2.strip()))

        g.create_line(self.PAD, self.Z_MID, self.W - self.PAD, self.Z_MID,
                      fill=GLASS_RULE, width=1)
        # dashed rule under the numbers row (like the real panel)
        g.create_line(self.SMALL_X, self.Z_MID + 24, self.W - self.PAD,
                      self.Z_MID + 24, fill=GLASS_RULE, width=1,
                      dash=(3, 4))

    def _small_display(self, cgram, which):
        """Two small 2-digit 7-seg displays (program/part numbers).
        Not yet mapped in this build — returns '--'. When a decoder is
        added, wire it here so the glass shows the live value."""
        fn = globals().get('decode_small_display')
        if fn is not None:
            try:
                v = fn(cgram, which)
                if v is not None:
                    return f'{v:>2}'
            except Exception:
                pass
        return '--'

    # ================= BOTTOM ZONE =================
    def _draw_bottom(self, cgram):
        g = self.g
        n = 8
        left = self.SMALL_X
        right = self.W - self.PAD
        span = right - left
        col_w = span / n
        meter_bars = 6
        for part in range(n):
            cx = left + col_w * (part + 0.5)
            # ---- meter (thermometer, bottom-up) ----
            level = decode_bargraph_level(cgram, part)
            bw, bh, gap = 32, 5, 2.5
            top = self.Z_MID + 12
            for i in range(meter_bars):
                y = top + (meter_bars - 1 - i) * (bh + gap)
                lit = (level is not None and i < level)
                g.create_rectangle(cx - bw / 2, y, cx + bw / 2, y + bh,
                                   fill=GLASS_SEG if lit else '',
                                   outline=GLASS_SEG if lit else GLASS_SEG_OFF,
                                   width=1)
            # ---- 3-digit number ----
            num = decode_bargraph_number(cgram, part)
            if num is not None:
                ntxt, on = f'{num:>3}', True
            elif BARGRAPH_NUMBER_MAP.get(part) is None:
                ntxt, on = '---', False
            else:
                ntxt, on = '???', False
            self._seg_text(cx, top + meter_bars * (bh + gap) + 18, ntxt, 22,
                           anchor='center', spacing=2, on=on)
            # ---- down arrow ----
            self._seg_text(cx, top + meter_bars * (bh + gap) + 40, '\u25BC',
                           14, anchor='center')
            # ---- printed panel label (not an electrode) ----
            self._seg_text(cx, self.H - 14, PART_NAMES[part], 11,
                           anchor='center', bold=False, fill=GLASS_PRINT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='Serial port (default: auto-detect)')
    p.add_argument('--baud', type=int, default=115200)
    args = p.parse_args()

    state = LiveState()
    def port_getter(): return args.port or guess_port()
    reader = threading.Thread(target=serial_reader,
                              args=(state, port_getter, args.baud),
                              daemon=True)
    reader.start()

    root = tk.Tk()
    App(root, state)
    root.mainloop()


if __name__ == '__main__':
    main()
