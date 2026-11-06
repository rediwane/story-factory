"""
Prototype « insomnia » : Insomnia (perso d'un fan, le frère de Snooze : balle verte, yeux énormes injectés,
cernes, petite bouche ronde, tasse de café) essaie de dormir. Bounce rebondit au pied de son lit : chaque
« BOUNCE » lui rouvre les yeux, alors que le matelas (mou, muet) le laisse s'endormir. Trois réveils qui
montent (le bruit, la lumière de la lampe qu'il éteint et rallume, le café qu'il lui envoie dans la bouche
en plein bâillement) ; survolté, Insomnia éclaire la chambre de ses yeux. Puis la règle se retourne : il
compte les Bounce comme des moutons (une bulle de pensée, une barrière, de petits Bounce qui sautent), et
chaque « BOUNCE » l'endort d'un cran. À un cheveu du sommeil, Bounce rebondit enfin en silence sur le
matelas : c'est le silence qui le réveille. « Insomnia. »

Tout est calculé d'avance sur une horloge (contacts, voix, états). Le monde est dessiné à l'échelle de
l'écran 1080×1920 puis mis à l'échelle de la config (aperçu 540×960). L'audio suit les instants exacts
des contacts : il est identique quel que soit le nombre d'images par seconde.

    python3 src/stories/insomnia.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import font
from PIL import Image, ImageDraw
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/insomnia/banque"

# ------------------------------------------------------------------ la voix d'Insomnia (Kokoro am_puck, vérifiée par whisper)
BANK_FILES = {"Insomnia.": "sigh.wav", "Insomnia!": "annoy.wav", "INSOMNIA!": "hyper.wav",
              "Insomniaaa...": "sleepy.wav", "Insomnia": "dead.wav"}
BANK = {}
_orig_say = narr_voice.say


def _bank_dir():
    return os.environ.get("INSOMNIA_BANK", BANK_DIR)


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
            BANK[text] = _read(os.path.join(_bank_dir(), BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

# ------------------------------------------------------------------ le mot de Bounce, stable (même prise pour l'aperçu et le final)
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(_bank_dir(), "hero_%s_%s_%s.wav" % (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"]))
    if key not in _hero_memo and os.path.exists(cache):
        _hero_memo[key] = _read(cache)
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.66:
                break
        _hero_memo[key] = best
        if best is not None:
            x = np.clip(best, -1, 1)
            with wave.open(cache, "w") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((x * 32767).astype(np.int16).tobytes())
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ l'accroche (posée par ce thème, après le 1er « BOUNCE »)
HOOK_T = 0.85
_orig_hook_audio = base.hook_audio
_hook_memo = {}


def hook_clip(cfg):
    key = cfg.get("hook_text")
    if key not in _hook_memo:
        v = _orig_hook_audio(cfg)
        if v is not None:
            v = np.asarray(v, float)
            e = np.abs(v)
            idx = np.where(e > 0.04 * e.max())[0]
            if len(idx):
                v = v[max(0, idx[0] - int(0.01 * SR)):min(len(v), idx[-1] + int(0.03 * SR))].copy()
            f = max(cfg.get("hook_speed", 1.1), len(v) / SR / cfg.get("hook_max_s", 1.1))
            v = base.pitch(v, f)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ géométrie (monde ; écran = monde × K − (OX, OY))
W, H = 1080, 1920
K = 1.1
OX, OY = 497.0 * K - 540.0, 760.0 * K - 860.0
G = 2600.0
R = 118.0                         # Bounce
RI = 135.0                        # Insomnia (disque de rayon RI, halo 1,6 RI)
IX, IY = 295.0, 960.0             # Insomnia, assis contre l'oreiller
BED_TOP = 1064.0                  # dessus de la couverture
SOFT_Y = BED_TOP - R
FOOT_X = 840.0                    # face intérieure du pied de lit
F_POS = (FOOT_X - R, 880.0)
PIVOT = (640.0, -40.0)
ROD = 620.0                       # pivot -> bas de l'abat-jour
SHADE_H = 80.0
CUP = (438.0, 1000.0, 502.0, 1068.0)   # tasse (x0, y0, x1, y1), anse à droite
C_POS = (550.0, 1006.0 - R)
PHOTO = (160.0, 560.0, 340.0, 720.0)
WINDOW = (700.0, 262.0, 880.0, 482.0)
CLOUD_C = (362.0, 372.0)
FENCE_X = 362.0
GROUND_Y = 440.0
CS = 0.86
MINI_R = 30.0

# couleurs
BG = (8, 8, 12)
NIGHT = (7, 8, 20)
WALL = (40, 46, 84)
WALL_D = (30, 34, 64)
WOOD = (150, 104, 70)
WOOD_D = (100, 68, 46)
PILLOW = (226, 228, 240)
BLANKET = (92, 106, 178)
BLANKET_D = (70, 80, 140)
MATT = (210, 210, 224)
FLOOR = (46, 34, 32)
FLOOR_L = (60, 44, 40)
RUG = (88, 66, 110)
I_BODY = (126, 200, 96)
I_RING = (56, 108, 44)
I_EYE = (226, 226, 230)
I_EDGE = (40, 70, 34)
I_BAG = (120, 108, 140)
VEIN = (196, 60, 60)
INK = (16, 14, 20)
CUPC = (244, 244, 248)
COFFEE = (110, 66, 40)
LAMP = (230, 200, 120)
LAMP_OFF = (110, 96, 70)
SKY = (16, 22, 50)
MOON = (240, 236, 200)
CLOUDC = (232, 230, 250)
CLOUD_E = (150, 146, 190)
GRASS = (120, 180, 110)
ZCOL = (196, 176, 255)
SNOOZE = (192, 192, 192)


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


class KF:
    """Courbe par images-clés (interpolation douce entre deux clés)."""

    def __init__(self, keys):
        self.keys = sorted(keys)
        self.ts = [k[0] for k in self.keys]

    def __call__(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        if i < 0:
            return self.keys[0][1]
        if i >= len(self.keys) - 1:
            return self.keys[-1][1]
        t0, v0 = self.keys[i]
        t1, v1 = self.keys[i + 1]
        return lerp(v0, v1, smooth((t - t0) / max(1e-6, t1 - t0)))


# ------------------------------------------------------------------ le plan
END = 64.07
ISSUE = 61.45
COUNT0 = 35.3                     # premier Bounce compté
NEAR_F = 46.6                     # le « BOUNCE » qui suit la quasi-collision
# contacts durs : (t, genre, gain) ; F = pied du lit, L = lampe, C = anse de la tasse
HARD = [
    (0.12, "F", 1.05), (2.75, "F", 1.0), (4.60, "F", 1.15),
    (7.90, "L", 1.1), (9.25, "L", 1.05), (10.15, "L", 1.0), (11.00, "L", 1.05), (11.85, "L", 1.0),
    (13.60, "L", 1.25),
    (15.60, "F", 0.95), (16.90, "F", 0.9), (18.10, "F", 0.85),
    (20.20, "C", 1.1),
    (21.90, "F", 1.0), (22.85, "F", 1.0), (23.80, "L", 1.1),
    (25.05, "F", 1.05), (25.90, "F", 1.0), (27.00, "F", 1.05), (27.85, "F", 1.0),
    (28.95, "F", 1.0), (30.20, "F", 0.95), (31.20, "F", 0.95), (32.45, "F", 0.95), (33.75, "F", 0.95),
    (35.30, "F", 0.9), (36.60, "F", 0.85), (38.00, "F", 0.85), (39.30, "F", 0.85),
    (41.20, "F", 0.9), (42.45, "F", 0.85), (43.80, "F", 0.85), (45.05, "F", 0.85),
    (NEAR_F, "F", 0.9),
    (49.00, "F", 0.85), (49.88, "F", 0.85), (50.90, "F", 0.85), (51.76, "F", 0.85), (52.86, "F", 0.85),
    (53.74, "F", 0.85),
    (54.95, "F", 0.9), (55.82, "F", 0.85), (56.86, "F", 0.85), (57.72, "F", 0.85), (58.70, "F", 0.85),
    (59.60, "F", 0.9),
    (63.30, "L", 1.15),
]
COUNTS = [t for (t, k, g) in HARD if COUNT0 - 1e-6 <= t <= 59.61 and k == "F"]
LINES = [(5.60, "Insomnia.", "sigh"), (14.55, "Insomnia!", "annoy"), (21.15, "INSOMNIA!", "hyper"),
         (47.55, "Insomniaaa...", "sleepy"), (62.40, "Insomnia", "dead")]
LINE_GAIN = {"sigh": 0.95, "annoy": 1.05, "hyper": 1.1, "sleepy": 0.75, "dead": 1.0}
L_HITS = [t for (t, k, g) in HARD if k == "L"]
POPS = [(0.12, 0.06, 8), (2.75, 0.18, 18), (4.60, 0.3, 28), (9.25, 0.2, 14), (11.0, 0.2, 14), (13.6, 0.35, 32),
        (15.6, 0.06, 6), (16.9, 0.04, 4), (21.0, 0.4, 36), (ISSUE, 0.42, 34)]


def apex_time(y0, y1, apex):
    """Durée d'un arc de y0 à y1 dont le sommet est en `apex` (y vers le bas)."""
    v = math.sqrt(2 * G * (y0 - apex))
    a, b, c = G / 2, -v, (y0 - y1)
    disc = b * b - 4 * a * c
    return (-b + math.sqrt(max(0.0, disc))) / (2 * a)


