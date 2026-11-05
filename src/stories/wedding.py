"""
Prototype « le mariage » : une chapelle la nuit, en plan fixe de face. Bounce porte les
alliances : il rebondit sur leur petit coussin, qui est mou (muet), et sur le marbre de
l'autel, qui est dur (« Bounce »). L'officiant (la voix du narrateur, sous-titrée en haut)
ne peut lire que pendant les rebonds mous. Les mariés lui glissent le coussin, le bouquet,
le voile en hamac ; le voile finit sur sa tête. « If anyone objects… » : silence, « Bounce ».
Puis « Security. », la poursuite dans les bancs, et l'officiant qui l'attrape : il lui jaillit
des mains dans la cloche, qui n'a pas de battant. Les invités croient aux cloches du mariage ;
la mariée lance son bouquet, qui retombe sur lui ; « I now pronounce you husband and… »
« Bounce. » « Oh no. »

Tout est calculé d'avance sur une seule horloge : les contacts de Bounce tombent aux instants
du plan et les arcs qui les relient sont balistiques, sous une seule gravité (G = 2600).

    python3 src/stories/wedding.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, tempfile, bisect, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
from PIL import Image, ImageDraw
import audio_kit as ak

SR = ak.SR

# ------------------------------------------------------------------ le mot de Bounce
# piper ne rend pas « Bounce » deux fois à la même longueur : on garde un tirage court,
# une fois par processus. Même voix, même mot.
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

# ------------------------------------------------------------------ la voix de l'accroche
# Une seule prise, la plus courte de quelques tirages, coupée au ras du son : la première
# frappe tombe juste à la fin de la voix, la même à chaque processus (fichier hors dépôt).
_orig_hook_voice = ak.hook_voice
HOOK = {"path": ""}


def _trim(x):
    idx = np.where(np.abs(x) > 0.02)[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - 200):idx[-1] + int(0.04 * SR)].copy()


def _read_wav(path):
    with wave.open(path) as w:
        raw = w.readframes(w.getnframes())
        fr = w.getframerate()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def _write_wav(path, x):
    y = np.clip(x, -1, 1)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def steady_hook_voice(text, *a, **k):
    HOOK_CACHE = HOOK["path"]
    if HOOK_CACHE and os.path.exists(HOOK_CACHE):
        return _read_wav(HOOK_CACHE)
    best = None
    for _ in range(4):
        x = _orig_hook_voice(text, *a, **k)
        if x is None:
            break
        x = _trim(x)
        if best is None or len(x) < len(best):
            best = x
    if best is not None and HOOK_CACHE:
        _write_wav(HOOK_CACHE, best)
    return best


ak.hook_voice = steady_hook_voice

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
R = 95.0
CX = 540.0
FRONT = 1330.0                 # ligne avant du marbre : Bounce et le coussin, devant les mariés
FEET = 1280.0                  # où se tiennent les mariés
DAIS = 1180.0                  # l'estrade de l'officiant
PIVOT = (540.0, 405.0)         # la cloche
STEP1, STEP2 = 1385.0, 1445.0  # dessus des marches
CARPET = 1600.0
PIL_W, PIL_H = 150.0, 36.0
Y = dict(marble=FRONT - R, pillow=FRONT - PIL_H - R, held=1230.0 - R, veil=1105.0, bouquet=1041.0,
         stems=1068.0, book=853.0, hands=855.0, bell=525.0, step1=STEP1 - R, step2=STEP2 - R,
         hat=1275.0, usher=1041.0, tophat=1250.0, carpet=CARPET - R)
HARD = {"marble", "book", "bell", "step1", "step2", "usher", "tophat", "stems"}
SOFT_SINK = {"pillow": 20.0, "held": 22.0, "veil": 0.0, "bouquet": 18.0, "hat": 18.0, "carpet": 16.0, "hands": 12.0}

# les contacts de Bounce : (t, surface, x)
C = [(-0.65, "pillow", 520), (0.15, "pillow", 520), (0.95, "pillow", 520),
     (1.95, "marble", 680), (2.95, "marble", 690),
     (4.05, "pillow", 680), (4.80, "pillow", 680),
     (5.65, "marble", 520), (6.55, "marble", 370),
     (7.50, "pillow", 370), (8.25, "pillow", 370),
     (9.05, "marble", 525), (10.00, "pillow", 370), (10.90, "marble", 525),
     (11.80, "marble", 575),
     (12.75, "bouquet", 640), (13.65, "bouquet", 640), (14.60, "stems", 640),
     (15.45, "marble", 540),
     (16.30, "veil", 540), (17.05, "veil", 540), (17.85, "veil", 540),
     (19.00, "marble", 560), (19.95, "marble", 525), (20.80, "book", 540), (21.70, "marble", 560),
     (22.65, "pillow", 370), (23.40, "pillow", 370), (24.15, "pillow", 370),
     (25.00, "marble", 540),
     (25.90, "held", 540), (26.65, "held", 540), (27.40, "held", 540), (28.15, "held", 540),
     (28.90, "held", 540), (29.65, "held", 540), (30.40, "held", 540), (31.00, "held", 540),
     (31.60, "held", 540),
     (32.68, "marble", 380),
     (33.55, "pillow", 540), (34.60, "marble", 700),
     (35.50, "pillow", 540), (36.65, "marble", 380), (37.55, "marble", 370),
     (38.45, "pillow", 540), (39.50, "marble", 700),
     (40.40, "step1", 610), (41.25, "step2", 530), (42.30, "hat", 110),
     (43.05, "usher", 245), (43.90, "usher", 590), (44.95, "tophat", 375),
     (45.80, "carpet", 545), (46.50, "step2", 545), (47.40, "marble", 700),
     (48.10, "hands", 540), (48.48, "bell", 540),
     (49.18, "pillow", 540), (49.80, "pillow", 540), (50.40, "bell", 540),
     (51.10, "pillow", 540), (51.75, "pillow", 540), (52.40, "pillow", 540),
     (53.20, "marble", 700), (54.10, "pillow", 540), (54.95, "marble", 700),
     (55.85, "pillow", 540), (56.75, "marble", 380),
     (57.65, "pillow", 540), (58.30, "pillow", 540), (58.95, "pillow", 540), (59.60, "pillow", 540),
     (60.65, "marble", 385),
     (61.50, "pillow", 540), (62.15, "pillow", 540), (62.75, "pillow", 540), (63.35, "pillow", 540),
     (63.95, "pillow", 540)]
T_FINAL = 60.65
T_END = 62.95
BELLS = [t for t, s, _ in C if s == "bell"]

LINES = [(4.10, "Dearly beloved."), (7.50, "We are gathered here today,"), (10.00, "in silence."),
         (12.80, "To join this man and this woman,"), (16.50, "in holy matrimony."),
         (22.65, "Where was I?"), (23.70, "Skipping ahead."),
         (25.95, "If anyone objects to this marriage,"), (28.35, "speak now,"),
         (29.75, "or forever hold your peace."),
         (33.60, "Who said that?"), (35.55, "On what grounds?"), (38.50, "Security."),
         (51.30, "No, no. That was an objection."), (57.70, "Close enough."),
         (58.40, "I now pronounce you husband and…")]

# ------------------------------------------------------------------ couleurs
BG = (8, 8, 12)
WALL = (22, 20, 34)
WALL2 = (30, 27, 44)
MARBLE = (196, 192, 204)
MARBLE_D = (150, 146, 160)
STEP_C = (120, 116, 132)
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


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))


def bump(t, t0, up=0.08, down=0.35):
    """Une impulsion : 0, monte vite jusqu'à 1, redescend."""
    u = t - t0
    if u < 0 or u > up + down:
        return 0.0
    if u < up:
        return math.sin(0.5 * math.pi * u / up)
    return 0.5 * (1 + math.cos(math.pi * (u - up) / down))


class K:
    """Une valeur par images clés (adoucies) : K([(t, v), ...])."""

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


# ------------------------------------------------------------------ la trajectoire
CT = [c[0] for c in C]


