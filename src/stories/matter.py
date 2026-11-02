"""
Prototype « Bounce teste les matières » : six surfaces, six physiques, une note de rebond
pour chacune. Bounce ne s'arrête jamais de rebondir, et c'est lui qui abîme, creuse,
s'englue ou s'envoie trop loin. La dernière retourne la série : la meilleure note va à
un endroit qu'aucun sol ne peut atteindre.

    python3 src/stories/matter.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, RED, GREEN, AMBER, FLOOR_Y, SCENE_TOP, glow, mix

R_BOUNCE = 68.0
G = 3000.0
WALL = (26, 24, 38)
FLOOR = (46, 38, 40)


def clamp(v, a, b):
    return max(a, min(b, v))


class Matter(Chapter):
    """Un essai : Bounce rebondit sur une matière. Physique propre à chaque matière."""
    stamp_y = 0.30
    hold_s = 1.6
    exit_ok = False
    bodies_exit_ok = True
    score = None
    label = "BOUNCE SCORE"

    def setup(self):
        self.R = R_BOUNCE
        self.g = G
        self.bx, self.by = 540.0, FLOOR_Y - 600.0
        self.vx = self.vy = 0.0
        self.on = "air"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.landings = 0
        self.init()

    def init(self):
        pass

    def step(self, dt):
        self.t += dt
        evs = []
        self.phys(dt, evs)
        return evs

    def say(self, evs):
        """Un choc : Bounce dit son nom (le moteur place le mot)."""
        if self.t - self.last_hit >= 0.15:
            self.last_hit = self.t
            self.hits += 1
            evs.append(("hit", "floor"))
        self.hit_t = self.t
        self.landings += 1

    def hop(self, h, vx=0.0):
        self.vy = -math.sqrt(2 * self.g * max(h, 1.0))
        self.vx = vx

    def counter(self, s):
        return None if s.get("end") is not None else self.title

    zc = (540.0, 1150.0)                    # où la caméra avance après la chute
    intro = 0.0                             # recul d'ouverture (premier chapitre)

    def zoom(self, s):
        z = 1.0 + 0.04 * min(1.0, s["t"] / 6.0)               # une lente avancée de caméra
        if self.intro:
            k = min(1.0, s["t"] / 2.4)
            z += self.intro * (1 - k * k * (3 - 2 * k))       # l'ouverture recule sur toute la scène
        if s.get("end") is not None:
            k = min(1.0, (s["t"] - s["end"]) / 2.2)
            z += 0.22 * k * k * (3 - 2 * k)                   # gros plan sur l'issue
        return z

    def draw(self, dr, s, t, S):
        from PIL import Image, ImageDraw
        img = dr._image
        W2, H2 = img.size
        tmp = Image.new("RGB", (W2, H2), tuple(self.cfg["bg_color"]))
        self.scene(ImageDraw.Draw(tmp), s, t, S)
        Z = self.zoom(s)
        y0 = int(SCENE_TOP * S)
        zx, zy = self.zcenter(Z)
        cx, cy = zx * S, zy * S
        box = (cx - W2 / 2 / Z, cy - (cy - y0) / Z, cx + W2 / 2 / Z, cy + (H2 - cy) / Z)
        part = tmp.crop(tuple(int(round(v)) for v in box)).resize((W2, H2 - y0), Image.BILINEAR)
        img.paste(part, (0, y0))
        hp = base.HERO.get("pos")
        if hp is not None:
            base.HERO["pos"] = ((hp[0] - cx) * Z + cx, (hp[1] - cy) * Z + cy)
        self.score_label(dr, lambda v: v * S, s)

    def zcenter(self, Z):
        """Le centre du zoom, gardé assez loin des bords pour que le cadre reste plein."""
        half = self.W / 2 / Z
        return clamp(self.zc[0], half, self.W - half), self.zc[1]

    def zxy(self, s, x, y):
        """Une position du monde vue à travers le zoom (pour le contrôle)."""
        Z = self.zoom(s)
        zx, zy = self.zcenter(Z)
        return (x - zx) * Z + zx, (y - zy) * Z + zy, Z

    def hero_w(self, s):
        return (s["bx"], s["by"])

    def hero(self, s):
        hx, hy = self.hero_w(s)
        x, y, Z = self.zxy(s, hx, hy)
        return (x, y, self.R * Z)

    def solids_w(self, s):
        return []

    def focus_w(self, s):
        return None

    def solids(self, s):
        out = []
        for sh in self.solids_w(s):
            if sh[0] == "rect":
                x0, y0, Z = self.zxy(s, sh[1], sh[2]); x1, y1, _ = self.zxy(s, sh[3], sh[4])
                out.append(("rect", x0, y0, x1, y1))
            elif sh[0] == "circle":
                x, y, Z = self.zxy(s, sh[1], sh[2])
                out.append(("circle", x, y, sh[3] * Z))
        return out

    def focus(self, s):
        f = self.focus_w(s)
        if f is None:
            return None
        x0, y0, _ = self.zxy(s, f[0], f[1]); x1, y1, _ = self.zxy(s, f[2], f[3])
        return (x0, y0, x1, y1)

    def bodies(self, s):
        out = []
        for b in self.bodies_w(s):
            x, y, _ = self.zxy(s, b[1], b[2])
            out.append((b[0], x, y, b[3]))
        return out

    def bodies_w(self, s):
        return []

    def room(self, dr, P, wall=WALL, floor=FLOOR):
        """Le labo d'essai : mur carrelé, projecteur sur la zone de test, règle de hauteur."""
        dr.rectangle([0, P(SCENE_TOP - 200), P(self.W), P(FLOOR_Y)], fill=wall)
        line = mix(wall, (90, 90, 120), 0.35)
        for y in range(int(SCENE_TOP - 200), int(FLOOR_Y), 120):
            dr.line([(0, P(y)), (P(self.W), P(y))], fill=line, width=max(1, int(P(2))))
        for x in range(0, int(self.W) + 1, 120):
            dr.line([(P(x), P(SCENE_TOP - 200)), (P(x), P(FLOOR_Y))], fill=line, width=max(1, int(P(2))))
        cone = mix(wall, (255, 240, 200), 0.10)
        dr.polygon([(P(470), P(SCENE_TOP - 200)), (P(610), P(SCENE_TOP - 200)), (P(960), P(FLOOR_Y)), (P(120), P(FLOOR_Y))], fill=cone)
        dr.rectangle([0, P(FLOOR_Y), P(self.W), P(self.H)], fill=floor)
        dr.rectangle([0, P(FLOOR_Y), P(self.W), P(FLOOR_Y + 8)], fill=dim(floor, 1.35))
        # la règle : de quoi lire la hauteur de chaque rebond
        dr.rectangle([P(28), P(SCENE_TOP - 100), P(52), P(FLOOR_Y)], fill=(200, 190, 150))
        f = self.fnt(int(P(20)))
        for k, y in enumerate(range(int(FLOOR_Y), int(SCENE_TOP - 100), -50)):
            w = 22 if k % 2 == 0 else 12
            dr.line([(P(52), P(y)), (P(52 + w), P(y))], fill=(200, 190, 150), width=max(1, int(P(3))))
            if k % 4 == 0 and k:
                dr.text((P(80), P(y)), f"{k // 2}", fill=(200, 190, 150), anchor="lm", font=f)

    _fonts = {}

    def fnt(self, size):
        f = Matter._fonts.get(size)
        if f is None:
            f = Matter._fonts[size] = base.font(size)
        return f

    def score_label(self, dr, P, s):
        if s.get("end") is None:
            return
        f = base.font(int(P(40)))
        dr.text((P(self.W / 2), P(self.H * self.stamp_y - 100)), self.label, fill=(220, 220, 232), anchor="mm", font=f,
                stroke_width=int(P(4)), stroke_fill=(10, 8, 12))


