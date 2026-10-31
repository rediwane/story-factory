"""
One-off d'Halloween : Bounce vu par ceux qu'il terrorise. Une maison la nuit, une
enfant qui entend rebondir dans le couloir, un père qui va voir avec une lampe torche,
et une chose qui n'avance que quand la lumière s'éteint. Une seule source de lumière
par plan, du grain, une vignette, un narrateur grave et lent, le mot de Bounce
lointain et réverbéré qui se rapproche, une nappe sourde, un sursaut, une fin froide.

    python3 src/stories/halloween.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim

PINK = (255, 20, 200)
INK = (5, 5, 8)
WARM = (255, 214, 150)
FLOOR_Y = 1500.0


class Scene:
    """Un plan de l'histoire : pas de physique commune, chaque plan écrit la sienne."""
    title = None
    stamp = None
    mood = None
    hold_s = 0.6

    def __init__(self, cfg, rng):
        self.cfg, self.rng = cfg, rng
        self.W, self.H = cfg["width"], cfg["height"]
        self.R = cfg["ball_r"]
        self.t = 0.0
        self.lines, self.replies = [], []
        self.done = self.payoff = False
        self.outcome = None
        self.end_t = None
        self.drone = []           # (t_local, niveau 0..1)
        self.next_far = 1.0
        self.setup()

    def setup(self):
        pass

    def line(self, text, key, when=None):
        self.lines.append((self.t if when is None else when, text, key))

    def finish(self, outcome="END"):
        if not self.payoff:
            self.payoff, self.outcome, self.end_t = True, outcome, self.t

    def counter(self, s):
        return None

    def far_bounce(self, evs, gain, lo=1.1, hi=2.0):
        """Un rebond lointain, à intervalles irréguliers. Renvoie True quand il a eu lieu."""
        if self.t >= self.next_far:
            self.next_far = self.t + self.rng.uniform(lo, hi)
            evs.append(("hit", "far:%.2f" % gain))
            return True
        return False

    def figure(self, dr, P, x, y_floor, col, h=260, w=96, tilt=0.0):
        dr.rectangle([P(x - w / 2), P(y_floor - h), P(x + w / 2), P(y_floor - 12)], fill=col)
        dr.rectangle([P(x - w / 2), P(y_floor - 12), P(x - 10), P(y_floor)], fill=dim(col, 0.8))
        dr.rectangle([P(x + 10), P(y_floor - 12), P(x + w / 2), P(y_floor)], fill=dim(col, 0.8))
        circle(dr, P(x + tilt * 24), P(y_floor - h - 46), P(42), col)

    def glow(self, dr, P, x, y, r, k):
        """La lueur de Bounce : plusieurs disques de plus en plus sombres."""
        for i in range(4, 0, -1):
            circle(dr, P(x), P(y), P(r * (1 + 0.7 * i)), dim(PINK, k * (0.05 + 0.05 * (4 - i))))
        circle(dr, P(x), P(y), P(r), dim(PINK, k))


# ---------------------------------------------------------------- 1. la maison
class House(Scene):
    def setup(self):
        self.line("This happened in a house two streets from mine. Last Halloween.", "l1", 0.0)
        self.line("Nobody talks about it. So I will.", "l2", 4.6)
        self.glow_k = 0.0
        self.drone = [(0.0, 0.05), (9.0, 0.12)]

    def step(self, dt):
        self.t += dt
        evs = []
        if self.far_bounce(evs, 0.22, 1.6, 2.6):
            self.glow_k = 1.0
        self.glow_k = max(0.0, self.glow_k - 0.8 * dt)
        if self.t >= 9.5:
            self.finish()
        return evs

    def snapshot(self):
        return {"t": self.t, "glow": self.glow_k, "end": self.end_t}

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, 0, P(W), P(H)], fill=INK)
        sky = (9, 10, 20)
        dr.rectangle([0, P(430), P(W), P(1420)], fill=sky)
        circle(dr, P(860), P(640), P(70), (120, 124, 140)); circle(dr, P(890), P(622), P(64), sky)
        for i in range(30):
            circle(dr, P((i * 7919 + 311) % W), P(440 + (i * 104729 + 97) % 700), P(1.6), (90, 92, 110))
        # la maison, noire, une fenêtre faiblement rose
        hx0, hx1, hy = 240, 840, 1420
        dr.polygon([(P(hx0), P(hy)), (P(hx0), P(960)), (P(540), P(780)), (P(hx1), P(960)), (P(hx1), P(hy))], fill=(12, 12, 18))
        dr.rectangle([P(700), P(800), P(740), P(900)], fill=(12, 12, 18))
        for (wx, wy) in ((330, 1040), (650, 1040), (330, 1220), (650, 1220)):
            dr.rectangle([P(wx), P(wy), P(wx + 110), P(wy + 120)], fill=(16, 16, 24))
        # une seule fenêtre : la lueur passe
        k = s["glow"]
        dr.rectangle([P(650), P(1040), P(760), P(1160)], fill=dim(PINK, 0.06 + 0.22 * k))
        dr.rectangle([P(0), P(1420), P(W), P(H)], fill=(10, 10, 14))
        # arbre nu
        for (x0, y0, x1, y1) in ((120, 1420, 110, 1100), (110, 1100, 40, 980), (110, 1100, 170, 960), (170, 960, 150, 880)):
            dr.line([(P(x0), P(y0)), (P(x1), P(y1))], fill=(14, 14, 20), width=int(P(14)))


