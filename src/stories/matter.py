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
        self.pending()
        return evs

    def say(self, evs):
        """Un choc : Bounce dit son nom (le moteur place le mot)."""
        if self.t - self.last_hit >= 0.15:
            self.last_hit = self.t
            self.hits += 1
            evs.append(("hit", "floor"))
        self.hit_t = self.t
        self.landings += 1

    # --- la voix : Bounce dit son nom à chaque choc ; une réplique ne se place que dans un
    # creux entre deux mots, sinon le moteur fait taire Bounce
    _durs = {}

    def word(self):
        w = Matter._durs.get("__word__")
        if w is None:
            x = base.hero_word(self.cfg["hero_name"], self.cfg)
            w = Matter._durs["__word__"] = (len(x) / base.ak.SR) if x is not None else 0.85
        return w

    def ldur(self, text):
        d = Matter._durs.get(text)
        if d is None:
            import voice as nv
            x = nv.say(text, self.cfg["narrator_voice"], self.cfg["narrator_length"])
            d = Matter._durs[text] = (len(x) / nv.SR) if x is not None else 0.9
        return d

    def talk(self, text, key):
        """Appelée sur un choc : la réplique commence après le mot, et renvoie le temps de vol
        qu'il faut avant le choc suivant pour qu'elle tienne entière."""
        start = self.t + self.word() + 0.2
        self.line(text, key, start)
        return start + self.ldur(text) + 0.3 - self.t

    def h_for(self, T, g=None):
        return (g or self.g) * T * T / 8.0

    def fall_in(self, x, land_y, title):
        """Bounce entre par le haut pendant que la voix dit le titre : sa première retombée
        tombe juste après."""
        tf = self.ldur(title) + 0.45
        self.bx, self.by = x, land_y - self.R - 0.5 * self.g * tf * tf
        self.vx = self.vy = 0.0
        self.line(title, "title", 0.0)

    def hop(self, h, vx=0.0):
        self.vy = -math.sqrt(2 * self.g * max(h, 1.0))
        self.vx = vx

    def counter(self, s):
        return None if s.get("end") is not None else self.title

    def later(self, outcome, line, key, delay=0.4, after=0.5):
        """La chute arrive un instant après le rebond qui la déclenche : le rebond reste dit."""
        self._pending = (self.t + delay, outcome, line, key, after)

    def pending(self):
        p = getattr(self, "_pending", None)
        if p is not None and self.t >= p[0] and not self.payoff:
            self._pending = None
            self.finish(p[1])
            if p[2]:
                self.line(p[2], p[3], self.t + p[4])

    zc = (540.0, 1150.0)                    # où la caméra avance après la chute
    intro = 0.14                            # chaque pièce s'ouvre en reculant

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
        if s["hit_t"] < 0 and y - self.R * Z < SCENE_TOP:
            return None                    # il entre par le haut : pas encore dans le cadre
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
        """Le labo d'essai : mur carrelé, projecteur sur la zone de test."""
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
    hold_s = 1.4
    exit_ok = True                          # la gelée le renvoie hors du cadre : c'est la chute
    X0, X1, TOP = 150.0, 930.0, 1130.0
    intro = 0.26
    zc = (540.0, 1250.0)
    N = 41

    def init(self):
        self.u = np.zeros(self.N)            # creux de la surface (vers le bas positif)
        self.w = np.zeros(self.N)
        self.bx, self.by = 540.0, self.TOP - self.R - 200
        self.state = "fall"                  # fall -> held (la gelée l'avale) -> hop -> flung -> held
        self.flung = False
        self.line("Jelly.", "title", 0.0)
        # la voix de l'accroche puis « Jelly. » : il ne retombe pour de bon qu'après
        hv = base.hook_audio(self.cfg)
        hook_end = 0.15 + (len(hv) / base.ak.SR if hv is not None else 1.8) + 0.3 + self.cfg["narr_gap_s"]
        self.first_land = hook_end + self.ldur("Jelly.") + 0.3
        self.release = self.first_land - 1.05

    def xs(self):
        return np.linspace(self.X0, self.X1, self.N)

    def surf(self, x):
        k = (x - self.X0) / (self.X1 - self.X0) * (self.N - 1)
        i = int(clamp(k, 0, self.N - 2)); f = k - i
        return self.TOP + self.u[i] * (1 - f) + self.u[i + 1] * f

    def poke(self, v):
        xs = self.xs()
        self.w += np.exp(-((xs - self.bx) / 90.0) ** 2) * v

    def phys(self, dt, evs):
        for _ in range(4):
            d = dt / 4
            lap = np.zeros(self.N)
            lap[1:-1] = self.u[:-2] - 2 * self.u[1:-1] + self.u[2:]
            acc = 14000.0 * lap - 30.0 * self.u - 0.9 * self.w
            self.w += acc * d
            self.u += self.w * d
            self.u[0] = self.u[-1] = 0.0
        if self.state == "held":
            # avalé à moitié : il tremble avec la gelée, sans rebondir (pas de choc)
            self.by = self.surf(self.bx) - self.R + self.sink
            if not self.flung and self.t >= self.release:
                self.state = "air"
                T = self.first_land - self.t
                self.hop(self.h_for(T))
            return
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if self.vy > 0 and self.X0 < self.bx < self.X1 and self.by + self.R >= self.surf(self.bx):
            if self.state == "fall" or self.flung:
                # la gelée l'attrape en douceur : elle l'avale à moitié
                self.poke(self.vy * 1.1)
                self.state = "held"
                self.sink = self.R * 0.55
                return
            self.poke(self.vy * 1.1)
            self.say(evs)
            self.by = self.surf(self.bx) - self.R
            if self.landings == 1:
                self.hop(self.h_for(1.22))
            else:
                # trop de rebond : elle le renvoie au plafond
                self.flung = True
                self.hop(980.0, -180.0)            # il retombera à gauche, loin de la note
        if self.flung and not self.payoff and self.by + self.R < SCENE_TOP - 10:
            self.finish("FLUNG")

    def snapshot(self):
        s = self.base_snap(); s["u"] = self.u.copy(); return s

    def solids_w(self, s):
        return [("rect", self.X0 + 20, self.TOP + 60 + max(0.0, float(np.max(s["u"]))), self.X1 - 20, FLOOR_Y)]

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
        for (bx, by, r) in ((300, 1260, 18), (700, 1380, 14), (520, 1440, 10), (820, 1250, 12), (420, 1400, 15), (620, 1240, 9)):
            k = (bx - self.X0) / (self.X1 - self.X0) * (self.N - 1)
            circle(dr, P(bx), P(by + 0.5 * u[int(k)]), P(r), (120, 220, 150))
        self.bounce(dr, P, s)
        # la gelée par-dessus le bas de Bounce quand elle l'avale : on le voit à travers
        if s["by"] + self.R > self.TOP + float(np.min(u)) + 2:
            dr.polygon(top + [(P(self.X1), P(FLOOR_Y)), (P(self.X0), P(FLOOR_Y))], fill=(80, 200, 120))
            r = self.R
            bx, by = P(s["bx"]), P(s["by"])
            dr.ellipse([bx - P(r) * 0.95, by - P(r) * 0.95, bx + P(r) * 0.95, by + P(r) * 0.95], outline=(60, 150, 95), width=int(P(4)))
        dr.line(top, fill=(180, 250, 190), width=int(P(12)), joint="curve")
        dr.ellipse([P(self.X0 + 40), P(self.TOP + 30), P(self.X0 + 140), P(self.TOP + 60)], fill=(150, 235, 170))


