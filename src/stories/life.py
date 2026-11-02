"""
Prototype « la vie de Bounce » : de sa naissance à ses 88 ans, en six chapitres de
quelques secondes. À chaque âge, une situation où il suffirait de se tenir tranquille, et
il ne s'arrête jamais de rebondir ni de dire son nom. Il grandit d'un chapitre à l'autre ;
sa voix, elle, est grave dès le premier jour.

    python3 src/stories/life.py configs/<name>.json [--simulate]
"""
import math, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter as _Chapter, RED, GREEN, AMBER, FLOOR_Y, SCENE_TOP, glow, mix, settle_body, separate, body_poly


class Chapter(_Chapter):
    """Le rythme de la voix : Bounce retombe au plus une fois par seconde, il tombe dans
    chaque nouvel âge pendant que le narrateur le nomme, et après la chute il se pose (sauf
    à la fin) : aucune réplique ne tombe sur une retombée, chaque choc est dit."""
    settle_after = True
    drop_in = True

    def start_drop(self):
        """Il arrive d'en haut : sa première retombée tombe après le titre."""
        if not self.drop_in:
            return
        T = 1.2
        h = min(0.5 * self.g * T ** 2, self.floor_y - 2 * self.R - SCENE_TOP - 10)
        self.by = self.floor_y - self.R - h
        self.vy = 0.0
        self.vx = 0.0
        self.on = "air"
        self.wait_until = T - math.sqrt(2 * h / self.g)

    def next_landing(self):
        if self.on != "air":
            return self.t
        a, b, c = 0.5 * self.g, self.vy, self.by - (self.floor_y - self.R)
        d = b * b - 4 * a * c
        return self.t + ((-b + math.sqrt(d)) / (2 * a) if d >= 0 else 0.0)

    def leap(self, h):
        """Un grand saut, assez long pour qu'une réplique tienne entre deux mots."""
        self.on = "air"
        self.vy = -math.sqrt(2 * self.g * h)
        self.vx = 0.0
        self.by = min(self.by, self.floor_y - self.R)

    def hop_step(self, dt, evs):
        if self.t < getattr(self, "wait_until", 0.0):
            return
        n0 = self.hits
        super().hop_step(dt, evs)
        if self.settle_after and self.payoff and self.hits > n0 and self.on == "air":
            self.on = "still"; self.vy = 0.0; self.vx = 0.0; self.by = self.floor_y - self.R

PINK = (255, 120, 200)
TEAL = (90, 200, 210)
MOON = (226, 228, 236)


def night_window(dr, P, x0, y0, x1, y1, wall, moon=None):
    dr.rectangle([P(x0 - 10), P(y0 - 10), P(x1 + 10), P(y1 + 10)], fill=dim(wall, 0.7))
    dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(16, 22, 44))
    if moon:
        circle(dr, P(moon[0]), P(moon[1]), P(26), MOON)
    dr.rectangle([P((x0 + x1) / 2 - 4), P(y0), P((x0 + x1) / 2 + 4), P(y1)], fill=dim(wall, 0.7))
    dr.rectangle([P(x0), P((y0 + y1) / 2 - 4), P(x1), P((y0 + y1) / 2 + 4)], fill=dim(wall, 0.7))


def small_ball(dr, P, x, y, r, col):
    """Un petit sans visage : une boule, un reflet."""
    circle(dr, P(x), P(y), P(r), col)
    circle(dr, P(x - r * 0.35), P(y - r * 0.35), P(r * 0.25), mix(col, (255, 255, 255), 0.5))


# ---------------------------------------------------------------- jour 1
class DayOne(Chapter):
    """La maternité : il rebondit dans son berceau, de plus en plus haut, et finit par
    sauter dehors. Son premier mot."""
    title = "DAY 1"
    stamp = ("IT'S A BOUNCE!", AMBER)
    stamp_y = 0.30
    mood = "win"
    hold_s = 1.2
    BX0, BX1, RIM, BOT = 330.0, 790.0, 1090.0, 1230.0

    def setup(self):
        self.R = 46.0
        self.hop_init(560.0, self.BOT, start_h=150.0, gain=(1.0, 1.0), min_h=80.0, max_h=700.0, wobble=30.0,
                      xmin=520, xmax=600, h_ref=250.0)
        self.hops = [260.0, 104.0, 380.0, 380.0]
        self.rock = 0.0
        self.rock_w = 0.0
        self.line("Day one.", "title", 0.0)
        self.leave = False
        self.spin = 2.6

    def on_land(self, k, evs):
        n = self.hits
        if self.leave:
            if self.floor_y == FLOOR_Y and not self.payoff:
                self.finish("OUT")
                self.line("His first word.", "word", self.t + 1.05)
            return
        if n <= len(self.hops):
            self.h = self.hops[n - 1]
            self.min_h = self.max_h = self.h
        self.rock_w += 1.4 * k * (1 if n % 2 else -1)
        if self.h >= 240:
            self.spin += 3.5
        if n == len(self.hops):
            # le dernier saut : par-dessus le bord du berceau, jusqu'au sol
            self.leave = True
            self.xmin, self.xmax, self.wobble = 170.0, 170.0, 0.0

    def after(self, dt, evs):
        self.spin = max(1.4, self.spin - 0.6 * dt)
        self.rock_w += (-30.0 * self.rock - 2.0 * self.rock_w) * dt
        self.rock += self.rock_w * dt
        if self.leave and self.bx < self.BX0 - self.R - 4:
            self.floor_y = FLOOR_Y
        if self.payoff:
            self.xmin = self.xmax = self.bx
            self.min_h = self.max_h = 90.0

    def snapshot(self):
        s = self.base_snap()
        s["spin"] = self.spin
        s["rock"] = self.rock
        s["end"] = self.end_t
        return s

    def solids(self, s):
        return [("rect", self.BX0 - 10, self.RIM, self.BX0 + 10, self.BOT + 20),
                ("rect", self.BX1 - 10, self.RIM, self.BX1 + 10, self.BOT + 20),
                ("rect", self.BX0, self.BOT, self.BX1, self.BOT + 20)]

    def focus(self, s):
        return (s["bx"] - 90, s["by"] - 90, s["bx"] + 90, s["by"] + self.R + 10)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (34, 34, 54)
        self.room(dr, P, wall, (60, 56, 66))
        # la veilleuse projette des étoiles qui tournent sur les murs
        for k in range(16):
            a = s["t"] * 0.9 + k * 2 * math.pi / 16
            rr = 260 + 160 * (k % 3)
            x, y = 560 + rr * math.cos(a), 900 + 0.7 * rr * math.sin(a)
            if SCENE_TOP + 30 < y < FLOOR_Y - 40:
                dr.regular_polygon((P(x), P(y), P(18 + 6 * (k % 2))), 5, fill=mix(wall, (255, 225, 140), 0.45))
        night_window(dr, P, 800, 760, 1000, 960, wall, moon=(950, 810))
        # le mobile au-dessus de son berceau
        cx, my = 560.0, 790.0
        dr.line([(P(cx), P(SCENE_TOP)), (P(cx), P(my))], fill=(150, 150, 165), width=int(P(5)))
        ang = s["t"] * s["spin"]
        dr.line([(P(cx - 210 * math.cos(ang)), P(my)), (P(cx + 210 * math.cos(ang)), P(my))], fill=(170, 170, 185), width=int(P(5)))
        for k in range(4):
            a = ang + k * math.pi / 2
            x = cx + 210 * math.cos(a)
            dr.line([(P(x), P(my)), (P(x), P(my + 70))], fill=(150, 150, 165), width=int(P(3)))
            col = [(250, 220, 90), (130, 200, 250), (250, 150, 180), (160, 230, 160)][k]
            r = 36 + 10 * math.sin(a)
            dr.regular_polygon((P(x), P(my + 92), P(r)), 5, fill=col)
        # son berceau, qui balance à chaque retombée (dessiné autour de son pied)
        a = 0.06 * s["rock"]
        px, py = (self.BX0 + self.BX1) / 2, FLOOR_Y
        def rot(x, y):
            return (P(px + (x - px) * math.cos(a) - (y - py) * math.sin(a)), P(py + (x - px) * math.sin(a) + (y - py) * math.cos(a)))
        def box(x0, y0, x1, y1, col):
            dr.polygon([rot(x0, y0), rot(x1, y0), rot(x1, y1), rot(x0, y1)], fill=col)
        box(self.BX0 + 10, self.RIM + 30, self.BX1 - 10, self.BOT, (250, 214, 230))
        box(self.BX0, self.BOT, self.BX1, self.BOT + 26, (235, 235, 245))
        box(self.BX0 - 12, self.RIM, self.BX0 + 12, self.BOT + 26, (235, 235, 245))
        box(self.BX1 - 12, self.RIM, self.BX1 + 12, self.BOT + 26, (235, 235, 245))
        for x in (self.BX0 + 50, self.BX1 - 64):
            box(x, self.BOT + 26, x + 14, FLOOR_Y, (150, 150, 165))
        dr.text(rot(px, self.BOT + 80), "BOUNCE", fill=(130, 120, 150), anchor="mm", font=base.font(int(P(40))))
        self.bounce(dr, P, s)
        # son premier mot, dans une bulle
        if s["end"] is not None and 0 <= s["t"] - s["end"] < 1.6:
            bx, by = s["bx"], s["by"]
            x0, y0, x1, y1 = bx + 60, by - 230, bx + 420, by - 110
            dr.rounded_rectangle([P(x0), P(y0), P(x1), P(y1)], radius=int(P(30)), fill=(250, 250, 252))
            dr.polygon([(P(x0 + 40), P(y1 - 4)), (P(x0 + 100), P(y1 - 4)), (P(bx + 40), P(by - 50))], fill=(250, 250, 252))
            dr.text((P((x0 + x1) / 2), P((y0 + y1) / 2)), "BOUNCE!", fill=(30, 20, 40), anchor="mm", font=base.font(int(P(64))))


