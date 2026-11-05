"""
Prototype « cinéma » : une salle de cinéma dans le noir, vue de dos. Bounce rebondit sur le
dossier de son siège au milieu de la salle et dit son nom à chaque contact dur. Les « Shh! »
montent ; l'ouvreur allume sa lampe et expulse quiconque est dans son faisceau (« éclairé =
coupable ») : le faisceau arrive toujours trop tard sur Bounce et tombe sur ceux qui le font
taire. La salle se vide. Bounce finit par envoyer la lampe en l'air ; elle retombe braquée sur
l'écran, et l'ouvreur, fidèle à sa règle, expulse… le personnage du film, qui sort par sa porte
et fait « Shh! » à Bounce.

Tout est calculé d'avance sur une horloge : les contacts de Bounce (arcs paraboliques exacts
sous G = 2600 entre deux contacts), les poses des spectateurs (clés), le faisceau (clés).
Les répliques (spectateurs, ouvreur, film) viennent d'une banque de voix hors dépôt
(cfg["voice_bank"]), passée au moteur comme répliques du narrateur ; aucun sous-titre du
moteur : chaque réplique est dessinée dans une bulle.

    python3 src/stories/cinema.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import font
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice
from PIL import Image, ImageDraw

SR = ak.SR

# ------------------------------------------------------------------ la banque de voix
LINE_FILES = {
    "SHH_B3": "shh_b3.wav", "SHH_2": "shh_2.wav", "SHH_4": "shh_4.wav", "SHH_ALL": "shh_all.wav",
    "OUT_YOU": "out_you.wav", "SHH_2B": "shh_2b.wav", "OUT_TWO": "out_two.wav", "SHH_USHER": "shh_usher.wav",
    "OUT_ALL": "out_all.wav", "OUT_YOU2": "out_you2.wav", "NOW": "now.wav", "OUT_FILM": "out_film.wav",
    "SHH_FILM": "shh_film.wav",
}
BUBBLE = {
    "SHH_B3": "shh", "SHH_2": "SHH!", "SHH_4": "SHH!", "SHH_ALL": "SHHHH!", "OUT_YOU": "YOU. OUT.",
    "SHH_2B": "SHH!", "OUT_TWO": "YOU TWO. OUT.", "SHH_USHER": "SHHHH!", "OUT_ALL": "EVERYONE. OUT.",
    "OUT_YOU2": "YOU. OUT.", "NOW": "NOW.", "OUT_FILM": "YOU. OUT.", "SHH_FILM": "shh.",
}
BANK = {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    return x


def load_bank(cfg):
    path = cfg.get("voice_bank")
    if not path:
        raise SystemExit("voice_bank manquant dans la config")
    gains = cfg.get("line_gains", {})
    for key, fn in LINE_FILES.items():
        x = _read(os.path.join(path, fn))
        x = x / (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9) * 0.2
        BANK[key] = x * gains.get(key, 1.0)


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say
base.subtitle_at = lambda narr, t, n_words: None          # les répliques sont dans des bulles
_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    if not text:
        return None                                        # pas de mot de réaction : le visage suffit
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(12):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
R = 90.0
SCREEN = (160.0, 450.0, 980.0, 880.0)
SW, SH = SCREEN[2] - SCREEN[0], SCREEN[3] - SCREEN[1]
DOOR = (22.0, 800.0, 140.0, 1065.0)
AISLE_X = 112.0
DOOR_YB = 1028.0                 # « dossier » de référence d'un marcheur arrivé à la porte
ROW_Y = {"A": 1075.0, "B": 1245.0, "C": 1415.0, "D": 1585.0}
ROW_ORDER = "ABCD"
SEATS = [285.0, 470.0, 665.0, 850.0]
HOME = (672.0, ROW_Y["C"] - R)
JK = (805.0, 1300.0)             # Bounce posé sur la doudoune
POT_X, POT_TOP = 378.0, 1305.0
POT = (POT_X, POT_TOP - R + 0.0)
B3 = (665.0, ROW_Y["B"] - R)
D3 = (665.0, ROW_Y["D"] - R)
D4 = (838.0, ROW_Y["D"] - R)

BG = (8, 8, 12)
WALL = (16, 14, 22)
SEAT_COL = (74, 22, 36)
SEAT_EDGE = (112, 40, 58)
RIM = (150, 165, 205)
BEAM = (255, 226, 150)
USHER_COL = (122, 28, 40)
GOLD = (220, 175, 70)
FILM_BG = (92, 106, 136)
FILM_FLOOR = (64, 74, 100)
INKF = (12, 12, 18)
POP = (250, 236, 178)


def lerp(a, b, s):
    return a + (b - a) * s


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def row_scale(yb):
    return 0.80 + (yb - ROW_Y["A"]) / (ROW_Y["D"] - ROW_Y["A"]) * 0.26


def keyval(keys, t):
    """Clés [(t, v)] : interpolation douce entre deux clés, tenue avant et après."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            if t1 - t0 < 1e-9:
                return v1
            return lerp(v0, v1, smooth((t - t0) / (t1 - t0)))
    return keys[-1][1]


