#!/usr/bin/env python3
"""
pr53_campaign.py — Guided step-wise segment mapping for SX-PR53.

Reads live v15 event log from the RP2350, walks you through a scripted
sequence of piano actions ("press CHORD ON now", "play C major on
keyboard", "press TEMPO UP"), auto-captures state before/after each step,
diffs the CGRAM bits, and saves each diff to mapping.csv with a
sensible pre-filled label.

Workflow:
    1. Pick a campaign from the dropdown
    2. Click "Start"
    3. Do what the on-screen instruction says on the piano
    4. Click "Capture" (or press SPACE) when the display has settled
    5. Confirm/edit the auto-suggested label, click Save & Next
    6. Repeat until campaign is done

Campaigns cover the natural mapping targets on this piano:
    - chord_types_on_C          Map Maj/min/7/dim/aug etc. bits
    - chord_roots_maj           Map C/D/E/F/G/A/B letter bits
    - tempo_step_from_current   Map tempo 7-segs by stepping +1 BPM
    - bargraph_part1_sweep      Map bargraph 1 by adjusting its volume
    - shaped_labels_toggle      Map RIGHT/LEFT/RHYTHM etc. by mode switch

You can add your own campaigns by editing CAMPAIGNS at the top of the file.

Dependencies: pyserial (pip install pyserial). tkinter is stdlib.
Firmware: expects v15 event log format (writes only, w/ read filtering).
Output: appends to mapping.csv, same schema as pr53_map.py.
"""
import argparse
import csv
import os
import re
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


# ============================================================
# CAMPAIGN DEFINITIONS
# ============================================================
# Each campaign is a list of steps. Each step has:
#   'action'  : human-readable instruction shown on screen
#   'label'   : pre-filled label for the diff that will result
#   'notes'   : optional hint text
# The first step of every campaign is implicitly the "baseline" —
# whatever state the piano is in when you click Start is captured as A,
# then step 1's B is captured after you do step 1's action.