class Lamp:
    """La lampe suspendue : un pendule amorti que les « BOUNCE » poussent."""

    def __init__(self):
        self.dt = 1 / 240
        n = int((END + 3) / self.dt)
        self.th = np.zeros(n)
        th, om = 0.0, 0.0
        kicks = {}
        for i, t in enumerate(L_HITS):
            kicks[int(t / self.dt)] = (0.16 if i % 2 == 0 else -0.14)
        kicks[int(46.15 / self.dt)] = 0.05            # le souffle de la quasi-collision
        w2 = G / ROD
        for i in range(n):
            if i in kicks:
                om += kicks[i]
            om += (-w2 * th - 0.35 * om) * self.dt
            th += om * self.dt
            self.th[i] = th

    def theta(self, t):
        return float(self.th[max(0, min(len(self.th) - 1, int(t / self.dt)))])

    def bottom(self, t):
        a = self.theta(t)
        return PIVOT[0] + ROD * math.sin(a), PIVOT[1] + ROD * math.cos(a)


def lit_at(t):
    """1 lampe allumée, 0 éteinte ; chaque coup sur la lampe la bascule."""
    state, last = 1.0, -9.0
    for th in L_HITS:
        if th <= t:
            state, last = 1.0 - state, th
    k = clamp01((t - last) / 0.07)
    return lerp(1.0 - state, state, k)