# ---------------------------------------------------------------- 1. la gelée
class Jelly(Matter):
    title = "JELLY"
    stamp = ("7/10", AMBER)
    mood = "lose"
    hold_s = 1.5
    exit_ok = True                          # la gelée le renvoie hors du cadre : c'est la chute
    X0, X1, TOP = 150.0, 930.0, 1130.0
    intro = 0.18
    zc = (540.0, 1250.0)
    N = 41

    def init(self):
        self.u = np.zeros(self.N)            # creux de la surface (vers le bas positif)
        self.w = np.zeros(self.N)
        self.h = 230.0
        self.bx, self.by = 540.0, self.TOP - self.R - 260
        self.flung = False
        self.line("Jelly.", "title", 0.0)

    def xs(self):
        return np.linspace(self.X0, self.X1, self.N)

    def surf(self, x):
        k = (x - self.X0) / (self.X1 - self.X0) * (self.N - 1)
        i = int(clamp(k, 0, self.N - 2)); f = k - i
        return self.TOP + self.u[i] * (1 - f) + self.u[i + 1] * f

    def phys(self, dt, evs):
        # la surface : une corde de ressorts (ondes), rappelée vers le repos
        for _ in range(4):
            d = dt / 4
            lap = np.zeros(self.N)
            lap[1:-1] = self.u[:-2] - 2 * self.u[1:-1] + self.u[2:]
            acc = 14000.0 * lap - 30.0 * self.u - 0.9 * self.w
            self.w += acc * d
            self.u += self.w * d
            self.u[0] = self.u[-1] = 0.0
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if not self.flung and self.X0 < self.bx < self.X1 and self.vy > 0 and self.by + self.R >= self.surf(self.bx):
            # il s'enfonce : la gelée plie sous lui, puis le rend (avec plus qu'il n'a donné)
            xs = self.xs()
            push = np.exp(-((xs - self.bx) / 90.0) ** 2)
            self.w += push * self.vy * 1.1
            self.say(evs)
            self.by = self.surf(self.bx) - self.R
            if self.landings >= 6:
                self.flung = True
                self.hop(1900.0, 420.0)
            else:
                self.h *= 1.2
                self.hop(self.h, float(self.rng.uniform(-30, 30)))
        if self.flung and not self.payoff and (self.by + self.R < SCENE_TOP - 10 or self.bx - self.R > self.W):
            self.finish("FLUNG")
            self.line("Seven out of ten. Too bouncy.", "score", self.t + 0.8)

    def snapshot(self):
        s = self.base_snap(); s["u"] = self.u.copy(); return s

    def solids_w(self, s):
        return [("rect", self.X0 + 20, self.TOP + 40 + max(0.0, float(np.max(s["u"]))), self.X1 - 20, FLOOR_Y)]

    def focus_w(self, s):
        return (self.X0 + 120, self.TOP - 60, self.X1 - 160, FLOOR_Y - 60)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        xs = self.xs()
        u = s["u"]
        bulge = float(np.mean(u)) * 0.6
        top = [(P(x), P(self.TOP + v)) for x, v in zip(xs, u)]
        body = top + [(P(self.X1 + bulge), P((self.TOP + FLOOR_Y) / 2)), (P(self.X1), P(FLOOR_Y)),
                      (P(self.X0), P(FLOOR_Y)), (P(self.X0 - bulge), P((self.TOP + FLOOR_Y) / 2))]
        dr.polygon(body, fill=(40, 140, 80))
        inner = [(x, y + P(14)) for (x, y) in top] + [(P(self.X1 - 14 + bulge), P((self.TOP + FLOOR_Y) / 2)), (P(self.X1 - 14), P(FLOOR_Y - 10)),
                                                      (P(self.X0 + 14), P(FLOOR_Y - 10)), (P(self.X0 + 14 - bulge), P((self.TOP + FLOOR_Y) / 2))]
        dr.polygon(inner, fill=(80, 200, 120))
        dr.line(top, fill=(180, 250, 190), width=int(P(12)), joint="curve")
        for (bx, by, r) in ((300, 1260, 18), (700, 1380, 14), (520, 1440, 10), (820, 1250, 12), (420, 1400, 15), (620, 1240, 9)):
            k = (bx - self.X0) / (self.X1 - self.X0) * (self.N - 1)
            circle(dr, P(bx), P(by + 0.5 * u[int(k)]), P(r), (120, 220, 150))
        dr.ellipse([P(self.X0 + 40), P(self.TOP + 30), P(self.X0 + 140), P(self.TOP + 60)], fill=(150, 235, 170))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 2. le papier bulle
