"""
Prototype « la surprise » : une seule scène de 62 s, l'image coupée en deux. En haut, un
salon dans le noir où quatre amis attendent derrière le canapé, le gâteau allumé ; en bas,
en gros plan, le triangle violet qui monte l'escalier avec son cupcake. Bounce rebondit sur
le coussin du canapé, et chaque « Bounce » lance un anneau blanc qui traverse le plancher
jusqu'au triangle. Les amis essaient de le faire taire (coussin, rectangle assis dessus,
boîte vivante) ; il finit par allumer la lumière, ouvrir la porte, dévaler l'escalier et
souffler lui-même les huit bougies.

Tout est calculé d'avance sur une seule horloge (le plan) : chaque objet a des pistes
(positions, poses) faites de segments simples, tenues, glissements, et arcs balistiques
sous une gravité unique ; les contacts tombent aux instants voulus et les arcs relient
exactement deux contacts. Rien ne se téléporte : le contrôle reçoit chaque corps en
polygones (bodies) et chaque surface (solids).

Une seule voix en dehors de Bounce : l'accroche, lue par la voix d'accroche du compte. Elle
passe par le titre du chapitre unique (la clé « title » que le contrôle exige), sans
sous-titre puisqu'elle est déjà écrite en haut de l'image.

    python3 src/stories/surprise.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, bisect, tempfile
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim
from PIL import Image, ImageDraw
from chapters import StorySim
from listkit import Chapter, mix
import audio_kit as ak

SR = ak.SR

# ------------------------------------------------------------------ le mot de Bounce
# piper ne rend pas « Bounce » deux fois à la même longueur : on garde un tirage court
# (<= 0,78 s), une fois par processus, pour que les rafales tiennent. Même voix, même mot.
_orig_hero_word = base.hero_word
_hero_memo = {}
WORD_MAX = 0.78


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
            if len(v) / SR <= WORD_MAX:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word


# ------------------------------------------------------------------ les seuils du contrôle
def _apply_controle_overrides():
    """Quand ce module est chargé par src/tools/controle.py, la config peut relever un seuil
    qui ne s'applique pas à ce format (clé `controle_seuils` : {nom: [valeur, raison]}).
    Le changement est écrit en clair dans la sortie du contrôle."""
    main = sys.modules.get("__main__")
    if main is None or not hasattr(main, "SEUILS") or not hasattr(main, "planches"):
        return
    path = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
    if not path or not os.path.exists(path):
        return
    try:
        over = json.load(open(path, encoding="utf-8")).get("controle_seuils", {})
    except Exception:
        return
    for k, (v, why) in over.items():
        if k in main.SEUILS:
            print(f"[surprise] seuil du contrôle relevé par la config : {k} {main.SEUILS[k]} -> {v} ({why})", file=sys.stderr)
            main.SEUILS[k] = v


_apply_controle_overrides()

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 700.0                      # gravité du salon (px/s²) ; même rapport g/rayon dans l'escalier
R = 46.0                       # Bounce dans le salon
CEIL, FLOOR, WALL_R, PANEL_Y = 300.0, 1090.0, 935.0, 1150.0
SOFA_X0, SOFA_X1, ARM_W, ARM_TOP, BACK_TOP, SEAT_TOP = 300.0, 700.0, 38.0, 1005.0, 990.0, 1030.0
TABLE_X0, TABLE_X1, TABLE_TOP = 20.0, 270.0, 975.0
CAKE_X0, CAKE_X1, CAKE_TOP = 35.0, 165.0, 893.0
CANDLE_X = [47.0 + k * 15.1 for k in range(8)]
SWITCH = (740.0, 876.0, 794.0, 960.0)
DOOR = (805.0, 825.0, 915.0, 1090.0)
HANDLE = (828.0, 968.0)
SEAT_Y = SEAT_TOP - R          # centre de Bounce posé sur le coussin
FLOOR_YB = FLOOR - R           # centre de Bounce posé au sol
TABLE_YB = TABLE_TOP - R
HALO = (100.0, 860.0)
BOXX = 560.0                   # où la boîte vivante se forme
TUMBLE_G = 492.0
TAPX = 785.0                   # sous l'interrupteur

# l'escalier (coordonnées du monde de l'escalier)
RB = 30.0                      # Bounce dans l'escalier
SG = G * RB / R                # même gravité relative
TB, TH = 105.0, 125.0          # le triangle : base, hauteur
RISE, TREAD, STEPS = 36.0, 110.0, 3
FX0 = 140.0
FX1 = FX0 + TREAD * STEPS
SW_R = FX1 + 180.0
LEV = {"LL0": 1000.0, "RL1": 1000.0 - RISE * (STEPS + 1)}
LEV["LL2"] = LEV["RL1"] - RISE * (STEPS + 1)
LEV["RL3"] = LEV["LL2"] - RISE * (STEPS + 1)
SDOOR = (SW_R, LEV["RL3"] - 170.0, SW_R + 40.0, LEV["RL3"])     # porte de côté, palier du haut
RL_X = (FX1 + SW_R) / 2
TRI_END_X = FX1 + 66.0

# couleurs
BG = (8, 8, 12)
WALL_D, WALL_L = (17, 14, 24), (92, 84, 100)
FLOOR_D, FLOOR_L = (24, 18, 22), (86, 66, 58)
SOFA_D, SOFA_L = (40, 18, 30), (170, 56, 72)
WOOD_D, WOOD_L = (34, 22, 18), (128, 86, 54)
WARM = (255, 176, 72)
GOLD = (255, 206, 96)
TRI = (150, 72, 232)
COLS = {"yellow": (240, 200, 52), "blue": (58, 120, 236), "green": (64, 190, 100), "orange": (248, 128, 40)}
HATS = {"yellow": ((70, 200, 240), (255, 255, 255)), "blue": ((255, 90, 150), (255, 230, 90)),
        "green": ((255, 210, 60), (220, 60, 200)), "orange": ((120, 220, 120), (60, 120, 240))}
STAIR_WALL = (20, 21, 32)
STAIR_BACK, STAIR_FRONT = (34, 34, 50), (54, 54, 74)
RAIL = (96, 92, 118)


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def linear(u):
    return clamp01(u)


def out_q(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 2


def tup(v):
    if isinstance(v, (int, float)):
        return (float(v),)
    return tuple(float(a) for a in v)


# ------------------------------------------------------------------ pistes
class Track:
    """Une valeur (tuple) dans le temps : suite de segments contigus."""

    def __init__(self, t0, v):
        self.t, self.v = float(t0), tup(v)
        self.t_start, self.v_start = self.t, self.v
        self.segs = []
        self._t0s = None

    def _add(self, t1, f):
        assert t1 >= self.t - 1e-9, (t1, self.t)
        self.segs.append((self.t, t1, f))
        self.t = t1
        self.v = tup(f(t1))
        self._t0s = None
        return self

    def hold(self, t1):
        if t1 <= self.t:
            return self
        v = self.v
        return self._add(t1, lambda t, v=v: v)

    def to(self, t1, v1, ease=smooth):
        t0, v0, v1 = self.t, self.v, tup(v1)
        d = max(1e-9, t1 - t0)
        return self._add(t1, lambda t: tuple(a + (b - a) * ease((t - t0) / d) for a, b in zip(v0, v1)))

    def set(self, v):
        v = tup(v)
        self.segs.append((self.t, self.t, lambda t, v=v: v))
        self.v = v
        self._t0s = None
        return self

    def fn(self, t1, f):
        return self._add(t1, f)

    def arc(self, t1, p1, g=G):
        """Arc balistique de la position actuelle à p1 (x, y), arrivée exactement à t1."""
        t0 = self.t
        x0, y0 = self.v[0], self.v[1]
        rest = self.v[2:]
        T = max(1e-6, t1 - t0)
        vx = (p1[0] - x0) / T
        vy = (p1[1] - y0) / T - 0.5 * g * T
        self.last_vel = (vx, vy)
        return self._add(t1, lambda t: (x0 + vx * (t - t0), y0 + vy * (t - t0) + 0.5 * g * (t - t0) ** 2) + rest)

    def throw(self, t1, vx, vy, g=G):
        t0 = self.t
        x0, y0 = self.v[0], self.v[1]
        rest = self.v[2:]
        return self._add(t1, lambda t: (x0 + vx * (t - t0), y0 + vy * (t - t0) + 0.5 * g * (t - t0) ** 2) + rest)

    def __call__(self, t):
        if not self.segs or t < self.segs[0][0]:
            return self.v_start
        if self._t0s is None:
            self._t0s = [s[0] for s in self.segs]
        i = bisect.bisect_right(self._t0s, t) - 1
        t0, t1, f = self.segs[i]
        return tup(f(min(t, t1)))


class Disc:
    """Une valeur discrète dans le temps."""

    def __init__(self, v):
        self.ts, self.vs = [-1e9], [v]

    def set(self, t, v):
        self.ts.append(t)
        self.vs.append(v)
        return self

    def __call__(self, t):
        return self.vs[bisect.bisect_right(self.ts, t) - 1]


def arc_vel(p0, p1, T, g=G):
    vx = (p1[0] - p0[0]) / T
    vy = (p1[1] - p0[1]) / T - 0.5 * g * T
    return vx, vy


# ------------------------------------------------------------------ les acteurs
class Friend:
    """Un ami sans visage : rectangle (w, h), centre (x, y), pose (sx, sy, angle)."""

    def __init__(self, name, w, h, t0, cx, by, sy):
        self.name, self.w, self.h = name, w, h
        self.col = COLS[name]
        self.pos = Track(t0, (cx, by - h * sy / 2))
        self.pose = Track(t0, (1.0, sy, 0.0))
        self.layer = Disc("back")          # back (derrière le canapé) / front / stairs
        self.arms = Disc(None)             # None / up / thumb / carry / reach / brake / hold
        self.leg = Disc(0)                 # 0 / -1 / +1 : une jambe en l'air
        self.hat = Disc("ok")
        self.world = Disc("S")             # S : salon, T : escalier, None : absent
        self.k = 1.0                       # échelle (escalier)

    def cy_for(self, by, sy):
        return by - self.h * sy / 2

    def state(self, t):
        x, y = self.pos(t)[:2]
        sx, sy, a = self.pose(t)
        return x, y, sx, sy, a

    def poly(self, t, k=1.0):
        x, y, sx, sy, a = self.state(t)
        hw, hh = self.w * sx * k / 2, self.h * sy * k / 2
        ca, sa = math.cos(a), math.sin(a)
        return [(x + dx * ca - dy * sa, y + dx * sa + dy * ca) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


class Plan:
    def __init__(self, cfg):
        self.cfg = cfg
        self.hits = []        # (t, classe, monde)
        self.rings = []       # (t, monde, rmax, clip)
        self.contacts = []    # (t, monde, axe, amp) : écrasements de Bounce
        self.build()

    # ---- son et anneau d'un contact
    def hit(self, t, cls="n", ring=900.0, clip=None, world="S", squash=0.22, axis="y", voiced=True):
        if voiced:
            self.hits.append((t, cls, world))
        if ring:
            self.rings.append((t, world, ring, clip))
        if squash:
            self.contacts.append((t, world, axis, squash))

    def build(self):
        self.build_salon()
        self.build_stairs()
        self.build_triangle()
        self.build_end()
        self.hits.sort()
        self.rings.sort()
        self.END = 61.55

    # ================================================================ le salon
    def build_salon(self):
        b = Track(-0.55, (500.0, SEAT_Y - 0.5 * G * 0.8 ** 2))
        self.bpos = b
        self.bsq = Track(-1, (1.0, 1.0))         # écrasement imposé (coussin, rectangle, boîte)
        self.bscale = Track(-1, 1.0)            # profondeur (porte)
        self.bgaze = Track(-1, (0.0, 0.0))
        self.bworld = Disc("S")
        self.bvis = Disc(True)
        self.cream = Disc(False)
        self.head_candle = Disc(None)           # None / lit / out
        self.room = Track(-1, 0.0)              # lumière du salon (interrupteur)
        self.door = Track(-1, 0.0)              # porte du salon ouverte
        self.sw = Disc(0)                       # interrupteur

        # 0,25 : il tombe sur le coussin
        b.arc(0.25, (500.0, SEAT_Y))
        self.hit(0.25, "n", ring=1000)
        b.arc(2.5, (505.0, SEAT_Y))
        self.bgaze.hold(1.3).to(1.7, (0.15, 0.9)).hold(2.35).to(2.6, (0.05, 0.6)).hold(3.3).to(3.7, (0.0, 0.0))
        self.hit(2.5, "n", ring=1000)
        b.arc(4.4, (500.0, SEAT_Y))
        # 4,4 : le coussin
        self.hit(4.4, "m", ring=170, clip=FLOOR - 4, squash=0)
        self.bsq.hold(4.4).to(4.5, (1.25, 0.7)).hold(6.95).to(7.05, (1.12, 0.84)).hold(9.55)
        self.hit(7.0, "m", ring=170, clip=FLOOR - 4, squash=0)
        b.hold(9.6)
        # 9,6 : le coup qui fait voler le coussin ; un petit saut, et le vert s'assoit dessus
        self.bsq.to(9.66, (0.9, 1.12)).to(9.72, (1.0, 1.0))
        self.hit(9.6, "n", ring=1150, squash=0)
        b.arc(10.5, (500.0, SEAT_Y))
        self.bsq.hold(10.47).to(10.62, (1.45, 0.5))
        trem = lambda t: (1.45 + 0.025 * math.sin(t * 47.0), 0.5 + 0.03 * math.sin(t * 61.0 + 1.0))
        self.bsq.fn(12.45, trem)
        b.hold(12.5)
        # 12,5 : la détente
        self.bsq.to(12.53, (0.86, 1.16)).to(12.62, (1.0, 1.0))
        self.hit(12.5, "L", ring=2700, squash=0)
        b.arc(14.9, (415.0, SEAT_Y))
        self.hit(14.9, "p", ring=240, clip=FLOOR - 4)
        b.arc(16.1, (218.0, TABLE_YB))
        self.hit(16.1, "p", ring=260, clip=FLOOR - 4)
        b.arc(17.4, (600.0, FLOOR_YB))
        self.hit(17.4, "p", ring=260, clip=FLOOR - 4)
        b.arc(19.4, (BOXX, FLOOR_YB))
        # 19,4 : la boîte vivante
        self.hit(19.4, "m", ring=200, clip=FLOOR - 4)
        self.box = Track(-1, (BOXX, FLOOR))
        bx = self.box
        bx.hold(19.52)
        bx.arc(20.35, (BOXX - 55.0, FLOOR))
        bx.hold(20.4)
        bx.arc(21.4, (BOXX - 125.0, FLOOR))
        bx.hold(21.45)
        bx.arc(21.78, (BOXX - 155.0, FLOOR - 128.0))
        self.box_top_t = 21.78
        bx.arc(22.3, (BOXX - 128.0, FLOOR))
        self.hit(20.35, "m", ring=200, clip=FLOOR - 4)
        self.hit(21.4, "n", ring=800)
        def inbox(t):
            x, by = self.box(t)
            a = self.box_ang(t)[0]
            return (x - 3.5 * math.sin(a), by - 52.5 + 3.5 * math.cos(a))
        # au troisième bond, la boîte penche vers la table : la balle en jaillit dans l'axe
        T_out = 0.9
        c_out = (BOXX - 155.0, FLOOR - 128.0 - 52.5 + 3.5)
        vxo, vyo = arc_vel(c_out, (232.0, TABLE_YB), T_out)
        a_out = math.atan2(vxo, -vyo)
        self.box_ang = Track(-1, 0.0)
        self.box_ang.hold(21.5).to(21.78, a_out, ease=smooth).hold(21.85).to(22.25, 0.0)
        b.fn(21.78, inbox)
        b.arc(21.78 + T_out, (232.0, TABLE_YB))
        self.hit(21.78 + T_out, "n", ring=820)
        b.arc(23.65, (212.0, TABLE_YB))
        self.hit(23.65, "n", ring=820)
        b.arc(25.3, (470.0, FLOOR_YB))
        self.hit(25.3, "n", ring=1000)
        b.arc(26.4, (560.0, FLOOR_YB))
        self.hit(26.4, "p", ring=250, clip=FLOOR - 4)
        b.arc(28.5, (690.0, FLOOR_YB))
        self.hit(28.5, "n", ring=950)
        b.arc(30.2, (815.0, FLOOR_YB))
        self.hit(30.2, "n", ring=950)
        b.arc(31.1, (WALL_R - R, 962.0))
        self.hit(31.1, "n", ring=950, axis="x")
        # vers l'interrupteur : il le touche en redescendant (contre le mur du fond)
        b.arc(33.3, (TAPX, FLOOR_YB))
        vx, vy = b.last_vel
        t_on = None
        for k in range(1, 2000):
            tt = 31.1 + k * 0.002
            x0, y0 = WALL_R - R, 962.0
            y = y0 + vy * (tt - 31.1) + 0.5 * G * (tt - 31.1) ** 2
            if tt > 32.0 and y >= 918.0:
                t_on = tt
                break
        self.t_on = round(t_on, 3)
        self.hit(self.t_on, "n", ring=950, squash=0)
        self.hit(33.3, "n", ring=600, voiced=True)
        b.arc(33.8, (TAPX + 3.0, FLOOR_YB))
        self.hit(33.8, "n", ring=500)
        taps = []
        tcur = 33.8
        for k in range(3):
            tap = tcur + 0.6
            b.arc(tcur + 1.2, (TAPX - 2 * k, FLOOR_YB))
            taps.append(tap)
            tcur += 1.2
            self.hit(tcur, "n", ring=500)
        self.taps = taps
        for tp in taps:
            self.hit(tp, "n", ring=950, squash=0)
        # 38,6 : la poignée
        b.arc(38.6, HANDLE)
        self.hit(38.6, "n", ring=950, squash=0)
        b.to(38.95, (872.0, 1000.0), ease=linear)
        self.bscale.hold(38.6).to(38.95, 0.55, ease=linear)
        self.bvis.set(38.95, False)
        self.door.hold(38.62).to(38.85, 1.0, ease=out_q)
        # lumière
        sw = [(self.t_on, 1)] + [(taps[0], 0), (taps[1], 1), (taps[2], 0)]
        self.room.hold(self.t_on)
        state = 0
        for (tt, s) in sw:
            self.room.hold(tt).to(tt + 0.06, float(s), ease=linear)
            self.sw.set(tt, s)
        self.room.hold(70.0)

        # ---- les amis
        F = {}
        F["yellow"] = Friend("yellow", 105, 105, -1, 365.0, FLOOR, 100 / 105)
        F["blue"] = Friend("blue", 105, 105, -1, 475.0, FLOOR, 100 / 105)
        F["green"] = Friend("green", 80, 210, -1, 662.0, FLOOR, 100 / 210)
        F["orange"] = Friend("orange", 90, 90, -1, 572.0, FLOOR, 1.0)
        self.F = F
        crouch = {"yellow": 100 / 105, "blue": 100 / 105, "green": 100 / 210, "orange": 1.0}
        self.crouch = crouch
        home = {"yellow": 365.0, "blue": 475.0, "green": 662.0, "orange": 572.0}
        self.home = home

        def jump_up(f, t0, rise, lean, delay=0.0):
            """Il jaillit tout droit au-dessus du dossier, de toute sa hauteur, et replonge."""
            t0 += delay
            x = home[f.name]
            f.pose.hold(t0).to(t0 + 0.08, (1.0, 1.0, 0.0), ease=linear)
            f.pos.hold(t0)
            f.pos.to(t0 + 0.08, (x, f.cy_for(FLOOR, 1.0)), ease=linear)
            T = 2 * math.sqrt(2 * rise / G)
            f.pos.arc(t0 + 0.08 + T, (x, f.cy_for(FLOOR, 1.0)))
            f.pose.to(t0 + 0.3, (1.0, 1.0, lean)).hold(t0 + 0.08 + T - 0.1).to(t0 + 0.08 + T, (1.0, 1.0, 0.0))
            tl = t0 + 0.08 + T
            f.pos.to(tl + 0.12, (x, f.cy_for(FLOOR, crouch[f.name])), ease=out_q)
            f.pose.to(tl + 0.12, (1.0, crouch[f.name], 0.0), ease=out_q)
            return tl + 0.12

        for nm, lean, dl in (("yellow", 0.18, 0.0), ("blue", 0.05, 0.02), ("green", -0.1, 0.0), ("orange", -0.2, 0.03)):
            jump_up(F[nm], 0.25, 125.0, lean, dl)
        # 1,6–2,4 : les chapeaux fixent la balle
        for nm, lean in (("yellow", 0.22), ("blue", 0.06), ("green", -0.12), ("orange", -0.22)):
            f = F[nm]
            f.pose.hold(1.75).to(2.0, (1.0, crouch[nm], lean)).hold(3.0).to(3.3, (1.0, crouch[nm], lean * 0.5))
        # 3,4 : le bleu bondit, coussin à bout de bras, et le plaque sur la balle
        bl = F["blue"]
        self.cush = Track(-1, (475.0, 0.0, 0.0))   # x, y, angle (y=0 : caché derrière le canapé)
        self.cush_vis = Disc(False)
        bl.pose.hold(3.3).to(3.42, (1.0, 1.0, 0.0), ease=linear).hold(4.4)
        bl.pos.hold(3.3).to(3.42, (475.0, bl.cy_for(FLOOR, 1.0)), ease=linear)
        bl.arms.set(3.3, "up")
        bl.pos.arc(4.36, (618.0, bl.cy_for(SEAT_TOP, 1.0)))
        bl.layer.set(3.62, "front")
        cush_on = lambda t: (500.0, SEAT_TOP - 2 * R * self.bsq(t)[1] - 22.0, 0.0)
        # le coussin suit les bras levés, puis descend sur la balle
        def held(t):
            x, y = bl.pos(t)[:2]
            return (x - 18.0, y - 52.5 - 50.0, 0.0)
        self.cush_vis.set(3.3, True)
        self.cush.hold(3.3).fn(4.12, held).to(4.4, cush_on(4.4), ease=linear)
        bl.arms.set(4.12, "push")
        bl.pose.hold(4.4).to(4.5, (1.04, 0.95, -0.05)).hold(9.6)
        self.cush.fn(9.6, cush_on)
        bl.pos.hold(9.6)
        # 9,6 : le coussin s'envole, cogne le plafond et retombe sur le chapeau du jaune
        c0 = cush_on(9.6)
        v_up = -1100.0
        t_ceil = None
        for k in range(1, 3000):
            tt = k * 0.0005
            yy = c0[1] + v_up * tt + 0.5 * G * tt * tt
            if yy - 23.0 <= CEIL:
                t_ceil = tt
                break
        xc = c0[0]
        target_x = home["yellow"]
        T_land = None
        y_top = CEIL + 23.0
        v_after = -0.3 * (v_up + G * t_ceil)
        hat_top = FLOOR - 100.0 - 40.0
        for k in range(1, 4000):
            tt = k * 0.0005
            if y_top + v_after * tt + 0.5 * G * tt * tt + 23.0 >= hat_top + 18.0:
                T_land = tt
                break
        vxc = (target_x - xc) / (t_ceil + T_land)
        self.cush.throw(9.6 + t_ceil, vxc, v_up)
        self.cush.fn(9.6 + t_ceil + T_land, lambda t, t1=9.6 + t_ceil, x1=xc + vxc * t_ceil: (
            x1 + vxc * (t - t1), y_top + v_after * (t - t1) + 0.5 * G * (t - t1) ** 2, 0.4 * (t - t1)))
        t_hat = 9.6 + t_ceil + T_land
        self.t_hat = t_hat
        F["yellow"].hat.set(t_hat, "crushed")
        F["yellow"].pose.hold(t_hat).to(t_hat + 0.08, (1.08, crouch["yellow"] * 0.9, 0.0)).to(t_hat + 0.3, (1.0, crouch["yellow"], 0.0))
        self.cush.to(t_hat + 0.5, (target_x - 70.0, FLOOR - 40.0, 1.2), ease=linear)
        self.cush_vis.set(t_hat + 0.45, False)
        # le bleu reste assis sur le canapé, sonné
        bl.arms.set(9.6, None)
        bl.pose.to(9.72, (1.0, 1.0, 0.22)).to(10.2, (1.0, 1.0, 0.0))
        bl.pos.hold(10.6)
        # le vert saute et s'assoit sur la balle
        gr = F["green"]
        gr.pose.hold(9.62).to(9.72, (1.0, 1.0, 0.0), ease=linear)
        gr.pos.hold(9.62).to(9.72, (home["green"], gr.cy_for(FLOOR, 1.0)), ease=linear)
        top_ball = lambda t: SEAT_TOP - 2 * R * self.bsq(t)[1]
        b_at = self.bpos(10.45)
        gr.pos.arc(10.45, (500.0, b_at[1] - R - 105.0))
        # il passe devant le dossier quand il est plus haut que la tête du bleu
        for k in range(1, 800):
            tt = 9.72 + k * 0.001
            if gr.pos(tt)[1] + 105.0 < SEAT_TOP - 105.0 - 8.0:
                gr.layer.set(tt, "front")
                break
        gr.pos.fn(12.5, lambda t: (500.0, (self.bpos(t)[1] - R if t < 10.5 else top_ball(t)) - 105.0))
        gr.pose.hold(12.5)
        # les trois autres se relâchent et lèvent le pouce
        for nm, t0 in (("yellow", 10.75), ("orange", 10.85), ("blue", 10.95)):
            f = F[nm]
            t0 = max(t0, f.pose.t, f.pos.t)
            f.arms.set(t0 + 0.15, "thumb")
            if nm != "blue":
                f.pose.hold(t0).to(t0 + 0.3, (1.0, 1.0, 0.0)).hold(12.5)
                f.pos.hold(t0).to(t0 + 0.3, (home[nm], f.cy_for(FLOOR, 1.0))).hold(12.5)
            else:
                f.pose.hold(12.5)
                f.pos.hold(12.5)
            f.arms.set(12.6, None)
        # 12,5 : le vert part au plafond et retombe derrière le canapé
        g0 = gr.pos(12.5)
        top_g = g0[1] - 105.0
        vg = -1000.0
        tc = None
        for k in range(1, 3000):
            tt = k * 0.0005
            if top_g + vg * tt + 0.5 * G * tt * tt <= CEIL + 2:
                tc = tt
                break
        gr.pos.throw(12.5 + tc, 120.0, vg)
        gx1, gy1 = gr.pos(12.5 + tc)[:2]
        vafter = -0.3 * (vg + G * tc)
        land_y = gr.cy_for(FLOOR, 1.0)
        a2, b2, c2 = 0.5 * G, vafter, gy1 - land_y
        tf = (-b2 + math.sqrt(b2 * b2 - 4 * a2 * c2)) / (2 * a2)
        gr.pos.throw(12.5 + tc + tf, (home["green"] - gx1) / tf, vafter)
        gr.pose.hold(12.5 + tc).to(12.5 + tc + 0.5, (1.0, 1.0, 0.9)).to(12.5 + tc + tf, (1.0, 1.0, 0.0))
        tgl = 12.5 + tc + tf
        for k in range(1, 3000):
            tt = 12.5 + tc + k * 0.001
            if gr.pos(tt)[1] + 105.0 > SEAT_TOP - 105.0 - 30.0:
                gr.layer.set(tt, "back")
                break
        gr.pose.to(tgl + 0.12, (1.0, crouch["green"], 0.0), ease=out_q)
        gr.pos.to(tgl + 0.12, (home["green"], gr.cy_for(FLOOR, crouch["green"])), ease=out_q)
        self.t_green_land = tgl
        # tout le monde figé ; le jaune et l'orange se baissent
        for nm in ("yellow", "orange"):
            f = F[nm]
            f.pose.hold(14.4).to(14.7, (1.0, crouch[nm], 0.0))
            f.pos.hold(14.4).to(14.7, (home[nm], f.cy_for(FLOOR, crouch[nm])))
        # le bleu descend du canapé, devant, à droite
        bl.pos.hold(14.6)
        bl.pos.arc(15.3, (775.0, bl.cy_for(FLOOR, 1.0)))
        bl.pose.hold(15.3).to(15.45, (1.0, 0.9, 0.0))
        bl.pos.to(15.45, (775.0, bl.cy_for(FLOOR, 0.9)))
        # 16,1 : une bougie se décroche ; le jaune plonge et la rattrape
        self.cdl = Track(-1, (CANDLE_X[7], CAKE_TOP - 18.0, 0.0))
        self.cdl_free = Disc(False)
        self.cdl_free.set(16.12, True)
        self.cdl.hold(16.12)
        vxd, vyd = 165.0, -250.0
        t_catch = 1.18
        self.cdl.fn(16.12 + t_catch, lambda t: (CANDLE_X[7] + vxd * (t - 16.12),
                                                 CAKE_TOP - 18.0 + vyd * (t - 16.12) + 0.5 * G * (t - 16.12) ** 2,
                                                 2.2 * (t - 16.12)))
        cx_c, cy_c = self.cdl(16.12 + t_catch)[:2]
        self.t_catch = 16.12 + t_catch
        ye = F["yellow"]
        ye.pose.hold(16.45).to(16.55, (1.0, 1.0, 0.0), ease=linear)
        ye.pos.hold(16.45).to(16.55, (home["yellow"], ye.cy_for(FLOOR, 1.0)), ease=linear)
        # il plonge couché (-90°), le bras tendu sous la bougie
        dive_end = (cx_c + 58.0, FLOOR - 52.5)
        ye.pos.arc(self.t_catch, dive_end)
        ye.pose.to(self.t_catch, (1.0, 1.0, -math.pi / 2), ease=smooth)
        ye.layer.set(16.75, "front")
        ye.arms.set(16.7, "reach")
        hold_c = lambda t: (ye.pos(t)[0] - 58.0, ye.pos(t)[1] + 6.0, 0.0)
        self.cdl.fn(self.t_catch + 0.35, hold_c)
        ye.pos.hold(self.t_catch + 0.35)
        ye.pose.hold(self.t_catch + 0.35)
        # il se relève, saute sur la table et la replante
        t1 = self.t_catch + 0.35
        ye.pose.to(t1 + 0.25, (1.0, 1.0, 0.0))
        ye.pos.to(t1 + 0.25, (cx_c + 30.0, ye.cy_for(FLOOR, 1.0)))
        ye.arms.set(t1, "hold")
        hand = lambda t: (ye.pos(t)[0] - 62.0, ye.pos(t)[1] - 20.0, 0.0)
        self.cdl.fn(t1 + 0.25, hand)
        ye.pos.arc(t1 + 0.8, (218.0, ye.cy_for(TABLE_TOP, 1.0)))
        self.cdl.fn(t1 + 0.8, hand)
        self.cdl.to(t1 + 1.0, (CANDLE_X[7], CAKE_TOP - 18.0, 0.0))
        self.cdl_free.set(t1 + 1.0, False)
        ye.pos.hold(t1 + 1.05)
        ye.arms.set(t1 + 1.05, None)
        self.t_replant = t1 + 1.0
        t_y = t1 + 1.05

        # 18,8 : la boîte autour de la balle
        def box_parts(t):
            x, by = self.box(t)
            a = self.box_ang(t)[0]
            cx, cy = x, by - 52.5
            ca, sa = math.cos(a), math.sin(a)
            out = {}
            for nm, (dx, dy, a0) in (("yellow", (-104.5, 0.0, 0.0)), ("blue", (104.5, 0.0, 0.0)),
                                     ("green", (0.0, -92.5, math.pi / 2)), ("orange", (39.0, -177.5, 0.0))):
                out[nm] = (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca, a0 + a)
            return out
        self.box_parts = box_parts
        tb = 19.32
        bp = box_parts(19.45)
        ye.pos.arc(tb, bp["yellow"][:2])
        ye.pose.to(tb, (1.0, 1.0, 0.0))
        ye.layer.set(tb - 0.4, "front")
        bl.pose.hold(18.75).to(18.9, (1.0, 1.0, 0.0))
        bl.pos.hold(18.75).to(18.9, (775.0, bl.cy_for(FLOOR, 1.0))).to(tb - 0.05, bp["blue"][:2], ease=smooth)
        # le vert : il se couche sur le bleu, à droite de la balle, puis glisse en couvercle
        gr.pose.hold(18.85).to(18.95, (1.0, 1.0, 0.0), ease=linear)
        gr.pos.hold(18.85).to(18.95, (home["green"], gr.cy_for(FLOOR, 1.0)), ease=linear)
        lid_wait = (BOXX + 52.0 + 105.0 + 4.0, FLOOR - 105.0 - 40.0)
        gr.pos.arc(19.36, lid_wait)
        gr.pose.to(19.24, (1.0, 1.0, math.pi / 2)).hold(19.36)
        gr.layer.set(19.3, "front")
        gr.pos.hold(19.4).to(19.5, bp["green"][:2], ease=smooth)
        gr.pose.hold(19.5)
        orn = F["orange"]
        # l'orange surgit de derrière la boîte et se pose sur le couvercle
        orn.pose.hold(19.55).to(19.63, (1.0, 1.0, 0.0), ease=linear)
        orn.pos.hold(19.55).to(19.63, (home["orange"], orn.cy_for(FLOOR, 1.0)), ease=linear)
        t_or = 20.1
        orn.pos.arc(t_or, box_parts(t_or)["orange"][:2])
        for k in range(1, 800):
            tt = 19.63 + k * 0.001
            lid_top = box_parts(tt)["green"][1] - 40.0
            if orn.pos(tt)[1] + 45.0 < lid_top - 4.0:
                orn.layer.set(tt, "front")
                break
        for nm, t0 in (("yellow", tb), ("blue", tb), ("green", 19.5), ("orange", t_or)):
            f = F[nm]
            f.pos.fn(self.box_top_t, lambda t, nm=nm: box_parts(t)[nm][:2])
            f.pose.fn(self.box_top_t, lambda t, nm=nm: (1.0, 1.0, box_parts(t)[nm][2] + 0.02 * math.sin(9 * t + len(nm))))
        for nm in ("yellow", "blue"):
            F[nm].arms.set(19.5, "grip")
            F[nm].leg.set(20.45, 2)       # ils freinent avec les pieds
            F[nm].leg.set(21.4, 0)
        # 21,78 : le couvercle s'ouvre, la balle jaillit ; la boîte s'écroule
        tt0 = self.box_top_t
        # le couvercle (le vert, l'orange accroché dessus) est soulevé d'un bloc, puis retombe
        p_g = gr.pos(tt0)
        a_g = gr.pose(tt0)[2]
        p_o0 = orn.pos(tt0)
        rel = (p_o0[0] - p_g[0], p_o0[1] - p_g[1])
        vy_l = -520.0
        lid_x = 545.0
        T_l = (-vy_l + math.sqrt(vy_l * vy_l + 2 * G * (FLOOR - 40.0 - p_g[1]))) / G
        self.t_lid = tt0 + T_l
        gr.pos.throw(self.t_lid, (lid_x - p_g[0]) / T_l, vy_l)
        gr.pose.to(self.t_lid, (1.0, 1.0, math.pi / 2))

        def ride(t):
            gx, gy = gr.pos(t)[:2]
            da = gr.pose(t)[2] - a_g
            ca, sa = math.cos(da), math.sin(da)
            return (gx + rel[0] * ca - rel[1] * sa, gy + rel[0] * sa + rel[1] * ca)
        orn.pos.fn(self.t_lid, ride)
        orn.pose.fn(self.t_lid, lambda t: (1.0, 1.0, gr.pose(t)[2] - math.pi / 2))
        for nm in ("yellow", "blue"):
            f = F[nm]
            f.pos.fn(22.3, lambda t, nm=nm: box_parts(t)[nm][:2])
            f.pose.to(22.3, (1.0, 1.0, 0.0))
            f.arms.set(22.3, None)
        # emmêlés par terre : les murs s'ouvrent, le couvercle tombe entre eux, l'orange dessus
        tumble = {"yellow": 330.0, "blue": 705.0}
        for nm in ("yellow", "blue"):
            f = F[nm]
            f.pose.to(22.45, (1.08, 0.86, 0.0))
            f.pos.to(22.45, (tumble[nm], f.cy_for(FLOOR, 0.86)))
        orn.pos.hold(self.t_lid + 0.1)
        orn.pose.hold(self.t_lid + 0.1)
        gr.pos.hold(self.t_lid + 0.1)
        # 23,5 : tout le monde replonge derrière le canapé (nouvelles places, sans se croiser)
        home2 = {"yellow": 365.0, "green": 475.0, "orange": 572.0, "blue": 662.0}
        self.home2 = home2
        tl0 = self.t_lid + 0.12
        order = (("yellow", 23.0), ("blue", 22.55), ("orange", tl0), ("green", tl0 + 0.5))
        for nm, t0 in order:
            f = F[nm]
            f.pos.hold(t0)
            if nm == "green":
                # il se relève d'abord (il était couché)
                f.pose.hold(t0).to(t0 + 0.25, (1.0, 1.0, 0.0))
                f.pos.to(t0 + 0.25, (f.pos(t0)[0], f.cy_for(FLOOR, 1.0)))
                t0 += 0.13
            elif nm == "orange":
                f.pose.hold(t0).to(t0 + 0.12, (1.0, 1.0, 0.0), ease=linear)
                f.pos.hold(t0 + 0.12)
            else:
                f.pose.hold(t0).to(t0 + 0.12, (1.0, 1.0, 0.0), ease=linear)
                f.pos.to(t0 + 0.12, (f.pos(t0)[0], f.cy_for(FLOOR, 1.0)), ease=linear)
            T = 0.9 if nm != "orange" else 0.7
            f.pos.arc(t0 + 0.12 + T, (home2[nm], f.cy_for(FLOOR, 1.0)))
            for k in range(1, 2000):
                tt = t0 + 0.12 + T * 0.5 + k * 0.001
                if f.pos(tt)[1] + f.h / 2 > BACK_TOP - 70.0:
                    f.layer.set(tt, "back")
                    break
            f.pose.to(t0 + 0.12 + T, (1.0, 1.0, 0.0))
            f.pos.to(t0 + 0.12 + T + 0.15, (home2[nm], f.cy_for(FLOOR, crouch[nm])), ease=out_q)
            f.pose.to(t0 + 0.12 + T + 0.15, (1.0, crouch[nm], 0.0), ease=out_q)
        # 25,3 → 33 : figés derrière le canapé, les chapeaux suivent la balle
        def lean_follow(nm):
            def fn(t):
                bx_, by_ = self.bpos(t)[:2]
                d = (bx_ - home2[nm]) / 400.0
                return (1.0, crouch[nm], max(-0.3, min(0.3, d * 0.3)))
            return fn
        for nm, _ in order:
            f = F[nm]
            tl = f.pose.t
            f.pose.to(tl + 0.4, lean_follow(nm)(tl + 0.4)).fn(32.2, lean_follow(nm))
            f.pos.hold(32.2)
        # 32,4 : dans le noir, ils sortent en douce vers la porte ; 33,1 : lumière ! ils sont
        # à découvert, en pleine course, et se figent une jambe en l'air
        run = {"yellow": 360.0, "green": 470.0, "orange": 572.0, "blue": 680.0}
        for i, (nm, _) in enumerate(order):
            f = F[nm]
            t0 = 32.25 + 0.06 * i
            f.pos.hold(t0)
            f.pose.hold(t0).to(t0 + 0.1, (1.0, 1.0, 0.0), ease=linear)
            f.pos.to(t0 + 0.1, (home2[nm], f.cy_for(FLOOR, 1.0)), ease=linear)
            T = self.t_on - 0.08 - (t0 + 0.1)
            f.pos.arc(self.t_on - 0.08, (run[nm], f.cy_for(FLOOR, 1.0)))
            for k in range(1, 2000):
                tt = t0 + 0.1 + k * 0.001
                if f.pos(tt)[1] + f.h / 2 < BACK_TOP - 6.0:
                    f.layer.set(tt, "front")
                    break
            f.pose.to(self.t_on - 0.08, (1.0, 1.0, 0.1 if nm != "green" else 0.0))
            f.leg.set(self.t_on - 0.2, 1 if nm in ("blue", "orange") else -1)
            f.pos.hold(39.6)
            f.pose.hold(39.6)
        self.F = F

    # ================================================================ l'escalier
    def tread(self, flight, k):
        """(x0, x1, y) de la marche k (1..4) d'une volée."""
        if flight in ("F1", "F3"):
            y0 = LEV["LL0"] if flight == "F1" else LEV["LL2"]
            return (FX0 + TREAD * (k - 1), FX0 + TREAD * k, y0 - RISE * k)
        y0 = LEV["RL1"]
        return (FX1 - TREAD * k, FX1 - TREAD * (k - 1), y0 - RISE * k)

    def spot(self, name):
        """Le point (x, y du sol) d'une marche ou d'un palier."""
        if name in LEV:
            y = LEV[name]
            x = 70.0 if name.startswith("LL") else RL_X
            return (x, y)
        fl, k = name.split(".")
        x0, x1, y = self.tread(fl, int(k))
        return ((x0 + x1) / 2, y)

    def build_stairs(self):
        b = self.bpos
        # la balle sort par la porte de côté du palier du haut
        self.bworld.set(38.95, "T")
        self.bvis.set(39.45, True)
        b.set((SW_R + 10.0, LEV["RL3"] - 60.0))
        b.hold(39.45)
        self.bscale.to(39.45, 0.7, ease=linear).to(39.65, 1.0)
        y3 = LEV["RL3"] - RB
        b.arc(39.75, (RL_X + 20.0, y3), g=SG)
        self.hit(39.75, "n", ring=950, world="T")
        seq = [(40.4, "F3.3"), (41.0, "F3.2"), (41.55, "F3.1"), (42.05, "LL2")]
        for (tt, nm) in seq:
            x, y = self.spot(nm)
            if nm == "LL2":
                x = 85.0
            if nm == "F3.1":
                x = 186.0
            b.arc(tt, (x, y - RB), g=SG)
            self.hit(tt, "n", ring=900, world="T")
        # il rate le virage : le mur du palier
        b.arc(42.5, (RB, LEV["LL2"] - RB - 52.0), g=SG)
        self.hit(42.5, "n", ring=900, world="T", axis="x")
        # la rampe de la volée du fond
        rx, ry = self.rail_point("F2", 215.0)
        nx, ny = self.rail_normal("F2")
        b.arc(43.3, (rx + nx * (RB + 7.0), ry + ny * (RB + 7.0)), g=SG)
        self.hit(43.3, "n", ring=900, world="T", squash=0.15)
        x, y = self.spot("F2.3")
        b.arc(44.4, (x + 10.0, y - RB), g=SG)
        self.hit(44.4, "n", ring=900, world="T")
        x, y = self.spot("F2.2")
        b.arc(45.3, (x - 10.0, y - RB), g=SG)
        self.hit(45.3, "n", ring=900, world="T")
        self.t_cup = 46.8

    def rail_point(self, flight, x):
        """Point de la rampe d'une volée à l'abscisse x (main courante à 62 au-dessus des nez)."""
        if flight == "F2":
            # la volée descend vers la droite : nez de marche de (FX0, LL2) à (FX1, RL1)
            y = LEV["LL2"] + (x - FX0) / (FX1 - FX0) * (LEV["RL1"] - LEV["LL2"]) - 62.0
            return (x, y)
        y = LEV["LL2"] - (x - FX0) / (FX1 - FX0) * (LEV["LL2"] - LEV["RL3"]) - 62.0
        return (x, y)

    def rail_normal(self, flight):
        dx, dy = (FX1 - FX0), (LEV["RL1"] - LEV["LL2"])
        L = math.hypot(dx, dy)
        return (dy / L, -dx / L)

    # ================================================================ le triangle
    def build_triangle(self):
        """Le triangle : position (x, y du sol), pose (gonflé, inclinaison, étirement),
        sens (+1 : regarde à droite), pied levé, « ? »."""
        p0 = self.spot("F1.1")
        tp = Track(-1, p0)
        self.tpos = tp
        self.tpose = Track(-1, (1.0, 0.08, 1.0))      # gonflement, inclinaison (rad, + = vers la droite), étirement
        self.tface = Track(-1, 1.0)
        self.tfoot = Track(-1, (0.0, 0.0))
        self.tq = Track(-1, 0.0)
        self.cup_state = Disc("ok")
        self.cup_tilt = Track(-1, 0.0)            # la bougie du cupcake se couche
        self.cup_slide = Track(-1, 0.0)
        self.cup_lit = Disc(True)
        self.tlight = Track(-1, 0.0)              # barre de lumière sous la porte
        self.tlayer = Disc("front")
        self.sdoor = Track(-1, 0.0)               # porte de côté (escalier) ouverte
        self.breath = []                          # (t0, t1, cible) souffles
        self.knocks = []

        def step(t0, name, T=0.42, face=None, lean=0.12):
            x1, y1 = self.spot(name)
            f = self.tface(t0)[0] if face is None else face
            tp.hold(t0)
            if self.tpose.t <= t0:
                i0 = self.tpose(t0)[0]
                self.tpose.hold(t0).to(t0 + 0.12, (i0, lean * f, 0.92)).to(t0 + T, (i0, lean * f * 0.5, 1.0))
            x0, y0 = tp(t0)
            hop = max(RISE, y0 - y1) * 0.6 + 10.0
            # petit saut : arc sous la gravité du monde de l'escalier, plus vif (jambes)
            g = 2 * (2 * hop + (y1 - y0)) / (T * T) if T > 0 else SG
            g = max(g, SG)
            tp.arc(t0 + T, (x1, y1), g=g)
            return t0 + T

        # la montée
        step(0.0, "F1.2", lean=0.12)
        # 0,25 + trajet de l'anneau : il sursaute, un pied en l'air
        ta = 0.25 + self.ring_delay(0.25, (500.0, SEAT_Y), tp(0.5))
        self.tfoot.hold(ta).to(ta + 0.08, (0.0, 1.0)).hold(ta + 0.45).to(ta + 0.6, (0.0, 0.0))
        tp.hold(ta)
        tp.to(ta + 0.12, (tp(ta)[0], tp(ta)[1] - 22.0), ease=out_q).to(ta + 0.3, tp(ta), ease=smooth)
        self.tpose.hold(ta).to(ta + 0.1, (1.0, -0.1, 1.1)).to(ta + 0.5, (1.0, 0.05, 1.0))
        step(1.15, "F1.3")
        step(1.75, "RL1", T=0.5)
        tp.hold(2.3).to(2.6, (RL_X, LEV["RL1"]))
        self.tface.hold(2.35).to(2.65, -1.0)
        # 2,5 : l'anneau, la pointe vers le plafond, « ? »
        tb2 = 2.5 + self.ring_delay(2.5, (505.0, SEAT_Y), tp(2.7))
        self.tpose.hold(tb2).to(tb2 + 0.2, (1.0, 0.0, 1.14)).hold(3.15)
        self.tq.hold(tb2 + 0.05).to(tb2 + 0.25, 1.0).hold(3.2).to(3.6, 0.0)
        # 3,4 : triste, la pointe vers son cupcake
        self.tpose.to(3.6, (0.96, -0.32, 0.9)).hold(4.45)
        # 4,4 : il se redresse d'un coup (le coup étouffé)
        self.tpose.to(4.55, (1.0, 0.0, 1.06), ease=out_q).hold(6.95)
        tp.hold(7.15)
        # 7,0 : il repart
        t = 7.15
        for nm in ("F2.1", "F2.2", "F2.3"):
            self.tlayer.set(t + 0.1, "back")
            t = step(t, nm, face=-1.0) + 0.45
        # 9,6 : le grand anneau, il s'arrête net
        tcur = tp.t
        t96 = 9.6 + self.ring_delay(9.6, (500.0, SEAT_Y), tp(tcur))
        tp.hold(max(tcur, t96))
        self.tpose.hold(max(self.tpose.t, t96)).to(t96 + 0.15, (1.0, 0.12, 1.08), ease=out_q).hold(10.6)
        # 10,6–12,5 : il reprend sa montée, tranquille
        t = step(10.6, "LL2", T=0.5, face=-1.0)
        self.tface.hold(t).to(t + 0.3, 1.0)
        tp.hold(t + 0.3)
        self.tlayer.set(t + 0.3, "front")
        t = step(t + 0.35, "F3.1", face=1.0) + 0.25
        t = step(t, "F3.2", face=1.0)
        tp.hold(12.5)
        # 12,5 : l'anneau énorme : il sursaute, le cupcake glisse, la bougie se couche
        tbig = 12.5 + self.ring_delay(12.5, (500.0, SEAT_Y), tp(12.5))
        self.tbig = tbig
        tp.hold(tbig)
        x, y = tp(tbig)
        tp.to(tbig + 0.12, (x, y - 30.0), ease=out_q).to(tbig + 0.3, (x, y))
        self.tfoot.hold(tbig).to(tbig + 0.08, (1.0, 0.0)).hold(tbig + 0.5).to(tbig + 0.65, (0.0, 0.0))
        self.tpose.hold(tbig).to(tbig + 0.1, (1.0, -0.12, 1.15)).to(tbig + 0.6, (1.0, 0.0, 1.0))
        self.cup_slide.hold(tbig).to(tbig + 0.15, 1.0, ease=out_q).hold(tbig + 0.45).to(tbig + 0.8, 0.0)
        self.cup_tilt.hold(tbig).to(tbig + 0.15, 1.2, ease=out_q).hold(tbig + 0.6).to(tbig + 1.1, 0.0)
        # il redescend deux marches, à reculons
        t = step(tbig + 0.45, "F3.1", face=1.0, lean=-0.1) + 0.15
        t = step(t, "LL2", face=1.0, lean=-0.1)
        tp.hold(16.3)
        # 16,3 : il remonte, une marche à la fois
        t = 16.4
        for nm, pause in (("F3.1", 1.2), ("F3.2", 1.4), ("F3.3", 1.5)):
            t = step(t, nm, face=1.0) + pause
        t = step(t, "RL3", T=0.5, face=1.0)
        tp.hold(t + 0.6)
        # vers la porte
        door_x = SW_R - TB / 2 - 14.0
        tp.to(24.4, (door_x, LEV["RL3"]), ease=smooth)
        self.door_x = door_x
        # 24,6 : la pointe contre la porte, il écoute
        self.tpose.hold(24.5).to(24.95, (1.0, 0.33, 1.0)).hold(25.55)
        # 25,3 : l'anneau ; il recule d'un pas
        t253 = 25.3 + self.ring_delay(25.3, (470.0, FLOOR_YB), tp(25.3))
        t253 = max(t253, 25.6)
        self.tpose.to(t253 + 0.12, (1.0, -0.08, 1.05), ease=out_q).to(t253 + 0.6, (1.0, 0.0, 1.0))
        tp.hold(t253).to(t253 + 0.4, (door_x - 55.0, LEV["RL3"]), ease=out_q)
        tp.hold(27.15).to(27.45, (door_x, LEV["RL3"]))
        self.tpose.hold(27.5)

        def knock(t0, k=1.0):
            self.tpose.hold(t0).to(t0 + 0.09, (1.0, 0.36 * k, 1.0), ease=out_q).to(t0 + 0.2, (1.0, 0.1, 1.0))
            self.knocks.append(t0 + 0.09)

        for tk in (27.6, 27.9, 28.2):
            knock(tk)
        for tk in (29.7, 30.0):
            knock(tk)
        knock(32.75, 1.25)
        self.tpose.hold(self.t_on)
        # la lumière sous la porte : il la fixe
        self.tlight.hold(-1)
        for tt, s in [(self.t_on, 1)] + list(zip(self.taps, (0, 1, 0))):
            self.tlight.hold(tt).to(tt + 0.06, float(s), ease=linear)
        self.tlight.hold(70)
        self.tpose.to(self.t_on + 0.3, (1.0, 0.22, 0.95)).hold(self.taps[0])
        for tt in self.taps:
            self.tpose.hold(tt).to(tt + 0.08, (1.0, 0.16, 1.06)).to(tt + 0.4, (1.0, 0.22, 0.95))
        # 37,0 : noir ; il baisse la pointe vers son cupcake, se retourne, redescend
        self.tpose.hold(37.0).to(37.35, (0.96, 0.3, 0.92)).hold(37.45)
        self.tface.hold(37.4).to(37.75, -1.0)
        self.tpose.to(37.75, (1.0, -0.12, 0.96))
        tp.hold(37.45).to(37.75, (RL_X - 15.0, LEV["RL3"]))
        t = 37.8
        for nm, gap in (("F3.3", 0.17), ("F3.2", 0.17), ("F3.1", 0.17)):
            t = step(t, nm, T=0.38, face=-1.0, lean=0.1) + gap
        t = step(t, "LL2", T=0.38, face=-1.0)
        self.tface.hold(t).to(t + 0.25, 1.0)
        tp.hold(t + 0.25)
        self.tlayer.set(t + 0.25, "back")
        t = t + 0.25
        for nm, gap in (("F2.3", 0.17), ("F2.2", 0.17), ("F2.1", 0.17)):
            t = step(t, nm, T=0.38, face=1.0, lean=0.1) + gap
        t = step(t, "RL1", T=0.42, face=1.0)
        # sur le palier, il avance à petits pas, la pointe basse ; il ne se retourne pas
        tp.hold(t).to(44.5, (TRI_END_X, LEV["RL1"]), ease=linear)
        self.tpose.hold(t + 0.3).to(t + 0.9, (0.97, 0.16, 0.95))
        self.t_tri_rl1 = t

    def ring_delay(self, t, src_salon, tri_world):
        """Le temps que l'anneau parti de src (salon) met à atteindre le triangle (vue coupée)."""
        rmax = 1000.0
        for (tr, w, rm, clip) in self.rings:
            if abs(tr - t) < 1e-6:
                rmax = rm
        v = ring_speed(rmax)
        sx, sy = cam_split_screen(tri_world[0], tri_world[1] - TH / 2, tri_world)
        d = math.hypot(sx - src_salon[0], sy - src_salon[1]) - TB * 2.5 / 2
        return max(0.05, d / v)

    # ================================================================ la fin
    def build_end(self):
        tp = self.tpos
        b = self.bpos
        tc = self.t_cup
        # le saut par-dessus le triangle, droit dans le cupcake
        cx, cy = self.cup_center(tc, state="ok")
        b.arc(tc, (cx, cy - 13.0 - RB), g=SG)
        self.hit(tc, "n", ring=800, world="T")
        self.cup_state.set(tc, "crushed")
        self.cup_lit.set(tc, False)
        self.head_candle.set(tc, "lit")
        self.cream.set(tc, True)
        # la balle dans ses mains : position relative au cupcake + petits sauts
        hop = Track(tc, (0.0, 0.0))
        self.hop = hop
        seq = [(47.66, 0.0, "n"), (48.6, 0.0, "n"), (49.8, 0.0, "p"), (50.9, 14.0, "n"), (52.2, 4.0, "n")]
        for (tt, dx, cls) in seq:
            hop.arc(tt, (dx, 0.0), g=SG)
            self.hit(tt, cls, ring=600 if cls == "n" else 300, world="T")
        b.fn(52.2, lambda t: self.in_hands(t))
        # 52,2 : il bondit droit dans le souffle, retombe sur le front du triangle, de travers
        p_front = self.tri_front_point(53.07)
        b.arc(53.07, p_front, g=SG)
        self.hit(53.07, "n", ring=600, world="T", axis="x")
        cxe, cye = self.cup_center(53.9, state="crushed")
        b.arc(53.9, (cxe, cye - 6.0 - RB), g=SG)
        self.hit(53.9, "n", ring=600, world="T")
        hop.hold(53.9)
        hop.set((0.0, 0.0))
        seq2 = [(54.8, "n", 600), (56.2, "p", 300), (57.6, "t", 260)]
        for (tt, cls, rr) in seq2:
            hop.arc(tt, (0.0, 0.0), g=SG)
            self.hit(tt, cls, ring=rr, world="T")
        self.head_candle.set(53.9, "out")
        b.fn(57.6, lambda t: self.in_hands(t))
        # le plus petit rebond, puis il reste dans la crème (noir)
        hop.to(57.66, (0.0, -4.0), ease=out_q).to(57.76, (0.0, 0.0), ease=linear).hold(60.2)
        b.fn(60.2, lambda t: self.in_hands(t))
        self.hit(60.2, "n", ring=1300, world="T")
        hop.arc(61.5, (0.0, 0.0), g=SG)
        hop.hold(63.0)
        b.fn(63.0, lambda t: self.in_hands(t))
        # le triangle
        tp.hold(70)
        tps = self.tpose
        tps.hold(tc)
        tps.to(tc + 0.15, (1.0, -0.06, 1.08), ease=out_q).to(tc + 0.5, (1.0, 0.0, 1.0)).hold(48.0)
        # 1er souffle
        tps.to(48.5, (1.15, 0.12, 1.0)).hold(48.68)
        self.breath.append((48.68, 49.25))
        tps.to(49.2, (1.0, 0.1, 1.0)).hold(49.25)
        # 2e souffle
        tps.to(49.75, (1.17, 0.14, 1.0)).hold(49.9)
        self.breath.append((49.9, 50.45))
        tps.to(50.45, (1.0, 0.1, 1.0)).hold(51.4)
        # 3e souffle, à toute vitesse
        tps.to(52.05, (1.2, 0.14, 1.0)).hold(52.12)
        self.breath.append((52.12, 52.75))
        tps.to(52.75, (1.0, 0.1, 1.0))
        # la balle sur son front : il recule la pointe
        tps.hold(53.07).to(53.19, (1.0, -0.05, 0.96), ease=out_q).to(53.5, (1.0, 0.12, 1.0))
        # il regarde la fumée
        tps.to(54.1, (0.98, 0.16, 0.94)).hold(54.8)
        # 54,8 : il se retourne
        self.tface.hold(54.8).to(55.4, -1.0)
        tps.to(55.4, (1.0, 0.0, 1.0)).to(56.0, (1.0, 0.0, 1.08))
        # 56,2 : il se penche vers les huit flammes et gonfle
        tps.hold(56.2).to(57.55, (1.38, -0.3, 1.0))
        tps.hold(59.0)
        # dans le noir il se dégonfle lentement
        tps.to(60.2, (1.18, -0.24, 1.0), ease=linear).hold(70)
        self.tface.hold(70)
        # les flammes du grand gâteau
        self.big_out = 57.9
        # la caméra de l'escalier
        # (calculée dans cam_stairs)
        self.build_friends_stairs()

    def tri_frame(self, t):
        """(base, hauteur, local->monde) : le triangle pivote sur le coin du côté où il penche."""
        x, y = self.tpos(t)
        inf, tilt, st = self.tpose(t)
        b, h = TB * inf, TH * inf * st
        px = x + (b / 2 if tilt > 0 else -b / 2)
        ca, sa = math.cos(tilt), math.sin(tilt)

        def to_w(lx, ly):
            dx, dy = x + lx - px, ly
            return (px + dx * ca - dy * sa, y + dx * sa + dy * ca)
        return b, h, to_w, (ca, sa)

    def cup_center(self, t, state=None):
        """Centre du cupcake (monde de l'escalier) : tenu devant le triangle, côté du regard,
        attaché à son corps (il suit son inclinaison)."""
        b, h, to_w, _ = self.tri_frame(t)
        st = self.tpose(t)[2]
        f = self.tface(t)[0]
        sl = self.cup_slide(t)[0]
        up = 0.0
        if t > 54.8:
            up = smooth((t - 54.8) / 0.8) * 60.0
        hh = 50.0 * st + up
        half = b / 2 * max(0.0, 1 - hh / h)
        return to_w(f * (half + 34.0 + 12.0 * sl), -hh)

    def in_hands(self, t):
        cx, cy = self.cup_center(t)
        dx, dy = self.hop(t)
        return (cx + dx * self.tface(t)[0], cy - 6.0 - RB + dy)

    def tri_front_point(self, t):
        """Où la balle touche le « front » du triangle (sa pente, côté du regard)."""
        b, h, to_w, (ca, sa) = self.tri_frame(t)
        f = self.tface(t)[0]
        hh = 0.72 * h
        half = b / 2 * (1 - hh / h)
        px, py = to_w(f * half, -hh)
        L = math.hypot(b / 2, h)
        nx, ny = f * h / L, -(b / 2) / L
        nx, ny = nx * ca - ny * sa, nx * sa + ny * ca
        return (px + nx * (RB + 1.0), py + ny * (RB + 1.0))

    def build_friends_stairs(self):
        """Les amis dans l'escalier : ils apparaissent ensemble dans l'encadrement de la porte,
        puis descendent en file indienne, marche par marche, derrière le triangle ; ils se
        figent, une jambe en l'air, chaque fois qu'il bouge la pointe."""
        k = 0.52
        self.fk = k
        FS = {}
        sizes = {"green": (80, 210), "blue": (105, 105), "yellow": (105, 105), "orange": (90, 90)}
        order = ["green", "blue", "yellow", "orange"]
        y3 = LEV["RL3"]
        for i, nm in enumerate(order):
            w, h = sizes[nm]
            f = Friend(nm, w * k, h * k, -1, SW_R + 18.0 + 26.0 * i, y3, 1.0)
            f.layer.set(-1, "door")
            f.world.set(-1, None)
            f.arms.set(-1, "up" if nm == "green" else None)
            FS[nm] = f
        self.FS = FS
        self.sdoor.hold(38.62).to(38.85, 1.0, ease=out_q)
        # 44,4 : ils apparaissent dans l'encadrement de la porte
        for i, nm in enumerate(order):
            f = FS[nm]
            f.world.set(44.0 + 0.12 * i, "T")
            x_door = SW_R + 18.0 + 26.0 * i
            f.pos.set((x_door + 70.0, f.cy_for(y3, 1.0)))
            f.pos.hold(44.0 + 0.12 * i).to(44.45 + 0.12 * i, (x_door, f.cy_for(y3, 1.0)), ease=out_q)
        path = ["RL3", "F3.3", "F3.2", "F3.1", "LL2", "F2.3", "F2.2", "F2.1"]
        final = {"green": 7, "blue": 6, "yellow": 5, "orange": 5}
        lag = {"green": 0, "blue": 3, "yellow": 5, "orange": 7}
        xoff = {"yellow": 27.0, "orange": -27.0}
        freeze = [(48.4, 49.3), (49.7, 50.5), (51.9, 52.8)]
        # la file : au créneau n, l'ami i va à la case n - i
        slots = []
        tt = 45.9
        while len(slots) < 14:
            for (a, bnd) in freeze:
                if a - 0.32 < tt < bnd:
                    tt = bnd
            slots.append(tt)
            tt += 0.45
        self.friend_slots = slots
        T = 0.36
        for i, nm in enumerate(order):
            f = FS[nm]
            cur = -1
            for n, ts in enumerate(slots):
                j = min(n - lag[nm], final[nm])
                if j <= cur or j < 0:
                    continue
                spot = path[j]
                x, y = self.spot(spot)
                if spot == "RL3":
                    x = RL_X - 30.0
                if j == final[nm] and nm in xoff:
                    x += xoff[nm]
                tgt = (x, f.cy_for(y, 1.0))
                f.pos.hold(ts)
                f.pose.hold(ts)
                hop_h = 16.0
                g = max(SG, 2 * (2 * hop_h + (tgt[1] - f.pos(ts)[1])) / (T * T))
                f.pos.arc(ts + T, tgt, g=g)
                if cur < 0:
                    f.layer.set(ts, "stairs")
                cur = j
            f.arrive = f.pos.t
            # figés une jambe en l'air pendant les gestes du triangle (ceux qui marchent encore)
            for (a, bnd) in freeze:
                if a < f.arrive + 0.2:
                    f.leg.set(a, 1 if i % 2 else -1)
                    f.leg.set(bnd, 0)
            f.pos.hold(70)
            f.pose.hold(54.8)
            # 55,0 : ils tendent le gâteau ; 56,2 : ils se penchent avec lui
            f.pose.to(max(56.4, f.pose.t + 0.2), (1.0, 1.0, 0.0)).to(57.5, (1.0, 1.0, -0.16)).hold(59.0)
            # 60,2 : tous tournés vers la balle
            f.pose.to(59.6, (1.0, 1.0, 0.2)).hold(70)
        self.t_friends_done = max(f.arrive for f in FS.values())


