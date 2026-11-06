"""
Prototype « magic » v3 : Bounce au spectacle de magie.

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
              "Abracadabra!": "abra.wav", "Oh, come on.": "comeon_hi.wav", "Stay in there!": "stayin_hi.wav",
              "Ta-da!": "tada_hi.wav", "Take him away!": "takeaway_hi.wav", "Where are you?": "where.wav",
              "Come here...": "comehere.wav", "My rabbit!": "myrabbit.wav", "Ta-da!!": "tada.wav",
              "Now you see him...": "see.wav"}
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
SLOW = (99.0, 99.5, 1.0)         # v4 : pas de ralenti


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


# ------------------------------------------------------------------ v3 : géométrie resserrée (Bounce un peu plus petit)
R = 100.0
WOOD_Y = TABLE[2] - R
HAT_X = 210.0                     # le chapeau du tour, retourné sur la table (à gauche)
HAT_W, HAT_H = 220.0, 170.0
SILK_Y = TABLE[2] - 28 - R
PAD = (180.0, 300.0, 845.0)       # le foulard plié, au bout gauche de la table (après le paravent)
PAD_X = 240.0
PAD_Y = PAD[2] - R
TB_HAT = (560.0, TABLE[2])        # le haut-de-forme du magicien, posé sur la table après le sort
XA = 385.0                        # la place de Bounce sur la table (acte 1)
XB = 340.0                        # sa place quand le magicien est petit (acte 2)
CAGE_Y = TABLE[2] - 25 - R        # Bounce sur le coussin de la cage

# ------------------------------------------------------------------ le plan de Bounce (temps de scène)
C = []
TB_HAT = (545.0, TABLE[2])        # v4 : le haut-de-forme tombé sur la table, un peu plus à gauche
XC = 310.0                        # la place de Bounce à côté du foulard (acte 3)
TRAP = (455.0, TABLE[2] - 160.0)  # le chapeau retourné sur la table (le piège) : bord en haut
HOLD = (405.0, 600.0)             # le chapeau présenté au public


def hard(t, kind, x=None, y=None, gain=1.0):
    C.append({"t": t, "kind": kind, "x": x, "y": y, "soft": False, "gain": gain})


def soft(t, kind, x=None, y=None):
    C.append({"t": t, "kind": kind, "x": x, "y": y, "soft": True, "gain": 0.0})


def press(a, b, x, y=None, dt=0.34):
    t, k = a, 0
    while t < b - 0.05:
        soft(t, "press", x + (5 if k % 2 else -5), (WOOD_Y + 22) if y is None else y)
        t += dt
        k += 1


START = {"t": -0.80, "x": HAT_X, "y": SILK_Y}
# --- acte 1 : la présentation, le tour du chapeau (un tour, un échec)
hard(0.12, "wood", XA, gain=1.1)
soft(0.85, "palm", 430, 760)
soft(1.60, "silk")
hard(2.40, "wood", XA)
soft(3.15, "palm", 430, 760)
soft(3.70, "palm", 434, 760)
soft(4.25, "palm", 430, 760)
soft(4.97, "silk")                                  # piège 1 : enfoncé dans le chapeau du tour, la main dessus
hard(5.75, "silk", gain=0.35)                       # « Bounce » étouffé : le chapeau tressaute
soft(6.15, "silk")
hard(6.55, "silk", gain=0.45)
soft(6.97, "silk")
hard(7.40, "silk", gain=1.25)                       # il jaillit, le chapeau sur la tête
hard(8.30, "wood", XA, gain=1.1)                    # le chapeau du tour s'envole hors de la table
# --- « Now you see him… » : il rebondit sur la paume ; « Now you don't! » : paravent… il s'assoit dessus
soft(9.00, "palm", 430, 760)
soft(9.55, "palm", 432, 760)
soft(10.10, "palm", 430, 760)
soft(10.70, "wood", XA)                             # derrière le paravent
soft(11.30, "top", 395, 433)
soft(11.72, "top", 397, 436)
hard(12.15, "top", 398, 437, gain=1.0)              # assis sur le paravent : « Bounce »
hard(12.95, "wood", XA, gain=1.1)
press(13.85, 15.50, XA)                             # « Stay. »
hard(15.50, "wood", XA, gain=0.95)
soft(15.95, "press", XA, WOOD_Y + 16)
hard(16.45, "wood", XA + 3, gain=1.05)
soft(16.88, "press", XA, WOOD_Y + 16)
hard(17.35, "wood", XA, gain=1.15)
soft(17.78, "press", XA, WOOD_Y + 18)
hard(18.25, "wood", XA, gain=1.35)                  # il éjecte le magicien
hard(19.15, "wood", XA)
soft(19.85, "pad")
soft(20.45, "pad")
soft(21.00, "pad")
hard(21.60, "wood", XA, gain=1.3)                   # le sort le touche… et ricoche sur le magicien
hard(22.55, "wood", XB + 20)
hard(23.50, "wood", XB)
soft(24.30, "pad")
soft(24.90, "pad")
hard(25.50, "wood", XB, gain=1.05)
for _t in (26.35, 26.80, 27.25, 27.70, 28.15, 28.60, 29.05, 29.50):   # en cage, sur le coussin : muet
    soft(_t, "cage", XB + (4 if int(_t * 10) % 2 else -4), CAGE_Y)
hard(29.95, "cage", XB, CAGE_Y, gain=1.35)          # un seul « Bounce » : la cage s'envole sur le magicien
hard(30.85, "wood", XB)
hard(31.85, "wood", XB + 10)
hard(32.70, "wood", XB)
soft(33.45, "pad")
soft(34.05, "pad")
soft(34.65, "pad")
soft(35.15, "carry", PAD_X, 640)                    # les colombes l'emportent… jusqu'au plafond
hard(36.40, "ceil", 600, 318, gain=1.15)            # « Bounce » contre le plafond : les colombes s'éparpillent
hard(37.15, "head", 640, 492, gain=1.3)             # il retombe sur la tête du petit magicien : il regrandit
soft(38.05, "pad")
hard(38.60, "wood", XC, gain=0.95)
soft(39.25, "pad")
soft(39.85, "pad")
soft(40.45, "pad")
press(40.75, 41.50, PAD_X, PAD_Y + 14)              # le lapin se cache derrière lui
hard(42.00, "wood", XC, gain=1.0)
press(42.35, 43.20, XC)                             # caché derrière lui, encore
hard(43.75, "wood", XC, gain=0.9)
press(44.10, 45.55, XC)
hard(46.60, "inhat", gain=0.55)                     # il saute tout seul dans le chapeau-piège… sur le lapin
hard(47.70, "inhat", gain=0.45)                     # étouffés, de plus en plus espacés
hard(49.30, "inhat", gain=0.35)
hard(51.20, "inhat", gain=0.28)
hard(57.20, "inhat", gain=0.3)                      # présenté au public : le chapeau tressaute
hard(58.60, "inhat", gain=0.45)
hard(59.90, "inhat", gain=0.8)                      # le dernier : le chapeau lui saute des mains
END_SCENE = 61.30
C.sort(key=lambda c: c["t"])
for c in C:
    if c["kind"] == "wood":
        c["y"] = WOOD_Y
    elif c["kind"] == "silk":
        c["x"], c["y"] = HAT_X, SILK_Y
    elif c["kind"] == "pad":
        c["x"], c["y"] = PAD_X, PAD_Y + 6

PROP_RIDE = (7.40, 8.30)          # le chapeau du tour sur la tête de Bounce
PROP_FLY = (8.30, 8.90)
PROP_GONE = 8.90
ZAP = 21.80                       # le sort revient sur le magicien : il rétrécit
RESTORE = 37.15                   # Bounce lui tombe sur la tête : il regrandit
SHRINK = KF(1.0, [(ZAP, 1.0), (ZAP + 0.3, 0.55), (RESTORE, 0.55), (RESTORE + 0.3, 1.0)])
INHAT = (46.60, 99.0)
CARRY = (35.15, 36.40)
CEIL = (36.40, 36.78, 37.15)
HAT_FLIP = (43.75, 44.40)         # il retourne son chapeau sur la table : un piège à lapin
GRAB = (53.55, 54.35)             # il saisit le chapeau et le lève
FLY_HAT = 59.90                   # le chapeau lui saute des mains
ISSUE_S = 59.9
SCREEN = (10.15, 12.75)

# lignes (temps réel de déclenchement) ; petit, sa voix est aiguë ; regrandi, elle redevient grave
LINES = [(3.30, "That's not a rabbit.", "notrabbit"), (9.25, "Now you see him...", "see"),
         (10.85, "Now you don't!", "dont"), (14.30, "Stay.", "stay"), (20.25, "Abracadabra!", "abra"),
         (24.45, "Oh, come on.", "comeon"), (26.40, "Stay in there!", "stayin"), (27.60, "Ta-da!", "tada_hi"),
         (33.65, "Take him away!", "takeaway"), (39.55, "Where are you?", "where"), (44.75, "Come here...", "comehere"),
         (52.60, "My rabbit!", "myrabbit"), (55.20, "Ta-da!!", "tada")]
SILENT_BUBBLES = [(23.05, 24.05, "?!"), (40.85, 41.50, "Hmm?"), (42.75, 43.35, "Huh?")]


class Plan:
    def __init__(self):
        self.cs = C
        self.refresh()
        self.start = START
        self.after = {"t": END_SCENE + 0.6, "x": 480.0, "y": 480.0}

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
            return (XA, WOOD_Y)
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


PRESS_SPANS = [(13.85, 15.50), (15.90, 16.45), (16.83, 17.35), (17.73, 18.25)]

# ------------------------------------------------------------------ le magicien
MX = KF(560.0, [(12.95, 560.0), (19.45, 560.0), (22.50, 560.0), (22.95, 655.0), (RESTORE, 655.0),
                (RESTORE + 0.3, 650.0)])
GROUND = KF(FLOOR, [(22.50, FLOOR), (22.95, TABLE[2]), (RESTORE, TABLE[2]), (RESTORE + 0.3, FLOOR)])
LEAN = KF(0.0, [(0.0, -6.0), (0.3, 4.0), (1.0, -10.0), (1.7, -14.0), (2.3, -14.0), (2.5, 6.0), (3.2, 0.0),
                (3.4, -6.0), (3.8, 4.0), (4.2, -6.0), (4.6, 0.0), (4.9, -26.0), (7.35, -26.0), (7.5, 18.0),
                (8.2, 0.0), (9.2, -8.0), (9.8, 4.0), (10.3, 0.0), (11.0, 0.0), (12.2, 0.0), (12.4, 6.0), (12.9, 0.0),
                (19.45, 0.0), (19.6, 22.0), (19.9, 22.0), (20.2, 0.0), (20.6, -8.0), (21.0, 4.0), (21.45, -6.0),
                (21.6, 0.0), (21.8, 10.0), (23.0, 0.0), (23.3, -8.0), (23.7, 8.0), (24.1, 0.0),
                (24.45, 8.0), (24.9, -4.0), (25.4, 0.0), (26.2, 6.0), (26.8, -12.0), (27.3, 0.0),
                (27.6, 0.0), (27.8, 35.0), (29.4, 35.0), (29.95, 0.0), (30.1, 14.0), (30.7, -10.0),
                (31.1, 10.0), (31.5, -10.0), (31.9, 0.0), (33.6, 0.0), (33.8, 10.0), (34.3, 0.0),
                (35.2, -6.0), (36.3, -10.0), (37.15, 0.0), (37.45, -12.0), (37.75, 10.0), (38.1, -6.0), (38.5, 0.0),
                (39.5, 0.0), (39.7, 8.0), (40.4, 0.0), (40.6, -10.0), (41.5, -10.0), (41.65, 6.0), (42.3, 0.0),
                (42.5, -12.0), (43.35, -12.0), (43.7, -16.0), (44.4, -4.0), (44.75, 6.0), (45.5, 12.0),
                (46.6, 12.0), (46.75, 16.0), (47.0, 12.0), (51.9, 12.0), (52.05, 6.0), (52.6, 10.0), (53.5, 6.0),
                (54.4, 0.0), (55.2, 4.0), (55.8, 0.0), (56.4, 8.0), (59.9, 8.0), (60.1, -10.0), (60.5, 4.0),
                (61.0, 0.0)])
BOW = KF(0.0, [(56.0, 0.0), (56.6, 48.0), (59.9, 48.0), (60.2, 30.0)])
FACE = KF(-1.0, [(39.40, -1.0), (39.55, 1.0), (40.45, 1.0), (40.60, -1.0), (41.50, -1.0), (41.65, 1.0),
                 (42.35, 1.0), (42.50, -1.0), (44.60, -1.0), (44.75, 1.0), (51.90, 1.0), (52.05, -1.0),
                 (55.0, -1.0), (55.2, 1.0)])
ANGER_K = KF(0.0, [(7.4, 0.0), (7.6, 1.0), (8.4, 1.0), (8.8, 0.0), (12.4, 0.0), (12.6, 1.0), (13.3, 1.0),
                   (13.6, 0.0), (20.2, 0.0), (20.5, 1.0), (21.6, 1.0), (21.75, 0.0)])
MAG_HOPS = [(12.55, 22), (12.85, 24), (22.50, 140), (RESTORE + 0.3, 70), (52.05, 30)]
TIPTOE = KF(0.0, [(9.6, 0.0), (9.75, 0.0), (12.05, 0.0), (12.25, 0.0), (45.6, 0.0), (45.8, 14.0), (46.4, 14.0),
                  (46.6, 0.0)])
SIT = [(13.45, 18.25)]
SIT_HOPS = [(15.50, 70), (16.45, 140), (17.35, 220)]
FLIGHTS = [(18.25, 19.45, (XA + 6, 670.0), (560.0, 1010.0))]
FLOOR_SIT = (19.45, 19.90)
ONHAT = (99.0, 99.1)
TWITCH = [(5.75, 0.5), (8.3, 1.0), (16.45, 0.6), (18.3, 1.0), (21.62, 1.0)]
# le lapin se montre : (début, fin, où, niveau) — une fois en clair avant 10 s, puis ailleurs, plus discret
PEEKS = [(3.00, 3.60, "prop", 1.0), (13.90, 14.50, "aud", 0.55), (19.75, 20.35, "tableR", 0.6),
         (29.20, 29.80, "table", 0.5)]
HAT_FALL = (21.90, 22.35)
HAT_FLAT = KF(0.0, [])
# le lapin dehors, sur la table (acte 3) : (t, x) — il se cache derrière Bounce quand le magicien se retourne
RAB_SIT_Y = TABLE[2] - 104 * 1.15
RAB_PATH = [(39.60, TB_HAT[0], TB_HAT[1] - 260), (40.00, 460.0, RAB_SIT_Y), (40.55, 460.0, RAB_SIT_Y),
            (40.80, 252.0, RAB_SIT_Y), (41.65, 252.0, RAB_SIT_Y), (41.95, 460.0, RAB_SIT_Y),
            (42.48, 460.0, RAB_SIT_Y), (42.70, 322.0, RAB_SIT_Y), (44.95, 322.0, RAB_SIT_Y),
            (45.40, TRAP[0], TRAP[1] + 70)]
RAB_FREE = (39.60, 45.40)
EARS_IN = 45.35                   # dès lors, ses oreilles dépassent du chapeau-piège

REST = (("rel", -20, 175), ("rel", 20, 175))
GLOVES = [
    (-9.0, 0.1, ("rel", -120, -175), ("rel", 50, -190)),             # ta-da
    (0.25, 0.25, ("rel", -110, -40), ("rel", 50, -60)),
    (0.5, 0.3, ("abs", 430, 878), ("rel", 50, -60)),                  # paume tendue
    (0.95, 0.35, ("abs", 330, 760), ("rel", 50, -40)),                # il le lance dans le chapeau
    (1.45, 0.3, ("abs", 320, 690), ("rel", 40, 20)),
    (2.45, 0.2, ("rel", -60, -80), ("rel", 50, -80)),
    (2.85, 0.3, ("abs", 430, 878), ("rel", 50, -150)),                # il le présente
    (3.35, 0.2, ("abs", 430, 878), ("rel", 70, -100)),                # « That's not a rabbit. »
    (3.75, 0.2, ("abs", 430, 878), ("rel", 50, -160)),
    (4.15, 0.2, ("abs", 430, 878), ("rel", 70, -100)),
    (4.30, 0.3, ("abs", 330, 760), ("rel", 50, -60)),                 # il le fourre dans le chapeau
    (4.95, 0.12, ("abs", HAT_X, 682), ("rel", 20, 40)),               # la main sur le chapeau
    (5.75, 0.06, ("abs", HAT_X, 664), ("rel", 20, 40)),
    (5.85, 0.1, ("abs", HAT_X, 682), ("rel", 20, 40)),
    (6.55, 0.06, ("abs", HAT_X, 646), ("rel", 20, 40)),
    (6.65, 0.1, ("abs", HAT_X, 682), ("rel", -40, -60)),              # deux mains
    (7.42, 0.12, ("rel", -90, -230), ("rel", 60, -180)),              # éjecté
    (8.0, 0.3, ("rel", -120, -40), ("rel", 60, -60)),
    (8.6, 0.3, ("abs", 430, 878), ("rel", 60, -150)),                 # « Now you see him… » : la paume
    (10.15, 0.25, ("abs", 285, 640), ("abs", 505, 640)),              # le paravent
    (10.5, 0.2, ("abs", 285, 600), ("abs", 505, 600)),
    (11.0, 0.25, ("abs", 285, 560), ("abs", 505, 560)),
    (11.6, 0.25, ("abs", 285, 520), ("abs", 505, 520)),
    (12.2, 0.25, ("abs", 270, 860), ("abs", 330, 860)),               # il le tire d'un coup
    (12.5, 0.15, ("rel", -60, 60), ("rel", 60, 60)),                  # poings serrés
    (13.35, 0.2, ("rel", -90, -60), ("rel", 90, -60)),                # il saute
    (13.85, 0.3, ("hip", -70, 20), ("hip", 70, 20)),
    (14.3, 0.15, ("ball", -40, -55), ("hip", 70, 20)),                # « Stay. » : il lui tapote la tête
    (14.6, 0.15, ("ball", -40, -30), ("hip", 70, 20)),
    (14.9, 0.2, ("hip", -70, 20), ("hip", 70, 20)),
    (17.30, 0.15, ("hat", -60, 0), ("hat", 60, 0)),                   # il tient son chapeau
    (18.2, 0.1, ("hat", -60, 0), ("hat", 60, 0)),
    (19.45, 0.2, ("rel", -110, 40), ("rel", 110, 40)),
    (19.9, 0.25, ("rel", -10, 120), ("rel", -40, 110)),               # la baguette sort de la manche
    (20.3, 0.3, ("rel", -110, -160), ("rel", 80, -120)),              # « Abracadabra! »
    (20.8, 0.2, ("rel", -130, -140), ("rel", 110, -150)),
    (21.2, 0.2, ("rel", -110, -160), ("rel", 80, -120)),
    (21.82, 0.1, ("rel", -120, -180), ("rel", 120, -180)),            # touché
    (23.05, 0.3, ("rel", -50, -60), ("rel", 50, -60)),                # (petit) il regarde ses mains
    (23.5, 0.2, ("rel", -40, -90), ("rel", 40, -90)),
    (24.45, 0.25, ("rel", -130, 30), ("rel", 130, 30)),               # « Oh, come on. »
    (25.2, 0.3, ("rel", -40, 120), ("rel", 40, 120)),
    (26.2, 0.25, ("rel", -60, -230), ("rel", 60, -60)),               # « Stay in there! » : le doigt en l'air
    (26.8, 0.15, ("rel", -190, -20), ("rel", 60, -60)),               # il pointe : la cage tombe
    (27.3, 0.2, ("rel", -50, 70), ("rel", 50, 70)),
    (27.6, 0.25, ("rel", -160, -120), ("rel", 160, -120)),            # « Ta-da! » : il salue
    (29.2, 0.3, ("rel", -50, 70), ("rel", 50, 70)),
    (29.97, 0.12, ("rel", -150, -180), ("rel", 150, -180)),           # la cage lui tombe dessus
    (30.6, 0.2, ("rel", -100, -60), ("rel", 100, -60)),               # mains aux barreaux
    (32.0, 0.3, ("rel", -70, -260), ("rel", 70, -260)),               # il soulève la cage
    (32.5, 0.2, ("rel", 80, -230), ("rel", 150, -170)),               # et la jette
    (33.5, 0.25, ("rel", -150, -160), ("rel", 150, -160)),            # « Take him away! »
    (34.25, 0.15, ("rel", -190, -60), ("rel", 190, -60)),             # il lâche les colombes
    (35.0, 0.4, ("rel", -90, -230), ("rel", 90, -230)),               # il les suit des yeux, bras levés
    (RESTORE, 0.1, ("rel", -170, -160), ("rel", 170, -160)),          # poum : il regrandit
    (37.55, 0.3, ("rel", -70, 60), ("rel", 70, 60)),                  # il regarde ses mains : grand !
    (38.1, 0.3, ("rel", -90, -40), ("rel", 90, -40)),
    (38.7, 0.3, ("rel", -20, 175), ("rel", 20, 175)),
    (39.35, 0.2, ("rel", -40, -70), ("rel", 40, -70)),                # « Where are you? » : mains en porte-voix
    (40.6, 0.2, ("rel", -150, -40), ("rel", 40, 60)),                 # il se retourne, il cherche
    (41.65, 0.2, ("rel", -40, -70), ("rel", 40, -70)),
    (42.5, 0.2, ("rel", -120, -100), ("rel", 40, 60)),                # la main en visière
    (43.40, 0.3, ("abs", 468, 812), ("abs", 622, 812)),               # il prend son chapeau
    (43.75, 0.1, ("hold", -88, 0), ("hold", 88, 0)),                  # et le retourne sur la table
    (44.45, 0.25, ("rel", -20, 175), ("rel", 20, 175)),
    (44.75, 0.2, ("rel", -110, -20), ("rel", 110, -20)),              # « Come here... »
    (45.15, 0.15, ("rel", -110, -60), ("rel", 110, -60)),
    (45.6, 0.3, ("rel", -30, 70), ("rel", 30, 70)),                   # il attend, bras croisés
    (52.05, 0.15, ("rel", -120, -130), ("rel", 120, -130)),           # il se retourne : les oreilles !
    (52.6, 0.2, ("rel", -170, -40), ("rel", 60, 40)),                 # « My rabbit! »
    (53.30, 0.25, ("hold", -92, 0), ("hold", 92, 0)),               # il saisit le chapeau
    (FLY_HAT, 0.12, ("rel", -160, -150), ("rel", 60, -190)),          # le chapeau lui saute des mains
]
GLOVES.sort(key=lambda g: g[0])
CAGE_DROP = (26.80, 27.15)
CAGE_LOCK = 27.40
CAGE_FLY = (29.95, 30.55)
CAGE_LIFT = (32.00, 32.40)
CAGE_TOSS = (32.50, 33.05)
DOVES = (34.25, 35.15, 36.40, 37.40)
CHARGE = [(20.3, 21.45)]
BOLT_OUT = (21.45, 21.60)
BOLT_BACK = (21.60, 21.80)
POOFS = [(ZAP, 560.0, 760.0, 1.2), (RESTORE, 650.0, 640.0, 1.1)]
HOOK_AGAIN = (40.70, 41.75)       # l'accroche revient en grand, une seconde
LAUGH = [(0.2, 0.6), (2.5, 0.8), (5.8, 0.6), (7.45, 1.0), (8.4, 0.8), (12.2, 1.0), (14.4, 0.7), (16.5, 0.6),
         (17.4, 0.8), (18.3, 1.0), (21.9, 1.0), (24.5, 0.7), (30.0, 1.0), (30.7, 0.9), (36.4, 0.8), (37.2, 1.0),
         (40.7, 0.6), (42.6, 0.6), (46.6, 0.8), (49.3, 0.5), (52.1, 0.9), (57.2, 0.6), (58.6, 0.8), (59.9, 1.0)]
ARMS_UP = [(27.7, 29.0), (55.3, 59.7)]
EXPR = [(5.0, 7.4, "lose"), (7.4, 8.3, "win"), (12.15, 12.6, "shock"), (13.75, 18.25, "lose"), (18.3, 19.2, "win"),
        (21.6, 22.1, "shock"), (22.1, 24.4, "win"), (26.8, 29.93, "lose"), (29.95, 30.5, "shock"),
        (30.6, 31.7, "win"), (35.15, 36.4, "lose"), (36.4, 37.1, "shock"), (37.15, 38.0, "win"),
        (40.75, 41.5, "lose"), (42.35, 43.2, "lose"), (46.6, 47.0, "shock"), (47.0, 59.9, "lose"),
        (59.9, 99.0, "win")]


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
        for c in self.P.cs:
            if c["kind"] == "inhat":
                J = self.rig(c["t"])
                c["x"], c["y"] = self.inhat_pos(c["t"], J)
        self.P.refresh()
        self.rings = [(t, g, x, y, k) for (t, g, x, y, k) in self.P.hits if g >= 0.6]

    # ---- Bounce
    def bpos(self, t):
        a, b = CARRY
        if a <= t <= b:
            u = (t - a) / (b - a)
            u = u * u * (1.6 - 0.6 * u)
            x, y = qbez((PAD_X, 640.0), (330.0, 360.0), (600.0, 318.0), u)
            w = 1 - u * u
            return x + 8 * math.sin(t * 13) * w, y + 14 * math.sin(t * 9) * w
        if CEIL[0] <= t <= CEIL[2]:
            a, m, b = CEIL                  # collé au plafond, sonné… puis il tombe
            u = clamp01((t - m) / (b - m))
            return lerp(600.0, 640.0, u), 318.0 + 2 * math.sin(t * 30) * (1 - u) + 174.0 * u * u
        if t >= INHAT[0]:
            J = self.rig(t)
            return self.inhat_pos(t, J)
        return self.P.pos(t)

    def inhat_pos(self, t, J):
        hx, hy, ang = self.hat(t, J)[:3]
        tilt = ang - math.pi
        jig = 0.0
        if t > INHAT[0] + 0.3:
            jig = 6 * math.sin(t * 17)
        d = 42 + jig
        return hx + 4 * math.sin(t * 11) + d * math.sin(tilt), hy - d * math.cos(tilt)

    def ball(self, t):
        x, y = self.bpos(t)
        sx, sy = self.P.squash(t)
        if CARRY[0] <= t <= CARRY[1] - 0.08:
            k = math.sin(t * 11)
            sx, sy = 1 + 0.06 * k, 1 - 0.06 * k
        if t > INHAT[0] + 0.2:
            k = math.sin(t * 17)
            sx, sy = 1 + 0.04 * k, 1 - 0.04 * k
        y += R * (1 - sy) * 0.9
        return x, y, R * sx, R * sy

    # ---- le magicien (échelle s : il rétrécit après le sort)
    def hip(self, t):
        s = SHRINK(t)
        ground = GROUND(t)
        x, y = MX(t), ground - (FLOOR - STAND_HIP) * s - hop(t, MAG_HOPS) - TIPTOE(t) + BOW(t)
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
        if a <= t <= b + 0.3:
            k = clamp01((b + 0.3 - t) / 0.3) if t > b else 1.0
            return x, lerp(STAND_HIP, 1010.0, smooth(k))
        a, b = ONHAT
        if a <= t <= b:
            return TB_HAT[0], TB_HAT[1] - 154 * 1.1 * (1 - 0.6 * HAT_FLAT(t)) - 4
        return x, y

    def mode(self, t):
        for (a, b) in SIT:
            if a + 0.3 <= t <= b:
                return "sit"
        for (a, b, p0, p1) in FLIGHTS:
            if a <= t <= b:
                return "fly"
        if ONHAT[0] <= t <= ONHAT[1]:
            return "sit"
        a, b = FLOOR_SIT
        if a <= t <= b + 0.2:
            return "floor"
        return "stand"

    def rig(self, t):
        s = SHRINK(t)
        hx, hy = self.hip(t)
        anger = ANGER_K(t)
        if anger > 0.05:
            hx += (2 + 7 * anger) * math.sin(t * 70.0) * s
        lean = LEAN(t)
        mode = self.mode(t)
        if mode == "fly":
            lean += 25 * math.sin(t * 9.0)
        a = math.radians(lean)
        u = (math.sin(a), -math.cos(a))
        r = (math.cos(a), math.sin(a))

        def P(du, dr):
            return (hx + (u[0] * du + r[0] * dr) * s, hy + (u[1] * du + r[1] * dr) * s)
        infl = 1.0 + 0.22 * anger
        J = {"hip": (hx, hy), "u": u, "r": r, "lean": lean, "infl": infl, "anger": anger, "mode": mode, "P": P, "s": s}
        J["sh"] = P(190, 0)
        J["shL"], J["shR"] = P(190, -64 * infl), P(190, 64 * infl)
        J["head"] = P(250, 0)
        J["tie"] = P(186, 0)
        ground = GROUND(t)
        if mode in ("sit", "fly"):
            dang = 0.0 if mode == "sit" else 30 * math.sin(t * 12.0)
            J["kL"], J["kR"] = (hx - 118 * s, hy - 20 * s), (hx + 118 * s, hy - 20 * s)
            J["fL"] = (hx - 150 * s, hy + (118 - dang) * s)
            J["fR"] = (hx + 150 * s, hy + (118 + dang) * s)
        elif mode == "floor":
            J["fL"] = (hx - 150, FLOOR - 40)
            J["fR"] = (hx - 110, FLOOR - 70)
        else:
            lift = ground - (FLOOR - STAND_HIP) * s - hy
            J["fL"] = (hx - 28 * s, ground - 10 * s - max(0.0, lift))
            J["fR"] = (hx + 28 * s, ground - 10 * s - max(0.0, lift))
        J["gL"], J["gR"] = self.gloves(t, J)
        return J

    def spec_pos(self, spec, side, t, J):
        kind = spec[0]
        s = J["s"]
        if kind == "rel":
            sh = J["shL"] if side == "L" else J["shR"]
            return (sh[0] + spec[1] * s, sh[1] + spec[2] * s)
        if kind == "abs":
            return (spec[1], spec[2])
        if kind == "ball":
            bx, by = self.P.pos(t)
            return (bx + spec[1], by + spec[2])
        if kind == "hip":
            return (J["hip"][0] + spec[1] * s, J["hip"][1] + spec[2] * s)
        if kind == "hat":
            hx, hy, ang = self.hat_base(t, J)
            return (hx + spec[1] * s, hy - 60 * s + spec[2] * s)
        if kind == "hold":                 # sur les flancs du chapeau (posé ou tenu)
            hx, hy, ang = self.hat_free(t)[:3]
            mx, my = hx + 77 * math.sin(ang), hy - 77 * math.cos(ang)
            return (mx + spec[1], my + spec[2])
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
                out[0] = (out[0][0], out[0][1] + d)
        return out[0], out[1]

    def hat_base(self, t, J):
        u = J["u"]
        s = J["s"]
        hx, hy = J["head"][0] + u[0] * 44 * s, J["head"][1] + u[1] * 44 * s
        return hx, hy, math.radians(J["lean"])

    def hat_top(self, hx, hy, ang, flat=0.0):
        h = 154 * (1 - 0.6 * flat)
        return hx + math.sin(ang) * h, hy - math.cos(ang) * h

    def net_pos(self, J):
        gL, gR = J["gL"], J["gR"]
        return (gL[0] + gR[0]) / 2, min(gL[1], gR[1]) - 24

    def hat(self, t, J):
        """(x, y, angle, aplati, ouverture vers le haut ?) du haut-de-forme du magicien."""
        if t < HAT_FALL[0]:
            hx, hy, ang = self.hat_base(t, J)
            for (t0, amp) in TWITCH:
                v = t - t0
                if 0 <= v <= 0.35:
                    hy -= amp * 16 * math.sin(math.pi * v / 0.35)
                    ang += amp * 0.1 * math.sin(2 * math.pi * v / 0.35)
            return hx, hy, ang, 0.0, False
        a, b = HAT_FALL
        if t < b:
            J0 = self.rig(a - 1e-3)
            hx, hy, ang = self.hat_base(a - 1e-3, J0)
            p = arc((hx, hy), TB_HAT, a, b - a, t)
            return p[0], p[1], ang * (1 - (t - a) / (b - a)) + 2 * math.pi * smooth((t - a) / (b - a)), 0.0, False
        x, y, ang = self.hat_free(t)
        return x, y, ang, 0.0, ang > math.pi / 2

    def hat_free(self, t):
        """Le chapeau une fois tombé : sur la table, retourné en piège, tenu, puis envolé (x, y, angle)."""
        if t < HAT_FLIP[0]:
            return TB_HAT[0], TB_HAT[1], 0.0
        a, b = HAT_FLIP
        if t < b:
            k = smooth((t - a) / (b - a))
            return lerp(TB_HAT[0], TRAP[0], k), lerp(TB_HAT[1] - 80, TRAP[1], k) - 150 * math.sin(math.pi * k), math.pi * k
        jump = 0.0
        for (th, g, _x, _y, kind) in self.P.hits:
            v = t - th
            if kind == "inhat" and 0 <= v <= 0.32:
                jump += (18 + 70 * g) * math.sin(math.pi * v / 0.32)
        if t < GRAB[0]:
            return TRAP[0], TRAP[1] - jump, math.pi
        a, b = GRAB
        if t < b:
            k = smooth((t - a) / (b - a))
            return lerp(TRAP[0], HOLD[0], k), lerp(TRAP[1], HOLD[1], k) - 60 * math.sin(math.pi * k) - jump, math.pi
        if t < FLY_HAT:
            lift = 50 * clamp01((t - 55.1) / 0.25) * (1 - clamp01((t - 55.9) / 0.4))
            bow = BOW(t) * 0.6
            wob = 0.0
            for (th, g, _x, _y, kind) in self.P.hits:
                v = t - th
                if kind == "inhat" and th > 56 and 0 <= v <= 0.5:
                    wob += g * 0.35 * math.sin(v * 30) * (1 - v / 0.5)
            return HOLD[0], HOLD[1] - lift + bow - jump, math.pi + wob
        y0 = HOLD[1] + BOW(FLY_HAT) * 0.6
        u = clamp01((t - FLY_HAT) / 1.6)
        x, y = qbez((HOLD[0], y0), (430.0, -40.0), (340.0, 820.0), u)
        return x, y, math.pi - 2.4 * u

    def peek(self, t):
        """Le lapin qui se montre : (où, niveau 0..2) ou None."""
        for (a, b, where, lvl) in PEEKS:
            if a <= t <= b:
                env = clamp01((t - a) / 0.15) * clamp01((b - t) / 0.12)
                return where, lvl * env, (t - a)
        return None

    # ---- la baguette
    def wand(self, t, J):
        if t < 4.30:
            g = J["gR"]
            return g[0], g[1], math.radians(205)
        if t < 19.9:
            return None
        if t < 21.8:
            g = J["gL"]
            bx, by = self.bpos(t)
            ang = math.atan2(by - g[1], bx - g[0])
            k = smooth((t - 19.9) / 0.4)
            return g[0], g[1], lerp(math.radians(-90), ang, k)
        if t < 22.6:
            x, y = arc((560.0, 520.0), (620.0, 1150.0), 21.8, 0.8, t)
            return x, y, 9 * (t - 21.8)
        return None

    def wand_tip(self, w):
        x, y, a = w[:3]
        return x + 150 * math.cos(a), y + 150 * math.sin(a)

    # ---- la cage : centre bas (x, y) ou None
    def cage(self, t, J):
        if t < CAGE_DROP[0] or t > CAGE_TOSS[1]:
            return None
        base_ = (XB, TABLE[2])
        if t < CAGE_DROP[1]:
            k = (t - CAGE_DROP[0]) / (CAGE_DROP[1] - CAGE_DROP[0])
            return base_[0], base_[1] - 900 * (1 - k * k)
        if t < CAGE_FLY[0]:
            return base_
        mag = (J["hip"][0], GROUND(t))
        if t < CAGE_FLY[1]:
            return arc(base_, (655.0, TABLE[2]), CAGE_FLY[0], CAGE_FLY[1] - CAGE_FLY[0], t)
        if t < CAGE_LIFT[0]:
            return mag
        if t < CAGE_LIFT[1]:
            k = smooth((t - CAGE_LIFT[0]) / (CAGE_LIFT[1] - CAGE_LIFT[0]))
            return mag[0], mag[1] - 260 * k
        return arc((mag[0], mag[1] - 260), (1200.0, 100.0), CAGE_TOSS[0], CAGE_TOSS[1] - CAGE_TOSS[0], t)

    def cage_angle(self, t):
        a, b = CAGE_FLY
        if a <= t <= b:
            return 2 * math.pi * smooth((t - a) / (b - a))
        return 0.0

    # ---- le lapin dehors (acte 3) : (x, y, ressort) ou None
    def rabbit_free(self, t):
        a, b = RAB_FREE
        if not (a <= t <= b):
            return None
        pts = RAB_PATH
        for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                if abs(x1 - x0) < 1 and abs(y1 - y0) < 1:
                    return x0, y0 - 4 * abs(math.sin(t * 6)), 1.0
                hgt = 110 + 0.25 * abs(x1 - x0)
                return lerp(x0, x1, k), lerp(y0, y1, k) - hgt * math.sin(math.pi * k), clamp01(k * 3)
        return None


# ------------------------------------------------------------------ cadrage : serré, public réduit à une frange
CAM_Z = KF(1.45, [])
CAM_OX = KF(85.0, [(35.3, 85.0), (36.3, 125.0), (38.0, 125.0), (39.0, 85.0)])
CAM_OY = KF(-49.0, [])


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
        self.bubbles = [(a, b, txt) for (a, b, txt) in SILENT_BUBBLES]

    def set_narr(self, narr):
        self.bubbles = [(scene_of(n["start"]), scene_of(max(n["end"] + 0.35, n["start"] + 0.5 + 0.3 * len(n["text"].split()))),
                         n["text"]) for n in narr] + [(a, b, txt) for (a, b, txt) in SILENT_BUBBLES]

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
        treal = float(t)
        t = scene_of(treal)
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
        self.draw_peek_at(dr, t, S, "tableR")
        front = J["mode"] in ("sit", "fly")
        behind = GROUND(t) > TABLE[2] + 1
        if not front and behind:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_table(dr, t, S)
        self.draw_prop_hat(dr, t, S, back=True)
        pk = sc.peek(t)
        if pk is not None and pk[0] == "prop":
            draw_peek(dr, (HAT_X, TABLE[2] - HAT_H + 8), 0.0, pk[1], pk[2], S)
        self.draw_pad(dr, t, S)
        if not front and not behind:
            self.draw_magician(dr, t, S, J, part="body")
        if front:
            self.draw_magician(dr, t, S, J, part="body")
        self.draw_rings(dr, t, S)
        bx, by, brx, bry = sc.ball(t)
        in_prop = abs(bx - HAT_X) < 140 and by > 600 and t < PROP_RIDE[0]
        if in_prop:
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
        if not in_prop:
            self.draw_bounce(dr, t, S, bx, by, brx, bry)
        self.draw_prop_ride(dr, t, S)
        self.draw_inhat_front(dr, t, S, J)
        self.draw_cage(dr, t, S, J)
        self.draw_doves(dr, t, S, J)
        self.draw_screen(dr, t, S, J)
        self.draw_magician(dr, t, S, J, part="front")
        self.draw_hands_front(dr, t, S, J)
        self.draw_burst(dr, t, S, J)
        self.draw_stage_front(dr, t, S)
        self.draw_peek_at(dr, t, S, "aud")
        self.draw_audience(dr, t, S)
        self.draw_bubble(dr, t, S, J)
        x0, y0 = int(ox * S), int(oy * S)
        full.paste(wimg.crop((x0, y0, x0 + full.width, y0 + full.height)), (0, 0))
        hs = self.cfg.get("hook_text_s", 13.0)
        a, b = HOOK_AGAIN
        if a <= treal <= b:
            # l'accroche revient en grand, une seconde, pendant que le lapin se cache derrière Bounce
            fd = ImageDraw.Draw(full)
            al = clamp01((treal - a) / 0.15) * clamp01((b - treal) / 0.2)
            words = (self.cfg.get("hook_text") or "").upper().split()
            half = (len(words) + 1) // 2
            lines = [" ".join(words[:half]), " ".join(words[half:])]
            hf = font(88 * S0)
            lh = int(88 * 1.25 * S0)
            hook_top = full.height * self.cfg["hook_top"]
            for i, line in enumerate(lines):
                fd.text((full.width / 2, hook_top + (i + 0.5) * lh), line, fill=mix((40, 30, 50), (255, 255, 255), al),
                        anchor="mm", font=hf, stroke_width=max(1, int(4 * S0)), stroke_fill=(20, 12, 26))
        elif treal >= hs:
            # rappel de l'accroche, en haut, sur deux lignes (>= 48 px de capitale à 1080)
            fd = ImageDraw.Draw(full)
            k = clamp01((treal - hs) / 0.4)
            words = (self.cfg.get("hook_text") or "").upper().split()
            half = (len(words) + 1) // 2
            for i, line in enumerate((" ".join(words[:half]), " ".join(words[half:]))):
                fd.text((full.width / 2, full.height * (0.078 + 0.042 * i)), line,
                        fill=mix((40, 30, 50), (236, 232, 244), k), anchor="mm", font=font(66 * S0),
                        stroke_width=max(1, int(4 * S0)), stroke_fill=(20, 12, 26))

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
            ell(dr, 480, 700, 470 * k, 560 * k, c, S)
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
        shake = 0.0
        v = t - 99.0
        if 0 <= v <= 0.4:
            shake = 10 * math.sin(v * 50) * (1 - v / 0.4)
        rect(dr, x0, ty + shake, x1, ty + 26 + shake, WOOD, S)
        rect(dr, x0, ty + shake, x1, ty + 6 + shake, WOOD_L, S)
        for k in range(26):
            xx = x0 + 22 + k * 19
            dr.line([xx * S, (ty + 26) * S, xx * S, (ty + 44) * S], fill=GOLD, width=max(1, int(4 * S)))

    def draw_pad(self, dr, t, S):
        if t < 12.75:
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
        if t >= PROP_RIDE[0]:
            return
        cx, top, bot = HAT_X, TABLE[2] - HAT_H, TABLE[2]
        dy = 0.0
        for c in self.sc.P.cs:
            if c["kind"] == "silk":
                v = t - c["t"]
                amp = 10 if c["soft"] else 26 + 30 * c["gain"]
                if 0 <= v <= 0.3:
                    dy -= amp * math.sin(math.pi * v / 0.3)
        top += dy
        bot += dy * 0.6
        if back:
            ell(dr, cx, top, HAT_W / 2 + 30, 26, HATC, S)
            ell(dr, cx, top, HAT_W / 2 - 4, 17, (8, 6, 12), S)
            for k, col in enumerate(SILKS[:4]):
                xs = cx - 72 + k * 48
                dr.polygon(poly([(xs - 16, top + 6), (xs + 16, top + 6), (xs + 4 * math.sin(t * 3 + k), top - 26)], S),
                           fill=col)
            return
        pts = [(cx - HAT_W / 2, top), (cx + HAT_W / 2, top), (cx + HAT_W / 2 - 14, bot), (cx - HAT_W / 2 + 14, bot)]
        dr.polygon(poly(pts, S), fill=HATC)
        rect(dr, cx - HAT_W / 2 + 1, top + 22, cx + HAT_W / 2 - 1, top + 50, HAT_BAND, S)
        dr.arc([(cx - HAT_W / 2 - 30) * S, (top - 26) * S, (cx + HAT_W / 2 + 30) * S, (top + 26) * S], 0, 180,
               fill=HAT_RIM, width=max(1, int(8 * S)))

    def draw_prop_ride(self, dr, t, S):
        """Le chapeau du tour, coiffé sur Bounce quand il jaillit, puis envolé hors de la table."""
        a, b = PROP_RIDE
        if a <= t < b:
            bx, by = self.sc.bpos(t)
            ang = 0.25 * math.sin(t * 9)
            draw_prop_shape(dr, bx, by - R + 30, ang, S)
            return
        a, b = PROP_FLY
        if a <= t < b:
            bx, by = self.sc.bpos(a)
            p = arc((bx, by - R + 30), (60.0, 1150.0), a, b - a, t)
            draw_prop_shape(dr, p[0], p[1], 7 * (t - a), S)

    def draw_silks(self, dr, t, S):
        emits = [c["t"] for c in self.sc.P.cs if c["kind"] == "silk"] + [-0.8, -0.3]
        for te in emits:
            v = t - te
            if not (0 <= v <= 0.9) or te >= PROP_RIDE[0] + 0.01:
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
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(2, int(w * S)))

    def draw_screen(self, dr, t, S, J):
        if not (SCREEN[0] <= t <= SCREEN[1]):
            return
        gL, gR = J["gL"], J["gR"]
        grow = smooth((t - SCREEN[0]) / 0.35)
        top = (gL[1] + gR[1]) / 2
        x0 = lerp((gL[0] + gR[0]) / 2, gL[0], grow)
        x1 = lerp((gL[0] + gR[0]) / 2, gR[0], grow)
        bot = TABLE[2] + 4
        if t > 12.2:
            k = smooth((t - 12.2) / 0.5)
            top = lerp(top, PAD[2], k)
            x0, x1 = lerp(x0, PAD[0], k), lerp(x1, PAD[1], k)
        bx, by = self.sc.bpos(t)
        sag = 0.0
        if 11.0 <= t <= 12.3 and by < top:
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

    def draw_peek_at(self, dr, t, S, where):
        """Le lapin qui se montre ailleurs que dans le chapeau : dans le public, derrière la table."""
        pk = self.sc.peek(t)
        if pk is None or pk[0] != where:
            return
        _w, lvl, age = pk
        if where == "aud":
            draw_peek(dr, (292.0, 1222.0), 0.12 * math.sin(age * 5), lvl, age, S)
        elif where == "tableR":
            draw_peek(dr, (668.0, TABLE[2] + 30), 0.35, lvl, age, S)

    # -------- le magicien
    def draw_magician(self, dr, t, S, J, part):
        P = J["P"]
        s = J["s"]
        infl = J["infl"]
        col = SUIT
        cold = SUIT_D
        if part == "body":
            cp = [P(196, -70 * infl), P(196, 70 * infl), P(-95, 150 * infl), P(-95, -150 * infl)]
            dr.polygon(poly(cp, S), fill=CAPE)
            cl = [P(186, -50 * infl), P(186, 50 * infl), P(-85, 125 * infl), P(-85, -125 * infl)]
            dr.polygon(poly(cl, S), fill=CAPE_L)
            if J["mode"] not in ("sit", "fly"):
                for (fx, fy), dx in ((J["fL"], -24), (J["fR"], 24)):
                    capsule(dr, P(10, dx), (fx, fy - 18 * s), 15 * s, (26, 28, 44), S)
            body = [P(-60, -50 * infl), P(-60, 50 * infl), P(0, 62 * infl), P(150, 70 * infl),
                    P(198, 58 * infl), P(204, 0), P(198, -58 * infl), P(150, -70 * infl), P(0, -62 * infl)]
            dr.polygon(poly(body, S), fill=col)
            dr.polygon(poly([P(196, -22), P(196, 22), P(80, 0)], S), fill=SHIRT)
            for k in range(3):
                c = P(60 + k * 34, -4)
                ell(dr, c[0], c[1], 5 * s, 5 * s, cold, S)
            hc = J["head"]
            ell(dr, hc[0], hc[1], 52 * s, 52 * s, (232, 196, 170), S)
            nose = P(250 + 6, 49 * FACE(t))
            ell(dr, nose[0], nose[1], 11 * s, 9 * s, (232, 196, 170), S)
            if J["mode"] not in ("sit", "fly"):
                for (fx, fy) in (J["fL"], J["fR"]):
                    self.shoe(dr, t, fx, fy, S, s)
            return
        if part == "arms":
            for (sh, g) in ((J["shL"], J["gL"]), (J["shR"], J["gR"])):
                capsule(dr, sh, g, 17 * s, cold, S)
            for g in (J["gL"], J["gR"]):
                glove(dr, g[0], g[1], S, s)
            return
        if part == "front":
            if J["mode"] not in ("sit", "fly"):
                return
            for (fx, fy), kn, dx in ((J["fL"], J["kL"], -24), (J["fR"], J["kR"], 24)):
                capsule(dr, P(10, dx), kn, 15 * s, (26, 28, 44), S)
                capsule(dr, kn, (fx, fy - 18 * s), 15 * s, (26, 28, 44), S)
                self.shoe(dr, t, fx, fy, S, s)
            return
        # « hat » : nœud papillon, chapeau, lapin qui se montre (derrière Bounce)
        tc = J["tie"]
        a = math.radians(J["lean"])
        for shape in ([(-30, -14), (0, 0), (-30, 14)], [(30, -14), (0, 0), (30, 14)]):
            dr.polygon(poly([(tc[0] + s * (u * math.cos(a) - v * math.sin(a)), tc[1] + s * (u * math.sin(a) + v * math.cos(a)))
                             for (u, v) in shape], S), fill=TIE)
        ell(dr, tc[0], tc[1], 9 * s, 9 * s, dim(TIE, 0.8), S)
        hx_, hy_, ang, flat, up = self.sc.hat(t, J)
        pk = self.sc.peek(t)
        if pk is not None and pk[0] not in ("head", "table"):
            pk = None
        lid = 0.0
        sit_on_top = None
        if pk is not None:
            where, lvl, age = pk
            lid = clamp01(lvl * 2)
            top = self.sc.hat_top(hx_, hy_, ang, flat)
            if lvl > 1.0:
                sit_on_top = (top, lvl, age)
            else:
                draw_peek(dr, top, ang, lvl, age, S)
        if not (t >= INHAT[0] and up):
            draw_top_hat(dr, hx_, hy_, ang, S, flat=flat, lid=lid, t=t)
        else:
            draw_top_hat(dr, hx_, hy_, ang, S, t=t)
        if sit_on_top is not None:
            top, lvl, age = sit_on_top
            k = clamp01(lvl - 1.0)
            draw_rabbit(dr, top[0], top[1] - 60 * k + 30, S, 1.0, math.sin(age * 4) * 3, t)
        if t >= EARS_IN:
            # dans le chapeau-piège : le lapin, dessous ; ses oreilles dépassent (derrière Bounce)
            tilt = ang - math.pi
            L = 300.0
            for (th, g, _x, _y, kind) in self.sc.P.hits:
                v = t - th
                if kind == "inhat" and 0 <= v <= 0.45:
                    L -= 110 * g * math.sin(math.pi * clamp01(v / 0.45)) * (1 if v < 0.2 else 0.6)
            if t < INHAT[0]:
                L = 230.0 * clamp01((t - EARS_IN) / 0.2)
            draw_ears(dr, (hx_, hy_), tilt, L, t, S)
        rf = self.sc.rabbit_free(t)
        if rf is not None:
            draw_rabbit(dr, rf[0], rf[1], S, rf[2], 0.0, t, size=1.15)

    def draw_hands_front(self, dr, t, S, J):
        """Les gants passent devant Bounce quand ils le tiennent (chapeau-filet, fin)."""
        if (GRAB[0] - 0.1 <= t < FLY_HAT) or (HAT_FLIP[0] <= t <= HAT_FLIP[1]) or (4.95 <= t <= 7.45):
            for g in (J["gL"], J["gR"]):
                glove(dr, g[0], g[1], S, J["s"])

    def draw_inhat_front(self, dr, t, S, J):
        if t < HAT_FLIP[1]:
            return
        hx_, hy_, ang, flat, up = self.sc.hat(t, J)
        draw_top_hat(dr, hx_, hy_, ang, S, front_only=True)

    def shoe(self, dr, t, fx, fy, S, s=1.0):
        pts = [(-46, -12), (34, -18), (40, 10), (-46, 12)]
        dr.polygon(poly([(fx + u * s, fy + v * s) for (u, v) in pts], S), fill=SHOE)

    def draw_wand(self, dr, w, S):
        x, y, a = w[:3]
        tip = (x + 150 * math.cos(a), y + 150 * math.sin(a))
        tail = (x - 40 * math.cos(a), y - 40 * math.sin(a))
        dr.line([tail[0] * S, tail[1] * S, tip[0] * S, tip[1] * S], fill=WAND, width=max(2, int(13 * S)))
        t2 = (tip[0] - 26 * math.cos(a), tip[1] - 26 * math.sin(a))
        dr.line([t2[0] * S, t2[1] * S, tip[0] * S, tip[1] * S], fill=(250, 250, 250), width=max(2, int(13 * S)))

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

    def draw_burst(self, dr, t, S, J):
        # le sort : il part de la baguette, frappe Bounce, ricoche et revient sur le magicien
        a, b = BOLT_OUT
        if a <= t <= BOLT_BACK[1]:
            J0 = self.sc.rig(a)
            w0 = self.sc.wand(a, J0)
            tip = self.sc.wand_tip(w0)
            bx, by = self.sc.bpos(BOLT_OUT[1])
            if t <= b:
                v = (t - a) / (b - a)
                p0, p1 = tip, (bx, by)
            else:
                v = (t - b) / (BOLT_BACK[1] - b)
                p0, p1 = (bx, by), (560.0, 760.0)
            for j in range(6):
                vv = max(0.0, v - j * 0.06)
                p = (lerp(p0[0], p1[0], vv), lerp(p0[1], p1[1], vv))
                dr.polygon(poly(star_pts(p[0], p[1], 40 - 5 * j, t * 9, 4, 0.32), S), fill=mix(SPARK, (255, 255, 255), 0.4))
        v = t - BOLT_OUT[1]
        if 0 <= v <= 0.35:                       # l'impact sur Bounce
            bx, by = self.sc.bpos(BOLT_OUT[1])
            for i in range(8):
                ang = i * math.pi / 4
                rr = 120 + 300 * v
                dr.polygon(poly(star_pts(bx + rr * math.cos(ang), by + rr * math.sin(ang), 26 * (1 - v / 0.35) + 4, i, 4, 0.35), S),
                           fill=SPARK)
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
                for i in range(8):
                    ang = i * 2 * math.pi / 8
                    rr = size * (60 + 260 * k)
                    dr.polygon(poly(star_pts(x + rr * math.cos(ang), y + rr * math.sin(ang), size * 22 * (1 - k) + 2,
                                             k * 5 + i, 4, 0.35), S), fill=SPARK)
        a, b, c, d = DOVES
        if a <= t <= a + 0.4:
            k = (t - a) / 0.4
            for g in (J["gL"], J["gR"]):
                for i in range(6):
                    ang = i * math.pi / 3
                    dr.polygon(poly(star_pts(g[0] + 60 * k * math.cos(ang), g[1] + 60 * k * math.sin(ang), 12 * (1 - k) + 2,
                                             i, 4, 0.35), S), fill=SPARK)

    # -------- cage, colombes
    def draw_cage(self, dr, t, S, J):
        c = self.sc.cage(t, J)
        if c is None:
            return
        x, y = c
        ang = self.sc.cage_angle(t)
        small = t >= CAGE_FLY[1]
        w2, h = (115.0, 330.0) if not small else (78.0, 300.0)
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(u, v):           # u vers la droite, v vers le haut, autour du centre bas
            return (x + u * ca + v * sa, y - v * ca + u * sa)
        dr.polygon(poly([Q(-w2 - 10, -8), Q(w2 + 10, -8), Q(w2 + 10, 14), Q(-w2 - 10, 14)], S), fill=GOLD)
        for k in range(9):
            uu = -w2 + k * (2 * w2) / 8
            dr.line(poly([Q(uu, 10), Q(uu, h - 40)], S), fill=GOLD, width=max(1, int(7 * S)))
        top = [Q(w2 * math.cos(i * math.pi / 12), h - 40 + 60 * math.sin(i * math.pi / 12)) for i in range(13)]
        dr.line(poly(top, S), fill=GOLD, width=max(1, int(9 * S)))
        dr.line(poly([Q(-w2, h - 40), Q(w2, h - 40)], S), fill=GOLD, width=max(1, int(8 * S)))
        ring_c = Q(0, h + 42)
        dr.ellipse([(ring_c[0] - 20) * S, (ring_c[1] - 20) * S, (ring_c[0] + 20) * S, (ring_c[1] + 20) * S],
                   outline=GOLD, width=max(1, int(7 * S)))
        if CAGE_LOCK <= t < CAGE_FLY[0]:
            lk = Q(w2 - 6, 120)
            rect(dr, lk[0] - 20, lk[1] - 4, lk[0] + 20, lk[1] + 30, (250, 210, 80), S, r=4)
            dr.arc([(lk[0] - 13) * S, (lk[1] - 26) * S, (lk[0] + 13) * S, (lk[1] + 4) * S], 180, 360, fill=(250, 210, 80),
                   width=max(1, int(6 * S)))

    def draw_doves(self, dr, t, S, J):
        a, b, c, d = DOVES
        if not (a <= t <= d + 0.8):
            return
        bx, by = self.sc.bpos(min(t, c))
        for side, g in ((-1, J["gL"]), (1, J["gR"])):
            grip = (bx + side * 64, by - R - 22)
            if t < b:
                g0 = self.sc.rig(a)["gL" if side < 0 else "gR"]
                k = smooth((t - a) / (b - a))
                p = (lerp(g0[0], grip[0], k), lerp(g0[1], grip[1], k) - 120 * math.sin(math.pi * k))
            elif t < c:
                p = (grip[0], grip[1] + 6 * math.sin(t * 20))
            elif t < d:
                k = (t - c) / (d - c)
                p = (grip[0] + side * 420 * k + 30 * math.sin(t * 25), grip[1] + 160 * k * k - 260 * k)
            else:
                continue
            flap = math.sin(t * (40 if b <= t < c else 30) + side)
            dove(dr, p[0], p[1], side, flap, S)
        if t >= c:                          # les plumes, après le plafond
            v = t - c
            for i in range(9):
                fx = 600 + (i - 4) * 38 + 30 * math.sin(v * 3 + i)
                fy = 250 + 160 * v + 20 * math.sin(v * 5 + i * 1.7) + (i % 3) * 18
                if v > 1.4:
                    continue
                ang = math.sin(v * 4 + i) * 0.8
                ca, sa = math.cos(ang), math.sin(ang)
                col = mix((248, 248, 252), WALL, clamp01((v - 0.9) / 0.5))
                dr.polygon(poly([(fx - 18 * ca, fy - 18 * sa), (fx - 4 * sa, fy + 4 * ca), (fx + 18 * ca, fy + 18 * sa),
                                 (fx + 4 * sa, fy - 4 * ca)], S), fill=col)

    # -------- le public : une frange
    def draw_audience(self, dr, t, S):
        rows = [(1205.0, 0.9, 0), (1290.0, 1.0, 1)]
        laugh = 0.0
        for (t0, a) in LAUGH:
            v = t - t0
            if 0 <= v <= 1.4:
                laugh = max(laugh, a * (1 - v / 1.4))
        up = any(a <= t <= b for (a, b) in ARMS_UP)
        for (y, sc_, ri) in rows:
            for k in range(7):
                x = 140 + k * 140 + (70 if ri == 1 else 0)
                ph = (k * 1.7 + ri * 2.3)
                bob = laugh * 22 * abs(math.sin(t * 11 + ph))
                if up:
                    bob = max(bob, 16 * abs(math.sin(t * 8 + ph)))
                col = AUD[ri + 1]
                hy = y - bob
                if up:
                    for side in (-1, 1):
                        capsule(dr, (x + side * 40 * sc_, hy + 50 * sc_), (x + side * 66 * sc_, hy - 80 * sc_), 12 * sc_, col, S)
                        ell(dr, x + side * 66 * sc_, hy - 80 * sc_, 17 * sc_, 17 * sc_, col, S)
                ell(dr, x, hy + 100 * sc_, 78 * sc_, 66 * sc_, col, S)
                ell(dr, x, hy, 44 * sc_, 48 * sc_, col, S)
                dr.arc([(x - 44 * sc_) * S, (hy - 48 * sc_) * S, (x + 44 * sc_) * S, (hy + 48 * sc_) * S], 200, 340,
                       fill=AUD_RIM, width=max(1, int(4 * S)))

    # -------- bulles : accrochées à la tête du magicien
    def draw_bubble(self, dr, t, S, J):
        for (a, b, text) in self.bubbles:
            if not (a <= t <= b):
                continue
            s = J["s"]
            head = J["head"]
            hx_, hy_, ang, flat, up = self.sc.hat(t, J)
            on_head = t < HAT_FALL[0]
            top_y = self.sc.hat_top(hx_, hy_, ang, flat)[1] if on_head else head[1] - 52 * s
            fs = 52
            fr = font(fs)
            bw = fr.getlength(text) + 52
            bh = fs * 1.5
            Z, ox, oy = cam(t)
            xmin, xmax = ox + 24 / Z + bw / 2, ox + 890 / Z - bw / 2
            bx, by = self.sc.bpos(t)
            cx = min(max(head[0] + 20, xmin), xmax)
            cy = top_y - 60 - bh / 2
            if t < 13.3:
                cy = max(cy, 440.0)
            # jamais sur Bounce : sinon, à côté de la tête du magicien, du côté opposé à Bounce
            if abs(cx - bx) < bw / 2 + R + 10 and abs(cy - by) < bh / 2 + R + 10:
                if abs(head[0] - bx) > R * 1.6:
                    cy = by - R - bh / 2 - 24          # au-dessus de Bounce, mais du côté du magicien
                else:
                    side = 1 if bx < head[0] else -1
                    cx = min(max(head[0] + side * (bw / 2 + 60 * s + 20), xmin), xmax)
                    if abs(cx - head[0]) < bw / 2 + 52 * s:      # pas de place de ce côté : l'autre
                        cx = min(max(head[0] - side * (bw / 2 + 60 * s + 20), xmin), xmax)
                    cy = head[1] - 30 * s
                    if abs(cx - bx) < bw / 2 + R + 10 and abs(cy - by) < bh / 2 + R + 10:
                        cy = by + R + bh / 2 + 20
            if t >= EARS_IN:                  # les oreilles qui dépassent du chapeau : la bulle passe au-dessus
                ex0, ex1 = bx - 110, bx + 110
                etop = hy_ - 300 * math.cos(ang - math.pi) if t >= INHAT[0] else hy_ - 240
                if cx + bw / 2 > ex0 and cx - bw / 2 < ex1 and cy + bh / 2 > etop:
                    cy = etop - bh / 2 - 14
            cy = max(cy, oy + 370 / Z)
            if t < 13.3 and cy < 440.0:       # jamais sous la grande accroche
                cy = 440.0
                if abs(cx - bx) < bw / 2 + R + 10 and abs(cy - by) < bh / 2 + R + 10:
                    cy = by + R + bh / 2 + 16
            k = clamp01((t - a) / 0.12)
            sc_ = 0.75 + 0.25 * k
            x0, y0, x1, y1 = cx - bw / 2 * sc_, cy - bh / 2 * sc_, cx + bw / 2 * sc_, cy + bh / 2 * sc_
            tgt = (head[0] - 10 * s, head[1] - 40 * s) if on_head else (head[0], head[1] - 50 * s)
            bxm = max(x0 + 30, min(x1 - 30, tgt[0]))
            tail = [(bxm - 20, y1 - 4), (bxm + 20, y1 - 4), (lerp(bxm, tgt[0], 0.6), min(tgt[1] - 10, y1 + 60))]
            dr.polygon(poly(tail, S), fill=(250, 250, 252))
            dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=bh / 2 * S * sc_, fill=(250, 250, 252),
                                 outline=(30, 24, 40), width=max(1, int(4 * S)))
            dr.text((cx * S, cy * S), text, fill=(24, 20, 30), anchor="mm", font=font(fs * S * sc_))


def draw_prop_shape(dr, x, y, ang, S):
    """Le chapeau du tour, à l'endroit (ouverture en bas), centré sur (x, y)."""
    ca, sa = math.cos(ang), math.sin(ang)

    def Q(u, v):
        return (x + u * ca - v * sa, y + u * sa + v * ca)
    w, h = HAT_W * 0.8, HAT_H * 0.8
    dr.polygon(poly([Q(-w / 2 + 10, -h), Q(w / 2 - 10, -h), Q(w / 2, 0), Q(-w / 2, 0)], S), fill=HATC)
    dr.polygon(poly([Q(-w / 2 + 4, -36), Q(w / 2 - 4, -36), Q(w / 2, -10), Q(-w / 2, -10)], S), fill=HAT_BAND)
    pts = [Q((w / 2 + 26) * math.cos(k * math.pi / 12), 14 * math.sin(k * math.pi / 12)) for k in range(25)]
    dr.polygon(poly(pts, S), fill=HATC)


