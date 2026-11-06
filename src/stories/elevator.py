"""
Prototype « elevator » : Bounce est dans un ascenseur avec un homme pressé qui veut l'étage 9. Chaque
fois que Bounce cogne le panneau, un bouton s'allume : l'ascenseur s'arrête à chaque étage. Derrière les
portes, le temps passe (9 h, midi, le soir, la nuit, l'hiver, l'été) et la barbe de l'homme pousse. Au 9,
au ralenti, Bounce frappe le bouton « fermer » (celui que l'homme martelait pour rien) : les portes lui
claquent au nez. Redescente, la dame du 3 a vieilli (« Still the stairs. »). L'homme, vieux, couvre le
panneau de tout son corps : montée express. Les portes s'ouvrent sur le 9 : son pot de départ en retraite.
« Happy retirement! » — « I just got here. »

Tout est écrit dans le temps « monde » ; un ralenti (L1) étire 0,42 s de monde sur 1,4 s de vidéo.
Les contacts durs sont posés à leurs instants exacts : l'audio est le même quel que soit le nombre
d'images par seconde. La résolution de la config est libre (aperçu 540×960).

    python3 src/stories/elevator.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import font
from PIL import Image, ImageDraw
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/elevator/bank"

# ------------------------------------------------------------------ voix des personnages (banque vérifiée par whisper)
BANK_FILES = {"Come on, come on!": "come.wav", "I'll take the stairs.": "stairs.wav", "No!": "noo.wav",
              "Still the stairs.": "still.wav", "Happy retirement!": "party.wav", "I just got here.": "got.wav"}
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

# le mot de Bounce : une prise fixe, gardée dans la banque (aperçu et rendu final identiques)
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
HOOK_T = 0.88
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
            f = max(cfg.get("hook_speed", 1.05), len(v) / SR / cfg.get("hook_max_s", 1.08))
            v = base.pitch(v, f)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ le temps : ralenti (L1)
SLO_A = 38.70          # début du ralenti (vidéo = monde)
SLO_V = 1.40           # durée vidéo
SLO_F = 0.30           # vitesse du monde pendant le ralenti
SLO_W = SLO_V * SLO_F
SHIFT = SLO_V - SLO_W  # après le ralenti, vidéo = monde + SHIFT


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


END_W = 61.47          # fin, en temps monde (vidéo 62,45 s)
ISSUE_W = 57.55        # les portes du 9 finissent de s'ouvrir sur la fête

# ------------------------------------------------------------------ géométrie (écran 1080×1920)
W, H = 1080, 1920
G = 2600.0
R = 118.0
CEIL = 500.0                  # face du plafond
FLOOR = 1200.0                # tapis / sol (Bounce y touche)
CY = CEIL + R                 # centre de Bounce au plafond
FY = FLOOR - R                # centre de Bounce au sol
DOOR = (290.0, 710.0, 600.0, FLOOR)
PAN = (165.0, 265.0, 560.0, 1130.0)      # panneau gauche (celui de Bounce)
PX = PAN[1] + R
PANR = (706.0, 754.0, 800.0, 960.0)      # petit panneau droit (celui de l'homme)
STEEL_X = 630.0
BRIEF_X = 452.0
RUG = (300.0, 590.0)


def btn_y(n):
    if n in ("open", "close"):
        return 1090.0
    return 1030.0 - (n - 1) * 55.0


BTN_X = {"open": 192.0, "close": 240.0}

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


# ------------------------------------------------------------------ le plan (temps monde)
# contacts durs : (t, genre, argument) ; pan = panneau gauche (allume un bouton), ceil = plafonnier,
# steel = sol nu (métal) à côté de l'homme, brief = la mallette, cane = la canne
HITS = [
    (0.12, "pan", 2), (2.15, "pan", 3), (4.30, "pan", 4), (5.35, "pan", 5), (6.50, "ceil", 628),
    (7.45, "pan", 6),
    (9.65, "pan", 7), (10.80, "ceil", 646), (11.85, "brief", 0), (13.00, "pan", 8), (14.05, "ceil", 640),
    (15.35, "steel", 0), (16.35, "ceil", 640), (17.55, "steel", 0), (18.50, "ceil", 646), (19.75, "pan", 3),
    (20.75, "ceil", 646), (21.70, "steel", 0),
    (23.65, "ceil", 646), (24.80, "steel", 0), (25.75, "ceil", 640), (26.90, "pan", "open"),
    (28.15, "ceil", 646), (29.10, "steel", 0), (30.35, "ceil", 640), (31.30, "steel", 0), (32.50, "ceil", 646),
    (33.45, "steel", 0), (34.65, "ceil", 640), (35.80, "steel", 0), (36.80, "ceil", 646),
    (37.85, "steel", 0),
    (39.20, "pan", "close"), (40.20, "pan", 1), (41.35, "ceil", 646), (42.30, "steel", 0),
    (43.55, "ceil", 640), (44.50, "steel", 0),
    (46.75, "ceil", 646), (47.75, "steel", 0), (49.05, "ceil", 646), (50.05, "steel", 0),
    (50.95, "cane", 0), (52.20, "ceil", 646), (53.20, "steel", 0), (54.45, "ceil", 646), (55.65, "steel", 0),
    (60.47, "steel", 0),
]
# contacts mous imposés (t, x, creux) ; les autres sont ajoutés pour qu'aucun arc ne monte trop haut
SOFT_FIX = [(38.45, 470.0, 22.0), (56.20, 590.0, 26.0), (56.80, 600.0, 30.0), (57.40, 585.0, 26.0),
            (58.05, 600.0, 30.0), (58.70, 590.0, 26.0), (59.30, 605.0, 28.0), (59.92, 590.0, 26.0),
            (61.00, 600.0, 26.0), (61.55, 590.0, 24.0)]
# arrêts : (étage, ding) ; portes : clés d'ouverture (0 fermé, 1 ouvert)
STOPS = [(2, 2.00), (3, 6.30), (4, 12.70), (5, 18.00), (6, 23.20), (7, 29.60), (8, 32.90), (9, 37.90),
         (3, 44.30), (1, 49.00), (9, 57.10)]
DOOR_KEYS = [(2.05, 0), (2.45, 1), (4.45, 1), (5.15, 0),
             (6.35, 0), (6.75, 1), (9.70, 1), (10.30, 0),
             (12.75, 0), (13.15, 1), (16.00, 1), (16.60, 0),
             (18.05, 0), (18.45, 1), (20.90, 1), (21.50, 0),
             (23.25, 0), (23.65, 1), (26.10, 1), (26.90, 0.35), (27.25, 1), (28.00, 1), (28.60, 0),
             (29.65, 0), (30.05, 1), (31.40, 1), (31.90, 0),
             (32.95, 0), (33.35, 1), (34.70, 1), (35.20, 0),
             (37.95, 0), (38.35, 1), (39.20, 1), (39.27, 0),
             (44.35, 0), (44.75, 1), (47.20, 1), (47.80, 0),
             (57.15, 0), (ISSUE_W, 1)]
# scène derrière les portes, par fenêtre d'ouverture
SCENES = [(2.0, 5.2, "morning"), (6.3, 10.3, "lady"), (12.7, 16.6, "noon"), (18.0, 21.5, "sunset"),
          (23.2, 28.6, "night"), (29.6, 31.9, "winter"), (32.9, 35.2, "summer"), (37.9, 39.3, "office"),
          (44.3, 47.8, "oldlady"), (57.1, 99.0, "party")]
FLOORS = [(0, 1), (1.40, 2), (5.80, 3), (11.90, 4), (17.40, 5), (22.60, 6), (28.95, 7), (32.40, 8), (37.30, 9),
          (41.00, 8), (41.50, 7), (42.00, 6), (42.50, 5), (43.05, 4), (43.65, 3), (48.30, 2), (48.85, 1),
          (50.90, 2), (51.50, 3), (52.10, 4), (52.75, 5), (53.40, 6), (54.00, 7), (54.65, 8), (57.10, 9)]
ARROW = [(0, 1), (40.25, -1), (50.30, 1)]
LIGHTS = {9: [(-1, 37.90), (50.20, 57.10)], 2: [(0.12, 2.00)], 3: [(2.15, 6.30), (19.75, 44.30)],
          4: [(4.30, 12.70)], 5: [(5.35, 18.00)], 6: [(7.45, 23.20)], 7: [(9.65, 29.60)], 8: [(13.00, 32.90)],
          1: [(40.20, 49.00)], "open": [(26.90, 27.40)], "close": [(39.20, 39.75)]}
# répliques (temps vidéo)
LINES = [(3.05, "Come on, come on!", "come"), (8.40, "I'll take the stairs.", "stairs"),
         (38.78, "No!", "noo"), (46.40, "Still the stairs.", "still"),
         (58.58, "Happy retirement!", "party"), (60.23, "I just got here.", "got")]
LINE_GAIN = {"come": 0.95, "stairs": 0.9, "noo": 1.05, "still": 0.9, "party": 1.0, "got": 1.05}


def ceil_x(arg):
    return float(arg)


class Plan:
    def __init__(self):
        cs = []
        for (t, kind, arg) in HITS:
            if kind == "pan":
                y = min(FY - 4, max(CY, btn_y(arg)))
                cs.append({"t": t, "x": PX, "y": y, "axis": "x", "soft": False, "kind": kind, "arg": arg})
            elif kind == "ceil":
                cs.append({"t": t, "x": ceil_x(arg), "y": CY, "axis": "y", "soft": False, "kind": kind, "arg": arg})
            elif kind == "steel":
                cs.append({"t": t, "x": STEEL_X, "y": FY, "axis": "y", "soft": False, "kind": kind, "arg": arg})
            elif kind == "brief":
                cs.append({"t": t, "x": BRIEF_X, "y": 905.0, "axis": "x", "soft": False, "kind": kind, "arg": arg})
            elif kind == "cane":
                cs.append({"t": t, "x": 492.0, "y": FY - 6, "axis": "x", "soft": False, "kind": kind, "arg": arg})
        for (t, x, dent) in SOFT_FIX:
            cs.append({"t": t, "x": x, "y": FY + dent * 0.6, "axis": "y", "soft": True, "kind": "soft", "dent": dent})
        cs.sort(key=lambda c: c["t"])
        start = {"t": -0.45, "x": 470.0, "y": FY + 10, "kind": "soft", "soft": True}
        full = []
        prev = start
        k = 0
        for c in cs:
            gap = c["t"] - prev["t"]
            lim = 0.56 if (c["kind"] == "ceil" or prev.get("kind") == "ceil") else 0.72
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
        self.after = {"t": END_W + 0.6, "x": 505.0, "y": FY + 10}
        self.ts = [c["t"] for c in full]
        self.hits = [c for c in full if not c["soft"]]

    @staticmethod
    def soft_x(t, k, a, b, u):
        x = lerp(a["x"], b["x"], u)
        # portes ouvertes : il reste sur la gauche du tapis, la scène du palier reste lisible
        doors_open = any(s0 <= t <= s1 for (s0, s1, _n) in SCENES)
        lo, hi = (405.0, 440.0) if doors_open else (430.0, 580.0)
        if t > 55.5:
            lo, hi = 575.0, 610.0
        x = max(lo, min(hi, x + (22 if k % 2 else -22)))
        return x

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
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.contacts[max(0, i - 1):i + 4]:
            u = t - c["t"]
            if -0.06 <= u <= 0.14:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / 0.14)
                amp = 0.2 if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def apexes(self):
        """Contrôle physique : point le plus haut de chaque arc, sens d'arrivée au plafond."""
        out = []
        prev = self.start
        for c in self.contacts:
            T = c["t"] - prev["t"]
            vy = (c["y"] - prev["y"]) / T - 0.5 * G * T
            ta = -vy / G
            top = prev["y"] + vy * ta + 0.5 * G * ta * ta if 0 < ta < T else min(prev["y"], c["y"])
            out.append((prev["t"], c["t"], top, vy + G * T))
            prev = c
        return out