class Plan:
    def __init__(self, lamp):
        cs = []
        for i, (t, kind, g) in enumerate(HARD):
            if kind == "F":
                x, y, ax = F_POS[0], F_POS[1], "x"
            elif kind == "L":
                bx, by = lamp.bottom(t)
                x, y, ax = bx, by + R, "y"
            else:
                x, y, ax = C_POS[0], C_POS[1], "y"
            cs.append({"t": t, "x": x, "y": y, "axis": ax, "soft": False, "gain": g, "kind": kind})
        # la quasi-collision : un rebond mou qui envoie Bounce juste sous l'abat-jour (8 px)
        bx, by = lamp.bottom(46.1)
        y_soft = SOFT_Y + 30
        apex = by + R + 8
        T = apex_time(y_soft, F_POS[1], apex)
        r = math.sqrt(2 * G * (y_soft - apex)) / G / T
        xs = (bx + 60 - F_POS[0] * r) / (1 - r)       # le sommet passe sous l'abat-jour, 60 px à droite du centre
        self.near = (NEAR_F - T, NEAR_F, round(xs, 1))
        cs.append({"t": NEAR_F - T, "x": xs, "y": y_soft, "axis": "y", "soft": True,
                   "gain": 0, "kind": "M", "nofill": True, "dent": 30})
        # la lampe se touche en montant et se quitte en descendant : un rebond mou à moins de 0,46 s de chaque côté
        ls_ = [c for c in cs if c["kind"] == "L"]
        for c0, c1 in zip(ls_, ls_[1:]):
            if c1["t"] - c0["t"] < 0.92:
                cs.append({"t": (c0["t"] + c1["t"]) / 2, "x": 652.0, "y": SOFT_Y + 16, "axis": "y", "soft": True,
                           "gain": 0, "kind": "M", "dent": 16})
        for c in ls_:
            for dtm in (-0.42, 0.42):
                tt = c["t"] + dtm
                if not any(abs(o["t"] - tt) < 0.3 or (o is not c and abs(o["t"] - c["t"]) < 0.47 and
                                                     (o["t"] - c["t"]) * dtm > 0) for o in cs):
                    cs.append({"t": tt, "x": 652.0, "y": SOFT_Y + 16, "axis": "y", "soft": True, "gain": 0,
                               "kind": "M", "dent": 16})
        cs.sort(key=lambda c: c["t"])
        # boucle : avant l'image 0, Bounce vient de la lampe (comme à la fin) ; après la fin, il va au pied du lit
        lb = lamp.bottom(0)
        start = [{"t": -0.76, "x": lb[0], "y": lb[1] + R, "axis": "y", "soft": False, "kind": "L", "gain": 0},
                 {"t": -0.34, "x": 655.0, "y": SOFT_Y + 16, "axis": "y", "soft": True, "kind": "M", "dent": 16}]
        after = [{"t": END + 0.03 + 0.12 - 0.46, "x": 655.0, "y": SOFT_Y + 16, "axis": "y", "soft": True, "kind": "M",
                  "dent": 16},
                 {"t": END + 0.03 + 0.12, "x": F_POS[0], "y": F_POS[1], "axis": "x", "soft": False, "kind": "F",
                  "gain": 0}]
        full = list(start)
        prev = start[-1]
        k = 0
        for c in cs + after:
            gap = c["t"] - prev["t"]
            if not prev.get("nofill") and not c.get("nofill"):
                n = max(1, math.ceil(gap / 0.72))
                for j in range(1, n):
                    tt = prev["t"] + gap * j / n
                    k += 1
                    x = 640.0 + 28.0 * math.sin(k * 2.3)
                    if 59.7 < tt < 63.2:          # la fin : petits rebonds au milieu du lit
                        x = 630.0 + 14.0 * math.sin(k * 1.7)
                    full.append({"t": tt, "x": x, "y": SOFT_Y + 16, "axis": "y", "soft": True, "gain": 0,
                                 "kind": "M", "dent": 16})
            full.append(c)
            prev = c
        self.contacts = sorted(full, key=lambda c: c["t"])
        self.ts = [c["t"] for c in self.contacts]
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in self.contacts
                     if not c["soft"] and 0 <= c["t"] <= END]
        self.softs = [c for c in self.contacts if c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        cs = self.contacts
        return cs[max(0, i - 1)], cs[min(len(cs) - 1, i)]

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
                amp = (0.08 + 0.004 * c.get("dent", 16)) if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def dent(self, t):
        """Le creux de la couverture sous Bounce (x, profondeur)."""
        best = None
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.contacts[i:i + 4]:
            if not c["soft"]:
                continue
            u = t - c["t"]
            if -0.07 <= u <= 0.16:
                kk = clamp01(1 + u / 0.07) if u < 0 else clamp01(1 - u / 0.16)
                d = c.get("dent", 16) * kk
                if best is None or d > best[1]:
                    best = (c["x"], d)
        return best


# ------------------------------------------------------------------ Insomnia : paupières, yeux, regard
def _lid_keys():
    k = [(0.0, 0.0), (0.45, 0.0), (2.70, 0.68), (2.75, 0.68), (2.80, 0.0), (3.15, 0.0), (4.56, 0.82),
         (4.60, 0.82), (4.65, 0.0), (5.55, 0.0), (6.45, 0.38), (7.88, 0.5),
         (9.20, 0.76), (9.25, 0.76), (9.30, 0.0), (10.15, 0.05), (10.95, 0.46), (11.0, 0.46), (11.05, 0.0),
         (11.9, 0.05), (13.55, 0.95), (13.6, 0.95), (13.65, 0.0), (15.25, 0.0), (15.55, 0.62), (15.6, 0.62),
         (15.66, 0.30), (16.85, 0.75), (16.9, 0.75), (16.96, 0.55), (18.05, 0.86), (18.1, 0.86), (18.16, 0.76),
         (18.85, 0.95), (19.1, 1.0), (21.0, 1.0), (21.04, 0.0), (29.4, 0.0), (33.0, 0.25), (35.3, 0.3)]
    vals = [0.36, 0.42, 0.48, 0.53, 0.56, 0.61, 0.66, 0.70, 0.72, 0.80, 0.83, 0.86, 0.88, 0.90, 0.915, 0.93,
            0.94, 0.95, 0.955, 0.96, 0.965]
    prev = 0.3
    for i, tc in enumerate(COUNTS):
        v = vals[min(i, len(vals) - 1)]
        if abs(tc - 41.2) < 0.01:              # l'omission du milieu : les yeux se sont rouverts
            k += [(39.9, prev), (41.15, 0.34), (41.2, 0.34)]
            prev = 0.34
        if abs(tc - NEAR_F) < 0.01:            # la quasi-collision : les paupières remontent à moitié
            k += [(45.9, prev), (46.2, 0.45), (46.55, 0.45)]
            prev = 0.45
        if abs(tc - 49.0) < 0.01:              # « Insomniaaa… » : il pique du nez
            k += [(47.5, prev), (48.9, 0.77)]
            prev = 0.77
        k += [(tc + 0.02, prev), (tc + 0.35, v)]
        prev = v
    k += [(60.3, 0.975), (61.42, 0.98), (61.48, 0.0)]
    return k


LID = KF(_lid_keys())
# le presque dans le noir : l'œil gauche se ferme, le droit reste une fente
LID_L_OVR = KF([(11.9, 0.05), (13.2, 1.0), (13.6, 1.0)])
LID_R_OVR = KF([(11.9, 0.05), (13.4, 0.88), (13.6, 0.88)])
# la paupière droite tressaille juste avant l'issue
TWITCH = KF([(0, 0.0), (60.95, 0.0), (61.05, 0.16), (61.2, 0.02), (61.3, 0.12), (61.42, 0.0)])


def lid_at(t, side):
    if 11.9 <= t < 13.6:
        return (LID_L_OVR if side < 0 else LID_R_OVR)(t)
    v = LID(t)
    if 27.9 <= t < 28.85:                      # clignements en rafale (les phares clignotent)
        ph = (t - 27.9) / 0.19
        v = 1.0 if (ph % 1.0) < 0.45 else 0.0
    if side > 0:
        v = max(0.0, v - TWITCH(t))
    return v


def eye_base(t):
    if t < 21.0:
        return 1.1
    if t < 35.3:
        return 1.5
    if t < ISSUE:
        return lerp(1.5, 1.22, clamp01((t - 35.3) / 12.0))
    return 1.4


def eye_scale(t):
    e = eye_base(t)
    for (tp, amp, _j) in POPS:
        u = t - tp
        if 0 <= u < 2.0:
            e += amp * math.exp(-u / 0.35) * clamp01(u / 0.04)
    return min(e, 1.62)


def jolt(t):
    y = 0.0
    for (tp, _a, j) in POPS:
        u = t - tp
        if 0 <= u <= 0.32:
            y += j * math.sin(math.pi * u / 0.32)
    return y


JIT = KF([(0, 0.0), (20.95, 0.0), (21.05, 7.5), (23.8, 6.0), (29.0, 5.0), (33.0, 2.5), (35.3, 2.2), (39.3, 0.8),
          (40.4, 1.6), (41.2, 1.4), (45.0, 0.0), (99, 0.0)])


def pupil_kind(t):
    if 21.0 <= t < 23.2:
        return "spiral"
    for tp in (9.25, 11.0, 13.6):
        if 0 <= t - tp < 0.55:
            return "pin"
    return "dot"


# ------------------------------------------------------------------ dessin : primitives
def P(pts, S):
    return [(x * S, y * S) for x, y in pts]


def ell(dr, x, y, rx, ry, col, S):
    dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=col)


