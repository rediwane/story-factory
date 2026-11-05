"""
Prototype « l'examen » : une salle d'examen silencieuse, vue du fond. Bounce passe un QCM
posé sur sa table ; à chaque rebond il dit son nom et laisse un cercle rose dans la marge
de sa feuille, jamais sur une bulle. Ses voisins se mettent à copier ses « réponses »,
puis toute la salle, dans le dos du surveillant qui ne quitte pas Bounce des yeux. Au
tableau : WRONG ANSWER = -1. Résultat : tout le monde -12, Bounce 0, premier de la classe.

Tout est calculé d'avance sur une seule horloge : Bounce suit des arcs balistiques sous
une gravité unique entre des contacts placés aux instants voulus (durs : il dit son nom ;
mous, sur sa trousse : rien, la trousse s'écrase). Les autres personnages sont des formes
sans visage dont la pose est une fonction du temps.

Deux voix en dehors de Bounce : l'accroche (voix d'accroche du compte) et le surveillant
(Kokoro, banque de prises vérifiées hors dépôt : cfg["voice_bank"]).

    python3 src/stories/exam.py configs/<name>.json [--simulate]
"""
import math, sys, os, bisect
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
import voice as narr_voice

SR = ak.SR

# ------------------------------------------------------------------ le mot de Bounce, stable
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.78


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= WORD_MAX:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ la voix du surveillant
LINES = ["Hush.", "Quiet, please.", "That's a warning.", "Second warning.", "Last warning.",
         "I'm not leaving your side.", "Pencils down.", "Wrong answer: minus one.",
         "Everyone else: minus twelve.", "Zero. Top of the class."]
BANK = {"path": None}
_orig_say = narr_voice.say


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    p = BANK["path"]
    if p and text in LINES:
        f = f"{p}_{LINES.index(text)}.npy"
        if os.path.exists(f):
            return np.load(f).astype(np.float64)
    return _orig_say(text, voice, length_scale) if length_scale is not None else _orig_say(text, voice)


narr_voice.say = bank_say


# ------------------------------------------------------------------ la réverbération, par FFT
def fft_reverb(x, sr, tail_s=0.8, wet=0.5):
    """Même calcul que base.reverb (même réponse impulsionnelle, même mélange), mais la
    convolution passe par la FFT : quelques millisecondes au lieu de minutes."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    m = len(x) + n - 1
    size = 1 << (m - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:m]
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = fft_reverb

# ------------------------------------------------------------------ le calendrier
G = 2600.0
R = 108.0
# contacts durs (il dit son nom) et mous (sa trousse)
HARD = [0.35, 1.25, 2.3, 5.0, 5.95, 6.9, 7.85, 10.7, 11.6, 12.55, 13.45, 16.3, 17.2, 18.1, 19.0, 20.45, 21.35,
        24.2, 25.1, 26.0, 28.8, 29.7, 30.85, 31.75, 32.9, 33.8, 34.75, 38.0, 38.9, 39.85, 40.75, 41.7, 42.6,
        43.55, 44.45, 45.35, 46.8, 47.7, 50.4, 51.3, 52.2, 55.25, 58.6, 63.3]
SOFT = [3.25, 3.8, 4.35, 8.9, 9.45, 10.0, 14.5, 15.05, 15.6, 22.4, 22.95, 23.5, 27.0, 27.55, 28.1,
        35.8, 36.35, 36.9, 37.45, 48.7, 49.25, 49.8, 53.2, 53.75, 54.3, 54.8, 56.25, 56.8, 57.35, 57.95,
        59.6, 60.15, 60.7, 61.25, 61.85, 62.4, 63.85, 64.4]
WHERE = {5.95: "FLR", 6.9: "DY", 11.6: "DG", 17.2: "FLL", 25.1: "HY"}
LINE_T = [3.22, 8.8, 14.4, 22.3, 26.95, 35.7, 48.65, 53.15, 56.2, 59.5]
BIG = {20.45: 2300.0, 46.8: 2800.0, 63.3: 2600.0, 19.0: 1100.0, 45.35: 1100.0}
PAYOFF_T = 61.6
END_T = 64.7
HOOK_HITS = (0.35, 1.25)

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
WALL_TOP, WALL_BOT = 395.0, 905.0
BOARD = (120.0, 412.0, 770.0, 770.0)
CLOCK = (925.0, 520.0, 92.0)
PDESK = (700.0, 875.0, 935.0, 960.0)          # bureau du surveillant (x0, dessus, x1, bas)
ROWS = {1: (1010.0, 0.84), 2: (1235.0, 0.92), 3: (1470.0, 1.0)}
COLX = (140.0, 410.0, 815.0)
SHEET_X = 382.0                               # la feuille de Bounce, sur sa table
TROUSSE = (472.0, 44.0, 100.0)                # x centre, hauteur, largeur
FLOOR3 = 1640.0
AISLE_R = 614.0
AISLE_L = 270.0

BG = (8, 8, 12)
WALL = (32, 34, 54)
FLOOR = (44, 39, 50)
FLOOR_L = (54, 48, 60)
WOOD = (128, 90, 60)
WOOD_D = (86, 60, 42)
WOOD_E = (70, 50, 36)
BOARD_G = (30, 68, 54)
CHALK = (236, 238, 228)
PAPER = (238, 238, 232)
PINK = (255, 20, 200)
INKC = (30, 30, 36)
SUIT = (52, 58, 92)
TROUSSE_C = (120, 196, 240)

STUDENTS = [
    {"name": "sleeper", "col": (150, 110, 215), "kind": "small", "row": 1, "x": 410.0},
    {"name": "blue", "col": (70, 130, 232), "kind": "sq", "row": 2, "x": 140.0},
    {"name": "orange", "col": (240, 142, 52), "kind": "round", "row": 2, "x": 410.0},
    {"name": "teal", "col": (58, 182, 170), "kind": "tall", "row": 2, "x": 815.0},
    {"name": "green", "col": (72, 182, 102), "kind": "tall", "row": 3, "x": 140.0},
    {"name": "yellow", "col": (236, 202, 62), "kind": "sq", "row": 3, "x": 815.0},
]
SNAME = {s["name"]: s for s in STUDENTS}
SLUMP_ORDER = ["blue", "orange", "teal", "green", "yellow", "sleeper"]
BOARD_ORDER = ["blue", "orange", "teal", "green", "yellow", "sleeper"]

# moments
T_LOUPE = (8.0, 9.75)
T_PROC_UP = 8.4
T_STEP_OUT = (26.0, 26.6)
T_WALK = (27.8, 33.8)
T_CROSS = 33.8
T_ROW2 = 38.0
T_WAVE = 38.9
T_BLUE_CHAIR = 41.7
T_CROWD = (42.6, 44.15)
T_WAKE = 46.8
T_SLEEPER_RUN = (47.6, 48.6)
T_PENCILS = 48.65
T_SCATTER = (48.95, 49.4)
T_PULL = 50.45
T_SHOW = (50.6, 51.35)
T_BACK = (51.35, 52.75)
T_TAPS = (52.8, 53.0, 53.2)
T_ERASE = (55.25, 55.6)
T_FIGS = 55.7
T_SLUMP0 = 56.6
T_ZERO = 59.55
T_STAR = 60.45
T_FINAL = 63.3


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def bump(u):
    """0 -> 1 -> 0 sur u in [0, 1]."""
    if u <= 0 or u >= 1:
        return 0.0
    return math.sin(math.pi * u)


def pulse(t, t0, rise, hold, fall):
    if t < t0:
        return 0.0
    if t < t0 + rise:
        return smooth((t - t0) / rise)
    if t < t0 + rise + hold:
        return 1.0
    return 1.0 - smooth((t - t0 - rise - hold) / fall)


def path(t, keys):
    """Interpolation douce entre des clés (t, valeur ou tuple)."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = smooth((t - t0) / max(1e-6, t1 - t0))
            if isinstance(v0, tuple):
                return tuple(lerp(a, b, u) for a, b in zip(v0, v1))
            return lerp(v0, v1, u)
    return keys[-1][1]