def cy(c):
    return Y[c[1]]


def ball_raw(t):
    """(x, y, vx, vy) du centre de Bounce sur l'arc en cours."""
    i = max(0, min(len(C) - 2, bisect.bisect_right(CT, t) - 1))
    (t0, s0, x0), (t1, s1, x1) = C[i], C[i + 1]
    y0, y1 = Y[s0], Y[s1]
    T = t1 - t0
    u = t - t0
    vy = (y1 - y0) / T - 0.5 * G * T
    vx = (x1 - x0) / T
    return x0 + vx * u, y0 + vy * u + 0.5 * G * u * u, vx, vy + G * u


def sink(t):
    """Enfoncement de Bounce dans une surface molle, autour du contact."""
    s = 0.0
    i = bisect.bisect_right(CT, t)
    for j in (i - 1, i):
        if 0 <= j < len(C):
            tc, surf, _ = C[j]
            d = SOFT_SINK.get(surf, 0.0)
            if d:
                s = max(s, d * clamp01(1 - abs(t - tc) / 0.09))
    return s


def ball(t):
    x, y, vx, vy = ball_raw(t)
    return x, y + sink(t), vx, vy


def contact_near(t, surf, win=0.12):
    i = bisect.bisect_right(CT, t)
    for j in (i - 1, i):
        if 0 <= j < len(C) and C[j][1] == surf and abs(C[j][0] - t) < win:
            return C[j]
    return None


def soft_contacts(surf, t0=-9, t1=99):
    return [c for c in C if c[1] == surf and t0 <= c[0] <= t1]


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
        """Un polygone translucide (le tulle)."""
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
    """Rectangle aux coins arrondis, en points."""
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
    """Un ruban d'épaisseur w le long d'une courbe (liste de points)."""
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


# ------------------------------------------------------------------ la cloche
BELL_PROFILE = [(15, 60), (28, 76), (60, 88), (110, 100), (150, 118), (178, 140), (192, 150), (198, 150)]


def bell_angle(t):
    a = 0.0
    for tb in BELLS:
        u = t - tb
        if u > 0:
            amp = 0.11 if tb < 49 else 0.085
            a += amp * math.exp(-u / 2.2) * math.sin(2 * math.pi * u / 1.45)
    # le frôlement fait trembler le nœud, pas la cloche
    return a


def bell_poly(t):
    px, py = PIVOT
    right = [(px + w, py + d) for d, w in BELL_PROFILE]
    left = [(px - w, py + d) for d, w in BELL_PROFILE[::-1]]
    return rot(right + left, px, py, bell_angle(t))


def bell_flash(t):
    return max([bump(t, tb, 0.05, 0.9) for tb in BELLS] + [0.0])


# ------------------------------------------------------------------ les personnages
# Le marié
GX = K([(0, 225), (3.0, 225), (3.35, 360), (3.75, 360), (4.2, 225), (25.05, 225), (25.55, 425),
        (32.9, 425), (33.6, 225)])
G_KNEEL = K([(0, 0), (25.4, 0), (25.75, 1.0), (32.75, 1.0), (33.3, 0)])
G_FOOT = K([(0, 0), (3.2, 0), (3.3, 1), (3.62, 1), (3.75, 0), (7.05, 0), (7.15, 0.55), (7.35, 0.55), (7.5, 0)])
G_LEAN = K([(0, 0), (16.2, 0), (16.35, 0.08), (17.0, 0.04), (17.85, 0), (18.2, -0.06), (19.2, 0),
            (56.7, 0), (56.85, -0.12), (57.6, -0.05), (60.55, -0.05), (60.75, 0.1), (63.5, 0.1)])
# La mariée
BX = 850.0
B_KNEEL = K([(0, 0), (25.4, 0), (25.75, 1.0), (32.75, 1.0), (33.3, 0)])
B_X = K([(0, 850), (25.05, 850), (25.55, 660), (32.9, 660), (33.7, 850)])
B_LEAN = K([(0, 0), (16.2, 0), (16.35, -0.08), (17.0, -0.04), (17.85, 0), (18.2, 0.05), (19.2, 0),
            (52.3, 0), (52.8, 0.10), (53.55, 0.16), (53.75, -0.12), (54.3, 0),
            (54.95, 0), (55.1, 0.12), (55.8, 0.05), (60.55, 0.05), (60.75, -0.1), (63.5, -0.1)])

JOLTS = [(1.95, 1.0), (32.68, 1.25), (48.48, 0.55)]


def jolt(t, k=1.0):
    return -26.0 * k * sum(a * bump(t, tj, 0.07, 0.4) for tj, a in JOLTS)


def pillow_state(t):
    """(x, y du centre, tenu ?) du coussin des alliances."""
    if t < 3.25:
        x = 520.0
    elif t < 3.65:
        x = 520 + 160 * smooth((t - 3.25) / 0.4)
    elif t < 6.75:
        x = 680.0
    elif t < 7.2:
        u = (t - 6.75) / 0.45
        x = 680 - 310 * (1 - (1 - u) ** 2)
    elif t < 25.2:
        x = 370.0
    elif t < 25.75:
        x = 370 + 170 * smooth((t - 25.2) / 0.55)
    else:
        x = 540.0
    floor_y = FRONT - PIL_H / 2
    held_y = 1230.0 + PIL_H / 2
    if 25.2 <= t < 25.75:
        y = floor_y + (held_y - floor_y) * smooth((t - 25.2) / 0.4)
    elif 25.75 <= t < 32.7:
        y = held_y
    elif 32.7 <= t < 33.05:
        u = (t - 32.7) / 0.35
        y = held_y + (floor_y - held_y) * u * u
    else:
        y = floor_y
    held = 25.4 <= t < 32.7
    if held:      # les bras plient à chaque rebond
        c = contact_near(t, "held", 0.2)
        if c:
            y += 16 * clamp01(1 - abs(t - c[0]) / 0.18)
    return x, y, held


def ring_offsets(t):
    """Hauteur du saut des deux alliances sur le coussin."""
    outs = []
    for k, (h0, d) in enumerate(((1.0, 0.0), (0.8, 0.04))):
        hy = 0.0
        for tc, s, _ in C:
            if s not in ("pillow", "held") or tc > t or t - tc > 0.7:
                continue
            h = (34 + 26 * (tc < 2)) * h0
            if s == "held":
                h *= 1.3
            Td = 2 * math.sqrt(2 * h / G)
            u = t - tc - d
            if 0 <= u <= Td:
                hy = max(hy, h * 4 * (u / Td) * (1 - u / Td))
        outs.append(hy)
    return outs


# l'officiant : penché, mains, livre
O_LEAN = K([(0, 0), (5.6, 0), (5.7, -0.03), (6.4, 0), (10.0, 0), (10.3, 0.07), (10.85, 0.07), (11.1, 0),
            (17.4, 0), (17.6, -0.16), (18.5, -0.05), (19.0, 0),
            (28.3, 0), (28.6, 0.1), (31.9, 0.1), (32.3, 0.0), (35.5, 0), (35.8, 0.08), (36.6, 0),
            (48.5, 0), (48.7, -0.12), (50.0, -0.05), (51.0, 0),
            (57.6, 0), (58.1, 0.05), (63.5, 0.05)])
O_SLUMP = K([(0, 0), (57.6, 0), (58.0, 1.0), (58.3, 0.6), (63.5, 0.6)])


