"""
Prototype « insomnia » (v4) : Insomnia (perso d'un fan, le frère de Snooze : balle verte, yeux énormes injectés,
cernes, petite bouche ronde, tasse de café) s'est enfin endormi. Bounce tombe de haut sur le pied du lit : une onde
traverse le matelas et le fait décoller. L'oreiller sur les yeux, soufflé ; la lampe éteinte puis rallumée ; l'onde
d'un autre grand « BOUNCE » catapulte la tasse posée sur ses genoux dans sa bouche en plein bâillement (elle finit en
chapeau) ; dans le noir, ses yeux font phares et trouvent la photo de Snooze qui dort. Il compte les Bounce comme
des moutons, avec des incidents (raté, chute qui coûte 2, un Bounce rêvé qui lui tombe sur la tête), des silences où
il manque de s'endormir ; le vrai Bounce cogne la bulle et remet le compte à zéro ; le second compte va par deux et
déborde en cascade. Il s'endort, Bounce se fait tout doux, le rêve cale, il frémit, et Bounce panique : le « BOUNCE »
le plus violent de la vidéo fait éclater le rêve. Puis le jour se lève, et il s'endort enfin, pendant que Bounce
rebondit tout doucement (et la vidéo reboucle sur le premier « BOUNCE »).

Tout est calculé d'avance sur une horloge (contacts, voix, états). Le monde est dessiné à l'échelle K puis recadré à
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
K = 1.15
OX, OY = 255.0 * K - 300.0, 1262.0 * K - 1620.0    # Insomnia centré vers x = 300, le sol à y = 1620
G = 2600.0
R = 118.0                         # Bounce
RI = 130.0                        # Insomnia (disque de rayon RI, halo 1,6 RI)
IX, IY = 255.0, 966.0             # Insomnia, assis contre l'oreiller
BED_TOP = 1064.0                  # dessus de la couverture
SOFT_Y = BED_TOP - R
FOOT_X = 678.0                    # face intérieure du pied de lit
F_POS = (FOOT_X - R, 880.0)
BED_X0, BED_X1 = 95.0, 713.0
PIVOT = (470.0, -40.0)
ROD = 620.0                       # pivot -> bas de l'abat-jour
SHADE_H = 80.0
CUP = (309.0, 981.0, 381.0, 1059.0)   # la tasse, posée sur ses genoux (x0, y0, x1, y1), anse à droite
PHOTO = (120.0, 470.0, 330.0, 690.0)
WINDOW = (540.0, 300.0, 690.0, 480.0)
# la bulle de pensée (monde) : centre, demi-largeur, demi-hauteur
BUB = (437.0, 465.0, 330.0, 215.0)
GROUND_Y = 628.0
FENCE_X = 437.0
FENCE_H = 110.0
MINI_R = 70.0
ROOM_R = 52.0
FLOOR_Y = 1262.0

# couleurs
BG = (8, 8, 12)
WALL = (40, 46, 84)
WALL_D = (30, 34, 64)
WOOD = (150, 104, 70)
WOOD_D = (100, 68, 46)
PILLOW = (226, 228, 240)
PILLOW_D = (180, 182, 204)
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
DAWN_SKY = (255, 176, 120)
SUN = (255, 220, 120)
MOON = (240, 236, 200)
CLOUDC = (236, 234, 252)
CLOUD_E = (150, 146, 190)
GRASS = (120, 180, 110)
ZCOL = (196, 176, 255)
SNOOZE = (192, 192, 192)
QCOL = (250, 196, 50)


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
END = 64.00
SLAM_APEX = 716.0
WAVE_DT = 0.16                    # l'onde met 0,16 s du pied du lit à la tête du lit
T_SLAM = 0.18                     # 1er « BOUNCE » : il tombe de haut sur le pied du lit
T_PILLOW, T_PILLOW_OFF = 3.30, 4.90
T_OFF, T_ON = 6.95, 10.00
T_CAFE_SLAM = 13.25               # le « BOUNCE » dont l'onde catapulte la tasse posée sur ses genoux
T_CUP = T_CAFE_SLAM + WAVE_DT * (FOOT_X - 345.0) / (FOOT_X - 150.0)
T_POP_CAFE = T_CUP + 0.85
T_DARK = 17.30
T_PHOTO = (21.60, 24.20)
T_CLOUD = 25.20
T_MISS = 29.25                    # un Bounce rêvé rate la barrière
T_CRASH = 36.70                   # un Bounce rêvé s'étale sur la barrière : le compteur perd 2
T_OVER1 = 37.85                   # 1er débordement : un Bounce rêvé tombe de la bulle et lui rebondit sur la tête
T_RESET = 42.00                   # le vrai Bounce cogne la bulle : le compte retombe à zéro
T_PAIRS = 42.90                   # 2e comptage : chaque « BOUNCE » fait sauter DEUX Bounce rêvés
T_OVER2 = 50.60                   # 2e débordement, plus fort : une cascade tombe par terre
T_ZZZ = 51.90
T_FAIL = 56.35                    # le « bounce » trop doux : le Bounce rêvé ne passe plus la barrière
ISSUE_BANG = 58.10                # le « BOUNCE » le plus violent de la vidéo
T_DAWN = 59.40
ISSUE = 62.00                     # il s'endort enfin, au lever du jour
# contacts durs : (t, genre, gain) ; F = pied du lit, L = lampe, B = sous la bulle
HARD = [
    (T_SLAM, "F", 1.4), (T_PILLOW_OFF, "F", 1.15),
    (T_OFF, "L", 1.15), (T_ON, "L", 1.25),
    (11.85, "F", 1.0), (T_CAFE_SLAM, "F", 1.4),
    (15.60, "F", 1.0), (16.45, "F", 1.0), (T_DARK, "L", 1.1),
    (18.20, "F", 1.0), (19.05, "F", 1.0), (20.90, "F", 1.0), (22.30, "F", 0.95), (23.60, "F", 0.95),
    (24.60, "F", 0.95),
    (26.30, "F", 0.9), (27.15, "F", 0.9), (28.40, "F", 0.9), (T_MISS, "F", 1.0), (30.40, "F", 0.9),
    (31.25, "F", 0.9),
    (33.80, "F", 0.95), (34.65, "F", 0.9), (35.85, "F", 0.9), (T_CRASH, "F", 1.05), (T_OVER1, "F", 1.15),
    (40.30, "F", 0.95), (41.15, "F", 0.9), (T_RESET, "B", 1.35),
    (T_PAIRS, "F", 0.95), (43.75, "F", 0.95), (45.25, "F", 0.95), (46.10, "F", 0.95), (47.60, "F", 0.95),
    (48.45, "F", 0.95),
    (T_OVER2, "F", 1.2), (51.45, "F", 1.2),
    (52.95, "F", 0.55), (54.05, "F", 0.38), (55.20, "F", 0.24), (T_FAIL, "F", 0.13),
    (ISSUE_BANG, "F", 1.5),
]
SLAMS = [T_SLAM, T_CAFE_SLAM, ISSUE_BANG]
COUNT0 = 26.30
COUNTS = [t for (t, k, g) in HARD if COUNT0 - 1e-6 <= t <= T_FAIL + 1e-6 and k == "F"]
DECRESC = {52.95: 150.0, 54.05: 136.0, 55.20: 124.0, T_FAIL: 70.0}   # hauteur de saut du Bounce rêvé
LINES = [(2.30, "Insomnia.", "sigh"), (10.95, "Insomnia!", "annoy"), (14.95, "INSOMNIA!", "hyper"),
         (59.05, "Insomnia!", "annoy2"), (60.60, "Insomniaaa...", "sleepy")]
LINE_GAIN = {"sigh": 0.95, "annoy": 1.05, "hyper": 1.1, "annoy2": 1.15, "sleepy": 0.8}
BUBBLE_TXT = {"sigh": "INSOMNIA.", "annoy": "INSOMNIA!", "hyper": "INSOMNIA!!", "annoy2": "INSOMNIA!",
              "sleepy": "insomniaaa..."}
L_HITS = [t for (t, k, g) in HARD if k == "L"]
# sursauts : (t, gonflement des yeux, saut en px) ; ceux des grands « BOUNCE » arrivent avec l'onde
POPS = [(T_SLAM + WAVE_DT, 0.45, 84), (T_PILLOW_OFF, 0.3, 40), (T_ON, 0.3, 30), (11.85, 0.06, 6),
        (T_POP_CAFE, 0.45, 46), (T_OVER1 + 1.0, 0.12, 14), (T_RESET, 0.12, 12), (ISSUE_BANG + WAVE_DT, 0.5, 104)]


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
        kicks = {int(T_OFF / self.dt): 0.62, int(T_ON / self.dt): -0.3, int(T_DARK / self.dt): 0.22}
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



def soft(t, x, dent=16.0, nofill_before=False, nofill_after=False):
    return {"t": t, "x": x, "y": SOFT_Y + dent, "axis": "y", "soft": True, "gain": 0, "kind": "M", "dent": dent,
            "nofill_before": nofill_before, "nofill_after": nofill_after}


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
                x, y, ax = 540.0, BUB[1] + BUB[3] + R, "y"
            cs.append({"t": t, "x": x, "y": y, "axis": ax, "soft": False, "gain": g, "kind": kind,
                       "nofill_before": any(abs(t - s) < 1e-6 for s in SLAMS)})
        # les grands « BOUNCE » tombent de haut : un rebond mou, un arc dont le sommet frôle l'abat-jour (ou la bulle)
        T = apex_time(SOFT_Y + 30, F_POS[1], SLAM_APEX)
        T2 = apex_time(SOFT_Y + 30, F_POS[1], BUB[1] + BUB[3] + R + 4)
        self.slam_T = T
        cs.append(soft(T_CAFE_SLAM - T, 540.0, 30.0, nofill_after=True))
        cs.append(soft(ISSUE_BANG - T2, 540.0, 30.0, nofill_after=True))
        # la fin : il rebondit tout doux (mou, muet, bien visible), sans jamais s'arrêter
        tt, i = ISSUE_BANG + 0.55, 0
        while tt < END + 1.5:
            cs.append(soft(tt, 518.0 if i % 2 else 556.0, 22.0))
            tt += 0.5
            i += 1
        # la lampe et la bulle se touchent en montant et se quittent en descendant
        for c in [c for c in cs if c["kind"] in ("L", "B")]:
            dd = 0.42 if c["kind"] == "L" else 0.32
            for dtm in (-dd, dd):
                tt = c["t"] + dtm
                if not any(abs(o["t"] - tt) < 0.25 or (o is not c and abs(o["t"] - c["t"]) < dd + 0.05 and
                                                      (o["t"] - c["t"]) * dtm > 0) for o in cs):
                    cs.append(soft(tt, 530.0))
        cs.sort(key=lambda c: c["t"])
        start = [soft(T_SLAM - T, 540.0, 30.0, nofill_after=True)]
        full = list(start)
        prev = start[-1]
        k = 0
        quiet = [(31.85, 33.8), (37.9, 40.3), (48.5, 50.6), (T_FAIL, ISSUE_BANG)]
        for c in cs:
            gap = c["t"] - prev["t"]
            if not prev.get("nofill_after") and not c.get("nofill_before"):
                n = max(1, math.ceil(gap / 0.66))
                for j in range(1, n):
                    tt = prev["t"] + gap * j / n
                    k += 1
                    x = 538.0 + 12.0 * math.sin(k * 2.3)
                    dent = 24.0 if any(a < tt < b for (a, b) in quiet) else 16.0
                    full.append(soft(tt, x, dent))
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
        i = bisect.bisect_left(self.ts, t - 0.25)
        for c in self.contacts[i:i + 4]:
            u = t - c["t"]
            big = (not c["soft"]) and c["gain"] >= 1.4
            d1 = 0.22 if big else 0.14
            if -0.06 <= u <= d1:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / d1)
                amp = (0.08 + 0.004 * c.get("dent", 16)) if c["soft"] else 0.1 + 0.07 * min(1.4, c["gain"])
                if big:
                    amp = 0.36
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
LIDV = {26.30: 0.40, 27.15: 0.45, 28.40: 0.50, T_MISS: 0.46, 30.40: 0.55, 31.25: 0.60, 33.80: 0.60, 34.65: 0.64,
        35.85: 0.68, T_CRASH: 0.55, T_OVER1: 0.62, 40.30: 0.66, 41.15: 0.70,
        T_PAIRS: 0.45, 43.75: 0.52, 45.25: 0.58, 46.10: 0.64, 47.60: 0.70, 48.45: 0.76, T_OVER2: 0.85, 51.45: 0.90,
        52.95: 0.955, 54.05: 0.96, 55.20: 0.965}


def _lid_keys():
    k = [(0.0, 0.92), (T_SLAM + WAVE_DT, 0.92), (T_SLAM + WAVE_DT + 0.03, 0.0), (1.0, 0.0), (2.2, 0.38),
         (3.2, 0.38), (3.6, 0.75), (T_PILLOW_OFF, 0.95), (T_PILLOW_OFF + 0.03, 0.0), (5.6, 0.0), (6.2, 0.4),
         (6.9, 0.7), (7.6, 0.96), (9.98, 0.96), (10.02, 0.0), (10.55, 0.0), (10.8, 0.42), (11.8, 0.42),
         (11.88, 0.22), (12.3, 0.9), (12.55, 1.0), (T_POP_CAFE - 0.02, 1.0), (T_POP_CAFE + 0.03, 0.0),
         (T_PHOTO[0] + 0.2, 0.0), (T_PHOTO[1], 0.3), (26.2, 0.35)]
    prev = 0.35
    for tc in COUNTS:
        if abs(tc - T_FAIL) < 1e-6:
            break
        if abs(tc - 33.80) < 1e-6:            # 1er silence : ses paupières tombent... cette fois ?
            k += [(31.9, prev), (33.75, 0.88)]
            prev = 0.88
        if abs(tc - 40.30) < 1e-6:            # 2e silence
            k += [(39.4, prev), (40.25, 0.9)]
            prev = 0.9
        if abs(tc - T_PAIRS) < 1e-6:          # la remise à zéro : il rouvre les yeux
            k += [(T_RESET, prev), (T_RESET + 0.06, 0.3), (T_PAIRS - 0.05, 0.36)]
            prev = 0.36
        if abs(tc - T_OVER2) < 1e-6:          # 3e silence : presque
            k += [(48.6, prev), (50.55, 0.93)]
            prev = 0.93
        v = LIDV.get(round(tc, 2), prev)
        k += [(tc + 0.02, prev), (tc + 0.35, v)]
        prev = v
    k += [(T_ZZZ, 0.955), (T_FAIL + 0.3, 0.97), (56.9, 0.8), (57.3, 0.92), (57.75, 0.72),
          (ISSUE_BANG + WAVE_DT - 0.01, 0.75), (ISSUE_BANG + WAVE_DT + 0.03, 0.0), (T_DAWN, 0.0), (60.4, 0.45),
          (61.2, 0.75), (ISSUE, 1.0), (END + 2, 1.0)]
    return sorted(k)


LID = KF(_lid_keys())


def lid_at(t, side):
    v = LID(t)
    if 7.0 < t < 9.98 and side > 0:           # dans le noir il est bien : un œil s'entrouvre pour vérifier
        v -= 0.25 * smooth((t - 8.6) / 0.2) * (1 - smooth((t - 9.2) / 0.2))
    if 19.7 <= t < 20.45:                      # survolté : il cligne en rafale (les phares clignotent)
        ph = (t - 19.7) / 0.17
        v = 1.0 if (ph % 1.0) < 0.45 else 0.0
    for tt in (T_MISS, T_CRASH):               # un incident dans le rêve : un œil tressaille
        if tt <= t < tt + 0.8 and side < 0:
            v -= 0.35 * math.sin(math.pi * (t - tt) / 0.8)
    return clamp01(v)


def eye_base(t):
    if t < T_POP_CAFE:
        return 1.15
    if t < 31.0:
        return 1.5
    if t < ISSUE_BANG:
        return lerp(1.5, 1.25, clamp01((t - 31.0) / 12.0))
    return lerp(1.45, 1.2, clamp01((t - T_DAWN) / 1.5))


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


JIT = KF([(0, 0.0), (T_POP_CAFE - 0.05, 0.0), (T_POP_CAFE + 0.05, 8.0), (T_DARK, 6.0), (23.0, 4.0), (26.0, 2.5),
          (30.0, 1.2), (33.0, 0.6), (36.0, 1.0), (40.0, 0.4), (42.0, 0.0), (99, 0.0)])


def pupil_kind(t):
    if T_POP_CAFE <= t < T_POP_CAFE + 1.9:
        return "spiral"
    if 0 <= t - T_ON < 0.8:
        return "pin"
    return "dot"


def dawn_k(t):
    return smooth((t - T_DAWN) / 1.6)


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


def text_c(d, x, y, s, fs, fill, S, stroke=(40, 30, 70)):
    d.text((x * S, y * S), s, fill=fill, anchor="mm", font=font(fs * S), stroke_width=max(1, int(fs * 0.08 * S)),
           stroke_fill=stroke)



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
        self.t_draw = 0.0
        self.cnt = self._count_events()

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

    # ---------------------------------------------------------- le compteur du rêve
    def _count_events(self):
        ev, n = [], 0
        for tc in COUNTS:
            if tc > T_RESET and n > 0 and not any(e[0] == T_RESET for e in ev):
                ev.append((T_RESET, 0))
                n = 0
            if abs(tc - T_MISS) < 1e-6 or abs(tc - T_FAIL) < 1e-6:
                continue
            if abs(tc - T_CRASH) < 1e-6:
                n -= 2
            elif tc >= T_PAIRS - 1e-6:
                n += 2
            else:
                n += 1
            ev.append((tc + (0.3 if tc < T_PAIRS else 0.25), n))
        return ev

    def count_at(self, t):
        n, last = 0, None
        for (te, v) in self.cnt:
            if te <= t:
                n, last = v, te
        return n, last

    # ---------------------------------------------------------- l'expression de Bounce
    def expr_at(self, t):
        for (a, b, e) in [(2.2, 3.3, "lose"), (10.8, 11.85, "lose"), (T_CAFE_SLAM, T_POP_CAFE + 0.6, "shock"),
                          (T_DARK, T_DARK + 1.0, "shock"), (T_CRASH, T_CRASH + 0.6, "shock"),
                          (T_RESET, T_PAIRS, "shock"), (T_PAIRS, 56.9, "win"), (56.9, 57.55, "shock"),
                          (57.55, ISSUE_BANG, "win"), (ISSUE_BANG, T_DAWN, "shock"), (T_DAWN, 60.6, "lose"),
                          (60.6, 99.0, "win")]:
            if a <= t < b:
                return e
        for (th, g, _x, _y, _k) in self.P.hits:
            if 0 <= t - th < 0.3:
                return "shock"
        return "calm"

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        self.t_draw = t
        Sc0 = S * self.cfg["width"] / W
        Sc = Sc0 * K
        img = Image.new("RGB", (int(W * Sc) + 2, int(H * Sc) + 2), BG)
        d = ImageDraw.Draw(img)
        self.lampL = lit_at(t)
        self.D = dawn_k(t)
        self.L = max(self.lampL, 0.9 * self.D)
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
        self.draw_pillow_on_head(d, t, Sc)
        self.draw_bed_front(d, t, Sc)
        self.draw_cup(d, t, Sc)
        base.HERO["expr"] = self.expr_at(t)
        self.draw_floor_minis(d, t, Sc)
        img = self.draw_beams(img, t, Sc)
        d = ImageDraw.Draw(img)
        self.draw_rings(d, t, Sc)
        self.draw_zs(d, t, Sc)
        self.draw_cloud(d, t, Sc)
        sx, sy = self.P.squash(t)
        if abs(sx - sy) < 0.004:
            base.ball(d, bx * Sc, by * Sc, R * Sc)
        else:
            self.draw_ball(img, bx, by, R * sx, R * sy, Sc)
        self.draw_speech(d, t, Sc)
        shx = shy = 0.0
        for ts in SLAMS:
            u = t - ts
            if 0 <= u < 0.35:
                a = (15 if ts > 50 else 9) * (1 - u / 0.35)
                shx, shy = a * math.sin(u * 90), a * math.cos(u * 70)
        base.HERO["pos"] = ((bx * K - OX) * Sc0, (by * K - OY) * Sc0)
        oy = int(round((-OY + shy) * Sc0))
        dr._image.paste(img, (int(round((-OX + shx) * Sc0)), oy))
        if oy > 0:                                # au-dessus du monde : le plafond
            ImageDraw.Draw(dr._image).rectangle([0, 0, dr._image.size[0], oy + 1], fill=self.c(WALL_D))

    def c(self, col, k=0.52):
        """Couleur d'un objet selon la lumière (lampe, aube, ou clair de lune)."""
        lit = col if self.D < 0.01 else mix(col, (255, 210, 170), 0.12 * self.D)
        return mix(night(col, k), lit, self.L)

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
        rect(d, -300, -300, W, FLOOR_Y, self.c(WALL), S)
        rect(d, -300, -300, W, 120, self.c(WALL_D), S)
        for k in range(-2, 10):
            x = k * 120
            rect(d, x, 120, x + 8, FLOOR_Y, self.c(mix(WALL, WALL_D, 0.5)), S)
        rect(d, -300, FLOOR_Y, W, H, self.c(FLOOR), S)
        for k in range(5):
            y = FLOOR_Y + 22 + k * 60
            d.line([-300 * S, y * S, W * S, y * S], fill=self.c(FLOOR_L), width=max(1, int(4 * S)))
        ell(d, 400, 1330, 360, 44, self.c(RUG), S)
        ell(d, 400, 1330, 300, 32, self.c(mix(RUG, (130, 100, 160), 0.5)), S)

    def draw_window(self, d, t, S):
        x0, y0, x1, y1 = WINDOW
        rect(d, x0 - 12, y0 - 12, x1 + 12, y1 + 12, self.c(WOOD_D), S)
        k = self.D
        sky = mix(SKY, DAWN_SKY, k)
        rect(d, x0, y0, x1, y1, sky, S)
        if k > 0.01:                              # le soleil se lève
            sy_ = lerp(y1 + 50, y0 + 95, k)
            ell(d, (x0 + x1) / 2, sy_, 46, 46, SUN, S)
            rect(d, x0, y1, x1, y1 + 60, self.c(WOOD_D), S)
        if k < 0.99:
            mc = mix(MOON, sky, k)
            ell(d, x1 - 42, y0 + 46, 26, 26, mc, S)
            ell(d, x1 - 32, y0 + 38, 22, 22, sky, S)
            for (sx, sy) in ((x0 + 30, y0 + 50), (x0 + 70, y0 + 120), (x0 + 26, y1 - 30), (x1 - 30, y1 - 42)):
                ell(d, sx, sy, 4, 4, mix((200, 200, 230), sky, k), S)
        d.line([(x0 + x1) / 2 * S, y0 * S, (x0 + x1) / 2 * S, y1 * S], fill=self.c(WOOD_D), width=int(10 * S))
        d.line([x0 * S, (y0 + y1) / 2 * S, x1 * S, (y0 + y1) / 2 * S], fill=self.c(WOOD_D), width=int(10 * S))

    def draw_moon(self, img, t, S):
        """Clair de lune (lampe éteinte), puis la lumière dorée de l'aube, par la fenêtre."""
        k = 1.0 - self.lampL
        if k < 0.02:
            return img
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        x0, y0, x1, y1 = WINDOW
        col = mix((150, 170, 255), (255, 190, 120), self.D)
        od.polygon(P([(x0, y0), (x1, y0), (x1 - 60, 1100), (x0 - 520, 1100)], S),
                   fill=col + (int((26 + 30 * self.D) * k),))
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    def photo_light(self, t):
        a, b = T_PHOTO
        return smooth((t - a) / 0.4) * smooth((b - t) / 0.4)

    def draw_photo(self, d, t, S):
        x0, y0, x1, y1 = PHOTO
        k = max(self.L, self.photo_light(t))

        def cc(col):
            return mix(night(col, 0.52), col, k)
        rect(d, x0, y0, x1, y1, cc(WOOD), S, r=8)
        rect(d, x0 + 14, y0 + 14, x1 - 14, y1 - 14, cc((70, 60, 100)), S)
        sx_, sy_, r = (x0 + x1) / 2, (y0 + y1) / 2 + 8, 62.0
        ell(d, sx_, sy_, 1.4 * r, 1.4 * r, cc(base.dim(SNOOZE, 0.35)), S)
        ell(d, sx_, sy_, r, r, cc(SNOOZE), S)
        for ex in (-0.37, 0.37):
            ell(d, sx_ + ex * r, sy_ - 0.2 * r, 0.29 * r, 0.29 * r, cc((104, 104, 104)), S)
            d.line([(sx_ + ex * r - 0.23 * r) * S, (sy_ - 0.2 * r) * S, (sx_ + ex * r + 0.23 * r) * S,
                    (sy_ - 0.2 * r) * S], fill=cc((40, 40, 40)), width=max(1, int(5 * S)))
        pl = self.photo_light(t)
        if pl > 0.3:
            pts = [(sx_ - 0.28 * r + 0.56 * r * j / 8, sy_ + 0.38 * r + 0.12 * r * math.sin(math.pi * j / 8)) for j in range(9)]
            d.line(P(pts, S), fill=cc((60, 60, 60)), width=max(1, int(6 * S)), joint="curve")
        else:
            d.line([(sx_ - 0.3 * r) * S, (sy_ + 0.42 * r) * S, (sx_ + 0.3 * r) * S, (sy_ + 0.42 * r) * S],
                   fill=cc((70, 70, 70)), width=max(1, int(6 * S)))
        if pl > 0.02:
            for i in range(4):
                ph = ((t - T_PHOTO[0]) * 0.8 + i * 0.25) % 1.0
                zx = x1 - 20 + 50 * ph + 8 * math.sin(i + t * 3)
                zy = y0 + 20 - 150 * ph
                a = pl * clamp01(ph / 0.15) * clamp01((1 - ph) / 0.3)
                d.text((zx * S, zy * S), "Z", fill=mix(self.c(WALL), ZCOL, a), anchor="mm",
                       font=font((60 + 40 * ph) * S))

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


    def pillow_state(self, t):
        """L'oreiller : derrière lui ; 3,3-4,9 s rabattu sur ses yeux ; soufflé par le « BOUNCE » de 4,9 s."""
        rest = (212.0, 940.0, 0.0)
        ix, iy = self.ins_pos(t)
        head = (ix, iy - RI * 0.22, 0.0)
        if t < T_PILLOW:
            return rest, False
        if t < T_PILLOW + 0.4:
            u = smooth((t - T_PILLOW) / 0.4)
            p = bez(rest[:2], (rest[0] - 40, iy - RI - 120), head[:2], u)
            return (p[0], p[1], -1.2 * (1 - u)), True
        if t < T_PILLOW_OFF:
            return head, True
        u = (t - T_PILLOW_OFF) / 0.75
        if u < 1.0:
            p = bez(head[:2], (head[0] + 60, head[1] - 360), rest[:2], u)
            return (p[0], p[1], 2 * math.pi * u), u < 0.6
        return rest, False

    def draw_pillow_shape(self, d, x, y, a, S):
        w, h = 175.0, 112.0
        pts = []
        for j in range(24):
            th = 2 * math.pi * j / 24
            rr = 1.0 + 0.08 * math.cos(4 * th)
            pts.append((x + w / 2 * rr * math.cos(th), y + h / 2 * rr * math.sin(th)))
        pts = rot(pts, x, y, a)
        d.polygon(P(pts, S), fill=self.ci(PILLOW))
        d.line(P(pts + [pts[0]], S), fill=self.ci(PILLOW_D), width=max(1, int(5 * S)))


    def draw_bed_back(self, d, t, S):
        rect(d, BED_X0, 768, BED_X0 + 35, 1180, self.c(WOOD), S)
        ell(d, BED_X0 + 17, 760, 22, 22, self.c(WOOD), S)
        (x, y, a), front = self.pillow_state(t)
        if not front:
            self.draw_pillow_shape(d, x, y, a, S)

    def draw_pillow_on_head(self, d, t, S):
        (x, y, a), front = self.pillow_state(t)
        if front:
            self.draw_pillow_shape(d, x, y, a, S)

    def wave(self, x, t):
        """L'onde qui part du pied du lit après un grand « BOUNCE » et file vers la tête du lit."""
        y = 0.0
        for ts in SLAMS:
            u = t - ts
            if 0 <= u < 0.5:
                front = FOOT_X - (FOOT_X - 150) * u / WAVE_DT
                amp = (40 if ts > 50 else 30) * (1 - u / 0.5)
                y -= amp * math.exp(-((x - front) / 60) ** 2)
        return y

    def bed_dx(self, t):
        return 0.35 * JIT(t) * math.sin(t * 71.0)

    def draw_bed_front(self, d, t, S):
        bdx = self.bed_dx(t)
        rect(d, BED_X0 + 15 + bdx, BED_TOP + 6, BED_X1 + bdx, 1132, self.c(MATT), S, r=10)
        dent = self.P.dent(t)
        top = []
        xa, xb = 150.0, FOOT_X - 6
        for i in range(81):
            x = lerp(xa, xb, i / 80)
            y = BED_TOP + 3 * math.sin(x / 47)
            if x < IX + 145:
                k = smooth((IX + 145 - x) / 115)
                y = lerp(y, IY + 80 + 4 * math.sin(x / 30), k)
            if dent is not None:
                y += dent[1] * math.exp(-((x - dent[0]) / 95) ** 2)
            y += self.wave(x, t)
            top.append((x + bdx, y))
        poly = top + [(xb + bdx, 1140), (xa + bdx, 1140)]
        d.polygon(P(poly, S), fill=self.c(BLANKET))
        d.line(P(top, S), fill=self.c(BLANKET_D), width=max(1, int(6 * S)), joint="curve")
        d.line(P([(280 + bdx, 1112), (xb + bdx, 1112)], S), fill=self.c(BLANKET_D), width=max(1, int(5 * S)))
        rect(d, BED_X0 + bdx, 1132, BED_X1 + 5 + bdx, 1182, self.c(WOOD), S)
        for x in (BED_X0 + 10, BED_X1 - 23):
            rect(d, x + bdx, 1182, x + 26 + bdx, FLOOR_Y, self.c(WOOD_D), S)
        sh = bdx
        for (th, g, _x, _y, k) in self.P.hits:
            u = t - th
            if k == "F" and 0 <= u < 0.35:
                sh += (5 + 14 * max(0.0, g - 0.9)) * math.sin(u * 70) * (1 - u / 0.35)
        rect(d, FOOT_X + sh, 800, FOOT_X + 35 + sh, 1182, self.c(WOOD), S)
        ell(d, FOOT_X + 17 + sh, 792, 22, 22, self.c(WOOD), S)
        d.line([(FOOT_X + 6 + sh) * S, 840 * S, (FOOT_X + 6 + sh) * S, 1120 * S], fill=self.c(WOOD_D),
               width=max(1, int(4 * S)))

    # -------- la tasse : sur ses genoux, catapultée par l'onde, chapeau, puis de retour
    def cup_state(self, t):
        x0, y0, x1, y1 = CUP
        rest = ((x0 + x1) / 2, (y0 + y1) / 2)
        ix, iy = self.ins_pos(t)
        hat = (ix + 4, iy - RI - (y1 - y0) / 2 + 14)
        hop = 0.0
        for (tp, h) in ((T_SLAM + WAVE_DT * 0.63, 30.0), (T_PILLOW_OFF, 24.0)):
            u = t - tp
            if 0 <= u < 0.34:
                hop = h * math.sin(math.pi * u / 0.34)
        if t < T_CUP:
            return rest[0], rest[1] - hop, 0.0, True
        u = (t - T_CUP) / 0.62
        if u < 1.0:
            p = bez(rest, (rest[0] + 30, 640.0), hat, smooth(u) * 0.9 + 0.1 * u)
            return p[0], p[1], -math.pi * smooth(u), u < 0.75
        tf = ISSUE_BANG + WAVE_DT
        if t < tf:
            return hat[0], hat[1], -math.pi + 0.06 * math.sin(t * 40) * (JIT(t) > 1), False
        u = (t - tf) / 0.9
        if u < 1.0:                               # le grand « BOUNCE » l'envoie en l'air ; elle retombe sur ses genoux
            p = bez(hat, (330.0, 520.0), rest, smooth(u))
            return p[0], p[1], -math.pi - 3 * math.pi * smooth(u), False
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
        if T_CUP + 0.62 <= t < T_CUP + 0.8:
            mx, my = self.mouth_pos(t)
            ell(d, mx, my, 16, 12, COFFEE, S)
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
        yawn = smooth((t - 12.2) / 0.6) * (1 - smooth((t - (T_CUP + 0.62)) / 0.08))
        if yawn > 0:
            w, h = lerp(w, 0.32, yawn), lerp(h, 0.36, yawn)
        for (a, b, key) in self.talk:
            if a - 0.05 <= t <= b + 0.05:
                ph = clamp01(math.sin(math.pi * (t - a + 0.05) / max(0.1, b - a + 0.1)))
                o = (0.12 * abs(math.sin((t - a) * 13)) + 0.09) * ph
                if key in ("hyper", "annoy2"):
                    o *= 1.4
                if key == "sleepy":
                    o *= 0.7
                h += o
                w += 0.45 * o
        return w, h

    def talking(self, t):
        return any(a - 0.05 <= t <= b + 0.05 for (a, b, _k) in self.talk)

    def smiling(self, t):
        if t < T_SLAM + WAVE_DT:
            return 1.0
        if 7.4 <= t < T_ON:
            return smooth((t - 7.4) / 0.4)
        if T_ZZZ <= t < T_FAIL + 0.4:
            return smooth((t - T_ZZZ) / 0.5)
        if t >= 61.95:
            return smooth((t - 61.95) / 0.4)
        return 0.0

    def ins_pos(self, t):
        x, y = IX, IY
        y -= jolt(t)
        j = JIT(t)
        if j > 0:
            x += j * math.sin(t * 97.0)
            y += 0.6 * j * math.sin(t * 83.0 + 1.0)
        if 10.95 <= t <= 11.7 or 59.05 <= t <= 59.8:
            x += 5 * math.sin(t * 60)
        if 0 <= t - T_ON < 0.5:
            x -= 14 * math.sin(math.pi * (t - T_ON) / 0.5)
        y += 14 * clamp01((LID(t) - 0.5) / 0.5) if 31.0 < t < ISSUE_BANG or t > 60.5 else 0.0
        return x, y

    def mouth_pos(self, t):
        x, y = self.ins_pos(t)
        return x, y + 0.47 * RI

    def gaze(self, t):
        bx, by = self.bpos
        if T_ON <= t < 11.8:
            lx, ly = self.lamp.bottom(t)
            return lx, ly + 20
        a, b = T_PHOTO
        if a - 0.3 <= t < b + 0.3:
            k = smooth((t - a + 0.3) / 0.4) * (1 - smooth((t - b + 0.1) / 0.4))
            px, py = (PHOTO[0] + PHOTO[2]) / 2, (PHOTO[1] + PHOTO[3]) / 2
            return lerp(bx, px, k), lerp(by, py, k)
        if ISSUE_BANG + WAVE_DT <= t < T_DAWN:     # il balaie toute la chambre de ses phares
            u = (t - ISSUE_BANG - WAVE_DT) / (T_DAWN - ISSUE_BANG - WAVE_DT)
            ang = -2.8 + 4.6 * u
            return IX + 700 * math.cos(ang), IY - 200 + 700 * math.sin(ang)
        if T_POP_CAFE + 0.5 <= t < 20.9:
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

    def beams_on(self, t):
        return (1.0 - self.L) * smooth((t - T_DARK - 0.3) / 0.15) if t >= T_DARK else 0.0

    def draw_insomnia(self, d, t, S):
        x, y = self.ins_pos(t)
        cI = self.ci
        squ = 1.0
        jy = jolt(t)
        if jy > 0:
            squ = 1.0 + 0.08 * min(1.0, jy / 60)
        if 2.3 <= t <= 3.1:
            squ = 1.0 - 0.05 * math.sin(math.pi * (t - 2.3) / 0.8)
        if T_CUP + 0.62 <= t <= T_POP_CAFE:
            squ = 1.0 + 0.07 * math.sin(math.pi * (t - T_CUP - 0.62) / (T_POP_CAFE - T_CUP - 0.62))
        rx, ry = RI * (2 - squ), RI * squ
        cy = y + RI - ry
        ell(d, x, cy, 1.6 * rx, 1.6 * ry, cI(base.dim(I_BODY, 0.22)), S)
        ell(d, x, cy, rx, ry, cI(I_RING), S)
        ell(d, x, cy, rx - 0.13 * RI, ry - 0.13 * RI, cI(I_BODY), S)
        dark = 1.0 - self.L
        bon = self.beams_on(t)
        tgt = self.gaze(t)
        kind = pupil_kind(t)
        for (side, ex, ey, er) in self.eyes(t):
            ey = ey + (cy - y)
            lid = lid_at(t, side)
            ell(d, ex, ey + er * 0.95, er * 1.0, er * 0.32, cI(I_BAG), S)
            glow = mix(cI(I_EYE), (255, 252, 225), max(dark * 0.6, bon))
            if bon > 0.05 and lid < 0.98:            # la source des phares : ses yeux brillent
                flash = 1.0 + 0.8 * math.exp(-(t - T_DARK - 0.3) / 0.25)
                ell(d, ex, ey, er * 1.45 * flash, er * 1.45 * flash, mix(cI(I_BODY), (255, 244, 170), 0.7 * bon), S)
                ell(d, ex, ey, er * 1.18, er * 1.18, mix(cI(I_BODY), (255, 250, 210), 0.9 * bon), S)
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
            if mh < 0.16 and not self.talking(t):
                ell(d, mx, my, max(0.0, mw - 0.055) * RI, inner * RI, cI(I_BODY), S)
            else:
                ell(d, mx, my + mh * RI * 0.45, mw * RI * 0.6, mh * RI * 0.4, cI((200, 90, 100)), S)

    # -------- les phares
    def draw_beams(self, img, t, S):
        k = self.beams_on(t)
        if k < 0.02:
            return img
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        tgt = self.gaze(t)
        flare = 1.0 + 0.7 * math.exp(-(t - ISSUE_BANG - WAVE_DT) / 0.5) * (t >= ISSUE_BANG + WAVE_DT)
        for (side, ex, ey, er) in self.eyes(t):
            lid = lid_at(t, side)
            open_k = 1.0 - lid
            if open_k < 0.02:
                continue
            vx, vy = tgt[0] - ex, tgt[1] - ey
            n = math.hypot(vx, vy) + 1e-6
            ux, uy = vx / n, vy / n
            half = (0.04 + 0.20 * open_k) * flare
            L = min(1150.0, n + 160.0)
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
            dur = 0.45 if g >= 1.4 else 0.28
            if not (0 <= u < dur):
                continue
            if k == "F":
                cx, cy = FOOT_X, y
            else:
                cx, cy = x, y - R
            big = 0.6 + 0.5 * min(1.4, g) + (1.2 if g >= 1.4 else 0.0)
            rr = (26 + 120 * u / dur) * big
            rr = min(rr, 300.0)
            col = mix((255, 255, 255), self.c(WALL), u / dur)
            wdt = max(1, int((7 if g < 1.4 else 12) * S))
            d.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], outline=col, width=wdt)
            for j in range(8):
                a = j * math.pi / 4 + 0.3
                r0, r1 = rr * 0.55, rr * 0.88
                d.line([(cx + r0 * math.cos(a)) * S, (cy + r0 * math.sin(a)) * S, (cx + r1 * math.cos(a)) * S,
                        (cy + r1 * math.sin(a)) * S], fill=col, width=wdt)

    # -------- les Z (gros : on doit voir qu'il dort)
    def draw_zs(self, d, t, S):
        x, y = self.ins_pos(t)
        out = []
        groups = [(-2.4, T_SLAM + WAVE_DT, 0.0), (3.9, T_PILLOW_OFF, 3.9), (7.9, T_ON, 7.9),
                  (T_ZZZ, T_FAIL + 0.4, T_ZZZ), (61.6, 99.0, 61.6)]
        for (a, b, t0) in groups:
            if not (a <= t < b + 0.2):
                continue
            for i in range(3):
                life = 2.1
                if a < 0 or b > 90:
                    ts = t0 + i * 0.7 - (2.1 if a < 0 else 0)
                    u = t - ts
                    if u < 0:
                        continue
                    ph = (u % life) / life
                else:
                    ts = t0 + i * 0.7
                    u = t - ts
                    if u < 0:
                        continue
                    ph = (u % life) / life if b - a > 3 else min(1.0, u / life)
                fs = 88 + 50 * ph
                al = clamp01(ph / 0.15) * clamp01((1 - ph) / 0.3)
                zx, zy = x + 120 + 70 * ph, y - RI - 60 - 170 * ph
                if t >= b:
                    kk = (t - b) / 0.2
                    fs *= 1 + kk
                    al *= 1 - kk
                out.append((zx, zy, fs, al))
        for (zx, zy, fs, a) in out:
            if a > 0.02:
                d.text((zx * S, zy * S), "Z", fill=mix(self.c(WALL), ZCOL, a), anchor="mm", font=font(fs * S),
                       stroke_width=max(1, int(fs * 0.06 * S)), stroke_fill=mix(self.c(WALL), (70, 50, 140), a))

    # -------- les bulles de parole d'Insomnia
    def draw_speech(self, d, t, S):
        ix, iy = self.ins_pos(t)
        for (a, b, key) in self.talk:
            if not (a - 0.05 <= t <= b + 0.4):
                continue
            k = smooth((t - a + 0.05) / 0.12)
            txt = BUBBLE_TXT.get(key, "INSOMNIA!")
            fs = (50 if key == "sleepy" else 58) * (0.7 + 0.3 * k)
            f = font(fs * S)
            tw = f.getlength(txt) / S
            cx, cy = max(80 + tw / 2 + 30, ix + 40), iy - RI - 175
            if t >= T_CUP + 0.6 and t < ISSUE_BANG + 1.2:
                cy -= 40
            x0, x1 = cx - tw / 2 - 30, cx + tw / 2 + 30
            y0, y1 = cy - fs * 0.85, cy + fs * 0.85
            tail = [(cx + 10, y1 - 4), (cx + 50, y1 - 4), (ix + 70, iy - RI + 10)]
            d.polygon(P(tail, S), fill=(20, 20, 28))
            rect(d, x0 - 5, y0 - 5, x1 + 5, y1 + 5, (20, 20, 28), S, r=(y1 - y0) / 2 + 5)
            d.polygon(P([(p[0], p[1] - (0 if i == 2 else 5)) for i, p in enumerate(tail)], S), fill=(255, 255, 255))
            rect(d, x0, y0, x1, y1, (255, 255, 255), S, r=(y1 - y0) / 2)
            d.text((cx * S, cy * S), txt, fill=(30, 30, 40), anchor="mm", font=f)

    # -------- la bulle de pensée : il compte les Bounce
    def cloud_k(self, t):
        if t < T_CLOUD:
            return 0.0
        return smooth((t - T_CLOUD) / 0.5)

    def bubble_shake(self, t):
        sx = 0.0
        for (tt, amp) in ((T_RESET, 22.0), (T_MISS + 0.45, 8.0), (T_CRASH + 0.35, 10.0), (T_OVER2 + 0.3, 16.0)):
            u = t - tt
            if 0 <= u < 0.6:
                sx += amp * math.sin(u * 55) * (1 - u / 0.6)
        return sx

    def draw_cloud(self, d, t, S):
        x, y = self.ins_pos(t)
        if t < T_CLOUD - 0.6:
            return
        bgc = self.c(WALL)
        cx0, cy0, hw, hh = BUB
        if t >= ISSUE_BANG:                       # la bulle éclate : elle se déchire en nuages qui s'envolent (1,6 s)
            u = (t - ISSUE_BANG) / 1.6
            if u >= 1.0:
                return
            for i in range(14):
                a = i * 2 * math.pi / 14 + 0.3
                rr = 120 + 420 * smooth(u)
                px, py = cx0 + rr * math.cos(a) * 1.1, cy0 + rr * math.sin(a) * 0.7 + 200 * u * u
                pr = 70 * (1 - u)
                ell(d, px, py, pr, pr, mix(bgc, CLOUDC, 1 - u), S)
            n, _l = self.count_at(ISSUE_BANG)
            text_c(d, cx0 - 210 + 90 * u, cy0 - 120 + 500 * u * u, str(n), 100, mix(bgc, (90, 70, 150), 1 - u), S,
                   stroke=mix(bgc, CLOUDC, 1 - u))
            pos = base.HERO.get("pos")
            for j in range(6):                    # les Bounce rêvés tombent en pluie
                xx = cx0 - 250 + j * 100 + 30 * math.sin(j)
                yy = GROUND_Y - MINI_R - 200 * u + 1300 * u * u * (0.8 + 0.1 * j)
                if yy < FLOOR_Y + 40:
                    base.ball(d, xx * S, yy * S, MINI_R * 0.75 * S)
            base.HERO["pos"] = pos
            return
        puffs = [(T_CLOUD - 0.6, (x + 100, y - RI - 10, 16)), (T_CLOUD - 0.35, (x + 125, y - RI - 60, 24))]
        for (tp, (px, py, pr)) in puffs:
            if t >= tp:
                k = smooth((t - tp) / 0.2)
                ell(d, px, py, (pr + 4) * k, (pr + 4) * k, CLOUD_E, S)
                ell(d, px, py, pr * k, pr * k, CLOUDC, S)
        k = self.cloud_k(t)
        if k <= 0.01:
            return
        cx = cx0 + self.bubble_shake(t)
        cy = cy0
        sxs, sys_ = hw / 262.0 * k, hh / 172.0 * k
        blobs = [(-180, 10, 82), (-95, -50, 96), (10, -70, 104), (115, -45, 94), (190, 12, 80), (110, 55, 86),
                 (0, 62, 92), (-110, 55, 86)]
        bump = 0.0
        u = t - T_RESET
        if 0 <= u < 0.4:                          # le vrai Bounce cogne le dessous de la bulle
            bump = 40 * math.sin(math.pi * u / 0.4)
        bulge = 0.0
        u2 = t - T_OVER2
        if 0 <= u2 < 1.5:                         # 2e débordement : la bulle se gonfle et crache des Bounce
            bulge = 30 * math.sin(math.pi * u2 / 1.5)
        for (bx, by, br) in blobs:
            yy = cy + by * sys_ - (bump if by > 40 else 0) + (bulge if by > 40 else 0)
            ell(d, cx + bx * sxs, yy, (br + 7) * sxs, (br + 7) * sys_, CLOUD_E, S)
        for (bx, by, br) in blobs:
            yy = cy + by * sys_ - (bump if by > 40 else 0) + (bulge if by > 40 else 0)
            ell(d, cx + bx * sxs, yy, br * sxs, br * sys_, CLOUDC, S)
        if k < 0.6:
            return
        g = GROUND_Y
        fx = FENCE_X + (cx - cx0)
        d.line(P([(cx - 270, g), (cx + 270, g)], S), fill=GRASS, width=max(1, int(9 * S)))
        fc = (150, 104, 70)
        for px_ in (fx - 36, fx + 36):
            rect(d, px_ - 8, g - FENCE_H, px_ + 8, g, fc, S)
        for fy in (g - 86, g - 44):
            rect(d, fx - 56, fy - 7, fx + 56, fy + 7, fc, S)
        self.draw_counter(d, t, S, cx - 225, cy - 120)
        pos = base.HERO.get("pos")
        self.draw_minis(d, t, S, fx, g)
        base.HERO["pos"] = pos

    def draw_counter(self, d, t, S, x0, y0):
        n, last = self.count_at(t)
        u = t - T_RESET
        if 0 <= u < 0.55:                         # l'ancien nombre s'envole, « 0 » le remplace
            n_before, _l = self.count_at(T_RESET - 0.01)
            text_c(d, x0 - 80 * u, y0 - 260 * u + 300 * u * u, str(n_before), 100, mix((90, 70, 150), CLOUDC, u / 0.55),
                   S, stroke=CLOUDC)
            if u > 0.25:
                text_c(d, x0, y0, "0", 100 * smooth((u - 0.25) / 0.2), (200, 50, 70), S, stroke=CLOUDC)
            return
        pop = 1.0
        if last is not None and t - last < 0.3:
            pop = 1.0 + 0.35 * (1 - (t - last) / 0.3)
        red = (last is not None and abs(last - (T_CRASH + 0.3)) < 1e-6 and t - last < 1.0) or (t >= T_RESET and n == 0)
        col = (200, 50, 70) if red else (90, 70, 150)
        text_c(d, x0, y0, str(n), 100 * pop, col, S, stroke=CLOUDC)
        if red and t >= T_CRASH and t < T_RESET:
            text_c(d, x0 + 95, y0 - 10, "-2", 60, (200, 50, 70), S, stroke=CLOUDC)

    def draw_minis(self, d, t, S, fx, g):
        mr = MINI_R
        xw, xl = fx + 135, fx - 135
        done = [tc for tc in COUNTS if tc <= t]
        for tc in done[-3:]:
            uu = t - tc
            pair = tc >= T_PAIRS - 1e-6
            offs = (-72.0, 72.0) if pair else (0.0,)
            hgt = DECRESC.get(round(tc, 2), 160.0)
            jd = 0.62
            if abs(tc - T_FAIL) < 1e-6:           # trop faible : ils ne passent pas, ils retombent de leur côté
                if uu <= 0.5:
                    v = uu / 0.5
                    for o in offs:
                        xx = lerp(xw + o, fx + 56 + mr + (o + 72) * 0.9, min(1.0, v * 1.6))
                        yy = g - mr - hgt * 4 * v * (1 - v)
                        base.ball(d, xx * S, yy * S, mr * S)
                continue
            if abs(tc - T_MISS) < 1e-6:           # il rate : il cogne la barrière, ricoche contre la paroi
                if uu <= 0.9:
                    if uu < 0.3:
                        v = uu / 0.3
                        xx, yy = lerp(xw, fx + 30 + mr, v), g - mr - 80 * 4 * v * (1 - v) - 40 * v
                    else:
                        v = (uu - 0.3) / 0.6
                        xx = lerp(fx + 30 + mr, xw + 40, v)
                        yy = lerp(g - mr - 40, g - mr, v) - 100 * math.sin(math.pi * v)
                    self.mini_squashed(d, xx, yy, mr, S, 1.0 - (0.4 * math.exp(-(uu - 0.3) * 12) if uu >= 0.3 else 0))
                continue
            if abs(tc - T_CRASH) < 1e-6:          # il accroche la barrière et s'étale : le compteur perd 2
                if uu <= 1.2:
                    v = min(1.0, uu / 0.5)
                    if v < 0.6:
                        xx, yy = lerp(xw, fx + 20, v / 0.6), g - mr - 120 * math.sin(math.pi * v / 0.6 * 0.5)
                        base.ball(d, xx * S, yy * S, mr * S)
                    else:
                        w2 = (v - 0.6) / 0.4
                        xx, yy = lerp(fx + 20, fx - 70, w2), lerp(g - mr - 120, g - mr * 0.45, w2 * w2)
                        self.mini_squashed(d, xx, yy, mr, S, 1.0 - 0.5 * w2)
                continue
            if abs(tc - T_OVER1) < 1e-6:          # trop loin : il sort de la bulle (la suite dans la chambre)
                if uu <= 0.5:
                    v = uu / 0.5
                    xx = lerp(xw, BUB[0] - BUB[2] + 20, v)
                    yy = g - mr - 200 * 4 * v * (1 - v)
                    base.ball(d, xx * S, yy * S, mr * S)
                continue
            if uu > jd + 0.7:
                continue
            for o in offs:
                if uu <= jd:
                    v = uu / jd
                    xx = lerp(xw + o, xl + o, v)
                    yy = g - mr - hgt * 4 * v * (1 - v) - (12 if o < 0 else 0) * math.sin(math.pi * v)
                    if tc >= T_OVER2 - 1e-6 and tc < 52.0 and v > 0.6:
                        continue                  # ceux-là tombent hors de la bulle (voir draw_floor_minis)
                    base.ball(d, xx * S, yy * S, mr * S)
                elif tc < T_OVER2 - 1e-6 or tc >= 52.0:
                    w2 = (uu - jd) / 0.7
                    xx = xl + o - 120 * w2
                    yy = g - mr - 30 * math.sin(math.pi * w2)
                    if w2 < 0.85:
                        base.ball(d, xx * S, yy * S, mr * S * (1 - 0.5 * w2))
        # ceux qui attendent leur tour, à droite
        nxt = [tc for tc in COUNTS if tc > t]
        if t >= T_FAIL:
            uu = t - T_FAIL
            if uu > 0.5:
                for o in (-72.0, 72.0):
                    hop = abs(math.sin(t * 8 + o)) * 10
                    xx = fx + 56 + mr + (o + 72) * 0.9
                    base.ball(d, xx * S, (g - mr - hop) * S, mr * S)
                q = smooth((uu - 0.5) / 0.4)
                if q > 0:
                    fsz = (100 + 40 * clamp01((uu - 0.9) / 1.0)) * q
                    text_c(d, fx + 56 + mr + 40, g - 2 * mr - fsz * 0.6, "?", fsz, QCOL, S, stroke=(90, 60, 20))
            return
        if not nxt:
            return
        last = done[-1] if done else None
        if last is not None and (abs(last - T_MISS) < 1e-6 or abs(last - T_CRASH) < 1e-6) and t - last < 0.9:
            return
        appear = (last + 0.25) if last is not None else T_CLOUD + 0.4
        if t < appear:
            return
        a = smooth((t - appear) / 0.25)
        quiet = [(31.9, 33.8), (37.9, 40.3), (48.5, 50.6)]
        waiting = any(qa <= t < qb for (qa, qb) in quiet)
        hop = abs(math.sin(t * (9 if waiting else 5))) * (14 if waiting else 7)
        wx = xw + (14 * math.sin(t * 3) if waiting else 0.0)
        offs = (-72.0, 72.0) if nxt[0] >= T_PAIRS - 1e-6 else (0.0,)
        for o in offs:
            base.ball(d, (wx + o) * S, (g - mr - hop - (12 if o < 0 else 0)) * S, mr * S * (0.5 + 0.5 * a))
        if waiting:
            q0 = [qa for (qa, qb) in quiet if qa <= t < qb][0]
            q = smooth((t - q0 - 0.4) / 0.35)
            fsz = 100 * q
            if fsz > 2:
                text_c(d, wx + 20, g - 2 * mr - fsz * 0.6, "?", fsz, QCOL, S, stroke=(90, 60, 20))

    # -------- les Bounce rêvés qui débordent dans la chambre (jamais sur son visage)
    def floor_minis(self):
        """[(t_sortie, point de sortie, sur sa tête ?, repos par terre)]"""
        out = [(T_OVER1 + 0.5, (BUB[0] - BUB[2] + 20, GROUND_Y - MINI_R - 40), True, (60.0, FLOOR_Y + 30))]
        exits = [(T_OVER2 + 0.4, (FENCE_X - 140, GROUND_Y + 20), (250.0, FLOOR_Y + 34)),
                 (T_OVER2 + 0.45, (FENCE_X - 80, GROUND_Y + 20), (370.0, FLOOR_Y + 40)),
                 (51.45 + 0.4, (FENCE_X - 140, GROUND_Y + 20), (500.0, FLOOR_Y + 36)),
                 (51.45 + 0.45, (FENCE_X - 80, GROUND_Y + 20), (630.0, FLOOR_Y + 42))]
        for (te, p, rest) in exits:
            out.append((te, p, False, rest))
        return out

    def draw_floor_minis(self, d, t, S):
        if t < T_OVER1 + 0.5:
            return
        pos = base.HERO.get("pos")
        ix, iy = self.ins_pos(t)
        tf = ISSUE_BANG + WAVE_DT
        for i, (te, src, head, rest) in enumerate(self.floor_minis()):
            if t < te:
                continue
            u = t - te
            r = ROOM_R
            if head:                              # il tombe, rebondit sur sa tête, puis roule par terre à gauche
                top = (IX + 20, IY - RI - r)
                if u < 0.5:
                    p = bez(src, (src[0] - 20, src[1] - 60), top, u / 0.5)
                elif u < 1.2:
                    p = bez(top, (top[0] - 120, top[1] - 160), rest, (u - 0.5) / 0.7)
                else:
                    p = rest
            else:                                 # il tombe de la bulle par terre, devant le lit
                v = min(1.0, u / 0.7)
                p = bez(src, ((src[0] + rest[0]) / 2, src[1] - 80), rest, v * v)
            if t >= tf:                           # le grand « BOUNCE » : ils sautent et disparaissent
                v = (t - tf) / 0.8
                if v >= 1.0:
                    continue
                p = (p[0] + (i - 2) * 120 * v, p[1] - 700 * v + 900 * v * v)
                r *= 1 - 0.5 * v
            land = u - (1.2 if head else 0.7)
            sq = 0.3 * math.exp(-land * 9) if 0 <= land < 0.5 else 0.0
            self.mini_squashed(d, p[0], p[1], r, S, 1.0 - sq)
        base.HERO["pos"] = pos

    def mini_squashed(self, d, x, y, r, S, k):
        """Un Bounce rêvé écrasé (il a trébuché, ou il vient d'atterrir)."""
        if k > 0.995:
            base.ball(d, x * S, y * S, r * S)
            return
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
    "hook_text_s": 17.6, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.1,
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
