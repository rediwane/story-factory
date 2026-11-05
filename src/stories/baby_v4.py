"""
Prototype « baby » v4 : Bounce est la balle du bébé, laissée dans son lit. Sur le matelas il se tait ;
chaque fois qu'il touche du bois (le panneau du lit, un jouet du mobile), il dit son nom et un anneau
part vers le bébé, qui se réveille d'un cran. Derrière le lit, la porte : la lumière du couloir passe
dans la fente quand Maman passe. Elle finit par entrer : « Who woke you up? » — le bébé montre la
balle : « BOUNCE! » — Maman vire au rouge… et comprend : « His first word! ». Le bébé redit
« BOUNCE! », Bounce répond.

v4 (après le verdict à l'aveugle de la v3) : cadrage 1,3× plus serré (le monde est dessiné dans une
image plus grande puis recadré), un événement neuf toutes les 3-4 s au début, la mère présente par
la lumière dès 10 s, le rendormissement devient une tension, colère qui va droit au rouge, 4 s de
récompense après « His first word! ».

Une seule scène, plan fixe ; Bounce suit une liste de contacts reliés par des arcs balistiques sous
une gravité unique (G = 2600 px/s², en coordonnées du monde) ; les autres acteurs suivent des pistes
à images clés. Les voix de Maman et du bébé viennent d'une banque hors dépôt (BANK_DIR).

    python3 src/stories/baby_v4.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import dim, font
from PIL import Image, ImageDraw
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lot6/baby/final"

# ------------------------------------------------------------------ voix des personnages
BANK_FILES = {"Everything okay?": "ok.wav", "Who woke you up?": "who.wav", "BOUNCE!": "baby.wav",
              "His first word!": "first.wav"}
BANK = {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr = w.getnframes(), w.getframerate()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if fr != SR:
        idx = np.arange(0, len(x) - 1, fr / SR)
        x = np.interp(idx, np.arange(len(x)), x)
    return x


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK_FILES:
        if text not in BANK:
            d = os.environ.get("BABY_V4_BANK", BANK_DIR)
            BANK[text] = _read(os.path.join(d, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

# ------------------------------------------------------------------ le mot de Bounce, stable
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.72:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ l'accroche : plus vive, coupée net
_orig_hook_audio = base.hook_audio
_hook_memo = {}


def quick_hook_audio(cfg):
    key = cfg.get("hook_text")
    if key not in _hook_memo:
        v = _orig_hook_audio(cfg)
        if v is not None:
            v = np.asarray(v, float)
            e = np.abs(v)
            idx = np.where(e > 0.04 * e.max())[0]
            if len(idx):
                v = v[max(0, idx[0] - int(0.01 * SR)):min(len(v), idx[-1] + int(0.03 * SR))].copy()
            # la voix du TTS varie d'une prise à l'autre : on accélère juste assez pour finir à temps
            f = max(cfg.get("hook_speed", 1.1), len(v) / SR / cfg.get("hook_max_s", 1.12))
            v = base.pitch(v, f)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = quick_hook_audio

# ------------------------------------------------------------------ cadrage : monde -> écran
W, H = 1080, 1920
K = 1.3                           # zoom du cadrage
OX, OY = 240.0 * K - 126.0, 895.0 * K - 1000.0   # monde (240, 895) -> écran (126, 1000)


def to_screen(x, y):
    return x * K - OX, y * K - OY


# ------------------------------------------------------------------ géométrie (coordonnées du monde)
G = 2600.0
R = 105.0                         # rayon de Bounce (136 px à l'écran)
FL = 1385.0                       # plancher
MT = 1000.0                       # dessus du matelas
MY = MT - R
PANEL = (200.0, 240.0)
RPOST = (840.0, 880.0)
KNOB_Y = 622.0
RAIL_Y = 680.0
PG_X = PANEL[1] + R
PG_Y = {"pgl": 875.0, "pgm": 805.0, "pgh": 740.0}
HUB = (400.0, 470.0)
ARM_R = 70.0
STRING = 60.0
TOY_R = 26.0
TOY_Y = HUB[1] + STRING
MOB_Y = TOY_Y + TOY_R + R
DOOR = (600.0, 820.0, 520.0, FL)  # x0 (côté poignée), x1 (gonds), y0, y1
SLIT = 18.0
SIGN_C = (712.0, 612.0)
SIGN_W, SIGN_H = 240.0, 100.0
BS = 1.85

# couleurs
BG = (8, 8, 12)
WALL = (22, 26, 52)
WALL_D = (16, 18, 38)
FLOOR_C = (52, 36, 32)
FLOOR_L = (70, 50, 42)
WOOD = (150, 104, 70)
WOOD_D = (96, 66, 46)
DRAWER = (124, 86, 60)
MATT = (226, 228, 238)
SUIT = (242, 228, 150)
SUIT_D = (206, 190, 112)
BLANKET = (150, 206, 178)
BLANKET_D = (110, 160, 138)
SKIN = (242, 190, 160)
SKIN_D = (200, 140, 112)
PACI = (110, 190, 240)
ZCOL = (196, 176, 255)
WARM = (255, 214, 140)
SIL = (24, 20, 26)
TEAL = (64, 168, 164)
JOY = (255, 158, 186)          # joie : rose clair, distinct du bébé jaune et de la porte ambrée
ANGER = [(0.0, TEAL), (0.25, (196, 92, 88)), (0.5, (216, 60, 50)), (0.8, (196, 38, 34)), (1.0, (166, 22, 22))]
TOYS = [((255, 214, 70), "star"), ((170, 200, 255), "moon"), ((236, 236, 246), "cloud")]
CREAM = (238, 230, 204)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def lerp(a, b, k):
    return a + (b - a) * k


def ramp(stops, v):
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if v <= b:
            return mix(ca, cb, (v - a) / max(1e-6, b - a))
    return stops[-1][1]


class KF:
    """Valeur scalaire à images clés : liste de (t, v) ; transitions lissées."""

    def __init__(self, v0, keys=()):
        self.keys = [(-1e9, v0)] + sorted(keys)
        self.ts = [k[0] for k in self.keys]

    def __call__(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        if i >= len(self.keys) - 1:
            return self.keys[-1][1]
        t0, v0 = self.keys[i]
        t1, v1 = self.keys[i + 1]
        if t0 < -1e8:
            return v0
        return lerp(v0, v1, smooth((t - t0) / max(1e-6, t1 - t0)))


def steps(v0, pts, d=0.15):
    keys, cur = [], v0
    for (t, v) in pts:
        keys += [(t, cur), (t + d, v)]
        cur = v
    return keys


def hop(t, hops):
    y = 0.0
    for (t0, h) in hops:
        T = 2 * math.sqrt(2 * h / G)
        u = t - t0
        if 0 <= u <= T:
            y = max(y, h - 0.5 * G * (u - T / 2) ** 2)
    return y


# ------------------------------------------------------------------ le plan
END = 61.2
ISSUE = 57.0
HITS = [
    (1.45, "pgl", 1.0), (2.95, "pgl", 0.45), (4.50, "pgm", 1.1),
    (6.30, "mob", 1.15), (7.40, "pgm", 1.0), (8.25, "pgl", 0.8), (10.50, "pgh", 1.25), (12.60, "mob", 0.9),
    (13.50, "pgm", 0.6), (14.90, "pgm", 1.0), (17.15, "mob", 1.3), (18.20, "pgm", 0.9), (19.10, "mob", 0.95),
    (20.50, "pgl", 0.75),
    (22.10, "pgm", 0.9), (25.65, "pgh", 1.35),
    (27.45, "pgm", 0.85), (29.25, "mob", 0.5), (30.85, "pgl", 0.5), (32.35, "pgl", 0.5), (33.75, "mob", 0.55),
    (35.05, "pgl", 0.5),
    (37.25, "pgm", 0.9), (38.45, "mob", 1.0), (39.50, "mob", 1.05), (40.45, "mob", 1.1), (41.30, "pgh", 1.15),
    (42.15, "mob", 1.2), (43.45, "pgh", 1.4),
    (44.30, "pgm", 0.95), (45.10, "mob", 0.95), (46.05, "mob", 1.0), (46.85, "pgh", 1.0), (47.70, "mob", 0.9),
    (49.75, "pgl", 0.8),
    (51.85, "pgm", 0.9), (52.65, "pgm", 0.95), (53.50, "pgh", 1.0), (54.30, "pgm", 1.05), (55.10, "pgh", 1.1),
    (56.00, "pgh", 1.4),
    (59.25, "pgm", 0.8),
]
SOFT = [(0.35, 380, 22), (22.75, 382, 18), (23.45, 376, 16), (24.15, 382, 13), (24.85, 378, 10),
        (51.30, 380, 20), (60.70, 380, 18)]
LINES = [(23.10, "Everything okay?", "ok"), (48.70, "Who woke you up?", "who"), (50.75, "BOUNCE!", "b"),
         (ISSUE, "His first word!", "first"), (58.60, "BOUNCE!", "b2")]
LINE_WHO = {"ok": "mom_off", "who": "mom", "b": "baby", "first": "mom", "b2": "baby"}
APPROACH = (37.4, 43.4)           # Bounce se rapproche du bébé qui dort


def soft_x(t, k=0):
    if APPROACH[0] <= t <= APPROACH[1]:
        return 380.0 + 110.0 * (t - APPROACH[0]) / (APPROACH[1] - APPROACH[0])
    return 376.0 + 8 * (k % 2)


class Mobile:
    """Le mobile : vitesse de rotation relancée à chaque coup, amortie ; l'étoile se décroche."""
    STAR_OFF = 19.1

    def __init__(self, kicks):
        self.dt = 1 / 240
        n = int((END + 2) / self.dt)
        self.phi = np.zeros(n)
        self.sp = np.zeros(n)
        ph, om, sp = 0.4, 0.0, 0.0
        ks = sorted(kicks)
        j = 0
        for i in range(n):
            t = i * self.dt
            while j < len(ks) and ks[j][0] <= t:
                om = om + ks[j][1]
                j += 1
            om *= math.exp(-0.45 * self.dt)
            if abs(om) < 0.05:
                om = 0.0
            ph += om * self.dt
            sp += (clamp01(abs(om) / 7.0) - sp) * min(1.0, 2.2 * self.dt)
            self.phi[i], self.sp[i] = ph, sp

    def toys(self, t):
        i = max(0, min(len(self.phi) - 1, int(t / self.dt)))
        ph, spread = self.phi[i], self.sp[i]
        beta = 1.2 * spread
        rr = ARM_R + STRING * math.sin(beta)
        out = []
        for k in range(3):
            if k == 0 and t >= self.STAR_OFF:
                continue
            a = ph + k * 2 * math.pi / 3
            z = math.sin(a)
            out.append((k, HUB[0] + rr * math.cos(a), HUB[1] + STRING * math.cos(beta), z,
                        TOYS[k][0], TOYS[k][1], HUB[0] + ARM_R * math.cos(a)))
        return out


