"""
Prototype « yoga » : un cours de yoga en silence total, la nuit, en plan fixe de face. La
professeure (sans visage, la voix douce du narrateur) guide quatre élèves sans visage dans
leurs postures. Bounce saute sur son tapis : le tapis est mou, donc muet ; le parquet est
dur, donc « Bounce ». Il glisse toujours du tapis. La professeure essaie le chuchotement,
puis de lui courir après avec le tapis, puis une règle : « Whoever moves... is out. Except
you, Bounce. » Les élèves sortent un par un ; au plus grand rebond, elle fait « Shh! » par
réflexe... et se met dehors elle-même. Bounce reste seul, en paix.

Tout est écrit d'avance sur une seule horloge : les contacts de Bounce (instant, lieu, dur
ou mou) sont reliés par des arcs balistiques sous une gravité unique ; chaque personnage est
un squelette simple (bassin, cou, tête, coudes, mains, genoux, pieds) dont les postures sont
des images clés interpolées. La première et la dernière image se raccordent (boucle).

    python3 src/stories/yoga.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR

# ------------------------------------------------------------------ les voix
# Le mot de Bounce : piper ne le rend pas deux fois à la même longueur ; on garde un
# tirage court, une fois par processus. Même voix, même mot.
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.78


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
            if text != cfg.get("hero_name", "Bounce") or len(v) / SR <= WORD_MAX:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# la réverbération du moteur, calculée par FFT (même résultat, bien plus rapide)
def fast_reverb(x, sr, tail_s=0.8, wet=0.5):
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

# l'accroche : un seul tirage par processus (le plus court de quelques-uns)
_orig_hook = ak.hook_voice
_hook_memo = {}


def steady_hook(text, *a, **k):
    if text not in _hook_memo:
        best = None
        for _ in range(4):
            v = _orig_hook(text, *a, **k)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
        _hook_memo[text] = best
    v = _hook_memo[text]
    return None if v is None else v.copy()


ak.hook_voice = steady_hook

# la professeure : Kokoro, voix douce ; chaque réplique coupée au plus près du son
TEACHER_VOICE = "af_nicole"
_orig_say = narr_voice.say
_say_memo = {}


def teacher_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    key = (text, voice, length_scale)
    if key in _say_memo:
        return _say_memo[key].copy()
    x = _orig_say(text, voice, length_scale, sr) if length_scale is not None else _orig_say(text, voice)
    if x is not None and len(x) and voice == TEACHER_VOICE:
        a = np.abs(x)
        idx = np.where(a > 0.03 * a.max())[0]
        if len(idx):
            x = x[max(0, idx[0] - int(0.03 * sr)):idx[-1] + int(0.06 * sr)].copy()
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
R = 95.0
FRONT = 1530.0            # le sol du premier rang (pieds, bas de la balle)
BACK = 1150.0             # le sol du rang du fond
DAIS = 1062.0             # le dessus de l'estrade
WALLY = 1030.0            # le pied du mur du fond
YM = FRONT - R            # centre de Bounce posé au sol
TDEPTH = 1450.0           # la professeure, à genoux derrière le tapis de Bounce
MOON = (540.0, 640.0, 165.0)
PL, PR = 360.0, 665.0     # le parquet nu à gauche et à droite du tapis
MATX0 = 500.0
SCENE_TOP = 0.235
FS = 1.12                 # l'échelle du premier rang

BG = (8, 8, 12)
WALL = (32, 24, 48)
WALL2 = (40, 30, 58)
FLOOR = (78, 52, 38)
FLOOR_L = (58, 38, 28)
COL = {"A": (250, 142, 52), "B": (78, 196, 112), "C": (78, 126, 238), "D": (238, 202, 64), "T": (188, 164, 238)}
MATC = {"A": (156, 84, 44), "B": (40, 118, 76), "C": (44, 76, 150), "D": (150, 122, 40), "Z": (24, 136, 146)}


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, k):
    return a + (b - a) * k


def mix(c1, c2, k):
    return tuple(int(round(lerp(a, b, k))) for a, b in zip(c1, c2))


CROUCH_DX = 0.0


def depth_scale(y):
    return 0.92 + (y - DAIS) / (FRONT - DAIS) * 0.20


CROUCH_DX = 92.0

# ------------------------------------------------------------------ le plan : répliques
LINES = [
    (2.58, "Breathe in..."), (4.65, "And out."), (5.70, "Now... be still."), (10.05, "Shh."),
    (11.20, "Find your inner peace."), (16.15, "Good..."), (19.25, "Yes..."),
    (21.30, "Please... be... still."), (26.03, "Shh!"), (28.00, "Breathe... in..."),
    (35.80, "New rule."), (36.95, "Whoever moves..."), (39.53, "...is out."),
    (40.50, "Except you, Bounce."), (43.20, "You moved. Out."), (49.63, "Shh!"),
    (51.00, "Out. All of you."), (53.30, "...Me too."), (55.40, "...Namaste, everyone."),
]
PAYOFF_T = 58.40
END_T = 61.60

# ------------------------------------------------------------------ le tapis de Bounce
MAT_KEYS = [(0.0, 500.0), (15.05, 500.0), (15.75, 665.0), (17.40, 665.0), (17.90, 500.0), (18.30, 500.0),
            (18.65, 665.0), (21.35, 665.0), (22.95, 500.0)]


def mat_x(t):
    if t <= MAT_KEYS[0][0]:
        return MAT_KEYS[0][1]
    for (t0, x0), (t1, x1) in zip(MAT_KEYS, MAT_KEYS[1:]):
        if t <= t1:
            return lerp(x0, x1, smooth((t - t0) / (t1 - t0)))
    return MAT_KEYS[-1][1]


# ------------------------------------------------------------------ figures : postures
# coordonnées locales : x à droite, y vers le haut, origine au sol sous la figure
P = {}
P["A_lotus"] = dict(pel=(0, 48), nek=(0, 190), hed=(0, 236), le=(-64, 108), lh=(-8, 146), re=(64, 108), rh=(8, 146),
                    lk=(-102, 24), lf=(30, 14), rk=(102, 24), rf=(-30, 14), fing=(0, 0))
P["A_up"] = dict(P["A_lotus"], le=(-62, 262), lh=(-8, 332), re=(62, 262), rh=(8, 332))
P["A_flinch"] = dict(P["A_lotus"], le=(-96, 200), lh=(-132, 262), re=(96, 200), rh=(132, 262))
P["A_stand"] = dict(pel=(0, 160), nek=(0, 300), hed=(0, 346), le=(-64, 232), lh=(-70, 156), re=(64, 232), rh=(70, 156),
                    lk=(-24, 82), lf=(-26, 0), rk=(24, 82), rf=(26, 0), fing=(0, 0))
P["A_sad"] = dict(P["A_stand"], hed=(10, 330), nek=(4, 292))

P["B_tree"] = dict(pel=(0, 182), nek=(0, 348), hed=(0, 394), le=(-44, 432), lh=(-6, 520), re=(44, 432), rh=(6, 520),
                   lk=(-6, 92), lf=(-8, 0), rk=(80, 122), rf=(8, 102), fing=(0, 0))
P["B_droop"] = dict(P["B_tree"], le=(-56, 398), lh=(-30, 470), re=(56, 398), rh=(30, 470), nek=(0, 340), hed=(4, 382))
P["B_flail"] = dict(P["B_tree"], le=(-84, 410), lh=(-122, 470), re=(100, 380), rh=(164, 440))
P["B_two"] = dict(P["B_tree"], le=(-92, 334), lh=(-166, 384), re=(92, 334), rh=(166, 384),
                  lk=(-28, 92), lf=(-34, 0), rk=(28, 92), rf=(34, 0))
P["B_stand"] = dict(P["B_tree"], le=(-60, 268), lh=(-64, 186), re=(60, 268), rh=(64, 186),
                    lk=(-24, 92), lf=(-26, 0), rk=(24, 92), rf=(26, 0))
P["B_sad"] = dict(P["B_stand"], hed=(10, 374), nek=(4, 342))

P["C_war"] = dict(pel=(0, 150), nek=(0, 300), hed=(0, 346), le=(-100, 302), lh=(-200, 304), re=(100, 302), rh=(200, 304),
                  lk=(-116, 88), lf=(-172, 0), rk=(82, 92), rf=(152, 0), fing=(0, 0))
P["C_noodle"] = dict(P["C_war"], le=(-96, 254), lh=(-106, 172), re=(96, 254), rh=(106, 172), hed=(0, 338))
P["C_flinch"] = dict(P["C_war"], le=(-84, 392), lh=(-124, 474), re=(84, 392), rh=(124, 474))
P["C_stand"] = dict(pel=(0, 160), nek=(0, 306), hed=(0, 352), le=(-60, 240), lh=(-64, 162), re=(60, 240), rh=(64, 162),
                    lk=(-24, 82), lf=(-26, 0), rk=(24, 82), rf=(26, 0), fing=(0, 0))
P["C_sad"] = dict(P["C_stand"], hed=(10, 334), nek=(4, 298))

P["D_head"] = dict(hed=(0, 38), nek=(0, 80), pel=(0, 236), le=(-62, 42), lh=(-24, 6), re=(62, 42), rh=(24, 6),
                   lk=(-7, 322), lf=(-7, 412), rk=(7, 322), rf=(7, 412), fing=(0, 0))
P["D_heap"] = dict(pel=(0, 40), nek=(0, 192), hed=(0, 238), le=(-62, 124), lh=(-96, 48), re=(62, 124), rh=(96, 48),
                   lk=(-74, 40), lf=(-128, 12), rk=(74, 40), rf=(128, 12), fing=(0, 0))
P["D_V"] = dict(P["D_head"], lk=(-34, 314), lf=(-70, 396), rk=(34, 314), rf=(70, 396))
P["D_stand"] = dict(pel=(0, 160), nek=(0, 306), hed=(0, 352), le=(-60, 240), lh=(-64, 162), re=(60, 240), rh=(64, 162),
                    lk=(-24, 82), lf=(-26, 0), rk=(24, 82), rf=(26, 0), fing=(0, 0))
P["D_sad"] = dict(P["D_stand"], hed=(10, 334), nek=(4, 298))

P["T_seat"] = dict(pel=(0, 50), nek=(0, 206), hed=(0, 252), le=(-72, 120), lh=(-96, 46), re=(72, 120), rh=(96, 46),
                   lk=(-106, 26), lf=(30, 14), rk=(106, 26), rf=(-30, 14), fing=(0, 0))
P["T_seat_up"] = dict(P["T_seat"], le=(-64, 272), lh=(-14, 348), re=(64, 272), rh=(14, 348))
P["T_seat_shh"] = dict(P["T_seat"], re=(64, 150), rh=(14, 232), fing=(1, 0))
P["T_seat_shh2"] = dict(P["T_seat"], le=(-60, 150), lh=(-16, 230), re=(60, 150), rh=(16, 230), fing=(1, 1),
                        nek=(0, 214), hed=(0, 244))
P["T_slump"] = dict(P["T_seat"], nek=(16, 176), hed=(40, 206), le=(-40, 100), lh=(-30, 30), re=(80, 96), rh=(90, 26))
P["T_stand"] = dict(pel=(0, 172), nek=(0, 332), hed=(0, 378), le=(-60, 252), lh=(-64, 172), re=(60, 252), rh=(64, 172),
                    lk=(-22, 86), lf=(-24, 0), rk=(22, 86), rf=(24, 0), fing=(0, 0))
P["T_step"] = dict(P["T_stand"], rk=(30, 120), rf=(36, 52), le=(-76, 262), lh=(-110, 200), re=(76, 262), rh=(110, 200))
P["T_crouch"] = dict(pel=(0, 92), nek=(-8, 244), hed=(-20, 288), le=(-44, 150), lh=(40, 30), re=(62, 158), rh=(104, 30),
                     lk=(-34, 16), lf=(-46, 2), rk=(34, 16), rf=(46, 2), fing=(0, 0))
P["T_crouch_ok"] = dict(P["T_crouch"], nek=(-6, 236), hed=(-16, 278))
P["T_armup"] = dict(P["T_stand"], re=(70, 402), rh=(80, 486))
P["T_sweep_r"] = dict(P["T_stand"], re=(92, 282), rh=(160, 236), fing=(1, 0))
P["T_point_b"] = dict(P["T_stand"], le=(-74, 278), lh=(-150, 214), fing=(0, 1))
P["T_point_c"] = dict(P["T_stand"], le=(-96, 322), lh=(-190, 310), fing=(0, 1))
P["T_shh"] = dict(P["T_stand"], re=(62, 270), rh=(14, 360), fing=(1, 0))
P["T_shh_sl"] = dict(P["T_shh"], le=(-96, 322), lh=(-190, 312))
P["T_shh_sr"] = dict(P["T_shh"], le=(-80, 300), lh=(-120, 250))
P["T_shh_look"] = dict(P["T_shh"], hed=(14, 370), nek=(4, 330))
P["T_sad"] = dict(P["T_stand"], hed=(10, 358), nek=(4, 322), le=(-56, 248), lh=(-58, 166), re=(56, 248), rh=(58, 166))

SHAPE = {"A": ("rect", 112, 112), "B": ("rect", 82, 82), "C": ("rect", 138, 22), "D": ("oval", 80, 80),
         "T": ("rect", 80, 142)}
HEAD_R = {"A": 37, "B": 37, "C": 37, "D": 37, "T": 38}


def lerp_pose(p1, p2, k):
    return {j: (lerp(p1[j][0], p2[j][0], k), lerp(p1[j][1], p2[j][1], k)) for j in p1}


class Track:
    """Images clés : (t, pose, réglages). Chaque clé dit l'état atteint à son instant ;
    entre deux clés, glissement adouci. Les réglages non donnés restent ceux d'avant."""
    DEF = dict(x=0.0, y=0.0, s=1.0, rot=0.0, px=0.0, py=0.0, k=1.0, walk=0.0, shake=0.0, bun=0.0, dy=0.0, rock=0.0,
               vis=1.0)

    def __init__(self, keys):
        self.keys = []
        cur = dict(self.DEF)
        for item in keys:
            t, pose = item[0], item[1]
            kw = item[2] if len(item) > 2 else {}
            ease = kw.pop("ease", "s") if kw else "s"
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
                v = {n: lerp(v0[n], v1[n], k) for n in v0}
                return pose, v
        return P[ks[-1][1]], dict(ks[-1][2])


