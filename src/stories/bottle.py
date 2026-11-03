"""
Prototype « la bouteille » : Bounce est dans une bouteille de verre couchée sur une table,
et il pourrait en sortir en roulant. Il ne s'arrête pas de rebondir, et chaque choc le
fait gonfler d'un cran : il devient trop gros pour le goulot, s'y coince, pousse la
bouteille au bord de la table, la fait basculer, finit avec la bouteille plantée sur la
tête, couvre toute la table, tombe, s'en libère enfin... dans une bouteille géante.

Aucune narration : les deux seules voix sont l'accroche et Bounce. Toute la chorégraphie
est calculée d'avance sur une seule horloge (le plan) : trajectoires balistiques entre
des contacts choisis, une seule gravité, dans le repère de la bouteille tant qu'il est
dedans, dans celui de la table ensuite. La caméra le suit et recule à mesure qu'il gonfle.

    python3 src/stories/bottle.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
from chapters import StorySim
from listkit import Chapter, mix
import audio_kit as ak

W, H = 1080, 1920
FPS = 60
G = 1000.0                                # wu/s², une seule gravité pour tout
A0 = math.radians(25.0)                   # pente des deux bouteilles
SA, CA = math.sin(A0), math.cos(A0)
END = 61.45

# ------------------------------------------------------------------ le mot de Bounce
# piper ne rend pas « Bounce » deux fois à la même longueur : on garde, une fois par
# processus, un tirage court (même voix, même mot), pour que le placement des mots soit
# le même à la simulation, au contrôle et au rendu.
_orig_hero_word = base.hero_word
_hero_memo = {}


def steady_hero_word(text, cfg):
    key = (text, cfg["hero_voice_pitch"], cfg["hero_voice_length"])
    if key not in _hero_memo:
        best = None
        for _ in range(10):
            v = _orig_hero_word(text, cfg)
            if v is None:
                break
            if best is None or len(v) < len(best):
                best = v
            if len(v) / ak.SR <= 0.70:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ la bouteille
# profil intérieur (demi-largeurs) le long de l'axe u : 0 = fond, UL = embouchure ;
# v > 0 du côté de la paroi basse. Épaule longue : de l'intérieur, le sol descend
# jusqu'à l'embouchure sans jamais remonter.
HB, HN, HL = 126.0, 54.0, 45.0
GL = 8.0
LIPO = HN + GL + 7.0
FIL = 40.0
LB, LS = 440.0, 250.0
UN = LB + LS
UL0, UL = 842.0, 860.0


def h_in(u):
    if u < FIL:
        return HB - FIL + math.sqrt(max(0.0, FIL ** 2 - (FIL - u) ** 2))
    if u <= LB:
        return HB
    if u <= UN:
        k = (u - LB) / LS
        return HN + (HB - HN) * 0.5 * (1 + math.cos(math.pi * k))
    if u <= UL0:
        return HN
    return HL


def h_out(u):
    if u < FIL:
        F = FIL + GL
        return HB + GL - F + math.sqrt(max(0.0, F ** 2 - (FIL - u) ** 2))
    if u >= UL0 - 4:
        return LIPO
    return h_in(u) + GL


def dh(u):
    return h_in(u + 0.5) - h_in(u - 0.5)


U_IN = np.concatenate([np.linspace(0.0, FIL, 12), np.linspace(FIL + 4, UL, 180)])
U_OUT = np.concatenate([np.linspace(-GL, FIL, 14), np.linspace(FIL + 4, UL, 180)])


def profile_polys():
    hi = np.array([h_in(u) for u in U_IN])
    ho = np.array([h_out(u) for u in U_OUT])
    ho[0] = 0.0
    outer = [(u, -h) for u, h in zip(U_OUT, ho)] + [(u, h) for u, h in zip(U_OUT[::-1], ho[::-1])]
    inner = [(u, -h) for u, h in zip(U_IN, hi)] + [(UL + 3, -HL), (UL + 3, HL)] + [(u, h) for u, h in zip(U_IN[::-1], hi[::-1])]
    top = [(u, -h) for u, h in zip(U_OUT, ho)] + [(u, -h) for u, h in zip(U_IN[::-1], hi[::-1])] + [(0.0, 0.0)]
    bot = [(u, h) for u, h in zip(U_OUT, ho)] + [(u, h) for u, h in zip(U_IN[::-1], hi[::-1])] + [(0.0, 0.0)]
    return outer, inner, top, bot


POLYS = profile_polys()
# le long reflet blanc courbe, sur le dessus du corps
HILITE = [(u, -HB * (0.58 + 0.13 * math.sin(math.pi * (u - 45) / 370))) for u in np.linspace(45, 415, 26)]
INNER_PTS = np.array([(u, -h_in(u)) for u in np.linspace(0, UL0, 500)] + [(u, h_in(u)) for u in np.linspace(0, UL0, 500)]
                     + [(u, s * HL) for u in np.linspace(UL0, UL, 8) for s in (-1, 1)]
                     + [(0.0, v) for v in np.linspace(-HB + FIL, HB - FIL, 40)])


def clearance(u, v):
    """Distance du point (u, v), repère de la bouteille, à la paroi intérieure."""
    return float(np.hypot(INNER_PTS[:, 0] - u, INNER_PTS[:, 1] - v).min())


def to_world(pose, u, v, k=1.0):
    x, y, a = pose
    ca, sa = math.cos(a), math.sin(a)
    return (x + (u * ca - v * sa) * k, y + (u * sa + v * ca) * k)


def lin(u):
    return max(0.0, min(1.0, u))


def ease(u):
    u = lin(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, k):
    return a + (b - a) * k


def keyed(keys, T):
    """Interpolation douce d'une suite (t, valeur)."""
    if T <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if T <= t1:
            return lerp(v0, v1, ease((T - t0) / max(1e-6, t1 - t0)))
    return keys[-1][1]


# ------------------------------------------------------------------ le décor
TABLE_X1 = 1500.0
TABLE_T = 40.0
LEG_W = 16.0
LEGS = (40.0, TABLE_X1 - 40.0 - LEG_W)
KG = 14.0                                  # la bouteille géante : la petite, KG fois plus grande
EU = (CA, SA)
EV = (-SA, CA)
FOOT = (LEGS[0] + LEG_W / 2, 900.0)       # le pied gauche touche le sol ici
UG_FOOT = 1600.0
GIANT = (FOOT[0] - EV[0] * HB * KG - EU[0] * UG_FOOT, FOOT[1] - EV[1] * HB * KG - EU[1] * UG_FOOT, A0)
GPOLYS = [[(u * KG, v * KG) for u, v in P] for P in POLYS]
GHILITE = [(u * KG, v * KG) for u, v in HILITE]


def floor_y(x):
    """Le sol : la paroi intérieure basse de la bouteille géante."""
    return FOOT[1] + (x - FOOT[0]) * math.tan(A0)


def ceil_y(x):
    return floor_y(x) - 2 * HB * KG / CA


def giant_floor(x, r):
    """Le point de la paroi basse de la géante (profil réel, épaule comprise) que touche une
    balle de rayon r centrée au-dessus de x, et la normale vers l'intérieur."""
    best = None
    for k in range(0, 1201):
        su = k * UL / 1200.0
        h, d = h_in(su) * KG, dh(su)
        L = math.hypot(d, 1.0)
        nl = (d / L, -1.0 / L)
        wx, wy = to_world(GIANT, su * KG, h)
        nx, ny = nl[0] * CA - nl[1] * SA, nl[0] * SA + nl[1] * CA
        cx = wx + nx * r
        if best is None or abs(cx - x) < best[0]:
            best = (abs(cx - x), (wx, wy), (nx, ny))
    return best[1], best[2]




def pose_on_table(x_lip, a, y_table=0.0):
    lx, ly = to_world((0, 0, a), UL, LIPO)
    return (x_lip - lx, y_table - ly, a)