# ---------------------------------------------------------------- 2. la chambre
class Bedroom(Scene):
    DOOR_X0, DOOR_X1 = 880.0, 1000.0

    def setup(self):
        self.line("Their daughter kept saying something was bouncing in the hallway.", "l1", 0.0)
        self.line("Her father said it was the pipes.", "l2", 5.2)
        self.line("The pipes do not say anything.", "l3", 9.6)
        self.pass_x = None       # position de la lueur derrière la porte
        self.pass_v = 0.0
        self.k = 0.0
        self.nl = 1.0            # la veilleuse
        self.drone = [(0.0, 0.12), (14.0, 0.25)]
        self.stopped = False

    def step(self, dt):
        self.t += dt
        evs = []
        if self.t < 12.5:
            if self.far_bounce(evs, 0.35 + 0.02 * self.t, 1.0, 1.8):
                self.k = 1.0
                if self.pass_x is None:
                    self.pass_x, self.pass_v = self.DOOR_X0 - 60, 160.0
        else:
            if not self.stopped:
                self.stopped = True
                self.pass_x = (self.DOOR_X0 + self.DOOR_X1) / 2
                self.pass_v = 0.0
                evs.append(("hit", "far:0.6"))
                self.k = 1.4
        self.k = max(0.0, self.k - 1.2 * dt) if not self.stopped else min(1.4, self.k + 0.6 * dt)
        if self.pass_x is not None and not self.stopped:
            self.pass_x += self.pass_v * dt
            if self.pass_x > self.DOOR_X1 + 60:
                self.pass_x, self.pass_v = self.DOOR_X0 - 60, 160.0
        self.nl = 1.0 if (int(self.t * 7) % 23) else 0.4
        if self.t >= 15.5:
            self.finish()
        return evs

    def snapshot(self):
        return {"t": self.t, "k": self.k, "px": self.pass_x, "nl": self.nl, "stopped": self.stopped, "end": self.end_t}

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, 0, P(W), P(H)], fill=INK)
        wall = (14, 13, 20)
        dr.rectangle([0, P(430), P(W), P(FLOOR_Y)], fill=wall)
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(10, 9, 13))
        # la porte entrouverte : une fente sur le couloir
        dr.rectangle([P(self.DOOR_X0 - 20), P(760), P(self.DOOR_X1 + 20), P(FLOOR_Y)], fill=(18, 16, 24))
        dr.rectangle([P(self.DOOR_X0), P(780), P(self.DOOR_X1), P(FLOOR_Y)], fill=(3, 3, 5))
        if s["px"] is not None:
            px = s["px"]
            if self.DOOR_X0 - 70 < px < self.DOOR_X1 + 70:
                vis = max(0.0, 1 - abs(px - (self.DOOR_X0 + self.DOOR_X1) / 2) / 100)
                self.glow(dr, P, px, 1330, 60, 0.5 * s["k"] * vis)
                # la lueur ne sort pas de la fente
                dr.rectangle([P(0), P(760), P(self.DOOR_X0), P(H)], fill=wall)
                dr.rectangle([P(self.DOOR_X1), P(760), P(W), P(H)], fill=wall)
                dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(10, 9, 13))
            if s["stopped"]:
                dr.polygon([(P(self.DOOR_X0), P(FLOOR_Y)), (P(self.DOOR_X1), P(FLOOR_Y)), (P(self.DOOR_X1 - 160), P(H)), (P(self.DOOR_X0 - 200), P(H))], fill=dim(PINK, 0.06 * min(1.0, s["k"])))
        dr.rectangle([P(self.DOOR_X0 - 20), P(760), P(self.DOOR_X0), P(FLOOR_Y)], fill=(26, 22, 32))
        # le lit, l'enfant assise, la veilleuse
        nl = s["nl"]
        for i in range(4, 0, -1):
            circle(dr, P(150), P(1230), P(60 + 70 * i), dim(WARM, 0.025 * nl * (5 - i)))
        circle(dr, P(150), P(1230), P(16), dim(WARM, 0.8 * nl))
        dr.rectangle([P(140), P(1240), P(160), P(1300)], fill=(40, 36, 44))
        dr.rectangle([P(220), P(1300), P(700), P(FLOOR_Y)], fill=(28, 24, 36))
        dr.rectangle([P(220), P(1240), P(700), P(1310)], fill=(60, 56, 74))
        dr.rectangle([P(230), P(1120), P(260), P(1300)], fill=(34, 28, 36))
        self.figure(dr, P, 420, 1250, (46, 42, 60), h=150, w=76)
        dr.rectangle([P(300), P(1270), P(700), P(1310)], fill=(70, 66, 86))


