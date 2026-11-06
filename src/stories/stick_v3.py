"""
Prototype « stick » v3 : Bounce à la bibliothèque, avec Stick (perso d'un fan : une balle verte qui colle à tout
ce qu'il touche), collé sur lui.

Ce sont les rebonds de Bounce qui font tout : chaque « Bounce » (anneau d'impact) l'envoie, avec Stick, contre
quelque chose qui colle (« Stick! », éclat). La pile de livres, le panneau QUIET (deux remises en place), la
bibliothécaire elle-même, le lecteur et son fauteuil, la pendule, la pile encore, une rangée de l'étagère. Sa
colère monte par paliers nets, un cran par objet collé : calme jusqu'à 22 s, puis rose, rouge, rouge foncé,
tremblements ; le panneau QUIET, au mur, se décroche d'un cran à chaque palier. Presque-craquage à 41 s,
fausse fin à 45 s (« Finally. »), un « bounce » et ça repart ; l'étagère penche un peu plus à chaque « Bounce ».
La dernière goutte : Stick attrape le panneau QUIET. « QUIET! » : Stick lâche tout et va se coller sur sa tête,
l'étagère tombe et enferme Bounce dans la case vide. Un dernier « bounce » étouffé : elle refume.

Coordonnées du monde 1080×1920, vues par une caméra légèrement serrée (×1,12), mises à l'échelle de la config.

    python3 src/stories/stick_v3.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import dim, font
from PIL import Image, ImageDraw
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = os.environ.get("STICK_BANK",
                          "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/stick/bank")

# ------------------------------------------------------------------ voix (banque Kokoro vérifiée par whisper)
BANK_FILES = {"Stick!": "stick.wav", "STICK!": "stick2.wav", "Give it back!": "giveback.wav",
              "Quiet, please!": "quietplease.wav", "Put me down!": "putdown.wav", "Stop bouncing!": "stop.wav",
              "Qui-": "qui_cut.wav", "...quiet.": "whisper.wav", "Finally.": "finally.wav",
              "No, no, no!": "nonono.wav", "QUIET!": "scream.wav"}
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
            BANK[text] = _read(os.path.join(BANK_DIR, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    """La prise du mot de Bounce est gardée dans la banque : aperçu et rendu final ont le même son."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(BANK_DIR, "hero_%s_%s_%s.wav" % key)
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
HOOK_T = 0.12
_hook_memo = {}


def hook_clip(cfg):
    """La voix de l'accroche (piper, débit accéléré sans changer la hauteur), finie avant 2,0 s."""
    key = cfg.get("hook_text")
    if key not in _hook_memo:
        v = ak.piper_say(key, ak.VOICE_NAME, SR, length_scale=cfg.get("hook_length", 0.68))
        if v is None:
            v = ak.hook_voice(key)
        if v is not None:
            v = np.asarray(v, float)
            e = np.abs(v)
            idx = np.where(e > 0.04 * e.max())[0]
            v = v[max(0, idx[0] - int(0.01 * SR)):min(len(v), idx[-1] + int(0.03 * SR))].copy()
            v /= np.abs(v).max() + 1e-9
            mx = cfg.get("hook_max_s", 1.30)
            if len(v) / SR > mx:
                v = base.pitch(v, len(v) / SR / mx)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
G = 2600.0


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, k):
    return a + (b - a) * k


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def rot(u, v, a):
    ca, sa = math.cos(a), math.sin(a)
    return u * ca - v * sa, u * sa + v * ca


class KF:
    """Images clés lissées : KF(v0, [(t, v), ...])."""

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
        k = smooth((t - t0) / max(1e-6, t1 - t0))
        return lerp(v0, v1, k)


# ------------------------------------------------------------------ ralenti sur l'issue
SLOW_A, SLOW_B, SLOW_K = 58.70, 59.50, 0.35


def vt(t):
    if t <= SLOW_A:
        return t
    if t <= SLOW_B:
        return SLOW_A + (t - SLOW_A) * SLOW_K
    return SLOW_A + (SLOW_B - SLOW_A) * SLOW_K + (t - SLOW_B)


def arc(x0, y0, home, t0, t1, t, lift):
    a, b = vt(t0), vt(t1)
    u = clamp01((vt(t) - a) / max(1e-6, b - a))
    return lerp(x0, home[0], u), lerp(y0, home[1], u) - lift * 4 * u * (1 - u)


# ------------------------------------------------------------------ le décor (coordonnées d'écran)
FL = 1510.0
BR = 150.0                  # Bounce : 300 px de diamètre
SRAD = 82.0                 # Stick, plus petit, collé sur lui en haut à droite
ATT = (184.0, -142.0)
Y_FLOOR = FL - BR
P1 = (300.0, 1430.0, 100.0)            # poufs : x, haut, demi-largeur
P2 = (612.0, 1440.0, 82.0)
POUFS = {"P": P1, "P2": P2}
POUF_DENT = 38.0
Y_POUF = P1[1] - BR + POUF_DENT
Y_POUF2 = P2[1] - BR + POUF_DENT
NAIL = (560.0, 486.0)
SIGN_W, SIGN_H = 300.0, 116.0
SIGN_HOME = (560.0, 486.0 + 22 + SIGN_H / 2)
BC = (730.0, 340.0, 990.0)             # étagère : x gauche, largeur, hauteur ; pivot = coin bas gauche
BC_ROWS = (0.0, 330.0, 660.0, 990.0)   # planches (hauteur depuis le bas)
CHAIR_HOME = (835.0, 1330.0)
CLOCK_HOME = (668.0, 712.0)
LIB_HOME = 690.0

# couleurs
WALL = (46, 31, 27)
WALL_D = (34, 22, 19)
WALL_L = (60, 42, 35)
WOOD = (122, 80, 50)
WOOD_D = (84, 54, 34)
WOOD_L = (150, 104, 68)
FLOOR_C = (58, 40, 30)
FLOOR_L = (72, 52, 40)
CREAM = (238, 230, 204)
INKC = (24, 22, 26)
ST_L = (134, 254, 157)       # Stick : disque vert clair
ST_D = (42, 186, 100)        # anneau vert foncé
LIB = (150, 84, 170)
LIB_RED = (226, 44, 40)
LIB_SKIRT = (66, 48, 92)
SKIN = (226, 176, 146)
HAIR = (92, 84, 92)
READ_B = (58, 150, 150)
READ_D = (40, 108, 108)
READ_SK = (160, 108, 78)
VELVET = (120, 36, 50)
VELVET_D = (88, 24, 36)
POUF_C = (214, 158, 60)
BOOK_COLS = [(196, 70, 60), (60, 120, 190), (220, 180, 70), (90, 160, 90), (170, 90, 160), (230, 120, 60),
             (80, 80, 150), (200, 200, 190), (150, 50, 80), (60, 160, 160)]

# ------------------------------------------------------------------ le plan (temps réels)
END = 62.30
SNAP = 58.35           # « QUIET! »
RELEASE = 58.60        # Stick sursaute et lâche tout
FAKE_END = 45.05       # le tas s'effondre sur Bounce (fausse fin), sur le pouf
LIB_STUCK = 15.20      # elle attrape Stick : elle colle
CASE_A, CASE_B = 58.70, 59.30   # l'étagère, qui penchait, tombe (temps réels)
WEDGE = 59.30          # Bounce coincé dans la case vide
ISSUE = SNAP
STICK_ON_HER = 60.10   # Stick, lâché, se recolle… sur sa tête

