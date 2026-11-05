"""
« hideseek » v3 : cache-cache dans un salon de nuit, en un seul plan fixe. Crush (perso de fan)
cherche ; il ne bouge que quand un anneau de son part d'un contact dur de Bounce, et il bondit
vers lui. Sur le mou (pouf, coussins, paillasson, le coussin resté sur la tête de Crush), Bounce
est muet et Crush est perdu. Ils se ratent de plus en plus près (le dossier, un croisement en
l'air, un second au ralenti), Crush ressort du siège coiffé d'un coussin, et Bounce finit par se
poser dessus : sur la tête du chercheur. Crush saute vers le bruit, qui vient de sa propre tête ;
Bounce glisse vers ses yeux ; puis le silence, Crush abandonne et passe la porte, et Bounce, qui
passait de justesse sous la poutre, rebondit dedans : « Bounce ». Trouvé.

Nouveau fichier : rien n'est modifié dans le moteur. Les dessins des persos de fans viennent des
scripts publiés (cfg["draw_from"]), leurs voix de banques hors dépôt (cfg["voices"]).

    python3 src/stories/hideseek_v3.py configs/hideseek_v3.json [--simulate]
"""
import math, sys, os, wave, importlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import base
from base import font
from PIL import Image, ImageDraw
import voice as narr_voice
import audio_kit as ak

ORIG = {"say": narr_voice.say, "sub": base.subtitle_at, "narr": base.build_narration,
        "word": base.hero_word, "audio": base.render_audio}
SR = ak.SR
BANK = {}
M = {}


# ------------------------------------------------------------------ voix et son
def _read(path, gain=1.0):
    with wave.open(path) as w:
        n, fr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
    return x * 0.2 * gain


def say(text, voice=None, length_scale=None, sr=SR):
    if text.startswith("@"):
        return BANK[text].copy()
    return ORIG["say"](text, voice or narr_voice.DEFAULT_VOICE, length_scale, sr)


def subtitle_at(narr, t, n):
    return ORIG["sub"]([x for x in narr if not x["text"].startswith("@")], t, n)


_memo = {}


def steady_word(text, cfg):
    """Même mot, même longueur pour tout le processus : un tirage court de « Bounce »."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _memo:
        best = None
        for _ in range(12):
            v = ORIG["word"](text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.70:
                break
        _memo[key] = best
    return None if _memo[key] is None else _memo[key].copy()


def render_audio(events, total_dur, cfg, path, payoff_t=None, mood=None, narr=(), replies=()):
    """Comme le moteur, sans réverbération (rien ici n'en a besoin) : « Bounce » à chaque
    contact dur, les répliques, « Oh no. » à la fin, la voix de l'accroche par-dessus."""
    sr = SR
    buf = np.zeros(int((total_dur + 2.0) * sr))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        react = None
        if payoff_t is not None and mood in ("win", "lose"):
            react = base.hero_word(cfg["hero_win"] if mood == "win" else cfg["hero_lose"], cfg)
        words = base.place_words(events, total_dur, cfg, payoff_t, mood if react is not None else None, narr, replies,
                                 name_len=len(name) / sr, react_len=(len(react) / sr if react is not None else 0.8))
        for (t0, kind, _d, tag) in words:
            if kind == "hit":
                ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=cfg["hero_gain"])
            elif kind == "react":
                ak.add(buf, react, t0, gain=1.0)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=1.0)
    if cfg["hook_voice"] and cfg["hook_text"]:
        v = cfg.get("_hook_voice")
        if v is None:
            v = base.hook_audio(cfg)
        if v is not None:
            n = min(len(v), len(buf))
            duck = np.ones(len(buf))
            duck[:n] = 0.42
            duck[n:n + int(0.3 * sr)] = np.linspace(0.42, 1.0, min(int(0.3 * sr), len(buf) - n))
            buf *= duck
            ak.add(buf, v, 0.15, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said, "reaction": mood}


def install():
    narr_voice.say = say
    base.subtitle_at = subtitle_at
    base.hero_word = steady_word
    base.render_audio = render_audio


install()


def load_modules(paths):
    if M:
        return
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
    for name in ("clip4", "blub"):
        M[name] = importlib.import_module(name)
    narr_voice.say, base.subtitle_at, base.build_narration = ORIG["say"], ORIG["sub"], ORIG["narr"]
    base.hero_word, base.render_audio = ORIG["word"], ORIG["audio"]
    install()


# ------------------------------------------------------------------ le salon (coordonnées image)
W, H = 1080, 1920
G = 2600.0
RB, RC = 95.0, 120.0           # Bounce, Crush
FL = 1150.0                    # sol
CEIL = 240.0
WALL_X0, WALL_X1 = 100.0, 200.0   # mur de gauche (épais) ; la porte est dessous
LINTEL = 692.0                 # bas de la poutre au-dessus de la porte
MAT = (205.0, 440.0, 12.0)     # paillasson : x0, x1, épaisseur
ARM = (380.0, 410.0, 935.0)    # accoudoir : x0, x1, dessus (bois : dur)
SEAT = (410.0, 600.0, 960.0, 1015.0)   # coussins : x0, x1, dessus, dessous
BACK = (600.0, 645.0, 790.0)   # dossier : x0, x1, sommet
POUF = (650.0, 760.0, 1090.0)  # pouf : x0, x1, dessus
RWALL = 875.0

# centres de Crush posé
CY_FLOOR = FL - RC              # 1030
CY_SEAT = SEAT[2] - RC + 12     # 852
CY_POUF = POUF[2] - RC + 15     # 985
# centres de Bounce au contact
B_FLOOR = (780.0, FL - RB)
B_FLOOR_IN = (760.0, FL - RB)   # tout contre le dos du dossier
B_POUF = (735.0, POUF[2] - RB + 8)
B_CUSH = (495.0, SEAT[2] - RB + 10)
B_ARM = (395.0, ARM[2] - RB)
B_MAT_Y = FL - MAT[2] + 6 - RB

HAT_W, HAT_H = 196.0, 62.0

