"""
Prototype « le bain de Float » : une invitée, Float (le personnage d'un fan, dessiné
d'après sa référence), prend son bain. Bounce entre en claquant la porte et rebondit
partout ; chaque rebond vide un peu plus la baignoire, jusqu'à ce qu'il soit mis à la
porte. Une seule scène, sans narrateur ni sous-titre : le son se limite à la voix de
l'accroche, aux « Bounce » de Bounce (étouffés sous l'eau et derrière la porte), à son
« Oh no. » final (la réaction `hero_lose` du moteur) et aux quatre « Float » de Float.

Toute la scène est un plan calculé d'avance sur une seule horloge, comme le roast :
les trajectoires de Bounce sont des arcs balistiques exacts entre ses contacts, et les
répliques de Float sont lues dans une banque de fichiers (cfg["float_bank"], hors dépôt)
dont les durées réelles placent la suite (une réplique tombe dans l'arc d'un rebond,
entre deux « Bounce »). Changer de banque = relancer le rendu, rien d'autre.

Les répliques de Float passent par le canal du narrateur du moteur (build_narration,
place_words) pour que Bounce se taise pendant qu'elle parle et que le contrôle le
vérifie ; elles n'ont pas de sous-titre. base.py n'est pas modifié : ce module enveloppe
voice.say (la banque), base.hero_word (un tirage stable), base.subtitle_at (aucun
sous-titre) et base.render_audio (les « Bounce » étouffés ou petits, la voix de Float).

    python3 src/stories/floatbath.py configs/<name>.json [--simulate]
"""
import math
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base  # noqa: E402
from chapters import StorySim  # noqa: E402
from listkit import Chapter, mix  # noqa: E402
import voice as narr_voice  # noqa: E402
import audio_kit as ak  # noqa: E402

SR = ak.SR
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------------------------------------------ la voix de Float
FLOAT_FILES = [("1_sec.wav", "Float (sec)", "title"), ("2_agace.wav", "Float (agacée)", "f2"),
               ("3_contente.wav", "Float (contente)", "f3"), ("4_glacial.wav", "Float (glaciale)", "f4")]
BANK, ENV = {}, {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr, sw, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    assert sw == 2, f"{path} : 16 bits attendus"
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def load_bank(cfg):
    """Les quatre répliques de Float, lues dans cfg["float_bank"] (dossier hors dépôt).
    Chaque fichier est rogné au son et normalisé ; son enveloppe anime la bouche."""
    BANK.clear(); ENV.clear()
    path = cfg.get("float_bank")
    if not path:
        raise SystemExit("[floatbath] float_bank manquant dans la config")
    path = path if os.path.isabs(path) else os.path.join(ROOT, path)
    for fn, text, _key in FLOAT_FILES:
        x = _read(os.path.join(path, fn))
        idx = np.where(np.abs(x) > 0.02 * np.max(np.abs(x)))[0]
        x = x[max(0, idx[0] - int(0.01 * SR)): idx[-1] + int(0.03 * SR)].copy()
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2
        BANK[text] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        e = np.convolve(e, np.ones(3) / 3, mode="same")
        ENV[text] = e / (e.max() + 1e-9)


def float_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text]
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = float_say
base.subtitle_at = lambda narr, t, n_words: None      # ni sous-titre pour elle, ni pour lui

# ------------------------------------------------------------------ le mot de Bounce
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.74


def steady_hero_word(text, cfg):
    """piper ne rend pas « Bounce » deux fois à la même longueur : on garde, une fois par
    processus, un tirage qui tient dans WORD_MAX (même voix, même mot)."""
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= WORD_MAX:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
G = 1600.0
RB = 56.0                     # Bounce
RF = 96.0                     # Float : environ un cinquième de la largeur
FLOOR = 1540.0
WL = 0.76                     # le plus long « Bounce » retenu, marge comprise
MG = 0.15                     # marge entre deux voix
# la porte (à gauche), le lavabo (tout à gauche), la baignoire, les toilettes
SINK = (4.0, 1230.0, 104.0, 1290.0)
PED = (36.0, 1290.0, 72.0, FLOOR)
DOOR_OPEN = (122.0, 1016.0, 250.0, FLOOR)       # l'ouverture
DOOR_FRAME = (108.0, 1000.0, 264.0, FLOOR)
DOOR_CX = 186.0
TUB_X0, TUB_X1 = 340.0, 830.0
IX0, IX1 = 360.0, 810.0                          # intérieur
RIM_Y = 1180.0
LIP_L = (334.0, RIM_Y, 368.0, 1198.0)
LIP_R = (802.0, RIM_Y, 836.0, 1198.0)
IB = 1495.0                                      # fond intérieur
TUB_BOT = 1515.0
RIM_LX, RIM_RX = 351.0, 819.0
SHELF = (420.0, 610.0, 680.0, 626.0)
TOILET_SEAT = (840.0, 1336.0, 936.0, 1350.0)
LID_UP = (846.0, 1150.0, 930.0, 1338.0)
LID_DOWN = (838.0, 1320.0, 938.0, 1338.0)
TOI_X = 888.0
DRAIN_X = 745.0
FOAM_Y = 1205.0                                  # le niveau de départ, marqué sur la paroi
FLASK_W, FLASK_H = 30.0, 70.0
DUCK_HW, DUCK_HH = 30.0, 24.0

# couleurs
BG = (8, 8, 12)
WALL = (26, 30, 42)
WALL_LINE = (33, 38, 52)
FLOORC = (36, 34, 46)
FLOORC2 = (30, 28, 38)
TUBC = (214, 220, 230)
TUB_IN = (132, 146, 166)
TUB_SH = (150, 158, 172)
WATER = (34, 120, 168)
WATER_A = 0.58
FOAMC = (236, 242, 248)
FOAM_SH = (196, 210, 222)
DOORC = (92, 62, 46)
FRAMEC = (64, 44, 34)
CORRIDOR = (10, 9, 14)
SINKC = (200, 206, 216)
SHELFC = (96, 72, 54)
FLASKC = (120, 150, 170)
DUCKC = (246, 204, 40)
BEAK = (240, 130, 40)
INK = (12, 12, 14)
F_IN = (0x00, 0xCB, 0x80)        # Float : disque intérieur
F_RING = (0x00, 0x79, 0x49)      # Float : anneau extérieur
EYE_W = (246, 248, 244)
CHAIN = (150, 156, 168)


def lin(u):
    return max(0.0, min(1.0, u))


def ease(u):
    u = lin(u)
    return u * u * (3 - 2 * u)


