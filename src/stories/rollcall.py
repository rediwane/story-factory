"""
Prototype « l'appel » : tous les personnages de l'univers de Bounce, sur une scène. Bounce rebondit
sur la tête de chacun ; le narrateur le présente, il dit son nom (Still, elle, ne dit rien). À la fin,
le narrateur demande qui devrait les rejoindre. Les dessins et les voix sont ceux des vidéos déjà
publiées (scripts des branches proto-*, banques hors dépôt, chemins dans la config).

    python3 src/stories/rollcall.py configs/<name>.json [--simulate]
"""
import math, sys, os, wave, importlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import base
import voice as narr_voice
import audio_kit as ak
ORIG = (narr_voice.say, base.subtitle_at, base.build_narration, base.hero_word)
SR = ak.SR


def load_cfg_paths():
    import json
    cfg = json.load(open(sys.argv[1]))
    return cfg


_cfg0 = load_cfg_paths()
for p in _cfg0["draw_from"]:
    sys.path.insert(0, p)
clip4 = importlib.import_module("clip4")
beam = importlib.import_module("beam")
fall = importlib.import_module("fall")
blub = importlib.import_module("blub")
crush = importlib.import_module("crush")
narr_voice.say, base.subtitle_at, base.build_narration, base.hero_word = ORIG       # nos propres réglages

BANK = {}


def _read(path):
    with wave.open(path) as w:
        n, fr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != SR:
        x = np.interp(np.arange(int(len(x) * SR / fr)) / SR, np.arange(len(x)) / fr, x)
    x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
    return x * 0.2


def say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text.startswith("@"):
        return BANK[text].copy()
    return ORIG[0](text, voice, length_scale, sr)


narr_voice.say = say
_sub = ORIG[1]
base.subtitle_at = lambda narr, t, n: _sub([x for x in narr if not x["text"].startswith("@")], t, n)


def build_keep(sim, cfg):
    narr, rep = ORIG[2](sim, cfg)
    sim.narr = narr
    return narr, rep


base.build_narration = build_keep
_memo = {}


