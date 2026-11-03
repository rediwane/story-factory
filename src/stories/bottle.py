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
END = 63.6

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
TABLE_X1 = 1100.0
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


POSE0 = pose_on_table(930.0, A0)
_fc = to_world(POSE0, -GL, HB + GL)
CALE = (_fc[0] - 110.0, _fc[1] + 2, _fc[0] + 90.0)
# la géante, elle aussi sur sa cale, sur une grande table
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
        self.hops = []            # sauts de la bouteille sur sa cale (t, haut, avance, durée)

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
        self.vel = (0.0, 0.0)

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
        self.v0 = (vx, vy)

    def touch(self, wpt, n, r_new, amp=0.22, dc=0.07, hop=None, voiced=True, keep=None):
        """Le contact : il s'écrase sur la paroi, gonfle d'un cran (à la sortie du choc), repart."""
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
            st = self.state(wx + nx * (rho - depth), wy + ny * (rho - depth), rho, depth, (nx, ny))
            if keep:
                st.update(keep)
            return st
        self.p.add(T0, T0 + dc, f)
        self.T = T0 + dc
        self.r = r_new
        self.C = (wx + nx * r_new, wy + ny * r_new)


class Local(Mover):
    """Dans la bouteille : repère local (u, v), gravité inclinée de A0."""

    def __init__(self, plan, T, C, r):
        super().__init__(plan, T, C, r, G * SA, G * CA, "local")

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

    def roll(self, t1, s0, v0, acc):
        r, T0 = self.r, self.T

        def f(T):
            tau = T - T0
            s = s0 + v0 * tau + 0.5 * acc * tau * tau
            u, v = self.center("floor", s, r)
            return self.state(u, v, r)
        self.p.add(T0, t1, f)
        tau = t1 - T0
        self.s = s0 + v0 * tau + 0.5 * acc * tau * tau
        self.side = "floor"
        self.C = self.center("floor", self.s, r)
        self.T = t1

    def to(self, t1, side, s, spin=None):
        self.arc(t1, self.center(side, s, self.r), spin)
        self.side, self.s = side, s

    def hit(self, r_new, amp=0.22, dc=0.07, hop=None):
        w, n = self.wall(self.side, self.s)
        self.touch(w, n, r_new, amp, dc, hop)


# ------------------------------------------------------------------ phase A : dans la bouteille
def phase_a(p):
    L = Local(p, 0.0, None, 28.0)
    # 0 s : il roule déjà vers l'embouchure, à un corps du goulot
    L.roll(1.40, 548.0, 34.0, 22.0)
    # il regarde la caméra, puis le saut fait exprès, sur place
    L.to(2.04, "floor", L.s + 6.0)
    L.hit(39.0, amp=0.26, dc=0.08)                      # « Bounce » : il gonfle d'un coup
    # l'épaule le renvoie vers le fond ; il remonte la pente en zigzag
    L.to(2.58, "ceil", 505.0)
    L.hit(41.0)
    L.to(3.16, "floor", 420.0)
    L.hit(43.0)
    L.to(4.30, "floor", 285.0)
    L.hit(45.0)
    L.to(4.80, "ceil", 215.0)
    L.hit(47.0)
    L.to(5.36, "floor", 140.0)
    L.hit(49.0)
    # le fond de plein fouet : galette, il repart comme une flèche
    L.arc(6.15, (49.0, 6.0))
    L.side, L.s = "fond", 6.0
    L.hit(51.0, amp=0.45, dc=0.16)
    L.arc(6.92, (UN + 6.0, 1.5))
    return L


def phase_neck(p, L):
    """Dans le goulot : il tient tout juste, rebondit haut-bas de plus en plus vite en
    gonflant (il s'aplatit en ovale), avance d'un demi-corps, bute contre la lèvre et jaillit."""
    T0, u0 = L.T, L.C[0]
    hits = [7.16, 7.94, 8.72, 9.14, 9.50]
    radii = [52.5, 54.5, 56.5, 58.5, 60.5]
    t_lip = 10.28
    u_lip = UL + 8.0 - 60.5 * 60.5 / HN * 1.08       # le front dépasse d'un doigt
    r_start = L.r

    def u_of(T):
        k = lin((T - T0) / (t_lip - T0))
        return u0 + (u_lip - u0) * (1 - (1 - k) ** 1.7)

    def r_of(T):
        rr = r_start
        for th, rn in zip(hits, radii):
            if T >= th:
                rr = rn if T >= th + 0.08 else rr + (rn - rr) * ease((T - th) / 0.08)
        if T >= t_lip:
            rr = 60.5 + 2.5 * ease((T - t_lip) / 0.08)
        return rr

    def f(T):
        u = u_of(T)
        rr = r_of(T)
        depth, side = 0.0, 1.0
        for k, th in enumerate(hits + [t_lip]):
            if th - 0.02 <= T < th + 0.1:
                depth = (0.18 if th != t_lip else 0.1) * math.sin(math.pi * lin((T - th + 0.02) / 0.12))
                side = 1.0 if k % 2 == 0 else -1.0
        hcap = h_in(u) - 0.5
        b = min(rr, hcap)
        a = rr * rr / b
        v = 0.0
        if rr < hcap:
            ph = sum(1 for th in hits if T >= th)
            v = (hcap - rr) * (1.0 if ph % 2 == 0 else -1.0) * 0.85
        b2 = b * (1 - depth)
        v += side * (b - b2)
        if T >= t_lip:
            a *= 1 - 0.1 * math.sin(math.pi * lin((T - t_lip) / 0.12))
        return {"mode": "neck", "u": u, "v": v, "a": a * (1 + 0.4 * depth), "b": b2, "r": rr, "spin": None}
    p.add(T0, t_lip + 0.1, f)
    p.hits.extend(hits + [t_lip])
    # il jaillit en arrière, en tournant, comme un noyau qu'on presse
    t_out, u_a, rr = t_lip + 0.1, u_lip, 63.0
    t_b, u_b = t_out + 0.26, 560.0

    def g(T):
        k = (T - t_out) / (t_b - t_out)
        u = u_a + (u_b - u_a) * (1 - (1 - k) ** 1.5)
        hc = h_in(u) - 0.5
        b = min(rr, hc)
        return {"mode": "neck", "u": u, "v": 0.0, "a": rr * rr / b, "b": b, "r": rr, "spin": -10.0 * (T - t_out)}
    p.add(t_out, t_b, g)
    L.T, L.C, L.r = t_b, (u_b, 0.0), rr
    L.to(11.22, "floor", 300.0, spin=(-10.0 * (t_b - t_out), -7.0))
    L.hit(64.5)
    return L