# ---------------------------------------------------------------- 2. le papier bulle
class Bubbles(Matter):
    title = "BUBBLE WRAP"
    stamp = ("9/10", GREEN)
    zc = (500.0, 1420.0)
    mood = "win"
    hold_s = 1.6
    X0 = 120.0
    BR = 40.0
    NB = 9

    def init(self):
        sp = 2 * self.BR + 4
        self.bub = [{"x": self.X0 + self.BR + k * sp, "pop": None} for k in range(self.NB)]
        self.fall_in(self.bub[0]["x"], FLOOR_Y - 2 * self.BR - 6, "Bubble wrap.")

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
            for b in self.bub:
                if b["pop"] is None and abs(b["x"] - self.bx) < self.BR + 6:
                    b["pop"] = self.t
            left = [b for b in self.bub if b["pop"] is None]
            h = float(self.rng.uniform(420, 460))
            if not left:
                if not getattr(self, "_done", False):
                    self._done = True
                    self.later("ALL POPPED", None, None)
                self.hop(h, -60.0)
                return
            tgt = min(left, key=lambda b: abs(b["x"] - self.bx))
            T = 2 * math.sqrt(2 * h / self.g)
            self.hop(h, clamp((tgt["x"] - self.bx) / T, -260, 260))

    def snapshot(self):
        s = self.base_snap(); s["bub"] = [(b["x"], b["pop"]) for b in self.bub]; return s

    def solids_w(self, s):
        return [("circle", x, FLOOR_Y - self.BR - 6, self.BR - 10) for (x, p) in s["bub"] if p is None]

    def focus_w(self, s):
        return (self.X0 + 40, FLOOR_Y - 2 * self.BR - 30, self.X0 + 2 * self.BR * self.NB - 120, FLOOR_Y - 20)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        x1 = self.X0 + (2 * self.BR + 4) * self.NB
        dr.rectangle([P(self.X0 - 20), P(FLOOR_Y - 10), P(x1 + 10), P(FLOOR_Y)], fill=(150, 170, 190))
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
    hold_s = 1.4
    exit_ok = True                          # il passe à travers : il tombe hors du cadre
    X0, X1, Y, TH = 160.0, 920.0, 1290.0, 90.0
    zc = (540.0, 1330.0)
    STARS = [(5, 60), (6, 110), (8, 170), (10, 240), (12, 330), (15, 460)]

    def init(self):
        self.stars = []                     # (x, rayons) : chaque rayon = polyligne sur la face
        self.shards = None
        self.fall_in(540.0, self.Y, "Glass.")

    def add_star(self, x, n, L):
        rays = []
        for k in range(n):
            ang = 2 * math.pi * k / n + float(self.rng.uniform(-0.25, 0.25))
            pts = [(x, self.Y + self.TH / 2)]
            px, py = x, self.Y + self.TH / 2
            for j in range(4):
                a = ang + float(self.rng.uniform(-0.35, 0.35))
                px += math.cos(a) * L / 4
                py += math.sin(a) * L / 4 * 0.35
                pts.append((clamp(px, self.X0 + 6, self.X1 - 6), clamp(py, self.Y + 4, self.Y + self.TH - 4)))
            rays.append(pts)
        self.stars.append(rays)

    def phys(self, dt, evs):
        self.vy += self.g * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if self.shards is None and self.vy > 0 and self.by + self.R >= self.Y:
            self.by = self.Y - self.R
            self.say(evs)
            if self.landings <= len(self.STARS):
                n, L = self.STARS[self.landings - 1]
                self.add_star(self.bx, n, L)
                self.hop(float(self.rng.uniform(430, 470)), float(self.rng.uniform(-90, 90)))
            else:
                self.shards = []
                cx = self.bx
                xs = sorted([self.X0, self.X1] + [float(v) for v in self.rng.uniform(self.X0 + 30, self.X1 - 30, 9)])
                for a, b in zip(xs, xs[1:]):
                    m = (a + b) / 2
                    self.shards.append({"x": m, "y": self.Y + self.TH / 2, "w": (b - a) / 2, "a": 0.0,
                                        "vx": (m - cx) * 0.6, "vy": -float(self.rng.uniform(150, 450)),
                                        "va": float(self.rng.uniform(-3, 3))})
                self.vy = 200.0
                self.vx = 0.0
                self.later("BROKE", "Zero.", "score", delay=0.35, after=0.6)
        if self.shards is not None:
            for c in self.shards:
                c["vy"] += self.g * 0.8 * dt
                c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["a"] += c["va"] * dt

    def snapshot(self):
        s = self.base_snap()
        s["stars"] = [[list(r) for r in rays] for rays in self.stars]
        s["shards"] = [dict(c) for c in self.shards] if self.shards is not None else None
        return s

    def solids_w(self, s):
        if s["shards"] is not None:
            return []
        return [("rect", self.X0, self.Y + 4, self.X1, self.Y + self.TH)]

    def focus_w(self, s):
        return (self.X0 + 60, self.Y - 40, self.X1 - 160, self.Y + self.TH)

    def bodies_w(self, s):
        if s["shards"] is None:
            return []
        return [(k, c["x"], c["y"], c["a"]) for k, c in enumerate(s["shards"]) if c["y"] < self.H]

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P)
        dr.rectangle([P(self.X0), P(self.Y), P(self.X1), P(self.H)], fill=(6, 6, 10))
        for x in (self.X0 - 34, self.X1):
            dr.rectangle([P(x), P(self.Y - 10), P(x + 34), P(self.H)], fill=(70, 70, 90))
        glass = (140, 195, 230)
        if s["shards"] is None:
            # une dalle de verre épaisse : on voit sa face, et les fissures dessus
            dr.rectangle([P(self.X0), P(self.Y), P(self.X1), P(self.Y + self.TH)], fill=glass)
            dr.rectangle([P(self.X0), P(self.Y), P(self.X1), P(self.Y + 9)], fill=(225, 245, 255))
            for k in range(4):
                xx = self.X0 + 70 + k * 190
                dr.polygon([(P(xx), P(self.Y + self.TH)), (P(xx + 60), P(self.Y + 10)), (P(xx + 90), P(self.Y + 10)), (P(xx + 30), P(self.Y + self.TH))], fill=(175, 215, 240))
            for rays in s["stars"]:
                for pts in rays:
                    dr.line([(P(x), P(y)) for x, y in pts], fill=(20, 40, 60), width=int(P(9)))
                    dr.line([(P(x), P(y)) for x, y in pts], fill=(255, 255, 255), width=int(P(5)))
                x0, y0 = rays[0][0]
                circle(dr, P(x0), P(y0), P(14), (255, 255, 255))
        else:
            for c in s["shards"]:
                ca, sa = math.cos(c["a"]), math.sin(c["a"])
                pts = [(-c["w"], -self.TH / 2), (c["w"], -self.TH / 2), (c["w"] * 0.6, self.TH / 2), (-c["w"] * 0.8, self.TH / 2)]
                dr.polygon([(P(c["x"] + dx * ca - dy * sa), P(c["y"] + dx * sa + dy * ca)) for dx, dy in pts], fill=glass)
        self.bounce(dr, P, s)