# ------------------------------------------------------------------ l'homme pressé
# poses : lean (degrés, + vers la droite), mains gauche/droite (dx, dy) depuis l'épaule, tête (dx, dy), hanche dy
POSES = {
    "rest": dict(lean=0, hl=(-26, 236), hr=(16, 230), hd=(0, 0), hip=0),
    "startle": dict(lean=5, hl=(-40, 220), hr=(40, 200), hd=(-16, -8), hip=0),
    "watch": dict(lean=0, hl=(-26, 236), hr=(-70, 110), hd=(-14, 10), hip=0),
    "jab": dict(lean=-13, hl=(-100, 175), hr=(16, 230), hd=(-22, 4), hip=0),
    "facepalm": dict(lean=-3, hl=(-26, 236), hr=(-66, -40), hd=(-4, 14), hip=0),
    "shield": dict(lean=-4, hl=(70, 40), hr=(78, 110), hd=(14, 0), hip=0),
    "stagger": dict(lean=-8, hl=(10, -150), hr=(-20, -150), hd=(-10, 6), hip=0),
    "sag": dict(lean=-2, hl=(-20, 250), hr=(20, 250), hd=(0, 22), hip=6),
    "flinch": dict(lean=10, hl=(-30, 120), hr=(40, 120), hd=(14, -4), hip=0),
    "slouch": dict(lean=6, hl=(-16, 250), hr=(20, 250), hd=(6, 26), hip=10),
    "sleep": dict(lean=7, hl=(-12, 262), hr=(16, 262), hd=(10, 50), hip=12),
    "jolt": dict(lean=-4, hl=(-90, 60), hr=(90, 60), hd=(0, -14), hip=-10),
    "armsup": dict(lean=0, hl=(-60, -150), hr=(60, -150), hd=(0, -10), hip=0),
    "shiver": dict(lean=0, hl=(70, 90), hr=(-70, 90), hd=(0, 18), hip=4),
    "eager": dict(lean=-12, hl=(-110, 100), hr=(20, 200), hd=(-24, 0), hip=0),
    "bonk": dict(lean=14, hl=(-40, 60), hr=(40, 60), hd=(18, -6), hip=0),
    "sit": dict(lean=4, hl=(-30, 200), hr=(30, 200), hd=(4, 40), hip=250),
    "old": dict(lean=-10, hl=(-26, 236), hr=(26, 200), hd=(-10, 46), hip=24),
    "press9": dict(lean=-14, hl=(-96, 70), hr=(26, 200), hd=(-18, 40), hip=24),
    "hug": dict(lean=0, hl=(-62, 60), hr=(62, 60), hd=(0, 30), hip=18),
    "look": dict(lean=4, hl=(-80, -10), hr=(70, 110), hd=(22, 34), hip=22),
}
SUIT_KEYS = [(0.0, "rest", 0.1), (0.14, "startle", 0.1), (0.7, "rest", 0.3), (1.1, "watch", 0.25),
             (2.2, "rest", 0.2), (2.6, "jab", 0.15), (4.45, "rest", 0.25), (5.40, "facepalm", 0.2),
             (6.40, "rest", 0.3), (10.2, "shield", 0.35), (11.86, "stagger", 0.12), (12.4, "shield", 0.25),
             (13.05, "sag", 0.25), (14.2, "rest", 0.3), (15.36, "flinch", 0.1), (15.8, "rest", 0.3),
             (17.56, "flinch", 0.1), (18.0, "slouch", 0.5), (20.8, "slouch", 0.1), (21.75, "sleep", 0.9),
             (23.66, "jolt", 0.08), (24.1, "slouch", 0.4), (24.81, "flinch", 0.1), (25.3, "slouch", 0.4),
             (26.95, "armsup", 0.15), (27.8, "slouch", 0.4), (29.11, "flinch", 0.1), (29.6, "shiver", 0.3),
             (31.31, "flinch", 0.1), (31.7, "slouch", 0.4), (33.46, "flinch", 0.1), (33.9, "slouch", 0.4),
             (35.81, "flinch", 0.1), (36.3, "slouch", 0.4), (37.86, "flinch", 0.08), (37.98, "eager", 0.25),
             (39.21, "bonk", 0.05), (39.6, "stagger", 0.2), (40.1, "sit", 0.45), (47.9, "old", 0.45),
             (48.30, "old", 0.2), (50.12, "press9", 0.15), (50.5, "hug", 0.3), (57.7, "look", 0.5)]
