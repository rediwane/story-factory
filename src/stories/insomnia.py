"""
Prototype « insomnia » (v2) : Insomnia (perso d'un fan, le frère de Snooze : balle verte, yeux énormes injectés,
cernes, petite bouche ronde, tasse de café) s'endort enfin ; Bounce, au pied du lit, le fait décoller de
l'oreiller à chaque « BOUNCE ». La lampe qu'il éteint (soulagement) puis rallume en se balançant ; le café qu'il
catapulte dans sa bouche en plein bâillement (la tasse finit en chapeau) ; survolté, Insomnia éclaire la chambre
de ses yeux. Puis il compte les Bounce comme des moutons : chaque « BOUNCE » fait sauter un Bounce rêvé par-dessus
la barrière (bâtons, pyramide, faux pas, point d'interrogation pendant les silences, remise à zéro). Fier, Bounce
rebondit de plus en plus près de la lampe ; effrayé, il se fait de plus en plus doux : le Bounce rêvé ne passe plus
la barrière, et Insomnia se réveille. « Insomnia. »

Tout est calculé d'avance sur une horloge (contacts, voix, états). Le monde est dessiné zoomé (K) puis recadré à
la résolution de la config (aperçu 540×960). L'audio suit les instants exacts des contacts.

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
K = 1.25
OX, OY = 470.0 * K - 540.0, 1064.0 * K - 1330.0
G = 2600.0
R = 118.0                         # Bounce
RI = 130.0                        # Insomnia (disque de rayon RI, halo 1,6 RI)
IX, IY = 255.0, 966.0             # Insomnia, assis contre l'oreiller
BED_TOP = 1064.0                  # dessus de la couverture
SOFT_Y = BED_TOP - R
FOOT_X = 756.0                    # face intérieure du pied de lit
F_POS = (FOOT_X - R, 880.0)
PIVOT = (600.0, -40.0)
ROD = 620.0                       # pivot -> bas de l'abat-jour
SHADE_H = 80.0
CUP = (376.0, 986.0, 448.0, 1064.0)   # la tasse (x0, y0, x1, y1), anse à droite
C_POS = (512.0, 890.0)
PHOTO = (140.0, 560.0, 300.0, 700.0)
WINDOW = (612.0, 292.0, 752.0, 482.0)
CLOUD_C = (372.0, 352.0)
FENCE_X = 372.0
GROUND_Y = 446.0
FENCE_H = 74.0
MINI_R = 38.0
XL, XR = FENCE_X - 118.0, FENCE_X + 118.0
PILE = [(500.0, 0), (550.0, 0), (525.0, 1)]

# couleurs
BG = (8, 8, 12)
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
COFFEE = (128, 76, 44)
LAMP = (230, 200, 120)
LAMP_OFF = (120, 106, 80)
SKY = (16, 22, 50)
MOON = (240, 236, 200)
CLOUDC = (236, 234, 252)
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


def night(col, k):
    """La couleur au clair de lune : assombrie de k, teintée de bleu."""
    r, g, b = col
    return (int(r * k * 0.82), int(g * k * 0.92), int(min(255, b * k * 1.12 + 14)))


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
END = 63.85
ISSUE = 60.90
T_OFF, T_ON, T_CUP, T_DARK, T_LAST = 6.95, 10.00, 16.60, 22.30, 62.80
T_POP_CAFE = 17.45
T_CLOUD = 31.6
T_RESET = 44.20                   # le « BOUNCE » trop fort : un œil s'ouvre, le compte retombe à zéro
T_GROW = 45.45                    # la bulle grandit, le rythme accélère
T_ZZZ = 49.95                     # le premier Z : il dort
T_FAIL = 58.30                    # le dernier petit « bounce » : le Bounce rêvé ne passe plus la barrière
# contacts durs : (t, genre, gain) ; F = pied du lit, L = lampe, C = anse de la tasse
HARD = [
    (0.18, "F", 1.3), (2.65, "F", 1.1), (4.70, "F", 0.9),
    (T_OFF, "L", 1.15), (T_ON, "L", 1.25),
    (11.85, "F", 1.0), (12.85, "F", 0.95), (13.85, "F", 0.9),
    (T_CUP, "C", 1.15),
    (18.60, "F", 1.0), (19.50, "F", 1.0), (20.40, "F", 1.0), (21.25, "F", 1.0),
    (T_DARK, "L", 1.1),
    (23.20, "F", 1.0), (24.10, "F", 1.0), (25.40, "F", 1.0), (26.25, "F", 1.0), (27.60, "F", 0.95),
    (28.50, "F", 0.95), (29.90, "F", 0.95), (30.80, "F", 0.95),
    (32.90, "F", 0.9), (34.05, "F", 0.9), (35.15, "F", 0.9), (36.05, "F", 0.95), (36.90, "F", 0.95),
    (38.15, "F", 0.9),
    (40.85, "F", 1.0), (41.95, "F", 0.9), (43.00, "F", 0.9), (T_RESET, "F", 1.45), (45.20, "F", 0.7),
    (46.10, "F", 0.9), (47.00, "F", 0.9), (47.90, "F", 0.9), (48.75, "F", 0.9), (49.70, "F", 0.95),
    (51.10, "F", 1.0), (52.50, "F", 1.0), (53.90, "F", 1.05),
    (55.20, "F", 0.5), (56.25, "F", 0.33), (57.30, "F", 0.2), (T_FAIL, "F", 0.12),
    (T_LAST, "L", 1.15),
]
# les grands rebonds vaniteux vers la lampe éteinte : (contact au pied du lit, marge sous l'abat-jour)
SHOW = [(49.70, 70.0), (51.10, 36.0), (52.50, 14.0), (53.90, 3.0)]
NEAR_T = 53.90
COUNT0 = 32.90
COUNTS = [t for (t, k, g) in HARD if COUNT0 - 1e-6 <= t <= T_FAIL + 1e-6 and k == "F"]
# hauteur du saut du Bounce rêvé (en px monde) et genre de saut, par compte
JUMP = {36.90: (70.0, "trip"), T_RESET: (330.0, "fly"), 55.20: (112.0, "n"), 56.25: (96.0, "n"),
        57.30: (82.0, "n"), T_FAIL: (46.0, "fail")}
for _t, _g in SHOW:
    JUMP[_t] = ({70.0: 215.0, 36.0: 235.0, 14.0: 255.0, 3.0: 270.0}[_g], "bonk")
LINES = [(3.75, "Insomnia.", "sigh"), (10.95, "Insomnia!", "annoy"), (17.95, "INSOMNIA!", "hyper"),
         (61.85, "Insomnia", "dead")]
LINE_GAIN = {"sigh": 0.95, "annoy": 1.05, "hyper": 1.1, "dead": 1.0}
L_HITS = [t for (t, k, g) in HARD if k == "L"]
# sursauts : (t, gonflement des yeux, saut en px)
POPS = [(0.18, 0.45, 78), (2.65, 0.3, 42), (T_ON, 0.3, 30), (11.85, 0.06, 6), (12.85, 0.03, 3),
        (T_POP_CAFE, 0.45, 46), (T_RESET, 0.15, 14), (ISSUE, 0.45, 54)]


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
        kicks = {int(T_OFF / self.dt): 0.62, int(T_ON / self.dt): -0.3, int(T_DARK / self.dt): 0.22,
                 int(T_LAST / self.dt): 0.2}
        for (tf, gap) in SHOW:
            kicks[int((tf + 0.37) / self.dt)] = 0.012 + 0.05 * math.exp(-gap / 10.0)
        w2 = G / ROD
        for i in range(n):
            if i in kicks:
                om += kicks[i]
            om += (-w2 * th - 0.30 * om) * self.dt
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


def soft(t, x, dent=16.0, nofill_before=False):
    return {"t": t, "x": x, "y": SOFT_Y + dent, "axis": "y", "soft": True, "gain": 0, "kind": "M", "dent": dent,
            "nofill_before": nofill_before}


class Plan:
    def __init__(self, lamp):
        cs = []
        for (t, kind, g) in HARD:
            if kind == "F":
                x, y, ax = F_POS[0], F_POS[1], "x"
            elif kind == "L":
                bx, by = lamp.bottom(t)
                x, y, ax = bx, by + R, "y"
            else:
                x, y, ax = C_POS[0], C_POS[1], "y"
            cs.append({"t": t, "x": x, "y": y, "axis": ax, "soft": False, "gain": g, "kind": kind,
                       "nofill_after": any(abs(t - s) < 1e-6 for s, _g in SHOW)})
        # les grands rebonds : du pied du lit, sommet juste sous l'abat-jour, puis un rebond mou
        self.show = []
        for (tf, gap) in SHOW:
            bx, by = lamp.bottom(tf + 0.37)
            y_soft = SOFT_Y + 28
            apex = by + R + gap
            v = math.sqrt(2 * G * (F_POS[1] - apex))
            T = v / G + math.sqrt(2 * (y_soft - apex) / G)
            ua = v / G
            xa = bx + 25.0
            vx = (xa - F_POS[0]) / ua
            xs = F_POS[0] + vx * T
            cs.append(soft(tf + T, xs, 28.0, nofill_before=True))
            self.show.append((tf, round(tf + ua, 3), gap, round(xs, 1)))
        # la lampe se touche en montant et se quitte en descendant
        ls_ = [c for c in cs if c["kind"] == "L"]
        for c in ls_:
            for dtm in (-0.42, 0.42):
                tt = c["t"] + dtm
                if not any(abs(o["t"] - tt) < 0.3 or (o is not c and abs(o["t"] - c["t"]) < 0.47 and
                                                     (o["t"] - c["t"]) * dtm > 0) for o in cs):
                    cs.append(soft(tt, 615.0))
        cs.sort(key=lambda c: c["t"])
        # boucle : avant l'image 0, Bounce vient de la lampe (comme à la fin) ; après la fin, il va au pied du lit
        t_loop = END + 0.03 + HARD[0][0]
        lb = lamp.bottom(0)
        d_end = t_loop - T_LAST
        start = [{"t": HARD[0][0] - d_end, "x": lb[0], "y": lb[1] + R, "axis": "y", "soft": False, "kind": "L",
                  "gain": 0}, soft(HARD[0][0] - d_end + 0.42, 615.0)]
        after = [{"t": t_loop, "x": F_POS[0], "y": F_POS[1], "axis": "x", "soft": False, "kind": "F", "gain": 0}]
        full = list(start)
        prev = start[-1]
        k = 0
        for c in cs + after:
            gap = c["t"] - prev["t"]
            if not prev.get("nofill_after") and not c.get("nofill_before"):
                n = max(1, math.ceil(gap / 0.68))
                for j in range(1, n):
                    tt = prev["t"] + gap * j / n
                    k += 1
                    x = 619.0 + 12.0 * math.sin(k * 2.3)
                    dent = 16.0
                    if T_FAIL < tt < ISSUE + 0.3 or 38.2 < tt < 40.8:   # il se fait tout doux
                        dent = 10.0
                    full.append(soft(tt, x, dent))
            full.append(c)
            prev = c
        self.contacts = sorted(full, key=lambda c: c["t"])
        self.ts = [c["t"] for c in self.contacts]
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in self.contacts
                     if not c["soft"] and 0 <= c["t"] <= END]

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
                amp = (0.08 + 0.004 * c.get("dent", 16)) if c["soft"] else 0.1 + 0.07 * min(1.4, c["gain"])
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def dent(self, t):
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
VALS = [0.40, 0.45, 0.50, 0.54, 0.58, 0.62, 0.60, 0.66, 0.70, 0.50, 0.58, 0.66, 0.74, 0.80, 0.86, 0.90, 0.93,
        0.95, 0.96, 0.965, 0.97, 0.975, 0.975]


def _lid_keys():
    k = [(0.0, 0.9), (0.18, 0.9), (0.21, 0.0), (0.7, 0.0), (2.6, 0.78), (2.65, 0.78), (2.68, 0.0), (3.05, 0.0),
         (3.5, 0.38), (4.68, 0.38), (4.72, 0.18), (4.95, 0.38), (5.4, 0.4), (6.9, 0.82), (7.6, 0.96),
         (9.98, 0.96), (10.02, 0.0), (10.55, 0.0), (10.8, 0.42), (11.8, 0.42), (11.88, 0.22), (12.8, 0.66),
         (12.88, 0.46), (13.8, 0.8), (13.9, 0.78), (14.4, 0.98), (14.6, 1.0), (T_POP_CAFE - 0.02, 1.0),
         (T_POP_CAFE + 0.03, 0.0), (26.3, 0.0), (28.8, 0.28), (32.85, 0.35)]
    prev = 0.35
    for i, tc in enumerate(COUNTS):
        v = VALS[min(i, len(VALS) - 1)]
        if abs(tc - 40.85) < 0.01:            # omission du milieu : les yeux se rouvrent
            k += [(38.9, prev), (40.8, 0.36)]
            prev = 0.36
        if abs(tc - T_RESET) < 0.01:          # trop fort : il rouvre un œil (voir lid_at) et retombe
            k += [(tc + 0.02, prev), (tc + 0.1, 0.45), (tc + 1.0, v)]
            prev = v
            continue
        if abs(tc - T_FAIL) < 0.01:
            break
        k += [(tc + 0.02, prev), (tc + 0.35, v)]
        prev = v
    k += [(T_FAIL + 0.6, 0.975), (59.6, 0.8), (60.4, 0.6), (ISSUE - 0.03, 0.55), (ISSUE + 0.02, 0.0),
          (T_LAST + 0.25, 0.0), (END + 0.05, 0.86)]
    return k


LID = KF(_lid_keys())
# le presque-réveil : l'œil gauche s'ouvre grand, puis se referme
RESET_EYE = KF([(0, 0.0), (T_RESET, 0.0), (T_RESET + 0.06, 1.0), (T_RESET + 0.8, 1.0), (T_RESET + 1.5, 0.0)])


def lid_at(t, side):
    v = LID(t)
    if 7.0 < t < 9.98 and side > 0:           # dans le noir il est bien : un œil s'entrouvre pour vérifier
        v -= 0.25 * smooth((t - 8.6) / 0.2) * (1 - smooth((t - 9.2) / 0.2))
    if 24.9 <= t < 25.75:                      # survolté : il cligne en rafale (les phares clignotent)
        ph = (t - 24.9) / 0.17
        v = 1.0 if (ph % 1.0) < 0.45 else 0.0
    if side < 0:
        v = lerp(v, 0.0, RESET_EYE(t))
    return clamp01(v)


def eye_base(t):
    if t < T_POP_CAFE:
        return 1.15
    if t < 35.0:
        return 1.5
    if t < ISSUE:
        return lerp(1.5, 1.25, clamp01((t - 35.0) / 12.0))
    return 1.45


def eye_scale(t):
    e = eye_base(t)
    for (tp, amp, _j) in POPS:
        u = t - tp
        if 0 <= u < 2.0:
            e += amp * math.exp(-u / 0.4) * clamp01(u / 0.04)
    return min(e, 1.62)


def jolt(t):
    y = 0.0
    for (tp, _a, j) in POPS:
        u = t - tp
        d = 0.32 + j / 260.0
        if 0 <= u <= d:
            y += j * math.sin(math.pi * u / d)
    return y


JIT = KF([(0, 0.0), (T_POP_CAFE - 0.05, 0.0), (T_POP_CAFE + 0.05, 8.0), (T_DARK, 6.0), (28.0, 4.0), (32.0, 2.5),
          (36.0, 1.2), (38.6, 0.6), (40.6, 2.0), (41.5, 1.0), (45.0, 0.0), (99, 0.0)])


def pupil_kind(t):
    if T_POP_CAFE <= t < T_POP_CAFE + 1.9:
        return "spiral"
    if 0 <= t - T_ON < 0.8:
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


def bez(p0, p1, p2, u):
    return ((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
            (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1])


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
        for (a, b, e) in [(3.6, 4.7, "lose"), (10.8, 11.85, "lose"), (T_CUP, T_POP_CAFE + 0.6, "shock"),
                          (T_DARK, T_DARK + 1.2, "shock"), (T_RESET, T_RESET + 0.95, "shock"),
                          (T_ZZZ - 0.3, NEAR_T + 0.3, "win"), (NEAR_T + 0.3, 55.1, "shock"),
                          (55.1, ISSUE, "lose"), (ISSUE, 61.8, "shock"), (61.8, 99.0, "lose")]:
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
        Sc = Sc0 * K
        img = Image.new("RGB", (int(W * Sc) + 2, int(H * Sc) + 2), BG)
        d = ImageDraw.Draw(img)
        self.L = lit_at(t)
        bx, by = self.P.pos(t)
        self.bpos = (bx, by)
        self.draw_room(d, t, Sc)
        self.draw_window(d, t, Sc)
        self.draw_photo(d, t, Sc)
        img = self.draw_moon(img, t, Sc)
        d = ImageDraw.Draw(img)
        self.draw_lamp(d, t, Sc)
        self.draw_bed_back(d, t, Sc)
        self.draw_insomnia(d, t, Sc)
        self.draw_bed_front(d, t, Sc)
        self.draw_cup(d, t, Sc)
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

    def c(self, col, k=0.52):
        """Couleur d'un objet selon la lumière (lampe, ou clair de lune)."""
        return mix(night(col, k), col, self.L)

    def ci(self, col):
        """Les personnages restent au moins à ~80 % au clair de lune."""
        return self.c(col, 0.84)

    def draw_ball(self, img, x, y, rx, ry, S):
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
        for k in range(9):
            x = 60 + k * 120
            rect(d, x, 120, x + 8, 1262, self.c(mix(WALL, WALL_D, 0.5)), S)
        rect(d, 0, 1262, W, H, self.c(FLOOR), S)
        for k in range(6):
            y = 1290 + k * 60
            d.line([0, y * S, W * S, y * S], fill=self.c(FLOOR_L), width=max(1, int(4 * S)))
        ell(d, 470, 1380, 360, 70, self.c(RUG), S)
        ell(d, 470, 1380, 300, 52, self.c(mix(RUG, (130, 100, 160), 0.5)), S)
        # ses chaussons
        for (x, a) in ((300, -0.15), (372, 0.1)):
            pts = rot([(x - 34, 1300), (x + 34, 1300), (x + 34, 1326), (x - 34, 1326)], x, 1313, a)
            d.polygon(P(pts, S), fill=self.c((170, 220, 140)))
            ell(d, x - 20, 1308, 12, 9, self.c((210, 240, 190)), S)

    def draw_window(self, d, t, S):
        x0, y0, x1, y1 = WINDOW
        rect(d, x0 - 12, y0 - 12, x1 + 12, y1 + 12, self.c(WOOD_D), S)
        rect(d, x0, y0, x1, y1, SKY, S)
        ell(d, x1 - 46, y0 + 50, 28, 28, MOON, S)
        ell(d, x1 - 35, y0 + 41, 24, 24, SKY, S)
        for (sx, sy) in ((x0 + 34, y0 + 56), (x0 + 80, y0 + 140), (x0 + 28, y1 - 34), (x1 - 34, y1 - 52)):
            ell(d, sx, sy, 4, 4, (200, 200, 230), S)
        d.line([(x0 + x1) / 2 * S, y0 * S, (x0 + x1) / 2 * S, y1 * S], fill=self.c(WOOD_D), width=int(10 * S))
        d.line([x0 * S, (y0 + y1) / 2 * S, x1 * S, (y0 + y1) / 2 * S], fill=self.c(WOOD_D), width=int(10 * S))

    def draw_moon(self, img, t, S):
        """Clair de lune : une nappe bleutée de la fenêtre au lit, quand la lampe est éteinte."""
        k = 1.0 - self.L
        if k < 0.02:
            return img
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        x0, y0, x1, y1 = WINDOW
        od.polygon(P([(x0, y0), (x1, y0), (x1 - 60, 1100), (x0 - 520, 1100)], S), fill=(150, 170, 255, int(26 * k)))
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    def photo_light(self, t):
        return smooth((t - 26.4) / 0.5) * smooth((28.8 - t) / 0.5)

    def draw_photo(self, d, t, S):
        x0, y0, x1, y1 = PHOTO
        k = max(self.L, self.photo_light(t))

        def cc(col):
            return mix(night(col, 0.52), col, k)
        rect(d, x0, y0, x1, y1, cc(WOOD), S, r=6)
        rect(d, x0 + 12, y0 + 12, x1 - 12, y1 - 12, cc((70, 60, 100)), S)
        sx_, sy_, r = (x0 + x1) / 2, (y0 + y1) / 2 + 6, 40.0
        ell(d, sx_, sy_, 1.6 * r, 1.6 * r, cc(base.dim(SNOOZE, 0.35)), S)
        ell(d, sx_, sy_, r, r, cc(SNOOZE), S)
        for ex in (-0.37, 0.37):
            ell(d, sx_ + ex * r, sy_ - 0.2 * r, 0.29 * r, 0.29 * r, cc((104, 104, 104)), S)
            d.line([(sx_ + ex * r - 0.23 * r) * S, (sy_ - 0.2 * r) * S, (sx_ + ex * r + 0.23 * r) * S,
                    (sy_ - 0.2 * r) * S], fill=cc((40, 40, 40)), width=max(1, int(4 * S)))
        d.line([(sx_ - 0.3 * r) * S, (sy_ + 0.42 * r) * S, (sx_ + 0.3 * r) * S, (sy_ + 0.42 * r) * S],
               fill=cc((70, 70, 70)), width=max(1, int(5 * S)))
        pl = self.photo_light(t)
        if pl > 0.02:
            for i in range(4):
                ph = ((t - 26.4) * 0.9 + i * 0.25) % 1.0
                zx = x1 - 26 + 40 * ph + 6 * math.sin(i + t * 3)
                zy = y0 + 10 - 120 * ph
                a = pl * clamp01(ph / 0.15) * clamp01((1 - ph) / 0.3)
                d.text((zx * S, zy * S), "z", fill=mix(self.c(WALL), ZCOL, a), anchor="mm", font=font((34 + 30 * ph) * S))

    def draw_lamp(self, d, t, S):
        a = self.lamp.theta(t)
        bx, by = self.lamp.bottom(t)
        tx, ty = PIVOT[0] + (ROD - SHADE_H) * math.sin(a), PIVOT[1] + (ROD - SHADE_H) * math.cos(a)
        d.line([PIVOT[0] * S, PIVOT[1] * S, tx * S, ty * S], fill=self.c((110, 110, 124), 0.8), width=max(1, int(6 * S)))
        shade = [(-50, -SHADE_H), (50, -SHADE_H), (100, 0), (-100, 0)]
        pts = [(bx + u * math.cos(a) + v * math.sin(a), by - u * math.sin(a) + v * math.cos(a)) for (u, v) in shade]
        on = self.L
        if on > 0.02:
            ell(d, bx, by + 10, 34, 22, mix(LAMP_OFF, (255, 246, 210), on), S)
        d.polygon(P(pts, S), fill=mix(night(LAMP_OFF, 0.9), LAMP, on))
        d.line(P(pts + [pts[0]], S), fill=mix((150, 140, 120), WOOD_D, on), width=max(1, int(5 * S)))

    def draw_bed_back(self, d, t, S):
        rect(d, 95, 768, 130, 1180, self.c(WOOD), S)
        ell(d, 112, 760, 22, 22, self.c(WOOD), S)
        rect(d, 125, 880, 300, 1000, self.c(PILLOW), S, r=40)

    def draw_bed_front(self, d, t, S):
        rect(d, 110, BED_TOP + 6, 790, 1132, self.c(MATT), S, r=10)
        dent = self.P.dent(t)
        top = []
        for i in range(81):
            x = lerp(150, 770, i / 80)
            y = BED_TOP + 3 * math.sin(x / 47)
            if x < IX + 145:
                k = smooth((IX + 145 - x) / 115)
                y = lerp(y, IY + 80 + 4 * math.sin(x / 30), k)
            if dent is not None:
                y += dent[1] * math.exp(-((x - dent[0]) / 95) ** 2)
            top.append((x, y))
        poly = top + [(770, 1140), (150, 1140)]
        d.polygon(P(poly, S), fill=self.c(BLANKET))
        d.line(P(top, S), fill=self.c(BLANKET_D), width=max(1, int(6 * S)), joint="curve")
        d.line(P([(280, 1112), (770, 1112)], S), fill=self.c(BLANKET_D), width=max(1, int(5 * S)))
        rect(d, 95, 1132, 795, 1182, self.c(WOOD), S)
        for x in (105, 765):
            rect(d, x, 1182, x + 26, 1262, self.c(WOOD_D), S)
        sh = 0.0
        for (th, g, _x, _y, k) in self.P.hits:
            u = t - th
            if k == "F" and 0 <= u < 0.3:
                sh += (5 + 9 * max(0.0, g - 0.9)) * math.sin(u * 70) * (1 - u / 0.3)
        rect(d, FOOT_X + sh, 800, FOOT_X + 35 + sh, 1182, self.c(WOOD), S)
        ell(d, FOOT_X + 17 + sh, 792, 22, 22, self.c(WOOD), S)
        d.line([(FOOT_X + 6 + sh) * S, 840 * S, (FOOT_X + 6 + sh) * S, 1120 * S], fill=self.c(WOOD_D),
               width=max(1, int(4 * S)))

    # -------- la tasse : sur le plateau, puis catapultée, puis chapeau, puis de retour
    def cup_state(self, t):
        """(cx, cy, angle, plein) : centre de la tasse, rotation (0 = debout), café dedans ?"""
        x0, y0, x1, y1 = CUP
        rest = ((x0 + x1) / 2, (y0 + y1) / 2)
        ix, iy = self.ins_pos(t)
        hat = (ix + 4, iy - RI - (y1 - y0) / 2 + 14)
        hop = 0.0
        for (tp, h) in ((0.18, 26.0), (2.65, 40.0)):
            u = t - tp
            if 0 <= u < 0.34:
                hop = h * math.sin(math.pi * u / 0.34)
        if t < T_CUP:
            return rest[0], rest[1] - hop, 0.0, True
        u = (t - T_CUP) / 0.62
        if u < 1.0:                               # vol : elle se retourne au-dessus de sa tête
            p = bez(rest, (rest[0] - 30, 640.0), hat, smooth(u) * 0.9 + 0.1 * u)
            return p[0], p[1], -math.pi * smooth(u), u < 0.75
        if t < ISSUE:                             # chapeau, qui tremble avec lui
            return hat[0], hat[1], -math.pi + 0.06 * math.sin(t * 40) * (JIT(t) > 1), False
        u = (t - ISSUE) / 0.6
        if u < 1.0:                               # le sursaut final la renvoie sur le plateau
            p = bez(hat, (330.0, 700.0), rest, smooth(u))
            return p[0], p[1], -math.pi + math.pi * smooth(u) - 2 * math.pi * smooth(u), False
        return rest[0], rest[1], 0.0, False

    def draw_cup(self, d, t, S):
        x0, y0, x1, y1 = CUP
        w, h = (x1 - x0), (y1 - y0)
        cx, cy, a, full = self.cup_state(t)
        body = rot([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2 - 5, cy + h / 2),
                    (cx - w / 2 + 5, cy + h / 2)], cx, cy, a)
        handle = rot([(cx + w / 2 - 2, cy - h / 2 + 14), (cx + w / 2 + 24, cy - h / 2 + 18),
                      (cx + w / 2 + 24, cy + h / 2 - 18), (cx + w / 2 - 2, cy + h / 2 - 14)], cx, cy, a)
        col = self.ci(CUPC)
        d.line(P(handle, S), fill=col, width=max(1, int(10 * S)), joint="curve")
        d.polygon(P(body, S), fill=col)
        if full and t < T_CUP:
            rim = rot([(cx - w / 2 + 5, cy - h / 2 + 7), (cx + w / 2 - 5, cy - h / 2 + 7)], cx, cy, a)
            d.line(P(rim, S), fill=self.c(COFFEE), width=max(1, int(9 * S)))
            for i in range(3):
                pts = []
                for j in range(9):
                    yy = cy - h / 2 - 14 - j * 10
                    xx = cx - 18 + i * 18 + 5 * math.sin(j * 0.9 + t * 4 + i)
                    pts.append((xx, yy))
                d.line(P(pts, S), fill=self.c(mix(WALL, (220, 220, 230), 0.55)), width=max(1, int(4 * S)))
        # 2,65 s : le café gicle et retombe dans la tasse
        u = t - 2.65
        if 0 <= u < 0.5:
            hh = 90 * math.sin(math.pi * u / 0.5)
            ell(d, cx, cy - h / 2 - hh, 18, 13, self.c(COFFEE), S)
            ell(d, cx - 16, cy - h / 2 - hh * 0.7, 9, 7, self.c(COFFEE), S)
        # le jet de café : de la tasse en vol jusque dans la bouche ouverte
        if T_CUP + 0.08 <= t < T_CUP + 0.62:
            mx, my = self.mouth_pos(t)
            mouth_top = (mx, my - 10)
            k = (t - T_CUP - 0.08) / 0.54
            src = rot([(cx, cy - h / 2)], cx, cy, a)[0]
            n = 9
            for j in range(n):
                v = clamp01(k * 1.6 - j / n * 0.8)
                if v <= 0:
                    continue
                p = bez(src, ((src[0] + mouth_top[0]) / 2, min(src[1], mouth_top[1]) - 40), mouth_top, v)
                rr = 19 - j * 1.2
                ell(d, p[0], p[1], rr, rr * 0.85, COFFEE, S)
        # glouglou : une grosse goutte avalée
        if T_CUP + 0.62 <= t < T_CUP + 0.8:
            mx, my = self.mouth_pos(t)
            ell(d, mx, my, 16, 12, COFFEE, S)
        # la vapeur sort sous la tasse-chapeau (comme une bouilloire)
        u = t - T_POP_CAFE
        if 0 <= u < 2.2:
            for i in range(6):
                ph = (u * 1.5 + i * 0.17) % 1.0
                aa = clamp01(1 - u / 2.2) * clamp01(ph / 0.1) * (1 - ph)
                side = -1 if i % 2 else 1
                ell(d, cx + side * (40 + 70 * ph), cy + h / 2 - 10 - 60 * ph, 16 + 18 * ph, 12 + 14 * ph,
                    mix(self.c(WALL), (240, 240, 245), aa), S)

    # -------- Insomnia
    def mouth(self, t):
        w, h = 0.105, 0.105
        yawn = smooth((t - 14.5) / 0.6) * (1 - smooth((t - (T_CUP + 0.62)) / 0.08))
        if yawn > 0:
            w, h = lerp(w, 0.32, yawn), lerp(h, 0.36, yawn)
        for (a, b, key) in self.talk:
            if a <= t <= b:
                ph = math.sin(math.pi * (t - a) / max(0.1, b - a))
                o = 0.06 * abs(math.sin((t - a) * 11)) * ph + 0.03 * ph
                if key == "hyper":
                    o *= 1.6
                h += o
                w += 0.3 * o
        return w, h

    def smiling(self, t):
        if 7.4 <= t < T_ON:
            return smooth((t - 7.4) / 0.4)
        if T_ZZZ <= t < T_FAIL + 0.4:
            return smooth((t - T_ZZZ) / 0.5)
        return 0.0

    def ins_pos(self, t):
        x, y = IX, IY
        y -= jolt(t)
        j = JIT(t)
        if j > 0:
            x += j * math.sin(t * 97.0)
            y += 0.6 * j * math.sin(t * 83.0 + 1.0)
        if 10.95 <= t <= 11.7:
            x += 5 * math.sin(t * 60)
        if 0 <= t - T_ON < 0.5:
            x -= 14 * math.sin(math.pi * (t - T_ON) / 0.5)
        y += 16 * clamp01((LID(t) - 0.5) / 0.5) if 35.0 < t < ISSUE else 0.0
        return x, y

    def mouth_pos(self, t):
        x, y = self.ins_pos(t)
        return x, y + 0.47 * RI

    def gaze(self, t):
        bx, by = self.bpos
        if T_ON <= t < 11.8:
            lx, ly = self.lamp.bottom(t)
            return lx, ly + 20
        if 26.3 <= t < 28.8:
            k = smooth((t - 26.3) / 0.5) * (1 - smooth((t - 28.3) / 0.5))
            px, py = (PHOTO[0] + PHOTO[2]) / 2, (PHOTO[1] + PHOTO[3]) / 2
            return lerp(bx, px, k), lerp(by, py, k)
        if T_POP_CAFE + 0.5 <= t < 24.9:
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
        cI = self.ci
        squ = 1.0
        jy = jolt(t)
        if jy > 0:
            squ = 1.0 + 0.08 * min(1.0, jy / 60)       # étiré quand il décolle
        if 3.75 <= t <= 4.6:
            squ = 1.0 - 0.05 * math.sin(math.pi * (t - 3.75) / 0.85)
        if T_CUP + 0.62 <= t <= T_POP_CAFE:
            squ = 1.0 + 0.07 * math.sin(math.pi * (t - T_CUP - 0.62) / (T_POP_CAFE - T_CUP - 0.62))
        rx, ry = RI * (2 - squ), RI * squ
        cy = y + RI - ry
        ell(d, x, cy, 1.6 * rx, 1.6 * ry, cI(base.dim(I_BODY, 0.22)), S)
        ell(d, x, cy, rx, ry, cI(I_RING), S)
        ell(d, x, cy, rx - 0.13 * RI, ry - 0.13 * RI, cI(I_BODY), S)
        dark = 1.0 - self.L
        tgt = self.gaze(t)
        kind = pupil_kind(t)
        for (side, ex, ey, er) in self.eyes(t):
            ey = ey + (cy - y)
            lid = lid_at(t, side)
            ell(d, ex, ey + er * 0.95, er * 1.0, er * 0.32, cI(I_BAG), S)
            glow = mix(cI(I_EYE), (250, 250, 240), dark)
            if dark > 0.05 and lid < 0.98 and t >= T_DARK:
                ell(d, ex, ey, er * 1.22, er * 1.22, mix(cI(I_BODY), (255, 244, 170), 0.45 * dark), S)
            ell(d, ex, ey, er, er, glow, S)
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
            vx, vy = tgt[0] - ex, tgt[1] - ey
            n = math.hypot(vx, vy) + 1e-6
            off = min(er * 0.48, n * 0.12)
            px, py = ex + vx / n * off, ey + vy / n * off
            pr = 0.36 * er / max(1.0, eye_scale(t) ** 0.5)
            if kind == "pin":
                pr *= 0.4
            if kind == "spiral":
                pts = []
                rot0 = t * 14 * side
                for j in range(44):
                    a = rot0 + j * 0.42
                    rr = er * 0.06 + er * 0.66 * j / 44
                    pts.append((ex + rr * math.cos(a), ey + rr * math.sin(a)))
                d.line(P(pts, S), fill=INK, width=max(1, int(7 * S)), joint="curve")
            else:
                ell(d, px, py, pr, pr, INK, S)
                ell(d, px - pr * 0.3, py - pr * 0.3, pr * 0.32, pr * 0.32, (250, 250, 250), S)
            if lid > 0.01:
                cut = ey - er + 2 * er * min(1.0, lid)
                dd = max(-1.0, min(1.0, (cut - ey) / er))
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
        mw, mh = self.mouth(t)
        mx, my = x, cy + 0.47 * RI
        sm = self.smiling(t)
        if sm > 0.5 and mh < 0.13:
            pts = [(mx - 0.2 * RI + 0.4 * RI * k / 10, my - 0.02 * RI + 0.09 * RI * math.sin(math.pi * k / 10))
                   for k in range(11)]
            d.line(P(pts, S), fill=INK, width=max(1, int(7 * S)), joint="curve")
        else:
            ell(d, mx, my, mw * RI, mh * RI, INK, S)
            inner = max(0.0, mh - 0.055)
            if mh < 0.2:
                ell(d, mx, my, max(0.0, mw - 0.055) * RI, inner * RI, cI(I_BODY), S)
            else:
                ell(d, mx, my + mh * RI * 0.45, mw * RI * 0.6, mh * RI * 0.4, cI((200, 90, 100)), S)

    # -------- les phares
    def draw_beams(self, img, t, S):
        k = (1.0 - self.L) * (1.0 if t >= T_DARK else 0.0)
        if k < 0.02:
            return img
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        tgt = self.gaze(t)
        flare = 1.0 + 0.7 * math.exp(-(t - ISSUE) / 0.5) * (t >= ISSUE)
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
            dist = min(n, 900)
            cx, cy = ex + ux * dist, ey + uy * dist
            rr = dist * math.tan(half) * 0.9
            od.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], fill=(255, 244, 180, int(a * 0.8)))
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    def draw_rings(self, d, t, S):
        for (th, g, x, y, k) in self.P.hits:
            u = t - th
            if not (0 <= u < 0.28):
                continue
            if k == "F":
                cx, cy = FOOT_X, y
            elif k == "L":
                cx, cy = x, y - R
            else:
                cx, cy = x - 30, y + R
            big = 0.6 + 0.5 * min(1.4, g)
            rr = (26 + 120 * u / 0.28) * big
            col = mix((255, 255, 255), self.c(WALL), u / 0.28)
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
        groups = [(-2.0, 0.18, 0.0), (7.9, T_ON, 7.9)]
        for (a, b, t0) in groups:
            if not (a <= t < b + 0.2):
                continue
            for i in range(3):
                ts = t0 + i * 0.7 - (2.1 if a < 0 else 0)
                u = t - ts
                if u < 0:
                    continue
                life = 2.1
                ph = (u % life) / life if a < 0 else min(1.0, u / life)
                fs = 40 + 34 * ph
                al = clamp01(ph / 0.15) * clamp01((1 - ph) / 0.3)
                zx, zy = x + 95 + 50 * ph, y - RI - 20 - 150 * ph
                if t >= b:
                    kk = (t - b) / 0.2
                    fs *= 1 + kk
                    al *= 1 - kk
                out.append((zx, zy, fs, al))
        if T_ZZZ <= t < ISSUE + 0.2:
            for i in range(12):
                ts = T_ZZZ + i * 0.85
                u = t - ts
                if u < 0 or u > 2.6 or ts > T_FAIL + 0.3:
                    continue
                ph = u / 2.6
                fs = 46 + 40 * ph
                al = clamp01(ph / 0.12) * clamp01((1 - ph) / 0.3)
                zx, zy = x + 100 + 70 * ph, y - RI - 30 - 200 * ph
                if t >= ISSUE:
                    kk = (t - ISSUE) / 0.2
                    fs *= 1 + kk
                    al *= 1 - kk
                out.append((zx, zy, fs, al))
        for (zx, zy, fs, a) in out:
            if a > 0.02:
                d.text((zx * S, zy * S), "Z", fill=mix(self.c(WALL), ZCOL, a), anchor="mm", font=font(fs * S))

    # -------- la bulle de pensée : il compte les Bounce
    def cloud_scale(self, t):
        if t < T_CLOUD:
            return 0.0
        k = smooth((t - T_CLOUD) / 0.5)
        return k * lerp(0.86, 1.0, smooth((t - T_GROW) / 0.5))

    def draw_cloud(self, d, t, S):
        x, y = self.ins_pos(t)
        if t < T_CLOUD - 0.6:
            return
        bgc = self.c(WALL)
        if t >= ISSUE:                            # la bulle éclate en petits nuages qui s'envolent
            u = (t - ISSUE) / 0.4
            if u >= 1.0:
                return
            sc0 = self.cloud_scale(ISSUE - 0.01)
            for i in range(10):
                a = i * 2 * math.pi / 10 + 0.3
                rr = (60 + 260 * u) * sc0
                px, py = CLOUD_C[0] + rr * math.cos(a) * 1.3, CLOUD_C[1] + rr * math.sin(a) * 0.7
                pr = 46 * (1 - u) * sc0
                ell(d, px, py, pr, pr, mix(bgc, CLOUDC, 1 - u), S)
            return
        burst = 0.0
        fade = 1.0
        puffs = [(T_CLOUD - 0.6, (x + 88, y - RI - 2, 14)), (T_CLOUD - 0.35, (x + 92, y - RI - 60, 22)),
                 (T_CLOUD - 0.1, (x + 92, y - RI - 135, 30))]
        for (tp, (px, py, pr)) in puffs:
            if t >= tp:
                k = smooth((t - tp) / 0.2) * fade
                ell(d, px, py, (pr + 4) * k, (pr + 4) * k, mix(bgc, CLOUD_E, fade), S)
                ell(d, px, py, pr * k, pr * k, mix(bgc, CLOUDC, fade), S)
        sc = self.cloud_scale(t) * (1 + 0.3 * burst)
        if sc <= 0.01:
            return
        shake = 0.0
        u = t - T_RESET
        if 0 <= u < 0.6:
            shake = 10 * math.sin(u * 60) * (1 - u / 0.6)
        cx, cy = CLOUD_C[0] + shake, CLOUD_C[1]
        top_y = cy - 174 * sc
        blobs = [(-180, 10, 82), (-95, -50, 96), (10, -70, 104), (115, -45, 94), (190, 12, 80), (110, 55, 86),
                 (0, 62, 92), (-110, 55, 86)]
        dent = 0.0
        for (tc, gap) in SHOW:                    # le Bounce rêvé cogne le plafond de la bulle
            uu = t - (tc + 0.3)
            if 0 <= uu < 0.35:
                dent = max(dent, (30 - gap / 3) * math.sin(math.pi * uu / 0.35))
        for (bx, by, br) in blobs:
            yy = cy + by * sc - (dent if by < -40 else 0)
            ell(d, cx + bx * sc, yy, (br + 6) * sc, (br + 6) * sc, mix(bgc, CLOUD_E, fade), S)
        for (bx, by, br) in blobs:
            yy = cy + by * sc - (dent if by < -40 else 0)
            ell(d, cx + bx * sc, yy, br * sc, br * sc, mix(bgc, CLOUDC, fade), S)
        if burst > 0 or self.cloud_scale(t) < 0.6:
            return
        g = cy + (GROUND_Y - CLOUD_C[1]) * sc / 0.86
        fx = cx + (FENCE_X - CLOUD_C[0])
        d.line(P([(cx - 200 * sc, g), (cx + 200 * sc, g)], S), fill=GRASS, width=max(1, int(8 * S)))
        fc = (150, 104, 70)
        for px_ in (fx - 28, fx + 28):
            rect(d, px_ - 6, g - FENCE_H, px_ + 6, g, fc, S)
        for fy in (g - 58, g - 30):
            rect(d, fx - 44, fy - 5, fx + 44, fy + 5, fc, S)
        self.draw_tally(d, t, S, cx - 150 * sc, cy - 95 * sc)
        pos = base.HERO.get("pos")
        self.draw_minis(d, t, S, fx, g, top_y)
        base.HERO["pos"] = pos

    def counted(self, t):
        """Nombre de Bounce comptés depuis la dernière remise à zéro."""
        n = 0
        for tc in COUNTS:
            if tc > t:
                break
            if abs(tc - T_RESET) < 1e-6:
                n = 0
                continue
            if abs(tc - T_FAIL) < 1e-6:
                continue
            n += 1
        return n

    def draw_tally(self, d, t, S, x0, y0):
        n = self.counted(t)
        col = (90, 80, 140)
        u = t - T_RESET
        if 0 <= u < 0.5:                         # les bâtons s'envolent : le compte retombe à zéro
            n_before = self.counted(T_RESET - 0.01)
            for i in range(n_before):
                gx = x0 + (i // 5) * 70 + (i % 5) * 11 + 60 * u * math.sin(i * 1.7)
                gy = y0 - 140 * u * (0.5 + 0.5 * math.cos(i))
                al = 1 - u / 0.5
                d.line([gx * S, gy * S, gx * S, (gy + 36) * S], fill=mix(CLOUDC, col, al), width=max(1, int(6 * S)))
            return
        for i in range(n):
            grp, j = i // 5, i % 5
            gx = x0 + grp * 70
            if j < 4:
                d.line([(gx + j * 11) * S, y0 * S, (gx + j * 11) * S, (y0 + 36) * S], fill=col, width=max(1, int(6 * S)))
            else:
                d.line([(gx - 6) * S, (y0 + 30) * S, (gx + 40) * S, (y0 + 6) * S], fill=col, width=max(1, int(6 * S)))

    def draw_minis(self, d, t, S, fx, g, top_y):
        mr = MINI_R
        xl, xr = fx - 118, fx + 118
        done = [tc for tc in COUNTS if tc <= t]
        last = done[-1] if done else None
        # la pyramide des Bounce déjà comptés (elle s'écroule à la remise à zéro)
        n = self.counted(t)
        settled = [tc for tc in COUNTS if tc + (0.62 if tc < T_GROW else 0.5) + 0.9 <= t
                   and tc > (T_RESET if t >= T_RESET else -1) and abs(tc - T_FAIL) > 1e-6]
        u = t - T_RESET
        if 0 <= u < 0.7:
            pre = [tc for tc in COUNTS if tc < T_RESET - 0.9]
            for i, _ in enumerate(pre[:len(PILE)]):
                px, row = PILE[i]
                vx = (i - 2.5) * 140
                xx = px + (fx - FENCE_X) + vx * u
                yy = g - mr * 0.8 - row * 1.5 * mr - 260 * u + 900 * u * u
                if yy < g + 40:
                    base.ball(d, xx * S, yy * S, mr * S * 0.9)
        else:
            for i, _ in enumerate(settled[:len(PILE)]):
                px, row = PILE[i]
                base.ball(d, (px + (fx - FENCE_X)) * S, (g - mr * 0.8 - row * 1.5 * mr) * S, mr * S * 0.8)
        # les sauts en cours
        for tc in done[-3:]:
            uu = t - tc
            hgt, kind = JUMP.get(round(tc, 2), (120.0, "n"))
            jd = 0.62 if tc < T_GROW else 0.5
            if kind == "fail":
                if uu <= 0.5:                     # trop faible : il ne passe pas, il retombe de son côté
                    v = uu / 0.5
                    xx = lerp(xl, fx - 46 - mr, min(1.0, v * 1.6))
                    yy = g - mr - hgt * 4 * v * (1 - v)
                    base.ball(d, xx * S, yy * S, mr * S)
                continue
            if uu > jd + 0.9:
                continue
            if uu <= jd:
                v = uu / jd
                xx = lerp(xl, xr, v)
                yy = g - mr - hgt * 4 * v * (1 - v)
                if kind == "bonk":
                    yy = max(yy, top_y + mr + 6)
                if kind == "fly":
                    yy = g - mr - hgt * v * 1.8
                if kind == "trip" and v > 0.5:      # il accroche la barrière et s'étale de l'autre côté
                    w2 = (v - 0.5) / 0.5
                    xx = lerp(fx + 10, xr - 30, w2)
                    yy = lerp(g - FENCE_H - mr, g - mr * 0.5, w2 * w2)
                if kind == "fly" and yy < top_y - 2 * mr:
                    continue
                if kind == "trip" and v > 0.5:
                    self.mini_squashed(d, xx, yy, mr, S, 1.0 - 0.45 * (v - 0.5) / 0.5)
                else:
                    base.ball(d, xx * S, yy * S, mr * S)
            else:                                 # il roule vers la pyramide
                if kind == "fly":
                    continue
                w2 = smooth((uu - jd) / 0.9)
                idx = min(len(PILE) - 1, max(0, self.counted(tc) - 1))
                px, row = PILE[idx] if self.counted(tc) <= len(PILE) else (fx + 240, 0)
                xx = lerp(xr, px + (fx - FENCE_X), w2)
                yy = lerp(g - mr, g - mr * 0.8 - row * 1.5 * mr, w2)
                if self.counted(tc) > len(PILE):
                    yy = g - mr
                    if xx > fx + 220:
                        continue
                if kind == "trip":
                    self.mini_squashed(d, xx, yy, mr, S, 0.55 + 0.45 * w2)
                else:
                    base.ball(d, xx * S, yy * S, mr * S * (1 - 0.1 * w2))
        # celui qui attend son tour
        nxt = [tc for tc in COUNTS if tc > t]
        if t >= T_FAIL:
            # le Bounce rêvé est resté devant la barrière : il attend le prochain « BOUNCE », qui ne vient pas
            uu = t - T_FAIL
            if uu > 0.5:
                hop = abs(math.sin(t * 7)) * 8
                base.ball(d, (fx - 46 - mr) * S, (g - mr - hop) * S, mr * S)
                q = smooth((uu - 0.6) / 0.5)
                if q > 0:
                    fsz = (60 + 50 * clamp01((uu - 1.0) / 1.5)) * q
                    d.text(((fx - 46 - mr) * S, (g - 2.2 * mr - fsz * 0.55) * S), "?", fill=(250, 200, 60),
                           anchor="mm", font=font(fsz * S), stroke_width=max(1, int(4 * S)), stroke_fill=(90, 60, 20))
            return
        if not nxt:
            return
        appear = (last + 0.25) if last is not None else T_CLOUD + 0.4
        if t < appear:
            return
        a = smooth((t - appear) / 0.25)
        gap = t - (last if last is not None else T_CLOUD)
        waiting = 38.9 <= t < 40.85
        hop = abs(math.sin(t * (9 if waiting else 5))) * (12 if waiting else 6)
        wx = xl + (12 * math.sin(t * 3) if waiting else 0.0)
        base.ball(d, wx * S, (g - mr - hop) * S, mr * S * (0.5 + 0.5 * a))
        if waiting:
            q = smooth((t - 39.4) / 0.4)
            fsz = 64 * q
            if fsz > 2:
                d.text((wx * S, (g - 2.2 * mr - fsz * 0.55) * S), "?", fill=(250, 200, 60), anchor="mm",
                       font=font(fsz * S), stroke_width=max(1, int(4 * S)), stroke_fill=(90, 60, 20))

    def mini_squashed(self, d, x, y, r, S, k):
        """Un Bounce rêvé qui s'étale (il a trébuché)."""
        size = int(2 * r * 1.7 * S) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO.get("pos")
        base.ball(ld, size / 2, size / 2, r * S)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size / max(0.3, k) ** 0.5)), max(2, int(size * k))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        d._image.paste(layer, (int(x * S - nw / 2), int((y + r * (1 - k)) * S - nh / 2)), layer)


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 12.4, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.1,
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
    summary["show"] = sim.P.show
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