CAMPAIGNS = {
    'chord_single_note_roots': {
        'description': 'Chord recognition: press single notes, watch chord display',
        'setup': ('Enable Auto-Play Chord (single-finger mode if available). '
                  'Piano decides which chord to play from one note. '
                  'Edit the label field for each step to record what chord you '
                  'think was displayed (e.g. "chord_C_maj", "chord_D_min").'),
        'steps': [
            {'action': 'Press single note C (release everything first)',   'label': 'chord_played_C'},
            {'action': 'Press single note C# / Db',                         'label': 'chord_played_C#'},
            {'action': 'Press single note D',                               'label': 'chord_played_D'},
            {'action': 'Press single note D# / Eb',                         'label': 'chord_played_D#'},
            {'action': 'Press single note E',                               'label': 'chord_played_E'},
            {'action': 'Press single note F',                               'label': 'chord_played_F'},
            {'action': 'Press single note F# / Gb',                         'label': 'chord_played_F#'},
            {'action': 'Press single note G',                               'label': 'chord_played_G'},
            {'action': 'Press single note G# / Ab',                         'label': 'chord_played_G#'},
            {'action': 'Press single note A',                               'label': 'chord_played_A'},
            {'action': 'Press single note A# / Bb',                         'label': 'chord_played_A#'},
            {'action': 'Press single note B',                               'label': 'chord_played_B'},
            {'action': 'Release all keys (back to no chord)',               'label': 'chord_none'},
        ],
    },

    'chord_two_note_variations': {
        'description': 'Chord recognition: two-note inputs to trigger non-major chord types',
        'setup': ('Single-finger chord mode usually treats extra notes as chord-type '
                  'modifiers. Try each pair below and note what chord type appears '
                  '(min, 7, min7, dim, etc.). Edit labels to match observed.'),
        'steps': [
            {'action': 'Press C + Bb (black key just below root)',   'label': 'chord_C_plus_flat7'},
            {'action': 'Press C + Eb (black key minor 3rd)',         'label': 'chord_C_plus_flat3'},
            {'action': 'Press C + Bb + Eb together',                 'label': 'chord_C_plus_flat3_flat7'},
            {'action': 'Press C + F# (tritone / dim)',               'label': 'chord_C_plus_tritone'},
            {'action': 'Press C + G# (aug 5th)',                     'label': 'chord_C_plus_sharp5'},
            {'action': 'Release all keys',                           'label': 'chord_none_after_variations'},
        ],
    },

    'chord_types_on_C': {
        'description': 'Chord types on C root (fingered mode — MAY NOT WORK on single-finger)',
        'setup': ('Only useful if your piano has a "fingered chord" mode where '
                  'YOU choose the chord notes exactly. If it uses chord recognition '
                  '(one note = piano decides), use chord_single_note_roots instead.'),
        'steps': [
            {'action': 'Play a C major chord (C-E-G)',    'label': 'chord_C_maj'},
            {'action': 'Play a C minor chord (C-Eb-G)',   'label': 'chord_C_min'},
            {'action': 'Play a C 7 chord (C-E-G-Bb)',     'label': 'chord_C_7'},
            {'action': 'Play a C maj7 chord (C-E-G-B)',   'label': 'chord_C_maj7'},
            {'action': 'Play a C min7 chord (C-Eb-G-Bb)', 'label': 'chord_C_min7'},
            {'action': 'Play a C dim chord (C-Eb-Gb)',    'label': 'chord_C_dim'},
            {'action': 'Play a C aug chord (C-E-G#)',     'label': 'chord_C_aug'},
            {'action': 'Play a C sus4 chord (C-F-G)',     'label': 'chord_C_sus4'},
            {'action': 'Release all keys (back to no chord)', 'label': 'chord_none'},
        ],
    },

    'chord_roots_maj': {
        'description': 'Chord root note letters (C-B, all major)',
        'setup': 'Enable Auto-Play Chord mode. Start on the play screen.',
        'steps': [
            {'action': 'Play C major (C-E-G)',    'label': 'chord_root_C'},
            {'action': 'Play D major (D-F#-A)',   'label': 'chord_root_D'},
            {'action': 'Play E major (E-G#-B)',   'label': 'chord_root_E'},
            {'action': 'Play F major (F-A-C)',    'label': 'chord_root_F'},
            {'action': 'Play G major (G-B-D)',    'label': 'chord_root_G'},
            {'action': 'Play A major (A-C#-E)',   'label': 'chord_root_A'},
            {'action': 'Play B major (B-D#-F#)',  'label': 'chord_root_B'},
        ],
    },

    'tempo_step_from_current': {
        'description': 'Tempo 7-segment digits by stepping +1 BPM',
        'setup': 'Set tempo to whatever value. Note the starting value; each step is +1.',
        'steps': [
            {'action': f'Press TEMPO UP once (+1)', 'label': f'tempo_step_{i:02d}'}
            for i in range(1, 21)  # 20 successive +1 presses
        ],
    },

    'tempo_hundreds_boundary': {
        'description': 'Cross hundreds boundary (99→100) to identify hundreds digit',
        'setup': 'Set tempo to 99 using TEMPO DOWN first if needed.',
        'steps': [
            {'action': 'Press TEMPO UP (99→100)',  'label': 'tempo_99_to_100'},
            {'action': 'Press TEMPO UP (100→101)', 'label': 'tempo_100_to_101'},
            {'action': 'Press TEMPO DOWN (101→100)', 'label': 'tempo_101_to_100'},
            {'action': 'Press TEMPO DOWN (100→99)',  'label': 'tempo_100_to_99'},
        ],
    },

    'bargraph_part_sweep_10steps': {
        'description': 'Sweep ONE part\'s volume through 10 known +1 steps',
        'setup': ('Pick a part (1-8), get to it in the volume settings. '
                  'Set volume to a known LOW value (like 100). Note which '
                  'part you\'re on — edit the labels below to match, e.g. '
                  'partN_vol_100_to_101 if you want to be specific.'),
        'steps': [
            {'action': f'Press volume UP once (+1)',
             'label': f'part_vol_step_{i:02d}'}
            for i in range(1, 11)
        ],
    },

    'bargraph_tens_boundary': {
        'description': 'Cross a bargraph tens boundary — identify tens digit position',
        'setup': ('Pick a part. Get its volume to a value ending in 9 (say 109 '
                  'or 119). Then walk it up through the tens boundary and back. '
                  'The diffs will show the tens digit position.'),
        'steps': [
            {'action': 'Volume UP once (crosses tens boundary X9→(X+1)0)',
             'label': 'tens_boundary_up'},
            {'action': 'Volume UP once (typical +1)',
             'label': 'after_tens_+1'},
            {'action': 'Volume UP once (typical +1)',
             'label': 'after_tens_+2'},
            {'action': 'Volume DOWN once (typical -1)',
             'label': 'after_tens_-1'},
            {'action': 'Volume DOWN once (typical -1)',
             'label': 'after_tens_-2'},
            {'action': 'Volume DOWN once (crosses back (X+1)0→X9)',
             'label': 'tens_boundary_down'},
        ],
    },

    'bargraph_number_5step_walk': {
        'description': 'Short 5-step +1 walk to identify a part\'s digit char/col',
        'setup': ('Get on the volume screen for the part you want to map. '
                  'Set it to a value ending in 4 or 5 so you cover a few '
                  'digit transitions (like 44→45→46→47→48→49).'),
        'steps': [
            {'action': f'Volume UP once', 'label': f'partN_step_{i:02d}'}
            for i in range(1, 6)
        ],
    },

    'bargraph_meter_full_sweep': {
        'description': 'Bar meter mapping — sweep from empty to full for one part',
        'setup': ('Pick a part. Set volume to 0 (all bars off). Baseline. '
                  'Then step up in units that each add ONE bar to the meter. '
                  'You may need to experiment; on many Technics units, '
                  'bar 1 lights at ~1/5 of max, bar 2 at ~2/5, etc.'),
        'steps': [
            {'action': f'Increase volume until 1st bar lights', 'label': 'meter_bar_1'},
            {'action': f'Increase volume until 2nd bar lights', 'label': 'meter_bar_2'},
            {'action': f'Increase volume until 3rd bar lights', 'label': 'meter_bar_3'},
            {'action': f'Increase volume until 4th bar lights', 'label': 'meter_bar_4'},
            {'action': f'Increase volume until 5th bar lights', 'label': 'meter_bar_5'},
        ],
    },

    'bargraph_part_locate': {
        'description': 'Identify which CGRAM char holds each part\'s bargraph',
        'setup': ('Move volume up/down ONCE on each of the 8 parts in turn. '
                  'Each diff should show one part\'s digit change. This '
                  'quickly identifies which CGRAM char belongs to each part.'),
        'steps': [
            {'action': f'Adjust Part 1 volume by 1 step',  'label': 'locate_part_1'},
            {'action': f'Adjust Part 2 volume by 1 step',  'label': 'locate_part_2'},
            {'action': f'Adjust Part 3 volume by 1 step',  'label': 'locate_part_3'},
            {'action': f'Adjust Part 4 volume by 1 step',  'label': 'locate_part_4'},
            {'action': f'Adjust Part 5 volume by 1 step',  'label': 'locate_part_5'},
            {'action': f'Adjust Part 6 volume by 1 step',  'label': 'locate_part_6'},
            {'action': f'Adjust Part 7 volume by 1 step',  'label': 'locate_part_7'},
            {'action': f'Adjust Part 8 volume by 1 step',  'label': 'locate_part_8'},
        ],
    },

    'shaped_labels_toggle': {
        'description': 'Shaped-electrode labels (RIGHT, LEFT, RHYTHM, etc.)',
        'setup': 'Play screen, no menus.',
        'steps': [
            {'action': 'Select RIGHT 1 mode',       'label': 'label_RIGHT1_on'},
            {'action': 'Select LEFT mode',          'label': 'label_LEFT_on'},
            {'action': 'Return to RIGHT 1 mode',    'label': 'label_RIGHT1_back'},
            {'action': 'Start rhythm (RHYTHM on)',  'label': 'label_RHYTHM_playing'},
            {'action': 'Stop rhythm',               'label': 'label_RHYTHM_stopped'},
        ],
    },

    'transpose_arrows': {
        'description': 'TRANSPOSE box + up/down arrows (top-right of display)',
        'setup': ('Play screen. Transpose should be at 0 (no shift).'),
        'steps': [
            {'action': 'Press TRANSPOSE UP once (+1 semitone)',
             'label': 'transpose_up_1'},
            {'action': 'Press TRANSPOSE UP once (+2 semitones)',
             'label': 'transpose_up_2'},
            {'action': 'Press TRANSPOSE DOWN twice (back to 0)',
             'label': 'transpose_back_to_zero'},
            {'action': 'Press TRANSPOSE DOWN once (-1 semitone)',
             'label': 'transpose_down_1'},
            {'action': 'Press TRANSPOSE UP once (back to 0)',
             'label': 'transpose_return_to_zero'},
        ],
    },

    'transpose_note_names': {
        'description': 'TRANSPOSE note-name readout (piano shows target note as you shift)',
        'setup': ('Play screen, transpose at 0. This piano displays the TARGET '
                  'note name in the transpose box as you shift. Walk +1 semitone '
                  'at a time from C up a full octave to capture each note-name '
                  'glyph (C, C#, D ... B, C). Each step both toggles the arrow '
                  'AND changes the note letter, so expect arrow bits (shared) '
                  'plus letter bits (unique per note). Edit labels if your '
                  'starting note differs.'),
        'steps': [
            {'action': 'TRANSPOSE UP: 0 → +1 (target C#/Db)', 'label': 'xpose_note_C#'},
            {'action': 'TRANSPOSE UP: +1 → +2 (target D)',    'label': 'xpose_note_D'},
            {'action': 'TRANSPOSE UP: +2 → +3 (target D#/Eb)','label': 'xpose_note_D#'},
            {'action': 'TRANSPOSE UP: +3 → +4 (target E)',    'label': 'xpose_note_E'},
            {'action': 'TRANSPOSE UP: +4 → +5 (target F)',    'label': 'xpose_note_F'},
            {'action': 'TRANSPOSE UP: +5 → +6 (target F#/Gb)','label': 'xpose_note_F#'},
            {'action': 'TRANSPOSE UP: +6 → +7 (target G)',    'label': 'xpose_note_G'},
            {'action': 'TRANSPOSE UP: +7 → +8 (target G#/Ab)','label': 'xpose_note_G#'},
            {'action': 'TRANSPOSE UP: +8 → +9 (target A)',    'label': 'xpose_note_A'},
            {'action': 'TRANSPOSE UP: +9 → +10 (target A#/Bb)','label': 'xpose_note_A#'},
            {'action': 'TRANSPOSE UP: +10 → +11 (target B)',  'label': 'xpose_note_B'},
            {'action': 'TRANSPOSE UP: +11 → +12 (target C)',  'label': 'xpose_note_C_oct'},
            {'action': 'TRANSPOSE DOWN x12 (back to 0)',      'label': 'xpose_note_back_to_zero'},
        ],
    },

    'midi_mode_indicator': {
        'description': 'MIDI symbol (top-middle, left of chord box)',
        'setup': ('Play screen. Find the control that enables MIDI mode on this '
                  'piano (may be a MIDI/FUNCTION menu, or a mode where the MIDI '
                  'symbol appears top-middle left of the chord box). Baseline is '
                  'captured with MIDI OFF. Isolate the single shaped MIDI '
                  'electrode bit by toggling it on and back off.'),
        'steps': [
            {'action': 'Enable MIDI mode (MIDI symbol appears)',  'label': 'midi_on'},
            {'action': 'Disable MIDI mode (MIDI symbol clears)',  'label': 'midi_off'},
            {'action': 'Enable MIDI mode again (confirm same bit)','label': 'midi_on_confirm'},
        ],
    },

    'menu_page_arrows': {
        'description': 'MENU/PAGE box + up/down arrows (top-right, above TRANSPOSE)',
        'setup': ('Enter a multi-page MENU/FUNCTION screen so PAGE navigation is '
                  'live. The top-right segmented box shows MENU/PAGE with up/down '
                  'arrows indicating whether more pages exist above/below. Walk '
                  'through pages to toggle the arrow bits. NOTE: menu content in '
                  'the DDRAM text area will also change — the arrow bits are the '
                  'shaped electrodes that repeat across page changes; the text '
                  'diff is contamination, ignore it when isolating arrows.'),
        'steps': [
            {'action': 'Enter menu, go to FIRST page (only DOWN arrow should show)',
             'label': 'page_first'},
            {'action': 'PAGE DOWN to a MIDDLE page (both arrows show)',
             'label': 'page_middle'},
            {'action': 'PAGE DOWN to the LAST page (only UP arrow should show)',
             'label': 'page_last'},
            {'action': 'PAGE UP back to a middle page',
             'label': 'page_middle_again'},
            {'action': 'Exit menu (both arrows clear)',
             'label': 'page_exit'},
        ],
    },

    'prog_arrows': {
        'description': 'PROG label + up/down arrows (right side, by page buttons)',
        'setup': ('Get to the screen where PROG (program/patch select) with its '
                  'up/down arrows is shown on the right edge alongside the page '
                  'buttons. Baseline with PROG shown. Step the program value '
                  'up/down to toggle the arrow bits. The PROG label itself is a '
                  'persistent shaped electrode; the arrows are state-driven.'),
        'steps': [
            {'action': 'PROG UP once (program +1)',      'label': 'prog_up_1'},
            {'action': 'PROG UP once (program +2)',      'label': 'prog_up_2'},
            {'action': 'PROG DOWN once (-1)',            'label': 'prog_down_1'},
            {'action': 'PROG DOWN once (-1, back to start)', 'label': 'prog_down_2'},
        ],
    },

    'small_2digit_top': {
        'description': 'Small 2-digit 7-seg left of the TOP text line (shows "P1" etc.)',
        'setup': ('This is the small 2-digit readout to the LEFT of the top text '
                  'line — user reports it sometimes shows a "P" prefix (like P1). '
                  'Likely a program/bank/part number. Get it onto a screen where '
                  'this number changes, set it to a known LOW value, then step +1 '
                  'through a units-and-tens range to map both digit positions. '
                  'Watch whether the left character is a real 7-seg "P" glyph or a '
                  'shaped label.'),
        'steps': [
            {'action': f'Increment the top-left number by 1',
             'label': f'top2_step_{i:02d}'}
            for i in range(1, 13)  # 12 steps to cross at least one tens boundary
        ],
    },

    'small_2digit_bottom': {
        'description': 'Small 2-digit 7-seg left of the BOTTOM text line',
        'setup': ('The small 2-digit readout to the LEFT of the bottom text line. '
                  'Get it onto a screen where it changes, set a known LOW value, '
                  'step +1 across a tens boundary to map both digit positions.'),
        'steps': [
            {'action': f'Increment the bottom-left number by 1',
             'label': f'bot2_step_{i:02d}'}
            for i in range(1, 13)
        ],
    },

    'chord_types_recognizer': {
        'description': 'Chord TYPE indicators via AUTO PLAY CHORD recognition on C root',
        'setup': ('Enable AUTO PLAY CHORD. Per the manual this piano recognizes '
                  'many chord qualities on each root (C used as example): C, C7, '
                  'CM7, Caug, Cm, Cm7, Cdim, Csus4, C6, etc. Keep the ROOT fixed '
                  'at C throughout so only the TYPE indicator bits change — root '
                  'letter (C5 c0) stays constant, isolating the quality glyphs '
                  '(maj/min/7/dim/aug/sus/6...). Play the actual chord voicings '
                  'below; edit labels if a given voicing displays a different '
                  'type than expected.'),
        'steps': [
            {'action': 'Play C major (C-E-G) — type: (none/maj)', 'label': 'ctype_C_maj'},
            {'action': 'Play C7 (C-E-G-Bb) — type: 7',            'label': 'ctype_C_7'},
            {'action': 'Play CM7 (C-E-G-B) — type: M7',           'label': 'ctype_C_M7'},
            {'action': 'Play Cm (C-Eb-G) — type: m',              'label': 'ctype_C_m'},
            {'action': 'Play Cm7 (C-Eb-G-Bb) — type: m7',         'label': 'ctype_C_m7'},
            {'action': 'Play Cdim (C-Eb-Gb) — type: dim',         'label': 'ctype_C_dim'},
            {'action': 'Play Caug (C-E-G#) — type: aug',          'label': 'ctype_C_aug'},
            {'action': 'Play Csus4 (C-F-G) — type: sus4',         'label': 'ctype_C_sus4'},
            {'action': 'Play C6 (C-E-G-A) — type: 6',             'label': 'ctype_C_6'},
            {'action': 'Play Cm7b5 (C-Eb-Gb-Bb) — type: m7b5',    'label': 'ctype_C_m7b5'},
            {'action': 'Release all keys (no chord / type clears)','label': 'ctype_C_none'},
        ],
    },

    'left_right_mode_clean': {
        'description': 'LEFT/RIGHT split-mode indicator — voice-contamination-free method',
        'setup': ('IMPORTANT: set BOTH keyboard zones (LEFT and RIGHT) to the '
                  'SAME voice first. This eliminates the 40+ bits of voice-name '
                  'CGRAM churn that made earlier LEFT/RIGHT captures unusable. '
                  'With identical voices, toggling the split mode should yield a '
                  'clean 1-2 bit diff = the pure mode-indicator electrode(s).'),
        'steps': [
            {'action': 'Confirm both zones = SAME voice. Select RIGHT mode.',
             'label': 'mode_RIGHT_clean'},
            {'action': 'Switch to LEFT mode (should be ~1-2 bit diff)',
             'label': 'mode_LEFT_clean'},
            {'action': 'Switch back to RIGHT mode',
             'label': 'mode_RIGHT_back_clean'},
        ],
    },
}


