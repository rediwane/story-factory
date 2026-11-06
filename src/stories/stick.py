"""
Prototype « stick » : Bounce à la bibliothèque, avec Stick (perso d'un fan : une balle bleu marine qui colle
à tout ce qu'il touche).

Au début, Stick lit, collé au mur sous le panneau QUIET. Bounce rebondit, le touche : Stick se colle à lui.
À chaque rebond de Bounce, Stick touche quelque chose et ce quelque chose reste collé (« Stick! ») : le livre
du lecteur, une rangée de livres, le panneau QUIET, la bibliothécaire (qui voulait les décoller), le lecteur
(qui ne lâche pas son livre), la lampe, le bureau. Il suffirait que Bounce arrête de rebondir.
La bibliothécaire remet deux fois les choses en place (motif), la troisième fois c'est elle qui colle.
Vers 0,63 D elle manque d'exploser (issue partielle) ; vers 0,7 D tout s'effondre sur Bounce, le silence
revient (« Finally. ») : fausse fin. Puis « …bounce » : tout le tas repart. À la fin, elle craque :
« QUIET! », le cri le plus fort de la vidéo. Stick sursaute et lâche tout : tout retombe à sa place, au
ralenti, le panneau se raccroche à son clou de justesse. Bounce s'en sort ; tout le monde regarde la
bibliothécaire.

Tout est dessiné en coordonnées d'écran 1080×1920, mis à l'échelle de la config (aperçu 540×960).
Le son est calculé sur les instants exacts des contacts : identique quel que soit le nombre d'images.

    python3 src/stories/stick.py configs/<name>.json [--simulate]
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
BANK_DIR = os.environ.get("STICK_BANK",
                          "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lundi/stick/bank")

# ------------------------------------------------------------------ voix (banque Kokoro vérifiée par whisper)
BANK_FILES = {"Stick!": "stick.wav", "STICK!": "stick2.wav", "Excuse me!": "excuse.wav",
              "Quiet, please!": "quietplease.wav", "Let go!": "letgo.wav", "Put me down!": "putdown.wav",
              "Stop bouncing!": "stop.wav", "...quiet.": "whisper.wav", "Finally.": "finally.wav",
              "No, no, no!": "nonono.wav", "QUIET!": "scream.wav"}
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
            BANK[text] = _read(os.path.join(BANK_DIR, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    """La prise du mot de Bounce est gardée dans la banque : l'aperçu et le rendu final ont le même son."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(BANK_DIR, "hero_%s_%s_%s.wav" % key)
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
            if len(v) / SR <= 0.70:
                break
        _hero_memo[key] = best
        if best is not None:
            with wave.open(cache, "w") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((np.clip(best, -1, 1) * 32767).astype(np.int16).tobytes())
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# l'accroche : posée par ce thème juste après le premier « Bounce » (base.hook_audio rend None pour que
# base.place_words ne réserve pas le début) ; piper, débit accéléré sans changer la hauteur
HOOK_T = 0.83
_hook_memo = {}


def hook_clip(cfg):
    key = cfg.get("hook_text")
    if key not in _hook_memo:
        v = ak.piper_say(key, ak.VOICE_NAME, SR, length_scale=cfg.get("hook_length", 0.62))
        if v is None:
            v = ak.hook_voice(key)
        if v is not None:
            v = np.asarray(v, float)
            e = np.abs(v)
            idx = np.where(e > 0.04 * e.max())[0]
            v = v[max(0, idx[0] - int(0.01 * SR)):min(len(v), idx[-1] + int(0.03 * SR))].copy()
            v /= np.abs(v).max() + 1e-9
            mx = cfg.get("hook_max_s", 1.14)          # la voix finit avant 2,0 s
            if len(v) / SR > mx:
                v = base.pitch(v, len(v) / SR / mx)
            n = min(int(0.02 * SR), len(v))
            v[-n:] *= np.linspace(1, 0, n)
        _hook_memo[key] = v
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = lambda cfg: None

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
G = 2600.0


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, k):
    return a + (b - a) * k


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


class KF:
    """Images clés lissées : KF(v0, [(t, v), ...])."""

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
        k = smooth((t - t0) / max(1e-6, t1 - t0))
        if isinstance(v0, tuple):
            return tuple(lerp(a, b, k) for a, b in zip(v0, v1))
        return lerp(v0, v1, k)


def hop(t, hops):
    y = 0.0
    for (t0, h) in hops:
        T = 2 * math.sqrt(2 * h / G)
        u = t - t0
        if 0 <= u <= T:
            y = max(y, h - 0.5 * G * (u - T / 2) ** 2)
    return y


# ------------------------------------------------------------------ ralenti sur l'issue
SLOW_A, SLOW_B, SLOW_K = 60.05, 61.05, 0.35


def vt(t):
    """Temps de l'image (ralenti entre SLOW_A et SLOW_B, réel ailleurs)."""
    if t <= SLOW_A:
        return t
    if t <= SLOW_B:
        return SLOW_A + (t - SLOW_A) * SLOW_K
    return SLOW_A + (SLOW_B - SLOW_A) * SLOW_K + (t - SLOW_B)


# ------------------------------------------------------------------ le décor (coordonnées d'écran)
FL = 1130.0                  # haut du parquet
BR = 120.0                   # rayon de Bounce
SRAD = 80.0                  # rayon de Stick
ATT = (166.0, -112.0)        # Stick, collé en haut à droite de Bounce
Y_FLOOR = FL - BR
POUFS = {"p1": (338.0, 1066.0, 78.0), "p2": (700.0, 1066.0, 78.0)}   # x, haut, demi-largeur
POUF_DENT = 30.0
STICK_WALL = (722.0, 898.0)  # Stick lit, collé au mur
SIGN_C = (530.0, 618.0)
SIGN_W, SIGN_H = 270.0, 104.0
NAIL = (530.0, 548.0)
SHELF = (770.0, 1080.0, 520.0)     # x0, x1, haut ; planches tous les 120 px
ROW1_Y = 640.0                     # planche sous la rangée qu'il emporte
DESK = (95.0, 330.0, 930.0)        # x0, x1, plateau
LAMP_HOME = (292.0, 930.0)
CHAIR = (770.0, 980.0)             # fauteuil du lecteur, x0 x1
SIDE_T = (735.0, 1010.0)           # guéridon du livre 2 (dessus)

# couleurs
WALL = (46, 31, 27)
WALL_D = (34, 22, 19)
WALL_L = (60, 42, 35)
WOOD = (122, 80, 50)
WOOD_D = (84, 54, 34)
WOOD_L = (150, 104, 68)
FLOOR_C = (58, 40, 30)
FLOOR_L = (72, 52, 40)
RUG = (34, 66, 58)
RUG_L = (46, 86, 74)
CREAM = (238, 230, 204)
INKC = (24, 22, 26)
NAVY_O = (14, 20, 124)
NAVY_I = (34, 48, 204)
ARROW = (196, 214, 255)
LIB = (150, 84, 170)
LIB_D = (104, 56, 122)
LIB_SKIRT = (66, 48, 92)
SKIN = (226, 176, 146)
HAIR = (92, 84, 92)
READ_B = (58, 150, 150)
READ_D = (40, 108, 108)
READ_SK = (160, 108, 78)
VELVET = (120, 36, 50)
VELVET_D = (88, 24, 36)
SHADE = (40, 150, 90)
BRASS = (210, 170, 80)
POUF_C = {"p1": (214, 158, 60), "p2": (70, 150, 170)}

BOOK_COLS = [(196, 70, 60), (60, 120, 190), (220, 180, 70), (90, 160, 90), (170, 90, 160), (230, 120, 60),
             (80, 80, 150), (200, 200, 190), (150, 50, 80), (60, 160, 160)]

# ------------------------------------------------------------------ le plan (temps réels)
END = 62.60
SNAP = 59.75           # « QUIET! »
RELEASE = 59.95        # Stick sursaute et lâche tout
FAKE_END = 46.55       # tout s'effondre sur Bounce (fausse fin)
FAKE_RISE = 48.95      # le tas tressaute
REST_HIT = 49.20       # « …bounce » : il repart
LIB_STUCK = 21.20      # la bibliothécaire colle
ISSUE = 61.00          # le panneau se raccroche à son clou (de justesse)