# ------------------------------------------------------------------ l'horloge
T_DROP, DROP_DUR = 12.05, 0.50          # la bouteille tombe de sa cale
T_TRY = 17.20                           # il tente le goulot, y entre à moitié, ressort
T_ENTRY, T_POP = 22.00, 23.80           # l'entrée qui réussit, montrée ; la tête sort
ENTRY_SURGES = (22.45, 22.95, 23.40)
STUCK_HOPS = [(24.60, 0.50, 50.0, 40.0), (25.60, 0.40, 36.0, 30.0), (26.60, 0.40, 36.0, 30.0),
              (27.60, 0.40, 36.0, 30.0), (28.60, 0.45, 44.0, 26.0)]   # (t, durée, levée, avance)
T_CALL, T_PLANT = 30.60, 31.60          # le saut fait exprès, la bouteille plantée sur sa tête
T_CALE = 46.10                          # il pousse la cale hors de la table
T_LAUNCH, T_FLOOR = 52.80, 55.50        # le rebond immense, le sol
FLAT_JOLT = (7.0, 5.0, 0.20)            # (levée, avance, durée) d'un à-coup, bouteille couchée
CALE_JOLT = (8.0, 3.0, 0.18)

POSE0 = pose_on_table(1000.0, A0)
CALE = (0.0, 0.0, 1.0)                  # fixée par World, là où le fond quitte la cale
_fc = to_world(POSE0, -GL, HB + GL)
GLIP = to_world(GIANT, UL * KG, LIPO * KG)
GFOND = to_world(GIANT, -GL * KG, (HB + GL) * KG)
GTABLE_Y = GLIP[1]

BG = (8, 8, 12)
GLASS_LINE = (176, 198, 226)
GLASS_FILL = (120, 150, 190, 55)
INTERIOR = (15, 18, 29)
HILITE_COL = (240, 246, 255)
TABLE_COL = (92, 92, 104)
TABLE_EDGE = (134, 134, 148)
LEG_COL = (78, 78, 90)
CALE_COL = (112, 86, 64)


# ================================================================== le plan
class Plan:
    def __init__(self):
        self.pieces = []          # (t0, t1, fn) -> état de Bounce
        self.hits = []
        self.hops = []            # à-coups de la bouteille (t, levée, avance, durée)

    def add(self, t0, t1, fn):
        self.pieces.append((t0, t1, fn))

    def at(self, T):
        for (t0, t1, fn) in self.pieces:
            if t0 <= T < t1:
                return fn(T)
        if T < self.pieces[0][0]:
            return self.pieces[0][2](self.pieces[0][0])
        t0, t1, fn = self.pieces[-1]
        return fn(T)


class Mover:
    """Bounce qui vole et touche des parois, dans un repère où la gravité vaut (gx, gy)."""

    def __init__(self, plan, T, C, r, gx, gy, mode):
        self.p, self.T, self.C, self.r = plan, T, C, r
        self.gx, self.gy, self.mode = gx, gy, mode

    def state(self, x, y, r, depth=0.0, n=(0.0, -1.0), spin=None):
        return {"mode": self.mode, "u": x, "v": y, "r": r, "depth": depth, "n": n, "spin": spin}

    def arc(self, t1, C1, spin=None):
        T0, (x0, y0) = self.T, self.C
        Tt = t1 - T0
        gx, gy = self.gx, self.gy
        vx = (C1[0] - x0 - 0.5 * gx * Tt * Tt) / Tt
        vy = (C1[1] - y0 - 0.5 * gy * Tt * Tt) / Tt
        r = self.r

        def f(T):
            tau = T - T0
            sp = None if spin is None else spin[0] + spin[1] * tau
            return self.state(x0 + vx * tau + 0.5 * gx * tau * tau, y0 + vy * tau + 0.5 * gy * tau * tau, r, spin=sp)
        self.p.add(T0, t1, f)
        self.T, self.C = t1, C1
        self.vel = (vx + gx * Tt, vy + gy * Tt)

    def touch(self, wpt, n, r_new, amp=0.22, dc=0.07, hop=None, voiced=True):
        """Le contact : il s'écrase sur la paroi, gonfle d'un cran, repart."""
        (wx, wy), (nx, ny) = wpt, n
        T0, r0 = self.T, self.r
        if voiced:
            self.p.hits.append(T0)
        if hop:
            self.p.hops.append((T0,) + hop)

        def f(T):
            tau = (T - T0) / dc
            rho = r0 + (r_new - r0) * ease(tau * 1.25)
            depth = amp * rho * math.sin(math.pi * lin(tau))
            return self.state(wx + nx * (rho - depth), wy + ny * (rho - depth), rho, depth, (nx, ny))
        self.p.add(T0, T0 + dc, f)
        self.T = T0 + dc
        self.r = r_new
        self.C = (wx + nx * r_new, wy + ny * r_new)


class Local(Mover):
    """Dans la bouteille : repère local (u, v) ; la gravité suit la pente de la bouteille."""

    def __init__(self, plan, T, C, r, tilt):
        super().__init__(plan, T, C, r, G * math.sin(tilt), G * math.cos(tilt), "local")

    def set_tilt(self, tilt):
        self.gx, self.gy = G * math.sin(tilt), G * math.cos(tilt)

    def wall(self, side, s):
        if side == "fond":
            return (0.0, s), (1.0, 0.0)
        h, d = h_in(s), dh(s)
        L = math.hypot(d, 1.0)
        if side == "floor":
            return (s, h), (d / L, -1.0 / L)
        return (s, -h), (d / L, 1.0 / L)

    def center(self, side, s, r):
        (wx, wy), (nx, ny) = self.wall(side, s)
        return (wx + nx * r, wy + ny * r)

    def roll(self, t1, v0, acc):
        r, T0, s0 = self.r, self.T, self.s

        def f(T):
            tau = T - T0
            u, v = self.center("floor", s0 + v0 * tau + 0.5 * acc * tau * tau, r)
            return self.state(u, v, r)
        self.p.add(T0, t1, f)
        tau = t1 - T0
        self.s = s0 + v0 * tau + 0.5 * acc * tau * tau
        self.C = self.center("floor", self.s, r)
        self.T = t1

    def to(self, t1, side, s, spin=None):
        self.arc(t1, self.center(side, s, self.r), spin)
        self.side, self.s = side, s

    def hit(self, r_new, amp=0.22, dc=0.07, hop=None):
        w, n = self.wall(self.side, self.s)
        self.touch(w, n, r_new, amp, dc, hop)


# ------------------------------------------------------------------ dans la bouteille
def squeeze_state(u_r, r_r, front, rh=0.0, face="front", spin=None):
    """Bounce qui force le passage : une boule à l'arrière, la chair qui s'étire dans
    l'épaule et le goulot jusqu'au front (toujours le long de l'axe), et la tête dehors."""
    return {"mode": "squeeze", "u_r": u_r, "r_r": r_r, "front": front, "rh": rh, "face": face, "spin": spin}