# ---------------------------------------------------------------- 3. le couloir
class Hallway(Scene):
    hold_s = 0.2

    def setup(self):
        c = self.cfg
        self.line("He went to check.", "l1", 0.0)
        self.line("It never moved while the light was on it.", "l2", 6.5)
        self.line("Every time the light went out, it was closer.", "l3", 13.5)
        self.fx, self.fv = 60.0, 50.0          # le père avance lentement
        self.bx, self.by = 1010.0, FLOOR_Y - self.R
        self.torch = True
        self.torch_t = 0.0
        self.next_cut = self.rng.uniform(3.0, 4.0)
        self.cut_len = 0.0
        self.h = 0.0; self.vy = 0.0; self.on = "ground"
        self.scale = 0.45
        self.drone = [(0.0, 0.25), (10.0, 0.5), (20.0, 0.85), (23.0, 1.0)]
        self.died = None

    def step(self, dt):
        self.t += dt
        evs = []
        c = self.cfg
        # le père
        if self.fx < 330 and self.died is None:
            self.fx += self.fv * dt
        # la lampe : des coupures de plus en plus longues
        if self.died is None:
            if self.torch and self.t >= self.next_cut:
                self.torch = False
                self.cut_len = self.rng.uniform(0.6, 1.1) + 0.12 * self.t
                self.torch_t = self.t
            if not self.torch and self.t - self.torch_t >= self.cut_len:
                self.torch = True
                self.next_cut = self.t + self.rng.uniform(1.6, 2.6)
        # Bounce n'avance que dans le noir
        if not self.torch and self.died is None:
            if self.on == "ground":
                self.h = self.rng.uniform(120, 200)
                self.vy = -math.sqrt(2 * c["gravity"] * self.h)
                self.on = "air"
            self.vy += c["gravity"] * dt
            self.by += self.vy * dt
            self.bx -= c["hall_step"] * dt / 0.5
            if self.vy > 0 and self.by >= FLOOR_Y - self.R:
                self.by = FLOOR_Y - self.R
                self.on = "ground"
                g = 0.35 + 0.55 * (1 - (self.bx - 450) / 560)
                evs.append(("hit", "far:%.2f" % max(0.3, min(0.9, g))))
        else:
            if self.on == "air":
                self.vy += c["gravity"] * dt
                self.by += self.vy * dt
                if self.vy > 0 and self.by >= FLOOR_Y - self.R:
                    self.by = FLOOR_Y - self.R
                    self.on = "ground"
        self.scale = 0.45 + 0.55 * max(0.0, min(1.0, (1010 - self.bx) / 560))
        if self.bx <= 450 and self.died is None:
            self.died = self.t
            self.torch = False
            evs.append(("event", "torch dies t %.2f" % self.t))
        if self.died is not None and self.t - self.died > 1.2:
            self.finish()
        return evs

    def snapshot(self):
        return {"t": self.t, "fx": self.fx, "bx": self.bx, "by": self.by, "torch": self.torch,
                "scale": self.scale, "died": self.died, "end": self.end_t,
                "flick": (self.t - self.torch_t) if not self.torch else 9.0}

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, 0, P(W), P(H)], fill=INK)
        if s["died"] is not None:
            # noir : seule la lueur reste
            self.glow(dr, P, s["bx"], s["by"], self.R * s["scale"], 0.5)
            return
        wall = (12, 11, 17)
        dr.rectangle([0, P(430), P(W), P(FLOOR_Y)], fill=wall)
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(9, 8, 12))
        # portes le long du couloir, à peine visibles
        for x in (560, 760):
            dr.rectangle([P(x), P(820), P(x + 100), P(FLOOR_Y)], fill=(16, 14, 22))
        # la lampe torche du père
        fx = s["fx"]
        hx, hy = fx + 70, FLOOR_Y - 230
        if s["torch"]:
            flick = 1.0 if (int(t * 50) % 17) else 0.6
            reach = 1100
            dr.polygon([(P(hx), P(hy)), (P(hx + reach), P(hy - 330)), (P(hx + reach), P(hy + 420))], fill=dim(WARM, 0.07 * flick))
            dr.polygon([(P(hx), P(hy)), (P(hx + reach), P(hy - 190)), (P(hx + reach), P(hy + 260))], fill=dim(WARM, 0.11 * flick))
            # ce que la lampe touche : Bounce, immobile
            self.glow(dr, P, s["bx"], s["by"], self.R * s["scale"], 0.25)
            base.HERO["expr"] = "calm"
            base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R * s["scale"]))
            circle(dr, P(hx), P(hy), P(14), (255, 244, 210))
        else:
            # noir : une lueur qui bouge
            self.glow(dr, P, s["bx"], s["by"], self.R * s["scale"], 0.35)
        self.figure(dr, P, fx, FLOOR_Y, (22, 22, 30), h=300, w=104, tilt=0.2)
        dr.rectangle([P(hx - 36), P(hy - 12), P(hx + 10), P(hy + 12)], fill=(40, 40, 48))