# ------------------------------------------------------------------ Bounce
def seat_y(row):
    top, k = ROWS[row]
    return top + 120.0 * k


def student_dims(s):
    k = ROWS[s["row"]][1]
    kind = s["kind"]
    if kind == "tall":
        bw, bh = 108.0, 218.0
    elif kind == "small":
        bw, bh = 120.0, 140.0
    elif kind == "round":
        bw, bh = 150.0, 165.0
    else:
        bw, bh = 148.0, 168.0
    return bw * k, bh * k, 44.0 * k


def contact_point(t):
    """Centre de Bounce au contact de l'instant t."""
    w = WHERE.get(t)
    top3 = ROWS[3][0]
    if t in SOFT:
        return (TROUSSE[0], top3 - TROUSSE[1] + 16.0 - R)
    if w == "FLR":
        return (AISLE_R - 8.0, FLOOR3 - R)
    if w == "FLL":
        return (AISLE_L + 12.0, FLOOR3 - R)
    if w == "DY":
        return (SNAME["yellow"]["x"] - 10.0, top3 - R)
    if w == "DG":
        return (SNAME["green"]["x"] + 10.0, top3 - R)
    if w == "HY":
        s = SNAME["yellow"]
        bw, bh, hr = student_dims(s)
        head_top = seat_y(3) - bh - hr * 1.45 + 20.0
        return (s["x"], head_top - R)
    jit = [0, -14, 10, -6, 16, -10, 4, 12, -16, 6]
    i = int(round(t * 20)) % len(jit)
    return (SHEET_X - 10.0 + jit[i], top3 - R)