# couleurs
NIGHT = (8, 8, 14)
WALL = (30, 30, 46)
WALL_D = (22, 22, 34)
FLOOR_C, FLOOR_D = (62, 46, 38), (34, 26, 24)
HALL = (112, 94, 66)
BEAM_C = (120, 90, 62)
SOFA_B, SOFA_D = (70, 36, 54), (92, 48, 70)
SOFA_C = (122, 64, 96)
CUSH_C, CUSH_L = (196, 70, 158), (220, 100, 186)     # rose, presque comme Bounce
POUF_C = (170, 90, 60)
MAT_C, MAT_L = (120, 96, 52), (150, 122, 70)
ARM_C = (110, 76, 52)
C_DISC, C_HALO, C_EYE, C_PUP = (40, 84, 164), (16, 30, 66), (140, 204, 242), (26, 52, 104)
C_LINE = (150, 196, 255)

# caméra : (t, (zoom, centre x, centre y)) dans l'image de base 1080×1920
CAM = [(0.0, (1.15, 561.5, 939.0)), (59.90, (1.15, 561.5, 939.0)), (61.20, (1.75, 310.0, 920.0)), (64.5, (1.75, 310.0, 920.0))]
RALENTI = (29.60, 30.80, 0.5)      # début, fin (temps vidéo), facteur


def warp(t):
    a, b, f = RALENTI
    if t < a:
        return t
    if t <= b:
        return a + (t - a) * f
    return t - (b - a) * (1 - f)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def keys(t, kf):
    if t <= kf[0][0]:
        return kf[0][1]
    for (ta, va), (tb, vb) in zip(kf, kf[1:]):
        if ta <= t <= tb:
            s = ease((t - ta) / max(1e-6, tb - ta))
            if isinstance(va, tuple):
                return tuple(lerp(a, b, s) for a, b in zip(va, vb))
            return lerp(va, vb, s)
    return kf[-1][1]


# ------------------------------------------------------------------ la chronologie
# Contacts durs (« Bounce ») : HARD ; tout le reste est mou et muet.
HARD = [1.40, 2.70, 4.55, 5.85,
        7.15, 8.45, 9.75, 11.05, 13.10, 14.35, 15.60, 17.45,
        19.85, 21.00, 22.15, 23.30, 25.30, 26.45, 27.60, 29.15,
        31.03, 32.12, 33.22, 34.32, 35.42, 37.12, 38.22, 39.32, 40.65,
        43.20, 44.60, 46.00, 47.55, 48.80, 50.20, 51.60,
        53.80, 54.80, 55.80, 56.95, 57.80, 58.75, 59.75,
        61.70]
T_ISSUE = 61.70
T_PAYOFF = 62.53          # « Oh no. » part 0,15 s après (1,07 s : fini à 63,75)
T_END = 63.80

# Bounce : (t, genre, position) ; position ("w", x, y) dans le salon, ou relative à Crush :
# ("hat", dx) sur le coussin de sa tête, ("crown", dx) sur son crâne nu, ("brow", k) sur son
# front (le bas de Bounce à k rayons au-dessus du centre de Crush). Options : "h" hauteur du
# petit bond relatif qui suit, "dip" enfoncement d'un contact mou qui dure.
def build_contacts():
    C = []

    def add(t, kind, pos, **o):
        C.append([t, kind, pos, o])
    w = lambda p: ("w",) + tuple(p)
    add(-0.36, "S", w(B_FLOOR))
    add(0.60, "S", w(B_POUF))
    # 0-6,6 : derrière le dossier, parquet (dur) / pouf (mou)
    seq = [(1.40, "H", B_FLOOR), (2.05, "S", B_POUF), (2.70, "H", B_FLOOR), (3.35, "S", B_POUF),
           (3.95, "S", B_POUF), (4.55, "H", B_FLOOR), (5.20, "S", B_POUF), (5.85, "H", B_FLOOR),
           (6.50, "S", B_POUF), (7.15, "H", B_FLOOR), (7.80, "S", B_POUF), (8.45, "H", B_FLOOR),
           (9.10, "S", B_POUF), (9.75, "H", B_FLOOR), (10.40, "S", B_POUF), (11.05, "H", B_FLOOR),
           (11.70, "S", B_POUF), (12.25, "S", B_POUF), (12.75, "S", B_POUF), (13.10, "H", B_FLOOR_IN), (13.75, "S", B_POUF),
           (14.35, "H", B_FLOOR), (15.00, "S", B_POUF), (15.60, "H", B_FLOOR), (16.25, "S", B_POUF),
           (16.85, "S", B_POUF), (17.45, "H", B_FLOOR)]
    for t, k, p in seq:
        add(t, k, w(p))
    # croisement 1 : il retombe sur le coussin du siège
    add(18.80, "S", w(B_CUSH))
    add(19.35, "S", w((B_CUSH[0] - 10, B_CUSH[1])))
    seq = [(19.85, "H", B_ARM), (20.45, "S", B_CUSH), (21.00, "H", B_ARM), (21.60, "S", B_CUSH),
           (22.15, "H", B_ARM), (22.75, "S", B_CUSH), (23.30, "H", B_ARM)]
    for t, k, p in seq:
        add(t, k, w(p))
    add(24.15, "S", w((B_CUSH[0] + 10, B_CUSH[1])), dip=48)     # il s'enfonce dans le coussin rose
    add(24.75, "S", w((B_CUSH[0] + 10, B_CUSH[1])))
    seq = [(25.30, "H", B_ARM), (25.90, "S", B_CUSH), (26.45, "H", B_ARM), (27.05, "S", B_CUSH),
           (27.60, "H", B_ARM), (28.25, "S", B_CUSH), (29.15, "H", B_ARM)]
    for t, k, p in seq:
        add(t, k, w(p))
    # croisement 2 (ralenti) : il repart derrière
    add(31.03, "H", w(B_FLOOR))
    seq = [(31.65, "S", B_POUF), (32.12, "H", B_FLOOR), (32.67, "S", B_POUF), (33.22, "H", B_FLOOR),
           (33.77, "S", B_POUF), (34.32, "H", B_FLOOR), (34.87, "S", B_POUF), (35.42, "H", B_FLOOR)]
    for t, k, p in seq:
        add(t, k, w(p))
    add(36.32, "S", ("hatgraze",))                                 # il frôle le coussin
    add(37.12, "H", w(B_FLOOR))
    add(37.67, "S", w(B_POUF))
    add(38.22, "H", w(B_FLOOR))
    add(39.32, "H", w(B_FLOOR))
    add(40.65, "H", w(B_FLOOR))
    # sur la tête de Crush
    add(41.80, "S", ("hat", 0.0), h=70)
    add(42.35, "S", ("hat", 4.0), h=45)
    add(42.85, "S", ("hat", 8.0), h=22)
    add(43.20, "H", ("crown", -55.0))
    for i, t in enumerate((43.90, 45.40, 46.95, 48.10, 49.65, 50.90, 52.25)):
        add(t, "S", ("hat", 0.0))
        nxt = (44.60, 46.00, 47.55, 48.80, 50.20, 51.60, None)[i]
        if nxt is not None:
            add(nxt, "H", ("crown", -55.0))
    add(52.95, "S", ("hat", 0.0), h=30)
    # vers ses yeux (il voyage avec lui pendant ses bonds)
    for t, k in ((53.80, 0.95), (54.80, 0.80), (55.80, 0.70), (56.95, 0.62), (57.80, 0.66), (58.75, 0.56),
                 (59.75, 0.60)):
        add(t, "H", ("brow", k), h=18)
    add(60.25, "S", ("hat", 0.0), h=55)
    add(60.80, "S", ("hat", 0.0), h=22)
    add(61.12, "S", ("hat", 0.0), dip=16)
    add(61.38, "S", ("hat", 0.0), dip=22)
    add(61.66, "S", ("hat", 0.0))
    add(T_ISSUE, "H", ("lintel",))
    add(62.10, "S", w((432.0, B_MAT_Y)))
    for t in (62.48, 62.84, 63.18, 63.50, 63.80, 64.10):
        add(t, "S", w((432.0 + 2 * math.sin(t * 7), B_MAT_Y)))
    C.sort(key=lambda c: c[0])
    return C