def build_inside(p):
    L = Local(p, 0.0, (500.0, 22.0), 31.0, A0)
    # 0 s : il est déjà en l'air, retombe, roule vers l'embouchure
    L.to(0.28, "floor", 520.0)
    L.hit(34.0, hop=CALE_JOLT)
    L.roll(1.25, 60.0, 40.0)
    # il regarde la caméra, puis le saut fait exprès
    L.to(1.92, "floor", L.s + 34.0)
    L.hit(42.0, amp=0.26, dc=0.08, hop=CALE_JOLT)
    # l'épaule le renvoie vers le fond : il remonte la pente ; chaque choc pousse la bouteille sur sa cale
    for (t, s, r) in [(2.75, 490.0, 44.0), (3.58, 380.0, 46.0), (4.41, 270.0, 48.0), (5.24, 160.0, 50.0)]:
        L.to(t, "floor", s)
        L.hit(r, hop=CALE_JOLT)
    L.arc(6.05, (50.0, 26.0))
    L.side, L.s = "fond", 26.0
    L.hit(53.0, amp=0.45, dc=0.16, hop=CALE_JOLT)
    for (t, s, r) in [(7.0, 230.0, 54.5), (7.8, 320.0, 56.0), (8.6, 400.0, 57.5), (9.4, 470.0, 59.0),
                      (10.2, 535.0, 60.5), (11.0, 470.0, 62.0)]:
        L.to(t, "floor", s)
        L.hit(r, hop=CALE_JOLT)
    # le choc qui fait tomber la bouteille de sa cale : il reste écrasé pendant la chute
    L.to(T_DROP, "floor", 420.0)
    L.hit(63.5, amp=0.30, dc=DROP_DUR)
    L.set_tilt(0.0)
    for (t, s, r) in [(13.25, 470.0, 65.0), (14.05, 390.0, 66.5), (14.85, 320.0, 68.0), (15.65, 410.0, 69.5),
                      (16.45, 500.0, 71.0)]:
        L.to(t, "floor", s)
        L.hit(r, hop=FLAT_JOLT)
    # il tente le goulot : il roule, remonte l'épaule, y entre à moitié, et ressort
    r = 72.5
    L.r = r
    L.roll(T_TRY, 230.0, -150.0)
    p.hits.append(T_TRY)
    t1, t2 = T_TRY + 0.42, T_TRY + 0.62

    def f_try(T):
        if T < t1:
            k = ease((T - T_TRY) / (t1 - T_TRY))
            u_r = lerp(600.0, 604.0, k)
            front = lerp(600.0 + r, 760.0, 1 - (1 - k) ** 2)
        else:
            k = ease((T - t1) / (t2 - t1))
            u_r = lerp(604.0, 590.0, k)
            front = lerp(760.0, 590.0 + r, k)
        return squeeze_state(u_r, min(r, h_in(u_r) - 2.0), front)
    p.add(T_TRY, t2, f_try)
    L.T, L.C, L.r = t2, (590.0, 0.0), r
    for (t, s, rr) in [(18.25, 470.0, 74.0), (19.05, 380.0, 75.0), (19.85, 270.0, 76.0)]:
        L.to(t, "floor", s)
        L.hit(rr, hop=FLAT_JOLT)
    # le fond de plein fouet, et il file vers le goulot
    L.arc(20.65, (77.0, 34.0))
    L.side, L.s = "fond", 34.0
    L.hit(78.0, amp=0.5, dc=0.18, hop=FLAT_JOLT)
    L.to(21.25, "floor", 300.0)
    L.hit(79.0, hop=FLAT_JOLT)
    L.roll(T_ENTRY, 420.0, -60.0)
    p.hits.append(T_ENTRY)
    p.hops.extend((t, 9.0, 2.0, 0.22) for t in ENTRY_SURGES)   # chaque poussée secoue la bouteille
    return L


def entry_state(T, r):
    """L'entrée qui réussit, en trois poussées : le front avance dans le goulot, le visage
    pressé contre le verre, jusqu'à ce que la tête sorte par l'embouchure."""
    k = lin((T - T_ENTRY) / (T_POP - 0.12 - T_ENTRY))
    surges = (k + 0.08 * math.sin(3 * 2 * math.pi * k)) if k < 1 else 1.0
    # trois poussées : à chacune, la boule arrière se tasse puis pousse
    puff = 0.0
    for th in ENTRY_SURGES:
        u = T - th
        if 0 <= u < 0.35:
            puff = max(puff, math.sin(math.pi * u / 0.35))
    u_r = 585.0 - 14.0 * puff
    r = r * (1.0 + 0.08 * puff)
    front = lerp(585.0 + 0.6 * r, UL, lin(surges))
    rh = 60.0 * ease((T - (T_POP - 0.12)) / 0.14) if T > T_POP - 0.12 else 0.0
    return squeeze_state(u_r, min(r, h_in(u_r) - 2.0), front, rh, "front" if rh < 30 else "head")


# ------------------------------------------------------------------ coincé
RH = [(T_POP, 60.0)] + [(t, 60.0 + 3.5 * (k + 1)) for k, (t, _d, _l, _a) in enumerate(STUCK_HOPS)] + [(T_CALL, 79.0)]


def rh_at(T):
    v = 0.0
    for (t, r) in RH:
        if T >= t:
            v = r if T >= t + 0.1 else v + (r - v) * ease((T - t) / 0.1)
    return v


def head_center(pose, rh, c=0.72):
    a = pose[2]
    mx, my = to_world(pose, UL, 0.0)
    return mx + c * rh * math.cos(a), my + c * rh * math.sin(a)


def flat_pose(xc, rh):
    """Couchée sur la table, sans cale, la tête dehors : elle repose sur le bas de son
    épaule (u = LB) et sur la tête de Bounce, plus lourde que le goulot."""
    def make(a):
        px, py = to_world((0, 0, a), LB, h_out(LB))
        return (xc - px, -py, a)

    def head_bottom(a):
        hx, hy = head_center(make(a), rh)
        return hy + rh
    lo, hi = -0.2, 0.7
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if head_bottom(m) < 0:
            lo = m
        else:
            hi = m
    return make(0.5 * (lo + hi))


# ------------------------------------------------------------------ la table
def sag_at(T):
    """Le plateau plie sous les rebonds lourds, puis vibre."""
    v = 0.0
    for (th, amp) in ((49.90, 24.0), (51.15, 28.0), (T_LAUNCH, 32.0)):
        u = T - th
        if u >= 0:
            v += amp * math.exp(-u / 0.45) * math.cos(2 * math.pi * 3.2 * u) if u > 0.2 else amp * math.sin(math.pi * u / 0.4)
    return v


def table_lift(T):
    """La table entière tressaute sur ses pieds (double rebond)."""
    v = 0.0
    for th in (43.50, 44.30):
        u = T - th - 0.06
        if 0 <= u < 0.26:
            v += 14.0 * math.sin(math.pi * u / 0.26)
    return v