# ---------------------------------------------------------------- 7 ans
class School(Chapter):
    """En classe : il rebondit sur sa chaise, la pile de livres sur son pupitre tremble à
    chaque retombée et finit par tomber. La maîtresse se retourne."""
    title = "AGE 7"
    stamp = ("DETENTION", RED)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.2
    DX0, DX1, DTOP = 300.0, 600.0, 1230.0
    BW, BH, N = 150.0, 34.0, 8

    def setup(self):
        self.R = 50.0
        self.seat = 1330.0
        self.hop_init(705.0, self.seat, start_h=260.0, gain=(0.95, 1.12), min_h=220.0, max_h=380.0, wobble=14.0,
                      xmin=695, xmax=718, h_ref=280.0)
        self.start_drop()
        self.line("Age seven.", "title", 0.0)
        self.off = [0.0] * self.N
        self.fall = None
        self.turn = 0.0

    def on_land(self, k, evs):
        if self.fall is not None:
            return
        self.sway = min(1.0, getattr(self, "sway", 0.2) + 0.12 * k)
        for i in range(self.N):
            self.off[i] += self.rng.uniform(-1.0, 0.35) * 7.0 * k * (i + 1) / self.N
        # le centre de gravité d'une pile au-dessus d'un livre sort de son appui : elle tombe
        for j in range(1, self.N):
            above = sum(self.off[j:]) / (self.N - j)
            if abs(above - self.off[j - 1]) > self.BW * 0.42 or self.hits >= 4:
                self.topple(j)
                break

    def topple(self, j):
        self.fall = []
        for i in range(self.N):
            x = 450.0 + self.off[i]
            y = self.DTOP - self.BH * (i + 0.5)
            c = {"x": x, "y": y, "a": 0.0, "vx": 0.0, "vy": 0.0, "w": 0.0, "rest": i < j, "i": i}
            if i >= j:
                c["vx"] = -self.rng.uniform(120, 420) * (1 + 0.15 * (i - j))
                c["vy"] = -self.rng.uniform(0, 120)
                c["w"] = -self.rng.uniform(2.0, 4.5)
            self.fall.append(c)

    def shape(self, c):
        return [(-self.BW / 2, -self.BH / 2), (self.BW / 2, -self.BH / 2), (self.BW / 2, self.BH / 2), (-self.BW / 2, self.BH / 2)]

    def ground(self, c):
        if self.DX0 < c["x"] < self.DX1 and c["y"] < self.DTOP - self.BH * 0.4:
            return self.DTOP
        return FLOOR_Y

    def after(self, dt, evs):
        if self.fall is not None:
            for c in self.fall:
                if c["rest"]:
                    continue
                c["vy"] += self.g * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["w"] * dt
                if c["x"] < 90:
                    c["x"] = 90; c["vx"] = abs(c["vx"]) * 0.3
                settle_body(c, self.ground(c), math.pi, dt, self.shape(c))
            if not self.payoff and any(not c["rest"] and c["y"] > FLOOR_Y - 80 for c in self.fall):
                self.finish("DETENTION")
                self.line("Detention.", "det", self.next_landing() + 1.05)
        if self.payoff:
            self.turn = min(1.0, self.turn + dt * 4)
        self.sway = max(0.15, getattr(self, "sway", 0.2) - 0.25 * dt)

    def snapshot(self):
        s = self.base_snap()
        s["sway"] = getattr(self, "sway", 0.2)
        s["off"] = list(self.off)
        s["fall"] = [dict(c) for c in self.fall] if self.fall is not None else None
        s["turn"] = self.turn
        return s

    def books(self, s):
        if s["fall"] is None:
            sway = 0.0
            out = []
            for i in range(self.N):
                w = s["sway"] * 26.0 * (i + 1) / self.N * math.sin(s["t"] * 9.0)
                out.append({"x": 450.0 + s["off"][i] + w, "y": self.DTOP - self.BH * (i + 0.5), "a": 0.0, "i": i})
            return out
        return s["fall"]

    def solids(self, s):
        sh = [("rect", self.DX0, self.DTOP, self.DX1, self.DTOP + 24), ("rect", 640, self.seat, 780, self.seat + 20)]
        for c in self.books(s):
            sh.append(("poly", body_poly(c, self.shape(c))))
        return sh

    def focus(self, s):
        bs = self.books(s)
        xs = [c["x"] for c in bs]; ys = [c["y"] for c in bs]
        return (max(20.0, min(xs) - 80), min(ys) - 30, max(xs) + 80, max(ys) + 30)

    def bodies(self, s):
        # une pile de livres tombés se chevauche à l'image : pas de polygone, seulement le suivi
        return [(c["i"], c["x"], c["y"], c["a"]) for c in self.books(s)]

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (36, 44, 46)
        self.room(dr, P, wall, (58, 48, 40))
        # le tableau, et ce qu'il y a d'écrit dessus
        dr.rectangle([P(120), P(570), P(960), P(900)], fill=(84, 64, 46))
        dr.rectangle([P(140), P(590), P(940), P(880)], fill=(30, 58, 46))
        dr.text((P(540), P(700)), "SIT STILL.", fill=(230, 236, 230), anchor="mm", font=base.font(int(P(84))))
        # la maîtresse écrit pendant la scène : les lignes s'allongent sous la consigne
        for row in range(3):
            L = max(0.0, min(1.0, (s["t"] - 0.8 - row * 2.2) / 2.2))
            if L > 0:
                y = 790 + row * 34
                dr.line([(P(200), P(y)), (P(200 + 680 * L), P(y))], fill=(170, 186, 170), width=int(P(6)))
        # le ventilateur au plafond
        fa = s["t"] * 7.0
        dr.rectangle([P(536), P(SCENE_TOP), P(544), P(500)], fill=(90, 90, 100))
        for k in range(3):
            a = fa + k * 2 * math.pi / 3
            ex, ey = 540 + 260 * math.cos(a), 505 + 26 * math.sin(a)
            dr.line([(P(540), P(505)), (P(ex), P(ey))], fill=(150, 150, 160), width=int(P(22)))
        circle(dr, P(540), P(505), P(22), (110, 110, 120))
        # la maîtresse : de dos, puis elle se retourne
        tx = 830 + 70 * math.sin(s["t"] * 0.9) - 60 * s["turn"]
        self.figure(dr, P, tx, FLOOR_Y, (110, 70, 90), h=300, w=104, tilt=-s["turn"])
        # le pupitre, la chaise
        wood = (120, 86, 58)
        dr.rectangle([P(self.DX0), P(self.DTOP), P(self.DX1), P(self.DTOP + 24)], fill=wood)
        for x in (self.DX0 + 20, self.DX1 - 40):
            dr.rectangle([P(x), P(self.DTOP + 24), P(x + 20), P(FLOOR_Y)], fill=dim(wood, 0.8))
        dr.rectangle([P(640), P(self.seat), P(780), P(self.seat + 20)], fill=(90, 110, 150))
        dr.rectangle([P(760), P(1160), P(780), P(self.seat)], fill=(90, 110, 150))
        for x in (650, 760):
            dr.rectangle([P(x), P(self.seat + 20), P(x + 14), P(FLOOR_Y)], fill=(70, 86, 120))
        cols = [(200, 70, 70), (70, 120, 200), (230, 190, 70), (90, 170, 110), (170, 100, 190), (230, 130, 60), (80, 170, 190), (210, 210, 220)]
        for c in self.books(s):
            pts = [(P(x), P(y)) for x, y in body_poly(c, self.shape(c))]
            dr.polygon(pts, fill=cols[c["i"] % len(cols)])
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 16 ans
class FirstLove(Chapter):
    """Sur un banc, sous un réverbère. Elle ne rebondissait pas. Chacune de ses retombées
    secoue le banc et la fait sauter ; elle se met à rebondir, et leurs rebonds finissent
    par tomber ensemble."""
    title = "AGE 16"
    stamp = ("PERFECT MATCH", PINK)
    stamp_y = 0.30
    mood = "win"
    hold_s = 1.3
    SEAT = 1300.0

    def setup(self):
        self.R = 54.0
        self.hop_init(420.0, self.SEAT, start_h=260.0, gain=(0.92, 1.1), min_h=245.0, max_h=320.0, wobble=10.0,
                      xmin=410, xmax=430, h_ref=240.0)
        self.start_drop()
        self.line("Sixteen.", "title", 0.0)
        self.her = {"x": 680.0, "y": self.SEAT - 50.0, "vy": 0.0, "on": "rest", "h": 0.0, "last": -9.0}
        self.r2 = 50.0
        self.sync = 0
        self.hearts = []
        self.said = False

    need_sync = 4
    blend_n = 2

    def on_match(self):
        pass                                   # le tampon le dit

    def next_land(self):
        """Le prochain instant où Bounce retombe sur le banc."""
        a = 0.5 * self.g
        b = self.vy
        c = self.by - (self.SEAT - self.R)
        d = b * b - 4 * a * c
        if d < 0:
            return None
        return self.t + (-b + math.sqrt(d)) / (2 * a)

    def on_land(self, k, evs):
        hr = self.her
        if hr["on"] == "rest":
            hr["kick"] = hr.get("kick", 0) + 1
            if hr["kick"] >= 2:
                hr["on"] = "air"
                hr["vy"] = -math.sqrt(2 * self.g * 90.0)
                self.said = True

    def after(self, dt, evs):
        hr = self.her
        if hr["on"] == "air":
            hr["vy"] += self.g * dt
            hr["y"] += hr["vy"] * dt
            if hr["vy"] > 0 and hr["y"] >= self.SEAT - self.r2:
                hr["y"] = self.SEAT - self.r2
                hr["last"] = self.t
                tn0 = self.next_land()
                if self.payoff:
                    hr["on"] = "rest"; hr["vy"] = 0.0
                elif (abs(self.t - self.hit_t) < 0.07 or (tn0 is not None and tn0 - self.t < 0.07)) \
                        and self.sync + 1 >= self.need_sync:
                    # leurs rebonds tombent ensemble : ils vont s'envoler à sa prochaine retombée
                    self.finish("MATCH")
                    self.match_pending = True
                    hr["on"] = "rest"; hr["vy"] = 0.0
                else:
                    if abs(self.t - self.hit_t) < 0.07 or (tn0 is not None and tn0 - self.t < 0.07):
                        self.sync += 1
                        self.hearts.append([hr["x"] - 80, self.SEAT - 140, self.t])
                    else:
                        self.sync = 0
                    self.plan_her(hr)
        if getattr(self, "match_pending", False) and (self.hit_t == self.t or abs(self.hit_t - self.t) < 0.075):
            # leurs rebonds sont tombés ensemble : ils se posent côte à côte
            self.match_pending = False
            self.on = "still"; self.vy = 0.0; self.vx = 0.0; self.by = self.floor_y - self.R
            self.on_match()
        self._her_tail(dt)

    def plan_her(self, hr):
        if True:
            if True:
                # son prochain saut : réglé pour retomber un peu plus près de lui
                tn = self.next_land()
                T = (tn - self.t) if tn is not None else 0.7
                if T < 0.45:
                    T += 2 * math.sqrt(2 * self.h / self.g)
                want = self.g * T * T / 8.0
                hr["h"] = want if hr.get("n", 0) >= self.blend_n else 0.5 * (want + 160.0)
                hr["n"] = hr.get("n", 0) + 1
                hr["vy"] = -math.sqrt(2 * self.g * max(60.0, min(420.0, hr["h"])))

    def _her_tail(self, dt):
        if self.payoff:
            if self.rng.random() < dt * 9:
                self.hearts.append([550 + self.rng.uniform(-120, 120), self.SEAT - 200, self.t])
        self.hearts = [h for h in self.hearts if self.t - h[2] < 1.6]

    def snapshot(self):
        s = self.base_snap()
        s["her"] = (self.her["x"], self.her["y"])
        s["hearts"] = [tuple(h) for h in self.hearts]
        return s

    def solids(self, s):
        x, y = s["her"]
        return [("rect", 260, self.SEAT, 820, self.SEAT + 26), ("circle", x, y, self.r2)]

    def focus(self, s):
        x, y = s["her"]
        return (s["bx"] - 80, min(s["by"], y) - 120, x + 80, self.SEAT + 30)

    def bodies(self, s):
        x, y = s["her"]
        return [("her", x, y, 0.0)]

    def heart(self, dr, P, x, y, r, col):
        circle(dr, P(x - r * 0.5), P(y), P(r * 0.55), col)
        circle(dr, P(x + r * 0.5), P(y), P(r * 0.55), col)
        dr.polygon([(P(x - r * 1.02), P(y + r * 0.15)), (P(x + r * 1.02), P(y + r * 0.15)), (P(x), P(y + r * 1.2))], fill=col)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        sky = (20, 24, 46)
        dr.rectangle([0, P(SCENE_TOP), P(self.W), P(FLOOR_Y)], fill=sky)
        for i in range(30):
            circle(dr, P((i * 7919 + 211) % self.W), P(460 + (i * 104729 + 37) % 520), P(2), (150, 155, 190))
        circle(dr, P(890), P(790), P(40), MOON)
        for k in range(14):
            a = s["t"] * (0.7 + 0.1 * (k % 4)) + k * 0.9
            fx = 540 + (180 + 40 * (k % 3)) * math.cos(a)
            fy = 960 + (110 + 30 * (k % 2)) * math.sin(1.3 * a)
            circle(dr, P(fx), P(fy), P(6), (250, 240, 150))
        # les arbres du parc
        for (x, r) in ((80, 150), (980, 170)):
            dr.rectangle([P(x - 16), P(1100), P(x + 16), P(FLOOR_Y)], fill=(50, 40, 36))
            circle(dr, P(x), P(1040), P(r), (26, 50, 40))
        # le réverbère
        fl = 0.26 + 0.12 * math.sin(s["t"] * 5.0) * math.sin(s["t"] * 1.7)
        glow(dr, P, 540, 900, 380, (255, 220, 150), sky, fl, rings=8)
        dr.rectangle([P(536), P(900), P(548), P(FLOOR_Y)], fill=(70, 70, 84))
        dr.rectangle([P(500), P(880), P(584), P(906)], fill=(250, 226, 160))
        dr.rectangle([0, P(FLOOR_Y), P(self.W), P(self.H)], fill=(30, 50, 34))
        # le banc
        wood = (130, 90, 58)
        dr.rectangle([P(260), P(1180), P(820), P(1206)], fill=dim(wood, 0.85))
        dr.rectangle([P(260), P(self.SEAT), P(820), P(self.SEAT + 26)], fill=wood)
        for x in (300, 760):
            dr.rectangle([P(x), P(self.SEAT + 26), P(x + 20), P(FLOOR_Y)], fill=(60, 60, 70))
        x, y = s["her"]
        small_ball(dr, P, x, y, self.r2, TEAL)
        # un nœud dans les cheveux : c'est elle
        dr.polygon([(P(x - 6), P(y - 46)), (P(x - 34), P(y - 66)), (P(x - 30), P(y - 34))], fill=(250, 110, 150))
        dr.polygon([(P(x + 6), P(y - 46)), (P(x + 34), P(y - 66)), (P(x + 30), P(y - 34))], fill=(250, 110, 150))
        for (hx, hy, t0) in s["hearts"]:
            age = s["t"] - t0
            self.heart(dr, P, hx, hy - 160 * age, 22 * (1 - 0.3 * age), (250, 110, 160))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 25 ans