# Crush : déplacements (début, fin, x, y, hauteur du bond). Entre deux, il reste où il est.
CRUSH_START = (290.0, CY_FLOOR)
CRUSH_MOVES = [
    (1.92, 2.38, 335.0, CY_FLOOR, 80),
    (3.12, 3.58, 375.0, CY_FLOOR, 80),
    (4.90, 5.18, 385.0, CY_FLOOR, 25),
    (6.08, 6.60, 505.0, CY_SEAT, 150),        # P1 : sur le canapé
    (7.30, 7.55, 518.0, CY_SEAT, 0),
    (8.60, 9.20, 505.0, CY_SEAT, 80),
    (9.90, 10.60, 505.0, CY_SEAT, 130),
    (13.25, 13.55, 525.0, CY_SEAT + 22, 0),
    (15.75, 16.35, 505.0, CY_SEAT, 150),
    (17.68, 18.68, 735.0, CY_POUF, 0),         # croisement 1 (hauteur : HOP_X1)
    (19.98, 20.12, 712.0, CY_POUF, 0),
    (21.10, 21.25, 735.0, CY_POUF, 0),
    (23.75, 24.65, 735.0, CY_POUF, 240),
    (25.45, 25.70, 752.0, CY_POUF, 0),
    (26.60, 27.05, 735.0, CY_POUF, 60),
    (29.475, 30.65, 505.0, CY_SEAT + 26, 0),    # croisement 2 (hauteur : HOP_X2), la tête dans le coussin
    (31.12, 31.40, 505.0, CY_SEAT, 30),
    (32.27, 32.80, 505.0, CY_SEAT, 70),
    (33.37, 34.00, 505.0, CY_SEAT, 120),
    (43.35, 43.85, 505.0, CY_SEAT, 70),
    (44.75, 45.35, 505.0, CY_SEAT, 140),
    (46.15, 46.90, 505.0, CY_SEAT, 220),
    (48.95, 49.60, 420.0, CY_FLOOR, 110),
    (51.75, 52.15, 452.0, CY_FLOOR, 45),
    (52.15, 52.35, 440.0, CY_FLOOR, 0),
    (53.95, 54.75, 400.0, CY_FLOOR, 130),
    (55.00, 55.75, 398.0, CY_FLOOR, 165),
    (55.95, 56.75, 365.0, CY_FLOOR, 120),
    (57.10, 57.75, 330.0, CY_FLOOR, 90),
    (57.95, 58.70, 300.0, CY_FLOOR, 100),
    (59.35, 59.75, 300.0, CY_FLOOR, 45),
    (61.00, 61.55, 190.0, CY_FLOOR, 0),        # il passe la porte, las
    (61.74, 62.05, 165.0, CY_FLOOR, 0),
]
HOP_X1 = 248.0
HOP_X2 = 270.0