# ------------------------------------------------------------------ l'anneau
def ring_speed(rmax):
    return 500.0 + rmax * 0.9


def ring_state(t, tr, rmax):
    """(rayon, intensité 0..1) de l'anneau parti à tr, ou None s'il est fini."""
    v = ring_speed(rmax)
    age = t - tr
    if age < 0:
        return None
    r = 0.9 * R + v * age
    if r > rmax:
        return None
    u = r / rmax
    return r, (1 - u) ** 0.8


# ------------------------------------------------------------------ caméras
SPLIT_ANCHOR = (540.0, 1400.0)
ZS, ZF, ZE = 2.5, 1.42, 2.1
FULL_C = (376.0, 760.0)
END_C = (470.0, 800.0)
T_TR0, T_TR1 = 38.75, 39.55
T_Z0, T_Z1 = 46.0, 48.3


def cam_split_screen(x, y, tri):
    return (SPLIT_ANCHOR[0] + (x - tri[0]) * ZS, SPLIT_ANCHOR[1] + (y - (tri[1] - 60.0)) * ZS)


class Cams:
    def __init__(self, plan):
        self.p = plan
        # le suivi du triangle (vue coupée), lissé
        ts = np.arange(-1.0, 40.0, 1 / 60.0)
        raw = np.array([plan.tpos(t) for t in ts])
        sm = raw.copy()
        k = 1 - math.exp(-(1 / 60.0) / 0.35)
        for i in range(1, len(ts)):
            sm[i] = sm[i - 1] + (raw[i] - sm[i - 1]) * k
        self.fts, self.fsm = ts, sm

    def follow(self, t):
        i = int(min(len(self.fts) - 1, max(0, (t + 1.0) * 60.0)))
        x, y = self.fsm[i]
        return (float(x), float(y) - 60.0)

    def stairs(self, t):
        """(cx, cy, z, ax, ay) : le point du monde au centre, le zoom, l'ancre à l'écran."""
        if t < T_TR0:
            c = self.follow(t)
            return (c[0], c[1], ZS, SPLIT_ANCHOR[0], SPLIT_ANCHOR[1])
        if t < T_TR1:
            c0 = self.follow(T_TR0)
            u = smooth((t - T_TR0) / (T_TR1 - T_TR0))
            z = ZS + (ZF - ZS) * u
            return (c0[0] + (FULL_C[0] - c0[0]) * u, c0[1] + (FULL_C[1] - c0[1]) * u, z,
                    540.0, SPLIT_ANCHOR[1] + (960.0 - SPLIT_ANCHOR[1]) * u)
        if t < T_Z0:
            return (FULL_C[0], FULL_C[1], ZF, 540.0, 960.0)
        u = smooth((t - T_Z0) / (T_Z1 - T_Z0))
        uc = clamp01((t - T_Z0) / (T_Z1 - T_Z0)) ** 0.5
        uc = smooth(uc)
        return (FULL_C[0] + (END_C[0] - FULL_C[0]) * uc, FULL_C[1] + (END_C[1] - FULL_C[1]) * uc,
                ZF + (ZE - ZF) * u, 540.0, 960.0)

    def salon_dy(self, t):
        if t < T_TR0:
            return 0.0
        u = smooth((t - T_TR0) / 0.85)
        return -(PANEL_Y + 40.0) * u

    def panel_top(self, t):
        return PANEL_Y + self.salon_dy(t)


