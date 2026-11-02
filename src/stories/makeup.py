"""
Prototype « tuto maquillage » : une maquilleuse fait un tuto sur Bounce, assis sur un
tabouret devant le miroir de loge. Chaque étape est un geste précis de sa main ; Bounce
ne s'arrête pas de rebondir, et le trait se dépose là où son visage se trouve à cet
instant : le maquillage s'accumule pour de vrai, en coordonnées de son visage. Quand il
a sauté hors de portée, le geste se pose sur le miroir, là où il était : elle vise juste,
c'est lui qui bouge.

    python3 src/stories/makeup.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, SCENE_TOP, GREEN, AMBER, glow, mix

R_FACE = 240.0                 # Bounce en très gros plan : son visage est la toile
G = 1500.0                     # des rebonds amples et lents : chaque retombée a le temps de dire son nom
SEAT_Y = 1460.0                # le dessus du tabouret
REST_X = 560.0
PINK = (255, 20, 200)
WALL = (34, 28, 44)
ARTIST = (64, 66, 96)
HANDLE = (196, 160, 104)       # les manches des outils : bois clair, bien visibles
MIRROR = (300.0, 530.0, 900.0, 1340.0)
SHOULDER = (150.0, 900.0)

BEIGE = (242, 214, 180)
BLUE = (60, 176, 255)
WHITE = (250, 248, 252)
BLACK = (14, 10, 18)
VIOLET = (128, 40, 176)
GOLD = (255, 220, 110)

LOOK = []                      # le maquillage déposé sur le visage, dans l'ordre : il traverse les étapes
MISS = []                      # ce qui s'est posé sur le miroir quand il n'était plus là


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, k):
    return a + (b - a) * k


def smooth(k):
    k = clamp(k, 0.0, 1.0)
    return k * k * (3 - 2 * k)


def in_mirror(x, y):
    return MIRROR[0] + 8 < x < MIRROR[2] - 8 and MIRROR[1] + 8 < y < MIRROR[3] - 8


class Step(Chapter):
    """Une étape du tuto : la main approche, fait son geste, se retire."""
    title = None
    stamp = None
    mood = None
    hold_s = 9.0               # remplacé à la chute par une tenue calée sur une retombée
    hold_min = 2.7
    tool = "sponge"
    hop = (110.0, 140.0)
    first_h = 460.0            # le saut d'ouverture : le titre se dit pendant qu'il est en l'air
    title_at = 0.55            # le titre attend que le dernier « Bounce » de l'étape d'avant soit fini
    t_go = 0.35
    approach = 0.6
    stroke_s = 3.0
    track = 0.15               # la main suit à peine le visage : elle vise juste, c'est lui qui bouge
    speed = 1800.0             # vitesse max de la main (px/s), sous le seuil de téléportation du contrôle
    say = ("", "")             # (titre dit, verdict après la chute)

    def setup(self):
        self.R = R_FACE
        lo, hi = self.hop
        self.hop_init(REST_X, SEAT_Y, start_h=lo, gain=(0.85, 1.2), min_h=lo, max_h=hi, wobble=16.0,
                      xmin=REST_X - 20, xmax=REST_X + 20, h_ref=hi)
        self.by = SEAT_Y - self.R - 1.0
        self.vy = -math.sqrt(2 * G * self.first_h)
        self.vx = 0.0
        self.rest = (REST_X, SEAT_Y - self.R - 0.45 * lo)
        self.aim = list(self.rest)
        self.home = (300.0, 1380.0)
        self.tip = list(self.home)
        self.press = False
        self.last_uv = None
        self.last_xy = None
        self.cut_set = False
        self.line(self.say[0], "title", self.title_at)

    def path(self, s):
        """Le geste, en coordonnées du visage au repos : (u, v, appui) pour s dans [0, 1]."""
        return 0.0, 0.0, False

    def deposit(self, u0, v0, u1, v1):
        pass

    def miss(self, x0, y0, x1, y1):
        """Le geste qui tombe à côté : il marque le miroir, là où le visage devait être."""
        if in_mirror(x1, y1):
            MISS.append(("seg", x0, y0, x1, y1, self.miss_col(), self.miss_w()))

    def miss_col(self):
        return BEIGE

    def miss_w(self):
        return 20.0

    def after(self, dt, evs):
        t = self.t
        tx = lerp(self.rest[0], self.bx, self.track)
        ty = lerp(self.rest[1], self.by, self.track)
        k = 1 - math.exp(-dt * 6.0)
        self.aim[0] += (tx - self.aim[0]) * k
        self.aim[1] += (ty - self.aim[1]) * k
        t1 = self.t_go + self.approach
        t2 = t1 + self.stroke_s
        if t < self.t_go:
            tgt, press = self.home, False
        elif t < t1:
            u, v, _ = self.path(0.0)
            a = smooth((t - self.t_go) / self.approach)
            tgt = (lerp(self.home[0], self.aim[0] + u * self.R, a), lerp(self.home[1], self.aim[1] + v * self.R, a))
            press = False
        elif t < t2:
            u, v, press = self.path((t - t1) / self.stroke_s)
            tgt = (self.aim[0] + u * self.R, self.aim[1] + v * self.R)
        else:
            tgt, press = self.home, False
            if not self.payoff and self.hit_t >= t2:
                self.finish("DONE")                       # la chute tombe sur une retombée : on l'entend
                self.line(self.say[1], "verdict", self.hit_t + 1.02)    # la voix de synthèse varie d'un rendu à l'autre : de la marge
                self.vy = -math.sqrt(2 * G * 330.0)       # un grand saut : le verdict se dit pendant qu'il vole
        # la coupe tombe juste après une retombée : son dernier « Bounce » finit avant le titre suivant
        if self.payoff and not self.cut_set and self.hit_t > self.end_t + self.hold_min:
            self.hold_s = self.hit_t - self.end_t + 0.55
            self.cut_set = True
        # la main ne se téléporte jamais
        ddx, ddy = tgt[0] - self.tip[0], tgt[1] - self.tip[1]
        dd = math.hypot(ddx, ddy)
        vmax = self.speed * dt
        if dd > vmax:
            self.tip[0] += ddx / dd * vmax; self.tip[1] += ddy / dd * vmax
            press = press and dd < 40.0
        else:
            self.tip = [tgt[0], tgt[1]]
        self.press = press
        x, y = self.tip
        dx, dy = x - self.bx, y - self.by
        on_face = math.hypot(dx, dy) < 0.97 * self.R
        if press and on_face:
            uv = (dx / self.R, dy / self.R)
            a = self.last_uv if self.last_uv is not None else uv
            self.deposit(a[0], a[1], uv[0], uv[1])
            self.last_uv = uv
            self.last_xy = None
        elif press and math.hypot(dx, dy) > 1.02 * self.R:
            a = self.last_xy if self.last_xy is not None else (x, y)
            self.miss(a[0], a[1], x, y)
            self.last_xy = (x, y)
            self.last_uv = None
        else:
            self.last_uv = None
            self.last_xy = None
        self.extra(dt)

    def extra(self, dt):
        pass

    # ------------------------------------------------------------------ contrat
    def snapshot(self):
        s = self.base_snap()
        s["tip"] = tuple(self.tip)
        s["press"] = self.press
        s["n"] = len(LOOK)
        s["m"] = len(MISS)
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
        room(dr, P, W, H, MISS[:s["m"]])
        stool(dr, P)
        bx, by = s["bx"], s["by"]
        base.ball(dr, P(bx), P(by), P(self.R))
        draw_misses(dr, P, MISS[:s["m"]], bx, by, self.R)    # les traces sur le miroir, autour de lui
        draw_look(dr, P(bx), P(by), P(self.R), LOOK[:s["n"]])
        base.hero_face(dr, P(bx), P(by), P(self.R))          # ses yeux et sa bouche restent par-dessus
        self.draw_extra(dr, P, s, t)
        artist(dr, P, s["tip"], self.tool, s["press"], t)
        frame_ui(dr, P, W, t, self.cfg)

    def draw_extra(self, dr, P, s, t):
        pass


# ---------------------------------------------------------------- le décor commun
def room(dr, P, W, H, misses):
    dr.rectangle([0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
    x0, y0, x1, y1 = MIRROR
    glow(dr, P, 600, 900, 560, (255, 220, 160), WALL, 0.10, rings=6)
    dr.rectangle([P(x0 - 30), P(y0 - 30), P(x1 + 30), P(y1 + 30)], fill=(70, 56, 50))
    dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(46, 52, 70))
    dr.polygon([(P(x0 + 40), P(y0)), (P(x0 + 120), P(y0)), (P(x0), P(y0 + 140)), (P(x0), P(y0 + 60))], fill=(58, 64, 84))
    for k in range(6):
        for xx in (x0 - 15, x1 + 15):
            circle(dr, P(xx), P(y0 + k * (y1 - y0) / 5), P(14), (255, 236, 190))
    for k in range(7):
        circle(dr, P(x0 + k * (x1 - x0) / 6), P(y0 - 15), P(14), (255, 236, 190))
    # le chariot de produits à droite
    dr.rectangle([P(840), P(1380), P(930), P(1394)], fill=(90, 80, 100))
    dr.rectangle([P(846), P(1394), P(854), P(1660)], fill=(70, 64, 80))
    dr.rectangle([P(916), P(1394), P(924), P(1660)], fill=(70, 64, 80))
    for (xx, w, h, c) in ((848, 16, 66, (230, 150, 190)), (868, 22, 46, BEIGE), (894, 12, 74, (40, 120, 200)), (910, 12, 44, VIOLET)):
        dr.rectangle([P(xx), P(1380 - h), P(xx + w), P(1380)], fill=c)
    dr.rectangle([0, P(1650), P(W), P(H)], fill=(44, 36, 46))


def draw_misses(dr, P, misses, bx, by, R):
    """Ce que le geste a laissé sur le miroir quand Bounce n'était plus là : dessiné
    par-dessus son halo, jamais sur son visage (il est devant le miroir)."""
    if not misses:
        return
    from PIL import Image, ImageDraw, ImageChops
    x0, y0, x1, y1 = MIRROR
    w, h = int(P(x1 - x0)), int(P(y1 - y0))
    layer = Image.new("RGB", (w, h), (0, 0, 0))
    cover = Image.new("L", (w, h), 0)
    dl, dc = ImageDraw.Draw(layer), ImageDraw.Draw(cover)
    Q = lambda x, y: (P(x - x0), P(y - y0))
    for (_, a, b, c, d, col, ww) in misses:
        lw = max(1, int(P(ww)))
        for (dd, fill) in ((dl, col), (dc, 255)):
            dd.line([Q(a, b), Q(c, d)], fill=fill, width=lw)
            qx, qy = Q(c, d)
            dd.ellipse([qx - lw / 2, qy - lw / 2, qx + lw / 2, qy + lw / 2], fill=fill)
    hole = Image.new("L", (w, h), 255)
    hx, hy = Q(bx, by)
    ImageDraw.Draw(hole).ellipse([hx - P(R), hy - P(R), hx + P(R), hy + P(R)], fill=0)
    dr._image.paste(layer, (int(P(x0)), int(P(y0))), ImageChops.multiply(cover, hole))


def stool(dr, P):
    dr.ellipse([P(REST_X - 140), P(SEAT_Y - 6), P(REST_X + 140), P(SEAT_Y + 24)], fill=(96, 84, 120))
    dr.rectangle([P(REST_X - 14), P(SEAT_Y + 18), P(REST_X + 14), P(1650)], fill=(150, 150, 165))
    dr.ellipse([P(REST_X - 90), P(1640), P(REST_X + 90), P(1662)], fill=(110, 110, 125))


def frame_ui(dr, P, W, t, cfg, show=True):
    """L'habillage d'un tuto filmé : REC et le nom de la vidéo ; le haut redevient noir."""
    if show:
        if int(t * 2) % 2 == 0:
            circle(dr, P(58), P(SCENE_TOP + 44), P(11), (235, 50, 60))
        f = base.font(int(P(32)))
        dr.text((P(80), P(SCENE_TOP + 44)), "MAKEUP TUTORIAL", fill=(240, 236, 246), anchor="lm", font=f)
    dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(cfg["bg_color"]))


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
        elif it[0] == "star":
            _, u, v, rad, col = it
            q = p(u, v)
            rr = rad * r
            pts = [(q[0], q[1] - rr), (q[0] + rr * 0.3, q[1]), (q[0], q[1] + rr), (q[0] - rr * 0.3, q[1])]
            pts2 = [(q[0] - rr, q[1]), (q[0], q[1] + rr * 0.3), (q[0] + rr, q[1]), (q[0], q[1] - rr * 0.3)]
            for pp in (pts, pts2):
                dl.polygon(pp, fill=col)
                dc.polygon(pp, fill=255)
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
    """La maquilleuse, sans visage, à gauche : épaule, bras en deux segments, main, outil.
    La pointe de l'outil est exactement là où le geste dépose."""
    col = ARTIST
    dr.rounded_rectangle([P(-80), P(840), P(190), P(1700)], radius=int(P(70)), fill=col)
    circle(dr, P(80), P(720), P(92), col)
    circle(dr, P(20), P(640), P(46), dim(col, 0.8))
    sh = SHOULDER
    ang = math.atan2(tip[1] - sh[1], tip[0] - sh[0])
    L_tool = {"sponge": 40, "brush": 120, "pencil": 120, "lipstick": 90, "puff": 50, "shaker": 70}[tool]
    ux, uy = math.cos(ang), math.sin(ang)
    hx, hy = tip[0] - ux * L_tool, tip[1] - uy * L_tool
    L1 = L2 = 340.0
    dx, dy = hx - sh[0], hy - sh[1]
    d = math.hypot(dx, dy)
    if d > L1 + L2 - 2:                    # hors de portée : le bras tendu, l'outil suit la pointe
        hx, hy = sh[0] + dx / d * (L1 + L2 - 2), sh[1] + dy / d * (L1 + L2 - 2)
        d = L1 + L2 - 2
    a0 = math.atan2(hy - sh[1], hx - sh[0])
    c = clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * max(d, 1.0)), -1.0, 1.0)
    ea = a0 + math.acos(c)
    ex, ey = sh[0] + L1 * math.cos(ea), sh[1] + L1 * math.sin(ea)
    dr.line([(P(sh[0]), P(sh[1])), (P(ex), P(ey))], fill=col, width=max(1, int(P(50))))
    dr.line([(P(ex), P(ey)), (P(hx), P(hy))], fill=dim(col, 1.1), width=max(1, int(P(42))))
    circle(dr, P(ex), P(ey), P(24), col)
    tx, ty = tip
    if tool == "sponge":
        dr.line([(P(hx), P(hy)), (P(tx), P(ty))], fill=HANDLE, width=max(1, int(P(10))))
        circle(dr, P(tx), P(ty), P(38), BEIGE)
    elif tool == "puff":
        circle(dr, P(tx), P(ty), P(50), WHITE)
        circle(dr, P(tx - 12), P(ty - 12), P(16), (255, 255, 255))
    elif tool == "brush":
        dr.line([(P(hx), P(hy)), (P(tx - ux * 30), P(ty - uy * 30))], fill=HANDLE, width=max(1, int(P(13))))
        circle(dr, P(tx), P(ty), P(30), BLUE)
    elif tool == "pencil":
        dr.line([(P(hx), P(hy)), (P(tx - ux * 20), P(ty - uy * 20))], fill=HANDLE, width=max(1, int(P(12))))
        dr.line([(P(tx - ux * 20), P(ty - uy * 20)), (P(tx), P(ty))], fill=BLACK, width=max(1, int(P(8))))
    elif tool == "lipstick":
        dr.line([(P(hx), P(hy)), (P(tx - ux * 28), P(ty - uy * 28))], fill=GOLD, width=max(1, int(P(24))))
        dr.line([(P(tx - ux * 28), P(ty - uy * 28)), (P(tx), P(ty))], fill=VIOLET, width=max(1, int(P(18))))
    elif tool == "shaker":
        dr.rounded_rectangle([P(tx - 22), P(ty - 40), P(tx + 22), P(ty + 20)], radius=int(P(8)), fill=(200, 200, 220))
        dr.rectangle([P(tx - 22), P(ty + 14), P(tx + 22), P(ty + 26)], fill=GOLD)
    circle(dr, P(hx), P(hy), P(32), dim(col, 1.25))


