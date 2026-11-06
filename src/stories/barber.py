"""
Prototype « barber » : Bounce attend son tour chez le coiffeur, sur le chariot à outils, à côté du fauteuil
où un client à l'afro énorme lit son journal. Chaque « Bounce » fait sursauter le coiffeur (sans visage) : un
coup de tondeuse de travers, une touffe qui part. Le client ne voit rien, caché derrière son journal.

Paliers : les sursauts (raie, entailles, raie centrale) ; le casque antibruit (deux « Bounce » sans sursaut,
puis Bounce rebondit sur l'afro et atterrit sur la tête du coiffeur : la moitié droite part d'un coup) ; le
coussin (deux rebonds muets, puis la lampe : la tondeuse s'envole au ralenti et rase le sommet) ; les touffes
recollées au scotch, la mèche rabattue, qui devient une antenne ; le client baisse son journal, l'antenne
fane, le dernier « Bounce » la coupe (« My hair. ») ; le coiffeur se rase lui-même la banane ; Bounce tombe
dans le tas de cheveux, le coiffeur en fait une perruque et la pose sur le client (« Perfect. ») : la
perruque dit « BOUNCE » et saute, tourne, montre le visage de Bounce, et le dernier sursaut la rase d'un
coup : c'est la coupe de Bounce, chauve, sur la tête chauve du client. Il retourne sur le chariot (boucle).

Toutes les durées de l'histoire sont en temps « récit » (tau) ; un ralenti (lampe) étire le temps réel.
L'audio est calculé sur les instants exacts des contacts, identique quel que soit le nombre d'images/s.

    python3 src/stories/barber.py configs/<name>.json [--simulate]
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
SCR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad"
BANK_DIR = os.environ.get("BARBER_BANK", SCR + "/lundi/barber/voix")
HERO_CACHE = SCR + "/lot6/baby/final"        # la même prise du mot « Bounce » que les autres vidéos

# ------------------------------------------------------------------ voix (banque vérifiée par whisper)
BANK_FILES = {"My hair.": "myhair_am_michael.wav", "Perfect.": "perfect_am_michael.wav"}
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
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    cache = os.path.join(HERO_CACHE, "hero_%s_%s_%s.wav" % key)
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
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

HOOK_T = 0.72
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

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
ZK = 1.15                # zoom de la scène
ZX, ZY = 525.0, 470.0    # point du monde qui reste en (540, 470) à l'écran
DX = 25.0
DY = 60.0                # la scène est dessinée 60 px plus bas que ses coordonnées
G = 2600.0
R = 105.0


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


def lerp2(p, q, k):
    return (lerp(p[0], q[0], k), lerp(p[1], q[1], k))


class KF:
    """Images clés lissées : KF(v0, [(t, v), ...]) ; v peut être un nombre ou un tuple."""
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


def win(t, a, b, fi=0.15, fo=0.15):
    """1 dans [a, b], rampes douces aux bords."""
    if t < a - fi or t > b + fo:
        return 0.0
    return smooth((t - (a - fi)) / max(1e-6, fi)) * smooth(((b + fo) - t) / max(1e-6, fo))


def sh(t):
    """Décalages de section (le plan est écrit en temps de base, puis allongé)."""
    return t


# ------------------------------------------------------------------ ralenti (lampe)
SLOW_A = 22.65        # début du ralenti (temps récit = temps réel à cet instant)
SLOW_L = 1.5              # durée réelle
SLOW_F = 0.33             # vitesse


def warp(t):
    if t < SLOW_A:
        return t
    if t < SLOW_A + SLOW_L:
        return SLOW_A + (t - SLOW_A) * SLOW_F
    return t - SLOW_L * (1 - SLOW_F)


def unwarp(tau):
    if tau < SLOW_A:
        return tau
    if tau < SLOW_A + SLOW_L * SLOW_F:
        return SLOW_A + (tau - SLOW_A) / SLOW_F
    return tau + SLOW_L * (1 - SLOW_F)


# ------------------------------------------------------------------ décor (coordonnées écran 1080×1920)
FLOOR_Y = 1250.0
CART = (170.0, 470.0, 1125.0)            # x0, x1, dessus du plateau
TOWEL = (318.0, 452.0, 40.0)             # x0, x1, épaisseur (posée sur le plateau)
CUSH = (300.0, 462.0, 78.0)
LAMP = (300.0, 600.0)                    # centre du bas de l'abat-jour
HEAD_C = (640.0, 835.0)
HEAD_R = 80.0
AFRO_C = (640.0, 712.0)
AFRO_RX, AFRO_RY = 178.0, 158.0
BARBER_X = 840.0
BHEAD = (836.0, 655.0)
BHEAD_R = 62.0
CROUCH = 70.0             # avec le casque, il se penche sur son travail (genoux fléchis)
HEAP_X = 610.0

# couleurs
WALL = (16, 34, 36)
WALL_L = (22, 44, 46)
TILE_A = (34, 34, 40)
TILE_B = (58, 58, 66)
HAIR = (112, 72, 48)
HAIR_L = (146, 98, 66)
HAIR_D = (62, 38, 26)
SKIN = (196, 138, 104)
SKIN_D = (160, 104, 76)
CAPE = (64, 108, 188)
CAPE_D = (46, 80, 146)
COAT = (226, 230, 236)
COAT_D = (178, 184, 196)
BSKIN = (166, 112, 86)
POMP = (70, 70, 84)
PAPER = (228, 224, 210)
PAPER_D = (150, 146, 136)
CHROME = (150, 158, 172)
CHROME_D = (96, 102, 116)
SEAT = (168, 40, 52)
SEAT_D = (120, 26, 36)
TOWEL_C = (236, 196, 118)
CUSH_C = (110, 196, 166)
CUSH_D = (76, 150, 124)
MUFF = (222, 62, 62)
CLIP_C = (60, 62, 74)
TAPE = (236, 236, 228)
LAMP_C = (214, 190, 118)

# ------------------------------------------------------------------ le plan (temps de base, puis sh())
# points de contact de Bounce (centre de la balle)
SPOT = {"m": (262.0, CART[2] - R), "t": (392.0, CART[2] - TOWEL[2] - R + 16), "c": (390.0, CART[2] - CUSH[2] - R + 34),
        "afro": (565.0, 560.0), "head": (832.0, BHEAD[1] + CROUCH - BHEAD_R - 14 - R), "lamp": (306.0, LAMP[1] + R),
        "heap": (HEAP_X - 10, 1186.0), "skull": (HEAD_C[0], HEAD_C[1] - HEAD_R - R + 6)}
HARD = {"m", "head", "lamp", "skull", "floor"}
# (t, point, gain) ; point « floor » = le sol sous le tas (mot étouffé)
_P = [
    (0.02, "m", 1.1), (0.95, "t", 0), (1.55, "t", 0), (2.30, "m", 1.0), (3.35, "m", 0.9), (4.25, "t", 0),
    (5.45, "m", 1.0), (6.35, "t", 0), (7.30, "m", 1.25), (8.35, "m", 0.95), (9.25, "m", 1.0),
    (10.4, "m", 0.95), (10.95, "t", 0), (11.85, "m", 1.0), (13.1, "m", 1.0), (13.8, "afro", 0), (14.17, "head", 1.4),
    (15.02, "m", 1.05), (15.95, "m", 0.95), (16.85, "t", 0), (17.75, "m", 1.0), (18.7, "m", 0.95), (19.55, "t", 0),
    (20.35, "m", 1.0), (21.25, "c", 0), (22.2, "c", 0), (22.6, "lamp", 1.4), (23.1, "c", 0),
    (24.0, "m", 1.0), (24.9, "m", 0.95), (25.8, "c", 0), (26.7, "m", 1.0), (27.6, "c", 0), (28.5, "m", 0.95),
    (29.4, "m", 1.1), (30.3, "m", 0.95), (31.2, "m", 0.95), (32.1, "c", 0), (33.0, "m", 1.15), (33.95, "m", 0.95),
    (35.0, "c", 0), (35.9, "m", 1.0), (36.8, "c", 0), (37.75, "m", 0.95), (38.55, "c", 0), (39.45, "m", 1.1),
    (40.35, "c", 0), (41.25, "c", 0), (42.45, "m", 1.15), (43.5, "m", 1.0), (44.5, "heap", 0),
    (45.0, "floor", 0.42), (45.45, "heap", 0),
    # 45.6 -> 46.6 : porté dans la boule de cheveux (pas de contact), posé sur la tête du client (mou)
    (46.6, "skull_soft", 0), (47.85, "skull", 1.0), (48.8, "m", 1.05), (49.75, "skull", 1.05),
    (50.15, "skull_soft", 0), (51.1, "skull", 1.1), (52.0, "m", 1.0), (52.95, "skull", 1.0), (53.35, "skull_soft", 0),
    (54.4, "skull", 1.1), (55.35, "m", 1.05), (56.3, "skull", 1.0), (56.7, "skull_soft", 0), (57.6, "skull", 1.35),
    (57.9, "skull_soft", 0),
    (59.9, "m", 1.15),
]
PLAN = [(sh(t), k, g) for (t, k, g) in _P]
CARRY = (45.6, 46.6)                    # Bounce dans la boule de cheveux, dans les mains du coiffeur
END = 59.9 + 0.92
T = dict(
    stop=3.6, muffs_on=10.35, muffs_ready=11.3, thumbs=13.2, head=14.17, presque=16.7, elbow=17.75,
    throw=20.45, lamp=22.6, tape0=25.8, tape_pop=29.4, comb0=30.8, comb1=32.8, spike=33.0, fold=36.35,
    wilt=37.95, snip=39.45, turn_b=41.5, point=41.95, pomp=42.45, turn_bounce=42.85, idea=45.0, scoop=45.6,
    plop=46.6, joy=46.7, wig1=47.85, side=48.8, face=51.1, top=54.4,
    careful=56.7, issue=57.6, leave=58.95, last=59.9)
ISSUE = T["issue"]
LINES_TAU = [(T["snip"] + 1.0, "My hair.", "hair"), (T["plop"] + 0.45, "Perfect.", "perfect")]

# ------------------------------------------------------------------ cheveux de l'afro
_rng = np.random.default_rng(31)


def _afro_puffs():
    pts = []
    tries = 0
    while len(pts) < 140 and tries < 40000:
        tries += 1
        x = _rng.uniform(-1, 1)
        y = _rng.uniform(-1, 1)
        if x * x + y * y > 1:
            continue
        px, py = AFRO_C[0] + x * (AFRO_RX - 30), AFRO_C[1] + y * (AFRO_RY - 28)
        if py > HEAD_C[1] - 10 and abs(px - HEAD_C[0]) < HEAD_R + 30:
            continue
        if py > HEAD_C[1] + 20:
            continue
        if any((px - qx) ** 2 + (py - qy) ** 2 < 21 ** 2 for (qx, qy, _r, _s) in pts):
            continue
        pts.append((px, py, _rng.uniform(31, 41), _rng.uniform(0, 1)))
    return pts


AFRO = _afro_puffs()

# coupes : (t, genre, paramètres)
CUTS = [
    (0.02, "seg", ((525, 600), (640, 636), 27)), (2.30, "seg", ((818, 680), (770, 752), 30)),
    (3.35, "seg", ((595, 590), (652, 594), 26)), (5.45, "seg", ((705, 560), (735, 660), 28)),
    (7.30, "seg", ((640, 540), (640, 800), 32)), (8.35, "seg", ((474, 715), (520, 702), 30)),
    (9.25, "seg", ((768, 590), (806, 626), 32)), (14.17, "half", 652.0),
    (15.02, "seg", ((505, 640), (560, 610), 30)), (17.75, "seg", ((468, 765), (505, 745), 30)),
    (18.7, "seg", ((585, 610), (610, 660), 30)), (22.9, "circ", ((570, 672), 36)),
    (24.0, "seg", ((541, 728), (543, 752), 22)), (30.3, "seg", ((528, 768), (529, 790), 20)),
]
CUTS = [(sh(t), k, p) for (t, k, p) in CUTS]


def _seg_d(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy + 1e-9
    u = clamp01(((px - ax) * vx + (py - ay) * vy) / L2)
    return math.hypot(px - (ax + u * vx), py - (ay + u * vy))


def _apply_cuts():
    cut_t = [None] * len(AFRO)
    cut_dir = [(0.0, -1.0)] * len(AFRO)
    for (t, kind, p) in CUTS:
        for i, (x, y, r, s) in enumerate(AFRO):
            if cut_t[i] is not None:
                continue
            hit = False
            if kind == "seg":
                hit = _seg_d((x, y), p[0], p[1]) < p[2]
                d = (p[1][0] - p[0][0], p[1][1] - p[0][1])
            elif kind == "half":
                hit = x > p
                d = (1.0, -0.4)
            elif kind == "circ":
                hit = math.hypot(x - p[0][0], y - p[0][1]) < p[1]
                d = (x - p[0][0], y - p[0][1])
            if hit:
                cut_t[i] = t
                n = math.hypot(*d) + 1e-6
                cut_dir[i] = (d[0] / n, d[1] / n)
    return cut_t, cut_dir


CUT_T, CUT_DIR = _apply_cuts()
REMAIN = [i for i in range(len(AFRO)) if CUT_T[i] is None]


def _combover_targets():
    """La mèche rabattue : les cheveux restants posés en arc sur le haut du crâne."""
    n = len(REMAIN)
    out = []
    for j in range(n):
        a = math.radians(-172 + 160 * j / max(1, n - 1))
        rr = HEAD_R + 14 + 6 * math.sin(j * 1.7)
        out.append((HEAD_C[0] + rr * math.cos(a), HEAD_C[1] + rr * math.sin(a), 21.0))
    return out


def _antenna_local():
    """L'antenne : une colonne fine au sommet du crâne (coordonnées relatives à sa base)."""
    n = len(REMAIN)
    out = []
    for j in range(n):
        k = j / max(1, n - 1)
        out.append((7 * math.sin(j * 2.1), -10 - 225 * k, 21.0 - 8 * k))
    return out


