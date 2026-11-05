"""
Le mariage, v3 : « When would you object? »

Plan fixe de face, l'autel d'une chapelle la nuit. Un seul gag, rejoué cinq fois : on glisse
sous Bounce quelque chose de mou pour qu'il se taise (le coussin des alliances, le voile
tendu en filet, le livre de l'officiant, la traîne de la robe, la traîne laissée en tas à
la place de la mariée) ; il se tait, puis son rebond détruit ou perd le coussin, et
« Bounce ». L'officiant (voix du narrateur, sous-titrée sur les marches) ne lit que pendant
les rebonds mous. « If anyone objects, speak now. » → « Bounce ». « Do you take this man? »
→ « Bounce ». La mariée s'en va ; « Moving on. ». « I now pronounce you… husband… and… »,
deux secondes de silence, et Bounce cogne la cloche : « Bounce ». « Oh no. »

Une seule horloge : les contacts de Bounce tombent aux instants du plan, les arcs qui les
relient sont balistiques sous une seule gravité (G = 2600), calculés dans le temps du
récit (un ralenti de 1 s à 0,4× pendant que le voile se pose sur lui).

    python3 src/stories/wedding_v3.py configs/<name>.json [--simulate | --frames DIR t1,t2,...]
"""
import math, sys, os, json, tempfile, bisect, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
from PIL import Image, ImageDraw
import audio_kit as ak

SR = ak.SR

# ------------------------------------------------------------------ voix (mêmes voix, prises stables)
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
        if best is not None and text != cfg["hero_name"]:
            idx = np.where(np.abs(best) > 0.02)[0]
            if len(idx):      # la réaction, sans les silences de tête et de queue
                best = best[max(0, idx[0] - 200):idx[-1] + int(0.03 * SR)].copy()
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word
_orig_hook_voice = ak.hook_voice
HOOK = {"path": ""}


def _read_wav(path):
    with wave.open(path) as w:
        raw = w.readframes(w.getnframes())
        fr = w.getframerate()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def steady_hook_voice(text, *a, **k):
    if HOOK["path"] and os.path.exists(HOOK["path"]):
        return _read_wav(HOOK["path"])
    return _orig_hook_voice(text, *a, **k)


ak.hook_voice = steady_hook_voice

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
R = 120.0
FLOOR = 1150.0                 # dessus du marbre, au premier plan : Bounce y rebondit
FEET = 1140.0                  # où se tiennent les mariés
DAIS = 1040.0                  # pieds de l'officiant, au fond
STEP1, STEP2 = 1205.0, 1260.0
BELLS_X = (210.0, 870.0)
BELL_PY = 452.0                # pivot des cloches (sous la poutre)
BELL_D, BELL_HW = 125.0, 112.0  # profondeur, demi-largeur de la bouche
BOOK_Y = 905.0                 # le livre tendu à plat
SLOW = (13.45, 14.45, 0.4)     # ralenti : [t0, t1] en temps vidéo, vitesse


def tau(t):
    """Temps du récit : la vidéo, sauf pendant le ralenti."""
    a, b, k = SLOW
    if t <= a:
        return t
    if t <= b:
        return a + k * (t - a)
    return t - (b - a) * (1 - k)


# surfaces : y du centre de Bounce au contact (avant enfoncement)
SURF_Y = {"floor": FLOOR - R, "pillow": 1106.0 - R, "net": 1010.0 - R, "book": BOOK_Y - 8 - R,
          "cover": BOOK_Y - 14 - R, "train": 1122.0 - R, "heap": 1076.0 - R, "bell": 696.0}
HARD = {"floor", "cover", "bell"}
SINK = {"pillow": 22.0, "net": 46.0, "book": 14.0, "train": 12.0, "heap": 30.0}

# les contacts de Bounce : (t vidéo, surface, x)
C = [(-0.55, "pillow", 520), (0.15, "pillow", 540), (0.80, "pillow", 565),
     (1.47, "floor", 660),
     (2.15, "pillow", 650), (2.80, "pillow", 640), (3.45, "pillow", 585),
     (4.15, "floor", 520), (5.10, "floor", 450),
     # le voile en filet
     (6.15, "net", 540), (6.85, "net", 530), (7.25, "net", 535),
     (7.85, "floor", 665),
     (8.55, "net", 585), (9.30, "net", 575),
     (10.20, "floor", 470),
     (10.95, "net", 480), (11.75, "net", 560),
     (12.60, "floor", 700),
     (13.25, "net", 560),
     (14.80, "floor", 520), (15.90, "floor", 600),
     # le livre
     (16.60, "book", 560), (17.20, "book", 550), (17.80, "book", 560),
     (18.60, "floor", 690),
     (19.30, "book", 590), (19.90, "book", 570), (20.50, "book", 550),
     (21.20, "floor", 455),
     (21.90, "book", 480), (22.50, "book", 500), (23.10, "book", 520),
     (23.90, "floor", 560),
     # la traîne
     (24.85, "train", 600), (25.55, "train", 560),
     (26.30, "floor", 360),
     (27.05, "train", 420), (27.80, "train", 455),
     (28.55, "floor", 385),
     (29.30, "train", 470), (30.05, "train", 520),
     (30.80, "cover", 545),
     (31.55, "train", 500), (32.30, "train", 455),
     (33.00, "floor", 330),
     (33.80, "train", 430), (34.55, "train", 470),
     (35.20, "floor", 340),
     (35.95, "train", 420), (36.65, "train", 395), (37.35, "train", 360),
     (37.95, "floor", 340),
     (39.00, "floor", 690),
     (39.75, "train", 600), (40.45, "train", 520), (41.15, "train", 470),
     (41.80, "floor", 345),
     (42.50, "train", 610), (43.20, "train", 590),
     (44.00, "floor", 560), (44.88, "floor", 470),
     # le tas de traîne, à la place de la mariée
     (45.55, "heap", 720), (46.10, "heap", 728),
     (46.70, "floor", 565),
     (47.35, "heap", 715), (48.05, "heap", 722),
     (48.70, "floor", 580),
     (49.45, "heap", 712), (50.20, "heap", 720),
     (50.95, "floor", 590), (51.60, "heap", 715),
     (52.25, "floor", 600), (52.90, "heap", 718),
     (53.55, "floor", 610),
     (54.20, "heap", 722), (54.80, "heap", 725), (55.35, "heap", 722), (55.85, "heap", 726),
     (56.30, "heap", 724), (56.75, "heap", 727), (57.15, "heap", 725), (57.55, "heap", 727),
     (57.90, "heap", 726), (58.25, "heap", 728), (58.55, "heap", 727), (58.85, "heap", 728),
     (59.10, "heap", 728), (59.30, "heap", 729), (59.45, "heap", 730),
     (59.95, "bell", 790),
     (60.40, "heap", 748), (61.00, "heap", 740), (61.55, "heap", 734), (62.10, "heap", 731)]
CT = [c[0] for c in C]
CTAU = [tau(c[0]) for c in C]
T_ISSUE = 59.95
T_PAYOFF = 60.65               # le visage s'affaisse, « Oh no. » suit (0,15 s après)
T_END = 61.65                  # + end_hold 0.3 = 61,95 s
DEEP = 59.45                   # le contact mou qui l'aplatit avant la cloche

LINES = [(2.40, "Dearly beloved,", "l0"),
         (6.05, "to join this man and this woman,", "l1"),
         (16.85, "in holy matrimony.", "l2"),
         (24.85, "Skipping ahead.", "l3"),
         (36.10, "If anyone objects, speak now.", "l4"),
         (42.70, "Do you take this man?", "l5"),
         (45.80, "Moving on.", "l6"),
         (54.65, "I now pronounce you", "f0"),
         (56.15, "husband", "f1"),
         (57.55, "and", "f2")]