SUIT_X = KF(840.0, [(10.2, 840.0), (11.25, 205.0), (11.86, 205.0), (12.15, 180.0), (14.2, 180.0), (15.25, 840.0), (38.05, 840.0), (39.18, 600.0),
                    (39.21, 600.0), (39.55, 700.0), (40.1, 820.0), (48.4, 820.0), (50.2, 215.0)])
# il traverse au premier plan (plus près de nous : plus bas, plus gros)
SUIT_FG = KF(0.0, [(10.2, 0.0), (10.72, 80.0), (11.25, 0.0), (14.2, 0.0), (14.72, 80.0), (15.25, 0.0),
                   (48.4, 0.0), (49.3, 90.0), (50.2, 0.0)])
SUIT_Q = 1.12
SUIT_HOP = [(0.14, 18), (23.66, 30), (38.0, 26)]
FLINCH = [h[0] for h in HITS if h[1] == "steel"]


def hop(t, hops):
    y = 0.0
    for (t0, h) in hops:
        T = 2 * math.sqrt(2 * h / G)
        u = t - t0
        if 0 <= u <= T:
            y = max(y, h - 0.5 * G * (u - T / 2) ** 2)
    return y


class Suit:
    def __init__(self):
        self.ts = [k[0] for k in SUIT_KEYS]
        # la barbe : longueur (px depuis le menton), puis le tas au sol
        self.beard = KF(0.0, [(16.5, 0.0), (19.0, 40.0), (23.0, 90.0), (29.0, 170.0), (32.5, 260.0),
                              (35.0, 340.0), (39.0, 420.0), (44.0, 520.0), (48.0, 640.0)])
        self.pool = KF(0.0, [(46.0, 0.0), (49.0, 120.0), (53.0, 330.0), (56.0, 390.0)])
        self.stub = KF(0.0, [(12.0, 0.0), (15.5, 1.0)])
        self.gray = KF(0.0, [(26.0, 0.0), (33.0, 0.55), (41.0, 0.8), (47.0, 1.0)])
        self.tie = KF(0.0, [(14.5, 0.0), (15.2, 1.0)])

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
           scarf=None, glasses=False, hunch=0.0):
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
        dr.chord([(hx - 49 * s) * k, (hy - 49 * s) * k, (hx + 49 * s) * k, (hy + 49 * s) * k], 190, 350, fill=hair)
    if bun:
        ell(dr, hx + 8 * s, hy - 56 * s, 24 * s, 22 * s, bun, k)
        dr.chord([(hx - 49 * s) * k, (hy - 49 * s) * k, (hx + 49 * s) * k, (hy + 49 * s) * k], 185, 355, fill=bun)
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
        self.ceil_hits = [(c["t"], c["x"]) for c in self.P.hits if c["kind"] == "ceil"]
        self.rng = np.random.default_rng(5)
        self.confetti = [(self.rng.uniform(300, 700), self.rng.uniform(0, 1), self.rng.uniform(0.6, 1.3),
                          [(255, 214, 90), (90, 200, 255), (255, 110, 160), (140, 230, 140)][i % 4])
                         for i in range(46)]
        self.snow = [(self.rng.uniform(0, 1), self.rng.uniform(0, 1), self.rng.uniform(0.5, 1.0)) for _ in range(26)]

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
                best, bd = (1.15 if c["kind"] == "pan" and c["arg"] in ("close", "open") else
                            0.85 if c["kind"] == "steel" else 1.0), abs(v - tv)
        return best

    # ---------------------------------------------------------- état
    def floor_at(self, t):
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
        for (th, _x) in self.ceil_hits:
            u = t - th
            if 0 <= u <= 0.22:
                f = min(f, 0.45 + 0.55 * (u / 0.22))
        return f

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, tv, S):
        tv = float(tv)
        t = world(tv)
        k = S * self.cfg["width"] / W
        img = dr._image
        self.draw_cabin(dr, t, k)
        o = self.door(t)
        if o > 0.002:
            self.draw_landing(img, t, k, o)
        self.draw_doors(dr, t, k, o)
        self.draw_display(dr, t, k)
        self.draw_panel(dr, t, k)
        self.draw_panel_r(dr, t, k)
        self.draw_floor(dr, t, k)
        self.draw_shadow(dr, t, k)
        self.draw_suit(dr, t, k, back=True)
        self.draw_rings(dr, t, k)
        base.HERO["expr"] = self.expr_at(t)
        bx, by = self.P.pos(t)
        sx, sy = self.P.squash(t)
        if abs(sx - sy) < 0.01:
            base.ball(dr, bx * k, by * k, R * k)
        else:
            self.draw_ball(dr, bx, by, R * sx, R * sy, k)
        self.draw_suit(dr, t, k, back=False)
        if SLO_A <= tv <= SLO_A + SLO_V:
            self.draw_slowmo(dr, tv, k)

    def expr_at(self, t):
        if t >= ISSUE_W + 1.2:
            return "win"
        if ISSUE_W - 0.2 <= t < ISSUE_W + 1.2:
            return "shock"
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
        # parois latérales en perspective
        dr.polygon(poly([(0, 430), (120, 500), (120, FLOOR), (0, FLOOR + 90)], k), fill=WALLD)
        dr.polygon(poly([(W, 430), (960, 500), (960, FLOOR), (W, FLOOR + 90)], k), fill=WALLD)
        for x in range(140, 960, 46):
            dr.line([(x * k, 505 * k), (x * k, (FLOOR - 4) * k)], fill=(60, 64, 80), width=max(1, int(2 * k)))
        # main courante
        rect(dr, 120, 930, 280, 946, (90, 94, 110), k, r=6)
        rect(dr, 720, 930, 960, 946, (90, 94, 110), k, r=6)
        # plafond et plafonnier
        dr.polygon(poly([(0, 400), (W, 400), (960, CEIL), (120, CEIL)], k), fill=CEILC)
        f = self.flicker(t)
        col = mix((70, 70, 64), LIGHT, f)
        rect(dr, 330, CEIL - 22, 690, CEIL, col, k, r=6)
        if f > 0.9:
            dr.polygon(poly([(330, CEIL), (690, CEIL), (760, CEIL + 40), (260, CEIL + 40)], k), fill=(64, 68, 82))

    def draw_floor(self, dr, t, k):
        dr.polygon(poly([(120, FLOOR), (960, FLOOR), (W, FLOOR + 90), (W, H), (0, H), (0, FLOOR + 90)], k),
                   fill=FLOORC)
        for j in range(1, 9):
            y = FLOOR + 40 * j + 6 * j * j
            if y > H:
                break
            dr.line([(0, y * k), (W * k, y * k)], fill=(52, 54, 66), width=max(1, int(3 * k)))
        # tapis épais (mou) : il se creuse sous Bounce
        bx, by = self.P.pos(t)
        dent = 0.0
        if by > FY - 2 and RUG[0] < bx < RUG[1] + 30:
            dent = min(30.0, (by - FY + 2) * 1.7)
        top = []
        for i in range(25):
            x = RUG[0] + (RUG[1] - RUG[0]) * i / 24
            d = dent * math.exp(-((x - bx) / 90.0) ** 2)
            top.append((x, FLOOR - 8 + d))
        RB = 1730.0
        pts = top + [(RUG[1] + 190, RB), (RUG[0] - 190, RB)]
        dr.polygon(poly(pts, k), fill=RUGC)

        def rx(xr, yy):
            u = (yy - FLOOR) / (RB - FLOOR)
            return RUG[0] - 190 * u + (RUG[1] - RUG[0] + 380 * u) * xr
        inner = [(rx(0.06, FLOOR + 40), FLOOR + 40), (rx(0.94, FLOOR + 40), FLOOR + 40), (rx(0.94, RB - 40), RB - 40),
                 (rx(0.06, RB - 40), RB - 40)]
        dr.polygon(poly(inner, k), outline=(196, 150, 90), width=max(1, int(8 * k)))
        for j in range(3):
            yc = FLOOR + 110 + j * 120 + j * j * 8
            hh = 44 + 10 * j
            for xr in (0.25, 0.5, 0.75):
                xc = rx(xr, yc)
                dr.polygon(poly([(xc, yc - hh), (xc + hh * 1.1, yc), (xc, yc + hh), (xc - hh * 1.1, yc)], k),
                           fill=RUGD)
                dr.polygon(poly([(xc, yc - hh * 0.4), (xc + hh * 0.45, yc), (xc, yc + hh * 0.4), (xc - hh * 0.45, yc)], k),
                           fill=(196, 150, 90))
        for i in range(0, 25, 2):
            x, y = top[i]
            dr.line([(x * k, y * k), ((x - 6) * k, (y - 10) * k)], fill=(150, 66, 78), width=max(1, int(4 * k)))
        # la barbe au sol (un tapis de plus)
        self.draw_beard_pool(dr, t, k)

    def draw_shadow(self, dr, t, k):
        bx, by = self.P.pos(t)
        h = clamp01((FY - by) / 500.0)
        ell(dr, bx, FLOOR + 6, R * (0.95 - 0.4 * h), 16 * (1 - 0.5 * h), (24, 20, 28), k)

    def draw_rings(self, dr, t, k):
        for c in self.P.hits:
            u = t - c["t"]
            if not (0 <= u <= 0.3):
                continue
            a = 1 - u / 0.3
            rr = 30 + 120 * u / 0.3
            if c["kind"] == "ceil":
                cx, cy = c["x"], CEIL
            elif c["axis"] == "x":
                cx, cy = c["x"] - R, c["y"]
            else:
                cx, cy = c["x"], c["y"] + R
            col = mix(WALLC, (255, 240, 200), a)
            ell(dr, cx, cy, rr, rr * 0.8, None, k, outline=col, width=6)

    def draw_slowmo(self, dr, tv, k):
        u = (tv - SLO_A) / SLO_V
        a = clamp01(min(u, 1 - u) * 8)
        col = mix(WALLC, (255, 255, 255), 0.35 * a)
        for (x0, y0, x1, y1) in ((130, 1000, 130, 1180), (950, 1000, 950, 1180)):
            dr.line([(x0 * k, y0 * k), (x1 * k, y1 * k)], fill=col, width=max(1, int(4 * k)))

    # -------- portes, palier
    def draw_doors(self, dr, t, k, o):
        x0, x1, y0, y1 = DOOR
        rect(dr, x0 - 16, y0 - 16, x1 + 16, y0, (88, 92, 108), k)
        dr.line([((x0 - 8) * k, y0 * k), ((x0 - 8) * k, y1 * k)], fill=(88, 92, 108), width=max(1, int(16 * k)))
        dr.line([((x1 + 8) * k, y0 * k), ((x1 + 8) * k, y1 * k)], fill=(88, 92, 108), width=max(1, int(16 * k)))
        half = (x1 - x0) / 2
        w = half * (1 - o)
        if w > 0.5:
            mid = (x0 + x1) / 2
            for (a, b) in ((x0, x0 + w), (x1 - w, x1)):
                rect(dr, a, y0, b, y1, STEELC, k)
                for j in range(3):
                    xx = a + (b - a) * (j + 1) / 4
                    dr.line([(xx * k, (y0 + 10) * k), (xx * k, (y1 - 10) * k)], fill=STEELL, width=max(1, int(2 * k)))
            if o < 0.02:
                dr.line([(mid * k, y0 * k), (mid * k, y1 * k)], fill=(70, 74, 88), width=max(1, int(4 * k)))

    def draw_display(self, dr, t, k):
        rect(dr, 372, 512, 536, 590, (14, 14, 18), k, r=10)
        f = self.floor_at(t)
        flash = any(0 <= t - d <= 0.5 for (_f, d) in STOPS)
        col = (255, 120, 80) if not flash else (255, 236, 150)
        text(dr, 482, 553, str(f), 66, col, k)
        a = self.arrow_at(t)
        cx, cy = 416, 551
        if a > 0:
            pts = [(cx - 20, cy + 14), (cx + 20, cy + 14), (cx, cy - 18)]
        else:
            pts = [(cx - 20, cy - 14), (cx + 20, cy - 14), (cx, cy + 18)]
        dr.polygon(poly(pts, k), fill=col)

    def draw_panel(self, dr, t, k):
        x0, x1, y0, y1 = PAN
        rect(dr, x0, y0, x1, y1, (96, 100, 116), k, r=12)
        rect(dr, x0 + 6, y0 + 6, x1 - 6, y1 - 6, (78, 82, 98), k, r=10)
        cx = (x0 + x1) / 2
        for n in range(1, 10):
            y = btn_y(n)
            on = self.lit(n, t)
            pulse = 0.0
            for c in self.P.hits:
                if c["kind"] == "pan" and c["arg"] == n and 0 <= t - c["t"] <= 0.35:
                    pulse = 1 - (t - c["t"]) / 0.35
            if on:
                ell(dr, cx, y, 30, 30, (120, 96, 40), k)
            if pulse > 0:
                rr = 30 + 60 * (1 - pulse)
                ell(dr, cx, y, rr, rr, None, k, outline=mix(WALLC, LIT, pulse), width=6)
            ell(dr, cx, y, 23, 23, LIT if on else (40, 42, 52), k, outline=(150, 154, 170), width=3)
            text(dr, cx, y + 1, str(n), 30, (30, 24, 10) if on else (200, 204, 216), k)
        if 38.45 <= t <= 39.2:                 # au ralenti : la cible
            ph = (t - 38.45) * 9
            rr = 30 + 6 * math.sin(ph * 6)
            ell(dr, BTN_X["close"], btn_y("close"), rr, rr, None, k, outline=(110, 230, 140), width=4)
        for key in ("open", "close"):
            bxx, y = BTN_X[key], btn_y(key)
            on = self.lit(key, t)
            rect(dr, bxx - 21, y - 17, bxx + 21, y + 17, (110, 230, 140) if on else (40, 42, 52), k, r=6,
                 outline=(150, 154, 170), width=3)
            ic = (20, 40, 20) if on else (200, 204, 216)
            if key == "open":
                pts1 = [(bxx - 4, y - 9), (bxx - 4, y + 9), (bxx - 15, y)]
                pts2 = [(bxx + 4, y - 9), (bxx + 4, y + 9), (bxx + 15, y)]
            else:
                pts1 = [(bxx - 15, y - 9), (bxx - 15, y + 9), (bxx - 4, y)]
                pts2 = [(bxx + 15, y - 9), (bxx + 15, y + 9), (bxx + 4, y)]
            dr.polygon(poly(pts1, k), fill=ic)
            dr.polygon(poly(pts2, k), fill=ic)

    def draw_panel_r(self, dr, t, k):
        x0, x1, y0, y1 = PANR
        rect(dr, x0, y0, x1, y1, (96, 100, 116), k, r=8)
        cx = (x0 + x1) / 2
        on9 = self.lit(9, t)
        ell(dr, cx, 838, 16, 16, LIT if on9 else (40, 42, 52), k, outline=(150, 154, 170), width=2)
        text(dr, cx, 839, "9", 20, (30, 24, 10) if on9 else (200, 204, 216), k)
        jab = 2.6 <= t <= 4.45 and math.sin(2 * math.pi * 7 * t) > 0.3
        rect(dr, cx - 20, 904, cx + 20, 938, (110, 230, 140) if jab else (40, 42, 52), k, r=5,
             outline=(150, 154, 170), width=3)
        ic = (20, 40, 20) if jab else (200, 204, 216)
        dr.polygon(poly([(cx - 12, 914), (cx - 12, 928), (cx - 3, 921)], k), fill=ic)
        dr.polygon(poly([(cx + 12, 914), (cx + 12, 928), (cx + 3, 921)], k), fill=ic)

    def draw_landing(self, img, t, k, o):
        x0, x1, y0, y1 = DOOR
        L = Image.new("RGB", img.size, BG)
        d = ImageDraw.Draw(L)
        name, u = self.scene_at(t)
        getattr(self, "land_" + (name or "morning"))(d, t, u, k)
        half = (x1 - x0) / 2 * o
        mid = (x0 + x1) / 2
        box = (int((mid - half) * k), int(y0 * k), int((mid + half) * k), int(y1 * k))
        if box[2] > box[0]:
            img.paste(L.crop(box), box[:2])

    # les paliers : mur, fenêtre, horloge, numéro, gens
    def land_room(self, d, k, wall, floor, sky, n, clock=None, lights=1.0):
        rect(d, 250, 560, 760, 1210, wall, k)
        rect(d, 250, 1150, 760, 1210, floor, k)
        rect(d, 312, 660, 446, 830, (24, 24, 30), k)
        rect(d, 320, 668, 438, 822, sky, k)
        d.line([(379 * k, 668 * k), (379 * k, 822 * k)], fill=(24, 24, 30), width=max(1, int(5 * k)))
        text(d, 655, 700, str(n), 64, mix(wall, (255, 255, 255), 0.45), k)
        if clock is not None:
            self.clock(d, 655, 820, 42, clock, k)

    def clock(self, d, x, y, r, hm, k):
        ell(d, x, y, r + 5, r + 5, (30, 30, 36), k)
        ell(d, x, y, r, r, (244, 244, 236), k)
        h, m = hm
        am = math.radians(m * 6 - 90)
        ah = math.radians((h % 12 + m / 60) * 30 - 90)
        capsule(d, (x, y), (x + 0.5 * r * math.cos(ah), y + 0.5 * r * math.sin(ah)), 4, (20, 20, 26), k)
        capsule(d, (x, y), (x + 0.8 * r * math.cos(am), y + 0.8 * r * math.sin(am)), 3, (20, 20, 26), k)

    def land_morning(self, d, t, u, k):
        self.land_room(d, k, (196, 206, 214), (150, 140, 128), (170, 214, 250), 2, (9, 5))
        ell(d, 345, 700, 20, 20, (255, 236, 160), k)
        rect(d, 520, 1060, 580, 1150, (170, 110, 70), k, r=6)
        for (dx, dy, r) in ((-30, -20, 34), (20, -50, 38), (40, -10, 30), (-10, -70, 30)):
            ell(d, 550 + dx, 1040 + dy, r, r, (70, 150, 80), k)

    def stairs_sign(self, d, x, y, k, col=(60, 170, 90)):
        rect(d, x - 44, y - 34, x + 44, y + 34, col, k, r=6)
        pts = [(x - 32, y + 22), (x - 32, y + 8), (x - 14, y + 8), (x - 14, y - 6), (x + 4, y - 6), (x + 4, y - 20),
               (x + 30, y - 20), (x + 30, y + 22)]
        d.polygon(poly(pts, k), fill=(255, 255, 255))

    def land_lady(self, d, t, u, k):
        self.land_room(d, k, (206, 196, 180), (150, 132, 112), (186, 222, 250), 3, (9, 30))
        self.stairs_sign(d, 520, 700, k)
        self.lady(d, t, u, k, old=False)

    def lady(self, d, t, u, k, old):
        # elle s'avance, voit Bounce, se fige, recule, montre l'escalier, s'en va
        if not old:
            xs = KF(680.0, [(0.3, 680.0), (0.65, 610.0), (1.25, 610.0), (1.55, 650.0), (2.9, 650.0), (3.9, 820.0)])
            lean = KF(0.0, [(0.65, -6.0), (0.75, 0.0), (1.2, 0.0), (1.4, 14.0), (2.8, 10.0), (3.0, -8.0)])
            point = (1.9, 2.9)
        else:
            xs = KF(690.0, [(0.3, 690.0), (1.0, 620.0), (2.2, 620.0), (2.5, 655.0), (3.5, 655.0)])
            lean = KF(-12.0, [(1.0, -12.0), (1.5, -6.0), (2.2, -6.0), (2.4, 10.0), (3.5, 10.0)])
            point = (2.4, 3.4)
        x = xs(u)
        fy = 1190.0
        s = 0.86
        body = (150, 90, 190)
        head = (228, 188, 156)
        hands = None
        if point[0] <= u <= point[1]:
            hands = [(540.0, 740.0), (x + 60 * s, fy - 270 * s)]
        hn = person(d, k, x, fy, s, body, head, lean=lean(u), hands=hands, dress=True,
                    bun=(200, 200, 206) if old else (110, 70, 40), hunch=1.0 if old else 0.0)
        # sac à main
        rect(d, x + 52 * s, fy - 300 * s, x + 100 * s, fy - 250 * s, (230, 120, 60), k, r=8)
        if old:
            d.line([((x - 70) * k, (fy - 250) * k), ((x - 84) * k, fy * k)], fill=(120, 80, 50), width=max(1, int(8 * k)))
            capsule(d, (x - 40 * s, fy - 330 * s), (x - 70, fy - 250), 12 * s, body, k)

    def land_noon(self, d, t, u, k):
        self.land_room(d, k, (214, 210, 186), (150, 140, 120), (120, 196, 255), 4, (12, 0))
        ell(d, 410, 700, 24, 24, (255, 230, 90), k)
        back = 40.0 * smooth((u - 1.35) / 0.3)
        bite = u > 1.95
        for (x0, col) in ((585.0, (90, 170, 110)), (680.0, (230, 150, 70))):
            x = x0 + back
            lean = 8.0 if 1.35 < u < 2.2 else 0.0
            hands = [(x - 40, 940.0), (x + 50, 930.0)]
            if x0 == 680.0 and bite and (u * 4) % 1 < 0.5:
                hands = [(x - 40, 940.0), (x + 10, 880.0)]
            person(d, k, x, 1190.0, 0.82, col, (222, 180, 146), lean=lean, hands=hands)
            hx, hy = hands[1]
            w = 46 if not (x0 == 680.0 and bite) else 28
            rect(d, hx - w / 2, hy - 14, hx + w / 2, hy + 14, (236, 206, 140), k, r=6)
            d.line([((hx - w / 2) * k, hy * k), ((hx + w / 2) * k, hy * k)], fill=(90, 170, 70), width=max(1, int(5 * k)))

    def land_sunset(self, d, t, u, k):
        self.land_room(d, k, (168, 140, 132), (120, 100, 92), (250, 150, 80), 5, (6, 0))
        ell(d, 380, 800, 30, 30, (255, 210, 120), k)
        x = KF(645.0, [(0.5, 645.0), (1.6, 645.0), (2.6, 780.0)])(u)
        shake = 10 * math.sin(u * 18) if 0.9 < u < 1.7 else 0.0
        person(d, k, x, 1190.0, 0.84, (70, 110, 190), (220, 180, 146), lean=0,
               hands=[(x - 46, 980.0), (x + 50, 1010.0)])
        rect(d, x + 30, 990, x + 90, 1050, (60, 50, 44), k, r=6)
        ell(d, x + shake * 0.0, 0, 0, 0, None, k)
        if shake:
            hy = 1190.0 - 300 * 0.84
            ell(d, x + shake, hy, 41, 41, (220, 180, 146), k)

    def land_night(self, d, t, u, k):
        self.land_room(d, k, (60, 62, 84), (44, 44, 58), (20, 24, 52), 6, (11, 0))
        ell(d, 410, 720, 22, 22, (240, 240, 210), k)
        ell(d, 418, 714, 20, 20, (20, 24, 52), k)
        # chariot, seau, panneau « sol mouillé » qu'elle pose devant les portes (la 4e fois casse le motif)
        x = 650.0
        mop = 24 * math.sin(u * 7)
        lean = 6.0 if u < 1.2 else -4.0
        person(d, k, x, 1190.0, 0.84, (110, 116, 130), (214, 176, 144), lean=lean,
               hands=[(x - 60 + mop * 0.5, 960.0), (x - 40 + mop * 0.5, 1040.0)])
        d.line([((x - 70 + mop) * k, 930 * k), ((x - 110 + mop) * k, 1180 * k)], fill=(170, 130, 80), width=max(1, int(8 * k)))
        rect(d, x - 150 + mop, 1170, x - 70 + mop, 1192, (200, 200, 210), k, r=6)
        rect(d, 690, 1100, 740, 1190, (90, 140, 200), k, r=6)
        sx = KF(700.0, [(1.5, 700.0), (2.1, 560.0)])(u)
        sy = 1190.0
        d.polygon(poly([(sx - 40, sy), (sx + 40, sy), (sx + 10, sy - 120), (sx - 10, sy - 120)], k), fill=(250, 210, 40))
        d.polygon(poly([(sx - 6, sy - 90), (sx + 8, sy - 68), (sx - 2, sy - 60), (sx + 14, sy - 30), (sx - 14, sy - 30),
                        (sx - 8, sy - 56)], k), fill=(30, 30, 30))

    def land_winter(self, d, t, u, k):
        self.land_room(d, k, (176, 196, 214), (140, 150, 166), (150, 170, 196), 7, None)
        for (a, b, s) in self.snow:
            yy = 668 + ((b + u * 0.35 * s) % 1.0) * 154
            ell(d, 320 + a * 118, yy, 4, 4, (255, 255, 255), k)
        rect(d, 320, 800, 438, 822, (255, 255, 255), k)
        # sapin décoré, et quelqu'un qui grelotte avec un cadeau
        d.polygon(poly([(500, 1150), (600, 1150), (550, 930)], k), fill=(40, 130, 70))
        for (dx, dy, c) in ((-20, -40, (255, 80, 80)), (18, -90, (255, 214, 90)), (-8, -150, (90, 180, 255)),
                            (26, -30, (255, 214, 90))):
            ell(d, 550 + dx, 1150 + dy, 8, 8, c, k)
        rect(d, 543, 1150, 557, 1180, (110, 70, 40), k)
        x = 660.0 + 10 * math.sin(u * 60) * 0.3
        person(d, k, x, 1190.0, 0.82, (200, 60, 60), (226, 184, 150), hands=[(x - 40, 980.0), (x + 40, 980.0)],
               hat=(60, 100, 200), scarf=(250, 250, 250))
        rect(d, x - 34, 950, x + 34, 1010, (200, 40, 60), k, r=4)
        d.line([(x * k, 950 * k), (x * k, 1010 * k)], fill=(255, 214, 90), width=max(1, int(6 * k)))

    def land_summer(self, d, t, u, k):
        self.land_room(d, k, (234, 222, 170), (170, 150, 110), (110, 200, 255), 8, None)
        ell(d, 345, 700, 22, 22, (255, 230, 90), k)
        ell(d, 410, 790, 34, 26, (70, 170, 70), k)
        x = 650.0
        person(d, k, x, 1190.0, 0.82, (250, 140, 170), (226, 184, 150), hands=[(x - 40, 990.0), (x + 50, 900.0)],
               glasses=True)
        d.polygon(poly([(x + 36, 900), (x + 64, 900), (x + 50, 950)], k), fill=(214, 160, 90))
        ell(d, x + 50, 890, 18, 18, (255, 190, 210), k)

    def land_office(self, d, t, u, k):
        self.land_room(d, k, (222, 226, 234), (160, 160, 168), (170, 214, 250), 9, (9, 0))
        rect(d, 520, 1030, 720, 1060, (150, 110, 80), k)
        rect(d, 540, 1060, 556, 1150, (120, 86, 60), k)
        rect(d, 680, 1060, 696, 1150, (120, 86, 60), k)
        rect(d, 580, 950, 660, 1010, (40, 44, 56), k, r=4)
        rect(d, 612, 1010, 628, 1030, (40, 44, 56), k)

    def land_oldlady(self, d, t, u, k):
        self.land_room(d, k, (190, 168, 150), (140, 120, 104), (230, 170, 110), 3, None)
        self.stairs_sign(d, 520, 700, k)
        for (a, b, s) in self.snow[:10]:
            yy = 668 + ((b + u * 0.3 * s) % 1.0) * 154
            ell(d, 320 + a * 118, yy, 7, 4, (210, 110, 40), k)
        self.lady(d, t, u, k, old=True)

    def land_party(self, d, t, u, k):
        self.land_room(d, k, (64, 54, 96), (50, 42, 70), (20, 24, 52), 9, None)
        # quatre collègues en chapeau pointu, bras levés, un gâteau couvert de bougies
        cheer = u > 0.4
        for i, (x, col, hat) in enumerate(((360.0, (90, 170, 110), (255, 90, 120)), (450.0, (230, 150, 70), (90, 180, 255)),
                                           (590.0, (70, 110, 190), (255, 214, 90)), (680.0, (200, 90, 90), (140, 230, 140)))):
            jump = hop(u, [(0.45 + 0.08 * i, 40), (1.5 + 0.1 * i, 30)]) if cheer else 0.0
            fy = 1190.0 - jump
            if cheer:
                hands = [(x - 60, fy - 520), (x + 60, fy - 520)]
            else:
                hands = None
            person(d, k, x, fy, 0.8, col, (224, 182, 148), hands=hands, hat=hat)
        rect(d, 330, 1080, 500, 1190, (240, 240, 244), k, r=6)
        rect(d, 340, 1030, 490, 1080, (250, 200, 210), k, r=10)
        rect(d, 340, 1030, 490, 1046, (255, 250, 250), k, r=8)
        for j in range(13):
            cx = 347 + j * 11.5
            rect(d, cx - 3, 1000, cx + 3, 1032, (120, 190, 255), k)
            ell(d, cx, 994 + 2 * math.sin(u * 20 + j), 4, 7, (255, 200, 60), k)
        # bannière
        rect(d, 300, 604, 720, 724, (255, 214, 90), k, r=10)
        text(d, 500, 636, "HAPPY", 46, (60, 30, 20), k)
        text(d, 500, 690, "RETIREMENT!", 46, (60, 30, 20), k)
        for (cx0, col) in ((330.0, (255, 90, 120)), (700.0, (90, 180, 255))):
            ell(d, cx0, 780, 30, 36, col, k)
            d.line([(cx0 * k, 816 * k), (cx0 * k, 960 * k)], fill=(230, 230, 230), width=max(1, int(2 * k)))
        for (x, ph, sp, col) in self.confetti:
            yy = 600 + ((ph + u * 0.45 * sp) % 1.0) * 600
            rect(d, x - 5, yy - 3, x + 5, yy + 3, col, k)

    # -------- l'homme
    def suit_geom(self, t):
        st = self.suit
        P = st.pose(t)
        x = SUIT_X(t)
        if P["name"] == "shiver" or (29.6 <= t <= 31.3):
            x += 4 * math.sin(t * 70)
        walking = abs(SUIT_X(t + 0.02) - SUIT_X(t - 0.02)) > 1.5
        fy = 1290.0 - hop(t, SUIT_HOP) + SUIT_FG(t)
        return P, x, fy, walking

    def draw_suit(self, dr, t, k, back):
        if back:
            return
        P, x, fy, walking = self.suit_geom(t)
        st = self.suit
        q = SUIT_Q * (1 + SUIT_FG(t) / 800.0)
        x, fy, k = x / q, fy / q, k * q        # dessin à l'échelle q autour de ses pieds
        s = 1.0
        a = math.radians(P["lean"])
        hip_dy = P["hip"]
        sitting = hip_dy > 100
        hipy = fy - 300 + hip_dy
        # jambes
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
        # canne
        old = t >= 47.9
        # torse
        torso = [(x - 66, hipy - 270), (x + 66, hipy - 270), (x + 60, hipy + 8), (x - 60, hipy + 8)]
        torso = [rot(px, py, x, hipy, a) for px, py in torso]
        dr.polygon(poly(torso, k), fill=NAVY)
        top = rot(x, hipy - 270, x, hipy, a)
        # col et cravate
        dr.polygon(poly([rot(px, py, x, hipy, a) for px, py in
                         [(x - 26, hipy - 270), (x + 26, hipy - 270), (x, hipy - 222)]], k), fill=(240, 240, 246))
        ta = a + 0.5 * st.tie(t) * math.sin(t * 3) * 0.3 + 0.35 * st.tie(t)
        tie = [(x - 12, hipy - 252), (x + 12, hipy - 252), (x + 16, hipy - 120), (x, hipy - 96), (x - 16, hipy - 120)]
        cx, cy = rot(x, hipy - 252, x, hipy, a)
        tie = [rot(px - x + cx, py - (hipy - 252) + cy, cx, cy, ta - a) for px, py in
               [rot(px, py, x, hipy, a) for px, py in tie]]
        dr.polygon(poly(tie, k), fill=TIE)
        # tête
        hx, hy = rot(x + P["hd"][0], hipy - 330 + P["hd"][1], x, hipy, a)
        hr = 52.0
        beard_len = st.beard(t)
        gray = st.gray(t)
        hair_c = mix((48, 34, 26), (236, 236, 240), gray)
        beard_c = mix((70, 50, 36), (238, 238, 242), gray)
        # bras (épaules)
        shl = rot(x - 58, hipy - 254, x, hipy, a)
        shr = rot(x + 58, hipy - 254, x, hipy, a)
        hl = (shl[0] + P["hl"][0], shl[1] + P["hl"][1])
        hrp = (shr[0] + P["hr"][0], shr[1] + P["hr"][1])
        if P["name"] == "jab" or (2.6 < t < 4.45):
            hl = ((734 + 16 * math.sin(2 * math.pi * 7 * t)) / q, 921.0 / q)
        if P["name"] == "press9":
            hl = (232.0 / q, 600.0 / q)
        if 10.2 <= t < 14.2:
            pass
        ell(dr, hx, hy, hr, hr, SKIN, k)
        # chevelure : une calotte, qui grisonne
        dr.chord([(hx - hr - 1) * k, (hy - hr - 1) * k, (hx + hr + 1) * k, (hy + hr + 1) * k], 212, 328, fill=hair_c)
        # barbe de trois jours, puis barbe qui pousse
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
        # la barbe coincée entre les portes (39,2 → 40,0) : tendue jusqu'à la fente
        if 39.2 <= t <= 40.0 and beard_len > 1:
            tip = (500.0 / q, 930.0 / q)
            yb = hy + 0.62 * hr + min(beard_len, 260) * 0.7
            wv = 3 * math.sin(t * 40)
            dr.polygon(poly([(hx - 14, yb - 10), (hx + 14, yb + 10), (tip[0], tip[1] + 8 + wv), (tip[0], tip[1] - 8 + wv)], k),
                       fill=beard_c, outline=mix(beard_c, (0, 0, 0), 0.35))
        # zzz
        if 21.9 <= t <= 23.6:
            for j in range(3):
                ph = (t * 0.9 + j / 3.0) % 1.0
                text(dr, hx + 50 + 40 * ph, hy - 70 - 90 * ph, "z", 40 + 30 * ph, mix(WALLC, (200, 190, 255), 1 - ph), k)
        # bras par-dessus
        armc = NAVYD
        capsule(dr, shl, hl, 17, armc, k)
        capsule(dr, shr, hrp, 17, armc, k)
        ell(dr, hl[0], hl[1], 18, 18, SKIN, k)
        ell(dr, hrp[0], hrp[1], 18, 18, SKIN, k)
        # mallette : à la main gauche, puis en bouclier contre le panneau, puis posée
        if t < 10.2 or 14.2 <= t < 39.2:
            if P["name"] in ("rest", "startle", "watch", "facepalm", "sag", "slouch", "sleep", "flinch", "eager") \
                    and not (2.6 < t < 4.45):
                rect(dr, hl[0] - 44, hl[1] - 6, hl[0] + 44, hl[1] + 58, BRIEFC, k, r=8)
                rect(dr, hl[0] - 14, hl[1] - 16, hl[0] + 14, hl[1] - 4, (90, 56, 30), k, r=4)
            else:
                rect(dr, x + 70, fy - 70, x + 158, fy - 6, BRIEFC, k, r=8)
        elif 10.2 <= t < 14.2:
            # bouclier : tenu devant le panneau ; le coup de Bounce le fait sauter
            kick = hop(t, [(11.86, 50)])
            bx0 = (BRIEF_X - R - 34 * q) / q
            by0 = (840 - kick) / q
            ang = 0.0
            rect(dr, bx0, by0, bx0 + 34, by0 + 130, BRIEFC, k, r=6)
            rect(dr, bx0 + 34, by0 + 50, bx0 + 46, by0 + 80, (90, 56, 30), k, r=3)
        elif t >= 39.2:
            rect(dr, 880 / q, (FLOOR + 50) / q, 968 / q, (FLOOR + 114) / q, BRIEFC, k, r=8)
        if old:
            cxh = hrp
            dr.line([(cxh[0] * k, cxh[1] * k), ((cxh[0] + 24) * k, (fy - 4) * k)], fill=(150, 104, 60),
                    width=max(1, int(12 * k)))
            dr.arc([(cxh[0] - 22) * k, (cxh[1] - 22) * k, (cxh[0] + 22) * k, (cxh[1] + 22) * k], 180, 360,
                   fill=(150, 104, 60), width=max(1, int(10 * k)))

    def draw_beard_pool(self, dr, t, k):
        p = self.suit.pool(t)
        if p < 2:
            return
        P, x, fy, walking = self.suit_geom(t)
        gray = self.suit.gray(t)
        beard_c = mix((70, 50, 36), (238, 238, 242), gray)
        x0 = x - 6
        x1 = x0 + p
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
        ell(dr, x1, FLOOR + 4, 30, 22, beard_c, k, outline=mix(beard_c, (0, 0, 0), 0.35), width=2)


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 99.0, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.05,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
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


def stats(sim, narr, hv, name):
    ev = exact_events(sim)
    hits = [e[0] for e in ev]
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
    out["arc_top_min_y"] = round(min(a[2] for a in ap), 1)
    out["ceil_hits_rising"] = all(a[3] < 0 for a in ap if False)
    bad = []
    for (a, b, top, vend) in ap:
        if top < CY - 1:
            bad.append((round(a, 2), round(b, 2), round(top, 1)))
    out["arcs_through_ceiling"] = bad
    lens = [b - a for (a, b, _t, _v) in ap]
    out["seg_max"] = round(max(lens), 2)
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
    summary.update(stats(sim, narr, hv, name))
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, dur, cfg, audio, narr)
        if "--audio-only" in argv:
            import shutil
            shutil.copy(audio, os.path.join(base.ROOT, "output", cfg["name"] + ".wav"))
            print(json.dumps(summary, ensure_ascii=False))
            return 0
        base.render_video(theme, sim, states, cfg, audio, out, events, ())
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, base.ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