class Plan:
    def __init__(self):
        kicks = [(t, 1.2 + 4.5 * g) for (t, k, g) in HITS if k == "mob"]
        self.mob = Mobile(kicks)
        cs = []
        for (t, kind, g) in HITS:
            if kind == "mob":
                toys = self.mob.toys(t - 1e-3)
                pref = 455.0 if APPROACH[0] <= t <= APPROACH[1] else 400.0
                tx = min(toys, key=lambda a: abs(a[1] - pref) - 0.3 * a[3])[1]
                x = max(345.0, min(455.0, tx))
                cs.append({"t": t, "x": x, "y": MOB_Y, "axis": "y", "soft": False, "gain": g, "kind": kind})
            else:
                cs.append({"t": t, "x": PG_X, "y": PG_Y[kind], "axis": "x", "soft": False, "gain": g, "kind": kind})
        for (t, x, dent) in SOFT:
            cs.append({"t": t, "x": float(x), "y": MY + dent, "axis": "y", "soft": True, "gain": 0, "kind": "mat"})
        # le mobile se touche en montant et se quitte en descendant : un saut mou juste avant et juste après
        for (t, kind, g) in HITS:
            if kind == "mob":
                for dtm in (-0.36, 0.36):
                    tt = t + dtm
                    if not any(abs(c["t"] - tt) < 0.3 for c in cs):
                        cs.append({"t": tt, "x": soft_x(tt), "y": MY + 16, "axis": "y", "soft": True, "gain": 0,
                                   "kind": "mat"})
        cs.sort(key=lambda c: c["t"])
        start = {"t": -0.37, "x": 380.0, "y": MY + 18}
        full = []
        prev = start
        k = 0
        for c in cs:
            if prev.get("kind") == "pgh" and c["t"] - prev["t"] > 0.8:
                k += 1
                early = {"t": prev["t"] + 0.45, "x": soft_x(prev["t"] + 0.45, k), "y": MY + 16, "axis": "y",
                         "soft": True, "gain": 0, "kind": "mat"}
                full.append(early)
                prev = early
            gap = c["t"] - prev["t"]
            n = max(1, math.ceil(gap / 0.74))
            for j in range(1, n):
                tt = prev["t"] + gap * j / n
                k += 1
                full.append({"t": tt, "x": soft_x(tt, k), "y": MY + 16, "axis": "y", "soft": True,
                             "gain": 0, "kind": "mat"})
            full.append(c)
            prev = c
        self.contacts = full
        self.start = start
        self.after = {"t": 61.45, "x": 380.0, "y": MY + 18}
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in full if not c["soft"]]
        self.ts = [c["t"] for c in full]

    def seg(self, t):
        cs = self.contacts
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else cs[i - 1]
        b = self.after if i >= len(cs) else cs[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        T = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / T
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def squash(self, t):
        sx = sy = 1.0
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.contacts[i:i + 4]:
            u = t - c["t"]
            if -0.06 <= u <= 0.14:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / 0.14)
                amp = 0.1 if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def ball(self, t):
        x, y = self.pos(t)
        sx, sy = self.squash(t)
        return x, y, R * sx, R * sy


