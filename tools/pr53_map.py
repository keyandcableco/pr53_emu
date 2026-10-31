#!/usr/bin/env python3
"""
pr53_map.py — Interactive segment-mapping tool for SX-PR53.

Live serial reader + LCD mock + two-snapshot diff view. Workflow:

    1. Piano is in a stable state (say, TEMPO=155). Click "Snapshot A".
    2. Press ONE piano button (say, TEMPO UP). Wait for display to settle.
    3. Click "Snapshot B".
    4. Diff auto-appears at the bottom: only the bits that changed.
    5. Type a label (say "TEMPO_D1_change_155_to_156") and click Save.
       Appends to mapping.csv.

Save mapping button records each bit that flipped, with the label you provided,
timestamp, and A/B context. Then you can iteratively map the display.

Dependencies: pyserial (pip install pyserial). tkinter is stdlib.

Usage:
    python3 pr53_map.py              # auto-detect port
    python3 pr53_map.py --port /dev/ttyACM0
    python3 pr53_map.py --mapping my_mapping.csv
"""
import argparse
import csv
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Need pyserial. Install with:  pip install pyserial")
    sys.exit(1)


# ---------- Shared state ----------

class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.ddram = bytearray(128)
        for i in range(128):
            self.ddram[i] = 0x20
        self.cgram = bytearray(64)
        self.ac = 0
        self.ms = 0
        self.status = 'starting...'
        self.updated = False


# ---------- Serial reader ----------

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
                state.status = 'no serial port — plug in RP2350'
                state.updated = True
            time.sleep(2); continue
        try:
            with state.lock:
                state.status = f'connecting {port}...'
                state.updated = True
            ser = serial.Serial(port, baud, timeout=1)
        except Exception as e:
            with state.lock:
                state.status = f'{port}: {e}'
                state.updated = True
            time.sleep(2); continue
        with state.lock:
            state.status = f'connected {port}'
            state.updated = True
        try:
            for raw in ser:
                try:
                    line = raw.decode('utf-8', errors='replace').strip()
                except Exception:
                    continue
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) != 5:
                    continue
                try:
                    ms = int(parts[0]); ac = int(parts[1], 16)
                    cgram = bytes.fromhex(parts[3])
                    ddram = bytes.fromhex(parts[4])
                    if len(cgram) != 64 or len(ddram) != 128:
                        continue
                except (ValueError, IndexError):
                    continue
                with state.lock:
                    state.ddram = bytearray(ddram)
                    state.cgram = bytearray(cgram)
                    state.ac = ac; state.ms = ms
                    state.status = f'{port} — live  ms={ms}  ac=0x{ac:02X}'
                    state.updated = True
        except Exception as e:
            with state.lock:
                state.status = f'{port} lost: {e}'
                state.updated = True
            try: ser.close()
            except Exception: pass
            time.sleep(2)


# ---------- Palette + geometry ----------

BG_APP    = '#0a1410'
BG_PANEL  = '#0e2e18'
LCD_BG    = '#0d3d1a'
LCD_ON    = '#c8ffb0'
LCD_OFF   = '#124a20'
LCD_GRID  = '#0a2812'
FG_LABEL  = '#8ac48a'
FG_STATUS = '#5f8f5f'
DIFF_A    = '#ff7676'   # bits only in A (that turned OFF going A→B)
DIFF_B    = '#77e0ff'   # bits only in B (that turned ON going A→B)

CELL_PX   = 5
CHAR_W    = 5 * CELL_PX
CHAR_H    = 8 * CELL_PX
CHAR_GAP  = 3


def draw_char_grid(canvas, x, y, pattern_bytes, on_col=LCD_ON, off_col=LCD_OFF,
                   cell=CELL_PX):
    for row in range(8):
        b = pattern_bytes[row] if row < len(pattern_bytes) else 0
        for col in range(5):
            fill = on_col if (b >> (4 - col)) & 1 else off_col
            canvas.create_rectangle(
                x + col * cell, y + row * cell,
                x + (col + 1) * cell, y + (row + 1) * cell,
                fill=fill, outline='')


# Minimal ASCII font (same as pr53_display.py, condensed).
def _b(*rows):
    return bytes(sum((1 << (4 - i)) for i, c in enumerate(r) if c == '#')
                 for r in rows) + b'\x00' * (8 - len(rows))

FONT = {}
def _f(ch, *rows): FONT[ch] = _b(*rows)

