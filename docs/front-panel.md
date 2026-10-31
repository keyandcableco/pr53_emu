# Front panel and display: what there is to decode

Every control on the SX-PR53's panel, by section, left to right, taken from
photos of the piano. Each section has a guided campaign in
`tools/pr53_campaign.py` (`panel_<section>`) that walks through its controls
and saves what each one changes on the glass to `mapping.csv`.

Never press **SET** (panel memory) or **RECORD / EASY REC** while mapping:
they overwrite the owner's stored data. The campaigns leave them out.

## The glass

What the original display shows, as far as the decoders know so far:

| Field | Drawn with | Decoded |
|---|---|---|
| Text line 1 and 2 (12 characters each): voice, rhythm, menu text | Character ROM | Yes, codes up to 0x7F. Codes above 0x7F (seen in the LCD test) have no glyphs yet |
| Tempo (3 digits) | CGRAM segments | Yes |
| Chord name (root, sharp/flat, type) | CGRAM segments | Root and flat/sharp: yes (C5 c0; accidental in C1 c0 rows 6-7). Type: not yet |
| Rhythm number in the group (1, 2, 3 ...) | CGRAM segments | Found at C6 c0 on the RHYTHM screen, standard 7-segment; not drawn yet |
| Transpose (note name, arrows) | CGRAM segments | Yes |
| Eight part meters (bars) | CGRAM segments | Yes, except Part 6 |
| Eight part numbers (3 digits) | CGRAM segments | Tens and ones; hundreds only on Part 8 |
| Two small 2-digit readouts left of the text lines | CGRAM segments | No |
| Shaped labels and arrows (RIGHT, LEFT, RHYTHM, MIDI, MENU/PAGE, PROG ...) | CGRAM segments | Partly |

The LCD test (`captures/lcd_test_mode_2026-10-31.log`) lit all 320 CGRAM
bits: 8 custom characters of 8 rows x 5 columns, placed at positions 12-15 of
each text line. Every one of those bits is a segment or label to account for.

### How the glass is encoded

What the captures so far show, and what lets most of the rest be inferred
instead of mapped bit by bit:

- **Each column of a custom character is one display cell.** Its rows are that
  cell's segments, in a fixed order: for digits and letters, rows 0-6 are
  a, b, f, g, c, e, d (the decoders' "bargraph" order; tempo uses rows 0-5 and
  7). Row 7 is often a separate indicator.
- **The chord root is one cell (C5 c0).** Letters are fixed segment sets:
  C {a,f}, D {a,c,d,e,f}, E {a,b,f,g}, F {b,f,g}, G {a,d,e,f,g},
  A {b,c,d,e,f,g}, B {a,b,c,d,f,g}. The accidental borrows the spare rows of
  the tempo hundreds cell (C1 c0): row 7 alone is a flat, rows 6+7 a sharp.
  The piano spells black keys Db, Eb, F#, Ab, Bb. The chord clears a couple of
  seconds after the keys are released.
- **The glass has screens.** The play screen shows the part meters and numbers
  (C0, C2-C7). Pressing a rhythm group briefly shows a RHYTHM screen (line 1
  "RHYTHM", line 2 the rhythm name, meters blank, the rhythm number in C6 c0).
  Menus show the menu name on line 1, the first item on line 2, meters blank,
  and the same few icon bits each time (C1 c3/c4 and row 6 of C2/C3): almost
  certainly the MENU/PAGE box and its arrows.

`tools/pr53_campaign_report.py` replays a campaign log and prints these
per-step bit changes; the step-by-step results are in
`captures/campaign_2026-10-31.log`.

## Controls

**Volume**
- MAIN VOLUME slider, RHYTHM VOLUME slider (with an LED). Analog; nothing on
  the glass expected.