class World:
    def __init__(self, cfg):
        self.cfg = cfg
        p = Plan()
        self.L = build_inside(p)
        self.p = p
        self.r_entry = self.L.r
        # la cale : son bord droit est là où le fond la quitte
        x_fc = to_world(self.cale_pose(T_DROP - 1e-3), -GL, HB + GL)[0]
        global CALE
        CALE = (x_fc - 200.0, _fc[1] + 2, x_fc - 4.0)
        self.flat0 = self.flat_rest()
        self.stuck_x0 = to_world(self.flat_pose_at(T_POP), LB, h_out(LB))[0]
        p.hits.extend([T_POP] + [t for (t, _d, _l, _a) in STUCK_HOPS] + [T_CALL])
        self.build_table()
        p.hits.sort()

    # ---- la bouteille, de 0 à 30,6 s
    def jolts(self, T, t0, t1):
        dx = dy = 0.0
        for (th, lift, adv, dur) in self.p.hops:
            if t0 <= th < t1 and T >= th:
                k = lin((T - th) / dur)
                dx += adv * ease(k)
                dy -= lift * 4 * k * (1 - k)
        return dx, dy

    def cale_pose(self, T):
        dx, dy = self.jolts(T, 0.0, T_DROP)
        return (POSE0[0] + dx, POSE0[1] + dy, A0)

    def flat_rest(self):
        """Tombée de la cale : couchée sur son flanc, l'embouchure là où elle était."""
        p0 = self.cale_pose(T_DROP)
        lip_x = to_world(p0, UL, 0.0)[0]
        return (lip_x - UL, -(HB + GL), 0.0)

    def flat_pose_at(self, T):
        dx, dy = self.jolts(T, T_DROP + 0.1, T_POP)
        x, y, a = self.flat0
        return (x + dx, y + dy, a)

    def bottle_pose(self, T):
        if T < T_DROP:
            return self.cale_pose(T)
        if T < T_DROP + DROP_DUR:
            # le fond glisse de la cale : elle bascule sur sa lèvre et tombe à plat, avec un rebond
            k = (T - T_DROP) / DROP_DUR
            p0, p1 = self.cale_pose(T_DROP), self.flat0
            kk = lin(k / 0.7) ** 2
            a = lerp(p0[2], p1[2], kk)
            if k > 0.7:
                a = 0.05 * math.sin(math.pi * (k - 0.7) / 0.3)
            lip0 = to_world(p0, UL, LIPO)
            lip1 = to_world(p1, UL, LIPO)
            lx, ly = lerp(lip0[0], lip1[0], kk), lerp(lip0[1], lip1[1], kk)
            ox, oy = to_world((0, 0, a), UL, LIPO)
            pose = (lx - ox, ly - oy, a)
            # le point le plus bas reste sur la table
            low = max(to_world(pose, u, h_out(u))[1] for u in (-GL, 0.0, LB, UN, UL))
            return (pose[0], pose[1] - max(0.0, low), a)
        if T < T_POP:
            return self.flat_pose_at(T)
        # la tête sort : plus lourde que le goulot, elle fait pencher la bouteille vers l'avant
        xc = self.stuck_x0
        prev = self.flat_pose_at(T_POP)
        if T < T_POP + 0.5:
            tgt = flat_pose(xc, rh_at(T))
            return self.blend(prev, tgt, (T - T_POP) / 0.5, 0.0)
        prev = flat_pose(xc, rh_at(T_POP + 0.5))
        for (th, dur, lift, adv) in STUCK_HOPS:
            if T < th:
                break
            tgt = flat_pose(xc + adv, rh_at(th + dur))
            if T < th + dur:
                return self.blend(prev, tgt, (T - th) / dur, lift)
            xc += adv
            prev = tgt
        return flat_pose(xc, rh_at(T))

    def blend(self, p0, p1, k, lift):
        kk = ease(k)
        return (lerp(p0[0], p1[0], kk), lerp(p0[1], p1[1], kk) - lift * 4 * lin(k) * (1 - lin(k)), lerp(p0[2], p1[2], kk))

    # ---- de 31,6 s à la fin : la bouteille plantée sur sa tête, la table, le sol
    def build_table(self):
        p = self.p
        M = Mover(p, 0.0, (0, 0), 0.0, 0.0, G, "world")
        self.M = M
        pose_c = self.bottle_pose(T_CALL)
        hx, hy = head_center(pose_c, rh_at(T_CALL))
        self.call = (hx, hy, pose_c[2])
        R = 120.0
        land = (hx - 170.0, -R)
        self.flip_land = land
        # le saut fait exprès : la tête bondit, la bouteille passe par-dessus et se plante
        M.T, M.C, M.r = T_CALL, (hx, hy), R
        M.arc(T_PLANT, land)
        M.touch((land[0], 0.0), (0.0, -1.0), 126.0, amp=0.34, dc=0.16)
        seq = [  # (t, x, r, amp)
            (32.45, 1020.0, 131.0, 0.22), (33.30, 960.0, 137.0, 0.22),
            (34.30, 920.0, 143.0, 0.26),                      # le rebond pour s'en débarrasser
            (35.60, 1000.0, 150.0, 0.28),                     # ... la bouteille se replante
            (36.45, 1180.0, 156.0, 0.22), (37.30, 1350.0, 162.0, 0.22),
            (38.15, 1490.0, 168.0, 0.22),                     # au bord : à moitié dans le vide
            (39.50, 1200.0, 175.0, 0.24),                     # il se rattrape
            (40.40, 980.0, 182.0, 0.22),
            (41.40, 860.0, 380.0, 0.32),                      # il double d'un coup
            (42.60, 820.0, 400.0, 0.22), (43.50, 800.0, 420.0, 0.24), (44.30, 780.0, 440.0, 0.24),
            (45.20, 740.0, 458.0, 0.22), (46.10, 700.0, 476.0, 0.26),   # il pousse la cale hors de la table
            (47.00, 760.0, 494.0, 0.22), (47.90, 820.0, 512.0, 0.26),   # la bouteille glisse sur sa tête
            (48.80, 860.0, 530.0, 0.24), (49.90, 1000.0, 548.0, 0.30), (51.15, 1240.0, 566.0, 0.30),
            (T_LAUNCH, 1470.0, 584.0, 0.30)]
        for (t, x, r, amp) in seq:
            M.arc(t, (x, -M.r))
            M.touch((x, 0.0), (0.0, -1.0), r, amp=amp, dc=0.12 if amp < 0.3 else 0.2)
        # le rebond immense, à côté de la table, jusqu'au sol ; puis vers le bas de la pente
        self.t_floor = T_FLOOR
        seq = [(T_FLOOR, 3400.0, 600.0, 0.5, 0.22), (56.86, 3720.0, 616.0, 0.22, 0.12),
               (58.04, 3980.0, 632.0, 0.22, 0.12), (60.30, 4200.0, 650.0, 0.34, 0.16)]
        for (t, x, r, amp, dc) in seq:
            wpt, n = giant_floor(x, M.r)
            M.arc(t, (wpt[0] + n[0] * M.r, wpt[1] + n[1] * M.r))
            M.touch(wpt, n, r, amp=amp, dc=dc)
        wpt, n = giant_floor(4420.0, M.r)
        M.arc(62.3, (wpt[0] + n[0] * M.r, wpt[1] + n[1] * M.r))

    def ball(self, T):
        return self.p.at(T)


# ================================================================== caméra et dessin
class Cam:
    def __init__(self, cx, cy, s, S):
        self.cx, self.cy, self.s, self.S = cx, cy, s, S

    def X(self, x, y):
        return ((x - self.cx) * self.s + W / 2) * self.S, ((y - self.cy) * self.s + H / 2) * self.S

    def L(self, l):
        return l * self.s * self.S

    def pts(self, P):
        return [self.X(x, y) for x, y in P]

    def scr(self, x, y):
        return (x - self.cx) * self.s + W / 2, (y - self.cy) * self.s + H / 2


def poly_world(pose, P):
    return [to_world(pose, u, v) for u, v in P]


def ellipse_pts(cx, cy, a, b, ang, n=48):
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = a * math.cos(t), b * math.sin(t)
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


def draw_glass_front(dr, dra, cam, pose, polys, hil=1.0, line_col=GLASS_LINE, fill=GLASS_FILL, k=1.0, hpts=None, min_px=0.0):
    """Le verre : deux contours clairs (l'embouchure reste ouverte), la bande entre les deux,
    la lèvre plus épaisse, le long reflet blanc."""
    outer, inner, top, bot = polys
    w = max(2, int(cam.L(GL * k) * 0.42), int(min_px * cam.S))
    for band in (top, bot):
        dra.polygon(cam.pts(poly_world(pose, band)), fill=fill)
    n2 = len(outer) // 2
    # le contour extérieur, de la lèvre haute à la lèvre basse en passant par le fond : jamais à travers l'embouchure
    dr.line(cam.pts(poly_world(pose, outer[:n2][::-1] + outer[n2:][::-1])), fill=line_col, width=w, joint="curve")
    ins = [q for q in inner if q[0] <= UL * k + 0.1]
    m2 = len(ins) // 2
    lc = dim(line_col, 0.8)
    dr.line(cam.pts(poly_world(pose, ins[:m2])), fill=lc, width=max(2, w - 1), joint="curve")
    dr.line(cam.pts(poly_world(pose, ins[m2:])), fill=lc, width=max(2, w - 1), joint="curve")
    for sg in (-1, 1):
        ring = [(UL0 - 2, sg * HL), (UL, sg * HL), (UL, sg * LIPO), (UL0 - 2, sg * LIPO)]
        dr.polygon(cam.pts(poly_world(pose, [(u * k, v * k) for u, v in ring])), fill=dim(line_col, 0.75))
    if hil > 0:
        col = mix(BG, HILITE_COL, hil)
        dr.line(cam.pts(poly_world(pose, hpts or HILITE)), fill=col,
                width=max(2, int(cam.L(HB * k * 0.085)), int(min_px * 0.8 * cam.S)), joint="curve")


def face_at(dr, X, Y, r, gaze=(0.0, 0.0), spin=None):
    gx, gy = gaze
    if spin is not None:
        base.HERO["tilt"] = spin
    base.hero_face(dr, X + gx * r * 0.34, Y + gy * r * 0.34, r * 0.92)
    if base.HERO["pos"] is None:
        base.HERO["pos"] = (X, Y)


