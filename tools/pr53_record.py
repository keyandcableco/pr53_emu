#!/usr/bin/env python3
"""
pr53_record.py — Free-running session recorder for SX-PR53 mapping.

The problem this solves: some piano menus time out and revert to the main
screen after a few seconds, so you can't reliably line up a manual
"Capture" click with the state you want. This tool doesn't ask you to.
It logs the ENTIRE v15 event stream continuously to a file, with
wall-clock timestamps, and lets you drop timestamped text annotations
into the same timeline whenever you like (just type and press Enter).

Afterward, run pr53_session.py on the log to reconstruct every
display-on state, auto-diff neighbors, and align your annotations to the
states they describe — all offline, no timing pressure.

Workflow:
    1. python3 pr53_record.py            # starts logging immediately
    2. Do stuff on the piano. Before (or during) each action, type a
       short note and press Enter, e.g.:
           enter transpose menu
           transpose up to F#
           back to main (timed out)
       Each note is timestamped into the log as a "# NOTE" line.
    3. Ctrl-C to stop. Log saved as session_HHMMSS.log (or --out).
    4. python3 pr53_session.py session_HHMMSS.log

The log format is a superset of the v15 stream: every raw line is kept
verbatim with a leading "t_wall=<epoch>" prefix, and annotations appear
as "t_wall=<epoch> # NOTE <your text>". pr53_session.py understands both.

Dependencies: pyserial. Everything else is stdlib.
"""
import argparse
import sys
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Need pyserial. Install with:  pip install pyserial")
    sys.exit(1)


def guess_port():
    for p in list(list_ports.comports()):
        n = ((p.device or '') + ' ' + (p.description or '') + ' '
             + (p.manufacturer or '')).upper()
        if 'ACM' in n or 'PICO' in n or 'RP2' in n or 'BOARD CDC' in n:
            return p.device
    ports = list(list_ports.comports())
    return ports[0].device if ports else None


class Recorder:
    def __init__(self, port, baud, out_path):
        self.port = port
        self.baud = baud
        self.out_path = out_path
        self.f = open(out_path, 'w')
        self.lock = threading.Lock()
        self.line_count = 0
        self.note_count = 0
        self.commit_count = 0      # DISP_ON (0x0C-class) events = display updates
        self.last_event_wall = 0.0  # wall-clock of most recent bus line
        self.running = True
        self.connected = False

    def write_line(self, text):
        with self.lock:
            self.f.write(text + '\n')
            self.f.flush()

    def serial_loop(self):
        while self.running:
            try:
                ser = serial.Serial(self.port, self.baud, timeout=1)
            except Exception as e:
                self.write_line(f't_wall={time.time():.3f} # NOTE '
                                f'[recorder] serial open failed: {e}')
                time.sleep(2)
                continue
            self.connected = True
            self.write_line(f't_wall={time.time():.3f} # NOTE '
                            f'[recorder] connected {self.port}')
            try:
                while self.running:
                    raw = ser.readline()
                    if not raw:
                        # Read timeout with no data — NOT a disconnect.
                        # Just keep waiting; the piano is event-driven and
                        # can be silent for long stretches.
                        continue
                    try:
                        line = raw.decode('utf-8', errors='replace').rstrip()
                    except Exception:
                        continue
                    if not line:
                        continue
                    self.write_line(f't_wall={time.time():.3f} {line}')
                    self.line_count += 1
                    # Track activity for the live indicator. Ignore the 2s
                    # ALIVE housekeeping pings — only real bus traffic counts.
                    if not line.startswith('#'):
                        self.last_event_wall = time.time()
                        # A DISP_ON / display-control commit (0x0C-class) is
                        # what actually latches a display change — count those
                        # as "commits" so the user can see each press land.
                        if 'DISP' in line or '0x0C' in line or '0x0E' in line \
                                or '0x0F' in line or '0x0D' in line:
                            self.commit_count += 1
            except Exception as e:
                self.connected = False
                self.write_line(f't_wall={time.time():.3f} # NOTE '
                                f'[recorder] serial lost: {e}')
                try:
                    ser.close()
                except Exception:
                    pass
                time.sleep(2)

    def annotate(self, text):
        self.note_count += 1
        self.write_line(f't_wall={time.time():.3f} # NOTE {text}')

    def status_loop(self):
        """Print a live activity line to stderr so the user can see bus
        events (esp. display commits) arriving in real time. Helps catch
        missed button presses: if you press a button and the commit count
        doesn't tick up, the press didn't register."""
        spinner = '|/-\\'
        si = 0
        last_commit = -1
        while self.running:
            now = time.time()
            since = now - self.last_event_wall if self.last_event_wall else 999
            # A recent bus event (within 0.4s) flashes the indicator bright.
            if self.commit_count != last_commit:
                flash = '<<< EVENT'   # a display commit just landed
                last_commit = self.commit_count
            elif since < 0.4:
                flash = ' < bus'      # non-commit bus traffic
            else:
                flash = ''
            conn = 'CONN' if self.connected else 'wait'
            si = (si + 1) % len(spinner)
            # \r rewrites the same line; pad to clear leftovers.
            sys.stderr.write(
                f'\r  [{spinner[si]}] {conn}  events={self.line_count:<5d} '
                f'commits={self.commit_count:<4d} notes={self.note_count:<3d} '
                f'{flash:<10s}')
            sys.stderr.flush()
            time.sleep(0.15)

    def close(self):
        self.running = False
        time.sleep(0.2)
        with self.lock:
            self.f.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='Serial port (default: auto-detect)')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--out', default=None,
                   help='Output log path (default: session_HHMMSS.log)')
    args = p.parse_args()

    port = args.port or guess_port()
    if not port:
        print("No serial port found. Plug in the Pico or pass --port.")
        sys.exit(1)
    out = args.out or time.strftime('session_%H%M%S.log')

    rec = Recorder(port, args.baud, out)
    t = threading.Thread(target=rec.serial_loop, daemon=True)
    t.start()
    st = threading.Thread(target=rec.status_loop, daemon=True)
    st.start()

    print(f"Recording {port} -> {out}")
    print("Type a note and press Enter to timestamp it into the log.")
    print("The status line below shows live activity — 'commits' ticks up on")
    print("each display update, so you can see every press land (or notice a")
    print("miss). Ctrl-C (or type 'q' + Enter) to stop.\n")

    try:
        while True:
            try:
                note = input()
            except EOFError:
                break
            note = note.strip()
            if note.lower() in ('q', 'quit', 'exit'):
                break
            if note:
                rec.annotate(note)
                # Newline first so the note echo lands above the live status
                # line instead of overwriting it.
                sys.stderr.write('\n')
                print(f"  [noted @ {time.strftime('%H:%M:%S')}] {note}")
    except KeyboardInterrupt:
        pass
    finally:
        rec.close()
        print(f"\nStopped. {rec.line_count} bus lines, "
              f"{rec.note_count} notes -> {out}")
        print(f"Now run:  python3 pr53_session.py {out}")


if __name__ == '__main__':
    main()
