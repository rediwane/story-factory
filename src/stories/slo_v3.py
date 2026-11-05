"""
Slo v3 : Bounce veut sortir du garage. Slo (le personnage d'un fan) dort au milieu.

Une seule règle, visible : chaque contact dur fait dire « Bounce » à Bounce et lance un anneau.
Quand l'anneau touche Slo, il fronce les sourcils, et 0,7 s plus tard sa bulle gonfle d'un cran.
Dans la bulle, Bounce passe au ralenti (le son, lui, n'est jamais ralenti). Un contact mou
(matelas, couverture) ne fait aucun bruit, et la bulle se dégonfle. Bounce tape lui-même le
bouton de la porte : le rideau descend par crans jusqu'à se fermer.

Le plan (config "plan") donne chaque contact en temps réel : [t, genre, paramètre]. Entre deux
contacts, Bounce suit une vraie parabole sous la gravité G, en temps propre ; le temps propre
écoulé est l'intégrale du facteur de ralenti de la bulle, calculée pour que le contact tombe à
l'instant voulu. Bounce ne s'arrête jamais.

Rien n'est ajouté au moteur : base.py n'est pas modifié. Ce script remplace seulement, pour
lui-même, la voix de l'accroche (débit, silences coupés), la réverbération (convolution FFT)
et les mots de Slo (banque de voix hors dépôt, cfg["slo_bank"]).

    python3 src/stories/slo_v3.py configs/slo_v3.json [--simulate]
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

# ------------------------------------------------------------------ voix de Slo (sa banque)
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
        raise SystemExit("[slo_v3] slo_bank manquant dans la config")
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


# ------------------------------------------------------------------ voix de l'accroche : plus vive, sans blanc
def hook_audio_tight(cfg):
    if not (cfg["hook_voice"] and cfg["hook_text"]):
        return None
    fixed = cfg.get("hook_wav")
    if fixed and os.path.exists(fixed):                    # prise figée (hors dépôt) : même durée à chaque rendu
        return _read(fixed)
    x = ak.piper_say(cfg["hook_text"], ak.VOICE_NAME, SR, cfg.get("hook_length_scale", 0.75))
    if x is None:
        x = ak.hook_voice(cfg["hook_text"])
    if x is None or not len(x):
        return None
    idx = np.where(np.abs(x) > 0.06 * np.abs(x).max())[0]
    x = x[max(0, idx[0] - int(0.01 * SR)):idx[-1] + int(0.03 * SR)].copy()
    n = min(int(0.02 * SR), len(x))
    x[-n:] *= np.linspace(1, 0, n)
    return x


base.hook_audio = hook_audio_tight


# ------------------------------------------------------------------ réverbération en FFT (même résultat que base.reverb)
def reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    m = len(x) + len(ir) - 1
    nf = 1 << (m - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:m]
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = reverb_fft

# ------------------------------------------------------------------ le mot de Bounce : la voix du moteur, la prise la plus nette
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

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
RB = 120.0                     # Bounce
RS = 100.0                     # Slo
SX, SY = 570.0, 1100.0         # Slo, couché au sol
CEIL = 480.0
FLOOR = 1200.0
WALL_R = 920.0                 # face du mur droit
DOOR_X = 160.0                 # plan de la porte (mur gauche)
DOOR_TOP = 560.0               # haut de l'ouverture
G = 2600.0
MAT_TOP = 1150.0               # dessus du matelas et de la couverture

C_BG = (10, 10, 16)
C_WALL = (30, 30, 44)
C_WALL2 = (22, 22, 32)
C_FLOOR = (36, 34, 46)
C_OUT = (88, 64, 40)
C_LAMP = (255, 206, 130)
C_MAT = (70, 86, 128)
C_BLK = (112, 40, 52)
C_METAL = (150, 152, 166)
C_SHUT = (96, 100, 114)
C_BUB = (120, 70, 210)
C_RIM = (214, 198, 255)
S_DISC = (128, 94, 186)
S_HALO = dim(S_DISC, 0.3)
S_EDGE = (120, 196, 214)
S_INK = (38, 22, 58)

K_LEVEL = [1.0, 0.45, 0.33, 0.25, 0.20, 0.18]
R_LEVEL = [150.0, 430.0, 540.0, 650.0, 760.0, 900.0]
A_LEVEL = [0.0, 0.20, 0.36, 0.52, 0.66, 0.78]       # (indice de teinte)
# teinte de chaque niveau : plus c'est lent, plus c'est sombre (luminance 83, 65, 49, 36, 25)
F_LEVEL = [(30, 30, 44), (92, 74, 140), (74, 56, 124), (60, 40, 108), (46, 28, 90), (34, 18, 72)]
SOFT = ("matelas", "matelas_mur", "couverture")


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def draw_slo(dr, x, y, r, S, sq=0.0, talk=0.0, spin=0.0, frown=0.0, eye=0.0):
    """Slo, d'après le dessin du fan : disque violet au halo sombre, yeux fermés en arcs, petite
    bouche ondulée, deux spirales de sommeil. `frown` fronce les sourcils, `eye` ouvre un œil."""
    sx, sy = 1 + sq, 1 - sq
    y = y + r * sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (y - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (y + 1.6 * r * sy) * S], fill=S_HALO)
    dr.ellipse([(x - r * sx) * S, (y - r * sy) * S, (x + r * sx) * S, (y + r * sy) * S], fill=S_DISC,
               outline=S_EDGE, width=max(1, int(0.025 * r * S)))

    def P(u, v):
        return ((x + u * r * sx) * S, (y + v * r * sy) * S)
    w = max(2, int(0.075 * r * S))
    for i, (cu, cv, ru, rv) in enumerate(((-0.40, 0.08, 0.20, 0.13), (0.33, 0.23, 0.16, 0.10))):
        if i == 1 and eye > 0.05:
            # un œil qui s'ouvre : blanc, pupille
            ro = 0.22 * ease(eye)
            dr.ellipse([P(cu - ro, cv - ro * 1.1)[0], P(cu - ro, cv - ro * 1.1)[1], P(cu + ro, cv + ro * 1.1)[0], P(cu + ro, cv + ro * 1.1)[1]],
                       fill=(245, 243, 248), outline=S_INK, width=max(2, int(0.04 * r * S)))
            rp = 0.09 * ease(eye)
            dr.ellipse([P(cu - 0.05 - rp, cv - rp)[0], P(cu - 0.05 - rp, cv - rp)[1], P(cu - 0.05 + rp, cv + rp)[0], P(cu - 0.05 + rp, cv + rp)[1]], fill=S_INK)
        else:
            pts = [P(cu + ru * math.cos(a), cv + rv * math.sin(a)) for a in np.linspace(0.05 * math.pi, 0.95 * math.pi, 14)]
            dr.line(pts, fill=S_INK, width=w, joint="curve")
        if frown > 0.02:
            # sourcils : de plus en plus froncés
            tilt = 0.10 + 0.16 * frown
            sgn = 1 if i == 0 else -1
            a0 = (cu - sgn * 0.17, cv - 0.30 - tilt * 0.5)
            a1 = (cu + sgn * 0.17, cv - 0.30 + tilt * 0.5)
            dr.line([P(*a0), P(*a1)], fill=S_INK, width=max(2, int(0.07 * r * S)))
    if talk > 0.08:
        mw, mh = 0.13 + 0.03 * talk, 0.05 + 0.13 * talk
        dr.polygon([P(0.0 + mw * math.cos(a), 0.70 + mh * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 20)], fill=S_INK)
    else:
        pts = [P(-0.15 + 0.30 * i / 16, 0.72 - 0.06 * math.sin(2 * math.pi * i / 16 + 0.6)) for i in range(17)]
        dr.line(pts, fill=S_INK, width=max(2, int(0.06 * r * S)), joint="curve")
    for (cu, cv, rr, ph) in ((0.58, -0.50, 0.20, 0.0), (0.95, 0.02, 0.23, 1.7)):
        pts = []
        for i in range(30):
            a = spin + ph + i / 29 * 2.3 * math.pi
            rad = rr * (0.15 + 0.85 * i / 29)
            pts.append(P(cu + rad * math.cos(a), cv + rad * math.sin(a)))
        dr.line(pts, fill=S_INK, width=max(2, int(0.065 * r * S)), joint="curve")


class Sim:
    scene_top = CEIL / H

    # ---------------------------------------------------------------- géométrie des contacts
    def contact_point(self, kind, p, t):
        if kind == "tete":                       # p : angle depuis le sommet de Slo, en degrés (+ = à droite)
            a = math.radians(p)
            return SX + (RB + RS) * math.sin(a), SY - (RB + RS) * math.cos(a)
        if kind == "mur":
            return WALL_R - RB, p
        if kind == "bouton":
            return WALL_R - RB, 790.0
        if kind == "matelas":
            return p, MAT_TOP - RB
        if kind == "matelas_mur":
            return WALL_R - 50 - RB, p
        if kind == "couverture":
            return p, MAT_TOP - RB
        if kind == "seuil":
            return 290.0, FLOOR - 15 - RB
        if kind == "barre":                      # il touche le coin du bas de la barre du rideau
            yb = self.bar_y(t)
            return DOOR_X + 8 + 74.0, yb + 94.0
        if kind == "rideau":
            return DOOR_X + 8 + RB + 2, p
        if kind == "air":
            return float(p[0]), float(p[1])
        raise ValueError(kind)

    # ---------------------------------------------------------------- le rideau, par crans
    def bar_y(self, t):
        d = 0.0
        for (tc, dd) in self.cfg["crans"]:
            if t >= tc:
                d = dd if t >= tc + 0.25 else lerp(d, dd, ease((t - tc) / 0.25))
        ts, te = self.cfg["slam"]
        if t >= ts:
            u = min(1.0, (t - ts) / (te - ts))
            d = lerp(d, FLOOR - DOOR_TOP, u * u)              # il tombe, de plus en plus vite
        return DOOR_TOP + d

    # ---------------------------------------------------------------- la bulle : niveau, rayon, ralenti
    def build_bubble(self):
        cfg = self.cfg
        evs = []                                  # (t, type, data)
        self.rings, self.reach = [], []
        for (t, kind, p) in self.plan:
            if kind in SOFT:
                evs.append((t, "deflate", None))
                continue
            x, y = self.contact_point(kind, p, t)
            d = math.hypot(x - SX, y - SY)
            tr = t + max(0.0, d - RS - RB) / cfg["ring_speed"]
            self.rings.append((t, x, y))
            self.reach.append((tr, kind))
            if kind == "seuil":
                evs.append((tr + 0.1, "mega", None))
            elif kind == "rideau":
                evs.append((tr + cfg["lag"], "puff", 1))
            else:
                big = any(abs(t - b) < 0.02 for b in cfg.get("big_puff_at", []))
                evs.append((tr + (cfg["big_lag"] if big else cfg["lag"]), "puff", cfg.get("big_puff_levels", 3) if big else 1))
        evs.sort(key=lambda e: e[0])
        self.bub_events = evs
        # échantillonnage à 240 Hz
        hz = 240
        n = int((self.end_s + 1.0) * hz) + 1
        T = np.arange(n) / hz
        K = np.ones(n); R = np.full(n, R_LEVEL[0]); A = np.zeros(n); LV = np.zeros(n)
        level, kcur, rcur, acur = 0, 1.0, R_LEVEL[0], 0.0
        k0, r0, a0, tchg, dur = 1.0, R_LEVEL[0], 0.0, -9.0, 0.3
        kt, rt, at = 1.0, R_LEVEL[0], 0.0
        ei = 0
        for i in range(n):
            t = T[i]
            while ei < len(evs) and evs[ei][0] <= t:
                et, typ, data = evs[ei]
                k0, r0, a0, tchg = kcur, rcur, acur, et
                if typ == "puff":
                    level = min(5, level + data)
                    kt, rt, at, dur = K_LEVEL[level], R_LEVEL[level], A_LEVEL[level], 0.3
                elif typ == "deflate":
                    level = 0
                    kt, rt, at, dur = 1.0, R_LEVEL[0], 0.0, 0.4
                elif typ == "mega":
                    level = 3
                    kt, rt, at, dur = cfg["mega_k"], 1100.0, A_LEVEL[4], 0.25
                ei += 1
            u = ease((t - tchg) / dur)
            kcur, rcur, acur = lerp(k0, kt, u), lerp(r0, rt, u), lerp(a0, at, u)
            K[i], R[i], A[i], LV[i] = kcur, rcur, acur, level
        self.bT, self.bK, self.bR, self.bA, self.bL = T, K, R, A, LV
        self.bhz = hz

    def bub(self, t):
        i = int(min(len(self.bT) - 1, max(0, round(t * self.bhz))))
        return self.bK[i], self.bR[i], self.bA[i]

    def slow(self, t):
        a, b, f = self.cfg["ralenti"]
        return f if a <= t < b else 1.0

    def k_eff(self, x, y, t):
        k, r, _ = self.bub(t)
        d = math.hypot(x - SX, y - SY)
        u = ease((r - d) / 90.0)
        return (1.0 - (1.0 - k) * u) * self.slow(t)

    # ---------------------------------------------------------------- arcs
    @staticmethod
    def arc(A, B, Tp):
        vx = (B[0] - A[0]) / Tp
        vy = (B[1] - A[1] - 0.5 * G * Tp * Tp) / Tp
        return vx, vy

    def run_seg(self, A, B, ta, tb, Tp, record=False):
        vx, vy = self.arc(A, B, Tp)
        h = 1.0 / 240.0
        t, tau = ta, 0.0
        out = []
        while tau < Tp and t < tb + 3.0:
            x = A[0] + vx * tau
            y = A[1] + vy * tau + 0.5 * G * tau * tau
            if record:
                out.append((t, x, y, tau))
            tau += self.k_eff(x, y, t) * h
            t += h
        return t, out

    def t_max(self, A, B, tb_ta):
        """Le plus long temps propre dont l'arc ne touche pas le plafond."""
        best = 0.02
        for i in range(1, 400):
            T = i * 0.005
            if T > tb_ta + 1e-3:
                break
            vx, vy = self.arc(A, B, T)
            top = A[1] - (vy * vy / (2 * G) if vy < 0 else 0.0)
            if top >= CEIL + RB:
                best = T
        return best

    def solve_seg(self, A, B, ta, tb):
        lo, hi = 0.01, self.t_max(A, B, tb - ta)
        tarr, _ = self.run_seg(A, B, ta, tb, hi)
        if tarr < tb - 0.02:
            self.warn_slow.append(f"arc trop court {ta:.2f}->{tb:.2f} (arrive a {tarr:.2f})")
            return hi
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            tarr, _ = self.run_seg(A, B, ta, tb, mid)
            if tarr > tb:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    # ---------------------------------------------------------------- construction
    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.rng = rng
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.end_s = cfg["end_s"]
        self.plan = [(float(c[0]), c[1], c[2] if len(c) > 2 else None) for c in cfg["plan"]]
        self.build_bubble()
        # trajectoire, segment par segment
        pts = [(0.0, "air", cfg["start"])] + self.plan
        fps = cfg["fps"]
        nfr = int(self.end_s * fps) + 2
        self.X = np.zeros(nfr); self.Y = np.zeros(nfr)
        self.segs = []
        warn = []
        self.warn_slow = warn
        for (ta, ka, pa), (tb, kb, pb) in zip(pts, pts[1:]):
            A = self.contact_point(ka, pa, ta)
            B = self.contact_point(kb, pb, tb)
            Tp = self.solve_seg(A, B, ta, tb)
            _, rec = self.run_seg(A, B, ta, tb, Tp, record=True)
            vx, vy = self.arc(A, B, Tp)
            self.segs.append((ta, tb, A, B, Tp, vx, vy, kb))
            ys = [r[2] for r in rec] or [A[1]]
            dmin = min([math.hypot(r[1] - SX, r[2] - SY) for r in rec[3:-3]] or [999])
            if min(ys) < CEIL + RB - 2:
                warn.append(f"plafond {ta:.2f}->{tb:.2f} ({min(ys):.0f})")
            if dmin < RB + RS - 6:
                warn.append(f"traverse Slo {ta:.2f}->{tb:.2f} (d={dmin:.0f})")
            if max(ys) > FLOOR - RB + 2:
                warn.append(f"sous le sol {ta:.2f}->{tb:.2f} ({max(ys):.0f})")
            for (tt, x, y, _) in rec[2:-2]:
                ybt = self.bar_y(tt)
                # le cercle de Bounce coupe-t-il la plaque du rideau [DOOR_X-22, DOOR_X+8] x [DOOR_TOP, yb] ?
                cx = min(max(x, DOOR_X - 22), DOOR_X + 8); cy = min(max(y, DOOR_TOP), ybt)
                if math.hypot(x - cx, y - cy) < RB - 4:
                    warn.append(f"traverse le rideau {ta:.2f}->{tb:.2f} (t={tt:.2f})"); break
            xs = [r[1] for r in rec]
            if xs and max(xs) > WALL_R - RB + 2:
                warn.append(f"dans le mur droit {ta:.2f}->{tb:.2f}")
            # échantillons aux images
            for (t, x, y, _) in rec:
                fi = int(math.floor(t * fps + 1e-9))
                if 0 <= fi < nfr and abs(t - fi / fps) < 1.0 / 240 + 1e-9:
                    self.X[fi], self.Y[fi] = x, y
        # images non couvertes : interpolation (sécurité)
        idx = np.arange(nfr)
        filled = (self.X != 0) | (self.Y != 0)
        self.X = np.interp(idx, idx[filled], self.X[filled])
        self.Y = np.interp(idx, idx[filled], self.Y[filled])
        self.warn = warn
        for w in warn:
            print("[slo_v3] attention :", w, file=sys.stderr)
        # les « z » de Slo : âge propre = intégrale du ralenti au centre de Slo
        kc = np.array([self.k_eff(SX, SY - 200, t) for t in self.bT])
        self.KC = np.cumsum(kc) / self.bhz
        # les contacts durs et mous
        self.hits = [(t, kind) for (t, kind, p) in self.plan if kind not in SOFT and t <= self.end_s]
        self.softs = [(t, kind, p) for (t, kind, p) in self.plan if kind in SOFT]
        self.hi = 0
        self.payoff_at = cfg["payoff_s"]
        self.lines = [(float(t), WHO + " " + k, f"s{i}") for i, (t, k) in enumerate(cfg["slo_lines"])]
        self.issue = cfg["slam"][1]
        self.button_t = next((t for (t, k, p) in self.plan if k == "bouton"), 1e9)
        self.seuil_reach = next((tr for (tr, k) in self.reach if k == "seuil"), 1e9)

    # ---------------------------------------------------------------- moteur
    def step(self, dt):
        evs = []
        t_prev = self.t
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= t_prev + 1e-9:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and t_prev >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "porte"))
        if t_prev >= self.end_s:
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

    def idx(self, t):
        return int(min(len(self.X) - 1, max(0, round(t * self.cfg["fps"]))))

    # ---------------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        i = self.idx(t)
        bx, by = self.X[i], self.Y[i]

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)

        def disc(x, y, r, **kw):
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], **kw)

        yb = self.bar_y(t)
        k, rb, ab = self.bub(t)
        # le mur du fond
        rect(DOOR_X, CEIL, WALL_R, FLOOR, C_WALL)
        # la bulle de Slo (coupée par le sol)
        if rb > RS * 1.55:
            fill = F_LEVEL[5] if ab > A_LEVEL[5] else F_LEVEL[0]
            for q in range(1, 6):
                lo_, hi_ = A_LEVEL[q - 1], A_LEVEL[q]
                if lo_ <= ab <= hi_:
                    fill = mix(F_LEVEL[q - 1], F_LEVEL[q], (ab - lo_) / (hi_ - lo_)); break
            disc(SX, SY, rb, fill=fill)
            # les crans : un anneau par niveau, nets
            lv = int(round(ab / 0.16))
            for j in range(1, lv + 1):
                rr = rb - j * 34
                if rr > RS * 1.7:
                    disc(SX, SY, rr, outline=mix(fill, C_RIM, 0.22), width=max(1, int(3 * S)))
            disc(SX, SY, rb, outline=C_RIM, width=max(2, int(6 * S)))
        else:
            disc(SX, SY, RS * 1.75, outline=mix(C_WALL, C_RIM, 0.35), width=max(1, int(3 * S)))
        # dehors : la rue, vue par la porte (la bulle ne déborde pas dehors)
        rect(0, CEIL, DOOR_X, FLOOR, C_OUT)
        disc(40, 760, 110, fill=mix(C_OUT, C_LAMP, 0.35))
        disc(40, 760, 45, fill=mix(C_OUT, C_LAMP, 0.8))
        rect(0, FLOOR - 4, DOOR_X, FLOOR, mix(C_OUT, C_LAMP, 0.25))
        # les masses de mur (au-dessus de la porte, à droite, le plafond) : elles recouvrent la bulle
        rect(0, 0, W, CEIL, C_BG)
        rect(0, CEIL - 10, W, CEIL, (46, 46, 62))
        rect(WALL_R, CEIL, W, FLOOR, C_WALL2)
        rect(0, CEIL, DOOR_X, DOOR_TOP, C_WALL2)
        # le sol
        rect(0, FLOOR, W, H, C_FLOOR)
        for j in range(1, 7):                                   # le sol qui fuit vers nous
            xa = 540 + (j - 3.5) * 190
            dr.line([(xa * S, FLOOR * S), ((540 + (xa - 540) * 3.2) * S, H * S)], fill=dim(C_FLOOR, 0.82), width=max(1, int(3 * S)))
        for yy in (1330, 1520, 1780):
            rect(0, yy, W, yy + 3, dim(C_FLOOR, 0.82))
        rect(0, FLOOR, W, FLOOR + 5, mix(C_FLOOR, (255, 255, 255), 0.12))
        # ombres de Slo et de Bounce sur le sol
        dr.ellipse([(SX - 130) * S, (FLOOR + 30) * S, (SX + 130) * S, (FLOOR + 80) * S], fill=dim(C_FLOOR, 0.8))
        hgt = max(0.0, FLOOR - RB - by)
        sw = 120 * (1 - min(0.5, hgt / 900))
        dr.ellipse([(bx - sw) * S, (FLOOR + 30) * S, (bx + sw) * S, (FLOOR + 80) * S], fill=dim(C_FLOOR, 0.8))
        gap = max(0.0, FLOOR - yb)
        if gap > 2:
            g = gap / (FLOOR - DOOR_TOP)
            yl = FLOOR + 380 * g
            dr.polygon([(0, FLOOR * S), (DOOR_X * S, FLOOR * S), ((DOOR_X + 420 * g) * S, yl * S), (0, yl * S)],
                       fill=mix(C_FLOOR, C_LAMP, 0.16))
        # le matelas (coin droit), la couverture (gauche), le seuil
        dent_m = dent_b = 0.0
        for (ts, kind, p) in self.softs:
            d = t - ts
            if 0 <= d < 0.45:
                dd = 24 * math.exp(-d / 0.12) * (1 - d / 0.45)
                if kind == "couverture":
                    dent_b = max(dent_b, dd)
                else:
                    dent_m = max(dent_m, dd)
        rect(670, MAT_TOP, WALL_R, FLOOR, C_MAT)
        rect(870, 860, WALL_R, FLOOR, C_MAT)
        for yy in (MAT_TOP + 14, MAT_TOP + 32):
            rect(680, yy, WALL_R, yy + 4, mix(C_MAT, (255, 255, 255), 0.22))
        rect(878, 870, 884, FLOOR, mix(C_MAT, (255, 255, 255), 0.22))
        if dent_m > 0.5:
            dr.ellipse([(bx - 95) * S, (MAT_TOP - 8) * S, (bx + 95) * S, (MAT_TOP + dent_m) * S], fill=dim(C_MAT, 0.55))
        rect(300, MAT_TOP, 462, FLOOR, C_BLK)
        rect(306, MAT_TOP + 18, 456, MAT_TOP + 22, mix(C_BLK, (255, 255, 255), 0.22))
        if dent_b > 0.5:
            dr.ellipse([(bx - 95) * S, (MAT_TOP - 8) * S, (bx + 95) * S, (MAT_TOP + dent_b) * S], fill=dim(C_BLK, 0.55))
        rect(DOOR_X - 20, FLOOR - 15, 298, FLOOR, C_METAL)
        # la porte : le rideau à lamelles descend devant la rue (vu de biais)
        rect(DOOR_X - 2, DOOR_TOP - 40, DOOR_X + 10, FLOOR, (58, 58, 72))
        rect(0, DOOR_TOP - 40, DOOR_X + 10, DOOR_TOP, (54, 54, 68))
        if yb > DOOR_TOP + 1:
            rect(0, DOOR_TOP, DOOR_X - 2, yb, C_SHUT)
            yy = DOOR_TOP + 20
            while yy < yb - 4:
                rect(0, yy, DOOR_X - 2, yy + 4, dim(C_SHUT, 0.72))
                yy += 26
            rect(0, yb - 14, DOOR_X + 10, yb, (140, 144, 160))
        # le gyrophare, au-dessus de la porte : il clignote tant que la porte bouge
        on = self.button_t <= t < self.issue
        gx, gy = DOOR_X + 46, DOOR_TOP - 30
        blink = on and (int(t * 4) % 2 == 0)
        if blink:
            disc(gx, gy, 46, fill=mix(C_WALL, (255, 150, 40), 0.35))
        disc(gx, gy, 18, fill=(255, 170, 60) if blink else ((200, 110, 30) if on else (90, 60, 40)))
        # le bouton, sur le mur droit
        pressed = t >= self.button_t
        rect(WALL_R - 12, 750, WALL_R, 830, (70, 70, 84))
        disc(WALL_R - 14, 790, 26, fill=(255, 70, 70) if pressed else (170, 30, 36))
        # les « z » de Slo, au ralenti dans la bulle
        kc = float(self.KC[int(min(len(self.KC) - 1, max(0, round(t * self.bhz))))])
        for j in range(3):
            ph = (kc * 0.45 + j / 3) % 1.0
            zx, zy = SX + 60 + 70 * ph, SY - RS - 30 - 170 * ph
            col = mix(C_WALL, (210, 190, 250), min(1.0, ph * 3, (1 - ph) * 3))
            dr.text((zx * S, zy * S), "z" if j % 2 else "Z", fill=col, anchor="mm", font=base.font(int((30 + 30 * ph) * S)))
        # Slo : froncement à chaque anneau reçu, écrasement sous un choc, œil ouvert au seuil
        frown = 0.0
        for (tr, kind) in self.reach:
            d = t - tr
            if 0 <= d < 1.2:
                frown = max(frown, min(1.0, d / 0.08) * (1 - max(0.0, d - 0.9) / 0.3))
        sq = 0.0
        for (th, kind) in self.hits:
            d = t - th
            if kind == "tete" and 0 <= d < 0.8:
                sq = max(sq, 0.10 * math.exp(-d * 6) * math.cos(d * 22))
        eye = 0.0
        d = t - self.seuil_reach
        if 0 <= d < 2.4:
            eye = min(1.0, d / 0.12) * (1 - max(0.0, d - 1.9) / 0.5)
        spin = 1.4 * kc + 0.2 * t
        draw_slo(dr, SX, SY, RS, S, sq=sq, talk=self.talking(t), spin=spin, frown=frown, eye=eye)
        # les anneaux : le bruit de Bounce, qui part de lui
        for (tw, hx, hy) in self.rings:
            d = t - tw
            rr = RB + 20 + self.cfg["ring_speed"] * d
            if 0 <= d and rr < RB + 470:
                a = 1 - (rr - RB) / 470
                dr.ellipse([(hx - rr) * S, (hy - rr) * S, (hx + rr) * S, (hy + rr) * S],
                           outline=mix(C_WALL, (250, 250, 255), 0.85 * a), width=max(2, int(7 * S * a + 1)))
        # Bounce
        base.ball(dr, bx * S, by * S, RB * S)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0,
            "hook_text_s": 99.0, "hook_top": 0.125, "hook_font_size": 84, "hook_width": 0.70,
            "hero_shock_s": 1.0, "hero_lose": "Oh no.", "ring_speed": 900.0, "lag": 0.5, "big_lag": 0.15, "mega_k": 0.25,
            "end_s": 64.0, "payoff_s": 62.45, "plan": [], "slo_lines": [], "start": [760, 760],
            "crans": [], "slam": [59.1, 60.0], "ralenti": [59.0, 60.0, 0.35], "big_puff_at": []}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
