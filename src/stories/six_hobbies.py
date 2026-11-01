"""
Liste : les six loisirs que Bounce a essayés. Six chapitres, six mécaniques physiques
différentes (une tour qui s'effondre, des pièces qui glissent, des oiseaux qui fuient,
une pose longue, un déraillement, de la peinture projetée). Le sixième retourne la
série : la peinture, où ne jamais s'arrêter devient la technique.

    python3 src/stories/six_hobbies.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, HOP, RED, GREEN, AMBER, FLOOR_Y, SCENE_TOP

R_BOUNCE = 68.0


def seg_poly(x0, y0, x1, y1, w):
    """Un segment épais en polygone (pour le dessin et pour solids)."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L * w / 2, dx / L * w / 2
    return [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]


# ---------------------------------------------------------------- 1. château de cartes
class CardHouse(Chapter):
    title = "1/6 · CARD HOUSE"
    stamp = ("COLLAPSED", RED)
    stamp_y = 0.36
    mood = "lose"
    hold_s = 1.6
    TX0, TX1, TOP = 560.0, 1020.0, 1180.0

    def setup(self):
        rng = self.rng
        self.hop_init(330.0, FLOOR_Y, wobble=60.0, xmin=250, xmax=420, **dict(HOP, start_h=380.0, min_h=320.0, max_h=430.0, gain=(0.95, 1.1)))
        self.line("Hobby one. Card house.", "title", 0.0)
        self.cards = []                     # segments (x0, y0, x1, y1, level)
        n, base_y, sp = 4, self.TOP, 100.0
        cx0 = (self.TX0 + self.TX1) / 2 - (n - 1) * sp / 2
        for lv in range(n):
            cnt = n - lv
            xs = [cx0 + lv * sp / 2 + k * sp for k in range(cnt)]
            top = base_y - 110
            for cx in xs:
                self.cards.append([cx - 36, base_y, cx, top, lv])
                self.cards.append([cx + 36, base_y, cx, top, lv])
            for a, b in zip(xs, xs[1:]):
                self.cards.append([a - 6, top - 3, b + 6, top - 3, lv])
            base_y = top - 6
        self.sway = 0.0
        self.need = int(rng.integers(4, 6))
        self.fall = None                    # corps des cartes en chute

    def on_land(self, k, evs):
        if self.fall is not None:
            return
        self.sway += 0.022 * k * self.rng.uniform(0.8, 1.2)
        if self.hits >= self.need:
            self.fall = []
            for (x0, y0, x1, y1, lv) in self.cards:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                L = math.hypot(x1 - x0, y1 - y0)
                ang = math.atan2(y1 - y0, x1 - x0)
                self.fall.append({"x": cx, "y": cy, "L": L, "a": ang, "vx": self.rng.uniform(-170, 170),
                                  "vy": self.rng.uniform(-260, 40), "w": self.rng.uniform(-7, 7), "rest": False})
            evs.append(("event", "cards fall t %.2f" % self.t))

    def ground(self, x):
        return self.TOP if self.TX0 < x < self.TX1 else FLOOR_Y

    def after(self, dt, evs):
        self.sway = max(0.0, self.sway - 0.004 * dt)
        if self.fall is not None:
            resting = 0
            for c in self.fall:
                if c["rest"]:
                    resting += 1
                    continue
                c["vy"] += self.g * 0.9 * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["w"] * dt
                low = c["y"] + abs(math.sin(c["a"])) * c["L"] / 2
                gy = self.ground(c["x"])
                if c["vy"] > 0 and low >= gy - 3:
                    c["y"] = gy - 4; c["a"] = 0.0 if math.cos(c["a"]) >= 0 else math.pi; c["rest"] = True
            if resting > 0.5 * len(self.fall) and not self.payoff:
                evs.append(("hit", "cards"))
                self.finish("COLLAPSED")
                self.line("Two hours of work.", "punch", self.t + 0.4)
        self.settle()

    def card_segments(self, s):
        segs = []
        if s["fall"] is None:
            sw = s["sway"]
            for (x0, y0, x1, y1, lv) in self.cards:
                off = sw * (lv + 1) * 60 * math.sin(s["t"] * 13 + lv)
                segs.append((x0 + off * (self.TOP - y0) / 440, y0, x1 + off * (self.TOP - y1) / 440, y1))
        else:
            for c in s["fall"]:
                dx, dy = math.cos(c["a"]) * c["L"] / 2, math.sin(c["a"]) * c["L"] / 2
                segs.append((c["x"] - dx, c["y"] - dy, c["x"] + dx, c["y"] + dy))
        return segs

    def snapshot(self):
        s = self.base_snap()
        s["sway"] = self.sway
        s["fall"] = [dict(c) for c in self.fall] if self.fall is not None else None
        return s

    def solids(self, s):
        sh = [("rect", self.TX0, self.TOP, self.TX1, self.TOP + 26),
              ("rect", self.TX0 + 20, self.TOP, self.TX0 + 44, FLOOR_Y), ("rect", self.TX1 - 44, self.TOP, self.TX1 - 20, FLOOR_Y)]
        for (x0, y0, x1, y1) in self.card_segments(s):
            sh.append(("poly", seg_poly(x0, y0, x1, y1, 10)))
        return sh

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 26, 38), (52, 40, 40))
        # lampe de table, tableau
        dr.rectangle([P(120), P(600), P(420), P(820)], fill=(52, 44, 60))
        dr.rectangle([P(140), P(620), P(400), P(800)], fill=(36, 56, 70))
        for k in range(3, 0, -1):
            circle(dr, P(980), P(760), P(60 + 50 * k), dim((255, 214, 150), 0.05 * (4 - k)))
        dr.polygon([(P(940), P(700)), (P(1020), P(700)), (P(1000), P(760)), (P(960), P(760))], fill=(200, 170, 110))
        dr.rectangle([P(976), P(760), P(984), P(1180)], fill=(90, 80, 70))
        # la table
        wood = (96, 66, 46)
        dr.rectangle([P(self.TX0), P(self.TOP), P(self.TX1), P(self.TOP + 26)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), P(self.TOP + 26), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        # les cartes
        for (x0, y0, x1, y1) in self.card_segments(s):
            dr.polygon([(P(x), P(y)) for x, y in seg_poly(x0, y0, x1, y1, 10)], fill=(232, 228, 236))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            circle(dr, P(mx), P(my), P(3), (200, 60, 70))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 2. échecs
class Chess(Chapter):
    title = "2/6 · CHESS"
    stamp = ("CHECKMATE", RED)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.7
    TX0, TX1, TOP = 120.0, 1000.0, 1200.0
    BX0, BX1 = 420.0, 880.0
    KING_X = 790.0

    def setup(self):
        rng = self.rng
        self.hop_init(250.0, self.TOP, wobble=50.0, xmin=200, xmax=300, **dict(HOP, start_h=300.0, min_h=260.0, max_h=340.0, gain=(0.95, 1.08)))
        self.line("Hobby two. Chess.", "title", 0.0)
        self.line("His opponent had not even moved yet.", "mid", 1.6)
        xs = [440, 485, 530, 575, 620, 665, 710, 745, 830, 860]
        self.pieces = []
        for k, x in enumerate(xs):
            king = abs(x - self.KING_X) < 1
            self.pieces.append({"x": float(x), "z": 0.0, "vz": 0.0, "vx": 0.0, "white": k % 2 == 0, "king": False,
                                "h": rng.uniform(46, 66), "st": "board", "y": self.TOP - 12, "vy": 0.0, "a": 0.0})
        self.pieces.append({"x": self.KING_X, "z": 0.0, "vz": 0.0, "vx": 0.0, "white": False, "king": True,
                            "h": 92.0, "st": "board", "y": self.TOP - 12, "vy": 0.0, "a": 0.0})
        self.nod = 0.0

    def on_land(self, k, evs):
        rng = self.rng
        for p in self.pieces:
            if p["king"] or p["st"] != "board":
                continue
            if p["z"] <= 0.5:
                p["vz"] = k * rng.uniform(150, 380)
                p["vx"] += k * rng.uniform(70, 180)

    def after(self, dt, evs):
        left = 0
        for p in self.pieces:
            if p["king"]:
                continue
            if p["st"] == "board":
                left += 1
                p["vz"] -= self.g * 0.8 * dt
                p["z"] = max(0.0, p["z"] + p["vz"] * dt)
                if p["z"] <= 0.0:
                    p["vz"] = 0.0
                    p["vx"] *= (1 - 2.2 * dt)
                p["x"] = max(self.BX0 - 10, p["x"] + p["vx"] * dt)
                if p["x"] > self.TX1 - 4:
                    p["st"] = "fall"; p["y"] = self.TOP - 12 - p["z"]; p["vy"] = -40.0
            elif p["st"] == "fall":
                p["vy"] += self.g * dt
                p["y"] += p["vy"] * dt; p["x"] += p["vx"] * 0.6 * dt; p["a"] += 6 * dt
                if p["y"] >= FLOOR_Y - 6:
                    p["y"] = FLOOR_Y - 6; p["st"] = "floor"; p["a"] = math.pi / 2
                    evs.append(("hit", "piece"))
        if left == 0 and not self.payoff:
            self.finish("CHECKMATE")
            self.nod = 1.0
            self.line("Checkmate. In zero moves.", "punch", self.t + 0.4)
        self.nod = max(0.0, self.nod - 1.5 * dt)
        self.settle()

    def snapshot(self):
        s = self.base_snap()
        s["pieces"] = [dict(p) for p in self.pieces]; s["nod"] = self.nod
        return s

    def solids(self, s):
        sh = [("rect", self.TX0, self.TOP, self.TX1, self.TOP + 30)]
        sh += self.figure_box(700, self.TOP + 10, h=230, w=104)
        for p in s["pieces"]:
            if p["st"] == "board":
                sh.append(("rect", p["x"] - 16, self.TOP - 12 - p["z"] - p["h"], p["x"] + 16, self.TOP - 12 - p["z"]))
        return sh

    def draw_piece(self, dr, P, x, y, h, white, king, a=0.0):
        col = (232, 228, 220) if white else (40, 38, 50)
        edge = (120, 118, 130)
        ca, sa = math.cos(a), math.sin(a)

        def T(dx, dy):
            return (P(x + dx * ca - dy * sa), P(y + dx * sa + dy * ca))
        dr.polygon([T(-18, 0), T(18, 0), T(10, -h * 0.6), T(-10, -h * 0.6)], fill=col, outline=edge)
        cx, cy = x + (-h * 0.75) * -sa, y + (-h * 0.75) * ca
        circle(dr, P(cx), P(cy), P(h * 0.18), col)
        if king:
            dr.line([T(0, -h * 0.95), T(0, -h * 1.2)], fill=col, width=int(P(6)))
            dr.line([T(-10, -h * 1.1), T(10, -h * 1.1)], fill=col, width=int(P(6)))

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (26, 30, 40), (44, 40, 46))
        for k in range(3, 0, -1):
            circle(dr, P(640), P(470), P(80 + 60 * k), dim((255, 220, 160), 0.04 * (4 - k)))
        dr.polygon([(P(600), P(440)), (P(680), P(440)), (P(720), P(520)), (P(560), P(520))], fill=(180, 150, 100))
        # l'adversaire, derrière la table
        self.figure(dr, P, 700, self.TOP + 10, (70, 76, 110), h=230, w=104, tilt=0.3 * s["nod"])
        # la table et l'échiquier
        wood = (92, 64, 46)
        dr.rectangle([P(self.TX0), P(self.TOP), P(self.TX1), P(self.TOP + 30)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), P(self.TOP + 30), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        for k in range(8):
            x = self.BX0 + k * (self.BX1 - self.BX0) / 8
            dr.rectangle([P(x), P(self.TOP - 12), P(x + (self.BX1 - self.BX0) / 8), P(self.TOP)], fill=(210, 200, 180) if k % 2 else (90, 70, 56))
        for p in s["pieces"]:
            if p["st"] == "board":
                self.draw_piece(dr, P, p["x"], self.TOP - 12 - p["z"], p["h"], p["white"], p["king"])
            else:
                self.draw_piece(dr, P, p["x"], p["y"], p["h"], p["white"], p["king"], p["a"])
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 3. observer les oiseaux
class Birds(Chapter):
    title = "3/6 · BIRD WATCHING"
    stamp = ("NO BIRDS", RED)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.7
    WIRE_Y = 780.0

    def setup(self):
        rng = self.rng
        self.hop_init(470.0, FLOOR_Y, wobble=150.0, xmin=260, xmax=760, **dict(HOP, start_h=320.0, min_h=280.0, max_h=420.0))
        self.line("Hobby three. Bird watching.", "title", 0.0)
        self.line("Birds do not like noise.", "mid", 1.8)
        self.birds = []
        for k in range(9):
            x = 120 + k * 105 + rng.uniform(-20, 20)
            self.birds.append({"x": x, "y": self.wire_y(x) - 18, "vx": 0.0, "vy": 0.0, "st": "sit", "flap": rng.uniform(0, 6)})
        self.reach = 150.0

    def wire_y(self, x):
        u = (x - 60) / (1020 - 60)
        return self.WIRE_Y + 70 * 4 * u * (1 - u)

    def on_land(self, k, evs):
        self.reach += 55 * k
        for b in self.birds:
            if b["st"] == "sit" and abs(b["x"] - self.bx) < self.reach:
                b["st"] = "fly"
                b["vx"] = (1 if b["x"] > self.bx else -1) * self.rng.uniform(220, 420)
                b["vy"] = -self.rng.uniform(320, 520)

    def after(self, dt, evs):
        sitting = 0
        for b in self.birds:
            b["flap"] += dt * 18
            if b["st"] == "sit":
                sitting += 1
            elif b["st"] == "fly":
                b["vy"] -= 120 * dt
                b["x"] += b["vx"] * dt; b["y"] += b["vy"] * dt
                if b["y"] < SCENE_TOP - 60 or b["x"] < -60 or b["x"] > self.W + 60:
                    b["st"] = "gone"
        if sitting == 0 and not self.payoff:
            self.finish("NO BIRDS")
            self.line("They found a quieter street.", "punch", self.t + 0.5)
        self.settle()

    def snapshot(self):
        s = self.base_snap(); s["birds"] = [dict(b) for b in self.birds]
        return s

    def solids(self, s):
        return [("rect", 50, 640, 74, FLOOR_Y), ("rect", 1006, 640, 1030, FLOOR_Y)]

    def bird(self, dr, P, x, y, flap, flying):
        col = (8, 8, 14)
        dr.ellipse([P(x - 22), P(y - 12), P(x + 22), P(y + 12)], fill=col)
        circle(dr, P(x + 18), P(y - 12), P(10), col)
        dr.polygon([(P(x + 26), P(y - 14)), (P(x + 38), P(y - 10)), (P(x + 26), P(y - 8))], fill=col)
        if flying:
            wy = 26 * math.sin(flap)
            dr.polygon([(P(x - 6), P(y - 4)), (P(x - 40), P(y - 20 - wy)), (P(x + 4), P(y - 8))], fill=col)
            dr.polygon([(P(x + 2), P(y - 4)), (P(x + 34), P(y - 22 + wy)), (P(x + 10), P(y - 8))], fill=col)
        else:
            dr.polygon([(P(x - 22), P(y)), (P(x - 40), P(y + 10)), (P(x - 20), P(y + 6))], fill=col)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        sky = (22, 28, 52)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(FLOOR_Y)], fill=sky)
        for k in range(4, 0, -1):
            circle(dr, P(820), P(560), P(50 + 40 * k), dim((150, 160, 200), 0.05 * (5 - k)))
        circle(dr, P(820), P(560), P(60), (226, 228, 236))
        for i in range(26):
            circle(dr, P((i * 7919 + 311) % W), P(450 + (i * 104729 + 97) % 520), P(2), (150, 155, 190))
        # toits au loin
        for (x0, w, h) in ((0, 220, 300), (230, 180, 240), (430, 260, 330), (720, 160, 260), (900, 200, 300)):
            dr.rectangle([P(x0), P(FLOOR_Y - h), P(x0 + w), P(FLOOR_Y)], fill=(14, 16, 30))
            for r in range(2):
                dr.rectangle([P(x0 + 30), P(FLOOR_Y - h + 40 + r * 90), P(x0 + 60), P(FLOOR_Y - h + 80 + r * 90)], fill=(60, 56, 40) if (x0 + r) % 3 else (130, 110, 60))
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(24, 40, 30))
        # poteaux et fil
        for x in (62, 1018):
            dr.rectangle([P(x - 12), P(640), P(x + 12), P(FLOOR_Y)], fill=(40, 34, 30))
            dr.rectangle([P(x - 40), P(660), P(x + 40), P(674)], fill=(40, 34, 30))
        pts = [(P(60 + k * 24), P(self.wire_y(60 + k * 24))) for k in range(41)]
        dr.line(pts, fill=(10, 10, 16), width=int(P(4)), joint="curve")
        for b in s["birds"]:
            if b["st"] != "gone":
                self.bird(dr, P, b["x"], b["y"], b["flap"], b["st"] == "fly")
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. photographie
class Photo(Chapter):
    title = "4/6 · PHOTOGRAPHY"
    stamp = ("BLURRY", RED)
    stamp_y = 0.56
    mood = "lose"
    hold_s = 1.6
    PR = (560.0, 540.0, 1000.0, 980.0)      # le tirage, en haut à droite

    def setup(self):
        self.hop_init(360.0, FLOOR_Y, wobble=130.0, xmin=230, xmax=470, **dict(HOP, start_h=300.0, min_h=240.0, max_h=430.0))
        self.line("Hobby four. Photography.", "title", 0.0)
        self.line("The photographer said: hold still.", "ask", 1.7)
        self.reply("ask", 0.35)
        c = self.cfg
        self.exp0, self.exp1 = c["photo_exp0"], c["photo_exp0"] + 2.6
        self.trail = []
        self.flash = None
        self.print_t = None

    def on_land(self, k, evs):
        if self.print_t is not None and self.t - self.print_t > 0.5 and not self.payoff:
            self.on = "still"
            self.finish("BLURRY")
            self.line("This was the sharpest one.", "punch", self.t + 0.4)

    def after(self, dt, evs):
        if self.exp0 <= self.t <= self.exp1:
            if self.flash is None:
                self.flash = self.t
            self.trail.append((self.bx, self.by))
        if self.t > self.exp1 + 0.3 and self.print_t is None:
            self.print_t = self.t
            evs.append(("event", "print t %.2f" % self.t))

    def snapshot(self):
        s = self.base_snap()
        s["trail"] = list(self.trail); s["flash"] = self.flash; s["print_t"] = self.print_t
        return s

    def solids(self, s):
        return [("rect", 800, 1100, 930, FLOOR_Y)] + self.figure_box(1000, FLOOR_Y, h=250, w=92)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        self.room(dr, P, (24, 22, 32), (40, 36, 44))
        # le fond de studio
        dr.rectangle([P(120), P(560), P(640), FLOOR_Y * S], fill=(46, 44, 60))
        dr.rectangle([P(110), P(540), P(650), P(570)], fill=(70, 66, 80))
        # la boîte à lumière
        dr.polygon([(P(40), P(700)), (P(150), P(660)), (P(150), P(860)), (P(40), P(820))], fill=(200, 196, 210))
        dr.rectangle([P(80), P(820), P(92), P(FLOOR_Y)], fill=(60, 60, 70))
        # l'appareil sur son trépied, le photographe
        dr.line([(P(865), P(1180)), (P(810), P(FLOOR_Y))], fill=(80, 80, 90), width=int(P(8)))
        dr.line([(P(865), P(1180)), (P(920), P(FLOOR_Y))], fill=(80, 80, 90), width=int(P(8)))
        dr.line([(P(865), P(1180)), (P(865), P(FLOOR_Y))], fill=(80, 80, 90), width=int(P(8)))
        dr.rectangle([P(820), P(1110), P(915), P(1180)], fill=(30, 30, 36))
        dr.rectangle([P(790), P(1125), P(822), P(1165)], fill=(60, 60, 70))
        circle(dr, P(790), P(1145), P(16), (110, 140, 190))
        self.figure(dr, P, 1000, FLOOR_Y, (70, 80, 100), h=250, w=92)
        self.bounce(dr, P, s)
        # le flash
        if s["flash"] is not None and 0 <= t - s["flash"] < 0.18:
            k = 1 - (t - s["flash"]) / 0.18
            dr.rectangle([0, P(SCENE_TOP), P(W), P(FLOOR_Y)], fill=tuple(int(40 + 180 * k) for _ in range(3)))
            self.bounce(dr, P, s)
        # le tirage
        if s["print_t"] is not None:
            u = min(1.0, (t - s["print_t"]) / 0.5)
            x0, y0, x1, y1 = self.PR
            yo = (1 - u) * 300
            dr.rectangle([P(x0), P(y0 + yo), P(x1), P(y1 + yo)], fill=(236, 232, 224))
            ix0, iy0, ix1, iy1 = x0 + 24, y0 + 24 + yo, x1 - 24, y1 - 70 + yo
            dr.rectangle([P(ix0), P(iy0), P(ix1), P(iy1)], fill=(20, 18, 28))
            tr = s["trail"]
            if len(tr) > 2:
                pts = []
                for (bx, by) in tr:
                    px = ix0 + (bx - 120) / (660 - 120) * (ix1 - ix0)
                    py = iy0 + (by - 760) / (FLOOR_Y - 760) * (iy1 - iy0)
                    pts.append((P(px), P(py)))
                dr.line(pts, fill=dim((255, 20, 200), 0.35), width=int(P(30)), joint="curve")
                dr.line(pts, fill=(255, 40, 210), width=int(P(14)), joint="curve")


