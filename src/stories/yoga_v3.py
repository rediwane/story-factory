"""
Yoga v3 : « Will Bounce calm down? »

Un cours de yoga la nuit, plan fixe de face. Le tapis de Bounce est mou (muet) ; tout le reste
est dur (« Bounce »). Chaque « Bounce » casse une posture pour de bon. Ses rebonds montent de plus
en plus haut, du parquet jusqu'au hublot rond du mur du fond : il en cogne le bord, le traverse aux
trois quarts, puis s'y coince à la place de la lune. Toute la classe, par terre, lui fait Namaste ;
il gigote et dit encore « Bounce ».

Tout est écrit d'avance sur une seule horloge : les contacts de Bounce (instant, lieu, dur ou mou)
sont reliés par des arcs balistiques sous une gravité unique ; la profondeur z (0 devant, 1 au mur)
règle sa taille et son ombre. Les personnages sont des squelettes simples dont les postures sont des
images clés interpolées. Nouveau fichier : yoga.py et base.py ne sont pas modifiés.

    python3 src/stories/yoga_v3.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR

# ------------------------------------------------------------------ les voix
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.76
REACT_MAX = 0.86


def _trim(v, thr=0.03):
    a = np.abs(v)
    idx = np.where(a > thr * (a.max() + 1e-9))[0]
    if len(idx) == 0:
        return v
    return v[max(0, idx[0] - int(0.01 * SR)):idx[-1] + int(0.04 * SR)].copy()


def steady_hero_word(text, cfg):
    """Même voix, même mot : le tirage le plus court parmi plusieurs, une fois par processus.
    « Oh no. » est rogné et, s'il dépasse REACT_MAX, légèrement accéléré."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if text != cfg.get("hero_name", "Bounce"):
                v = _trim(v)
            if best is None or len(v) < len(best):
                best = v
            lim = WORD_MAX if text == cfg.get("hero_name", "Bounce") else REACT_MAX
            if len(v) / SR <= lim:
                break
        if best is not None and text != cfg.get("hero_name", "Bounce") and len(best) / SR > REACT_MAX:
            f = (len(best) / SR) / REACT_MAX
            idx = np.arange(0, len(best) - 1, f)
            best = np.interp(idx, np.arange(len(best)), best)
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word


