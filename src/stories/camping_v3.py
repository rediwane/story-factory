"""
camping v3 : « HOW MANY BEARS? ». La nuit, Bounce rebondit dans une tente dôme ouverte. Chaque contact
dur (sol, glacière, lanterne) lui fait dire son nom et envoie un anneau blanc : l'ours que l'anneau
touche fait un bond vers la tente, puis entre. Un rebond mou (sac de couchage, ours, rocher) est muet,
et l'ours dehors se fige. La tente se remplit (deux ours, un ourson par l'aération du toit, deux ours
par la porte qui s'assoient là où il frappe le sol, un grand ours, un ours coincé), une ourse géante
arrive, la pression le chasse par l'aération ; il retombe sur le « rocher » de l'image 0, qui était un
ours. Dernière image raccord avec l'image 0.

Tout est écrit d'avance sur une horloge : la liste des contacts de Bounce (arcs balistiques exacts
sous G entre deux contacts), les poses des ours par images clés. Nouveau fichier : base.py n'est pas
modifié ; la réverbération du moteur passe par une convolution FFT équivalente.

    python3 src/stories/camping_v3.py configs/camping_v3.json [--simulate | --plan | --still t1,t2,... dir]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
from PIL import Image, ImageDraw

SR = ak.SR

# ------------------------------------------------------------------ son : le mot de Bounce, stable
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.74:
                break
        if best is not None:
            best = np.where(np.abs(best) < 1e-9, 0.0, best)
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

_np_convolve = np.convolve


def _fft_convolve(a, v, mode="full"):
    a, v = np.asarray(a, float), np.asarray(v, float)
    if mode != "full" or min(len(a), len(v)) < 64:
        return _np_convolve(a, v, mode)
    n = len(a) + len(v) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, N) * np.fft.rfft(v, N), N)[:n]


def reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    """base.reverb, mais par FFT (même réponse impulsionnelle, même mélange)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    wetx = _fft_convolve(x, ir)
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = reverb_fft

# la voix d'accroche : silences de tête et de queue retirés, dite 7 % plus vite, pour que le
# premier « Bounce » (1,48 s) tombe après elle
_orig_hook_voice = ak.hook_voice
_hook_memo = {}


def tight_hook_voice(text, sr=SR, prefer_piper=True):
    if text not in _hook_memo:
        x = _orig_hook_voice(text, sr, prefer_piper)
        if x is not None and len(x):
            a = np.abs(x)
            idx = np.where(a > 0.012)[0]
            if len(idx):
                x = x[max(0, idx[0] - int(0.01 * sr)): idx[-1] + int(0.02 * sr)]
            n = int(len(x) / 1.07)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
            fade = int(0.01 * sr)
            x[-fade:] *= np.linspace(1, 0, fade)
        _hook_memo[text] = x
    x = _hook_memo[text]
    return None if x is None else x.copy()


ak.hook_voice = tight_hook_voice

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
R = 120.0
G = 2600.0


def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, s):
    return a + (b - a) * s


def mix(c0, c1, s):
    s = clamp01(s)
    return tuple(int(a + (b - a) * s) for a, b in zip(c0, c1))


def pulse(t, t0, a=0.12, b=0.25):
    if t < t0 - a or t > t0 + b:
        return 0.0
    if t <= t0:
        return smooth((t - (t0 - a)) / a) if a > 0 else 1.0
    return 1.0 - smooth((t - t0) / b)


def ramp(t, t0, t1):
    return smooth((t - t0) / max(1e-6, t1 - t0))


class Keys:
    def __init__(self, keys, ease=smooth):
        self.k = sorted(keys, key=lambda p: p[0])
        self.ease = ease

    def __call__(self, t):
        k = self.k
        if t <= k[0][0]:
            return k[0][1]
        for (t0, v0), (t1, v1) in zip(k, k[1:]):
            if t <= t1:
                s = self.ease((t - t0) / max(1e-6, t1 - t0))
                if isinstance(v0, tuple):
                    return tuple(lerp(a, b, s) for a, b in zip(v0, v1))
                return lerp(v0, v1, s)
        return k[-1][1]


def P(x, y, S):
    return (x * S, y * S)


def ell(dr, x, y, rx, ry, fill, S):
    dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=fill)


# ------------------------------------------------------------------ le temps : un seul ralenti
SLOW_A, SLOW_B, SLOW_K = 57.95, 59.45, 0.4


def warp(t):
    """Horloge du monde (ours, tente) : ralentie × SLOW_K entre SLOW_A et SLOW_B."""
    if t <= SLOW_A:
        return t
    if t <= SLOW_B:
        return SLOW_A + (t - SLOW_A) * SLOW_K
    return SLOW_A + (SLOW_B - SLOW_A) * SLOW_K + (t - SLOW_B)


# ------------------------------------------------------------------ la scène
DCX, BASE = 510.0, 1250.0
DOA, DOB = 250.0, 690.0             # la porte (demi-ellipse)
FLOOR_BACK, FLOOR_FRONT = 1170.0, 1246.0
FLOOR_C = 1100.0                     # centre de Bounce posé sur le tapis
COOLER = (255.0, 1085.0, 412.0, 1238.0)
COOL_C = COOLER[1] - R
BAG = (585.0, 1150.0, 778.0, 1240.0)
BAG_C = BAG[1] - R + 16
ROCK = (265.0, 1180.0, 135.0, 86.0)  # centre, demi-axes
ROCK_C = ROCK[1] - ROCK[3] - R + 8
VENT_X = 420.0
LANT_X = 600.0
LANT_H = 76.0


def dome_shape(t):
    """(demi-largeur, hauteur, levée de la base) de la tente, qui gonfle à chaque palier."""
    tw = warp(t)
    a = Keys([(0, 340.0), (25.4, 340.0), (25.9, 350.0), (35.6, 350.0), (36.2, 358.0), (41.2, 358.0),
              (41.7, 362.0), (53.6, 362.0), (54.1, 366.0), (55.9, 366.0), (56.6, 374.0)])(tw)
    b = Keys([(0, 770.0), (25.4, 770.0), (25.9, 786.0), (35.6, 786.0), (36.2, 806.0), (41.2, 806.0),
              (41.7, 812.0), (53.6, 812.0), (54.1, 820.0), (55.9, 820.0), (56.6, 836.0)])(tw)
    lift = 30.0 * pulse(tw, 36.0, 0.25, 0.6) + 10.0 * ramp(tw, 36.0, 36.6)
    # le sol tressaute sous les pas de la géante
    for tg in (48.97, 50.32):
        lift += 14.0 * pulse(tw, tg, 0.05, 0.25)
    # tangage quand ça pousse
    wob = 0.0
    for (t0, amp) in ((23.15, 6), (24.1, 8), (25.15, 6), (41.2, 7), (42.7, 6), (53.85, 9), (56.15, 10)):
        if tw > t0:
            u = tw - t0
            wob += amp * math.exp(-u * 2.2) * math.sin(u * 13.0)
    return a, b, lift, wob


def dome_y(x, t, shape=None):
    a, b, lift, _ = shape or dome_shape(t)
    u = (x - DCX) / a
    if abs(u) >= 1:
        return BASE - lift
    return BASE - lift - b * math.sqrt(1 - u * u)


def door_a(t):
    return Keys([(0, DOA), (41.25, DOA), (41.55, 234.0), (53.6, 234.0), (54.0, 244.0)])(warp(t))


def door_y(x, t, da=None):
    da = door_a(t) if da is None else da
    u = (x - DCX) / da
    if abs(u) >= 1:
        return BASE
    return BASE - DOB * math.sqrt(1 - u * u)


def vent_pos(t):
    sh = dome_shape(t)
    return VENT_X, 0.5 * (dome_y(VENT_X, t, sh) + door_y(VENT_X, t))