# contacts de Bounce : (t réel, surface, x, gain) ; F = parquet (dur, il dit « Bounce ») ; p1/p2 = poufs (mous, muets)
CONTACTS = [
    (0.10, "F", 556, 1.0),
    (1.00, "p1", 352, 0), (1.86, "p2", 690, 0),
    (2.70, "F", 600, 1.0),
    (3.30, "p2", 690, 0), (3.85, "p2", 690, 0), (4.75, "p2", 690, 0),
    (5.45, "F", 560, 1.0), (6.30, "F", 440, 0.95), (7.20, "F", 470, 1.05),
    (7.95, "p1", 380, 0), (8.70, "p1", 390, 0), (9.35, "p1", 380, 0),
    (10.00, "F", 470, 1.0), (10.95, "F", 440, 0.95), (11.80, "F", 480, 1.05),
    (12.40, "p2", 690, 0), (13.30, "p2", 690, 0), (13.90, "p2", 690, 0),
    (14.55, "F", 580, 1.05), (15.40, "F", 560, 0.95),
    (16.05, "p1", 390, 0), (16.85, "p1", 390, 0), (17.65, "p1", 390, 0),
    (18.30, "F", 520, 1.05), (19.20, "F", 560, 1.0), (20.05, "F", 380, 0.95),
    (20.60, "p1", 380, 0), (21.20, "p1", 380, 0), (22.10, "p1", 380, 0),
    (22.90, "F", 450, 1.15), (23.75, "F", 470, 1.1), (24.60, "F", 460, 1.05),
    (25.30, "p1", 370, 0), (25.95, "p1", 370, 0), (26.65, "p1", 370, 0),
    (27.45, "F", 470, 1.25), (28.30, "F", 565, 1.05),
    (28.95, "p2", 690, 0), (29.75, "p2", 690, 0), (30.55, "p1", 360, 0),
    (31.15, "F", 450, 1.0), (32.00, "F", 470, 1.05), (32.85, "F", 450, 1.0),
    (33.55, "p1", 360, 0), (34.30, "p1", 360, 0), (35.05, "p1", 360, 0),
    (35.75, "F", 460, 1.25), (36.65, "F", 470, 1.0), (37.50, "F", 450, 1.05),
    (38.15, "p1", 352, 0), (38.95, "p1", 352, 0), (39.65, "p1", 360, 0),
    (40.30, "F", 450, 1.0), (41.15, "F", 455, 0.95), (42.00, "F", 450, 0.9),
    (42.80, "p1", 380, 0), (43.80, "p1", 380, 0),
    (44.85, "F", 450, 0.9), (45.70, "F", 445, 0.85), (FAKE_END, "F", 440, 1.0),
    (REST_HIT, "F", 440, 0.5), (50.05, "F", 445, 0.9), (50.90, "F", 450, 1.15), (51.75, "F", 450, 1.2),
    (52.45, "p1", 380, 0), (53.15, "p1", 380, 0), (53.85, "p1", 380, 0),
    (54.55, "F", 560, 1.1),
    (55.25, "p1", 380, 0), (55.95, "p1", 370, 0), (56.60, "p1", 370, 0),
    (57.25, "F", 460, 1.2), (58.10, "F", 470, 1.25), (58.95, "F", 470, 1.4),
    (59.65, "p1", 360, 0),
    (60.72, "F", 470, 1.0),
    (61.75, "F", 490, 1.05),
]
AFTER = (62.75, "F", 500)          # il rebondit encore après la dernière image
REST = (FAKE_END, FAKE_RISE)       # il ne quitte pas le sol : écrasé sous le tas, il palpite

# ce que Stick attrape (t réel)
PICK = {"book1": 2.70, "row": 4.30, "row2": 12.85, "sign": 17.25, "book2": 28.30, "clock": 30.15,
        "sign2": 38.55, "chair": 54.55}
# ce que la bibliothécaire décolle et remet : (t décollé, t remis)
PEEL = {"row": (10.00, 11.55), "sign": (19.05, 20.45)}
# retour de chaque objet à sa place après le cri (t réel d'arrivée)
CHAIR_BACK, ROW_BACK, CLOCK_BACK, LIB_BACK, BOOK1_BACK, BOOK2_BACK = 60.30, 60.34, 60.45, 60.50, 60.58, 60.62
STICK_BACK, SIGN_BACK = 60.85, ISSUE
LIB_LAND_X = 262.0
LIB_SLOT = 62.0          # où ses mains collent sur Stick (degrés)
CLOCK_HOME = (700.0, 585.0)
BOOK2_ARM = (752.0, 900.0)
CHAIR_HOME = (840.0, 975.0)
READER_HANDS = (798.0, 884.0)
# le panneau se balance quand le tas passe tout près (« presque »), puis à l'issue
SIGN_WOBBLE = [(25.95, 0.10), (32.00, 0.16), (36.60, 0.22), (ISSUE, 0.30)]

# répliques : (t, texte, clé) ; « Stick! » à chaque prise
LINES = [(2.08, "Stick!", "s_glue"), (3.50, "Stick!", "s_book"), (4.36, "Stick!", "s_row"),
         (7.98, "Excuse me!", "l_excuse"), (12.90, "Stick!", "s_row2"),
         (16.20, "Quiet, please!", "l_quiet"), (17.40, "Stick!", "s_sign"),
         (LIB_STUCK + 0.08, "STICK!", "s_lib"), (25.40, "Put me down!", "l_down"), (29.11, "Stick!", "s_book2"), (30.20, "Stick!", "s_clock"),
         (34.50, "Stop bouncing!", "l_stop"), (38.60, "Stick!", "s_sign2"),
         (42.83, "...quiet.", "l_whisper"), (47.40, "Finally.", "l_final"),
         (52.55, "No, no, no!", "l_nonono"), (55.35, "STICK!", "s_chair"), (SNAP, "QUIET!", "l_snap")]
LINE_GAIN = {"l_whisper": 0.32, "l_snap": 1.6, "l_final": 0.8, "s_lib": 1.25, "s_chair": 1.25}
WHO = {k: ("stick" if k.startswith("s_") else "lib") for (_t, _x, k) in LINES}

# la bibliothécaire quand elle n'est pas collée : x de ses pieds, gestes
LIB_X = KF(215.0, [(5.9, 215.0), (7.5, 720.0), (11.75, 720.0), (13.3, 215.0), (18.4, 215.0), (19.0, 400.0),
                   (19.3, 400.0), (19.85, 530.0), (20.45, 530.0), (20.9, 640.0)])
LIB_WALK = KF(0.0, [(5.9, 0.0), (6.0, 1.0), (7.4, 1.0), (7.5, 0.0), (11.75, 0.0), (11.85, 1.0), (13.2, 1.0),
                    (13.3, 0.0), (18.4, 0.0), (18.5, 1.0), (18.9, 1.0), (19.0, 0.0), (19.3, 0.0), (19.4, 1.0),
                    (19.75, 1.0), (19.85, 0.0), (20.45, 0.0), (20.55, 1.0), (20.8, 1.0), (20.9, 0.0)])
LIB_LEAN = KF(0.0, [(0.12, 0.0), (0.2, -16.0), (0.8, -16.0), (1.1, 0.0), (2.7, 0.0), (2.8, -14.0), (3.3, 0.0),
                    (5.95, 0.0), (6.3, 12.0), (7.3, 12.0), (7.6, 0.0), (8.0, -8.0), (9.5, -10.0), (9.9, -18.0),
                    (10.2, 0.0), (12.85, 0.0), (12.95, 22.0), (13.5, 8.0), (13.9, 0.0), (17.25, 0.0),
                    (17.45, 14.0), (18.2, 8.0), (18.8, 12.0), (19.2, 0.0), (20.6, 0.0), (20.9, -16.0)])
LIB_DIR = KF(1.0, [(7.4, 1.0), (7.55, -1.0), (10.85, -1.0), (11.0, 1.0), (11.75, 1.0), (11.85, -1.0),
                   (12.9, -1.0), (13.0, 1.0), (13.2, 1.0), (13.25, -1.0), (13.4, -1.0), (13.5, 1.0),
                   (20.8, 1.0), (20.9, -1.0)])
LIB_ARMS = [(0.0, "desk"), (0.18, "shock"), (0.9, "desk"), (2.75, "shock"), (3.5, "desk"), (5.9, "rest"),
            (7.9, "finger"), (9.75, "grab_row"), (10.1, "carry"), (10.9, "shelve"), (11.7, "rest"),
            (12.9, "shock"), (13.6, "slump"), (15.5, "point"), (17.95, "slump"), (18.7, "grab_sign"),
            (19.1, "carry"), (19.85, "hang_sign"), (20.55, "rest"), (20.9, "push")]
LIB_INFL = KF(0.0, [(40.0, 0.0), (40.7, 0.55), (41.6, 1.0), (42.1, 1.0), (42.4, 0.0), (59.3, 0.0),
                    (59.75, 1.0), (60.0, 0.2)])


class Plan:
    """La trajectoire de Bounce : des arcs sous G entre ses contacts (temps de l'image)."""

    def __init__(self):
        cs = []
        for (t, kind, x, g) in CONTACTS:
            soft = kind.startswith("p")
            if soft:
                y = POUFS[kind][1] - BR + POUF_DENT
            else:
                y = Y_FLOOR
            cs.append({"t": vt(t), "tr": t, "x": float(x), "y": y, "soft": soft, "gain": g, "kind": kind})
        self.contacts = cs
        self.ts = [c["t"] for c in cs]
        self.start = {"t": -0.42, "x": 400.0, "y": 760.0}
        self.after = {"t": vt(AFTER[0]), "x": float(AFTER[2]),
                      "y": Y_FLOOR if AFTER[1] == "F" else POUFS[AFTER[1]][1] - BR + POUF_DENT}
        self.hits = [(c["tr"], c["gain"], c["x"], c["y"]) for c in cs if not c["soft"]]

    def seg(self, tv):
        i = bisect.bisect_right(self.ts, tv)
        a = self.start if i == 0 else self.contacts[i - 1]
        b = self.after if i >= len(self.contacts) else self.contacts[i]
        return a, b

    def pos(self, tv):
        if REST[0] <= tv <= REST[1]:
            return 440.0 + 3 * math.sin(tv * 9), Y_FLOOR + 22
        if REST[1] < tv < REST_HIT:       # le tas tressaute de 3 cm
            u = (tv - REST[1]) / (REST_HIT - REST[1])
            return 440.0, Y_FLOOR + 22 * (1 - u) - 30 * 4 * u * (1 - u)
        a, b = self.seg(tv)
        if a["t"] == REST[0] and a.get("kind") == "F" and abs(a["tr"] - FAKE_END) < 1e-6:
            a = {"t": REST_HIT, "x": 440.0, "y": Y_FLOOR}
        T = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / T
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        u = tv - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def vel(self, tv):
        x0, y0 = self.pos(tv - 0.01)
        x1, y1 = self.pos(tv + 0.01)
        return (x1 - x0) / 0.02, (y1 - y0) / 0.02

    def squash(self, tv):
        sx = sy = 1.0
        if REST[0] <= tv <= REST[1] + 0.2:     # écrasé sous le tas, il palpite (il ne s'arrête jamais)
            k = clamp01((tv - REST[0]) / 0.15) * (1 - clamp01((tv - REST[1]) / 0.2))
            p = 0.04 * math.sin(tv * 2 * math.pi * 2.6)
            return 1 + (0.2 - p) * k, 1 - (0.2 - p) * k
        i = bisect.bisect_left(self.ts, tv - 0.2)
        for c in self.contacts[i:i + 4]:
            u = tv - c["t"]
            if -0.06 <= u <= 0.14:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / 0.14)
                amp = 0.2 if c["soft"] else 0.17
                sy *= 1 - amp * kk
                sx *= 1 + 0.8 * amp * kk
        return sx, sy