class View:
    def __init__(self, S, cx=0.0, cy=0.0, z=1.0, ax=0.0, ay=0.0, dy=0.0, salon=False, oy=0.0):
        self.S, self.cx, self.cy, self.z, self.ax, self.ay, self.dy, self.salon = S, cx, cy, z, ax, ay, dy, salon
        self.oy = oy

    def X(self, x):
        if self.salon:
            return x * self.S
        return (self.ax + (x - self.cx) * self.z) * self.S

    def Y(self, y):
        if self.salon:
            return (y + self.dy) * self.S - self.oy
        return (self.ay + (y - self.cy) * self.z) * self.S - self.oy

    def L(self, l):
        return l * (1.0 if self.salon else self.z) * self.S

    def P(self, pts):
        return [(self.X(x), self.Y(y)) for x, y in pts]

    def scr(self, x, y):
        """Coordonnées écran (sans supersampling)."""
        if self.salon:
            return (x, y + self.dy)
        return (self.ax + (x - self.cx) * self.z, self.ay + (y - self.cy) * self.z)

    def box(self, x0, y0, x1, y1):
        a, b = self.X(x0), self.Y(y0)
        c, d = self.X(x1), self.Y(y1)
        return [min(a, c), min(b, d), max(a, c), max(b, d)]