# ---------------------------------------------------------------- les étapes, de plus en plus folles
class Foundation(Step):
    title = "FOUNDATION"
    title_at = 0.0
    tool = "sponge"
    say = ("Foundation.", "Flawless.")
    hop = (185.0, 215.0)
    t_go = 0.15
    approach = 0.6
    stroke_s = 4.1
    DABS = [(-0.45, 0.1), (0.45, 0.1), (0.0, -0.55), (-0.3, 0.55), (0.3, 0.55), (0.0, 0.15), (-0.55, -0.3), (0.55, -0.3)]

    def path(self, s):
        n = len(self.DABS)
        k = min(n - 1, int(s * n))
        f = s * n - k
        u, v = self.DABS[k]
        if f > 0.6:
            nu, nv = self.DABS[min(n - 1, k + 1)]
            g = smooth((f - 0.6) / 0.4)
            return lerp(u, nu, g), lerp(v, nv, g), False
        return u, v, 0.12 < f < 0.5

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("dot", u1, v1, 0.17, BEIGE))
        if math.hypot(u1 - u0, v1 - v0) > 1e-6:
            LOOK.append(("seg", u0, v0, u1, v1, BEIGE, 0.34))

    def miss(self, x0, y0, x1, y1):
        if in_mirror(x1, y1):
            MISS.append(("seg", x0, y0, x1, y1, BEIGE, 60.0))