# ------------------------------------------------------------------ dessin : primitives
class Dr:
    """Dessin en coordonnées du monde (1080×1920), vu par une caméra : zoom K, décalage (ox, oy) ; s = échelle
    de la sortie (aperçu 540 px : 0,5)."""

    def __init__(self, dr, s, K=1.0, ox=0.0, oy=0.0):
        self.d, self.s, self.K, self.ox, self.oy = dr, s, K, ox, oy
        self.ws = K * s

    def X(self, x):
        return (x * self.K - self.ox) * self.s

    def Y(self, y):
        return (y * self.K - self.oy) * self.s

    def P(self, pts):
        return [(self.X(x), self.Y(y)) for x, y in pts]

    def rect(self, x0, y0, x1, y1, col, r=0):
        box = [self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)]
        if r:
            self.d.rounded_rectangle(box, radius=r * self.ws, fill=col)
        else:
            self.d.rectangle(box, fill=col)

    def ell(self, x, y, rx, ry, col, outline=None, w=0):
        X, Y, ws = self.X(x), self.Y(y), self.ws
        self.d.ellipse([X - rx * ws, Y - ry * ws, X + rx * ws, Y + ry * ws], fill=col,
                       outline=outline, width=max(1, int(w * ws)) if outline else 0)

    def ring(self, x, y, r, col, w):
        X, Y, ws = self.X(x), self.Y(y), self.ws
        self.d.ellipse([X - r * ws, Y - r * ws, X + r * ws, Y + r * ws], outline=col, width=max(2, int(w * ws)))

    def pie(self, x, y, r, a0, a1, col):
        X, Y, ws = self.X(x), self.Y(y), self.ws
        self.d.pieslice([X - r * ws, Y - r * ws, X + r * ws, Y + r * ws], a0, a1, fill=col)

    def poly(self, pts, col):
        self.d.polygon(self.P(pts), fill=col)

    def line(self, pts, col, w):
        self.d.line(self.P(pts), fill=col, width=max(1, int(w * self.ws)), joint="curve")

    def cap(self, p0, p1, r, col):
        self.line([p0, p1], col, 2 * r)
        for p in (p0, p1):
            self.ell(p[0], p[1], r, r, col)

    def text(self, x, y, txt, px, col, stroke=0, stroke_col=(0, 0, 0)):
        f = font(px * self.ws)
        self.d.text((self.X(x), self.Y(y)), txt, fill=col, anchor="mm", font=f,
                    stroke_width=int(stroke * self.ws), stroke_fill=stroke_col)


def rot(u, v, a):
    ca, sa = math.cos(a), math.sin(a)
    return u * ca - v * sa, u * sa + v * ca


def rrect_pts(cx, cy, w, h, a):
    return [(cx + p[0], cy + p[1]) for p in (rot(-w / 2, -h / 2, a), rot(w / 2, -h / 2, a),
                                              rot(w / 2, h / 2, a), rot(-w / 2, h / 2, a))]


def arrow_head(D, tip, ang, size, col):
    a1 = (tip[0] - size * math.cos(ang - 0.5), tip[1] - size * math.sin(ang - 0.5))
    a2 = (tip[0] - size * math.cos(ang + 0.5), tip[1] - size * math.sin(ang + 0.5))
    D.line([a1, tip, a2], col, size * 0.32)


# ------------------------------------------------------------------ Stick (le visage du dessin du fan)
def draw_stick(D, x, y, r, mood="calm", flash=0.0, arrows=True):
    """Stick : disque bleu marine cerclé de noir, disque intérieur plus clair, un œil plissé (à gauche),
    un œil ouvert (à droite), la bouche en coin ; des flèches courbes autour de lui (il colle)."""
    D.ell(x, y, r * 1.6, r * 1.6, dim(NAVY_O, 0.3))
    if arrows:
        k = 1.0 + 0.25 * flash
        col = mix(ARROW, (255, 255, 255), flash)
        w = r * (0.075 + 0.04 * flash)
        # flèche de gauche : monte puis se recourbe vers lui
        pts = [(x - r * 1.30 * k, y + r * 0.55), (x - r * 1.45 * k, y + r * 0.05), (x - r * 1.42 * k, y - r * 0.32),
               (x - r * 1.22 * k, y - r * 0.55), (x - r * 1.05, y - r * 0.40)]
        D.line(pts, col, w)
        arrow_head(D, pts[-1], math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0]), r * 0.28, col)
        # crochet en bas à droite
        pts2 = [(x + r * 0.62, y + r * 0.86), (x + r * 0.85, y + r * 1.25 * k), (x + r * 1.05, y + r * 1.45 * k),
                (x + r * 1.30 * k, y + r * 1.30 * k), (x + r * 1.30 * k, y + r * 0.95)]
        D.line(pts2, col, w)
        D.ell(x + r * 0.62, y + r * 0.86, r * 0.1, r * 0.08, col)
    D.ell(x, y, r, r, NAVY_O, outline=(0, 0, 0), w=r * 0.07)
    D.ell(x + r * 0.02, y - r * 0.02, r * 0.62, r * 0.62, NAVY_I)
    ink = (0, 0, 0)
    if mood == "startle":
        D.ell(x - r * 0.22, y - r * 0.08, r * 0.16, r * 0.24, (245, 245, 250))
        D.ell(x + r * 0.22, y - r * 0.08, r * 0.16, r * 0.24, (245, 245, 250))
        D.ell(x - r * 0.22, y - r * 0.06, r * 0.07, r * 0.1, ink)
        D.ell(x + r * 0.22, y - r * 0.06, r * 0.07, r * 0.1, ink)
        D.ell(x, y + r * 0.36, r * 0.13, r * 0.16, ink)
        return
    if mood == "strain":
        D.line([(x - r * 0.38, y - r * 0.02), (x - r * 0.06, y + r * 0.04)], ink, r * 0.11)
        D.line([(x + r * 0.06, y + r * 0.04), (x + r * 0.38, y - r * 0.02)], ink, r * 0.11)
        D.line([(x - r * 0.3, y + r * 0.38), (x - r * 0.1, y + r * 0.32), (x + r * 0.1, y + r * 0.38),
                (x + r * 0.3, y + r * 0.32)], ink, r * 0.06)
        return
    # œil plissé (gauche), œil ouvert (droite), bouche en coin qui part de sous l'œil gauche
    D.d.polygon(D.P([(x - r * 0.42 + r * 0.22 * math.cos(a) - 0.03 * r * math.sin(a) * 0,
                      y + r * 0.02 + r * 0.1 * math.sin(a) - r * 0.04 * math.cos(a) * 0)
                     for a in np.linspace(0, 2 * math.pi, 20)]), fill=ink)
    D.ell(x + r * 0.16, y - r * 0.14, r * 0.12, r * 0.24, ink)
    mouth = [(x - r * 0.52, y - r * 0.02), (x - r * 0.48, y + r * 0.26), (x - r * 0.30, y + r * 0.45),
             (x + r * 0.0, y + r * 0.52), (x + r * 0.30, y + r * 0.42), (x + r * 0.45, y + r * 0.2),
             (x + r * 0.42, y - r * 0.04)]
    D.line(mouth, ink, r * 0.07)


# ------------------------------------------------------------------ les objets
SIGN_IMG = {}


def sign_image(s):
    key = round(s, 4)
    if key not in SIGN_IMG:
        w, h, pad = int(SIGN_W * s), int(SIGN_H * s), int(10 * s)
        img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([pad, pad, pad + w, pad + h], radius=int(10 * s), fill=(30, 26, 24, 255))
        d.rounded_rectangle([pad + int(6 * s), pad + int(6 * s), pad + w - int(6 * s), pad + h - int(6 * s)],
                            radius=int(8 * s), fill=CREAM + (255,))
        d.text((pad + w / 2, pad + h / 2 + 2 * s), "QUIET", fill=INKC + (255,), anchor="mm", font=font(70 * s))
        SIGN_IMG[key] = img
    return SIGN_IMG[key]


def paste_rot(img, D, sprite, cx, cy, ang_deg):
    r = sprite.rotate(-ang_deg, resample=Image.BICUBIC, expand=True)
    img.paste(r, (int(D.X(cx) - r.width / 2), int(D.Y(cy) - r.height / 2)), r)


def draw_book(D, cx, cy, w, h, a, col):
    D.poly(rrect_pts(cx, cy, w + 6, h + 6, a), (22, 16, 14))
    D.poly(rrect_pts(cx, cy, w, h, a), col)
    for off in (-0.3, 0.3):
        p0 = (cx + rot(-w / 2 + 3, h * off, a)[0], cy + rot(-w / 2 + 3, h * off, a)[1])
        p1 = (cx + rot(w / 2 - 3, h * off, a)[0], cy + rot(w / 2 - 3, h * off, a)[1])
        D.line([p0, p1], dim(col, 0.65), 4)