def keyed(keys, t, f=ease):
    """Interpolation entre des clés (t, valeur ou tuple)."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t < t1:
            u = f((t - t0) / max(1e-6, t1 - t0))
            if isinstance(v0, tuple):
                return tuple(a + (b - a) * u for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * u
    return keys[-1][1]


# ------------------------------------------------------------------ le plan
class Plan:
    def __init__(self, cfg, durs, hook_end):
        self.cfg = cfg
        self.durs = durs
        self.hook_end = hook_end
        self.segs = []            # (t0, t1, kind, data)
        self.contacts = []        # dict(t, x, y, surf, voice, nx, ny, amp)
        self.lines = []           # dict(start, end, text, key)
        self.t, self.x, self.y = 0.0, DOOR_CX, 1360.0
        self.lv = []              # baisses de niveau : (t0, durée, delta)
        self.waves = []           # (t0, amplitude, x source)
        self.spills = []          # (t0, côté, volume, durée)
        self.splashes = []        # (t0, x, y, n, vmin, vmax, angle, écart, rayon, graine, mousse)
        self.gaze = [(0.0, (0.0, 0.0))]
        self.shakes = []
        self.mark = {}
        self.build()

    # ---- Bounce
    def arc(self, T, x1, y1, surf, voice="n", nx=0.0, ny=-1.0, amp=0.22):
        t1 = self.t + T
        self.segs.append((self.t, t1, "arc", (self.x, self.y, x1, y1)))
        self.t, self.x, self.y = t1, x1, y1
        self.contacts.append({"t": t1, "x": x1, "y": y1, "surf": surf, "voice": voice, "nx": nx, "ny": ny, "amp": amp})
        return t1

    def line(self, idx, start):
        fn, text, key = FLOAT_FILES[idx]
        d = self.durs[text]
        self.lines.append({"start": start, "end": start + d, "text": text, "key": key})
        return start + d

    def after_word(self, t):
        return t + WL + MG

    def look(self, t, dx, dy, dur=0.25):
        prev = self.gaze[-1][1]
        self.gaze.append((t, prev))
        self.gaze.append((t + dur, (dx, dy)))

    def build(self):
        fy, ry = FLOOR - RB, RIM_Y - RB
        # 0,3 s : la porte claque, il jaillit déjà en l'air
        self.t_door = 0.30
        self.shakes.append((0.30, 12.0))
        self.t = 0.32
        self.t_emerge = 0.32
        c1 = self.arc(max(1.88, self.hook_end + 0.12 - 0.32), 278.0, fy, "floor")
        e1 = self.line(0, self.after_word(c1))                        # « Float. » sec
        self.mark["F1"] = e1 - self.durs[FLOAT_FILES[0][1]]
        c2 = self.arc(max(1.55, e1 + MG + 0.06 - self.t), 54.0, SINK[1] - RB, "sink")
        c3 = self.arc(1.15, 900.0, LID_UP[1] - RB, "lid")             # l'abattant se rabat
        self.mark["lid"] = c3
        self.shakes.append((c3, 4.0))
        c4 = self.arc(1.05, 640.0, SHELF[1] - RB, "shelf")            # le flacon tombe
        self.mark["shelf"] = c4
        self.shakes.append((c4, 4.0))
        c5 = self.arc(1.15, RIM_RX, ry, "rim")                         # une vague passe
        self.waves.append((c5, 9.0, IX1))
        self.lv.append((c5 + 0.05, 0.5, 10.0))
        self.spills.append((c5 + 0.05, "R", 0.6, 0.7))
        self.splashes.append((c5, IX1 - 20, None, 10, 250, 520, -1.75, 0.5, 9, 51, True))
        c6 = self.arc(1.0, RIM_LX, ry, "rim")                          # de l'autre côté
        self.waves.append((c6, 10.0, IX0))
        self.lv.append((c6 + 0.05, 0.4, 8.0))
        self.spills.append((c6 + 0.05, "L", 0.5, 0.6))
        self.splashes.append((c6, IX0 + 20, None, 10, 250, 500, -1.35, 0.5, 9, 52, True))
        c7 = self.arc(0.85, RIM_LX, ry, "rim")
        self.waves.append((c7, 12.0, IX0))
        self.lv.append((c7 + 0.05, 0.5, 18.0))                         # le niveau baisse encore, franchement
        self.spills.append((c7 + 0.05, "L", 0.9, 0.8))
        self.splashes.append((c7, IX0 + 20, None, 14, 280, 560, -1.3, 0.55, 10, 53, True))
        self.t_capsize = c7 + 0.15
        c7b = self.arc(0.85, RIM_LX, ry, "rim")
        self.waves.append((c7b, 7.0, IX0))
        e2 = self.line(1, self.after_word(c7b))                       # « Float. » agacée
        self.mark["F2"] = e2 - self.durs[FLOAT_FILES[1][1]]
        c8 = self.arc(max(1.45, e2 + MG + 0.08 - self.t), RIM_LX, ry, "rim")   # plus haut
        self.waves.append((c8, 14.0, IX0))
        self.lv.append((c8 + 0.05, 0.5, 8.0))
        self.spills.append((c8 + 0.05, "L", 0.5, 0.6))
        self.splashes.append((c8, IX0 + 20, None, 12, 300, 600, -1.3, 0.5, 10, 54, True))
        c9 = self.arc(1.35, 262.0, fy, "floor")                        # le carrelage
        c10 = self.arc(1.35, RIM_LX, ry, "rim")                        # et la gerbe sur Float
        self.mark["gerbe"] = c10
        self.waves.append((c10, 16.0, IX0))
        self.lv.append((c10 + 0.05, 0.5, 10.0))
        self.splashes.append((c10, IX0 + 30, None, 26, 420, 640, -1.05, 0.25, 13, 55, True))
        c11 = self.arc(1.0, RIM_LX, ry, "rim")
        self.waves.append((c11, 7.0, IX0))
        c12 = self.arc(1.2, RIM_RX, ry, "rim")                         # il traverse
        self.waves.append((c12, 9.0, IX1))
        c13 = self.arc(1.45, RIM_LX, ry, "rim")                        # le long rebond, retombe à côté d'elle
        self.mark["long"] = c12
        self.mark["near"] = c13
        self.waves.append((c13, 22.0, IX0))                            # grosse vague
        self.lv.append((c13 + 0.05, 0.6, 14.0))
        self.spills.append((c13 + 0.05, "L", 1.0, 0.9))
        self.splashes.append((c13, IX0 + 20, None, 18, 300, 620, -1.25, 0.6, 11, 56, True))
        # des rebonds courts sur le rebord, en équilibre
        hops = [0.84, 0.82, 0.86, 0.82, 0.84]
        jitter = [4.0, -3.0, 5.0, -2.0, 6.0]
        for T, j in zip(hops, jitter):
            self.arc(T, RIM_LX + j, ry, "rim", amp=0.18)
            self.waves.append((self.t, 4.0, IX0))
        self.mark["wobble"] = self.t
        # il perd l'équilibre : il tombe dans la baignoire (plus rien de dur)
        x_in = 482.0
        t_in = self.t + 0.62
        self.segs.append((self.t, t_in, "arc_free", (self.x, self.y, x_in, None)))
        self.t_plouf = t_in
        self.x_in = x_in
        self.waves.append((t_in, 26.0, x_in))
        self.lv.append((t_in, 0.6, 4.0))
        self.spills.append((t_in + 0.05, "L", 0.4, 0.5))
        self.splashes.append((t_in, x_in, None, 34, 300, 760, -math.pi / 2, 1.1, 13, 57, True))
        self.shakes.append((t_in, 6.0))
        # il flotte, regarde l'eau autour de lui ; silence
        self.look(t_in + 0.9, -0.5, 0.25)
        self.look(t_in + 1.6, 0.5, 0.3)
        self.look(t_in + 2.1, 0.4, 0.0)
        f3 = t_in + 2.35
        e3 = self.line(2, f3)                                          # « Float. » contente
        self.mark["F3"] = f3
        self.look(e3 + 0.75, 0.0, 0.5, dur=0.9)                        # les yeux descendent vers le fond
        t_dive = e3 + 1.75
        t_bot = t_dive + 0.42
        self.t_dive, self.t_bot = t_dive, t_bot
        self.segs.append((t_in, t_dive, "float", (x_in, 492.0)))
        self.segs.append((t_dive, t_bot, "dive", (492.0, 506.0)))
        self.t, self.x, self.y = t_bot, 506.0, IB - RB
        self.contacts.append({"t": t_bot, "x": 506.0, "y": IB - RB, "surf": "bottom", "voice": "m", "nx": 0.0, "ny": -1.0, "amp": 0.25})
        self.look(t_bot, 0.0, 0.0, dur=0.15)
        # il ressort comme un boulet : la moitié de l'eau passe par-dessus
        self.mark["boulet"] = t_bot
        self.shakes.append((t_bot + 0.12, 16.0))
        self.waves.append((t_bot + 0.1, 30.0, 490.0))
        self.lv.append((t_bot + 0.1, 0.9, 99.0))
        self.spills.append((t_bot + 0.12, "L", 4.0, 1.2))
        self.spills.append((t_bot + 0.12, "R", 3.0, 1.2))
        self.splashes.append((t_bot + 0.12, 490.0, None, 60, 400, 1000, -math.pi / 2, 1.3, 14, 58, True))
        cf = self.arc(1.7, 214.0, fy, "floor", voice="n")              # dans la flaque
        self.splashes.append((cf, 214.0, FLOOR, 16, 200, 420, -math.pi / 2, 1.2, 8, 59, False))
        # dans la flaque, de plus en plus haut
        p0 = self.arc(1.12, 190.0, fy, "floor")
        self.mark["p0"] = p0
        self.splashes.append((p0, 190.0, FLOOR, 12, 200, 380, -math.pi / 2, 1.2, 7, 60, False))
        p1 = self.arc(0.8, TUB_X0 - RB, 1290.0, "wall", nx=-1.0, ny=0.0)   # contre la baignoire
        p2 = self.arc(0.78, 176.0, fy, "floor")
        self.mark["p2"] = p2
        self.splashes.append((p2, 176.0, FLOOR, 14, 220, 420, -math.pi / 2, 1.2, 7, 61, False))
        p3 = self.arc(1.6, RIM_RX, ry, "rim")                          # par-dessus la baignoire
        p4 = self.arc(1.0, 910.0, LID_DOWN[1] - RB, "lid")             # sur l'abattant
        p5 = self.arc(1.0, RIM_RX, ry, "rim")                          # le rebord : la chaînette, la bonde saute
        self.mark["p5"] = p5
        self.t_plug = p5 + 0.02
        self.waves.append((p5, 6.0, IX1))
        # le tourbillon
        self.t_whirl = p5 + 0.45
        p6 = self.arc(1.15, RIM_RX, ry, "rim")
        self.look(p6 - 0.6, -0.15, 0.45, dur=0.3)                      # il regarde le tourbillon
        p7 = self.arc(1.7, RIM_RX, ry, "rim")
        self.t_duck = p7 + WL + 0.3                                    # le canard bouche le trou
        p8 = self.arc(1.7, RIM_RX, ry, "rim")                          # à côté d'elle
        self.look(p8 - 0.5, -0.4, 0.2, dur=0.3)
        self.mark["p8"] = p8
        e4 = self.line(3, self.after_word(p8))                         # « Float. » glaciale
        self.mark["F4"] = e4 - self.durs[FLOAT_FILES[3][1]]
        self.mark["F4e"] = e4
        self.mark["door_look"] = e4 + 0.15
        p9 = self.arc(min(1.75, max(1.4, e4 + MG + 0.05 - self.t)), RIM_RX, ry, "rim")
        self.look(e4 + 0.45, -0.6, 0.0, dur=0.4)                       # il suit son regard vers la porte
        p10 = self.arc(1.4, RIM_LX, ry, "rim")
        p11 = self.arc(1.35, 256.0, fy, "floor")                       # le carrelage, vers la porte
        self.mark["p11"] = p11
        self.splashes.append((p11, 268.0, FLOOR, 10, 180, 360, -math.pi / 2, 1.2, 7, 62, False))
        for k, (T, x1) in enumerate([(0.88, 244.0), (0.84, 222.0), (0.82, 204.0)]):
            tk = self.arc(T, x1, fy, "floor", amp=0.18)
            self.splashes.append((tk, x1, FLOOR, 8 - k * 2, 140, 300, -math.pi / 2, 1.2, 6, 63 + k, False))
        # sur le seuil : il se retourne vers la baignoire, tout petits rebonds sur place
        self.look(self.t + 0.1, 0.55, 0.0, dur=0.3)
        self.mark["seuil"] = self.t
        for T in [0.62, 0.56, 0.52, 0.5, 0.48, 0.44]:
            self.arc(T, DOOR_CX, fy, "floor", voice="s", amp=0.16)
        self.mark["tasse"] = self.t
        for T in [0.4, 0.36, 0.32]:                                    # il se tasse, de plus en plus bas
            self.arc(T, DOOR_CX, fy, "floor", voice="s", amp=0.34)
        self.arc(0.45, DOOR_CX, fy, "floor", voice="s", amp=0.36)
        self.mark["eye_open"] = self.t - 0.6
        last = self.arc(1.0, DOOR_CX, fy, "floor", amp=0.3)          # un dernier rebond, plus haut, sur place
        self.mark["last"] = last
        # il se détend, se tourne vers la porte, sort
        self.look(last + 0.35, -0.5, -0.1, dur=0.35)
        self.look(last + 0.95, 0.0, 0.0, dur=0.25)                    # le visage bien visible dans l'encadrement
        t_out0 = last + 0.25
        t_out1 = t_out0 + 2.1                                         # encore dans l'encadrement quand la porte se ferme
        self.segs.append((last, t_out1, "exit", (DOOR_CX,)))
        self.t_exit0, self.t_exit1 = t_out0, t_out1
        self.t_ohno = last + 1.3
        self.t_payoff = self.t_ohno - 0.15
        self.t_close0 = self.t_ohno + 0.55
        self.t_close1 = self.t_close0 + 0.6
        # derrière la porte : deux « Bounce » étouffés, la porte vibre
        self.t_smile = self.t_close1 + 2.0
        k1 = self.t_close1 + 3.6
        k2 = k1 + 1.8
        for k in (k1, k2):
            self.contacts.append({"t": k, "x": DOOR_CX, "y": fy, "surf": "door", "voice": "m", "nx": 0, "ny": -1, "amp": 0})
        self.t_knock = (k1, k2)
        self.t_eye_last = k1 + 1.0
        self.t_cut = k2 + 1.0
        self.end = self.t_cut + 0.7
        self.segs.append((t_out1, self.end + 5, "gone", ()))
        self.segs.sort(key=lambda s: s[0])
        self.contacts.sort(key=lambda c: c["t"])
        self.gaze.sort(key=lambda g: g[0])

    # ---- états à l'instant T
    def level(self, T):
        L = FOAM_Y
        for (t0, d, dl) in self.lv:
            L += dl * ease((T - t0) / d)
        # le tourbillon vide le fond d'eau jusqu'au bouchon
        if T > self.t_whirl:
            u = lin((T - self.t_whirl) / (self.t_duck - self.t_whirl))
            L += 66.0 * (u ** 0.85)
        return L

    def whirl(self, T):
        """Intensité du tourbillon (0..1) : monte, puis s'arrête net au bouchon."""
        if T < self.t_whirl:
            return 0.0
        if T < self.t_duck:
            return 0.25 + 0.75 * lin((T - self.t_whirl) / (self.t_duck - self.t_whirl))
        return max(0.0, 1.0 - (T - self.t_duck) / 0.18)

    def surface(self, x, T):
        L = self.level(T)
        Lw = IX1 - IX0
        u = (x - IX0) / Lw
        eta = 0.0
        for (t0, A, xs) in self.waves:
            tau = T - t0
            if tau < 0 or tau > 6.0:
                continue
            env = A * math.exp(-tau / 1.4) * lin(tau / 0.08)
            side = -1.0 if xs < (IX0 + IX1) / 2 else 1.0
            eta += env * side * math.cos(math.pi * u) * math.cos(2 * math.pi * 0.9 * tau)
            eta += 0.45 * env * math.cos(2 * math.pi * u) * math.sin(2 * math.pi * 1.4 * tau + xs * 0.01)
            # l'onde qui part de l'impact
            d = abs(x - xs) - 520.0 * tau
            eta += 0.6 * env * math.exp(-(d / 60.0) ** 2)
        eta += 1.5 * math.sin(T * 1.7 + x * 0.02)
        w = self.whirl(T)
        if w > 0:
            eta += 18.0 * w * math.exp(-((x - DRAIN_X) / 55.0) ** 2)
        y = L - eta
        return min(y, IB - 2.0)

    def seg_at(self, T):
        for s in self.segs:
            if s[0] <= T < s[1]:
                return s
        return self.segs[-1] if T >= self.segs[-1][0] else None

    def bounce(self, T):
        """dict : x, y, sx, sy, scale, hidden, behind (dans le couloir), water."""
        st = {"x": DOOR_CX, "y": 1360.0, "sx": 1.0, "sy": 1.0, "scale": 1.0, "hidden": False,
              "behind": False, "water": False}
        if T < self.t_emerge:
            st["hidden"] = True
            return st
        s = self.seg_at(T)
        if s is None:
            st["hidden"] = True
            return st
        t0, t1, k, d = s
        tau = T - t0
        if k == "arc":
            x0, y0, x1, y1 = d
            Tt = t1 - t0
            vy0 = (y1 - y0) / Tt - 0.5 * G * Tt
            st["x"] = x0 + (x1 - x0) * tau / Tt
            st["y"] = y0 + vy0 * tau + 0.5 * G * tau * tau
        elif k == "arc_free":
            x0, y0, x1, _ = d
            Tt = t1 - t0
            y1 = self.surface(x1, t1) - 0.42 * RB
            vy0 = (y1 - y0) / Tt - 0.5 * G * Tt
            st["x"] = x0 + (x1 - x0) * tau / Tt
            st["y"] = y0 + vy0 * tau + 0.5 * G * tau * tau
        elif k == "float":
            st["x"], st["y"] = self._floating(T, s)
            st["water"] = True
        elif k == "dive":
            x0, x1 = d
            u = lin(tau / (t1 - t0))
            fs = self.seg_at(t0 - 1e-6)
            xs, y0 = self._floating(t0, fs)
            st["x"] = xs + (x1 - xs) * u
            st["y"] = y0 + (IB - RB - y0) * u * u
            st["water"] = True
        elif k == "exit":
            (xc,) = d
            # il se détend, puis recule dans le couloir par petits sauts
            if T < self.t_exit0:
                st["x"], st["y"] = xc, FLOOR - RB
            else:
                u = lin((T - self.t_exit0) / (self.t_exit1 - self.t_exit0))
                sc = 1.0 - 0.18 * ease(u)
                hop = abs(math.sin(u * math.pi * 2.0)) * 26.0 * (1 - u)
                st["scale"] = sc
                st["behind"] = u > 0.0
                st["x"] = xc
                st["y"] = FLOOR - 26.0 * ease(u) - RB * sc - hop
        else:
            st["hidden"] = True
            return st
        if T < self.t_emerge + 0.15:
            u = lin((T - self.t_emerge) / 0.15)
            st["scale"] = 0.7 + 0.3 * ease(u)
            st["behind"] = u < 1.0
        # écrasement aux contacts
        for c in self.contacts:
            if c["amp"] <= 0 or not (c["t"] - 0.05 <= T <= c["t"] + 0.11):
                continue
            kk = lin(1 - (c["t"] - T) / 0.05 if T < c["t"] else 1 - (T - c["t"]) / 0.11)
            a = c["amp"] * kk
            if c["nx"]:
                st["sx"], st["sy"] = 1 - a, 1 + 0.6 * a
                st["x"] = c["x"] + RB * a * (1 if c["nx"] < 0 else -1)
            else:
                st["sy"], st["sx"] = 1 - a, 1 + 0.7 * a
                st["y"] = c["y"] + RB * a
        if st["y"] > FLOOR - RB * st["sy"] * st["scale"] and not st["behind"]:
            st["y"] = FLOOR - RB * st["sy"] * st["scale"]
        return st

    def _floating(self, T, s):
        t0, t1, k, (x0, x1) = s
        tau = T - t0
        u = ease(tau / (t1 - t0))
        x = x0 + (x1 - x0) * u + 6.0 * math.sin(T * 2.3) * lin(tau / 0.6)
        yf = self.surface(x, T) - 0.42 * RB
        # l'entrée : il s'enfonce, puis remonte et danse sur la surface
        yf += 46.0 * math.exp(-tau / 0.35) * math.sin(min(math.pi, tau / 0.5 * math.pi))
        yf += 4.0 * math.sin(2 * math.pi * 1.6 * tau)
        return x, yf

    def gaze_at(self, T):
        return keyed(self.gaze, T)