# ---------------------------------------------------------------- 5. train miniature
class Train(Chapter):
    title = "5/6 · MODEL TRAINS"
    stamp = ("DERAILED", RED)
    stamp_y = 0.36
    mood = "lose"
    hold_s = 1.7
    TX0, TX1, TOP = 420.0, 1040.0, 1180.0
    RAIL0, RAIL1 = 470.0, 990.0

    def setup(self):
        rng = self.rng
        self.hop_init(230.0, FLOOR_Y, wobble=60.0, xmin=160, xmax=290, **dict(HOP, start_h=330.0, min_h=280.0, max_h=430.0))
        self.line("Hobby five. Model trains.", "title", 0.0)
        self.line("The trains ran perfectly on time.", "mid", 1.6)
        self.tx = 760.0; self.tv = -150.0          # position de la locomotive, vitesse
        self.hop = 0.0; self.hv = 0.0
        self.need = int(rng.integers(7, 9))
        self.fall = None

    def cars(self):
        d = 1 if self.tv > 0 else -1
        return [self.tx - d * k * 96 for k in range(3)]

    def on_land(self, k, evs):
        if self.fall is not None:
            return
        self.hv = -(30 + 22 * self.hits) * k * 6
        if self.hits >= self.need and 560 < self.tx < 900:
            self.fall = []
            for k2, x in enumerate(self.cars()):
                self.fall.append({"x": x, "y": self.TOP - 30 - self.hop, "vx": self.tv * 0.6 + self.rng.uniform(-60, 60),
                                  "vy": -self.rng.uniform(200, 380), "a": 0.0, "w": self.rng.uniform(-5, 5), "rest": False, "eng": k2 == 0})
            evs.append(("event", "derail t %.2f" % self.t))

    def after(self, dt, evs):
        if self.fall is None:
            self.tx += self.tv * dt
            head = self.cars()
            if max(head) > self.RAIL1 - 45 and self.tv > 0:
                self.tv = -abs(self.tv)
            if min(head) < self.RAIL0 + 45 and self.tv < 0:
                self.tv = abs(self.tv)
            self.hv += self.g * 0.9 * dt
            self.hop = min(0.0, self.hop + self.hv * dt) if self.hop < 0 or self.hv < 0 else 0.0
            if self.hop >= 0:
                self.hop, self.hv = 0.0, 0.0
        else:
            rest = 0
            for c in self.fall:
                if c["rest"]:
                    rest += 1; continue
                c["vy"] += self.g * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["w"] * dt
                gy = FLOOR_Y if c["y"] > self.TOP + 10 or not (self.TX0 < c["x"] < self.TX1) else self.TOP
                if c["vy"] > 0 and c["y"] + 26 >= FLOOR_Y:
                    c["y"] = FLOOR_Y - 26; c["vy"] = 0.0; c["rest"] = True
                    c["a"] = round(c["a"] / (math.pi / 2)) * (math.pi / 2)
            if rest == len(self.fall) and not self.payoff:
                evs.append(("hit", "train"))
                self.finish("DERAILED")
                self.line("Next stop: the floor.", "punch", self.t + 0.4)
        self.settle()

    def snapshot(self):
        s = self.base_snap()
        s["cars"] = self.cars(); s["hop"] = self.hop; s["dir"] = 1 if self.tv > 0 else -1
        s["fall"] = [dict(c) for c in self.fall] if self.fall is not None else None
        return s

    def solids(self, s):
        sh = [("rect", self.TX0, self.TOP, self.TX1, self.TOP + 26)]
        if s["fall"] is None:
            for x in s["cars"]:
                sh.append(("rect", x - 44, self.TOP - 56 + s["hop"], x + 44, self.TOP + s["hop"]))
        else:
            for c in s["fall"]:
                sh.append(("circle", c["x"], c["y"], 40))
        return sh

    def car(self, dr, P, x, y, a, eng, d):
        ca, sa = math.cos(a), math.sin(a)

        def T(dx, dy):
            return (P(x + dx * ca - dy * sa), P(y + dx * sa + dy * ca))
        col = (190, 50, 60) if eng else (50, 90, 160)
        dr.polygon([T(-44, -26), T(44, -26), T(44, 18), T(-44, 18)], fill=col)
        if eng:
            dr.polygon([T(d * 10, -26), T(d * 30, -26), T(d * 30, -48), T(d * 10, -48)], fill=(40, 40, 46))
            dr.polygon([T(-d * 40, -26), T(-d * 6, -26), T(-d * 6, -40), T(-d * 40, -40)], fill=dim(col, 0.8))
        else:
            for wx in (-24, 4):
                dr.polygon([T(wx, -18), T(wx + 18, -18), T(wx + 18, -2), T(wx, -2)], fill=(255, 220, 140))
        for wx in (-26, 26):
            circle(dr, *T(wx, 22), P(10), (30, 30, 34))

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 28, 44), (48, 38, 40))
        dr.rectangle([P(80), P(560), P(360), P(860)], fill=(16, 18, 34))
        circle(dr, P(260), P(640), P(36), (220, 222, 232)); circle(dr, P(276), P(630), P(32), (16, 18, 34))
        dr.rectangle([P(216), P(560), P(224), P(860)], fill=(50, 44, 60)); dr.rectangle([P(80), P(706), P(360), P(714)], fill=(50, 44, 60))
        wood = (92, 64, 46)
        dr.rectangle([P(self.TX0), P(self.TOP), P(self.TX1), P(self.TOP + 26)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), P(self.TOP + 26), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        # les rails et les butoirs
        dr.rectangle([P(self.RAIL0), P(self.TOP - 6), P(self.RAIL1), P(self.TOP)], fill=(150, 150, 160))
        for x in range(int(self.RAIL0), int(self.RAIL1), 30):
            dr.rectangle([P(x), P(self.TOP - 4), P(x + 14), P(self.TOP)], fill=(70, 50, 40))
        for x in (self.RAIL0 - 10, self.RAIL1 - 6):
            dr.rectangle([P(x), P(self.TOP - 30), P(x + 16), P(self.TOP)], fill=(200, 160, 60))
        if s["fall"] is None:
            for k, x in enumerate(s["cars"]):
                self.car(dr, P, x, self.TOP - 30 + s["hop"], 0.0, k == 0, s["dir"])
        else:
            for c in s["fall"]:
                self.car(dr, P, c["x"], c["y"], c["a"], c["eng"], s["dir"])
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 6. peinture
class Painting(Chapter):
    title = "6/6 · PAINTING"
    stamp = ("MASTERPIECE", GREEN)
    stamp_y = 0.30
    mood = "win"
    hold_s = 3.8
    CV = (560.0, 720.0, 1000.0, 1180.0)
    PUDDLES = ((220.0, (220, 60, 70)), (340.0, (240, 200, 70)), (460.0, (70, 130, 220)))

    def setup(self):
        self.hop_init(340.0, FLOOR_Y, wobble=110.0, xmin=200, xmax=480, **dict(HOP, start_h=300.0, min_h=260.0, max_h=430.0))
        self.line("Hobby six. Painting.", "title", 0.0)
        self.line("Every landing splashed the paint.", "mid", 1.6)
        self.drops = []
        self.splats = []
        self.need = self.cfg["paint_splats"]
        self.critic = 1200.0
        self.nod = 0.0

    def on_land(self, k, evs):
        col = min(self.PUDDLES, key=lambda p: abs(p[0] - self.bx))[1]
        x0, y0, x1, y1 = self.CV
        for _ in range(int(9 + 6 * k)):
            tx = self.rng.uniform(x0 + 20, x1 - 20); ty = self.rng.uniform(y0 + 20, y1 - 20)
            T = self.rng.uniform(0.45, 0.7)
            vx = (tx - self.bx) / T
            vy = (ty - (FLOOR_Y - 10) - 0.5 * self.g * 0.8 * T * T) / T
            self.drops.append({"x": self.bx, "y": FLOOR_Y - 10, "vx": vx, "vy": vy, "c": col, "r": self.rng.uniform(7, 16),
                               "tx": tx, "ty": ty, "T": T, "age": 0.0})

    def after(self, dt, evs):
        keep = []
        for d in self.drops:
            d["age"] += dt
            d["vy"] += self.g * 0.8 * dt
            d["x"] += d["vx"] * dt; d["y"] += d["vy"] * dt
            if d["age"] >= d["T"]:
                self.splats.append((d["tx"], d["ty"], d["r"] * self.rng.uniform(1.4, 2.4), d["c"]))
            else:
                keep.append(d)
        self.drops = keep
        if len(self.splats) >= self.need and not self.payoff:
            self.finish("MASTERPIECE")
            self.line("A museum hung it the next day.", "punch", self.t + 0.4)
            self.line("Finally, a hobby.", "end", self.t + 2.6)
        if self.payoff:
            self.critic = max(1010.0, self.critic - 300 * dt)
            self.nod = 0.5 + 0.5 * math.sin(self.t * 5)

    def snapshot(self):
        s = self.base_snap()
        s["drops"] = [(d["x"], d["y"], d["r"], d["c"]) for d in self.drops]
        s["splats"] = list(self.splats); s["critic"] = self.critic; s["nod"] = self.nod
        return s

    def solids(self, s):
        x0, y0, x1, y1 = self.CV
        return [("rect", x0 - 20, y0 - 20, x1 + 20, y1 + 20), ("rect", 600, y1, 624, FLOOR_Y), ("rect", 936, y1, 960, FLOOR_Y)]

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 28, 36), (54, 48, 52))
        x0, y0, x1, y1 = self.CV
        ended = s["end"] is not None
        if ended:
            k = min(1.0, (t - s["end"]) / 0.4)
            dr.polygon([(P(740), P(SCENE_TOP)), (P(820), P(SCENE_TOP)), (P(x1 + 60), P(FLOOR_Y)), (P(x0 - 60), P(FLOOR_Y))], fill=dim((255, 236, 190), 0.10 * k))
        # le chevalet
        dr.line([(P(612), P(y1)), (P(590), P(FLOOR_Y))], fill=(110, 80, 56), width=int(P(14)))
        dr.line([(P(948), P(y1)), (P(970), P(FLOOR_Y))], fill=(110, 80, 56), width=int(P(14)))
        dr.rectangle([P(x0 - 10), P(y1), P(x1 + 10), P(y1 + 16)], fill=(110, 80, 56))
        # la toile
        if ended:
            dr.rectangle([P(x0 - 22), P(y0 - 22), P(x1 + 22), P(y1 + 22)], fill=(200, 160, 70))
        dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(222, 218, 210))
        for (x, y, r, c) in s["splats"]:
            circle(dr, P(x), P(y), P(r), c)
        # les flaques
        for (px, c) in self.PUDDLES:
            dr.ellipse([P(px - 60), P(FLOOR_Y - 8), P(px + 60), P(FLOOR_Y + 14)], fill=dim(c, 0.85))
        for (x, y, r, c) in s["drops"]:
            circle(dr, P(x), P(y), P(r * 0.6), c)
        if s["critic"] < 1150:
            self.figure(dr, P, s["critic"], FLOOR_Y, (60, 64, 90), h=260, w=96, tilt=0.3 * s["nod"])
        self.bounce(dr, P, s)


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": 3000.0,
    "photo_exp0": 4.7, "paint_splats": 150,
    "chapter_max_s": 14.0,
    "counter_font_size": 54, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 0.6, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(CardHouse, {}), (Chess, {}), (Birds, {}), (Photo, {}), (Train, {}), (Painting, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