def glove(dr, x, y, S, s=1.0):
    k = max(0.7, s)
    ell(dr, x, y, 34 * k, 34 * k, GLOVE, S)
    ell(dr, x + 5 * k, y + 8 * k, 18 * k, 14 * k, GLOVE_D, S)
    rect(dr, x - 25 * k, y + 18 * k, x + 25 * k, y + 38 * k, GLOVE, S, r=7)


def dove(dr, x, y, side, flap, S):
    k = 1.25
    ell(dr, x, y, 46 * k, 26 * k, (248, 248, 252), S)
    ell(dr, x + side * 40 * k, y - 14 * k, 18 * k, 16 * k, (248, 248, 252), S)
    dr.polygon(poly([(x + side * 56 * k, y - 14 * k), (x + side * 72 * k, y - 10 * k), (x + side * 56 * k, y - 6 * k)], S),
               fill=(240, 190, 90))
    dr.polygon(poly([(x - side * 40 * k, y), (x - side * 70 * k, y - 10 * k), (x - side * 62 * k, y + 12 * k)], S),
               fill=(230, 230, 240))
    wy = 80 * flap
    dr.polygon(poly([(x - 24 * k, y - 6), (x + 18 * k, y - 6), (x - 10 * k, y - 34 * k - wy)], S), fill=(236, 236, 246))