def draw_open_book(D, cx, cy, a, col, scale=1.0):
    """Un livre ouvert vu de face (ce que tient le lecteur)."""
    w, h = 96 * scale, 64 * scale
    D.poly(rrect_pts(cx, cy, w + 8, h + 8, a), (22, 16, 14))
    D.poly(rrect_pts(cx, cy, w, h, a), col)
    D.poly(rrect_pts(cx + rot(-w / 4 + 2, 0, a)[0], cy + rot(-w / 4 + 2, 0, a)[1], w / 2 - 8, h - 10, a),
           (236, 230, 214))
    D.poly(rrect_pts(cx + rot(w / 4 - 2, 0, a)[0], cy + rot(w / 4 - 2, 0, a)[1], w / 2 - 8, h - 10, a),
           (226, 220, 204))


def draw_lamp(D, x, y, a):
    """Lampe de banquier : pied laiton, abat-jour vert. (x, y) = la base, a = inclinaison."""
    def P(u, v):
        q = rot(u, v, a)
        return (x + q[0], y + q[1])
    D.poly([P(-34, 0), P(34, 0), P(26, -12), P(-26, -12)], BRASS)
    D.line([P(0, -12), P(0, -70)], BRASS, 9)
    D.poly([P(-58, -64), P(58, -64), P(44, -100), P(-44, -100)], SHADE)
    D.poly([P(-50, -64), P(50, -64), P(46, -56), P(-46, -56)], (255, 238, 170))


def draw_desk(D, x0, x1, top, a=0.0, cx=None, cy=None):
    """Le bureau de prêt : plateau, façade, une pile de livres et un tampon."""
    if cx is None:
        cx, cy = (x0 + x1) / 2, top + (FL - top) / 2
    w, hh = x1 - x0, FL - top

    def P(u, v):
        q = rot(u, v, a)
        return (cx + q[0], cy + q[1])
    D.poly([P(-w / 2, -hh / 2), P(w / 2, -hh / 2), P(w / 2, hh / 2), P(-w / 2, hh / 2)], WOOD_D)
    D.poly([P(-w / 2 - 10, -hh / 2 - 14), P(w / 2 + 10, -hh / 2 - 14), P(w / 2 + 10, -hh / 2 + 6),
            P(-w / 2 - 10, -hh / 2 + 6)], WOOD_L)
    for k in range(3):
        u0 = -w / 2 + 16 + k * (w - 32) / 3
        D.poly([P(u0 + 6, -hh / 2 + 22), P(u0 + (w - 32) / 3 - 6, -hh / 2 + 22),
                P(u0 + (w - 32) / 3 - 6, hh / 2 - 16), P(u0 + 6, hh / 2 - 16)], WOOD)
    # livres sur le plateau
    for k, col in enumerate((BOOK_COLS[1], BOOK_COLS[4], BOOK_COLS[2])):
        D.poly([P(-w / 2 + 24, -hh / 2 - 14 - 24 * (k + 1)), P(-w / 2 + 120, -hh / 2 - 14 - 24 * (k + 1)),
                P(-w / 2 + 120, -hh / 2 - 14 - 24 * k - 2), P(-w / 2 + 24, -hh / 2 - 14 - 24 * k - 2)], col)


def draw_clock(D, x, y, a, t):
    D.ell(x, y, 50, 50, (30, 24, 22))
    D.ell(x, y, 42, 42, CREAM)
    for k in range(12):
        q = rot(0, -34, k * math.pi / 6 + a)
        D.ell(x + q[0], y + q[1], 3, 3, INKC)
    h = rot(0, -20, a + 1.9)
    m = rot(0, -32, a + t * 0.6)
    D.line([(x, y), (x + h[0], y + h[1])], INKC, 6)
    D.line([(x, y), (x + m[0], y + m[1])], INKC, 4)


def draw_chair(D, cx, cy, a, empty=True):
    """Fauteuil de velours vu de profil, tourné vers la gauche. (cx, cy) = centre de l'assise."""
    def P(u, v):
        q = rot(u, v, a)
        return (cx + q[0], cy + q[1])
    D.poly([P(10, -200), P(100, -210), P(110, 10), P(20, 20)], VELVET_D)            # dossier
    D.poly([P(-100, -20), P(100, -20), P(100, 40), P(-100, 40)], VELVET)            # assise
    D.poly([P(-110, -70), P(-70, -70), P(-70, 40), P(-110, 40)], VELVET_D)          # accoudoir
    D.ell(*P(-90, -70), 22, 14, VELVET)
    D.line([P(-92, 40), P(-96, 150)], WOOD_D, 14)
    D.line([P(92, 40), P(96, 150)], WOOD_D, 14)


# ------------------------------------------------------------------ objets : états et poses
STUCK_BLEND = 0.12


class Thing:
    """Un objet que Stick peut emporter. Segments : (t réel, mode, données). Modes : home, stuck, held, fly."""

    def __init__(self, name, home_fn, slot_ang, dist, slot_rot, home_rot=0.0):
        self.name = name
        self.home_fn = home_fn          # t -> (x, y)
        self.slot_ang = math.radians(slot_ang)
        self.dist = dist
        self.slot_rot = math.radians(slot_rot)
        self.home_rot = math.radians(home_rot)
        self.segs = [(-9.0, "home", None)]

    def at(self, t, mode, data=None):
        self.segs.append((t, mode, data))
        self.segs.sort(key=lambda s: s[0])
        return self


