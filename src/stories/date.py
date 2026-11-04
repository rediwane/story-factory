"""
Prototype « le premier rendez-vous » : Bounce et Still (le personnage d'un fan, présenté
dans nameoc) dînent au restaurant. Une petite table ronde à nappe à carreaux, deux chaises,
une bougie, deux verres d'eau, une assiette de spaghettis, une lampe suspendue. Le serveur
est une silhouette sans visage ; sa voix est celle du narrateur, sous-titrée.

Bounce ne dit que son nom et ne s'arrête jamais de rebondir : il renverse son verre, catapulte
les spaghettis, rebondit sur la tête du serveur et sur la lampe. Still ne bouge pas et ne dit
rien : seuls ses yeux réagissent. À la fin, le serveur demande « Same table next week? » ;
Still, qui n'a rien montré de toute la soirée, ouvre grand les yeux pour la première fois et
sourit. Bounce fait le plus grand rebond de la vidéo.

Tout est calculé d'avance sur une horloge : les contacts de Bounce (chaise, verre, assiette,
tête du serveur, lampe), reliés par des arcs balistiques exacts sous une gravité unique
(x linéaire, y = y0 + vy0·s + G·s²/2 entre deux contacts). Les répliques du serveur sont
synthétisées dans __init__ (mémoïsées) pour que les contacts tombent entre les phrases.
`check_paths()` vérifie qu'aucun arc ne traverse un objet.

    python3 src/stories/date.py configs/<name>.json [--simulate]
"""
import math, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim

SR = base.ak.SR

# ------------------------------------------------------------------ voix mémoïsées
# la voix de Bounce ne rend pas « Bounce » deux fois à la même longueur : un tirage court,
# une fois par processus (le correctif steady_hero_word de nameoc / snooze).
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
            if len(v) / SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# la voix de l'accroche et celle du serveur : un seul tirage, que la simulation et le rendu
# partagent (la chorégraphie se cale sur leurs durées réelles)
_orig_hook = base.ak.hook_voice
_orig_say = base.narr_voice.say
_hook_memo, _say_memo = {}, {}


def memo_hook(text, *a, **k):
    if text not in _hook_memo:
        _hook_memo[text] = _orig_hook(text, *a, **k)
    v = _hook_memo[text]
    return None if v is None else v.copy()


def memo_say(text, voice=None, length_scale=None, *a, **k):
    key = (text, voice, length_scale)
    if key not in _say_memo:
        _say_memo[key] = _orig_say(text, voice, length_scale, *a, **k) if voice else _orig_say(text)
    v = _say_memo[key]
    return None if v is None else v.copy()


base.ak.hook_voice = memo_hook
base.narr_voice.say = memo_say

# ------------------------------------------------------------------ le décor
W, H = 1080, 1920
G = 2600.0
RB = 100.0                     # Bounce
R = 100.0                      # Still : même taille que Bounce
WALL_TOP = 470.0
FLOOR = 1460.0
SEAT = 1270.0                  # le dessus des deux assises
BX = 180.0                     # Bounce sur sa chaise
SX = 890.0                     # Still sur la sienne
BY = SEAT - RB
TT = 1176.0                    # le dessus de la table
TL, TR = 330.0, 750.0          # bords de la table
GL_X = 370.0                   # le verre de Bounce
GS_X = 705.0                   # le verre de Still
GW, GH = 40.0, 75.0
PL_X = 480.0                   # l'assiette
CA_X = 620.0                   # la bougie
LAMP_X, LAMP_Y0 = 410.0, 470.0  # point d'accroche de la lampe
LAMP_L = 90.0                  # longueur du fil
WT_X = 700.0                   # le serveur, debout derrière la table
WT_HEAD_Y, WT_HEAD_R = 730.0, 50.0
WT_OFF = 1220.0                # hors champ à droite

WALL = (22, 19, 30)
WALL_LOW = (27, 21, 29)
FLOOR_COL = (13, 11, 15)
TRIM = (44, 36, 46)
WINDOW = (26, 32, 60)
WIN_FRAME = (50, 44, 58)
CONE = (33, 28, 38)
CHAIR = (92, 62, 48)
CHAIR_D = (66, 44, 36)
CLOTH_A = (214, 208, 214)
CLOTH_B = (176, 52, 58)
CLOTH_EDGE = (120, 36, 44)
PEDESTAL = (40, 34, 40)
GLASS = (176, 196, 214)
WATER = (86, 138, 200)
PLATE = (232, 232, 238)
PLATE_D = (176, 176, 188)
PASTA = (240, 204, 112)
PASTA_D = (196, 156, 70)
SAUCE = (186, 52, 40)
CANDLE = (236, 228, 206)
HOLDER = (150, 130, 96)
FLAME_O = (255, 170, 60)
FLAME_I = (255, 238, 160)
GLOW = (54, 38, 30)
SHADE = (196, 150, 72)
SHADE_D = (150, 110, 50)
WAITER = (60, 58, 76)
WAITER_D = (46, 44, 58)
TOWEL = (206, 206, 216)

# Still, d'après le dessin validé (nameoc)
OC_OUT = (152, 166, 56)
OC_IN = (238, 250, 178)
OC_INK = (14, 14, 12)
HAT_FILL = (142, 146, 244)
HAT_LINE = (84, 86, 214)
BOW_FILL = (234, 246, 176)
BOW_LINE = (92, 98, 34)
BLUSH = (246, 150, 150)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def ballistic(x0, y0, x1, y1, d):
    """Arc exact sous la gravité G, de (x0, y0) à (x1, y1) en d secondes : (vx, vy0)."""
    return (x1 - x0) / d, (y1 - y0 - 0.5 * G * d * d) / d