# contacts de Bounce : (t réel, surface, x, gain) ; F = parquet (dur : « Bounce ») ; P / P2 = poufs (mous, muets)
CONTACTS = [
    (0.55, "P", 300, 0), (1.00, "P", 305, 0),
    (1.50, "F", 450, 1.15),
    (2.55, "P2", 600, 0),
    (3.10, "F", 440, 1.0), (3.95, "F", 470, 1.05),
    (4.75, "P2", 600, 0),
    (5.75, "F", 430, 1.0),
    (6.50, "P", 350, 0), (7.20, "P", 350, 0),
    (8.52, "F", 460, 1.05), (9.37, "F", 440, 1.0), (10.22, "F", 470, 1.1),
    (10.95, "P", 310, 0), (11.65, "P", 305, 0), (12.35, "P", 310, 0), (12.95, "P", 320, 0),
    (13.20, "F", 430, 1.0), (14.05, "F", 450, 1.05),
    (14.95, "P", 330, 0),
    (16.10, "F", 430, 1.1), (16.95, "F", 450, 1.1), (17.80, "F", 440, 1.15),
    (18.50, "P", 310, 0), (19.20, "P", 310, 0),
    (20.40, "F", 450, 1.3), (21.25, "F", 470, 1.2),
    (22.05, "P2", 600, 0),
    (22.60, "F", 430, 1.0),
    (23.35, "P", 320, 0), (24.10, "P", 320, 0),
    (24.90, "F", 440, 1.0), (25.75, "F", 450, 1.05),
    (26.45, "P", 320, 0), (27.10, "P", 320, 0), (27.75, "P", 330, 0),
    (28.40, "F", 430, 1.3),
    (29.55, "P2", 600, 0),
    (30.30, "P", 320, 0),
    (31.35, "F", 430, 1.0), (32.20, "F", 470, 1.15),
    (33.05, "P2", 600, 0),
    (33.65, "F", 430, 1.0), (34.50, "F", 450, 1.05), (35.35, "F", 470, 1.15),
    (36.15, "P2", 600, 0),
    (36.80, "F", 430, 1.1),
    (37.50, "P", 320, 0), (38.20, "P", 320, 0), (38.90, "P", 330, 0),
    (39.60, "F", 430, 1.05), (40.45, "F", 440, 1.15),
    (41.20, "P", 320, 0), (41.85, "P", 320, 0),
    (42.50, "F", 430, 1.0), (43.35, "F", 420, 0.95), (44.20, "F", 410, 0.9),
    (FAKE_END, "P", 310, 0),
    (45.50, "P", 310, 0), (45.95, "P", 308, 0), (46.40, "P", 310, 0),
    (47.00, "F", 400, 0.4),
    (47.65, "P", 320, 0), (48.30, "P", 340, 0),
    (48.95, "F", 490, 1.05), (49.80, "F", 500, 1.1), (50.65, "F", 500, 1.15),
    (51.35, "P", 330, 0), (52.00, "P", 330, 0),
    (52.70, "F", 495, 1.2),
    (53.40, "P", 330, 0), (54.10, "P", 330, 0),
    (54.80, "F", 500, 1.2), (55.65, "F", 500, 1.25),
    (56.35, "P", 330, 0),
    (57.00, "F", 440, 1.5),
    (58.30, "P", 330, 0),
    (WEDGE, "F", 565, 1.0),
    (61.00, "F", 565, 0.32),
]
HEAVY = [(39.0, 45.1)]       # le tas pèse : écrasement plus fort
LEAN_HITS = [48.95, 49.80, 50.65, 52.70, 54.80, 55.65]   # chaque « Bounce » fait pencher l'étagère

# ce que Stick attrape (t réel) : chaque fois juste après le « Bounce » qui l'y envoie
PICK = {"stack": 2.28, "sign": 7.85, "chair": 22.05, "clock": 29.20, "stack2": 33.05, "row": 36.15,
        "sign2": 57.80}
LINES = [(2.28, "Stick!", "s_stack"), (4.75, "Give it back!", "l_give"), (6.55, "Quiet, please!", "l_quiet"),
         (7.85, "Stick!", "s_sign"), (LIB_STUCK, "STICK!", "s_lib"), (18.60, "Put me down!", "l_down"),
         (22.05, "Stick!", "s_chair"), (26.55, "Stop bouncing!", "l_stop"), (29.20, "Stick!", "s_clock"),
         (33.05, "Stick!", "s_stack2"), (36.15, "STICK!", "s_row"), (41.28, "Qui-", "l_qui"),
         (41.72, "...quiet.", "l_whisper"), (45.60, "Finally.", "l_final"), (47.78, "No, no, no!", "l_nonono"),
         (57.80, "STICK!", "s_sign2"), (SNAP, "QUIET!", "l_snap"), (STICK_ON_HER, "Stick!", "s_her")]
LINE_GAIN = {"l_whisper": 0.4, "l_snap": 2.2, "l_final": 0.75, "l_qui": 1.0}
WHO = {k: ("stick" if k.startswith("s_") else "lib") for (_t, _x, k) in LINES}


def steps(v0, pts, d=0.25):
    keys, cur = [], v0
    for (t, v) in pts:
        keys += [(t, cur), (t + d, v)]
        cur = v
    return keys


# la colère : un cran net par objet collé (calme jusqu'à 22 s), presque-craquage, fausse fin, puis le dernier cran
ANGER = KF(0.0, steps(0.0, [(LIB_STUCK, 0.1), (22.05, 0.27), (29.20, 0.5), (33.05, 0.62), (36.15, 0.76),
                            (40.45, 0.84), (41.28, 0.95), (41.72, 0.70), (44.20, 0.76), (45.60, 0.28),
                            (47.00, 0.80), (50.65, 0.84), (52.70, 0.87), (55.65, 0.90), (57.80, 1.0), (SNAP, 1.15),
                            (59.40, 0.95), (61.05, 1.12), (61.80, 1.0)]))
LEAN = KF(0.0, steps(0.0, [(t, math.radians(4.0 * (i + 1))) for i, t in enumerate(LEAN_HITS)], 0.2))
# la bibliothécaire quand elle n'est pas collée
LIB_X = KF(LIB_HOME, [(4.35, LIB_HOME), (4.7, 640.0), (5.2, 640.0), (5.6, 660.0), (10.85, 660.0), (11.15, 640.0),
                      (11.35, 640.0), (12.0, 560.0), (12.6, 560.0), (13.2, 600.0), (14.6, 600.0), (15.05, 570.0)])
LIB_WALK = KF(0.0, [(4.35, 0.0), (4.4, 1.0), (4.65, 1.0), (4.7, 0.0), (11.35, 0.0), (11.4, 1.0), (11.95, 1.0),
                    (12.0, 0.0), (12.65, 0.0), (12.7, 1.0), (13.15, 1.0), (13.2, 0.0)])
LIB_ARMS = [(0.0, "hold"), (2.6, "empty"), (3.3, "cross"), (4.55, "reach_stack"), (5.0, "carry"), (5.85, "putdown"),
            (6.40, "point"), (8.6, "cross"), (10.85, "reach_sign"), (11.2, "carry_up"), (12.0, "hang"),
            (12.65, "cross"), (14.75, "grab")]
LIB_DIR = KF(-1.0, [(11.35, -1.0), (11.4, -1.0)])
LIB_LAND = (330.0, 59.25)      # où et quand elle retombe après le cri


class Plan:
    """La trajectoire de Bounce : des arcs sous G entre ses contacts (temps de l'image)."""

    def __init__(self):
        cs = []
        for (t, kind, x, g) in CONTACTS:
            soft = kind in POUFS
            y = (Y_POUF if kind == "P" else Y_POUF2) if soft else Y_FLOOR
            cs.append({"t": vt(t), "tr": t, "x": float(x), "y": y, "soft": soft, "gain": g, "kind": kind})
        self.contacts = cs
        self.ts = [c["t"] for c in cs]
        self.start = {"t": 0.0, "x": 360.0, "y": 1080.0}
        self.after = {"t": vt(END) + 1.0, "x": 565.0, "y": Y_FLOOR}
        self.hits = [(c["tr"], c["gain"], c["x"], c["y"]) for c in cs if not c["soft"]]

    def seg(self, tv):
        i = bisect.bisect_right(self.ts, tv)
        a = self.start if i == 0 else self.contacts[i - 1]
        b = self.after if i >= len(self.contacts) else self.contacts[i]
        return a, b

    def pos(self, tv):
        if tv >= vt(WEDGE):           # coincé dans la case : il gigote, il ne peut plus rebondir
            return 565.0 + 3 * math.sin(tv * 23), Y_FLOOR - 1.5
        a, b = self.seg(tv)
        T = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / T
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        u = tv - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def vel(self, tv):
        x0, y0 = self.pos(tv - 0.01)
        x1, y1 = self.pos(tv + 0.01)
        return (x1 - x0) / 0.02, (y1 - y0) / 0.02

    def squash(self, tv):
        if tv >= vt(WEDGE):
            p = 0.025 * math.sin(tv * 2 * math.pi * 3.0)
            k = 0.0
            for c in self.contacts:
                if c["tr"] > WEDGE + 0.5 and 0 <= tv - c["t"] <= 0.25:
                    k = math.sin(math.pi * (tv - c["t"]) / 0.25)
            return 0.97 + p - 0.03 * k, 0.985 - p + 0.02 * k
        sx = sy = 1.0
        heavy = any(a <= tv <= b for (a, b) in HEAVY)
        i = bisect.bisect_left(self.ts, tv - 0.25)
        for c in self.contacts[i:i + 4]:
            u = tv - c["t"]
            dur = 0.2 if heavy else 0.14
            if -0.06 <= u <= dur:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / dur)
                amp = (0.22 if c["soft"] else 0.17) * (1.5 if heavy else 1.0)
                sy *= 1 - amp * kk
                sx *= 1 + 0.8 * amp * kk
        return sx, sy