class Scene:
    def __init__(self):
        self.P = Plan()
        rng = np.random.default_rng(11)
        self.rows = []
        for r in range(4):
            yb = SHELF[2] + 120 * (r + 1)
            x = SHELF[0] + 16
            books = []
            while x < SHELF[1] - 10:
                w = float(rng.integers(28, 40))
                h = float(rng.integers(78, 104))
                books.append([x + w / 2, yb - h / 2 - 4, w, h, BOOK_COLS[int(rng.integers(0, len(BOOK_COLS)))]])
                x += w + 3
            self.rows.append(books)
        self.lib_books = self.rows[0][:4]          # la rangée qu'il emporte (rangée du haut, à gauche)
        self.build()

    # -------------------------------------------------------------- Bounce et Stick
    def bounce(self, t):
        tv = vt(t)
        x, y = self.P.pos(tv)
        sx, sy = self.P.squash(tv)
        return x, y, sx, sy

    def cluster_ang(self, t):
        """Le groupe penche selon la vitesse ; sous le tas (fausse fin), il s'affaisse sur la tête de Bounce."""
        tv = vt(t)
        _vx, vy = self.P.vel(tv)
        a = max(-0.14, min(0.14, -vy / 8000.0))
        heap = clamp01((t - FAKE_END + 0.05) / 0.25) * (1 - clamp01((t - REST_HIT) / 0.5))
        return a * (1 - heap) - 0.5 * heap

    def stuck_frame(self, t):
        """Centre de Stick quand il est collé à Bounce, et l'angle du groupe."""
        bx, by, _sx, sy = self.bounce(t)
        a = self.cluster_ang(t)
        ax, ay = rot(ATT[0], ATT[1], a)
        return bx + ax, by + ay + (1 - sy) * BR * 0.9, a

    def stick_pos(self, t):
        if t < 0.10:
            return STICK_WALL[0], STICK_WALL[1], 0.0
        if t < RELEASE:
            x, y, a = self.stuck_frame(t)
            k = smooth((t - 0.10) / 0.14)
            return lerp(STICK_WALL[0], x, k), lerp(STICK_WALL[1], y, k), a
        x0, y0, a0 = self.stuck_frame(RELEASE)
        x, y = arc(x0, y0, STICK_WALL, RELEASE, STICK_BACK, t, 60)
        return x, y, 0.0

    # -------------------------------------------------------------- les objets
    def build(self):
        self.things = []
        reader_hands = lambda t: self.reader_hands(t)
        b1 = Thing("book1", reader_hands, -4, 118, 86)
        b1.at(PICK["book1"], "stuck").at(RELEASE, "fly", (BOOK1_BACK, 50, 2.0))
        b2 = Thing("book2", lambda t: self.chair_pt(t, BOOK2_ARM) if (t < 4.95 or t > 60.0) else self.reader_hands(t),
                   24, 112, 114)
        b2.at(4.70, "home").at(PICK["book2"], "stuck").at(RELEASE, "fly", (BOOK2_BACK, 40, 1.0))
        self.book1, self.book2 = b1, b2
        self.row = []
        angs = [-112, -92, -72, -52]
        for i, bk in enumerate(self.lib_books):
            th = Thing("rb%d" % i, (lambda bk: (lambda t: (bk[0], bk[1])))(bk), angs[i], SRAD + bk[3] / 2 - 4,
                       angs[i] + 90)
            th.book = bk
            th.at(PICK["row"], "stuck").at(PEEL["row"][0], "held", i).at(PEEL["row"][1], "home")
            th.at(PICK["row2"], "stuck").at(RELEASE, "fly", (ROW_BACK + 0.07 * i, 50, 3.0))
            self.row.append(th)
        sg = Thing("sign", lambda t: (NAIL[0], NAIL[1] + SIGN_H / 2 + 18), -128, 128, -18)
        sg.at(PICK["sign"], "stuck").at(PEEL["sign"][0], "held", 0).at(PEEL["sign"][1], "home")
        sg.at(PICK["sign2"], "stuck").at(RELEASE, "fly", (SIGN_BACK, 50, 2.0))
        self.sign = sg
        ck = Thing("clock", lambda t: CLOCK_HOME, -22, 128, 0)
        ck.at(PICK["clock"], "stuck").at(RELEASE, "fly", (CLOCK_BACK, 40, -1.0))
        self.clock = ck
        ch = Thing("chair", lambda t: CHAIR_HOME, 14, 218, 14)
        ch.at(PICK["chair"], "stuck").at(RELEASE, "fly", (CHAIR_BACK, 30, 0.0))
        self.chair = ch
        self.things = [b1, b2, sg, ck, ch] + self.row

    def seg_of(self, th, t):
        i = max(0, bisect.bisect_right([s[0] for s in th.segs], t) - 1)
        return i, th.segs[i]

    def raw_pose(self, th, t, seg, idx):
        t0, mode, data = seg
        if mode == "home":
            x, y = th.home_fn(t)
            return x, y, th.home_rot
        if mode == "stuck":
            sx, sy, a = self.stick_pos(t)
            ang = th.slot_ang + a
            return sx + th.dist * math.cos(ang), sy + th.dist * math.sin(ang), th.slot_rot + a
        if mode == "held":
            hx, hy = self.lib_hold(t, th, data)
            return hx, hy, 0.0
        if mode == "fly":
            t1, lift, spins = data
            px, py, pa = self.pose(th, t0 - 1e-4, upto=idx)
            hx, hy = th.home_fn(t1)
            x, y = arc(px, py, (hx, hy), t0, t1, t, lift)
            u = clamp01((vt(t) - vt(t0)) / max(1e-6, vt(t1) - vt(t0)))
            ang = lerp(pa, th.home_rot + 2 * math.pi * spins, smooth(u))
            if th.name == "sign":
                ang = self.sign_swing(t, ang)
            return x, y, ang
        x, y = th.home_fn(t)
        return x, y, th.home_rot

    def pose(self, th, t, upto=None):
        idx, seg = self.seg_of(th, t)
        if upto is not None:
            idx = min(idx, upto - 1)
            seg = th.segs[idx]
        p = self.raw_pose(th, t, seg, idx)
        if seg[1] != "fly" and idx > 0 and t - seg[0] < STUCK_BLEND:
            q = self.raw_pose(th, seg[0], th.segs[idx - 1], idx - 1) if th.segs[idx - 1][1] != "fly" else \
                self.pose(th, seg[0] - 1e-4)
            k = smooth((t - seg[0]) / STUCK_BLEND)
            p = (lerp(q[0], p[0], k), lerp(q[1], p[1], k), lerp(q[2], p[2], k))
        if seg[1] == "home" and th.name == "sign":
            p = (p[0], p[1], self.sign_swing(t, p[2]))
        return p

    def sign_swing(self, t, ang):
        """Le panneau se balance sur son clou quand le tas passe tout près (« presque »), et à l'issue."""
        a = 0.0
        for (t0, amp) in SIGN_WOBBLE:
            u = vt(t) - vt(t0)
            if 0 <= u <= 2.0:
                a += amp * math.sin(u * 9.0) * math.exp(-u * 2.2)
        return ang + a

    # -------------------------------------------------------------- la bibliothécaire
    def lib_hold(self, t, th, i):
        (h1, h2) = self.lib_hands(t)
        cx, cy = (h1[0] + h2[0]) / 2, (h1[1] + h2[1]) / 2
        if th.name == "sign":
            return cx, cy - 50
        return cx - 45 + 30 * i, cy - 40

    def lib_free(self, t):
        """Ses pieds (x), son penché, ses mains (cibles), quand elle n'est pas collée."""
        x = LIB_X(t)
        lean = LIB_LEAN(t)
        return x, lean

    def lib_hands(self, t):
        J = self.lib_joints(t)
        return J["h1"], J["h2"]

    def lib_joints(self, t):
        """Articulations de la bibliothécaire (personnage sans visage). Debout : pieds au sol ; collée :
        mains sur Stick, le corps pend, genoux pliés quand le sol est proche."""
        inflate = LIB_INFL(t)
        trem = (3 + 8 * inflate) * math.sin(t * 70) if inflate > 0.05 else 0.0
        if LIB_STUCK <= t < RELEASE + 0.0001:
            sx, sy, a = self.stick_pos(t)
            ang = math.radians(LIB_SLOT) + a
            hx, hy = sx + (SRAD + 6) * math.cos(ang), sy + (SRAD + 6) * math.sin(ang)
            vx, _vy = self.P.vel(vt(t))
            sway = max(-50.0, min(50.0, -vx * 0.05))
            k_in = smooth((t - LIB_STUCK) / 0.25)
            fx = LIB_X(LIB_STUCK)
            if k_in < 1:
                # elle était debout, mains sur lui : son corps se fait soulever
                hx0, hy0 = self.lib_free_hands(LIB_STUCK)
                hx, hy = lerp(hx0[0], hx, k_in), lerp(hx0[1], hy, k_in)
            sh = (hx + 40 + sway * 0.3 + trem, hy + 110)
            hip = (sh[0] + 6 + sway, sh[1] + 200)
            leg = 250.0
            fy = min(FL, hip[1] + leg)
            d = fy - hip[1]
            fxx = hip[0] + sway * 0.4
            knee_out = math.sqrt(max(0.0, (leg / 2) ** 2 - (d / 2) ** 2))
            air = clamp01((FL - (hip[1] + leg)) / 60.0)
            pd = 34 * air * math.sin(t * 2 * math.pi * 2.4)
            J = {"sh": sh, "hip": hip, "f1": (fxx - 26 + pd, fy - abs(pd) * 0.6), "f2": (fxx + 26 - pd, fy - abs(pd) * 0.6),
                 "k1": (fxx - 26 - knee_out, hip[1] + d / 2), "k2": (fxx + 26 + knee_out * 0.6, hip[1] + d / 2),
                 "h1": (hx - 8, hy), "h2": (hx + 14, hy + 6),
                 "head": (sh[0] + 4 + 10 * inflate, sh[1] - 66), "lean": 0.0, "inflate": inflate, "dir": -1}
            if t >= SNAP - 0.45:    # elle craque : elle se redresse de toute sa taille, gonflée, tête en arrière
                k = smooth((t - SNAP + 0.45) / 0.35)
                bxx = hx + 120
                st = {"hip": (bxx, FL - 250), "sh": (bxx - 4, FL - 452), "f1": (bxx - 30, FL), "f2": (bxx + 30, FL),
                      "k1": (bxx - 26, FL - 125), "k2": (bxx + 26, FL - 125), "head": (bxx + 16, FL - 522)}
                for kk, v in st.items():
                    J[kk] = (lerp(J[kk][0], v[0] + trem * 0.5, k), lerp(J[kk][1], v[1], k))
            return J
        if t >= RELEASE:
            # elle tombe sous le panneau, bras écartés ; puis elle se fait toute petite
            J0 = self.lib_joints(RELEASE - 1e-4)
            hipx, hipy = arc(J0["hip"][0], J0["hip"][1], (LIB_LAND_X, FL - 250), RELEASE, LIB_BACK, t, 20)
            k = clamp01((vt(t) - vt(LIB_BACK)) / 0.2)
            shrink = smooth((t - 61.9) / 0.7) * 0.5
            hip = (hipx, hipy + 30 * shrink)
            sh = (hip[0], hip[1] - 200 + 40 * shrink)
            arms = 1 - shrink * 1.6
            J = {"sh": sh, "hip": hip, "f1": (hip[0] - 34, min(FL, hip[1] + 250)), "f2": (hip[0] + 34, min(FL, hip[1] + 250)),
                 "h1": (sh[0] - 150 * arms - 40 * (1 - arms), sh[1] - 120 * arms + 60 * (1 - arms)),
                 "h2": (sh[0] + 150 * arms + 40 * (1 - arms), sh[1] - 120 * arms + 60 * (1 - arms)),
                 "head": (sh[0], sh[1] - 66 + 20 * shrink), "lean": 0.0, "inflate": 0.0, "dir": -1}
            J["k1"] = ((J["f1"][0] + hip[0]) / 2 - 6, (J["f1"][1] + hip[1]) / 2)
            J["k2"] = ((J["f2"][0] + hip[0]) / 2 + 6, (J["f2"][1] + hip[1]) / 2)
            if shrink > 0:
                J["h1"] = (lerp(J["h1"][0], J["head"][0] - 20, shrink * 1.8), lerp(J["h1"][1], J["head"][1] + 30, shrink * 1.8))
            return J
        x = LIB_X(t)
        lean = LIB_LEAN(t)
        walk = LIB_WALK(t)
        ph = t * 2 * math.pi * 1.8
        bob = 6 * abs(math.sin(ph)) * walk
        hip = (x, FL - 250 - bob)
        sh = (x + lean, hip[1] - 200)
        fy = FL
        st = 30 * math.sin(ph) * walk
        J = {"hip": hip, "sh": sh, "f1": (x - 24 + st, fy), "f2": (x + 24 - st, fy),
             "head": (sh[0] + lean * 0.3, sh[1] - 66), "lean": lean, "inflate": inflate, "dir": LIB_DIR(t)}
        J["k1"] = ((J["f1"][0] + hip[0]) / 2 - 4, (J["f1"][1] + hip[1]) / 2)
        J["k2"] = ((J["f2"][0] + hip[0]) / 2 + 4, (J["f2"][1] + hip[1]) / 2)
        h1, h2 = self.lib_free_hands(t)
        J["h1"], J["h2"] = h1, h2
        return J

    def arm_target(self, mode, t):
        x, lean = LIB_X(t), LIB_LEAN(t)
        sh = (x + lean, FL - 450)
        if mode == "desk":
            stamp = 16 * max(0.0, math.sin(t * 6.5)) if t < 5.9 else 0.0
            return (sh[0] - 70, DESK[2] - 14 - stamp), (sh[0] + 46, DESK[2] - 8)
        if mode == "shock":
            return (sh[0] - 92, sh[1] - 70), (sh[0] + 92, sh[1] - 70)
        if mode == "finger":
            return (sh[0] - 46, sh[1] + 170), (sh[0] + 40, sh[1] - 140)
        if mode == "grab_row":
            p = self.pose(self.row[1], PEEL["row"][0] - 0.01)
            return (p[0] - 34, p[1] + 10), (p[0] + 34, p[1] + 10)
        if mode == "carry":
            return (sh[0] - 34, sh[1] + 70), (sh[0] + 34, sh[1] + 70)
        if mode == "shelve":
            return (SHELF[0] + 36, ROW1_Y - 50), (SHELF[0] + 104, ROW1_Y - 50)
        if mode == "point":
            return (sh[0] - 46, sh[1] + 170), (SIGN_C[0] + 40, SIGN_C[1] + 50)
        if mode == "grab_sign":
            p = self.pose(self.sign, PEEL["sign"][0] - 0.01)
            return (p[0] - 70, p[1] + 30), (p[0] + 70, p[1] + 30)
        if mode == "hang_sign":
            return (NAIL[0] - 70, NAIL[1] + 100), (NAIL[0] + 70, NAIL[1] + 100)
        if mode == "push":
            p = self.stick_pos(LIB_STUCK)
            return (p[0] + 72, p[1] - 6), (p[0] + 86, p[1] + 14)
        if mode == "slump":
            return (sh[0] - 34, sh[1] + 200), (sh[0] + 34, sh[1] + 200)
        return (sh[0] - 48, sh[1] + 175), (sh[0] + 48, sh[1] + 175)

    def lib_free_hands(self, t):
        ts = [m[0] for m in LIB_ARMS]
        i = max(0, bisect.bisect_right(ts, t) - 1)
        cur = self.arm_target(LIB_ARMS[i][1], t)
        if i > 0:
            k = smooth((t - LIB_ARMS[i][0]) / 0.28)
            if k < 1:
                prev = self.arm_target(LIB_ARMS[i - 1][1], t)
                cur = tuple((lerp(p[0], c[0], k), lerp(p[1], c[1], k)) for p, c in zip(prev, cur))
        if LIB_WALK(t) > 0.05 and LIB_ARMS[i][1] == "rest":
            sw = 22 * math.sin(t * 2 * math.pi * 1.8) * LIB_WALK(t)
            cur = ((cur[0][0] + sw, cur[0][1]), (cur[1][0] - sw, cur[1][1]))
        return cur[0], cur[1]

    # -------------------------------------------------------------- le lecteur
    def chair_pt(self, t, p):
        """Un point lié au fauteuil (coordonnées données fauteuil à sa place), où qu'il soit."""
        cx, cy, a = self.pose(self.chair, t)
        u, v = rot(p[0] - CHAIR_HOME[0], p[1] - CHAIR_HOME[1], a - self.chair.home_rot)
        return cx + u, cy + v

    def reader_joints(self, t):
        """Le lecteur, assis dans son fauteuil, lit. Quand le fauteuil part, il part avec, toujours assis."""
        base_ = {"hip": (846.0, 968.0), "sh": (838.0, 850.0), "head": (832.0, 796.0), "k1": (768.0, 976.0),
                 "k2": (774.0, 984.0), "f1": (762.0, 1110.0), "f2": (774.0, 1112.0)}
        look = 0.0
        for (a_, b_) in ((2.85, 4.45), (28.45, 30.6)):
            if a_ <= t < b_ + 0.3:
                look = max(look, smooth((t - a_) / 0.3) * (1 - smooth((t - b_) / 0.3)))
        J = {k: self.chair_pt(t, v) for k, v in base_.items()}
        hx = self.reader_hands(t)
        J["h1"] = (hx[0] - 22, hx[1] + 6)
        J["h2"] = (hx[0] + 22, hx[1] + 6)
        J["head"] = (J["head"][0] + 6 * look, J["head"][1] + 14 * look)
        turn = smooth((t - 60.75) / 0.3) if t > 60.75 else 0.0
        J["head"] = (J["head"][0] - 10 * turn, J["head"][1] - 4 * turn)
        J["turn"] = turn
        if SNAP <= t < RELEASE + 0.4:        # le cri : il sursaute dans son fauteuil
            J["head"] = (J["head"][0], J["head"][1] - 16 * math.sin(math.pi * clamp01((t - SNAP) / 0.6)))
        return J

    def reader_hands(self, t):
        h = READER_HANDS
        if PICK["book1"] <= t < 4.5 or PICK["book2"] <= t < 60.3:
            h = (READER_HANDS[0] + 6, READER_HANDS[1] + 4)        # il tient… rien
        elif 4.5 <= t < 4.95:
            k = math.sin(math.pi * (t - 4.5) / 0.45)
            h = (lerp(READER_HANDS[0], BOOK2_ARM[0], k), lerp(READER_HANDS[1], BOOK2_ARM[1], k))
        return self.chair_pt(t, h)


