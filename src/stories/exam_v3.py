"""
« exam » v3 : une salle d'examen silencieuse, vue de face. Bounce rebondit sur sa copie ;
chaque rebond y laisse un rond rose, au hasard des bulles. Le regard du surveillant (une
ligne pointillée grise) ne quitte pas Bounce ; juste à côté, les autres élèves recopient
ses ronds roses (lignes pointillées roses). Le surveillant finit par lui confisquer sa
copie et lui mettre 0. À la correction (WRONG ANSWER = -1), tous ceux qui l'ont copié
ont un score négatif : le 0 de Bounce est la meilleure note de la salle.

Tout est calculé d'avance sur une seule horloge. Bounce suit des arcs balistiques sous une
gravité unique entre des contacts placés aux instants voulus (durs : il dit son nom ; mous,
sur sa trousse : rien, la trousse s'écrase). Un ralenti (x0,4) au milieu : toute la scène
passe sur un temps de scène tau(t) ; le son garde le temps de la vidéo.

Deux voix en dehors de Bounce : l'accroche (voix d'accroche du compte, rognée de ses
silences) et le surveillant (Kokoro, prises vérifiées hors dépôt : cfg["voice_bank"]).

    python3 src/stories/exam_v3.py configs/exam_v3.json [--simulate]
"""
import math, sys, os, bisect
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
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

# ------------------------------------------------------------------ l'accroche, rognée de ses silences
_orig_hook_voice = ak.hook_voice
_hook_memo = {}


def trimmed_hook_voice(text, sr=SR, prefer_piper=True):
    if text not in _hook_memo:
        x = _orig_hook_voice(text, sr, prefer_piper)
        if x is not None and len(x):
            a = np.abs(x)
            idx = np.where(a > 0.02 * a.max())[0]
            if len(idx):
                x = x[max(0, idx[0] - int(0.01 * sr)): idx[-1] + int(0.02 * sr)].copy()
                n = min(int(0.02 * sr), len(x))
                x[-n:] *= np.linspace(1, 0, n)
        _hook_memo[text] = x
    x = _hook_memo[text]
    return None if x is None else x.copy()


ak.hook_voice = trimmed_hook_voice

# ------------------------------------------------------------------ la voix du surveillant
LINES = ["Hush.", "Quiet.", "That's a zero.", "Pencils down.", "Top of the class."]
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
    """Même calcul que base.reverb (même réponse impulsionnelle, même mélange), par FFT."""
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

# ------------------------------------------------------------------ le temps
SLOW = (32.5, 34.4, 0.4)          # ralenti : [a, b] en temps vidéo, vitesse r


def tau(t):
    a, b, r = SLOW
    if t <= a:
        return t
    if t <= b:
        return a + r * (t - a)
    return t - (b - a) * (1 - r)


# contacts durs, en temps vidéo (Bounce dit son nom à chacun)
HARD = [1.98, 2.85, 5.37, 8.35, 9.21, 10.08, 10.98, 13.60, 14.46, 17.46, 18.32, 19.21, 21.03,
        23.23, 24.10, 24.96, 25.86, 28.74, 29.62, 30.49, 33.00, 34.70, 35.58, 36.45, 37.33,
        39.70, 40.57, 41.45, 44.20, 45.07, 45.95, 48.35, 49.22, 50.10, 53.10, 53.98,
        56.64, 57.52, 58.38, 61.70]
LINE_T = [3.76, 16.40, 42.40, 47.00, 60.40]
ISSUE = 60.40
END_T = 62.62

# ce qui se passe, en temps vidéo, converti en temps de scène plus bas
EV = {
    "wake": 1.98, "yellow_start": 2.85, "hush": 3.76, "sweep1": 8.35, "green_turn": 9.21, "green_start": 10.08,
    "pencil_g": 14.46, "quiet": 16.40, "blue_peek": 17.46, "corner": 18.32, "orange_neck": 19.21,
    "row2_rise": 21.03, "row2_start": 23.23, "sweep2": 24.10, "pencil_y": 25.86, "walk": (27.0, 28.7),
    "planted": 29.62, "nose": 30.49, "two": (31.0, 32.3), "clue": 33.00, "topple": 34.70,
    "crowd": (34.9, 35.58), "sweep3": 39.70, "snatch": 41.80, "zero_write": 43.85, "to_board": (44.35, 45.0),
    "pin0": 45.0, "underline": (45.35, 45.9), "pencils": 47.00, "back_seat": (47.05, 47.45),
    "raise": 47.45, "take": 48.15, "look": (48.4, 50.4), "to_board2": (50.5, 51.9), "pin1": 52.25, "nod": (52.6, 53.05),
    "xs": (53.10, 53.60), "step_r": (53.6, 53.72), "m12": (53.75, 54.10, 54.45, 54.80),
    "hope": 56.64, "hover": (56.64, 58.5), "up": (58.55, 59.0), "slump2": 58.7, "star": 60.40,
    "step_back": (61.0, 61.7), "final": 61.70,
}


def T(k):
    v = EV[k]
    return tuple(tau(x) for x in v) if isinstance(v, tuple) else tau(v)


# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
R = 120.0
WALL_BOT = 905.0
BOARD = (150.0, 535.0, 880.0, 852.0)
SILENCE_XY = (272.0, 584.0)
RULE_XY = (600.0, 588.0)
PIN0 = (300.0, 280.0, 520.0, 490.0)           # la copie de Bounce, épinglée au mur au-dessus du tableau
PIN1 = (540.0, 280.0, 760.0, 490.0)           # celle de Green, à côté
M12 = [(680.0, 642.0), (680.0, 680.0), (680.0, 718.0), (680.0, 756.0)]   # −N au tableau, une ligne par élève
PDESK = (690.0, 880.0, 890.0, 955.0)          # bureau du surveillant (x0, dessus, x1, bas)
DESK = (300.0, 995.0, 790.0, 1140.0)          # table de Bounce : x0, haut (fond), x1, bas (devant)
SHEET = (418.0, 1006.0, 662.0, 1006.0, 402.0, 1130.0, 680.0, 1130.0)   # trapèze : fond g, fond d, devant g, devant d
NROW, NCOL = 6, 5
CASE = (352.0, 994.0, 92.0, 50.0)             # trousse : x centre, dessus, largeur, hauteur
CASE_C = (120, 196, 240)
SUB_Y = 1205.0

BG = (8, 8, 12)
WALL = (30, 32, 52)
WALL_D = (24, 26, 42)
FLOOR = (44, 39, 50)
FLOOR_L = (54, 48, 60)
WOOD = (134, 96, 64)
WOOD_D = (92, 64, 44)
WOOD_E = (74, 52, 38)
BOARD_G = (30, 66, 52)
CHALK = (230, 232, 222)
PAPER = (240, 240, 234)
BUBBLE = (150, 150, 162)
PINK = (255, 20, 200)
RED = (226, 40, 46)
GOLD = (250, 206, 70)
SUIT = (52, 58, 92)
SKIN = (150, 152, 172)
GREY_LINE = (214, 216, 226)

