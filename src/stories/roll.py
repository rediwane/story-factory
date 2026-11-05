"""
Prototype « Roll » : le personnage d’un fan (Roll, une balle verte qui roule d’avant en arrière, au
hasard) et Bounce. Roll passe toujours pile sous Bounce quand il retombe : Bounce part valser contre les
murs, Roll adore. Bounce finit par le chevaucher ; puis Roll le fauche, et Bounce roule pour la première
fois de sa vie : « Roll. »

Roll ne dit que son nom (banque hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/roll.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------------------------------------------------ la voix de Snooze
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
    for key, fn in LINES.items():
        x = _read(os.path.join(path, fn))
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2 * (GAIN.get(key, 1.0))
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def snooze_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = snooze_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Snooze suit sa voix
    return narr, replies


base.build_narration = build_narration_keep

# ------------------------------------------------------------------ le mot de Bounce
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word



# ------------------------------------------------------------------ Roll
WHO = "Roll"
LINES = {"joie": "joie.wav", "q": "q.wav", "long": "long.wav"}
GAIN = {}

W, H = 1080, 1920
R = 100.0
RB = 100.0
CEIL = 470.0
FLOOR = 1500.0
FY = FLOOR - RB
G = 2600.0
WALL_L, WALL_R = 40.0, 1040.0
R_DISC, R_RING, R_HALO, R_INK = (26, 236, 40), (22, 70, 26), (10, 32, 14), (10, 12, 10)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def arc(t, t0, x0, y0, t1, x1, y1, cap=CEIL + RB):
    d = max(1e-6, t1 - t0)
    s = (t - t0) / d
    h = min(0.5 * G * (d / 2) ** 2, 700.0)
    top = max(min(y0, y1) - h, cap)
    a0, a1 = max(0.0, y0 - top), max(0.0, y1 - top)
    sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
    if s <= sm:
        u = s / sm if sm > 0 else 1
        y = top + a0 * (1 - u) ** 2
    else:
        u = (s - sm) / (1 - sm) if sm < 1 else 1
        y = top + a1 * u ** 2
    return lerp(x0, x1, s), y


def draw_roll(dr, x, y, r, S, rot=0.0, talk=0.0, sq=0.0):
    """Roll, d'après le dessin du fan, aux proportions de Bounce : un disque vert vif cerclé de
    vert foncé, deux yeux en accent circonflexe, une grande bouche ouverte. Il tourne quand il roule."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=R_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=R_RING)
    dr.ellipse([(x - 0.8 * r * sx) * S, (y - 0.8 * r * sy) * S, (x + 0.8 * r * sx) * S, (y + 0.8 * r * sy) * S], fill=R_DISC)
    ca, sa = math.cos(rot), math.sin(rot)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.11 * r * S))
    for side in (-1, 1):
        ex = 0.30 * side
        dr.line([P(ex - 0.16, -0.12), P(ex, -0.30), P(ex + 0.16, -0.12)], fill=R_INK, width=w, joint="curve")
    o = 0.28 + 0.12 * talk
    pts = [P(0.30 * math.cos(math.pi * k / 16), 0.10 + o * math.sin(math.pi * k / 16)) for k in range(17)]
    dr.polygon(pts, fill=R_INK)


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        C, L = [], []
        rk = []                                          # (t, x) : les positions de Roll

        def c(t, x, y, hard=True):
            C.append((t, float(x), float(y), hard))
        head_y = FY - 2 * R                             # Bounce posé sur Roll
        # l'intro : Bounce rebondit, Roll arrive en roulant de la droite
        for i, x in enumerate((300, 400, 330)):
            c(0.6 + 1.0 * i, x, FY)
        rk += [(0.0, 940.0), (1.4, 940.0)]
        # cinq fois : Roll passe pile dessous, Bounce lui tombe dessus et part valser
        flings = [(3.7, 520, (WALL_L + RB, 1180)), (8.0, 610, (WALL_R - RB, 1100)), (12.3, 420, (500, CEIL + RB)),
                  (16.6, 700, (WALL_L + RB, 1060)), (20.9, 480, (WALL_R - RB, 1180))]
        for k, (th, xh, (wx, wy)) in enumerate(flings):
            rk.append((th - 1.3 + 0.3 * (k % 2), xh + (140 if k % 2 else -140)))   # un aller-retour au hasard
            rk.append((th - 0.25, xh)); rk.append((th + 0.35, xh + (60 if k % 2 else -60)))
            c(th, xh, head_y)                            # sur Roll
            L.append((th + 0.92, "joie"))                # « Roll! » : il adore
            c(th + 1.55, wx, wy)                         # éjecté : le mur, ou le plafond
            fx = 300 if wx > 540 else 780
            c(th + 2.5, fx, FY)
            c(th + 3.4, fx + (90 if fx < 540 else -90), FY)
            rk.append((th + 2.6, 900 - fx * 0.6 + 200))
        # la balade : Bounce reste sur Roll, qui roule d'un bout à l'autre
        t = 25.2
        rk.append((t - 0.6, 380.0)); rk.append((t, 400.0))
        ride = [(25.2, 400), (26.7, 560), (28.2, 720), (29.7, 860), (31.2, 700), (32.7, 520), (34.2, 340), (35.7, 230)]
        for i, (tr, xr) in enumerate(ride):
            rk.append((tr, float(xr)))
            c(tr, xr, head_y)
            if i in (1, 4, 6):
                L.append((tr + 0.9, "joie"))
        # Roll s'arrête net : Bounce est projeté en avant ; Roll repart dessous… et le renverse
        rk.append((36.5, 230.0)); rk.append((36.9, 230.0))
        c(36.9, 520, FY); c(37.8, 640, FY); c(38.7, 560, FY)
        rk.append((39.3, 700.0)); rk.append((40.1, 590.0))
        self.t_knock = 40.1                              # Roll lui fauche le dessous : Bounce tombe et roule
        c(40.1, 600, FY)
        self.t_up = 46.6                                 # il roule jusqu'au mur, puis se remet à rebondir
        self.roll_path = (600.0, 960.0)
        rk.append((44.0, 520.0)); rk.append((46.0, 430.0))
        L.append((self.t_knock + 3.6, "q"))              # « Roll? » : Roll n'en revient pas
        c(self.t_up, 960, FY)
        t = self.t_up
        for x in (880, 790, 700):
            t += 0.95; c(t, x, FY)
        # et ça recommence : Roll repasse dessous
        rk.append((t - 1.0, 330.0)); rk.append((t + 1.4, 600.0))
        t += 1.4; c(t, 600, head_y)
        rk.append((t + 0.5, 660.0))
        L.append((t + 0.92, "joie"))
        c(t + 1.55, WALL_R - RB, 1150); c(t + 2.5, 760, FY)
        tt = t + 2.5
        while tt < 61.0:
            tt += 0.95; c(tt, 760 + (40 if len(C) % 2 else -40), FY)
        rk.append((61.8, 300.0))
        self.C = sorted(C)
        self.rk = sorted(rk)
        self.hits = [(e[0], "dur") for e in self.C if e[3] and not (self.t_knock < e[0] < self.t_up)]
        self.hi = 0
        self.lines = [(tl, WHO + " " + k, f"r{i}") for i, (tl, k) in enumerate(sorted(L))]
        self.payoff_at = self.t_knock + 0.6
        self.end_s = 61.8
        self.head_hits = [e[0] for e in self.C if abs(e[2] - head_y) < 1]

    def roll_x(self, t):
        rk = self.rk
        if t <= rk[0][0]:
            return rk[0][1]
        for a, b in zip(rk, rk[1:]):
            if a[0] <= t <= b[0]:
                return lerp(a[1], b[1], ease((t - a[0]) / max(1e-6, b[0] - a[0])))
        return rk[-1][1]

    def bounce_at(self, t):
        if self.t_knock <= t <= self.t_up:              # il roule, pour la première fois
            s = (t - self.t_knock) / (self.t_up - self.t_knock)
            x = lerp(self.roll_path[0], self.roll_path[1], 1 - (1 - s) ** 2)
            return x, FY, (x - self.roll_path[0]) / RB
        C = self.C
        if t <= C[0][0]:
            return (*arc(t, -0.5, 200.0, 800.0, C[0][0], C[0][1], C[0][2]), None)
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                x0, y0 = a[1], a[2]
                x1, y1 = b[1], b[2]
                head_y = FY - 2 * R
                if abs(y0 - head_y) < 1 and b[0] - a[0] < 1.45 and abs(y1 - head_y) < 1:
                    pass
                return (*arc(t, a[0], x0, y0, b[0], x1, y1), None)
        return C[-1][1], C[-1][2], None

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "il roule"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                return 0.0 if e is None else float(e[min(int((t - n["start"]) * 60), len(e) - 1)])
        return 0.0

    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        wall = (28, 30, 40)
        rect(0, CEIL, W, FLOOR, wall)
        rect(0, CEIL - 8, W, CEIL, dim(wall, 0.6))
        rect(0, FLOOR, W, H, (52, 40, 34))
        for i in range(12):                              # le parquet
            dr.line([(i * 96 * S, FLOOR * S), (i * 96 * S, (FLOOR + 30) * S)], fill=(40, 30, 26), width=int(3 * S))
        rect(0, CEIL, WALL_L, FLOOR, (40, 42, 54)); rect(WALL_R, CEIL, W, FLOOR, (40, 42, 54))
        dr.rectangle([300 * S, 640 * S, 560 * S, 900 * S], fill=(16, 18, 34), outline=(60, 58, 70), width=int(10 * S))
        dr.ellipse([480 * S, 680 * S, 530 * S, 730 * S], fill=(230, 228, 200))
        # Roll : il tourne en roulant
        rx = self.roll_x(t)
        sq = 0.0
        for th in self.head_hits:
            if 0 <= t - th < 0.4:
                sq = 0.12 * math.exp(-(t - th) * 8)
        draw_roll(dr, rx, FY - sq * R * 0.5, R, S, rot=0.45 * math.sin((rx - 940.0) / R), talk=self.talking(t), sq=sq)
        bx, by, tilt = self.bounce_at(t)
        if tilt is not None:
            base.HERO["tilt"] = tilt
        base.ball(dr, bx * S, by * S, RB * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4,
            "hero_lose": "Roll."}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