_f(' ', '.....','.....','.....','.....','.....','.....','.....','.....')
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
_f('.', '.....','.....','.....','.....','.....','..#..','..#..','.....')
_f(',', '.....','.....','.....','.....','..#..','..#..','.#...','.....')
_f('-', '.....','.....','.....','#####','.....','.....','.....','.....')
_f('/', '....#','...#.','..#..','.#...','#....','.....','.....','.....')
_f('&', '.##..','#..#.','.##..','#.#.#','#..#.','.##.#','.....','.....')
_f('#', '.#.#.','#####','.#.#.','#####','.#.#.','.....','.....','.....')

DEFAULT_GLYPH = _b('.###.','#...#','#..##','#.#.#','##..#','#...#','.###.')

def glyph_for(byte, cgram):
    if byte < 8: return cgram[byte * 8:(byte + 1) * 8]
    if byte < 16: return cgram[(byte - 8) * 8:(byte - 8 + 1) * 8]
    ch = chr(byte) if 32 <= byte < 127 else None
    return FONT.get(ch, DEFAULT_GLYPH)


# ---------- Bit-diff helpers ----------

def bits_set(cgram):
    return sum(bin(b & 0x1F).count('1') for b in cgram)

def diff_bits(a, b):
    """Return two 64-byte arrays: bits_off_going_a_to_b, bits_on_going_a_to_b."""
    off = bytes((x & ~y) & 0x1F for x, y in zip(a, b))
    on  = bytes((~x & y) & 0x1F for x, y in zip(a, b))
    return off, on

def enumerate_bits(mask64):
    """Yield (char, row, col) for each set bit in a 64-byte mask."""
    for pos, byte in enumerate(mask64):
        if not byte: continue
        ch, row = pos // 8, pos % 8
        for col in range(5):
            if (byte >> (4 - col)) & 1:
                yield ch, row, col

def bit_label(ch, row, col):
    return f'C{ch}:r{row}:c{col}'


# ---------- App ----------