# ------------------------------------------------------------------ Bounce : les contacts
# (t, surface, x) ; dur = « Bounce ». Les y viennent des surfaces.
HARD = {"floor", "cool", "lant"}
SEQ = [
    (0.15, "rock", 250), (0.75, "rock", 285),
    (1.48, "floor", 430), (2.10, "bag", 660), (2.60, "bag", 720), (3.00, "cool", 385), (3.55, "bag", 700),
    (4.10, "floor", 520), (4.80, "bag", 655), (5.45, "bag", 720),
    (6.10, "floor", 470), (6.75, "bag", 650), (7.30, "cool", 390), (7.95, "bag", 700),
    (8.80, "floor", 500), (9.35, "bag", 640), (9.90, "floor", 450), (10.30, "bag", 650),
    (10.85, "b2", 700), (11.40, "floor", 500), (11.85, "b2", 690), (12.30, "cool", 380), (13.00, "b2", 700),
    (13.75, "floor", 480), (14.25, "b2", 690), (14.70, "cool", 375), (15.25, "b2", 650), (15.75, "b2", 680),
    (16.15, "b2", 650),
    (16.45, "lant", 0), (16.80, "b2", 680), (17.35, "floor", 520), (18.00, "b2", 690), (18.65, "cool", 380),
    (19.10, "b2", 690), (19.55, "floor", 440), (20.15, "b2", 700), (20.55, "b2", 660), (20.85, "lant", 0),
    (21.12, "b4", 440), (21.75, "floor", 600), (22.40, "b4", 440), (23.05, "cool", 380), (23.55, "b4", 450),
    (24.00, "floor", 520), (24.45, "b4", 450), (24.80, "b5", 650), (25.05, "lant", 0),
    # (à partir de 25,05 : rebonds sur les têtes, générés par heads_era())
    # la poche se referme : rebonds mous de plus en plus courts vers l'aération
    (56.25, "pk1", 470), (56.78, "pk2", 395), (57.20, "pk3", 440), (57.60, "pk4", 410),
]
HEAD_X = {"b4": 462.0, "b5": 600.0, "b2": 688.0, "b7": 652.0, "cub": 322.0}
HEADS_HARD = [(25.05, "lant"), (27.30, "lant"), (28.55, "lant"), (32.75, "lant"), (33.70, "lant"),
              (35.25, "cool"), (37.40, "lant"), (39.00, "lant"), (39.95, "cool"), (41.10, "lant"),
              (42.60, "lant"), (43.50, "lant"), (44.85, "lant"), (46.95, "lant"), (48.85, "lant"),
              (50.20, "lant"), (52.30, "lant"), (53.75, "lant"), (55.98, "lant")]
CYCLE = ["b2", "b4", "b5", "b2", "b4", "b5"]
NEAR = (31.113, "b4", 445.0, "b2", 700.0, 0.0)   # le presque : départ, de, x, vers, x


def heads_era():
    out = []
    ci = 0
    prev = "b5"
    for (ta, sa), (tb, sb) in zip(HEADS_HARD, HEADS_HARD[1:]):
        items = []
        if ta < 30.9 < tb:          # l'omission 1 : une suite de rebonds mous, et le presque
            items = [(28.81, "b4"), (29.40, "b2"), (29.95, "b4"), (30.55, "b2"), (NEAR[0], "b4"),
                     (31.756, "b2"), (32.20, "b4"), (32.49, "b2")]
        else:
            first = ta + (0.26 if sa == "lant" else 0.0)
            last = tb - (0.26 if sb == "lant" else 0.0)
            names = []
            n = max(0, int(math.ceil((last - first) / (0.62 if tb < 53.8 else 0.5))) + 1) if (sa == "lant" or sb == "lant") else \
                max(1, int(round((tb - ta) / 0.58)) - 1)
            if sa != "lant" and sb != "lant":
                first, last = ta + (tb - ta) / (n + 1), tb - (tb - ta) / (n + 1)
            elif sa != "lant":
                first = ta + (last - ta) / (n + 0.0) if n else last
            elif sb != "lant":
                last = tb - (tb - first) / (n + 0.0) if n else first
            for k in range(n):
                tt = first if n == 1 else first + (last - first) * k / (n - 1)
                edge = (k == 0 and sa == "lant") or (k == n - 1 and sb == "lant")
                pool = ["b4", "b2"] if edge else CYCLE
                nm = pool[ci % len(pool)]
                if nm == prev:
                    ci += 1
                    nm = pool[ci % len(pool)]
                ci += 1
                items.append((tt, nm))
                prev = nm
        for j, (tt, nm) in enumerate(items):
            out.append((round(tt, 3), nm, HEAD_X[nm] + (-18 if (len(out) % 2) else 18)))
    return out


SEQ = sorted(SEQ + [(t, "lant" if s_ == "lant" else "cool", 385) if False else (t, s_, 385 if s_ == "cool" else 0)
                    for (t, s_) in HEADS_HARD[1:]] + heads_era(), key=lambda r: r[0])

EXTRUDE_A, EXTRUDE_B = 57.80, 58.45      # sortie continue par l'aération (temps réel)
EXTRUDE_Y0, EXTRUDE_Y1 = 712.0, 548.0
EXIT_VX, EXIT_VY = -230.0, -560.0         # vitesse au sortir de l'aération (horloge du monde)
# rebonds sur le rocher après la chute (hauteurs décroissantes)
HEAD_UP_Y = 1010.0                        # centre de la tête de l'ours-rocher, levée
HEAD_R = 100.0
RHEAD_X = 340.0
HEAD_C = HEAD_UP_Y - HEAD_R - R + 6
END_SEQ = [(60.80, 335.0, "rhead"), (61.42, 355.0, "rhead"), (61.98, 328.0, "rhead"), (62.45, 345.0, "rhead"),
           (63.05, 290.0, "rock"), (63.80, 250.0, "rock")]
END_T = 63.65
FINAL_AFTER_APEX = 0.10


def lantern_pos(t):
    """Le bas de la lanterne (x, y) ; elle se balance au gré des coups et saute un peu quand il la cogne."""
    ax = LANT_X
    ay = door_y(LANT_X, t) + 14.0
    a = 0.0
    for (tk, amp) in LANT_KICKS:
        if t > tk:
            u = t - tk
            a += amp * math.exp(-u / 1.8) * math.sin(5.6 * u)
    L = LANT_H - 8.0
    return ax + L * math.sin(a), ay + L * math.cos(a), a


LANT_KICKS = []


def surface_y(s, t, x=None):
    if s == "rock":
        return ROCK_C
    if s == "floor":
        return FLOOR_C
    if s == "cool":
        return COOL_C
    if s == "bag":
        return BAG_C
    if s == "lant":
        return lantern_pos(t)[1] + R
    if s in ("b1", "b2", "b4", "b5", "b7", "cub"):
        return BEARS[s].head_top(t) - R + 6
    if s.startswith("pk"):
        return {"pk1": 920.0, "pk2": 872.0, "pk3": 840.0, "pk4": 800.0}[s]
    raise KeyError(s)


class Ball:
    def __init__(self):
        C = []
        for (t, s, x) in SEQ:
            if s == "lant":
                lx, ly, _ = lantern_pos(t - 0.001)
                C.append([t, lx - 8.0, ly + R, s])
                LANT_KICKS.append((t + 0.005, 0.10))
            else:
                C.append([t, float(x), surface_y(s, t), s])
        self.C = C
        self.hits = [c[0] for c in C if c[3] in HARD]
        # la sortie : de la fin de la poche au bas de l'aération (arc qui arrive en montant)
        c = C[-1]
        self.ext0 = (VENT_X, EXTRUDE_Y0)
        T = EXTRUDE_A - c[0]
        vy0 = (EXTRUDE_Y0 - c[2] - 0.5 * G * T * T) / T
        self.bridge = (c[0], c[1], c[2], (VENT_X - c[1]) / T, vy0, T)
        self.v_ext_in = vy0 + G * T
        # l'arc de sortie, sur l'horloge du monde
        w0 = warp(EXTRUDE_B)
        dy = ROCK_C - EXTRUDE_Y1
        Ts = (-EXIT_VY + math.sqrt(EXIT_VY ** 2 + 2 * G * dy)) / G
        self.exit = (w0, Ts)
        land_w = w0 + Ts
        # temps réel de l'atterrissage
        if land_w <= warp(SLOW_B):
            self.t_land = SLOW_A + (land_w - SLOW_A) / SLOW_K
        else:
            self.t_land = SLOW_B + (land_w - warp(SLOW_B))
        self.x_land = VENT_X + EXIT_VX * Ts
        # la fin : sur le rocher, puis sur la tête de l'ours-rocher, puis de nouveau sur le rocher
        self.end = [(self.t_land, self.x_land, ROCK_C, "rock")] + [(t_, x_, ROCK_C if s_ == "rock" else HEAD_C, s_)
                                                                    for (t_, x_, s_) in END_SEQ]
        self.t_end = END_T

    def pos(self, t):
        C = self.C
        if t <= C[0][0]:
            # même arc que la dernière image (raccord) : 0,15 s avant le contact sur le rocher
            Tl = END_SEQ[-1][0] - END_SEQ[-2][0]
            vc = 0.5 * G * Tl
            vx = (END_SEQ[-1][1] - END_SEQ[-2][1]) / Tl
            u = C[0][0] - t
            return C[0][1] - vx * u, C[0][2] - vc * u + 0.5 * G * u * u
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                T = b[0] - a[0]
                u = t - a[0]
                vy = (b[2] - a[2] - 0.5 * G * T * T) / T
                return lerp(a[1], b[1], u / T), a[2] + vy * u + 0.5 * G * u * u
        t0, x0, y0, vx, vy0, T = self.bridge
        if t <= EXTRUDE_A:
            u = t - t0
            return x0 + vx * u, y0 + vy0 * u + 0.5 * G * u * u
        if t <= EXTRUDE_B:
            # poussé par la pression : vitesse qui décroît de façon monotone, jamais nulle
            u = (t - EXTRUDE_A) / (EXTRUDE_B - EXTRUDE_A)
            v_end = -EXIT_VY * SLOW_K       # px/s réels à la sortie
            v_in = -self.v_ext_in
            Ttot = EXTRUDE_B - EXTRUDE_A
            # profil de vitesse linéaire v_in -> v_end, ajusté pour couvrir la distance
            dist = EXTRUDE_Y0 - EXTRUDE_Y1
            v_mid = 2 * dist / Ttot - 0.5 * (v_in + v_end)
            # vitesse par morceaux : v_in -> v_mid -> v_end
            if u < 0.5:
                d = Ttot * (v_in * u + (v_mid - v_in) * u * u)
            else:
                d0 = Ttot * (v_in * 0.5 + (v_mid - v_in) * 0.25)
                w = u - 0.5
                d = d0 + Ttot * (v_mid * w + (v_end - v_mid) * w * w)
            return VENT_X, EXTRUDE_Y0 - d
        tw = warp(t)
        w0, Ts = self.exit
        if tw <= w0 + Ts:
            u = tw - w0
            return VENT_X + EXIT_VX * u, EXTRUDE_Y1 + EXIT_VY * u + 0.5 * G * u * u
        E = self.end
        for a, b in zip(E, E[1:]):
            if a[0] <= t <= b[0]:
                T = b[0] - a[0]
                u = t - a[0]
                vy = (b[2] - a[2] - 0.5 * G * T * T) / T
                return lerp(a[1], b[1], u / T), a[2] + vy * u + 0.5 * G * u * u
        a = E[-1]
        return a[1], a[2]

    def contacts_soft(self):
        out = [(c[0], c[3], c[1]) for c in self.C if c[3] not in HARD]
        out += [(e[0], e[3], e[1]) for e in self.end]
        return out