# ------------------------------------------------------------------ dessin : primitives
CAM_K, CAM_C = 1.12, (540.0, 460.0)     # caméra : zoom autour du haut de la scène (l'accroche ne bouge pas)


class Dr:
    """Dessin en coordonnées du monde, vu par la caméra (zoom CAM_K autour de CAM_C), à l'échelle s."""

    def __init__(self, dr, s, k=CAM_K):
        self.d, self.s, self.k = dr, s, k
        self.ws = s * k

    def X(self, x):
        return (CAM_C[0] + (x - CAM_C[0]) * self.k) * self.s

    def Y(self, y):
        return (CAM_C[1] + (y - CAM_C[1]) * self.k) * self.s

    def P(self, pts):
        return [(self.X(x), self.Y(y)) for x, y in pts]

    def rect(self, x0, y0, x1, y1, col, r=0):
        box = [self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)]
        if r:
            self.d.rounded_rectangle(box, radius=r * self.ws, fill=col)
        else:
            self.d.rectangle(box, fill=col)

    def ell(self, x, y, rx, ry, col, outline=None, w=0):
        X, Y, k = self.X(x), self.Y(y), self.ws
        self.d.ellipse([X - rx * k, Y - ry * k, X + rx * k, Y + ry * k], fill=col,
                       outline=outline, width=max(1, int(w * k)) if outline else 0)

    def ring(self, x, y, r, col, w):
        X, Y, k = self.X(x), self.Y(y), self.ws
        self.d.ellipse([X - r * k, Y - r * k, X + r * k, Y + r * k], outline=col, width=max(2, int(w * k)))

    def pie(self, x, y, r, a0, a1, col):
        X, Y, k = self.X(x), self.Y(y), self.ws
        self.d.pieslice([X - r * k, Y - r * k, X + r * k, Y + r * k], a0, a1, fill=col)

    def poly(self, pts, col):
        self.d.polygon(self.P(pts), fill=col)

    def line(self, pts, col, w):
        self.d.line(self.P(pts), fill=col, width=max(1, int(w * self.ws)), joint="curve")

    def cap(self, p0, p1, r, col):
        self.line([p0, p1], col, 2 * r)
        for p in (p0, p1):
            self.ell(p[0], p[1], r, r, col)

    def text(self, x, y, txt, px, col, stroke=0, stroke_col=(0, 0, 0)):
        self.d.text((self.X(x), self.Y(y)), txt, fill=col, anchor="mm", font=font(px * self.ws),
                    stroke_width=int(stroke * self.ws), stroke_fill=stroke_col)


def rrect_pts(cx, cy, w, h, a):
    return [(cx + p[0], cy + p[1]) for p in (rot(-w / 2, -h / 2, a), rot(w / 2, -h / 2, a),
                                              rot(w / 2, h / 2, a), rot(-w / 2, h / 2, a))]


# ------------------------------------------------------------------ Stick (le dessin du fan, commentaire à 74 likes)
def draw_stick(D, x, y, r, mood="calm"):
    """Stick : disque vert clair, anneau vert foncé, deux yeux blancs à pupille noire, sourcils noirs droits,
    bouche plate. Il ne change que d'yeux : ronds quand il sursaute, plissés quand il force."""
    D.ell(x, y, r * 1.6, r * 1.6, dim(ST_D, 0.28))
    D.ell(x, y, r, r, ST_D)
    D.ell(x, y, r * 0.88, r * 0.88, ST_L)
    ink = (0, 0, 0)
    ey = y - r * 0.12
    if mood == "strain":
        for sx_ in (-1, 1):
            D.line([(x + sx_ * r * 0.55, ey - r * 0.02), (x + sx_ * r * 0.18, ey + r * 0.06)], ink, r * 0.1)
        D.line([(x - r * 0.42, y + r * 0.46), (x - r * 0.14, y + r * 0.40), (x + r * 0.14, y + r * 0.46),
                (x + r * 0.42, y + r * 0.40)], ink, r * 0.09)
        return
    big = 1.25 if mood == "startle" else 1.0
    for sx_ in (-1, 1):
        cx = x + sx_ * r * 0.36
        D.ell(cx, ey, r * 0.26 * big, r * 0.26 * big, (252, 252, 252))
        D.ell(cx + r * 0.07, ey + r * 0.02, r * 0.11, r * 0.11, ink)
        by = ey - r * (0.42 if mood != "startle" else 0.55)
        D.line([(cx - r * 0.2, by), (cx + r * 0.2, by)], ink, r * 0.11)
    if mood == "startle":
        D.ell(x, y + r * 0.48, r * 0.12, r * 0.15, ink)
    else:
        D.line([(x - r * 0.4, y + r * 0.48), (x + r * 0.4, y + r * 0.48)], ink, r * 0.1)


# ------------------------------------------------------------------ objets
SIGN_IMG = {}


def sign_image(s):
    key = round(s, 4)
    if key not in SIGN_IMG:
        w, h, pad = int(SIGN_W * s), int(SIGN_H * s), int(10 * s)
        img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([pad, pad, pad + w, pad + h], radius=int(10 * s), fill=(30, 26, 24, 255))
        d.rounded_rectangle([pad + int(7 * s), pad + int(7 * s), pad + w - int(7 * s), pad + h - int(7 * s)],
                            radius=int(8 * s), fill=CREAM + (255,))
        d.text((pad + w / 2, pad + h / 2 + 2 * s), "QUIET", fill=INKC + (255,), anchor="mm", font=font(80 * s))
        SIGN_IMG[key] = img
    return SIGN_IMG[key]


def paste_rot(img, D, sprite, cx, cy, ang_deg):
    r = sprite.rotate(-ang_deg, resample=Image.BICUBIC, expand=True)
    img.paste(r, (int(D.X(cx) - r.width / 2), int(D.Y(cy) - r.height / 2)), r)


def draw_book(D, cx, cy, w, h, a, col):
    D.poly(rrect_pts(cx, cy, w + 8, h + 8, a), (22, 16, 14))
    D.poly(rrect_pts(cx, cy, w, h, a), col)
    for off in (-0.3, 0.3):
        p0 = rot(-w / 2 + 4, h * off, a)
        p1 = rot(w / 2 - 4, h * off, a)
        D.line([(cx + p0[0], cy + p0[1]), (cx + p1[0], cy + p1[1])], dim(col, 0.62), 5)


STACK = [(150, 46, BOOK_COLS[0]), (140, 44, BOOK_COLS[1]), (156, 48, BOOK_COLS[2]), (138, 42, BOOK_COLS[3]),
         (150, 46, BOOK_COLS[4]), (144, 44, BOOK_COLS[5]), (152, 46, BOOK_COLS[9])]
STACK_H = sum(b[1] for b in STACK)


def draw_stack(D, cx, cy, a):
    """La pile de livres de la bibliothécaire : une colonne de 7 gros livres. (cx, cy) = le bas de la pile,
    elle monte dans la direction a - 90°."""
    up = a - math.pi / 2
    d = 0.0
    for (w, h, col) in STACK:
        c = (cx + math.cos(up) * (d + h / 2), cy + math.sin(up) * (d + h / 2))
        draw_book(D, c[0], c[1], w, h, a, col)
        d += h


def draw_clock(D, x, y, a, t):
    """La grande pendule murale (140 px)."""
    D.ell(x, y, 72, 72, (30, 24, 22))
    D.ell(x, y, 62, 62, CREAM)
    for k in range(12):
        q = rot(0, -50, k * math.pi / 6 + a)
        D.ell(x + q[0], y + q[1], 5, 5, INKC)
    h = rot(0, -30, a + 1.9)
    m = rot(0, -48, a + t * 0.6)
    D.line([(x, y), (x + h[0], y + h[1])], INKC, 9)
    D.line([(x, y), (x + m[0], y + m[1])], INKC, 6)