class Eyeshadow(Step):
    title = "EYESHADOW"
    tool = "brush"
    say = ("Eyeshadow.", "Just the lids.")
    hop = (195.0, 235.0)
    stroke_s = 4.6

    def path(self, s):
        side = -1.0 if s < 0.5 else 1.0
        q = (s % 0.5) / 0.5
        if q < 0.06 or q > 0.94:
            return side * 0.36, -0.36, False
        return side * (0.36 + 0.16 * math.sin(q * 6 * math.pi)), -0.36 + 0.03 * math.cos(q * 12 * math.pi), True

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, BLUE, 0.16))

    def miss_col(self):
        return BLUE


class Powder(Step):
    title = "POWDER"
    tool = "puff"
    say = ("Powder.", "One light puff.")
    hop = (190.0, 240.0)
    stroke_s = 2.4
    speed = 2200.0

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
        LOOK.append(("dot", u1 + float(self.rng.uniform(-0.12, 0.12)), v1 + float(self.rng.uniform(-0.12, 0.12)), 0.11, WHITE))
        self.burst(4)

    def miss(self, x0, y0, x1, y1):
        if in_mirror(x1, y1):
            MISS.append(("seg", x0, y0, x1, y1, (210, 210, 222), 44.0))
        self.burst(2)

    def burst(self, n):
        if len(self.dust) < 340:
            for _ in range(n):
                a = float(self.rng.uniform(0, 2 * math.pi))
                sp = float(self.rng.uniform(120, 620))
                self.dust.append([self.tip[0], self.tip[1], math.cos(a) * sp, math.sin(a) * sp - 160, self.t])

    def extra(self, dt):
        for d in self.dust:
            d[0] += d[2] * dt; d[1] += d[3] * dt
            d[2] *= (1 - 1.5 * dt); d[3] *= (1 - 1.5 * dt); d[3] += 40 * dt

    def snapshot(self):
        s = super().snapshot()
        s["dust"] = [(d[0], d[1], self.t - d[4]) for d in self.dust]
        return s

    def draw_extra(self, dr, P, s, t):
        for (x, y, age) in s["dust"]:
            if age < 2.0:
                k = age / 2.0
                c = mix(WHITE, WALL, max(0.0, (k - 0.6) / 0.4) * 0.8)
                circle(dr, P(x), P(y), P(16 * (1.0 - 0.7 * k) + 3), c)