class BouncePath:
    def __init__(self):
        cs = sorted([(t, "h") for t in HARD] + [(t, "s") for t in SOFT])
        self.cs = cs
        self.pts = [contact_point(t) for t, _ in cs]
        # départ : en l'air au-dessus de sa feuille, vitesse nulle
        p0 = self.pts[0]
        self.start = (p0[0], p0[1] - 0.5 * G * cs[0][0] ** 2)
        self.ts = [c[0] for c in cs]

    def pos(self, t):
        ts = self.ts
        if t <= ts[0]:
            x, y0 = self.start
            return (x, y0 + 0.5 * G * t * t)
        i = bisect.bisect_right(ts, t) - 1
        if i >= len(ts) - 1:
            # le dernier rebond : il remonte aussi haut, la vidéo coupe en l'air
            t0 = ts[-1]
            x0, y0 = self.pts[-1]
            T = 0.55
            vy = -0.5 * G * T
            u = t - t0
            return (x0, y0 + vy * u + 0.5 * G * u * u)
        t0, t1 = ts[i], ts[i + 1]
        (x0, y0), (x1, y1) = self.pts[i], self.pts[i + 1]
        T = t1 - t0
        vx = (x1 - x0) / T
        vy = (y1 - y0) / T - 0.5 * G * T
        u = t - t0
        return (x0 + vx * u, y0 + vy * u + 0.5 * G * u * u)

    def last_contact(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        return None if i < 0 else self.cs[i]


# ------------------------------------------------------------------ dessin : petites briques
class Pen:
    def __init__(self, dr, S):
        self.dr, self.S = dr, S

    def P(self, v):
        return v * self.S

    def poly(self, pts, fill, outline=None, width=0):
        self.dr.polygon([(x * self.S, y * self.S) for x, y in pts], fill=fill, outline=outline,
                        width=int(width * self.S) if width else 0)

    def rect(self, x0, y0, x1, y1, fill):
        self.dr.rectangle([min(x0, x1) * self.S, min(y0, y1) * self.S, max(x0, x1) * self.S, max(y0, y1) * self.S],
                          fill=fill)

    def rrect(self, x0, y0, x1, y1, r, fill):
        r = max(0.0, min(r, abs(x1 - x0) / 2 - 0.01, abs(y1 - y0) / 2 - 0.01))
        self.dr.rounded_rectangle([min(x0, x1) * self.S, min(y0, y1) * self.S, max(x0, x1) * self.S,
                                   max(y0, y1) * self.S], radius=r * self.S, fill=fill)

    def circ(self, x, y, r, fill):
        self.dr.ellipse([(x - r) * self.S, (y - r) * self.S, (x + r) * self.S, (y + r) * self.S], fill=fill)

    def ell(self, x, y, rx, ry, fill=None, outline=None, width=1):
        self.dr.ellipse([(x - rx) * self.S, (y - ry) * self.S, (x + rx) * self.S, (y + ry) * self.S], fill=fill,
                        outline=outline, width=max(1, int(width * self.S)))

    def line(self, pts, fill, width):
        self.dr.line([(x * self.S, y * self.S) for x, y in pts], fill=fill, width=max(1, int(width * self.S)),
                     joint="curve")

    def text(self, x, y, s, size, fill, anchor="mm"):
        self.dr.text((x * self.S, y * self.S), s, fill=fill, anchor=anchor, font=base.font(size * self.S))


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def rr_pts(x0, y0, x1, y1, r, n=5):
    """Contour d'un rectangle arrondi (pour le faire pivoter)."""
    pts = []
    for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def ring_state(t, tr, rmax):
    v = 520.0 + rmax * 0.9
    age = t - tr
    if age < 0:
        return None
    r = 0.9 * R + v * age
    if r > rmax:
        return None
    u = r / rmax
    return r, (1 - u) ** 0.8


def draw_ring(pen, cx, cy, r, w, col):
    n = max(40, min(260, int(r / 4)))
    pts = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
    pen.line(pts, col, w)


# ------------------------------------------------------------------ la simulation
class Sim:
    scene_top = 0.205

    def __init__(self, cfg, rng):
        self.cfg = cfg
        BANK["path"] = cfg.get("voice_bank")
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.outcome = None
        self.B = BouncePath()
        self.hits = [t for t in HARD]
        self.hi = 0
        self.lines = [(tt, txt, f"l{i}") for i, (tt, txt) in enumerate(zip(LINE_T, LINES))]
        self.replies = []
        # les cercles roses dans la marge de sa feuille : un par rebond sur la feuille
        self.marks = []
        k = 0
        for t in HARD:
            if t in WHERE or t >= T_PULL:
                continue
            side = k % 4
            u = ((k * 0.37) % 1.0)
            self.marks.append((t, side, u))
            k += 1

    def step(self, dt):
        self.t += dt
        evs = []
        while self.hi < len(self.hits) and self.hits[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "floor"))
            self.hi += 1
        if not self.payoff and self.t >= PAYOFF_T:
            self.payoff = True
            self.outcome = "TOP OF THE CLASS"
            evs.append(("payoff", self.outcome))
        if self.t >= END_T - 0.05:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def hero_mood(self):
        return "win"

    # ---------------------------------------------------------- états
    def hits_before(self, t, t0=0.0):
        return [h for h in HARD if t0 <= h <= t]

    def last_hit(self, t):
        i = bisect.bisect_right(HARD, t) - 1
        return HARD[i] if i >= 0 else None

    def proctor(self, t):
        """(x, pieds_y, k, assis, bras, cible_x, inclinaison)"""
        front = (815.0, 962.0, 0.84)
        aisle_f = (AISLE_R, 995.0, 0.86)
        side = (AISLE_R, 1612.0, 1.1)
        board_side = (70.0, 925.0, 0.80)
        if t < T_STEP_OUT[0]:
            x, fy, k = front
        elif t < T_WALK[0]:
            x, fy, k = path(t, [(T_STEP_OUT[0], front), (T_STEP_OUT[1], aisle_f)])
        elif t < T_WALK[1]:
            x, fy, k = path(t, [(T_WALK[0], aisle_f), (T_WALK[1], side)])
        elif t < T_BACK[0]:
            x, fy, k = side
        else:
            x, fy, k = path(t, [(T_BACK[0], side), (T_BACK[0] + 0.9, (AISLE_R, 980.0, 0.84)), (T_BACK[1], board_side)])
        walking = (T_WALK[0] < t < T_WALK[1]) or (T_BACK[0] < t < T_BACK[1]) or (T_STEP_OUT[0] < t < T_STEP_OUT[1])
        seated = t < T_PROC_UP
        if T_PROC_UP <= t < T_PROC_UP + 0.4:
            seated = False
        return {"x": x, "fy": fy, "k": k, "seated": seated, "walking": walking,
                "rise": smooth((t - T_PROC_UP) / 0.4) if t >= T_PROC_UP else 0.0}

    # ---------------------------------------------------------- élèves
    def student_pose(self, s, t):
        """Pose d'un élève : position, décalage, inclinaison latérale, cambrure, gribouillage..."""
        name = s["name"]
        row = s["row"]
        top, k = ROWS[row]
        p = {"x": s["x"], "sy": seat_y(row), "k": k, "dy": 0.0, "lean": 0.0, "back": 0.0, "scrib": 0.0,
             "slump": 0.0, "stand": 0.0, "walk": 0.0, "stretch": 1.0, "chair_tip": 0.0, "squash": 1.0,
             "arms": None, "awake": True, "depth": row}
        awake = not (name == "sleeper" and (t < T_WAKE or t > T_SLUMP0 + 6 * 0.28 + 0.2))
        p["awake"] = awake
        # sursauts
        if awake and t < T_SLUMP0 and not (T_CROWD[0] - 0.1 < t < T_SCATTER[1] + 0.2):
            for h in HARD:
                if h > t:
                    break
                u = (t - h) / 0.32
                if 0 <= u <= 1:
                    amp = (16.0 + 26.0 * clamp01(h / 21.0)) * k
                    if T_WALK[0] < h < T_CROSS + 1.0:
                        amp *= 0.5
                    if h >= T_PENCILS:
                        amp *= 0.6
                    p["dy"] -= amp * bump(u)
        # gags du début
        if name == "yellow":
            p["chair_tip"] = pulse(t, 6.9, 0.12, 0.35, 0.35)
            if 25.1 <= t < 25.45:
                p["squash"] = 1.0 - 0.28 * bump((t - 25.1) / 0.35)
        if name == "green":
            p["lean"] -= 0.32 * pulse(t, 11.6, 0.1, 0.2, 0.3)
            p["lean"] += 0.18 * pulse(t, 17.25, 0.15, 0.3, 0.3)
        if name == "blue":
            f = pulse(t, 20.45, 0.25, 0.5, 0.6)
            p["dy"] += 170.0 * k * f
            p["lean"] -= 0.6 * f
        # copie
        side = 1.0 if s["x"] < COLX[1] else -1.0
        start = {"yellow": 7.85, "green": 11.9}.get(name)
        if row == 2:
            start = T_ROW2
        frozen = [(14.4, 16.25), (T_WALK[0] - 0.8, T_ROW2 - 0.05), (T_PENCILS - 0.05, 99.0)]
        if start is not None and t >= start - 0.05 and t < T_CROWD[0] - 0.05:
            for h in HARD:
                if h > t:
                    break
                if h < start - 0.01 or any(a <= h < b for a, b in frozen):
                    continue
                u = t - h
                if 0 <= u <= 0.95:
                    look = pulse(u, 0.08, 0.17, 0.2, 0.2)
                    if row == 3:
                        p["lean"] += side * 0.27 * look
                    else:
                        p["back"] = max(p["back"], look)
                    if 0.55 <= u <= 0.92:
                        p["scrib"] = 1.0
            if name == "yellow" and 7.85 <= t < 9.6:
                # la toute première copie, plus lente (la loupe)
                u = t - 7.85
                p["lean"] = -0.3 * pulse(u, 0.1, 0.3, 0.4, 0.3)
                p["scrib"] = 1.0 if 1.0 <= u <= 1.7 else 0.0
        if T_WALK[0] - 0.8 <= t < T_ROW2 - 0.05 and row == 3:
            p["stiff"] = True
        # le bleu debout sur sa chaise
        if name == "blue" and T_BLUE_CHAIR <= t < T_CROWD[0]:
            p["stand"] = smooth((t - T_BLUE_CHAIR) / 0.3)
            p["dy"] -= 70.0 * k * p["stand"]
        # la grappe dans le dos du surveillant : on y va par l'allée de gauche et par
        # l'espace devant le dernier rang, jamais à travers une table
        route = CROWD_PATH.get(name)
        if route is not None:
            t0, t1 = CROWD_T[name]
            ts0, ts1 = T_SCATTER
            if t0 <= t < ts1 + 0.4:
                if t < t1:
                    x, fy = along(route, smooth((t - t0) / (t1 - t0)))
                    p["walk"] = 1.0
                    p["stand"] = 1.0
                elif t < ts0:
                    x, fy = route[-1]
                    p["stand"] = 1.0
                else:
                    u = smooth((t - ts0) / (ts1 - ts0))
                    x, fy = along(route, 1.0 - u)
                    p["walk"] = 1.0 if u < 1 else 0.0
                    p["stand"] = 1.0 - smooth((t - ts1) / 0.3) if t > ts1 else 1.0
                kk = k_for(fy)
                p["x"], p["sy"], p["k"] = x, fy, kk
                p["depth"] = depth_for(fy)
                if p["walk"] == 0.0 and p["stand"] < 1.0 and t > ts1:
                    p["depth"] = row
                p["dy"] = 0.0
                p["lean"] = 0.0
                if t1 <= t < ts0:
                    # regarder la feuille de Bounce par-dessus l'épaule du surveillant, gribouiller
                    p["lean"] = -0.22
                    p["stretch"] = 1.12
                    hh = [h for h in HARD if t1 <= h <= t]
                    if hh and t - hh[-1] < 0.9:
                        p["scrib"] = 1.0 if t - hh[-1] > 0.35 else 0.0
                    p["dy"] -= 60.0 * pulse(t, 45.35, 0.4, 0.5, 0.5)
                    if name == "sleeper":
                        p["scrib"] = 1.0
        # après « Pencils down » : droits, mains à plat ; puis l'affaissement
        if t >= T_SCATTER[1] + 0.4:
            p["lean"] = 0.0
            p["back"] = 0.0
            p["scrib"] = 0.0
            p["arms"] = "flat"
        i = SLUMP_ORDER.index(name)
        ts = T_SLUMP0 + 0.28 * i + (0.25 if name == "sleeper" else 0.0)
        if t >= ts:
            p["slump"] = smooth((t - ts) / 0.45)
        # le dormeur
        if name == "sleeper":
            p["stand"] = max(p["stand"], 0.0)
            if T_WAKE <= t < T_SLEEPER_RUN[0]:
                p["dy"] -= 30.0 * k * pulse(t, T_WAKE, 0.08, 0.3, 0.3)
                p["stretch"] = 1.0 + 0.12 * pulse(t, T_WAKE + 0.1, 0.15, 0.4, 0.3)
        return p


