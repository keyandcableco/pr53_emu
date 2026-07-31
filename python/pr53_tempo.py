#!/usr/bin/env python3
"""
pr53_tempo.py — Empirical tempo readout learner for SX-PR53.

Uses the pr53_map.py-generated mapping.csv to know WHICH CGRAM bits belong
to the tempo display, then builds a lookup database mapping "tempo value →
those bits' state". Once you've taught it a range of values, it displays
the current tempo in real time by matching against the closest-known state.

Teaching workflow:
    1. Confirm what tempo the piano is at now (count from a known start,
       or find TEMPO DOWN's minimum, or use the current-value hint below).
    2. Enter that number in "Actual tempo" and click "Teach".
    3. Press TEMPO UP once on piano, enter new value, Teach again.
    4. After ~15-30 samples the tool can match most values you'll ever see.

Guessing:
    Whenever known bits match a stored state exactly, "Guessed tempo"
    shows that value. If no exact match, shows nearest-known + delta.

Database persists in tempo_learned.csv. Delete that file to start over.

Usage:
    python3 pr53_tempo.py                        # auto-detect port
    python3 pr53_tempo.py --port /dev/ttyACM0
    python3 pr53_tempo.py --mapping mapping.csv --learned tempo_learned.csv
"""
import argparse
import csv
import os
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


# ---------- Load mapping.csv to find tempo bits ----------

def parse_bit(bit_str):
    """'C1:r5:c2' -> (1, 5, 2)"""
    parts = bit_str.split(':')
    return int(parts[0][1:]), int(parts[1][1:]), int(parts[2][1:])