def ant_curve(ph, j, n, L=235.0):
    """Point j de l'antenne quand son bout est incliné de ph (courbure uniforme : elle plie, elle fane)."""
    k = j / max(1, n - 1)
    steps = 12
    x = y = 0.0
    for i in range(steps):
        s0 = k * (i + 0.5) / steps
        th = ph * s0 ** 1.3
        x += math.sin(th) * L * k / steps
        y -= math.cos(th) * L * k / steps
    return (x, y - 10)


COMB_T = _combover_targets()
ANT_L = _antenna_local()
ANT_BASE = (HEAD_C[0] + 4, HEAD_C[1] - HEAD_R + 6)

# touffes recollées au scotch (prises sur les épaules de la cape) : (départ, position collée)
TAPED = [((520.0, 965.0), (700.0, 640.0)), ((760.0, 965.0), (606.0, 612.0))]

# ------------------------------------------------------------------ particules (touffes qui tombent)
FALL_DT = 1 / 120


def _fall_path(x, y, vx, vy, t0, seed, floor=1238.0, drag=2.6, g=1500.0, sway=1.0):
    rr = np.random.default_rng(seed)
    ph = rr.uniform(0, 6.28)
    pts = []
    t = 0.0
    while True:
        pts.append((x + sway * 14 * math.sin(3.1 * t + ph), y))
        if y >= floor or t > 6:
            break
        vx -= vx * drag * FALL_DT
        vy += (g - vy * drag) * FALL_DT
        x += vx * FALL_DT
        y += vy * FALL_DT
        t += FALL_DT
    return {"t0": t0, "pts": pts, "land": t0 + t, "x_land": min(760.0, max(470.0, x))}


def _build_particles():
    parts = []
    rr = np.random.default_rng(5)
    for i, (x, y, r, s) in enumerate(AFRO):
        if CUT_T[i] is None:
            continue
        dx, dy = CUT_DIR[i]
        sp = rr.uniform(260, 520)
        vx = dx * sp * 0.6 + rr.uniform(-160, 160)
        vy = -rr.uniform(200, 420) + dy * 80
        p = _fall_path(x, y, vx, vy, CUT_T[i], i)
        p["r"] = r * 0.82
        p["s"] = s
        parts.append(p)
    return parts


PARTS = _build_particles()

# ------------------------------------------------------------------ perruque (boule de cheveux, en 3D)


def _wig_points():
    pts = []
    n = 150
    ga = math.pi * (3 - math.sqrt(5))
    rr = np.random.default_rng(9)
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - y * y)
        th = ga * i
        pts.append((math.cos(th) * r, y, math.sin(th) * r, rr.uniform(0.9, 1.1), rr.uniform(0, 1)))
    return pts


WIG = _wig_points()
WIG_R = 128.0
WIG_PR = 34.0


def _wig_removed(i, tau):
    """Les morceaux de perruque emportés par les sursauts (repère de la perruque, avant rotation)."""
    x, y, z, _k, _s = WIG[i]
    if tau >= T["issue"]:
        return T["issue"]
    if tau >= T["side"] and x < -0.5 and abs(y) < 0.6:                 # un pan sur le côté
        return T["side"]
    if tau >= T["face"] and z > 0.3 and abs(x) < 0.62 and -0.55 < y < 0.6:   # devant : son visage apparaît
        return T["face"]
    if tau >= T["top"] and y < -0.45:                                  # le dessus
        return T["top"]
    return None


def wig_angle(tau):
    return 0.0


WIG_C = (HEAD_C[0], HEAD_C[1] - HEAD_R - R + 6 - 8)