class App:
    def __init__(self, root, state, mapping_path):
        self.state = state
        self.mapping_path = mapping_path
        self.snap_a = None    # (ms, ddram, cgram) or None
        self.snap_b = None
        self.root = root
        root.title("SX-PR53 Segment Mapper")
        root.configure(bg=BG_APP)
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG_APP, padx=20, pady=20)
        wrap.pack()

        # --- Live LCD ---
        tk.Label(wrap, text='Live LCD',
                 bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 11, 'bold')).pack(anchor='w')
        lcd_w = 16 * CHAR_W + 15 * CHAR_GAP + 20
        lcd_h = 2 * CHAR_H + CHAR_GAP + 20
        self.lcd = tk.Canvas(wrap, width=lcd_w, height=lcd_h, bg=LCD_BG,
                             highlightthickness=2, highlightbackground='#000')
        self.lcd.pack(pady=(4, 14))

        # --- Snapshot controls ---
        ctl = tk.Frame(wrap, bg=BG_APP)
        ctl.pack(fill='x', pady=(0, 10))
        self.snap_a_btn = tk.Button(ctl, text='Snapshot A',
                                    command=self._on_snap_a,
                                    bg='#2a4a2a', fg='#ddd',
                                    activebackground='#3a5a3a', activeforeground='#fff',
                                    font=('Helvetica', 12, 'bold'), width=14)
        self.snap_a_btn.pack(side='left', padx=(0, 8))
        self.snap_b_btn = tk.Button(ctl, text='Snapshot B',
                                    command=self._on_snap_b,
                                    bg='#2a4a2a', fg='#ddd',
                                    activebackground='#3a5a3a', activeforeground='#fff',
                                    font=('Helvetica', 12, 'bold'), width=14)
        self.snap_b_btn.pack(side='left', padx=(0, 8))
        self.clear_btn = tk.Button(ctl, text='Clear',
                                   command=self._on_clear,
                                   bg='#4a2a2a', fg='#ddd',
                                   activebackground='#5a3a3a',
                                   font=('Helvetica', 11), width=8)
        self.clear_btn.pack(side='left')
        self.a_state = tk.Label(ctl, text='A: not captured', bg=BG_APP,
                                fg=FG_STATUS, font=('Courier', 10))
        self.a_state.pack(side='left', padx=(20, 0))
        self.b_state = tk.Label(ctl, text='B: not captured', bg=BG_APP,
                                fg=FG_STATUS, font=('Courier', 10))
        self.b_state.pack(side='left', padx=(12, 0))

        # --- Diff panel ---
        tk.Label(wrap, text='Diff (A → B)', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 11, 'bold')).pack(anchor='w', pady=(6, 0))
        self.diff_summary = tk.Label(
            wrap, text='(capture A and B to see diff)',
            bg=BG_APP, fg=FG_STATUS, font=('Courier', 10),
            anchor='w', justify='left', wraplength=lcd_w)
        self.diff_summary.pack(fill='x', pady=(4, 6))
        # Diff canvas shows 8 CGRAM chars, tinted with off/on colors
        cg_gap = 12
        cg_w = 8 * CHAR_W + 7 * cg_gap + 20
        cg_h = CHAR_H + 24
        self.diff_canvas = tk.Canvas(wrap, width=cg_w, height=cg_h,
                                     bg=BG_PANEL, highlightthickness=1,
                                     highlightbackground='#0a2812')
        self.diff_canvas.pack(pady=(0, 12))

        # Legend
        legend = tk.Frame(wrap, bg=BG_APP)
        legend.pack(anchor='w', pady=(0, 12))
        tk.Label(legend, text='  ', bg=DIFF_B).pack(side='left')
        tk.Label(legend, text=' turned ON going A→B    ',
                 bg=BG_APP, fg=FG_STATUS, font=('Helvetica', 9)).pack(side='left')
        tk.Label(legend, text='  ', bg=DIFF_A).pack(side='left')
        tk.Label(legend, text=' turned OFF going A→B    ',
                 bg=BG_APP, fg=FG_STATUS, font=('Helvetica', 9)).pack(side='left')
        tk.Label(legend, text='  ', bg=LCD_ON).pack(side='left')
        tk.Label(legend, text=' unchanged (was on in both)',
                 bg=BG_APP, fg=FG_STATUS, font=('Helvetica', 9)).pack(side='left')

        # --- Label + Save ---
        save_row = tk.Frame(wrap, bg=BG_APP)
        save_row.pack(fill='x')
        tk.Label(save_row, text='Label:', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(side='left')
        self.label_entry = tk.Entry(save_row, width=40,
                                    bg='#122', fg='#dfd',
                                    insertbackground='#dfd',
                                    font=('Courier', 11))
        self.label_entry.pack(side='left', padx=(8, 8), fill='x', expand=True)
        self.save_btn = tk.Button(save_row, text='Save diff → mapping.csv',
                                  command=self._on_save,
                                  bg='#3a5a3a', fg='#fff',
                                  activebackground='#4a6a4a',
                                  font=('Helvetica', 11, 'bold'))
        self.save_btn.pack(side='right')

        self.status = tk.Label(wrap, text='ready', bg=BG_APP, fg=FG_STATUS,
                               font=('Courier', 10), anchor='w', justify='left')
        self.status.pack(fill='x', pady=(10, 0))

        self._render()

    # ----- Snapshot capture -----

    def _current(self):
        with self.state.lock:
            return (self.state.ms, bytes(self.state.ddram),
                    bytes(self.state.cgram))

    def _on_snap_a(self):
        self.snap_a = self._current()
        self._update_snap_labels()
        self._update_diff()

    def _on_snap_b(self):
        self.snap_b = self._current()
        self._update_snap_labels()
        self._update_diff()

    def _on_clear(self):
        self.snap_a = None
        self.snap_b = None
        self._update_snap_labels()
        self._update_diff()

    def _update_snap_labels(self):
        def brief(snap, tag):
            if snap is None:
                return f'{tag}: not captured'
            ms, ddram, cgram = snap
            l1 = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ddram[0:12])
            l2 = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ddram[0x40:0x40+12])
            return f'{tag}: ms={ms}  L1="{l1}"  L2="{l2}"  ({bits_set(cgram)}b)'
        self.a_state.config(text=brief(self.snap_a, 'A'))
        self.b_state.config(text=brief(self.snap_b, 'B'))

    # ----- Diff rendering -----

    def _update_diff(self):
        self.diff_canvas.delete('all')
        if self.snap_a is None or self.snap_b is None:
            self.diff_summary.config(text='(capture A and B to see diff)',
                                     fg=FG_STATUS)
            return
        _, _, cga = self.snap_a
        _, _, cgb = self.snap_b
        off_mask, on_mask = diff_bits(cga, cgb)
        off_count = bits_set(off_mask)
        on_count = bits_set(on_mask)
        # Summary text
        parts = [f'{on_count} bit(s) turned ON, {off_count} bit(s) turned OFF']
        if on_count + off_count == 0:
            parts.append('  (no CGRAM changes)')
        else:
            # List them
            on_list = [bit_label(*b) for b in enumerate_bits(on_mask)]
            off_list = [bit_label(*b) for b in enumerate_bits(off_mask)]
            if on_list:
                parts.append('  ON : ' + ' '.join(on_list))
            if off_list:
                parts.append('  OFF: ' + ' '.join(off_list))
        self.diff_summary.config(text='\n'.join(parts), fg=FG_LABEL)

        # Canvas: 8 CGRAM chars. For each pixel:
        #   was ON in A only (turned off) → red
        #   was ON in B only (turned on)  → blue
        #   was ON in both → green (unchanged-on)
        #   was OFF in both → dark
        cg_gap = 12
        for ch in range(8):
            x = 10 + ch * (CHAR_W + cg_gap); y = 12
            self.diff_canvas.create_text(x + CHAR_W // 2, y - 2, text=str(ch),
                                         fill=FG_LABEL, font=('Helvetica', 8),
                                         anchor='s')
            for row in range(8):
                a_byte = cga[ch * 8 + row]
                b_byte = cgb[ch * 8 + row]
                for col in range(5):
                    a_on = (a_byte >> (4 - col)) & 1
                    b_on = (b_byte >> (4 - col)) & 1
                    if a_on and not b_on:   fill = DIFF_A
                    elif b_on and not a_on: fill = DIFF_B
                    elif a_on and b_on:     fill = LCD_ON
                    else:                   fill = LCD_OFF
                    self.diff_canvas.create_rectangle(
                        x + col * CELL_PX, y + row * CELL_PX,
                        x + (col + 1) * CELL_PX, y + (row + 1) * CELL_PX,
                        fill=fill, outline='')

    # ----- Save mapping -----

    def _on_save(self):
        label = self.label_entry.get().strip()
        if self.snap_a is None or self.snap_b is None:
            self.status.config(text='no A/B captured — nothing to save',
                               fg='#c66')
            return
        if not label:
            self.status.config(text='enter a Label first', fg='#c66')
            return
        ma, dda, cga = self.snap_a
        mb, ddb, cgb = self.snap_b
        off_mask, on_mask = diff_bits(cga, cgb)
        if bits_set(off_mask) + bits_set(on_mask) == 0:
            self.status.config(text='no bits changed — nothing to save',
                               fg='#c66')
            return
        l1a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in dda[0:12])
        l2a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in dda[0x40:0x40+12])
        l1b = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ddb[0:12])
        l2b = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ddb[0x40:0x40+12])
        rows_to_write = []
        for (ch, r, c) in enumerate_bits(on_mask):
            rows_to_write.append({
                'bit': bit_label(ch, r, c), 'direction': 'ON',
                'label': label, 'A_l1': l1a, 'A_l2': l2a,
                'B_l1': l1b, 'B_l2': l2b, 'A_ms': ma, 'B_ms': mb,
            })
        for (ch, r, c) in enumerate_bits(off_mask):
            rows_to_write.append({
                'bit': bit_label(ch, r, c), 'direction': 'OFF',
                'label': label, 'A_l1': l1a, 'A_l2': l2a,
                'B_l1': l1b, 'B_l2': l2b, 'A_ms': ma, 'B_ms': mb,
            })

        header = ['bit', 'direction', 'label', 'A_l1', 'A_l2',
                  'B_l1', 'B_l2', 'A_ms', 'B_ms']
        new_file = not os.path.exists(self.mapping_path)
        with open(self.mapping_path, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=header)
            if new_file:
                w.writeheader()
            for row in rows_to_write:
                w.writerow(row)
        self.status.config(
            text=f'saved {len(rows_to_write)} bit(s) as "{label}" → {self.mapping_path}',
            fg='#8f8')
        self.label_entry.delete(0, tk.END)

    # ----- Live LCD render -----

    def _render(self):
        with self.state.lock:
            ddram = bytes(self.state.ddram)
            cgram = bytes(self.state.cgram)
            status = self.state.status
            dirty = self.state.updated
            self.state.updated = False
        if dirty:
            self._draw_lcd(ddram, cgram)
            self.status.config(text=status)
        self.root.after(60, self._render)

    def _draw_lcd(self, ddram, cgram):
        self.lcd.delete('all')
        for row_i, offset in enumerate((0x00, 0x40)):
            y = 10 + row_i * (CHAR_H + CHAR_GAP)
            for col_i in range(16):
                x = 10 + col_i * (CHAR_W + CHAR_GAP)
                self.lcd.create_rectangle(
                    x - 1, y - 1, x + CHAR_W + 1, y + CHAR_H + 1,
                    outline=LCD_GRID, fill='')
                b = ddram[offset + col_i]
                pat = glyph_for(b, cgram)
                draw_char_grid(self.lcd, x, y, pat)


# ---------- Main ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='Serial port (default: auto-detect)')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--mapping', default='mapping.csv',
                   help='CSV file to append confirmed mappings to')
    args = p.parse_args()

    state = LiveState()

    def port_getter():
        return args.port or guess_port()

    reader = threading.Thread(target=serial_reader,
                              args=(state, port_getter, args.baud),
                              daemon=True)
    reader.start()

    root = tk.Tk()
    App(root, state, args.mapping)
    root.mainloop()


if __name__ == '__main__':
    main()
