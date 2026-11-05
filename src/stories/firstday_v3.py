"""
firstday v3 : « Fired for bouncing? ». Un seul plan fixe, un open space. Le chef tape une ligne
du tableau TODAY : tout le monde se tait et se baisse ; le prochain « Bounce » vaut une main
levée, et une pastille rose se pose dans le rond de la ligne. Le gag est rejoué cinq fois. La
dernière ligne, FIRED, est rouge dès l'image 0, et le chef tient un carton vide. Au passage 4,
Bounce est sur son coussin (mou, muet) : c'est Kevin qui prend. Au dernier, le chef tape FIRED
pendant que Bounce est sur le coussin... un saut mou dérive, au ralenti, et touche le coin du
bureau. Il finit dans le carton.

Tout est calculé d'avance sur une horloge d'écran : les contacts de la balle (durs : bureau,
coin, carton ; mous : coussin), les arcs sous une gravité unique (temps « histoire » ralenti
×0,4 de 59,0 à 59,6 s), les répliques du chef (voix du narrateur), les gestes et les têtes.

    python3 src/stories/firstday_v3.py configs/firstday_v3.json [--simulate | --plan]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice  # noqa: F401

SR = ak.SR

# ------------------------------------------------------------------ correctifs d'exécution
# (aucun fichier existant n'est modifié : ces remplacements ne vivent que dans ce module)
_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr
    return narr, replies


base.build_narration = build_narration_keep

_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    """Une seule prise par mot pour toute la vidéo ; pour « Bounce », la plus courte (≤ 0,72 s)."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if len(v) / SR <= (0.72 if text == cfg["hero_name"] else 1.15):
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

_orig_hook = base.hook_audio
_hook_memo = {}


def steady_hook(cfg):
    """La même prise d'accroche pour le plan et le rendu, débarrassée du silence de fin."""
    key = (cfg.get("hook_text"), cfg.get("hook_narrator"))
    if key not in _hook_memo:
        v = _orig_hook(cfg)
        if v is not None and len(v):
            a = np.abs(v)
            idx = np.where(a > a.max() * 0.02)[0]
            if len(idx):
                v = v[:min(len(v), idx[-1] + int(0.04 * SR))].copy()
                n = min(int(0.02 * SR), len(v))
                v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = steady_hook