# ------------------------------------------------------------------ le bébé : poses à articulations
# x du monde, y relatif au dessus du matelas (négatif = plus haut) ; les poses couchées ont la tête à droite
_LYING = {
    "lie": {"hip": (790, -50), "sh": (650, -52), "head": (577, -62), "h1": (690, -92), "h2": (706, -80),
            "f1": (852, -44), "f2": (846, -62)},
    "armup": {"hip": (790, -50), "sh": (650, -54), "head": (577, -64), "h1": (640, -245), "h2": (706, -82),
              "f1": (852, -44), "f2": (846, -62)},
    "headup": {"hip": (790, -50), "sh": (655, -70), "head": (588, -130), "h1": (700, -130), "h2": (710, -84),
               "f1": (790, -190), "f2": (846, -62)},
    "side": {"hip": (782, -62), "sh": (650, -64), "head": (577, -72), "h1": (612, -78), "h2": (626, -52),
             "f1": (808, -26), "f2": (826, -44)},
    "thumb": {"hip": (782, -62), "sh": (650, -64), "head": (577, -72), "h1": (586, -60), "h2": (626, -52),
              "f1": (808, -26), "f2": (826, -44)},
    "curl": {"hip": (752, -126), "sh": (650, -58), "head": (590, -56), "h1": (622, -16), "h2": (652, -18),
             "f1": (784, -18), "f2": (806, -22)},
    "fours": {"hip": (762, -140), "sh": (644, -136), "head": (580, -176), "h1": (642, -12), "h2": (664, -12),
              "f1": (772, -12), "f2": (798, -12)},
}
POSES = {n: {k: (1351 - v[0], v[1]) for k, v in p.items()} for n, p in _LYING.items()}
POSES.update({
    # endormi sur le côté, en boule, tout à droite (laisse la place à Bounce qui s'approche)
    "nap": {"hip": (650, -60), "sh": (722, -66), "head": (796, -74), "h1": (760, -58), "h2": (748, -44),
            "f1": (612, -24), "f2": (628, -40)},
    "sit": {"hip": (712, -52), "sh": (712, -205), "head": (712, -282), "h1": (664, -122), "h2": (760, -122),
            "f1": (630, -18), "f2": (652, -12)},
    "half": {"hip": (716, -170), "sh": (712, -305), "head": (712, -382), "h1": (688, -322), "h2": (746, -322),
             "f1": (690, -14), "f2": (746, -14)},
    "stand": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (688, -322), "h2": (746, -322),
              "f1": (696, -10), "f2": (740, -10)},
    "grab": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (688, -322), "h2": (724, -400),
             "f1": (696, -10), "f2": (740, -10)},
    "down": {"hip": (712, -205), "sh": (708, -340), "head": (708, -416), "h1": (672, -222), "h2": (748, -222),
             "f1": (694, -10), "f2": (738, -10)},
    "reach": {"hip": (714, -205), "sh": (716, -340), "head": (718, -416), "h1": (690, -480), "h2": (742, -490),
              "f1": (696, -10), "f2": (740, -10)},
    "point": {"hip": (714, -205), "sh": (708, -340), "head": (704, -416), "h1": (556, -300), "h2": (746, -322),
              "f1": (696, -10), "f2": (740, -10)},
    "up": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (664, -520), "h2": (764, -520),
           "f1": (696, -10), "f2": (740, -10)},
})
POSES["lifted"] = {k: (v[0] - 24, v[1] - 140) for k, v in POSES["up"].items()}

BABY_KEYS = [(0.0, "lie", 0.0), (1.6, "armup", 0.15), (3.0, "lie", 0.8), (4.7, "headup", 0.2), (5.4, "lie", 0.5),
             (7.5, "side", 0.3), (12.8, "thumb", 0.5), (15.0, "side", 0.3), (17.3, "curl", 0.45),
             (25.9, "fours", 0.35), (31.1, "sit", 0.45), (34.0, "half", 0.6), (36.5, "sit", 0.3),
             (36.9, "nap", 0.5), (43.6, "grab", 0.25), (44.0, "stand", 0.3), (45.9, "down", 0.25),
             (46.85, "reach", 0.3), (47.7, "stand", 0.3), (50.75, "point", 0.2), (51.6, "stand", 0.4),
             (56.1, "up", 0.4), (58.0, "lifted", 0.6)]
BABY_HOPS = [(44.30, 40), (47.70, 45), (50.75, 55), (52.65, 22), (54.30, 22), (56.2, 30), (56.85, 30)]
BABY_JOLTS = [(1.6, 16), (4.65, 10), (7.45, 12), (10.55, 14), (14.95, 10), (17.2, 12), (19.2, 10), (25.8, 14),
              (41.3, 12), (51.85, 6)]
BABY_MOVES = [(1.75, 2.7, 3, 14, "trem"), (4.9, 5.5, 3, 14, "trem"), (7.8, 10.4, 7, 2.6, "wig"),
              (10.6, 11.8, 18, 3.2, "kick"), (15.1, 17.0, 6, 2.2, "wig"), (17.75, 18.9, 7, 1.6, "rock"),
              (26.2, 27.45, 10, 1.4, "rock"), (27.45, 31.0, 17, 1.6, "rock"), (31.5, 34.0, 9, 0.8, "sway"),
              (35.0, 36.4, 10, 2.4, "wob")]
BABY_DIR = KF(0.0, [(28.3, 0.0), (28.6, -1.0), (31.1, -1.0), (31.4, 0.0), (32.4, 0.0), (32.7, -1.0),
                    (36.5, -1.0), (36.9, 0.0), (45.1, 0.0), (45.35, 1.0), (47.4, 1.0), (47.7, -1.0),
                    (56.1, -1.0), (56.4, -0.5)])


class Baby:
    def __init__(self):
        self.ts = [k[0] for k in BABY_KEYS]

    def joints(self, t):
        i = max(0, bisect.bisect_right(self.ts, t) - 1)
        t0, name, d = BABY_KEYS[i]
        prev = POSES[BABY_KEYS[i - 1][1]] if i > 0 else POSES[name]
        cur = POSES[name]
        k = smooth((t - t0) / d) if d > 0 else 1.0
        J = {j: (lerp(prev[j][0], cur[j][0], k), lerp(prev[j][1], cur[j][1], k)) for j in cur}
        upper_dx, feet_dy, all_dx, all_dy = 0.0, 0.0, 0.0, 0.0
        for (a, b, amp, f, kind) in BABY_MOVES:
            if a <= t <= b:
                env = math.sin(math.pi * (t - a) / (b - a))
                s = math.sin(2 * math.pi * f * (t - a))
                if kind == "trem":
                    all_dx += amp * math.sin(t * 90.0)
                elif kind == "wig":
                    upper_dx += amp * s * env
                    all_dy += 0.5 * amp * abs(s) * env
                elif kind == "kick":
                    feet_dy += amp * abs(s) * env
                elif kind == "rock":
                    upper_dx += amp * s
                else:
                    upper_dx += amp * s * env
        jy = 0.0
        for (tj, amp) in BABY_JOLTS:
            u = t - tj
            if 0 <= u <= 0.3:
                jy += amp * math.sin(math.pi * u / 0.3)
        lift = hop(t, BABY_HOPS) + jy
        out = {}
        for j, (x, y) in J.items():
            yy = MT + y - lift - all_dy
            xx = x + all_dx
            if j in ("sh", "head", "h1", "h2"):
                xx += upper_dx
            if j in ("f1", "f2"):
                yy -= feet_dy * (1.0 if j == "f1" else 0.6)
            out[j] = (xx, yy)
        out["dir"] = BABY_DIR(t)
        out["upright"] = name in ("sit", "half", "stand", "grab", "down", "reach", "point", "up", "lifted")
        return out