def K(t, pose, **kw):
    return (t, pose, kw)


# ------------------------------------------------------------------ les contacts de Bounce
# (t, genre, x, y, tag) ; genre : "A" point de passage, "S" tapis (muet), "H" dur
def build_contacts():
    C = [(0.0, "A", 640.0, YM - 600.0, ""), (0.68, "H", 640.0, YM, "floor")]
    soft = [1.25, 1.78, 2.30, 2.82]
    C += [(t, "S", None, YM, "") for t in soft]
    C += [(3.75, "H", PR, YM, "floor")]
    C += [(t, "S", None, YM, "") for t in (4.35, 4.90, 5.45, 5.95, 6.40, 6.80)]
    C += [(7.15, "S", 485.0, YM, ""), (7.48, "S", 466.0, YM, ""), (7.80, "S", 440.0, YM, ""),
          (8.15, "H", 404.0, YM, "edge")]
    C += [(9.15, "H", PR, YM, "floor")]
    C += [(t, "S", None, YM, "") for t in (9.75, 10.30, 10.85, 11.40, 11.95, 12.50, 13.05)]
    C += [(13.90, "H", PR, YM, "floor"), (14.45, "S", None, YM, ""), (15.00, "S", None, YM, ""),
          (15.95, "S", None, YM, ""), (16.50, "S", None, YM, ""),
          (17.35, "H", 500.0, YM, "floor"), (18.25, "H", PR, YM, "floor"),
          (18.85, "S", None, YM, ""), (19.40, "S", 693.0, YM, ""),
          (20.35, "H", None, None, "head"),
          (21.35, "S", None, YM, ""), (21.90, "S", None, YM, ""), (22.45, "S", None, YM, ""), (23.00, "S", None, YM, ""),
          (23.50, "S", None, YM, ""),
          (24.10, "H", PL, YM, "floor"), (25.10, "H", 830.0, FRONT - 532.0 * FS - R, "hands")]
    C += [(t, "S", None, YM, "") for t in (25.90, 26.45, 27.00, 27.55, 28.10, 28.65, 29.20)]
    C += [(30.00, "H", PR, YM, "floor"), (30.60, "S", None, YM, ""), (31.10, "S", None, YM, ""),
          (32.00, "H", PL, YM, "floor"), (33.05, "H", PR, YM, "floor"), (34.00, "H", PL, YM, "floor"),
          (34.87, "H", PR, YM, "floor")]
    C += [(t, "S", None, YM, "") for t in (35.45, 36.00, 36.55, 37.10, 37.65, 38.15)]
    C += [(38.60, "H", PR, YM, "floor")]
    C += [(t, "S", None, YM, "") for t in (39.20, 39.75, 40.30, 40.85, 41.40)]
    C += [(42.30, "H", PR, YM, "floor")]
    C += [(t, "S", None, YM, "") for t in (42.90, 43.45, 44.00, 44.55)]
    C += [(45.40, "H", PL, YM, "floor"), (46.35, "H", PR, YM, "floor"), (47.25, "H", PR, YM, "floor"),
          (48.70, "H", PL, YM, "scare")]
    C += [(round(49.30 + 0.55 * k, 2), "S", None, YM, "") for k in range(14)]       # 49,30 ... 56,45
    C += [(57.30, "H", PR, YM, "far:1.0")]
    C += [(t, "S", None, YM, "") for t in (57.90, 58.45, 59.00, 59.55, 60.05)]
    C += [(60.60, "H", 640.0, YM, "floor"), (END_T, "A", 640.0, YM - 605.0, "")]
    return C