# ============================================================
# HD44780 STATE MACHINE (shared with pr53_display.py)
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
        self.last_event_time = 0.0


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
                    state.last_event_time = time.monotonic()
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
# Palette
# ============================================================

BG_APP    = '#0a1410'
BG_PANEL  = '#0e2e18'
LCD_BG    = '#0d3d1a'
LCD_ON    = '#c8ffb0'
LCD_OFF   = '#124a20'
LCD_GRID  = '#0a2812'
FG_LABEL  = '#8ac48a'
FG_STATUS = '#5f8f5f'
FG_INSTR  = '#ffeaa0'
DIFF_A    = '#ff7676'
DIFF_B    = '#77e0ff'
CELL_PX   = 5
CHAR_W    = 5 * CELL_PX
CHAR_H    = 8 * CELL_PX
CHAR_GAP  = 3


def bits_set(cg):
    return sum(bin(b & 0x1F).count('1') for b in cg)

def diff_bits(a, b):
    off = bytes((x & ~y) & 0x1F for x, y in zip(a, b))
    on  = bytes((~x & y) & 0x1F for x, y in zip(a, b))
    return off, on

def enumerate_bits(mask):
    for pos, byte in enumerate(mask):
        if not byte: continue
        ch, row = pos // 8, pos % 8
        for col in range(5):
            if (byte >> (4 - col)) & 1:
                yield ch, row, col