# ------------------------------------------------------------------ les autres acteurs
class Actors:
    """Float, le canard, le flacon, la bonde, l'abattant, la porte : positions à l'instant T."""

    def __init__(self, plan):
        self.p = plan
        p = plan
        m = p.mark
        # Float : au milieu, puis ballottée ; contre la paroi au boulet ; aspirée au tourbillon
        self.fx_keys = [(0.0, 584.0), (m["shelf"] + 0.7, 584.0), (m["shelf"] + 1.6, 572.0),
                        (m["gerbe"] - 0.6, 560.0), (m["gerbe"] + 1.0, 548.0),
                        (m["near"] - 1.2, 494.0), (m["near"] + 0.15, 494.0), (m["near"] + 1.4, 640.0),
                        (p.t_bot + 0.12, 642.0), (p.t_bot + 0.9, 458.0), (p.t_whirl, 458.0)]
        # le canard : à côté d'elle, chavire, se range contre la paroi de droite, bouche le trou
        self.dx_keys = [(0.0, 732.0), (m["shelf"] + 1.5, 736.0), (p.t_capsize + 1.0, 744.0),
                        (m["near"] - 0.5, 752.0), (m["near"] + 1.4, 772.0), (p.t_whirl, 772.0)]
        self.f_end = DRAIN_X - (DUCK_HW + RF + 8.0)
        self.flask_t0 = m["shelf"] + 0.04
        self.flask_x0 = 455.0
        # instant où le flacon touche l'eau
        y0 = SHELF[1] - FLASK_H / 2
        t = 0.0
        while True:
            yb = y0 + 0.5 * G * t * t + FLASK_H / 2
            if yb >= p.surface(self.flask_x0, self.flask_t0 + t) or t > 2:
                break
            t += 1 / 240
        self.flask_tin = self.flask_t0 + t
        self.flask_vin = G * t
        self.flask_yin = y0 + 0.5 * G * t * t
        p.splashes.append((self.flask_tin, self.flask_x0, None, 30, 300, 700, -math.pi / 2, 0.9, 11, 70, True))
        p.waves.append((self.flask_tin, 18.0, self.flask_x0))
        p.lv.append((self.flask_tin + 0.05, 0.6, 20.0))                 # la gerbe passe par-dessus le bord
        p.spills.append((self.flask_tin + 0.1, "L", 1.2, 0.8))
        p.mark["flask_in"] = self.flask_tin

    # Float
    def float_xa(self, T):
        p = self.p
        x = keyed(self.fx_keys, T)
        if T >= p.t_whirl:
            span = p.t_duck - p.t_whirl
            tw = min(T, p.t_duck) - p.t_whirl
            u = lin(tw / span)
            xc = 458.0 + (self.f_end - 20.0 - 458.0) * ease(u)
            A = 60.0 * math.sin(math.pi * u) ** 0.8
            x = xc + A * math.sin(2.0 * tw + 3.5 * tw * tw / span)
            if T > p.t_duck:
                x = x + (self.f_end - x) * ease((T - p.t_duck) / 0.6)
            dx, _ = self.duck_xy(T)
            x = min(x, dx - (DUCK_HW + RF + 8.0))
        return max(IX0 + RF + 2, min(IX1 - RF - 2, x))

    def float_spin(self, T):
        p = self.p
        a = 0.0
        # projetée contre la paroi au boulet : elle tourne sur elle-même (un tour complet et demi)
        tb = p.t_bot + 0.15
        if T > tb:
            a += -2 * math.pi * 2.0 * ease((T - tb) / 2.4)
        if T > p.t_whirl:
            span = p.t_duck - p.t_whirl
            tw = min(T, p.t_duck) - p.t_whirl
            turns_raw = 1.2 * tw + 2.6 * tw * tw / span
            total = 1.2 * span + 2.6 * span
            n = math.ceil(total / (2 * math.pi))
            scale = n * 2 * math.pi / total
            a += -turns_raw * scale
        return a

    def float_state(self, T):
        p = self.p
        x = self.float_xa(T)
        s0, s1 = p.surface(x - 40, T), p.surface(x + 40, T)
        surf = (s0 + s1) / 2
        y = surf - (RF - 0.3 * RF)
        y += 3.0 * math.sin(T * 2.1)
        g = p.mark["gerbe"] + 0.45
        if g <= T < g + 1.2:
            y += 20.0 * math.sin(math.pi * (T - g) / 1.2)
        y = min(y, IB - RF - 1.0)
        slope = math.atan2(s1 - s0, 80.0)
        a = 0.55 * slope + 0.04 * math.sin(T * 1.9) + self.float_spin(T)
        return x, y, a

    # le canard
    def duck_xy(self, T):
        p = self.p
        x = keyed(self.dx_keys, T)
        if T >= p.t_whirl:
            span = p.t_duck - p.t_whirl
            u = lin((T - p.t_whirl) / span)
            xc = 772.0 + (DRAIN_X - 772.0) * ease(u)
            A = 22.0 * math.sin(math.pi * u)
            x = xc + A * math.sin(3.0 * (T - p.t_whirl) + 5 * (T - p.t_whirl) ** 2 / span)
            if T >= p.t_duck:
                x = DRAIN_X
        surf = p.surface(x, T)
        y = surf - 4.0
        y = min(y, IB - DUCK_HH)
        if T >= p.t_duck - 0.25:
            u = lin((T - (p.t_duck - 0.25)) / 0.25)
            y = y + (IB - DUCK_HH + 4 - y) * ease(u)
        return x, y

    def duck_angle(self, T):
        p = self.p
        a = math.pi * ease((T - p.t_capsize) / 0.45)
        a += 0.12 * math.sin(T * 2.4)
        if T > p.t_whirl:
            a += 0.25 * math.sin(4.0 * (T - p.t_whirl)) * (1 - lin((T - p.t_duck) / 0.3))
        if T >= p.t_duck:
            a = math.pi + 0.12 * math.sin(p.t_duck * 2.4) * max(0, 1 - (T - p.t_duck) / 0.4)
        return a

    # le flacon
    def flask(self, T):
        """(x, y, angle) du centre du flacon."""
        p = self.p
        x0 = self.flask_x0
        y0 = SHELF[1] - FLASK_H / 2
        if T < self.flask_t0:
            # il tremble quand Bounce secoue l'étagère
            return x0, y0, 0.0
        t = T - self.flask_t0
        if T < self.flask_tin:
            return x0 - 10 * t, y0 + 0.5 * G * t * t, -0.9 * t
        ti = T - self.flask_tin
        a_in = -0.9 * (self.flask_tin - self.flask_t0)
        x_in = x0 - 10 * (self.flask_tin - self.flask_t0)
        # dans l'eau : il ralentit, coule, se couche au fond
        rest_y = IB - FLASK_W / 2
        k = 1 - math.exp(-ti / 0.35)
        y = self.flask_yin + (self.flask_vin * 0.35) * k + 160 * ti
        x = x_in + (400.0 - x_in) * ease(ti / 1.6)
        a = a_in + (-math.pi / 2 - a_in) * ease(ti / 1.4)
        if y >= rest_y:
            y = rest_y
        return x, y, a

    # la bonde
    def plug(self, T):
        p = self.p
        if T < p.t_plug:
            return DRAIN_X, IB - 5, 0.0
        t = T - p.t_plug
        # elle saute au bout de sa chaînette et retombe contre la paroi
        xr, yr = DRAIN_X + 40.0, IB - 70.0
        u = ease(t / 0.5)
        hop = 90.0 * math.sin(math.pi * lin(t / 0.5))
        return DRAIN_X + (xr - DRAIN_X) * u, IB - 5 + (yr - IB + 5) * u - hop, 1.2 * u

    def lid(self, T):
        """0 = relevé, 1 = rabattu."""
        return ease((T - self.p.mark["lid"]) / 0.16)

    def door(self, T):
        """Angle d'ouverture de la porte (0 fermée, 1 ouverte) et son tremblement."""
        p = self.p
        a = 0.0
        if T >= p.t_door:
            u = (T - p.t_door) / 0.12
            a = lin(u) if u < 1 else 1.0 - 0.12 * math.exp(-(T - p.t_door - 0.12) / 0.15) * abs(math.sin((T - p.t_door - 0.12) * 18))
        if T >= p.t_close0:
            a = 1.0 - ease((T - p.t_close0) / (p.t_close1 - p.t_close0))
        sh = 0.0
        for (k, amp) in zip(p.t_knock, (4.0, 7.0)):
            tt = T - k
            if 0 <= tt < 0.9:
                sh += amp * math.exp(-tt / 0.25) * math.sin(tt * 60)
        return a, sh

    def camera(self, T):
        p = self.p
        m = p.mark
        if not hasattr(self, "_cam"):
            e4 = m["F4e"]
            self._cam = [(0.0, (1.16, 580.0, 1290.0)), (p.t_door, (1.16, 580.0, 1290.0)), (p.t_door + 0.9, (1.05, 552.0, 1060.0)),
                         (m["F1"] + 0.3, (1.0, 540.0, 960.0)),
                         (m["F2"], (1.0, 540.0, 960.0)), (m["gerbe"] + 0.3, (1.12, 520.0, 1200.0)),
                         (m["near"] + 0.4, (1.0, 540.0, 960.0)), (m["wobble"], (1.15, 520.0, 1230.0)),
                         (p.t_plouf + 0.6, (1.1, 560.0, 1210.0)), (p.t_bot - 0.2, (1.3, 590.0, 1290.0)),
                         (p.t_bot + 0.1, (1.3, 590.0, 1290.0)), (p.t_bot + 0.85, (1.0, 540.0, 960.0)),
                         (m["p0"], (1.0, 540.0, 960.0)), (m["p2"], (1.08, 500.0, 1100.0)), (m["p5"], (1.12, 640.0, 1210.0)),
                         (p.t_duck - 1.2, (1.0, 540.0, 960.0)), (p.t_duck + 0.6, (1.22, 640.0, 1240.0)),
                         (e4 + 0.9, (1.24, 640.0, 1240.0)), (e4 + 1.6, (1.0, 540.0, 960.0)),
                         (m["p11"], (1.0, 540.0, 960.0)), (m["seuil"], (1.5, 400.0, 1330.0)),
                         (m["last"] + 0.2, (1.58, 400.0, 1330.0)), (p.t_ohno + 0.4, (1.9, 330.0, 1370.0)),
                         (p.t_close1 + 0.4, (1.52, 410.0, 1330.0)),
                         (p.t_knock[0] - 0.05, (2.0, 600.0, 1345.0)), (p.t_knock[0] + 0.55, (1.55, 420.0, 1330.0)),
                         (p.t_knock[1] + 0.3, (1.68, 455.0, 1330.0)), (p.t_cut, (1.8, 480.0, 1325.0))]
        if T < p.t_cut:
            z, cx, cy = keyed(self._cam, T)
        else:
            # coupe sur l'œil ouvert de Float
            fx, fy, fa = self.float_state(T)
            ex, ey = face_point(fx, fy, fa, RF, -0.2, -0.13)
            z, cx, cy = 6.5, ex + 6.0, ey + 8.0
        ox = oy = 0.0
        for (t, a) in p.shakes:
            u = T - t
            if 0 <= u < 0.5:
                k = a * math.exp(-u / 0.12)
                ox += k * math.sin(2 * math.pi * 17 * u)
                oy += k * math.cos(2 * math.pi * 13 * u)
        return cx, cy, z, ox, oy


