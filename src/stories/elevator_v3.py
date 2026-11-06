"""
Prototype « elevator » v3 : Bounce est dans un ascenseur avec un homme pressé qui veut l'étage 9. Au
premier rebond, Bounce s'écrase sur le tableau et allume tous les étages d'un coup. À chaque arrêt, des
années passent (le calendrier du palier saute, la barbe de l'homme fait un bond) et l'homme fait autre
chose, en une réplique. Au 9, au ralenti, Bounce frappe « fermer » : les portes lui claquent au nez.
Redescente, la dame du 3 a vieilli (« Still taking the stairs! »). Le vieil homme garde le tableau avec sa
canne : duel. Le 9 : son pot de départ en retraite. « Happy retirement! » — « I just got here. » — et
Bounce rallume le 1 : les portes se referment, il redescend avec le vieillard.

Tout est écrit dans le temps « monde » ; un ralenti (L1) étire 0,42 s de monde sur 1,4 s de vidéo. Les
contacts durs sont posés à leurs instants exacts : l'audio est le même quel que soit le nombre d'images par
seconde. La résolution de la config est libre (aperçu 540×960).

    python3 src/stories/elevator_v3.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import font
from PIL import Image, ImageDraw, ImageChops
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/elevator/bank3"

# ------------------------------------------------------------------ voix des personnages (banque vérifiée par whisper)
BANK_FILES = {"Come on, come on!": "come.wav", "I'll take the stairs.": "stairs.wav", "No!": "noo.wav",
              "Still taking the stairs!": "still.wav", "Happy retirement!": "party.wav",
              "I just got here.": "got.wav", "Seriously?!": "seriously.wav", "Excuse me!": "excuse.wav",
              "Wait!": "wait.wav", "Working late?": "working.wav", "Oh... come on.": "weary.wav", "Nine!": "nine.wav",
              "Hi, Santa!": "santa.wav", "What year is it?": "year.wav", "Not today!": "nottoday.wav"}
BANK = {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr = w.getnframes(), w.getframerate()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if fr != SR:
        idx = np.arange(0, len(x) - 1, fr / SR)
        x = np.interp(idx, np.arange(len(x)), x)
    return x


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK_FILES:
        if text not in BANK:
            BANK[text] = _read(os.path.join(os.environ.get("ELEVATOR_BANK", BANK_DIR), BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(os.environ.get("ELEVATOR_BANK", BANK_DIR),
                         "hero_%s_%s_%s.wav" % (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"]))
    if key not in _hero_memo and os.path.exists(cache):
        _hero_memo[key] = _read(cache)
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if len(v) / SR <= 0.70:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# l'accroche : posée par ce thème à HOOK_T (après le premier « Bounce »), finie avant 2,0 s
HOOK_T = 1.0
_orig_hook_audio = base.hook_audio
_hook_memo = {}


def hook_clip(cfg):
    key = cfg.get("hook_text")
    if key not in _hook_memo:
        v = _orig_hook_audio(cfg)
        if v is not None:
            v = np.asarray(v, float)
            e = np.abs(v)
            idx = np.where(e > 0.04 * e.max())[0]
            if len(idx):
                v = v[max(0, idx[0] - int(0.01 * SR)):min(len(v), idx[-1] + int(0.03 * SR))].copy()
            f = max(cfg.get("hook_speed", 1.05), len(v) / SR / cfg.get("hook_max_s", 0.95))
            v = base.pitch(v, f)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ le temps : ralenti (L1)
SLO_A = 38.25
SLO_V = 1.40
SLO_F = 0.30
SLO_W = SLO_V * SLO_F
SHIFT = SLO_V - SLO_W


def world(tv):
    if tv < SLO_A:
        return tv
    if tv < SLO_A + SLO_V:
        return SLO_A + (tv - SLO_A) * SLO_F
    return tv - SHIFT


def video(tw):
    if tw < SLO_A:
        return tw
    if tw < SLO_A + SLO_W:
        return SLO_A + (tw - SLO_A) / SLO_F
    return tw + SHIFT


END_W = 61.47          # fin (vidéo 62,45 s)
ISSUE_W = 57.55        # les portes du 9 finissent de s'ouvrir sur la fête

# ------------------------------------------------------------------ géométrie (écran 1080×1920)
W, H = 1080, 1920
G = 2600.0
R = 100.0
CEIL = 530.0                  # face du plafond
FLOOR = 1430.0                # tapis / sol (Bounce y touche)
CY = CEIL + R
FY = FLOOR - R
DOOR = (420.0, 740.0, 650.0, FLOOR)
LAND_DX = 70.0                           # les paliers sont dessinés pour 440–800, posés 40 px plus à gauche
PAN = (100.0, 300.0, 580.0, 1400.0)      # le tableau, deux colonnes (boutons de 88 px)
PX = PAN[1] + R
BTN_R = 44.0
DIAL = (540.0, 212.0, 172.0)             # le grand cadran d'étage, en haut (centre x, y, rayon)
STEEL_X = 560.0                          # sol nu (métal), à côté de l'homme
BRIEF_X = 432.0                          # Bounce contre la mallette-bouclier (centre)
RUG = (290.0, 470.0)
SUIT_FY = 1480.0
SUIT_Q = 1.18
PEOPLE_FY = 1424.0
PEOPLE_S = 1.2
CEIL_X = 430.0
ROWS = [650.0, 785.0, 920.0, 1055.0, 1190.0, 1325.0]
COLS = (158.0, 245.0)
BTN = {8: (COLS[0], ROWS[0]), 9: (COLS[1], ROWS[0]), 6: (COLS[0], ROWS[1]), 7: (COLS[1], ROWS[1]),
       4: (COLS[0], ROWS[2]), 5: (COLS[1], ROWS[2]), 2: (COLS[0], ROWS[3]), 3: (COLS[1], ROWS[3]),
       1: (COLS[1], ROWS[4]), "open": (COLS[0], ROWS[5]), "close": (COLS[1], ROWS[5])}


def btn_y(n):
    return BTN[n][1]


# couleurs
BG = (8, 8, 12)
WALLC = (54, 58, 72)
WALLD = (38, 41, 52)
STEELC = (120, 126, 142)
STEELL = (150, 156, 172)
CEILC = (34, 36, 46)
LIGHT = (236, 232, 206)
RUGC = (122, 46, 58)
RUGD = (92, 32, 44)
FLOORC = (44, 46, 56)
NAVY = (46, 62, 120)
NAVYD = (34, 46, 92)
SKIN = (226, 186, 150)
TIE = (206, 44, 56)
BRIEFC = (128, 82, 46)
LIT = (255, 214, 90)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def lerp(a, b, k):
    return a + (b - a) * k


class KF:
    def __init__(self, v0, keys=()):
        self.keys = [(-1e9, v0)] + sorted(keys, key=lambda k: k[0])
        self.ts = [k[0] for k in self.keys]

    def __call__(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        if i >= len(self.keys) - 1:
            return self.keys[-1][1]
        t0, v0 = self.keys[i]
        t1, v1 = self.keys[i + 1]
        if t0 < -1e8:
            return v0
        return lerp(v0, v1, smooth((t - t0) / max(1e-6, t1 - t0)))


def hop(t, hops):
    y = 0.0
    for (t0, h) in hops:
        T = 2 * math.sqrt(2 * h / G)
        u = t - t0
        if 0 <= u <= T:
            y = max(y, h - 0.5 * G * (u - T / 2) ** 2)
    return y


# ------------------------------------------------------------------ le plan (temps monde)
# contacts durs : (t, genre, argument). pan = tableau (allume un bouton ; "cascade" = tous d'un coup),
# ceil = plafonnier, disp = sous l'afficheur (le fait sauter), steel = sol nu près de l'homme,
# brief = la mallette, cane = la canne (argument : hauteur du contact)
HITS = [
    (0.25, "pan", "cascade"), (2.15, "pan", "close"),
    (4.45, "ceil", 0), (5.20, "steel", 0),
    (7.00, "ceil", 0), (7.75, "pan", 5),
    (9.75, "ceil", 0), (10.50, "steel", 0), (11.40, "brief", 0), (12.15, "pan", 1),
    (13.95, "ceil", 0), (14.70, "steel", 0),
    (17.40, "steel2", 0), (18.15, "steel2", 0), (18.90, "ceil", 0),
    (20.85, "pan", 6), (21.75, "steel", 0),
    (23.65, "ceil", 0),
    (26.90, "pan", "open"),
    (29.60, "disp", 0),
    (32.95, "steel", 0), (33.70, "ceil", 0),
    (36.05, "ceil", 0), (36.80, "steel", 0),
    (38.75, "pan", "close"), (40.20, "pan", 3), (41.00, "ceil", 0), (41.75, "steel", 0),
    (43.25, "ceil", 0), (44.05, "pan", 3),
    (46.85, "steel", 0), (47.60, "ceil", 0), (48.40, "steel", 0), (49.60, "ceil", 0),
    (50.45, "cane", 1250.0), (51.20, "cane", 1100.0), (53.40, "cane", 820.0), (54.20, "ceil", 0),
    (55.00, "cane", 1010.0), (55.75, "cane", 1290.0),
    (60.47, "pan", 1),
]
# contacts mous imposés (t, x, creux)
SOFT_FIX = [(38.20, 430.0, 22.0), (56.30, 420.0, 26.0), (56.90, 430.0, 30.0), (57.50, 418.0, 26.0),
            (58.15, 432.0, 30.0), (58.80, 420.0, 26.0), (59.40, 432.0, 28.0), (59.95, 420.0, 26.0),
            (61.00, 430.0, 26.0), (61.55, 420.0, 24.0)]
# arrêts : (étage, ding, année au calendrier du palier)
STOPS = [(2, 0.85, 2026), (3, 5.90, 2029), (4, 15.00, 2034), (5, 19.60, 2040), (6, 23.20, 2047),
         (7, 31.10, 2053), (8, 34.00, 2058), (9, 37.75, 2064), (3, 44.30, 2071), (1, 49.00, None),
         (9, 57.10, 2079)]
JOLTS = [s_[1] for s_ in STOPS]
DOOR_KEYS = [(1.05, 0), (1.35, 1), (2.15, 1), (2.25, 0),                 # le 2 : claquée au nez du joggeur
             (5.95, 0), (6.30, 1), (9.90, 1), (10.50, 0),                 # le 3 : la dame
             (15.05, 0), (15.40, 1), (18.00, 1), (18.60, 0),              # le 4 : il tente de sortir
             (19.65, 0), (19.85, 1), (19.95, 1), (20.15, 0),              # le 5 : arrêt éclair
             (23.25, 0), (23.65, 1), (26.10, 1), (26.90, 0.35), (27.25, 1), (28.40, 1), (29.00, 0),   # la nuit
             (31.15, 0), (31.50, 1), (33.00, 1), (33.50, 0),              # le 7 (après le faux 9) : l'hiver
             (34.05, 0), (34.40, 1), (35.50, 1), (35.95, 0),              # le 8 : l'été
             (37.80, 0), (38.25, 1), (38.75, 1), (38.82, 0),              # le 9 : claquées au nez
             (44.35, 0), (44.75, 1), (47.20, 1), (47.80, 0),              # le 3 : la dame, vieille
             (57.15, 0), (ISSUE_W, 1), (60.60, 1), (61.30, 0)]           # la fête, puis Bounce rallume le 1
SCENES = [(1.0, 2.3, "jogger"), (5.9, 10.5, "lady"), (15.0, 18.6, "noon"), (19.6, 20.2, "sunset"),
          (23.2, 29.0, "night"), (31.1, 33.5, "winter"), (34.0, 36.0, "summer"), (37.75, 38.9, "office"),
          (44.3, 47.8, "oldlady"), (57.1, 99.0, "party")]
FLOORS = [(0, 1), (0.80, 2), (5.30, 3), (14.40, 4), (19.30, 5), (22.60, 6), (29.20, 7), (33.60, 8), (37.20, 9),
          (41.00, 8), (41.50, 7), (42.00, 6), (42.50, 5), (43.05, 4), (43.65, 3), (48.30, 2), (48.85, 1),
          (50.90, 2), (51.50, 3), (52.10, 4), (52.75, 5), (53.40, 6), (54.00, 7), (54.65, 8), (57.10, 9),
          (61.0, 8)]
FAKE9 = (29.62, 31.00)        # le cadran, cogné, montre 9
ARROW = [(0, 1), (40.25, -1), (50.30, 1), (60.55, -1)]
CASCADE = [(n, 0.25 + 0.07 * (n - 2)) for n in range(2, 9)]
LIGHTS = {9: [(-1, 37.75), (50.20, 57.10)], 2: [(0.25, 0.85)], 3: [(0.32, 5.90), (40.20, 44.30)],
          4: [(0.39, 15.00)], 5: [(0.46, 19.60)], 6: [(0.53, 23.20)], 7: [(0.60, 31.10)], 8: [(0.67, 34.00)],
          1: [(12.15, 49.00), (60.47, 99.0)], "open": [(26.90, 27.40)], "close": [(2.15, 2.6), (38.75, 39.3)]}
# répliques (temps vidéo), qui parle, durée
LINES = [(3.20, "Come on, come on!", "come"), (8.65, "I'll take the stairs.", "stairs"),
         (13.05, "Seriously?!", "seriously"), (16.30, "Excuse me!", "excuse"), (20.00, "Wait!", "wait"),
         (24.60, "Working late?", "working"), (27.80, "Oh... come on.", "weary"), (30.50, "Nine!", "nine"),
         (31.90, "Hi, Santa!", "santa"), (34.60, "What year is it?", "year"),
         (38.40, "No!", "noo"), (46.40, "Still taking the stairs!", "still"), (53.10, "Not today!", "nottoday"),
         (58.58, "Happy retirement!", "party"), (60.23, "I just got here.", "got")]
LINE_GAIN = {"come": 0.95, "stairs": 1.0, "noo": 1.05, "still": 1.05, "party": 1.0, "got": 1.05, "seriously": 1.0,
             "excuse": 1.0, "wait": 1.0, "working": 0.95, "weary": 1.0, "nine": 1.05, "santa": 0.95, "year": 1.0,
             "nottoday": 1.05}
SPEAKER = {"come": "man", "stairs": "lady", "noo": "man", "still": "lady", "party": "party", "got": "man",
           "seriously": "man", "excuse": "man", "wait": "man", "working": "cleaner", "weary": "man", "nine": "man",
           "santa": "kid", "year": "man", "nottoday": "man"}
LINE_LEN = {"come": 1.10, "stairs": 0.97, "noo": 0.90, "still": 1.27, "party": 1.35, "got": 1.12, "seriously": 0.79,
            "excuse": 0.99, "wait": 0.57, "working": 0.87, "weary": 1.18, "nine": 0.60, "santa": 0.92, "year": 1.16,
            "nottoday": 1.17}
LINE_SPANS = {key: (tl, tl + LINE_LEN[key]) for (tl, _txt, key) in LINES}
# visages de Bounce (temps monde) : il réagit
EXPR = [(0.35, 1.9, "win"), (2.2, 3.2, "win"), (8.7, 9.6, "lose"), (17.45, 18.6, "win"), (26.95, 27.8, "win"),
        (29.7, 30.9, "win"), (31.0, 31.6, "lose"), (38.76, 41.0, "lose"), (50.5, 51.0, "lose"),
        (51.25, 51.9, "lose"), (53.45, 54.0, "shock"), (55.05, 55.6, "lose"), (55.8, 56.6, "lose"),
        (60.55, 99.0, "lose")]

def speaking(who, tv):
    for (key, (a, b)) in LINE_SPANS.items():
        if SPEAKER[key] == who and a <= tv <= b:
            return math.sin((tv - a) * 2 * math.pi * 4.5)
    return None


class Plan:
    def __init__(self):
        cs = []
        for (t, kind, arg) in HITS:
            if kind == "pan":
                y = 1000.0 if arg == "cascade" else min(FY - 4, max(CY, btn_y(arg)))
                cs.append({"t": t, "x": PX, "y": y, "axis": "x", "kind": kind, "arg": arg})
            elif kind == "ceil":
                cs.append({"t": t, "x": CEIL_X, "y": CY, "axis": "y", "kind": kind, "arg": arg})
            elif kind == "disp":
                cs.append({"t": t, "x": 540.0, "y": CY, "axis": "y", "kind": "ceil", "arg": "disp"})
            elif kind == "steel":
                cs.append({"t": t, "x": STEEL_X, "y": FY, "axis": "y", "kind": "steel", "arg": arg})
            elif kind == "steel2":
                cs.append({"t": t, "x": 505.0, "y": FY, "axis": "y", "kind": "steel", "arg": arg})
            elif kind == "brief":
                cs.append({"t": t, "x": BRIEF_X, "y": 1150.0, "axis": "x", "kind": kind, "arg": arg})
            elif kind == "cane":
                cs.append({"t": t, "x": self.cane_x(arg) + R, "y": min(FY - 4, arg), "axis": "x", "kind": kind,
                           "arg": arg})
        for c in cs:
            c["soft"] = False
        for (t, x, dent) in SOFT_FIX:
            cs.append({"t": t, "x": x, "y": FY + dent * 0.6, "axis": "y", "soft": True, "kind": "soft", "dent": dent})
        cs.sort(key=lambda c: c["t"])
        start = {"t": -0.30, "x": 520.0, "y": 900.0, "kind": "soft", "soft": True}
        full = []
        prev = start
        k = 0
        for c in cs:
            gap = c["t"] - prev["t"]
            lim = 0.6 if (c["kind"] == "ceil" or prev.get("kind") == "ceil") else 0.72
            n = max(1, math.ceil(gap / lim - 1e-9))
            for j in range(1, n):
                tt = prev["t"] + gap * j / n
                k += 1
                full.append({"t": tt, "x": self.soft_x(tt, k, prev, c, j / n), "y": FY + 12, "axis": "y",
                             "soft": True, "kind": "soft", "dent": 20.0})
            full.append(c)
            prev = c
        self.contacts = full
        self.start = start
        self.after = {"t": END_W + 0.6, "x": 405.0, "y": FY + 10}
        self.ts = [c["t"] for c in full]
        self.hits = [c for c in full if not c["soft"]]

    @staticmethod
    def cane_x(y):
        """La canne, tenue en garde devant le tableau : x de sa face droite à la hauteur y."""
        return 322.0 + 0.04 * (y - 850.0)

    @staticmethod
    def soft_x(t, k, a, b, u):
        x = lerp(a["x"], b["x"], u)
        doors_open = any(s0 <= t <= s1 for (s0, s1, _n) in SCENES)
        lo, hi = (370.0, 392.0) if doors_open else (400.0, 466.0)
        if 50.2 <= t <= 56.0:                   # le duel : jamais à travers la canne
            lo, hi = 456.0, 468.0
        if t > 56.0:
            lo, hi = 410.0, 432.0
        return max(lo, min(hi, x + (18 if k % 2 else -18)))

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.contacts[i - 1]
        b = self.after if i >= len(self.contacts) else self.contacts[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        T = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / T
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def squash(self, t):
        sx = sy = 1.0
        i = bisect.bisect_left(self.ts, t - 0.25)
        for c in self.contacts[max(0, i - 1):i + 4]:
            u = t - c["t"]
            big = c.get("arg") == "cascade"
            post = 0.22 if big else 0.14
            if -0.06 <= u <= post:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / post)
                amp = 0.32 if big else (0.2 if c["soft"] else 0.17)
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def apexes(self):
        out = []
        prev = self.start
        for c in self.contacts:
            T = c["t"] - prev["t"]
            vy = (c["y"] - prev["y"]) / T - 0.5 * G * T
            ta = -vy / G
            top = prev["y"] + vy * ta + 0.5 * G * ta * ta if 0 < ta < T else min(prev["y"], c["y"])
            out.append((prev["t"], c["t"], top, vy + G * T, c["kind"]))
            prev = c
        return out


# ------------------------------------------------------------------ l'homme pressé
POSES = {
    "rest": dict(lean=0, hl=(-26, 236), hr=(16, 230), hd=(0, 0), hip=0),
    "watch": dict(lean=0, hl=(-26, 236), hr=(-70, 110), hd=(-14, 10), hip=0),
    "startle": dict(lean=6, hl=(-60, 120), hr=(50, 120), hd=(-22, -10), hip=0),
    "whoa": dict(lean=8, hl=(-60, -40), hr=(60, -40), hd=(-10, -6), hip=0),
    "tap": dict(lean=-2, hl=(-26, 236), hr=(-74, 100), hd=(-12, 12), hip=0),
    "facepalm": dict(lean=-3, hl=(-26, 236), hr=(-66, -40), hd=(-4, 14), hip=0),
    "shield": dict(lean=-4, hl=(70, 40), hr=(78, 110), hd=(14, 0), hip=0),
    "stagger": dict(lean=-8, hl=(10, -150), hr=(-20, -150), hd=(-10, 6), hip=0),
    "sag": dict(lean=-2, hl=(-20, 250), hr=(20, 250), hd=(0, 22), hip=6),
    "flinch": dict(lean=10, hl=(-30, 120), hr=(40, 120), hd=(14, -4), hip=0),
    "escape": dict(lean=-10, hl=(-90, 130), hr=(30, 200), hd=(-20, 0), hip=0),
    "slouch": dict(lean=6, hl=(-16, 250), hr=(20, 250), hd=(6, 26), hip=10),
    "sleep": dict(lean=7, hl=(-12, 262), hr=(16, 262), hd=(10, 50), hip=12),
    "jolt": dict(lean=-4, hl=(-90, 60), hr=(90, 60), hd=(0, -14), hip=-10),
    "armsup": dict(lean=0, hl=(-60, -150), hr=(60, -150), hd=(0, -10), hip=0),
    "perk": dict(lean=-8, hl=(-60, 60), hr=(70, 60), hd=(-12, -10), hip=-6),
    "shiver": dict(lean=0, hl=(70, 90), hr=(-70, 90), hd=(0, 18), hip=4),
    "eager": dict(lean=-12, hl=(-110, 100), hr=(20, 200), hd=(-24, 0), hip=0),
    "bonk": dict(lean=14, hl=(-40, 60), hr=(40, 60), hd=(18, -6), hip=0),
    "kneel": dict(lean=4, hl=(-30, 200), hr=(30, 200), hd=(4, 40), hip=250),
    "old": dict(lean=-10, hl=(-26, 236), hr=(26, 200), hd=(-10, 46), hip=24),
    "guard": dict(lean=0, hl=(-50, 70), hr=(56, 100), hd=(0, 34), hip=18),
    "guard_hi": dict(lean=2, hl=(-50, 70), hr=(60, -60), hd=(4, 28), hip=10),
    "look": dict(lean=6, hl=(-50, 70), hr=(56, 110), hd=(26, 30), hip=18),
    "chin": dict(lean=-2, hl=(-26, 236), hr=(-62, -20), hd=(-6, 12), hip=0),
    "beardhold": dict(lean=0, hl=(-26, 236), hr=(-50, 40), hd=(-4, 20), hip=4),
    "wallhead": dict(lean=16, hl=(-20, 250), hr=(-30, -60), hd=(26, 36), hip=12),
    "doorlook": dict(lean=-6, hl=(-26, 236), hr=(-30, 160), hd=(-30, 10), hip=0),
}
SUIT_KEYS = [(0.0, "watch", 0.1), (0.30, "startle", 0.08), (0.95, "rest", 0.3), (1.6, "rest", 0.1),
             (2.17, "whoa", 0.08), (2.9, "tap", 0.25), (4.35, "rest", 0.25), (5.25, "flinch", 0.08),
             (5.6, "rest", 0.2), (6.25, "chin", 0.2), (7.2, "rest", 0.3), (10.3, "shield", 0.35),
             (11.41, "stagger", 0.12), (12.4, "shield", 0.2), (12.9, "stagger", 0.15), (13.9, "rest", 0.3),
             (15.25, "beardhold", 0.2), (15.7, "escape", 0.3), (17.41, "flinch", 0.08), (17.7, "escape", 0.2),
             (18.16, "flinch", 0.08), (18.5, "sag", 0.3), (19.7, "doorlook", 0.15), (20.4, "slouch", 0.4),
             (21.5, "sleep", 0.9), (23.66, "jolt", 0.08), (24.1, "slouch", 0.4),
             (26.95, "wallhead", 0.3), (28.6, "slouch", 0.4),
             (29.65, "perk", 0.15), (31.0, "sag", 0.3), (31.5, "shiver", 0.3), (32.96, "flinch", 0.1),
             (33.6, "slouch", 0.4), (34.5, "beardhold", 0.3), (35.9, "slouch", 0.3), (36.81, "flinch", 0.08),
             (37.2, "slouch", 0.3), (37.76, "eager", 0.2),
             (38.76, "bonk", 0.05), (39.3, "kneel", 0.5), (41.76, "flinch", 0.06),
             (42.0, "kneel", 0.3), (47.9, "old", 0.45), (50.3, "guard", 0.3), (53.25, "guard_hi", 0.2),
             (53.9, "guard", 0.3), (57.7, "look", 0.5)]
SUIT_X = KF(750.0, [(10.3, 750.0), (11.2, 205.0), (11.46, 205.0), (11.75, 182.0), (14.2, 182.0), (15.1, 750.0),
                    (15.7, 750.0), (16.2, 680.0), (17.41, 680.0), (17.6, 730.0), (17.85, 690.0), (18.16, 690.0),
                    (18.4, 750.0),
                    (37.78, 750.0), (38.74, 620.0), (38.77, 620.0), (39.1, 690.0), (39.5, 750.0),
                    (48.4, 750.0), (50.2, 195.0)])
# il traverse au premier plan (plus près de nous : plus bas, plus gros) ; il recule vers les portes pour sortir
SUIT_FG = KF(0.0, [(10.3, 0.0), (10.75, 80.0), (11.2, 0.0), (14.2, 0.0), (14.65, 80.0), (15.1, 0.0),
                   (15.7, 0.0), (16.2, -60.0), (17.41, -60.0), (17.6, -30.0), (17.85, -60.0), (18.16, -60.0),
                   (18.4, 0.0), (37.78, 0.0), (38.74, -60.0), (38.77, -60.0), (39.5, 0.0),
                   (48.4, 0.0), (49.3, 90.0), (50.2, 0.0)])
SUIT_HOP = [(0.30, 26), (2.17, 14), (23.66, 30), (29.65, 22), (37.78, 26)]


class Suit:
    def __init__(self):
        self.ts = [k[0] for k in SUIT_KEYS]
        # chaque ouverture de porte = des années : la barbe et les cheveux font un bond
        jumps = [(15.05, 50.0, 0.0), (19.65, 100.0, 0.05), (23.25, 160.0, 0.2), (31.15, 240.0, 0.5),
                 (34.05, 320.0, 0.65), (37.80, 420.0, 0.75), (44.35, 560.0, 0.95), (48.0, 700.0, 1.0)]
        bk, gk = [], []
        pb, pg = 0.0, 0.0
        for (tj, b, g) in jumps:
            bk += [(tj, pb), (tj + 0.22, b)]
            gk += [(tj, pg), (tj + 0.22, g)]
            pb, pg = b, g
        self.beard = KF(0.0, bk)
        self.gray = KF(0.0, gk)
        self.pool = KF(0.0, [(46.0, 0.0), (49.0, 120.0), (53.0, 230.0), (56.0, 260.0)])
        self.stub = KF(0.0, [(5.95, 0.0), (6.15, 1.0)])
        self.tie = KF(0.0, [(15.05, 0.0), (15.3, 1.0)])

    def pose(self, t):
        i = max(0, bisect.bisect_right(self.ts, t) - 1)
        t0, name, d = SUIT_KEYS[i]
        prev = POSES[SUIT_KEYS[i - 1][1]] if i > 0 else POSES[name]
        cur = POSES[name]
        k = smooth((t - t0) / d) if d > 0 else 1.0
        P = {}
        for key in cur:
            a, b = prev[key], cur[key]
            P[key] = (lerp(a[0], b[0], k), lerp(a[1], b[1], k)) if isinstance(a, tuple) else lerp(a, b, k)
        P["name"] = name
        return P


# ------------------------------------------------------------------ primitives (coordonnées écran, échelle k)
def poly(pts, k):
    return [(x * k, y * k) for x, y in pts]


def rect(dr, x0, y0, x1, y1, col, k, r=0, outline=None, width=0):
    box = [x0 * k, y0 * k, x1 * k, y1 * k]
    if r:
        dr.rounded_rectangle(box, radius=r * k, fill=col, outline=outline, width=int(width * k) if width else 0)
    else:
        dr.rectangle(box, fill=col, outline=outline, width=int(width * k) if width else 0)


def ell(dr, x, y, rx, ry, col, k, outline=None, width=0):
    dr.ellipse([(x - rx) * k, (y - ry) * k, (x + rx) * k, (y + ry) * k], fill=col, outline=outline,
               width=max(1, int(width * k)) if width else 0)


def capsule(dr, p0, p1, r, col, k):
    dr.line([(p0[0] * k, p0[1] * k), (p1[0] * k, p1[1] * k)], fill=col, width=max(1, int(2 * r * k)))
    for p in (p0, p1):
        dr.ellipse([(p[0] - r) * k, (p[1] - r) * k, (p[0] + r) * k, (p[1] + r) * k], fill=col)


def text(dr, x, y, s, size, col, k, anchor="mm"):
    dr.text((x * k, y * k), s, fill=col, anchor=anchor, font=font(size * k))


def rot(px, py, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = px - cx, py - cy
    return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca


def person(dr, k, x, fy, s, body, head, lean=0.0, hands=None, dress=False, hair=None, bun=None, hat=None,
           scarf=None, glasses=False, hunch=0.0, band=None):
    """Un passant sans visage : corps, tête, bras vers les mains données (absolues)."""
    a = math.radians(lean)
    hipy = fy - 250 * s
    legc = tuple(max(0, c - 40) for c in body)
    if dress:
        pts = [(x - 40 * s, hipy - 210 * s), (x + 40 * s, hipy - 210 * s), (x + 78 * s, fy - 60 * s),
               (x - 78 * s, fy - 60 * s)]
        pts = [rot(px, py, x, fy, a) for px, py in pts]
        capsule(dr, (x - 24 * s, fy - 70 * s), (x - 24 * s, fy - 8 * s), 13 * s, head, k)
        capsule(dr, (x + 24 * s, fy - 70 * s), (x + 24 * s, fy - 8 * s), 13 * s, head, k)
        dr.polygon(poly(pts, k), fill=body)
    else:
        capsule(dr, (x - 22 * s, hipy), (x - 22 * s, fy - 12 * s), 17 * s, legc, k)
        capsule(dr, (x + 22 * s, hipy), (x + 22 * s, fy - 12 * s), 17 * s, legc, k)
        pts = [(x - 58 * s, hipy - 240 * s), (x + 58 * s, hipy - 240 * s), (x + 54 * s, hipy + 6 * s),
               (x - 54 * s, hipy + 6 * s)]
        pts = [rot(px, py, x, hipy, a) for px, py in pts]
        dr.polygon(poly(pts, k), fill=body)
    top = rot(x, hipy - 240 * s - hunch * 20 * s, x, hipy, a)
    hx, hy = rot(x + hunch * 26 * s, hipy - 300 * s + hunch * 30 * s, x, hipy, a)
    shl = rot(x - 50 * s, hipy - 226 * s, x, hipy, a)
    shr = rot(x + 50 * s, hipy - 226 * s, x, hipy, a)
    if hands is None:
        hands = [(shl[0] - 14 * s, shl[1] + 200 * s), (shr[0] + 14 * s, shr[1] + 200 * s)]
    for sh, hd in ((shl, hands[0]), (shr, hands[1])):
        capsule(dr, sh, hd, 14 * s, body, k)
        ell(dr, hd[0], hd[1], 15 * s, 15 * s, head, k)
    if scarf:
        capsule(dr, (top[0] - 40 * s, top[1] + 10 * s), (top[0] + 40 * s, top[1] + 10 * s), 18 * s, scarf, k)
        capsule(dr, (top[0] + 24 * s, top[1] + 14 * s), (top[0] + 30 * s, top[1] + 90 * s), 13 * s, scarf, k)
    ell(dr, hx, hy, 48 * s, 48 * s, head, k)
    if hair:
        dr.chord([(hx - 49 * s) * k, (hy - 49 * s) * k, (hx + 49 * s) * k, (hy + 49 * s) * k], 200, 340, fill=hair)
    if bun:
        ell(dr, hx + 8 * s, hy - 56 * s, 24 * s, 22 * s, bun, k)
        dr.chord([(hx - 49 * s) * k, (hy - 49 * s) * k, (hx + 49 * s) * k, (hy + 49 * s) * k], 185, 355, fill=bun)
    if band:
        rect(dr, hx - 48 * s, hy - 30 * s, hx + 48 * s, hy - 14 * s, band, k)
    if hat:
        dr.polygon(poly([(hx - 36 * s, hy - 34 * s), (hx + 36 * s, hy - 34 * s), (hx + 4 * s, hy - 120 * s)], k),
                   fill=hat)
        ell(dr, hx + 4 * s, hy - 122 * s, 10 * s, 10 * s, (255, 255, 255), k)
    if glasses:
        rect(dr, hx - 40 * s, hy - 14 * s, hx + 40 * s, hy + 6 * s, (20, 20, 26), k, r=8 * s)
    return (hx, hy), shl, shr


# ------------------------------------------------------------------ la scène
class Sim:
    scene_top = 0.275

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.P = Plan()
        self.suit = Suit()
        self.door = KF(0.0, DOOR_KEYS)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_v = [video(c["t"]) for c in self.P.hits]
        self.hi = 0
        self.lines = list(LINES)
        self.replies = []
        self.ceil_hits = [c["t"] for c in self.P.hits if c["kind"] == "ceil"]
        rng2 = np.random.default_rng(5)
        self.confetti = [(rng2.uniform(450, 790), rng2.uniform(0, 1), rng2.uniform(0.6, 1.3),
                          [(255, 214, 90), (90, 200, 255), (255, 110, 160), (140, 230, 140)][i % 4])
                         for i in range(46)]
        self.snow = [(rng2.uniform(0, 1), rng2.uniform(0, 1), rng2.uniform(0.5, 1.0)) for _ in range(26)]

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_v) and self.hit_v[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if world(self.t) >= END_W - 1e-9:
            self.done = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, tv):
        best, bd = 0.9, 1e9
        for c, v in zip(self.P.hits, self.hit_v):
            if abs(v - tv) < bd:
                bd = abs(v - tv)
                best = 1.25 if c.get("arg") == "cascade" else (
                    1.15 if c["kind"] == "pan" and c["arg"] in ("close", "open") else
                    0.85 if c["kind"] == "steel" else 1.0)
        return best

    # ---------------------------------------------------------- état
    def floor_at(self, t):
        if FAKE9[0] <= t < FAKE9[1]:
            return 9 if (t < FAKE9[1] - 0.2 or int(t * 20) % 2) else 7
        f = 1
        for (tt, v) in FLOORS:
            if t >= tt:
                f = v
        return f

    def arrow_at(self, t):
        a = 1
        for (tt, v) in ARROW:
            if t >= tt:
                a = v
        return a

    def lit(self, key, t):
        return any(a <= t < b for (a, b) in LIGHTS.get(key, []))

    def scene_at(self, t):
        for (a, b, n) in SCENES:
            if a <= t <= b:
                return n, t - a
        return None, 0.0

    def flicker(self, t):
        f = 1.0
        for th in self.ceil_hits:
            u = t - th
            if 0 <= u <= 0.22:
                f = min(f, 0.45 + 0.55 * (u / 0.22))
        return f

    def jolt(self, t):
        """L'ascenseur pile : la cabine tressaute (vers le bas puis remonte)."""
        dy = 0.0
        for d in JOLTS:
            u = t - (d - 0.05)
            if 0 <= u <= 0.35:
                dy += 14 * math.sin(u * 30) * (1 - u / 0.35)
        return dy

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, tv, S):
        tv = float(tv)
        t = world(tv)
        k = S * self.cfg["width"] / W
        img = dr._image
        self.draw_cabin(dr, t, k)
        o = self.door(t)
        if o > 0.002:
            self.draw_landing(img, t, tv, k, o)
        self.draw_doors(dr, t, k, o)
        self.draw_display(dr, t, k)
        self.draw_panel(dr, t, k)
        self.draw_floor(dr, t, k)
        self.draw_shadow(dr, t, k)
        self.draw_rings(dr, t, k)
        base.HERO["expr"] = self.expr_at(t)
        bx, by = self.P.pos(t)
        sx, sy = self.P.squash(t)
        if abs(sx - sy) < 0.01:
            base.ball(dr, bx * k, by * k, R * k)
        else:
            self.draw_ball(dr, bx, by, R * sx, R * sy, k)
        self.draw_suit(dr, t, tv, k)
        if SLO_A <= tv <= SLO_A + SLO_V:
            self.draw_slowmo(dr, tv, k)
        j = self.jolt(t)
        if abs(j) > 0.5:
            # la scène tressaute ; on comble le haut avec le fond (l'accroche est posée ensuite par base)
            sh = int(round(j * k))
            moved = ImageChops.offset(img, 0, sh)
            if sh > 0:
                moved.paste(BG, (0, 0, img.size[0], sh))
            else:
                moved.paste(BG, (0, img.size[1] + sh, img.size[0], img.size[1]))
            img.paste(moved)

    def expr_at(self, t):
        if t >= 60.55:
            return "lose"
        if t >= ISSUE_W + 1.2:
            return "win"
        if ISSUE_W - 0.2 <= t < ISSUE_W + 1.2:
            return "shock"
        for (a, b, e) in EXPR:
            if a <= t < b:
                return e
        for c in self.P.hits:
            if 0 <= t - c["t"] < 0.3:
                return "shock"
        return "calm"

    def draw_ball(self, dr, x, y, rx, ry, k):
        r = max(rx, ry)
        size = int(2 * r * 1.7 * k) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO["pos"]
        base.ball(ld, size / 2, size / 2, R * k)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size * rx / R)), max(2, int(size * ry / R))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        dr._image.paste(layer, (int(x * k - nw / 2), int(y * k - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (x * k, y * k)

    def draw_cabin(self, dr, t, k):
        rect(dr, 0, 470, W, FLOOR, WALLC, k)
        dr.polygon(poly([(0, 440), (110, CEIL), (110, FLOOR), (0, FLOOR + 90)], k), fill=WALLD)
        dr.polygon(poly([(W, 440), (970, CEIL), (970, FLOOR), (W, FLOOR + 90)], k), fill=WALLD)
        for x in range(130, 970, 46):
            dr.line([(x * k, (CEIL + 5) * k), (x * k, (FLOOR - 4) * k)], fill=(60, 64, 80), width=max(1, int(2 * k)))
        rect(dr, 290, 1120, 402, 1136, (90, 94, 110), k, r=6)
        rect(dr, 788, 1120, 970, 1136, (90, 94, 110), k, r=6)
        dr.polygon(poly([(0, 440), (W, 440), (970, CEIL), (110, CEIL)], k), fill=CEILC)
        f = self.flicker(t)
        col = mix((70, 70, 64), LIGHT, f)
        rect(dr, 300, CEIL - 22, 780, CEIL, col, k, r=6)
        if f > 0.9:
            dr.polygon(poly([(300, CEIL), (780, CEIL), (850, CEIL + 40), (230, CEIL + 40)], k), fill=(64, 68, 82))

    def draw_floor(self, dr, t, k):
        dr.polygon(poly([(110, FLOOR), (970, FLOOR), (W, FLOOR + 90), (W, H), (0, H), (0, FLOOR + 90)], k),
                   fill=FLOORC)
        for j in range(1, 7):
            y = FLOOR + 40 * j + 6 * j * j
            if y > H:
                break
            dr.line([(0, y * k), (W * k, y * k)], fill=(52, 54, 66), width=max(1, int(3 * k)))
        rect(dr, 0, 1760, W, H, (22, 22, 28), k)       # bande sombre : le filigrane s'y lit
        bx, by = self.P.pos(t)
        dent = 0.0
        if by > FY - 2 and RUG[0] < bx < RUG[1] + 30:
            dent = min(30.0, (by - FY + 2) * 1.7)
        top = []
        for i in range(25):
            x = RUG[0] + (RUG[1] - RUG[0]) * i / 24
            d = dent * math.exp(-((x - bx) / 80.0) ** 2)
            top.append((x, FLOOR - 8 + d))
        RB = 1740.0
        pts = top + [(RUG[1] + 140, RB), (RUG[0] - 140, RB)]
        dr.polygon(poly(pts, k), fill=RUGC)

        def rx(xr, yy):
            u = (yy - FLOOR) / (RB - FLOOR)
            return RUG[0] - 140 * u + (RUG[1] - RUG[0] + 280 * u) * xr
        inner = [(rx(0.06, FLOOR + 34), FLOOR + 34), (rx(0.94, FLOOR + 34), FLOOR + 34), (rx(0.94, RB - 30), RB - 30),
                 (rx(0.06, RB - 30), RB - 30)]
        dr.polygon(poly(inner, k), outline=(196, 150, 90), width=max(1, int(7 * k)))
        for j in range(2):
            yc = FLOOR + 100 + j * 130
            hh = 40 + 10 * j
            for xr in (0.25, 0.5, 0.75):
                xc = rx(xr, yc)
                dr.polygon(poly([(xc, yc - hh), (xc + hh * 1.1, yc), (xc, yc + hh), (xc - hh * 1.1, yc)], k),
                           fill=RUGD)
                dr.polygon(poly([(xc, yc - hh * 0.4), (xc + hh * 0.45, yc), (xc, yc + hh * 0.4), (xc - hh * 0.45, yc)], k),
                           fill=(196, 150, 90))
        for i in range(0, 25, 2):
            x, y = top[i]
            dr.line([(x * k, y * k), ((x - 6) * k, (y - 10) * k)], fill=(150, 66, 78), width=max(1, int(4 * k)))
        self.draw_beard_pool(dr, t, k)

    def draw_shadow(self, dr, t, k):
        bx, by = self.P.pos(t)
        h = clamp01((FY - by) / 600.0)
        ell(dr, bx, FLOOR + 6, R * (0.95 - 0.4 * h), 14 * (1 - 0.5 * h), (24, 20, 28), k)

    def draw_rings(self, dr, t, k):
        for c in self.P.hits:
            u = t - c["t"]
            dur = 0.45 if c.get("arg") == "cascade" else 0.3
            if not (0 <= u <= dur):
                continue
            a = 1 - u / dur
            rr = 30 + (220 if c.get("arg") == "cascade" else 120) * u / dur
            if c["kind"] == "ceil":
                cx, cy = c["x"], CEIL
            elif c["axis"] == "x":
                cx, cy = c["x"] - R, c["y"]
            else:
                cx, cy = c["x"], c["y"] + R
            col = mix(WALLC, (255, 240, 200), a)
            ell(dr, cx, cy, rr, rr * 0.8, None, k, outline=col, width=7)

    def draw_slowmo(self, dr, tv, k):
        u = (tv - SLO_A) / SLO_V
        a = clamp01(min(u, 1 - u) * 8)
        col = mix(WALLC, (255, 255, 255), 0.35 * a)
        for (x0, y0, x1, y1) in ((120, 1200, 120, 1400), (960, 1200, 960, 1400)):
            dr.line([(x0 * k, y0 * k), (x1 * k, y1 * k)], fill=col, width=max(1, int(4 * k)))

    # -------- portes, afficheur, tableau
    def draw_doors(self, dr, t, k, o):
        x0, x1, y0, y1 = DOOR
        rect(dr, x0 - 16, y0 - 16, x1 + 16, y0, (88, 92, 108), k)
        dr.line([((x0 - 8) * k, y0 * k), ((x0 - 8) * k, y1 * k)], fill=(88, 92, 108), width=max(1, int(16 * k)))
        dr.line([((x1 + 8) * k, y0 * k), ((x1 + 8) * k, y1 * k)], fill=(88, 92, 108), width=max(1, int(16 * k)))
        half = (x1 - x0) / 2
        w = half * (1 - o)
        shake = 0.0
        for ts in (2.25, 39.27):                   # claquées : elles vibrent
            u = t - ts
            if 0 <= u <= 0.4:
                shake = 6 * math.sin(u * 70) * (1 - u / 0.4)
        if w > 0.5:
            mid = (x0 + x1) / 2
            for (a, b) in ((x0, x0 + w), (x1 - w, x1)):
                rect(dr, a + shake, y0, b + shake, y1, STEELC, k)
                for j in range(3):
                    xx = a + (b - a) * (j + 1) / 4 + shake
                    dr.line([(xx * k, (y0 + 10) * k), (xx * k, (y1 - 10) * k)], fill=STEELL, width=max(1, int(2 * k)))
            if o < 0.02:
                dr.line([((mid + shake) * k, y0 * k), ((mid + shake) * k, y1 * k)], fill=(70, 74, 88),
                        width=max(1, int(4 * k)))

    def needle_floor(self, t):
        """Étage montré par l'aiguille : glisse d'un étage à l'autre ; cognée, elle saute sur 9."""
        if FAKE9[0] <= t < FAKE9[1]:
            u = t - FAKE9[0]
            return 9.0 + (0.25 * math.sin(u * 40) * max(0.0, 1 - u / 0.5))
        prev_t, prev_f = 0.0, 1
        for (tt, v) in FLOORS:
            if t >= tt:
                prev_t, prev_f, last = tt, v, v
        before = [v for (tt, v) in FLOORS if tt <= prev_t - 1e-9]
        f0 = before[-1] if before else prev_f
        return lerp(f0, prev_f, smooth((t - prev_t) / 0.35))

    def clock_turns(self, t):
        """Tours de la grande aiguille : lente en temps normal, folle pendant que les portes sont ouvertes."""
        turns = 0.02 * t
        for (a, b, _n) in SCENES:
            turns += 7.0 * max(0.0, min(t, b) - a)
        return turns

    def draw_display(self, dr, t, k):
        """Le haut de la cabine : calendrier (l'année), grand cadran d'étage à aiguille, grande horloge."""
        cx, cy, r = DIAL
        rect(dr, 0, 0, W, 238, (26, 22, 20), k)
        self.calendar(dr, t, k)
        hx, hy, hr = 860.0, 136.0, 84.0
        ell(dr, hx, hy, hr + 8, hr + 8, (120, 92, 46), k)
        ell(dr, hx, hy, hr, hr, (244, 244, 236), k)
        for j in range(12):
            a_ = math.radians(j * 30)
            ell(dr, hx + 0.82 * hr * math.cos(a_), hy + 0.82 * hr * math.sin(a_), 5, 5, (40, 40, 46), k)
        turns = self.clock_turns(t)
        am = 2 * math.pi * turns - math.pi / 2
        ah = 2 * math.pi * turns / 12 - math.pi / 2 + 1.0
        capsule(dr, (hx, hy), (hx + 0.5 * hr * math.cos(ah), hy + 0.5 * hr * math.sin(ah)), 7, (20, 20, 26), k)
        capsule(dr, (hx, hy), (hx + 0.78 * hr * math.cos(am), hy + 0.78 * hr * math.sin(am)), 5, (20, 20, 26), k)
        ell(dr, hx, hy, 8, 8, (200, 40, 40), k)
        dr.pieslice([(cx - r - 26) * k, (cy - r - 26) * k, (cx + r + 26) * k, (cy + r + 26) * k], 180, 360,
                    fill=(120, 92, 46))
        dr.pieslice([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], 180, 360, fill=(236, 226, 196))
        flash = any(0 <= t - st_[1] <= 0.5 for st_ in STOPS)
        for n in range(1, 10):
            ang = math.radians(180 + (n - 1) * 22.5)
            tx, ty = cx + 0.78 * r * math.cos(ang), cy + 0.78 * r * math.sin(ang)
            on = self.lit(n, t)
            if on:
                ell(dr, tx, ty, 21, 21, (255, 214, 90), k)
            text(dr, tx, ty, str(n), 34, (40, 30, 20), k)
        f = self.needle_floor(t)
        ang = math.radians(180 + (f - 1) * 22.5)
        tip = (cx + 0.62 * r * math.cos(ang), cy + 0.62 * r * math.sin(ang))
        ncol = (220, 40, 40) if not flash else (255, 120, 40)
        dr.line([(cx * k, cy * k), (tip[0] * k, tip[1] * k)], fill=ncol, width=max(1, int(10 * k)))
        ell(dr, cx, cy, 16, 16, (60, 44, 30), k)
        a = self.arrow_at(t)
        ax, ay = cx, cy - 0.3 * r
        if a > 0:
            pts = [(ax - 16, ay + 12), (ax + 16, ay + 12), (ax, ay - 14)]
        else:
            pts = [(ax - 16, ay - 12), (ax + 16, ay - 12), (ax, ay + 14)]
        dr.polygon(poly(pts, k), fill=(60, 44, 30))

    def draw_panel(self, dr, t, k):
        x0, x1, y0, y1 = PAN
        rect(dr, x0, y0, x1, y1, (100, 104, 120), k, r=16)
        rect(dr, x0 + 8, y0 + 8, x1 - 8, y1 - 8, (78, 82, 98), k, r=14)
        for n in range(1, 10):
            cx, y = BTN[n]
            on = self.lit(n, t)
            pulse = 0.0
            for (nn, tc) in CASCADE:
                if nn == n and 0 <= t - tc <= 0.45:
                    pulse = 1 - (t - tc) / 0.45
            for c in self.P.hits:
                if c["kind"] == "pan" and c["arg"] == n and 0 <= t - c["t"] <= 0.4:
                    pulse = max(pulse, 1 - (t - c["t"]) / 0.4)
            if on:
                ell(dr, cx, y, BTN_R + 8, BTN_R + 8, (130, 104, 40), k)
            if pulse > 0:
                rr = BTN_R + 10 + 70 * (1 - pulse)
                ell(dr, cx, y, rr, rr, None, k, outline=mix(WALLC, LIT, pulse), width=8)
            ell(dr, cx, y, BTN_R, BTN_R, LIT if on else (40, 42, 52), k, outline=(160, 164, 180), width=4)
            text(dr, cx, y + 1, str(n), 54, (30, 24, 10) if on else (210, 214, 226), k)
        if 38.0 <= t <= 38.75:                  # au ralenti : la cible
            ph = (t - 38.0) * 9
            rr = 52 + 8 * math.sin(ph * 6)
            ell(dr, BTN["close"][0], btn_y("close"), rr, rr, None, k, outline=(110, 230, 140), width=6)
        if 55.3 <= t <= 55.8:                   # au duel : il vise « fermer », paré au dernier moment
            rr = 52 + 6 * math.sin(t * 50)
            ell(dr, BTN["close"][0], btn_y("close"), rr, rr, None, k, outline=(110, 230, 140), width=6)
        for key in ("open", "close"):
            bxx, y = BTN[key]
            on = self.lit(key, t)
            rect(dr, bxx - 38, y - 32, bxx + 38, y + 32, (110, 230, 140) if on else (40, 42, 52), k, r=10,
                 outline=(160, 164, 180), width=4)
            ic = (20, 40, 20) if on else (210, 214, 226)
            if key == "open":
                pts1 = [(bxx - 6, y - 17), (bxx - 6, y + 17), (bxx - 28, y)]
                pts2 = [(bxx + 6, y - 17), (bxx + 6, y + 17), (bxx + 28, y)]
            else:
                pts1 = [(bxx - 28, y - 17), (bxx - 28, y + 17), (bxx - 6, y)]
                pts2 = [(bxx + 28, y - 17), (bxx + 28, y + 17), (bxx + 6, y)]
            dr.polygon(poly(pts1, k), fill=ic)
            dr.polygon(poly(pts2, k), fill=ic)

    # -------- les paliers
    def draw_landing(self, img, t, tv, k, o):
        x0, x1, y0, y1 = DOOR
        L = Image.new("RGB", img.size, BG)
        d = ImageDraw.Draw(L)
        name, u = self.scene_at(t)
        self._t = t
        getattr(self, "land_" + (name or "jogger"))(d, t, u, k, tv)
        half = (x1 - x0) / 2 * o
        mid = (x0 + x1) / 2
        box = (int((mid - half) * k), int(y0 * k), int((mid + half) * k), int(y1 * k))
        src = (box[0] + int(LAND_DX * k), box[1], box[2] + int(LAND_DX * k), box[3])
        if box[2] > box[0]:
            img.paste(L.crop(src), box[:2])

    def land_room(self, d, k, wall, floor, sky, n, clock=None):
        rect(d, 400, 600, 840, 1440, wall, k)
        rect(d, 400, 1380, 840, 1440, floor, k)
        rect(d, 640, 690, 772, 880, (24, 24, 30), k)
        rect(d, 648, 698, 764, 872, sky, k)
        d.line([(706 * k, 698 * k), (706 * k, 872 * k)], fill=(24, 24, 30), width=max(1, int(5 * k)))

    def year_at(self, t):
        y = None
        for st_ in STOPS:
            if t >= st_[1] - 0.05 and st_[2] is not None:
                y = st_[2]
        return y

    def calendar(self, d, t, k):
        """Le calendrier de la cabine : l'année, en grand (220 px de large). À chaque ouverture de porte, des
        années passent : la page s'envole."""
        y = self.year_at(t)
        if y is None:
            y = 2026
        x0, y0, x1, y1 = 110.0, 40.0, 330.0, 226.0
        rect(d, x0, y0, x1, y1, (248, 246, 240), k, r=8)
        rect(d, x0, y0, x1, y0 + 40, (210, 50, 56), k, r=8)
        rect(d, x0, y0 + 30, x1, y0 + 40, (210, 50, 56), k)
        for rx in (x0 + 34, x1 - 34):
            ell(d, rx, y0 + 6, 8, 8, (60, 60, 66), k)
        text(d, (x0 + x1) / 2, y0 + 116, str(y), 72, (30, 30, 36), k)
        # la page de l'année d'avant s'envole
        opens = [st_[1] for st_ in STOPS if st_[2] is not None and 0 <= t - st_[1] <= 0.7]
        if opens:
            u = (t - opens[-1]) / 0.7
            px, py = x0 - 120 * u, y0 - 60 * u + 200 * u * u
            dr_pts = [rot(qx, qy, (x0 + x1) / 2, (y0 + y1) / 2, -1.2 * u) for (qx, qy) in
                      ((x0, y0 + 40), (x1, y0 + 40), (x1, y1), (x0, y1))]
            dr_pts = [(qx - (x0 - px), qy - (y0 - py)) for (qx, qy) in dr_pts]
            d.polygon(poly(dr_pts, k), fill=mix((248, 246, 240), (200, 200, 200), u))

    def clock(self, d, x, y, r, hm, k):
        ell(d, x, y, r + 5, r + 5, (30, 30, 36), k)
        ell(d, x, y, r, r, (244, 244, 236), k)
        h, m = hm
        am = math.radians(m * 6 - 90)
        ah = math.radians((h % 12 + m / 60) * 30 - 90)
        capsule(d, (x, y), (x + 0.5 * r * math.cos(ah), y + 0.5 * r * math.sin(ah)), 4, (20, 20, 26), k)
        capsule(d, (x, y), (x + 0.8 * r * math.cos(am), y + 0.8 * r * math.sin(am)), 3, (20, 20, 26), k)

    def land_jogger(self, d, t, u, k, tv):
        self.land_room(d, k, (196, 206, 214), (150, 140, 128), (170, 214, 250), 2, (9, 1))
        # un joggeur arrive en courant : Bounce lui ferme la porte au nez
        x = KF(800.0, [(0.3, 800.0), (1.2, 640.0)])(u)
        run = math.sin(u * 16)
        fy = PEOPLE_FY - abs(run) * 14
        s = PEOPLE_S
        person(d, k, x, fy, s, (240, 120, 60), (226, 184, 150), lean=-12,
               hands=[(x - 70 + 30 * run, fy - 330), (x + 60 - 30 * run, fy - 270)], band=(255, 255, 255))

    def stairs_sign(self, d, x, y, k, col=(60, 170, 90)):
        rect(d, x - 50, y - 38, x + 50, y + 38, col, k, r=6)
        pts = [(x - 36, y + 25), (x - 36, y + 9), (x - 16, y + 9), (x - 16, y - 7), (x + 4, y - 7), (x + 4, y - 23),
               (x + 34, y - 23), (x + 34, y + 25)]
        d.polygon(poly(pts, k), fill=(255, 255, 255))

    def land_lady(self, d, t, u, k, tv):
        self.land_room(d, k, (206, 196, 180), (150, 132, 112), (186, 222, 250), 3, (9, 30))
        self.stairs_sign(d, 560, 960, k)
        self.lady(d, t, u, k, tv, old=False)

    def lady(self, d, t, u, k, tv, old):
        if not old:
            xs = KF(720.0, [(0.3, 720.0), (0.7, 650.0), (1.2, 650.0), (1.5, 690.0), (3.6, 690.0), (4.4, 820.0)])
            lean = KF(0.0, [(0.7, -6.0), (0.8, 0.0), (1.1, 0.0), (1.3, 14.0), (2.6, 10.0), (3.7, -8.0)])
            point = (2.0, 3.6)
        else:
            xs = KF(730.0, [(0.3, 730.0), (1.0, 660.0), (2.2, 660.0), (2.5, 690.0), (3.5, 690.0)])
            lean = KF(-12.0, [(1.0, -12.0), (1.5, -6.0), (2.2, -6.0), (2.4, 10.0), (3.5, 10.0)])
            point = (1.9, 3.4)
        x = xs(u)
        fy = PEOPLE_FY
        s = PEOPLE_S
        talk = speaking("lady", tv)
        bob = 0.0 if talk is None else 6 * talk
        body = (150, 90, 190)
        head = (228, 188, 156)
        hands = None
        if point[0] <= u <= point[1]:
            hands = [(575.0 + bob, 975.0 + bob), (x + 60 * s, fy - 270 * s)]
        person(d, k, x, fy - abs(bob), s, body, head, lean=lean(u) + bob * 0.8, hands=hands, dress=True,
               bun=(200, 200, 206) if old else (110, 70, 40), hunch=1.0 if old else 0.0)
        rect(d, x + 52 * s, fy - 300 * s, x + 100 * s, fy - 250 * s, (230, 120, 60), k, r=8)
        if old:
            d.line([((x - 80) * k, (fy - 300) * k), ((x - 96) * k, fy * k)], fill=(120, 80, 50), width=max(1, int(9 * k)))

    def land_noon(self, d, t, u, k, tv):
        self.land_room(d, k, (214, 210, 186), (150, 140, 120), (120, 196, 255), 4, (12, 0))
        ell(d, 700, 740, 24, 24, (255, 230, 90), k)
        bite = u > 1.9
        for (x0, col) in ((610.0, (90, 170, 110)), (700.0, (230, 150, 70))):
            x = x0
            hands = [(x - 40, 1150.0), (x + 50, 1130.0)]
            if x0 == 700.0 and bite and (u * 4) % 1 < 0.5:
                hands = [(x - 40, 1150.0), (x + 10, 1060.0)]
            # ils regardent l'homme qui essaie de sortir : ils se penchent
            lean = 6.0 * math.sin(u * 3) if 1.0 < u < 3.0 else 0.0
            person(d, k, x, PEOPLE_FY, 1.12, col, (222, 180, 146), lean=lean, hands=hands)
            hx, hy = hands[1]
            w = 50 if not (x0 == 700.0 and bite) else 30
            rect(d, hx - w / 2, hy - 15, hx + w / 2, hy + 15, (236, 206, 140), k, r=6)
            d.line([((hx - w / 2) * k, hy * k), ((hx + w / 2) * k, hy * k)], fill=(90, 170, 70), width=max(1, int(5 * k)))

    def land_sunset(self, d, t, u, k, tv):
        self.land_room(d, k, (168, 140, 132), (120, 100, 92), (250, 150, 80), 5, (18, 0))
        ell(d, 700, 840, 32, 32, (255, 210, 120), k)
        x = 650.0
        wave_ = 40 * math.sin(u * 30)
        person(d, k, x, PEOPLE_FY, 1.12, (70, 110, 190), (220, 180, 146),
               hands=[(x - 60 + wave_, PEOPLE_FY - 560), (x + 50, PEOPLE_FY - 290)])

    def land_night(self, d, t, u, k, tv):
        self.land_room(d, k, (60, 62, 84), (44, 44, 58), (20, 24, 52), 6, (23, 0))
        ell(d, 700, 760, 24, 24, (240, 240, 210), k)
        ell(d, 709, 753, 22, 22, (20, 24, 52), k)
        x = 690.0
        mop = 24 * math.sin(u * 7)
        lean = 6.0 if u < 1.2 else -4.0
        talk = speaking("cleaner", tv)
        if talk is not None:
            lean = -10.0 + 5 * talk
        person(d, k, x, PEOPLE_FY, 1.12, (110, 116, 130), (214, 176, 144), lean=lean,
               hands=[(x - 60 + mop * 0.5, 1150.0), (x - 40 + mop * 0.5, 1240.0)])
        d.line([((x - 70 + mop) * k, 1110 * k), ((x - 110 + mop) * k, 1410 * k)], fill=(170, 130, 80), width=max(1, int(9 * k)))
        rect(d, x - 160 + mop, 1398, x - 70 + mop, 1424, (200, 200, 210), k, r=6)
        sx = KF(790.0, [(1.5, 790.0), (2.1, 610.0)])(u)
        sy = PEOPLE_FY
        d.polygon(poly([(sx - 48, sy), (sx + 48, sy), (sx + 12, sy - 150), (sx - 12, sy - 150)], k), fill=(250, 210, 40))
        d.polygon(poly([(sx - 7, sy - 112), (sx + 10, sy - 84), (sx - 2, sy - 74), (sx + 17, sy - 38), (sx - 17, sy - 38),
                        (sx - 10, sy - 70)], k), fill=(30, 30, 30))

    def land_winter(self, d, t, u, k, tv):
        self.land_room(d, k, (176, 196, 214), (140, 150, 166), (150, 170, 196), 7, None)
        for (a, b, s) in self.snow:
            yy = 698 + ((b + u * 0.35 * s) % 1.0) * 174
            ell(d, 648 + a * 116, yy, 4, 4, (255, 255, 255), k)
        rect(d, 648, 846, 764, 872, (255, 255, 255), k)
        d.polygon(poly([(500, 1400), (620, 1400), (560, 1110)], k), fill=(40, 130, 70))
        for (dx, dy, c) in ((-24, -50, (255, 80, 80)), (20, -110, (255, 214, 90)), (-8, -190, (90, 180, 255)),
                            (30, -40, (255, 214, 90))):
            ell(d, 560 + dx, 1400 + dy, 10, 10, c, k)
        rect(d, 552, 1400, 568, 1424, (110, 70, 40), k)
        # un enfant en bonnet, un cadeau dans les bras : il prend l'homme barbu pour le père Noël
        talk = speaking("kid", tv)
        x = 680.0
        jump = 0.0 if talk is None else 10 * abs(talk)
        person(d, k, x, PEOPLE_FY - jump, 0.78, (200, 60, 60), (226, 184, 150),
               hands=[(x - 70, PEOPLE_FY - 560 - jump), (x + 34, PEOPLE_FY - 300 - jump)],
               hat=(60, 100, 200), scarf=(250, 250, 250))
        rect(d, x + 4, PEOPLE_FY - 330 - jump, x + 64, PEOPLE_FY - 276 - jump, (200, 40, 60), k, r=4)
        d.line([((x + 34) * k, (PEOPLE_FY - 330 - jump) * k), ((x + 34) * k, (PEOPLE_FY - 276 - jump) * k)],
               fill=(255, 214, 90), width=max(1, int(6 * k)))

    def land_summer(self, d, t, u, k, tv):
        self.land_room(d, k, (234, 222, 170), (170, 150, 110), (110, 200, 255), 8, None)
        ell(d, 676, 730, 22, 22, (255, 230, 90), k)
        ell(d, 730, 830, 30, 24, (70, 170, 70), k)
        x = 690.0
        person(d, k, x, PEOPLE_FY, 1.12, (250, 140, 170), (226, 184, 150), hands=[(x - 40, 1170.0), (x + 50, 1060.0)],
               glasses=True)
        d.polygon(poly([(x + 34, 1060), (x + 66, 1060), (x + 50, 1116)], k), fill=(214, 160, 90))
        ell(d, x + 50, 1048, 20, 20, (255, 190, 210), k)

    def land_office(self, d, t, u, k, tv):
        self.land_room(d, k, (222, 226, 234), (160, 160, 168), (170, 214, 250), 9, (9, 0))
        rect(d, 600, 1220, 800, 1252, (150, 110, 80), k)
        rect(d, 616, 1252, 634, 1380, (120, 86, 60), k)
        rect(d, 768, 1252, 786, 1380, (120, 86, 60), k)
        rect(d, 650, 1130, 740, 1200, (40, 44, 56), k, r=4)
        rect(d, 686, 1200, 704, 1220, (40, 44, 56), k)

    def land_oldlady(self, d, t, u, k, tv):
        self.land_room(d, k, (190, 168, 150), (140, 120, 104), (230, 170, 110), 3, None)
        self.stairs_sign(d, 560, 960, k)
        for (a, b, s) in self.snow[:10]:
            yy = 698 + ((b + u * 0.3 * s) % 1.0) * 174
            ell(d, 648 + a * 116, yy, 7, 4, (210, 110, 40), k)
        self.lady(d, t, u, k, tv, old=True)

    def land_party(self, d, t, u, k, tv):
        self.land_room(d, k, (64, 54, 96), (50, 42, 70), (20, 24, 52), 9, None)
        cheer = u > 0.4
        talk = speaking("party", tv)
        for i, (x, col, hat) in enumerate(((520.0, (90, 170, 110), (255, 90, 120)), (600.0, (230, 150, 70), (90, 180, 255)),
                                           (690.0, (70, 110, 190), (255, 214, 90)), (770.0, (200, 90, 90), (140, 230, 140)))):
            jump = hop(u, [(0.45 + 0.08 * i, 46), (1.5 + 0.1 * i, 32)]) if cheer else 0.0
            if talk is not None:
                jump += 6 * abs(talk)
            fy = PEOPLE_FY - jump
            hands = [(x - 64, fy - 640), (x + 64, fy - 640)] if cheer else None
            person(d, k, x, fy, 1.0, col, (224, 182, 148), hands=hands, hat=hat)
        rect(d, 600, 1300, 790, 1424, (240, 240, 244), k, r=6)
        rect(d, 612, 1244, 778, 1300, (250, 200, 210), k, r=10)
        rect(d, 612, 1244, 778, 1262, (255, 250, 250), k, r=8)
        for j in range(14):
            cx = 620 + j * 11.5
            rect(d, cx - 3, 1210, cx + 3, 1246, (120, 190, 255), k)
            ell(d, cx, 1203 + 2 * math.sin(u * 20 + j), 4, 7, (255, 200, 60), k)
        for (x, ph, sp, col) in self.confetti:
            yy = 640 + ((ph + u * 0.45 * sp) % 1.0) * 760
            rect(d, x - 5, yy - 3, x + 5, yy + 3, col, k)
        rect(d, 496, 660, 806, 800, (255, 214, 90), k, r=10)
        text(d, 651, 700, "HAPPY", 44, (60, 30, 20), k)
        text(d, 651, 758, "RETIREMENT!", 38, (60, 30, 20), k)

    # -------- l'homme
    def suit_geom(self, t):
        P = self.suit.pose(t)
        x = SUIT_X(t)
        if 31.0 <= t <= 32.0:
            x += 4 * math.sin(t * 70)
        walking = abs(SUIT_X(t + 0.02) - SUIT_X(t - 0.02)) > 1.5
        fy = SUIT_FY - hop(t, SUIT_HOP) + SUIT_FG(t)
        return P, x, fy, walking

    def draw_suit(self, dr, t, tv, k):
        P, x, fy, walking = self.suit_geom(t)
        st = self.suit
        q = SUIT_Q * (1 + SUIT_FG(t) / 800.0)
        talk = speaking("man", tv)
        x, fy, k = x / q, fy / q, k * q
        a = math.radians(P["lean"] + (4 * talk if talk is not None else 0.0))
        hip_dy = P["hip"]
        sitting = hip_dy > 100
        hipy = fy - 300 + hip_dy
        legc = (30, 40, 80)
        if sitting:
            for sgn in (-1, 1):
                knee = (x - 46 + sgn * 22, hipy - 96)
                capsule(dr, (x + sgn * 22, hipy), knee, 20, legc, k)
                capsule(dr, knee, (x - 60 + sgn * 22, fy - 12), 19, legc, k)
                ell(dr, x - 70 + sgn * 22, fy - 8, 30, 14, (20, 20, 24), k)
        else:
            sw = 26 * math.sin(t * 13) if walking else 0.0
            for sgn in (-1, 1):
                foot = (x + sgn * 24 + sw * sgn, fy - 14)
                capsule(dr, (x + sgn * 22, hipy), foot, 20, legc, k)
                ell(dr, foot[0] - 8, fy - 6, 30, 14, (20, 20, 24), k)
        old = t >= 47.9
        torso = [(x - 66, hipy - 270), (x + 66, hipy - 270), (x + 60, hipy + 8), (x - 60, hipy + 8)]
        torso = [rot(px, py, x, hipy, a) for px, py in torso]
        dr.polygon(poly(torso, k), fill=NAVY)
        dr.polygon(poly([rot(px, py, x, hipy, a) for px, py in
                         [(x - 26, hipy - 270), (x + 26, hipy - 270), (x, hipy - 222)]], k), fill=(240, 240, 246))
        ta = a + 0.35 * st.tie(t)
        tie = [(x - 12, hipy - 252), (x + 12, hipy - 252), (x + 16, hipy - 120), (x, hipy - 96), (x - 16, hipy - 120)]
        cx, cy = rot(x, hipy - 252, x, hipy, a)
        tie = [rot(px - x + cx, py - (hipy - 252) + cy, cx, cy, ta - a) for px, py in
               [rot(px, py, x, hipy, a) for px, py in tie]]
        dr.polygon(poly(tie, k), fill=TIE)
        hdx, hdy = P["hd"]
        if talk is not None:
            hdy += 6 * talk
        hx, hy = rot(x + hdx, hipy - 330 + hdy, x, hipy, a)
        hr = 52.0
        beard_len = st.beard(t)
        gray = st.gray(t)
        hair_c = mix((48, 34, 26), (236, 236, 240), gray)
        beard_c = mix((70, 50, 36), (238, 238, 242), gray)
        shl = rot(x - 58, hipy - 254, x, hipy, a)
        shr = rot(x + 58, hipy - 254, x, hipy, a)
        hl = (shl[0] + P["hl"][0], shl[1] + P["hl"][1])
        hrp = (shr[0] + P["hr"][0], shr[1] + P["hr"][1])
        if talk is not None and P["name"] in ("tap", "rest", "look", "guard"):
            hrp = (hrp[0], hrp[1] - 30 - 20 * talk)
        ell(dr, hx, hy, hr, hr, SKIN, k)
        dr.chord([(hx - hr - 1) * k, (hy - hr - 1) * k, (hx + hr + 1) * k, (hy + hr + 1) * k], 212, 328, fill=hair_c)
        sb = st.stub(t)
        if sb > 0.02 and beard_len < 30:
            dr.chord([(hx - hr) * k, (hy - hr) * k, (hx + hr) * k, (hy + hr) * k], 28, 152,
                     fill=mix(SKIN, (120, 100, 90), 0.7 * sb))
        floor_y = fy - 4
        if beard_len > 1:
            chin = hy + 0.62 * hr
            bottom = min(chin + beard_len, floor_y)
            n = 14
            sway = 6 * math.sin(t * 2.0)
            left, right = [], []
            for j in range(n + 1):
                u = j / n
                yy = chin - 0.2 * hr + (bottom - chin + 0.2 * hr) * u
                w = hr * (0.8 - 0.5 * u ** 0.7) if beard_len > 60 else hr * (0.8 - 0.3 * u)
                wave = (7 * math.sin(u * 9 + t * 1.5) if beard_len > 120 else 0) + sway * u
                left.append((hx - w + wave, yy)); right.append((hx + w + wave, yy))
            pts = left + right[::-1]
            dr.chord([(hx - hr) * k, (hy - hr) * k, (hx + hr) * k, (hy + hr) * k], 30, 150, fill=beard_c)
            dr.polygon(poly(pts, k), fill=beard_c, outline=mix(beard_c, (0, 0, 0), 0.35))
            for j in range(1, 6):
                u = j / 6
                yy = chin + (bottom - chin) * u
                w = hr * (0.8 - 0.5 * u ** 0.7) * 0.5
                wave = 7 * math.sin(u * 9 + t * 1.5) if beard_len > 120 else 0
                dr.line([((hx - w + wave) * k, yy * k), ((hx + wave) * k, (yy + 10) * k), ((hx + w + wave) * k, yy * k)],
                        fill=mix(beard_c, (0, 0, 0), 0.25), width=max(1, int(3 * k)))
        if 38.76 <= t <= 39.6 and beard_len > 1:
            tip = (620.0 / q, 1140.0 / q)
            yb = hy + 0.62 * hr + min(beard_len, 260) * 0.7
            wv = 3 * math.sin(t * 40)
            dr.polygon(poly([(hx - 14, yb - 10), (hx + 14, yb + 10), (tip[0], tip[1] + 8 + wv), (tip[0], tip[1] - 8 + wv)], k),
                       fill=beard_c, outline=mix(beard_c, (0, 0, 0), 0.35))
        if 21.7 <= t <= 23.6:
            for j in range(3):
                ph = (t * 0.9 + j / 3.0) % 1.0
                text(dr, hx + 50 + 40 * ph, hy - 70 - 90 * ph, "z", 40 + 30 * ph, mix(WALLC, (200, 190, 255), 1 - ph), k)
        armc = NAVYD
        capsule(dr, shl, hl, 17, armc, k)
        capsule(dr, shr, hrp, 17, armc, k)
        ell(dr, hl[0], hl[1], 18, 18, SKIN, k)
        ell(dr, hrp[0], hrp[1], 18, 18, SKIN, k)
        # la mallette : à la main, en bouclier contre le tableau, puis par terre (x < 900)
        if t < 10.3 or 14.2 <= t < 38.76:
            if P["name"] in ("rest", "watch", "startle", "tap", "facepalm", "sag", "slouch", "sleep", "flinch",
                             "eager", "escape", "perk"):
                rect(dr, hl[0] - 44, hl[1] - 6, hl[0] + 44, hl[1] + 58, BRIEFC, k, r=8)
                rect(dr, hl[0] - 14, hl[1] - 16, hl[0] + 14, hl[1] - 4, (90, 56, 30), k, r=4)
            else:
                rect(dr, 790 / q, (SUIT_FY - 70) / q, 870 / q, (SUIT_FY - 8) / q, BRIEFC, k, r=8)
        elif 10.3 <= t < 14.2:
            kick = hop(t, [(11.41, 60)])
            bx0 = (BRIEF_X - R - 36) / q
            by0 = (1060 - kick) / q
            rect(dr, bx0, by0, bx0 + 36 / q, by0 + 150 / q, BRIEFC, k, r=6)
        else:
            rect(dr, 790 / q, (SUIT_FY - 70) / q, 870 / q, (SUIT_FY - 8) / q, BRIEFC, k, r=8)
        if old:
            if P["name"] in ("guard", "guard_hi", "look") or t >= 50.2:
                # la canne en garde devant le tableau
                gx0, gy0 = (Plan.cane_x(700.0) - 6) / q, 700.0 / q
                gx1, gy1 = (Plan.cane_x(1400.0) - 6) / q, 1400.0 / q
                lift = KF(0.0, [(53.15, 0.0), (53.3, -1.0), (53.7, -1.0), (53.9, 0.0)])(t)
                for tc in (50.45, 51.20, 53.40, 55.00, 55.75):    # il pare : la canne part vers la balle
                    u = t - (tc - 0.12)
                    if 0 <= u <= 0.35:
                        jab = (40 if tc == 55.75 else 24) * math.sin(math.pi * u / 0.35) / q
                        gx0 += jab; gx1 += jab * 0.4
                top = gy0 + lift * 120 / q
                bot = gy1 + lift * 120 / q
                cc = (182, 124, 66)
                for (wd, col) in ((24, (60, 40, 24)), (16, cc)):           # canne à crosse, cernée
                    dr.line([(gx0 * k, top * k), (gx1 * k, bot * k)], fill=col, width=max(1, int(wd * k)))
                    dr.arc([(gx0 - 72) * k, (top - 36) * k, gx0 * k, (top + 36) * k], 180, 360, fill=col,
                           width=max(1, int(wd * k)))
                    dr.line([((gx0 - 72) * k, top * k), ((gx0 - 72) * k, (top + 26) * k)], fill=col,
                            width=max(1, int(wd * k)))
            else:
                cxh = hrp
                dr.line([(cxh[0] * k, cxh[1] * k), ((cxh[0] + 24) * k, (fy - 4) * k)], fill=(150, 104, 60),
                        width=max(1, int(12 * k)))

    def draw_beard_pool(self, dr, t, k):
        p = self.suit.pool(t)
        if p < 2:
            return
        P, x, fy, walking = self.suit_geom(t)
        gray = self.suit.gray(t)
        beard_c = mix((70, 50, 36), (238, 238, 242), gray)
        x0 = x - 6
        x1 = x0 + p
        if x > 540:
            x1, x0 = x0, x0 - p
        bx, by = self.P.pos(t)
        dent = 0.0
        if by > FY - 2 and x0 < bx < x1 + 40:
            dent = min(26.0, (by - FY + 2) * 1.5)
        top, bot = [], []
        for i in range(25):
            xx = x0 + (x1 - x0) * i / 24
            d = dent * math.exp(-((xx - bx) / 80.0) ** 2)
            yc = FLOOR + 4 + 6 * math.sin(xx * 0.05) + d * 0.6
            hh = 34 + 8 * math.sin(xx * 0.11)
            top.append((xx, yc - hh)); bot.append((xx, yc + hh * 0.5))
        pts = top + bot[::-1]
        dr.polygon(poly(pts, k), fill=beard_c, outline=mix(beard_c, (0, 0, 0), 0.35))


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 99.0, "hook_top": 0.125, "hook_font_size": 100, "hook_speed": 1.05, "hook_max_s": 0.95,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.95, "watermark_alpha": 0.4, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}


def exact_events(sim):
    return [(v, "hit", "h%d" % i) for i, v in enumerate(sim.hit_v)]


def render_audio(sim, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(exact_events(sim), total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        lag = 1.0 / cfg["fps"]       # le son part au plus une image après l'image du contact (A9), jamais avant
        for (t0, kind, _d, tag) in words:
            gg = sim.hit_gain(t0) * 0.92
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0 + lag, gain=gg)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=LINE_GAIN.get(n["key"], 1.0))
    v = hook_clip(cfg) if cfg.get("hook_voice") else None
    if v is not None:
        a, n = int(HOOK_T * SR), len(v)
        duck = np.ones(len(buf))
        duck[a:a + n] = 0.42
        m = int(0.3 * SR)
        duck[a + n:a + n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, HOOK_T, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


def stats(sim):
    hits = [e[0] for e in exact_events(sim)]
    iv = np.diff(hits)
    out = {"hits": len(hits), "iv_min": round(float(iv.min()), 2), "iv_max": round(float(iv.max()), 2),
           "iv_med": round(float(np.median(iv)), 2), "cv": round(float(iv.std() / iv.mean()), 3)}
    best = 1
    for i in range(len(iv)):
        j = i
        while j + 1 < len(iv) and all(abs(iv[j + 1] - iv[q]) <= 0.1 * iv[q] for q in range(i, j + 1)):
            j += 1
        best = max(best, j - i + 1)
    out["max_run_equal"] = best
    pre = [h for h in hits if h < video(ISSUE_W)]
    ivp = np.diff(pre)
    out["cv_pre_issue"] = round(float(ivp.std() / ivp.mean()), 3)
    out["iv_pre"] = [round(float(x), 2) for x in ivp]
    ap = sim.P.apexes()
    out["arcs_through_ceiling"] = [(round(a, 2), round(b, 2), round(top, 1)) for (a, b, top, v, kd) in ap
                                   if top < CY - 1]
    out["ceil_not_rising"] = [round(b, 2) for (a, b, top, v, kd) in ap if kd == "ceil" and v > 0]
    out["rise_max_px"] = round(max(FY - a[2] for a in ap), 1)
    return out


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr],
               "word_len": round(len(name) / SR, 3),
               "muets": [round(e[0], 3) for e in ev if round(e[0], 3) not in said],
               "issue_video": round(video(ISSUE_W), 2)}
    if hv is not None:
        summary["contacts_sous_l_accroche"] = [round(e[0], 2) for e in ev
                                               if e[0] + len(name) / SR > HOOK_T - 0.05 and e[0] < HOOK_T + len(hv) / SR + 0.05]
    summary.update(stats(sim))
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, dur, cfg, audio, narr)
        base.render_video(theme, sim, states, cfg, audio, out, events, ())
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, base.ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