def off_hands(t):
    """Mains de l'officiant (gauche, droite) et mode du livre."""
    rest = ((500, 958), (580, 958))
    book = "open"
    hands = rest
    if 1.95 <= t < 2.95:
        book = "closed"
    if 20.8 <= t < 21.05:
        book = "fall"
    elif 21.05 <= t < 21.9:
        book = "dais"
        hands = ((520, 1120), (560, 1120)) if t > 21.35 else rest
    elif 21.9 <= t < 22.3:
        u = smooth((t - 21.9) / 0.4)
        hands = ((520, 1120 - 162 * u), (560, 1120 - 162 * u))
    if 22.4 <= t < 24.7:
        book = "flip"
    if 38.4 <= t < 39.2:
        hands = ((500, 958), (640, 1040 - 60 * smooth((t - 38.4) / 0.25)))
        book = "side"
    if 39.2 <= t < 47.3:
        book = "side"
    if 47.3 <= t < 48.2:
        book = "side"
        u = smooth((t - 47.3) / 0.6)
        hands = ((500 - 10 * u, 958 - 8 * u), (580 + 10 * u, 958 - 8 * u))
    if 48.2 <= t < 51.0:
        book = "side"
        u = smooth((t - 48.4) / 0.4)
        hands = ((490, 950 + 20 * u), (590, 950 + 20 * u))
    if 51.0 <= t < 53.0:
        book = "side"
        u = smooth((t - 51.05) / 0.3) * (1 - smooth((t - 52.7) / 0.3))
        hands = ((490 - 40 * u, 960 - 90 * u), (590 + 40 * u, 960 - 90 * u))
    if 53.0 <= t < 57.6:
        book = "open"
    if 57.6 <= t < 58.25:
        book = "closed"
    if t >= 58.25:
        book = "side"
        u = smooth((t - 58.3) / 0.4)
        hands = ((500 - 70 * u, 960 - 10 * u), (580 + 70 * u, 960 - 10 * u))
    return hands, book


# les invités : (nom, x assis, couleur, forme)
GUESTS = {
    "lady": (110.0, (176, 140, 206)),
    "orange": (245.0, (238, 140, 62)),
    "teal": (375.0, (60, 186, 190)),
    "green": (790.0, (74, 168, 92)),
}
HEAD_Y = 1452.0
STAND_Y = 1180.0
PARTY_Y = 1395.0


def guest_state(name, t):
    """(x, y du centre de la tête, bras en l'air 0..1, enfoncé 0..1)."""
    x0, _ = GUESTS[name]
    x, y = x0, HEAD_Y
    arms = 0.0
    # sursauts
    y += jolt(t, 1.4)
    # les têtes qui se penchent les unes vers les autres, qui se tournent vers la balle
    lean = 0.0
    if 10.95 <= t < 12.3:
        lean = 10 * smooth((t - 10.95) / 0.3) * (1 - smooth((t - 12.0) / 0.3)) * (1 if x0 < 300 else -1)
    if 26.6 <= t < 32.6 or 34.6 <= t < 36.0:
        lean = 14 * (1 if x0 < 540 else -1) * smooth((t - (26.6 if t < 33 else 34.6)) / 0.5)
    x += lean
    if 17.9 <= t < 18.9:
        y -= 10 * math.sin(math.pi * (t - 17.9))
    # les deux grands invités
    if name == "orange":
        st = smooth((t - 42.3) / 0.45) * (1 - smooth((t - 45.45) / 0.35))
        y = y + (STAND_Y - HEAD_Y) * st + (PARTY_Y - HEAD_Y) * smooth((t - 50.4) / 0.4)
        if 43.05 <= t < 43.3:
            y += 14 * math.sin(math.pi * (t - 43.05) / 0.25)
        if 44.95 <= t < 45.5:
            x = x0 + 150 * smooth((t - 45.0) / 0.35) - 150 * smooth((t - 45.4) / 0.4)
        arms = smooth((t - 42.4) / 0.3) * (1 - smooth((t - 45.4) / 0.3))
    if name == "green":
        st = smooth((t - 39.4) / 0.45) * (1 - smooth((t - 45.45) / 0.35))
        y = y + (STAND_Y - HEAD_Y) * st + (PARTY_Y - HEAD_Y) * smooth((t - 50.4) / 0.4)
        gx = K([(0, x0), (40.6, x0), (41.4, 590), (44.95, 590), (45.3, 475), (45.6, 690), (46.4, x0)])
        x = gx(t) + lean
        if 43.9 <= t < 44.15:
            y += 14 * math.sin(math.pi * (t - 43.9) / 0.25)
        arms = smooth((t - 39.5) / 0.3) * (1 - smooth((t - 45.4) / 0.3))
    if name == "lady":
        if 42.25 <= t < 42.75:
            y += 18 * math.sin(math.pi * (t - 42.25) / 0.5)
        st = smooth((t - 49.75) / 0.35)
        y = y + (PARTY_Y - HEAD_Y) * st
    if name == "teal":
        st = smooth((t - 50.4) / 0.35)
        y = y + (PARTY_Y - HEAD_Y) * st
    # la fête : tout le monde debout saute, chacun à son rythme
    if 50.45 <= t < 54.95:
        ph = {"lady": 0.0, "orange": 0.23, "teal": 0.41, "green": 0.13}[name]
        per = {"lady": 0.52, "orange": 0.61, "teal": 0.47, "green": 0.57}[name]
        u = ((t - 50.45 + ph) % per) / per
        amp = 34 * (1 - smooth((t - 54.5) / 0.4))
        y -= amp * 4 * u * (1 - u)
        arms = max(arms, 1.0 - smooth((t - 54.5) / 0.4))
    if name == "lady" and 49.8 <= t < 50.45:
        arms = 0.6 + 0.4 * math.sin(t * 30)
    if 53.6 <= t < 54.4:
        arms = 1.0
    if t >= 54.95:
        x += 12 * (1 if x0 < 540 else -1) * smooth((t - 54.95) / 0.4)
    return x, y, arms


def lady_hat(t):
    """Le chapeau lilas : sur la tête, envolé à l'objection, lancé à la fête."""
    x, y, _ = guest_state("lady", t)
    hy = 0.0
    for t0, h in ((32.7, 120.0), (54.32, 220.0)):
        Td = 2 * math.sqrt(2 * h / 1500.0)
        u = t - t0
        if 0 <= u <= Td:
            hy = max(hy, h * 4 * (u / Td) * (1 - u / Td))
    dent = 0.0
    if 42.2 <= t < 42.45:
        dent = 16 * math.sin(math.pi * (t - 42.2) / 0.25)
    return x, y - 44 - hy, dent


def tophat(t):
    """Le haut-de-forme du turquoise : (x, y du bas, angle)."""
    x, y, _ = guest_state("teal", t)
    if t < 44.95:
        return x, y - 34, 0.0
    u = t - 44.95
    # il s'envole vers la gauche, tourne, retombe derrière le banc
    return x - 260 * u, y - 34 - 900 * u + 0.5 * 2600 * u * u, -6.5 * u


# ------------------------------------------------------------------ voile, bouquet, alliance
def stems_flight(t):
    """La botte de tiges lancée : None, ou (x, y, angle) en vol."""
    t0, t1 = 53.65, 54.45
    if t < t0 or t >= t1:
        return None
    x0, y0 = 800.0, 850.0
    bx, by, _, _ = ball(t1)
    x1, y1 = bx + 8, by - R - 20
    T = t1 - t0
    u = t - t0
    vy = (y1 - y0) / T - 0.5 * G * T
    return x0 + (x1 - x0) * u / T, y0 + vy * u + 0.5 * G * u * u, -4.0 * u


def ring_flight(t):
    """L'alliance qui saute du coussin et retombe sur sa tête."""
    t0, t1 = 61.5, 62.32
    if t < t0:
        return None
    x0, y0 = 540 + 62, FRONT - PIL_H - 20
    if t >= t1:
        return "on"
    bx, by, _, _ = ball(t1)
    x1, y1 = bx - 28, by - R - 12
    T = t1 - t0
    u = t - t0
    vy = (y1 - y0) / T - 0.5 * G * T
    return x0 + (x1 - x0) * u / T, y0 + vy * u + 0.5 * G * u * u