def wig_center(tau, bpos):
    """Pendant le portage, la boule suit Bounce ; une fois posée, la perruque reste sur la tête."""
    if tau < CARRY[1]:
        return bpos
    return WIG_C


# ------------------------------------------------------------------ Bounce : trajectoire
class Plan:
    def __init__(self):
        cs = []
        for (t, k, g) in PLAN:
            if k == "skull_soft":
                x, y = SPOT["skull"]
                cs.append({"t": t, "x": x, "y": y + 4, "soft": True, "g": 0, "k": k, "axis": "y"})
                continue
            if k == "floor":
                x, y = SPOT["heap"]
                cs.append({"t": t, "x": x + 6, "y": y + 10, "soft": False, "g": g, "k": k, "axis": "y"})
                continue
            x, y = SPOT[k]
            hard = k in HARD
            if k == "c":
                y = y + (8 if t < sh(21.0) else 0)
            if k == "t" and t > T["throw"]:
                k2 = "c"
                x, y = SPOT["c"]
            cs.append({"t": t, "x": x + (4 if len(cs) % 2 else -4) * (k in ("m", "t", "c")), "y": y,
                       "soft": not hard, "g": g, "k": k, "axis": "x" if k == "head" else "y"})
        self.cs = cs
        self.ts = [c["t"] for c in cs]
        self.start = {"t": -0.32, "x": 262.0, "y": SPOT["m"][1] - 150}
        self.after = {"t": END + 0.08, "x": SPOT["c"][0], "y": SPOT["c"][1]}
        self.hits = [(c["t"], c["g"], c["x"], c["y"], c["k"]) for c in cs if not c["soft"]]

    def seg(self, t):
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else self.cs[i - 1]
        b = self.after if i >= len(self.cs) else self.cs[i]
        return a, b

    def pos(self, t):
        if CARRY[0] <= t < CARRY[1]:
            return carry_pos(t)
        a, b = self.seg(t)
        hopd = 0.36 if b.get("k") == "skull" else 0.95
        if a.get("k") == "skull_soft" and t < b["t"] - hopd:
            return a["x"] + 6 * math.sin(t * 19.0), a["y"] + 3 * math.sin(t * 13.0)
        if a.get("k") == "skull_soft":
            a = {"t": b["t"] - hopd, "x": a["x"] + 6 * math.sin((b["t"] - hopd) * 19.0), "y": a["y"]}
        if a.get("k") == "heap" and b.get("k") == "skull_soft":
            # dans le tas, avant d'être ramassé : il gigote sur place
            u = (t - a["t"]) / max(1e-6, CARRY[0] - a["t"])
            return a["x"] + 7 * math.sin(t * 21.0), a["y"] - 16 * math.sin(math.pi * clamp01(u))
        Tt = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / Tt
        vy = (b["y"] - a["y"]) / Tt - 0.5 * G * Tt
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def squash(self, t):
        sx = sy = 1.0
        i = bisect.bisect_left(self.ts, t - 0.2)
        for c in self.cs[i:i + 4]:
            u = t - c["t"]
            if -0.05 <= u <= 0.14:
                kk = clamp01(1 + u / 0.05) if u < 0 else clamp01(1 - u / 0.14)
                amp = 0.2 if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy


def carry_pos(t):
    """Porté : le coiffeur soulève la boule du tas et la pose sur la tête du client ; ça gigote dedans."""
    a, b = CARRY
    u = (t - a) / (b - a)
    p0 = SPOT["heap"]
    p1 = (HEAD_C[0] + 10, 560.0)
    p2 = SPOT["skull"]
    if u < 0.55:
        q = lerp2(p0, p1, smooth(u / 0.55))
    else:
        q = lerp2(p1, (p2[0], p2[1] + 4), smooth((u - 0.55) / 0.45))
    wob = 7 * math.sin(t * 21.0)
    return q[0] + wob, q[1] + 4 * math.cos(t * 17.0)


PLAN_OBJ = Plan()
HIT_T = [h[0] for h in PLAN_OBJ.hits]
# le coiffeur sursaute à chaque contact dur, sauf avec le casque sur les oreilles
DEAF = (T["muffs_ready"], T["head"] - 0.01)
JOLTS = [(t, g) for (t, g, x, y, k) in PLAN_OBJ.hits if not (DEAF[0] <= t <= DEAF[1])]


def jolt(tau, decay=0.32):
    """Amplitude du sursaut du coiffeur (0..~1.4)."""
    v = 0.0
    for (t0, g) in JOLTS:
        u = tau - t0
        if 0 <= u <= 0.7:
            k = math.sin(math.pi * clamp01(u / 0.12)) if u < 0.12 else math.exp(-(u - 0.12) / decay)
            v = max(v, g * k)
    return v


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


def capsule(dr, p0, p1, r, col, S):
    dr.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=col, width=max(1, int(2 * r * S)))
    for p in (p0, p1):
        dr.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)


def puff(dr, x, y, r, s, S, k=1.0):
    """Une touffe de cheveux : bord sombre, corps, reflet."""
    ell(dr, x, y, r * k + 3, r * k + 3, HAIR_D, S)
    ell(dr, x, y, r * k, r * k, mix(HAIR, HAIR_L, 0.25 * s), S)
    ell(dr, x - r * 0.28 * k, y - r * 0.3 * k, r * 0.34 * k, r * 0.26 * k, mix(HAIR, HAIR_L, 0.7), S)


def cloud(dr, pts, S):
    """Des touffes dessinées comme une seule masse : contour commun, corps, puis reflets."""
    for (x, y, r, s) in pts:
        ell(dr, x, y, r + 4, r + 4, HAIR_D, S)
    for (x, y, r, s) in pts:
        ell(dr, x, y, r, r, mix(HAIR, HAIR_L, 0.18 * s), S)
    for (x, y, r, s) in pts:
        if s > 0.45:
            ell(dr, x - r * 0.3, y - r * 0.32, r * 0.42, r * 0.22, mix(HAIR, HAIR_L, 0.55), S)


def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


