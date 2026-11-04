"""
Prototype « le clip des quatre » : Bounce, Float, Snooze et Still, sur une chanson générée
(Suno, offre du propriétaire, fichier hors dépôt). La musique est gardée entière, sans coupe ;
les images sont calées sur ses temps (126 BPM) et sur les mots chantés. Les paroles sont
sous-titrées avec le texte écrit, pas avec ce qu'une transcription entend.

Cinq parties, comme la chanson : Bounce seul (intro), la salle de bain de Float, la chambre de
Snooze, la scène de Still, puis les quatre ensemble (refrain, break, fin). La fin : Still,
qui ne bouge jamais, rebondit pour la première fois.

    python3 src/stories/clip4.py configs/clip4_proto.json
"""
import math, sys, os, json, subprocess, tempfile
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W, H = 1080, 1920
S = 2
FPS = 60
BPM = 126.05
B0 = 0.255
BEAT = 60.0 / BPM
G = 2600.0
BG = (8, 8, 12)
INK = (12, 12, 14)


def beat(n):
    return B0 + n * BEAT


def nb(t):
    """Le temps le plus proche de t."""
    return beat(round((t - B0) / BEAT))


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


# ------------------------------------------------------------------ Float (d'après floatbath)
F_IN = (0x00, 0xCB, 0x80)
F_RING = (0x00, 0x79, 0x49)
EYE_W = (246, 248, 244)
FOAMC = (236, 242, 248)
RF = 100.0
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip4_float.py")).read())


class V0:
    """Une vue sans caméra : coordonnées de la scène = coordonnées de l'image."""
    def X(self, x):
        return x * S

    def Y(self, y):
        return y * S

    def L(self, l):
        return l * S

    def box(self, x0, y0, x1, y1):
        return [x0 * S, y0 * S, x1 * S, y1 * S]


VIEW = V0()

# ------------------------------------------------------------------ Snooze
S_DISC, S_HALO = (192, 192, 192), (42, 42, 44)
S_EYE, S_EDGE, S_LID = (104, 104, 104), (52, 52, 52), (40, 40, 40)
S_MOUTH = (112, 112, 112)


def draw_snooze(dr, x, y, r, roll=0.0, open_k=0.0, look=0.0, talk=0.0, smile=False, sq=0.0):
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=S_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=S_DISC)
    ca, sa = math.cos(roll), math.sin(roll)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.05 * r * S))
    for ex in (-0.37, 0.37):
        cx, cy, er = ex, -0.2, 0.29
        pts = [P(cx + er * math.cos(k * math.pi / 16), cy + er * math.sin(k * math.pi / 16)) for k in range(32)]
        dr.polygon(pts, fill=S_EYE)
        dr.line(pts + [pts[0]], fill=S_EDGE, width=w)
        if open_k > 0.5:
            pu, pv = cx + look * 0.12, cy - 0.02
            dr.polygon([P(pu + 0.1 * math.cos(k * math.pi / 8), pv + 0.1 * math.sin(k * math.pi / 8)) for k in range(16)], fill=(238, 238, 238))
        else:
            dr.line([P(cx - er * 0.8, cy), P(cx + er * 0.8, cy)], fill=S_LID, width=w)
    mh = 0.15 + 0.22 * talk
    if smile and talk < 0.05:
        pts = [(-0.36 + 0.72 * k / 12, 0.36 + 0.10 * math.sin(math.pi * k / 12)) for k in range(13)]
        dr.line([P(u, v) for u, v in pts], fill=S_EDGE, width=int(w * 1.6), joint="curve")
    else:
        pts = []
        for k in range(13):
            a = math.pi / 2 + math.pi * k / 12
            pts.append((-0.40 + mh / 2 * math.cos(a) + mh / 2, 0.40 + mh / 2 * math.sin(a)))
        for k in range(13):
            a = -math.pi / 2 + math.pi * k / 12
            pts.append((0.40 + mh / 2 * math.cos(a) - mh / 2, 0.40 + mh / 2 * math.sin(a)))
        q = [P(u, v) for u, v in pts]
        dr.polygon(q, fill=S_MOUTH)
        dr.line(q + [q[0]], fill=S_EDGE, width=w)