def bit_label(ch, row, col):
    return f'C{ch}:r{row}:c{col}'


def draw_char_grid(canvas, x, y, pat, on_col=LCD_ON, off_col=LCD_OFF, cell=CELL_PX):
    for row in range(8):
        b = pat[row] if row < len(pat) else 0
        for col in range(5):
            fill = on_col if (b >> (4 - col)) & 1 else off_col
            canvas.create_rectangle(
                x + col * cell, y + row * cell,
                x + (col + 1) * cell, y + (row + 1) * cell,
                fill=fill, outline='')


# ============================================================
# App
# ============================================================

class App:
    def __init__(self, root, state, mapping_path, settle_ms=800):
        self.state = state
        self.mapping_path = mapping_path
        self.settle_ms = settle_ms
        self.root = root
        self.campaign = None
        self.step_idx = 0
        self.baseline = None    # (ms, ddram, cgram) — updated after each accept
        self.pending = None     # captured snapshot waiting for accept
        self.pending_diff = None
        root.title("SX-PR53 Guided Mapping")
        root.configure(bg=BG_APP)
        root.resizable(False, False)
        root.bind('<space>', lambda e: self._on_capture())

        wrap = tk.Frame(root, bg=BG_APP, padx=20, pady=18)
        wrap.pack()

        # Campaign selector row
        top = tk.Frame(wrap, bg=BG_APP)
        top.pack(fill='x')
        tk.Label(top, text='Campaign:', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 11, 'bold')).pack(side='left')
        self.campaign_var = tk.StringVar(value=list(CAMPAIGNS.keys())[0])
        self.campaign_menu = ttk.Combobox(
            top, textvariable=self.campaign_var,
            values=list(CAMPAIGNS.keys()), state='readonly', width=32,
            font=('Helvetica', 11))
        self.campaign_menu.pack(side='left', padx=(8, 8))
        self.start_btn = tk.Button(top, text='Start / Reset',
                                   command=self._on_start,
                                   bg='#3a5a3a', fg='#fff',
                                   activebackground='#4a6a4a',
                                   font=('Helvetica', 11, 'bold'))
        self.start_btn.pack(side='left')

        # Campaign description
        self.campaign_info = tk.Label(
            wrap, text='', bg=BG_APP, fg=FG_STATUS,
            font=('Helvetica', 10), anchor='w', justify='left', wraplength=720)
        self.campaign_info.pack(fill='x', pady=(4, 12))

        # Live LCD
        tk.Label(wrap, text='Live LCD', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        lcd_w = 16 * CHAR_W + 15 * CHAR_GAP + 20
        lcd_h = 2 * CHAR_H + CHAR_GAP + 20
        self.lcd = tk.Canvas(wrap, width=lcd_w, height=lcd_h, bg=LCD_BG,
                             highlightthickness=2, highlightbackground='#000')
        self.lcd.pack(pady=(4, 10))

        # Instruction panel — big yellow text
        instr_frame = tk.Frame(wrap, bg=BG_PANEL, padx=16, pady=14,
                               highlightthickness=1,
                               highlightbackground='#0a2812')
        instr_frame.pack(fill='x', pady=(0, 10))
        tk.Label(instr_frame, text='Do this on the piano:', bg=BG_PANEL,
                 fg=FG_STATUS, font=('Helvetica', 10)).pack(anchor='w')
        self.instr_lbl = tk.Label(
            instr_frame, text='Pick a campaign and click Start',
            bg=BG_PANEL, fg=FG_INSTR,
            font=('Helvetica', 16, 'bold'), anchor='w', justify='left',
            wraplength=lcd_w)
        self.instr_lbl.pack(fill='x', pady=(4, 0))
        self.step_lbl = tk.Label(instr_frame, text='',
                                 bg=BG_PANEL, fg=FG_STATUS,
                                 font=('Helvetica', 9), anchor='w')
        self.step_lbl.pack(fill='x')

        # Capture controls
        cap_row = tk.Frame(wrap, bg=BG_APP)
        cap_row.pack(fill='x')
        self.cap_btn = tk.Button(cap_row, text='Capture (SPACE)',
                                 command=self._on_capture,
                                 bg='#2a4a5a', fg='#fff',
                                 activebackground='#3a5a6a',
                                 font=('Helvetica', 12, 'bold'),
                                 state='disabled', width=18)
        self.cap_btn.pack(side='left')
        self.skip_btn = tk.Button(cap_row, text='Skip step',
                                  command=self._on_skip,
                                  bg='#4a4a2a', fg='#fff',
                                  activebackground='#5a5a3a',
                                  font=('Helvetica', 11),
                                  state='disabled', width=12)
        self.skip_btn.pack(side='left', padx=(8, 0))

        # Diff summary
        self.diff_summary = tk.Label(
            wrap, text='', bg=BG_APP, fg=FG_STATUS,
            font=('Courier', 10), anchor='w', justify='left',
            wraplength=lcd_w)
        self.diff_summary.pack(fill='x', pady=(10, 4))
        cg_gap = 12
        cg_w = 8 * CHAR_W + 7 * cg_gap + 20
        cg_h = CHAR_H + 24
        self.diff_canvas = tk.Canvas(wrap, width=cg_w, height=cg_h,
                                     bg=BG_PANEL, highlightthickness=1,
                                     highlightbackground='#0a2812')
        self.diff_canvas.pack(pady=(0, 10))

        # Save controls
        save_row = tk.Frame(wrap, bg=BG_APP)
        save_row.pack(fill='x')
        tk.Label(save_row, text='Label:', bg=BG_APP, fg=FG_LABEL,
                 font=('Helvetica', 10, 'bold')).pack(side='left')
        self.label_entry = tk.Entry(save_row, width=40,
                                    bg='#122', fg='#dfd',
                                    insertbackground='#dfd',
                                    font=('Courier', 11))
        self.label_entry.pack(side='left', padx=(8, 8), fill='x', expand=True)
        self.save_btn = tk.Button(save_row, text='Save & Next',
                                  command=self._on_save_next,
                                  bg='#3a5a3a', fg='#fff',
                                  activebackground='#4a6a4a',
                                  font=('Helvetica', 11, 'bold'),
                                  state='disabled')
        self.save_btn.pack(side='right')

        self.status = tk.Label(wrap, text='ready', bg=BG_APP, fg=FG_STATUS,
                               font=('Courier', 10), anchor='w')
        self.status.pack(fill='x', pady=(8, 0))

        self._on_campaign_change()
        self.campaign_menu.bind('<<ComboboxSelected>>',
                                lambda e: self._on_campaign_change())
        self._render()

    # ---- Campaign lifecycle ----

    def _on_campaign_change(self):
        c = CAMPAIGNS[self.campaign_var.get()]
        text = (f"{c['description']}\n"
                f"Setup: {c['setup']}\n"
                f"{len(c['steps'])} steps total.")
        self.campaign_info.config(text=text)

    def _on_start(self):
        # Grab baseline now, walk into step 1.
        self.campaign = CAMPAIGNS[self.campaign_var.get()]
        self.step_idx = 0
        with self.state.lock:
            self.baseline = (
                int(self.state.last_event_time * 1000),
                bytes(self.state.state.ddram),
                bytes(self.state.state.cgram),
            )
        self.pending = None
        self.pending_diff = None
        self.diff_canvas.delete('all')
        self.diff_summary.config(text='baseline captured — begin step 1')
        self.status.config(text='campaign started', fg='#8f8')
        self._show_current_step()
        self.cap_btn.config(state='normal')
        self.skip_btn.config(state='normal')
        self.save_btn.config(state='disabled')

    def _show_current_step(self):
        if self.campaign is None or self.step_idx >= len(self.campaign['steps']):
            self.instr_lbl.config(text='Campaign complete 🎉')
            self.step_lbl.config(text='')
            self.cap_btn.config(state='disabled')
            self.skip_btn.config(state='disabled')
            return
        step = self.campaign['steps'][self.step_idx]
        self.instr_lbl.config(text=step['action'])
        self.step_lbl.config(
            text=f'Step {self.step_idx + 1} of {len(self.campaign["steps"])}'
                 f'  •  suggested label: {step["label"]}')

    def _on_capture(self):
        if self.baseline is None: return
        if self.step_idx >= len(self.campaign['steps']): return
        # Grab current state as the "after" of this step.
        with self.state.lock:
            self.pending = (
                int(self.state.last_event_time * 1000),
                bytes(self.state.state.ddram),
                bytes(self.state.state.cgram),
            )
        _, _, cga = self.baseline
        _, _, cgb = self.pending
        off_mask, on_mask = diff_bits(cga, cgb)
        self.pending_diff = (off_mask, on_mask)
        self._render_diff(cga, cgb, off_mask, on_mask)
        # Pre-fill suggested label
        suggested = self.campaign['steps'][self.step_idx]['label']
        self.label_entry.delete(0, tk.END)
        self.label_entry.insert(0, suggested)
        self.save_btn.config(state='normal')
        n_bits = bits_set(off_mask) + bits_set(on_mask)
        if n_bits == 0:
            self.status.config(
                text='no bits changed — try again or skip', fg='#c66')
        else:
            self.status.config(
                text=f'captured {n_bits} bit changes — review and save',
                fg='#8f8')

    def _on_skip(self):
        self.step_idx += 1
        self.pending = None
        self.pending_diff = None
        self.diff_canvas.delete('all')
        self.diff_summary.config(text='(step skipped)')
        self.label_entry.delete(0, tk.END)
        self.save_btn.config(state='disabled')
        self._show_current_step()

    def _on_save_next(self):
        label = self.label_entry.get().strip()
        if not label:
            self.status.config(text='enter a label first', fg='#c66'); return
        if self.pending is None or self.pending_diff is None:
            self.status.config(text='no capture pending', fg='#c66'); return
        ma, dda, cga = self.baseline
        mb, ddb, cgb = self.pending
        off_mask, on_mask = self.pending_diff
        self._append_to_mapping(label, off_mask, on_mask, ma, mb, dda, ddb)
        # Advance
        self.baseline = self.pending
        self.pending = None
        self.pending_diff = None
        self.step_idx += 1
        self.diff_canvas.delete('all')
        self.diff_summary.config(text=f'saved "{label}" — on to next step')
        self.label_entry.delete(0, tk.END)
        self.save_btn.config(state='disabled')
        self._show_current_step()

    def _append_to_mapping(self, label, off_mask, on_mask, ma, mb, dda, ddb):
        def txt(dd, off):
            return ''.join(chr(x) if 32 <= x < 127 else '.'
                           for x in dd[off:off+12])
        l1a, l2a = txt(dda, 0), txt(dda, 0x40)
        l1b, l2b = txt(ddb, 0), txt(ddb, 0x40)
        rows = []
        for (ch, r, c) in enumerate_bits(on_mask):
            rows.append({
                'bit': bit_label(ch, r, c), 'direction': 'ON',
                'label': label, 'A_l1': l1a, 'A_l2': l2a,
                'B_l1': l1b, 'B_l2': l2b, 'A_ms': ma, 'B_ms': mb})
        for (ch, r, c) in enumerate_bits(off_mask):
            rows.append({
                'bit': bit_label(ch, r, c), 'direction': 'OFF',
                'label': label, 'A_l1': l1a, 'A_l2': l2a,
                'B_l1': l1b, 'B_l2': l2b, 'A_ms': ma, 'B_ms': mb})
        if not rows:
            return
        header = ['bit', 'direction', 'label', 'A_l1', 'A_l2',
                  'B_l1', 'B_l2', 'A_ms', 'B_ms']
        new_file = not os.path.exists(self.mapping_path)
        with open(self.mapping_path, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=header)
            if new_file: w.writeheader()
            for r in rows: w.writerow(r)

    # ---- Rendering ----

    def _render_diff(self, cga, cgb, off_mask, on_mask):
        off_n = bits_set(off_mask)
        on_n = bits_set(on_mask)
        parts = [f'{on_n} bit(s) ON, {off_n} bit(s) OFF going baseline → step']
        if on_n:
            parts.append('  ON : ' + ' '.join(
                bit_label(*b) for b in enumerate_bits(on_mask)))
        if off_n:
            parts.append('  OFF: ' + ' '.join(
                bit_label(*b) for b in enumerate_bits(off_mask)))
        self.diff_summary.config(text='\n'.join(parts), fg=FG_LABEL)
        self.diff_canvas.delete('all')
        cg_gap = 12
        for ch in range(8):
            x = 10 + ch * (CHAR_W + cg_gap); y = 12
            self.diff_canvas.create_text(x + CHAR_W // 2, y - 2,
                                         text=str(ch), fill=FG_LABEL,
                                         font=('Helvetica', 8), anchor='s')
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

    def _render(self):
        with self.state.lock:
            ddram = bytes(self.state.state.ddram)
            cgram = bytes(self.state.state.cgram)
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
                # For live LCD in mapper we show text and skip CGRAM sprites
                # (they'd hide the useful DDRAM text visible)
                if b < 16:
                    continue
                ch = chr(b) if 32 <= b < 127 else '?'
                # Simple text placement instead of pixel font — just use tk
                # font at this size. Skip the pixel font here for simplicity.
                self.lcd.create_text(x + CHAR_W // 2, y + CHAR_H // 2,
                                     text=ch, fill=LCD_ON,
                                     font=('Courier', 14, 'bold'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='Serial port (default: auto-detect)')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--mapping', default='mapping.csv',
                   help='mapping.csv path (appended to)')
    args = p.parse_args()

    state = LiveState()
    def port_getter(): return args.port or guess_port()
    reader = threading.Thread(target=serial_reader,
                              args=(state, port_getter, args.baud),
                              daemon=True)
    reader.start()
    root = tk.Tk()
    App(root, state, args.mapping)
    root.mainloop()


if __name__ == '__main__':
    main()