FRONT = 1690.0                 # l'espace devant le dernier rang (pieds)
AISLE_X = 275.0                # l'allée de gauche, entre la table du vert et celle de Bounce
CROWD_PATH = {
    "yellow": [(815.0, 1590.0), (790.0, FRONT), (700.0, 1650.0)],
    "green": [(140.0, 1590.0), (150.0, FRONT), (700.0, FRONT), (775.0, 1646.0)],
    "blue": [(140.0, 1345.0), (AISLE_X, 1385.0), (AISLE_X, FRONT), (735.0, FRONT)],
    "orange": [(410.0, 1345.0), (AISLE_X, 1395.0), (AISLE_X, FRONT), (835.0, 1694.0)],
    "teal": [(815.0, 1345.0), (AISLE_X + 30.0, 1415.0), (AISLE_X, 1440.0), (AISLE_X, FRONT), (850.0, 1650.0)],
    "sleeper": [(410.0, 1111.0), (AISLE_X, 1150.0), (AISLE_X, FRONT), (790.0, 1702.0)],
}
CROWD_T = {"yellow": (42.6, 43.3), "green": (42.65, 43.75), "blue": (42.7, 43.9), "orange": (42.75, 43.95),
           "teal": (42.8, 44.15), "sleeper": (47.6, 48.6)}


def along(route, u):
    """Point à la fraction u (0..1) de la longueur d'une ligne brisée."""
    segs = [math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(route, route[1:])]
    total = sum(segs) or 1.0
    d = clamp01(u) * total
    for (a, b), L in zip(zip(route, route[1:]), segs):
        if d <= L or L == segs[-1]:
            f = 0.0 if L == 0 else min(1.0, d / L)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        d -= L
    return route[-1]


def k_for(fy):
    pts = [(1111.0, 0.84), (1345.0, 0.92), (1590.0, 1.0), (1700.0, 1.02)]
    if fy <= pts[0][0]:
        return pts[0][1]
    for (a, ka), (b, kb) in zip(pts, pts[1:]):
        if fy <= b:
            return ka + (kb - ka) * (fy - a) / (b - a)
    return pts[-1][1]


def depth_for(fy):
    if fy < 1250:
        return 1.5
    if fy < 1500:
        return 2.5
    if fy < 1620:
        return 2.9
    return 3.2