# ------------------------------------------------------------------ les ours
BROWN = [(150, 98, 60), (160, 108, 66), (142, 92, 58), (166, 112, 70), (138, 90, 56), (172, 118, 74),
         (148, 100, 64)]
MUZ = (204, 160, 116)
RIM = (236, 222, 190)
ROCK_GREY = (112, 104, 98)


class Bear:
    """Un ours par images clés : moves = [(t, x, y, s, mode)] ; entre deux clés, un bond
    (si `hop`) ou un glissement. y = la base (pattes, ou derrière assis)."""

    def __init__(self, name, col, moves, layer_keys, hop_s=0.36, freezes=(), swings=(), perks=()):
        self.name = name
        self.col = col
        self.moves = moves
        self.layer_keys = layer_keys
        self.hop_s = hop_s
        self.freezes = freezes
        self.perks = perks

    def state(self, t):
        tw = warp(t)
        m = self.moves
        if tw <= m[0][0]:
            k = m[0]
            return dict(x=k[1], y=k[2], s=k[3], mode=k[4], hop=0.0)
        for a, b in zip(m, m[1:]):
            if tw <= b[0]:
                # immobile jusqu'au départ du mouvement, qui dure b[5] s (par défaut hop_s)
                dur = b[5] if len(b) > 5 else self.hop_s
                t0 = b[0] - dur
                if tw <= t0:
                    return dict(x=a[1], y=a[2], s=a[3], mode=a[4], hop=0.0)
                u = (tw - t0) / dur
                e = smooth(u)
                kind = b[6] if len(b) > 6 else "hop"
                hop = math.sin(math.pi * u) if kind == "hop" else 0.0
                return dict(x=lerp(a[1], b[1], e), y=lerp(a[2], b[2], e) - 34 * b[3] * hop,
                            s=lerp(a[3], b[3], e), mode=b[4] if u > 0.5 else a[4], hop=hop)
        k = m[-1]
        return dict(x=k[1], y=k[2], s=k[3], mode=k[4], hop=0.0)

    def layer(self, t):
        tw = warp(t)
        cur = self.layer_keys[0][1]
        for (tk, lay) in self.layer_keys:
            if tw >= tk:
                cur = lay
        return cur

    def head_top(self, t):
        st = self.state(t)
        s = st["s"]
        if st["mode"] == "lie":
            return st["y"] - 108 * s + SQUEEZE(t)
        if st["mode"] == "sit":
            return st["y"] - 204 * s + SQUEEZE(t)
        return st["y"] - 150 * s


def SQUEEZE(t):
    """Tout remonte dans la tente quand la géante pousse."""
    return BEAR_SHIFT(t)


def BEAR_SHIFT(t):
    tw = warp(t)
    return -26.0 * ramp(tw, 53.8, 54.3) - 40.0 * ramp(tw, 56.1, 57.6)


# t (horloge du monde) des bonds : quelques centièmes après le contact dur qui les cause
def hk(t):
    return t + 0.08 + 0.36


B = {}
# l'ours 1 : à gauche, déjà en marche à l'image 0
B["b1"] = Bear("b1", BROWN[0], [
    (0.0, 236, 642, 1.22, "walk"), (1.48, 246, 652, 1.22, "walk", 1.48, "slide"),
    (hk(1.48), 268, 724, 1.28, "walk"), (hk(3.00), 300, 806, 1.32, "walk"), (hk(4.10), 372, 960, 1.32, "walk"),
    (5.00, 330, 1110, 0.92, "sit", 0.55, "slide"), (5.55, 322, 1180, 0.95, "sit", 0.55, "slide"),
    (35.95, 322, 1180, 0.95, "sit"), (36.3, 306, 1178, 0.95, "sit", 0.35, "slide"),
], [(0, "out"), (4.75, "enterL"), (5.6, "in")])
B["b2"] = Bear("b2", BROWN[1], [
    (0.0, 790, 700, 1.0, "walk"), (6.10, 790, 700, 1.0, "walk"), (6.30, 786, 650, 1.18, "walk", 0.25, "slide"),
    (hk(7.30), 772, 724, 1.24, "walk"), (hk(8.80), 742, 806, 1.28, "walk"), (hk(9.90), 650, 960, 1.28, "walk"),
    (10.60, 690, 1120, 1.0, "lie", 0.45, "slide"), (10.90, 682, 1216, 1.08, "lie", 0.30, "slide"),
], [(0, "hidden"), (6.12, "outR"), (10.25, "enterR"), (10.95, "in")])
B["cub"] = Bear("cub", BROWN[3], [
    (0.0, 188, 420, 0.42, "walk"), (11.40, 188, 420, 0.42, "walk"), (11.60, 196, 408, 0.46, "walk", 0.2, "slide"),
    (12.30, 196, 408, 0.46, "walk"), (12.95, 372, 418, 0.46, "walk", 0.6, "slide"),
    (13.75, 372, 418, 0.46, "walk"), (14.15, 400, 512, 0.46, "walk", 0.4, "hop"),
    (14.70, 404, 520, 0.46, "walk"), (15.10, 416, 540, 0.46, "dive", 0.4, "slide"),
    (15.40, 360, 880, 0.5, "sit", 0.3, "slide"), (15.55, 326, 1002, 0.5, "sit", 0.15, "slide"),
], [(0, "hidden"), (11.42, "branch"), (13.40, "roof"), (14.95, "vent"), (15.12, "in")])
B["b4"] = Bear("b4", BROWN[2], [
    (0.0, 214, 760, 1.15, "walk"), (16.45, 214, 760, 1.15, "walk"), (16.65, 214, 740, 1.22, "walk", 0.2, "slide"),
    (hk(17.35), 262, 640, 0.95, "walk"), (18.75, 300, 880, 0.95, "fall", 0.5, "slide"),
    (19.20, 330, 1238, 1.0, "sit", 0.35, "slide"),
    (hk(19.55) - 0.15, 440, 1245, 1.0, "sit", 0.45, "slide"),
    (hk(24.00), 462, 1245, 1.0, "sit", 0.4, "slide"),
], [(0, "hidden"), (16.47, "outL"), (17.75, "front"), (18.85, "in")])
B["b5"] = Bear("b5", BROWN[5], [
    (0.0, 806, 760, 1.15, "walk"), (16.45, 806, 760, 1.15, "walk"), (16.65, 806, 740, 1.22, "walk", 0.2, "slide"),
    (hk(17.35), 758, 640, 0.95, "walk"), (18.75, 720, 880, 0.95, "fall", 0.5, "slide"),
    (19.20, 700, 1238, 1.05, "sit", 0.35, "slide"),
    (hk(21.75) - 0.15, 600, 1245, 1.05, "sit", 0.45, "slide"),
    (hk(24.00), 586, 1245, 1.05, "sit", 0.4, "slide"),
], [(0, "hidden"), (16.47, "outR"), (17.75, "front"), (18.85, "in")])
B["b6"] = Bear("b6", BROWN[4], [
    (0.0, 262, 650, 1.0, "stand"), (27.30, 262, 650, 1.0, "stand"), (27.75, 262, 652, 1.0, "stand"),
    (hk(28.55), 268, 676, 1.55, "walk"),
    (30.70, 262, 676, 1.55, "back", 0.35, "slide"), (31.30, 244, 640, 1.45, "back", 0.45, "hop"),
    (32.15, 236, 618, 1.40, "back", 0.45, "hop"),
    (32.95, 240, 622, 1.42, "walk", 0.25, "slide"), (hk(32.75) + 0.3, 270, 700, 1.52, "walk"),
    (hk(33.70), 304, 790, 1.56, "walk"), (hk(35.25), 420, 980, 1.56, "walk"),
    (36.20, 505, 1140, 1.3, "sit", 0.5, "slide"), (36.45, 505, 1186, 1.36, "sit", 0.25, "slide"),
], [(0, "hidden"), (27.32, "outL"), (35.85, "enterC"), (36.5, "in")])
B["b7"] = Bear("b7", BROWN[6], [
    (0.0, 792, 640, 1.18, "walk"), (37.40, 792, 640, 1.18, "walk"), (37.60, 790, 650, 1.2, "walk", 0.2, "slide"),
    (hk(39.00), 790, 770, 1.26, "walk"),
    (40.30, 800, 1200, 1.0, "back", 0.30, "slide"), (hk(39.95) + 0.05, 800, 1205, 1.0, "back", 0.1, "slide"),
    (41.40, 690, 1262, 1.05, "back", 0.40, "hop"),
    (53.95, 668, 1060, 0.78, "sit", 0.20, "slide"), (54.15, 668, 1118, 0.76, "sit", 0.20, "slide"),
], [(0, "hidden"), (37.42, "outR"), (40.05, "front"), (53.80, "in")])
BEARS = B


