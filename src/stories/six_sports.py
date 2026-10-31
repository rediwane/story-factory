"""
Histoire-liste : les six sports que Bounce a essayés. Six chapitres, un terrain chacun,
une chute physique causée par ses rebonds ; le sixième retourne la série : le
trampoline, où ne jamais s'arrêter est exactement ce qu'on note.

    python3 src/stories/six_sports.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from six_jobs import Chapter, HOP, RED, GREEN, FLOOR_Y

AMBER = (240, 190, 70)


class Sport(Chapter):
    """Chapitre de sport : la foule en haut, le sol en bas."""

    def crowd(self, dr, P, y=560.0, cols=((90, 70, 120), (70, 90, 120), (110, 80, 90), (80, 100, 90), (100, 90, 70), (80, 70, 110))):
        dr.rectangle([0, P(y - 60), P(self.W), P(y + 60)], fill=(30, 28, 44))
        for i in range(11):
            x = 60 + i * 96
            circle(dr, P(x), P(y + 6 * math.sin(self.t * 3 + i)), P(30), cols[i % len(cols)])
        dr.rectangle([0, P(y + 60), P(self.W), P(y + 80)], fill=(60, 56, 80))


# ---------------------------------------------------------------- 1. basket
class Basketball(Sport):
    title = "BASKETBALL"
    stamp = ("OWN BASKET", RED)
    stamp_y = 0.68
    mood = "lose"
    RIM_X, RIM_Y, RIM_R = 230.0, 900.0, 70.0

    def setup(self):
        self.hop_init(760.0, FLOOR_Y, wobble=70.0, xmin=560, xmax=900, **dict(HOP, min_h=260.0, max_h=640.0, gain=(1.04, 1.2)))
        self.line("This is Bounce. He says one word, and he never stops bouncing. This summer, he tried six sports.", "intro", 0.0)
        self.line("Basketball.", "title", 5.9)
        self.armed = False
        self.in_net = None
        self.net_sway = 0.0

    def on_land(self, k, evs):
        if self.t > self.cfg["bb_arm_s"] and self.h > 520 and self.in_net is None:
            # le grand saut part vers son propre panier
            self.armed = True

    def after(self, dt, evs):
        if self.armed and self.on == "air" and self.in_net is None:
            # vise l'anneau : la trajectoire est recalculée au décollage
            T = 2 * abs(self.vy) / self.g
            if T > 0.2:
                self.vx = (self.RIM_X - self.bx) / T
            self.armed = False
            self.aiming = True
        if getattr(self, "aiming", False) and self.in_net is None and self.on == "air":
            if self.vy > 0 and abs(self.bx - self.RIM_X) < self.RIM_R and abs(self.by - self.RIM_Y) < 40:
                self.in_net = self.t
                self.on = "net"
                self.bx, self.by = self.RIM_X, self.RIM_Y + 70
                evs.append(("hit", "net"))
                self.finish("OWN")
                self.line("Three points. For the other team.", "fired", self.t + 0.4)
        if self.in_net is not None:
            age = self.t - self.in_net
            self.by = self.RIM_Y + 70 + 40 * (1 - math.exp(-age * 4))
            self.net_sway = math.exp(-age * 2) * math.sin(age * 12)

    def snapshot(self):
        s = self.base_snap(); s["sway"] = self.net_sway
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (36, 36, 50), (178, 126, 70), skirting=False)
        self.crowd(dr, P)
        for x in range(0, self.W, 120):
            dr.line([(P(x), P(FLOOR_Y)), (P(x), P(self.H))], fill=(150, 104, 56), width=int(P(3)))
        dr.arc([P(-260), P(FLOOR_Y - 60), P(420), P(self.H + 200)], 0, 360, fill=(240, 240, 240), width=int(P(5)))
        # panneau et anneau
        rx, ry = self.RIM_X, self.RIM_Y
        dr.rectangle([P(rx - 150), P(ry - 230), P(rx - 120), P(ry - 60)], fill=(220, 220, 228))
        dr.rectangle([P(rx - 180), P(ry - 260), P(rx - 30), P(ry - 230)], fill=(200, 200, 208))
        dr.rectangle([P(40), P(ry - 260), P(70), P(FLOOR_Y)], fill=(120, 120, 130))
        dr.rectangle([P(40), P(ry - 260), P(rx - 120), P(ry - 240)], fill=(120, 120, 130))
        dr.line([(P(rx - self.RIM_R), P(ry)), (P(rx + self.RIM_R), P(ry))], fill=(230, 90, 60), width=int(P(12)))
        sw = s["sway"] * 20
        for i in range(6):
            x0 = rx - self.RIM_R + i * (2 * self.RIM_R / 5)
            dr.line([(P(x0), P(ry)), (P(rx + (x0 - rx) * 0.5 + sw), P(ry + 120))], fill=(230, 230, 236), width=int(P(3)))
        if s["on"] == "net":
            self.bounce(dr, P, s)
            for i in range(6):
                x0 = rx - self.RIM_R + i * (2 * self.RIM_R / 5)
                dr.line([(P(x0), P(ry)), (P(rx + (x0 - rx) * 0.5 + sw), P(ry + 120))], fill=(230, 230, 236), width=int(P(3)))
        else:
            self.bounce(dr, P, s)


# ---------------------------------------------------------------- 2. golf
class Golf(Sport):
    title = "GOLF"
    stamp = ("WATER", RED)
    mood = "lose"
    HOLE_X, POND_X = 520.0, 760.0

    def setup(self):
        self.hop_init(160.0, FLOOR_Y, wobble=0.0, xmin=0, xmax=2000, **dict(HOP, min_h=200.0, max_h=460.0))
        self.line("Golf.", "title", 0.0)
        self.stride = 60.0
        self.splash = []
        self.splash_t = None

    def hop_go(self):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        self.stride *= self.rng.uniform(1.12, 1.28)
        self.vx = self.stride / T
        self.vy = -s
        self.on = "air"

    def on_land(self, k, evs):
        if abs(self.bx - self.HOLE_X) < 40:
            evs.append(("event", "over the hole t %.2f" % self.t))

    def after(self, dt, evs):
        if self.splash_t is None and self.on == "air" and self.bx > self.POND_X + 20 and self.by > FLOOR_Y - self.R - 10:
            self.splash_t = self.t
            self.on = "sunk"
            self.by = FLOOR_Y + 60
            evs.append(("hit", "splash"))
            for i in range(22):
                a = self.rng.uniform(math.pi * 1.05, math.pi * 1.95); sp = self.rng.uniform(300, 900)
                self.splash.append([self.bx, FLOOR_Y, math.cos(a) * sp, math.sin(a) * sp])
            self.finish("WATER")
            self.line("He cleared the hole. And the green.", "fired", self.t + 0.5)
        if self.on == "air" and self.bx > self.POND_X - 60 and self.vy > 0:
            self.floor_y = FLOOR_Y + 200       # plus de sol : l'étang
        for sp in self.splash:
            sp[3] += self.g * dt; sp[0] += sp[2] * dt; sp[1] += sp[3] * dt

    def snapshot(self):
        s = self.base_snap(); s["splash"] = [(p[0], p[1]) for p in self.splash]
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, P(430), P(W), P(FLOOR_Y)], fill=(12, 16, 36))
        circle(dr, P(200), P(600), P(60), (226, 228, 236)); circle(dr, P(226), P(586), P(54), (12, 16, 36))
        for i in range(24):
            circle(dr, P((i * 7919 + 311) % W), P(460 + (i * 104729 + 97) % 560), P(2), (170, 175, 200))
        dr.rectangle([0, P(1150), P(W), P(FLOOR_Y)], fill=(22, 44, 30))
        for i in range(8):
            dr.polygon([(P(60 + i * 140), P(1150)), (P(90 + i * 140), P(1020)), (P(120 + i * 140), P(1150))], fill=(14, 30, 22))
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(34, 86, 44))
        dr.rectangle([0, P(FLOOR_Y), P(self.POND_X - 60), P(FLOOR_Y + 10)], fill=(50, 110, 56))
        # la lampe du green
        circle(dr, P(self.HOLE_X), P(FLOOR_Y - 20), P(260), (40, 96, 50))
        # l'étang
        water = (18, 50, 96)
        dr.rectangle([P(self.POND_X - 40), P(FLOOR_Y - 4), P(W), P(H)], fill=water)
        dr.ellipse([P(self.POND_X - 60), P(FLOOR_Y - 30), P(self.POND_X + 20), P(FLOOR_Y + 30)], fill=(34, 86, 44))
        dr.rectangle([P(self.POND_X - 40), P(FLOOR_Y - 4), P(W), P(FLOOR_Y + 10)], fill=(40, 80, 130))
        # le trou et le drapeau
        hx = self.HOLE_X
        dr.ellipse([P(hx - 40), P(FLOOR_Y - 12), P(hx + 40), P(FLOOR_Y + 14)], fill=(20, 40, 20))
        dr.rectangle([P(hx - 4), P(FLOOR_Y - 300), P(hx + 4), P(FLOOR_Y)], fill=(230, 230, 230))
        dr.polygon([(P(hx + 4), P(FLOOR_Y - 300)), (P(hx + 110), P(FLOOR_Y - 270)), (P(hx + 4), P(FLOOR_Y - 240))], fill=(230, 60, 60))
        if s["on"] == "sunk":
            self.bounce(dr, P, s)
            dr.rectangle([P(self.POND_X - 40), P(FLOOR_Y - 4), P(W), P(FLOOR_Y + 70)], fill=water)
        else:
            self.bounce(dr, P, s)
        for (x, y) in s["splash"]:
            if y < FLOOR_Y + 10:
                circle(dr, P(x), P(y), P(8), (200, 230, 255))


# ---------------------------------------------------------------- 3. tennis
class Tennis(Sport):
    title = "TENNIS"
    stamp = ("OUT", RED)
    mood = "lose"
    NET_X = 540.0
    LINE_L, LINE_R = 180.0, 900.0

    def setup(self):
        self.hop_init(300.0, FLOOR_Y, wobble=0.0, xmin=0, xmax=2000, **dict(HOP, min_h=240.0, max_h=560.0))
        self.line("Tennis.", "title", 0.0)
        self.dir = 1.0
        self.swing = {"L": 0.0, "R": 0.0}
        self.out = None

    def hop_go(self):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        # il traverse le filet dans un sens, puis dans l'autre, de plus en plus loin
        target = self.rng.uniform(640, 900) if self.bx < self.NET_X else self.rng.uniform(140, 420)
        target += (self.hits * 28) * (1 if target > self.NET_X else -1)
        self.vx = (target - self.bx) / T
        self.vy = -s
        self.on = "air"

    def on_land(self, k, evs):
        side = "R" if self.bx > self.NET_X else "L"
        self.swing[side] = 1.0            # le joueur de ce côté frappe dans le vide
        if (self.bx < self.LINE_L or self.bx > self.LINE_R) and self.out is None:
            self.out = self.t
            self.on = "still"
            self.finish("OUT")
            self.line("Out. Both players missed him anyway.", "fired", self.t + 0.5)
            self.line("The umpire asked for his name.", "ask", self.t + 1.2)
            self.replies.append(("ask", 0.3))

    def after(self, dt, evs):
        for kk in self.swing:
            self.swing[kk] = max(0.0, self.swing[kk] - 3 * dt)

    def snapshot(self):
        s = self.base_snap(); s["swing"] = dict(self.swing)
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        self.room(dr, P, (36, 40, 56), (60, 110, 70), skirting=False)
        self.crowd(dr, P)
        dr.rectangle([0, P(FLOOR_Y), P(W), P(FLOOR_Y + 8)], fill=(90, 150, 100))
        for x in (self.LINE_L, self.LINE_R):
            dr.rectangle([P(x - 5), P(FLOOR_Y), P(x + 5), P(H)], fill=(240, 240, 240))
        # le filet
        dr.rectangle([P(self.NET_X - 6), P(FLOOR_Y - 230), P(self.NET_X + 6), P(FLOOR_Y)], fill=(60, 60, 70))
        for y in range(int(FLOOR_Y - 220), int(FLOOR_Y), 28):
            dr.line([(P(self.NET_X - 60), P(y)), (P(self.NET_X + 60), P(y))], fill=(220, 220, 230), width=int(P(2)))
        dr.rectangle([P(self.NET_X - 60), P(FLOOR_Y - 236), P(self.NET_X + 60), P(FLOOR_Y - 224)], fill=(240, 240, 240))
        # les deux joueurs et leurs raquettes
        for (x, col, side) in ((70, (200, 80, 80), "L"), (1010, (80, 120, 200), "R")):
            self.figure(dr, P, x, FLOOR_Y, col, h=240, w=86)
            sw = s["swing"][side]
            ang = (-1.2 if side == "L" else 1.2) * (1 - sw) + (0.4 if side == "L" else -0.4) * sw
            hx, hy = x + (60 if side == "L" else -60), FLOOR_Y - 200
            ex, ey = hx + math.cos(ang) * 120, hy + math.sin(ang) * 120
            dr.line([(P(hx), P(hy)), (P(ex), P(ey))], fill=(80, 60, 40), width=int(P(10)))
            circle(dr, P(ex), P(ey), P(44), (200, 60, 70)); circle(dr, P(ex), P(ey), P(34), (240, 240, 240))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. saut en hauteur
class HighJump(Sport):
    title = "HIGH JUMP"
    stamp = ("BAR DOWN", RED)
    stamp_y = 0.36
    mood = "lose"
    MAT_X0, MAT_X1, MAT_TOP = 560.0, 1040.0, 1300.0
    BAR_Y = 1000.0

    def setup(self):
        self.hop_init(760.0, self.MAT_TOP, wobble=60.0, xmin=640, xmax=940, **dict(HOP, min_h=240.0, max_h=560.0))
        self.line("High jump.", "title", 0.0)
        self.bar = None       # [x, y, vy, ang]
        self.attempt = 0

    def on_land(self, k, evs):
        self.attempt += 1

    def after(self, dt, evs):
        if self.bar is None and self.on == "air" and self.vy < 0 and self.by - self.R < self.BAR_Y + 10 and abs(self.bx - 800) < 260 and self.attempt >= self.cfg["hj_attempts"]:
            # il monte et prend la barre de dessous
            self.bar = [800.0, self.BAR_Y, -200.0, 0.0]
            self.vy = abs(self.vy) * 0.3
            evs.append(("hit", "bar"))
            self.finish("BAR")
            self.line("The bar was in the way.", "fired", self.t + 0.6)
        if self.bar is not None:
            b = self.bar
            b[2] += self.g * dt; b[1] += b[2] * dt; b[3] = min(0.22, b[3] + 0.9 * dt)
            if b[1] >= self.MAT_TOP - 10:
                b[1] = self.MAT_TOP - 10; b[2] = 0.0; b[3] = 0.0
        self.settle()

    def snapshot(self):
        s = self.base_snap(); s["bar"] = list(self.bar) if self.bar else None
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        self.room(dr, P, (40, 38, 54), (190, 90, 70), skirting=False)
        self.crowd(dr, P)
        for x in range(0, W, 140):
            dr.line([(P(x), P(FLOOR_Y)), (P(x), P(H))], fill=(220, 220, 220), width=int(P(3)))
        # le tapis
        dr.rounded_rectangle([P(self.MAT_X0), P(self.MAT_TOP), P(self.MAT_X1), P(FLOOR_Y)], radius=P(30), fill=(60, 100, 200))
        dr.rounded_rectangle([P(self.MAT_X0 + 20), P(self.MAT_TOP + 20), P(self.MAT_X1 - 20), P(self.MAT_TOP + 60)], radius=P(16), fill=(90, 130, 220))
        # les montants
        for x in (self.MAT_X0 - 40, self.MAT_X1 + 40):
            dr.rectangle([P(x - 12), P(self.BAR_Y - 60), P(x + 12), P(FLOOR_Y)], fill=(230, 230, 236))
            dr.rectangle([P(x - 40), P(FLOOR_Y - 20), P(x + 40), P(FLOOR_Y)], fill=(200, 200, 210))
        if s["bar"] is None:
            dr.line([(P(self.MAT_X0 - 40), P(self.BAR_Y)), (P(self.MAT_X1 + 40), P(self.BAR_Y))], fill=(240, 240, 240), width=int(P(14)))
            for i in range(5):
                x0 = self.MAT_X0 - 40 + i * 110
                dr.line([(P(x0), P(self.BAR_Y)), (P(x0 + 50), P(self.BAR_Y))], fill=(230, 60, 60), width=int(P(14)))
        else:
            bx, by, _, ang = s["bar"]
            ca, sa = math.cos(ang), math.sin(ang)
            L = (self.MAT_X1 - self.MAT_X0 - 20) / 2
            dr.line([(P(bx - L * ca), P(by - L * sa)), (P(bx + L * ca), P(by + L * sa))], fill=(240, 240, 240), width=int(P(14)))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 5. natation
class Swimming(Sport):
    title = "SWIMMING"
    stamp = ("DISQUALIFIED", RED)
    mood = "lose"
    WATER_Y = 1300.0

    def setup(self):
        self.hop_init(120.0, self.WATER_Y, wobble=0.0, xmin=0, xmax=2000, **dict(HOP, min_h=180.0, max_h=360.0, gain=(0.95, 1.1)))
        self.line("Swimming.", "title", 0.0)
        self.stride = 125.0
        self.rings = []
        self.done_x = 850.0

    def hop_go(self):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        self.vx = self.stride * self.rng.uniform(0.9, 1.15) / T
        self.vy = -s
        self.on = "air"

    def on_land(self, k, evs):
        self.rings.append([self.bx, self.t])
        if self.bx >= self.done_x and not self.payoff:
            self.on = "still"
            self.finish("DQ")
            self.line("First to the wall. He never touched the water.", "fired", self.t + 0.5)

    def snapshot(self):
        s = self.base_snap(); s["rings"] = [(r[0], self.t - r[1]) for r in self.rings if self.t - r[1] < 1.2]
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H, WY = self.W, self.H, self.WATER_Y
        dr.rectangle([0, P(430), P(W), P(WY)], fill=(30, 44, 64))
        self.crowd(dr, P)
        dr.rectangle([0, P(WY - 40), P(W), P(WY)], fill=(200, 204, 212))
        water = (40, 120, 190)
        dr.rectangle([0, P(WY), P(W), P(H)], fill=water)
        self.figure(dr, P, 1010, WY - 40, (40, 40, 56), h=220, w=80)
        for i in range(5):
            y = WY + 90 + i * 110
            dr.line([(P(0), P(y)), (P(W), P(y))], fill=(230, 80, 80) if i % 2 else (240, 240, 240), width=int(P(6)))
        for i in range(10):
            y = WY + 50 + i * 70
            dr.line([(P(20), P(y + 6 * math.sin(t * 2 + i))), (P(W - 20), P(y + 6 * math.sin(t * 2 + i + 1)))], fill=(90, 160, 220), width=int(P(2)))
        dr.rectangle([P(self.done_x + 80), P(WY - 60), P(W), P(H)], fill=(190, 194, 204))
        for (x, age) in s["rings"]:
            r = 20 + 160 * age
            dr.ellipse([P(x - r), P(WY - r * 0.25), P(x + r), P(WY + r * 0.25)], outline=(200, 230, 255), width=int(P(3)))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 6. trampoline
class Trampoline(Sport):
    title = "TRAMPOLINE"
    stamp = ("GOLD", AMBER)
    mood = "win"
    hold_s = 2.2
    MAT_Y = 1380.0

    def setup(self):
        self.hop_init(540.0, self.MAT_Y, wobble=30.0, xmin=470, xmax=610, **dict(HOP, start_h=360.0, min_h=360.0, max_h=5000.0, gain=(1.26, 1.34)))
        self.line("Trampoline.", "title", 0.0)
        self.cards = [0, 0, 0]
        self.sink = 0.0
        self.gone = None

    def on_land(self, k, evs):
        self.sink = 60 * min(1.5, k)
        for i in range(3):
            self.cards[i] = min(10, self.cards[i] + self.rng.integers(1, 3))

    def after(self, dt, evs):
        self.sink = max(0.0, self.sink - 240 * dt)
        if self.gone is None and self.on == "air" and self.by < -200 and self.vy < 0:
            self.gone = self.t
            self.on = "gone"
            self.cards = [10, 10, 10]
            evs.append(("event", "out of frame t %.2f" % self.t))
            self.finish("GOLD")
            self.line("Gold.", "perfect", self.t + 0.3)
            self.line("He is still up there.", "still", self.t + 1.6)

    def snapshot(self):
        s = self.base_snap(); s["cards"] = list(self.cards); s["sink"] = self.sink
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        self.room(dr, P, (34, 34, 48), (120, 110, 130), skirting=False)
        self.crowd(dr, P)
        # les juges et leurs cartons
        for i, x in enumerate((760, 880, 1000)):
            self.figure(dr, P, x, FLOOR_Y, (50, 50, 70), h=200, w=70)
            dr.rectangle([P(x - 34), P(FLOOR_Y - 330), P(x + 34), P(FLOOR_Y - 250)], fill=(240, 236, 220))
            f = base.font(int(52 * S))
            dr.text((P(x), P(FLOOR_Y - 290)), str(s["cards"][i]), fill=(30, 30, 40), anchor="mm", font=f)
        # le trampoline
        my = self.MAT_Y
        for x in (150, 450):
            dr.rectangle([P(x), P(my + 10), P(x + 16), P(FLOOR_Y)], fill=(120, 120, 130))
        dr.rectangle([P(130), P(my - 8), P(630), P(my + 10)], fill=(60, 60, 200))
        pts = []
        for i in range(27):
            x = 150 + 460 * i / 26
            y = my + s["sink"] * math.exp(-((x - s["bx"]) / 140.0) ** 2)
            pts.append((P(x), P(y)))
        dr.line(pts, fill=(30, 30, 40), width=int(P(10)), joint="curve")
        for i in range(0, 27, 2):
            dr.line([(P(150 + 460 * i / 26), P(my - 6)), pts[i]], fill=(200, 200, 210), width=int(P(3)))
        if s["on"] != "gone":
            self.bounce(dr, P, s)


DEFAULTS = {
    "ball_r": 68.0, "gravity": 3000.0,
    "bb_arm_s": 9.5, "hj_attempts": 5,
    "chapter_max_s": 15.0,
    "counter_font_size": 56, "counter_y": 0.19, "hook_text_s": 5.0,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.0, "narr_tail_s": 0.2,
}

CHAPTERS = [(Basketball, {}), (Golf, {}), (Tennis, {}), (HighJump, {}), (Swimming, {}), (Trampoline, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