# ---------------------------------------------------------------- 4. le miel
class Honey(Matter):
    title = "HONEY"
    stamp = ("1/10", RED)
    zc = (540.0, 1230.0)
    mood = "lose"
    hold_s = 2.0
    TOP = 1250.0

    def zoom(self, s):
        # la caméra se rapproche de lui à mesure qu'il s'enfonce
        return super().zoom(s) + 0.05 * s["t"]

    def init(self):
        self.depth = 0.0
        self.h = 470.0
        self.stuck = False
        self.leave = None
        self.fall_in(540.0, self.TOP, "Honey.")

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
            self.h *= 0.82
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
        dr.rectangle([P(150), P(self.TOP - 40), P(930), P(FLOOR_Y)], fill=(80, 70, 66))
        self.bounce(dr, P, s)
        bx, by = s["bx"], s["by"]
        age = s["t"] - s["hit_t"]
        A = 16.0 * math.exp(-max(0.0, age) / 0.9) + 3.0
        xs = [170 + k * 10 for k in range(75)]
        ys = [self.TOP + A * math.sin((abs(x - bx) - 260 * age) / 38.0) * math.exp(-abs(x - bx) / 420.0) for x in xs]
        dr.polygon([(P(170), P(FLOOR_Y))] + [(P(x), P(y)) for x, y in zip(xs, ys)] + [(P(910), P(FLOOR_Y))], fill=amber)
        dr.line([(P(x), P(y)) for x, y in zip(xs, ys)], fill=light, width=int(P(10)))
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
    zc = (560.0, 1420.0)
    mood = "lose"
    hold_s = 1.8
    X0, X1, BASE = 100.0, 980.0, 1300.0
    DX = 6.0
    LANDS = 8

    def zoom(self, s):
        return super().zoom(s) + 0.03 * s["t"]

    def init(self):
        n = int((self.X1 - self.X0) / self.DX) + 1
        self.hx = np.linspace(self.X0, self.X1, n)
        self.hy = np.full(n, self.BASE) + 6 * np.sin(self.hx / 90.0)
        self.grains = []
        self.buried = False
        self.fall_in(560.0, self.BASE, "Sand.")

    def surf(self, x):
        return float(np.interp(x, self.hx, self.hy))

    def dig(self):
        """Un trou rond, plus large que lui : le fond est un arc de cercle de rayon R + 18 ;
        le sable chassé retombe en bourrelets de part et d'autre."""
        rb = self.R + 18.0
        bottom = min(self.surf(self.bx) + 30.0, FLOOR_Y - 30.0)
        yc = bottom - rb
        dx = self.hx - self.bx
        inside = np.abs(dx) < rb
        bowl = yc + np.sqrt(np.maximum(0.0, rb * rb - dx * dx))
        before = self.hy.copy()
        self.hy = np.where(inside, np.maximum(self.hy, bowl), self.hy)
        moved = float(np.sum(self.hy - before)) * self.DX
        rim = np.exp(-((np.abs(dx) - rb * 1.9) / (rb * 0.85)) ** 2) * (np.abs(dx) >= rb)
        if rim.sum() > 0:
            self.hy -= rim / (rim.sum() * self.DX) * moved * 0.85
        # les pentes trop raides s'adoucissent (sans jamais remplir le fond rond)
        for _ in range(3):
            sm = self.hy.copy()
            sm[1:-1] = (self.hy[:-2] + self.hy[1:-1] + self.hy[2:]) / 3
            self.hy = np.where(inside, self.hy, sm)

    def phys(self, dt, evs):
        for gr in self.grains:
            gr[3] += self.g * dt
            gr[0] += gr[2] * dt; gr[1] += gr[3] * dt
        self.grains = [gr for gr in self.grains if gr[1] < self.surf(gr[0]) + 4]
        if self.buried:
            # les bourrelets s'éboulent dans le trou : le sable monte à plat jusqu'à ses yeux
            cover = self.by - self.R * 0.05
            near = np.abs(self.hx - self.bx) < self.R * 2.4
            tgt = np.where(near, np.minimum(self.hy, cover), self.hy)
            self.hy += (tgt - self.hy) * min(1.0, 3.0 * dt)
            return
        self.vy += self.g * dt
        self.by += self.vy * dt
        floor_here = self.surf(self.bx) - self.R
        if self.vy > 0 and self.by >= floor_here:
            self.say(evs)
            self.dig()
            for _ in range(44):
                side = 1 if self.rng.random() < 0.5 else -1
                self.grains.append([self.bx + side * self.R * 0.8, floor_here + self.R * 0.7,
                                    side * float(self.rng.uniform(150, 420)), -float(self.rng.uniform(350, 800))])
            self.by = self.surf(self.bx) - self.R
            if self.landings >= self.LANDS:
                self.buried = True
                self.later("BURIED", "Two. He dug that hole himself.", "score", delay=0.4, after=0.4)
                return
            self.hop(440.0)

    def snapshot(self):
        s = self.base_snap(); s["hy"] = self.hy.copy(); s["grains"] = [tuple(g) for g in self.grains]; return s

    def focus_w(self, s):
        return (self.bx - 200, self.BASE - 120, self.bx + 200, FLOOR_Y)

    def scene(self, dr, s, t, S):
        P = lambda v: v * S
        self.room(dr, P, (30, 30, 50), (60, 50, 40))
        self.bounce(dr, P, s)
        sand, light = (214, 180, 120), (236, 206, 150)
        pts = [(P(self.X0), P(self.H))] + [(P(x), P(y)) for x, y in zip(self.hx, s["hy"])] + [(P(self.X1), P(self.H))]
        dr.polygon(pts, fill=sand)
        dr.rectangle([P(self.X0), P(FLOOR_Y + 40), P(self.X1), P(self.H)], fill=dim(sand, 0.8))
        dr.line([(P(x), P(y)) for x, y in zip(self.hx, s["hy"])], fill=light, width=int(P(6)))
        for (x, y, vx, vy) in s["grains"]:
            circle(dr, P(x), P(y), P(7), light)