# ------------------------------------------------------------------ la scène
class Sim:
    scene_top = SCENE_TOP

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.outcome = None
        self.lines = [(t, s, f"l{i}") for i, (t, s) in enumerate(LINES)]
        self.build_tracks()
        self.C = build_contacts()
        self.resolve_contacts()
        self.hits = [(c[0], c[4]) for c in self.C if c[1] == "H"]
        self.hit_i = 0
        self.rings = []
        for c in self.C:
            if c[1] == "H":
                big = c[4] == "scare"
                cx, cy = self.contact_point(c)
                self.rings.append((c[0], cx, cy, big, c[4]))

    # ---------------------------------------------------------- personnages
    def build_tracks(self):
        jd = dict(ease="out")
        # A : orange, devant à gauche, en tailleur
        A = [K(0.0, "A_lotus", x=115.0, y=FRONT, s=FS, px=102.0, py=0.0),
             K(2.60, "A_lotus"), K(3.55, "A_up", k=1.12), K(3.75, "A_up", k=1.12), K(3.95, "A_lotus", k=0.9, ease="out"),
             K(4.65, "A_lotus", k=0.9), K(5.40, "A_lotus", k=0.84), K(5.75, "A_lotus", k=0.84), K(6.05, "A_lotus", k=1.0),
             K(24.10, "A_lotus"), K(24.28, "A_flinch", dy=70.0, ease="out"), K(24.62, "A_lotus", dy=0.0, rot=-38.0, ease="in"),
             K(24.80, "A_lotus", rock=1.0), K(26.90, "A_lotus", rock=1.0), K(27.10, "A_lotus", rock=0.0),
             K(27.80, "A_lotus", rot=0.0),
             K(34.00, "A_lotus"), K(34.30, "A_lotus", rot=-34.0, ease="in"), K(34.45, "A_lotus", rock=1.0),
             K(35.70, "A_lotus", rock=1.0), K(35.85, "A_lotus", rock=0.0), K(36.50, "A_lotus", rot=0.0),
             K(48.70, "A_lotus"), K(48.86, "A_flinch", dy=80.0, ease="out"), K(49.20, "A_lotus", dy=0.0, rot=-42.0, ease="in"),
             K(51.55, "A_lotus"), K(52.15, "A_sad", rot=0.0), K(52.35, "A_sad", px=0.0),
             K(54.40, "A_sad", x=-170.0, walk=1.0, ease="lin")]
        # B : vert, devant à droite, l'arbre (pivot : le pied d'appui)
        B = [K(0.0, "B_tree", x=830.0, y=FRONT, s=FS, px=-8.0, py=0.0),
             K(0.68, "B_tree"), K(0.95, "B_tree", rot=9.0), K(1.30, "B_tree", rot=-6.0), K(1.75, "B_tree", rot=0.0),
             K(2.60, "B_tree"), K(3.55, "B_tree", k=1.1), K(3.75, "B_tree", k=1.1), K(3.95, "B_droop", k=0.9, ease="out"),
             K(4.65, "B_droop", k=0.9), K(5.40, "B_droop", k=0.85), K(5.75, "B_droop", k=0.85), K(6.05, "B_tree", k=1.0),
             K(8.15, "B_tree"), K(8.32, "B_flail", rot=-12.0, ease="out"), K(8.55, "B_flail", rot=-8.0, dy=18.0),
             K(8.75, "B_flail", rot=-11.0, dy=0.0), K(8.95, "B_flail", rot=-5.0, dy=16.0), K(9.15, "B_flail", rot=-3.0, dy=0.0),
             K(9.60, "B_tree", rot=0.0),
             K(25.10, "B_tree"), K(25.22, "B_tree", dy=-10.0), K(26.25, "B_tree", rot=-92.0, dy=0.0, ease="in"),
             K(26.40, "B_tree", rot=-88.0), K(27.10, "B_tree", rot=-88.0), K(28.00, "B_tree", rot=0.0),
             K(34.87, "B_tree"), K(35.05, "B_two", dy=24.0, ease="out"), K(35.25, "B_two", dy=0.0),
             K(35.80, "B_two"), K(36.50, "B_tree"),
             K(46.35, "B_tree"), K(46.60, "B_tree", rot=-6.0), K(46.90, "B_tree", rot=2.5), K(47.20, "B_tree", rot=-3.0),
             K(47.45, "B_tree", rot=0.0),
             K(48.70, "B_tree"), K(48.86, "B_two", dy=40.0, ease="out"), K(49.10, "B_two", dy=0.0),
             K(51.55, "B_two"), K(52.10, "B_sad"), K(52.40, "B_sad"), K(54.80, "B_sad", x=1260.0, walk=1.0, ease="lin")]
        # C : bleu, au fond à gauche, le guerrier
        C = [K(0.0, "C_war", x=200.0, y=BACK, s=depth_scale(BACK)),
             K(0.68, "C_war"), K(0.82, "C_flinch", ease="out"), K(1.60, "C_war"),
             K(2.60, "C_war"), K(3.55, "C_war", k=1.1), K(3.75, "C_war", k=1.1), K(3.95, "C_noodle", k=0.9, ease="out"),
             K(4.65, "C_noodle", k=0.9), K(5.40, "C_noodle", k=0.85), K(5.75, "C_noodle", k=0.85), K(6.05, "C_war", k=1.0),
             K(32.00, "C_war"), K(32.30, "C_noodle", ease="out"), K(35.80, "C_noodle"), K(36.50, "C_war"),
             K(42.30, "C_war"), K(42.45, "C_flinch", dy=40.0, ease="out"), K(42.70, "C_flinch", dy=0.0),
             K(43.40, "C_flinch"), K(43.90, "C_sad"), K(44.05, "C_sad"), K(46.10, "C_sad", x=-170.0, walk=1.0, ease="lin")]
        # D : jaune, au fond à droite, sur la tête (pivot au sol, côté gauche de la tête)
        D = [K(0.0, "D_head", x=690.0, y=BACK, s=depth_scale(BACK), px=-40.0, py=0.0),
             K(0.68, "D_head"), K(0.95, "D_head", rot=-6.0), K(1.30, "D_head", rot=4.0), K(1.70, "D_head", rot=0.0),
             K(2.60, "D_head"), K(3.55, "D_head", k=1.1), K(3.75, "D_head", k=1.1), K(3.95, "D_head", k=0.9, ease="out"),
             K(5.75, "D_head", k=0.88), K(6.05, "D_head", k=1.0),
             K(9.15, "D_head"), K(9.35, "D_head", rot=-7.0), K(9.65, "D_head", rot=-12.0), K(10.05, "D_heap", rot=0.0, ease="in"),
             K(10.70, "D_heap"), K(11.50, "D_head"),
             K(33.05, "D_head"), K(33.30, "D_V", ease="out"), K(35.80, "D_V"), K(36.50, "D_head"),
             K(48.70, "D_head"), K(48.84, "D_head", rot=-8.0), K(49.20, "D_heap", rot=0.0, ease="in"),
             K(51.55, "D_heap"), K(52.30, "D_sad"), K(52.45, "D_sad"),
             K(55.00, "D_sad", x=1260.0, walk=1.0, ease="lin")]
        # T : la professeure
        st = dict(x=540.0, y=DAIS, s=depth_scale(DAIS))
        T = [K(0.0, "T_seat", **st),
             K(2.60, "T_seat"), K(3.50, "T_seat_up", k=1.08), K(3.75, "T_seat_up", k=1.08), K(3.95, "T_seat", k=0.93, ease="out"),
             K(4.65, "T_seat", k=0.93), K(5.40, "T_seat", k=0.95), K(5.75, "T_seat", k=0.95), K(6.05, "T_seat", k=1.0),
             K(10.05, "T_seat"), K(10.35, "T_seat_shh"), K(11.00, "T_seat_shh"), K(11.20, "T_seat"),
             K(11.75, "T_stand"),
             K(12.80, "T_stand", x=480.0, y=1250.0, s=depth_scale(1250.0), walk=1.0, ease="lin"),
             K(13.90, "T_stand", x=392.0, y=1430.0, s=depth_scale(1430.0), walk=1.0, ease="lin"),
             K(14.02, "T_step", walk=0.0), K(14.30, "T_step"), K(14.42, "T_stand", walk=1.0),
             K(15.00, "T_stand", x=408.0, y=TDEPTH, s=depth_scale(TDEPTH), walk=1.0, ease="lin"),
             K(15.05, "T_stand", walk=0.0), K(15.30, "T_crouch", x=500.0 - CROUCH_DX)]
        T.append(("MAT", 15.30, 23.00))          # pendant ce temps, elle suit le tapis
        T += [K(16.00, "T_crouch"), K(16.35, "T_crouch_ok"), K(17.35, "T_crouch_ok"),
              K(17.45, "T_crouch", dy=22.0, ease="out"), K(17.65, "T_crouch", dy=0.0), K(18.25, "T_crouch"),
              K(18.35, "T_crouch", dy=16.0, ease="out"), K(18.50, "T_crouch", dy=0.0), K(19.00, "T_crouch"),
              K(19.35, "T_crouch_ok"), K(20.35, "T_crouch_ok"), K(20.43, "T_crouch", dy=-10.0, ease="out"),
              K(20.75, "T_crouch", dy=0.0),
              K(23.00, "T_crouch", x=500.0 - CROUCH_DX), K(23.40, "T_stand"),
              K(24.30, "T_stand", x=330.0, y=1250.0, s=depth_scale(1250.0), walk=1.0, ease="lin"),
              K(25.30, "T_stand", x=540.0, y=DAIS, s=depth_scale(DAIS), walk=1.0, ease="lin"),
              K(25.40, "T_stand", walk=0.0), K(25.85, "T_seat"),
              K(26.03, "T_seat"), K(26.30, "T_seat_shh2"), K(27.10, "T_seat_shh2"), K(27.50, "T_seat"),
              K(28.00, "T_seat"), K(29.10, "T_seat_up", k=2.0), K(29.55, "T_seat_up", k=2.05, shake=2.0),
              K(30.00, "T_seat_up", k=2.05, shake=2.0),
              K(30.18, "T_slump", k=0.72, shake=0.0, bun=65.0, ease="out"), K(30.60, "T_slump", k=0.72),
              K(31.30, "T_seat", k=0.95, bun=25.0, shake=2.5), K(32.00, "T_seat", shake=3.0),
              K(33.05, "T_seat", k=0.97, shake=5.0), K(34.00, "T_seat", k=1.0, shake=7.0), K(34.87, "T_seat", shake=9.0),
              K(35.15, "T_stand", shake=0.0, bun=0.0, ease="out"),
              K(35.80, "T_stand"), K(36.20, "T_armup"), K(36.95, "T_armup"), K(37.35, "T_sweep_r"),
              K(40.30, "T_sweep_r"), K(40.75, "T_point_b"), K(42.20, "T_point_b"), K(42.60, "T_stand"),
              K(43.20, "T_stand"), K(43.50, "T_point_c"), K(44.70, "T_point_c"), K(45.10, "T_stand"),
              K(49.60, "T_stand"), K(49.72, "T_shh", ease="out"), K(51.00, "T_shh"), K(51.35, "T_shh_sl"),
              K(52.10, "T_shh_sr"), K(52.40, "T_shh"), K(53.10, "T_shh_look"), K(53.35, "T_shh_look"),
              K(53.85, "T_sad"), K(54.20, "T_sad", y=1090.0, s=depth_scale(1090.0)),
              K(56.40, "T_sad", x=-170.0, walk=1.0, ease="lin")]
        self.TR = {"A": Track(A), "B": Track(B), "C": Track(C), "D": Track(D)}
        mat_seg = [k for k in T if k[0] == "MAT"][0]
        self.T_mat = (mat_seg[1], mat_seg[2])
        self.TR["T"] = Track([k for k in T if k[0] != "MAT"])
        # sursauts : la classe bondit un peu à chaque « Bounce », sauf quand le jeu fige tout
        self.jolt_off = {n: [] for n in "ABCDT"}
        for n in "ABCD":
            self.jolt_off[n] += [(36.9, 48.65)]
        self.jolt_off["T"] += [(14.9, 23.2), (28.0, 30.7), (48.6, 99.0)]
        self.jolt_off["B"] += [(24.0, 28.1)]
        # frissons pendant le jeu (ils tiennent)
        self.trem = {"A": [(38.6, 39.4, 2.5), (45.4, 46.3, 4.0)], "B": [(38.6, 39.4, 3.0)],
                     "C": [(38.6, 39.4, 3.0)], "D": [(38.6, 39.4, 3.0), (47.25, 48.3, 4.0)], "T": []}

    def fig_state(self, n, t):
        pose, v = self.TR[n](t)
        if n == "T" and self.T_mat[0] <= t <= self.T_mat[1] + 1e-9:
            v["x"] = mat_x(t) - CROUCH_DX
        # sursaut aux « Bounce »
        if not any(a <= t <= b for (a, b) in self.jolt_off[n]):
            j = 0.0
            for (th, tag) in self.hits:
                age = t - th
                if 0.0 <= age < 0.5:
                    g = 1.0 if th > 1.0 else 2.4
                    j = max(j, g * 22.0 * math.sin(math.pi * min(1.0, age / 0.32)) * (1.0 if age < 0.32 else 0.0))
            v["dy"] += j
        for (a, b, amp) in self.trem[n]:
            if a <= t <= b:
                v["shake"] += amp * math.sin(math.pi * (t - a) / (b - a))
        if v["rock"] > 0:
            v["rot"] += v["rock"] * 9.0 * math.sin(2 * math.pi * 1.1 * t)
        return pose, v

    def fig_points(self, n, t):
        """Les points de la figure n à l'instant t, en coordonnées de l'image, plus ce qu'il faut
        pour la dessiner."""
        pose, v = self.fig_state(n, t)
        pts = {j: list(p) for j, p in pose.items() if j != "fing"}
        k = v["k"]
        # gonflement : le tronc s'élargit, la tête et les bras montent un peu
        if abs(k - 1.0) > 1e-3:
            lift = (k - 1.0) * (34.0 if n != "T" else 30.0)
            for j in ("nek", "hed", "le", "lh", "re", "rh"):
                pts[j][1] += lift if n != "D" else -lift * 0.3
            for j in ("le", "lh", "re", "rh"):
                pts[j][0] *= 1.0 + (k - 1.0) * 0.6
        # la marche
        if v["walk"] > 1e-3:
            ph = 2 * math.pi * 1.9 * t
            a = v["walk"]
            for side, sg in (("l", 1.0), ("r", -1.0)):
                s = math.sin(ph) * sg
                pts[side + "f"][0] += a * 26.0 * s
                pts[side + "f"][1] += a * max(0.0, 16.0 * math.cos(ph) * sg)
                pts[side + "k"][0] += a * 12.0 * s
                pts[side + "h"][0] -= a * 18.0 * s
            for j in ("pel", "nek", "hed", "le", "lh", "re", "rh"):
                pts[j][1] += a * 5.0 * abs(math.sin(ph))
        # rotation autour du pivot
        rot = math.radians(v["rot"])
        if abs(rot) > 1e-6:
            c, s_ = math.cos(rot), math.sin(rot)
            px, py = v["px"], v["py"]
            for j in pts:
                x, y = pts[j][0] - px, pts[j][1] - py
                pts[j] = [px + x * c - y * s_, py + x * s_ + y * c]
        sx = v["shake"] * math.sin(t * 61.0) + v["shake"] * 0.5 * math.sin(t * 97.0)
        X0, Y0, sc = v["x"] + sx, v["y"], v["s"]
        dy = v["dy"]
        out = {j: (X0 + sc * p[0], Y0 - sc * (p[1] + dy)) for j, p in pts.items()}
        return out, pose["fing"], v, sc, rot

    # ---------------------------------------------------------- Bounce
    def resolve_contacts(self):
        res = []
        for (t, kind, x, y, tag) in self.C:
            if kind == "S" and x is None:
                x = mat_x(t)
            if tag == "head":
                x, y = self.head_contact(t)
            res.append((t, kind, x, y, tag))
        self.C = res
        self.CT = [c[0] for c in res]

    def head_contact(self, t):
        pts, _f, v, sc, _r = self.fig_points("T", t)
        hx, hy = pts["hed"]
        return float(hx), float(hy - HEAD_R["T"] * sc * 1.58 - R)

    def back_contact(self, t):
        pts, _f, v, sc, _r = self.fig_points("T", t)
        pel, nek = np.array(pts["pel"]), np.array(pts["nek"])
        mid = pel * 0.45 + nek * 0.55
        u = (nek - pel) / np.linalg.norm(nek - pel)
        nrm = np.array([u[1], -u[0]])            # perpendiculaire, côté du dos (en haut à gauche)
        if nrm[1] > 0:
            nrm = -nrm
        half = 0.5 * lerp(SHAPE["T"][2], SHAPE["T"][1], 0.55) * sc
        p = mid + nrm * (half + R)
        return float(p[0]), float(p[1])

    def contact_point(self, c):
        t, kind, x, y, tag = c
        if tag == "head":
            return x, y + R
        return x, y + R

    def ball(self, t):
        C = self.C
        if t <= C[0][0]:
            return C[0][2], C[0][3]
        if t >= C[-1][0]:
            return C[-1][2], C[-1][3]
        i = max(0, int(np.searchsorted(self.CT, t, side="right")) - 1)
        i = min(i, len(C) - 2)
        a, b = C[i], C[i + 1]
        T = b[0] - a[0]
        u = t - a[0]
        x = lerp(a[2], b[2], u / T)
        vy = (b[3] - a[3] - 0.5 * G * T * T) / T
        y = a[3] + vy * u + 0.5 * G * u * u
        # le tapis se creuse : la balle s'y enfonce un peu
        for c in (a, b):
            if c[1] == "S":
                d = abs(t - c[0])
                if d < 0.08:
                    y += 16.0 * (1 - d / 0.08)
        return x, y

    def dent(self, t):
        """(x, profondeur) du creux du tapis de Bounce."""
        best = (mat_x(t), 0.0)
        for c in self.C:
            if c[1] == "S" and abs(t - c[0]) < 0.09:
                best = (c[2], 16.0 * (1 - abs(t - c[0]) / 0.09))
        return best

    # ---------------------------------------------------------- API du moteur
    def step(self, dt):
        self.t += dt
        evs = []
        while self.hit_i < len(self.hits) and self.hits[self.hit_i][0] <= self.t + 1e-9:
            evs.append(("hit", self.hits[self.hit_i][1]))
            self.hit_i += 1
        if not self.payoff and self.t >= PAYOFF_T - 1e-9:
            self.payoff = True
            self.outcome = "PEACE"
            evs.append(("payoff", "PEACE"))
        if self.t >= END_T - self.cfg["end_hold_s"] - 1e-9:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def hero_mood(self):
        return "win"

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        Q = lambda v: v * S
        self.draw_room(dr, t, S)
        # les tapis
        self.draw_mat(dr, S, 200.0, BACK, MATC["C"], depth_scale(BACK), 1.25)
        self.draw_mat(dr, S, 690.0, BACK, MATC["D"], depth_scale(BACK), 1.0)
        self.draw_mat(dr, S, 115.0, FRONT, MATC["A"], FS, 1.4)
        self.draw_mat(dr, S, 830.0, FRONT, MATC["B"], FS, 0.95)
        dx, dd = self.dent(t)
        self.draw_mat(dr, S, mat_x(t), FRONT, MATC["Z"], FS, 1.0, dent=(dx, dd))
        # les personnages, du fond vers l'avant ; Bounce à sa profondeur
        order = []
        for n in "ABCDT":
            pts, fing, v, sc, rot = self.fig_points(n, t)
            if v["x"] < -260 or v["x"] > 1340:
                continue
            order.append((v["y"] - (0.5 if n == "T" else 0.0), n, (pts, fing, v, sc, rot)))
        order.append((FRONT + 0.1, "ball", None))
        order.sort(key=lambda o: o[0])
        bx, by = self.ball(t)
        for (_d, n, data) in order:
            if n == "ball":
                base.ball(dr, Q(bx), Q(by), Q(R))
            else:
                self.draw_figure(dr, S, n, *data)
        self.draw_rings(dr, t, S)

    def draw_room(self, dr, t, S):
        Q = lambda v: v * S
        dr.rectangle([0, 0, Q(W), Q(WALLY)], fill=WALL)
        # deux grands panneaux au mur
        for x0 in (40.0, 760.0):
            dr.rectangle([Q(x0), Q(470), Q(x0 + 280), Q(980)], fill=WALL2)
        # la fenêtre ronde et la lune
        mx, my, mr = MOON
        dr.ellipse([Q(mx - mr - 18), Q(my - mr - 18), Q(mx + mr + 18), Q(my + mr + 18)], fill=(70, 56, 90))
        dr.ellipse([Q(mx - mr), Q(my - mr), Q(mx + mr), Q(my + mr)], fill=(18, 24, 52))
        for (sx, sy, sr) in ((450, 560, 3), (612, 530, 2.5), (640, 720, 3), (468, 730, 2), (575, 770, 2.5), (676, 610, 2)):
            dr.ellipse([Q(sx - sr), Q(sy - sr), Q(sx + sr), Q(sy + sr)], fill=(200, 205, 230))
        dr.ellipse([Q(mx - 70 - 40), Q(my - 70 - 20), Q(mx - 70 + 70), Q(my - 70 + 90)], fill=(236, 232, 210))
        dr.ellipse([Q(mx - 112), Q(my - 82), Q(mx - 82), Q(my - 52)], fill=(214, 208, 186))
        dr.ellipse([Q(mx - 60), Q(my - 40), Q(mx - 44), Q(my - 24)], fill=(214, 208, 186))
        dr.line([Q(mx - mr), Q(my), Q(mx + mr), Q(my)], fill=(70, 56, 90), width=int(Q(8)))
        dr.line([Q(mx), Q(my - mr), Q(mx), Q(my + mr)], fill=(70, 56, 90), width=int(Q(8)))
        # le sol : parquet en perspective
        dr.rectangle([0, Q(WALLY), Q(W), Q(H)], fill=FLOOR)
        vx, vy = 540.0, 250.0
        for k in range(-9, 10):
            xb = 540.0 + k * 150.0
            # droite du point de fuite vers xb au bas de l'image
            def at(y):
                return vx + (xb - vx) * (y - vy) / (H - vy)
            dr.line([Q(at(WALLY)), Q(WALLY), Q(at(H)), Q(H)], fill=FLOOR_L, width=int(Q(3)))
        for (y, off) in ((1075, 0), (1135, 0), (1215, 0), (1320, 0), (1450, 0), (1610, 0), (1800, 0)):
            dr.line([0, Q(y), Q(W), Q(y)], fill=dim(FLOOR_L, 1.05), width=int(Q(2)))
        dr.rectangle([0, Q(WALLY - 22), Q(W), Q(WALLY)], fill=(24, 18, 36))
        # l'estrade et son coussin
        dr.rectangle([Q(400), Q(DAIS - 6), Q(680), Q(DAIS + 22)], fill=(150, 110, 76))
        dr.rectangle([Q(400), Q(DAIS + 22), Q(680), Q(DAIS + 34)], fill=(104, 74, 50))
        dr.ellipse([Q(460), Q(DAIS - 22), Q(620), Q(DAIS + 6)], fill=(110, 58, 132))

    def draw_mat(self, dr, S, x, y, col, sc, wk, dent=None):
        Q = lambda v: v * S
        yb, yf = y - 52 * sc, y + 58 * sc
        hb, hf = 64 * sc * wk, 78 * sc * wk
        n = 24
        top, bot = [], []
        for i in range(n + 1):
            u = i / n
            xb_ = x - hb + 2 * hb * u
            xf_ = x - hf + 2 * hf * u
            db = df = 0.0
            if dent is not None and dent[1] > 0:
                db = dent[1] * 0.5 * max(0.0, 1 - abs(xb_ - dent[0]) / 90.0) ** 2
                df = dent[1] * max(0.0, 1 - abs(xf_ - dent[0]) / 90.0) ** 2
            top.append((Q(xb_), Q(yb + db)))
            bot.append((Q(xf_), Q(yf + df)))
        dr.polygon(top + bot[::-1], fill=col)
        edge = [(px, py + Q(9)) for (px, py) in bot]
        dr.polygon(bot + edge[::-1], fill=dim(col, 0.62))

    def draw_figure(self, dr, S, n, pts, fing, v, sc, rot):
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
        sh_l = nek + nrm * (wt_ / 2 - 12 * sc) * 1.0
        sh_r = nek - nrm * (wt_ / 2 - 12 * sc)
        if n == "C":
            sh_l, sh_r = nek + nrm * (wt_ / 2 - 16 * sc), nek - nrm * (wt_ / 2 - 16 * sc)
        hip_l = pel + nrm * max(14 * sc, wb_ / 2 - 18 * sc)
        hip_r = pel - nrm * max(14 * sc, wb_ / 2 - 18 * sc)
        if n == "C":
            hip_l, hip_r = pel + nrm * 12 * sc, pel - nrm * 12 * sc
        # quel côté est « gauche » à l'image : celui dont le coude est le plus à gauche
        if np.dot(np.array(pts["le"]) - nek, nrm) < 0:
            sh_l, sh_r = sh_r, sh_l
        if np.dot(np.array(pts["lk"]) - pel, nrm) < 0:
            hip_l, hip_r = hip_r, hip_l
        lw_leg, lw_arm = 30 * sc, 24 * sc

        def limb_line(a, b, c, w):
            ptsl = [Q(a), Q(b), Q(c)]
            dr.line(ptsl, fill=limb, width=max(2, int(w * S)), joint="curve")
            for p in (a, b, c):
                r = w / 2 * S
                dr.ellipse([p[0] * S - r, p[1] * S - r, p[0] * S + r, p[1] * S + r], fill=limb)
        limb_line(hip_l, pts["lk"], pts["lf"], lw_leg)
        limb_line(hip_r, pts["rk"], pts["rf"], lw_leg)
        # le tronc
        if kind == "oval":
            c = (pel + nek) / 2
            a_ = L / 2 + 22 * sc
            b_ = wt_ / 2
            poly = [Q(c + u * a_ * math.cos(th) + nrm * b_ * math.sin(th)) for th in np.linspace(0, 2 * math.pi, 28)]
        else:
            poly = [Q(pel + nrm * wb_ / 2), Q(nek + nrm * wt_ / 2 + u * 6 * sc), Q(nek - nrm * wt_ / 2 + u * 6 * sc),
                    Q(pel - nrm * wb_ / 2)]
            if wb_ < 30 * sc:   # le triangle du guerrier : pointe en bas, arrondie
                poly = [Q(pel - u * 10 * sc), Q(nek + nrm * wt_ / 2 + u * 6 * sc), Q(nek - nrm * wt_ / 2 + u * 6 * sc)]
        dr.polygon(poly, fill=col)
        limb_line(sh_l, pts["le"], pts["lh"], lw_arm)
        limb_line(sh_r, pts["re"], pts["rh"], lw_arm)
        # la tête (et le chignon de la professeure)
        hr = HEAD_R[n] * sc
        hx, hy = hed
        if n == "T":
            up = hed - nek
            up = up / (np.linalg.norm(up) + 1e-9)
            ba = math.radians(v["bun"])
            c_, s_ = math.cos(ba), math.sin(ba)
            up = np.array([up[0] * c_ - up[1] * s_, up[0] * s_ + up[1] * c_])
            bx_, by_ = hed + up * hr * 1.08
            br = hr * 0.5
            dr.ellipse([(bx_ - br) * S, (by_ - br) * S, (bx_ + br) * S, (by_ + br) * S], fill=dim(col, 0.86))
        dr.ellipse([(hx - hr) * S, (hy - hr) * S, (hx + hr) * S, (hy + hr) * S], fill=col)
        # l'index levé (chut, ou pointé)
        for side, on in (("rh", fing[0]), ("lh", fing[1])):
            if on > 0.5:
                el = np.array(pts["re" if side == "rh" else "le"])
                hd = np.array(pts[side])
                d = hd - el
                d = d / (np.linalg.norm(d) + 1e-9)
                tip = hd + d * 52 * sc
                dr.line([Q(hd), Q(tip)], fill=limb, width=max(2, int(15 * sc * S)))
                r = 7.5 * sc * S
                dr.ellipse([tip[0] * S - r, tip[1] * S - r, tip[0] * S + r, tip[1] * S + r], fill=limb)

    def draw_rings(self, dr, t, S):
        for (th, cx, cy, big, tag) in self.rings:
            age = t - th
            if age < 0 or age > 1.3:
                continue
            rmax = 1500.0 if big else (1100.0 if tag.startswith("far") else (420.0 if tag == "edge" else 820.0))
            dur = 1.15 if big else 0.85
            u = age / dur
            if u >= 1:
                continue
            r = R + (rmax - R) * (1 - (1 - u) ** 2)
            k = (1 - u) ** 1.4
            w = (12 if big else 8) * (1 - 0.6 * u)
            col = mix(BG, (255, 255, 255), 0.85 * k)
            dr.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=col, width=max(1, int(w * S)))


DEFAULTS = {
    "ball_r": R, "gravity": G,
    "hook_text_s": 2.8, "hook_top": 0.09, "hook_font_size": 92,
    "narrator_voice": TEACHER_VOICE, "narrator_length": 1.0, "narr_gap_s": 0.08,
    "sub_y": 0.262, "sub_font_size": 66, "sub_words": 4,
    "watermark_y": 0.955, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True,
    "hero_win": "Yes!",
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