def draw_rabbit(dr, x, y, S, spring, spin, t, size=1.0):
    """Le lapin, sans visage : corps, tête, longues oreilles. (x, y) = centre du corps."""
    RS = 1.3 * size
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


def draw_peek(dr, top, ang, lvl, age, S):
    """Le lapin qui dépasse du haut du chapeau : d'abord les oreilles, puis la tête (le chapeau, dessiné
    après, cache ce qui est dessous)."""
    ca, sa = math.cos(ang), math.sin(ang)

    def Q(u, v):              # u : vers le haut du chapeau ; v : vers la droite
        return (top[0] + v * ca + u * sa, top[1] + v * sa - u * ca)
    head_up = 54 * clamp01((lvl - 0.75) / 0.25)
    turn = 0.25 * math.sin(age * 7) * (lvl > 0.9)
    L = (90 + 110 * clamp01(lvl / 0.8)) * clamp01(lvl / 0.3)
    hb = Q(head_up - 10, 0)
    for side in (-1, 1):
        a = ang + side * 0.22 + turn
        b0 = Q(head_up + 20, side * 22)
        tip = (b0[0] + math.sin(a) * L, b0[1] - math.cos(a) * L)
        nx, ny = math.cos(a) * 24, math.sin(a) * 24
        dr.polygon(poly([(b0[0] - nx, b0[1] - ny), (b0[0] + nx, b0[1] + ny), (tip[0] + nx * 0.6, tip[1] + ny * 0.6), tip,
                         (tip[0] - nx * 0.6, tip[1] - ny * 0.6)], S), fill=RABBIT)
        mid = ((b0[0] + tip[0]) / 2, (b0[1] + tip[1]) / 2)
        dr.polygon(poly([(b0[0] - nx * 0.4, b0[1] - ny * 0.4), (b0[0] + nx * 0.4, b0[1] + ny * 0.4), mid, tip], S),
                   fill=RABBIT_IN)
    if head_up > 0:
        ell(dr, hb[0], hb[1], 50, 46, RABBIT, S)
        ell(dr, hb[0] - 34, hb[1] + 14, 16, 12, RABBIT_D, S)
        ell(dr, hb[0] + 34, hb[1] + 14, 16, 12, RABBIT_D, S)


