"""
Prototype « Grounded » : le personnage d’un fan (Grounded, ou Anti-Bounce : Bounce en couleurs inversées,
qui déteste que Bounce rebondisse). Il essaie de l’immobiliser : il lui saute dessus, lui lâche un livre,
une caisse, un poids d’une tonne ; Bounce ressort chaque fois, et le poids finit par sauter avec Grounded
dessus. Pour finir, il l’attrape à bras-le-corps… et se retrouve collé à lui, forcé de rebondir.

Grounded ne dit que son nom (banque hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/grounded.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------------------------------------------ la voix de Snooze
BANK, ENV = {}, {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def load_bank(cfg):
    path = cfg.get("voice_bank")
    if not path:
        raise SystemExit("voice_bank manquant dans la config")
    for key, fn in LINES.items():
        x = _read(os.path.join(path, fn))
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2 * (GAIN.get(key, 1.0))
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def snooze_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = snooze_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Snooze suit sa voix
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word



# ------------------------------------------------------------------ Grounded
WHO = "Grounded"
LINES = {"dit": "dit.wav", "fort": "fort.wav", "las": "las.wav"}
GAIN = {"fort": 1.15}

W, H = 1080, 1920
R = 100.0
RB = 100.0
CEIL = 470.0
FLOOR = 1500.0
FY = FLOOR - RB
G = 2600.0
G_HALO, G_DISC, G_INK = (240, 168, 214), (228, 100, 172), (252, 250, 252)   # Bounce en couleurs inversées
BOOK, CRATE, IRON = (70, 90, 150), (150, 110, 64), (70, 72, 82)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def arc(t, t0, x0, y0, t1, x1, y1, cap=CEIL + RB):
    d = max(1e-6, t1 - t0)
    s = (t - t0) / d
    h = min(0.5 * G * (d / 2) ** 2, 700.0)
    top = max(min(y0, y1) - h, cap)
    a0, a1 = max(0.0, y0 - top), max(0.0, y1 - top)
    sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
    if s <= sm:
        u = s / sm if sm > 0 else 1
        y = top + a0 * (1 - u) ** 2
    else:
        u = (s - sm) / (1 - sm) if sm < 1 else 1
        y = top + a1 * u ** 2
    return lerp(x0, x1, s), y


def draw_grounded(dr, x, y, r, S, mood="furieux", talk=0.0, sq=0.0, rot=0.0):
    """Grounded, d'après le dessin du fan : Bounce en couleurs inversées (halo rose pâle, disque
    rose), sourcils blancs en colère, yeux blancs, bouche blanche en grimace."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=G_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=G_DISC)
    ca, sa = math.cos(rot), math.sin(rot)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.08 * r * S))
    if mood == "las":
        dr.line([P(-0.48, -0.30), P(-0.14, -0.26)], fill=G_INK, width=w); dr.line([P(0.14, -0.26), P(0.48, -0.30)], fill=G_INK, width=w)
        for ex in (-0.3, 0.3):
            dr.line([P(ex - 0.1, -0.08), P(ex + 0.1, -0.08)], fill=G_INK, width=w)
        dr.line([P(-0.2, 0.40), P(0.2, 0.40)], fill=G_INK, width=w)
        return
    dr.line([P(-0.50, -0.42), P(-0.14, -0.26)], fill=G_INK, width=w)
    dr.line([P(0.14, -0.26), P(0.50, -0.42)], fill=G_INK, width=w)
    big = 1.3 if mood == "panique" else 1.0
    for ex in (-0.30, 0.30):
        rr = 0.12 * big
        dr.ellipse([*P(ex - rr, -0.10 - rr), *P(ex + rr, -0.10 + rr)], fill=G_INK)
    o = 0.06 * talk
    if mood == "panique":
        dr.ellipse([*P(-0.12, 0.26), *P(0.12, 0.52 + o)], fill=G_INK)
    else:
        dr.line([P(-0.28, 0.46), P(-0.1, 0.32 - o), P(0.12, 0.30 - o), P(0.30, 0.44)], fill=G_INK, width=w, joint="curve")


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        C, L = [], []

        def c(t, x, y, hard=True):
            C.append((t, float(x), float(y), hard))
        PIN_Y = FY + 30
        self.pins = []                                  # (t0, t1, x, quoi)
        # l'intro
        for i, x in enumerate((260, 340, 280)):
            c(0.6 + 1.0 * i, x, FY)
        # 1. Grounded lui saute dessus
        c(3.6, 380, FY); self.pins.append((3.6, 5.2, 380.0, "lui")); L.append((4.55, "dit"))
        c(6.2, 560, FY); c(7.1, 480, FY); c(7.95, 600, FY); c(8.8, 520, FY)
        # 2. le gros livre
        c(9.6, 450, FY); self.pins.append((9.6, 11.2, 450.0, "livre")); L.append((10.55, "dit"))
        c(12.2, 640, FY); c(13.1, 560, FY); c(13.95, 680, FY); c(14.8, 600, FY)
        # 3. la caisse : il rebondit dedans, la caisse saute avec lui
        self.crate = (15.6, 21.8)
        c(15.6, 520, FY); L.append((16.55, "dit"))
        for k, x in enumerate((600, 680, 600, 700, 760)):
            c(17.5 + 0.95 * k, x, FY)
        c(22.8, 600, FY); c(23.8, 500, FY)
        # 4. le poids d'une tonne, et Grounded fier dessus
        c(25.0, 420, FY); self.pins.append((25.0, 27.6, 420.0, "poids")); L.append((26.3, "dit"))
        self.weight_hops = []
        t = 27.6
        for k in range(3):
            t += 0.8 + 0.14 * k
            c(t, 420, FY); self.weight_hops.append(t)
        L.append((t + 0.95, "fort"))                     # il se cogne au plafond
        self.t_weight_off = t + 1.95
        c(t + 1.95, 600, FY); c(t + 2.85, 520, FY)
        # 5. il l'attrape à bras-le-corps… et rebondit avec lui
        self.t_grab = t + 3.75
        c(self.t_grab, 480, FY)
        tt = self.t_grab
        xs = [560, 680, 820, 700, 560, 420, 300, 420, 560, 700, 820, 700, 560, 440]
        k = 0
        while tt < 59.9:
            tt += 1.05
            c(tt, xs[k % len(xs)], FY); k += 1
            if k == 1:
                tt += 1.0                               # la place de son « Oh no »
            if k in (2, 6, 11):
                L.append((tt + 0.95, "las"))            # « Grounded… » : son pire cauchemar
                tt += 1.0
        self.C = sorted(C)
        self.hits = [(e[0], "dur") for e in self.C if e[3]]
        self.hi = 0
        self.lines = [(tl, WHO + " " + k, f"g{i}") for i, (tl, k) in enumerate(sorted(L))]
        self.payoff_at = self.t_grab + 1.75
        self.end_s = 61.8
        # les positions de Grounded hors attache : (t, x, y)
        self.gk = [(0.0, 860.0, FY), (2.9, 860.0, FY), (3.6, 380.0, FY - 2 * R + 30),
                   (5.2, 380.0, FY - 2 * R + 30), (6.3, 830.0, FY), (9.0, 830.0, FY), (15.0, 860.0, FY),
                   (24.2, 860.0, FY), (25.8, 420.0, FY + 30 - RB - 190 - R), (27.6, 420.0, FY + 30 - RB - 190 - R)]
        self.PIN_Y = PIN_Y

    def bounce_at(self, t):
        for (a, b, x, _) in self.pins:
            if a <= t <= b:
                return x + 4 * math.sin(t * 70), self.PIN_Y + 3 * math.sin(t * 53)
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 200.0, 800.0, C[0][0], C[0][1], C[0][2])
        prev = None
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                y0 = self.PIN_Y if any(abs(p[1] - a[0]) < 1e-6 for p in self.pins) else a[2]
                t0 = a[0]
                for p in self.pins:
                    if abs(p[0] - a[0]) < 1e-6:
                        t0, y0 = p[1], self.PIN_Y
                return arc(t, t0, a[1], y0, b[0], b[1], b[2])
        return C[-1][1], C[-1][2]

    def grounded_at(self, t):
        """(x, y, mood, rot)"""
        bx, by = self.bounce_at(t)
        if t >= self.t_grab - 0.6:
            if t < self.t_grab:                          # le saut pour l'attraper
                s = (t - (self.t_grab - 0.6)) / 0.6
                x, y = lerp(860, bx + 1.7 * R, s), lerp(FY, by, s) - 200 * math.sin(math.pi * s)
                return x, y, "furieux", 0.0
            return bx + 1.75 * R, by, "panique", 0.3 * math.sin(t * 9)
        if self.weight_hops and self.pins[2][1] <= t < self.t_weight_off:
            return bx, by - RB - 190 - R, "panique", 0.0   # sur le poids, qui saute
        gk = self.gk
        for a, b in zip(gk, gk[1:]):
            if a[0] <= t <= b[0]:
                if abs(a[1] - b[1]) < 1 and abs(a[2] - b[2]) < 1:
                    return a[1], a[2], "furieux", 0.0
                x, y = arc(t, a[0], a[1], a[2], b[0], b[1], b[2])
                return x, y, "furieux", 0.0
        if t < 3.6 + 0.01:
            return 860.0, FY, "furieux", 0.0
        return gk[-1][1], gk[-1][2], "furieux", 0.0

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "colles"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                return 0.0 if e is None else float(e[min(int((t - n["start"]) * 60), len(e) - 1)])
        return 0.0

    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        wall = (30, 30, 40)
        rect(0, CEIL, W, FLOOR, wall)
        rect(0, CEIL - 8, W, CEIL, dim(wall, 0.6))
        rect(0, FLOOR, W, H, (46, 44, 52))
        # un mur rangé au cordeau : des cadres bien droits
        for (x0, y0) in ((120, 640), (420, 600), (760, 660)):
            dr.rectangle([x0 * S, y0 * S, (x0 + 180) * S, (y0 + 130) * S], outline=(80, 80, 96), width=int(6 * S))
        bx, by = self.bounce_at(t)
        # le livre, la caisse, le poids
        a, b, xp, _ = self.pins[1]
        if t >= a - 0.5:
            if t < a:
                s = (t - (a - 0.5)) / 0.5; ly = lerp(CEIL, self.PIN_Y - RB - 30, s * s); lx, rot = xp, 0.0
            elif t <= b:
                lx, ly, rot = xp, self.PIN_Y - RB - 30, 0.0
            else:
                s = min(1.0, (t - b) / 0.9); lx = xp - 260 * s; ly = lerp(self.PIN_Y - RB - 30, FLOOR - 30, s) - 360 * math.sin(math.pi * s); rot = 3.2 * s
            ca, sa = math.cos(rot), math.sin(rot)
            pts = [(lx + u * ca - v * sa, ly + u * sa + v * ca) for u, v in ((-120, -30), (120, -30), (120, 30), (-120, 30))]
            dr.polygon([(p[0] * S, p[1] * S) for p in pts], fill=BOOK)
        crate_on = self.crate[0] - 0.4 <= t <= self.crate[1]
        a, b, xw, _ = self.pins[2]
        if t >= a - 0.5:
            if t < a:
                s = (t - (a - 0.5)) / 0.5; wx, wy = xw, lerp(CEIL - 100, self.PIN_Y - RB - 90, s * s)
            elif t < self.t_weight_off:
                wx, wy = (xw, self.PIN_Y - RB - 90) if t <= b else (bx, by - RB - 90)
            else:
                s = min(1.0, (t - self.t_weight_off) / 0.6); wx, wy = lerp(xw, 140, s), lerp(by - RB - 90, FLOOR - 90, s)
            dr.polygon([((wx - 110) * S, (wy + 90) * S), ((wx + 110) * S, (wy + 90) * S), ((wx + 80) * S, (wy - 70) * S), ((wx - 80) * S, (wy - 70) * S)], fill=IRON)
            dr.rectangle([(wx - 30) * S, (wy - 100) * S, (wx + 30) * S, (wy - 70) * S], fill=IRON)
            dr.text((wx * S, (wy + 20) * S), "1 TON", fill=(230, 230, 236), anchor="mm", font=font(int(46 * S)))
        # Grounded
        gx, gy, mood, rot = self.grounded_at(t)
        if any(n["start"] <= t <= n["end"] + 0.3 and n["text"].endswith("las") for n in self.narr):
            mood = "las"
        draw_grounded(dr, gx, gy, R, S, mood=mood, talk=self.talking(t), rot=rot)
        base.ball(dr, bx * S, by * S, RB * S)
        if crate_on:
            s = min(1.0, (t - (self.crate[0] - 0.4)) / 0.4)
            cx, cy = (bx, lerp(CEIL, by, s * s)) if t < self.crate[0] else (bx, by)
            k = max(0.0, (t - (self.crate[1] - 0.5)) / 0.5)
            ca, sa = math.cos(1.3 * k), math.sin(1.3 * k)
            pts = [(cx + u * ca - v * sa + 160 * k, cy + u * sa + v * ca) for u, v in ((-150, -160), (150, -160), (150, 100), (-150, 100))]
            dr.polygon([(p[0] * S, p[1] * S) for p in pts], fill=CRATE)
            dr.line([(pts[0][0] * S, pts[0][1] * S), (pts[2][0] * S, pts[2][1] * S)], fill=(110, 80, 46), width=int(8 * S))


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