# ---------------------------------------------------------------- 4. le noir
class Dark(Scene):
    hold_s = 0.3

    def setup(self):
        self.next_hit = 0.9
        self.gap = 0.9
        self.lighter = None
        self.scared = False
        self.drone = [(0.0, 1.0), (5.5, 1.0), (5.6, 0.0), (9.0, 0.0)]

    def step(self, dt):
        self.t += dt
        evs = []
        if self.lighter is None:
            if self.t >= self.next_hit:
                evs.append(("hit", "near"))
                self.gap = max(0.35, self.gap * 0.82)
                self.next_hit = self.t + self.gap
            if self.t >= 5.6:
                self.lighter = self.t
                evs.append(("hit", "scare"))
        else:
            if self.t - self.lighter >= 0.9 and not self.scared:
                self.scared = True
            if self.t - self.lighter >= 2.6:
                self.finish()
        return evs

    def snapshot(self):
        return {"t": self.t, "lighter": self.lighter, "end": self.end_t}

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, 0, P(W), P(H)], fill=(2, 2, 3))
        if s["lighter"] is None:
            return
        age = t - s["lighter"]
        if age < 0.9:
            # la flamme, et lui, en plein cadre
            fl = 1.0 if (int(t * 40) % 5) else 0.7
            for i in range(5, 0, -1):
                circle(dr, P(540), P(1240), P(120 + 110 * i), dim(WARM, 0.03 * fl * (6 - i)))
            self.glow(dr, P, 540, 1000, 300, 0.6)
            base.HERO["expr"] = "calm"
            base.ball(dr, P(540), P(1000), P(300))
            dr.polygon([(P(530), P(1300)), (P(550), P(1300)), (P(556), P(1250)), (P(540), P(1215)), (P(524), P(1250))], fill=dim(WARM, 0.9 * fl))
            dr.rectangle([P(520), P(1300), P(560), P(1380)], fill=(60, 60, 70))
        else:
            # la flamme s'est éteinte : il reste ses yeux ? non : juste la lueur, qui s'éloigne un peu
            self.glow(dr, P, 540, 1000, 300, max(0.0, 0.5 - 0.3 * (age - 0.9)))