def draw_ears(dr, base_pt, tilt, L, t, S):
    """Deux oreilles de lapin qui sortent d'un point (le bord du chapeau), vers le haut (tilt)."""
    for side in (-1, 1):
        a = tilt + side * (0.2 + 0.05 * math.sin(t * 5 + side))
        b0 = (base_pt[0] + side * 24 * math.cos(tilt), base_pt[1] + side * 24 * math.sin(tilt))
        tip = (b0[0] + math.sin(a) * L, b0[1] - math.cos(a) * L)
        nx, ny = math.cos(a) * 25, math.sin(a) * 25
        dr.polygon(poly([(b0[0] - nx, b0[1] - ny), (b0[0] + nx, b0[1] + ny), (tip[0] + nx * 0.6, tip[1] + ny * 0.6), tip,
                         (tip[0] - nx * 0.6, tip[1] - ny * 0.6)], S), fill=RABBIT)
        mid = (b0[0] + (tip[0] - b0[0]) * 0.55, b0[1] + (tip[1] - b0[1]) * 0.55)
        dr.polygon(poly([(b0[0] - nx * 0.4, b0[1] - ny * 0.4), (b0[0] + nx * 0.4, b0[1] + ny * 0.4), mid, tip], S),
                   fill=RABBIT_IN)