def face_point(x, y, a, r, u, v):
    ca, sa = math.cos(a), math.sin(a)
    return x + (u * ca - v * sa) * r, y + (u * sa + v * ca) * r


# ------------------------------------------------------------------ Float : son visage
EXPR = {
    "serene": {"eyes": ("closed", "closed"), "brow": None, "mouth": "smile"},
    "calm": {"eyes": ("closed", "closed"), "brow": None, "mouth": "flat"},
    "slit": {"eyes": ("slit", "closed"), "brow": "V", "mouth": "flat"},
    "squint": {"eyes": ("squint", "squint"), "brow": "tilt", "mouth": "frown"},
    "squint_flat": {"eyes": ("squint", "squint"), "brow": "tilt", "mouth": "flat"},
    "wide": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "csmile"},
    "wide_o": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "o"},
    "wide_flat": {"eyes": ("wide", "wide"), "brow": "up", "mouth": "flat"},
    "glacial": {"eyes": ("lid", "lid"), "brow": "flat", "mouth": "flat"},
    "slit_door": {"eyes": ("slit", "closed"), "brow": "V", "mouth": "flat"},
}


def draw_float(dr, V, x, y, a, expr, look=(0.0, 0.0), mouth=0.0, nod=0.0, foam=0.0):
    """Float, d'après la référence du fan : disque #00CB80, anneau épais #007949 (un quart
    du rayon), deux yeux en « Y » en miroir (un trait vertical, un cil en diagonale vers
    l'extérieur et le haut), un petit sourire en U. Toutes les expressions gardent ce trait
    noir épais et arrondi."""
    r = RF
    dr.ellipse(V.box(x - r, y - r, x + r, y + r), fill=F_RING)
    ri = r * 0.735
    dr.ellipse(V.box(x - ri, y - ri, x + ri, y + ri), fill=F_IN)
    ca, sa = math.cos(a), math.sin(a)
    dy0 = nod

    def P(u, v):
        v = v + dy0
        return V.X(x + (u * ca - v * sa) * r), V.Y(y + (u * sa + v * ca) * r)

    wst = 0.072

    def stroke(pts, w=wst, col=INK):
        q = [P(u, v) for u, v in pts]
        lw = max(1, int(V.L(w * r)))
        dr.line(q, fill=col, width=lw, joint="curve")
        rr = V.L(w * r) / 2
        for (qx, qy) in (q[0], q[-1]):
            dr.ellipse([qx - rr, qy - rr, qx + rr, qy + rr], fill=col)

    def blob(u, v, ru, rv, col, n=20):
        dr.polygon([P(u + ru * math.cos(k * 2 * math.pi / n), v + rv * math.sin(k * 2 * math.pi / n)) for k in range(n)], fill=col)

    def arc_pts(u, v, ru, rv, a0, a1, n=10):
        return [(u + ru * math.cos(a0 + (a1 - a0) * k / n), v + rv * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    lx, ly = look
    for side, state in zip((-1, 1), expr["eyes"]):
        ex = 0.197 * side
        if state == "closed":
            stroke([(ex, -0.325), (ex, 0.02)])
            stroke([(0.19 * side, -0.20), (0.40 * side, -0.315)])
            continue
        cy = -0.15
        if state == "wide":
            ru, rv, top, bot = 0.13, 0.18, -1.0, 1.0
        elif state == "squint":
            ru, rv, top, bot = 0.135, 0.16, -0.4, 0.55
        elif state == "slit":
            ru, rv, top, bot = 0.135, 0.16, 0.0, 1.0
        else:  # "lid" : paupière lourde, regard glacial
            ru, rv, top, bot = 0.135, 0.16, -0.2, 1.0
        # le blanc visible entre les paupières
        pts = []
        for k in range(25):
            th = math.pi * k / 24
            u = ex + ru * math.cos(th + math.pi)
            vv = rv * math.sin(th + math.pi)
            pts.append((u, cy + max(vv, top * rv)))
        for k in range(25):
            th = math.pi * k / 24
            u = ex + ru * math.cos(th)
            vv = rv * math.sin(th)
            pts.append((u, cy + min(vv, bot * rv)))
        dr.polygon([P(u, v) for u, v in pts], fill=EYE_W)
        # la pupille, qui regarde
        pr = 0.062 if state != "wide" else 0.07
        pu = ex + lx * (ru - pr) * 0.85
        pv = cy + ly * (rv - pr) * 0.6
        lo, hi = cy + top * rv + pr * 0.4, cy + bot * rv - pr * 0.4
        if lo < hi:
            pv = max(lo, min(hi, pv))
        blob(pu, pv, pr, pr, INK)
        # ce qui dépasse des paupières est recouvert de peau
        if top > -1.0:
            blob(ex, cy + top * rv - 0.12, ru + 0.03, 0.12, F_IN)
        if bot < 1.0:
            blob(ex, cy + bot * rv + 0.12, ru + 0.03, 0.12, F_IN)
        # les traits : paupières et contour, dans le trait de la référence
        if top > -1.0:
            stroke([(ex - ru, cy + top * rv), (ex + ru, cy + top * rv)])
        else:
            stroke(arc_pts(ex, cy, ru, rv, math.pi, 2 * math.pi), w=0.055)
        if bot < 1.0:
            # la paupière du bas, une courbe fine qui remonte le blanc
            stroke(arc_pts(ex, cy + bot * rv - 0.03, ru * 0.85, 0.05, 0.15 * math.pi, 0.85 * math.pi, 8), w=0.045)
        else:
            stroke(arc_pts(ex, cy, ru, rv, 0, math.pi), w=0.055)
        # le cil de la référence, du coin extérieur vers le haut
        yt = cy + (top * rv if top > -1.0 else -rv * 0.6)
        stroke([(ex + side * ru * 0.9, yt), (ex + side * (ru + 0.12), yt - 0.08)])
    # les sourcils
    b = expr["brow"]
    if b == "V":
        for side in (-1, 1):
            stroke([(0.07 * side, -0.37), (0.30 * side, -0.48)])
    elif b == "tilt":
        for side in (-1, 1):
            stroke([(0.06 * side, -0.35), (0.31 * side, -0.52)])
    elif b == "up":
        for side in (-1, 1):
            stroke(arc_pts(0.2 * side, -0.38, 0.12, 0.06, math.pi * 1.1, math.pi * 1.9, 8))
    elif b == "flat":
        for side in (-1, 1):
            stroke([(0.09 * side, -0.33), (0.31 * side, -0.33)])
    # la bouche
    mo = expr["mouth"]
    m = max(0.0, min(1.0, mouth))
    if mo in ("smile", "csmile"):
        rx = 0.165 if mo == "smile" else 0.19
        ry = 0.145 if mo == "smile" else 0.12
        if m > 0.05:
            pts = arc_pts(0.0, 0.18, rx, ry + 0.05 * m, 0.0, math.pi, 12)
            dr.polygon([P(u, v) for u, v in pts], fill=(30, 40, 34))
        stroke(arc_pts(0.0, 0.18, rx, ry + 0.05 * m, 0.0, math.pi, 12))
    elif mo == "flat":
        if m > 0.05:
            blob(0.0, 0.25, 0.12, 0.05 * m + 0.01, (30, 40, 34))
        stroke([(-0.13, 0.25 - 0.02 * m), (0.13, 0.25 - 0.02 * m)])
    elif mo == "frown":
        if m > 0.05:
            blob(0.0, 0.27, 0.11, 0.05 * m + 0.01, (30, 40, 34))
        stroke(arc_pts(0.0, 0.33, 0.15, 0.09, math.pi * 1.0, math.pi * 2.0, 10))
    elif mo == "o":
        blob(0.0, 0.27, 0.07, 0.09 + 0.03 * m, INK)
    if foam > 0:
        k = foam
        for (u, v, rr) in ((-0.35, -0.85, 0.28), (0.0, -0.98, 0.34), (0.35, -0.86, 0.27), (-0.15, -1.15, 0.2),
                           (0.2, -1.12, 0.22)):
            blob(u, v + (1 - k) * 0.3, rr * k, rr * k * 0.85, FOAMC)


# ------------------------------------------------------------------ dessin
class View:
    def __init__(self, S, cam):
        self.S = S
        self.cx, self.cy, self.z, self.ox, self.oy = cam

    def X(self, x):
        return (W / 2 + (x - self.cx) * self.z + self.ox) * self.S

    def Y(self, y):
        return (H / 2 + (y - self.cy) * self.z + self.oy) * self.S

    def L(self, l):
        return l * self.z * self.S

    def pts(self, pts):
        return [(self.X(x), self.Y(y)) for x, y in pts]

    def box(self, x0, y0, x1, y1):
        return [self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)]


def rrect(dr, V, x0, y0, x1, y1, r, fill):
    dr.rounded_rectangle(V.box(x0, y0, x1, y1), radius=max(0, int(V.L(r))), fill=fill)


def rot(pts, x, y, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(x + dx * ca - dy * sa, y + dx * sa + dy * ca) for dx, dy in pts]


def flask_poly(x, y, a):
    hw, hh = FLASK_W / 2, FLASK_H / 2
    return rot([(-hw, -hh * 0.55), (-hw * 0.45, -hh), (hw * 0.45, -hh), (hw, -hh * 0.55), (hw, hh), (-hw, hh)], x, y, a)


def duck_poly(x, y, a):
    return rot([(-DUCK_HW, -DUCK_HH), (DUCK_HW, -DUCK_HH), (DUCK_HW, DUCK_HH), (-DUCK_HW, DUCK_HH)], x, y, a)


def float_poly(x, y):
    return [(x + RF * math.cos(k * math.pi / 8), y + RF * math.sin(k * math.pi / 8)) for k in range(16)]


class Scene:
    """Le dessin de la salle de bain à l'instant T."""

    def __init__(self, plan, actors):
        self.p, self.a = plan, actors
        rng = np.random.default_rng(11)
        self.foam_seed = [(float(rng.uniform(0, 1)), float(rng.uniform(0, 1)), float(rng.uniform(0.6, 1.0))) for _ in range(60)]
        self.drops = self._drops()

    def _drops(self):
        out = []
        for (t0, x, y, n, vmin, vmax, ang, spread, rad, seed, foam) in self.p.splashes:
            rng = np.random.default_rng(seed)
            y0 = self.p.surface(x, t0) if y is None else y
            for k in range(n):
                a = ang + float(rng.uniform(-spread, spread))
                v = float(rng.uniform(vmin, vmax))
                r = rad * float(rng.uniform(0.5, 1.1))
                fo = foam and rng.random() < 0.4
                out.append((t0, x + float(rng.uniform(-14, 14)), y0, v * math.cos(a), v * math.sin(a), r, fo))
        return out

    def draw(self, dr, T, S):
        p, A = self.p, self.a
        V = View(S, A.camera(T))
        img = dr._image
        full = View(S, (W / 2, H / 2, 1.0, 0.0, 0.0))
        dr.rectangle(full.box(0, 0, W, H), fill=BG)
        # le mur carrelé
        dr.rectangle(V.box(-600, 300, W + 600, FLOOR), fill=WALL)
        step = 90.0
        lw = max(1, int(V.L(3)))
        for k in range(-8, 20):
            xx = k * step
            dr.line([(V.X(xx), V.Y(300)), (V.X(xx), V.Y(FLOOR))], fill=WALL_LINE, width=lw)
        for k in range(0, 15):
            yy = FLOOR - k * step
            dr.line([(V.X(-600), V.Y(yy)), (V.X(W + 600), V.Y(yy))], fill=WALL_LINE, width=lw)
        # le sol
        dr.rectangle(V.box(-600, FLOOR, W + 600, H + 600), fill=FLOORC)
        for k in range(-8, 20):
            for j in range(0, 5):
                if (k + j) % 2 == 0:
                    dr.rectangle(V.box(k * 80, FLOOR + j * 80, k * 80 + 80, FLOOR + j * 80 + 80), fill=FLOORC2)
        dr.rectangle(V.box(-600, FLOOR, W + 600, FLOOR + 6), fill=mix(FLOORC, (120, 120, 140), 0.3))
        self.draw_mirror_sink(dr, V)
        b = p.bounce(T)
        self.draw_door(dr, V, T, b)
        self.draw_shelf(dr, V, T)
        self.draw_toilet(dr, V, T)
        self.draw_puddles(dr, V, T)
        self.draw_tub(dr, V, T, b, img)
        if not b["hidden"] and not b["behind"] and not b["water"]:
            self.draw_bounce(dr, V, b, T)
        self.draw_drops(dr, V, T)

    # -- décor
    def draw_mirror_sink(self, dr, V):
        rrect(dr, V, 12, 1040, 98, 1170, 10, (58, 70, 86))
        rrect(dr, V, 20, 1048, 90, 1162, 8, (74, 92, 112))
        dr.line([(V.X(34), V.Y(1070)), (V.X(58), V.Y(1046 + 10))], fill=(110, 130, 150), width=max(1, int(V.L(4))))
        rrect(dr, V, PED[0], PED[1], PED[2], PED[3], 6, mix(SINKC, WALL, 0.25))
        dr.chord(V.box(SINK[0] + 4, SINK[1] - 30, SINK[2] - 4, SINK[3] + 4), 0, 180, fill=SINKC)
        rrect(dr, V, SINK[0], SINK[1], SINK[2], SINK[1] + 12, 5, mix(SINKC, (255, 255, 255), 0.3))
        rrect(dr, V, 6, 1200, 18, 1230, 3, (150, 156, 168))      # le robinet, contre le mur

    def draw_door(self, dr, V, T, b):
        p, A = self.p, self.a
        ang, sh = A.door(T)
        x0, y0, x1, y1 = DOOR_OPEN
        dr.rectangle(V.box(x0, y0, x1, y1), fill=CORRIDOR)
        dr.rectangle(V.box(x0, y1 - 30, x1, y1), fill=(16, 15, 22))
        if not b["hidden"] and b["behind"]:
            self.draw_bounce(dr, V, b, T)
        fx0, fy0, fx1, fy1 = DOOR_FRAME
        dr.rectangle(V.box(fx0, fy0, x0, fy1), fill=FRAMEC)
        dr.rectangle(V.box(x1, fy0, fx1, fy1), fill=FRAMEC)
        dr.rectangle(V.box(fx0, fy0, fx1, y0), fill=FRAMEC)
        # le panneau : charnière à gauche ; ouvert, il pivote vers nous (perspective)
        th = ang * math.radians(95)
        xe = x0 + (x1 - x0) * math.cos(th) + sh
        grow = 26.0 * math.sin(th)
        pts = [(x0 + sh * 0.3, y0), (xe, y0 - grow), (xe, y1 + grow * 0.5), (x0 + sh * 0.3, y1)]
        if abs(xe - x0) < 3:
            pts = [(x0 - 3, y0 - grow), (x0 + 3, y0 - grow), (x0 + 3, y1), (x0 - 3, y1)]
        dr.polygon(V.pts(pts), fill=DOORC if math.cos(th) > 0 else mix(DOORC, (0, 0, 0), 0.25))
        if math.cos(th) > 0.2:
            inset = 16 * math.cos(th)
            for (ya, yb) in ((y0 + 40, y0 + 230), (y0 + 270, y1 - 40)):
                q = [(x0 + inset + sh * 0.3, ya), (xe - inset, ya - grow * 0.8), (xe - inset, yb - grow * 0.2), (x0 + inset + sh * 0.3, yb)]
                dr.polygon(V.pts(q), outline=mix(DOORC, (0, 0, 0), 0.3), width=max(1, int(V.L(4))))
            kx = xe - 18 * math.cos(th)
            dr.ellipse(V.box(kx - 8, 1290 - 8, kx + 8, 1290 + 8), fill=(200, 170, 90))

    def draw_shelf(self, dr, V, T):
        p, A = self.p, self.a
        jolt = 0.0
        tS = p.mark["shelf"]
        if 0 <= T - tS < 0.4:
            jolt = 5.0 * math.exp(-(T - tS) / 0.08) * math.sin((T - tS) * 60)
        x0, y0, x1, y1 = SHELF
        dr.rectangle(V.box(x0, y0 + jolt, x1, y1 + jolt), fill=SHELFC)
        for bx in (x0 + 30, x1 - 30):
            dr.polygon(V.pts([(bx - 6, y1 + jolt), (bx + 6, y1 + jolt), (bx + 6, y1 + 34), (bx - 6, y1 + 18)]), fill=mix(SHELFC, WALL, 0.4))
        fx, fy, fa = A.flask(T)
        if T < A.flask_tin:
            self.draw_flask(dr, V, fx, fy + (jolt if T < tS + 0.05 else 0), fa)

    def draw_flask(self, dr, V, x, y, a):
        dr.polygon(V.pts(flask_poly(x, y, a)), fill=FLASKC)
        cap = rot([(-5, -FLASK_H / 2 - 10), (5, -FLASK_H / 2 - 10), (5, -FLASK_H / 2), (-5, -FLASK_H / 2)], x, y, a)
        dr.polygon(V.pts(cap), fill=(70, 80, 96))
        hl = rot([(-9, -12), (-4, -12), (-4, 26), (-9, 26)], x, y, a)
        dr.polygon(V.pts(hl), fill=mix(FLASKC, (255, 255, 255), 0.35))

    def draw_toilet(self, dr, V, T):
        A = self.a
        rrect(dr, V, 870, 1180, 906, 1214, 4, (60, 66, 80))      # la plaque de chasse, au mur
        body = [(842, 1350), (934, 1350), (918, 1440), (902, 1540), (874, 1540), (858, 1440)]
        dr.polygon(V.pts(body), fill=TUBC)
        dr.polygon(V.pts([(858, 1440), (918, 1440), (902, 1540), (874, 1540)]), fill=mix(TUBC, (0, 0, 0), 0.12))
        rrect(dr, V, *TOILET_SEAT, 6, mix(TUBC, (255, 255, 255), 0.2))
        u = A.lid(T)
        # l'abattant : relevé (debout contre le mur), il se rabat vers nous
        top = LID_UP[1] + (LID_DOWN[1] - LID_UP[1]) * u
        x0 = LID_UP[0] + (LID_DOWN[0] - LID_UP[0]) * u
        x1 = LID_UP[2] + (LID_DOWN[2] - LID_UP[2]) * u
        rrect(dr, V, x0, top, x1, LID_DOWN[3], 14 - 6 * u, mix(TUBC, (255, 255, 255), 0.35))
        rrect(dr, V, x0 + 6, top + 6, x1 - 6, LID_DOWN[3] - 4, 10 - 6 * u, mix(TUBC, (0, 0, 0), 0.06))

    def draw_puddles(self, dr, V, T):
        p = self.p
        vol = {"L": 0.0, "R": 0.0}
        flows = []
        for (t0, side, v, d) in p.spills:
            u = lin((T - t0) / d)
            vol[side] += v * u
            if 0 <= T - t0 < d + 0.5:
                flows.append((t0, side, v, d))
        # les flaques
        if vol["L"] > 0:
            w = min(260.0, 60 + 34 * vol["L"])
            th = min(14.0, 3 + 1.4 * vol["L"])
            cx = TUB_X0 - w * 0.42
            dr.ellipse(V.box(cx - w / 2 - 20, FLOOR - th * 0.5, TUB_X0 + 10, FLOOR + th * 1.6), fill=mix(FLOORC, WATER, 0.8))
            dr.ellipse(V.box(cx - w * 0.3, FLOOR, cx + w * 0.1, FLOOR + 4), fill=mix(WATER, (200, 230, 240), 0.5))
        if vol["R"] > 0:
            w = min(130.0, 40 + 26 * vol["R"])
            th = min(12.0, 3 + 1.4 * vol["R"])
            dr.ellipse(V.box(TUB_X1 - 10, FLOOR - th * 0.5, TUB_X1 + w, FLOOR + th * 1.6), fill=mix(FLOORC, WATER, 0.8))
        self._flows = flows

    def draw_tub(self, dr, V, T, b, img):
        p, A = self.p, self.a
        # l'intérieur, la ligne de mousse du niveau de départ
        rrect(dr, V, IX0, RIM_Y, IX1, IB, 26, TUB_IN)
        for k in range(int((IX1 - IX0) / 16)):
            xx = IX0 + 10 + k * 16
            r = 5 + 3 * ((k * 7) % 3)
            dr.ellipse(V.box(xx - r, FOAM_Y - r * 0.7, xx + r, FOAM_Y + r * 0.7), fill=mix(TUB_IN, FOAMC, 0.75))
        # la bonde, sa chaînette
        dr.ellipse(V.box(DRAIN_X - 18, IB - 6, DRAIN_X + 18, IB + 4), fill=(40, 44, 54))
        px, py, pa = A.plug(T)
        ax, ay = IX1 - 6, RIM_Y + 20
        n = 14
        mx_, my_ = (ax + px) / 2 + 10, max(ay, py) - 10 + 30
        pts = []
        for k in range(n + 1):
            u = k / n
            xx = (1 - u) ** 2 * ax + 2 * (1 - u) * u * mx_ + u * u * px
            yy = (1 - u) ** 2 * ay + 2 * (1 - u) * u * my_ + u * u * (py - 6)
            pts.append((xx, yy))
        for (xx, yy) in pts:
            dr.ellipse(V.box(xx - 3, yy - 3, xx + 3, yy + 3), fill=CHAIN)
        dr.polygon(V.pts(rot([(-20, -6), (20, -6), (16, 6), (-16, 6)], px, py, pa)), fill=(46, 48, 58))
        # le flacon coulé
        fx, fy, fa = A.flask(T)
        if T >= A.flask_tin:
            self.draw_flask(dr, V, fx, fy, fa)
        # Bounce sous l'eau
        if not b["hidden"] and b["water"]:
            self.draw_bounce(dr, V, b, T)
        # Float et le canard
        x, y, a = A.float_state(T)
        expr, look, mouth, nod, foam = self.float_face(T, x, y, b)
        draw_float(dr, V, x, y, a, EXPR[expr], look, mouth, nod, foam)
        # l'eau, translucide
        L = p.level(T)
        xs = np.linspace(IX0, IX1, 46)
        top = [min(p.surface(float(xx), T), self.bottom_y(float(xx))) for xx in xs]
        bot = [self.bottom_y(float(xx)) for xx in xs]
        poly = [(float(xx), float(yy)) for xx, yy in zip(xs, top)] + [(float(xx), float(yy)) for xx, yy in zip(xs[::-1], bot[::-1])]
        self.water_fill(img, V, poly)
        # la mousse sur l'eau
        foam_amt = max(0.15, 1.0 - (L - FOAM_Y) / 140.0)
        dkx, _ = A.duck_xy(T)
        for k, (u, v, s) in enumerate(self.foam_seed):
            xx = IX0 + 14 + u * (IX1 - IX0 - 28)
            if abs(xx - x) < RF * 0.8 or abs(xx - dkx) < DUCK_HW + 6 or v > foam_amt:
                continue
            yy = p.surface(xx, T) - 4 - v * 18 * foam_amt
            rr = (7 + 9 * s) * (0.6 + 0.4 * foam_amt)
            dr.ellipse(V.box(xx - rr, yy - rr * 0.8, xx + rr, yy + rr * 0.8), fill=FOAMC if k % 3 else FOAM_SH)
        self.draw_duck(dr, V, T)
        # le tourbillon
        w = p.whirl(T)
        if w > 0.02:
            sy = p.surface(DRAIN_X, T)
            for k in range(4):
                ph = T * (6 + 6 * w) + k * math.pi / 2
                rx = 18 + 12 * k
                ry = 5 + 2 * k
                cyy = sy + 6 + k * 7
                a0 = math.degrees(ph) % 360
                dr.arc(V.box(DRAIN_X - rx, cyy - ry, DRAIN_X + rx, cyy + ry), a0, a0 + 200, fill=mix(WATER, (255, 255, 255), 0.55), width=max(1, int(V.L(3))))
            dr.line([(V.X(DRAIN_X), V.Y(sy + 30)), (V.X(DRAIN_X), V.Y(IB - 8))], fill=mix(WATER, (255, 255, 255), 0.35), width=max(1, int(V.L(4 * w))))
        # les parois et le rebord (par-dessus l'eau)
        wall_c = TUBC
        dr.rectangle(V.box(TUB_X0, RIM_Y + 10, IX0, TUB_BOT - 10), fill=wall_c)
        dr.rectangle(V.box(IX1, RIM_Y + 10, TUB_X1, TUB_BOT - 10), fill=wall_c)
        rrect(dr, V, TUB_X0, IB, TUB_X1, TUB_BOT, 16, wall_c)
        dr.rectangle(V.box(IX0 + 20, IB, IX1 - 20, IB + 4), fill=TUB_SH)
        rrect(dr, V, *LIP_L, 8, mix(TUBC, (255, 255, 255), 0.4))
        rrect(dr, V, *LIP_R, 8, mix(TUBC, (255, 255, 255), 0.4))
        for fx_ in (TUB_X0 + 40, TUB_X1 - 40):
            dr.ellipse(V.box(fx_ - 18, TUB_BOT - 4, fx_ + 18, FLOOR + 2), fill=(170, 150, 90))
        # l'eau qui passe par-dessus le bord
        for (t0, side, v, d) in self._flows:
            tt = T - t0
            k = math.sin(math.pi * lin(tt / (d + 0.5)))
            if k <= 0:
                continue
            wd = (6 + 5 * v) * k
            if side == "L":
                xa = LIP_L[0]
                pts = [(LIP_L[2], RIM_Y - 3), (xa - 4, RIM_Y - 3 - wd * 0.3), (xa - 6 - wd * 0.5, RIM_Y + 30), (TUB_X0 - wd * 0.4, FLOOR - 4), (TUB_X0 + 2, FLOOR - 4), (TUB_X0 + 2, RIM_Y + 20)]
            else:
                xa = LIP_R[2]
                pts = [(LIP_R[0], RIM_Y - 3), (xa + 4, RIM_Y - 3 - wd * 0.3), (xa + 6 + wd * 0.5, RIM_Y + 30), (TUB_X1 + wd * 0.4, FLOOR - 4), (TUB_X1 - 2, FLOOR - 4), (TUB_X1 - 2, RIM_Y + 20)]
            dr.polygon(V.pts(pts), fill=mix(WATER, (210, 235, 245), 0.25))
            fx_ = (LIP_L[0] - 4) if side == "L" else (LIP_R[2] + 4)
            for j in range(3):
                yy = RIM_Y - 2 + j * 10
                rr = 6 * k + 2
                dr.ellipse(V.box(fx_ - rr, yy - rr, fx_ + rr, yy + rr), fill=FOAMC)

    def bottom_y(self, x):
        r = 26.0
        if x < IX0 + r:
            d = IX0 + r - x
            return IB - r + math.sqrt(max(0.0, r * r - d * d))
        if x > IX1 - r:
            d = x - (IX1 - r)
            return IB - r + math.sqrt(max(0.0, r * r - d * d))
        return IB

    def water_fill(self, img, V, poly):
        from PIL import Image, ImageDraw
        pts = V.pts(poly)
        x0 = int(max(0, math.floor(min(p[0] for p in pts))))
        y0 = int(max(0, math.floor(min(p[1] for p in pts))))
        x1 = int(min(img.size[0], math.ceil(max(p[0] for p in pts)) + 1))
        y1 = int(min(img.size[1], math.ceil(max(p[1] for p in pts)) + 1))
        if x1 <= x0 or y1 <= y0:
            return
        mask = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(mask).polygon([(px - x0, py - y0) for px, py in pts], fill=int(255 * WATER_A))
        img.paste(WATER, (x0, y0, x1, y1), mask)
        # la ligne de surface, plus claire
        d2 = ImageDraw.Draw(img)
        n = len(poly) // 2
        d2.line(pts[:n], fill=mix(WATER, (235, 248, 255), 0.55), width=max(1, int(V.L(4))))

    def draw_duck(self, dr, V, T):
        A = self.a
        x, y, a = *A.duck_xy(T), A.duck_angle(T)
        body = [(-DUCK_HW, -4), (-DUCK_HW + 6, 12), (DUCK_HW - 4, 14), (DUCK_HW, 0), (DUCK_HW - 10, -10), (-DUCK_HW + 8, -10)]
        dr.polygon(V.pts(rot(body, x, y, a)), fill=DUCKC)
        hx, hy = rot([(DUCK_HW * 0.45, -DUCK_HH * 0.85)], x, y, a)[0]
        dr.ellipse(V.box(hx - 12, hy - 12, hx + 12, hy + 12), fill=DUCKC)
        bk = rot([(DUCK_HW * 0.45 + 10, -DUCK_HH * 0.85 - 2), (DUCK_HW * 0.45 + 22, -DUCK_HH * 0.85 + 2), (DUCK_HW * 0.45 + 10, -DUCK_HH * 0.85 + 6)], x, y, a)
        dr.polygon(V.pts(bk), fill=BEAK)
        ex, ey = rot([(DUCK_HW * 0.45 + 4, -DUCK_HH * 0.85 - 4)], x, y, a)[0]
        dr.ellipse(V.box(ex - 2.5, ey - 2.5, ex + 2.5, ey + 2.5), fill=INK)

    def draw_drops(self, dr, V, T):
        p = self.p
        for (t0, x0, y0, vx, vy, r, fo) in self.drops:
            tt = T - t0
            if tt < 0 or tt > 1.6:
                continue
            x = x0 + vx * tt
            y = y0 + vy * tt + 0.5 * G * tt * tt
            if vy * 1 + G * tt > 0:  # en descente : s'arrête à l'eau ou au sol
                if IX0 < x < IX1 and y > p.surface(x, T) and tt > 0.05:
                    continue
                if y > FLOOR + 4:
                    continue
            if IX0 - 4 < x < IX1 + 4 and RIM_Y < y < IB and not (y < p.surface(x, T)):
                continue
            col = FOAMC if fo else mix(WATER, (220, 240, 250), 0.35)
            dr.ellipse(V.box(x - r, y - r, x + r, y + r), fill=col)

    def draw_bounce(self, dr, V, b, T):
        hc = base.HERO["color"]
        s = b["scale"]
        rx, ry = RB * b["sx"] * s, RB * b["sy"] * s
        x, y = b["x"], b["y"]
        if not b["water"] and not b["behind"]:
            dr.ellipse(V.box(x - rx * 1.35, y - ry * 1.35, x + rx * 1.35, y + ry * 1.35), fill=mix(WALL, hc, 0.16))
        col = hc if not b["behind"] else mix(hc, CORRIDOR, 0.25 * (1 - s) / 0.3)
        dr.ellipse(V.box(x - rx, y - ry, x + rx, y + ry), fill=col)
        gx, gy = self.p.gaze_at(T)
        r = RB * min(b["sx"], b["sy"]) * s
        base.hero_face(dr, V.X(x + gx * 0.22 * r), V.Y(y + gy * 0.22 * r), V.L(r))
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (V.X(x), V.Y(y))

    # -- Float : expression, regard, bouche
    def float_face(self, T, fx, fy, b):
        p = self.p
        m = p.mark
        bx, by = b["x"], b["y"]
        tgt = (bx, by)
        if T < m["F1"] - 0.5:
            e = "serene"
        elif T < m["F2"] - 0.35:
            e = "slit"
        elif T < p.t_plouf + 0.4:
            e = "squint"
        elif T < m["F3"] - 0.35:
            e = "squint_flat"
        elif T < p.t_bot:
            e = "wide"
        elif T < p.t_bot + 2.6:
            e = "wide_o"
        elif T < p.t_whirl:
            e = "squint_flat"
        elif T < m["p8"] + 0.25:
            e = "wide_flat"
        elif T < m["seuil"] - 0.8:
            e = "glacial"
        elif T < m["eye_open"]:
            e = "calm"
        elif T < p.t_close1:
            e = "slit"
        elif T < p.t_smile:
            e = "calm"
        elif T < p.t_eye_last:
            e = "serene"
        else:
            e = "slit_door"
        # le regard
        if m["door_look"] <= T < m["door_look"] + 1.5 and e == "glacial":
            u = T - m["door_look"]
            k = ease(u / 0.6) if u < 0.75 else 1 - ease((u - 0.75) / 0.6)
            tgt = (tgt[0] + (DOOR_CX - tgt[0]) * k, tgt[1] + (1330 - tgt[1]) * k)
        if e == "slit_door" or (T >= p.t_exit1):
            tgt = (DOOR_CX, 1330.0)
        if b["hidden"] and T < p.t_exit1:
            tgt = (DOOR_CX, 1300.0)
        dx, dy = tgt[0] - fx, tgt[1] - fy
        d = math.hypot(dx, dy) or 1.0
        look = (dx / d, dy / d)
        if e in ("wide", "wide_o", "wide_flat") and T >= p.t_whirl and T < m["p8"]:
            look = (math.sin(T * 9.0), 0.4)    # elle tourne : les yeux s'affolent
        # la bouche suit l'enveloppe de sa réplique
        mouth = 0.0
        for ln in p.lines:
            if ln["start"] <= T < ln["end"]:
                env = ENV.get(ln["text"])
                if env is not None and len(env):
                    i = int((T - ln["start"]) * 60)
                    mouth = float(env[min(i, len(env) - 1)])
        nod = 0.0
        if m["F3"] <= T < m["F3"] + 1.0:
            nod = 0.05 * math.sin(2 * math.pi * (T - m["F3"]) / 0.5)
        foam = 0.0
        g = m["gerbe"] + 0.5
        if T >= g:
            foam = min(1.0, (T - g) / 0.2)
            drip0 = p.t_bot + 1.6
            if T > drip0:
                foam *= max(0.0, 1 - (T - drip0) / 2.4)
        # la tête disparaît sous la mousse : un gros paquet de mousse sur elle
        return e, look, mouth, nod, foam


# ------------------------------------------------------------------ le chapitre unique
PLAN = {}


class Bath(Chapter):
    """Toute la vidéo est un seul chapitre ; sa « chute », au sens du contrôle, est le premier
    gag (l'abattant qui se rabat), avant 6 s."""
    title = None
    mood = "lose"
    exit_ok = False
    bodies_exit_ok = False

    def setup(self):
        p, a, sc = PLAN["p"], PLAN["a"], PLAN["s"]
        self.P, self.A, self.Sc = p, a, sc
        self.chute = p.mark["lid"]
        self.hold_s = p.end - self.chute
        self.lines = [(l["start"], l["text"], l["key"]) for l in p.lines]
        self.R = RB
        self.prevT = None
        self.bx, self.by, self.on = DOOR_CX, 1360.0, "air"

    def step(self, dt):
        self.t += dt
        T = self.t
        evs = []
        lo = self.prevT if self.prevT is not None else T - dt
        for c in self.P.contacts:
            if lo < c["t"] <= T:
                evs.append(("hit", "floor"))
        self.prevT = T
        if T >= self.chute - 1e-9:
            self.finish("LID")
        return evs

    def snapshot(self):
        return {"T": self.t, "t": self.t, "end": self.end_t, "on": "air"}

    def hero(self, s):
        b = self.P.bounce(s["T"])
        if b["hidden"] or b["behind"]:
            return None
        return (b["x"], b["y"], RB * min(b["sx"], b["sy"]) * b["scale"])

    def solids(self, s):
        T = s["T"]
        A = self.A
        out = [("rect", -50.0, FLOOR, W + 50.0, H + 50.0),
               ("rect", *LIP_L), ("rect", *LIP_R),
               ("rect", TUB_X0, LIP_L[3], IX0, TUB_BOT), ("rect", IX1, LIP_R[3], TUB_X1, TUB_BOT),
               ("rect", TUB_X0, IB, TUB_X1, TUB_BOT),
               ("rect", *SINK), ("rect", *PED), ("rect", *SHELF),
               ("rect", *TOILET_SEAT), ("poly", [(842, 1350), (934, 1350), (902, 1540), (874, 1540)])]
        u = A.lid(T)
        top = LID_UP[1] + (LID_DOWN[1] - LID_UP[1]) * u
        x0 = LID_UP[0] + (LID_DOWN[0] - LID_UP[0]) * u
        x1 = LID_UP[2] + (LID_DOWN[2] - LID_UP[2]) * u
        out.append(("rect", x0, top, x1, LID_DOWN[3]))
        fx, fy, fa = A.float_state(T)
        out.append(("circle", fx, fy, RF))
        dx, dy = A.duck_xy(T)
        out.append(("poly", duck_poly(dx, dy, A.duck_angle(T))))
        out.append(("poly", flask_poly(*A.flask(T))))
        return out

    def focus(self, s):
        return (IX0, 1000.0, IX1, IB + 20)

    def bodies(self, s):
        T = s["T"]
        A = self.A
        fx, fy, fa = A.float_state(T)
        dx, dy = A.duck_xy(T)
        da = A.duck_angle(T)
        kx, ky, ka = A.flask(T)
        px, py, pa = A.plug(T)
        return [("float", fx, fy, fa, float_poly(fx, fy)),
                ("duck", dx, dy, da, duck_poly(dx, dy, da)),
                ("flask", kx, ky, ka, flask_poly(kx, ky, ka)),
                ("plug", px, py, pa)]

    def draw(self, dr, s, t, S):
        self.Sc.draw(dr, s["T"], S)


CHAPTERS = [(Bath, {})]

DEFAULTS = {
    "ball_r": RB, "gravity": G,
    "hook_text_s": 2.9, "hook_top": 0.07, "hook_font_size": 92,
    "watermark_y": 0.95, "end_hold_s": 0.05, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
    "scene_top": 0.215, "min_duration_s": 30.0, "chapter_max_s": 500.0,
    "float_gain": 1.0, "muffled_gain": 0.42, "muffled_hz": 520.0, "small_gain": 0.55,
}


def lowpass(x, fc):
    n = len(x)
    X = np.fft.rfft(np.concatenate([x, np.zeros(2048)]))
    f = np.fft.rfftfreq(n + 2048, 1 / SR)
    X *= 1.0 / np.sqrt(1.0 + (f / fc) ** 4)
    y = np.fft.irfft(X)[:n + 2048]
    return y


def float_render_audio(events, total_dur, cfg, path, payoff_t=None, mood=None, narr=(), replies=()):
    """Le mixage : le placement des mots est celui du moteur (place_words, que le contrôle
    relit) ; chaque « Bounce » prend le traitement de son contact (sous l'eau et derrière la
    porte : passe-bas et moins fort ; sur le seuil : plus petit). La voix de Float vient de
    sa banque. Aucun autre son."""
    p = PLAN["p"]
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    stats = {"hero": cfg["hero_name"], "said": 0, "muffled": 0, "small": 0, "reaction": mood, "contacts": 0}
    stats["contacts"] = sum(1 for (t, k, d) in events if k == "hit")
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        react = base.hero_word(cfg["hero_lose"], cfg) if mood == "lose" else None
        words = base.place_words(events, total_dur, cfg, payoff_t, mood if react is not None else None, narr, replies,
                                 name_len=len(name) / SR, react_len=(len(react) / SR if react is not None else 0.8))
        muff = lowpass(name, cfg["muffled_hz"])
        for (t0, kind, _d, tag) in words:
            if kind == "react":
                ak.add(buf, react, t0, gain=1.0)
                continue
            c = min(p.contacts, key=lambda c: abs(c["t"] - t0))
            v = c["voice"]
            if v == "m":
                ak.add(buf, muff, t0, gain=cfg["muffled_gain"] * 1.2)
                stats["muffled"] += 1
            elif v == "s":
                ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.02, 0.02)), t0, gain=cfg["hero_gain"] * cfg["small_gain"])
                stats["small"] += 1
            else:
                ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=cfg["hero_gain"])
            stats["said"] += 1
        stats["words"] = [round(w[0], 2) for w in words]
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=cfg["float_gain"])
    v = cfg.get("_hook_voice")
    if v is None:
        v = base.hook_audio(cfg)
    if v is not None:
        n = min(len(v), len(buf))
        duck = np.ones(len(buf))
        duck[:n] = 0.42
        duck[n:n + int(0.3 * SR)] = np.linspace(0.42, 1.0, min(int(0.3 * SR), len(buf) - n))
        buf *= duck
        ak.add(buf, v, 0.15, gain=1.0)
    ak.write_wav(buf, path, peak=0.7)
    print(f"[{cfg['name']}] voix : {stats}", file=sys.stderr)
    return stats


