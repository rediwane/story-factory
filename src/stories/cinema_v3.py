"""
Cinéma, v3. Une salle de cinéma dans le noir, vue de dos. Bounce rebondit sur le dossier de son
siège et dit son nom à chaque contact dur. L'ouvreur a une règle : ce que sa lampe éclaire (la
tache s'arrête au moins 0,5 s dessus) sort. La tache arrive toujours un rien trop tard sur Bounce
et tombe sur ceux qui lui font « chut » : un, deux, puis toute la salle (qui a fait « chut » à
l'ouvreur), la doudoune où il se cache, le personnage du film (Bounce envoie la lampe en l'air),
et enfin le spectateur de la vidéo (la lampe retombe braquée sur nous). Bounce saute sur la lampe,
qui s'éteint.

Tout est calculé d'avance sur une horloge : les contacts de Bounce (arcs paraboliques exacts sous
G = 2600 entre deux contacts, dans le temps « physique » tau, qui ralentit au tiers pendant le
ralenti), les poses des spectateurs, l'ouvreur et la tache de lumière (clés). Les répliques
viennent d'une banque de voix hors dépôt (cfg["voice_bank"]), passées au moteur comme répliques du
narrateur ; aucun sous-titre du moteur : chaque réplique est dessinée dans une bulle, dans la
bande y 1000-1260.

Nouveau script : base.py n'est pas modifié. Ce module remplace, pour lui seul, quelques fonctions
de base (voix de l'accroche lancée à 0,00, réverbération par FFT, sous-titres).

    python3 src/stories/cinema_v3.py configs/<name>.json [--simulate]
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
    "SHH_B2": "shh_b3.wav", "OUT_1": "out_you.wav", "SHH_PAIR": "shh_2b.wav", "OUT_TWO": "out_two.wav",
    "SHH_USHER": "shh_usher.wav", "OUT_ALL": "out_all.wav", "OUT_COAT": "out_you2.wav",
    "OUT_FILM": "out_film.wav", "SHH_FILM": "shh_film.wav", "OUT_YOU": "out_you.wav",
}
BUBBLE = {
    "SHH_B2": "SHH!", "OUT_1": "YOU. OUT.", "SHH_PAIR": "SHH!", "OUT_TWO": "YOU TWO. OUT.",
    "SHH_USHER": "SHHHH!", "OUT_ALL": "EVERYONE. OUT.", "OUT_COAT": "YOU. OUT.", "OUT_FILM": "YOU. OUT.",
    "SHH_FILM": "shh.", "OUT_YOU": "YOU. OUT.",
}
LINES = [(2.35, "SHH_B2"), (4.40, "OUT_1"), (11.27, "SHH_PAIR"), (13.50, "OUT_TWO"), (22.45, "SHH_USHER"),
         (24.75, "OUT_ALL"), (36.75, "OUT_COAT"), (48.75, "OUT_FILM"), (53.10, "SHH_FILM"), (60.75, "OUT_YOU")]
OUT_KEYS = ("OUT_1", "OUT_TWO", "OUT_ALL", "OUT_COAT", "OUT_FILM", "OUT_YOU")
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

# ------------------------------------------------------------------ la voix de l'accroche, lancée à 0,00
_hook_memo = {}


def hook_audio_v3(cfg):
    """L'accroche lue par la voix du narrateur, coupée au plus près du son (elle démarre à 0,00)."""
    if not (cfg["hook_voice"] and cfg["hook_text"]):
        return None
    key = (cfg["hook_text"], cfg["narrator_voice"], cfg["narrator_length"])
    if key not in _hook_memo:
        x = _orig_say(cfg["hook_text"], cfg["narrator_voice"], cfg["narrator_length"], SR)
        if x is None or not len(x):
            _hook_memo[key] = None
        else:
            a = np.abs(x)
            idx = np.where(a > 0.02 * a.max())[0]
            x = x[max(0, idx[0] - int(0.01 * SR)):idx[-1] + int(0.03 * SR)].copy()
            n = int(0.02 * SR)
            x[-n:] *= np.linspace(1, 0, n)
            _hook_memo[key] = x
    v = _hook_memo[key]
    return None if v is None else v.copy()


base.hook_audio = hook_audio_v3
_orig_place = base.place_words


def place_words_v3(events, total_dur, cfg, *a, **k):
    """Le moteur réserve l'accroche de 0 à 0,15 + durée + 0,1 ; elle démarre ici à 0,00."""
    hv = cfg.get("_hook_voice")
    if hv is not None:
        cfg2 = dict(cfg)
        cfg2["_hook_voice"] = hv[int(0.15 * SR):]
        return _orig_place(events, total_dur, cfg2, *a, **k)
    return _orig_place(events, total_dur, cfg, *a, **k)


base.place_words = place_words_v3


def reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    """Même réverbération que base.reverb, par FFT (np.convolve est trop lent sous charge)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    N = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = reverb_fft


def render_audio_v3(events, total_dur, cfg, path, payoff_t=None, mood=None, narr=(), replies=()):
    """base.render_audio, à deux différences près : l'accroche est posée à 0,00 (au lieu de 0,15)
    et la réverbération passe par la FFT."""
    sr = ak.SR
    buf = np.zeros(int((total_dur + 2.0) * sr))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(events, total_dur, cfg, payoff_t, None, narr, replies, name_len=len(name) / sr)
        for (t0, kind, _d, tag) in words:
            if kind == "hit":
                ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=cfg["hero_gain"])
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
            ak.add(buf, v, 0.0, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said, "reaction": None}


base.render_audio = render_audio_v3

# ------------------------------------------------------------------ le mot de Bounce
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    if not text:
        return None
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
R = 110.0
SCREEN = (230.0, 472.0, 900.0, 790.0)
FILM_W, FILM_H = 820.0, 410.0                     # le film est dessiné à cette taille, puis réduit
FK = (SCREEN[2] - SCREEN[0]) / FILM_W
FKY = (SCREEN[3] - SCREEN[1]) / FILM_H
DOOR = (125.0, 600.0, 215.0, 790.0)
AISLE_X = 175.0
ROW_Y = {"A": 880.0, "B": 1030.0, "C": 1190.0}
SEATS = [330.0, 490.0, 650.0, 810.0]
HOME = (650.0, ROW_Y["C"] - R)
C4B = (810.0, ROW_Y["C"] - R)
C1B = (330.0, ROW_Y["C"] - R)
B3B = (650.0, ROW_Y["B"] - R)
COAT = (810.0, 1048.0)
POTX, POT_BASE, POT_HT = 490.0, ROW_Y["C"], 118.0
POTP = (POTX, POT_BASE - POT_HT - R + 30.0)
LAMP_B4 = (810.0, ROW_Y["B"] - 14.0)
LAMP_C3 = (650.0, ROW_Y["C"] - 14.0)
LAMPHIT = (530.0, 862.0)
TRAP_SPOT = (650.0, 1245.0)

BG = (8, 8, 12)
WALL = (16, 14, 22)
SEAT_COL = (74, 22, 36)
SEAT_EDGE = (112, 40, 58)
BEAM = (255, 226, 150)
USHER_COL = (122, 28, 40)
GOLD = (220, 175, 70)
FILM_BG = (92, 106, 136)
FILM_FLOOR = (64, 74, 100)
INKF = (12, 12, 18)
POP = (250, 236, 178)
SPOT_RX, SPOT_RY = 70.0, 52.0

# temps
T_SLOW0, T_SLOW1, SLOWK = 59.45, 60.25, 1.0 / 3.0
T_LAMP1, T_LAMP1_LAND, T_LAMP1_AIM = 46.90, 47.90, 48.15
T_LAMP2, T_LAMP2_LAND = 59.25, 60.25
T_QUIET = 1.45
T_EXIT_SIGN = 4.40
T_SILENCE_SUB = 53.90
T_ISSUE = 60.75
T_OFF = 62.52
T_SMILE = 62.55
T_END = 63.55
T_FLASH = 47.30


def tau(t):
    if t <= T_SLOW0:
        return t
    if t <= T_SLOW1:
        return T_SLOW0 + (t - T_SLOW0) * SLOWK
    return t - (T_SLOW1 - T_SLOW0) * (1 - SLOWK)


def lerp(a, b, s):
    return a + (b - a) * s


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def row_scale(yb):
    return 0.76 + (yb - ROW_Y["A"]) / (ROW_Y["C"] - ROW_Y["A"]) * 0.24


def keyval(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            if t1 - t0 < 1e-9:
                return v1
            u = smooth((t - t0) / (t1 - t0))
            if isinstance(v0, tuple):
                return tuple(lerp(a, b, u) for a, b in zip(v0, v1))
            return lerp(v0, v1, u)
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
# (t écran, x, y, dur ?, durée du contact mou, enfoncement, quoi)
def contacts():
    C = []

    def h(t, p, dx=0.0, what="seat"):
        C.append((t, p[0] + dx, p[1], True, 0.0, 0.0, what))

    def s(t, p, dur=0.12, depth=36.0, what="coat"):
        C.append((t, p[0], p[1], False, dur, depth, what))
    C.append((-0.90, HOME[0], HOME[1], False, 0.0, 0.0, "virtual"))
    s(0.30, COAT)
    h(1.45, HOME); s(2.50, COAT); h(3.45, HOME, -6); s(4.50, COAT)
    for k, t in enumerate((5.45, 6.68, 7.91, 9.14, 10.37)):
        h(t, HOME, (-8, 6, -4, 8, 0)[k])
    s(11.40, COAT, 0.60, 150, "hide")
    h(12.40, HOME); s(13.50, COAT)
    for k, t in enumerate((14.45, 15.63, 16.85, 18.07, 19.29)):
        h(t, HOME, (6, -6, 4, -8, 0)[k])
    s(20.20, COAT, 0.10, 46)
    h(21.45, HOME); s(22.65, COAT); h(23.85, HOME); s(24.75, COAT)
    for k, t in enumerate((25.75, 27.00, 28.25, 29.50, 30.60, 31.70, 32.80, 33.90, 34.85, 35.80)):
        h(t, HOME, (0, -8, 6, -4, 8, -6, 4, -8, 6, 0)[k])
    s(36.05, COAT, 1.35, 150, "hide")
    h(37.50, C4B)
    h(38.60, HOME); h(39.70, C4B); h(40.80, HOME); h(41.90, C1B)
    s(42.85, POTP, 0.12, 30, "pot")
    h(43.80, HOME); h(44.90, C4B); h(45.95, C4B, -10)
    s(46.60, POTP, 0.08, 26, "pot")
    h(T_LAMP1, LAMPHIT, what="lamp")
    s(47.15, POTP, 0.10, 24, "pot")
    h(47.85, HOME); s(48.80, POTP, 0.12, 26, "pot")
    for k, t in enumerate((49.75, 50.97, 52.19)):
        h(t, HOME, (0, -6, 6)[k])
    s(53.15, POTP, 0.12, 24, "pot")
    for k, t in enumerate((54.10, 55.32, 56.54, 57.50)):
        h(t, HOME, (4, -6, 6, 0)[k])
    h(58.40, HOME, 10)
    h(T_LAMP2, (LAMP_B4[0], LAMP_B4[1] - 14 - R), what="lamp")
    s(60.70, POTP, 0.12, 24, "pot")
    h(61.50, C4B)
    h(T_OFF, (LAMP_C3[0], LAMP_C3[1] - 14 - R), what="lampoff")
    C.append((63.70, HOME[0] + 90, HOME[1], False, 0.0, 0.0, "virtual"))
    return C


class Sim:
    scene_top = 0.245

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
        self.make_arcs()
        self.lines = [(t, key, key) for (t, key) in LINES]
        self.build_people()
        self.build_popcorn(rng)
        self.dust = [(float(rng.uniform(0, W)), float(rng.uniform(40, 440)), float(rng.uniform(0, 6.28)),
                      float(rng.uniform(1.5, 3.5))) for _ in range(40)]
        self._bubble_pos = {}

    # ------------------------------------------------------------------ Bounce
    def make_arcs(self):
        C = self.C
        self.arcs = []
        self.arc_warn = []
        for a, b in zip(C, C[1:]):
            t0 = tau(a[0]) + a[4]
            t1 = tau(b[0])
            T = t1 - t0
            x0, y0, x1, y1 = a[1], a[2], b[1], b[2]
            vy0 = (y1 - y0 - 0.5 * G * T * T) / T
            top = y0 - (vy0 * vy0 / (2 * G) if vy0 < 0 else 0)
            if top < 540 and a[0] > 0:
                self.arc_warn.append((a[0], b[0], round(top)))
            self.arcs.append((t0, t1, x0, y0, x1, y1, vy0, b))

    def bounce_at(self, t):
        """(x, y, contact mou en cours (quoi, u, enfoncement) ou None)"""
        T = tau(t)
        for c in self.C:
            tc = tau(c[0])
            if c[4] > 0 and tc <= T <= tc + c[4]:
                u = (T - tc) / c[4]
                sn = max(0.0, math.sin(math.pi * u))
                d = c[5] * sn if c[5] < 100 else c[5] * sn ** 0.35
                return c[1], c[2] + d, (c[6], u, c[5])
        for (t0, t1, x0, y0, x1, y1, vy0, nxt) in self.arcs:
            if t0 <= T <= t1:
                dt = T - t0
                return lerp(x0, x1, dt / (t1 - t0)), y0 + vy0 * dt + 0.5 * G * dt * dt, None
        c = self.C[-1]
        return c[1], c[2], None

    def hidden(self, t):
        """Bounce est caché dans la doudoune (elle s'est refermée sur lui)."""
        b = self.bounce_at(t)
        if b[2] is None or b[2][0] != "hide":
            return False
        u, depth = b[2][1], b[2][2]
        return depth * max(0.0, math.sin(math.pi * u)) ** 0.35 > 75

    def in_pot(self, t):
        b = self.bounce_at(t)
        return b[2] is not None and b[2][0] == "pot"

    # ------------------------------------------------------------------ les spectateurs
    def build_people(self):
        cols = {"A1": (176, 142, 70), "A2": (84, 112, 176), "A3": (138, 94, 172), "A4": (86, 146, 104),
                "B1": (184, 106, 64), "B2": (70, 104, 196), "B3": (58, 146, 150), "B4": (156, 82, 126),
                "C1": (130, 136, 72), "C2": (74, 160, 92)}
        shapes = {"A1": "bun", "B1": "cap", "A4": "small", "B4": "tail", "C1": "cap", "A2": "tall", "B3": "round"}
        P = {}
        for row in "ABC":
            for i, x in enumerate(SEATS):
                pid = f"{row}{i + 1}"
                if row == "C" and i >= 2:
                    continue
                P[pid] = {"id": pid, "row": row, "x0": x, "col": cols[pid], "shape": shapes.get(pid, "round"),
                          "stand": [(0.0, 0.0)], "gest": [], "path": None, "gone": 99.0, "run": False}
        self.P = P

        def up(pid, t, v=1.0, d=0.22):
            P[pid]["stand"].append((t, P[pid]["stand"][-1][1]))
            P[pid]["stand"].append((t + d, v))

        def gest(pid, t0, t1, kind, target=None):
            P[pid]["gest"].append((t0, t1, kind, target))
        bounce = lambda t: self.bounce_at(t)[:2]
        coat = lambda t: (COAT[0], COAT[1] + 40)
        usher_head = lambda t: self.usher_at(t)["head"]
        # 1. B2 fait chut, se fait prendre, sort plié en deux à petits pas
        up("B2", 2.35); gest("B2", 2.35, 5.45, "shh", bounce)
        self.walk_out(P["B2"], 5.45, row_v=230.0, aisle_v=220.0, crouch=-0.55)
        # 2. A1 et A2 le dénoncent, sortent de côté par l'avant
        for pid in ("A1", "A2"):
            up(pid, 10.40); gest(pid, 10.40, 11.40, "point", bounce); gest(pid, 11.40, 13.50, "point", coat)
        self.walk_out(P["A1"], 14.41, row_v=200.0, aisle_v=200.0, crouch=1.0)
        self.walk_out(P["A2"], 14.55, row_v=330.0, aisle_v=200.0, crouch=1.0)
        # 3. les sept : ils s'enfoncent, puis font chut à l'ouvreur, puis sortent en courant
        rest = ["A3", "A4", "B1", "B3", "B4", "C1", "C2"]
        for pid in rest:
            P[pid]["stand"] += [(15.63, 0.0), (15.9, -0.35)]
            gest(pid, 15.9, 21.9, "mouth")
            up(pid, 21.90)
            gest(pid, 21.90, 23.85, "shh", usher_head)
        delays = {"A3": 0.0, "A4": 0.12, "B1": 0.06, "B3": 0.3, "B4": 0.42, "C1": 0.36, "C2": 0.75}
        for pid in rest:
            P[pid]["run"] = True
            self.walk_out(P[pid], 25.75 + delays[pid], row_v=720.0, aisle_v=620.0, crouch=1.0)

    def walk_out(self, p, t0, row_v, aisle_v, crouch):
        yb = ROW_Y[p["row"]]
        x_end = AISLE_X + 60.0
        t_row = t0 + (p["x0"] - x_end) / row_v
        te = t_row + 0.12
        t_door = te + (yb - DOOR[3]) / aisle_v
        p["stand"].append((t0, keylin(p["stand"], t0))); p["stand"].append((t0 + 0.15, crouch))
        p["path"] = [(t0, p["x0"], yb, "row"), (t_row, x_end, yb, "row"), (te, AISLE_X, yb, "aisle"),
                     (t_door, AISLE_X, DOOR[3], "aisle")]
        p["gone"] = t_door + 0.12
        p["door"] = t_door

    def person_at(self, p, t):
        """x, yb, lieu ('row'/'aisle'), debout (-0.55..1) ; None une fois sorti."""
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

    def head_of(self, p, t):
        st = self.person_at(p, t)
        if st is None:
            return None
        x, yb, where, a = st
        Rh = 58.0 * row_scale(yb)
        hy = yb - 0.8 * Rh - 1.9 * Rh * max(0.0, a) + 0.75 * Rh * max(0.0, -a) - self.jolt(t, yb)
        return (x, hy, Rh)

    def jolt(self, t, yb):
        if T_QUIET <= t < T_QUIET + 0.38:
            return 20 * row_scale(yb) * math.sin(math.pi * (t - T_QUIET) / 0.38)
        return 0.0

    # ------------------------------------------------------------------ l'ouvreur
    def usher_at(self, t):
        """x, pieds (yb), lieu ('aisle' / 'rows' entre B et C / 'front' devant la rangée A), tête,
        épaule, main de la lampe, lampe tenue ?, pouce levé ?, taille."""
        if t < 29.6:
            x, yb, where = AISLE_X, 1200.0, "aisle"
        elif t < 31.0:
            u = smooth((t - 29.6) / 1.4)
            x, yb, where = lerp(AISLE_X, 540.0, u), 1180.0, ("aisle" if u < 0.25 else "rows")
        elif t < 35.6:
            x, yb, where = 540.0 + 30 * math.sin((t - 31.0) * 1.3), 1180.0, "rows"
        elif t < 37.4:
            x, yb, where = lerp(540.0 + 30 * math.sin(4.6 * 1.3), 700.0, smooth((t - 35.6) / 1.2)), 1180.0, "rows"
        elif t < 38.6:
            x, yb, where = 700.0, 1180.0, "rows"
        elif t < 44.4:
            x, yb, where = keyval([(38.6, 700.0), (39.6, 620.0), (41.2, 560.0), (42.3, 540.0), (44.4, 545.0)], t), 1180.0, "rows"
        else:
            x = keyval([(47.9, 545.0), (49.0, 330.0), (57.0, 330.0), (58.6, 690.0), (59.35, 690.0), (60.3, 330.0)], t)
            yb, where = 1180.0, "rows"
        s = row_scale(min(yb, 1190.0)) if yb < 1190 else 1.0
        Ru = 62.0 * s
        size = 1.0
        if 23.30 <= t < 23.85:
            size = lerp(1.0, 0.86, smooth((t - 23.30) / 0.25))
        elif 23.85 <= t < 24.4:
            size = lerp(0.86, 1.07, smooth((t - 23.85) / 0.3))
        elif t >= 24.4:
            size = 1.07
        bend = 0.0
        if 58.0 <= t < 59.6:
            bend = 0.5 * smooth((t - 58.0) / 1.2) * (1 - smooth((t - T_LAMP2) / 0.15))
        head = (x + 1.2 * Ru * bend, yb - 5.4 * Ru * size + 1.3 * Ru * bend)
        shoulder = (x + 0.95 * Ru, yb - 4.3 * Ru * size + 1.0 * Ru * bend)
        holding = t < T_LAMP1
        arm_len = 1.9 * Ru
        sp = self.spot_raw(t)
        if 44.4 <= t < T_LAMP1:
            # le piège : la lampe tenue haut, braquée vers le bas
            up = smooth((t - 44.4) / 0.5)
            dn = (shoulder[0] + 0.3 * Ru, shoulder[1] + 1.4 * Ru)
            hand = (lerp(dn[0], 540.0, up), lerp(dn[1], 748.0, up))
        elif holding and sp is not None:
            dx, dy = sp[0] - shoulder[0], sp[1] - shoulder[1]
            d = math.hypot(dx, dy) + 1e-6
            hand = (shoulder[0] + dx / d * arm_len, shoulder[1] + dy / d * arm_len)
        elif 58.0 <= t < 59.6:
            k = smooth((t - 58.0) / 1.2)
            hand = (lerp(shoulder[0] + 0.3 * Ru, LAMP_B4[0] - 52, k),
                    lerp(shoulder[1] + 1.3 * Ru, LAMP_B4[1] - 10, k))
        else:
            hand = (shoulder[0] + 0.25 * Ru, shoulder[1] + 1.3 * Ru)
        thumb = None
        for key in OUT_KEYS:
            w = self.line_window(key)
            if w is not None and w[0] - 0.15 <= t <= w[0] + 1.25:
                thumb = (key, w[0] - 0.15)
        if t >= T_ISSUE - 0.2:
            thumb = ("OUT_YOU", T_ISSUE - 0.2)
        return {"x": x, "yb": yb, "where": where, "s": s, "R": Ru, "size": size, "head": head,
                "shoulder": shoulder, "hand": hand, "holding": holding, "thumb": thumb, "bend": bend}

    def line_window(self, key):
        for n in self.narr:
            if n["key"] == key:
                return n["start"], n["end"]
        for (tt, k) in LINES:
            if k == key:
                return tt, tt + len(BANK.get(k, np.zeros(int(0.6 * SR)))) / SR
        return None

    # ------------------------------------------------------------------ la tache de lumière
    def spot_raw(self, t):
        """Centre de la tache tant que l'ouvreur tient la lampe, ou None."""
        if t >= T_LAMP1:
            return None
        P = self.P

        def head(pid, tt, dy=0.0):
            hd = self.head_of(P[pid], tt)
            if hd is None:
                return (AISLE_X + 30, DOOR[3] - 80)
            return (hd[0], hd[1] + dy)

        def feet(tt):
            u = self.usher_feet(tt)
            return (u[0] + 70, u[1] + 30)
        seated_A = ROW_Y["A"] - 0.8 * 58 * row_scale(ROW_Y["A"])
        faceC = 1245.0
        if t < 1.45:
            return (keyval([(0.0, (290.0, seated_A)), (1.45, (450.0, seated_A))], t))
        if t < 5.25:
            return keyval([(1.45, (450.0, seated_A)), (2.3, (330.0, 990.0)), (3.0, (360.0, 960.0)),
                           (3.85, head("B2", 3.85))], t) if t < 3.85 else head("B2", t)
        if t < 8.0:
            if t < 5.25:
                return head("B2", t)
            hx, hy = head("B2", t)
            k = smooth((t - 5.25) / 0.3)
            return (lerp(hx, min(hx, 340.0), k), hy)
        if t < 11.45:
            return keyval([(8.0, head("B2", 7.99)), (8.8, (260.0, seated_A)), (9.9, (420.0, seated_A)),
                           (10.9, (360.0, seated_A)), (11.45, (400.0, seated_A))], t)
        if t < 11.75:
            return keyval([(11.45, (400.0, seated_A)), (11.58, (COAT[0], COAT[1] + 70)), (11.75, (COAT[0], COAT[1] + 70))], t)
        if t < 12.15:
            return keyval([(11.75, (COAT[0], COAT[1] + 70)), (12.15, head("A1", 12.15))], t)
        if t < 12.75:
            return head("A1", t)
        if t < 12.95:
            return keyval([(12.75, head("A1", 12.75)), (12.95, head("A2", 12.95))], t)
        if t < 16.1:
            return head("A2", t) if self.person_at(P["A2"], t) is not None else (AISLE_X + 20, DOOR[3] - 60)
        if t < 20.2:
            return keyval([(16.1, (AISLE_X + 20, DOOR[3] - 60)), (16.9, (300.0, faceC)), (18.1, (470.0, faceC)),
                           (19.2, (320.0, faceC)), (20.2, (430.0, 1150.0))], t)
        if t < 20.75:
            return keyval([(20.2, (430.0, 1150.0)), (20.5, (360.0, 800.0)), (20.75, self.film_wall_spot())], t)
        if t < 23.30:
            return self.film_wall_spot()
        if t < 23.6:
            return keyval([(23.30, self.film_wall_spot()), (23.6, feet(23.6))], t)
        if t < 31.0:
            return feet(t)
        if t < 36.10:
            return self.chase_spot(t)
        if t < 37.18:
            return keyval([(36.10, self.chase_spot(36.0999)), (36.22, (COAT[0], COAT[1] + 60))], t)
        if t < 38.6:
            return keyval([(37.18, (COAT[0], COAT[1] + 60)), (37.36, (330.0, 1180.0)), (38.6, (330.0, 1180.0))], t)
        if t < 44.4:
            return self.chase_spot(t)
        return keyval([(44.4, self.chase_spot(44.4)), (44.9, TRAP_SPOT)], t)

    def usher_feet(self, t):
        if t < 29.6:
            return (AISLE_X, 1200.0)
        u = self.usher_x_simple(t)
        return (u, 1200.0)

    def usher_x_simple(self, t):
        if t < 29.6:
            return AISLE_X
        if t < 31.0:
            return lerp(AISLE_X, 540.0, smooth((t - 29.6) / 1.4))
        return 540.0

    def chase_spot(self, t):
        """La tache court sur les dossiers de la rangée C, un temps derrière Bounce : elle arrive
        sur le dossier qu'il vient de quitter, et en repart avant qu'il n'y revienne."""
        y = 1245.0
        if t < 36.10:
            # 31,0 -> 36,1 : Bounce rebondit sur C3 ; la tache vient sur C3 juste après chaque départ,
            # et repart vers C2 / C1 avant chaque retour.
            hits = [30.60, 31.70, 32.80, 33.90, 34.85, 35.80]
            L, M = (420.0, y), (650.0, y)
            prev = max([h for h in hits if h <= t], default=None)
            if prev is None:
                return keyval([(31.0, (self.usher_x_simple(31.0) + 70, 1230.0)), (31.3, L)], t)
            nxt = min([h for h in hits if h > t], default=prev + 1.0)
            return keyval([(prev, L), (prev + 0.30, M), (prev + 0.50, M), (max(prev + 0.55, nxt - 0.38), L)], t)
        # 38,6 -> 44,4 : il change de siège
        keys = [(38.6, (330.0, 1180.0)), (38.9, (810.0, y)), (39.3, (810.0, y)), (39.75, (650.0, y)),
                (40.05, (650.0, y)), (40.45, (810.0, y)), (41.0, (810.0, y)), (41.35, (650.0, y)),
                (42.2, (650.0, y)), (42.85, (700.0, y)), (43.0, (820.0, 700.0)), (43.3, (760.0, 600.0)),
                (43.6, (300.0, 650.0)), (44.0, (330.0, y)), (44.4, (330.0, y))]
        return keyval(keys, t)

    def film_wall_spot(self):
        return (548.0, 505.0)

    def spot(self, t):
        """La tache dessinée (centre) tant que la lampe est tenue."""
        return self.spot_raw(t)

    # ------------------------------------------------------------------ la lampe
    def lamp_state(self, t):
        """(x, y, angle du faisceau, allumée, « face à nous »)."""
        if t < T_LAMP1:
            u = self.usher_at(t)
            hx, hy = u["hand"]
            sp = self.spot(t)
            ang = math.atan2(sp[1] - hy, sp[0] - hx) if sp is not None else math.pi / 2
            return hx, hy, ang, True, False
        if t < T_LAMP1_LAND:
            x0, y0 = 540.0, 748.0
            x1, y1 = LAMP_B4
            T = T_LAMP1_LAND - T_LAMP1
            dt = t - T_LAMP1
            vy0 = (y1 - y0 - 0.5 * G * T * T) / T
            vy0 = min(vy0, -900.0) if False else vy0
            x = lerp(x0, x1, dt / T)
            y = y0 + vy0 * dt + 0.5 * G * dt * dt
            a1 = self.film_aim(T_LAMP1_AIM) + 4 * math.pi
            return x, y, lerp(math.pi / 2, a1, 1 - (1 - dt / T) ** 1.5), True, False
        if t < T_LAMP2:
            x, y = LAMP_B4
            aim = self.film_aim(t)
            if t < T_LAMP1_AIM:
                aim += 0.35 * math.sin((t - T_LAMP1_LAND) * 30) * (1 - (t - T_LAMP1_LAND) / (T_LAMP1_AIM - T_LAMP1_LAND))
            return x, y, aim, True, False
        if t < T_LAMP2_LAND:
            x0, y0 = LAMP_B4
            x1, y1 = LAMP_C3
            T = tau(T_LAMP2_LAND) - tau(T_LAMP2)
            dt = tau(t) - tau(T_LAMP2)
            vy0 = (y1 - y0 - 0.5 * G * T * T) / T
            x = lerp(x0, x1, dt / T)
            y = y0 + vy0 * dt + 0.5 * G * dt * dt
            u = dt / T
            return x, y, self.film_aim(T_LAMP2) + u * 3 * math.pi, True, u > 0.85
        return LAMP_C3[0], LAMP_C3[1], math.pi / 2, t < T_OFF, True

    def film_aim(self, t):
        sp = self.film_spot_img(t)
        return math.atan2(sp[1] - LAMP_B4[1], sp[0] - LAMP_B4[0])

    # ------------------------------------------------------------------ le film
    def film_state(self, t):
        """x (coordonnées du film), tourné (0 profil -> 1 face), pose."""
        hits = self.hits
        frozen = t < T_QUIET or any(h <= t < h + 0.5 for h in hits)
        speed = 2.5

        def moving_until(tt):
            return max(0.0, tt - T_QUIET) - sum(max(0.0, min(tt, h + 0.5) - h) for h in hits if T_QUIET <= h < tt)
        stop_at = T_LAMP1
        x = 170.0 + speed * moving_until(min(t, stop_at))
        x_lit = 170.0 + speed * moving_until(stop_at)
        turn = 0.0
        pose = "tiptoe"
        if t < T_QUIET:
            pose = "tiptoe_frozen"
        elif frozen:
            pose = "freeze"
        if t >= stop_at:
            x = x_lit
            pose = "freeze"
        walk = 0.0
        door_x = 690.0
        if t >= 49.30:
            pose = "stand"
        if t >= 49.75:
            u = clamp01((t - 49.75) / 1.8)
            x = lerp(x_lit, door_x, u)
            pose = "walk" if t < 51.55 else "stand"
            walk = (t - 49.75) * 3.2
        if t >= 52.30:
            turn = smooth((t - 52.30) / 0.3)
            pose = "shh" if t >= 52.5 else "stand"
        if t >= 53.45:
            turn = 1 - smooth((t - 53.45) / 0.15)
            pose = "walk"
            x = door_x + (t - 53.45) * 260
            walk = (t - 53.45) * 6
        phase = moving_until(t) * 2.2
        return {"x": x, "turn": turn, "pose": pose, "phase": phase if pose != "walk" else walk}

    def film_to_img(self, u, v):
        return (SCREEN[0] + u * FK, SCREEN[1] + v * FKY)

    def img_to_film(self, x, y):
        return ((x - SCREEN[0]) / FK, (y - SCREEN[1]) / FKY)

    def film_spot_img(self, t):
        fs = self.film_state(max(t, T_LAMP1_AIM))
        u = fs["x"]
        if t >= 53.6:
            u = 690.0
        return self.film_to_img(u, 200.0)

    def film_door(self, t):
        if t < 51.40:
            return 0.0
        if t < 51.75:
            return smooth((t - 51.40) / 0.35)
        if t < 53.60:
            return 1.0
        return 1.0 - smooth((t - 53.60) / 0.3)

    def draw_film(self, t, S, bx, by, film_spot):
        img = Image.new("RGB", (int(FILM_W * S), int(FILM_H * S)), FILM_BG)
        d = ImageDraw.Draw(img, "RGBA")

        def P(v):
            return v * S
        d.rectangle([0, P(330), P(FILM_W), P(FILM_H)], fill=FILM_FLOOR)
        for k in range(6):
            x = 60 + k * 140
            d.line([P(x), P(330), P(x - 90), P(FILM_H)], fill=(58, 66, 90), width=int(P(3)))
        d.rectangle([0, P(40), P(FILM_W), P(52)], fill=(80, 92, 120))
        dx0, dx1, dy0, dy1 = 640.0, 740.0, 120.0, 330.0
        op = self.film_door(t)
        d.rectangle([P(dx0 - 8), P(dy0 - 8), P(dx1 + 8), P(dy1)], fill=(52, 58, 78))
        if op > 0:
            d.rectangle([P(dx0), P(dy0), P(dx1), P(dy1)], fill=(236, 238, 246))
        fs = self.film_state(t)
        if t < 53.9:
            self.draw_silhouette(d, fs["x"], 330.0, fs, S)
        wdoor = (dx1 - dx0) * (1 - op)
        d.rectangle([P(dx0), P(dy0), P(dx0 + max(2.0, wdoor)), P(dy1)], fill=(34, 38, 54))
        if op < 0.5:
            d.ellipse([P(dx0 + wdoor - 18), P(222), P(dx0 + wdoor - 8), P(232)], fill=(150, 150, 170))
        if t >= T_SILENCE_SUB:
            d.text((P(FILM_W / 2), P(380)), "[ silence ]", fill=(232, 232, 240), anchor="mm", font=font(int(38 * S)))
        # l'ombre de Bounce
        if by + 60 < SCREEN[3] + R * 1.2:
            lx, ly = self.img_to_film(bx, by + 60)
            rx, ry = 1.25 * R / FK, 1.25 * R / FKY
            d.ellipse([P(lx - rx), P(ly - ry), P(lx + rx), P(ly + ry)], fill=(30, 34, 48, 205))
        # la tache sur l'écran
        if film_spot is not None:
            lx, ly = self.img_to_film(*film_spot[:2])
            rx, ry = film_spot[2] / FK, film_spot[3] / FKY
            d.ellipse([P(lx - rx), P(ly - ry), P(lx + rx), P(ly + ry)], fill=BEAM + (115,), outline=BEAM + (230,), width=int(P(4)))
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
        if pose in ("tiptoe", "tiptoe_frozen"):
            a = math.sin(ph) if pose == "tiptoe" else 0.8
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
        d.rounded_rectangle([P(x - bw), P(sh_y - 8), P(x + bw), P(hip_y + 6)], radius=int(P(14)), fill=INKF)
        aw = int(P(14))
        if pose == "freeze":
            arms = [((x - bw + 6, sh_y + 6), (x - 50, sh_y - 30), (x - 62, sh_y - 80)),
                    ((x + bw - 6, sh_y + 6), (x + 52, sh_y - 30), (x + 66, sh_y - 78))]
        elif pose in ("tiptoe", "tiptoe_frozen"):
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
        d.rectangle([P(x - 8), P(head_y + 14), P(x + 8), P(sh_y)], fill=INKF)
        d.ellipse([P(x - Rh), P(head_y - Rh), P(x + Rh), P(head_y + Rh)], fill=INKF)
        if turn < 0.95:
            nx = x + Rh * (1 - turn) * 0.92
            nsz = 9 * (1 - turn)
            d.polygon([(P(nx - 2), P(head_y - 6)), (P(nx + nsz), P(head_y + 4)), (P(nx - 2), P(head_y + 10))], fill=INKF)
        if pose == "shh":
            d.rounded_rectangle([P(x - 6), P(head_y - 4), P(x + 6), P(head_y + 30)], radius=int(P(5)), fill=(40, 40, 52))

    # ------------------------------------------------------------------ doudoune, pot, porte
    def coat_state(self, t):
        """None (sur le siège), ou (x, y, angle, échelle) quand elle est soulevée / lancée ; 'gone'."""
        if t < 37.40:
            return None
        if t < 37.60:
            u = smooth((t - 37.40) / 0.2)
            return (lerp(COAT[0], 770.0, u), lerp(1110.0, 930.0, u), 0.0, 1.0)
        if t < 38.50:
            T = 0.9
            dt = t - 37.60
            x0, y0, x1, y1 = 770.0, 930.0, (DOOR[0] + DOOR[2]) / 2, 700.0
            vy0 = (y1 - y0 - 0.5 * G * T * T) / T
            return (lerp(x0, x1, dt / T), y0 + vy0 * dt + 0.5 * G * dt * dt, dt * 7.0, lerp(1.0, 0.55, dt / T))
        return "gone"

    def pot_state(self, t):
        """'held' (dans la main du vert) ou (x, sommet) sur le dossier C2."""
        if t < 25.75:
            return "held"
        if t < 26.0:
            return "moving"
        return (POTX, POT_BASE - POT_HT)

    def pot_fill(self, t):
        fill = 1.0
        for (tt, f) in ((42.85, 0.7), (46.60, 0.55), (47.15, 0.45), (48.80, 0.35), (53.15, 0.25), (60.70, 0.15)):
            if t >= tt:
                fill = f
        return fill

    def door_open(self, t):
        v = 0.0
        for (a, b) in ((7.45, 8.30), (15.20, 16.40), (26.15, 28.05), (38.15, 38.80)):
            if a - 0.2 <= t <= b + 0.2:
                v = max(v, min(smooth((t - a + 0.2) / 0.22), 1 - smooth((t - b) / 0.2)))
        return v

    def build_popcorn(self, rng):
        self.pop = []
        for (t0, n, power, spread) in ((42.85, 40, 1.0, 1.0), (46.60, 14, 0.6, 0.6), (47.15, 10, 0.5, 0.5),
                                       (48.80, 12, 0.6, 0.6), (53.15, 10, 0.5, 0.5), (60.70, 8, 0.45, 0.5)):
            for _ in range(n):
                vx = float(rng.uniform(-420, 420)) * spread
                vy = -float(rng.uniform(800, 1600)) * power
                land = float(rng.uniform(1150, 1330))
                self.pop.append((t0, POTX + float(rng.uniform(-30, 30)), POT_BASE - POT_HT - 10, vx, vy, land,
                                 float(rng.uniform(0, 6))))
        self.usher_pop = [(float(rng.uniform(-0.9, 0.9)), float(rng.uniform(-0.3, 0.4))) for _ in range(9)]

    # ------------------------------------------------------------------ moteur
    def step(self, dt):
        evs = []
        # base.simulate date les événements du pas à son début (t - dt) : on attend que ce début
        # ait atteint le contact, pour que le mot parte sur l'image du contact, jamais avant (A9)
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi] <= self.t - dt + 1e-9:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and self.t >= T_ISSUE:
            self.payoff = True
            evs.append(("payoff", "le spectateur dehors"))
        if self.t >= T_END:
            self.done = True
        return evs

    def hero_mood(self):
        return None

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, snap, t, S):
        img = dr._image
        da = ImageDraw.Draw(img, "RGBA")

        def P(v):
            return v * S

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([P(x0), P(y0), P(x1), P(y1)], fill=col)
        bx, by, soft = self.bounce_at(t)
        usher = self.usher_at(t)
        lamp = self.lamp_state(t)
        sp = self.spot(t)
        # mur, rayons du projecteur, poussière
        rect(0, 470, W, H, WALL)
        for (x0, x1, tx0, tx1) in ((300, 420, 250, 390), (470, 610, 430, 590), (650, 780, 640, 790), (820, 940, 820, 900)):
            da.polygon([(P(x0), 0), (P(x1), 0), (P(tx1), P(SCREEN[1])), (P(tx0), P(SCREEN[1]))], fill=(170, 180, 220, 14))
        for (dx, dy, ph, r) in self.dust:
            x = (dx + 8 * math.sin(t * 0.4 + ph)) % W
            y = dy + 6 * math.sin(t * 0.3 + ph * 2)
            da.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=(200, 210, 240, 40))
        for k in range(5, 0, -1):
            col = tuple(int(WALL[i] + (60 - WALL[i]) * 0.17 * (6 - k)) for i in range(3))
            dr.rounded_rectangle([P(SCREEN[0] - 12 * k), P(SCREEN[1] - 8 * k), P(SCREEN[2] + 12 * k), P(SCREEN[3] + 8 * k)],
                                 radius=int(P(18)), fill=col)
        film_spot = None
        if sp is not None and sp[1] < SCREEN[3]:
            film_spot = (sp[0], sp[1], 80.0, 62.0)
        if T_LAMP1_AIM - 0.05 <= t < T_LAMP2:
            fsp = self.film_spot_img(t)
            film_spot = (fsp[0], fsp[1], 70.0, 105.0)
        film = self.draw_film(t, S, bx, by, film_spot)
        film = film.resize((int(P(SCREEN[2] - SCREEN[0])), int(P(SCREEN[3] - SCREEN[1]))), Image.LANCZOS)
        img.paste(film, (int(P(SCREEN[0])), int(P(SCREEN[1]))))
        # PLEASE BE QUIET : éteint jusqu'au premier « Bounce », puis clignote une fois
        on = t >= T_QUIET and not (T_QUIET + 0.14 <= t < T_QUIET + 0.26)
        sx0, sy0, sx1, sy1 = 395.0, 434.0, 735.0, 464.0
        if on:
            for k in range(3, 0, -1):
                da.rounded_rectangle([P(sx0 - 7 * k), P(sy0 - 5 * k), P(sx1 + 7 * k), P(sy1 + 5 * k)], radius=int(P(14)), fill=(255, 60, 60, 18))
            dr.rounded_rectangle([P(sx0), P(sy0), P(sx1), P(sy1)], radius=int(P(10)), fill=(64, 12, 18), outline=(255, 80, 80), width=int(P(3)))
            dr.text((P((sx0 + sx1) / 2), P((sy0 + sy1) / 2)), "PLEASE BE QUIET", fill=(255, 128, 116), anchor="mm", font=font(int(26 * S)))
        else:
            dr.rounded_rectangle([P(sx0), P(sy0), P(sx1), P(sy1)], radius=int(P(10)), fill=(26, 12, 16), outline=(46, 20, 24), width=int(P(3)))
        # la porte EXIT et son panneau (éteint jusqu'au premier « OUT »)
        rect(DOOR[0] - 7, DOOR[1] - 7, DOOR[2] + 7, DOOR[3], (30, 28, 38))
        rect(*DOOR, (44, 40, 52))
        op = self.door_open(t)
        if op > 0:
            rect(DOOR[0], DOOR[1], DOOR[0] + (DOOR[2] - DOOR[0]) * op, DOOR[3], (255, 214, 150))
        ex0, ey0, ex1, ey1 = DOOR[0] - 2, 562.0, DOOR[2] + 2, 592.0
        if t >= T_EXIT_SIGN:
            for k in range(3, 0, -1):
                da.rounded_rectangle([P(ex0 - 5 * k), P(ey0 - 4 * k), P(ex1 + 5 * k), P(ey1 + 4 * k)], radius=int(P(8)), fill=(80, 255, 140, 20))
            dr.rounded_rectangle([P(ex0), P(ey0), P(ex1), P(ey1)], radius=int(P(6)), fill=(18, 70, 40), outline=(90, 255, 150), width=int(P(3)))
            dr.text((P((ex0 + ex1) / 2), P((ey0 + ey1) / 2)), "EXIT", fill=(140, 255, 175), anchor="mm", font=font(int(24 * S)))
        else:
            dr.rounded_rectangle([P(ex0), P(ey0), P(ex1), P(ey1)], radius=int(P(6)), fill=(14, 26, 20), outline=(26, 46, 34), width=int(P(3)))
        # l'allée
        rect(DOOR[0] - 7, DOOR[3], 225, H, (22, 20, 28))
        for yb in [800 + k * 62 for k in range(18)]:
            rect(DOOR[0] - 4, yb, 221, yb + 6, (40, 36, 50))
        # les rangées vides entre la scène et nous (décor, sous y 1260) : la nôtre est la dernière
        for x in SEATS:
            dr.rounded_rectangle([P(x - 82), P(1330), P(x + 82), P(1560)], radius=int(P(26)), fill=(58, 17, 28), outline=(90, 32, 46), width=int(P(4)))
        for x in (245.0, 450.0, 655.0, 860.0):
            dr.rounded_rectangle([P(x - 96), P(1640), P(x + 96), P(1990)], radius=int(P(30)), fill=(46, 13, 22), outline=(76, 26, 38), width=int(P(5)))
        walkers = []
        if usher["where"] == "front":
            self.draw_usher(dr, da, usher, t, S)
        for row in "ABC":
            yb = ROW_Y[row]
            s = row_scale(yb)
            people = []
            for p in self.P.values():
                st = self.person_at(p, t)
                if st is None:
                    continue
                if st[2] == "aisle":
                    walkers.append((p, st))
                elif p["row"] == row:
                    people.append((p, st))
            if row == "C" and usher["where"] == "rows":
                self.draw_usher(dr, da, usher, t, S)
            for p, st in people:
                self.draw_person(dr, da, p, st, t, S)
            for x in SEATS:
                w2 = 72 * s
                dr.rounded_rectangle([P(x - w2), P(yb), P(x + w2), P(yb + 150 * s)], radius=int(P(22 * s)),
                                     fill=SEAT_COL, outline=SEAT_EDGE, width=int(P(4)))
            if row == "B" and T_LAMP1_LAND <= t < T_LAMP2:
                self.draw_lamp(dr, lamp[0], lamp[1], lamp[2], S, on=True, k=lerp(2.2, 1.5, smooth((t - T_LAMP1_LAND) / 0.25)))
            if row == "C":
                self.draw_coat(dr, t, S, back=True)
                ps = self.pot_state(t)
                if ps not in ("held", "moving") and not self.in_pot(t):
                    self.draw_pot(dr, ps[0], ps[1], t, S)
        walkers.sort(key=lambda w: w[1][1])
        for p, st in walkers:
            self.draw_person(dr, da, p, st, t, S)
        if usher["where"] == "aisle":
            self.draw_usher(dr, da, usher, t, S)
        # la doudoune devant Bounce si elle est sur le siège et qu'il n'est pas dedans
        cs = self.coat_state(t)
        if cs is None and not (soft is not None and soft[0] in ("hide", "coat")):
            self.draw_coat(dr, t, S, back=False)
        # la lampe en l'air / posée sur C4
        if T_LAMP1 <= t < T_LAMP1_LAND or t >= T_LAMP2:
            kf = lerp(1.0, 2.2, smooth((t - T_LAMP1) / 0.15)) if t < T_LAMP1_LAND else lerp(1.5, 2.0, smooth((t - T_LAMP2) / 0.15))
            self.draw_lamp(dr, lamp[0], lamp[1], lamp[2], S, on=lamp[3], facing=lamp[4], k=kf)
        # le faisceau
        self.draw_beam(da, usher, lamp, sp, t, S)
        # pop-corn en l'air ; doudoune lancée
        for (t0, x0, y0, vx, vy, land, ph) in self.pop:
            if t < t0:
                continue
            dt = tau(t) - tau(t0)
            y = y0 + vy * dt + 0.5 * G * dt * dt
            if vy + G * dt > 0 and y > land:
                continue
            x = x0 + vx * dt
            for k in range(3):
                ox, oy = 5 * math.cos(ph + k * 2.1), 5 * math.sin(ph + k * 2.1)
                dr.ellipse([P(x + ox - 6), P(y + oy - 6), P(x + ox + 6), P(y + oy + 6)], fill=POP)
        if cs is not None and cs != "gone":
            self.draw_coat_free(dr, cs, S)
        # lumière d'ensemble
        if T_FLASH <= t < T_FLASH + 0.05:
            da.rectangle([0, 0, P(W), P(H)], fill=(255, 245, 210, 55))
        if T_LAMP2_LAND - 0.1 <= t < T_OFF:
            k = smooth((t - T_LAMP2_LAND + 0.1) / 0.25)
            da.rectangle([0, 0, P(W), P(H)], fill=(255, 236, 180, int(48 * k)))
            cx, cy = LAMP_C3[0] - 20, LAMP_C3[1]
            for rr, al in ((420, 30), (300, 40), (190, 60), (110, 90), (55, 160)):
                da.ellipse([P(cx - rr), P(cy - rr * 0.9), P(cx + rr), P(cy + rr * 0.9)], fill=(255, 240, 190, int(al * k)))
        if t >= T_OFF:
            k = smooth((t - T_OFF) / 0.12)
            da.rectangle([0, 0, P(W), P(H)], fill=(0, 0, 0, int(70 * k)))
        # Bounce
        self.draw_hero(dr, da, t, S, bx, by, soft)
        # la tache posée sur la doudoune où il se cache reste visible par-dessus la doudoune
        if sp is not None and soft is not None and soft[0] == "hide":
            da.ellipse([P(sp[0] - SPOT_RX), P(sp[1] - SPOT_RY), P(sp[0] + SPOT_RX), P(sp[1] + SPOT_RY)],
                       fill=BEAM + (105,), outline=BEAM + (235,), width=int(P(4)))
        # les bulles
        self.draw_bubbles(dr, t, S, usher)

    def draw_hero(self, dr, da, t, S, bx, by, soft):
        def P(v):
            return v * S
        for key in OUT_KEYS:
            w = self.line_window(key)
            if w is not None and w[0] <= t < w[0] + 1.0:
                base.HERO["expr"] = "shock"
        if t >= T_SMILE:
            base.HERO["expr"] = "win"
        if not self.hidden(t):
            base.ball(dr, P(bx), P(by), P(R))
        if soft is not None and soft[0] in ("hide", "coat"):
            self.draw_coat(dr, t, S, back=False)
        if soft is not None and soft[0] == "pot":
            ps = self.pot_state(t)
            self.draw_pot(dr, ps[0], ps[1], t, S)

    # ------------------------------------------------------------------ personnages
    def draw_person(self, dr, da, p, st, t, S):
        def P(v):
            return v * S
        x, yb, where, a = st
        s = row_scale(yb)
        Rh = 58.0 * s
        col = p["col"]
        rim = tuple(min(255, int(c * 0.5 + 120)) for c in col)
        gest = None
        for (t0, t1, kind, target) in p["gest"]:
            if t0 <= t < t1:
                gest = (kind, target)
        tx = ty = None
        lean = 0.0
        if gest is not None and gest[1] is not None:
            tx, ty = gest[1](t)
            lean = max(-1.0, min(1.0, (tx - x) / 300.0))
        hx, hy, _ = self.head_of(p, t)
        hx = x + lean * 0.4 * Rh * max(0.3, a)
        top_body = hy + 0.65 * Rh
        bot = yb + 120 * s if where == "row" else yb + 1.0 * Rh
        dr.rounded_rectangle([P(x - 1.2 * Rh), P(top_body), P(x + 1.2 * Rh), P(bot)], radius=int(P(0.55 * Rh)), fill=col)
        moving = p["path"] is not None and p["path"][0][0] <= t
        if where == "aisle" or (p["run"] and moving):
            ph = t * (16.0 if p["run"] else 7.0)
            for sgn in (-1, 1):
                fx = x + sgn * 0.45 * Rh + 0.35 * Rh * math.sin(ph) * sgn
                dr.line([P(x + sgn * 0.45 * Rh), P(bot - 4), P(fx), P(bot + 1.25 * Rh)], fill=col, width=int(P(0.42 * Rh)))
            if not p["run"]:
                hy += 0.15 * Rh
        if gest is not None and gest[0] in ("shh", "point"):
            side = 1 if (tx if tx is not None else x) >= x else -1
            shx, shy = hx + side * 1.0 * Rh, top_body + 0.35 * Rh
            if gest[0] == "shh":
                ex, ey = shx + side * 0.35 * Rh, hy + 0.1 * Rh
                dr.line([P(shx), P(shy), P(ex), P(ey)], fill=col, width=int(P(0.42 * Rh)))
                dr.rounded_rectangle([P(ex - 0.12 * Rh), P(ey - 0.75 * Rh), P(ex + 0.12 * Rh), P(ey + 0.05 * Rh)],
                                     radius=int(P(0.1 * Rh)), fill=rim)
            else:
                dx, dy = tx - shx, ty - shy
                d = math.hypot(dx, dy) + 1e-6
                L = 2.4 * Rh
                ex, ey = shx + dx / d * L, shy + dy / d * L
                dr.line([P(shx), P(shy), P(ex), P(ey)], fill=col, width=int(P(0.4 * Rh)))
                dr.ellipse([P(ex - 0.2 * Rh), P(ey - 0.2 * Rh), P(ex + 0.2 * Rh), P(ey + 0.2 * Rh)], fill=rim)
        if gest is not None and gest[0] == "mouth":
            for sgn in (-1, 1):
                dr.ellipse([P(hx + sgn * 0.95 * Rh - 0.28 * Rh), P(hy + 0.1 * Rh), P(hx + sgn * 0.95 * Rh + 0.28 * Rh),
                            P(hy + 0.66 * Rh)], fill=rim)
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
        # le vert tient son pot
        if p["id"] == "C2" and self.pot_state(t) in ("held", "moving"):
            u = smooth((t - 25.75) / 0.25) if t >= 25.75 else 0.0
            px = lerp(hx + 1.15 * Rh, POTX, u)
            ptop = lerp(hy - 0.2 * Rh, POT_BASE - POT_HT, u)
            self.draw_pot(dr, px, ptop, t, S, k=lerp(0.85, 1.0, u))

    def draw_usher(self, dr, da, u, t, S):
        def P(v):
            return v * S
        x, yb, Ru, size = u["x"], u["yb"], u["R"], u["size"]
        hx, hy = u["head"]
        dark = t >= T_OFF
        col = (60, 16, 22) if dark else USHER_COL
        rim = (120, 60, 70) if dark else (220, 120, 130)
        top = hy + 0.7 * Ru
        bot = yb - 1.2 * Ru
        dr.rounded_rectangle([P(x - 1.15 * Ru), P(top), P(x + 1.15 * Ru), P(bot)], radius=int(P(0.5 * Ru)), fill=col)
        dr.rectangle([P(x - 1.15 * Ru), P(top + 1.4 * Ru), P(x + 1.15 * Ru), P(top + 1.6 * Ru)], fill=GOLD if not dark else (90, 72, 30))
        for sgn in (-1, 1):
            dr.line([P(x + sgn * 0.5 * Ru), P(bot - 6), P(x + sgn * 0.55 * Ru), P(yb)], fill=(70, 18, 26), width=int(P(0.5 * Ru)))
        dr.ellipse([P(hx - Ru), P(hy - Ru), P(hx + Ru), P(hy + Ru)], fill=col, outline=rim, width=int(P(3)))
        dr.rounded_rectangle([P(hx - 0.85 * Ru), P(hy - 1.35 * Ru), P(hx + 0.85 * Ru), P(hy - 0.7 * Ru)], radius=int(P(0.2 * Ru)), fill=(46, 20, 26))
        dr.rectangle([P(hx - 0.85 * Ru), P(hy - 0.92 * Ru), P(hx + 0.85 * Ru), P(hy - 0.78 * Ru)], fill=GOLD if not dark else (90, 72, 30))
        if t >= 42.95:
            for (ux, uy) in self.usher_pop:
                gx, gy = hx + ux * Ru, hy - 1.3 * Ru + uy * Ru
                dr.ellipse([P(gx - 7), P(gy - 7), P(gx + 7), P(gy + 7)], fill=POP)
        sx, sy = u["shoulder"]
        hdx, hdy = u["hand"]
        dr.line([P(sx), P(sy), P(hdx), P(hdy)], fill=col, width=int(P(0.42 * Ru)))
        if u["holding"]:
            lamp = self.lamp_state(t)
            self.draw_lamp(dr, hdx, hdy, lamp[2], S, on=True)
        # la doudoune soulevée (37,40 -> 37,60)
        # le pouce
        if u["thumb"] is not None:
            key, t0 = u["thumb"]
            k = smooth((t - t0) / 0.2)
            ox, oy = x - 0.9 * Ru, top + 0.35 * Ru
            if key == "OUT_FILM":
                ox = x + 0.9 * Ru
                spx, spy = self.film_spot_img(t)
                dx, dy = spx - ox, spy - oy
                dd = math.hypot(dx, dy) + 1e-6
                tx, ty = ox + dx / dd * 3.0 * Ru, oy + dy / dd * 3.0 * Ru
            elif key == "OUT_YOU":
                tx, ty = x - 1.4 * Ru, top - 1.0 * Ru
            else:
                tx, ty = x - 1.25 * Ru, top - 1.3 * Ru
            ex, ey = lerp(ox, tx, k), lerp(oy + Ru, ty, k)
            dr.line([P(ox), P(oy), P(ex), P(ey)], fill=col, width=int(P(0.4 * Ru)))
            dr.rounded_rectangle([P(ex - 0.13 * Ru), P(ey - 0.55 * Ru), P(ex + 0.13 * Ru), P(ey + 0.05 * Ru)], radius=int(P(0.1 * Ru)), fill=rim)

    def draw_lamp(self, dr, x, y, ang, S, on=True, facing=False, k=1.0):
        def P(v):
            return v * S
        if facing:
            # couchée sur le dossier, la vitre tournée vers nous
            dr.rounded_rectangle([P(x - 62), P(y - 20), P(x + 44), P(y + 18)], radius=int(P(10)), fill=(150, 152, 166))
            dr.ellipse([P(x - 34), P(y - 34), P(x + 34), P(y + 34)], fill=(185, 188, 200))
            dr.ellipse([P(x - 24), P(y - 24), P(x + 24), P(y + 24)], fill=(255, 246, 200) if on else (70, 70, 80))
            return
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(u, v):
            u, v = u * k, v * k
            return (P(x + u * ca - v * sa), P(y + u * sa + v * ca))
        dr.polygon([Q(-42, -12), Q(16, -12), Q(16, 12), Q(-42, 12)], fill=(150, 152, 166))
        dr.polygon([Q(16, -20), Q(36, -20), Q(36, 20), Q(16, 20)], fill=(185, 188, 200))
        dr.polygon([Q(36, -17), Q(41, -17), Q(41, 17), Q(36, 17)], fill=(255, 240, 180) if on else (90, 90, 100))

    def draw_beam(self, da, usher, lamp, sp, t, S):
        def P(v):
            return v * S
        lx, ly, ang, on, facing = lamp
        if not on or facing:
            return
        ox, oy = lx + 41 * math.cos(ang), ly + 41 * math.sin(ang)
        if sp is not None and t < T_LAMP1:
            tx, ty = sp
            rr = SPOT_RX
        elif T_LAMP1 <= t < T_LAMP1_AIM or T_LAMP2 <= t < T_LAMP2_LAND:
            L = 1600.0
            tx, ty = ox + L * math.cos(ang), oy + L * math.sin(ang)
            rr = 220.0
        else:
            tx, ty = self.film_spot_img(t)
            rr = 70.0
        dx, dy = tx - ox, ty - oy
        d = math.hypot(dx, dy) + 1e-6
        nx, ny = -dy / d, dx / d
        pts = [(P(ox + nx * 10), P(oy + ny * 10)), (P(tx + nx * rr), P(ty + ny * rr)),
               (P(tx - nx * rr), P(ty - ny * rr)), (P(ox - nx * 10), P(oy - ny * 10))]
        da.polygon(pts, fill=BEAM + (22,))
        if sp is not None and t < T_LAMP1 and sp[1] >= SCREEN[3]:
            da.ellipse([P(tx - SPOT_RX), P(ty - SPOT_RY), P(tx + SPOT_RX), P(ty + SPOT_RY)], fill=BEAM + (105,),
                       outline=BEAM + (235,), width=int(P(4)))

    def draw_pot(self, dr, x, top, t, S, k=1.0):
        def P(v):
            return v * S
        sq = 0.0
        b = self.bounce_at(t)
        if b[2] is not None and b[2][0] == "pot":
            sq = math.sin(math.pi * b[2][1]) * 0.18
        w0, w1, h = 64 * k * (1 + sq), 50 * k * (1 + sq * 0.6), POT_HT * k * (1 - sq)
        base_y = top + POT_HT * k
        y0 = base_y - h
        fill = self.pot_fill(t)
        n = int(4 + 7 * fill)
        for i in range(n):
            px = x + (i - n / 2) * 12 * (0.8 + 0.4 * fill) * k
            py = y0 - 6 - 16 * fill * math.sin(math.pi * (i + 0.5) / n)
            dr.ellipse([P(px - 9 * k), P(py - 9 * k), P(px + 9 * k), P(py + 9 * k)], fill=POP)
        dr.polygon([(P(x - w0), P(y0)), (P(x + w0), P(y0)), (P(x + w1), P(base_y)), (P(x - w1), P(base_y))], fill=(214, 46, 50))
        for j in (-2, 0, 2):
            u0 = j / 5
            dr.polygon([(P(x + w0 * u0 - 7 * k), P(y0)), (P(x + w0 * u0 + 7 * k), P(y0)), (P(x + w1 * u0 + 6 * k), P(base_y)),
                        (P(x + w1 * u0 - 6 * k), P(base_y))], fill=(245, 240, 236))

    def draw_coat(self, dr, t, S, back):
        def P(v):
            return v * S
        if self.coat_state(t) is not None:
            return
        x = COAT[0]
        top = ROW_Y["C"] - 40
        dep = 0.0
        b = self.bounce_at(t)
        hide = False
        if b[2] is not None and b[2][0] in ("coat", "hide"):
            u, depth = b[2][1], b[2][2]
            sn = max(0.0, math.sin(math.pi * u))
            dep = depth * sn if depth < 100 else depth * sn ** 0.35
            hide = b[2][0] == "hide"
        col, dk = (62, 150, 84), (40, 104, 58)
        if back:
            dr.rounded_rectangle([P(x - 86), P(top - 8), P(x + 86), P(top + 150)], radius=int(P(40)), fill=dk)
            return
        if hide and dep > 40:
            k = smooth((dep - 40) / 60.0)
            hw = lerp(86, 92, k)
            ytop = top - 150 * k
            dr.rounded_rectangle([P(x - hw), P(ytop), P(x + hw), P(top + 160)], radius=int(P(lerp(36, 80, k))), fill=col)
            for j in range(1, 5):
                yy = ytop + j * (top + 160 - ytop) / 5
                dr.line([P(x - hw + 14), P(yy), P(x + hw - 14), P(yy)], fill=dk, width=int(P(4)))
            dr.line([P(x), P(ytop + 10), P(x), P(top + 155)], fill=dk, width=int(P(4)))
            dr.rounded_rectangle([P(x - 58), P(ytop - 6), P(x + 58), P(ytop + 26)], radius=int(P(14)), fill=dk)
            return
        dent = min(dep, 60.0) * 0.5
        dr.rounded_rectangle([P(x - 86), P(top + dent), P(x + 86), P(top + 155)], radius=int(P(36)), fill=col)
        for j in range(1, 4):
            yy = top + dent + j * (155 - dent) / 4
            dr.line([P(x - 76), P(yy), P(x + 76), P(yy)], fill=dk, width=int(P(4)))
        dr.line([P(x), P(top + dent + 6), P(x), P(top + 150)], fill=dk, width=int(P(4)))

    def draw_coat_free(self, dr, cs, S):
        def P(v):
            return v * S
        x, y, ang, k = cs
        col, dk = (62, 150, 84), (40, 104, 58)
        ca, sa = math.cos(ang), math.sin(ang)

        def Q(u, v):
            return (P(x + (u * ca - v * sa) * k), P(y + (u * sa + v * ca) * k))
        dr.polygon([Q(-80, -70), Q(80, -70), Q(95, 80), Q(-95, 80)], fill=col)
        dr.polygon([Q(-80, -70), Q(-130, 30), Q(-105, 45), Q(-70, -20)], fill=col)
        dr.polygon([Q(80, -70), Q(130, 30), Q(105, 45), Q(70, -20)], fill=col)
        dr.line([Q(0, -66), Q(0, 76)], fill=dk, width=int(P(4)))
        dr.polygon([Q(-40, -80), Q(40, -80), Q(30, -62), Q(-30, -62)], fill=dk)

    # ------------------------------------------------------------------ bulles (bande y 1000-1260)
    def speakers(self, key, t, usher):
        if key in OUT_KEYS:
            hx, hy = usher["head"]
            return [(hx, hy + usher["R"])]
        if key == "SHH_FILM":
            fs = self.film_state(t)
            return [self.film_to_img(fs["x"], 330 - 150)]
        who = {"SHH_B2": ["B2"], "SHH_PAIR": ["A1", "A2"],
               "SHH_USHER": ["A3", "A4", "B1", "B3", "B4", "C1", "C2"]}[key]
        heads = []
        for pid in who:
            hd = self.head_of(self.P[pid], t)
            if hd is not None:
                heads.append((hd[0], hd[1] + hd[2]))
        return heads

    def draw_bubbles(self, dr, t, S, usher):
        for (_, key) in LINES:
            win = self.line_window(key)
            if win is None:
                continue
            a, b = win
            text = BUBBLE[key]
            words = len(text.split())
            hold = max(0.5 + 0.3 * words, b - a + 0.45)
            if not (a - 0.03 <= t <= a + hold):
                continue
            fs = 52 if key == "OUT_ALL" else 56
            f = font(int(fs * S))
            tw = f.getbbox(text)[2] / S
            bw, bh = tw + 56, fs * 1.4
            if key not in self._bubble_pos:
                best, bestd = None, -1e9
                for cx in (300.0, 420.0, 540.0, 660.0, 780.0):
                    cx = max(125 + bw / 2, min(895 - bw / 2, cx))
                    worst = 1e9
                    for tt in np.linspace(a, a + hold, 8):
                        bx2, by2 = self.bounce_at(tt)[:2]
                        ddx = max(abs(bx2 - cx) - bw / 2, 0.0)
                        ddy = max(abs(by2 - 1212) - bh / 2, 0.0)
                        worst = min(worst, math.hypot(ddx, ddy))
                    if worst > bestd:
                        best, bestd = cx, worst
                self._bubble_pos[key] = best
            cx, cy = self._bubble_pos[key], 1212.0
            pop = smooth((t - a + 0.03) / 0.1)
            heads = self.speakers(key, t, usher)
            self.bubble(dr, cx, cy, bw, bh, heads, text, f, S, pop)

    def bubble(self, dr, cx, cy, bw, bh, tails, text, f, S, pop):
        def P(v):
            return v * S
        k = 0.6 + 0.4 * pop
        bw, bh = bw * k, bh * k
        white = (246, 246, 246)
        for (hx, hy) in tails:
            ax = max(cx - bw / 2 + 26, min(cx + bw / 2 - 26, hx))
            if hy < cy:
                dr.polygon([(P(ax - 15), P(cy - bh / 2 + 4)), (P(ax + 15), P(cy - bh / 2 + 4)), (P(hx), P(hy))], fill=white)
            else:
                dr.polygon([(P(ax - 15), P(cy + bh / 2 - 4)), (P(ax + 15), P(cy + bh / 2 - 4)), (P(hx), P(hy))], fill=white)
        dr.rounded_rectangle([P(cx - bw / 2), P(cy - bh / 2), P(cx + bw / 2), P(cy + bh / 2)], radius=int(P(bh * 0.4)), fill=white)
        dr.text((P(cx), P(cy)), text, fill=(12, 12, 16), anchor="mm", font=f if pop >= 1 else font(int(f.size * k)))


def chk_beam(sim, fps=60):
    """La tache ne touche jamais Bounce tant que l'ouvreur tient la lampe (sauf s'il est caché).
    Renvoie la liste des images en faute et la marge minimale."""
    bad, worst = [], (1e9, None)
    n = int(T_LAMP1 * fps)
    for i in range(n):
        t = i / fps
        sp = sim.spot(t)
        if sp is None:
            continue
        if sim.hidden(t):
            continue
        bx, by = sim.bounce_at(t)[:2]
        d = math.hypot(bx - sp[0], by - sp[1]) - (SPOT_RX + R)
        if d < worst[0]:
            worst = (d, t)
        if d < 10:
            bad.append((round(t, 3), round(d, 1)))
    return bad, worst


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 99.0,
            "hook_top": 0.125, "hook_font_size": 80, "hero_win": "", "hook_narrator": True, "narrator_length": 0.95}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
