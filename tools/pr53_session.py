#!/usr/bin/env python3
"""
pr53_session.py — Offline analyzer for pr53_record.py session logs.

Reads a free-running session log (raw v15 event stream + timestamped
# NOTE annotations), runs the HD44780 state machine over the whole
thing, and reconstructs a timeline of every *committed* display state
(the CGRAM+DDRAM as it stood at each display-on / 0x0C commit). Then:

  * Diffs each committed state against the previous one — so every
    change the piano made is captured, whether or not you clicked
    anything at the time.
  * Aligns your # NOTE annotations to the state that was current when
    you typed them, so "entering MIDI menu" sits next to the snapshot
    that shows the MIDI menu.
  * Optionally appends bit-diffs to mapping.csv with labels derived
    from your notes (so a free-running session feeds the same decoders
    the campaign tool does).

This is the answer to "some menus revert before I can capture them":
the revert is in the log too. You narrate loosely; the analyzer does
the alignment.

Usage:
    python3 pr53_session.py session_120000.log
        # prints the timeline: notes + state diffs, human-readable

    python3 pr53_session.py session_120000.log --states
        # dump every committed state's decoded readout (voice/tempo/etc)

    python3 pr53_session.py session_120000.log --diff "MIDI"
        # show only state transitions near notes matching "MIDI"

    python3 pr53_session.py session_120000.log --to-mapping out.csv
        # append labeled bit-diffs (label = nearest preceding note,
        #   slugified) to a mapping.csv-format file for the decoders

Design notes:
  * "Committed" state = snapshot taken at each DISPLAY-ON (0x0C-class)
    command, matching pr53_display.py's commit semantics. Bulk CGRAM
    redraws between commits don't create spurious diffs.
  * A diff with a huge bit count (> BULK_THRESHOLD) is almost always a
    voice-name change or a full redraw; flagged as [BULK] so you can
    skip it when hunting single-bit indicators.
  * Annotations bind to the FIRST committed state at or after the note
    timestamp (you usually type the note, THEN do the action), but the
    binding is shown both ways so you can eyeself.

Dependencies: none beyond stdlib.
"""
import argparse
import csv
import os
import re
import sys


# ============================================================
# HD44780 state machine (identical semantics to pr53_display.py)
# ============================================================

class HD44780State:
    def __init__(self):
        self.ddram = bytearray(0x20 for _ in range(128))
        self.cgram = bytearray(64)
        self.ac = 0
        self.in_cgram = False
        self.entry_inc = True
        self.display_on = False

    def apply_cmd(self, b):
        if b == 0x01:
            for i in range(128):
                self.ddram[i] = 0x20
            self.ac = 0
            self.in_cgram = False
        elif b <= 0x03:
            self.ac = 0
            self.in_cgram = False
        elif (b & 0xFC) == 0x04:
            self.entry_inc = (b & 0x02) != 0
        elif (b & 0xF8) == 0x08:
            self.display_on = (b & 0x04) != 0
        elif (b & 0xC0) == 0x40:
            self.ac = b & 0x3F
            self.in_cgram = True
        elif b & 0x80:
            self.ac = b & 0x7F
            self.in_cgram = False

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

    def snapshot(self):
        return bytes(self.cgram), bytes(self.ddram)


# ============================================================
# Log parsing
# ============================================================

# Raw v15 line embedded after the wall-clock prefix, e.g.
#   t_wall=1730000000.123 t=00123456 W CMD 0x80 [SET_DDRAM 0x00]
WALL_RE = re.compile(r'^t_wall=(\d+(?:\.\d+)?)\s+(.*)$')
EVENT_RE = re.compile(
    r'^t=\d+\s+([WR])\s+(CMD|DAT|STA)(?:\s+0x([0-9A-Fa-f]{2}))?')
NOTE_RE = re.compile(r'^#\s*NOTE\s+(.*)$')


class Note:
    def __init__(self, t_wall, text):
        self.t_wall = t_wall
        self.text = text


class CommitState:
    """A committed (display-on) snapshot with the time it occurred."""
    def __init__(self, t_wall, cgram, ddram, event_idx):
        self.t_wall = t_wall
        self.cgram = cgram
        self.ddram = ddram
        self.event_idx = event_idx


