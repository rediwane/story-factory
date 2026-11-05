"""
Prototype « camping » : une petite tente la nuit, vue de face, les pans de porte ouverts. Dehors, un
grand ours sans visage rôde ; on voit son ombre sur la toile du fond, éclairée par la lune. Dedans,
Bounce rebondit (glacière, tapis de sol : « Bounce » ; sac de couchage : muet) et essaie d'attraper la
lanterne éteinte. L'ours cherche le bruit (ombre, patte sur le toit, museau sous la toile, tapes,
oreille collée au toit qui fait descendre la lanterne) ; Bounce allume la lanterne : son ombre géante
fait fuir l'ours dans un sapin. Éjecté dehors, Bounce est reniflé, ignoré, et l'ours prend la tente.

Tout est calculé d'avance sur une seule horloge : la liste des contacts de Bounce (arcs balistiques
exacts sous G entre deux contacts), les poses de l'ours par images clés, les creux de toile, la
lanterne (pendule de même gravité). Une seule voix en dehors de Bounce : l'accroche.

    python3 src/stories/camping.py configs/<name>.json [--simulate | --plan | --still t1,t2,...]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
import audio_kit as ak
from PIL import Image, ImageDraw, ImageChops

SR = ak.SR
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        if best is not None:
            best = np.where(np.abs(best) < 1e-9, 0.0, best)   # pas de flottants dénormaux (convolution lente)
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# la réverbération du moteur (écho du nom) par FFT : même résultat, sans la convolution directe
# de numpy, qui reste bloquée plusieurs minutes sur cette machine pour ces longueurs.
_np_convolve = np.convolve


def _fft_convolve(a, v, mode="full"):
    a, v = np.asarray(a, float), np.asarray(v, float)
    if mode != "full" or min(len(a), len(v)) < 64:
        return _np_convolve(a, v, mode)
    n = len(a) + len(v) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, N) * np.fft.rfft(v, N), N)[:n]


def reverb_fft(x, sr, tail_s=0.8, wet=0.5):
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    wetx = _fft_convolve(x, ir)
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = reverb_fft

# ------------------------------------------------------------------ outils
W, H = 1080, 1920
R = 90.0
G = 2600.0


def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, s):
    return a + (b - a) * s


def mix(c0, c1, s):
    return tuple(int(a + (b - a) * s) for a, b in zip(c0, c1))


def pulse(t, t0, a=0.12, b=0.25):
    """0 -> 1 -> 0 autour de t0 (montée a, descente b)."""
    if t < t0 - a or t > t0 + b:
        return 0.0
    if t <= t0:
        return smooth((t - (t0 - a)) / a)
    return 1.0 - smooth((t - t0) / b)


class Keys:
    """Une valeur par images clés [(t, v)], interpolation douce (ou linéaire)."""

    def __init__(self, keys, ease=smooth):
        self.k = sorted(keys, key=lambda p: p[0])
        self.ease = ease

    def __call__(self, t):
        k = self.k
        if t <= k[0][0]:
            return k[0][1]
        for (t0, v0), (t1, v1) in zip(k, k[1:]):
            if t <= t1:
                s = self.ease((t - t0) / max(1e-6, t1 - t0))
                if isinstance(v0, tuple):
                    return tuple(lerp(a, b, s) for a, b in zip(v0, v1))
                return lerp(v0, v1, s)
        return k[-1][1]


# ------------------------------------------------------------------ la tente
APX, APY = 500.0, 540.0              # pointe (sans affaissement)
BLX, BRX, BASE = 60.0, 935.0, 1380.0
FLAP = 34.0                          # largeur des pans noués sur les côtés
HEM = 1330.0                         # bas de la toile du fond
FRONT = 1386.0                       # bord avant du tapis de sol
SHY = 1050.0                         # au-dessous, les parois ne plient pas
GROUND_Y = 1490.0                    # centre de Bounce posé dehors
FLOOR_C, COOL_C, BAG_C = 1290.0, 1130.0, 1215.0
COOLER = (272.0, 1218.0, 462.0, 1384.0)
BAG = (548.0, 878.0)                 # x du sac de couchage
LANT_L = 230.0                       # du point d'attache au bas de la lanterne
OMEGA = math.sqrt(G / 200.0)         # pendule de même gravité


def seg_pt(p, q, s):
    return (lerp(p[0], q[0], s), lerp(p[1], q[1], s))


def line_x_at(p, q, y):
    s = (y - p[1]) / (q[1] - p[1])
    return lerp(p[0], q[0], s)


# ------------------------------------------------------------------ le plan des contacts
# surfaces : (y du centre de Bounce, dur ?, touchée par-dessous ?)
SURF = {
    "F": (FLOOR_C, True, False), "C": (COOL_C, True, False), "B": (BAG_C, False, False),
    "N": (1186.0, False, False), "G": (GROUND_Y, True, False),
    "D": (None, False, True), "P": (None, False, True), "E": (None, False, True),
    "L": (None, True, True), "T": (None, False, False),
}


def arc_time(y0, y1, h, over_to, over_from):
    if over_to:                      # monte jusqu'à une surface au-dessus, sommet virtuel h au-dessus
        top = y1 - h
        return math.sqrt(2 * (y0 - top) / G) - math.sqrt(2 * (y1 - top) / G)
    if over_from:                    # repart vers le bas après un contact par-dessous
        top = y0 - h
        return math.sqrt(2 * (y1 - top) / G) - math.sqrt(2 * (y0 - top) / G)
    top = min(y0, y1) - h
    return math.sqrt(2 * (y0 - top) / G) + math.sqrt(2 * (y1 - top) / G)


# (surface, h, x, y imposé ou None, étiquette)
SEQ = [
    # --- A. l'ombre entend ; Bounce vise la lanterne
    ("B", 0.39, 600, None, "start"),
    ("B", 165, 630, None, ""),
    ("F", 215, 520, None, "first"),
    ("C", 170, 395, None, ""),
    ("B", 100, 630, None, ""),
    ("F", 120, 470, None, ""),
    ("F", 240, 590, None, "try1"),           # saut sous la lanterne : trop court
    ("B", 90, 630, None, ""),
    ("C", 175, 395, None, "nose_close"),
    ("F", 170, 470, None, ""),
    ("F", 240, 590, None, "try2"),
    ("C", 170, 395, None, "rear"),
    ("F", 170, 470, None, "paw_down"),
    # --- B. la patte sur le toit
    ("D", 40, 612, 1118, "dent1"),
    ("B", 0, 610, None, ""),
    ("D", 22, 626, 1124, "dent2"),
    ("B", 0, 630, None, ""),
    ("D", 12, 636, 1132, "dent3"),
    ("F", 20, 520, None, "paw_jerk"),
    ("C", 170, 395, None, "lie"),
    ("F", 170, 455, None, "hem"),
    # --- C. le museau sous la toile
    ("C", 170, 395, None, "snout_left"),
    ("B", 120, 630, None, ""),
    ("F", 120, 600, None, "snout_right"),
    ("C", 170, 395, None, "snout_left2"),
    ("N", 60, 520, None, "boop1"),
    ("N", 55, 524, None, "boop2"),
    ("F", 40, 566, None, "snout_out"),
    # --- D1. l'ours debout, les tapes
    ("C", 170, 395, None, "rise"),
    ("F", 170, 480, None, "stand"),
    ("B", 120, 630, None, ""),
    ("C", 160, 395, None, "paws_apex"),
    ("F", 170, 510, None, ""),
    ("B", 150, 630, None, "tap1"),
    ("F", 150, 520, None, "tap2"),
    ("C", 170, 395, None, "tap3"),
    ("B", 110, 630, None, ""),
    ("F", 140, 455, None, "tap4_wait"),
    ("B", 60, 620, None, ""),
    ("P", 60, 420, 1050, "tap4"),            # la 4e tape tombe sur lui à travers la toile
    ("F", 0, 470, None, "tap4_down"),
    ("C", 170, 395, None, "paw_drop"),
    # --- D2. l'oreille collée au toit : chaque « Bounce » fait descendre la lanterne
    ("F", 170, 520, None, "ear_on"),
    ("B", 140, 630, None, ""),
    ("C", 150, 395, None, "n1"),
    ("F", 170, 470, None, "n2"),
    ("F", 240, 590, None, "n3"),             # essai sous la lanterne
    ("B", 100, 630, None, "yawn"),
    ("C", 100, 395, None, "n4"),
    ("B", 120, 630, None, ""),
    ("E", 30, 578, 1078, "brush"),           # frôle l'oreille à travers la toile
    ("F", 10, 470, None, "n5"),
    ("F", 240, 590, None, "n6"),             # essai
    ("B", 100, 630, None, ""),
    ("C", 60, 395, None, "n7"),
    ("B", 60, 630, None, ""),
    ("F", 80, 470, None, "n8"),
    ("F", 240, 590, None, "n9"),             # essai : il manque un doigt
    ("B", 110, 600, None, "reach"),
    ("L", 25, None, None, "ON"),
    # --- E. l'ombre géante
    ("B", 0, 630, None, ""),
    ("C", 170, 395, None, ""),
    ("F", 170, 500, None, ""),
    ("B", 150, 620, None, ""),
    ("L", 40, None, None, "giant"),
    ("B", 0, 630, None, "fall"),
    ("F", 160, 520, None, ""),
    ("C", 170, 395, None, "flee"),
    ("B", 160, 620, None, ""),
    ("L", 40, None, None, "giant2"),
    ("B", 0, 630, None, "bend"),
    ("B", 150, 620, None, ""),
    ("L", 20, None, None, "swing"),
    ("B", 0, 630, None, "squash"),
    ("C", 110, 418, None, "corner"),
    # --- F. dehors
    ("G", 140, 610, None, "out"),
    ("G", 330, 650, None, "look"),
    ("G", 360, 690, None, "drop"),
    ("G", 300, 720, None, "land"),
    ("G", 260, 740, None, "approach"),
    ("G", 300, 750, None, "approach2"),
    ("G", 300, 760, None, "freeze"),
    ("G", 280, 760, None, "sniff"),
    ("G", 250, 765, None, "sniff2"),
    ("G", 300, 765, None, "yawn2"),
    ("G", 320, 770, None, "enter"),
    ("G", 300, 775, None, "last"),
    ("T", 60, 772, 900, "knock1"),
    ("T", 140, 770, 900, "knock2"),
    ("T", 200, 772, 900, "knock3"),
]


BOW_END = 48.0                       # la tente gonflée par l'ours, à la fin
CUP = 34.0                           # le creux de toile sous Bounce quand il frappe la tente fermée
KNOCK_S = 0.50                       # où, le long du pan droit (0 = sol, 1 = pointe)


def knock_point():
    p0, p1 = (BRX, BASE), (APX, APY)
    L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    d = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
    n_out = (-d[1], d[0]) if -d[1] > 0 else (d[1], -d[0])
    q = seg_pt(p0, p1, KNOCK_S)
    k = BOW_END + R - CUP
    return q[0] + n_out[0] * k, q[1] + n_out[1] * k


class Plan:
    def __init__(self):
        self.sag_keys = [(0.0, 0.0)]
        self.kicks = []                       # (t, amplitude rad) du pendule de la lanterne
        self.lifts = []                       # (t) la lanterne cognée par-dessous saute
        self.C = []                           # (t, x, y, surface, tag)
        t = SEQ[0][1]
        prev = SEQ[0]
        self.C.append((t, float(SEQ[0][2]), BAG_C, "B", "start"))
        self.tags = {"start": t}
        self.events_before()
        for row in SEQ[1:]:
            s, h, x, y, tag = row
            y0 = self.C[-1][2]
            over_to = SURF[s][2]
            over_from = SURF[prev[0]][2]
            if s == "L":
                # la lanterne là où elle sera : quelques itérations sur l'instant du contact
                tc = t + 0.4
                for _ in range(6):
                    lx, ly = self.lantern_bottom(tc)
                    yy = ly + R
                    dt = arc_time(y0, yy, h, True, over_from)
                    tc = t + dt
                x, y = lx, yy
            elif s == "T":
                x, y = knock_point()
                dt = arc_time(y0, y, h, over_to, over_from)
            else:
                y = SURF[s][0] if y is None else y
                dt = arc_time(y0, y, h, over_to, over_from)
            t += dt
            self.C.append((t, float(x), float(y), s, tag))
            if tag:
                self.tags[tag] = t
            self.on_contact(t, s, tag)
            prev = row
        self.finish()

    # --- la lanterne et l'affaissement
    def events_before(self):
        pass

    def on_contact(self, t, s, tag):
        if s == "L":
            self.kicks.append((t, 0.0))      # pas de balancement : il la cogne par-dessous
            self.lifts.append(t)
        if tag in ("paw_jerk", "snout_out"):
            self.kicks.append((t + 0.05, 0.16))
        if tag == "paws_apex":
            self.sag_keys += [(t - 0.05, 0.0), (t + 0.25, 46.0), (t + 0.6, 34.0)]
            self.kicks.append((t + 0.1, 0.12))
        if tag == "tap3":
            for k in range(3):
                self.kicks.append((t + 0.35 + 0.22 * k, 0.05))
        if tag == "paw_drop":
            self.sag_keys += [(t + 0.2, 34.0), (t + 0.7, 10.0)]
        if tag == "ear_on":
            self.sag_keys += [(t + 0.15, 10.0), (t + 0.55, 34.0)]
            self.kicks.append((t + 0.3, 0.08))
        if tag in ("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9"):
            k = int(tag[1:])
            cur = self.sag_keys[-1][1]
            new = 34.0 + 12.7 * k
            # l'oreille sursaute (la pointe remonte un peu), puis appuie plus fort
            self.sag_keys += [(t + 0.05, cur), (t + 0.2, cur - 14.0), (t + 0.55, new)]
            self.kicks.append((t + 0.35, 0.05))
        if tag == "ON":
            self.sag_keys += [(t + 0.12, self.sag_keys[-1][1]), (t + 0.42, -26.0), (t + 0.7, 8.0), (t + 0.95, 0.0)]
            self.kicks.append((t + 0.45, 0.10))
        if tag == "swing":
            self.kicks.append((t + 0.01, 0.42))
        if tag == "giant":
            self.kicks.append((t + 0.01, 0.12))
        if tag == "giant2":
            self.kicks.append((t + 0.01, -0.10))

    def finish(self):
        self.sag = Keys(self.sag_keys)
        self.hits = [(c[0], c[3]) for c in self.C if SURF[c[3]][1]]
        self.soft = [(c[0], c[3]) for c in self.C if not SURF[c[3]][1]]

    def sag_at(self, t):
        if not hasattr(self, "sag"):
            return Keys(self.sag_keys)(t)
        return self.sag(t)

    def sag_pulse(self, t):
        return sum(16.0 * pulse(t, tp, 0.06, 0.16) for tp in getattr(self, "apex_taps", []))

    def swing(self, t):
        a = 0.0
        for (tk, amp) in self.kicks:
            if t > tk and amp:
                u = t - tk
                a += amp * math.exp(-u / 2.2) * math.sin(OMEGA * u)
        return a

    def lift(self, t):
        v = 0.0
        for tl in self.lifts:
            v += 34.0 * pulse(t, tl, 0.02, 0.35)
        return v

    def apex(self, t):
        return (APX, APY + self.sag_at(t))

    def lantern_bottom(self, t):
        ax, ay = self.apex(t)
        ay += FLAP * 1.1 + self.sag_pulse(t)  # attache sous la toile
        a = self.swing(t)
        L = LANT_L - self.lift(t)
        return ax + L * math.sin(a), ay + L * math.cos(a)

    # --- Bounce
    def ball(self, t):
        C = self.C
        if t <= C[0][0]:
            # chute depuis le haut jusqu'au premier contact
            y = C[0][2] - 0.5 * G * (C[0][0] - t) ** 2
            return C[0][1], y
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                T = b[0] - a[0]
                u = t - a[0]
                vy = (b[2] - a[2] - 0.5 * G * T * T) / T
                x = lerp(a[1], b[1], u / T)
                y = a[2] + vy * u + 0.5 * G * u * u
                # les mous se creusent : il s'enfonce un peu
                for c in (a, b):
                    if c[3] == "B":
                        y += 30.0 * pulse(t, c[0], 0.07, 0.09)
                    elif c[3] == "N":
                        y += 15.0 * pulse(t, c[0], 0.07, 0.09)
                return x, y
        # après le dernier contact : un dernier arc qui ne retombe pas avant la fin
        a = C[-1]
        u = t - a[0]
        vy = -math.sqrt(2 * G * 260)
        return a[1] - 30 * u, a[2] + vy * u + 0.5 * G * u * u


PLAN = Plan()
TG = PLAN.tags


# ------------------------------------------------------------------ géométrie de la tente
def _unit(dx, dy):
    L = math.hypot(dx, dy)
    return dx / L, dy / L


D_L = _unit(APX - BLX, APY - BASE)            # de la base gauche vers la pointe
D_R = _unit(APX - BRX, APY - BASE)
N_IN = {"L": (-D_L[1], D_L[0]), "R": (D_R[1], -D_R[0])}   # vers l'intérieur
N_OUT = {k: (-v[0], -v[1]) for k, v in N_IN.items()}


def _isect(p, d, q, e):
    """intersection des droites p + a d et q + b e"""
    den = d[0] * e[1] - d[1] * e[0]
    a = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return p[0] + a * d[0], p[1] + a * d[1]


def _at_y(p, d, y):
    a = (y - p[1]) / d[1]
    return p[0] + a * d[0], y


_OL0 = (BLX, BASE)
_OR0 = (BRX, BASE)
_IL0 = (BLX + FLAP * N_IN["L"][0], BASE + FLAP * N_IN["L"][1])
_IR0 = (BRX + FLAP * N_IN["R"][0], BASE + FLAP * N_IN["R"][1])
OUT_APEX0 = (APX, APY)
IN_APEX0 = _isect(_IL0, D_L, _IR0, D_R)
EDGE = {
    ("L", 0): (_OL0, _at_y(_OL0, D_L, SHY), OUT_APEX0),
    ("R", 0): (_OR0, _at_y(_OR0, D_R, SHY), OUT_APEX0),
    ("L", 1): (_at_y(_IL0, D_L, BASE), _at_y(_IL0, D_L, SHY), IN_APEX0),
    ("R", 1): (_at_y(_IR0, D_R, BASE), _at_y(_IR0, D_R, SHY), IN_APEX0),
}
NE = 36


class Tent:
    """Les pans de la tente : polylignes base -> épaule -> pointe, creusées par les dents (patte,
    tapes, oreille, Bounce dehors) et gonflées par l'ours à la fin."""

    def __init__(self, plan):
        self.plan = plan
        self.dents = []           # (côté, s0, largeur, fonction profondeur(t))
        self.bow = Keys([(0.0, 0.0)])

    def raw_edge(self, side, inner, t):
        b, sh, ap = EDGE[(side, inner)]
        sg = self.plan.sag_at(t) + self.plan.sag_pulse(t)
        ap = (ap[0], ap[1] + sg)
        l1 = math.hypot(sh[0] - b[0], sh[1] - b[1])
        l2 = math.hypot(ap[0] - sh[0], ap[1] - sh[1])
        pts, ss = [], []
        for k in range(NE + 1):
            s = k / NE
            d = s * (l1 + l2)
            if d <= l1:
                p = seg_pt(b, sh, d / l1)
            else:
                p = seg_pt(sh, ap, (d - l1) / l2)
            pts.append(p); ss.append(s)
        return pts, ss

    def disp(self, side, s, t):
        v = 0.0
        for (sd, s0, w, fn) in self.dents:
            if sd == side:
                dep = fn(t)
                if dep:
                    v += dep * math.exp(-((s - s0) / w) ** 2)
        bw = self.bow(t)
        if bw:
            v -= bw * math.sin(math.pi * clamp01(s / 0.92)) ** 1.5
        return v

    def edge(self, side, inner, t):
        pts, ss = self.raw_edge(side, inner, t)
        n = N_IN[side]
        out = []
        for p, s in zip(pts, ss):
            dv = self.disp(side, s, t)
            out.append((p[0] + n[0] * dv, p[1] + n[1] * dv))
        return out

    def nearest(self, side, c, t):
        """(s, distance) du point de la paroi intérieure (sans dent) le plus proche de c."""
        pts, ss = self.raw_edge(side, 1, t)
        best = (0.0, 1e9)
        for (p, q), (s0, s1) in zip(zip(pts, pts[1:]), zip(ss, ss[1:])):
            dx, dy = q[0] - p[0], q[1] - p[1]
            L2 = dx * dx + dy * dy
            u = clamp01(((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / L2)
            x, y = p[0] + u * dx, p[1] + u * dy
            d = math.hypot(c[0] - x, c[1] - y)
            if d < best[1]:
                best = (lerp(s0, s1, u), d)
        return best

    def point(self, side, inner, s, t):
        pts = self.edge(side, inner, t)
        f = s * NE
        k = min(NE - 1, int(f))
        return seg_pt(pts[k], pts[k + 1], f - k)


TENT = Tent(PLAN)


def contact(tag):
    for c in PLAN.C:
        if c[4] == tag:
            return c
    raise KeyError(tag)


def _build_dents():
    T = TENT
    # B. la patte sur le pan droit : trois contacts par-dessous
    ds = []
    for tag in ("dent1", "dent2", "dent3"):
        c = contact(tag)
        s0, d = T.nearest("R", (c[1], c[2]), c[0])
        ds.append((c[0], s0, d - R + 3.0))
    s0 = sum(d[1] for d in ds) / 3
    t0, t1 = TG["paw_down"], TG["paw_jerk"]
    kD = [(t0 + 0.02, 0.0), (t0 + 0.16, ds[0][2] * 0.85)] + [(tc, dep) for (tc, _s, dep) in ds] + \
         [(t1 - 0.02, ds[2][2] * 0.9), (t1 + 0.1, -10.0), (t1 + 0.3, 0.0)]
    T.dents.append(("R", s0, 0.07, Keys(kD)))
    # D1. les tapes : 1 à gauche, 2 à droite, (3 sur la pointe : affaissement), la 4e sur lui
    PLAN.tap_times = {"L1": TG["tap1"] + 0.18, "R1": TG["tap2"] + 0.33, "R2": TG["tap2"] + 0.56}
    for key, side, sp in (("L1", "L", 0.55), ("R1", "R", 0.48), ("R2", "R", 0.62)):
        tp = PLAN.tap_times[key]
        T.dents.append((side, sp, 0.06, (lambda tp: (lambda t: 46.0 * pulse(t, tp, 0.07, 0.2)))(tp)))
    c = contact("tap4")
    s4, d4 = T.nearest("L", (c[1], c[2]), c[0])
    dep4 = d4 - R + 4.0
    PLAN.tap_times["L4"] = c[0]
    kP = [(c[0] - 0.16, 0.0), (c[0], dep4), (c[0] + 0.25, dep4 * 0.8), (TG["tap4_down"] + 0.3, dep4 * 0.8),
          (TG["tap4_down"] + 0.5, 0.0)]
    T.dents.append(("L", s4, 0.07, Keys(kP)))
    PLAN.tap4 = (s4, dep4)
    # D2. l'oreille collée au pan droit
    c = contact("brush")
    sE, dE = T.nearest("R", (c[1], c[2]), c[0])
    dE = dE - R + 3.0
    rest = dE - 14.0
    ton, toff = TG["ear_on"] + 0.25, TG["ON"] + 0.12
    kE = [(ton - 0.25, 0.0), (ton + 0.2, rest)]
    for k in range(1, 10):
        tn = TG[f"n{k}"]
        if tn > toff:
            continue
        if k == 4:                       # pendant le bâillement, l'oreille n'est pas sur le toit
            continue
        kE += [(tn + 0.04, rest), (tn + 0.16, rest - 26.0), (tn + 0.5, rest + 4.0), (tn + 0.75, rest)]
    ty = TG["yawn"]
    kE += [(ty + 0.05, rest), (ty + 0.3, -8.0), (ty + 0.95, -8.0), (ty + 1.25, rest)]
    tb = c[0]
    kE += [(tb - 0.1, rest), (tb, dE), (tb + 0.12, rest - 10.0), (tb + 0.3, rest)]
    kE += [(toff - 0.05, rest), (toff + 0.12, -20.0), (toff + 0.35, 0.0)]
    kE.sort(key=lambda p: p[0])
    T.dents.append(("R", sE, 0.075, Keys(kE)))
    PLAN.ear = (sE, rest)
    # F. la tente gonflée, puis les coups de Bounce contre la toile
    te = TG["enter"]
    T.bow = Keys([(0.0, 0.0), (te + 0.25, 0.0), (te + 0.75, BOW_END + 14.0), (te + 1.1, BOW_END)])
    for c in PLAN.C:
        if c[3] == "T":
            T.dents.append(("R", KNOCK_S, 0.085, (lambda tc: (lambda t: CUP * pulse(t, tc, 0.07, 0.2)))(c[0])))


PLAN.apex_taps = [TG["tap3"] + 0.35 + 0.22 * k for k in range(3)]
_build_dents()


def print_plan():
    last = None
    for (t, x, y, s, tag) in PLAN.C:
        hard = SURF[s][1]
        g = ""
        if hard:
            if last is not None:
                d = t - last
                g = f"gap {d:.2f}" + (" !!" if d < 0.85 or d > 1.6 else "")
            last = t
        print(f"{t:6.2f} {s} x={x:5.0f} y={y:5.0f} {'H' if hard else 's'} {g:12s} {tag}")


# ------------------------------------------------------------------ validation géométrique
def validate(verbose=True):
    """Bounce ne traverse ni les parois, ni la lanterne, ni l'ours hors des contacts voulus."""
    bad = []
    soft_t = [c[0] for c in PLAN.C if c[3] in ("D", "P", "E", "L")]
    t_out = TG["corner"] + 0.15
    t = 0.0
    while t < PLAN.C[-1][0]:
        x, y = PLAN.ball(t)
        near = any(abs(t - tc) < 0.05 for tc in soft_t)
        if t < t_out and not near:
            for side in ("L", "R"):
                pts = TENT.edge(side, 1, t)
                d = min(_seg_dist((x, y), p, q) for p, q in zip(pts, pts[1:]))
                if d < R - 3:
                    bad.append((round(t, 2), "paroi " + side, round(d, 1)))
            lx, ly = PLAN.lantern_bottom(t)
            dx = max(abs(x - lx) - 34, 0)
            dy = max(ly - 92 - y, 0, y - ly)
            if math.hypot(dx, dy) < R - 2 and not near:
                bad.append((round(t, 2), "lanterne", round(math.hypot(dx, dy), 1)))
        t += 1 / 120
    # hauteur des arcs
    for a, b in zip(PLAN.C, PLAN.C[1:]):
        T_ = b[0] - a[0]
        vy = (b[2] - a[2] - 0.5 * G * T_ * T_) / T_
        if vy < 0:
            hgt = vy * vy / (2 * G)
            if hgt > 700:
                bad.append((round(a[0], 2), "arc", round(hgt)))
    if verbose:
        merged = {}
        for b in bad:
            merged.setdefault((b[1], int(b[0] * 2)), b)
        for b in sorted(merged.values()):
            print("  !", b)
        print("validation :", "OK" if not bad else f"{len(bad)} défauts")
    return bad


def _seg_dist(c, p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L2 = dx * dx + dy * dy or 1e-9
    u = clamp01(((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / L2)
    return math.hypot(c[0] - p[0] - u * dx, c[1] - p[1] - u * dy)


# ------------------------------------------------------------------ palette
SKY_TOP, SKY_LOW = (10, 14, 32), (30, 40, 74)
MOON = (236, 234, 216)
GROUND0, GROUND1 = (30, 27, 30), (16, 15, 18)
PINE = (24, 36, 42)
FAB, FAB_LIT = (128, 62, 34), (238, 146, 58)
FLAPC, FLAP_LIT = (110, 52, 30), (214, 120, 46)
WALL, WALL_LIT = (84, 104, 142), (255, 200, 120)
FLOORC, FLOOR_LIT = (38, 44, 60), (150, 104, 62)
COOL_B, COOL_L = (40, 104, 196), (226, 230, 238)
BAG_C, BAG_D = (46, 128, 76), (30, 92, 54)
BEAR, RIM = (7, 7, 11), (96, 108, 146)
SHADOW = (14, 18, 30)
WARM_SH = (46, 22, 14)


def P(x, y, S):
    return (x * S, y * S)


def ell_pts(x, y, rx, ry, a=0.0, n=28):
    ca, sa = math.cos(a), math.sin(a)
    return [(x + rx * math.cos(2 * math.pi * k / n) * ca - ry * math.sin(2 * math.pi * k / n) * sa,
             y + rx * math.cos(2 * math.pi * k / n) * sa + ry * math.sin(2 * math.pi * k / n) * ca) for k in range(n)]


def draw_prims(dr, prims, fill, S, ox=0.0, oy=0.0, xf=None):
    """Dessine des primitives monde (cercle, ellipse, capsule, polygone) ; xf = (k, cx, cy, dx, dy)."""
    def tp(x, y):
        if xf:
            k, cx, cy, dx, dy = xf
            x, y = cx + (x - cx) * k + dx, cy + (y - cy) * k + dy
        return x * S + ox, y * S + oy
    kk = xf[0] if xf else 1.0
    for pr in prims:
        kind = pr[0]
        if kind == "c":
            x, y = tp(pr[1], pr[2]); r = pr[3] * kk * S
            dr.ellipse([x - r, y - r, x + r, y + r], fill=fill)
        elif kind == "e":
            pts = ell_pts(*pr[1:6])
            dr.polygon([tp(*p) for p in pts], fill=fill)
        elif kind == "k":
            (x0, y0), (x1, y1) = tp(pr[1], pr[2]), tp(pr[3], pr[4])
            w = pr[5] * kk * S
            dr.line([(x0, y0), (x1, y1)], fill=fill, width=max(1, int(w)))
            r = w / 2
            dr.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=fill)
            dr.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fill)
        elif kind == "p":
            dr.polygon([tp(*p) for p in pr[1]], fill=fill)


def rot(p, a):
    ca, sa = math.cos(a), math.sin(a)
    return (p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca)


# ------------------------------------------------------------------ l'ours
def head_prims(hx, hy, r, hview=0.0, hp=0.0, jaw=0.0, ear=0.0, tilt=0.0):
    """Tête sans visage : un disque, deux oreilles rondes ; de profil (hview = ±1), un museau
    dans la direction hp (0 = horizontal, + = vers le bas), qui s'ouvre (jaw) pour bâiller."""
    pr = []
    side = abs(hview) > 0.05
    for sx in (-1, 1):
        if side:
            off = rot(((-0.38 + 0.5 * (sx > 0)) * r * (1 if hview > 0 else -1), -0.84 * r - 0.14 * r * ear), tilt)
        else:
            off = rot((0.66 * r * sx, -0.72 * r - 0.12 * r * ear), tilt)
        pr.append(("c", hx + off[0], hy + off[1], 0.36 * r + 0.05 * r * ear))
    pr.append(("c", hx, hy, r))
    if side:
        f = 1.0 if hview > 0 else -1.0
        L = 0.95 * r * abs(hview)
        a_up = hp - 0.32 * jaw
        a_lo = hp + 0.5 * jaw
        d_up = (math.cos(a_up) * f, math.sin(a_up))
        d_lo = (math.cos(a_lo) * f, math.sin(a_lo))
        ang_up = math.atan2(d_up[1], d_up[0])
        ang_lo = math.atan2(d_lo[1], d_lo[0])
        pr.append(("e", hx + d_up[0] * L, hy + d_up[1] * L - 0.12 * r * jaw, 0.78 * r * abs(hview), 0.48 * r, ang_up))
        if jaw > 0.02:
            pr.append(("e", hx + d_lo[0] * L * 0.85, hy + d_lo[1] * L * 0.85 + 0.2 * r * jaw, 0.66 * r * abs(hview), 0.3 * r, ang_lo))
        tip = (hx + d_up[0] * (L + 0.75 * r), hy + d_up[1] * (L + 0.75 * r))
    else:
        tip = (hx, hy + 0.3 * r)
    return pr, tip


def side_bear(x, gy, s, f=1, rear=0.0, lie=0.0, hp=0.15, ear=0.0, jaw=0.0, walk=0.0, lift=0.0,
              hdx=0.0, hdy=0.0, slump=0.0):
    """L'ours de profil, tourné vers f (+1 droite), pieds au sol en gy."""
    def W(lx, ly):
        return (x + f * s * lx, gy + s * ly)
    drop = 210.0 * lie + 16.0 * slump
    hip = (-215.0, -330.0 + drop)
    sh0 = (150.0, -350.0 + drop + 10 * slump)
    a = -1.15 * rear
    sh = (hip[0] + rot((sh0[0] - hip[0], sh0[1] - hip[1]), a)[0], hip[1] + rot((sh0[0] - hip[0], sh0[1] - hip[1]), a)[1])
    hump = (sh[0] + rot((-70.0, -95.0), a)[0], sh[1] + rot((-70.0, -95.0), a)[1])
    hc = (sh[0] + rot((180.0, -20.0 + 40 * lie), a)[0] + hdx, sh[1] + rot((180.0, -20.0 + 40 * lie), a)[1] + hdy)
    pr = []
    # pattes
    if lie < 0.5:
        k = 1.0 - 2 * lie
        ph = walk
        legs = [((sh[0] + 10, sh[1] + 80), (sh[0] + 40 + 45 * math.sin(ph), 0.0)),
                ((sh[0] - 45, sh[1] + 80), (sh[0] - 25 - 45 * math.sin(ph), 0.0)),
                ((hip[0] + 15, hip[1] + 80), (hip[0] + 5 - 45 * math.sin(ph), 0.0)),
                ((hip[0] - 50, hip[1] + 80), (hip[0] - 60 + 45 * math.sin(ph), 0.0))]
        if rear > 0:
            for i in (0, 1):
                a0, foot = legs[i]
                hang = (a0[0] + 70 + 20 * i, a0[1] + 170)
                legs[i] = (a0, (lerp(foot[0], hang[0], smooth(rear)), lerp(foot[1], hang[1], smooth(rear))))
        if lift > 0:
            a0, foot = legs[0]
            legs[0] = (a0, (foot[0] + 50 * lift, foot[1] - 150 * lift))
        for (p0, p1) in legs:
            p1 = (lerp(p0[0], p1[0], k), lerp(p0[1], p1[1], k)) if k < 1 else p1
            pr.append(("k", *W(*p0), *W(*p1), 100 * s))
    pr.append(("k", *W(*hip), *W(*sh), 330 * s))
    pr.append(("c", *W(*hip), 178 * s))
    pr.append(("c", *W(sh[0] + 15, sh[1] + 15), 165 * s))
    pr.append(("c", *W(*hump), 118 * s))
    pr.append(("k", *W(*sh), *W(*hc), 190 * s))
    hp_w = hp if f > 0 else hp
    hpr, tip = head_prims(*W(*hc), 108 * s, hview=float(f), hp=hp_w, jaw=jaw, ear=ear)
    pr += hpr
    return pr, {"head": W(*hc), "tip": tip, "r": 108 * s}


def front_bear(x, gy, s, head=None, tilt=0.0, hview=0.0, hp=0.0, jaw=0.0, ear=0.0,
               armL=None, armR=None, sit=0.0, ang=0.0, lean=0.0, legs=True):
    """L'ours de face (ou de dos), debout ; head = position monde de la tête (sinon au-dessus des
    épaules) ; armL/armR = où sont les pattes avant (monde)."""
    def W(lx, ly):
        q = rot((lx, ly), ang)
        return (x + s * q[0], gy + s * q[1])
    dn = 330.0 * sit
    hipY = -400.0 + dn
    pr = []
    if legs:
        for sx in (-1, 1):
            if sit > 0.3:
                pr.append(("k", *W(70 * sx, hipY), *W(150 * sx, -40.0), 150 * s))
            else:
                pr.append(("k", *W(70 * sx, hipY), *W(95 * sx, 0.0), 150 * s))
    body = W(lean * 0.5, hipY - 230)
    pr.append(("e", body[0], body[1], 238 * s, 300 * s, ang))
    shL, shR = W(-160 + lean, hipY - 455), W(160 + lean, hipY - 455)
    hd = head if head is not None else W(lean, hipY - 610)
    neck = W(lean, hipY - 480)
    pr.append(("k", neck[0], neck[1], hd[0], hd[1], 190 * s))
    for sh, tgt, sx in ((shL, armL, -1), (shR, armR, 1)):
        if tgt is None:
            tgt = W(-200 * sx * -1 + lean if False else (205 * sx + lean), hipY - 130)
        pr.append(("k", sh[0], sh[1], tgt[0], tgt[1], 116 * s))
        pr.append(("c", tgt[0], tgt[1], 66 * s))
    hpr, tip = head_prims(hd[0], hd[1], 126 * s, hview=hview, hp=hp, jaw=jaw, ear=ear, tilt=tilt + ang)
    pr += hpr
    return pr, {"head": hd, "tip": tip, "r": 126 * s, "shL": shL, "shR": shR}


def curl_prims(t, cx=505.0, cy=1236.0, breath=0.0):
    """L'ours roulé en boule dans la tente."""
    b = 1.0 + 0.025 * breath
    pr = [("e", cx - 20, cy, 300 * b, 150 * b, 0.0),
          ("c", cx - 240, cy - 40, 120 * b),
          ("c", cx + 230, cy - 10, 96)]
    hp_, _ = head_prims(cx + 250, cy - 30, 92, hview=0.0, ear=0.0, tilt=0.5)
    return pr + hp_


# ------------------------------------------------------------------ le sapin
PINE_BASE = (92.0, 1348.0)
PINE_LEN = 1180.0


def pine_pts(phi, n=24):
    """Le tronc, de la base vers la cime, plié d'un angle total phi vers la droite."""
    pts = [PINE_BASE]
    x, y = PINE_BASE
    for k in range(1, n + 1):
        u = k / n
        a = phi * u ** 1.1
        x += math.sin(a) * PINE_LEN / n
        y -= math.cos(a) * PINE_LEN / n
        pts.append((x, y))
    return pts


def pine_at(phi, u):
    pts = pine_pts(phi)
    f = u * (len(pts) - 1)
    k = min(len(pts) - 2, int(f))
    p = seg_pt(pts[k], pts[k + 1], f - k)
    a = phi * u ** 1.1
    return p, a


def draw_pine(dr, phi, S, col=PINE):
    _draw_pine(dr, phi, S, (52, 66, 90), -3, -3)
    _draw_pine(dr, phi, S, col, 0, 0)


def _draw_pine(dr, phi, S, col, ox, oy):
    pts = [(p[0] + ox, p[1] + oy) for p in pine_pts(phi)]
    dr.line([P(*p, S) for p in pts], fill=col, width=int(34 * S))
    for k, u in enumerate((0.28, 0.4, 0.52, 0.63, 0.73, 0.82, 0.9, 0.97)):
        (px, py), a = pine_at(phi, u)
        px += ox; py += oy
        w = lerp(330, 70, (u - 0.28) / 0.69)
        h = lerp(230, 110, (u - 0.28) / 0.69)
        tri = [(-w / 2, 40), (w / 2, 40), (0, -h)]
        tri = [rot(q, a) for q in tri]
        dr.polygon([P(px + q[0], py + q[1], S) for q in tri], fill=col)


# ------------------------------------------------------------------ la scène
def tri_ramp(t, t0, t1):
    return smooth((t - t0) / max(1e-6, t1 - t0))


class Choreo:
    """Les poses de l'ours, de la lanterne allumée, des pans de porte, de la buée et des Z."""

    def __init__(self):
        T = TG
        self.T = T
        self.t_payoff = T["last"] + 0.82
        self.t_on = T["ON"]
        self.t_close0, self.t_close1 = T["enter"] + 0.62, T["enter"] + 0.95
        self.t_end = PLAN.C[-1][0] + 0.75
        self.rings = [c for c in PLAN.C if SURF[c[3]][1]]
        # le sapin : angle de flexion
        tf, tg2, tb, tsw, tdr = T["flee"], T["giant2"], T["bend"], T["swing"], T["drop"]
        self.phi_k = Keys([(0, 0.0), (tf + 0.4, 0.0), (tf + 0.8, 0.1), (tg2 + 0.1, 0.12), (tg2 + 0.5, 0.42),
                           (tb + 0.5, 0.66), (tsw + 0.2, 0.74), (tsw + 0.6, 0.82), (tdr, 0.84)])
        self.t_drop = tdr
        # la buée : (t0, source) ; les sources sont lues sur la pose de l'ours à t0
        P_ = []
        for k in range(6):
            P_.append(0.05 + 0.32 * k)
        for tt in (3.4, 3.7, 4.4):
            P_.append(tt)
        for k in range(6):
            P_.append(5.45 + 0.16 * k)
        for k in range(4):
            P_.append(T["nose_close"] + 0.1 + 0.25 * k)
        for k in range(10):
            P_.append(T["hem"] + 0.35 + 0.42 * k)
        for k in range(4):
            P_.append(T["ear_on"] + 0.5 + 1.1 * k)
        for k in range(6):
            P_.append(T["sniff"] + 0.1 + 0.22 * k)
        self.puff_t = sorted(P_)
        self.puffs = None

    # --- la lumière de la lanterne
    def light(self, t):
        if t < self.t_on:
            return 0.0
        if t >= self.t_payoff:
            return 0.0
        return 1.0

    def closed(self, t):
        return tri_ramp(t, self.t_close0, self.t_close1)

    # --- l'ours
    def bear(self, t):
        """(prims, info, couche, ombre) ; ombre = (k, dx, dy, alpha) ou None."""
        T = self.T
        tA = T["rear"]
        # A. l'ombre qui marche puis s'approche
        if t < tA + 0.42:
            x = Keys([(0, 860.0), (T["first"], 700.0), (T["first"] + 1.0, 700.0), (4.0 + 0.3, 680.0),
                      (6.3, 650.0), (7.2, 670.0), (tA, 650.0)])(t)
            walking = t < T["first"]
            near = Keys([(0, 0.0), (T["first"], 0.1), (4.4, 0.55), (6.4, 0.95), (7.3, 0.7), (tA, 0.8)])(t)
            ear = 1.0 if t > T["first"] else 0.0
            hp = 0.75 if t < T["first"] else Keys([(T["first"], 0.75), (T["first"] + 0.25, 0.0), (2.9, -0.25),
                                                   (3.5, 0.2), (4.3, 0.1), (6.3, 0.35), (7.25, -0.1)])(t)
            hdx = Keys([(0, 0.0), (6.1, 0.0), (6.4, 40.0), (7.2, 40.0), (7.35, -30.0), (8.0, 0.0)])(t)
            rear = tri_ramp(t, tA + 0.02, tA + 0.4)
            pr, info = side_bear(x, 1330.0 - 60 * rear, 0.64, f=-1, rear=rear, hp=hp, ear=ear,
                                 walk=(t * 6.5 if walking else 0.0), hdx=hdx)
            k = lerp(1.42, 1.3, near) + 0.7 * rear
            alpha = lerp(205, 240, near)
            return pr, info, "behind", (k, -330.0 * rear, -130.0 + 150 * rear, alpha)
        # B. debout, la patte sur le toit
        tB1 = T["paw_jerk"]
        if t < tB1 + 0.85:
            gy = Keys([(tA + 0.42, 1720.0), (tA + 0.7, 1330.0), (tB1 + 0.3, 1330.0), (tB1 + 0.85, 1800.0)])(t)
            armR = None
            sD = TENT.dents[0][1]
            pd = TENT.point("R", 0, sD, t)
            pd = (pd[0] + N_OUT["R"][0] * 50, pd[1] + N_OUT["R"][1] * 50)
            if t >= T["paw_down"] - 0.3:
                u = tri_ramp(t, T["paw_down"] - 0.3, T["paw_down"] + 0.1)
                base_ = (690.0, 760.0)
                up = (720.0, 620.0)
                if t < tB1:
                    armR = (lerp(base_[0], pd[0], u), lerp(base_[1], pd[1], u))
                else:
                    v = tri_ramp(t, tB1, tB1 + 0.15)
                    armR = (lerp(pd[0], up[0], v), lerp(pd[1], up[1], v))
            hx = 520.0 + 30 * math.sin(2.0 * t) * (t < T["paw_down"])
            pr, info = front_bear(520.0, gy, 0.92, head=None if armR is None else (hx + 40, gy - 0.92 * 1000 + 30),
                                  armR=armR, tilt=0.25 if armR else 0.0, ear=1.0)
            return pr, info, "behind", (1.05, 0.0, 30.0, 235)
        # C. couché derrière, le museau sous la toile
        tC1 = T["rise"]
        if t < tC1 + 0.45:
            rear = tri_ramp(t, tC1 + 0.02, tC1 + 0.4)
            ear = 1.0
            pr, info = side_bear(170.0, 1330.0, 0.85, f=1, lie=1.0 - rear, rear=rear, hp=0.6, ear=ear,
                                 hdx=Keys([(0, 0.0), (T["hem"], 0.0), (T["hem"] + 0.5, 40.0)])(t))
            return pr, info, "behind", (1.08, 0.0, 20.0, lerp(200, 230, rear))
        # D1. debout derrière la pointe : pattes sur la pointe, tapes
        tE = T["ear_on"]
        tON = T["ON"]
        sg = PLAN.sag_at(t) + PLAN.sag_pulse(t)
        apex = (APX, APY + sg)
        if t < tON:
            gy = Keys([(tC1 + 0.45, 1760.0), (T["stand"] + 0.35, 1330.0)])(t)
            s = 0.92
            restL = (300.0, gy - 0.92 * 360)
            restR = (740.0, gy - 0.92 * 360)
            onL = (apex[0] - 40, apex[1] - 10)
            onR = (apex[0] + 40, apex[1] - 10)
            pa = T["paws_apex"]
            u = tri_ramp(t, pa - 0.3, pa)
            armL = (lerp(restL[0], onL[0], u), lerp(restL[1], onL[1], u))
            armR = (lerp(restR[0], onR[0], u), lerp(restR[1], onR[1], u))
            head = None
            tilt = 0.0
            hview, hp, jaw = 0.0, 0.0, 0.0
            hd0 = (520.0, gy - 0.92 * 1010)
            if t < pa:
                hd0 = (520.0 + 60 * math.sin(3.0 * (t - T["stand"])) * tri_ramp(t, T["stand"] + 0.4, T["stand"] + 0.7), hd0[1])
            head = hd0
            # les tapes
            taps = PLAN.tap_times
            for key, side, sp in (("L1", "L", 0.55), ("R1", "R", 0.48), ("R2", "R", 0.62)):
                tp = taps[key]
                if tp - 0.35 <= t <= tp + 0.35:
                    q = TENT.point(side, 0, sp, t)
                    q = (q[0] + N_OUT[side][0] * 55, q[1] + N_OUT[side][1] * 55)
                    up = (q[0] + N_OUT[side][0] * 120, q[1] - 90)
                    v = pulse(t, tp, 0.12, 0.2)
                    tgt = (lerp(up[0], q[0], v), lerp(up[1], q[1], v))
                    if side == "L":
                        armL = tgt
                    else:
                        armR = tgt
            for tp in PLAN.apex_taps:
                if tp - 0.15 <= t <= tp + 0.15:
                    v = pulse(t, tp, 0.08, 0.1)
                    armR = (apex[0] + 30, apex[1] - 70 + 60 * v)
            if PLAN.apex_taps[-1] + 0.15 < t < taps["L4"] - 0.3:      # la patte reste levée
                armR = (apex[0] + 120, apex[1] - 130)
            t4 = taps["L4"]
            if t4 - 0.3 <= t <= T["tap4_down"] + 0.55:
                s4, d4 = PLAN.tap4
                q = TENT.point("L", 0, s4, t)
                q = (q[0] + N_OUT["L"][0] * 55, q[1] + N_OUT["L"][1] * 55)
                up = (q[0] - 60, q[1] - 160)
                if t < t4:
                    v = tri_ramp(t, t4 - 0.3, t4)
                elif t < T["tap4_down"] + 0.3:
                    v = 1.0
                else:
                    v = 1.0 - tri_ramp(t, T["tap4_down"] + 0.3, T["tap4_down"] + 0.55)
                armL = (lerp(up[0], q[0], v), lerp(up[1], q[1], v))
                armR = (apex[0] + 120, apex[1] - 130) if t < t4 + 0.2 else onR
            if T["tap4_down"] + 0.55 < t < tE:
                armR = onR
                armL = (lerp(onL[0] - 160, onL[0], tri_ramp(t, T["paw_drop"], tE)), lerp(onL[1] + 60, onL[1], tri_ramp(t, T["paw_drop"], tE)))
            # D2. l'oreille collée au toit
            bx_ = 520.0
            if t >= tE - 0.2:
                vv = tri_ramp(t, tE - 0.2, tE + 0.25)
                gy = lerp(gy, 1700.0, vv)
                bx_ = lerp(520.0, 610.0, vv)
                hd0 = (bx_ + 0.92 * 40, gy - 0.92 * 1010)
                sE, rest = PLAN.ear
                q = TENT.point("R", 0, sE, t)
                hr = 126 * s
                on_roof = (q[0] + N_OUT["R"][0] * (hr * 0.78), q[1] + N_OUT["R"][1] * (hr * 0.78) - 10)
                v = tri_ramp(t, tE - 0.2, tE + 0.25)
                head = (lerp(hd0[0], on_roof[0], v), lerp(hd0[1], on_roof[1], v))
                tilt = 1.0 * v
                armL = onL
                armR = (lerp(onR[0], bx_ + 0.92 * 245, v), lerp(onR[1], gy - 0.92 * 530, v))
                ty = T["yawn"]
                if ty - 0.05 <= t <= ty + 1.3:
                    w = tri_ramp(t, ty, ty + 0.3) * (1 - tri_ramp(t, ty + 1.0, ty + 1.3))
                    up = (600.0, 690.0)
                    head = (lerp(head[0], up[0], w), lerp(head[1], up[1], w))
                    tilt = lerp(tilt, -0.15, w)
                    hview = -1.0 * w
                    hp = -1.0
                    jaw = math.sin(math.pi * clamp01((t - ty - 0.3) / 0.75)) if t > ty + 0.3 else 0.0
                for k in range(1, 10):
                    tn = T[f"n{k}"]
                    if k != 4 and tn <= t <= tn + 0.6:
                        jolt = pulse(t, tn + 0.15, 0.1, 0.4)
                        head = (head[0] + N_OUT["R"][0] * 30 * jolt, head[1] + N_OUT["R"][1] * 30 * jolt)
            ear = 1.0 if t < tE else 0.6 + 0.4 * pulse(t, T["brush"] + 0.1, 0.05, 0.3)
            pr, info = front_bear(bx_, gy, s, head=head, tilt=tilt, hview=hview, hp=hp,
                                  jaw=jaw, ear=ear, armL=armL, armR=armR, lean=40.0 * (t >= tE))
            return pr, info, "behind", (1.04, 0.0, 30.0, 238)
        # E. la lumière : il recule, tombe, file au sapin
        tg = T["giant"]
        tf = T["flee"]
        if t < tf:
            jump = pulse(t, tON + 0.12, 0.1, 0.4)
            gy = 1330.0 - 60 * jump
            gy = Keys([(tON, 1330.0), (tg, 1330.0), (tg + 0.18, 1290.0), (tg + 0.5, 1400.0), (tg + 0.9, 1820.0)])(t) - 60 * jump
            sit = tri_ramp(t, tg + 0.15, tg + 0.45)
            lean = Keys([(tON, 0.0), (tON + 1.0, 0.0), (T["ON"] + 1.4, -40.0), (40.8, 30.0), (tg, 30.0), (tg + 0.2, -60.0)])(t)
            armL = (330.0, gy - 0.92 * (420 if t < tg else 820))
            armR = (720.0, gy - 0.92 * (420 if t < tg else 820))
            head = (520.0 + lean, gy - 0.92 * 1010 + 20 * (lean > 0) + 330 * 0.92 * sit)
            pr, info = front_bear(520.0, gy, 0.92, head=head, armL=armL, armR=armR, sit=sit, lean=lean, ear=1.0)
            return pr, info, "behind", None
        # le sapin
        td = self.t_drop
        if t < td + 0.6:
            phi = self.phi_k(t)
            u = Keys([(tf, 0.1), (tf + 0.6, 0.34), (T["giant2"], 0.34), (T["giant2"] + 0.4, 0.46), (td, 0.46)])(t)
            (px, py), a = pine_at(phi, u)
            trem = 5.0 * math.sin(t * 47.0) if t < T["look"] else 0.0
            if t < td:
                s = 0.62
                ang = a
                # accroché au tronc : pattes autour du tronc, tête au-dessus
                arms = []
                for sx in (-1, 1):
                    (qx, qy), _a = pine_at(phi, min(1.0, u + 0.2))
                    arms.append((qx + sx * 70 * s * math.cos(a), qy + sx * 70 * s * math.sin(a)))
                look = tri_ramp(t, T["look"], T["look"] + 0.4)
                pr, info = front_bear(px + trem, py, s, ang=ang, armL=arms[0], armR=arms[1],
                                      hview=look, hp=0.4, ear=1.0)
                return pr, info, "front" if phi > 0.3 else "behind", None
            # il lâche : chute devant la tente, jusqu'au premier plan
            v = clamp01((t - td) / 0.5)
            (px0, py0), a0 = pine_at(self.phi_k(td), u)
            x = lerp(px0, 250.0, v)
            gy = lerp(py0, 1640.0, v * v)
            s = lerp(0.62, 1.0, v)
            pr, info = front_bear(x, gy, s, ang=lerp(a0, 0.0, v), armL=(x - 260 * s, gy - 820 * s), armR=(x + 260 * s, gy - 820 * s), ear=1.0)
            return pr, info, "front", None
        # F. au premier plan, de profil
        te = T["enter"]
        if t < te + 0.55:
            x = Keys([(td + 0.6, -30.0), (T["approach"], -30.0), (T["freeze"], 140.0), (T["sniff"], 140.0),
                      (T["sniff"] + 0.3, 170.0), (te, 170.0), (te + 0.55, 215.0)])(t)
            gy = Keys([(td + 0.6, 1640.0), (te, 1640.0), (te + 0.55, 1430.0)])(t)
            s = Keys([(td + 0.6, 1.0), (te, 1.0), (te + 0.55, 0.74)])(t)
            walking = (T["approach"] <= t < T["freeze"]) or t >= te
            lift = pulse(t, T["freeze"] + 0.25, 0.25, 0.7) if t < T["sniff"] + 0.2 else 0.0
            hp = Keys([(td + 0.6, 0.1), (T["sniff"], 0.15), (T["sniff"] + 0.35, 0.95), (T["yawn2"], 0.95),
                       (T["yawn2"] + 0.3, -1.05), (T["yawn2"] + 1.0, -1.05), (te, 0.2)])(t)
            hdy = Keys([(td + 0.6, -40.0), (T["sniff"], -40.0), (T["sniff"] + 0.35, -60.0), (T["yawn2"], -60.0),
                        (T["yawn2"] + 0.3, -90.0), (te, -40.0)])(t)
            jaw = math.sin(math.pi * clamp01((t - T["yawn2"] - 0.25) / 0.75)) if t > T["yawn2"] + 0.25 else 0.0
            slump = tri_ramp(t, T["sniff2"] + 0.3, T["sniff2"] + 0.7)
            rr = Keys([(td + 0.6, 0.0), (T["freeze"], 0.0), (T["freeze"] + 0.3, 0.22), (T["sniff"], 0.22),
                       (T["sniff"] + 0.35, 0.42), (T["yawn2"] + 1.0, 0.42), (te, 0.0)])(t)
            pr, info = side_bear(x, gy, s, f=1, rear=rr, hp=hp, ear=1.0 - 0.6 * slump, jaw=jaw, walk=(t * 6.0 if walking else 0.0),
                                 lift=lift, hdy=hdy, slump=slump)
            return pr, info, "front", None
        # dans la tente, roulé en boule
        return curl_prims(t, breath=math.sin(t * 2.4)), {"tip": (760, 1230), "head": (755, 1206), "r": 92}, "inside", None

    # --- le museau sous la toile (phase C)
    def snout(self, t):
        """La tête qui passe sous la toile du fond : (sortie 0..1, x, sens du museau -1..1, aplati)."""
        T = self.T
        h0, h1 = T["hem"] + 0.05, T["snout_out"]
        if t < h0 or t > h1 + 0.25:
            return None
        ext = tri_ramp(t, h0, h0 + 0.55) * (1 - tri_ramp(t, h1 + 0.02, h1 + 0.18))
        cx = Keys([(h0, 505.0), (T["snout_left"] + 0.05, 505.0), (T["snout_left"] + 0.35, 470.0),
                   (T["snout_right"] + 0.05, 470.0), (T["snout_right"] + 0.3, 540.0), (T["boop1"] - 0.2, 522.0), (h1, 522.0)])(t)
        dr_ = Keys([(h0, 0.0), (h0 + 0.6, 0.0), (T["snout_left"] + 0.05, 0.0), (T["snout_left"] + 0.3, -1.0),
                    (T["snout_right"] + 0.05, -1.0), (T["snout_right"] + 0.25, 1.0),
                    (T["snout_left2"] + 0.1, 1.0), (T["snout_left2"] + 0.4, -1.0), (h1, -1.0)])(t)
        flat = max(pulse(t, T["boop1"], 0.07, 0.09), pulse(t, T["boop2"], 0.07, 0.09))
        trem = 2.5 * math.sin(t * 60) if T["boop1"] < t < h1 else 0.0
        return ext, cx + trem, dr_, flat

    def snout_geom(self, t):
        st = self.snout(t)
        if st is None:
            return None
        ext, cx, d, flat = st
        hy = HEM + 30.0 - 10 * ext
        L = 100.0 * abs(d) * ext
        tip = (cx + math.copysign(L + 50, d) if abs(d) > 0.05 else cx, hy + 26 + 8 * flat)
        return {"c": (cx, hy), "ext": ext, "dir": d, "flat": flat, "tip": tip}

    # --- la buée
    def build_puffs(self):
        out = []
        for t0 in self.puff_t:
            sg = self.snout_geom(t0)
            if sg is not None and sg["ext"] > 0.5:
                src = sg["tip"]; v = (0.0, -40.0); layer = "inside"
            else:
                pr, info, layer, _ = self.bear(t0)
                src = info["tip"]; v = (0.0, -70.0)
                if self.T["ear_on"] < t0 < self.T["ON"]:
                    v = (-60.0, 50.0)          # glisse le long du toit
                if self.T["sniff"] < t0 < self.T["yawn2"]:
                    v = (20.0, 60.0)           # tombe sur Bounce
            out.append((t0, src, v, layer))
        self.puffs = out

    def puffs_at(self, t):
        if self.puffs is None:
            self.build_puffs()
        res = []
        for (t0, src, v, layer) in self.puffs:
            a = t - t0
            if 0 <= a <= 1.0:
                res.append((src[0] + v[0] * a, src[1] + v[1] * a, 16 + 46 * a, (1 - a) ** 1.3, layer))
        return res


CH = Choreo()


# ------------------------------------------------------------------ rendu
def make_background(S):
    img = Image.new("RGB", (W * S, H * S), SKY_TOP)
    dr = ImageDraw.Draw(img)
    for k in range(0, 1400, 8):
        c = mix(SKY_TOP, SKY_LOW, (k / 1400) ** 1.3)
        dr.rectangle([0, k * S, W * S, (k + 8) * S], fill=c)
    mx, my = 500, 500
    a = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:H * S, 0:W * S]
    d = np.hypot(xx / S - mx, yy / S - my)
    g = np.exp(-np.maximum(d - 80, 0) / 210.0)[..., None] * 0.75
    a = a * (1 - g) + np.array([86, 98, 138], np.float32) * g
    img = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    dr.ellipse([(mx - 82) * S, (my - 82) * S, (mx + 82) * S, (my + 82) * S], fill=MOON)
    for (cx, cy, rr) in ((470, 480, 14), (525, 525, 10), (488, 538, 7)):
        dr.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], fill=(214, 212, 196))
    # sapins lointains
    for (x, base, h, w) in ((1010, 1350, 620, 230), (1070, 1350, 820, 260), (930, 1355, 420, 170),
                            (-20, 1350, 520, 220), (230, 1352, 300, 140), (800, 1356, 300, 140)):
        for k in range(4):
            yy = base - h * k / 4
            ww = w * (1 - k / 5)
            dr.polygon([P(x - ww / 2, yy, S), P(x + ww / 2, yy, S), P(x, yy - h / 2.2, S)], fill=(14, 20, 30))
    # le sol
    for k in range(1340, H, 6):
        c = mix(GROUND0, GROUND1, (k - 1340) / (H - 1340))
        dr.rectangle([0, k * S, W * S, (k + 6) * S], fill=c)
    rng = np.random.default_rng(3)
    for _ in range(26):
        x = rng.uniform(0, W); y = rng.uniform(1420, 1680)
        if 80 < x < 980 and y < 1400:
            continue
        h = rng.uniform(16, 34)
        for d in (-8, 0, 8):
            dr.line([P(x, y, S), P(x + d, y - h, S)], fill=(40, 46, 40), width=int(3 * S))
    return img


