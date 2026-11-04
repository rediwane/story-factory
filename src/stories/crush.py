"""
Prototype « Crush » : le personnage d’un fan (Crush, une grosse balle qui écrase tout ce sur quoi elle
atterrit) veut rebondir comme Bounce. Chaque fois que Bounce rebondit sur un meuble, Crush saute dessus et
l’écrase. Bounce lui montre comment faire ; le plancher se fend ; au dernier saut, il cède, et les deux
tombent chez Snooze, qui dort à l’étage du dessous depuis le début.

Crush ne dit que son nom (banque hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/crush.py configs/<name>.json [--simulate]
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



# ------------------------------------------------------------------ Crush
WHO = "Crush"
LINES = {"crush": "crush.wav", "fort": "fort.wav", "q": "q.wav"}
GAIN = {"fort": 1.15, "crush": 0.8}

W, H = 1080, 1920
R = 100.0
RB = 100.0
RC = 150.0                         # Crush : plus gros que tout le monde
CEIL = 470.0
G = 2600.0
F1 = 1250.0                        # le plancher du haut (dur)
F0 = 1800.0                        # le sol du bas
HOLE = (330.0, 790.0)              # là où le plancher cédera
CHAIR = (130.0, 250.0, 1130.0)     # x0, x1, assise
TABLE = (330.0, 590.0, 1060.0)     # x0, x1, plateau
WARD = (660.0, 790.0, 900.0)       # l'armoire : x0, x1, dessus
C_DISC, C_HALO, C_EYE, C_PUP = (40, 84, 164), (16, 30, 66), (140, 204, 242), (26, 52, 104)
WALL_UP, WALL_DN = (34, 30, 42), (22, 22, 34)
def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def arc(t, t0, x0, y0, t1, x1, y1, cap=CEIL + RB, g=G):
    d = max(1e-6, t1 - t0)
    s = (t - t0) / d
    h = min(0.5 * g * (d / 2) ** 2, 760.0)
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




def draw_crush(dr, x, y, r, S, mood="neutre", sq=0.0):
    """Crush, d'après le dessin du fan mais en boule nette : un grand disque bleu foncé, deux
    grands yeux bleu clair, pas de bouche."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=C_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=C_DISC)
    for side in (-1, 1):
        ex, ey = x + 0.34 * r * side * sx, y - 0.18 * r * sy
        rw, rh = 0.24 * r, 0.30 * r * (0.55 if mood == "triste" else 1.0)
        dr.ellipse([(ex - rw) * S, (ey - rh) * S, (ex + rw) * S, (ey + rh) * S], fill=C_EYE)
        pr = 0.10 * r
        py = ey + (0.08 * r if mood == "triste" else 0.0)
        dr.ellipse([(ex - pr) * S, (py - pr) * S, (ex + pr) * S, (py + pr) * S], fill=C_PUP)
        if mood == "triste":
            dr.line([((ex - rw) * S, (ey - rh - 6) * S), ((ex + rw) * S, (ey - rh + 8 * side) * S)], fill=C_PUP, width=int(8 * S))
        if mood == "joie":
            dr.ellipse([(ex - 0.07 * r) * S, (ey - 0.16 * r) * S, (ex + 0.0) * S, (ey - 0.09 * r) * S], fill=(240, 248, 255))


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        C, K, L = [], [], []                        # contacts de Bounce, de Crush ; répliques
        by_floor, cy_floor = F1 - RB, F1 - RC

        def c(t, x, y, hard=True):
            C.append((t, float(x), float(y), hard))
        self.crushed = {}                           # objet -> instant où Crush l'écrase
        # l'intro : Bounce au sol, Crush à droite qui le regarde
        for i, x in enumerate((300, 240, 300)):
            c(0.6 + 0.9 * i, x, by_floor)
        K.append((0.0, 930.0, cy_floor))
        # trois fois : Bounce rebondit sur un meuble, Crush saute dessus et l'écrase
        plan = [("chaise", (CHAIR[0] + CHAIR[1]) / 2, CHAIR[2], 3.0), ("table", 460.0, TABLE[2], 9.6), ("armoire", 725.0, WARD[2], 16.2)]
        targets_after = [(430, by_floor), (880 - 0, by_floor), (300, by_floor)]
        for (obj, ox, top, tb), (ax, ay) in zip(plan, targets_after):
            c(tb, ox, top - RB)                     # Bounce sur le meuble
            c(tb + 1.05, ax, ay)                    # il en descend
            c(tb + 2.0, ax + (60 if ax < 540 else -60), ay)
            tk = tb + 2.7                           # Crush atterrit dessus
            K.append((tk - 1.25, K[-1][1], K[-1][2]))
            K.append((tk, ox, top - RC + 30))
            self.crushed[obj] = tk
            L.append((tk + 0.08, "fort" if obj == "armoire" else "crush"))
            K.append((tk + 0.9, ox, cy_floor))       # il se pose au sol, au milieu des débris
            c(tb + 3.0, ax + (20 if ax < 540 else -20), ay)
            c(tb + 4.0, ax + (80 if ax < 540 else -80), ay)
            c(tb + 5.0, ax + (30 if ax < 540 else -30), ay)
            c(tb + 6.0, ax + (90 if ax < 540 else -90), ay)
        L.append((23.0, "q"))                       # « Crush? » : il voudrait juste rebondir
        # Bounce lui montre : il lui rebondit sur la tête, et lui apprend à sauter tout doucement
        t = 23.8
        hx = K[-1][1]
        for k in range(3):
            t += 1.0
            c(t, hx, cy_floor - RC - RB)
        t += 1.0; c(t, 560 if hx < 540 else 420, by_floor)
        self.crack = []
        for k in range(3):                          # trois petits sauts de Crush : le plancher se fend
            tk = t + 1.2 + 2.9 * k
            K.append((tk - 0.7, hx, cy_floor)); K.append((tk, hx + 15 * (k % 2), cy_floor))
            self.crack.append(tk)
            c(tk - 0.5, 300 if hx > 540 else 820, by_floor); c(tk + 0.6, 260 if hx > 540 else 860, by_floor)
        L.append((self.crack[1] + 0.1, "crush"))
        t = self.crack[-1] + 1.5
        # le final : Bounce rebondit au milieu, sur les fissures ; Crush prend son plus grand élan
        for k in range(6):
            t += 0.95
            c(t, 540 + (40 if k % 2 else -40), by_floor)
        self.t_break = t + 1.2
        K.append((self.t_break - 1.5, K[-1][1], cy_floor))
        K.append((self.t_break, 600.0, cy_floor))
        c(self.t_break, 520.0, by_floor)            # Bounce est au sol quand Crush arrive
        L.append((self.t_break + 0.05, "fort"))
        # la chute à l'étage du dessous, chez Snooze qui dort
        self.t_down = self.t_break + 1.0
        K.append((self.t_down, 640.0, F0 - RC))
        c(self.t_down, 860.0, F0 - RB, hard=False)  # il tombe sur les gravats : le premier contact est sourd
        tt = self.t_down
        while tt < 61.8:
            tt += 1.0
            c(tt, 860.0 + (40 if len(C) % 2 else -40), F0 - RB)
        L.append((self.t_down + 4.6, "crush"))
        # en bas, Crush fait un tout petit saut… et le sol de chez Snooze se fend à son tour
        self.t_crack2 = self.t_down + 9.0
        K.append((self.t_crack2 - 0.6, 640.0, F0 - RC)); K.append((self.t_crack2, 650.0, F0 - RC))
        L.append((self.t_crack2 + 0.1, "q"))
        self.payoff_at = self.t_down + 1.6
        self.C, self.K = sorted(C), sorted(K)
        self.hits = [(e[0], "dur") for e in self.C if e[3] and e[0] > 0.3]
        self.hi = 0
        self.k_land = [e[0] for e in self.K[1:]]
        self.lines = [(tl, WHO + " " + k, f"c{i}") for i, (tl, k) in enumerate(sorted(L))]
        self.end_s = 61.8

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 200.0, 800.0, C[0][0], C[0][1], C[0][2])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                if a[0] < self.t_break <= b[0] or (a[0] >= self.t_break and a[0] < self.t_down):
                    s = (t - a[0]) / (b[0] - a[0])
                    return lerp(a[1], b[1], s), lerp(a[2], b[2], s * s)
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2])
        return C[-1][1], C[-1][2]

    def crush_at(self, t):
        K = self.K
        if t <= K[0][0]:
            return K[0][1], K[0][2]
        for a, b in zip(K, K[1:]):
            if a[0] <= t <= b[0]:
                if abs(a[1] - b[1]) < 1 and abs(a[2] - b[2]) < 1:
                    return a[1], a[2]
                if b[2] > F1:                      # la chute à travers le plancher
                    s = (t - a[0]) / (b[0] - a[0])
                    return lerp(a[1], b[1], s), lerp(a[2], b[2], s * s)
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2], g=G * 0.8)
        return K[-1][1], K[-1][2]

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "en bas"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        shake = 0.0
        for tk in self.k_land:
            if 0 <= t - tk < 0.35:
                shake = max(shake, 10 * (1 - (t - tk) / 0.35))
        oy = shake * math.sin(t * 90)
        broken = t >= self.t_break
        # l'étage du bas : la chambre de Snooze, qui dort
        rect(0, F1, W, F0, WALL_DN)
        rect(0, F0, W, H, (26, 22, 24))
        rect(160, F0 - 130, 520, F0 - 60, (210, 210, 222))
        rect(150, F0 - 260, 190, F0, (82, 60, 52)); rect(150, F0 - 60, 520, F0 - 30, (82, 60, 52))
        dr.rounded_rectangle([170 * S, (F0 - 180) * S, 330 * S, (F0 - 128) * S], radius=22 * S, fill=(236, 236, 244))
        sx_, sy_, sr = 250.0, F0 - 128 - 80 + 12, 80.0
        dr.ellipse([(sx_ - 1.6 * sr) * S, (sy_ - 1.6 * sr) * S, (sx_ + 1.6 * sr) * S, (sy_ + 1.6 * sr) * S], fill=(42, 42, 44))
        dr.ellipse([(sx_ - sr) * S, (sy_ - sr) * S, (sx_ + sr) * S, (sy_ + sr) * S], fill=(192, 192, 192))
        for ex in (-0.37, 0.37):
            cx, cy, er = sx_ + ex * sr, sy_ - 0.2 * sr, 0.29 * sr
            dr.ellipse([(cx - er) * S, (cy - er) * S, (cx + er) * S, (cy + er) * S], fill=(104, 104, 104), outline=(52, 52, 52), width=int(4 * S))
            dr.line([((cx - er * 0.8) * S, cy * S), ((cx + er * 0.8) * S, cy * S)], fill=(40, 40, 40), width=int(4 * S))
        dr.line([((sx_ - 0.3 * sr) * S, (sy_ + 0.4 * sr) * S), ((sx_ + 0.3 * sr) * S, (sy_ + 0.4 * sr) * S)], fill=(52, 52, 52), width=int(6 * S))
        for i in range(3):
            ph = (t * 0.6 + i / 3) % 1.0
            dr.text(((sx_ + 60 + 60 * ph) * S, (sy_ - sr - 20 - 110 * ph) * S), "z" if i % 2 else "Z",
                    fill=mix(WALL_DN, (170, 170, 200), min(1.0, ph * 3, (1 - ph) * 3)), anchor="mm", font=font(int((28 + 24 * ph) * S)))
        if t >= getattr(self, 't_crack2', 99):
            dr.line([(600 * S, F0 * S), (640 * S, (F0 + 30) * S), (610 * S, (F0 + 60) * S), (660 * S, (F0 + 90) * S)], fill=(10, 8, 8), width=int(7 * S))
        # l'étage du haut
        rect(0, CEIL, W, F1, WALL_UP)
        rect(0, CEIL - 8, W, CEIL, dim(WALL_UP, 0.6))
        # le plancher : fissures, puis le trou
        slab = (92, 70, 54)
        if broken:
            rect(0, F1 + oy, HOLE[0], F1 + 40 + oy, slab); rect(HOLE[1], F1 + oy, W, F1 + 40 + oy, slab)
            for j in range(9):
                dd = t - self.t_break
                qx = lerp(HOLE[0], HOLE[1], (j + 0.5) / 9)
                qy = min(F0 - 20, F1 + 20 + 600 * dd * dd + 40 * (j % 3))
                rect(qx - 26, qy - 12, qx + 26, qy + 12, slab)
        else:
            rect(0, F1 + oy, W, F1 + 40 + oy, slab)
            for k, tk in enumerate(self.crack):
                if t >= tk:
                    x0 = 420 + 90 * k
                    dr.line([(x0 * S, (F1 + oy) * S), ((x0 + 30) * S, (F1 + 18 + oy) * S), ((x0 + 10) * S, (F1 + 40 + oy) * S)], fill=(20, 16, 14), width=int(6 * S))
        # les meubles, intacts ou écrasés
        wood = (120, 86, 58)

        def flat(obj, x0, x1):
            tk = self.crushed[obj]
            k = min(1.0, max(0.0, (t - tk) / 0.12))
            return k
        k = flat("chaise", *CHAIR[:2])
        if k < 1:
            rect(CHAIR[0], CHAIR[2], CHAIR[1], CHAIR[2] + 18, wood); rect(CHAIR[0], CHAIR[2] - 130, CHAIR[0] + 18, F1, wood)
            rect(CHAIR[1] - 18, CHAIR[2], CHAIR[1], F1, wood)
        elif not broken or True:
            rect(CHAIR[0] - 30, F1 - 20, CHAIR[1] + 30, F1, wood)
        k = flat("table", *TABLE[:2])
        if k < 1:
            rect(TABLE[0], TABLE[2], TABLE[1], TABLE[2] + 22, wood); rect(TABLE[0] + 20, TABLE[2], TABLE[0] + 40, F1, wood); rect(TABLE[1] - 40, TABLE[2], TABLE[1] - 20, F1, wood)
        elif not broken:
            rect(TABLE[0] - 30, F1 - 22, TABLE[1] + 30, F1, wood)
        k = flat("armoire", *WARD[:2])
        if k < 1:
            rect(WARD[0], WARD[2], WARD[1], F1, (96, 70, 50)); dr.line([((WARD[0] + WARD[1]) / 2 * S, WARD[2] * S), ((WARD[0] + WARD[1]) / 2 * S, F1 * S)], fill=(60, 44, 32), width=int(4 * S))
        elif not broken:
            rect(WARD[0] - 40, F1 - 30, WARD[1] + 40, F1, (96, 70, 50))
        # Crush, puis Bounce
        cx, cy = self.crush_at(t)
        sq = 0.0
        for tk in self.k_land:
            if 0 <= t - tk < 0.4:
                sq = max(sq, 0.12 * math.exp(-(t - tk) * 7))
        mood = "neutre"
        if any(0.3 <= t - tk < 3.5 for tk in self.crushed.values()) or (self.crack and self.crack[0] <= t < self.crack[-1] + 1.5):
            mood = "triste"
        if self.crushed["armoire"] + 7.0 <= t < self.crack[0] or t >= self.t_down + 4.0:
            mood = "joie"
        draw_crush(dr, cx, cy + oy, RC, S, mood=mood, sq=sq)
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, (by + (oy if by < F1 else 0)) * S, RB * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