# ------------------------------------------------------------------ les Z
class Zs:
    def __init__(self, burst_times):
        sp = []
        t = -2.4
        while t < 43.6:
            if t < 7.5:
                s, per = 1.0, 0.9
            elif t < 12.8:
                s, per = 0.6, 1.2
            elif t < 15.0:
                s, per = 0.8, 0.9           # il se calme : le réveil peut échouer
            elif t < 17.2:
                s, per = 0.5, 1.2
            elif t < 25.9:
                s, per = 0.5, 1.1
            elif t < 31.1:
                s, per = 0.36, 1.0
            elif t < 37.0:
                s, per = 0.3, 2.6
            else:                            # il se rendort : les Z grossissent
                s, per = 0.45 + 0.9 * clamp01((t - 37.0) / 6.0), 0.95
            sp.append((t, s))
            t += per
        self.spawns = sp
        self.bursts = burst_times
        self.life = 2.4

    def visible(self, t, head):
        out = []
        if t >= 43.6:
            return out
        for (ts, size) in self.spawns:
            age = t - ts
            if age < 0 or age > self.life:
                continue
            b = [tb for tb in self.bursts if ts < tb <= t]
            k = age / self.life
            x = head[0] - 20 + 50 * k * size + 14 * math.sin(ts * 3.1 + age * 2.2)
            y = head[1] - 70 - 200 * k
            alpha = clamp01(age / 0.3) * clamp01((self.life - age) / 0.6)
            if 25.9 <= ts < 31.1:
                alpha *= 0.55 + 0.45 * (math.sin(t * 17.0 + ts) > 0)
            fs = (40 + 44 * k) * size + 18
            if b:
                u = t - b[-1]
                if u > 0.35:
                    continue
                ang = ts * 2.7
                x += math.cos(ang) * 200 * u / 0.35
                y += math.sin(ang) * 160 * u / 0.35 - 60 * u
                alpha *= 1 - u / 0.35
                fs *= 1 + 0.6 * u / 0.35
            out.append((x, y, fs, alpha))
        return out


# ------------------------------------------------------------------ scène
def arc_point(p0, p1, t0, T, t):
    u = clamp01((t - t0) / T) * T
    vx = (p1[0] - p0[0]) / T
    vy = (p1[1] - p0[1]) / T - 0.5 * G * T
    return p0[0] + vx * u, p0[1] + vy * u + 0.5 * G * u * u


class Scene:
    def __init__(self):
        self.P = Plan()
        self.B = Baby()
        reach = [t + 0.15 for (t, g, x, y, k) in self.P.hits if g >= 0.6 and not (36.9 < t < 43.4)]
        self.Z = Zs(reach)
        # porte (derrière le lit, à droite) : ouverture, lumière du couloir, poignée, ombre de quelqu'un
        self.door_o = KF(0.18, [(0.0, 0.18), (0.9, 0.0), (46.45, 0.0), (46.8, 1.0)])
        self.hall = KF(1.0, [(0.85, 1.0), (1.0, 0.0), (10.0, 0.0), (10.15, 1.0), (11.2, 1.0), (11.35, 0.0),
                             (16.0, 0.0), (16.15, 1.0), (17.25, 1.0), (17.4, 0.0),
                             (21.6, 0.0), (21.75, 1.0), (25.25, 1.0), (25.4, 0.0), (43.7, 0.0), (43.85, 1.0)])
        self.handle = KF(0.0, [(24.6, 0.0), (24.8, 40.0), (24.95, 40.0), (25.1, 0.0),
                               (45.6, 0.0), (46.2, 48.0), (46.45, 48.0)])
        # ombres dans la fente : (arrivée, installée, départ, partie) ; la première ne fait que passer
        self.shadows = [(10.2, 10.5, 10.6, 10.95), (16.3, 16.5, 16.9, 17.15), (22.4, 22.7, 25.0, 25.3),
                        (44.6, 44.9, 46.5, 46.6)]
        # Maman
        self.mom_vis = KF(0.0, [(46.5, 0.0), (46.55, 1.0)])
        self.mom_col = KF(0.0, [(47.0, 0.0), (47.6, 1.0)])
        self.mom_x = KF(640.0, [(47.0, 640.0), (48.3, 560.0), (51.4, 560.0), (52.0, 500.0), (56.1, 500.0),
                                (56.7, 565.0)])
        self.mom_dir = KF(-1.0, [(48.0, -1.0), (48.4, 1.0), (51.4, 1.0), (52.0, -1.0), (56.1, -1.0), (56.6, 1.0)])
        self.mom_lean = KF(0.0, [(48.3, 0.0), (48.8, 12.0), (51.4, 12.0), (52.0, -14.0), (53.5, -14.0),
                                 (53.9, -20.0), (56.1, -20.0), (56.6, 0.0), (58.0, 0.0), (58.6, 10.0)])
        anger = [(51.85, 0.25), (52.65, 0.45), (53.5, 0.62), (54.3, 0.78), (55.1, 0.9), (56.0, 1.0), (ISSUE, 0.0)]
        self.mom_anger = KF(0.0, steps(0.0, anger, 0.14))
        self.mom_joy = KF(0.0, [(ISSUE, 0.0), (ISSUE + 0.12, 1.0)])
        self.mom_hops = [(51.3, 22), (ISSUE + 0.05, 60)]
        self.mom_arms = [(46.5, "hang"), (48.3, "rail"), (ISSUE, "up"), (58.0, "lift")]
        # la feuille, scotchée sur la porte : rotation autour du coin gauche après 14,9 s ; arrachée à 43,6 s
        self.sign_rot = KF(-6.0, [(13.5, -6.0), (13.65, -4.0), (14.9, -4.0), (15.2, 22.0), (15.6, 10.0),
                                  (16.1, 16.0), (16.7, 13.0), (42.15, 13.0), (42.4, 24.0), (42.8, 10.0),
                                  (43.2, 18.0)])
        self.sign_fall = (43.75, 44.5)
        self.paci_t = 7.4
        self.blanket_t = 11.2
        self.rings = [(t, g, x, y) for (t, g, x, y, k) in self.P.hits]
        self.subs = []

    def set_narr(self, narr):
        out = []
        for i, n in enumerate(narr):
            words = len(n["text"].split())
            end = max(n["end"] + 0.45, n["start"] + 0.5 + 0.3 * words)
            if i + 1 < len(narr):
                end = min(end, narr[i + 1]["start"] - 0.05)
            out.append((LINE_WHO.get(n["key"], "mom"), n["text"], n["start"], end))
        self.subs = out