def fft_reverb(x, sr, tail_s=0.8, wet=0.5):
    """Même réverbération que base.reverb, par convolution FFT (np.convolve est trop lent sous charge)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    m = len(x) + n - 1
    L = 1 << (m - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, L) * np.fft.rfft(ir, L), L)[:m]
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9) * np.max(np.abs(x))


base.reverb = fft_reverb


def held_subtitle(narr, t, n_words):
    """Sous-titre tenu au moins 0,5 s + 0,3 s par mot (grille C18), une réplique à la fois."""
    for n in narr:
        until = max(n["end"] + 0.15, n["start"] + 0.5 + 0.3 * len(n["text"].split()))
        if n["start"] <= t <= until:
            return n["text"]
    return None


base.subtitle_at = held_subtitle

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
G = 2600.0
R = 120.0
SCENE_TOP = 470.0
FLOOR = 1620.0
WALL = (34, 37, 58)
CARPET = (50, 46, 60)
WOOD = (128, 90, 60)
PINK = (255, 60, 200)
MUSTARD = (214, 176, 64)
TURQ = (70, 164, 164)
SUIT = (46, 50, 72)
HEAD = (88, 92, 114)
CARD = (184, 138, 86)
NAVY = (30, 40, 90)
RED = (206, 34, 46)

BOARD = (580.0, 480.0, 895.0, 812.0)
ROWS = [("PARTY", 562.0), ("WEEKEND", 614.0), ("CLIENT", 666.0), ("PITCH", 718.0), ("FIRED", 774.0)]
DOT_X = 862.0
CUSH = (200.0, 390.0, 1190.0)          # coussin : x0, x1, dessus
DESK = (430.0, 700.0, 1150.0)          # bureau : x0, x1, plateau
CORNER = (DESK[0], DESK[2])
PART = (480.0, 722.0, 940.0)           # cloison derrière le bureau
COLS = [(548.0, TURQ), (662.0, MUSTARD)]
UP, DUCK, PEEK = 892.0, 1004.0, 940.0
PILE_X = 636.0
FOLD_W, FOLD_H = 92.0, 26.0
BOX_W, BOX_H = 220.0, 110.0
BOSS_X = 792.0

REST_C = 1070.0                        # centre de la balle posée sur le coussin
REST_D = DESK[2] - R                   # posée sur le bureau
DESK_X = 470.0
BOX_X = 545.0
SLOW = (59.0, 59.6, 0.4)               # ralenti : début, fin (écran), facteur


def warp(t):
    a, b, k = SLOW
    if t <= a:
        return t
    if t <= b:
        return a + (t - a) * k
    return a + (b - a) * k + (t - b)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


class Track:
    """Une valeur qui change par segments (début, durée, cible)."""

    def __init__(self, v):
        self.v0 = v
        self.segs = []

    def to(self, t0, dur, v, ease=smooth):
        self.segs.append((t0, max(1e-3, dur), v, ease))
        self.segs.sort(key=lambda s: s[0])
        return self

    def __call__(self, t):
        v = self.v0
        for (t0, d, tgt, e) in self.segs:
            if t < t0:
                break
            if t >= t0 + d:
                v = tgt
            else:
                v = lerp(v, tgt, e((t - t0) / d))
                break
        return v


def rr(dr, b, **kw):
    dr.rectangle([min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])], **kw)


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for (x, y) in pts]


def graze_point(x_from):
    """Le centre de la balle au contact du coin (distance R), en descente, côté coussin."""
    cx = CORNER[0] - 78.0
    cy = CORNER[1] - math.sqrt(R * R - 78.0 * 78.0)
    return cx, cy


# ------------------------------------------------------------------ la simulation
class Sim:
    scene_top = SCENE_TOP / H

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.build()

    # ================================================================ le scénario
    def build(self):
        cfg = self.cfg
        hook = base.hook_audio(cfg)
        hook_busy = 0.15 + (len(hook) / SR if hook is not None else 0.0) + 0.1
        react = base.hero_word(cfg["hero_lose"], cfg)
        react_len = len(react) / SR if react is not None else 0.9

        h1 = round(max(1.45, hook_busy + 0.02), 3)
        L1 = max(2.45, h1 + 0.92)
        # --- les contacts durs (temps d'écran) : bureau, sauf le coin et le carton
        hard = [h1, 4.05, 6.05, 8.30, 9.95, 11.35, 12.55, 14.95, 15.95, 17.00, 18.15, 19.55,
                21.75, 23.75, 25.45, 27.00, 28.35, 29.55, 30.60, 32.70, 33.70, 34.70, 36.50,
                42.10, 43.10, 44.25, 45.55, 47.05, 49.25, 51.45, 52.80, 54.25, 55.40, 56.50, 57.55]
        self.t_issue = 59.60
        self.payoff_at = 60.60
        tx = round(max(61.95, self.payoff_at + 0.15 + react_len + 0.09), 3)
        self.t_box = tx
        self.end_t = 62.95
        self.lines_plan = [(L1, "Who wants to plan the party?"), (13.50, "Who can work the weekend?"),
                           (24.65, "Client?"), (37.40, "CEO pitch?"), (39.10, "Anyone?"),
                           (40.95, "Kevin! Great."), (48.15, "Last one.")]
        self.bubbles = [(6.05 + 0.3, "I'm just sitting here."), (19.55 + 0.3, "I don't even have hands."),
                        (30.60 + 0.3, "That wasn't a yes."), (49.25 + 0.3, "Nice box.")]
        bubble_hits = {6.05, 19.55, 30.60, 49.25}

        # moments où le tableau se lit : pas de grand saut devant lui (son halo cacherait les lignes)
        self.board_busy = [(2.0, 5.6), (13.0, 16.6), (23.8, 27.0), (36.9, 42.9), (53.5, 59.7)]
        # --- la trajectoire : contacts (t, x, y, dur, creux max)
        C = []

        def add(t, x, y, hardc, dent=0.0):
            C.append((t, x, y, hardc, dent))

        def cush(t, x=300.0, dent=18.0):
            add(t, x, REST_C, False, dent)

        def desk(t):
            add(t, DESK_X, REST_D, True)

        # ouverture : même arc que la fin (raccord), du carton (absent) vers le coussin
        add(0.10 - 1.10, BOX_X, REST_D, False)
        cush(0.10, 300.0)
        self._fill(C, 0.10, h1 - 0.62, cush)
        desk(h1)
        prev = h1
        jit = [0, 4, 9, 2, 6, 11, 3, 8, 1, 7, 5, 10]
        for i, h in enumerate(hard[1:]):
            gap = h - prev
            in_bubble = any(0 <= tb - 0.3 - prev < 0.01 for (tb, _) in self.bubbles)
            if prev == 36.50:          # passage 4 : il reste sur le coussin (omission 1, presque)
                cush(37.20, 300.0)
                for (tt, xx) in ((37.72, 302.0), (38.26, 306.0), (38.82, 313.0), (39.38, 322.0)):
                    cush(tt, xx, 14.0)
                cush(39.95, 330.0, 4.0)               # le presque : le coin à quelques pixels
                for (tt, xx) in ((40.50, 318.0), (41.02, 304.0)):
                    cush(tt, xx, 14.0)
                cush(41.45, 300.0)
            elif gap <= 1.06 and not in_bubble and not any(a <= prev + gap / 2 <= b for (a, b) in self.board_busy):
                pass                                  # saut direct bureau → bureau
            else:
                if gap < 1.5:
                    cush(prev + gap * 0.48, 300.0 + jit[i % len(jit)] * 0.6)
                else:
                    t_land = prev + 0.60
                    t_off = h - 0.60
                    cush(t_land, 300.0 + jit[i % len(jit)] * 0.6)
                    self._fill(C, t_land, t_off, lambda t, x=None: cush(t, 300.0 + jit[int(t * 7) % len(jit)] * 0.5))
                    cush(t_off, 300.0 + jit[(i + 3) % len(jit)] * 0.5)
            desk(h)
            prev = h
        # la fin : retombée muette sur le coussin à la tape de FIRED, puis le coin
        cush(58.55, 318.0, 10.0)
        gx, gy = graze_point(318.0)
        add(self.t_issue, gx, gy, True)
        cush(60.15, 300.0, 14.0)
        cush(60.62, 302.0, 12.0)
        t_off = tx - 0.72
        self._fill(C, 60.62, t_off, lambda t, x=None: cush(t, 301.0, 12.0))
        cush(t_off, 300.0, 12.0)
        add(tx, BOX_X, REST_D, True)
        cush(tx + 1.10, 300.0)                         # après la fin : même arc qu'à l'image 0
        C.sort(key=lambda c: c[0])
        self.C = C
        self.hard_t = [c[0] for c in C if c[3] and c[0] >= 0]
        self.lines = [(t, text, f"l{k}") for k, (t, text) in enumerate(self.lines_plan)]

        # --- le tableau : lignes allumées, pastilles, appels, impulsions
        self.row_lit = {0: L1, 1: 13.50, 2: 24.30, 3: 37.40}
        self.dots = {0: (hard[1] + 0.12, PINK), 1: (14.95 + 0.06, PINK), 2: (24.35, PINK),
                     3: (41.25, MUSTARD), 4: (self.t_issue, PINK)}
        self.calls = [(L1, 0), (13.50, 1), (24.30, 2), (37.40, 3), (58.55, 4)]
        self.pulses = [(54.25, 0), (55.40, 1), (56.50, 2), (57.55, 3)]

        # --- le chef : bâton de présentation (cible), carton, position
        boss = {k: Track(v) for k, v in dict(x=BOSS_X, reach=0.0, tx=760.0, ty=1100.0, lean=0.0).items()}
        self.boss = boss
        box = {k: Track(v) for k, v in dict(x=BOSS_X, y=1062.0, flap=0.0).items()}
        self.box = box

        def point(t, tx_, ty_, hold=0.7, rise=0.22):
            boss["tx"].to(t - rise, rise * 0.6, tx_)
            boss["ty"].to(t - rise, rise * 0.6, ty_)
            boss["reach"].to(t - rise, rise, 1.0).to(t + hold, 0.3, 0.0)

        for (tc, r) in self.calls[:4]:
            point(tc, DOT_X - 44.0, ROWS[r][1], 0.8 if r != 2 else 1.4)
        point(58.55, DOT_X - 10.0, ROWS[4][1], 3.5)
        for (tp, r) in self.pulses:
            point(tp, DOT_X - 20.0, ROWS[r][1], 0.35, 0.18)
        # le dossier lancé sans appel
        self.tosses = [(hard[1] + 0.25, 0, None), (10.05, 1, None), (15.10, 2, None), (15.30, 3, None),
                       (25.55, 4, None), (25.75, 5, None), (25.95, 6, None), (41.40, -1, "kevin")]
        self.collapse_t = 45.55
        # « Last one. » : le carton levé à deux mains, sans taper FIRED
        box["y"].to(48.15, 0.4, 960.0).to(52.80, 0.5, 1062.0)
        box["x"].to(48.15, 0.4, 772.0).to(52.80, 0.5, BOSS_X)
        self.raised = (48.15, 53.3)
        # après l'issue : il pose le carton sur le bureau
        boss["x"].to(self.payoff_at, 0.6, 662.0)
        box["x"].to(self.payoff_at, 0.6, BOX_X)
        box["y"].to(self.payoff_at, 0.6, DESK[2] - BOX_H / 2)
        self.box_on_desk = self.payoff_at + 0.6
        boss["lean"].to(39.10, 0.3, -1.0).to(40.90, 0.3, 0.0)
        # rabats du carton qui battent à certains « Bounce »
        self.flap_hits = [h1, 18.15, 32.70, 51.45, tx]

        # --- les collègues
        cols = [Track(UP) for _ in COLS]
        lean = [Track(0.0) for _ in COLS]
        self.cols, self.lean = cols, lean
        self.kevin_arm = [(40.90, 42.10), (57.55, 58.40)]

        def heads(t, pose, dur=0.14, who=(0, 1), stagger=0.0):
            for k, i in enumerate(who):
                cols[i].to(t + k * stagger, dur, pose)

        def jolt(t, who=(0, 1), amt=14.0):
            for i in who:
                cols[i].to(t, 0.07, UP - amt).to(t + 0.07, 0.35, UP)

        jolt(h1)
        heads(L1 + 0.95, DUCK, 0.16, stagger=0.05)       # au mot « party »
        heads(hard[1] + 0.7, UP, 0.8, stagger=0.15)
        jolt(8.30, (1,))
        jolt(11.35, (0,))
        jolt(12.55)
        heads(13.55, DUCK, 0.14, stagger=0.04)
        heads(16.20, PEEK, 0.7)
        jolt(17.00, (0,), 20.0)
        heads(18.6, UP, 0.6)
        jolt(21.75, (1,))
        heads(24.30, DUCK, 0.14, stagger=0.05)
        heads(26.30, PEEK, 0.8)
        heads(28.6, UP, 0.6)
        jolt(29.55, (0,))
        jolt(33.70, (1,))
        heads(37.45, DUCK, 0.14, stagger=0.05)
        heads(38.60, PEEK + 20, 0.6, who=(0,))
        heads(39.55, UP, 0.35)                  # le presque : ils se relèvent pour voir
        lean[0].to(39.55, 0.35, -26.0).to(40.9, 0.4, 0.0)
        heads(40.90, UP - 8, 0.12, who=(1,))          # Kevin jaillit
        heads(41.6, UP + 30, 0.4, who=(1,))            # puis s'affaisse sous le dossier
        heads(41.0, UP, 0.5, who=(0,))
        heads(43.0, UP, 0.5, who=(1,))
        jolt(44.25, (0,))
        for i in (0, 1):
            lean[i].to(48.3, 0.5, 18.0).to(53.0, 0.5, 0.0)   # ils fixent le carton levé
        heads(58.58, DUCK, 0.13, stagger=0.04)           # l'appel sur FIRED s'ouvre
        heads(self.t_issue, UP - 8, 0.10)              # l'issue : les têtes jaillissent
        for i in (0, 1):
            lean[i].to(self.t_issue, 0.12, -24.0)

        self.slow = SLOW
        self.check()

    def _fill(self, C, t0, t1, fn, period=0.52):
        gap = t1 - t0
        n = max(1, int(round(gap / period)))
        for k in range(1, n):
            fn(t0 + gap * k / n)

    # ================================================================ contrôles
    def check(self):
        self.worst, self.min_top = 0.0, 1e9
        for a, b in zip(self.C, self.C[1:]):
            T = warp(b[0]) - warp(a[0])
            vy = (b[2] - a[2] - 0.5 * G * T * T) / T
            top = a[2] - vy * vy / (2 * G) if vy < 0 else a[2]
            hgt = max(a[2], b[2]) - top
            self.worst = max(self.worst, hgt)
            if a[0] >= 0:
                self.min_top = min(self.min_top, top)
            if hgt > 700 or (top < 640 and a[0] >= 0):
                print(f"[firstday_v3] arc trop haut à {a[0]:.2f} : {hgt:.0f} px, sommet {top:.0f}", file=sys.stderr)
        # écart minimal au coin pendant le passage 4 et à l'issue
        self.gap_presque = min(self.corner_gap(t) for t in np.arange(37.2, 41.5, 1 / 240))
        ts = [t for t in np.arange(0.0, self.end_t, 1 / 120) if abs(t - self.t_issue) > 0.02]
        self.gap_all = min(self.corner_gap(t) for t in ts)
        self.gap_issue_before = min(self.corner_gap(t) for t in np.arange(58.56, self.t_issue - 1 / 240, 1 / 240))

    def corner_gap(self, t):
        x, y, _ = self.ball_at(t)
        return math.hypot(x - CORNER[0], y - CORNER[1]) - R

    # ================================================================ la balle
    def ball_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return C[0][1], C[0][2], None
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                wa, wb, wt = warp(a[0]), warp(b[0]), warp(t)
                T = wb - wa
                s = wt - wa
                vy = (b[2] - a[2] - 0.5 * G * T * T) / T
                x = a[1] + (b[1] - a[1]) * s / T
                y = a[2] + vy * s + 0.5 * G * s * s
                dent = 0.0
                for c in (a, b):
                    if not c[3]:
                        k = 1 - abs(wt - warp(c[0])) / 0.09
                        if k > 0:
                            dent = max(dent, k * c[4])
                return x, y + dent, dent
        return C[-1][1], C[-1][2], None

    # ================================================================ moteur
    def step(self, dt):
        self.t += dt
        evs = []
        # base.simulate date les événements de l'instant d'avant le pas (celui de l'image dessinée) :
        # le « Bounce » part donc sur la première image où le contact est atteint, jamais avant
        tf = self.t - dt
        while self.hi < len(self.hard_t) and self.hard_t[self.hi] <= tf + 1e-9:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and tf >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "fired"))
        if self.t >= self.end_t - 0.06:
            self.done = True
        return evs

    hi = 0

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    # ================================================================ dessin
    def talking(self, t):
        return any(n["start"] <= t <= n["end"] for n in self.narr)

    def draw(self, dr, snap, t, S):
        P = lambda v: v * S
        rr(dr, [0, P(SCENE_TOP), P(W), P(FLOOR)], fill=WALL)
        rr(dr, [0, P(FLOOR), P(W), P(H)], fill=CARPET)
        rr(dr, [0, P(FLOOR), P(W), P(FLOOR + 8)], fill=dim(CARPET, 1.35))
        for k in range(6):
            yy = FLOOR + 70 + k * 70
            rr(dr, [0, P(yy), P(W), P(yy + 3)], fill=dim(CARPET, 1.12))
        self.draw_board(dr, t, S)
        self.draw_colleagues(dr, t, S)
        x0, x1, top = PART
        rr(dr, [P(x0), P(top), P(x1), P(FLOOR)], fill=(80, 86, 108))
        rr(dr, [P(x0), P(top), P(x1), P(top + 12)], fill=(116, 122, 146))
        rr(dr, [P((x0 + x1) / 2 - 3), P(top), P((x0 + x1) / 2 + 3), P(FLOOR)], fill=(62, 66, 86))
        self.draw_boss(dr, t, S)
        self.draw_chair(dr, t, S)
        self.draw_desk(dr, t, S)
        self.draw_folders(dr, t, S)
        on_desk = t >= self.box_on_desk - 0.05
        if not self.box_held(t):
            self.draw_box(dr, S, self.box["x"](t), self.box["y"](t), t, front=False)
        self.draw_bubble(dr, t, S)
        x, y, _ = self.ball_at(t)
        if self.t_box <= t < self.t_box + 0.9:
            base.HERO["expr"] = "shock"
        elif t >= self.t_box + 0.9:
            base.HERO["expr"] = "calm"            # il retrouve sa tête blasée : raccord avec l'image 0
        base.ball(dr, P(x), P(y), P(R))
        self.draw_desk(dr, t, S)                  # le bureau repasse devant le halo : le coin reste net
        self.draw_folders(dr, t, S)
        if on_desk:
            self.draw_box(dr, S, self.box["x"](t), self.box["y"](t), t, front=True)
        self.draw_flash(dr, t, S)
        rr(dr, [0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))

    def draw_flash(self, dr, t, S):
        """L'éclat d'un contact dur : 9 images de traits blancs autour du point d'impact."""
        P = lambda v: v * S
        for h in self.hard_t:
            age = t - h
            if 0 <= age < 0.15:
                x, y, _ = self.ball_at(h)
                if abs(h - self.t_issue) < 1e-6:
                    px, py = CORNER
                elif abs(h - self.t_box) < 1e-6:
                    px, py = x, DESK[2] - 6
                else:
                    px, py = x, DESK[2]
                k = 1 - age / 0.15
                for ang in (-150, -120, -60, -30, -90):
                    a = math.radians(ang)
                    r0, r1 = 26 + 30 * (1 - k), 60 + 40 * (1 - k)
                    dr.line([(P(px + r0 * math.cos(a)), P(py + r0 * math.sin(a))),
                             (P(px + r1 * math.cos(a)), P(py + r1 * math.sin(a)))],
                            fill=(255, 255, 255), width=max(1, int(P(6 * k + 2))))

    def draw_board(self, dr, t, S):
        P = lambda v: v * S
        x0, y0, x1, y1 = BOARD
        rr(dr, [P(x0), P(y0), P(x1), P(y1)], fill=(150, 152, 162))
        rr(dr, [P(x0 + 9), P(y0 + 9), P(x1 - 9), P(y1 - 9)], fill=(238, 240, 244))
        dr.text((P((x0 + x1) / 2), P(y0 + 33)), "TODAY", fill=(120, 122, 140), anchor="mm", font=base.font(P(30)))
        f = base.font(P(40))
        fr = base.font(P(52))
        for i, (name, ry) in enumerate(ROWS):
            # l'appel : bande jaune derrière la ligne tapée
            for (tc, r) in self.calls:
                if r == i and 0 <= t - tc < 0.7:
                    k = 1 - (t - tc) / 0.7
                    col = (255, 226, 90) if i < 4 else (255, 120, 120)
                    rr(dr, [P(x0 + 14), P(ry - 27), P(x1 - 14), P(ry + 27)],
                       fill=tuple(int(238 + (c - 238) * k) for c in col))
            if i == 4:
                dr.text((P(x0 + 20), P(ry)), name, fill=RED, anchor="lm", font=fr)
                ring = RED
            else:
                lit = t >= self.row_lit[i]
                dr.text((P(x0 + 20), P(ry)), name, fill=NAVY if lit else (214, 216, 224), anchor="lm", font=f)
                ring = (60, 64, 90) if lit else (214, 216, 224)
            r = 21.0
            dt_, dcol = self.dots[i]
            pulse = 0.0
            for (tp, rp) in self.pulses:
                if rp == i and 0 <= t - tp < 0.35:
                    pulse = math.sin(math.pi * (t - tp) / 0.35)
            dr.ellipse([P(DOT_X - r), P(ry - r), P(DOT_X + r), P(ry + r)], outline=ring, width=max(1, int(P(4))))
            if t >= dt_:
                k = clamp01((t - dt_) / 0.12)
                rd = (r - 4) * (0.4 + 0.6 * k) * (1 + 0.45 * pulse)
                circle(dr, P(DOT_X), P(ry), P(rd), dcol)

    def draw_colleagues(self, dr, t, S):
        P = lambda v: v * S
        for i, (cx, col) in enumerate(COLS):
            hy = self.cols[i](t)
            hx = cx + self.lean[i](t)
            dr.rounded_rectangle([P(hx - 62), P(hy + 46), P(hx + 62), P(hy + 150)], radius=int(P(30)), fill=dim(col, 0.85))
            circle(dr, P(hx), P(hy), P(56), col)
            if i == 1 and any(a <= t < b for (a, b) in self.kevin_arm):
                a0 = min(a for (a, b) in self.kevin_arm if a <= t < b)
                k = clamp01((t - a0) / 0.12)
                ex, ey = hx + 62, hy + 60 - 135 * k
                dr.line([(P(hx + 50), P(hy + 70)), (P(ex), P(ey))], fill=dim(col, 0.85), width=int(P(22)))
                circle(dr, P(ex), P(ey), P(15), col)

    def box_held(self, t):
        return t < self.payoff_at + 0.6

    def draw_boss(self, dr, t, S):
        P = lambda v: v * S
        b = self.boss
        x = b["x"](t)
        hip = 1180.0
        top = 946.0
        lean = b["lean"](t)
        talk = self.talking(t)
        for sx in (-1, 1):
            rr(dr, [P(x + sx * 30 - 19), P(hip - 4), P(x + sx * 30 + 19), P(FLOOR)], fill=dim(SUIT, 0.85))
            rr(dr, [P(x + sx * 30 - 24), P(FLOOR - 16), P(x + sx * 30 + 26), P(FLOOR)], fill=(20, 20, 26))
        rr(dr, [P(x - 64), P(top), P(x + 64), P(hip)], fill=SUIT)
        dr.polygon([(P(x - 22), P(top)), (P(x + 22), P(top)), (P(x), P(top + 62))], fill=(232, 232, 236))
        dr.polygon([(P(x - 7), P(top + 10)), (P(x + 7), P(top + 10)), (P(x + 11), P(top + 88)), (P(x), P(top + 102)),
                    (P(x - 11), P(top + 88))], fill=(196, 40, 52))
        hy = top - 62 + (3.0 * math.sin(t * 22) if talk else 0.0)
        circle(dr, P(x - 10 * lean), P(hy + 6 * abs(lean)), P(62), HEAD)
        # le bras qui pointe (gauche) et son bâton
        sh = (x - 54, top + 26)
        reach = b["reach"](t)
        rest_hand = (x - 74, top + 170)
        tgt = (b["tx"](t), b["ty"](t))
        if reach > 0:
            hand = (lerp(rest_hand[0], sh[0] + 0.55 * (tgt[0] - sh[0]), reach),
                    lerp(rest_hand[1], sh[1] + 0.55 * (tgt[1] - sh[1]), reach))
            tip = (lerp(hand[0], tgt[0], reach), lerp(hand[1] + 120, tgt[1], reach))
        else:
            hand = rest_hand
            tip = (hand[0] - 10, hand[1] + 120)
        held = self.box_held(t)
        raised = self.raised[0] <= t < self.raised[1]
        if held and raised:
            bx, by = self.box["x"](t), self.box["y"](t)
            hand = (bx - BOX_W / 2 + 8, by)
            tip = None
        dr.line([(P(sh[0]), P(sh[1])), (P(hand[0]), P(hand[1]))], fill=SUIT, width=int(P(26)))
        circle(dr, P(hand[0]), P(hand[1]), P(14), SUIT)
        if tip is not None:
            dr.line([(P(hand[0]), P(hand[1])), (P(tip[0]), P(tip[1]))], fill=(26, 26, 30), width=max(1, int(P(6))))
        # le carton tenu (bras droit)
        if held:
            bx, by = self.box["x"](t), self.box["y"](t)
            self.draw_box(dr, S, bx, by, t, front=False)
            self.draw_box(dr, S, bx, by, t, front=True)
            rh = (bx + BOX_W / 2 - 6, by)
            dr.line([(P(x + 54), P(top + 26)), (P(rh[0]), P(rh[1]))], fill=SUIT, width=int(P(26)))
            circle(dr, P(rh[0]), P(rh[1]), P(14), SUIT)
        else:
            dr.line([(P(x + 54), P(top + 26)), (P(x + 70), P(top + 190))], fill=SUIT, width=int(P(26)))

    def draw_box(self, dr, S, cx, cy, t, front):
        """Le carton de déménagement, rabats ouverts. front=False : rabats et fond ; True : la face avant."""
        P = lambda v: v * S
        w, h = BOX_W / 2, BOX_H / 2
        flap = 0.0
        for th in self.flap_hits:
            if 0 <= t - th < 0.4:
                flap = 14.0 * math.sin(math.pi * (t - th) / 0.4)
        if not front:
            rr(dr, [P(cx - w), P(cy - h), P(cx + w), P(cy + h)], fill=dim(CARD, 0.62))
            dr.polygon([(P(cx - w), P(cy - h)), (P(cx - w - 18), P(cy - h - 52 - flap)), (P(cx - w + 46), P(cy - h - 56 - flap)),
                        (P(cx - w + 60), P(cy - h))], fill=dim(CARD, 1.1))
            dr.polygon([(P(cx + w), P(cy - h)), (P(cx + w + 18), P(cy - h - 52 - flap)), (P(cx + w - 46), P(cy - h - 56 - flap)),
                        (P(cx + w - 60), P(cy - h))], fill=dim(CARD, 1.1))
        else:
            rr(dr, [P(cx - w), P(cy - h + 8), P(cx + w), P(cy + h)], fill=CARD)
            rr(dr, [P(cx - w), P(cy - h + 8), P(cx + w), P(cy - h + 20)], fill=dim(CARD, 0.82))
            rr(dr, [P(cx - 22), P(cy - 2), P(cx + 22), P(cy + 10)], fill=dim(CARD, 0.6))

    def draw_chair(self, dr, t, S):
        P = lambda v: v * S
        x0, x1, top = CUSH
        rr(dr, [P(x0 + 4), P(950), P(x0 + 26), P(top)], fill=(72, 72, 88))
        rr(dr, [P(x0 + 4), P(930), P(x0 + 46), P(1020)], fill=(72, 72, 88))
        rr(dr, [P(x0 + 20), P(top + 30), P(x1 - 6), P(top + 46)], fill=(72, 72, 88))
        cxm = (x0 + x1) / 2
        rr(dr, [P(cxm - 7), P(top + 46), P(cxm + 7), P(FLOOR - 40)], fill=(92, 92, 104))
        rr(dr, [P(cxm - 80), P(FLOOR - 40), P(cxm + 80), P(FLOOR - 28)], fill=(92, 92, 104))
        for wx in (cxm - 72, cxm + 72):
            circle(dr, P(wx), P(FLOOR - 14), P(14), (40, 40, 48))
        x, y, dent = self.ball_at(t)
        dent = dent or 0.0
        pts = [(x0, top + 32)]
        for k in range(15):
            xx = x0 + (x1 - x0) * k / 14
            d = dent * max(0.0, 1 - abs(xx - x) / 120)
            pts.append((xx, top + d))
        pts.append((x1, top + 32))
        dr.polygon([(P(a), P(b_)) for (a, b_) in pts], fill=(96, 106, 160))

    def draw_desk(self, dr, t, S):
        P = lambda v: v * S
        x0, x1, top = DESK
        rr(dr, [P(x0 + 14), P(top + 24), P(x1 - 14), P(FLOOR)], fill=dim(WOOD, 0.66))
        rr(dr, [P(x0 + 40), P(top + 70), P(x1 - 40), P(top + 74)], fill=dim(WOOD, 0.55))
        rr(dr, [P(x0), P(top), P(x1), P(top + 26)], fill=WOOD)
        rr(dr, [P(x0), P(top), P(x1), P(top + 5)], fill=dim(WOOD, 1.25))

    # ------------------------------------------------------------ dossiers
    def toss_pose(self, t, t0, k, dest):
        if t < t0:
            return None
        sx, sy = BOSS_X - 60, 1000.0
        if dest == "kevin":
            ex, ey = COLS[1][0] - 10, 940.0
        else:
            ex, ey = PILE_X, DESK[2] - FOLD_H * (k + 0.5)
        T = 0.6
        if t < t0 + T:
            s = t - t0
            vy = (ey - sy - 0.5 * G * T * T) / T
            return sx + (ex - sx) * s / T, sy + vy * s + 0.5 * G * s * s, 2.5 * (1 - s / T)
        if dest == "kevin":
            return None
        return ex, ey, None

    def draw_folders(self, dr, t, S):
        P = lambda v: v * S
        cols = [(230, 190, 60), (150, 152, 166), (80, 140, 220), (70, 120, 200), (210, 60, 60), (190, 50, 50), (170, 40, 50)]
        for (t0, k, dest) in self.tosses:
            fp = self.toss_pose(t, t0, k, dest)
            if fp is None:
                continue
            x, y, a = fp
            col = cols[k] if k >= 0 else (90, 190, 110)
            if a is None:
                # posé sur la pile : penche un peu plus à chaque dossier, tremble aux « Bounce »
                n_on = sum(1 for (tt, kk, d) in self.tosses if d is None and tt + 0.6 <= t)
                lean = 0.006 * k * k + 0.004 * n_on
                w = 0.0
                for h in self.hard_t:
                    if 0 <= t - h < 0.35:
                        w = 0.03 * (k + 1) / 3 * math.sin((t - h) * 40) * (1 - (t - h) / 0.35)
                x = x + 5.0 * k * k / 3
                a = lean + w
                if t >= self.collapse_t:
                    s = t - self.collapse_t - 0.03 * k
                    if s > 0:
                        vx = 160.0 + 30 * k
                        x = x + vx * s
                        y = y - (260 + 40 * k) * s + 0.5 * G * s * s
                        a = a + (2.0 + 0.4 * k) * s
                        if y > FLOOR + 60:
                            continue
                        if x - FOLD_W / 2 > DESK[1] + 10 and y > DESK[2]:
                            continue           # tombé derrière le bureau
            pts = [(x - FOLD_W / 2, y - FOLD_H / 2), (x + FOLD_W / 2, y - FOLD_H / 2),
                   (x + FOLD_W / 2, y + FOLD_H / 2), (x - FOLD_W / 2, y + FOLD_H / 2)]
            pts = rot(pts, x, y, a)
            dr.polygon([(P(a_), P(b_)) for (a_, b_) in pts], fill=col)
            tab = rot([(x - 34, y - FOLD_H / 2 - 7), (x - 10, y - FOLD_H / 2 - 7), (x - 10, y - FOLD_H / 2),
                       (x - 34, y - FOLD_H / 2)], x, y, a)
            dr.polygon([(P(a_), P(b_)) for (a_, b_) in tab], fill=dim(col, 0.8))

    # ------------------------------------------------------------ la bulle
    def draw_bubble(self, dr, t, S):
        P = lambda v: v * S
        cur = None
        for (tb, text) in self.bubbles:
            if tb <= t < tb + 1.8:
                cur = (tb, text)
        if cur is None:
            return
        tb, text = cur
        age = t - tb
        k = min(1.0, age / 0.15)
        x0, x1, y0 = 130.0, 560.0, 484.0
        f2 = base.font(P(48))
        rows, c = [], ""
        for w in text.split():
            cand = (c + " " + w).strip()
            if base.text_w(f2, cand) <= P(x1 - x0 - 50) or not c:
                c = cand
            else:
                rows.append(c); c = w
        rows.append(c)
        row0 = y0 + 168
        y1 = row0 + (len(rows) - 1) * 56 + 40
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sc = 0.6 + 0.4 * k
        qx0, qx1 = cx - (cx - x0) * sc, cx + (x1 - cx) * sc
        qy0, qy1 = cy - (cy - y0) * sc, cy + (y1 - cy) * sc
        bx, by, _ = self.ball_at(t)
        tx, ty = bx, by - R - 10
        ax = min(max(bx, 220.0), 470.0)
        dr.polygon([(P(ax - 40), P(qy1 - 4)), (P(ax + 40), P(qy1 - 4)), (P(tx), P(max(ty, qy1 + 30)))], fill=(250, 250, 252))
        dr.rounded_rectangle([P(qx0), P(qy0), P(qx1), P(qy1)], radius=int(P(28)), fill=(250, 250, 252),
                             outline=(20, 20, 26), width=max(1, int(P(5))))
        if k < 1.0:
            return
        dr.text((P(cx), P(y0 + 52)), "“BOUNCE.”", fill=PINK, anchor="mm", font=base.font(P(66)),
                stroke_width=max(1, int(P(3))), stroke_fill=(120, 0, 80))
        dr.text((P(cx), P(y0 + 112)), "means:", fill=(110, 110, 130), anchor="mm", font=base.font(P(34)))
        for i, row in enumerate(rows):
            dr.text((P(cx), P(row0 + i * 56)), row, fill=(20, 20, 26), anchor="mm", font=f2)