class Eyeliner(Step):
    title = "EYELINER"
    tool = "pencil"
    say = ("Eyeliner.", "One clean line.")
    hop = (230.0, 290.0)
    stroke_s = 3.4
    speed = 2400.0

    def path(self, s):
        if s < 0.46:
            q = s / 0.46
            return lerp(0.2, 0.74, q), lerp(-0.12, -0.38, q), 0.05 < q < 0.95
        if s < 0.54:
            q = (s - 0.46) / 0.08
            return lerp(0.74, -0.2, q), lerp(-0.38, -0.12, q), False
        q = (s - 0.54) / 0.46
        return lerp(-0.2, -0.74, q), lerp(-0.12, -0.38, q), 0.05 < q < 0.95

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, BLACK, 0.05))

    def miss_col(self):
        return BLACK

    def miss_w(self):
        return 10.0


class Lipstick(Step):
    title = "LIPSTICK"
    tool = "lipstick"
    say = ("Lipstick.", "Inside the lines.")
    hop = (270.0, 330.0)
    stroke_s = 5.6
    speed = 2400.0

    def path(self, s):
        q = (s * 4) % 2.0
        q = q if q < 1 else 2 - q
        return lerp(-0.28, 0.28, q), 0.42 + 0.03 * math.sin(s * 30), 0.04 < s < 0.96

    def deposit(self, u0, v0, u1, v1):
        LOOK.append(("seg", u0, v0, u1, v1, VIOLET, 0.13))

    def miss_col(self):
        return VIOLET

    def miss_w(self):
        return 26.0