class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_times = [h[0] for h in self.sc.P.hits]
        self.hi = 0
        self.lines = list(LINES)
        self.replies = []

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_times) and self.hit_times[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= END - 1e-9:
            self.done = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t0):
        for (th, g, _x, _y, _k) in self.sc.P.hits:
            if abs(th - t0) < 0.02:
                return g
        return 0.9

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        """Le monde est dessiné à l'échelle S·K dans une image plus grande, puis recadré sur l'écran."""
        t = float(t)
        sc = self.sc
        Sw = S * K
        wimg = Image.new("RGB", (int((W + OX) * S) + 2, int((H + OY) * S) + 2), BG)
        wd = ImageDraw.Draw(wimg)
        self.draw_room(wd, t, Sw)
        self.draw_door(wd, t, Sw)
        self.draw_sign(wimg, wd, t, Sw, falling=False)
        self.draw_light_wall(wd, t, Sw)
        self.draw_mobile(wd, t, Sw)
        self.draw_mom(wd, t, Sw, body=True)
        self.draw_crib_back(wd, t, Sw)
        self.draw_mom(wd, t, Sw, body=False)
        self.draw_sign(wimg, wd, t, Sw, falling=True)
        self.draw_floor(wd, t, Sw)
        self.draw_light_floor(wd, t, Sw)
        bx, by, brx, bry = sc.P.ball(t)
        J = sc.B.joints(t)
        self.draw_crib_front(wd, t, Sw, bx, by, bry)
        self.draw_rings(wd, t, Sw)
        self.draw_baby(wd, t, Sw, J)
        self.draw_paci(wd, t, Sw, J)
        self.draw_star(wd, t, Sw)
        for (zx, zy, fs, a) in sc.Z.visible(t, J["head"]):
            if a <= 0.02:
                continue
            wd.text((zx * Sw, zy * Sw), "Z", fill=mix(WALL, ZCOL, a), anchor="mm", font=font(fs * Sw))
        # Bounce, par-dessus tout
        if t >= ISSUE:
            base.HERO["expr"] = "win"
        if abs(brx - bry) < 0.5:
            base.ball(wd, bx * Sw, by * Sw, brx * Sw)
        else:
            self.draw_ball(wd, bx, by, brx, bry, Sw)
        crop = wimg.crop((int(OX * S), int(OY * S), int(OX * S) + W * S, int(OY * S) + H * S))
        dr._image.paste(crop, (0, 0))
        self.draw_subs(dr, t, S)

    def draw_ball(self, dr, x, y, rx, ry, S):
        r = max(rx, ry)
        size = int(2 * r * 1.7 * S) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO["pos"]
        base.ball(ld, size / 2, size / 2, R * S)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size * rx / R)), max(2, int(size * ry / R))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        dr._image.paste(layer, (int(x * S - nw / 2), int(y * S - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (x * S, y * S)

    # -------- décor
    def draw_room(self, dr, t, S):
        rect(dr, 0, 0, 1000, FL, WALL, S)
        rect(dr, 0, 0, 1000, 150, WALL_D, S)
        dr.line([0, 150 * S, 1000 * S, 150 * S], fill=(34, 40, 76), width=int(8 * S))
        for k in range(46):
            x = 130 + (k * 211) % 860
            y = 190 + (k * 137) % 900
            dr.polygon(poly(star_pts(x, y, 6), S), fill=(34, 40, 74))
        dr.line([HUB[0] * S, 150 * S, HUB[0] * S, HUB[1] * S], fill=(170, 170, 190), width=int(4 * S))

    def draw_floor(self, dr, t, S):
        rect(dr, 0, FL, 1000, 1620, FLOOR_C, S)
        yb = FL + 18
        for k in range(8):
            dr.line([0, yb * S, 1000 * S, yb * S], fill=FLOOR_L, width=int(3 * S))
            yb += 20 + 8 * k
        ell(dr, 560, 1520, 380, 80, (92, 80, 128), S)
        ell(dr, 560, 1520, 320, 60, (110, 96, 150), S)
        for (cx, cy, c) in ((790, 1440, (200, 90, 80)), (850, 1462, (90, 150, 200)), (815, 1400, (220, 190, 80))):
            rect(dr, cx - 24, cy - 24, cx + 24, cy + 24, c, S, r=5)
            rect(dr, cx - 13, cy - 13, cx + 13, cy + 13, dim(c, 0.78), S, r=3)
        tb = (150, 110, 80)
        ell(dr, 260, 1450, 50, 54, tb, S)
        ell(dr, 260, 1375, 36, 34, tb, S)
        ell(dr, 232, 1350, 12, 12, tb, S); ell(dr, 288, 1350, 12, 12, tb, S)

    def draw_light_floor(self, dr, t, S):
        """Le filet de lumière sous la porte, son éventail sur le plancher, et les pieds qui le coupent."""
        o, h = self.sc.door_o(t), self.sc.hall(t)
        if h < 0.05:
            return
        x0, x1 = DOOR[0], DOOR[1]
        col = mix(FLOOR_C, (226, 178, 104), h)
        if o < 0.05:
            rect(dr, x0 + 4, FL - 9, x1 - 4, FL, mix((20, 18, 22), WARM, h), S)
            dr.polygon(poly([(x0, FL), (x1, FL), (x1 + 40, FL + 46), (x0 - 40, FL + 46)], S), fill=col)
            ks = self.shadow_k(t)
            if ks > 0.02:
                # deux pieds : ils glissent pendant le passage, se posent pendant l'arrêt
                off = 0.0
                for (ta, tb_, tc, td) in self.sc.shadows:
                    if ta <= t <= td:
                        off = -90 + 180 * clamp01((t - ta) / (td - ta)) if (tc - tb_) < 0.2 else 0.0
                for fx in (x0 + 50, x0 + 120):
                    rect(dr, fx + off, FL - 9, fx + off + 44, FL + 40, mix(col, (16, 12, 14), ks), S)
        else:
            left = self.door_left(t)
            reach = 260 * min(1.0, o * 1.3)
            dr.polygon(poly([(x0, FL), (left, FL), (left - 40, FL + 60), (x0 - 40 - reach, FL + 60)], S),
                       fill=mix(FLOOR_C, (226, 178, 104), 0.8 * h))

    def door_left(self, t):
        o = self.sc.door_o(t)
        return DOOR[0] + SLIT + (DOOR[1] - DOOR[0] - SLIT) * o

    def shadow_k(self, t):
        k = 0.0
        for (ta, tb_, tc, td) in self.sc.shadows:
            k = max(k, clamp01((t - ta) / (tb_ - ta)) * (1 - clamp01((t - tc) / (td - tc))))
        return k

    def draw_door(self, dr, t, S):
        x0, x1, y0, y1 = DOOR
        sc = self.sc
        o, h = sc.door_o(t), sc.hall(t)
        rect(dr, x0 - 12, y0 - 12, x1 + 12, y1, WOOD_D, S)
        light = mix((26, 22, 26), mix(WARM, (214, 132, 64), clamp01(o * 1.5)), h)
        rect(dr, x0, y0, x1, y1, light, S)
        left = self.door_left(t)
        # l'ombre de quelqu'un derrière la porte : elle coupe la fente
        ks = self.shadow_k(t)
        if ks > 0.02 and o < 0.05 and h > 0.05:
            rect(dr, x0, 760, left, 1000, mix(light, (14, 12, 14), ks), S)
            rect(dr, x0, 700, left, 760, mix(light, (14, 12, 14), 0.6 * ks), S)
        # silhouette de Maman dans l'embrasure
        if sc.mom_vis(t) > 0.5 and sc.mom_col(t) < 0.02:
            self.mom_shape(dr, t, S, 640.0, SIL, 0.78, 0.0, 0.0, -0.3, body=True, sil=True)
        if x1 - left > 2:
            rect(dr, left, y0, x1, y1, (84, 60, 48), S)
            if x1 - left > 80:
                rect(dr, left + 18, y0 + 24, x1 - 18, y0 + 200, (96, 70, 56), S)
                rect(dr, left + 18, y0 + 236, x1 - 18, y1 - 30, (96, 70, 56), S)
            if o < 0.3:
                ang = math.radians(sc.handle(t))
                px, py = left + 48, 800.0
                ex, ey = px - 50 * math.cos(ang), py + 50 * math.sin(ang)
                ell(dr, px, py, 13, 13, (60, 46, 36), S)
                capsule(dr, (px, py), (ex, ey), 10, (236, 222, 178), S)
                ell(dr, px, py, 7, 7, (200, 186, 140), S)

    def draw_light_wall(self, dr, t, S):
        o = self.sc.door_o(t)
        h = self.sc.hall(t)
        if h < 0.05:
            return
        x0 = DOOR[0]
        if o < 0.05:
            # une lueur sur le mur, à gauche de la fente
            for i, w in enumerate((70, 40, 18)):
                col = mix(WALL, (214, 168, 96), h * (0.14 + 0.14 * i))
                dr.polygon(poly([(x0 - 10, DOOR[2] + 10), (x0 - 10 - w, DOOR[2] + 60), (x0 - 10 - w, 1000),
                                 (x0 - 10, 1000)], S), fill=col)
            return
        left = self.door_left(t)
        col = mix(WALL, (110, 98, 96), h * min(1.0, o * 1.3))
        dr.polygon(poly([(x0, DOOR[2] + 30), (250, 700), (250, 1000), (x0, 1000)], S), fill=col)

    def draw_sign(self, img, dr, t, S, falling):
        sc = self.sc
        is_fall = t >= sc.sign_fall[0]
        if is_fall != falling:
            return
        if sc.door_o(t) > 0.05:
            return
        simg, pad = sign_image(S)
        ang = sc.sign_rot(t)
        px, py = SIGN_C[0] - SIGN_W / 2, SIGN_C[1] - SIGN_H / 2
        if t < 14.9:
            cx, cy = SIGN_C
        else:
            ar = math.radians(ang)
            dx, dy = SIGN_W / 2, SIGN_H / 2
            cx, cy = px + dx * math.cos(ar) - dy * math.sin(ar), py + dx * math.sin(ar) + dy * math.cos(ar)
        if 43.6 <= t < sc.sign_fall[0]:
            cx += 10 * (t - 43.6) / 0.15
        if is_fall:
            u = clamp01((t - sc.sign_fall[0]) / (sc.sign_fall[1] - sc.sign_fall[0]))
            cy += 520 * u * u
            cx += 30 * math.sin(u * 6)
            ang += 50 * u
            if cy > MT + 40:
                return
        rot = simg.rotate(-ang, resample=Image.BICUBIC, expand=True)
        img.paste(rot, (int(cx * S - rot.width / 2), int(cy * S - rot.height / 2)), rot)
        if not is_fall:
            ar = math.radians(ang)

            def corner(dx, dy):
                return (cx + dx * math.cos(ar) - dy * math.sin(ar), cy + dx * math.sin(ar) + dy * math.cos(ar))
            tapes = [corner(-SIGN_W / 2 + 8, -SIGN_H / 2 + 4)]
            if t < 14.9:
                lift = 1.0 if t < 13.5 else 0.5
                tapes.append(corner(SIGN_W / 2 - 8, -SIGN_H / 2 + 4 - 8 * (1 - lift)))
            for (x, y) in tapes:
                dr.polygon(poly([(x - 22, y - 7), (x + 22, y - 12), (x + 24, y + 6), (x - 20, y + 10)], S),
                           fill=(214, 208, 180))

    def draw_crib_back(self, dr, t, S):
        dr.rectangle([PANEL[1] * S, (RAIL_Y - 8) * S, RPOST[0] * S, (RAIL_Y + 8) * S], fill=WOOD_D)
        for k in range(13):
            x = PANEL[1] + 22 + k * 46
            dr.line([x * S, (RAIL_Y + 8) * S, x * S, MT * S], fill=WOOD_D, width=int(6 * S))

    def draw_crib_front(self, dr, t, S, bx, by, bry):
        rect(dr, PANEL[0], KNOB_Y, PANEL[1], FL, WOOD, S)
        rect(dr, PANEL[0] + 6, 660, PANEL[1] - 6, MT - 10, (166, 118, 82), S)
        rect(dr, RPOST[0], KNOB_Y, RPOST[1], FL, WOOD, S)
        for kx in ((PANEL[0] + PANEL[1]) / 2, (RPOST[0] + RPOST[1]) / 2):
            ell(dr, kx, KNOB_Y - 10, 24, 24, WOOD, S)
        # le cadre sous le matelas ; dessous, on voit le bas de la porte
        rect(dr, PANEL[1], MT + 34, RPOST[0], MT + 76, WOOD, S)
        if t >= self.sc.blanket_t + 0.6:
            dr.rounded_rectangle([660 * S, (MT - 6) * S, 830 * S, (MT + 90) * S], radius=18 * S, fill=BLANKET)
            dr.line([680 * S, (MT + 34) * S, 810 * S, (MT + 38) * S], fill=BLANKET_D, width=int(4 * S))
        self.draw_soft(dr, PANEL[1], RPOST[0], MT, MT + 34, MATT, (180, 184, 200), bx, by, bry, S)

    def draw_soft(self, dr, x0, x1, top, bottom, col, col_d, bx, by, bry, S):
        pts = []
        n = 60
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = top
            dxb = x - bx
            if abs(dxb) < R * 1.05:
                circ_y = by + math.sqrt(max(0.0, (R * 1.05) ** 2 - dxb * dxb))
                y = max(y, min(bottom - 4, circ_y))
            pts.append((x, y))
        dr.polygon(poly(pts + [(x1, bottom), (x0, bottom)], S), fill=col)
        dr.line(poly(pts, S), fill=col_d, width=int(4 * S))

    def draw_rings(self, dr, t, S):
        for (t0, g, x, y) in self.sc.rings:
            u = t - t0
            if u < 0 or u > 1.2:
                continue
            rmax = (50 + 260 * g) if g < 0.6 else (190 + 900 * g)
            r = 26 + 1450 * u
            if r > rmax:
                continue
            k = 1 - r / rmax
            inten = k * (0.35 + 0.65 * min(1.0, g))
            col = mix(WALL, (246, 246, 255), inten)
            w = (4 + 8 * min(1.3, g)) * (0.5 + 0.5 * k)
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(1, int(w * S)))

    def draw_mobile(self, dr, t, S):
        dr.line([(HUB[0] - ARM_R) * S, HUB[1] * S, (HUB[0] + ARM_R) * S, HUB[1] * S], fill=(200, 200, 214),
                width=int(6 * S))
        ell(dr, HUB[0], HUB[1], 16, 8, (220, 220, 232), S)
        toys = sorted(self.sc.P.mob.toys(t), key=lambda a: a[3])
        for (k, x, y, z, col, shape, xa) in toys:
            c = mix(WALL, col, 0.72 + 0.28 * (z + 1) / 2)
            dr.line([xa * S, HUB[1] * S, x * S, (y - TOY_R) * S], fill=(170, 170, 190), width=int(2 * S))
            rr = TOY_R * (0.9 + 0.1 * z)
            draw_toy(dr, shape, x, y, rr, c, S)
        # le fil cassé de l'étoile
        if t >= Mobile.STAR_OFF:
            dr.line([(HUB[0] - ARM_R) * S, HUB[1] * S, (HUB[0] - ARM_R + 6) * S, (HUB[1] + 22) * S],
                    fill=(170, 170, 190), width=int(2 * S))

    def draw_star(self, dr, t, S):
        t0 = Mobile.STAR_OFF
        if t < t0:
            return
        p0 = (HUB[0] - 20.0, TOY_Y)
        land = (560.0, FL + 30)
        if t < t0 + 0.9:
            x, y = arc_point(p0, land, t0, 0.9, t)
            a = (t - t0) * 9
        else:
            x, y, a = land[0], land[1], 0.3
        dr.polygon(poly(star_pts(x, y, 30, a), S), fill=TOYS[0][0])

    # -------- bébé
    def draw_baby(self, dr, t, S, J):
        LR = 9 * BS
        TR = 27 * BS
        HR = 32 * BS
        sc = self.sc
        breath = 1.0 + 0.04 * math.sin(2 * math.pi * t / 2.3)
        for f in ("f1", "f2"):
            capsule(dr, J["hip"], J[f], LR * 1.15, SUIT_D, S)
            ell(dr, J[f][0], J[f][1], LR * 1.25, LR * 1.25, SUIT, S)
        capsule(dr, J["hip"], J["sh"], TR * breath, SUIT, S)
        bt = sc.blanket_t
        if t < bt + 0.7:
            k = smooth((t - bt) / 0.7)
            c0 = ((J["hip"][0] + J["sh"][0]) / 2 - 30, (J["hip"][1] + J["f1"][1]) / 2)
            c1 = (745.0, MT + 40)
            cx, cy = lerp(c0[0], c1[0], k), lerp(c0[1], c1[1], k)
            dr.rounded_rectangle([(cx - 120) * S, (cy - 40) * S, (cx + 120) * S, (cy + 40 - 10 * k) * S],
                                 radius=30 * S, fill=BLANKET)
        for hnd in ("h1", "h2"):
            capsule(dr, J["sh"], J[hnd], LR, SUIT_D, S)
            ell(dr, J[hnd][0], J[hnd][1], LR * 1.15, LR * 1.15, SKIN, S)
        hx, hy = J["head"]
        ell(dr, hx, hy, HR, HR, SKIN, S)
        vx, vy = hx - J["sh"][0], hy - J["sh"][1]
        n = math.hypot(vx, vy) + 1e-6
        ux, uy = vx / n, vy / n
        d = J["dir"]
        px, py = -uy, ux
        if J["upright"]:
            px, py = 1.0, 0.0
        tip = (hx + ux * HR * 0.95 + px * d * HR * 0.45, hy + uy * HR * 0.95 + py * d * HR * 0.45)
        c2 = (tip[0] + ux * 26 + px * d * 26, tip[1] + uy * 26 + py * d * 26)
        c3 = (c2[0] - ux * 4 + px * d * 14, c2[1] - uy * 4 + py * d * 14 + 12)
        dr.line(poly([tip, c2, c3], S), fill=SKIN_D, width=int(9 * S), joint="curve")
        if J["upright"] and abs(d) > 0.2:
            ell(dr, hx + d * HR * 0.62, hy + HR * 0.18, HR * 0.2, HR * 0.14, (236, 160, 150), S)
        self._baby = J

    def draw_paci(self, dr, t, S, J):
        hx, hy = J["head"]
        HR = 32 * BS
        face = (hx, hy - HR * 0.85)
        t0 = self.sc.paci_t
        land = (600.0, FL + 22)
        if t < t0:
            x, y, a = face[0], face[1], 0.0
        elif t < t0 + 0.8:
            x, y = arc_point(face, land, t0, 0.8, t)
            a = (t - t0) * 12
        else:
            u = smooth((t - t0 - 0.8) / 1.6)           # elle roule sur le plancher
            x, y, a = land[0] + 120 * u, land[1], 1.2 + 4.0 * u
        ca, sa = math.cos(a), math.sin(a)

        def Pp(u_, v):
            return (x + u_ * ca - v * sa, y + u_ * sa + v * ca)
        shield = [Pp(26 * math.cos(k * math.pi / 8), 11 * math.sin(k * math.pi / 8)) for k in range(16)]
        dr.polygon(poly(shield, S), fill=PACI)
        cx, cy = Pp(0, -20)
        dr.ellipse([(cx - 14) * S, (cy - 14) * S, (cx + 14) * S, (cy + 14) * S], outline=PACI, width=int(6 * S))

    # -------- Maman
    def mom_state(self, t):
        sc = self.sc
        a = sc.mom_anger(t)
        joy = sc.mom_joy(t)
        col = ramp(ANGER, a)
        col = mix(SIL, col, sc.mom_col(t))
        col = mix(col, JOY, joy)
        return a, joy, col

    def mom_shape(self, dr, t, S, x, col, k, lean, anger, dirn, body=True, sil=False):
        """Maman, sans visage : corps arrondi, tête avec chignon (derrière) et petit nez (devant)."""
        sc = self.sc
        infl = 1.0 + 0.32 * anger
        trem = (2 + 9 * anger) * math.sin(t * 70.0) if anger > 0.05 else 0.0
        x = x + trem
        lift = 0.0 if sil else hop(t, sc.mom_hops)
        bw = 150 * k * infl
        hr = 62 * k * (1 + 0.12 * anger)
        hip_y = 798.0 + (1 - k) * 380.0 - lift
        sh_h = 330 * k
        a = math.radians(lean)
        ca, sa = math.cos(a), math.sin(a)

        def P(u, v):
            return (x + v * ca + u * sa, hip_y - u * ca + v * sa)
        if body:
            lc = dim(col, 0.8) if not sil else col
            lw = 0.3 * bw / infl
            for sx in (-1, 1):
                rect(dr, x + sx * bw * 0.22 - lw / 2, hip_y - 10, x + sx * bw * 0.22 + lw / 2, FL - lift, lc, S)
            pts = [P(0, -bw / 2)]
            for i in range(13):
                ang = math.pi * i / 12
                pts.append(P(sh_h - bw / 2 + (bw / 2) * math.sin(ang), -(bw / 2) * math.cos(ang)))
            pts.append(P(0, bw / 2))
            dr.polygon(poly(pts, S), fill=col)
            hc = P(sh_h + hr * 0.95, 0)
            bun = (hc[0] - dirn * hr * 0.92, hc[1] - hr * (0.35 + 0.55 * (1 - abs(dirn))))
            ell(dr, bun[0], bun[1], hr * 0.42, hr * 0.42, dim(col, 0.8), S)
            ell(dr, hc[0], hc[1], hr, hr, col, S)
            if abs(dirn) > 0.15:
                ell(dr, hc[0] + dirn * hr * 0.97, hc[1] + hr * 0.08, hr * 0.2, hr * 0.17, col, S)
            self._mom_head = hc
        return P(sh_h - bw * 0.35, -bw * 0.45), P(sh_h - bw * 0.35, bw * 0.45)

    def draw_mom(self, dr, t, S, body):
        sc = self.sc
        if sc.mom_col(t) <= 0.0:
            return
        a, joy, col = self.mom_state(t)
        x = sc.mom_x(t)
        lean = sc.mom_lean(t)
        d = sc.mom_dir(t)
        s1, s2 = self.mom_shape(dr, t, S, x, col, 1.0, lean, a, d, body=body)
        if body:
            return
        mode = "hang"
        for (tm, m) in sc.mom_arms:
            if t >= tm:
                mode = m
        armc = dim(col, 0.82)
        lift = hop(t, sc.mom_hops)
        if mode == "rail":
            hands = [(x - 70 + lean * 2.0, RAIL_Y - 10 - lift * 0.3), (x + 60 + lean * 2.0, RAIL_Y - 10 - lift * 0.3)]
        elif mode == "up":
            hands = [(s1[0] - 50, s1[1] - 190), (s2[0] + 50, s2[1] - 190)]
        elif mode == "lift":
            J = getattr(self, "_baby", None)
            if J:
                hands = [(J["sh"][0] - 40, J["hip"][1] - 30), (J["sh"][0] + 30, J["hip"][1] - 20)]
            else:
                hands = [(s1[0], s1[1] + 150), (s2[0], s2[1] + 150)]
        else:
            hands = [(s1[0] - 10, s1[1] + 190), (s2[0] + 10, s2[1] + 190)]
        for (s, hnd) in ((s1, hands[0]), (s2, hands[1])):
            capsule(dr, s, hnd, 15, armc, S)
            ell(dr, hnd[0], hnd[1], 18, 18, armc, S)

    # -------- sous-titres (T3), en coordonnées de l'écran
    def draw_subs(self, dr, t, S):
        for (who, text, a, b) in self.sc.subs:
            if not (a <= t <= b):
                continue
            k = clamp01((t - a) / 0.12)
            f = font(48 * S * (0.8 + 0.2 * k))
            bb = f.getbbox(text)
            tw = (bb[2] - bb[0]) / S
            if who == "mom_off":
                cx, tgt, colt = 470.0, to_screen(DOOR[0] + 8, 980.0), (130, 222, 214)
            elif who == "baby":
                J = getattr(self, "_baby", None)
                hx = to_screen(J["head"][0], 0)[0] if J else 700.0
                cx, tgt, colt = min(900 - tw / 2 - 30, max(120 + tw / 2 + 30, hx)), (hx, 1150.0), (252, 236, 150)
            else:
                mx = to_screen(self.sc.mom_x(t), 0)[0]
                _a, joy, _c = self.mom_state(t)
                colt = mix((130, 222, 214), (255, 178, 200), joy)
                cx, tgt = min(900 - tw / 2 - 30, max(120 + tw / 2 + 30, mx)), (mx, 1150.0)
            x0, x1 = cx - tw / 2 - 26, cx + tw / 2 + 26
            y0, y1 = 1196.0, 1250.0
            bxm = max(x0 + 24, min(x1 - 24, tgt[0]))
            dr.polygon(poly([(bxm - 16, y0 + 2), (bxm + 16, y0 + 2), (tgt[0], min(tgt[1], y0 - 22))], S),
                       fill=(14, 14, 22))
            rect(dr, x0, y0, x1, y1, (14, 14, 22), S, r=22)
            dr.text((cx * S, (y0 + y1) / 2 * S), text, fill=colt, anchor="mm", font=f)


# ------------------------------------------------------------------ primitives
def poly(pts, S):
    return [(x * S, y * S) for x, y in pts]


def capsule(dr, p0, p1, r, col, S):
    dr.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=col, width=max(1, int(2 * r * S)))
    for p in (p0, p1):
        dr.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)