# ---------------------------------------------------------------- 6. le trampoline
class Trampoline(Matter):
    title = "TRAMPOLINE"
    stamp = ("10/10", GREEN)
    zc = (640.0, 1100.0)

    def zoom(self, s):
        z = super().zoom(s)
        if s.get("end") is not None:
            z += 0.06 * max(0.0, s["t"] - s["end"] - 2.2)      # la caméra continue d'avancer sur lui
        return z
    mood = "win"
    hold_s = 2.6
    MAT = 1330.0
    CEIL = 430.0
    ROOF = -250.0
    MOON_Y = -9000.0
    MOON_R = 330.0
    MOON_X = 720.0

    def init(self):
        self.h = 440.0
        self.cam = 0.0
        self.camv = 0.0                      # décalage vertical de la caméra (monde -> écran)
        self.sag = 0.0
        self.sagv = 0.0
        self.phase = "room"
        self.holes = []
        self.debris = []
        self.moon_g = 420.0
        self.fall_in(540.0, self.MAT, "Trampoline.")

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
            if self.vy > 0 and self.by + self.R >= self.MAT + self.sag:
                self.by = self.MAT + self.sag - self.R
                self.say(evs)
                self.sagv += self.vy * 0.25
                self.h *= 1.55
                if self.h > 2400:
                    # le dernier saut : il ne redescend pas
                    self.phase = "space"
                    self.t_space = self.t
                    self.vy = -2600.0
                    self.talk("He's not coming down.", "space")
                    self.line("Still going.", "still", self.t + 2.6)
                else:
                    # les sauts qui crèvent le plafond, puis le toit : la voix le dit pendant le vol
                    apex = self.MAT - self.R - self.h
                    if apex - self.R < self.CEIL and not getattr(self, "_c", False):
                        self._c = True
                        self.h = max(self.h, self.h_for(self.talk("The ceiling.", "ceil")))
                    elif apex - self.R < self.ROOF and not getattr(self, "_r", False):
                        self._r = True
                        self.h = max(self.h, self.h_for(self.talk("The roof.", "roof")))
                    self.hop(self.h)
        elif self.phase == "space":
            # dans l'espace, il file vers la Lune et se pose dessus en arc
            k = clamp((self.t - self.t_space) / 4.2, 0.0, 1.0)
            sm = lambda v: v * v * (3 - 2 * v)
            y0 = self.MAT - self.R
            top = self.MOON_Y - self.MOON_R
            y1 = top - self.R
            yt = top - 520.0
            if k < 0.72:
                # il monte en passant à gauche de la Lune
                ka = k / 0.72
                self.bx = 540.0 + (250.0 - 540.0) * sm(min(1.0, ka / 0.45))
                self.by = y0 + (yt - y0) * sm(ka)
            else:
                # puis il redescend dessus en arc
                kb = (k - 0.72) / 0.28
                self.bx = 250.0 + (self.MOON_X - 250.0) * sm(kb)
                self.by = yt + (y1 - yt) * kb - 420.0 * math.sin(math.pi * kb)
            if k >= 1.0:
                self.phase = "moon"
                self.by = y1
                self.say(evs)
                T = self.talk("The Moon. Ten out of ten.", "score")
                self.later("MOON", None, None, delay=0.4)
                self.vy = -math.sqrt(2 * self.h_for(T, self.moon_g) * self.moon_g)
        else:
            self.vy += self.moon_g * dt
            self.by += self.vy * dt
            y1 = self.MOON_Y - self.MOON_R - self.R
            self.bx = self.MOON_X
            if self.vy > 0 and self.by >= y1:
                self.by = y1
                self.say(evs)
                self.vy = -math.sqrt(2 * self.moon_g * 240)
        # la caméra garde Bounce dans l'image
        # la caméra : un ressort amorti vers la position qui garde Bounce dans la bande
        sy = self.by + self.cam
        lo, hi = 760.0, 1200.0
        if self.phase == "moon":
            target = 1300.0 - (self.MOON_Y - self.MOON_R)
        elif sy < lo:
            target = self.cam + (lo - sy)
        elif sy > hi:
            target = max(0.0, self.cam - (sy - hi))
        else:
            target = self.cam
        w = 9.0
        self.camv += (w * w * (target - self.cam) - 2 * w * self.camv) * dt
        self.cam += self.camv * dt
        # jamais hors cadre, même quand il file
        sy = self.by + self.cam
        if sy < 560:
            self.cam += 560 - sy
        elif sy > 1400 and self.phase != "moon":
            self.cam = max(0.0, self.cam - (sy - 1400))

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
        if self.ROOF - 160 + c < self.H + 50:
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