def load_tempo_bits(mapping_path):
    """Return sorted list of (char, row, col) tuples that ever appeared in a
    diff whose label contained 'tempo'. These are the bits we care about."""
    if not os.path.exists(mapping_path):
        return []
    seen = set()
    with open(mapping_path, newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            if 'tempo' in row.get('label', '').lower():
                try:
                    seen.add(parse_bit(row['bit']))
                except (ValueError, IndexError):
                    pass
    return sorted(seen)


def load_learned(path):
    """Return dict {tempo_value:int -> bit_state_key:str} loaded from csv.
    The state key is a compact string of 0/1 for each tempo bit, in the
    same order as load_tempo_bits() returns them. Overwrites earlier
    entries for the same tempo value (last-write-wins)."""
    db = {}
    if not os.path.exists(path):
        return db
    with open(path, newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                db[int(row['tempo'])] = row['bit_state']
            except (ValueError, KeyError):
                pass
    return db


def save_learned(path, db, bits):
    """Rewrite the learned-CSV from db. Also embeds the bits header for
    self-describing files."""
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['# columns:', 'tempo', 'bit_state'])
        w.writerow([f'# bit order:'] + [f'C{c}:r{r}:c{k}' for c, r, k in bits])
        w.writerow(['tempo', 'bit_state'])
        for t in sorted(db):
            w.writerow([t, db[t]])


# ---------- Bit-state key ----------

def state_key(cgram, bits):
    """Return a '010110...' string of the tempo bits' state in a CGRAM."""
    out = []
    for ch, row, col in bits:
        b = cgram[ch * 8 + row]
        out.append('1' if (b >> (4 - col)) & 1 else '0')
    return ''.join(out)


def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def best_match(current, db):
    """Return (nearest_tempo, distance) or (None, None) if db empty."""
    if not db:
        return None, None
    best_t, best_d = None, 999
    for t, k in db.items():
        d = hamming(current, k)
        if d < best_d:
            best_d, best_t = d, t
    return best_t, best_d


# ---------- Live state ----------

class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.cgram = bytearray(64)
        self.ms = 0
        self.status = 'starting...'
        self.updated = False


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
                state.status = 'no serial port'
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
                try: line = raw.decode('utf-8', errors='replace').strip()
                except Exception: continue
                if not line or line.startswith('#'): continue
                parts = line.split(',')
                if len(parts) != 5: continue
                try:
                    ms = int(parts[0])
                    cgram = bytes.fromhex(parts[3])
                    if len(cgram) != 64: continue
                except (ValueError, IndexError):
                    continue
                with state.lock:
                    state.cgram = bytearray(cgram)
                    state.ms = ms
                    state.status = f'{port} — live ms={ms}'
                    state.updated = True
        except Exception as e:
            with state.lock:
                state.status = f'{port} lost: {e}'
                state.updated = True
            try: ser.close()
            except Exception: pass
            time.sleep(2)


# ---------- UI ----------

BG_APP    = '#0a1410'
BG_PANEL  = '#0e2e18'
CELL_ON   = '#c8ffb0'
CELL_OFF  = '#124a20'
FG_LABEL  = '#8ac48a'
FG_STATUS = '#5f8f5f'
FG_BIG    = '#ffeaa0'


class App:
    def __init__(self, root, state, mapping_path, learned_path):
        self.state = state
        self.mapping_path = mapping_path
        self.learned_path = learned_path
        self.bits = load_tempo_bits(mapping_path)
        self.learned = load_learned(learned_path)
        self.root = root
        root.title("SX-PR53 Tempo Learner")
        root.configure(bg=BG_APP)
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG_APP, padx=24, pady=20)
        wrap.pack()

        # ---- Header ----
        tk.Label(wrap,
                 text=f'{len(self.bits)} tempo bits from {mapping_path}',
                 bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')

        if not self.bits:
            tk.Label(wrap,
                     text=('No tempo bits found. Run pr53_map.py first and '
                           'save some diffs with "tempo" in the label.'),
                     bg=BG_APP, fg='#c66',
                     font=('Helvetica', 11), wraplength=520).pack(pady=12)
            return

        # ---- Big current-tempo display ----
        tk.Label(wrap, text='Guessed tempo', bg=BG_APP, fg=FG_STATUS,
                 font=('Helvetica', 10)).pack(anchor='w', pady=(14, 0))
        self.guess_lbl = tk.Label(wrap, text='—', bg=BG_APP, fg=FG_BIG,
                                  font=('Courier', 48, 'bold'))
        self.guess_lbl.pack(anchor='w')
        self.guess_detail = tk.Label(wrap, text='', bg=BG_APP, fg=FG_STATUS,
                                     font=('Courier', 10))
        self.guess_detail.pack(anchor='w', pady=(0, 12))

        # ---- Bit state grid ----
        tk.Label(wrap, text='Live tempo bits', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        bits_frame = tk.Frame(wrap, bg=BG_PANEL, padx=10, pady=8)
        bits_frame.pack(fill='x', pady=(4, 14))
        self.bit_widgets = []
        for i, (ch, row, col) in enumerate(self.bits):
            f = tk.Frame(bits_frame, bg=BG_PANEL)
            f.grid(row=0, column=i, padx=3)
            box = tk.Label(f, text='  ', bg=CELL_OFF, width=2, height=1,
                           relief='flat', bd=0)
            box.pack()
            tk.Label(f, text=f'C{ch}\nr{row}\nc{col}', bg=BG_PANEL,
                     fg=FG_STATUS,
                     font=('Courier', 8)).pack()
            self.bit_widgets.append(box)

        # ---- Teach controls ----
        teach = tk.Frame(wrap, bg=BG_APP)
        teach.pack(fill='x', pady=(0, 10))
        tk.Label(teach, text='Actual tempo:', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 11, 'bold')).pack(side='left')
        self.actual_entry = tk.Entry(teach, width=6, bg='#122', fg='#dfd',
                                     insertbackground='#dfd',
                                     font=('Courier', 14))
        self.actual_entry.pack(side='left', padx=(8, 8))
        self.actual_entry.bind('<Return>', lambda e: self._teach())
        tk.Button(teach, text='Teach', command=self._teach,
                  bg='#3a5a3a', fg='#fff',
                  activebackground='#4a6a4a',
                  font=('Helvetica', 11, 'bold')).pack(side='left')
        tk.Button(teach, text='Auto +1',
                  command=self._teach_auto_up,
                  bg='#2a4a5a', fg='#fff',
                  activebackground='#3a5a6a',
                  font=('Helvetica', 10)).pack(side='left', padx=(8, 0))
        tk.Button(teach, text='Auto -1',
                  command=self._teach_auto_down,
                  bg='#2a4a5a', fg='#fff',
                  activebackground='#3a5a6a',
                  font=('Helvetica', 10)).pack(side='left', padx=(4, 0))

        # ---- Learned summary ----
        self.learned_lbl = tk.Label(wrap, text='', bg=BG_APP, fg=FG_STATUS,
                                    font=('Courier', 10), anchor='w',
                                    justify='left', wraplength=560)
        self.learned_lbl.pack(fill='x', pady=(4, 8))
        self.status = tk.Label(wrap, text='ready', bg=BG_APP, fg=FG_STATUS,
                               font=('Courier', 10), anchor='w')
        self.status.pack(fill='x')

        self._last_taught = None
        self._refresh_learned_summary()
        self._render()

    # ---- Teach logic ----

    def _teach_value(self, value):
        with self.state.lock:
            key = state_key(self.state.cgram, self.bits)
        self.learned[value] = key
        save_learned(self.learned_path, self.learned, self.bits)
        self._last_taught = value
        self.actual_entry.delete(0, tk.END)
        self.actual_entry.insert(0, str(value))
        self.status.config(
            text=f'taught tempo={value} → {key}  ({len(self.learned)} known)',
            fg='#8f8')
        self._refresh_learned_summary()

    def _teach(self):
        try:
            v = int(self.actual_entry.get().strip())
        except ValueError:
            self.status.config(text='enter a number in Actual tempo', fg='#c66')
            return
        self._teach_value(v)

    def _teach_auto_up(self):
        if self._last_taught is None:
            self.status.config(text='use Teach first with an initial value',
                               fg='#c66')
            return
        self._teach_value(self._last_taught + 1)

    def _teach_auto_down(self):
        if self._last_taught is None:
            self.status.config(text='use Teach first with an initial value',
                               fg='#c66')
            return
        self._teach_value(self._last_taught - 1)

    def _refresh_learned_summary(self):
        if not self.learned:
            self.learned_lbl.config(text='(no learned values yet)')
            return
        keys = sorted(self.learned)
        ranges = []
        run_start = prev = keys[0]
        for k in keys[1:]:
            if k == prev + 1:
                prev = k; continue
            ranges.append((run_start, prev))
            run_start = prev = k
        ranges.append((run_start, prev))
        parts = [(f'{a}' if a == b else f'{a}-{b}') for a, b in ranges]
        self.learned_lbl.config(
            text=f'Learned {len(self.learned)} value(s): '
                 + ', '.join(parts))

    # ---- Render loop ----

    def _render(self):
        with self.state.lock:
            cgram = bytes(self.state.cgram)
            status = self.state.status
            dirty = self.state.updated
            self.state.updated = False

        if dirty:
            key = state_key(cgram, self.bits)
            # Update bit widgets
            for i, ch in enumerate(key):
                self.bit_widgets[i].config(bg=CELL_ON if ch == '1' else CELL_OFF)
            # Match
            t, d = best_match(key, self.learned)
            if t is None:
                self.guess_lbl.config(text='—', fg=FG_STATUS)
                self.guess_detail.config(text='learn some tempo values first')
            elif d == 0:
                self.guess_lbl.config(text=str(t), fg=FG_BIG)
                self.guess_detail.config(
                    text=f'exact match  ({len(self.learned)} known)')
            else:
                self.guess_lbl.config(text=f'~{t}', fg='#ff9')
                self.guess_detail.config(
                    text=(f'closest known differs by {d} bit(s)  — '
                          f'consider teaching this value'))
            self.status.config(text=status)

        self.root.after(60, self._render)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='Serial port (default: auto-detect)')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--mapping', default='mapping.csv',
                   help='mapping.csv from pr53_map.py')
    p.add_argument('--learned', default='tempo_learned.csv',
                   help='where to persist learned tempo values')
    args = p.parse_args()

    state = LiveState()
    def port_getter(): return args.port or guess_port()
    reader = threading.Thread(target=serial_reader,
                              args=(state, port_getter, args.baud),
                              daemon=True)
    reader.start()

    root = tk.Tk()
    App(root, state, args.mapping, args.learned)
    root.mainloop()


if __name__ == '__main__':
    main()