def ell(dr, x, y, rx, ry, col, S):
    dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=col)


def rect(dr, x0, y0, x1, y1, col, S, r=0):
    if r:
        dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=col)
    else:
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)


def star_pts(x, y, r, a=0.0, n=5, k=0.45):
    pts = []
    for i in range(2 * n):
        rr = r if i % 2 == 0 else r * k
        aa = a - math.pi / 2 + i * math.pi / n
        pts.append((x + rr * math.cos(aa), y + rr * math.sin(aa)))
    return pts


def draw_toy(dr, shape, x, y, rr, c, S):
    if shape == "star":
        dr.polygon(poly(star_pts(x, y, rr + 4), S), fill=c)
    elif shape == "moon":
        ell(dr, x, y, rr, rr, c, S)
        ell(dr, x + rr * 0.45, y - rr * 0.25, rr * 0.8, rr * 0.8, WALL, S)
    else:
        ell(dr, x - rr * 0.45, y + 4, rr * 0.6, rr * 0.55, c, S)
        ell(dr, x + rr * 0.45, y + 4, rr * 0.6, rr * 0.55, c, S)
        ell(dr, x, y - 4, rr * 0.7, rr * 0.65, c, S)


_SIGN = {}


def sign_image(S):
    key = round(S, 4)
    if key in _SIGN:
        return _SIGN[key]
    w, h = int(SIGN_W * S), int(SIGN_H * S)
    pad = int(24 * S)
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([pad, pad, pad + w, pad + h], fill=CREAM + (255,))
    ink = (24, 22, 26, 255)
    f1 = font(32 * S)
    f2 = font(23 * S)
    d.text((pad + w / 2, pad + 0.27 * h), "DO NOT", fill=ink, anchor="mm", font=f1)
    d.text((pad + w / 2, pad + 0.58 * h), "WAKE HIM!", fill=ink, anchor="mm", font=f1)
    d.text((pad + 0.7 * w, pad + 0.85 * h), "— Mom", fill=(50, 50, 70, 255), anchor="mm", font=f2)
    _SIGN[key] = (img, pad)
    return _SIGN[key]


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 46.6, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.1,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 1.0,
}
LINE_GAIN = {"ok": 0.7, "who": 1.0, "b": 1.0, "first": 1.05, "b2": 1.1}