class Bubbles(Matter):
    title = "BUBBLE WRAP"
    stamp = ("9/10", GREEN)
    zc = (540.0, 1420.0)
    mood = "win"
    hold_s = 1.6
    X0, X1 = 130.0, 950.0
    BR = 46.0

    def init(self):
        n = int((self.X1 - self.X0) // (2 * self.BR + 6))
        self.bub = [{"x": self.X0 + self.BR + k * (2 * self.BR + 6), "pop": None} for k in range(n)]
        self.bx, self.by = self.bub[0]["x"], FLOOR_Y - 600.0
        self.dirx = 1
        self.line("Bubble wrap.", "title", 0.0)

    def ground(self, x):
        for b in self.bub:
            if b["pop"] is None and abs(b["x"] - x) < self.BR:
                return FLOOR_Y - 2 * self.BR - 6
        return FLOOR_Y - 8

    def phys(self, dt, evs):
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        g = self.ground(self.bx)
        if self.vy > 0 and self.by + self.R >= g:
            self.by = g - self.R
            self.say(evs)
            # il éclate tout ce qui est sous lui
            for b in self.bub:
                if b["pop"] is None and abs(b["x"] - self.bx) < self.BR + 6:
                    b["pop"] = self.t
            left = [b for b in self.bub if b["pop"] is None]
            if not left and not self.payoff:
                self.finish("ALL POPPED")
                self.line("Nine. Very satisfying.", "score", self.t + 0.9)
                self.hop(240.0)
                return
            if self.payoff:
                self.hop(240.0)
                return
            # vers la bulle intacte la plus proche
            tgt = min(left, key=lambda b: abs(b["x"] - self.bx))
            h = float(self.rng.uniform(250, 300))
            T = 2 * math.sqrt(2 * h / self.g)
            self.hop(h, clamp((tgt["x"] - self.bx) / T, -260, 260))
        if self.landings == 4 and self.once("more"):
            self.line("He's not stopping.", "more", self.t)

    def once(self, k):
        if getattr(self, "_said", None) is None:
            self._said = set()
        if k in self._said:
            return False
        self._said.add(k); return True

    def snapshot(self):
        s = self.base_snap(); s["bub"] = [(b["x"], b["pop"]) for b in self.bub]; return s

    def solids_w(self, s):
        return [("circle", x, FLOOR_Y - self.BR - 6, self.BR - 10) for (x, p) in s["bub"] if p is None]

    def focus_w(self, s):
        return (self.X0 + 60, FLOOR_Y - 2 * self.BR - 30, self.X1 - 200, FLOOR_Y - 20)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        dr.rectangle([P(self.X0 - 20), P(FLOOR_Y - 10), P(self.X1 + 20), P(FLOOR_Y)], fill=(150, 170, 190))
        for (x, p) in s["bub"]:
            cy = FLOOR_Y - self.BR - 6
            if p is None:
                circle(dr, P(x), P(cy), P(self.BR), (110, 140, 170))
                circle(dr, P(x), P(cy), P(self.BR - 5), (170, 200, 225))
                circle(dr, P(x - 14), P(cy - 15), P(11), (240, 248, 255))
            else:
                dr.ellipse([P(x - self.BR), P(FLOOR_Y - 16), P(x + self.BR), P(FLOOR_Y - 4)], fill=(120, 140, 160))
                age = s["t"] - p
                if age < 0.3:
                    k = age / 0.3
                    for a in range(8):
                        ang = a * math.pi / 4
                        r0, r1 = self.BR * (0.6 + k), self.BR * (1.0 + 1.6 * k)
                        dr.line([(P(x + math.cos(ang) * r0), P(cy + math.sin(ang) * r0 * 0.7)),
                                 (P(x + math.cos(ang) * r1), P(cy + math.sin(ang) * r1 * 0.7))],
                                fill=mix((255, 240, 200), WALL, k), width=int(P(5)))
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 3. le verre
class Glass(Matter):
    title = "GLASS"
    stamp = ("0/10", RED)
    mood = "lose"
    hold_s = 1.5
    exit_ok = True                          # il passe à travers : il tombe hors du cadre
    X0, X1, Y = 180.0, 900.0, 1330.0
    zc = (540.0, 1330.0)

    def init(self):
        self.cracks = []                    # polylignes
        self.shards = None
        self.bx, self.by = 520.0, self.Y - 600
        self.line("Glass.", "title", 0.0)

    def add_cracks(self, x, n, L):
        for _ in range(n):
            ang = float(self.rng.uniform(0, math.pi * 2))
            pts = [(x, self.Y)]
            px, py = x, 0.0
            for k in range(5):
                ang += float(self.rng.uniform(-0.5, 0.5))
                px += math.cos(ang) * L / 5
                py += math.sin(ang) * L / 5 * 0.12
                pts.append((clamp(px, self.X0 + 4, self.X1 - 4), self.Y + clamp(py, -8, 8)))
            self.cracks.append(pts)

    def phys(self, dt, evs):
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if self.shards is None and self.vy > 0 and self.by + self.R >= self.Y - 8:
            self.by = self.Y - 8 - self.R
            self.say(evs)
            if self.landings <= 9:
                n, L = [(1, 30), (1, 50), (2, 70), (2, 100), (3, 130), (3, 170), (4, 220), (5, 300), (7, 400)][self.landings - 1]
                self.add_cracks(self.bx, n, L)
                if self.landings == 3:
                    self.line("That's a crack.", "crack", self.t + 0.75)
                self.hop(300.0, float(self.rng.uniform(-120, 120)))
            else:
                # tout part : la vitre se brise en éclats, il passe au travers
                self.shards = []
                cx = self.bx
                xs = sorted([self.X0, self.X1] + [float(v) for v in self.rng.uniform(self.X0 + 30, self.X1 - 30, 9)])
                for a, b in zip(xs, xs[1:]):
                    m = (a + b) / 2
                    self.shards.append({"x": m, "y": self.Y, "w": (b - a) / 2, "a": 0.0,
                                        "vx": (m - cx) * 0.6, "vy": -float(self.rng.uniform(150, 450)),
                                        "va": float(self.rng.uniform(-3, 3))})
                self.vy = 200.0
                self.vx = 0.0
                self.broke_t = self.t
        if self.shards is not None and not self.payoff and self.t - self.broke_t > 0.35:
            self.finish("BROKE")
            self.line("Zero.", "score", self.t + 0.6)
        if self.shards is not None:
            for c in self.shards:
                c["vy"] += self.g * 0.8 * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["va"] * dt
            if self.by > self.H + self.R * 2:
                self.vy = 0.0

    def snapshot(self):
        s = self.base_snap()
        s["cracks"] = [list(p) for p in self.cracks]
        s["shards"] = [dict(c) for c in self.shards] if self.shards is not None else None
        return s

    def solids_w(self, s):
        if s["shards"] is not None:
            return []
        return [("rect", self.X0, self.Y - 6, self.X1, self.Y + 12)]

    def focus_w(self, s):
        return (self.X0 + 60, self.Y - 60, self.X1 - 140, self.Y + 60)

    def bodies_w(self, s):
        if s["shards"] is None:
            return []
        return [(k, c["x"], c["y"], c["a"]) for k, c in enumerate(s["shards"]) if c["y"] < self.H]

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        # le trou noir sous la vitre
        dr.rectangle([P(self.X0), P(self.Y), P(self.X1), P(self.H)], fill=(6, 6, 10))
        for x in (self.X0 - 30, self.X1):
            dr.rectangle([P(x), P(self.Y - 10), P(x + 30), P(self.H)], fill=(70, 70, 90))
        glass = (150, 200, 230)
        if s["shards"] is None:
            dr.rectangle([P(self.X0), P(self.Y - 8), P(self.X1), P(self.Y + 26)], fill=glass)
            dr.rectangle([P(self.X0), P(self.Y - 8), P(self.X1), P(self.Y - 1)], fill=(225, 245, 255))
            for k in range(4):
                xx = self.X0 + 80 + k * 190
                dr.polygon([(P(xx), P(self.Y + 24)), (P(xx + 40), P(self.Y - 6)), (P(xx + 60), P(self.Y - 6)), (P(xx + 20), P(self.Y + 24))], fill=(190, 225, 245))
            for pts in s["cracks"]:
                dr.line([(P(x), P(y + 8)) for x, y in pts], fill=(255, 255, 255), width=int(P(6)))
        else:
            for c in s["shards"]:
                ca, sa = math.cos(c["a"]), math.sin(c["a"])
                pts = [(-c["w"], -8), (c["w"], -8), (c["w"] * 0.6, 10), (-c["w"] * 0.8, 10)]
                dr.polygon([(P(c["x"] + dx * ca - dy * sa), P(c["y"] + dx * sa + dy * ca)) for dx, dy in pts], fill=glass)
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. le miel
class Honey(Matter):
    title = "HONEY"
    stamp = ("1/10", RED)
    zc = (540.0, 1230.0)

    def zoom(self, s):
        # la caméra se rapproche de lui à mesure qu'il s'enfonce
        return super().zoom(s) + 0.05 * s["t"]
    mood = "lose"
    hold_s = 2.0
    TOP = 1250.0

    def init(self):
        self.depth = 0.0                    # combien il est enfoncé (px sous la surface)
        self.h = 330.0
        self.stuck = False
        self.leave = None                   # le moment où il a quitté le miel (le fil s'étire)
        self.bx, self.by = 540.0, self.TOP - self.R - 340
        self.line("Honey.", "title", 0.0)

    def phys(self, dt, evs):
        if self.stuck:
            self.depth = min(self.R * 1.05, self.depth + 6.0 * dt)
            self.by = self.TOP - self.R + self.depth
            self.bx = 540.0 + 6.0 * math.sin(self.t * 9.0) * max(0.0, 1.0 - (self.t - self.stuck_t) / 2.0)
            if not self.payoff and self.t - self.stuck_t > 0.6:
                self.finish("STUCK")
                self.line("First time he's ever been quiet.", "score", self.t + 0.3)
            return
        self.vy += self.g * dt
        self.by += self.vy * dt
        low = self.TOP - self.R + self.depth
        if self.vy > 0 and self.by >= low:
            self.by = low
            self.say(evs)
            self.depth += self.R * 0.15
            self.h *= 0.85
            if self.depth > self.R * 0.85:
                self.stuck = True
                self.stuck_t = self.t
                return
            self.hop(self.h)
            self.leave = self.t

    def snapshot(self):
        s = self.base_snap(); s["depth"] = self.depth; s["leave"] = self.leave; return s

    def focus_w(self, s):
        return (300.0, self.TOP - 120, 780.0, self.TOP + 80)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        amber, light = (220, 150, 40), (250, 200, 90)
        # le pot de miel, vu en coupe
        dr.rectangle([P(150), P(self.TOP - 40), P(930), P(FLOOR_Y)], fill=(80, 70, 66))
        self.bounce(dr, P, s)
        bx, by = s["bx"], s["by"]
        # la surface ondule autour de chaque retombée
        age = s["t"] - s["hit_t"]
        A = 16.0 * math.exp(-max(0.0, age) / 0.9) + 3.0
        xs = [170 + k * 10 for k in range(75)]
        ys = [self.TOP + A * math.sin((abs(x - bx) - 260 * age) / 38.0) * math.exp(-abs(x - bx) / 420.0) for x in xs]
        dr.polygon([(P(170), P(FLOOR_Y))] + [(P(x), P(y)) for x, y in zip(xs, ys)] + [(P(910), P(FLOOR_Y))], fill=amber)
        dr.line([(P(x), P(y)) for x, y in zip(xs, ys)], fill=light, width=int(P(10)))
        # le bourrelet autour de lui, et le fil qui s'étire quand il remonte
        if s["depth"] > 0:
            w = self.R * 1.25
            dr.ellipse([P(bx - w), P(self.TOP - 18), P(bx + w), P(self.TOP + 16)], fill=amber)
        if s["leave"] is not None and s["on"] != "stuck":
            age = s["t"] - s["leave"]
            bottom = by + self.R
            if 0 < age < 0.35 and bottom < self.TOP:
                th = self.R * 0.5 * (1 - age / 0.35)
                dr.polygon([(P(bx - th), P(bottom - 6)), (P(bx + th), P(bottom - 6)), (P(bx + th * 1.8), P(self.TOP + 4)), (P(bx - th * 1.8), P(self.TOP + 4))], fill=amber)
        for k in range(5):
            dx = 210 + k * 160
            dr.ellipse([P(dx), P(self.TOP + 40 + (k % 2) * 60), P(dx + 26), P(self.TOP + 54 + (k % 2) * 60)], fill=light)
        dr.rectangle([P(150), P(self.TOP - 40), P(170), P(FLOOR_Y)], fill=(110, 100, 96))
        dr.rectangle([P(910), P(self.TOP - 40), P(930), P(FLOOR_Y)], fill=(110, 100, 96))

    def base_snap(self):
        s = super().base_snap()
        if self.stuck:
            s["on"] = "stuck"
        return s


# ---------------------------------------------------------------- 5. le sable
class Sand(Matter):
    title = "SAND"
    stamp = ("2/10", RED)
    zc = (560.0, 1300.0)
    mood = "lose"
    hold_s = 1.8
    X0, X1, BASE = 100.0, 980.0, 1300.0
    DX = 8.0

    def init(self):
        n = int((self.X1 - self.X0) / self.DX) + 1
        self.hx = np.linspace(self.X0, self.X1, n)
        self.hy = np.full(n, self.BASE) + 6 * np.sin(self.hx / 90.0)
        self.grains = []
        self.buried = False
        self.bx, self.by = 560.0, self.BASE - self.R - 360
        self.line("Sand.", "title", 0.0)

    def surf(self, x):
        return float(np.interp(x, self.hx, self.hy))

    def phys(self, dt, evs):
        for gr in self.grains:
            gr[3] += self.g * dt
            gr[0] += gr[2] * dt; gr[1] += gr[3] * dt
        self.grains = [gr for gr in self.grains if gr[1] < self.surf(gr[0]) + 4]
        if self.buried:
            # les bords s'éboulent dans le trou, par-dessus lui
            tgt = np.full_like(self.hy, self.BASE)
            near = np.abs(self.hx - self.bx) < self.R * 2.6
            cover = self.by - self.R * 0.05
            tgt[near] = np.minimum(self.hy[near], np.maximum(cover, self.BASE - 4))
            self.hy += (np.where(near, np.minimum(self.hy, cover + 0 * self.hy), self.hy) - self.hy) * min(1.0, 3.0 * dt)
            return
        self.vy += self.g * dt
        self.by += self.vy * dt
        floor_here = self.surf(self.bx) - self.R
        if self.vy > 0 and self.by >= floor_here:
            self.by = floor_here
            self.say(evs)
            # il creuse : le sable sous lui part sur les bords, en gerbe
            dig = 26.0
            g = np.exp(-((self.hx - self.bx) / (self.R * 0.9)) ** 2)
            rim = np.exp(-((np.abs(self.hx - self.bx) - self.R * 1.9) / (self.R * 0.9)) ** 2)
            self.hy += dig * g - dig * 0.38 * rim
            self.hy = np.minimum(self.hy, FLOOR_Y - 20)
            for _ in range(26):
                side = 1 if self.rng.random() < 0.5 else -1
                self.grains.append([self.bx + side * self.R * 0.8, self.by + self.R * 0.7,
                                    side * float(self.rng.uniform(150, 420)), -float(self.rng.uniform(350, 800))])
            self.by = self.surf(self.bx) - self.R
            if self.landings == 3:
                self.line("He's digging.", "dig", self.t + 0.8)
            if self.landings >= 9:
                self.buried = True
                self.finish("BURIED")
                self.line("Two. He dug that hole himself.", "score", self.t + 0.9)
                return
            self.hop(300.0)

    def snapshot(self):
        s = self.base_snap(); s["hy"] = self.hy.copy(); s["grains"] = [tuple(g) for g in self.grains]; return s

    def focus_w(self, s):
        return (self.bx - 200, self.BASE - 120, self.bx + 200, FLOOR_Y)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 30, 50), (60, 50, 40))
        circle(dr, P(860), P(700), P(46), (230, 230, 236))
        self.bounce(dr, P, s)
        sand, light = (214, 180, 120), (236, 206, 150)
        pts = [(P(self.X0), P(self.H))] + [(P(x), P(y)) for x, y in zip(self.hx, s["hy"])] + [(P(self.X1), P(self.H))]
        dr.polygon(pts, fill=sand)
        dr.rectangle([P(self.X0), P(FLOOR_Y + 40), P(self.X1), P(self.H)], fill=dim(sand, 0.8))
        dr.line([(P(x), P(y)) for x, y in zip(self.hx, s["hy"])], fill=light, width=int(P(6)))
        for (x, y, vx, vy) in s["grains"]:
            circle(dr, P(x), P(y), P(5), light)