base.render_audio = float_render_audio


class Sim(StorySim):
    def __init__(self, cfg, rng):
        load_bank(cfg)
        apply_controle(cfg)
        hv = base.hook_audio(cfg)
        hook_end = 0.15 + (len(hv) / SR if hv is not None else 2.0)
        durs = {k: len(v) / SR for k, v in BANK.items()}
        PLAN.clear()
        p = Plan(cfg, durs, hook_end)
        a = Actors(p)
        PLAN["p"], PLAN["a"] = p, a
        PLAN["s"] = Scene(p, a)
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)
        self.plan = p

    def step(self, dt):
        evs = super().step(dt)
        if not self.payoff and self.t >= self.plan.t_payoff:
            self.payoff = True        # la réaction de Bounce (« Oh no. ») ; la scène continue
        if self.t >= self.plan.end and not self.done:
            self.done = True
            evs = list(evs) + [("payoff", "END")]
        return evs

    def draw(self, dr, snap, t, S):
        s = self.sims[snap["i"]]
        s.draw(dr, snap["snap"], snap["tl"], S)

    def hero_mood(self):
        return "lose"


def apply_controle(cfg):
    """Une règle du contrôle des listes qui ne s'applique pas à ce format est relevée par
    la config (cfg["controle"] = {"seuils": {...}, "pourquoi": {...}}), seulement quand le
    contrôle tourne, et chaque relèvement est affiché avec sa raison."""
    import __main__
    ctl = cfg.get("controle") or {}
    S = getattr(__main__, "SEUILS", None)
    if not isinstance(S, dict) or not ctl.get("seuils"):
        return
    for k, v in ctl["seuils"].items():
        if k in S and S[k] != v:
            print(f"[floatbath] contrôle : {k} {S[k]} -> {v} ({ctl.get('pourquoi', {}).get(k, '')})", file=sys.stderr)
            S[k] = v


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