def arc(x0, y0, home, t0, t1, t, lift):
    """Vol en arc (temps de l'image) de (x0, y0) à home, entre t0 et t1."""
    a, b = vt(t0), vt(t1)
    u = clamp01((vt(t) - a) / max(1e-6, b - a))
    x = lerp(x0, home[0], u)
    y = lerp(y0, home[1], u) - lift * 4 * u * (1 - u)
    return x, y


# ------------------------------------------------------------------ personnages sans visage
def draw_lib(D, J, t):
    """La bibliothécaire : gilet prune, jupe, chignon et crayon ; aucun visage, tout passe par le corps."""
    infl = J.get("inflate", 0.0)
    w_t = 64 * (1 + 0.45 * infl)
    leg_c, shoe = (52, 40, 60), (30, 24, 34)
    for f, k in (("f1", "k1"), ("f2", "k2")):
        D.cap(J["hip"], J[k], 15, leg_c)
        D.cap(J[k], J[f], 13, leg_c)
        D.ell(J[f][0] - 8 * J["dir"], J[f][1] - 6, 22, 11, shoe)
    hip, sh = J["hip"], J["sh"]
    # jupe
    D.poly([(hip[0] - 54, hip[1] + 70), (hip[0] + 54, hip[1] + 70), (hip[0] + 40, hip[1] - 30),
            (hip[0] - 40, hip[1] - 30)], LIB_SKIRT)
    # buste (gilet)
    ux, uy = sh[0] - hip[0], sh[1] - hip[1]
    n = math.hypot(ux, uy) + 1e-6
    px, py = -uy / n, ux / n
    pts = [(hip[0] + px * w_t * 0.8, hip[1] + py * w_t * 0.8), (sh[0] + px * w_t, sh[1] + py * w_t),
           (sh[0] - px * w_t, sh[1] - py * w_t), (hip[0] - px * w_t * 0.8, hip[1] - py * w_t * 0.8)]
    D.poly(pts, LIB)
    D.ell(sh[0], sh[1], w_t, 34 * (1 + 0.3 * infl), LIB)
    D.line([((sh[0] + hip[0]) / 2, (sh[1] + hip[1]) / 2 - 60), ((sh[0] + hip[0]) / 2, (sh[1] + hip[1]) / 2 + 80)],
           LIB_D, 5)
    # tête, chignon, crayon
    hx, hy = J["head"]
    hr = 46 * (1 + 0.25 * infl)
    d = J["dir"]
    D.ell(hx, hy, hr, hr, SKIN)
    D.pie(hx, hy, hr, 180, 360, HAIR)
    bx, by = hx - d * hr * 0.75, hy - hr * 0.7
    D.line([(bx - 6, by - 4), (bx + 30 * -d, by - 52)], (240, 200, 70), 7)
    D.ell(bx, by, hr * 0.45, hr * 0.42, HAIR)
    D.ell(hx + d * hr * 0.95, hy + 6, hr * 0.16, hr * 0.14, SKIN)
    # bras
    for hnd, shx in ((J["h1"], -1), (J["h2"], 1)):
        s0 = (sh[0] + shx * w_t * 0.75, sh[1] + 10)
        D.cap(s0, hnd, 13, LIB_D)
        D.ell(hnd[0], hnd[1], 15, 15, SKIN)


def draw_reader(D, J, t):
    """Le lecteur, assis de profil vers la gauche : pull bleu-vert, tête ronde ; aucun visage."""
    pants, shoe = (60, 56, 80), (30, 26, 30)
    for f, k in (("f1", "k1"), ("f2", "k2")):
        D.cap(J["hip"], J[k], 22, pants)
        D.cap(J[k], J[f], 18, pants)
        D.ell(J[f][0] - 16, J[f][1] - 6, 28, 12, shoe)
    D.cap(J["hip"], J["sh"], 52, READ_B)
    hx, hy = J["head"]
    D.ell(hx, hy, 44, 44, READ_SK)
    D.pie(hx, hy, 44, 200, 380, (44, 30, 26))
    D.ell(hx - 40, hy + 8, 9, 8, READ_SK)
    sh = J["sh"]
    for hnd in (J["h2"], J["h1"]):
        D.cap((sh[0] - 10, sh[1] + 20), hnd, 15, READ_D)
        D.ell(hnd[0], hnd[1], 14, 14, READ_SK)