def phase_b2(p, L):
    """La place diminue : rebonds courts entre le bas et le haut ; chaque choc fait
    sauter la bouteille sur sa cale et la pousse vers le bord de la table."""
    seq = []
    t, r, k = 12.02, 64.5, 0
    s_pos = [330.0, 350.0, 368.0, 390.0, 400.0, 405.0, 380.0, 360.0, 340.0, 360.0, 380.0, 395.0, 375.0, 355.0, 340.0,
             362.0, 380.0, 392.0, 372.0, 352.0, 332.0, 320.0]
    while t < 22.0:
        for (dt, side) in ((0.0, "floor"), (0.40, "ceil"), (0.40, "floor")):
            t += dt
            r += 1.2
            seq.append((t, side, s_pos[k % len(s_pos)], r))
            k += 1
        t += 0.80
    for (t, side, s, r) in seq:
        L.to(t, side, s)
        hop = (42.0, 6.0, 0.34) if side == "ceil" else (14.0, 2.0, 0.22)
        L.hit(r, hop=hop)
    # il remonte vers le fond en deux bonds, en regardant le goulot puis la caméra
    L.to(seq[-1][0] + 0.62, "floor", 215.0)
    L.hit(r + 1.0)
    L.arc(seq[-1][0] + 1.32, (r + 1.0, 24.0))
    L.side, L.s = "fond", 24.0
    L.hit(r + 2.0, amp=0.5, dc=0.16)
    return L


# ------------------------------------------------------------------ coincé dans le goulot
T_RAM, T_JUMP, T_CALL = 24.56, 25.36, 30.62
FACE_HITS = (32.50, 33.30, 34.66, 35.48)
RH = [(24.40, 0.0), (T_RAM, 60.0), (T_JUMP, 63.0), (26.86, 66.0), (27.68, 69.0), (28.66, 72.0), (29.74, 75.0),
      (T_CALL, 79.0), (FACE_HITS[0], 91.0), (FACE_HITS[1], 104.0), (FACE_HITS[2], 120.0), (FACE_HITS[3], 138.0)]


def rh_at(T):
    v = RH[0][1]
    for (t, r) in RH:
        if T >= t:
            v = r if T >= t + 0.1 else v + (r - v) * ease((T - t) / 0.1)
    return v


def flat_pose(xc, rh):
    """Couchée sur la table, sans cale : elle repose sur le bas de son épaule (u = LB) et
    sur la tête de Bounce, qui dépasse de l'embouchure."""
    def make(a):
        px, py = to_world((0, 0, a), LB, h_out(LB))
        return (xc - px, -py, a)

    def head_bottom(a):
        pose = make(a)
        mx, my = to_world(pose, UL, 0.0)
        return my + 0.72 * rh * math.sin(a) + rh
    lo, hi = -0.2, 0.7
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if head_bottom(m) < 0:
            lo = m
        else:
            hi = m
    return make(0.5 * (lo + hi))


def edge_pose(xc):
    """La bouteille couchée, embouchure au ras du bord : elle repose sur son épaule et
    sur l'arête de la table (sous le goulot), la tête au-dessus du vide."""
    def make(a):
        px, py = to_world((0, 0, a), LB, h_out(LB))
        return (xc - px, -py, a)
    best = None
    for k in range(0, 400):
        a = k * 0.002
        pose = make(a)
        ok = True
        for u in np.linspace(LB, UL, 60):
            x, y = to_world(pose, u, h_out(u))
            if x <= TABLE_X1 and y > 0.5:
                ok = False
                break
        if not ok:
            break
        best = pose
    return best


CORNER = (TABLE_X1, 0.0)
U_PIVOT = 742.0


def hang_pose(a):
    """En équilibre sur l'arête, goulot vers le bas : l'arête touche la paroi basse en U_PIVOT."""
    px, py = to_world((0, 0, a), U_PIVOT, h_out(U_PIVOT))
    return (CORNER[0] - px, CORNER[1] - py, a)


