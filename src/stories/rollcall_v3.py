"""
rollcall v3 : soirée jeu de société. Bounce rebondit sur la table à côté d'une tour de blocs
en bois ; chaque coup dur sur la table fait trembler la tour et des blocs tombent sur la tête
de Still (personnage de fan), qui ne réagit jamais : ils s'empilent. Il suffirait qu'il reste
sur son coussin. À la fin, toute la pile bascule et l'ensevelit ; il reste un bloc sur Still,
celui de la première image.

Tout est écrit en fonction du temps (contacts placés à la main, arcs sous une gravité unique,
ressorts amortis pour les oscillations, chutes balistiques). Un ralenti ×0,5 couvre la chute.
Still est redessinée d'après le script du clip (même dessin), sans voix.

    python3 src/stories/rollcall_v3.py configs/rollcall_v3.json [--simulate]
"""
import math, sys, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import base
from base import dim
import audio_kit as ak

SR = ak.SR
W, H = 1080, 1920
G = 2600.0
RB = 120.0                       # Bounce
TAB_Y = 1200.0 - RB              # centre de Bounce posé sur la table
CUSH_TOP = 1185.0
CUSH_X = 772.0
CUSH_Y = CUSH_TOP - RB + 18.0    # centre de Bounce enfoncé dans le coussin
TABLE_X = 645.0

# ------------------------------------------------------------------ son : FFT et accroche
def _reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + len(ir) - 1
    nf = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = _reverb_fft
_orig_hook = base.hook_audio


def _compress(x, sr=SR, th=0.02, maxgap=0.08):
    """La voix de l'accroche, sans ses silences : début et fin coupés, pauses internes
    ramenées à 80 ms."""
    a = np.abs(x)
    env = np.convolve(a, np.ones(240) / 240, "same")
    loud = env > th * env.max()
    idx = np.where(loud)[0]
    x, loud = x[idx[0]:idx[-1] + 1], loud[idx[0]:idx[-1] + 1]
    out, i, n, g = [], 0, len(x), int(maxgap * sr)
    while i < n:
        j = i
        while j < n and loud[j] == loud[i]:
            j += 1
        out.append(x[i:j] if loud[i] else x[i:i + min(j - i, g)])
        i = j
    y = np.concatenate(out)
    f = min(len(y), int(0.01 * sr))
    y[-f:] *= np.linspace(1, 0, f)
    return y


_hook_cache = {}


def _hook(cfg):
    if "v" not in _hook_cache:
        v = _orig_hook(cfg)
        _hook_cache["v"] = None if v is None else _compress(v)
    v = _hook_cache["v"]
    return None if v is None else v.copy()


base.hook_audio = _hook

# ------------------------------------------------------------------ Still (dessin du clip)
OC_OUT = (152, 166, 56)
OC_IN = (238, 250, 178)
OC_INK = (14, 14, 12)
HAT_FILL = (142, 146, 244)
HAT_LINE = (84, 86, 214)
BOW_FILL = (234, 246, 176)
BOW_LINE = (92, 98, 34)