# ------------------------------------------------------------------ dessins
MOON = (238, 236, 220)
SKY_TOP, SKY_LOW = (10, 14, 34), (34, 44, 82)
PINE_FAR, PINE_NEAR = (14, 26, 26), (10, 20, 20)
FAB, FAB_LIT = (176, 98, 40), (250, 160, 66)
FAB_SEAM, FAB_SEAM_LIT = (140, 74, 30), (214, 124, 44)
WALL, WALL_LIT = (88, 70, 64), (250, 214, 150)
FLOORC, FLOOR_LIT = (64, 72, 92), (150, 116, 80)
COOL_B, COOL_L = (44, 110, 200), (226, 230, 238)
BAG_C_, BAG_D = (52, 134, 82), (34, 96, 58)
GROUND0, GROUND1 = (34, 30, 30), (18, 16, 18)
RING = (255, 255, 255)

FAR_TREES = [(130 + 74 * k + (17 * k) % 23, 690 - (k * 37) % 40, 110 + (k * 53) % 70, 70 + (k * 29) % 30)
             for k in range(12)]


def make_background(S):
    img = Image.new("RGB", (W * S, H * S), SKY_TOP)
    dr = ImageDraw.Draw(img)
    for k in range(0, 1260, 6):
        dr.rectangle([0, k * S, W * S, (k + 6) * S], fill=mix(SKY_TOP, SKY_LOW, (k / 1260) ** 1.2))
    mx, my = 760, 470
    a = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:H * S, 0:W * S]
    d = np.hypot(xx / S - mx, yy / S - my)
    g = np.exp(-np.maximum(d - 40, 0) / 170.0)[..., None] * 0.55
    a = a * (1 - g) + np.array([90, 104, 146], np.float32) * g
    img = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    ell(dr, mx, my, 44, 44, MOON, S)
    for (cx, cy, rr) in ((748, 460, 8), (772, 482, 6)):
        ell(dr, cx, cy, rr, rr, (218, 216, 200), S)
    # le sol : terre battue au clair de lune, plus claire au premier plan
    for k in range(1180, H, 6):
        dr.rectangle([0, k * S, W * S, (k + 6) * S], fill=mix((40, 40, 50), (58, 54, 60), (k - 1180) / (H - 1180)))
    rng = np.random.default_rng(5)
    for _ in range(140):                       # cailloux
        x = rng.uniform(20, W - 20); y = rng.uniform(1290, 1880)
        r = rng.uniform(4, 11) * (0.6 + (y - 1290) / 900)
        ell(dr, x, y, r * 1.5, r, (74, 72, 80), S)
    for _ in range(70):                        # touffes d'herbe
        x = rng.uniform(20, W - 20); y = rng.uniform(1300, 1880)
        h = rng.uniform(16, 34) * (0.7 + (y - 1300) / 800)
        for dd in (-8, 0, 8):
            dr.line([P(x, y, S), P(x + dd, y - h, S)], fill=(52, 70, 52), width=int(3 * S))
    # cercle de pierres et bûches (éteint)
    for k in range(10):
        ang = 2 * math.pi * k / 10
        ell(dr, 540 + 150 * math.cos(ang), 1560 + 52 * math.sin(ang), 32, 20, (92, 90, 96), S)
    for (x0, y0, x1, y1) in ((440, 1575, 640, 1540), (465, 1540, 625, 1580), (520, 1530, 560, 1592)):
        dr.line([P(x0, y0, S), P(x1, y1, S)], fill=(104, 72, 48), width=int(24 * S))
    # un sac à dos et des bottes
    dr.rounded_rectangle([760 * S, 1330 * S, 870 * S, 1470 * S], radius=26 * S, fill=(150, 60, 50))
    dr.rounded_rectangle([775 * S, 1395 * S, 855 * S, 1450 * S], radius=12 * S, fill=(120, 46, 40))
    dr.rounded_rectangle([780 * S, 1310 * S, 850 * S, 1340 * S], radius=12 * S, fill=(120, 46, 40))
    for bx in (170, 228):
        dr.rounded_rectangle([bx * S, 1420 * S, (bx + 44) * S, 1500 * S], radius=10 * S, fill=(92, 70, 56))
        dr.rounded_rectangle([bx * S, 1476 * S, (bx + 72) * S, 1506 * S], radius=10 * S, fill=(92, 70, 56))
    # une bûche couchée au premier plan
    dr.rounded_rectangle([250 * S, 1720 * S, 830 * S, 1790 * S], radius=34 * S, fill=(96, 66, 44))
    ell(dr, 810, 1755, 30, 34, (150, 112, 76), S)
    return img


def draw_tree(dr, x, base, h, w, col, S, lean=0.0):
    for k in range(4):
        yy = base - h * k / 4.2
        ww = w * (1 - k / 5)
        top = (x + lean * (h * (k + 1) / 4.2), yy - h / 2.0)
        dr.polygon([P(x - ww / 2 + lean * h * k / 4.2, yy, S), P(x + ww / 2 + lean * h * k / 4.2, yy, S),
                    P(top[0], top[1], S)], fill=col)


def tree_lean(t, x):
    tw = warp(t)
    lean = 0.0
    for (t0, amp, x0) in ((43.55, 0.10, 0), (44.90, 0.16, 0), (47.0, 0.22, 0)):
        if tw > t0:
            u = tw - t0
            lean += amp * math.exp(-u * 1.6) * math.sin(u * 7.0 + x * 0.01)
    return lean


def bear_prims(st, col, t, ear=0.0, swing=0.0, perk=0.0):
    """Liste (forme, x, y, rx, ry, couleur) d'un ours vu de face, sans visage."""
    x, y, s, mode = st["x"], st["y"], st["s"], st["mode"]
    pr = []
    if mode in ("walk", "fall", "dive"):
        hx = x + swing * 14 * s
        pr += [("e", x - 58 * s, y - 16 * s, 19 * s, 20 * s, "d"), ("e", x + 58 * s, y - 16 * s, 19 * s, 20 * s, "d"),
               ("e", x - 30 * s, y - 12 * s, 20 * s, 18 * s, "c"), ("e", x + 30 * s, y - 12 * s, 20 * s, 18 * s, "c"),
               ("e", x, y - 64 * s, 94 * s, 52 * s, "d"),
               ("e", hx - 42 * s, y - 120 * s - perk * 10 * s, 21 * s, 21 * s, "c"),
               ("e", hx + 42 * s, y - 120 * s - perk * 10 * s, 21 * s, 21 * s, "c"),
               ("e", hx, y - 78 * s, 56 * s, 52 * s, "c"),
               ("e", hx, y - 58 * s, 26 * s, 18 * s, "m")]
    elif mode == "back":
        pr += [("e", x - 46 * s, y - 20 * s, 20 * s, 22 * s, "c"), ("e", x + 46 * s, y - 20 * s, 20 * s, 22 * s, "c"),
               ("e", x, y - 68 * s, 92 * s, 56 * s, "c"),
               ("e", x - 34 * s, y - 118 * s, 16 * s, 16 * s, "c"), ("e", x + 34 * s, y - 118 * s, 16 * s, 16 * s, "c"),
               ("e", x, y - 92 * s, 44 * s, 38 * s, "c"), ("e", x, y - 38 * s, 12 * s, 10 * s, "m")]
    elif mode == "stand":
        hx = x + swing * 12 * s
        pr += [("e", x - 30 * s, y - 24 * s, 22 * s, 26 * s, "c"), ("e", x + 30 * s, y - 24 * s, 22 * s, 26 * s, "c"),
               ("e", x, y - 100 * s, 62 * s, 88 * s, "c"),
               ("e", x - 62 * s, y - 150 * s, 18 * s, 40 * s, "c"), ("e", x + 62 * s, y - 150 * s, 18 * s, 40 * s, "c"),
               ("e", hx - 33 * s, y - 238 * s - perk * 8 * s, 16 * s, 16 * s, "c"),
               ("e", hx + 33 * s, y - 238 * s - perk * 8 * s, 16 * s, 16 * s, "c"),
               ("e", hx, y - 206 * s, 46 * s, 42 * s, "c"), ("e", hx, y - 190 * s, 21 * s, 14 * s, "m"),
               ("e", x, y - 92 * s, 36 * s, 50 * s, "m2")]
    elif mode in ("sit", "stuck"):
        hx = x + swing * 10 * s
        pr += [("e", x, y - 72 * s, 80 * s, 74 * s, "c"),
               ("e", x - 44 * s, y - 14 * s, 26 * s, 16 * s, "c"), ("e", x + 44 * s, y - 14 * s, 26 * s, 16 * s, "c"),
               ("e", x, y - 64 * s, 44 * s, 46 * s, "m2"),
               ("e", hx - 36 * s, y - 190 * s - perk * 8 * s, 17 * s, 17 * s, "c"),
               ("e", hx + 36 * s, y - 190 * s - perk * 8 * s, 17 * s, 17 * s, "c"),
               ("e", hx, y - 152 * s, 52 * s, 50 * s, "c"), ("e", hx, y - 134 * s, 24 * s, 16 * s, "m")]
    elif mode == "lie":
        hx = x + swing * 10 * s
        pr += [("e", x, y - 52 * s, 104 * s, 50 * s, "c"),
               ("e", hx - 32 * s, y - 98 * s - perk * 6 * s, 15 * s, 15 * s, "c"),
               ("e", hx + 32 * s, y - 98 * s - perk * 6 * s, 15 * s, 15 * s, "c"),
               ("e", hx, y - 62 * s, 46 * s, 42 * s, "c"), ("e", hx, y - 46 * s, 22 * s, 15 * s, "m")]
    return pr