STUDENTS = {
    "yellow": {"col": (236, 202, 62), "kind": "sq", "x": 186.0, "base": 1000.0, "k": 1.0, "side": 1},
    "green": {"col": (72, 182, 102), "kind": "tall", "x": 848.0, "base": 1000.0, "k": 1.0, "side": -1},
    "blue": {"col": (70, 130, 232), "kind": "sq", "x": 205.0, "base": 905.0, "k": 0.8, "side": 1},
    "orange": {"col": (240, 142, 52), "kind": "round", "x": 596.0, "base": 905.0, "k": 0.8, "side": -1},
}
ORDER_M12 = ["yellow", "green", "blue", "orange"]


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
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = smooth((t - t0) / max(1e-6, t1 - t0))
            if isinstance(v0, tuple):
                return tuple(lerp(a, b, u) for a, b in zip(v0, v1))
            return lerp(v0, v1, u)
    return keys[-1][1]


def sheet_point(u, v):
    """Point (u, v) de la copie posée sur la table, en perspective (u en largeur, v en profondeur)."""
    bl, by, br, _, fl, fy, fr, _ = SHEET
    x0 = lerp(bl, fl, v)
    x1 = lerp(br, fr, v)
    return (lerp(x0, x1, u), lerp(by, fy, v))


def grid_uv(i, j):
    """Centre de la bulle (colonne i, ligne j), en coordonnées de feuille."""
    return ((i + 0.5) / NCOL * 0.84 + 0.12, (j + 0.5) / NROW * 0.9 + 0.08)


# ------------------------------------------------------------------ le plan des contacts
def build_contacts():
    """Contacts durs (temps de scène) avec leur point d'impact, puis les mous qui remplissent les passages."""
    rng = np.random.default_rng(11)
    cells = [(i, j) for j in range(NROW) for i in range(NCOL)]
    pick = [cells[q] for q in rng.permutation(len(cells))[:13]]     # il retombe souvent sur les mêmes bulles
    cells = pick
    order = list(range(len(cells))) + list(rng.permutation(len(cells))) + list(rng.permutation(len(cells)))
    hard = []
    k = 0
    snatch = tau(EV["snatch"])
    for tv in HARD:
        ts = tau(tv)
        kind = "sheet" if ts < snatch else "wood"
        if tv in (EV["final"],):
            kind = "wood"
        if tv == EV["clue"]:
            uv = (0.47, 0.5)                                # entre deux lignes, hors des bulles
        elif tv == EV["sweep1"] or tv == EV["sweep3"]:
            uv = grid_uv(0, (k * 2) % NROW)                 # au bord gauche, côté Yellow
        elif tv == EV["sweep2"]:
            uv = grid_uv(NCOL - 1, 3)                       # au bord droit
        elif tv == EV["corner"]:
            uv = (0.02, 0.9)                                # le coin gauche, à un doigt de Yellow
        else:
            i, j = cells[order[k % len(order)]]
            uv = grid_uv(i, j)
            k += 1
        if kind == "wood":
            uv = (0.02 + 0.2 * ((k * 0.37) % 1.0), 0.15 + 0.7 * ((k * 0.61) % 1.0))
            k += 1
        x, y = sheet_point(*uv)
        hard.append({"tv": tv, "t": ts, "uv": uv, "x": x, "y": y, "kind": kind})
    return hard


HARD_C = build_contacts()


def case_contact():
    return (CASE[0], CASE[1] + 6.0)


def big_arc_gap(a, b):
    """Les passages faits de grands arcs (une seule trousse au milieu)."""
    return any(abs(a - tau(x)) < 1e-6 for x in (10.98, 30.49, 25.86))


def build_path():
    pts = []                                         # (t, x, y_contact, dur?)
    for c in HARD_C:
        pts.append((c["t"], c["x"], c["y"], "h"))
    allc = []
    t_hook = 7.5
    for c0, c1 in zip(pts, pts[1:]):
        allc.append(c0)
        g = c1[0] - c0[0]
        if g <= 1.05:
            continue
        if big_arc_gap(c0[0], c1[0]):
            n = 1
            if c0[0] < tau(44.6) and g / 2 > 1.0:
                n = 2
        else:
            n = max(1, int(math.ceil(g / 0.98)) - 1)
            if c0[0] < tau(44.6):
                n = max(n, int(math.ceil(g / 0.97)) - 1)
            if c0[0] < t_hook:
                n = max(n, int(math.ceil(g / 0.8)) - 1)
            if c0[0] > tau(44.0):
                n = max(n, int(math.ceil(g / 0.72)) - 1)      # à la fin, des petits bonds : le tableau reste visible
        # omission avant l'issue : petits rebonds bas et lents
        if abs(c0[0] - tau(58.38)) < 1e-6:
            n = 3
        cx, cy = case_contact()
        for m in range(n):
            ts = c0[0] + g * (m + 1) / (n + 1)
            allc.append((ts, cx + (m % 2) * 6 - 3, cy, "s"))
    allc.append(pts[-1])
    # avant le premier contact dur : deux écrasements de trousse
    cx, cy = case_contact()
    allc = [(0.42, cx, cy, "s"), (1.18, cx, cy, "s")] + allc
    return sorted(allc)


class BouncePath:
    def __init__(self):
        self.cs = build_path()
        self.ts = [c[0] for c in self.cs]
        self.soft = [c[0] for c in self.cs if c[3] == "s"]
        x0, y0 = self.cs[0][1], self.cs[0][2] - R
        T0 = self.cs[0][0]
        self.start = (x0 + 330.0, y0 - 0.5 * G * T0 * T0)

    def center(self, c):
        x, y = c[1], c[2]
        if c[3] == "s":
            return (x, y - R + 18.0)           # il s'enfonce dans la trousse
        return (x, y - R)

    def pos(self, t):
        ts = self.ts
        if t <= ts[0]:
            x1, y1 = self.center(self.cs[0])
            u = t / ts[0]
            return (lerp(self.start[0], x1, u), self.start[1] + 0.5 * G * t * t)
        i = bisect.bisect_right(ts, t) - 1
        if i >= len(ts) - 1:
            x0, y0 = self.center(self.cs[-1])
            Tq = 0.75
            vy = -0.5 * G * Tq
            u = t - ts[-1]
            return (x0 + 20 * u, y0 + vy * u + 0.5 * G * u * u)
        t0, t1 = ts[i], ts[i + 1]
        (x0, y0), (x1, y1) = self.center(self.cs[i]), self.center(self.cs[i + 1])
        Tq = t1 - t0
        vx = (x1 - x0) / Tq
        vy = (y1 - y0) / Tq - 0.5 * G * Tq
        u = t - t0
        return (x0 + vx * u, y0 + vy * u + 0.5 * G * u * u)

    def apexes(self):
        out = []
        for c0, c1 in zip(self.cs, self.cs[1:]):
            (x0, y0), (x1, y1) = self.center(c0), self.center(c1)
            Tq = c1[0] - c0[0]
            vy = (y1 - y0) / Tq - 0.5 * G * Tq
            out.append((c0[0], Tq, y0 - vy * vy / (2 * G)))
        return out