GAZE = [  # (t, gx, gy) : 0,0 = la caméra
    (0.0, 0.8, 0.25), (0.7, 0.8, 0.25), (0.9, 0.0, 0.0), (2.05, 0.0, 0.0), (2.25, -0.6, 0.0),
    (5.9, -0.6, 0.0), (6.25, 0.6, 0.15), (11.9, 0.6, 0.15), (12.1, 0.0, 0.7), (12.5, 0.0, 0.7), (12.7, 0.0, 0.0),
    (16.4, 0.0, 0.0), (16.6, 0.85, 0.0), (17.8, 0.85, 0.0), (18.0, 0.0, 0.0), (19.8, 0.0, 0.0), (20.0, -0.6, 0.0),
    (21.2, -0.6, 0.0), (21.45, 0.85, 0.0), (23.75, 0.85, 0.0), (23.95, 0.0, 0.0),
    (28.75, 0.0, 0.0), (28.95, 0.6, 0.6), (29.3, 0.6, 0.6), (29.5, 0.0, 0.0),
    (33.4, 0.0, 0.0), (33.6, 0.0, -0.85), (35.5, 0.0, -0.85), (35.75, 0.0, 0.0),
    (38.2, 0.0, 0.0), (38.35, 0.5, 0.85), (39.3, 0.5, 0.85), (39.5, 0.0, 0.0),
    (47.95, 0.0, 0.0), (48.1, 0.4, -0.8), (48.6, 0.4, -0.8), (48.8, 0.0, 0.0),
    (53.5, 0.0, 0.0), (53.75, 0.2, 0.85), (55.35, 0.2, 0.85), (55.6, 0.0, 0.0),
    (59.2, 0.0, 0.0), (59.45, 0.0, -0.8), (60.15, 0.0, -0.8), (60.3, 0.0, 0.0),
]


def gaze_at(T):
    gx = keyed([(t, a) for t, a, b in GAZE], T)
    gy = keyed([(t, b) for t, a, b in GAZE], T)
    return gx, gy


def cale_state(T):
    """La cale reste où la bouteille l'a laissée, jusqu'à ce que Bounce, qui couvre presque
    tout le plateau, la pousse hors de la table : elle bascule par-dessus le bord, tombe et
    se pose à plat sur le sol en pente."""
    w, h = CALE[2] - CALE[0], -CALE[1]
    cx, cy = 0.5 * (CALE[0] + CALE[2]), CALE[1] + h / 2
    if T < T_CALE:
        return cx, cy, 0.0
    u = T - T_CALE
    vx = -560.0
    t_off = (cx + 0.15 * w) / -vx
    if u < t_off:
        return cx + vx * u, cy, 0.0
    tau = u - t_off
    x = cx + vx * u
    y = cy + 0.5 * G * tau * tau
    a = -2.6 * tau
    a_rest = A0 - math.pi / 2
    gy = floor_y(x) - 0.5 * w / CA
    if y >= gy:
        lo, hi = 0.0, tau
        for _ in range(30):
            m = 0.5 * (lo + hi)
            xm = cx + vx * (t_off + m)
            if cy + 0.5 * G * m * m >= floor_y(xm) - 0.5 * w / CA:
                hi = m
            else:
                lo = m
        tc = hi
        xc = cx + vx * (t_off + tc)
        ac = -2.6 * tc
        k = ease((tau - tc) / 0.35)
        xr = xc + vx * 0.25 * min(tau - tc, 0.35)
        return xr, floor_y(xr) - 0.5 * w / CA, lerp(ac, a_rest, k)
    return x, y, a