# ------------------------------------------------------------------ couleurs
BG = (8, 8, 12)
WALL = (24, 22, 36)
WALL2 = (31, 28, 46)
MARBLE = (204, 200, 212)
MARBLE_D = (156, 152, 168)
STEP_C = (112, 108, 124)
WOOD = (92, 62, 42)
WOOD_D = (58, 38, 28)
CARPET_C = (150, 30, 44)
GOLD = (236, 186, 72)
GOLD_D = (168, 120, 40)
GOLD_L = (255, 226, 140)
ROBE = (126, 32, 56)
ROBE_D = (96, 22, 42)
STOLE = (60, 150, 90)
SKIN = (214, 182, 150)
NAVY = (36, 46, 104)
NAVY_D = (26, 34, 80)
DRESS = (242, 240, 248)
DRESS_D = (206, 204, 220)
TULLE = (236, 236, 250)
SATIN = (244, 238, 246)
SATIN_D = (206, 198, 214)
PETALS = [(220, 40, 70), (250, 110, 150), (200, 30, 60), (255, 150, 180)]
LEAF = (70, 150, 70)
BOOK_C = (110, 64, 40)
PAGE = (246, 244, 234)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))


def bump(t, t0, up=0.08, down=0.35):
    u = t - t0
    if u < 0 or u > up + down:
        return 0.0
    if u < up:
        return math.sin(0.5 * math.pi * u / up)
    return 0.5 * (1 + math.cos(math.pi * (u - up) / down))


class K:
    """Une valeur par images clés adoucies."""

    def __init__(self, keys):
        self.keys = sorted(keys, key=lambda k: k[0])
        self.ts = [k[0] for k in self.keys]

    def __call__(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        i = bisect.bisect_right(self.ts, t) - 1
        (t0, v0), (t1, v1) = ks[i], ks[i + 1]
        u = smooth((t - t0) / max(1e-9, t1 - t0))
        if isinstance(v0, tuple):
            return tuple(a + (b - a) * u for a, b in zip(v0, v1))
        return v0 + (v1 - v0) * u


HITS = [c[0] for c in C if c[1] in HARD and 0 <= c[0] <= T_END]


def jolt(t, k=1.0):
    """Le sursaut général de la chapelle à chaque « Bounce » (petit, sauf le premier)."""
    s = 0.0
    for th in HITS:
        if th - 0.05 <= t <= th + 0.6:
            a = 1.0 if th < 2 else (0.9 if abs(th - 37.95) < 0.01 else 0.35)
            s += a * bump(t, th, 0.07, 0.4)
    return -24.0 * k * s


# ------------------------------------------------------------------ trajectoire
def ball_raw(t):
    T = tau(t)
    i = max(0, min(len(C) - 2, bisect.bisect_right(CTAU, T) - 1))
    (t0, s0, x0), (t1, s1, x1) = C[i], C[i + 1]
    a0, a1 = CTAU[i], CTAU[i + 1]
    y0, y1 = SURF_Y[s0], SURF_Y[s1]
    D = a1 - a0
    u = T - a0
    vy = (y1 - y0) / D - 0.5 * G * D
    vx = (x1 - x0) / D
    return x0 + vx * u, y0 + vy * u + 0.5 * G * u * u, vx, vy + G * u


def sink(t):
    s = 0.0
    i = bisect.bisect_right(CT, t)
    for j in (i - 1, i):
        if 0 <= j < len(C):
            tc, surf, _ = C[j]
            d = SINK.get(surf, 0.0)
            if abs(tc - DEEP) < 1e-6:
                d = 48.0
            if d:
                s = max(s, d * clamp01(1 - abs(t - tc) / 0.1))
    return s


def ball(t):
    x, y, vx, vy = ball_raw(t)
    return x, y + sink(t), vx, vy


def contact_near(t, surfs, win=0.12):
    i = bisect.bisect_right(CT, t)
    for j in (i - 2, i - 1, i, i + 1):
        if 0 <= j < len(C) and C[j][1] in surfs and abs(C[j][0] - t) < win:
            return C[j]
    return None


def dent_at(t, surfs, depth, win=0.12):
    c = contact_near(t, surfs, win)
    if not c:
        return None, 0.0
    return c[2], depth * clamp01(1 - abs(t - c[0]) / win)


# ------------------------------------------------------------------ dessin : outils
class Pen:
    def __init__(self, dr, S):
        self.dr, self.S, self.im = dr, S, dr._image

    def P(self, pts):
        return [(x * self.S, y * self.S) for x, y in pts]

    def poly(self, pts, fill, outline=None, width=0):
        self.dr.polygon(self.P(pts), fill=fill, outline=outline, width=int(width * self.S) if width else 0)

    def line(self, pts, fill, width):
        self.dr.line(self.P(pts), fill=fill, width=max(1, int(width * self.S)), joint="curve")

    def circle(self, x, y, r, fill, outline=None, width=0):
        S = self.S
        self.dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill, outline=outline,
                        width=int(width * S) if width else 0)

    def ellipse(self, x, y, rx, ry, fill, outline=None, width=0):
        S = self.S
        self.dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=fill, outline=outline,
                        width=int(width * S) if width else 0)

    def rect(self, x0, y0, x1, y1, fill, r=0):
        S = self.S
        b = [min(x0, x1) * S, min(y0, y1) * S, max(x0, x1) * S, max(y0, y1) * S]
        if r:
            self.dr.rounded_rectangle(b, radius=r * S, fill=fill)
        else:
            self.dr.rectangle(b, fill=fill)

    def tpoly(self, pts, col, alpha):
        S = self.S
        xs = [p[0] * S for p in pts]; ys = [p[1] * S for p in pts]
        x0, y0 = max(0, int(min(xs)) - 1), max(0, int(min(ys)) - 1)
        x1, y1 = min(self.im.size[0], int(max(xs)) + 2), min(self.im.size[1], int(max(ys)) + 2)
        if x1 <= x0 or y1 <= y0:
            return
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in zip(xs, ys)], fill=int(255 * alpha))
        self.im.paste(col, (x0, y0, x1, y1), m)

    def text(self, x, y, s, f, fill, stroke=0, sfill=(0, 0, 0)):
        self.dr.text((x * self.S, y * self.S), s, font=f, fill=fill, anchor="mm",
                     stroke_width=int(stroke * self.S), stroke_fill=sfill)


def rpoly(x0, y0, x1, y1, r, n=6):
    pts = []
    for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def quad(p0, p1, p2, n=16):
    out = []
    for k in range(n + 1):
        u = k / n
        out.append(((1 - u) ** 2 * p0[0] + 2 * u * (1 - u) * p1[0] + u * u * p2[0],
                    (1 - u) ** 2 * p0[1] + 2 * u * (1 - u) * p1[1] + u * u * p2[1]))
    return out