def draw_prims(dr, pr, col, S, lit=0.0, rim=True, ox=0.0, oy=0.0, dark=1.0):
    c = mix(tuple(int(v * dark) for v in col), (226, 164, 110), lit * 0.12)
    m = mix(tuple(int(v * dark) for v in MUZ), (246, 206, 150), lit * 0.2)
    m2 = mix(c, m, 0.45)
    cd = tuple(int(v * 0.78) for v in c)
    if rim:
        rc = mix(RIM, (255, 214, 150), lit)
        for (_, x, y, rx, ry, k) in pr:
            if k in ("c", "d"):
                ell(dr, x - ox, y - oy - 4, rx + 1.5, ry + 1.5, rc, S)
    for (_, x, y, rx, ry, k) in pr:
        if k == "d":
            ell(dr, x - ox, y - oy, rx, ry, cd, S)
    for (_, x, y, rx, ry, k) in pr:
        if k == "c":
            ell(dr, x - ox, y - oy, rx, ry, c, S)
    for (_, x, y, rx, ry, k) in pr:
        if k == "m2":
            ell(dr, x - ox, y - oy, rx, ry, m2, S)
        elif k == "m":
            ell(dr, x - ox, y - oy, rx, ry, m, S)


def freeze_swing(name, t):
    """Tête qui balance quand le bruit s'arrête (ours dehors seulement)."""
    tw = warp(t)
    FZ = {"b1": [(2.30, 2.95)], "b2": [(6.80, 7.25), (9.40, 9.85)], "b6": [(29.25, 30.6)],
          "b4": [(18.05, 18.6)], "b5": [(18.05, 18.6)]}
    for (a, b) in FZ.get(name, []):
        if a <= tw <= b:
            return math.sin((tw - a) * 9.0) * min(1.0, (tw - a) * 4, (b - tw) * 4)
    return 0.0


