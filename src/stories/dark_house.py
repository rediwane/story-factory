"""
One-off d'Halloween : Bounce vu par celui qu'il terrorise. Une maison la nuit, un
couloir noir, quelqu'un au premier plan avec une lampe torche. Au fond, un rebond qu'on
entend sans le voir, une lueur rose qui grossit à chaque « Bounce », la lampe qui
faiblit à mesure qu'il approche, et lui qui arrive, la même tête que d'habitude.

    python3 src/stories/dark_house.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from six_jobs import Chapter, HOP, FLOOR_Y


class DarkHouse(Chapter):
    title = None
    stamp = None
    mood = None
    hold_s = 2.0
    FAR_X, NEAR_X = 1000.0, 330.0

    def setup(self):
        c = self.cfg
        self.hop_init(self.FAR_X, FLOOR_Y, wobble=0.0, xmin=0, xmax=2000, **dict(HOP, start_h=200.0, min_h=180.0, max_h=320.0, gain=(1.0, 1.08)))
        self.R = c["ball_r"]
        self.lines = [(0.0, "Every Halloween, people in this house hear the same thing.", "l1"),
                      (4.2, "A bounce. Somewhere in the dark.", "l2"),
                      (9.0, "Then another one. Closer.", "l3"),
                      (16.0, "Nobody has ever seen what it is. It only says one word.", "l4")]
        self.replies = []
        self.step_px = c["step_px"]
        self.torch = 1.0
        self.flick = 0.0
        self.arrived = None
        self.dark = None

    def hop_go(self):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        self.vx = -self.step_px * self.rng.uniform(0.85, 1.15) / T
        self.vy = -s
        self.on = "air"

    def scale(self):
        # loin = petit et sombre, près = plein cadre
        u = (self.FAR_X - self.bx) / (self.FAR_X - self.NEAR_X)
        return max(0.0, min(1.0, u))

    def on_land(self, k, evs):
        u = self.scale()
        self.flick = 1.0
        self.torch = max(0.15, 1.0 - 0.9 * u * u)
        if self.bx <= self.NEAR_X + 10 and self.arrived is None:
            self.arrived = self.t
            self.on = "still"
            self.bx = self.NEAR_X
            evs.append(("event", "arrives t %.2f" % self.t))
            self.line("Tonight, someone finally did.", "l5", self.t + 0.2)
            self.line("It said hello.", "l6", self.t + 3.0)
            self.replies.append(("l6", 0.5))
            self.finish("DARK")

    def after(self, dt, evs):
        self.flick = max(0.0, self.flick - 3.0 * dt)
        if self.arrived is not None and self.dark is None and self.t - self.arrived > 2.6:
            self.dark = self.t
            evs.append(("hit", "torch"))

    def snapshot(self):
        s = self.base_snap()
        s["u"] = self.scale(); s["torch"] = self.torch; s["flick"] = self.flick
        s["arrived"] = self.arrived; s["dark"] = self.dark
        return s

    def draw(self, dr, s, t, S):
        P = lambda v: v * S
        W, H, R = self.W, self.H, self.R
        u = s["u"]
        torch = s["torch"] * (1.0 - 0.5 * s["flick"] * (0.5 + 0.5 * math.sin(t * 60)))
        if s["dark"] is not None:
            torch = 0.0
        # la maison : couloir noir, porte au fond éclairée par la lune
        dr.rectangle([0, P(430), P(W), P(H)], fill=(6, 6, 10))
        wall = (16, 14, 22)
        dr.rectangle([0, P(430), P(W), P(FLOOR_Y)], fill=wall)
        dr.rectangle([0, P(FLOOR_Y), P(W), P(H)], fill=(12, 10, 14))
        dr.rectangle([P(840), P(780), P(1020), P(FLOOR_Y)], fill=(22, 24, 44))
        dr.rectangle([P(856), P(796), P(1004), P(FLOOR_Y)], fill=(30, 34, 60))
        dr.rectangle([P(900), P(820), P(960), P(960)], fill=(70, 80, 120))
        for k in range(0, W, 160):
            dr.line([(P(k), P(430)), (P(k), P(FLOOR_Y))], fill=(12, 10, 16), width=int(P(3)))
        # un tableau, une horloge arrêtée : des formes dans le noir
        dr.rectangle([P(520), P(700), P(720), P(860)], fill=(24, 20, 28))
        circle(dr, P(380), P(760), P(60), (24, 20, 28)); circle(dr, P(380), P(760), P(50), (14, 12, 18))
        # la personne et la lampe torche, au premier plan à gauche
        px = 150.0
        self.figure(dr, P, px, FLOOR_Y, (30, 30, 40), h=300, w=104, tilt=-0.3 * u)
        hx, hy = px + 60, FLOOR_Y - 220
        if torch > 0.02:
            cone = dim((255, 230, 170), 0.10 + 0.22 * torch)
            reach = 300 + 700 * torch
            dr.polygon([(P(hx), P(hy)), (P(hx + reach), P(hy - 90 - 160 * torch)), (P(hx + reach), P(hy + 140 + 260 * torch))], fill=cone)
            circle(dr, P(hx), P(hy), P(14), (255, 240, 200))
        dr.rectangle([P(hx - 36), P(hy - 12), P(hx + 10), P(hy + 12)], fill=(60, 60, 70))
        # Bounce : d'abord une lueur, puis lui
        glow = dim(base.HERO["color"], 0.08 + 0.3 * u)
        for k in range(3, 0, -1):
            circle(dr, P(s["bx"]), P(s["by"]), P(R * (1.2 + 0.9 * k) * (0.5 + 0.8 * u)), dim(glow, 0.35 + 0.2 * (3 - k)))
        if s["dark"] is not None:
            # noir complet, il ne reste que lui
            dr.rectangle([0, P(430), P(W), P(H)], fill=(4, 4, 6))
            base.ball(dr, P(s["bx"]), P(s["by"]), P(R))
            return
        if u > 0.35 or s["arrived"] is not None:
            base.ball(dr, P(s["bx"]), P(s["by"]), P(R))
        else:
            circle(dr, P(s["bx"]), P(s["by"]), P(R * (0.4 + 0.6 * u / 0.35)), dim(base.HERO["color"], 0.25 + 0.6 * u / 0.35))


DEFAULTS = {
    "ball_r": 74.0, "gravity": 3000.0,
    "step_px": 24.0,
    "chapter_max_s": 40.0,
    "hook_text_s": 4.0, "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 0.6, "narr_tail_s": 0.3,
    "hero_gain": 1.0, "hero_min_gap_s": 0.6,
}

CHAPTERS = [(DarkHouse, {})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
