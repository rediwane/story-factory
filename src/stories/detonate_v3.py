"""
Detonate v3 : le personnage d'un fan (Detonate, une boule orange dans une coque de huit morceaux) et
Bounce, sur un trampoline, dans un jardin la nuit. À gauche du tapis, un gros coussin de mousse : quand
Bounce y retombe, rien ne bouge et il se tait ; quand il retombe sur la toile (« Bounce »), l'onde
secoue Detonate, qui perd sa coque morceau par morceau et se fâche de plus en plus. La coque vide
n'explose pas : il se met à gonfler à chaque rebond. Il s'est presque calmé quand le dernier rebond le
regonfle au-delà de son maximum : il éclate en confettis, et c'est Bounce qui les prend.

Tout le déroulé est écrit d'avance (contacts, sauts, états), comme dans le découpage
lot6/detonate/decoupage_v3.md. Une seule gravité (G = 2600) pour Bounce, Detonate, les morceaux et les
confettis (ces derniers freinés par l'air). Bounce n'est dessiné que par base.ball(). Detonate ne dit
que son nom (banque de voix hors dépôt, cfg["voice_bank"]), sans sous-titre. Rien n'est ajouté au moteur.

    python3 src/stories/detonate_v3.py configs/detonate_v3.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR
G = 2600.0

# ------------------------------------------------------------------ la voix de Detonate
WHO = "Detonate"
# hauteur et vitesse propres à chaque réplique (rééchantillonnage : > 1 plus aigu et plus court)
LINE_PITCH = {"grogne": 0.90, "warn": 1.00, "furax": 1.08, "boude": 0.95, "lent": 0.95, "hurle": 1.12,
              "gonfle": 1.03, "fin": 1.10}
LINE_GAIN = {"grogne": 0.8, "warn": 0.95, "furax": 1.1, "boude": 0.75, "lent": 1.0, "hurle": 1.25,
             "gonfle": 1.0, "fin": 1.05}
BANK, ENV = {}, {}
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
    for key, f in LINE_PITCH.items():
        x = _read(os.path.join(path, key + ".wav"))
        a = np.abs(x)
        idx = np.where(a > 0.03 * a.max())[0]
        x = x[max(0, idx[0] - int(0.01 * SR)):idx[-1] + int(0.02 * SR)]
        x = base.pitch(x, f)
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2 * LINE_GAIN[key]
        n = min(int(0.015 * SR), len(x))
        x[-n:] *= np.linspace(1, 0, n)
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def detonate_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = detonate_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Detonate suit sa voix
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce : une prise stable
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
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
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ réverbération par FFT
# base.reverb fait un np.convolve direct, très lent sous charge ; même calcul par FFT.
def fft_reverb(x, sr, tail_s=0.8, wet=0.5):
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    L = len(x) + n - 1
    nf = 1 << (L - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:L]
    out = np.zeros(L)
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = fft_reverb

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
RB = 120.0                       # Bounce
RV = 115.0                       # Detonate, coque comprise, à l'échelle 1
KI = 0.66                        # le disque orange, sous la coque
DX0 = 760.0                      # Detonate, assis sur la toile
MAT_Y = 1190.0
X0, X1 = 420.0, 1000.0           # la toile
PAD_X0, PAD_X1, PAD_Y = 190.0, 420.0, 1150.0
PAD_X = 305.0
GRASS_Y = 1480.0
CM = 0.16                        # contact sur la toile

BG = (10, 11, 20)
FENCE, FENCE_LINE = (17, 18, 30), (24, 25, 40)
GRASS, GRASS_HI = (14, 26, 20), (20, 38, 28)
MAT_COL, MAT_EDGE = (30, 30, 42), (110, 112, 140)
FRAME = (78, 82, 100)
PAD_COL, PAD_HI, PAD_LO = (88, 150, 220), (130, 190, 245), (58, 104, 168)
D_ORANGE = (255, 112, 10)
D_SHELL, D_SHELL_EDGE = (196, 74, 8), (255, 168, 90)
D_HALO = (46, 22, 10)
INK = (16, 14, 20)
CONF_COLS = [(255, 80, 170), (255, 220, 60), (70, 220, 255), (120, 240, 110), (250, 250, 250),
             (255, 150, 40), (180, 110, 255)]
HEAT = [(0.0, (255, 112, 10)), (0.25, (236, 84, 6)), (0.45, (228, 60, 12)), (0.7, (220, 34, 22)),
        (1.0, (255, 26, 30))]

# ------------------------------------------------------------------ le plan (découpage §3)
# contacts de Bounce : (t, genre, x, durée du contact). M = toile (dur, « Bounce ») ; P = coussin (mou)
S_CONTACTS = []
# les contacts durs du découpage, et, entre deux, le passage par le coussin
M_T = [0.55, 2.25, 3.20, 5.95, 6.83, 7.85, 10.40, 11.32, 12.42, 14.32, 15.50, 16.36, 19.26, 20.31, 23.01,
       23.94, 25.86, 27.06, 27.94, 28.80, 30.68, 31.80, 34.40, 35.27, 36.22, 37.30, 39.55, 40.55, 42.41,
       43.63, 44.58, 45.44, 48.24, 49.14, 50.48, 52.93, 54.08, 55.18, 56.03, 57.00, 58.03, 60.52]
M_X = [460, 470, 455, 470, 460, 450, 475, 455, 460, 470, 460, 455, 470, 455, 460,
       450, 455, 455, 450, 465, 470, 455, 470, 450, 445, 445, 465, 455, 460,
       455, 450, 445, 445, 440, 440, 440, 440, 440, 440, 440, 440, 435]
LONG_MIN = 1.5                   # au-delà, le passage se fait par le coussin
# répliques : (t de début, clé)
LINES = [(4.15, "grogne"), (9.15, "warn"), (17.41, "furax"), (21.86, "boude"), (32.70, "lent"),
         (38.45, "hurle"), (46.84, "gonfle"), (51.68, "fin")]
# les sauts de Detonate provoqués par un contact dur : t du contact -> hauteur (px)
LAUNCH = {5.95: 150, 10.40: 100, 14.32: 110, 19.26: 90, 25.86: 360, 30.68: 80, 34.40: 120, 39.55: 100,
          48.24: 198}
WAVE = 0.12                      # l'onde de la toile met ce temps à l'atteindre
T_POP = 60.87
T_END = 62.63

# la coque : 8 morceaux, par angle écran (0 = droite, 90 = bas)
SEG = {"TL": 225, "TR": 315, "R": 0, "BR": 45, "B": 90, "BL": 135, "L": 180, "T": 270}
# morceaux arrachés : clé -> t
LOSS = {"TL": 0.70, "TR": 2.40, "R": 6.78, "BR": 6.78, "B": 12.55, "BL": 16.48, "L": 26.45}
T_LAST_FALL = 42.53
# pics de taille (V = rayon visible / RV), keyframes (t, V)
SIZE_K = [(0, 1.0), (6.78, 1.0), (6.90, 1.04), (16.48, 1.04), (16.62, 1.12), (17.6, 1.12), (19.1, 1.05),
          (26.0, 1.05), (26.2, 1.08), (35.35, 1.08), (35.50, 1.22), (38.6, 1.22), (40.3, 1.10),
          (42.53, 1.10)]
# après la chute du dernier morceau : rayon du corps nu (px)
BODY_K = [(42.53, KI * RV * 1.10), (44.70, KI * RV * 1.10), (44.82, 147), (45.56, 147), (45.68, 152),
          (46.9, 152), (47.9, 150), (48.36, 150), (48.48, 154), (50.60, 154), (50.72, 158), (51.7, 158),
          (52.6, 156), (53.05, 156), (53.17, 159), (56.15, 159), (56.27, 161), (58.85, 161), (60.40, 132),
          (60.64, 132), (60.85, 167)]
RED_K = [(0, 0.0), (0.62, 0.0), (0.70, 0.12), (6.78, 0.12), (6.9, 0.25), (16.48, 0.25), (16.62, 0.7),
         (17.6, 0.7), (19.1, 0.42), (26.2, 0.45), (35.35, 0.45), (35.5, 0.92), (38.6, 0.92), (40.3, 0.68),
         (42.53, 0.72), (44.82, 0.78), (56.27, 0.98), (58.85, 0.98), (60.40, 0.12), (60.64, 0.12),
         (60.85, 1.0)]
SHAKE_K = [(0, 0.0), (6.78, 0.0), (6.9, 1.5), (16.48, 1.5), (16.62, 6.0), (17.6, 6.0), (19.1, 2.5),
           (26.2, 3.0), (35.35, 3.0), (35.5, 9.0), (38.6, 9.0), (40.3, 4.0), (44.82, 4.0), (56.27, 10.0),
           (58.85, 10.0), (60.0, 0.0), (60.64, 0.0), (60.85, 13.0)]
RIM_K = [(0, 0.0), (35.35, 0.0), (35.5, 0.7), (38.6, 0.7), (40.3, 0.0), (46.10, 0.0), (46.2, 0.6),
         (46.6, 0.0), (56.15, 0.0), (56.27, 0.5), (58.1, 0.5), (58.2, 0.9), (58.85, 0.9), (59.6, 0.0),
         (60.64, 0.0), (60.76, 1.0)]
STEAM = [(9.6, 0.5, 0.5), (12.9, 0.5, 0.4), (14.6, 0.4, 0.4), (17.9, 1.4, 1.0), (24.05, 0.5, 0.8),
         (39.3, 1.3, 1.0), (47.2, 0.8, 0.6), (52.0, 0.7, 0.6), (59.0, 1.3, 0.8)]       # (t, durée, force)
WISP = (28.0, 42.5)              # de la vapeur fuit en continu


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def keyed(K, t):
    if t <= K[0][0]:
        return K[0][1]
    for (ta, va), (tb, vb) in zip(K, K[1:]):
        if ta <= t <= tb:
            return lerp(va, vb, ease((t - ta) / (tb - ta)) if tb > ta else 1.0)
    return K[-1][1]


def heat_col(r):
    for (ra, ca), (rb, cb) in zip(HEAT, HEAT[1:]):
        if r <= rb:
            return mix(ca, cb, (r - ra) / (rb - ra))
    return HEAT[-1][1]


def shape(x, xc):
    if x <= X0 or x >= X1:
        return 0.0
    v = (x - X0) / (xc - X0) if x < xc else (X1 - x) / (X1 - xc)
    return max(0.0, min(1.0, v)) ** 0.7


def pulse(s):
    if s < 0:
        return 0.0
    if s < CM:
        return math.sin(math.pi * s / CM)
    u = s - CM
    if u > 1.6:
        return 0.0
    return -0.45 * math.exp(-u / 0.28) * math.sin(math.pi * u / 0.22)


def ballistic(t, t0, x0, y0, t1, x1, y1):
    T = max(1e-6, t1 - t0)
    s = t - t0
    vy = (y1 - y0) / T - 0.5 * G * T
    return lerp(x0, x1, s / T), y0 + vy * s + 0.5 * G * s * s


class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.rng = np.random.default_rng(int(cfg["seed"]) + 5)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.payoff_at = T_POP

        # ---- Bounce : la suite complète de ses contacts
        C = []
        for i, (tm, xm) in enumerate(zip(M_T, M_X)):
            C.append({"t": tm, "k": "M", "x": float(xm), "d": CM})
            if i + 1 < len(M_T):
                gap = M_T[i + 1] - tm
                if gap > LONG_MIN:
                    C.extend(self._pad_visit(tm + CM, M_T[i + 1], gap))
        # après l'éclatement : soufflé vers le coussin, il s'y enfonce, il remonte
        C.append({"t": 61.75, "k": "P", "x": PAD_X, "d": 0.42, "depth": 55.0})
        self.C = sorted(C, key=lambda c: c["t"])
        self.hits = [(c["t"], "toile") for c in self.C if c["k"] == "M"]
        self.hi = 0
        self.lines = [(tl, WHO + " " + k, f"d{i}") for i, (tl, k) in enumerate(LINES)]

        # ---- les chocs sur la toile : (t, x, amplitude)
        self.imp = []
        prev_end = None
        for c in self.C:
            if c["k"] != "M":
                prev_end = c["t"] + c["d"]
                continue
            f = (c["t"] - prev_end) if prev_end is not None else 0.55
            v = G * f / 2
            self.imp.append((c["t"], c["x"], min(64.0, 0.042 * v)))
            prev_end = c["t"] + c["d"]

        # ---- Detonate : ses sauts
        self.dfl = []                 # (t0, t1, x0, x1, spin)
        busy = []
        for tm in M_T:
            if tm >= 60.5:
                continue
            t0 = tm + WAVE
            if any(a - 0.02 <= t0 <= b + 0.05 for (a, b, *_r) in self.dfl):
                continue
            Hh = LAUNCH.get(round(tm, 2))
            if Hh is None:
                f = self._flight_before(tm)
                Hh = 14 + 26 * min(1.0, max(0.0, (f - 0.6) / 0.6))
                if tm > 42.5:
                    Hh *= 0.6                                  # nu et gonflé, il est lourd
            T = 2 * math.sqrt(2 * Hh / G)
            x0 = self.dx_rest(t0)
            x1 = x0
            spin = 0.0
            if round(tm, 2) == 25.86:
                x1, spin = 705.0, 2 * math.pi                  # le record : vrille, retombe collé à Bounce
            self.dfl.append((t0, t0 + T, x0, x1, spin, Hh))
            self.imp.append((t0 + T, x1, 10.0 + 0.11 * Hh))
        # les morceaux arrachés : trajectoires (t0, x0, y0, vx, vy, spin, rot0)
        self.pieces = []
        for k, tl in LOSS.items():
            self.pieces.append(self._piece(k, tl))
        self.pieces.append(self._piece("T", T_LAST_FALL, fall=True))
        self.stars = [(tl, k) for k, tl in LOSS.items()]

        self.conf = None
        self.steam = []               # bouffées : [x, y, r, born, life, vx]

    # ---------------------------------------------------------------- Bounce
    def _pad_visit(self, a, b, gap):
        """Entre deux contacts durs éloignés : un ou deux passages mous sur le coussin."""
        tot = b - a
        if gap > 2.2:                                          # deux touches molles
            d1, d2 = 0.32, 0.28
            fl = tot - d1 - d2
            f1, f2, f3 = 0.34 * fl, 0.16 * fl, 0.50 * fl
            t1 = a + f1
            t2 = t1 + d1 + f2
            return [{"t": t1, "k": "P", "x": PAD_X, "d": d1, "depth": 50.0},
                    {"t": t2, "k": "P", "x": PAD_X + 6, "d": d2, "depth": 38.0}]
        d1 = 0.40 if gap > 2.0 else 0.34
        fl = tot - d1
        t1 = a + 0.45 * fl
        return [{"t": t1, "k": "P", "x": PAD_X, "d": d1, "depth": 52.0}]

    def _flight_before(self, tm):
        prev = [c for c in self.C if c["t"] < tm - 1e-6]
        if not prev:
            return 0.55
        p = prev[-1]
        return tm - p["t"] - p["d"]

    def surf_y(self, c, t):
        """Le dessus de la surface sous Bounce pendant le contact c."""
        if c["k"] == "M":
            return self.mat_y(c["x"], t)
        u = (t - c["t"]) / c["d"]
        return PAD_Y + c["depth"] * math.sin(math.pi * max(0.0, min(1.0, u)))

    def bounce_at(self, t):
        C = self.C
        if t < C[0]["t"]:
            c = C[0]
            y1 = self.mat_y(c["x"], c["t"]) - RB
            s = c["t"] - t
            return c["x"] - 30 * s, y1 - 0.5 * G * s * s
        for i, c in enumerate(C):
            a, b = c["t"], c["t"] + c["d"]
            if a <= t <= b:
                return c["x"], self.surf_y(c, t) - RB
            if i + 1 < len(C) and b < t < C[i + 1]["t"]:
                n = C[i + 1]
                if a < T_POP < n["t"]:
                    # l'éclatement le souffle en plein vol vers le coussin
                    if t < T_POP:
                        return self._arc_free(c, t)
                    px, py = self._arc_free(c, T_POP)
                    yn = PAD_Y - RB
                    return ballistic(t, T_POP, px, py, n["t"], n["x"], yn)
                y0 = self.surf_y(c, b) - RB
                y1 = self.surf_y(n, n["t"]) - RB
                return ballistic(t, b, c["x"], y0, n["t"], n["x"], y1)
        c = C[-1]
        b = c["t"] + c["d"]
        s = t - b
        y0 = PAD_Y - RB
        return c["x"] + 20 * s, y0 - 820 * s + 0.5 * G * s * s

    def _arc_free(self, c, t):
        b = c["t"] + c["d"]
        y0 = self.surf_y(c, b) - RB
        return ballistic(t, b, c["x"], y0, b + 1.0, c["x"] - 30, y0)

    # ---------------------------------------------------------------- la toile
    def d_on_mat(self, t):
        """1 quand Detonate pèse sur la toile. Sur un petit saut, la toile n'a pas le temps de remonter ;
        sur un vrai lancer, elle remonte (et se recreuse juste avant qu'il retombe) en 0,1 s."""
        for (a, b, x0, x1, spin, Hh) in self.dfl:
            if a <= t <= b:
                if Hh < 45:
                    return 1.0
                return max(0.0, 1 - ease((t - a) / 0.1), 1 - ease((b - t) / 0.1))
        return 1.0

    def dip(self, x, t):
        d = 0.0
        for (te, xc, A) in self.imp:
            s = t - te
            if 0 <= s < 1.8:
                d += A * shape(x, xc) * pulse(s)
        v = self.size_v(t) / RV
        sag = 14.0 * v ** 3 + 26.0 * ease((t - 54.08) / 0.4) * (1 if t < T_POP else 0)
        d += sag * self.d_on_mat(t) * shape(x, self.dx_rest(t))
        return d

    def mat_y(self, x, t):
        return MAT_Y + self.dip(x, t)

    # ---------------------------------------------------------------- Detonate
    def shell_on(self, t):
        return t < T_LAST_FALL

    def size_v(self, t):
        """Rayon visible de Detonate (coque comprise tant qu'il en a une)."""
        if t >= T_POP:
            return KI * RV
        if self.shell_on(t):
            return RV * keyed(SIZE_K, t)
        return keyed(BODY_K, t)

    def body_r(self, t):
        if t >= T_POP:
            return KI * RV
        if self.shell_on(t):
            return KI * self.size_v(t)
        return self.size_v(t)

    def dx_rest(self, t):
        """Sa place : il glisse vers Bounce à 20,3 s ; gonflé, son centre recule pour rester dans l'image."""
        x = DX0
        if 20.42 <= t < 22.9:
            k = ease((t - 20.42) / 0.45) if t < 21.9 else 1 - ease((t - 21.9) / 0.9)
            x = lerp(DX0, 700.0, k)
        if 26.95 <= t < 28.6:
            k = 1 - ease((t - 28.0) / 0.55) if t >= 28.0 else 1.0
            x = lerp(DX0, 705.0, k)
        if t >= 42.53 and t < T_POP:
            x = min(x, 897.0 - self.size_v(t))
        if t >= T_POP:
            x = 897.0 - 167.0
        return x

    def det_at(self, t):
        rest = self.mat_y(self.dx_rest(t), t) - self.body_r(t)
        for (a, b, x0, x1, spin, _h) in self.dfl:
            if a <= t <= b:
                y0 = self.mat_y(x0, a - 1e-3) - self.body_r(a)
                y1 = self.mat_y(x1, b + 1e-3) - self.body_r(b)
                x, y = ballistic(t, a, x0, y0, b, x1, y1)
                if not spin:
                    x = self.dx_rest(t)
                return x, min(y, self.mat_y(x, t) - self.body_r(t)), spin * (t - a) / (b - a)
        return self.dx_rest(t), rest, 0.0

    def _piece(self, k, tl, fall=False):
        rng = self.rng
        dx, dy, _ = self.det_at(tl)
        a = math.radians(SEG[k])
        rc = 0.5 * (1 + KI) * self.size_v(tl)
        x0, y0 = dx + rc * math.cos(a), dy + rc * math.sin(a)
        if fall:
            return {"k": k, "t0": tl, "x0": x0, "y0": y0, "vx": 330.0, "vy": -260.0, "spin": 4.0,
                    "rot0": a + math.pi / 2 + 1.0}
        vx = rng.uniform(300, 420)
        vy = -rng.uniform(760, 900)
        return {"k": k, "t0": tl, "x0": x0, "y0": y0, "vx": vx, "vy": vy, "spin": rng.uniform(6, 10),
                "rot0": a + math.pi / 2}

    def piece_pos(self, p, t):
        s = t - p["t0"]
        x = p["x0"] + p["vx"] * s
        y = p["y0"] + p["vy"] * s + 0.5 * G * s * s
        if x < X1 + 30 and y > MAT_Y - 14:                      # il glisse sur la toile jusqu'au bord
            y = MAT_Y - 14
        return x, min(y, GRASS_Y + 20), p["rot0"] + p["spin"] * s

    # ---------------------------------------------------------------- pas de simulation
    def step(self, dt):
        evs = []
        self.t += dt
        t = self.t
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        for k, tl in LOSS.items():
            if tl <= t < tl + dt:
                evs.append(("event", f"morceau {k}"))
        if not self.payoff and t >= T_POP:
            self.payoff = True
            evs.append(("payoff", "confettis"))
            self._burst()
        if self.conf is not None:
            self._conf_step(dt)
        self._steam_step(dt)
        if t >= T_END:
            self.done = True
        return evs

    def _steam_step(self, dt):
        t = self.t
        rng = self.rng
        dx, dy, _ = self.det_at(t)
        top = dy - self.size_v(t)
        rate = 0.0
        for (ts, du, f) in STEAM:
            if ts <= t < ts + du:
                rate = max(rate, 26.0 * f)
        if WISP[0] <= t < WISP[1]:
            rate = max(rate, 5.0)
        if t < T_POP and rng.random() < rate * dt:
            self.steam.append([dx + rng.uniform(-18, 18), top + 6, rng.uniform(10, 18), t,
                               rng.uniform(0.7, 1.2), rng.uniform(-20, 20)])
        keep = []
        for s in self.steam:
            age = t - s[3]
            if age < s[4]:
                s[1] -= 120 * dt
                s[0] += s[5] * dt
                s[2] += 18 * dt
                keep.append(s)
        self.steam = keep

    def _burst(self):
        rng = self.rng
        dx, dy, _ = self.det_at(T_POP)
        n = 340
        R = 167.0
        ang = rng.uniform(-math.pi, math.pi, n)
        ang = np.where(np.sin(ang) > 0.4, -ang, ang)
        spd = rng.uniform(500, 2000, n)
        rr = rng.uniform(0.2, 0.95, n) * R
        self.conf = {
            "x": dx + rr * np.cos(ang), "y": dy + rr * np.sin(ang),
            "vx": spd * np.cos(ang), "vy": spd * np.sin(ang) - 250,
            "col": rng.integers(0, len(CONF_COLS), n), "sz": rng.uniform(0.8, 1.4, n),
            "rot": rng.uniform(0, math.pi, n), "spin": rng.uniform(-9, 9, n), "ph": rng.uniform(0, 6.3, n),
            "st": np.zeros(n, dtype=int), "rx": np.zeros(n), "ry": np.zeros(n),
        }
        # Bounce prend la gerbe en pleine face
        bx, by = self.bounce_at(T_POP)
        k = 36
        a = rng.uniform(-1.5, 1.5, k)                             # côté droit de Bounce, face à Detonate
        C = self.conf
        C["st"][:k] = 2
        C["rx"][:k] = np.cos(a) * RB * rng.uniform(0.6, 0.95, k)
        C["ry"][:k] = np.sin(a) * RB * rng.uniform(0.6, 0.95, k)

    def _conf_step(self, dt):
        C = self.conf
        t = self.t
        free = C["st"] == 0
        if free.any():
            C["vy"][free] += G * dt
            dec = math.exp(-3.2 * dt)
            C["vx"][free] *= dec
            C["vy"][free] *= dec
            sway = 60 * np.sin(C["ph"][free] + t * 5.0)
            C["x"][free] += (C["vx"][free] + sway) * dt
            C["y"][free] += C["vy"][free] * dt
            C["rot"][free] += C["spin"][free] * dt
        bx, by = self.bounce_at(t)
        for i in np.where(free)[0]:
            x, y = C["x"][i], C["y"][i]
            if x < -40 or x > W + 40 or y > H:
                C["st"][i] = 4
                continue
            ddx, ddy = x - bx, y - by
            if ddx * ddx + ddy * ddy < (RB * 0.95) ** 2 and t > T_POP + 0.05:
                C["st"][i] = 2
                C["rx"][i], C["ry"][i] = ddx * 0.9, ddy * 0.9
                continue
            if C["vy"][i] > 0:
                if X0 < x < X1 and y >= self.mat_y(x, t) - 4:
                    C["st"][i] = 1
                elif PAD_X0 < x < PAD_X1 and y >= PAD_Y - 4:
                    C["st"][i] = 6
                elif y >= GRASS_Y + 6:
                    C["st"][i] = 5
                    C["y"][i] = GRASS_Y + 6 + (i % 7) * 4

    def snapshot(self):
        st = [list(s) for s in self.steam]
        if self.conf is None:
            return (self.t, None, st)
        C = self.conf
        return (self.t, {k: C[k].copy() for k in ("x", "y", "rot", "ph", "st", "rx", "ry", "col", "sz")}, st)

    def hero_mood(self):
        return "lose"

    def counter(self, snap):
        return None

    # ---------------------------------------------------------------- dessin
    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                if e is None:
                    return 0.0, None
                i = int((t - n["start"]) * 60)
                return float(e[min(i, len(e) - 1)]), n["text"].split(" ", 1)[1]
        return 0.0, None

    def seg_poly(self, cx, cy, ri, ro, a_mid, half, S, rot=0.0, pivot=None):
        pts = []
        n = 8
        for j in range(n + 1):
            a = a_mid - half + 2 * half * j / n
            pts.append((cx + ro * math.cos(a), cy + ro * math.sin(a)))
        for j in range(n, -1, -1):
            a = a_mid - half + 2 * half * j / n
            pts.append((cx + ri * math.cos(a), cy + ri * math.sin(a)))
        if rot:
            px, py = pivot if pivot is not None else (sum(p[0] for p in pts) / len(pts),
                                                       sum(p[1] for p in pts) / len(pts))
            ca, sa = math.cos(rot), math.sin(rot)
            pts = [(px + (x - px) * ca - (y - py) * sa, py + (x - px) * sa + (y - py) * ca) for x, y in pts]
        return [(x * S, y * S) for x, y in pts]

    def loose_piece_poly(self, x, y, rot, S, scale=1.0):
        """Un morceau détaché, ramené à son centre et tourné de rot."""
        V = RV * scale
        pts = self.seg_poly(0, 0, KI * V, V, -math.pi / 2, math.radians(19.5), 1)
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        ca, sa = math.cos(rot), math.sin(rot)
        return [((x + (u - mx) * ca - (v - my) * sa) * S, (y + (u - mx) * sa + (v - my) * ca) * S) for u, v in pts]

    def eyes_state(self, t):
        if t < 0.62:
            return "sleep"
        if t >= T_POP + 0.15:
            return "serene"
        if 59.85 <= t < 60.62:
            return "closing"
        if 43.75 <= t < 44.45:
            return "down"
        return "angry"

    def draw_detonate(self, dr, t, S, part):
        x, y, spin = self.det_at(t)
        V = self.size_v(t)
        red = keyed(RED_K, t) if t < T_POP else 0.0
        shake = keyed(SHAKE_K, t) if t < T_POP else 0.0
        x += shake * math.sin(t * 61.0) * 0.8
        y += shake * math.sin(t * 47.0 + 1.3) * 0.5
        sq = 0.0
        for (a, b, *_r) in self.dfl:
            if 0 <= t - b < 0.35:
                sq = 0.13 * math.exp(-(t - b) * 9) * math.cos((t - b) * 20)
        if 0 <= t - T_POP < 0.6:
            sq = 0.12 * math.exp(-(t - T_POP) * 6) * math.cos((t - T_POP) * 24)
        sx, sy = 1 + sq, 1 - sq
        if part == "halo":
            hr = 1.6 * V
            dr.ellipse([(x - hr * sx) * S, (y - hr * sy) * S, (x + hr * sx) * S, (y + hr * sy) * S],
                       fill=mix(D_HALO, (70, 14, 10), red))
            return
        br = self.body_r(t)
        shell = self.shell_on(t) and t < T_POP
        body_col = heat_col(red)
        if shell:
            # la lueur rouge qui fuit par les trous de la coque
            glow = mix((170, 30, 12), (255, 50, 30), red)
            gr = V * (0.97 + 0.03 * math.sin(t * 9))
            dr.ellipse([(x - gr) * S, (y - gr) * S, (x + gr) * S, (y + gr) * S], fill=glow)
            gi = V * 0.84
            dr.ellipse([(x - gi) * S, (y - gi) * S, (x + gi) * S, (y + gi) * S],
                       fill=mix(glow, (255, 150, 90), 0.45 + 0.1 * math.sin(t * 9)))
        rim = keyed(RIM_K, t) if t < T_POP else 0.0
        if rim > 0.02 and (rim > 0.95 or math.sin(t * 38) > -0.2):
            rr = (V if shell else br) + 7
            dr.ellipse([(x - rr * sx) * S, (y - rr * sy) * S, (x + rr * sx) * S, (y + rr * sy) * S],
                       outline=mix(body_col, (255, 255, 255), rim), width=max(2, int((6 + 12 * rim) * S)))
        dr.ellipse([(x - br * sx) * S, (y - br * sy) * S, (x + br * sx) * S, (y + br * sy) * S], fill=body_col)
        # la peau qui se tend (57 s)
        if 56.95 <= t < T_POP and not shell:
            k = ease((t - 56.95) / 0.3)
            dr.ellipse([(x - 0.62 * br) * S, (y - 0.70 * br) * S, (x - 0.12 * br) * S, (y - 0.40 * br) * S],
                       fill=mix(body_col, (255, 220, 200), 0.55 * k))
        if shell:
            half = math.radians(19.5)
            for k, ang in SEG.items():
                if k in LOSS and t >= LOSS[k]:
                    continue
                a = math.radians(ang) + spin
                off, rot, pivot = 0.0, 0.0, None
                if k == "R" and 3.32 <= t < 4.0:                   # se soulève, retombe
                    u = (t - 3.32) / 0.68
                    off = 20 * math.sin(math.pi * u)
                if k == "BL" and t >= 10.55:                       # recollé de travers
                    u = min(1.0, (t - 10.55) / 0.25)
                    rot, off = 0.42 * u, 7 * u
                if k == "L" and 19.38 <= t < 20.2:
                    off = 6 * abs(math.sin((t - 19.38) * 30))
                if k == "T" and 28.92 <= t < 29.6:
                    off = 4 * abs(math.sin((t - 28.92) * 34))
                if k == "T" and t >= 35.40:                        # pend par un coin, puis par un fil
                    u = t - 35.40
                    base_a = 0.75 if t < 39.67 else 1.15
                    rot = base_a + 0.22 * math.sin(u * 4.2) * (1.6 if 36.3 < t < 37.3 else 1.0)
                    pc = a + half
                    pivot = (x + V * math.cos(pc), y + V * math.sin(pc))
                ro = V + off
                ri = KI * V + off
                pts = self.seg_poly(x, y, ri, ro, a, half, S, rot=rot, pivot=pivot)
                pts = [(((px / S - x) * sx + x) * S, ((py / S - y) * sy + y) * S) for (px, py) in pts]
                dr.polygon(pts, fill=mix(D_SHELL, (150, 40, 20), red * 0.5))
                dr.line(pts + [pts[0]], fill=D_SHELL_EDGE, width=max(2, int(4 * S)), joint="curve")
                if k == "T" and t >= 31.92:                         # la fente
                    c0 = a - half * 0.1
                    zz = []
                    for j in range(5):
                        rr = ri + (ro - ri) * j / 4
                        zz.append(((x + rr * math.cos(c0 + 0.06 * (1 if j % 2 else -1))) * S,
                                   (y + rr * math.sin(c0 + 0.06 * (1 if j % 2 else -1))) * S))
                    if rot == 0.0:
                        dr.line(zz, fill=(40, 12, 6), width=max(2, int(4 * S)))
        talk, line = self.talking(t)
        self.draw_face(dr, x, y, br, S, talk, line, red, sx, sy, self.eyes_state(t), t, 0.0)

    def draw_face(self, dr, x, y, r, S, talk, line, red, sx, sy, eyes, t, spin):
        ca, sa = math.cos(spin), math.sin(spin)

        def P(u, v):
            uu, vv = u * ca - v * sa, u * sa + v * ca
            return ((x + uu * r * sx) * S, (y + vv * r * sy) * S)
        w = max(2, int(0.11 * r * S))
        bx, by = self.bounce_at(t)
        look = max(-1.0, min(1.0, (bx - x) / 300.0)) * 0.06
        if eyes in ("sleep", "serene", "closing"):
            k = 1.0 if eyes != "closing" else ease((t - 59.85) / 0.5)
            # sourcils détendus, paupières mi-closes ou fermées
            dr.line([P(-0.70, -0.46), P(-0.14, -0.40)], fill=INK, width=w)
            dr.line([P(0.70, -0.46), P(0.14, -0.40)], fill=INK, width=w)
            for ex in (-0.34, 0.34):
                if eyes == "sleep":
                    dr.chord([P(ex - 0.13, -0.24)[0], P(ex - 0.13, -0.24)[1], P(ex + 0.13, 0.0)[0],
                              P(ex + 0.13, 0.0)[1]], 0, 180, fill=INK)
                else:
                    dr.arc([P(ex - 0.13, -0.24)[0], P(ex - 0.13, -0.24)[1], P(ex + 0.13, -0.02)[0],
                            P(ex + 0.13, -0.02)[1]], 10, 170, fill=INK, width=max(2, int(0.06 * r * S)))
            dr.line([P(-0.18, 0.42), P(0.18, 0.42)], fill=INK, width=max(2, int(0.06 * r * S)))
            return
        deep = 0.07 * red
        dr.line([P(-0.82, -0.66 - deep), P(-0.10, -0.08)], fill=INK, width=w)
        dr.line([P(0.80, -0.72 - deep), P(0.12, -0.10)], fill=INK, width=w)
        er = 0.085 + 0.02 * red + (0.05 if 58.1 <= t < 58.85 else 0.0)
        dy_e = 0.10 if eyes == "down" else 0.0
        for ex in (-0.34, 0.34):
            ey = -0.12 + dy_e
            ex2 = ex + (look if eyes != "down" else 0.0)
            a0, a1 = P(ex2 - er, ey - er), P(ex2 + er, ey + er)
            dr.ellipse([min(a0[0], a1[0]), min(a0[1], a1[1]), max(a0[0], a1[0]), max(a0[1], a1[1])], fill=INK)
        if talk > 0.08:
            op = 0.10 + 0.32 * talk * (1.25 if line in ("hurle", "lent", "furax") else 1.0)
            top = [(-0.42, 0.40), (-0.24, 0.34), (-0.06, 0.38), (0.12, 0.33), (0.30, 0.36), (0.44, 0.33)]
            bot = [(0.40, 0.36 + op), (0.20, 0.40 + op), (0.0, 0.42 + op), (-0.22, 0.40 + op), (-0.40, 0.42 + 0.4 * op)]
            dr.polygon([P(u, v) for u, v in top + bot], fill=INK)
            dr.polygon([P(-0.30, 0.37), P(0.30, 0.355), P(0.28, 0.40), P(-0.28, 0.41)], fill=(240, 236, 228))
        else:
            pts = [(-0.46, 0.54), (-0.40, 0.45), (-0.26, 0.39), (-0.12, 0.40), (-0.02, 0.45), (0.10, 0.44),
                   (0.20, 0.36), (0.34, 0.33), (0.52, 0.33), (0.54, 0.38)]
            dr.line([P(u, v) for u, v in pts], fill=INK, width=max(2, int(0.075 * r * S)), joint="curve")

    def draw_conf_piece(self, dr, x, y, rot, ph, col, sz, S, t):
        flut = abs(math.cos(ph + t * 7.0))
        w2, h2 = 10 * sz * (0.25 + 0.75 * flut), 6 * sz
        ca, sa = math.cos(rot), math.sin(rot)
        pts = [((x + u * ca - v * sa) * S, (y + u * sa + v * ca) * S) for u, v in
               ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2))]
        dr.polygon(pts, fill=CONF_COLS[int(col)])

    def draw_star(self, dr, x, y, u, S):
        r = 34 + 46 * u
        col = mix((255, 255, 255), BG, u * 0.7)
        for j in range(8):
            a = j * math.pi / 4
            rr = r if j % 2 == 0 else r * 0.6
            dr.line([(x + 0.25 * rr * math.cos(a)) * S, (y + 0.25 * rr * math.sin(a)) * S,
                     (x + rr * math.cos(a)) * S, (y + rr * math.sin(a)) * S], fill=col, width=max(2, int(7 * S)))
        dr.ellipse([(x - 16) * S, (y - 16) * S, (x + 16) * S, (y + 16) * S], fill=col)

    def draw(self, dr, snap, t, S):
        t, C, steam = snap

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        # le jardin
        rect(0, 520, W, GRASS_Y, FENCE)
        for xx in range(0, W + 1, 90):
            dr.line([(xx * S, 520 * S), (xx * S, GRASS_Y * S)], fill=FENCE_LINE, width=max(1, int(3 * S)))
        rect(0, 600, W, 612, FENCE_LINE)
        rect(0, 1380, W, 1392, FENCE_LINE)
        rect(0, GRASS_Y, W, H, GRASS)
        for (bxx, byy, brr) in ((90, 1600, 120), (230, 1660, 90), (980, 1640, 130), (840, 1720, 80), (520, 1760, 70)):
            dr.ellipse([(bxx - brr) * S, (byy - brr * 0.7) * S, (bxx + brr) * S, (byy + brr * 0.7) * S], fill=(12, 34, 24))
            dr.ellipse([(bxx - brr * 0.6) * S, (byy - brr * 0.9) * S, (bxx + brr * 0.5) * S, (byy) * S], fill=(16, 42, 30))
        for (fx, fy) in ((150, 1540), (420, 1580), (660, 1620), (300, 1730), (760, 1560), (940, 1530)):
            dr.ellipse([(fx - 7) * S, (fy - 7) * S, (fx + 7) * S, (fy + 7) * S], fill=(70, 60, 90))
        for i in range(40):
            gx = (i * 137) % W
            dr.line([(gx * S, (GRASS_Y + 4) * S), ((gx + 8) * S, (GRASS_Y - 14) * S)], fill=GRASS_HI,
                    width=max(1, int(3 * S)))
        # le trampoline : pieds, cadre, ressorts, toile
        for (xa, xb) in ((240, 220), (980, 1000), (560, 550), (780, 790)):
            dr.line([(xa * S, (MAT_Y + 26) * S), (xb * S, GRASS_Y * S)], fill=FRAME, width=int(14 * S))
        rect(180, MAT_Y + 18, 1060, MAT_Y + 36, FRAME)
        N = 72
        xs = [X0 + (X1 - X0) * i / N for i in range(N + 1)]
        ys = [self.mat_y(xx, t) for xx in xs]
        zz = []
        for j in range(9):
            u = j / 8
            zz.append((lerp(1056, X1, u) * S, (lerp(MAT_Y + 6, ys[-1], u) + (7 if j % 2 else -7) * (0 < j < 8)) * S))
        dr.line(zz, fill=(150, 150, 170), width=int(3 * S))
        poly = [(xx * S, yy * S) for xx, yy in zip(xs, ys)] + [(xx * S, (yy + 12) * S) for xx, yy in
                                                                 reversed(list(zip(xs, ys)))]
        dr.polygon(poly, fill=MAT_COL)
        dr.line([(xx * S, yy * S) for xx, yy in zip(xs, ys)], fill=MAT_EDGE, width=int(4 * S))
        # le coussin : il se creuse sous Bounce
        bx, by = self.bounce_at(t)
        depth = 0.0
        for c in self.C:
            if c["k"] == "P" and c["t"] <= t <= c["t"] + c["d"]:
                depth = self.surf_y(c, t) - PAD_Y
        top = []
        for i in range(25):
            xx = PAD_X0 + (PAD_X1 - PAD_X0) * i / 24
            dd = depth * max(0.0, 1 - ((xx - bx) / 150.0) ** 2)
            top.append((xx, PAD_Y + dd))
        dr.polygon([(x * S, y * S) for x, y in top] + [(PAD_X1 * S, (MAT_Y + 70) * S), (PAD_X0 * S, (MAT_Y + 70) * S)],
                   fill=PAD_COL)
        for xx in (250, 310, 370):
            dr.line([(xx * S, (PAD_Y + 30) * S), (xx * S, (MAT_Y + 60) * S)], fill=PAD_LO, width=max(1, int(3 * S)))
        dr.line([(x * S, y * S) for x, y in top], fill=PAD_HI, width=int(6 * S))
        rect(PAD_X0, MAT_Y + 62, PAD_X1, MAT_Y + 70, PAD_LO)
        # les morceaux tombés (derrière les personnages)
        for p in self.pieces:
            if t >= p["t0"] and (t < T_POP or p["k"] == "T"):
                px, py, rot = self.piece_pos(p, t)
                if p["k"] == "T" and t >= T_POP:
                    continue
                dr.polygon(self.loose_piece_poly(px, py, rot, S), fill=D_SHELL, outline=D_SHELL_EDGE)
        # confettis posés
        if C is not None:
            for i in np.where((C["st"] == 1) | (C["st"] == 5) | (C["st"] == 6))[0]:
                x = C["x"][i]
                if C["st"][i] == 1:
                    y = self.mat_y(x, t) - 4
                elif C["st"][i] == 6:
                    y = PAD_Y - 4
                else:
                    y = C["y"][i]
                self.draw_conf_piece(dr, x, y, C["rot"][i], 0.0, C["col"][i], C["sz"][i], S, 0.0)
        self.draw_detonate(dr, t, S, "halo")
        base.ball(dr, bx * S, by * S, RB * S)
        if C is not None:
            for i in np.where(C["st"] == 2)[0]:
                self.draw_conf_piece(dr, bx + C["rx"][i], by + C["ry"][i], C["rot"][i], 0.0,
                                     C["col"][i], C["sz"][i], S, 0.0)
        self.draw_detonate(dr, t, S, "body")
        # l'éclatement : un anneau de lumière
        if 0 <= t - T_POP < 0.25:
            u = (t - T_POP) / 0.25
            dx, dy, _ = self.det_at(T_POP)
            rr = 167 * (1.0 + 1.4 * u)
            dr.ellipse([(dx - rr) * S, (dy - rr) * S, (dx + rr) * S, (dy + rr) * S],
                       outline=mix(BG, (255, 245, 220), 1 - u), width=int((16 - 11 * u) * S))
        # étoiles des morceaux arrachés
        for (tl, k) in self.stars:
            if 0 <= t - tl < 8 / 60:
                dx, dy, spin = self.det_at(tl)
                a = math.radians(SEG[k]) + spin
                rc = 0.5 * (1 + KI) * self.size_v(tl)
                self.draw_star(dr, dx + rc * math.cos(a), dy + rc * math.sin(a), (t - tl) * 60 / 8, S)
        # vapeur
        for s in steam:
            age = (t - s[3]) / s[4]
            col = mix((246, 246, 250), (150, 152, 170), age)
            rr = s[2] * (1.0 - 0.6 * max(0.0, age - 0.6) / 0.4)
            dr.ellipse([(s[0] - rr) * S, (s[1] - rr) * S, (s[0] + rr) * S, (s[1] + rr) * S], fill=col)
        if C is not None:
            for i in np.where(C["st"] == 0)[0]:
                self.draw_conf_piece(dr, C["x"][i], C["y"][i], C["rot"][i], C["ph"][i], C["col"][i],
                                     C["sz"][i], S, t)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0,
            "hook_text_s": 999.0, "hook_top": 0.125, "hook_font_size": 96}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