def draw_still(dr, cx, cy, R, S, gx=0.0):
    def P(u, v):
        return ((cx + u * R) * S, (cy + v * R) * S)

    def poly(pts, fill=None, outline=None, width=0):
        q = [P(u, v) for u, v in pts]
        if fill is not None:
            dr.polygon(q, fill=fill)
        if outline is not None:
            dr.line(q + [q[0]], fill=outline, width=max(1, int(width * R * S)), joint="curve")

    def ell(u, v, ru, rv, n=40, a0=0.0, a1=2 * math.pi):
        return [(u + ru * math.cos(a0 + (a1 - a0) * i / n), v + rv * math.sin(a0 + (a1 - a0) * i / n))
                for i in range(n + (0 if a1 - a0 >= 2 * math.pi else 1))]

    def stroke(pts, w, col=OC_INK):
        q = [P(u, v) for u, v in pts]
        dr.line(q, fill=col, width=max(2, int(w * R * S)), joint="curve")
        rr = w * R * S / 2
        for (x, y) in (q[0], q[-1]):
            dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)

    poly(ell(0, 0, 1.6, 1.6, 64), fill=dim(OC_OUT, 0.55))
    poly(ell(0, 0, 1.0, 1.0, 64), fill=OC_IN)
    px = gx * 0.05
    stroke([(-0.60, -0.50), (-0.18, -0.40)], 0.12)
    stroke([(0.14, -0.44), (0.60, -0.30)], 0.12)
    for (eu, ev, ru, rv) in ((-0.36, -0.16, 0.17, 0.13), (0.33, -0.12, 0.17, 0.15)):
        poly([(eu - ru, ev)] + ell(eu + px, ev, ru, rv, 24, 0.0, math.pi)[::-1] + [(eu + ru, ev)], fill=OC_INK)
        stroke([(eu - ru - 0.02, ev), (eu + ru + 0.02, ev)], 0.07)
    stroke([(-0.53, -0.16), (-0.62, -0.22)], 0.06)
    poly([(0.42, -0.02), (0.52, 0.07), (0.46, 0.10), (0.37, 0.02)], fill=OC_INK)
    stroke([(-0.20, 0.38), (0.10, 0.46)], 0.09)
    band = ell(0, 0, 0.99, 0.99, 20, math.radians(-128), math.radians(-62))
    inner = ell(0, 0, 0.79, 0.79, 20, math.radians(-128), math.radians(-62))[::-1]
    poly(band + inner, fill=HAT_FILL, outline=HAT_LINE, width=0.05)
    kx, ky = 0.36, -0.86

    def lobe(ang, L, Wd):
        ca, sa = math.cos(ang), math.sin(ang)
        pts = []
        for i in range(32):
            k = 2 * math.pi * i / 32
            u, v = L / 2 * (1 + math.cos(k)), Wd * math.sin(k) * (0.55 + 0.45 * (1 + math.cos(k)) / 2)
            pts.append((kx + u * ca - v * sa, ky + u * sa + v * ca))
        return pts
    poly(lobe(math.radians(-25), 0.50, 0.20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(lobe(math.radians(-120), 0.46, 0.19), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(lobe(math.radians(40), 0.30, 0.10), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
    poly(ell(kx, ky, 0.10, 0.09, 20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)


# ------------------------------------------------------------------ le temps
SLOW_A, SLOW_B, SLOW_K = 61.65, 62.99, 0.5     # ralenti : [A, B] en temps vidéo, ×K


def tau(t):
    """Temps de la scène (physique) en fonction du temps vidéo : ralenti sur la chute."""
    if t <= SLOW_A:
        return t
    if t <= SLOW_B:
        return SLOW_A + (t - SLOW_A) * SLOW_K
    return SLOW_A + (SLOW_B - SLOW_A) * SLOW_K + (t - SLOW_B)


def vid(tt):
    """Inverse de tau."""
    if tt <= SLOW_A:
        return tt
    mid = SLOW_A + (SLOW_B - SLOW_A) * SLOW_K
    if tt <= mid:
        return SLOW_A + (tt - SLOW_A) / SLOW_K
    return SLOW_B + (tt - mid)


# ------------------------------------------------------------------ le plan des contacts
# coups durs sur la table (temps vidéo = temps scène avant le ralenti)
HARD = [2.06, 3.80, 4.70, 5.65, 7.40, 9.40, 11.30, 12.90, 13.90, 14.85, 15.75, 16.65, 18.45, 19.45, 20.35,
        21.45, 23.35, 25.35, 28.95, 29.97, 30.90, 31.82, 34.10, 36.30, 37.30, 38.20, 39.85, 42.00, 43.35,
        44.35, 45.25, 47.55, 49.60, 50.90, 51.80, 53.20, 55.40, 56.49, 57.42, 58.34, 60.62, 61.52]
X1 = 27.20                        # le bloc qui tombe sur Bounce
SOFT = [-0.55, 0.45, 1.25, 2.95, 6.55, 8.40, 10.35, 12.10, 17.55, 20.95, 22.40, 24.35, 26.25, 28.05,
        32.77, 33.25, 35.20, 39.05, 40.90, 46.15, 46.60, 48.55, 54.30, 59.29, 59.80]
PASSES = {2.06, 7.40, 16.65, 25.35, 34.10, 39.85, 45.25, 53.20, 60.62}
T_TIP = 61.52                     # le petit coup qui fait tout tomber
PAYOFF = 64.30
END = 65.9


def table_x(k):
    return TABLE_X + (12, -8, 5, -14, 0, 9, -6)[k % 7]


class Spring:
    """Un angle amorti, échantillonné à 600 Hz sur le temps de la scène."""
    def __init__(self, T, k, c, kicks, targets, freeze=()):
        self.dt = 1 / 600.0
        n = int(T / self.dt) + 2
        a, v = 0.0, 0.0
        out = np.zeros(n)
        kicks = sorted(kicks)
        targets = sorted(targets)
        ki = ti = 0
        tgt = 0.0
        cc = c
        for i in range(n):
            t = i * self.dt
            while ki < len(kicks) and kicks[ki][0] <= t:
                v += kicks[ki][1]; ki += 1
            while ti < len(targets) and targets[ti][0] <= t:
                tgt = targets[ti][1]; ti += 1
            cc = c
            for (f0, f1, fc) in freeze:
                if f0 <= t < f1:
                    cc = fc
            acc = -k * (a - tgt) - cc * v
            v += acc * self.dt
            a += v * self.dt
            out[i] = a
        self.a = out

    def __call__(self, tt):
        i = int(max(0.0, tt) / self.dt)
        return float(self.a[min(i, len(self.a) - 1)])


def ballistic(p0, p1, d, tt):
    """Position à tt dans [0, d] d'un objet allant de p0 à p1 en d secondes sous G."""
    s = max(0.0, min(d, tt))
    vx = (p1[0] - p0[0]) / d
    vy = (p1[1] - p0[1] - 0.5 * G * d * d) / d
    return p0[0] + vx * s, p0[1] + vy * s + 0.5 * G * s * s


def rot(px, py, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = px - cx, py - cy
    return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca


# ------------------------------------------------------------------ géométrie
TW = 156.0
RH = 30.0
TBASE = 1150.0
TCX = 440.0
NROWS = 22
STILL = (250.0, 1015.0, 105.0)
STACK_BASE = STILL[1] - STILL[2] - 4.0        # dessus de la tête de Still (au-dessus de la barrette)
WOOD = (226, 186, 128)
WOOD_D = (196, 152, 98)
WOOD_E = (122, 86, 48)
WOOD_BACK = (150, 112, 70)


def slot_local(r, s):
    """Centre local (dx, dy depuis la base de la tour) et taille d'un bloc de la tour."""
    y = -(r + 0.5) * RH
    if r % 2 == 0:
        return (-52.0 + 52.0 * s, y, 48.0, RH - 2)
    return (0.0, y, TW, RH - 2)


class Block:
    """Un bloc : sa vie est une suite de phases (dans la tour, en vol, sur la pile, au sol)."""
    def __init__(self, key, w, h):
        self.key, self.w, self.h = key, w, h
        self.phases = []       # (t0, kind, data)

    def add(self, t0, kind, data):
        self.phases.append((t0, kind, data)); self.phases.sort(key=lambda p: p[0])

    def phase(self, tt):
        cur = None
        for p in self.phases:
            if p[0] <= tt:
                cur = p
        return cur


class Sim:
    scene_top = 0.26

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.rng = np.random.default_rng(int(cfg["seed"]))
        # ------------------------------------------------ Bounce : ses contacts
        kf = []
        for k, th in enumerate(HARD):
            kf.append((th, table_x(k), TAB_Y, "hard"))
        for ts in SOFT:
            kf.append((ts, CUSH_X + (8 if int(ts * 10) % 2 else -6), CUSH_Y, "soft"))
        kf.append((X1, 700.0, 830.0, "x1"))
        kf.sort()
        self.kf = kf
        self.hits = sorted(HARD + [X1])
        # ------------------------------------------------ secousses de la table
        self.jolt_t = sorted(HARD + [X1])
        # ------------------------------------------------ la tour : blocs
        self.blocks = {}
        holes = {(4, 0), (8, 2), (10, 1), (14, 0), (6, 2), (12, 2)}
        for r in range(NROWS):
            if r % 2 == 0:
                for s in range(3):
                    if (r, s) in holes:
                        continue
                    b = Block((r, s), 48.0, RH - 2)
                    b.add(-99, "tower", (r, s, 0.0))
                    self.blocks[(r, s)] = b
            else:
                for s in ("f", "b"):            # bloc de devant, bloc du milieu (plus sombre)
                    if (r, s) in ((7, "f"), (21, "b")):
                        continue
                    b = Block((r, s), TW, RH - 2)
                    b.add(-99, "tower", (r, s, 0.0))
                    self.blocks[(r, s)] = b
        # le bloc A, sur la tête de Still dès l'image 0 (il restera seul à la fin)
        A = Block("A", TW, RH - 2)
        A.add(-99, "stack", (0, 0.0, 0.0))
        self.blocks["A"] = A
        self.stack = [(-99, "A")]              # (t_arrivée, clé) dans l'ordre de la pile
        self.slides = {}                       # clé -> [(t, dx)] glissements dans la tour
        self.teeter = {}                       # clé -> (t, amp, dx_final, ang_final)
        self.crooked = {}                      # clé -> [(t, ang)]
        self._script()
        # ------------------------------------------------ ressorts
        tk = [(t, v) for (t, v) in self.tower_kicks]
        self.lean = Spring(70, 60.0, 3.2, tk, self.tower_targets, freeze=[(32.77, 34.05, 14.0)])
        self.sway = Spring(70, 46.0, 2.6, self.stack_kicks, self.stack_targets,
                           freeze=[(59.29, 60.6, 6.0), (60.62, 61.52, 60.0)])
        self._collapse()
        self.payoff_t = None

    # -------------------------------------------------------------- le scénario
    def slide(self, key, t, dx):
        self.slides.setdefault(key, []).append((t, dx))

    def fly(self, key, t0, d, target_kind, target, spin=0.0, p0=None, a1=0.0):
        b = self.blocks[key]
        b.add(t0, "fly", {"d": d, "to": target_kind, "target": target, "spin": spin, "p0": p0, "a1": a1})
        if target_kind == "stack":
            self.stack.append((t0 + d, key))
            b.add(t0 + d, "stack", (len(self.stack) - 1, target[0], a1))
        elif target_kind == "rest":
            b.add(t0 + d, "rest", target)

    def _script(self):
        self.tower_kicks, self.tower_targets = [], [(0, 0.0)]
        self.stack_kicks, self.stack_targets = [], [(0, 0.0)]
        K, T = self.tower_kicks, self.tower_targets
        SK, ST = self.stack_kicks, self.stack_targets
        for th in HARD:
            K.append((th, -0.02 if int(th * 7) % 2 else 0.02))
            SK.append((th, 0.012 if int(th * 3) % 2 else -0.012))
        # image 0 : le bloc du sommet (rangée 21) dépasse de 45 % au-dessus de Still
        self.slide((21, "f"), -99, -70.0)
        self.slide((21, "b"), -99, 0.0)
        # P1 : il glisse et tombe sur la pile
        self.slide((21, "f"), 2.06, -100.0)
        self.fly((21, "f"), 2.16, 0.5, "stack", (2.0,), spin=-0.25)
        K.append((2.06, -0.10))
        self.slide((19, "f"), 3.80, -40.0)
        self.slide((19, "f"), 4.70, -70.0)
        K.append((5.65, 0.16))
        # P2 : deux blocs ensemble
        self.slide((19, "f"), 7.40, -95.0)
        self.slide((20, 0), 7.40, -30.0)
        self.fly((19, "f"), 7.48, 0.42, "stack", (-4.0,), spin=0.2)
        self.fly((20, 0), 7.56, 0.44, "stack", (10.0,), spin=0.35)
        K.append((7.40, -0.14))
        # 10-17 s
        self.slide((13, "f"), 9.40, -60.0)
        SK.append((11.30, 0.05))
        self.slide((13, "f"), 12.90, -95.0)
        self.slide((20, 2), 13.90, 12.0)
        SK.append((14.85, 0.07))
        self.slide((13, "f"), 15.75, -102.0)
        # P3 : le bloc du milieu tombe de travers sur la pile, vacille
        self.slide((13, "f"), 16.65, -130.0)
        self.fly((13, "f"), 16.72, 0.36, "stack", (34.0,), spin=0.5, a1=0.28)
        self.teeter[(13, "f")] = (17.08, 0.24, 18.0, 0.10)
        T.append((16.65, -0.025))
        K.append((16.65, -0.08))
        T.append((18.45, -0.035))
        self.slide((20, 2), 20.35, 18.0)
        self.slide((20, 2), 21.45, 22.0)
        K.append((23.35, 0.06))
        # P4 : le carré du sommet, au bord droit, tombe sur Bounce
        self.slide((20, 2), 25.35, 30.0)
        b = self.blocks[(20, 2)]
        b.add(26.83, "fly", {"d": X1 - 26.83, "to": "x1", "target": (700.0, 830.0 - RB - 14), "spin": 0.9,
                             "p0": None, "a1": 0.9})
        b.add(X1, "fly", {"d": 0.62, "to": "floor", "target": (905.0, 1560.0), "spin": 2.2, "p0": (700.0, 830.0 - RB - 14),
                          "a1": 2.2 + 0.9})
        b.add(X1 + 0.62, "rest", (905.0, 1560.0, 0.0))
        # de travers dans la pile, sur un autre objet
        self.crooked[(19, "f")] = [(29.97, 0.12)]
        self.slide((5, "f"), 30.90, 30.0)
        K.append((31.82, -0.07))
        self.slide((5, "f"), 31.82, 42.0)
        # P5 : cascade de trois blocs
        self.slide((20, 1), 34.10, -40.0)
        self.slide((19, "b"), 34.10, -80.0)
        self.slide((18, 0), 34.10, -40.0)
        self.fly((20, 1), 34.18, 0.42, "stack", (6.0,), spin=0.3)
        self.fly((19, "b"), 34.30, 0.40, "stack", (-6.0,), spin=-0.2)
        self.fly((18, 0), 34.42, 0.42, "stack", (12.0,), spin=0.4)
        K.append((34.10, -0.12))
        K.append((36.30, 0.08))
        self.slide((5, "f"), 37.30, 60.0)
        T.append((38.20, 0.02))
        # P6 : la tour penche au-dessus de Bounce, revient
        K.append((39.85, 1.15))
        T.append((42.00, -0.03))
        K.append((42.00, -0.25))
        SK.append((43.35, 0.10))
        # P7 : la tranche du haut glisse sur la pile de Still
        self.slab_t0, self.slab_t1 = 44.35, 45.25
        self.slab_rows = [16, 17, 18]
        T.append((45.25, -0.02))
        # après la fausse fin : la pile de Still oscille, côté incertain
        SK.append((49.60, 0.10))
        SK.append((50.90, -0.16))
        self.slide((9, "f"), 51.80, 40.0)
        ST.append((53.20, -0.06)); SK.append((53.20, -0.22))
        ST.append((55.40, 0.06)); SK.append((55.40, 0.40))
        self.crooked[(19, "b")] = [(56.49, -0.14)]
        ST.append((57.42, -0.05)); SK.append((57.42, -0.42))
        ST.append((58.34, 0.04)); SK.append((58.34, 0.44))
        ST.append((59.29, 0.03))
        ST.append((60.62, 0.035))

    # -------------------------------------------------------------- l'effondrement
    def _collapse(self):
        """Après T_TIP : la colonne de la pile de Still (tout sauf A) bascule à droite, heurte
        la tour, la tour bascule à son tour sur Bounce. Intégré sur le temps de la scène."""
        dt = 1 / 600.0
        # colonne : pivot coin haut-droit du bloc A
        piv = (STILL[0] + 78.0, STACK_BASE - RH)
        Lc = 330.0
        a = self.sway(T_TIP)
        w = 0.35
        t = T_TIP
        ang = []
        t_imp = None
        corner = (TCX - TW / 2, TBASE - 16 * RH)
        ac = math.atan2(corner[0] - piv[0], piv[1] - corner[1])
        while t < T_TIP + 1.5:
            w += 1.5 * G / Lc * math.sin(a) * dt
            a += w * dt
            t += dt
            ang.append((t, a))
            if t_imp is None and a >= ac:
                t_imp = t
                w *= 0.35
        self.col_ang = ang
        self.col_ang0 = self.sway(T_TIP)
        self.t_imp = t_imp
        self.col_piv = piv
        # tour (rangées 3 à 15) : pivot coin bas-droit de la rangée 3
        tp = (TCX + TW / 2, TBASE - 3 * RH)
        Lt = 13 * RH
        b, wb = 0.0, 0.75
        t = t_imp
        tang = []
        bc = (TABLE_X, TAB_Y)
        self.t_x2 = None
        # Bounce : petit saut après T_TIP ; on cherche quand la face de la tour le touche
        while t < t_imp + 1.5:
            wb += 1.5 * G / Lt * math.sin(max(b, 0.02)) * dt
            b += wb * dt
            t += dt
            tang.append((t, b))
            ux, uy = math.sin(b), -math.cos(b)
            cx, cy = bc[0] - tp[0], (bc[1] - 40.0) - tp[1]
            dist = abs(cx * uy - cy * ux)
            if self.t_x2 is None and dist <= RB + 2 and b > 0.2:
                self.t_x2 = t
                break
        self.tow_ang = tang
        self.tow_piv = tp
        # les blocs de la colonne et de la tour s'envolent vers le tas
        self._pile()

    def col_angle(self, tt):
        if tt < T_TIP:
            return None
        for (t, a) in self.col_ang:
            if t >= tt:
                return a
        return self.col_ang[-1][1]

    def tow_angle(self, tt):
        if tt < self.t_imp:
            return 0.0
        for (t, b) in self.tow_ang:
            if t >= tt:
                return b
        return self.tow_ang[-1][1]

    def _pile(self):
        """Où chaque bloc finit : un tas autour de Bounce, son visage dégagé."""
        bx = TABLE_X
        spots = []
        # sur sa tête, en deux couches de travers (ils bougent avec lui)
        spots += [("head", -38.0, -RB - 12, 0.07, TW), ("head", 46.0, -RB - 8, -0.10, 48.0),
                  ("head", 6.0, -RB - 40, -0.05, TW), ("head", -70.0, -RB - 38, 0.18, 48.0),
                  ("head", 60.0, -RB - 66, 0.12, TW)]
        # devant le bas de son corps : deux rangs (dessinés devant lui, sous sa bouche)
        spots += [("front", bx - 82, 1188.0, 0.0, TW), ("front", bx + 82, 1188.0, 0.03, TW), ("front", bx, 1186.0, -0.02, TW),
                  ("front", bx - 120, 1160.0, -0.10, TW), ("front", bx + 118, 1158.0, 0.12, TW), ("front", bx - 20, 1162.0, 0.05, 48.0)]
        # contre lui, de chaque côté, en appui (couches qui montent jusqu'à ses yeux)
        for k in range(4):
            spots.append(("side", bx - RB - 48 + 4 * k, 1168.0 - 30 * k, 0.32 - 0.05 * k, TW))
        for k in range(4):
            spots.append(("side", bx + RB + 48 - 4 * k, 1168.0 - 30 * k, -0.30 + 0.05 * k, TW))
        # sur la table et le coussin, à droite
        for k in range(8):
            spots.append(("rest", 830.0 + (k % 3) * 40, 1168.0 - 28 * (k // 3), 0.05 * ((k * 7) % 5 - 2), 48.0 if k % 2 else TW))
        # tombés au sol, devant la table (décor)
        for k in range(40):
            spots.append(("rest", 470.0 + (k * 67) % 470, 1610.0 + (k * 37) % 110, 0.4 * ((k * 3) % 5 - 2), 48.0 if k % 2 else TW))
        self.pile_spots = spots

    # -------------------------------------------------------------- moteur
    def step(self, dt):
        evs = []
        prev = self.t
        self.t += dt
        # le mot part sur la première image qui montre le contact (jamais avant)
        for th in self.hits:
            if prev - dt + 1e-9 < th <= prev + 1e-9:
                evs.append(("hit", "x1" if th == X1 else "table"))
        if self.t_x2 is not None:
            tv = vid(self.t_x2)
            if prev - dt + 1e-9 < tv <= prev + 1e-9:
                evs.append(("hit", "x2"))
        if not self.payoff and self.t >= PAYOFF:
            self.payoff = True
            evs.append(("payoff", "lose"))
        if self.t >= END:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # -------------------------------------------------------------- Bounce
    def bounce_pos(self, tt):
        """Position de Bounce au temps de scène tt (et décalage d'enfoui)."""
        if self.t_x2 is not None and tt >= T_TIP:
            if tt <= self.t_x2:
                return ballistic((table_x(len(HARD) - 1), TAB_Y), (TABLE_X, TAB_Y), self.t_x2 - T_TIP, tt - T_TIP)
            v = vid(tt)
            ox = 11 * math.sin(2 * math.pi * 1.7 * v) + 5 * math.sin(2 * math.pi * 2.9 * v + 1)
            oy = 7 * math.sin(2 * math.pi * 2.3 * v + 0.4) + 3 * math.sin(2 * math.pi * 3.7 * v)
            k = min(1.0, (tt - self.t_x2) / 0.25)
            push = 0.0
            if v > 65.35:
                push = -60.0 * min(1.0, (v - 65.35) / 0.5)
            return TABLE_X + ox * k, TAB_Y + oy * k + push * 1.0
        kf = self.kf
        if tt <= kf[0][0]:
            return kf[0][1], kf[0][2]
        for a, b in zip(kf, kf[1:]):
            if a[0] <= tt <= b[0]:
                return ballistic((a[1], a[2]), (b[1], b[2]), b[0] - a[0], tt - a[0])
        return kf[-1][1], kf[-1][2]

    def jolt(self, tt):
        d = 0.0
        for th in self.jolt_t:
            s = tt - th
            if 0 <= s < 0.14:
                d = max(d, 6.0 * (1 - s / 0.14))
        return d

    def cushion_dent(self, tt):
        d = 0.0
        for ts in SOFT:
            s = tt - ts
            if -0.08 <= s < 0.25:
                d = max(d, 22.0 * (1 - abs(s + 0.0) / 0.25) if s >= 0 else 22.0 * (1 + s / 0.08))
        return max(0.0, d)

    # -------------------------------------------------------------- blocs
    def slide_dx(self, key, tt):
        dx = 0.0
        for (t, v) in self.slides.get(key, []):
            if tt >= t:
                k = min(1.0, (tt - t) / 0.18) if t > -50 else 1.0
                dx = dx + (v - dx) * k
        if key == (21, "f") and tt < 2.06:
            dx += 3.0 * math.sin(tt * 5.0)          # il oscille au bord
        if key == (20, 2) and 21.45 <= tt < 26.83:
            dx += 2.5 * math.sin((tt - 21.45) * 6.0) * min(1.0, (tt - 21.45))
        if key == (13, "f") and 15.75 <= tt < 16.65:
            dx += 4.0 * math.sin((tt - 15.75) * 30.0) * math.exp(-(tt - 15.75) * 3)
        return dx

    def tower_xform(self, tt, x, y):
        """Repère de la tour : rotation autour de sa base (inclinaison) puis secousse."""
        a = self.lean(tt)
        if a >= 0:
            cx = TCX + TW / 2
        else:
            cx = TCX - TW / 2
        px, py = rot(x, y, cx, TBASE, a)
        return px, py + self.jolt(tt)

    def stack_pose(self, tt):
        """Pivot et angle de la pile de Still."""
        return STILL[0], STACK_BASE + self.jolt(tt), self.sway(tt)

    def stack_item_pos(self, idx, dx, tt):
        """Centre d'un bloc d'indice idx dans la pile."""
        px, py, a = self.stack_pose(tt)
        x, y = px + dx, py - (idx + 0.5) * RH
        return rot(x, y, px, py, a), a

    def block_quad(self, cx, cy, w, h, a):
        pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        return [rot(cx + u, cy + v, cx, cy, a) for (u, v) in pts]

    def draw_block(self, dr, S, q, col):
        pts = [(x * S, y * S) for (x, y) in q]
        dr.polygon(pts, fill=col)
        dr.line(pts + [pts[0]], fill=WOOD_E, width=max(2, int(2.2 * S)))
        # une veine du bois
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = q
        mx0, my0 = (x0 * 0.7 + x3 * 0.3), (y0 * 0.7 + y3 * 0.3)
        mx1, my1 = (x1 * 0.7 + x2 * 0.3), (y1 * 0.7 + y2 * 0.3)
        dr.line([(mx0 * S + (mx1 - mx0) * S * 0.15, my0 * S + (my1 - my0) * S * 0.15),
                 (mx0 * S + (mx1 - mx0) * S * 0.6, my0 * S + (my1 - my0) * S * 0.6)], fill=WOOD_D, width=max(1, int(1.5 * S)))

    def stack_items(self, tt):
        """Les blocs posés sur Still à tt : [(clé, idx)] ; la tranche compte pour 3 rangées."""
        items = [k for (ta, k) in self.stack if ta <= tt]
        return items

    def block_pose(self, key, tt):
        """(cx, cy, angle, w, h, couleur, plan) ou None. plan : 'back' (derrière Bounce) / 'front'."""
        b = self.blocks[key]
        ph = b.phase(tt)
        if ph is None:
            return None
        t0, kind, data = ph
        col = WOOD_BACK if (isinstance(key, tuple) and key[1] == "b") else WOOD
        # l'effondrement final prend le dessus
        coll = self.collapse_pose(key, tt, kind, data)
        if coll is not None:
            return coll
        if kind == "tower":
            r, s, _ = data
            if self.in_slab(key) and tt >= self.slab_t0:
                return self.slab_pose(key, tt)
            lx, ly, w, h = slot_local(r, s)
            lx += self.slide_dx(key, tt)
            x, y = TCX + lx, TBASE + ly
            x, y = self.tower_xform(tt, x, y)
            return (x, y, self.lean(tt), w, h, col, "back")
        if kind == "fly":
            d = data["d"]
            p0 = data["p0"]
            if p0 is None:
                # point de départ : sa pose juste avant
                prev = [p for p in b.phases if p[0] < t0]
                pk = prev[-1]
                if pk[1] == "tower":
                    r, s, _ = pk[2]
                    lx, ly, w, h = slot_local(r, s)
                    lx += self.slide_dx(key, t0)
                    p0 = self.tower_xform(t0, TCX + lx, TBASE + ly)
                else:
                    p0 = (0, 0)
                data["p0"] = p0
            if data["to"] == "stack":
                idx = [k for (_, k) in self.stack].index(key)
                (tx, ty), sa = self.stack_item_pos(idx, data["target"][0], t0 + d)
            else:
                tx, ty = data["target"]
            x, y = ballistic(p0, (tx, ty), d, tt - t0)
            u = (tt - t0) / d
            ang = data["spin"] * math.sin(u * math.pi) + data["a1"] * u
            return (x, y, ang, b.w, b.h, col, "front" if data["to"] in ("x1", "floor") else "back")
        if kind == "stack":
            idx, dx, a1 = data
            ang = a1
            if key in self.teeter:
                t1, amp, dxf, af = self.teeter[key]
                if tt >= t1:
                    s = tt - t1
                    ang = af + (a1 - af + amp) * math.exp(-s / 0.3) * math.cos(2 * math.pi * 2.0 * s)
                    dx = dxf + (dx - dxf) * math.exp(-s / 0.25)
            cr = self.crooked.get(key)
            if cr:
                for (tc, ac) in cr:
                    if tt >= tc:
                        ang += ac * min(1.0, (tt - tc) / 0.15)
            if key == "A" and tt >= vid_to_tau_end_wobble[0]:
                s = tt - vid_to_tau_end_wobble[0]
                if s < 1.0:
                    ang += 0.14 * math.exp(-s / 0.3) * math.sin(2 * math.pi * 1.6 * s)
            (x, y), sa = self.stack_item_pos(idx, dx, tt)
            if key == "A":
                (x, y), sa = self.stack_item_pos(0, dx, tt) if tt < T_TIP else ((STILL[0], STACK_BASE - RH / 2 + self.jolt(tt)), 0.0)
            return (x, y, ang + sa, b.w, b.h, col, "back")
        if kind == "rest":
            x, y, a = data
            return (x, y, a, b.w, b.h, col, "front")
        return None

    def in_slab(self, key):
        return isinstance(key, tuple) and key[0] in getattr(self, "slab_rows", [])

    def slab_pose(self, key, tt):
        """La tranche du haut (rangées 16-18) glisse d'un seul bloc sur la pile de Still."""
        r, s = key
        lx, ly, w, h = slot_local(r, s)
        lx += self.slide_dx(key, tt)
        col = WOOD_BACK if s == "b" else WOOD
        n_stack = len([1 for (ta, k) in self.stack if ta <= self.slab_t1])
        if tt < self.slab_t1:
            u = (tt - self.slab_t0) / (self.slab_t1 - self.slab_t0)
            sh = -20.0 * min(1.0, u * 3) if tt < self.slab_t1 else 0
            x, y = self.tower_xform(tt, TCX + lx + sh, TBASE + ly)
            return (x, y, self.lean(tt), w, h, col, "back")
        # glissement : de la tour vers le dessus de la pile (0,55 s), puis posé
        d = 0.55
        u = min(1.0, (tt - self.slab_t1) / d)
        e = u * u * (3 - 2 * u)
        x0, y0 = self.tower_xform(self.slab_t1, TCX + lx - 20.0, TBASE + ly)
        # cible : même rangée, empilée au-dessus des n_stack blocs de la pile
        row_off = (r - 16 + 0.5) * RH
        if u < 1.0:
            tx = STILL[0] + lx
            ty = STACK_BASE - n_stack * RH - row_off + self.jolt(tt)
            x = x0 + (tx - x0) * e
            y = y0 + (ty - y0) * e + 4.0 * max(0.0, u - 0.8) / 0.2
            return (x, y, self.lean(tt) * (1 - e), w, h, col, "back")
        px, py, a = self.stack_pose(tt)
        if tt >= T_TIP:
            return None
        x, y = STILL[0] + lx, STACK_BASE + self.jolt(tt) - n_stack * RH - row_off
        x, y = rot(x, y, px, py, a)
        return (x, y, a, w, h, col, "back")

    # -------------------------------------------------------------- collapse
    def collapse_pose(self, key, tt, kind, data):
        if tt < T_TIP or key == "A":
            return None
        if not hasattr(self, "_targets"):
            self._assign()
        info = self._targets.get(key)
        if info is None:
            return None
        group, base_pose, t_brk, spot = info
        if tt < t_brk:
            # rigide avec son groupe
            x, y, a = base_pose(tt)
            return (x, y, a, self.blocks[key].w, self.blocks[key].h, WOOD_BACK if (isinstance(key, tuple) and key[1] == "b") else WOOD, "back")
        # en vol vers son emplacement
        x0, y0, a0 = base_pose(t_brk)
        kindS, sx, sy, sa, sw = spot
        if kindS == "head":
            hx, hy = self.bounce_pos(max(tt, t_brk))
            tx, ty = hx + sx, hy + sy
        else:
            tx, ty = sx, sy
        dfall = max(0.18, math.sqrt(max(1.0, 2 * (ty - y0)) / G) if ty > y0 else 0.25)
        dfall = min(dfall, 0.55)
        u = tt - t_brk
        if u < dfall:
            x, y = ballistic((x0, y0), (tx, ty), dfall, u)
            a = a0 + (sa - a0) * (u / dfall)
            plane = "front" if kindS in ("head", "front", "side") or tx > 560 else "back"
            return (x, y, a, self.blocks[key].w, self.blocks[key].h, WOOD_BACK if (isinstance(key, tuple) and key[1] == "b") else WOOD, plane)
        if kindS == "head":
            hx, hy = self.bounce_pos(tt)
            return (hx + sx, hy + sy, sa, self.blocks[key].w, self.blocks[key].h, WOOD, "front")
        if kindS in ("side", "front"):
            hx, hy = self.bounce_pos(tt)
            kk = 0.45 if kindS == "side" else 0.15
            tx, ty = tx + kk * (hx - TABLE_X), ty + kk * (hy - TAB_Y)
            sa = sa + (0.002 * (hx - TABLE_X) if kindS == "side" else 0.0)
        plane = "front" if kindS in ("front", "side") or tx > 560 else "back"
        return (tx, ty, sa, self.blocks[key].w, self.blocks[key].h, WOOD_BACK if (isinstance(key, tuple) and key[1] == "b") else WOOD, plane)

    def _assign(self):
        """Groupes rigides : la colonne (pile de Still sans A), la tour (rangées 3-15).
        Chaque bloc reçoit un instant de rupture et un emplacement du tas."""
        self._targets = {}
        stack_keys = [k for (ta, k) in self.stack if ta <= T_TIP and k != "A"]
        slab_keys = [k for k in self.blocks if self.in_slab(k) and self.blocks[k].phase(T_TIP)[1] == "tower"]
        spots = list(self.pile_spots)
        piv = self.col_piv
        n_st = len(stack_keys)

        def col_pose_fn(key, local):
            def f(tt):
                a0 = self.col_angle(tt) - self.col_ang0
                x, y, a = local
                px, py = piv
                X, Y = rot(x, y, px, py, a0)
                return X, Y, a + a0
            return f
        # la colonne : positions locales à T_TIP (pile droite, à son angle de balancement)
        sw = self.sway(T_TIP)
        locs = []
        for i, k in enumerate(stack_keys):
            p = self.block_pose_static_stack(k, T_TIP)
            locs.append((k, p))
        for k in slab_keys:
            p = self.slab_pose(k, T_TIP - 1e-3)
            locs.append((k, (p[0], p[1], p[2])))
        # au sol devant la table : les blocs du haut de la colonne ; sur Bounce : ceux du bas de la tour
        order = sorted(locs, key=lambda kp: kp[1][1])     # du plus haut au plus bas
        far = [s for s in spots if s[0] == "rest" and s[2] >= 1500]
        rest = [s for s in spots if s[0] == "rest" and s[2] < 1500]
        side = [s for s in spots if s[0] == "side"]
        head = [s for s in spots if s[0] == "head"]
        front = [s for s in spots if s[0] == "front"]
        # la tour, rangées 3 à 15 : c'est elle qui tombe sur lui
        tp = self.tow_piv
        tkeys = [k for k in self.blocks if isinstance(k, tuple) and 3 <= k[0] <= 15
                 and self.blocks[k].phase(T_TIP) is not None and self.blocks[k].phase(T_TIP)[1] == "tower"]

        def tow_pose_fn(key):
            r, s = key
            lx, ly, w, h = slot_local(r, s)
            lx += self.slide_dx(key, T_TIP)

            def f(tt):
                b = self.tow_angle(tt)
                tf = min(tt, self.t_imp)
                x0, y0 = self.tower_xform(tf, TCX + lx, TBASE + ly)
                X, Y = rot(x0, y0, tp[0], tp[1], b)
                return X, Y, b + self.lean(tf)
            return f
        tkeys.sort(key=lambda k: (k[0], str(k[1])))
        pool = side[:] + front[:] + head[:]
        pool_order = []
        # rangées basses -> côtés et devant ; rangées du milieu -> sa tête ; hautes -> au-delà
        for i, k in enumerate(tkeys):
            t_brk = self.t_x2 - 0.03 + 0.006 * i
            r = k[0]
            if r <= 6 and side:
                spot = side.pop(0)
            elif r <= 9 and front:
                spot = front.pop(0)
            elif head:
                spot = head.pop(0)
            elif side:
                spot = side.pop(0)
            elif front:
                spot = front.pop(0)
            elif rest:
                spot = rest.pop(0)
            else:
                spot = far.pop(0)
            self._targets[k] = ("tow", tow_pose_fn(k), t_brk, spot)
        # la colonne (pile de Still) : par-dessus, puis sur la table à droite et au sol
        for i, (k, p) in enumerate(order[::-1]):
            t_brk = self.t_imp + 0.02 + 0.01 * i
            if head:
                spot = head.pop(0)
            elif side:
                spot = side.pop(0)
            elif rest:
                spot = rest.pop(0)
            else:
                spot = far.pop(0)
            self._targets[k] = ("col", col_pose_fn(k, p), t_brk, spot)

    def block_pose_static_stack(self, key, tt):
        b = self.blocks[key]
        ph = b.phase(tt)
        t0, kind, data = ph
        idx, dx, a1 = data
        (x, y), sa = self.stack_item_pos(idx, dx, tt)
        ang = a1
        if key in self.teeter:
            ang = self.teeter[key][3]
            t1, amp, dxf, af = self.teeter[key]
            (x, y), sa = self.stack_item_pos(idx, dxf, tt)
        cr = self.crooked.get(key)
        if cr:
            for (tc, ac) in cr:
                ang += ac
        return (x, y, ang + sa)

    # -------------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        tt = tau(t)
        img = dr._image
        jol = self.jolt(tt)
        # mur et lampe
        dr.rectangle([0, 0, W * S, 1120 * S], fill=(20, 22, 38))
        for k in range(10):
            rr = (520 - 40 * k) * S
            c = tuple(int(v) for v in np.array((20, 22, 38)) + (np.array((54, 46, 52)) - np.array((20, 22, 38))) * (k / 9) * 0.55)
            dr.ellipse([440 * S - rr, 860 * S - rr * 0.8, 440 * S + rr, 860 * S + rr * 0.8], fill=c)
        dr.rectangle([0, 1265 * S, W * S, H * S], fill=(14, 13, 20))
        for k in range(6):
            yk = (1300 + 70 * k) * S
            dr.line([(0, yk), (W * S, yk)], fill=(20, 19, 28), width=int(3 * S))
        dr.ellipse([60 * S, 1540 * S, 1020 * S, 1800 * S], fill=(52, 26, 40))
        dr.ellipse([90 * S, 1560 * S, 990 * S, 1780 * S], outline=(74, 40, 56), width=int(6 * S))
        dr.rectangle([150 * S, 1470 * S, 380 * S, 1560 * S], fill=(44, 92, 120))
        dr.rectangle([150 * S, 1470 * S, 380 * S, 1490 * S], fill=(58, 116, 148))
        for k in range(4):
            dr.rectangle([(240 + (k % 2) * 26) * S, (1540 - 16 * k) * S, (266 + (k % 2) * 26) * S, (1552 - 16 * k) * S], fill=WOOD)
        # coussin et tabouret
        dent = self.cushion_dent(tt)
        dr.rectangle([745 * S, 1225 * S, 815 * S, 1500 * S], fill=(70, 52, 40))
        dr.rounded_rectangle([680 * S, (CUSH_TOP + dent) * S, 900 * S, 1245 * S], radius=int(30 * S), fill=(150, 132, 206))
        dr.rounded_rectangle([690 * S, (CUSH_TOP + dent + 8) * S, 890 * S, (CUSH_TOP + dent + 26) * S], radius=int(9 * S), fill=(176, 160, 226))
        # Still (posée contre le bord arrière de la table, elle tressaute avec elle)
        gx = 0.0
        if 2.6 <= tt < 3.4 or 7.9 <= tt < 8.6 or 34.6 <= tt < 35.4:
            gx = -0.6
        if 27.2 <= tt < 28.4 or tt >= vid_to_tau_end_wobble[0] + 0.9:
            gx = 0.9
        draw_still(dr, STILL[0], STILL[1] + jol, STILL[2], S, gx=gx)
        # table
        dr.polygon([(110 * S, (1120 + jol) * S), (730 * S, (1120 + jol) * S), (740 * S, (1205 + jol) * S), (100 * S, (1205 + jol) * S)], fill=(150, 104, 62))
        dr.line([(110 * S, (1120 + jol) * S), (730 * S, (1120 + jol) * S)], fill=(176, 128, 82), width=int(3 * S))
        dr.rectangle([100 * S, (1205 + jol) * S, 740 * S, (1262 + jol) * S], fill=(112, 74, 44))
        for lx in (130, 690):
            dr.rectangle([lx * S, (1262 + jol) * S, (lx + 26) * S, 1560 * S], fill=(96, 62, 36))
        # blocs : derrière / devant Bounce
        poses = []
        for key in self.blocks:
            p = self.block_pose(key, tt)
            if p is not None:
                poses.append((key, p))
        back = [p for p in poses if p[1][6] == "back"]
        front = [p for p in poses if p[1][6] == "front"]
        bx, by = self.bounce_pos(tt)
        # 1) ce qui est derrière Bounce, sur une copie, pour le remettre par-dessus son halo
        r_h = int(RB * 1.6 * S) + 2
        x0, y0 = max(0, int(bx * S) - r_h), max(0, int(by * S) - r_h)
        x1, y1 = min(W * S, int(bx * S) + r_h), min(H * S, int(by * S) + r_h)
        box = (x0, y0, x1, y1)
        before = img.crop(box)
        for key, (x, y, a, w, h, col, _) in sorted(back, key=lambda kp: -kp[1][1]):
            self.draw_block(dr, S, self.block_quad(x, y, w, h, a), col)
        with_obj = img.crop(box)
        # 2) Bounce
        if tt >= T_TIP and self.t_x2 is not None and tt >= self.t_x2:
            base.HERO["expr"] = "lose" if PAYOFF <= t < PAYOFF + 1.3 else ("shock" if t < self.t_x2v + 0.8 else "calm")
        else:
            shock_until = -1
            for th in self.hits:
                if th <= tt:
                    shock_until = th + (1.1 if (th in PASSES or th == X1) else 0.3)
            base.HERO["expr"] = "shock" if tt < shock_until else "calm"
        base.ball(dr, bx * S, by * S, RB * S)
        # 3) les objets derrière lui reviennent par-dessus son halo (pas sur son corps)
        if x1 > x0 and y1 > y0:
            bo = np.asarray(before).astype(np.int16)
            wo = np.asarray(with_obj)
            cur = np.asarray(img.crop((x0, y0, x1, y1))).copy()
            yy, xx = np.mgrid[y0:y1, x0:x1]
            dd = (xx - bx * S) ** 2 + (yy - by * S) ** 2
            obj = np.abs(wo.astype(np.int16) - bo).sum(axis=2) > 6
            m = obj & (dd > (RB * S + 1) ** 2)
            cur[m] = wo[m]
            img.paste(Image.fromarray(cur), (x0, y0))
        # 4) devant
        for key, (x, y, a, w, h, col, _) in sorted(front, key=lambda kp: kp[1][1]):
            self.draw_block(dr, S, self.block_quad(x, y, w, h, a), col)


vid_to_tau_end_wobble = [999.0]

DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0,
            "hook_text_s": 8.3, "hook_top": 0.125, "hook_font_size": 96, "hero_shock_s": 0.3}


def _post_init(sim):
    sim.t_x2v = vid(sim.t_x2)
    # le bloc A vacille une fois pendant le battement (temps de scène)
    vid_to_tau_end_wobble[0] = tau(sim.t_x2v + 0.95)


_Init = Sim.__init__


def _init(self, cfg, rng):
    _Init(self, cfg, rng)
    _post_init(self)
    if self.t_x2 is not None:
        self.jolt_t.append(self.t_x2)


Sim.__init__ = _init

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