def draw_top_hat(dr, x, y, ang, S, flat=0.0, lid=0.0, t=0.0, front_only=False):
    """Le haut-de-forme : (x, y) = centre du bord, ang = angle (0 = droit, pi = retourné)."""
    ca, sa = math.cos(ang), math.sin(ang)
    hk = 1.0 - 0.6 * flat
    wk = 1.0 + 0.35 * flat

    def P(u, v):
        u, v = u * 1.1 * hk, v * 1.3 * wk
        return (x + v * ca + u * sa, y + v * sa - u * ca)
    if front_only:
        crown = [P(0, -60), P(0, 60), P(140, 64), P(140, -64)]
        dr.polygon(poly(crown, S), fill=HATC)
        band = [P(8, -61), P(8, 61), P(34, 62), P(34, -62)]
        dr.polygon(poly(band, S), fill=HAT_BAND)
        dr.line(poly([P(140, -64), P(140, 64)], S), fill=HAT_RIM, width=max(1, int(6 * S)))
        bpts = [P(6 * math.sin(k * math.pi / 12), 84 * math.cos(k * math.pi / 12)) for k in range(25)]
        bpts += [P(-12 * math.sin(k * math.pi / 12), 84 * math.cos(math.pi - k * math.pi / 12)) for k in range(25)]
        dr.polygon(poly(bpts, S), fill=HATC)
        dr.line(poly(bpts[:25], S), fill=HAT_RIM, width=max(1, int(5 * S)))
        return
    crown = [P(0, -60), P(0, 60), P(140, 64), P(140, -64)]
    dr.polygon(poly(crown, S), fill=HATC)
    band = [P(8, -61), P(8, 61), P(34, 62), P(34, -62)]
    dr.polygon(poly(band, S), fill=HAT_BAND)
    if lid > 0:
        l0, l1 = P(140 + 80 * lid, -74), P(140 + 30 * lid, 70)
        dr.line(poly([l0, l1], S), fill=HAT_RIM, width=max(1, int(14 * S)))
    else:
        dr.line(poly([P(140, -64), P(140, 64)], S), fill=HAT_RIM, width=max(1, int(6 * S)))
    dr.line(poly([P(10, -52), P(128, -54)], S), fill=HAT_RIM, width=max(1, int(4 * S)))
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
    "hook_text_s": 13.0, "hook_top": 0.125, "hook_font_size": 88, "hook_width": 0.72, "hook_speed": 1.1,
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