class Glitter(Step):
    title = "GLITTER"
    tool = "shaker"
    say = ("Glitter.", "Just a pinch.")
    hop = (300.0, 380.0)
    stroke_s = 3.0
    speed = 2400.0

    def setup(self):
        super().setup()
        self.flakes = []

    def path(self, s):
        return 0.5 * math.sin(s * 9), -0.75 + 0.1 * math.cos(s * 13), True

    def extra(self, dt):
        t = self.t
        t1 = self.t_go + self.approach
        if t1 <= t < t1 + self.stroke_s and len(self.flakes) < 520:
            for _ in range(5):
                self.flakes.append([self.tip[0] + float(self.rng.uniform(-20, 20)), self.tip[1] + 20,
                                    float(self.rng.uniform(-90, 90)), float(self.rng.uniform(80, 260)),
                                    GOLD if self.rng.random() < 0.5 else WHITE, False])
        for f in self.flakes:
            if f[5]:
                continue
            f[3] += 900 * dt
            f[0] += f[2] * dt; f[1] += f[3] * dt
            dx, dy = f[0] - self.bx, f[1] - self.by
            if math.hypot(dx, dy) < 0.95 * self.R:
                LOOK.append(("star", dx / self.R, dy / self.R, 0.035, f[4]))
                f[5] = True
            elif f[1] > SEAT_Y + 180:
                f[5] = True

    def deposit(self, u0, v0, u1, v1):
        pass

    def miss(self, x0, y0, x1, y1):
        pass

    def snapshot(self):
        s = super().snapshot()
        s["flakes"] = [(f[0], f[1], f[4]) for f in self.flakes if not f[5]]
        return s

    def draw_extra(self, dr, P, s, t):
        for (x, y, c) in s["flakes"]:
            circle(dr, P(x), P(y), P(5), c)


