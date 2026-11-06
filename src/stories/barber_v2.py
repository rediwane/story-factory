"""
Prototype « barber » v2 : Bounce est le client. Il est assis dans le fauteuil du barbier avec une tignasse
énorme et il ne tient pas en place : chaque rebond sur le fauteuil fait rater la tondeuse, et c'est SA coupe
qui part, touffe par touffe, sur la tête du voisin caché derrière son journal. Le barbier le tient (il
décolle avec lui), le serre (il s'envole), lui glisse un coussin (faux arrêt : « Easy... easy. »), mais
Bounce rebondit sur l'accoudoir : la tondeuse s'envole au ralenti, rase le sommet et fait tomber la casquette
du barbier, chauve. La mèche rabattue devient une antenne, qui finit sur le voisin. Bounce plonge alors dans
le tas du voisin et en ressort avec une tignasse plus grosse qu'au départ. Le barbier la rabote à plat, rebond
après rebond, jusqu'à une barbe et une moustache. Au miroir : « Perfect. », Bounce adore, saute de joie, et
sa barbe s'envole sur le crâne du barbier. Dernier « Bounce » : le barbier se rase sa nouvelle perruque, et
il ne reste à Bounce qu'une moustache, sur le sommet du crâne.

Le temps du récit (tau) est étiré par un ralenti ; l'audio suit les instants exacts des contacts.

    python3 src/stories/barber_v2.py configs/<name>.json [--simulate]
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

HOOK_T = 0.72
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
DY = 70.0                    # toute la scène est dessinée 70 px plus bas que ses coordonnées
G = 2600.0
R = 130.0


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
        k = smooth((t - t0) / max(1e-6, t1 - t0))
        if isinstance(v0, tuple):
            return tuple(lerp(a, b, k) for a, b in zip(v0, v1))
        return lerp(v0, v1, k)


def win(t, a, b, fi=0.15, fo=0.15):
    if t < a - fi or t > b + fo:
        return 0.0
    return smooth((t - (a - fi)) / max(1e-6, fi)) * smooth(((b + fo) - t) / max(1e-6, fo))


def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


# ------------------------------------------------------------------ ralenti (la tondeuse s'envole)
SLOW_A = 24.2
SLOW_L = 2.0
SLOW_F = 0.33


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


# ------------------------------------------------------------------ décor (écran 1080×1920)
FLOOR_Y = 1560.0
SEAT_Y = 1230.0                      # dessus de l'assise (dur : il dit son nom)
CX = 520.0                           # axe du fauteuil de Bounce
CUSH_TOP = 1172.0
ARM_Y = 1150.0
NB = (195.0, 935.0)                  # tête du voisin
NB_R = 62.0
BX0 = 800.0                          # le barbier, au repos (son corps reste à gauche de x = 900)

WALL = (18, 32, 38)
WALL_L = (24, 42, 48)
TILE_A = (34, 34, 40)
TILE_B = (54, 54, 62)
HAIR = (112, 72, 48)
HAIR_L = (146, 98, 66)
HAIR_D = (62, 38, 26)
NSKIN = (196, 138, 104)
NSKIN_D = (160, 104, 76)
NCAPE = (92, 100, 118)
NCAPE_D = (70, 76, 92)
COAT = (226, 230, 236)
COAT_D = (178, 184, 196)
BSKIN = (166, 112, 86)
BSKIN_L = (196, 146, 120)
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
MIRROR = (180, 210, 225)
FRAME = (200, 160, 80)

SPOT = {"seat": (CX, SEAT_Y - R), "cush": (CX, CUSH_TOP - R + 26), "arm": (398.0, ARM_Y - R + 4),
        "nb": (205.0, 812.0)}
HARD = {"seat", "arm", "nbH"}

# ------------------------------------------------------------------ le plan (temps du récit)
# r = il se tasse sur l'assise et gigote (repos, muet) ; cr = pareil sur le coussin ; nbr = dans le tas du voisin
_P = [
    (0.02, "seat", 1.1), (0.35, "r", 0), (2.30, "seat", 1.0), (3.20, "seat", 0.95), (3.55, "r", 0),
    (4.60, "seat", 0.9), (4.95, "r", 0), (5.90, "seat", 1.2), (6.85, "seat", 1.0), (7.75, "seat", 0.95), (8.10, "r", 0), (9.40, "seat", 1.05),
    (9.75, "r", 0),
    (11.30, "seat", 1.1), (12.30, "seat", 1.2), (13.35, "seat", 1.4), (13.70, "r", 0), (15.10, "seat", 1.0),
    (16.00, "seat", 0.95), (16.35, "r", 0), (17.50, "seat", 1.0), (17.85, "r", 0), (19.30, "seat", 1.05),
    (20.25, "cush", 0), (20.95, "cush", 0), (21.40, "cush", 0), (21.75, "cr", 0), (23.60, "cush", 0),
    (24.15, "arm", 1.4), (24.70, "cush", 0), (25.75, "seat", 1.0),
    (26.10, "r", 0), (27.00, "seat", 0.9), (27.35, "r", 0), (28.60, "seat", 1.15), (29.55, "seat", 0.95),
    (29.90, "r", 0), (31.10, "seat", 1.0), (32.00, "seat", 0.95), (32.35, "r", 0), (33.50, "seat", 1.05),
    (33.85, "r", 0), (35.20, "seat", 1.1),
    (36.20, "seat", 1.0), (37.20, "nb", 0), (37.60, "nbr", 0), (38.60, "nbH", 0.85), (38.95, "nbr", 0),
    (40.40, "nbH", 0.95), (40.75, "nbr", 0), (42.00, "nbH", 1.0), (43.00, "seat", 1.15), (43.95, "seat", 1.0),
    (44.30, "r", 0),
    (45.60, "seat", 1.05), (46.50, "seat", 1.0), (46.85, "r", 0), (48.30, "seat", 1.05), (49.20, "seat", 0.95),
    (49.55, "r", 0), (50.90, "seat", 1.05), (51.80, "seat", 1.15), (52.15, "r", 0),
    (55.10, "seat", 0.9), (56.05, "seat", 1.3), (56.40, "r", 0), (58.50, "seat", 1.2), (59.40, "r", 0),
]
END = 58.5 + 1.35
T = dict(hold=3.7, hold_end=5.9, lift_end=6.85, hug=9.8, hug_lift=11.3, thrown=13.35, presque=16.4, face_tuft=17.5,
         presque_end=18.45, cush_in=19.35, cush_land=20.2, easy=21.45, slow_hit=24.15, crown=24.3, cap_off=24.45,
         yank=24.9, comb0=26.3, comb1=28.3, ant=28.6, wilt=34.0, snip=35.2, launch=36.2, pile_in=37.2,
         pat=37.4, nb_drop=40.4, leave=42.0, back=43.0, level=44.4, beard=51.8, mirror=52.9, perfect=53.6,
         love=54.4, proud1=55.1, issue=56.05, admire=56.8, last=58.5)
ISSUE = T["issue"]
LINES_TAU = [(T["easy"], "Easy... easy.", "easy", 1.09), (T["perfect"], "Perfect.", "perfect", 0.67)]


def talking(tau):
    for (t0, _txt, _k, d) in LINES_TAU:
        if t0 <= tau <= t0 + d:
            return True
    return False


class Plan:
    def __init__(self):
        self.cs = []
        for (t, k, g) in _P:
            base_k = {"r": "seat", "cr": "cush", "nbr": "nb", "nbH": "nb"}.get(k, k)
            x, y = SPOT[base_k]
            if k in ("r", "cr", "nbr"):
                y += 6
            self.cs.append({"t": t, "k": k, "x": x, "y": y, "g": g, "soft": k not in HARD,
                            "axis": "y"})
        self.ts = [c["t"] for c in self.cs]
        self.start = {"t": -0.34, "k": "start", "x": CX, "y": SPOT["seat"][1] - 140}
        self.after = {"t": END + 0.1, "k": "end", "x": CX, "y": SPOT["seat"][1] - 20}
        self.hits = [(c["t"], c["g"], c["x"], c["y"], c["k"]) for c in self.cs if not c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.cs[i - 1]
        b = self.after if i >= len(self.cs) else self.cs[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        if a["k"] in ("r", "cr", "nbr"):
            hop = 0.42 if abs(b["x"] - a["x"]) < 30 else 0.95
            if t < b["t"] - hop:
                f = 2.6 if a["k"] == "r" else 2.0
                return a["x"] + 5 * math.sin(t * 17.0), a["y"] - 4 * abs(math.sin(t * f * math.pi))
            a = {"t": b["t"] - hop, "x": a["x"] + 5 * math.sin((b["t"] - hop) * 17.0), "y": a["y"]}
        Tt = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / Tt
        vy = (b["y"] - a["y"]) / Tt - 0.5 * G * Tt
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def rise(self, t):
        """Hauteur de Bounce au-dessus de l'assise (pour soulever le barbier qui le tient)."""
        return max(0.0, SPOT["seat"][1] - self.pos(t)[1])

    def squash(self, t):
        sx = sy = 1.0
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.cs[i:i + 4]:
            u = t - c["t"]
            if c["k"] in ("r", "cr", "nbr"):
                continue
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


