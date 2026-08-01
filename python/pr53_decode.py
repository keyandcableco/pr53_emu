#!/usr/bin/env python3
"""
pr53_decode.py — Live tempo/numeric readout decoder for SX-PR53.

Reads v15 event log over USB serial, mirrors CGRAM state via HD44780
state machine, and decodes the tempo digits directly from the derived
segment mapping. No teaching/lookup phase — pure decode.

Assumes tempo lives in CGRAM char C1, columns c0 (hundreds), c1 (tens),
c2 (ones), with the row-to-segment mapping worked out empirically from
the 20-step tempo campaign:

    Row 0 → segment a (top)
    Row 1 → segment b (top-right)
    Row 2 → segment f (top-left)     ← unusual placement but consistent
    Row 3 → segment g (middle)
    Row 4 → segment c (bottom-right)
    Row 5 → segment e (bottom-left)
    Row 6 → unused
    Row 7 → segment d (bottom)

Digit patterns match this piano's 7-seg glyphs (note: "7" is drawn with
segment f — a European-style 7 with a tail).

If the tens or hundreds digit decodes as '?' consistently, that means
they DON'T use the same convention as ones — run the tempo_step campaign
inside a decade (say 40→50) to check, and let me know so we can revise.

Dependencies: pyserial. tkinter is stdlib.
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


# ============================================================
# SEGMENT MAPPING (from empirical campaign analysis)
# ============================================================

# Row → segment letter within one digit's column of CGRAM char C1
ROW_TO_SEG = {
    0: 'a',
    1: 'b',
    2: 'f',
    3: 'g',
    4: 'c',
    5: 'e',
    # row 6 unused
    7: 'd',
}

# Digit patterns as observed on THIS piano's display font.
# Note '7' includes segment f — the piano draws 7 with a small tail.
DIGIT_TABLE = {
    frozenset(): ' ',                # blank digit
    frozenset('abcdef'):  '0',
    frozenset('bc'):      '1',
    frozenset('bf'):      '1',       # hundreds-digit "1" glyph (stylized)
    frozenset('abdeg'):   '2',
    frozenset('abg'):     '2',       # hundreds-digit "2" glyph (stylized)
    frozenset('abcdg'):   '3',
    frozenset('bcfg'):    '4',
    frozenset('acdfg'):   '5',
    frozenset('acdefg'):  '6',
    frozenset('abcf'):    '7',       # European "7" with tail
    frozenset('abcdefg'): '8',
    frozenset('abcdfg'):  '9',
}

# Which CGRAM (char, col) triples make up the tempo display, left to right.
TEMPO_DIGITS = [(1, 0), (1, 1), (1, 2)]  # (char, col) — hundreds, tens, ones


def decode_digit(cgram, char_idx, col):
    """Return (digit_char, segments_set) for one digit position."""
    segs = set()
    for row, seg in ROW_TO_SEG.items():
        byte = cgram[char_idx * 8 + row]
        if (byte >> (4 - col)) & 1:
            segs.add(seg)
    key = frozenset(segs)
    return DIGIT_TABLE.get(key, '?'), segs


def decode_tempo(cgram):
    """Return (tempo_int_or_None, digits_string, per_digit_segments)."""
    per_digit = []
    chars = []
    for ch, col in TEMPO_DIGITS:
        d, segs = decode_digit(cgram, ch, col)
        chars.append(d)
        per_digit.append(segs)
    text = ''.join(chars)
    stripped = text.lstrip()
    try:
        tempo = int(stripped)
    except ValueError:
        tempo = None
    return tempo, text, per_digit


# ============================================================
# HD44780 state machine (shared with pr53_display.py)
# ============================================================

class HD44780State:
    def __init__(self):
        self.ddram = bytearray(128)
        for i in range(128): self.ddram[i] = 0x20
        self.cgram = bytearray(64)
        self.ac = 0
        self.in_cgram = False
        self.entry_inc = True
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
            self.display_on = (b & 0x04) != 0
        elif (b & 0xC0) == 0x40:
            self.ac = b & 0x3F; self.in_cgram = True
        elif b & 0x80:
            self.ac = b & 0x7F; self.in_cgram = False

    def apply_data(self, b):
        step = 1 if self.entry_inc else -1
        if self.in_cgram:
            if self.ac < 64: self.cgram[self.ac] = b & 0x1F
            self.ac = (self.ac + step) & 0x3F
        else:
            if self.ac < 128: self.ddram[self.ac] = b
            self.ac = (self.ac + step) & 0x7F


class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = HD44780State()
        self.status = 'starting...'
        self.updated = False
        self.event_count = 0


LINE_RE = re.compile(
    r'^t=\d+\s+([WR])\s+(CMD|DAT|STA)(?:\s+0x([0-9A-Fa-f]{2}))?')


def guess_port():
    for p in list(list_ports.comports()):
        n = ((p.device or '') + ' ' + (p.description or '') + ' '
             + (p.manufacturer or '')).upper()
        if 'ACM' in n or 'PICO' in n or 'RP2' in n or 'BOARD CDC' in n:
            return p.device
    ports = list(list_ports.comports())
    return ports[0].device if ports else None


def serial_reader(state, port_getter, baud):
    while True:
        port = port_getter()
        if not port:
            with state.lock:
                state.status = 'no serial port'; state.updated = True
            time.sleep(2); continue
        try:
            with state.lock:
                state.status = f'connecting {port}...'; state.updated = True
            ser = serial.Serial(port, baud, timeout=1)
        except Exception as e:
            with state.lock:
                state.status = f'{port}: {e}'; state.updated = True
            time.sleep(2); continue
        with state.lock:
            state.status = f'connected {port}'; state.updated = True
        try:
            for raw in ser:
                try: line = raw.decode('utf-8', errors='replace').rstrip()
                except Exception: continue
                if not line or line.startswith('#'): continue
                m = LINE_RE.match(line)
                if not m: continue
                direction, kind, hexbyte = m.group(1), m.group(2), m.group(3)
                if direction != 'W' or hexbyte is None: continue
                b = int(hexbyte, 16)
                with state.lock:
                    if kind == 'CMD':   state.state.apply_cmd(b)
                    elif kind == 'DAT': state.state.apply_data(b)
                    state.event_count += 1
                    state.status = (f'{port} — {state.event_count} events'
                                    f'  disp={"on" if state.state.display_on else "OFF"}')
                    state.updated = True
        except Exception as e:
            with state.lock:
                state.status = f'{port} lost: {e}'; state.updated = True
            try: ser.close()
            except Exception: pass
            time.sleep(2)


# ============================================================
# UI
# ============================================================

BG_APP     = '#0a1410'
BG_PANEL   = '#0e2e18'
SEG_ON     = '#c8ffb0'
SEG_OFF    = '#1a3020'
FG_LABEL   = '#8ac48a'
FG_STATUS  = '#5f8f5f'
FG_BIG     = '#c8ffb0'
FG_UNCERT  = '#ffcc55'


def draw_seven_seg(canvas, x, y, w, h, on_segs, on_color=SEG_ON, off_color=SEG_OFF):
    """Draw one 7-seg digit at (x, y) with bounding box (w, h)."""
    t = max(4, h // 10)         # segment thickness
    g = max(1, t // 3)          # gap between segments
    mid_y = y + h // 2
    def col(seg): return on_color if seg in on_segs else off_color

    # a: top horizontal
    canvas.create_polygon(
        x + t + g, y,
        x + w - t - g, y,
        x + w - t - g - t/2, y + t,
        x + t + g + t/2, y + t,
        fill=col('a'), outline='')

    # d: bottom horizontal
    canvas.create_polygon(
        x + t + g + t/2, y + h - t,
        x + w - t - g - t/2, y + h - t,
        x + w - t - g, y + h,
        x + t + g, y + h,
        fill=col('d'), outline='')

    # g: middle horizontal
    canvas.create_polygon(
        x + t + g, mid_y,
        x + t + g + t/2, mid_y - t/2,
        x + w - t - g - t/2, mid_y - t/2,
        x + w - t - g, mid_y,
        x + w - t - g - t/2, mid_y + t/2,
        x + t + g + t/2, mid_y + t/2,
        fill=col('g'), outline='')

    # f: top-left vertical
    canvas.create_polygon(
        x, y + t + g,
        x + t, y + t + g + t/2,
        x + t, mid_y - t/2,
        x, mid_y - g,
        fill=col('f'), outline='')

    # b: top-right vertical
    canvas.create_polygon(
        x + w, y + t + g,
        x + w, mid_y - g,
        x + w - t, mid_y - t/2,
        x + w - t, y + t + g + t/2,
        fill=col('b'), outline='')

    # e: bottom-left vertical
    canvas.create_polygon(
        x, mid_y + g,
        x + t, mid_y + t/2,
        x + t, y + h - t - g - t/2,
        x, y + h - t - g,
        fill=col('e'), outline='')

    # c: bottom-right vertical
    canvas.create_polygon(
        x + w, mid_y + g,
        x + w, y + h - t - g,
        x + w - t, y + h - t - g - t/2,
        x + w - t, mid_y + t/2,
        fill=col('c'), outline='')


class App:
    def __init__(self, root, state):
        self.state = state
        self.root = root
        root.title("SX-PR53 Live Tempo Decode")
        root.configure(bg=BG_APP)
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG_APP, padx=32, pady=28)
        wrap.pack()

        # ---- Header ----
        tk.Label(wrap, text='TEMPO', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 14, 'bold')).pack(anchor='w')

        # ---- Big 7-seg-styled digit display ----
        # Sized for readability from across the room
        digit_w = 60
        digit_h = 110
        digit_gap = 16
        total_w = 3 * digit_w + 2 * digit_gap + 40
        total_h = digit_h + 20
        self.seg_canvas = tk.Canvas(wrap, width=total_w, height=total_h,
                                    bg=BG_PANEL, highlightthickness=1,
                                    highlightbackground='#0a2812')
        self.seg_canvas.pack(pady=(8, 6))
        self.digit_w = digit_w
        self.digit_h = digit_h
        self.digit_gap = digit_gap

        # ---- Decoded value as text ----
        self.decoded_lbl = tk.Label(
            wrap, text='---', bg=BG_APP, fg=FG_BIG,
            font=('Courier', 42, 'bold'))
        self.decoded_lbl.pack(pady=(2, 0))
        self.decoded_sub = tk.Label(
            wrap, text='(waiting for data)', bg=BG_APP, fg=FG_STATUS,
            font=('Helvetica', 10))
        self.decoded_sub.pack()

        # ---- Debug: per-digit segment identity ----
        tk.Label(wrap, text='Decoded segments per digit',
                 bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(18, 0))
        self.debug_frame = tk.Frame(wrap, bg=BG_PANEL, padx=12, pady=8)
        self.debug_frame.pack(fill='x', pady=(4, 4))
        self.debug_labels = []
        for i, name in enumerate(('hundreds (C1 c0)', 'tens (C1 c1)', 'ones (C1 c2)')):
            row = tk.Frame(self.debug_frame, bg=BG_PANEL)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=name + ':', bg=BG_PANEL, fg=FG_STATUS,
                     font=('Courier', 10), width=18, anchor='e').pack(side='left')
            lab = tk.Label(row, text='—', bg=BG_PANEL, fg=SEG_ON,
                           font=('Courier', 12, 'bold'), anchor='w')
            lab.pack(side='left')
            self.debug_labels.append(lab)

        # ---- Status ----
        self.status = tk.Label(wrap, text='ready', bg=BG_APP, fg=FG_STATUS,
                               font=('Courier', 9), anchor='w')
        self.status.pack(fill='x', pady=(14, 0))

        self._draw_digits(['?', '?', '?'], [set(), set(), set()])
        self._render()

    def _draw_digits(self, chars, per_segs):
        self.seg_canvas.delete('all')
        for i, (ch, segs) in enumerate(zip(chars, per_segs)):
            x = 20 + i * (self.digit_w + self.digit_gap)
            y = 10
            # Draw as-is; if the digit didn't decode (ch=='?'), still draw
            # the raw segments that ARE set, in yellow to flag uncertainty.
            color = SEG_ON if ch != '?' else FG_UNCERT
            draw_seven_seg(self.seg_canvas, x, y, self.digit_w,
                           self.digit_h, segs, on_color=color)

    def _render(self):
        with self.state.lock:
            cgram = bytes(self.state.state.cgram)
            status = self.state.status
            dirty = self.state.updated
            self.state.updated = False

        if dirty:
            tempo, digits_str, per_segs = decode_tempo(cgram)
            chars = list(digits_str)
            self._draw_digits(chars, per_segs)

            if tempo is not None:
                self.decoded_lbl.config(text=str(tempo), fg=FG_BIG)
                self.decoded_sub.config(text=f'BPM  (raw: "{digits_str}")')
            elif digits_str.strip() == '':
                self.decoded_lbl.config(text='---', fg=FG_STATUS)
                self.decoded_sub.config(text='no digits lit')
            else:
                # Some digits decoded as '?' — likely tens/hundreds using
                # a different convention than the ones digit.
                self.decoded_lbl.config(text=digits_str, fg=FG_UNCERT)
                self.decoded_sub.config(
                    text='? = digit pattern not recognized '
                         '(may need to run tempo_step_from_current '
                         'inside a decade)')

            for i, segs in enumerate(per_segs):
                if segs:
                    sorted_segs = ''.join(sorted(segs))
                    ch = chars[i]
                    self.debug_labels[i].config(
                        text=f'{sorted_segs}  →  "{ch}"',
                        fg=SEG_ON if ch != '?' else FG_UNCERT)
                else:
                    self.debug_labels[i].config(text='(blank)', fg=FG_STATUS)

            self.status.config(text=status)

        self.root.after(50, self._render)


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
