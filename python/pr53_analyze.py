#!/usr/bin/env python3
"""
pr53_analyze.py — Analyze SX-PR53 multiplex-cycle CSV captures from v13 firmware.

Usage:
    pr53_analyze.py capture.csv              # full report
    pr53_analyze.py capture.csv --states     # just per-state CGRAM union view
    pr53_analyze.py capture.csv --diff A B   # bit-diff between two state names (substring match)
    pr53_analyze.py capture.csv --raw N      # dump snapshot #N as ASCII CGRAM
    pr53_analyze.py capture.csv --annotate events.txt  # overlay button-press events

events.txt format (one per line):
    12345 voice-up
    38419 menu
    42458 voice-down
"""
import argparse
import sys
from pathlib import Path

# --- Loading ---

def load_csv(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) != 5:
                continue
            try:
                rows.append({
                    'ms': int(parts[0]),
                    'ac': int(parts[1], 16),
                    'in_cgram': int(parts[2]),
                    'cgram': bytes.fromhex(parts[3]),
                    'ddram': bytes.fromhex(parts[4]),
                })
            except (ValueError, IndexError):
                continue
    return rows

def load_events(path):
    """Read annotation file: 'ms label' per line."""
    events = []
    if not path:
        return events
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                try:
                    events.append((int(parts[0]), parts[1]))
                except ValueError:
                    pass
    return sorted(events)

# --- Decoding ---

def decode_text(ddram, start, length=12):
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in ddram[start:start+length])

def l1(row): return decode_text(row['ddram'], 0)
def l2(row): return decode_text(row['ddram'], 0x40)

def state_key(row):
    return (l1(row), l2(row))

# --- Views ---

def render_cgram(cg):
    """8 CGRAM chars as compact ASCII grid."""
    lines = []
    for ch in range(8):
        char = cg[ch*8:(ch+1)*8]
        pattern = []
        for row_byte in char:
            row = ''.join('#' if (row_byte >> (4-b)) & 1 else '.' for b in range(5))
            pattern.append(row)
        bits = sum(bin(b & 0x1F).count('1') for b in char)
        lines.append(f'  C{ch} ({bits:2}b): ' + ' '.join(pattern))
    return '\n'.join(lines)

def cgram_union(rows):
    result = bytearray(64)
    for r in rows:
        for i in range(64):
            result[i] |= r['cgram'][i]
    return bytes(result)

def count_bits(data):
    return sum(bin(b & 0x1F).count('1') for b in data)

# --- Reports ---

def report_timeline(rows, events):
    print("=" * 78)
    print("STATE TIMELINE")
    print("=" * 78)
    prev = None
    ev_iter = iter(events)
    next_ev = next(ev_iter, None)
    for r in rows:
        while next_ev and next_ev[0] <= r['ms']:
            print(f"  >> t={next_ev[0]:>6}ms  EVENT: {next_ev[1]}")
            next_ev = next(ev_iter, None)
        key = state_key(r)
        if key != prev:
            bits = count_bits(r['cgram'])
            print(f"  t={r['ms']:>6}ms  L1='{key[0]}'  L2='{key[1]}'  cg_bits={bits}")
            prev = key
    while next_ev:
        print(f"  >> t={next_ev[0]:>6}ms  EVENT: {next_ev[1]}")
        next_ev = next(ev_iter, None)
    print()

def report_states(rows):
    print("=" * 78)
    print("STATES (CGRAM union per unique text state)")
    print("=" * 78)
    groups = {}
    order = []
    for r in rows:
        k = state_key(r)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    for k in order:
        grp = groups[k]
        union = cgram_union(grp)
        bits = count_bits(union)
        first_ms = grp[0]['ms']
        last_ms = grp[-1]['ms']
        print(f"\nSTATE L1='{k[0]}'  L2='{k[1]}'")
        print(f"  {len(grp)} snapshots, {first_ms}..{last_ms}ms, {bits} bits set in union")
        print(render_cgram(union))
    return groups

def cgram_intersection(rows):
    if not rows: return bytes(64)
    result = bytearray(rows[0]['cgram'])
    for r in rows[1:]:
        for i in range(64):
            result[i] &= r['cgram'][i]
    return bytes(result)