# ------------------------------------------------------------------ la tignasse de Bounce (accessoire posé sur lui)
_rng = np.random.default_rng(23)


def _cloud(cx, cy, rx, ry, n, rmin, rmax, gap, seed):
    rr = np.random.default_rng(seed)
    pts, tries = [], 0
    while len(pts) < n and tries < 40000:
        tries += 1
        x, y = rr.uniform(-1, 1), rr.uniform(-1, 1)
        if x * x + y * y > 1:
            continue
        px, py = cx + x * rx, cy + y * ry
        if px * px + py * py < (0.98 * R) ** 2 and py > -0.74 * R:      # le visage reste visible
            continue
        if py > 0.35 * R and abs(px) < 1.25 * R:
            continue
        if any((px - q[0]) ** 2 + (py - q[1]) ** 2 < gap * gap for q in pts):
            continue
        pts.append((px, py, rr.uniform(rmin, rmax), rr.uniform(0, 1)))
    return pts


HAIR1 = _cloud(0.0, -125.0, 200.0, 170.0, 120, 30, 40, 21, 23)
# la tignasse reprise au voisin : plus grosse, avec une barbe et une moustache
HAIR2 = _cloud(0.0, -135.0, 225.0, 185.0, 150, 30, 40, 21, 29)
BEARD = []
for k in range(15):
    a = math.radians(12 + 156 * k / 14)
    BEARD.append((math.cos(a) * R * 1.02, math.sin(a) * R * 1.02 + 6, 30.0 + 4 * math.sin(k), 0.3 + 0.04 * k))
for k in range(9):
    a = math.radians(30 + 120 * k / 8)
    BEARD.append((math.cos(a) * R * 1.32, math.sin(a) * R * 1.26 + 4, 28.0, 0.6))
MUST = [(-46.0, 36.0, 18.0, 0.7), (-24.0, 30.0, 19.0, 0.5), (0.0, 33.0, 19.0, 0.4), (24.0, 30.0, 19.0, 0.5),
        (46.0, 36.0, 18.0, 0.7)]

# coupes de la tignasse 1 : (t, règle) en coordonnées relatives à Bounce
CUTS1 = [
    (0.02, ("side", 1, 8)), (2.30, ("near", (-130, -250), 8)), (3.20, ("near", (80, -270), 6)),
    (5.90, ("xnear", 0.0, 10)), (6.85, ("near", (160, -110), 5)), (7.75, ("near", (-190, -90), 6)),
    (9.40, ("near", (70, -170), 5)), (11.30, ("side", -1, 8)), (12.30, ("near", (-90, -190), 6)),
    (13.35, ("side", 1, 20)), (15.10, ("near", (-140, -60), 4)), (16.00, ("near", (-40, -270), 4)),
    (17.50, ("near", (-120, -250), 3)), (19.30, ("near", (-150, -160), 3)), (24.30, ("near", (-50, -180), 6)),
    (25.75, ("near", (-110, -110), 2)),
]
# la tignasse 2 (après le voisin) : rabotée à plat, rebond après rebond
CUTS2 = [(45.60, -240.0), (46.50, -190.0), (48.30, -145.0), (49.20, -100.0), (50.90, -50.0), (51.80, 8.0)]


def _seg_d(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    u = clamp01(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy + 1e-9))
    return math.hypot(px - (ax + u * vx), py - (ay + u * vy))


def _rule_hit(rule, x, y):
    k = rule[0]
    if k == "x>":
        return x > rule[1]
    if k == "x<":
        return x < rule[1]
    if k == "seg":
        return _seg_d((x, y), rule[1], rule[2]) < rule[3]
    if k == "band":
        return rule[1] < x < rule[2] and y < rule[3]
    if k == "circ":
        return math.hypot(x - rule[1][0], y - rule[1][1]) < rule[2]
    return False


CUT1_T = [None] * len(HAIR1)
for (t, rule) in CUTS1:
    alive = [i for i in range(len(HAIR1)) if CUT1_T[i] is None]
    kind, a, n = rule
    if kind == "side":
        key = lambda i: -a * HAIR1[i][0]
    elif kind == "xnear":
        key = lambda i: abs(HAIR1[i][0] - a) + (0 if HAIR1[i][1] < -90 else 999)
    else:
        key = lambda i: math.hypot(HAIR1[i][0] - a[0], HAIR1[i][1] - a[1])
    for i in sorted(alive, key=key)[:n]:
        CUT1_T[i] = t