# ------------------------------------------------------------------ le décor
def draw_room(D, sc, t):
    D.rect(0, 0, W, FL, WALL)
    D.rect(0, 0, W, 186, WALL_D)
    D.rect(0, 180, W, 196, WALL_L)
    for k in range(9):
        x = 60 + k * 135
        D.rect(x, 196, x + 4, 880, WALL_D)
    D.rect(0, 880, W, FL, WALL_D)
    D.rect(0, 876, W, 892, WALL_L)
    for k in range(8):
        x = 30 + k * 140
        D.rect(x, 912, x + 110, FL - 24, (40, 27, 23), r=6)
    # suspensions (décor, dans la bande de l'accroche)
    for x in (250.0, 830.0):
        D.line([(x, 0), (x, 120)], (90, 80, 70), 4)
        D.poly([(x - 44, 150), (x + 44, 150), (x + 26, 116), (x - 26, 116)], (40, 120, 80))
        D.ell(x, 152, 30, 8, (255, 230, 160))
    # parquet, tapis
    D.rect(0, FL, W, H, FLOOR_C)
    y = FL + 14
    k = 0
    while y < H:
        D.rect(0, y, W, y + 3, FLOOR_L)
        y += 26 + 6 * k
        k += 1
    D.ell(540, 1255, 470, 70, RUG)
    D.ell(540, 1255, 420, 56, RUG_L)
    D.ell(540, 1255, 360, 42, RUG)


def draw_shelf(D, sc, t, held_ids):
    x0, x1, top = SHELF
    D.rect(x0 - 16, top - 24, x1, FL, WOOD_D)
    D.rect(x0, top, x1, FL, (40, 26, 20))
    for r in range(5):
        yb = top + 120 * r
        D.rect(x0 - 16, yb - 6, x1, yb + 8, WOOD)
    jolt = 0.0
    for (t0, amp) in SHELF_JOLT:
        u = vt(t) - vt(t0)
        if 0 <= u <= 0.5:
            jolt = max(jolt, amp * math.sin(u * 30) * (1 - u / 0.5))
    for r, books in enumerate(sc.rows):
        for j, b in enumerate(books):
            if r == 0 and j < len(sc.lib_books):
                continue
            jj = jolt * (1 if (j + r) % 2 else -0.6)
            D.rect(b[0] - b[2] / 2, b[1] - b[3] / 2 - abs(jj), b[0] + b[2] / 2, b[1] + b[3] / 2 - abs(jj), b[4])
            D.rect(b[0] - b[2] / 2 + 4, b[1] - b[3] * 0.25 - abs(jj), b[0] + b[2] / 2 - 4, b[1] - b[3] * 0.18 - abs(jj),
                   dim(b[4], 0.6))
    D.rect(x0 - 16, top - 30, x1, top - 14, WOOD_L)


def draw_desk_all(D, t):
    x0, x1, top = DESK
    D.rect(x0 - 10, top - 14, x1 + 10, top + 6, WOOD_L)
    D.rect(x0, top + 6, x1, FL, WOOD_D)
    for k in range(3):
        u0 = x0 + 14 + k * (x1 - x0 - 28) / 3
        D.rect(u0 + 6, top + 26, u0 + (x1 - x0 - 28) / 3 - 6, FL - 18, WOOD, r=4)
    for k, col in enumerate((BOOK_COLS[1], BOOK_COLS[4], BOOK_COLS[2])):
        D.rect(x0 + 20, top - 14 - 22 * (k + 1), x0 + 118 - 8 * k, top - 14 - 22 * k - 2, col)
    draw_lamp(D, LAMP_HOME[0], top - 14, 0.0)


def draw_pouf(D, name, bx, by, bry):
    cx, top, hw = POUFS[name]
    col = POUF_C[name]
    pts = []
    n = 40
    for i in range(n + 1):
        x = cx - hw + 2 * hw * i / n
        y = top + 8 * (1 - ((x - cx) / hw) ** 2) * 0 - 10 * (1 - ((x - cx) / hw) ** 2)
        dxb = x - bx
        if abs(dxb) < BR * 1.02:
            cy = by + math.sqrt(max(0.0, (BR * 1.02) ** 2 - dxb * dxb))
            y = max(y, min(FL - 20, cy))
        pts.append((x, y))
    D.poly(pts + [(cx + hw + 6, FL), (cx - hw - 6, FL)], col)
    D.line(pts, dim(col, 0.7), 5)
    D.line([(cx - hw * 0.7, FL - 26), (cx + hw * 0.7, FL - 26)], dim(col, 0.75), 4)


# caméra : le monde est zoomé (personnages plus gros), le parquet tombe vers y = 1224 à l'écran
CAM_K = 1.25
CAM_OX = 120.0
CAM_OY = 232.0


def draw_foreground(D, t):
    """Premier plan sombre (décor non essentiel, sous la zone de l'action) : le bord d'une grande table de
    lecture, deux lampes allumées, des livres, une tasse à crayons."""
    top = 1385.0
    D.rect(-100, top, 1300, 2100, (40, 26, 20))
    D.rect(-100, top - 18, 1300, top + 6, (78, 52, 36))
    for k in range(7):
        D.rect(-100, top + 40 + 58 * k, 1300, top + 44 + 58 * k, (48, 32, 25))
    for lx in (230.0, 860.0):
        D.ell(lx, top - 60, 150, 80, (58, 42, 30))
        D.line([(lx, top - 18), (lx, top - 120)], (150, 120, 60), 12)
        D.poly([(lx - 74, top - 110), (lx + 74, top - 110), (lx + 48, top - 160), (lx - 48, top - 160)], (30, 96, 64))
        D.ell(lx, top - 108, 64, 10, (240, 220, 150))
    for k, col in enumerate(((140, 54, 50), (50, 90, 140), (170, 140, 60), (90, 120, 80))):
        D.rect(600 + 6 * k, top - 18 - 26 * (k + 1), 760 - 10 * k, top - 18 - 26 * k - 2, dim(col, 0.85))
    D.poly([(380, top - 14), (540, top - 14), (556, top - 4), (364, top - 4)], (210, 200, 176))
    D.line([(460, top - 14), (460, top - 4)], (150, 140, 120), 3)
    D.rect(320, top - 70, 350, top - 18, (120, 90, 140), r=4)
    for k in range(3):
        D.line([(326 + 9 * k, top - 70), (322 + 14 * k, top - 104)], ((230, 190, 60), (200, 80, 70), (80, 140, 200))[k], 5)


SHELF_JOLT = [(28.30, 6), (32.85, 9), (40.30, 7), (50.05, 9), (58.10, 9), (58.95, 13), (59.75, 16)]