class Apartment(Chapter):
    """Son premier appartement, juste au-dessus du voisin qui regarde la télé. Chaque
    retombée fissure le plancher, le plâtre tombe chez le voisin ; le plancher cède et
    Bounce atterrit sur son canapé."""
    title = "AGE 25"
    stamp = ("NEW ROOMMATE", AMBER)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.3
    drop_in = False
    FL, TH = 1040.0, 80.0
    H0, H1 = 420.0, 660.0
    COUCH = 1360.0
    GO = 2.5

    def setup(self):
        self.R = 62.0
        self.hop_init(540.0, self.FL, start_h=0.0, gain=(0.95, 1.08), min_h=280.0, max_h=320.0, wobble=6.0,
                      xmin=535, xmax=545, h_ref=300.0, start_air=False)
        self.on = "still"; self.by = self.FL - self.R; self.h = 300.0
        self.line("Twenty five.", "title", 0.0)
        self.line("Downstairs neighbor.", "neighbor", 0.9)
        self.crack = 0.0
        self.open = None
        self.dust = []
        self.chunks = []
        self.lamp = 0.0
        self.lamp_w = 2.5

    def on_land(self, k, evs):
        if self.open is not None:
            if not self.payoff and self.t - self.open > 0.2:
                self.finish("FELL")
                self.line("Roommates now.", "now", self.t + 1.05)
            return
        self.crack += 0.55 * k * self.rng.uniform(0.95, 1.1)
        self.lamp_w += 3.0 * k
        for _ in range(8):
            self.dust.append([self.rng.uniform(self.H0 - 60, self.H1 + 60), self.FL + self.TH, self.rng.uniform(-40, 40), self.t,
                              self.rng.uniform(8, 16)])
        if self.crack >= 1.0:
            # le plancher cède sous lui : deux trappes s'ouvrent, il tombe chez le voisin
            self.open = self.t
            self.lamp_w += 9.0
            for k2 in range(12):
                side = -1 if k2 % 2 == 0 else 1
                x = (self.H0 + 20 if side < 0 else self.H1 - 20) + self.rng.uniform(-20, 20)
                self.chunks.append({"x": x, "y": self.FL + self.TH / 2, "vx": side * self.rng.uniform(90, 260),
                                    "vy": self.rng.uniform(-200, 50), "a": 0.0, "w": self.rng.uniform(-6, 6),
                                    "s": self.rng.uniform(18, 34), "rest": False, "id": k2})
            self.floor_y = self.COUCH
            self.xmin = self.xmax = 540.0

    def flap(self, t):
        if self.open is None:
            return 0.0
        u = t - self.open
        if u * 12.0 < math.pi / 2 * 0.95:
            return u * 12.0
        return math.pi / 2 * 0.95 - 0.3 * math.exp(-0.8 * u) * abs(math.sin(u * 7.0))

    def after(self, dt, evs):
        if self.on == "still" and self.open is None and self.t >= self.GO:
            self.on = "ground"
        if self.open is not None and self.t - self.open < 1e-9 + dt and self.on == "air":
            self.vy = -400.0                    # le plancher se dérobe sous lui : un petit sursaut, puis la chute
        self.lamp_w += -9.0 * self.lamp * dt - 0.8 * self.lamp_w * dt
        self.lamp += self.lamp_w * dt
        self.dust = [d for d in self.dust if self.t - d[3] < 1.6]
        for c in self.chunks:
            if c["rest"]:
                continue
            c["vy"] += self.g * dt
            c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["w"] * dt
            gy = (self.COUCH if 330 < c["x"] < 750 else FLOOR_Y) - c["s"] * 0.35
            if c["y"] >= gy:
                c["y"] = gy; c["rest"] = True

    def snapshot(self):
        s = self.base_snap()
        s.update(crack=self.crack, flap=self.flap(self.t), dust=[tuple(d) for d in self.dust], lamp=self.lamp,
                 chunks=[dict(c) for c in self.chunks])
        return s

    def flaps(self, s):
        a = s["flap"]
        L = (self.H1 - self.H0) / 2
        out = []
        for (hx, sg) in ((self.H0, 1), (self.H1, -1)):
            ex, ey = hx + sg * L * math.cos(a), self.FL + L * math.sin(a)
            out.append((hx, self.FL, ex, ey))
        return out

    def solids(self, s):
        sh = [("rect", 0, self.FL, self.H0, self.FL + self.TH), ("rect", self.H1, self.FL, self.W, self.FL + self.TH),
              ("rect", 330, self.COUCH, 750, self.COUCH + 60)]
        for (x0, y0, x1, y1) in self.flaps(s):
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L * 14, dx / L * 14
            if ny < 0:
                nx, ny = -nx, -ny
            sh.append(("poly", [(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]))
        return sh

    def focus(self, s):
        return (s["bx"] - 110, s["by"] - 110, s["bx"] + 110, s["by"] + self.R + 20)

    def bodies(self, s):
        out = [(k, (x0 + x1) / 2, (y0 + y1) / 2, math.atan2(y1 - y0, x1 - x0)) for k, (x0, y0, x1, y1) in enumerate(self.flaps(s))]
        out += [("c%d" % c["id"], c["x"], c["y"], 0.0) for c in s["chunks"]]
        return out

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        up, down = (46, 42, 64), (42, 52, 48)
        FL, TH = self.FL, self.TH
        dr.rectangle([0, P(SCENE_TOP), P(self.W), P(FL)], fill=up)
        dr.rectangle([0, P(FL), P(self.W), P(FLOOR_Y)], fill=down)
        dr.rectangle([0, P(FLOOR_Y), P(self.W), P(self.H)], fill=(52, 42, 38))
        # en haut : des cartons de déménagement, une fenêtre
        night_window(dr, P, 770, 720, 950, 900, up, moon=(905, 760))
        for (x, w, h, y_off) in ((70, 160, 130, 0), (95, 110, 90, 130), (760, 180, 110, 0)):
            y0 = FL - h - y_off
            dr.rectangle([P(x), P(y0), P(x + w), P(y0 + h)], fill=(170, 130, 86))
            dr.rectangle([P(x), P(y0 + h / 2 - 6), P(x + w), P(y0 + h / 2 + 6)], fill=(140, 104, 66))
        # en bas : la télé du voisin, qui clignote
        tv = [(70, 120, 200), (200, 90, 140), (90, 180, 120), (220, 200, 90)][int(s["t"] * 10) % 4]
        dr.rectangle([P(30), P(1180), P(330), P(1400)], fill=(30, 30, 34))
        dr.rectangle([P(46), P(1196), P(314), P(1384)], fill=tv)
        dr.rectangle([P(140), P(1400), P(220), P(FLOOR_Y)], fill=(70, 56, 46))
        # le plancher, épais ; la fissure ; les trappes
        slab = (120, 100, 86)
        dr.rectangle([0, P(FL), P(self.H0), P(FL + TH)], fill=slab)
        dr.rectangle([P(self.H1), P(FL), P(self.W), P(FL + TH)], fill=slab)
        for (x0, y0, x1, y1) in self.flaps(s):
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L * TH, dx / L * TH
            if ny < 0:
                nx, ny = -nx, -ny
            dr.polygon([(P(x0), P(y0)), (P(x1), P(y1)), (P(x1 + nx), P(y1 + ny)), (P(x0 + nx), P(y0 + ny))], fill=slab)
        dr.rectangle([0, P(FL), P(self.W), P(FL + 8)], fill=(150, 124, 100)) if s["flap"] == 0.0 else None
        if s["flap"] == 0.0 and s["crack"] > 0.05:
            c = min(1.0, s["crack"])
            # la fissure : une grande étoile de cassures dans la dalle, qui gagne le plafond du voisin
            for (dx0, ang, L) in ((0, 1.5, 1.0), (-1, 3.0, 1.3), (1, 0.1, 1.3), (-1, 2.5, 0.9), (1, 0.6, 0.9), (0, 1.9, 0.8)):
                pts = [(540.0, FL)]
                x, y = 540.0, FL
                for k in range(7):
                    a = ang + 0.45 * math.sin(k * 2.3 + dx0)
                    step = 42 * L * c
                    x += math.cos(a) * step; y += abs(math.sin(a)) * step * 0.6 + 4
                    pts.append((x, min(FL + TH + 10, y)))
                dr.line([(P(px), P(py)) for (px, py) in pts], fill=(28, 20, 18), width=int(P(12)))
            for (ox, L) in ((-60, 1.0), (40, 1.2), (110, 0.8), (-140, 0.7)):
                dr.line([(P(540 + ox * c), P(FL + TH)), (P(540 + ox * c * 1.6), P(FL + TH + 70 * L * c))], fill=(28, 20, 18), width=int(P(8)))
        elif s["flap"] > 0:
            # le trou, net : ses bords cassés
            for xx in (self.H0, self.H1):
                for k in range(4):
                    dr.polygon([(P(xx - 10), P(FL + k * 20)), (P(xx + 10), P(FL + k * 20 + 10)), (P(xx - 10), P(FL + k * 20 + 20))], fill=(70, 56, 46))
        # la lampe du voisin, qui se balance
        lx = 540 + 110 * math.sin(s["lamp"])
        dr.line([(P(540), P(FL + TH)), (P(lx), P(FL + TH + 110))], fill=(150, 150, 160), width=int(P(4)))
        dr.polygon([(P(lx - 46), P(FL + TH + 156)), (P(lx + 46), P(FL + TH + 156)), (P(lx + 22), P(FL + TH + 110)), (P(lx - 22), P(FL + TH + 110))], fill=(250, 220, 150))
        # son canapé
        dr.rectangle([P(330), P(self.COUCH), P(750), P(self.COUCH + 60)], fill=(150, 70, 70))
        dr.rectangle([P(330), P(self.COUCH - 90), P(750), P(self.COUCH)], fill=(130, 60, 60))
        dr.rectangle([P(310), P(self.COUCH - 40), P(350), P(FLOOR_Y)], fill=(120, 54, 54))
        dr.rectangle([P(730), P(self.COUCH - 40), P(770), P(FLOOR_Y)], fill=(120, 54, 54))
        # le voisin, debout, qui lève les yeux ; il sursaute quand le plafond cède
        jump = abs(math.sin(s["t"] * 9.0)) * 60.0 if s["flap"] > 0 else 0.0
        self.figure(dr, P, 830, FLOOR_Y - jump, (80, 120, 96), h=340, w=110)
        for (x, y, vx, t0, r) in s["dust"]:
            age = s["t"] - t0
            yy = y + 200 * age + 400 * age * age
            if yy < FLOOR_Y - 10:
                circle(dr, P(x + vx * age), P(yy), P(r), (215, 205, 185))
        for c in s["chunks"]:
            body = {"x": c["x"], "y": c["y"], "a": c["a"]}
            hs = c["s"] / 2
            dr.polygon([(P(x), P(y)) for (x, y) in body_poly(body, [(-hs, -hs * 0.7), (hs, -hs * 0.7), (hs, hs * 0.7), (-hs, hs * 0.7)])], fill=(200, 188, 168))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 29 ans
class Wedding(FirstLove):
    """Le mariage, avec elle. « Do you take her? » — il répond comme il peut. Elle répond
    en rebondissant, et quand leurs rebonds tombent ensemble, les confettis partent."""
    title = "AGE 29"
    stamp = ("JUST MARRIED", PINK)
    hold_s = 1.2
    need_sync = 2
    blend_n = 0
    SEAT = FLOOR_Y

    def setup(self):
        self.R = 64.0
        self.hop_init(430.0, self.SEAT, start_h=260.0, gain=(0.95, 1.08), min_h=245.0, max_h=310.0, wobble=8.0,
                      xmin=424, xmax=436, h_ref=220.0)
        self.start_drop()
        self.line("Twenty nine.", "title", 0.0)
        self.line("Do you take her?", "vow", 2.12)
        self.reply("vow", 0.35)
        self.resume = 4.3
        self.her = {"x": 660.0, "y": self.SEAT - 54.0, "vy": 0.0, "on": "rest", "h": 0.0, "last": -9.0}
        self.r2 = 54.0
        self.sync = 0
        self.hearts = []
        self.said = False
        self.confetti = []
        self.petals = [[300 + k * 37.0 % 480, 760.0 + (k * 97) % 700, 0.0, k * 1.3] for k in range(8)]

    def on_match(self):
        self.line("He meant yes.", "yes", self.t + 1.05)

    def on_land(self, k, evs):
        hr = self.her
        pass

    def after(self, dt, evs):
        # à l'autel, il se tient (presque) tranquille pendant la question, puis répond
        if self.hits >= 1 and self.t < self.resume and self.on == "air" and self.hit_t == self.t:
            self.on = "still"; self.vy = 0.0; self.by = self.floor_y - self.R
        if self.on == "still" and self.t >= self.resume and not self.payoff:
            self.on = "ground"
        hr = self.her
        if hr["on"] == "rest" and self.t >= self.resume and self.on == "air" and self.vy < 0 and not self.payoff:
            # elle répond en rebondissant avec lui, calée sur sa retombée
            T = self.next_landing() - self.t
            hr["on"] = "air"; hr["vy"] = -self.g * T / 2; hr["n"] = 1
        was = self.payoff
        super().after(dt, evs)
        if self.payoff and not was:
            for _ in range(70):
                a = self.rng.uniform(-2.6, -0.5)
                v = self.rng.uniform(500, 1100)
                self.confetti.append([545.0, self.SEAT - 160, math.cos(a) * v, math.sin(a) * v,
                                      [(250, 110, 160), (250, 220, 90), (130, 200, 250), (160, 230, 160), (240, 240, 250)][len(self.confetti) % 5]])
        if self.rng.random() < dt * 6:
            self.petals.append([self.rng.uniform(300, 780), 760.0, self.rng.uniform(-40, 40), self.rng.uniform(0, 6.28)])
        for pt in self.petals:
            pt[1] += 140 * dt; pt[0] += pt[2] * dt + 30 * math.sin(self.t * 2 + pt[3]) * dt
        self.petals = [pt for pt in self.petals if pt[1] < FLOOR_Y]
        for c in self.confetti:
            c[3] += 1400 * dt
            c[0] += c[2] * dt; c[1] += c[3] * dt
            c[2] *= (1 - 1.2 * dt)
        self.confetti = [c for c in self.confetti if c[1] < FLOOR_Y]
        self.hearts = []

    def snapshot(self):
        s = super().snapshot()
        s["conf"] = [tuple(c) for c in self.confetti]
        s["petals"] = [tuple(p) for p in self.petals]
        return s

    def solids(self, s):
        x, y = s["her"]
        return [("circle", x, y, self.r2)]

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (40, 34, 52)
        self.room(dr, P, wall, (70, 56, 60))
        # l'arche de fleurs, l'allée, les invités
        dr.arc([P(300), P(760), P(780), P(1480)], 180, 360, fill=(240, 240, 248), width=int(P(22)))
        for k in range(14):
            a = math.pi + k * math.pi / 13
            fx, fy = 540 + 240 * math.cos(a), 1120 + 360 * math.sin(a)
            circle(dr, P(fx), P(fy), P(18), [(250, 140, 180), (250, 220, 120), (240, 240, 250)][k % 3])
        dr.rectangle([P(250), P(FLOOR_Y - 10), P(830), P(FLOOR_Y + 30)], fill=(150, 40, 60))
        for k, (x, col) in enumerate(((70, (90, 100, 140)), (150, (120, 90, 120)), (790, (100, 120, 100)), (860, (130, 110, 80)))):
            sway = 8 * math.sin(s["t"] * 2.0 + k)
            self.figure(dr, P, x + sway, FLOOR_Y, col, h=230, w=64)
            # de temps en temps, un invité prend une photo : un petit éclat blanc
            u = (s["t"] * 0.8) % 1.0
            if int(s["t"] * 0.8) % 4 == k and u < 0.06:
                fx, fy = x + sway, FLOOR_Y - 260
                circle(dr, P(fx), P(fy), P(16), (255, 255, 255))
                for a in range(4):
                    ang = a * math.pi / 4
                    dr.line([(P(fx - 44 * math.cos(ang)), P(fy - 44 * math.sin(ang))), (P(fx + 44 * math.cos(ang)), P(fy + 44 * math.sin(ang)))],
                            fill=(255, 255, 255), width=int(P(5)))
        x, y = s["her"]
        small_ball(dr, P, x, y, self.r2, TEAL)
        # le voile
        dr.polygon([(P(x - 30), P(y - 50)), (P(x + 30), P(y - 50)), (P(x + 66), P(y + 40)), (P(x - 20), P(y + 10))], fill=(240, 240, 250))
        for (px_, py_, _v, ph) in s.get("petals", []):
            dr.ellipse([P(px_ - 9), P(py_ - 6), P(px_ + 9), P(py_ + 6)], fill=(250, 170, 200))
        for (cx, cy, vx, vy, col) in s["conf"]:
            dr.rectangle([P(cx - 6), P(cy - 4), P(cx + 6), P(cy + 4)], fill=col)
        self.bounce(dr, P, s)
        # le nœud papillon
        bx, by = s["bx"], s["by"]
        dr.polygon([(P(bx), P(by + 44)), (P(bx - 26), P(by + 30)), (P(bx - 26), P(by + 58))], fill=(20, 20, 26))
        dr.polygon([(P(bx), P(by + 44)), (P(bx + 26), P(by + 30)), (P(bx + 26), P(by + 58))], fill=(20, 20, 26))


# ---------------------------------------------------------------- 33 ans
class Dad(Chapter):
    """Son bébé dort dans son lit à barreaux. Il n'arrive pas à ne pas rebondir à côté. Le
    bébé se réveille, et rebondit à son tour."""
    title = "AGE 33"
    stamp = ("LIKE FATHER", AMBER)
    stamp_y = 0.30
    mood = "win"
    hold_s = 4.4
    CX0, CX1, CBOT, CRIM = 560.0, 840.0, 1300.0, 1120.0

    def setup(self):
        self.R = 66.0
        self.hop_init(330.0, FLOOR_Y, start_h=260.0, gain=(0.95, 1.1), min_h=220.0, max_h=330.0, wobble=40.0,
                      xmin=280, xmax=380, h_ref=260.0)
        self.start_drop()
        self.line("Thirty three.", "title", 0.0)
        self.baby = {"x": 700.0, "y": self.CBOT - 26.0, "vy": 0.0, "on": "sleep", "w": 0.0, "last": -9.0, "n": 0}
        self.rb = 26.0

    def on_land(self, k, evs):
        b = self.baby
        if b["on"] == "sleep":
            b["w"] += 0.42 * k * self.rng.uniform(0.9, 1.1)
            b["stir"] = self.t
            if b["w"] >= 1.0:
                b["on"] = "wake"

    def after(self, dt, evs):
        b = self.baby
        if b["on"] == "wake" and self.on == "air" and self.vy < 0:
            # le premier saut du bébé est réglé pour retomber en même temps que son père
            a = 0.5 * self.g
            c = self.by - (self.floor_y - self.R)
            T = (-self.vy + math.sqrt(self.vy * self.vy - 4 * a * c)) / (2 * a)
            b["on"] = "air"
            b["vy"] = -self.g * T / 2
        if b["on"] == "rest":
            # après la réplique, le père et le bébé repartent ensemble
            if getattr(self, "together", None) is not None and self.t >= self.together and self.on == "still":
                self.on = "ground"
                self.settle_after = False
            if getattr(self, "together", None) is not None and self.t >= self.together and self.on == "air" and self.vy < 0:
                T = self.next_landing() - self.t
                b["on"] = "air"; b["vy"] = -self.g * T / 2; b["n"] = 2; b["sync"] = True
        elif b["on"] == "air":
            b["vy"] += self.g * dt
            b["y"] += b["vy"] * dt
            if b["vy"] > 0 and b["y"] >= self.CBOT - self.rb:
                b["y"] = self.CBOT - self.rb
                b["n"] += 1
                b["last"] = self.t
                # le bébé aussi dit son nom, et de la même voix (sauf s'il retombe avec son père)
                if abs(self.t - self.hit_t) > 0.05:
                    evs.append(("hit", "floor"))
                if b.get("sync"):
                    T = self.next_landing() - self.t if self.on == "air" else 0.0
                    if T < 0.3:
                        T += 2 * math.sqrt(2 * self.h / self.g)
                    b["vy"] = -self.g * T / 2
                elif b["n"] == 1 and not self.payoff:
                    # le bébé retombe avec son père : ils se posent ensemble
                    self.finish("LIKE")
                    self.on = "still"; self.vy = 0.0; self.vx = 0.0; self.by = self.floor_y - self.R
                    b["on"] = "rest"; b["vy"] = 0.0
                    self.line("Like father.", "like", self.t + 1.05)
                    self.together = self.t + 2.3

    def snapshot(self):
        s = self.base_snap()
        b = self.baby
        s["baby"] = (b["x"], b["y"], b["on"], b["w"], b.get("stir", -9.0))
        return s

    def solids(self, s):
        return [("rect", self.CX0 - 12, self.CRIM, self.CX0 + 12, FLOOR_Y), ("rect", self.CX1 - 12, self.CRIM, self.CX1 + 12, FLOOR_Y),
                ("rect", self.CX0, self.CBOT, self.CX1, self.CBOT + 30)]

    def focus(self, s):
        x, y = s["baby"][0], s["baby"][1]
        return (x - 120, y - 200, x + 120, self.CBOT + 30)

    def bodies(self, s):
        return [("baby", s["baby"][0], s["baby"][1], 0.0)]

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (40, 36, 58)
        self.room(dr, P, wall, (64, 52, 56))
        night_window(dr, P, 110, 720, 320, 920, wall, moon=(270, 770))
        glow(dr, P, 900, 980, 260, (255, 210, 150), wall, 0.18 + 0.1 * math.sin(s["t"] * 3.0))
        circle(dr, P(900), P(980), P(22), (250, 220, 160))
        # des étoiles peintes au mur
        for i in range(9):
            dr.regular_polygon((P(470 + (i * 97) % 520), P(520 + (i * 61) % 260), P(12)), 5, fill=(70, 66, 100))
        x, y, on, w, stir = s["baby"]
        # le mobile au-dessus du lit, comme celui de son premier jour
        ang = s["t"] * 3.2
        dr.line([(P(700), P(SCENE_TOP)), (P(700), P(900))], fill=(150, 150, 165), width=int(P(5)))
        dr.line([(P(700 - 170 * math.cos(ang)), P(900)), (P(700 + 170 * math.cos(ang)), P(900))], fill=(170, 170, 185), width=int(P(5)))
        for k in range(4):
            a = ang + k * math.pi / 2
            mx = 700 + 170 * math.cos(a)
            dr.line([(P(mx), P(900)), (P(mx), P(960))], fill=(150, 150, 165), width=int(P(3)))
            dr.regular_polygon((P(mx), P(985), P(30 + 8 * math.sin(a))), 5,
                               fill=[(250, 220, 90), (130, 200, 250), (250, 150, 180), (160, 230, 160)][k])
        # le lit à barreaux
        wood = (220, 220, 232)
        dr.rectangle([P(self.CX0), P(self.CBOT), P(self.CX1), P(self.CBOT + 30)], fill=wood)
        if on == "sleep":
            small_ball(dr, P, x, y, self.rb, PINK)
            if s["t"] - stir < 0.3:
                dr.text((P(x + 30), P(y - 44)), "?", fill=(250, 220, 120), anchor="mm", font=base.font(int(P(36))))
            u = (s["t"] * 0.5) % 1.0
            dr.text((P(x + 26 + 20 * u), P(y - 40 - 60 * u)), "z", fill=mix(wall, (200, 200, 230), 1 - u), anchor="mm", font=base.font(int(P(30))))
        else:
            small_ball(dr, P, x, y, self.rb, PINK)
        for k in range(9):
            bx = self.CX0 + 12 + k * (self.CX1 - self.CX0 - 24) / 8
            dr.rectangle([P(bx - 4), P(self.CRIM), P(bx + 4), P(self.CBOT)], fill=wood)
        dr.rectangle([P(self.CX0 - 12), P(self.CRIM), P(self.CX0 + 12), P(FLOOR_Y)], fill=wood)
        dr.rectangle([P(self.CX1 - 12), P(self.CRIM), P(self.CX1 + 12), P(FLOOR_Y)], fill=wood)
        dr.rectangle([P(self.CX0), P(self.CRIM), P(self.CX1), P(self.CRIM + 14)], fill=wood)
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 88 ans
class Old(Chapter):
    settle_after = False
    """Sur la véranda, dans son rocking-chair, à 88 ans. Ses rebonds sont devenus petits ;
    pour la première fois de sa vie, il s'arrête. Un compteur le chronomètre. Un de ses
    petits-enfants lui saute dessus, et c'est reparti."""
    title = "AGE 88"
    stamp = ("NEVER STOPPED", GREEN)
    stamp_y = 0.30
    mood = "win"
    hold_s = 2.4
    stamp_y = 0.255
    SEAT = 1350.0

    def setup(self):
        self.R = 62.0
        self.hop_init(400.0, self.SEAT, start_h=175.0, gain=(1.0, 1.0), min_h=175.0, max_h=175.0, wobble=0.0,
                      xmin=400, xmax=400, h_ref=120.0)
        self.start_drop()
        self.line("Eighty eight.", "title", 0.0)
        self.still_t = None
        self.kids = [{"x": 760.0, "y": FLOOR_Y - 24, "vy": -700.0, "vx": 0.0, "r": 24.0, "col": (255, 150, 210)},
                     {"x": 860.0, "y": FLOOR_Y - 22, "vy": -400.0, "vx": 0.0, "r": 22.0, "col": (255, 130, 190)},
                     {"x": 660.0, "y": FLOOR_Y - 20, "vy": -900.0, "vx": 0.0, "r": 20.0, "col": (255, 165, 220)}]
        self.jump = None
        self.rock = 0.0
        self.rock_w = 0.0
        self.back = False

    def on_land(self, k, evs):
        self.rock_w += 0.6 * k
        if not self.back and self.hits >= 3 and self.still_t is None:
            self.on = "still"
            self.by = self.SEAT - self.R
            self.still_t = self.t
            self.line("He finally sat still.", "still", self.t + 0.95)
            self.line("A new record.", "record", self.t + 2.2)


    def after(self, dt, evs):
        self.rock_w += (-14.0 * self.rock - 1.4 * self.rock_w) * dt
        self.rock += self.rock_w * dt
        for i, kd in enumerate(self.kids):
            if kd is self.jump:
                continue
            kd["vy"] += self.g * dt
            kd["y"] += kd["vy"] * dt
            kd["x"] += kd.get("vx", 0.0) * dt
            if kd["vy"] > 0 and kd["y"] >= FLOOR_Y - kd["r"]:
                kd["y"] = FLOOR_Y - kd["r"]
                kd["vx"] = 0.0
                kd["vy"] = -math.sqrt(2 * self.g * (150.0 + 40 * i))
        # au bout de trois secondes immobile, le plus petit lui saute dessus
        if self.still_t is not None and self.jump is None and not self.back and self.t - self.still_t > 3.1:
            kd = self.kids[0]
            if kd["vy"] > 0:
                self.jump = kd
                T = 0.6
                tx, ty = self.bx + 10, self.by - self.R - kd["r"]
                kd["vx"] = (tx - kd["x"]) / T
                kd["vy"] = (ty - kd["y"] - 0.5 * self.g * T * T) / T
        if self.jump is not None:
            kd = self.jump
            kd["vy"] += self.g * dt
            kd["x"] += kd["vx"] * dt; kd["y"] += kd["vy"] * dt
            d = math.hypot(kd["x"] - self.bx, kd["y"] - self.by)
            if d < self.R + kd["r"] and kd["vy"] > 0 and not self.back:
                # le petit retombe sur lui : il repart
                self.back = True
                # le petit lui tombe dessus : un choc, il dit son nom, et il bondit comme jamais
                if self.t - self.last_hit >= 0.15:
                    self.last_hit = self.t
                    evs.append(("hit", "floor"))
                self.hit_t = self.t
                self.min_h, self.max_h, self.gain, self.h = 240.0, 300.0, (0.95, 1.1), 260.0
                self.leap_at = self.t + 0.15         # le petit rebondit d'abord sur sa tête, vers le jardin
                if not self.payoff:
                    self.finish("NEVER")
                kd["y"] = self.by - self.R - kd["r"] - 1
                kd["vy"] = -900.0; kd["vx"] = 380.0
                self.jump = None
            if kd["x"] > 1000 or kd["y"] > FLOOR_Y - kd["r"]:
                kd["y"] = min(kd["y"], FLOOR_Y - kd["r"])
        if getattr(self, "leap_at", None) is not None and self.t >= self.leap_at:
            self.leap_at = None
            self.leap(650.0)                     # un bond de joie : sa réaction tient dedans

    def snapshot(self):
        s = self.base_snap()
        s["kids"] = [(k["x"], k["y"], k["r"], k["col"]) for k in self.kids]
        s["rock"] = self.rock
        s["still"] = (self.t - self.still_t) if (self.still_t is not None and not self.back) else (None if self.still_t is None else -1.0)
        return s

    def solids(self, s):
        return [("rect", 300, self.SEAT, 500, self.SEAT + 24)]

    def focus(self, s):
        return (290.0, self.SEAT - 140, 530.0, 1450.0)        # le fauteuil, là où le petit lui tombe dessus

    def bodies(self, s):
        return [(k, x, y, 0.0) for k, (x, y, r, c) in enumerate(s["kids"])]

    def hero(self, s):
        return (s["bx"], s["by"], self.R)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        sky = (18, 22, 44)
        dr.rectangle([0, P(SCENE_TOP), P(self.W), P(FLOOR_Y)], fill=sky)
        for i in range(40):
            circle(dr, P((i * 7919 + 97) % self.W), P(450 + (i * 104729 + 11) % 600), P(2), (150, 155, 190))
        circle(dr, P(880), P(790), P(46), MOON)
        dr.rectangle([0, P(FLOOR_Y), P(self.W), P(self.H)], fill=(34, 52, 36))
        # la véranda : le mur de la maison, la fenêtre éclairée
        dr.rectangle([0, P(860), P(240), P(FLOOR_Y)], fill=(70, 56, 50))
        dr.rectangle([P(60), P(980), P(190), P(1140)], fill=(250, 214, 150))
        dr.rectangle([0, P(1440), P(560), P(FLOOR_Y)], fill=(100, 76, 58))
        # le rocking-chair
        a = 0.06 * s["rock"]
        wood = (130, 90, 58)
        cx, cy = 400.0, 1440.0
        def rot(x, y):
            return (P(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a)), P(cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)))
        dr.polygon([rot(300, self.SEAT), rot(500, self.SEAT), rot(500, self.SEAT + 24), rot(300, self.SEAT + 24)], fill=wood)
        dr.polygon([rot(480, self.SEAT), rot(500, self.SEAT), rot(520, 1060), rot(500, 1060)], fill=wood)
        dr.line([rot(300, 1440), rot(400, 1452), rot(520, 1440)], fill=dim(wood, 0.8), width=int(P(12)), joint="curve")
        for x in (320, 480):
            dr.polygon([rot(x, self.SEAT + 24), rot(x + 14, self.SEAT + 24), rot(x + 14, 1444), rot(x, 1444)], fill=dim(wood, 0.85))
        # sa canne, contre le fauteuil
        dr.line([(P(540), P(1440)), (P(570), P(1210))], fill=(180, 150, 110), width=int(P(9)))
        dr.arc([P(560), P(1190), P(610), P(1240)], 180, 360, fill=(180, 150, 110), width=int(P(9)))
        for (x, y, r, c) in s["kids"]:
            small_ball(dr, P, x, y, r, c)
        st = s["still"]
        if st is not None and st >= 0:
            f = base.font(int(P(46)))
            dr.text((P(470), P(640)), f"SITTING STILL: {st:0.1f}s", fill=(240, 240, 250), anchor="mm", font=f,
                    stroke_width=int(P(4)), stroke_fill=(10, 10, 14))
        self.bounce(dr, P, s)
        # les cheveux blancs et les lunettes du grand-père
        bx, by, R = s["bx"], s["by"], self.R
        for k in (-1, 0, 1):
            circle(dr, P(bx + k * 16), P(by - R + 4), P(10), (236, 236, 240))
        dr.arc([P(bx - 34), P(by - 22), P(bx - 6), P(by + 6)], 0, 360, fill=(30, 20, 30), width=int(P(4)))
        dr.arc([P(bx + 6), P(by - 22), P(bx + 34), P(by + 6)], 0, 360, fill=(30, 20, 30), width=int(P(4)))


DEFAULTS = {
    "ball_r": 60.0, "gravity": 1600.0,
    "chapter_max_s": 13.0,
    "counter_font_size": 84, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.4, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(DayOne, {}), (School, {}), (FirstLove, {}), (Apartment, {}), (Wedding, {}), (Dad, {}), (Old, {"chapter_max_s": 20.0})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