def band(curve, w0, w1=None):
    w1 = w0 if w1 is None else w1
    up, dn = [], []
    n = len(curve)
    for i, (x, y) in enumerate(curve):
        a = curve[max(0, i - 1)]; b = curve[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        w = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2
        up.append((x + nx * w, y + ny * w)); dn.append((x - nx * w, y - ny * w))
    return up + dn[::-1]


# ------------------------------------------------------------------ les cloches
BELL_PROFILE = [(0, 26), (13, 46), (36, 62), (74, 76), (100, 92), (116, 105), (125, BELL_HW)]


def bell_angle(t, k):
    if k == 1:
        u = t - T_ISSUE
        if u > 0:
            return 0.28 * math.exp(-u / 1.8) * math.sin(2 * math.pi * u / 1.2)
    return 0.0


def bell_poly(t, k):
    px, py = BELLS_X[k], BELL_PY
    right = [(px + w, py + d) for d, w in BELL_PROFILE]
    left = [(px - w, py + d) for d, w in BELL_PROFILE[::-1]]
    return rot(right + left, px, py, bell_angle(t, k))


def bell_flash(t):
    return bump(t, T_ISSUE, 0.05, 1.1)


# ------------------------------------------------------------------ les personnages : images clés
# le marié
GX = K([(0, 245), (15.4, 245),
        (28.6, 245), (28.9, 300), (29.6, 245),
        (50.95, 245), (51.4, 330), (52.0, 340), (52.6, 380), (53.6, 400), (62.5, 400)])
G_KNEEL = K([(0, 0), (7.85, 0), (8.0, 1.0), (8.5, 1.0), (8.8, 0)])
G_LEAN = K([(0, 0), (37.95, 0), (38.05, 0.05), (39.05, 0.05), (39.2, 0.07), (44.0, 0.07), (44.15, -0.06),
            (46.5, -0.06), (46.9, 0.03), (48.7, 0.03), (49.0, 0.06), (60.0, 0.06), (60.2, 0.09), (62.5, 0.09)])
# la mariée
BXK = K([(0, 795), (1.6, 795), (1.75, 770), (2.2, 795), (15.4, 795),
         (28.55, 795), (28.85, 690), (29.35, 690), (29.9, 795), (44.95, 795)])
B_LEAN = K([(0, 0), (28.55, 0), (28.7, -0.30), (29.3, -0.22), (29.8, 0), (37.95, 0), (38.05, -0.10),
            (39.0, -0.10), (39.4, 0), (44.0, 0), (44.12, -0.14), (44.8, -0.14), (45.0, 0.0)])
B_HOP = K([(0, 0), (12.6, 0), (12.68, 1.0), (12.95, 0.2), (13.2, 0)])
TRAIN_L = K([(0, 380), (28.55, 380), (28.8, 270), (29.6, 270), (30.2, 330), (62.0, 330)])
# l'officiant
O_LEAN = K([(0, 0), (10.2, 0), (10.28, -0.10), (10.7, -0.03), (11.2, 0), (16.1, 0), (16.5, 0.12), (23.95, 0.12),
            (24.3, 0.0)])
O_KNEEL = K([(0, 0), (24.05, 0), (24.35, 1.0), (26.8, 1.0), (27.2, 0)])


def officiant_lean(t):
    v = O_LEAN(t)
    if 20.5 <= t < 21.3:      # elle lui frôle le nez : il se rejette en arrière
        v = 0.12 - 0.30 * bump(t, 20.55, 0.12, 0.6)
    if 45.8 <= t < 46.6:      # le haussement d'épaules
        v = 0.04 * math.sin(math.pi * (t - 45.8) / 0.8)
    return v


# ------------------------------------------------------------------ la simulation
class Sim:
    scene_top = 0.234

    def __init__(self, cfg, rng):
        self.cfg = cfg
        HOOK["path"] = cfg.get("hook_cache", "")
        self.clock = 0.0
        self.snap_t = 0.0
        self.done = False
        self.payoff = False
        self.payoff_t = None
        self.lines = list(LINES)
        self.replies = []
        self.narr = []
        self.fs = None
        self.ci = bisect.bisect_left(CT, 0.0)
        self.outcome = ("Après « I now pronounce you… husband… and… » et deux secondes de silence, Bounce, "
                        "voilé à la place de la mariée partie, cogne la cloche : « Bounce. » ; « Oh no. »")
        rng2 = np.random.default_rng(11)
        self.pages = [dict(dx=float(rng2.uniform(-1, 1)), vy=float(rng2.uniform(-900, -350)),
                           vx=float(rng2.uniform(-420, 420)), spin=float(rng2.uniform(-8, 8)),
                           t0=float(rng2.choice([21.95, 22.55, 23.12, 23.12, 23.12, 23.12, 23.9])),
                           w=float(rng2.uniform(26, 40))) for _ in range(26)]

    def hero_mood(self):
        return "lose" if self.payoff else None

    def step(self, dt):
        t0 = self.clock
        evs = []
        while self.ci < len(C) and C[self.ci][0] < t0:
            tc, s, x = C[self.ci]
            if tc >= t0 - dt - 1e-9 and s in HARD:
                evs.append(("hit", "final" if abs(tc - T_ISSUE) < 1e-6 else "n"))
            self.ci += 1
        if not self.payoff and t0 >= T_PAYOFF:
            self.payoff = True
            evs.append(("payoff", "married"))
        self.snap_t = t0
        self.clock += dt
        if self.clock >= T_END:
            self.done = True
        return evs

    def snapshot(self):
        return self.snap_t

    # -------------------------------------------------------------- dessin
    def draw(self, dr, snap, tt, S):
        t = snap
        p = Pen(dr, S)
        self.draw_room(p, t)
        self.draw_window(p, t)
        self.draw_bells(p, t)
        self.draw_officiant(p, t)
        self.draw_groom(p, t)
        self.draw_train(p, t)
        self.draw_bride(p, t)
        self.draw_bouquet_floor(p, t)
        self.draw_pillow(p, t)
        self.draw_net_back(p, t)
        self.draw_book_front(p, t)
        self.draw_ball(p, t)
        self.draw_net_front(p, t)
        self.draw_pages(p, t)
        self.draw_subs(p, t)

    # ---- le décor
    def draw_room(self, p, t):
        p.rect(0, 0, W, H, BG)
        p.rect(40, 250, W - 40, DAIS, WALL)
        for row in range(13):
            yy = 278 + row * 64
            off = 0 if row % 2 else 55
            for k in range(-1, 10):
                xx = 40 + off + k * 110
                p.rect(xx + 4, yy + 4, xx + 106, yy + 60, WALL2, r=6)
        for k in range(8):
            col = mix(WALL, BG, 0.55 + 0.05 * k)
            p.rect(40 + k * 14, 250, 54 + k * 14, DAIS, col)
            p.rect(W - 54 - k * 14, 250, W - 40 - k * 14, DAIS, col)
        # le marbre de l'autel, vu en légère plongée
        p.poly([(0, DAIS), (W, DAIS), (W, FLOOR), (0, FLOOR)], MARBLE)
        for k in range(7):
            p.line([(60 + k * 170, DAIS), (k * 170 - 20, FLOOR)], MARBLE_D, 2)
        p.rect(0, DAIS, W, DAIS + 6, mix(MARBLE, BG, 0.4))
        p.rect(0, FLOOR, W, FLOOR + 14, MARBLE_D)
        p.rect(140, FLOOR + 14, 940, STEP1, mix(MARBLE, STEP_C, 0.55))
        p.rect(140, STEP1, 940, STEP1 + 10, STEP_C)
        p.rect(140, STEP1 + 10, 940, STEP2, mix(MARBLE, STEP_C, 0.75))
        p.rect(140, STEP2, 940, STEP2 + 10, mix(STEP_C, BG, 0.3))
        # l'allée et les bancs (décor)
        p.poly([(470, STEP2 + 10), (610, STEP2 + 10), (650, H), (430, H)], CARPET_C)
        heads = [(150, (190, 150, 220), "hat"), (300, (240, 140, 60), ""), (780, (60, 170, 180), "top"),
                 (930, (70, 160, 90), "sq")]
        for k, (x, col, kind) in enumerate(heads):
            y = 1350 + jolt(t, 0.6)
            p.rect(x - 58, y + 34, x + 58, 1500, mix(col, BG, 0.55), r=30)
            if kind == "sq":
                p.rect(x - 46, y - 44, x + 46, y + 40, col, r=12)
            else:
                p.circle(x, y, 44, col)
            if kind == "hat":
                p.ellipse(x, y - 30, 80, 16, (150, 110, 190))
                p.ellipse(x, y - 52, 44, 30, (190, 150, 220))
            if kind == "top":
                p.rect(x - 48, y - 46, x + 48, y - 36, (16, 16, 20))
                p.rect(x - 32, y - 120, x + 32, y - 40, (16, 16, 20))
        for (x0, x1) in ((20, 440), (640, 1060)):
            p.rect(x0, 1420, x1, 1500, WOOD, r=8)
            p.rect(x0, 1420, x1, 1428, mix(WOOD, (255, 255, 255), 0.18), r=4)
        # les rangs de derrière, dans l'ombre
        back = [(120, (120, 100, 160)), (260, (200, 120, 90)), (370, (90, 130, 170)), (720, (170, 90, 120)),
                (850, (110, 150, 110)), (980, (160, 140, 90))]
        for row, (yy, kk) in enumerate(((1590, 0.45), (1770, 0.3))):
            for j, (x, col) in enumerate(back):
                xx = x + (35 if row else 0) - (j % 2) * 10
                c2 = mix(BG, col, kk)
                p.rect(xx - 50, yy + 28, xx + 50, yy + 120, mix(BG, col, kk * 0.6), r=26)
                p.circle(xx, yy, 38, c2)
            for (x0, x1) in ((20, 440), (640, 1060)):
                p.rect(x0, yy + 70, x1, yy + 140, mix(BG, WOOD, kk + 0.15), r=8)
        # la poutre et le nœud des cloches
        p.rect(140, BELL_PY - 16, 940, BELL_PY - 2, WOOD)
        p.rect(140, BELL_PY - 16, 940, BELL_PY - 11, mix(WOOD, (255, 255, 255), 0.15))

    def draw_window(self, p, t):
        fl = bell_flash(t)
        x0, x1, ytop, yspr, ybot = 395.0, 685.0, 470.0, 600.0, 1000.0
        cx = (x0 + x1) / 2

        def ogive(ins):
            left, right = x0 + ins, x1 - ins
            r = right - left
            ky = (yspr - ytop - ins) / (r * math.sin(math.radians(60)))
            pts = [(left, ybot - ins)]
            for k in range(14):
                a = math.radians(180 - 60 * k / 13)
                pts.append((right + r * math.cos(a), yspr - r * math.sin(a) * ky))
            for k in range(1, 14):
                a = math.radians(60 - 60 * k / 13)
                pts.append((left + r * math.cos(a), yspr - r * math.sin(a) * ky))
            pts.append((right, ybot - ins))
            return pts
        p.poly(ogive(-22), mix((50, 44, 76), (170, 140, 80), fl))
        p.poly(ogive(0), (18, 16, 26))
        cols = [(46, 92, 200), (190, 40, 60), (220, 170, 50), (40, 140, 170), (120, 60, 170)]
        rng = np.random.default_rng(5)
        dw, dh = 52.0, 66.0
        win = ogive(6)
        for j in range(-1, int((ybot - ytop) / (dh / 2)) + 2):
            for i in range(-1, int((x1 - x0) / dw) + 2):
                px = x0 + i * dw + (dw / 2 if j % 2 else 0)
                py = ytop + j * dh / 2
                col = cols[int(rng.integers(0, len(cols)))]
                if not self._inside(px, py, win):
                    continue
                cc = mix(dim(col, 0.55), col, 0.62 + 0.38 * fl)
                if fl > 0:
                    cc = mix(cc, (255, 240, 200), 0.35 * fl)
                p.poly([(px, py - dh / 2 + 4), (px + dw / 2 - 4, py), (px, py + dh / 2 - 4), (px - dw / 2 + 4, py)], cc)
        p.rect(cx - 5, yspr - 30, cx + 5, ybot, (18, 16, 26))

    @staticmethod
    def _inside(x, y, poly):
        n = len(poly); c = False
        for i in range(n):
            (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
            if (ya > y) != (yb > y) and x < (xb - xa) * (y - ya) / ((yb - ya) or 1e-9) + xa:
                c = not c
        return c

    def draw_bells(self, p, t):
        for k in (0, 1):
            px, py = BELLS_X[k], BELL_PY
            a = bell_angle(t, k)
            p.poly(bell_poly(t, k), GOLD)
            p.poly(rot([(px - 52, py + 28), (px - 38, py + 20), (px - 62, py + 108), (px - 88, py + 114)], px, py, a), GOLD_L)
            p.poly(rot([(px + 44, py + 28), (px + 62, py + 34), (px + 98, py + 116), (px + 76, py + 118)], px, py, a), GOLD_D)
            mouth = rot([(px - BELL_HW + 8 + (2 * BELL_HW - 16) * j / 16, py + BELL_D + 8 * math.sin(math.pi * j / 16))
                         for j in range(17)], px, py, a)
            p.poly(mouth, (24, 16, 8))
            p.poly(rot([(px - BELL_HW, py + BELL_D - 6), (px + BELL_HW, py + BELL_D - 6), (px + BELL_HW, py + BELL_D + 2),
                        (px - BELL_HW, py + BELL_D + 2)], px, py, a), GOLD_D)
        # le nœud de satin entre les deux cloches, qui frémit quand la balle passe tout près
        fr = 0.25 * math.sin(30 * t) * bump(t, 13.95, 0.1, 0.9)
        kx, ky = 540.0, BELL_PY - 4
        for sx in (-1, 1):
            p.poly(rot([(kx, ky), (kx + sx * 60, ky - 26), (kx + sx * 64, ky + 18)], kx, ky, fr * sx), (250, 250, 252))
            p.poly(rot([(kx, ky), (kx + sx * 20, ky + 60), (kx + sx * 42, ky + 52)], kx, ky, -fr * sx), (232, 232, 242))
        p.circle(kx, ky, 12, (255, 255, 255))
        # cercles dorés de la cloche frappée
        u = t - T_ISSUE
        if 0 <= u < 1.1:
            px, py = BELLS_X[1], BELL_PY + 70
            for j in range(3):
                uu = u - j * 0.16
                if uu <= 0:
                    continue
                rad = 130 + 560 * uu
                k = 1 - uu / 1.1
                if k > 0:
                    p.circle(px, py, rad, None, outline=mix(BG, GOLD_L, 0.85 * k), width=9 * k + 2)

    # ---- l'officiant, son livre
    def book_state(self, t):
        """(état, x du centre) du livre."""
        if t < 16.1:
            return "chest", 540.0
        if t < 23.9:
            bk = [(tc, x) for tc, s_, x in C if s_ == "book"]
            prev = [q for q in bk if q[0] <= t]
            nxt = [q for q in bk if q[0] > t]
            if not prev:
                x = 540 + (bk[0][1] - 540) * smooth((t - 16.1) / 0.45)
            elif not nxt:
                x = prev[-1][1]
            else:
                (ta, xa), (tb, xb) = prev[-1], nxt[0]
                x = xa + (xb - xa) * smooth((t - ta - 0.05) / max(0.2, tb - ta - 0.2))
            return ("closed" if 18.60 <= t < 18.95 else "open"), x
        if 24.2 <= t < 27.0:
            return "kneel", 540.0
        return "cover", 540.0

    def draw_officiant(self, p, t):
        lean = officiant_lean(t)
        kn = O_KNEEL(t)
        jy = jolt(t, 0.7)
        h = 340 - 120 * kn

        def P(x, y):
            hh = DAIS - y
            return (x + lean * hh, y + jy * hh / 340 + (340 - h) * hh / 340)
        p.poly([P(x, y) for x, y in rpoly(455, DAIS - 340, 625, DAIS, 56)], ROBE)
        p.poly([P(455, DAIS - 60), P(625, DAIS - 60), P(625, DAIS), P(455, DAIS)], ROBE_D)
        p.poly([P(500, DAIS - 330), P(518, DAIS - 330), P(518, DAIS - 40), P(500, DAIS - 40)], STOLE)
        p.poly([P(562, DAIS - 330), P(580, DAIS - 330), P(580, DAIS - 40), P(562, DAIS - 40)], STOLE)
        p.poly([P(498, DAIS - 344), P(582, DAIS - 344), P(576, DAIS - 326), P(504, DAIS - 326)], (250, 250, 250))
        hx, hy = P(540, DAIS - 395)
        p.circle(hx, hy, 56, SKIN)
        self.o_P = P
        st, bx = self.book_state(t)
        sh = (P(474, DAIS - 300), P(606, DAIS - 300))
        if st == "chest":
            hands = (P(500, DAIS - 230), P(580, DAIS - 230))
            if t >= 15.9:
                u = smooth((t - 15.9) / 0.2)
                hands = tuple((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
                              for a, b in zip(hands, ((bx - 104, BOOK_Y), (bx + 104, BOOK_Y))))
            self.book_hands = None
            for s, hnd in zip(sh, hands):
                p.line([s, hnd], ROBE_D, 22)
                p.circle(hnd[0], hnd[1], 13, SKIN)
            self.draw_book(p, t, (hands[0][0] + hands[1][0]) / 2, (hands[0][1] + hands[1][1]) / 2 - 10,
                           "open" if t < 1.47 or t > 2.05 else "closed", small=True)
        elif st in ("open", "closed"):
            hands = ((bx - 104, BOOK_Y), (bx + 104, BOOK_Y))
            for s, hnd in zip(sh, hands):
                p.line([s, hnd], ROBE_D, 22)
            self.book_hands = (hands, bx, st)
        else:
            if st == "kneel":
                hands = (P(470, DAIS - 120), P(610, DAIS - 120))
            elif 30.6 <= t < 31.2:
                hands = ((440, BOOK_Y - 10), (640, BOOK_Y - 10))
            else:
                hands = (P(490, DAIS - 250), P(590, DAIS - 250))
            if t >= 53.4:      # la main levée
                u = smooth((t - 53.4) / 0.4)
                hands = (hands[0], (hands[1][0] + 40 * u, hands[1][1] - 160 * u))
            for s, hnd in zip(sh, hands):
                p.line([s, hnd], ROBE_D, 22)
                p.circle(hnd[0], hnd[1], 13, SKIN)
            self.book_hands = None
            if st == "kneel":
                # il ramasse les pages, puis en brandit une
                p.rect(hands[0][0] - 30, hands[0][1] - 20, hands[0][0] + 30, hands[0][1] + 18, PAGE)
                if t >= 24.85:
                    u = smooth((t - 24.85) / 0.3)
                    p.rect(hands[1][0] - 26, hands[1][1] - 40 - 50 * u, hands[1][0] + 26, hands[1][1] + 20 - 50 * u, PAGE)
            else:
                cx = (hands[0][0] + hands[1][0]) / 2
                cyy = (hands[0][1] + hands[1][1]) / 2 - 8
                snap = bump(t, 30.80, 0.06, 0.3)
                p.rect(cx - 90, cyy - 12 + 10 * snap, cx + 90, cyy + 10, BOOK_C, r=4)
                if 27.0 <= t < 45.8:
                    # la page tirée au hasard, qu'il tient droite
                    p.rect(hands[1][0] - 26, hands[1][1] - 70, hands[1][0] + 26, hands[1][1] + 6, PAGE)
                if t >= 45.8:
                    # « Moving on. » : il feuillette son paquet de pages jusqu'à la dernière
                    ph = (t * 4.0) % 1.0
                    if t < 49.0:
                        p.poly([(cx, cyy - 12), (cx + 80 * math.cos(math.pi * ph), cyy - 12 - 40 * math.sin(math.pi * ph)),
                                (cx + 80 * math.cos(math.pi * ph), cyy - 4 - 40 * math.sin(math.pi * ph)), (cx, cyy - 4)], PAGE)

    def draw_book(self, p, t, cx, cyy, st, small=False):
        k = 0.7 if small else 1.0
        if st == "closed":
            p.rect(cx - 70 * k, cyy - 12, cx + 70 * k, cyy + 14, BOOK_C, r=3)
            return
        x, dent = dent_at(t, ("book",), 16.0)
        dl = dent if x is not None else 0.0
        left = self.pages_left(t)
        p.poly([(cx - 110 * k, cyy - 4), (cx, cyy + 4 + dl), (cx, cyy + 18 + dl), (cx - 110 * k, cyy + 10)], BOOK_C)
        p.poly([(cx + 110 * k, cyy - 4), (cx, cyy + 4 + dl), (cx, cyy + 18 + dl), (cx + 110 * k, cyy + 10)], BOOK_C)
        if left > 0:
            th = 4 + 10 * left
            p.poly([(cx - 104 * k, cyy - 6 - th * 0.5), (cx - 2, cyy + dl - th * 0.2), (cx - 2, cyy + 8 + dl),
                    (cx - 104 * k, cyy + 2)], PAGE)
            p.poly([(cx + 104 * k, cyy - 6 - th * 0.5), (cx + 2, cyy + dl - th * 0.2), (cx + 2, cyy + 8 + dl),
                    (cx + 104 * k, cyy + 2)], PAGE)
            if dl > 1:      # les pages en éventail sous lui
                for j in range(4):
                    a = math.pi * (0.15 + 0.7 * j / 3)
                    ex = cx + 100 * math.cos(a)
                    ey = cyy - 8 - 30 * math.sin(a) * dl / 16
                    p.poly([(cx, cyy + dl), (ex, ey), (ex, ey + 6), (cx, cyy + dl + 6)], (236, 234, 224))

    def pages_left(self, t):
        if t < 21.9:
            return 1.0
        if t < 23.1:
            return 0.6
        return 0.0

    def draw_book_front(self, p, t):
        if getattr(self, "book_hands", None) is None:
            return
        hands, bx, st = self.book_hands
        self.draw_book(p, t, bx, BOOK_Y - 6, st)
        for hnd in hands:
            p.circle(hnd[0], hnd[1], 14, SKIN)

    def draw_pages(self, p, t):
        for pg in self.pages:
            u = t - pg["t0"]
            if u < 0 or u > 3.0:
                continue
            x = 540 + pg["dx"] * 80 + pg["vx"] * u
            y = BOOK_Y - 20 + pg["vy"] * u + 0.5 * 700 * u * u
            if y > 1150:
                y = 1150
            a = pg["spin"] * u
            w = pg["w"]
            p.poly(rot([(x - w / 2, y - w * 0.65), (x + w / 2, y - w * 0.65), (x + w / 2, y + w * 0.65),
                        (x - w / 2, y + w * 0.65)], x, y, a), PAGE)

    # ---- le marié
    def groom_geo(self, t):
        x = GX(t)
        if 5.6 <= t < 14.6:           # il tient un bout du voile : il suit le filet
            u = smooth((t - 5.6) / 0.4) * (1 - smooth((t - 14.0) / 0.6))
            x = x + (self.net_center(min(t, 13.25)) - 240 - x) * u
        k = G_KNEEL(t)
        h = 470 * (1 - 0.35 * k)
        top = FEET - h + jolt(t, 1.0) * (1 - 0.3 * k)
        return x, top, h, G_LEAN(t)

    def draw_groom(self, p, t):
        x, top, h, lean = self.groom_geo(t)

        def P(px, py):
            return (px + lean * (FEET - py), py)
        p.poly([P(a, b) for a, b in rpoly(x - 78, top, x + 78, FEET, 30)], NAVY)
        p.poly([P(x - 32, top + 2), P(x + 32, top + 2), P(x, top + 90)], (240, 240, 244))
        p.poly([P(x - 28, top + 10), P(x, top + 20), P(x - 28, top + 30)], (14, 14, 18))
        p.poly([P(x + 28, top + 10), P(x, top + 20), P(x + 28, top + 30)], (14, 14, 18))
        hx, hy = P(x, top - 56)
        p.circle(hx, hy, 58, SKIN)
        sh = (P(x - 64, top + 36), P(x + 64, top + 36))
        hands = self.groom_hands(t, x, top, P)
        for s, hnd in zip(sh, hands):
            p.line([s, hnd], NAVY_D, 24)
            p.circle(hnd[0], hnd[1], 14, SKIN)
        p.ellipse(x - 34, FEET - 4, 34, 12, (14, 14, 18))
        p.ellipse(x + 34, FEET - 4, 34, 12, (14, 14, 18))

    def groom_hands(self, t, x, top, P):
        rest = (P(x - 78, top + 200), P(x + 78, top + 200))
        if 5.6 <= t < 14.0:
            nl, nr = self.net_ends(t)
            u = smooth((t - 5.6) / 0.3)
            return (rest[0], (rest[1][0] + (nl[0] - rest[1][0]) * u, rest[1][1] + (nl[1] - rest[1][1]) * u))
        if 28.6 <= t < 29.5:       # il rattrape la mariée par le bras
            u = smooth((t - 28.6) / 0.2) * (1 - smooth((t - 29.2) / 0.3))
            bx = BXK(t) - 70
            return (rest[0], (rest[1][0] + (bx - rest[1][0]) * u, rest[1][1] + (top + 150 - rest[1][1]) * u))
        if 46.5 <= t < 47.4:       # le bras tendu vers l'allée, qui retombe
            u = bump(t, 46.5, 0.25, 0.65)
            return (rest[0], (rest[1][0] + 120 * u, rest[1][1] - 150 * u))
        if 52.0 <= t < 52.9:       # il remet le voile droit sur la tête de la balle
            u = bump(t, 52.0, 0.35, 0.55)
            bx, by, _, _ = ball(t)
            tgt = (bx - R * 0.55, by - R * 0.95)
            return (rest[0], (rest[1][0] + (tgt[0] - rest[1][0]) * u, rest[1][1] + (tgt[1] - rest[1][1]) * u))
        return rest

    # ---- la mariée
    def bride_geo(self, t):
        x = BXK(t)
        if 5.6 <= t < 14.6:           # elle tient l'autre bout
            u = smooth((t - 5.6) / 0.4) * (1 - smooth((t - 14.0) / 0.6))
            x = x + (min(795.0, self.net_center(min(t, 13.25)) + 235) - x) * u
        h = 470.0
        dy = 0.0
        if t >= 44.95:             # elle part : demi-tour, puis elle descend l'allée
            u = clamp01((t - 45.15) / 2.2)
            x = 795 - 230 * smooth(u)
            dy = 620 * u
        top = FEET - h + jolt(t, 1.0) - 60 * B_HOP(t) + dy
        return x, top, h, B_LEAN(t), dy

    def draw_bride(self, p, t):
        if t > 47.8:
            return
        x, top, h, lean, dy = self.bride_geo(t)
        feet = FEET + dy

        def P(px, py):
            return (px + lean * (feet - py), py)
        dress = [P(x - 50, top), P(x + 50, top), P(x + 62, top + 150), P(x + 85, feet), P(x - 85, feet),
                 P(x - 62, top + 150)]
        p.poly(dress, DRESS)
        p.poly([P(x - 85, feet - 12), P(x + 85, feet - 12), P(x + 85, feet), P(x - 85, feet)], DRESS_D)
        p.poly([P(x - 52, top + 70), P(x + 52, top + 70), P(x + 56, top + 82), P(x - 56, top + 82)], DRESS_D)
        hx, hy = P(x, top - 54)
        p.circle(hx, hy, 56, SKIN)
        if t < 5.35:
            lift = 40 * bump(t, 1.47, 0.08, 0.6)
            p.tpoly([(hx - 58, hy - 18 - lift), (hx - 12, hy - 66 - lift), (hx + 50, hy - 58), (hx + 64, hy - 8),
                     (hx + 92, feet - 120 - dy * 0), (hx + 30, feet - 140)], TULLE, 0.5)
        else:
            p.ellipse(hx + 10, hy - 52, 22, 7, (250, 248, 240))
        sh = (P(x - 46, top + 30), P(x + 46, top + 30))
        hands = self.bride_hands(t, x, top, P)
        for s, hnd in zip(sh, hands):
            p.line([s, hnd], DRESS_D, 20)
            p.circle(hnd[0], hnd[1], 13, SKIN)
        if t < 44.9:
            self.draw_bunch(p, hands[1][0], hands[1][1], 0.0)

    def bride_hands(self, t, x, top, P):
        rest = (P(x - 74, top + 190), P(x + 66, top + 196))
        left, right = rest
        if 5.0 <= t < 5.6:         # elle enlève son voile
            u = bump(t, 5.0, 0.25, 0.35)
            left = (left[0] + (x - 40 - left[0]) * u, left[1] + (top - 90 - left[1]) * u)
        if 5.6 <= t < 14.0:
            nl, nr = self.net_ends(t)
            u = smooth((t - 5.6) / 0.3)
            left = (left[0] + (nr[0] - left[0]) * u, left[1] + (nr[1] - left[1]) * u)
        if 14.85 <= t < 16.0:      # elle tâte sa tête nue
            u = bump(t, 14.9, 0.3, 0.8)
            left = (left[0] + (x - 30 - left[0]) * u, left[1] + (top - 80 - left[1]) * u)
        if 23.95 <= t < 24.7:      # elle lance sa traîne devant elle
            u = bump(t, 24.0, 0.3, 0.45)
            left = (left[0] - 120 * u, left[1] - 40 * u)
        if 41.8 <= t < 42.4:       # ses mains tremblent
            left = (left[0] + 4 * math.sin(60 * t), left[1])
        if 44.05 <= t < 44.45:     # elle décroche sa traîne
            u = bump(t, 44.05, 0.15, 0.25)
            left = (left[0] + 30 * u, left[1] - 40 * u)
        if 44.55 <= t < 44.95:     # elle jette son bouquet par terre, aux pieds du marié
            u = smooth((t - 44.55) / 0.3)
            right = (right[0] - 40 * u, right[1] - 120 * u + 160 * u * u)
        return left, right

    def draw_bunch(self, p, hx, hy, ang, s=1.0):
        for k in range(7):
            a = -0.5 + k / 6.0
            p.line(rot([(hx, hy + 12), (hx + 40 * a * s, hy - 56 * s)], hx, hy, ang), LEAF, 6 * s)
        cx, cy0 = rot([(hx, hy - 64 * s)], hx, hy, ang)[0]
        for k in range(9):
            a = 2 * math.pi * k / 9
            p.circle(cx + 26 * s * math.cos(a), cy0 + 14 * s * math.sin(a), 17 * s, PETALS[k % 4])
        p.circle(cx, cy0 - 8, 18 * s, PETALS[1])

    def draw_bouquet_floor(self, p, t):
        if t < 44.9:
            return
        u = clamp01((t - 44.9) / 0.35)
        x = 690 + (380 - 690) * u
        y = 880 + (1110 - 880) * u - 160 * math.sin(math.pi * u)
        p.circle(x, y + 28, 0, None)
        self.draw_bunch(p, x, y + 30, 1.4 * u + 0.2, 0.9)

    # ---- la traîne
    def train_on_floor(self, t):
        return 24.55 <= t < 44.25

    def draw_train(self, p, t):
        if t < 23.95:
            return
        x, top, h, lean, dy = self.bride_geo(t)
        if t < 24.55:
            # elle part de sa taille et se déroule vers la gauche
            u = smooth((t - 23.95) / 0.6)
            xl = x - 60 - (x - 60 - TRAIN_L(t)) * u
            arc = [(x - 40, top + 90), ((x + xl) / 2, top + 40 - 120 * math.sin(math.pi * u)), (xl, FLOOR - 10)]
            p.poly(band(quad(*arc, n=16), 26, 70), SATIN)
            return
        if self.train_on_floor(t):
            xl = TRAIN_L(t)
            xr = x - 30
            bx, dent = dent_at(t, ("train",), 12.0)
            pts = []
            n = 24
            for k in range(n + 1):
                xx = xl + (xr - xl) * k / n
                d = dent * math.exp(-((xx - bx) / 70) ** 2) if bx is not None else 0.0
                pts.append((xx, FLOOR - 30 + d + 5 * math.sin(k * 1.3)))
            p.poly([(q[0], q[1] - 6) for q in pts] + [(xr, FLOOR + 3), (xl, FLOOR + 3)], (150, 140, 160))
            poly = pts + [(xr, FLOOR), (xl, FLOOR)]
            p.poly(poly, SATIN)
            p.line(pts, (160, 150, 172), 4)
            p.rect(xl, FLOOR - 4, xr, FLOOR, SATIN_D)
            # le pan qui remonte jusqu'à sa taille
            p.poly(band([(xr, FLOOR - 10), (x - 40, (FLOOR + top) / 2), (x - 46, top + 90)], 40, 26), SATIN)
            return
        # en tas, à la place de la mariée
        hx = 735.0
        u = smooth((t - 44.25) / 0.3)
        hgt = 74 * u
        bx, dent = dent_at(t, ("heap",), 30.0, 0.12)
        if abs(t - DEEP) < 0.12:
            dent = 48 * clamp01(1 - abs(t - DEEP) / 0.12)
        pts = []
        n = 20
        for k in range(n + 1):
            xx = hx - 115 + 230 * k / n
            yy = FLOOR - hgt * math.sin(math.pi * k / n) ** 0.7
            if bx is not None:
                yy += dent * math.exp(-((xx - bx) / 60) ** 2)
            pts.append((xx, yy))
        p.poly(pts + [(hx + 115, FLOOR), (hx - 115, FLOOR)], SATIN)
        p.line(pts, (160, 150, 172), 4)
        for k in range(3):
            p.line(quad((hx - 80 + 60 * k, FLOOR - 6), (hx - 50 + 60 * k, FLOOR - hgt * 0.7), (hx - 20 + 60 * k, FLOOR - 8), 8),
                   SATIN_D, 3)

    # ---- le coussin des alliances
    def pillow_state(self, t):
        """(x, y du centre, angle) ; None quand il est sorti de l'image."""
        if t < 1.6:
            return 540.0, FLOOR - 22, 0.0
        if t < 2.05:
            return 540 + 110 * smooth((t - 1.6) / 0.45), FLOOR - 22, 0.0
        if t < 3.45:
            return 650.0, FLOOR - 22, 0.0
        u = t - 3.45
        if u > 1.2:
            return None
        # il bascule autour de son coin droit, puis vole par-dessus les marches
        x = 650 + 260 * u
        y = FLOOR - 22 - 900 * u + 0.5 * G * u * u
        return x, y, 7.0 * u

    def draw_pillow(self, p, t):
        st = self.pillow_state(t)
        if st is None:
            return
        px, py, ang = st
        pw, ph = 190.0, 44.0
        bx, by, _, _ = ball(t)
        dent = 0.0
        if ang == 0.0 and abs(bx - px) < pw / 2 + 10:
            dent = max(0.0, min(26, by + R - (py - ph / 2)))
        top = py - ph / 2
        pts = []
        n = 18
        for k in range(n + 1):
            x = px - pw / 2 + pw * k / n
            yy = top - 4 * (1 - (2 * k / n - 1) ** 2) + dent * math.exp(-((x - bx) / 56) ** 2)
            pts.append((x, yy))
        bot = py + ph / 2
        poly = pts + [(px + pw / 2 + 4, bot - 6), (px + pw / 2, bot), (px - pw / 2, bot), (px - pw / 2 - 4, bot - 6)]
        poly = rot(poly, px, py, ang)
        p.poly(poly, SATIN)
        p.poly(rot([(px - pw / 2, bot - 10), (px + pw / 2, bot - 10), (px + pw / 2, bot), (px - pw / 2, bot)], px, py, ang), SATIN_D)
        # les alliances : elles sautent à chaque rebond mou, puis partent avec le coussin
        for k, dx in enumerate((-56, 56)):
            hop = 0.0
            for tc, s, _ in C:
                if s == "pillow" and 0 <= t - tc < 0.45:
                    hop = max(hop, (30 + 10 * k) * math.sin(math.pi * (t - tc) / 0.45))
            rx, ry = rot([(px + dx, top - 20 - hop)], px, py, ang)[0]
            if ang:
                ry -= 120 * (t - 3.45) * (1 + k)
                rx += 60 * (t - 3.45) * (k - 0.5)
            p.circle(rx, ry, 20, None, outline=GOLD, width=8)
            p.circle(rx - 3, ry - 3, 14, None, outline=GOLD_L, width=2)

    # ---- le voile en filet
    def net_center(self, t):
        keys = [(5.6, 540), (7.3, 535), (7.6, 580), (8.3, 585), (9.4, 575), (9.9, 500), (10.4, 480),
                (11.0, 480), (11.8, 560), (12.2, 585), (12.8, 585), (13.1, 560), (14.0, 560)]
        return K(keys)(t)

    def net_ends(self, t):
        c = self.net_center(t)
        yy = 1010.0
        if 13.25 <= t:              # le coup sec, puis le voile s'échappe
            yy -= 60 * bump(t, 13.2, 0.12, 0.3)
        return (c - 150, yy), (c + 150, yy)

    def net_curve(self, t):
        l, r = self.net_ends(t)
        bx, by, _, _ = ball(t)
        mid = (l[0] + r[0]) / 2
        sag = 18.0
        if abs(bx - mid) < 150:
            sag = max(sag, by + R - l[1] + 4)
        sag = min(sag, 70)
        return quad(l, (mid, l[1] + 2 * sag), r, 20)

    def draw_net_back(self, p, t):
        if 5.35 <= t < 5.6:
            u = smooth((t - 5.35) / 0.25)
            x, top, h, lean, dy = self.bride_geo(t)
            hx = x - 40
            l, r = self.net_ends(5.6)
            p.tpoly(band(quad((hx, top - 60), ((hx + r[0]) / 2, top + 100 * u), (l[0] + (r[0] - l[0]) * (1 - u), r[1]), 12), 24),
                    TULLE, 0.5)
            return
        if 5.6 <= t < 13.25:
            cur = self.net_curve(t)
            low = [(x, y + 70 + 10 * math.sin(x / 30.0)) for x, y in cur]
            p.tpoly(cur + low[::-1], TULLE, 0.6)

    def draw_net_front(self, p, t):
        if 5.6 <= t < 13.25:
            cur = self.net_curve(t)
            p.tpoly(band(cur, 18), TULLE, 0.75)
            l, r = cur[0], cur[-1]
            p.tpoly([l, (l[0] - 10, l[1] + 80), (l[0] + 40, l[1] + 8)], TULLE, 0.35)
            p.tpoly([r, (r[0] + 10, r[1] + 80), (r[0] - 40, r[1] + 8)], TULLE, 0.35)

    # ---- Bounce et le voile qu'il porte
    def veil_on_ball(self, t):
        return t >= 14.25

    def draw_ball(self, p, t):
        x, y, vx, vy = ball(t)
        S = p.S
        if 13.25 <= t < 14.25:
            self.draw_veil_flying(p, t, x, y)
        base.ball(p.dr, x * S, y * S, R * S)
        if self.veil_on_ball(t):
            self.draw_veil_tail(p, t, x, y, vx, vy)
            self.draw_veil_cap(p, x, y)

    def veil_cap_pts(self, x, y):
        pts = []
        for k in range(11):
            a = math.radians(205 + 130 * k / 10)
            pts.append((x + R * 1.1 * math.cos(a), y + R * 1.1 * math.sin(a)))
        for k in range(11):
            a = math.radians(335 - 130 * k / 10)
            pts.append((x + R * 0.9 * math.cos(a), y - R * 0.22 + R * 0.9 * math.sin(a)))
        return pts

    def draw_veil_cap(self, p, x, y):
        p.tpoly(self.veil_cap_pts(x, y), (250, 250, 255), 0.85)
        for k in range(5):
            p.circle(x - 40 + k * 20, y - R * 1.06 - 7 * math.sin(math.pi * k / 4), 8, (252, 250, 244))

    def draw_veil_tail(self, p, t, x, y, vx, vy):
        """Le voile pend derrière sa tête, du côté opposé à sa course, et ondule."""
        side = -1.0 if vx > 0 else 1.0
        sway = max(-1.0, min(1.0, -vy / 1800.0))
        top_l = (x + side * R * 0.35, y - R * 0.98)
        top_r = (x + side * R * 1.02, y - R * 0.30)
        lift = 70 * sway
        bot_r = (x + side * (R + 70), y + R * 0.9 - lift)
        bot_l = (x + side * (R + 190), y + R * 0.75 - 1.6 * lift)
        wave_ = [(bot_r[0] + (bot_l[0] - bot_r[0]) * k / 6, bot_r[1] + (bot_l[1] - bot_r[1]) * k / 6
                  + 10 * math.sin(k * 1.6 + 7 * t)) for k in range(7)]
        mid = (x + side * (R + 150), y - R * 0.2 - lift)
        p.tpoly([top_l, top_r] + wave_ + [mid], TULLE, 0.6)

    def draw_veil_flying(self, p, t, x, y):
        """Le voile lâché par les mariés monte avec la balle et se pose sur elle (ralenti)."""
        u = smooth((tau(t) - 13.25) / (tau(14.25) - 13.25))
        l, r = self.net_ends(13.25)
        cur = quad(l, ((l[0] + r[0]) / 2, l[1] + 30), r, 16)
        n = len(cur)
        pts = []
        for k, (cx_, cy_) in enumerate(cur):
            tx = x - R * 1.05 + 2.1 * R * k / (n - 1)
            ty = y - R * 0.75 - 40 * math.sin(math.pi * k / (n - 1))
            lag = 1 - u
            pts.append((tx + (cx_ - tx) * lag * lag, ty + (cy_ - ty) * lag + 60 * math.sin(math.pi * u) * math.sin(3 * k / n)))
        p.tpoly(band(pts, 60 - 30 * u), TULLE, 0.75)

    # ---- les répliques, sur les marches
    def draw_subs(self, p, t):
        if self.fs is None:
            self.fs = base.font(54 * p.S)
            self.fb = base.font(72 * p.S)
        narr = self.narr
        if not narr:
            return
        final = [n for n in narr if n["key"].startswith("f")]
        if final and t >= final[0]["start"]:
            rows = ["I now pronounce you…", "husband… and…"]
            if t >= T_ISSUE:
                k = clamp01((t - T_ISSUE) / 0.12)
                p.text(W / 2, 1176, rows[0], self.fs, (255, 255, 255), stroke=5)
                w1 = base.text_w(self.fs, rows[1] + " ") / p.S
                w2 = base.text_w(self.fb, "BOUNCE.") / p.S
                x0 = W / 2 - (w1 + w2) / 2
                p.text(x0 + w1 / 2, 1234, rows[1], self.fs, (255, 255, 255), stroke=5)
                p.text(x0 + w1 + w2 / 2, 1230, "BOUNCE.", self.fb, mix((255, 255, 255), tuple(base.HERO["color"]), k), stroke=6)
            else:
                p.text(W / 2, 1176, rows[0], self.fs, (255, 255, 255), stroke=5)
                p.text(W / 2, 1234, rows[1], self.fs, (255, 255, 255), stroke=5)
            return
        txt = None
        others = [n for n in narr if not n["key"].startswith("f")]
        for i, n in enumerate(others):
            words = len(n["text"].split())
            until = max(n["end"] + 0.3, n["start"] + 0.5 + 0.3 * words)
            if i + 1 < len(others):
                until = min(until, others[i + 1]["start"])
            if n["start"] <= t < until:
                txt = n["text"]
        if not txt:
            return
        rows = self.wrap(txt, self.fs, W * 0.86 * p.S)
        if len(rows) == 1:
            p.text(W / 2, 1205, rows[0], self.fs, (255, 255, 255), stroke=5)
        else:
            for i, row in enumerate(rows[:2]):
                p.text(W / 2, 1176 + 58 * i, row, self.fs, (255, 255, 255), stroke=5)

    @staticmethod
    def wrap(text, f, maxw):
        rows = [""]
        for w in text.split():
            cand = (rows[-1] + " " + w).strip()
            if base.text_w(f, cand) <= maxw or not rows[-1]:
                rows[-1] = cand
            else:
                rows.append(w)
        return rows


# ------------------------------------------------------------------ audio
def render_audio(sim, events, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    react = base.hero_word(cfg["hero_lose"], cfg)
    said = 0
    if name is not None:
        words = base.place_words(events, total_dur, cfg, sim.payoff_t, "lose" if react is not None else None,
                                 narr, (), name_len=len(name) / SR,
                                 react_len=(len(react) / SR if react is not None else 0.8))
        for (t0, kind, _d, tag) in words:
            if kind == "react":
                ak.add(buf, react, t0, gain=1.0)
            else:       # la même voix partout, le dernier compris : aucun effet
                ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=cfg["hero_gain"])
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=1.0)
    v = cfg.get("_hook_voice")
    if v is not None:
        n = min(len(v), len(buf))
        duck = np.ones(len(buf))
        duck[:n] = 0.42
        m = min(int(0.3 * SR), len(buf) - n)
        duck[n:n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, 0.15, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


DEFAULTS = {
    "hook_text_s": 8.0, "hook_top": 0.125, "hook_font_size": 80,
    "narrator_voice": "am_fenrir", "narrator_length": 1.0, "narr_gap_s": 0.35,
    "watermark_y": 0.94, "end_hold_s": 0.3, "narr_tail_s": 0.0,
    "min_duration_s": 61.0, "max_duration_s": 70.0, "show_counter": False,
    "hero_lose": "Oh no.", "hero_shock_s": 1.0,
}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    HOOK["path"] = cfg.get("hook_cache", "")
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.narr = narr
    cfg["_sim"] = sim
    name = base.hero_word(cfg["hero_name"], cfg)
    react = base.hero_word(cfg["hero_lose"], cfg)
    words = base.place_words(events, dur, cfg, sim.payoff_t, "lose", narr, (), name_len=len(name) / SR,
                             react_len=len(react) / SR)
    hits = [round(e[0], 2) for e in events if e[1] == "hit"]
    said = {round(w[0], 2) for w in words}
    summary = {"name": cfg["name"], "duration_s": round(dur, 2), "payoff": bool(sim.payoff),
               "hits": len(hits), "muets": [h for h in hits if h not in said],
               "react": [round(w[0], 2) for w in words if w[1] == "react"],
               "hook_s": round(len(cfg["_hook_voice"]) / SR, 2) if cfg.get("_hook_voice") is not None else None,
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    if "--simulate" in argv:
        summary["hit_times"] = hits
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if "--frames" in argv:
        out = argv[argv.index("--frames") + 1]
        os.makedirs(out, exist_ok=True)
        times = [float(x) for x in argv[argv.index("--frames") + 2].split(",")]
        S = cfg["supersample"]
        hook_lines = base.layout_hook(cfg, S, W * S, H * S, sim.scene_top * H * S)
        for tt in times:
            i = min(range(len(states)), key=lambda k: abs(states[k][0] - tt))
            img = Image.new("RGB", (W * S, H * S), tuple(cfg["bg_color"]))
            dr = ImageDraw.Draw(img)
            base.HERO["pos"] = None
            last = max([h for h in hits if h <= tt] + [-9])
            base.HERO["expr"] = "lose" if tt >= T_PAYOFF else ("shock" if tt - last < cfg["hero_shock_s"] else "calm")
            sim.draw(dr, states[i][1], tt, S)
            if tt < cfg["hook_text_s"]:
                lines, hf, lh, top = hook_lines
                for k, line in enumerate(lines):
                    dr.text((W * S / 2, top + (k + 0.5) * lh), line, fill=(255, 255, 255), anchor="mm", font=hf)
            img.resize((W, H), Image.LANCZOS).save(os.path.join(out, f"f_{tt:05.2f}.png"))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, events, dur, cfg, audio, narr)
        base.render_video(theme, sim, states, cfg, audio, out, events, ())
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, base.ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