# ------------------------------------------------------------------ le dessin
class Drawer:
    def __init__(self, sim):
        self.sim = sim
        self.B = sim.B

    # ---- décor
    def wall(self, pen, t):
        pen.rect(0, WALL_TOP, W, WALL_BOT, WALL)
        pen.rect(0, WALL_BOT, W, 1700, FLOOR)
        for kx in range(10):
            y = WALL_BOT + (kx ** 1.35) * 34
            if y < 1700:
                pen.line([(0, y), (W, y)], FLOOR_L, 2)
        pen.rect(0, WALL_BOT - 14, W, WALL_BOT, (40, 42, 64))

    def board(self, pen, t):
        x0, y0, x1, y1 = BOARD
        pen.rect(x0 - 14, y0 - 14, x1 + 14, y1 + 14, WOOD_D)
        pen.rect(x0, y0, x1, y1, BOARD_G)
        pen.rect(x0 - 14, y1, x1 + 14, y1 + 16, WOOD)
        cx = (x0 + x1) / 2
        # SILENCE. / EXAM IN PROGRESS, effacés à la fin pour les résultats
        er = clamp01((t - T_ERASE[0]) / (T_ERASE[1] - T_ERASE[0]))
        if er < 1:
            pen.text(cx, 470, "SILENCE.", 88, CHALK)
            pen.text(cx, 548, "EXAM IN PROGRESS", 50, CHALK)
            if er > 0:
                ex = x0 + 10 + (x1 - x0 - 20) * er
                pen.rect(x0 + 10, 425, ex, 590, BOARD_G)
                pen.rrect(ex - 20, 430, ex + 20, 585, 8, (60, 50, 44))
        # la règle
        pen.text(cx, 730, "WRONG ANSWER = −1", 46, CHALK)
        # les trois coups de craie, puis le soulignement
        for tt in T_TAPS:
            if tt <= t < tt + 0.5:
                pen.circ(cx + 150 + (tt - T_TAPS[0]) * 60, 760, 7, CHALK)
        if t >= T_TAPS[-1]:
            u = clamp01((t - T_TAPS[-1]) / 0.35)
            pen.line([(cx - 230, 757), (cx - 230 + 460 * u, 757)], CHALK, 5)
        # les résultats
        if t >= T_FIGS:
            for i, nm in enumerate(BOARD_ORDER):
                ti = T_FIGS + 0.2 * i
                if t < ti:
                    continue
                fx = x0 + 62 + i * ((x1 - x0 - 124) / 5)
                fy = 596
                self.chalk_fig(pen, SNAME[nm], fx, fy)
                if t >= ti + 0.08:
                    pen.text(fx, 663, "−12", 38, CHALK)
        if t >= T_ZERO:
            pen.ell(cx - 175, 482, 44, 44, outline=(255, 120, 220), width=9)
            if t >= T_ZERO + 0.2:
                pen.text(cx - 40, 486, "0", 140, (255, 140, 225))
        if t >= T_STAR:
            u = clamp01((t - T_STAR) / 0.25)
            self.star(pen, cx + 140, 482, 78 * (0.6 + 0.4 * u), (250, 214, 80))
            pen.text(cx + 140, 488, "1st", 42, (60, 40, 10))

    def chalk_fig(self, pen, s, x, y):
        col = mix(s["col"], CHALK, 0.25)
        kind = s["kind"]
        if kind == "tall":
            pen.rrect(x - 13, y - 30, x + 13, y + 22, 6, col)
        elif kind == "round":
            pen.rrect(x - 20, y - 18, x + 20, y + 22, 18, col)
        elif kind == "small":
            pen.rrect(x - 15, y - 8, x + 15, y + 22, 6, col)
        else:
            pen.rrect(x - 19, y - 16, x + 19, y + 22, 6, col)
        top = {"tall": y - 30, "round": y - 18, "small": y - 8}.get(kind, y - 16)
        pen.circ(x, top - 11, 11, col)

    def star(self, pen, x, y, r, col):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.48
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        pen.poly(pts, col)

    def clock(self, pen, t):
        cx, cy, r = CLOCK
        tilt = 0.0
        if t >= 13.45:
            tilt += 0.12 * math.sin((t - 13.45) * 11.0) * math.exp(-(t - 13.45) * 2.2)
        if t >= 20.45:
            tilt += 0.24 * smooth((t - 20.45) / 0.25) + 0.08 * math.sin((t - 20.45) * 9.0) * math.exp(-(t - 20.45) * 2.5)
        pen.line([(cx, cy - r - 30), (cx, cy - r - 8)], (90, 90, 100), 3)
        pen.circ(cx, cy - r - 30, 5, (120, 120, 130))
        # le cadran pivote autour du clou
        px, py = cx, cy - r - 30
        ccx = px + (cy - py) * math.sin(-tilt)
        ccy = py + (cy - py) * math.cos(tilt)
        pen.circ(ccx, ccy, r + 9, (62, 62, 74))
        pen.circ(ccx, ccy, r, (240, 238, 230))
        for i in range(12):
            a = i * math.pi / 6 + tilt
            pen.line([(ccx + 0.8 * r * math.sin(a), ccy - 0.8 * r * math.cos(a)),
                      (ccx + 0.93 * r * math.sin(a), ccy - 0.93 * r * math.cos(a))], INKC, 5)
        mins = -5.0 + 5.0 * clamp01(t / T_PENCILS)
        am = mins / 60 * 2 * math.pi + tilt
        ah = (11 + (55 + 5 * clamp01(t / T_PENCILS)) / 60) / 12 * 2 * math.pi + tilt
        pen.line([(ccx, ccy), (ccx + 0.5 * r * math.sin(ah), ccy - 0.5 * r * math.cos(ah))], INKC, 10)
        pen.line([(ccx, ccy), (ccx + 0.82 * r * math.sin(am), ccy - 0.82 * r * math.cos(am))], INKC, 7)
        pen.circ(ccx, ccy, 7, INKC)

    def proctor_desk(self, pen, t):
        x0, top, x1, bot = PDESK
        pen.rect(x0 - 8, top, x1 + 8, top + 18, WOOD)
        pen.rect(x0, top + 18, x1, bot, WOOD_D)

    # ---- tables
    def desk(self, pen, x, row, sheet=True, t=0.0, own=False):
        top, k = ROWS[row]
        w = 250.0 * k
        d = 40.0 * k
        pen.poly([(x - w / 2 + 14 * k, top - d), (x + w / 2 - 14 * k, top - d), (x + w / 2, top), (x - w / 2, top)], WOOD)
        pen.rect(x - w / 2, top, x + w / 2, top + 15 * k, WOOD_E)
        for sx in (-1, 1):
            lx = x + sx * (w / 2 - 14 * k)
            pen.rect(lx - 6 * k, top + 15 * k, lx + 6 * k, top + 150 * k, (62, 54, 62))

    def sheet_on_desk(self, pen, x, row, t, fly=0.0, own=False):
        top, k = ROWS[row]
        dy = -fly
        cx = x + (SHEET_X - COLX[1] if own else 0.0)
        w0, w1 = 120 * k, 128 * k
        pts = [(cx - w0 / 2, top - 34 * k + dy), (cx + w0 / 2, top - 34 * k + dy), (cx + w1 / 2, top - 6 * k + dy),
               (cx - w1 / 2, top - 6 * k + dy)]
        if fly > 1:
            a = 0.35 * math.sin(fly * 0.05)
            pts = rot(pts, cx, top - 20 * k + dy, a)
        pen.poly(pts, PAPER)
        if not own:
            for j in range(3):
                yy = top - 28 * k + j * 8 * k + dy
                if fly <= 1:
                    pen.line([(cx - 40 * k, yy), (cx + 30 * k, yy)], (180, 180, 186), 2)
        return cx

    def own_sheet(self, pen, t):
        if t >= T_PULL:
            return
        top, k = ROWS[3]
        fly = self.paper_fly(t)
        cx = self.sheet_on_desk(pen, COLX[1], 3, t, fly, own=True)
        # bulles minuscules au milieu, cercles roses dans la marge
        if fly < 1:
            for j in range(3):
                for i in range(4):
                    pen.circ(cx - 24 + i * 16, top - 27 + j * 9, 2.6, (150, 150, 160))
            for (tm, side, u) in self.sim.marks:
                if tm > t:
                    break
                if side == 0:
                    mx, my = cx - 56, top - 33 + 26 * u
                elif side == 1:
                    mx, my = cx + 56, top - 33 + 26 * u
                elif side == 2:
                    mx, my = cx - 50 + 100 * u, top - 31
                else:
                    mx, my = cx - 50 + 100 * u, top - 9
                pen.ell(mx, my, 13, 5, outline=PINK, width=2.5)

    def paper_fly(self, t):
        if 20.45 <= t < 22.2:
            u = (t - 20.45) / 1.75
            return 120.0 * math.sin(math.pi * min(1.0, u * 1.1)) * (1 - u * 0.2)
        return 0.0

    def trousse(self, pen, t):
        x, h, w = TROUSSE
        top3 = ROWS[3][0]
        sq = 0.0
        for ts in SOFT:
            u = t - ts
            if -0.05 <= u <= 0.28:
                sq = max(sq, 1.0 - abs(u - 0.05) / 0.25 if u > 0.05 else 1.0 + u / 0.1)
        sq = clamp01(sq)
        hh = h * (1 - 0.45 * sq)
        ww = w * (1 + 0.22 * sq)
        pen.rrect(x - ww / 2, top3 - 8 - hh, x + ww / 2, top3 - 4, hh / 2, TROUSSE_C)
        pen.line([(x - ww / 2 + 12, top3 - 8 - hh * 0.55), (x + ww / 2 - 12, top3 - 8 - hh * 0.55)], (70, 130, 180), 3)
        pen.circ(x + ww / 2 - 16, top3 - 8 - hh * 0.55, 5, (230, 230, 240))

    # ---- élèves
    def chair(self, pen, s, p):
        """La chaise d'un élève, toujours à sa place (même quand il est parti)."""
        x = s["x"]
        ck = ROWS[s["row"]][1]
        tip = p["chair_tip"]
        cy = seat_y(s["row"])
        pts = [(x - 70 * ck, cy - 10 * ck), (x + 70 * ck, cy - 10 * ck), (x + 70 * ck, cy + 8 * ck), (x - 70 * ck, cy + 8 * ck)]
        if tip:
            pts = [(px, py + 18 * tip) for px, py in pts]
        pen.poly(pts, (72, 72, 90))
        for sx in (-1, 1):
            lx = x + sx * 60 * ck
            pen.rect(lx - 5 * ck, cy + 8 * ck + 18 * tip, lx + 5 * ck, cy + 70 * ck + 6 * tip, (72, 72, 90))

    def student(self, pen, s, t, p):
        k = p["k"]
        bw, bh, hr = student_dims(s)
        bw, bh, hr = bw / ROWS[s["row"]][1] * k, bh / ROWS[s["row"]][1] * k, hr / ROWS[s["row"]][1] * k
        x = p["x"]
        seat = p["sy"]
        col = s["col"]
        stand = p["stand"]
        walk = p["walk"]
        # corps
        base_y = seat + p["dy"]
        legs = 0.0
        if stand > 0:
            legs = 62.0 * k * stand
            bob = abs(math.sin(t * 14.0)) * 10 * k * walk
            base_y = seat - bob
            # jambes
            lw = 16 * k
            ph = math.sin(t * 14.0) * walk
            for sx, ph2 in ((-1, ph), (1, -ph)):
                lx = x + sx * bw * 0.22 + ph2 * 10 * k
                pen.rect(lx - lw / 2, base_y - legs, lx + lw / 2, base_y, dim(col, 0.7))
            base_y -= legs
        sy = p["squash"] * p["stretch"] * (1 - 0.32 * p["slump"])
        top = base_y - bh * sy
        lean = p["lean"]
        back = p["back"]
        # le corps pivote autour du bassin
        body = rr_pts(x - bw / 2, top, x + bw / 2, base_y, min(bw, bh) * (0.45 if s["kind"] == "round" else 0.22))
        if s.get("kind") == "round":
            body = rr_pts(x - bw / 2, top, x + bw / 2, base_y, bw * 0.45)
        if p["chair_tip"] > 0:
            lean_b = 0.0
            body = [(px, py + 14 * p["chair_tip"]) for px, py in body]
            top += 14 * p["chair_tip"]
        a = lean
        body = rot(body, x, base_y, a)
        pen.poly(body, col)
        # bras : gribouillage / à plat
        hx = x + math.sin(a) * (base_y - top)
        hy = base_y - math.cos(a) * (base_y - top)
        # tête
        hr2 = hr
        hd = hr * 0.55 - (20 * k if not p.get("stiff") else 2 * k)
        hd -= 26 * k * back            # cambré en arrière : la tête descend vers nous
        hd -= 26 * k * p["slump"]
        hx2 = hx + math.sin(a) * hd * 0.0 + (math.sin(a) * hr * 0.6)
        hy2 = hy - hd
        if back > 0:
            hy2 = hy - hd
            hr2 = hr * (1 + 0.15 * back)
        if p["slump"] > 0:
            hy2 = lerp(hy2, top + hr * 0.55, p["slump"])
            hx2 = hx2 + 6 * k * math.sin(t * 2.0) * p["slump"]
        pen.circ(hx2, hy2, hr2, mix(col, (255, 255, 255), 0.14))
        if p["scrib"] > 0:
            side = 1 if (s["x"] < COLX[1]) else -1
            ex = x - side * bw * 0.48
            ey = base_y - bh * 0.45 + 6 * math.sin(t * 45.0)
            pen.line([(ex, ey), (ex - side * 14 * k, ey - 24 * k)], (250, 210, 90), 5)
        if p["arms"] == "flat" and p["slump"] < 0.3:
            for sx in (-1, 1):
                pen.rect(x + sx * bw / 2 - 9 * k, base_y - bh * 0.6, x + sx * bw / 2 + 9 * k, base_y - bh * 0.2,
                         dim(col, 0.85))
        return (hx2, hy2, hr2)

    def zs(self, pen, t, hx, hy, k):
        for i in range(3):
            ph = ((t * 0.7) + i / 3.0) % 1.0
            zx = hx + 20 * k + ph * 40 * k
            zy = hy - 40 * k - ph * 90 * k
            c = mix(WALL, (190, 190, 205), (1 - ph) * 0.9 + 0.1)
            pen.text(zx, zy, "z", int(26 + 14 * ph), c)

    # ---- le surveillant
    def proctor(self, pen, t, P, front_layer):
        x, fy, k = P["x"], P["fy"], P["k"]
        seated = P["seated"]
        bw, bh, hr = 134 * k, 250 * k, 50 * k
        jump = 36 * k * bump((t - T_FINAL) / 0.35) if t >= T_FINAL else 0.0
        if seated:
            base_y = PDESK[1] + 40 - 70 * (P["rise"])
        else:
            base_y = fy - 92 * k - jump
            bob = abs(math.sin(t * 9.0)) * 8 * k if P["walking"] else 0.0
            base_y -= bob
            ph = math.sin(t * 9.0) if P["walking"] else 0.0
            for sx, ph2 in ((-1, ph), (1, -ph)):
                lx = x + sx * bw * 0.22 + ph2 * 12 * k
                pen.rect(lx - 14 * k, base_y, lx + 14 * k, fy - jump - bob + ph2 * 0, (34, 38, 64))
                pen.rrect(lx - 20 * k, fy - jump - 12 * k, lx + 22 * k, fy - jump, 6 * k, (20, 20, 26))
        top = base_y - bh
        lean = 0.0
        if T_CROSS <= t < T_PENCILS + 0.3:
            lean = -0.03
        body = rot(rr_pts(x - bw / 2, top, x + bw / 2, base_y, 38 * k), x, base_y, lean)
        pen.poly(body, SUIT)
        sh = (x + math.sin(lean) * bh, top + 4)
        # col, cravate, badge
        cx, cy = x + math.sin(lean) * (bh - 6), top + 6
        pen.poly([(cx - 24 * k, cy), (cx + 24 * k, cy), (cx, cy + 56 * k)], (232, 232, 238))
        tie_flip = pulse(t, 32.9, 0.12, 0.6, 0.25) if t < 34.0 else 0.0
        if tie_flip > 0.05:
            pen.poly([(cx - 7 * k, cy + 10 * k), (cx + 7 * k, cy + 10 * k), (cx + 60 * k * tie_flip, cy - 30 * k * tie_flip),
                      (cx + 48 * k * tie_flip, cy - 40 * k * tie_flip)], (200, 50, 56))
        else:
            pen.poly([(cx - 7 * k, cy + 10 * k), (cx + 7 * k, cy + 10 * k), (cx + 11 * k, cy + 100 * k), (cx, cy + 112 * k),
                      (cx - 11 * k, cy + 100 * k)], (200, 50, 56))
        pen.line([(cx - 30 * k, cy + 2), (cx, cy + 120 * k), (cx + 30 * k, cy + 2)], (220, 220, 230), 3)
        pen.rrect(cx - 16 * k, cy + 118 * k, cx + 16 * k, cy + 152 * k, 3, (245, 245, 245))
        # tête
        hx = cx + math.sin(lean) * 40
        hy = top - hr * 0.9
        if t < 0.35:
            hy += 18 * k
        elif t < 1.2:
            hy += 18 * k * (1 - smooth((t - 0.35) / 0.8))
        pen.circ(hx, hy, hr, (150, 152, 172))
        self.phead = (hx, hy, hr)
        # bras
        self.proctor_arms(pen, t, P, x, top, bw, bh, k, lean)
        return (hx, hy)

    def arm(self, pen, sx, sy, ex, ey, k, hand=None):
        pen.line([(sx, sy), (ex, ey)], (44, 50, 82), 26 * k)
        pen.circ(ex, ey, 15 * k, (150, 152, 172))
        if hand == "finger":
            pen.line([(ex, ey - 8 * k), (ex, ey - 40 * k)], (150, 152, 172), 9 * k)
        elif hand == "two":
            pen.line([(ex - 6 * k, ey - 8 * k), (ex - 12 * k, ey - 40 * k)], (150, 152, 172), 8 * k)
            pen.line([(ex + 6 * k, ey - 8 * k), (ex + 12 * k, ey - 40 * k)], (150, 152, 172), 8 * k)
        elif hand == "chalk":
            pen.line([(ex, ey), (ex - 18 * k, ey - 8 * k)], CHALK, 7 * k)

    def proctor_arms(self, pen, t, P, x, top, bw, bh, k, lean):
        lsh = (x - bw / 2 + 12 * k, top + 30 * k)
        rsh = (x + bw / 2 - 12 * k, top + 30 * k)
        down_l = (lsh[0] - 6 * k, lsh[1] + 170 * k)
        down_r = (rsh[0] + 6 * k, rsh[1] + 170 * k)
        bx, by = self.B.pos(t)
        # bras gauche (côté salle, à notre gauche) et droit
        L, Rr = down_l, down_r
        lh = rh = None
        if t < T_PROC_UP:
            # assis, il lit une feuille
            L = (x - 40 * k, top + 120 * k)
            Rr = (x + 40 * k, top + 120 * k)
            pen.poly([(x - 60 * k, top + 95 * k), (x + 60 * k, top + 95 * k), (x + 60 * k, top + 135 * k),
                      (x - 60 * k, top + 135 * k)], PAPER)
        if 3.0 <= t < 4.6 or 14.3 <= t < 15.8 or 22.2 <= t < 23.7:
            u = pulse(t, (3.0 if t < 5 else 14.3 if t < 16 else 22.2), 0.2, 1.0, 0.3)
            Rr = (lerp(down_r[0], rsh[0] + 30 * k, u), lerp(down_r[1], top - 40 * k, u))
            rh = "two" if t >= 22.2 else "finger"
        if 26.85 <= t < 28.3:
            u = pulse(t, 26.85, 0.2, 1.0, 0.3)
            Lx = lerp(down_l[0], lsh[0] - 90 * k, u)
            Ly = lerp(down_l[1], lsh[1] + 30 * k, u)
            L = (Lx, Ly)
            lh = "finger"
        if T_CROSS <= t < T_PENCILS + 0.25:
            # bras croisés
            pen.rrect(x - bw / 2 - 4 * k, top + 70 * k, x + bw / 2 + 4 * k, top + 112 * k, 18 * k, (44, 50, 82))
            pen.circ(x - bw / 2 + 4 * k, top + 91 * k, 15 * k, (150, 152, 172))
            pen.circ(x + bw / 2 - 4 * k, top + 91 * k, 15 * k, (150, 152, 172))
            return
        if T_PULL <= t < T_SHOW[1] + 0.2:
            # il tire la feuille et la montre face à nous
            u = smooth((t - T_PULL) / 0.15)
            if t < T_SHOW[0]:
                L = (lerp(down_l[0], SHEET_X + 40, u), lerp(down_l[1], ROWS[3][0] - 20, u))
            else:
                self.big_sheet(pen, t, x - 20 * k, top + 70 * k, k)
                return
        if T_SHOW[1] + 0.2 <= t < T_BACK[1]:
            # la pile sous le bras
            pen.rect(x + bw / 2 - 30 * k, top + 90 * k, x + bw / 2 + 30 * k, top + 112 * k, PAPER)
        if t >= T_STAR + 0.6:
            pass                      # il a fini d'écrire : le bras retombe, le tableau reste dégagé
        elif t >= T_BACK[1]:
            # au tableau : la craie suit ce qu'il écrit
            tx, ty = self.chalk_target(t)
            dx, dy = tx - rsh[0], ty - rsh[1]
            d = math.hypot(dx, dy) or 1.0
            reach = 150.0 * k
            Rr = (rsh[0] + dx / d * reach, rsh[1] + dy / d * reach)
            rh = "chalk"
            # la pile, posée contre lui
        self.arm(pen, lsh[0], lsh[1], L[0], L[1], k, lh)
        self.arm(pen, rsh[0], rsh[1], Rr[0], Rr[1], k, rh)

    def chalk_target(self, t):
        x0, y0, x1, y1 = BOARD
        cx = (x0 + x1) / 2
        if t < T_TAPS[-1] + 0.4:
            return (cx + 160, 745)
        if t < T_ERASE[0]:
            return (cx - 230 + 460 * clamp01((t - T_TAPS[-1]) / 0.35), 750)
        if t < T_FIGS:
            return (x0 + 30 + (x1 - x0 - 60) * clamp01((t - T_ERASE[0]) / 0.35), 500)
        if t < T_FIGS + 1.3:
            i = min(5, int((t - T_FIGS) / 0.2))
            return (x0 + 62 + i * ((x1 - x0 - 124) / 5), 610)
        if t < T_ZERO:
            return (x1 - 60, 680)
        if t < T_STAR:
            return (cx - 60, 490)
        if t < T_FINAL:
            return (cx + 120, 490)
        # il sursaute, la craie lui échappe
        return (cx + 110, 560)

    def big_sheet(self, pen, t, x, y, k):
        """La feuille de Bounce, tenue face à nous : bulles toutes vides, cercles roses dans les marges."""
        u = smooth((t - T_SHOW[0]) / 0.18)
        w, h = 250 * k * u, 330 * k * u
        if w < 4:
            return
        x0, y0 = x - w / 2, y - 40 * k
        pen.rect(x0, y0, x0 + w, y0 + h, PAPER)
        # mains qui la tiennent
        pen.circ(x0, y0 + h * 0.5, 15 * k, (150, 152, 172))
        pen.circ(x0 + w, y0 + h * 0.5, 15 * k, (150, 152, 172))
        if u < 0.9:
            return
        pen.text(x0 + w / 2, y0 + 22 * k, "ANSWER SHEET", 18 * k, (90, 90, 100))
        for j in range(8):
            yy = y0 + 52 * k + j * 32 * k
            pen.text(x0 + 26 * k, yy, str(j + 1), 16 * k, (110, 110, 120))
            for i in range(4):
                bx = x0 + 60 * k + i * 44 * k
                pen.ell(bx, yy, 11 * k, 11 * k, outline=(120, 120, 130), width=2)
        rings = [(0.04, 0.12), (0.96, 0.2), (0.03, 0.45), (0.97, 0.52), (0.05, 0.8), (0.95, 0.86), (0.3, 0.97),
                 (0.7, 0.98), (0.5, 0.025), (0.2, 0.03), (0.82, 0.03), (0.02, 0.63), (0.98, 0.7), (0.5, 0.97)]
        for (u0, v0) in rings:
            pen.ell(x0 + w * u0, y0 + h * v0, 26 * k, 26 * k, outline=PINK, width=4)

    # ---- la loupe
    def loupe(self, pen, t):
        a, b = T_LOUPE
        if not (a <= t < b):
            return
        u = smooth((t - a) / 0.2) * (1 - smooth((t - (b - 0.2)) / 0.2))
        if u <= 0.02:
            return
        cx, cy = 540.0, 1040.0
        w, h = 720 * u, 300 * u
        # fils vers les deux tables
        if u > 0.9:
            pen.line([(cx - 180, cy + h / 2), (SHEET_X, ROWS[3][0] - 30)], (240, 240, 250), 3)
            pen.line([(cx + 180, cy + h / 2), (SNAME["yellow"]["x"], ROWS[3][0] - 30)], (240, 240, 250), 3)
        pen.rrect(cx - w / 2 - 6, cy - h / 2 - 6, cx + w / 2 + 6, cy + h / 2 + 6, 24, (245, 245, 250))
        pen.rrect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 20, (24, 24, 34))
        if u < 0.95:
            return
        for side in (-1, 1):
            px = cx + side * 180
            pen.rect(px - 160, cy - 120, px + 160, cy + 130, PAPER)
            if side < 0:
                base.ball(pen.dr, (px - 130) * pen.S, (cy - 140) * pen.S, 22 * pen.S)
            else:
                pen.rrect(px + 112, cy - 162, px + 152, cy - 122, 6, SNAME["yellow"]["col"])
            for j in range(4):
                yy = cy - 80 + j * 56
                pen.text(px - 128, yy, str(j + 1), 26, (110, 110, 120))
                for i, L in enumerate("ABCD"):
                    bx = px - 70 + i * 62
                    pen.ell(bx, yy, 19, 19, outline=(120, 120, 130), width=3)
                    pen.text(bx, yy, L, 18, (150, 150, 160))
            if side < 0:
                pen.ell(px - 128, cy - 80 + 2 * 56, 34, 34, outline=PINK, width=6)
            else:
                f = clamp01((t - 8.6) / 0.5)
                if f > 0:
                    bx, yy = px - 70 + 1 * 62, cy - 80 + 2 * 56
                    pen.circ(bx, yy, 17 * f, INKC)
                    pen.line([(bx + 10, yy + 4), (bx + 70, yy - 60)], (250, 210, 90), 9)
                    pen.line([(bx + 10, yy + 4), (bx + 18, yy - 5)], INKC, 6)

    # ---- tout
    def draw(self, dr, t, S):
        pen = Pen(dr, S)
        sim = self.sim
        self.wall(pen, t)
        self.board(pen, t)
        self.clock(pen, t)
        P = sim.proctor(t)
        poses = {s["name"]: sim.student_pose(s, t) for s in STUDENTS}
        heads = {}
        # le surveillant au fond (derrière son bureau, ou au tableau)
        proctor_depth = 0.0 if (P["fy"] < 1000) else (1.5 if P["fy"] < 1250 else (2.5 if P["fy"] < 1500 else 3.0))
        if P["fy"] > 1590:
            proctor_depth = 3.0
        if proctor_depth == 0.0:
            if not P["seated"] and P["fy"] <= 965 and P["x"] > 700:
                pass
            self.proctor(pen, t, P, False)
            if P["x"] > 690:
                self.proctor_desk(pen, t)
        else:
            self.proctor_desk(pen, t)
        # rangée par rangée, du fond vers nous
        drawn_proctor = proctor_depth == 0.0
        fly = self.paper_fly(t)
        for row in (1, 2, 3):
            if not drawn_proctor and proctor_depth < row:
                self.proctor(pen, t, P, False)
                drawn_proctor = True
            for s in STUDENTS:
                p = poses[s["name"]]
                if row - 1 < p["depth"] < row:
                    heads[s["name"]] = self.student(pen, s, t, p)
            for x in COLX:
                if row == 3 and x == COLX[1]:
                    self.desk(pen, x, 3)
                    self.trousse(pen, t)
                    self.own_sheet(pen, t)
                    continue
                self.desk(pen, x, row)
                occupied = any(s["row"] == row and s["x"] == x for s in STUDENTS)
                if occupied:
                    self.sheet_on_desk(pen, x, row, t, fly)
            for s in STUDENTS:
                if s["row"] == row:
                    self.chair(pen, s, poses[s["name"]])
            if row == 3 and self.bounce_behind(t):
                self.bounce(pen, t)
            for s in STUDENTS:
                p = poses[s["name"]]
                if abs(p["depth"] - row) < 0.01 or (row == 3 and p["depth"] == 2.9 and False):
                    heads[s["name"]] = self.student(pen, s, t, p)
        # la grappe derrière le surveillant, puis lui, puis ceux devant
        for s in STUDENTS:
            p = poses[s["name"]]
            if p["depth"] == 2.9:
                heads[s["name"]] = self.student(pen, s, t, p)
        if not drawn_proctor:
            self.proctor(pen, t, P, True)
        for s in STUDENTS:
            p = poses[s["name"]]
            if p["depth"] == 3.2:
                heads[s["name"]] = self.student(pen, s, t, p)
        # dormeur : z / !
        sp = poses["sleeper"]
        if "sleeper" in heads:
            hx, hy, hr = heads["sleeper"]
            if t < T_WAKE or t > T_SLUMP0 + 0.28 * 5 + 0.25 + 0.5:
                self.zs(pen, t, hx, hy, sp["k"])
            elif t < T_WAKE + 0.9:
                pen.text(hx, hy - 70 * sp["k"], "!", 70, (255, 230, 90))
        # crayons qui sautent au début
        for h in HARD:
            if 4.9 < h < 5.1 and h <= t < h + 0.6:
                u = (t - h) / 0.6
                for s in STUDENTS:
                    if s["name"] == "sleeper" or s["name"] not in heads:
                        continue
                    hx, hy, hr = heads[s["name"]]
                    yy = hy - hr - 30 - 160 * u + 260 * u * u
                    pen.line([(hx - 14, yy + 8), (hx + 14, yy - 8)], (250, 210, 90), 6)
        # les anneaux
        for h in HARD:
            st = ring_state(t, h, BIG.get(h, 900.0) if h not in HOOK_HITS else 1000.0)
            if st is None:
                continue
            r, inten = st
            if inten < 0.3:
                continue
            x, y = contact_point(h)
            draw_ring(pen, x, y + R * 0.6, r, 7 + 6 * inten, mix(BG, (246, 246, 255), inten))
        if not self.bounce_behind(t):
            self.bounce(pen, t)
        if T_WALK[1] - 0.5 <= t < T_BACK[0] and getattr(self, "phead", None):
            hx, hy, hr = self.phead
            pen.circ(hx, hy, hr, (150, 152, 172))
        self.loupe(pen, t)

    def bounce_behind(self, t):
        lc = self.B.last_contact(t)
        nxt = None
        i = bisect.bisect_right(self.B.ts, t)
        if i < len(self.B.ts):
            nxt = self.B.ts[i]
        for tt in (lc[0] if lc else None, nxt):
            if tt in (6.9, 11.6) and abs(t - tt) < 0.35:
                return True
        return False

    def bounce(self, pen, t):
        x, y = self.B.pos(t)
        base.ball(pen.dr, x * pen.S, y * pen.S, R * pen.S)


class FullSim(Sim):
    def __init__(self, cfg, rng):
        super().__init__(cfg, rng)
        self.D = Drawer(self)

    def draw(self, dr, snap, t, S):
        self.D.draw(dr, snap, S)


DEFAULTS = {
    "hook_text_s": 2.6, "hook_top": 0.085, "hook_font_size": 92,
    "narrator_voice": "bm_lewis", "narrator_length": 1.0, "narr_gap_s": 0.05,
    "sub_y": 0.135, "sub_font_size": 62, "sub_words": 6, "narr_tail_s": 0.0,
    "watermark_y": 0.94, "end_hold_s": 0.05, "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True,
}

Sim = FullSim

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