def head_center(pose, rh, hang=0.0, swing=0.0, c=0.72):
    a = pose[2]
    mx, my = to_world(pose, UL, 0.0)
    dx, dy = math.cos(a), math.sin(a) + hang
    L = math.hypot(dx, dy)
    dx, dy = dx / L, dy / L
    cs, sn = math.cos(swing), math.sin(swing)
    dx, dy = dx * cs - dy * sn, dx * sn + dy * cs
    return mx + c * rh * dx, my + c * rh * dy


def hang_angle(rh):
    """Plus la tête grossit, plus elle repousse la face de la table : la bouteille se redresse."""
    lo, hi = 0.35, 1.25
    f = lambda a: head_center(hang_pose(a), rh, 1.0)[0] - rh - TABLE_X1
    if f(hi) > 0:
        return hi
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if f(m) > 0:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


class World:
    def __init__(self, cfg):
        self.cfg = cfg
        p = Plan()
        L = phase_a(p)
        L = phase_neck(p, L)
        L = phase_b2(p, L)
        self.p, self.L = p, L
        self.t_ram0 = L.T
        self.ram_from = L.C
        self.r_ram = L.r
        self.stuck_hits = [T_RAM, T_JUMP, 26.86, 27.68, 28.66, 29.74, T_CALL] + list(FACE_HITS) + [37.20]
        p.hits.extend(self.stuck_hits)
        self.build_table()
        p.hits.sort()

    # ---- la bouteille, de 0 à 38 s
    def cale_pose(self, T):
        x, y, a = POSE0
        dx = dy = 0.0
        for (th, ddy, ddx, dur) in self.p.hops:
            if T >= th:
                k = lin((T - th) / dur)
                dx += ddx * ease(k)
                dy -= ddy * 4 * k * (1 - k)
        return (x + dx, y + dy, a)

    def bottle_pose(self, T):
        if T < T_JUMP:
            return self.cale_pose(T)
        p_cale = self.cale_pose(T_JUMP)
        xc0 = to_world(p_cale, LB, h_out(LB))[0]
        hops = [(T_JUMP, 0.55, 60.0, 64.0), (26.86, 0.38, 40.0, 22.0), (27.68, 0.38, 40.0, 22.0),
                (28.66, 0.42, 46.0, 24.0), (29.74, 0.6, 70.0, 60.0)]
        xc = xc0
        prev = p_cale
        for k, (th, dur, lift, adv) in enumerate(hops):
            if T < th:
                break
            if adv is None:
                pass
            if k < 4:
                tgt = flat_pose(xc + adv, rh_at(th + dur))
                if T < th + dur:
                    return self.blend(prev, tgt, (T - th) / dur, lift)
                xc += adv
                prev = tgt
            else:
                tgt = edge_pose(xc + adv)
                self._edge = tgt
                if T < th + dur:
                    return self.blend(prev, tgt, (T - th) / dur, lift)
                prev = tgt
        if T < 29.74:
            return flat_pose(xc, rh_at(T))
        if T < 30.62:
            return prev
        # le saut fait exprès : la bouteille passe l'arête et bascule
        a_h = hang_angle(rh_at(31.6))
        if T < 31.6:
            k = (T - 30.62) / 0.98
            e = prev
            h = hang_pose(a_h)
            kk = ease(k)
            x = lerp(e[0], h[0], kk)
            y = lerp(e[1], h[1], kk) - 18 * math.sin(math.pi * min(1, k * 1.6))
            a = lerp(e[2], h[2], kk ** 1.4)
            return (x, y, a)
        if T < 37.2:
            # en équilibre sur l'arête, elle oscille à chaque choc de la tête contre la table,
            # puis s'immobilise : le temps du suspens avant la catapulte
            a = hang_angle(rh_at(T))
            teeter = 0.0
            for th in FACE_HITS:
                u = T - th
                if u >= 0:
                    teeter += 0.07 * math.exp(-u / 0.45) * math.sin(2 * math.pi * 1.6 * u)
            if T < FACE_HITS[-1]:
                teeter += 0.025 * math.sin(2 * math.pi * 0.9 * (T - 31.6)) * lin((T - 31.6) / 0.4)
            return hang_pose(a - teeter)
        return None

    def blend(self, p0, p1, k, lift):
        kk = ease(k)
        return (lerp(p0[0], p1[0], kk), lerp(p0[1], p1[1], kk) - lift * 4 * lin(k) * (1 - lin(k)), lerp(p0[2], p1[2], kk))

    # ---- de 38 s à la fin : sur la table, la bouteille sur la tête, puis le sol
    def build_table(self):
        p = self.p
        M = Mover(p, 0.0, (0, 0), 0.0, 0.0, G, "world")
        self.M = M
        # la catapulte : la tête remonte le long de la face de la table, puis vole
        a_end = hang_angle(rh_at(37.0))
        pose_end = hang_pose(a_end)
        hx, hy = head_center(pose_end, rh_at(37.0), 1.0)
        self.cat0 = (hx, hy, a_end)
        R = 146.0
        self.R_land = R
        t_up, t_land = 37.52, 38.30
        top = (TABLE_X1 + R + 4, -R - 30)
        self.cat_up = (37.2, t_up, (hx, hy), top)
        land = (720.0, -R)
        M.T, M.C, M.r = t_up, top, R
        M.arc(t_land, land)
        self.hat_from = t_up
        M.touch((land[0], 0.0), (0.0, -1.0), 150.0, amp=0.3, dc=0.14)
        seq = [  # (t, x, r, amp)
            (40.00, 660.0, 156.0, 0.22), (41.72, 560.0, 300.0, 0.3), (43.50, 520.0, 318.0, 0.22),
            (44.70, 540.0, 336.0, 0.25), (46.20, 600.0, 352.0, 0.2), (47.02, 640.0, 368.0, 0.2),
            (47.84, 1080.0, 390.0, 0.22), (48.64, 1090.0, 410.0, 0.26), (49.66, 640.0, 440.0, 0.3),
            (51.00, 720.0, 464.0, 0.3), (52.36, 820.0, 486.0, 0.3)]
        for (t, x, r, amp) in seq:
            M.arc(t, (x, -M.r))
            M.touch((x, 0.0), (0.0, -1.0), r, amp=amp, dc=0.12 if amp < 0.3 else 0.2)
        # le rebond immense : il sort par le haut, retombe à côté de la table, jusqu'au sol
        self.t_floor = 55.50
        seq = [(55.50, 2300.0, 510.0, 0.5, 0.22), (56.86, 3000.0, 528.0, 0.22, 0.12), (58.04, 3600.0, 546.0, 0.22, 0.12),
               (60.25, 4300.0, 580.0, 0.2, 0.12), (61.70, 4800.0, 598.0, 0.34, 0.16), (62.50, 5150.0, 614.0, 0.2, 0.12)]
        # le sol penche : il rebondit vers le bas de la pente, vers le goulot de la géante
        for (t, x, r, amp, dc) in seq:
            wpt, n = giant_floor(x, M.r)
            M.arc(t, (wpt[0] + n[0] * M.r, wpt[1] + n[1] * M.r))
            M.touch(wpt, n, r, amp=amp, dc=dc)
        wpt, n = giant_floor(5700.0, M.r)
        M.arc(64.4, (wpt[0] + n[0] * M.r, wpt[1] + n[1] * M.r))

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


