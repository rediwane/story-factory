"""
Prototype « magic » : Bounce au spectacle de magie.

Le magicien (forme sans visage, haut-de-forme, cape) voulait sortir un lapin de son chapeau : c'est
Bounce qui en sort, et il gâche chaque tour en rebondissant et en disant son nom. Il suffirait qu'il
reste tranquille dans le chapeau ; il ne le fait jamais.

  - ouverture : le magicien le remet dans le chapeau, il en ressort ; « That's not a rabbit. » ;
    sa baguette, cognée, s'envole et retombe plantée dans le chapeau ;
  - tour 1, le paravent : il le cache derrière un foulard qu'il monte de plus en plus haut ;
    « Now you don't! »… Bounce est assis SUR le foulard ;
  - tour 2, le rodéo : il s'assoit sur lui (« Stay. ») ; Bounce le soulève de plus en plus haut, puis
    l'envoie valser derrière la table ;
  - la lévitation : le magicien fait croire que c'est lui qui le fait léviter, et salue ;
  - tour 3, le sort : « Abracadabra! » ; Bounce cogne la baguette, qui se retourne : c'est le
    magicien qui disparaît (il ne reste que son chapeau, son nœud, ses gants et ses chaussures) ;
  - le magicien invisible : il tape où était Bounce, s'assoit encore sur lui (son chapeau s'envole et
    retombe), le vise : ses sorts ratent Bounce et font disparaître le chapeau du tour, puis la table ;
  - la course sur le plancher, plus rapide ; il l'attrape enfin dans sa main, se penche pour le
    regarder… Bounce rebondit dans son chapeau, qui s'envole, se retourne et retombe dans son autre
    main : le lapin en sort. Il était sous son chapeau depuis le début.

Tout est dessiné à l'échelle de l'écran 1080×1920 (aperçu 540×960 : tout est mis à l'échelle). Le son
suit les instants exacts des contacts. Un ralenti couvre le vol du chapeau à la fin.

    python3 src/stories/magic.py configs/<name>.json [--simulate | --plan | --stills t1,t2,... dir]
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
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/magic/bank"

# ------------------------------------------------------------------ voix du magicien (Kokoro bm_george)
BANK_FILES = {"That's not a rabbit.": "notrabbit.wav", "Now you don't!": "dont.wav", "Stay.": "stay.wav",
              "Abracadabra!": "abra.wav", "Oh, come on.": "comeon.wav"}
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
            d = os.environ.get("MAGIC_BANK", BANK_DIR)
            BANK[text] = _read(os.path.join(d, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

# ------------------------------------------------------------------ le mot de Bounce, stable (même prise partout)
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(os.environ.get("MAGIC_BANK", BANK_DIR),
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

# ------------------------------------------------------------------ l'accroche : posée par ce thème, après le 1er « Bounce »
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

# ------------------------------------------------------------------ géométrie (écran 1080×1920)
W, H = 1080, 1920
G = 2600.0
R = 115.0
FLOOR = 1110.0                    # dessus du plancher de la scène
TABLE = (170.0, 690.0, 870.0)     # x0, x1, dessus
WOOD_Y = TABLE[2] - R
FLOOR_BY = FLOOR - R
HAT_X = 285.0                     # le chapeau du tour, retourné sur la table
HAT_W, HAT_H = 240.0, 180.0
SILK_Y = TABLE[2] - 28 - R
PAD = (590.0, 690.0, 840.0)       # le foulard plié, posé au bout de la table (après le tour 1)
PAD_X = 640.0
PAD_Y = PAD[2] - R
STAND_HIP = 905.0

# couleurs
BG = (8, 8, 12)
WALL = (22, 15, 32)
SPOT = [(30, 21, 44), (38, 27, 56), (46, 33, 66)]
CURT = (120, 18, 40)
CURT_D = (88, 12, 30)
GOLD = (226, 178, 72)
PLANK = (70, 48, 38)
PLANK_L = (88, 62, 48)
LIP = (44, 30, 26)
WOOD = (132, 88, 58)
WOOD_L = (160, 112, 76)
SKIRT = (64, 34, 100)
SKIRT_D = (48, 24, 78)
HATC = (34, 32, 44)
HAT_RIM = (104, 98, 128)
HAT_BAND = (190, 30, 52)
SUIT = (62, 84, 178)
SUIT_D = (46, 62, 138)
SHIRT = (236, 236, 242)
TIE = (210, 34, 56)
CAPE = (150, 20, 44)
CAPE_L = (206, 44, 74)
GLOVE = (246, 246, 250)
GLOVE_D = (196, 196, 210)
SHOE = (18, 18, 22)
SHOE_L = (100, 100, 122)
WAND = (16, 16, 20)
SPARK = (255, 236, 150)
CLOTH = (206, 30, 62)
CLOTH_D = (156, 18, 44)
AUD = [(26, 20, 40), (32, 25, 50), (38, 30, 60)]
AUD_RIM = (78, 62, 108)
RABBIT = (246, 246, 250)
RABBIT_D = (206, 206, 220)
RABBIT_IN = (255, 170, 194)
SILKS = [(255, 84, 84), (255, 204, 64), (84, 200, 255), (124, 230, 124), (230, 120, 255)]
ANGER = (214, 44, 44)
GHOST = (96, 86, 140)


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
    """Valeur interpolée (lissée) entre des clés (t, v)."""
    def __init__(self, v0, keys=()):
        self.keys = [(-1e9, v0)] + sorted(keys, key=lambda k: k[0])
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


def hold(v0, pts, d=0.2):
    """Clés « marche » : à chaque (t, v), passe à v en d secondes et y reste."""
    keys, cur = [], v0
    for (t, v) in pts:
        keys += [(t, cur), (t + d, v)]
        cur = v
    return keys


def hop(t, hops):
    """Sauts paraboliques (t0, hauteur) : renvoie la hauteur au-dessus du sol."""
    y = 0.0
    for (t0, h) in hops:
        T = 2 * math.sqrt(2 * h / G)
        u = t - t0
        if 0 <= u <= T:
            y = max(y, h - 0.5 * G * (u - T / 2) ** 2)
    return y


def arc(p0, p1, t0, T, t):
    u = max(0.0, min(T, t - t0))
    vx = (p1[0] - p0[0]) / T
    vy = (p1[1] - p0[1]) / T - 0.5 * G * T
    return p0[0] + vx * u, p0[1] + vy * u + 0.5 * G * u * u


# ------------------------------------------------------------------ le temps : ralenti sur le vol du chapeau
SLOW = (58.62, 59.32, 0.4)       # intervalle en temps de scène, facteur de vitesse


def scene_of(t):
    a, b, k = SLOW
    if t < a:
        return t
    ra = a + (b - a) / k
    if t < ra:
        return a + (t - a) * k
    return b + (t - ra)


def real_of(s):
    a, b, k = SLOW
    if s < a:
        return s
    if s < b:
        return a + (s - a) / k
    return a + (b - a) / k + (s - b)


# ------------------------------------------------------------------ le plan de Bounce (temps de scène)
# (t, genre, x, y, dur, gain)  ; dur = contact qui fait dire « Bounce »
C = []


def hard(t, kind, x=None, y=None, gain=1.0):
    C.append({"t": t, "kind": kind, "x": x, "y": y, "soft": False, "gain": gain})


def soft(t, kind, x=None, y=None):
    C.append({"t": t, "kind": kind, "x": x, "y": y, "soft": True, "gain": 0.0})


def press(a, b, x):
    """Écrasé sous le magicien : petits rebonds mous, muets, jamais immobile."""
    t, k = a, 0
    while t < b - 0.18:
        soft(t, "press", x + (5 if k % 2 else -5), WOOD_Y + 24)
        t += 0.34
        k += 1


START = {"t": -0.80, "x": HAT_X, "y": SILK_Y}
# --- ouverture : il sort du chapeau, le magicien le remet dedans, il ressort
hard(0.12, "wood", 500, gain=1.1)
soft(0.95, "palm", 588, 735)
soft(1.75, "silk")
hard(2.40, "wood", 500)
soft(3.15, "palm", 600, 735)
soft(3.70, "palm", 604, 735)
soft(4.25, "palm", 600, 735)
soft(4.80, "palm", 600, 735)
hard(5.15, "wand", 578, 565, gain=1.2)
soft(5.50, "palm", 590, 735)
hard(6.05, "wood", 488)
hard(6.90, "wood", 560, gain=1.05)
hard(7.80, "wood", 512)
# --- tour 1 : le paravent
hard(8.85, "wood", 505, gain=0.9)
hard(10.00, "wood", 505, gain=1.1)
soft(10.85, "top", 520, 418)
soft(11.50, "top", 522, 422)
soft(12.12, "top", 524, 430)
hard(12.85, "wood", 515, gain=1.1)
# --- tour 2 : le rodéo
hard(13.80, "wood", 500)
press(14.55, 15.95, 500)
hard(15.95, "wood", 500, gain=0.95)
soft(16.52, "press", 500, WOOD_Y + 18)
hard(16.90, "wood", 503, gain=1.05)
soft(17.42, "press", 500, WOOD_Y + 18)
hard(17.80, "wood", 500, gain=1.15)
soft(18.30, "press", 500, WOOD_Y + 20)
hard(18.70, "wood", 500, gain=1.35)
hard(19.75, "wood", 515)
hard(20.60, "wood", 500)
# --- la lévitation : le magicien fait croire que c'est son tour
hard(21.45, "wood", 520)
hard(22.60, "wood", 520, gain=1.15)
soft(23.55, "palm", 560, 560)
hard(24.45, "wood", 520)
# --- tour 3 : le sort
soft(25.30, "pad")
soft(25.95, "pad")
soft(26.33, "pad")
hard(26.62, "wand", 612, 598, gain=1.25)
soft(26.95, "pad")
hard(27.70, "wood", 510)
# --- le magicien invisible
hard(28.65, "wood", 500)
soft(29.70, "pad")
hard(30.85, "wood", 520)
hard(31.75, "wood", 500)
hard(32.70, "wood", 530)
hard(33.55, "wood", 510)
press(34.32, 35.15, 505)
hard(35.15, "wood", 505, gain=0.95)
soft(35.68, "press", 505, WOOD_Y + 18)
hard(36.05, "wood", 505, gain=1.05)
soft(36.55, "press", 505, WOOD_Y + 18)
hard(36.90, "wood", 505, gain=1.1)
press(37.40, 39.10, 505)
hard(39.10, "wood", 505, gain=1.35)
hard(40.05, "wood", 520)
hard(41.25, "wood", 500)
hard(42.10, "wood", 470)
hard(42.95, "wood", 450, gain=1.1)
hard(43.85, "wood", 520)
hard(44.95, "floor", 530, gain=1.2)
# --- la course sur le plancher (Q4 : plus serré)
hard(45.85, "floor", 500)
hard(46.75, "floor", 560)
soft(47.10, "squeeze", 560, 700)
hard(47.90, "floor", 520)
hard(48.75, "floor", 470)
hard(49.60, "shoe", 560, 957, gain=1.1)
hard(50.45, "floor", 520)
hard(51.55, "back", 600, 862, gain=1.1)
hard(52.40, "back", 560, 862, gain=1.0)
hard(53.25, "floor", 500)
hard(54.55, "floor", 520, gain=1.1)
hard(55.40, "floor", 540)
hard(56.40, "floor", 505, gain=1.05)
# --- pris dans sa main ; il se penche ; le chapeau
soft(57.20, "palm", 505, 812)
soft(57.55, "palm", 505, 812)
soft(57.90, "palm", 505, 812)
soft(58.22, "palm", 505, 812)
soft(58.45, "palm", 505, 812)
hard(58.60, "hat", 505, 765, gain=1.35)
soft(59.40, "palm", 508, 812)
soft(59.95, "palm", 506, 812)
soft(60.55, "palm", 505, 812)
soft(61.10, "palm", 505, 812)
END_SCENE = 61.25
C.sort(key=lambda c: c["t"])

for c in C:
    if c["kind"] == "wood":
        c["y"] = WOOD_Y
    elif c["kind"] == "floor":
        c["y"] = FLOOR_BY
    elif c["kind"] == "silk":
        c["x"], c["y"] = HAT_X, SILK_Y
    elif c["kind"] == "pad":
        c["x"], c["y"] = PAD_X, PAD_Y + 6

TABLE_GONE = 44.30                # le 2e sort rate Bounce et fait disparaître la table
PROP_GONE = 43.20                 # le 1er sort fait disparaître le chapeau du tour
ZAP = 26.85                       # le sort revient sur le magicien
INVIS = 27.05
LAST_HARD = 58.60
ISSUE_S = 59.38                   # le lapin sort du chapeau (temps de scène)

# lignes du magicien (temps réel de déclenchement)
LINES = [(3.30, "That's not a rabbit.", "notrabbit"), (11.55, "Now you don't!", "dont"),
         (15.00, "Stay.", "stay"), (25.40, "Abracadabra!", "abra"), (29.62, "Oh, come on.", "comeon")]


class Plan:
    def __init__(self):
        self.cs = C
        self.ts = [c["t"] for c in C]
        self.start = START
        self.after = {"t": END_SCENE + 0.6, "x": 505, "y": 812}
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in C if not c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.cs[i - 1]
        b = self.after if i >= len(self.cs) else self.cs[i]
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
        for c in self.cs[i:i + 4]:
            u = t - c["t"]
            if -0.06 <= u <= 0.14:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / 0.14)
                if c["kind"] == "squeeze":
                    sx *= 1 - 0.3 * kk; sy *= 1 + 0.25 * kk
                    continue
                amp = 0.12 if c["soft"] else 0.18
                if c["kind"] == "wand" or c["kind"] == "hat":
                    sy *= 1 - amp * kk; sx *= 1 + 0.7 * amp * kk
                else:
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
        # écrasé sous le magicien
        pr = self.pressed(t)
        if pr > 0:
            sy *= 1 - 0.2 * pr; sx *= 1 + 0.16 * pr
        return sx, sy

    def pressed(self, t):
        k = 0.0
        for (a, b) in PRESS_SPANS:
            k = max(k, clamp01((t - a + 0.1) / 0.1) * clamp01((b - t) / 0.12))
        return k

    def ball(self, t):
        x, y = self.pos(t)
        sx, sy = self.squash(t)
        # posé sur une surface : le bas reste à sa place quand il s'écrase
        y += R * (1 - sy) * 0.9
        return x, y, R * sx, R * sy


PRESS_SPANS = [(14.55, 15.95), (16.45, 16.90), (17.35, 17.80), (18.25, 18.70), (34.32, 35.15), (35.62, 36.05),
               (36.50, 36.90), (37.40, 39.10)]

# ------------------------------------------------------------------ le magicien (temps de scène)
# x du bassin
MX = KF(800.0, [(7.95, 800.0), (8.35, 700.0), (13.85, 700.0), (20.0, 640.0), (21.0, 640.0), (21.5, 760.0),
                (45.5, 760.0), (46.5, 700.0), (52.49, 700.0), (52.51, 760.0), (56.0, 760.0), (56.9, 660.0)])
LEAN = KF(0.0, [(0.0, -6.0), (0.3, 4.0), (1.0, -10.0), (1.7, -14.0), (2.3, -14.0), (2.5, 6.0), (3.2, 0.0),
                (5.9, -8.0), (6.4, -20.0), (6.95, -20.0), (7.1, 10.0), (7.8, 0.0),
                (12.2, 0.0), (12.4, 6.0), (12.9, -6.0), (13.8, 0.0),
                (19.9, 0.0), (20.1, 24.0), (20.9, 24.0), (21.4, 0.0),
                (22.05, -8.0), (22.4, 18.0), (22.62, 18.0), (22.8, -4.0), (23.35, 6.0), (23.75, 14.0), (24.2, 0.0),
                (24.6, -18.0), (24.95, -6.0), (26.6, -6.0), (26.7, 8.0),
                (28.3, 8.0), (28.6, -10.0), (29.3, -10.0), (29.6, 0.0),
                (31.2, 0.0), (31.35, -16.0), (31.6, 0.0), (32.1, 0.0), (32.25, -16.0), (32.5, 0.0),
                (40.2, 0.0), (40.4, 10.0), (40.8, 0.0),
                (50.85, 0.0), (51.15, -84.0), (52.5, -84.0), (52.52, 0.0),
                (57.3, 0.0), (57.9, -12.0)])
ANGER_K = KF(0.0, [(12.9, 0.0), (13.2, 1.0), (13.8, 1.0), (14.2, 0.3), (18.7, 0.3), (20.4, 0.6), (21.4, 0.0),
                   (24.4, 0.0), (24.7, 1.0), (26.6, 1.0), (26.8, 0.0)])
# sauts du magicien debout (t0, hauteur) : trépignements, rebonds de l'invisible
MAG_HOPS = [(12.95, 26), (13.35, 30), (13.62, 22), (55.45, 130)]
TIPTOE = KF(0.0, [(10.4, 0.0), (10.55, 22.0), (12.15, 22.0), (12.35, 0.0)])
# assis sur Bounce : levées au-dessus de lui à chaque « Bounce »
SIT = [(14.15, 18.70), (34.0, 39.10)]
SIT_HOPS = [(15.95, 70), (16.90, 140), (17.80, 220), (35.15, 70), (36.05, 150), (36.90, 230)]
# vols : (t0, t1, p0 (bassin), p1) — envoyé en l'air depuis Bounce
FLIGHTS = [(18.70, 20.00, (505.0, 640.0), (640.0, 1010.0)),
           (39.10, 39.90, (510.0, 640.0), (760.0, STAND_HIP))]
FLOOR_SIT = (20.0, 21.0)          # tombé derrière la table
DIVE = (50.85, 51.20, 52.50, 52.52)   # il plonge sur Bounce (raté), à plat ventre, puis se relève d'un bond
DIVE_HIP = (700.0, 1040.0)
CROUCH = KF(0.0)
# chapeau du magicien : petits sursauts tout seul (le lapin, dessous, sursaute aux gros « Bounce »)
TWITCH = [(5.2, 1.0), (12.9, 0.8), (18.75, 1.0), (26.65, 0.8), (39.12, 0.6), (44.98, 0.8), (49.65, 1.0)]
# le chapeau esquive (le lapin) : (t0, t1, dx, dy, rot)
DODGE = [(52.72, 53.12, 34.0, 6.0, 0.36), (54.8, 55.2, 36.0, 4.0, 0.36)]
# le chapeau tenu à deux mains (indice) : (t0, t1)
HAT_HELD = [(7.0, 7.7), (17.85, 18.6), (18.75, 19.9)]
HAT_FLY2 = (39.15, 40.2)          # sur l'invisible : le chapeau décolle et retombe sur la tête
HAT_FLY_END = (58.60, 59.32)      # la fin : il s'envole, se retourne, retombe dans la main droite

# gants : (t, durée de transition, spec gauche, spec droite)
# spec : ("rel", dx, dy) par rapport à l'épaule ; ("abs", x, y) ; ("ball", dx, dy) ; ("hip", dx, dy)
REST = (("rel", -20, 175), ("rel", 20, 175))
GLOVES = [
    (-9.0, 0.1, ("rel", -120, -175), ("rel", 110, -185)),            # ta-da
    (0.25, 0.25, ("rel", -110, -40), ("rel", 60, -60)),               # surpris
    (0.62, 0.3, ("abs", 588, 868), ("rel", 60, -60)),                 # la main tendue, paume en l'air
    (1.0, 0.35, ("abs", 430, 760), ("rel", 60, -40)),                 # il le lance dans le chapeau
    (1.45, 0.3, ("abs", 430, 690), ("rel", 40, 20)),                  # la main au-dessus du chapeau
    (2.45, 0.2, ("rel", -60, -80), ("rel", 60, -80)),                 # sursaut
    (2.85, 0.3, ("abs", 600, 868), ("rel", 110, -150)),               # il le présente au public
    (4.55, 0.3, ("abs", 600, 868), ("abs", 700, 452)),                # la baguette au-dessus de lui
    (5.17, 0.12, ("abs", 590, 868), ("rel", 60, -170)),               # la baguette s'envole
    (5.75, 0.3, ("rel", -50, 150), ("rel", 60, -120)),
    (6.4, 0.3, ("rel", -60, 120), ("rel", 50, 140)),
    (7.0, 0.25, ("hat", -60, 0), ("hat", 60, 0)),                     # il tient son chapeau (frôlé)
    (7.7, 0.3, REST[0], REST[1]),
    (8.05, 0.35, ("abs", 392, 640), ("abs", 648, 640)),               # le foulard, tendu en paravent
    (8.5, 0.2, ("abs", 390, 600), ("abs", 650, 600)),
    (9.45, 0.25, ("abs", 390, 560), ("abs", 650, 560)),
    (10.4, 0.25, ("abs", 390, 520), ("abs", 650, 520)),
    (12.15, 0.25, ("abs", 400, 860), ("abs", 640, 860)),              # il tire le foulard d'un coup
    (12.6, 0.3, ("rel", -40, 110), ("rel", 40, 110)),
    (12.9, 0.15, ("rel", -60, 60), ("rel", 60, 60)),                  # poings serrés, trépigne
    (13.8, 0.3, ("rel", -90, -60), ("rel", 90, -60)),                 # il saute
    (14.6, 0.3, ("hip", -70, 20), ("hip", 70, 20)),                   # assis, mains sur les genoux
    (14.95, 0.15, ("ball", -40, -60), ("hip", 70, 20)),               # « Stay. » : il lui tapote la tête
    (15.6, 0.2, ("hip", -70, 20), ("hip", 70, 20)),
    (17.75, 0.15, ("hat", -60, 0), ("hat", 60, 0)),                   # il tient son chapeau
    (18.6, 0.1, ("hat", -60, 0), ("hat", 60, 0)),
    (19.9, 0.2, ("rel", -110, 40), ("rel", 110, 40)),                 # tombé derrière la table
    (21.0, 0.3, REST[0], REST[1]),
    (21.6, 0.3, ("rel", -150, -40), ("rel", -60, -20)),               # « lévitation » : les mains vers lui
    (22.05, 0.25, ("rel", -60, -150), ("rel", 140, -150)),            # ta-da au public
    (22.62, 0.12, ("rel", -60, -60), ("rel", 60, -60)),               # sursaut
    (23.0, 0.35, ("abs", 560, 694), ("rel", 140, -150)),              # encore : la paume tendue
    (23.6, 0.1, ("abs", 560, 735), ("rel", 140, -150)),               # elle plie sous lui
    (23.85, 0.3, ("rel", -50, 120), ("rel", 50, 150)),
    (24.55, 0.3, ("abs", 290, 600), ("rel", 40, 120)),                # il reprend sa baguette (chapeau)
    (25.0, 0.35, ("abs", 720, 440), ("rel", 110, -120)),              # il vise
    (26.64, 0.1, ("abs", 718, 446), ("rel", 110, -120)),
    (27.25, 0.3, ("rel", -60, 90), ("rel", 60, 90)),                  # invisible : il se tâte
    (27.6, 0.15, ("rel", -50, 70), ("rel", 50, 70)),
    (27.8, 0.15, ("rel", -50, 100), ("rel", 50, 100)),
    (28.0, 0.15, ("rel", -50, 70), ("rel", 50, 70)),
    (28.2, 0.15, ("rel", -50, 100), ("rel", 50, 100)),
    (29.5, 0.25, ("rel", -130, 30), ("rel", 130, 30)),                # « Oh, come on. »
    (30.9, 0.3, ("rel", -110, -30), ("rel", 30, -60)),
]
# claps ratés (t, x, y) : les gants se referment où Bounce était
CLAPS = [(31.35, 470, 520), (32.25, 560, 515), (53.62, 515, 780)]
GLOVES += [
    (33.0, 0.3, REST[0], REST[1]),
    (33.85, 0.3, ("rel", -90, -60), ("rel", 90, -60)),
    (34.4, 0.25, ("hip", -70, 20), ("hip", 70, 20)),
    (36.9, 0.15, ("hat", -60, 0), ("hat", 60, 0)),
    (37.45, 0.25, ("hip", -60, 10), ("hip", 60, 10)),                 # bras croisés, content de lui
    (39.1, 0.2, ("rel", -130, -120), ("rel", 130, -120)),
    (40.3, 0.3, REST[0], REST[1]),
    (41.0, 0.3, ("abs", 600, 860), ("rel", 40, 150)),                 # il ramasse la baguette
    (41.45, 0.3, ("aim", 0, 0), ("rel", 40, 120)),                    # il vise Bounce
    (45.15, 0.2, ("rel", -70, -10), ("rel", 40, 120)),                # la baguette fait pschitt
    (45.4, 0.12, ("rel", -50, 10), ("rel", 40, 120)),
    (45.55, 0.12, ("rel", -70, -10), ("rel", 40, 120)),
    (45.75, 0.25, ("rel", 60, -160), ("rel", 40, 120)),               # il la jette
    (46.2, 0.3, REST[0], REST[1]),
    (46.75, 0.15, ("ball", -125, 0), ("ball", 125, 0)),               # il le serre entre ses mains
    (47.08, 0.05, ("ball", -98, 0), ("ball", 98, 0)),
    (47.2, 0.2, ("rel", -100, -60), ("rel", 100, -60)),               # il lui file entre les doigts
    (48.0, 0.3, REST[0], REST[1]),
    (50.6, 0.25, ("rel", -110, -40), ("rel", 60, -60)),
    (51.0, 0.2, ("hip", -330, -30), ("hip", -310, 30)),               # plongeon, bras en avant
    (52.5, 0.02, ("rel", -110, -150), ("rel", 110, -150)),            # pouf : debout, ta-da
    (53.0, 0.3, REST[0], REST[1]),
    (55.3, 0.15, ("rel", -60, -210), ("rel", 60, -210)),              # il saute pour l'attraper : raté
    (55.75, 0.3, ("rel", -70, 120), ("rel", 70, 120)),
    (56.75, 0.35, ("abs", 505, 945), ("rel", 50, 120)),               # la main en coupe : il l'attrape
    (57.5, 0.3, ("abs", 505, 945), ("rel", 160, -150)),               # ta-da au public
    (57.95, 0.35, ("abs", 505, 945), ("abs", 728, 790)),              # se penche, la main droite prête
]
# les tapes des claps
for (tc, cx, cy) in CLAPS:
    GLOVES += [(tc - 0.3, 0.2, ("abs", cx - 130, cy), ("abs", cx + 130, cy)),
               (tc - 0.06, 0.06, ("abs", cx - 30, cy), ("abs", cx + 30, cy)),
               (tc + 0.12, 0.15, ("abs", cx - 75, cy + 12), ("abs", cx + 75, cy - 12)),
               (tc + 0.6, 0.3, REST[0], REST[1])]
GLOVES.sort(key=lambda g: g[0])
GLOVE_PRESS = [(23.55, 23.9, 40.0)]     # la paume plie sous le poids

# la baguette : ("hand", côté, angle°) ; angle 180 = vers la gauche
WAND_HAND = [(-9.0, "R", 205.0), (4.5, "R", 180.0)]
WAND_FLY = (5.17, 6.55, (618.0, 452.0), (HAT_X + 4, 640.0), 6.5)       # cognée : vole, se plante dans le chapeau
WAND_STUCK = (6.55, 24.85)
WAND_AIM1 = (24.85, 26.62)        # tenue main gauche, vers Bounce
WAND_FLIP = (26.62, 26.8)         # retournée contre le magicien
WAND_DROP = (27.1, 27.55, (680.0, 500.0), (600.0, 860.0))
WAND_TABLE = (27.55, 41.25)
WAND_AIM2 = (41.25, 45.8)
WAND_TOSS = (45.8, 46.6)
CHARGE = [(25.3, 26.62), (41.9, 42.98), (43.4, 44.05)]
BOLTS = [(26.66, 26.84, "back"), (43.0, 43.2, "prop"), (44.06, 44.28, "table")]
POOFS = [(ZAP, 760.0, 760.0, 1.4), (PROP_GONE, HAT_X, 760.0, 1.0), (TABLE_GONE, 430.0, 920.0, 1.6),
         (52.42, 640.0, 960.0, 0.8)]
FIZZLE = (45.05, 45.8)
# le pied qui écrase (raté) puis la chaussure catapultée
STOMP = (48.6, 49.05)
SHOE_FLY = (49.62, 50.55)
# public : rires (t, force) et bras levés (t0, t1)
LAUGH = [(0.2, 0.6), (2.5, 0.8), (5.3, 0.9), (7.0, 0.6), (11.7, 0.7), (12.9, 1.0), (16.0, 0.6), (17.9, 0.8),
         (18.8, 1.0), (22.7, 0.9), (23.6, 0.8), (27.0, 1.0), (31.4, 0.7), (32.3, 0.8), (36.1, 0.7), (39.2, 1.0),
         (43.1, 0.8), (44.4, 1.0), (47.2, 0.7), (49.7, 1.0), (51.3, 1.0), (53.7, 0.7), (55.6, 0.8),
         (58.7, 1.0), (59.5, 1.0)]
ARMS_UP = [(22.1, 22.75), (27.1, 29.3), (59.45, 99.0)]

# Bounce : visage (début, fin, expression)
EXPR = [(5.15, 5.7, "shock"), (12.15, 12.55, "shock"), (14.5, 15.0, "shock"), (15.0, 18.7, "lose"),
        (18.75, 19.8, "win"), (23.55, 23.9, "shock"), (26.62, 27.1, "shock"), (27.1, 28.4, "win"),
        (34.3, 39.1, "lose"), (39.15, 40.0, "win"), (41.9, 44.8, "shock"), (47.1, 47.45, "shock"),
        (49.6, 50.2, "win"), (51.55, 52.45, "win"), (57.2, 58.6, "calm"), (58.6, 99.0, "shock")]


def gloves_spec_at(t):
    i = 0
    for k, g in enumerate(GLOVES):
        if g[0] <= t:
            i = k
    return i


# ------------------------------------------------------------------ scène
class Scene:
    def __init__(self):
        self.P = Plan()
        self.rings = [(t, g, x, y, k) for (t, g, x, y, k) in self.P.hits]

    # ---- le magicien
    def hip(self, t):
        """Le bassin du magicien (x, y), selon qu'il est debout, assis sur Bounce, en vol ou par terre."""
        x, y = MX(t), STAND_HIP - hop(t, MAG_HOPS) - TIPTOE(t) + 105 * CROUCH(t)
        for (a, b) in SIT:
            if a <= t <= b:
                bx, by = self.P.pos(t)
                # saut vers lui (0,4 s), puis assis : il suit le haut de Bounce, avec ses levées
                sx, sy = bx + 6, by - R * (1 - 0.18 * self.P.pressed(t)) + 4 - hop(t, SIT_HOPS)
                k = smooth((t - a) / 0.4)
                if k < 1:
                    jump = 120 * math.sin(math.pi * k)
                    return lerp(x, sx, k), lerp(y, sy, k) - jump
                return sx, sy
        for (a, b, p0, p1) in FLIGHTS:
            if a <= t <= b:
                return arc(p0, p1, a, b - a, t)
        a, b = FLOOR_SIT
        if a <= t <= b + 0.5:
            k = clamp01((b + 0.5 - t) / 0.5) if t > b else 1.0
            return x, lerp(STAND_HIP, 1010.0, smooth(k))
        d0, d1, d2, d3 = DIVE
        if d0 <= t <= d3:
            if t < d1:
                return arc((x, y), DIVE_HIP, d0, d1 - d0, t)
            if t < d2:
                return DIVE_HIP
            k = smooth((t - d2) / (d3 - d2))
            return lerp(DIVE_HIP[0], x, k), lerp(DIVE_HIP[1], y, k) - 60 * math.sin(math.pi * k)
        return x, y

    def mode(self, t):
        for (a, b) in SIT:
            if a + 0.3 <= t <= b:
                return "sit"
        for (a, b, p0, p1) in FLIGHTS:
            if a <= t <= b:
                return "fly"
        a, b = FLOOR_SIT
        if a <= t <= b + 0.3:
            return "floor"
        if DIVE[0] + 0.1 <= t <= DIVE[3] - 0.1:
            return "dive"
        return "stand"

    def rig(self, t):
        hx, hy = self.hip(t)
        anger = ANGER_K(t)
        if anger > 0.05:
            hx += (2 + 7 * anger) * math.sin(t * 70.0)
        lean = LEAN(t)
        mode = self.mode(t)
        if mode == "fly":
            lean += 25 * math.sin((t - 18.7) * 9.0)
        a = math.radians(lean)
        u = (math.sin(a), -math.cos(a))
        r = (math.cos(a), math.sin(a))

        def P(du, dr):
            return (hx + u[0] * du + r[0] * dr, hy + u[1] * du + r[1] * dr)
        infl = 1.0 + 0.22 * anger
        J = {"hip": (hx, hy), "u": u, "r": r, "lean": lean, "infl": infl, "anger": anger, "mode": mode}
        J["sh"] = P(190, 0)
        J["shL"], J["shR"] = P(190, -64 * infl), P(190, 64 * infl)
        J["neck"] = P(205, 0)
        J["head"] = P(250, 0)
        J["tie"] = P(186, 0)
        J["P"] = P
        # pieds
        if mode in ("sit", "fly"):
            dang = 0.0 if mode == "sit" else 30 * math.sin((t - 18.7) * 12.0)
            J["kL"], J["kR"] = (hx - 118, hy - 20), (hx + 118, hy - 20)
            J["fL"] = (hx - 150, hy + 118 - dang)
            J["fR"] = (hx + 150, hy + 118 + dang)
        elif mode == "floor":
            J["fL"] = (hx - 150, FLOOR - 40)
            J["fR"] = (hx - 110, FLOOR - 70)
        elif mode == "dive":
            J["fL"] = (hx + 175, hy - 40 - 30 * abs(math.sin(t * 9)))
            J["fR"] = (hx + 200, hy - 95 + 30 * abs(math.sin(t * 9)))
        else:
            lift = STAND_HIP - hy
            J["fL"] = (hx - 28, FLOOR - 10 - max(0.0, lift - 40 * CROUCH(t)) * (1 - CROUCH(t)))
            J["fR"] = (hx + 28, FLOOR - 10 - max(0.0, lift - 40 * CROUCH(t)) * (1 - CROUCH(t)))
            if CROUCH(t) > 0:
                J["fL"] = (hx - 60, FLOOR - 10)
                J["fR"] = (hx + 40, FLOOR - 10)
            if STOMP[0] <= t <= STOMP[1] + 1.6:
                k = smooth((t - STOMP[0]) / 0.25)
                up = 90 * math.sin(math.pi * clamp01((t - STOMP[0]) / 0.45))
                J["fL"] = (lerp(hx - 28, 562, k), FLOOR - 10 - up * (t < STOMP[1]))
                if t > SHOE_FLY[0]:
                    J["fR"] = (hx + 28, FLOOR - 10 - 60 * abs(math.sin((t - SHOE_FLY[0]) * 7.0)) * (t < SHOE_FLY[1] + 0.3))
                if t > SHOE_FLY[1] + 0.4:
                    k2 = smooth((t - SHOE_FLY[1] - 0.4) / 0.4)
                    J["fL"] = (lerp(562, hx - 28, k2), FLOOR - 10)
        # gants
        J["gL"], J["gR"] = self.gloves(t, J)
        # chapeau : centre du bord, angle
        J["hat"] = self.hat(t, J)
        return J

    def spec_pos(self, spec, side, t, J):
        kind = spec[0]
        if kind == "rel":
            s = J["shL"] if side == "L" else J["shR"]
            return (s[0] + spec[1], s[1] + spec[2])
        if kind == "abs":
            return (spec[1], spec[2])
        if kind == "ball":
            bx, by = self.P.pos(t)
            return (bx + spec[1], by + spec[2])
        if kind == "hip":
            return (J["hip"][0] + spec[1], J["hip"][1] + spec[2])
        if kind == "hat":
            hx, hy, ang = self.hat_base(t, J)
            return (hx + spec[1], hy - 60 + spec[2])
        if kind == "aim":
            bx, by = self.P.pos(t)
            s = J["shL"]
            dx, dy = bx - s[0], by - s[1]
            n = math.hypot(dx, dy) + 1e-6
            return (s[0] + dx / n * 150, s[1] + dy / n * 150 - 40)
        return J["sh"]

    def gloves(self, t, J):
        i = gloves_spec_at(t)
        g = GLOVES[i]
        prev = GLOVES[i - 1] if i > 0 else g
        k = smooth((t - g[0]) / g[1]) if g[1] > 0 else 1.0
        out = []
        for j, side in enumerate(("L", "R")):
            p0 = self.spec_pos(prev[2 + j], side, t, J)
            p1 = self.spec_pos(g[2 + j], side, t, J)
            p = (lerp(p0[0], p1[0], k), lerp(p0[1], p1[1], k))
            for (a, b, d) in GLOVE_PRESS:
                if a <= t <= b and side == "L":
                    p = (p[0], p[1] + d * math.sin(math.pi * (t - a) / (b - a)))
            out.append(p)
        # la paume sous Bounce : elle plie un peu à chaque contact mou
        for c in self.P.cs:
            if c["kind"] == "palm" and -0.05 <= t - c["t"] <= 0.2:
                d = 14 * math.sin(math.pi * clamp01((t - c["t"] + 0.05) / 0.25))
                out[0] = (out[0][0], out[0][1] + d)
        return out[0], out[1]

    def hat_base(self, t, J):
        """Le chapeau sur la tête : centre du bord, angle (rad)."""
        u = J["u"]
        hx, hy = J["head"][0] + u[0] * 44, J["head"][1] + u[1] * 44
        ang = math.radians(J["lean"])
        return hx, hy, ang

    def hat(self, t, J):
        hx, hy, ang = self.hat_base(t, J)
        for (t0, amp) in TWITCH:
            v = t - t0
            if 0 <= v <= 0.35:
                hy -= amp * 16 * math.sin(math.pi * v / 0.35)
                ang += amp * 0.1 * math.sin(2 * math.pi * v / 0.35)
        for (a, b, dx, dy, rot) in DODGE:
            if a <= t <= b:
                k = math.sin(math.pi * (t - a) / (b - a))
                hx += dx * k; hy += dy * k; ang += rot * k
        a, b = HAT_FLY2
        if a <= t <= b:
            v = (t - a) / (b - a)
            hy -= 90 * math.sin(math.pi * v)
            hx += 30 * math.sin(math.pi * v)
            ang += 2 * math.pi * smooth(v)
        a, b = HAT_FLY_END
        if t >= a:
            # vole vers le haut à droite en tournant, se retourne, retombe dans la main droite
            gx, gy = J["gR"]
            land = (gx, gy - 30)
            T = b - a
            v = min(t, b)
            p = arc((hx, hy), land, a, T, v)
            # retourné : angle de pi (ouverture vers le haut)
            ang = ang + (math.pi - ang) * smooth((min(t, b) - a) / T) + 0.6 * math.sin(math.pi * clamp01((t - a) / T))
            if t >= b:
                p = land
                ang = math.pi
            return p[0], p[1], ang
        return hx, hy, ang

    # ---- la baguette : (x de la poignée, y, angle en radians) ou None
    def wand(self, t, J):
        if t < WAND_FLY[0]:
            side, ang = "R", WAND_HAND[0][2]
            for (tt, s, a) in WAND_HAND:
                if t >= tt:
                    side, ang = s, a
            if 4.5 <= t <= 4.8:
                ang = lerp(205.0, 180.0, smooth((t - 4.5) / 0.3))
            g = J["gR"] if side == "R" else J["gL"]
            return g[0], g[1], math.radians(ang)
        a, b, p0, p1, spin = WAND_FLY
        if t < b:
            x, y = arc(p0, p1, a, b - a, t)
            return x, y, math.radians(180) + spin * 2 * math.pi * (t - a) / (b - a)
        if t < WAND_STUCK[1]:
            return HAT_X + 4, 640.0, math.radians(-90)          # plantée dans le chapeau, debout
        if t < WAND_FLIP[0]:
            g = J["gL"]
            k = smooth((t - WAND_AIM1[0]) / 0.4)
            return g[0], g[1], lerp(math.radians(-90), math.radians(205), k)
        if t < WAND_DROP[0]:
            g = J["gL"]
            k = smooth((t - WAND_FLIP[0]) / (WAND_FLIP[1] - WAND_FLIP[0]))
            return g[0], g[1], lerp(math.radians(205), math.radians(415), k)
        a, b, p0, p1 = WAND_DROP
        if t < b:
            x, y = arc(p0, p1, a, b - a, t)
            return x, y, math.radians(415) + 9 * (t - a)
        if t < WAND_TABLE[1]:
            if t >= TABLE_GONE:
                return None
            return 560.0, 858.0, math.radians(0)
        if t < WAND_TOSS[0]:
            g = J["gL"]
            bx, by = self.P.pos(t)
            ang = math.atan2(by - g[1], bx - g[0])
            if FIZZLE[0] <= t:
                ang = lerp(ang, math.radians(100), smooth((t - FIZZLE[0]) / 0.3))
            dist = math.hypot(bx - g[0], by - g[1])
            return g[0], g[1], ang, max(40.0, min(150.0, dist - 1.6 * R - 40))
        a, b = WAND_TOSS
        if t < b:
            x, y = arc((J["gL"][0], J["gL"][1]), (1000.0, 300.0), a, b - a, t)
            return x, y, 8 * (t - a)
        return None

    def wand_tip(self, w):
        x, y, a = w[:3]
        L = w[3] if len(w) > 3 else 150.0
        return x + L * math.cos(a), y + L * math.sin(a)