def keylin(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            if t1 - t0 < 1e-9:
                return v1
            return lerp(v0, v1, (t - t0) / (t1 - t0))
    return keys[-1][1]


# ------------------------------------------------------------------ le plan de Bounce
# (t d'arrivée, x, y, dur ?, durée du contact mou, enfoncement)
def contacts():
    C = []

    def h(t, p, dx=0.0):
        C.append((t, p[0] + dx, p[1], True, 0.0, 0.0))

    def s(t, p, dur=0.12, depth=34.0, dx=0.0):
        C.append((t, p[0] + dx, p[1], False, dur, depth))
    C.append((-0.62, HOME[0], HOME[1], False, 0.0, 0.0))      # virtuel : l'arc de la première image
    s(0.70, JK)
    h(2.12, HOME); h(3.52, HOME, -14); h(4.45, HOME, 10)
    s(5.55, POT, 0.14, 30)
    h(6.85, HOME); s(7.95, JK)
    h(9.10, HOME, 12); h(10.05, HOME, -10)
    s(11.35, JK)
    h(12.60, HOME); h(13.55, HOME, 8)
    s(14.75, JK)
    h(15.95, HOME, -8); h(17.05, HOME, 10); h(18.20, HOME, -12); h(19.10, HOME, 6)
    h(20.00, B3); h(21.45, B3, 12)
    s(22.35, JK, 1.05, 150)                                   # elle disparaît dans la doudoune
    h(24.60, HOME); h(25.65, HOME, -10); h(26.75, HOME, 8)
    s(27.95, JK)
    h(29.00, HOME); s(30.20, JK)
    h(31.40, HOME); h(32.30, HOME, -10)
    h(33.45, B3); h(34.35, B3, -10)
    h(35.25, HOME)
    s(36.40, POT, 0.14, 30)
    h(37.60, D3); h(38.60, D4)
    h(39.55, HOME); h(40.50, HOME, 10)
    s(41.65, POT, 0.14, 26)
    h(42.75, HOME); h(43.70, HOME, -8)
    h(44.65, B3)
    h(46.17, HOME); h(47.05, HOME, 8); h(47.95, HOME, -6)
    h(49.05, HOME); h(49.92, HOME, 4); h(50.78, HOME, -4)
    s(51.65, JK, 0.10, 40)
    C.append((52.00, 790.0, 1190.0, True, 0.0, 0.0))          # la lampe, frappée par en dessous
    s(52.35, JK, 0.10, 34)
    h(53.75, HOME)
    s(54.95, JK)
    h(56.25, HOME); h(57.25, HOME, 8); h(58.10, HOME, -6); h(58.95, HOME)
    s(60.25, JK)
    h(61.70, HOME)
    C.append((63.15, HOME[0], HOME[1], False, 0.0, 0.0))      # virtuel : la dernière image en l'air
    return C


T_LAMP = 52.00
T_LAMP_LAND = 53.15
LAMP_LAND = (300.0, ROW_Y["A"] - 16.0)
T_LIGHT_ON = 12.9
T_PAYOFF = 60.30
T_END = 62.75


class Sim:
    scene_top = 0.195

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.C = contacts()
        self.hits = [c[0] for c in self.C if c[3] and c[0] > 0]
        self.hi = 0
        self.check_arcs()
        self.lines = [(3.04, "SHH_B3", "SHH_B3"), (5.39, "SHH_2", "SHH_2"), (7.77, "SHH_4", "SHH_4"),
                      (10.97, "SHH_ALL", "SHH_ALL"), (14.47, "OUT_YOU", "OUT_YOU"), (20.92, "SHH_2B", "SHH_2B"),
                      (23.32, "OUT_TWO", "OUT_TWO"), (27.67, "SHH_USHER", "SHH_USHER"),
                      (29.92, "OUT_ALL", "OUT_ALL"), (41.42, "OUT_YOU2", "OUT_YOU2"), (45.57, "NOW", "NOW"),
                      (54.77, "OUT_FILM", "OUT_FILM"), (59.87, "SHH_FILM", "SHH_FILM")]
        self.build_people()
        self.build_popcorn(rng)
        self.dust = [(float(rng.uniform(0, W)), float(rng.uniform(40, 440)), float(rng.uniform(0, 6.28)),
                      float(rng.uniform(1.5, 3.5))) for _ in range(40)]

    # ------------------------------------------------------------------ Bounce
    def check_arcs(self):
        C = self.C
        self.arcs = []
        for a, b in zip(C, C[1:]):
            t0 = a[0] + a[4]
            T = b[0] - t0
            x0, y0, x1, y1 = a[1], a[2], b[1], b[2]
            vy0 = (y1 - y0 - 0.5 * G * T * T) / T
            top = y0 - (vy0 * vy0 / (2 * G) if vy0 < 0 else 0)
            hgt = max(y0, y1) - top
            if hgt > 700.5 + max(0, abs(y1 - y0)) and a[0] > 0:
                print(f"[cinema] arc {a[0]:.2f}->{b[0]:.2f} trop haut ({hgt:.0f} px)", file=sys.stderr)
            if min(y0, y1) - top > 700.5 and a[0] > 0:
                print(f"[cinema] arc {a[0]:.2f}->{b[0]:.2f} : {min(y0, y1) - top:.0f} px au-dessus du plus haut appui", file=sys.stderr)
            self.arcs.append((t0, b[0], x0, y0, x1, y1, vy0))

    def bounce_at(self, t):
        """(x, y, appui) ; appui = (rangée de profondeur, quoi, enfoncement)"""
        C = self.C
        for c in C:
            if c[0] <= t <= c[0] + c[4] and c[4] > 0:
                u = (t - c[0]) / c[4]
                d = c[5] * math.sin(math.pi * u) if c[5] < 100 else c[5] * math.sin(math.pi * u) ** 0.35
                return c[1], c[2] + d, self.support_of(c), d
        for (t0, t1, x0, y0, x1, y1, vy0) in self.arcs:
            if t0 <= t <= t1:
                dt = t - t0
                x = lerp(x0, x1, dt / (t1 - t0))
                y = y0 + vy0 * dt + 0.5 * G * dt * dt
                nxt = next(c for c in C if abs(c[0] - t1) < 1e-9)
                return x, y, self.support_of(nxt), 0.0
        c = C[-1]
        return c[1], c[2], "C", 0.0

    def support_of(self, c):
        y = c[2]
        if abs(y - B3[1]) < 2:
            return "B"
        if abs(y - D3[1]) < 2:
            return "D"
        return "C"

    def in_jacket(self, t):
        for c in self.C:
            if not c[3] and abs(c[1] - JK[0]) < 1 and c[0] <= t <= c[0] + c[4]:
                return (t - c[0]) / c[4], c[5]
        return None

    def in_pot(self, t):
        for c in self.C:
            if not c[3] and abs(c[1] - POT[0]) < 1 and c[0] - 0.02 <= t <= c[0] + c[4] + 0.05:
                return clamp01((t - c[0]) / max(c[4], 1e-3)), c[5]
        return None

    # ------------------------------------------------------------------ les spectateurs
    def build_people(self):
        cols = {"A1": (176, 142, 70), "A2": (84, 112, 176), "A3": (138, 94, 172), "A4": (86, 146, 104),
                "B1": (184, 106, 64), "B2": (58, 146, 150), "B3": (70, 104, 196), "B4": (156, 82, 126),
                "C1": (130, 136, 72), "C2": (74, 160, 92),
                "D1": (102, 112, 148), "D2": (152, 112, 82), "D3": (200, 116, 52), "D4": (164, 146, 112)}
        shapes = {"A1": "bun", "B1": "cap", "D2": "tall", "A4": "small", "B4": "tail", "C1": "cap", "D4": "bun",
                  "A2": "tall"}
        P = {}
        for row in "ABCD":
            for i, x in enumerate(SEATS):
                pid = f"{row}{i + 1}"
                if row == "C" and i >= 2:
                    continue
                P[pid] = {"id": pid, "row": row, "x0": x, "col": cols[pid], "shape": shapes.get(pid, "round"),
                          "stand": [(0.0, 0.0)], "gest": [], "path": None, "gone": 99.0}
        self.P = P

        def up(pid, t, v=1.0):
            P[pid]["stand"].append((t, P[pid]["stand"][-1][1]))
            P[pid]["stand"].append((t + 0.22, v))

        def down(pid, t, d=0.12):
            P[pid]["stand"].append((t, P[pid]["stand"][-1][1]))
            P[pid]["stand"].append((t + d, 0.0))

        def gest(pid, t0, t1, kind, target=None):
            P[pid]["gest"].append((t0, t1, kind, target))
        bounce = lambda t: self.bounce_at(t)[:2]
        usher_head = lambda t: self.usher_at(t)["head"]
        # 1. les « Shh! »
        up("B3", 3.04); gest("B3", 3.04, 14.75, "shh", bounce)
        for pid in ("A3", "D3"):
            up(pid, 5.39); gest(pid, 5.39, 12.9, "shh", bounce); down(pid, 12.9)
        for pid in ("A2", "B2", "B4", "C1"):
            up(pid, 7.77); gest(pid, 7.77, 12.9, "shh", bounce); down(pid, 12.9)
        for pid in ("A1", "A4", "B1", "C2", "D1", "D2", "D4"):
            up(pid, 10.97); gest(pid, 10.97, 12.9, "shh", bounce); down(pid, 12.9)
        # 2. la dénonciation
        jk = lambda t: (JK[0], JK[1] + 40)
        for pid in ("A3", "B2"):
            up(pid, 20.92); gest(pid, 20.92, 22.35, "point", bounce); gest(pid, 22.35, 24.6, "point", jk)
        # 3. la salle fait « shh » à l'ouvreur, puis tout le monde dehors
        rest = ["A1", "A2", "A4", "B1", "B4", "C1", "C2", "D1", "D2", "D3", "D4"]
        for pid in rest:
            up(pid, 27.67); gest(pid, 27.67, 29.6, "shh", usher_head)
        # les sorties
        self.exit(P["B3"], 15.95, 420.0)
        self.exit(P["A3"], 24.6, 560.0)
        self.exit(P["B2"], 24.6, 380.0, after=P["A3"])
        prev = None
        for pid in ["A1", "A2", "A4", "B1", "B4", "D1", "D2", "D3", "D4", "C1"]:
            self.exit(P[pid], 31.4 + 0.08 * len(pid) * 0 + 0.1 * rest.index(pid), 430.0, after=prev)
            prev = P[pid]
        self.green_path(P["C2"], prev)

    def exit(self, p, t0, crouch_v, after=None, aisle_v=280.0):
        """Plié en deux le long de sa rangée jusqu'à l'allée, puis l'allée jusqu'à la porte. Si
        quelqu'un le précède dans l'allée, il attend au bout de sa rangée qu'il y ait la place."""
        yb = ROW_Y[p["row"]]
        x_end = AISLE_X + 95.0
        t_row = t0 + (p["x0"] - x_end) / crouch_v
        te = t_row + 0.25
        if after is not None and after["path"] is not None:
            a_te, a_yb = after["aisle_in"]
            need = a_te + (a_yb - yb + 170.0) / aisle_v
            te = max(te, need)
        t_door = te + (yb - DOOR_YB) / aisle_v
        p["stand"].append((t0, p["stand"][-1][1])); p["stand"].append((t0 + 0.15, -0.55))
        p["path"] = [(t0, p["x0"], yb, "row"), (t_row, x_end, yb, "row"), (te - 0.25, x_end, yb, "row"),
                     (te, AISLE_X, yb, "aisle"), (t_door, AISLE_X, DOOR_YB, "aisle")]
        p["aisle_in"] = (te, yb)
        p["gone"] = t_door + 0.25
        p["door"] = t_door

    def green_path(self, p, prev):
        """Le vert : il se lève avec les autres, attend au bout de sa rangée, revient en douce
        vers son pot, se fait prendre, repose le pot et sort le dernier."""
        yb = ROW_Y["C"]
        x0, x_end, x_pot = p["x0"], AISLE_X + 95.0, 262.0
        p["stand"] += [(31.4, 1.0), (31.55, -0.55)]
        p["path"] = [(31.4, x0, yb, "row"), (32.3, x_end, yb, "row"), (34.9, x_end, yb, "row"),
                     (36.3, x_pot, yb, "row"), (38.15, x_pot, yb, "row"), (38.55, x_end, yb, "row"),
                     (38.8, AISLE_X, yb, "aisle"), (40.05, AISLE_X, DOOR_YB, "aisle")]
        p["gest"].append((34.35, 34.9, "look", lambda t: (x_pot + 200, yb - 200)))
        p["gest"].append((36.4, 38.15, "hug", None))
        p["aisle_in"] = (38.8, yb)
        p["gone"] = 40.3
        p["door"] = 40.05
        self.t_door_close = 40.55
        if prev is not None and prev["aisle_in"][0] + (prev["aisle_in"][1] - yb + 170) / 280.0 > 38.8:
            print("[cinema] le vert rattrape la file", file=sys.stderr)

    def person_at(self, p, t):
        """Pose : x, yb (référence du dossier), lieu ('row'/'aisle'), debout (-0.55..1), visible."""
        if t >= p["gone"]:
            return None
        x, yb, where = p["x0"], ROW_Y[p["row"]], "row"
        if p["path"] is not None and t >= p["path"][0][0]:
            pts = p["path"]
            for a, b in zip(pts, pts[1:]):
                if a[0] <= t <= b[0]:
                    u = (t - a[0]) / max(1e-6, b[0] - a[0])
                    x, yb, where = lerp(a[1], b[1], u), lerp(a[2], b[2], u), b[3]
                    if a[3] == "row" and b[3] == "aisle":
                        where = "aisle" if u > 0.5 else "row"
                    break
            else:
                x, yb, where = pts[-1][1], pts[-1][2], pts[-1][3]
        st = keylin(p["stand"], t)
        if where == "aisle":
            st = 1.0
        return x, yb, where, st

    # ------------------------------------------------------------------ l'ouvreur
    def usher_at(self, t):
        """x, yb, lieu, la main, l'angle du bras (rad), lampe en main ?, taille (1 = normale)"""
        yb_bot = 1700.0
        if t < 40.9:
            x, yb, where = 95.0, yb_bot, "aisle"
        elif t < 45.4:
            x, yb, where = 95.0 + (AISLE_X - 95.0) * smooth((t - 40.9) / 0.5), lerp(yb_bot, ROW_Y["C"], smooth((t - 41.0) / 4.4)), "aisle"
        elif t < 46.1:
            x, yb, where = AISLE_X, ROW_Y["C"], "aisle"
        elif t < 49.0:
            x, yb, where = lerp(AISLE_X, 490.0, smooth((t - 46.1) / 2.9)), ROW_Y["C"], ("aisle" if t < 46.5 else "row")
        else:
            x, yb, where = 490.0, ROW_Y["C"], "row"
        s = row_scale(yb)
        Ru = 76.0 * s
        size = 1.0
        if 28.4 <= t < 29.0:
            size = lerp(1.0, 0.88, smooth((t - 28.4) / 0.2))
        elif 29.0 <= t < 30.0:
            size = lerp(0.88, 1.06, smooth((t - 29.0) / 0.35))
        elif t >= 30.0:
            size = 1.06
        head = (x, yb - 3.3 * Ru * size)
        shoulder = (x + 0.9 * Ru, yb - 2.3 * Ru * size)
        holding = t < T_LAMP or (t >= 53.15 and False)
        # la main : vers la cible du faisceau, à longueur de bras
        arm_len = 1.9 * Ru
        tgt = self.beam_target(t)
        if 49.0 <= t < T_LAMP:
            lp = self.lamp_held(t)
            hand = lp
        elif tgt is not None and holding:
            dx, dy = tgt[0] - shoulder[0], tgt[1] - shoulder[1]
            d = math.hypot(dx, dy) + 1e-6
            hand = (shoulder[0] + dx / d * arm_len, shoulder[1] + dy / d * arm_len)
        else:
            hand = (shoulder[0] + 0.25 * Ru, shoulder[1] + 1.3 * Ru)
        thumb = None
        for (t0, t1) in ((14.47, 15.6), (23.32, 24.6), (29.92, 31.2), (41.42, 42.5), (45.57, 46.3), (54.77, 56.2)):
            if t0 <= t <= t1:
                thumb = t
        return {"x": x, "yb": yb, "where": where, "s": s, "R": Ru, "size": size, "head": head,
                "shoulder": shoulder, "hand": hand, "holding": holding, "thumb": thumb}

    def lamp_held(self, t):
        """La lampe tenue au-dessus de Bounce (49 s -> 52 s)."""
        u = smooth((t - 51.35) / 0.55)
        return (lerp(672.0, 790.0, u), lerp(916.0, 1066.0, u))

    def lamp_free(self, t):
        """La lampe en l'air puis posée : (x, y, angle du faisceau)."""
        x0, y0 = 790.0, 1066.0
        x1, y1 = LAMP_LAND
        T = T_LAMP_LAND - T_LAMP
        aim = math.atan2(self.film_spot(T_LAMP_LAND)[1] - y1, self.film_spot(T_LAMP_LAND)[0] - x1)
        if t >= T_LAMP_LAND:
            sp = self.film_spot(t)
            return x1, y1, math.atan2(sp[1] - y1, sp[0] - x1)
        dt = t - T_LAMP
        vy0 = (y1 - y0 - 0.5 * G * T * T) / T
        x = lerp(x0, x1, dt / T)
        y = y0 + vy0 * dt + 0.5 * G * dt * dt
        a0 = math.pi / 2
        a1 = aim + 4 * math.pi
        return x, y, lerp(a0, a1, 1 - (1 - dt / T) ** 1.6)

    # ------------------------------------------------------------------ le faisceau
    def beam_target(self, t):
        """(x, y, rayon de la tache) ou None. Pendant que la lampe est tenue."""
        if t < T_LIGHT_ON:
            return None
        P = self.P

        def phead(pid, tt):
            p = P[pid]
            st = self.person_at(p, tt)
            if st is None:
                return (AISLE_X, DOOR_YB - 120)
            x, yb, where, a = st
            Rh = 62 * row_scale(yb)
            return (x, yb - 0.8 * Rh - 1.9 * Rh * max(0.0, a) - (0.0 if where == "row" else 0.0) + 40)
        bx = lambda tt: self.bounce_at(tt)[:2]
        keys = [
            (12.9, (420.0, 1180.0, 60.0)), (13.6, (560.0, 1160.0, 70.0)), (14.2, phead("B3", 14.2) + (85.0,)),
        ]
        if t < 14.2:
            return self._kinterp(keys, t)
        if t < 19.4:
            hx, hy = phead("B3", t)
            return (hx, hy + 30, 85.0)
        if t < 21.45:
            u = smooth((t - 19.4) / 2.0)
            return (lerp(820.0, 360.0, u), lerp(1150.0, 1250.0, u), 75.0)
        if t < 22.6:
            u = smooth((t - 21.45) / 1.15)
            return (lerp(360.0, JK[0], u), lerp(1250.0, JK[1] + 50, u), 85.0)
        if t < 23.0:
            u = smooth((t - 22.6) / 0.4)
            mx = (phead("A3", 23.0)[0] + phead("B2", 23.0)[0]) / 2
            my = (phead("A3", 23.0)[1] + phead("B2", 23.0)[1]) / 2
            return (lerp(JK[0], mx, u), lerp(JK[1] + 50, my, u), lerp(85.0, 150.0, u))
        if t < 25.8:
            a3, b2 = phead("A3", t), phead("B2", t)
            return ((a3[0] + b2[0]) / 2, (a3[1] + b2[1]) / 2, 150.0)
        if t < 26.4:
            u = smooth((t - 25.8) / 0.6)
            return (lerp(160.0, 560.0, u), lerp(1000.0, 640.0, u), lerp(110.0, 260.0, u))
        if t < 28.4:
            return (560.0, 640.0, 260.0)
        if t < 29.0:
            u = smooth((t - 28.4) / 0.3)
            return (lerp(560.0, 190.0, u), lerp(640.0, 1730.0, u), lerp(260.0, 60.0, u))
        if t < 30.6:
            u = smooth((t - 29.2) / 1.4)
            return (lerp(250.0, 860.0, u), lerp(1000.0, 1450.0, u) if u < 1 else 1450.0, 130.0)
        if t < 31.4:
            u = smooth((t - 30.6) / 0.8)
            return (lerp(860.0, 200.0, u), lerp(1450.0, 1300.0, u), 110.0)
        if t < 36.3:
            return (AISLE_X + 10, 1160.0 + 60 * math.sin(t * 0.9), 95.0)
        if t < 36.45:
            u = smooth((t - 36.3) / 0.15)
            g = phead("C2", 36.45)
            return (lerp(AISLE_X + 10, g[0] + 40, u), lerp(1160.0, g[1] + 30, u), 100.0)
        if t < 40.5:
            g = phead("C2", t)
            return (g[0] + (40 if t < 38.3 else 0), g[1] + 30, 100.0)
        if t < 40.9:
            return (AISLE_X + 30, DOOR_YB - 60, 90.0)
        if t < 41.1:
            u = smooth((t - 40.9) / 0.2)
            return (lerp(300.0, 600.0, u), lerp(1250.0, 1300.0, u), 100.0)
        if t < 41.3:
            u = smooth((t - 41.1) / 0.2)
            b = bx(41.3)
            return (lerp(600.0, b[0], u), lerp(1300.0, b[1], u), 115.0)
        b = bx(t)
        return (b[0], b[1], 118.0)

    def _kinterp(self, keys, t):
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                u = smooth((t - t0) / (t1 - t0))
                return tuple(lerp(a, b, u) for a, b in zip(v0, v1))
        return keys[-1][1]

    # ------------------------------------------------------------------ le film
    def film_state(self, t):
        """Position (x locale), pas, tourné (0 profil -> 1 face), pose."""
        hits = self.hits
        frozen = any(h <= t < h + 0.5 for h in hits)
        # avance sur la pointe des pieds, s'arrête net à chaque « Bounce »
        x = 150.0
        speed = 13.0
        dt = 1 / 30
        # intégration analytique simple : temps en mouvement avant t
        moving = t - sum(max(0.0, min(t, h + 0.5) - h) for h in hits if h < t)
        stop_at = 41.0
        if t > stop_at:
            moving = stop_at - sum(max(0.0, min(stop_at, h + 0.5) - h) for h in hits if h < stop_at)
        x += speed * moving
        turn = 0.0
        if 38.6 <= t < 39.5:
            turn = 0.75 * math.sin(math.pi * clamp01((t - 38.6) / 0.9)) ** 0.5
        notch_hits = [h for h in hits if 42.0 < h < 49.0]
        if t >= 42.0:
            k = sum(1 for h in notch_hits if h <= t)
            last = max([h for h in notch_hits if h <= t], default=None)
            turn = 0.13 * (k - 1) + (0.13 * smooth((t - last) / 0.12) if last is not None else 0)
            turn = min(turn, 0.65)
        pose = "tiptoe"
        if frozen and t < 41.0:
            pose = "freeze"
        if t >= 41.0:
            pose = "stand"
        walk = 0.0
        xd = x
        door_x = 690.0
        if t >= 55.6:
            u = clamp01((t - 55.6) / 2.4)
            xd = lerp(x, door_x, u)
            pose = "walk" if t < 58.0 else "stand"
            turn = lerp(turn, 0.0, smooth((t - 55.6) / 0.4)) if t < 58.95 else turn
            walk = (t - 55.6) * 3.2
        if t >= 58.95:
            turn = smooth((t - 58.95) / 0.35)
            pose = "shh" if t >= 59.15 else "stand"
        phase = moving * 2.2
        return {"x": xd, "turn": turn, "pose": pose, "phase": phase if pose != "walk" else walk}

    def film_spot(self, t):
        """Où tombe la lampe posée, sur l'écran (coordonnées de l'image)."""
        fs = self.film_state(max(t, T_LAMP_LAND))
        x = SCREEN[0] + fs["x"]
        if t >= T_PAYOFF:
            x = SCREEN[0] + 690.0
        return (x, SCREEN[1] + 200.0)

    def film_door(self, t):
        """Ouverture de la porte du film, 0..1."""
        if t < 57.25:
            return 0.0
        if t < 57.7:
            return smooth((t - 57.25) / 0.45)
        if t < 59.95:
            return 1.0
        return 1.0 - smooth((t - 59.95) / 0.35)

    def draw_film(self, t, S, bx, by):
        img = Image.new("RGB", (int(SW * S), int(SH * S)), FILM_BG)
        d = ImageDraw.Draw(img, "RGBA")

        def P(v):
            return v * S
        # couloir
        d.rectangle([0, P(330), P(SW), P(SH)], fill=FILM_FLOOR)
        for k in range(6):
            x = 60 + k * 140
            d.line([P(x), P(330), P(x - 90), P(SH)], fill=(58, 66, 90), width=int(P(3)))
        d.rectangle([0, P(40), P(SW), P(52)], fill=(80, 92, 120))
        # la porte du film
        dx0, dx1, dy0, dy1 = 640.0, 740.0, 120.0, 330.0
        op = self.film_door(t)
        d.rectangle([P(dx0 - 8), P(dy0 - 8), P(dx1 + 8), P(dy1)], fill=(52, 58, 78))
        if op > 0:
            d.rectangle([P(dx0), P(dy0), P(dx1), P(dy1)], fill=(236, 238, 246))
        fs = self.film_state(t)
        sx = fs["x"]
        in_door = t >= 58.0
        if t < 60.4:
            self.draw_silhouette(d, sx, 330.0, fs, S)
        # le battant de la porte : par-dessus la silhouette quand il se referme
        wdoor = (dx1 - dx0) * (1 - op)
        d.rectangle([P(dx0), P(dy0), P(dx0 + max(2.0, wdoor)), P(dy1)], fill=(34, 38, 54))
        if op < 0.5:
            d.ellipse([P(dx0 + wdoor - 18), P(222), P(dx0 + wdoor - 8), P(232)], fill=(150, 150, 170))
        # sous-titre du film
        d.text((P(SW / 2), P(398)), "[ silence ]", fill=(232, 232, 240), anchor="mm", font=font(int(36 * S)))
        # l'ombre de Bounce
        if by + 70 < SCREEN[3] + R * 1.3:
            lx, ly = bx - SCREEN[0], by + 70 - SCREEN[1]
            rr = 1.3 * R
            d.ellipse([P(lx - rr), P(ly - rr), P(lx + rr), P(ly + rr)], fill=(30, 34, 48, 215))
        # le faisceau de l'ouvreur, quand il est sur l'écran
        tg = self.beam_target(t) if t < T_LAMP else None
        if tg is not None and tg[1] < SCREEN[3] + 60:
            lx, ly, rr = tg[0] - SCREEN[0], tg[1] - SCREEN[1], tg[2]
            for k, a in ((1.0, 120), (0.75, 70), (0.45, 60)):
                d.ellipse([P(lx - rr * k * 1.25), P(ly - rr * k), P(lx + rr * k * 1.25), P(ly + rr * k)], fill=BEAM + (a,))
        if t >= T_LAMP_LAND:
            sp = self.film_spot(t)
            lx, ly = sp[0] - SCREEN[0], sp[1] - SCREEN[1]
            for k, a in ((1.0, 90), (0.7, 60)):
                d.ellipse([P(lx - 110 * k), P(ly - 175 * k), P(lx + 110 * k), P(ly + 175 * k)], fill=BEAM + (a,))
        return img

    def draw_silhouette(self, d, x, foot, fs, S):
        def P(v):
            return v * S
        turn, pose, ph = fs["turn"], fs["pose"], fs["phase"]
        Rh = 27.0
        hip_y = foot - 125.0
        sh_y = foot - 225.0
        head_y = foot - 262.0
        bw = lerp(22.0, 40.0, turn)
        lw = int(P(17))
        # jambes
        if pose == "tiptoe":
            a = math.sin(ph)
            k1 = (x + 30 * a, foot - 60 - 30 * max(0, a))
            k2 = (x - 30 * a, foot - 60 - 30 * max(0, -a))
            f1 = (x + 45 * a, foot - 40 * max(0, a))
            f2 = (x - 45 * a, foot - 40 * max(0, -a))
        elif pose == "freeze":
            k1, f1 = (x + 28, foot - 85), (x + 50, foot - 70)
            k2, f2 = (x - 6, foot - 60), (x - 10, foot)
        elif pose == "walk":
            a = math.sin(ph * 2.5)
            k1, f1 = (x + 18 * a, foot - 62), (x + 34 * a, foot)
            k2, f2 = (x - 18 * a, foot - 62), (x - 34 * a, foot)
        else:
            sp = lerp(10.0, 26.0, turn)
            k1, f1 = (x + sp, foot - 62), (x + sp, foot)
            k2, f2 = (x - sp, foot - 62), (x - sp, foot)
        for k, f in ((k1, f1), (k2, f2)):
            d.line([P(x), P(hip_y), P(k[0]), P(k[1]), P(f[0]), P(f[1])], fill=INKF, width=lw, joint="curve")
        # torse
        d.rounded_rectangle([P(x - bw), P(sh_y - 8), P(x + bw), P(hip_y + 6)], radius=int(P(14)), fill=INKF)
        # bras
        aw = int(P(14))
        if pose == "freeze":
            arms = [((x - bw + 6, sh_y + 6), (x - 50, sh_y - 30), (x - 62, sh_y - 80)),
                    ((x + bw - 6, sh_y + 6), (x + 52, sh_y - 30), (x + 66, sh_y - 78))]
        elif pose == "tiptoe":
            arms = [((x - bw + 6, sh_y + 8), (x - 52, sh_y + 30), (x - 80, sh_y + 20)),
                    ((x + bw - 6, sh_y + 8), (x + 54, sh_y + 26), (x + 82, sh_y + 10))]
        elif pose == "shh":
            arms = [((x - bw + 6, sh_y + 8), (x - bw - 12, sh_y + 60), (x - bw - 10, sh_y + 100)),
                    ((x + bw - 6, sh_y + 8), (x + bw + 26, sh_y - 4), (x + 6, head_y + 20))]
        else:
            arms = [((x - bw + 6, sh_y + 8), (x - bw - 12, sh_y + 60), (x - bw - 10, sh_y + 100)),
                    ((x + bw - 6, sh_y + 8), (x + bw + 12, sh_y + 60), (x + bw + 10, sh_y + 100))]
        for pts in arms:
            d.line([(P(px), P(py)) for px, py in pts], fill=INKF, width=aw, joint="curve")
        if pose == "shh":
            d.rounded_rectangle([P(x + 1), P(head_y - 2), P(x + 13), P(head_y + 34)], radius=int(P(6)), fill=(26, 26, 34))
        # cou et tête ; le petit nez de profil dit où elle regarde
        d.rectangle([P(x - 8), P(head_y + 14), P(x + 8), P(sh_y)], fill=INKF)
        d.ellipse([P(x - Rh), P(head_y - Rh), P(x + Rh), P(head_y + Rh)], fill=INKF)
        if turn < 0.95:
            nx = x + Rh * (1 - turn) * 0.92
            nsz = 9 * (1 - turn)
            d.polygon([(P(nx - 2), P(head_y - 6)), (P(nx + nsz), P(head_y + 4)), (P(nx - 2), P(head_y + 10))], fill=INKF)
        if pose == "shh":
            d.rounded_rectangle([P(x - 6), P(head_y - 4), P(x + 6), P(head_y + 30)], radius=int(P(5)), fill=(40, 40, 52))

    # ------------------------------------------------------------------ pop-corn
    def build_popcorn(self, rng):
        self.pop = []
        for (t0, x, y, n, power) in ((5.62, POT_X, POT_TOP - 20, 46, 1.0),
                                     (36.47, POT_X, POT_TOP - 20, 34, 0.85), (41.72, POT_X, POT_TOP - 20, 10, 0.55)):
            for _ in range(n):
                vx = float(rng.uniform(-520, 520)) * power
                vy = -float(rng.uniform(900, 1850)) * power
                land = float(rng.uniform(1020, 1330)) if t0 < 30 else float(rng.uniform(1300, 1420))
                self.pop.append((t0, x + float(rng.uniform(-30, 30)), y, vx, vy, land, float(rng.uniform(0, 6))))
        self.head_pop = {pid: [(float(rng.uniform(-0.6, 0.6)), float(rng.uniform(-0.2, 0.3))) for _ in range(3)]
                         for pid in ("A1", "A2", "A3", "B1", "B2", "B3", "C1")}

    def pot_fill(self, t):
        return 1.0 if t < 5.6 else (0.55 if t < 28.0 else (0.45 if t < 36.45 else (0.2 if t < 41.7 else 0.12)))

    # ------------------------------------------------------------------ moteur
    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi] <= self.t:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and self.t >= T_PAYOFF:
            self.payoff = True
            evs.append(("payoff", "film dehors"))
        if self.t >= T_END:
            self.done = True
        return evs

    def hero_mood(self):
        return "win"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def narr_window(self, key):
        for n in self.narr:
            if n["key"] == key:
                return n["start"], n["end"]
        for (tt, txt, k) in self.lines:
            if k == key:
                return tt, tt + 0.6
        return None

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, snap, t, S):
        img = dr._image
        da = ImageDraw.Draw(img, "RGBA")

        def P(v):
            return v * S

        def rect(x0, y0, x1, y1, col, **kw):
            dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=col, **kw)
        bx, by, brow, bdep = self.bounce_at(t)
        # mur, rayons du projecteur, poussière
        rect(0, 360, W, H, WALL)
        for (x0, x1, tx0, tx1) in ((300, 420, 170, 330), (470, 610, 380, 560), (650, 780, 610, 800), (820, 940, 830, 975)):
            da.polygon([(P(x0), 0), (P(x1), 0), (P(tx1), P(SCREEN[1])), (P(tx0), P(SCREEN[1]))], fill=(170, 180, 220, 16))
        for (dx, dy, ph, r) in self.dust:
            x = (dx + 8 * math.sin(t * 0.4 + ph)) % W
            y = dy + 6 * math.sin(t * 0.3 + ph * 2)
            da.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=(200, 210, 240, 45))
        # halo de l'écran
        for k in range(5, 0, -1):
            col = tuple(int(WALL[i] + (60 - WALL[i]) * 0.17 * (6 - k)) for i in range(3))
            dr.rounded_rectangle([P(SCREEN[0] - 14 * k), P(SCREEN[1] - 10 * k), P(SCREEN[2] + 14 * k), P(SCREEN[3] + 10 * k)],
                                 radius=int(P(18)), fill=col)
        film = self.draw_film(t, S, bx, by)
        img.paste(film, (int(P(SCREEN[0])), int(P(SCREEN[1]))))
        # le panneau
        for k in range(3, 0, -1):
            da.rounded_rectangle([P(318 - 8 * k), P(378 - 6 * k), P(762 + 8 * k), P(434 + 6 * k)], radius=int(P(16)),
                                 fill=(255, 60, 60, 18))
        dr.rounded_rectangle([P(318), P(378), P(762), P(434)], radius=int(P(12)), fill=(64, 12, 18), outline=(255, 80, 80), width=int(P(4)))
        dr.text((P(540), P(406)), "PLEASE BE QUIET", fill=(255, 128, 116), anchor="mm", font=font(int(40 * S)))
        # la porte EXIT et l'allée
        door_open = self.door_open(t)
        rect(DOOR[0] - 8, DOOR[1] - 8, DOOR[2] + 8, DOOR[3], (30, 28, 38))
        rect(*DOOR, (44, 40, 52))
        if door_open > 0:
            w = (DOOR[2] - DOOR[0]) * door_open
            rect(DOOR[0], DOOR[1], DOOR[0] + w, DOOR[3], (255, 214, 150))
        for k in range(3, 0, -1):
            da.rounded_rectangle([P(24 - 5 * k), P(748 - 4 * k), P(138 + 5 * k), P(790 + 4 * k)], radius=int(P(8)), fill=(80, 255, 140, 20))
        dr.rounded_rectangle([P(24), P(748), P(138), P(790)], radius=int(P(6)), fill=(18, 70, 40), outline=(90, 255, 150), width=int(P(3)))
        dr.text((P(81), P(769)), "EXIT", fill=(140, 255, 175), anchor="mm", font=font(int(30 * S)))
        rect(0, DOOR[3], 205, H, (22, 20, 28))
        for yb in [1065 + k * 70 for k in range(12)]:
            rect(4, yb, 200, yb + 7, (40, 36, 50))
        # les marcheurs à la porte (silhouette dans la lumière)
        walkers_aisle = []
        usher = self.usher_at(t)
        # rangées, du fond (près de l'écran) vers nous
        for row in ROW_ORDER:
            yb = ROW_Y[row]
            s = row_scale(yb)
            people = []
            for p in self.P.values():
                st = self.person_at(p, t)
                if st is None:
                    continue
                x, ybp, where, a = st
                if where == "aisle":
                    walkers_aisle.append((p, st))
                elif p["row"] == row:
                    people.append((p, st))
            for p, st in people:
                self.draw_person(dr, da, p, st, t, S)
            if usher["where"] == "row" and row == "C":
                self.draw_usher(dr, da, usher, t, S)
            for x in SEATS:
                w2 = 86 * s
                dr.rounded_rectangle([P(x - w2), P(yb), P(x + w2), P(yb + 150 * s)], radius=int(P(22 * s)),
                                     fill=SEAT_COL, outline=SEAT_EDGE, width=int(P(4)))
            if row == "C":
                self.draw_pot(dr, da, t, S)
                self.draw_jacket(dr, t, S, back=True)
                if brow != "C":
                    self.draw_jacket(dr, t, S, back=False)
            if row == "A" and t >= T_LAMP_LAND:
                lx, ly, ang = self.lamp_free(t)
                self.draw_lamp(dr, lx, ly, ang, S)
            if brow == row:
                self.draw_hero(dr, da, t, S, bx, by, brow)
        # l'allée : ceux qui sortent, puis l'ouvreur au premier plan
        walkers_aisle.sort(key=lambda w: w[1][1])
        for p, st in walkers_aisle:
            self.draw_person(dr, da, p, st, t, S)
        if usher["where"] == "aisle":
            self.draw_usher(dr, da, usher, t, S)
        # le pop-corn en l'air
        for (t0, x0, y0, vx, vy, land, ph) in self.pop:
            if t < t0:
                continue
            dt = t - t0
            y = y0 + vy * dt + 0.5 * G * dt * dt
            if vy + G * dt > 0 and y > land:
                continue
            x = x0 + vx * dt
            for k in range(3):
                ox, oy = 5 * math.cos(ph + k * 2.1), 5 * math.sin(ph + k * 2.1)
                dr.ellipse([P(x + ox - 6), P(y + oy - 6), P(x + ox + 6), P(y + oy + 6)], fill=POP)
        # le faisceau
        self.draw_beam(da, usher, t, S)
        if t >= T_LIGHT_ON:
            # Bounce reste par-dessus la lumière (sa couleur ne change pas)
            self.draw_hero(dr, da, t, S, bx, by, brow)
        if T_LAMP <= t < T_LAMP_LAND:
            lx, ly, ang = self.lamp_free(t)
            self.draw_lamp(dr, lx, ly, ang, S)
        # les bulles
        self.draw_bubbles(dr, t, S, usher)
        # micro-réactions de Bounce : les yeux quand le bleu est puni, penchée vers lui
        # (dessinées par-dessus via l'état du héros)
        if 52.42 <= t < 52.58:
            da.rectangle([0, 0, P(W), P(H)], fill=(255, 245, 210, int(60 * math.sin(math.pi * (t - 52.42) / 0.16))))

    def draw_hero(self, dr, da, t, S, bx, by, brow):
        def P(v):
            return v * S
        # micro-réactions : grands yeux quand le bleu est puni, penchée vers lui quand il sort
        if 14.47 <= t < 15.25 and base.HERO["expr"] == "calm":
            base.HERO["expr"] = "shock"
        if 15.95 <= t < 16.9:
            base.HERO["tilt"] = -0.3 * math.sin(math.pi * (t - 15.95) / 0.95)
        base.ball(dr, P(bx), P(by), P(R))
        if brow == "C":
            self.draw_jacket(dr, t, S, back=False, by=by)
            if self.in_pot(t) is not None:
                self.draw_pot(dr, da, t, S)

    def door_open(self, t):
        v = 0.0
        for p in self.P.values():
            td = p.get("door")
            if td is None:
                continue
            if td - 0.45 <= t <= td + 0.55:
                v = max(v, min(smooth((t - td + 0.45) / 0.25), 1 - smooth((t - td - 0.3) / 0.25)))
        if 56.0 <= t:
            pass
        return v

    # ------------------------------------------------------------------ personnages
    def draw_person(self, dr, da, p, st, t, S):
        def P(v):
            return v * S
        x, yb, where, a = st
        s = row_scale(yb)
        Rh = 62.0 * s
        col = p["col"]
        rim = tuple(min(255, int(c * 0.5 + 120)) for c in col)
        # le sursaut général au premier « Bounce »
        jolt = 0.0
        if 2.12 <= t < 2.5:
            jolt = 22 * s * math.sin(math.pi * (t - 2.12) / 0.38)
        lean = 0.0
        gest = None
        for (t0, t1, kind, target) in p["gest"]:
            if t0 <= t < t1:
                gest = (kind, target)
        tx = None
        if gest is not None and gest[1] is not None:
            tx, ty = gest[1](t)
            lean = max(-1.0, min(1.0, (tx - x) / 300.0))
        if gest is not None and gest[0] == "look":
            lean = 0.8
        if p["row"] == "D" and gest is not None and gest[0] == "shh" and abs(x - HOME[0]) < 120:
            lean = -1.0                                            # il se penche de côté, sans cacher la balle
        a_draw = a
        if where == "aisle":
            a_draw = 1.0
        hy = yb - 0.8 * Rh - 1.9 * Rh * max(0.0, a_draw) + 0.75 * Rh * max(0.0, -a_draw) - jolt
        hx = x + lean * 0.45 * Rh * max(0.3, a_draw)
        top_body = hy + 0.65 * Rh
        bot = yb + 120 * s if where == "row" else yb + 1.0 * Rh
        # corps
        dr.rounded_rectangle([P(x - 1.2 * Rh), P(top_body), P(x + 1.2 * Rh), P(bot)], radius=int(P(0.55 * Rh)), fill=col)
        if where == "aisle":
            ph = t * 7.0
            for sgn in (-1, 1):
                fx = x + sgn * 0.45 * Rh + 0.3 * Rh * math.sin(ph) * sgn
                dr.line([P(x + sgn * 0.45 * Rh), P(bot - 4), P(fx), P(bot + 1.25 * Rh)], fill=col, width=int(P(0.42 * Rh)))
            # tête basse : ceux qui sortent baissent la tête
            hy += 0.15 * Rh
        # bras
        if gest is not None and gest[0] in ("shh", "point"):
            side = 1 if (tx or x) >= x else -1
            shx, shy = hx + side * 1.0 * Rh, top_body + 0.35 * Rh
            if gest[0] == "shh":
                ex, ey = shx + side * 0.35 * Rh, hy + 0.1 * Rh
                dr.line([P(shx), P(shy), P(ex), P(ey)], fill=col, width=int(P(0.42 * Rh)))
                dr.rounded_rectangle([P(ex - 0.12 * Rh), P(ey - 0.75 * Rh), P(ex + 0.12 * Rh), P(ey + 0.05 * Rh)],
                                     radius=int(P(0.1 * Rh)), fill=rim)
            else:
                dx, dy = tx - shx, ty - shy
                d = math.hypot(dx, dy) + 1e-6
                L = 2.3 * Rh
                ex, ey = shx + dx / d * L, shy + dy / d * L
                dr.line([P(shx), P(shy), P(ex), P(ey)], fill=col, width=int(P(0.4 * Rh)))
                dr.ellipse([P(ex - 0.2 * Rh), P(ey - 0.2 * Rh), P(ex + 0.2 * Rh), P(ey + 0.2 * Rh)], fill=rim)
        if gest is not None and gest[0] == "hug":
            pass
        # tête
        shape = p["shape"]
        if shape == "tall":
            dr.ellipse([P(hx - 0.9 * Rh), P(hy - 1.2 * Rh), P(hx + 0.9 * Rh), P(hy + Rh)], fill=col, outline=rim, width=int(P(3)))
        else:
            rr = Rh * (0.85 if shape == "small" else 1.0)
            dr.ellipse([P(hx - rr), P(hy - rr), P(hx + rr), P(hy + rr)], fill=col, outline=rim, width=int(P(3)))
        if shape == "bun":
            dr.ellipse([P(hx - 0.42 * Rh), P(hy - 1.55 * Rh), P(hx + 0.42 * Rh), P(hy - 0.7 * Rh)], fill=col, outline=rim, width=int(P(3)))
        elif shape == "cap":
            dr.chord([P(hx - 1.02 * Rh), P(hy - 1.08 * Rh), P(hx + 1.02 * Rh), P(hy + 0.5 * Rh)], 180, 360, fill=tuple(int(c * 0.6) for c in col))
        elif shape == "tail":
            dr.ellipse([P(hx - 0.3 * Rh), P(hy + 0.5 * Rh), P(hx + 0.3 * Rh), P(hy + 1.5 * Rh)], fill=tuple(int(c * 0.75) for c in col))
        # du pop-corn sur la tête
        if p["id"] in self.head_pop and t >= 6.9:
            for (ux, uy) in self.head_pop[p["id"]]:
                gx, gy = hx + ux * Rh, hy - Rh * 0.85 + uy * Rh * 0.3
                dr.ellipse([P(gx - 7), P(gy - 7), P(gx + 7), P(gy + 7)], fill=POP)
        if p["id"] == "C2" and t >= 36.6:
            for k in range(7):
                gx, gy = hx + (k - 3) * 0.28 * Rh, hy - Rh * (0.8 - 0.1 * abs(k - 3)) + (k % 2) * 6
                dr.ellipse([P(gx - 8), P(gy - 8), P(gx + 8), P(gy + 8)], fill=POP)
        # le vert serre son pot dans les bras
        if p["id"] == "C2" and gest is not None and gest[0] == "hug":
            pass

    def draw_usher(self, dr, da, u, t, S):
        def P(v):
            return v * S
        x, yb, Ru, size = u["x"], u["yb"], u["R"], u["size"]
        hx, hy = u["head"]
        col = USHER_COL
        rim = (220, 120, 130)
        top = hy + 0.7 * Ru
        bot = yb + 2.6 * Ru if u["where"] == "aisle" else yb + 130 * u["s"]
        dr.rounded_rectangle([P(x - 1.15 * Ru), P(top), P(x + 1.15 * Ru), P(bot)], radius=int(P(0.5 * Ru)), fill=col)
        dr.rectangle([P(x - 1.15 * Ru), P(top + 1.4 * Ru), P(x + 1.15 * Ru), P(top + 1.6 * Ru)], fill=GOLD)
        if u["where"] == "aisle":
            for sgn in (-1, 1):
                dr.line([P(x + sgn * 0.5 * Ru), P(bot - 6), P(x + sgn * 0.55 * Ru), P(bot + 1.2 * Ru)], fill=(70, 18, 26), width=int(P(0.5 * Ru)))
        dr.ellipse([P(hx - Ru), P(hy - Ru), P(hx + Ru), P(hy + Ru)], fill=col, outline=rim, width=int(P(3)))
        dr.rounded_rectangle([P(hx - 0.85 * Ru), P(hy - 1.35 * Ru), P(hx + 0.85 * Ru), P(hy - 0.7 * Ru)], radius=int(P(0.2 * Ru)), fill=(46, 20, 26))
        dr.rectangle([P(hx - 0.85 * Ru), P(hy - 0.92 * Ru), P(hx + 0.85 * Ru), P(hy - 0.78 * Ru)], fill=GOLD)
        # bras de la lampe
        sx, sy = u["shoulder"]
        hdx, hdy = u["hand"]
        dr.line([P(sx), P(sy), P(hdx), P(hdy)], fill=col, width=int(P(0.42 * Ru)))
        if u["holding"]:
            tg = self.beam_target(t)
            if 49.0 <= t < T_LAMP:
                ang = math.pi / 2
            elif tg is not None:
                ang = math.atan2(tg[1] - hdy, tg[0] - hdx)
            else:
                ang = math.pi / 2
            self.draw_lamp(dr, hdx, hdy, ang, S, on=t >= T_LIGHT_ON)
        # l'autre bras : le pouce vers la porte
        if u["thumb"] is not None:
            k = smooth((t - u["thumb"]) / 0.25) if True else 1
            ox, oy = x - 0.9 * Ru, top + 0.35 * Ru
            if 54.77 <= t <= 56.2:
                ox = x + 0.9 * Ru                                    # le bras tendu vers le film
                sp = self.film_spot(t)
                dx, dy = sp[0] - ox, sp[1] - oy
                dd = math.hypot(dx, dy) + 1e-6
                tx, ty = ox + dx / dd * 3.2 * Ru, oy + dy / dd * 3.2 * Ru
            else:
                tx, ty = x - 1.2 * Ru, top - 1.3 * Ru
            ex, ey = lerp(ox, tx, k), lerp(oy + Ru, ty, k)
            dr.line([P(ox), P(oy), P(ex), P(ey)], fill=col, width=int(P(0.4 * Ru)))
            dr.rounded_rectangle([P(ex - 0.13 * Ru), P(ey - 0.55 * Ru), P(ex + 0.13 * Ru), P(ey + 0.05 * Ru)], radius=int(P(0.1 * Ru)), fill=rim)

    def draw_lamp(self, dr, x, y, ang, S, on=True):
        def P(v):
            return v * S
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(u, v):
            return (P(x + u * ca - v * sa), P(y + u * sa + v * ca))
        dr.polygon([Q(-34, -10), Q(14, -10), Q(14, 10), Q(-34, 10)], fill=(150, 152, 166))
        dr.polygon([Q(14, -16), Q(30, -16), Q(30, 16), Q(14, 16)], fill=(185, 188, 200))
        dr.polygon([Q(30, -14), Q(34, -14), Q(34, 14), Q(30, 14)], fill=(255, 240, 180) if on else (90, 90, 100))

    def beam_geom(self, usher, t):
        """(origine, direction ou cible, rayon de tache, longueur) ou None."""
        if t < T_LIGHT_ON:
            return None
        if t < 49.0:
            tg = self.beam_target(t)
            return usher["hand"], (tg[0], tg[1]), tg[2]
        if t < T_LAMP:
            hx, hy = usher["hand"]
            bxy = self.bounce_at(t)[:2]
            return (hx, hy + 20), (hx + 0.25 * (bxy[0] - hx), max(hy + 190, bxy[1] - 10)), 90.0
        lx, ly, ang = self.lamp_free(t)
        if t < T_LAMP_LAND:
            L = 1500.0
            return (lx, ly), (lx + L * math.cos(ang), ly + L * math.sin(ang)), 260.0
        sp = self.film_spot(t)
        return (lx, ly), sp, 110.0

    def draw_beam(self, da, usher, t, S):
        g = self.beam_geom(usher, t)
        if g is None:
            return

        def P(v):
            return v * S
        (ox, oy), (tx, ty), rr = g
        dx, dy = tx - ox, ty - oy
        d = math.hypot(dx, dy) + 1e-6
        nx, ny = -dy / d, dx / d
        on_screen = ty < SCREEN[3] + 40 and SCREEN[0] < tx < SCREEN[2]
        pts = [(P(ox + nx * 8), P(oy + ny * 8)), (P(tx + nx * rr), P(ty + ny * rr)),
               (P(tx - nx * rr), P(ty - ny * rr)), (P(ox - nx * 8), P(oy - ny * 8))]
        da.polygon(pts, fill=BEAM + (44,))
        if not on_screen and t < T_LAMP:
            for k, al in ((1.0, 52), (0.6, 46)):
                da.ellipse([P(tx - rr * k), P(ty - rr * k * 0.8), P(tx + rr * k), P(ty + rr * k * 0.8)], fill=BEAM + (al,))

    def draw_pot(self, dr, da, t, S):
        def P(v):
            return v * S
        x, top = POT_X, POT_TOP
        g = self.P["C2"]
        if 36.4 <= t < 38.15:                                  # dans les bras du vert
            st = self.person_at(g, t)
            if st is not None:
                gx, yb, _, a = st
                Rh = 62 * row_scale(yb)
                hy = yb - 0.8 * Rh - 1.9 * Rh * max(0.0, a) + 0.75 * Rh * max(0.0, -a)
                u = smooth((t - 36.45) / 0.3) * (1 - smooth((t - 37.6) / 0.5))
                x = lerp(POT_X, gx + 1.1 * Rh, u)
                top = lerp(POT_TOP, hy + 0.2 * Rh, u)
        sq = 0.0
        ip = self.in_pot(t)
        if ip is not None:
            sq = math.sin(math.pi * ip[0]) * 0.18
        w0, w1, h = 64 * (1 + sq), 50 * (1 + sq * 0.6), 118 * (1 - sq)
        y0 = top + 118 - h
        fill = self.pot_fill(t)
        # pop-corn au sommet
        for k in range(int(4 + 7 * fill)):
            px = x + (k - (4 + 7 * fill) / 2) * 12 * (0.8 + 0.4 * fill)
            py = y0 - 6 - 16 * fill * math.sin(math.pi * (k + 0.5) / (4 + 7 * fill))
            dr.ellipse([P(px - 9), P(py - 9), P(px + 9), P(py + 9)], fill=POP)
        dr.polygon([(P(x - w0), P(y0)), (P(x + w0), P(y0)), (P(x + w1), P(top + 118)), (P(x - w1), P(top + 118))], fill=(214, 46, 50))
        for k in (-2, 0, 2):
            u0 = k / 5
            dr.polygon([(P(x + w0 * u0 - 7), P(y0)), (P(x + w0 * u0 + 7), P(y0)), (P(x + w1 * u0 + 6), P(top + 118)), (P(x + w1 * u0 - 6), P(top + 118))], fill=(245, 240, 236))

    def draw_jacket(self, dr, t, S, back, by=None):
        def P(v):
            return v * S
        x = JK[0]
        top = ROW_Y["C"] - 28
        dep = 0.0
        ij = self.in_jacket(t)
        if ij is not None:
            dep = ij[1] * math.sin(math.pi * ij[0]) if ij[1] < 100 else ij[1] * math.sin(math.pi * ij[0]) ** 0.35
        col, dk = (62, 150, 84), (40, 104, 58)
        if back:
            dr.rounded_rectangle([P(x - 88), P(top - 8), P(x + 88), P(top + 160)], radius=int(P(40)), fill=dk)
            return
        if dep > 40 and ij[1] >= 100:
            # elle est dedans : la doudoune gonfle et se referme par-dessus elle
            k = smooth((dep - 40) / 60.0)
            hw = lerp(88, 148, k)
            ytop = top - 95 * k
            dr.rounded_rectangle([P(x - hw), P(ytop), P(x + hw), P(top + 172)], radius=int(P(lerp(36, 70, k))), fill=col)
            for j in range(1, 5):
                yy = ytop + j * (top + 172 - ytop) / 5
                dr.line([P(x - hw + 14), P(yy), P(x + hw - 14), P(yy)], fill=dk, width=int(P(4)))
            dr.line([P(x), P(ytop + 10), P(x), P(top + 165)], fill=dk, width=int(P(4)))
            dr.rounded_rectangle([P(x - 60), P(ytop - 6), P(x + 60), P(ytop + 26)], radius=int(P(14)), fill=dk)
            return
        dent = min(dep, 60.0) * 0.5
        dr.rounded_rectangle([P(x - 88), P(top + dent), P(x + 88), P(top + 165)], radius=int(P(36)), fill=col)
        for k in range(1, 4):
            yy = top + dent + k * (165 - dent) / 4
            dr.line([P(x - 78), P(yy), P(x + 78), P(yy)], fill=dk, width=int(P(4)))
        dr.line([P(x), P(top + dent + 6), P(x), P(top + 160)], fill=dk, width=int(P(4)))

    # ------------------------------------------------------------------ bulles
    def speakers(self, key, t, usher):
        P = self.P
        if key in ("OUT_YOU", "OUT_TWO", "OUT_ALL", "OUT_YOU2", "NOW", "OUT_FILM"):
            return [usher["head"]], "usher"
        if key == "SHH_FILM":
            fs = self.film_state(t)
            return [(SCREEN[0] + fs["x"], SCREEN[1] + 330 - 262)], "film"
        who = {"SHH_B3": ["B3"], "SHH_2": ["A3", "D3"], "SHH_4": ["A2", "B2", "B4", "C1"], "SHH_2B": ["A3", "B2"],
               "SHH_ALL": list(P.keys()),
               "SHH_USHER": ["A1", "A2", "A4", "B1", "B4", "C1", "C2", "D1", "D2", "D3", "D4"]}[key]
        heads = []
        for pid in who:
            st = self.person_at(P[pid], t)
            if st is None:
                continue
            x, yb, where, a = st
            Rh = 62 * row_scale(yb)
            heads.append((x, yb - 0.8 * Rh - 1.9 * Rh * max(0.0, a) - Rh))
        return heads, ("group" if key in ("SHH_ALL", "SHH_USHER") else "single")

    def clear_of_bounce(self, cands, bw, bh, t, others=()):
        """La première place de bulle qui ne touche ni Bounce (halo compris) ni une autre bulle."""
        best, best_d = cands[0], -1e9
        for (cx, cy) in cands:
            worst = 1e9
            for tt in (t, t + 0.25, t + 0.5):
                bx, by = self.bounce_at(tt)[:2]
                dx = max(abs(bx - cx) - bw / 2, 0.0)
                dy = max(abs(by - cy) - bh / 2, 0.0)
                worst = min(worst, math.hypot(dx, dy) - 1.6 * R)
            for (ox, oy, ow, oh) in others:
                if abs(ox - cx) < (ow + bw) / 2 + 6 and abs(oy - cy) < (oh + bh) / 2 + 6:
                    worst = min(worst, -500)
            if worst >= 0:
                return (cx, cy)
            if worst > best_d:
                best, best_d = (cx, cy), worst
        return best

    def draw_bubbles(self, dr, t, S, usher):
        placed = []
        for (_, key, _) in self.lines:
            win = self.narr_window(key)
            if win is None:
                continue
            a, b = win
            hold = max(1.0, b - a + 0.45)
            if not (a - 0.05 <= t <= a + hold):
                continue
            text = BUBBLE[key]
            heads, kind = self.speakers(key, t, usher)
            if not heads:
                continue
            big = kind == "group"
            fs = 92 if big else (60 if key.startswith("OUT") else 54)
            if key == "NOW":
                fs = 80
            if key == "SHH_B3":
                fs = 48
            if key == "SHH_FILM":
                fs = 72
            f = font(int(fs * S))
            tw = f.getbbox(text)[2] / S
            bw, bh = tw + 50, fs * 1.35
            pop = smooth((t - a + 0.05) / 0.12)
            # la place de la bulle se décide à son apparition et ne bouge plus
            mem = self._bubble_pos.get(key) if hasattr(self, "_bubble_pos") else None
            if not hasattr(self, "_bubble_pos"):
                self._bubble_pos = {}
            if big:
                if mem is None:
                    if key == "SHH_ALL":
                        cands = [(x, y) for y in (930.0, 1000.0, 860.0) for x in (420.0, 560.0, 680.0)]
                    else:
                        cands = [(x, y) for y in (1010.0, 950.0, 1080.0) for x in (330.0, 400.0)]
                    mem = self._bubble_pos[key] = [self.clear_of_bounce(cands, bw, bh, a)]
                cx, cy = mem[0]
                if key == "SHH_USHER":
                    tails = [(cx - bw * 0.3, usher["head"][1] - 80)]
                else:
                    tails = [(hx, cy + bh / 2 + 34) for hx in (cx - bw * 0.3, cx, cx + bw * 0.3)]
                self.bubble(dr, cx, cy, bw, bh, tails, text, f, S, pop, short=True,
                            aim=(usher["head"] if key == "SHH_USHER" else None))
                placed.append((cx, cy, bw, bh))
                continue
            if kind == "usher":
                hx, hy = heads[0]
                cands = [(max(bw / 2 + 20, min(hx + dx, 925 - bw / 2)), hy + dy) for (dx, dy) in
                         ((120, -150), (60, -230), (160, -90), (60, -310))]
            elif kind == "film":
                hx, hy = heads[0]
                cands = [(min(hx - 110, SCREEN[2] - bw / 2 - 20), hy + 20)]
            else:
                cands = None
            if kind == "single":
                if mem is None:
                    mem = []
                    for (hx, hy) in heads:
                        c = [(max(bw / 2 + 20, min(hx + dx, 925 - bw / 2)), hy + dy) for (dx, dy) in
                             ((30, -70), (-60, -70), (100, -40), (-120, -40), (20, -150), (-200, -20), (200, -20), (-260, 40))]
                        pos = self.clear_of_bounce(c, bw, bh, a, placed)
                        placed.append((pos[0], pos[1], bw, bh))
                        mem.append(pos)
                    self._bubble_pos[key] = mem
                for (hx, hy), (cx, cy) in zip(heads, mem):
                    self.bubble(dr, cx, cy, bw, bh, [(hx, hy)], text, f, S, pop)
                continue
            if mem is None:
                mem = self._bubble_pos[key] = [self.clear_of_bounce(cands, bw, bh, a)]
            cx, cy = mem[0]
            self.bubble(dr, cx, cy, bw, bh, heads, text, f, S, pop)

    def bubble(self, dr, cx, cy, bw, bh, tails, text, f, S, pop, short=False, aim=None):
        def P(v):
            return v * S
        k = 0.6 + 0.4 * pop
        bw, bh = bw * k, bh * k
        white = (246, 246, 246)
        if aim is not None:
            ux, uy = aim
            dx, dy = ux - cx, uy - cy
            d = math.hypot(dx, dy) + 1e-6
            L = min(d - 60, 170)
            tip = (cx + dx / d * L, cy + dy / d * L)
            nx, ny = -dy / d, dx / d
            dr.polygon([(P(cx + nx * 30), P(cy + ny * 30)), (P(cx - nx * 30), P(cy - ny * 30)), (P(tip[0]), P(tip[1]))], fill=white)
        else:
            for (hx, hy) in tails:
                ax = max(cx - bw / 2 + 24, min(cx + bw / 2 - 24, hx))
                if short:
                    dr.polygon([(P(ax - 14), P(cy + bh / 2 - 4)), (P(ax + 14), P(cy + bh / 2 - 4)), (P(hx), P(hy))], fill=white)
                else:
                    tip_y = hy - 4 if hy - 4 > cy else cy + bh / 2 + 24
                    dr.polygon([(P(ax - 16), P(cy + bh / 2 - 4)), (P(ax + 16), P(cy + bh / 2 - 4)), (P(hx), P(tip_y))], fill=white)
        dr.rounded_rectangle([P(cx - bw / 2), P(cy - bh / 2), P(cx + bw / 2), P(cy + bh / 2)], radius=int(P(bh * 0.4)), fill=white)
        dr.text((P(cx), P(cy)), text, fill=(12, 12, 16), anchor="mm", font=f if pop >= 1 else font(int(f.size * k)))


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4,
            "hook_top": 0.05, "hook_font_size": 92, "hero_win": ""}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