def draw_chair_unit(D, cx, cy, a, t, look=0.0):
    """Le fauteuil et le lecteur assis dedans, qui lit ; (cx, cy) = centre de l'assise ; a = rotation."""
    def P(u, v):
        q = rot(u, v, a)
        return (cx + q[0], cy + q[1])

    def quad(pts, col):
        D.poly([P(u, v) for (u, v) in pts], col)
    quad([(10, -270), (120, -280), (130, 15), (20, 25)], VELVET_D)
    quad([(-110, -25), (120, -25), (120, 45), (-110, 45)], VELVET)
    for u in (-100, 105):
        D.line([P(u, 45), P(u + (4 if u > 0 else -4), 175)], WOOD_D, 16)
    # le lecteur (sans visage) : jambes, buste, tête, bras, livre ouvert
    pants, shoe = (60, 56, 80), (30, 26, 30)
    hip, sh, head = P(20, -10), P(14, -150), P(8 + 8 * look, -214 + 16 * look)
    k1, f1 = P(-70, 0), P(-78, 150)
    D.cap(hip, k1, 26, pants)
    D.cap(k1, f1, 21, pants)
    D.poly([P(-104, 140), P(-60, 140), P(-60, 160), P(-104, 160)], shoe)
    D.cap(hip, sh, 60, READ_B)
    D.ell(head[0], head[1], 54, 54, READ_SK)
    D.pie(head[0], head[1], 54, 200 + math.degrees(a), 380 + math.degrees(a), (44, 30, 26))
    bk = P(-52, -110)
    D.cap(sh, bk, 17, READ_D)
    w_, h_ = 120, 82
    D.poly(rrect_pts(bk[0], bk[1], w_ + 10, h_ + 10, a), (22, 16, 14))
    D.poly(rrect_pts(bk[0], bk[1], w_, h_, a), (190, 60, 56))
    for side in (-1, 1):
        q = rot(side * w_ / 4, 0, a)
        D.poly(rrect_pts(bk[0] + q[0], bk[1] + q[1], w_ / 2 - 10, h_ - 14, a), (236, 230, 214))
    D.ell(bk[0], bk[1], 16, 16, READ_SK)
    quad([(-120, -85), (-75, -85), (-75, 45), (-120, 45)], VELVET_D)
    D.ell(*P(-97, -85), 26, 16, VELVET)


# ------------------------------------------------------------------ la scène
class Thing:
    """Un objet : segments (t réel, mode, données). Modes : home, stuck, held, fly (vers une pose fixe)."""

    def __init__(self, name, home_fn, slot_ang, dist, slot_rot):
        self.name = name
        self.home_fn = home_fn
        self.slot_ang = math.radians(slot_ang)
        self.dist = dist
        self.slot_rot = math.radians(slot_rot)
        self.segs = [(-9.0, "home", None)]

    def at(self, t, mode, data=None):
        self.segs.append((t, mode, data))
        self.segs.sort(key=lambda s: s[0])
        return self