REMAIN = [i for i in range(len(HAIR1)) if CUT1_T[i] is None]
HAIR2_ALL = HAIR2 + BEARD + MUST
NB2 = len(HAIR2)
CUT2_T = [None] * len(HAIR2_ALL)
for (t, yl) in CUTS2:
    for i, (x, y, r, s) in enumerate(HAIR2_ALL):
        if CUT2_T[i] is None and i < NB2 and y < yl:
            CUT2_T[i] = t
KEEP2 = [i for i in range(len(HAIR2_ALL)) if CUT2_T[i] is None]       # la barbe : elle s'envole à l'issue


def comb_target(j, n):
    a = math.radians(-172 + 164 * j / max(1, n - 1))
    rr = R + 16 + 6 * math.sin(j * 1.7)
    return (rr * math.cos(a), rr * math.sin(a), 22.0)


def ant_curve(ph, j, n, L=250.0):
    k = j / max(1, n - 1)
    x = y = 0.0
    for i in range(12):
        s0 = k * (i + 0.5) / 12
        th = ph * s0 ** 1.3
        x += math.sin(th) * L * k / 12
        y -= math.cos(th) * L * k / 12
    return (x + 6 * math.sin(j * 2.1), y - R + 4, 22.0 - 9 * k)


def ant_angle(tau):
    a = 0.0
    for th in (29.55, 31.1, 32.0, 33.5):
        u = tau - th
        if u >= 0:
            a += (0.3 + 0.12 * (th > 31)) * math.exp(-u / 0.5) * math.sin(u * 15)
    u = tau - T["ant"]
    if u >= 0:
        a += 0.25 * math.exp(-u / 0.4) * math.sin(u * 18)
    a += math.radians(-15) * smooth((tau - 33.5) / 0.3)
    a += math.radians(-185) * smooth((tau - T["wilt"]) / 1.1)
    return a


# ------------------------------------------------------------------ le tas du voisin (là où atterrit tout ce qui est coupé)
def _pile_slots():
    rr = np.random.default_rng(41)
    pts = []
    tries = 0
    while len(pts) < 140 and tries < 50000:
        tries += 1
        x, y = rr.uniform(-1, 1), rr.uniform(-1, 0.25)
        if x * x + y * y > 1:
            continue
        px, py = NB[0] + x * 180, NB[1] - NB_R + 14 + y * 175
        if any((px - q[0]) ** 2 + (py - q[1]) ** 2 < 20 * 20 for q in pts):
            continue
        pts.append((px, py))
    pts.sort(key=lambda p: (-(p[1]) + 0.25 * abs(p[0] - NB[0])))       # le tas monte du crâne vers le haut
    pts.reverse()
    pts.sort(key=lambda p: math.hypot(p[0] - NB[0], (p[1] - (NB[1] - NB_R)) * 1.3))
    return pts


PILE = _pile_slots()


def _particles():
    """Chaque touffe coupée vole vers le tas du voisin (la tondeuse balaie de droite à gauche)."""
    out = []
    events = []
    for i, (x, y, r, s) in enumerate(HAIR1):
        if CUT1_T[i] is not None:
            events.append((CUT1_T[i], x, y, r, s, "h1"))
    # l'antenne coupée : ses touffes aussi
    for j, i in enumerate(REMAIN):
        x, y, r, s = HAIR1[i]
        events.append((T["snip"] + 0.02 * j, None, j, 20.0, s, "ant"))
    events.sort(key=lambda e: e[0])
    for n, e in enumerate(events):
        slot = PILE[min(n, len(PILE) - 1)]
        out.append({"t0": e[0], "src": e, "slot": slot, "dur": 0.75 + 0.1 * (n % 3), "r": e[3], "s": e[4]})
    return out


PARTS = _particles()


def pile_count(tau):
    return sum(1 for p in PARTS if p["t0"] + p["dur"] <= tau)


# ------------------------------------------------------------------ dessin : primitives
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
        ell(dr, x, y, r, r, mix(HAIR, HAIR_L, 0.18 * s), S)
    for (x, y, r, s) in pts:
        if s > 0.45:
            ell(dr, x - r * 0.3, y - r * 0.32, r * 0.42, r * 0.22, mix(HAIR, HAIR_L, 0.55), S)


def arm_ik(sh, target, L1=165.0, L2=175.0, bend=1.0):
    """Bras à deux segments de longueur fixe : la main va vers la cible sans jamais s'allonger."""
    dx, dy = target[0] - sh[0], target[1] - sh[1]
    d = math.hypot(dx, dy)
    dmax = L1 + L2 - 4
    if d > dmax:
        target = (sh[0] + dx / d * dmax, sh[1] + dy / d * dmax)
        d = dmax
    d = max(d, 40.0)
    a = math.atan2(target[1] - sh[1], target[0] - sh[0])
    cosb = clamp01((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d) * 0.5 + 0.5) * 2 - 1
    b = math.acos(max(-1.0, min(1.0, cosb)))
    el = (sh[0] + L1 * math.cos(a + bend * b), sh[1] + L1 * math.sin(a + bend * b))
    return el, target


# ------------------------------------------------------------------ la scène
class Scene:
    def __init__(self):
        t = T
        # le barbier : position, hauteur (soulevé), inclinaison
        self.bx = KF(BX0, [(t["hold"] - 0.3, BX0), (t["hold"], 730.0), (t["lift_end"] + 0.2, 730.0),
                           (t["lift_end"] + 0.7, BX0), (t["hug"], BX0), (t["hug"] + 0.6, 600.0),
                           (t["thrown"], 600.0), (t["thrown"] + 0.35, 880.0), (t["thrown"] + 1.0, BX0),
                           (t["cush_in"] - 0.2, BX0), (t["cush_in"] + 0.3, 760.0), (t["cush_land"], 760.0),
                           (t["cush_land"] + 0.4, BX0), (t["mirror"] - 0.3, BX0), (t["mirror"] + 0.2, 830.0)])
        self.lean = KF(0.0, [(t["thrown"], 0.0), (t["thrown"] + 0.3, 14.0), (t["thrown"] + 1.4, 0.0),
                             (t["back"] + 0.1, 0.0), (t["back"] + 0.6, -14.0), (t["level"], -14.0),
                             (t["level"] + 0.4, 0.0)])
        self.cap_t = t["cap_off"]
        self.rings = [(h[0], h[1], h[2], h[3]) for h in PLAN.hits]

    def barber_lift(self, tau):
        t = T
        if t["hold_end"] - 0.05 <= tau <= t["lift_end"]:
            return 0.55 * PLAN.rise(tau)
        if t["hug_lift"] - 0.02 <= tau <= t["thrown"]:
            return 0.85 * PLAN.rise(tau)
        u = tau - t["thrown"]
        if 0 <= u <= 0.5:
            return 160 * math.sin(math.pi * u / 0.5) * (1 - u)
        return 0.0