# ---------------------------------------------------------------- 6. le trampoline
class Trampoline(Matter):
    title = "TRAMPOLINE"
    stamp = ("10/10", GREEN)
    zc = (640.0, 1100.0)
    mood = "win"
    hold_s = 4.4
    MAT = 1330.0
    CEIL = 430.0
    ROOF = -250.0
    MOON_Y = -9000.0
    MOON_R = 380.0
    MOON_X = 640.0

    def init(self):
        self.h = 260.0
        self.cam = 0.0                      # décalage vertical de la caméra (monde -> écran)
        self.sag = 0.0
        self.sagv = 0.0
        self.phase = "room"
        self.holes = []
        self.debris = []
        self.moon_g = 420.0
        self.bx, self.by = 540.0, self.MAT - self.R - 300
        self.line("Trampoline.", "title", 0.0)

    def phys(self, dt, evs):
        # la toile du trampoline
        self.sagv += (-900.0 * self.sag - 9.0 * self.sagv) * dt
        self.sag += self.sagv * dt
        for d in self.debris:
            d[3] += self.g * dt; d[0] += d[2] * dt; d[1] += d[3] * dt
        if self.phase == "room":
            self.vy += self.g * dt
            self.by += self.vy * dt
            # le plafond, puis le toit : il passe au travers
            for (yy, key) in ((self.CEIL, "ceil"), (self.ROOF, "roof")):
                if self.vy < 0 and self.by - self.R < yy and key not in [k for k, _ in self.holes]:
                    self.holes.append((key, self.bx))
                    for _ in range(18):
                        self.debris.append([self.bx + float(self.rng.uniform(-80, 80)), yy, float(self.rng.uniform(-300, 300)), float(self.rng.uniform(-200, 200))])
                    if key == "ceil":
                        self.line("That was the ceiling.", "ceil", self.t + 0.1)
                    else:
                        self.line("And the roof.", "roof", self.t + 0.1)
            if self.vy > 0 and self.by + self.R >= self.MAT + self.sag:
                self.by = self.MAT + self.sag - self.R
                self.say(evs)
                self.sagv += self.vy * 0.25
                self.h *= 1.62
                if self.h > 2600:
                    # le dernier saut : il ne redescend pas
                    self.phase = "space"
                    self.t_space = self.t
                    self.vy = -2600.0
                    self.line("He's not coming down.", "space", self.t + 0.8)
                else:
                    self.hop(self.h)
        elif self.phase == "space":
            # dans l'espace, il file vers la Lune et se pose dessus en arc
            k = clamp((self.t - self.t_space) / 4.6, 0.0, 1.0)
            sm = lambda v: v * v * (3 - 2 * v)
            y0 = self.MAT - self.R
            top = self.MOON_Y - self.MOON_R
            y1 = top - self.R
            yt = top - 520.0
            if k < 0.72:
                # il monte en passant à gauche de la Lune
                ka = k / 0.72
                self.bx = 540.0 + (120.0 - 540.0) * sm(min(1.0, ka / 0.45))
                self.by = y0 + (yt - y0) * sm(ka)
            else:
                # puis il redescend dessus en arc
                kb = (k - 0.72) / 0.28
                self.bx = 120.0 + (self.MOON_X - 120.0) * sm(kb)
                self.by = yt + (y1 - yt) * kb - 420.0 * math.sin(math.pi * kb)
            if k >= 1.0:
                self.phase = "moon"
                self.by = y1
                self.say(evs)
                self.finish("MOON")
                self.line("The Moon. Ten out of ten.", "score", self.t + 0.9)
                self.vy = -math.sqrt(2 * self.moon_g * 170)
        else:
            self.vy += self.moon_g * dt
            self.by += self.vy * dt
            y1 = self.MOON_Y - self.MOON_R - self.R
            self.bx = self.MOON_X
            if self.vy > 0 and self.by >= y1:
                self.by = y1
                self.say(evs)
                self.vy = -math.sqrt(2 * self.moon_g * 170)
        # la caméra garde Bounce dans l'image
        sy = self.by + self.cam
        lo, hi = 700.0, 1240.0
        if self.phase == "moon":
            target = 1180.0 - (self.MOON_Y - self.MOON_R)
            self.cam += (target - self.cam) * min(1.0, 3.0 * dt)
        elif sy < lo:
            self.cam += lo - sy
        elif sy > hi and self.cam > 0:
            self.cam = max(0.0, self.cam - (sy - hi))

    def snapshot(self):
        s = self.base_snap()
        s["cam"] = self.cam; s["sag"] = self.sag; s["holes"] = list(self.holes); s["debris"] = [tuple(d) for d in self.debris]
        s["phase"] = self.phase
        return s

    def hero_w(self, s):
        return (s["bx"], s["by"] + s["cam"])

    def focus_w(self, s):
        y = s["by"] + s["cam"]
        return (s["bx"] - 110, y - self.R - 10, s["bx"] + 110, y + self.R + 30)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        c = s["cam"]
        Y = lambda y: P(y + c)
        W = self.W
        # le ciel : de la nuit bleue au noir de l'espace selon l'altitude
        alt = clamp(c / 6000.0, 0.0, 1.0)
        sky = mix((20, 26, 56), (4, 4, 10), alt)
        dr.rectangle([0, P(SCENE_TOP), P(W), P(self.H)], fill=sky)
        for i in range(140):
            sx = (i * 7919 + 131) % W
            syw = -200 - (i * 104729) % 9000
            sy = (syw + c * 0.45) % 2600 - 300
            if SCENE_TOP < sy < self.H:
                circle(dr, P(sx), P(sy), P(2 + i % 2), (200, 205, 230))
        for (cx, cyw, w) in ((200, -1600, 260), (800, -2500, 320), (420, -3600, 280)):
            yy = cyw + c
            if SCENE_TOP - 200 < yy < self.H + 200:
                dr.ellipse([P(cx - w), P(yy - 50), P(cx + w), P(yy + 50)], fill=mix(sky, (200, 200, 220), 0.25))
        # la Lune
        my = self.MOON_Y + c
        if my + self.MOON_R > SCENE_TOP - 100 and my - self.MOON_R < self.H + 100:
            glow(dr, P, self.MOON_X, my, self.MOON_R * 1.5, (200, 200, 220), sky, 0.18)
            circle(dr, P(self.MOON_X), P(my), P(self.MOON_R), (200, 200, 210))
            for (dx, dy, r) in ((-150, -200, 60), (120, -260, 40), (-40, 80, 70), (170, 120, 50), (-200, 150, 34)):
                circle(dr, P(self.MOON_X + dx), P(my + dy), P(r), (170, 170, 182))
        # la maison : toit, mur, plafond, sol, trampoline
        if self.ROOF + c < self.H + 50:
            dr.polygon([(P(-40), Y(self.ROOF + 120)), (P(W / 2), Y(self.ROOF - 160)), (P(W + 40), Y(self.ROOF + 120))], fill=(70, 50, 50))
            dr.rectangle([P(0), Y(self.ROOF + 120), P(W), Y(self.CEIL)], fill=(40, 34, 44))
            dr.rectangle([P(0), Y(self.CEIL), P(W), Y(FLOOR_Y)], fill=WALL)
            dr.rectangle([P(0), Y(self.CEIL - 30), P(W), Y(self.CEIL)], fill=(60, 54, 66))
            dr.rectangle([P(0), Y(FLOOR_Y), P(W), P(self.H) if Y(FLOOR_Y) < P(self.H) else Y(FLOOR_Y) + 1], fill=FLOOR)
            for (key, hx) in s["holes"]:
                yy = self.CEIL if key == "ceil" else self.ROOF - 20
                dr.ellipse([P(hx - 90), Y(yy - 40), P(hx + 90), Y(yy + 10)], fill=sky)
            mat = self.MAT + s["sag"]
            for lx in (190, 890):
                dr.line([(P(lx), Y(self.MAT)), (P(lx + (40 if lx > 500 else -40)), Y(FLOOR_Y))], fill=(120, 120, 140), width=int(P(16)))
            dr.line([(P(190), Y(self.MAT)), (P(540), Y(mat)), (P(890), Y(self.MAT))], fill=(20, 20, 26), width=int(P(22)))
            dr.rectangle([P(170), Y(self.MAT - 14), P(210), Y(self.MAT + 14)], fill=(70, 130, 220))
            dr.rectangle([P(870), Y(self.MAT - 14), P(910), Y(self.MAT + 14)], fill=(70, 130, 220))
        for (dx, dyw, vx, vy) in s["debris"]:
            yy = dyw + c
            if SCENE_TOP < yy < self.H:
                dr.rectangle([P(dx - 8), P(yy - 6), P(dx + 8), P(yy + 6)], fill=(90, 80, 86))
        base.ball(dr, P(s["bx"]), P(s["by"] + c), P(self.R))
        dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": G,
    "chapter_max_s": 12.0,
    "counter_font_size": 84, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 2.0, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(Jelly, {}), (Bubbles, {}), (Glass, {}), (Honey, {}), (Sand, {}), (Trampoline, {"chapter_max_s": 30.0})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