def render_audio(sim, events, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(events, total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        for (t0, kind, _d, tag) in words:
            g = sim.hit_gain(t0)
            gg = max(0.1, min(1.3, g)) ** 0.7 * 0.92
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=LINE_GAIN.get(n["key"], 1.0))
    v = cfg.get("_hook_voice")
    if v is not None:
        n = min(len(v), len(buf))
        duck = np.ones(len(buf))
        duck[:n] = 0.42
        m = min(int(0.3 * SR), len(buf) - n)
        duck[n:n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, 0.15, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.sc.set_narr(narr)
    cfg["_sim"] = sim
    hv = cfg.get("_hook_voice")
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook_end": round(0.15 + len(hv) / SR, 2) if hv is not None else None,
               "hits": sum(1 for e in events if e[1] == "hit"),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(events, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    hits = [round(e[0], 3) for e in events if e[1] == "hit"]
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [h for h in hits if h not in said]
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, events, dur, cfg, audio, narr)
        if "--audio-only" in argv:
            import shutil
            shutil.copy(audio, os.path.join(base.ROOT, "output", cfg["name"] + ".wav"))
            print(json.dumps(summary, ensure_ascii=False))
            return 0
        base.render_video(theme, sim, states, cfg, audio, out, events, ())
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, base.ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