CRUSH_LOOK = [
    (0.0, (0.0, 0.0)), (1.80, (0.95, 0.15)), (2.4, (0.9, 0.1)), (3.40, (-0.6, -0.4)), (3.75, (0.7, -0.5)),
    (4.10, (-0.2, 0.6)), (4.50, (0.3, 0.0)), (4.85, (0.95, -0.2)), (6.6, (0.9, -0.2)), (7.4, (0.95, 0.0)),
    (8.6, (0.95, -0.5)), (9.9, (0.95, -0.3)), (11.2, (0.95, -0.2)), (11.75, (-0.5, -0.2)), (12.35, (0.95, -0.3)),
    (12.65, (0.6, 0.2)), (13.3, (0.8, 0.95)), (15.75, (0.9, -0.4)), (17.55, (0.7, 0.9)), (18.80, (0.5, 0.9)),
    (19.40, (-0.3, 0.2)), (19.95, (-0.9, 0.8)), (21.1, (-0.7, -0.7)), (22.25, (0.0, 0.0)), (23.75, (-0.6, 0.3)),
    (24.15, (-0.85, 0.75)), (24.55, (-0.3, 0.8)), (25.4, (0.2, 0.0)), (26.55, (-0.9, 0.0)), (27.7, (-0.9, -0.3)),
    (29.3, (-0.9, -0.2)), (29.9, (-0.2, -0.9)), (31.15, (0.0, 0.0)), (31.6, (0.9, -0.2)), (32.3, (0.95, -0.4)),
    (34.35, (0.0, 0.3)), (34.8, (0.9, 0.0)), (35.5, (0.95, -0.1)), (36.5, (0.6, -0.5)), (37.25, (0.0, -1.0)),
    (37.9, (0.0, -0.9)), (38.3, (0.95, -0.2)), (39.4, (0.95, -0.3)), (40.75, (-0.9, 0.1)), (41.3, (0.0, 0.0)),
    (41.95, (0.9, 0.3)), (42.4, (-0.9, 0.3)), (42.8, (0.0, 0.85)), (43.30, (0.0, -0.9)), (43.95, (0.0, -0.95)),
    (44.65, (0.0, -0.95)), (45.4, (0.0, -0.95)), (46.05, (0.0, -0.9)), (47.0, (0.4, -0.3)), (47.45, (0.2, -0.2)),
    (48.05, (0.0, -1.0)), (48.6, (0.0, -1.0)), (48.9, (-0.8, 0.2)), (49.7, (-0.5, 0.0)), (50.25, (0.9, 0.0)),
    (50.45, (0.0, 0.9)), (50.65, (-0.9, 0.0)), (50.85, (0.0, -0.9)), (51.1, (0.9, 0.0)), (51.65, (0.95, 0.2)),
    (52.4, (0.0, 0.0)), (53.85, (-0.9, 0.2)), (54.8, (-0.2, 0.0)), (55.2, (0.0, 0.6)), (55.85, (-0.9, 0.0)),
    (56.97, (0.95, 0.1)), (57.55, (0.95, 0.1)), (57.85, (-0.9, 0.3)), (58.7, (0.0, 0.0)), (59.4, (0.0, 0.5)),
    (60.35, (-0.95, 0.5)), (61.55, (-0.95, 0.4)), (62.05, (0.95, 0.35)), (63.8, (0.95, 0.35)),
]
CRUSH_LOOK.sort(key=lambda k: k[0])
# fermetures des yeux : (début, fin)
CRUSH_BLINK = [(30.08, 30.42), (43.30, 43.85), (44.70, 45.35), (46.10, 46.90), (54.84, 55.16), (58.80, 59.32)]
CRUSH_WIDE = [(0.0, 0.0), (1.78, 0.0), (1.80, 0.8), (2.3, 0.0), (24.2, 0.0), (24.3, 0.6), (24.8, 0.0),
              (47.6, 0.0), (47.9, 0.0), (48.05, 0.0), (61.70, 0.0), (61.74, 0.7), (62.15, 0.7), (62.3, 1.2),
              (63.8, 1.2)]
CRUSH_SQUINT = [(0.0, 0.0), (22.25, 0.0), (22.35, 1.0), (23.25, 1.0), (23.35, 0.0), (25.4, 0.0), (25.5, 0.0),
                (47.55, 0.0), (47.85, 0.55), (48.7, 0.55), (48.85, 0.0), (60.30, 0.0), (60.55, 0.5),
                (61.70, 0.5), (61.74, 0.0)]
CRUSH_TURN = [(0.0, 0.0), (38.30, 0.0), (38.65, 0.45), (39.40, 0.45), (39.75, 0.85), (40.75, 0.85),
              (40.95, -0.15), (41.3, 0.0)]
# poses : (t, (sx, sy, tilt))
CRUSH_POSE = [
    (0.0, (0.88, 1.06, -0.10)), (1.75, (0.88, 1.06, -0.10)), (1.92, (1.0, 1.0, 0.0)),
    (4.90, (1.0, 1.0, 0.0)), (5.10, (0.94, 1.04, 0.12)), (5.95, (0.94, 1.04, 0.12)), (6.08, (1.0, 1.0, 0.0)),
    (7.30, (1.0, 1.0, 0.0)), (7.50, (0.90, 1.07, 0.16)), (8.40, (0.90, 1.07, 0.16)), (8.60, (1.0, 1.0, 0.0)),
    (11.15, (1.0, 1.0, 0.0)), (11.45, (0.84, 1.30, 0.0)), (12.85, (0.84, 1.30, 0.0)), (13.25, (1.05, 0.95, 0.25)),
    (14.45, (1.05, 0.95, 0.25)), (14.70, (1.10, 0.84, 0.32)), (15.55, (1.10, 0.84, 0.32)), (15.75, (1.0, 1.0, 0.0)),
    (19.95, (1.0, 1.0, 0.0)), (20.20, (1.36, 0.66, -0.05)), (20.95, (1.36, 0.66, -0.05)), (21.15, (0.86, 1.28, 0.0)),
    (22.10, (0.86, 1.28, 0.0)), (22.30, (0.98, 1.0, -0.22)), (23.30, (0.98, 1.0, -0.22)), (23.55, (1.0, 1.0, 0.0)),
    (25.45, (1.0, 1.0, 0.0)), (25.70, (0.90, 1.06, 0.0)), (26.50, (0.90, 1.06, 0.0)), (26.60, (1.0, 1.0, 0.0)),
    (27.70, (1.0, 1.0, 0.0)), (28.00, (1.26, 0.72, 0.0)), (29.25, (1.26, 0.72, 0.0)), (29.40, (1.0, 1.0, 0.0)),
    (30.62, (1.0, 1.0, 0.0)), (30.70, (1.16, 0.84, 0.0)), (31.12, (1.16, 0.84, 0.0)), (31.30, (1.0, 1.0, 0.0)),
    (50.25, (1.0, 1.0, 0.0)), (50.40, (1.12, 0.92, 0.35)), (50.60, (0.92, 1.06, -0.35)), (50.80, (1.12, 0.92, 0.3)),
    (51.00, (1.0, 1.0, 0.0)), (52.55, (1.0, 1.0, 0.0)), (52.75, (1.10, 1.08, 0.0)), (53.10, (1.10, 1.08, 0.0)),
    (53.30, (1.0, 1.0, 0.0)), (58.80, (1.0, 1.0, 0.0)), (58.95, (0.98, 1.0, -0.2)), (59.30, (0.98, 1.0, -0.2)),
    (59.40, (1.0, 1.0, 0.0)), (60.30, (1.0, 1.0, 0.0)), (60.60, (1.06, 0.90, 0.0)), (61.70, (1.06, 0.90, 0.0)),
    (61.74, (1.0, 1.0, 0.0)), (62.20, (1.04, 1.04, 0.0)), (63.8, (1.04, 1.04, 0.0)),
]
# le coussin sur sa tête : décalage et inclinaison
HAT_ON = 30.70
HAT_KEYS = [(0.0, (0.0, 0.0, 0.0)), (30.70, (0.0, 38.0, 0.0)), (31.12, (0.0, 38.0, 0.0)), (31.35, (0.0, 0.0, 0.0)),
            (33.45, (0.0, 0.0, 0.0)), (33.65, (-6.0, 42.0, -0.15)), (34.40, (-6.0, 42.0, -0.15)), (34.70, (0.0, 0.0, 0.0)),
            (38.30, (0.0, 0.0, 0.0)), (38.65, (62.0, 26.0, 0.55)), (39.40, (62.0, 26.0, 0.55)), (39.75, (78.0, 42.0, 0.75)),
            (40.75, (78.0, 42.0, 0.75)), (41.00, (0.0, 0.0, 0.0)), (42.35, (0.0, 0.0, 0.0)), (43.00, (80.0, 12.0, 0.35)),
            (53.30, (80.0, 12.0, 0.35)), (53.70, (86.0, 12.0, 0.45)), (59.75, (86.0, 12.0, 0.45)), (59.95, (0.0, 0.0, 0.0)),
            (61.70, (0.0, 0.0, 0.0)), (61.80, (14.0, 0.0, 0.1)), (64.0, (14.0, 0.0, 0.1))]

