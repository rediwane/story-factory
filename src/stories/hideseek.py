"""
Prototype « cache-cache » : les personnages des fans jouent à cache-cache dans une maison en
coupe, filmée étage par étage. Crush compte, puis cherche à l'oreille. Bounce se cache aussi,
mais il dit son nom à chaque contact dur : c'est lui qu'on entend, et ce sont les autres qu'on
trouve (Beam éternue dans la poussière qu'il soulève, la mousse du bain qu'il fait voler
découvre Float et Blub). Un paquet de cette mousse coiffe Crush ; Bounce finit par y retomber :
sur du mou, il est muet. La perruque fond à chaque rebond, compte à rebours. « Found ones can
help! » : les trouvés ne savent dire que leur nom ; Crush trouve Still, en pleine vue depuis le
début. « Everyone found! » ; « Who should seek next? » — « Bounce. »

Les dessins des personnages viennent des scripts déjà publiés (chemins dans cfg["draw_from"]),
leurs voix des banques hors dépôt (cfg["voices"]). Crush est redessiné à l'identique avec des
pupilles qui bougent et un clignement. Rien n'est modifié dans le moteur : les surcharges
(banque de voix, « Bou— » étouffé) vivent ici.

    python3 src/stories/hideseek.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave, importlib, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import base
from base import dim, font
import voice as narr_voice
import audio_kit as ak

ORIG = {"say": narr_voice.say, "sub": base.subtitle_at, "narr": base.build_narration,
        "word": base.hero_word, "audio": base.render_audio}
SR = ak.SR
BANK = {}
M = {}                                   # modules de dessin des personnages


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


def build_keep(sim, cfg):
    narr, rep = ORIG["narr"](sim, cfg)
    sim.narr = narr
    return narr, rep


_memo = {}


def steady_word(text, cfg):
    """Même mot, même longueur : on garde un tirage court de « Bounce » pour tout le processus."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _memo:
        best = None
        for _ in range(12):
            v = ORIG["word"](text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _memo[key] = best
    return None if _memo[key] is None else _memo[key].copy()


def muffled(name):
    """« Bou— » : le début du mot de Bounce, coupé net et étouffé (à travers la mousse)."""
    n = min(len(name), int(0.30 * SR))
    x = name[:n].copy()
    f = int(0.06 * SR)
    x[-f:] *= np.linspace(1, 0, f)
    ker = np.ones(28) / 28
    x = np.convolve(np.convolve(x, ker, mode="same"), ker, mode="same")
    return x / (np.max(np.abs(x)) + 1e-9) * np.max(np.abs(name)) * 0.45


def render_audio(events, total_dur, cfg, path, payoff_t=None, mood=None, narr=(), replies=()):
    """Celle du moteur, plus un cas : un contact marqué « muffle » dit « Bou— » étouffé."""
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
        mu = muffled(name)
        for (t0, kind, _d, tag) in words:
            if kind == "hit" and tag == "muffle":
                ak.add(buf, mu, t0, gain=cfg["hero_gain"])
            elif kind == "hit":
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
    base.build_narration = build_keep
    base.hero_word = steady_word
    base.render_audio = render_audio


install()


def load_modules(paths):
    """Les dessins des personnages, tels quels. Leurs modules posent leurs propres surcharges
    à l'import : on remet ensuite les nôtres."""
    if M:
        return
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
    for name in ("clip4", "beam", "blub"):
        M[name] = importlib.import_module(name)
    narr_voice.say, base.subtitle_at, base.build_narration = ORIG["say"], ORIG["sub"], ORIG["narr"]
    base.hero_word, base.render_audio = ORIG["word"], ORIG["audio"]
    install()


# ------------------------------------------------------------------ la maison (coordonnées du monde)
W, H = 1080, 1920
G = 2600.0
RB = 90.0
FL = 1560.0             # sol du salon
CEIL = 560.0            # plafond du salon
FB = 520.0              # sol de la salle de bain (dessus de la dalle)
CB = -480.0             # plafond de la salle de bain
CAM_UP = -1040.0        # la caméra à l'étage
WL, WR = 40.0, 935.0    # murs intérieurs
COL0 = 680.0            # cage d'escalier : x 680..935
RC, RS, RBM, RF, RBL = 125.0, 80.0, 75.0, 78.0, 72.0
STILL = (600.0, FL - RS)
SOFA_X0, SOFA_X1, SOFA_UNDER, SOFA_SEAT, SOFA_BACK = 300.0, 580.0, 1380.0, 1290.0, 1120.0
POUF = (548.0, 652.0, 40.0)                  # coussin de sol derrière Still : x0, x1, épaisseur
TOWEL = (835.0, 932.0, 866.0 - 60.0)         # pile de serviettes, palier haut : x0, x1, dessus
TUB_X0, TUB_X1, TUB_RIM, TUB_IN = 30.0, 600.0, 260.0, 500.0
WATER = 330.0
FLOAT0, BLUB0 = (140.0, 300.0), (470.0, 405.0)

# couleurs
NIGHT = (8, 8, 14)
WALL_LR, WALL_BA = (30, 30, 46), (30, 40, 52)
FLOOR_C, SLAB_C = (58, 44, 38), (20, 18, 26)
SOFA_C, SOFA_D, SOFA_B = (120, 66, 92), (92, 48, 70), (70, 36, 54)
STAIR_C, STAIR_D = (86, 70, 60), (52, 42, 38)
FOAM, FOAM_S = (240, 244, 250), (206, 214, 228)
WATER_C = (150, 206, 236)
DUST = (150, 140, 128)
C_DISC, C_HALO, C_EYE, C_PUP = (40, 84, 164), (16, 30, 66), (140, 204, 242), (26, 52, 104)
C_LINE = (150, 196, 255)


def stair_flights():
    """Trois volées en zigzag de FL à FB : [(x_bas, y_bas, x_haut, y_haut)]."""
    return [(930.0, FL, 705.0, 1213.0), (705.0, 1213.0, 930.0, 866.0), (930.0, 866.0, 705.0, FB)]


def step_top(f, k):
    """Le dessus de la marche k (1..4) de la volée f : (x milieu, y)."""
    x0, y0, x1, y1 = stair_flights()[f]
    return x0 + (x1 - x0) * (k - 0.5) / 4, y0 + (y1 - y0) * k / 4


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def keys(t, kf):
    """Interpolation douce entre images clés [(t, valeur)] ; les valeurs sont des nombres ou des tuples."""
    if t <= kf[0][0]:
        return kf[0][1]
    for (ta, va), (tb, vb) in zip(kf, kf[1:]):
        if ta <= t <= tb:
            s = ease((t - ta) / max(1e-6, tb - ta))
            if isinstance(va, tuple):
                return tuple(lerp(a, b, s) for a, b in zip(va, vb))
            return lerp(va, vb, s)
    return kf[-1][1]


def step_keys(t, kf):
    v = kf[0][1]
    for (ta, va) in kf:
        if t >= ta:
            v = va
    return v


# ------------------------------------------------------------------ Crush : le dessin du fan, les yeux qui bougent
def draw_crush(dr, x, y, r, S, Y, mood="neutre", look=(0.0, 0.0), blink=0.0, sx=1.0, sy=1.0, wide=0.0):
    """Le disque, le halo et les deux grands yeux de Crush (d'après crush.py), plus un contour clair ;
    les pupilles regardent (look), les yeux se ferment (blink) ou s'arrondissent (wide)."""
    def box(cx, cy, rx, ry):
        return [(cx - rx) * S, Y(cy - ry), (cx + rx) * S, Y(cy + ry)]
    dr.ellipse(box(x, y, 1.6 * r * sx, 1.6 * r * sy), fill=C_HALO)
    dr.ellipse(box(x, y, r * sx, r * sy), fill=C_DISC, outline=C_LINE, width=max(2, int(0.045 * r * S)))
    for side in (-1, 1):
        ex, ey = x + 0.34 * r * side * sx, y - 0.18 * r * sy
        rw = 0.24 * r * (1 + 0.15 * wide)
        rh = 0.30 * r * (0.55 if mood == "triste" else 1.0) * (1 + 0.2 * wide)
        if blink > 0.05:
            rh *= max(0.08, 1 - blink)
        dr.ellipse(box(ex, ey, rw, rh), fill=C_EYE)
        if blink < 0.7:
            pr = 0.10 * r * (1 - 0.25 * wide)
            px = ex + look[0] * (rw - pr) * 0.85
            py = ey + (0.08 * r if mood == "triste" else 0.0) + look[1] * (rh - pr) * 0.8
            dr.ellipse(box(px, py, pr, pr), fill=C_PUP)
            if mood == "joie":
                dr.ellipse(box(px - 0.035 * r, py - 0.06 * r, 0.035 * r, 0.035 * r), fill=(240, 248, 255))
        if mood == "triste":
            dr.line([((ex - rw) * S, Y(ey - rh - 6)), ((ex + rw) * S, Y(ey - rh + 8 * side))], fill=C_PUP, width=int(8 * S))


# ------------------------------------------------------------------ la chronologie
# Bounce : contacts (t, x, y, genre, étiquette) ; genre "H" dur (il parle), "S" mou (muet),
# "W" la perruque de mousse (mou, position calculée sur la tête de Crush), "WM" la perruque
# traversée (« Bou— » étouffé), "CH" le crâne nu de Crush (dur).
SEAT_C = SOFA_SEAT - RB + 22          # centre de Bounce dans le coussin
POUF_C = FL - POUF[2] - RB + 26       # centre de Bounce dans le coussin de sol
FLOOR_C_Y = FL - RB
BEHIND_L, BEHIND_R = 545.0, 655.0     # au sol derrière Still, débordant à gauche / à droite


def build_contacts():
    C = []

    def add(t, x, y, kind, tag=""):
        C.append([t, x, y, kind, tag])
    add(-0.36, 590, POUF_C, "S")
    add(0.40, 610, POUF_C, "S")
    add(1.15, 590, POUF_C, "S")
    add(2.10, BEHIND_L, FLOOR_C_Y, "H")
    add(3.00, BEHIND_R, FLOOR_C_Y, "H")
    add(3.90, 520, SEAT_C, "S")
    add(4.65, 450, SEAT_C, "S")
    add(5.38, 380, SEAT_C, "S")
    add(6.00, 360, FLOOR_C_Y, "H", "back")
    add(7.10, 480, FLOOR_C_Y, "H", "back")
    add(7.95, 520, SOFA_BACK - RB + 20, "S", "backtop")
    add(8.75, 420, SEAT_C, "S")
    add(9.50, 500, SEAT_C, "S")
    add(10.25, 440, SEAT_C, "S")
    add(11.35, 480, SEAT_C, "S")
    add(12.20, BEHIND_R, FLOOR_C_Y, "H")
    x, y = step_top(0, 2)
    add(13.10, x, y - RB, "H")
    add(14.00, 885, TOWEL[2] - RB + 26, "S", "towel")
    x, y = step_top(2, 2)
    add(14.90, x, y - RB, "H")
    x, y = step_top(2, 4)
    add(15.85, x, y - RB, "H")
    add(16.80, 585, TUB_RIM - RB, "H", "rim")
    add(17.65, 380, 178, "S", "foam")
    add(18.40, 270, 205, "S", "foam")
    add(19.15, 420, 236, "S", "foam")
    add(19.90, 320, 280, "S", "foam")
    add(20.75, 310, TUB_IN - RB, "H", "tub")
    add(22.17, 885, TOWEL[2] - RB + 26, "S", "towel")
    x, y = step_top(1, 2)
    add(22.80, x, y - RB, "H")
    x, y = step_top(0, 2)
    add(23.97, x, y - RB, "H")
    add(24.92, BEHIND_R, FLOOR_C_Y, "H")
    add(25.82, 520, SEAT_C, "S")
    add(26.62, 470, SEAT_C, "S")
    add(27.52, BEHIND_L, FLOOR_C_Y, "H")
    add(28.42, 400, SEAT_C, "S")
    add(29.22, 460, SEAT_C, "S")
    add(30.02, 380, SEAT_C, "S")
    add(30.82, 440, SEAT_C, "S")
    add(31.62, 400, SEAT_C, "S")
    for t in (32.45, 33.33, 34.21, 35.15):
        add(t, 0, 0, "W")
    add(36.45, BEHIND_R, FLOOR_C_Y, "H")
    for t in (37.35, 38.23, 39.11, 39.99, 40.87, 41.75, 42.63, 43.51):
        add(t, 0, 0, "W")
    add(44.39, 0, 0, "WM", "muffle")
    add(45.24, 0, 0, "W")
    add(46.05, 0, 0, "W")
    add(46.95, STILL[0] + 8, STILL[1] - RS - RB, "H", "still")
    for t in (47.60, 48.48, 49.36, 50.24):
        add(t, 0, 0, "W")
    add(51.05, 0, 0, "WM", "muffle")
    add(51.87, 0, 0, "W")
    add(53.00, 600, POUF_C + 12, "S")
    add(53.62, 592, POUF_C + 12, "S")
    add(54.16, 604, POUF_C + 12, "S")
    add(54.98, 0, 0, "CH", "payoff")
    add(55.95, 600, POUF_C + 12, "S")
    t = 55.95
    while t < 58.2:
        t = round(t + 0.36, 2)
        add(t, 590 + (8 if len(C) % 2 else -8), POUF_C + 12, "S")
    add(t + 0.72, 600, POUF_C + 12, "S")          # le rebond plus haut, visage au-dessus de Still
    add(t + 1.08, 595, POUF_C + 12, "S")
    add(60.25, BEHIND_R, FLOOR_C_Y, "H", "final")
    add(61.35, 680, FLOOR_C_Y - 30, "S", "virtual")
    return sorted(C)


# Les répliques : (déclencheur, texte, clé). « @x » = une voix de la banque.
LINES = [
    (3.90, "Ready or not!", "n_ready"),
    (8.00, "@bea", "b_bea"),
    (8.93, "@beabea", "b_beabea"),
    (10.54, "@beam_cri", "b_cri"),
    (11.49, "@crush", "c_found1"),
    (17.70, "@blub_peur", "bl_peur"),
    (18.73, "@float_agace", "f_agace"),
    (20.04, "@crush", "c_found2"),
    (25.82, "@crush_q", "c_q1"),
    (28.85, "@beam_petit", "b_petit1"),
    (30.90, "@crush", "c_bof"),
    (32.95, "@crush_q", "c_q2"),
    (35.00, "@crush_fort", "c_stomp"),
    (37.35, "@crush_q", "c_q3"),
    (38.60, "Found ones can help!", "n_help"),
    (40.00, "@beam_cri", "b_help"),
    (40.95, "@float_sec", "f_help"),
    (42.32, "@crush_q", "c_q4"),
    (45.30, "@crush_q", "c_q5"),
    (47.85, "@crush", "c_found3"),
    (48.73, "@float_glacial", "f_glacial"),
    (49.95, "Everyone found!", "n_all"),
    (51.95, "@crush_fort", "c_joy"),
    (53.55, "Who should seek next?", "n_next"),
    (56.95, "@crush", "c_lean"),
    (58.20, "@beam_petit", "b_petit2"),
]

T_SNEEZE = 10.54
T_FOUND = {"beam": 11.49, "float": 20.04, "blub": 20.04, "still": 47.85, "bounce": 60.25}
T_WIG = 19.62
T_CHUNK = 19.15
T_JOY_UP, T_JOY_LAND = 51.85, 52.35
T_STOMP_UP, T_STOMP_LAND = 34.52, 35.00
T_HELP = 39.55
# la perruque : épaisseur perdue à chaque rebond dedans
WIG_LOSS = {32.45: 8, 33.33: 12, 34.21: 12, 35.15: 30, 37.35: 8, 38.23: 8, 39.11: 7, 39.99: 7, 40.87: 6, 41.75: 5,
            42.63: 4, 43.51: 3, 44.39: 4, 45.24: 3, 46.05: 3, 47.60: 4, 48.48: 4, 49.36: 4, 50.24: 4, 51.05: 3, 51.87: 3}
WIG0 = 150.0


def cam_at(t):
    return keys(t, [(0.0, 0.0), (14.85, 0.0), (15.95, CAM_UP), (22.10, CAM_UP), (23.30, 0.0)])


# Crush : position (images clés), sauts, regard, humeur
CRUSH_PATH = [
    (0.0, (172.0, 1435.0)), (5.9, (172.0, 1435.0)), (6.55, (195.0, 1435.0)), (7.05, (195.0, 1435.0)),
    (7.65, (210.0, 1435.0)), (12.40, (210.0, 1435.0)), (13.00, (385.0, 1435.0)), (14.60, (385.0, 1435.0)),
    (15.35, (808.0, 1435.0)), (16.45, (742.0, 1120.0)), (17.55, (828.0, 840.0)), (18.70, (760.0, 585.0)),
    (19.55, (735.0, FB - RC)), (20.20, (640.0, FB - RC)), (21.80, (640.0, FB - RC)), (22.30, (735.0, FB - RC)),
    (23.00, (760.0, 585.0)), (23.95, (828.0, 840.0)), (24.90, (742.0, 1120.0)), (25.95, (808.0, 1435.0)),
    (27.25, (340.0, 1435.0)), (29.40, (340.0, 1435.0)), (30.25, (808.0, 1435.0)), (30.95, (808.0, 1435.0)),
    (31.95, (340.0, 1435.0)), (45.75, (340.0, 1435.0)), (46.65, (392.0, 1435.0)), (56.40, (392.0, 1435.0)),
    (57.30, (372.0, 1395.0)), (61.4, (372.0, 1395.0)),
]
CRUSH_HOPS = [(5.9, 6.55, 95), (7.05, 7.65, 95), (12.40, 13.00, 50), (14.60, 15.35, 40), (25.95, 27.25, 40),
              (29.40, 30.25, 40), (30.95, 31.95, 40), (T_STOMP_UP, T_STOMP_LAND, 120), (T_JOY_UP, T_JOY_LAND, 160)]
CRUSH_LOOK = [
    (0.0, (0.0, 0.0)), (4.3, (0.6, 0.0)), (4.8, (0.2, -0.2)), (5.4, (-0.3, -0.1)), (6.0, (0.9, 0.2)),
    (7.9, (0.5, 0.9)), (11.3, (-0.9, 0.7)), (12.3, (0.9, 0.0)), (13.4, (0.95, 0.1)), (13.95, (0.9, -0.6)),
    (19.8, (-0.9, 0.7)), (21.35, (-0.4, 0.4)), (21.55, (0.7, -0.9)), (22.5, (0.6, 0.6)), (26.0, (-0.8, 0.5)),
    (27.6, (0.9, 0.3)), (28.4, (0.95, 0.4)), (29.3, (0.95, 0.4)), (30.3, (-0.6, 0.6)), (30.95, (-0.95, 0.6)),
    (31.5, (-0.9, 0.0)), (32.3, (-0.3, 0.0)), (33.1, (0.8, -0.3)), (33.6, (-0.8, -0.3)), (34.1, (0.0, 0.8)),
    (36.55, (0.95, 0.3)), (38.0, (0.9, 0.2)), (40.0, (-0.95, 0.3)), (41.0, (0.9, -0.5)), (42.3, (-0.9, 0.3)),
    (42.8, (0.9, -0.2)), (43.25, (0.0, -1.0)), (44.2, (0.0, -1.0)), (44.5, (0.0, -0.95)), (45.8, (0.0, -0.5)),
    (47.30, (0.0, -0.5)), (47.70, (0.95, 0.2)), (49.9, (0.0, 0.0)), (50.3, (-0.9, 0.3)), (50.6, (0.8, -0.4)),
    (50.9, (0.95, 0.3)), (51.2, (0.0, 0.0)), (51.05, (0.0, -0.9)), (51.4, (0.0, 0.0)),
    (55.05, (0.0, -1.0)), (56.3, (0.0, -1.0)), (56.8, (0.95, 0.35)), (61.4, (0.95, 0.35)),
]
CRUSH_LOOK.sort(key=lambda k: k[0])
CRUSH_MOOD = [(0.0, "neutre"), (49.9, "joie"), (55.0, "neutre")]
CRUSH_WIDE = [(0.0, 0.0), (44.39, 0.0), (44.45, 1.0), (45.6, 0.6), (46.5, 0.2), (47.7, 0.0), (48.0, 1.0),
              (48.8, 0.3), (49.5, 0.0), (55.0, 0.0), (55.05, 1.0), (56.4, 0.4), (57.2, 0.0)]


class Sim:
    scene_top = 0.27

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
        self.lines = [(t, txt, k) for (t, txt, k) in LINES]
        self.C = build_contacts()
        self._resolve_contacts()
        self.hits = [(c[0], c[4] if c[4] == "muffle" else "h") for c in self.C if c[3] in ("H", "WM", "CH") and 0 < c[0] < 61.2]
        self.hi = 0
        self.payoff_at = [c[0] for c in self.C if c[4] == "payoff"][0]
        self.end_s = 61.15
        self._particles()

    # ---------------------------------------------------------- Crush
    def crush(self, t):
        x, y = keys(t, CRUSH_PATH)
        hop = 0.0
        for (a, b, h) in CRUSH_HOPS:
            if a <= t <= b:
                s = (t - a) / (b - a)
                n = 1 if h >= 90 else max(1, round((b - a) / 0.42))
                hop = h * abs(math.sin(math.pi * s * n))
        # en montant ou descendant l'escalier, il sautille de marche en marche
        if 15.35 < t < 19.55 or 22.30 < t < 25.95:
            hop = 26 * abs(math.sin(math.pi * (t - 15.35) / 0.36))
        sx, sy = 1.0, 1.0
        if t < 4.0:                       # aplati contre le mur, il compte
            sx, sy = 0.86, 1.08
            x -= 14
        elif t < 4.5:
            k = ease((t - 4.0) / 0.5)
            sx, sy = lerp(0.86, 1.0, k), lerp(1.08, 1.0, k)
            x -= 14 * (1 - k)
        for land in (6.55, 7.65, T_STOMP_LAND, T_JOY_LAND):
            d = t - land
            if 0 <= d < 0.45:
                q = (0.16 if land in (T_STOMP_LAND, T_JOY_LAND) else 0.08) * math.exp(-d * 7) * math.cos(d * 20)
                sx, sy = sx + q, sy - q
        y = y - hop + RC * (1 - sy)
        return x, y, sx, sy

    def crush_top(self, t):
        x, y, sx, sy = self.crush(t)
        return x, y - RC * sy

    def wig(self, t):
        if t < T_WIG or t >= T_JOY_LAND:
            return 0.0
        w = WIG0
        for tc, d in WIG_LOSS.items():
            if t >= tc + 0.08:
                w -= d
        return max(0.0, w)

    def _resolve_contacts(self):
        for c in self.C:
            t, kind = c[0], c[3]
            if kind in ("W", "WM", "CH"):
                x, top = self.crush_top(t)
                w = self.wig(t - 0.01)
                if kind == "W":
                    c[1], c[2] = x + (6 if int(t * 10) % 2 else -6), top - w * 0.55 - RB
                elif kind == "WM":
                    c[1], c[2] = x, top - 3 - RB
                else:
                    c[1], c[2] = x, top - RB
        self.C = sorted(self.C)

    # ---------------------------------------------------------- Bounce
    def bounce_at(self, t):
        C = self.C
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                T = b[0] - a[0]
                s = t - a[0]
                v0 = (a[2] - b[2]) / T + G * T / 2
                return a[1] + (b[1] - a[1]) * s / T, a[2] - v0 * s + 0.5 * G * s * s
        if t < C[0][0]:
            return C[0][1], C[0][2]
        return C[-1][1], C[-1][2]

    def contact_near(self, t, kinds, tags=None, win=0.16):
        for c in self.C:
            if c[3] in kinds and abs(t - c[0]) < win and (tags is None or c[4] in tags):
                return c
        return None

    def layer(self, t):
        if 5.95 <= t <= 7.62:
            return "back"
        if 14.95 <= t <= 25.0 or 32.2 <= t <= 52.9 or 54.55 <= t <= 55.5:
            return "front"
        hp = self.high_pop_t()
        if hp is not None and abs(t - hp) < 0.3:
            return "front"
        return "mid"

    # ---------------------------------------------------------- particules (calculées d'avance)
    def _particles(self):
        rng = np.random.default_rng(11)
        P = []          # (t0, x0, y0, vx, vy, r, col, t_fin, sol)

        def burst(t0, x0, y0, n, sp, up, r0, col, floor, life=2.5, spread=1.0):
            for _ in range(n):
                a = rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
                v = rng.uniform(0.4, 1.0) * sp
                P.append((t0, x0 + rng.uniform(-30, 30), y0 + rng.uniform(-20, 20), math.cos(a) * v * spread,
                          math.sin(a) * v - up, rng.uniform(0.6, 1.2) * r0, col, t0 + life, floor))
        for c in self.C:
            if c[4] == "foam":
                burst(c[0], c[1], c[2] + 60, 16, 900, 300, 24, FOAM, FB, 2.2)
            if c[4] == "tub":
                burst(c[0], c[1], WATER, 14, 700, 200, 10, WATER_C, FB, 1.2)
        for c in self.C:
            if c[3] in ("W", "WM"):
                loss = WIG_LOSS.get(c[0], 3)
                for side in (-1, 1):
                    for _ in range(int(1 + loss / 5)):
                        P.append((c[0], c[1] + side * rng.uniform(95, 135), c[2] + RB - 5, side * rng.uniform(120, 320),
                                  -rng.uniform(150, 420), 8 + loss * 0.45 * rng.uniform(0.7, 1.2), FOAM, c[0] + 3.0, FL))
        # le saut de Crush arrache un gros morceau ; son saut de joie fait tout exploser
        x, top = self.crush_top(T_STOMP_LAND)
        burst(T_STOMP_LAND, x, top - 40, 10, 500, 200, 26, FOAM, FL, 3.0, 1.8)
        x, top = self.crush_top(T_JOY_LAND)
        for _ in range(70):
            a = rng.uniform(0, 2 * math.pi)
            v = rng.uniform(250, 1100)
            P.append((T_JOY_LAND, x + rng.uniform(-60, 60), top - 20, math.cos(a) * v, math.sin(a) * v - 700,
                      rng.uniform(8, 22), FOAM, T_JOY_LAND + 4.5, FL))
        self.parts = P
        self.flakes_g = 900.0

    # ---------------------------------------------------------- moteur
    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "bounce"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def hero_mood(self):
        return "lose"

    def speaking(self, t, key):
        for n in self.narr:
            if n["key"] == key and n["start"] <= t <= n["end"]:
                return (t - n["start"]) / max(0.01, n["end"] - n["start"])
        return None

    def said_since(self, t, key):
        for n in self.narr:
            if n["key"] == key:
                return t - n["start"]
        return -99.0

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        cam = cam_at(t)

        def Y(y):
            return (y - cam) * S

        def X(x):
            return x * S

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([X(x0), Y(y0), X(x1), Y(y1)], fill=col)

        def ell(x, y, rx, ry, col, outline=None, w=0):
            dr.ellipse([X(x - rx), Y(y - ry), X(x + rx), Y(y + ry)], fill=col, outline=outline, width=w)

        def poly(pts, col):
            dr.polygon([(X(px), Y(py)) for px, py in pts], fill=col)

        bx, by = self.bounce_at(t)

        def dent(x0, x1, ytop, depth_max=34):
            """La surface molle se creuse sous Bounce."""
            d = max(0.0, by + RB - ytop)
            if d <= 0 or not (x0 - RB < bx < x1 + RB):
                return 0.0
            return min(depth_max, d)

        # ---- la maison
        rect(0, CB - 200, W, H + 400, NIGHT)
        rect(WL, CEIL, WR, FL, WALL_LR)
        rect(WL, CB, WR, FB, WALL_BA)
        for i in range(int((WR - WL) / 60) + 1):            # carrelage de la salle de bain
            dr.line([(X(WL + i * 60), Y(CB)), (X(WL + i * 60), Y(FB))], fill=(36, 48, 62), width=int(2 * S))
        for j in range(int((FB - CB) / 60) + 1):
            dr.line([(X(WL), Y(CB + j * 60)), (X(WR), Y(CB + j * 60))], fill=(36, 48, 62), width=int(2 * S))
        rect(0, FB, COL0, CEIL, SLAB_C)
        rect(0, CB - 40, W, CB, SLAB_C)
        rect(0, FL, W, FL + 60, FLOOR_C)
        rect(0, CB - 40, WL, FL + 60, SLAB_C)
        rect(WR, CB - 40, WR + 25, FL + 60, SLAB_C)
        # la fenêtre du salon et son cadre (le cadre penche au saut de Crush)
        rect(80, 700, 250, 930, (20, 26, 52))
        ell(200, 760, 26, 26, (230, 226, 190))
        rect(162, 700, 168, 930, (60, 56, 70)); rect(80, 812, 250, 818, (60, 56, 70))
        tilt = 0.0 if t < T_STOMP_LAND else min(0.22, (t - T_STOMP_LAND) * 2.0)
        cx, cy = 450, 820
        pts = [(-70, -55), (70, -55), (70, 55), (-70, 55)]
        poly([(cx + u * math.cos(tilt) - v * math.sin(tilt), cy + u * math.sin(tilt) + v * math.cos(tilt)) for u, v in pts], (96, 80, 56))
        pts = [(-58, -43), (58, -43), (58, 43), (-58, 43)]
        poly([(cx + u * math.cos(tilt) - v * math.sin(tilt), cy + u * math.sin(tilt) + v * math.cos(tilt)) for u, v in pts], (60, 86, 92))
        # le miroir de la salle de bain
        rect(640, -260, 760, -60, (70, 90, 110)); rect(650, -250, 750, -70, (120, 150, 170))
        # l'escalier (au fond)
        for f, (x0, y0, x1, y1) in enumerate(stair_flights()):
            for k in range(4):
                xa = x0 + (x1 - x0) * k / 4
                xb = x0 + (x1 - x0) * (k + 1) / 4
                yt = y0 + (y1 - y0) * (k + 1) / 4
                lo, hi = min(xa, xb), max(xa, xb)
                rect(lo, yt, hi, yt + 18, STAIR_C)
            poly([(x0, y0), (x1, y1), (x1, y1 + 30), (x0, y0 + 30)], STAIR_D)
        rect(680, 1213, 761, 1231, STAIR_C)
        rect(874, 866, 935, 884, STAIR_C)
        # la pile de serviettes
        d = dent(TOWEL[0], TOWEL[1], TOWEL[2]) if self.contact_near(t, ("S",), ("towel",), 0.2) else 0.0
        for i, col in enumerate(((210, 120, 120), (120, 170, 210), (230, 210, 140))):
            y0 = 866 - 20 * (i + 1) + (d * (i + 1) / 3)
            rect(TOWEL[0], y0, TOWEL[1], y0 + 20, col)
        # le compte, sur le mur
        if t < 3.9:
            num = "3" if t < 2.1 else ("2" if t < 3.0 else "1")
            last = 0.0 if t < 2.1 else (2.1 if t < 3.0 else 3.0)
            sh = 10 * math.exp(-(t - last) * 8) * math.sin((t - last) * 50) if last else 0.0
            dr.text((X(220 + sh), Y(870)), num, fill=(245, 245, 250), anchor="mm", font=font(int(300 * S)),
                    stroke_width=int(8 * S), stroke_fill=(10, 10, 16))

        # ---- le canapé (le dos d'abord : Bounce peut passer derrière)
        jump = 0.0
        if T_SNEEZE <= t <= T_SNEEZE + 0.45:
            jump = 75 * math.sin(math.pi * (t - T_SNEEZE) / 0.45)
        if self.layer(t) == "back":
            base.ball(dr, X(bx), Y(by), RB * S)
        rect(SOFA_X0, SOFA_BACK - jump, SOFA_X1, FL - 6 - jump, SOFA_B)
        db = dent(SOFA_X0, SOFA_X1, SOFA_BACK) if self.contact_near(t, ("S",), ("backtop",), 0.2) else 0.0
        dr.rounded_rectangle([X(SOFA_X0 + 10), Y(SOFA_BACK - 14 - jump + db * 0.6), X(SOFA_X1 - 10), Y(SOFA_SEAT - jump)],
                             radius=int(24 * S), fill=SOFA_C)
        # poussière soulevée
        for c in self.C:
            if (c[4] == "back" or (c[3] == "S" and abs(c[2] - SEAT_C) < 1)) and c[0] < T_SNEEZE + 0.1:
                dd = t - c[0]
                if 0 <= dd < 2.4:
                    for j in range(6):
                        px = c[1] + (j - 2.5) * 20 + dd * (418 - c[1]) * 0.35 - dd * 30
                        py = SOFA_UNDER + 70 - dd * 25 - (j % 3) * 22
                        rr = 16 + 12 * dd + (j % 2) * 6
                        ell(px, py, rr, rr * 0.8, mix(WALL_LR, DUST, 0.8 * (1 - dd / 2.4)))
        # l'assise, les accoudoirs, les pieds
        ds = dent(SOFA_X0, SOFA_X1, SOFA_SEAT) if (self.layer(t) != "back" and SOFA_X0 - 60 < bx < SOFA_X1 + 60
                                                   and by > SOFA_SEAT - RB - 40 and by < SOFA_SEAT) else 0.0
        seat = [(SOFA_X0 + 6, SOFA_SEAT + 90 - jump)]
        for i in range(29):
            xx = SOFA_X0 + 6 + (SOFA_X1 - SOFA_X0 - 12) * i / 28
            k = max(0.0, 1 - ((xx - bx) / (RB * 1.1)) ** 2) if ds > 0 else 0.0
            seat.append((xx, SOFA_SEAT - jump + ds * k))
        seat.append((SOFA_X1 - 6, SOFA_SEAT + 90 - jump))
        poly(seat, SOFA_C)
        rect(SOFA_X0 + 6, SOFA_SEAT + 60 - jump, SOFA_X1 - 6, SOFA_UNDER - jump, SOFA_D)
        for ax in (SOFA_X0 - 14, SOFA_X1 - 30):
            dr.rounded_rectangle([X(ax), Y(SOFA_SEAT - 60 - jump), X(ax + 44), Y(SOFA_UNDER - jump)], radius=int(16 * S), fill=SOFA_D)
        for lx in (SOFA_X0 + 8, SOFA_X1 - 24):
            rect(lx, SOFA_UNDER - jump, lx + 16, FL - jump * 0.2, (60, 40, 34))
        # éclair rouge de l'éternuement
        if T_SNEEZE <= t <= T_SNEEZE + 0.35:
            k = 1 - (t - T_SNEEZE) / 0.35
            cxs, cys = 418, SOFA_UNDER + 90
            pts = []
            for i in range(16):
                rr = (160 if i % 2 == 0 else 60) * (0.6 + 0.6 * (1 - k))
                a = i * math.pi / 8
                pts.append((cxs + rr * math.cos(a), cys + rr * math.sin(a) * 0.6))
            poly(pts, mix(WALL_LR, (255, 70, 70), k))

        # ---- la salle de bain : baignoire, eau, Float, Blub, mousse
        if cam < -60:
            self.draw_bath(dr, t, S, X, Y, bx, by)

        # ---- l'étage reste caché tant que la caméra n'y monte pas
        k = max(0.0, min(1.0, cam / CAM_UP))
        band = 520.0 * (1 - k) ** 1.5
        if band > 1:
            dr.rectangle([0, 0, W * S, band * S], fill=NIGHT)
            dr.rectangle([0, max(0.0, band - 40) * S, W * S, band * S], fill=SLAB_C)
        # ---- le coussin de sol derrière Still
        dp = dent(POUF[0], POUF[1], FL - POUF[2]) if self.layer(t) == "mid" and abs(bx - 600) < 80 and by > POUF_C - 30 else 0.0
        pts = [(POUF[0] - 10, FL)]
        for i in range(21):
            xx = POUF[0] + (POUF[1] - POUF[0]) * i / 20
            k = max(0.0, 1 - ((xx - bx) / RB) ** 2) if dp > 0 else 0.0
            pts.append((xx, FL - POUF[2] + dp * k))
        pts.append((POUF[1] + 10, FL))
        poly(pts, (170, 90, 60))

        if self.layer(t) == "mid":
            base.ball(dr, X(bx), Y(by), RB * S)
        # Still : elle ne bouge jamais
        M["clip4"].draw_still(dr, STILL[0], STILL[1] - cam, RS)
        dr.ellipse([X(STILL[0] - RS), Y(STILL[1] - RS), X(STILL[0] + RS), Y(STILL[1] + RS)], outline=(250, 250, 210), width=int(3 * S))
        # les trouvés hors de leur cachette
        self.draw_beam_state(dr, t, S, X, Y, under=False)
        if t >= T_HELP:
            self.draw_float(dr, t, S, X, Y)
            self.draw_blub(dr, t, S, X, Y)
        # Crush et sa perruque
        self.draw_crush(dr, t, S, X, Y, bx, by)
        # Beam, sous le canapé (dessiné après les halos de Crush et de Still, qui sinon le couvrent)
        self.draw_beam_state(dr, t, S, X, Y, under=True)
        # particules : mousse, gouttes, flocons
        for (t0, x0, y0, vx, vy, r, col, t1, floor) in self.parts:
            dd = t - t0
            if 0 <= dd <= t1 - t0:
                g = 1500.0 if col == FOAM else 2200.0
                px = x0 + vx * dd * (0.6 if col == FOAM else 1.0)
                py = y0 + vy * dd + 0.5 * g * dd * dd
                if py > floor - r:
                    py = floor - r
                    px = x0 + vx * 0.6 * math.sqrt(max(0.0, 2 * (floor - r - y0) / g)) if col == FOAM else px
                ell(px, py, r, r * 0.85, col)
        if self.layer(t) == "front":
            base.ball(dr, X(bx), Y(by), RB * S)
        # la mousse qui vole jusqu'à la tête de Crush
        if T_CHUNK <= t < T_WIG:
            s = (t - T_CHUNK) / (T_WIG - T_CHUNK)
            x1, top = self.crush_top(T_WIG)
            px = lerp(420, x1, s)
            py = lerp(230, top - 60, s) - 260 * math.sin(math.pi * s)
            for (u, v, r) in ((0, 0, 46), (-34, 14, 32), (34, 12, 34), (0, -30, 30)):
                ell(px + u, py + v, r, r * 0.9, FOAM)
        # les bulles de Blub
        sb = self.said_since(t, "bl_peur")
        if 0 <= sb < 2.5:
            for j in range(7):
                ph = (sb * 1.4 + j / 7) % 1.0
                if sb * 1.4 > j / 7:
                    yb = lerp(420, WATER - 10, ph)
                    ell(BLUB0[0] + 14 * math.sin(j * 2 + sb * 6), yb, 9 + j % 3 * 3, 9 + j % 3 * 3, (220, 240, 255), outline=(255, 255, 255), w=int(2 * S))
        # les tampons FOUND
        for who, tf in T_FOUND.items():
            if t >= tf:
                px, py = self.pos_of(who, t)
                dd = t - tf
                k = 1.0 + 0.8 * math.exp(-dd * 12)
                flash = 1.0
                if who != "bounce" and 50.05 <= t <= 51.25:
                    idx = ["beam", "float", "blub", "still"].index(who)
                    flash = 1.35 if abs(t - (50.15 + 0.25 * idx)) < 0.12 else 1.0
                R = {"beam": RBM, "float": RF, "blub": RBL, "still": RS, "bounce": RB}[who]
                if (py + R - cam) * 1.0 > 520.0 * (1 - max(0.0, min(1.0, cam / CAM_UP))) ** 1.5 + 30:
                    self.stamp(dr, px + (25 if who == "bounce" else 0), py + (0.52 * R if who != "bounce" else -0.55 * R), k * flash * (0.8 if who != "bounce" else 1.0), S, Y)

    def pos_of(self, who, t):
        if who == "beam":
            return self.beam_pos(t)[:2]
        if who == "float":
            return self.float_pos(t)[:2]
        if who == "blub":
            return self.blub_pos(t)[:2]
        if who == "still":
            return STILL
        bx, by = self.bounce_at(t)
        return bx, by

    def stamp(self, dr, x, y, k, S, Y):
        f = font(int(44 * k * S))
        dr.text((x * S, Y(y)), "FOUND", fill=(255, 255, 255), anchor="mm", font=f,
                stroke_width=int(6 * k * S), stroke_fill=(200, 30, 50))

    # ---------------------------------------------------------- les personnages
    def beam_pos(self, t):
        if t < T_SNEEZE:
            return 418.0, FL - RBM, 0.0
        if t < T_SNEEZE + 0.9:
            s = ease((t - T_SNEEZE) / 0.9)
            return lerp(418, 115, s), FL - RBM, -s * 6.0
        x, y = 115.0, FL - RBM
        hop = 0.0
        p = self.speaking(t, "b_help")
        if p is not None or 39.65 <= t <= 40.0:
            hop = 70 * abs(math.sin(math.pi * min(1.0, (t - 39.65) / 0.5)))
        if 44.39 <= t <= 44.85:
            hop = 110 * math.sin(math.pi * (t - 44.39) / 0.46)
        if 41.2 <= t <= 42.2:
            hop = 50 * abs(math.sin(math.pi * (t - 41.2) / 0.5))
        return x, y - hop, -6.0

    def draw_beam_state(self, dr, t, S, X, Y, under):
        if under != (t < T_SNEEZE):
            return
        x, y, rot = self.beam_pos(t)
        n_dust = sum(1 for c in self.C if (c[4] == "back" or (c[3] == "S" and abs(c[2] - SEAT_C) < 1)) and 4.0 < c[0] <= t)
        nose = min(1.0, n_dust / 6.0) if t < T_SNEEZE + 1.2 else 0.3
        tilt, squint, shy = 0.0, 0.0, 0.0
        p = self.speaking(t, "b_bea")
        if p is not None:
            tilt, squint = -0.25 * ease(p * 1.5), 0.6
        p = self.speaking(t, "b_beabea")
        if p is not None:
            tilt, squint = -0.32 - 0.06 * math.sin(p * 14), 0.8
        if T_SNEEZE <= t <= T_SNEEZE + 0.6:
            tilt, squint = 0.15, 1.0
        if not under:
            tilt = 0.0 if rot == 0 else (rot if t < T_SNEEZE + 0.9 else 0.0)
            if self.speaking(t, "b_petit1") is not None or 28.6 < t < 30.2:
                shy = 1.0
            if self.speaking(t, "b_help") is not None or 41.0 < t < 47.0:
                tilt = 0.35
            if 48.7 <= t <= 51.0:
                tilt, squint = -0.1, 1.0
            if t >= 57.9:
                x += 3 * math.sin(t * 60)
                shy = 1.0
        sq = 0.0
        if 48.7 <= t <= 51.0:
            sq = 0.12
        y = y + RBM * sq
        M["beam"].draw_beam(dr, x, y - (self._cam(t)), RBM, S, tilt=tilt, squint=squint, shy=shy, sq=sq, nose=nose)

    def _cam(self, t):
        return cam_at(t)

    def float_pos(self, t):
        if t < T_HELP:
            return FLOAT0[0], FLOAT0[1], 0.0
        kf = [(T_HELP, FLOAT0), (T_HELP + 0.5, (720.0, 420.0)), (T_HELP + 0.9, (790.0, 700.0)),
              (T_HELP + 1.3, (step_top(2, 1)[0], step_top(2, 1)[1] - RF))]
        x, y = keys(t, kf)
        a = 0.0
        if T_HELP + 1.3 <= t:
            p = self.speaking(t, "f_help")
            if p is not None or 41.0 <= t <= 42.2:
                y -= 60 * abs(math.sin(math.pi * (t - 40.95) / 0.34))
                a = -0.35
            if 42.2 < t < 48.6:
                a = -0.25
            if 44.39 <= t <= 44.85:
                y -= 110 * math.sin(math.pi * (t - 44.39) / 0.46)
        return x, y, a

    def draw_float(self, dr, t, S, X, Y):
        x, y, a = self.float_pos(t)
        c4 = M["clip4"]
        c4.RF = RF
        if t < 16.8:
            e = "serene"
        elif t < 18.5:
            e = "slit"
        elif t < 20.75:
            e = "squint"
        elif t < 21.7:
            e = "calm"
        elif t < 40.9:
            e = "squint_flat"
        elif t < 42.2:
            e = "wide_o"
        elif t < 48.7:
            e = "squint"
        elif t < 49.5:
            e = "glacial"
        else:
            e = "calm"
        mouth = 0.0
        for k in ("f_agace", "f_help", "f_glacial"):
            if self.speaking(t, k) is not None:
                mouth = 0.8 * abs(math.sin(t * 14))
        c4.draw_float(dr, c4.VIEW, x, y - cam_at(t), a, c4.EXPR[e], (0.0, 0.0), mouth, 0.0, 0.0)

    def blub_pos(self, t):
        if t < T_HELP:
            sb = self.said_since(t, "bl_peur")
            y = BLUB0[1] if sb < 0 else lerp(BLUB0[1], TUB_IN - RBL, ease(sb / 0.5))
            return BLUB0[0], y
        kf = [(T_HELP, (BLUB0[0], TUB_IN - RBL)), (T_HELP + 0.6, (720.0, 420.0)), (T_HELP + 1.1, (846.0, 800.0)),
              (T_HELP + 1.6, (step_top(1, 3)[0], step_top(1, 3)[1] - RBL))]
        x, y = keys(t, kf)
        if 44.39 <= t <= 44.85:
            y -= 100 * math.sin(math.pi * (t - 44.39) / 0.46)
        return x, y

    def draw_blub(self, dr, t, S, X, Y):
        x, y = self.blub_pos(t)
        if t < 17.7:
            mood = "joie"
        elif t < T_HELP:
            mood = "peur"
        elif t < 49.0:
            mood = "retient"
        else:
            mood = "joie"
        talk = 0.0
        if self.speaking(t, "bl_peur") is not None:
            talk = abs(math.sin(t * 14))
        M["blub"].draw_blub(dr, x, y - cam_at(t), RBL, S, mood=mood, talk=talk)
        dr.ellipse([X(x - RBL), Y(y - RBL), X(x + RBL), Y(y + RBL)], outline=(235, 240, 255), width=int(4 * S))

    def draw_bath(self, dr, t, S, X, Y, bx, by):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([X(x0), Y(y0), X(x1), Y(y1)], fill=col)

        def ell(x, y, rx, ry, col):
            dr.ellipse([X(x - rx), Y(y - ry), X(x + rx), Y(y + ry)], fill=col)
        # la baignoire en coupe : parois, eau claire
        rect(TUB_X0, TUB_RIM, TUB_X1, FB, (200, 206, 220))
        rect(TUB_X0 + 18, TUB_RIM, TUB_X1 - 18, TUB_IN, (40, 54, 70))
        rect(TUB_X0 + 18, WATER, TUB_X1 - 18, TUB_IN, WATER_C)
        for (px, py) in ((60, FB), (TUB_X1 - 40, FB)):
            rect(px, FB - 6, px + 24, FB, (160, 160, 170))
        if t < T_HELP:
            self.draw_blub(dr, t, S, X, Y)
            self.draw_float(dr, t, S, X, Y)
        # la montagne de mousse : des tas qui partent à chaque plongeon
        foam_cs = [c for c in self.C if c[4] == "foam"]
        n_gone = sum(1 for c in foam_cs if t >= c[0])
        heaps = [(110, 300, 70), (235, 250, 72), (300, 200, 95), (390, 190, 95), (470, 230, 80), (540, 280, 60),
                 (250, 300, 60), (430, 300, 70), (350, 290, 80)]
        order = [2, 3, 6, 4, 8, 1, 7, 5, 0]       # l'ordre dans lequel ils s'envolent
        gone = set()
        for i in range(n_gone):
            for j in order[i * 2:i * 2 + 2 + (1 if i == len(foam_cs) - 1 else 0)]:
                gone.add(j)
        if t >= 20.75:
            gone = set(range(len(heaps)))
        for j, (hx, hy, hr) in enumerate(heaps):
            if j in gone:
                continue
            if j == 0 and t < 18.5:
                hy = 352
            ell(hx, hy + 20, hr, hr * 0.6, FOAM_S)
            ell(hx, hy, hr * 0.92, hr * 0.55, FOAM)
        # le rebord de la baignoire par-dessus
        rect(TUB_X0, TUB_RIM - 10, TUB_X1, TUB_RIM + 8, (225, 230, 240))

    def draw_crush(self, dr, t, S, X, Y, bx, by):
        x, y, sx, sy = self.crush(t)
        cam = cam_at(t)
        look = keys(t, CRUSH_LOOK)
        mood = step_keys(t, CRUSH_MOOD)
        wide = keys(t, CRUSH_WIDE)
        blink = 0.0
        if t < 3.95:
            blink = 1.0                                   # il compte, les yeux fermés
        for tb in (13.5, 33.9):
            if 0 <= t - tb < 0.18:
                blink = math.sin(math.pi * (t - tb) / 0.18)
        # le clignement au moment où Bounce surgit au-dessus de Still (le rebond plus haut de la fin)
        hi = self.high_pop_t()
        if hi is not None and 0 <= t - hi < 0.2:
            blink = math.sin(math.pi * (t - hi) / 0.2)
        draw_crush(dr, x, y, RC, S, lambda v: (v - cam) * S, mood=mood, look=look, blink=blink, sx=sx, sy=sy, wide=wide)
        # la perruque de mousse
        w = self.wig(t)
        if t >= T_WIG and w > 0:
            top = y - RC * sy
            d = max(0.0, (by + RB) - (top - w)) if abs(bx - x) < 120 else 0.0
            d = min(d, w * 0.85)
            sway = 0.0
            if 21.2 <= t <= 22.2:
                sway = 30 * math.sin((t - 21.2) * 9) * math.exp(-(t - 21.2) * 2.5)
            ww = RC * (0.62 + 0.45 * min(1.0, w / WIG0))
            hh = max(10.0, w - d)
            if t < T_WIG + 0.25:
                hh *= 0.6 + 1.6 * (t - T_WIG)
            # un tas de mousse : une base posée sur le crâne et des boules au-dessus
            dr.chord([X(x - ww), Y(top - hh), X(x + ww), Y(top + hh * 0.9)], 180, 360, fill=FOAM)
            n = 5 if w > 60 else (3 if w > 20 else 2)
            for i in range(n):
                u = (i - (n - 1) / 2) / max(1, (n - 1) / 2)
                hx = x + u * ww * 0.6 + sway * (1 - abs(u))
                hy = top - hh * (0.75 - 0.3 * abs(u))
                r = ww * 0.32
                if abs(hx - bx) < RB * 0.9 and d > 0:
                    hy += d * 0.4
                dr.ellipse([X(hx - r), Y(hy - r * 0.8), X(hx + r), Y(hy + r * 0.8)], fill=FOAM)
                dr.ellipse([X(hx - r * 0.5), Y(hy - r * 0.6), X(hx + r * 0.1), Y(hy - r * 0.2)], fill=(255, 255, 255))

    def high_pop_t(self):
        tail = [c for c in self.C if c[0] > 56.0 and c[3] == "S"]
        for a, b in zip(tail, tail[1:]):
            if b[0] - a[0] > 0.6:
                return (a[0] + b[0]) / 2
        return None


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.6,
            "sub_y": 0.165, "sub_font_size": 58, "show_counter": False, "narr_tail_s": 0.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