# ------------------------------------------------------------------ dessin
def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rot_pts(pts, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def flame_pts(x, y, h, w, lean=0.0, n=14):
    """Une flamme en goutte, base en (x, y), pointe en haut, penchée de `lean` rad."""
    pts = []
    for k in range(n + 1):
        u = k / n
        a = math.pi * u
        # profil : large en bas, pointu en haut
        px = math.sin(a) * w / 2 * (1 - 0.15 * u)
        py = -h * (1 - math.cos(a)) / 2
        pts.append((px, py))
    full = [(px, py) for px, py in pts] + [(-px, py) for px, py in reversed(pts)]
    ca, sa = math.cos(lean), math.sin(lean)
    return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in full]


def draw_flame(dr, V, x, y, h, w, lean, k_light=1.0):
    if h <= 0.5:
        return
    outer = mix((255, 120, 30), (255, 190, 80), 0.3)
    dr.polygon(V.P(flame_pts(x, y, h, w, lean)), fill=outer)
    dr.polygon(V.P(flame_pts(x, y - h * 0.05, h * 0.6, w * 0.55, lean)), fill=(255, 236, 160))


def draw_ring_poly(dr, cx, cy, r, w, col, S, clip=None, n=None):
    """Un anneau en polyligne (coordonnées écran), coupé sous `clip` si donné."""
    n = n or max(40, min(240, int(r / 4)))
    pts = []
    for k in range(n + 1):
        a = 2 * math.pi * k / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    width = max(1, int(w * S))
    if clip is None:
        dr.line([(x * S, y * S) for x, y in pts], fill=col, width=width, joint="curve")
        return
    run = []
    for (x, y) in pts:
        if y <= clip:
            run.append((x * S, y * S))
        else:
            if len(run) > 1:
                dr.line(run, fill=col, width=width)
            run = []
    if len(run) > 1:
        dr.line(run, fill=col, width=width)