# les répliques : (déclencheur, voix de la banque, clé)
LINES = [
    (12.00, "@crush_q", "c_q1"),
    (18.95, "@crush_q", "c_q2"),
    (42.00, "@crush_qlow", "c_q3"),
    (52.55, "@crush_fort", "c_cri"),
]

# le banc : Float, Blub, Still (petits, en bas, réactions décalées)
BENCH = {"float": (400.0, 1415.0), "blub": (560.0, 1415.0), "still": (720.0, 1415.0)}
RBN = 72.0


class Sim:
    scene_top = 0.30

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_modules(cfg["draw_from"])
        gains = cfg.get("voice_gain", {})
        for key, path in cfg["voices"].items():
            BANK["@" + key] = _read(path, gains.get(key, 1.0))
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.lines = list(LINES)
        self.moves = []
        for (a, b, x, y, h) in CRUSH_MOVES:
            if abs(a - 17.68) < 1e-6:
                h = HOP_X1
            if abs(a - 29.475) < 1e-6:
                h = HOP_X2
            self.moves.append((a, b, x, y, h))
        self.C = build_contacts()
        self._resolve()
        self.hits = [c[0] for c in self.C if c[1] == "H"]
        self.hi = 0
        self.end_s = T_END
        self._rings()

    # ---------------------------------------------------------- Crush
    def crush_base(self, t):
        """Centre de Crush (sans la pose) et le bond en cours."""
        x, y = CRUSH_START
        for (a, b, x1, y1, h) in self.moves:
            if t >= b:
                x, y = x1, y1
                continue
            if t <= a:
                break
            s = (warp(t) - warp(a)) / max(1e-6, warp(b) - warp(a))
            if h > 0:
                return lerp(x, x1, s), lerp(y, y1, s) - 4 * h * s * (1 - s), (a, b)
            k = ease(s)
            return lerp(x, x1, k), lerp(y, y1, k), (a, b)
        return x, y, None

    def crush(self, t):
        x, y, mv = self.crush_base(t)
        sx, sy, tilt = keys(t, CRUSH_POSE)
        # écrasement à l'atterrissage
        for (a, b, x1, y1, h) in self.moves:
            d = t - b
            if h > 0 and 0 <= d < 0.4:
                q = min(0.16, 0.0008 * h + 0.03) * math.exp(-d * 8) * math.cos(d * 22)
                sx, sy = sx + q, sy - q
        y = y + RC * (1 - sy)             # le bas reste posé
        return x, y, sx, sy, tilt

    def crush_top(self, t):
        x, y, sx, sy, tilt = self.crush(t)
        return x, y - RC * sy

    def hat(self, t):
        """(cx, haut, inclinaison) du coussin sur la tête de Crush, ou None."""
        if t < HAT_ON:
            return None
        x, y, sx, sy, tilt = self.crush(t)
        dx, dy, a = keys(t, HAT_KEYS)
        top = y - RC * sy
        return x + dx, top - HAT_H + 8 + dy, a

    # ---------------------------------------------------------- Bounce
    def _pos(self, c, t):
        p = c[2]
        if p[0] == "w":
            return p[1], p[2]
        x, y, sx, sy, tilt = self.crush(t)
        if p[0] == "hat":
            hx, htop, a = self.hat(t)
            return hx + p[1], htop - RB + 6
        if p[0] == "crown":
            dx = p[1]
            return x + dx, y - math.sqrt(RC * RC - dx * dx) * sy - RB + 4
        if p[0] == "brow":
            return x - 8, y - p[1] * RC - RB
        if p[0] == "lintel":
            return x, LINTEL + RB
        if p[0] == "hatgraze":
            hx, htop, a = self.hat(t)
            return hx + 132, htop - 52
        raise ValueError(p)

    def _resolve(self):
        for c in self.C:
            c.append(self._pos(c, c[0]))          # c[4] = position monde au contact
            p = c[2]
            if p[0] in ("hat", "crown", "brow"):
                x, y, sx, sy, tilt = self.crush(c[0])
                c.append((c[4][0] - x, c[4][1] - y))    # c[5] = décalage par rapport à Crush
            else:
                c.append(None)

    @staticmethod
    def rel(c):
        return c[2][0] in ("hat", "crown", "brow")

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return C[0][4]
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                s_lin = (t - a[0]) / max(1e-6, b[0] - a[0])
                dip = a[3].get("dip")
                if dip:
                    if self.rel(a):
                        x, y, *_ = self.crush(t)
                        ox, oy = lerp(a[5][0], b[5][0], s_lin), lerp(a[5][1], b[5][1], s_lin)
                        return x + ox, y + oy + dip * math.sin(math.pi * s_lin)
                    return lerp(a[4][0], b[4][0], s_lin), lerp(a[4][1], b[4][1], s_lin) + dip * math.sin(math.pi * s_lin)
                if self.rel(a) and self.rel(b):
                    T = b[0] - a[0]
                    h = a[3].get("h", min(240.0, G * T * T / 8))
                    x, y, *_ = self.crush(t)
                    ox = lerp(a[5][0], b[5][0], s_lin)
                    oy = lerp(a[5][1], b[5][1], s_lin) - 4 * h * s_lin * (1 - s_lin)
                    return x + ox, y + oy
                # arc balistique dans le salon (temps ralenti compris)
                Ts = warp(b[0]) - warp(a[0])
                s = warp(t) - warp(a[0])
                (xa, ya), (xb, yb) = a[4], b[4]
                v0 = (ya - yb) / Ts + G * Ts / 2
                return xa + (xb - xa) * s / Ts, ya - v0 * s + 0.5 * G * s * s
        return C[-1][4]

    # ---------------------------------------------------------- les anneaux
    def _rings(self):
        self.R = []
        for c in self.C:
            if c[1] != "H":
                continue
            bx, by = c[4]
            if c[2][0] == "lintel":
                px, py = bx - 10, by - RB
            elif c[2][0] == "brow":
                px, py = bx, by + RB * 0.7
            else:
                px, py = bx, by + RB
            cx, cy, *_ = self.crush(c[0] + 0.25)
            d = math.hypot(cx - px, cy - py)
            touch = max(0.0, d - RC)
            rmax = max(touch + 45.0, 210.0)
            self.R.append((c[0], px, py, rmax, touch))
        self.t_wake = self.R[0][0] + self.R[0][4] / 1100.0

    # ---------------------------------------------------------- moteur
    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi] <= self.t:
            evs.append(("hit", "h"))
            self.hi += 1
        if not self.payoff and self.t >= T_PAYOFF:
            self.payoff = True
            evs.append(("payoff", "found"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def hero_mood(self):
        return "lose"

    # ---------------------------------------------------------- la caméra (un recadrage, sans coupe)
    def post(self, img, t):
        """Plan fixe resserré sur le salon ; à la fin, la caméra s'approche lentement de la porte.
        Le filigrane, sorti du cadre par le recadrage, est reposé à sa place."""
        k, cx, cy = keys(t, CAM)
        w, h = W / k, H / k
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        out = img.resize((W, H), Image.LANCZOS, box=box)
        d = ImageDraw.Draw(out)
        d.text((W / 2, H * self.cfg["watermark_y"]), self.cfg["watermark"], fill=(92, 80, 76), anchor="mm", font=font(30))
        return out

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        def X(x):
            return x * S

        def Y(y):
            return y * S

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([X(x0), Y(y0), X(x1), Y(y1)], fill=col)

        def ell(x, y, rx, ry, col, outline=None, w=0):
            dr.ellipse([X(x - rx), Y(y - ry), X(x + rx), Y(y + ry)], fill=col, outline=outline, width=w)

        def poly(pts, col):
            dr.polygon([(X(px), Y(py)) for px, py in pts], fill=col)

        bx, by = self.bounce_at(t)
        bbot = by + RB

        def dent_at(xx, x0, x1, ytop, depth_max):
            d = bbot - ytop
            if d <= 0 or not (x0 - RB < bx < x1 + RB):
                return 0.0
            k = max(0.0, 1 - ((xx - bx) / (RB * 1.05)) ** 2)
            return min(depth_max, d) * k

        def soft_top(x0, x1, ytop, depth_max, n=24):
            return [(x0 + (x1 - x0) * i / n, ytop + dent_at(x0 + (x1 - x0) * i / n, x0, x1, ytop, depth_max)) for i in range(n + 1)]

        # ---- la pièce
        rect(0, 0, W, H, NIGHT)
        rect(0, 0, W, FL, WALL_D)
        rect(WALL_X1, 0, RWALL, FL, WALL)
        rect(WALL_X1, 96, RWALL, 110, WALL_D)
        # une suspension au plafond, éteinte
        dr.line([(X(540), Y(0)), (X(540), Y(150))], fill=(60, 56, 70), width=int(3 * S))
        poly([(505, 190), (575, 190), (556, 150), (524, 150)], (70, 62, 84))
        # la fenêtre et la lune, un cadre
        rect(660, 330, 840, 560, (20, 26, 52))
        ell(790, 390, 30, 30, (230, 226, 190))
        rect(747, 330, 753, 560, (60, 56, 70)); rect(660, 442, 840, 448, (60, 56, 70))
        rect(240, 380, 400, 482, (96, 80, 56)); rect(252, 392, 388, 470, (60, 86, 92))
        # le couloir derrière la porte, éclairé, et la lumière qui en sort sur le sol
        rect(0, LINTEL, WALL_X1, FL, HALL)
        rect(0, FL - 4, WALL_X1, FL + 24, (118, 98, 70))
        poly([(WALL_X1, FL), (WALL_X1 + 170, FL), (WALL_X1 + 120, FL + 22), (WALL_X1, FL + 22)], (92, 76, 58))
        # le mur épais au-dessus de la porte, la poutre, le chambranle
        rect(WALL_X0, 0, WALL_X1, LINTEL, WALL_D)
        rect(WALL_X0 - 8, LINTEL - 24, WALL_X1 + 10, LINTEL, BEAM_C)
        rect(WALL_X0 - 8, LINTEL - 24, WALL_X1 + 10, LINTEL - 18, (150, 116, 82))
        rect(WALL_X1, LINTEL, WALL_X1 + 10, FL, BEAM_C)
        rect(WALL_X0 - 8, LINTEL, WALL_X0, FL, BEAM_C)
        rect(RWALL, 0, W, FL + 40, WALL_D)
        # le sol, et son devant jusqu'en bas
        rect(WALL_X1 + 10, FL, W, FL + 22, FLOOR_C)
        for i in range(19):
            y0 = FL + 22 + i * 40
            rect(0, y0, W, y0 + 40, mix(FLOOR_C, FLOOR_D, min(1.0, 0.25 + i * 0.06)))
            dr.line([(X(0), Y(y0)), (X(W), Y(y0))], fill=mix(FLOOR_D, NIGHT, 0.5), width=int(2 * S))
        # un tapis au premier plan (décor)
        ell(540, 1560, 430, 110, (52, 36, 44)); ell(540, 1560, 390, 90, (64, 44, 54))
        # le paillasson
        mt = FL - MAT[2]
        poly([(MAT[0], FL)] + soft_top(MAT[0], MAT[1], mt, MAT[2] - 2) + [(MAT[1], FL)], MAT_C)
        for i in range(10):
            xx = MAT[0] + 12 + i * 23
            dr.line([(X(xx), Y(mt + 3 + dent_at(xx, MAT[0], MAT[1], mt, MAT[2] - 2))), (X(xx), Y(FL - 2))], fill=MAT_L, width=int(2 * S))
        # le pouf
        poly([(POUF[0] - 6, FL)] + soft_top(POUF[0], POUF[1], POUF[2], 36) + [(POUF[1] + 6, FL)], POUF_C)
        dr.line([(X(POUF[0] + 8), Y(POUF[2] + 24)), (X(POUF[1] - 8), Y(POUF[2] + 24))], fill=(196, 116, 80), width=int(4 * S))
        # le canapé (sans le dossier) : socle, pieds, accoudoir, coussin
        rect(ARM[0], SEAT[3], BACK[1], 1120, SOFA_B)
        for lx in (ARM[0] + 6, BACK[1] - 20):
            rect(lx, 1120, lx + 14, FL, (60, 40, 34))
        dr.rounded_rectangle([X(ARM[0]), Y(ARM[2]), X(ARM[1] + 8), Y(1120)], radius=int(14 * S), fill=ARM_C,
                             outline=(150, 108, 76), width=int(3 * S))
        if t < HAT_ON:
            top = soft_top(SEAT[0], SEAT[1], SEAT[2], 50)
            poly([(SEAT[0], SEAT[3])] + top + [(SEAT[1], SEAT[3])], CUSH_C)
            dr.line([(X(px), Y(py + 6)) for px, py in top[2:-2]], fill=CUSH_L, width=int(4 * S))
        else:
            rect(SEAT[0], SEAT[3] - 12, SEAT[1], SEAT[3], SOFA_D)

        # ---- le banc (en bas)
        rect(310, 1487, 810, 1501, (96, 72, 52))
        for lx in (326, 786):
            rect(lx, 1501, lx + 10, 1535, (70, 52, 40))
        self.draw_bench(dr, t, S)

        # ---- les halos, Bounce, puis le dossier par-dessus les halos, puis les corps
        self.draw_crush(dr, t, S, bx, by, part="halo")
        base.ball(dr, X(bx), Y(by), RB * S)
        dr.rounded_rectangle([X(BACK[0]), Y(BACK[2]), X(BACK[1]), Y(1120)], radius=int(22 * S), fill=SOFA_C,
                             outline=(176, 112, 146), width=int(4 * S))
        dr.line([(X(BACK[0] + 14), Y(BACK[2] + 40)), (X(BACK[0] + 14), Y(1100))], fill=SOFA_D, width=int(3 * S))
        # le mur au-dessus de la porte et sa poutre repassent devant les halos
        rect(WALL_X0, 0, WALL_X1, LINTEL - 24, WALL_D)
        rect(WALL_X0 - 8, LINTEL - 24, WALL_X1 + 10, LINTEL, BEAM_C)
        rect(WALL_X0 - 8, LINTEL - 24, WALL_X1 + 10, LINTEL - 18, (150, 116, 82))
        self.draw_crush(dr, t, S, bx, by, part="body")
        hb = self.hat(t)
        if hb is not None:
            self.draw_hat(dr, t, S, hb, bx, by)
        # le disque et le visage de Bounce repassent devant (mêmes tracés que base.ball)
        base.circle(dr, X(bx), Y(by), RB * S, base.HERO["color"])
        base.hero_face(dr, X(bx), Y(by), RB * S)
        # Bounce enfoncé dans le coussin rose : le bord du coussin repasse devant lui
        if 24.10 <= t <= 24.85:
            k = max(0.0, (bbot - SEAT[2]) / 48.0)
            if k > 0:
                lip = [(B_CUSH[0] + 10 + u, SEAT[2] + 6 - 26 * k * math.cos(u / 70.0)) for u in range(-92, 93, 8)]
                poly([(B_CUSH[0] - 82, SEAT[3])] + lip + [(B_CUSH[0] + 102, SEAT[3])], CUSH_C)
        # ---- les anneaux du son
        for (t0, px, py, rmax, touch) in self.R:
            d = t - t0
            if d < 0:
                continue
            r = 1100.0 * d
            fade = 1.0 if r < rmax else 1.0 - (d - rmax / 1100.0) / 0.18
            if fade <= 0:
                continue
            r = min(r, rmax + 60 * (1 - fade))
            col = mix(WALL, (255, 255, 255), 0.95 * fade)
            dr.ellipse([X(px - r), Y(py - r), X(px + r), Y(py + r)], outline=col, width=int(6 * S))

    def draw_hat(self, dr, t, S, hb, bx, by):
        hx, htop, a = hb
        d = 0.0
        if abs(bx - hx) < HAT_W * 0.8:
            d = max(0.0, min(20.0, by + RB - htop))
        ca, sa = math.cos(a), math.sin(a)
        cy = htop + HAT_H / 2
        pts = []
        for i in range(36):
            th = 2 * math.pi * i / 36
            u = math.copysign(abs(math.cos(th)) ** 0.5, math.cos(th)) * HAT_W / 2
            v = math.copysign(abs(math.sin(th)) ** 0.5, math.sin(th)) * HAT_H / 2
            if v < 0:
                v += d * max(0.0, 1 - (u / (HAT_W * 0.5)) ** 2)
            pts.append((hx + u * ca - v * sa, cy + u * sa + v * ca))
        dr.polygon([(px * S, py * S) for px, py in pts], fill=CUSH_C, outline=CUSH_L, width=int(3 * S))
        for u in (-0.25, 0.25):
            ux, uy = hx + u * HAT_W * ca, cy + u * HAT_W * sa
            dr.ellipse([(ux - 5) * S, (uy - 5) * S, (ux + 5) * S, (uy + 5) * S], fill=(150, 46, 118))
        dr.line([((hx - 0.38 * HAT_W * ca) * S, (cy - 0.38 * HAT_W * sa + 4) * S),
                 ((hx + 0.38 * HAT_W * ca) * S, (cy + 0.38 * HAT_W * sa + 4) * S)], fill=CUSH_L, width=int(4 * S))

    def draw_crush(self, dr, t, S, bx, by, part="body"):
        x, y, sx, sy, tilt = self.crush(t)
        if part == "halo":
            dr.ellipse([(x - 1.6 * RC * sx) * S, (y - 1.6 * RC * sy) * S, (x + 1.6 * RC * sx) * S, (y + 1.6 * RC * sy) * S], fill=C_HALO)
            return
        look = keys(t, CRUSH_LOOK)
        wide = keys(t, CRUSH_WIDE)
        squint = keys(t, CRUSH_SQUINT)
        turn = keys(t, CRUSH_TURN)
        blink = 0.0
        if t < self.t_wake:
            blink = 1.0
        for (a, b) in CRUSH_BLINK:
            if a <= t <= b:
                blink = min(1.0, min(t - a, b - t) / 0.06)
        flash = 0.0
        for (t0, px, py, rmax, touch) in self.R:
            dd = t - (t0 + touch / 1100.0)
            if 0 <= dd < 0.16:
                flash = max(flash, 1 - dd / 0.16)
        r = RC
        ca, sa = math.cos(tilt), math.sin(tilt)

        def P(u, v):
            return (x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S

        line = mix(C_LINE, (255, 255, 255), flash)
        dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=C_DISC,
                   outline=line, width=max(2, int((0.045 + 0.05 * flash) * r * S)))
        for side in (-1, 1):
            eu = 0.34 * side + 0.20 * turn
            far = 1.0 - 0.35 * max(0.0, turn * side)      # l'œil du côté où il tourne s'amincit
            ev = -0.18
            rw = 0.24 * far * (1 + 0.15 * wide)
            rh = 0.30 * (1 + 0.2 * wide) * (1 - 0.55 * squint)
            if blink > 0.05:
                rh *= max(0.08, 1 - blink)
            pts = [P(eu + rw * math.cos(k * math.pi / 14), ev + rh * math.sin(k * math.pi / 14)) for k in range(28)]
            dr.polygon(pts, fill=C_EYE)
            if blink < 0.7 and rh > 0.08:
                pr = 0.10 * (1 - 0.25 * wide)
                pu = eu + look[0] * max(0.0, rw - pr) * 0.85
                pv = ev + look[1] * max(0.0, rh - pr) * 0.8
                dr.polygon([P(pu + pr * math.cos(k * math.pi / 8), pv + pr * math.sin(k * math.pi / 8)) for k in range(16)], fill=C_PUP)
            if squint > 0.2:
                dr.line([P(eu - rw, ev - rh), P(eu + rw, ev - rh)], fill=C_PUP, width=max(2, int(0.05 * r * S)))

    def draw_bench(self, dr, t, S):
        c4, bl = M["clip4"], M["blub"]
        c4.RF = RBN

        def hop(t0, h, dur=0.45):
            d = t - t0
            return h * math.sin(math.pi * d / dur) if 0 <= d <= dur else 0.0
        lean = 0.0
        for (t0, t1) in ((30.50, 31.40), (42.20, 44.0)):
            if t0 <= t <= t1:
                lean = min(1.0, (t - t0) / 0.25, (t1 - t) / 0.25)
        jumps = [(18.55, 22), (54.20, 34), (55.20, 28), (62.65, 95)]
        dy = sum(hop(a, h) for a, h in jumps)
        # Float
        fx, fy = BENCH["float"]
        e = "wide_o" if (42.2 <= t <= 47.0 or t >= 62.65) else ("squint" if t > 18.5 else "calm")
        c4.draw_float(dr, c4.VIEW, fx + 10 * lean, fy - dy - 8 * lean, 0.25 * lean, c4.EXPR[e], (0.0, 0.0), 0.0, 0.0, 0.0)
        # Blub
        bx, byy = BENCH["blub"]
        mood = "peur" if 42.2 <= t <= 47.0 else ("joie" if t >= 62.65 or t < 18.5 else "retient")
        bl.draw_blub(dr, bx + 8 * lean, byy - hop(18.65, 22) - hop(54.30, 34) - hop(62.70, 98) - 8 * lean, RBN, S, mood=mood)
        dr.ellipse([(bx + 8 * lean - RBN) * S, (byy - 8 * lean - RBN - hop(62.70, 98) - hop(54.30, 34) - hop(18.65, 22)) * S,
                    (bx + 8 * lean + RBN) * S, (byy - 8 * lean + RBN - hop(62.70, 98) - hop(54.30, 34) - hop(18.65, 22)) * S],
                   outline=(235, 240, 255), width=int(3 * S))
        # Still : elle dort ; elle ouvre les yeux quand Bounce se pose sur la tête de Crush, puis à la fin
        sx_, sy_ = BENCH["still"]
        wide = (42.3 <= t <= 46.5) or t >= 62.75
        c4.draw_still(dr, sx_ + 6 * lean, sy_ - hop(62.75, 92) - 6 * lean, RBN, gx=-1.0 if wide else 0.0, wide=wide)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 8.3,
            "hook_top": 0.163, "hook_font_size": 84, "hook_width": 0.75, "sub_y": 0.165, "sub_font_size": 58, "show_counter": False,
            "narr_tail_s": 0.3, "hero_shock_s": 0.22}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