# ------------------------------------------------------------------ la scène
class Scene:
    def __init__(self):
        self.P = PLAN_OBJ
        t = T
        # le client : journal (0 levé, 1 baissé pour tourner la page, 2 plié sur les genoux)
        self.paper = KF(0.0, [(t["presque"], 0.0), (t["presque"] + 0.55, 0.62), (t["elbow"], 0.62),
                              (t["elbow"] + 0.16, 0.0), (t["fold"], 0.0), (t["fold"] + 0.8, 2.0)])
        # tête du client : -1 vers Bounce (gauche), +1 vers le coiffeur, 0 face au miroir
        self.c_dir = KF(0.0, [(t["turn_b"], 0.0), (t["turn_b"] + 0.45, 1.0), (t["turn_bounce"], 1.0),
                              (t["turn_bounce"] + 0.35, -1.0), (t["idea"] + 0.3, -1.0), (t["idea"] + 0.8, -0.6),
                              (t["plop"] - 0.2, -0.6), (t["plop"] + 0.1, 0.0)])
        self.c_stiff = KF(0.0, [(t["fold"] + 0.7, 0.0), (t["fold"] + 0.9, 1.0), (t["snip"] + 2.0, 1.0),
                                (t["snip"] + 2.6, 0.3), (t["plop"], 0.3), (t["plop"] + 0.2, 0.0),
                                (t["wig1"], 0.0), (t["wig1"] + 0.15, 1.0), (t["careful"] + 0.2, 1.0),
                                (t["careful"] + 0.6, 0.6)])
        # coiffeur
        self.b_x = KF(BARBER_X, [(t["idea"] + 0.3, BARBER_X), (t["scoop"], 815.0), (t["plop"] + 0.3, 815.0),
                                 (t["plop"] + 0.9, BARBER_X)])
        self.b_lean = KF(0.0, [(t["idea"] + 0.3, 0.0), (t["scoop"], -24.0), (t["scoop"] + 0.45, -8.0),
                               (t["plop"], 0.0), (t["careful"], 0.0), (t["careful"] + 0.5, -10.0),
                               (t["issue"], -10.0), (t["issue"] + 0.4, 0.0)])
        self.lamp_t = t["lamp"]
        self.muffs = (t["muffs_on"], t["head"])
        self.pomp_cut = t["pomp"]
        self.cush_land = t["throw"] + 0.55
        self.rings = [(h[0], h[1], h[2], h[3]) for h in self.P.hits]

    # ---- le coiffeur : mains (C = tondeuse, O = l'autre)
    def hands(self, tau):
        t = T
        bx = self.b_x(tau)
        dx = bx - BARBER_X
        work = self.work_point(tau)
        jl = jolt(tau)
        # main de la tondeuse : au travail, petits cercles
        c = (work[0] + 14 * math.sin(tau * 9.0), work[1] + 10 * math.cos(tau * 7.0))
        # la coupe : la main suit le trait juste après le contact
        for (tc, kind, p) in CUTS:
            u = tau - tc
            if 0 <= u <= 0.22:
                if kind == "seg":
                    c = lerp2(p[0], p[1], smooth(u / 0.18))
                elif kind == "half":
                    c = lerp2((700.0, 560.0), (760.0, 860.0), smooth(u / 0.2))
                elif kind == "circ":
                    pass
        c = (c[0] + 30 * jl * math.sin(tau * 40), c[1] - 50 * jl)
        o = (bx - 120 + dx * 0, 760.0 + 8 * math.sin(tau * 3.0))      # posée sur le haut de la cape
        # gestes de la main O
        if win(tau, t["stop"], t["stop"] + 1.3) > 0:
            k = win(tau, t["stop"], t["stop"] + 1.3)
            o = lerp2(o, (560.0, 690.0), k)                     # paume tendue vers Bounce
        if t["muffs_on"] - 0.1 <= tau <= t["muffs_ready"] + 0.1:
            u = (tau - t["muffs_on"]) / (t["muffs_ready"] - t["muffs_on"])
            o = lerp2((bx - 40, 860.0), (BHEAD[0] - 50, BHEAD[1]), smooth(u * 1.4))
            c = lerp2(c, (BHEAD[0] + 60, BHEAD[1]), win(tau, t["muffs_on"] + 0.2, t["muffs_ready"] - 0.1, 0.25, 0.2))
        k = win(tau, t["thumbs"], t["thumbs"] + 0.7)
        if k > 0:
            o = lerp2(o, (640.0, 640.0), k)
        k = win(tau, t["throw"] - 0.3, t["throw"] + 0.1, 0.2, 0.25)
        if k > 0:
            o = lerp2(o, (bx - 40, 700.0 - 80 * clamp01((tau - t["throw"] + 0.3) / 0.4)), k)
        # scotch : la main O va chercher une touffe sur l'épaule et la colle
        for j, (src, dst) in enumerate(TAPED):
            a = t["tape0"] + 1.2 * j + (0.15 if j else 0)
            u = (tau - a) / 1.1
            if 0 <= u <= 1.0:
                if u < 0.4:
                    o = lerp2(o, src, smooth(u / 0.4))
                elif u < 0.75:
                    o = lerp2(src, dst, smooth((u - 0.4) / 0.35))
                else:
                    o = (dst[0] + 6 * math.sin(tau * 40), dst[1] + 4 * math.sin(tau * 33))
        # le peigne : passes sur la mèche
        if t["comb0"] <= tau <= t["comb1"] + 0.15:
            u = (tau - t["comb0"]) / (t["comb1"] - t["comb0"])
            ph = (u * 3) % 1.0
            a = math.radians(-175 + 165 * smooth(ph))
            o = (HEAD_C[0] + 120 * math.cos(a), HEAD_C[1] + 120 * math.sin(a))
        k = win(tau, t["comb1"], t["spike"], 0.1, 0.1)
        if k > 0:
            o = lerp2(o, (HEAD_C[0] + 40, HEAD_C[1] - 150), k)
        if t["spike"] <= tau <= t["spike"] + 0.3:              # le peigne part vers le haut : antenne
            o = lerp2((HEAD_C[0] + 30, HEAD_C[1] - 120), (HEAD_C[0] + 60, HEAD_C[1] - 330), smooth((tau - t["spike"]) / 0.2))
        # figé : bras en l'air
        k = win(tau, t["fold"] + 0.6, t["point"] - 0.1, 0.2, 0.2)
        if k > 0:
            fz = 3 * math.sin(tau * 55)
            o = lerp2(o, (bx - 100 + fz, 560.0), k)
            c = lerp2(c, (bx + 70 + fz, 560.0), k)
        # il montre Bounce du doigt
        k = win(tau, t["point"], t["pomp"] - 0.05, 0.25, 0.1)
        if k > 0:
            o = lerp2(o, (500.0, 690.0), k)
        # la tondeuse rase sa propre banane
        if t["pomp"] <= tau <= t["pomp"] + 0.6:
            u = (tau - t["pomp"]) / 0.25
            c = lerp2((BHEAD[0] - 60, BHEAD[1] - 70), (BHEAD[0] + 70, BHEAD[1] - 70), smooth(u))
        # le tas : il ramasse la boule et la pose
        if t["scoop"] - 0.4 <= tau <= t["plop"] + 0.35:
            q = carry_pos(min(max(tau, CARRY[0]), CARRY[1] - 1e-3)) if tau >= CARRY[0] else SPOT["heap"]
            k = smooth((tau - (t["scoop"] - 0.4)) / 0.4) * (1 - smooth((tau - t["plop"]) / 0.35))
            o = lerp2(o, (q[0] - WIG_R * 0.75, q[1] + 30), k)
            c = lerp2(c, (q[0] + WIG_R * 0.75, q[1] + 30), k)
        # il tient la perruque d'une main pour couper autour, prudemment
        k = win(tau, t["careful"], t["issue"] + 0.1, 0.4, 0.15)
        if k > 0:
            wp = WIG_C
            c = lerp2(c, (wp[0] + WIG_R * 1.05 + 6 * math.sin(tau * 5), wp[1] - 20 + 40 * smooth((tau - t["careful"]) / 1.4)), k)
        if t["issue"] <= tau <= t["issue"] + 0.35:
            wp = (HEAD_C[0], HEAD_C[1] - 160)
            u = (tau - t["issue"]) / 0.3
            c = lerp2((wp[0] + 170, wp[1] - 40), (wp[0] - 190, wp[1] + 10), smooth(u))
        c = (c[0], c[1])
        return c, o, jl

    def work_point(self, tau):
        """Où la tondeuse travaille : sur ce qui reste de cheveux."""
        if tau < T["head"]:
            return (720.0, 640.0)
        if tau < T["spike"]:
            return (560.0, 650.0)
        if tau < T["plop"]:
            return (700.0, 700.0)
        return (790.0, 640.0)


def warp_in(tau):
    return unwarp(tau)