def draw_glass_front(dr, dra, cam, pose, polys, hil=1.0, line_col=GLASS_LINE, fill=GLASS_FILL, k=1.0, hpts=None):
    outer, inner, top, bot = polys
    w = max(2, int(cam.L(GL * k) * 0.42))
    if k == 1.0:
        w = max(w, int(3.0 * cam.S))      # la petite bouteille reste lisible dans le plan large
    for band in (top, bot):
        dra.polygon(cam.pts(poly_world(pose, band)), fill=fill)
    dr.line(cam.pts(poly_world(pose, outer + outer[:1])), fill=line_col, width=w, joint="curve")
    ins = [q for q in inner if q[0] <= UL * k + 0.1]
    n2 = len(ins) // 2
    lc = dim(line_col, 0.8)
    dr.line(cam.pts(poly_world(pose, ins[:n2])), fill=lc, width=max(2, w - 1), joint="curve")
    dr.line(cam.pts(poly_world(pose, ins[n2:])), fill=lc, width=max(2, w - 1), joint="curve")
    # la lèvre de l'embouchure : un anneau de verre plus épais
    for sg in (-1, 1):
        ring = [(UL0 - 2, sg * HL), (UL, sg * HL), (UL, sg * LIPO), (UL0 - 2, sg * LIPO)]
        dr.polygon(cam.pts(poly_world(pose, [(u * k, v * k) for u, v in ring])), fill=dim(line_col, 0.75))
    if hil > 0:
        col = mix(BG, HILITE_COL, hil)
        dr.line(cam.pts(poly_world(pose, hpts or HILITE)), fill=col, width=max(2, int(cam.L(HB * k * 0.085)), int(2.0 * cam.S) if k == 1.0 else 0), joint="curve")


def face_at(dr, X, Y, r, gaze=(0.0, 0.0), spin=None):
    gx, gy = gaze
    if spin is not None:
        base.HERO["tilt"] = spin
    base.hero_face(dr, X + gx * r * 0.34, Y + gy * r * 0.34, r * 0.92)
    if base.HERO["pos"] is None:
        base.HERO["pos"] = (X, Y)


GAZE = [  # (t, gx, gy) : 0,0 = la caméra
    (0.0, 0.8, 0.25), (0.75, 0.8, 0.25), (1.0, 0.0, 0.0), (2.2, 0.0, 0.0), (2.4, -0.6, 0.0),
    (6.1, -0.6, 0.0), (6.4, 0.7, 0.1), (11.0, 0.5, 0.2), (12.0, 0.0, 0.0),
    (21.9, 0.0, 0.0), (22.3, 0.85, 0.3), (22.95, 0.85, 0.3), (23.2, 0.0, 0.0), (23.7, 0.0, 0.0), (23.9, 0.8, 0.0),
    (25.0, 0.0, 0.0), (28.6, 0.0, 0.0), (28.9, 0.6, 0.6), (29.5, 0.6, 0.6), (29.85, 0.0, 0.0),
    (30.9, 0.0, 0.0), (31.2, -0.5, 0.0), (35.5, -0.5, 0.0), (35.8, 0.0, 0.0),
    (40.2, 0.0, 0.0), (40.4, 0.0, -0.8), (41.4, 0.0, -0.8), (41.6, 0.0, 0.0),
    (47.95, 0.0, 0.0), (48.12, 0.5, 0.85), (48.55, 0.5, 0.85), (48.8, 0.0, 0.0),
    (53.8, 0.0, 0.0), (54.05, 0.2, 0.85), (55.4, 0.2, 0.85), (55.7, 0.0, 0.0),
    (59.4, 0.0, 0.0), (59.75, 0.0, -0.8), (61.45, 0.0, -0.8), (61.65, 0.0, 0.0),
]


