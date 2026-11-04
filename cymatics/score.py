# score.py: the one source of every
# sound you hear and grain you see.
# A note is a plate mode: mode k rings
# at f = F * k Hz, and its figure is
# every pair (a, b) with a*a + b*b == k.
# So there is no perfect fifth.
F = 16.48   # Hz per k (a 54 cm plate)
BPM = 96    # 4/4: a bar is 2.5 s

# notes as k (bass, pad: k / 2^n)
E2, E3, Gs3, B3 = 5, 10, 12.5, 15.25
Cs3, A3 = 8.5, 13.25
E4, Fs4, Gs4, A4 = 20, 22.5, 25, 26.5
B4, Cs4 = 30.5, 17
Cs5, D5, E5, Fs5 = 34, 36, 40, 45
Gs5, A5, B5 = 50, 53, 61
Cs6, E6 = 68, 80

# PLATE: struck metal. Shakes sand.
# (bar, beat, note, beats, velocity)
PLATE = [
    (1, 1, Gs4, 4, 1.0),
    (2, 1, E5, 4, .8),
    (3, 1, Cs5, 4, .8),
    (4, 1, B5, 4, .9),
    (5, 1, E5, 2, .7),
    (5, 3, Gs5, 2, .7),
    (6, 1, Cs6, 2, .8),
    (6, 3, B5, 2, .7),
    (7, 1, A5, 2, .8),
    (7, 3, E5, 2, .7),
    (8, 1, Fs5, 4, .8),
    # bar 9: rest. The sand settles.
    (10, 1, E6, 4, .35),
    (12, 1, B5, 4, .45),
    (13, 1, Cs6, 2, .6),
    (13, 3, E6, 2, .6),
    (15, 1, E5, 4, .7),
    (19, 1, Gs4, 2, .8),
    (19, 3, E5, 2, .7),
    (20, 1, Cs5, 2, .7),
    (20, 3, B5, 2, .8),
    (21, 1, E5, 8, .9),
]

# GLASS: a glass pad. Drives water.
CHORDS = {
    1: [], 3: [E3], 5: [E3, Gs3, B3],
    6: [Cs3, E3, Gs3], 7: [A3, Cs4, E4],
    8: [B3, E4, Fs4], 9: [], 10: [E3],
    11: [E3, E4], 12: [E3, Gs4],
    13: [E3, A4, Cs5],
    15: [E3, Gs3, B3],
    16: [Cs3, E3, Gs3],
    17: [A3, Cs4, E4],
    18: [B3, E4, Fs4],
    19: [E3, Gs3, B3],
    20: [A3, Cs4, E4],
    21: [E3, Gs3, B3, E4],
}

# BASS: a drone (heard, not seen)
BASS = {
    1: E2, 5: E2, 6: Cs3 / 2, 7: A3 / 2,
    8: B3 / 2, 9: None, 10: E2, 15: E2,
    16: Cs3 / 2, 17: A3 / 2, 18: B3 / 2,
    19: E2, 20: A3 / 2, 21: E2,
    23: None,
}

# loudness of pad and bass, per bar
DYN = {1: .7, 5: .55, 8: .45, 9: 0,
       10: .6, 11: .7, 12: .7, 13: 1.0,
       15: .4, 19: .7, 21: .85, 23: .3}