def parse_log(path):
    """Return (commits, notes). commits: list[CommitState] at each
    display-on commit. notes: list[Note]."""
    st = HD44780State()
    commits = []
    notes = []
    event_idx = 0
    last_wall = 0.0
    prev_display_on = False

    with open(path, 'r', errors='replace') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = WALL_RE.match(line)
            if m:
                t_wall = float(m.group(1))
                last_wall = t_wall
                body = m.group(2)
            else:
                # tolerate logs without wall prefix (plain v15 stream)
                t_wall = last_wall
                body = line

            note_m = NOTE_RE.match(body)
            if note_m:
                txt = note_m.group(1).strip()
                # Skip recorder housekeeping (connect/lost/reconnect spam)
                # and any alive-ping text that leaked through — these are
                # not user annotations and just clutter the timeline.
                low = txt.lower()
                if txt.startswith('[recorder]') or low.startswith('alive') \
                        or 'ring_depth' in low:
                    continue
                notes.append(Note(t_wall, txt))
                continue

            ev = EVENT_RE.match(body)
            if not ev:
                continue
            direction, kind, hexbyte = ev.group(1), ev.group(2), ev.group(3)
            if direction != 'W' or hexbyte is None:
                continue
            b = int(hexbyte, 16)
            event_idx += 1
            if kind == 'CMD':
                st.apply_cmd(b)
                # Commit a snapshot whenever display transitions to ON,
                # OR on any display-on-class command while already on
                # (matches the "commit on 0x0C" behavior).
                if (b & 0xF8) == 0x08 and (b & 0x04):
                    cg, dd = st.snapshot()
                    commits.append(CommitState(t_wall, cg, dd, event_idx))
                prev_display_on = st.display_on
            elif kind == 'DAT':
                st.apply_data(b)

    # De-duplicate consecutive identical commits (idle re-commits).
    deduped = []
    for c in commits:
        if deduped and deduped[-1].cgram == c.cgram and \
                deduped[-1].ddram == c.ddram:
            continue
        deduped.append(c)
    return deduped, notes


# ============================================================
# Diffing
# ============================================================

BULK_THRESHOLD = 12   # more changed bits than this = redraw/voice-name


def bit_label(ch, r, c):
    return f'C{ch}:r{r}:c{c}'


def diff_cgram(a, b):
    """Return (on_bits, off_bits) as lists of (ch,r,c) going a->b."""
    on, off = [], []
    for ch in range(8):
        for r in range(8):
            av = a[ch * 8 + r]
            bv = b[ch * 8 + r]
            if av == bv:
                continue
            for c in range(5):
                abit = (av >> (4 - c)) & 1
                bbit = (bv >> (4 - c)) & 1
                if abit and not bbit:
                    off.append((ch, r, c))
                elif bbit and not abit:
                    on.append((ch, r, c))
    return on, off


def ddram_text(dd):
    def line(off):
        return ''.join(chr(x) if 32 <= x < 127 else '.'
                       for x in dd[off:off + 12])
    return line(0x00), line(0x40)


# ============================================================
# Timeline / reporting
# ============================================================

def build_timeline(commits, notes):
    """Interleave notes and commit-diffs by time. Returns a list of
    ('note', Note) and ('diff', prev, cur, on, off) tuples in order."""
    events = []
    for n in notes:
        events.append((n.t_wall, 'note', n))
    for i in range(1, len(commits)):
        prev, cur = commits[i - 1], commits[i]
        on, off = diff_cgram(prev.cgram, cur.cgram)
        if not on and not off:
            continue
        events.append((cur.t_wall, 'diff', (prev, cur, on, off)))
    events.sort(key=lambda e: e[0])
    return events


def fmt_bits(bits):
    return ' '.join(bit_label(*b) for b in bits)


def print_timeline(events, t0):
    for t_wall, kind, payload in events:
        rel = t_wall - t0
        if kind == 'note':
            print(f'\n[{rel:8.2f}s] NOTE: {payload.text}')
        else:
            prev, cur, on, off = payload
            n = len(on) + len(off)
            tag = ' [BULK]' if n > BULK_THRESHOLD else ''
            l1, l2 = ddram_text(cur.ddram)
            print(f'[{rel:8.2f}s] diff {n:3d} bits{tag}  '
                  f'L1="{l1}" L2="{l2}"')
            if n <= BULK_THRESHOLD:
                if on:
                    print(f'            ON : {fmt_bits(on)}')
                if off:
                    print(f'            OFF: {fmt_bits(off)}')


