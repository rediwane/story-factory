"""
Prototype « Slo » : le personnage d'un fan (Slo, une balle violette inspirée du paresseux : yeux
fermés, spirales de sommeil ; quand on l'approche, il vous ignore et vous ralentit) et Bounce.

Slo dort au milieu du chemin. Le bruit le réveille à moitié : chaque « Bounce » fait naître
autour de lui une bulle où le temps passe plus lentement (une seule règle : dans la bulle, le
temps propre avance à k·dt ; les arcs gardent leur forme, ils sont plus lents, la poussière
aussi). Plus le silence dure, plus Slo se rendort et plus la bulle ralentit ; quand il dort
tout à fait, la bulle éclate d'un coup. Bounce, qui n'a jamais perdu sa vitesse propre, est
alors relâché à pleine vitesse… et son propre « Bounce » réveille Slo.

Slo ne dit que son nom (banque de voix hors dépôt, cfg["slo_bank"]), sans sous-titre.
Bounce ne s'arrête jamais. Rien n'est ajouté au moteur.

    python3 src/stories/slo.py configs/<name>.json [--simulate]
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

# ------------------------------------------------------------------ la voix de Slo
WHO = "Slo"
LINES = {"long": "long.wav", "court": "court.wav", "tres_long": "tres_long.wav", "moyen": "moyen.wav"}
GAIN = {"court": 0.9, "tres_long": 1.0}
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
    path = cfg.get("slo_bank")
    if not path:
        raise SystemExit("[slo] slo_bank manquant dans la config")
    for key, fn in LINES.items():
        x = _read(os.path.join(path, fn))
        x /= (np.sqrt(np.mean(x[np.abs(x) > 0.05 * np.abs(x).max()] ** 2)) + 1e-9)
        x *= 0.2 * GAIN.get(key, 1.0)
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def slo_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = slo_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Slo suit sa voix
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

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
R = 74.0                     # Slo et Bounce : même taille
RB = 74.0
CEIL = 560.0
FLOOR = 1500.0
FY = FLOOR - RB
WALL_L, WALL_R = 34.0, 1046.0       # faces intérieures des murs
XL, XR = WALL_L + RB, WALL_R - RB    # centre de Bounce au contact d'un mur
DOOR_TOP = 1262.0                    # la porte, en bas du mur de droite : la sortie
SX, SY = 590.0, FLOOR - R           # Slo, posé au sol au milieu du chemin
RZ = 340.0                           # la bulle de Slo
EDGE = 90.0                          # le bord de la bulle, où le temps rattrape
G = 2600.0

K_LIGHT = 0.22               # à moitié réveillé : le temps passe à 22 %
K_DEEP = 0.008               # presque endormi
Q_POP = 5.0                  # endormi : la bulle éclate
BLOOM_DELAY, BLOOM_S = 0.25, 0.75

S_DISC = (128, 94, 186)
S_HALO = dim(S_DISC, 0.3)
S_EDGE = (120, 196, 214)
S_INK = (38, 22, 58)
WALL, FLOOR_COL = (22, 20, 32), (34, 28, 40)
ZONE = (150, 110, 230)
DUST = (150, 138, 160)
LIGHT = (255, 214, 140)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def draw_slo(dr, x, y, r, S, sq=0.0, talk=0.0, spin=0.0, nod=0.0):
    """Slo, d'après le dessin du fan, aux proportions de Bounce : un disque violet au halo sombre,
    deux yeux fermés en arcs, une petite bouche ondulée, deux spirales de sommeil sur le côté."""
    sx, sy = 1 + sq, 1 - sq
    y = y + r * sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=S_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=S_DISC,
               outline=S_EDGE, width=max(1, int(0.025 * r * S)))
    tilt = 0.10 * nod

    def P(u, v):
        uu = u * math.cos(tilt) - v * math.sin(tilt)
        vv = u * math.sin(tilt) + v * math.cos(tilt) + 0.08 * nod
        return ((x + uu * r * sx) * S, (y + vv * r * sy) * S)
    w = max(2, int(0.075 * r * S))
    # les yeux fermés : deux arcs vers le bas, le gauche plus grand, un peu de travers comme sur le dessin
    for (cu, cv, ru, rv) in ((-0.40, 0.08, 0.20, 0.13), (0.33, 0.23, 0.16, 0.10)):
        pts = [P(cu + ru * math.cos(a), cv + rv * math.sin(a)) for a in np.linspace(0.05 * math.pi, 0.95 * math.pi, 14)]
        dr.line(pts, fill=S_INK, width=w, joint="curve")
        dr.line([P(cu - ru * 0.98, cv - rv * 0.15), P(cu - ru * 1.02, cv - rv * 0.55)], fill=S_INK, width=w)
        dr.line([P(cu + ru * 0.98, cv - rv * 0.15), P(cu + ru * 1.02, cv - rv * 0.55)], fill=S_INK, width=w)
    # la bouche : un petit « ~ » ; quand il parle, elle s'ouvre en un petit rond
    if talk > 0.08:
        mw, mh = 0.13 + 0.03 * talk, 0.05 + 0.13 * talk
        dr.polygon([P(0.0 + mw * math.cos(a), 0.70 + mh * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 20)], fill=S_INK)
    else:
        pts = [P(-0.15 + 0.30 * i / 16, 0.72 - 0.06 * math.sin(2 * math.pi * i / 16 + 0.6)) for i in range(17)]
        dr.line(pts, fill=S_INK, width=max(2, int(0.06 * r * S)), joint="curve")
    # les spirales de sommeil, en haut à droite, qui tournent lentement
    for (cu, cv, rr, ph) in ((0.58, -0.50, 0.20, 0.0), (0.95, 0.02, 0.23, 1.7)):
        pts = []
        for i in range(40):
            a = spin + ph + i / 39 * 2.3 * math.pi
            rad = rr * (0.15 + 0.85 * i / 39)
            pts.append(P(cu + rad * math.cos(a), cv + rad * math.sin(a)))
        dr.line(pts, fill=S_INK, width=max(2, int(0.065 * r * S)), joint="curve")


class Sim:
    scene_top = 0.24

    # ---------------------------------------------------------------- la règle
    def drowsy(self, t):
        """Slo a de plus en plus sommeil : il se rendort de plus en plus vite après chaque « Bounce », et
        même à moitié réveillé sa bulle est plus lente. cfg["drowsy"] : [t, silence avant qu'il replonge,
        constante de temps, temps de la bulle à moitié réveillé], interpolés."""
        ks = self.cfg["drowsy"]
        if t <= ks[0][0]:
            return tuple(ks[0][1:])
        for a, b in zip(ks, ks[1:]):
            if a[0] <= t <= b[0]:
                s = ease((t - a[0]) / (b[0] - a[0]))
                return tuple(lerp(u, v, s) for u, v in zip(a[1:], b[1:]))
        return tuple(ks[-1][1:])

    def k_in(self, q, t=None):
        """Le temps dans la bulle, selon le silence q (s) depuis le dernier « Bounce »."""
        qd, tau, kl = self.drowsy(self.t_now if t is None else t)
        if q <= qd:
            return kl
        return max(K_DEEP, kl * math.exp(-(q - qd) / tau))

    def zone_scale(self, t):
        if self.bloom_t is None or t < self.bloom_t:
            return 0.0
        return ease((t - self.bloom_t) / BLOOM_S)

    def k_at(self, x, y, t):
        if not self.on:
            return 1.0
        sc = self.zone_scale(t)
        if sc <= 0:
            return 1.0
        d = math.hypot(x - SX, y - SY)
        rz = RZ * sc
        if d >= rz:
            return 1.0
        u = ease((rz - d) / EDGE)
        return 1.0 - (1.0 - self.k_in(t - self.last_word)) * u

    # ---------------------------------------------------------------- le plan de Bounce
    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.rng = rng
        self.t_now = 0.0
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        hv = base.hook_audio(cfg)
        self.hook_end = (0.15 + len(hv) / SR + 0.1) if hv is not None else 0.0
        nm = steady_hero_word(cfg["hero_name"], cfg)
        self.name_len = len(nm) / SR if nm is not None else 0.8
        self.dur = {k: len(BANK[WHO + " " + k]) / SR for k in LINES}
        self._integrate(cfg)
        self._place_lines(cfg)

    # ---------------------------------------------------------------- la trajectoire, en temps propre
    @staticmethod
    def contact_point(c):
        """Le centre de Bounce au contact décrit par c = [surface, valeur, hauteur de l'arc qui y mène]."""
        kind, v = c[0], float(c[1])
        if kind == "sol":
            return v, FY
        if kind == "tete":                       # v : angle depuis le sommet de Slo, en degrés (+ = à droite)
            a = math.radians(v)
            return SX + (R + RB) * math.sin(a), SY - (R + RB) * math.cos(a)
        if kind == "mur_g":
            return XL, v
        if kind == "mur_d":
            return XR, v
        if kind == "plafond":
            return v, CEIL + RB
        if kind == "air":                        # un point de départ hors champ
            return float(c[1]), float(c[2])
        raise ValueError(kind)

    def build_path(self, cfg):
        """Les arcs entre contacts : de vraies paraboles sous la gravité G, en temps propre. La bulle
        n'y change rien d'autre que la vitesse à laquelle on les parcourt."""
        pts = [("air",) + self.contact_point(cfg["start"])]
        arcs = []
        tau = 0.0
        x0, y0 = pts[0][1], pts[0][2]
        prev = "air"
        for c in cfg["plan"]:
            x1, y1 = self.contact_point(c)
            hh = float(c[2]) if c[0] != "air" else 0.0
            top = min(y0, y1) - hh
            t1 = math.sqrt(max(0.0, 2 * (y0 - top) / G))
            t2 = math.sqrt(max(0.0, 2 * (y1 - top) / G))
            if c[0] == "plafond":            # il heurte le plafond en montant : sommet virtuel au-dessus
                T, vy = t1 - t2, -G * t1
            elif prev == "plafond":          # il en repart vers le bas
                T, vy = t2 - t1, G * t1
            else:
                T, vy = t1 + t2, -G * t1
            T = max(1e-3, T)
            vx = (x1 - x0) / T
            arcs.append((tau, T, x0, y0, vx, vy, c[0]))
            tau += T
            x0, y0 = x1, y1
            prev = c[0]
        self.arcs = arcs
        self.tau_end = tau

    def pos(self, tau):
        """Position (x, y) et vitesse propre au temps propre tau. Au-delà du dernier contact, il
        continue sur un dernier rebond vertical (il ne s'arrête jamais)."""
        arcs = self.arcs
        lo, hi = 0, len(arcs) - 1
        while lo < hi:
            m = (lo + hi + 1) // 2
            if arcs[m][0] <= tau:
                lo = m
            else:
                hi = m - 1
        t0, T, x0, y0, vx, vy, _ = arcs[lo]
        s = min(tau - t0, T)
        if lo == len(arcs) - 1 and tau > t0 + T:
            # après le dernier contact : il rebondit sur place, sans fin
            xe, ye = x0 + vx * T, y0 + vy * T + 0.5 * G * T * T
            v0 = math.sqrt(2 * G * 150.0)
            tb = 2 * v0 / G
            u = (tau - t0 - T) % tb
            return xe, ye - (v0 * u - 0.5 * G * u * u), 0.0, -v0 + G * u
        return x0 + vx * s, y0 + vy * s + 0.5 * G * s * s, vx, vy + G * s

    def _integrate(self, cfg):
        fps = cfg["fps"]
        dt = 1.0 / fps
        NSUB = 12
        h = dt / NSUB
        self.build_path(cfg)
        name_len = max(self.name_len, 0.8)
        self.on, self.bloom_t, self.last_word, self.pop_t = False, None, -99.0, None
        self.pops, self.blooms = [], []
        last_word_end = -9.0
        T, X, Y, K, KI, SC, ON, Q = [], [], [], [], [], [], [], []
        self.hits, self.words = [], []
        parts = []          # particules : [x, y, vx, vy, age, life]
        self.parts_frames = []
        t, tau = 0.0, 0.0
        self.sigh = None
        end_s = cfg["end_s"]
        self.payoff_at = None
        ci = 1                      # prochain contact : fin de l'arc ci-1
        x, y, _, _ = self.pos(0.0)
        while t < end_s + 0.05:
            for _ in range(NSUB):
                self.t_now = t
                k = self.k_at(x, y, t)
                tau += k * h
                hit = None
                while ci <= len(self.arcs) and tau >= self.arcs[ci - 1][0] + self.arcs[ci - 1][1]:
                    a = self.arcs[ci - 1]
                    hit = {"sol": "sol", "tete": "tete", "mur_g": "mur", "mur_d": "mur", "plafond": "plafond"}.get(a[6], "sol")
                    cx, cy = self.contact_point(cfg["plan"][ci - 1])
                    hit_at = (cx, cy)
                    ci += 1
                    if hit == "sol":
                        _, _, nvx, _ = self.pos(tau)
                        for j in range(7):
                            an = math.pi * (0.15 + 0.7 * self.rng.random())
                            sp = 180 + 260 * self.rng.random()
                            parts.append([cx + (j - 3) * 12, FLOOR - 6, sp * math.cos(an) + 0.25 * nvx, -sp * math.sin(an), 0.0, 0.8 + 0.5 * self.rng.random()])
                x, y, _, _ = self.pos(tau)
                if hit:
                    self.hits.append((t, hit, hit_at[0], hit_at[1]))
                    if t >= self.hook_end and t >= last_word_end + 0.05:
                        self.words.append((t, hit, hit_at[0], hit_at[1]))
                        last_word_end = t + name_len
                        self.last_word = t
                        if not self.on:
                            self.on = True
                            self.bloom_t = t + BLOOM_DELAY
                            self.blooms.append(self.bloom_t)
                # la fin : rattrapé, il regèle ; la bulle va céder… et il soupire son nom
                if (self.payoff_at is None and len(self.blooms) >= 2 and self.on
                        and t - self.last_word >= Q_POP - cfg["sigh_before_pop"]):
                    self.payoff_at = t
                    ts = t + 0.15
                    bx_, by_, _, _ = self.pos(tau)
                    self.sigh = (ts, "soupir", bx_, by_)
                if self.sigh is not None and t >= self.sigh[0] and self.last_word < self.sigh[0]:
                    self.words.append(self.sigh)
                    self.last_word = self.sigh[0]
                if self.on and t - self.last_word >= Q_POP:
                    self.on = False
                    self.pops.append(t)
                    self.bloom_t = None
                for p in parts:
                    kp = self.k_at(p[0], p[1], t) * h
                    p[3] += 900 * kp
                    p[0] += p[2] * kp
                    p[1] = min(FLOOR - 4, p[1] + p[3] * kp)
                    p[4] += kp
                parts = [p for p in parts if p[4] < p[5]]
                t += h
            T.append(t); X.append(x); Y.append(y)
            K.append(self.k_at(x, y, t))
            KI.append(self.k_in(t - self.last_word) if self.on else 1.0)
            SC.append(self.zone_scale(t) if self.on else 0.0)
            ON.append(self.on)
            Q.append(t - self.last_word)
            self.parts_frames.append([(p[0], p[1], p[4] / p[5]) for p in parts])
        self.T, self.X, self.Y, self.K, self.KI, self.SC, self.ON, self.Q = map(np.array, (T, X, Y, K, KI, SC, ON, Q))
        if self.payoff_at is None:
            self.payoff_at = end_s - 2.0
        self.end_s = min(end_s, self.payoff_at + cfg["tail_s"])
        self.hi = 0

    def _place_lines(self, cfg):
        """Les « Slooo… » de Slo, posés dans des vols : jamais sur un contact dur (le moteur y couperait
        le mot de Bounce), jamais l'un sur l'autre."""
        hits = [h[0] for h in self.hits if h[0] >= self.hook_end - 0.5]
        prev_end = self.hook_end + 0.3
        L = []
        for (want, key) in cfg["slo_lines"]:
            d = self.dur[key]
            t0 = max(want, prev_end + 0.4)
            for _ in range(400):
                before = [h for h in hits if h <= t0 + 0.0]
                a_ok = (not before) or (t0 >= before[-1] + self.name_len + 0.18)
                nxt = [h for h in hits if h > t0 - 0.12]
                b_ok = (not nxt) or (t0 + d + 0.2 <= nxt[0])
                if a_ok and b_ok:
                    break
                t0 += 0.05
            L.append((round(t0, 3), key))
            prev_end = t0 + d
        self.line_plan = L
        self.lines = [(t0, WHO + " " + k, f"s{i}") for i, (t0, k) in enumerate(L)]

    # ---------------------------------------------------------------- moteur
    def idx(self, t):
        return int(min(len(self.T) - 1, max(0, round(t * self.cfg["fps"]) - 1)))

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.payoff_at is not None and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "repris"))
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
                i = int((t - n["start"]) * 60)
                return float(e[min(i, len(e) - 1)])
        return 0.0

    # ---------------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        i = self.idx(t)
        P = lambda x, y: (x * S, y * S)

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)

        def disc(x, y, r, **kw):
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], **kw)
        rect(0, CEIL, W, FLOOR, WALL)
        # la sortie : une porte ouverte au bas du mur de droite, de la lumière derrière
        for j in range(6):
            a = 0.10 * (1 - j / 6)
            dr.polygon([P(WALL_R, DOOR_TOP + 10), P(WALL_R, FLOOR), P(WALL_R - 150 - 40 * j, FLOOR)], fill=mix(WALL, LIGHT, a))
        # quelques lianes qui pendent du plafond : la forêt de Slo
        for (lx, ll, ph) in ((150, 230, 0.0), (300, 140, 1.3), (820, 260, 2.1), (960, 170, 0.7)):
            pts = [P(lx + 10 * math.sin(ph + 0.6 * t * 0.5 + s * 3.0) * s, CEIL + ll * s) for s in np.linspace(0, 1, 12)]
            dr.line(pts, fill=(30, 44, 34), width=int(6 * S), joint="curve")
            for s in (0.35, 0.7, 1.0):
                px, py = lx + 10 * math.sin(ph + 0.3 * t + s * 3.0) * s, CEIL + ll * s
                dr.ellipse([(px - 14) * S, (py - 7) * S, (px + 14) * S, (py + 7) * S], fill=(34, 56, 40))
        # la bulle de Slo
        ki, sc, on = self.KI[i], self.SC[i], self.ON[i]
        deep = (0.22 - ki) / (0.22 - K_DEEP) if on else 0.0
        deep = max(0.0, min(1.0, deep))
        if on and sc > 0:
            rz = RZ * sc
            q = self.Q[i]
            near = max(0.0, min(1.0, (q - (Q_POP - 2.2)) / 2.2))
            wob = (10 * near * near) * math.sin(t * 25)
            fill = mix(WALL, ZONE, 0.07 + 0.13 * deep)
            disc(SX, SY, rz + wob, fill=fill)
            for jj in range(3):                     # le bord : plus épais et plus sombre à mesure qu'il s'endort
                rr = rz + wob - jj * (10 + 14 * deep)
                if rr < 8:
                    continue
                disc(SX, SY, rr, outline=mix(WALL, ZONE, (0.55 - 0.15 * jj) * (0.6 + 0.4 * deep)), width=max(1, int((4 + 5 * deep) * S)))
            # des tirets qui tournent au rythme du temps de la bulle : lents dedans
            ph = float(np.sum(self.KI[:i + 1])) / self.cfg["fps"] * 0.9
            for jj in (range(18) if rz > 60 else ()):
                a0 = ph + jj * 2 * math.pi / 18
                dr.arc([(SX - rz + 18) * S, (SY - rz + 18) * S, (SX + rz - 18) * S, (SY + rz - 18) * S],
                       math.degrees(a0), math.degrees(a0) + 6, fill=mix(WALL, ZONE, 0.45), width=int(3 * S))
        for tp in self.pops:                        # la bulle éclate
            d = t - tp
            if 0 <= d < 0.45:
                rr = RZ + 140 * d / 0.45
                disc(SX, SY, rr, outline=mix(WALL, ZONE, 0.9 * (1 - d / 0.45)), width=int(10 * S * (1 - d / 0.45) + S))
                for jj in range(14):
                    a = jj * 2 * math.pi / 14
                    px, py = SX + (RZ + 220 * d) * math.cos(a), SY + (RZ + 220 * d) * math.sin(a)
                    disc(px, py, 9 * (1 - d / 0.45) + 2, fill=mix(WALL, ZONE, 1 - d / 0.45))
        # le sol, qui coupe la bulle
        rect(0, FLOOR, W, H, FLOOR_COL)
        rect(0, FLOOR, W, FLOOR + 6, dim(FLOOR_COL, 1.4))
        # les murs, la porte
        rect(0, CEIL - 10, W, CEIL, (40, 34, 52))
        rect(0, CEIL, WALL_L, FLOOR, (44, 38, 56))
        rect(WALL_R, CEIL, W, DOOR_TOP, (44, 38, 56))
        rect(WALL_R, DOOR_TOP, W, FLOOR, mix(WALL, LIGHT, 0.85))
        rect(WALL_R - 8, DOOR_TOP - 14, W, DOOR_TOP, (70, 56, 48))
        # le bruit, visible : une onde part de chaque « Bounce »
        for (tw, kind, hx, hy) in self.words:
            d = t - tw
            if 0 <= d < 0.6:
                rr = RB + 30 + 380 * d
                dr.ellipse([(hx - rr) * S, (hy - rr) * S, (hx + rr) * S, (hy + rr) * S],
                           outline=mix(WALL, (230, 230, 240), 0.55 * (1 - d / 0.6)), width=int(5 * S))
        # Slo
        sq = 0.0
        for (th, kind, hx, hy) in self.hits:
            d = t - th
            if kind == "tete" and 0 <= d < 2.5:
                kk = self.K[i]
                dd = d * (0.35 + 0.65 * kk)
                sq = max(sq, 0.12 * math.exp(-dd * 7) * math.cos(dd * 20))
        spin = 1.6 * float(np.sum(self.KI[:i + 1])) / self.cfg["fps"] + 0.3 * t
        draw_slo(dr, SX, SY, R, S, sq=sq, talk=self.talking(t), spin=spin, nod=deep)
        # zzz quand il dort pour de bon
        if not on:
            for jj in range(3):
                ph2 = (t * 0.5 + jj / 3) % 1.0
                zx, zy = SX + 70 + 60 * ph2, SY - R - 40 - 150 * ph2
                col = mix(WALL, (190, 170, 230), min(1.0, ph2 * 3, (1 - ph2) * 3))
                dr.text((zx * S, zy * S), "z" if jj % 2 else "Z", fill=col, anchor="mm", font=base.font(int((30 + 26 * ph2) * S)))
        # la poussière, au ralenti dans la bulle
        for (px, py, a) in self.parts_frames[i]:
            rr = 5 + 6 * a
            disc(px, py, rr, fill=mix(WALL, DUST, 0.8 * (1 - a)))
        # Bounce
        base.ball(dr, self.X[i] * S, self.Y[i] * S, RB * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.6,
            "hero_lose": "Bounce...", "end_s": 63.0, "plan": [], "slo_lines": [], "start": ["air", -90, 1150],
            "sigh_before_pop": 1.1, "tail_s": 2.4,
            "drowsy": [[0, 2.4, 0.8, 0.22], [40, 2.4, 0.8, 0.22], [47, 0.6, 0.33, 0.22], [56, 0.6, 0.33, 0.22], [58, 0.35, 0.3, 0.05]]}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