# les points de contact de Bounce (centre de la balle au contact)
SPOTS = {
    "seat": (BX, BY),
    "glass": (GL_X, TT - GH - RB),
    "rim": (430.0, 1058.0),               # le bord gauche de l'assiette : elle bascule
    "plate": (PL_X, TT - 12 - RB),        # l'assiette retournée
    "head": (WT_X, WT_HEAD_Y - WT_HEAD_R - RB),
    "lamp": (LAMP_X, LAMP_Y0 + LAMP_L + 60 + RB),   # par en dessous
}


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.end_s = cfg["end_s"]
        self.plan_narration()
        self.build_track()
        self.build_props()
        self.check_paths()

    # ---- les répliques du serveur, placées comme base.build_narration les placera
    def plan_narration(self):
        cfg = self.cfg
        self.lines = [(t, txt, k) for (t, txt, k) in cfg["lines"]]
        hook = base.hook_audio(cfg)
        prev_end = (0.15 + len(hook) / SR + 0.3) if hook is not None else 0.3
        self.hook_end = prev_end
        self.say = {}
        for (trig, text, key) in sorted(self.lines):
            x = base.narr_voice.say(text, cfg["narrator_voice"], cfg["narrator_length"])
            d = (len(x) / SR) if x is not None else 0.8
            start = max(trig, prev_end + cfg["narr_gap_s"])
            self.say[key] = (start, start + d, text)
            prev_end = start + d
        self.replies = [(k, cfg["reply_delay"]) for k in cfg["reply_keys"]]

    def S(self, key):
        return self.say[key][0]

    def E(self, key):
        return self.say[key][1]

    # ---- la piste de Bounce
    def build_track(self):
        cfg = self.cfg
        C = []                                        # (t, x, y, kind, dur)
        hop = cfg["hop_s"]

        def at(t, kind):
            x, y = SPOTS[kind.split("_")[0]]
            C.append((t, x, y, kind))

        def hops(t_to):
            """De petits rebonds sur la chaise (le coussin : sans bruit) jusqu'à t_to au plus."""
            t = C[-1][0]
            n = max(1, round((t_to - t) / hop))
            d = (t_to - t) / n
            for i in range(1, n + 1):
                C.append((t + d * i, BX, BY, "soft"))

        def seq(t0, steps):
            """steps = [(durée, kind)] à partir de t0 (le dernier contact)."""
            t = t0
            for (d, kind) in steps:
                t += d
                at(t, kind)
            return t

        C.append((-0.70, -150.0, 880.0, "start"))
        C.append((0.80, BX, BY, "soft"))
        # 1 « Table for two? »
        hops(self.E("l1") + 0.25)
        t = seq(C[-1][0], [(1.05, "seat"), (1.1, "seat"), (1.25, "seat"), (1.05, "seat")])
        # 2 « Anything to drink? » ... « Bounce. » ... « Water it is. »
        tr = self.E("l2") + cfg["reply_delay"]
        hops(tr - 0.95)
        at(tr, "seat")
        hops(self.E("l3") + 0.2)
        # 3 le verre
        t = seq(C[-1][0], [(1.0, "seat"), (1.05, "glass"), (1.1, "seat"), (1.2, "seat"), (1.0, "seat"), (1.1, "seat")])
        self.t_glass = [c[0] for c in C if c[3] == "glass"][0]
        hops(self.S("l4") + 0.1)
        hops(self.E("l4") + 0.3)
        # 4 les spaghettis
        t = seq(C[-1][0], [(1.1, "rim"), (0.95, "seat")])
        self.t_rim = [c[0] for c in C if c[3] == "rim"][0]
        hops(self.S("l5"))
        hops(self.E("l5") + 0.2)
        # 5 la tête du serveur, la lampe
        t = seq(C[-1][0], [(1.05, "seat"), (1.05, "plate"), (1.0, "head"), (1.0, "plate"), (1.1, "seat_q"),
                           (0.45, "lamp"), (0.45, "plate"), (1.1, "seat")])
        hops(t + 0.9)
        # 6 seul avec elle
        t = seq(C[-1][0], [(1.3, "seat_q"), (0.45, "lamp"), (0.45, "plate"), (1.1, "seat"), (1.0, "seat"),
                           (1.25, "seat"), (1.05, "plate"), (0.95, "seat")])
        # 7 « Dessert? » ... « Bounce. » ... « I'll take that as a no. »
        tr = self.E("l6") + cfg["reply_delay"]
        hops(tr - 1.0)
        at(tr, "seat")
        hops(self.E("l7") + 0.2)
        t = seq(C[-1][0], [(1.05, "seat"), (1.05, "plate"), (1.0, "head"), (1.0, "plate"), (1.1, "seat")])
        # 8 « Same table next week? » ... le silence ... elle sourit
        hops(self.S("l8"))
        hops(cfg["t_big"])
        # 9 le grand rebond : le plus haut de la vidéo
        self.t_land = cfg["t_big"] + cfg["big_s"]
        C.append((self.t_land, BX, BY, "seat"))
        hops(self.end_s + 0.4)
        self.C = C
        # un appel de la chaise juste avant la lampe reste muet (_q) : le mot va à la lampe
        self.hits = [(c[0], c[3]) for c in C if c[3] not in ("soft", "start") and not c[3].endswith("_q") and c[0] > 0]
        self.hi = 0
        self.payoff_at = self.t_land
        # contrôle : aucun contact dur pendant une phrase (il y serait muet)
        for (tc, k) in self.hits:
            for key, (a, b, txt) in self.say.items():
                if a - 0.1 <= tc <= b + 0.1 and not (key in cfg["reply_keys"]):
                    print(f"[date] contact {k} à {tc:.2f} pendant « {txt} »", file=sys.stderr)

    def bounce_at(self, t):
        C = self.C
        if t <= C[0][0]:
            return C[0][1], C[0][2]
        for a, b in zip(C, C[1:]):
            if a[0] <= t <= b[0]:
                d = b[0] - a[0]
                vx, vy = ballistic(a[1], a[2], b[1], b[2], d)
                s = t - a[0]
                return a[1] + vx * s, a[2] + vy * s + 0.5 * G * s * s
        a = C[-1]
        return a[1], a[2]

    def contact_kind_near(self, t, win=0.07):
        for c in self.C:
            if abs(c[0] - t) <= win:
                return c[3].split("_")[0]
        return None

    # ---- les objets
    def build_props(self):
        cfg = self.cfg
        self.wt_keys = cfg["waiter"]                       # [(t, x)]
        self.table_hits = [t for (t, k) in self.hits if k in ("glass", "rim", "plate")]
        self.lamp_hits = [t for (t, k) in self.hits if k == "lamp"]
        self.head_hits = [t for (t, k) in self.hits if k == "head"]
        tr = self.t_rim
        # les spaghettis catapultés : (cible, durée, forme à l'arrivée)
        x0, y0 = PL_X - 10, 1132.0
        self.strands = []
        for (tx, ty, d, shape, ph) in [
            (SX, SEAT - 2 * R - 3, 1.25, "still", 0.3),
            (WT_X, WT_HEAD_Y - WT_HEAD_R - 3, 1.0, "waiter", 1.1),
            (GS_X, TT - GH - 2, 0.85, "glass", 2.0),
            (560.0, TT - 4, 0.62, "flat", 2.7),
            (668.0, TT - 4, 0.78, "flat", 3.5),
            (395.0, TT - 4, 0.95, "flat", 4.4),
        ]:
            vx, vy = ballistic(x0, y0, tx, ty, d)
            self.strands.append({"x0": x0, "y0": y0, "vx": vx, "vy": vy, "t0": tr, "t1": tr + d,
                                 "tx": tx, "ty": ty, "shape": shape, "ph": ph})
        self.t_still_pasta = tr + 1.25
        # l'assiette bascule et retombe retournée
        self.plate_flip = (tr, tr + 0.62)
        # le verre de Bounce : il bascule (0,3 s) puis tombe en tournant
        tg = self.t_glass
        self.glass_tip = (tg, tg + 0.3)
        self.glass_fall_t = math.sqrt(2 * (FLOOR - GW / 2 - (TT - GW / 2)) / G)
        # Still : les yeux qui s'ouvrent, le sourire (après « Same table next week? »)
        e8 = self.E("l8")
        self.t_open = e8 + cfg["open_after_s"]
        self.t_smile = self.t_open + 0.55

    def waiter_x(self, t):
        k = self.wt_keys
        if t <= k[0][0]:
            return k[0][1]
        for (t0, x0), (t1, x1) in zip(k, k[1:]):
            if t0 <= t <= t1:
                return lerp(x0, x1, (t - t0) / (t1 - t0)) if t1 > t0 else x1
        return k[-1][1]

    def waiter_walking(self, t):
        return abs(self.waiter_x(t + 0.02) - self.waiter_x(t - 0.02)) > 0.5

    def lamp_angle(self, t):
        a = 0.0
        for th in self.lamp_hits:
            d = t - th
            if d >= 0:
                a += 0.32 * math.exp(-d / 3.2) * math.sin(d * 2 * math.pi / 1.7)
        return a

    def lamp_geom(self, t):
        """Le fil et l'abat-jour, tournés autour du point d'accroche."""
        a = self.lamp_angle(t)
        ca, sa = math.cos(a), math.sin(a)

        def P(u, v):
            return LAMP_X + u * ca - v * sa, LAMP_Y0 + u * sa + v * ca
        shade = [P(-35, LAMP_L), P(35, LAMP_L), P(55, LAMP_L + 60), P(-55, LAMP_L + 60)]
        return P, shade

    # ---- contrôle : aucun arc ne traverse un objet
    def obstacles(self, t):
        obs = [("rect", 80, SEAT, 270, SEAT + 20, "seat"), ("rect", 40, 990, 55, SEAT + 20, "back"),
               ("rect", TL, TT, TR, TT + 24, "table"), ("rect", 528, TT, 552, FLOOR, "table"),
               ("rect", CA_X - 9, 1060, CA_X + 9, TT, "candle"), ("rect", CA_X - 20, TT - 10, CA_X + 20, TT, "candle"),
               ("rect", GS_X - GW / 2, TT - GH, GS_X + GW / 2, TT, "sglass"),
               ("circ", SX, SEAT - R, R, "still"), ("rect", -999, FLOOR, 2000, 2400, "floor")]
        if t < self.t_glass:
            obs.append(("rect", GL_X - GW / 2, TT - GH, GL_X + GW / 2, TT, "glass"))
        if t < self.t_rim:
            obs.append(("rect", PL_X - 70, TT - 12, PL_X + 70, TT, "rim"))
            obs.append(("rect", PL_X - 42, TT - 42, PL_X + 42, TT, "rim"))
        elif t > self.plate_flip[1]:
            obs.append(("rect", PL_X - 70, TT - 12, PL_X + 70, TT, "plate"))
        wx = self.waiter_x(t)
        if wx < 1150:
            obs.append(("circ", wx, WT_HEAD_Y, WT_HEAD_R, "head"))
            obs.append(("rect", wx - 75, 790, wx + 75, FLOOR, "head"))
        _, shade = self.lamp_geom(t)
        cx = sum(p[0] for p in shade) / 4
        cy = sum(p[1] for p in shade) / 4
        obs.append(("circ", cx, cy, 42, "lamp"))
        return obs

    def check_paths(self):
        bad = []
        dt = 1 / 120
        t = 0.0
        while t < self.end_s:
            x, y = self.bounce_at(t)
            near = self.contact_kind_near(t, 0.09)
            for o in self.obstacles(t):
                if o[0] == "rect":
                    _, x0, y0, x1, y1, tag = o
                    nx, ny = min(max(x, x0), x1), min(max(y, y0), y1)
                else:
                    _, cx, cy, r, tag = o
                    dd = math.hypot(x - cx, y - cy) or 1e-9
                    nx, ny = cx + (x - cx) * r / dd, cy + (y - cy) * r / dd
                    if dd < r:
                        nx, ny = x, y
                pen = RB - math.hypot(x - nx, y - ny)
                tol = 3.0
                if near is not None and (tag == near or (near in ("seat", "soft") and tag == "seat")):
                    tol = 45.0 if tag == "rim" else 12.0
                if pen > tol:
                    bad.append((round(t, 2), tag, round(pen, 1)))
            t += dt
        if bad:
            merged = []
            for b in bad:
                if not merged or b[1] != merged[-1][1] or b[0] - merged[-1][0] > 0.05:
                    merged.append(b)
            print(f"[date] traversées : {merged[:30]}", file=sys.stderr)
        self.bad = bad

    # ---- la simulation
    def step(self, dt):
        evs = []
        self.t += dt
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "oui"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "win"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # ---- Still : son état à l'instant t
    def still_state(self, t):
        cfg = self.cfg
        bx, by = self.bounce_at(t)
        tx, ty = bx, by
        for key in cfg["look_waiter"]:
            a, b, _ = self.say[key]
            if a - 0.2 <= t <= b + 0.3:
                tx, ty = self.waiter_x(t), WT_HEAD_Y
        cx, cy = SX, SEAT - R
        dx, dy = tx - cx, ty - (cy - 40)
        n = math.hypot(dx, dy) or 1.0
        gx, gy = dx / n, dy / n
        # un sourcil qui se lève un instant (le verre, l'assiette, la tête du serveur)
        brow = 0.0
        for (t0, amp) in [(self.t_glass + 0.2, 1.0), (self.head_hits[0] + 0.1, 0.8), (self.E("l7") - 0.6, 0.7)]:
            d = t - t0
            if 0 <= d < 1.6:
                brow = max(brow, amp * min(1.0, d / 0.15) * (1 - ease((d - 1.0) / 0.6)))
        # un clignement lent, sous les spaghettis
        blink = 0.0
        for t0 in (self.t_still_pasta + 1.0, self.t_still_pasta + 13.0):
            if 0 <= t - t0 < 0.32:
                blink = 1.0
        opn = ease((t - self.t_open) / 0.45)
        smile = ease((t - self.t_smile) / 0.5)
        blush = ease((t - self.t_smile - 0.2) / 0.8)
        return (gx, gy), brow, blink, opn, smile, blush

    def draw_oc(self, dr, t, S):
        """Still, le dessin validé de nameoc (draw_oc) à l'identique : disque clair, halo olive,
        bandeau bleu et nœud, yeux mi-clos sous des sourcils qui tombent vers la droite. Ajouts
        de ce prototype, tous à zéro par défaut : un sourcil qui se lève, un clignement, les
        yeux qui s'ouvrent grand, le sourire et les joues roses de la fin."""
        squash, wince, annoy = 0.0, 0.0, 0.25
        (gx, gy), brow, blink, opn, smile, blush = self.still_state(t)
        sx, sy = 1 + squash, 1 - squash
        cx = SX
        fy = SEAT
        cy = fy - R * sy

        def P(u, v):
            return ((cx + u * R * sx) * S, (cy + v * R * sy) * S)

        def poly(pts, fill=None, outline=None, width=0):
            q = [P(u, v) for u, v in pts]
            if fill is not None:
                dr.polygon(q, fill=fill)
            if outline is not None:
                dr.line(q + [q[0]], fill=outline, width=max(1, int(width * R * S)), joint="curve")

        def ell(u, v, ru, rv, n=40, a0=0.0, a1=2 * math.pi):
            return [(u + ru * math.cos(a0 + (a1 - a0) * i / n), v + rv * math.sin(a0 + (a1 - a0) * i / n))
                    for i in range(n + (0 if a1 - a0 >= 2 * math.pi else 1))]

        def stroke(pts, w, col=OC_INK):
            q = [P(u, v) for u, v in pts]
            dr.line(q, fill=col, width=max(2, int(w * R * S)), joint="curve")
            rr = w * R * S / 2
            for (x, y) in (q[0], q[-1]):
                dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)

        # le halo olive puis le disque clair, comme le halo violet de Bounce
        poly(ell(0, 0, 1.6, 1.6, 64), fill=dim(OC_OUT, 0.55))
        poly(ell(0, 0, 1.0, 1.0, 64), fill=OC_IN)
        if blush > 0:
            bc = mix(OC_IN, BLUSH, 0.75 * blush)
            poly(ell(-0.60, 0.16, 0.15, 0.08, 24), fill=bc)
            poly(ell(0.66, 0.22, 0.14, 0.08, 24), fill=bc)

        # le regard : seules les pupilles bougent, sous la paupière
        px, pv = gx * 0.05, max(-0.01, min(0.03, gy * 0.03))
        lo = 0.05 * annoy + 0.06 * wince
        rb_ = 0.10 * brow + 0.07 * opn          # le sourcil droit se lève ; les deux à la fin
        lb_ = 0.07 * opn
        # sourcils : plats et lourds, qui tombent vers la droite
        stroke([(-0.60, -0.50 + lo * 0.4 - lb_), (-0.18, -0.40 + lo - lb_)], 0.12)
        stroke([(0.14, -0.44 + lo - rb_), (0.60, -0.30 + lo * 0.4 - rb_ * 0.7)], 0.12)
        if wince > 0.5:
            stroke([(-0.52, -0.14), (-0.20, -0.12)], 0.10)
            stroke([(0.16, -0.10), (0.50, -0.07)], 0.10)
        elif blink > 0.5:
            for (eu, ev, ru, rv) in ((-0.36, -0.16, 0.17, 0.13), (0.33, -0.12, 0.17, 0.15)):
                stroke([(eu - ru - 0.02, ev + 0.04), (eu + ru + 0.02, ev + 0.04)], 0.07)
            stroke([(-0.53, -0.12), (-0.62, -0.18)], 0.06)
        else:
            # les yeux mi-clos : la moitié basse d'une pupille noire, coupée par une paupière droite ;
            # le gauche allongé avec un cil vers l'extérieur, le droit plus grand qui coule en bas
            for (eu, ev, ru, rv) in ((-0.36, -0.16, 0.17, 0.13), (0.33, -0.12, 0.17, 0.15)):
                if opn <= 0.001:
                    poly([(eu - ru, ev)] + ell(eu + px, ev + pv * 0.5, ru, rv, 24, 0.0, math.pi)[::-1] + [(eu + ru, ev)], fill=OC_INK)
                    stroke([(eu - ru - 0.02, ev), (eu + ru + 0.02, ev)], 0.07)
                else:
                    # la paupière remonte : la pupille entière apparaît, avec un reflet
                    rv2 = rv * (1 + 0.25 * opn)
                    lid = ev - rv2 * 0.95 * opn
                    pts = [(u, max(v, lid)) for (u, v) in ell(eu + px, ev + pv * 0.5, ru, rv2, 40)]
                    poly(pts, fill=OC_INK)
                    stroke([(eu - ru * (1 - 0.3 * opn), lid), (eu + ru * (1 - 0.3 * opn), lid)], 0.07 * (1 - 0.5 * opn))
                    if opn > 0.6:
                        poly(ell(eu + px - 0.055, ev - rv2 * 0.35, 0.045, 0.045, 16), fill=(250, 250, 244))
            stroke([(-0.53, -0.16 - 0.1 * opn), (-0.62, -0.22 - 0.1 * opn)], 0.06)
            poly([(0.42, -0.02), (0.52, 0.07), (0.46, 0.10), (0.37, 0.02)], fill=OC_INK)
        # bouche : petit trait en biais ; il se courbe en un petit sourire à la fin
        if wince > 0.5:
            stroke([(-0.20, 0.42), (-0.10, 0.37), (0.0, 0.43), (0.10, 0.38)], 0.08)
        elif smile <= 0.001:
            stroke([(-0.20, 0.38), (0.10, 0.46)], 0.09)
        else:
            pts = []
            for i in range(9):
                s = i / 8
                u = lerp(-0.20, 0.10, s) * (1 + 0.25 * smile)
                v = lerp(0.38, 0.46, s) * (1 - smile) + (0.40 + 0.10 * math.sin(math.pi * s) - 0.03 * s) * smile
                pts.append((u, v))
            stroke(pts, 0.09)

        # le bandeau bleu en travers du haut de la tête, et le nœud clair sur le côté droit
        band = ell(0, 0, 0.99, 0.99, 20, math.radians(-128), math.radians(-62))
        inner = ell(0, 0, 0.79, 0.79, 20, math.radians(-128), math.radians(-62))[::-1]
        poly(band + inner, fill=HAT_FILL, outline=HAT_LINE, width=0.05)
        kx, ky = 0.36, -0.86

        def lobe(ang, L, Wd):
            ca, sa = math.cos(ang), math.sin(ang)
            pts = []
            for i in range(32):
                k = 2 * math.pi * i / 32
                u, v = L / 2 * (1 + math.cos(k)), Wd * math.sin(k) * (0.55 + 0.45 * (1 + math.cos(k)) / 2)
                pts.append((kx + u * ca - v * sa, ky + u * sa + v * ca))
            return pts
        poly(lobe(math.radians(-25), 0.50, 0.20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
        poly(lobe(math.radians(-120), 0.46, 0.19), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
        poly(lobe(math.radians(40), 0.30, 0.10), fill=BOW_FILL, outline=BOW_LINE, width=0.06)
        poly(ell(kx, ky, 0.10, 0.09, 20), fill=BOW_FILL, outline=BOW_LINE, width=0.06)

    # ---- le dessin
    def draw_strand_pts(self, pts, S, w=7):
        q = [(x * S, y * S) for (x, y) in pts]
        dr = self._dr
        dr.line(q, fill=PASTA_D, width=int((w + 3) * S), joint="curve")
        dr.line(q, fill=PASTA, width=int(w * S), joint="curve")

    def strand_points(self, st, t):
        """La forme d'un spaghetti : une vague qui tourne en vol ; posé, il épouse ce qui le porte."""
        L = 64.0
        if t < st["t1"]:
            s = t - st["t0"]
            x = st["x0"] + st["vx"] * s
            y = st["y0"] + st["vy"] * s + 0.5 * G * s * s
            a = st["ph"] + s * 9.0
            ca, sa = math.cos(a), math.sin(a)
            pts = []
            for i in range(13):
                u = (i / 12 - 0.5) * L
                v = 7 * math.sin(i / 12 * 2 * math.pi + st["ph"])
                pts.append((x + u * ca - v * sa, y + u * sa + v * ca))
            return pts
        shape = st["shape"]
        if shape == "still" or shape == "waiter":
            if shape == "still":
                cx, cy, r = SX, SEAT - R, R + 3
                a0, a1 = -150, -30
            else:
                cx, cy, r = self.waiter_x(t), WT_HEAD_Y + self.waiter_dip(t), WT_HEAD_R + 3
                a0, a1 = -165, -15
            pts = [(cx + r * math.cos(math.radians(lerp(a0, a1, i / 10))),
                    cy + r * math.sin(math.radians(lerp(a0, a1, i / 10)))) for i in range(11)]
            # les deux bouts pendent
            l0, l1 = pts[0], pts[-1]
            sway = 2 * math.sin(t * 3.1)
            return [(l0[0] - 4 + sway, l0[1] + 34)] + pts + [(l1[0] + 4 + sway, l1[1] + 26)]
        if shape == "glass":
            x0, y0 = GS_X - 6, TT - GH - 1
            return [(x0 - 10, y0 + 28), (x0 - 16, y0 + 6), (x0 - 6, y0 - 3), (x0 + 8, y0 + 4), (x0 + 6, y0 + 30), (x0 + 12, y0 + 52)]
        x0, y0 = st["tx"], st["ty"]
        return [(x0 - 24 + 6 * i, y0 - 2 + 3 * math.sin(i * 1.3 + st["ph"])) for i in range(9)]

    def waiter_dip(self, t):
        d = 0.0
        for th in self.head_hits:
            k = t - th
            if 0 <= k < 0.5:
                d = max(d, 10 * math.exp(-k * 8) * math.cos(k * 18))
        return d

    def draw_waiter(self, dr, t, S):
        x = self.waiter_x(t)
        if x > WT_OFF - 10:
            return
        bob = -7 * abs(math.sin(t * 7.5)) if self.waiter_walking(t) else 0.0
        dip = self.waiter_dip(t)
        hy = WT_HEAD_Y + bob + dip
        R_ = lambda x0, y0, x1, y1, col, r=0: dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=col)
        # les jambes, avec un pas quand il marche
        sw = 14 * math.sin(t * 7.5) if self.waiter_walking(t) else 0.0
        R_(x - 52 + sw, 1150 + bob, x - 8 + sw, FLOOR, WAITER_D, 10)
        R_(x + 8 - sw, 1150 + bob, x + 52 - sw, FLOOR, WAITER_D, 10)
        # le buste
        R_(x - 75, 790 + bob + dip * 0.6, x + 75, 1180 + bob, WAITER, 40)
        # la tête : un disque, sans visage
        dr.ellipse([(x - WT_HEAD_R) * S, (hy - WT_HEAD_R) * S, (x + WT_HEAD_R) * S, (hy + WT_HEAD_R) * S], fill=WAITER)
        # le nœud papillon et la serviette sur le bras
        ny = 806 + bob + dip * 0.6
        dr.polygon([((x - 22) * S, (ny - 10) * S), ((x - 22) * S, (ny + 10) * S), (x * S, ny * S)], fill=TOWEL)
        dr.polygon([((x + 22) * S, (ny - 10) * S), ((x + 22) * S, (ny + 10) * S), (x * S, ny * S)], fill=TOWEL)
        dr.ellipse([(x - 6) * S, (ny - 6) * S, (x + 6) * S, (ny + 6) * S], fill=TOWEL)
        R_(x - 92, 930 + bob, x - 58, 1040 + bob, TOWEL, 8)

    def draw_chair(self, dr, S, x0, x1, back_x0, back_x1):
        rect = lambda a, b, c, d, col: dr.rectangle([a * S, b * S, c * S, d * S], fill=col)
        rect(back_x0, 990, back_x1, SEAT + 20, CHAIR_D)
        dr.ellipse([(back_x0 - 4) * S, 978 * S, (back_x1 + 4) * S, 1002 * S], fill=CHAIR_D)
        rect(x0 + 8, SEAT + 20, x0 + 20, FLOOR, CHAIR_D)
        rect(x1 - 20, SEAT + 20, x1 - 8, FLOOR, CHAIR_D)
        dr.rounded_rectangle([x0 * S, SEAT * S, x1 * S, (SEAT + 20) * S], radius=6 * S, fill=CHAIR)

    def draw_glass(self, dr, S, cx, base_y, ang=0.0, pivot=None, water_k=1.0, ripple=0.0):
        """Un verre (40 × 75), tourné de `ang` autour de `pivot` (ou de son pied)."""
        px_, py_ = pivot if pivot is not None else (cx - GW / 2, base_y)
        ca, sa = math.cos(ang), math.sin(ang)

        def P(x, y):
            u, v = x - px_, y - py_
            return ((px_ + u * ca - v * sa) * S, (py_ + u * sa + v * ca) * S)
        x0, x1, y1, y0 = cx - GW / 2, cx + GW / 2, base_y, base_y - GH
        body = [P(x0, y0), P(x1, y0), P(x1 - 3, y1), P(x0 + 3, y1)]
        dr.polygon(body, fill=dim(GLASS, 0.35))
        if water_k > 0:
            wy = y1 - (GH - 14) * water_k
            dr.polygon([P(x0 + 2, wy + ripple), P(x1 - 2, wy - ripple), P(x1 - 4, y1 - 3), P(x0 + 4, y1 - 3)], fill=WATER)
        dr.line(body + [body[0]], fill=GLASS, width=int(3 * S))
        dr.line([P(x0 + 9, y0 + 10), P(x0 + 9, y1 - 14)], fill=(230, 240, 250), width=int(3 * S))

    def draw(self, dr, snap, t, S):
        self._dr = dr
        rect = lambda a, b, c, d, col: dr.rectangle([a * S, b * S, c * S, d * S], fill=col)
        # le mur, le lambris, le sol
        rect(0, WALL_TOP, W, FLOOR, WALL)
        rect(0, 1090, W, FLOOR, WALL_LOW)
        rect(0, 1084, W, 1092, TRIM)
        rect(0, FLOOR, W, H, FLOOR_COL)
        rect(0, FLOOR, W, FLOOR + 6, TRIM)
        # la fenêtre : la nuit, la lune
        rect(712, 532, 1008, 808, WIN_FRAME)
        rect(726, 546, 994, 794, WINDOW)
        dr.ellipse([920 * S, 580 * S, 970 * S, 630 * S], fill=(226, 226, 204))
        dr.ellipse([934 * S, 572 * S, 984 * S, 622 * S], fill=WINDOW)
        for (sx_, sy_) in [(770, 600), (830, 700), (900, 740), (960, 700), (790, 760)]:
            dr.ellipse([(sx_ - 3) * S, (sy_ - 3) * S, (sx_ + 3) * S, (sy_ + 3) * S], fill=(150, 156, 190))
        rect(856, 546, 864, 794, WIN_FRAME)
        rect(726, 666, 994, 674, WIN_FRAME)
        # la lumière de la lampe (elle suit la lampe quand elle balance)
        Pl, shade = self.lamp_geom(t)
        cone = [shade[3], shade[2], Pl(260, 760), Pl(-260, 760)]
        dr.polygon([(x * S, y * S) for (x, y) in cone], fill=CONE)
        # la lueur de la bougie sur le mur
        fl = 0.92 + 0.08 * math.sin(t * 11) * math.sin(t * 4.3)
        for (rr, kk) in ((95, 0.25), (70, 0.5), (45, 0.8)):
            col = mix(WALL, GLOW, kk)
            dr.ellipse([(CA_X - rr * fl) * S, (1080 - rr * fl) * S, (CA_X + rr * fl) * S, (1080 + rr * fl) * S], fill=col)
        # le serveur, derrière la table
        self.draw_waiter(dr, t, S)
        # les chaises
        self.draw_chair(dr, S, 70, 270, 40, 55)
        self.draw_chair(dr, S, SX - 95, SX + 95, SX + 115, SX + 130)
        # Still
        self.draw_oc(dr, t, S)
        # la table : pied, plateau à carreaux
        rect(528, TT + 20, 552, FLOOR - 14, PEDESTAL)
        dr.ellipse([440 * S, (FLOOR - 22) * S, 640 * S, (FLOOR + 4) * S], fill=PEDESTAL)
        self.draw_tabletop(dr, t, S)
        # le verre de Bounce, l'eau renversée
        self.draw_bounce_glass(dr, t, S)
        # le verre de Still : l'eau tremble quand la table prend un coup
        rip = 0.0
        for th in self.table_hits:
            d = t - th
            if 0 <= d < 1.2:
                rip += 5 * math.exp(-d * 4) * math.sin(d * 30)
        self.draw_glass(dr, S, GS_X, TT, ripple=rip)
        # la bougie
        self.draw_candle(dr, t, S)
        # l'assiette
        self.draw_plate(dr, t, S)
        # les spaghettis
        for st in self.strands:
            if t >= st["t0"]:
                self.draw_strand_pts(self.strand_points(st, t), S)
        # la lampe, par-dessus
        dr.line([(LAMP_X * S, LAMP_Y0 * S), (Pl(0, LAMP_L)[0] * S, Pl(0, LAMP_L)[1] * S)], fill=(70, 64, 78), width=int(5 * S))
        bulb = Pl(0, LAMP_L + 58)
        dr.ellipse([(bulb[0] - 22) * S, (bulb[1] - 14) * S, (bulb[0] + 22) * S, (bulb[1] + 14) * S], fill=(255, 236, 170))
        dr.polygon([(x * S, y * S) for (x, y) in shade], fill=SHADE)
        dr.line([(x * S, y * S) for (x, y) in shade[2:4]], fill=SHADE_D, width=int(6 * S))
        # Bounce, devant tout
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, by * S, RB * S)

    def draw_tabletop(self, dr, t, S):
        # le chant de la nappe
        dr.rounded_rectangle([TL * S, (TT - 2) * S, TR * S, (TT + 22) * S], radius=6 * S, fill=CLOTH_EDGE)
        # le dessus, vu un peu d'en haut : une bande de carreaux
        n = 14
        w = (TR - TL) / n
        for i in range(n):
            for j in range(2):
                col = CLOTH_B if (i + j) % 2 == 0 else CLOTH_A
                y0 = TT - 16 + j * 8
                inset = 6 * (1 - j)
                x0 = TL + inset + i * (TR - TL - 2 * inset) / n
                x1 = TL + inset + (i + 1) * (TR - TL - 2 * inset) / n
                dr.rectangle([x0 * S, y0 * S, x1 * S, (y0 + 8) * S], fill=col)
        for i in range(n):
            col = CLOTH_A if i % 2 == 0 else CLOTH_B
            x0, x1 = TL + i * w, TL + (i + 1) * w
            dr.rectangle([x0 * S, TT * S, x1 * S, (TT + 16) * S], fill=col)
        # l'eau renversée sur la nappe, et les gouttes
        tg = self.t_glass + 0.25
        if t >= tg:
            k = ease((t - tg) / 1.4)
            dr.ellipse([(TL - 2) * S, (TT - 6) * S, (TL + 20 + 110 * k) * S, (TT + 6) * S], fill=dim(WATER, 0.8))
            dr.rectangle([TL * S, TT * S, (TL + 10 + 60 * k) * S, (TT + 18) * S], fill=dim(WATER, 0.62))
            for i in range(10):
                t0 = tg + 0.3 + i * 0.28
                d = t - t0
                if 0 <= d:
                    y = TT + 18 + 0.5 * G * d * d
                    if y < FLOOR - 4:
                        dr.ellipse([(TL + 4) * S, (y - 6) * S, (TL + 14) * S, (y + 6) * S], fill=WATER)
            fk = ease((t - tg - 0.6) / 3.0)
            if fk > 0:
                dr.ellipse([(TL - 30 - 40 * fk) * S, (FLOOR - 3) * S, (TL + 40 + 30 * fk) * S, (FLOOR + 5) * S], fill=dim(WATER, 0.55))

    def draw_bounce_glass(self, dr, t, S):
        a0, a1 = self.glass_tip
        pivot = (GL_X - GW / 2, TT)
        if t < a0:
            self.draw_glass(dr, S, GL_X, TT)
            return
        if t < a1:
            k = ((t - a0) / (a1 - a0)) ** 2
            self.draw_glass(dr, S, GL_X, TT, ang=-math.pi / 2 * k, pivot=pivot, water_k=1 - 0.6 * k)
            return
        # il glisse du bord et tombe en faisant un demi-tour, puis reste couché au sol
        tf = self.glass_fall_t
        d = t - a1
        cx0, cy0 = pivot[0] - GH / 2, TT - GW / 2          # son centre, couché sur la nappe
        if d < tf:
            s = d / tf
            cy = cy0 + 0.5 * G * d * d
            cx = cx0 - 10 * s
            ang = -math.pi / 2 - math.pi * s
        else:
            cx, cy = cx0 - 10, FLOOR - GW / 2
            ang = -3 * math.pi / 2 + 0.06 * math.exp(-(d - tf) * 6) * math.sin((d - tf) * 25)
        # dessiné autour de son centre
        self.draw_glass(dr, S, cx, cy + GH / 2, ang=ang, pivot=(cx, cy), water_k=0.0)

    def draw_candle(self, dr, t, S):
        lean = 0.06 * math.sin(t * 6.3) + 0.04 * math.sin(t * 13.1)
        for th in self.table_hits + self.lamp_hits:
            d = t - th
            if 0 <= d < 1.5:
                lean += 0.5 * math.exp(-d * 3) * math.sin(d * 14)
        dr.rounded_rectangle([(CA_X - 20) * S, (TT - 10) * S, (CA_X + 20) * S, TT * S], radius=4 * S, fill=HOLDER)
        dr.rectangle([(CA_X - 9) * S, 1100 * S, (CA_X + 9) * S, (TT - 10) * S], fill=CANDLE)
        dr.line([(CA_X * S, 1100 * S), (CA_X * S, 1092 * S)], fill=(40, 30, 30), width=int(3 * S))
        # la flamme : une goutte qui penche
        bx_, by_ = CA_X, 1094.0
        h, w = 34.0, 11.0
        for (hh, ww, col) in ((h, w, FLAME_O), (h * 0.6, w * 0.55, FLAME_I)):
            pts = []
            for i in range(25):
                a = 2 * math.pi * i / 24
                u = ww * math.sin(a) * (1 - 0.5 * (1 - math.cos(a)) / 2)
                v = -hh * (1 - math.cos(a)) / 2
                pts.append(((bx_ + u - v * lean) * S, (by_ + v * 0.98 + 2) * S))
            dr.polygon(pts, fill=col)

    def draw_plate(self, dr, t, S):
        a0, a1 = self.plate_flip
        if t < a0:
            cx, cy, ang = PL_X, TT - 6, 0.0
        elif t < a1:
            s = (t - a0) / (a1 - a0)
            cx = PL_X + 18 * math.sin(math.pi * s)
            cy = TT - 6 - 4 * 90 * s * (1 - s)
            ang = -math.pi * ease(s)
        else:
            cx, cy, ang = PL_X, TT - 6, -math.pi
        ca, sa = math.cos(ang), math.sin(ang)

        def P(u, v):
            return ((cx + u * ca - v * sa) * S, (cy + u * sa + v * ca) * S)
        if t < a0:
            # le tas de spaghettis, la sauce
            mound = [P(-46, -4)] + [P(-46 + 92 * i / 12, -6 - 28 * math.sin(math.pi * i / 12) - 3 * math.sin(i * 2.1)) for i in range(13)] + [P(46, -4)]
            dr.polygon(mound, fill=PASTA)
            for k in range(5):
                u0 = -36 + 16 * k
                dr.line([P(u0, -8), P(u0 + 8, -20 - 4 * (k % 2)), P(u0 + 16, -10)], fill=PASTA_D, width=int(3 * S))
            dr.ellipse([P(-14, -38)[0], P(-14, -38)[1], P(16, -22)[0], P(16, -22)[1]], fill=SAUCE)
        body = [P(-70, -6), P(70, -6), P(42, 6), P(-42, 6)]
        dr.polygon(body, fill=PLATE)
        dr.line([P(-70, -6), P(70, -6)], fill=PLATE_D, width=int(3 * S))


DEFAULTS = {
    "fps": 60,
    "min_duration_s": 8.0,
    "max_duration_s": 75.0,
    "end_hold_s": 0.0,
    "hook_text_s": 2.6,
    "narrator_length": 1.0,
    "sub_y": 0.84,
    "sub_font_size": 64,
    "hero_win": "Bounce",            # même sa réaction de la fin : il ne dit que son nom
    "hop_s": 0.42,
    "reply_delay": 0.4,
    "reply_keys": ["l2", "l6"],
    "look_waiter": ["l1", "l2", "l6", "l8"],
    "lines": [
        [2.5, "Table for two?", "l1"],
        [10.0, "Anything to drink?", "l2"],
        [12.6, "Water it is.", "l3"],
        [21.6, "How's the pasta?", "l4"],
        [26.6, "Is everything alright here?", "l5"],
        [44.4, "Dessert?", "l6"],
        [46.6, "I'll take that as a no.", "l7"],
        [54.4, "Same table next week?", "l8"],
        [61.0, "I'll take that as a yes.", "l9"],
    ],
    "open_after_s": 1.3,
    "t_big": 58.0,
    "big_s": 1.55,
    "end_s": 63.4,
    # le serveur : (t, x) ; WT_OFF = hors champ à droite
    "waiter": [[0.0, 700.0], [3.9, 700.0], [5.1, 1220.0], [8.4, 1220.0], [9.6, 700.0], [13.9, 700.0],
               [15.1, 1220.0], [19.6, 1220.0], [20.8, 700.0], [36.9, 700.0], [38.1, 1220.0],
               [42.4, 1220.0], [43.6, 700.0]],
}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