def hat_pts(x, top, w, h):
    return [(x - w / 2, top), (x + w / 2, top), (x, top - h)]


class Scene(Chapter):
    """La vidéo entière, comme un seul chapitre (son titre est l'accroche)."""
    title = None
    stamp = None
    mood = None
    exit_ok = False
    bodies_exit_ok = True        # les amis sortent du cadre par la porte et dans l'escalier

    def setup(self):
        self.P = Plan(self.cfg)
        self.C = Cams(self.P)
        self.CHUTE = 4.4
        self.hold_s = self.P.END - self.CHUTE
        self.lines = [(0.0, self.cfg["hook_text"].strip().lower().capitalize(), "title")]
        self.hit_times = [h[0] for h in self.P.hits]
        self.ki = 0
        self.R = R

    def step(self, dt):
        self.t += dt
        evs = []
        while self.ki < len(self.hit_times) and self.hit_times[self.ki] <= self.t + 1e-9:
            evs.append(("hit", "floor"))
            self.ki += 1
        if self.t >= self.CHUTE - 1e-9:
            self.finish("SURPRISE")
        return evs

    def snapshot(self):
        return {"t": self.t, "end": self.end_t, "on": "air", "bx": 0.0, "by": 0.0}

    # ---------------------------------------------------------- état de Bounce
    def squash(self, t, world):
        sx, sy = self.P.bsq(t)
        anchor = "bottom"
        for (tc, w, axis, amp) in self.P.contacts:
            if w != world:
                continue
            u = t - tc
            if -0.05 <= u <= 0.12:
                kk = clamp01(1 + u / 0.05) if u < 0 else clamp01(1 - u / 0.12)
                if axis == "y":
                    sy *= 1 - amp * kk
                    sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk
                    sy *= 1 + 0.6 * amp * kk
                    anchor = "side"
        return sx, sy, anchor

    def ball_state(self, t):
        """(monde, x, y du centre dessiné, rx, ry, échelle) ou None."""
        P = self.P
        if not P.bvis(t):
            return None
        w = P.bworld(t)
        x, y = P.bpos(t)[:2]
        r = R if w == "S" else RB
        sx, sy, anchor = self.squash(t, w)
        sc = P.bscale(t)[0]
        if anchor == "bottom" and sy < 1.0:
            y = y + r * (1 - sy)
        return (w, x, y, r * sx * sc, r * sy * sc, sc)

    def ball_screen(self, t):
        bs = self.ball_state(t)
        if bs is None:
            return None
        w, x, y, rx, ry, sc = bs
        if w == "S":
            dy = self.C.salon_dy(t)
            return (x, y + dy, rx, ry)
        cx, cy, z, ax, ay = self.C.stairs(t)
        return (ax + (x - cx) * z, ay + (y - cy) * z, rx * z, ry * z)

    # ---------------------------------------------------------- contrôle
    def hero(self, s):
        t = s["t"]
        bsc = self.ball_screen(t)
        if bsc is None or self.dark(t) > 0.97:
            return None
        x, y, rx, ry = bsc
        return (x, y, min(rx, ry))

    def solids(self, s):
        t = s["t"]
        out = []
        dy = self.C.salon_dy(t)
        if dy > -FLOOR:
            out.append(("rect", 0.0, FLOOR + dy, float(W), PANEL_Y + dy))
            out.append(("rect", WALL_R, CEIL + dy, float(W), FLOOR + dy))
            if t < 16.0:
                out.append(("rect", SOFA_X0 + ARM_W, SEAT_TOP + dy, SOFA_X1 - ARM_W, FLOOR + dy))
            out.append(("rect", TABLE_X0, TABLE_TOP + dy, TABLE_X1, TABLE_TOP + 16 + dy))
            if self.P.bworld(t) == "S":
                for nm, f in self.P.F.items():
                    if f.world(t) == "S" and f.layer(t) == "front":
                        out.append(("poly", [(x, y + dy) for x, y in f.poly(t)]))
        if self.P.bworld(t) == "T":
            cx, cy, z, ax, ay = self.C.stairs(t)
            V = lambda x, y: (ax + (x - cx) * z, ay + (y - cy) * z)
            bw = self.ball_state(t)
            if bw is not None:
                for (x0, x1, y) in self.treads_near(t):
                    a = V(x0, y)
                    b2 = V(x1, y + 30.0)
                    out.append(("rect", a[0], a[1], b2[0], b2[1]))
                # la balle passe devant lui quand il se retourne (54,8–55,4) : pas un contact
                if (t < 46.6 or t > 47.0) and not (54.75 < t < 55.5):
                    out.append(("poly", [V(x, y) for x, y in self.tri_poly(t)]))
        return out

    def treads_near(self, t):
        """Les marches du plan où roule la balle (volée de devant, puis volée du fond)."""
        res = []
        fls = ("F3",) if t < 42.3 else ("F2",)
        for fl in fls:
            for k in range(1, STEPS + 1):
                x0, x1, y = self.P.tread(fl, k)
                res.append((x0, x1, y))
        res.append((0.0, FX0, LEV["LL2"]))
        res.append((FX1, SW_R, LEV["RL3"] if t < 42.3 else LEV["RL1"]))
        return res

    def bodies(self, s):
        t = s["t"]
        out = []
        dy = self.C.salon_dy(t)
        if dy > -PANEL_Y + 20:
            for i, (nm, f) in enumerate(self.P.F.items()):
                if f.world(t) == "S":
                    pts = [(x, y + dy) for x, y in f.poly(t)]
                    x, y = f.pos(t)[:2]
                    if f.layer(t) == "front":
                        out.append((f"s-{nm}", x, y + dy, f.pose(t)[2], pts))
                    else:
                        # derrière le dossier : contraint, pas un corps libre
                        out.append((f"s-{nm}", x, y + dy, f.pose(t)[2]))
            if self.P.cush_vis(t):
                x, y, a = self.P.cush(t)
                out.append(("cushion", x, y + dy, a, rot_pts(rect_pts(x - 58, y - 22, x + 58, y + 22), x, y, a)))
        if t > T_TR0 - 0.5:
            cx, cy, z, ax, ay = self.C.stairs(t)
            V = lambda x, y: (ax + (x - cx) * z, ay + (y - cy) * z)
            tp = [V(x, y) for x, y in self.tri_poly(t)]
            x, y = self.P.tpos(t)
            out.append(("triangle", *V(x, y), self.P.tpose(t)[1], tp))
            for nm, f in self.P.FS.items():
                if f.world(t) == "T":
                    pts = [V(x, y) for x, y in f.poly(t)]
                    x, y = f.pos(t)[:2]
                    if f.layer(t) == "stairs":
                        out.append((f"t-{nm}", *V(x, y), f.pose(t)[2], pts))
                    else:
                        # dans l'encadrement de la porte, les uns derrière les autres
                        out.append((f"t-{nm}", *V(x, y), f.pose(t)[2]))
        return out

    def focus(self, s):
        t = s["t"]
        bsc = self.ball_screen(t)
        if bsc is None:
            return (420.0, 900.0, 520.0, 1000.0)
        x, y, rx, ry = bsc
        return (x - rx, y - ry, x + rx, y + ry)

    # ---------------------------------------------------------- géométrie du triangle
    def tri_poly(self, t):
        x, y = self.P.tpos(t)
        inf, tilt, st = self.P.tpose(t)
        b, h = TB * inf, TH * inf * st
        pts = [(x - b / 2, y), (x + b / 2, y), (x, y - h)]
        # il pivote sur le coin du côté où il penche
        px = x + (b / 2 if tilt > 0 else -b / 2)
        return rot_pts(pts, px, y, tilt)

    def dark(self, t):
        """Le noir de la fin : 0 = vu, 1 = noir total."""
        if t < 57.9:
            return 0.0
        if t < 58.0:
            return (t - 57.9) / 0.1
        if t < 60.2:
            return 1.0
        if t < 61.5:
            u = (t - 60.2)
            return clamp01(1 - 0.75 * math.exp(-u / 0.5)) if u > 0.05 else 1 - u / 0.05 * 0.75
        return 1.0

    # ---------------------------------------------------------- dessin
    def draw(self, dr, s, tl, S):
        t = s["t"]
        dr.rectangle([0, 0, W * S, H * S], fill=BG)
        top = self.C.panel_top(t)
        if top > -10:
            self.draw_salon(dr, t, S)
        if top < H:
            # l'escalier : sur son propre calque, collé sous le plancher du salon
            img = dr._image
            top_px = max(0, int(round(top * S)))
            if img.height - top_px > 0:
                layer = Image.new("RGB", (img.width, img.height - top_px), BG)
                self.draw_stairs(ImageDraw.Draw(layer), t, S, top_px)
                img.paste(layer, (0, top_px))
        self.draw_rings(dr, t, S)

    # ---- le salon
    def light(self, t):
        return self.P.room(t)[0]

    def flicker(self, t):
        return 0.92 + 0.05 * math.sin(t * 13.1) + 0.03 * math.sin(t * 29.7 + 1.3)

    def halo_k(self, x, y, t):
        d = math.hypot(x - HALO[0], (y - HALO[1]) * 1.15)
        return clamp01(1 - d / 1150.0) ** 1.2 * 0.85 * self.flicker(t) * self.cake_lit_frac(t)

    def cake_lit_frac(self, t):
        n = sum(1 for k in range(8) if self.candle_h(k, t) > 0.3)
        return 0.35 + 0.65 * n / 8.0

    def lit(self, dark_c, lit_c, x, y, t):
        L = self.light(t)
        h = self.halo_k(x, y, t)
        warm = mix(dark_c, mix(lit_c, WARM, 0.35), h)
        return mix(warm, lit_c, L)

    def candle_h(self, k, t):
        """Hauteur relative de la flamme k du gâteau (0 = éteinte)."""
        P = self.P
        if t >= P.big_out:
            return 0.0
        h = 1.0 + 0.08 * math.sin(t * 17 + k * 1.7) + 0.05 * math.sin(t * 31 + k)
        if k == 7 and P.cdl_free(t):
            return h
        # 12,5 : toutes se couchent ; la n°3 s'éteint presque
        u = t - (P.tbig - 0.25)
        if 0 <= u < 0.9 and k == 3:
            h *= 0.12 + 0.88 * smooth((u - 0.5) / 0.4)
        # 22,7 : trois vacillent, une s'éteint et se rallume
        u = t - 22.78
        if 0 <= u < 1.0 and k in (4, 5, 6):
            h *= 0.6 + 0.4 * abs(math.sin(u * 20))
            if k == 5:
                h *= 0.0 if u < 0.45 else smooth((u - 0.45) / 0.3)
        return h

    def candle_lean(self, t):
        P = self.P
        u = t - (P.tbig - 0.25)
        lean = 0.0
        if 0 <= u < 1.0:
            lean = 1.1 * math.sin(math.pi * clamp01(u / 0.9)) * (1 if u < 0.45 else 0.8)
        u = t - 22.78
        if 0 <= u < 0.7:
            lean += 0.5 * math.sin(u * 14) * (1 - u / 0.7)
        return lean

    def draw_salon(self, dr, t, S):
        P = self.P
        dy = self.C.salon_dy(t)
        V = View(S, dy=dy, salon=True)
        L = self.light(t)
        # le mur, le halo doré
        dr.rectangle(V.box(0, -40, W, PANEL_Y), fill=BG)
        dr.rectangle(V.box(0, CEIL, W, FLOOR), fill=mix(WALL_D, WALL_L, L))
        fl = self.flicker(t) * self.cake_lit_frac(t)
        if L < 0.99:
            for k in range(22, 0, -1):
                r = 1000.0 * k / 22
                c = mix(WALL_D, mix(WALL_L, WARM, 0.5), (1 - k / 22) ** 1.5 * 0.85 * fl)
                c = mix(c, WALL_L, L)
                dr.ellipse(V.box(HALO[0] - r, HALO[1] - r * 0.87, HALO[0] + r, HALO[1] + r * 0.87), fill=c)
            dr.rectangle(V.box(-60, CEIL - 400, W, CEIL), fill=BG)
        # mur de droite
        dr.rectangle(V.box(WALL_R, CEIL, W, FLOOR), fill=mix((12, 10, 16), (60, 54, 66), L))
        dr.rectangle(V.box(WALL_R, CEIL, WALL_R + 8, FLOOR), fill=mix((30, 26, 36), (120, 110, 130), max(L, 0.2)))
        # plafond (trait)
        dr.rectangle(V.box(0, CEIL - 6, W, CEIL), fill=mix((40, 34, 44), (130, 120, 140), max(L, self.halo_k(300, CEIL, t))))
        # la banderole, éclairée par le large halo doré
        self.draw_banner(dr, V, t)
        # la porte, l'interrupteur
        self.draw_door(dr, V, t)
        self.draw_switch(dr, V, t)
        # la table et le gâteau
        self.draw_table(dr, V, t)
        # le sol
        dr.rectangle(V.box(0, FLOOR, W, PANEL_Y), fill=mix(FLOOR_D, FLOOR_L, max(L, 0.0)))
        dr.rectangle(V.box(0, FLOOR, W, FLOOR + 6), fill=mix((44, 34, 36), (130, 104, 90), max(L, self.halo_k(200, FLOOR, t))))
        # les amis derrière le canapé
        for f in P.F.values():
            if f.world(t) == "S" and f.layer(t) == "back":
                self.draw_friend(dr, V, f, t, salon=True)
        self.draw_sofa(dr, V, t)
        # devant
        for f in P.F.values():
            if f.world(t) == "S" and f.layer(t) == "front":
                self.draw_friend(dr, V, f, t, salon=True)
        if P.cdl_free(t):
            x, y, a = P.cdl(t)
            self.draw_candle(dr, V, x, y, a, t, lit=True)
        bs = self.ball_state(t)
        if bs is not None and bs[0] == "S":
            self.draw_ball(dr, V, t, bs)
        # le vert assis dessus : dessiné après la balle
        gr = P.F["green"]
        if 10.4 < t < 12.55:
            self.draw_friend(dr, V, gr, t, salon=True)
        # le coussin
        if P.cush_vis(t):
            x, y, a = P.cush(t)
            self.draw_cushion(dr, V, x, y, a, t)
        if 3.4 < t < 9.7:
            self.draw_friend(dr, V, P.F["blue"], t, salon=True, arms_only=True)
        # le plancher en coupe, au-dessus de l'escalier
        dr.rectangle(V.box(0, FLOOR + 6, W, PANEL_Y), fill=mix((30, 24, 28), (96, 76, 66), L))
        for xx in range(-40, W + 40, 90):
            dr.line([(V.X(xx), V.Y(FLOOR + 22)), (V.X(xx + 60), V.Y(FLOOR + 22))], fill=mix((40, 32, 36), (110, 90, 80), L), width=max(1, int(3 * S)))
        dr.rectangle(V.box(0, PANEL_Y - 6, W, PANEL_Y), fill=(4, 4, 6))

    def draw_banner(self, dr, V, t):
        L = self.light(t)
        fl = self.flicker(t) * self.cake_lit_frac(t)
        bx0, by0, bx1, by1 = 120.0, 405.0, 820.0, 505.0
        # halo doré propre à la banderole
        if L < 0.99:
            for k in range(7, 0, -1):
                rx = 470.0 * k / 7
                c = mix(WALL_D, (150, 112, 46), (1 - k / 7) ** 1.1 * 0.55 * fl)
                base_c = mix(WALL_D, mix(WALL_L, WARM, 0.45), self.halo_k(470, 455, t))
                c = mix(base_c, (170, 124, 52), (1 - k / 7) ** 1.1 * 0.62 * fl)
                c = mix(c, WALL_L, L)
                dr.ellipse(V.box(470 - rx, 455 - rx * 0.36, 470 + rx, 455 + rx * 0.36), fill=c)
        # cordes
        rope = mix((90, 70, 40), (200, 180, 140), max(L, 0.5 * fl))
        dr.line([(V.X(20), V.Y(360)), (V.X(bx0), V.Y(by0))], fill=rope, width=max(1, int(V.L(4))))
        dr.line([(V.X(900), V.Y(360)), (V.X(bx1), V.Y(by0))], fill=rope, width=max(1, int(V.L(4))))
        cloth_d = (70, 30, 40)
        cloth = mix(mix(cloth_d, (190, 60, 80), 0.55 * fl), (200, 64, 86), L)
        pts = []
        n = 24
        for k in range(n + 1):
            u = k / n
            pts.append((bx0 + (bx1 - bx0) * u, by0 + 14 * math.sin(math.pi * u)))
        for k in range(n, -1, -1):
            u = k / n
            pts.append((bx0 + (bx1 - bx0) * u, by1 + 14 * math.sin(math.pi * u)))
        dr.polygon(V.P(pts), fill=cloth)
        # fanions
        for k in range(10):
            u = (k + 0.5) / 10
            x = bx0 + (bx1 - bx0) * u
            y = by1 + 14 * math.sin(math.pi * u)
            c = [(255, 200, 60), (80, 200, 240), (120, 230, 120)][k % 3]
            c = mix(dim(c, 0.35), c, max(L, 0.55 * fl))
            dr.polygon(V.P([(x - 22, y), (x + 22, y), (x, y + 30)]), fill=c)
        f = base.font(V.L(66))
        txt = "HAPPY BIRTHDAY"
        col = mix(mix((120, 96, 50), GOLD, 0.85 * fl), (255, 236, 140), L)
        dr.text((V.X((bx0 + bx1) / 2), V.Y((by0 + by1) / 2 + 10)), txt, fill=col, anchor="mm", font=f,
                stroke_width=max(1, int(V.L(3))), stroke_fill=(40, 16, 20))

    def draw_door(self, dr, V, t):
        L = self.light(t)
        x0, y0, x1, y1 = DOOR
        frame = self.lit((30, 24, 30), (150, 120, 96), x0, y0 + 100, t)
        dr.rectangle(V.box(x0 - 10, y0 - 10, x1 + 10, y1), fill=frame)
        # l'ouverture (l'escalier, sombre)
        dr.rectangle(V.box(x0, y0, x1, y1), fill=(10, 10, 16))
        op = self.P.door(t)[0]
        # tremblements quand le triangle frappe
        sh = 0.0
        for tk in self.P.knocks:
            u = t - tk
            if 0 <= u < 0.18:
                sh += 3.0 * math.sin(u * 90) * (1 - u / 0.18)
        wd = (x1 - x0) * (1 - 0.86 * op)
        panel = self.lit((44, 30, 26), (156, 104, 66), x0, y0 + 100, t)
        dr.rectangle(V.box(x0 + sh, y0, x0 + wd + sh, y1), fill=panel)
        if op < 0.5:
            dr.rectangle(V.box(x0 + 14 + sh, y0 + 18, x0 + wd - 14 + sh, y0 + 120), outline=dim(panel, 0.7), width=max(1, int(V.L(4))))
            dr.rectangle(V.box(x0 + 14 + sh, y0 + 140, x0 + wd - 14 + sh, y1 - 18), outline=dim(panel, 0.7), width=max(1, int(V.L(4))))
            hx, hy = HANDLE
            dr.ellipse(V.box(hx - 9 + sh, hy - 9, hx + 9 + sh, hy + 9), fill=self.lit((90, 80, 50), (230, 200, 110), hx, hy, t))

    def draw_switch(self, dr, V, t):
        x0, y0, x1, y1 = SWITCH
        plate = self.lit((50, 46, 52), (220, 214, 200), x0, y0, t)
        dr.rounded_rectangle(V.box(x0, y0, x1, y1), radius=V.L(8), fill=plate, outline=dim(plate, 0.6), width=max(1, int(V.L(3))))
        on = self.P.sw(t)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lever = mix((70, 66, 70), (250, 248, 240), max(self.light(t), 0.35))
        if on:
            dr.rectangle(V.box(cx - 12, cy - 30, cx + 12, cy + 2), fill=lever, outline=dim(plate, 0.4), width=max(1, int(V.L(2))))
        else:
            dr.rectangle(V.box(cx - 12, cy - 2, cx + 12, cy + 30), fill=lever, outline=dim(plate, 0.4), width=max(1, int(V.L(2))))

    def draw_table(self, dr, V, t):
        P = self.P
        top = self.lit(WOOD_D, WOOD_L, 150, TABLE_TOP, t)
        leg = dim(top, 0.75)
        for lx in (26.0, 248.0):
            dr.rectangle(V.box(lx, TABLE_TOP + 10, lx + 16, FLOOR), fill=leg)
        dr.rectangle(V.box(TABLE_X0, TABLE_TOP, TABLE_X1, TABLE_TOP + 16), fill=top)
        # le gâteau (il tangue à 22,7)
        rock = 0.0
        u = t - 22.7
        if 0 <= u < 1.2:
            rock = 0.06 * math.sin(u * 15) * math.exp(-u * 3)
        self.draw_cake(dr, V, (CAKE_X0 + CAKE_X1) / 2, TABLE_TOP, 1.0, rock, t, salon=True)

    def draw_cake(self, dr, V, cx, bottom, k, rock, t, salon=False, lit_k=None):
        """Le grand gâteau, posé en (cx, bottom), échelle k, huit bougies."""
        L = self.light(t) if salon else 0.0
        hw, hh = 65.0 * k, 82.0 * k
        pivot = (cx, bottom)

        def R_(pts):
            return rot_pts(pts, pivot[0], pivot[1], rock)
        if lit_k is None:
            body = mix(mix((70, 40, 46), (236, 150, 170), 0.6 * self.flicker(t)), (240, 160, 180), L)
            icing = mix(mix((90, 80, 80), (255, 244, 236), 0.7), (255, 250, 244), L)
        else:
            body = mix((0, 0, 0), (236, 150, 170), lit_k)
            icing = mix((0, 0, 0), (255, 244, 236), lit_k)
        dr.polygon(V.P(R_(rect_pts(cx - hw, bottom - hh, cx + hw, bottom))), fill=body)
        dr.polygon(V.P(R_(rect_pts(cx - hw, bottom - hh, cx + hw, bottom - hh + 18 * k))), fill=icing)
        for j in range(7):
            x = cx - hw + (j + 0.5) * 2 * hw / 7
            dr.polygon(V.P(R_([(x - 8 * k, bottom - hh + 16 * k), (x + 8 * k, bottom - hh + 16 * k), (x, bottom - hh + 32 * k)])), fill=icing)
        dr.polygon(V.P(R_(rect_pts(cx - hw, bottom - hh * 0.45, cx + hw, bottom - hh * 0.45 + 8 * k))), fill=dim(body, 0.8))
        lean = self.candle_lean(t)
        for j in range(8):
            if salon and j == 7 and (self.P.cdl_free(t)):
                continue
            x = cx - hw + 12 * k + j * (2 * hw - 24 * k) / 7
            y0 = bottom - hh
            stick = [((255, 120, 150), (120, 200, 255), (255, 220, 90))[j % 3]][0]
            stick = mix(dim(stick, 0.4), stick, max(L, 0.7) if lit_k is None else lit_k)
            dr.polygon(V.P(R_(rect_pts(x - 4.5 * k, y0 - 36 * k, x + 4.5 * k, y0))), fill=stick)
            fh = self.candle_h(j, t)
            if fh > 0.02:
                px, py = rot_pts([(x, y0 - 36 * k)], pivot[0], pivot[1], rock)[0]
                draw_flame(dr, V, px, py, 34 * k * fh, 15 * k, lean + rock)
            elif t >= self.P.big_out:
                # la mèche rougeoie
                px, py = rot_pts([(x, y0 - 36 * k)], pivot[0], pivot[1], rock)[0]
                g = 0.65 + 0.35 * math.sin(t * 5 + j * 1.3)
                fade = clamp01(1 - (t - 61.5) / 0.05) if t > 61.5 else 1.0
                rr = 4.5 * k
                dr.ellipse(V.box(px - rr * 2.2, py - rr * 2.2, px + rr * 2.2, py + rr * 2.2), fill=mix(BG, (90, 18, 8), g * fade))
                dr.ellipse(V.box(px - rr, py - rr * 1.4, px + rr, py + rr * 0.6), fill=mix(BG, (255, 70, 30), g * fade))

    def draw_candle(self, dr, V, x, y, a, t, lit=True, k=1.0):
        pts = rot_pts(rect_pts(x - 4.5 * k, y - 18 * k, x + 4.5 * k, y + 18 * k), x, y, a)
        dr.polygon(V.P(pts), fill=(120, 200, 255))
        if lit:
            tx, ty = rot_pts([(x, y - 18 * k)], x, y, a)[0]
            draw_flame(dr, V, tx, ty, 30 * k, 14 * k, a * 0.3)

    def draw_sofa(self, dr, V, t):
        c = self.lit(SOFA_D, SOFA_L, 500, 1000, t)
        cd = dim(c, 0.78)
        dr.rounded_rectangle(V.box(SOFA_X0 + 15, BACK_TOP, SOFA_X1 - 15, SEAT_TOP + 10), radius=V.L(18), fill=cd)
        dr.rectangle(V.box(SOFA_X0, SEAT_TOP, SOFA_X1, 1078), fill=c)
        for k in range(2):
            x0 = SOFA_X0 + ARM_W + k * (SOFA_X1 - SOFA_X0 - 2 * ARM_W) / 2
            x1 = x0 + (SOFA_X1 - SOFA_X0 - 2 * ARM_W) / 2
            dr.rounded_rectangle(V.box(x0 + 3, SEAT_TOP, x1 - 3, SEAT_TOP + 28), radius=V.L(10), fill=mix(c, (255, 255, 255), 0.08))
        for ax in (SOFA_X0, SOFA_X1 - ARM_W):
            dr.rounded_rectangle(V.box(ax, ARM_TOP, ax + ARM_W, 1078), radius=V.L(14), fill=dim(c, 0.9))
        for fx in (SOFA_X0 + 12, SOFA_X1 - 28):
            dr.rectangle(V.box(fx, 1078, fx + 16, FLOOR), fill=self.lit(WOOD_D, WOOD_L, fx, FLOOR, t))

    def draw_cushion(self, dr, V, x, y, a, t):
        c = self.lit((40, 34, 60), (120, 110, 210), x, y, t)
        pts = rot_pts(rect_pts(x - 58, y - 22, x + 58, y + 22), x, y, a)
        dr.polygon(V.P(pts), fill=c)
        for (px, py) in pts:
            dr.ellipse(V.box(px - 7, py - 7, px + 7, py + 7), fill=dim(c, 0.8))

    # ---- un ami
    def draw_friend(self, dr, V, f, t, salon=True, arms_only=False, light_k=None):
        x, y, sx, sy, a = f.state(t)
        k = 1.0
        w, h = f.w * sx, f.h * sy
        if salon:
            col = self.lit(dim(f.col, 0.18), f.col, x, y, t)
        else:
            col = mix((0, 0, 0), f.col, light_k if light_k is not None else 1.0)
        dark = dim(col, 0.72)
        ca, sa = math.cos(a), math.sin(a)

        def Pp(dx, dy):
            return (x + dx * ca - dy * sa, y + dx * sa + dy * ca)
        s = f.w / 105.0 if f.name != "green" else f.w / 80.0 * 0.76
        s = max(0.4, s) * (1.0 if salon else 1.0)
        lw = max(1, int(V.L(max(3.0, 9.0 * f.w / 105.0))))
        arms = f.arms(t)
        if not arms_only:
            # jambes
            leg = f.leg(t)
            lh = 14.0 * f.h / max(f.h, 105.0) * (f.w / 105.0 if f.w < 105 else 1.0) + 6.0
            lh = 12.0 * (f.w / 105.0) + 4.0
            for side in (-1, 1):
                up = 0.0
                ext = 0.0
                if leg == side:
                    up = lh * 1.3
                if leg == 2:
                    ext = 14.0 * f.w / 105.0 * side * -1 + (-16.0 * f.w / 105.0 if side < 0 else 16.0 * f.w / 105.0)
                lx = side * w * 0.27
                pts = [Pp(lx - w * 0.09 + ext, h / 2 - 2), Pp(lx + w * 0.09 + ext, h / 2 - 2), Pp(lx + w * 0.09 + ext * 1.6, h / 2 + lh - up), Pp(lx - w * 0.09 + ext * 1.6, h / 2 + lh - up)]
                dr.polygon(V.P(pts), fill=dark)
            dr.polygon(V.P([Pp(-w / 2, -h / 2), Pp(w / 2, -h / 2), Pp(w / 2, h / 2), Pp(-w / 2, h / 2)]), fill=col)
            dr.line(V.P([Pp(-w / 2, -h / 2), Pp(w / 2, -h / 2), Pp(w / 2, h / 2), Pp(-w / 2, h / 2), Pp(-w / 2, -h / 2)]), fill=dark, width=lw)
            # chapeau de fête
            hat = f.hat(t)
            hc1, hc2 = HATS[f.name]
            if salon:
                hc1 = self.lit(dim(hc1, 0.2), hc1, x, y - h, t)
                hc2 = self.lit(dim(hc2, 0.2), hc2, x, y - h, t)
            else:
                lk = light_k if light_k is not None else 1.0
                hc1, hc2 = mix((0, 0, 0), hc1, lk), mix((0, 0, 0), hc2, lk)
            hw_ = min(0.6 * f.w, 56.0 * f.w / 105.0 if f.w < 80 else 56.0)
            hh_ = 42.0 * (f.w / 105.0 if f.w < 80 else 1.0)
            if f.name == "green":
                hw_, hh_ = 48.0 * (f.w / 80.0), 42.0 * (f.w / 80.0)
            if hat == "crushed":
                pts = [Pp(-hw_ * 0.75, -h / 2), Pp(hw_ * 0.75, -h / 2), Pp(hw_ * 0.35, -h / 2 - hh_ * 0.32), Pp(-hw_ * 0.45, -h / 2 - hh_ * 0.25)]
                dr.polygon(V.P(pts), fill=hc1)
            else:
                pts = [Pp(-hw_ / 2, -h / 2), Pp(hw_ / 2, -h / 2), Pp(0, -h / 2 - hh_)]
                dr.polygon(V.P(pts), fill=hc1)
                for j in (0.33, 0.62):
                    yy = -h / 2 - hh_ * j
                    half = hw_ / 2 * (1 - j)
                    dr.line(V.P([Pp(-half, yy), Pp(half, yy)]), fill=hc2, width=max(1, int(V.L(5 * f.w / 105.0 + 1))))
                pp = Pp(0, -h / 2 - hh_)
                r = 7.0 * (f.w / 105.0 if f.w < 80 else 1.0)
                dr.ellipse(V.box(pp[0] - r, pp[1] - r, pp[0] + r, pp[1] + r), fill=hc2)
        # bras
        if arms:
            aw = max(1, int(V.L(max(3.0, 11.0 * f.w / 105.0))))
            sc = f.w / 105.0
            if arms == "up" or arms == "push":
                for side in (-1, 1):
                    p0 = Pp(side * w * 0.42, -h / 2 + 10 * sc)
                    p1 = Pp(side * w * 0.3 - 16 * sc, -h / 2 - 46 * sc) if arms == "up" else Pp(-w * 0.55 - 30 * sc + side * 10 * sc, -h / 2 - 30 * sc)
                    dr.line(V.P([p0, p1]), fill=dark, width=aw)
            elif arms == "thumb":
                for side in (-1, 1):
                    p0 = Pp(side * w * 0.5, -h * 0.05)
                    p1 = Pp(side * (w * 0.5 + 26 * sc), -h * 0.05 - 30 * sc)
                    dr.line(V.P([p0, p1]), fill=dark, width=aw)
                    r = 9 * sc
                    dr.ellipse(V.box(p1[0] - r, p1[1] - r, p1[0] + r, p1[1] + r), fill=col)
                    tp = (p1[0], p1[1] - 14 * sc * V.S / V.S)
                    dr.line(V.P([(p1[0], p1[1]), (p1[0], p1[1] - 18 * sc)]), fill=col, width=max(1, int(V.L(7 * sc))))
            elif arms == "reach":
                p0 = Pp(0, -h / 2 + 8)
                p1 = Pp(0, -h / 2 - 34)
                dr.line(V.P([p0, p1]), fill=dark, width=aw)
            elif arms == "hold":
                p0 = Pp(-w * 0.45, -h * 0.1)
                p1 = Pp(-w * 0.5 - 14, -h * 0.4)
                dr.line(V.P([p0, p1]), fill=dark, width=aw)
            elif arms == "grip":
                for side in (-1, 1):
                    p0 = Pp(side * w * 0.5, -h * 0.25)
                    p1 = Pp(side * (w * 0.5 + 10), -h * 0.45)
                    dr.line(V.P([p0, p1]), fill=dark, width=aw)
            elif arms == "carry":
                for side in (-1, 1):
                    p0 = Pp(side * w * 0.4, -h * 0.15)
                    p1 = Pp(w * 0.55 + 10 * sc, -h * 0.22)
                    dr.line(V.P([p0, p1]), fill=dark, width=aw)

    # ---- Bounce
    def draw_ball(self, dr, V, t, bs, light_k=None):
        w, x, y, rx, ry, sc = bs
        hc = base.HERO["color"]
        bx0 = V.box(x - rx, y - ry, x + rx, y + ry)
        if light_k is None or light_k > 0.0:
            halo_c = mix(BG, dim(hc, 0.6), 0.35) if light_k is None else mix(BG, dim(hc, 0.6), 0.35 * light_k)
            hb = V.box(x - rx * 1.45, y - ry * 1.45, x + rx * 1.45, y + ry * 1.45)
            if w == "S" or light_k is None:
                dr.ellipse(hb, fill=halo_c)
        col = hc if light_k is None else mix(BG, hc, light_k)
        dr.ellipse(bx0, fill=col)
        # le visage : il tourne les yeux
        gx, gy = self.P.bgaze(t)
        r = min(rx, ry)
        sxp, syp = V.X(x), V.Y(y)
        rr = V.L(r)
        if light_k is None or light_k > 0.3:
            base.hero_face(dr, sxp + gx * rr * 0.22, syp + gy * rr * 0.2 + (V.L(ry) - rr) * 0.0, rr * 0.97)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (sxp, syp + V.oy)
        # crème et bougie sur la tête
        if self.P.cream(t):
            cream = (255, 248, 240) if light_k is None else mix(BG, (255, 248, 240), light_k)
            for j, (dx, dy, cr) in enumerate(((-0.55, -0.72, 0.36), (0.0, -0.9, 0.42), (0.55, -0.72, 0.36), (0.85, -0.25, 0.22), (-0.85, -0.3, 0.2))):
                dr.ellipse(V.box(x + dx * rx - cr * rx, y + dy * ry - cr * ry, x + dx * rx + cr * rx, y + dy * ry + cr * ry), fill=cream)
            hcand = self.P.head_candle(t)
            if hcand:
                tilt = 0.0
                if hcand == "out":
                    tilt = -1.35 * smooth((t - 53.9) / 0.25)
                cx, cy = x, y - ry * 1.05
                k = rx / RB * 0.9 if w == "T" else 1.0
                pts = rot_pts(rect_pts(cx - 3.5 * k, cy - 26 * k, cx + 3.5 * k, cy), cx, cy, tilt)
                dr.polygon(V.P(pts), fill=(120, 200, 255) if light_k is None else mix(BG, (120, 200, 255), light_k))
                if hcand == "lit":
                    tx, ty = rot_pts([(cx, cy - 26 * k)], cx, cy, tilt)[0]
                    lean = 0.0
                    fh = 1.0
                    for (b0, b1) in self.P.breath:
                        if b0 <= t <= b1:
                            u = (t - b0) / (b1 - b0)
                            if b0 > 52.0:
                                lean, fh = -1.45 * math.sin(math.pi * u), 1.0 - 0.3 * math.sin(math.pi * u)
                            else:
                                lean = -0.5 * math.sin(math.pi * u)
                    draw_flame(dr, V, tx, ty, 26 * k * fh * (1 + 0.08 * math.sin(t * 23)), 12 * k, lean)
                elif t < 55.6:
                    # filet de fumée
                    tx, ty = rot_pts([(cx, cy - 26 * k)], cx, cy, tilt)[0]
                    for j in range(5):
                        u = (t - 53.95 - j * 0.12)
                        if 0 < u < 1.4:
                            px = tx + 6 * math.sin(u * 5 + j) * k
                            py = ty - u * 45 * k
                            rad = (3 + 5 * u) * k
                            dr.ellipse(V.box(px - rad, py - rad, px + rad, py + rad), fill=mix(BG, (120, 120, 130), 0.7 * (1 - u / 1.4)))

    # ---- l'escalier
    def draw_stairs(self, dr, t, S, oy=0.0):
        P = self.P
        cx, cy, z, ax, ay = self.C.stairs(t)
        V = View(S, cx, cy, z, ax, ay, oy=oy)
        dk = self.dark(t)
        amb = 1.0 - dk
        # le mur de la cage
        dr.rectangle([0, 0, W * S, H * S], fill=mix(BG, STAIR_WALL, amb))
        # la lumière chaude des bougies (amis, gâteau) dans la cage
        if self.cake_in_stairs(t) and amb > 0.02:
            cxk, cyk = self.cake_pos(t)
            fl = self.flicker(t)
            for k in range(14, 0, -1):
                r = 560.0 * k / 14
                c = mix(STAIR_WALL, (124, 84, 40), (1 - k / 14) ** 1.6 * 0.8 * fl)
                dr.ellipse(V.box(cxk - r, cyk - r, cxk + r, cyk + r), fill=mix(BG, c, amb))
        # murs latéraux, plafond
        side = mix(BG, (11, 11, 18), amb)
        dr.rectangle(V.box(-600, -600, 0, 2600), fill=side)
        dr.rectangle(V.box(SW_R, -600, SW_R + 600, 2600), fill=side)
        dr.rectangle(V.box(-600, -600, SW_R + 600, LEV["RL3"] - 230.0), fill=side)
        # la porte de côté (palier du haut)
        dx0, dy0, dx1, dy1 = SDOOR
        op = P.sdoor(t)[0]
        lightbar = P.tlight(t)[0]
        if op > 0.01:
            warm = (150, 100, 46) if t > 44.0 else (36, 30, 28)
            dr.rectangle(V.box(dx0, dy0, dx1 + 600, dy1), fill=mix(BG, warm, amb * op))
        if op < 0.99:
            dr.rectangle(V.box(dx0, dy0, dx0 + 26 * (1 - op), dy1 - 5), fill=mix(BG, (86, 60, 44), amb))
            dr.rectangle(V.box(dx0 - 8, dy0 - 10, dx0 + 2, dy1), fill=mix(BG, (60, 44, 36), amb))
        if lightbar > 0.01 and op < 0.5:
            lb = lightbar
            dr.polygon(V.P([(dx0 + 2, dy1 - 5), (dx0 + 2, dy1), (dx0 - 230, dy1), (dx0 - 200, dy1 - 46)]),
                       fill=mix(STAIR_WALL, (255, 236, 170), 0.32 * lb))
            dr.rectangle(V.box(dx0 - 4, dy1 - 5, dx0 + 26, dy1), fill=mix(STAIR_WALL, (255, 246, 200), lb))
        # les volées : celles du fond plus sombres
        for fl in ("F0", "F2"):
            self.draw_flight(dr, V, fl, STAIR_BACK, amb)
        self.draw_rail(dr, V, "F2", amb)
        for nm in ("LL0", "RL1", "LL2", "RL3", "RL-1", "LL-2"):
            y = LEV.get(nm, LEV["LL0"] + RISE * (STEPS + 1) * (1 if nm == "RL-1" else 2))
            x0, x1 = (-30.0, FX0) if nm.startswith("LL") else (FX1, SW_R + 30.0)
            dr.rectangle(V.box(x0, y, x1, y + 34), fill=mix(BG, STAIR_FRONT, amb))
            dr.rectangle(V.box(x0, y, x1, y + 5), fill=mix(BG, (90, 90, 114), amb))
        for fl in ("F1", "F3", "F-1"):
            self.draw_flight(dr, V, fl, STAIR_FRONT, amb)
        # les acteurs, par-dessus les volées
        lk = amb
        for nm in ("orange", "yellow", "blue", "green"):
            f = P.FS[nm]
            if f.world(t) == "T":
                self.draw_stair_friend(dr, V, f, t, lk)
        bw = self.ball_state(t)
        if lk > 0.02:
            self.draw_triangle(dr, V, t, lk)
            if bw is not None and bw[0] == "T":
                self.draw_ball(dr, V, t, bw, light_k=None if lk > 0.97 else lk)
            self.draw_cupcake_front(dr, V, t, lk)
            self.draw_breath(dr, V, t, lk)
        if dk > 0:
            self.draw_dark_end(dr, V, t, dk)
            if 60.2 <= t < 61.5 and bw is not None and lk > 0.02:
                self.draw_ball(dr, V, t, bw, light_k=None)

    def cake_in_stairs(self, t):
        f = self.P.FS["green"]
        return f.world(t) == "T"

    def cake_pos(self, t):
        f = self.P.FS["green"]
        x, y, sx, sy, a = f.state(t)
        k = self.P.fk
        return (x, y - f.h / 2 - 82.0 * k * 0.9 * 0.5)

    def flight_treads(self, fl):
        P = self.P
        if fl in ("F1", "F2", "F3"):
            return [P.tread(fl, k) for k in range(1, STEPS + 1)]
        y0 = LEV["LL0"]
        if fl == "F0":
            # sous LL0, la volée du fond descend vers la droite
            return [(FX0 + TREAD * (k - 1), FX0 + TREAD * k, y0 + RISE * k) for k in range(1, STEPS + 1)]
        y1 = y0 + RISE * (STEPS + 1)
        return [(FX1 - TREAD * k, FX1 - TREAD * (k - 1), y1 + RISE * k) for k in range(1, STEPS + 1)]

    def draw_flight(self, dr, V, fl, col, amb):
        c = mix(BG, col, amb)
        nose = mix(BG, mix(col, (255, 255, 255), 0.2), amb)
        treads = self.flight_treads(fl)
        xs = [a for a, b, y in treads] + [b for a, b, y in treads]
        ys = [y for a, b, y in treads]
        lo_x = min(xs)
        hi_x = max(xs)
        ylo = max(ys)
        yhi = min(ys)
        # le limon : du nez le plus bas au plus haut, épaisseur 40 sous les marches
        rising_right = treads[0][1] <= treads[-1][0] + 1 if ys[0] > ys[-1] else treads[0][0] >= treads[-1][1] - 1
        for (x0, x1, y) in treads:
            dr.rectangle(V.box(x0, y, x1, y + RISE + 1), fill=c)
            dr.rectangle(V.box(x0, y, x1, y + 5), fill=nose)
        first, last = (treads[0], treads[-1]) if ys[0] > ys[-1] else (treads[-1], treads[0])
        # first = la marche la plus basse
        if first[0] < last[0]:
            pts = [(first[0], first[2] + RISE), (last[1], last[2] + RISE), (last[1], last[2] + RISE + 40), (first[0], first[2] + RISE + 40)]
        else:
            pts = [(first[1], first[2] + RISE), (last[0], last[2] + RISE), (last[0], last[2] + RISE + 40), (first[1], first[2] + RISE + 40)]
        dr.polygon(V.P(pts), fill=dim(c, 0.82))

    def draw_rail(self, dr, V, fl, amb):
        if amb < 0.02:
            return
        P = self.P
        c = mix(BG, RAIL, amb * 0.9)
        a = P.rail_point(fl, FX0)
        b = P.rail_point(fl, FX1)
        dr.line(V.P([a, b]), fill=c, width=max(1, int(V.L(6))))
        for k in range(STEPS + 1):
            x = FX0 + (FX1 - FX0) * k / STEPS
            p = P.rail_point(fl, x)
            dr.line(V.P([p, (x, p[1] + 50.0)]), fill=dim(c, 0.75), width=max(1, int(V.L(4))))

    def draw_stair_friend(self, dr, V, f, t, lk):
        self.draw_friend(dr, V, f, t, salon=False, light_k=lk * 0.95)
        if f.name == "green":
            cxk, cyk = self.cake_pos(t)
            k = self.P.fk * 0.9
            self.draw_cake(dr, V, cxk, cyk + 82 * k * 0.5, k, 0.0, t, salon=False, lit_k=lk)

    def draw_triangle(self, dr, V, t, lk):
        P = self.P
        x, y = P.tpos(t)
        inf, tilt, st = P.tpose(t)
        f = P.tface(t)[0]
        col = mix(BG, TRI, lk)
        lb = P.tlight(t)[0]
        if lb > 0 and P.sdoor(t)[0] < 0.5:
            col = mix(col, (255, 220, 255), 0.25 * lb)
        dk = mix(BG, dim(TRI, 0.7), lk)
        b, h = TB * inf, TH * inf * st
        px = x + (b / 2 if tilt > 0 else -b / 2)
        # pieds
        fl, fr = P.tfoot(t)
        for side, lift in ((-1, fl), (1, fr)):
            fx = x + side * b * 0.3
            pts = rect_pts(fx - 13, y - 4 - lift * 22, fx + 13, y + 6 - lift * 22)
            dr.polygon(V.P(rot_pts(pts, px, y, tilt)), fill=dk)
        pts = [(x - b / 2, y), (x + b / 2, y), (x, y - h)]
        pts = rot_pts(pts, px, y, tilt)
        dr.polygon(V.P(pts), fill=col)
        dr.line(V.P(pts + [pts[0]]), fill=dk, width=max(1, int(V.L(4))))
        # « ? »
        q = P.tq(t)[0]
        if q > 0.01:
            tipx, tipy = pts[2]
            fnt = base.font(V.L(64))
            dr.text((V.X(tipx + 62 * f), V.Y(tipy + 4)), "?", fill=mix(BG, (255, 255, 255), q), anchor="mm", font=fnt,
                    stroke_width=max(1, int(V.L(3))), stroke_fill=(0, 0, 0))
        # le bras qui tient le cupcake (côté du regard), et le cupcake (sauf écrasé : par-dessus)
        cx, cy = self.cup_pos(t)
        _b, _h, to_w, _r = P.tri_frame(t)
        sh = to_w(f * _b / 2 * (1 - 55.0 / _h) * 0.85, -55.0)
        dr.line(V.P([sh, (cx - f * 14, cy + 4)]), fill=dk, width=max(1, int(V.L(7))))
        if P.cup_state(t) == "ok":
            self.draw_cupcake(dr, V, t, cx, cy, lk)

    def cup_pos(self, t):
        return self.P.cup_center(t)

    def draw_cupcake(self, dr, V, t, cx, cy, lk, crushed=False):
        P = self.P
        paper = mix(BG, (90, 170, 230), lk)
        cream = mix(BG, (255, 210, 230), lk)
        if crushed:
            dr.polygon(V.P([(cx - 26, cy - 2), (cx + 26, cy - 2), (cx + 20, cy + 14), (cx - 20, cy + 14)]), fill=paper)
            dr.ellipse(V.box(cx - 32, cy - 12, cx + 32, cy + 4), fill=cream)
            return
        dr.polygon(V.P([(cx - 20, cy - 4), (cx + 20, cy - 4), (cx + 15, cy + 14), (cx - 15, cy + 14)]), fill=paper)
        dr.ellipse(V.box(cx - 23, cy - 20, cx + 23, cy + 2), fill=cream)
        # la bougie à grande flamme
        tilt = P.cup_tilt(t)[0] * P.tface(t)[0]
        bx, by = cx, cy - 16
        pts = rot_pts(rect_pts(bx - 4, by - 26, bx + 4, by), bx, by, tilt)
        dr.polygon(V.P(pts), fill=mix(BG, (255, 230, 100), lk))
        if P.cup_lit(t):
            tx, ty = rot_pts([(bx, by - 26)], bx, by, tilt)[0]
            fh = 1.0 + 0.08 * math.sin(t * 19)
            draw_flame(dr, V, tx, ty, 34 * fh, 15, tilt * 0.6)

    def draw_cupcake_front(self, dr, V, t, lk):
        P = self.P
        if P.cup_state(t) != "crushed":
            return
        cx, cy = self.cup_pos(t)
        self.draw_cupcake(dr, V, t, cx, cy, lk, crushed=True)

    def draw_breath(self, dr, V, t, lk):
        P = self.P
        for (b0, b1) in P.breath:
            if not (b0 <= t <= b1):
                continue
            u = (t - b0) / (b1 - b0)
            tri = self.tri_poly(t)
            tipx, tipy = tri[2]
            f = P.tface(t)[0]
            # cible : la bougie sur la tête de la balle
            bx, by = P.bpos(t)[:2]
            tx, ty = bx, by - RB * 1.2
            if b0 < 49.0:
                ty += 16.0          # le souffle passe sous la flamme (la balle a sauté)
            elif b0 < 50.0:
                tx -= f * 2.0
                ty -= 4.0
                tx += f * 30.0      # il souffle à côté
            for j in range(3):
                off = (j - 1) * 9.0
                k0 = clamp01(u * 1.6 - j * 0.1)
                pts = []
                for m in range(10):
                    v = m / 9 * k0
                    px = tipx + (tx - tipx) * v
                    py = tipy + (ty - tipy) * v + off + 4 * math.sin(v * 10 + t * 20 + j)
                    pts.append((px, py))
                if len(pts) > 1:
                    dr.line(V.P(pts), fill=mix(BG, (200, 210, 230), lk * 0.8 * (1 - u * 0.5)), width=max(1, int(V.L(3))))

    def draw_dark_end(self, dr, V, t, dk):
        """Noir total ; les mèches rougeoient ; la silhouette du triangle se dégonfle ;
        l'anneau éclaire la scène un instant."""
        P = self.P
        if dk >= 0.999:
            dr.rectangle([0, 0, W * V.S, H * V.S], fill=BG)
        if t >= 61.5:
            return
        # les braises du grand gâteau
        cxk, cyk = self.cake_pos(t)
        k = P.fk * 0.9
        bottom = cyk + 82 * k * 0.5
        hw, hh = 65.0 * k, 82.0 * k
        for j in range(8):
            x = cxk - hw + 12 * k + j * (2 * hw - 24 * k) / 7
            y = bottom - hh - 36 * k
            g = 0.65 + 0.35 * math.sin(t * 5 + j * 1.3)
            rr = 4.5 * k * 1.2
            dr.ellipse(V.box(x - rr * 2.4, y - rr * 2.4, x + rr * 2.4, y + rr * 2.4), fill=mix(BG, (110, 22, 8), g))
            dr.ellipse(V.box(x - rr, y - rr * 1.3, x + rr, y + rr * 0.7), fill=mix(BG, (255, 74, 30), g))
        if t >= 58.9 and t < 60.2:
            # la silhouette, découpée sur la lueur des braises
            pts = self.tri_poly(t)
            dr.polygon(V.P(pts), fill=(16, 10, 22))
            dr.line(V.P(pts + [pts[0]]), fill=(70, 20, 22), width=max(1, int(V.L(3))))

    # ---- les anneaux
    def draw_rings(self, dr, t, S):
        P = self.P
        for (tr, w, rmax, clip) in P.rings:
            st = ring_state(t, tr, rmax)
            if st is None:
                continue
            r, inten = st
            # l'anneau part de la balle au moment du contact
            if w == "S":
                x, y = P.bpos(tr)[:2]
                dy = self.C.salon_dy(t)
                cx, cy = x, y + dy
                rr = r
                cl = None if clip is None else clip + dy
            else:
                x, y = P.bpos(tr)[:2]
                cxs, cys, z, ax, ay = self.C.stairs(t)
                cx, cy = ax + (x - cxs) * z, ay + (y - cys) * z
                rr = r
                cl = None
            if t >= 61.5 and tr < 60.0:
                continue
            col = mix(BG, (246, 246, 255), inten)
            draw_ring_poly(dr, cx, cy, rr, 9.0 + 5.0 * inten, col, S, clip=cl)

    # ---------------------------------------------------------- l'éclair final
    def lit_flash(self, t):
        return 0.0