# ------------------------------------------------------------------ cadrage : léger zoom après l'accroche, poussée en Q4
ZOOM = KF(1.0, [(8.4, 1.0), (10.0, 1.08), (44.4, 1.08), (46.2, 1.24), (56.8, 1.24), (58.2, 1.3)])
CAMX = KF(540.0, [(44.4, 540.0), (46.2, 585.0), (56.8, 585.0), (58.2, 590.0)])
CAMY = KF(760.0, [(44.4, 760.0), (46.2, 800.0), (56.8, 800.0), (58.2, 770.0)])


# ------------------------------------------------------------------ la simulation (pour base.py)
class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_times = [real_of(h[0]) for h in self.sc.P.hits]
        self.hi = 0
        self.lines = list(LINES)
        self.replies = []
        self.end_real = real_of(END_SCENE)

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_times) and self.hit_times[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= self.end_real - 1e-9:
            self.done = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t0):
        best, bd = 1.0, 1e9
        for (th, g, _x, _y, _k) in self.sc.P.hits:
            d = abs(real_of(th) - t0)
            if d < bd:
                best, bd = g, d
        return best

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = scene_of(float(t))
        sc = self.sc
        S0 = S * self.cfg["width"] / W
        Z = ZOOM(t)
        S = S0 * Z
        cx, cy = CAMX(t), CAMY(t)
        ox = min(max(0.0, cx * Z - W / 2), W * (Z - 1))
        oy = min(max(0.0, cy * Z - 760.0), H * (Z - 1))
        full = dr._image
        wimg = Image.new("RGB", (int(W * S) + 2, int(H * S) + 2), BG)
        dr = ImageDraw.Draw(wimg)
        J = sc.rig(t)
        self.S = S
        self.draw_back(dr, t, S)
        self.draw_audience(dr, t, S, back=True)
        front = J["mode"] in ("sit", "fly")
        if not front:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_table(dr, t, S)
        self.draw_prop_hat(dr, t, S, back=True)
        w = sc.wand(t, J)
        if w is not None and WAND_STUCK[0] <= t < WAND_STUCK[1]:
            self.draw_wand(dr, w, S)
        self.draw_pad(dr, t, S)
        if front:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_rings(dr, t, S)
        bx, by, brx, bry = sc.P.ball(t)
        # Bounce passe derrière le devant du chapeau quand il est dedans
        in_hat = abs(bx - HAT_X) < 140 and by > 600 and t < PROP_GONE
        if in_hat:
            self.draw_bounce(dr, t, S, bx, by, brx, bry)
            self.draw_prop_hat(dr, t, S, back=False)
        else:
            self.draw_prop_hat(dr, t, S, back=False)
        self.draw_silks(dr, t, S)
        self.draw_magician(dr, t, S, J, part="arms")
        self.draw_magician(dr, t, S, J, part="hat")
        if w is not None and not (WAND_STUCK[0] <= t < WAND_STUCK[1]):
            self.draw_wand(dr, w, S)
        self.draw_fx(dr, t, S, J, w, layer="charge")
        if not in_hat:
            self.draw_bounce(dr, t, S, bx, by, brx, bry)
        self.draw_screen(dr, t, S, J)
        self.draw_magician(dr, t, S, J, part="front")
        self.draw_fx(dr, t, S, J, w, layer="burst")
        self.draw_stage_front(dr, t, S)
        self.draw_audience(dr, t, S, back=False)
        x0, y0 = int(ox * S0), int(oy * S0)
        full.paste(wimg.crop((x0, y0, x0 + full.width, y0 + full.height)), (0, 0))

    def expr_at(self, t):
        for (a, b, e) in EXPR:
            if a <= t < b:
                return e
        for (th, g, _x, _y, _k) in self.sc.P.hits:
            if g >= 1.25 and 0 <= t - th < 0.5:
                return "shock"
        return "calm"

    def draw_bounce(self, dr, t, S, bx, by, brx, bry):
        base.HERO["expr"] = self.expr_at(t)
        if abs(brx - bry) < 0.5:
            base.ball(dr, bx * S, by * S, brx * S)
        else:
            r = max(brx, bry)
            size = int(2 * r * 1.7 * S) + 4
            layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            pos = base.HERO["pos"]
            base.ball(ld, size / 2, size / 2, R * S)
            base.HERO["pos"] = pos
            nw, nh = max(2, int(size * brx / R)), max(2, int(size * bry / R))
            layer = layer.resize((nw, nh), Image.BILINEAR)
            dr._image.paste(layer, (int(bx * S - nw / 2), int(by * S - nh / 2)), layer)
            if base.HERO["pos"] is None:
                base.HERO["pos"] = (bx * S, by * S)

    # -------- décor
    def draw_back(self, dr, t, S):
        rect(dr, 0, 0, W, FLOOR, WALL, S)
        for i, c in enumerate(SPOT):
            k = 1 - i * 0.22
            ell(dr, 560, 760, 470 * k, 560 * k, c, S)
        # rideaux
        for (x0, x1) in ((0, 118), (962, W)):
            rect(dr, x0, 80, x1, FLOOR, CURT, S)
            for k in range(4):
                xx = x0 + 14 + k * 28
                rect(dr, xx, 80, xx + 9, FLOOR, CURT_D, S)
        rect(dr, 0, 0, W, 80, (14, 8, 20), S)
        rect(dr, 0, 80, W, 196, CURT, S)
        for k in range(12):
            cx = 45 + k * 90
            ell(dr, cx, 196, 46, 26, CURT, S)
            ell(dr, cx, 200, 10, 10, GOLD, S)
        rect(dr, 0, 92, W, 100, GOLD, S)

    def draw_stage_front(self, dr, t, S):
        rect(dr, 0, FLOOR, W, FLOOR + 48, PLANK, S)
        for k in range(3):
            y = FLOOR + 8 + k * 14
            dr.line([0, y * S, W * S, y * S], fill=PLANK_L, width=max(1, int(2 * S)))
        rect(dr, 0, FLOOR + 48, W, FLOOR + 84, LIP, S)
        for k in range(9):
            x = 80 + k * 115
            ell(dr, x, FLOOR + 50, 22, 12, (255, 222, 150), S)

    def draw_table(self, dr, t, S):
        if t >= TABLE_GONE:
            return
        x0, x1, ty = TABLE
        rect(dr, x0 + 20, ty + 20, x1 - 20, FLOOR, SKIRT, S)
        for k in range(7):
            xx = x0 + 50 + k * 72
            rect(dr, xx, ty + 26, xx + 12, FLOOR, SKIRT_D, S)
        for k in range(8):
            xs, ys = x0 + 70 + k * 58, ty + 120 + (k % 3) * 46
            dr.polygon(poly(star_pts(xs, ys, 13), S), fill=dim(GOLD, 0.8))
        rect(dr, x0, ty, x1, ty + 26, WOOD, S)
        rect(dr, x0, ty, x1, ty + 6, WOOD_L, S)
        for k in range(26):
            xx = x0 + 22 + k * 19
            dr.line([xx * S, (ty + 26) * S, xx * S, (ty + 44) * S], fill=GOLD, width=max(1, int(4 * S)))

    def draw_pad(self, dr, t, S):
        """Le foulard plié au bout de la table : mou, il se creuse sous Bounce."""
        if t < 12.65 or t >= TABLE_GONE:
            return
        x0, x1, top = PAD
        bx, by = self.sc.P.pos(t)
        pts = []
        for i in range(31):
            x = x0 + (x1 - x0) * i / 30
            y = top + 4 * math.sin(i * 0.9)
            dx = x - bx
            if abs(dx) < R * 1.02:
                cy = by + math.sqrt(max(0.0, (R * 1.02) ** 2 - dx * dx))
                y = max(y, min(TABLE[2] - 6, cy))
            pts.append((x, y))
        dr.polygon(poly(pts + [(x1, TABLE[2]), (x0, TABLE[2])], S), fill=CLOTH)
        dr.line(poly(pts, S), fill=CLOTH_D, width=max(1, int(5 * S)))

    def draw_prop_hat(self, dr, t, S, back):
        if t >= PROP_GONE:
            return
        cx, top, bot = HAT_X, TABLE[2] - HAT_H, TABLE[2]
        # le chapeau sursaute un peu quand Bounce rebondit dedans
        dy = 0.0
        for c in self.sc.P.cs:
            if c["kind"] == "silk":
                v = t - c["t"]
                if 0 <= v <= 0.25:
                    dy -= 10 * math.sin(math.pi * v / 0.25)
        top += dy
        if back:
            ell(dr, cx, top, HAT_W / 2 + 32, 28, HATC, S)
            ell(dr, cx, top, HAT_W / 2 - 4, 18, (8, 6, 12), S)
            # coins de foulards qui dépassent
            for k, col in enumerate(SILKS[:4]):
                xs = cx - 80 + k * 52
                dr.polygon(poly([(xs - 16, top + 6), (xs + 16, top + 6), (xs + 4 * math.sin(t * 3 + k), top - 26)], S),
                           fill=col)
            return
        pts = [(cx - HAT_W / 2, top), (cx + HAT_W / 2, top), (cx + HAT_W / 2 - 14, bot), (cx - HAT_W / 2 + 14, bot)]
        dr.polygon(poly(pts, S), fill=HATC)
        rect(dr, cx - HAT_W / 2 + 1, top + 22, cx + HAT_W / 2 - 1, top + 50, HAT_BAND, S)
        dr.line(poly([(cx - HAT_W / 2 + 10, top + 60), (cx - HAT_W / 2 + 22, bot - 8)], S), fill=HAT_RIM,
                width=max(1, int(5 * S)))
        # le bord avant
        dr.arc([(cx - HAT_W / 2 - 32) * S, (top - 28) * S, (cx + HAT_W / 2 + 32) * S, (top + 28) * S], 0, 180,
               fill=HAT_RIM, width=max(1, int(8 * S)))

    def draw_silks(self, dr, t, S):
        """Foulards qui jaillissent du chapeau à chaque rebond mou dedans."""
        if t >= PROP_GONE + 0.8:
            return
        emits = [c["t"] for c in self.sc.P.cs if c["kind"] == "silk"] + [-0.8, -0.3]
        if PROP_GONE <= t:
            emits = [PROP_GONE]
        for te in emits:
            v = t - te
            if not (0 <= v <= 0.9):
                continue
            for k in range(6):
                ang = -math.pi / 2 + (k - 2.5) * 0.32
                sp = 520 + 60 * (k % 3)
                x = HAT_X + math.cos(ang) * sp * v
                y = TABLE[2] - HAT_H + math.sin(ang) * sp * v + 0.5 * 1800 * v * v
                a = v * 9 + k
                col = SILKS[k % len(SILKS)]
                s = 22
                dr.polygon(poly([(x + s * math.cos(a), y + s * math.sin(a)),
                                 (x + s * math.cos(a + 2.2), y + s * math.sin(a + 2.2)),
                                 (x + s * math.cos(a + 4.2), y + s * math.sin(a + 4.2))], S), fill=col)

    def draw_rings(self, dr, t, S):
        for (t0, g, x, y, k) in self.sc.rings:
            u = t - t0
            if u < 0 or u > 0.6:
                continue
            rmax = R + 60 + 200 * g
            r = R + 10 + 900 * u
            if r > rmax:
                continue
            kk = 1 - (r - R) / max(1.0, rmax - R)
            if kk < 0.3:
                continue
            col = mix(WALL, (250, 250, 255), 0.6 + 0.4 * kk)
            w = (12 + 10 * min(1.3, g)) * (0.6 + 0.4 * kk)
            bx, by = self.sc.P.pos(t0)
            dr.ellipse([(bx - r) * S, (by - r) * S, (bx + r) * S, (by + r) * S], outline=col, width=max(2, int(w * S)))

    def draw_screen(self, dr, t, S, J):
        """Le foulard tendu en paravent entre les deux gants ; il tombe d'un coup."""
        if not (8.05 <= t <= 12.65):
            return
        gL, gR = J["gL"], J["gR"]
        grow = smooth((t - 8.05) / 0.35)
        top = (gL[1] + gR[1]) / 2
        x0 = lerp((gL[0] + gR[0]) / 2, gL[0], grow)
        x1 = lerp((gL[0] + gR[0]) / 2, gR[0], grow)
        bot = TABLE[2] + 4
        if t > 12.15:
            # il le tire vers le bas : le foulard s'effondre au bout de la table
            k = smooth((t - 12.15) / 0.5)
            top = lerp(top, PAD[2], k)
            x0, x1 = lerp(x0, PAD[0], k), lerp(x1, PAD[1], k)
        # creux du bord sous Bounce quand il est assis dessus
        bx, by = self.sc.P.pos(t)
        sag = 0.0
        if 11.3 <= t <= 12.3 and by < top:
            sag = clamp01((by + R + 14 - top) / 30) * 26
        n = 16
        topl = []
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            d = 1 - min(1.0, abs(x - bx) / 150)
            topl.append((x, top + sag * d * d))
        wob = 6 * math.sin(t * 13)
        pts = topl + [(x1 + wob, bot), (x0 - wob, bot)]
        dr.polygon(poly(pts, S), fill=CLOTH)
        for k in range(1, 6):
            xx = x0 + (x1 - x0) * k / 6
            yy = top + sag * max(0.0, 1 - abs(xx - bx) / 150) ** 2
            dr.line([(xx + wob * 0.5) * S, (yy + 12) * S, (xx + wob) * S, (bot - 4) * S], fill=CLOTH_D,
                    width=max(1, int(7 * S)))
        dr.line(poly(topl, S), fill=GOLD, width=max(1, int(8 * S)))
        for g in (gL, gR):
            glove(dr, g[0], g[1], S)

    # -------- le magicien
    def draw_magician(self, dr, t, S, J, part):
        vis = t < INVIS
        P = J["P"]
        infl = J["infl"]
        col = mix(SUIT, ANGER, 0.85 * J["anger"])
        cold = mix(SUIT_D, dim(ANGER, 0.75), 0.85 * J["anger"])
        hx, hy = J["hip"]
        if part == "body":
            if vis:
                # cape
                cp = [P(196, -70 * infl), P(196, 70 * infl), P(-95, 150 * infl), P(-95, -150 * infl)]
                dr.polygon(poly(cp, S), fill=CAPE)
                cl = [P(186, -50 * infl), P(186, 50 * infl), P(-85, 125 * infl), P(-85, -125 * infl)]
                dr.polygon(poly(cl, S), fill=CAPE_L)
                # jambes (assis ou en vol : dessinées devant Bounce, avec la partie « front »)
                if J["mode"] not in ("sit", "fly"):
                    for (fx, fy), dx in ((J["fL"], -24), (J["fR"], 24)):
                        capsule(dr, P(10, dx), (fx, fy - 18), 15, (26, 28, 44), S)
                # queue-de-pie et buste
                body = [P(-60, -50 * infl), P(-60, 50 * infl), P(0, 62 * infl), P(150, 70 * infl),
                        P(198, 58 * infl), P(204, 0), P(198, -58 * infl), P(150, -70 * infl), P(0, -62 * infl)]
                dr.polygon(poly(body, S), fill=col)
                dr.polygon(poly([P(196, -22), P(196, 22), P(80, 0)], S), fill=SHIRT)
                for k in range(3):
                    c = P(60 + k * 34, -4)
                    ell(dr, c[0], c[1], 5, 5, cold, S)
                # tête (sans visage), nez du côté où il regarde
                hc = J["head"]
                ell(dr, hc[0], hc[1], 52, 52, (232, 196, 170), S)
                ell(dr, hc[0] - 49, hc[1] + 6, 11, 9, (232, 196, 170), S)
            else:
                # invisible : un contour à peine visible
                gc = GHOST
                body = [P(-60, -50), P(-60, 50), P(0, 62), P(150, 70), P(198, 58), P(204, 0), P(198, -58),
                        P(150, -70), P(0, -62)]
                dr.line(poly(body + body[:1], S), fill=gc, width=max(1, int(4 * S)), joint="curve")
                hc = J["head"]
                dr.ellipse([(hc[0] - 52) * S, (hc[1] - 52) * S, (hc[0] + 52) * S, (hc[1] + 52) * S], outline=gc,
                           width=max(1, int(4 * S)))
                if J["mode"] not in ("sit", "fly"):
                    for (fx, fy), dx in ((J["fL"], -24), (J["fR"], 24)):
                        a0 = P(-50, dx)
                        dr.line([a0[0] * S, a0[1] * S, fx * S, (fy - 14) * S], fill=gc, width=max(1, int(4 * S)))
            # chaussures (toujours)
            if J["mode"] not in ("sit", "fly"):
                for (fx, fy) in (J["fL"], J["fR"]):
                    self.shoe(dr, t, fx, fy, S)
            return
        if part == "arms":
            for (s, g) in ((J["shL"], J["gL"]), (J["shR"], J["gR"])):
                if vis:
                    capsule(dr, s, g, 17, cold, S)
                else:
                    dr.line([s[0] * S, s[1] * S, g[0] * S, g[1] * S], fill=GHOST, width=max(1, int(4 * S)))
            for g in (J["gL"], J["gR"]):
                glove(dr, g[0], g[1], S)
            return
        # devant : jambes qui pendent quand il est assis sur Bounce, nœud papillon et chapeau
        if part == "front":
            if J["mode"] not in ("sit", "fly"):
                return
            for (fx, fy), kn, dx in ((J["fL"], J["kL"], -24), (J["fR"], J["kR"], 24)):
                if vis:
                    capsule(dr, P(10, dx), kn, 15, (26, 28, 44), S)
                    capsule(dr, kn, (fx, fy - 18), 15, (26, 28, 44), S)
                else:
                    dr.line(poly([P(10, dx), kn, (fx, fy - 18)], S), fill=GHOST, width=max(1, int(4 * S)))
                self.shoe(dr, t, fx, fy, S)
            return
        if part != "hat":
            return
        tc = J["tie"]
        a = math.radians(J["lean"])
        bow = [(-30, -14), (0, 0), (-30, 14)]
        bw = [(30, -14), (0, 0), (30, 14)]
        for shape in (bow, bw):
            dr.polygon(poly([(tc[0] + u * math.cos(a) - v * math.sin(a), tc[1] + u * math.sin(a) + v * math.cos(a))
                             for (u, v) in shape], S), fill=TIE)
        ell(dr, tc[0], tc[1], 9, 9, dim(TIE, 0.8), S)
        hx_, hy_, ang = J["hat"]
        rabbit_k = 0.0
        if t >= ISSUE_S - 0.05:
            rabbit_k = clamp01((t - ISSUE_S + 0.05) / 0.3)
        draw_top_hat(dr, hx_, hy_, ang, S, rabbit_k, t)

    def shoe(self, dr, t, fx, fy, S):
        ang = 0.0
        a, b = SHOE_FLY
        if a <= t <= b and fx < self.sc.hip(t)[0]:
            p = arc((fx, fy), (fx, fy), a, b - a, t)
            # la chaussure gauche est catapultée et retombe
            v = (t - a) / (b - a)
            fy = fy - 480 * math.sin(math.pi * v)
            fx = fx + 250 * math.sin(math.pi * v)
            ang = 4 * math.pi * v
        pts = [(-46, -12), (34, -18), (40, 10), (-46, 12)]
        ca, sa = math.cos(ang), math.sin(ang)
        dr.polygon(poly([(fx + u * ca - v * sa, fy + u * sa + v * ca) for (u, v) in pts], S), fill=SHOE)
        dr.line(poly([(fx + u * ca - v * sa, fy + u * sa + v * ca) for (u, v) in [(-40, -12), (30, -17)]], S),
                fill=SHOE_L, width=max(1, int(4 * S)))

    def draw_wand(self, dr, w, S):
        x, y, a = w[:3]
        L = w[3] if len(w) > 3 else 150.0
        tip = (x + L * math.cos(a), y + L * math.sin(a))
        tail = (x - 40 * math.cos(a), y - 40 * math.sin(a))
        dr.line([tail[0] * S, tail[1] * S, tip[0] * S, tip[1] * S], fill=WAND, width=max(2, int(13 * S)))
        t2 = (tip[0] - 26 * math.cos(a), tip[1] - 26 * math.sin(a))
        dr.line([t2[0] * S, t2[1] * S, tip[0] * S, tip[1] * S], fill=(250, 250, 250), width=max(2, int(13 * S)))
        t3 = (tail[0] + 22 * math.cos(a), tail[1] + 22 * math.sin(a))
        dr.line([tail[0] * S, tail[1] * S, t3[0] * S, t3[1] * S], fill=(250, 250, 250), width=max(2, int(13 * S)))
        dr.line([tail[0] * S, tail[1] * S, tip[0] * S, tip[1] * S], fill=(70, 70, 86), width=max(1, int(2 * S)))

    # -------- effets
    def draw_fx(self, dr, t, S, J, w, layer):
        sc = self.sc
        if layer == "burst":
            return self.draw_burst(dr, t, S)
        # étincelles qui se chargent au bout de la baguette
        if w is not None:
            tip = sc.wand_tip(w)
            for (a, b) in CHARGE:
                if a <= t <= b:
                    k = clamp01((t - a) / (b - a))
                    for i in range(7):
                        ang = i * 0.9 + t * 5
                        rr = (16 + 40 * k) * (0.6 + 0.4 * math.sin(t * 17 + i))
                        sp = (tip[0] + rr * math.cos(ang), tip[1] + rr * math.sin(ang))
                        dr.polygon(poly(star_pts(sp[0], sp[1], 9 + 10 * k, t * 4 + i, 4, 0.35), S), fill=SPARK)
                    ell(dr, tip[0], tip[1], 10 + 12 * k, 10 + 12 * k, (255, 250, 220), S)
            if FIZZLE[0] <= t <= FIZZLE[1]:
                for i in range(5):
                    v = ((t - FIZZLE[0]) * 2 + i * 0.2) % 1.0
                    dr.polygon(poly(star_pts(tip[0] + 10 * math.sin(i * 3), tip[1] + 160 * v, 8 * (1 - v), i, 4, 0.35),
                                    S), fill=dim(SPARK, 0.8))

    def draw_burst(self, dr, t, S):
        sc = self.sc
        # éclairs (étoile qui file)
        for (a, b, tgt) in BOLTS:
            if a <= t <= b:
                v = (t - a) / (b - a)
                if tgt == "back":
                    p0 = (618.0, 520.0)
                    p1 = (760.0, 780.0)
                elif tgt == "prop":
                    p0 = sc.wand_tip(sc.wand(a, sc.rig(a)))
                    p1 = (HAT_X + 30, 780.0)
                else:
                    p0 = sc.wand_tip(sc.wand(a, sc.rig(a)))
                    p1 = (470.0, 880.0)
                for j in range(5):
                    vv = max(0.0, v - j * 0.06)
                    p = (lerp(p0[0], p1[0], vv), lerp(p0[1], p1[1], vv))
                    dr.polygon(poly(star_pts(p[0], p[1], 34 - 5 * j, t * 9, 4, 0.32), S), fill=mix(SPARK, (255, 255, 255), 0.4))
        # nuages « pouf »
        for (t0, x, y, size) in POOFS:
            v = t - t0
            if 0 <= v <= 0.75:
                k = v / 0.75
                for i in range(10):
                    ang = i * 2 * math.pi / 10 + 0.3
                    rr = size * (40 + 170 * smooth(k))
                    cx, cy = x + rr * math.cos(ang), y + rr * math.sin(ang) * 0.9
                    rad = size * (70 * (1 - k) + 20)
                    ell(dr, cx, cy, rad, rad, mix((255, 255, 255), WALL, k * 0.9), S)
                ell(dr, x, y, size * 150 * (1 - k), size * 170 * (1 - k), mix((255, 255, 255), WALL, k), S)
                for i in range(8):
                    ang = i * 2 * math.pi / 8
                    rr = size * (60 + 260 * k)
                    dr.polygon(poly(star_pts(x + rr * math.cos(ang), y + rr * math.sin(ang), size * 22 * (1 - k) + 2,
                                             k * 5 + i, 4, 0.35), S), fill=SPARK)

    # -------- le public
    def draw_audience(self, dr, t, S, back):
        rows = [(1240.0, 0.9, 0), (1395.0, 1.0, 1), (1560.0, 1.12, 2)]
        if back:
            return
        laugh = 0.0
        for (t0, a) in LAUGH:
            v = t - t0
            if 0 <= v <= 1.4:
                laugh = max(laugh, a * (1 - v / 1.4))
        up = any(a <= t <= b for (a, b) in ARMS_UP)
        for (y, sc_, ri) in rows:
            n = 6 if ri != 1 else 5
            for k in range(n):
                x = 90 + k * 180 + (90 if ri == 1 else 0)
                ph = (k * 1.7 + ri * 2.3)
                bob = laugh * 22 * abs(math.sin(t * 11 + ph))
                if up:
                    bob = max(bob, 16 * abs(math.sin(t * 8 + ph)))
                col = AUD[ri]
                hy = y - bob
                if up:
                    for side in (-1, 1):
                        capsule(dr, (x + side * 50 * sc_, hy + 60 * sc_), (x + side * 80 * sc_, hy - 90 * sc_), 14 * sc_, col, S)
                        ell(dr, x + side * 80 * sc_, hy - 90 * sc_, 20 * sc_, 20 * sc_, col, S)
                ell(dr, x, hy + 120 * sc_, 92 * sc_, 80 * sc_, col, S)
                ell(dr, x, hy, 52 * sc_, 56 * sc_, col, S)
                dr.arc([(x - 52 * sc_) * S, (hy - 56 * sc_) * S, (x + 52 * sc_) * S, (hy + 56 * sc_) * S], 200, 340,
                       fill=AUD_RIM, width=max(1, int(4 * S)))


