"""
Prototype « magic » v2 : Bounce au spectacle de magie.

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
              "Abracadabra!": "abra.wav", "Oh, come on.": "comeon.wav", "Gotcha!": "gotcha.wav",
              "Stay in there!": "stayin.wav", "Take him away!": "takeaway.wav", "Where are you?": "where.wav",
              "Hold still!": "hold.wav", "Come here...": "comehere.wav", "My rabbit!": "myrabbit.wav"}
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
SLOW = (57.95, 58.35, 0.5)       # intervalle en temps de scène, facteur de vitesse


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
# --- acte 1 : il sort du chapeau à la place du lapin
hard(0.12, "wood", 500, gain=1.1)
soft(0.85, "palm", 588, 735)
soft(1.60, "silk")
hard(2.40, "wood", 500)
soft(3.15, "palm", 600, 735)
soft(3.70, "palm", 604, 735)
soft(4.25, "palm", 600, 735)
soft(4.80, "palm", 600, 735)
hard(5.15, "wand", 578, 565, gain=1.2)          # la baguette s'envole
soft(5.50, "palm", 590, 735)
hard(6.05, "prophat", 400, 578, gain=1.15)      # le chapeau du tour bascule de la table, foulards partout
hard(6.90, "wood", 512)
hard(7.80, "wood", 505, gain=0.9)               # derrière le paravent
hard(8.85, "wood", 505, gain=1.1)
soft(9.70, "top", 520, 418)                     # assis sur le paravent
soft(10.30, "top", 522, 422)
soft(10.90, "top", 524, 430)
hard(11.35, "wood", 560, gain=1.1)
soft(11.95, "pad")
hard(12.45, "maghat", gain=1.2)                 # oreilles n°1 : il retombe sur le chapeau, l'enfonce
hard(13.30, "wood", 500)
press(14.05, 15.45, 500)                        # « Stay. »
hard(15.45, "wood", 500, gain=0.95)
soft(16.00, "press", 500, WOOD_Y + 18)
hard(16.40, "wood", 503, gain=1.05)
soft(16.88, "press", 500, WOOD_Y + 18)
hard(17.30, "wood", 500, gain=1.15)
soft(17.74, "press", 500, WOOD_Y + 20)
hard(18.15, "wood", 500, gain=1.35)             # il éjecte le magicien
hard(19.05, "wood", 515)
soft(19.85, "pad")
soft(20.45, "pad")
soft(21.00, "pad")
soft(21.45, "pad")
soft(21.85, "pad")
hard(22.15, "wand", 612, 598, gain=1.25)        # « Abracadabra! » : il cogne la baguette, le sort se retourne
soft(22.50, "pad")
# --- acte 2 : le magicien invisible
hard(23.30, "wood", 510)
hard(24.20, "wood", 500)
soft(25.00, "pad")
soft(25.65, "pad")
hard(26.40, "wood", 520)
soft(27.10, "pad")
soft(27.75, "pad")
hard(28.35, "wood", 500)                        # au lasso
soft(29.00, "pad")
hard(29.65, "wood", 500, gain=1.3)              # il soulève le magicien par la corde
hard(30.60, "flathat", gain=1.1)                # oreilles n°2 : il aplatit le chapeau tombé sur la table
hard(31.45, "wood", 500)
soft(32.30, "pad")
soft(33.10, "pad")
hard(33.85, "cage", 560, WOOD_Y - 20)           # en cage : la cage rebondit avec lui
hard(34.75, "cage", 588, WOOD_Y - 20, gain=1.1)
hard(35.60, "cage", 612, WOOD_Y - 20, gain=1.25)  # la cage s'envole sur la tête du magicien
hard(36.50, "wood", 520)
hard(37.30, "wood", 500)
hard(38.50, "wood", 520)
soft(39.40, "pad")
soft(40.05, "pad")
hard(40.85, "wood", 520)
soft(41.25, "carry", 520, 560)                  # les colombes l'emportent
soft(42.60, "carry")
hard(42.85, "maghat", gain=1.3)                 # oreilles n°3 : lâché sur le chapeau, enfoncé jusqu'au menton
hard(43.70, "wood", 520)
soft(44.55, "pad")
soft(45.20, "pad")
hard(45.85, "wood", 500)                        # aveugle : il fonce sur chaque « Bounce »
hard(46.80, "wood", 470)
hard(48.00, "wood", 520, gain=1.1)
hard(48.85, "wood", 500)
soft(49.60, "pad")
soft(50.25, "pad")
hard(51.00, "maghat", gain=1.25)                # le chapeau remonte : il y voit
hard(51.90, "wood", 500)
soft(52.70, "pad")
soft(53.30, "pad")
hard(54.10, "wood", 520)
hard(54.95, "wood", 500)
hard(56.00, "wood", 520, gain=1.05)
soft(56.70, "pad")
soft(57.30, "pad")
hard(57.95, "inhat", gain=1.2)                  # pris dans le chapeau : le lapin en jaillit
hard(60.10, "inhat", gain=1.35)                 # dernier « Bounce » : le lapin replonge dans le chapeau
soft(60.85, "palm", 760, 687)
soft(61.22, "palm", 760, 687)
END_SCENE = 61.38
C.sort(key=lambda c: c["t"])

for c in C:
    if c["kind"] == "wood":
        c["y"] = WOOD_Y
    elif c["kind"] == "silk":
        c["x"], c["y"] = HAT_X, SILK_Y
    elif c["kind"] == "pad":
        c["x"], c["y"] = PAD_X, PAD_Y + 6

TABLE_GONE = 999.0
PROP_GONE = 6.62                  # le chapeau du tour, basculé hors de la table
PROP_FLIP = (6.05, 6.62)
ZAP = 22.38
INVIS = 22.55
INHAT = (57.95, 60.10)            # Bounce dans le chapeau tenu par le magicien
CARRY = (41.25, 42.60)
RABBIT_OUT = (57.98, 58.55)       # le lapin jaillit et retombe dans la main droite
RABBIT_BACK = (60.18, 60.55)      # il replonge dans le chapeau
ISSUE_S = 60.40

# lignes du magicien (temps réel de déclenchement)
LINES = [(3.30, "That's not a rabbit.", "notrabbit"), (10.00, "Now you don't!", "dont"),
         (14.40, "Stay.", "stay"), (20.90, "Abracadabra!", "abra"), (25.10, "Oh, come on.", "comeon"),
         (27.30, "Gotcha!", "gotcha"), (32.45, "Stay in there!", "stayin"), (39.60, "Take him away!", "takeaway"),
         (44.65, "Where are you?", "where"), (49.80, "Hold still!", "hold"), (52.85, "Come here...", "comehere"),
         (59.15, "My rabbit!", "myrabbit")]


class Plan:
    def __init__(self):
        self.cs = C
        self.ts = [c["t"] for c in C]
        self.start = START
        self.after = {"t": 61.58, "x": 760, "y": 687}
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in C if not c["soft"]]

    def refresh(self):
        self.ts = [c["t"] for c in self.cs]
        self.hits = [(c["t"], c["gain"], c["x"], c["y"], c["kind"]) for c in self.cs if not c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.cs[i - 1]
        b = self.after if i >= len(self.cs) else self.cs[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        if a["x"] is None or b["x"] is None:
            return (500.0, WOOD_Y)
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
                amp = 0.12 if c["soft"] else 0.18
                sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
        pr = self.pressed(t)
        if pr > 0:
            sy *= 1 - 0.2 * pr; sx *= 1 + 0.16 * pr
        return sx, sy

    def pressed(self, t):
        k = 0.0
        for (a, b) in PRESS_SPANS:
            k = max(k, clamp01((t - a + 0.1) / 0.1) * clamp01((b - t) / 0.12))
        return k


PRESS_SPANS = [(14.05, 15.45), (15.95, 16.40), (16.83, 17.30), (17.69, 18.15)]

# ------------------------------------------------------------------ le magicien (temps de scène)
MX = KF(760.0, [(7.0, 760.0), (7.4, 680.0), (11.3, 680.0), (11.7, 700.0), (13.3, 700.0),
                (19.4, 640.0), (20.3, 640.0), (20.8, 720.0), (31.0, 720.0), (31.5, 740.0),
                (39.6, 740.0), (40.8, 690.0), (45.8, 690.0), (46.0, 650.0), (46.6, 690.0),
                (53.8, 690.0), (55.0, 650.0), (56.0, 700.0), (57.4, 720.0)])
LEAN = KF(0.0, [(0.0, -6.0), (0.3, 4.0), (1.0, -10.0), (1.7, -14.0), (2.3, -14.0), (2.5, 6.0), (3.2, 0.0),
                (3.4, -6.0), (3.8, 4.0), (4.2, -6.0), (4.6, 0.0),
                (5.9, -8.0), (6.1, 12.0), (6.6, 0.0),
                (11.0, 0.0), (11.25, 6.0), (11.75, -30.0), (12.45, -30.0), (12.6, 8.0), (13.3, 0.0),
                (19.4, 0.0), (19.6, 24.0), (20.3, 24.0), (20.8, 0.0), (21.2, -8.0), (21.6, 4.0), (22.1, -6.0),
                (22.2, 8.0), (22.7, -12.0), (24.2, -12.0), (24.5, 0.0), (25.1, 8.0), (25.6, -4.0), (26.2, 0.0),
                (27.1, 0.0), (27.25, -18.0), (27.6, 0.0), (28.35, 0.0), (28.45, -24.0), (29.0, -8.0),
                (31.5, 0.0), (32.4, 6.0), (33.0, -10.0), (33.6, 6.0), (35.6, 6.0), (35.8, -12.0),
                (36.3, 10.0), (36.7, -10.0), (37.1, 10.0), (37.5, -10.0), (37.9, 10.0), (38.3, 0.0),
                (39.0, 12.0), (39.4, 0.0), (42.85, 0.0), (43.0, 12.0), (43.5, -8.0), (44.0, 8.0), (44.5, 0.0),
                (45.85, 0.0), (46.05, -38.0), (46.35, -38.0), (46.7, 0.0),
                (47.05, 0.0), (47.25, 20.0), (47.5, -20.0), (47.75, 16.0), (48.0, -10.0), (48.3, 0.0),
                (51.0, 0.0), (51.3, -16.0), (51.9, -6.0), (54.0, -10.0), (55.0, -6.0), (57.4, -12.0),
                (57.95, -4.0), (58.6, 6.0), (59.2, -6.0), (59.7, 6.0), (60.1, 0.0)])
ANGER_K = KF(0.0, [(11.05, 0.0), (11.3, 1.0), (12.4, 1.0), (12.6, 0.4), (13.4, 0.0),
                   (20.4, 0.0), (20.7, 1.0), (22.15, 1.0), (22.3, 0.0)])
MAG_HOPS = [(11.30, 22), (11.55, 24), (50.40, 110)]
TIPTOE = KF(0.0, [(9.2, 0.0), (9.35, 22.0), (10.95, 22.0), (11.15, 0.0)])
SIT = [(13.60, 18.15)]
SIT_HOPS = [(15.45, 70), (16.40, 140), (17.30, 220)]
FLIGHTS = [(18.15, 19.45, (505.0, 640.0), (640.0, 1010.0))]
FLOOR_SIT = (19.45, 20.30)        # tombé derrière la table
LIFT = (29.65, 29.98, 30.32)      # soulevé par le lasso, puis retombe assis par terre
FLOOR2 = (30.32, 31.05)
TWITCH = [(5.2, 1.0), (18.2, 1.0), (24.25, 0.7), (36.55, 0.8), (48.05, 0.8), (54.15, 0.7)]
EARS = [(11.95, 12.45, "head"), (30.25, 30.60, "table"), (42.20, 42.85, "head")]
CRUSH = KF(0.0, [(12.44, 0.0), (12.5, 1.0), (13.0, 1.0), (13.4, 0.0),
                 (42.84, 0.0), (42.9, 1.0), (50.99, 1.0), (51.12, 0.0)])
HAT_OFF = (29.85, 30.25, 31.0, 31.55)   # tombe, sur la table, ramassé, remis
HAT_FLAT = KF(0.0, [(30.59, 0.0), (30.64, 0.7), (31.0, 0.6), (31.55, 0.6), (31.62, 0.0)])
HAT_HAND = (52.25, 52.70)               # il ôte son chapeau et le tient comme un filet
REST = (("rel", -20, 175), ("rel", 20, 175))
GLOVES = [
    (-9.0, 0.1, ("rel", -120, -175), ("rel", 50, -190)),             # ta-da
    (0.25, 0.25, ("rel", -110, -40), ("rel", 50, -60)),               # surpris
    (0.5, 0.3, ("abs", 588, 868), ("rel", 50, -60)),                  # paume tendue
    (0.95, 0.35, ("abs", 430, 760), ("rel", 50, -40)),                # il le lance dans le chapeau
    (1.45, 0.3, ("abs", 430, 690), ("rel", 40, 20)),                  # la main au-dessus du chapeau
    (2.45, 0.2, ("rel", -60, -80), ("rel", 50, -80)),                 # sursaut
    (2.85, 0.3, ("abs", 600, 868), ("rel", 50, -150)),                # il le présente
    (3.35, 0.2, ("abs", 600, 868), ("rel", 70, -100)),                # « That's not a rabbit. » : il secoue la main
    (3.75, 0.2, ("abs", 600, 868), ("rel", 50, -160)),
    (4.15, 0.2, ("abs", 600, 868), ("rel", 70, -100)),
    (4.55, 0.3, ("abs", 600, 868), ("abs", 700, 452)),                # la baguette au-dessus de lui
    (5.17, 0.12, ("abs", 590, 868), ("rel", 40, -170)),               # elle s'envole
    (5.75, 0.25, ("rel", -50, 150), ("rel", 40, -120)),
    (6.08, 0.2, ("rel", -120, -60), ("rel", 60, -120)),               # le chapeau du tour bascule
    (6.5, 0.3, ("abs", 680, 560), ("rel", 40, -60)),                  # il rattrape la baguette
    (6.95, 0.2, ("rel", -10, 120), ("rel", -40, 110)),                # la range dans sa manche
    (7.25, 0.35, ("abs", 392, 640), ("abs", 648, 640)),               # le foulard, tendu en paravent
    (7.6, 0.2, ("abs", 390, 600), ("abs", 650, 600)),
    (8.45, 0.25, ("abs", 390, 560), ("abs", 650, 560)),
    (9.25, 0.25, ("abs", 390, 520), ("abs", 650, 520)),
    (11.0, 0.25, ("abs", 400, 860), ("abs", 640, 860)),               # il tire le foulard
    (11.3, 0.15, ("rel", -60, 60), ("rel", 60, 60)),                  # poings serrés, trépigne
    (11.75, 0.3, ("rel", -60, 120), ("rel", 10, 140)),                # se penche au-dessus de la table
    (12.47, 0.1, ("hat", -70, 10), ("hat", 70, 10)),                  # chapeau enfoncé : il l'agrippe
    (13.0, 0.4, ("hat", -70, 0), ("hat", 70, 0)),                     # et le remonte
    (13.5, 0.2, ("rel", -90, -60), ("rel", 90, -60)),                 # il saute
    (14.1, 0.3, ("hip", -70, 20), ("hip", 70, 20)),                   # assis
    (14.4, 0.15, ("ball", -40, -60), ("hip", 70, 20)),                # « Stay. » : il lui tapote la tête
    (14.7, 0.15, ("ball", -40, -30), ("hip", 70, 20)),
    (15.0, 0.2, ("hip", -70, 20), ("hip", 70, 20)),
    (17.25, 0.15, ("hat", -60, 0), ("hat", 60, 0)),                   # il tient son chapeau
    (18.1, 0.1, ("hat", -60, 0), ("hat", 60, 0)),
    (19.4, 0.2, ("rel", -110, 40), ("rel", 110, 40)),                 # tombé derrière la table
    (20.3, 0.25, ("rel", -10, 120), ("rel", -40, 110)),               # la baguette sort de sa manche
    (20.7, 0.3, ("abs", 720, 440), ("rel", 80, -130)),                # il vise
    (21.2, 0.15, ("abs", 705, 452), ("rel", 110, -160)),              # « Abracadabra! »
    (21.6, 0.15, ("abs", 720, 440), ("rel", 80, -120)),
    (22.17, 0.1, ("abs", 718, 446), ("rel", 80, -130)),
    (22.7, 0.3, ("rel", -50, -120), ("rel", 40, -120)),               # invisible : il regarde ses mains
    (23.5, 0.15, ("rel", -50, 70), ("rel", 50, 70)),                  # il se tâte le ventre
    (23.7, 0.15, ("rel", -50, 100), ("rel", 50, 100)),
    (23.9, 0.15, ("rel", -50, 70), ("rel", 50, 70)),
    (24.1, 0.15, ("rel", -50, 100), ("rel", 50, 100)),
    (25.0, 0.25, ("rel", -130, 30), ("rel", 130, 30)),                # « Oh, come on. » : bras ouverts
    (25.6, 0.2, ("rel", -130, -10), ("rel", 130, -10)),
    (26.2, 0.25, ("rel", -10, 120), ("rel", -40, 110)),               # il tire une corde de foulards de sa manche
    (26.5, 0.25, ("rel", -10, 120), ("rel", 140, 10)),
    (26.75, 0.2, ("rel", -10, 120), ("rel", -40, 100)),
    (26.95, 0.2, ("rel", -10, 120), ("rel", 140, 0)),
    (27.15, 0.12, ("rel", -170, -70), ("rel", 60, 40)),               # il lance le lasso
    (27.5, 0.2, ("rel", -130, 40), ("rel", -70, 60)),                 # « Gotcha! »
    (28.38, 0.1, ("rel", -190, 70), ("rel", -130, 80)),               # la corde tire
    (28.9, 0.2, ("rel", -130, 40), ("rel", -70, 60)),
    (29.68, 0.1, ("rel", -150, -150), ("rel", -90, -160)),            # soulevé, bras en l'air
    (30.32, 0.2, ("rel", -110, 40), ("rel", 110, 40)),                # assis par terre
    (31.0, 0.3, ("abs", 600, 850), ("rel", 40, 60)),                  # il ramasse le chapeau aplati
    (31.55, 0.2, ("hat", -60, 0), ("hat", 60, 0)),                    # le remet : pop
    (32.0, 0.25, ("rel", -60, 60), ("rel", 60, 60)),
    (32.45, 0.25, ("rel", -60, -210), ("rel", 70, -60)),              # « Stay in there! » : le doigt en l'air
    (33.0, 0.15, ("rel", -170, -20), ("rel", 70, -60)),               # il pointe : la cage tombe
    (33.6, 0.3, ("rel", -60, 70), ("rel", 60, 70)),                   # poings sur les hanches
    (35.62, 0.12, ("rel", -120, -130), ("rel", 120, -130)),           # la cage lui arrive dessus
    (36.2, 0.2, ("rel", -95, -90), ("rel", 95, -90)),                 # mains aux barreaux
    (38.4, 0.3, ("rel", -70, -250), ("rel", 70, -250)),               # il soulève la cage
    (39.0, 0.2, ("rel", 90, -220), ("rel", 150, -170)),               # et la jette
    (39.5, 0.25, ("rel", -130, -160), ("rel", 130, -160)),            # « Take him away! » : les colombes
    (40.2, 0.2, ("rel", -150, -60), ("rel", 150, -60)),
    (41.3, 0.3, ("rel", -60, 50), ("rel", 60, 50)),                   # il regarde, ravi
    (41.9, 0.2, ("rel", -50, 20), ("rel", 50, 20)),                   # se frotte les mains
    (42.1, 0.15, ("rel", -20, 30), ("rel", 20, 30)),
    (42.3, 0.15, ("rel", -50, 20), ("rel", 50, 20)),
    (42.87, 0.1, ("rel", -130, -40), ("rel", 130, -40)),              # aveuglé
    (43.4, 0.3, ("rel", -170, 0), ("rel", -60, 20)),                  # il tâtonne
    (44.0, 0.3, ("rel", -150, 30), ("rel", 100, -10)),
    (44.65, 0.25, ("rel", -170, -40), ("rel", 170, -40)),             # « Where are you? »
    (45.85, 0.15, ("abs", 520, 800), ("abs", 640, 820)),              # il fonce sur le « Bounce » : clap
    (46.12, 0.08, ("abs", 478, 858), ("abs", 540, 858)),              # sur la table vide
    (46.5, 0.3, ("rel", -120, -20), ("rel", 120, -20)),
    (46.95, 0.2, ("rel", -180, -50), ("rel", 180, -50)),              # il enlace le vide
    (47.35, 0.15, ("rel", 30, 50), ("rel", -30, 50)),                 # et s'enlace lui-même
    (48.1, 0.3, ("rel", -120, -20), ("rel", 120, -20)),
    (49.8, 0.25, ("rel", -160, -90), ("rel", 160, -90)),              # « Hold still! »
    (50.35, 0.15, ("rel", -60, -240), ("rel", 60, -240)),             # il saute pour l'attraper
    (50.95, 0.15, ("rel", -130, -90), ("rel", 130, -90)),
    (51.4, 0.3, ("rel", -60, 50), ("rel", 60, 50)),
    (51.95, 0.25, ("hat", -60, 0), ("hat", 60, 0)),                   # il ôte son chapeau
    (52.6, 0.3, ("abs", 600, 800), ("rel", 60, 50)),                  # le tient comme un filet
    (52.95, 0.15, ("abs", 600, 800), ("rel", 110, -70)),              # « Come here... » : il fait signe
    (53.2, 0.15, ("abs", 600, 800), ("rel", 70, -30)),
    (53.45, 0.15, ("abs", 600, 800), ("rel", 110, -70)),
    (53.8, 0.4, ("abs", 560, 780), ("rel", 60, 50)),                  # il s'approche à pas de loup
    (55.2, 0.5, ("abs", 640, 800), ("rel", 60, 40)),
    (56.3, 0.5, ("abs", 600, 790), ("rel", 60, 40)),
    (57.55, 0.3, ("abs", 600, 812), ("rel", 60, 40)),                 # sous lui : pris !
    (58.0, 0.25, ("abs", 600, 822), ("abs", 800, 640)),               # la main droite attrape le lapin
    (58.6, 0.25, ("abs", 600, 822), ("abs", 790, 660)),               # il le serre contre lui
    (59.15, 0.15, ("abs", 600, 812), ("abs", 800, 645)),              # « My rabbit! »
    (59.4, 0.15, ("abs", 600, 822), ("abs", 790, 660)),
    (60.25, 0.2, ("abs", 600, 822), ("abs", 760, 820)),               # le lapin file : il ne tient plus que Bounce
]
GLOVES.sort(key=lambda g: g[0])
WAND_FLY = (5.17, 6.70, (618.0, 452.0), (680.0, 560.0), 5.0)
WAND_SLEEVE = (7.05, 20.40)
WAND_AIM = (20.40, 22.15)
WAND_FLIP = (22.15, 22.30)
WAND_DROP = (22.55, 23.0)
CHARGE = [(20.9, 22.15)]
POOFS = [(ZAP, 760.0, 760.0, 1.4)]
CAGE_DROP = (33.00, 33.40)
CAGE_FLY = (35.60, 36.15)
CAGE_LIFT = (38.40, 38.90)
CAGE_TOSS = (39.00, 39.55)
DOVES = (40.15, 41.25, 42.60, 43.50)    # sortent des gants, l'attrapent, le lâchent, s'envolent
LASSO_PULL = (26.30, 27.15)
LASSO_THROW = (27.15, 27.45)
LASSO_ON = (27.45, 30.60)
LAUGH = [(0.2, 0.6), (2.5, 0.8), (5.3, 0.9), (6.1, 0.8), (11.1, 0.7), (12.5, 1.0), (14.5, 0.7), (16.4, 0.6),
         (17.4, 0.8), (18.2, 1.0), (22.4, 1.0), (25.2, 0.6), (28.4, 0.7), (29.7, 1.0), (30.6, 0.9),
         (33.4, 0.8), (35.7, 1.0), (41.3, 0.8), (42.9, 1.0), (46.1, 0.8), (47.4, 0.9), (50.5, 0.7), (51.0, 0.9),
         (57.95, 1.0), (60.2, 1.0)]
ARMS_UP = [(22.4, 23.9), (58.0, 59.3)]
EXPR = [(5.15, 5.7, "shock"), (6.05, 6.5, "shock"), (10.95, 11.6, "shock"), (12.45, 13.0, "win"),
        (13.65, 14.1, "shock"), (14.1, 18.15, "lose"), (18.2, 19.2, "win"), (22.15, 22.55, "shock"),
        (22.55, 24.3, "win"), (27.45, 29.6, "lose"), (29.65, 30.55, "shock"), (30.6, 31.3, "win"),
        (33.3, 35.6, "lose"), (35.62, 36.3, "shock"), (36.3, 37.2, "win"), (41.25, 42.6, "lose"),
        (42.6, 42.85, "shock"), (42.9, 43.6, "win"), (57.95, 58.4, "shock"), (58.4, 60.08, "lose"),
        (60.1, 60.6, "shock"), (60.6, 99.0, "calm")]


def gloves_spec_at(t):
    i = 0
    for k, g in enumerate(GLOVES):
        if g[0] <= t:
            i = k
    return i


def qbez(p0, p1, p2, u):
    a = (1 - u) * (1 - u)
    b = 2 * u * (1 - u)
    c = u * u
    return a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]


# ------------------------------------------------------------------ scène
class Scene:
    def __init__(self):
        self.P = Plan()
        # les contacts posés sur le chapeau du magicien ou dans le chapeau tenu : calculés sur le dessin
        for c in self.P.cs:
            if c["kind"] == "maghat":
                J = self.rig(c["t"] - 1e-3)
                hx, hy, ang = self.hat_base(c["t"] - 1e-3, J)
                top = self.hat_top(hx, hy, ang)
                c["x"], c["y"] = top[0], top[1] - R + 4
            elif c["kind"] == "flathat":
                c["x"], c["y"] = 600.0, TABLE[2] - 154 - R + 6
            elif c["kind"] == "inhat":
                J = self.rig(c["t"])
                bx, by = self.inhat_pos(c["t"], J)
                c["x"], c["y"] = bx, by
        carry_end = [c for c in self.P.cs if c["kind"] == "carry"][-1]
        mh = [c for c in self.P.cs if c["kind"] == "maghat" and c["t"] > carry_end["t"]][0]
        carry_end["x"], carry_end["y"] = mh["x"] - 120, mh["y"] - 130
        self.P.refresh()
        self.rings = [(t, g, x, y, k) for (t, g, x, y, k) in self.P.hits]

    # ---- Bounce : trajectoire, avec les passages où il est porté ou tenu
    def bpos(self, t):
        a, b = CARRY
        if a <= t <= b:
            p0 = (520.0, 560.0)
            ce = [c for c in self.P.cs if c["kind"] == "carry"][-1]
            p2 = (ce["x"], ce["y"])
            u = smooth((t - a) / (b - a))
            x, y = qbez(p0, (560.0, 330.0), p2, u)
            return x + 6 * math.sin(t * 13), y + 10 * math.sin(t * 9)
        a, b = INHAT
        if a <= t <= b:
            J = self.rig(t)
            return self.inhat_pos(t, J)
        return self.P.pos(t)

    def inhat_pos(self, t, J):
        hx, hy, ang = self.hat(t, J)[:3]
        bob = 18 * abs(math.sin((t - INHAT[0]) * 5.5)) if t > INHAT[0] + 0.3 else 0.0
        return hx, hy - 52 - bob

    def ball(self, t):
        x, y = self.bpos(t)
        sx, sy = self.P.squash(t)
        if CARRY[0] <= t <= CARRY[1]:
            k = math.sin(t * 11)
            sx, sy = 1 + 0.06 * k, 1 - 0.06 * k
        y += R * (1 - sy) * 0.9
        return x, y, R * sx, R * sy

    # ---- le magicien
    def hip(self, t):
        x, y = MX(t), STAND_HIP - hop(t, MAG_HOPS) - TIPTOE(t)
        for (a, b) in SIT:
            if a <= t <= b:
                bx, by = self.P.pos(t)
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
        a, m, b = LIFT
        if a <= t <= b:
            if t < m:
                k = smooth((t - a) / (m - a))
                return lerp(720.0, 640.0, k), lerp(STAND_HIP, 700.0, k)
            k = (t - m) / (b - m)
            return lerp(640.0, 770.0, k), lerp(700.0, 1040.0, k * k)
        a, b = FLOOR2
        if a <= t <= b + 0.5:
            k = clamp01((b + 0.5 - t) / 0.5) if t > b else 1.0
            return lerp(MX(t), 770.0, smooth(k)), lerp(STAND_HIP, 1040.0, smooth(k))
        return x, y

    def mode(self, t):
        for (a, b) in SIT:
            if a + 0.3 <= t <= b:
                return "sit"
        for (a, b, p0, p1) in FLIGHTS:
            if a <= t <= b:
                return "fly"
        if LIFT[0] <= t <= LIFT[2]:
            return "fly"
        a, b = FLOOR_SIT
        if a <= t <= b + 0.3:
            return "floor"
        a, b = FLOOR2
        if a <= t <= b + 0.3:
            return "floor"
        return "stand"

    def rig(self, t):
        hx, hy = self.hip(t)
        anger = ANGER_K(t)
        if anger > 0.05:
            hx += (2 + 7 * anger) * math.sin(t * 70.0)
        lean = LEAN(t)
        mode = self.mode(t)
        if mode == "fly":
            lean += 25 * math.sin(t * 9.0)
        a = math.radians(lean)
        u = (math.sin(a), -math.cos(a))
        r = (math.cos(a), math.sin(a))

        def P(du, dr):
            return (hx + u[0] * du + r[0] * dr, hy + u[1] * du + r[1] * dr)
        infl = 1.0 + 0.22 * anger
        J = {"hip": (hx, hy), "u": u, "r": r, "lean": lean, "infl": infl, "anger": anger, "mode": mode, "P": P}
        J["sh"] = P(190, 0)
        J["shL"], J["shR"] = P(190, -64 * infl), P(190, 64 * infl)
        J["head"] = P(250, 0)
        J["tie"] = P(186, 0)
        if mode in ("sit", "fly"):
            dang = 0.0 if mode == "sit" else 30 * math.sin(t * 12.0)
            J["kL"], J["kR"] = (hx - 118, hy - 20), (hx + 118, hy - 20)
            J["fL"] = (hx - 150, hy + 118 - dang)
            J["fR"] = (hx + 150, hy + 118 + dang)
        elif mode == "floor":
            J["fL"] = (hx - 150, FLOOR - 40)
            J["fR"] = (hx - 110, FLOOR - 70)
        else:
            lift = STAND_HIP - hy
            J["fL"] = (hx - 28, FLOOR - 10 - max(0.0, lift))
            J["fR"] = (hx + 28, FLOOR - 10 - max(0.0, lift))
        J["gL"], J["gR"] = self.gloves(t, J)
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
            out.append((lerp(p0[0], p1[0], k), lerp(p0[1], p1[1], k)))
        for c in self.P.cs:
            if c["kind"] == "palm" and -0.05 <= t - c["t"] <= 0.2:
                d = 14 * math.sin(math.pi * clamp01((t - c["t"] + 0.05) / 0.25))
                if c["t"] > 60:
                    out[1] = (out[1][0], out[1][1] + d)
                else:
                    out[0] = (out[0][0], out[0][1] + d)
        return out[0], out[1]

    def hat_base(self, t, J):
        """Le chapeau sur la tête : centre du bord, angle (rad), enfoncé ou non."""
        u = J["u"]
        cr = CRUSH(t)
        d = 44 - 112 * cr
        hx, hy = J["head"][0] + u[0] * d, J["head"][1] + u[1] * d
        return hx, hy, math.radians(J["lean"])

    def hat_top(self, hx, hy, ang, flat=0.0):
        h = 154 * (1 - 0.6 * flat)
        return hx + math.sin(ang) * h, hy - math.cos(ang) * h

    def hat(self, t, J):
        """(x, y, angle, aplati, ouverture vers le haut ?) du haut-de-forme du magicien."""
        hx, hy, ang = self.hat_base(t, J)
        flat = 0.0
        for (t0, amp) in TWITCH:
            v = t - t0
            if 0 <= v <= 0.35:
                hy -= amp * 16 * math.sin(math.pi * v / 0.35)
                ang += amp * 0.1 * math.sin(2 * math.pi * v / 0.35)
        for (a, b, where) in EARS:
            if where == "head" and a - 0.1 <= t <= b:
                hy -= 14 * math.sin(math.pi * clamp01((t - a + 0.1) / 0.25))
        a, b, c, d = HAT_OFF
        if a <= t <= d:
            land = (600.0, TABLE[2])
            if t < b:
                p = arc((hx, hy), land, a, b - a, t)
                return p[0], p[1], ang * (1 - (t - a) / (b - a)) + 2 * math.pi * (t - a) / (b - a), 0.0, False
            if t < c:
                return land[0], land[1], 0.0, HAT_FLAT(t), False
            k = smooth((t - c) / (d - c))
            return lerp(land[0], hx, k), lerp(land[1], hy, k) - 60 * math.sin(math.pi * k), ang * k, HAT_FLAT(t), False
        flat = max(flat, 0.18 * CRUSH(t))
        a, b = HAT_HAND
        if t >= a:
            g = J["gL"]
            k = smooth((t - a) / (b - a))
            tx, ty = g[0], g[1] - 34
            return lerp(hx, tx, k), lerp(hy, ty, k), lerp(ang, math.pi, k), 0.0, k > 0.5
        return hx, hy, ang, flat, False

    # ---- la baguette : (x de la poignée, y, angle) ou None
    def wand(self, t, J):
        if t < WAND_FLY[0]:
            ang = 205.0 if t < 4.5 else lerp(205.0, 180.0, smooth((t - 4.5) / 0.3))
            g = J["gR"]
            return g[0], g[1], math.radians(ang)
        a, b, p0, p1, spin = WAND_FLY
        if t < b:
            x, y = arc(p0, p1, a, b - a, t)
            return x, y, math.radians(180) + spin * 2 * math.pi * (t - a) / (b - a)
        if t < WAND_SLEEVE[0]:
            g = J["gL"]
            return g[0], g[1], math.radians(-60)
        if t < WAND_SLEEVE[1]:
            return None
        if t < WAND_FLIP[0]:
            g = J["gL"]
            k = smooth((t - WAND_SLEEVE[1]) / 0.4)
            return g[0], g[1], lerp(math.radians(-90), math.radians(205), k)
        if t < WAND_DROP[0]:
            g = J["gL"]
            k = smooth((t - WAND_FLIP[0]) / (WAND_FLIP[1] - WAND_FLIP[0]))
            return g[0], g[1], lerp(math.radians(205), math.radians(415), k)
        a, b = WAND_DROP
        if t < b:
            x, y = arc((680.0, 500.0), (700.0, 1150.0), a, b - a, t)
            return x, y, math.radians(415) + 9 * (t - a)
        return None

    def wand_tip(self, w):
        x, y, a = w[:3]
        L = w[3] if len(w) > 3 else 150.0
        return x + L * math.cos(a), y + L * math.sin(a)

    # ---- la cage : centre bas (x, y) ou None
    def cage(self, t, J):
        if t < CAGE_DROP[0] or t > CAGE_TOSS[1]:
            return None
        bx, by = self.bpos(t)
        follow = (bx, by + R + 22)
        if t < CAGE_DROP[1]:
            k = (t - CAGE_DROP[0]) / (CAGE_DROP[1] - CAGE_DROP[0])
            return follow[0], follow[1] - 900 * (1 - k * k)
        if t < CAGE_FLY[0]:
            return follow
        head = (J["head"][0], J["head"][1] + 170)
        if t < CAGE_FLY[1]:
            p0 = self.cage(CAGE_FLY[0] - 1e-3, J)
            return arc(p0, head, CAGE_FLY[0], CAGE_FLY[1] - CAGE_FLY[0], t)
        if t < CAGE_LIFT[0]:
            return head
        if t < CAGE_LIFT[1]:
            k = smooth((t - CAGE_LIFT[0]) / (CAGE_LIFT[1] - CAGE_LIFT[0]))
            return head[0], head[1] - 230 * k
        return arc((head[0], head[1] - 230), (1200.0, 100.0), CAGE_TOSS[0], CAGE_TOSS[1] - CAGE_TOSS[0], t)

    # ---- le lapin : (x, y, ressort des oreilles 0..1, visible) ou None
    def rabbit(self, t, J):
        a, b = RABBIT_OUT
        hx, hy, ang, _f, up = self.hat(t, J)
        gR = J["gR"]
        hold = (gR[0] - 10, gR[1] - 70)
        if a <= t < b:
            p = arc((hx, hy - 40), hold, a, b - a, t)
            return p[0], p[1], clamp01((t - a) / 0.2), (t - a) * 9
        a2, b2 = RABBIT_BACK
        if b <= t < a2:
            return hold[0], hold[1], 1.0, 0.0
        if a2 <= t < b2:
            p = arc(hold, (hx, hy - 20), a2, b2 - a2, t)
            return p[0], p[1], 1.0, -(t - a2) * 9
        if t >= b2:
            return hx, hy, -1.0, 0.0        # rentré : seules ses oreilles dépassent du chapeau
        return None


# ------------------------------------------------------------------ cadrage : serré dès le début (scène sur ~75 % de la hauteur)
CAM_Z = KF(1.42, [(56.6, 1.42), (57.6, 1.5)])
CAM_OX = KF(134.0, [(56.6, 134.0), (57.6, 250.0)])
CAM_OY = KF(89.0, [(56.6, 89.0), (57.6, 180.0)])


def cam(t):
    return CAM_Z(t), CAM_OX(t), CAM_OY(t)


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
        self.bubbles = []

    def set_narr(self, narr):
        self.bubbles = [(scene_of(n["start"]), scene_of(max(n["end"] + 0.35, n["start"] + 0.5 + 0.3 * len(n["text"].split()))),
                         n["text"]) for n in narr]

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
        Z, ox, oy = cam(t)
        S = S0 * Z
        full = dr._image
        wimg = Image.new("RGB", (int(W * S) + 2, int(H * S) + 2), BG)
        dr = ImageDraw.Draw(wimg)
        self.img = wimg
        J = sc.rig(t)
        self.draw_back(dr, t, S)
        front = J["mode"] in ("sit", "fly")
        if not front:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_table(dr, t, S)
        self.draw_prop_hat(dr, t, S, back=True)
        self.draw_pad(dr, t, S)
        if front:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_rings(dr, t, S)
        bx, by, brx, bry = sc.ball(t)
        in_hat = abs(bx - HAT_X) < 140 and by > 600 and t < PROP_FLIP[0]
        if in_hat:
            self.draw_bounce(dr, t, S, bx, by, brx, bry)
            self.draw_prop_hat(dr, t, S, back=False)
        else:
            self.draw_prop_hat(dr, t, S, back=False)
        self.draw_silks(dr, t, S)
        self.draw_magician(dr, t, S, J, part="arms")
        self.draw_magician(dr, t, S, J, part="hat")
        w = sc.wand(t, J)
        if w is not None:
            self.draw_wand(dr, w, S)
        self.draw_charge(dr, t, S, w)
        self.draw_lasso(dr, t, S, J, back=True)
        if not in_hat:
            self.draw_bounce(dr, t, S, bx, by, brx, bry)
        self.draw_inhat_front(dr, t, S, J)
        self.draw_lasso(dr, t, S, J, back=False)
        self.draw_cage(dr, t, S, J)
        self.draw_doves(dr, t, S, J)
        self.draw_screen(dr, t, S, J)
        self.draw_magician(dr, t, S, J, part="front")
        self.draw_burst(dr, t, S)
        self.draw_stage_front(dr, t, S)
        self.draw_audience(dr, t, S)
        self.draw_bubble(dr, t, S, J)
        x0, y0 = int(ox * S0 * Z / Z * Z / Z), int(oy * S0)
        x0 = int(ox * S)
        y0 = int(oy * S)
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
            ell(dr, 560, 700, 470 * k, 560 * k, c, S)
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
        if t < 11.65:
            return
        x0, x1, top = PAD
        bx, by = self.sc.bpos(t)
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
        dy = 0.0
        for c in self.sc.P.cs:
            if c["kind"] == "silk":
                v = t - c["t"]
                if 0 <= v <= 0.25:
                    dy -= 10 * math.sin(math.pi * v / 0.25)
        a, b = PROP_FLIP
        if t >= a:
            # cogné sur le bord : il bascule et tombe de la table (pivot en bas à gauche)
            k = (t - a) / (b - a)
            ang = -2.2 * k * k - 0.4 * k
            if back:
                return
            img = Image.new("RGBA", (int(420 * S), int(420 * S)), (0, 0, 0, 0))
            d2 = ImageDraw.Draw(img)
            o = 210.0
            pts = [(o - HAT_W / 2, o - HAT_H / 2), (o + HAT_W / 2, o - HAT_H / 2), (o + HAT_W / 2 - 14, o + HAT_H / 2),
                   (o - HAT_W / 2 + 14, o + HAT_H / 2)]
            d2.polygon(poly(pts, S), fill=HATC + (255,))
            d2.rectangle([(o - HAT_W / 2) * S, (o - HAT_H / 2 + 22) * S, (o + HAT_W / 2) * S, (o - HAT_H / 2 + 50) * S],
                         fill=HAT_BAND + (255,))
            d2.ellipse([(o - HAT_W / 2 - 32) * S, (o - HAT_H / 2 - 28) * S, (o + HAT_W / 2 + 32) * S,
                        (o - HAT_H / 2 + 28) * S], fill=HATC + (255,), outline=HAT_RIM + (255,), width=max(1, int(6 * S)))
            img = img.rotate(math.degrees(-ang), resample=Image.BICUBIC)
            px = cx - 160 * k
            py = (top + bot) / 2 + 300 * k * k
            dr._image.paste(img, (int((px - 210) * S), int((py - 210) * S)), img)
            return
        top += dy
        if back:
            ell(dr, cx, top, HAT_W / 2 + 32, 28, HATC, S)
            ell(dr, cx, top, HAT_W / 2 - 4, 18, (8, 6, 12), S)
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
        dr.arc([(cx - HAT_W / 2 - 32) * S, (top - 28) * S, (cx + HAT_W / 2 + 32) * S, (top + 28) * S], 0, 180,
               fill=HAT_RIM, width=max(1, int(8 * S)))

    def draw_silks(self, dr, t, S):
        emits = [c["t"] for c in self.sc.P.cs if c["kind"] == "silk"] + [-0.8, -0.3, PROP_FLIP[0]]
        for te in emits:
            v = t - te
            if not (0 <= v <= 1.0):
                continue
            n = 14 if te == PROP_FLIP[0] else 6
            for k in range(n):
                ang = -math.pi / 2 + (k - (n - 1) / 2) * (0.32 if n == 6 else 0.22)
                sp = 520 + 60 * (k % 3) + (200 if n > 6 else 0)
                x = HAT_X + math.cos(ang) * sp * v
                y = TABLE[2] - HAT_H + math.sin(ang) * sp * v + 0.5 * 1800 * v * v
                a = v * 9 + k
                col = SILKS[k % len(SILKS)]
                s = 22 if n == 6 else 28
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
            bx, by = x, y
            dr.ellipse([(bx - r) * S, (by - r) * S, (bx + r) * S, (by + r) * S], outline=col, width=max(2, int(w * S)))

    def draw_screen(self, dr, t, S, J):
        if not (7.25 <= t <= 11.65):
            return
        gL, gR = J["gL"], J["gR"]
        grow = smooth((t - 7.25) / 0.35)
        top = (gL[1] + gR[1]) / 2
        x0 = lerp((gL[0] + gR[0]) / 2, gL[0], grow)
        x1 = lerp((gL[0] + gR[0]) / 2, gR[0], grow)
        bot = TABLE[2] + 4
        if t > 11.0:
            k = smooth((t - 11.0) / 0.5)
            top = lerp(top, PAD[2], k)
            x0, x1 = lerp(x0, PAD[0], k), lerp(x1, PAD[1], k)
        bx, by = self.sc.bpos(t)
        sag = 0.0
        if 9.55 <= t <= 11.1 and by < top:
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
    def ghost_layer(self, S):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def draw_magician(self, dr, t, S, J, part):
        vis = t < INVIS
        P = J["P"]
        infl = J["infl"]
        col = mix(SUIT, ANGER, 0.85 * J["anger"])
        cold = mix(SUIT_D, dim(ANGER, 0.75), 0.85 * J["anger"])
        if part == "body":
            if vis:
                cp = [P(196, -70 * infl), P(196, 70 * infl), P(-95, 150 * infl), P(-95, -150 * infl)]
                dr.polygon(poly(cp, S), fill=CAPE)
                cl = [P(186, -50 * infl), P(186, 50 * infl), P(-85, 125 * infl), P(-85, -125 * infl)]
                dr.polygon(poly(cl, S), fill=CAPE_L)
                if J["mode"] not in ("sit", "fly"):
                    for (fx, fy), dx in ((J["fL"], -24), (J["fR"], 24)):
                        capsule(dr, P(10, dx), (fx, fy - 18), 15, (26, 28, 44), S)
                body = [P(-60, -50 * infl), P(-60, 50 * infl), P(0, 62 * infl), P(150, 70 * infl),
                        P(198, 58 * infl), P(204, 0), P(198, -58 * infl), P(150, -70 * infl), P(0, -62 * infl)]
                dr.polygon(poly(body, S), fill=col)
                dr.polygon(poly([P(196, -22), P(196, 22), P(80, 0)], S), fill=SHIRT)
                for k in range(3):
                    c = P(60 + k * 34, -4)
                    ell(dr, c[0], c[1], 5, 5, cold, S)
                hc = J["head"]
                ell(dr, hc[0], hc[1], 52, 52, (232, 196, 170), S)
                ell(dr, hc[0] - 49, hc[1] + 6, 11, 9, (232, 196, 170), S)
            else:
                # invisible : un corps blanc translucide au contour épais et lumineux
                lay = self.ghost_layer(S)
                ld = ImageDraw.Draw(lay)
                fill, line = (226, 230, 255, 125), (246, 248, 255, 235)
                body = [P(-60, -50), P(-60, 50), P(0, 62), P(150, 70), P(198, 58), P(204, 0), P(198, -58),
                        P(150, -70), P(0, -62)]
                if J["mode"] not in ("sit", "fly"):
                    for (fx, fy), dx in ((J["fL"], -24), (J["fR"], 24)):
                        a0 = P(-50, dx)
                        ld.line([a0[0] * S, a0[1] * S, fx * S, (fy - 14) * S], fill=fill, width=max(1, int(30 * S)))
                        ld.line([a0[0] * S, a0[1] * S, fx * S, (fy - 14) * S], fill=line, width=max(1, int(7 * S)))
                ld.polygon(poly(body, S), fill=fill)
                ld.line(poly(body + body[:1], S), fill=line, width=max(1, int(8 * S)), joint="curve")
                hc = J["head"]
                ld.ellipse([(hc[0] - 52) * S, (hc[1] - 52) * S, (hc[0] + 52) * S, (hc[1] + 52) * S], fill=fill,
                           outline=line, width=max(1, int(8 * S)))
                self.img.paste(lay, (0, 0), lay)
            if J["mode"] not in ("sit", "fly"):
                for (fx, fy) in (J["fL"], J["fR"]):
                    self.shoe(dr, t, fx, fy, S)
            return
        if part == "arms":
            if vis:
                for (s, g) in ((J["shL"], J["gL"]), (J["shR"], J["gR"])):
                    capsule(dr, s, g, 17, cold, S)
            else:
                lay = self.ghost_layer(S)
                ld = ImageDraw.Draw(lay)
                for (s, g) in ((J["shL"], J["gL"]), (J["shR"], J["gR"])):
                    ld.line([s[0] * S, s[1] * S, g[0] * S, g[1] * S], fill=(226, 230, 255, 125), width=max(1, int(34 * S)))
                    ld.line([s[0] * S, s[1] * S, g[0] * S, g[1] * S], fill=(246, 248, 255, 235), width=max(1, int(7 * S)))
                self.img.paste(lay, (0, 0), lay)
            for g in (J["gL"], J["gR"]):
                glove(dr, g[0], g[1], S, big=not vis)
            return
        if part == "front":
            if J["mode"] not in ("sit", "fly"):
                return
            for (fx, fy), kn, dx in ((J["fL"], J["kL"], -24), (J["fR"], J["kR"], 24)):
                if vis:
                    capsule(dr, P(10, dx), kn, 15, (26, 28, 44), S)
                    capsule(dr, kn, (fx, fy - 18), 15, (26, 28, 44), S)
                else:
                    dr.line(poly([P(10, dx), kn, (fx, fy - 18)], S), fill=(246, 248, 255), width=max(1, int(7 * S)))
                self.shoe(dr, t, fx, fy, S)
            return
        # « hat » : nœud papillon et chapeau (derrière Bounce)
        tc = J["tie"]
        a = math.radians(J["lean"])
        sz = 1.0 if vis else 1.35
        for shape in ([(-30, -14), (0, 0), (-30, 14)], [(30, -14), (0, 0), (30, 14)]):
            dr.polygon(poly([(tc[0] + sz * (u * math.cos(a) - v * math.sin(a)), tc[1] + sz * (u * math.sin(a) + v * math.cos(a)))
                             for (u, v) in shape], S), fill=TIE)
        ell(dr, tc[0], tc[1], 9 * sz, 9 * sz, dim(TIE, 0.8), S)
        hx_, hy_, ang, flat, up = self.sc.hat(t, J)
        ears, lid = 0.0, 0.0
        for (ea, eb, where) in EARS:
            if ea <= t <= eb:
                k = clamp01((t - ea) / 0.12)
                ears, lid = k, k
        draw_top_hat(dr, hx_, hy_, ang, S, flat=flat, ears=ears, lid=lid, t=t)
        rb = self.sc.rabbit(t, J)
        if rb is not None and rb[2] >= 0:
            draw_rabbit(dr, rb[0], rb[1], S, rb[2], rb[3], t)

    def draw_inhat_front(self, dr, t, S, J):
        """Quand Bounce est dans le chapeau tenu (ouverture en haut), le devant du chapeau passe devant lui."""
        if not (HAT_HAND[1] <= t):
            return
        hx_, hy_, ang, flat, up = self.sc.hat(t, J)
        if t >= RABBIT_BACK[1]:
            # le lapin est rentré : ses oreilles dépassent de l'ouverture, et s'enfoncent un peu
            k = 1.0 - 0.35 * smooth((t - RABBIT_BACK[1]) / 0.8)
            for side in (-1, 1):
                bx_, by_ = hx_ + side * 20, hy_ - 4
                L = 150 * k
                ae = side * 0.22 + 0.05 * math.sin(t * 7)
                tip = (bx_ + math.sin(ae) * L, by_ - math.cos(ae) * L)
                nx, ny = math.cos(ae) * 22, math.sin(ae) * 22
                dr.polygon(poly([(bx_ - nx, by_ - ny), (bx_ + nx, by_ + ny), (tip[0] + nx * 0.6, tip[1] + ny * 0.6), tip,
                                 (tip[0] - nx * 0.6, tip[1] - ny * 0.6)], S), fill=RABBIT)
                dr.polygon(poly([(bx_ - nx * 0.4, by_ - ny * 0.4), (bx_ + nx * 0.4, by_ + ny * 0.4),
                                 ((bx_ + tip[0]) / 2, (by_ + tip[1]) / 2), tip], S), fill=RABBIT_IN)
            draw_top_hat(dr, hx_, hy_, ang, S, front_only=True)
            return
        if up and INHAT[0] <= t <= INHAT[1] + 0.05:
            draw_top_hat(dr, hx_, hy_, ang, S, front_only=True)

    def shoe(self, dr, t, fx, fy, S):
        pts = [(-46, -12), (34, -18), (40, 10), (-46, 12)]
        dr.polygon(poly([(fx + u, fy + v) for (u, v) in pts], S), fill=SHOE)
        dr.line(poly([(fx - 40, fy - 12), (fx + 30, fy - 17)], S), fill=SHOE_L, width=max(1, int(4 * S)))

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

    def draw_charge(self, dr, t, S, w):
        if w is None:
            return
        tip = self.sc.wand_tip(w)
        for (a, b) in CHARGE:
            if a <= t <= b:
                k = clamp01((t - a) / (b - a))
                for i in range(7):
                    ang = i * 0.9 + t * 5
                    rr = (16 + 40 * k) * (0.6 + 0.4 * math.sin(t * 17 + i))
                    sp = (tip[0] + rr * math.cos(ang), tip[1] + rr * math.sin(ang))
                    dr.polygon(poly(star_pts(sp[0], sp[1], 9 + 10 * k, t * 4 + i, 4, 0.35), S), fill=SPARK)
                ell(dr, tip[0], tip[1], 10 + 12 * k, 10 + 12 * k, (255, 250, 220), S)

    def draw_burst(self, dr, t, S):
        if ZAP - 0.18 <= t <= ZAP:
            v = (t - ZAP + 0.18) / 0.18
            p0, p1 = (618.0, 520.0), (760.0, 780.0)
            for j in range(5):
                vv = max(0.0, v - j * 0.06)
                p = (lerp(p0[0], p1[0], vv), lerp(p0[1], p1[1], vv))
                dr.polygon(poly(star_pts(p[0], p[1], 34 - 5 * j, t * 9, 4, 0.32), S), fill=mix(SPARK, (255, 255, 255), 0.4))
        for (t0, x, y, size) in POOFS + [(DOVES[0], 0, 0, 0)]:
            v = t - t0
            if size == 0:
                continue
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

    # -------- lasso, cage, colombes
    def draw_lasso(self, dr, t, S, J, back):
        gL = J["gL"]
        bx, by = self.sc.bpos(t)
        a, b = LASSO_PULL
        if a <= t < b and not back:
            # la corde de foulards sort de la manche
            gR = J["gR"]
            n = 10
            for i in range(n):
                p = (lerp(gL[0], gR[0], i / n), lerp(gL[1], gR[1], i / n) + 8 * math.sin(i + t * 8))
                ell(dr, p[0], p[1], 14, 10, SILKS[i % len(SILKS)], S)
            return
        a, b = LASSO_THROW
        if a <= t < b and not back:
            k = smooth((t - a) / (b - a))
            cx, cy = lerp(gL[0], bx, k), lerp(gL[1], by - 60, k)
            rr = 50 + (R + 14 - 50) * k
            self.rope(dr, gL, (cx, cy), S)
            dr.ellipse([(cx - rr) * S, (cy - rr * 0.4) * S, (cx + rr) * S, (cy + rr * 0.4) * S],
                       outline=SILKS[1], width=max(2, int(12 * S)))
            return
        a, b = LASSO_ON
        if a <= t <= b + 0.5:
            slip = clamp01((t - b) / 0.5)
            ry = by + 10 + 80 * slip
            rr = R + 8 + 30 * slip
            if back:
                dr.arc([(bx - rr) * S, (ry - rr * 0.35) * S, (bx + rr) * S, (ry + rr * 0.35) * S], 180, 360,
                       fill=SILKS[1], width=max(2, int(12 * S)))
                return
            dr.arc([(bx - rr) * S, (ry - rr * 0.35) * S, (bx + rr) * S, (ry + rr * 0.35) * S], 0, 180,
                   fill=SILKS[1], width=max(2, int(12 * S)))
            if t <= b:
                self.rope(dr, gL, (bx + rr * 0.9, ry), S, taut=(28.35 <= t <= 29.98))

    def rope(self, dr, p0, p1, S, taut=False):
        n = 14
        pts = []
        for i in range(n + 1):
            u = i / n
            sag = 0.0 if taut else 60 * math.sin(math.pi * u)
            pts.append((lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u) + sag))
        for i in range(n):
            dr.line(poly([pts[i], pts[i + 1]], S), fill=SILKS[i % len(SILKS)], width=max(2, int(11 * S)))

    def draw_cage(self, dr, t, S, J):
        c = self.sc.cage(t, J)
        if c is None:
            return
        x, y = c
        w2, h = 160.0, 450.0
        top = y - h
        # plateau, barreaux, dôme, anneau
        rect(dr, x - w2 - 10, y - 14, x + w2 + 10, y + 8, GOLD, S, r=6)
        for k in range(9):
            xx = x - w2 + k * (2 * w2) / 8
            dr.line([xx * S, (top + 40) * S, xx * S, (y - 10) * S], fill=GOLD, width=max(1, int(7 * S)))
        dr.arc([(x - w2) * S, (top - 40) * S, (x + w2) * S, (top + 120) * S], 180, 360, fill=GOLD,
               width=max(1, int(9 * S)))
        rect(dr, x - w2, top + 38, x + w2, top + 46, GOLD, S)
        dr.ellipse([(x - 22) * S, (top - 84) * S, (x + 22) * S, (top - 40) * S], outline=GOLD, width=max(1, int(7 * S)))

    def draw_doves(self, dr, t, S, J):
        a, b, c, d = DOVES
        if not (a <= t <= d):
            return
        bx, by = self.sc.bpos(t)
        for side, g in ((-1, J["gL"]), (1, J["gR"])):
            grip = (bx + side * 70, by - R - 30)
            if t < b:
                k = smooth((t - a) / (b - a))
                p = (lerp(g[0], grip[0], k), lerp(g[1], grip[1], k) - 120 * math.sin(math.pi * k))
            elif t < c:
                p = grip
            else:
                k = (t - c) / (d - c)
                p = (grip[0] + side * 300 * k, grip[1] - 700 * k)
            flap = math.sin(t * 26 + side)
            dove(dr, p[0], p[1], side, flap, S)

    # -------- le public : une bande fine en bas
    def draw_audience(self, dr, t, S):
        rows = [(1205.0, 0.9, 0), (1300.0, 1.0, 1), (1410.0, 1.12, 2)]
        laugh = 0.0
        for (t0, a) in LAUGH:
            v = t - t0
            if 0 <= v <= 1.4:
                laugh = max(laugh, a * (1 - v / 1.4))
        up = any(a <= t <= b for (a, b) in ARMS_UP)
        for (y, sc_, ri) in rows:
            n = 7
            for k in range(n):
                x = 60 + k * 160 + (80 if ri == 1 else 0)
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

    # -------- bulles : la réplique en cours, près du magicien
    def draw_bubble(self, dr, t, S, J):
        for (a, b, text) in self.bubbles:
            if not (a <= t <= b):
                continue
            hx_, hy_, ang, flat, up = self.sc.hat(t, J)
            top = self.sc.hat_top(hx_, hy_, ang, flat)
            fs = 40
            f = font(fs * S)
            fr = font(fs)
            bw = fr.getlength(text) + 44
            bh = fs * 1.5
            Z, ox, oy = cam(t)
            xmin, xmax = ox + 24 / Z + bw / 2, ox + (W - 24) / Z - bw / 2
            bx, by = self.sc.bpos(t)
            if t < 8.2:
                cx, cy = 560.0, 455.0          # sous l'accroche, à gauche de sa tête
            else:
                cx = min(max(top[0] - 60, xmin), xmax)
                cy = min(top[1], hy_) - 70
                # jamais sur Bounce : au-dessus de lui, sinon de l'autre côté du magicien
                if abs(cx - bx) < bw / 2 + R + 10 and cy + bh / 2 > by - 1.35 * R:
                    cy = min(cy, by - 1.35 * R - bh / 2 - 10)
                if cy - bh / 2 < oy + 100 / Z:
                    cy = top[1] + 30
                    cx = top[0] + 60 + bw / 2 if bx < top[0] else top[0] - 60 - bw / 2
                    cx = min(max(cx, xmin), xmax)
            k = clamp01((t - a) / 0.12)
            sc_ = 0.75 + 0.25 * k
            x0, y0, x1, y1 = cx - bw / 2 * sc_, cy - bh / 2 * sc_, cx + bw / 2 * sc_, cy + bh / 2 * sc_
            tgt = (J["head"][0] - 20, J["head"][1] - 40) if t < INVIS else (top[0] - 30, top[1] + 20)
            bxm = max(x0 + 30, min(x1 - 30, tgt[0]))
            tail = [(bxm - 18, y1 - 4), (bxm + 18, y1 - 4), (lerp(bxm, tgt[0], 0.5), y1 + 34)]
            dr.polygon(poly(tail, S), fill=(250, 250, 252))
            dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=bh / 2 * S * sc_, fill=(250, 250, 252),
                                 outline=(30, 24, 40), width=max(1, int(4 * S)))
            dr.text((cx * S, cy * S), text, fill=(24, 20, 30), anchor="mm", font=font(fs * S * sc_))


def glove(dr, x, y, S, big=False):
    k = 1.3 if big else 1.0
    ell(dr, x, y, 34 * k, 34 * k, GLOVE, S)
    ell(dr, x + 5 * k, y + 8 * k, 18 * k, 14 * k, GLOVE_D, S)
    rect(dr, x - 25 * k, y + 18 * k, x + 25 * k, y + 38 * k, GLOVE, S, r=7)


def dove(dr, x, y, side, flap, S):
    """Une colombe sans visage : corps, tête, deux ailes qui battent."""
    ell(dr, x, y, 46, 26, (248, 248, 252), S)
    ell(dr, x + side * 40, y - 14, 18, 16, (248, 248, 252), S)
    dr.polygon(poly([(x + side * 56, y - 14), (x + side * 70, y - 10), (x + side * 56, y - 6)], S), fill=(240, 190, 90))
    dr.polygon(poly([(x - side * 40, y), (x - side * 70, y - 10), (x - side * 62, y + 12)], S), fill=(230, 230, 240))
    wy = 70 * flap
    dr.polygon(poly([(x - 20, y - 6), (x + 16, y - 6), (x - 10, y - 30 - wy)], S), fill=(236, 236, 246))


def draw_rabbit(dr, x, y, S, spring, spin, t):
    """Le lapin, sans visage : corps, tête, longues oreilles."""
    RS = 1.3
    ca, sa = math.cos(spin * 0.15), math.sin(spin * 0.15)

    def Q(u, v):
        return (x + (u * ca - v * sa) * RS, y + (u * sa + v * ca) * RS)
    for (u, v, rx, ry) in ((0, 30, 46, 50), (0, -36, 38, 36)):
        c = Q(u, v)
        ell(dr, c[0], c[1], rx * RS, ry * RS, RABBIT, S)
    for side in (-1, 1):
        a = side * (0.5 - 0.38 * smooth(spring)) + 0.06 * math.sin(t * 9) * spring
        base_ = (side * 16, -64)
        ear = []
        for (s, w) in [(0, -16), (0.4, -20), (0.85, -14), (1, 0), (0.85, 14), (0.4, 20), (0, 16)]:
            L = 120 * s
            ear.append(Q(base_[0] + math.sin(a) * L + math.cos(a) * w, base_[1] - math.cos(a) * L + math.sin(a) * w))
        dr.polygon(poly(ear, S), fill=RABBIT)
        inner = []
        for (s, w) in [(0.1, -7), (0.8, -7), (0.92, 0), (0.8, 7), (0.1, 7)]:
            L = 120 * s
            inner.append(Q(base_[0] + math.sin(a) * L + math.cos(a) * w, base_[1] - math.cos(a) * L + math.sin(a) * w))
        dr.polygon(poly(inner, S), fill=RABBIT_IN)
    for side in (-1, 1):
        c = Q(side * 40, 4)
        ell(dr, c[0], c[1], 16 * RS, 12 * RS, RABBIT_D, S)


def draw_top_hat(dr, x, y, ang, S, flat=0.0, ears=0.0, lid=0.0, t=0.0, front_only=False, ears_only=False):
    """Le haut-de-forme du magicien : (x, y) = centre du bord, ang = angle (0 = droit, pi = retourné).
    flat : aplati ; ears/lid : le couvercle se soulève et deux oreilles de lapin sortent du haut."""
    ca, sa = math.cos(ang), math.sin(ang)
    hk = 1.0 - 0.6 * flat
    wk = 1.0 + 0.35 * flat

    def P(u, v):
        u, v = u * 1.1 * hk, v * 1.3 * wk
        return (x + v * ca + u * sa, y + v * sa - u * ca)
    if front_only:
        crown = [P(0, -60), P(0, 60), P(80, 62), P(80, -62)]
        dr.polygon(poly(crown, S), fill=HATC)
        band = [P(8, -61), P(8, 61), P(34, 62), P(34, -62)]
        dr.polygon(poly(band, S), fill=HAT_BAND)
        return
    if ears > 0:
        for side in (-1, 1):
            base_ = P(140, side * 18)
            L = 175 * ears
            ae = ang + side * 0.25
            tip = (base_[0] + math.sin(ae) * L, base_[1] - math.cos(ae) * L)
            nx, ny = math.cos(ae) * 24, math.sin(ae) * 24
            dr.polygon(poly([(base_[0] - nx, base_[1] - ny), (base_[0] + nx, base_[1] + ny),
                             (tip[0] + nx * 0.6, tip[1] + ny * 0.6), tip, (tip[0] - nx * 0.6, tip[1] - ny * 0.6)], S),
                       fill=RABBIT)
            mid = ((base_[0] + tip[0]) / 2, (base_[1] + tip[1]) / 2)
            dr.polygon(poly([(base_[0] - nx * 0.4, base_[1] - ny * 0.4), (base_[0] + nx * 0.4, base_[1] + ny * 0.4),
                             (mid[0] + nx * 0.3, mid[1] + ny * 0.3), (tip[0], tip[1]), (mid[0] - nx * 0.3, mid[1] - ny * 0.3)], S),
                       fill=RABBIT_IN)
    if ears_only:
        return
    crown = [P(0, -60), P(0, 60), P(140, 64), P(140, -64)]
    dr.polygon(poly(crown, S), fill=HATC)
    band = [P(8, -61), P(8, 61), P(34, 62), P(34, -62)]
    dr.polygon(poly(band, S), fill=HAT_BAND)
    if lid > 0:
        l0, l1 = P(140 + 70 * lid, -70), P(140 + 30 * lid, 70)
        dr.line(poly([l0, l1], S), fill=HAT_RIM, width=max(1, int(14 * S)))
    else:
        top0, top1 = P(140, -64), P(140, 64)
        dr.line(poly([top0, top1], S), fill=HAT_RIM, width=max(1, int(6 * S)))
    e0, e1 = P(10, -52), P(128, -54)
    dr.line(poly([e0, e1], S), fill=HAT_RIM, width=max(1, int(4 * S)))
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
    "hook_text_s": 8.0, "hook_top": 0.125, "hook_font_size": 88, "hook_width": 0.72, "hook_speed": 1.1,
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
        bx, by = sim.sc.bpos(s_)
        Z, ox, oy = cam(s_)
        sx_, sy_ = (bx - ox) * Z, (by - oy) * Z
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
    sim.set_narr(narr)
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