def rect(dr, x0, y0, x1, y1, col, S, r=0):
    if r:
        dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=col)
    else:
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)


def rot(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


# ------------------------------------------------------------------ simulation
class Sim:
    scene_top = 0.26

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.lamp = Lamp()
        self.P = Plan(self.lamp)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_times = [h[0] for h in self.P.hits]
        self.hi = 0
        self.lines = list(LINES)
        self.replies = []
        self.talk = []
        self.zs = [54.95 + 1.15 * i for i in range(6)]

    def set_narr(self, narr):
        self.talk = [(n["start"], n["end"], n["key"]) for n in narr]

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
        best, bd = 0.9, 1e9
        for (th, g, _x, _y, _k) in self.P.hits:
            if abs(th - t0) < bd:
                best, bd = g, abs(th - t0)
        return best

    # ---------------------------------------------------------- l'expression de Bounce
    def expr_at(self, t):
        for (a, b, e) in [(21.0, 21.9, "shock"), (23.8, 24.5, "shock"), (45.85, 46.6, "shock"),
                          (54.95, ISSUE, "win"), (ISSUE, 62.3, "shock"), (62.3, 99.0, "lose")]:
            if a <= t < b:
                return e
        for (th, g, _x, _y, _k) in self.P.hits:
            if 0 <= t - th < 0.3:
                return "shock"
        return "calm"

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        Sc0 = S * self.cfg["width"] / W
        Sc = Sc0 * K                                # le monde est zoomé (K), puis recadré
        img = Image.new("RGB", (int(W * Sc) + 2, int(H * Sc) + 2), BG)
        d = ImageDraw.Draw(img)
        self.L = lit_at(t)
        bx, by = self.P.pos(t)
        self.bpos = (bx, by)
        self.draw_room(d, t, Sc)
        self.draw_window(d, t, Sc)
        self.draw_photo(d, t, Sc)
        self.draw_lamp(d, t, Sc)
        self.draw_bed_back(d, t, Sc)
        self.draw_insomnia(d, t, Sc)
        self.draw_bed_front(d, t, Sc)
        self.draw_cup(d, t, Sc)
        self.draw_under(d, t, Sc)
        img = self.draw_beams(img, t, Sc)
        d = ImageDraw.Draw(img)
        self.draw_rings(d, t, Sc)
        base.HERO["expr"] = self.expr_at(t)
        self.draw_zs(d, t, Sc)
        self.draw_cloud(d, t, Sc)
        sx, sy = self.P.squash(t)
        if abs(sx - sy) < 0.004:
            base.ball(d, bx * Sc, by * Sc, R * Sc)
        else:
            self.draw_ball(img, bx, by, R * sx, R * sy, Sc)
        base.HERO["pos"] = ((bx * K - OX) * Sc0, (by * K - OY) * Sc0)
        dr._image.paste(img, (int(round(-OX * Sc0)), int(round(-OY * Sc0))))

    def c(self, col, k=0.8):
        """Couleur d'un objet de la chambre selon la lumière."""
        return mix(mix(col, NIGHT, k), col, self.L)

    def ci(self, col):
        """Insomnia et la lampe restent lisibles dans le noir."""
        return self.c(col, 0.58)

    def draw_ball(self, img, x, y, rx, ry, S):
        r = max(rx, ry)
        size = int(2 * R * 1.7 * S) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        base.ball(ld, size / 2, size / 2, R * S)
        nw, nh = max(2, int(size * rx / R)), max(2, int(size * ry / R))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        img.paste(layer, (int(x * S - nw / 2), int(y * S - nh / 2)), layer)

    # -------- décor
    def draw_room(self, d, t, S):
        rect(d, 0, 0, W, 1262, self.c(WALL), S)
        rect(d, 0, 0, W, 120, self.c(WALL_D), S)
        for k in range(9):                              # papier peint : rayures discrètes
            x = 60 + k * 120
            rect(d, x, 120, x + 8, 1262, self.c(mix(WALL, WALL_D, 0.5)), S)
        rect(d, 0, 1262, W, H, self.c(FLOOR), S)
        for k in range(8):
            y = 1300 + k * 80
            d.line([0, y * S, W * S, y * S], fill=self.c(FLOOR_L), width=max(1, int(4 * S)))
        ell(d, 540, 1470, 470, 120, self.c(RUG), S)
        ell(d, 540, 1470, 400, 92, self.c(mix(RUG, (130, 100, 160), 0.5)), S)
        # par terre : les tasses vides de toutes ses nuits blanches
        for (mx, my, a) in [(250, 1395, 0.0), (330, 1440, 1.57), (430, 1405, 0.0), (610, 1452, -1.57), (700, 1400, 0.0),
                            (790, 1446, 0.3), (520, 1500, 1.4), (180, 1470, 0.0), (880, 1395, 0.0)]:
            body = rot([(mx - 28, my - 34), (mx + 28, my - 34), (mx + 25, my + 34), (mx - 25, my + 34)], mx, my, a)
            hnd = rot([(mx + 26, my - 18), (mx + 48, my - 14), (mx + 48, my + 14), (mx + 26, my + 18)], mx, my, a)
            d.line(P(hnd, S), fill=self.c((206, 206, 214)), width=max(1, int(8 * S)), joint="curve")
            d.polygon(P(body, S), fill=self.c((206, 206, 214)))

    def draw_window(self, d, t, S):
        x0, y0, x1, y1 = WINDOW
        rect(d, x0 - 12, y0 - 12, x1 + 12, y1 + 12, self.c(WOOD_D), S)
        rect(d, x0, y0, x1, y1, SKY, S)
        ell(d, x1 - 52, y0 + 56, 30, 30, MOON, S)
        ell(d, x1 - 40, y0 + 46, 26, 26, SKY, S)
        for (sx, sy) in ((x0 + 40, y0 + 60), (x0 + 90, y0 + 150), (x0 + 30, y1 - 40), (x1 - 40, y1 - 60)):
            ell(d, sx, sy, 4, 4, (200, 200, 230), S)
        d.line([(x0 + x1) / 2 * S, y0 * S, (x0 + x1) / 2 * S, y1 * S], fill=self.c(WOOD_D), width=int(10 * S))
        d.line([x0 * S, (y0 + y1) / 2 * S, x1 * S, (y0 + y1) / 2 * S], fill=self.c(WOOD_D), width=int(10 * S))

    def photo_light(self, t):
        """Les phares d'Insomnia éclairent le cadre de Snooze (29,4 → 33 s)."""
        return smooth((t - 29.6) / 0.5) * smooth((33.0 - t) / 0.5)

    def draw_photo(self, d, t, S):
        x0, y0, x1, y1 = PHOTO
        k = max(self.L, self.photo_light(t))
        def cc(col):
            return mix(mix(col, NIGHT, 0.8), col, k)
        rect(d, x0, y0, x1, y1, cc(WOOD), S, r=6)
        rect(d, x0 + 12, y0 + 12, x1 - 12, y1 - 12, cc((70, 60, 100)), S)
        sx_, sy_, r = (x0 + x1) / 2, (y0 + y1) / 2 + 8, 44.0
        ell(d, sx_, sy_, 1.6 * r, 1.6 * r, cc(base.dim(SNOOZE, 0.35)), S)
        ell(d, sx_, sy_, r, r, cc(SNOOZE), S)
        for ex in (-0.37, 0.37):
            ell(d, sx_ + ex * r, sy_ - 0.2 * r, 0.29 * r, 0.29 * r, cc((104, 104, 104)), S)
            d.line([(sx_ + ex * r - 0.23 * r) * S, (sy_ - 0.2 * r) * S, (sx_ + ex * r + 0.23 * r) * S,
                    (sy_ - 0.2 * r) * S], fill=cc((40, 40, 40)), width=max(1, int(4 * S)))
        d.line([(sx_ - 0.3 * r) * S, (sy_ + 0.42 * r) * S, (sx_ + 0.3 * r) * S, (sy_ + 0.42 * r) * S],
               fill=cc((70, 70, 70)), width=max(1, int(5 * S)))
        # Snooze dort en photo : quand le faisceau l'éclaire, des Z en sortent
        pl = self.photo_light(t)
        if pl > 0.02:
            for i in range(4):
                ph = ((t - 29.6) * 0.9 + i * 0.25) % 1.0
                zx = x1 - 30 + 40 * ph + 6 * math.sin(i + t * 3)
                zy = y0 + 10 - 120 * ph
                a = pl * clamp01(ph / 0.15) * clamp01((1 - ph) / 0.3)
                d.text((zx * S, zy * S), "z", fill=mix(NIGHT, ZCOL, a), anchor="mm", font=font((30 + 30 * ph) * S))

    def draw_lamp(self, d, t, S):
        a = self.lamp.theta(t)
        bx, by = self.lamp.bottom(t)
        tx, ty = PIVOT[0] + (ROD - SHADE_H) * math.sin(a), PIVOT[1] + (ROD - SHADE_H) * math.cos(a)
        d.line([PIVOT[0] * S, PIVOT[1] * S, tx * S, ty * S], fill=self.ci((90, 90, 104)), width=max(1, int(6 * S)))
        shade = [(-50, -SHADE_H), (50, -SHADE_H), (100, 0), (-100, 0)]
        pts = [(bx + u * math.cos(a) + v * math.sin(a), by - u * math.sin(a) + v * math.cos(a)) for (u, v) in shade]
        on = self.L
        if on > 0.02:
            ell(d, bx, by + 10, 34, 22, mix(LAMP_OFF, (255, 246, 210), on), S)
        d.polygon(P(pts, S), fill=mix(self.ci(LAMP_OFF), LAMP, on))
        d.line(P(pts + [pts[0]], S), fill=mix((120, 110, 90), WOOD_D, on), width=max(1, int(5 * S)))

    def draw_lamp_light(self, img, t, S):
        if self.L < 0.02:
            return img
        bx, by = self.lamp.bottom(t)
        a = self.lamp.theta(t)
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        dx = 520 * math.sin(a)
        cone = [(bx - 95, by), (bx + 95, by), (bx + dx + 430, 1180), (bx + dx - 430, 1180)]
        od.polygon(P(cone, S), fill=(255, 226, 160, int(34 * self.L)))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        return img

    def draw_bed_back(self, d, t, S):
        rect(d, 115, 768, 155, 1180, self.c(WOOD), S)
        ell(d, 135, 760, 22, 22, self.c(WOOD), S)
        rect(d, 150, 880, 340, 1000, self.c(PILLOW), S, r=40)

    def draw_bed_front(self, d, t, S):
        rect(d, 130, BED_TOP + 6, 870, 1132, self.c(MATT), S, r=10)
        # la couverture, creusée là où Bounce atterrit
        dent = self.P.dent(t)
        top = []
        for i in range(81):
            x = lerp(172, 846, i / 80)
            y = BED_TOP + 3 * math.sin(x / 47)
            if x < IX + 150:                       # elle remonte sur Insomnia
                k = smooth((IX + 150 - x) / 120)
                y = lerp(y, IY + 82 + 4 * math.sin(x / 30), k)
            if dent is not None:
                y += dent[1] * math.exp(-((x - dent[0]) / 95) ** 2)
            top.append((x, y))
        poly = top + [(846, 1140), (172, 1140)]
        d.polygon(P(poly, S), fill=self.c(BLANKET))
        d.line(P(top, S), fill=self.c(BLANKET_D), width=max(1, int(6 * S)), joint="curve")
        d.line(P([(300, 1112), (846, 1112)], S), fill=self.c(BLANKET_D), width=max(1, int(5 * S)))
        rect(d, 115, 1132, 875, 1182, self.c(WOOD), S)
        for x in (125, 845):
            rect(d, x, 1182, x + 26, 1262, self.c(WOOD_D), S)
        # pied de lit (il tremble quand Bounce le tape)
        sh = 0.0
        for (th, g, _x, _y, k) in self.P.hits:
            u = t - th
            if k == "F" and 0 <= u < 0.25:
                sh += 6 * math.sin(u * 70) * (1 - u / 0.25)
        rect(d, FOOT_X + sh, 800, FOOT_X + 35 + sh, 1182, self.c(WOOD), S)
        ell(d, FOOT_X + 17 + sh, 792, 22, 22, self.c(WOOD), S)
        d.line([(FOOT_X + 6 + sh) * S, 840 * S, (FOOT_X + 6 + sh) * S, 1120 * S], fill=self.c(WOOD_D),
               width=max(1, int(4 * S)))

    def draw_under(self, d, t, S):
        """Sous le lit : la pile de tasses vides d'Insomnia."""
        for (x, y) in [(300, 1224), (372, 1224), (444, 1224), (516, 1224)]:
            rect(d, x - 26, y - 32, x + 26, y + 32, self.c((200, 200, 208)), S, r=6)
            d.arc([(x + 18) * S, (y - 16) * S, (x + 44) * S, (y + 14) * S], -90, 90, fill=self.c((200, 200, 208)),
                  width=max(1, int(6 * S)))

    # -------- la tasse
    def cup_angle(self, t):
        if t < 20.2:
            return 0.0
        return -0.62 * smooth((t - 20.2) / 0.16) + 0.06 * math.sin((t - 20.2) * 18) * math.exp(-(t - 20.36) * 5) * (t > 20.36)

    def draw_cup(self, d, t, S):
        x0, y0, x1, y1 = CUP
        a = self.cup_angle(t)
        jump = 0.0
        u = t - 4.6
        if 0 <= u < 0.3:
            jump = 22 * math.sin(math.pi * u / 0.3)
        cx, cy = x0, y1                         # elle bascule autour de son coin bas gauche
        body = rot([(x0, y0 - jump), (x1, y0 - jump), (x1 - 4, y1 - jump), (x0 + 4, y1 - jump)], cx, cy, a)
        handle = rot([(x1 - 2, y0 + 14 - jump), (x1 + 20, y0 + 18 - jump), (x1 + 20, y0 + 46 - jump),
                      (x1 - 2, y0 + 50 - jump)], cx, cy, a)
        col = self.c(CUPC)
        d.line(P(handle, S), fill=col, width=max(1, int(9 * S)), joint="curve")
        d.polygon(P(body, S), fill=col)
        if t < 20.2:
            rim = [(x0 + 4, y0 + 6 - jump), (x1 - 4, y0 + 6 - jump)]
            d.line(P(rim, S), fill=self.c(COFFEE), width=max(1, int(8 * S)))
            # la vapeur
            for i in range(3):
                pts = []
                for j in range(9):
                    yy = y0 - 14 - j * 9
                    xx = x0 + 16 + i * 16 + 5 * math.sin(j * 0.9 + t * 4 + i)
                    pts.append((xx, yy - jump))
                d.line(P(pts, S), fill=self.c(mix(WALL, (220, 220, 230), 0.5)), width=max(1, int(4 * S)))
        # 4,6 s : le café gicle et retombe dans la tasse
        if 0 <= u < 0.45:
            h = 70 * math.sin(math.pi * u / 0.45)
            ell(d, (x0 + x1) / 2, y0 - h, 14, 10, self.c(COFFEE), S)
        # 20,2 s : le café vole jusque dans la bouche ouverte
        v = (t - 20.22) / 0.42
        if 0 <= v <= 1:
            p0, p2 = (446.0, 998.0), (IX, IY + 0.47 * RI)
            x = lerp(p0[0], p2[0], v)
            y = lerp(p0[1], p2[1], v) - 150 * 4 * v * (1 - v)
            for j in range(5):
                vv = max(0.0, v - j * 0.05)
                xx = lerp(p0[0], p2[0], vv)
                yy = lerp(p0[1], p2[1], vv) - 150 * 4 * vv * (1 - vv)
                ell(d, xx, yy, 26 - 4 * j, 19 - 3 * j, (128, 76, 44), S)

    # -------- Insomnia
    def mouth(self, t):
        """(largeur, hauteur) de la bouche en fractions de RI."""
        w, h = 0.105, 0.105
        yawn = smooth((t - 18.9) / 0.6) * (1 - smooth((t - 20.62) / 0.08))
        if yawn > 0:
            w, h = lerp(w, 0.30, yawn), lerp(h, 0.34, yawn)
        for (a, b, key) in self.talk:
            if a <= t <= b:
                ph = math.sin(math.pi * (t - a) / max(0.1, b - a))
                o = 0.06 * abs(math.sin((t - a) * 11)) * ph + 0.03 * ph
                if key == "hyper":
                    o *= 1.6
                h += o
                w += 0.3 * o
        return w, h

    def ins_pos(self, t):
        x, y = IX, IY
        y -= jolt(t)
        j = JIT(t)
        if j > 0:
            x += j * math.sin(t * 97.0)
            y += 0.6 * j * math.sin(t * 83.0 + 1.0)
        if 14.55 <= t <= 15.3:
            x += 5 * math.sin(t * 60)
        # il pique du nez en s'endormant
        y += 16 * clamp01((LID(t) - 0.5) / 0.5) if 35.0 < t < ISSUE else 0.0
        return x, y

    def gaze(self, t):
        bx, by = self.bpos
        if 9.25 <= t < 13.6:
            lx, ly = self.lamp.bottom(t)
            return lx, ly + 20
        if 29.4 <= t < 33.0:
            k = smooth((t - 29.4) / 0.6) * (1 - smooth((t - 32.4) / 0.6))
            px, py = (PHOTO[0] + PHOTO[2]) / 2, (PHOTO[1] + PHOTO[3]) / 2
            return lerp(bx, px, k), lerp(by, py, k)
        if 21.9 <= t < 27.9:                        # survolté : le regard fouette avec un dépassement
            ov = 0.0
            for (th, g, _x, _y, _k) in self.P.hits:
                u = t - th
                if 0 <= u < 0.3:
                    ov = 60 * math.sin(u * 30) * math.exp(-u * 10)
            return bx + ov, by - ov
        return bx, by

    def eyes(self, t):
        x, y = self.ins_pos(t)
        e = eye_scale(t)
        er = 0.28 * RI * e
        dx = max((0.30 + 0.06 * e) * RI, er * 1.06)
        return [(-1, x - dx, y - 0.2 * RI, er), (1, x + dx, y - 0.2 * RI, er)]

    def draw_insomnia(self, d, t, S):
        x, y = self.ins_pos(t)
        squ = 1.0
        cI = self.ci
        if 5.6 <= t <= 6.6:                         # le soupir : il s'affaisse
            squ = 1.0 - 0.05 * math.sin(math.pi * (t - 5.6) / 1.0)
        if 20.62 <= t <= 21.0:                       # glouglou : il gonfle
            squ = 1.0 + 0.06 * math.sin(math.pi * (t - 20.62) / 0.38)
        rx, ry = RI * (2 - squ), RI * squ
        ell(d, x, y + RI - ry, 1.6 * rx, 1.6 * ry, cI(base.dim(I_BODY, 0.22)), S)
        ell(d, x, y + RI - ry, rx, ry, cI(I_RING), S)
        ell(d, x, y + RI - ry, rx - 0.13 * RI, ry - 0.13 * RI, cI(I_BODY), S)
        cy = y + RI - ry
        dark = 1.0 - self.L
        tgt = self.gaze(t)
        kind = pupil_kind(t)
        for (side, ex, ey, er) in self.eyes(t):
            ey = ey + (cy - y)
            lid = lid_at(t, side)
            # cernes
            ell(d, ex, ey + er * 0.95, er * 1.0, er * 0.32, cI(I_BAG), S)
            # le blanc de l'œil (il brille dans le noir)
            glow = mix(cI(I_EYE), (250, 250, 240), dark)
            if dark > 0.05 and lid < 0.98:
                ell(d, ex, ey, er * 1.22, er * 1.22, mix(cI(I_BODY), (255, 244, 170), 0.45 * dark), S)
            ell(d, ex, ey, er, er, glow, S)
            # veines (de plus en plus nombreuses)
            nv = 2 + sum(1 for (tp, _a, _j) in POPS if tp <= t)
            rng = np.random.default_rng(7 + (side > 0))
            for i in range(min(nv, 10)):
                a0 = rng.uniform(0, 2 * math.pi)
                l1 = rng.uniform(0.35, 0.6)
                pts = [(ex + er * 0.95 * math.cos(a0), ey + er * 0.95 * math.sin(a0))]
                a1 = a0 + rng.uniform(-0.6, 0.6)
                pts.append((ex + er * (0.95 - l1 * 0.6) * math.cos(a1), ey + er * (0.95 - l1 * 0.6) * math.sin(a1)))
                pts.append((ex + er * (0.95 - l1) * math.cos(a1 + 0.3), ey + er * (0.95 - l1) * math.sin(a1 + 0.3)))
                d.line(P(pts, S), fill=mix(VEIN, glow, 0.25), width=max(1, int(3 * S)))
            # pupille
            vx, vy = tgt[0] - ex, tgt[1] - ey
            n = math.hypot(vx, vy) + 1e-6
            off = min(er * 0.48, n * 0.12)
            px, py = ex + vx / n * off, ey + vy / n * off
            pr = 0.36 * er / max(1.0, eye_scale(t) ** 0.5)
            if kind == "pin":
                pr *= 0.42
            if kind == "spiral":
                pts = []
                rot0 = t * 14 * side
                for j in range(40):
                    a = rot0 + j * 0.42
                    rr = er * 0.06 + er * 0.62 * j / 40
                    pts.append((ex + rr * math.cos(a), ey + rr * math.sin(a)))
                d.line(P(pts, S), fill=INK, width=max(1, int(6 * S)), joint="curve")
            else:
                ell(d, px, py, pr, pr, INK, S)
                ell(d, px - pr * 0.3, py - pr * 0.3, pr * 0.32, pr * 0.32, (250, 250, 250), S)
            # paupière (couleur du corps) : une corde qui descend
            if lid > 0.01:
                cut = ey - er + 2 * er * min(1.0, lid)
                dd = (cut - ey) / er
                dd = max(-1.0, min(1.0, dd))
                th0 = math.degrees(math.asin(dd))
                lidcol = cI(mix(I_BODY, I_RING, 0.25))
                if lid >= 0.999:
                    ell(d, ex, ey, er, er, lidcol, S)
                else:
                    d.chord([(ex - er) * S, (ey - er) * S, (ex + er) * S, (ey + er) * S], 180 - th0, 360 + th0,
                            fill=lidcol)
                hw = er * math.sqrt(max(0.0, 1 - dd * dd))
                d.line([(ex - hw) * S, cut * S, (ex + hw) * S, cut * S], fill=cI(I_EDGE), width=max(1, int(5 * S)))
            d.ellipse([(ex - er) * S, (ey - er) * S, (ex + er) * S, (ey + er) * S], outline=cI(I_EDGE),
                      width=max(1, int(0.05 * RI * S)))
        # bouche
        mw, mh = self.mouth(t)
        mx, my = x, cy + 0.47 * RI
        ell(d, mx, my, mw * RI, mh * RI, INK, S)
        inner = max(0.0, mh - 0.055)
        if mh < 0.2:
            ell(d, mx, my, max(0.0, mw - 0.055) * RI, inner * RI, cI(I_BODY), S)
        else:
            ell(d, mx, my + mh * RI * 0.45, mw * RI * 0.6, mh * RI * 0.4, self.c((200, 90, 100)), S)
        # 21 s : la vapeur sort de sa tête
        u = t - 21.0
        if 0 <= u < 1.6:
            for i in range(5):
                ph = (u * 1.4 + i * 0.2) % 1.0
                a = clamp01(1 - u / 1.6) * clamp01(ph / 0.1) * (1 - ph)
                ell(d, x - 50 + 25 * i + 10 * math.sin(i + u * 6), cy - RI - 20 - 120 * ph, 18 + 20 * ph, 14 + 16 * ph,
                    mix(self.c(WALL), (235, 235, 240), a), S)

    # -------- les phares (ses yeux éclairent la chambre)
    def draw_beams(self, img, t, S):
        k = (1.0 - self.L) * (1.0 if t >= 23.8 else 0.0)
        if k < 0.02:
            return img
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        tgt = self.gaze(t)
        flare = 1.0 + 0.6 * math.exp(-(t - ISSUE) / 0.4) * (t >= ISSUE)
        for (side, ex, ey, er) in self.eyes(t):
            lid = lid_at(t, side)
            open_k = 1.0 - lid
            if open_k < 0.02:
                continue
            vx, vy = tgt[0] - ex, tgt[1] - ey
            n = math.hypot(vx, vy) + 1e-6
            ux, uy = vx / n, vy / n
            half = (0.04 + 0.20 * open_k) * flare
            L = 1150
            p1 = (ex + L * (ux * math.cos(half) - uy * math.sin(half)), ey + L * (ux * math.sin(half) + uy * math.cos(half)))
            p2 = (ex + L * (ux * math.cos(-half) - uy * math.sin(-half)), ey + L * (ux * math.sin(-half) + uy * math.cos(-half)))
            a = int(min(170, 92 * k * (0.5 + 0.5 * open_k) * flare))
            od.polygon(P([(ex, ey), p1, p2], S), fill=(255, 238, 150, a))
            # la tache de lumière là où ça tombe
            dist = min(n, 900)
            cx, cy = ex + ux * dist, ey + uy * dist
            rr = dist * math.tan(half) * 0.9
            od.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], fill=(255, 244, 180, int(a * 0.8)))
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    # -------- l'équivalent visible des chocs
    def draw_rings(self, d, t, S):
        for (th, g, x, y, k) in self.P.hits:
            u = t - th
            if not (0 <= u < 0.26):
                continue
            if k == "F":
                cx, cy = FOOT_X, y
            elif k == "L":
                cx, cy = x, y - R
            else:
                cx, cy = x - 30, y + R
            rr = 26 + 120 * u / 0.26
            col = mix((255, 255, 255), self.c(WALL), u / 0.26)
            d.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], outline=col, width=max(1, int(7 * S)))
            for j in range(6):
                a = j * math.pi / 3 + 0.3
                r0, r1 = rr * 0.55, rr * 0.85
                d.line([(cx + r0 * math.cos(a)) * S, (cy + r0 * math.sin(a)) * S, (cx + r1 * math.cos(a)) * S,
                        (cy + r1 * math.sin(a)) * S], fill=col, width=max(1, int(6 * S)))

    # -------- les Z
    def draw_zs(self, d, t, S):
        x, y = self.ins_pos(t)
        out = []
        if 12.9 <= t < 13.75:                       # le petit z du presque, qui éclate au rallumage
            u = t - 12.9
            if t < 13.6:
                out.append((x + 110 + 10 * u, y - RI - 10 - 40 * u, 34 + 20 * u, clamp01(u / 0.2)))
            else:
                k = (t - 13.6) / 0.15
                out.append((x + 118, y - RI - 40, 54 * (1 + k), 1 - k))
        for (i, tz) in enumerate(self.zs):
            u = t - tz
            if u < 0 or t > ISSUE + 0.18:
                continue
            life = 3.0
            if u > life:
                continue
            fs = 40 + 34 * (u / life) + 8 * i
            a = clamp01(u / 0.25) * clamp01((life - u) / 0.6)
            zx = x + 100 + 60 * (u / life) + 8 * math.sin(u * 2 + i)
            zy = y - RI - 10 - 190 * (u / life)
            if t >= ISSUE:
                k = (t - ISSUE) / 0.18
                fs *= 1 + 0.8 * k
                a *= 1 - k
            out.append((zx, zy, fs, a))
        for (zx, zy, fs, a) in out:
            if a > 0.02:
                d.text((zx * S, zy * S), "Z", fill=mix(self.c(WALL), ZCOL, a), anchor="mm", font=font(fs * S))

    # -------- la bulle de pensée : il compte les Bounce
    def cloud_k(self, t):
        if t < 34.6:
            return 0.0
        if t < ISSUE:
            return smooth((t - 34.6) / 0.5)
        return 1.0

    def draw_cloud(self, d, t, S):
        x, y = self.ins_pos(t)
        puffs = [(33.8, (x + 92, y - RI - 2, 14)), (34.1, (x + 92, y - RI - 62, 22)),
                 (34.4, (x + 82, y - RI - 140, 30))]
        burst = clamp01((t - ISSUE) / 0.12) if t >= ISSUE else 0.0
        if burst >= 1.0 or t < 33.8:
            return
        fade = 1 - burst
        bgc = self.c(WALL)
        for (tp, (px, py, pr)) in puffs:
            if t >= tp:
                k = smooth((t - tp) / 0.2) * fade
                ell(d, px, py, (pr + 4) * k, (pr + 4) * k, mix(bgc, CLOUD_E, fade), S)
                ell(d, px, py, pr * k, pr * k, mix(bgc, CLOUDC, fade), S)
        k = self.cloud_k(t)
        if k <= 0.01:
            return
        sc = CS * k * (1 + 0.3 * burst)
        cx, cy = CLOUD_C
        blobs = [(-180, 10, 82), (-95, -50, 96), (10, -70, 104), (115, -45, 94), (190, 12, 80), (110, 55, 86),
                 (0, 62, 92), (-110, 55, 86)]
        for (bx, by, br) in blobs:
            ell(d, cx + bx * sc, cy + by * sc, (br + 6) * sc, (br + 6) * sc, mix(bgc, CLOUD_E, fade), S)
        for (bx, by, br) in blobs:
            ell(d, cx + bx * sc, cy + by * sc, br * sc, br * sc, mix(bgc, CLOUDC, fade), S)
        if burst > 0 or k < 0.6:
            return
        # l'herbe et la barrière
        d.line(P([(cx - 200, GROUND_Y), (cx + 200, GROUND_Y)], S), fill=GRASS, width=max(1, int(8 * S)))
        fc = (150, 104, 70)
        for fx in (FENCE_X - 30, FENCE_X + 30):
            rect(d, fx - 6, GROUND_Y - 74, fx + 6, GROUND_Y, fc, S)
        for fy in (GROUND_Y - 58, GROUND_Y - 30):
            rect(d, FENCE_X - 46, fy - 5, FENCE_X + 46, fy + 5, fc, S)
        # les petits Bounce : un qui attend à gauche, et ceux qui sautent
        pos = base.HERO.get("pos")
        last = [tc for tc in COUNTS if tc <= t]
        jump_d = 0.62
        JX = 108
        for tc in last[-2:]:
            u = t - tc
            if u < 0 or u > jump_d + 0.45:
                continue
            if u <= jump_d:
                v = u / jump_d
                mxp = lerp(FENCE_X - JX, FENCE_X + JX, v)
                myp = GROUND_Y - MINI_R - 120 * 4 * v * (1 - v)
                al = 1.0
            else:
                v = (u - jump_d) / 0.45
                mxp = FENCE_X + JX + 70 * v
                myp = GROUND_Y - MINI_R - 30 * math.sin(math.pi * v)
                al = 1 - v
            if al > 0.05:
                base.ball(d, mxp * S, myp * S, MINI_R * S * (0.6 + 0.4 * al))
        # celui qui attend son tour (il apparaît après chaque saut ; il piétine pendant les silences)
        appear = (last[-1] + 0.2) if last else 34.9
        if t >= appear:
            a = smooth((t - appear) / 0.25)
            gap = t - (last[-1] if last else 35.3)
            tap = 1.0 if gap > 1.4 else 0.4
            hop = abs(math.sin(t * (9 if gap > 1.4 else 5))) * 14 * tap
            base.ball(d, (FENCE_X - JX) * S, (GROUND_Y - MINI_R - hop) * S, MINI_R * S * (0.5 + 0.5 * a))
        base.HERO["pos"] = pos


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 8.4, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.1,
    "narrator_voice": "am_puck", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.3,
}


def exact_events(sim):
    """Les contacts durs à leurs instants exacts (indépendants du nombre d'images par seconde)."""
    return [(t, "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(sim.P.hits)]


def render_audio(sim, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(exact_events(sim), total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        for (t0, kind, _d, tag) in words:
            g = sim.hit_gain(t0)
            gg = max(0.1, min(1.3, g)) ** 0.7 * 0.92
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=LINE_GAIN.get(n["key"], 1.0))
    v = hook_clip(cfg) if cfg.get("hook_voice") else None
    if v is not None:
        a, n = int(HOOK_T * SR), len(v)
        duck = np.ones(len(buf))
        duck[a:a + n] = 0.42
        m = int(0.3 * SR)
        duck[a + n:a + n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, HOOK_T, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.set_narr(narr)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "hits": len(ev),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [round(e[0], 3) for e in ev if round(e[0], 3) not in said]
    if hv is not None:
        summary["contacts_sous_l_accroche"] = [round(e[0], 2) for e in ev
                                               if e[0] + len(name) / SR > HOOK_T - 0.05 and e[0] < HOOK_T + len(hv) / SR + 0.05]
    summary["near_miss"] = [round(x, 3) for x in sim.P.near]
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, dur, cfg, audio, narr)
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
