"""
Prototype « baby » v5 : Bounce est la balle du bébé, laissée dans son lit. Sur le matelas il se tait ;
chaque fois qu'il touche du bois (le panneau du lit, un jouet du mobile, la porte), il dit son nom et
un anneau part vers le bébé, qui se réveille d'un cran. La balle monte d'un cran à chaque étape : plus
haut, plus près du bébé, puis contre la porte derrière laquelle Maman écoute (« Who's there? » —
« Bounce. »). Le bébé finit debout, sautille au rythme de la balle et forme le mot sans le son
(« B… », « Bou… », « Boun… »). Maman entre : « Who woke you up? » — silence — « BOUNCE! » —
Maman vire au rouge… et comprend : « His first word! ».

v5 (après le panel de trois juges sur la v4) : plus de rendormissement ; ouverture sur un rebond haut ;
pancarte agrandie et lisible dès l'image 0 ; Maman présente à chaque étape ; bulles accrochées à qui
parle ; mobile tenu par un bras du lit (son fil ne traverse plus l'accroche) ; rien d'important sous
y 1260 ; anneaux épais et courts ; dernière seconde sur un « Bounce » complet.

Le monde est dessiné dans une image plus grande puis recadré (zoom K). La résolution de la config est
libre (aperçu 540×960) : tout est mis à l'échelle. L'audio est calculé sur les instants exacts des
contacts, donc identique quel que soit le nombre d'images par seconde.

    python3 src/stories/baby_v5.py configs/<name>.json [--simulate]
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
BANK_FILES = {"B...": "bab1.wav", "Bou...": "bab2.wav", "Boun...": "bab3.wav",
              "Shhh!": "shh.wav", "Everything okay?": "ok.wav", "Who's there?": "whos.wav",
              "Sweetie?": "sweet.wav", "Who woke you up?": "who.wav", "BOUNCE!": "baby.wav",
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
            d = os.environ.get("BABY_V6_BANK", BANK_DIR)
            BANK[text] = _read(os.path.join(d, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

# ------------------------------------------------------------------ le mot de Bounce, stable
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    # la prise retenue est gardée dans la banque : l'aperçu et le rendu final ont le même son
    cache = os.path.join(os.environ.get("BABY_V6_BANK", BANK_DIR),
                         "hero_%s_%s_%s.wav" % (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"]))
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.70:
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

# ------------------------------------------------------------------ l'accroche
# Le premier « BOUNCE » tombe à 0,12 s ; la voix de l'accroche vient juste après (HOOK_T) et finit
# avant 2,0 s. base.place_words ne doit donc pas réserver le début pour l'accroche : base.hook_audio
# rend None, et ce thème pose lui-même la voix de l'accroche (aucun contact dur pendant qu'elle parle).
HOOK_T = 0.88
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

# ------------------------------------------------------------------ cadrage : monde -> écran (1080×1920)
W, H = 1080, 1920
K = 1.3
OX, OY = 240.0 * K - 126.0, 895.0 * K - 1000.0


def to_screen(x, y):
    return x * K - OX, y * K - OY


# ------------------------------------------------------------------ géométrie (monde)
G = 2600.0
R = 105.0
FL = 1385.0
MT = 1000.0
MY = MT - R
PANEL = (200.0, 240.0)
RPOST = (840.0, 880.0)
KNOB_Y = 622.0
RAIL_Y = 680.0
PG_X = PANEL[1] + R
PG_Y = {"pgl": 875.0, "pgm": 805.0, "pgh": 740.0}
HUB = (400.0, 470.0)              # mobile tenu par un bras fixé au panneau gauche
ARM_R = 70.0
STRING = 46.0
TOY_R = 26.0
TOY_Y = HUB[1] + STRING
MOB_Y = TOY_Y + TOY_R + R
DOOR = (560.0, 860.0, 520.0, FL)  # x0 (côté poignée, la fente), x1 (gonds), y0, y1
DOOR_HIT = (640.0, 525.0)         # Bounce contre la porte (centre)
SLIT = 18.0
SIGN_C = (692.0, 600.0)
SIGN_W, SIGN_H = 290.0, 160.0
BS = 1.85

# couleurs
BG = (8, 8, 12)
WALL = (22, 26, 52)
WALL_D = (16, 18, 38)
FLOOR_C = (52, 36, 32)
FLOOR_L = (70, 50, 42)
WOOD = (150, 104, 70)
WOOD_D = (96, 66, 46)
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
JOY = (255, 158, 186)
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
END = 61.62
ISSUE = 57.4
# (t, genre, gain) : pgl / pgm / pgh = panneau bas / milieu / haut ; mob = un jouet du mobile ; door = la porte
HITS = [
    (0.12, "mob", 1.1),
    (2.15, "pgl", 0.55), (3.40, "pgm", 1.0), (4.55, "pgm", 0.95), (5.85, "pgh", 1.15), (7.05, "mob", 1.0),
    (9.00, "pgh", 1.2), (10.10, "pgm", 1.0), (11.20, "mob", 1.25), (12.50, "pgm", 1.0), (13.30, "pgm", 1.05),
    (14.60, "door", 1.3), (15.40, "door", 1.4), (17.10, "pgm", 0.85),
    (18.05, "pgm", 0.9), (19.40, "pgm", 1.0), (20.20, "mob", 1.05), (21.55, "pgh", 1.1), (22.40, "pgm", 1.0),
    (26.20, "pgh", 1.3), (27.20, "pgm", 1.0), (28.55, "pgm", 0.95), (29.60, "mob", 1.05), (31.75, "pgh", 1.25),
    (33.00, "pgm", 1.0), (34.30, "pgm", 1.0), (35.30, "mob", 1.1), (36.30, "pgh", 1.1), (37.20, "pgm", 1.05),
    (39.80, "pgh", 1.3), (40.75, "pgm", 1.0), (41.50, "mob", 1.05), (42.65, "pgm", 1.0), (43.40, "pgh", 1.1),
    (44.55, "mob", 0.95), (45.30, "pgm", 1.0), (46.40, "pgh", 1.0), (47.15, "mob", 0.9), (48.00, "pgl", 0.8),
    (51.60, "pgm", 0.9), (52.40, "pgm", 0.95), (53.20, "pgh", 1.0), (54.10, "pgm", 1.05), (54.90, "pgh", 1.1),
    (55.70, "pgm", 1.15), (56.45, "pgh", 1.4),
    (59.30, "pgm", 0.8), (60.82, "pgh", 1.05),
]
# contacts mous imposés (t, x, creux) ; les « slam » (creux profond) soulèvent le bébé
SOFT = [(0.52, 378, 20), (1.30, 378, 18), (5.30, 372, 44), (11.95, 420, 46),
        (24.30, 384, 12), (24.90, 380, 10), (25.50, 384, 10),
        (38.80, 384, 12), (39.30, 380, 10),
        (50.30, 410, 14), (51.10, 400, 16), (61.27, 396, 16)]
SLAMS = [(5.30, 30), (11.95, 44)]
LINES = [(7.95, "Shhh!", "shh"), (16.30, "Who's there?", "whos"), (24.60, "Sweetie?", "sweet"),
         (28.15, "B...", "bab1"), (33.95, "Bou...", "bab2"), (38.15, "Boun...", "bab3"),
         (48.90, "Who woke you up?", "who"), (50.75, "BOUNCE!", "b"),
         (ISSUE, "His first word!", "first"), (58.65, "BOUNCE!", "b2"), (60.20, "BOUNCE!", "b3")]
LINE_WHO = {"shh": "mom_off", "whos": "mom_off", "sweet": "mom_off", "bab1": "babble", "bab2": "babble",
            "bab3": "babble", "who": "mom", "b": "baby", "first": "mom", "b2": "baby", "b3": "baby"}
MOUTH = []
# Bounce réagit à ce qui se passe (visage) : (début, fin, expression)
EXPR = [(6.6, 8.95, "shock"), (14.6, 17.1, "shock"), (23.45, 26.2, "shock"), (30.2, 31.75, "shock"),
        (38.35, 39.8, "shock"), (43.3, 46.6, "shock"), (50.75, 51.6, "shock"), (51.6, ISSUE, "lose"),
        (ISSUE, 99.0, "win")]
FLAT = [(24.0, 26.4), (38.45, 40.0)]
SIGN_FALL_T = 15.45


def soft_x(t, k=0):
    """Bounce se rapproche du bébé au fil des étapes (x du centre sur le matelas)."""
    if any(a - 0.2 <= t < b + 0.1 for (a, b) in FLAT):
        x = 382.0
    elif t < 10.8:
        x = 380.0
    elif t < 12.0:
        x = 405.0
    elif t < 17.2:
        x = 425.0
    elif t < 19.6:
        x = 468.0
    elif t < 51.4:
        x = 480.0
    elif t < ISSUE:
        x = 378.0
    else:
        x = 430.0
    return x + 8 * (k % 2) - 4


class Mobile:
    STAR_OFF = 11.20

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
                if kind == "mob" and abs(t - Mobile.STAR_OFF) < 1e-6:
                    tx = [a for a in toys if a[0] == 0][0][1]
                else:
                    tx = min(toys, key=lambda a: abs(a[1] - 410.0) - 0.3 * a[3])[1]
                x = max(345.0, min(455.0, tx))
                cs.append({"t": t, "x": x, "y": MOB_Y, "axis": "y", "soft": False, "gain": g, "kind": kind})
            elif kind == "door":
                cs.append({"t": t, "x": DOOR_HIT[0], "y": DOOR_HIT[1], "axis": "z", "soft": False, "gain": g,
                           "kind": kind})
            else:
                cs.append({"t": t, "x": PG_X, "y": PG_Y[kind], "axis": "x", "soft": False, "gain": g, "kind": kind})
        for (t, x, dent) in SOFT:
            cs.append({"t": t, "x": float(x), "y": MY + dent, "axis": "y", "soft": True, "gain": 0, "kind": "mat"})
        # le mobile et la porte se touchent en montant et se quittent en descendant
        for (t, kind, g) in HITS:
            if kind in ("mob", "door"):
                d = 0.36 if kind == "mob" else 0.4
                for dtm in (-d, d):
                    tt = t + dtm
                    if not any(abs(c["t"] - tt) < 0.3 for c in cs):
                        sx_ = 392.0 if kind == "door" else soft_x(tt)
                        cs.append({"t": tt, "x": sx_, "y": MY + 16, "axis": "y", "soft": True, "gain": 0,
                                   "kind": "mat"})
        cs.sort(key=lambda c: c["t"])
        start = {"t": -0.30, "x": 400.0, "y": MY + 18}
        full = []
        prev = start
        k = 0
        for c in cs:
            if prev.get("kind") == "pgh" and c["t"] - prev["t"] > 0.7:
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
        self.after = {"t": 61.97, "x": 396.0, "y": MY + 18}
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
                amp = (0.16 if c["y"] > MY + 30 else 0.1) if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                elif c["axis"] == "x":
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
                else:                  # contre la porte : il s'aplatit face à nous
                    sx *= 1 + 0.12 * kk; sy *= 1 + 0.12 * kk
        return sx, sy

    def ball(self, t):
        x, y = self.pos(t)
        sx, sy = self.squash(t)
        return x, y, R * sx, R * sy


# ------------------------------------------------------------------ le bébé
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
    "flat": {"hip": (770, -46), "sh": (640, -46), "head": (580, -52), "h1": (600, -20), "h2": (620, -18),
             "f1": (840, -30), "f2": (830, -20)},
}
POSES = {n: {k: (1351 - v[0], v[1]) for k, v in p.items()} for n, p in _LYING.items()}
POSES.update({
    "sit": {"hip": (712, -52), "sh": (712, -205), "head": (712, -282), "h1": (664, -122), "h2": (760, -122),
            "f1": (630, -18), "f2": (652, -12)},
    "half": {"hip": (716, -170), "sh": (712, -305), "head": (712, -382), "h1": (688, -322), "h2": (746, -322),
             "f1": (690, -14), "f2": (746, -14)},
    "stand": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (688, -322), "h2": (746, -322),
              "f1": (696, -10), "f2": (740, -10)},
    "cheer": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (650, -470), "h2": (776, -470),
              "f1": (696, -10), "f2": (740, -10)},
    "down": {"hip": (712, -205), "sh": (708, -340), "head": (708, -416), "h1": (672, -222), "h2": (748, -222),
             "f1": (694, -10), "f2": (738, -10)},
    "reach": {"hip": (714, -205), "sh": (716, -340), "head": (718, -416), "h1": (690, -480), "h2": (742, -490),
              "f1": (696, -10), "f2": (740, -10)},
    "point": {"hip": (716, -205), "sh": (706, -340), "head": (700, -416), "h1": (566, -215), "h2": (746, -322),
              "f1": (696, -10), "f2": (740, -10)},
    "up": {"hip": (716, -205), "sh": (712, -340), "head": (712, -416), "h1": (664, -520), "h2": (764, -520),
           "f1": (696, -10), "f2": (740, -10)},
})
POSES["lifted"] = {k: (v[0] - 24, v[1] - 140) for k, v in POSES["up"].items()}

BABY_KEYS = [(0.0, "lie", 0.0), (0.3, "armup", 0.12), (1.9, "lie", 0.5), (4.6, "headup", 0.2), (5.2, "lie", 0.3),
             (5.95, "side", 0.3), (10.2, "curl", 0.45), (12.0, "fours", 0.35), (17.2, "sit", 0.3),
             (19.5, "half", 0.4), (20.3, "stand", 0.4), (24.1, "flat", 0.25), (26.35, "stand", 0.25),
             (30.6, "down", 0.25), (31.9, "stand", 0.3), (35.35, "cheer", 0.2), (36.1, "stand", 0.3),
             (38.5, "flat", 0.2), (39.95, "stand", 0.25), (43.55, "down", 0.25), (44.9, "reach", 0.3),
             (46.8, "stand", 0.3), (50.75, "point", 0.2), (51.9, "stand", 0.4), (57.0, "up", 0.4),
             (58.4, "lifted", 0.6)]
BABY_HOPS = [(5.35, 30), (12.0, 44),
             (21.6, 30), (22.45, 36), (26.4, 60), (27.25, 34), (28.6, 40), (29.65, 44), (33.05, 30), (34.35, 38),
             (35.35, 52), (36.35, 40), (37.25, 46), (40.0, 60), (40.8, 34), (41.55, 40), (42.7, 46),
             (52.45, 18), (54.15, 18), (60.25, 34)]
BABY_JOLTS = [(0.3, 18), (2.2, 10), (3.45, 14), (4.6, 10), (5.9, 12), (7.1, 8), (9.05, 14), (10.15, 10),
              (11.25, 12), (12.55, 8), (14.65, 14), (15.45, 14), (17.15, 10), (51.65, 6)]
BABY_MOVES = [(0.4, 1.7, 3, 14, "trem"), (3.5, 4.4, 3, 14, "trem"), (6.2, 8.9, 7, 2.6, "wig"),
              (9.1, 10.0, 18, 3.2, "kick"), (10.6, 11.9, 7, 1.6, "rock"), (12.4, 17.1, 12, 1.5, "rock"),
              (17.5, 19.4, 9, 0.9, "sway"), (24.15, 26.3, 3, 12, "trem"), (30.7, 31.8, 2, 14, "trem"),
              (38.6, 39.9, 3, 12, "trem")]
BABY_DIR = KF(0.0, [(15.3, 0.0), (15.5, 1.0), (17.1, 1.0), (17.3, -1.0), (20.3, -1.0), (20.5, 0.0),
                    (30.2, 0.0), (30.4, 1.0), (31.9, 1.0), (32.1, 0.0), (43.4, 0.0), (43.6, 1.0),
                    (46.7, 1.0), (46.9, -1.0), (57.0, -1.0), (57.3, -0.5)])
POSES["lifted"] = {k: (v[0] - 24, v[1] - 60) for k, v in POSES["up"].items()}


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
        out["upright"] = name in ("sit", "half", "stand", "cheer", "down", "reach", "point", "up", "lifted")
        return out


# ------------------------------------------------------------------ les Z
class Zs:
    def __init__(self, burst_times):
        sp = []
        t = -2.4
        while t < 17.2:
            if t < 3.45:
                s, per = 1.0, 0.9
            elif t < 6.0:
                s, per = 0.7, 1.0
            elif t < 10.2:
                s, per = 0.5, 1.1
            else:
                s, per = 0.36, 1.1
            sp.append((t, s))
            t += per
        self.spawns = sp
        self.bursts = burst_times
        self.life = 2.2

    def visible(self, t, head):
        out = []
        if t >= 17.2:
            return out
        for (ts, size) in self.spawns:
            age = t - ts
            if age < 0 or age > self.life:
                continue
            b = [tb for tb in self.bursts if ts < tb <= t]
            k = age / self.life
            x = min(800.0, head[0] - 30 + 30 * k * size + 12 * math.sin(ts * 3.1 + age * 2.2))
            y = head[1] - 60 - 140 * k
            alpha = clamp01(age / 0.3) * clamp01((self.life - age) / 0.6)
            if 10.2 <= ts:
                alpha *= 0.55 + 0.45 * (math.sin(t * 17.0 + ts) > 0)
            fs = (40 + 44 * k) * size + 18
            if b:
                u = t - b[-1]
                if u > 0.35:
                    continue
                ang = ts * 2.7
                x += math.cos(ang) * 160 * u / 0.35
                y += math.sin(ang) * 140 * u / 0.35 - 60 * u
                alpha *= 1 - u / 0.35
                fs *= 1 + 0.6 * u / 0.35
            if t < SIGN_FALL_T:                # sous la pancarte tant qu'elle est sur la porte
                y = max(y, 715.0)
            out.append((min(x, 815.0), y, fs, alpha))
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
        reach = [t + 0.15 for (t, g, x, y, k) in self.P.hits if g >= 0.6] + [s + 0.1 for (s, h) in SLAMS]
        self.Z = Zs(sorted(reach))
        self.door_o = KF(0.0, [(23.75, 0.0), (24.0, 0.34), (25.85, 0.34), (26.05, 0.0),
                               (30.4, 0.0), (30.65, 0.6), (31.6, 0.6), (31.85, 0.0),
                               (38.45, 0.0), (38.55, 0.34), (39.5, 0.34), (39.65, 0.0), (44.6, 0.0), (44.95, 1.0)])
        self.hall = KF(0.0, [(6.6, 0.0), (6.75, 1.0), (10.3, 1.0), (10.45, 0.0), (15.5, 0.0), (15.65, 1.0),
                             (17.6, 1.0), (17.75, 0.0), (23.45, 0.0), (23.6, 1.0), (26.05, 1.0), (26.2, 0.0),
                             (30.2, 0.0), (30.35, 1.0), (32.0, 1.0), (32.15, 0.0), (38.35, 0.0), (38.45, 1.0),
                             (39.65, 1.0), (39.8, 0.0), (43.3, 0.0), (43.45, 1.0)])
        self.handle = KF(0.0, [(23.6, 0.0), (23.8, 48.0), (24.0, 48.0), (26.0, 48.0), (26.1, 0.0),
                               (30.2, 0.0), (30.4, 48.0), (31.85, 48.0), (31.95, 0.0),
                               (38.4, 0.0), (38.5, 48.0), (39.65, 48.0), (39.75, 0.0),
                               (44.1, 0.0), (44.45, 48.0)])
        self.shadows = [(6.8, 7.0, 10.0, 10.3), (15.6, 15.8, 17.5, 17.75), (23.5, 23.7, 26.0, 26.2),
                        (30.2, 30.4, 32.0, 32.2), (38.35, 38.45, 39.6, 39.75), (43.4, 43.6, 44.9, 45.0)]
        self.door_shake = [h[0] for h in self.P.hits if h[4] == "door"]
        # Maman : la tête dans l'entrebâillement, un pas dans la chambre, puis l'entrée
        self.peek = KF(0.0, [(23.95, 0.0), (24.05, 1.0), (25.8, 1.0), (25.9, 0.0),
                             (38.5, 0.0), (38.6, 1.0), (39.45, 1.0), (39.55, 0.0)])
        self.step = KF(0.0, [(30.6, 0.0), (31.0, 1.0), (31.3, 1.0), (31.65, 0.0)])
        self.step_vis = KF(0.0, [(30.55, 0.0), (30.6, 1.0), (31.75, 1.0), (31.8, 0.0)])
        self.beam = [(24.0, 25.8, 1.0), (38.55, 39.5, 1.6)]
        self.mom_vis = KF(0.0, [(44.9, 0.0), (44.95, 1.0)])
        self.mom_col = KF(0.0, [(45.45, 0.0), (46.05, 1.0)])
        self.mom_x = KF(640.0, [(45.45, 640.0), (46.8, 560.0), (51.6, 560.0), (52.2, 500.0), (57.0, 500.0),
                                (57.6, 425.0)])
        self.mom_dir = KF(-1.0, [(46.5, -1.0), (46.9, 1.0), (51.6, 1.0), (52.2, -1.0), (57.0, -1.0), (57.4, 1.0)])
        self.mom_lean = KF(0.0, [(46.8, 0.0), (47.3, 12.0), (51.6, 12.0), (52.2, -14.0), (53.2, -14.0),
                                 (53.6, -22.0), (57.0, -22.0), (57.4, 0.0), (58.4, 0.0), (59.0, 6.0),
                                 (60.2, 6.0), (60.6, 2.0), (61.2, 6.0)])
        anger = [(51.6, 0.25), (52.4, 0.45), (53.2, 0.6), (54.1, 0.75), (54.9, 0.85), (55.7, 0.93), (56.45, 1.0),
                 (ISSUE, 0.0)]
        self.mom_anger = KF(0.0, steps(0.0, anger, 0.14) + [(60.3, 0.0), (61.5, 0.5)])
        self.mom_joy = KF(0.0, [(ISSUE, 0.0), (ISSUE + 0.12, 1.0), (60.3, 1.0), (61.5, 0.25)])
        self.mom_hops = [(50.8, 20), (ISSUE + 0.05, 60), (60.25, 30)]
        self.mom_arms = [(44.95, "hang"), (46.8, "rail"), (52.4, "grab"), (ISSUE, "up"), (58.4, "lift")]
        self.grab = (52.4, ISSUE - 0.05)
        # la pancarte, scotchée sur la porte : elle penche au premier coup contre la porte, tombe au second
        self.sign_rot = KF(-6.0, [(14.6, -6.0), (14.75, 20.0), (15.1, 12.0)])
        self.sign_fall = (15.45, 16.2)
        self.paci_t = 3.45
        self.blanket_t = 9.3
        self.rings = [(t, g, x, y) for (t, g, x, y, k) in self.P.hits]
        self.subs = []

    def set_narr(self, narr):
        out = []
        for i, n in enumerate(narr):
            words = len(n["text"].split())
            end = max(n["end"] + 0.45, n["start"] + 0.5 + 0.3 * words)
            if i + 1 < len(narr):
                end = min(end, narr[i + 1]["start"] - 0.05)
            for (fa, fb) in FLAT:            # le bébé se jette à plat en plein babil : la bulle s'arrête net
                if n["start"] < fa < end:
                    end = fa + 0.05
            out.append((LINE_WHO.get(n["key"], "mom"), n["text"], n["start"], end))
        for (a, b, txt) in MOUTH:
            out.append(("mouth", txt, a, b))
        self.subs = sorted(out, key=lambda s: s[2])


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
        best, bd = 0.9, 1e9
        for (th, g, _x, _y, _k) in self.sc.P.hits:
            if abs(th - t0) < bd:
                best, bd = g, abs(th - t0)
        return best

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        sc = self.sc
        S = S * self.cfg["width"] / W            # échelle de l'écran (aperçu 540 px : moitié)
        Sw = S * K
        wimg = Image.new("RGB", (int((W + OX) * S) + 2, int((H + OY) * S) + 2), BG)
        wd = ImageDraw.Draw(wimg)
        self.draw_room(wd, t, Sw)
        self.draw_door(wd, t, Sw)
        self.draw_sign(wimg, wd, t, Sw, falling=False)
        self.draw_light_wall(wd, t, Sw)
        self.draw_mom(wd, t, Sw, body=True)
        self.draw_crib_back(wd, t, Sw)
        self.draw_beam(wd, t, Sw)
        self.draw_mom(wd, t, Sw, body=False)
        self.draw_mobile(wd, t, Sw)
        self.draw_sign(wimg, wd, t, Sw, falling=True)
        self.draw_floor(wd, t, Sw)
        self.draw_light_floor(wd, t, Sw)
        self.draw_under(wd, t, Sw)
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
        base.HERO["expr"] = self.expr_at(t)
        if abs(brx - bry) < 0.5:
            base.ball(wd, bx * Sw, by * Sw, brx * Sw)
        else:
            self.draw_ball(wd, bx, by, brx, bry, Sw)
        crop = wimg.crop((int(OX * S), int(OY * S), int(OX * S) + int(W * S), int(OY * S) + int(H * S)))
        dr._image.paste(crop, (0, 0))
        self.draw_bubbles(dr, t, S)

    def expr_at(self, t):
        """Le visage de Bounce suit les événements : yeux ronds quand Maman approche ou quand il cogne fort,
        inquiet devant sa colère, sourire après « His first word! », blasé le reste du temps."""
        for (a, b, e) in EXPR:
            if a <= t < b:
                return e
        for (th, g, _x, _y, _k) in self.sc.P.hits:
            if g >= 1.25 and 0 <= t - th < 0.6:
                return "shock"
        return "calm"

    def draw_beam(self, dr, t, S):
        """Le faisceau du couloir qui balaie le lit quand la porte s'entrouvre."""
        for (a, b, sweeps) in self.sc.beam:
            if not (a <= t <= b):
                continue
            u = (t - a) / (b - a)
            k = math.sin(math.pi * clamp01(u * 1.15))
            ph = 0.5 - 0.5 * math.cos(2 * math.pi * sweeps * u)
            bx = lerp(560.0, 270.0, ph)
            col = mix((58, 42, 34), (236, 196, 128), 0.55 * k)
            dr.polygon(poly([(DOOR[0] + 4, RAIL_Y + 8), (DOOR[0] + 30, RAIL_Y + 8), (bx + 70, MT),
                             (bx - 70, MT)], S), fill=col)
            for kk in range(13):
                x = PANEL[1] + 22 + kk * 46
                dr.line([x * S, (RAIL_Y + 8) * S, x * S, MT * S], fill=(120, 86, 60), width=int(6 * S))

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

    def draw_floor(self, dr, t, S):
        rect(dr, 0, FL, 1000, 1620, FLOOR_C, S)
        yb = FL + 18
        for k in range(8):
            dr.line([0, yb * S, 1000 * S, yb * S], fill=FLOOR_L, width=int(3 * S))
            yb += 20 + 8 * k
        ell(dr, 560, 1525, 380, 80, (92, 80, 128), S)
        ell(dr, 560, 1525, 320, 60, (110, 96, 150), S)

    def draw_under(self, dr, t, S):
        """Sous le lit : un panier de jouets et une pile de livres (décor)."""
        bx0, bx1, by0 = 270.0, 520.0, 1250.0
        for (cx, cy, r, c) in ((330, 1240, 46, (200, 120, 140)), (420, 1228, 52, (150, 110, 80)),
                               (480, 1246, 38, (120, 170, 210))):
            ell(dr, cx, cy, r, r, c, S)
        ell(dr, 420, 1190, 20, 20, (150, 110, 80), S); ell(dr, 395, 1190, 14, 14, (150, 110, 80), S)
        dr.polygon(poly([(bx0, by0), (bx1, by0), (bx1 - 20, FL), (bx0 + 20, FL)], S), fill=(176, 134, 82))
        for k in range(6):
            yy = by0 + 22 * k
            dr.line([(bx0 + 4 + k * 3.5) * S, yy * S, (bx1 - 4 - k * 3.5) * S, yy * S], fill=(140, 102, 60),
                    width=int(4 * S))
        for (y0, c) in ((FL - 30, (200, 90, 80)), (FL - 58, (90, 150, 200)), (FL - 84, (220, 190, 80))):
            rect(dr, 560 - 20, y0, 680, y0 + 26, c, S, r=4)

    def door_left(self, t):
        o = self.sc.door_o(t)
        return DOOR[0] + SLIT + (DOOR[1] - DOOR[0] - SLIT) * o

    def door_dx(self, t):
        dx = 0.0
        for t0 in self.sc.door_shake:
            u = t - t0
            if 0 <= u <= 0.45:
                dx += 9 * math.sin(u * 60) * (1 - u / 0.45)
        return dx

    def shadow_k(self, t):
        k = 0.0
        for (ta, tb_, tc, td) in self.sc.shadows:
            k = max(k, clamp01((t - ta) / (tb_ - ta)) * (1 - clamp01((t - tc) / (td - tc))))
        return k

    def draw_light_floor(self, dr, t, S):
        o, h = self.sc.door_o(t), self.sc.hall(t)
        if h < 0.05:
            return
        x0, x1 = DOOR[0], DOOR[1]
        col = mix(FLOOR_C, (226, 178, 104), h)
        if o < 0.05:
            rect(dr, x0 + 4, FL - 9, x1 - 4, FL, mix((20, 18, 22), WARM, h), S)
            dr.polygon(poly([(x0, FL), (x1, FL), (x1 + 40, FL + 46), (x0 - 40, FL + 46)], S), fill=col)
        else:
            left = self.door_left(t)
            reach = 260 * min(1.0, o * 1.3)
            rect(dr, x0 + 4, FL - 9, x1 - 4, FL, mix((20, 18, 22), WARM, h), S)
            dr.polygon(poly([(x0, FL), (left, FL), (left - 40, FL + 60), (x0 - 40 - reach, FL + 60)], S),
                       fill=mix(FLOOR_C, (226, 178, 104), 0.8 * h))
        ks = self.shadow_k(t)
        if ks > 0.02:
            off = 0.0
            for (ta, tb_, tc, td) in self.sc.shadows:
                if ta <= t <= td and (tc - tb_) < 0.2:
                    off = -90 + 180 * clamp01((t - ta) / (td - ta))
            for fx in (x0 + 70, x0 + 140):
                rect(dr, fx + off, FL - 9, fx + off + 48, FL + 40, mix(col, (16, 12, 14), ks), S)

    def draw_door(self, dr, t, S):
        x0, x1, y0, y1 = DOOR
        sc = self.sc
        o, h = sc.door_o(t), sc.hall(t)
        dx = self.door_dx(t)
        rect(dr, x0 - 12, y0 - 12, x1 + 12, y1, WOOD_D, S)
        light = mix((26, 22, 26), mix(WARM, (214, 132, 64), clamp01(o * 1.5)), h)
        rect(dr, x0, y0, x1, y1, light, S)
        left = self.door_left(t)
        ks = self.shadow_k(t)
        if ks > 0.02 and o < 0.05 and h > 0.05:
            rect(dr, x0, 760, left, 1000, mix(light, (14, 12, 14), ks), S)
        # la tête de Maman dans l'entrebâillement
        if sc.peek(t) > 0.02:
            self.mom_shape(dr, t, S, 640.0, SIL, 0.78, -8.0, 0.0, -1.0, body=True, sil=True)
        if sc.step_vis(t) > 0.5:
            st = sc.step(t)
            self.mom_shape(dr, t, S, lerp(650.0, 600.0, st), SIL, lerp(0.78, 0.9, st), 0.0, 0.0, -1.0,
                           body=True, sil=True)
        if sc.mom_vis(t) > 0.5 and sc.mom_col(t) < 0.02:
            self.mom_shape(dr, t, S, 640.0, SIL, 0.78, 0.0, 0.0, -0.3, body=True, sil=True)
        if x1 - left > 2:
            rect(dr, left + dx, y0, x1 + dx, y1, (84, 60, 48), S)
            if x1 - left > 80:
                rect(dr, left + 18 + dx, y0 + 24, x1 - 18 + dx, y0 + 200, (96, 70, 56), S)
                rect(dr, left + 18 + dx, y0 + 236, x1 - 18 + dx, y1 - 30, (96, 70, 56), S)
            if o < 0.3:
                ang = math.radians(sc.handle(t))
                px, py = left + 48 + dx, 640.0
                ex, ey = px - 52 * math.cos(ang), py + 52 * math.sin(ang)
                ell(dr, px, py, 14, 14, (60, 46, 36), S)
                capsule(dr, (px, py), (ex, ey), 11, (236, 222, 178), S)
                ell(dr, px, py, 7, 7, (200, 186, 140), S)

    def draw_light_wall(self, dr, t, S):
        o = self.sc.door_o(t)
        h = self.sc.hall(t)
        if h < 0.05:
            return
        x0 = DOOR[0]
        if o < 0.05:
            for i, w in enumerate((70, 40, 18)):
                col = mix(WALL, (214, 168, 96), h * (0.14 + 0.14 * i))
                dr.polygon(poly([(x0 - 10, DOOR[2] + 10), (x0 - 10 - w, DOOR[2] + 60), (x0 - 10 - w, 1000),
                                 (x0 - 10, 1000)], S), fill=col)
            return
        col = mix(WALL, (110, 98, 96), h * min(1.0, o * 1.3))
        dr.polygon(poly([(x0, DOOR[2] + 30), (250, 700), (250, 1000), (x0, 1000)], S), fill=col)

    def draw_sign(self, img, dr, t, S, falling):
        sc = self.sc
        is_fall = t >= sc.sign_fall[0]
        if is_fall != falling:
            return
        simg, pad = sign_image(S)
        ang = sc.sign_rot(t)
        dx = self.door_dx(t)
        px, py = SIGN_C[0] - SIGN_W / 2, SIGN_C[1] - SIGN_H / 2
        if t < 14.6:
            cx, cy = SIGN_C[0] + dx, SIGN_C[1]
        else:
            ar = math.radians(ang)
            hx, hy = SIGN_W / 2, SIGN_H / 2
            cx, cy = px + hx * math.cos(ar) - hy * math.sin(ar) + dx, py + hx * math.sin(ar) + hy * math.cos(ar)
        if is_fall:
            u = clamp01((t - sc.sign_fall[0]) / (sc.sign_fall[1] - sc.sign_fall[0]))
            cy += 480 * u * u
            cx += 30 * math.sin(u * 6)
            ang += 50 * u
            if cy > MT + 40:
                return
        rot = simg.rotate(-ang, resample=Image.BICUBIC, expand=True)
        img.paste(rot, (int(cx * S - rot.width / 2), int(cy * S - rot.height / 2)), rot)
        if not is_fall:
            ar = math.radians(ang)

            def corner(ddx, ddy):
                return (cx + ddx * math.cos(ar) - ddy * math.sin(ar), cy + ddx * math.sin(ar) + ddy * math.cos(ar))
            tapes = [corner(-SIGN_W / 2 + 8, -SIGN_H / 2 + 4)]
            if t < 14.6:
                tapes.append(corner(SIGN_W / 2 - 8, -SIGN_H / 2 + 4))
            for (x, y) in tapes:
                dr.polygon(poly([(x - 22, y - 7), (x + 22, y - 12), (x + 24, y + 6), (x - 20, y + 10)], S),
                           fill=(214, 208, 180))

    def draw_crib_back(self, dr, t, S):
        """Dossier plein derrière les barreaux : ce qui est derrière le lit (porte, Maman) ne se voit qu'au-dessus."""
        rect(dr, PANEL[1], RAIL_Y, RPOST[0], MT, (58, 42, 34), S)
        dr.rectangle([PANEL[1] * S, (RAIL_Y - 8) * S, RPOST[0] * S, (RAIL_Y + 8) * S], fill=WOOD_D)
        for k in range(13):
            x = PANEL[1] + 22 + k * 46
            dr.line([x * S, (RAIL_Y + 8) * S, x * S, MT * S], fill=(120, 86, 60), width=int(6 * S))

    def draw_crib_front(self, dr, t, S, bx, by, bry):
        rect(dr, PANEL[0], KNOB_Y, PANEL[1], FL, WOOD, S)
        rect(dr, PANEL[0] + 6, 660, PANEL[1] - 6, MT - 10, (166, 118, 82), S)
        rect(dr, RPOST[0], KNOB_Y, RPOST[1], FL, WOOD, S)
        for kx in ((PANEL[0] + PANEL[1]) / 2, (RPOST[0] + RPOST[1]) / 2):
            ell(dr, kx, KNOB_Y - 10, 24, 24, WOOD, S)
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
        """Anneaux épais et courts : ils s'arrêtent avant de devenir des traits gris."""
        for (t0, g, x, y) in self.sc.rings:
            u = t - t0
            if u < 0 or u > 0.6:
                continue
            rmax = (R + 40 + 120 * g) if g < 0.6 else (R + 60 + 230 * g)
            r = R + 10 + 900 * u
            if r > rmax:
                continue
            k = 1 - (r - R) / max(1.0, rmax - R)
            if k < 0.3:
                continue
            col = mix(WALL, (250, 250, 255), 0.6 + 0.4 * k)
            w = (12 + 10 * min(1.3, g)) * (0.6 + 0.4 * k)
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(2, int(w * S)))

    def draw_mobile(self, dr, t, S):
        # le bras du mobile, fixé en haut du panneau gauche
        ax = (PANEL[0] + PANEL[1]) / 2
        capsule(dr, (ax, KNOB_Y - 20), (ax, HUB[1] - 20), 6, (200, 200, 214), S)
        dr.arc([ax * S, (HUB[1] - 20) * S, (ax + 60) * S, (HUB[1] + 40) * S], 180, 270, fill=(200, 200, 214),
               width=int(12 * S))
        capsule(dr, (ax + 30, HUB[1] - 20), (HUB[0], HUB[1] - 20), 6, (200, 200, 214), S)
        dr.line([HUB[0] * S, (HUB[1] - 20) * S, HUB[0] * S, HUB[1] * S], fill=(200, 200, 214), width=int(4 * S))
        dr.line([(HUB[0] - ARM_R) * S, HUB[1] * S, (HUB[0] + ARM_R) * S, HUB[1] * S], fill=(200, 200, 214),
                width=int(6 * S))
        ell(dr, HUB[0], HUB[1], 16, 8, (220, 220, 232), S)
        toys = sorted(self.sc.P.mob.toys(t), key=lambda a: a[3])
        for (k, x, y, z, col, shape, xa) in toys:
            c = mix(WALL, col, 0.72 + 0.28 * (z + 1) / 2)
            dr.line([xa * S, HUB[1] * S, x * S, (y - TOY_R) * S], fill=(170, 170, 190), width=int(2 * S))
            draw_toy(dr, shape, x, y, TOY_R * (0.9 + 0.1 * z), c, S)

    def draw_star(self, dr, t, S):
        """L'étoile du mobile se décroche, tombe sur le bébé et glisse sur le matelas."""
        t0 = Mobile.STAR_OFF
        if t < t0:
            return
        p0 = (420.0, TOY_Y)
        land = (610.0, 952.0)
        rest = (600.0, MT - 22)
        if t < t0 + 0.6:
            x, y = arc_point(p0, land, t0, 0.6, t)
            a = (t - t0) * 9
        elif t < t0 + 1.0:
            u = smooth((t - t0 - 0.6) / 0.4)
            x, y, a = lerp(land[0], rest[0], u), lerp(land[1], rest[1], u), 5.4 + u
        else:
            x, y, a = rest[0], rest[1], 6.4
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
        """La tétine saute quand le matelas soulève le bébé et retombe sur le matelas, devant lui."""
        hx, hy = J["head"]
        HR = 32 * BS
        face = (hx, hy - HR * 0.85)
        t0 = self.sc.paci_t
        land = (705.0, MT - 10)
        if t < t0:
            x, y, a = face[0], face[1], 0.0
        elif t < t0 + 0.6:
            x, y = arc_point(face, land, t0, 0.6, t)
            a = (t - t0) * 12
        else:
            x, y, a = land[0], land[1], 1.4
        if t >= 12.0:              # le bébé à quatre pattes l'a poussée contre le montant droit
            u = smooth((t - 12.0) / 0.5)
            x = lerp(land[0], 815.0, u)
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
            if not sil:
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
        elif mode == "grab":
            g0, g1 = sc.grab
            p = 0.92 * smooth((t - g0) / (g1 - g0))
            bx, by = sc.P.pos(t)
            rail = (x - 70 + lean * 2.0, RAIL_Y - 10)
            tgt = (bx + 70, by - 80)
            hands = [(lerp(rail[0], tgt[0], p), lerp(rail[1], tgt[1], p)),
                     (x + 60 + lean * 2.0, RAIL_Y - 10)]
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

    # -------- bulles, en coordonnées de l'écran (1080×1920), accrochées à celui qui parle
    def draw_bubbles(self, dr, t, S):
        hook_on = t < self.cfg.get("hook_text_s", 44.9) + 0.2
        for (who, text, a, b) in self.sc.subs:
            if not (a <= t <= b):
                continue
            k = clamp01((t - a) / 0.12)
            text = text.replace("...", "…")
            if who == "mom_off":
                tgt = to_screen(DOOR[0] + 10, 600.0)
                self.bubble(dr, S, [text], 72, k, (470.0, 505.0), tgt, (64, 168, 164), (255, 255, 255))
                continue
            if who in ("baby", "babble"):
                J = getattr(self, "_baby", None)
                hx, hy = to_screen(*J["head"]) if J else (744.0, 596.0)
                hr = 32 * BS * K
                fill, ink = ((252, 236, 150), (30, 26, 20))
                if who == "babble" or hook_on:
                    fs = 132 if who == "babble" else 96
                    lines, bw, bh = self.wrap(text, fs, 900)
                    cx = max(120 + bw / 2, hx - hr - 30 - bw / 2)
                    cy = max(445 + bh / 2, hy - 30)
                    self.bubble(dr, S, lines, fs, k, (cx, cy), (hx - hr * 0.8, hy - 10), fill, ink)
                else:
                    fs = 62
                    lines, bw, bh = self.wrap(text, fs, 700)
                    cy = min(450 - bh / 2, hy - hr - 24 - bh / 2)
                    cy = max(300 + bh / 2, cy)
                    cx = 895 - bw / 2            # à droite : jamais sur la tête de Maman
                    self.bubble(dr, S, lines, fs, k, (cx, cy), (hx, hy - hr * 0.9), fill, ink)
                continue
            # Maman dans la chambre : à côté de sa tête, du côté le plus libre, entre y 300 et 480
            hd = getattr(self, "_mom_head", None)
            hx, hy = to_screen(*hd) if hd else to_screen(self.sc.mom_x(t), 440.0)
            hr = 62 * K * 1.12
            _a, joy, col = self.mom_state(t)
            left_w = (hx - hr - 24) - 125
            right_w = 895 - (hx + hr + 24)
            best = None
            for fs in (72, 64, 58):
                for side, avail in (("right", right_w), ("left", left_w)):
                    lines, bw, bh = self.wrap(text, fs, avail - 10)
                    if bw <= avail and bh <= 260:
                        best = (fs, side, lines, bw, bh)
                        break
                if best:
                    break
            if best is None:
                fs, side = 58, ("right" if right_w > left_w else "left")
                lines, bw, bh = self.wrap(text, fs, max(right_w, left_w))
            else:
                fs, side, lines, bw, bh = best
            cx = hx + hr + 24 + bw / 2 if side == "right" else hx - hr - 24 - bw / 2
            cy = min(480 - bh / 2, max(300 + bh / 2, hy - 20))
            self.bubble(dr, S, lines, fs, k, (cx, cy), (hx + (hr if side == "right" else -hr) * 0.8, hy), col,
                        (255, 255, 255))

    def wrap(self, text, fs, maxw):
        f = font(fs)
        words = text.split()
        lines = [""]
        for w in words:
            cand = (lines[-1] + " " + w).strip()
            if lines[-1] and f.getlength(cand) + 56 > maxw:
                lines.append(w)
            else:
                lines[-1] = cand
        bw = max(f.getlength(l) for l in lines) + 56
        bh = fs * (1.2 * len(lines) + 0.3)
        return lines, bw, bh

    def bubble(self, dr, S, lines, fs, k, c, tgt, fill, ink):
        f = font(fs * S * (0.75 + 0.25 * k))
        fr = font(fs)
        bw = max(fr.getlength(l) for l in lines) + 56
        bh = fs * (1.2 * len(lines) + 0.3)
        cx, cy = c
        x0, y0, x1, y1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
        if tgt[1] > y1:
            bxm = max(x0 + 30, min(x1 - 30, tgt[0]))
            tail = [(bxm - 20, y1 - 6), (bxm + 20, y1 - 6), tgt]
        else:
            bym = max(y0 + 20, min(y1 - 20, tgt[1]))
            side = x0 + 6 if tgt[0] < cx else x1 - 6
            tail = [(side, bym - 18), (side, bym + 18), tgt]
        dr.polygon(poly(tail, S), fill=(20, 20, 26))
        rect(dr, x0 - 4, y0 - 4, x1 + 4, y1 + 4, (20, 20, 26), S, r=min(bh, 120) / 2.2 + 4)
        dr.polygon(poly([(p[0], p[1] - (0 if i == 2 else 3)) for i, p in enumerate(tail)], S), fill=fill)
        rect(dr, x0, y0, x1, y1, fill, S, r=min(bh, 120) / 2.2)
        n = len(lines)
        for i, line in enumerate(lines):
            yy = cy + (i - (n - 1) / 2) * fs * 1.2
            dr.text((cx * S, yy * S), line, fill=ink, anchor="mm", font=f)


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
    f1 = font(46 * S)
    f2 = font(36 * S)
    d.text((pad + w / 2, pad + 0.22 * h), "DO NOT", fill=ink, anchor="mm", font=f1)
    d.text((pad + w / 2, pad + 0.5 * h), "WAKE HIM!", fill=ink, anchor="mm", font=f1)
    d.text((pad + 0.66 * w, pad + 0.8 * h), "— Mom", fill=(40, 40, 60, 255), anchor="mm", font=f2)
    _SIGN[key] = (img, pad)
    return _SIGN[key]


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 44.9, "hook_top": 0.125, "hook_font_size": 88, "hook_speed": 1.1,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 1.0,
}
LINE_GAIN = {"bab1": 0.75, "bab2": 0.85, "bab3": 0.95, "b3": 1.15,
             "shh": 0.8, "ok": 0.75, "whos": 0.85, "sweet": 0.75, "who": 1.0, "b": 1.05, "first": 1.05,
             "b2": 1.1}


def exact_events(sim):
    """Les contacts durs à leurs instants exacts (indépendants du nombre d'images par seconde)."""
    return [(t, "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(sim.sc.P.hits)]


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
    sim.sc.set_narr(narr)
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