def fast_reverb(x, sr, tail_s=0.8, wet=0.5):
    """La réverbération du moteur, calculée par FFT (même réponse, bien plus rapide)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    nf = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = fast_reverb

_orig_hook = ak.hook_voice
_hook_memo = {}


def steady_hook(text, *a, **k):
    if text not in _hook_memo:
        best = None
        for _ in range(5):
            v = _orig_hook(text, *a, **k)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
        _hook_memo[text] = best
    v = _hook_memo[text]
    return None if v is None else v.copy()


ak.hook_voice = steady_hook

TEACHER_VOICE = "af_nicole"
_orig_say = narr_voice.say
_say_memo = {}


def teacher_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    key = (text, voice, length_scale)
    if key in _say_memo:
        return _say_memo[key].copy()
    x = _orig_say(text, voice, length_scale, sr) if length_scale is not None else _orig_say(text, voice)
    if x is not None and len(x) and voice == TEACHER_VOICE:
        x = _trim(x)
        n = min(int(0.02 * sr), len(x))
        x[-n:] *= np.linspace(1, 0, n)
        x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
    if x is not None:
        _say_memo[key] = x
        return x.copy()
    return x


narr_voice.say = teacher_say

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
R0 = 125.0
FRONT, WALLY = 1240.0, 960.0
DAIS_TOP = 945.0
DAIS_X0, DAIS_X1 = 260.0, 800.0
WIN = (620.0, 470.0)
WIN_R = 93.0
WIN_FRAME = 14.0
SCENE_TOP = 0.26


def floor_y(z):
    return FRONT - (FRONT - WALLY) * z


def zscale(z):
    return 1.0 - 0.30 * z


def R_at(z):
    return R0 * zscale(z)


BG = (8, 8, 12)
WALL = (34, 24, 52)
WALL2 = (42, 30, 62)
FLOOR = (84, 56, 40)
FLOOR_L = (62, 41, 30)
SHADOW = (40, 26, 20)
COL = {"A": (250, 142, 52), "B": (78, 196, 112), "D": (238, 202, 64), "T": (188, 164, 238)}
MATC = {"A": (156, 84, 44), "B": (40, 118, 76), "D": (150, 122, 40), "Z": (24, 136, 146)}
CUSHION = (112, 58, 136)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, k):
    return a + (b - a) * k


def mix(c1, c2, k):
    return tuple(int(round(lerp(a, b, k))) for a, b in zip(c1, c2))


# ------------------------------------------------------------------ le plan
LOC = {
    "mat": (540.0, FRONT - R0, 0.0), "fl": (395.0, FRONT - R0, 0.0), "fr": (690.0, FRONT - R0, 0.0),
    "oh": (250.0, 760.0, 0.0), "yf": (650.0, 544.0, 0.45), "dais": (655.0, 856.0, 0.95),
    "win1": (652.0, 478.0, 1.0), "win2": (620.0, 462.0, 1.06), "win": (WIN[0], WIN[1], 1.0),
}
# (t, genre, lieu)  genre : H dur (« Bounce »), S mou (tapis), A point de passage
PLAN = [
    (0.00, "A", (620.0, 600.0, 1.0)),
    (0.45, "H", "fr"), (1.15, "S", "mat"), (1.95, "H", "fl"), (2.88, "S", "mat"), (3.58, "S", "mat"),
    (4.40, "H", "fr"), (5.05, "S", "mat"), (5.72, "S", "mat"), (6.70, "H", "fl"), (7.62, "S", "mat"),
    (8.70, "H", "oh"), (9.95, "S", "mat"), (10.85, "H", "fr"), (11.75, "H", "fl"), (12.62, "H", "fr"),
    (13.55, "H", "fl"), (14.75, "H", "fl"), (15.62, "H", "yf"), (16.67, "S", "mat"), (17.60, "H", "fr"),
    (18.30, "S", "mat"), (19.00, "S", "mat"), (19.90, "H", "fl"), (20.58, "S", "mat"), (21.30, "S", "mat"),
    (22.20, "H", "fr"), (23.62, "H", "fl"), (24.62, "H", "dais"), (25.50, "H", "win1"), (26.22, "S", "mat"),
    (26.95, "S", "mat"), (27.80, "H", "fr"), (28.55, "S", "mat"), (29.45, "H", "fl"), (30.12, "S", "mat"),
    (30.82, "S", "mat"), (31.45, "H", "fr"), (32.15, "S", "mat"), (32.85, "S", "mat"), (33.75, "H", "fl"),
    (34.40, "S", "mat"), (35.40, "H", "dais"), (36.40, "H", "fl"), (37.10, "S", "mat"), (37.78, "S", "mat"),
    (38.45, "H", "fl"), (39.30, "H", "fr"), (40.20, "H", "dais"), (41.08, "H", "win2"), (41.82, "S", "mat"),
    (42.55, "S", "mat"), (43.40, "H", "fl"), (44.10, "S", "mat"), (44.80, "S", "mat"), (45.70, "H", "fr"),
    (46.45, "S", "mat"), (47.50, "H", "dais"), (48.37, "H", "dais"), (49.31, "H", "dais"), (50.25, "H", "fl"),
    (51.00, "S", "mat"), (51.90, "H", "fr"), (52.80, "H", "dais"), (53.80, "H", "dais"), (54.60, "S", "mat"),
    (55.35, "H", "fl"), (56.20, "H", "fr"), (56.95, "S", "mat"), (57.83, "H", "dais"), (58.70, "H", "win"),
    (61.68, "H", "jolt"),
]
T_STUCK = 58.70
T_KNOCK = 61.68
END_T = 62.55
PAYOFF_T = 59.57          # le « Oh no. » de base.py part 0,15 s après : 59,72 s
LINES = [(3.15, "Shh."), (32.40, "Find your balance."), (60.70, "...Namaste.")]
HOOK_OFF = 8.0

# ------------------------------------------------------------------ postures (coordonnées locales,
# x à droite, y vers le haut, origine au sol sous la figure)
P = {}
P["A_lotus"] = dict(pel=(0, 48), nek=(0, 190), hed=(0, 236), le=(-64, 108), lh=(-8, 146), re=(64, 108), rh=(8, 146),
                    lk=(-102, 24), lf=(30, 14), rk=(102, 24), rf=(-30, 14), fing=(0, 0))
P["A_hop"] = dict(P["A_lotus"], le=(-96, 200), lh=(-132, 262), re=(96, 200), rh=(132, 262))
P["A_squash"] = dict(P["A_lotus"], nek=(0, 160), hed=(0, 196), le=(-84, 120), lh=(-120, 168), re=(84, 120), rh=(120, 168))
P["A_look"] = dict(P["A_lotus"], hed=(14, 246))
P["A_pray"] = dict(P["A_lotus"], le=(-50, 150), lh=(-8, 196), re=(50, 150), rh=(8, 196))

P["B_tree"] = dict(pel=(0, 182), nek=(0, 348), hed=(0, 394), le=(-44, 432), lh=(-6, 520), re=(44, 432), rh=(6, 520),
                   lk=(-6, 92), lf=(-8, 0), rk=(80, 122), rf=(8, 102), fing=(0, 0))
P["B_flail"] = dict(P["B_tree"], le=(-84, 410), lh=(-122, 470), re=(100, 380), rh=(164, 440))
P["B_two"] = dict(P["B_tree"], le=(-60, 440), lh=(-30, 520), re=(60, 440), rh=(30, 520),
                  lk=(-28, 92), lf=(-34, 0), rk=(28, 92), rf=(34, 0))
P["B_hop"] = dict(P["B_tree"], le=(-92, 334), lh=(-166, 384), re=(92, 334), rh=(166, 384))
P["B_lie"] = dict(P["B_tree"], le=(-92, 300), lh=(-150, 340), re=(92, 300), rh=(150, 340),
                  lk=(-28, 92), lf=(-34, 0), rk=(28, 92), rf=(34, 0))
P["B_kneel"] = dict(pel=(0, 110), nek=(0, 270), hed=(0, 316), le=(-60, 200), lh=(-70, 120), re=(60, 200), rh=(70, 120),
                    lk=(-30, 40), lf=(-60, 0), rk=(40, 60), rf=(30, 0), fing=(0, 0))
P["B_pray"] = dict(pel=(0, 48), nek=(0, 200), hed=(0, 246), le=(-50, 150), lh=(-8, 196), re=(50, 150), rh=(8, 196),
                   lk=(-102, 24), lf=(30, 14), rk=(102, 24), rf=(-30, 14), fing=(0, 0))

P["D_head"] = dict(hed=(0, 38), nek=(0, 80), pel=(0, 236), le=(-62, 42), lh=(-24, 6), re=(62, 42), rh=(24, 6),
                   lk=(-7, 322), lf=(-7, 412), rk=(7, 322), rf=(7, 412), fing=(0, 0))
P["D_V"] = dict(P["D_head"], lk=(-40, 314), lf=(-86, 392), rk=(40, 314), rf=(86, 392))
P["D_heap"] = dict(pel=(0, 40), nek=(0, 150), hed=(-30, 180), le=(-62, 100), lh=(-110, 40), re=(62, 100), rh=(110, 40),
                   lk=(-84, 50), lf=(-138, 12), rk=(84, 50), rf=(138, 12), fing=(0, 0))
P["D_look"] = dict(P["D_heap"], hed=(0, 196))
P["D_pray"] = dict(pel=(0, 48), nek=(0, 200), hed=(0, 246), le=(-50, 150), lh=(-8, 196), re=(50, 150), rh=(8, 196),
                   lk=(-102, 24), lf=(30, 14), rk=(102, 24), rf=(-30, 14), fing=(0, 0))

P["T_seat"] = dict(pel=(0, 50), nek=(0, 206), hed=(0, 252), le=(-72, 120), lh=(-96, 46), re=(72, 120), rh=(96, 46),
                   lk=(-106, 26), lf=(30, 14), rk=(106, 26), rf=(-30, 14), fing=(0, 0))
P["T_look"] = dict(P["T_seat"], hed=(18, 250))
P["T_shh"] = dict(P["T_seat"], re=(64, 150), rh=(14, 232), fing=(1, 0), hed=(10, 250))
P["T_tense"] = dict(P["T_seat"], nek=(0, 214), hed=(0, 246), le=(-60, 120), lh=(-80, 50), re=(60, 120), rh=(80, 50))
P["T_stand"] = dict(pel=(0, 172), nek=(0, 332), hed=(0, 378), le=(-60, 252), lh=(-64, 172), re=(60, 252), rh=(64, 172),
                    lk=(-22, 86), lf=(-24, 0), rk=(22, 86), rf=(24, 0), fing=(0, 0))
P["T_tree"] = dict(pel=(0, 182), nek=(0, 348), hed=(0, 394), le=(-44, 432), lh=(-6, 520), re=(44, 432), rh=(6, 520),
                   lk=(-6, 92), lf=(-8, 0), rk=(80, 122), rf=(8, 102), fing=(0, 0))
P["T_wobble"] = dict(P["T_tree"], le=(-70, 420), lh=(-40, 500), re=(70, 420), rh=(40, 500))
P["T_floor"] = dict(P["T_seat"], le=(-90, 150), lh=(-130, 90), re=(90, 150), rh=(130, 90), lf=(40, 60), rf=(-40, 60),
                    lk=(-110, 90), rk=(110, 90))
P["T_look_up"] = dict(P["T_floor"], hed=(10, 262))
P["T_pray"] = dict(P["T_seat"], le=(-50, 150), lh=(-8, 196), re=(50, 150), rh=(8, 196), hed=(0, 256))

SHAPE = {"A": ("rect", 112, 112), "B": ("rect", 82, 82), "D": ("oval", 80, 80), "T": ("rect", 80, 142)}
HEAD_R = {"A": 37, "B": 37, "D": 37, "T": 38}


def lerp_pose(p1, p2, k):
    return {j: (lerp(p1[j][0], p2[j][0], k), lerp(p1[j][1], p2[j][1], k)) for j in p1}


class Track:
    DEF = dict(x=0.0, y=0.0, s=1.0, rot=0.0, px=0.0, py=0.0, k=1.0, shake=0.0, dy=0.0, rock=0.0, sy=1.0,
               bun=0.0, hx=0.0)

    def __init__(self, keys):
        self.keys = []
        cur = dict(self.DEF)
        for item in keys:
            t, pose = item[0], item[1]
            kw = dict(item[2]) if len(item) > 2 else {}
            ease = kw.pop("ease", "s")
            cur = dict(cur); cur.update(kw)
            self.keys.append((t, pose, cur, ease))

    def __call__(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return P[ks[0][1]], dict(ks[0][2])
        for (t0, p0, v0, _), (t1, p1, v1, e) in zip(ks, ks[1:]):
            if t <= t1:
                u = (t - t0) / max(1e-6, t1 - t0)
                k = smooth(u) if e == "s" else (u * u if e == "in" else (1 - (1 - u) ** 2 if e == "out" else clamp01(u)))
                pose = lerp_pose(P[p0], P[p1], k) if p0 != p1 else P[p0]
                return pose, {n: lerp(v0[n], v1[n], k) for n in v0}
        return P[ks[-1][1]], dict(ks[-1][2])


def K(t, pose, **kw):
    return (t, pose, kw)


# ------------------------------------------------------------------ la scène
class Sim:
    scene_top = SCENE_TOP

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.lines = [(t, s, f"l{i}") for i, (t, s) in enumerate(LINES)]
        self.C = []
        for (t, kind, l) in PLAN:
            if l == "jolt":
                self.C.append((t, kind, WIN[0], WIN[1], 1.0, "jolt"))
                continue
            x, y, z = LOC[l] if isinstance(l, str) else l
            self.C.append((t, kind, x, y, z, l if isinstance(l, str) else ""))
        self.CT = [c[0] for c in self.C]
        self.hits = [(c[0], c[5]) for c in self.C if c[1] == "H"]
        self.hit_i = 0
        self.build_tracks()
        # secousses du coincement : instants irréguliers, 2 à 4 par seconde, de plus en plus fortes
        r = np.random.default_rng(int(cfg.get("seed", 3)) + 11)
        js, t = [], T_STUCK + 0.02
        while t < END_T + 0.5:
            js.append(t)
            t += r.uniform(0.25, 0.42)
        self.jolts = js
        self.jolt_sign = [1 if r.random() < 0.5 else -1 for _ in js]
        self.jolt_dir = [r.uniform(0, 2 * math.pi) for _ in js]

    # ---------------------------------------------------------- personnages
    def build_tracks(self):
        SA, SB = 1.3, 1.3
        SD = 1.3 * zscale(0.45)
        ST = 1.3 * zscale(0.95)
        self.SC = {"A": SA, "B": SB, "D": SD, "T": ST}
        # A : orange, devant à gauche, en tailleur
        A = [K(0.0, "A_lotus", x=250.0, y=FRONT, s=SA, px=0.0, py=40.0),
             K(1.95, "A_lotus"), K(2.12, "A_hop", dy=40.0, ease="out"), K(2.45, "A_lotus", dy=0.0, ease="in"),
             K(6.70, "A_lotus"), K(6.86, "A_hop", dy=30.0, ease="out"), K(7.15, "A_lotus", dy=0.0, ease="in"),
             K(8.70, "A_lotus"), K(8.80, "A_squash", ease="out"), K(9.05, "A_squash", rot=-30.0),
             K(9.40, "A_lotus", rot=-78.0, rock=1.0, ease="in"),
             K(17.60, "A_lotus", rot=-78.0, x=250.0), K(18.40, "A_lotus", rot=-200.0, x=300.0, rock=0.0),
             K(19.10, "A_lotus", rot=-282.0, x=330.0), K(19.40, "A_lotus", rot=-276.0),
             K(48.37, "A_lotus", rot=-276.0), K(48.70, "A_look", rot=-262.0),
             K(55.35, "A_look", rot=-262.0), K(56.05, "A_pray", rot=-360.0, x=300.0),
             K(60.70, "A_pray", rot=-360.0), K(61.20, "A_pray", rot=-348.0), K(END_T + 1, "A_pray", rot=-348.0)]
        # B : verte, devant à droite, l'arbre (pivot : le pied d'appui)
        B = [K(0.0, "B_tree", x=860.0, y=FRONT, s=SB),
             K(0.45, "B_tree"), K(0.62, "B_flail", rot=-9.0, ease="out"), K(0.95, "B_flail", rot=7.0),
             K(1.30, "B_flail", rot=-5.0), K(1.70, "B_tree", rot=2.0), K(2.10, "B_tree", rot=0.0),
             K(4.40, "B_tree"), K(4.60, "B_flail", rot=-7.0, ease="out"), K(5.00, "B_flail", rot=5.0),
             K(5.40, "B_tree", rot=0.0),
             K(6.70, "B_tree"), K(6.95, "B_two", rot=-4.0, ease="out"), K(7.30, "B_two", rot=3.0),
             K(7.70, "B_two", rot=0.0),
             K(19.90, "B_two"), K(20.10, "B_hop", dy=30.0, x=875.0, rot=6.0, ease="out"),
             K(20.40, "B_hop", dy=0.0, x=880.0, rot=12.0, ease="in"), K(20.70, "B_hop", rot=10.0),
             K(27.80, "B_hop", rot=10.0), K(28.05, "B_lie", rot=6.0, sy=0.85, ease="in"),
             K(28.45, "B_lie", rot=0.0, sy=0.24, ease="in"),
             K(33.75, "B_lie", sy=0.24), K(34.50, "B_kneel", sy=0.80), K(36.40, "B_kneel", sy=0.80),
             K(36.70, "B_lie", sy=0.24, ease="in"),
             K(48.37, "B_lie", sy=0.24), K(48.70, "B_lie", sy=0.34),
             K(55.35, "B_lie", sy=0.34), K(56.05, "B_pray", sy=1.0, rot=0.0),
             K(60.70, "B_pray"), K(61.20, "B_pray", rot=12.0), K(END_T + 1, "B_pray", rot=12.0)]
        # D : jaune, au milieu à droite, sur la tête
        D = [K(0.0, "D_head", x=650.0, y=floor_y(0.45), s=SD),
             K(0.45, "D_head"), K(0.65, "D_head", rot=-5.0), K(1.00, "D_head", rot=4.0), K(1.40, "D_head", rot=0.0),
             K(1.95, "D_head"), K(2.10, "D_V", ease="out"),
             K(4.40, "D_V"), K(4.55, "D_V", rot=-4.0), K(4.85, "D_V", rot=3.0), K(5.15, "D_V", rot=0.0),
             K(11.75, "D_V"), K(11.95, "D_V", rot=-8.0), K(15.62, "D_V", rot=-8.0),
             K(15.75, "D_V", rot=-12.0, ease="in"), K(16.15, "D_heap", rot=0.0, ease="in"),
             K(48.37, "D_heap"), K(48.70, "D_look"),
             K(55.35, "D_look"), K(56.05, "D_pray"),
             K(60.70, "D_pray"), K(61.20, "D_pray", rot=12.0), K(END_T + 1, "D_pray", rot=12.0)]
        # T : la prof, sur l'estrade, à gauche
        st = dict(x=380.0, y=DAIS_TOP, s=ST)
        T = [K(0.0, "T_seat", **st),
             K(1.95, "T_seat"), K(2.05, "T_seat", dy=14.0, ease="out"), K(2.30, "T_seat", dy=0.0),
             K(2.70, "T_look"), K(3.10, "T_shh"), K(4.10, "T_shh"), K(4.50, "T_look"),
             K(12.62, "T_look"), K(12.90, "T_tense"),
             K(24.62, "T_tense"), K(24.70, "T_tense", bun=70.0, dy=10.0, ease="out"), K(25.10, "T_tense", bun=0.0, dy=0.0),
             K(29.45, "T_tense"), K(30.40, "T_stand"),
             K(32.40, "T_stand"), K(33.30, "T_tree"),
             K(35.40, "T_tree"), K(35.55, "T_wobble", shake=5.0, ease="out"), K(36.40, "T_tree", shake=2.0),
             K(40.20, "T_tree", shake=2.0), K(40.35, "T_wobble", rot=-6.0, shake=6.0, ease="out"),
             K(40.80, "T_wobble", rot=4.0), K(41.30, "T_tree", rot=0.0, shake=3.0),
             K(43.40, "T_tree", shake=3.5), K(45.70, "T_tree", shake=6.0), K(46.40, "T_wobble", shake=7.0),
             K(47.50, "T_wobble", shake=7.0, x=380.0, y=DAIS_TOP),
             K(47.65, "T_wobble", rot=-18.0, shake=0.0, ease="in"),
             K(48.05, "T_floor", rot=-55.0, x=330.0, y=1010.0, s=1.3 * zscale(0.82), ease="in"),
             K(48.37, "T_floor", rot=-22.0), K(48.70, "T_look_up", rot=-18.0),
             K(52.80, "T_look_up", rot=-18.0), K(53.30, "T_pray", rot=0.0),
             K(60.70, "T_pray"), K(61.20, "T_pray", rot=14.0), K(END_T + 1, "T_pray", rot=14.0)]
        self.TR = {"A": Track(A), "B": Track(B), "D": Track(D), "T": Track(T)}
        self.jolt_off = {"A": [(8.6, 99)], "B": [(27.7, 99)], "D": [(15.5, 99)], "T": [(30.3, 99)]}

    def fig_state(self, n, t):
        pose, v = self.TR[n](t)
        if not any(a <= t <= b for (a, b) in self.jolt_off[n]):
            j = 0.0
            for (th, _tag) in self.hits:
                age = t - th
                if 0.0 <= age < 0.32:
                    j = max(j, 18.0 * math.sin(math.pi * age / 0.32))
            v["dy"] += j
        if v["rock"] > 0:
            v["rot"] += v["rock"] * 10.0 * math.sin(2 * math.pi * 1.1 * t)
        # les personnes à terre sursautent un peu à chaque « Bounce »
        if any(a <= t <= b for (a, b) in self.jolt_off[n]):
            for (th, _tag) in self.hits:
                age = t - th
                if 0.0 <= age < 0.25:
                    v["dy"] += 9.0 * math.sin(math.pi * age / 0.25)
        return pose, v

    def fig_points(self, n, t):
        pose, v = self.fig_state(n, t)
        pts = {j: list(p) for j, p in pose.items() if j != "fing"}
        pts["hed"][0] += v["hx"]
        rot = math.radians(v["rot"])
        if abs(rot) > 1e-6:
            c, s_ = math.cos(rot), math.sin(rot)
            px, py = v["px"], v["py"]
            for j in pts:
                x, y = pts[j][0] - px, pts[j][1] - py
                pts[j] = [px + x * c - y * s_, py + x * s_ + y * c]
        if abs(v["sy"] - 1.0) > 1e-3:
            for j in pts:
                pts[j][1] *= v["sy"]
        sx = v["shake"] * math.sin(t * 61.0) + v["shake"] * 0.5 * math.sin(t * 97.0)
        X0, Y0, sc = v["x"] + sx, v["y"], v["s"]
        out = {j: (X0 + sc * p[0], Y0 - sc * (p[1] + v["dy"])) for j, p in pts.items()}
        return out, pose["fing"], v, sc

    # ---------------------------------------------------------- Bounce
    def ball(self, t):
        """(x, y, z) du centre de Bounce."""
        C = self.C
        if t >= T_STUCK:
            return WIN[0], WIN[1], 1.0
        if t <= C[0][0]:
            return C[0][2], C[0][3], C[0][4]
        i = max(0, int(np.searchsorted(self.CT, t, side="right")) - 1)
        i = min(i, len(C) - 2)
        a, b = C[i], C[i + 1]
        T = b[0] - a[0]
        u = t - a[0]
        x = lerp(a[2], b[2], u / T)
        z = lerp(a[4], b[4], u / T)
        vy = (b[3] - a[3] - 0.5 * G * T * T) / T
        y = a[3] + vy * u + 0.5 * G * u * u
        for c in (a, b):
            if c[1] == "S":
                d = abs(t - c[0])
                if d < 0.08:
                    y += 16.0 * (1 - d / 0.08)
        return x, y, z

    def dent(self, t):
        for c in self.C:
            if c[1] == "S" and abs(t - c[0]) < 0.09:
                return (c[2], 18.0 * (1 - abs(t - c[0]) / 0.09))
        return (540.0, 0.0)

    def stuck_motion(self, t):
        """Coincé : (dx, dy, r, sx, sy, tilt). Jamais 0,15 s sans changement."""
        u = t - T_STUCK
        grow = 0.6 + 0.4 * clamp01(u / (T_KNOCK - T_STUCK))
        amp = 0.0
        sgn, ang = 1, 0.0
        for jt, sg, an in zip(self.jolts, self.jolt_sign, self.jolt_dir):
            a = t - jt
            if 0 <= a < 0.27:
                e = math.sin(math.pi * min(1.0, a / 0.12) / 2) if a < 0.12 else 1 - smooth((a - 0.12) / 0.15)
                if e > amp:
                    amp, sgn, ang = e, sg, an
        # la grosse secousse du « Bounce » final
        a = t - T_KNOCK
        if -0.05 <= a < 0.45:
            e = math.sin(math.pi * clamp01((a + 0.05) / 0.5))
            amp = max(amp, 1.6 * e)
        amp *= grow
        flick = 3.0 * math.sin(t * 23.0) + 2.0 * math.sin(t * 37.0)
        dx = sgn * 8.0 * amp + flick
        dy = 7.0 * amp * math.sin(ang) + 1.5 * math.sin(t * 29.0)
        r = R_at(1.0) * (1.0 + 0.13 * amp * (0.5 + 0.5 * math.cos(ang)))
        squash = 0.5 + 0.5 * math.sin(t * 9.0 + 3 * amp)
        sx = 1.0 + 0.04 * amp
        sy = lerp(0.88, 1.07, squash) - 0.06 * amp
        tilt = sgn * math.radians(12.0 + 8.0 * min(1.0, amp)) * min(1.0, amp * 1.4) + 0.05 * math.sin(t * 17.0)
        return dx, dy, r, sx, sy, tilt

    # ---------------------------------------------------------- API du moteur
    def step(self, dt):
        evs = []
        t_prev = self.t
        while self.hit_i < len(self.hits) and self.hits[self.hit_i][0] <= t_prev + 1e-9:
            tag = self.hits[self.hit_i][1]
            evs.append(("hit", tag))
            self.hit_i += 1
        self.t += dt
        if not self.payoff and self.t >= PAYOFF_T - 1e-9:
            self.payoff = True
            evs.append(("payoff", "STUCK"))
        if self.t >= END_T - self.cfg["end_hold_s"] - 1e-9:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def hero_mood(self):
        return "lose"

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        Q = lambda v: v * S
        self.draw_room(dr, t, S)
        bx, by, bz = self.ball(t)
        inside = t >= T_STUCK or (abs(t - 41.08) < 0.22)
        if inside:
            self.draw_hero(dr, t, S, bx, by, bz, inside=True)
        self.draw_window_frame(dr, S)
        self.draw_dais(dr, t, S)
        # tapis
        self.draw_mat(dr, S, 650.0, floor_y(0.45), MATC["D"], zscale(0.45) * 1.15, 0.95)
        self.draw_mat(dr, S, 250.0, FRONT, MATC["A"], 1.15, 1.35)
        self.draw_mat_b(dr, t, S)
        dx, dd = self.dent(t)
        self.draw_mat(dr, S, 540.0, FRONT, MATC["Z"], 1.15, 1.0, dent=(dx, dd))
        # ombre de Bounce
        if not inside:
            self.draw_shadow(dr, S, bx, by, bz)
        order = []
        for n in "ADTB":
            pts, fing, v, sc = self.fig_points(n, t)
            order.append((v["y"], n, (pts, fing, v, sc)))
        if not inside:
            order.append((floor_y(bz) + 0.5, "ball", None))
        order.sort(key=lambda o: o[0])
        for (_d, n, data) in order:
            if n == "ball":
                self.draw_hero(dr, t, S, bx, by, bz)
            else:
                self.draw_figure(dr, S, n, *data)
                if n == "B":
                    self.draw_blanket(dr, t, S, data[0])
                if n == "T":
                    self.draw_cushion_on_head(dr, t, S, data[0], data[3])
        self.draw_rings(dr, t, S)

    def draw_hero(self, dr, t, S, bx, by, bz, inside=False):
        Q = lambda v: v * S
        if t >= T_STUCK:
            dx, dy, r, sx, sy, tilt = self.stuck_motion(t)
            base.HERO["tilt"] = tilt
            self.paste_ball(dr, S, bx + dx, by + dy, r, sx, sy)
            return
        r = R_at(bz)
        if inside:
            r = R_at(1.0) * 0.86
        base.ball(dr, Q(bx), Q(by), Q(r))

    def paste_ball(self, dr, S, x, y, r, sx, sy):
        """base.ball() rendu à part, puis écrasé ou étiré, et posé sur l'image."""
        rr = r * 1.6 * S
        size = int(2 * rr + 8)
        tmp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        td = ImageDraw.Draw(tmp)
        save = base.HERO["pos"]
        base.ball(td, size / 2, size / 2, r * S)
        base.HERO["pos"] = (x * S, y * S) if save is None else save
        w2, h2 = max(4, int(size * sx)), max(4, int(size * sy))
        tmp = tmp.resize((w2, h2), Image.LANCZOS)
        img = dr._image
        img.paste(tmp, (int(x * S - w2 / 2), int(y * S - h2 / 2)), tmp)

    def draw_shadow(self, dr, S, bx, by, bz):
        Q = lambda v: v * S
        on_dais = bz >= 0.85 and DAIS_X0 + 20 <= bx <= DAIS_X1 - 20
        gy = DAIS_TOP if on_dais else floor_y(bz)
        r = R_at(bz)
        h = max(0.0, gy - (by + r))
        k = 1.0 / (1.0 + h / 420.0)
        w = r * 1.25 * k
        hh = r * 0.22 * k
        col = mix(dim(FLOOR, 0.95) if not on_dais else (150, 110, 76), SHADOW, 0.85 * k)
        dr.ellipse([Q(bx - w), Q(gy - hh), Q(bx + w), Q(gy + hh)], fill=col)

    def draw_room(self, dr, t, S):
        Q = lambda v: v * S
        dr.rectangle([0, 0, Q(W), Q(WALLY)], fill=WALL)
        for x0 in (40.0, 800.0):
            dr.rectangle([Q(x0), Q(560), Q(x0 + 240), Q(900)], fill=WALL2)
        # le ciel par le hublot
        mx, my = WIN
        dr.ellipse([Q(mx - WIN_R), Q(my - WIN_R), Q(mx + WIN_R), Q(my + WIN_R)], fill=(16, 22, 50))
        for (sx_, sy_, sr) in ((585, 420, 3), (668, 440, 2.5), (640, 505, 2)):
            dr.ellipse([Q(sx_ - sr), Q(sy_ - sr), Q(sx_ + sr), Q(sy_ + sr)], fill=(200, 205, 230))
        lx, ly, lr = mx - 26, my + 30, 30
        dr.ellipse([Q(lx - lr), Q(ly - lr), Q(lx + lr), Q(ly + lr)], fill=(232, 228, 206))
        dr.ellipse([Q(lx - 14), Q(ly - 12), Q(lx - 4), Q(ly - 2)], fill=(212, 206, 184))
        # le sol
        dr.rectangle([0, Q(WALLY), Q(W), Q(H)], fill=FLOOR)
        vx, vy = 540.0, 260.0
        for kx in range(-9, 10):
            xb = 540.0 + kx * 150.0
            at = lambda y: vx + (xb - vx) * (y - vy) / (H - vy)
            dr.line([Q(at(WALLY)), Q(WALLY), Q(at(H)), Q(H)], fill=FLOOR_L, width=int(Q(3)))
        for y in (1010, 1080, 1160, 1260, 1400, 1580, 1800):
            dr.line([0, Q(y), Q(W), Q(y)], fill=dim(FLOOR_L, 1.05), width=int(Q(2)))
        dr.rectangle([0, Q(WALLY - 20), Q(W), Q(WALLY)], fill=(24, 18, 36))

    def draw_window_frame(self, dr, S):
        Q = lambda v: v * S
        mx, my = WIN
        r1 = WIN_R + WIN_FRAME
        dr.ellipse([Q(mx - r1), Q(my - r1), Q(mx + r1), Q(my + r1)], outline=(96, 80, 122), width=int(Q(WIN_FRAME)))

    def draw_dais(self, dr, t, S):
        Q = lambda v: v * S
        dr.rectangle([Q(DAIS_X0), Q(DAIS_TOP), Q(DAIS_X1), Q(DAIS_TOP + 26)], fill=(150, 110, 76))
        dr.rectangle([Q(DAIS_X0), Q(DAIS_TOP + 26), Q(DAIS_X1), Q(DAIS_TOP + 40)], fill=(104, 74, 50))
        # le coussin : sous la prof ; il saute à 49,31 s et retombe sur sa tête
        if t < 49.31:
            cx, cy = 380.0, DAIS_TOP - 6
            dr.ellipse([Q(cx - 70), Q(cy - 16), Q(cx + 70), Q(cy + 12)], fill=CUSHION)
        elif t < 49.31 + 0.62:
            u = (t - 49.31) / 0.62
            hx, hy = self.teacher_head(49.31 + 0.62)
            cx = lerp(380.0, hx, u)
            cy = lerp(DAIS_TOP - 6, hy, u) - 240.0 * 4 * u * (1 - u)
            ang = 300.0 * u
            self.draw_cushion(dr, S, cx, cy, 1.0, ang)

    def teacher_head(self, t):
        pts, _f, v, sc = self.fig_points("T", t)
        hx, hy = pts["hed"]
        return hx, hy - HEAD_R["T"] * sc * 1.05

    def draw_cushion(self, dr, S, cx, cy, k, ang):
        Q = lambda v: v * S
        a = math.radians(ang)
        pts = []
        for i in range(24):
            th = 2 * math.pi * i / 24
            px, py = 70 * k * math.cos(th), 15 * k * math.sin(th)
            pts.append((Q(cx + px * math.cos(a) - py * math.sin(a)), Q(cy + px * math.sin(a) + py * math.cos(a))))
        dr.polygon(pts, fill=CUSHION)

    def draw_cushion_on_head(self, dr, t, S, pts, sc):
        if t < 49.31 + 0.62:
            return
        hx, hy = pts["hed"]
        hy -= HEAD_R["T"] * sc * 1.05
        wob = 6.0 * math.sin(t * 5.0) if t < 50.5 else 0.0
        self.draw_cushion(dr, S, hx, hy, 0.82, -10.0 + wob)

    def draw_mat_b(self, dr, t, S):
        """Le tapis de la verte, à plat jusqu'à 51,90 s."""
        if t < 51.90:
            self.draw_mat(dr, S, 860.0, FRONT, MATC["B"], 1.15, 0.95)

    def draw_blanket(self, dr, t, S, pts):
        """51,90 s : le tapis de la verte se dresse d'un coup, puis se rabat sur elle."""
        if t < 51.90 or t >= 56.05:
            if t >= 56.05:
                self.draw_mat(dr, S, 860.0, FRONT, MATC["B"], 1.15, 0.95)
            return
        Q = lambda v: v * S
        u = clamp01((t - 51.90) / 0.45)
        x0, x1, yb = 715.0, 975.0, 1246.0
        if u < 0.5:
            top = yb - 70 - 440 * smooth(u / 0.5)
        else:
            top = lerp(yb - 510, 1150.0, smooth((u - 0.5) / 0.5))
        dr.rounded_rectangle([Q(x0), Q(top), Q(x1), Q(yb)], radius=Q(18), fill=MATC["B"])
        dr.rounded_rectangle([Q(x0), Q(top), Q(x1), Q(top + 16)], radius=Q(8), fill=dim(MATC["B"], 1.25))

    def draw_mat(self, dr, S, x, y, col, sc, wk, dent=None):
        Q = lambda v: v * S
        yb, yf = y - 48 * sc, y + 54 * sc
        hb, hf = 64 * sc * wk, 78 * sc * wk
        n = 24
        top, bot = [], []
        for i in range(n + 1):
            u = i / n
            xb_ = x - hb + 2 * hb * u
            xf_ = x - hf + 2 * hf * u
            db = df = 0.0
            if dent is not None and dent[1] > 0:
                db = dent[1] * 0.5 * max(0.0, 1 - abs(xb_ - dent[0]) / 100.0) ** 2
                df = dent[1] * max(0.0, 1 - abs(xf_ - dent[0]) / 100.0) ** 2
            top.append((Q(xb_), Q(yb + db)))
            bot.append((Q(xf_), Q(yf + df)))
        dr.polygon(top + bot[::-1], fill=col)
        edge = [(px, py + Q(9)) for (px, py) in bot]
        dr.polygon(bot + edge[::-1], fill=dim(col, 0.62))

    def draw_figure(self, dr, S, n, pts, fing, v, sc):
        Q = lambda p: (p[0] * S, p[1] * S)
        col = COL[n]
        limb = dim(col, 0.8)
        kind, wt, wb = SHAPE[n]
        k = v["k"]
        pel, nek, hed = np.array(pts["pel"]), np.array(pts["nek"]), np.array(pts["hed"])
        ax = nek - pel
        L = float(np.linalg.norm(ax)) + 1e-9
        u = ax / L
        nrm = np.array([-u[1], u[0]])
        wt_, wb_ = wt * sc * k, wb * sc * k
        sh_l = nek + nrm * (wt_ / 2 - 12 * sc)
        sh_r = nek - nrm * (wt_ / 2 - 12 * sc)
        hip_l = pel + nrm * max(14 * sc, wb_ / 2 - 18 * sc)
        hip_r = pel - nrm * max(14 * sc, wb_ / 2 - 18 * sc)
        if np.dot(np.array(pts["le"]) - nek, nrm) < 0:
            sh_l, sh_r = sh_r, sh_l
        if np.dot(np.array(pts["lk"]) - pel, nrm) < 0:
            hip_l, hip_r = hip_r, hip_l
        lw_leg, lw_arm = 42 * sc, 34 * sc

        def limb_line(a, b, c, w):
            ptsl = [Q(a), Q(b), Q(c)]
            dr.line(ptsl, fill=limb, width=max(2, int(w * S)), joint="curve")
            for p in (a, b, c):
                r = w / 2 * S
                dr.ellipse([p[0] * S - r, p[1] * S - r, p[0] * S + r, p[1] * S + r], fill=limb)
        limb_line(hip_l, pts["lk"], pts["lf"], lw_leg)
        limb_line(hip_r, pts["rk"], pts["rf"], lw_leg)
        if kind == "oval":
            c = (pel + nek) / 2
            a_ = L / 2 + 22 * sc
            b_ = wt_ / 2
            poly = [Q(c + u * a_ * math.cos(th) + nrm * b_ * math.sin(th)) for th in np.linspace(0, 2 * math.pi, 28)]
        else:
            poly = [Q(pel + nrm * wb_ / 2), Q(nek + nrm * wt_ / 2 + u * 6 * sc), Q(nek - nrm * wt_ / 2 + u * 6 * sc),
                    Q(pel - nrm * wb_ / 2)]
        dr.polygon(poly, fill=col)
        limb_line(sh_l, pts["le"], pts["lh"], lw_arm)
        limb_line(sh_r, pts["re"], pts["rh"], lw_arm)
        hr = HEAD_R[n] * sc
        hx, hy = hed
        if n == "T":
            up = hed - nek
            up = up / (np.linalg.norm(up) + 1e-9)
            ba = math.radians(v["bun"] + (70.0 if 45.7 <= self.t_draw <= 99 else 0.0))
            c_, s_ = math.cos(ba), math.sin(ba)
            up = np.array([up[0] * c_ - up[1] * s_, up[0] * s_ + up[1] * c_])
            bx_, by_ = hed + up * hr * 1.08
            br = hr * 0.5
            dr.ellipse([(bx_ - br) * S, (by_ - br) * S, (bx_ + br) * S, (by_ + br) * S], fill=dim(col, 0.86))
        dr.ellipse([(hx - hr) * S, (hy - hr) * S, (hx + hr) * S, (hy + hr) * S], fill=col)
        for side, on in (("rh", fing[0]), ("lh", fing[1])):
            if on > 0.5:
                el = np.array(pts["re" if side == "rh" else "le"])
                hd = np.array(pts[side])
                d = hd - el
                d = d / (np.linalg.norm(d) + 1e-9)
                tip = hd + d * 52 * sc
                dr.line([Q(hd), Q(tip)], fill=limb, width=max(2, int(15 * sc * S)))

    def draw_rings(self, dr, t, S):
        for c in self.C:
            if c[1] != "H":
                continue
            age = t - c[0]
            if age < 0 or age > 1.0:
                continue
            tag = c[5]
            z = c[4]
            if tag in ("win", "win1", "win2", "jolt"):
                cx, cy = c[2], c[3]
                rmax, start = (260.0 if tag == "jolt" else 520.0), WIN_R
            else:
                cx, cy = c[2], c[3] + R_at(z)
                rmax = 900.0 if z < 0.3 else 620.0
                start = R_at(z)
            dur = 0.85
            u = age / dur
            if u >= 1:
                continue
            r = start + (rmax - start) * (1 - (1 - u) ** 2)
            kk = (1 - u) ** 1.4
            w = 9 * (1 - 0.6 * u) * (0.7 if tag == "jolt" else 1.0)
            col = mix(BG, (255, 255, 255), 0.85 * kk)
            dr.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=col, width=max(1, int(w * S)))


# le dessin de la prof a besoin du temps courant (chignon défait)
_orig_draw = Sim.draw


def _draw_with_t(self, dr, snap, t, S):
    self.t_draw = t
    return _orig_draw(self, dr, snap, t, S)


Sim.draw = _draw_with_t

DEFAULTS = {
    "ball_r": R0, "gravity": G,
    "hook_text_s": HOOK_OFF, "hook_top": 0.125, "hook_font_size": 88,
    "narrator_voice": TEACHER_VOICE, "narrator_length": 1.0, "narr_gap_s": 0.08,
    "sub_y": 3.0, "sub_font_size": 10, "sub_words": 4,
    "watermark_y": 0.955, "end_hold_s": 0.0, "narr_tail_s": 0.0,
    "min_duration_s": 61.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True,
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