# ------------------------------------------------------------------ qui copie quoi, et quand
def build_copies():
    """Pour chaque élève : la liste (temps d'apparition, uv) des ronds roses de sa feuille, et
    les fenêtres où il est penché (avec la cible de sa ligne rose)."""
    gates = {"yellow": tau(EV["yellow_start"]), "green": tau(EV["green_start"]),
             "blue": tau(EV["row2_start"]), "orange": tau(EV["row2_start"])}
    frozen = {"yellow": [(tau(8.30), tau(9.0)), (tau(39.65), tau(40.5))],
              "green": [(tau(24.05), tau(24.75)), (tau(39.65), tau(40.5))],
              "blue": [(tau(39.65), tau(40.5))],
              "orange": [(tau(24.05), tau(24.75)), (tau(34.65), tau(35.2)), (tau(39.65), tau(40.5))]}
    stop = tau(EV["pencils"])
    dots = {n: [] for n in STUDENTS}
    leans = {n: [] for n in STUDENTS}
    for n in STUDENTS:
        pending = []
        for c in HARD_C:
            if c["t"] >= stop:
                break
            pending.append(c)
            if c["t"] < gates[n] - 1e-6:
                continue
            t0 = c["t"]
            if any(a <= t0 < b for a, b in frozen[n]):
                continue
            # il se penche, la ligne rose part vers le dernier rond, puis il tape sa feuille
            slow_in = 1.0
            la = t0 + 0.30 * slow_in
            lb = t0 + 0.78 * slow_in
            leans[n].append((la, lb, c))
            # rattrapage : tous les ronds qu'il n'a pas encore, l'un après l'autre
            for m, cc in enumerate(pending):
                dots[n].append((t0 + (0.62 + 0.05 * m) * slow_in if len(pending) > 1 else t0 + 0.62 * slow_in, cc["uv"]))
            pending = []
    return dots, leans


DOTS, LEANS = build_copies()
NDOTS = len({(round(uv[0], 3), round(uv[1], 3)) for (_, uv) in DOTS["yellow"]})


# ------------------------------------------------------------------ dessin : petites briques
class Pen:
    def __init__(self, dr, S):
        self.dr, self.S = dr, S

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

    def dashed(self, a, b, fill, width, dash=22.0, gap=14.0, phase=0.0):
        (x0, y0), (x1, y1) = a, b
        d = math.hypot(x1 - x0, y1 - y0)
        if d < 1:
            return
        ux, uy = (x1 - x0) / d, (y1 - y0) / d
        s = -phase % (dash + gap)
        s -= dash + gap
        while s < d:
            p0 = max(0.0, s)
            p1 = min(d, s + dash)
            if p1 > p0:
                self.line([(x0 + ux * p0, y0 + uy * p0), (x0 + ux * p1, y0 + uy * p1)], fill, width)
            s += dash + gap

    def text(self, x, y, s, size, fill, anchor="mm", stroke=0, stroke_fill=(0, 0, 0)):
        self.dr.text((x * self.S, y * self.S), s, fill=fill, anchor=anchor, font=base.font(size * self.S),
                     stroke_width=int(stroke * self.S), stroke_fill=stroke_fill)


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def rr_pts(x0, y0, x1, y1, r, n=5):
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