class Sim:
    scene_top = 0.20

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hi = 0
        self.hits = BALL.hits
        self.bg = None
        self.t_end = BALL.t_end
        self.t_payoff = T_PAYOFF

    def step(self, dt):
        evs = []
        self.t += dt
        # le mot part à la première image où le contact est atteint (jamais avant)
        while self.hi < len(self.hits) and self.hits[self.hi] <= self.t - dt + 1e-6:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and self.t >= self.t_payoff:
            self.payoff = True
            evs.append(("payoff", "rock"))
        if self.t >= self.t_end:
            self.done = True
        return evs

    def hero_mood(self):
        return "win"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # --------------------------------------------------------------
    def lit(self, t):
        return ramp(warp(t), 32.78, 32.95)

    def draw(self, dr, snap, t, S):
        img = dr._image
        if self.bg is None or self.bg.size != img.size:
            self.bg = make_background(S)
        img.paste(self.bg)
        dr = ImageDraw.Draw(img)
        dra = ImageDraw.Draw(img, "RGBA")
        tw = warp(t)
        lit = self.lit(t)
        sh = dome_shape(t)
        bx, by = BALL.pos(t)
        perk_t = [h for h in BALL.hits if h <= t]
        last_hit = perk_t[-1] if perk_t else -9
        perk = pulse(t, last_hit + 0.12, 0.08, 0.35)

        # --- sapins lointains (oscillent quand elle approche), puis l'ourse géante devant eux
        for (x, base_y, h, w) in FAR_TREES:
            if 300 < x < 720:
                continue
            draw_tree(dr, x, base_y, h, w, PINE_FAR, S, tree_lean(t, x))
        # grand sapin de gauche et sa branche au-dessus de la tente
        dr.rectangle([132 * S, 360 * S, 160 * S, 1180 * S], fill=(26, 20, 18))
        dr.line([P(146, 430, S), P(300, 410, S), P(450, 432, S)], fill=(30, 24, 20), width=int(16 * S), joint="curve")
        for (x0, y0) in ((210, 412), (300, 400), (390, 420), (448, 434)):
            dr.polygon([P(x0 - 40, y0 + 6, S), P(x0 + 40, y0 + 6, S), P(x0, y0 - 30, S)], fill=PINE_NEAR)
        for k in range(5):
            yy = 560 + k * 150
            ww = 120 - k * 6
            dr.polygon([P(146 - ww, yy + 80, S), P(146 + ww * 0.55, yy + 80, S), P(146, yy - 70, S)], fill=PINE_NEAR)
        # --- l'ourse géante (devant les sapins, derrière la tente)
        self.draw_giant(dr, t, S, behind=True)

        # --- les ours dehors, derrière la tente
        for nm in ("b1", "b2", "b4", "b5", "b6", "b7"):
            bear = BEARS[nm]
            lay = bear.layer(t)
            if lay in ("out", "outL", "outR"):
                st = bear.state(t)
                draw_prims(dr, bear_prims(st, bear.col, t, swing=freeze_swing(nm, t), perk=perk), bear.col, S)
        cub = BEARS["cub"]
        if cub.layer(t) == "branch":
            st = cub.state(t)
            draw_prims(dr, bear_prims(st, cub.col, t, perk=perk), cub.col, S)

        # --- la tente
        a, b, lift, wob = sh
        n = 64
        outer = []
        for k in range(n + 1):
            u = math.pi * k / n
            x = DCX - a * math.cos(u)
            y = BASE - lift - b * math.sin(u) + wob * math.sin(u) * math.sin(3 * u)
            # creux du toit (ourson, ours qui grimpent)
            y += self.roof_dent(x, t)
            outer.append((x, y))
        fab = mix(FAB, FAB_LIT, lit)
        seam = mix(FAB_SEAM, FAB_SEAM_LIT, lit)
        dr.polygon([P(x, y, S) for x, y in outer] + [P(DCX + a, BASE + 6, S), P(DCX - a, BASE + 6, S)], fill=fab)
        # arceaux
        for sgn in (-1, 1):
            pts = []
            for k in range(25):
                u = k / 24
                xx = DCX + sgn * a * (1 - u) * 0.98
                yy = dome_y(xx, t, sh) + 10
                pts.append(P(xx + sgn * 0, yy, S))
            dr.line(pts, fill=seam, width=int(7 * S), joint="curve")
        # sardines et haubans
        for (sx, side) in ((DCX - a - 26, -1), (DCX + a + 26, 1)):
            py = BASE + 22
            pop = ramp(tw, 35.95, 36.25)
            fly = pulse(tw, 36.3, 0.3, 0.5)
            dx = side * 40 * pop
            dy = -90 * fly
            dr.line([P(DCX + side * (a - 30), dome_y(DCX + side * (a - 30), t, sh) + 40, S),
                     P(sx + dx, py + dy - 6, S)], fill=(150, 150, 140), width=int(3 * S))
            dr.polygon([P(sx + dx - 6, py + dy - 10, S), P(sx + dx + 6, py + dy - 10, S), P(sx + dx, py + dy + 20 - 14 * pop, S)],
                       fill=(190, 190, 196))

        # --- l'intérieur, vu par la porte
        self.draw_inside(img, t, S, lit, perk)
        # bords roulés de la porte
        da = door_a(t)
        flap = mix((150, 80, 32), (236, 140, 56), lit)
        for sgn in (-1, 1):
            pts = []
            for k in range(30):
                u = k / 29
                xx = DCX + sgn * da * math.cos(u * math.pi / 2 * 0.92)
                pts.append(P(xx, door_y(xx, t, da) - 4, S))
            dr.line(pts, fill=flap, width=int(16 * S), joint="curve")
        # l'aération
        vx_, vy_ = vent_pos(t)
        open_r = 38.0 + 90.0 * self.vent_open(t)
        dr.ellipse([(vx_ - open_r) * S, (vy_ - 24 - open_r * 0.15) * S, (vx_ + open_r) * S, (vy_ + 24 + open_r * 0.15) * S],
                   fill=mix((54, 34, 26), (120, 70, 36), lit))
        dr.ellipse([(vx_ - open_r - 6) * S, (vy_ - 30 - open_r * 0.15) * S, (vx_ + open_r + 6) * S, (vy_ + 30 + open_r * 0.15) * S],
                   outline=seam, width=int(6 * S))
        if tw > 58.62:      # une oreille d'ours bouche le trou derrière lui
            k = ramp(tw, 58.62, 58.75)
            ell(dr, vx_, vy_ + 6 - 20 * k, 22 * k + 1, 22 * k + 1, BROWN[1], S)
        # l'ourson sur le toit, puis la tête dans l'aération
        lay = cub.layer(t)
        if lay in ("roof", "vent"):
            st = cub.state(t)
            if lay == "vent":
                st = dict(st, mode="back")
            draw_prims(dr, bear_prims(st, cub.col, t, perk=perk), cub.col, S, lit=lit)
        # ours 4 et 5 qui glissent sur le devant du dôme
        for nm in ("b4", "b5", "b7"):
            bear = BEARS[nm]
            if bear.layer(t) == "front":
                st = dict(bear.state(t))
                if nm == "b7" and 41.4 <= tw < 53.8:      # coincé dans la porte : il gigote
                    st["x"] += 9 * math.sin(tw * 15)
                draw_prims(dr, bear_prims(st, bear.col, t, perk=perk), bear.col, S, lit=lit)
        # pattes de la géante sur le dos du dôme, et sa bosse
        self.draw_giant(dr, t, S, behind=False)

        # --- le sol éclairé par la porte, les ombres des ours
        self.draw_ground(dr, img, t, S, lit)
        # --- le rocher (c'est un ours)
        self.draw_rock(dr, t, S, lit)

        # --- l'anneau du dernier contact dur
        for h in BALL.hits:
            if h <= t < h + 0.32:
                u = (t - h) / 0.32
                hx, hy = BALL.pos(h)
                rr = R + 40 + 640 * u
                al = int(230 * (1 - u))
                dra.ellipse([(hx - rr) * S, (hy - rr) * S, (hx + rr) * S, (hy + rr) * S],
                            outline=(255, 255, 255, al), width=int(max(2, 10 * (1 - u)) * S))

        # --- Bounce
        base.HERO["expr"] = self.expr(t)
        base.ball(dr, bx * S, by * S, R * S)

    def expr(self, t):
        if t >= T_YES:
            return "win"
        if 46.95 <= t < 48.20 or 56.20 <= t < 59.80:
            return "shock"
        return "calm"

    def vent_open(self, t):
        # l'ourson qui passe (14,95-15,15), puis Bounce (57,8-58,6)
        tw = warp(t)
        v = pulse(tw, 15.08, 0.12, 0.12) * 0.25
        if 57.85 <= t:
            v = max(v, pulse(t, 58.30, 0.40, 0.18))
        return v

    def roof_dent(self, x, t):
        tw = warp(t)
        d = 0.0
        # l'ourson tombe sur le toit
        k = pulse(tw, 13.95, 0.12, 0.5)
        if k:
            d += 26 * k * math.exp(-((x - 400) / 60) ** 2)
        # les deux ours grimpent sur les épaules
        k = ramp(tw, 17.55, 17.8) * (1 - ramp(tw, 18.55, 18.85))
        if k:
            d += 22 * k * (math.exp(-((x - 270) / 60) ** 2) + math.exp(-((x - 750) / 60) ** 2))
        # la tête de l'ours 1 qui disparaît derrière
        return d

    def draw_giant(self, dr, t, S, behind):
        tw = warp(t)
        if tw < 46.9:
            return
        rise = ramp(tw, 46.97, 47.35)
        # échelle et descente à chaque pas
        k = Keys([(46.9, 0.92), (48.9, 0.92), (49.3, 0.97), (50.25, 0.97), (50.65, 1.0)])(tw)
        base_y = Keys([(46.9, 640.0), (48.9, 640.0), (49.3, 615.0), (50.25, 615.0), (50.65, 594.0)])(tw)
        head_dn = ramp(tw, 52.35, 52.9) * 190 + ramp(tw, 53.78, 54.0) * 30
        cy = base_y + (1 - rise) * 420
        col = (146, 100, 64)
        if behind:
            # épaules et tête au-dessus des arbres (le dôme la cache en bas)
            pr = [("e", DCX, cy + 120 * k, 374 * k, 270 * k, "d"),
                  ("e", DCX - 138 * k, cy - 248 * k + head_dn, 50 * k, 50 * k, "c"),
                  ("e", DCX + 138 * k, cy - 248 * k + head_dn, 50 * k, 50 * k, "c"),
                  ("e", DCX, cy - 150 * k + head_dn, 172 * k, 140 * k, "c"),
                  ("e", DCX, cy - 92 * k + head_dn, 70 * k, 46 * k, "m")]
            # la tête ne monte jamais au-dessus de y 265
            top = cy - 248 * k - 50 * k + head_dn
            if top < 265:
                dy = 265 - top
                pr = [(a, x, y + dy, rx, ry, c) for (a, x, y, rx, ry, c) in pr]
            # elle reste derrière la lisière : rien d'elle sous y 860
            img = dr._image
            crop = img.crop((0, 0, W * S, 860 * S))
            draw_prims(ImageDraw.Draw(crop), pr, col, S)
            img.paste(crop, (0, 0))
        else:
            paws = ramp(tw, 50.3, 50.6)
            if paws > 0:
                sh = dome_shape(t)
                for sgn in (-1, 1):
                    px = DCX + sgn * 250
                    py = dome_y(px, t, sh) - 6 + 40 * (1 - paws)
                    for j in (-1, 0, 1):
                        ell(dr, px + j * 22, py + 6, 18, 22, col, S)
                    ell(dr, px, py + 26, 50, 30, col, S)

    def draw_rock(self, dr, t, S, lit):
        x, y, rx, ry = ROCK
        dent = 0.0
        hdent = 0.0
        for (tc, s_, xc) in SOFT_CONTACTS:
            if s_ == "rock":
                dent += 18 * pulse(t, tc, 0.06, 0.16)
            elif s_ == "rhead":
                hdent += 16 * pulse(t, tc, 0.06, 0.16)
        head = ramp(t, 59.95, 60.40) * (1 - ramp(t, 62.50, 63.00))
        col = mix(ROCK_GREY, (128, 100, 74), head)
        hi = mix((140, 132, 124), (170, 132, 96), head)
        # le rocher : gris-brun, deux petites bosses (les oreilles du dos)
        ell(dr, x - 52, y - ry + 12 + dent * 0.4, 20, 17, hi, S)
        ell(dr, x + 40, y - ry + 14 + dent * 0.4, 19, 16, hi, S)
        ell(dr, x, y + dent * 0.3, rx, ry - dent * 0.5, col, S)
        ell(dr, x - 40, y - 34 + dent * 0.3, 54, 22, mix(col, (160, 152, 142), 0.35), S)
        # la tête sort de l'avant du rocher : brun franc, deux oreilles rondes, museau clair
        if head > 0:
            hx = RHEAD_X
            hy = y + 10 - (y + 10 - HEAD_UP_Y) * head + hdent
            hc = (160, 106, 66)
            r = HEAD_R * (0.6 + 0.4 * head)
            for sgn in (-1, 1):
                ell(dr, hx + sgn * 0.64 * r, hy - 0.76 * r, 0.31 * r, 0.31 * r, RIM, S)
                ell(dr, hx + sgn * 0.64 * r, hy - 0.72 * r, 0.29 * r, 0.29 * r, hc, S)
            ell(dr, hx, hy - 5, r + 2, r * 0.92 + 2, RIM, S)
            ell(dr, hx, hy, r, r * 0.92, hc, S)
            ell(dr, hx, hy + 0.3 * r, 0.44 * r, 0.3 * r, MUZ, S)

    def draw_ground(self, dr, img, t, S, lit):
        """Le bas de l'image (décor) : la lumière de la porte sur la terre, et l'ombre de chaque ours."""
        if lit <= 0:
            return
        dra = ImageDraw.Draw(img, "RGBA")
        da = door_a(t)
        top = BASE + 4
        for k in range(10):
            u = k / 10
            y0, y1 = top + 520 * u, top + 520 * (u + 0.1)
            w0, w1 = da + 330 * u, da + 330 * (u + 0.1)
            dra.polygon([P(DCX - w0, y0, S), P(DCX + w0, y0, S), P(DCX + w1, y1, S), P(DCX - w1, y1, S)],
                        fill=(255, 176, 90, int(70 * lit * (1 - u) ** 1.2)))
        # une ombre par ours dans la tente (on peut les compter)
        tw = warp(t)
        for nm in ("b1", "cub", "b2", "b4", "b5", "b6", "b7"):
            bear = BEARS[nm]
            if bear.layer(t) != "in":
                continue
            st = bear.state(t)
            sx = DCX + (st["x"] - DCX) * 1.9
            sc = st["s"]
            L = 230 * sc
            dra.ellipse([(sx - 46 * sc) * S, (top + 30) * S, (sx + 46 * sc) * S, (top + 30 + L) * S], fill=(20, 12, 10, int(80 * lit)))
            for sgn in (-1, 1):
                dra.ellipse([(sx + sgn * 30 * sc - 14 * sc) * S, (top + 30 + L - 10 * sc) * S,
                             (sx + sgn * 30 * sc + 14 * sc) * S, (top + 30 + L + 18 * sc) * S], fill=(20, 12, 10, int(80 * lit)))
        if tw >= 56.0:
            k = ramp(tw, 56.0, 56.5)
            dra.ellipse([(DCX - 130) * S, (top + 20) * S, (DCX + 130) * S, (top + 20 + 360 * k) * S], fill=(20, 12, 10, int(110 * lit)))

    def draw_inside(self, img, t, S, lit, perk):
        """Tout ce qui se voit par la porte, dessiné sur un calque découpé à la forme de la porte."""
        tw = warp(t)
        da = door_a(t)
        x0, y0 = DCX - da - 4, BASE - DOB - 4
        x1, y1 = DCX + da + 4, BASE + 4
        w, h = int((x1 - x0) * S), int((y1 - y0) * S)
        lay = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(lay)
        ox, oy = x0, y0

        def E(x, y, rx, ry, c):
            d.ellipse([(x - rx - ox) * S, (y - ry - oy) * S, (x + rx - ox) * S, (y + ry - oy) * S], fill=c)

        wall = mix(WALL, WALL_LIT, lit)
        d.rectangle([0, 0, w, h], fill=wall)
        # une lueur de lune sur la toile du fond (pour compter avant la lanterne)
        for k in range(14):
            E(DCX, 930, 240 - 13 * k, 230 - 13 * k, mix(wall, (120, 102, 96) if lit < 0.5 else (252, 214, 150), 0.05 * k))
        # le tapis
        floor = mix(FLOORC, FLOOR_LIT, lit)
        d.polygon([((260 - ox) * S, (FLOOR_BACK - oy) * S), ((760 - ox) * S, (FLOOR_BACK - oy) * S),
                   ((790 - ox) * S, (FLOOR_FRONT + 10 - oy) * S), ((230 - ox) * S, (FLOOR_FRONT + 10 - oy) * S)], fill=floor)
        # les entrées par la toile du fond : le bas de la toile se soulève
        for (nm, xe, t0, t1, wdt) in (("b1", 330, 4.70, 5.65, 120), ("b2", 690, 10.20, 11.0, 130),
                                      ("b6", 505, 35.80, 36.55, 190),
                                      ("giant", 510, 55.95, 99, 200)):
            if t0 <= tw <= t1 + 0.3:
                k = min(ramp(tw, t0, t0 + 0.2), 1 - ramp(tw, t1, t1 + 0.3)) if nm != "giant" else ramp(tw, t0, t0 + 0.25)
                hgt = (215 if nm == "b7" else 110) * k
                pts = [((xe - wdt - ox) * S, (FLOOR_BACK - oy) * S)]
                for j in range(13):
                    u = j / 12
                    pts.append(((xe - wdt + 2 * wdt * u - ox) * S, (FLOOR_BACK - hgt * math.sin(math.pi * u) - oy) * S))
                pts.append(((xe + wdt - ox) * S, (FLOOR_BACK - oy) * S))
                d.polygon(pts, fill=mix((26, 22, 26), (90, 60, 40), lit))
        # les ours qui entrent par le fond (cachés au-dessus de l'ourlet soulevé)
        entering = []
        for nm in ("b1", "b2", "b6"):
            bear = BEARS[nm]
            lay_ = bear.layer(t)
            if lay_ in ("enterL", "enterR", "enterC", "stuck"):
                entering.append(nm)
        for nm in entering:
            bear = BEARS[nm]
            st = bear.state(t)
            if st["mode"] == "walk":
                st = dict(st, mode="sit")
            if bear.layer(t) == "stuck":
                st = dict(st, mode="sit", s=0.82)
                wig = math.sin(tw * 14) * 6 * (1 - ramp(tw, 53.8, 54.0))
                st["x"] += wig
            pr = bear_prims(st, bear.col, t, perk=perk)
            draw_prims(d, pr, bear.col, S, lit=lit, ox=ox, oy=oy)
        if entering:
            # la toile du fond repasse devant ce qui est encore dehors
            for nm in entering:
                xe = {"b1": 330, "b2": 690, "b6": 505, "b7": 715}[nm]
                wdt = {"b1": 120, "b2": 130, "b6": 190, "b7": 112}[nm]
                t0 = {"b1": 4.70, "b2": 10.20, "b6": 35.80, "b7": 41.0}[nm]
                t1 = {"b1": 5.65, "b2": 11.0, "b6": 36.55, "b7": 54.2}[nm]
                k = min(ramp(tw, t0, t0 + 0.2), 1 - ramp(tw, t1, t1 + 0.3))
                hgt = (215 if nm == "b7" else 110) * k
                pts = [((xe - wdt - 30 - ox) * S, -10)]
                pts.append(((xe - wdt - 30 - ox) * S, (FLOOR_BACK - oy) * S))
                for j in range(13):
                    u = j / 12
                    pts.append(((xe - wdt + 2 * wdt * u - ox) * S, (FLOOR_BACK - hgt * math.sin(math.pi * u) - oy) * S))
                pts.append(((xe + wdt + 30 - ox) * S, (FLOOR_BACK - oy) * S))
                pts.append(((xe + wdt + 30 - ox) * S, -10))
                d.polygon(pts, fill=wall)
        # la tête de la géante entre par le fond
        if tw >= 55.95:
            k = ramp(tw, 56.0, 56.5)
            hy = FLOOR_BACK + 80 - 230 * k
            hc = (124, 84, 54)
            pr = [("e", DCX - 92, hy - 104, 34, 34, "c"), ("e", DCX + 92, hy - 104, 34, 34, "c"),
                  ("e", DCX, hy - 10, 132, 116, "c"), ("e", DCX, hy + 30, 56, 38, "m")]
            draw_prims(d, pr, hc, S, lit=lit, ox=ox, oy=oy)
            # repasser la toile du fond devant ce qui n'est pas encore entré
            pts = [((DCX - 260 - ox) * S, (FLOOR_BACK + 200 - oy) * S), ((DCX - 260 - ox) * S, (FLOOR_BACK + 4 - oy) * S),
                   ((DCX + 260 - ox) * S, (FLOOR_BACK + 4 - oy) * S), ((DCX + 260 - ox) * S, (FLOOR_BACK + 200 - oy) * S)]
            if k < 1:
                d.polygon(pts, fill=floor)
        # ours assis : du fond vers l'avant
        order = ["b6", "b1", "cub", "b2", "b7", "b4", "b5"]
        shift = BEAR_SHIFT(t)
        for nm in order:
            bear = BEARS[nm]
            if bear.layer(t) != "in":
                if nm == "cub" and bear.layer(t) == "in":
                    pass
                if nm == "b2":
                    pass
                continue
            st = bear.state(t)
            st = dict(st)
            if st["mode"] in ("sit", "lie"):
                st["y"] += shift
            # chaque ours bouge un peu tout seul : il reste vivant
            st["x"] += 3 * math.sin(tw * 1.3 + hash(nm) % 7)
            dent = 0.0
            for (tc, s_, xc) in SOFT_CONTACTS:
                if s_ == nm:
                    dent += 14 * pulse(t, tc, 0.06, 0.18)
            pr = bear_prims(st, bear.col, t, perk=perk * 0.6, swing=self.inside_swing(nm, t))
            if dent:
                pr = [(a, x, y + dent * 0.6, rx, ry * (1 - dent / 220), c) for (a, x, y, rx, ry, c) in pr]
            if nm == "b2" or nm == "b7":
                pass
            draw_prims(d, pr, bear.col, S, lit=lit, ox=ox, oy=oy)
            if nm == "b1":
                self.draw_cooler(d, t, S, lit, ox, oy)
            if nm == "cub":
                pass
            if nm == "b6" and False:
                pass
            if nm == "b1" and BEARS["b2"].layer(t) != "in":
                self.draw_bag(d, t, S, lit, ox, oy)
        if BEARS["b1"].layer(t) != "in":
            self.draw_cooler(d, t, S, lit, ox, oy)
            self.draw_bag(d, t, S, lit, ox, oy)
        elif BEARS["b2"].layer(t) == "in":
            pass
        # la lanterne
        lx, ly, ang = lantern_pos(t)
        ax, ay = LANT_X, door_y(LANT_X, t) + 14
        d.line([((ax - ox) * S, (ay - 30 - oy) * S), ((lx - ox) * S, (ly - LANT_H - oy) * S)], fill=(40, 40, 44), width=int(4 * S))
        glass = mix((96, 90, 60), (255, 236, 150), lit)
        cx, cy = lx, ly - LANT_H / 2
        d.rounded_rectangle([(cx - 34 - ox) * S, (cy - LANT_H / 2 - oy) * S, (cx + 34 - ox) * S, (cy + LANT_H / 2 - oy) * S],
                            radius=12 * S, fill=(70, 72, 80))
        d.rounded_rectangle([(cx - 24 - ox) * S, (cy - LANT_H / 2 + 14 - oy) * S, (cx + 24 - ox) * S, (cy + LANT_H / 2 - 10 - oy) * S],
                            radius=6 * S, fill=glass)
        # le masque de la porte
        m = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(m)
        pts = []
        for k in range(49):
            u = math.pi * k / 48
            xx = DCX - da * math.cos(u)
            pts.append(((xx - ox) * S, (BASE - DOB * math.sin(u) - oy) * S))
        md.polygon(pts, fill=255)
        img.paste(lay, (int(ox * S), int(oy * S)), m)

    def inside_swing(self, nm, t):
        tw = warp(t)
        # l'ours 1 suit Bounce de la tête ; tous tournent la tête vers le fond à 44,9
        if nm == "b1" and 7.4 < tw < 15.0:
            bxp, _ = BALL.pos(t)
            return clamp01((bxp - 300) / 400) * 2 - 1
        if 44.95 < tw < 46.9:
            return -0.0
        return 0.0

    def draw_cooler(self, d, t, S, lit, ox, oy):
        x0, y0, x1, y1 = COOLER
        dent = 0.0
        body = mix(COOL_B, (110, 150, 220), lit * 0.5)
        lid = mix(COOL_L, (255, 240, 220), lit * 0.5)
        d.rounded_rectangle([(x0 - ox) * S, (y0 + 16 - oy) * S, (x1 - ox) * S, (y1 - oy) * S], radius=12 * S, fill=body)
        d.rounded_rectangle([(x0 - 6 - ox) * S, (y0 - oy) * S, (x1 + 6 - ox) * S, (y0 + 24 - oy) * S], radius=8 * S, fill=lid)
        d.rectangle([(x0 + 50 - ox) * S, (y0 + 60 - oy) * S, (x1 - 50 - ox) * S, (y0 + 72 - oy) * S], fill=dim(body, 0.7))

    def draw_bag(self, d, t, S, lit, ox, oy):
        x0, y0, x1, y1 = BAG
        dent = 0.0
        xc = (x0 + x1) / 2
        for (tc, s_, xx) in SOFT_CONTACTS:
            if s_ == "bag":
                k = pulse(t, tc, 0.07, 0.2)
                if k:
                    dent = max(dent, 30 * k)
                    xc = xx
        c = mix(BAG_C_, (110, 170, 100), lit * 0.4)
        cd = mix(BAG_D, (80, 130, 76), lit * 0.4)
        d.rounded_rectangle([(x0 - ox) * S, (y0 - oy) * S, (x1 - ox) * S, (y1 - oy) * S], radius=40 * S, fill=c)
        if dent:
            d.ellipse([(xc - 70 - ox) * S, (y0 - 6 - oy) * S, (xc + 70 - ox) * S, (y0 + dent * 1.4 - oy) * S], fill=cd)
        for k in range(1, 4):
            xx = x0 + (x1 - x0) * k / 4
            d.line([((xx - ox) * S, (y0 + 18 + dent * 0.5 - oy) * S), ((xx - ox) * S, (y1 - 10 - oy) * S)], fill=cd, width=int(4 * S))