def cushion_state(tau):
    """(x du centre, présent) : glissé sous lui (19,35), arraché et jeté (24,9)."""
    t = T
    if tau < t["cush_in"]:
        return None
    if tau < t["cush_land"]:
        u = smooth((tau - t["cush_in"]) / (t["cush_land"] - t["cush_in"]))
        return (lerp(850.0, CX, u), lerp(1080.0, CUSH_TOP + 30, u), 0.0)
    if tau < t["yank"]:
        return (CX, CUSH_TOP + 30, 0.0)
    u = tau - t["yank"]
    if u > 0.9:
        return None
    return (CX + 900 * u, CUSH_TOP + 30 - 500 * u + 800 * u * u, 5 * u)


class Sim:
    scene_top = 0.245

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_real = [unwarp(h[0]) for h in PLAN.hits]
        self.hi = 0
        self.lines = [(unwarp(tt), txt, key) for (tt, txt, key, _d) in LINES_TAU]
        self.replies = []

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

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        tau = warp(float(t))
        S = S * self.cfg["width"] / W
        out_img = dr._image
        layer = Image.new("RGB", out_img.size, WALL)
        dr = ImageDraw.Draw(layer)
        bpos = PLAN.pos(tau)
        self.draw_room(dr, tau, S)
        self.draw_neighbor(dr, tau, S, bpos, layer="back")
        self.draw_barber(dr, tau, S, body=True)
        self.draw_chair(dr, tau, S, bpos)
        self.draw_rings(dr, tau, S)
        in_pile = T["pile_in"] - 0.05 <= tau < T["leave"] + 0.02
        if in_pile:
            self.draw_pile(dr, tau, S, bpos, part="back")
        self.draw_bounce(dr, tau, S, bpos)
        self.draw_neighbor(dr, tau, S, bpos, layer="front")
        if in_pile:
            self.draw_pile(dr, tau, S, bpos, part="front")
        self.draw_barber(dr, tau, S, body=False)
        self.draw_particles(dr, tau, S)
        self.draw_flying(dr, tau, S)
        dy = int(DY * S)
        out_img.paste(layer.crop((0, 0, layer.width, layer.height - dy)), (0, dy))
        ImageDraw.Draw(out_img).rectangle([0, 0, out_img.width, dy], fill=WALL)
        if base.HERO["pos"] is not None:
            base.HERO["pos"] = (base.HERO["pos"][0], base.HERO["pos"][1] + dy)

    # -------- Bounce et ses cheveux
    def expr_at(self, tau):
        t = T
        for (a, b, e) in [(t["thrown"], t["thrown"] + 0.6, "shock"), (t["slow_hit"], t["slow_hit"] + 1.0, "shock"),
                          (t["back"], t["back"] + 1.3, "win"), (t["love"], t["issue"], "win"),
                          (t["issue"] + 0.3, 99.0, "lose")]:
            if a <= tau < b:
                return e
        for (th, g, _x, _y, _k) in PLAN.hits:
            if g >= 1.25 and 0 <= tau - th < 0.4:
                return "shock"
        return "calm"

    def hair_now(self, tau):
        """Les touffes posées sur Bounce, en coordonnées relatives (x, y, r, s)."""
        t = T
        out = []
        if tau < t["comb0"]:
            for i, (x, y, r, s) in enumerate(HAIR1):
                if CUT1_T[i] is None or tau < CUT1_T[i]:
                    out.append((x, y, r, s))
            return out
        if tau < t["snip"]:
            n = len(REMAIN)
            for j, i in enumerate(REMAIN):
                x, y, r, s = HAIR1[i]
                if tau < t["ant"]:
                    u = smooth((tau - t["comb0"] - 0.07 * j) / 1.2)
                    cx, cy, cr = comb_target(j, n)
                    # le sursaut de 27,0 : la mèche se décoiffe un instant
                    jit = 30 * math.exp(-max(0.0, tau - 27.0) / 0.3) * (tau >= 27.0)
                    out.append((lerp(x, cx, u), lerp(y, cy, u) - jit * (j % 2), lerp(r, cr, u), s))
                else:
                    u = smooth((tau - t["ant"]) / 0.16)
                    cx, cy, cr = comb_target(j, n)
                    ax, ay, ar = ant_curve(ant_angle(tau), j, n)
                    out.append((lerp(cx, ax, u), lerp(cy, ay, u), lerp(cr, ar, u), s))
            return out
        if tau < t["leave"]:
            return out
        if tau < t["issue"]:
            for i, (x, y, r, s) in enumerate(HAIR2_ALL):
                if CUT2_T[i] is None or tau < CUT2_T[i]:
                    wob = 0.0
                    if i >= NB2 and t["proud1"] <= tau < t["issue"]:     # la barbe ballotte : presque
                        wob = 16 * math.exp(-(tau - t["proud1"]) / 0.5) * math.sin((tau - t["proud1"]) * 14)
                    out.append((x + wob * 0.3, y + wob, r, s))
            return out
        if tau >= t["last"] + 0.55:
            # ce qui lui reste : la moustache, posée sur le sommet du crâne
            for (x, y, r, s) in MUST:
                out.append((x * 1.25, -R - 14 + 0.3 * (y - 33), r * 1.4, s))
        return out

    def draw_bounce(self, dr, tau, S, bpos):
        base.HERO["expr"] = self.expr_at(tau)
        bx, by = bpos
        sx, sy = PLAN.squash(tau)
        self.draw_ball(dr, bx, by, R * sx, R * sy, S)
        hair = self.hair_now(tau)
        cloud(dr, [(bx + x * sx, by + y * sy, r, s) for (x, y, r, s) in hair], S)

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
            x = 45 + k * 90
            rect(dr, x, 0, x + 10, FLOOR_Y, WALL_L, S)
        rect(dr, 0, 1300, W, 1312, (30, 52, 58), S)
        # étagère et flacons (en haut à droite, sous l'accroche)
        rect(dr, 700, 600, 1000, 614, (120, 90, 60), S)
        for (x, h, c) in ((730, 60, (90, 170, 210)), (780, 46, (210, 120, 70)), (830, 70, (140, 200, 110)),
                          (880, 40, (220, 200, 90)), (930, 56, (200, 110, 160))):
            rect(dr, x - 16, 600 - h, x + 16, 600, c, S, r=6)
            rect(dr, x - 6, 600 - h - 14, x + 6, 600 - h, (220, 220, 226), S)
        # sol en damier
        rect(dr, 0, FLOOR_Y, W, H, TILE_A, S)
        for row in range(10):
            y0 = FLOOR_Y + row * 44
            for col in range(13):
                if (row + col) % 2 == 0:
                    rect(dr, col * 90, y0, col * 90 + 90, y0 + 44, TILE_B, S)
        rect(dr, 0, FLOOR_Y - 6, W, FLOOR_Y, (60, 70, 76), S)
        # touffes tombées par terre au fil de la vidéo
        n = pile_count(tau)
        rr = np.random.default_rng(12)
        for k in range(min(14, n // 6)):
            x = rr.uniform(60, 980)
            y = FLOOR_Y + 30 + rr.uniform(0, 260)
            self.puff(dr, x, y, 16, rr.uniform(), S)

    def puff(self, dr, x, y, r, s, S):
        cloud(dr, [(x, y, r, s)], S)

    def draw_chair(self, dr, tau, S, bpos):
        # dossier
        rect(dr, CX - 125, 880, CX + 125, SEAT_Y, SEAT_D, S, r=40)
        rect(dr, CX - 105, 905, CX + 105, SEAT_Y, (140, 32, 44), S, r=32)
        # pied, repose-pieds, socle
        rect(dr, CX - 22, SEAT_Y + 60, CX + 22, 1500, CHROME, S)
        rect(dr, CX - 95, 1430, CX + 95, 1446, CHROME_D, S, r=6)
        ell(dr, CX, 1530, 175, 26, CHROME_D, S)
        ell(dr, CX, 1524, 160, 20, CHROME, S)
        # assise (bord chromé : c'est là qu'il dit son nom)
        dk = 0.0
        for (t0, g, xh, yh, kh) in PLAN.hits:
            u = tau - t0
            if kh == "seat" and 0 <= u <= 0.3:
                dk = max(dk, 8 * g * math.sin(u * 40) * (1 - u / 0.3))
        rect(dr, CX - 145, SEAT_Y + dk, CX + 145, SEAT_Y + 60, SEAT, S, r=14)
        rect(dr, CX - 150, SEAT_Y - 4 + dk, CX + 150, SEAT_Y + 10 + dk, CHROME, S, r=6)
        # accoudoirs
        for x in (CX - 122, CX + 122):
            rect(dr, x - 8, ARM_Y + 10, x + 8, SEAT_Y, CHROME_D, S)
            rect(dr, x - 26, ARM_Y - 6, x + 26, ARM_Y + 14, CHROME, S, r=8)
        # coussin
        cs = cushion_state(tau)
        if cs is not None:
            x, y, a = cs
            bx, by = bpos
            pts = []
            for i in range(41):
                xx = x - 110 + 220 * i / 40
                yy = y - 30 + 10 * ((2 * i / 40 - 1) ** 4)
                d = xx - bx
                if T["cush_land"] <= tau < T["yank"] and abs(d) < R * 1.02:
                    cy = by + math.sqrt(max(0.0, (R * 1.02) ** 2 - d * d))
                    yy = max(yy, min(y + 22, cy))
                pts.append((xx, yy))
            if a:
                pts = [(x + rot((px - x, py - y), a)[0], y + rot((px - x, py - y), a)[1]) for (px, py) in pts]
            poly = pts + [(x + 110, y + 30), (x - 110, y + 30)] if not a else pts
            dr.polygon(P(poly, S), fill=CUSH_C)
            dr.line(P(pts, S), fill=CUSH_D, width=max(1, int(5 * S)))

    def draw_rings(self, dr, tau, S):
        for (t0, g, x, y) in self.sc.rings:
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

    # -------- le voisin, caché derrière son journal
    def nb_state(self, tau):
        """(journal : 0 levé .. 1 sur les genoux, main levée vers la tête 0..1, sursaut)"""
        t = T
        paper = 0.0
        paper = max(paper, win(tau, t["presque"] + 0.2, t["presque_end"] - 0.4, 0.3, 0.35) * 0.55)
        paper = max(paper, win(tau, t["nb_drop"], t["leave"] + 0.4, 0.15, 0.5))
        hand = max(win(tau, t["presque"] + 0.5, t["face_tuft"] - 0.1, 0.25, 0.25),
                   win(tau, t["pat"], t["pat"] + 1.0, 0.25, 0.25))
        jolt_ = 0.0
        for th in (38.6, 40.4, 42.0):
            u = tau - th
            if 0 <= u <= 0.3:
                jolt_ = max(jolt_, 22 * math.sin(math.pi * u / 0.3))
        return paper, hand, jolt_

    def draw_neighbor(self, dr, tau, S, bpos, layer):
        paper, hand, jl = self.nb_state(tau)
        hx, hy = NB[0], NB[1] + jl * 0.4
        if layer == "back":
            rect(dr, NB[0] - 125, 900, NB[0] + 125, 1270, SEAT_D, S, r=36)
            rect(dr, NB[0] - 22, 1270, NB[0] + 22, 1500, CHROME, S)
            ell(dr, NB[0], 1528, 160, 22, CHROME, S)
            rect(dr, NB[0] - 140, 1250, NB[0] + 140, 1300, SEAT, S, r=12)
            # corps sous la cape
            dr.polygon(P([(hx - 60, hy + 60), (hx + 60, hy + 60), (hx + 140, 1262), (hx - 140, 1262)], S), fill=NCAPE)
            for k in range(4):
                x = hx - 100 + 66 * k
                dr.line(P([(hx + (x - hx) * 0.35, hy + 80), (x, 1255)], S), fill=NCAPE_D, width=max(1, int(4 * S)))
            rect(dr, hx - 24, hy + 30, hx + 24, hy + 70, NSKIN_D, S)
            ell(dr, hx - 60, hy + 6, 14, 20, NSKIN_D, S)
            ell(dr, hx + 60, hy + 6, 14, 20, NSKIN_D, S)
            ell(dr, hx, hy, NB_R, NB_R, NSKIN, S)
            # sa coupe à lui, sage (raie sur le côté)
            dr.chord([(hx - NB_R - 2) * S, (hy - NB_R - 4) * S, (hx + NB_R + 2) * S, (hy + NB_R * 0.6) * S],
                     180, 360, fill=(52, 40, 34))
            dr.line([(hx - 20) * S, (hy - NB_R) * S, (hx - 10) * S, (hy - 20) * S], fill=(90, 72, 60),
                    width=max(1, int(4 * S)))
            # le tas sur sa tête (tout ce qui a été coupé à Bounce)
            if not (T["pile_in"] - 0.05 <= tau < T["leave"] + 0.02):
                n = pile_count(tau) if tau < T["leave"] else 0
                pts = [(x, y + jl * 0.4, 20 + 6 * ((k * 7) % 5) / 4, (k * 0.37) % 1) for k, (x, y) in enumerate(PILE[:n])]
                cloud(dr, pts, S)
            return
        # devant : le journal et les mains
        y0 = lerp(925.0, 1150.0, paper) + jl * 0.3
        x0, x1 = NB[0] - 140, NB[0] + 140
        h = lerp(200.0, 80.0, paper)
        rect(dr, x0, y0, x1, y0 + h, PAPER, S, r=4)
        dr.line([NB[0] * S, y0 * S, NB[0] * S, (y0 + h) * S], fill=PAPER_D, width=max(1, int(3 * S)))
        rect(dr, x0 + 16, y0 + 14, x0 + 120, min(y0 + h - 6, y0 + 40), (60, 60, 66), S)
        for k in range(int(h // 24) - 1):
            yy = y0 + 56 + k * 22
            if yy > y0 + h - 8:
                break
            for (a, b) in ((x0 + 16, x0 + 125), (x1 - 125, x1 - 16)):
                dr.line([a * S, yy * S, (b - 12 * (k % 3)) * S, yy * S], fill=PAPER_D, width=max(1, int(5 * S)))
        hl = (x0, y0 + h * 0.5)
        hr = (x1, y0 + h * 0.5)
        if hand > 0:
            tgt = (hx + 40, hy - NB_R - 30)
            hr = lerp2(hr, tgt, hand)
            capsule(dr, (x1 - 10, y0 + h * 0.6), hr, 15, NCAPE, S)
        for q in (hl, hr):
            ell(dr, q[0], q[1], 22, 22, NSKIN, S)
        # la touffe qui lui tombe sur le visage pendant qu'il regarde (17,5)
        u = tau - T["face_tuft"]
        if 0.55 <= u <= 1.4 and paper > 0.2:
            cloud(dr, [(hx - 14, hy + 18, 24, 0.5), (hx + 14, hy + 22, 22, 0.3)], S)

    def draw_pile(self, dr, tau, S, bpos, part):
        """Bounce dans le tas du voisin : le tas autour de lui (derrière) et devant son bas."""
        n = pile_count(tau)
        _p, _h, jl = self.nb_state(tau)
        bx, by = bpos
        pts = []
        for k, (x, y) in enumerate(PILE[:n]):
            front = y > by + 0.45 * R and abs(x - bx) < R * 1.2
            if (part == "front") != front:
                continue
            pts.append((x, y + jl * 0.4, 20 + 6 * ((k * 7) % 5) / 4, (k * 0.37) % 1))
        cloud(dr, pts, S)

    # -------- le barbier
    def draw_barber(self, dr, tau, S, body):
        sc = self.sc
        t = T
        bx = sc.bx(tau)
        jl = jolt(tau)
        lift = sc.barber_lift(tau) + 30 * jl
        lean = math.radians(sc.lean(tau))
        talk = talking(tau)
        bob = 5 * math.sin(tau * 40) if talk else 0.0
        hip = (bx, 1180.0 - lift)

        def B(u, v):
            return (hip[0] + v * math.cos(lean) + u * math.sin(lean), hip[1] - u * math.cos(lean) + v * math.sin(lean))
        shN, shF = B(330, -62), B(330, 58)
        head = B(412 + 8 * jl, -2)
        head = (head[0], head[1] + bob)
        if body:
            dangle = clamp01((lift - 40) / 120)
            for sx in (-1, 1):
                foot = (hip[0] + sx * 40 + sx * 30 * dangle * math.sin(tau * 18), min(FLOOR_Y - 8, hip[1] + 370))
                capsule(dr, (hip[0] + sx * 32, hip[1]), foot, 20, (44, 46, 58), S)
                ell(dr, foot[0] + 10, foot[1] + 4, 32, 13, (24, 24, 30), S)
            pts = [B(-30, -92), B(-30, 92), B(330, 74), B(348, 0), B(330, -74)]
            dr.polygon(P(pts, S), fill=COAT)
            for k in range(3):
                q = B(60 + 80 * k, -16)
                ell(dr, q[0], q[1], 7, 7, COAT_D, S)
            neck = B(348, -2)
            capsule(dr, neck, (head[0], head[1] + 30), 22, BSKIN, S)
            hx, hy = head
            ell(dr, hx, hy, 72, 72, BSKIN, S)
            look = -1.0
            ell(dr, hx + look * 70, hy + 10, 14, 13, BSKIN, S)
            # casquette (elle s'envole pendant le ralenti : il est chauve)
            if tau < self.sc.cap_t:
                self.draw_cap(dr, hx, hy, 0.0, S)
            else:
                u = tau - self.sc.cap_t
                if u < 1.2:
                    q = (hx + 260 * u, hy - 380 * u + 900 * u * u)
                    if q[1] < FLOOR_Y - 20:
                        self.draw_cap(dr, q[0], q[1] + 40, 5 * u, S)
                ell(dr, hx - 22, hy - 44, 22, 10, BSKIN_L, S)
            # la barbe de Bounce posée sur son crâne (après l'issue), jusqu'au dernier sursaut
            if t["issue"] + 0.55 <= tau < t["last"] + 0.05:
                pts = [(hx + x * 0.62, hy - 72 + y * 0.55 - 10, r * 0.8, s) for i, (x, y, r, s) in
                       enumerate(HAIR2_ALL) if i in KEEP2]
                cloud(dr, pts, S)
            self._head = head
            return
        # bras (devant tout)
        c, o = self.hand_targets(tau, bx, head, shN, shF, jl)
        elN, c = arm_ik(shN, c, bend=1.0)
        elF, o = arm_ik(shF, o, bend=-1.0)
        for (s, el, hnd) in ((shF, elF, o), (shN, elN, c)):
            capsule(dr, s, el, 21, COAT_D, S)
            capsule(dr, el, hnd, 19, COAT, S)
            ell(dr, hnd[0], hnd[1], 24, 24, BSKIN, S)
        # objets tenus
        if t["comb0"] - 0.1 <= tau <= t["ant"] + 0.4:
            rect(dr, o[0] - 9, o[1] - 60, o[0] + 9, o[1] + 8, (40, 40, 48), S, r=3)
        if t["mirror"] <= tau:
            self.draw_mirror(dr, tau, S, o)
        if t["thumbs"] if False else False:
            pass
        self.draw_clippers(dr, tau, S, c, jl)

    def draw_cap(self, dr, x, y, a, S):
        pts = [(-74, -18), (-70, -60), (-30, -88), (30, -88), (70, -60), (74, -18)]
        vis = [(-74, -18), (-150, -10), (-150, 4), (-74, 0)]
        for poly_, col in ((pts, CAP), (vis, CAP_D)):
            q = [rot(p, a) for p in poly_]
            dr.polygon(P([(x + px, y + py) for (px, py) in q], S), fill=col)

    def hand_targets(self, tau, bx, head, shN, shF, jl):
        """Main N (tondeuse) et main F (l'autre)."""
        t = T
        bpos = PLAN.pos(tau)
        # au travail : la tondeuse sur le côté droit de la tignasse
        c = (bpos[0] + 175 + 12 * math.sin(tau * 9), bpos[1] - 150 + 10 * math.cos(tau * 7))
        o = (bx + 40, 1000.0)
        # chaque contact : la tondeuse balaie la tignasse de droite à gauche
        for (th, g, _x, _y, k) in PLAN.hits:
            u = tau - th
            if 0 <= u <= 0.26 and k == "seat":
                hb = PLAN.pos(th)
                yl = -150
                for (tc, ycut) in CUTS2:
                    if abs(tc - th) < 1e-6:
                        yl = ycut
                c = lerp2((hb[0] + 190, hb[1] + yl), (hb[0] - 150, hb[1] + yl - 20), smooth(u / 0.22))
        c = (c[0], c[1] - 40 * jl)
        # il le tient par le dessus de la tête, puis le serre dans ses bras
        k = win(tau, t["hold"], t["lift_end"], 0.3, 0.3)
        if k > 0:
            o = lerp2(o, (bpos[0] + 30, bpos[1] - 250), k)
        k = win(tau, t["hug"] + 0.3, t["thrown"], 0.3, 0.05)
        if k > 0:
            c = lerp2(c, (bpos[0] - R - 10, bpos[1] + 20), k)
            o = lerp2(o, (bpos[0] + R + 10, bpos[1] + 20), k)
        # le coussin, poussé sous lui
        k = win(tau, t["cush_in"], t["cush_land"], 0.2, 0.2)
        if k > 0:
            cs = cushion_state(tau) or (CX, CUSH_TOP)
            o = lerp2(o, (cs[0] + 110, cs[1]), k)
        # faux arrêt : il taille doucement, sur le dessus
        k = win(tau, t["easy"] - 0.1, 23.5, 0.3, 0.2)
        if k > 0:
            c = lerp2(c, (bpos[0] + 60 + 40 * math.sin(tau * 3), bpos[1] - 250), k)
            o = lerp2(o, (bpos[0] + 160, bpos[1] - 120), k)
        # il arrache le coussin
        k = win(tau, t["yank"] - 0.2, t["yank"] + 0.15, 0.15, 0.25)
        if k > 0:
            o = lerp2(o, (CX + 140, CUSH_TOP + 20), k)
        # le peigne : passes sur le crâne
        if t["comb0"] <= tau <= t["comb1"]:
            u = (tau - t["comb0"]) / (t["comb1"] - t["comb0"])
            a = math.radians(-175 + 165 * smooth((u * 3) % 1.0))
            o = (bpos[0] + (R + 70) * math.cos(a), bpos[1] + (R + 70) * math.sin(a))
        k = win(tau, t["comb1"], t["ant"], 0.1, 0.1)
        if k > 0:
            o = lerp2(o, (bpos[0] + 30, bpos[1] - R - 120), k)
        if t["ant"] <= tau <= t["ant"] + 0.3:
            o = lerp2((bpos[0] + 30, bpos[1] - R - 100), (bpos[0] + 70, bpos[1] - R - 330), smooth((tau - t["ant"]) / 0.2))
        # l'antenne : il la coupe
        if t["snip"] - 0.3 <= tau <= t["snip"] + 0.2:
            c = lerp2(c, (bpos[0] - 30, bpos[1] - R - 120), smooth((tau - t["snip"] + 0.3) / 0.3))
        # Bounce revient avec plus de cheveux : bras ballants
        k = win(tau, t["back"] + 0.1, t["level"], 0.3, 0.3)
        if k > 0:
            c = lerp2(c, (bx - 30, 1080.0), k)
            o = lerp2(o, (bx + 70, 1080.0), k)
        # le miroir
        if tau >= t["mirror"]:
            u = smooth((tau - t["mirror"]) / 0.5)
            o = lerp2(o, (690.0, 1020.0), u)
            if t["perfect"] <= tau <= t["perfect"] + 0.7:      # « Perfect. » : petit moulinet du miroir
                o = (o[0] + 20 * math.sin((tau - t["perfect"]) * 18), o[1] - 30 * math.sin((tau - t["perfect"]) * 9))
            k = win(tau, t["admire"], t["last"] - 0.1, 0.4, 0.1)
            if k > 0:                                              # il s'admire avec sa nouvelle perruque
                o = lerp2(o, (head[0] - 150, head[1] + 10 + 8 * math.sin(tau * 6)), k)
        # le dernier sursaut : la tondeuse passe sur son propre crâne
        if t["last"] <= tau <= t["last"] + 0.35:
            u = smooth((tau - t["last"]) / 0.25)
            c = lerp2((head[0] - 80, head[1] - 90), (head[0] + 90, head[1] - 90), u)
        return c, o

    def draw_mirror(self, dr, tau, S, hnd):
        t = T
        admire = win(tau, t["admire"], t["last"] - 0.1, 0.4, 0.1)
        x, y = hnd[0], hnd[1] - 110
        rect(dr, hnd[0] - 10, hnd[1] - 40, hnd[0] + 10, hnd[1] + 20, FRAME, S, r=5)
        if admire > 0.5:                                    # tourné vers lui : on voit le dos
            ell(dr, x, y, 72, 92, FRAME, S)
            ell(dr, x, y, 62, 82, (120, 84, 50), S)
            return
        ell(dr, x, y, 72, 92, FRAME, S)
        ell(dr, x, y, 62, 82, MIRROR, S)
        # le reflet : Bounce en petit, avec ce qu'il a sur la tête
        pos = base.HERO["pos"]
        e = base.HERO["expr"]
        rr = 34.0
        k = rr / R
        base.HERO["expr"] = self.expr_at(tau)
        base.ball(dr, x * S, (y + 10) * S, rr * S)
        base.HERO["pos"] = pos
        base.HERO["expr"] = e
        hair = self.hair_now(tau)
        cloud(dr, [(x - hx * k, y + 10 + hy * k, max(6.0, r * k), s) for (hx, hy, r, s) in hair], S)
        dr.line([(x + 30) * S, (y - 60) * S, (x + 48) * S, (y - 30) * S], fill=(240, 248, 255), width=max(1, int(5 * S)))

    def draw_clippers(self, dr, tau, S, c, jl):
        t0 = T["slow_hit"]
        u = tau - t0
        x, y = c
        ang = -0.4 + 0.5 * jl * math.sin(tau * 30)
        level = win(tau, T["level"], T["beard"] + 0.3, 0.4, 0.4)
        ang = lerp(ang, -math.pi / 2, level)
        if 0.03 <= u <= 0.62:
            k = clamp01((u - 0.03) / 0.59)
            bp = PLAN.pos(t0)
            hd = getattr(self, "_head", (BX0, 760.0))
            path = [c, (bp[0] + 120, bp[1] - 300), (bp[0] - 60, bp[1] - 330), (bp[0] - 40, bp[1] - 220),
                    (hd[0] - 30, hd[1] - 110), (hd[0] + 40, hd[1] - 60), c]
            n = len(path) - 1
            i = min(n - 1, int(k * n))
            f = k * n - i
            x, y = lerp2(path[i], path[i + 1], smooth(f))
            ang = k * 5 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(a, b):
            return (x + a * ca - b * sa, y + a * sa + b * ca)
        dr.polygon(P([Q(-26, -60), Q(26, -60), Q(30, 52), Q(-30, 52)], S), fill=CLIP_C)
        dr.polygon(P([Q(-28, -60), Q(28, -60), Q(28, -76), Q(-28, -76)], S), fill=(205, 208, 218))
        for kk in range(6):
            q = Q(-24 + 9.6 * kk, -78)
            ell(dr, q[0], q[1], 3, 6, (205, 208, 218), S)
        if 0.03 <= u <= 0.62 or jl > 0.4:
            for kk in range(3):
                q0 = Q(-40, -24 + 24 * kk)
                q1 = Q(-70, -30 + 24 * kk)
                dr.line(P([q0, q1], S), fill=(225, 225, 235), width=max(1, int(5 * S)))

    # -------- ce qui vole
    def draw_particles(self, dr, tau, S):
        pts = []
        for p in PARTS:
            u = (tau - p["t0"]) / p["dur"]
            if u < 0 or u >= 1:
                continue
            e = p["src"]
            if e[5] == "h1":
                hb = PLAN.pos(p["t0"])
                sx, sy = PLAN.squash(p["t0"])
                st = (hb[0] + e[1], hb[1] + e[2])
            else:
                hb = PLAN.pos(T["snip"])
                n = len(REMAIN)
                ax, ay, _r = ant_curve(ant_angle(T["snip"]), e[2], n)
                st = (hb[0] + ax, hb[1] + ay)
            en = p["slot"]
            x = lerp(st[0], en[0], u)
            y = lerp(st[1], en[1], u) - 260 * math.sin(math.pi * u) * (1 - 0.3 * (e[5] == "ant"))
            pts.append((x, y, p["r"] * 0.85, p["s"]))
        cloud(dr, pts, S)

    def draw_flying(self, dr, tau, S):
        """Les rabotages de la tignasse 2, la barbe qui s'envole sur le barbier, la moustache qui revient."""
        t = T
        pts = []
        for i, (x, y, r, s) in enumerate(HAIR2_ALL):
            tc = CUT2_T[i]
            if tc is None:
                continue
            u = tau - tc
            if 0 <= u <= 1.1:
                hb = PLAN.pos(tc)
                px = hb[0] + x - 520 * u - 40 * math.sin(i)
                py = hb[1] + y - 420 * u + 900 * u * u
                if py < FLOOR_Y:
                    pts.append((px, py, r * 0.85, s))
        hd = getattr(self, "_head", (BX0, 760.0))
        u = tau - t["issue"]
        if 0 <= u < 0.55:                            # la barbe part en cloche vers le crâne du barbier
            hb = PLAN.pos(t["issue"])
            k = smooth(u / 0.55)
            for i in KEEP2:
                x, y, r, s = HAIR2_ALL[i]
                st = (hb[0] + x, hb[1] + y)
                en = (hd[0] + x * 0.62, hd[1] - 82 + y * 0.55)
                pts.append((lerp(st[0], en[0], k), lerp(st[1], en[1], k) - 300 * math.sin(math.pi * k),
                            lerp(r, r * 0.8, k), s))
        u = tau - t["last"]
        if 0.05 <= u < 0.55:                         # dernier sursaut : la perruque du barbier part
            k = u / 0.5
            bp = PLAN.pos(t["last"] + 0.55)
            for i in KEEP2:
                x, y, r, s = HAIR2_ALL[i]
                if i >= len(HAIR2_ALL) - len(MUST):
                    continue
                pts.append((hd[0] + x * 0.62 + 600 * k * (1 if x > 0 else 0.4), hd[1] - 82 + y * 0.55 - 300 * k + 1400 * k * k,
                            r * 0.8, s))
            for (x, y, r, s) in MUST:                # la moustache retombe sur la tête de Bounce
                st = (hd[0] + x * 0.62, hd[1] - 82 + y * 0.55)
                en = (bp[0] + x * 1.25, bp[1] - R - 14 + 0.3 * (y - 33))
                kk = smooth(k)
                pts.append((lerp(st[0], en[0], kk), lerp(st[1], en[1], kk) - 220 * math.sin(math.pi * kk), r, s))
        cloud(dr, pts, S)


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 80, "hook_speed": 1.0, "hook_max_s": 1.26,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
LINE_GAIN = {"easy": 0.95, "perfect": 1.0}
REACT_TAU = T["issue"] + 0.75


def exact_events(sim):
    return [(unwarp(t), "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(PLAN.hits)]


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
    hits = [unwarp(h[0]) for h in PLAN.hits]
    iv = np.diff(hits)
    run = best = 1
    for i in range(1, len(iv)):
        run = run + 1 if abs(iv[i] - iv[i - 1]) <= 0.1 * iv[i - 1] else 1
        best = max(best, run)
    tops = []
    for k in range(0, int(END * 30)):
        tau = k / 30
        x, y = PLAN.pos(tau)
        hair = Sim.hair_now(Sim.__new__(Sim), tau)
        top = min([y - R] + [y + hy - r for (hx, hy, r, s) in hair])
        tops.append((round(top), round(unwarp(tau), 2)))
    return {"hits": len(hits), "cv": round(float(np.std(iv) / np.mean(iv)), 3), "iv_min": round(float(iv.min()), 2),
            "iv_max": round(float(iv.max()), 2), "run": best, "remain1": len(REMAIN), "keep2": len(KEEP2),
            "highest": sorted(tops)[:4], "end_real": round(unwarp(END), 2), "issue_real": round(unwarp(ISSUE), 2),
            "pile": len(PARTS)}


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