class Scene:
    def __init__(self):
        self.P = Plan()
        rng = np.random.default_rng(11)
        self.case_books = []
        for r in range(3):
            u0, u1 = BC_ROWS[r] + 14, BC_ROWS[r + 1] - 14
            v = 22.0
            books = []
            while v < BC[1] - 50:
                w = float(rng.integers(36, 48))
                h = float(rng.integers(150, 210))
                books.append((v + w / 2, u0 + h / 2 + 2, w, h, BOOK_COLS[int(rng.integers(0, len(BOOK_COLS)))]))
                v += w + 4
            self.case_books.append(books)
        self.build()

    # -------- Bounce et Stick
    def bounce(self, t):
        tv = vt(t)
        x, y = self.P.pos(tv)
        sx, sy = self.P.squash(tv)
        return x, y, sx, sy

    def cluster_ang(self, t):
        tv = vt(t)
        _vx, vy = self.P.vel(tv)
        a = max(-0.12, min(0.12, -vy / 9000.0))
        heap = clamp01((t - FAKE_END + 0.05) / 0.25) * (1 - clamp01((t - 46.9) / 0.4))
        return a * (1 - heap) - 0.55 * heap

    def stuck_frame(self, t):
        bx, by, _sx, sy = self.bounce(t)
        a = self.cluster_ang(t)
        ax, ay = rot(ATT[0], ATT[1], a)
        return bx + ax, by + ay + (1 - sy) * BR * 0.9, a

    def stick_pos(self, t):
        if t < RELEASE:
            return self.stuck_frame(t)
        x0, y0, a0 = self.stuck_frame(RELEASE)
        J = self.lib_joints(min(t, STICK_ON_HER + 5))
        hx, hy = J["head"]
        top = (hx + 6, hy - 62 * (1 + 0.3 * clamp01((ANGER(t) - 0.8) / 0.2) * 0.45) - SRAD * 0.75)
        if t < STICK_ON_HER:
            x, y = arc(x0, y0, top, RELEASE, STICK_ON_HER, t, 160)
            return x, y, 0.0
        return top[0], top[1], 0.0

    # -------- objets
    def build(self):
        stack = Thing("stack", lambda t: self.lib_hold_pt(t), -50, SRAD + 6, -50 + 90)
        stack.at(PICK["stack"], "stuck").at(5.00, "held", "carry").at(5.95, "fly", (6.25, (712.0, FL, 0.0), 0, 0.0))
        stack.at(PICK["stack2"], "stuck", (-138, SRAD + 6, -138 + 90))
        stack.at(PICK["row"], "fly", (PICK["row"] + 0.55, (520.0, FL - 76.0, -1.571), 60, 0.0))
        self.stack = stack
        sign = Thing("sign", lambda t: self.sign_home(t), -128, 128 + 30, -14)
        sign.at(PICK["sign"], "stuck").at(11.20, "held", "sign").at(12.45, "home")
        sign.at(PICK["sign2"], "stuck", (-112, SRAD + 74, -18))
        sign.at(RELEASE, "fly", (59.35, (250.0, FL - 66.0, -0.22), 60, 0.0))
        self.sign = sign
        chair = Thing("chair", lambda t: CHAIR_HOME, -82, SRAD + 230, 180)
        chair.at(PICK["chair"], "stuck").at(RELEASE, "fly", (59.25, (770.0, FL - 280.0, math.pi), 90, 0.0))
        self.chair = chair
        clock = Thing("clock", lambda t: CLOCK_HOME, -150, SRAD + 74, 0)
        clock.at(PICK["clock"], "stuck").at(PICK["stack2"], "fly", (PICK["stack2"] + 0.5, (470.0, FL - 74.0, 0.8), 40, 0.0))
        self.clock = clock
        self.row = []
        books = self.case_books[0][:6]
        for i, b in enumerate(books):
            ang = -178 + 10.5 * i
            th = Thing("rb%d" % i, (lambda b: (lambda t: self.case_pt(t, b[0], b[1])))(b), ang, SRAD + b[3] / 2 - 6,
                       ang + 90)
            th.book = b
            lx = 110.0 + 40 * i
            th.at(PICK["row"], "stuck").at(RELEASE, "fly", (58.95 + 0.04 * i, (lx, FL - b[2] / 2, 1.571 + 0.2 * (i % 3 - 1)),
                                                             100, 0.0))
            self.row.append(th)
        self.things = [stack, sign, chair, clock] + self.row

    def sign_home(self, t):
        """Le panneau QUIET, au mur : il se décroche d'un cran à chaque palier de colère (la jauge du décor)."""
        a = ANGER(t) if t >= 12.45 or t < PICK["sign"] else 0.0
        tilt = math.radians(42.0) * clamp01(a / 0.95) ** 1.2
        u, v = rot(0.0, 22 + SIGN_H / 2, tilt)
        return NAIL[0] + u, NAIL[1] + v, tilt

    def seg_of(self, th, t):
        i = max(0, bisect.bisect_right([s[0] for s in th.segs], t) - 1)
        return i, th.segs[i]

    def raw_pose(self, th, t, idx):
        t0, mode, data = th.segs[idx]
        if mode == "home":
            p = th.home_fn(t)
            return p[0], p[1], (p[2] if len(p) > 2 else 0.0)
        if mode == "stuck":
            sx, sy, a = self.stick_pos(min(t, RELEASE - 1e-4))
            sa, dist, sr_ = th.slot_ang, th.dist, th.slot_rot
            if data:
                sa, dist, sr_ = math.radians(data[0]), data[1], math.radians(data[2])
            ang = sa + a
            return sx + dist * math.cos(ang), sy + dist * math.sin(ang), sr_ + a
        if mode == "held":
            if data == "sign":
                (h1, h2) = self.lib_hands(t)
                return (h1[0] + h2[0]) / 2, (h1[1] + h2[1]) / 2 - 40, 0.0
            p = self.lib_hold_pt(t)
            return p[0], p[1], 0.0
        if mode == "fly":
            t1, target, lift, spins = data
            px, py, pa = self.pose(th, t0 - 1e-4)
            x, y = arc(px, py, target, t0, t1, t, lift)
            u = clamp01((vt(t) - vt(t0)) / max(1e-6, vt(t1) - vt(t0)))
            return x, y, lerp(pa, target[2], smooth(u))
        return 0.0, 0.0, 0.0

    def pose(self, th, t):
        idx, seg = self.seg_of(th, t)
        p = self.raw_pose(th, t, idx)
        if seg[1] != "fly" and idx > 0 and t - seg[0] < 0.14:
            q = self.raw_pose(th, seg[0] - 1e-4, idx - 1)
            k = smooth((t - seg[0]) / 0.14)
            p = (lerp(q[0], p[0], k), lerp(q[1], p[1], k), lerp(q[2], p[2], k))
        if th.name == "sign" and seg[1] == "home":
            p = (p[0], p[1], p[2] + self.sign_swing(t))
        return p

    def sign_swing(self, t):
        a = 0.0
        for (t0, amp) in SIGN_WOBBLE:
            u = vt(t) - vt(t0)
            if 0 <= u <= 2.2:
                a += amp * math.sin(u * 9.0) * math.exp(-u * 2.0)
        return a

    # -------- l'étagère
    def case_angle(self, t):
        tv = vt(t)
        a, b = vt(CASE_A), vt(CASE_B)
        if tv >= b:
            return -math.pi / 2
        l0 = LEAN(CASE_A)
        if tv >= a:
            u = (tv - a) / (b - a)
            return -(l0 + (math.pi / 2 - l0) * u * u)
        w = 0.0
        for (t0, amp) in CASE_WOBBLE:
            u = tv - t0
            if 0 <= u <= 1.2:
                w += amp * math.sin(u * 14) * math.exp(-u * 3.5)
        return -abs(w) - LEAN(t)

    def case_pt(self, t, v, u):
        """Un point de l'étagère (v en travers depuis la gauche, u en hauteur depuis le bas)."""
        ph = self.case_angle(t)
        x, y = rot(v, -u, ph)
        return BC[0] + x, FL + y

    # -------- la bibliothécaire
    def lib_hold_pt(self, t):
        h1, h2 = self.lib_hands(t)
        return (h1[0] + h2[0]) / 2, (h1[1] + h2[1]) / 2 + 10

    def lib_hands(self, t):
        J = self.lib_joints(t)
        return J["h1"], J["h2"]

    def arm_target(self, mode, t):
        x = LIB_X(t)
        sh = (x, FL - 600)
        if mode in ("hold", "empty"):
            return (sh[0] - 120, sh[1] + 150), (sh[0] - 40, sh[1] + 160)
        if mode == "cross":
            return (sh[0] + 34, sh[1] + 150), (sh[0] - 34, sh[1] + 160)
        if mode == "fists":
            tr = 5 * math.sin(t * 60) * clamp01((ANGER(t) - 0.5) / 0.3)
            return (sh[0] - 90 + tr, sh[1] + 250), (sh[0] + 90 - tr, sh[1] + 250)
        if mode == "reach_stack":
            p = self.pose(self.stack, 4.94)
            return (p[0] - 50, p[1] - 60), (p[0] + 30, p[1] - 120)
        if mode == "carry":
            return (sh[0] - 120, sh[1] + 150), (sh[0] - 40, sh[1] + 160)
        if mode == "putdown":
            return (sh[0] + 20, sh[1] + 420), (sh[0] + 100, sh[1] + 420)
        if mode == "point":
            return (sh[0] + 70, sh[1] + 240), (SIGN_HOME[0] + 70, SIGN_HOME[1] + 40)
        if mode == "reach_sign":
            p = self.pose(self.sign, 11.19)
            return (p[0] - 80, p[1] + 40), (p[0] + 80, p[1] + 40)
        if mode == "carry_up":
            return (sh[0] - 80, sh[1] - 160), (sh[0] + 80, sh[1] - 160)
        if mode == "hang":
            return (NAIL[0] - 90, NAIL[1] + 140), (NAIL[0] + 90, NAIL[1] + 140)
        if mode == "grab":
            p = self.stick_pos(LIB_STUCK)
            return (p[0] + 70, p[1] - 30), (p[0] + 86, p[1] + 20)
        return (sh[0] - 70, sh[1] + 250), (sh[0] + 70, sh[1] + 250)

    def lib_free_hands(self, t):
        ts = [m[0] for m in LIB_ARMS]
        i = max(0, bisect.bisect_right(ts, t) - 1)
        cur = self.arm_target(LIB_ARMS[i][1], t)
        if i > 0:
            k = smooth((t - LIB_ARMS[i][0]) / 0.25)
            if k < 1:
                prev = self.arm_target(LIB_ARMS[i - 1][1], t)
                cur = tuple((lerp(p[0], c[0], k), lerp(p[1], c[1], k)) for p, c in zip(prev, cur))
        return cur

    def lib_joints(self, t):
        """La bibliothécaire, sans visage : debout (pieds au sol) ; collée (mains sur Stick, elle pend) ;
        après le cri, debout à gauche, toute rouge."""
        a = ANGER(t)
        trem = (3 + 12 * clamp01((a - 0.7) / 0.3)) * math.sin(t * 70) if a > 0.7 else 0.0
        if LIB_STUCK <= t < RELEASE:
            sx, sy, ca = self.stick_pos(t)
            ang = math.radians(38) + ca
            hx, hy = sx + (SRAD + 8) * math.cos(ang), sy + (SRAD + 8) * math.sin(ang)
            k_in = smooth((t - LIB_STUCK) / 0.25)
            if k_in < 1:
                h0 = self.lib_free_hands(LIB_STUCK)[1]
                hx, hy = lerp(h0[0], hx, k_in), lerp(h0[1], hy, k_in)
            vx, _vy = self.P.vel(vt(t))
            sway = max(-60.0, min(60.0, -vx * 0.05))
            sh = (hx + 66 + sway * 0.3 + trem, hy + 150)
            hip = (sh[0] + 6 + sway, sh[1] + 270)
            leg = 300.0
            fy = min(FL, hip[1] + leg)
            d = fy - hip[1]
            air = clamp01((FL - (hip[1] + leg)) / 60.0)
            pd = 40 * air * math.sin(t * 2 * math.pi * 2.4)
            fx = hip[0] + sway * 0.4
            ko = math.sqrt(max(0.0, (leg / 2) ** 2 - (d / 2) ** 2))
            J = {"sh": sh, "hip": hip, "f1": (fx - 30 + pd, fy - abs(pd) * 0.6), "f2": (fx + 30 - pd, fy - abs(pd) * 0.6),
                 "k1": (fx - 30 - ko, hip[1] + d / 2), "k2": (fx + 30 + ko * 0.6, hip[1] + d / 2),
                 "h1": (hx - 10, hy), "h2": (hx + 16, hy + 8), "head": (sh[0] + 6, sh[1] - 92), "dir": -1}
            return J
        if t >= RELEASE:
            J0 = self.lib_joints(RELEASE - 1e-4)
            hipx, hipy = arc(J0["hip"][0], J0["hip"][1], (LIB_LAND[0], FL - 330), RELEASE, LIB_LAND[1], t, 80)
            lean = 18.0 * smooth((t - LIB_LAND[1]) / 0.3)
            hip = (hipx, hipy)
            sh = (hip[0] + lean + trem, hip[1] - 270)
            J = {"sh": sh, "hip": hip, "f1": (hip[0] - 40, min(FL, hip[1] + 330)), "f2": (hip[0] + 40, min(FL, hip[1] + 330)),
                 "head": (sh[0] + lean * 0.5, sh[1] - 92), "dir": 1}
            J["k1"] = ((J["f1"][0] + hip[0]) / 2 - 8, (J["f1"][1] + hip[1]) / 2)
            J["k2"] = ((J["f2"][0] + hip[0]) / 2 + 8, (J["f2"][1] + hip[1]) / 2)
            J["h1"] = (sh[0] - 100, sh[1] + 240)
            J["h2"] = (sh[0] + 110, sh[1] + 240)
            return J
        x = LIB_X(t)
        walk = LIB_WALK(t)
        ph = t * 2 * math.pi * 1.8
        bob = 7 * abs(math.sin(ph)) * walk
        hip = (x, FL - 330 - bob)
        sh = (x + trem, hip[1] - 270)
        st = 34 * math.sin(ph) * walk
        J = {"hip": hip, "sh": sh, "f1": (x - 30 + st, FL), "f2": (x + 30 - st, FL), "head": (sh[0] - 4, sh[1] - 92),
             "dir": -1}
        mode = LIB_ARMS[max(0, bisect.bisect_right([m[0] for m in LIB_ARMS], t) - 1)][1]
        if mode == "putdown":
            k = math.sin(math.pi * clamp01((t - 5.85) / 0.4))
            J["sh"] = (sh[0] - 40 * k, sh[1] + 120 * k)
            J["head"] = (J["sh"][0] - 30 * k, J["sh"][1] - 92)
        if 0.12 <= t < 1.6:        # elle regarde ses bras vides
            k = math.sin(math.pi * clamp01((t - 0.12) / 1.4))
            J["head"] = (J["head"][0] - 20 * k, J["head"][1] + 22 * k)
        J["k1"] = ((J["f1"][0] + hip[0]) / 2 - 5, (J["f1"][1] + hip[1]) / 2)
        J["k2"] = ((J["f2"][0] + hip[0]) / 2 + 5, (J["f2"][1] + hip[1]) / 2)
        h1, h2 = self.lib_free_hands(t)
        J["h1"], J["h2"] = h1, h2
        return J