class Scene:
    def __init__(self, cfg):
        self.w = World(cfg)
        self.N = int(math.ceil(END * FPS)) + 4
        self.plan_flight()
        self.make_camera()

    # ---- la petite bouteille qui saute comme un bouchon, effleure le plafond, retombe sur sa tête
    def plan_flight(self):
        w = self.w
        self.t_pop = w.t_floor + 0.05
        b0 = w.ball(self.t_pop)
        R0 = b0["r"]
        self.c_pop = 0.56
        m0 = (b0["u"], b0["v"] - self.c_pop * R0)
        self.f_c0 = (m0[0], m0[1] - (UL - 430.0))
        best = None
        for k in range(0, 60):
            tl = 59.10 + 0.01 * k
            b1 = w.ball(tl)
            c1 = (b1["u"], b1["v"] - 1.0 * b1["r"] - (UL - 430.0))
            T = tl - self.t_pop
            vx = (c1[0] - self.f_c0[0]) / T
            vy = (c1[1] - self.f_c0[1] - 0.5 * G * T * T) / T
            ta = -vy / G
            xa, ya = self.f_c0[0] + vx * ta, self.f_c0[1] + vy * ta + 0.5 * G * ta * ta
            gap = (ya - 430.0) - ceil_y(xa)
            if best is None or abs(gap - 12.0) < abs(best[0] - 12.0):
                best = (gap, tl, vx, vy)
        gap, tl, vx, vy = best
        self.t_bl, self.f_v = tl, (vx, vy)
        self.f_spin = 2 * math.pi * 3 / (tl - self.t_pop)
        self.w.p.hits.append(tl)
        self.w.p.hits.sort()
        self.t_chase = 60.32
        self.graze_gap = gap

    def flight_pose(self, T):
        if T < self.t_bl:
            tau = T - self.t_pop
            cx = self.f_c0[0] + self.f_v[0] * tau
            cy = self.f_c0[1] + self.f_v[1] * tau + 0.5 * G * tau * tau
            a = math.pi / 2 + self.f_spin * tau
            return (cx - 430.0 * math.cos(a), cy - 430.0 * math.sin(a), a)
        tau = T - self.t_chase
        p0 = self.hat_pose_at(self.t_chase)
        c0 = to_world(p0, 430.0, 0.0)
        cx = c0[0] - 900.0 * tau
        cy = c0[1] - 1900.0 * tau + 0.5 * G * tau * tau
        a = math.pi / 2 - 6.0 * tau
        return (cx - 430.0 * math.cos(a), cy - 430.0 * math.sin(a), a)

    # ---- l'état à l'instant T
    def state(self, T):
        w = self.w
        b = dict(w.ball(T))
        if T < T_ENTRY:
            return {"phase": "in", "pose": w.bottle_pose(T), "ball": b}
        if T < T_POP:
            return {"phase": "in", "pose": w.bottle_pose(T), "ball": entry_state(T, w.r_entry)}
        if T < T_CALL:
            pose = w.bottle_pose(T)
            return {"phase": "stuck", "pose": pose, "ball": self.stuck_ball(T, pose)}
        st = self.hat_state(T, b)
        if self.t_pop <= T < self.t_bl or T >= self.t_chase + 0.02:
            st["phase"] = "free"
            st["fpose"] = self.flight_pose(T)
        return st

    def stuck_ball(self, T, pose):
        rh = rh_at(T)
        wig = 0.10 * math.sin(2 * math.pi * 2.3 * T) + 0.07 * math.sin(2 * math.pi * 3.7 * T + 1.0)
        hx, hy = head_center(pose, rh)
        # il gigote : la tête bouge sans cesse, sans jamais quitter l'embouchure
        mx, my = to_world(pose, UL, 0.0)
        ang = math.atan2(hy - my, hx - mx) + wig
        d = math.hypot(hx - mx, hy - my)
        hx, hy = mx + d * math.cos(ang), my + d * math.sin(ang)
        if hx - 0.3 * rh < TABLE_X1:
            hy = min(hy, -rh)
        # ce qui reste dedans : une boule à l'entrée de l'épaule, tirée vers le goulot à
        # mesure que la tête grossit dehors
        k_in = lin((rh - 60.0) / (79.0 - 60.0))
        u_r = lerp(585.0, 712.0, ease(k_in))
        r_r = min(lerp(self.w.r_entry, HN - 2.0, ease(k_in)), h_in(u_r) - 2.0)
        st = squeeze_state(u_r, r_r, UL, rh, "head")
        st["head"] = (hx, hy)
        return st

    def hat_state(self, T, b):
        w = self.w
        if T < T_PLANT:
            # le saut fait exprès : il s'arrache du goulot, la bouteille passe par-dessus sa tête
            k = lin((T - T_CALL) / (T_PLANT - T_CALL))
            R = lerp(79.0, 120.0, ease(k * 2.0))
            b = dict(b)
            b["r"] = R
            a = lerp(w.call[2], math.pi / 2, ease(k / 0.85))
            st = {"phase": "hat", "ball": b, "c": 0.72, "a": a, "lift": 0.0,
                  "u_in": lerp(712.0, UL - 0.28 * R - 24, ease(k))}
            return st
        if T_CALL <= T < T_PLANT + 0.3:
            c = keyed([(T_PLANT, 0.72), (T_PLANT + 0.2, 0.15)], T)
        elif T < 59.0:
            c = keyed([(T_PLANT + 0.2, 0.15), (41.40, 0.15), (41.65, 0.56)], T)
        else:
            c = keyed([(self.t_bl, 1.0), (self.t_bl + 0.16, 0.40)], T)
        wob = 0.0
        for (th, amp) in [(T_PLANT, 0.14), (32.45, 0.14), (33.30, 0.16), (35.60, 0.3), (36.45, 0.14), (37.30, 0.14),
                          (38.15, 0.24), (39.50, 0.2), (41.40, 0.2), (43.50, 0.16), (44.30, 0.16), (46.10, 0.14),
                          (47.90, 0.0), (49.90, 0.12), (51.15, 0.12), (T_LAUNCH, 0.1), (self.t_bl, 0.25), (60.30, 0.0)]:
            u = T - th
            if u >= 0:
                wob += amp * math.exp(-u / 0.7) * math.sin(2 * math.pi * 1.3 * u)
        # 47,9 s : la bouteille glisse sur le côté de sa tête, penche... et se remet en place
        u = T - 47.90
        if 0 <= u < 1.2:
            wob += 0.42 * math.sin(math.pi * u / 1.2) * (1 - 0.3 * math.sin(2 * math.pi * 2.0 * u))
        a = math.pi / 2 + wob
        st = {"phase": "hat", "ball": b, "c": c, "a": a, "lift": 0.0}
        # 34,3 s : le rebond pour s'en débarrasser. La bouteille décolle franchement... et se replante
        if 34.42 <= T < 35.60:
            u = (T - 34.42) / 1.18
            st["lift"] = 430.0 * 4 * u * (1 - u)
            st["a"] += 0.5 * math.sin(math.pi * u)
        return st

    def hat_pose(self, x, y, R, c, a, lift=0.0):
        mx, my = x - c * R * math.cos(a), y - c * R * math.sin(a) - lift
        return (mx - UL * math.cos(a), my - UL * math.sin(a), a)

    def hat_pose_at(self, T):
        st = self.hat_state(T, dict(self.w.ball(T)))
        b = st["ball"]
        return self.hat_pose(b["u"], b["v"], b["r"], st["c"], st["a"], st["lift"])

    def small_pose(self, T, st=None):
        st = st or self.state(T)
        if st["phase"] in ("in", "stuck"):
            return st["pose"]
        if st["phase"] == "free":
            return st["fpose"]
        b = st["ball"]
        return self.hat_pose(b["u"], b["v"], b["r"], st["c"], st["a"], st["lift"])

    def ball_world(self, T, st=None):
        """(x, y, r, r plein) de Bounce dans le monde : la tête quand il est coincé."""
        st = st or self.state(T)
        b = st["ball"]
        if st["phase"] in ("in", "stuck") and b["mode"] == "squeeze":
            if b["rh"] > 20 and "head" in b:
                return b["head"][0], b["head"][1], b["rh"], b["rh"]
            if b["rh"] > 20:
                hx, hy = head_center(st["pose"], b["rh"])
                return hx, hy, b["rh"], b["rh"]
            X, Y = to_world(st["pose"], b["u_r"], 0.0)
            return X, Y, b["r_r"], max(b["r_r"], 60.0)
        if st["phase"] == "in":
            X, Y = to_world(st["pose"], b["u"], b["v"])
            return X, Y, b["r"] - b.get("depth", 0.0), b["r"]
        return b["u"], b["v"], b["r"] - b.get("depth", 0.0), b["r"]

    # ---- la caméra
    def final_view(self):
        """Le dernier cadre : la géante du fond jusqu'au début du goulot, assez serrée pour
        que Bounce, la petite bouteille et l'ancienne table se lisent."""
        x0, x1 = GFOND[0] - 250.0, 7400.0
        s = (W - 60.0) / (x1 - x0)
        top = to_world(GIANT, 0.0, -(HB + GL) * KG)[1]
        cx = (x0 + x1) / 2 + 20.0 / s
        cy = 0.5 * (top + GTABLE_Y) + 120.0 - 140.0 / s
        return cx, cy, s

    def cam_target(self, T):
        st = self.state(T)
        X, Y, r, rfull = self.ball_world(T, st)
        if T < 2.25:
            # l'ouverture : un cadre fixe, la balle à gauche, le goulot et l'embouchure à droite
            pose = self.w.bottle_pose(0.0)
            ax, ay = to_world(pose, 700.0, 30.0)
            return ax, ay - 30.0, 2.2, 0.05
        if T < T_DROP:
            pose = self.w.bottle_pose(T)
            ax, ay = to_world(pose, 330.0, 0.0)
            bx, by = to_world(pose, 610.0, 0.0)
            k = lin((X - ax) / (bx - ax + 1e-6))
            cx, cy = to_world(pose, lerp(360.0, 560.0, k), 20.0)
            return cx, cy, 1.6, 0.6
        if T < 19.0:
            pose = self.w.bottle_pose(T)
            cx, cy = to_world(pose, lerp(420.0, 560.0, lin((X - pose[0] - 300.0) / 300.0)), 30.0)
            return cx, cy, 1.45, 0.6
        if T < T_ENTRY - 0.4:
            # la caméra recule : à droite de l'embouchure, la table s'arrête
            pose = self.w.bottle_pose(T)
            cx, cy = to_world(pose, 520.0, 0.0)
            return lerp(cx, 1060.0, 0.6), cy - 60.0, 0.85, 0.45
        if T < T_POP + 0.3:
            # l'entrée, montrée : on se rapproche du goulot
            pose = self.w.bottle_pose(T)
            cx, cy = to_world(pose, 680.0, 0.0)
            return cx, cy - 20.0, lerp(1.25, 1.7, lin((T - T_ENTRY) / 1.8)), 0.35
        if T < T_CALL:
            hx, hy = st["ball"]["head"]
            return hx - 260.0, hy - 80.0, 1.15, 0.45
        if T < 41.40:
            return min(X, 1280.0) - 60.0, -480.0, 0.82, 0.45
        if T < T_LAUNCH:
            return 900.0, -380.0, 0.5, 0.6
        if T < self.w.t_floor:
            # le rebond immense : il reste entier dans l'image
            return X + 260.0, Y - 300.0, 0.36, 0.25
        return X + 200.0, Y - 100.0, 0.45, 0.25

    def make_camera(self):
        N = self.N
        dt = 1.0 / FPS
        tg = np.zeros((N, 3))
        taus = np.zeros(N)
        for i in range(N):
            cx, cy, s, tau = self.cam_target(i * dt)
            tg[i] = (cx, cy, math.log(s))
            taus[i] = tau
        y = tg.copy()
        for _ in range(2):
            for i in range(1, N):
                y[i] = y[i - 1] + (y[i] - y[i - 1]) * (1 - math.exp(-dt / taus[i]))
            for i in range(N - 2, -1, -1):
                y[i] = y[i + 1] + (y[i] - y[i + 1]) * (1 - math.exp(-dt / taus[i]))
        # l'ouverture reste fixe : aucun lissage avant 2,2 s
        i_open = int(2.2 * FPS)
        y[:i_open] = tg[0]
        for i in range(i_open, i_open + 30):
            k = ease((i - i_open) / 30.0)
            y[i] = tg[0] + (y[i] - tg[0]) * k
        # la révélation : suivre la bouteille qui monte, puis reculer, en 1,8 s, jusqu'au cadre final
        self.t_rev0, self.t_rev1 = self.t_pop + 0.45, self.t_pop + 2.25
        gx, gy, gs = self.final_view()
        self.gview = (gx, gy, gs)
        i0 = int(self.t_pop * FPS)
        c_start = y[i0].copy()
        c_rev = c_start
        for i in range(i0, N):
            T = i * dt
            if T < self.t_rev0:
                fp = self.flight_pose(T)
                bx, by = to_world(fp, 430.0, 0.0)
                k = ease((T - self.t_pop) / (self.t_rev0 - self.t_pop))
                y[i] = (lerp(c_start[0], bx, 0.4 * k), lerp(c_start[1], by, 0.5 * k), c_start[2])
                c_rev = y[i].copy()
            else:
                k = ease((T - self.t_rev0) / (self.t_rev1 - self.t_rev0))
                ls = lerp(c_rev[2], math.log(gs), k)
                kk = (math.exp(-c_rev[2]) - math.exp(-ls)) / (math.exp(-c_rev[2]) - math.exp(-math.log(gs)) + 1e-9)
                y[i] = (lerp(c_rev[0], gx, kk), lerp(c_rev[1], gy, kk), ls)
                if T > self.t_rev1:
                    # puis la caméra s'approche, très lentement, jusqu'à la coupe
                    y[i][2] += 0.07 * ease((T - self.t_rev1) / (END - self.t_rev1))
        self.cam = y

    def cam_at(self, T):
        i = min(self.N - 1, max(0, int(round(T * FPS))))
        cx, cy, ls = self.cam[i]
        return cx, cy, math.exp(ls)

    def camera(self, T, S):
        cx, cy, s = self.cam_at(T)
        return Cam(cx, cy, s, S)

    # ---- le grand reflet : sur la vitre de la géante, tout près de nous, puis à sa place
    def reflection(self, T, cam):
        true = [cam.scr(*to_world(GIANT, u, v)) for u, v in GHILITE]
        rot = [(u * CA - v * SA, u * SA + v * CA) for u, v in GHILITE]
        xs = [p[0] for p in rot]
        k = 1240.0 / (max(xs) - min(xs))
        x0 = min(xs)
        cx0 = self.cam[0][0]
        drift_x = max(-220.0, min(220.0, -(cam.cx - cx0) * 0.05))
        drift_y = max(-90.0, min(90.0, -(cam.cy - self.cam[0][1]) * 0.03))
        ym = sum(p[1] for p in rot) / len(rot)
        sty = [(-80.0 + (x - x0) * k + drift_x, 330.0 + (y - ym) * k + drift_y) for x, y in rot]
        wt = cam.L(HB * KG * 0.085) / cam.S
        if T < self.t_rev0:
            return sty, 0.2, 26.0
        if T >= self.t_rev1:
            return true, 0.88, wt
        kk = ease((T - self.t_rev0) / (self.t_rev1 - self.t_rev0))
        pts = [(lerp(a[0], b[0], kk), lerp(a[1], b[1], kk)) for a, b in zip(sty, true)]
        return pts, lerp(0.2, 0.88, kk), lerp(26.0, wt, kk)

    def pop(self, T):
        """Le cran de gonflement se voit : juste après chaque choc, une petite bouffée."""
        k = 1.0
        for th in self.w.p.hits:
            u = T - th
            if 0.06 <= u < 0.30:
                k = max(k, 1.0 + 0.08 * math.sin(math.pi * (u - 0.06) / 0.24))
        return k

    # ---- dessin
    def draw(self, dr, T, S):
        import PIL.ImageDraw as ID
        dra = ID.Draw(dr._image, "RGBA")
        st = self.state(T)
        cam = self.camera(T, S)
        hc = base.HERO["color"]
        gz = gaze_at(T)
        pk = self.pop(T)
        if T >= 60.30:
            base.HERO["expr"] = "calm"          # le dernier « Bounce » tombe sur le visage blasé
        wide = cam.s < 0.3
        mp = 3.5 if wide else 0.0               # dans le plan large : des formes pleines, pas du fil
        # la grande table et la cale de la géante
        gt = GTABLE_Y
        dr.rectangle([*cam.X(GFOND[0] - 9000, gt), *cam.X(GLIP[0] + 9000, gt + TABLE_T * KG)], fill=TABLE_COL)
        dr.rectangle([*cam.X(GFOND[0] - 110 * KG, GFOND[1] + 2 * KG), *cam.X(GFOND[0] + 90 * KG, gt)], fill=CALE_COL)
        # la géante : sa paroi basse est le sol
        draw_glass_front(dr, dra, cam, GIANT, GPOLYS, hil=0.0, k=KG, fill=(120, 150, 190, 60 if wide else 40), min_px=4.0 if wide else 0.0)
        pts, inten, wd = self.reflection(T, cam)
        sp = [(x * S, y * S) for x, y in pts]
        dr.line(sp, fill=mix(BG, HILITE_COL, inten * 0.55), width=max(2, int(wd * 1.8 * S)), joint="curve")
        dr.line(sp, fill=mix(BG, HILITE_COL, inten), width=max(2, int(wd * S)), joint="curve")
        # la table
        lift = table_lift(T)
        sg = sag_at(T) if 49.8 <= T < 54.5 else 0.0
        top = [(x, -lift + sg * math.sin(math.pi * x / TABLE_X1)) for x in np.linspace(0, TABLE_X1, 24)]
        tt = max(TABLE_T, 12.0 / cam.s) if wide else TABLE_T
        plank = top + [(x, y + tt) for x, y in top[::-1]]
        dr.polygon(cam.pts(plank), fill=TABLE_COL)
        dr.line(cam.pts(top), fill=TABLE_EDGE, width=max(2, int(cam.L(5))))
        lw = max(LEG_W, 6.0 / cam.s) if wide else LEG_W
        for lx in LEGS:
            fy = floor_y(lx + LEG_W / 2)
            dr.rectangle([*cam.X(lx + LEG_W / 2 - lw / 2, TABLE_T - lift), *cam.X(lx + LEG_W / 2 + lw / 2, fy)], fill=LEG_COL)
        ccx, ccy, ca_ = cale_state(T)
        cw, ch = (CALE[2] - CALE[0]) / 2, -CALE[1] / 2
        cpts = [(ccx + dx * math.cos(ca_) - dy * math.sin(ca_), ccy + dx * math.sin(ca_) + dy * math.cos(ca_))
                for dx, dy in ((-cw, -ch), (cw, -ch), (cw, ch), (-cw, ch))]
        dr.polygon(cam.pts(cpts), fill=CALE_COL)
        sfill = (150, 178, 215, 150) if wide else GLASS_FILL
        if st["phase"] in ("in", "stuck"):
            pose = st["pose"]
            dr.polygon(cam.pts(poly_world(pose, POLYS[1])), fill=INTERIOR)
            b = st["ball"]
            if b["mode"] == "local":
                X, Y = to_world(pose, b["u"], b["v"])
                r, dpt = b["r"], b["depth"]
                nx, ny = to_world((0, 0, pose[2]), b["n"][0], b["n"][1])
                ang = math.atan2(ny, nx)
                dr.polygon(cam.pts(ellipse_pts(X, Y, (r - dpt) * pk, (r + 0.6 * dpt) * pk, ang)), fill=hc)
                face_at(dr, *cam.X(X, Y), cam.L(r - dpt), gz, b.get("spin"))
            else:
                self.draw_squeeze(dr, cam, pose, b, gz)
            draw_glass_front(dr, dra, cam, pose, POLYS)
            return
        b = st["ball"]
        x, y, R = b["u"], b["v"], b["r"]
        dpt, n = b.get("depth", 0.0), b.get("n", (0.0, -1.0))
        ang = math.atan2(n[1], n[0])
        if st["phase"] == "free":
            fpose = st["fpose"]
            dr.polygon(cam.pts(poly_world(fpose, POLYS[1])), fill=INTERIOR)
            draw_glass_front(dr, dra, cam, fpose, POLYS, fill=sfill, min_px=mp)
            dr.polygon(cam.pts(ellipse_pts(x, y, (R - dpt) * pk, (R + 0.6 * dpt) * pk, ang)), fill=hc)
            face_at(dr, *cam.X(x, y), cam.L(R - dpt), gz)
            return
        pose = self.hat_pose(x, y, R, st["c"], st["a"], st["lift"])
        dr.polygon(cam.pts(poly_world(pose, POLYS[1])), fill=INTERIOR)
        u_in = st.get("u_in", max(UN - 20, UL - (1 - st["c"]) * R - 24))
        if st["lift"] < 4:
            plug = [(u, -h_in(u) + 1.5) for u in np.linspace(u_in, UL, 30)] + [(u, h_in(u) - 1.5) for u in np.linspace(UL, u_in, 30)]
            dr.polygon(cam.pts(poly_world(pose, plug)), fill=hc)
        dr.polygon(cam.pts(ellipse_pts(x, y, (R - dpt) * pk, (R + 0.6 * dpt) * pk, ang)), fill=hc)
        face_at(dr, *cam.X(x, y), cam.L(R - dpt), gz)
        draw_glass_front(dr, dra, cam, pose, POLYS, fill=sfill, min_px=mp)

    def draw_squeeze(self, dr, cam, pose, b, gz):
        """La boule arrière, la chair étirée le long de l'axe (jamais plus large que la
        boule), le front arrondi, et la tête dehors."""
        hc = base.HERO["color"]
        u_r, r_r, front = b["u_r"], b["r_r"], min(b["front"], UL)
        X, Y = to_world(pose, u_r, 0.0)
        dr.ellipse([*cam.X(X - r_r, Y - r_r), *cam.X(X + r_r, Y + r_r)], fill=hc)
        if front > u_r + 2:
            us = np.linspace(u_r, front, 40)
            hw = [min(h_in(u) - 1.5, r_r) for u in us]
            sau = [(u, -h) for u, h in zip(us, hw)] + [(u, h) for u, h in zip(us[::-1], hw[::-1])]
            dr.polygon(cam.pts(poly_world(pose, sau)), fill=hc)
            hf = hw[-1]
            if b["front"] < UL - 1:
                FX, FY = to_world(pose, front, 0.0)
                dr.ellipse([*cam.X(FX - hf, FY - hf), *cam.X(FX + hf, FY + hf)], fill=hc)
        if b["rh"] > 2:
            hx, hy = b.get("head") or head_center(pose, b["rh"])
            r = b["rh"]
            dr.ellipse([*cam.X(hx - r, hy - r), *cam.X(hx + r, hy + r)], fill=hc)
            if b["face"] == "head":
                face_at(dr, *cam.X(hx, hy), cam.L(r), gz)
        if b["face"] == "front":
            fu = max(u_r, front - 0.6 * min(h_in(front) - 1.5, r_r))
            FX, FY = to_world(pose, fu, 0.0)
            face_at(dr, *cam.X(FX, FY), cam.L(min(h_in(fu) - 2, r_r) * 0.95), gz)