# ---------------------------------------------------------------- 5. après
class After(Scene):
    hold_s = 0.0

    def setup(self):
        self.line("They moved out the next morning.", "l1", 0.6)
        self.line("The new family says the house is quiet.", "l2", 4.6)
        self.line("Except on Halloween.", "l3", 9.6)
        self.drone = [(0.0, 0.0), (12.0, 0.08), (14.0, 0.0)]
        self.last = False

    def step(self, dt):
        self.t += dt
        evs = []
        if self.t >= 13.2 and not self.last:
            self.last = True
            evs.append(("hit", "far:0.55"))
        if self.t >= 15.4:
            self.finish()
        return evs

    def snapshot(self):
        return {"t": self.t, "last": self.last, "end": self.end_t}

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H = self.W, self.H
        dr.rectangle([0, 0, P(W), P(H)], fill=INK)
        sky = (34, 38, 50)
        dr.rectangle([0, P(430), P(W), P(1420)], fill=sky)
        hx0, hx1, hy = 240, 840, 1420
        dr.polygon([(P(hx0), P(hy)), (P(hx0), P(960)), (P(540), P(780)), (P(hx1), P(960)), (P(hx1), P(hy))], fill=(40, 42, 54))
        dr.rectangle([P(700), P(800), P(740), P(900)], fill=(40, 42, 54))
        for (wx, wy) in ((330, 1040), (650, 1040), (330, 1220), (650, 1220)):
            dr.rectangle([P(wx), P(wy), P(wx + 110), P(wy + 120)], fill=(24, 26, 36))
        if s["last"]:
            k = min(1.0, (t - 13.2) / 0.4)
            dr.rectangle([P(650), P(1040), P(760), P(1160)], fill=dim(PINK, 0.35 * k))
        dr.rectangle([P(0), P(1420), P(W), P(H)], fill=(30, 32, 40))
        # le panneau devant la maison
        dr.rectangle([P(930), P(1200), P(944), P(1420)], fill=(60, 60, 70))
        dr.rectangle([P(870), P(1120), P(1010), P(1210)], fill=(200, 200, 208))
        dr.rectangle([P(884), P(1140), P(996), P(1150)], fill=(90, 90, 100))
        dr.rectangle([P(884), P(1164), P(970), P(1174)], fill=(90, 90, 100))
        for (x0, y0, x1, y1) in ((120, 1420, 110, 1100), (110, 1100, 40, 980), (110, 1100, 170, 960), (170, 960, 150, 880)):
            dr.line([(P(x0), P(y0)), (P(x1), P(y1))], fill=(26, 28, 36), width=int(P(14)))


# ---------------------------------------------------------------- l'histoire
class HorrorSim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        self.drone_pts = []
        super().__init__(cfg, rng)
        W, H = cfg["width"], cfg["height"]
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
        self.vignette = (1.0 - 0.8 * r ** 2.2)[..., None]
        self.grain_rng = np.random.default_rng(int(cfg["seed"]) + 99)

    def _open(self, i):
        super()._open(i)
        s = self.sims[i]
        for (tl, lvl) in getattr(s, "drone", []):
            self.drone_pts.append((self.t0 + tl, lvl))

    def drone_env(self, t):
        pts = sorted(self.drone_pts)
        if not pts:
            return 0.0
        if t <= pts[0][0]:
            return pts[0][1]
        for (ta, la), (tb, lb) in zip(pts, pts[1:]):
            if ta <= t <= tb:
                return la + (lb - la) * (t - ta) / max(1e-6, tb - ta)
        return pts[-1][1]

    def post(self, img, t):
        a = np.asarray(img).astype(np.float32)
        a *= self.vignette
        a += self.grain_rng.normal(0, 7.0, a.shape).astype(np.float32)
        a *= 1.0 + 0.02 * self.grain_rng.standard_normal()
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


DEFAULTS = {
    "ball_r": 70.0, "gravity": 3000.0,
    "hall_step": 45.0,
    "chapter_max_s": 40.0,
    "narrator_voice": "am_onyx", "narrator_length": 1.18, "narr_gap_s": 0.6,
    "hook_text_s": 4.5, "sub_y": 0.80, "sub_font_size": 50, "watermark_y": 0.93,
    "end_hold_s": 0.8, "narr_tail_s": 0.3,
    "hero_gain": 1.0, "hero_min_gap_s": 0.3, "hero_win": "", "hero_lose": "",
}

CHAPTERS = [(House, {}), (Bedroom, {}), (Hallway, {}), (Dark, {}), (After, {})]


class Sim(HorrorSim):
    pass


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
