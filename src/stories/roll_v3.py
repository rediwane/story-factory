"""
Prototype « Roll » v3 : un fil de funambule au-dessus du vide, sous un chapiteau.
Roll (le personnage d'un fan, une balle verte qui roule) traverse la corde ; Bounce lui
rebondit sur la tête. Au milieu, la corde s'amincit en six fils : chaque « Bounce » sur
Roll posé sur ce point faible en fait claquer un. Quand Bounce tombe sur la corde, elle
se creuse sans bruit et le renvoie. Au dernier fil, la corde fait fronde et les renvoie
tous les deux au départ.

Roll ne dit que son nom (banque hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/roll_v3.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR


# ------------------------------------------------------------------ réverbération en FFT (même résultat que base.reverb)
def reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    m = len(x) + len(ir) - 1
    nf = 1 << (m - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:m]
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = reverb_fft

# ------------------------------------------------------------------ la voix de Roll (banque)
WHO = "Roll"
LINES = {"joie": "joie.wav", "q": "q.wav"}
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
        x *= 0.2
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Roll suit sa voix
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce : la prise la plus nette
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.76:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
R = 120.0                       # Roll et Bounce
G = 2600.0
Y0 = 1045.0                     # la corde, aux faces des plateformes
AX, BX = 250.0, 760.0           # ses deux attaches
PTOP = 990.0                    # dessus des plateformes (une marche au-dessus de la corde)
SP0, SP1, SPC = 420.0, 590.0, 505.0   # le point faible
NF = 6                          # fils au départ
LEVEL = [10, 50, 90, 130, 170, 205]   # creux sous Roll au point faible, par palier (px sous Y0)

R_DISC, R_RING, R_HALO, R_INK = (26, 236, 40), (22, 70, 26), (10, 32, 14), (10, 12, 10)
ROPE, ROPE_D = (214, 196, 160), (140, 120, 92)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def arc(t, t0, x0, y0, t1, x1, y1, cap):
    d = max(1e-6, t1 - t0)
    s = max(0.0, min(1.0, (t - t0) / d))
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


def env(x):
    u = (x - AX) / (BX - AX)
    return math.sqrt(max(0.0, math.sin(math.pi * max(0.0, min(1.0, u)))))


def draw_roll_halo(dr, x, y, r, S, sq=0.0):
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=R_HALO)


def draw_roll(dr, x, y, r, S, rot=0.0, talk=0.0, sq=0.0):
    """Roll, d'après le dessin du fan, aux proportions de Bounce (le halo est dessiné à part, sous la corde)."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=R_RING)
    dr.ellipse([(x - 0.8 * r * sx) * S, (y - 0.8 * r * sy) * S, (x + 0.8 * r * sx) * S, (y + 0.8 * r * sy) * S], fill=R_DISC)
    ca, sa = math.cos(rot), math.sin(rot)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.11 * r * S))
    for side in (-1, 1):
        ex = 0.30 * side
        dr.line([P(ex - 0.16, -0.12), P(ex, -0.30), P(ex + 0.16, -0.12)], fill=R_INK, width=w, joint="curve")
    o = 0.28 + 0.12 * talk
    pts = [P(0.30 * math.cos(math.pi * k / 16), 0.10 + o * math.sin(math.pi * k / 16)) for k in range(17)]
    dr.polygon(pts, fill=R_INK)


# ------------------------------------------------------------------ le plan
# contacts durs (sur Roll) : temps ; contacts mous (sur la corde) : (temps, x)
HARD = [0.40, 1.40, 2.26, 5.02, 5.88, 6.76, 7.62, 8.49, 11.39, 12.25, 13.12, 16.09, 16.95, 17.83, 20.67, 21.53,
        24.52, 25.39, 27.95, 28.81, 29.68, 32.66, 33.52, 34.40, 35.27, 38.22, 39.08, 41.80, 42.67, 45.60, 46.46,
        47.32, 48.20, 49.22, 50.08, 50.95, 53.18, 54.16, 55.12, 55.98, 56.85, 57.73, 59.26, 61.38]