# ================================================================== branchement moteur
SCENE = {}


def scene_for(cfg):
    if "s" not in SCENE:
        SCENE["s"] = Scene(cfg)
    return SCENE["s"]


class Part(Chapter):
    idx = 0
    exit_ok = True
    bodies_exit_ok = True
    WIN = [(0.0, 6.0, 2.02), (6.0, END, 57.75)]

    def setup(self):
        self.sc = scene_for(self.cfg)
        a, b, c = self.WIN[self.idx]
        self.chute_abs = c
        self.hold_s = b - c
        self.abs0 = a
        self.prevT = None
        self.title = None
        self.R = 28.0
        self.bx, self.by, self.on = 500.0, 900.0, "air"

    def step(self, dt):
        self.t += dt
        T = self.abs0 + self.t
        evs = []
        lo = self.prevT if self.prevT is not None else T - dt
        for th in self.sc.w.p.hits:
            if lo < th <= T:
                evs.append(("hit", "floor"))
        self.prevT = T
        if T >= self.chute_abs - 1e-9:
            self.finish("CHUTE")
        return evs

    def snapshot(self):
        T = self.abs0 + self.t
        return {"T": T, "t": self.t, "end": self.end_t, "on": "air", "bx": 0, "by": 0}

    # ---- ce que le contrôle mesure, en coordonnées de l'image
    def _cam(self, T):
        return self.sc.camera(T, 1.0)

    def hero(self, s):
        T = s["T"]
        cam = self._cam(T)
        st = self.sc.state(T)
        x, y, r, _ = self.sc.ball_world(T, st)
        X, Y = cam.scr(x, y)
        return (X, Y, r * cam.s)

    def solids(self, s):
        T = s["T"]
        sc = self.sc
        cam = self._cam(T)
        st = sc.state(T)
        out = []
        P = lambda pts: ("poly", [cam.scr(x, y) for x, y in pts])
        for band in (GPOLYS[2], GPOLYS[3]):
            out.append(P(poly_world(GIANT, band)))
        lift = table_lift(T)
        sg = sag_at(T) if 49.8 <= T < 54.5 else 0.0
        top = [(x, -lift + sg * math.sin(math.pi * x / TABLE_X1)) for x in np.linspace(0, TABLE_X1, 24)]
        out.append(P(top + [(x, y + TABLE_T) for x, y in top[::-1]]))
        ccx, ccy, ca_ = cale_state(T)
        cw, ch = (CALE[2] - CALE[0]) / 2, -CALE[1] / 2
        out.append(P([(ccx + dx * math.cos(ca_) - dy * math.sin(ca_), ccy + dx * math.sin(ca_) + dy * math.cos(ca_))
                      for dx, dy in ((-cw, -ch), (cw, -ch), (cw, ch), (-cw, ch))]))
        squeezing = st["phase"] in ("in", "stuck") and st["ball"]["mode"] == "squeeze"
        attached = squeezing or st["phase"] in ("hat", "stuck") or (st["phase"] == "free" and (T < sc.t_pop + 0.3 or sc.t_chase <= T < sc.t_chase + 0.3))
        if not attached:
            pose = sc.small_pose(T, st)
            for band in (POLYS[2], POLYS[3]):
                out.append(P(poly_world(pose, band)))
        return out

    def bodies(self, s):
        T = s["T"]
        if self.sc.t_rev0 - 0.05 <= T < self.sc.t_rev1 + 0.05:
            return []                      # la caméra recule de plusieurs fois en 1,8 s : rien ne bouge que l'image
        s0, s1 = self.sc.cam_at(T - 0.05)[2], self.sc.cam_at(T + 0.05)[2]
        if abs(math.log(s1 / s0)) / 0.1 > 0.9:
            return []                      # zoom rapide de la caméra : l'image bouge, pas les objets
        cam = self._cam(T)
        st = self.sc.state(T)
        ccx, ccy, ca_ = cale_state(T)
        CX, CY = cam.scr(ccx, ccy)
        out = [("cale", CX, CY, ca_)]
        if st["phase"] != "hat":
            # plantée sur sa tête, la bouteille fait corps avec Bounce : elle n'est suivie
            # comme objet libre que lorsqu'elle ne tient à rien
            pose = self.sc.small_pose(T, st)
            X, Y = cam.scr(*to_world(pose, 430.0, 0.0))
            out.append(("bouteille", X, Y, pose[2]))
        return out

    def focus(self, s):
        T = s["T"]
        cam = self._cam(T)
        if self.idx == 0:
            X, Y, r = self.hero(s)
            return (X - r, Y - r, X + r, Y + r)
        pts, _, _ = self.sc.reflection(T, cam)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def draw(self, dr, s, t, S):
        dr.rectangle([0, 0, W * S, H * S], fill=BG)
        self.sc.draw(dr, s["T"], S)


def make(i):
    class P_(Part):
        pass
    P_.idx = i
    P_.__name__ = f"Part{i + 1}"
    return P_


CHAPTERS = [(make(i), {"chapter_max_s": 80.0}) for i in range(2)]

DEFAULTS = {
    "ball_r": 31.0, "gravity": G,
    "hook_text_s": 3.0, "hook_top": 0.075, "hook_font_size": 96, "hook_width": 0.72,
    "end_hold_s": 0.02, "min_duration_s": 30.0, "scene_top": 0.2,
}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        SCENE.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)

    def _open(self, i):
        s = self.sims[i]
        s.abs0 = self.t
        super()._open(i)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