def print_states(commits, t0):
    # Lazy import of the display decoders if available, else basic text.
    dec = _try_import_decoders()
    for i, c in enumerate(commits):
        rel = c.t_wall - t0
        l1, l2 = ddram_text(c.ddram)
        extra = ''
        if dec:
            parts = []
            t = dec['decode_tempo'](c.cgram)
            if t is not None:
                parts.append(f'tempo={t}')
            ch = dec['decode_chord'](c.cgram)
            if ch and ch.strip():
                parts.append(f'chord={ch}')
            extra = '  ' + ' '.join(parts) if parts else ''
        print(f'[{rel:8.2f}s] #{i:03d}  L1="{l1}" L2="{l2}"{extra}')


def _try_import_decoders():
    """Best-effort import of decode_* from pr53_display.py in cwd."""
    try:
        import importlib.util
        import types
        for m in ['serial', 'serial.tools', 'serial.tools.list_ports',
                  'tkinter', 'tkinter.ttk']:
            if m not in sys.modules:
                sys.modules[m] = types.ModuleType(m)
        sys.modules['serial'].Serial = object
        sys.modules['serial.tools.list_ports'].comports = lambda: []
        sys.modules['tkinter'].ttk = sys.modules['tkinter.ttk']
        spec = importlib.util.spec_from_file_location(
            'pr53_display', 'pr53_display.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {'decode_tempo': mod.decode_tempo,
                'decode_chord': mod.decode_chord}
    except Exception:
        return None


def slugify(text):
    s = re.sub(r'[^a-zA-Z0-9]+', '_', text.strip().lower())
    return s.strip('_')[:40] or 'note'


def export_mapping(events, path):
    """Append labeled diffs to a mapping.csv-format file. Label = the
    most recent NOTE preceding each diff, slugified."""
    header = ['bit', 'direction', 'label', 'A_l1', 'A_l2',
              'B_l1', 'B_l2', 'A_ms', 'B_ms']
    new_file = not os.path.exists(path)
    cur_label = 'session'
    rows = []
    for t_wall, kind, payload in events:
        if kind == 'note':
            cur_label = slugify(payload.text)
            continue
        prev, cur, on, off = payload
        n = len(on) + len(off)
        if n == 0 or n > BULK_THRESHOLD:
            continue  # skip bulk redraws in export
        a1, a2 = ddram_text(prev.ddram)
        b1, b2 = ddram_text(cur.ddram)
        for (ch, r, c) in on:
            rows.append(dict(bit=bit_label(ch, r, c), direction='ON',
                             label=cur_label, A_l1=a1, A_l2=a2,
                             B_l1=b1, B_l2=b2, A_ms='', B_ms=''))
        for (ch, r, c) in off:
            rows.append(dict(bit=bit_label(ch, r, c), direction='OFF',
                             label=cur_label, A_l1=a1, A_l2=a2,
                             B_l1=b1, B_l2=b2, A_ms='', B_ms=''))
    with open(path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header)
        if new_file:
            w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def main():
    global BULK_THRESHOLD
    ap = argparse.ArgumentParser()
    ap.add_argument('logfile')
    ap.add_argument('--states', action='store_true',
                    help='List every committed display state instead of diffs')
    ap.add_argument('--diff', metavar='SUBSTR',
                    help='Only show timeline around notes matching SUBSTR')
    ap.add_argument('--to-mapping', metavar='CSV',
                    help='Append labeled bit-diffs to a mapping.csv file')
    ap.add_argument('--bulk', type=int, default=None,
                    help=f'Override BULK threshold (default {BULK_THRESHOLD})')
    args = ap.parse_args()

    if args.bulk is not None:
        BULK_THRESHOLD = args.bulk

    commits, notes = parse_log(args.logfile)
    if not commits:
        print("No committed display states found. Is this a v15 log?")
        sys.exit(1)
    t0 = commits[0].t_wall
    print(f"Parsed {len(commits)} committed states, {len(notes)} notes. "
          f"Span {commits[-1].t_wall - t0:.1f}s.\n")

    if args.states:
        print_states(commits, t0)
        return

    events = build_timeline(commits, notes)

    if args.diff:
        # Filter to windows around matching notes (±5s).
        keep_windows = [n.t_wall for n in notes
                        if args.diff.lower() in n.text.lower()]
        if not keep_windows:
            print(f"No notes match '{args.diff}'.")
            return
        filtered = []
        for e in events:
            if any(abs(e[0] - w) <= 5.0 for w in keep_windows):
                filtered.append(e)
        events = filtered

    print_timeline(events, t0)

    if args.to_mapping:
        # Rebuild full (unfiltered) events for a complete export.
        full = build_timeline(commits, notes)
        n = export_mapping(full, args.to_mapping)
        print(f"\nAppended {n} bit-diff rows to {args.to_mapping}")


if __name__ == '__main__':
    main()
