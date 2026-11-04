"""
Prototype « Blub » : le personnage d’un fan (Blub, une balle de la mer qui coule un peu plus à chaque fois
qu’il dit son nom) et le défi qu’il a posé : Bounce peut-il le sauver avant le fond ? Chaque « Bounce »
le fait sursauter et dire « Blub » : il coule. Bounce plonge, aggrave tout, touche le fond, passe dessous
et le remonte rebond après rebond, pendant que Blub se retient de parler. Blub atterrit sur la plage, à
côté de Snooze qui dort. Bounce, lui, reste au fond.

Blub ne dit que son nom (banque hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/blub.py configs/<name>.json [--simulate]
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



# ------------------------------------------------------------------ Blub
WHO = "Blub"
LINES = {"peur": "peur.wav", "triste": "triste.wav", "joie": "joie.wav"}
GAIN = {}

W, H = 1080, 1920
R = 100.0
RB = 100.0
CEIL = 330.0
G = 2600.0
GW = 1150.0                       # sous l'eau, tout retombe plus lentement
SURF = 800.0                      # la surface de l'eau
SEA = 1800.0                      # le fond, dur (des rochers)
PIER = (300.0, 560.0, 770.0)      # le ponton : x0, x1, dessus (dur)
BLX = 720.0                       # Blub
SNZ = (140.0, 700.0)              # Snooze qui dort sur la plage
LEVELS = [SURF + 10, 960.0, 1110.0, 1260.0, 1400.0, 1500.0]
B_DISC, B_HALO, B_INK, B_TONGUE = (34, 52, 214), (14, 20, 84), (8, 8, 18), (214, 96, 150)
WATER_T, WATER_B = (22, 50, 96), (8, 18, 44)
SKY = (12, 14, 30)
SAND = (120, 104, 78)

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




def draw_blub(dr, x, y, r, S, mood="joie", talk=0.0, sq=0.0):
    """Blub, d'après le dessin du fan, aux proportions de Bounce : un disque bleu roi, deux
    grands yeux noirs en amande, la langue rose tirée. Quand il se retient de parler : yeux
    plissés, joues gonflées."""
    puff = 0.08 if mood == "retient" else 0.0
    sx, sy = 1 + sq + puff, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=B_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=B_DISC)

    def P(u, v):
        return ((x + u * r * sx) * S, (y + v * r * sy) * S)

    def ell(u, v, ru, rv, a=0.0, n=24):
        ca, sa = math.cos(a), math.sin(a)
        return [P(u + ru * math.cos(2 * math.pi * k / n) * ca - rv * math.sin(2 * math.pi * k / n) * sa,
                  v + ru * math.cos(2 * math.pi * k / n) * sa + rv * math.sin(2 * math.pi * k / n) * ca) for k in range(n)]
    w = max(2, int(0.08 * r * S))
    for side in (-1, 1):
        ex = 0.32 * side
        if mood == "retient":
            dr.line([P(ex - 0.16, -0.20), P(ex, -0.12), P(ex + 0.16, -0.20)], fill=B_INK, width=w, joint="curve")
        else:
            big = 1.25 if mood == "peur" else 1.0
            dr.polygon(ell(ex, -0.18, 0.15 * big, 0.21 * big, a=0.35 * side), fill=B_INK)
            if mood == "peur":
                dr.polygon(ell(ex + 0.04, -0.24, 0.05, 0.05), fill=(240, 240, 250))
    if mood == "retient":
        dr.line([P(-0.16, 0.36), P(0.16, 0.36)], fill=B_INK, width=w)
    elif mood == "peur":
        dr.polygon(ell(0.0, 0.38, 0.09, 0.12 + 0.05 * talk), fill=B_INK)
    else:
        o = 0.10 * talk
        dr.polygon(ell(0.02, 0.42 + o, 0.13, 0.14 + o), fill=B_TONGUE)
        dr.line([P(-0.18, 0.30), P(0.0, 0.34), P(0.20, 0.30)], fill=B_INK, width=w, joint="curve")


def draw_snooze_asleep(dr, x, y, r, S, t):
    dr.ellipse([(x - 1.6 * r) * S, (y - 1.6 * r) * S, (x + 1.6 * r) * S, (y + 1.6 * r) * S], fill=(42, 42, 44))
    dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=(192, 192, 192))
    w = max(2, int(0.05 * r * S))
    for ex in (-0.37, 0.37):
        cx, cy, er = x + ex * r, y - 0.2 * r, 0.29 * r
        dr.ellipse([(cx - er) * S, (cy - er) * S, (cx + er) * S, (cy + er) * S], fill=(104, 104, 104), outline=(52, 52, 52), width=w)
        dr.line([((cx - er * 0.8) * S, cy * S), ((cx + er * 0.8) * S, cy * S)], fill=(40, 40, 40), width=w)
    dr.rounded_rectangle([(x - 0.4 * r) * S, (y + 0.33 * r) * S, (x + 0.4 * r) * S, (y + 0.47 * r) * S], radius=0.07 * r * S, fill=(112, 112, 112), outline=(52, 52, 52), width=w)
    for i in range(3):
        ph = (t * 0.6 + i / 3) % 1.0
        col = mix(SKY, (170, 170, 200), min(1.0, ph * 3, (1 - ph) * 3))
        dr.text(((x + 70 + 60 * ph) * S, (y - r - 20 - 130 * ph) * S), "z" if i % 2 else "Z", fill=col, anchor="mm", font=font(int((30 + 26 * ph) * S)))


class Sim:
    scene_top = 0.17

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        d = {k: len(BANK[WHO + " " + k]) / SR for k in LINES}
        C = []                                     # (t, x, y, dur, gravite de l'arc qui y arrive)

        def c(t, x, y, hard=True, g=G):
            C.append((t, float(x), float(y), hard, g))
        L = []
        self.sinks = []                            # (t, niveau) : Blub s'enfonce
        py = PIER[2] - RB
        # sur le ponton : quelques rebonds, puis chaque « Bounce » fait sursauter Blub, qui coule d'un cran
        for i, x in enumerate((340, 420, 360)):
            c(0.6 + 0.9 * i, x, py)
        t = 2.4
        lvl = 0
        for k in range(3):
            t += 1.55
            c(t, 380 + 80 * (k % 2), py)
            tl = t + 0.82
            L.append((tl, "peur")); lvl += 1; self.sinks.append((tl + 0.15, lvl))
        # Bounce veut aider : deux rebonds encore, puis il plonge
        t += 1.55; c(t, 460, py)
        t += 1.0; c(t, 520, py)
        self.t_dive = t + 0.75                     # il traverse la surface
        # sous l'eau : il lui tombe sur la tête, Blub sursaute, coule encore
        t_head = t + 2.0
        for k in range(2):
            yb = LEVELS[lvl]
            c(t_head, BLX, yb - R - RB, g=GW)
            tl = t_head + 0.82
            L.append((tl, "peur")); lvl += 1; self.sinks.append((tl + 0.15, lvl))
            t_head += 2.0
        # il glisse à côté de lui jusqu'au fond, puis passe dessous et le remonte, un niveau à chaque fois,
        # pendant que Blub se retient de parler
        sea_y = SEA - RB
        c(t_head - 0.2, BLX - 240, sea_y, g=GW)
        self.pushes = []
        tt = t_head - 0.2
        cur = lvl
        for nl in (4, 3, 2, 1, 0):
            tt += 1.7
            c(tt, BLX, sea_y, g=GW)                 # le fond, sous Blub
            tt += 1.25
            c(tt, BLX, LEVELS[cur] + R + RB, g=GW)  # sous Blub : il le pousse d'un cran
            self.pushes.append((tt, nl)); cur = nl
            tt += 1.25
            c(tt, BLX - 200 + 60 * (nl % 2), sea_y, g=GW)
        # le dernier : il le soulève hors de l'eau, Blub s'envole jusqu'à la plage
        tt += 1.7; c(tt, BLX, sea_y, g=GW)
        tt += 1.3; c(tt, BLX, SURF + R + RB - 20, g=GW)
        self.t_launch = tt
        self.t_beach = tt + 1.4
        L.append((self.t_beach + 0.5, "joie"))     # sur le sable, « Blub » ne le fait plus couler
        # Bounce, lui, est resté au fond : il essaie de remonter, de plus en plus haut, sans y arriver
        for dd in (1.3, 1.6, 1.9, 2.2, 2.4, 2.4, 1.8, 1.5, 1.4, 1.4, 1.3, 1.3):
            if tt + dd > 61.6:
                break
            tt += dd
            c(tt, BLX - 60 + (40 if len(C) % 2 else 0), sea_y, g=GW)
        L.append((self.t_beach + 12.0, "joie"))    # Blub l'encourage depuis la plage
        self.C = sorted(C)
        self.hits = [(e[0], "dur") for e in self.C if e[3] and e[0] > 0.3]
        self.hi = 0
        self.lines = [(tl, WHO + " " + k, f"bl{i}") for i, (tl, k) in enumerate(L)]
        self.payoff_at = self.t_beach + 2.2
        self.end_s = 61.8

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 330.0, 420.0, C[0][0], C[0][1], C[0][2])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                under = b[4] == GW
                cap = SURF + RB * 0.2 if under and a[2] > SURF else CEIL + RB
                return arc(t, a[0], a[1], a[2], b[0], b[1], b[2], cap=cap, g=b[4])
        return C[-1][1], C[-1][2]

    def blub_at(self, t):
        if t >= self.t_launch:
            s = min(1.0, (t - self.t_launch) / (self.t_beach - self.t_launch))
            x = lerp(BLX, 300, s)
            y = lerp(SURF - 20, 690, s) - 360 * math.sin(math.pi * s)
            return x, y
        lvl = 0
        y = LEVELS[0]
        for (ts, l) in self.sinks:
            if t >= ts:
                y = lerp(LEVELS[lvl], LEVELS[l], ease((t - ts) / 0.6)); lvl = l
        for (tp, nl) in self.pushes:
            if t >= tp:
                y = lerp(LEVELS[lvl], LEVELS[nl], ease((t - tp) / 0.45)); lvl = nl
        return BLX, y + 6 * math.sin(t * 2.5)

    def blub_mood(self, t):
        for n in self.narr:
            if n["start"] - 0.1 <= t <= n["end"] + 0.4:
                return "peur" if n["text"].endswith("peur") else "joie"
        if self.pushes and self.pushes[0][0] - 3.0 <= t < self.t_launch + 0.3:
            return "retient"                       # surtout ne pas dire son nom
        if t < 3.0 or t >= self.t_launch + 0.3:
            return "joie"
        return "peur"

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                return 0.0 if e is None else float(e[min(int((t - n["start"]) * 60), len(e) - 1)])
        return 0.0

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "au fond"))
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
        rect(0, CEIL, W, SURF, SKY)
        dr.ellipse([860 * S, 400 * S, 950 * S, 490 * S], fill=(236, 232, 200))
        # l'eau, du clair vers le sombre
        for i in range(10):
            y0 = lerp(SURF, SEA, i / 10); y1 = lerp(SURF, SEA, (i + 1) / 10)
            rect(0, y0, W, y1 + 1, mix(WATER_T, WATER_B, i / 9))
        rect(0, SEA, W, H, (40, 34, 30))
        for (rx, rw) in ((120, 160), (430, 120), (980, 180)):
            dr.ellipse([(rx - rw) * S, (SEA - 40) * S, (rx + rw) * S, (SEA + 50) * S], fill=(56, 50, 46))
        for k, sx in enumerate((90, 230, 940, 1010)):
            sway = 14 * math.sin(t * 1.4 + k)
            dr.line([(sx * S, SEA * S), ((sx + sway) * S, (SEA - 140) * S), ((sx - sway) * S, (SEA - 260) * S)], fill=(30, 90, 60), width=int(10 * S), joint="curve")
        # la plage et Snooze
        dr.polygon([(0, (SURF - 120) * S), (250 * S, (SURF - 110) * S), (420 * S, (SURF + 60) * S), (420 * S, (SURF + 200) * S), (0, (SURF + 200) * S)], fill=SAND)
        draw_snooze_asleep(dr, SNZ[0], SNZ[1] - 8, 80, S, t)
        # le ponton
        p0, p1, pt = PIER
        for px in (p0 + 30, p1 - 30):
            rect(px - 10, pt, px + 10, SURF + 200, (70, 50, 36))
        rect(p0, pt, p1, pt + 26, (112, 82, 56))
        # Blub
        bx_, by_ = self.blub_at(t)
        draw_blub(dr, bx_, by_, R, S, mood=self.blub_mood(t), talk=self.talking(t))
        # Bounce, et ses bulles sous l'eau
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, by * S, RB * S)
        if by > SURF + RB * 0.5:
            for j in range(4):
                ph = (t * 0.9 + j / 4) % 1.0
                qx, qy = bx + 50 * math.sin(j * 2.1 + t), by - RB - 200 * ph
                if qy > SURF:
                    rr = 8 + 8 * ph
                    dr.ellipse([(qx - rr) * S, (qy - rr) * S, (qx + rr) * S, (qy + rr) * S], outline=(170, 200, 240), width=int(3 * S))
        # la surface, par-dessus : une ligne qui ondule ; l'éclaboussure du plongeon
        pts = [(x * S, (SURF + 6 * math.sin(x / 70 + t * 2)) * S) for x in range(int(p1), W + 20, 20)]
        dr.line(pts, fill=(120, 170, 220), width=int(5 * S))
        dd = t - self.t_dive
        if 0 <= dd < 0.9:
            for j in range(14):
                a = -math.pi / 2 + (j - 6.5) * 0.18
                rr = 40 + 380 * dd
                qx, qy = 560 + 40 + rr * math.cos(a) * 0.7, SURF + rr * math.sin(a) + 500 * dd * dd
                if qy < SURF:
                    dr.ellipse([(qx - 12) * S, (qy - 12) * S, (qx + 12) * S, (qy + 12) * S], fill=(140, 190, 235))


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