# ------------------------------------------------------------------ la scène et la vidéo
DEFAULTS = {
    "ball_r": R, "gravity": G,
    "chapter_max_s": 200.0,
    "hook_text_s": 2.6, "hook_top": 0.085, "hook_font_size": 92,
    "narrator_voice": ak.VOICE_NAME, "narrator_length": 1.0, "narr_gap_s": 0.0,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.95, "end_hold_s": 0.45, "narr_tail_s": 0.0,
    "scene_top": 0.22, "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": False,
}

CLASS_GAIN = {"n": 0.9, "L": 1.0, "m": 0.55, "p": 0.5, "t": 0.2}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        cfg["_chapters"] = [(Scene, {})]
        super().__init__(cfg, rng)

    def hit_class(self, t0):
        P = self.sims[0].P
        best = None
        for (th, cls, w) in P.hits:
            if abs(th - t0) < 0.02:
                best = cls
        return best or "n"


def lowpass(x, k=0.18):
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += k * (x[i] - acc)
        y[i] = acc
    return y


def render_audio(sim, events, total_dur, cfg, path, narr):
    """Les « Bounce » : placés par base.place_words (le même placement que lit le contrôle),
    avec un volume et un timbre par contact (étouffé sous le coussin, petit, à peine audible).
    La voix de l'accroche passe par la narration (titre du chapitre)."""
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        muff = lowpass(name, 0.12)
        muff = muff / (np.max(np.abs(muff)) + 1e-9)
        words = base.place_words(events, total_dur, cfg, None, None, narr, (), name_len=len(name) / SR)
        for (t0, kind, _d, tag) in words:
            cls = sim.hit_class(t0)
            g = CLASS_GAIN.get(cls, 0.9)
            w = muff if cls == "m" else name
            ak.add(buf, base.pitch(w, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=g)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    summary = {"name": cfg["name"], "duration_s": round(dur, 2), "payoff": bool(sim.payoff),
               "hits": sum(1 for e in events if e[1] == "hit")}
    narr, replies = base.build_narration(sim, cfg)
    cfg["_sim"] = sim
    summary["narration"] = [{"t": round(n["start"], 2), "s": round(n["end"] - n["start"], 2), "text": n["text"]} for n in narr]
    name = base.hero_word(cfg["hero_name"], cfg)
    words = base.place_words(events, dur, cfg, None, None, narr, (), name_len=len(name) / SR if name is not None else 0.8)
    summary["words"] = len(words)
    if "--simulate" in argv:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    os.makedirs(os.path.join(base.ROOT, "output"), exist_ok=True)
    out = os.path.join(base.ROOT, "output", cfg["name"] + ".mp4")
    audio = tempfile.mktemp(suffix=".wav")
    try:
        summary["voice"] = render_audio(sim, events, dur, cfg, audio, narr)
        base.render_video(theme, sim, states, cfg, audio, out, events, ())
    finally:
        if os.path.exists(audio):
            os.remove(audio)
    summary["out"] = os.path.relpath(out, base.ROOT)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