def glove(dr, x, y, S):
    ell(dr, x, y, 34, 34, GLOVE, S)
    ell(dr, x + 5, y + 8, 18, 14, GLOVE_D, S)
    rect(dr, x - 25, y + 18, x + 25, y + 38, GLOVE, S, r=7)


def draw_top_hat(dr, x, y, ang, S, rabbit_k=0.0, t=0.0):
    """Le haut-de-forme du magicien : (x, y) = centre du bord, ang = angle (0 = droit, pi = retourné).
    Quand rabbit_k > 0, le lapin sort de l'ouverture (chapeau retourné)."""
    ca, sa = math.cos(ang), math.sin(ang)

    def P(u, v):          # u : vers le haut du chapeau ; v : vers la droite (grand chapeau : 1,3 × 1,1)
        u, v = u * 1.1, v * 1.3
        return (x + v * ca + u * sa, y + v * sa - u * ca)
    if rabbit_k > 0:
        RS = 1.4
        # le lapin, sorti de l'ouverture (vers le haut de l'écran, chapeau retourné)
        ov = 1.0 + 0.18 * math.sin(math.pi * clamp01(rabbit_k * 1.4)) * (rabbit_k < 0.72)
        rise = 150 * RS * smooth(rabbit_k) * ov
        cx, cy = x, y - rise + 10 * RS
        ell(dr, cx, cy + 40 * RS, 50 * RS, 54 * RS, RABBIT, S)
        ell(dr, cx, cy - 30 * RS, 40 * RS, 38 * RS, RABBIT, S)
        spring = clamp01((rabbit_k - 0.4) / 0.6)
        for side in (-1, 1):
            a = side * (0.5 - 0.38 * smooth(spring)) + 0.08 * math.sin(t * 9) * spring
            ex, ey = cx + (side * 18 + math.sin(a) * 60) * RS, cy - (60 + math.cos(a) * 60) * RS
            ear = [(ex + (math.sin(a) * 70 * s + math.cos(a) * w) * RS, ey + (-math.cos(a) * 70 * s + math.sin(a) * w) * RS)
                   for (s, w) in [(-1, -16), (-0.3, -20), (0.6, -14), (1, 0), (0.6, 14), (-0.3, 20), (-1, 16)]]
            dr.polygon(poly(ear, S), fill=RABBIT)
            inner = [(ex + (math.sin(a) * 50 * s + math.cos(a) * w) * RS, ey + (-math.cos(a) * 50 * s + math.sin(a) * w) * RS)
                     for (s, w) in [(-0.9, -7), (0.6, -7), (0.95, 0), (0.6, 7), (-0.9, 7)]]
            dr.polygon(poly(inner, S), fill=RABBIT_IN)
        ell(dr, cx - 44 * RS, cy + 6 * RS, 16 * RS, 12 * RS, RABBIT_D, S)
        ell(dr, cx + 44 * RS, cy + 6 * RS, 16 * RS, 12 * RS, RABBIT_D, S)
    crown = [P(0, -60), P(0, 60), P(140, 64), P(140, -64)]
    dr.polygon(poly(crown, S), fill=HATC)
    band = [P(8, -61), P(8, 61), P(34, 62), P(34, -62)]
    dr.polygon(poly(band, S), fill=HAT_BAND)
    top0, top1 = P(140, -64), P(140, 64)
    dr.line(poly([top0, top1], S), fill=HAT_RIM, width=max(1, int(6 * S)))
    e0, e1 = P(10, -52), P(128, -54)
    dr.line(poly([e0, e1], S), fill=HAT_RIM, width=max(1, int(4 * S)))
    # le bord
    bpts = [P(6 * math.sin(k * math.pi / 12), 84 * math.cos(k * math.pi / 12)) for k in range(25)]
    bpts += [P(-12 * math.sin(k * math.pi / 12), 84 * math.cos(math.pi - k * math.pi / 12)) for k in range(25)]
    dr.polygon(poly(bpts, S), fill=HATC)
    dr.line(poly(bpts[:25], S), fill=HAT_RIM, width=max(1, int(5 * S)))


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


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 8.4, "hook_top": 0.125, "hook_font_size": 88, "hook_width": 0.72, "hook_speed": 1.1,
    "narrator_voice": "bm_george", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
