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
                        state.state.apply_cmd(b)
                        # Commit the visible buffers when display transitions
                        # to on (bit 2 of DISP_CTRL). Also commit continuously
                        # if display is already on so voice-name changes
                        # during play still show up promptly.
                        if state.state.display_on:
                            state.committed_ddram[:] = state.state.ddram
                            state.committed_cgram[:] = state.state.cgram
                    elif kind == 'DAT':
                        state.state.apply_data(b)
                        # If display is currently on, commit each data write
                        # too so live activity (text streaming in) is visible.
                        # When display is OFF the buffer is being staged
                        # invisibly, exactly how the real LCD would behave.
                        if state.state.display_on:
                            state.committed_ddram[:] = state.state.ddram
                            state.committed_cgram[:] = state.state.cgram
                    state.event_count += 1

                    # Persistent voice/rhythm/mode — use committed buffers
                    # so we don't classify text mid-write.
                    ddram = state.committed_ddram
                    l1 = ''.join(chr(x) if 32 <= x < 127 else ' '
                                 for x in ddram[0:12])
                    l2 = ''.join(chr(x) if 32 <= x < 127 else ' '
                                 for x in ddram[0x40:0x40+12])
                    l1_menu = looks_like_menu_label(l1)
                    l2_menu = looks_like_menu_label(l2)
                    if l1_menu or l2_menu:
                        state.current_mode = (l1.strip() if l1_menu
                                              else l2.strip())
                    else:
                        state.current_mode = ''
                    if not l1_menu and l1.strip():
                        state.persistent_l1 = l1
                    if not l2_menu and l2.strip():
                        state.persistent_l2 = l2

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
    def __init__(self, root, state):
        self.state = state
        self.root = root
        root.title("SX-PR53 Live Display (v14)")
        root.configure(bg=BG_APP)
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG_APP, padx=24, pady=24)
        wrap.pack()

        # Persistent-state header
        tk.Label(wrap, text='Piano state (persistent)', bg=BG_APP,
                 fg=FG_LABEL, font=('Helvetica', 11, 'bold')).pack(anchor='w')
        persist = tk.Frame(wrap, bg=BG_PANEL, padx=14, pady=10,
                           highlightthickness=1, highlightbackground='#0a2812')
        persist.pack(fill='x', pady=(6, 16))
        def _row(parent, r, label):
            tk.Label(parent, text=label, bg=BG_PANEL, fg=FG_STATUS,
                     font=('Helvetica', 10), anchor='e', width=16).grid(
                        row=r, column=0, sticky='e', padx=(0, 12), pady=2)
            v = tk.Label(parent, text='—', bg=BG_PANEL, fg=LCD_ON,
                         font=('Courier', 14, 'bold'), anchor='w')
            v.grid(row=r, column=1, sticky='w', pady=2)
            return v
        self.voice_lbl = _row(persist, 0, 'Line 1 (top):')
        self.rhythm_lbl = _row(persist, 1, 'Line 2 (bottom):')
        self.mode_lbl = _row(persist, 2, 'Mode:')

        tk.Label(wrap, text='Raw LCD (what the piano writes right now)',
                 bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 11, 'bold')).pack(anchor='w')
        lcd_w = 16 * CHAR_W + 15 * CHAR_GAP + 20
        lcd_h = 2 * CHAR_H + CHAR_GAP + 20
        self.lcd = tk.Canvas(wrap, width=lcd_w, height=lcd_h, bg=LCD_BG,
                             highlightthickness=2, highlightbackground='#000')
        self.lcd.pack(pady=(6, 18))

        tk.Label(wrap, text='CGRAM 0..7 (raw pixel view)', bg=BG_APP,
                 fg=FG_LABEL, font=('Helvetica', 10, 'bold')).pack(anchor='w')
        cg_gap = 12
        cg_w = 8 * CHAR_W + 7 * cg_gap + 20
        cg_h = CHAR_H + 20
        self.cg = tk.Canvas(wrap, width=cg_w, height=cg_h, bg=BG_PANEL,
                            highlightthickness=1,
                            highlightbackground='#0a2812')
        self.cg.pack(pady=(6, 12))

        self.status = tk.Label(wrap, text='waiting for serial...',
                               bg=BG_APP, fg=FG_STATUS,
                               font=('Courier', 10), anchor='w',
                               justify='left')
        self.status.pack(fill='x')

        self._render()

    def _render(self):
        with self.state.lock:
            # Render from committed buffers, not the raw state machine —
            # this hides intermediate writes that happen while display is off.
            ddram = bytes(self.state.committed_ddram)
            cgram = bytes(self.state.committed_cgram)
            status = self.state.status
            persistent_l1 = self.state.persistent_l1
            persistent_l2 = self.state.persistent_l2
            current_mode = self.state.current_mode
            dirty = self.state.updated
            self.state.updated = False

        if dirty:
            self._draw_lcd(ddram, cgram)
            self._draw_cgram(cgram)
            self.voice_lbl.config(text=persistent_l1.strip() or '—')
            self.rhythm_lbl.config(text=persistent_l2.strip() or '—')
            self.mode_lbl.config(
                text=current_mode if current_mode else '(playing)',
                fg='#ffcc55' if current_mode else FG_STATUS)
            self.status.config(text=status)

        # Faster refresh — 30fps ceiling — because events stream continuously.
        self.root.after(33, self._render)

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

    def _draw_cgram(self, cgram):
        self.cg.delete('all')
        cg_gap = 12
        for ch in range(8):
            x = 10 + ch * (CHAR_W + cg_gap); y = 10
            self.cg.create_text(x + CHAR_W // 2, y - 2, text=str(ch),
                                fill=FG_LABEL, font=('Helvetica', 8),
                                anchor='s')
            pat = cgram[ch * 8:(ch + 1) * 8]
            draw_char_grid(self.cg, x, y, pat)


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
