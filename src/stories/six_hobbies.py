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
from listkit import Chapter, HOP, RED, GREEN, AMBER, FLOOR_Y, SCENE_TOP, glow, mix, settle_body

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
    stamp_y = 0.33
    mood = "lose"
    hold_s = 1.7
    TX0, TX1, TOP = 500.0, 900.0, 1180.0

    def setup(self):
        rng = self.rng
        self.hop_init(320.0, FLOOR_Y, wobble=120.0, xmin=200, xmax=400, **dict(HOP, start_h=420.0, min_h=340.0, max_h=460.0, gain=(0.95, 1.1)))
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
        self.sway = 0.05                    # la tour tremble dès l'image 0 : elle est déjà menacée
        self.need = int(rng.integers(4, 6))
        self.fall = None                    # corps des cartes en chute
        self.heap = {}

    def on_land(self, k, evs):
        if self.fall is not None:
            return
        self.sway += 0.022 * k * self.rng.uniform(0.8, 1.2)
        if self.hits >= self.need:
            self.fall = []
            for (x0, y0, x1, y1) in self.card_segments({"fall": None, "sway": self.sway, "t": self.t}):
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                self.fall.append({"x": cx, "y": cy, "L": math.hypot(x1 - x0, y1 - y0), "a": math.atan2(y1 - y0, x1 - x0),
                                  "vx": self.rng.uniform(-80, 80) - 0.8 * (cx - 700), "vy": self.rng.uniform(-240, -20),
                                  "w": self.rng.uniform(-5, 5), "rest": False})
            evs.append(("event", "cards fall t %.2f" % self.t))

    def ground(self, c):
        x = c["x"]
        if self.TX0 < x < self.TX1:
            return self.TOP - self.heap.get(int(x // 40), 0.0)
        return FLOOR_Y

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
                if c["x"] < 30 or c["x"] > 1040:
                    c["vx"] = -c["vx"] * 0.5; c["x"] = min(1040, max(30, c["x"]))
                L2 = c["L"] / 2
                if settle_body(c, self.ground(c), math.pi, dt, [(-L2, -5), (L2, -5), (L2, 5), (-L2, 5)]) and c["rest"]:
                    b = int(c["x"] // 40)
                    if self.TX0 < c["x"] < self.TX1:
                        self.heap[b] = self.heap.get(b, 0.0) + 7.0
            if resting > 0.6 * len(self.fall) and not self.payoff:
                self.finish("COLLAPSED")
                self.line("Two hours to build. Five seconds to fall.", "punch", self.t + 1.4)

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

    def focus(self, s):
        segs = self.card_segments(s)
        xs = [v for (x0, y0, x1, y1) in segs for v in (x0, x1)]
        ys = [v for (x0, y0, x1, y1) in segs for v in (y0, y1)]
        return (min(xs), min(ys), max(xs), max(ys))

    def bodies(self, s):
        return [(k, (x0 + x1) / 2, (y0 + y1) / 2, math.atan2(y1 - y0, x1 - x0)) for k, (x0, y0, x1, y1) in enumerate(self.card_segments(s))]

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (30, 26, 38)
        self.room(dr, P, wall, (52, 40, 40))
        dr.rectangle([P(120), P(600), P(420), P(820)], fill=(52, 44, 60))
        dr.rectangle([P(140), P(620), P(400), P(800)], fill=(36, 56, 70))
        glow(dr, P, 970, 730, 170, (255, 214, 150), wall, 0.22)
        dr.polygon([(P(930), P(670)), (P(1010), P(670)), (P(990), P(730)), (P(950), P(730))], fill=(200, 170, 110))
        dr.rectangle([P(966), P(730), P(974), P(FLOOR_Y)], fill=(90, 80, 70))
        wood = (96, 66, 46)
        dr.rectangle([P(self.TX0), P(self.TOP), P(self.TX1), P(self.TOP + 26)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), P(self.TOP + 26), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        for (x0, y0, x1, y1) in self.card_segments(s):
            dr.polygon([(P(x), P(y)) for x, y in seg_poly(x0, y0, x1, y1, 10)], fill=(232, 228, 236))
            circle(dr, P((x0 + x1) / 2), P((y0 + y1) / 2), P(3), (200, 60, 70))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 2. échecs
class Chess(Chapter):
    title = "2/6 · CHESS"
    stamp = ("CHECKMATE", RED)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.8
    TX0, TX1, TOP = 120.0, 900.0, 1200.0
    BX0, BX1 = 380.0, 860.0
    KX = 470.0                               # son roi, le blanc, côté Bounce

    def setup(self):
        rng = self.rng
        self.hop_init(240.0, self.TOP, wobble=50.0, xmin=200, xmax=280, **dict(HOP, start_h=300.0, min_h=260.0, max_h=340.0, gain=(0.95, 1.08)))
        self.line("Hobby two. Chess.", "title", 0.0)
        self.line("His opponent had not even moved yet.", "mid", 1.4)
        self.pieces = []
        for k, x in enumerate([720.0, 778.0]):
            white = k == 0
            self.pieces.append({"id": "p%d" % k, "x": float(x), "z": 0.0, "vz": 0.0, "vx": 0.0, "white": white,
                                "h": rng.uniform(76, 96), "king": False})
        self.pieces.append({"id": "bk", "x": 836.0, "z": 0.0, "vz": 0.0, "vx": 0.0, "white": False, "h": 124.0, "king": True})
        self.ka, self.kw = 0.0, 0.0          # angle du roi blanc, vitesse angulaire (> 0 : vers la droite)
        self.kfall = False
        self.nod = 0.0

    def on_land(self, k, evs):
        rng = self.rng
        for p in self.pieces:
            if p["z"] <= 0.5:
                p["vz"] = k * rng.uniform(90, 200) * (0.5 if p["king"] else 1.0)
                p["vx"] += k * rng.uniform(-35, 45)
        if not self.kfall:
            self.kw += k * (1.0 + 0.36 * self.hits) * rng.uniform(0.85, 1.15)

    def after(self, dt, evs):
        for p in self.pieces:
            p["vz"] -= self.g * 0.8 * dt
            p["z"] = max(0.0, p["z"] + p["vz"] * dt)
            if p["z"] <= 0.0:
                p["vz"] = 0.0
                p["vx"] *= max(0.0, 1 - 4.0 * dt)
            p["x"] += p["vx"] * dt
        # les pièces restent sur l'échiquier et ne se traversent pas
        ps = sorted(self.pieces, key=lambda p: p["x"])
        lo = self.KX + 225
        for p in ps:
            if p["x"] < lo:
                p["x"] = lo; p["vx"] = abs(p["vx"]) * 0.3
            lo = p["x"] + 54
        hi = self.BX1 - 26
        for p in reversed(ps):
            if p["x"] > hi:
                p["x"] = hi; p["vx"] = -abs(p["vx"]) * 0.3
            hi = p["x"] - 54
        # le roi blanc : un ressort tant qu'il tient, la gravité quand il penche trop
        if not self.kfall:
            self.kw += (-38.0 * self.ka - 2.5 * self.kw) * dt
            self.ka += self.kw * dt
            if self.ka > 0.42:
                self.kfall = True
                evs.append(("event", "king falls t %.2f" % self.t))
        else:
            self.kw += 14.0 * math.sin(self.ka) * dt
            self.ka += self.kw * dt
            if self.ka >= math.pi / 2:
                self.ka, self.kw = math.pi / 2, 0.0
                if not self.payoff:
                    self.finish("CHECKMATE")
                    self.nod = 1.0
                    self.line("Lost in zero moves.", "punch", self.t + 0.9)
        if self.payoff:
            self.nod = 0.5 + 0.5 * math.sin(self.t * 6)

    def king_poly(self, a, h=110.0):
        """Le roi blanc, pivotant sur le coin droit de sa base."""
        px, py = self.KX + 24, self.TOP - 12
        pts = [(-48, 0), (0, 0), (-10, -h), (-38, -h)]
        ca, sa = math.cos(a), math.sin(a)
        return [(px + dx * ca - dy * sa, py + dx * sa + dy * ca) for dx, dy in pts]

    def snapshot(self):
        s = self.base_snap()
        s["pieces"] = [dict(p) for p in self.pieces]; s["ka"] = self.ka; s["nod"] = self.nod
        return s

    def solids(self, s):
        sh = [("rect", self.TX0, self.TOP, self.TX1, self.TOP + 30), ("poly", self.king_poly(s["ka"]))]
        sh += self.figure_box(640, self.TOP + 10, h=230, w=104)
        for p in s["pieces"]:
            sh.append(("rect", p["x"] - 24, self.TOP - 12 - p["z"] - p["h"], p["x"] + 24, self.TOP - 12 - p["z"]))
        return sh

    def focus(self, s):
        pts = self.king_poly(s["ka"])
        return (min(x for x, y in pts) - 10, min(y for x, y in pts) - 40, max(x for x, y in pts) + 40, max(y for x, y in pts))

    def bodies(self, s):
        out = [(p["id"], p["x"], self.TOP - 12 - p["z"], 0.0) for p in s["pieces"]]
        return out + [("wk", self.KX, self.TOP - 60, s["ka"])]

    def draw_piece(self, dr, P, x, y, h, white, king):
        col = (236, 230, 220) if white else (48, 44, 58)
        edge = (60, 56, 66) if white else (200, 192, 176)
        dr.polygon([(P(x - 24), P(y)), (P(x + 24), P(y)), (P(x + 13), P(y - h * 0.62)), (P(x - 13), P(y - h * 0.62))], fill=col, outline=edge, width=max(1, int(P(3))))
        circle(dr, P(x), P(y - h * 0.76), P(h * 0.17 + 2), edge)
        circle(dr, P(x), P(y - h * 0.76), P(h * 0.17), col)
        if king:
            dr.line([(P(x), P(y - h * 0.94)), (P(x), P(y - h * 1.18))], fill=edge, width=int(P(8)))
            dr.line([(P(x - 12), P(y - h * 1.07)), (P(x + 12), P(y - h * 1.07))], fill=edge, width=int(P(8)))

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (26, 30, 40)
        self.room(dr, P, wall, (44, 40, 46))
        glow(dr, P, 640, 480, 230, (255, 220, 160), wall, 0.2)
        dr.rectangle([P(637), P(SCENE_TOP), P(643), P(440)], fill=(70, 66, 76))
        dr.polygon([(P(600), P(440)), (P(680), P(440)), (P(720), P(520)), (P(560), P(520))], fill=(180, 150, 100))
        self.figure(dr, P, 640, self.TOP + 10, (70, 76, 110), h=230, w=104, tilt=0.4 * s["nod"])
        wood = (92, 64, 46)
        dr.rectangle([P(self.TX0), P(self.TOP), P(self.TX1), P(self.TOP + 30)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), P(self.TOP + 30), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        for k in range(8):
            x = self.BX0 + k * (self.BX1 - self.BX0) / 8
            dr.rectangle([P(x), P(self.TOP - 12), P(x + (self.BX1 - self.BX0) / 8), P(self.TOP)], fill=(210, 200, 180) if k % 2 else (90, 70, 56))
        for p in s["pieces"]:
            self.draw_piece(dr, P, p["x"], self.TOP - 12 - p["z"], p["h"], p["white"], p["king"])
        # le roi blanc
        pts = self.king_poly(s["ka"])
        dr.polygon([(P(x), P(y)) for x, y in pts], fill=(240, 234, 222), outline=(60, 56, 66), width=max(1, int(P(3))))
        ax, ay = (pts[2][0] + pts[3][0]) / 2, (pts[2][1] + pts[3][1]) / 2
        ca, sa = math.cos(s["ka"]), math.sin(s["ka"])
        hx, hy = ax + 18 * sa, ay - 18 * ca
        circle(dr, P(hx), P(hy), P(24), (60, 56, 66)); circle(dr, P(hx), P(hy), P(21), (240, 234, 222))
        cx, cy = hx + 30 * sa, hy - 30 * ca
        dr.line([(P(hx + 20 * sa), P(hy - 20 * ca)), (P(hx + 52 * sa), P(hy - 52 * ca))], fill=(240, 234, 222), width=int(P(9)))
        dr.line([(P(cx - 13 * ca), P(cy - 13 * sa)), (P(cx + 13 * ca), P(cy + 13 * sa))], fill=(240, 234, 222), width=int(P(9)))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 3. observer les oiseaux
class Birds(Chapter):
    title = "3/6 · BIRD WATCHING"
    stamp = ("NO BIRDS", RED)
    stamp_y = 0.30
    mood = "lose"
    hold_s = 1.8
    WIRE_Y = 800.0
    bodies_exit_ok = True                    # partir hors champ, c'est la chute

    def setup(self):
        rng = self.rng
        self.hop_init(480.0, FLOOR_Y, wobble=150.0, xmin=280, xmax=700, **dict(HOP, start_h=320.0, min_h=280.0, max_h=420.0))
        self.line("Hobby three. Bird watching.", "title", 0.0)
        self.line("He sat very still. Mostly.", "mid", 1.4)
        self.birds = []
        for k in range(7):
            x = 170 + k * 108 + rng.uniform(-14, 14)
            self.birds.append({"id": k, "x": x, "y": self.wire_y(x) - 17, "vx": 0.0, "vy": 0.0, "st": "sit", "flap": rng.uniform(0, 6)})
        self.reach = 70.0

    def wire_y(self, x):
        u = (x - 100) / (900 - 100)
        return self.WIRE_Y + 60 * 4 * u * (1 - u)

    def on_land(self, k, evs):
        self.reach += 44 * k
        for b in self.birds:
            if b["st"] == "sit" and abs(b["x"] - self.bx) < self.reach:
                b["st"] = "fly"
                b["vx"] = (1 if b["x"] > self.bx else -1) * self.rng.uniform(160, 300)
                b["vy"] = -self.rng.uniform(420, 600)

    def after(self, dt, evs):
        sitting = 0
        for b in self.birds:
            b["flap"] += dt * 18
            if b["st"] == "sit":
                sitting += 1
            elif b["st"] == "fly":
                b["vy"] -= 160 * dt
                b["x"] += b["vx"] * dt; b["y"] += b["vy"] * dt
                if b["y"] < -70 or b["x"] < -80 or b["x"] > self.W + 80:
                    b["st"] = "gone"
        if sitting == 0 and not self.payoff:
            self.finish("NO BIRDS")
            self.line("They found a quieter street.", "punch", self.t + 0.9)

    def snapshot(self):
        s = self.base_snap(); s["birds"] = [dict(b) for b in self.birds]
        return s

    def solids(self, s):
        return [("rect", 88, 660, 112, FLOOR_Y), ("rect", 888, 660, 912, FLOOR_Y)]

    def focus(self, s):
        return (100.0, self.WIRE_Y - 60, 900.0, self.WIRE_Y + 80)

    def bodies(self, s):
        return [(b["id"], b["x"], b["y"], 0.0) for b in s["birds"] if b["st"] != "gone"]

    def bird(self, dr, P, x, y, flap, flying):
        body, wing = (214, 216, 226), (150, 154, 172)
        dr.ellipse([P(x - 30), P(y - 16), P(x + 30), P(y + 16)], fill=body)
        circle(dr, P(x + 24), P(y - 16), P(13), body)
        dr.polygon([(P(x + 35), P(y - 19)), (P(x + 50), P(y - 14)), (P(x + 35), P(y - 10))], fill=(240, 180, 80))
        if flying:
            wy = 34 * math.sin(flap)
            dr.polygon([(P(x - 8), P(y - 6)), (P(x - 54), P(y - 28 - wy)), (P(x + 6), P(y - 10))], fill=wing)
            dr.polygon([(P(x + 2), P(y - 6)), (P(x + 46), P(y - 30 + wy)), (P(x + 14), P(y - 10))], fill=wing)
        else:
            dr.polygon([(P(x - 30), P(y)), (P(x - 54), P(y + 12)), (P(x - 26), P(y + 8))], fill=wing)

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        sky = (22, 28, 52)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(FLOOR_Y)], fill=sky)
        glow(dr, P, 170, 1010, 150, (190, 200, 235), sky, 0.25)
        circle(dr, P(170), P(1010), P(52), (226, 228, 236))
        for i in range(26):
            circle(dr, P((i * 7919 + 311) % W), P(450 + (i * 104729 + 97) % 520), P(2), (150, 155, 190))
        for (x0, w, h) in ((0, 220, 300), (230, 180, 240), (430, 260, 330), (720, 160, 260), (900, 200, 300)):
            dr.rectangle([P(x0), P(FLOOR_Y - h), P(x0 + w), P(FLOOR_Y)], fill=(14, 16, 30))
            for r in range(2):
                dr.rectangle([P(x0 + 30), P(FLOOR_Y - h + 40 + r * 90), P(x0 + 60), P(FLOOR_Y - h + 80 + r * 90)], fill=(60, 56, 40) if (x0 + r) % 3 else (130, 110, 60))
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(24, 40, 30))
        for x in (100, 900):
            dr.rectangle([P(x - 12), P(660), P(x + 12), P(FLOOR_Y)], fill=(70, 58, 50))
            dr.rectangle([P(x - 40), P(680), P(x + 40), P(694)], fill=(70, 58, 50))
        pts = [(P(100 + k * 20), P(self.wire_y(100 + k * 20))) for k in range(41)]
        dr.line(pts, fill=(120, 116, 130), width=int(P(5)), joint="curve")
        for b in s["birds"]:
            if b["st"] != "gone":
                self.bird(dr, P, b["x"], b["y"], b["flap"], b["st"] == "fly")
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. photographie
class Photo(Chapter):
    title = "4/6 · PHOTOGRAPHY"
    stamp = ("BLURRY", RED)
    stamp_y = 0.265
    mood = "lose"
    hold_s = 1.7
    PR = (480.0, 600.0, 880.0, 1000.0)      # le tirage

    def setup(self):
        self.hop_init(350.0, FLOOR_Y, wobble=120.0, xmin=230, xmax=460, **dict(HOP, start_h=300.0, min_h=240.0, max_h=430.0))
        self.line("Hobby four. Photography.", "title", 0.0)
        self.line("The photographer asked: can you hold still?", "ask", 1.4)
        self.reply("ask", 0.35)
        c = self.cfg
        self.exp0, self.exp1 = c["photo_exp0"], c["photo_exp0"] + c["photo_exp_s"]
        self.trail = []
        self.flash = None
        self.print_t = None
        self._cache = None

    def on_land(self, k, evs):
        if self.print_t is not None and self.t - self.print_t > 0.7 and not self.payoff:
            self.min_h, self.max_h, self.h = 150.0, 200.0, 180.0     # il continue, sous le tampon
            self.finish("BLURRY")
            self.line("This was the sharpest one.", "punch", self.t + 0.9)

    def after(self, dt, evs):
        if self.exp0 <= self.t <= self.exp1:
            if self.flash is None:
                self.flash = self.t
            self.trail.append((self.bx, self.by))
        if self.t > self.exp1 + 0.25 and self.print_t is None:
            self.print_t = self.t
            evs.append(("event", "print t %.2f" % self.t))

    def snapshot(self):
        s = self.base_snap()
        s["trail"] = len(self.trail); s["flash"] = self.flash; s["print_t"] = self.print_t
        return s

    def solids(self, s):
        return [("rect", 690, 1100, 800, FLOOR_Y)] + self.figure_box(870, FLOOR_Y, h=250, w=92)

    def focus(self, s):
        return self.PR

    def print_image(self, S, w, h):
        """Le tirage : Bounce en pose longue, une traînée rose floue (rendu une fois)."""
        from PIL import Image, ImageFilter
        key = (round(S, 4), w, h)
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        x0, y0, x1, y1 = self.PR
        ix0, iy0, ix1, iy1 = x0 + 24, y0 + 24, x1 - 24, y1 - 70
        acc = np.zeros((h, w), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        for (bx, by) in self.trail[::2]:
            px = (bx - 120) / (660 - 120) * w
            py = (by - 760) / (FLOOR_Y - 760) * h
            r = self.R / (660 - 120) * w
            acc += ((xx - px) ** 2 + (yy - py) ** 2 <= r * r).astype(np.float32)
        acc = np.clip(acc / max(1.0, acc.max() * 0.35), 0, 1)
        im = Image.fromarray((acc * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1.0, w / 28)))
        a = np.asarray(im, dtype=np.float32)[..., None] / 255.0
        bg = np.array([22, 20, 30], dtype=np.float32); pink = np.array([255, 70, 200], dtype=np.float32)
        rgb = (bg * (1 - a) + pink * a).astype(np.uint8)
        out = Image.fromarray(rgb, "RGB")
        self._cache = (key, out)
        return out

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        wall = (24, 22, 32)
        self.room(dr, P, wall, (40, 36, 44))
        dr.rectangle([P(120), P(560), P(640), FLOOR_Y * S], fill=(46, 44, 60))
        dr.rectangle([P(110), P(540), P(650), P(570)], fill=(70, 66, 80))
        dr.polygon([(P(40), P(700)), (P(150), P(660)), (P(150), P(860)), (P(40), P(820))], fill=(200, 196, 210))
        dr.rectangle([P(80), P(820), P(92), P(FLOOR_Y)], fill=(60, 60, 70))
        # l'appareil sur son trépied, le photographe
        for xe in (690, 745, 800):
            dr.line([(P(745), P(1180)), (P(xe), P(FLOOR_Y))], fill=(80, 80, 90), width=int(P(8)))
        dr.rectangle([P(700), P(1110), P(795), P(1180)], fill=(30, 30, 36))
        dr.rectangle([P(668), P(1125), P(702), P(1165)], fill=(60, 60, 70))
        circle(dr, P(668), P(1145), P(16), (110, 140, 190))
        tilt = math.sin((t - s["end"]) * 9.0) * 1.4 if s["end"] is not None else 0.0
        self.figure(dr, P, 870, FLOOR_Y, (70, 80, 100), h=250, w=92, tilt=tilt)
        self.bounce(dr, P, s)
        if s["flash"] is not None and 0 <= t - s["flash"] < 0.18:
            k = 1 - (t - s["flash"]) / 0.18
            from PIL import Image
            box = (0, int(P(SCENE_TOP)), int(P(W)), int(P(FLOOR_Y)))
            reg = dr._image.crop(box)
            dr._image.paste(Image.blend(reg, Image.new("RGB", reg.size, (200, 200, 205)), 0.55 * k), box[:2])
        if s["print_t"] is not None:
            u = min(1.0, (t - s["print_t"]) / 0.6)      # le tirage se révèle
            x0, y0, x1, y1 = self.PR
            dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(236, 232, 224))
            ix0, iy0, ix1, iy1 = int(P(x0 + 24)), int(P(y0 + 24)), int(P(x1 - 24)), int(P(y1 - 70))
            w, h = max(2, ix1 - ix0), max(2, iy1 - iy0)
            if len(self.trail) > 2 and s["trail"] == len(self.trail):
                from PIL import Image
                im = self.print_image(S, w, h)
                dark = Image.new("RGB", (w, h), (22, 20, 30))
                dr._image.paste(Image.blend(dark, im, u), (ix0, iy0))
            else:
                dr.rectangle([ix0, iy0, ix1, iy1], fill=(22, 20, 30))


# ---------------------------------------------------------------- 5. train miniature
class Train(Chapter):
    title = "5/6 · MODEL TRAINS"
    stamp = ("DERAILED", RED)
    stamp_y = 0.27
    mood = "lose"
    hold_s = 1.8
    TX0, TX1, TOP = 140.0, 900.0, 1180.0
    RAIL0, RAIL1 = 410.0, 880.0
    SP = 92.0

    def setup(self):
        rng = self.rng
        self.hop_init(260.0, self.TOP, wobble=50.0, xmin=215, xmax=300, **dict(HOP, start_h=300.0, min_h=260.0, max_h=360.0))
        self.line("Hobby five. Model trains.", "title", 0.0)
        self.line("The trains ran perfectly on time.", "mid", 1.4)
        self.tx = 760.0; self.tv = -120.0          # la locomotive (en tête à droite), vitesse
        self.hop = 0.0; self.hv = 0.0
        self.shake = 0.0
        self.need = int(rng.integers(8, 10))
        self.fall = None

    def cars(self):
        return [self.tx - k * self.SP for k in range(3)]

    def on_land(self, k, evs):
        self.shake = min(10.0, self.shake + 5.0 * k)
        if self.fall is not None:
            return
        self.hv = -(140 + 40 * self.hits) * k
        if self.hits >= self.need:
            self.fall = []
            for k2, x in enumerate(self.cars()):
                self.fall.append({"id": k2, "x": x, "y": self.TOP - 30 + self.hop, "vx": self.rng.uniform(-50, 70),
                                  "vy": -self.rng.uniform(720, 900), "a": 0.0, "w": self.rng.uniform(3.0, 5.0) * (1 if k2 % 2 else -1),
                                  "rest": False, "eng": k2 == 0})
            evs.append(("event", "derail t %.2f" % self.t))

    def after(self, dt, evs):
        self.shake = max(0.0, self.shake - 30.0 * dt)
        if self.fall is None:
            self.tx += self.tv * dt
            if self.tx > self.RAIL1 - 54 and self.tv > 0:
                self.tv = -abs(self.tv)
            if self.tx - 2 * self.SP < self.RAIL0 + 54 and self.tv < 0:
                self.tv = abs(self.tv)
            if self.hop < 0 or self.hv < 0:
                self.hv += self.g * 0.9 * dt
                self.hop = min(0.0, self.hop + self.hv * dt)
                if self.hop >= 0:
                    self.hop, self.hv = 0.0, 0.0
        else:
            rest = 0
            for c in self.fall:
                if c["rest"]:
                    rest += 1; continue
                c["vy"] += self.g * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["w"] * dt
                c["x"] = min(self.TX1 - 50, max(self.RAIL0 - 20, c["x"]))
                pts = [(-44, -26), (44, -26), (44, 32), (-44, 32)]
                if c["eng"]:
                    pts += [(10, -48), (30, -48), (-40, -40), (-6, -40)]
                settle_body(c, self.TOP, math.pi / 2, dt, pts)
            if rest == len(self.fall) and not self.payoff:
                self.finish("DERAILED")
                self.line("Delays are expected.", "punch", self.t + 0.9)

    def snapshot(self):
        s = self.base_snap()
        s["cars"] = self.cars(); s["hop"] = self.hop; s["shake"] = self.shake
        s["fall"] = [dict(c) for c in self.fall] if self.fall is not None else None
        return s

    def car_list(self, s):
        if s["fall"] is None:
            return [(k, x, self.TOP - 30 + s["hop"], 0.0, k == 0) for k, x in enumerate(s["cars"])]
        return [(c["id"], c["x"], c["y"], c["a"], c["eng"]) for c in s["fall"]]

    def solids(self, s):
        sh = [("rect", self.TX0, self.TOP, self.TX1, self.TOP + 26), ("rect", self.RAIL0 - 10, self.TOP - 30, self.RAIL0 + 6, self.TOP)]
        for (_id, x, y, a, eng) in self.car_list(s):
            sh.append(("circle", x, y, 44))
        return sh

    def focus(self, s):
        cl = self.car_list(s)
        return (min(c[1] for c in cl) - 50, min(c[2] for c in cl) - 50, max(c[1] for c in cl) + 50, max(c[2] for c in cl) + 34)

    def bodies(self, s):
        return [(c[0], c[1], c[2], c[3]) for c in self.car_list(s)]

    def car(self, dr, P, x, y, a, eng):
        ca, sa = math.cos(a), math.sin(a)

        def T(dx, dy):
            return (P(x + dx * ca - dy * sa), P(y + dx * sa + dy * ca))
        col = (190, 50, 60) if eng else (50, 90, 160)
        dr.polygon([T(-44, -26), T(44, -26), T(44, 18), T(-44, 18)], fill=col)
        if eng:
            dr.polygon([T(10, -26), T(30, -26), T(30, -48), T(10, -48)], fill=(40, 40, 46))
            dr.polygon([T(-40, -26), T(-6, -26), T(-6, -40), T(-40, -40)], fill=dim(col, 0.8))
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
        sy = s["shake"] * math.sin(t * 70)          # la table tremble à chaque retombée
        Q = lambda v: (v + sy) * S
        wood = (92, 64, 46)
        dr.rectangle([P(self.TX0), Q(self.TOP), P(self.TX1), Q(self.TOP + 26)], fill=wood)
        for x in (self.TX0 + 20, self.TX1 - 44):
            dr.rectangle([P(x), Q(self.TOP + 26), P(x + 24), P(FLOOR_Y)], fill=dim(wood, 0.8))
        dr.rectangle([P(self.RAIL0), Q(self.TOP - 6), P(self.RAIL1), Q(self.TOP)], fill=(150, 150, 160))
        for x in range(int(self.RAIL0), int(self.RAIL1), 30):
            dr.rectangle([P(x), Q(self.TOP - 4), P(x + 14), Q(self.TOP)], fill=(70, 50, 40))
        for x in (self.RAIL0 - 10, self.RAIL1 - 6):
            dr.rectangle([P(x), Q(self.TOP - 30), P(x + 16), Q(self.TOP)], fill=(200, 160, 60))
        for (_id, x, y, a, eng) in self.car_list(s):
            self.car(dr, P, x, y + sy, a, eng)
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 6. peinture
class Painting(Chapter):
    title = "6/6 · PAINTING"
    stamp = ("MASTERPIECE", GREEN)
    stamp_y = 0.30
    mood = "win"
    hold_s = 3.8
    CV = (480.0, 700.0, 840.0, 1140.0)
    PUDDLES = ((190.0, (220, 60, 70)), (300.0, (240, 200, 70)), (410.0, (70, 130, 220)))

    def setup(self):
        self.hop_init(290.0, FLOOR_Y, wobble=110.0, xmin=170, xmax=385, **dict(HOP, start_h=300.0, min_h=260.0, max_h=430.0))
        self.line("Hobby six. Painting.", "title", 0.0)
        self.line("Every bounce, a brushstroke.", "mid", 1.4)
        self.drops = []
        self.splats = []
        self.need = self.cfg["paint_splats"]
        self.critic = 1150.0
        self.nod = 0.0
        self.nid = 0

    def on_land(self, k, evs):
        x0, y0, x1, y1 = self.CV
        for _ in range(int(9 + 6 * k)):
            col = self.PUDDLES[int(self.rng.integers(0, 3))][1]
            r = self.rng.uniform(7, 16)
            rr = r * self.rng.uniform(1.4, 2.2)
            tx = self.rng.uniform(x0 + rr + 4, x1 - rr - 4); ty = self.rng.uniform(y0 + rr + 4, y1 - rr - 4)
            T = self.rng.uniform(0.45, 0.7)
            vx = (tx - self.bx) / T
            vy = (ty - (FLOOR_Y - 10) - 0.5 * self.g * 0.8 * T * T) / T
            self.nid += 1
            self.drops.append({"id": self.nid, "x": self.bx, "y": FLOOR_Y - 10, "vx": vx, "vy": vy, "c": col, "r": r, "rr": rr,
                               "tx": tx, "ty": ty, "T": T, "age": 0.0})

    def after(self, dt, evs):
        keep = []
        for d in self.drops:
            d["age"] += dt
            d["vy"] += self.g * 0.8 * dt
            d["x"] += d["vx"] * dt; d["y"] += d["vy"] * dt
            if d["age"] >= d["T"]:
                self.splats.append((d["tx"], d["ty"], d["rr"], d["c"]))
            else:
                keep.append(d)
        self.drops = keep
        if len(self.splats) >= self.need and not self.payoff:
            self.finish("MASTERPIECE")
            self.line("A museum hung it the next day.", "punch", self.t + 0.9)
            self.line("Finally, a hobby.", "end", self.t + 3.0)
        if self.payoff:
            self.critic = max(922.0, self.critic - 300 * dt)
            self.nod = 0.5 + 0.5 * math.sin(self.t * 5)

    def snapshot(self):
        s = self.base_snap()
        s["drops"] = [(d["id"], d["x"], d["y"], d["r"], d["c"]) for d in self.drops]
        s["splats"] = list(self.splats); s["critic"] = self.critic; s["nod"] = self.nod
        return s

    def solids(self, s):
        x0, y0, x1, y1 = self.CV
        return [("rect", x0 - 20, y0 - 20, x1 + 20, y1 + 20), ("rect", x0 + 30, y1, x0 + 60, FLOOR_Y), ("rect", x1 - 60, y1, x1 - 30, FLOOR_Y)]

    def focus(self, s):
        x0, y0, x1, y1 = self.CV
        return (x0 - 22, y0 - 22, x1 + 22, y1 + 22)

    def bodies(self, s):
        return [("d%d" % d[0], d[1], d[2], 0.0) for d in s["drops"]] + ([("critic", s["critic"], FLOOR_Y - 150, 0.0)] if s["critic"] <= self.W else [])

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        wall = (30, 28, 36)
        self.room(dr, P, wall, (54, 48, 52))
        x0, y0, x1, y1 = self.CV
        ended = s["end"] is not None
        if ended:
            k = min(1.0, (t - s["end"]) / 0.4)
            dr.polygon([(P(620), P(SCENE_TOP)), (P(700), P(SCENE_TOP)), (P(x1 + 60), P(FLOOR_Y)), (P(x0 - 60), P(FLOOR_Y))], fill=mix(wall, (255, 236, 190), 0.16 * k))
        dr.line([(P(x0 + 45), P(y1)), (P(x0 + 20), P(FLOOR_Y))], fill=(110, 80, 56), width=int(P(14)))
        dr.line([(P(x1 - 45), P(y1)), (P(x1 - 20), P(FLOOR_Y))], fill=(110, 80, 56), width=int(P(14)))
        dr.rectangle([P(x0 - 10), P(y1), P(x1 + 10), P(y1 + 16)], fill=(110, 80, 56))
        if ended:
            dr.rectangle([P(x0 - 22), P(y0 - 22), P(x1 + 22), P(y1 + 22)], fill=(200, 160, 70))
        dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=(222, 218, 210))
        for (x, y, r, c) in s["splats"]:
            circle(dr, P(x), P(y), P(r), c)
        for (px, c) in self.PUDDLES:
            dr.ellipse([P(px - 55), P(FLOOR_Y - 8), P(px + 55), P(FLOOR_Y + 14)], fill=dim(c, 0.85))
        for (_id, x, y, r, c) in s["drops"]:
            circle(dr, P(x), P(y), P(r * 0.6), c)
        if s["critic"] < 1100:
            self.figure(dr, P, s["critic"], FLOOR_Y, (60, 64, 90), h=260, w=96, tilt=0.3 * s["nod"])
        self.bounce(dr, P, s)


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": 3000.0,
    "photo_exp0": 4.2, "photo_exp_s": 1.0, "paint_splats": 165,
    "chapter_max_s": 14.0,
    "counter_font_size": 54, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.3, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(CardHouse, {}), (Chess, {}), (Birds, {}), (Photo, {}), (Train, {}), (Painting, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