# ------------------------------------------------------------------ Still (d'après nameoc)
OC_OUT = (152, 166, 56)
OC_IN = (238, 250, 178)
OC_INK = (14, 14, 12)
HAT_FILL = (142, 146, 244)
HAT_LINE = (84, 86, 214)
BOW_FILL = (234, 246, 176)
BOW_LINE = (92, 98, 34)


def draw_still(dr, cx, cy, R, gx=0.0, gy=0.0, sq=0.0, wide=False):
    sx, sy = 1 + sq, 1 - sq

    def P(u, v):
        return ((cx + u * R * sx) * S, (cy + v * R * sy) * S)

    def poly(pts, fill=None, outline=None, width=0):
        q = [P(u, v) for u, v in pts]
        if fill is not None:
            dr.polygon(q, fill=fill)
        if outline is not None:
            dr.line(q + [q[0]], fill=outline, width=max(1, int(width * R * S)), joint="curve")

    def ell(u, v, ru, rv, n=40, a0=0.0, a1=2 * math.pi):
        return [(u + ru * math.cos(a0 + (a1 - a0) * i / n), v + rv * math.sin(a0 + (a1 - a0) * i / n))
                for i in range(n + (0 if a1 - a0 >= 2 * math.pi else 1))]

    def stroke(pts, w, col=OC_INK):
        q = [P(u, v) for u, v in pts]
        dr.line(q, fill=col, width=max(2, int(w * R * S)), joint="curve")
        rr = w * R * S / 2
        for (x, y) in (q[0], q[-1]):
            dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)

    poly(ell(0, 0, 1.6, 1.6, 64), fill=dim(OC_OUT, 0.55))
    poly(ell(0, 0, 1.0, 1.0, 64), fill=OC_IN)
    px, pv = gx * 0.05, max(-0.01, min(0.03, gy * 0.03))
    if wide:
        # les yeux s'ouvrent : la seule fois de la vidéo
        stroke([(-0.58, -0.58), (-0.18, -0.52)], 0.12)
        stroke([(0.14, -0.54), (0.58, -0.46)], 0.12)
        for (eu, ev, rr) in ((-0.36, -0.2, 0.17), (0.33, -0.17, 0.18)):
            poly(ell(eu, ev, rr, rr, 30), fill=(250, 250, 244))
            poly(ell(eu + px * 1.6, ev + 0.02, rr * 0.55, rr * 0.55, 20), fill=OC_INK)
    else:
        stroke([(-0.60, -0.50), (-0.18, -0.40)], 0.12)
        stroke([(0.14, -0.44), (0.60, -0.30)], 0.12)
        for (eu, ev, ru, rv) in ((-0.36, -0.16, 0.17, 0.13), (0.33, -0.12, 0.17, 0.15)):
            poly([(eu - ru, ev)] + ell(eu + px, ev + pv * 0.5, ru, rv, 24, 0.0, math.pi)[::-1] + [(eu + ru, ev)], fill=OC_INK)
            stroke([(eu - ru - 0.02, ev), (eu + ru + 0.02, ev)], 0.07)
        stroke([(-0.53, -0.16), (-0.62, -0.22)], 0.06)
        poly([(0.42, -0.02), (0.52, 0.07), (0.46, 0.10), (0.37, 0.02)], fill=OC_INK)
    stroke([(-0.20, 0.38), (0.10, 0.46)], 0.09)
    band = ell(0, 0, 0.99, 0.99, 20, math.radians(-128), math.radians(-62))
    inner = ell(0, 0, 0.79, 0.79, 20, math.radians(-128), math.radians(-62))[::-1]
    poly(band + inner, fill=HAT_FILL, outline=HAT_LINE, width=0.05)
    kx, ky = 0.36, -0.86

    def lobe(ang, L, Wd):
        ca, sa = math.cos(ang), math.sin(ang)
        pts = []
        for i in range(32):
            k = 2 * math.pi * i / 32
            u, v = L / 2 * (1 + math.cos(k)), Wd * math.sin(k) * (0.55 + 0.45 * (1 + math.cos(k)) / 2)
            pts.append((kx + u * ca - v * sa, ky + u * sa + v * ca))
        return pts
    poly(lobe(math.radians(-25), 0.50, 0.20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(lobe(math.radians(-120), 0.46, 0.19), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(lobe(math.radians(40), 0.30, 0.10), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(ell(kx, ky, 0.10, 0.09, 20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)


# ------------------------------------------------------------------ les trajectoires
class Track:
    """Une balle : des contacts (t, x, y) reliés par des arcs sous une gravité unique."""
    def __init__(self, contacts, start=None):
        self.c = sorted(contacts)
        self.start = start

    def at(self, t):
        c = self.c
        if t <= c[0][0]:
            if self.start is None:
                return c[0][1], c[0][2]
            t0, x0, y0 = self.start
            t1, x1, y1 = c[0]
            return self._arc(t, t0, x0, y0, t1, x1, y1)
        for a, b in zip(c, c[1:]):
            if a[0] <= t <= b[0]:
                return self._arc(t, *a, *b)
        t0, x0, y0 = c[-1]
        s = t - t0
        return x0, y0 - 900 * s + 0.5 * G * s * s if s < 0.69 else y0

    @staticmethod
    def _arc(t, t0, x0, y0, t1, x1, y1):
        d = max(1e-6, t1 - t0)
        s = (t - t0) / d
        h = min(0.5 * G * (d / 2) ** 2, 900.0)
        top = max(min(y0, y1) - h, 250.0)
        a0, a1 = max(0.0, y0 - top), max(0.0, y1 - top)
        sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
        if s <= sm:
            u = s / sm if sm > 0 else 1
            y = top + a0 * (1 - u) ** 2
        else:
            u = (s - sm) / (1 - sm) if sm < 1 else 1
            y = top + a1 * u ** 2
        return lerp(x0, x1, s), y


def squash_at(t, hits, amp=0.13):
    sq = 0.0
    for th in hits:
        d = t - th
        if 0 <= d < 0.5:
            sq = max(sq, amp * math.exp(-d * 8) * math.cos(d * 24))
    return sq


# ------------------------------------------------------------------ texte
LYRICS = [
    (4.16, 6.80, "Somebody stop Bounce!"), (8.04, 10.50, "Somebody stop Bounce!"), (12.66, 14.38, "Somebody stop Bounce!"),
    (17.42, 21.0, "Float was in the bubbles, eyes closed, all alone"), (21.46, 24.66, "Door goes bang... guess who's home"),
    (25.20, 28.36, "Half the bath is on the floor"), (28.36, 32.84, "“Float.” She points him to the door"),
    (32.84, 35.96, "Snooze is sleeping, seven a.m."), (36.88, 39.98, "Bounce is the alarm again"),
    (39.98, 42.50, "Bounce! “Snooze.” Nine more minutes"), (42.50, 44.46, "Bounce! Now it's midnight"),
    (47.98, 51.42, "Meet the new girl, her name is Still"), (51.42, 55.36, "She don't move and she never will"),
    (55.36, 59.18, "He bounced on her bow, he bounced on her head"), (59.18, 63.08, "Still didn't blink, she just stared instead"),
    (63.08, 64.88, "Bounce, bounce, he never stops"), (64.88, 66.74, "Off the walls and off the clocks"),
    (66.74, 68.78, "Float and Snooze and Still say no"), (68.78, 70.68, "Nobody can stop the show"),
    (70.68, 72.72, "Bounce, bounce, here he comes"), (72.72, 78.76, "Bounce! Bounce! Bounce!"),
    (81.70, 85.22, "...bounce?"),
    (90.50, 93.80, "Float said “Float”, Snooze said “Snooze”"), (93.80, 97.36, "Still said nothing, nothing to lose"),
    (97.36, 101.0, "The room went quiet... she looked at him..."), (101.0, 105.44, "And Still... bounced."),
    (105.44, 106.6, "Bounce!"),
]
TITLE = "CAN ANYONE STOP BOUNCE?"


def text_block(dr, txt, y, size, fill=(255, 255, 255), alpha=1.0, maxw=0.88):
    f = font(size * S)
    words, rows = txt.split(), [""]
    for wd in words:
        cand = (rows[-1] + " " + wd).strip()
        if base.text_w(f, cand) <= W * S * maxw or not rows[-1]:
            rows[-1] = cand
        else:
            rows.append(wd)
    col = mix(BG, fill, alpha)
    for i, row in enumerate(rows):
        dr.text((W / 2 * S, (y + (i - (len(rows) - 1) / 2) * size * 1.18) * S), row, fill=col, anchor="mm", font=f,
                stroke_width=max(2, int(size * S * 0.08)), stroke_fill=(0, 0, 0))


def label(dr, txt, x, y, t, t0, t1, size=86):
    if not (t0 <= t <= t1):
        return
    a = min(1.0, (t - t0) / 0.25, (t1 - t) / 0.3)
    pop = 1.0 + 0.25 * max(0.0, 1 - (t - t0) / 0.18)
    f = font(int(size * pop) * S)
    dr.text((x * S, y * S), txt, fill=mix(BG, (255, 255, 255), a), anchor="mm", font=f,
            stroke_width=max(2, int(size * S * 0.08)), stroke_fill=(0, 0, 0))


# ------------------------------------------------------------------ les scènes
R = 100.0
RB = 100.0
RB4 = 80.0                 # tout le monde un peu plus petit quand ils sont quatre
FLOOR = 1430.0
T_FLOAT, T_SNOOZE, T_STILL, T_ALL, T_END = 17.30, 32.70, 47.85, 62.95, 106.8


def hero_expr(t, hits, mood=None):
    if mood:
        return mood
    for th in hits:
        if 0 <= t - th < 0.3:
            return "shock"
    return "calm"


class Clip:
    def __init__(self):
        fy = FLOOR - RB
        # ---- intro : Bounce seul, un rebond tous les deux temps
        c = [(beat(n), 330 if (n // 2) % 2 else 750, fy) for n in range(0, 36, 2)]
        self.intro = Track(c, start=(-0.4, 540, 700))
        self.intro_hits = [x[0] for x in c]
        # ---- Float : la baignoire
        self.tub = (290, 1180, 790, FLOOR)          # x0, haut du bord, x1, bas
        rim = self.tub[1] - RB
        c = [(nb(21.9), 260, fy), (nb(22.85), 330, rim), (nb(23.8), 750, rim), (nb(24.7), 330, rim),
             (nb(25.65), 750, rim), (nb(26.6), 880, fy), (nb(27.55), 750, rim), (nb(28.5), 330, rim),
             (nb(29.45), 560, fy - 10 + 10), (nb(30.4), 380, fy), (nb(31.35), 230, fy), (nb(32.3), 110, fy)]
        self.f_track = Track(c, start=(21.46, 60, 1150))
        self.f_hits = [x[0] for x in c]
        self.f_splash = nb(25.65)
        # ---- Snooze : la chambre
        self.s_x, self.s_y = 330.0, 1262 + 16 - R
        hy = self.s_y - R - RB
        my = 1262 - RB
        c = [(nb(36.9), self.s_x, hy), (nb(37.85), 640, my), (nb(38.8), self.s_x, hy), (nb(39.98), self.s_x, hy),
             (nb(40.52), 600, my), (nb(42.5), self.s_x, hy), (nb(43.45), 700, my), (nb(44.46), self.s_x, hy),
             (nb(45.4), self.s_x, hy), (nb(46.35), self.s_x, hy), (nb(47.3), 700, my)]
        self.s_track = Track(c, start=(36.2, 1150, 700))
        self.s_hits = [x[0] for x in c]
        self.s_head = [x[0] for x in c if x[1] == self.s_x]
        self.s_roll = (nb(40.8), nb(41.64))
        # ---- Still : la scène
        self.st_x, self.st_y = 540.0, FLOOR - R
        bow = (self.st_x + 0.5 * R, self.st_y - 1.0 * R - RB)
        head = (self.st_x - 0.05 * R, self.st_y - R - RB)
        c = [(beat(n), 230 if (n // 2) % 2 else 850, fy) for n in range(102, 118, 2)]
        c += [(nb(56.78), *bow), (nb(57.9), 860, fy), (nb(58.74), *head), (nb(59.7), 230, fy),
              (nb(60.65), 850, fy), (nb(61.6), 230, fy), (nb(62.55), 850, fy)]
        self.st_track = Track(c, start=(48.0, 1150, 800))
        self.st_hits = [x[0] for x in c]
        self.st_head = [nb(56.78), nb(58.74)]
        # ---- les quatre ensemble
        self.X = {"float": 150.0, "still": 565.0, "snooze": 935.0}
        r4 = 80.0
        self.r4 = r4
        self.ytop = {"float": 1312 - 0.25 * r4, "still": FLOOR - r4, "snooze": 1318 + 12 - r4}
        heads = {k: (self.X[k], self.ytop[k] - r4 - RB4) for k in self.X}
        order = ["float", "still", "snooze", "still"]
        c, self.h4 = [], {k: [] for k in self.X}
        n = int(round((63.08 - B0) / BEAT))
        i = 0
        while beat(n) < 78.6:
            k = order[i % 4]
            c.append((beat(n), *heads[k])); self.h4[k].append(beat(n))
            n += 2 if beat(n) < 72.6 else 1 if i % 2 else 2
            i += 1
        # le break et la fin : de petits rebonds au sol, devant, entre Float et Still
        bx, byf = 358.0, FLOOR - RB4
        t = c[-1][0] + 0.9
        small = []
        while t < 101.5:
            small.append((t, bx + (6 if len(small) % 2 else -6), byf))
            t += 0.476 * (2 if 81.6 < t < 85.3 else 1.0) if t > 97.3 else 0.476 * 2
        c += small
        self.t_still_jump = nb(101.68)
        # Still rebondit, et Bounce avec elle, sur les « bounce » chantés
        jumps = [nb(x) for x in (102.44, 102.88, 103.30, 103.90, 104.30, 104.78, 105.44, 106.2)]
        self.still_jump = Track([(self.t_still_jump - 0.01, self.X["still"], self.ytop["still"])] +
                                [(tj, self.X["still"], self.ytop["still"]) for tj in jumps])
        self.still_jumps = jumps
        for j, tj in enumerate(jumps):
            c.append((tj + BEAT / 2, bx + (6 if j % 2 else -6), byf))
        self.all_track = Track(c, start=(62.95, 1150, 700))
        self.all_hits = [x[0] for x in c]

    # ---- le décor commun
    @staticmethod
    def stage(dr, wall=(26, 26, 38), spot=False, cx=540):
        dr.rectangle([0, 460 * S, W * S, FLOOR * S], fill=wall)
        if spot:
            dr.polygon([((cx - 70) * S, 460 * S), ((cx + 70) * S, 460 * S), ((cx + 330) * S, FLOOR * S), ((cx - 330) * S, FLOOR * S)],
                       fill=mix(wall, (60, 60, 76), 0.45))
        dr.rectangle([0, FLOOR * S, W * S, H * S], fill=(14, 14, 20))
        dr.line([(0, FLOOR * S), (W * S, FLOOR * S)], fill=(44, 44, 58), width=int(6 * S))

    def frame(self, t):
        img = Image.new("RGB", (W * S, H * S), BG)
        dr = ImageDraw.Draw(img)
        base.HERO["pos"] = None
        if t < T_FLOAT:
            self.f_intro(dr, t)
        elif t < T_SNOOZE:
            self.f_float(dr, t)
        elif t < T_STILL:
            self.f_snooze(dr, t)
        elif t < T_ALL:
            self.f_still(dr, t)
        else:
            self.f_all(dr, t)
        # le texte du haut, les sous-titres, le filigrane
        if t < 5.5:
            text_block(dr, TITLE, 250, 80, alpha=min(1.0, (5.5 - t) / 0.5))
        for (a, b, txt) in LYRICS:
            if a <= t <= b:
                text_block(dr, txt, 1640, 54)
                break
        wcol = tuple(int(c + (255 - c) * 0.15) for c in BG)
        dr.text((W / 2 * S, H * 0.94 * S), "@bouncefactory0", fill=wcol, anchor="mm", font=font(30 * S))
        return img.resize((W, H), Image.LANCZOS)

    def ball(self, dr, x, y, t, hits, mood=None, r=RB):
        base.HERO["expr"] = hero_expr(t, hits, mood)
        base.HERO["tilt"] = 0.0
        base.ball(dr, x * S, y * S, r * S)

    def f_intro(self, dr, t):
        self.stage(dr, spot=True)
        x, y = self.intro.at(t)
        self.ball(dr, x, y, t, self.intro_hits)
        label(dr, "BOUNCE", 540, 560, t, 2.6, T_FLOAT)

    def f_float(self, dr, t):
        self.stage(dr, wall=(24, 30, 40))
        x0, top, x1, bot = self.tub
        # la porte
        dr.rectangle([30 * S, 1000 * S, 190 * S, FLOOR * S], fill=(12, 10, 12))
        op = ease((t - 21.46) / 0.15) if t < 32.5 else 1 - ease((t - 32.5) / 0.2)
        dr.polygon([(30 * S, 1000 * S), ((30 + 160 * (1 - op)) * S, (1000 + 30 * op) * S),
                    ((30 + 160 * (1 - op)) * S, (FLOOR - 30 * op) * S), (30 * S, FLOOR * S)], fill=(96, 70, 54))
        # l'eau : pleine, puis la moitié par terre
        lvl = lerp(top + 30, top + 120, ease((t - self.f_splash) / 0.5))
        dr.rounded_rectangle([x0 * S, top * S, x1 * S, bot * S], radius=40 * S, fill=(232, 236, 244))
        dr.rectangle([(x0 + 22) * S, lvl * S, (x1 - 22) * S, (bot - 24) * S], fill=(96, 160, 214))
        for i in range(9):
            fx = lerp(x0 + 40, x1 - 40, i / 8)
            dr.ellipse([(fx - 30) * S, (lvl - 22) * S, (fx + 30) * S, (lvl + 18) * S], fill=FOAMC)
        if t > self.f_splash:
            k = min(1.0, (t - self.f_splash) / 0.6)
            dr.ellipse([(x1 - 40) * S, (FLOOR - 10) * S, (x1 + 240 * k) * S, (FLOOR + 26) * S], fill=(70, 120, 170))
            if k < 1:
                for i in range(10):
                    a = -math.pi / 2 + (i - 4.5) * 0.25
                    rr = 60 + 260 * k
                    dr.ellipse([(560 + rr * math.cos(a) - 16) * S, (top + rr * math.sin(a) * 0.9 - 16 + 300 * k * k) * S,
                                (560 + rr * math.cos(a) + 16) * S, (top + rr * math.sin(a) * 0.9 + 16 + 300 * k * k) * S], fill=(120, 180, 230))
        # Float, qui flotte
        fy = lvl - 0.25 * RF + 6 * math.sin(t * 3)
        if t < 21.46:
            ex, look = "serene", (0.0, 0.0)
        elif t < self.f_splash:
            ex, look = "slit", (-0.6, 0.0)
        elif t < 28.36:
            ex, look = "squint", (0.0, -0.3)
        else:
            ex, look = "glacial", (-1.0, 0.0)
        mouth = 0.8 * abs(math.sin((t - 28.36) * 9)) if 28.36 <= t <= 29.0 else 0.0
        bx, by = self.f_track.at(t)
        draw_float(dr, VIEW, 560, fy, 0.0, EXPR[ex], look, mouth, 0.0, 0.0)
        # le bord avant de la baignoire passe devant l'eau
        dr.rectangle([x0 * S, (top + 140) * S, x1 * S, bot * S], fill=(232, 236, 244))
        if t >= 21.46:
            self.ball(dr, bx, by, t, self.f_hits)
        label(dr, "FLOAT", 560, 560, t, 17.4, T_SNOOZE)

    def f_snooze(self, dr, t):
        night = ease((t - 43.26) / 0.85)
        wall = mix((30, 30, 44), (13, 13, 22), night)
        self.stage(dr, wall=wall)
        # la fenêtre et l'horloge
        sky = mix((196, 118, 112), (10, 12, 30), night)
        dr.rectangle([86 * S, 546 * S, 484 * S, 944 * S], fill=(60, 52, 50))
        dr.rectangle([100 * S, 560 * S, 470 * S, 930 * S], fill=sky)
        dr.rectangle([279 * S, 560 * S, 291 * S, 930 * S], fill=(60, 52, 50)); dr.rectangle([100 * S, 739 * S, 470 * S, 751 * S], fill=(60, 52, 50))
        if night > 0.6:
            dr.ellipse([350 * S, 610 * S, 410 * S, 670 * S], fill=(236, 236, 214))
            dr.ellipse([364 * S, 604 * S, 420 * S, 660 * S], fill=sky)
        m = 420
        if t >= self.s_roll[1]:
            m = 429
        if t >= 43.26:
            m = int(lerp(429, 24 * 60, ease((t - 43.26) / 0.85)))
        m %= 24 * 60
        dr.rounded_rectangle([600 * S, 540 * S, 990 * S, 700 * S], radius=18 * S, fill=(18, 12, 14), outline=(70, 60, 64), width=int(5 * S))
        dr.text((795 * S, 624 * S), f"{m // 60}:{m % 60:02d}", fill=(255, 70, 60), anchor="mm", font=font(118 * S))
        if 0 <= t - self.s_roll[1] < 1.0:
            k = (t - self.s_roll[1])
            dr.text((795 * S, (500 - 40 * k) * S), "+9 MIN", fill=mix((120, 255, 140), wall, k), anchor="mm", font=font(70 * S))
        # le lit
        YM = 1262
        bed = (82, 60, 52)
        dr.rectangle([150 * S, 980 * S, 205 * S, FLOOR * S], fill=bed)
        dr.rectangle([150 * S, (YM + 70) * S, 930 * S, (YM + 120) * S], fill=bed)
        dr.rectangle([170 * S, (YM + 120) * S, 200 * S, FLOOR * S], fill=bed); dr.rectangle([890 * S, (YM + 120) * S, 920 * S, FLOOR * S], fill=bed)
        dr.rectangle([205 * S, YM * S, 920 * S, (YM + 72) * S], fill=(210, 210, 222))
        dr.rounded_rectangle([215 * S, (YM - 52) * S, 445 * S, (YM + 6) * S], radius=26 * S, fill=(236, 236, 244))
        a, b = self.s_roll
        rk = ease((t - a) / 0.2) if a <= t < a + 0.2 else (1.0 if a + 0.2 <= t <= b else (1 - ease((t - b) / 0.3) if b < t < b + 0.3 else 0.0))
        sx = lerp(self.s_x, 470, rk)
        bx, by = self.s_track.at(t)
        pinned = a + 0.1 <= t <= b
        if pinned:
            bx, by = 520 + 5 * math.sin(t * 70), YM - RB + 40
            self.ball(dr, bx, by, t, self.s_hits)
        talk = abs(math.sin((t - 40.8) * 9)) * 0.9 if 40.8 <= t <= 41.3 else 0.0
        sq = squash_at(t, self.s_head)
        draw_snooze(dr, sx, YM + 16 - R * (1 - sq), R, roll=(sx - self.s_x) / R, talk=talk, smile=t > 44.4, sq=sq)
        # la couverture
        top = [(lerp(400, 920, i / 40) * S, (YM - 26 + 6 * math.sin(lerp(400, 920, i / 40) / 60)) * S) for i in range(41)]
        dr.polygon(top + [(920 * S, (YM + 76) * S), (400 * S, (YM + 76) * S)], fill=(86, 98, 168))
        if t >= 36.2 and not pinned:
            self.ball(dr, bx, by, t, self.s_hits)
        label(dr, "SNOOZE", 540, 470 + 0 * 1, t, 32.8, 36.6, size=80)

    def f_still(self, dr, t):
        self.stage(dr, spot=True)
        sq = squash_at(t, self.st_head, 0.08)
        draw_still(dr, self.st_x, FLOOR - R * (1 - sq), R, sq=sq)
        if t >= 48.0:
            x, y = self.st_track.at(t)
            self.ball(dr, x, y, t, self.st_hits)
        label(dr, "STILL", 540, 600, t, 50.8, T_ALL)

    def f_all(self, dr, t):
        self.stage(dr, spot=True)
        r4 = self.r4
        # Float dans une petite bassine
        fx = self.X["float"]
        dr.rounded_rectangle([(fx - 120) * S, 1300 * S, (fx + 120) * S, FLOOR * S], radius=30 * S, fill=(232, 236, 244))
        dr.rectangle([(fx - 104) * S, 1314 * S, (fx + 104) * S, (FLOOR - 16) * S], fill=(96, 160, 214))
        global RF
        RF = r4
        if 66.96 <= t < 69.0:
            fex, flook = "squint", (0.6, 0.0)
        elif 101.7 <= t:
            fex, flook = "wide_o", (0.6, -0.2)
        else:
            fex, flook = "calm", (0.0, 0.0)
        fm = 0.8 * abs(math.sin((t - 91.0) * 9)) if 91.0 <= t <= 91.6 else 0.0
        if fm > 0:
            fex = "slit"
        fsq = squash_at(t, self.h4["float"])
        draw_float(dr, VIEW, fx, self.ytop["float"] + 5 * math.sin(t * 3), 0.0, EXPR[fex], flook, fm, 0.0, 0.0)
        dr.rectangle([(fx - 120) * S, 1366 * S, (fx + 120) * S, FLOOR * S], fill=(232, 236, 244))
        RF = 100.0
        # Snooze sur son oreiller
        sx = self.X["snooze"]
        dr.rounded_rectangle([(sx - 125) * S, 1306 * S, (sx + 125) * S, 1356 * S], radius=24 * S, fill=(236, 236, 244))
        sq = squash_at(t, self.h4["snooze"])
        talk = abs(math.sin((t - 92.6) * 9)) * 0.9 if 92.6 <= t <= 93.2 else 0.0
        open_k = 1.0 if t >= 102.4 else 0.0
        draw_snooze(dr, sx, self.ytop["snooze"] + r4 * sq, r4, open_k=open_k, look=-0.8, talk=talk,
                    smile=(67.54 > t or t > 69.0) and t < 102.4, sq=sq)
        # Still : immobile, jusqu'à la fin
        bx, by = self.all_track.at(t)
        if t < self.t_still_jump:
            g = (bx - self.X["still"]) / 300.0 if t >= 99.48 else 0.0
            sq = squash_at(t, self.h4["still"], 0.08)
            draw_still(dr, self.X["still"], self.ytop["still"] + r4 * sq, r4, gx=max(-1, min(1, g)) * 3, sq=sq)
        else:
            x, y = self.still_jump.at(t)
            draw_still(dr, x, y, r4, gx=-3.0, wide=t < self.t_still_jump + 0.8)
        mood = "win" if t > self.t_still_jump + 0.3 else None
        self.ball(dr, bx, by, t, self.all_hits, mood, r=RB4)
        if t < 66.7:
            for k, nm in (("float", "FLOAT"), ("still", "STILL"), ("snooze", "SNOOZE")):
                label(dr, nm, self.X[k], FLOOR + 70, t, 63.0, 66.7, size=48)


CLIP = None


def render_chunk(args):
    i0, i1, out = args
    global CLIP
    CLIP = Clip()
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                             "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for i in range(i0, i1):
        proc.stdin.write(CLIP.frame(i / FPS).tobytes())
    proc.stdin.close(); proc.wait()
    return out


def main():
    cfg = json.load(open(sys.argv[1]))
    song = cfg["song"]
    n = int(T_END * FPS)
    if "--frames" in sys.argv:
        c = Clip()
        ts = [float(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]
        ims = [c.frame(t).resize((270, 480)) for t in ts]
        sheet = Image.new("RGB", (270 * min(6, len(ims)), 480 * ((len(ims) + 5) // 6)))
        for k, im in enumerate(ims):
            sheet.paste(im, ((k % 6) * 270, (k // 6) * 480))
        sheet.save(sys.argv[sys.argv.index("--frames") + 2])
        return
    tmp = tempfile.mkdtemp()
    parts = 4
    jobs = [(n * k // parts, n * (k + 1) // parts, os.path.join(tmp, f"p{k}.mp4")) for k in range(parts)]
    with Pool(parts) as p:
        outs = p.map(render_chunk, jobs)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{o}'\n" for o in outs))
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    out = os.path.join(ROOT, "output", cfg["name"] + ".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", song,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True)
    print(json.dumps({"name": cfg["name"], "out": os.path.relpath(out, ROOT), "duration_s": T_END}))


if __name__ == "__main__":
    main()
