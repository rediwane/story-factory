"""
Prototype « Beam » : le personnage d’un fan (Beam, une balle rouge à tête de mort dont l’éternuement est
un rayon) et Bounce, dans un grenier poussiéreux. Chaque rebond de Bounce soulève de la poussière vers
Beam ; son nez le chatouille, « Bea… », et chaque éternuement est un rayon. Les deux premiers ratent Bounce,
le troisième le carbonise. Bounce se secoue, repart… et le nez de Beam rechatouille.

Beam ne dit que son nom (banque de voix hors dépôt, cfg["voice_bank"]), sans sous-titre. Bounce ne s’arrête
jamais. Rien n’est ajouté au moteur.

    python3 src/stories/beam.py configs/<name>.json [--simulate]
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


# ------------------------------------------------------------------ Beam
WHO = "Beam"
LINES = {"bea": "bea.wav", "beabea": "beabea.wav", "cri": "cri.wav", "petit": "petit.wav"}
GAIN = {"cri": 1.15, "petit": 0.8}

W, H = 1080, 1920
R = 100.0
RB = 100.0
CEIL = 470.0
FLOOR = 1500.0
FY = FLOOR - RB
G = 2600.0
BX, BY = 800.0, FLOOR - R          # Beam, assis au sol à droite, tourné vers la gauche
B_RED, B_RED2, B_HALO = (226, 46, 52), (244, 96, 96), (86, 18, 22)
SKULL = (250, 246, 240)
WALL, FLOOR_COL = (34, 28, 36), (40, 32, 30)
DUST = (150, 140, 128)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


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


def draw_beam(dr, x, y, r, S, tilt=0.0, squint=0.0, shy=0.0, sq=0.0, nose=0.0):
    """Beam, d'après le dessin du fan, aux proportions de Bounce : un disque rouge au halo
    sombre, une tête de mort blanche (deux orbites rouges, un nez, une mâchoire)."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=B_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=B_RED)
    dr.ellipse([(x - 0.86 * r * sx) * S, (y - 0.86 * r * sy) * S, (x + 0.86 * r * sx) * S, (y + 0.86 * r * sy) * S], fill=B_RED2)
    ca, sa = math.cos(tilt), math.sin(tilt)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)

    def ell(u, v, ru, rv, n=28):
        return [P(u + ru * math.cos(2 * math.pi * i / n), v + rv * math.sin(2 * math.pi * i / n)) for i in range(n)]
    ox = -0.08 - 0.10 * shy          # la tête de mort regarde un peu à gauche, vers Bounce
    dr.polygon(ell(ox, -0.12, 0.60, 0.52), fill=SKULL)
    dr.polygon([P(ox - 0.34, 0.18), P(ox + 0.34, 0.18), P(ox + 0.28, 0.56), P(ox - 0.28, 0.56)], fill=SKULL)
    for gx in (-0.14, 0.0, 0.14):
        dr.line([P(ox + gx, 0.40), P(ox + gx, 0.56)], fill=B_RED2, width=max(2, int(0.04 * r * S)))
    for ex in (-0.25, 0.25):
        if squint > 0.5:
            dr.line([P(ox + ex - 0.17, -0.12), P(ox + ex, -0.06), P(ox + ex + 0.17, -0.12)], fill=B_RED, width=max(2, int(0.08 * r * S)), joint="curve")
        else:
            rr = 0.19 * (1 - 0.35 * squint)
            dr.polygon(ell(ox + ex - 0.05 * shy, -0.12, rr, rr * (1 - 0.3 * squint)), fill=B_RED)
    nr = 0.07 + 0.05 * nose
    dr.polygon([P(ox - nr, 0.08), P(ox + nr, 0.08), P(ox, 0.08 + 1.6 * nr)], fill=mix(B_RED, (255, 160, 160), nose))


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        d = {k: len(BANK[WHO + " " + k]) / SR for k in LINES}
        # ---- les éternuements : on les cale d'abord, Bounce se règle dessus
        L, fires = [], []

        def sneeze(t_start, build):
            t = t_start
            for k in build:
                L.append((t, k)); t += d[k] + 0.45
            L.append((t, "cri")); fires.append(t)
            return t + d["cri"]
        L.append((8.6, "bea"))                                    # fausse alerte
        self.fake = 8.6
        sneeze(18.4, ["beabea"])
        sneeze(31.0, ["bea"])
        end3 = sneeze(43.2, ["bea", "beabea"])
        self.fires = fires
        self.t_char = fires[2]
        L.append((self.t_char + 5.6, "petit"))                     # « beam. » : oups
        self.t_clean = self.t_char + 8.6
        L.append((self.t_clean + 2.2, "bea"))                      # et ça recommence
        self.lines = [(t, WHO + " " + k, f"b{i}") for i, (t, k) in enumerate(L)]
        self.payoff_at = self.t_char + 0.05
        self.end_s = max(61.4, self.t_clean + 3.2)
        # ---- Bounce : au sol à gauche, la poussière part vers Beam
        anchors = [(fires[0] - 0.5, 300), (fires[0] + 0.5, 360),  # 1 : il est en l'air, le rayon passe dessous
                   (fires[1], 320),                                 # 2 : il est au sol, le rayon monte et passe dessus
                   (self.t_char, 380)]                              # 3 : au sol, en plein dans le rayon
        C = []
        t, x = 0.6, 150.0
        xs = [150, 230, 320, 410, 300, 200, 360, 470, 260, 430]
        k = 0
        for (ta, xa) in anchors:
            n = max(1, round((ta - t) / 0.95))
            step = (ta - t) / n
            for i in range(n):
                C.append((t + i * step, float(xs[k % len(xs)]), FY)); k += 1
            t = ta
            C.append((t, float(xa), FY)); k += 1
        C.append((self.t_char, 380.0, FY))
        # carbonisé : de petits rebonds, puis il se secoue et repart
        t = self.t_char
        while t < self.end_s + 1.0:
            t += 0.95 if t < self.t_clean else 0.9
            C.append((t, 380.0 + (25 if len(C) % 2 else -25), FY))
        self.C = sorted(set(C))
        self.hits = [(c[0], "sol") for c in self.C if c[0] > 0.3]
        self.hi = 0
        self.puffs = [c for c in self.C if c[0] < self.t_char]

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 120.0, 900.0, C[0][0], C[0][1], C[0][2])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2])
        t0, x0, y0 = C[-1]
        return x0, y0

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "beam"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def line_at(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"] + 0.15:
                return n["text"].split(" ", 1)[1], (t - n["start"]) / max(0.01, n["end"] - n["start"])
        return None, 0.0

    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        rect(0, CEIL, W, FLOOR, WALL)
        rect(0, CEIL - 8, W, CEIL, dim(WALL, 0.6))
        rect(0, FLOOR, W, H, FLOOR_COL)
        # une ampoule nue au plafond, de vieux cartons : un grenier poussiéreux
        dr.line([(540 * S, CEIL * S), (540 * S, 560 * S)], fill=(70, 64, 60), width=int(4 * S))
        dr.ellipse([522 * S, 556 * S, 558 * S, 596 * S], fill=(250, 226, 150))
        for (x0, w, h) in ((960, 110, 120), (985, 80, 90)):
            rect(x0 - w / 2, FLOOR - h - (120 if x0 == 985 else 0), x0 + w / 2, FLOOR - (120 if x0 == 985 else 0), (120, 92, 64))
        # les trous laissés par les rayons
        holes = []
        if t >= self.fires[0]:
            holes.append((14, BY))
        if t >= self.fires[1]:
            holes.append((BX - R * 0.7 - (BY + 0.05 * R - CEIL) / math.tan(1.0), CEIL + 10))
        for (hx, hy) in holes:
            pts = [((hx + 46 * (1 + 0.25 * math.sin(i * 2.7)) * math.cos(i * math.pi / 8)) * S,
                    (hy + 46 * (1 + 0.25 * math.sin(i * 2.7)) * math.sin(i * math.pi / 8)) * S) for i in range(16)]
            dr.polygon(pts, fill=(6, 6, 10))
        # la poussière soulevée par chaque rebond, qui dérive vers Beam
        for (tc, cx, cy) in self.puffs:
            dd = t - tc
            if 0 <= dd < 2.6:
                for j in range(6):
                    px = cx + (j - 2.5) * 22 + dd * (BX - cx) * 0.32
                    py = FLOOR - 20 - dd * 70 - (j % 3) * 18
                    rr = 14 + 10 * dd + (j % 2) * 6
                    col = mix(WALL, DUST, 0.75 * (1 - dd / 2.6))
                    dr.ellipse([(px - rr) * S, (py - rr) * S, (px + rr) * S, (py + rr) * S], fill=col)
        # l'état de Beam : le nez qui chatouille, la tête qui part en arrière, le rayon
        txt, prog = self.line_at(t)
        tilt, squint, nose, shy = 0.0, 0.0, 0.0, 0.0
        since = min([t - f for f in self.fires if t >= f] + [99])
        n_dust = sum(1 for (tc, _, _) in self.puffs if tc <= t and all(not (tc < f <= t) for f in self.fires))
        nose = min(1.0, n_dust / 12.0)
        if txt in ("bea", "beabea"):
            tilt, squint = -0.30 * ease(prog * 1.5), 0.6
            if txt == "beabea":
                tilt -= 0.06 * math.sin(prog * 12)
        if txt == "cri" or since < 0.6:
            tilt, squint = 0.12, 1.0
        if txt == "petit" or (self.t_char + 5.6 <= t <= self.t_char + 7.5):
            shy = 1.0
        sq = 0.10 * math.exp(-since * 6) if since < 0.6 else 0.0
        draw_beam(dr, BX, BY, R, S, tilt=tilt, squint=squint, shy=shy, sq=sq, nose=nose)
        # le rayon
        for i, f in enumerate(self.fires):
            dd = t - f
            if 0 <= dd < (0.55 if i != 1 else 0.3):
                a = 0.0 if i != 1 else 1.0                  # le deuxième part vers le haut, dans le plafond
                x0, y0 = BX - R * 0.7, BY + 0.05 * R
                x1 = 14.0 if i == 0 else (x0 - (y0 - CEIL) / math.tan(a) if i == 1 else 380.0 + RB * 0.6)
                y1 = y0 - math.tan(a) * (x0 - x1)
                k = 1 - dd / (0.55 if i != 1 else 0.3)
                for wdt, col in ((70, (255, 60, 70)), (40, (255, 150, 160)), (16, (255, 240, 240))):
                    dr.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=mix(WALL, col, k), width=int(wdt * S * (0.6 + 0.4 * k)))
        # Bounce : carbonisé après le troisième, puis il se secoue
        bx, by = self.bounce_at(t)
        if self.t_char <= t < self.t_clean:
            base.HERO["color"] = (26, 22, 26)
            base.ball(dr, bx * S, by * S, RB * S)
            base.HERO["color"] = tuple(self.cfg["hero_color"])
            for ex in (-0.3, 0.3):
                dr.ellipse([(bx + ex * RB - 15) * S, (by - 0.25 * RB - 19) * S, (bx + ex * RB + 15) * S, (by - 0.25 * RB + 19) * S], fill=(245, 245, 245))
            for j in range(3):
                ph = ((t - self.t_char) * 0.7 + j / 3) % 1.0
                sx_, sy_ = bx - 30 + 30 * j, by - RB - 20 - 140 * ph
                rr = 10 + 22 * ph
                dr.ellipse([(sx_ - rr) * S, (sy_ - rr) * S, (sx_ + rr) * S, (sy_ + rr) * S], fill=mix(WALL, (90, 90, 96), 1 - ph))
        else:
            base.ball(dr, bx * S, by * S, RB * S)
            dd = t - self.t_clean
            if 0 <= dd < 0.8:                                # la suie s'envole
                for j in range(10):
                    ang = j * 0.63
                    rr = RB * (0.9 + 1.4 * dd)
                    px, py = bx + rr * math.cos(ang), by + rr * math.sin(ang)
                    dr.ellipse([(px - 12) * S, (py - 12) * S, (px + 12) * S, (py + 12) * S], fill=mix(WALL, (30, 26, 30), 1 - dd / 0.8))


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4,
            "hero_lose": "Bounce..."}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
