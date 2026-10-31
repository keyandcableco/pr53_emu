#!/usr/bin/env python3
"""
pr53_campaign_report.py — Replay a campaign raw log and show what each step did.

Reads a log written by `pr53_campaign.py --raw-log`, replays the HD44780 bus,
and snapshots the display at every saved step (the last capture before each
save). For each campaign run it prints the two text lines per step and the
CGRAM bits that changed since the previous step, then a table of every bit
that varies across the run, so a field's segments and their values per step
can be read off directly.

Usage:
    pr53_campaign_report.py captures/campaign_2026-10-31.log
    pr53_campaign_report.py LOG --campaign chord_roots_all12
    pr53_campaign_report.py LOG --campaign chord_roots_all12 --run 2

Bits are named like the other tools: C<char>:r<row>:c<col>, col 0 = leftmost.
"""
import argparse
import re
import sys

WALL_RE = re.compile(r'^t_wall=\S+\s+(.*)$')
EVENT_RE = re.compile(r'^t=\d+\s+W\s+(CMD|DAT)\s+0x([0-9A-Fa-f]{2})')
NOTE_RE = re.compile(r'^#\s*NOTE\s+(.*)$')
START_RE = re.compile(r'^campaign (\S+) start')
STEP_RE = re.compile(r'^(capture|saved|skipped) step (\d+): (.*)$')


class Display:
    def __init__(self):
        self.ddram = bytearray(b' ' * 128)
        self.cgram = bytearray(64)
        self.ac = 0
        self.in_cgram = False

    def cmd(self, b):
        if b & 0x80:
            self.in_cgram, self.ac = False, b & 0x7F
        elif b & 0x40:
            self.in_cgram, self.ac = True, b & 0x3F
        elif b == 0x01:
            self.ddram[:] = b' ' * 128
            self.ac, self.in_cgram = 0, False

    def data(self, b):
        if self.in_cgram:
            self.cgram[self.ac] = b & 0x1F
            self.ac = (self.ac + 1) & 0x3F
        else:
            self.ddram[self.ac] = b
            self.ac = (self.ac + 1) & 0x7F

    def snapshot(self):
        def line(off):
            return ''.join(chr(c) if 32 <= c < 127 else '.' for c in self.ddram[off:off + 12])
        return {'l1': line(0), 'l2': line(0x40), 'cgram': bytes(self.cgram)}


def bits_on(cgram):
    out = set()
    for pos, byte in enumerate(cgram):
        for col in range(5):
            if (byte >> (4 - col)) & 1:
                out.add((pos // 8, pos % 8, col))
    return out


def name(bit):
    return f'C{bit[0]}:r{bit[1]}:c{bit[2]}'


def parse(path):
    disp = Display()
    runs, run, pending = [], None, None
    for raw in open(path, errors='replace'):
        line = raw.rstrip('\n')
        m = WALL_RE.match(line)
        body = m.group(1) if m else line
        ev = EVENT_RE.match(body)
        if ev:
            b = int(ev.group(2), 16)
            disp.cmd(b) if ev.group(1) == 'CMD' else disp.data(b)
            continue
        note = NOTE_RE.match(body)
        if not note:
            continue
        text = note.group(1)
        st = START_RE.match(text)
        if st:
            run = {'campaign': st.group(1), 'baseline': disp.snapshot(), 'steps': []}
            runs.append(run)
            pending = None
            continue
        sp = STEP_RE.match(text)
        if not sp or run is None:
            continue
        kind, num, label = sp.group(1), int(sp.group(2)), sp.group(3)
        if kind == 'capture':
            pending = disp.snapshot()
        elif kind == 'saved' and pending is not None:
            run['steps'].append({'num': num, 'label': label, **pending})
            pending = None
        elif kind == 'skipped':
            run['steps'].append({'num': num, 'label': label + ' (skipped)', 'skipped': True})
    return runs


def report(run, out):
    print(f"== {run['campaign']}: {len(run['steps'])} steps", file=out)
    prev = run['baseline']
    states = [('baseline', prev)]
    print(f"   {'baseline':28s} L1={prev['l1']!r} L2={prev['l2']!r}", file=out)
    for s in run['steps']:
        if s.get('skipped'):
            print(f"   {s['label']:28s}", file=out)
            continue
        on, before = bits_on(s['cgram']), bits_on(prev['cgram'])
        added = sorted(on - before)
        removed = sorted(before - on)
        changes = ' '.join(['+' + name(b) for b in added] + ['-' + name(b) for b in removed])
        print(f"   {s['label']:28s} L1={s['l1']!r} L2={s['l2']!r}  "
              f"{len(added) + len(removed):3d} bits {changes}", file=out)
        states.append((s['label'], s))
        prev = s
    # Every bit that differs anywhere across the run, as a step x bit table.
    sets = [bits_on(st['cgram']) for _, st in states]
    varying = sorted(set.union(*sets) - set.intersection(*sets))
    if not varying:
        return
    print(f"\n   {len(varying)} bits vary across this run:", file=out)
    width = max(len(lbl) for lbl, _ in states)
    print(' ' * (width + 4) + ' '.join(f'{name(b):>9s}' for b in varying), file=out)
    for (lbl, _), on in zip(states, sets):
        print(f"   {lbl:{width}s} " + ' '.join(f"{('#' if b in on else '.'):>9s}" for b in varying),
              file=out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('log')
    p.add_argument('--campaign', help='only this campaign')
    p.add_argument('--run', type=int, default=0,
                   help='which run of that campaign, 1 = first (default: last)')
    args = p.parse_args()
    runs = parse(args.log)
    if args.campaign:
        runs = [r for r in runs if r['campaign'] == args.campaign]
        if not runs:
            sys.exit(f'no run of {args.campaign} in {args.log}')
        runs = [runs[args.run - 1] if args.run else runs[-1]]
    for r in runs:
        report(r, sys.stdout)
        print()


if __name__ == '__main__':
    main()
