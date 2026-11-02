"""
Prototype « tuto maquillage » : une maquilleuse fait un tuto sur Bounce, assis sur un
tabouret devant le miroir de loge. Chaque étape est un geste précis de sa main ; Bounce
ne s'arrête pas de rebondir, et le trait se dépose là où son visage se trouve à cet
instant : le maquillage s'accumule pour de vrai, en coordonnées de son visage.

Rien n'est truqué : la main suit une trajectoire propre, Bounce bouge dessous, et le
dépôt (point de contact ramené dans le repère du visage) dessine le désastre tout seul.

    python3 src/stories/makeup.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, SCENE_TOP, GREEN, AMBER, glow, mix

R_FACE = 150.0                 # Bounce en gros plan : son visage est la toile
G = 1500.0                     # des rebonds amples et lents : chaque retombée a le temps de dire son nom
SEAT_Y = 1440.0                # le dessus du tabouret
REST_X = 600.0
PINK = (255, 20, 200)
WALL = (34, 28, 44)
SKIN = (238, 196, 160)
ARTIST = (64, 66, 96)

LOOK = []                      # tout le maquillage déposé, dans l'ordre : il traverse les étapes


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, k):
    return a + (b - a) * k


def smooth(k):
    k = clamp(k, 0.0, 1.0)
    return k * k * (3 - 2 * k)


class Step(Chapter):
    """Une étape du tuto : la main approche, fait son geste (le « stroke »), se retire."""
    title = None
    stamp = None
    mood = None
    hold_s = 2.7
    tool = "sponge"
    hop = (90.0, 150.0)
    t_go = 0.5                 # début de l'approche
    approach = 0.7
    stroke_s = 3.0
    track = 0.25               # la main suit un peu le visage, avec retard
    say = ("", "")             # (titre dit, verdict après la chute)

    def setup(self):
        self.R = R_FACE
        lo, hi = self.hop
        self.hop_init(REST_X, SEAT_Y, start_h=lo, gain=(0.85, 1.2), min_h=lo, max_h=hi, wobble=14.0,
                      xmin=REST_X - 18, xmax=REST_X + 18, h_ref=hi)
        self.rest = (REST_X, SEAT_Y - self.R - 0.5 * lo)
        self.aim = list(self.rest)
        self.hand = [300.0, 1300.0]
        self.tip = [300.0, 1300.0]
        self.press = False
        self.last_uv = None
        self.n0 = len(LOOK)
        self.line(self.say[0], "title", 0.0)

    # le geste, en coordonnées du visage au repos : (u, v, appui) pour s dans [0, 1]
    def path(self, s):
        return 0.0, 0.0, False

    def deposit(self, u0, v0, u1, v1):
        pass

    def after(self, dt, evs):
        t = self.t
        # la main vise le visage « au repos », en suivant un peu ses rebonds
        tx = lerp(self.rest[0], self.bx, self.track)
        ty = lerp(self.rest[1], self.by, self.track)
        k = 1 - math.exp(-dt * 6.0)
        self.aim[0] += (tx - self.aim[0]) * k
        self.aim[1] += (ty - self.aim[1]) * k
        t1 = self.t_go + self.approach
        t2 = t1 + self.stroke_s
        home = (330.0, 1330.0)
        if t < self.t_go:
            tip, press = home, False
        elif t < t1:
            u, v, _ = self.path(0.0)
            a = smooth((t - self.t_go) / self.approach)
            tip = (lerp(home[0], self.aim[0] + u * self.R, a), lerp(home[1], self.aim[1] + v * self.R, a))
            press = False
        elif t < t2:
            u, v, press = self.path((t - t1) / self.stroke_s)
            tip = (self.aim[0] + u * self.R, self.aim[1] + v * self.R)
        else:
            u, v, _ = self.path(1.0)
            a = smooth((t - t2) / 0.7)
            tip = (lerp(self.aim[0] + u * self.R, home[0], a), lerp(self.aim[1] + v * self.R, home[1], a))
            press = False
            if not self.payoff and self.hit_t >= t2:
                self.finish("DONE")                   # la chute tombe sur une retombée : on l'entend
                self.line(self.say[1], "verdict", t + 1.05)
        # la main ne se téléporte jamais : elle rejoint sa cible à vitesse bornée
        ddx, ddy = tip[0] - self.tip[0], tip[1] - self.tip[1]
        dd = math.hypot(ddx, ddy)
        vmax = 1700.0 * dt
        if dd > vmax:
            self.tip[0] += ddx / dd * vmax; self.tip[1] += ddy / dd * vmax
            press = press and dd < 40.0
        else:
            self.tip = list(tip)
        tip = tuple(self.tip)
        self.press = press
        # le dépôt : là où l'outil touche le visage, ramené dans le repère du visage
        dx, dy = tip[0] - self.bx, tip[1] - self.by
        if press and math.hypot(dx, dy) < 0.97 * self.R:
            uv = (dx / self.R, dy / self.R)             # le repère du visage (l'inclinaison n'est qu'un effet de dessin)
            if self.last_uv is not None:
                self.deposit(self.last_uv[0], self.last_uv[1], uv[0], uv[1])
            else:
                self.deposit(uv[0], uv[1], uv[0], uv[1])
            self.last_uv = uv
        else:
            self.last_uv = None


    # ------------------------------------------------------------------ contrat
    def snapshot(self):
        s = self.base_snap()
        s["tip"] = tuple(self.tip)
        s["press"] = self.press
        s["n"] = len(LOOK)
        return s

    def solids(self, s):
        return []

    def focus(self, s):
        return (s["bx"] - self.R - 10, s["by"] - self.R - 10, s["bx"] + self.R + 10, s["by"] + self.R + 10)

    def bodies(self, s):
        return [("tool", s["tip"][0], s["tip"][1], 0.0)]

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        room(dr, P, W, H)
        bx, by = s["bx"], s["by"]
        # l'ombre du tabouret et le tabouret
        dr.ellipse([P(REST_X - 120), P(SEAT_Y - 6), P(REST_X + 120), P(SEAT_Y + 22)], fill=(120, 40, 60))
        dr.rectangle([P(REST_X - 12), P(SEAT_Y + 16), P(REST_X + 12), P(1640)], fill=(150, 150, 165))
        dr.ellipse([P(REST_X - 80), P(1630), P(REST_X + 80), P(1652)], fill=(110, 110, 125))
        base.ball(dr, P(bx), P(by), P(self.R))
        draw_look(dr, P(bx), P(by), P(self.R), LOOK[:s["n"]])
        base.hero_face(dr, P(bx), P(by), P(self.R))
        artist(dr, P, s["tip"], self.tool, s["press"], t)
        # l'habillage d'un tuto filmé : REC et le nom de la vidéo
        if not (self.stamp and s["end"] is not None):
            if int(t * 2) % 2 == 0:
                circle(dr, P(58), P(SCENE_TOP + 44), P(11), (235, 50, 60))
            f = base.font(int(32 * S))
            dr.text((P(80), P(SCENE_TOP + 44)), "MAKEUP TUTORIAL", fill=(240, 236, 246), anchor="lm", font=f)
        dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))


# ---------------------------------------------------------------- le décor commun
def room(dr, P, W, H):
    dr.rectangle([0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
    # le miroir de loge et ses ampoules, derrière Bounce
    x0, y0, x1, y1 = 300, 520, 900, 1250
    glow(dr, P, 600, 880, 520, (255, 220, 160), WALL, 0.10, rings=6)
    dr.rectangle([P(x0 - 30), P(y0 - 30), P(x1 + 30), P(y1 + 30)], fill=(70, 56, 50))
    dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(46, 52, 70))
    # le reflet : le dos de Bounce, flou, et la pièce
    for k in range(6):
        for (xx, yy) in ((x0 - 15 + k * 0 , y0 + k * (y1 - y0) / 5), (x1 + 15, y0 + k * (y1 - y0) / 5)):
            circle(dr, P(xx), P(yy), P(14), (255, 236, 190))
    for k in range(7):
        circle(dr, P(x0 + k * (x1 - x0) / 6), P(y0 - 15), P(14), (255, 236, 190))
    # le chariot de produits à droite
    dr.rectangle([P(800), P(1330), P(920), P(1346)], fill=(90, 80, 100))
    dr.rectangle([P(806), P(1346), P(814), P(1650)], fill=(70, 64, 80))
    dr.rectangle([P(906), P(1346), P(914), P(1650)], fill=(70, 64, 80))
    for (xx, w, h, c) in ((815, 18, 70, (230, 120, 150)), (842, 26, 50, (200, 170, 140)), (874, 14, 80, (60, 40, 60)), (896, 12, 46, (210, 40, 60))):
        dr.rectangle([P(xx), P(1330 - h), P(xx + w), P(1330)], fill=c if c != (210, 40, 60) else (128, 40, 176))
    dr.rectangle([0, P(1640), P(W), P(H)], fill=(44, 36, 46))


def draw_look(dr, x, y, r, items):
    """Le maquillage déposé, dessiné sur le visage (repère du visage, découpé au disque)."""
    if not items:
        return
    from PIL import Image, ImageDraw, ImageChops
    tl = base.HERO.get("tilt", 0.0)
    ca, sa = math.cos(tl), math.sin(tl)
    size = int(2 * r) + 4
    ox, oy = x - size / 2, y - size / 2
    layer = Image.new("RGB", (size, size), (0, 0, 0))
    cover = Image.new("L", (size, size), 0)
    dl, dc = ImageDraw.Draw(layer), ImageDraw.Draw(cover)

    def p(u, v):
        return (size / 2 + (u * ca - v * sa) * r, size / 2 + (u * sa + v * ca) * r)
    for it in items:
        if it[0] == "seg":
            _, u0, v0, u1, v1, col, w = it
            a, b = p(u0, v0), p(u1, v1)
            ww = max(1, int(w * r))
            dl.line([a, b], fill=col, width=ww)
            dc.line([a, b], fill=255, width=ww)
            for q in (a, b):
                rr = ww / 2
                dl.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=col)
                dc.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=255)
        else:
            _, u, v, rad, col = it
            q = p(u, v)
            rr = rad * r
            dl.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=col)
            dc.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=255)
    disc = Image.new("L", (size, size), 0)
    ImageDraw.Draw(disc).ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], fill=255)
    mask = ImageChops.multiply(cover, disc)
    dr._image.paste(layer, (int(ox), int(oy)), mask)


def artist(dr, P, tip, tool, press, t):
    """La maquilleuse, sans visage, à gauche : épaule, bras en deux segments, main, outil."""
    col = ARTIST
    # le corps et la tête, chignon
    dr.rounded_rectangle([P(-60), P(860), P(210), P(1700)], radius=int(P(70)), fill=col)
    circle(dr, P(100), P(740), P(92), col)
    circle(dr, P(40), P(660), P(46), dim(col, 0.8))
    sh = (170.0, 930.0)
    # l'outil pointe vers le visage : la main est un peu en retrait de la pointe
    ang = math.atan2(tip[1] - sh[1], tip[0] - sh[0])
    L_tool = {"sponge": 40, "brush": 120, "pencil": 110, "wand": 110, "lipstick": 80, "puff": 50}[tool]
    hx, hy = tip[0] - math.cos(ang) * L_tool, tip[1] - math.sin(ang) * L_tool
    # deux segments (bras, avant-bras), coude vers le bas
    L1 = L2 = 250.0
    dx, dy = hx - sh[0], hy - sh[1]
    d = clamp(math.hypot(dx, dy), 1.0, L1 + L2 - 1.0)
    a0 = math.atan2(dy, dx)
    c = clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1.0, 1.0)
    ea = a0 + math.acos(c)
    ex, ey = sh[0] + L1 * math.cos(ea), sh[1] + L1 * math.sin(ea)
    hx, hy = ex + L2 * math.cos(math.atan2(hy - ey, hx - ex)), ey + L2 * math.sin(math.atan2(hy - ey, hx - ex))
    w = max(1, int(P(46)))
    dr.line([(P(sh[0]), P(sh[1])), (P(ex), P(ey))], fill=col, width=w)
    dr.line([(P(ex), P(ey)), (P(hx), P(hy))], fill=dim(col, 1.1), width=max(1, int(P(40))))
    circle(dr, P(ex), P(ey), P(22), col)
    # l'outil
    tx, ty = hx + math.cos(ang) * L_tool, hy + math.sin(ang) * L_tool
    ux, uy = math.cos(ang), math.sin(ang)
    if tool == "sponge":
        circle(dr, P(tx), P(ty), P(34), (236, 200, 170))
    elif tool == "puff":
        circle(dr, P(tx), P(ty), P(44), (250, 240, 245))
        circle(dr, P(tx - 10), P(ty - 10), P(14), (255, 255, 255))
    elif tool == "brush":
        dr.line([(P(hx), P(hy)), (P(tx - ux * 30), P(ty - uy * 30))], fill=(40, 30, 40), width=max(1, int(P(12))))
        circle(dr, P(tx), P(ty), P(30), (220, 150, 160))
    elif tool == "pencil":
        dr.line([(P(hx), P(hy)), (P(tx), P(ty))], fill=(20, 20, 26), width=max(1, int(P(9))))
        dr.line([(P(tx - ux * 14), P(ty - uy * 14)), (P(tx), P(ty))], fill=(5, 5, 8), width=max(1, int(P(5))))
    elif tool == "wand":
        dr.line([(P(hx), P(hy)), (P(tx), P(ty))], fill=(30, 30, 40), width=max(1, int(P(8))))
        for k in range(5):
            q = 1 - k * 0.06
            px_, py_ = hx + ux * L_tool * q, hy + uy * L_tool * q
            dr.line([(P(px_ - uy * 12), P(py_ + ux * 12)), (P(px_ + uy * 12), P(py_ - ux * 12))], fill=(10, 10, 12), width=max(1, int(P(3))))
    elif tool == "lipstick":
        dr.line([(P(hx), P(hy)), (P(tx - ux * 26), P(ty - uy * 26))], fill=(200, 170, 80), width=max(1, int(P(22))))
        dr.line([(P(tx - ux * 26), P(ty - uy * 26)), (P(tx), P(ty))], fill=(128, 40, 176), width=max(1, int(P(16))))
    circle(dr, P(hx), P(hy), P(30), dim(col, 1.25))


# ---------------------------------------------------------------- les étapes
class Foundation(Step):
    title = "STEP 1/6 · FOUNDATION"
    tool = "sponge"
    say = ("Step one: foundation.", "Flawless.")
    hop = (120.0, 150.0)
    t_go = 0.2
    approach = 0.6
    stroke_s = 4.3
    DABS = [(-0.45, 0.1), (0.45, 0.1), (0.0, -0.55), (-0.3, 0.55), (0.3, 0.55), (0.0, 0.15), (-0.55, -0.3), (0.55, -0.3)]

    def path(self, s):
        n = len(self.DABS)
        k = min(n - 1, int(s * n))
        f = s * n - k
        u, v = self.DABS[k]
        if f > 0.65:
            nu, nv = self.DABS[min(n - 1, k + 1)]
            g = smooth((f - 0.65) / 0.35)
            return lerp(u, nu, g), lerp(v, nv, g), False
        return u, v, 0.15 < f < 0.5

    def deposit(self, u0, v0, u1, v1):
        if abs(u1 - u0) + abs(v1 - v0) < 1e-6 or (LOOK and LOOK[-1][0] == "dot" and math.hypot(LOOK[-1][1] - u1, LOOK[-1][2] - v1) > 0.05):
            LOOK.append(("dot", u1, v1, 0.24, mix(PINK, SKIN, 0.85)))
        else:
            LOOK.append(("seg", u0, v0, u1, v1, mix(PINK, SKIN, 0.85), 0.4))


class Blush(Step):
    title = "STEP 2/6 · BLUSH"
    tool = "brush"
    say = ("Step two: blush. Little circles.", "A natural glow.")
    hop = (150.0, 200.0)
    stroke_s = 5.4

    def path(self, s):
        side = -1.0 if s < 0.5 else 1.0
        q = (s % 0.5) / 0.5
        a = q * 2 * math.pi * 2.0
        if q < 0.08 or q > 0.92:
            return side * 0.5 + 0.14, 0.18, False
        return side * 0.5 + 0.14 * math.cos(a), 0.18 + 0.12 * math.sin(a), True

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, mix(PINK, (235, 60, 90), 0.55), 0.17))


class Eyeliner(Step):
    title = "STEP 3/6 · EYELINER"
    tool = "pencil"
    say = ("Step three: eyeliner. Keep it subtle.", "Subtle.")
    hop = (180.0, 240.0)
    stroke_s = 3.2

    def path(self, s):
        # l'œil droit puis l'œil gauche : un trait fin qui file vers la tempe
        if s < 0.46:
            q = s / 0.46
            return lerp(0.22, 0.7, q), lerp(-0.1, -0.34, q), 0.05 < q < 0.95
        if s < 0.54:
            q = (s - 0.46) / 0.08
            return lerp(0.7, -0.22, q), lerp(-0.34, -0.1, q), False
        q = (s - 0.54) / 0.46
        return lerp(-0.22, -0.7, q), lerp(-0.1, -0.34, q), 0.05 < q < 0.95

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, (14, 10, 18), 0.045))


class Mascara(Step):
    title = "STEP 4/6 · MASCARA"
    tool = "wand"
    say = ("Step four: mascara. Wiggle the wand.", "Volume.")
    hop = (210.0, 280.0)
    stroke_s = 6.6

    def path(self, s):
        n = 8
        k = min(n - 1, int(s * n))
        f = s * n - k
        side = -1 if k < n // 2 else 1
        u0 = side * (0.24 + 0.08 * (k % (n // 2)))
        return u0 + 0.03 * math.sin(f * 20), lerp(-0.26, -0.5, f), 0.1 < f < 0.9

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, (20, 14, 24), 0.035))


class Lipstick(Step):
    title = "STEP 5/6 · LIPSTICK"
    tool = "lipstick"
    say = ("Step five: lipstick. Follow the lip line.", "Bold choice.")
    hop = (240.0, 320.0)
    stroke_s = 4.2

    def path(self, s):
        q = (s * 3) % 2.0
        q = q if q < 1 else 2 - q
        return lerp(-0.26, 0.26, q), 0.42 + 0.03 * math.sin(s * 30), 0.04 < s < 0.96

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, (128, 40, 176), 0.13))      # un rouge à lèvres violet : jamais une couleur de sang


class Powder(Step):
    title = "STEP 6/6 · SETTING POWDER"
    tool = "puff"
    say = ("Step six: setting powder. One light puff.", "And set.")
    hop = (260.0, 340.0)
    stroke_s = 3.4

    def setup(self):
        super().setup()
        self.dust = []

    def path(self, s):
        k = min(2, int(s * 3))
        f = s * 3 - k
        pts = [(0.0, -0.3), (-0.35, 0.2), (0.35, 0.25)]
        u, v = pts[k]
        return u, v, 0.2 < f < 0.55

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("dot", u1 + float(self.rng.uniform(-0.1, 0.1)), v1 + float(self.rng.uniform(-0.1, 0.1)), 0.12,
                     mix(PINK, (255, 245, 250), 0.55)))
        if len(self.dust) < 260:
            for _ in range(3):
                a = float(self.rng.uniform(0, 2 * math.pi))
                sp = float(self.rng.uniform(80, 420))
                self.dust.append([self.tip[0], self.tip[1], math.cos(a) * sp, math.sin(a) * sp - 120, self.t])

    def after(self, dt, evs):
        super().after(dt, evs)
        for d in self.dust:
            d[0] += d[2] * dt; d[1] += d[3] * dt
            d[2] *= (1 - 1.6 * dt); d[3] *= (1 - 1.6 * dt); d[3] += 40 * dt

    def snapshot(self):
        s = super().snapshot()
        s["dust"] = [(d[0], d[1], self.t - d[4]) for d in self.dust]
        return s

    def draw(self, dr, s, t, S):
        super().draw(dr, s, t, S)
        P = lambda v: v * S
        for (x, y, age) in s["dust"]:
            if age < 2.0:
                k = age / 2.0
                c = mix((250, 246, 252), WALL, max(0.0, (k - 0.6) / 0.4) * 0.8)
                circle(dr, P(x), P(y), P(12 * (1.0 - 0.7 * k) + 2), c)


class FinalLook(Step):
    title = "FINAL LOOK"
    tool = "sponge"
    say = ("Final look.", "Nailed it.")
    stamp = ("NAILED IT", GREEN)
    stamp_y = 0.27
    mood = "win"
    hop = (200.0, 260.0)
    t_go = 99.0
    hold_s = 3.6

    def after(self, dt, evs):
        # la maquilleuse a rangé ses pinceaux ; on regarde le résultat
        self.tip = [330.0, 1330.0]
        self.press = False
        if self.t >= 2.2 and self.hit_t >= 2.2 and not self.payoff:
            self.finish("NAILED IT")
            self.line(self.say[1], "verdict", self.t + 1.2)


    def draw(self, dr, s, t, S):
        super().draw(dr, s, t, S)
        if s["end"] is not None:
            P = lambda v: v * S
            age = t - s["end"]
            for k in range(8):
                a = k * math.pi / 4 + age * 1.2
                rr = 230 + 20 * math.sin(age * 6 + k)
                x, y = s["bx"] + math.cos(a) * rr, s["by"] + math.sin(a) * rr
                sz = 16 + 6 * math.sin(age * 8 + k * 1.7)
                dr.polygon([(P(x), P(y - sz)), (P(x + sz * 0.3), P(y)), (P(x), P(y + sz)), (P(x - sz * 0.3), P(y))], fill=(255, 236, 150))
                dr.polygon([(P(x - sz), P(y)), (P(x), P(y + sz * 0.3)), (P(x + sz), P(y)), (P(x), P(y - sz * 0.3))], fill=(255, 236, 150))


DEFAULTS = {
    "ball_r": R_FACE, "gravity": G,
    "chapter_max_s": 13.0,
    "counter_font_size": 60, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 2.6, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(Foundation, {}), (Blush, {}), (Eyeliner, {}), (Mascara, {}), (Lipstick, {}), (Powder, {}), (FinalLook, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        LOOK.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