# ------------------------------------------------------------------ Sim
class Sim:
    scene_top = 0.245

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_real = [unwarp(h[0]) for h in PLAN_OBJ.hits]
        self.hi = 0
        self.lines = [(unwarp(tt), txt, key) for (tt, txt, key) in LINES_TAU]
        self.replies = []

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_real) and self.hit_real[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= unwarp(END) - 1e-9:
            self.done = True
            self.payoff = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t_real):
        best, bd = 0.9, 1e9
        for (th, g, _x, _y, _k) in PLAN_OBJ.hits:
            d = abs(unwarp(th) - t_real)
            if d < bd:
                best, bd = g, d
        return best

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t_real = float(t)
        tau = warp(t_real)
        S = S * self.cfg["width"] / W
        sc = self.sc
        out_img = dr._image
        S0 = S
        S = S0 * ZK
        layer = Image.new("RGB", (int(W * S) + 2, int(H * S) + 2), WALL)
        dr = ImageDraw.Draw(layer)
        self.draw_room(dr, tau, S)
        self.draw_lamp(dr, tau, S)
        self.draw_barber(dr, tau, S, body=True)
        self.draw_chair_back(dr, tau, S)
        self.draw_afro(dr, tau, S, layer="back")
        bpos = sc.P.pos(tau)
        wig_on = CARRY[0] <= tau < ISSUE + 0.01
        if wig_on and tau >= CARRY[0]:
            self.draw_wig(dr, tau, S, bpos, front=False)
        self.draw_client(dr, tau, S)
        self.draw_afro(dr, tau, S, layer="front")
        self.draw_cart(dr, tau, S, bpos)
        self.draw_rings(dr, tau, S)
        # Bounce
        base.HERO["expr"] = self.expr_at(tau)
        bx, by = bpos
        sx, sy = sc.P.squash(tau)
        self.draw_wig_bits(dr, tau, S, final=True)
        popping = wig_on and tau >= CARRY[1] and math.hypot(bx - WIG_C[0], by - WIG_C[1]) > 70
        if wig_on and tau >= CARRY[0] and popping:
            self.draw_wig(dr, tau, S, bpos, front=True)
        self.draw_ball(dr, bx, by, R * sx, R * sy, S)
        if wig_on and tau >= CARRY[0] and not popping:
            self.draw_wig(dr, tau, S, bpos, front=True)
        self.draw_heap(dr, tau, S, bpos)
        self.draw_paper(dr, tau, S)
        self.draw_barber(dr, tau, S, body=False)
        self.draw_particles(dr, tau, S)
        self.draw_wig_bits(dr, tau, S)
        ox, oy = int((540 - ZX * ZK) * S0), int((470 - ZY * ZK) * S0)
        out_img.paste(layer, (ox, oy))
        self.draw_bottom(ImageDraw.Draw(out_img), tau, S0)
        if base.HERO["pos"] is not None:
            base.HERO["pos"] = (base.HERO["pos"][0] + ox, base.HERO["pos"][1] + oy)

    def expr_at(self, tau):
        t = T
        for (a, b, e) in [(t["head"], t["head"] + 0.7, "shock"), (t["lamp"], t["lamp"] + 0.9, "shock"),
                          (t["fold"] + 0.6, t["snip"], "shock"), (t["issue"], 99.0, "lose")]:
            if a <= tau < b:
                return e
        for (th, g, _x, _y, _k) in PLAN_OBJ.hits:
            if g >= 1.25 and 0 <= tau - th < 0.45:
                return "shock"
        return "calm"

    def draw_ball(self, dr, x, y, rx, ry, S):
        if abs(rx - ry) < 0.5:
            base.ball(dr, x * S, y * S, rx * S)
            return
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

    # -------- décor du bas (coordonnées écran), sous la scène : sol, tapis, balai
    def draw_bottom(self, dr, tau, S):
        y0 = (FLOOR_Y - ZY) * ZK + 470 + 75
        ell(dr, 560, y0 + 120, 470, 120, (70, 40, 54), S)
        ell(dr, 560, y0 + 120, 420, 96, (104, 58, 74), S)
        ell(dr, 560, y0 + 120, 330, 66, (132, 78, 92), S)
        for k in range(14):
            a = 2 * math.pi * k / 14
            ell(dr, 560 + 375 * math.cos(a), y0 + 120 + 86 * math.sin(a), 12, 6, (164, 112, 120), S)
        # balai et pelle, appuyés à gauche
        dr.line([150 * S, (y0 - 40) * S, 230 * S, (y0 + 330) * S], fill=(176, 130, 80), width=max(1, int(14 * S)))
        dr.polygon(P([(190, y0 + 300), (290, y0 + 300), (310, y0 + 420), (170, y0 + 420)], S), fill=(206, 170, 90))
        for k in range(7):
            x = 182 + 20 * k
            dr.line([x * S, (y0 + 330) * S, (x - 4) * S, (y0 + 416) * S], fill=(160, 126, 60), width=max(1, int(4 * S)))
        dr.polygon(P([(820, y0 + 330), (940, y0 + 330), (960, y0 + 400), (800, y0 + 400)], S), fill=(70, 120, 170))
        rect(dr, 930, y0 + 250, 948, y0 + 340, (60, 100, 150), S)
        # quelques touffes égarées sur le tapis, selon ce qui est déjà tombé
        n = self.heap_count(tau)
        rr = np.random.default_rng(12)
        for k in range(min(16, n // 5)):
            puff(dr, rr.uniform(260, 860), y0 + 80 + rr.uniform(0, 90), 14, rr.uniform(), S)

    # -------- décor
    def draw_room(self, dr, tau, S):
        rect(dr, 0, 0, W, FLOOR_Y, WALL, S)
        for k in range(12):                                   # lambris
            x = 45 + k * 90
            rect(dr, x, 0, x + 10, FLOOR_Y, WALL_L, S)
        rect(dr, 0, 1000, W, 1012, (28, 54, 56), S)
        # enseigne de barbier qui tourne (décor, à droite au-dessus du coiffeur)
        px0, px1, py0, py1 = 960.0, 1010.0, 520.0, 800.0
        rect(dr, px0 - 6, py0 - 20, px1 + 6, py0, CHROME, S, r=6)
        rect(dr, px0 - 6, py1, px1 + 6, py1 + 20, CHROME, S, r=6)
        rect(dr, px0, py0, px1, py1, (236, 236, 240), S)
        off = (tau * 60.0) % 60.0
        for k in range(-1, 6):
            y = py0 + k * 60 + off
            col = (196, 40, 46) if k % 2 == 0 else (46, 76, 176)
            dr.polygon(P([(px0, y), (px1, y - 30), (px1, y - 10), (px0, y + 20)], S), fill=col)
        rect(dr, 0, py0 - 22, px0 - 8, py0 - 21, WALL, S)
        # sol en damier
        rect(dr, 0, FLOOR_Y, W, H, TILE_A, S)
        tw = 90
        for row in range(8):
            y0 = FLOOR_Y + row * 40
            for col in range(14):
                if (row + col) % 2 == 0:
                    x0 = col * tw - (row % 2) * 0
                    rect(dr, x0, y0, x0 + tw, y0 + 40, TILE_B, S)
        rect(dr, 0, FLOOR_Y - 6, W, FLOOR_Y, (60, 70, 74), S)

    def lamp_angle(self, tau):
        u = tau - self.sc.lamp_t
        if u < 0:
            return 0.0
        return 0.32 * math.exp(-u / 2.2) * math.sin(u * 3.2)

    def draw_lamp(self, dr, tau, S):
        a = self.lamp_angle(tau)
        top = (LAMP[0], 0.0)
        Lc = LAMP[1] - 60
        bot = (top[0] + math.sin(a) * Lc, top[1] + math.cos(a) * Lc)
        dr.line([top[0] * S, top[1] * S, bot[0] * S, bot[1] * S], fill=(90, 96, 104), width=max(1, int(5 * S)))

        def Q(u, v):
            return (bot[0] + u * math.cos(a) + v * math.sin(a), bot[1] - u * math.sin(a) + v * math.cos(a))
        glow = 0.7 + 0.3 * (1 - clamp01((tau - self.sc.lamp_t) / 0.4)) if tau >= self.sc.lamp_t else 0.7
        ell(dr, *Q(0, 62), 40, 22, mix(WALL, (255, 236, 170), 0.5 * glow), S)
        dr.polygon(P([Q(-22, 0), Q(22, 0), Q(92, 60), Q(-92, 60)], S), fill=LAMP_C)
        dr.line(P([Q(-92, 60), Q(92, 60)], S), fill=dim(LAMP_C, 0.7), width=max(1, int(6 * S)))

    def draw_chair_back(self, dr, tau, S):
        rect(dr, 470, 860, 810, 1150, SEAT_D, S, r=40)
        rect(dr, 600, 1180, 680, 1236, CHROME, S)
        ell(dr, 640, 1240, 150, 20, CHROME_D, S)
        ell(dr, 640, 1236, 140, 16, CHROME, S)
        rect(dr, 560, 1185, 720, 1200, CHROME_D, S, r=6)          # repose-pieds

    def draw_cart(self, dr, tau, S, bpos):
        x0, x1, ty = CART
        # pieds, étagère, bouteilles
        for x in (x0 + 18, x1 - 18):
            rect(dr, x - 7, ty, x + 7, FLOOR_Y - 14, CHROME_D, S)
            ell(dr, x, FLOOR_Y - 10, 14, 10, (40, 40, 46), S)
        rect(dr, x0 + 10, 1196, x1 - 10, 1206, CHROME_D, S)
        for (bx_, h_, c_) in ((200, 52, (90, 170, 210)), (250, 40, (210, 120, 70)), (395, 46, (140, 200, 110))):
            rect(dr, bx_ - 14, 1196 - h_, bx_ + 14, 1196, c_, S, r=6)
            rect(dr, bx_ - 6, 1196 - h_ - 12, bx_ + 6, 1196 - h_, (220, 220, 226), S)
        # le plateau (métal : c'est là qu'il dit son nom)
        dk = 0.0
        for (t0, g, xh, yh, kh) in self.sc.P.hits:
            u = tau - t0
            if kh == "m" and 0 <= u <= 0.3:
                dk = max(dk, 7 * g * math.sin(u * 40) * (1 - u / 0.3))
        rect(dr, x0, ty + dk, x1, ty + 16 + dk, CHROME, S, r=5)
        rect(dr, x0, ty + 12 + dk, x1, ty + 18 + dk, CHROME_D, S, r=3)
        # serviette pliée (molle) puis coussin
        bx, by = bpos
        landed = tau >= self.sc.cush_land
        if not landed:
            self.draw_soft(dr, TOWEL[0], TOWEL[1], ty - TOWEL[2], ty, TOWEL_C, dim(TOWEL_C, 0.75), bx, by, S, tau)
            # le coussin en vol, lancé par le coiffeur
            a = self.sc.cush_land - 0.55
            if tau >= a:
                u = (tau - a) / 0.55
                p0 = (BARBER_X - 70, 700.0)
                p1 = ((CUSH[0] + CUSH[1]) / 2, ty - TOWEL[2] - CUSH[2] / 2)
                Tt = 0.55
                vx = (p1[0] - p0[0]) / Tt
                vy = (p1[1] - p0[1]) / Tt - 0.5 * 1800 * Tt
                q = (p0[0] + vx * u * Tt, p0[1] + vy * u * Tt + 0.5 * 1800 * (u * Tt) ** 2)
                rect(dr, q[0] - 81, q[1] - 39, q[0] + 81, q[1] + 39, CUSH_C, S, r=30)
        else:
            self.draw_soft(dr, TOWEL[0], TOWEL[1], ty - TOWEL[2], ty, TOWEL_C, dim(TOWEL_C, 0.75), -999, 0, S, tau)
            self.draw_soft(dr, CUSH[0], CUSH[1], ty - TOWEL[2] - CUSH[2] + 26, ty - TOWEL[2] + 4, CUSH_C, CUSH_D,
                           bx, by, S, tau, round_=True)

    def draw_soft(self, dr, x0, x1, top, bottom, col, col_d, bx, by, S, tau, round_=False):
        pts = []
        n = 40
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = top
            if round_:
                e = (2 * (x - x0) / (x1 - x0) - 1)
                y = top + 18 * e ** 4
            d = x - bx
            if abs(d) < R * 1.05:
                cy = by + math.sqrt(max(0.0, (R * 1.05) ** 2 - d * d))
                y = max(y, min(bottom - 6, cy))
            pts.append((x, y))
        dr.polygon(P(pts + [(x1, bottom), (x0, bottom)], S), fill=col)
        dr.line(P(pts, S), fill=col_d, width=max(1, int(5 * S)))
        if not round_:
            for k in (0.35, 0.7):
                yy = lerp(top, bottom, k)
                dr.line([(x0 + 6) * S, yy * S, (x1 - 6) * S, yy * S], fill=col_d, width=max(1, int(3 * S)))

    def draw_rings(self, dr, tau, S):
        for (t0, g, x, y) in self.sc.rings:
            u = tau - t0
            if u < 0 or u > 0.5 or g < 0.3:
                continue
            rmax = R + 50 + 160 * g
            r = R + 10 + 800 * u
            if r > rmax:
                continue
            k = 1 - (r - R) / max(1.0, rmax - R)
            if k < 0.3:
                continue
            col = mix(WALL, (250, 250, 255), 0.55 + 0.45 * k)
            w = (10 + 9 * min(1.3, g)) * (0.6 + 0.4 * k)
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(2, int(w * S)))

    # -------- l'afro
    def afro_state(self, tau):
        """Liste des touffes visibles sur la tête (x, y, r, s) selon les coupes, la mèche, l'antenne."""
        out = []
        t = T
        rem_pos = {}
        for i, (x, y, r, s) in enumerate(AFRO):
            if CUT_T[i] is not None and tau >= CUT_T[i]:
                continue
            out.append((i, x, y, r, s))
        if tau < t["comb0"]:
            res = [(x, y, r, s) for (i, x, y, r, s) in out]
        else:
            res = []
            for j, i in enumerate(REMAIN):
                x, y, r, s = AFRO[i]
                if tau < t["spike"]:
                    u = clamp01((tau - t["comb0"] - 0.08 * j) / 1.0)
                    cx, cy, cr = COMB_T[j]
                    res.append((lerp(x, cx, smooth(u)), lerp(y, cy, smooth(u)), lerp(r, cr, smooth(u)), s))
                elif tau < t["snip"]:
                    u = smooth((tau - t["spike"]) / 0.18)
                    lx, ly, lr = ANT_L[j]
                    q = ant_curve(self.ant_angle(tau), j, len(REMAIN))
                    ax, ay = ANT_BASE[0] + q[0] + lx, ANT_BASE[1] + q[1]
                    cx, cy, cr = COMB_T[j]
                    res.append((lerp(cx, ax, u), lerp(cy, ay, u), lerp(cr, lr, u), s))
                else:
                    q = self.ant_fall(tau, j)
                    if q is not None:
                        res.append(q + (s,))
        return res

    def ant_angle(self, tau):
        t = T
        a = 0.0
        for th in (33.95, 35.9, 37.75):
            u = tau - th
            if u >= 0:
                a += 0.35 * math.exp(-u / 0.5) * math.sin(u * 16)
        u = tau - (t["spike"])
        if 0 <= u:
            a += 0.25 * math.exp(-u / 0.4) * math.sin(u * 18)
        # elle fane, lentement, vers la droite
        a += math.radians(200) * smooth((tau - t["wilt"]) / 1.3)
        return a

    def ant_fall(self, tau, j):
        """L'antenne coupée tombe comme une feuille, se pose sur le journal plié, puis part avec le tas."""
        t = T
        u = tau - t["snip"]
        lx, ly, lr = ANT_L[j]
        ph0 = self.ant_angle(t["snip"])
        land_y = 1020.0
        dur = 1.9
        k = clamp01(u / dur)
        cx = ANT_BASE[0] + 80 + 70 * math.sin(u * 3.0) * (1 - k)
        cy = lerp(ANT_BASE[1] - 40, land_y, k ** 1.2)
        ph = ph0 + 1.2 * math.sin(u * 2.6) * (1 - k) + (math.pi / 2 - ph0) * smooth(k)
        if tau > t["scoop"]:
            return None
        q = rot((lx, ly + 110), ph)
        return (cx + q[0], cy + q[1], lr)

    def draw_afro(self, dr, tau, S, layer):
        """Le volume derrière la tête (back) et devant (front : ce qui dépasse au-dessus du crâne)."""
        st = self.afro_state(tau)
        hb = self.head_bob(tau)
        sel = []
        for (x, y, r, s) in st:
            front = y < HEAD_C[1] - HEAD_R * 0.55 or abs(x - HEAD_C[0]) > HEAD_R * 0.9
            if tau >= T["comb0"]:
                front = True
            if (layer == "front") == front:
                sel.append((x, y + hb, r, s))
        cloud(dr, sel, S)
        # touffes recollées au scotch
        if layer == "front":
            for j, (src, dst) in enumerate(TAPED):
                a = T["tape0"] + 1.2 * j + (0.15 if j else 0)
                u = (tau - a) / 1.1
                if u < 0.4:
                    continue
                if tau >= T["tape_pop"]:
                    v = tau - T["tape_pop"]
                    if v > 1.2:
                        continue
                    x = dst[0] + (j * 2 - 1) * 260 * v
                    y = dst[1] - 700 * v + 900 * v * v
                    ang = 7 * v
                elif u < 0.75:
                    q = lerp2(src, dst, smooth((u - 0.4) / 0.35))
                    x, y, ang = q[0], q[1], 0.0
                else:
                    x, y, ang = dst[0], dst[1], (1.2 if j == 0 else -0.5)
                for (ox, oy) in ((-16, 0), (14, -8), (2, 12)):
                    q = rot((ox, oy), ang)
                    puff(dr, x + q[0], y + q[1] + hb, 22, 0.5, S)
                if u >= 0.75 and tau < T["tape_pop"] + 1.2:
                    for sgn in (-1, 1):
                        q0 = rot((-30, sgn * 14), ang + 0.6 * sgn)
                        q1 = rot((30, -sgn * 14), ang + 0.6 * sgn)
                        dr.line(P([(x + q0[0], y + q0[1] + hb), (x + q1[0], y + q1[1] + hb)], S), fill=TAPE,
                                width=max(1, int(12 * S)))
            # la touffe qu'il tenait et qui s'envole au sursaut (25,9)
            tt = 26.7
            v = tau - tt
            if -0.6 <= v <= 1.3:
                if v < 0:
                    c, o, _j = self.sc.hands(tau)
                    x, y = o[0], o[1] - 10
                else:
                    c, o, _j = self.sc.hands(tt)
                    x, y = o[0] - 380 * v, o[1] - 10 - 650 * v + 800 * v * v
                for (ox, oy) in ((-16, 0), (14, -8), (2, 12)):
                    puff(dr, x + ox, y + oy, 20, 0.6, S)

    def head_bob(self, tau):
        return 0.0

    # -------- le client
    def draw_client(self, dr, tau, S):
        sc = self.sc
        stiff = sc.c_stiff(tau)
        tr = 3.0 * stiff * math.sin(tau * 60)
        lift = self.client_lift(tau)
        # cape
        cx = HEAD_C[0] + tr
        top = 925.0 - lift
        pts = [(cx - 70, top - 10), (cx + 70, top - 10), (cx + 200, 1185), (cx - 200, 1185)]
        dr.polygon(P(pts, S), fill=CAPE)
        for k in range(5):
            x = cx - 150 + 75 * k
            dr.line(P([(cx + (x - cx) * 0.3, top + 20), (x, 1180)], S), fill=CAPE_D, width=max(1, int(5 * S)))
        rect(dr, cx - 62, top - 22, cx + 62, top + 6, (236, 236, 240), S, r=10)
        # accoudoirs devant la cape
        rect(dr, 430, 1110, 480, 1160, SEAT, S, r=14)
        rect(dr, 800, 1110, 850, 1160, SEAT, S, r=14)
        # cou et tête
        hx, hy = HEAD_C[0] + tr, HEAD_C[1] - lift
        rect(dr, hx - 30, hy + 40, hx + 30, top, SKIN_D, S)
        d = sc.c_dir(tau)
        ell(dr, hx - 78 + 14 * max(0.0, d), hy + 6, 16, 22, SKIN_D, S)
        ell(dr, hx + 78 + 14 * min(0.0, d), hy + 6, 16, 22, SKIN_D, S)
        ell(dr, hx, hy, HEAD_R, HEAD_R, SKIN, S)
        if abs(d) > 0.15:                        # profil : petit nez du côté où il regarde
            ell(dr, hx + d * HEAD_R * 0.95, hy + 10, 15 * abs(d), 13, SKIN, S)
        # reflet du crâne (chauve) quand il ne reste rien
        if tau >= T["spike"]:
            ell(dr, hx - 26, hy - 44, 22, 10, mix(SKIN, (255, 236, 220), 0.5), S)
        self._client_head = (hx, hy)

    def client_lift(self, tau):
        """Le client est soulevé quand la perruque saute pendant qu'il la tient (48,85)."""
        return 0.0

    def client_hands(self, tau):
        sc = self.sc
        p = sc.paper(tau)
        hx, hy = getattr(self, "_client_head", HEAD_C)
        if p <= 1.0:
            yy = lerp(905.0, 1010.0, p)
            l, r = (470.0, yy), (810.0, yy)
        else:
            k = smooth(p - 1.0)
            l = lerp2((470.0, 1010.0), (540.0, 1085.0), k)
            r = lerp2((810.0, 1010.0), (740.0, 1085.0), k)
        t = T
        k = win(tau, t["joy"], t["joy"] + 1.1, 0.2, 0.25)
        if k > 0:
            w = 20 * math.sin(tau * 18)
            l = lerp2(l, (470.0 + w, 700.0), k)
            r = lerp2(r, (810.0 + w, 700.0), k)
        k = win(tau, t["wig1"] + 0.1, t["face"] - 0.3, 0.2, 0.2)
        if k > 0:                                # il se fige, mains crispées sur les accoudoirs
            l = lerp2(l, (455.0, 1105.0), k)
            r = lerp2(r, (825.0, 1105.0), k)
        k = win(tau, t["face"] + 0.1, t["careful"], 0.15, 0.3)
        if k > 0:                                # il voit un visage dans ses cheveux : mains en l'air
            w = 14 * math.sin(tau * 40)
            l = lerp2(l, (430.0 + w, 760.0), k)
            r = lerp2(r, (850.0 - w, 760.0), k)
        return l, r

    def draw_paper(self, dr, tau, S):
        sc = self.sc
        p = sc.paper(tau)
        l, r = self.client_hands(tau)
        lift = self.client_lift(tau)
        if p <= 1.0:
            y0 = lerp(822.0, 960.0, p) - lift
            x0, x1 = 478.0, 802.0
            h = 205.0
            rect(dr, x0, y0, x1, y0 + h, PAPER, S, r=4)
            dr.line([((x0 + x1) / 2) * S, y0 * S, ((x0 + x1) / 2) * S, (y0 + h) * S], fill=PAPER_D, width=max(1, int(3 * S)))
            rect(dr, x0 + 18, y0 + 16, x0 + 148, y0 + 44, (60, 60, 66), S)
            rect(dr, x1 - 148, y0 + 16, x1 - 18, y0 + 30, (90, 90, 98), S)
            for k in range(6):
                yy = y0 + 64 + k * 22
                for (a, b) in ((x0 + 18, x0 + 148), (x1 - 148, x1 - 18)):
                    dr.line([a * S, yy * S, (b - 12 * (k % 3)) * S, yy * S], fill=PAPER_D, width=max(1, int(5 * S)))
        else:
            k = smooth(p - 1.0)
            y0 = lerp(960.0, 1040.0, k)
            rect(dr, 520.0, y0, 760.0, y0 + 70, PAPER, S, r=4)
            for kk in range(2):
                yy = y0 + 22 + kk * 22
                dr.line([538 * S, yy * S, 742 * S, yy * S], fill=PAPER_D, width=max(1, int(5 * S)))
        for q in (l, r):
            ell(dr, q[0], q[1] - lift, 22, 22, SKIN, S)

    # -------- le coiffeur
    def draw_barber(self, dr, tau, S, body):
        sc = self.sc
        c, o, jl = sc.hands(tau)
        bx = sc.b_x(tau)
        lean = math.radians(sc.b_lean(tau))
        jump = 34 * jl - CROUCH * win(tau, T["muffs_ready"] + 0.2, T["head"], 0.4, 0.25)
        hip = (bx + 30, 1000.0 - jump)

        def B(u, v):
            return (hip[0] + v * math.cos(lean) + u * math.sin(lean), hip[1] - u * math.cos(lean) + v * math.sin(lean))
        sh_l, sh_r = B(320, -68), B(320, 70)
        head = B(378 + 10 * jl, -4)
        if body:
            # jambes, blouse
            for sx in (-1, 1):
                rect(dr, hip[0] + sx * 34 - 18, hip[1], hip[0] + sx * 34 + 18, FLOOR_Y - 4, (44, 46, 58), S)
                ell(dr, hip[0] + sx * 34 + 8, FLOOR_Y - 8, 30, 12, (24, 24, 30), S)
            pts = [B(-30, -96), B(-30, 96), B(330, 78), B(345, 0), B(330, -78)]
            dr.polygon(P(pts, S), fill=COAT)
            for k in range(3):
                q = B(60 + 80 * k, -20)
                ell(dr, q[0], q[1], 7, 7, COAT_D, S)
            return
        # bras (devant le client)
        for (s, hnd, holding) in ((sh_l, o, False), (sh_r, c, True)):
            capsule(dr, s, hnd, 19, COAT_D if holding else COAT, S)
            ell(dr, hnd[0], hnd[1], 21, 21, BSKIN, S)
        self.draw_clippers(dr, tau, S, c, jl)
        # pouce levé
        k = win(tau, T["thumbs"], T["thumbs"] + 0.7)
        if k > 0.3:
            capsule(dr, (o[0], o[1] - 8), (o[0], o[1] - 44), 8, BSKIN, S)
        # paume « stop »
        k = win(tau, T["stop"], T["stop"] + 1.3)
        if k > 0.3:
            for f in range(4):
                capsule(dr, (o[0] - 15 + 10 * f, o[1] - 10), (o[0] - 18 + 12 * f, o[1] - 50), 6, BSKIN, S)
        # doigt pointé
        k = win(tau, T["point"], T["pomp"] - 0.05, 0.25, 0.1)
        if k > 0.3:
            capsule(dr, o, (o[0] - 58, o[1] + 22), 8, BSKIN, S)
        # peigne
        if T["comb0"] - 0.2 <= tau <= T["spike"] + 0.5:
            rect(dr, o[0] - 8, o[1] - 50, o[0] + 8, o[1] + 10, (40, 40, 48), S, r=3)
        # cou, tête (sans visage), nez du côté où il regarde
        neck_top = B(345, -4)
        hx, hy = head
        capsule(dr, neck_top, (hx, hy + 20), 20, BSKIN, S)
        look = -1.0
        if T["joy"] <= tau < T["careful"] - 0.2:
            look = -0.7
        ell(dr, hx, hy, BHEAD_R, BHEAD_R, BSKIN, S)
        ell(dr, hx + look * BHEAD_R * 0.95, hy + 8, 13, 12, BSKIN, S)
        # banane (rasée par sa propre tondeuse à 40,95)
        pc = sc.pomp_cut
        if tau < pc + 0.08:
            pts = [(hx - 58, hy - 30), (hx - 70, hy - 76), (hx - 20, hy - 104), (hx + 50, hy - 92), (hx + 62, hy - 38)]
            dr.polygon(P(pts, S), fill=POMP)
            dr.line(P([(hx - 50, hy - 80), (hx + 30, hy - 86)], S), fill=(110, 110, 130), width=max(1, int(6 * S)))
        else:
            v = tau - pc
            if v < 1.6:
                fx = hx + 140 * v
                fy = min(FLOOR_Y - 20, hy - 70 - 300 * v + 900 * v * v)
                a = 3 * v
                pts = [rot(p, a) for p in [(-60, 20), (-70, -26), (-20, -54), (50, -42), (62, 12)]]
                dr.polygon(P([(fx + x, fy + y) for (x, y) in pts], S), fill=POMP)
            else:
                dr.polygon(P([(930, FLOOR_Y - 4), (950, FLOOR_Y - 34), (1010, FLOOR_Y - 30), (1020, FLOOR_Y - 4)], S),
                           fill=POMP)
            ell(dr, hx - 18, hy - 40, 18, 8, mix(BSKIN, (255, 230, 210), 0.5), S)
        # casque antibruit
        a0, a1 = sc.muffs
        if a0 + 0.7 <= tau < a1:
            dr.arc([(hx - 74) * S, (hy - 92) * S, (hx + 74) * S, (hy + 40) * S], 180, 360, fill=(70, 70, 82),
                   width=max(1, int(14 * S)))
            for sx in (-1, 1):
                ell(dr, hx + sx * 68, hy + 2, 26, 36, MUFF, S)
        elif a0 <= tau < a0 + 0.7:
            u = (tau - a0) / 0.7
            q = lerp2((bx - 40, 860.0), (hx, hy), smooth(u))
            for sx in (-1, 1):
                ell(dr, q[0] + sx * 60 * smooth(u), q[1], 24, 32, MUFF, S)
        elif a1 <= tau < a1 + 1.4:
            v = tau - a1
            q = (hx + 260 * v, hy - 500 * v + 1200 * v * v)
            if q[1] < FLOOR_Y:
                for sx in (-1, 1):
                    p = rot((sx * 60, 0), 6 * v)
                    ell(dr, q[0] + p[0], q[1] + p[1], 24, 32, MUFF, S)

    def draw_clippers(self, dr, tau, S, c, jl):
        """La tondeuse ; au ralenti de la lampe elle s'envole en tournant au-dessus du crâne et revient."""
        t0 = T["lamp"]
        u = tau - t0
        ang = -0.5 + 0.6 * jl * math.sin(tau * 30)
        x, y = c[0], c[1]
        if 0.02 <= u <= 0.75:
            k = clamp01((u - 0.02) / 0.73)
            # boucle au-dessus de la tête : du coiffeur, par le sommet, et retour dans sa main
            path = [(c[0], c[1]), (680, 560), (580, 600), (500, 660), (560, 540), (c[0], c[1])]
            n = len(path) - 1
            i = min(n - 1, int(k * n))
            f = k * n - i
            x, y = lerp2(path[i], path[i + 1], smooth(f))
            ang = k * 4 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(a, b):
            return (x + a * ca - b * sa, y + a * sa + b * ca)
        dr.polygon(P([Q(-20, -48), Q(20, -48), Q(24, 40), Q(-24, 40)], S), fill=CLIP_C)
        dr.polygon(P([Q(-22, -48), Q(22, -48), Q(22, -60), Q(-22, -60)], S), fill=(200, 204, 214))
        for kk in range(5):
            q = Q(-18 + 9 * kk, -62)
            ell(dr, q[0], q[1], 3, 5, (200, 204, 214), S)
        if 0.02 <= u <= 0.75 or jl > 0.4:
            for kk in range(3):                    # traits de vitesse
                q0 = Q(-34, -20 + 20 * kk)
                q1 = Q(-58, -26 + 20 * kk)
                dr.line(P([q0, q1], S), fill=(220, 220, 230), width=max(1, int(4 * S)))

    # -------- le tas de cheveux par terre
    def heap_count(self, tau):
        return sum(1 for p in PARTS if p["land"] <= tau)

    def draw_heap(self, dr, tau, S, bpos):
        n = self.heap_count(tau)
        if tau >= T["scoop"]:
            n = int(n * 0.12)
        if n <= 0:
            return
        hgt = 76 * min(1.0, n / 70.0) ** 0.6
        wdt = 110 + 150 * min(1.0, n / 70.0) ** 0.5
        rr = np.random.default_rng(3)
        bx, by = bpos
        inside = 44.5 - 0.12 <= tau < CARRY[0] + 0.3
        pile = []
        for k in range(min(34, 6 + n // 2)):
            u = rr.uniform(-1, 1)
            x = HEAP_X + u * wdt
            y = FLOOR_Y - 10 - hgt * (1 - u * u) * rr.uniform(0.55, 1.0)
            r = 24 + 10 * rr.uniform()
            if inside:                            # Bounce y est enfoui : le tas gonfle autour de lui
                d = math.hypot(x - bx, y - by)
                if d < R + 60:
                    y -= 30
            pile.append((x, y, r, rr.uniform()))
        cloud(dr, pile, S)
        if inside:
            for k in range(12):                   # ce qui le recouvre (on voit du rose entre les touffes)
                a = math.radians(-160 + 140 * k / 11)
                x = bx + (R - 10) * math.cos(a) + 8 * math.sin(tau * 9 + k)
                y = by + (R - 30) * math.sin(a) * 0.5 + 30
                puff(dr, x, y, 34, 0.4, S)

    def draw_particles(self, dr, tau, S):
        for p in PARTS:
            if tau < p["t0"] or tau >= p["land"]:
                continue
            i = min(len(p["pts"]) - 1, int((tau - p["t0"]) / FALL_DT))
            x, y = p["pts"][i]
            puff(dr, x, y, p["r"], p["s"], S, 0.85)

    # -------- la perruque (Bounce dedans)
    def wig_puffs(self, tau, center):
        a = wig_angle(tau)
        ca, sa = math.cos(a), math.sin(a)
        out = []
        for i, (x, y, z, kk, s) in enumerate(WIG):
            rt = _wig_removed(i, tau)
            if rt is not None:
                continue
            xr = x * ca + z * sa
            zr = -x * sa + z * ca
            out.append((center[0] + xr * WIG_R, center[1] + y * WIG_R * 0.92 - 10, zr, WIG_PR * kk, s))
        return out

    def draw_wig(self, dr, tau, S, bpos, front):
        if tau >= ISSUE:
            return
        if tau < CARRY[0]:
            return
        pts = self.wig_puffs(tau, wig_center(tau, bpos))
        sel = [(x, y, r * (0.85 + 0.15 * z), s) for (x, y, z, r, s) in sorted(pts, key=lambda p: p[2])
               if (z > -0.15) == front]
        cloud(dr, sel, S)

    def draw_wig_bits(self, dr, tau, S, final=False):
        """Ce que les sursauts arrachent à la perruque ; l'explosion finale (final=True) passe derrière Bounce."""
        events = ((ISSUE, "all", 2.6),) if final else ((T["side"], "side", 1.0), (T["face"], "face", 1.0),
                                                      (T["top"], "top", 1.0))
        for (t0, sel, spread) in events:
            u = tau - t0
            if u < 0 or u > 1.6:
                continue
            ctr = WIG_C
            a = wig_angle(t0)
            ca, sa = math.cos(a), math.sin(a)
            for i, (x, y, z, kk, s) in enumerate(WIG):
                rt = _wig_removed(i, t0 + 1e-3)
                if rt is None or abs(rt - t0) > 1e-6:
                    continue
                xr = x * ca + z * sa
                px, py = ctr[0] + xr * WIG_R, ctr[1] + y * WIG_R * 0.92
                vx = xr * 520 * spread + 60 * math.sin(i)
                vy = y * 420 * spread - 380
                gx = px + vx * u
                gy = py + vy * u + 0.5 * 1600 * u * u
                if gy > FLOOR_Y:
                    continue
                puff(dr, gx, gy, WIG_PR * kk * 0.8, s, S)


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 80, "hook_speed": 1.0, "hook_max_s": 1.26,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.94, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True, "hero_shock_s": 0.0,
}
LINE_GAIN = {"hair": 0.95, "perfect": 1.0}


def exact_events(sim):
    return [(unwarp(t), "hit", "h%d" % i) for i, (t, g, x, y, k) in enumerate(PLAN_OBJ.hits)]


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


def plan_report():
    hits = [unwarp(h[0]) for h in PLAN_OBJ.hits]
    iv = np.diff(hits)
    arcs = []
    cs = [PLAN_OBJ.start] + PLAN_OBJ.cs
    for a, b in zip(cs[:-1], cs[1:]):
        if CARRY[0] - 0.01 <= a["t"] < CARRY[1] + 0.01 and b["t"] <= CARRY[1] + 0.01:
            continue
        Tt = b["t"] - a["t"]
        vy = (b["y"] - a["y"]) / Tt - 0.5 * G * Tt
        top = a["y"] - (vy * vy / (2 * G) if vy < 0 else 0)
        arcs.append((round(a["t"], 2), round(Tt, 2), round(top - R)))
    return {"hits": len(hits), "cv": round(float(np.std(iv) / np.mean(iv)), 3), "iv_min": round(float(iv.min()), 2),
            "iv_max": round(float(iv.max()), 2), "remain": len(REMAIN), "highest": sorted(arcs, key=lambda a: a[2])[:5],
            "end_real": round(unwarp(END), 2), "issue_real": round(unwarp(ISSUE), 2)}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    cfg["_sim"] = sim
    hv = hook_clip(cfg)
    ev = exact_events(sim)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2),
               "hook": [HOOK_T, round(HOOK_T + len(hv) / SR, 2)] if hv is not None else None,
               "hits": len(ev), "plan": plan_report(),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(ev, dur, cfg, None, None, narr, (), name_len=len(name) / SR)
    said = {round(w[0], 3) for w in words}
    summary["word_len"] = round(len(name) / SR, 3)
    summary["muets"] = [round(e[0], 3) for e in ev if round(e[0], 3) not in said]
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