DEFAULTS = {
    "ball_r": R, "gravity": G,
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 80,
    "show_counter": False, "sub_y": 0.645, "sub_font_size": 52, "sub_words": 8,
    "watermark_y": 0.94, "end_hold_s": 0.05, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
    "hero_shock_s": 0.9, "min_duration_s": 61.0,
}


def report(sim, cfg):
    narr, _ = base.build_narration(sim, cfg)
    print("accroche : voix jusqu'à", round(0.15 + len(base.hook_audio(cfg)) / SR, 2))
    print("contacts durs :", [round(t, 2) for t in sim.hard_t])
    for n in narr:
        print(f"  {n['start']:6.2f}-{n['end']:6.2f} {n['text']}")
    for (tb, text) in sim.bubbles:
        print(f"  bulle {tb:6.2f}-{tb + 1.8:6.2f} {text}")
    print("arc le plus haut", round(sim.worst), "sommet le plus haut (centre)", round(sim.min_top),
          "| écart au coin : presque", round(sim.gap_presque, 1), "px, avant l'issue", round(sim.gap_issue_before, 2), "px, hors issue", round(sim.gap_all, 1))
    print("issue", sim.t_issue, "carton", sim.t_box, "fin", sim.end_t)


if __name__ == "__main__":
    if "--plan" in sys.argv:
        cfg = base.load_config(sys.argv[1], DEFAULTS)
        report(Sim(cfg, None), cfg)
        sys.exit(0)
    sys.exit(base.run(sys.modules[__name__]))