def steady(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _memo:
        best = None
        for _ in range(12):
            v = ORIG[3](text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if text != cfg["hero_name"] or len(v) / SR <= 0.78:
                break
        _memo[key] = best
    return None if _memo[key] is None else _memo[key].copy()


base.hero_word = steady

W, H = 1080, 1920
RB = 62.0
G = 2600.0
SHELF = 1010.0
FLOOR = 1500.0
CAST = [  # nom, x, rayon, rangée (0 = l'étagère, 1 = le sol), réplique du narrateur
    ("Float", 170.0, 62.0, 0, "She just wants a bath."),
    ("Snooze", 400.0, 62.0, 0, "He sleeps through anything."),
    ("Still", 640.0, 62.0, 0, "She never moves."),
    ("Beam", 880.0, 62.0, 0, "Don't make him sneeze."),
    ("Fall", 200.0, 62.0, 1, "He loves falling."),
    ("Blub", 520.0, 62.0, 1, "Don't let him talk."),
    ("Crush", 840.0, 92.0, 1, "He breaks everything."),
]


def lerp(a, b, s):
    return a + (b - a) * s


def arc(t, t0, x0, y0, t1, x1, y1):
    d = max(1e-6, t1 - t0)
    s = (t - t0) / d
    h = min(0.5 * G * (d / 2) ** 2, 700.0)
    top = max(min(y0, y1) - h, 560.0)
    a0, a1 = max(0.0, y0 - top), max(0.0, y1 - top)
    sm = math.sqrt(a0) / (math.sqrt(a0) + math.sqrt(a1) + 1e-9)
    if s <= sm:
        u = s / sm if sm > 0 else 1
        y = top + a0 * (1 - u) ** 2
    else:
        u = (s - sm) / (1 - sm) if sm < 1 else 1
        y = top + a1 * u ** 2
    return lerp(x0, x1, s), y


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        for key, path in cfg["voices"].items():
            BANK["@" + key] = _read(path)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        L, C = [], []
        self.pos = {}
        for name, x, r, row, _ in CAST:
            y = (SHELF if row == 0 else FLOOR) - r
            self.pos[name] = (x, y, r)
        t0 = 3.4
        self.spot = []
        GAP_SOFT, GAP_HARD = 360.0, 665.0          # au sol : un coussin (mou) entre Fall et Blub, le plancher entre Blub et Crush
        fy = FLOOR - RB
        for k, (name, x, r, row, fact) in enumerate(CAST):
            T = t0 + 7.0 * k
            cx, cy, cr = self.pos[name]
            L.append((T, f"This is {name}.", f"n{k}"))
            C.append((T + 1.6, cx, cy - cr - RB, True))      # Bounce sur sa tête
            if name != "Still":
                L.append((T + 2.5, "@" + name, f"v{k}"))
            L.append((T + 3.6, fact, f"f{k}"))
            C.append((T + 3.3, GAP_SOFT, fy + 14, False))    # le coussin, pendant que ça parle
            C.append((T + 5.2, GAP_HARD, fy, True))          # le plancher, dans le silence
            C.append((T + 6.2, GAP_SOFT, fy + 14, False))
            C.append((T + 7.4, GAP_SOFT, fy + 14, False))
            self.spot.append((T, T + 7.0, name))
        T = t0 + 7.0 * len(CAST)
        L.append((T, "Who should join next?", "q1"))
        L.append((T + 2.0, "Draw them in the comments.", "q2"))
        C = [c for c in C if c[0] < T + 0.3]
        C.append((T + 1.0, GAP_SOFT, fy + 14, False)); C.append((T + 2.3, GAP_SOFT, fy + 14, False))
        tt = T + 3.6
        C.append((tt, GAP_HARD, fy, True))
        while tt < 60.6:
            tt += 0.95
            C.append((tt, GAP_HARD + (25 if len(C) % 2 else -25), fy, True))
        self.T_end = T
        self.lines = L
        self.C = sorted(C)
        self.hits = [(c[0], "dur") for c in self.C if c[3]]
        self.C = [c[:3] for c in self.C]
        self.hi = 0
        self.end_s = 61.6
        self.payoff_at = 61.0

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 540.0, 700.0, *C[0])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                return arc(t, *a, *b)
        return C[-1][1], C[-1][2]

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "fin"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def speaking(self, t, name):
        for n in self.narr:
            if n["text"] == "@" + name and n["start"] <= t <= n["end"] + 0.2:
                return True
        return False

    def draw(self, dr, snap, t, S):
        wall = (24, 24, 36)
        dr.rectangle([0, 470 * S, W * S, FLOOR * S], fill=wall)
        dr.rectangle([0, FLOOR * S, W * S, H * S], fill=(14, 14, 20))
        cur = None
        for (a, b, name) in self.spot:
            if a <= t < b:
                cur = name
        if t >= self.T_end:
            cur = "all"
        for name, x, r, row, _ in CAST:
            if cur == name or cur == "all":
                cx, cy, cr = self.pos[name]
                k = 0.45 if cur == name else 0.18
                dr.polygon([((cx - 40) * S, 470 * S), ((cx + 40) * S, 470 * S), ((cx + 2.2 * cr) * S, (cy + cr) * S), ((cx - 2.2 * cr) * S, (cy + cr) * S)],
                           fill=base.dim((255, 255, 255), 0.0) if False else tuple(int(w + (90 - w) * k) for w in wall))
        dr.rectangle([60 * S, SHELF * S, 1020 * S, (SHELF + 22) * S], fill=(96, 72, 54))
        dr.rounded_rectangle([280 * S, (FLOOR - 28) * S, 440 * S, (FLOOR + 6) * S], radius=16 * S, fill=(150, 70, 110))
        sq_hits = {name: [c[0] for c in self.C if abs(c[1] - self.pos[name][0]) < 1 and c[2] < self.pos[name][1]] for name, *_ in CAST}

        def sq(name):
            v = 0.0
            for th in sq_hits[name]:
                d = t - th
                if 0 <= d < 0.4:
                    v = max(v, 0.12 * math.exp(-d * 8))
            return v
        for name, x, r, row, _ in CAST:
            cx, cy, cr = self.pos[name]
            s = sq(name)
            talk = 0.8 * abs(math.sin(t * 14)) if self.speaking(t, name) else 0.0
            if name == "Float":
                dr.rounded_rectangle([(cx - 85) * S, (cy + 10) * S, (cx + 85) * S, (SHELF) * S], radius=16 * S, fill=(232, 236, 244))
                clip4.RF = cr
                clip4.draw_float(dr, clip4.VIEW, cx, cy - 6, 0.0, clip4.EXPR["serene" if not talk else "slit"], (0.0, 0.0), talk, 0.0, 0.0)
                dr.rectangle([(cx - 85) * S, (cy + 30) * S, (cx + 85) * S, SHELF * S], fill=(232, 236, 244))
            elif name == "Snooze":
                clip4.draw_snooze(dr, cx, cy, cr, talk=talk, smile=not talk, sq=s)
            elif name == "Still":
                clip4.draw_still(dr, cx, cy, cr, sq=s * 0.6)
            elif name == "Beam":
                beam.draw_beam(dr, cx, cy, cr, S, squint=1.0 if talk else 0.0, sq=s)
                if self.speaking(t, name):
                    dr.line([((cx - 0.7 * cr) * S, cy * S), (30 * S, cy * S)], fill=(255, 90, 100), width=int(18 * S))
            elif name == "Fall":
                fall.draw_fall(dr, cx, cy, cr, S, mood="joie", talk=talk, sq=s)
            elif name == "Blub":
                blub.draw_blub(dr, cx, cy, cr, S, mood="joie" if not talk else "peur", talk=talk, sq=s)
            elif name == "Crush":
                crush.draw_crush(dr, cx, cy, cr, S, mood="joie" if cur == "Crush" else "neutre", sq=s)
            if cur == "all" or cur == name:
                dr.text((cx * S, (cy + cr + 40) * S), name.upper(), fill=(235, 235, 245), anchor="mm", font=base.font(int(30 * S)),
                        stroke_width=int(3 * S), stroke_fill=(0, 0, 0))
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, by * S, RB * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.6,
            "sub_y": 0.84, "sub_font_size": 56}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