**Play Style** (`panel_play_style`)
- SPLIT POINT (second label: INST ERASE), AUTO PLAY CHORD, KEYBOARD SPLIT,
  PIANO MODE, PIANO STYLIST, ONE TOUCH PLAY (second label under both: MUSIC STYLE SELECT).
  All but SPLIT POINT have LEDs.

**Composer** (`panel_composer`)
- RECORD, CHORD MAP, MEMORY (second label: COMPOSER LOAD). LEDs on each.
- METRONOME (LED).

**Rhythm Group** (`panel_rhythm_groups`)
- 8 & 16 BEAT, ROCK, SOUL & DISCO, BIG BAND & SWING, COUNTRY & WESTERN,
  SHOW TIME, LATIN, BALLAD, FUNK & FUSION, GOSPEL & BLUES, JAZZ COMBO,
  BALLROOM, MARCH & WALTZ, WORLD. LEDs on each.
- RHYTHM SELECT up/down.

**Rhythm controls** (`panel_rhythm_controls`)
- DEMO.
- MUSIC STYLE ARRANGER, VARIATION & MSA 1-4 (LEDs 1-4).
- FILL IN 1/2 (second labels: SEQUENCER RESET, COUNT INTRO), INTRO & ENDING 1/2
  (LEDs 1, 2 each).
- SYNCHRO START, START/STOP, TAP TEMPO, beat LEDs 1-4.

**Display area** (`panel_display_controls`, `panel_parts`)
- Left of the window: TEMPO up/down, OTHER PARTS/TRACKS.
- Right of the window: TRANSPOSE up/down, EXIT.
- Under the window, one up/down pair per part: DRUMS, ACCOMP 3, ACCOMP 2,
  ACCOMP 1, BASS, LEFT, RIGHT 2, RIGHT 1, with a MUTE bracket.
- BALANCE, EXECUTE, PAGE up/down, DISPLAY HOLD. Three LED pointers (▼)
  along this row.

**Sound Group** (`panel_sound_groups`)
- PIANO & E PIANO, GUITAR, STRINGS, VOCAL, BRASS, FLUTE, BASS, DRUM KITS,
  MALLET & ORCH PERC, WORLD PERC, ORGAN & ACCORDION, SAX, REED, SYNTH LEAD,
  SYNTH PAD, PERC & EFFECT. LEDs on each.
- SOUND SELECT up/down.
- PIANO: GRAND, UPRIGHT, ELECTRIC, MODERN. MIXTURES. TECHNI-CHORD.

**Conductor** (`panel_conductor`)
- LEFT SELECT, RIGHT 2, RIGHT 1 (LEDs).

**Sequencer and Menu** (`panel_menus`)
- Sequencer: EASY REC, MENU, PLAY (LEDs).
- Menu: SOUND SETTING, MIDI, MEMORY & CONTROL (second label: DISK LOAD) (LEDs).

**Effects** (`panel_effects`)
- SUSTAIN PEDAL, DIGITAL EFFECT, CHORUS, DIGITAL REVERB (LEDs).

**Panel Memory** (`panel_memory`)
- SET, 1-5 (LEDs). The campaign recalls 1-5 only.

**Elsewhere**: floppy disk drive (right end), General MIDI logo.

## Chords

Chord names come from the left hand with AUTO PLAY CHORD on.
`chord_roots_all12` plays all twelve roots (sharps included) as major chords,
and `chord_types_recognizer` holds the root at C and plays each chord type.
Together they separate the root letters, the sharp sign and the type suffixes.

## Service test modes

From the service manual's self-diagnostic table. Hold two keyboard keys while
switching on:

- **G4 + G5: LCD check.** Lights every CGRAM pixel and fills both lines with
  full blocks. PIANO & E PIANO then starts a scroll through the character set.
- **F4 + F5: control panel buttons and LED check.**
- **Two E keys: Wave ROM check** (sine-wave test tones; which E keys not checked).

The first G4 + G5 attempt only set up the display and went quiet; the second
worked. The key pairs are read from a small diagram in the manual.