def masked(img, S, box, clip_pts, paint, color):
    """Peint `paint(draw, ox, oy)` (valeurs 0..255) dans `color`, seulement dans clip_pts."""
    x0, y0, x1, y1 = [int(v * S) for v in box]
    w, h = x1 - x0, y1 - y0
    m1 = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m1).polygon([(x * S - x0, y * S - y0) for x, y in clip_pts], fill=255)
    m2 = Image.new("L", (w, h), 0)
    paint(ImageDraw.Draw(m2), -x0, -y0)
    img.paste(color, (x0, y0, x1, y1), ImageChops.multiply(m1, m2))


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hi = 0
        self.hits = [(c[0], c[3]) for c in PLAN.C if SURF[c[3]][1]]
        self.bg = None

    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", "dur"))
            self.hi += 1
        if not self.payoff and self.t >= CH.t_payoff:
            self.payoff = True
            evs.append(("payoff", "evicted"))
        if self.t >= CH.t_end:
            self.done = True
        return evs

    def hero_mood(self):
        return "lose"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # --------------------------------------------------------------
    def draw(self, dr, snap, t, S):
        img = dr._image
        if self.bg is None or self.bg.size != img.size:
            self.bg = make_background(S)
        img.paste(self.bg)
        dra = ImageDraw.Draw(img, "RGBA")
        lit = CH.light(t)
        closed = CH.closed(t)
        prims, info, layer, shadow = CH.bear(t)
        bx, by = PLAN.ball(t)
        inside = t < TG["corner"] + 0.3
        # le grand sapin (derrière la tente)
        phi = CH.phi_k(t) if t < CH.t_drop else CH.phi_k(CH.t_drop) * math.exp(-(t - CH.t_drop) * 3.0) * math.cos((t - CH.t_drop) * 11.0)
        draw_pine(dr, phi, S)
        # l'ours derrière la tente
        if layer == "behind":
            clipr = [(0, 0), (W, 0), (W, 1352), (0, 1352)]
            masked(img, S, (0, 0, W, 1352), clipr, lambda d, ox, oy: draw_prims(d, prims, 255, S, ox - 4 * S, oy - 5 * S), RIM)
            masked(img, S, (0, 0, W, 1352), clipr, lambda d, ox, oy: draw_prims(d, prims, 255, S, ox, oy), BEAR)
        # buée derrière
        for (px, py, r, a, lay) in CH.puffs_at(t):
            if lay == "behind":
                dra.ellipse([(px - r) * S, (py - r) * S, (px + r) * S, (py + r) * S], fill=(200, 210, 232, int(110 * a)))
        # la tente
        oL, oR = TENT.edge("L", 0, t), TENT.edge("R", 0, t)
        iL, iR = TENT.edge("L", 1, t), TENT.edge("R", 1, t)
        outer = oL + oR[::-1]
        inner = iL + iR[::-1]
        fab = mix(FAB, FAB_LIT, lit)
        dr.polygon([P(*p, S) for p in outer], fill=fab)
        # piquets et cordes
        for (a, b) in (((BLX + 30, BASE - 200), (BLX - 30, BASE + 40)), ((BRX - 30, BASE - 200), (BRX + 5, BASE + 40))):
            dr.line([P(*a, S), P(*b, S)], fill=(150, 150, 150) if lit < 0.5 else (200, 170, 130), width=max(1, int(2 * S)))
        # intérieur : toile du fond + tapis
        wall = mix(WALL, WALL_LIT, lit)
        dr.polygon([P(*p, S) for p in inner], fill=wall)
        box = (0, 380, W, 1400)
        # ombre de l'ours (lune) sur la toile
        if shadow is not None and lit < 0.5:
            k, sdx, sdy, alpha = shadow
            xf = (k, 500.0, 1330.0, sdx, sdy)
            masked(img, S, box, inner, lambda d, ox, oy: draw_prims(d, prims, int(alpha), S, ox, oy, xf), SHADOW)
        # le bas de la toile soulevé par le museau
        sg = CH.snout_geom(t)
        fl = mix(FLOORC, FLOOR_LIT, lit)
        floor = [(line_x_at(iL[0], iL[1], HEM), HEM), (line_x_at(iR[0], iR[1], HEM), HEM), iR[0], iL[0]]
        dr.polygon([P(*p, S) for p in floor], fill=fl)
        if sg is not None:
            e = sg["ext"]
            gx = sg["c"][0]
            dr.chord([(gx - 120 * e) * S, (HEM - 90 * e) * S, (gx + 120 * e) * S, (HEM + 90 * e) * S], 180, 360, fill=(6, 8, 14))
        # l'ombre de Bounce (lanterne)
        lx, ly = PLAN.lantern_bottom(t)
        lc = (lx, ly - 46)
        if lit > 0.5 and inside:
            d = math.hypot(bx - lc[0], by - lc[1])
            kk = 1.3 + 5.2 * math.exp(-d / 190.0)
            sx, sy = lc[0] + (bx - lc[0]) * kk, lc[1] + (by - lc[1]) * kk * 0.85 - 20
            rr = R * kk
            masked(img, S, box, inner[:], lambda dd, ox, oy: dd.ellipse([sx * S + ox - rr * S, sy * S + oy - rr * S,
                                                                          sx * S + ox + rr * S, sy * S + oy + rr * S], fill=235), WARM_SH)
        # la glacière
        c0, c1, c2, c3 = COOLER
        dim_k = 0.62 + 0.38 * lit
        dr.rectangle([c0 * S, (c1 + 26) * S, c2 * S, c3 * S], fill=dim(COOL_B, dim_k))
        dr.rectangle([(c0 - 6) * S, c1 * S, (c2 + 6) * S, (c1 + 30) * S], fill=dim(COOL_L, dim_k))
        dr.rectangle([(c0 + 60) * S, (c1 + 70) * S, (c2 - 60) * S, (c1 + 84) * S], fill=dim((24, 70, 140), dim_k))
        cpress = sum(5.0 * pulse(t, c[0], 0.03, 0.12) for c in PLAN.C if c[3] == "C")
        # le sac de couchage (se creuse sous Bounce)
        self.draw_bag(dr, t, S, lit, bx)
        # le museau (posé sur le tapis, devant la glacière et le sac)
        if sg is not None:
            self.draw_snout(dr, sg, S)
        # l'ours roulé dans la tente
        if layer == "inside":
            ins = [p for p in inner]
            masked(img, S, box, ins, lambda d, ox, oy: draw_prims(d, prims, 255, S, ox, oy), BEAR)
        # Bounce dedans
        if inside:
            base.ball(dr, bx * S, by * S, R * S)
        # la lanterne
        self.draw_lantern(dr, dra, t, S, lit)
        # les pans de porte
        self.draw_flaps(dr, img, t, S, oL, oR, iL, iR, lit, closed, layer, prims, box)
        # lumière qui sort de la porte
        if lit > 0.5 and closed < 1.0:
            a = 1 - closed
            for k in range(14):
                u = k / 14
                yb = 1386 + 300 * (1 - u)
                xs = 330 * (1 - u) + 90
                dra.polygon([P(500 - 360 + 40 * u, 1386, S), P(500 + 360 - 40 * u, 1386, S), P(500 + 360 + xs * 0.4, yb, S), P(500 - 360 - xs * 0.4, yb, S)],
                            fill=(255, 176, 90, int(5 * a)))
        if lit > 0.5 and closed > 0:
            dra.polygon([P(*p, S) for p in outer], fill=(255, 190, 110, int(40 * closed)))
        # l'ours devant
        if layer == "front":
            draw_prims(dr, prims, RIM, S, ox=-4 * S, oy=-5 * S)
            draw_prims(dr, prims, BEAR, S)
        # Bounce dehors
        if not inside:
            base.ball(dr, bx * S, by * S, R * S)
        # buée devant
        for (px, py, r, a, lay) in CH.puffs_at(t):
            if lay != "behind":
                dra.ellipse([(px - r) * S, (py - r) * S, (px + r) * S, (py + r) * S], fill=(205, 214, 236, int(120 * a)))
        # les anneaux
        for c in CH.rings:
            age = t - c[0]
            if 0 <= age < 1.1:
                r = 0.9 * R + 1150 * age
                a = (1 - age / 1.1) ** 1.2
                cx, cy = c[1], c[2] + (R * 0.9 if c[3] != "L" else -R * 0.9)
                w = max(2, int((12 - 8 * age) * S))
                dra.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=(255, 255, 255, int(220 * a)), width=w)
        # les Z
        zf = font(int(90 * S))
        for i, c in enumerate([c for c in PLAN.C if c[3] == "T"]):
            age = t - c[0] - 0.12
            if age >= 0:
                n = 1 if i < 2 else 2
                ap = TENT.point("R", 0, 1.0, t)
                for j in range(n):
                    a = max(0.0, 1 - age / 2.2)
                    zx = ap[0] - 130 - 85 * i - 70 * j - 40 * age + 12 * math.sin(age * 3)
                    zy = ap[1] + 70 - 30 * i - 95 * age - 55 * j
                    size = int((96 + 30 * i + 26 * j) * S)
                    dra.text((zx * S, zy * S), "Z", font=font(size), fill=(255, 255, 255, int(255 * a)), anchor="mm")

    def draw_snout(self, dr, sg, S):
        """La tête sous la toile soulevée : un dôme noir, et le museau de profil qui renifle le tapis."""
        cx, hy = sg["c"]
        e, d, fl = sg["ext"], sg["dir"], sg["flat"]
        if e < 0.03:
            return
        r = 76.0 * e
        sy = hy + 28 * e + 8 * fl                    # le museau, au ras du tapis
        L = (60 + 70 * abs(d)) * e
        sx = cx + d * L * 0.7
        rx, ry = (52 + 40 * abs(d)) * e, (34 - 9 * fl) * e
        ryh = r * (1 - 0.22 * fl)
        hyc = hy + r - ryh
        for col, ox, oy in ((RIM, -4, -5), (BEAR, 0, 0)):
            dr.ellipse([(cx - r * (1 + 0.1 * fl) + ox) * S, (hyc - ryh + oy) * S, (cx + r * (1 + 0.1 * fl) + ox) * S, (hyc + ryh + oy) * S], fill=col)
            dr.ellipse([(sx - rx + ox) * S, (sy - ry + oy) * S, (sx + rx + ox) * S, (sy + ry + oy) * S], fill=col)
        nx = sx + d * (rx - 14 * e)
        dr.ellipse([(nx - 18 * e) * S, (sy - 16 * e) * S, (nx + 18 * e) * S, (sy + 6 * e) * S], fill=(48, 48, 62))
        dr.ellipse([(nx - 9 * e) * S, (sy - 14 * e) * S, (nx + 1 * e) * S, (sy - 8 * e) * S], fill=(130, 130, 150))

    def draw_bag(self, dr, t, S, lit, bx):
        x0, x1 = BAG
        dip = 0.0
        for c in PLAN.C:
            if c[3] == "B":
                dip = max(dip, pulse(t, c[0], 0.07, 0.12))
        if CH.bear(t)[2] == "inside":
            dip = 0.0
        dk = 0.6 + 0.4 * lit
        top = 1300.0
        pts = []
        for k in range(25):
            x = lerp(x0, x1, k / 24)
            y = top - 26 * math.sin(math.pi * k / 24) ** 0.6
            y += 34 * dip * math.exp(-((x - bx) / 70.0) ** 2)
            pts.append((x, y))
        pts += [(x1, 1384.0), (x0, 1384.0)]
        dr.polygon([P(x0 - 10, 1352, S), P(x1 + 6, 1352, S), P(x1 + 6, 1386, S), P(x0 - 10, 1386, S)], fill=dim((70, 76, 96), dk))
        dr.polygon([P(*p, S) for p in pts], fill=dim(BAG_C, dk))
        dr.line([P(x0 + 20, 1336, S), P(x1 - 30, 1336, S)], fill=dim(BAG_D, dk), width=int(5 * S))
        dr.ellipse([(x1 - 110) * S, 1290 * S, (x1 - 10) * S, 1340 * S], fill=dim((60, 150, 96), dk))

    def draw_lantern(self, dr, dra, t, S, lit):
        ax, ay = PLAN.apex(t)
        ay += FLAP * 1.1 + PLAN.sag_pulse(t)
        lx, ly = PLAN.lantern_bottom(t)
        ang = PLAN.swing(t)
        dr.line([P(ax, ay, S), P(lx - math.sin(ang) * 100, ly - math.cos(ang) * 100, S)], fill=(160, 150, 140), width=int(3 * S))

        def Q(u, v):
            q = rot((u, v), -ang)
            return P(lx + q[0], ly + q[1], S)
        metal = (150, 150, 160)
        glass = (255, 236, 170) if lit > 0.5 else (60, 70, 86)
        if lit > 0.5:
            for k in range(6, 0, -1):
                r = 30 + 26 * k
                dra.ellipse([(lx - r) * S, (ly - 46 - r) * S, (lx + r) * S, (ly - 46 + r) * S], fill=(255, 220, 140, 22))
        dr.polygon([Q(-34, -10), Q(34, -10), Q(34, 0), Q(-34, 0)], fill=metal)
        dr.polygon([Q(-26, -80), Q(26, -80), Q(30, -10), Q(-30, -10)], fill=glass)
        dr.polygon([Q(-30, -92), Q(30, -92), Q(18, -104), Q(-18, -104)], fill=metal)
        dr.line([Q(-20, -104), Q(0, -122), Q(20, -104)], fill=metal, width=int(4 * S))
        for u in (-12, 12):
            dr.line([Q(u, -80), Q(u, -10)], fill=metal, width=int(3 * S))

    def draw_flaps(self, dr, img, t, S, oL, oR, iL, iR, lit, closed, layer, prims, box):
        col = mix(FLAPC, FLAP_LIT, lit)
        ap = oL[-1]
        for side, o, i in (("L", oL, iL), ("R", oR, iR)):
            bx_open = i[0][0] + (10 if side == "L" else -10)
            bx_c = lerp(bx_open, 500.0, closed)
            # le pan : du bord extérieur jusqu'à la ligne pointe -> (bx_c, base)
            n = len(o)
            inner_line = [seg_pt((bx_c, BASE + 4), (ap[0], ap[1] + 6), k / (n - 1)) for k in range(n)]
            if closed < 0.02:
                inner_line = i
            poly = o + inner_line[::-1]
            dr.polygon([P(*p, S) for p in poly], fill=col)
            if closed < 0.5:
                # le pan roulé et son attache
                q = seg_pt(o[8], i[8], 0.5)
                dr.ellipse([(q[0] - 18) * S, (q[1] - 18) * S, (q[0] + 18) * S, (q[1] + 18) * S], fill=dim(col, 0.7))
        if closed > 0.98:
            dr.line([P(500, BASE, S), P(ap[0], ap[1] + 10, S)], fill=dim(col, 0.6), width=int(4 * S))
            # l'ombre de l'ours roulé sur la toile de devant, tant que la lanterne brille
            if lit > 0.5:
                front = oL + oR[::-1]
                xf = (1.08, 505.0, 1236.0, 0.0, -10.0)
                pr = list(prims)
                tp0 = CH.t_payoff
                if t > tp0 - 0.6:
                    v = tri_ramp(t, tp0 - 0.6, tp0 - 0.15)
                    lxb, lyb = PLAN.lantern_bottom(t)
                    pr.append(("k", 760.0, 1180.0, lerp(760.0, lxb + 30, v), lerp(1180.0, lyb - 30, v), 60.0))
                    pr.append(("c", lerp(760.0, lxb + 30, v), lerp(1180.0, lyb - 30, v), 40.0))
                masked(img, S, box, front, lambda d, ox, oy: draw_prims(d, pr, 150, S, ox, oy, xf), (120, 52, 20))


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 3.0}


def stills(cfg_path, times, out_dir):
    cfg = base.load_config(cfg_path, DEFAULTS)
    S = 1
    sim = Sim(cfg, None)
    os.makedirs(out_dir, exist_ok=True)
    for t in times:
        base.HERO["expr"] = "calm"
        base.HERO["pos"] = None
        img = Image.new("RGB", (W * S, H * S), (8, 8, 12))
        dr = ImageDraw.Draw(img)
        sim.draw(dr, t, t, S)
        img.save(os.path.join(out_dir, f"s_{t:05.2f}.png"))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        print_plan()
        validate()
        sys.exit(0)
    if "--still" in sys.argv:
        ts = [float(v) for v in sys.argv[sys.argv.index("--still") + 1].split(",")]
        stills(sys.argv[1], ts, sys.argv[sys.argv.index("--still") + 2])
        sys.exit(0)
    sys.exit(base.run(sys.modules[__name__]))