# ------------------------------------------------------------------ simulation (horloge d'événements)
DEFAULTS = {
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 88, "hook_length": 0.59,
    "narrator_voice": "am_puck", "narrator_length": 1.0, "narr_gap_s": 0.0,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
EXPR = [(0.10, 0.9, "shock"), (LIB_STUCK, 22.3, "shock"), (40.0, 42.1, "shock"), (FAKE_END, REST_HIT, "lose"),
        (REST_HIT, 50.0, "shock"), (SNAP, ISSUE + 0.05, "shock"), (ISSUE + 0.05, 99.0, "win")]
STICK_MOOD = [(40.0, 42.1, "strain"), (FAKE_END, REST_HIT + 0.1, "strain"), (54.3, 56.45, "strain"),
              (SNAP + 0.12, RELEASE + 1.6, "startle")]


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
        self.subs = []

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
        for (th, g, _x, _y) in self.sc.P.hits:
            if abs(th - t0) < bd:
                best, bd = g, abs(th - t0)
        return best

    def set_narr(self, narr):
        out = []
        for i, n in enumerate(narr):
            words = len(n["text"].split())
            end = max(n["end"] + 0.3, n["start"] + 0.5 + 0.3 * words)
            if i + 1 < len(narr):
                end = min(end, narr[i + 1]["start"] - 0.05)
            out.append((WHO.get(n["key"], "lib"), n["text"], n["start"], end, n["key"]))
        self.subs = out

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        sc = self.sc
        s = S * self.cfg["width"] / W
        img = dr._image
        # le cri secoue l'image
        shake = 0.0
        if SNAP <= t < SNAP + 0.7:
            shake = 7 * math.sin(t * 95) * (1 - (t - SNAP) / 0.7)
        D = Dr(dr, s, CAM_K, CAM_OX + shake, CAM_OY + shake * 0.6)
        self.D = D
        draw_room(D, sc, t)
        draw_shelf(D, sc, t, None)
        D.ell(NAIL[0], NAIL[1], 7, 7, (200, 200, 210))
        mode = {th.name: sc.seg_of(th, t)[1][1] for th in sc.things}
        for th in sc.things:
            if mode[th.name] == "home" and th.name not in ("book1", "book2", "chair"):
                self.draw_thing(D, img, th, t)
        chair_home = mode["chair"] == "home"
        if chair_home:
            self.draw_chair_unit(D, img, t, mode)
        LJ = sc.lib_joints(t)
        lib_hanging = LIB_STUCK <= t < LIB_BACK
        behind_desk = t < 5.95
        if behind_desk:
            draw_lib(D, LJ, t)
        draw_desk_all(D, t)
        bx, by, sx, sy = sc.bounce(t)
        lib_front = not behind_desk and not lib_hanging and abs(LJ["sh"][0] - bx) > 150
        if not behind_desk and not lib_hanging and not lib_front:
            draw_lib(D, LJ, t)
        for name in ("p1", "p2"):
            draw_pouf(D, name, bx, by + (1 - sy) * BR, BR * sy)
        stx, sty, _a = sc.stick_pos(t)
        D.ell(stx, sty, SRAD * 1.6, SRAD * 1.6, dim(NAVY_O, 0.3))
        if not chair_home:
            self.draw_chair_unit(D, img, t, mode)
        self.draw_rings(D, t)
        base.HERO["expr"] = self.expr_at(t)
        ycen = by + (1 - sy) * BR
        if abs(sx - 1) < 0.004 and abs(sy - 1) < 0.004:
            base.ball(dr, D.X(bx), D.Y(ycen), BR * D.ws)
        else:
            self.draw_ball(dr, D.X(bx), D.Y(ycen), BR * sx, BR * sy, D.ws)
        lib_last = SNAP - 0.45 <= t < LIB_BACK + 0.2
        if (lib_hanging or lib_front) and not lib_last:
            draw_lib(D, LJ, t)
        for th in sc.things:
            if mode[th.name] != "home" and th.name != "chair":
                self.draw_thing(D, img, th, t)
        fl = 0.0
        for tp in list(PICK.values()) + [0.10, LIB_STUCK]:
            u = t - tp
            if 0 <= u <= 0.45:
                fl = max(fl, 1 - u / 0.45)
        smood = "calm"
        for (a_, b_, m) in STICK_MOOD:
            if a_ <= t < b_:
                smood = m
        draw_stick(D, stx, sty, SRAD, smood, fl, arrows=not (SNAP + 0.12 <= t < STICK_BACK))
        if lib_last:                 # le cri : elle passe devant tout le monde
            draw_lib(D, LJ, t)
        if SNAP - 0.05 <= t < SNAP + 0.9:
            self.draw_shout(D, LJ, t)
        self.draw_bursts(D, t)
        draw_foreground(D, t)
        self.draw_subs(Dr(dr, s), t)

    def draw_bursts(self, D, t):
        """Un éclat blanc là où une chose vient de coller : la prise se voit, même petite."""
        sc = self.sc
        spots = []
        for name, tp in PICK.items():
            if 0 <= t - tp <= 0.4:
                th = {"book1": sc.book1, "book2": sc.book2, "row": sc.row[1], "row2": sc.row[1], "sign": sc.sign,
                      "sign2": sc.sign, "clock": sc.clock, "chair": sc.chair}[name]
                x, y, _a = sc.pose(th, tp + 0.13)
                spots.append((tp, x, y, 1.3 if name == "chair" else 1.0))
        if 0 <= t - LIB_STUCK <= 0.4:
            J = sc.lib_joints(LIB_STUCK + 0.3)
            spots.append((LIB_STUCK, J["h1"][0], J["h1"][1], 1.0))
        for (tp, x, y, k) in spots:
            u = (t - tp) / 0.4
            for i in range(10):
                ang = i * math.pi / 5 + 0.3
                r0 = (40 + 70 * u) * k
                r1 = r0 + 34 * (1 - u) * k
                D.line([(x + r0 * math.cos(ang), y + r0 * math.sin(ang)), (x + r1 * math.cos(ang), y + r1 * math.sin(ang))],
                       mix((255, 255, 255), ARROW, u), 9 * (1 - u) + 2)

    def draw_shout(self, D, J, t):
        """Le cri se voit : des traits qui jaillissent de sa tête."""
        hx, hy = J["head"]
        u = (t - SNAP + 0.05) / 0.95
        k = math.sin(math.pi * clamp01(u))
        for i in range(9):
            ang = -math.pi * (0.1 + 0.8 * i / 8) + 0.05 * math.sin(t * 40 + i)
            r0 = 70 + 30 * k
            r1 = r0 + 70 * k + 10 * math.sin(t * 50 + i * 2)
            D.line([(hx + r0 * math.cos(ang), hy + r0 * math.sin(ang)),
                    (hx + r1 * math.cos(ang), hy + r1 * math.sin(ang))], (255, 240, 200), 9)

    def draw_chair_unit(self, D, img, t, mode):
        """Le fauteuil, le lecteur assis dedans, ses livres ; un seul bloc (il part avec quand Stick le prend)."""
        sc = self.sc
        cx, cy, a = sc.pose(sc.chair, t)
        draw_chair(D, cx, cy, a)
        if mode["book2"] == "home" and (t < 4.7 or t > 60.0):
            x, y, ab = sc.pose(sc.book2, t)
            draw_book(D, x, y + 14, 90, 30, a, (60, 110, 190))
        J = sc.reader_joints(t)
        draw_reader(D, J, t)
        for th, col in ((sc.book1, (190, 60, 56)), (sc.book2, (60, 110, 190))):
            if mode[th.name] == "home" and not (th.name == "book2" and (t < 4.7 or t > 60.0)):
                if th.name == "book1" and PICK["book1"] <= t < BOOK1_BACK:
                    continue
                x, y, ab = sc.pose(th, t)
                draw_open_book(D, x, y - 8, a, col)
        # l'accoudoir, devant lui
        p0 = sc.chair_pt(t, (CHAIR_HOME[0] - 90, CHAIR_HOME[1] - 70))
        pts = [sc.chair_pt(t, (CHAIR_HOME[0] + u, CHAIR_HOME[1] + v)) for (u, v) in
               ((-110, -70), (-70, -70), (-70, 40), (-110, 40))]
        D.poly(pts, VELVET_D)
        D.ell(p0[0], p0[1], 22, 14, VELVET)

    def draw_thing(self, D, img, th, t):
        sc = self.sc
        x, y, a = sc.pose(th, t)
        if th.name.startswith("rb"):
            b = th.book
            draw_book(D, x, y, b[2], b[3], a, b[4])
        elif th.name == "sign":
            i, seg = sc.seg_of(th, t)
            hung = seg[1] == "home" or (seg[1] == "fly" and t >= SIGN_BACK)
            if hung:
                c1 = (x + rot(-SIGN_W / 2 + 20, -SIGN_H / 2, a)[0], y + rot(-SIGN_W / 2 + 20, -SIGN_H / 2, a)[1])
                c2 = (x + rot(SIGN_W / 2 - 20, -SIGN_H / 2, a)[0], y + rot(SIGN_W / 2 - 20, -SIGN_H / 2, a)[1])
                D.line([c1, NAIL, c2], (180, 170, 150), 4)
            paste_rot(img, D, sign_image(D.ws), x, y, math.degrees(a))
        elif th.name == "clock":
            draw_clock(D, x, y, a, t)
        elif th.name == "book1":
            draw_open_book(D, x, y, a, (190, 60, 56))
        elif th.name == "book2":
            draw_open_book(D, x, y, a, (60, 110, 190))

    def draw_rings(self, D, t):
        tv = vt(t)
        for (th, g, x, y) in self.sc.P.hits:
            u = tv - vt(th)
            if u < 0 or u > 0.5:
                continue
            r = BR + 14 + 700 * u
            rmax = BR + 60 + 160 * g
            if r > rmax:
                continue
            k = 1 - (r - BR) / max(1.0, rmax - BR)
            col = mix(WALL, (250, 248, 255), 0.5 + 0.5 * k)
            D.ring(x, Y_FLOOR, r, col, (8 + 8 * min(1.3, g)) * k)

    def draw_ball(self, dr, X, Y, rx, ry, ws):
        """Bounce écrasé : dessiné par base.ball sur un calque, puis déformé. (X, Y) en pixels de sortie."""
        r = max(rx, ry)
        size = int(2 * r * 1.7 * ws) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        pos = base.HERO["pos"]
        base.ball(ld, size / 2, size / 2, BR * ws)
        base.HERO["pos"] = pos
        nw, nh = max(2, int(size * rx / BR)), max(2, int(size * ry / BR))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        dr._image.paste(layer, (int(X - nw / 2), int(Y - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (X, Y)

    def expr_at(self, t):
        for (a, b, e) in EXPR:
            if a <= t < b:
                return e
        for (th, g, _x, _y) in self.sc.P.hits:
            if g >= 1.2 and 0 <= t - th < 0.5:
                return "shock"
        return "calm"

    def draw_subs(self, D, t):
        """Répliques sous-titrées (≥ 48 px, y 1000–1260), une à la fois, dans la couleur de qui parle."""
        for (who, text, a, b, key) in self.subs:
            if not (a <= t <= b):
                continue
            k = clamp01((t - a) / 0.1)
            big = key == "l_snap"
            fs = (130 if big else 76) * (0.8 + 0.2 * k)
            txt = text.replace("...", "…")
            f = font(fs)
            w = f.getlength(txt) + 60
            h = fs * 1.35
            cy = 1222.0 if not big else 1200.0
            fill = (60, 70, 200) if who == "stick" else (130, 70, 150)
            D.rect(540 - w / 2 - 4, cy - h / 2 - 4, 540 + w / 2 + 4, cy + h / 2 + 4, (16, 14, 18), r=h / 2.2)
            D.rect(540 - w / 2, cy - h / 2, 540 + w / 2, cy + h / 2, fill, r=h / 2.2)
            D.text(540, cy + 2, txt, fs, (255, 255, 255))


# ------------------------------------------------------------------ audio, rendu
def fft_reverb(x, sr, tail_s=0.7, wet=0.35, seed=7):
    """Réverbération par convolution FFT (même principe que base.reverb, sans np.convolve lent)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    N = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


def exact_events(sim):
    return [(t, "hit", "h%d" % i) for i, (t, g, x, y) in enumerate(sim.sc.P.hits)]


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
            gg = max(0.1, min(1.4, g)) ** 0.7 * 0.92
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
    for n in narr:
        x = n["audio"]
        if n["key"] == "l_snap":
            x = fft_reverb(x, SR, 0.9, 0.3)
        ak.add(buf, x, n["start"], gain=LINE_GAIN.get(n["key"], 1.2 if n["key"].startswith("s_") else 1.0))
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
