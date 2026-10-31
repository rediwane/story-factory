"""
Histoire-liste : les six métiers que Bounce a essayés en une semaine. Six chapitres,
chacun un lieu, une mise en place instantanée et une chute physique causée par ses
rebonds ; le narrateur enchaîne ; le sixième retourne la série : le seul métier où
rebondir sans arrêt est exactement ce qu'on attend de lui. Un dimanche en épilogue.

    python3 src/stories/six_jobs.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim, Hopper

RED = (226, 54, 66)
GREEN = (90, 210, 130)
FLOOR_Y = 1500.0
HOP = dict(start_h=300.0, gain=(0.9, 1.15), min_h=220.0, max_h=520.0, h_ref=300.0)


class Chapter(Hopper):
    title = None
    stamp = None
    mood = None
    hold_s = 1.5

    def __init__(self, cfg, rng):
        self.cfg, self.rng = cfg, rng
        self.W, self.H = cfg["width"], cfg["height"]
        self.R, self.g = cfg["ball_r"], cfg["gravity"]
        self.t = 0.0
        self.lines, self.replies = [], []
        self.done = self.payoff = False
        self.outcome = None
        self.end_t = None
        self.setup()

    def setup(self):
        pass

    def line(self, text, key, when=None):
        self.lines.append((self.t if when is None else when, text, key))

    def finish(self, outcome):
        if self.payoff:
            return
        self.payoff, self.outcome, self.end_t = True, outcome, self.t

    def counter(self, s):
        return None if s.get("end") else self.title

    def on_land(self, k, evs):
        pass

    def step(self, dt):
        self.t += dt
        evs = []
        self.hop_step(dt, evs)
        self.after(dt, evs)
        return evs

    def after(self, dt, evs):
        pass

    def settle(self):
        """Après la chute : Bounce se pose au prochain contact et reste là."""
        if self.payoff and self.on == "air" and self.vy > 0 and self.by >= self.floor_y - self.R - 2:
            self.on = "still"; self.by = self.floor_y - self.R

    def base_snap(self):
        return {"t": self.t, "bx": self.bx, "by": self.by, "end": self.end_t, "hit_t": self.hit_t, "on": self.on}

    # --- décor commun
    def figure(self, dr, P, x, y_floor, col, h=260, w=96, tilt=0.0):
        """Un personnage sans visage : tronc, tête, deux jambes. (x, y_floor) = pieds."""
        dr.rectangle([P(x - w / 2), P(y_floor - h), P(x + w / 2), P(y_floor - 12)], fill=col)
        dr.rectangle([P(x - w / 2), P(y_floor - 12), P(x - 10), P(y_floor)], fill=dim(col, 0.7))
        dr.rectangle([P(x + 10), P(y_floor - 12), P(x + w / 2), P(y_floor)], fill=dim(col, 0.7))
        circle(dr, P(x + tilt * 24), P(y_floor - h - 46), P(42), col)

    def room(self, dr, P, wall, floor, top=430.0, floor_y=FLOOR_Y, skirting=True):
        W, H = self.W, self.H
        dr.rectangle([0, P(top), P(W), P(floor_y)], fill=wall)
        dr.rectangle([0, P(floor_y), P(W), P(H)], fill=floor)
        if skirting:
            dr.rectangle([0, P(floor_y - 26), P(W), P(floor_y)], fill=dim(wall, 0.75))
        dr.rectangle([0, P(floor_y), P(W), P(floor_y + 8)], fill=dim(floor, 1.35))

    def bounce(self, dr, P, s):
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 1. bibliothécaire
class Library(Chapter):
    title = "MONDAY · LIBRARIAN"
    stamp = ("FIRED", RED)
    mood = "lose"
    hold_s = 1.2
    PX, PY = 610.0, FLOOR_Y          # le pivot de l'étagère : son pied gauche
    SW, SH = 420.0, 980.0            # largeur, hauteur de l'étagère

    def setup(self):
        rng = self.rng
        self.hop_init(470.0, FLOOR_Y, wobble=50.0, xmin=400, xmax=540, **HOP)
        self.line("This is Bounce. He says one word, and he never stops bouncing. Last week, he tried six jobs.", "intro", 0.0)
        self.line("Monday. Librarian.", "title", 5.9)
        pal = [(170, 60, 60), (60, 110, 160), (200, 160, 70), (80, 140, 90), (150, 90, 160), (210, 120, 80), (90, 90, 120)]
        self.books = []
        for sy in (190.0, 390.0, 590.0, 790.0):          # hauteur des rayons depuis le sol
            x = 30.0
            while x < self.SW - 40:
                w = rng.uniform(34, 54); h = rng.uniform(120, 165)
                self.books.append([x + w / 2, sy, w, h, pal[rng.integers(len(pal))], rng.uniform(-0.04, 0.04)])
                x += w + 4
        self.lean = 0.0
        self.lean_v = 0.0
        self.falling = False
        self.down = False
        self.shake = 0.0
        self.spill = []

    def on_land(self, k, evs):
        if self.down:
            return
        self.shake = 1.0
        if self.t < self.cfg["lib_arm_s"]:
            return                      # tant que le lundi n'est pas annoncé, l'étagère tient
        bump = 1.6 if self.bx > 500 else 1.0
        self.lean += self.cfg["lib_lean"] * k * bump * self.rng.uniform(0.5, 1.3)
        for b in self.books:
            b[5] += self.rng.uniform(-0.03, 0.06) * k
        if self.lean > 0.15 and not self.falling:
            self.falling = True
            self.lean_v = 0.3
            evs.append(("event", "shelf tips t %.2f" % self.t))

    def after(self, dt, evs):
        self.shake = max(0.0, self.shake - 4 * dt)
        if self.falling and not self.down:
            self.lean_v += 6.0 * math.sin(self.lean) * dt + 2.0 * dt
            self.lean += self.lean_v * dt
            if self.lean >= math.pi / 2:
                self.lean = math.pi / 2
                self.down = True
                evs.append(("hit", "shelf"))
                for b in self.books:
                    self.spill.append((self.PX - self.rng.uniform(0, self.SH - 60) - 60 + self.rng.uniform(-40, 40), b[2], b[3], b[4], self.rng.uniform(0, math.pi)))
                self.on = "under"
                self.bx = min(self.bx, 520.0)
                self.by = FLOOR_Y - self.R
                self.finish("FIRED")
                self.line("Fired.", "fired", self.t + 0.3)
        if self.falling and not self.down and self.on == "air" and self.vy > 0 and self.by >= FLOOR_Y - self.R - 2:
            self.on = "still"; self.by = FLOOR_Y - self.R

    def snapshot(self):
        s = self.base_snap()
        s["lean"] = self.lean; s["down"] = self.down; s["shake"] = self.shake
        s["books"] = [tuple(b) for b in self.books]; s["spill"] = list(self.spill)
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (52, 40, 34), (70, 52, 38))
        # tableau et lampe au mur
        dr.rectangle([P(120), P(620), P(420), P(820)], fill=(90, 70, 50))
        dr.rectangle([P(140), P(640), P(400), P(800)], fill=(60, 90, 70))
        circle(dr, P(260), P(1000), P(40), (60, 140, 90)); dr.rectangle([P(254), P(1000), P(266), P(1100)], fill=(200, 170, 90))
        if s["down"]:
            # l'étagère à plat, les livres répandus, Bounce dessous
            self.bounce(dr, P, s)
            dr.rectangle([P(self.PX - self.SH), P(FLOOR_Y - self.SW * 0.35), P(self.PX), P(FLOOR_Y)], fill=(40, 28, 22))
            dr.rectangle([P(self.PX - self.SH), P(FLOOR_Y - self.SW * 0.35), P(self.PX), P(FLOOR_Y - self.SW * 0.35 + 18)], fill=(90, 62, 44))
            for (x, w, h, col, a) in s["spill"]:
                ca, sa = math.cos(a), math.sin(a)
                cx, cy = x, FLOOR_Y - self.SW * 0.35 - w / 2
                pts = [(-h / 2, -w / 2), (h / 2, -w / 2), (h / 2, w / 2), (-h / 2, w / 2)]
                dr.polygon([(P(cx + px * ca - py * sa * 0.3), P(cy + px * sa * 0.3 + py * ca)) for px, py in pts], fill=col)
            return
        a = s["lean"]
        ca, sa = math.cos(a), math.sin(a)
        sx = 8 * math.sin(t * 40) * s["shake"]

        def T(x, y):
            # repère de l'étagère : x vers la droite depuis le pivot, y vers le haut depuis le sol
            return (P(self.PX + sx + x * ca - y * sa * 1.0), P(self.PY - (x * sa + y * ca)))
        dr.polygon([T(0, 0), T(self.SW, 0), T(self.SW, self.SH), T(0, self.SH)], fill=(40, 28, 22))
        for sy in (190.0, 390.0, 590.0, 790.0, self.SH - 20):
            dr.polygon([T(0, sy), T(self.SW, sy), T(self.SW, sy - 18), T(0, sy - 18)], fill=(90, 62, 44))
        for (bx, by, w, h, col, lean) in s["books"]:
            lb = max(-0.3, min(0.3, lean))
            cb, sb = math.cos(lb), math.sin(lb)
            pts = [(bx - w / 2, by), (bx + w / 2, by), (bx + w / 2 - h * sb, by + h * cb), (bx - w / 2 - h * sb, by + h * cb)]
            dr.polygon([T(x, y) for x, y in pts], fill=col)
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 2. serveur
class Waiter(Chapter):
    title = "TUESDAY · WAITER"
    stamp = ("FIRED", RED)
    mood = "lose"

    def setup(self):
        rng = self.rng
        self.hop_init(440.0, FLOOR_Y, wobble=80.0, xmin=260, xmax=640, **dict(HOP, max_h=420.0))
        self.line("Tuesday. Waiter.", "title", 0.0)
        self.tray_w = 320.0
        self.glasses = [{"dx": d, "lift": 0.0, "vl": 0.0, "st": "on", "x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "drift": rng.choice([-1.0, 1.0])}
                        for d in (-120.0, -60.0, 0.0, 60.0, 120.0)]
        self.shards = []

    def tray_y(self):
        return self.by - self.R - 14

    def on_land(self, k, evs):
        rng = self.rng
        for gl in self.glasses:
            if gl["st"] == "on":
                gl["vl"] = -k * rng.uniform(320, 520)
                out = 1.0 if gl["dx"] > 0 else (-1.0 if gl["dx"] < 0 else gl["drift"])
                gl["drift"] = out
                gl["dx"] += out * k * rng.uniform(16, 36)

    def after(self, dt, evs):
        ty = self.tray_y()
        alive = 0
        for gl in self.glasses:
            if gl["st"] == "on":
                alive += 1
                gl["vl"] += self.g * dt
                gl["lift"] = min(0.0, gl["lift"] + gl["vl"] * dt)
                if gl["lift"] >= 0.0:
                    gl["lift"], gl["vl"] = 0.0, 0.0
                gl["x"], gl["y"] = self.bx + gl["dx"], ty + gl["lift"]
                if abs(gl["dx"]) > self.tray_w / 2 + 8:
                    gl["st"] = "fall"; gl["vx"] = gl["drift"] * 160 + self.vx * 0.5; gl["vy"] = gl["vl"]
            elif gl["st"] == "fall":
                gl["vy"] += self.g * dt
                gl["x"] += gl["vx"] * dt; gl["y"] += gl["vy"] * dt
                if gl["y"] >= FLOOR_Y:
                    gl["st"] = "broken"
                    evs.append(("hit", "glass"))
                    for i in range(10):
                        a = self.rng.uniform(math.pi, 2 * math.pi); sp = self.rng.uniform(150, 460)
                        self.shards.append([gl["x"], FLOOR_Y - 4, math.cos(a) * sp, math.sin(a) * sp])
        for sh in self.shards:
            sh[3] += self.g * dt; sh[0] += sh[2] * dt; sh[1] += sh[3] * dt
            if sh[1] > FLOOR_Y - 2:
                sh[1] = FLOOR_Y - 2; sh[2] *= 0.6; sh[3] = 0.0
        if alive == 0 and not self.payoff:
            self.finish("FIRED")
            self.line("Fired.", "fired", self.t + 0.3)
        self.settle()

    def snapshot(self):
        s = self.base_snap()
        s["glasses"] = [(gl["x"], gl["y"], gl["st"]) for gl in self.glasses]
        s["shards"] = [(sh[0], sh[1]) for sh in self.shards]
        s["tray"] = (self.bx, self.tray_y())
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (36, 30, 44), (58, 40, 36))
        dr.rectangle([0, P(1000), P(self.W), P(FLOOR_Y - 26)], fill=(48, 38, 52))
        for tx in (840, 1060):
            dr.polygon([(P(tx - 170), P(1260)), (P(tx + 170), P(1260)), (P(tx + 200), P(1340)), (P(tx - 200), P(1340))], fill=(220, 210, 200))
            dr.rectangle([P(tx - 170), P(1340), P(tx + 170), P(1450)], fill=(200, 190, 180))
            dr.rectangle([P(tx - 12), P(1450), P(tx + 12), P(FLOOR_Y)], fill=(70, 50, 40))
            circle(dr, P(tx - 50), P(1244), P(12), (240, 200, 120))
            dr.rectangle([P(tx - 55), P(1244), P(tx - 45), P(1262)], fill=(230, 230, 230))
        dr.rectangle([P(100), P(520), P(440), P(960)], fill=(14, 16, 34))
        dr.rectangle([P(266), P(520), P(274), P(960)], fill=(60, 50, 62)); dr.rectangle([P(100), P(736), P(440), P(744)], fill=(60, 50, 62))
        circle(dr, P(360), P(610), P(30), (226, 228, 236))
        for (x, y) in s["shards"]:
            circle(dr, P(x), P(y), P(5), (210, 225, 240))
        self.bounce(dr, P, s)
        tx, ty = s["tray"]
        dr.rectangle([P(tx - self.tray_w / 2), P(ty - 9), P(tx + self.tray_w / 2), P(ty + 9)], fill=(170, 170, 180))
        dr.rectangle([P(tx - self.tray_w / 2), P(ty - 9), P(tx + self.tray_w / 2), P(ty - 4)], fill=(210, 210, 220))
        for (x, y, st) in s["glasses"]:
            if st in ("on", "fall"):
                dr.polygon([(P(x - 20), P(y - 92)), (P(x + 20), P(y - 92)), (P(x + 12), P(y - 40)), (P(x - 12), P(y - 40))], fill=(200, 220, 240))
                dr.rectangle([P(x - 4), P(y - 40), P(x + 4), P(y - 12)], fill=(200, 220, 240))
                dr.rectangle([P(x - 18), P(y - 14), P(x + 18), P(y - 9)], fill=(200, 220, 240))
                dr.polygon([(P(x - 16), P(y - 74)), (P(x + 16), P(y - 74)), (P(x + 11), P(y - 44)), (P(x - 11), P(y - 44))], fill=(170, 60, 90))


# ---------------------------------------------------------------- 3. gardien de musée
class Museum(Chapter):
    title = "WEDNESDAY · NIGHT GUARD"
    stamp = ("FIRED", RED)
    mood = "lose"
    PX, TOP, PW = 780.0, 1060.0, 120.0      # socle : centre, sommet, largeur
    VH, VW = 280.0, 100.0                  # vase : hauteur, largeur de base

    def setup(self):
        self.hop_init(430.0, FLOOR_Y, wobble=60.0, xmin=300, xmax=560, **HOP)
        self.line("Wednesday. Museum night guard.", "title", 0.0)
        self.a = 0.0; self.av = 0.0        # le vase tangue sur sa base
        self.fall = None                   # [x, y, vx, vy, ang, angv]
        self.alarm = None
        self.shards = []

    def on_land(self, k, evs):
        if self.fall is None:
            sign = (1 if self.av >= 0 else -1) if abs(self.av) > 0.1 else self.rng.choice([-1, 1])
            self.av += sign * self.cfg["mus_kick"] * k * self.rng.uniform(0.5, 1.4)

    def after(self, dt, evs):
        if self.fall is None:
            # tangage : rappel tant que le centre de masse est au-dessus de la base, sinon ça part
            crit = math.atan2(self.VW / 2, self.VH / 2)       # ~0.34 rad
            if abs(self.a) < crit:
                self.av += -22.0 * self.a * dt - 0.6 * self.av * dt
            else:
                self.av += 9.0 * math.copysign(1.0, self.a) * dt
            self.a += self.av * dt
            if abs(self.a) > 1.0:
                side = 1 if self.a > 0 else -1
                self.fall = [self.PX + side * self.VW / 2, self.TOP - self.VH / 2, side * 160.0, 40.0, self.a, side * 3.0]
                evs.append(("event", "vase falls t %.2f" % self.t))
        elif self.alarm is None:
            f = self.fall
            f[3] += self.g * dt; f[0] += f[2] * dt; f[1] += f[3] * dt; f[4] += f[5] * dt
            if f[1] + self.VH / 2 >= FLOOR_Y:
                self.alarm = self.t
                evs.append(("hit", "vase"))
                for i in range(16):
                    a = self.rng.uniform(math.pi, 2 * math.pi); sp = self.rng.uniform(150, 520)
                    self.shards.append([f[0], FLOOR_Y - 4, math.cos(a) * sp, math.sin(a) * sp])
                self.finish("FIRED")
                self.line("Fired.", "fired", self.t + 0.5)
        for sh in self.shards:
            sh[3] += self.g * dt; sh[0] += sh[2] * dt; sh[1] += sh[3] * dt
            if sh[1] > FLOOR_Y - 2:
                sh[1] = FLOOR_Y - 2; sh[2] *= 0.6; sh[3] = 0.0
        self.settle()

    def snapshot(self):
        s = self.base_snap()
        s["a"] = self.a; s["fall"] = list(self.fall) if self.fall else None; s["alarm"] = self.alarm
        s["shards"] = [(sh[0], sh[1]) for sh in self.shards]
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        alarm = s["alarm"] is not None and int((t - s["alarm"]) * 4) % 2 == 0
        wall = (58, 54, 64) if not alarm else (100, 44, 52)
        self.room(dr, P, wall, (150, 146, 150))
        for k in range(0, self.W, 180):
            dr.line([(P(k), P(FLOOR_Y)), (P(k + 90), P(self.H))], fill=(130, 126, 132), width=int(P(2)))
        for (x0, y0, w, h, col) in ((90, 560, 300, 360, (40, 90, 140)), (470, 640, 220, 260, (150, 90, 50))):
            dr.rectangle([P(x0 - 16), P(y0 - 16), P(x0 + w + 16), P(y0 + h + 16)], fill=(190, 150, 70))
            dr.rectangle([P(x0), P(y0), P(x0 + w), P(y0 + h)], fill=col)
            circle(dr, P(x0 + w * 0.5), P(y0 + h * 0.45), P(min(w, h) * 0.22), dim(col, 1.6))
        # le projecteur sur le vase
        spot = (255, 240, 200)
        dr.polygon([(P(self.PX - 30), P(430)), (P(self.PX + 30), P(430)), (P(self.PX + 190), P(FLOOR_Y)), (P(self.PX - 190), P(FLOOR_Y))], fill=dim(wall, 1.35) if not alarm else dim(wall, 1.2))
        circle(dr, P(self.PX), P(440), P(26), spot)
        # cordon
        for px in (600, 960):
            dr.rectangle([P(px - 9), P(1300), P(px + 9), P(FLOOR_Y)], fill=(200, 170, 80))
            circle(dr, P(px), P(1296), P(16), (200, 170, 80))
        pts = [(P(600 + 360 * i / 20), P(1310 + 70 * math.sin(math.pi * i / 20))) for i in range(21)]
        dr.line(pts, fill=(170, 40, 60), width=int(P(9)), joint="curve")
        # le socle
        dr.rectangle([P(self.PX - self.PW / 2), P(self.TOP), P(self.PX + self.PW / 2), P(FLOOR_Y)], fill=(206, 202, 206))
        dr.rectangle([P(self.PX - self.PW / 2 - 12), P(self.TOP - 16), P(self.PX + self.PW / 2 + 12), P(self.TOP)], fill=(226, 222, 226))
        # le vase
        if s["alarm"] is None:
            if s["fall"] is None:
                a = s["a"]
                base_y = self.TOP - 16
                ca, sa = math.cos(a), math.sin(a)
                pivot = (self.PX + (self.VW / 2 if a > 0 else -self.VW / 2), base_y)

                def V(x, y):   # repère du vase : origine au pivot, y vers le haut
                    return (P(pivot[0] + x * ca - y * sa), P(pivot[1] - (x * sa + y * ca)))
                off = -self.VW / 2 if a > 0 else self.VW / 2
            else:
                f = s["fall"]; a = f[4]; ca, sa = math.cos(a), math.sin(a)

                def V(x, y):
                    return (P(f[0] + x * ca - y * sa), P(f[1] + self.VH / 2 - (x * sa + y * ca)))
                off = 0.0
            prof = [(-50, 0), (50, 0), (72, 90), (46, 180), (60, 240), (62, 280), (-62, 280), (-60, 240), (-46, 180), (-72, 90)]
            dr.polygon([V(x + off, y) for x, y in prof], fill=(70, 120, 180))
            dr.line([V(-56 + off, 150), V(56 + off, 150)], fill=(230, 200, 110), width=int(P(8)))
            dr.line([V(-60 + off, 265), V(60 + off, 265)], fill=(230, 200, 110), width=int(P(6)))
        for (x, y) in s["shards"]:
            circle(dr, P(x), P(y), P(7), (70, 120, 180))
        if alarm:
            circle(dr, P(1000), P(520), P(28), (255, 60, 60)); circle(dr, P(1000), P(520), P(70), dim((255, 60, 60), 0.35))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. livreur de gâteau
class Cake(Chapter):
    title = "THURSDAY · CAKE DELIVERY"
    stamp = ("FIRED", RED)
    mood = "lose"
    hold_s = 1.0

    def setup(self):
        rng = self.rng
        self.hop_init(360.0, FLOOR_Y, wobble=40.0, xmin=300, xmax=430, **HOP)
        self.line("Thursday. Wedding cake delivery.", "title", 0.0)
        self.cart_x, self.cart_top = 720.0, 1360.0
        self.tiers = [{"w": w, "h": 92, "dx": 0.0, "drift": rng.choice([-1.0, 1.0]), "st": "on", "x": 0, "y": 0, "vx": 0, "vy": 0}
                      for w in (360, 290, 220, 160, 100)]
        self.splats = []
        self.jig = 0.0
        self.boss_x = 1240.0

    def on_land(self, k, evs):
        rng = self.rng
        self.jig = 1.0
        for tr in self.tiers:
            if tr["st"] == "on":
                if rng.random() < 0.2:
                    tr["drift"] = -tr["drift"]
                tr["dx"] += tr["drift"] * k * rng.uniform(6, self.cfg["cake_slide"])

    def after(self, dt, evs):
        self.jig = max(0.0, self.jig - 4 * dt)
        below_w, falling_from = 460.0, None
        for i, tr in enumerate(self.tiers):
            if tr["st"] != "on":
                continue
            if abs(tr["dx"]) > (below_w - tr["w"]) / 2 + 30:
                falling_from = i
                break
            below_w = tr["w"]
        if falling_from is not None:
            y, x = self.cart_top, self.cart_x
            for j, tr in enumerate(self.tiers):
                if tr["st"] == "on":
                    x += tr["dx"]
                    if j >= falling_from:
                        tr["st"] = "fall"; tr["x"] = x; tr["y"] = y; tr["vx"] = tr["drift"] * 140; tr["vy"] = -60
                    y -= tr["h"]
        for tr in self.tiers:
            if tr["st"] == "fall":
                tr["vy"] += self.g * dt; tr["x"] += tr["vx"] * dt; tr["y"] += tr["vy"] * dt
                if tr["y"] >= FLOOR_Y:
                    tr["st"] = "splat"; self.splats.append((tr["x"], tr["w"] * 1.3))
                    evs.append(("hit", "cake"))
                    if not self.payoff:
                        self.finish("FIRED")
                        self.line("Fired.", "fired", self.t + 0.4)
                        self.line("The boss asked if he had anything to say. His answer was one word.", "ask", self.t + 1.6)
                        self.replies.append(("ask", 0.3))
        if self.payoff:
            self.boss_x = max(900.0, self.boss_x - 260 * dt)
        self.settle()

    def snapshot(self):
        s = self.base_snap()
        s["tiers"] = [(tr["st"], tr["dx"], tr["w"], tr["h"], tr["x"], tr["y"]) for tr in self.tiers]
        s["splats"] = list(self.splats); s["jig"] = self.jig; s["boss_x"] = self.boss_x
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (44, 34, 52), (80, 60, 70))
        for i in range(9):
            x = 60 + i * 120; y = 540 + 50 * math.sin(i * 0.9)
            col = [(220, 80, 100), (240, 200, 90), (90, 170, 210)][i % 3]
            dr.polygon([(P(x), P(y)), (P(x + 60), P(y)), (P(x + 30), P(y + 80))], fill=col)
        dr.line([(P(0), P(540)), (P(1080), P(540))], fill=(200, 200, 210), width=int(P(3)))
        jx = 5 * math.sin(t * 45) * s["jig"]
        cx, top = self.cart_x + jx, self.cart_top
        dr.rectangle([P(cx - 230), P(top), P(cx + 230), P(top + 32)], fill=(170, 170, 180))
        for lx in (cx - 200, cx + 200):
            dr.rectangle([P(lx - 9), P(top + 32), P(lx + 9), P(FLOOR_Y - 32)], fill=(120, 120, 130))
            circle(dr, P(lx), P(FLOOR_Y - 28), P(28), (40, 40, 44))
        dr.rectangle([P(cx - 250), P(top - 140), P(cx - 232), P(top + 32)], fill=(120, 120, 130))
        y, x = top, cx
        for (st, dx, w, h, fx, fy) in s["tiers"]:
            if st == "on":
                x += dx
                dr.rectangle([P(x - w / 2), P(y - h), P(x + w / 2), P(y)], fill=(246, 236, 228))
                dr.rectangle([P(x - w / 2), P(y - h), P(x + w / 2), P(y - h + 16)], fill=(230, 150, 170))
                for k in range(int(w // 44)):
                    circle(dr, P(x - w / 2 + 22 + k * 44), P(y - h + 16), P(9), (230, 150, 170))
                y -= h
            elif st == "fall":
                dr.rectangle([P(fx - w / 2), P(fy - h), P(fx + w / 2), P(fy)], fill=(246, 236, 228))
                dr.rectangle([P(fx - w / 2), P(fy - h), P(fx + w / 2), P(fy - h + 16)], fill=(230, 150, 170))
        for (sx, sw) in s["splats"]:
            dr.ellipse([P(sx - sw / 2), P(FLOOR_Y - 28), P(sx + sw / 2), P(FLOOR_Y + 24)], fill=(246, 236, 228))
            dr.ellipse([P(sx - sw / 4), P(FLOOR_Y - 20), P(sx + sw / 4), P(FLOOR_Y + 12)], fill=(230, 150, 170))
        if s["boss_x"] < 1200:
            self.figure(dr, P, s["boss_x"], FLOOR_Y, (60, 64, 90), h=300, w=104)
            dr.polygon([(P(s["boss_x"] - 52), P(FLOOR_Y - 300)), (P(s["boss_x"] + 52), P(FLOOR_Y - 300)), (P(s["boss_x"]), P(FLOOR_Y - 230))], fill=(170, 60, 70))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 5. maître-nageur
class Lifeguard(Chapter):
    title = "FRIDAY · LIFEGUARD"
    stamp = ("FIRED", RED)
    mood = "lose"
    DECK_Y = 1320.0
    SEAT_H = 420.0            # hauteur du siège au-dessus de la plage
    EDGE = 700.0              # bord du bassin

    def setup(self):
        self.cx = 880.0       # centre de la chaise
        self.hop_init(self.cx, self.DECK_Y - self.SEAT_H, wobble=30.0, xmin=self.cx - 40, xmax=self.cx + 40, **dict(HOP, max_h=440.0))
        self.line("Friday. Lifeguard.", "title", 0.0)
        self.ang = 0.0
        self.tipping = False
        self.splash = []
        self.splash_t = None

    def on_land(self, k, evs):
        if not self.tipping:
            step = self.cfg["chair_step"] * k * self.rng.uniform(0.6, 1.3)
            self.cx -= step
            self.xmin, self.xmax = self.cx - 40, self.cx + 40
            self.bx -= step
            if self.cx - 110 < self.EDGE:
                self.tipping = True
                evs.append(("event", "chair over the edge t %.2f" % self.t))

    def seat_pos(self):
        px0, py0 = self.cx + 110, self.DECK_Y        # pivot : le pied droit
        dx, dy = -110.0, -self.SEAT_H
        ca, sa = math.cos(-self.ang), math.sin(-self.ang)
        return px0 + dx * ca - dy * sa, py0 + dx * sa + dy * ca

    def after(self, dt, evs):
        if self.tipping and self.splash_t is None:
            self.ang += (1.2 + 4.0 * self.ang) * dt
            px, py = self.seat_pos()
            self.on = "ride"
            self.bx, self.by = px, py - self.R
            if self.ang >= math.pi / 2 or py > self.DECK_Y + 30:
                self.splash_t = self.t
                self.on = "sunk"
                self.bx, self.by = self.cx - 60, self.DECK_Y + 80
                evs.append(("hit", "splash"))
                for i in range(26):
                    a = self.rng.uniform(math.pi * 1.05, math.pi * 1.95); sp = self.rng.uniform(300, 1000)
                    self.splash.append([self.bx, self.DECK_Y + 20, math.cos(a) * sp, math.sin(a) * sp])
                self.finish("FIRED")
                self.line("Fired.", "fired", self.t + 0.6)
        for sp in self.splash:
            sp[3] += self.g * dt; sp[0] += sp[2] * dt; sp[1] += sp[3] * dt

    def snapshot(self):
        s = self.base_snap()
        s["cx"] = self.cx; s["ang"] = self.ang; s["splash"] = [(p[0], p[1]) for p in self.splash]
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H, DY = self.W, self.H, self.DECK_Y
        dr.rectangle([0, P(430), P(W), P(DY)], fill=(26, 40, 58))
        dr.rectangle([0, P(DY), P(W), P(H)], fill=(190, 196, 204))
        for k in range(0, W, 90):
            dr.line([(P(k), P(DY)), (P(k), P(H))], fill=(160, 168, 180), width=int(P(2)))
        water = (40, 120, 190)
        dr.rectangle([0, P(DY + 20), P(self.EDGE), P(H)], fill=water)
        dr.rectangle([0, P(DY), P(self.EDGE), P(DY + 20)], fill=(120, 170, 210))
        for i in range(6):
            y = DY + 60 + i * 90
            dr.line([(P(20), P(y + 8 * math.sin(t * 2 + i))), (P(self.EDGE - 20), P(y + 8 * math.sin(t * 2 + i + 1)))], fill=(90, 160, 220), width=int(P(3)))
        circle(dr, P(960), P(680), P(70), (230, 70, 60)); circle(dr, P(960), P(680), P(40), (26, 40, 58))
        if s["on"] == "sunk":
            self.bounce(dr, P, s)
            dr.rectangle([0, P(DY + 20), P(self.EDGE), P(DY + 20 + 60)], fill=water)
        # la chaise, pivot au pied droit
        cx, ang = s["cx"], s["ang"]
        px0, py0 = cx + 110, DY
        ca, sa = math.cos(-ang), math.sin(-ang)

        def T(x, y):
            dx, dy = x - px0, y - py0
            return (P(px0 + dx * ca - dy * sa), P(py0 + dx * sa + dy * ca))
        col = (240, 240, 244)
        seat = DY - self.SEAT_H
        for (x0, y0, x1, y1) in ((cx - 110, DY, cx - 70, seat + 12), (cx + 110, DY, cx + 70, seat + 12), (cx - 100, DY - 200, cx + 100, DY - 200)):
            dr.line([T(x0, y0), T(x1, y1)], fill=col, width=int(P(16)))
        dr.polygon([T(cx - 90, seat), T(cx + 90, seat), T(cx + 90, seat + 26), T(cx - 90, seat + 26)], fill=col)
        dr.polygon([T(cx + 70, seat), T(cx + 90, seat), T(cx + 90, seat - 150), T(cx + 70, seat - 150)], fill=col)
        if s["on"] != "sunk":
            self.bounce(dr, P, s)
        for (x, y) in s["splash"]:
            if y < DY + 30:
                circle(dr, P(x), P(y), P(8), (200, 230, 255))


# ---------------------------------------------------------------- 6. testeur de matelas
class Mattress(Chapter):
    title = "SATURDAY · MATTRESS TESTER"
    stamp = ("PERFECT", GREEN)
    mood = "win"
    hold_s = 1.0
    TOP = 1360.0

    def setup(self):
        self.hop_init(430.0, self.TOP, wobble=50.0, xmin=300, xmax=560, **dict(HOP, gain=(1.0, 1.2), max_h=600.0))
        self.line("Saturday. Mattress tester.", "title", 0.0)
        self.nod = 0.0
        self.sink = 0.0

    def on_land(self, k, evs):
        self.nod = 1.0; self.sink = 22 * k
        if self.hits >= self.cfg["mattress_hits"] and not self.payoff:
            self.finish("PERFECT")
            self.line("Perfect.", "perfect", self.t + 0.3)
            self.line("He still works there.", "still", self.t + 1.4)

    def after(self, dt, evs):
        self.nod = max(0.0, self.nod - 2.5 * dt)
        self.sink = max(0.0, self.sink - 100 * dt)

    def snapshot(self):
        s = self.base_snap(); s["nod"] = self.nod; s["sink"] = self.sink
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (38, 44, 50), (70, 72, 78))
        for x in (100, 400):
            dr.rectangle([P(x), P(540), P(x + 240), P(760)], fill=(60, 80, 100))
            dr.line([(P(x + 120), P(540)), (P(x + 120), P(760))], fill=(38, 44, 50), width=int(P(6)))
            dr.line([(P(x), P(650)), (P(x + 240), P(650))], fill=(38, 44, 50), width=int(P(6)))
        for i in range(3):
            dr.rounded_rectangle([P(760), P(1280 - i * 76), P(1070), P(1346 - i * 76)], radius=P(18), fill=(200, 196, 210))
        top = self.TOP
        dr.rectangle([P(170), P(top + 70), P(700), P(FLOOR_Y)], fill=(90, 70, 50))
        pts = []
        for i in range(27):
            x = 170 + (700 - 170) * i / 26
            y = top + s["sink"] * math.exp(-((x - s["bx"]) / 130.0) ** 2)
            pts.append((P(x), P(y)))
        dr.polygon(pts + [(P(700), P(top + 80)), (P(170), P(top + 80))], fill=(236, 232, 240))
        dr.line(pts, fill=(200, 196, 210), width=int(P(4)), joint="curve")
        for k in range(5):
            circle(dr, P(225 + k * 108), P(top + 40), P(6), (200, 196, 210))
        nod = s["nod"]
        self.figure(dr, P, 900, FLOOR_Y, (70, 80, 110), h=300, w=104, tilt=0.4 * nod)
        dr.rectangle([P(810), P(1250 + 10 * nod), P(880), P(1340 + 10 * nod)], fill=(240, 236, 220))
        for k in range(3):
            dr.line([(P(822), P(1272 + k * 20 + 10 * nod)), (P(868), P(1272 + k * 20 + 10 * nod))], fill=(120, 120, 130), width=int(P(3)))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 7. dimanche
class Sunday(Chapter):
    title = "SUNDAY · DAY OFF"
    hold_s = 0.0
    BED = 1330.0

    def setup(self):
        self.hop_init(540.0, self.BED, wobble=40.0, xmin=420, xmax=660, start_air=False, **dict(HOP, start_h=200.0, gain=(1.0, 1.15), max_h=400.0))
        self.line("Sunday. Day off.", "title", 0.0)
        self.line("He did not rest.", "rest", 1.7)
        self.sink = 0.0

    def on_land(self, k, evs):
        self.sink = 18 * k

    def after(self, dt, evs):
        self.sink = max(0.0, self.sink - 80 * dt)
        if self.t >= self.cfg.get("sunday_s", 3.6):
            self.finish("END")

    def snapshot(self):
        s = self.base_snap(); s["sink"] = self.sink
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 26, 44), (46, 36, 40))
        dr.rectangle([P(700), P(560), P(980), P(880)], fill=(10, 12, 28))
        circle(dr, P(900), P(650), P(44), (226, 228, 236)); circle(dr, P(922), P(636), P(40), (10, 12, 28))
        dr.rectangle([P(836), P(560), P(844), P(880)], fill=(60, 50, 70)); dr.rectangle([P(700), P(716), P(980), P(724)], fill=(60, 50, 70))
        top = self.BED
        dr.rectangle([P(150), P(top - 220), P(190), P(top + 120)], fill=(70, 50, 40))
        dr.rectangle([P(160), P(top + 20), P(940), P(FLOOR_Y)], fill=(80, 60, 90))
        pts = []
        for i in range(31):
            x = 160 + (940 - 160) * i / 30
            y = top + s["sink"] * math.exp(-((x - s["bx"]) / 130.0) ** 2)
            pts.append((P(x), P(y)))
        dr.polygon(pts + [(P(940), P(top + 60)), (P(160), P(top + 60))], fill=(210, 206, 226))
        dr.rounded_rectangle([P(190), P(top - 56), P(400), P(top + 10)], radius=P(20), fill=(236, 234, 244))
        dr.rectangle([P(420), P(top + 10), P(940), P(top + 54)], fill=(120, 60, 80))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- l'histoire
DEFAULTS = {
    "ball_r": 68.0, "gravity": 3000.0,
    "lib_lean": 0.055, "lib_arm_s": 9.2, "mus_kick": 1.05, "cake_slide": 15.0, "chair_step": 15.0, "mattress_hits": 6,
    "sunday_s": 4.0, "chapter_max_s": 15.0,
    "counter_font_size": 56, "counter_y": 0.19, "hook_text_s": 5.0,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 0.5, "narr_tail_s": 0.2,
}

CHAPTERS = [(Library, {}), (Waiter, {}), (Museum, {}), (Cake, {}), (Lifeguard, {}), (Mattress, {}), (Sunday, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
