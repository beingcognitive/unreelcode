"""J. S. Bach, Prelude in C major, BWV 846, bars 1-19 (public domain), as (time, midi) note events.

Each bar is one five-note chord, broken as n1 n2 n3 n4 n5 n3 n4 n5, twice (16 sixteenths).
"""
NAMES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}


def m(s):
    return 12 * (int(s[-1]) + 1) + NAMES[s[:-1]]


CHORDS = [
    "C4 E4 G4 C5 E5", "C4 D4 A4 D5 F5", "B3 D4 G4 D5 F5", "C4 E4 G4 C5 E5",
    "C4 E4 A4 E5 A5", "C4 D4 F#4 A4 D5", "B3 D4 G4 D5 G5", "B3 C4 E4 G4 C5",
    "A3 C4 E4 G4 C5", "D3 A3 D4 F#4 C5", "G3 B3 D4 G4 B4", "G3 Bb3 E4 G4 C#5",
    "F3 A3 D4 A4 D5", "F3 Ab3 D4 F4 B4", "E3 G3 C4 G4 C5", "E3 F3 A3 C4 F4",
    "D3 F3 A3 C4 F4", "G2 D3 G3 B3 F4", "C3 E3 G3 C4 E4",
]
PATTERN = [0, 1, 2, 3, 4, 2, 3, 4] * 2


def notes(t0, bar):
    """[(t, midi, bar_index)] for all 19 bars; the last bar ends on its first half (n1..n5 then the chord rings)."""
    out = []
    six = bar / 16
    for b, ch in enumerate(CHORDS):
        ms = [m(x) for x in ch.split()]
        pat = PATTERN if b < len(CHORDS) - 1 else [0, 1, 2, 3, 4]
        for k, p in enumerate(pat):
            out.append((t0 + b * bar + k * six, ms[p], b))
    return out


def pitches():
    return sorted({m(x) for ch in CHORDS for x in ch.split()})


if __name__ == "__main__":
    n = notes(0, 2.7)
    print(len(n), "notes;", len(pitches()), "pitches:", pitches())