# ------------------------------------------------------------------ les pétales
def make_petals():
    rng = np.random.default_rng(11)
    ps = []
    for tb, n in ((12.75, 26), (13.65, 34)):
        for _ in range(n):
            a = rng.uniform(-2.6, -0.5)
            sp = rng.uniform(250, 620)
            ps.append(dict(t0=tb, x=640 + rng.uniform(-30, 30), y=1150 + rng.uniform(-20, 10),
                           vx=math.cos(a) * sp, vy=math.sin(a) * sp, ph=rng.uniform(0, 6.28),
                           col=PETALS[int(rng.integers(0, len(PETALS)))], s=rng.uniform(7, 12),
                           floor=FEET + rng.uniform(-20, 60)))
    return ps


PETAL = make_petals()


def petal_pos(p, t):
    """Pétale freiné par l'air : vitesse qui tend vers une chute lente, qui se balance."""
    u = t - p["t0"]
    if u < 0:
        return None
    k = 4.0
    vt = 110.0
    x = p["x"] + p["vx"] / k * (1 - math.exp(-k * u)) + 18 * math.sin(2.2 * u + p["ph"])
    y = p["y"] + vt * u + (p["vy"] - vt) / k * (1 - math.exp(-k * u))
    if y >= p["floor"]:
        y = p["floor"]
    return x, y