def report_diff(groups, needle_a, needle_b):
    print("=" * 78)
    print(f"BIT DIFF: state matching '{needle_a}' vs '{needle_b}'")
    print("=" * 78)
    def find(needle):
        return [k for k in groups if needle.lower() in (k[0] + '|' + k[1]).lower()]
    a = find(needle_a); b = find(needle_b)
    if not a or not b:
        print(f"No match. A={a} B={b}")
        return
    print(f"State A '{needle_a}' ({len(a)} matches):")
    for k in a: print(f"    L1='{k[0]}' L2='{k[1]}' ({len(groups[k])} snaps)")
    print(f"State B '{needle_b}' ({len(b)} matches):")
    for k in b: print(f"    L1='{k[0]}' L2='{k[1]}' ({len(groups[k])} snaps)")
    print()

    rows_a = [r for k in a for r in groups[k]]
    rows_b = [r for k in b for r in groups[k]]
    ua = cgram_union(rows_a);      ub = cgram_union(rows_b)
    ia = cgram_intersection(rows_a); ib = cgram_intersection(rows_b)

    # STRICT: bits ON in every A snap AND OFF in every B snap. These are the
    # high-confidence label bits — nothing voice/state-specific can survive
    # both a strict intersection on A and total absence from B.
    strict_a = bytes((x & ~y) & 0x1F for x, y in zip(ia, ub))
    strict_b = bytes((x & ~y) & 0x1F for x, y in zip(ib, ua))

    # LOOSE: bits ever ON in some A snap but not in any B snap. Wider —
    # includes voice-name bits that happened to be in an A state but not a
    # B state. Useful for exploration; noisy for label mapping.
    loose_a = bytes((x & ~y) & 0x1F for x, y in zip(ua, ub))
    loose_b = bytes((~x & y) & 0x1F for x, y in zip(ua, ub))

    print(f"STRICT — bits ON in every A snap and OFF in every B snap")
    print(f"  A '{needle_a}' unique ({count_bits(strict_a)} bits):")
    print(render_cgram(strict_a))
    print(f"  B '{needle_b}' unique ({count_bits(strict_b)} bits):")
    print(render_cgram(strict_b))
    print()
    print(f"LOOSE — bits ever ON in A but not in any B snap (and vice versa)")
    print(f"  A '{needle_a}' loose-unique ({count_bits(loose_a)} bits):")
    print(render_cgram(loose_a))
    print(f"  B '{needle_b}' loose-unique ({count_bits(loose_b)} bits):")
    print(render_cgram(loose_b))

def report_raw(rows, idx):
    if idx < 0 or idx >= len(rows):
        print(f"Index {idx} out of range (have {len(rows)})")
        return
    r = rows[idx]
    print(f"Snapshot #{idx}  t={r['ms']}ms  ac=0x{r['ac']:02X}  in_cgram={r['in_cgram']}")
    print(f"L1='{l1(r)}'  L2='{l2(r)}'")
    print(f"cg_bits={count_bits(r['cgram'])}")
    print(render_cgram(r['cgram']))

# --- Main ---

def main():
    p = argparse.ArgumentParser()
    p.add_argument('csv')
    p.add_argument('--states', action='store_true', help='states report only')
    p.add_argument('--diff', nargs=2, metavar=('A', 'B'), help='bit-diff between two states (substring match)')
    p.add_argument('--raw', type=int, metavar='N', help='dump snapshot N as CGRAM art')
    p.add_argument('--annotate', metavar='FILE', help='overlay button-press events')
    args = p.parse_args()

    rows = load_csv(args.csv)
    events = load_events(args.annotate) if args.annotate else []
    print(f"Loaded {len(rows)} snapshots from {args.csv}")
    if events:
        print(f"Loaded {len(events)} events from {args.annotate}")
    print()

    if args.raw is not None:
        report_raw(rows, args.raw)
        return

    if args.diff:
        groups = {}
        for r in rows:
            groups.setdefault(state_key(r), []).append(r)
        report_diff(groups, args.diff[0], args.diff[1])
        return

    if args.states:
        report_states(rows)
        return

    report_timeline(rows, events)
    report_states(rows)

if __name__ == '__main__':
    main()