SOFT = [(3.11, 680), (3.96, 700), (9.44, 715), (10.39, 745), (14.07, 330), (15.07, 340), (18.78, 690), (19.68, 720),
        (22.48, 640), (23.51, 650), (26.34, 700), (27.05, 745), (30.63, 640), (31.66, 650), (36.22, 390),
        (37.22, 340), (40.03, 750), (40.78, 755), (43.62, 730), (44.60, 740), (51.90, 440), (60.31, 620)]
LINES_AT = [(3.21, "q"), (9.89, "joie"), (14.57, "joie"), (19.18, "q"), (22.83, "q"), (26.70, "joie"), (31.08, "q"),
            (36.51, "q"), (40.49, "joie"), (44.00, "q")]
SNAPS = [7.62, 20.67, 27.95, 38.22, 46.46]          # un fil claque
FIBRES = [3.11, 13.12, 18.78, 26.34, 28.81, 40.03, 43.62]   # des fibres giclent, un fil s'amincit
SLING = (57.73, 57.95)                               # le dernier fil se tend, puis lâche
FLIGHT = (57.95, 59.21)
TI = 59.26                                           # l'issue : Bounce retombe sur Roll au départ
RELAUNCH = 61.38
END = 62.26
HALF = (762.0, 870.0)                                # Roll à moitié sur la plateforme, en appui sur le coin

# Roll : (t, x, lift) ; lift < 0 = soulevé au-dessus de la corde
ROLL_K = [
    (0.0, 370, 0), (2.0, 395, 0), (3.11, 410, 0), (4.0, 425, 0), (5.02, 425, 0), (5.25, 405, 0), (5.88, 440, 0),
    (6.76, 495, 0), (7.62, 505, 0), (8.49, 505, 0), (8.95, 445, 0), (10.2, 505, 0), (13.12, 505, 0),
    (13.8, 570, 0), (16.09, 590, 0), (16.95, 600, 0), (17.83, 600, 0), (18.4, 505, 0), (18.95, 430, 0),
    (20.4, 505, 0), (21.53, 505, 0), (22.4, 370, 0), (22.6, 385, 0), (22.8, 372, 0), (24.52, 372, 0),
    (25.39, 420, 0), (27.6, 505, 0), (29.68, 505, 0), (30.35, 370, 0), (30.6, 388, 0), (30.85, 372, 0),
    (31.1, 382, 0), (31.4, 375, 0), (32.66, 380, 0), (33.52, 450, 0), (34.2, 640, 0), (34.40, 640, 0),
    (34.6, 640, -20), (34.85, 640, 0), (35.27, 640, 0), (35.5, 640, -40), (35.8, 640, 0), (36.22, 640, 0),
    (37.22, 600, 0), (38.1, 505, 0), (41.80, 505, 0), (42.3, 540, 0), (42.67, 540, 0), (43.2, 480, 0),
    (43.62, 480, 0), (45.4, 505, 0), (47.32, 505, 0), (47.8, 580, 0), (48.20, 580, 0), (48.6, 620, 0),
    (49.22, 620, 0), (49.6, 610, 0), (50.08, 610, 0), (50.4, 640, 0), (50.95, 640, 0), (51.3, HALF[0], 1),
    (53.18, HALF[0], 1), (53.5, 640, 0), (54.16, 640, 0), (54.5, HALF[0], 1), (55.12, HALF[0], 1),
    (55.9, 505, 0), (57.95, 505, 0)]
# après la fronde : (59.13, 370) ; puis il roule vers le point faible
SPINS = [(39.08, 1.2, 2 * math.pi), (21.53, 0.9, -2 * math.pi), (29.68, 0.7, -2 * math.pi)]   # (t, durée, tour en plus)
TREMBLE = [(16.95, 17.7), (51.3, 53.18), (46.46, 47.3)]


