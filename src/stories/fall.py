"""
Prototype « Fall » : le personnage d’un fan (Fall, une balle bleue qui adore tomber, et l’automne) et
Bounce. Fall saute de sa branche dans un gros tas de feuilles, ravi. Bounce veut essayer, mais il ne sait
pas tomber : chaque plongeon traverse le tas jusqu’au sol dur, le renvoie en l’air et éparpille les
feuilles. Le tas fond. Fall saute quand même… et atterrit sur Bounce : il rebondit pour la première fois.
Bounce est devenu son trampoline.

Fall ne dit que son nom (banque de voix hors dépôt, cfg["voice_bank"]), sans sous-titre.

    python3 src/stories/fall.py configs/<name>.json [--simulate]
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


# ------------------------------------------------------------------ Fall
WHO = "Fall"
LINES = {"long": "long.wav", "joie": "joie.wav", "q": "q.wav"}
GAIN = {}

W, H = 1080, 1920
R = 100.0
RB = 100.0
CEIL = 300.0
GROUND = 1500.0
FY = GROUND - RB
G = 2600.0
TRUNK = (840.0, 905.0)                 # le tronc : x0, x1
BRANCH = (600.0, 880.0, 820.0)         # la branche : x0, x1, dessus
PERCH = (700.0, BRANCH[2] - R)         # Fall sur sa branche
PILE_X = 640.0
F_DISC, F_RING, F_HALO, F_INK = (136, 218, 250), (176, 232, 252), (42, 82, 104), (64, 142, 176)
SKY, HILL = (16, 18, 36), (26, 30, 34)
LEAF = [(214, 112, 40), (232, 160, 52), (190, 70, 36), (240, 196, 80)]


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
    h = min(0.5 * G * (d / 2) ** 2, 760.0)
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


def draw_fall(dr, x, y, r, S, mood="joie", talk=0.0, sq=0.0, rot=0.0):
    """Fall, d'après le dessin du fan, aux proportions de Bounce : un disque bleu ciel, un anneau
    plus pâle, deux yeux en amande dressés, une bouche ouverte, la langue tirée."""
    sx, sy = 1 + sq, 1 - sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=F_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=F_RING)
    dr.ellipse([(x - 0.84 * r * sx) * S, (y - 0.84 * r * sy) * S, (x + 0.84 * r * sx) * S, (y + 0.84 * r * sy) * S], fill=F_DISC)
    ca, sa = math.cos(rot), math.sin(rot)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (y + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.07 * r * S))
    for side in (-1, 1):
        ex = 0.28 * side
        if mood == "surpris":
            pts = [P(ex + 0.12 * math.cos(k * math.pi / 10), -0.2 + 0.16 * math.sin(k * math.pi / 10)) for k in range(20)]
            dr.line(pts + [pts[0]], fill=F_INK, width=w)
        else:
            # l'amande dressée du dessin, avec le petit trait sous l'œil
            pts = [P(ex - 0.07, -0.02), P(ex - 0.05, -0.28), P(ex, -0.40), P(ex + 0.06, -0.28), P(ex + 0.07, -0.02)]
            dr.line(pts + [pts[0]], fill=F_INK, width=w, joint="curve")
            dr.line([P(ex - 0.03 * side, 0.08), P(ex - 0.08 * side, 0.18)], fill=F_INK, width=w)
    if mood == "inquiet":
        dr.line([P(-0.22, 0.38), P(0.0, 0.30), P(0.22, 0.38)], fill=F_INK, width=w, joint="curve")
    else:
        o = 0.12 + 0.18 * talk + (0.12 if mood == "surpris" else 0.0)
        dr.line([P(-0.26, 0.20), P(0.26, 0.20)], fill=F_INK, width=w)
        tongue = [P(-0.13, 0.20)] + [P(0.13 * math.cos(math.pi * k / 10), 0.20 + o + 0.16 * math.sin(math.pi * k / 10)) for k in range(11)] + [P(0.13, 0.20)]
        dr.line(tongue, fill=F_INK, width=w, joint="curve")


class Sim:
    scene_top = 0.20

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.rng = np.random.default_rng(7)
        d = {k: len(BANK[WHO + " " + k]) / SR for k in LINES}
        # ---- Fall : sauts dans le tas, remontée par le tronc
        jumps = [2.9, 11.4, 21.6, 31.8]                 # chaque saut
        self.jumps = jumps
        L = [(j, "long") for j in jumps]
        self.f_land = [j + 1.0 for j in jumps]           # il atterrit dans le tas
        L += [(l + 0.35, "joie") for l in self.f_land[:2]]
        L += [(self.f_land[2] + 0.4, "q")]                 # le tas a fondu : « Fall? »
        # ---- Bounce : il veut essayer ; chaque fois qu'il tombe dans le tas, il le traverse
        # jusqu'au sol dur et repart très haut en éparpillant les feuilles
        C = []
        hops = [(0.6, 140), (1.6, 190), (2.6, 150), (3.6, 210), (4.6, 170), (5.6, 230), (6.6, 190),
                (7.6, 260), (8.6, 220)]
        dives = [(9.7, PILE_X), (17.0, PILE_X - 20), (27.3, PILE_X + 10), (37.6, PILE_X)]
        self.dives = [t for t, _ in dives]
        C += hops
        t = 8.6
        for (td, xd) in dives:
            # quelques rebonds d'élan à gauche, puis le plongeon
            while t + 0.95 < td - 0.2:
                t += 0.95
                C.append((t, 160 + 60 * ((len(C) * 7) % 3)))
            C.append((td, xd))
            t = td + 1.6
            C.append((t, 230))                           # il retombe à gauche, loin
        # la fin : plus de tas ; Bounce rebondit à sa place, Fall saute quand même et lui tombe dessus
        t_last_jump = 44.4
        self.jumps.append(t_last_jump)
        L.append((t_last_jump, "long"))
        while t + 0.95 < t_last_jump + 0.5:
            t += 0.95
            C.append((t, 300 + 120 * ((len(C) * 5) % 4)))
        # Bounce se place sous la branche : il est au sol quand Fall arrive
        self.t_stack = t_last_jump + 1.25
        C.append((self.t_stack, PILE_X))
        # ensuite, empilés : Bounce au sol, Fall rebondit sur lui ; une seule cadence
        self.stack = []
        tt = self.t_stack
        while tt < 61.8:
            tt += 1.0
            C.append((tt, PILE_X))
            self.stack.append(tt)
        L.append((self.t_stack + 0.55, "q"))              # « Fall?! » : il rebondit
        L.append((self.t_stack + 3.6, "joie"))
        L.append((self.t_stack + 8.0, "joie"))
        self.lines = [(tl, WHO + " " + k, f"f{i}") for i, (tl, k) in enumerate(sorted(L))]
        self.C = sorted((tc, float(xc), FY) for tc, xc in C)
        self.hits = [(c[0], "sol") for c in self.C if c[0] > 0.3]
        self.hi = 0
        self.payoff_at = self.t_stack + 1.9
        self.end_s = 61.7
        self.d = d

    # ---- Bounce
    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return arc(t, -0.5, 60.0, 900.0, C[0][0], C[0][1], C[0][2])
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                return arc(t, *a, *b)
        return C[-1][1], C[-1][2]

    # ---- Fall
    def pile(self, t):
        """La hauteur du tas (0 à 1) : chaque plongeon de Bounce en enlève un quart."""
        n = sum(1 for td in self.dives if t >= td)
        return max(0.0, 1.0 - 0.25 * n)

    def fall_at(self, t):
        """(x, y, mood, rot) de Fall."""
        top = GROUND - 150 * self.pile(t)
        for i, tj in enumerate(self.jumps[:4]):
            tl = self.f_land[i]
            if tj <= t < tl:                             # le saut, depuis la branche
                s = (t - tj) / (tl - tj)
                return lerp(PERCH[0], PILE_X + 20, s), PERCH[1] - 120 * math.sin(math.pi * s) + (top - 40 - PERCH[1]) * s * s, "joie", -2 * s
            if tl <= t < tl + 1.3:                       # dans le tas, ravi
                sink = 0.6 * self.pile(t)
                return PILE_X + 20, top - R * (1 - sink), "joie" if i < 2 else "inquiet", 0.0
            nxt = self.jumps[i + 1] if i + 1 < len(self.jumps) else 99
            if tl + 1.3 <= t < min(tl + 4.3, nxt):       # il remonte : il roule jusqu'au tronc, puis le long du tronc
                s = (t - tl - 1.3) / 3.0
                if s < 0.4:
                    u = s / 0.4
                    return lerp(PILE_X + 20, TRUNK[0] - R, u), lerp(top - R * 0.4, GROUND - R, u), "joie", 3 * u
                if s < 0.85:
                    u = (s - 0.4) / 0.45
                    return TRUNK[0] - R, lerp(GROUND - R, PERCH[1] - 10, u), "joie", 3 + 4 * u
                u = (s - 0.85) / 0.15
                return lerp(TRUNK[0] - R, PERCH[0], u), PERCH[1], "joie", 7 + u
        tj = self.jumps[4]
        if tj <= t < self.t_stack:                       # le dernier saut : sur Bounce
            s = (t - tj) / (self.t_stack - tj)
            return lerp(PERCH[0], PILE_X, s), PERCH[1] - 120 * math.sin(math.pi * s) + (FY - 2 * R - PERCH[1]) * s * s, "joie", -2 * s
        if t >= self.t_stack:                            # empilés : il rebondit sur Bounce
            ts = [self.t_stack] + self.stack
            for a, b in zip(ts, ts[1:]):
                if a <= t <= b:
                    s = (t - a) / (b - a)
                    mood = "surpris" if t < self.t_stack + 3.2 else "joie"
                    _, by = self.bounce_at(t)
                    return PILE_X, by - 2 * R - 300 * 4 * s * (1 - s), mood, 0.0
            return PILE_X, FY - 2 * R, "joie", 0.0
        return PERCH[0], PERCH[1], ("inquiet" if t > self.dives[1] else "joie"), 0.0

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "trampoline"))
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
                if e is None:
                    return 0.0
                return float(e[min(int((t - n["start"]) * 60), len(e) - 1)])
        return 0.0

    def draw(self, dr, snap, t, S):
        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        rect(0, CEIL, W, GROUND, SKY)
        dr.ellipse([140 * S, 420 * S, 230 * S, 510 * S], fill=(236, 232, 200))
        dr.ellipse([-200 * S, 1300 * S, 700 * S, 1700 * S], fill=HILL)
        rect(0, GROUND, W, H, (30, 24, 22))
        # l'arbre
        rect(TRUNK[0], 560, TRUNK[1], GROUND, (78, 56, 44))
        dr.polygon([(BRANCH[0] * S, BRANCH[2] * S), (BRANCH[1] * S, (BRANCH[2] - 30) * S), (BRANCH[1] * S, (BRANCH[2] + 10) * S), (BRANCH[0] * S, (BRANCH[2] + 22) * S)], fill=(78, 56, 44))
        rng = np.random.default_rng(3)
        for i in range(70):
            a, rr = rng.uniform(0, 2 * math.pi), rng.uniform(0, 230)
            lx, ly = 880 + rr * math.cos(a) * 1.1, 520 + rr * math.sin(a) * 0.55
            col = LEAF[i % 4]
            dr.ellipse([(lx - 26) * S, (ly - 18) * S, (lx + 26) * S, (ly + 18) * S], fill=col)
        # le tas de feuilles, qui fond à chaque plongeon de Bounce ; les feuilles éparpillées au sol
        p = self.pile(t)
        if p > 0:
            hgt = 150 * p
            dr.ellipse([(PILE_X - 230 * (0.6 + 0.4 * p)) * S, (GROUND - hgt) * S, (PILE_X + 230 * (0.6 + 0.4 * p)) * S, (GROUND + hgt) * S], fill=(196, 100, 40))
            for i in range(int(30 * p)):
                lx = PILE_X + rng.uniform(-200, 200) * (0.6 + 0.4 * p)
                ly = GROUND - rng.uniform(0, hgt * 0.9)
                dr.ellipse([(lx - 18) * S, (ly - 12) * S, (lx + 18) * S, (ly + 12) * S], fill=LEAF[i % 4])
        n_out = sum(1 for td in self.dives if t >= td)
        rng2 = np.random.default_rng(11)
        for i in range(26 * n_out):
            lx, ly = rng2.uniform(30, 1050), GROUND - rng2.uniform(0, 14)
            dr.ellipse([(lx - 16) * S, (ly - 9) * S, (lx + 16) * S, (ly + 9) * S], fill=LEAF[i % 4])
        # les feuilles qui volent : à chaque plongeon, à chaque arrivée de Fall
        for te in self.dives + self.f_land:
            dd = t - te
            if 0 <= dd < 1.6:
                rng3 = np.random.default_rng(int(te * 100))
                for i in range(24):
                    vx, vy = rng3.uniform(-520, 520), rng3.uniform(-1100, -500)
                    lx = PILE_X + vx * dd
                    ly = GROUND - 60 + vy * dd + 0.5 * 1300 * dd * dd
                    if ly < GROUND:
                        dr.ellipse([(lx - 16) * S, (ly - 10) * S, (lx + 16) * S, (ly + 10) * S], fill=LEAF[i % 4])
        # Fall, puis Bounce par-dessus (ou dessous quand ils sont empilés)
        fx, fy, mood, rot = self.fall_at(t)
        sq = 0.0
        for tl in self.f_land:
            if 0 <= t - tl < 0.4:
                sq = 0.12 * math.exp(-(t - tl) * 8)
        draw_fall(dr, fx, fy, R, S, mood=mood, talk=self.talking(t), sq=sq, rot=rot)
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, by * S, RB * S)
        if t >= self.t_stack:
            draw_fall(dr, fx, fy, R, S, mood=mood, talk=self.talking(t), sq=sq, rot=rot)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