class Reveal(Step):
    """La fin : avant / après, côte à côte. La photo d'avant, blasée ; lui, après, ravi."""
    title = "BEFORE / AFTER"
    say = ("Before. After.", "Slay.")
    stamp = ("SLAY", GREEN)
    stamp_y = 0.27
    mood = "win"
    hop = (160.0, 210.0)
    hold_s = 3.4
    AX = 700.0

    def setup(self):
        self.R = 200.0
        lo, hi = self.hop
        self.hop_init(self.AX, SEAT_Y, start_h=lo, gain=(0.85, 1.2), min_h=lo, max_h=hi, wobble=10.0,
                      xmin=self.AX - 12, xmax=self.AX + 12, h_ref=hi)
        self.by = SEAT_Y - self.R - 1.0
        self.vy = -math.sqrt(2 * G * 520.0)
        self.vx = 0.0
        self.tip = [300.0, 1380.0]
        self.press = False
        self.line(self.say[0], "title", 0.45)

    def after(self, dt, evs):
        if not self.payoff and self.t >= 2.0 and self.hit_t >= 2.0:
            self.finish("SLAY")
            self.line(self.say[1], "verdict", self.hit_t + 1.02)
            self.vy = -math.sqrt(2 * G * 330.0)

    def bodies(self, s):
        return []

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
        glow(dr, P, 700, 1100, 520, (255, 220, 160), WALL, 0.12, rings=6)
        # après : lui, en vrai, maquillé, qui rebondit
        dr.rectangle([0, P(1650), P(W), P(H)], fill=(44, 36, 46))
        dr.ellipse([P(self.AX - 120), P(SEAT_Y - 6), P(self.AX + 120), P(SEAT_Y + 24)], fill=(96, 84, 120))
        bx, by = s["bx"], s["by"]
        base.ball(dr, P(bx), P(by), P(self.R))
        draw_look(dr, P(bx), P(by), P(self.R), LOOK[:s["n"]])
        base.hero_face(dr, P(bx), P(by), P(self.R))
        f = base.font(int(P(46)))
        if s["end"] is None:
            dr.text((P(self.AX), P(560)), "AFTER", fill=(240, 236, 246), anchor="mm", font=f)
        # avant : la photo du début, propre et blasée
        k = clamp(t / 0.4, 0.0, 1.0)
        px, py, pw, ph = 70.0, 640.0, 320.0, 400.0
        dr.rectangle([P(px), P(py), P(px + pw), P(py + ph + 70)], fill=(236, 232, 226))
        dr.rectangle([P(px + 16), P(py + 16), P(px + pw - 16), P(py + ph - 16)], fill=(40, 34, 52))
        expr = base.HERO["expr"]
        base.HERO["expr"] = "calm"
        tl = base.HERO["tilt"]
        base.HERO["tilt"] = 0.0
        pos = base.HERO["pos"]
        base.ball(dr, P(px + pw / 2), P(py + ph / 2 + 10), P(84 * k + 1))
        base.HERO["pos"] = pos
        base.HERO["expr"], base.HERO["tilt"] = expr, tl
        dr.text((P(px + pw / 2), P(py + ph + 34)), "BEFORE", fill=(40, 34, 52), anchor="mm", font=f)
        frame_ui(dr, P, W, t, self.cfg, show=s["end"] is None)


DEFAULTS = {
    "ball_r": R_FACE, "gravity": G,
    "chapter_max_s": 13.0,
    "counter_font_size": 64, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 2.6, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(Foundation, {}), (Eyeshadow, {}), (Powder, {}), (Eyeliner, {}), (Lipstick, {}), (Glitter, {}), (Reveal, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        LOOK.clear()
        MISS.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