LINE_GAIN = {"notrabbit": 1.0, "dont": 1.05, "stay": 1.1, "abra": 1.1, "comeon": 1.0}


def exact_events(sim):
    return [(real_of(t), "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(sim.sc.P.hits)]


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
            gg = max(0.1, min(1.35, g)) ** 0.7 * 0.92
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


def plan_report(sim, narr, name_len, hv):
    """Contrôle du plan : intervalles, CV, silences, arcs, voix."""
    P = sim.sc.P
    hits = [real_of(h[0]) for h in P.hits]
    iv = [b - a for a, b in zip(hits, hits[1:])]
    m = float(np.mean(iv)); sd = float(np.std(iv))
    out = {"n_hits": len(hits), "cv": round(sd / m, 3), "mean_iv": round(m, 3), "min_iv": round(min(iv), 3),
           "max_iv": round(max(iv), 3)}
    # quarts
    D = real_of(END_SCENE)
    q = {}
    for name, (a, b) in {"Q1": (0, D / 4), "Q2-3": (D / 4, 0.75 * D), "Q4": (0.75 * D, D)}.items():
        ii = [y - x for x, y in zip(hits, hits[1:]) if a <= x < b]
        q[name] = round(float(np.median(ii)), 3) if ii else None
    out["median_iv"] = q
    # arcs
    cs = [P.start] + P.cs + [P.after]
    worst = []
    for a, b in zip(cs, cs[1:]):
        T = b["t"] - a["t"]
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        apex = a["y"] - (vy * vy / (2 * G) if vy < 0 else 0)
        h = a["y"] - apex
        if h > 600 or apex < 250 or T > 1.5:
            worst.append((round(a["t"], 2), round(T, 2), round(h), round(apex)))
    out["arcs_suspects"] = worst
    # chevauchements voix / mots
    clash = []
    for n in narr:
        for h in hits:
            if n["start"] - 0.9 < h < n["end"] + 0.1:
                clash.append((round(h, 2), n["text"]))
    if hv is not None:
        for h in hits:
            if h + name_len > HOOK_T - 0.05 and h < HOOK_T + len(hv) / SR + 0.05:
                clash.append((round(h, 2), "hook"))
    out["clash"] = clash
    # silences entre « Bounce » (fin d'un mot -> début du suivant) > 1,2 s
    sil = []
    for a, b in zip(hits, hits[1:]):
        g = b - (a + name_len)
        spoken = any(n["start"] < b and n["end"] > a + name_len for n in narr)
        if g > 1.15:
            sil.append((round(a + name_len, 2), round(g, 2), "voix" if spoken else "SILENCE"))
    out["trous"] = sil
    # zone de Bounce à l'écran (après cadrage) : x 300-780, y 450-1100
    n_in = n = 0
    tt = 0.0
    while tt < D:
        s_ = scene_of(tt)
        bx, by = P.pos(s_)
        Z = ZOOM(s_)
        ox = min(max(0.0, CAMX(s_) * Z - W / 2), W * (Z - 1))
        oy = min(max(0.0, CAMY(s_) * Z - 760.0), H * (Z - 1))
        sx_, sy_ = bx * Z - ox, by * Z - oy
        n += 1
        n_in += (300 <= sx_ <= 780 and 450 <= sy_ <= 1100)
        tt += 1 / 30
    out["zone_bounce"] = round(n_in / n, 3)
    out["duree"] = round(D, 2)
    out["issue_reel"] = round(real_of(ISSUE_S), 2)
    return out


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    name = base.hero_word(cfg["hero_name"], cfg)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "hits": len(ev),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [round(e[0], 3) for e in ev if round(e[0], 3) not in said]
    if "--plan" in argv:
        summary["plan"] = plan_report(sim, narr, len(name) / SR, hv)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    if "--stills" in argv:
        i = argv.index("--stills")
        times = [float(x) for x in argv[i + 1].split(",")]
        outd = argv[i + 2]
        os.makedirs(outd, exist_ok=True)
        Wc, Hc = cfg["width"], cfg["height"]
        for tt in times:
            img = Image.new("RGB", (Wc, Hc), BG)
            d = ImageDraw.Draw(img)
            base.HERO["pos"] = None
            sim.draw(d, tt, tt, 1)
            if tt < cfg["hook_text_s"]:
                lines, hf, lh, hook_top = base.layout_hook(cfg, 1, Wc, Hc, sim.scene_top * Hc - 30)
                for k, line in enumerate(lines):
                    d.text((Wc / 2, hook_top + (k + 0.5) * lh), line, fill=(255, 255, 255), anchor="mm", font=hf)
            img.save(os.path.join(outd, "s_%05.2f.png" % tt))
        print("stills", len(times))
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