STICK_LAND = (840.0, 700.0)        # Stick, lâché, se recolle au mur
STICK_LAND_T = 61.0
SIGN_WOBBLE = [(10.22, 0.05), (20.40, 0.08), (28.40, 0.10), (40.45, 0.12), (50.65, 0.14), (55.65, 0.18)]
CASE_WOBBLE = [(20.40, 0.02), (28.40, 0.03), (40.45, 0.03)] + [(t, 0.03) for t in LEAN_HITS] + [(57.00, 0.05)]


# ------------------------------------------------------------------ personnages sans visage
ANGER_COLS = [(0.0, LIB), (0.27, (226, 120, 172)), (0.5, (228, 50, 50)), (0.76, (168, 22, 28)), (1.0, (128, 8, 14))]


def anger_col(a):
    a = clamp01(a)
    for i in range(len(ANGER_COLS) - 1):
        (x0, c0), (x1, c1) = ANGER_COLS[i], ANGER_COLS[i + 1]
        if a <= x1:
            return mix(c0, c1, (a - x0) / (x1 - x0))
    return ANGER_COLS[-1][1]


def draw_lib(D, J, t):
    """La bibliothécaire : sa colère se lit au corps : elle rougit, gonfle, tremble, fume, son chignon se défait."""
    a = ANGER(t)
    col = anger_col(a)
    infl = clamp01((a - 0.8) / 0.2) * 0.45
    w_t = 74 * (1 + infl)
    leg_c, shoe = (52, 40, 60), (30, 24, 34)
    for f, k in (("f1", "k1"), ("f2", "k2")):
        D.cap(J["hip"], J[k], 18, leg_c)
        D.cap(J[k], J[f], 15, leg_c)
        D.ell(J[f][0] - 10 * J["dir"], J[f][1] - 7, 27, 13, shoe)
    hip, sh = J["hip"], J["sh"]
    D.poly([(hip[0] - 66, hip[1] + 86), (hip[0] + 66, hip[1] + 86), (hip[0] + 50, hip[1] - 36),
            (hip[0] - 50, hip[1] - 36)], LIB_SKIRT)
    ux, uy = sh[0] - hip[0], sh[1] - hip[1]
    n = math.hypot(ux, uy) + 1e-6
    px, py = -uy / n, ux / n
    D.poly([(hip[0] + px * w_t * 0.8, hip[1] + py * w_t * 0.8), (sh[0] + px * w_t, sh[1] + py * w_t),
            (sh[0] - px * w_t, sh[1] - py * w_t), (hip[0] - px * w_t * 0.8, hip[1] - py * w_t * 0.8)], col)
    D.ell(sh[0], sh[1], w_t, 42 * (1 + 0.4 * infl), col)
    hx, hy = J["head"]
    hr = 62 * (1 + 0.3 * infl)
    D.ell(hx, hy, hr, hr, mix(SKIN, (232, 80, 66), clamp01((a - 0.4) / 0.55)))
    D.pie(hx, hy, hr, 180, 360, HAIR)
    # le chignon se défait : des mèches qui se dressent, de plus en plus
    undone = clamp01((a - 0.2) / 0.7)
    bx, by = hx - J["dir"] * hr * 0.2, hy - hr * 0.95
    nstr = int(1 + 7 * undone)
    for i in range(nstr):
        ang = -math.pi / 2 + (i - (nstr - 1) / 2) * 0.32
        L = hr * (0.35 + 0.65 * undone) * (1 + 0.15 * math.sin(t * 9 + i))
        D.line([(bx + math.cos(ang) * hr * 0.3, by + math.sin(ang) * hr * 0.3),
                (bx + math.cos(ang) * (hr * 0.3 + L), by + math.sin(ang) * (hr * 0.3 + L))], HAIR, 9)
    D.ell(bx, by, hr * 0.42 * (1 - 0.5 * undone), hr * 0.38 * (1 - 0.5 * undone), HAIR)
    if undone < 0.7:
        D.line([(bx - 8, by + 4), (bx + 40, by - 56)], (240, 200, 70), 8)
    # vapeur au-dessus de la tête
    if a > 0.45:
        k = clamp01((a - 0.45) / 0.55)
        for i in range(1 if a < 0.6 else (2 if a < 0.74 else 3)):
            ph = (t * (1.2 + 1.6 * k) + i / 3) % 1.0
            side = (-1.15, 1.15, 0.0)[i]
            sx_ = hx + side * hr * (1.0 + 0.6 * ph) + 10 * math.sin(t * 5 + i)
            sy_ = hy - hr * 0.5 - 150 * ph * (0.6 + 0.6 * k)
            r_ = (16 + 26 * ph) * (0.6 + 0.6 * k)
            D.ell(sx_, sy_, r_, r_, mix((210, 210, 220), WALL, ph * 0.9))
    if 61.0 <= t < 62.4:            # le dernier « bounce » étouffé : elle refume, en gros
        u = (t - 61.0) / 1.4
        for i in range(6):
            ang = -math.pi / 2 + (i - 2.5) * 0.45
            r_ = (26 + 40 * u) * (1 - 0.5 * u)
            D.ell(hx + math.cos(ang) * hr * (1.2 + 2.2 * u), hy - hr * 0.3 + math.sin(ang) * hr * (1.2 + 2.2 * u), r_, r_,
                  mix((230, 230, 236), WALL, u * 0.8))
    for hnd, sgn in ((J["h1"], -1), (J["h2"], 1)):
        s0 = (sh[0] + sgn * w_t * 0.78, sh[1] + 12)
        D.cap(s0, hnd, 16, dim(col, 0.8))
        D.ell(hnd[0], hnd[1], 18, 18, SKIN)


# ------------------------------------------------------------------ le décor
def draw_room(D, t):
    D.rect(0, 0, W, FL, WALL)
    D.rect(0, 0, W, 210, WALL_D)
    D.rect(0, 204, W, 220, WALL_L)
    for k in range(9):
        x = 60 + k * 135
        D.rect(x, 220, x + 4, 1180, WALL_D)
    D.rect(0, 1180, W, FL, WALL_D)
    D.rect(0, 1176, W, 1194, WALL_L)
    # fenêtre haute, lune (décor)
    D.rect(150, 560, 360, 900, (30, 40, 70), r=12)
    D.rect(158, 568, 352, 892, (40, 56, 96), r=10)
    D.line([(255, 568), (255, 892)], WALL_L, 8)
    D.line([(158, 730), (352, 730)], WALL_L, 8)
    D.ell(310, 620, 26, 26, (230, 226, 200))
    # parquet, tapis, premier plan
    D.rect(0, FL, W, H, FLOOR_C)
    y, k = FL + 14, 0
    while y < H:
        D.rect(0, y, W, y + 3, FLOOR_L)
        y += 24 + 5 * k
        k += 1
    D.ell(540, 1640, 500, 70, (34, 66, 58))
    D.ell(540, 1640, 440, 52, (46, 86, 74))


def draw_foreground(D, t):
    """Premier plan (décor) : une table de lecture, deux lampes allumées, des livres, une tasse à crayons."""
    top = 1745.0
    D.rect(-10, top, W + 10, H, (44, 29, 22))
    D.rect(-10, top - 16, W + 10, top + 6, (82, 54, 38))
    for lx in (170.0, 910.0):
        D.ell(lx, top - 50, 140, 70, (60, 44, 32))
        D.line([(lx, top - 16), (lx, top - 110)], (150, 120, 60), 12)
        D.poly([(lx - 70, top - 100), (lx + 70, top - 100), (lx + 46, top - 150), (lx - 46, top - 150)], (30, 96, 64))
        D.ell(lx, top - 98, 60, 9, (240, 220, 150))
    for k, c in enumerate(((140, 54, 50), (50, 90, 140), (170, 140, 60))):
        D.rect(470 + 6 * k, top - 16 - 26 * (k + 1), 640 - 10 * k, top - 16 - 26 * k - 2, dim(c, 0.85))
    D.rect(350, top - 66, 380, top - 16, (120, 90, 140), r=4)
    for k in range(3):
        D.line([(356 + 9 * k, top - 66), (352 + 14 * k, top - 100)], ((230, 190, 60), (200, 80, 70), (80, 140, 200))[k], 5)


