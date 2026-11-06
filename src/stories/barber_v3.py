"""
Prototype « barber » v3. Bounce est le client, tignasse énorme, et il ne tient pas en place dans le fauteuil :
chaque rebond fait rater la tondeuse et creuse dans SA tignasse un dégât qui reste (raie, trou, côté rasé,
tonsure, crête). Chaque touffe atterrit sur le crâne chauve du voisin caché derrière son journal, qui se fait
un afro avec les cheveux de Bounce. Faux arrêt sur un coussin (« Easy... easy. »), ralenti : la casquette du
barbier tombe, il est chauve. La crête finit en antenne, coupée. Bounce, chauve, saute dans l'afro du voisin
et le lui reprend ; le voisin baisse son journal, chauve. Puis chaque rebond envoie une touffe sur le crâne du
barbier (le voisin essaie d'en attraper). Il ne reste à Bounce qu'une barbe : miroir, « Perfect! », saut de
joie, la barbe s'envole sur le barbier. « Oh no! ». Dernier « Bounce » : le barbier se rase une raie dans
sa nouvelle coiffure, la même qu'à l'image 0.

Le temps du récit (tau) est étiré par un ralenti ; l'audio suit les instants exacts des contacts.

    python3 src/stories/barber_v3.py configs/<name>.json [--simulate]
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
SCR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad"
BANK_DIR = os.environ.get("BARBER_BANK", SCR + "/lundi/barber/voix")
HERO_CACHE = SCR + "/lot6/baby/final"        # la même prise du mot « Bounce » que les autres vidéos

# ------------------------------------------------------------------ voix (banque vérifiée par whisper)
BANK_FILES = {"Easy... easy.": "easy_am_michael.wav", "Perfect.": "perfect_am_michael.wav"}
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
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(HERO_CACHE, "hero_%s_%s_%s.wav" % key)
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
            f = max(cfg.get("hook_speed", 1.1), len(v) / SR / cfg.get("hook_max_s", 1.1))
            v = base.pitch(v, f)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
G = 2600.0
R = 145.0


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


def lerp2(p, q, k):
    return (lerp(p[0], q[0], k), lerp(p[1], q[1], k))


def win(t, a, b, fi=0.15, fo=0.15):
    if t < a - fi or t > b + fo:
        return 0.0
    return smooth((t - (a - fi)) / max(1e-6, fi)) * smooth(((b + fo) - t) / max(1e-6, fo))


def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


# ------------------------------------------------------------------ décor (écran 1080×1920)
FLOOR_Y = 1690.0
SEAT_Y = 1312.0
CX = 445.0                         # le fauteuil de Bounce
ARM_Y = 1225.0
CUSH_TOP = 1250.0
NB = (150.0, 1040.0)               # tête du voisin
NB_R = 66.0
BX0 = 760.0                        # le barbier (corps dans x 670–850)
BHEAD_R = 80.0

WALL = (18, 32, 38)
WALL_L = (24, 42, 48)
TILE_A = (34, 34, 40)
TILE_B = (54, 54, 62)
HAIR = (150, 96, 58)
HAIR_L = (196, 138, 92)
HAIR_D = (52, 30, 20)
NSKIN = (198, 140, 106)
NSKIN_D = (160, 104, 76)
NSKIN_L = (232, 186, 160)
NCAPE = (92, 100, 118)
NCAPE_D = (70, 76, 92)
COAT = (226, 230, 236)
COAT_D = (178, 184, 196)
BSKIN = (166, 112, 86)
BSKIN_L = (204, 156, 130)
CAP = (60, 110, 190)
CAP_D = (40, 80, 150)
PAPER = (228, 224, 210)
PAPER_D = (150, 146, 136)
CHROME = (160, 168, 182)
CHROME_D = (96, 102, 116)
SEAT = (168, 40, 52)
SEAT_D = (120, 26, 36)
CUSH_C = (110, 196, 166)
CUSH_D = (76, 150, 124)
CLIP_C = (54, 56, 70)
MIRROR = (176, 208, 224)
SCALP = (236, 40, 190)                 # le crâne de Bounce, sous ses cheveux (sa couleur, à peine plus sombre)
FRAME = (206, 166, 84)

SPOT = {"seat": (CX, SEAT_Y - R), "cush": (CX, CUSH_TOP - R + 28), "arm": (CX - 140.0, ARM_Y - R + 4),
        "nb": (NB[0] + 20.0, NB[1] - NB_R - R + 70.0)}
HARD = {"H", "arm", "nbH"}

# ------------------------------------------------------------------ le plan, événement par événement
# (genre, écart depuis le contact précédent, gain, étiquette)
#   H = contact dur sur l'assise ; r = il se tasse et gigote (muet) ; c = coussin (mou) ; cr = tassé sur le coussin
#   arm = accoudoir (dur) ; nb = dans l'afro du voisin (mou) ; nbr = tassé dedans ; nbH = sur le crâne du voisin (dur)
SEQ = [
    ("H", 0.90, 1.1, "d1"), ("r", 0.35, 0, "react1"), ("H", 1.55, 1.0, "d2"), ("H", 0.90, 0.95, "d3"),
    ("r", 0.35, 0, "react2"), ("H", 1.40, 0.9, "holdhop"), ("r", 0.35, 0, ""), ("H", 1.25, 1.2, "d4"),
    ("H", 1.00, 1.0, "d5"), ("r", 0.35, 0, "comb1"), ("H", 1.85, 1.05, "d5b"), ("H", 0.95, 1.15, "d6"),
    ("r", 0.35, 0, "react3"), ("H", 1.50, 1.0, "d6b"), ("r", 0.35, 0, "hug"), ("H", 1.90, 1.1, "d7"), ("H", 1.00, 1.2, "d8"), ("H", 1.05, 1.4, "d9"),
    ("r", 0.35, 0, "pause"), ("H", 1.65, 0.9, "gocush"), ("c", 0.95, 0, "cush1"), ("c", 0.70, 0, ""),
    ("c", 0.45, 0, ""), ("cr", 0.35, 0, "easy"), ("c", 2.20, 0, "cushbig"), ("arm", 0.55, 1.4, "slow"),
    ("c", 0.50, 0, ""), ("H", 1.10, 1.0, "after"), ("r", 0.35, 0, "baldbarber"), ("H", 1.90, 1.05, "ant"),
    ("r", 0.35, 0, ""), ("H", 1.40, 1.1, "snip"), ("r", 0.35, 0, "bare"), ("H", 1.30, 1.0, "launch"),
    ("nb", 1.00, 0, "pile"), ("nbr", 0.35, 0, "pat"), ("nbH", 1.20, 0.85, "patH"), ("nbr", 0.35, 0, ""), ("nbH", 1.20, 1.0, "steal"), ("H", 1.00, 1.15, "stolen"),
    ("r", 0.35, 0, "nbbald"), ("H", 2.00, 0.9, "nbgrab"), ("r", 0.35, 0, ""), ("H", 1.30, 1.0, "t1"),
    ("H", 0.90, 0.95, "t2"), ("r", 0.35, 0, "touch"), ("H", 1.45, 1.0, "t3"), ("H", 0.90, 1.0, "t4"),
    ("r", 0.35, 0, "shimmy"), ("H", 1.80, 1.05, "t5"), ("H", 0.90, 1.0, "t6"), ("r", 0.35, 0, ""),
    ("H", 1.40, 1.05, "t7"), ("H", 0.95, 1.1, "t8"), ("r", 0.35, 0, "mirror"), ("H", 3.40, 0.9, "proud1"),
    ("H", 0.95, 1.3, "issue"), ("r", 0.35, 0, "ohno"), ("H", 2.90, 1.2, "last"), ("r", 0.95, 0, "final"),
]
START = -0.60                      # contact virtuel : avant l'image 0 (la première raie est déjà faite)
_P = []
T = {}
_t = START
T["d0"] = START
for (k, dt, g, lab) in SEQ:
    _t = round(_t + dt, 3)
    _P.append((_t, k, g))
    if lab:
        T[lab] = _t
END = T["last"] + 1.85
ISSUE = T["issue"]
# repères dérivés
T.update(hold=T["react2"] + 0.25, hold_end=T["d4"], lift_end=T["d5"], cush_in=T["gocush"] + 0.1,
         cush_land=T["cush1"] - 0.05, peek=T["easy"] + 0.65, peek_end=T["easy"] + 2.75, cap_off=T["slow"] + 0.3,
         yank=T["after"] - 0.75, comb0=T["comb1"] + 0.15, comb1=T["d5b"] - 0.1, nb_low=T["nbbald"] + 0.15,
         perfect=T["mirror"] + 0.95, love=T["mirror"] + 1.9)
SLOW_A = T["slow"] + 0.05          # ralenti : il commence au contact sur l'accoudoir
SLOW_L = 2.5
SLOW_F = 0.33
LINES_TAU = [(T["easy"] + 0.1, "Easy... easy.", "easy", 1.09), (T["perfect"], "Perfect.", "perfect", 0.67)]


def warp(t):
    if t < SLOW_A:
        return t
    if t < SLOW_A + SLOW_L:
        return SLOW_A + (t - SLOW_A) * SLOW_F
    return t - SLOW_L * (1 - SLOW_F)


def unwarp(tau):
    if tau < SLOW_A:
        return tau
    if tau < SLOW_A + SLOW_L * SLOW_F:
        return SLOW_A + (tau - SLOW_A) / SLOW_F
    return tau + SLOW_L * (1 - SLOW_F)


def talking(tau):
    for (t0, _txt, _k, d) in LINES_TAU:
        if t0 <= tau <= t0 + d:
            return (tau - t0) / d
    return None


class Plan:
    def __init__(self):
        self.cs = []
        for (t, k, g) in _P:
            base_k = {"H": "seat", "r": "seat", "c": "cush", "cr": "cush", "nbr": "nb", "nbH": "nb"}.get(k, k)
            x, y = SPOT[base_k]
            if k in ("r", "cr", "nbr"):
                y += 6
            if k == "nbH":
                y += 26
            self.cs.append({"t": t, "k": k, "x": x, "y": y, "g": g, "soft": k not in HARD})
        self.ts = [c["t"] for c in self.cs]
        self.start = {"t": START, "k": "start", "x": CX, "y": SPOT["seat"][1]}
        self.after = {"t": END + 0.5, "k": "end", "x": CX, "y": SPOT["seat"][1] + 6}
        self.hits = [(c["t"], c["g"], c["x"], c["y"], c["k"]) for c in self.cs if not c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.cs[i - 1]
        b = self.after if i >= len(self.cs) else self.cs[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        if a["k"] == "final":
            return a["x"] + 5 * math.sin(t * 17.0), a["y"] - 4 * abs(math.sin(t * 8.0))
        if a["k"] in ("r", "cr", "nbr"):
            hop = 0.42 if abs(b["x"] - a["x"]) < 30 else 0.95
            if t < b["t"] - hop:
                return a["x"] + 5 * math.sin(t * 17.0), a["y"] - 4 * abs(math.sin(t * 8.0))
            a = {"t": b["t"] - hop, "x": a["x"] + 5 * math.sin((b["t"] - hop) * 17.0), "y": a["y"]}
        Tt = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / Tt
        vy = (b["y"] - a["y"]) / Tt - 0.5 * G * Tt
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def rise(self, t):
        return max(0.0, SPOT["seat"][1] - self.pos(t)[1])

    def squash(self, t):
        sx = sy = 1.0
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.cs[i:i + 4]:
            if c["k"] in ("r", "cr", "nbr", "final"):
                continue
            u = t - c["t"]
            if -0.05 <= u <= 0.16:
                kk = clamp01(1 + u / 0.05) if u < 0 else clamp01(1 - u / 0.16)
                amp = 0.24 if c["soft"] else 0.2
                sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
        return sx, sy


PLAN = Plan()
JOLTS = [(t, g) for (t, g, x, y, k) in PLAN.hits]


def jolt(tau, decay=0.3):
    v = 0.0
    for (t0, g) in JOLTS:
        u = tau - t0
        if 0 <= u <= 0.7:
            k = math.sin(math.pi * clamp01(u / 0.12)) if u < 0.12 else math.exp(-(u - 0.12) / decay)
            v = max(v, g * k)
    return v


# ------------------------------------------------------------------ cheveux
def _cloud(cx, cy, rx, ry, n, rmin, rmax, gap, seed):
    rr = np.random.default_rng(seed)
    pts, tries = [], 0
    while len(pts) < n and tries < 40000:
        tries += 1
        x, y = rr.uniform(-1, 1), rr.uniform(-1, 1)
        if x * x + y * y > 1:
            continue
        px, py = cx + x * rx, cy + y * ry
        if px * px + py * py < (0.98 * R) ** 2 and py > -0.74 * R:
            continue
        if py > 0.3 * R and abs(px) < 1.2 * R:
            continue
        if any((px - q[0]) ** 2 + (py - q[1]) ** 2 < gap * gap for q in pts):
            continue
        pts.append((px, py, rr.uniform(rmin, rmax), rr.uniform(0, 1)))
    return pts


HAIR1 = _cloud(0.0, -150.0, 228.0, 185.0, 150, 30, 40, 22, 23)
# les dégâts : chacun différent, ils restent
CUTS1 = [
    (T["d0"], ("seg", (-225, -150), (-45, -330), 32)),        # une raie chauve en travers (déjà là à l'image 0)
    (T["d1"], ("circ", (135, -185), 62)),                     # un gros trou à droite
    (T["d2"], ("x<", -150.0)),                                 # le côté gauche rasé
    (T["d3"], ("circ", (115, -310), 52)),                      # une encoche au sommet
    (T["d4"], ("x>", 165.0)),                                  # le côté droit rasé
    (T["d5"], ("circ", (-95, -150), 52)),                      # un trou devant à gauche
    (T["d5b"], ("seg", (-150, -260), (-60, -300), 30)),        # la mèche rabattue repart
    (T["d6"], ("circ", (-80, -250), 48)),                       # une tonsure
    (T["d6b"], ("seg", (75, -110), (150, -210), 30)),          # une raie en biais, devant
    (T["d7"], ("x<", -70.0)),
    (T["d8"], ("x>", 70.0)),
    (T["d9"], ("crest", 54.0)),                                # il ne reste qu'une crête
    (T["slow"] + 0.15, ("y<", -300.0)),                        # au ralenti : la crête raccourcie
]


def _seg_d(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    u = clamp01(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy + 1e-9))
    return math.hypot(px - (ax + u * vx), py - (ay + u * vy))


def _hit(rule, x, y):
    k = rule[0]
    if k == "x>":
        return x > rule[1]
    if k == "x<":
        return x < rule[1]
    if k == "y<":
        return y < rule[1]
    if k == "seg":
        return _seg_d((x, y), rule[1], rule[2]) < rule[3]
    if k == "circ":
        return math.hypot(x - rule[1][0], y - rule[1][1]) < rule[2]
    if k == "crest":
        return abs(x) > rule[1] or y > -R * 0.9
    return False


CUT1_T = [None] * len(HAIR1)
for (t, rule) in CUTS1:
    for i, (x, y, r, s) in enumerate(HAIR1):
        if CUT1_T[i] is None and _hit(rule, x, y):
            CUT1_T[i] = t
REMAIN = [i for i in range(len(HAIR1)) if CUT1_T[i] is None]

# l'afro repris au voisin : gros, avec une barbe et une moustache
HAIR2 = _cloud(28.0, -150.0, 200.0, 190.0, 150, 30, 40, 22, 29)
BEARD = []
for k in range(15):
    a = math.radians(12 + 156 * k / 14)
    BEARD.append((math.cos(a) * R * 1.02, math.sin(a) * R * 1.02 + 6, 33.0 + 4 * math.sin(k), 0.3 + 0.04 * k))
for k in range(9):
    a = math.radians(30 + 120 * k / 8)
    BEARD.append((math.cos(a) * R * 1.3, math.sin(a) * R * 1.24 + 4, 30.0, 0.6))
MUST = [(-52.0, 40.0, 20.0, 0.7), (-27.0, 33.0, 21.0, 0.5), (0.0, 36.0, 21.0, 0.4), (27.0, 33.0, 21.0, 0.5),
        (52.0, 40.0, 20.0, 0.7)]
HAIR2_ALL = HAIR2 + BEARD + MUST
NB2 = len(HAIR2)
TSTEPS = [("t1", -270.0), ("t2", -225.0), ("t3", -180.0), ("t4", -140.0), ("t5", -100.0), ("t6", -60.0),
          ("t7", -20.0), ("t8", 10.0)]
CUT2_T = [None] * len(HAIR2_ALL)
for (lab, yl) in TSTEPS:
    for i, (x, y, r, s) in enumerate(HAIR2_ALL):
        if CUT2_T[i] is None and i < NB2 and y < yl:
            CUT2_T[i] = T[lab]
KEEP2 = [i for i in range(len(HAIR2_ALL)) if CUT2_T[i] is None]
CAUGHT = {T["t4"], T["t7"]}          # ces touffes-là, le voisin les attrape


def ant_curve(ph, j, n, L=260.0):
    k = j / max(1, n - 1)
    x = y = 0.0
    for i in range(12):
        s0 = k * (i + 0.5) / 12
        th = ph * s0 ** 1.3
        x += math.sin(th) * L * k / 12
        y -= math.cos(th) * L * k / 12
    return (x + 6 * math.sin(j * 2.1), y - R + 4, 24.0 - 9 * k)


def ant_angle(tau):
    u = tau - T["ant"]
    a = 0.0
    if u >= 0:
        a += 0.35 * math.exp(-u / 0.45) * math.sin(u * 16)
    a += math.radians(-160) * smooth((tau - (T["snip"] - 0.9)) / 0.8)    # elle fane avant d'être coupée
    return a


# ------------------------------------------------------------------ où atterrissent les cheveux
def _slots(cx, cy, rx, ry, n, seed, ref):
    rr = np.random.default_rng(seed)
    pts, tries = [], 0
    while len(pts) < n and tries < 60000:
        tries += 1
        x, y = rr.uniform(-1, 1), rr.uniform(-1, 0.3)
        if x * x + y * y > 1:
            continue
        px, py = cx + x * rx, cy + y * ry
        if any((px - q[0]) ** 2 + (py - q[1]) ** 2 < 19 * 19 for q in pts):
            continue
        pts.append((px, py))
    pts.sort(key=lambda p: math.hypot(p[0] - ref[0], (p[1] - ref[1]) * 1.3))
    return pts


PILE = _slots(NB[0], NB[1] - NB_R + 20, 175.0, 175.0, 150, 41, (NB[0], NB[1] - NB_R))     # sur le voisin
NB_TUFT = [(NB[0] - 10, NB[1] - NB_R - 6), (NB[0] + 22, NB[1] - NB_R - 2)]                 # ce qu'il rattrape


def _particles():
    events = []
    for i, (x, y, r, s) in enumerate(HAIR1):
        if CUT1_T[i] is not None:
            events.append((CUT1_T[i], ("h1", i), r, s))
    for j, i in enumerate(REMAIN):
        events.append((T["snip"] + 0.02 * j, ("ant", j), 22.0, HAIR1[i][3]))
    events.sort(key=lambda e: e[0])
    out = []
    for n, e in enumerate(events):
        out.append({"t0": e[0], "src": e[1], "slot": PILE[min(n, len(PILE) - 1)], "dur": 0.55 + 0.08 * (n % 3),
                    "r": e[2], "s": e[3]})
    return out


PARTS = _particles()


def pile_count(tau):
    return sum(1 for p in PARTS if p["t0"] + p["dur"] <= tau)


def barber_slots():
    """La coiffure qui pousse sur le crâne du barbier : de petites touffes, puis un afro, puis la barbe."""
    rr = np.random.default_rng(57)
    pts, tries = [], 0
    while len(pts) < 110 and tries < 60000:
        tries += 1
        x, y = rr.uniform(-1, 1), rr.uniform(-1, 0.15)
        if x * x + y * y > 1:
            continue
        px, py = x * 175, -BHEAD_R + 30 + y * 160
        if any((px - q[0]) ** 2 + (py - q[1]) ** 2 < 19 * 19 for q in pts):
            continue
        pts.append((px, py))
    pts.sort(key=lambda p: math.hypot(p[0], (p[1] + BHEAD_R) * 1.3))
    return pts


BSLOTS = barber_slots()


def _bparticles():
    ev = []
    for i, (x, y, r, s) in enumerate(HAIR2_ALL):
        if CUT2_T[i] is not None:
            ev.append((CUT2_T[i], i))
    ev.sort()
    out = []
    nb_k = 0
    bk = 0
    for (t0, i) in ev:
        if t0 in CAUGHT and nb_k < 6 and (i % 3 == 0):
            out.append({"t0": t0, "i": i, "to": "nb", "slot": NB_TUFT[nb_k % 2], "dur": 0.6})
            nb_k += 1
        else:
            out.append({"t0": t0, "i": i, "to": "barber", "slot": BSLOTS[min(bk, len(BSLOTS) - 1)], "dur": 0.6})
            bk += 1
    for i in KEEP2:                                   # l'issue : la barbe s'envole sur le barbier
        out.append({"t0": ISSUE, "i": i, "to": "barber", "slot": BSLOTS[min(bk, len(BSLOTS) - 1)], "dur": 0.6})
        bk += 1
    return out


BPARTS = _bparticles()
STRIPE_T = T["last"] + 0.05                           # la raie du barbier, au dernier sursaut


# ------------------------------------------------------------------ primitives
def P(pts, S):
    return [(x * S, y * S) for x, y in pts]


def ell(dr, x, y, rx, ry, col, S):
    dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=col)


def rect(dr, x0, y0, x1, y1, col, S, r=0):
    if r:
        dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=col)
    else:
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)


def capsule(dr, p0, p1, r, col, S):
    dr.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=col, width=max(1, int(2 * r * S)))
    for p in (p0, p1):
        dr.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)


def cloud(dr, pts, S):
    for (x, y, r, s) in pts:
        ell(dr, x, y, r + 4, r + 4, HAIR_D, S)
    for (x, y, r, s) in pts:
        ell(dr, x, y, r, r, mix(HAIR, HAIR_L, 0.2 * s), S)
    for (x, y, r, s) in pts:
        if s > 0.4:
            ell(dr, x - r * 0.3, y - r * 0.32, r * 0.42, r * 0.22, HAIR_L, S)


def arm_ik(sh, target, L1=170.0, L2=180.0, bend=1.0):
    dx, dy = target[0] - sh[0], target[1] - sh[1]
    d = math.hypot(dx, dy)
    dmax = L1 + L2 - 4
    if d > dmax:
        target = (sh[0] + dx / d * dmax, sh[1] + dy / d * dmax)
        d = dmax
    d = max(d, 40.0)
    a = math.atan2(target[1] - sh[1], target[0] - sh[0])
    cb = max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))
    b = math.acos(cb)
    el = (sh[0] + L1 * math.cos(a + bend * b), sh[1] + L1 * math.sin(a + bend * b))
    return el, target


def cushion_state(tau):
    t = T
    if tau < t["cush_in"]:
        return None
    if tau < t["cush_land"]:
        u = smooth((tau - t["cush_in"]) / (t["cush_land"] - t["cush_in"]))
        return (lerp(860.0, CX, u), lerp(1000.0, CUSH_TOP + 30, u) - 160 * math.sin(math.pi * u), 0.0)
    if tau < t["yank"]:
        return (CX, CUSH_TOP + 30, 0.0)
    u = tau - t["yank"]
    if u > 0.8:
        return None
    return (CX + 520 * u, CUSH_TOP + 30 - 520 * u + 1300 * u * u, 4 * u)


# ------------------------------------------------------------------ Sim
class Sim:
    scene_top = 0.262

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_real = [unwarp(h[0]) for h in PLAN.hits if h[0] >= 0]
        self.hi = 0
        self.lines = [(unwarp(tt), txt, key) for (tt, txt, key, _d) in LINES_TAU]
        self.replies = []
        self.rings = [(h[0], h[1], h[2], h[3]) for h in PLAN.hits]
        self.bx = KF(BX0, [(T["hold"] - 0.3, BX0), (T["hold"], 700.0), (T["lift_end"] + 0.2, 700.0),
                           (T["lift_end"] + 0.7, BX0), (T["hug"], BX0), (T["hug"] + 0.6, 560.0),
                           (T["d9"], 560.0), (T["d9"] + 0.35, 830.0), (T["d9"] + 1.1, BX0),
                           (T["mirror"] - 0.3, BX0), (T["mirror"] + 0.3, 800.0)])
        self.lean = KF(0.0, [(T["d9"], 0.0), (T["d9"] + 0.3, 14.0), (T["d9"] + 1.3, 0.0),
                             (T["t5"] - 0.6, 0.0), (T["t5"] - 0.2, -16.0), (T["t6"] + 0.4, -16.0),
                             (T["t6"] + 0.8, 0.0)])

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_real) and self.hit_real[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= unwarp(END) - 1e-9:
            self.done = True
            self.payoff = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t_real):
        best, bd = 0.9, 1e9
        for (th, g, _x, _y, _k) in PLAN.hits:
            d = abs(unwarp(th) - t_real)
            if d < bd:
                best, bd = g, d
        return best

    def barber_lift(self, tau):
        t = T
        if t["hold_end"] - 0.05 <= tau <= t["lift_end"]:
            return 0.55 * PLAN.rise(tau)
        if t["d7"] - 0.02 <= tau <= t["d9"]:
            return 0.85 * PLAN.rise(tau)
        u = tau - t["d9"]
        if 0 <= u <= 0.5:
            return 160 * math.sin(math.pi * u / 0.5) * (1 - u)
        return 0.0

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        tau = warp(float(t))
        S = S * self.cfg["width"] / W
        bpos = PLAN.pos(tau)
        self.draw_room(dr, tau, S)
        self.draw_neighbor(dr, tau, S, bpos, layer="back")
        self.draw_barber(dr, tau, S, body=True)
        self.draw_chair(dr, tau, S, bpos)
        self.draw_rings(dr, tau, S)
        in_pile = T["pile"] - 0.05 <= tau < T["steal"] + 0.02
        if in_pile:
            self.draw_pile(dr, tau, S, bpos, part="back")
        self.draw_bounce(dr, tau, S, bpos)
        self.draw_neighbor(dr, tau, S, bpos, layer="front")
        if in_pile:
            self.draw_pile(dr, tau, S, bpos, part="front")
        self.draw_barber(dr, tau, S, body=False)
        self.draw_particles(dr, tau, S)

    # -------- Bounce
    def expr_at(self, tau):
        t = T
        for (a, b, e) in [(t["react1"] + 0.1, t["react1"] + 0.9, "shock"), (t["react2"] + 0.2, t["react2"] + 1.2, "lose"),
                          (t["d9"], t["d9"] + 0.5, "shock"), (t["pause"] + 0.1, t["gocush"] - 0.2, "lose"),
                          (t["slow"], t["slow"] + 0.9, "shock"), (t["bare"] + 0.1, t["launch"] - 0.3, "lose"),
                          (t["launch"] - 0.3, t["launch"] + 0.2, "win"), (t["stolen"], t["stolen"] + 1.6, "win"),
                          (t["love"], t["issue"], "win"), (t["issue"] + 0.3, 99.0, "lose")]:
            if a <= tau < b:
                return e
        for (th, g, _x, _y, _k) in PLAN.hits:
            if g >= 1.25 and 0 <= tau - th < 0.4:
                return "shock"
        return "calm"

    def hair_now(self, tau):
        t = T
        out = []
        if tau < t["ant"] - 0.3:
            for i, (x, y, r, s) in enumerate(HAIR1):
                if CUT1_T[i] is None or tau < CUT1_T[i]:
                    if T["comb0"] <= tau < T["d5b"] and x < -40:      # il rabat une mèche sur les trous
                        k = smooth((tau - T["comb0"]) / 1.2)
                        x, y = lerp(x, x + 70, k), lerp(y, y - 40, k)
                    out.append((x, y, r, s))
            return out
        if tau < t["snip"]:
            n = len(REMAIN)
            for j, i in enumerate(REMAIN):
                x, y, r, s = HAIR1[i]
                u = smooth((tau - (t["ant"] - 0.3)) / 0.3)
                ax, ay, ar = ant_curve(ant_angle(tau), j, n)
                out.append((lerp(x, ax, u), lerp(y, ay, u), lerp(r, ar, u), s))
            return out
        if tau < t["steal"]:
            return out
        if tau < t["issue"]:
            for i, (x, y, r, s) in enumerate(HAIR2_ALL):
                if CUT2_T[i] is None or tau < CUT2_T[i]:
                    wob = 0.0
                    if i >= NB2 and t["proud1"] <= tau < t["issue"]:
                        wob = 18 * math.exp(-(tau - t["proud1"]) / 0.5) * math.sin((tau - t["proud1"]) * 14)
                    out.append((x + wob * 0.3, y + wob, r, s))
        return out

    def draw_bounce(self, dr, tau, S, bpos):
        base.HERO["expr"] = self.expr_at(tau)
        bx, by = bpos
        sx, sy = PLAN.squash(tau)
        # le cuir chevelu sous la tignasse : chaque trou se lit comme une plaque chauve
        k = 1.0 - smooth((tau - (T["ant"] - 0.35)) / 0.3)
        if k > 0.02:
            col = SCALP
            for (x, y, r, s) in HAIR1:
                if math.hypot(x, y) > 0.8 * R:
                    rr = r * 0.95 * k
                    ell(dr, bx + x * k * sx, by + y * (0.55 + 0.45 * k) * sy, rr, rr, col, S)
        self.draw_ball(dr, bx, by, R * sx, R * sy, S)
        cloud(dr, [(bx + x * sx, by + y * sy, r, s) for (x, y, r, s) in self.hair_now(tau)], S)

    def draw_ball(self, dr, x, y, rx, ry, S):
        if abs(rx - ry) < 0.5:
            base.ball(dr, x * S, y * S, rx * S)
            return
        r = max(rx, ry)
        size = int(2 * r * 1.7 * S) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO["pos"]
        base.ball(ld, size / 2, size / 2, R * S)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size * rx / R)), max(2, int(size * ry / R))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        dr._image.paste(layer, (int(x * S - nw / 2), int(y * S - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (x * S, y * S)

    # -------- décor
    def draw_room(self, dr, tau, S):
        rect(dr, 0, 0, W, FLOOR_Y, WALL, S)
        for k in range(12):
            rect(dr, 45 + k * 90, 0, 55 + k * 90, FLOOR_Y, WALL_L, S)
        rect(dr, 0, 1390, W, 1402, (30, 52, 58), S)
        rect(dr, 690, 560, 930, 574, (120, 90, 60), S)
        for (x, h, c) in ((715, 60, (90, 170, 210)), (760, 46, (210, 120, 70)), (805, 70, (140, 200, 110)),
                          (850, 40, (220, 200, 90)), (895, 56, (200, 110, 160))):
            rect(dr, x - 15, 560 - h, x + 15, 560, c, S, r=6)
            rect(dr, x - 6, 560 - h - 14, x + 6, 560 - h, (220, 220, 226), S)
        rect(dr, 0, FLOOR_Y, W, H, TILE_A, S)
        for row in range(6):
            y0 = FLOOR_Y + row * 44
            for col in range(13):
                if (row + col) % 2 == 0:
                    rect(dr, col * 90, y0, col * 90 + 90, y0 + 44, TILE_B, S)
        rect(dr, 0, FLOOR_Y - 6, W, FLOOR_Y, (60, 70, 76), S)

    def draw_chair(self, dr, tau, S, bpos):
        rect(dr, CX - 135, 940, CX + 135, SEAT_Y, SEAT_D, S, r=40)
        rect(dr, CX - 113, 965, CX + 113, SEAT_Y, (140, 32, 44), S, r=32)
        rect(dr, CX - 24, SEAT_Y + 64, CX + 24, 1640, CHROME, S)
        rect(dr, CX - 100, 1560, CX + 100, 1576, CHROME_D, S, r=6)
        ell(dr, CX, 1665, 185, 26, CHROME_D, S)
        ell(dr, CX, 1659, 170, 20, CHROME, S)
        dk = 0.0
        for (t0, g, xh, yh, kh) in PLAN.hits:
            u = tau - t0
            if kh == "H" and 0 <= u <= 0.3:
                dk = max(dk, 8 * g * math.sin(u * 40) * (1 - u / 0.3))
        rect(dr, CX - 160, SEAT_Y + dk, CX + 160, SEAT_Y + 64, SEAT, S, r=14)
        rect(dr, CX - 165, SEAT_Y - 4 + dk, CX + 165, SEAT_Y + 10 + dk, CHROME, S, r=6)
        for x in (CX - 140, CX + 140):
            rect(dr, x - 8, ARM_Y + 10, x + 8, SEAT_Y, CHROME_D, S)
            rect(dr, x - 28, ARM_Y - 6, x + 28, ARM_Y + 14, CHROME, S, r=8)
        cs = cushion_state(tau)
        if cs is not None:
            x, y, a = cs
            bx, by = bpos
            pts = []
            for i in range(41):
                xx = x - 120 + 240 * i / 40
                yy = y - 30 + 10 * ((2 * i / 40 - 1) ** 4)
                d = xx - bx
                if T["cush_land"] <= tau < T["yank"] and abs(d) < R * 1.02:
                    cy = by + math.sqrt(max(0.0, (R * 1.02) ** 2 - d * d))
                    yy = max(yy, min(y + 22, cy))
                pts.append((xx, yy))
            poly = pts + [(x + 120, y + 30), (x - 120, y + 30)]
            if a:
                poly = [(x + rot((px - x, py - y), a)[0], y + rot((px - x, py - y), a)[1]) for (px, py) in poly]
            dr.polygon(P(poly, S), fill=CUSH_C)
            dr.line(P(poly[:41], S), fill=CUSH_D, width=max(1, int(5 * S)))

    def draw_rings(self, dr, tau, S):
        for (t0, g, x, y) in self.rings:
            u = tau - t0
            if u < 0 or u > 0.5:
                continue
            rmax = R + 50 + 150 * g
            r = R + 10 + 800 * u
            if r > rmax:
                continue
            k = 1 - (r - R) / max(1.0, rmax - R)
            if k < 0.3:
                continue
            col = mix(WALL, (250, 250, 255), 0.55 + 0.45 * k)
            w = (10 + 9 * min(1.3, g)) * (0.6 + 0.4 * k)
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(2, int(w * S)))

    # -------- le voisin
    def nb_state(self, tau):
        """journal (0 levé .. 1 sur les genoux), tête tournée vers Bounce (0..1), main levée (0..1), sursaut."""
        t = T
        paper = 0.0
        paper = max(paper, win(tau, t["peek"], t["peek_end"], 0.4, 0.4) * 0.75)
        if tau >= t["nb_low"]:
            paper = max(paper, smooth((tau - t["nb_low"]) / 1.3))
        turn = win(tau, t["peek"] + 0.3, t["peek_end"] - 0.2, 0.3, 0.3)
        turn = max(turn, win(tau, t["nbgrab"] - 1.0, t["t4"] + 0.5, 0.3, 0.3))
        hand = 0.0
        tgt = None
        for (lab, dur) in (("pat", 2.0),):
            k = win(tau, t[lab] + 0.2, t[lab] + 0.2 + dur, 0.25, 0.25)
            if k > hand:
                hand, tgt = k, (NB[0] + 30, NB[1] - NB_R - 90)
        k = win(tau, t["nbbald"] + 1.5, t["nbbald"] + 2.4, 0.25, 0.25)       # il tâte son crâne chauve
        if k > hand:
            hand, tgt = k, (NB[0] + 20, NB[1] - NB_R - 10)
        k = win(tau, t["nbgrab"] - 0.6, t["nbgrab"] + 0.1, 0.3, 0.2)        # il veut reprendre l'afro
        if k > hand:
            hand, tgt = k, (CX - 170, SPOT["seat"][1] - 200)
        for lab in ("t3", "t4", "t7"):                                        # il essaie d'attraper les touffes
            k = win(tau, t[lab] + 0.1, t[lab] + 0.6, 0.15, 0.3)
            if k > hand:
                hand, tgt = k, (NB[0] + 110, NB[1] - 260)
        jl = 0.0
        for th in (t["pile"], t["patH"], t["steal"]):
            u = tau - th
            if 0 <= u <= 0.3:
                jl = max(jl, 22 * math.sin(math.pi * u / 0.3))
        return paper, turn, hand, tgt, jl

    def nb_head_hair(self, tau):
        """Ce qui est posé sur la tête du voisin hors du gag du vol : le tas, puis ce qu'il rattrape."""
        if tau < T["steal"]:
            return [(x, y, 21 + 5 * ((k * 7) % 5) / 4, (k * 0.37) % 1, k) for k, (x, y) in enumerate(PILE[:pile_count(tau)])]
        out = []
        for p in BPARTS:
            if p["to"] == "nb" and p["t0"] + p["dur"] <= tau:
                out.append((p["slot"][0], p["slot"][1], 24.0, 0.5, 0))
        return out

    def draw_neighbor(self, dr, tau, S, bpos, layer):
        paper, turn, hand, tgt, jl = self.nb_state(tau)
        hx, hy = NB[0], NB[1] + jl * 0.4
        if layer == "back":
            rect(dr, NB[0] - 130, 980, NB[0] + 130, 1330, SEAT_D, S, r=36)
            rect(dr, NB[0] - 22, 1330, NB[0] + 22, 1640, CHROME, S)
            ell(dr, NB[0], 1660, 160, 22, CHROME, S)
            rect(dr, NB[0] - 145, 1310, NB[0] + 145, 1370, SEAT, S, r=12)
            dr.polygon(P([(hx - 64, hy + 64), (hx + 64, hy + 64), (hx + 145, 1322), (hx - 145, 1322)], S), fill=NCAPE)
            for k in range(4):
                x = hx - 104 + 70 * k
                dr.line(P([(hx + (x - hx) * 0.35, hy + 84), (x, 1315)], S), fill=NCAPE_D, width=max(1, int(4 * S)))
            rect(dr, hx - 26, hy + 30, hx + 26, hy + 72, NSKIN_D, S)
            ell(dr, hx - 64, hy + 6, 15, 21, NSKIN_D, S)
            ell(dr, hx + 64, hy + 6, 15, 21, NSKIN_D, S)
            ell(dr, hx, hy, NB_R, NB_R, NSKIN, S)
            if turn > 0.1:
                ell(dr, hx + NB_R * 0.95 * turn, hy + 10, 15 * turn, 13, NSKIN, S)
            ell(dr, hx - 22, hy - 40, 22, 10, NSKIN_L, S)                # crâne chauve, qui brille
            if not (T["pile"] - 0.05 <= tau < T["steal"] + 0.02):
                pts = []
                for (x, y, r, s, k) in self.nb_head_hair(tau):
                    pop = 1.0
                    for p in PARTS:
                        pass
                    pts.append((x, y + jl * 0.4, r, s))
                # la touffe qui vient d'atterrir gonfle un instant (le « plop »)
                n = pile_count(tau)
                if tau < T["steal"] and n:
                    last = [p for p in PARTS if p["t0"] + p["dur"] <= tau]
                    if last and tau - (last[-1]["t0"] + last[-1]["dur"]) < 0.2:
                        k = 1 + 0.5 * (1 - (tau - (last[-1]["t0"] + last[-1]["dur"])) / 0.2)
                        pts = [(x, y, r * (k if i >= len(pts) - 6 else 1.0), s) for i, (x, y, r, s) in enumerate(pts)]
                cloud(dr, pts, S)
            return
        y0 = lerp(1020.0, 1260.0, paper) + jl * 0.3
        x0, x1 = NB[0] - 145, NB[0] + 145
        h = lerp(205.0, 70.0, paper)
        rect(dr, x0, y0, x1, y0 + h, PAPER, S, r=4)
        dr.line([NB[0] * S, y0 * S, NB[0] * S, (y0 + h) * S], fill=PAPER_D, width=max(1, int(3 * S)))
        rect(dr, x0 + 16, y0 + 14, x0 + 124, min(y0 + h - 6, y0 + 40), (60, 60, 66), S)
        for k in range(int(h // 24) - 1):
            yy = y0 + 56 + k * 22
            if yy > y0 + h - 8:
                break
            for (a, b) in ((x0 + 16, x0 + 128), (x1 - 128, x1 - 16)):
                dr.line([a * S, yy * S, (b - 12 * (k % 3)) * S, yy * S], fill=PAPER_D, width=max(1, int(5 * S)))
        hl, hr = (x0, y0 + h * 0.5), (x1, y0 + h * 0.5)
        if hand > 0 and tgt is not None:
            el, hr2 = arm_ik((hx + 50, hy + 90), lerp2(hr, tgt, hand), 120.0, 130.0, bend=1.0)
            capsule(dr, (hx + 50, hy + 90), el, 15, NCAPE, S)
            capsule(dr, el, hr2, 14, NCAPE, S)
            hr = hr2
        for q in (hl, hr):
            ell(dr, q[0], q[1], 23, 23, NSKIN, S)

    def draw_pile(self, dr, tau, S, bpos, part):
        _p, _t, _h, _tg, jl = self.nb_state(tau)
        bx, by = bpos
        pts = []
        for k, (x, y) in enumerate(PILE[:pile_count(tau)]):
            front = y > by + 0.45 * R and abs(x - bx) < R * 1.2
            if (part == "front") != front:
                continue
            pts.append((x, y + jl * 0.4, 21 + 5 * ((k * 7) % 5) / 4, (k * 0.37) % 1))
        cloud(dr, pts, S)

    # -------- le barbier
    def draw_barber(self, dr, tau, S, body):
        t = T
        bx = self.bx(tau)
        jl = jolt(tau)
        lift = self.barber_lift(tau) + 30 * jl
        lean = math.radians(self.lean(tau))
        tk = talking(tau)
        bob = 6 * math.sin(tau * 40) if tk is not None else 0.0
        hip = (bx, 1240.0 - lift)

        def B(u, v):
            return (hip[0] + v * math.cos(lean) + u * math.sin(lean), hip[1] - u * math.cos(lean) + v * math.sin(lean))
        shN, shF = B(350, -66), B(350, 62)
        head = B(442 + 8 * jl, -2)
        head = (head[0], head[1] + bob)
        if body:
            dangle = clamp01((lift - 40) / 120)
            for sx in (-1, 1):
                foot = (hip[0] + sx * 40 + sx * 30 * dangle * math.sin(tau * 18), min(FLOOR_Y - 8, hip[1] + 440))
                capsule(dr, (hip[0] + sx * 34, hip[1]), foot, 22, (44, 46, 58), S)
                ell(dr, foot[0] + 10, foot[1] + 4, 34, 14, (24, 24, 30), S)
            pts = [B(-30, -98), B(-30, 98), B(350, 80), B(370, 0), B(350, -80)]
            dr.polygon(P(pts, S), fill=COAT)
            for k in range(3):
                q = B(60 + 85 * k, -16)
                ell(dr, q[0], q[1], 8, 8, COAT_D, S)
            capsule(dr, B(370, -2), (head[0], head[1] + 34), 24, BSKIN, S)
            hx, hy = head
            ell(dr, hx, hy, BHEAD_R, BHEAD_R, BSKIN, S)
            ell(dr, hx - BHEAD_R * 0.97, hy + 12, 16, 15, BSKIN, S)
            if tau < t["cap_off"]:
                self.draw_cap(dr, hx, hy, 0.0, S)
            else:
                u = tau - t["cap_off"]
                if u < 1.2:
                    q = (hx - 200 * u, hy - 320 * u + 900 * u * u)
                    if q[1] < FLOOR_Y - 20:
                        self.draw_cap(dr, q[0], q[1] + 40, -4 * u, S)
                else:
                    self.draw_cap(dr, 600.0, FLOOR_Y - 30, -2.4, S)
                ell(dr, hx - 24, hy - 50, 24, 11, BSKIN_L, S)
            self.draw_barber_hair(dr, tau, S, hx, hy)
            self._head = head
            return
        c, o = self.hand_targets(tau, bx, head, shN, shF, jl)
        elN, c = arm_ik(shN, c, bend=1.0)
        elF, o = arm_ik(shF, o, bend=-1.0)
        for (s, el, hnd) in ((shF, elF, o), (shN, elN, c)):
            capsule(dr, s, el, 23, COAT_D, S)
            capsule(dr, el, hnd, 21, COAT, S)
            ell(dr, hnd[0], hnd[1], 26, 26, BSKIN, S)
        if t["comb0"] - 0.1 <= tau <= t["d5b"] + 0.3 or t["baldbarber"] + 0.8 <= tau <= t["ant"] + 0.2:
            rect(dr, o[0] - 10, o[1] - 66, o[0] + 10, o[1] + 8, (40, 40, 48), S, r=3)
        if tau >= t["mirror"]:
            self.draw_mirror(dr, tau, S, o)
        if tk is not None and LINES_TAU[1][0] <= tau:      # « Perfect! » : pouce levé de la main libre
            pass
        self.draw_clippers(dr, tau, S, c, jl)

    def draw_barber_hair(self, dr, tau, S, hx, hy):
        pts = []
        for p in BPARTS:
            if p["to"] != "barber" or p["t0"] + p["dur"] > tau:
                continue
            sx, sy = p["slot"]
            x, y, r, s = HAIR2_ALL[p["i"]]
            if tau >= STRIPE_T and abs(sx - 10) < 30 and sy < -BHEAD_R + 20:      # sa propre raie
                continue
            pts.append((hx + sx, hy + sy, r * 0.82, s))
        cloud(dr, pts, S)

    def draw_cap(self, dr, x, y, a, S):
        pts = [(-80, -20), (-76, -64), (-34, -94), (34, -94), (76, -64), (80, -20)]
        vis = [(-80, -20), (-160, -12), (-160, 4), (-80, 0)]
        for poly_, col in ((pts, CAP), (vis, CAP_D)):
            q = [rot(p, a) for p in poly_]
            dr.polygon(P([(x + px, y + py) for (px, py) in q], S), fill=col)

    def hand_targets(self, tau, bx, head, shN, shF, jl):
        t = T
        bpos = PLAN.pos(tau)
        c = (bpos[0] + 190 + 12 * math.sin(tau * 9), bpos[1] - 170 + 10 * math.cos(tau * 7))
        o = (bx + 40, 1080.0)
        for (th, g, _x, _y, k) in PLAN.hits:
            u = tau - th
            if 0 <= u <= 0.26 and k == "H" and th < t["stolen"]:
                hb = PLAN.pos(th)
                c = lerp2((hb[0] + 200, hb[1] - 230), (hb[0] - 170, hb[1] - 190), smooth(u / 0.22))
        c = (c[0], c[1] - 40 * jl)
        k = win(tau, t["hold"], t["lift_end"], 0.3, 0.3)
        if k > 0:
            o = lerp2(o, (bpos[0] + 30, bpos[1] - 280), k)
        k = win(tau, t["hug"] + 0.3, t["d9"], 0.3, 0.05)
        if k > 0:
            c = lerp2(c, (bpos[0] - R - 10, bpos[1] + 20), k)
            o = lerp2(o, (bpos[0] + R + 10, bpos[1] + 20), k)
        if t["comb0"] <= tau <= t["d5b"]:
            u = (tau - t["comb0"]) / max(0.1, t["d5b"] - t["comb0"])
            a = math.radians(-170 + 140 * smooth((u * 2.5) % 1.0))
            o = (bpos[0] + (R + 90) * math.cos(a), bpos[1] - 40 + (R + 90) * math.sin(a))
        k = win(tau, t["cush_in"], t["cush_land"], 0.15, 0.2)
        if k > 0:
            o = lerp2(o, (bx - 60, 1000.0 - 120 * smooth((tau - t["cush_in"]) / 0.3)), k)
        k = win(tau, t["easy"] - 0.1, t["cushbig"] - 0.4, 0.3, 0.2)
        if k > 0:
            c = lerp2(c, (bpos[0] + 60 + 40 * math.sin(tau * 3), bpos[1] - 280), k)
            o = lerp2(o, (bpos[0] + 200, bpos[1] - 120), k)
            tk = talking(tau)
            if tk is not None:                          # « Easy... easy. » : la main libre fait « doucement »
                o = (o[0] + 30, o[1] - 40 + 30 * math.sin(tau * 9))
        k = win(tau, t["yank"] - 0.2, t["yank"] + 0.15, 0.15, 0.25)
        if k > 0:
            o = lerp2(o, (CX + 150, CUSH_TOP + 20), k)
        k = win(tau, t["baldbarber"] + 0.1, t["baldbarber"] + 0.9, 0.25, 0.25)
        if k > 0:                                       # il découvre qu'il est chauve : main sur le crâne
            o = lerp2(o, (head[0] + 20, head[1] - BHEAD_R - 10), k)
        if t["baldbarber"] + 1.0 <= tau <= t["ant"]:
            u = smooth((tau - t["baldbarber"] - 1.0) / 0.6)
            o = lerp2((bpos[0] + 180, bpos[1] - 150), (bpos[0] + 40, bpos[1] - R - 150), u)
        if t["ant"] <= tau <= t["ant"] + 0.3:
            o = lerp2((bpos[0] + 30, bpos[1] - R - 120), (bpos[0] + 80, bpos[1] - R - 330), smooth((tau - t["ant"]) / 0.2))
        if t["snip"] - 0.3 <= tau <= t["snip"] + 0.2:
            c = lerp2(c, (bpos[0] - 20, bpos[1] - R - 130), smooth((tau - t["snip"] + 0.3) / 0.3))
        k = win(tau, t["touch"] + 0.1, t["touch"] + 1.0, 0.25, 0.25)
        if k > 0:                                       # il sent quelque chose sur son crâne
            o = lerp2(o, (head[0] + 30, head[1] - BHEAD_R - 20), k)
        k = win(tau, t["shimmy"] + 0.05, t["shimmy"] + 1.0, 0.2, 0.2)
        if k > 0:                                       # il est ravi : bras en l'air
            o = lerp2(o, (head[0] + 120, head[1] - 140 + 20 * math.sin(tau * 16)), k)
        if tau >= t["mirror"]:
            u = smooth((tau - t["mirror"]) / 0.5)
            o = lerp2(o, (715.0, 1225.0), u)
            if t["perfect"] <= tau <= t["perfect"] + 0.8:     # « Perfect! » : la tondeuse levée, pouce en l'air
                c = (head[0] - 150, head[1] - 60 - 40 * math.sin((tau - t["perfect"]) * 8))
        if t["last"] <= tau <= t["last"] + 0.35:
            u = smooth((tau - t["last"]) / 0.25)
            c = lerp2((head[0] - 90, head[1] - 110), (head[0] + 90, head[1] - 110), u)
        return c, o

    def draw_mirror(self, dr, tau, S, hnd):
        """Grand miroir à main : le reflet de Bounce y fait 220 px."""
        x, y = hnd[0], hnd[1] - 150
        mw, mh = 160.0, 205.0
        rect(dr, hnd[0] - 14, hnd[1] - 40, hnd[0] + 14, hnd[1] + 60, FRAME, S, r=6)
        ell(dr, x, y, mw, mh, FRAME, S)
        ell(dr, x, y, mw - 14, mh - 14, MIRROR, S)
        pos = base.HERO["pos"]
        e = base.HERO["expr"]
        rr = 92.0
        k = rr / R
        bp = PLAN.pos(tau)
        oy = (bp[1] - SPOT["seat"][1]) * k
        base.HERO["expr"] = self.expr_at(tau)
        base.ball(dr, x * S, (y + 40 + oy) * S, rr * S)
        base.HERO["pos"] = pos
        base.HERO["expr"] = e
        hair = self.hair_now(tau)
        cloud(dr, [(x - hx * k, y + 40 + oy + hy * k, max(7.0, r * k), s) for (hx, hy, r, s) in hair], S)
        dr.line([(x + 70) * S, (y - 140) * S, (x + 110) * S, (y - 80) * S], fill=(240, 248, 255), width=max(1, int(7 * S)))

    def draw_clippers(self, dr, tau, S, c, jl):
        t0 = T["slow"]
        u = tau - t0
        x, y = c
        ang = -0.4 + 0.5 * jl * math.sin(tau * 30)
        if 0.03 <= u <= 0.95:
            k = clamp01((u - 0.03) / 0.92)
            bp = PLAN.pos(t0)
            hd = getattr(self, "_head", (BX0, 760.0))
            path = [c, (bp[0] + 120, bp[1] - 330), (bp[0] - 40, bp[1] - 380), (hd[0] - 160, hd[1] - 120),
                    (hd[0] - 20, hd[1] - 100), (hd[0] + 60, hd[1] - 40), c]
            n = len(path) - 1
            i = min(n - 1, int(k * n))
            f = k * n - i
            x, y = lerp2(path[i], path[i + 1], smooth(f))
            ang = k * 6 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(a, b):
            return (x + a * ca - b * sa, y + a * sa + b * ca)
        dr.polygon(P([Q(-28, -64), Q(28, -64), Q(32, 56), Q(-32, 56)], S), fill=CLIP_C)
        dr.polygon(P([Q(-30, -64), Q(30, -64), Q(30, -80), Q(-30, -80)], S), fill=(205, 208, 218))
        for kk in range(6):
            q = Q(-25 + 10 * kk, -82)
            ell(dr, q[0], q[1], 3, 6, (205, 208, 218), S)
        if 0.03 <= u <= 0.95 or jl > 0.4:
            for kk in range(3):
                q0 = Q(-42, -26 + 26 * kk)
                q1 = Q(-74, -32 + 26 * kk)
                dr.line(P([q0, q1], S), fill=(225, 225, 235), width=max(1, int(5 * S)))

    # -------- ce qui vole
    def draw_particles(self, dr, tau, S):
        pts = []
        for p in PARTS:
            u = (tau - p["t0"]) / p["dur"]
            if u < 0 or u >= 1:
                continue
            kind, i = p["src"]
            if kind == "h1":
                hb = PLAN.pos(p["t0"])
                st = (hb[0] + HAIR1[i][0], hb[1] + HAIR1[i][1])
            else:
                hb = PLAN.pos(T["snip"])
                ax, ay, _r = ant_curve(ant_angle(T["snip"]), i, len(REMAIN))
                st = (hb[0] + ax, hb[1] + ay)
            en = p["slot"]
            pts.append((lerp(st[0], en[0], u), lerp(st[1], en[1], u) - 230 * math.sin(math.pi * u), p["r"] * 0.9, p["s"]))
        hd = getattr(self, "_head", (BX0, 700.0))
        for p in BPARTS:
            u = (tau - p["t0"]) / p["dur"]
            if u < 0 or u >= 1:
                continue
            x, y, r, s = HAIR2_ALL[p["i"]]
            hb = PLAN.pos(p["t0"])
            st = (hb[0] + x, hb[1] + y)
            en = (hd[0] + p["slot"][0], hd[1] + p["slot"][1]) if p["to"] == "barber" else p["slot"]
            pts.append((lerp(st[0], en[0], u), lerp(st[1], en[1], u) - 260 * math.sin(math.pi * u), r * 0.85, s))
        u = tau - STRIPE_T                               # la raie dans sa nouvelle coiffure : ça tombe
        if 0 <= u <= 1.0:
            for p in BPARTS:
                sx, sy = p["slot"]
                if p["to"] == "barber" and abs(sx - 10) < 30 and sy < -BHEAD_R + 20:
                    pts.append((hd[0] + sx + 90 * u, hd[1] + sy - 200 * u + 1200 * u * u, 26.0, 0.5))
        cloud(dr, pts, S)


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


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 84, "hook_width": 0.70, "hook_speed": 1.0, "hook_max_s": 1.0,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
LINE_GAIN = {"easy": 0.95, "perfect": 1.05}
REACT_TAU = T["issue"] + 0.75


def exact_events(sim):
    return [(unwarp(t), "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(PLAN.hits) if t >= 0]


def render_audio(sim, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(exact_events(sim), total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        for (t0, kind, _d, tag) in words:
            g = sim.hit_gain(t0)
            gg = max(0.1, min(1.4, g)) ** 0.7 * 0.92
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
        react = base.hero_word(cfg["hero_lose"], cfg)
        if react is not None:
            ak.add(buf, react, unwarp(REACT_TAU), gain=0.95)
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


def plan_report():
    hits = [unwarp(h[0]) for h in PLAN.hits if h[0] >= 0]
    iv = np.diff(hits)
    run = best = 1
    for i in range(1, len(iv)):
        run = run + 1 if abs(iv[i] - iv[i - 1]) <= 0.1 * iv[i - 1] else 1
        best = max(best, run)
    tops = []
    for k in range(0, int(END * 30)):
        tau = k / 30
        x, y = PLAN.pos(tau)
        hair = Sim.hair_now(None, tau)
        top = min([y - R] + [y + hy - r for (hx, hy, r, s) in hair])
        tops.append((round(top), round(unwarp(tau), 2)))
    from collections import Counter
    return {"hits": len(hits), "cv": round(float(np.std(iv) / np.mean(iv)), 3), "iv_min": round(float(iv.min()), 2),
            "iv_max": round(float(iv.max()), 2), "run": best, "remain1": len(REMAIN), "keep2": len(KEEP2),
            "cuts1": sorted(Counter(CUT1_T).items(), key=lambda x: (x[0] is None, x[0] or 0)),
            "highest": sorted(tops)[:3], "end_real": round(unwarp(END), 2), "issue_real": round(unwarp(ISSUE), 2),
            "first_hit": round(hits[0], 2)}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "hits": len(ev), "plan": plan_report(),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [round(e[0], 3) for e in ev if round(e[0], 3) not in said]
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
