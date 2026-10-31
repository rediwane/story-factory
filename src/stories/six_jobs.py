"""
Histoire-liste : les six métiers que Bounce a essayés en une semaine. Six chapitres
de huit à dix secondes, chacun un lieu, une mise en place instantanée et une chute
physique ; le narrateur enchaîne ; le sixième retourne la série : le seul métier où
rebondir sans arrêt est exactement ce qu'on attend de lui.

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
INK = (16, 14, 20)
FLOOR_Y = 1500.0


class Chapter(Hopper):
    title = None
    stamp = None
    mood = None
    hold_s = 2.0

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

    def base_snap(self):
        return {"t": self.t, "bx": self.bx, "by": self.by, "end": self.end_t, "hit_t": self.hit_t}

    # --- décor commun
    def figure(self, dr, P, x, y_floor, col, h=230, w=86, hat=False, tilt=0.0):
        """Un personnage sans visage : tronc, tête, deux jambes. (x, y_floor) = pieds."""
        dr.rectangle([P(x - w / 2), P(y_floor - h), P(x + w / 2), P(y_floor - 10)], fill=col)
        dr.rectangle([P(x - w / 2), P(y_floor - 10), P(x - 8), P(y_floor)], fill=dim(col, 0.7))
        dr.rectangle([P(x + 8), P(y_floor - 10), P(x + w / 2), P(y_floor)], fill=dim(col, 0.7))
        circle(dr, P(x + tilt * 20), P(y_floor - h - 42), P(38), col)
        if hat:
            dr.rectangle([P(x - 48 + tilt * 20), P(y_floor - h - 84), P(x + 48 + tilt * 20), P(y_floor - h - 72)], fill=dim(col, 0.6))
            dr.rectangle([P(x - 30 + tilt * 20), P(y_floor - h - 112), P(x + 30 + tilt * 20), P(y_floor - h - 80)], fill=dim(col, 0.6))

    def room(self, dr, P, wall, floor, top=430.0, floor_y=FLOOR_Y, skirting=True):
        W, H = self.W, self.H
        dr.rectangle([0, P(top), P(W), P(floor_y)], fill=wall)
        dr.rectangle([0, P(floor_y), P(W), P(H)], fill=floor)
        if skirting:
            dr.rectangle([0, P(floor_y - 26), P(W), P(floor_y)], fill=dim(wall, 0.75))
        dr.rectangle([0, P(floor_y), P(W), P(floor_y + 8)], fill=dim(floor, 1.35))


# ---------------------------------------------------------------- 0. présentation
class Intro(Chapter):
    hold_s = 0.0

    def setup(self):
        self.hop_init(540.0, FLOOR_Y, start_h=200.0, max_h=300.0, wobble=40.0)
        self.line("This is Bounce. He says one word, and he never stops bouncing. Last week, he tried six jobs.", "intro", 0.0)

    def after(self, dt, evs):
        if self.t >= self.cfg.get("intro_s", 6.2):
            self.finish("INTRO")

    def snapshot(self):
        return self.base_snap()

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (26, 24, 36), (44, 40, 56), skirting=False)
        for k in range(3, 0, -1):
            circle(dr, P(540), P(FLOOR_Y), P(120 + 60 * k), dim((70, 60, 100), 0.5 + 0.12 * (3 - k)))
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 1. bibliothécaire
class Library(Chapter):
    title = "MONDAY · LIBRARIAN"
    stamp = ("FIRED", RED)
    mood = "lose"

    def setup(self):
        c, rng = self.cfg, self.rng
        self.hop_init(380.0, FLOOR_Y, start_h=160.0, max_h=330.0, wobble=50.0, xmin=300, xmax=470)
        self.line("Monday. Librarian.", "title", 0.0)
        pal = [(170, 60, 60), (60, 110, 160), (200, 160, 70), (80, 140, 90), (150, 90, 160), (210, 120, 80), (90, 90, 120)]
        self.shelves = [760.0, 940.0, 1120.0, 1300.0]
        self.books = []
        for sy in self.shelves:
            x = 640.0
            while x < 1000:
                w = rng.uniform(34, 54); h = rng.uniform(108, 150)
                self.books.append({"x": x + w / 2, "y": sy, "w": w, "h": h, "col": pal[rng.integers(len(pal))],
                                   "lean": 0.0, "st": "up", "vx": 0.0, "vy": 0.0, "ang": 0.0, "px": x + w / 2, "py": sy})
                x += w + 4
        self.shake = 0.0

    def on_land(self, k, evs):
        rng = self.rng
        self.shake = 1.0
        for b in self.books:
            if b["st"] == "up" and rng.random() < 0.55:
                b["lean"] += self.cfg["lib_lean"] * k * rng.uniform(0.3, 1.2) * (1.0 + 0.4 * (b["y"] < 1000))
                if b["lean"] > 0.42:
                    b["st"], b["vx"], b["vy"] = "fall", -rng.uniform(80, 200), -rng.uniform(0, 120)
                    evs.append(("event", "book falls t %.2f" % self.t))

    def after(self, dt, evs):
        self.shake = max(0.0, self.shake - 4 * dt)
        n_down = 0
        for b in self.books:
            if b["st"] == "fall":
                b["vy"] += self.g * 0.8 * dt
                b["px"] += b["vx"] * dt
                b["py"] += b["vy"] * dt
                b["ang"] = min(math.pi / 2, b["ang"] + 3.2 * dt)
                if b["py"] >= FLOOR_Y:
                    b["py"] = FLOOR_Y; b["st"] = "down"; b["ang"] = math.pi / 2
                    if self.t - self.last_hit > 0.1:
                        evs.append(("hit", "book"))
            if b["st"] == "down":
                n_down += 1
        if not self.payoff and n_down >= int(0.6 * len(self.books)):
            self.finish("FIRED")
            self.line("Fired.", "fired")
        if self.payoff and self.t - self.end_t > 0.2:
            self.on = "ground"; self.vy = 0.0; self.by = FLOOR_Y - self.R
            if self.t - self.end_t > 0.25:
                self.on = "still"

    def snapshot(self):
        s = self.base_snap()
        s["books"] = [(b["px"], b["py"], b["w"], b["h"], b["col"], b["lean"], b["st"], b["ang"]) for b in self.books]
        s["shake"] = self.shake
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (52, 40, 34), (70, 52, 38))
        # le bureau et la bibliothécaire
        dr.rectangle([P(80), P(1360), P(300), P(FLOOR_Y)], fill=(74, 50, 36))
        dr.rectangle([P(70), P(1350), P(310), P(1366)], fill=(96, 66, 46))
        self.figure(dr, P, 190, 1360, (60, 70, 96), h=170, w=70)
        circle(dr, P(260), P(1300), P(34), (60, 140, 90))
        dr.rectangle([P(256), P(1300), P(264), P(1350)], fill=(200, 170, 90))
        # l'étagère
        sx = 6 * math.sin(t * 40) * s["shake"]
        dr.rectangle([P(610 + sx), P(560), P(1020 + sx), P(FLOOR_Y)], fill=(40, 28, 22))
        for sy in [760.0, 940.0, 1120.0, 1300.0]:
            dr.rectangle([P(610 + sx), P(sy), P(1020 + sx), P(sy + 16)], fill=(90, 62, 44))
        dr.rectangle([P(610 + sx), P(560), P(1020 + sx), P(580)], fill=(90, 62, 44))
        for (px, py, w, h, col, lean, st, ang) in s["books"]:
            if st == "up":
                a = lean
                ca, sa = math.cos(a), math.sin(a)
                bx0 = px + sx
                pts = [(bx0 - w / 2, py), (bx0 + w / 2, py), (bx0 + w / 2 - h * sa, py - h * ca), (bx0 - w / 2 - h * sa, py - h * ca)]
                dr.polygon([(P(x), P(y)) for x, y in pts], fill=col)
                dr.line([(P(bx0 - w / 2 + 6 - h * sa * 0.5), P(py - h * 0.5 * ca)), (P(bx0 + w / 2 - 6 - h * sa * 0.5), P(py - h * 0.5 * ca))], fill=dim(col, 0.6), width=int(P(3)))
            else:
                ca, sa = math.cos(ang), math.sin(ang)
                cx, cy = px, py - (h / 2 if st == "fall" else w / 2)
                pts = [(-w / 2, h / 2), (w / 2, h / 2), (w / 2, -h / 2), (-w / 2, -h / 2)]
                pts = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]
                dr.polygon([(P(x), P(y)) for x, y in pts], fill=col)
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 2. serveur
class Waiter(Chapter):
    title = "TUESDAY · WAITER"
    stamp = ("FIRED", RED)
    mood = "lose"

    def setup(self):
        rng = self.rng
        self.hop_init(420.0, FLOOR_Y, start_h=130.0, max_h=260.0, wobble=70.0, xmin=260, xmax=620)
        self.line("Tuesday. Waiter.", "title", 0.0)
        self.tray_w = 260.0
        self.glasses = [{"dx": d, "lift": 0.0, "vl": 0.0, "st": "on", "x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "drift": rng.choice([-1.0, 1.0])}
                        for d in (-96.0, -48.0, 0.0, 48.0, 96.0)]
        self.shards = []

    def tray_y(self):
        return self.by - self.R - 12

    def on_land(self, k, evs):
        rng = self.rng
        for gl in self.glasses:
            if gl["st"] == "on":
                gl["vl"] = -k * rng.uniform(260, 460)
                gl["drift"] = gl["drift"] if rng.random() < 0.88 else -gl["drift"]
                gl["dx"] += gl["drift"] * k * rng.uniform(18, 44)

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
                if abs(gl["dx"]) > self.tray_w / 2 + 6:
                    gl["st"] = "fall"; gl["vx"] = gl["drift"] * 140 + self.vx * 0.5; gl["vy"] = gl["vl"]
            elif gl["st"] == "fall":
                gl["vy"] += self.g * dt
                gl["x"] += gl["vx"] * dt; gl["y"] += gl["vy"] * dt
                if gl["y"] >= FLOOR_Y:
                    gl["st"] = "broken"
                    evs.append(("hit", "glass"))
                    for i in range(9):
                        a = self.rng.uniform(math.pi, 2 * math.pi)
                        sp = self.rng.uniform(150, 420)
                        self.shards.append([gl["x"], FLOOR_Y - 4, math.cos(a) * sp, math.sin(a) * sp, self.t])
        for sh in self.shards:
            sh[3] += self.g * dt
            sh[0] += sh[2] * dt; sh[1] += sh[3] * dt
            if sh[1] > FLOOR_Y - 2:
                sh[1] = FLOOR_Y - 2; sh[2] *= 0.6; sh[3] = 0.0
        if alive == 0 and not self.payoff:
            self.finish("FIRED")
            self.line("Fired.", "fired")
        if self.payoff and self.t - self.end_t > 0.3 and self.on == "air" and self.vy > 0 and self.by >= FLOOR_Y - self.R - 2:
            self.on = "still"; self.by = FLOOR_Y - self.R

    def snapshot(self):
        s = self.base_snap()
        s["glasses"] = [(gl["x"], gl["y"], gl["st"]) for gl in self.glasses]
        s["shards"] = [(sh[0], sh[1]) for sh in self.shards]
        s["tray"] = (self.bx, self.tray_y())
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (36, 30, 44), (58, 40, 36))
        dr.rectangle([0, P(1100), P(self.W), P(FLOOR_Y - 26)], fill=(48, 38, 52))
        # tables
        for tx in (820, 1040):
            dr.polygon([(P(tx - 150), P(1310)), (P(tx + 150), P(1310)), (P(tx + 180), P(1380)), (P(tx - 180), P(1380))], fill=(220, 210, 200))
            dr.rectangle([P(tx - 150), P(1380), P(tx + 150), P(1470)], fill=(200, 190, 180))
            dr.rectangle([P(tx - 10), P(1470), P(tx + 10), P(FLOOR_Y)], fill=(70, 50, 40))
            circle(dr, P(tx - 40), P(1296), P(10), (240, 200, 120))
            dr.rectangle([P(tx - 44), P(1296), P(tx - 36), P(1312)], fill=(230, 230, 230))
        # la fenêtre
        dr.rectangle([P(120), P(560), P(420), P(1000)], fill=(14, 16, 34))
        dr.rectangle([P(266), P(560), P(274), P(1000)], fill=(60, 50, 62))
        dr.rectangle([P(120), P(776), P(420), P(784)], fill=(60, 50, 62))
        circle(dr, P(340), P(640), P(26), (226, 228, 236))
        # éclats
        for (x, y) in s["shards"]:
            circle(dr, P(x), P(y), P(4), (210, 225, 240))
        # Bounce, le plateau, les verres
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))
        tx, ty = s["tray"]
        if not s.get("end") or True:
            dr.rectangle([P(tx - self.tray_w / 2), P(ty - 8), P(tx + self.tray_w / 2), P(ty + 8)], fill=(170, 170, 180))
            dr.rectangle([P(tx - self.tray_w / 2), P(ty - 8), P(tx + self.tray_w / 2), P(ty - 4)], fill=(210, 210, 220))
        for (x, y, st) in s["glasses"]:
            if st in ("on", "fall"):
                dr.polygon([(P(x - 16), P(y - 70)), (P(x + 16), P(y - 70)), (P(x + 10), P(y - 30)), (P(x - 10), P(y - 30))], fill=(200, 220, 240))
                dr.rectangle([P(x - 3), P(y - 30), P(x + 3), P(y - 10)], fill=(200, 220, 240))
                dr.rectangle([P(x - 14), P(y - 12), P(x + 14), P(y - 8)], fill=(200, 220, 240))
                dr.polygon([(P(x - 13), P(y - 56)), (P(x + 13), P(y - 56)), (P(x + 9), P(y - 34)), (P(x - 9), P(y - 34))], fill=(170, 60, 90))


# ---------------------------------------------------------------- 3. gardien de musée
class Museum(Chapter):
    title = "WEDNESDAY · NIGHT GUARD"
    stamp = ("FIRED", RED)
    mood = "lose"

    def setup(self):
        self.hop_init(420.0, FLOOR_Y, start_h=150.0, max_h=320.0, wobble=50.0, xmin=320, xmax=520)
        self.line("Wednesday. Night guard.", "title", 0.0)
        self.phi = 0.0; self.omega = 0.0
        self.vase = None          # [x, y, vx, vy, ang, w]
        self.alarm = None
        self.shards = []

    def on_land(self, k, evs):
        if self.vase is None:
            sign = (1 if self.omega >= 0 else -1) if abs(self.omega) > 0.05 else self.rng.choice([-1, 1])
            self.omega += sign * self.cfg["mus_kick"] * k * self.rng.uniform(0.5, 1.4)

    def after(self, dt, evs):
        c = self.cfg
        if self.vase is None:
            self.omega += -14.0 * self.phi * dt - 1.2 * self.omega * dt
            self.phi += self.omega * dt
            if abs(self.phi) * 2.4 > 0.5:
                side = 1 if self.phi > 0 else -1
                self.vase = [720.0 + side * 30, 1200.0 - 80, side * 90.0, -40.0, self.phi * 2.4, 0.0]
                evs.append(("event", "vase tips t %.2f" % self.t))
        elif self.alarm is None:
            v = self.vase
            v[3] += self.g * dt; v[0] += v[2] * dt; v[1] += v[3] * dt; v[4] += (1 if v[2] > 0 else -1) * 2.5 * dt
            if v[1] + 80 >= FLOOR_Y:
                self.alarm = self.t
                evs.append(("hit", "vase"))
                for i in range(14):
                    a = self.rng.uniform(math.pi, 2 * math.pi); sp = self.rng.uniform(150, 480)
                    self.shards.append([v[0], FLOOR_Y - 4, math.cos(a) * sp, math.sin(a) * sp])
                self.finish("FIRED")
                self.line("Fired.", "fired", self.t + 0.9)
        for sh in self.shards:
            sh[3] += self.g * dt; sh[0] += sh[2] * dt; sh[1] += sh[3] * dt
            if sh[1] > FLOOR_Y - 2:
                sh[1] = FLOOR_Y - 2; sh[2] *= 0.6; sh[3] = 0.0
        if self.payoff and self.on == "air" and self.vy > 0 and self.by >= FLOOR_Y - self.R - 2:
            self.on = "still"; self.by = FLOOR_Y - self.R

    def snapshot(self):
        s = self.base_snap()
        s["phi"] = self.phi; s["vase"] = list(self.vase) if self.vase else None; s["alarm"] = self.alarm
        s["shards"] = [(sh[0], sh[1]) for sh in self.shards]
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        alarm = s["alarm"] is not None and int((t - s["alarm"]) * 4) % 2 == 0
        wall = (60, 56, 66) if not alarm else (96, 44, 52)
        self.room(dr, P, wall, (150, 146, 150))
        for k in range(0, self.W, 180):
            dr.line([(P(k), P(FLOOR_Y)), (P(k + 90), P(self.H))], fill=(130, 126, 132), width=int(P(2)))
        # tableaux
        for (x0, y0, w, h, col) in ((120, 620, 260, 320, (40, 90, 140)), (470, 700, 200, 240, (150, 90, 50)), (820, 600, 220, 300, (110, 60, 120))):
            dr.rectangle([P(x0 - 14), P(y0 - 14), P(x0 + w + 14), P(y0 + h + 14)], fill=(190, 150, 70))
            dr.rectangle([P(x0), P(y0), P(x0 + w), P(y0 + h)], fill=col)
            circle(dr, P(x0 + w * 0.5), P(y0 + h * 0.45), P(min(w, h) * 0.2), dim(col, 1.6))
        # cordon
        for px in (560, 900):
            dr.rectangle([P(px - 8), P(1340), P(px + 8), P(FLOOR_Y)], fill=(200, 170, 80))
            circle(dr, P(px), P(1336), P(14), (200, 170, 80))
        pts = [(P(560 + (900 - 560) * i / 20), P(1350 + 60 * math.sin(math.pi * i / 20))) for i in range(21)]
        dr.line(pts, fill=(170, 40, 60), width=int(P(8)), joint="curve")
        # socle et vase
        phi = s["phi"]
        bx0, top = 720.0, 1200.0
        pts = [(-45, 0), (45, 0), (45 + phi * 300, -(FLOOR_Y - top)), (-45 + phi * 300, -(FLOOR_Y - top))]
        dr.polygon([(P(bx0 + x), P(FLOOR_Y + y)) for x, y in pts], fill=(200, 196, 200))
        if s["vase"] is None:
            vx, vy, ang = bx0 + phi * 300, top, phi * 2.4
        else:
            vx, vy, ang = s["vase"][0], s["vase"][1] + 80, s["vase"][4]
        if s["alarm"] is None:
            ca, sa = math.cos(ang), math.sin(ang)
            prof = [(-30, 0), (30, 0), (46, -60), (28, -120), (40, -160), (-40, -160), (-28, -120), (-46, -60)]
            dr.polygon([(P(vx + x * ca - y * sa), P(vy + x * sa + y * ca)) for x, y in prof], fill=(70, 120, 170))
            dr.line([(P(vx + (-40) * ca - (-90) * sa), P(vy + (-40) * sa + (-90) * ca)), (P(vx + 40 * ca - (-90) * sa), P(vy + 40 * sa + (-90) * ca))], fill=(220, 200, 120), width=int(P(6)))
        for (x, y) in s["shards"]:
            circle(dr, P(x), P(y), P(6), (70, 120, 170))
        if alarm:
            circle(dr, P(1000), P(520), P(26), (255, 60, 60))
            circle(dr, P(1000), P(520), P(60), dim((255, 60, 60), 0.35))
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 4. livreur de gâteau
class Cake(Chapter):
    title = "THURSDAY · CAKE DELIVERY"
    stamp = ("FIRED", RED)
    mood = "lose"
    hold_s = 4.2

    def setup(self):
        rng = self.rng
        self.hop_init(380.0, FLOOR_Y, start_h=150.0, max_h=320.0, wobble=40.0, xmin=320, xmax=440)
        self.line("Thursday. Wedding cake delivery.", "title", 0.0)
        self.cart_x = 700.0
        self.cart_top = 1380.0
        self.tiers = [{"w": 320, "h": 80, "dx": 0.0, "drift": rng.choice([-1.0, 1.0]), "st": "on", "x": 0, "y": 0, "vx": 0, "vy": 0}
                      for _ in range(4)]
        for i, w in enumerate((320, 240, 170, 110)):
            self.tiers[i]["w"] = w
        self.splats = []
        self.jig = 0.0

    def on_land(self, k, evs):
        rng = self.rng
        self.jig = 1.0
        for tr in self.tiers:
            if tr["st"] == "on":
                if rng.random() < 0.25:
                    tr["drift"] = -tr["drift"]
                tr["dx"] += tr["drift"] * k * rng.uniform(4, self.cfg["cake_slide"])

    def after(self, dt, evs):
        self.jig = max(0.0, self.jig - 4 * dt)
        # un étage qui dépasse trop celui du dessous tombe, et emporte ceux du dessus
        below_w = 420.0
        acc = 0.0
        falling_from = None
        for i, tr in enumerate(self.tiers):
            if tr["st"] != "on":
                continue
            lim = (below_w - tr["w"]) / 2 + 26
            if abs(tr["dx"]) > lim:
                falling_from = i
                break
            below_w = tr["w"]
        if falling_from is not None:
            y = self.cart_top
            x = self.cart_x
            for j, tr in enumerate(self.tiers):
                if tr["st"] == "on":
                    x += tr["dx"]
                    if j >= falling_from:
                        tr["st"] = "fall"; tr["x"] = x; tr["y"] = y; tr["vx"] = tr["drift"] * 120; tr["vy"] = -60
                    y -= tr["h"]
        for tr in self.tiers:
            if tr["st"] == "fall":
                tr["vy"] += self.g * dt; tr["x"] += tr["vx"] * dt; tr["y"] += tr["vy"] * dt
                if tr["y"] >= FLOOR_Y:
                    tr["st"] = "splat"; self.splats.append((tr["x"], tr["w"] * 1.3))
                    evs.append(("hit", "cake"))
                    if not self.payoff:
                        self.finish("FIRED")
                        self.line("Fired.", "fired", self.t + 0.8)
                        self.line("The boss asked if he had anything to say.", "ask", self.t + 1.8)
                        self.replies.append(("ask", 0.35))
        if self.payoff and self.on == "air" and self.vy > 0 and self.by >= FLOOR_Y - self.R - 2:
            self.on = "still"; self.by = FLOOR_Y - self.R

    def snapshot(self):
        s = self.base_snap()
        s["tiers"] = [(tr["st"], tr["dx"], tr["w"], tr["h"], tr["x"], tr["y"]) for tr in self.tiers]
        s["splats"] = list(self.splats); s["jig"] = self.jig
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (44, 34, 52), (80, 60, 70))
        # fanions
        for i in range(9):
            x = 60 + i * 120
            y = 560 + 50 * math.sin(i * 0.9)
            col = [(220, 80, 100), (240, 200, 90), (90, 170, 210)][i % 3]
            dr.polygon([(P(x), P(y)), (P(x + 60), P(y)), (P(x + 30), P(y + 70))], fill=col)
        dr.line([(P(0), P(560)), (P(1080), P(560))], fill=(200, 200, 210), width=int(P(3)))
        # table du fond
        dr.rectangle([P(700), P(1180), P(1080), P(1210)], fill=(230, 226, 230))
        dr.rectangle([P(700), P(1210), P(1080), P(1300)], fill=(210, 204, 214))
        # le chariot
        jx = 5 * math.sin(t * 45) * s["jig"]
        cx, top = self.cart_x + jx, self.cart_top
        dr.rectangle([P(cx - 210), P(top), P(cx + 210), P(top + 30)], fill=(170, 170, 180))
        for lx in (cx - 180, cx + 180):
            dr.rectangle([P(lx - 8), P(top + 30), P(lx + 8), P(FLOOR_Y - 30)], fill=(120, 120, 130))
            circle(dr, P(lx), P(FLOOR_Y - 26), P(26), (40, 40, 44))
        dr.rectangle([P(cx - 230), P(top - 120), P(cx - 214), P(top + 30)], fill=(120, 120, 130))
        # le gâteau
        y = top
        x = cx
        for (st, dx, w, h, fx, fy) in s["tiers"]:
            if st == "on":
                x += dx
                dr.rectangle([P(x - w / 2), P(y - h), P(x + w / 2), P(y)], fill=(246, 236, 228))
                dr.rectangle([P(x - w / 2), P(y - h), P(x + w / 2), P(y - h + 14)], fill=(230, 150, 170))
                for k in range(int(w // 40)):
                    circle(dr, P(x - w / 2 + 20 + k * 40), P(y - h + 14), P(8), (230, 150, 170))
                y -= h
            elif st == "fall":
                dr.rectangle([P(fx - w / 2), P(fy - h), P(fx + w / 2), P(fy)], fill=(246, 236, 228))
                dr.rectangle([P(fx - w / 2), P(fy - h), P(fx + w / 2), P(fy - h + 14)], fill=(230, 150, 170))
        for (sx, sw) in s["splats"]:
            dr.ellipse([P(sx - sw / 2), P(FLOOR_Y - 26), P(sx + sw / 2), P(FLOOR_Y + 22)], fill=(246, 236, 228))
            dr.ellipse([P(sx - sw / 4), P(FLOOR_Y - 18), P(sx + sw / 4), P(FLOOR_Y + 10)], fill=(230, 150, 170))
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 5. maître-nageur
class Lifeguard(Chapter):
    title = "FRIDAY · LIFEGUARD"
    stamp = ("FIRED", RED)
    mood = "lose"
    DECK_Y = 1320.0
    SEAT_Y = 960.0

    def setup(self):
        self.hop_init(820.0, self.SEAT_Y, start_h=150.0, max_h=300.0, wobble=30.0, xmin=790, xmax=850)
        self.line("Friday. Lifeguard.", "title", 0.0)
        self.lean = 0.0; self.lean_v = 0.0
        self.fall = None      # angle de chute de la chaise
        self.splash = []
        self.splash_t = None

    def on_land(self, k, evs):
        if self.fall is None:
            self.lean += self.cfg["chair_kick"] * k * self.rng.uniform(0.4, 1.3)
            self.lean_v = 0.0

    def after(self, dt, evs):
        if self.fall is None:
            self.lean = max(0.0, self.lean - 0.08 * self.lean * dt)
            if self.lean > 0.5:
                self.fall = self.lean
                evs.append(("event", "chair tips t %.2f" % self.t))
        elif self.splash_t is None:
            self.fall += (3.0 + 2.0 * self.fall) * dt
            # Bounce suit le siège
            ang = self.fall
            px, py = self.seat_pos(ang)
            if self.on == "air":
                self.on = "ride"
            self.bx, self.by = px, py - self.R
            if self.fall >= math.pi / 2 - 0.05 or py > self.DECK_Y + 40:
                self.splash_t = self.t
                self.on = "sunk"
                self.bx, self.by = 560.0, self.DECK_Y + 70
                evs.append(("hit", "splash"))
                for i in range(22):
                    a = self.rng.uniform(math.pi * 1.05, math.pi * 1.95); sp = self.rng.uniform(300, 900)
                    self.splash.append([560.0, self.DECK_Y + 20, math.cos(a) * sp, math.sin(a) * sp])
                self.finish("FIRED")
                self.line("Fired.", "fired", self.t + 0.9)
        for sp in self.splash:
            sp[3] += self.g * dt; sp[0] += sp[2] * dt; sp[1] += sp[3] * dt

    def seat_pos(self, ang):
        # la chaise pivote autour de son pied gauche (côté bassin) : (720, DECK_Y)
        px0, py0 = 720.0, self.DECK_Y
        dx, dy = 820.0 - px0, self.SEAT_Y - py0
        ca, sa = math.cos(-ang), math.sin(-ang)
        return px0 + dx * ca - dy * sa, py0 + dx * sa + dy * ca

    def snapshot(self):
        s = self.base_snap()
        s["ang"] = self.fall if self.fall is not None else self.lean
        s["on"] = self.on; s["splash"] = [(p[0], p[1]) for p in self.splash]; s["splash_t"] = self.splash_t
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        DY = self.DECK_Y
        dr.rectangle([0, P(430), P(W), P(DY)], fill=(26, 40, 58))
        dr.rectangle([0, P(DY), P(W), P(H)], fill=(190, 196, 204))
        for k in range(0, W, 90):
            dr.line([(P(k), P(DY)), (P(k), P(H))], fill=(160, 168, 180), width=int(P(2)))
        # bassin
        water = (40, 120, 190)
        dr.rectangle([0, P(DY + 20), P(700), P(H)], fill=water)
        dr.rectangle([0, P(DY), P(700), P(DY + 20)], fill=(120, 170, 210))
        for i in range(6):
            y = DY + 60 + i * 90
            dr.line([(P(20), P(y + 8 * math.sin(t * 2 + i))), (P(680), P(y + 8 * math.sin(t * 2 + i + 1)))], fill=(90, 160, 220), width=int(P(3)))
        dr.rectangle([P(690), P(DY - 60), P(700), P(DY + 20)], fill=(210, 210, 220))
        dr.rectangle([P(730), P(DY - 60), P(740), P(DY + 20)], fill=(210, 210, 220))
        # bouée au mur
        circle(dr, P(960), P(700), P(60), (230, 70, 60)); circle(dr, P(960), P(700), P(34), (26, 40, 58))
        # Bounce dans l'eau : dessiné avant l'eau de surface
        if s["on"] == "sunk":
            base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))
            dr.rectangle([0, P(DY + 20), P(700), P(DY + 20 + 50)], fill=water)
        # la chaise
        ang = s["ang"]
        px0, py0 = 720.0, DY
        ca, sa = math.cos(-ang), math.sin(-ang)

        def T(x, y):
            dx, dy = x - px0, y - py0
            return (P(px0 + dx * ca - dy * sa), P(py0 + dx * sa + dy * ca))
        col = (240, 240, 244)
        for (x0, y0, x1, y1) in ((720, DY, 760, self.SEAT_Y + 10), (920, DY, 880, self.SEAT_Y + 10), (720, DY - 180, 920, DY - 180)):
            dr.line([T(x0, y0), T(x1, y1)], fill=col, width=int(P(14)))
        dr.polygon([T(740, self.SEAT_Y), T(900, self.SEAT_Y), T(900, self.SEAT_Y + 24), T(740, self.SEAT_Y + 24)], fill=col)
        dr.polygon([T(880, self.SEAT_Y), T(900, self.SEAT_Y), T(900, self.SEAT_Y - 120), T(880, self.SEAT_Y - 120)], fill=col)
        if s["on"] != "sunk":
            base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))
        for (x, y) in s["splash"]:
            if y < DY + 30:
                circle(dr, P(x), P(y), P(7), (200, 230, 255))


# ---------------------------------------------------------------- 6. testeur de matelas
class Mattress(Chapter):
    title = "SATURDAY · MATTRESS TESTER"
    stamp = ("PERFECT", GREEN)
    mood = "win"
    hold_s = 3.8
    TOP = 1380.0

    def setup(self):
        self.hop_init(430.0, self.TOP, start_h=200.0, gain=(1.0, 1.2), max_h=440.0, wobble=50.0, xmin=300, xmax=560)
        self.line("Saturday. Mattress tester.", "title", 0.0)
        self.nod = 0.0
        self.sink = 0.0

    def on_land(self, k, evs):
        self.nod = 1.0; self.sink = 18 * k
        if self.hits >= self.cfg["mattress_hits"] and not self.payoff:
            self.finish("PERFECT")
            self.line("Perfect.", "perfect", self.t + 0.3)
            self.line("He still works there.", "still", self.t + 1.6)

    def after(self, dt, evs):
        self.nod = max(0.0, self.nod - 2.5 * dt)
        self.sink = max(0.0, self.sink - 90 * dt)

    def snapshot(self):
        s = self.base_snap(); s["nod"] = self.nod; s["sink"] = self.sink
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (38, 44, 50), (70, 72, 78))
        # fenêtres d'usine
        for x in (120, 420, 720):
            dr.rectangle([P(x), P(560), P(x + 220), P(760)], fill=(60, 80, 100))
            dr.line([(P(x + 110), P(560)), (P(x + 110), P(760))], fill=(38, 44, 50), width=int(P(6)))
            dr.line([(P(x), P(660)), (P(x + 220), P(660))], fill=(38, 44, 50), width=int(P(6)))
        # pile de matelas au fond
        for i in range(3):
            dr.rounded_rectangle([P(760), P(1300 - i * 70), P(1060), P(1360 - i * 70)], radius=P(16), fill=(200, 196, 210))
        # le matelas et son cadre
        top = self.TOP
        dr.rectangle([P(180), P(top + 60), P(700), P(FLOOR_Y)], fill=(90, 70, 50))
        pts = []
        for i in range(27):
            x = 180 + (700 - 180) * i / 26
            y = top + s["sink"] * math.exp(-((x - s["bx"]) / 120.0) ** 2)
            pts.append((P(x), P(y)))
        dr.polygon(pts + [(P(700), P(top + 70)), (P(180), P(top + 70))], fill=(236, 232, 240))
        dr.line(pts, fill=(200, 196, 210), width=int(P(4)), joint="curve")
        for k in range(5):
            circle(dr, P(230 + k * 105), P(top + 35), P(5), (200, 196, 210))
        # le patron et son carnet
        nod = s["nod"]
        self.figure(dr, P, 900, FLOOR_Y, (70, 80, 110), h=240, w=90, hat=False, tilt=0.4 * nod)
        dr.rectangle([P(820), P(1300 + 10 * nod), P(880), P(1380 + 10 * nod)], fill=(240, 236, 220))
        for k in range(3):
            dr.line([(P(830), P(1320 + k * 18 + 10 * nod)), (P(870), P(1320 + k * 18 + 10 * nod))], fill=(120, 120, 130), width=int(P(3)))
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- 7. dimanche
class Sunday(Chapter):
    title = "SUNDAY · DAY OFF"
    hold_s = 0.0
    BED = 1330.0

    def setup(self):
        self.hop_init(540.0, self.BED, start_h=120.0, gain=(1.0, 1.15), max_h=260.0, wobble=40.0, xmin=420, xmax=660, start_air=False)
        self.line("Sunday. Day off.", "title", 0.0)
        self.line("He did not rest.", "rest", 3.2)
        self.sink = 0.0

    def on_land(self, k, evs):
        self.sink = 16 * k

    def after(self, dt, evs):
        self.sink = max(0.0, self.sink - 80 * dt)
        if self.t >= 6.0:
            self.finish("END")

    def snapshot(self):
        s = self.base_snap(); s["sink"] = self.sink
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 26, 44), (46, 36, 40))
        dr.rectangle([P(700), P(600), P(980), P(900)], fill=(10, 12, 28))
        circle(dr, P(900), P(680), P(40), (226, 228, 236)); circle(dr, P(920), P(668), P(36), (10, 12, 28))
        dr.rectangle([P(838), P(600), P(846), P(900)], fill=(60, 50, 70)); dr.rectangle([P(700), P(748), P(980), P(756)], fill=(60, 50, 70))
        top = self.BED
        dr.rectangle([P(150), P(top - 190), P(190), P(top + 120)], fill=(70, 50, 40))
        dr.rectangle([P(160), P(top + 20), P(940), P(FLOOR_Y)], fill=(80, 60, 90))
        pts = []
        for i in range(31):
            x = 160 + (940 - 160) * i / 30
            y = top + s["sink"] * math.exp(-((x - s["bx"]) / 130.0) ** 2)
            pts.append((P(x), P(y)))
        dr.polygon(pts + [(P(940), P(top + 60)), (P(160), P(top + 60))], fill=(210, 206, 226))
        dr.rounded_rectangle([P(190), P(top - 50), P(380), P(top + 10)], radius=P(18), fill=(236, 234, 244))
        dr.rectangle([P(400), P(top + 10), P(940), P(top + 50)], fill=(120, 60, 80))
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R))


# ---------------------------------------------------------------- l'histoire
DEFAULTS = {
    "ball_r": 58.0, "gravity": 3000.0,
    "intro_s": 6.2,
    "lib_lean": 0.12, "mus_kick": 0.7, "cake_slide": 16.0, "chair_kick": 0.13, "mattress_hits": 9,
    "chapter_max_s": 12.0,
    "counter_font_size": 56, "counter_y": 0.19, "hook_text_s": 5.5,
    "sub_y": 0.885, "watermark_y": 0.955,
}

CHAPTERS = [(Intro, {}), (Library, {}), (Waiter, {}), (Museum, {}), (Cake, {}), (Lifeguard, {}), (Mattress, {}), (Sunday, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