def draw_pouf(D, bx, by, pf=P1, col=None):
    cx, top, hw = pf
    POUF_C_ = col or POUF_C
    pts = []
    for i in range(41):
        x = cx - hw + 2 * hw * i / 40
        y = top - 12 * (1 - ((x - cx) / hw) ** 2)
        dxb = x - bx
        if abs(dxb) < BR * 1.02:
            cy = by + math.sqrt(max(0.0, (BR * 1.02) ** 2 - dxb * dxb))
            y = max(y, min(FL - 22, cy))
        pts.append((x, y))
    D.poly(pts + [(cx + hw + 6, FL), (cx - hw - 6, FL)], POUF_C_)
    D.line(pts, dim(POUF_C_, 0.7), 6)
    D.line([(cx - hw * 0.7, FL - 30), (cx + hw * 0.7, FL - 30)], dim(POUF_C_, 0.75), 5)


# ------------------------------------------------------------------ simulation
DEFAULTS = {
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 88, "hook_length": 0.68,
    "narrator_voice": "am_puck", "narrator_length": 1.0, "narr_gap_s": 0.0,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.965, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
EXPR = [(LIB_STUCK, 16.6, "shock"), (PICK["chair"], 23.2, "shock"), (41.1, 42.3, "shock"), (FAKE_END, 47.0, "lose"),
        (47.0, 48.6, "shock"), (PICK["sign2"], 59.8, "shock"), (59.8, 61.0, "lose"), (61.0, 61.7, "shock"),
        (61.7, 99.0, "lose")]
STICK_MOOD = [(39.0, 45.1, "strain"), (FAKE_END, 47.0, "strain"), (SNAP + 0.1, 99.0, "startle")]


class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_times = [h[0] for h in self.sc.P.hits]
        self.hi = 0
        self.lines = list(LINES)
        self.replies = []
        self.subs = []
        self._hook = None

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_times) and self.hit_times[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= END - 1e-9:
            self.done = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t0):
        best, bd = 0.9, 1e9
        for (th, g, _x, _y) in self.sc.P.hits:
            if abs(th - t0) < bd:
                best, bd = g, abs(th - t0)
        return best

    def set_narr(self, narr):
        out = []
        for i, n in enumerate(narr):
            words = len(n["text"].split())
            end = max(n["end"] + 0.35, n["start"] + 0.6 + 0.3 * words)
            if i + 1 < len(narr):
                end = min(end, narr[i + 1]["start"] - 0.05)
            out.append((WHO.get(n["key"], "lib"), n["text"], n["start"], end, n["key"]))
        self.subs = out

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        sc = self.sc
        s = S * self.cfg["width"] / W
        img = dr._image
        D = Dr(dr, s)
        shake = 0.0
        if SNAP <= t < SNAP + 0.9:
            shake = 10 * math.sin(t * 95) * (1 - (t - SNAP) / 0.9)
        draw_room(D, t)
        # le clou et le panneau quand il est au mur
        D.ell(NAIL[0], NAIL[1], 8, 8, (200, 200, 210))
        modes = {th.name: sc.seg_of(th, t)[1][1] for th in sc.things}
        if modes["sign"] == "home":
            self.draw_thing(D, img, sc.sign, t)
        self.draw_case(D, t, back=True)
        if t < CASE_A:
            self.draw_case(D, t, back=False)
        if modes["chair"] == "home":
            self.draw_thing(D, img, sc.chair, t)
        LJ = sc.lib_joints(t)
        lib_hanging = LIB_STUCK <= t < RELEASE
        bx, by, sx, sy = sc.bounce(t)
        draw_pouf(D, bx, by + (1 - sy) * BR)
        draw_pouf(D, bx, by + (1 - sy) * BR, P2, (70, 150, 170))
        # objets au sol (la pile posée, les choses retombées)
        for th in sc.things:
            if not (th.name == "sign" and modes["sign"] == "home") and th.name != "chair" and \
                    modes[th.name] in ("home", "fly") and \
                    not (th.name == "stack" and t < 5.95) and not th.name.startswith("rb"):
                self.draw_thing(D, img, th, t)
        for th in self.sc.row:
            if modes[th.name] == "fly":
                self.draw_thing(D, img, th, t)
        if modes["chair"] == "fly":
            self.draw_thing(D, img, sc.chair, t)
        stx, sty, _a = sc.stick_pos(t)
        D.ell(stx, sty, SRAD * 1.6, SRAD * 1.6, dim(ST_D, 0.28))
        self.draw_rings(D, t)
        base.HERO["expr"] = self.expr_at(t)
        ycen = by + (1 - sy) * BR
        if abs(sx - 1) < 0.004 and abs(sy - 1) < 0.004:
            base.ball(dr, D.X(bx), D.Y(ycen), BR * D.ws)
        else:
            self.draw_ball(dr, D.X(bx), D.Y(ycen), BR * sx, BR * sy, D.ws)
        if t >= CASE_A:
            self.draw_case(D, t, back=False)
        if lib_hanging or t >= RELEASE:
            draw_lib(D, LJ, t)
        elif t < LIB_STUCK:
            draw_lib(D, LJ, t)
        for th in sc.things:
            if modes[th.name] in ("stuck", "held"):
                self.draw_thing(D, img, th, t)
        if t < 5.95 and modes["stack"] == "home":
            self.draw_thing(D, img, sc.stack, t)
        smood = "calm"
        for (a_, b_, m) in STICK_MOOD:
            if a_ <= t < b_:
                smood = m
        draw_stick(D, stx, sty, SRAD, smood)
        self.draw_bursts(D, t)
        if SNAP - 0.05 <= t < SNAP + 1.2:
            self.draw_shout(D, LJ, t)
        draw_foreground(D, t)
        self.draw_bubbles(D, t, LJ)
        if shake:
            im2 = img.copy()
            img.paste(im2, (int(shake * s), int(shake * 0.6 * s)))

    def draw_case(self, D, t, back):
        """L'étagère (bois), avec ses livres ; la rangée du bas est vide une fois volée. Le fond est dessiné
        derrière Bounce, les montants et les planches devant lui (quand elle tombe, il est dans la case)."""
        sc = self.sc
        v1, hgt = BC[1], BC[2]
        P = lambda v, u: sc.case_pt(t, v, u)
        if back:
            D.poly([P(0, 0), P(v1, 0), P(v1, hgt), P(0, hgt)], (40, 26, 20))
            for r, books in enumerate(sc.case_books):
                if r == 0 and t >= PICK["row"]:
                    continue
                for (vc, uc, w, h, col) in books:
                    a = sc.case_angle(t)
                    x, y = P(vc, uc)
                    draw_book(D, x, y, w, h, a, col)
            return
        th = 18.0
        for (va, vb) in ((0, th), (v1 - th, v1)):
            D.poly([P(va, 0), P(vb, 0), P(vb, hgt + 10), P(va, hgt + 10)], WOOD_D)
        for u in BC_ROWS:
            D.poly([P(-6, u - 7), P(v1 + 6, u - 7), P(v1 + 6, u + 9), P(-6, u + 9)], WOOD)

    def draw_thing(self, D, img, th, t):
        sc = self.sc
        x, y, a = sc.pose(th, t)
        if th.name == "stack":
            draw_stack(D, x, y, a)
        elif th.name == "sign":
            i, seg = sc.seg_of(th, t)
            if seg[1] == "home":
                c1 = (x + rot(-SIGN_W / 2 + 22, -SIGN_H / 2, a)[0], y + rot(-SIGN_W / 2 + 22, -SIGN_H / 2, a)[1])
                c2 = (x + rot(SIGN_W / 2 - 22, -SIGN_H / 2, a)[0], y + rot(SIGN_W / 2 - 22, -SIGN_H / 2, a)[1])
                D.line([c1, NAIL, c2], (180, 170, 150), 5)
            paste_rot(img, D, sign_image(D.ws), x, y, math.degrees(a))
        elif th.name == "chair":
            look = 0.0
            draw_chair_unit(D, x, y, a, t, look)
        elif th.name == "clock":
            draw_clock(D, x, y, a, t)
        elif th.name.startswith("rb"):
            b = th.book
            draw_book(D, x, y, b[2], b[3], a, b[4])

    def draw_bursts(self, D, t):
        sc = self.sc
        spots = []
        tgt = {"stack": sc.stack, "sign": sc.sign, "chair": sc.chair, "stack2": sc.stack, "row": sc.row[3],
               "clock": sc.clock, "sign2": sc.sign}
        for name, tp in PICK.items():
            if 0 <= t - tp <= 0.45:
                x, y, _a = sc.pose(tgt[name], tp + 0.15)
                spots.append((tp, x, y, 1.4 if name in ("chair", "row") else 1.1))
        if 0 <= t - STICK_ON_HER <= 0.45:
            x, y, _a = sc.stick_pos(STICK_ON_HER)
            spots.append((STICK_ON_HER, x, y, 1.2))
        if 0 <= t - LIB_STUCK <= 0.45:
            J = sc.lib_joints(LIB_STUCK + 0.3)
            spots.append((LIB_STUCK, J["h1"][0], J["h1"][1], 1.2))
        for (tp, x, y, k) in spots:
            u = (t - tp) / 0.45
            for i in range(10):
                ang = i * math.pi / 5 + 0.3
                r0 = (60 + 90 * u) * k
                r1 = r0 + 46 * (1 - u) * k
                D.line([(x + r0 * math.cos(ang), y + r0 * math.sin(ang)), (x + r1 * math.cos(ang), y + r1 * math.sin(ang))],
                       mix((255, 255, 255), ST_L, u), 12 * (1 - u) + 3)

    def draw_shout(self, D, J, t):
        hx, hy = J["head"]
        u = (t - SNAP + 0.05) / 1.25
        k = math.sin(math.pi * clamp01(u))
        for i in range(12):
            ang = -math.pi * (0.05 + 0.9 * i / 11) + 0.05 * math.sin(t * 40 + i)
            r0 = 90 + 40 * k
            r1 = r0 + 110 * k + 14 * math.sin(t * 50 + i * 2)
            D.line([(hx + r0 * math.cos(ang), hy + r0 * math.sin(ang)),
                    (hx + r1 * math.cos(ang), hy + r1 * math.sin(ang))], (255, 236, 190), 12)

    def draw_rings(self, D, t):
        tv = vt(t)
        for (th, g, x, y) in self.sc.P.hits:
            u = tv - vt(th)
            if u < 0 or u > 0.5 or g < 0.35:
                continue
            r = BR + 14 + 700 * u
            rmax = BR + 50 + 150 * g
            if r > rmax:
                continue
            k = 1 - (r - BR) / max(1.0, rmax - BR)
            D.ring(x, Y_FLOOR, r, mix(WALL, (250, 248, 255), 0.5 + 0.5 * k), (8 + 9 * min(1.4, g)) * k)

    def draw_ball(self, dr, X, Y, rx, ry, s):
        r = max(rx, ry)
        size = int(2 * r * 1.7 * s) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO["pos"]
        base.ball(ld, size / 2, size / 2, BR * s)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size * rx / BR)), max(2, int(size * ry / BR))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        dr._image.paste(layer, (int(X - nw / 2), int(Y - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (X, Y)

    def expr_at(self, t):
        for (a, b, e) in EXPR:
            if a <= t < b:
                return e
        for (th, g, _x, _y) in self.sc.P.hits:
            if g >= 1.25 and 0 <= t - th < 0.5:
                return "shock"
        return "calm"

    def draw_bubbles(self, D, t, LJ):
        """Les répliques, dans une bulle à côté de qui parle (une à la fois)."""
        sc = self.sc
        for (who, text, a, b, key) in self.subs:
            if not (a <= t <= b):
                continue
            k = clamp01((t - a) / 0.1)
            txt = text.replace("...", "…")
            big = key == "l_snap"
            fs = (150 if big else (74 if who == "lib" else 70)) * (0.8 + 0.2 * k)
            if who == "stick":
                x, y, _ = sc.stick_pos(t)
                tx, ty = x, y - SRAD
                cx, cy = x + 40, y - SRAD - 110
                fill, ink = ST_L, (10, 40, 20)
            else:
                hx, hy = LJ["head"]
                tx, ty = hx, hy - 60
                cx, cy = hx, hy - 210
                fill, ink = anger_col(ANGER(t)), (255, 255, 255)
                if big:
                    cx, cy = 560, 760
            f = font(fs * D.s)
            w = f.getlength(txt) / D.s + 60
            h = fs * 1.35
            cx = max(130 + w / 2, min(880 - w / 2, cx))
            cy = max(520 + h / 2, min(1150, cy))
            if not big:
                D.poly([(cx - 22, cy + h / 2 - 6), (cx + 22, cy + h / 2 - 6), (tx, max(ty, cy + h / 2 + 10))],
                       (16, 14, 18))
                D.poly([(cx - 16, cy + h / 2 - 8), (cx + 16, cy + h / 2 - 8), (tx, max(ty, cy + h / 2 + 4))], fill)
            D.rect(cx - w / 2 - 5, cy - h / 2 - 5, cx + w / 2 + 5, cy + h / 2 + 5, (16, 14, 18), r=h / 2.2)
            D.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill, r=h / 2.2)
            D.text(cx, cy + 3, txt, fs, ink)

    def post(self, img, t):
        """L'accroche, redessinée par-dessus tout, avec un contour : rien ne la recouvre."""
        if self._hook is None:
            cfg = self.cfg
            Wp, Hp = img.size
            lines, hf, lh, top = base.layout_hook(cfg, 1, Wp, Hp, Hp * self.scene_top - 30)
            self._hook = (lines, hf, lh, top)
        lines, hf, lh, top = self._hook
        d = ImageDraw.Draw(img)
        sw = max(2, int(img.size[0] / 1080 * 7))
        for i, line in enumerate(lines):
            d.text((img.size[0] / 2, top + (i + 0.5) * lh), line, fill=(255, 255, 255), anchor="mm", font=hf,
                   stroke_width=sw, stroke_fill=(12, 10, 14))
        return img


# ------------------------------------------------------------------ audio, rendu
def fft_reverb(x, sr, tail_s=0.7, wet=0.35, seed=7):
    """Réverbération par convolution FFT (même principe que base.reverb, sans np.convolve lent)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    N = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


VOICE_LEVEL = 0.55     # tout le reste est plus bas : le « QUIET! » final domine nettement


def exact_events(sim):
    return [(t, "hit", "h%d" % i) for i, (t, g, x, y) in enumerate(sim.sc.P.hits)]


def render_audio(sim, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is not None:
        words = base.place_words(exact_events(sim), total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        for (t0, kind, _d, tag) in words:
            g = sim.hit_gain(t0)
            gg = max(0.1, min(1.5, g)) ** 0.8 * 0.95 * VOICE_LEVEL
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
    for n in narr:
        x = n["audio"]
        g = LINE_GAIN.get(n["key"], 1.15 if n["key"].startswith("s_") else 1.0)
        if n["key"] == "l_snap":
            x = fft_reverb(x, SR, 1.1, 0.35)
        else:
            g *= VOICE_LEVEL
        ak.add(buf, x, n["start"], gain=g)
    v = hook_clip(cfg) if cfg.get("hook_voice") else None
    if v is not None:
        a, n = int(HOOK_T * SR), len(v)
        duck = np.ones(len(buf))
        duck[a:a + n] = 0.42
        m = int(0.3 * SR)
        duck[a + n:a + n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, HOOK_T, gain=VOICE_LEVEL * 1.1)
    # mixage : normalisation sur le corps (sans le cri), puis le cri passe au-dessus, limité en douceur
    body = np.concatenate([buf[:int(SNAP * SR)], buf[int((SNAP + 1.6) * SR):]])
    m = np.percentile(np.abs(body), 99.5) + 1e-9
    out = np.tanh(buf / m * 0.5) / np.tanh(0.5 * np.max(np.abs(buf)) / m) * 0.97
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())
    return {"hero": cfg["hero_name"], "said": said}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.set_narr(narr)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "hits": len(ev),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [round(e[0], 3) for e in ev if round(e[0], 3) not in said]
    if hv is not None:
        summary["chevauche_accroche"] = [round(e[0], 2) for e in ev
                                         if e[0] + len(name) / SR > HOOK_T - 0.05 and e[0] < HOOK_T + len(hv) / SR + 0.05]
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