def star_pts(x, y, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.46
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    return pts


# ------------------------------------------------------------------ la simulation
class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        BANK["path"] = cfg.get("voice_bank")
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.outcome = None
        self.B = BouncePath()
        self.hi = 0
        self.lines = [(tt, txt, f"l{i}") for i, (tt, txt) in enumerate(zip(LINE_T, LINES))]
        self.replies = []

    def step(self, dt):
        t_frame = self.t                    # l'instant de la frame que base enregistre pour ces événements
        self.t += dt
        evs = []
        while self.hi < len(HARD) and HARD[self.hi] <= t_frame + 1e-9:
            evs.append(("hit", "desk"))
            self.hi += 1
        if not self.payoff and t_frame >= ISSUE:
            self.payoff = True
            self.outcome = "TOP OF THE CLASS"
            evs.append(("payoff", self.outcome))
        if self.t >= END_T - 0.05:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def hero_mood(self):
        return None

    def draw(self, dr, snap, t, S):
        Drawer.get(self).draw(dr, t, S)


# ------------------------------------------------------------------ le surveillant : où il est
def proctor_state(s):
    """s = temps de scène. Renvoie dict : x, head_y, mode ('seat', 'stand', 'walk'), layer ('back' ou 'mid')."""
    seat = (790.0, 752.0)
    stand_desk = (790.0, 596.0)
    behind = (470.0, 560.0)
    board_a = (500.0, 590.0)     # devant le milieu du tableau (épingler la copie de Bounce)
    board_r = (870.0, 590.0)     # à droite du tableau
    board_m = (700.0, 590.0)
    w0, w1 = T("walk")
    tb0, tb1 = T("to_board")
    b0, b1 = T("to_board2")
    ul0, ul1 = T("underline")
    sr0, sr1 = T("step_r")
    up0, up1 = T("up")
    sb0, sb1 = T("step_back")
    q = T("quiet")
    if s < q:
        x, y = seat
        rise = 0.0
        if s >= q - 0.25:
            rise = smooth((s - (q - 0.25)) / 0.25)
            x, y = seat[0], lerp(seat[1], stand_desk[1], rise)
            return {"x": x, "hy": y, "mode": "stand", "layer": "back"}
        return {"x": x, "hy": y, "mode": "seat", "layer": "back"}
    if s < w0:
        return {"x": stand_desk[0], "hy": stand_desk[1], "mode": "stand", "layer": "back"}
    if s < w1:
        x, y = path(s, [(w0, stand_desk), (w0 + 0.5, (690.0, 575.0)), (w1, behind)])
        return {"x": x, "hy": y, "mode": "walk", "layer": "back" if s < w0 + 0.55 else "mid"}
    if s < tb0:
        return {"x": behind[0], "hy": behind[1], "mode": "stand", "layer": "mid"}
    if s < tb1:
        x, y = path(s, [(tb0, behind), (tb1, board_a)])
        return {"x": x, "hy": y, "mode": "walk", "layer": "mid" if s < tb0 + 0.3 else "back"}
    if s < ul0 - 0.25:
        return {"x": board_a[0], "hy": board_a[1], "mode": "stand", "layer": "back"}
    if s < ul0:
        x, y = path(s, [(ul0 - 0.25, board_a), (ul0, board_r)])
        return {"x": x, "hy": y, "mode": "walk", "layer": "back"}
    if s < b0:
        return {"x": board_r[0], "hy": board_r[1], "mode": "stand", "layer": "back"}
    if s < b1:
        x = lerp(board_r[0], 600.0, smooth((s - b0) / (b1 - b0)))
        return {"x": x, "hy": board_r[1], "mode": "walk", "layer": "back"}
    if s < sr0:
        return {"x": 600.0, "hy": board_m[1], "mode": "stand", "layer": "back"}
    if s < sr1:
        x = lerp(600.0, board_r[0], smooth((s - sr0) / (sr1 - sr0)))
        return {"x": x, "hy": board_r[1], "mode": "walk", "layer": "back"}
    if s < up0:
        return {"x": board_r[0], "hy": board_r[1], "mode": "stand", "layer": "back"}
    if s < up1:
        x = lerp(board_r[0], 600.0, smooth((s - up0) / (up1 - up0)))
        return {"x": x, "hy": board_r[1], "mode": "walk", "layer": "back"}
    if s < sb0:
        return {"x": 600.0, "hy": board_r[1], "mode": "stand", "layer": "back"}
    if s < sb1:
        x = lerp(600.0, 870.0, smooth((s - sb0) / (sb1 - sb0)))
        return {"x": x, "hy": board_r[1], "mode": "walk", "layer": "back"}
    return {"x": 870.0, "hy": board_r[1], "mode": "stand", "layer": "back"}


# ------------------------------------------------------------------ le dessin
class Drawer:
    _inst = {}

    @classmethod
    def get(cls, sim):
        if id(sim) not in cls._inst:
            cls._inst[id(sim)] = cls(sim)
        return cls._inst[id(sim)]

    def __init__(self, sim):
        self.sim = sim
        self.B = sim.B
        self.hard_t = [c["t"] for c in HARD_C]

    # ---- temps utiles
    def last_hard(self, s):
        i = bisect.bisect_right(self.hard_t, s) - 1
        return HARD_C[i] if i >= 0 else None

    # ---- décor
    def wall(self, pen, s):
        pen.rect(0, 0, W, WALL_BOT, WALL)
        pen.rect(0, 0, W, 60, WALL_D)
        pen.rect(0, WALL_BOT, W, H, FLOOR)
        for kx in range(14):
            y = WALL_BOT + 20 + (kx ** 1.45) * 26
            if y < H:
                pen.line([(0, y), (W, y)], FLOOR_L, 2)
        for kx in range(-6, 8):
            pen.line([(540 + kx * 60, WALL_BOT), (540 + kx * 220, H)], FLOOR_L, 2)
        pen.rect(0, WALL_BOT - 12, W, WALL_BOT, (40, 42, 64))

    def floor_props(self, pen):
        # chaises, cartables : du décor sous la scène
        for (x, w) in ((186.0, 160.0), (545.0, 230.0), (848.0, 120.0)):
            pen.rect(x - w / 2, 1440, x + w / 2, 1466, (72, 72, 90))
            for sx in (-1, 1):
                pen.rect(x + sx * (w / 2 - 10) - 7, 1466, x + sx * (w / 2 - 10) + 7, 1660, (72, 72, 90))
        for (x, col) in ((430.0, (96, 70, 120)), (700.0, (70, 100, 96)), (110.0, (110, 80, 60))):
            pen.rrect(x - 52, 1560, x + 52, 1672, 18, col)
            pen.rrect(x - 30, 1530, x + 30, 1566, 12, mix(col, (0, 0, 0), 0.3))

    def legs(self, pen, nm, p, s):
        """Les jambes d'un élève du premier rang, sous sa table (elles suivent son corps)."""
        st = STUDENTS[nm]
        col = mix(st["col"], (0, 0, 0), 0.25)
        x = st["x"]
        hop = -p["dy"] * 0.6
        for sx in (-1, 1):
            lx = x + sx * 26
            fy = 1612 - max(0.0, hop) * (1.0 if sx < 0 else 0.6)
            pen.rect(lx - 13, 1405, lx + 13, fy, col)
            pen.rrect(lx - 22 + sx * 6, fy - 4, lx + 24 + sx * 6, fy + 20, 9, (36, 34, 44))

    def board(self, pen, s, t):
        x0, y0, x1, y1 = BOARD
        pen.rect(x0 - 14, y0 - 14, x1 + 14, y1 + 14, WOOD_D)
        pen.rect(x0, y0, x1, y1, BOARD_G)
        pen.rect(x0 - 14, y1, x1 + 14, y1 + 14, WOOD)
        pen.text(SILENCE_XY[0], SILENCE_XY[1], "SILENCE.", 50, mix(BOARD_G, CHALK, 0.82))
        # la règle : petite et pâle, puis soulignée et éclairée
        ul0, ul1 = T("underline")
        lit = smooth((s - ul0) / (ul1 - ul0))
        rule_col = mix(BOARD_G, CHALK, 0.36 + 0.64 * lit)
        size = 28 + 2 * lit
        pen.text(RULE_XY[0], RULE_XY[1], "WRONG ANSWER = −1", size, rule_col)
        if s >= ul0:
            u = smooth((s - ul0) / (ul1 - ul0))
            xa, xb = RULE_XY[0] + 140, RULE_XY[0] + 190
            pen.line([(xa, RULE_XY[1] + 25), (lerp(xa, xb, u), RULE_XY[1] + 25)], CHALK, 5)
        # les copies épinglées
        if s >= T("pin0"):
            self.pinned(pen, PIN0, None, s, zero=True)
        if s >= T("pin1"):
            self.pinned(pen, PIN1, "green", s, zero=False)
        # les scores
        for i, nm in enumerate(ORDER_M12):
            tw = tau(EV["m12"][i])
            if s >= tw:
                x, y = M12[i]
                self.chalk_fig(pen, nm, x - 26, y)
                pen.text(x + 44, y + 2, f"−{NDOTS}", 40, CHALK)

    def chalk_fig(self, pen, nm, x, y):
        st = STUDENTS[nm]
        col = mix(st["col"], CHALK, 0.25)
        if st["kind"] == "tall":
            pen.rrect(x - 9, y - 12, x + 9, y + 20, 4, col)
            pen.circ(x, y - 19, 8, col)
        elif st["kind"] == "round":
            pen.ell(x, y + 5, 15, 15, fill=col)
            pen.circ(x, y - 16, 8, col)
        else:
            pen.rrect(x - 14, y - 9, x + 14, y + 20, 4, col)
            pen.circ(x, y - 17, 8, col)

    def sheet_upright(self, pen, box, dots, s, scale=1.0):
        x0, y0, x1, y1 = box
        pen.rect(x0, y0, x1, y1, PAPER)
        w, h = x1 - x0, y1 - y0
        pen.rect(x0 + 8, y0 + 8, x0 + w * 0.55, y0 + 14, (196, 196, 204))
        for j in range(NROW):
            for i in range(NCOL):
                u, v = grid_uv(i, j)
                pen.ell(x0 + u * w, y0 + v * h, 9 * scale, 9 * scale, outline=BUBBLE, width=2)
        pts = []
        for (ta, uv) in dots:
            if ta > s:
                continue
            px, py = x0 + uv[0] * w, y0 + uv[1] * h
            pen.circ(px, py, 13 * scale, PINK)
            pts.append((px, py))
        return pts

    def pinned(self, pen, box, who, s, zero):
        x0, y0, x1, y1 = box
        if who is None:
            dots = [(0.0, c["uv"]) for c in HARD_C if c["kind"] == "sheet"]
        else:
            dots = [(0.0, uv) for (_, uv) in DOTS[who]]
        pts = self.sheet_upright(pen, box, dots, s)
        pen.circ((x0 + x1) / 2, y0 + 4, 7, (200, 60, 60))
        if zero:
            pen.ell((x0 + x1) / 2, (y0 + y1) / 2 + 6, 70, 84, outline=RED, width=14)
            if s >= T("star"):
                u = smooth((s - T("star")) / 0.22)
                pen.poly(star_pts(x1 - 20, y0 + 26, 34 + 40 * u), GOLD)
        else:
            xa, xb = T("xs")
            n = len(pts)
            for m, (px, py) in enumerate(pts):
                tm = xa + (xb - xa) * m / max(1, n)
                if s >= tm:
                    pen.line([(px - 12, py - 12), (px + 12, py + 12)], RED, 5)
                    pen.line([(px - 12, py + 12), (px + 12, py - 12)], RED, 5)

    def proctor_desk(self, pen):
        x0, top, x1, bot = PDESK
        pen.rect(x0 - 8, top, x1 + 8, top + 16, WOOD)
        pen.rect(x0, top + 16, x1, bot, WOOD_D)

    # ---- la table de Bounce, sa copie, sa trousse
    def bounce_desk(self, pen, s):
        x0, top, x1, bot = DESK
        pen.poly([(x0 + 16, top), (x1 - 16, top), (x1, bot), (x0, bot)], WOOD)
        pen.rect(x0, bot, x1, bot + 270, WOOD_E)
        pen.rect(x0, bot, x1, bot + 10, WOOD_D)
        for lx in (x0 + 20, x1 - 32):
            pen.rect(lx, bot + 270, lx + 12, bot + 540, (62, 54, 62))
        snatch = T("snatch")
        if s < snatch:
            self.flat_sheet(pen, s)
        # les ronds sur le bois nu
        for c in HARD_C:
            if c["kind"] == "wood" and c["t"] <= s and self.dot_visible(c, s):
                pen.ell(c["x"], c["y"], 15, 11, fill=PINK)
        self.case(pen, s)

    def dot_visible(self, c, s):
        # le rond apparaît dès que Bounce s'est un peu décollé (il le couvre au contact)
        return s >= c["t"] + 0.02

    def flat_sheet(self, pen, s):
        bl, by, br, _, fl, fy, fr, _ = SHEET
        pen.poly([(bl, by), (br, by), (fr, fy), (fl, fy)], PAPER)
        for j in range(NROW):
            for i in range(NCOL):
                x, y = sheet_point(*grid_uv(i, j))
                pen.ell(x, y, 9.5, 7.2, outline=BUBBLE, width=2)
        for c in HARD_C:
            if c["kind"] == "sheet" and c["t"] <= s:
                pen.ell(c["x"], c["y"], 16, 12, fill=PINK)

    def case(self, pen, s):
        x, top, w, h = CASE
        sq = 0.0
        for ts in self.B.soft:
            u = s - ts
            if -0.06 <= u <= 0.3:
                sq = max(sq, 1.0 - abs(u - 0.04) / 0.26 if u > 0.04 else 1.0 + u / 0.1)
        sq = clamp01(sq)
        hh = h * (1 - 0.5 * sq)
        ww = w * (1 + 0.24 * sq)
        bot = top + h
        pen.rrect(x - ww / 2, bot - hh, x + ww / 2, bot, hh / 2, CASE_C)
        pen.line([(x - ww / 2 + 12, bot - hh * 0.55), (x + ww / 2 - 12, bot - hh * 0.55)], (70, 130, 180), 3)
        pen.circ(x + ww / 2 - 14, bot - hh * 0.55, 5, (230, 230, 240))

    # ---- élèves
    def pose(self, nm, s):
        st = STUDENTS[nm]
        p = {"x": st["x"], "dy": 0.0, "lean": 0.0, "slump": 0.0, "raise": 0.0, "target": None, "tap": 0.0,
             "pencil": None, "stiff": 0.0}
        side = st["side"]
        crowd0, crowd1 = T("crowd")
        pen_t = T("pencils")
        back0, back1 = T("back_seat")
        crowd = smooth((s - crowd0) / (crowd1 - crowd0)) * (1 - smooth((s - back0) / (back1 - back0)))
        # sursauts aux contacts (pas au tout premier : seul le surveillant se réveille)
        for c in HARD_C[1:]:
            if c["t"] > s:
                break
            u = (s - c["t"]) / 0.3
            if 0 <= u <= 1 and c["t"] < pen_t:
                p["dy"] -= 12.0 * st["k"] * bump(u)
        # penché pour copier
        for (la, lb, c) in LEANS[nm]:
            if la - 0.12 <= s <= lb + 0.25:
                lk = pulse(s, la - 0.12, 0.12, lb - la, 0.25)
                p["lean"] = max(p["lean"], lk)
                if la <= s <= lb:
                    p["target"] = (c["x"], c["y"])
                if lb - 0.12 <= s <= lb + 0.05:
                    p["tap"] = 1.0
        lean_amt = {"yellow": 0.34, "green": 0.30, "blue": 0.30, "orange": 0.30}[nm]
        p["lean"] = side * lean_amt * p["lean"]
        # gags
        if nm == "green":
            turn = pulse(s, T("green_turn") + 0.1, 0.2, 0.4, 0.3)
            p["lean"] -= 0.12 * turn
            if T("pencil_g") <= s < T("pencil_g") + 0.8:
                p["pencil"] = (s - T("pencil_g")) / 0.8
        if nm == "yellow":
            if T("pencil_y") <= s < T("pencil_y") + 0.8:
                p["pencil"] = (s - T("pencil_y")) / 0.8
            f = pulse(s, T("corner") + 0.02, 0.08, 0.2, 0.3)
            p["dy"] += 26 * f
            p["lean"] -= 0.18 * f
        if nm == "blue":
            p["dy"] -= 26 * pulse(s, T("blue_peek") + 0.2, 0.3, 0.5, 0.4)
            p["lean"] += 0.14 * pulse(s, T("blue_peek") + 0.2, 0.3, 0.5, 0.4)
        if nm == "orange":
            p["dy"] -= 30 * pulse(s, T("orange_neck") + 0.2, 0.3, 0.5, 0.4)
            tp = pulse(s, T("topple") + 0.05, 0.15, 0.25, 0.35)
            p["lean"] -= 0.35 * tp
        if nm in ("blue", "orange"):
            rise = smooth((s - T("row2_rise") - 0.2) / 0.5)
            if s < T("pencils"):
                p["dy"] -= 44 * rise
        # la grappe autour de la copie de Bounce
        if crowd > 0:
            if nm == "yellow":
                p["x"] = lerp(st["x"], 250.0, crowd)
                p["lean"] += 0.22 * crowd
            elif nm == "green":
                p["x"] = lerp(st["x"], 830.0, crowd)
                p["lean"] -= 0.22 * crowd
            elif nm == "blue":
                p["x"] = lerp(st["x"], 330.0, crowd)
                p["dy"] -= 70 * crowd
            elif nm == "orange":
                p["x"] = lerp(st["x"], 616.0, crowd)
                p["dy"] -= 70 * crowd
        # statues (balayage 3) : raides
        for (a, b) in ((T("sweep1"), T("sweep1") + 0.7), (T("sweep2"), T("sweep2") + 0.7), (T("sweep3"), T("sweep3") + 0.9)):
            if a - 0.05 <= s < b:
                who = {T("sweep1"): ("yellow",), T("sweep2"): ("green", "orange")}.get(a, tuple(STUDENTS))
                if nm in who:
                    p["lean"] *= 0.0
                    p["stiff"] = 1.0
        # crayons levés pour rendre les feuilles
        if nm == "green" and T("raise") <= s < T("take") + 0.3:
            p["raise"] = pulse(s, T("raise"), 0.25, T("take") - T("raise") - 0.25, 0.3)
        # espoir, puis retombée
        hope = pulse(s, T("hope") + 0.1, 0.3, (T("up")[0] - T("hope")) - 0.4, 0.25)
        if s >= T("xs")[0]:
            m12_t = {"yellow": tau(EV["m12"][0]), "green": tau(EV["m12"][1]), "blue": tau(EV["m12"][2]),
                     "orange": tau(EV["m12"][3])}[nm]
            sl = smooth((s - m12_t) / 0.35)
            p["slump"] = sl * (1 - hope)
            p["dy"] -= 18 * hope
        # le dernier geste : ils se penchent tous vers le dernier rond
        fin = T("final")
        if s >= fin + 0.08:
            k = smooth((s - fin - 0.08) / 0.22)
            p["lean"] = side * 0.36 * k
            p["slump"] *= (1 - k)
            p["target"] = (HARD_C[-1]["x"], HARD_C[-1]["y"])
            p["tap"] = 0.0
        return p

    def own_sheet(self, pen, nm, s, x, y, k):
        """La feuille d'un élève sur sa table (petite, en perspective) avec les ronds recopiés."""
        if nm == "green" and s >= T("raise"):
            return                                   # il la tend au surveillant
        w0, w1, d = 120 * k, 132 * k, 66 * k
        pts = [(x - w0 / 2, y - d), (x + w0 / 2, y - d), (x + w1 / 2, y), (x - w1 / 2, y)]
        pen.poly(pts, PAPER)
        for (ta, uv) in DOTS[nm]:
            if ta <= s:
                xx = lerp(x - lerp(w0, w1, uv[1]) / 2, x + lerp(w0, w1, uv[1]) / 2, uv[0])
                yy = y - d + d * uv[1]
                pen.ell(xx, yy, 6.5 * k, 5 * k, fill=PINK)

    def student(self, pen, nm, s, p):
        st = STUDENTS[nm]
        k = st["k"]
        col = st["col"]
        x = p["x"]
        base_y = st["base"] + p["dy"]
        if st["kind"] == "sq":
            bw, bh, hr = 140 * k, 138 * k, 40 * k
        elif st["kind"] == "tall":
            bw, bh, hr = 92 * k, 190 * k, 35 * k
        else:
            bw, bh, hr = 132 * k, 122 * k, 40 * k
        sy = 1 - 0.3 * p["slump"]
        top = base_y - bh * sy
        a = p["lean"]
        rad = bw * 0.45 if st["kind"] == "round" else min(bw, bh) * 0.2
        body = rot(rr_pts(x - bw / 2, top, x + bw / 2, base_y, rad), x, base_y, a)
        pen.poly(body, col)
        hx = x + math.sin(a) * (bh * sy + hr * 0.9)
        hy = base_y - math.cos(a) * (bh * sy + hr * 0.9)
        if p["slump"] > 0:
            hy += 18 * k * p["slump"]
        pen.circ(hx, hy, hr, mix(col, (255, 255, 255), 0.16))
        # bras et crayon
        side = st["side"]
        ax = x + side * bw * 0.38 + math.sin(a) * bh * 0.4
        ay = base_y - bh * 0.42 * sy
        if p["raise"] > 0:
            ex, ey = x + side * 20 * k, top - 110 * k * p["raise"]
            pen.line([(ax, ay), (ex, ey)], mix(col, (0, 0, 0), 0.2), 16 * k)
            if s < T("take"):
                pen.rect(ex - 34 * k, ey - 46 * k, ex + 34 * k, ey, PAPER)
                for (ta, uv) in DOTS[nm]:
                    pen.circ(ex - 34 * k + uv[0] * 68 * k, ey - 46 * k + uv[1] * 46 * k, 4 * k, PINK)
        else:
            tapy = 8 * k * math.sin(s * 40) if p["tap"] else 0.0
            ex, ey = ax + side * 34 * k, ay + 46 * k + tapy
            pen.line([(ax, ay), (ex, ey)], mix(col, (0, 0, 0), 0.2), 16 * k)
            if p["pencil"] is not None:
                u = p["pencil"]
                px, py = ex + side * 20 * u, ey - 150 * k * bump(u) - 10
                ang = u * 9.0
                pen.line([(px - 18 * math.cos(ang), py - 18 * math.sin(ang)), (px + 18 * math.cos(ang), py + 18 * math.sin(ang))],
                         (250, 210, 90), 6)
            else:
                pen.line([(ex, ey), (ex + side * 10 * k, ey - 26 * k)], (250, 210, 90), 6 * k)
        return (hx, hy, hr)

    def small_desk(self, pen, nm, s, k):
        st = STUDENTS[nm]
        x, y = st["x"], st["base"]
        w = 180 * k
        d = 120 * k if k == 1.0 else 40 * k
        pen.poly([(x - w / 2 + 12 * k, y), (x + w / 2 - 12 * k, y), (x + w / 2, y + d), (x - w / 2, y + d)], WOOD)
        pen.rect(x - w / 2, y + d, x + w / 2, y + d + (290 if k == 1.0 else 150) * k, WOOD_E)
        pen.rect(x - w / 2, y + d, x + w / 2, y + d + 9 * k, WOOD_D)
        self.own_sheet(pen, nm, s, x, y + d - 12 * k, k)

    # ---- le surveillant
    def proctor(self, pen, s, P):
        x, hy, mode = P["x"], P["hy"], P["mode"]
        hr = 46.0
        bw = 130.0
        top = hy + hr * 0.95
        bot = top + 330.0
        bob = abs(math.sin(s * 9.0)) * 8 if mode == "walk" else 0.0
        top -= bob
        hy -= bob
        tilt = 0.0
        n0, n1 = T("nod")
        if n0 <= s < n1:
            tilt = 0.0
            hy += 12 * bump((s - n0) / (n1 - n0))
        jerk = pulse(s, T("nose") + 0.25, 0.08, 0.2, 0.3)
        hy -= 14 * jerk
        pen.poly(rr_pts(x - bw / 2, top, x + bw / 2, bot, 36), SUIT)
        cx, cy = x, top + 4
        pen.poly([(cx - 22, cy), (cx + 22, cy), (cx, cy + 52)], (232, 232, 238))
        pen.poly([(cx - 7, cy + 10), (cx + 7, cy + 10), (cx + 11, cy + 96), (cx, cy + 108), (cx - 11, cy + 96)],
                 (200, 50, 56))
        pen.circ(x, hy, hr, SKIN)
        self.phead = (x, hy)
        self.proctor_arms(pen, s, P, x, top, bw)

    def arm(self, pen, sx, sy, ex, ey, hand=None):
        d = math.hypot(ex - sx, ey - sy)
        if hand == "pen" and d > 175:
            # trop loin pour le bras : il prend sa longue règle, au bout rouge
            ux, uy = (ex - sx) / d, (ey - sy) / d
            hx, hy = sx + ux * 160, sy + uy * 160
            pen.line([(sx, sy), (hx, hy)], (44, 50, 82), 24)
            pen.line([(hx, hy), (ex - ux * 18, ey - uy * 18)], (176, 132, 80), 8)
            pen.line([(ex - ux * 18, ey - uy * 18), (ex, ey)], RED, 9)
            pen.circ(hx, hy, 14, SKIN)
            return
        pen.line([(sx, sy), (ex, ey)], (44, 50, 82), 24)
        pen.circ(ex, ey, 14, SKIN)
        if hand == "finger":
            pen.line([(ex, ey - 8), (ex, ey - 40)], SKIN, 9)
        elif hand == "two":
            pen.line([(ex - 6, ey - 8), (ex - 12, ey - 40)], SKIN, 8)
            pen.line([(ex + 6, ey - 8), (ex + 12, ey - 40)], SKIN, 8)
        elif hand == "pen":
            pen.line([(ex, ey), (ex - 22, ey - 14)], RED, 8)
        elif hand == "point":
            pen.line([(ex, ey), (ex - 40, ey + 6)], SKIN, 9)

    def pen_target(self, s):
        """Où va le stylo rouge (ou la craie), au tableau."""
        ul0, ul1 = T("underline")
        if ul0 <= s < ul1 + 0.2:
            u = smooth((s - ul0) / (ul1 - ul0))
            return (RULE_XY[0] + 140 + 50 * u, RULE_XY[1] + 25)
        xa, xb = T("xs")
        if xa - 0.15 <= s < xb + 0.05:
            pts = self.pin1_pts()
            u = clamp01((s - xa) / (xb - xa))
            i = min(len(pts) - 1, int(u * len(pts)))
            return pts[i]
        m = EV["m12"]
        for i in range(4):
            tw = tau(m[i])
            if tw - 0.18 <= s < tw + 0.17:
                return (M12[i][0] + 40, M12[i][1])
        h0, h1 = T("hover")
        if h0 <= s < h1:
            u = (s - h0) / (h1 - h0)
            # il hésite : sur Yellow, puis Green, puis Blue, sans écrire
            seq = [0, 0, 1, 1, 2, 1]
            f = u * (len(seq) - 1)
            i = int(f)
            a = M12[seq[i]]
            b = M12[seq[min(len(seq) - 1, i + 1)]]
            v = smooth(f - i)
            return (lerp(a[0], b[0], v) + 70, lerp(a[1], b[1], v) - 6 + 6 * math.sin(s * 7))
        up0, up1 = T("up")
        st = T("star")
        if up0 <= s < st + 0.4:
            u = smooth((s - up0) / (up1 - up0))
            a = (M12[1][0] + 70, M12[1][1])
            b = (PIN0[2] - 20, PIN0[1] + 26)
            if s < st:
                b = (b[0] + 4 * math.sin(s * 5), b[1] - 30)
            return (lerp(a[0], b[0], u), lerp(a[1], b[1], u))
        return None

    def pin1_pts(self):
        x0, y0, x1, y1 = PIN1
        seen, out = set(), []
        for (_, uv) in DOTS["green"]:
            key = (round(uv[0], 3), round(uv[1], 3))
            if key not in seen:
                seen.add(key)
                out.append((x0 + uv[0] * (x1 - x0), y0 + uv[1] * (y1 - y0)))
        return out

    def proctor_arms(self, pen, s, P, x, top, bw):
        lsh = (x - bw / 2 + 12, top + 34)
        rsh = (x + bw / 2 - 12, top + 34)
        down_l = (lsh[0] - 6, lsh[1] + 160)
        down_r = (rsh[0] + 6, rsh[1] + 160)
        L, Rr, lh, rh = down_l, down_r, None, None
        wake = T("wake")
        if s < wake + 0.25:
            # assis, il lit un livre devant son visage ; il le laisse tomber au premier « Bounce »
            drop = smooth((s - wake) / 0.25)
            by = top - 20 + 90 * drop
            L = (x - 44, by + 40)
            Rr = (x + 44, by + 40)
            pen.rect(x - 64, by - 50, x + 64, by + 40, (170, 60, 64))
            pen.rect(x - 4, by - 50, x + 4, by + 40, (120, 40, 44))
        hu = pulse(s, T("hush") - 0.1, 0.2, 0.9, 0.3)
        if hu > 0:
            Rr = (lerp(down_r[0], rsh[0] - 40, hu), lerp(down_r[1], top - 60, hu))
            rh = "finger"
        qu = pulse(s, T("quiet") - 0.05, 0.2, 1.2, 0.4)
        if qu > 0:
            bx, by = self.B.pos(s)
            d = math.hypot(bx - lsh[0], by - lsh[1]) or 1
            L = (lerp(down_l[0], lsh[0] + (bx - lsh[0]) / d * 190, qu), lerp(down_l[1], lsh[1] + (by - lsh[1]) / d * 190, qu))
            lh = "finger"
        t0, t1 = T("two")
        tw = pulse(s, t0, 0.25, (t1 - t0) - 0.5, 0.25)
        if tw > 0:
            Rr = (lerp(down_r[0], rsh[0] + 20, tw), lerp(down_r[1], top - 70, tw))
            rh = "two"
        # la copie confisquée, tenue devant lui, puis épinglée
        sn = T("snatch")
        if sn <= s < T("pin0"):
            u = smooth((s - sn) / 0.2)
            hx = x
            hy0 = top + 120
            if u < 1:
                cx0, cy0 = (DESK[0] + DESK[2]) / 2 - 80, DESK[1] + 60
                hx, hy0 = lerp(cx0, x, u), lerp(cy0, hy0, u)
            pv = T("pin0")
            w_up = smooth((s - (pv - 0.55)) / 0.5)
            hx = lerp(hx, (PIN0[0] + PIN0[2]) / 2, w_up)
            hy0 = lerp(hy0, (PIN0[1] + PIN0[3]) / 2, w_up)
            box = (hx - 110, hy0 - 105, hx + 110, hy0 + 105)
            dots = [(0.0, c["uv"]) for c in HARD_C if c["kind"] == "sheet"]
            self.sheet_upright(pen, box, dots, s)
            if s >= T("zero_write"):
                v = clamp01((s - T("zero_write")) / 0.3)
                pts = [(hx + 70 * math.sin(2 * math.pi * a), hy0 + 6 - 84 * math.cos(2 * math.pi * a))
                       for a in np.linspace(0, v, 30)]
                if len(pts) > 1:
                    pen.line(pts, RED, 14)
                Rr = pts[-1] if pts else Rr
                rh = "pen"
            L = (box[0], hy0)
            if rh is None:
                Rr = (box[2], hy0)
        tgt = self.pen_target(s)
        if tgt is not None:
            d = math.hypot(tgt[0] - lsh[0], tgt[1] - lsh[1])
            sh = lsh if abs(tgt[0] - lsh[0]) < abs(tgt[0] - rsh[0]) else rsh
            if sh is lsh:
                L, lh = tgt, "pen"
            else:
                Rr, rh = tgt, "pen"
        # il épingle
        for key, box in (("pin0", PIN0), ("pin1", PIN1)):
            pt = T(key)
            if pt - 0.3 <= s < pt + 0.15:
                L, lh = ((box[0] + box[2]) / 2, box[1] + 4), None
        tk = T("take")
        if tk - 0.25 <= s < tk:
            Rr = (rsh[0] + 10, rsh[1] + 200)
        if tk <= s < T("pin1"):
            # la feuille de Green, tenue devant lui : il la regarde, puis regarde la copie de Bounce
            pv = T("pin1")
            u = smooth((s - (pv - 1.0)) / 0.7)
            cx, cy = lerp(x - 10, (PIN1[0] + PIN1[2]) / 2, u), lerp(top + 150, (PIN1[1] + PIN1[3]) / 2, u)
            box = (cx - 110, cy - 105, cx + 110, cy + 105)
            self.sheet_upright(pen, box, [(0.0, uv) for (_, uv) in DOTS["green"]], s)
            L, lh = (box[0] + 10, cy + 60), None
            Rr, rh = (box[2] - 10, cy + 60), None
        self.arm(pen, lsh[0], lsh[1], L[0], L[1], lh)
        self.arm(pen, rsh[0], rsh[1], Rr[0], Rr[1], rh)

    # ---- les regards
    def gaze_target(self, s):
        """Où regarde le surveillant (None : il lit)."""
        if s < T("wake"):
            return None
        bx, by = self.B.pos(s)
        tgt = (bx, by)
        hd = getattr(self, "heads", {})
        sw = [(T("sweep1"), 0.75, ["yellow"]), (T("sweep2"), 0.75, ["green", "orange"]),
              (T("sweep3"), 1.0, ["yellow", "blue", "orange", "green"])]
        for (a, d, who) in sw:
            if a + 0.12 <= s < a + 0.12 + d:
                u = (s - a - 0.12) / d
                pts = [hd[w][:2] for w in who if w in hd]
                if not pts:
                    break
                if len(pts) == 1:
                    q = bump(u)
                    return (lerp(bx, pts[0][0], q), lerp(by, pts[0][1] - 40, q))
                seq = [(bx, by)] + [(p[0], p[1] - 40) for p in pts] + [(bx, by)]
                f = u * (len(seq) - 1)
                i = min(len(seq) - 2, int(f))
                v = smooth(f - i)
                return (lerp(seq[i][0], seq[i + 1][0], v), lerp(seq[i][1], seq[i + 1][1], v))
        n0 = T("take")
        if n0 <= s < T("xs")[0]:
            # la feuille de Green, puis la copie de Bounce, de l'une à l'autre
            a = ((PIN0[0] + PIN0[2]) / 2, (PIN0[1] + PIN0[3]) / 2)
            if s < T("pin1") - 1.0:
                P = proctor_state(s)
                b = (P["x"] - 10, P["hy"] + 200)
                u = (s - n0) / max(0.1, (T("pin1") - 1.0 - n0))
                q = 0.5 - 0.5 * math.cos(u * 4 * math.pi)
            else:
                b = ((PIN1[0] + PIN1[2]) / 2, (PIN1[1] + PIN1[3]) / 2)
                u = (s - (T("pin1") - 1.0)) / (T("xs")[0] - T("pin1") + 1.0)
                q = 0.5 - 0.5 * math.cos(u * 3 * math.pi)
            return (lerp(b[0], a[0], q), lerp(b[1], a[1], q))
        tg = self.pen_target(s)
        if tg is not None and T("xs")[0] - 0.2 <= s < T("star") + 0.3:
            return tg
        if T("pin0") - 0.3 <= s < T("underline")[1] + 0.2:
            tg = self.pen_target(s)
            if tg is not None:
                return tg
        st = T("star")
        if st + 0.3 <= s < st + 0.8:
            return ((PIN0[0] + PIN0[2]) / 2, PIN0[1] + 40)
        return tgt

    def draw_gaze(self, pen, s):
        tgt = self.gaze_target(s)
        if tgt is None or not getattr(self, "phead", None):
            return
        hx, hy = self.phead
        tx, ty = tgt
        d = math.hypot(tx - hx, ty - hy)
        if d < 60:
            return
        ux, uy = (tx - hx) / d, (ty - hy) / d
        a = (hx + ux * 52, hy + uy * 52)
        bx, by = self.B.pos(s)
        stop = R * 1.08 if math.hypot(tx - bx, ty - by) < 5 else 14
        b = (tx - ux * stop, ty - uy * stop)
        grow = smooth((s - T("wake")) / 0.25)
        b = (lerp(a[0], b[0], grow), lerp(a[1], b[1], grow))
        pen.dashed(a, b, GREY_LINE, 9, 24, 15, phase=s * 60)

    def draw_copy_lines(self, pen, s, heads):
        for nm in STUDENTS:
            p = self.poses[nm]
            if p["target"] is None or nm not in heads:
                continue
            hx, hy, hr = heads[nm]
            tx, ty = p["target"]
            d = math.hypot(tx - hx, ty - hy)
            if d < 40:
                continue
            ux, uy = (tx - hx) / d, (ty - hy) / d
            a = (hx + ux * (hr + 6), hy + uy * (hr + 6))
            b = (tx - ux * 18, ty - uy * 18)
            pen.dashed(a, b, (255, 120, 225), 8, 18, 11, phase=s * 80)

    # ---- sous-titres
    def subtitle(self, pen, t):
        for (lt, txt) in zip(LINE_T, LINES):
            nw = len(txt.split())
            dur = max(0.5 + 0.3 * nw + 0.1, {0: 0.54, 1: 0.56, 2: 1.07, 3: 1.08, 4: 1.14}[LINE_T.index(lt)] + 0.2)
            if lt <= t < lt + dur:
                s = txt.upper()
                f = base.font(64 * pen.S)
                bb = f.getbbox(s)
                w = (bb[2] - bb[0]) / pen.S
                pen.rrect(540 - w / 2 - 26, SUB_Y - 46, 540 + w / 2 + 26, SUB_Y + 42, 14, (12, 12, 18))
                pen.text(540, SUB_Y, s, 64, (255, 255, 255), stroke=3, stroke_fill=(0, 0, 0))
                return

    # ---- tout
    def draw(self, dr, t, S):
        pen = Pen(dr, S)
        s = tau(t)
        self.wall(pen, s)
        self.floor_props(pen)
        self.board(pen, s, t)
        P = proctor_state(s)
        self.poses = {nm: self.pose(nm, s) for nm in STUDENTS}
        heads = {}
        self.phead = None
        if P["layer"] == "back":
            self.proctor(pen, s, P)
        self.proctor_desk(pen)
        for nm in ("blue", "orange"):
            heads[nm] = self.student(pen, nm, s, self.poses[nm])
            self.small_desk(pen, nm, s, STUDENTS[nm]["k"])
        if P["layer"] == "mid":
            self.proctor(pen, s, P)
        for nm in ("yellow", "green"):
            self.legs(pen, nm, self.poses[nm], s)
            heads[nm] = self.student(pen, nm, s, self.poses[nm])
            self.small_desk(pen, nm, s, 1.0)
        self.bounce_desk(pen, s)
        self.heads = heads
        self.draw_copy_lines(pen, s, heads)
        self.draw_gaze(pen, s)
        # les anneaux
        for c in HARD_C:
            st = ring_state(s, c["t"], 760.0)
            if st is None:
                continue
            r, inten = st
            if inten < 0.25:
                continue
            draw_ring(pen, c["x"], c["y"] - R * 0.4, r, 6 + 6 * inten, mix(BG, (246, 246, 255), inten * 0.9))
        x, y = self.B.pos(s)
        base.ball(pen.dr, x * pen.S, y * pen.S, R * pen.S)
        self.subtitle(pen, t)


DEFAULTS = {
    "hook_text_s": 44.6, "hook_top": 0.125, "hook_font_size": 88,
    "narrator_voice": "bm_lewis", "narrator_length": 1.0, "narr_gap_s": 0.05,
    "sub_y": 3.0, "sub_font_size": 10, "sub_words": 6, "narr_tail_s": 0.0,
    "watermark_y": 0.94, "end_hold_s": 0.05, "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True,
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