# ------------------------------------------------------------------ la scène
class Sim:
    scene_top = 0.215

    def __init__(self, cfg, rng):
        self.cfg = cfg
        HOOK["path"] = cfg.get("hook_cache", "")
        self.clock = 0.0
        self.snap_t = 0.0
        self.done = False
        self.payoff = False
        self.payoff_t = None
        self.lines = [(t, s, f"l{k}") for k, (t, s) in enumerate(LINES)]
        self.replies = []
        self.narr = []
        self.fs = None
        self.ci = bisect.bisect_left(CT, 0.0)
        self.outcome = "Bounce, voilé et bouqueté, se fait marier au marié : « husband and… Bounce. » « Oh no. »"

    def hero_mood(self):
        return "lose" if self.payoff else None

    def step(self, dt):
        t0 = self.clock
        evs = []
        # un contact est annoncé sur l'image qui suit son instant : l'horodatage du moteur
        # (début de l'image) ne tombe jamais avant le contact
        while self.ci < len(C) and C[self.ci][0] < t0:
            tc, s, x = C[self.ci]
            if tc >= t0 - dt - 1e-9 and s in HARD:
                tag = "bell" if s == "bell" else ("final" if abs(tc - T_FINAL) < 1e-6 else "n")
                evs.append(("hit", tag))
                if abs(tc - T_FINAL) < 1e-6:
                    evs.append(("payoff", "husband and bounce"))
                    self.payoff = True
            self.ci += 1
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
        self.draw_officiant(p, t)
        self.draw_bride_veil_back(p, t)
        self.draw_groom(p, t)
        self.draw_bride(p, t)
        self.draw_pillow(p, t)
        self.draw_petals(p, t)
        self.draw_guests(p, t)
        self.draw_net_back(p, t)
        self.draw_ball(p, t)
        self.draw_net_front(p, t)
        self.draw_rings(p, t)
        self.draw_off_hands_front(p, t)
        self.draw_bell(p, t)
        self.draw_flying(p, t)
        self.draw_subs(p, t)

    def draw_room(self, p, t):
        p.rect(0, 0, W, FRONT, BG)
        p.rect(60, 330, W - 60, 1240, WALL)
        # pierres, à peine visibles
        for row in range(14):
            yy = 360 + row * 64
            off = 0 if row % 2 else 55
            for k in range(-1, 10):
                xx = 60 + off + k * 110
                p.rect(xx + 4, yy + 4, xx + 106, yy + 60, WALL2, r=6)
        # l'ombre gagne les bords
        for k in range(10):
            a = 0.09 * (10 - k)
            col = mix(WALL, BG, 0.65 + 0.035 * k)
            p.rect(60 + k * 16, 330, 60 + k * 16 + 16, 1240, mix(col, BG, a))
            p.rect(W - 60 - k * 16 - 16, 330, W - 60 - k * 16, 1240, mix(col, BG, a))
        # l'estrade et le marbre
        p.rect(0, 1240, W, FRONT, MARBLE)
        for k in range(6):
            p.line([(40 + k * 190, 1240), (10 + k * 190 + 60, FRONT)], MARBLE_D, 2)
        p.rect(0, 1240, W, 1252, mix(MARBLE, BG, 0.35))
        p.rect(430, DAIS, 650, 1240, MARBLE_D)
        p.rect(430, DAIS, 650, DAIS + 8, MARBLE)
        p.rect(0, FRONT, W, FRONT + 18, MARBLE_D)
        p.rect(300, FRONT + 18, 780, STEP1, mix(MARBLE, STEP_C, 0.5))
        p.rect(300, STEP1, 780, STEP1 + 14, STEP_C)
        p.rect(300, STEP1 + 14, 780, STEP2, mix(MARBLE, STEP_C, 0.7))
        p.rect(300, STEP2, 780, STEP2 + 14, mix(STEP_C, BG, 0.3))
        p.rect(0, FRONT + 18, 300, H, BG)
        p.rect(780, FRONT + 18, W, H, BG)
        p.rect(300, STEP2 + 14, 780, H, BG)
        # le tapis rouge de l'allée
        dent = 0.0
        c = contact_near(t, "carpet", 0.15)
        if c:
            dent = 14 * clamp01(1 - abs(t - c[0]) / 0.15)
        p.poly([(468, STEP2 + 14), (612, STEP2 + 14), (640, H), (440, H)], CARPET_C)
        if dent:
            p.ellipse(545, CARPET + 4, 70, 4 + dent, mix(CARPET_C, BG, 0.45))
        # la poutre
        p.rect(330, 382, 750, 404, WOOD)
        p.rect(330, 382, 750, 388, mix(WOOD, (255, 255, 255), 0.15))

    def draw_window(self, p, t):
        fl = bell_flash(t)
        x0, x1, ytop, yspr, ybot = 350.0, 730.0, 470.0, 640.0, 1070.0
        cx = (x0 + x1) / 2

        # ogive : deux arcs de cercle
        def ogive(ins):
            """Arc brisé : deux arcs de cercle centrés sur les naissances opposées, aplatis."""
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
        glow = mix((60, 50, 90), (150, 130, 80), fl)
        p.poly(ogive(-26), mix(WALL, glow, 0.55))
        p.poly(ogive(-10), (34, 30, 48))
        p.poly(ogive(0), (18, 16, 26))
        # losanges
        cols = [(46, 92, 200), (190, 40, 60), (220, 170, 50), (40, 140, 170), (120, 60, 170)]
        rng = np.random.default_rng(5)
        dw, dh = 54.0, 70.0
        win = ogive(6)
        xs = [q[0] for q in win]
        for j in range(-1, int((ybot - ytop) / (dh / 2)) + 2):
            for i in range(-1, int((x1 - x0) / dw) + 2):
                px = x0 + i * dw + (dw / 2 if j % 2 else 0)
                py = ytop + j * dh / 2
                col = cols[int(rng.integers(0, len(cols)))]
                if not self._inside(px, py, win):
                    continue
                k = 0.62 + 0.38 * fl
                cc = mix(dim(col, 0.55), col, k)
                if fl > 0:
                    cc = mix(cc, (255, 240, 200), 0.35 * fl)
                p.poly([(px, py - dh / 2 + 4), (px + dw / 2 - 4, py), (px, py + dh / 2 - 4), (px - dw / 2 + 4, py)], cc)
        # meneau central
        p.rect(cx - 5, yspr - 40, cx + 5, ybot, (18, 16, 26))
        p.rect(x0, 860, x1, 868, (18, 16, 26))

    @staticmethod
    def _inside(x, y, poly):
        n = len(poly); c = False
        for i in range(n):
            (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
            if (ya > y) != (yb > y) and x < (xb - xa) * (y - ya) / ((yb - ya) or 1e-9) + xa:
                c = not c
        return c

    # ---- l'officiant
    def officiant_pts(self, t):
        lean = O_LEAN(t)
        sl = O_SLUMP(t)
        jy = jolt(t, 0.8)
        h = 290 - 26 * sl

        def P(x, y):
            hh = (DAIS - y)
            return (x + lean * hh, y + jy * hh / 290 + (290 - h) * hh / 290)
        return P

    def draw_officiant(self, p, t):
        P = self.officiant_pts(t)
        body = [P(x, y) for x, y in rpoly(470, 890, 610, DAIS, 50)]
        p.poly(body, ROBE)
        p.poly([P(470, 1120), P(610, 1120), P(610, DAIS), P(470, DAIS)], ROBE_D)
        p.poly([P(510, 900), P(526, 900), P(526, 1150), P(510, 1150)], STOLE)
        p.poly([P(554, 900), P(570, 900), P(570, 1150), P(554, 1150)], STOLE)
        p.poly([P(505, 888), P(575, 888), P(570, 904), P(510, 904)], (250, 250, 250))
        hx, hy = P(540, 846)
        p.circle(hx, hy, 42, SKIN)
        hands, book = off_hands(t)
        catching = 47.95 <= t < 48.35
        shoulders = (P(492, 918), P(588, 918))
        if not catching:
            for s, hnd in zip(shoulders, hands):
                p.line([s, hnd], ROBE_D, 20)
                p.circle(hnd[0], hnd[1], 12, SKIN)
        self.draw_book(p, t, hands, book, P)

    def draw_off_hands_front(self, p, t):
        if not (47.95 <= t < 48.35):
            return
        P = self.officiant_pts(t)
        bx, by, _, _ = ball(min(t, 48.16))     # la balle part, les mains restent
        shoulders = (P(492, 918), P(588, 918))
        # deux mains bien visibles, posées sur les flancs de la balle
        hands = ((bx - 84, by + 18), (bx + 84, by + 18))
        for s, hnd in zip(shoulders, hands):
            p.line([s, hnd], ROBE, 24)
            p.line([s, hnd], mix(ROBE, (255, 255, 255), 0.15), 10)
            p.ellipse(hnd[0], hnd[1], 20, 26, SKIN)
            p.ellipse(hnd[0], hnd[1], 20, 26, None, outline=(150, 110, 80), width=3)

    def draw_book(self, p, t, hands, book, P):
        if book in ("open", "flip", "closed"):
            cx = (hands[0][0] + hands[1][0]) / 2
            cyy = (hands[0][1] + hands[1][1]) / 2 - 8
            c = contact_near(t, "book", 0.0)
            if book == "closed":
                p.rect(cx - 50, cyy - 10, cx + 50, cyy + 12, BOOK_C, r=3)
                return
            p.poly([(cx - 80, cyy - 4), (cx, cyy + 4), (cx, cyy + 16), (cx - 80, cyy + 8)], BOOK_C)
            p.poly([(cx + 80, cyy - 4), (cx, cyy + 4), (cx, cyy + 16), (cx + 80, cyy + 8)], BOOK_C)
            p.poly([(cx - 74, cyy - 8), (cx - 2, cyy), (cx - 2, cyy + 8), (cx - 74, cyy + 1)], (248, 246, 236))
            p.poly([(cx + 74, cyy - 8), (cx + 2, cyy), (cx + 2, cyy + 8), (cx + 74, cyy + 1)], (248, 246, 236))
            if book == "flip":
                for k in range(3):
                    ph = ((t * 7.0 + k / 3) % 1.0)
                    if t > 23.4 and t < 23.75:
                        ph = ((t * 3.0 + k / 3) % 1.0)
                    a = math.pi * ph
                    ex = cx + 72 * math.cos(a)
                    ey = cyy - 4 - 34 * math.sin(a)
                    p.poly([(cx, cyy), (ex, ey), (ex, ey + 8), (cx, cyy + 8)], (232, 230, 220))
        elif book == "fall":
            u = (t - 20.8) / 0.25
            cx, cyy = 540 + 20 * u, 952 + 220 * u * u
            p.poly(rot([(cx - 70, cyy - 10), (cx + 70, cyy - 10), (cx + 70, cyy + 8), (cx - 70, cyy + 8)], cx, cyy, 0.5 * u), BOOK_C)
            p.poly(rot([(cx - 66, cyy - 14), (cx + 66, cyy - 14), (cx + 66, cyy - 8), (cx - 66, cyy - 8)], cx, cyy, 0.5 * u), (248, 246, 236))
        elif book == "dais":
            p.rect(484, DAIS - 16, 616, DAIS, BOOK_C, r=3)
            p.rect(488, DAIS - 20, 612, DAIS - 14, (248, 246, 236))
        elif book == "side":
            hx, hy = hands[0]
            sx, sy = P(478, 1010)
            p.rect(sx - 14, sy - 44, sx + 12, sy + 44, BOOK_C, r=3)

    # ---- le marié
    def groom_geo(self, t):
        x = GX(t)
        k = G_KNEEL(t)
        h = 370 * (1 - 0.4 * k)
        top = FEET - h + jolt(t, 1.0) * (1 - 0.3 * k)
        lean = G_LEAN(t)
        return x, top, h, lean

    def draw_groom(self, p, t):
        x, top, h, lean = self.groom_geo(t)

        def P(px, py):
            return (px + lean * (FEET - py), py)
        body = [P(a, b) for a, b in rpoly(x - 65, top, x + 65, FEET, 26)]
        p.poly(body, NAVY)
        p.poly([P(x - 26, top + 2), P(x + 26, top + 2), P(x, top + 74)], (240, 240, 244))
        p.poly([P(x - 22, top + 8), P(x, top + 16), P(x - 22, top + 24)], (14, 14, 18))
        p.poly([P(x + 22, top + 8), P(x, top + 16), P(x + 22, top + 24)], (14, 14, 18))
        hx, hy = P(x, top - 44)
        p.circle(hx, hy, 46, SKIN)
        # bras
        sh = (P(x - 52, top + 30), P(x + 52, top + 30))
        hands = self.groom_hands(t, x, top, P)
        for s, hnd in zip(sh, hands):
            p.line([s, hnd], NAVY_D, 20)
            p.circle(hnd[0], hnd[1], 12, SKIN)
        # chaussure (qui pousse le coussin)
        f = G_FOOT(t)
        fx = x + 30 + f * (pillow_state(t)[0] - 75 - (x + 30) - 10)
        if 7.0 <= t < 7.6:
            fx = x + 30 + f * 70
        p.ellipse(fx, FEET - 4, 30, 11, (14, 14, 18))
        if G_KNEEL(t) < 0.5:
            p.ellipse(x - 30, FEET - 4, 30, 11, (14, 14, 18))

    def groom_hands(self, t, x, top, P):
        rest = (P(x - 64, top + 160), P(x + 64, top + 160))
        if 15.5 <= t < 18.25:
            u = smooth((t - 15.5) / 0.35)
            nl, nr = self.net_ends(t)
            return (rest[0], (rest[1][0] + (nl[0] - rest[1][0]) * u, rest[1][1] + (nl[1] - rest[1][1]) * u))
        if 25.4 <= t < 32.7:
            px, py, _ = pillow_state(t)
            u = smooth((t - 25.4) / 0.3)
            tgt = (px - PIL_W / 2 + 6, py)
            return (rest[0], (rest[1][0] + (tgt[0] - rest[1][0]) * u, rest[1][1] + (tgt[1] - rest[1][1]) * u))
        if 32.7 <= t < 33.3:
            return (P(x - 70, top - 10), P(x + 70, top - 10))
        if 50.5 <= t < 54.9 and False:
            return rest
        if t >= 60.6:
            u = smooth((t - 60.6) / 0.3)
            return (rest[0], (rest[1][0] + 30 * u, rest[1][1] - 40 * u))
        return rest

    # ---- la mariée
    def bride_geo(self, t):
        x = B_X(t)
        k = B_KNEEL(t)
        h = 365 * (1 - 0.4 * k)
        top = FEET - h + jolt(t, 1.0) * (1 - 0.3 * k)
        return x, top, h, B_LEAN(t)

    def bride_P(self, t):
        x, top, h, lean = self.bride_geo(t)
        return lambda px, py: (px + lean * (FEET - py), py)

    def veil_on_bride(self, t):
        return t < 15.45

    def draw_bride_veil_back(self, p, t):
        if not self.veil_on_bride(t):
            return
        x, top, h, lean = self.bride_geo(t)
        P = self.bride_P(t)
        lift = 40 * bump(t, 1.95, 0.08, 0.6) + 50 * bump(t, 32.68, 0.08, 0.6)
        hx, hy = P(x, top - 42)
        tail = [(hx - 10, hy - 40), (hx + 40, hy - 30), (x + 84, FEET - lift * 0.3), (x + 36, FEET),
                (x + 20, top + 60)]
        if 15.0 <= t < 15.45:
            # elle l'enlève : il glisse vers ses mains
            u = smooth((t - 15.0) / 0.45)
            tail = [(a + (720 - a) * u * 0.6, b + (1130 - b) * u * 0.6) for a, b in tail]
        p.tpoly(tail, TULLE, 0.42)

    def draw_bride(self, p, t):
        x, top, h, lean = self.bride_geo(t)
        P = self.bride_P(t)
        dress = [P(x - 44, top), P(x + 44, top), P(x + 58, top + 120), P(x + 88, FEET), P(x - 88, FEET),
                 P(x - 58, top + 120)]
        p.poly(dress, DRESS)
        p.poly([P(x - 88, FEET - 10), P(x + 88, FEET - 10), P(x + 88, FEET), P(x - 88, FEET)], DRESS_D)
        p.poly([P(x - 46, top + 60), P(x + 46, top + 60), P(x + 50, top + 70), P(x - 50, top + 70)], DRESS_D)
        hx, hy = P(x, top - 42)
        p.circle(hx, hy, 44, SKIN)
        if self.veil_on_bride(t):
            lift = 40 * bump(t, 1.95, 0.08, 0.6)
            p.tpoly([(hx - 46, hy - 14 - lift), (hx - 10, hy - 52 - lift), (hx + 40, hy - 46), (hx + 50, hy - 6)], TULLE, 0.55)
        else:
            # un petit peigne de nacre reste sur sa tête
            p.ellipse(hx + 8, hy - 42, 18, 6, (250, 248, 240))
        sh = (P(x - 40, top + 24), P(x + 40, top + 24))
        hands = self.bride_hands(t, x, top, P)
        for s, hnd in zip(sh, hands):
            p.line([s, hnd], DRESS_D, 18)
            p.circle(hnd[0], hnd[1], 11, SKIN)
        self.draw_bouquet(p, t, hands[0])

    def bride_hands(self, t, x, top, P):
        rest = (P(x - 70, top + 150), P(x + 52, top + 160))
        bq = rest[0]
        if 11.85 <= t < 15.0:
            u = smooth((t - 11.85) / 0.35) * (1 - smooth((t - 14.7) / 0.3))
            tgt = (672, 1205 + self.bouquet_dent(t))
            bq = (rest[0][0] + (tgt[0] - rest[0][0]) * u, rest[0][1] + (tgt[1] - rest[0][1]) * u)
        other = rest[1]
        if 15.4 <= t < 18.25:
            u = smooth((t - 15.4) / 0.35)
            nl, nr = self.net_ends(t)
            other = (rest[1][0] + (nr[0] - rest[1][0]) * u, rest[1][1] + (nr[1] - rest[1][1]) * u)
            bq = (rest[0][0] + 10, rest[0][1] + 20)
        if 25.4 <= t < 32.7:
            px, py, _ = pillow_state(t)
            u = smooth((t - 25.4) / 0.3)
            tgt = (px + PIL_W / 2 - 6, py)
            bq = (rest[0][0] + (tgt[0] - rest[0][0]) * u, rest[0][1] + (tgt[1] - rest[0][1]) * u)
        if 32.7 <= t < 33.3:
            bq, other = P(x - 70, top - 10), P(x + 70, top - 10)
        # le lancer par-dessus l'épaule
        if 52.4 <= t < 53.65:
            u = smooth((t - 52.4) / 0.6)
            bq = (rest[0][0] + (870 - rest[0][0]) * u, rest[0][1] + (1060 - rest[0][1]) * u)
            if t > 53.3:
                v = smooth((t - 53.3) / 0.35)
                bq = (870 + (800 - 870) * v, 1060 + (850 - 1060) * v)
        if 53.65 <= t < 54.2:
            bq = (800, 850 + 60 * smooth((t - 53.65) / 0.5))
        return (bq, other)

    def bouquet_dent(self, t):
        d = 0.0
        for s in ("bouquet", "stems"):
            c = contact_near(t, s, 0.14)
            if c:
                d = max(d, (22 if s == "bouquet" else 26) * clamp01(1 - abs(t - c[0]) / 0.14))
        return d

    def draw_bouquet(self, p, t, hand):
        if t >= 53.65:
            return
        hx, hy = hand
        if 11.85 <= t < 14.9:
            top_y = hy - 36
        else:
            top_y = hy - 36
        self.draw_bunch(p, hx, hy, t, 0.0)

    def draw_bunch(self, p, hx, hy, t, ang, small=1.0):
        """Le bouquet (ou ce qu'il en reste) tenu en (hx, hy), fleurs vers le haut."""
        petals_left = 1.0 if t < 12.75 else (0.5 if t < 13.65 else 0.0)
        d = self.bouquet_dent(t)
        stems = []
        for k in range(7):
            a = -0.5 + k / 6.0
            stems.append([(hx, hy + 10), (hx + 34 * a * small, hy - (52 - d * 0.6) * small)])
        for st in stems:
            pts = rot(st, hx, hy, ang)
            p.line(pts, LEAF, 5 * small)
        p.circle(*rot([(hx, hy + 6)], hx, hy, ang)[0], 9 * small, (250, 248, 240))
        if petals_left > 0:
            cx, cy0 = rot([(hx, hy - (58 - d) * small)], hx, hy, ang)[0]
            n = 9 if petals_left > 0.6 else 4
            for k in range(n):
                a = 2 * math.pi * k / n
                rr = 22 * small
                col = PETALS[k % len(PETALS)]
                p.circle(cx + rr * math.cos(a), cy0 + rr * 0.55 * math.sin(a) - (d * 0.2), 15 * small, col)
            if petals_left > 0.6:
                p.circle(cx, cy0 - 8, 16 * small, PETALS[1])

    # ---- le voile en hamac
    def net_ends(self, t):
        l, r = (372.0, 1130.0), (708.0, 1130.0)
        if t >= 18.25:
            u = clamp01((t - 18.25) / 0.7)
            l = (l[0], l[1] + 0.5 * G * (u * 0.7) ** 2 * 0.4)
            r = (r[0], r[1] + 0.5 * G * (u * 0.7) ** 2 * 0.4)
        return l, r

    def net_curve(self, t):
        l, r = self.net_ends(t)
        bx, by, _, _ = ball(t)
        bottom = by + R
        sag = 34.0
        mid = (l[0] + r[0]) / 2
        if abs(bx - mid) < 160:
            sag = max(sag, bottom - 1130 + 4)
        sag = min(sag, 120)
        return quad(l, (mid, 1130 + 2 * sag), r, 20)

    def net_on(self, t):
        return 15.75 <= t < 18.25

    def draw_net_back(self, p, t):
        if 15.4 <= t < 15.75:
            # le voile passe des mains de la mariée à celles des deux mariés
            u = smooth((t - 15.4) / 0.35)
            l, r = (372.0, 1130.0), (708.0, 1130.0)
            l = (r[0] + (l[0] - r[0]) * u, l[1])
            p.tpoly(band(quad(l, ((l[0] + r[0]) / 2, 1180), r, 16), 18), TULLE, 0.5)
            return
        if self.net_on(t):
            p.tpoly(band(self.net_curve(t), 20), TULLE, 0.35)

    def draw_net_front(self, p, t):
        if self.net_on(t):
            cur = self.net_curve(t)
            p.tpoly(band(cur, 12), TULLE, 0.55)
            # les plis qui pendent
            l, r = cur[0], cur[-1]
            p.tpoly([l, (l[0] + 20, l[1] + 70), (l[0] + 50, l[1] + 10)], TULLE, 0.3)
            p.tpoly([r, (r[0] - 20, r[1] + 70), (r[0] - 50, r[1] + 10)], TULLE, 0.3)

    # ---- le coussin
    def draw_pillow(self, p, t):
        px, py, held = pillow_state(t)
        bx, by, _, _ = ball(t)
        top = py - PIL_H / 2
        dentx, dent = bx, 0.0
        if abs(bx - px) < PIL_W / 2 + 10 and by + R > top - 1:
            dent = min(26, by + R - top)
        pts = []
        n = 18
        for k in range(n + 1):
            x = px - PIL_W / 2 + PIL_W * k / n
            yy = top + 3 * (1 - (2 * k / n - 1) ** 2) * -1 + dent * math.exp(-((x - dentx) / 46) ** 2)
            pts.append((x, yy))
        bot = py + PIL_H / 2
        poly = pts + [(px + PIL_W / 2 + 4, bot - 6), (px + PIL_W / 2, bot), (px - PIL_W / 2, bot),
                      (px - PIL_W / 2 - 4, bot - 6)]
        if not held:
            p.ellipse(px, bot + 2, PIL_W / 2 + 6, 6, mix(MARBLE_D, BG, 0.4))
        p.poly(poly, SATIN)
        p.poly([(px - PIL_W / 2, bot - 9), (px + PIL_W / 2, bot - 9), (px + PIL_W / 2, bot), (px - PIL_W / 2, bot)], SATIN_D)
        for sx in (-1, 1):
            p.circle(px + sx * (PIL_W / 2 + 2), top + 4, 6, SATIN_D)

    def draw_rings(self, p, t):
        px, py, held = pillow_state(t)
        top = py - PIL_H / 2
        hops = ring_offsets(t)
        rf = ring_flight(t)
        for k, (dx, hy) in enumerate(((-62, hops[0]), (62, hops[1]))):
            if k == 1 and rf is not None:
                continue
            x, y = px + dx, top - 18 - hy
            p.circle(x, y, 19, None, outline=GOLD, width=7)
            p.circle(x - 3, y - 3, 13, None, outline=GOLD_L, width=2)

    # ---- les invités et les bancs
    def draw_guests(self, p, t):
        # le banc de derrière
        for (x0, x1) in ((20, 452), (628, 1060)):
            p.rect(x0, 1560, x1, 1700, WOOD_D)
        order = ["lady", "orange", "teal", "green"]
        for name in order:
            x, y, arms = guest_state(name, t)
            col = GUESTS[name][1]
            standing = y < HEAD_Y - 40
            # épaules / corps
            bw = 128 if name in ("orange", "green") else 112
            body_col = {"lady": (120, 90, 150), "orange": (92, 70, 110), "teal": (40, 90, 110), "green": (50, 96, 70)}[name]
            p.rect(x - bw / 2, y + 30, x + bw / 2, 1700, body_col, r=34)
            if arms > 0.02:
                for sx in (-1, 1):
                    sh = (x + sx * bw * 0.42, y + 60)
                    hand = (x + sx * (bw * 0.42 + 30), y + 60 - 120 * arms)
                    p.line([sh, hand], body_col, 22)
                    p.circle(hand[0], hand[1], 13, SKIN)
            if name == "green":
                sq = 1.0
                if 43.9 <= t < 44.15:
                    sq = 1 - 0.18 * math.sin(math.pi * (t - 43.9) / 0.25)
                p.rect(x - 50, y - 50 * sq, x + 50, y + 46, col, r=12)
            else:
                sq = 1.0
                if name == "orange" and 43.05 <= t < 43.3:
                    sq = 1 - 0.18 * math.sin(math.pi * (t - 43.05) / 0.25)
                p.ellipse(x, y + 44 * (1 - sq), 44, 44 * sq, col)
            if name == "lady":
                hx, hy, dent = lady_hat(t)
                p.ellipse(hx, hy + 6, 92, 20 - dent * 0.2, (150, 110, 190))
                pts = []
                for k in range(13):
                    a = math.pi * k / 12
                    pts.append((hx - 52 * math.cos(a), hy + 2 - (46 - dent) * math.sin(a)))
                p.poly(pts, (190, 150, 220))
                p.rect(hx - 50, hy - 8, hx + 50, hy + 4, (230, 120, 170))
            if name == "teal":
                tx, tyb, ta = tophat(t)
                hat = [(tx - 52, tyb), (tx + 52, tyb), (tx + 52, tyb - 10), (tx + 36, tyb - 10), (tx + 36, tyb - 92),
                       (tx - 36, tyb - 92), (tx - 36, tyb - 10), (tx - 52, tyb - 10)]
                p.poly(rot(hat, tx, tyb - 40, ta), (16, 16, 20))
                p.poly(rot([(tx - 36, tyb - 26), (tx + 36, tyb - 26), (tx + 36, tyb - 14), (tx - 36, tyb - 14)], tx, tyb - 40, ta), (150, 40, 60))
        # les dossiers du premier banc
        for (x0, x1) in ((20, 452), (628, 1060)):
            p.rect(x0, 1492, x1, 1566, WOOD, r=8)
            p.rect(x0, 1492, x1, 1500, mix(WOOD, (255, 255, 255), 0.18), r=4)

    # ---- Bounce
    def veil_on_ball(self, t):
        return t >= 18.95

    def draw_ball(self, p, t):
        x, y, vx, vy = ball(t)
        S = p.S
        if self.veil_on_ball(t) or 18.25 <= t < 18.95:
            self.draw_ball_veil_tail(p, t, x, y, vx, vy)
        base.ball(p.dr, x * S, y * S, R * S)
        if self.veil_on_ball(t):
            self.draw_ball_veil_cap(p, t, x, y)
        elif 18.25 <= t < 18.95:
            self.draw_falling_veil(p, t, x, y)

    def veil_cap_pts(self, x, y):
        pts = []
        for k in range(11):
            a = math.radians(205 + 130 * k / 10)
            pts.append((x + R * 1.12 * math.cos(a), y + R * 1.12 * math.sin(a)))
        for k in range(11):
            a = math.radians(335 - 130 * k / 10)
            pts.append((x + R * 0.9 * math.cos(a), y - R * 0.2 + R * 0.9 * math.sin(a)))
        return pts

    def draw_ball_veil_tail(self, p, t, x, y, vx, vy):
        # la traîne flotte derrière lui, à l'opposé de sa vitesse, et pend
        sp = math.hypot(vx, vy) + 1e-6
        dx, dy = -vx / sp, -vy / sp
        dx, dy = dx * 0.6, dy * 0.6 + 0.55
        L = math.hypot(dx, dy) or 1
        dx, dy = dx / L, dy / L
        side = -1 if vx > 30 else 1
        ax, ay = x + side * R * 0.55, y - R * 0.85
        bx_, by_ = x - side * R * 0.2, y - R * 1.02
        tip = (ax + dx * 200 + side * 50, ay + dy * 200)
        p.tpoly([(bx_, by_), (ax + side * 40, ay - 10), (tip[0] + side * 40, tip[1]), (tip[0] - side * 40, tip[1] + 16),
                 (ax - side * 30, ay + 60)], TULLE, 0.58)

    def draw_ball_veil_cap(self, p, t, x, y):
        p.tpoly(self.veil_cap_pts(x, y), TULLE, 0.82)
        for k in range(5):
            p.circle(x - 34 + k * 17, y - R * 1.08 - 6 * math.sin(math.pi * k / 4), 7, (252, 250, 244))
        # le bouquet planté dans le voile
        if t >= 54.45:
            self.draw_bunch(p, x + 26, y - R * 0.88, 99.0, 0.35, small=1.25)
        rf = ring_flight(t)
        if rf == "on":
            p.circle(x - 28, y - R - 12, 22, None, outline=GOLD, width=8)
            p.circle(x - 31, y - R - 15, 15, None, outline=GOLD_L, width=2)

    def draw_falling_veil(self, p, t, x, y):
        u = smooth((t - 18.25) / 0.7)
        cur = self.net_curve(18.25)
        cap = self.veil_cap_pts(x, y)
        # le voile se resserre autour du haut de la balle
        n = len(cur)
        pts = []
        for k, (cx_, cy_) in enumerate(cur):
            tx = x - R + 2 * R * k / (n - 1)
            ty = y - R * 0.8 - 30 * math.sin(math.pi * k / (n - 1))
            pts.append((cx_ + (tx - cx_) * u, cy_ + (ty - cy_) * u))
        p.tpoly(band(pts, 22 - 10 * u), TULLE, 0.5)

    # ---- la cloche
    def draw_bell(self, p, t):
        poly = bell_poly(t)
        p.poly(poly, GOLD)
        a = bell_angle(t)
        px, py = PIVOT
        hl = rot([(px - 70, py + 40), (px - 52, py + 30), (px - 64, py + 150), (px - 96, py + 170)], px, py, a)
        p.poly(hl, GOLD_L)
        sh = rot([(px + 60, py + 40), (px + 84, py + 50), (px + 128, py + 178), (px + 96, py + 180)], px, py, a)
        p.poly(sh, GOLD_D)
        lip = rot([(px - 150, py + 188), (px + 150, py + 188), (px + 150, py + 198), (px - 150, py + 198)], px, py, a)
        p.poly(lip, GOLD_D)
        mouth = rot([(px - 136 + 272 * k / 16, py + 198 + 9 * math.sin(math.pi * k / 16)) for k in range(17)], px, py, a)
        p.poly(mouth + [rot([(px, py + 198)], px, py, a)[0]], (20, 14, 8))
        # le nœud de satin, qui frémit au frôlement
        fr = 0.25 * math.sin(30 * t) * bump(t, 18.35, 0.1, 0.9)
        kx, ky = rot([(px, py + 12)], px, py, a)[0]
        for sx in (-1, 1):
            p.poly(rot([(kx, ky), (kx + sx * 40, ky - 20), (kx + sx * 44, ky + 10)], kx, ky, fr * sx), (250, 250, 252))
            p.poly(rot([(kx, ky), (kx + sx * 14, ky + 46), (kx + sx * 30, ky + 40)], kx, ky, -fr * sx), (236, 236, 244))
        p.circle(kx, ky, 9, (255, 255, 255))
        # ondes dorées
        for tb in BELLS:
            u = t - tb
            if 0 <= u < 0.9:
                for j in range(2):
                    uu = u - j * 0.14
                    if uu <= 0:
                        continue
                    rad = 160 + 620 * uu
                    k = (1 - uu / 0.9)
                    p.circle(px, py + 120, rad, None, outline=mix(BG, GOLD_L, 0.8 * k), width=8 * k + 2)

    # ---- ce qui vole
    def draw_petals(self, p, t):
        if t < 12.75:
            return
        for pt in PETAL:
            q = petal_pos(pt, t)
            if q is None:
                continue
            x, y = q
            a = 2.5 * t + pt["ph"]
            p.ellipse(x, y, pt["s"], pt["s"] * (0.45 + 0.35 * abs(math.sin(a))), pt["col"])

    def draw_flying(self, p, t):
        sf = stems_flight(t)
        if sf:
            x, y, a = sf
            self.draw_bunch(p, x, y, 99.0, a, small=1.25)
        rf = ring_flight(t)
        if rf is not None and rf != "on":
            x, y = rf
            p.circle(x, y, 22, None, outline=GOLD, width=8)

    # ---- les paroles de l'officiant, en haut
    def draw_subs(self, p, t):
        if self.fs is None:
            self.fs = base.font(64 * p.S)
            self.fb = base.font(84 * p.S)
        hook_s = self.cfg["hook_text_s"]
        if t < hook_s:
            return
        txt, final = None, False
        for n in self.narr:
            last = n is self.narr[-1]
            if last and n["start"] <= t:
                txt = n["text"]
                final = t >= T_FINAL
                if t > T_END - 0.6:
                    txt = None
                break
            if n["start"] <= t <= n["end"] + 0.2:
                chunks = base.sub_chunks(n["text"], 6)
                total = sum(len(c) for c in chunks) or 1
                acc = n["start"]
                txt = chunks[-1]
                for c in chunks:
                    d = (n["end"] - n["start"]) * len(c) / total
                    if t <= acc + d:
                        txt = c
                        break
                    acc += d
                break
        if not txt:
            return
        rows = self.wrap(txt, self.fs, W * 0.88 * p.S)
        y0 = 300 - (len(rows) - 1) * 36 - (40 if final else 0)
        for i, row in enumerate(rows):
            p.text(W / 2, y0 + i * 72, row, self.fs, (255, 255, 255), stroke=5)
        if final:
            k = clamp01((t - T_FINAL) / 0.12)
            sc = (1.25 - 0.25 * k)
            p.text(W / 2, y0 + len(rows) * 72 + 14, "BOUNCE.", self.fb, mix((0, 0, 0), tuple(base.HERO["color"]), k),
                   stroke=6)

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
def fast_reverb(x, sr, tail_s=0.8, wet=0.5):
    """La même réverbération que base.reverb (même réponse, même mélange), convoluée par FFT :
    la convolution directe prend des minutes sur une machine chargée."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    nf = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


def render_audio(sim, events, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    react = base.hero_word(cfg["hero_lose"], cfg)
    said = 0
    hits = [(t0, d) for (t0, k, d) in events if k == "hit"]
    if name is not None:
        far = fast_reverb(name, SR, 1.4, 0.55)
        words = base.place_words(events, total_dur, cfg, sim.payoff_t, "lose" if react is not None else None,
                                 narr, (), name_len=len(name) / SR,
                                 react_len=(len(react) / SR if react is not None else 0.8))
        for (t0, kind, _d, tag) in words:
            if kind == "react":
                ak.add(buf, react, t0, gain=1.0)
            elif tag == "bell":
                ak.add(buf, far, t0, gain=1.25)
            elif tag == "final":
                ak.add(buf, name, t0, gain=1.05)
            else:
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
    "hook_text_s": 3.0, "hook_top": 0.09, "hook_font_size": 92,
    "narrator_voice": "am_fenrir", "narrator_length": 1.0, "narr_gap_s": 0.35,
    "watermark_y": 0.955, "end_hold_s": 0.3, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0, "show_counter": False,
    "hero_lose": "Oh no.",
}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.narr = narr
    cfg["_sim"] = sim
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(events, dur, cfg, sim.payoff_t, "lose", narr, (), name_len=len(name) / SR)
    hits = [round(e[0], 2) for e in events if e[1] == "hit"]
    said = {round(w[0], 2) for w in words}
    summary = {"name": cfg["name"], "duration_s": round(dur, 2), "payoff": bool(sim.payoff),
               "hits": len(hits), "muets": [h for h in hits if h not in said],
               "react": [round(w[0], 2) for w in words if w[1] == "react"],
               "hook_s": round(len(cfg["_hook_voice"]) / SR, 2) if cfg.get("_hook_voice") is not None else None,
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if "--frames" in argv:
        out = argv[argv.index("--frames") + 1]
        os.makedirs(out, exist_ok=True)
        times = [float(x) for x in argv[argv.index("--frames") + 2].split(",")]
        S = cfg["supersample"]
        for tt in times:
            i = min(range(len(states)), key=lambda k: abs(states[k][0] - tt))
            img = Image.new("RGB", (W * S, H * S), tuple(cfg["bg_color"]))
            dr = ImageDraw.Draw(img)
            base.HERO["pos"] = None
            base.HERO["expr"] = "lose" if (sim.payoff_t is not None and tt >= sim.payoff_t) else "calm"
            sim.draw(dr, states[i][1], tt, S)
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