BALL = Ball()
SOFT_CONTACTS = BALL.contacts_soft()
T_YES = 61.35
T_PAYOFF = T_YES - 0.15

DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0,
            "hook_text_s": 99.0, "hook_top": 0.125, "hook_font_size": 72, "hook_width": 0.92,
            "show_counter": False, "hero_min_gap_s": 0.45}


# ------------------------------------------------------------------ contrôles
def validate(verbose=True):
    C = BALL.C
    bad = []
    for a, b in zip(C, C[1:]):
        T = b[0] - a[0]
        vy0 = (b[2] - a[2] - 0.5 * G * T * T) / T
        vy1 = vy0 + G * T
        apex = a[2] - (vy0 ** 2 / (2 * G) if vy0 < 0 else 0)
        rise = a[2] - apex
        vx = (b[1] - a[1]) / T
        if a[3] == "lant" and vy0 < 0:
            bad.append((a[0], "repart vers le haut après la lanterne"))
        if b[3] == "lant" and vy1 > 0:
            bad.append((b[0], f"arrive en descendant sur la lanterne (vy {vy1:.0f})"))
        if b[3] != "lant" and vy1 < 0:
            bad.append((b[0], f"arrive en montant sur {b[3]} (vy {vy1:.0f})"))
        if a[3] != "lant" and vy0 > 0:
            bad.append((a[0], f"repart vers le bas depuis {a[3]}"))
        if rise > 700:
            bad.append((a[0], f"arc trop haut {rise:.0f}"))
        if abs(vx) < 50 and T > 0.25:
            bad.append((a[0], f"vitesse horizontale faible {vx:.0f} px/s"))
        if T < 0.85 and a[3] in HARD and b[3] in HARD:
            bad.append((a[0], "deux contacts durs trop proches"))
        # la lanterne : pas de chevauchement hors contact
        n = max(2, int(T * 60))
        for k in range(1, n):
            tt = a[0] + T * k / n
            x, y = BALL.pos(tt)
            lx, ly, _ = lantern_pos(tt)
            if abs(x - lx) < R + 32 and y - R < ly - 2 and y + R > ly - LANT_H:
                if not (b[3] == "lant" and b[0] - tt < 0.03) and not (a[3] == "lant" and tt - a[0] < 0.03):
                    bad.append((round(tt, 2), f"traverse la lanterne (haut {y - R:.0f} / bas lanterne {ly:.0f})"))
                    break
            if y - R < door_y(x, tt) - 6 and tt < 57.0 and tt > 1.2:
                bad.append((round(tt, 2), f"sort par le haut de la porte (haut {y - R:.0f} / porte {door_y(x, tt):.0f})"))
                break
    hits = BALL.hits
    iv = [b - a for a, b in zip(hits, hits[1:])]
    if verbose:
        for t, msg in bad:
            print(f"  ! {t:6.2f} {msg}")
        print("contacts durs", len(hits), "min intervalle", round(min(iv), 2), "atterrissage", round(BALL.t_land, 2),
              "fin", round(BALL.t_end, 2))
        # le presque
        best = (9e9, 0)
        for k in range(int(29.0 * 60), int(32.7 * 60)):
            tt = k / 60
            x, y = BALL.pos(tt)
            lx, ly, _ = lantern_pos(tt)
            if abs(x - lx) < R + 30:
                gap = (y - R) - ly
                if gap < best[0]:
                    best = (gap, tt)
        print("presque : écart minimal", round(best[0], 1), "px à", round(best[1], 2))
    return bad


def stills(cfg_path, times, out_dir, S=2):
    cfg = base.load_config(cfg_path, DEFAULTS)
    sim = Sim(cfg, None)
    os.makedirs(out_dir, exist_ok=True)
    lines, hf, lh, hook_top = base.layout_hook(cfg, S, W * S, H * S, sim.scene_top * H * S - 30 * S)
    for t in times:
        base.HERO["pos"] = None
        img = Image.new("RGB", (W * S, H * S), (8, 8, 12))
        dr = ImageDraw.Draw(img)
        sim.draw(dr, t, t, S)
        for i, line in enumerate(lines):
            dr.text((W * S / 2, hook_top + (i + 0.5) * lh), line, fill=(255, 255, 255), anchor="mm", font=hf)
        if S > 1:
            img = img.resize((W, H), Image.LANCZOS)
        img.save(os.path.join(out_dir, f"s_{t:05.2f}.png"))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        validate()
        sys.exit(0)
    if "--still" in sys.argv:
        i = sys.argv.index("--still")
        ts = [float(v) for v in sys.argv[i + 1].split(",")]
        stills(sys.argv[1], ts, sys.argv[i + 2])
        sys.exit(0)
    sys.exit(base.run(sys.modules[__name__]))