class Sim:
    scene_top = 0.20

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.payoff_at = TI + 0.90
        self.end_s = END
        evs = [(t, "hit", "dur") for t in HARD] + [(t, "event", "mou") for t, _ in SOFT]
        self.evs = sorted(evs)
        self.ei = 0
        self.lines = [(t, WHO + " " + k, f"r{i}") for i, (t, k) in enumerate(LINES_AT)]
        rng2 = np.random.default_rng(11)
        # le public : des têtes minuscules
        self.crowd = []
        y = 1335.0
        row = 0
        while y < 1760:
            x = -10.0 + (row % 2) * 13
            while x < W + 10:
                self.crowd.append((x + rng2.uniform(-4, 4), y + rng2.uniform(-3, 3), rng2.uniform(8, 12),
                                   tuple(int(c) for c in rng2.integers(24, 46, 3)), rng2.uniform(0, 6.28)))
                x += rng2.uniform(24, 30)
            y += 30 + row * 1.5
            row += 1
        # fibres : petites particules par évènement
        self.fib = []
        for t0 in FIBRES + SNAPS:
            for k in range(22 if t0 in SNAPS else 16):
                a = rng2.uniform(-math.pi, 0.0) if k % 2 else rng2.uniform(0, math.pi)
                self.fib.append((t0, rng2.uniform(SP0 + 20, SP1 - 20), a, rng2.uniform(160, 380), rng2.uniform(30, 52)))
        self.tuft = [(rng2.uniform(-1.4, 1.4), rng2.uniform(24, 46)) for _ in range(16)]
        # Bounce : ses points de passage
        self._bounce_pts()

    # ---------------------------------------------------------------- état
    def level(self, t):
        k = sum(1 for s in SNAPS if t >= s + 0.08)
        return LEVEL[k]

    def threads(self, t):
        return NF - sum(1 for s in SNAPS if t >= s)

    def rope_base(self, x, t):
        """Creux statique de la corde sous une charge posée en x."""
        lv = self.level(t)
        bump = math.exp(-((x - SPC) / 95.0) ** 2)
        return Y0 + (12 + (lv - 12) * bump) * env(x)

    def dyn(self, t):
        """Plongée dynamique de la corde sous Roll après chaque choc."""
        d = 0.0
        for th in HARD:
            if 0 <= t - th < 0.7:
                a = 18.0 + 10.0 * (th in SNAPS)
                d += a * math.exp(-(t - th) * 7) * math.cos(2 * math.pi * 2.4 * (t - th))
        return d

    def roll_state(self, t):
        """(x, y, rot, squash) du centre de Roll."""
        sq = 0.0
        self._lift = 0.0
        for th in HARD:
            if 0 <= t - th < 0.2:
                sq = max(sq, 0.13 * math.exp(-(t - th) * 9))
        if SLING[0] <= t < SLING[1]:
            sq = 0.22
        if t >= FLIGHT[0]:
            if t < FLIGHT[1]:
                x0, y0 = SPC, Y0 + 213 - R
                x1, y1 = 370.0, self.rope_base(370, t) - R
                x, y = arc(t, FLIGHT[0], x0, y0, FLIGHT[1], x1, y1, 640)
                rot = -2 * math.pi * ease((t - FLIGHT[0]) / (FLIGHT[1] - FLIGHT[0]))
                return x, y, rot, 0.0
            x = 370.0 if t < RELAUNCH else lerp(370.0, 420.0, ease((t - RELAUNCH) / (END - RELAUNCH)))
            y = self.rope_base(x, t) - R + 0.5 * self.dyn(t)
            return x, y, 0.0, sq
        K = ROLL_K
        x, lift = K[-1][1], K[-1][2]
        for a, b in zip(K, K[1:]):
            if a[0] <= t <= b[0]:
                s = ease((t - a[0]) / max(1e-6, b[0] - a[0]))
                x = lerp(a[1], b[1], s)
                la = HALF[1] - (self.rope_base(a[1], t) - R) if a[2] == 1 else a[2]
                lb = HALF[1] - (self.rope_base(b[1], t) - R) if b[2] == 1 else b[2]
                lift = lerp(la, lb, s)
                break
        else:
            lift = 0
        if t < K[0][0]:
            x = K[0][1]
        self._lift = lift
        y = self.rope_base(x, t) - R + lift
        if lift > -1:
            y = min(y + self.dyn(t), 1258.0 - R)
            if SLING[0] <= t < SLING[1]:
                y = Y0 + 205 + 8 * (t - SLING[0]) / (SLING[1] - SLING[0]) - R
        if lift > -1:
            y += R * sq                                   # écrasé, il garde le bas sur la corde
        rot = 0.0
        for (ts, d, turn) in SPINS:
            if t >= ts:
                rot += turn * ease((t - ts) / d)
        # tangage après les chocs, tremblement
        for th in HARD:
            if 0 <= t - th < 1.2:
                rot += 0.16 * math.exp(-(t - th) * 3.5) * math.sin(2 * math.pi * 1.6 * (t - th))
        for (a, b) in TREMBLE:
            if a <= t <= b:
                x += 2.5 * math.sin(t * 70)
                rot += 0.04 * math.sin(t * 55)
        return x, y, rot, sq

    def _bounce_pts(self):
        pts = []
        for th in HARD:
            pts.append((th, "H", None))
        for ts, xs in SOFT:
            pts.append((ts, "S", xs))
        pts.append((SLING[1], "V", None))
        self.bp = []
        for (t, k, xs) in sorted(pts):
            if k == "H":
                rx, ry, _, sq = self.roll_state(t)
                self.bp.append((t, rx, ry - R * (1 - sq) - R))
            elif k == "S":
                self.bp.append((t, float(xs), min(self.rope_base(xs, t) + 70, 1255.0) - R))
            else:
                self.bp.append((t, SPC, Y0 + 213 - R - 2 * R))
        # avant le premier contact : il tombe vers Roll
        self.bp.insert(0, (-0.45, 370.0, self.bp[0][2]))
        self.bp.append((END + 0.86, 420.0, self.bp[-1][2]))

    def bounce_at(self, t):
        if FLIGHT[0] <= t <= TI:                          # la fronde : il vole juste au-dessus de Roll
            rx, ry, _, _ = self.roll_state(t)
            u = min(1.0, (t - FLIGHT[0]) / (TI - FLIGHT[0]))
            return rx, ry - 2 * R - 30 * math.sin(math.pi * u)
        bp = self.bp
        for a, b in zip(bp, bp[1:]):
            if a[0] <= t <= b[0]:
                cap = 445.0 if t < 8.6 else 360.0
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2], cap)
        return bp[-1][1], bp[-1][2]

    def soft_contact(self, t):
        """Bounce dans la corde : (x, y du point de corde) ou None."""
        bx, by = self.bounce_at(t)
        for ts, xs in SOFT:
            if abs(t - ts) < 0.35:
                yb = self.rope_base(bx, t)
                if by + R > yb:
                    return bx, by + R
        return None

    # ---------------------------------------------------------------- moteur
    def step(self, dt):
        out = []
        self.t += dt
        # le mot part à l'image du contact (base.simulate note l'évènement au début du pas)
        while self.ei < len(self.evs) and self.evs[self.ei][0] <= self.t - dt + 1e-6:
            out.append((self.evs[self.ei][1], self.evs[self.ei][2]))
            self.ei += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            out.append(("payoff", "retour au départ"))
        if self.t >= self.end_s:
            self.done = True
        return out

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

    def crowd_dy(self, t):
        d = 0.0
        for s in SNAPS + [33.52, 50.95]:
            if 0 <= t - s < 1.4:
                d = min(d, -9 * math.sin(math.pi * (t - s) / 1.4))
        if 46.46 <= t < 57.7:
            d = min(d, -5)
        if SLING[0] <= t < TI + 1.5:
            d = -10
        return d

    # ---------------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        def R_(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)

        def L_(pts, col, w):
            dr.line([(a * S, b * S) for a, b in pts], fill=col, width=max(1, int(w * S)), joint="curve")

        # le chapiteau
        for i in range(-6, 7):
            col = (46, 14, 24) if i % 2 else (14, 18, 40)
            dr.polygon([(540 * S, -260 * S), ((540 + i * 190) * S, 250 * S), ((540 + (i + 1) * 190) * S, 250 * S)], fill=col)
        R_(0, 248, W, 256, (30, 22, 30))
        # le cône du projecteur, jusqu'au sable
        dr.polygon([(520 * S, 0), (560 * S, 0), (660 * S, 1800 * S), (350 * S, 1800 * S)], fill=(22, 22, 30))
        # la piste et le public, minuscules, loin dessous
        dr.ellipse([200 * S, 1770 * S, 880 * S, 1860 * S], fill=(58, 46, 34))
        dr.ellipse([420 * S, 1788 * S, 590 * S, 1830 * S], fill=(110, 100, 80))
        cdy = self.crowd_dy(t)
        for i, (x, y, r, col, ph) in enumerate(self.crowd):
            yy = y + cdy * (0.6 + 0.4 * math.sin(ph)) + (y - 1335) * 0.0
            dr.ellipse([(x - r) * S, (yy - r) * S, (x + r) * S, (yy + r) * S], fill=col)
        for k in range(14):
            yb = 1352 + k * (31 + k * 1.5)
            R_(0, yb, W, yb + 3, (20, 18, 24))
        # les mâts et leurs échelles, qui sortent du cadre
        for (ra, rb) in ((95, 150), (915, 970)):
            R_(ra, 1080, ra + 7, H, (70, 52, 38)); R_(rb, 1080, rb + 7, H, (70, 52, 38))
            y, gap = 1110.0, 64.0
            while y < H:
                R_(ra, y, rb + 7, y + 5, (62, 46, 34))
                y += gap
                gap = max(14.0, gap * 0.86)
        # les plateformes
        for (x0, x1) in ((0, AX), (BX, W)):
            R_(x0, PTOP, x1, PTOP + 90, (96, 66, 42))
            R_(x0, PTOP, x1, PTOP + 10, (132, 94, 60))
            for k in range(int(x0) + 30, int(x1), 60):
                R_(k, PTOP + 12, k + 3, PTOP + 88, (76, 52, 34))
        # le point faible, au centre du projecteur : la zone la plus claire
        yc = Y0 + 25
        dr.ellipse([(SPC - 150) * S, (yc - 75) * S, (SPC + 150) * S, (yc + 75) * S], fill=(40, 40, 56))
        dr.ellipse([(SPC - 105) * S, (yc - 50) * S, (SPC + 105) * S, (yc + 50) * S], fill=(58, 58, 76))
        # la corde : polyligne par les charges (le halo de Roll dessous, Roll dessus)
        rx, ry, rrot, rsq = self.roll_state(t)
        draw_roll_halo(dr, rx, ry, R, S, rsq)
        draw_roll(dr, rx, ry, R, S, rot=rrot, talk=self.talking(t), sq=rsq)   # la corde passe devant lui
        on_rope = not (FLIGHT[0] <= t < FLIGHT[1]) and (t >= FLIGHT[1] or self._lift > -1)
        pts = []
        if on_rope:
            pts.append((rx, ry + R * (1 - rsq)))
        sc = self.soft_contact(t)
        if sc is not None and (not on_rope or abs(sc[0] - rx) > 60):
            pts.append(sc)
        if FLIGHT[0] <= t < FLIGHT[1] + 0.6:                 # la fronde : la corde remonte, oscille, revient droite
            u = t - FLIGHT[0]
            yo = Y0 - 90 * math.exp(-u * 4.5) * math.cos(2 * math.pi * 1.8 * u)
            if t < FLIGHT[1] and ry + R > yo - 1:            # tant qu'elle le pousse, elle reste sous lui
                pts.append((rx, ry + R))
            else:
                pts.append((SPC, yo))
        pts = [(AX, Y0)] + sorted(pts) + [(BX, Y0)]

        def rope_y(x):
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                if xa <= x <= xb:
                    return lerp(ya, yb, (x - xa) / max(1e-6, xb - xa))
            return Y0
        # la corde torsadée, hors du point faible
        for (xa, xb) in ((AX, SP0), (SP1, BX)):
            xs = np.linspace(xa, xb, 30)
            L_([(x, rope_y(x)) for x in xs], ROPE, 22)
            x = xa + 4
            while x < xb - 4:
                y = rope_y(x)
                L_([(x - 6, y + 10), (x + 6, y - 10)], ROPE_D, 4)
                x += 13
        # le point faible : des fils fins, des touffes, la barbe
        n = self.threads(t)
        k_snap = NF - n
        widths = [7.0, 6.2, 5.4, 4.6, 3.8, 3.0]
        cols = [(214, 196, 160), (222, 208, 178), (230, 220, 196), (236, 230, 214), (242, 238, 228), (250, 248, 244)]
        wth, col = widths[k_snap], cols[k_snap]
        tense = SLING[0] <= t < SLING[1]
        for i in range(n):
            off = (i - (n - 1) / 2) * 13.0
            vib = 0.0
            for f in FIBRES:
                if 0 <= t - f < 0.5 and i == (int(f * 7) % n):
                    vib = 7.0 * math.sin(t * 60)
            if n == 1 and t >= SNAPS[-1]:
                vib = 4.0 * math.sin(t * 50)
            xs = np.linspace(SP0, SP1, 26)
            ww = wth
            if tense:
                ww = 2.0
            seg = []
            for x in xs:
                bulge = math.sin(math.pi * (x - SP0) / (SP1 - SP0))
                seg.append((x, rope_y(x) + off * bulge * (0.6 if tense else 1.0) + vib * bulge))
            L_(seg, col, ww)
        # touffes de fibres aux deux bouts de la gaine
        for (x, sgn) in ((SP0, 1), (SP1, -1)):
            y = rope_y(x)
            for (a, ln) in self.tuft:
                ang = a * 1.3 + (math.pi / 2 if sgn > 0 else -math.pi / 2) * 0.0
                L_([(x, y), (x + sgn * ln * abs(math.cos(ang)) * 0.6, y + ln * math.sin(ang))], (226, 212, 180), 4)
        # la barbe : les bouts cassés qui pendent
        for j, s in enumerate(SNAPS):
            if t < s:
                continue
            u = min(1.0, (t - s) / 0.25)
            for (xa, side) in ((SP0 + 14 + 11 * j, 1), (SP1 - 14 - 11 * j, -1)):
                ya = rope_y(xa)
                ln = 48 + 8 * j
                sway = 3 * math.sin(t * 3 + j + side)
                seg = []
                for q in range(8):
                    v = q / 7
                    seg.append((xa + side * (1 - u) * 30 * v + sway * v + side * 6 * math.sin(v * 3), ya + v * ln * (0.3 + 0.7 * u)))
                L_(seg, (204, 188, 154), 7)
        # fibres qui giclent
        for (t0, x, a, sp, ln) in self.fib:
            u = t - t0
            if 0 <= u < 0.5:
                y = rope_y(x)
                px, py = x + math.cos(a) * sp * u, y + math.sin(a) * sp * u + 300 * u * u
                L_([(px, py), (px + math.cos(a) * ln * 0.5, py + math.sin(a) * ln * 0.5)], (240, 230, 204), 5)
        # Bounce
        bx, by = self.bounce_at(t)
        if t >= RELAUNCH:
            base.HERO["expr"] = "shock" if t - RELAUNCH < self.cfg["hero_shock_s"] else "calm"
        base.ball(dr, bx * S, by * S, R * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