def gaze_at(T):
    gx = keyed([(t, a) for t, a, b in GAZE], T)
    gy = keyed([(t, b) for t, a, b in GAZE], T)
    return gx, gy


def sag_at(T):
    """Le plateau plie sous les rebonds lourds, puis vibre."""
    v = 0.0
    for (th, amp) in ((49.66, 26.0), (51.00, 30.0), (52.36, 34.0)):
        u = T - th
        if u >= 0:
            v += amp * math.exp(-u / 0.45) * math.cos(2 * math.pi * 3.2 * u) if u > 0.2 else amp * math.sin(math.pi * u / 0.4)
    return v


def table_lift(T):
    """La table entière tressaute sur ses pieds (double rebond)."""
    v = 0.0
    for th in (46.20, 47.02):
        u = T - th - 0.06
        if 0 <= u < 0.26:
            v += 14.0 * math.sin(math.pi * u / 0.26)
    return v


T_CALE = 49.70


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
    t_off = (cx + 0.15 * w) / -vx            # son centre passe le bord : elle bascule
    if u < t_off:
        return cx + vx * u, cy, 0.0
    tau = u - t_off
    x = cx + vx * u
    y = cy + 0.5 * G * tau * tau
    a = -2.6 * tau
    # elle touche le sol : posée à plat sur la pente (une face contre le sol)
    a_rest = A0 - math.pi / 2
    gy = floor_y(x) - 0.5 * w / CA
    if y >= gy:
        # instant du contact, puis elle se couche en 0,35 s
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
        for k in range(0, 50):
            tl = 59.25 + 0.01 * k
            b1 = w.ball(tl)
            c1 = (b1["u"], b1["v"] - 1.0 * b1["r"] - (UL - 430.0))
            T = tl - self.t_pop
            vx = (c1[0] - self.f_c0[0]) / T
            vy = (c1[1] - self.f_c0[1] - 0.5 * G * T * T) / T
            ta = -vy / G
            xa, ya = self.f_c0[0] + vx * ta, self.f_c0[1] + vy * ta + 0.5 * G * ta * ta
            gap = (ya - 430.0) - ceil_y(xa)
            if best is None or abs(gap - 12.0) < abs(best[0] - 12.0):
                best = (gap, tl, vx, vy, c1)
        gap, tl, vx, vy, c1 = best
        self.t_bl, self.f_v = tl, (vx, vy)
        self.f_spin = 2 * math.pi * 3 / (tl - self.t_pop)
        self.w.p.hits.append(tl)
        self.w.p.hits.sort()
        self.t_chase = 61.72
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
        cx = c0[0] - 520.0 * tau
        cy = c0[1] - 1450.0 * tau + 0.5 * G * tau * tau
        a = math.pi / 2 - 6.0 * tau
        return (cx - 430.0 * math.cos(a), cy - 430.0 * math.sin(a), a)

    # ---- l'état à l'instant T
    def state(self, T):
        w = self.w
        b = dict(w.ball(T))
        if T < w.t_ram0:
            return {"phase": "in", "pose": w.bottle_pose(T), "ball": b}
        if T < 37.2:
            pose = w.bottle_pose(T)
            return {"phase": "stuck", "pose": pose, "ball": self.stuck_ball(T, pose)}
        st = self.hat_state(T, b)
        if self.t_pop <= T < self.t_bl or T >= self.t_chase + 0.02:
            st["phase"] = "free"
            st["fpose"] = self.flight_pose(T)
        return st

    def stuck_ball(self, T, pose):
        w = self.w
        rh = rh_at(T)
        if T < T_JUMP:
            hang = -0.35
        elif T < T_CALL:
            hang = 0.0
        else:
            hang = keyed([(T_CALL, 0.0), (31.4, 1.0)], T)
        swing = 0.12 * math.sin(2 * math.pi * 2.3 * T) + 0.08 * math.sin(2 * math.pi * 3.7 * T + 1.0)
        if 31.4 <= T < 37.2:
            for th in FACE_HITS:
                u = T - (th - 0.25)
                if 0 <= u < 0.6:
                    swing += 0.22 * math.sin(math.pi * u / 0.6) * (1 if rh < 100 else 0.3)
        hx, hy = head_center(pose, rh, hang, swing)
        if 31.4 <= T < 37.2:
            hx = max(hx, TABLE_X1 + rh * 0.985)
        if hx - 0.3 * rh < TABLE_X1:
            hy = min(hy, -rh)              # elle repose sur la table
        # ce qui reste dedans : une boule à l'entrée de l'épaule, tirée vers le goulot à
        # mesure que la tête grossit dehors
        k_in = lin((rh - 60.0) / (138.0 - 60.0))
        u_r = lerp(560.0, 712.0, ease(k_in))
        r_r = min(lerp(min(w.r_ram, h_in(560.0) - 2), 30.0, ease(k_in)), h_in(u_r) - 2)
        m = lin((T - w.t_ram0) / (T_RAM - w.t_ram0))
        if m < 1.0:
            u0, v0 = w.ram_from
            uc = lerp(u0, 560.0, ease(m * 2))
            front = lerp(uc, UL + 0.72 * 60.0 * 2, ease((m - 0.25) / 0.75))
            return {"mode": "stuck", "u_rear": uc, "v_rear": lerp(v0, 0.0, ease(m * 2)),
                    "r_rear": lerp(w.r_ram, r_r, ease(m * 2)), "u_in": uc, "u_front": front, "rh": rh,
                    "head": head_center(pose, rh, hang, swing)}
        return {"mode": "stuck", "u_rear": u_r, "v_rear": 0.0, "r_rear": r_r, "u_in": u_r, "u_front": UL,
                "rh": rh, "head": (hx, hy)}

    def hat_state(self, T, b):
        w = self.w
        t0, t1, (hx, hy), (tx, ty) = w.cat_up
        if T < t1:
            k = ease((T - t0) / (t1 - t0))
            R = lerp(rh_at(T), w.R_land, lin((T - t0) / (t1 - t0)))
            b = {"mode": "world", "u": lerp(hx, tx, k ** 2), "v": lerp(hy, ty, k), "r": R, "depth": 0.0, "n": (0.0, -1.0)}
        if 49.6 <= T < 52.4 and b.get("depth", 0) > 0:
            b["v"] += sag_at(T)
        a_c = w.cat0[2]
        wob = 0.0
        if T < 38.3:
            a = lerp(a_c, math.pi / 2, ease((T - 37.2) / 1.1))
            c = lerp(0.72, 0.15, ease((T - 38.1) / 0.25)) if T > 38.1 else 0.72
        else:
            for (th, amp) in [(38.3, 0.16), (40.0, 0.22), (41.72, 0.2), (43.5, 0.18), (45.42, 0.3),
                              (46.2, 0.14), (47.02, 0.16), (47.84, 0.2), (48.64, 0.2), (49.66, 0.12), (51.0, 0.12),
                              (52.36, 0.1), (55.0, 0.0), (59.5, 0.25), (60.25, 0.15), (61.0, 0.0)]:
                u = T - th
                if u >= 0:
                    wob += amp * math.exp(-u / 0.7) * math.sin(2 * math.pi * 1.3 * u)
            a = math.pi / 2 + wob
            c = keyed([(38.3, 0.15), (41.72, 0.15), (41.98, 0.56)], T) if T < 59.0 else keyed([(self.t_bl, 1.0), (self.t_bl + 0.16, 0.40)], T)
        st = {"phase": "hat", "ball": b, "c": c, "a": a, "lift": 0.0}
        if 44.82 <= T < 45.42:
            u = (T - 44.82) / 0.60
            st["lift"] = 300.0 * 4 * u * (1 - u)
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
        """(x, y, r) de Bounce dans le monde : la tête quand il est coincé."""
        st = st or self.state(T)
        b = st["ball"]
        if st["phase"] == "in":
            X, Y = to_world(st["pose"], b["u"], b["v"])
            r = b["r"] - b.get("depth", 0.0) if b["mode"] == "local" else b["b"]
            return X, Y, r, b["r"]
        if st["phase"] == "stuck":
            if b["u_front"] >= UL - 1:
                return b["head"][0], b["head"][1], b["rh"], b["rh"]
            X, Y = to_world(st["pose"], min(b["u_front"], UL) - 40, 0.0)
            return X, Y, HN, HN
        return b["u"], b["v"], b["r"] - b.get("depth", 0.0), b["r"]

    # ---- la caméra
    def giant_view(self):
        pts = [to_world(GIANT, u * KG, v * KG) for u, v in POLYS[0]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        bx0, by0, bx1, by1 = 34.0, 470.0, 930.0, 1500.0
        s = min((bx1 - bx0) / (x1 - x0), (by1 - by0) / (y1 - y0))
        cx = (x0 + x1) / 2 - ((bx0 + bx1) / 2 - W / 2) / s
        cy = (y0 + y1) / 2 - ((by0 + by1) / 2 - H / 2) / s
        return cx, cy, s

    def cam_target(self, T):
        st = self.state(T)
        X, Y, r, rfull = self.ball_world(T, st)
        tau = 0.3
        if st["phase"] == "in":
            s = (100 + 1.75 * rfull) / (2 * rfull)
            s0 = 2.45
            # l'ouverture : la balle à gauche, le goulot et l'embouchure à droite
            k = ease((T - 1.7) / 0.9)
            sx = lerp(185.0, 430.0, k)
            sy = lerp(1000.0, 1010.0, k)
            s = lerp(s0, s, k)
            if 11.3 <= T < 18.8:
                # la place diminue : on cadre la bouteille sur sa table, pour voir chaque saut
                cp = self.w.cale_pose(T)
                bx, by = to_world((cp[0], POSE0[1], cp[2]), 520.0, 70.0)
                s2 = 1.05
                kk = ease((T - 11.3) / 0.8)
                return lerp(X + (W / 2 - sx) / s, bx - 130, kk), lerp(Y + (H / 2 - sy) / s, by, kk), lerp(s, s2, kk), 0.35
            if 18.8 <= T:
                # la caméra recule : à droite de l'embouchure, la table s'arrête
                kk = ease((T - 18.8) / 1.4)
                s = lerp(1.05, 0.88, kk)
                cp = self.w.cale_pose(T)
                bx, by = to_world((cp[0], POSE0[1], cp[2]), 520.0, 70.0)
                cx = lerp(bx - 130, 600.0, kk)
                cy = lerp(by, by - 40, kk)
                return cx, cy, s, 0.35
            if 6.2 <= T < 7.1:
                tau = 0.12
            return X + (W / 2 - sx) / s, Y + (H / 2 - sy) / s, s, tau
        if st["phase"] == "stuck":
            pose = st["pose"]
            bx, by = to_world(pose, 430.0, 0.0)
            if T < 30.9:
                hx, hy = st["ball"]["head"]
                return hx - 230, hy - 60, 1.2, 0.4
            return 980.0, 60.0, lerp(0.9, 1.08, ease((T - 31.2) / 6.0)), 0.45
        # sur la table, la bouteille sur la tête
        if T < 41.72:
            return X + 40, Y - 330, 0.84, 0.35
        if T < 52.30:
            return 740.0, -330.0, 0.56, 0.6
        if T < 53.50:
            # il part par le haut : la caméra se rapproche du plateau, seul, qui vibre encore
            return 720.0, 430.0, 1.5, 0.12
        return X, Y - 100, 0.55, 0.25

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
        # le début reste cadré comme voulu (pas de lissage à l'image 0)
        # la révélation : suivre la bouteille qui monte, puis reculer jusqu'à la géante
        self.t_rev0, self.t_rev1 = self.t_pop + 0.40, self.t_pop + 1.12
        gx, gy, gs = self.giant_view()
        self.gview = (gx, gy, gs)
        i0 = int(self.t_pop * FPS)
        c_start = y[i0].copy()
        for i in range(i0, N):
            T = i * dt
            if T < self.t_rev0:
                fp = self.flight_pose(T)
                bx, by = to_world(fp, 430.0, 0.0)
                k = ease((T - self.t_pop) / (self.t_rev0 - self.t_pop))
                y[i] = (lerp(c_start[0], bx, 0.5 * k), lerp(c_start[1], by, 0.6 * k), c_start[2])
                c_rev = y[i].copy()
            else:
                k = ease((T - self.t_rev0) / (self.t_rev1 - self.t_rev0))
                ls = lerp(c_rev[2], math.log(gs), k)
                # le point fixe se déplace comme l'échelle, pour un recul régulier
                kk = (math.exp(-c_rev[2]) - math.exp(-ls)) / (math.exp(-c_rev[2]) - math.exp(-math.log(gs)) + 1e-9)
                y[i] = (lerp(c_rev[0], gx, kk), lerp(c_rev[1], gy, kk), ls)
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
        if T < self.t_rev0:
            return sty, 0.2, 26.0
        if T >= self.t_rev1:
            return true, 0.88, cam.L(HB * KG * 0.085) / cam.S
        kk = ease((T - self.t_rev0) / (self.t_rev1 - self.t_rev0))
        pts = [(lerp(a[0], b[0], kk), lerp(a[1], b[1], kk)) for a, b in zip(sty, true)]
        return pts, lerp(0.2, 0.88, kk), lerp(26.0, cam.L(HB * KG * 0.085) / cam.S, kk)

    def pop(self, T):
        """Le cran de gonflement se voit : juste après chaque choc, une petite bouffée."""
        k = 1.0
        for th in self.w.p.hits:
            u = T - th
            if 0.06 <= u < 0.30:
                k = max(k, 1.0 + 0.07 * math.sin(math.pi * (u - 0.06) / 0.24))
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
        # la grande table et la cale de la géante (on ne les voit qu'à la fin)
        gt = GTABLE_Y
        dr.rectangle([*cam.X(GFOND[0] - 9000, gt), *cam.X(GLIP[0] + 9000, gt + TABLE_T * KG)], fill=TABLE_COL)
        dr.rectangle([*cam.X(GFOND[0] - 110 * KG, GFOND[1] + 2 * KG), *cam.X(GFOND[0] + 90 * KG, gt)], fill=CALE_COL)
        # la géante : sa paroi basse est le sol
        draw_glass_front(dr, dra, cam, GIANT, GPOLYS, hil=0.0, k=KG, fill=(120, 150, 190, 40))
        pts, inten, wd = self.reflection(T, cam)
        sp = [(x * S, y * S) for x, y in pts]
        dr.line(sp, fill=mix(BG, HILITE_COL, inten * 0.55), width=max(2, int(wd * 1.8 * S)), joint="curve")
        dr.line(sp, fill=mix(BG, HILITE_COL, inten), width=max(2, int(wd * S)), joint="curve")
        # la table
        lift = table_lift(T)
        sg = sag_at(T) if 49.6 <= T < 54 else 0.0
        top = [(x, -lift + sg * math.sin(math.pi * x / TABLE_X1)) for x in np.linspace(0, TABLE_X1, 24)]
        plank = top + [(x, y + TABLE_T) for x, y in top[::-1]]
        dr.polygon(cam.pts(plank), fill=TABLE_COL)
        dr.line(cam.pts(top), fill=TABLE_EDGE, width=max(2, int(cam.L(5))))
        for lx in LEGS:
            fy = floor_y(lx + LEG_W / 2)
            dr.rectangle([*cam.X(lx, TABLE_T - lift), *cam.X(lx + LEG_W, fy - max(0.0, lift - 0.0) * 0)], fill=LEG_COL)
        ccx, ccy, ca_ = cale_state(T)
        cw, ch = (CALE[2] - CALE[0]) / 2, -CALE[1] / 2
        cpts = [(ccx + dx * math.cos(ca_) - dy * math.sin(ca_), ccy + dx * math.sin(ca_) + dy * math.cos(ca_))
                for dx, dy in ((-cw, -ch), (cw, -ch), (cw, ch), (-cw, ch))]
        dr.polygon(cam.pts(cpts), fill=CALE_COL)
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
            elif b["mode"] == "neck":
                X, Y = to_world(pose, b["u"], b["v"])
                dr.polygon(cam.pts(ellipse_pts(X, Y, b["a"], b["b"], pose[2])), fill=hc)
                face_at(dr, *cam.X(X, Y), cam.L(b["b"]), gz, b.get("spin"))
            else:
                self.draw_stuck(dr, cam, pose, b, gz)
            draw_glass_front(dr, dra, cam, pose, POLYS)
            return
        b = st["ball"]
        x, y, R = b["u"], b["v"], b["r"]
        dpt, n = b.get("depth", 0.0), b.get("n", (0.0, -1.0))
        if st["phase"] == "free":
            fpose = st["fpose"]
            dr.polygon(cam.pts(poly_world(fpose, POLYS[1])), fill=INTERIOR)
            draw_glass_front(dr, dra, cam, fpose, POLYS)
            ang = math.atan2(n[1], n[0])
            dr.polygon(cam.pts(ellipse_pts(x, y, (R - dpt) * pk, (R + 0.6 * dpt) * pk, ang)), fill=hc)
            face_at(dr, *cam.X(x, y), cam.L(R - dpt), gz)
            return
        pose = self.hat_pose(x, y, R, st["c"], st["a"], st["lift"])
        dr.polygon(cam.pts(poly_world(pose, POLYS[1])), fill=INTERIOR)
        u_in = max(UN - 20, UL - (1 - st["c"]) * R - 24)
        if st["lift"] < 4:
            plug = [(u, -h_in(u) + 1.5) for u in np.linspace(u_in, UL, 30)] + [(u, h_in(u) - 1.5) for u in np.linspace(UL, u_in, 30)]
            dr.polygon(cam.pts(poly_world(pose, plug)), fill=hc)
        ang = math.atan2(n[1], n[0])
        dr.polygon(cam.pts(ellipse_pts(x, y, (R - dpt) * pk, (R + 0.6 * dpt) * pk, ang)), fill=hc)
        face_at(dr, *cam.X(x, y), cam.L(R - dpt), gz)
        draw_glass_front(dr, dra, cam, pose, POLYS)

    def draw_stuck(self, dr, cam, pose, b, gz):
        hc = base.HERO["color"]
        if b["r_rear"] > 1:
            X, Y = to_world(pose, b["u_rear"], b["v_rear"])
            dr.ellipse([*cam.X(X - b["r_rear"], Y - b["r_rear"]), *cam.X(X + b["r_rear"], Y + b["r_rear"])], fill=hc)
        u0, u1 = b["u_in"], min(b["u_front"], UL)
        if u1 > u0:
            sau = [(u, -h_in(u) + 1.5) for u in np.linspace(u0, u1, 30)] + [(u, h_in(u) - 1.5) for u in np.linspace(u1, u0, 30)]
            dr.polygon(cam.pts(poly_world(pose, sau)), fill=hc)
        if b["u_front"] >= UL - 1 and b["rh"] > 2:
            hx, hy = b["head"]
            r = b["rh"]
            dr.ellipse([*cam.X(hx - r, hy - r), *cam.X(hx + r, hy + r)], fill=hc)
            face_at(dr, *cam.X(hx, hy), cam.L(r), gz)
        else:
            X, Y = to_world(pose, min(b["u_front"], UL) - 40, 0.0)
            face_at(dr, *cam.X(X, Y), cam.L(HN * 0.95), (0.8, 0.0))


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
    WIN = [(0.0, 6.0, 2.04), (6.0, END, 56.86)]

    def setup(self):
        self.sc = scene_for(self.cfg)
        a, b, c = self.WIN[self.idx]
        self.chute_abs = c
        self.hold_s = b - c
        self.abs0 = a
        self.prevT = None
        self.title = None
        self.R = 26.0
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
        sg = sag_at(T) if 49.6 <= T < 54 else 0.0
        top = [(x, -lift + sg * math.sin(math.pi * x / TABLE_X1)) for x in np.linspace(0, TABLE_X1, 24)]
        out.append(P(top + [(x, y + TABLE_T) for x, y in top[::-1]]))
        ccx, ccy, ca_ = cale_state(T)
        cw, ch = (CALE[2] - CALE[0]) / 2, -CALE[1] / 2
        out.append(P([(ccx + dx * math.cos(ca_) - dy * math.sin(ca_), ccy + dx * math.sin(ca_) + dy * math.cos(ca_))
                      for dx, dy in ((-cw, -ch), (cw, -ch), (cw, ch), (-cw, ch))]))
        attached = st["phase"] in ("hat", "stuck") or (st["phase"] == "free" and (T < sc.t_pop + 0.3 or sc.t_chase <= T < sc.t_chase + 0.3))
        if not attached:
            pose = sc.small_pose(T, st)
            for band in (POLYS[2], POLYS[3]):
                out.append(P(poly_world(pose, band)))
        return out

    def bodies(self, s):
        T = s["T"]
        if self.sc.t_rev0 - 0.05 <= T < self.sc.t_rev1 + 0.05:
            return []                      # la caméra recule de dix fois en 0,7 s : rien ne bouge que l'image
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
    "ball_r": 28.0, "gravity": G,
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
