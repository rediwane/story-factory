"""
Prototype « baby » : Bounce garde un bébé. Les parents viennent de l'endormir ; au mur, un mot
« DO NOT WAKE HIM! ». Bounce rebondit et dit son nom à chaque contact dur ; chaque « Bounce »
lance un anneau blanc qui traverse la chambre : quand il atteint le lit, les « Z » du bébé
éclatent et le bébé réagit (sursaut, tête levée, à moitié assis…). Sur le mou (tapis, matelas),
Bounce se tait. Il finit dans le lit, le bébé se réveille et saute avec lui, les parents entrent :
« Who woke you up? » — « Bounce! » — « His first word… ».

Une seule scène, plan fixe, tout est calculé d'avance sur une horloge : Bounce suit une liste
de contacts reliés par des arcs balistiques sous une gravité unique (G = 2600 px/s²) ; les autres
acteurs suivent des pistes à images clés.

Les voix de la mère, du père et du bébé viennent d'une banque hors dépôt (cfg["voice_bank"]),
lue à la place de la voix du narrateur ; leurs répliques sont des bulles dessinées.

    python3 src/stories/baby.py configs/<name>.json [--simulate]
"""
import math, sys, os, json, wave, tempfile, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import base
from base import dim, font
from PIL import Image, ImageDraw
import audio_kit as ak
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import voice as narr_voice

SR = ak.SR
BANK_DIR = "/tmp/claude-0/-home-user-bouncefactory/b9b675be-c303-52dd-8eb3-2f9df7a3dbaa/scratchpad/lot4/baby/final"

# ------------------------------------------------------------------ les voix des personnages
BANK_FILES = {"Who woke you up?": "mom.wav", "His first word...": "dad.wav",
              "Bounce!": "baby1.wav", "BOUNCE!": "baby2.wav"}
BANK = {}
_orig_say = narr_voice.say


def _read(path):
    with wave.open(path) as w:
        n, fr = w.getnframes(), w.getframerate()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if fr != SR:
        idx = np.arange(0, len(x) - 1, fr / SR)
        x = np.interp(idx, np.arange(len(x)), x)
    return x


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK_FILES:
        if text not in BANK:
            d = os.environ.get("BABY_VOICE_BANK", BANK_DIR)
            BANK[text] = _read(os.path.join(d, BANK_FILES[text]))
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say

# ------------------------------------------------------------------ le mot de Bounce, stable
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
            if text != cfg["hero_name"] or len(v) / SR <= 0.74:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
BS = 1.35                         # échelle du bébé
G = 2600.0
R = 90.0
CEIL = 110.0
FL = 1440.0                       # dessus du plancher
FY = FL - R                       # centre de Bounce posé au sol
RUG = (200.0, 390.0, 1418.0)      # x0, x1, dessus du tapis
RY = RUG[2] - R
POST_L = (400.0, 436.0)
POST_R = (896.0, 930.0)
POST_TOP = 985.0
KNOB_R = 16.0
KNOB_L = (418.0, POST_TOP - 13.0)
KNOB_RR = (913.0, POST_TOP - 13.0)
KNOB_Y = KNOB_L[1] - KNOB_R - R   # centre de Bounce posé sur la boule
MT = 1255.0                       # dessus du matelas
MY = MT - R
SIDE_X = POST_L[1] + R            # Bounce contre le montant gauche, de l'intérieur
IN_X = 582.0                      # Bounce dans le lit
DOOR = (30.0, 200.0, 1010.0, FL)
WIN = (250.0, 420.0, 580.0, 800.0)
NOTE_C = (640.0, 556.0)
NOTE_W, NOTE_H = 400.0, 220.0
HUB = (780.0, 715.0)
ARM_Y = 680.0
STRING = 95.0
TOY_R = 24.0

# couleurs
BG = (8, 8, 12)
WALL = (22, 26, 52)
WALL_D = (16, 18, 38)
FLOOR_C = (52, 36, 32)
FLOOR_L = (70, 50, 42)
WOOD = (150, 104, 70)
WOOD_D = (96, 66, 46)
MATT = (226, 228, 238)
RUG_C = (150, 128, 196)
RUG_D = (110, 92, 150)
SWAD = (242, 228, 150)
SWAD_D = (206, 190, 112)
SKIN = (242, 190, 160)
SKIN_D = (200, 140, 112)
PACI = (110, 190, 240)
ZCOL = (196, 176, 255)
WARM = (255, 214, 140)
MOM = (64, 168, 164)
DAD = (214, 150, 70)
SIL = (24, 20, 26)
TOYS = [((255, 214, 70), "star"), ((170, 200, 255), "moon"), ((236, 236, 246), "cloud")]


def clamp01(u):
    return max(0.0, min(1.0, u))


def smooth(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def mix(a, b, k):
    k = clamp01(k)
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def lerp(a, b, k):
    return a + (b - a) * k


class KF:
    """Valeur scalaire à images clés : liste de (t, v) ; transitions lissées."""

    def __init__(self, v0, keys=()):
        self.keys = [(-1e9, v0)] + sorted(keys)
        self.ts = [k[0] for k in self.keys]

    def __call__(self, t):
        i = bisect.bisect_right(self.ts, t) - 1
        if i >= len(self.keys) - 1:
            return self.keys[-1][1]
        t0, v0 = self.keys[i]
        t1, v1 = self.keys[i + 1]
        if t0 < -1e8:
            return v0
        return lerp(v0, v1, smooth((t - t0) / max(1e-6, t1 - t0)))


def hold_to(v_from, t0, d_in, v, t_hold, d_out, v_back):
    """Petit raccourci : monte à v en d_in, tient jusqu'à t_hold, revient en d_out."""
    return [(t0, v_from), (t0 + d_in, v), (t_hold, v), (t_hold + d_out, v_back)]


# ------------------------------------------------------------------ le plan
END = 62.2
PAYOFF = 56.45

# (t, genre, gain) ; genre : rug:x / floor:x / knob / mob / paci / mat:x[:dent] / side
PLAN = [
    (0.5, "rug:285", 0), (1.6, "rug:250", 0),
    (2.4, "floor:110", 0.9), (3.3, "floor:92", 1.05), (4.6, "rug:275", 0),
    (5.4, "floor:115", 0.5), (6.3, "floor:110", 0.28), (7.2, "floor:100", 0.12),
    (8.3, "knob", 1.15), (9.5, "rug:275", 0), (10.5, "floor:120", 0.4),
    (11.4, "floor:90", 0.95), (12.5, "knob", 0.9), (13.4, "mob", 0.8), (14.6, "rug:228", 0),
    (15.5, "floor:110", 0.85), (16.5, "mob", 1.0), (17.4, "knob", 0.9), (18.3, "mob", 1.2),
    (19.5, "rug:240", 0), (20.6, "floor:120", 0.12), (21.5, "floor:80", 0.85),
    (22.4, "floor:120", 0.8), (23.3, "rug:275", 0), (24.1, "rug:285", 0),
    (24.7, "floor:115", 0.9), (25.6, "floor:100", 1.0), (26.5, "rug:275", 0),
    (27.4, "paci", 0.9), (28.3, "floor:100", 1.0),
    (29.25, "knob", 0.9), (30.15, "mat:552", 0), (30.6, "side", 0.25), (31.1, "mat:536", 0), (31.85, "mat:530", 0),
    (32.5, "mob", 0.45), (33.3, "mat:534", 0), (34.05, "mat:530", 0), (34.6, "side", 0.8),
    (35.4, "mat:536", 0), (36.15, "mat:532:26", 0), (36.8, "mob", 0.95), (37.6, "mat:530", 0),
    (38.4, "mat:530", 0), (38.9, "side", 1.0), (40.0, "mat:536:28", 0), (40.9, "side", 1.35),
    (41.7, "mat:534", 0), (42.4, "mat:530", 0), (43.0, "side", 0.85), (43.6, "mat:536", 0),
    (44.4, "mob", 0.9), (45.1, "mat:530", 0), (45.9, "side", 0.95), (46.6, "mat:536", 0),
    (47.4, "side", 0.95), (48.1, "mat:534", 0), (48.6, "side", 1.0), (49.3, "mat:536", 0),
    (49.8, "side", 1.0), (50.5, "mat:534", 0), (51.0, "side", 1.0), (51.5, "mat:536", 0),
    (52.0, "side", 0.95),
    (52.5, "mat:534", 0), (53.0, "mat:538", 0), (53.5, "mat:534", 0), (54.0, "mat:538", 0),
    (54.5, "mat:534", 0), (55.0, "mat:538", 0), (55.5, "mat:534", 0), (56.0, "mat:538", 0),
    (56.5, "mat:534", 0), (57.0, "mat:538", 0), (57.5, "mat:534", 0),
    (58.0, "side", 0.9), (58.7, "mat:536", 0), (59.45, "mat:532", 0), (60.2, "side", 1.3),
    (60.95, "mat:538:24", 0), (61.75, "mat:540", 0),
]

# les instants où le bébé saute tout seul (éveillé), (t, hauteur)
BABY_HOPS = [(43.05, 34), (43.6, 46), (45.1, 54), (45.95, 58), (46.6, 62), (47.45, 60),
             (48.1, 52), (48.65, 40), (49.3, 58), (49.85, 66), (50.5, 46), (51.5, 50),
             (52.05, 60), (54.5, 78), (58.85, 90), (61.12, 115), (61.8, 90)]


class Mobile:
    """Le mobile : vitesse de rotation relancée à chaque coup, amortie ; l'étoile se décroche."""
    STAR_OFF = 18.3

    def __init__(self, kicks):
        self.dt = 1 / 240
        n = int((END + 2) / self.dt)
        self.phi = np.zeros(n)
        self.om = np.zeros(n)
        self.sp = np.zeros(n)
        ph, om, sp = 0.9, 0.0, 0.0
        ks = sorted(kicks)
        j = 0
        for i in range(n):
            t = i * self.dt
            while j < len(ks) and ks[j][0] <= t:
                om = om + ks[j][1] if om >= 0 else ks[j][1]
                j += 1
            om *= math.exp(-0.42 * self.dt) if t < 19.5 else math.exp(-0.9 * self.dt)
            if abs(om) < 0.05:
                om = 0.0
            ph += om * self.dt
            sp += (clamp01(abs(om) / 7.0) - sp) * min(1.0, 2.2 * self.dt)
            self.phi[i], self.om[i], self.sp[i] = ph, om, sp

    def state(self, t):
        i = max(0, min(len(self.phi) - 1, int(t / self.dt)))
        return self.phi[i], self.om[i]

    def spread(self, t):
        i = max(0, min(len(self.phi) - 1, int(t / self.dt)))
        return self.sp[i]

    def toys(self, t):
        """[(index, x, y, profondeur, couleur, forme, x_attache)] — l'étoile absente après sa chute."""
        ph, om = self.state(t)
        spread = self.spread(t)
        beta = 0.75 * spread                           # angle des fils
        rr = 62.0 + STRING * math.sin(beta)
        out = []
        for k in range(3):
            if k == 0 and t >= self.STAR_OFF:
                continue
            a = ph + k * 2 * math.pi / 3
            z = math.sin(a)
            x = HUB[0] + rr * math.cos(a)
            xa = HUB[0] + 62.0 * math.cos(a)
            y = HUB[1] + STRING * math.cos(beta)
            col, shape = TOYS[k]
            out.append((k, x, y, z, col, shape, xa))
        return out


class Plan:
    def __init__(self):
        kicks = [(t, {0.45: 1.6, 0.8: 2.6, 0.9: 4.0, 0.95: 4.5, 1.0: 6.5, 1.2: 9.0}.get(g, 3.0 * g))
                 for (t, k, g) in PLAN if k == "mob"]
        self.mob = Mobile(kicks)
        self.contacts = []
        for (t, kind, g) in PLAN:
            parts = kind.split(":")
            k = parts[0]
            if k == "rug":
                x, y, ax, soft = float(parts[1]), RY + 18, "y", True
            elif k == "floor":
                x, y, ax, soft = float(parts[1]), FY, "y", False
            elif k == "knob":
                x, y, ax, soft = KNOB_L[0], KNOB_Y, "y", False
            elif k == "paci":
                x, y, ax, soft = 165.0, FL - 14 - R, "y", False
            elif k == "mat":
                dent = float(parts[2]) if len(parts) > 2 else 16.0
                x, y, ax, soft = float(parts[1]), MY + dent, "y", True
            elif k == "side":
                x, y, ax, soft = SIDE_X, 1110.0, "x", False
            elif k == "mob":
                toys = self.mob.toys(t - 1e-3)
                i, tx, ty = min(((tt[0], tt[1], tt[2]) for tt in toys), key=lambda a: a[1])
                x, y, ax, soft = tx - TOY_R - R - 2, ty + 6, "x", False
            self.contacts.append({"t": t, "x": x, "y": y, "axis": ax, "soft": soft, "gain": g, "kind": k})
        # départ : l'image commence pendant la chute vers le tapis
        self.start = {"t": -0.62, "x": 330.0, "y": RY + 18}
        self.hits = [(c["t"], c["gain"], c["x"], c["y"]) for c in self.contacts if not c["soft"]]
        self.ts = [c["t"] for c in self.contacts]

    def seg(self, t):
        cs = self.contacts
        i = bisect.bisect_right(self.ts, t)
        a = self.start if i == 0 else cs[i - 1]
        if i >= len(cs):
            # après le dernier contact : un dernier arc qui monte
            b = {"t": a["t"] + 0.9, "x": a["x"] + 2, "y": a["y"] - 8}
        else:
            b = cs[i]
        return a, b

    def pos(self, t):
        a, b = self.seg(t)
        T = max(1e-6, b["t"] - a["t"])
        vx = (b["x"] - a["x"]) / T
        vy = (b["y"] - a["y"]) / T - 0.5 * G * T
        u = t - a["t"]
        return a["x"] + vx * u, a["y"] + vy * u + 0.5 * G * u * u

    def squash(self, t):
        sx = sy = 1.0
        for c in self.contacts:
            u = t - c["t"]
            if -0.06 <= u <= 0.14:
                kk = clamp01(1 + u / 0.06) if u < 0 else clamp01(1 - u / 0.14)
                amp = 0.1 if c["soft"] else 0.17
                if c["axis"] == "y":
                    sy *= 1 - amp * kk; sx *= 1 + 0.8 * amp * kk
                else:
                    sx *= 1 - amp * kk; sy *= 1 + 0.6 * amp * kk
        return sx, sy

    def ball(self, t):
        x, y = self.pos(t)
        sx, sy = self.squash(t)
        return x, y, R * sx, R * sy


# ------------------------------------------------------------------ le bébé
class Baby:
    def __init__(self, plan):
        self.plan = plan
        self.theta = KF(0.0, [(19.0, 0.0), (19.25, 40.0), (20.3, 40.0), (20.9, 0.0),
                              (41.3, 0.0), (41.55, 90.0)])
        self.head = KF(0.0, hold_to(0, 3.35, 0.3, 1.0, 4.6, 0.6, 0) + hold_to(0, 8.55, 0.3, 1.0, 9.5, 0.6, 0))
        self.arm = KF(0.0, hold_to(0, 3.4, 0.3, 0.8, 4.6, 0.6, 0) + hold_to(0, 8.6, 0.3, 1.0, 9.5, 0.6, 0)
                      + hold_to(0, 13.8, 0.4, 0.9, 15.0, 0.5, 0))
        self.leg = KF(0.0, hold_to(0, 3.35, 0.2, 1.0, 4.6, 0.6, 0) + hold_to(0, 17.7, 0.15, 1.0, 17.9, 0.5, 0))
        self.swell = KF(0.0, [(26.1, 0.0), (27.4, 0.55), (28.5, 0.6), (28.65, 0.0),
                              (41.6, 0.0), (42.95, 1.0), (43.0, 1.0), (43.12, 0.0)])
        self.hug = KF(0.0, [(30.9, 0.0), (31.25, 1.0), (38.4, 1.0), (38.8, 0.0)])
        self.dx = KF(0.0, [(38.4, 0.0), (38.9, 3.0)])
        self.up = KF(0.0, [(44.3, 0.0), (44.6, 1.0), (52.6, 1.0), (52.9, 0.3), (54.4, 0.3), (54.6, 1.0)])
        self.jolts = [(2.65, 14), (3.55, 6), (12.7, 7), (17.7, 9), (25.85, 10), (41.2, 6)]
        self.wiggles = [(2.95, 3.6, 5.0), (12.7, 13.5, 5.0), (26.0, 28.5, 4.0), (19.25, 20.3, 7.0)]
        self.trembles = [(3.6, 4.6), (8.85, 9.5), (26.4, 28.5), (41.6, 43.0)]
        self.mat_hops = [(36.15, 22), (40.0, 30)]

    def hop_y(self, t):
        y = 0.0
        for (t0, h) in self.mat_hops + BABY_HOPS:
            T = 2 * math.sqrt(2 * h / G)
            u = t - t0
            if 0 <= u <= T:
                y = max(y, h - 0.5 * G * (u - T / 2) ** 2 if True else 0)
        return y

    def pose(self, t):
        th = self.theta(t)
        wob = 0.0
        for (a, b, amp) in self.wiggles:
            if a <= t <= b:
                wob += amp * math.sin((t - a) * 2 * math.pi * 2.2) * math.sin(math.pi * (t - a) / (b - a))
        th += wob
        jy = 0.0
        for (tj, amp) in self.jolts:
            u = t - tj
            if 0 <= u <= 0.3:
                jy += amp * math.sin(math.pi * u / 0.3)
        trem = 0.0
        for (a, b) in self.trembles:
            if a <= t <= b:
                trem = 2.2 * math.sin(t * 95.0)
        lift = self.hop_y(t)
        hug = self.hug(t)
        if hug > 0.01:
            bx, by = self.plan.pos(t)
            lift = max(lift, hug * clamp01((MY - by) / 160.0) * 26.0)
        return {"th": math.radians(th), "jy": jy + lift, "trem": trem, "head": self.head(t), "arm": self.arm(t),
                "leg": self.leg(t), "swell": self.swell(t), "hug": hug, "dx": self.dx(t), "up": self.up(t),
                "sit": clamp01(self.theta(t) / 90.0)}

    def frame(self, t):
        """Repère du bébé : renvoie une fonction (u, v) -> (x, y). u le long du dos, des pieds (0) à la
        tête (~150) ; v vers le ventre (négatif = au-dessus quand il est couché)."""
        p = self.pose(t)
        th = p["th"]
        px = 893.0 - 160.0 * p["sit"] + p["dx"] + p["trem"]
        py = MT - p["jy"]
        ct, st = math.cos(th), math.sin(th)

        def P(u, v):
            x, y = -u * BS, (v - 32.0) * BS
            return (px + x * ct - y * st, py + x * st + y * ct)
        return P, p


# ------------------------------------------------------------------ les Z
class Zs:
    def __init__(self):
        spawns = []
        def every(a, b, per, size):
            t = a
            while t < b:
                spawns.append((t, size)); t += per
        every(-2.6, 2.6, 0.85, 1.0)
        spawns += [(5.0, 0.8), (6.45, 0.9), (7.35, 1.0), (10.7, 0.8), (11.5, 0.9), (14.0, 0.9), (14.9, 1.0),
                   (15.9, 1.0), (16.9, 0.9), (20.75, 0.8), (21.6, 0.9), (22.5, 1.0), (23.4, 1.0), (24.3, 1.0),
                   (25.2, 1.0), (28.65, 0.9), (29.4, 1.0)]
        every(30.0, 40.9, 0.8, 1.7)
        self.spawns = spawns
        self.bursts = [2.65, 3.55, 8.5, 12.7, 17.7, 18.6, 25.85, 41.25]
        self.trembles = [5.55, 16.8, 34.75, 36.95, 39.05]
        self.freeze = (40.95, 41.25)
        self.life = 2.6

    def visible(self, t, P):
        out = []
        hx, hy = P(150, -18)
        for (ts, size) in self.spawns:
            age = t - ts
            if age < 0 or age > self.life:
                continue
            b = max([tb for tb in self.bursts if ts < tb <= t] or [None]) if any(ts < tb <= t for tb in self.bursts) else None
            a_eff = age
            if self.freeze[0] <= t and ts < self.freeze[0]:
                a_eff = min(age, self.freeze[0] - ts)
            k = a_eff / self.life
            x = hx + 18 + 60 * k * size + 14 * math.sin(ts * 3.1 + a_eff * 2.2)
            y = hy - 30 - 230 * k * (0.8 + 0.2 * size)
            alpha = clamp01(a_eff / 0.3) * clamp01((self.life - a_eff) / 0.6)
            fs = (46 + 34 * k) * size
            if b is not None:
                u = t - b
                if u > 0.35:
                    continue
                ang = ts * 2.7
                x += math.cos(ang) * 260 * u / 0.35
                y += math.sin(ang) * 200 * u / 0.35 - 80 * u
                alpha *= 1 - u / 0.35
                fs *= 1 + 0.6 * u / 0.35
            for tt in self.trembles:
                if 0 <= t - tt <= 0.4 and ts < tt:
                    x += 6 * math.sin(t * 80 + ts)
                    y += 4 * math.cos(t * 70 + ts)
            out.append((x, y, fs, alpha))
        return out


# ------------------------------------------------------------------ les acteurs secondaires
def arc_point(p0, p1, t0, T, t):
    u = clamp01((t - t0) / T) * T
    vx = (p1[0] - p0[0]) / T
    vy = (p1[1] - p0[1]) / T - 0.5 * G * T
    return p0[0] + vx * u, p0[1] + vy * u + 0.5 * G * u * u


class Scene:
    def __init__(self):
        self.P = Plan()
        self.B = Baby(self.P)
        self.Z = Zs()
        # porte : ouverture (0 fermée, 1 grande ouverte), lumière du couloir (0..1)
        self.door_o = KF(0.075, [(0.0, 0.075), (1.0, 0.0), (47.0, 0.0), (47.3, 0.12), (48.55, 0.12), (49.0, 1.0)])
        self.hall = KF(1.0, [(1.0, 1.0), (1.3, 0.0), (22.0, 0.0), (22.2, 1.0), (24.45, 1.0), (24.65, 0.0),
                             (43.0, 0.0), (43.2, 1.0)])
        self.handle = KF(0.0, [(45.6, 0.0), (46.0, 1.0), (49.0, 1.0), (49.2, 0.0)])
        # ombres de pieds : (arrivée, départ)
        self.feet = [(22.4, 22.75, 24.3, 24.6), (44.1, 44.5, 1e9, 1e9 + 1)]
        # parents : 0 absents ; silhouettes dans la porte ; entrée
        self.par_in = KF(0.0, [(51.0, 0.0), (51.9, 1.0)])
        self.dad_sag = KF(0.0, [(52.2, 0.0), (52.6, 1.0)])
        self.dad_sit = KF(0.0, [(59.4, 0.0), (60.2, 1.0)])
        self.mom_lean = KF(0.0, [(52.4, 0.0), (52.95, 11.0), (56.45, 11.0), (57.6, 7.0), (59.4, 7.0), (60.0, 11.0)])
        self.mom_sag = KF(0.0, [(59.4, 0.0), (60.0, 1.0)])
        self.turn = KF(0.0, [(56.45, 0.0), (57.6, 1.0)])
        self.dad_lean = KF(0.0, [(56.45, 0.0), (57.6, 7.0), (59.4, 7.0), (60.2, 0.0)])
        # la feuille : rotation autour du coin gauche, puis la chute
        self.note_rot = KF(-3.0, [(16.65, -3.0), (16.9, 13.0), (17.3, 7.0), (17.8, 10.0), (18.5, 9.0),
                                  (36.95, 9.0), (37.2, 21.0), (37.6, 14.0), (38.2, 18.0), (39.0, 17.0)])
        self.note_fall = (60.4, 61.3)
        # le texte des bulles (qui, texte, début, fin) : recalé sur la narration au rendu
        self.bubbles = [("mom", "Who woke you up?", 53.0, 54.19), ("baby", "BOUNCE!", 54.55, 54.98),
                        ("dad", "His first word...", 55.35, 56.39), ("baby", "BOUNCE!", 58.95, 59.38),
                        ("baby", "BOUNCE!", 61.15, 61.65)]
        self.rings = [(t, g, x, y) for (t, g, x, y) in self.P.hits]

    def set_narr(self, narr):
        who = {"mom": "mom", "b1": "baby", "dad": "dad", "b2": "baby", "b3": "baby"}
        out = []
        for n in narr:
            if n["key"] in who:
                txt = n["text"].upper() if who[n["key"]] == "baby" else n["text"]
                out.append((who[n["key"]], txt.replace("...", "…"), n["start"], n["end"]))
        if out:
            self.bubbles = out

    # -------- tétine et étoile
    def paci(self, t, P):
        """Position de la tétine (x, y, angle) ; sur le visage, en vol, au sol ou sur le matelas."""
        face = P(150, -52)
        if t < 25.85:
            return face + (0.0,)
        if t < 26.95:
            p = arc_point(face, (180.0, FL - 9), 25.85, 1.1, t)
            return p + ((t - 25.85) * 9.0,)
        if t < 27.4:
            return (180.0, FL - 9, 0.0)
        if t < 28.55:
            p = arc_point((180.0, FL - 9), face, 27.45, 1.1, t)
            return p + (-(t - 27.45) * 8.0,)
        if t < 41.3:
            return face + (0.0,)
        if t < 41.65:
            p = arc_point(P(150, -52), (690.0, MT - 10), 41.3, 0.35, t)
            return p + (1.5,)
        return (690.0, MT - 10, 1.5)

    def star(self, t, P):
        if t < Mobile.STAR_OFF:
            return None
        belly = P(70, -56)
        if t < 19.0:
            ph, om = self.P.mob.state(Mobile.STAR_OFF)
            x0 = HUB[0] + (62.0 + STRING * math.sin(0.75 * self.P.mob.spread(Mobile.STAR_OFF))) * math.cos(ph)
            p = arc_point((x0, HUB[1] + STRING * 0.8), belly, Mobile.STAR_OFF, 0.6, t)
            return p + ((t - 18.3) * 10,)
        if t < 41.3:
            return belly + (0.0,)
        if t < 41.65:
            p = arc_point(belly, (862.0, MT - 20), 41.3, 0.35, t)
            return p + (0.0,)
        return (862.0, MT - 20, 0.0)

    def note_state(self, t):
        """(cx, cy, angle en degrés)"""
        a0 = self.note_rot(t)
        if t < self.note_fall[0]:
            # pivot sur le coin haut-gauche
            px, py = NOTE_C[0] - NOTE_W / 2, NOTE_C[1] - NOTE_H / 2
            ar = math.radians(a0)
            dx, dy = NOTE_W / 2, NOTE_H / 2
            return (px + dx * math.cos(ar) - dy * math.sin(ar), py + dx * math.sin(ar) + dy * math.cos(ar), a0)
        u = clamp01((t - self.note_fall[0]) / (self.note_fall[1] - self.note_fall[0]))
        pts = [(NOTE_C[0], NOTE_C[1] + 40), (360, 600), (150, 800), (205, 1192)]
        # Bézier simple
        k = smooth(u)
        def bez(p, k):
            while len(p) > 1:
                p = [(lerp(p[i][0], p[i + 1][0], k), lerp(p[i][1], p[i + 1][1], k)) for i in range(len(p) - 1)]
            return p[0]
        x, y = bez(pts, k)
        ang = lerp(a0, -8.0, k) + 18 * math.sin(u * math.pi * 3) * (1 - u)
        return (x, y, ang)


# ------------------------------------------------------------------ dessin
def poly_round(pts, S):
    return [(x * S, y * S) for x, y in pts]


def capsule(dr, p0, p1, r, col, S):
    dr.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=col, width=max(1, int(2 * r * S)))
    for p in (p0, p1):
        dr.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)


def ell(dr, x, y, rx, ry, col, S, outline=None, w=0):
    dr.ellipse([(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S], fill=col,
               outline=outline, width=int(w * S) if w else 0)


def rect(dr, x0, y0, x1, y1, col, S, r=0):
    if r:
        dr.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=col)
    else:
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)


def star_pts(x, y, r, a=0.0, n=5, k=0.45):
    pts = []
    for i in range(2 * n):
        rr = r if i % 2 == 0 else r * k
        aa = a - math.pi / 2 + i * math.pi / n
        pts.append((x + rr * math.cos(aa), y + rr * math.sin(aa)))
    return pts


_NOTE_IMG = {}


def note_image(S):
    if S in _NOTE_IMG:
        return _NOTE_IMG[S]
    w, h = int(NOTE_W * S), int(NOTE_H * S)
    pad = int(30 * S)
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([pad, pad, pad + w, pad + h], fill=(236, 232, 218, 255))
    f1 = font(64 * S)
    f2 = font(46 * S)
    ink = (20, 20, 26, 255)
    d.text((pad + w / 2, pad + 0.24 * h), "DO NOT", fill=ink, anchor="mm", font=f1)
    d.text((pad + w / 2, pad + 0.52 * h), "WAKE HIM!", fill=ink, anchor="mm", font=f1)
    yy = pad + 0.67 * h
    d.line([pad + 0.12 * w, yy, pad + 0.88 * w, yy], fill=ink, width=int(5 * S))
    d.line([pad + 0.16 * w, yy + 10 * S, pad + 0.84 * w, yy + 10 * S], fill=ink, width=int(4 * S))
    d.text((pad + 0.62 * w, pad + 0.85 * h), "— Mom", fill=(40, 40, 60, 255), anchor="mm", font=f2)
    _NOTE_IMG[S] = (img, pad)
    return _NOTE_IMG[S]


class Sim:
    scene_top = 0.22

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.sc = Scene()
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.hit_times = [h[0] for h in self.sc.P.hits]
        self.hi = 0
        self.lines = [(53.0, "Who woke you up?", "mom"), (54.55, "Bounce!", "b1"),
                      (55.35, "His first word...", "dad"), (58.95, "Bounce!", "b2"), (61.15, "BOUNCE!", "b3")]
        self.replies = []

    def hero_mood(self):
        return "lose"

    def step(self, dt):
        evs = []
        while self.hi < len(self.hit_times) and self.hit_times[self.hi] <= self.t + 1e-9:
            evs.append(("hit", "h%d" % self.hi))
            self.hi += 1
        if self.t >= PAYOFF and not self.payoff:
            self.payoff = True
            evs.append(("payoff", "first word"))
        if self.t >= END - 1e-9:
            self.done = True
        self.t += dt
        return evs

    def snapshot(self):
        return self.t

    def hit_gain(self, t0):
        for (th, g, _x, _y) in self.sc.P.hits:
            if abs(th - t0) < 0.02:
                return g
        return 0.9

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        t = float(t)
        sc = self.sc
        img = dr._image
        # mur
        rect(dr, 0, CEIL, W, FL, WALL, S)
        rect(dr, 0, 0, W, CEIL, BG, S)
        dr.line([0, CEIL * S, W * S, CEIL * S], fill=WALL_D, width=int(6 * S))
        for k in range(40):                                   # petites étoiles du papier peint
            x = 40 + (k * 211) % 1000
            y = CEIL + 40 + (k * 137) % 1240
            dr.polygon(poly_round(star_pts(x, y, 7), S), fill=(36, 42, 78))
        # fenêtre
        x0, x1, y0, y1 = WIN
        rect(dr, x0 - 10, y0 - 10, x1 + 10, y1 + 10, WOOD_D, S)
        rect(dr, x0, y0, x1, y1, (14, 20, 46), S)
        ell(dr, x0 + 110, y0 + 70, 34, 34, (250, 236, 170), S)
        ell(dr, x0 + 126, y0 + 60, 30, 30, (14, 20, 46), S)
        for (sx_, sy_) in ((x0 + 40, y0 + 150), (x0 + 70, y0 + 40), (x0 + 140, y0 + 170)):
            dr.polygon(poly_round(star_pts(sx_, sy_, 7), S), fill=(220, 220, 255))
        dr.line([((x0 + x1) / 2) * S, y0 * S, ((x0 + x1) / 2) * S, y1 * S], fill=WOOD_D, width=int(6 * S))
        self.draw_light_wall(dr, t, S)
        self.draw_door(dr, t, S)
        self.draw_note(img, dr, t, S, falling=False)
        # le lit, au fond : barreaux et barre du fond
        dr.rectangle([POST_L[1] * S, 1000 * S, POST_R[0] * S, 1014 * S], fill=WOOD_D)
        for k in range(10):
            x = POST_L[1] + 22 + k * 42
            dr.line([x * S, 1014 * S, x * S, MT * S], fill=WOOD_D, width=int(7 * S))
        self.draw_mobile(dr, t, S)
        # plancher
        rect(dr, 0, FL, W, H, FLOOR_C, S)
        yb = FL + 26
        for k in range(9):
            dr.line([0, yb * S, W * S, yb * S], fill=FLOOR_L, width=int(3 * S))
            yb += 30 + 9 * k
        self.draw_light_floor(dr, t, S)
        bx, by, brx, bry = sc.P.ball(t)
        # tapis (creusé par la balle)
        self.draw_soft(dr, RUG[0], RUG[1], RUG[2], FL, RUG_C, RUG_D, bx, by, bry, S)
        # pieds du lit
        rect(dr, POST_L[0], POST_TOP, POST_L[1], FL, WOOD, S)
        rect(dr, POST_R[0], POST_TOP, POST_R[1], FL, WOOD, S)
        rect(dr, POST_L[1], 1300, POST_R[0], 1318, WOOD, S)
        # matelas
        self.draw_soft(dr, POST_L[1], POST_R[0], MT, 1300, MATT, (180, 184, 200), bx, by, bry, S)
        # boules des montants
        for (kx, ky) in (KNOB_L, KNOB_RR):
            ell(dr, kx, ky, KNOB_R, KNOB_R, WOOD, S)
        # tétine au sol (avant la balle)
        Pb, pose = sc.B.frame(t)
        # anneaux (derrière les acteurs)
        self.draw_rings(dr, t, S)
        # Bounce
        base.ball(dr, bx * S, by * S, brx * S) if abs(brx - bry) < 0.5 else self.draw_ball(dr, bx, by, brx, bry, S)
        # le bébé
        self.draw_baby(dr, t, S, Pb, pose, bx, by)
        # Z
        for (zx, zy, fs, a) in sc.Z.visible(t, Pb):
            if a <= 0.02:
                continue
            col = mix(WALL, ZCOL, a)
            dr.text((zx * S, zy * S), "Z", fill=col, anchor="mm", font=font(fs * S))
        # tétine, étoile
        px_, py_, pa = sc.paci(t, Pb)
        self.draw_paci(dr, px_, py_, pa, S)
        st = sc.star(t, Pb)
        if st:
            dr.polygon(poly_round(star_pts(st[0], st[1], 30, st[2]), S), fill=TOYS[0][0])
        # parents
        self.draw_parents(dr, t, S)
        self.draw_note(img, dr, t, S, falling=True)
        self.draw_bubbles(dr, t, S)

    def draw_ball(self, dr, x, y, rx, ry, S):
        """Bounce écrasé : on le dessine avec base.ball sur une couche, puis on l'étire."""
        r = max(rx, ry)
        size = int(2 * r * 1.7 * S) + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        base.ball(ld, size / 2, size / 2, R * S)
        base.HERO["pos"] = None
        nw, nh = max(2, int(size * rx / R)), max(2, int(size * ry / R))
        layer = layer.resize((nw, nh), Image.BILINEAR)
        img = dr._image
        img.paste(layer, (int(x * S - nw / 2), int(y * S - nh / 2)), layer)
        if base.HERO["pos"] is None:
            base.HERO["pos"] = (x * S, y * S)

    def draw_soft(self, dr, x0, x1, top, bottom, col, col_d, bx, by, bry, S):
        pts = []
        n = 48
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = top
            dxb = x - bx
            if abs(dxb) < R * 1.25:
                circ_y = by + math.sqrt(max(0.0, (R * 1.05) ** 2 - dxb * dxb)) if abs(dxb) < R * 1.05 else -1e9
                y = max(y, min(bottom - 6, circ_y))
                # bord adouci
                if abs(dxb) >= R * 1.05:
                    pass
            pts.append((x, y))
        pts = pts + [(x1, bottom), (x0, bottom)]
        dr.polygon(poly_round(pts, S), fill=col)
        dr.line(poly_round(pts[:n + 1], S), fill=col_d, width=int(4 * S))

    def draw_rings(self, dr, t, S):
        for (t0, g, x, y) in self.sc.rings:
            u = t - t0
            if u < 0 or u > 1.2:
                continue
            rmax = 220 + 1050 * g
            r = 30 + 1700 * u
            if r > rmax:
                continue
            k = 1 - r / rmax
            inten = k * (0.35 + 0.65 * min(1.0, g))
            col = mix(WALL, (246, 246, 255), inten)
            w = (4 + 9 * min(1.3, g)) * (0.5 + 0.5 * k)
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=col, width=max(1, int(w * S)))

    def draw_door(self, dr, t, S):
        x0, x1, y0, y1 = DOOR
        o = self.sc.door_o(t)
        h = self.sc.hall(t)
        rect(dr, x0 - 10, y0 - 10, x1 + 10, y1, WOOD_D, S)
        light = mix((30, 26, 30), WARM, h)
        rect(dr, x0, y0, x1, y1, light, S)
        # le battant : couvre la baie depuis les gonds (à gauche)
        wpan = (x1 - x0) * (1 - o)
        if wpan > 1:
            rect(dr, x0, y0, x0 + wpan, y1, (78, 56, 46), S)
            rect(dr, x0 + 14, y0 + 18, x0 + wpan - 14, y0 + 190, (88, 64, 52), S) if wpan > 40 else None
            rect(dr, x0 + 14, y0 + 220, x0 + wpan - 14, y1 - 24, (88, 64, 52), S) if wpan > 40 else None
            # poignée
            hk = self.sc.handle(t)
            hx, hy = x0 + wpan - 22, y0 + 230
            ang = math.radians(28 * hk)
            capsule(dr, (hx, hy), (hx - 26 * math.cos(ang), hy + 26 * math.sin(ang)), 5, (200, 190, 150), S)
        # la ligne sous la porte (fermée)
        if o < 0.02:
            line = mix((20, 18, 22), WARM, h)
            rect(dr, x0 + 4, y1 - 12, x1 - 4, y1, line, S)
            for (ta, tb, tc, td) in self.sc.feet:
                k = clamp01((t - ta) / (tb - ta)) * (1 - clamp01((t - tc) / (td - tc)))
                if k > 0:
                    for fx in (x0 + 52, x0 + 108):
                        off = (1 - k) * 60
                        rect(dr, fx - 20 + off, y1 - 12, fx + 20 + off, y1, (20, 18, 22), S)
        # silhouettes dans l'encadrement
        pin = self.sc.par_in(t)
        if o > 0.5 and pin < 0.02:
            self.parent_shape(dr, 140, FL, 0.78, SIL, S, kind="mom")
            self.parent_shape(dr, 85, FL, 0.78, SIL, S, kind="dad")

    def draw_light_floor(self, dr, t, S):
        o = self.sc.door_o(t)
        h = self.sc.hall(t)
        if o < 0.02 or h < 0.05:
            return
        x0, x1 = DOOR[0], DOOR[1]
        open_w = (x1 - x0) * o
        xa = x1 - open_w
        reach = 120 + 420 * min(1.0, o * 1.4)
        col = mix(FLOOR_C, (150, 120, 80), 0.55 * h)
        dr.polygon(poly_round([(xa, FL), (x1, FL), (x1 + reach, 1560), (xa + reach * 0.1, 1560)], S), fill=col)

    def draw_mobile(self, dr, t, S):
        # bras
        dr.line([(KNOB_RR[0]) * S, POST_TOP * S, KNOB_RR[0] * S, (ARM_Y + 20) * S], fill=(200, 200, 214), width=int(7 * S))
        dr.line([KNOB_RR[0] * S, ARM_Y * S, HUB[0] * S, ARM_Y * S], fill=(200, 200, 214), width=int(7 * S))
        dr.line([HUB[0] * S, ARM_Y * S, HUB[0] * S, HUB[1] * S], fill=(200, 200, 214), width=int(5 * S))
        ell(dr, HUB[0], HUB[1], 18, 8, (220, 220, 232), S)
        toys = sorted(self.sc.P.mob.toys(t), key=lambda a: a[3])
        for (k, x, y, z, col, shape, xa) in toys:
            c = mix(WALL, col, 0.72 + 0.28 * (z + 1) / 2)
            dr.line([xa * S, HUB[1] * S, x * S, (y - TOY_R) * S], fill=(170, 170, 190), width=int(2 * S))
            rr = TOY_R * (0.9 + 0.1 * z)
            if shape == "star":
                dr.polygon(poly_round(star_pts(x, y, rr + 4), S), fill=c)
            elif shape == "moon":
                ell(dr, x, y, rr, rr, c, S)
                ell(dr, x + rr * 0.45, y - rr * 0.25, rr * 0.8, rr * 0.8, WALL, S)
            else:
                ell(dr, x - rr * 0.45, y + 4, rr * 0.6, rr * 0.55, c, S)
                ell(dr, x + rr * 0.45, y + 4, rr * 0.6, rr * 0.55, c, S)
                ell(dr, x, y - 4, rr * 0.7, rr * 0.65, c, S)

    def draw_paci(self, dr, x, y, a, S):
        ca, sa = math.cos(a), math.sin(a)
        def Pp(u, v):
            return (x + u * ca - v * sa, y + u * sa + v * ca)
        shield = [Pp(19 * math.cos(k * math.pi / 8), 8 * math.sin(k * math.pi / 8)) for k in range(16)]
        dr.polygon(poly_round(shield, S), fill=PACI)
        cx, cy = Pp(0, -15)
        dr.ellipse([(cx - 11) * S, (cy - 11) * S, (cx + 11) * S, (cy + 11) * S], outline=PACI, width=int(5 * S))

    def draw_baby(self, dr, t, S, P, p, bx, by):
        sw = 1.0 + 0.35 * p["swell"]
        breath = 1.0 + 0.035 * math.sin(2 * math.pi * t / 2.3)
        hw = 32 * sw * breath
        # jambe levée (le bout de la couverture)
        if p["leg"] > 0.01:
            a = math.radians(70 * p["leg"])
            f0 = P(14, 0)
            q = P(-30 * math.cos(a), -40 * math.sin(a))
            capsule(dr, f0, q, 17 * BS, SWAD_D, S)
        # corps
        body = []
        for k in range(24):
            ang = 2 * math.pi * k / 24
            u = 62 + 60 * sw * math.cos(ang)
            v = hw * math.sin(ang)
            body.append(P(u, v))
        dr.polygon(poly_round(body, S), fill=SWAD)
        # plis de la couverture
        for uu in (40, 78):
            dr.line(poly_round([P(uu, -hw * 0.8), P(uu + 8, 0), P(uu, hw * 0.8)], S), fill=SWAD_D, width=int(3 * S))
        # bras
        arm = p["arm"]
        up = p["up"]
        sh = P(108, -hw * 0.6)
        if p["hug"] > 0.05:
            h = p["hug"]
            for (s0, dy) in ((sh, -22), (P(102, hw * 0.2), 22)):
                tx, ty = bx, by + dy
                d = math.hypot(tx - s0[0], ty - s0[1]) + 1e-6
                L = h * min(d - R + 10, 80.0)
                capsule(dr, s0, (s0[0] + (tx - s0[0]) / d * L, s0[1] + (ty - s0[1]) / d * L), 10 * BS, SWAD_D, S)
        elif up > 0.02:
            th = p["th"]
            for side in (-1, 1):
                s0 = P(112, side * hw * 0.7)
                a = th - math.pi / 2 + side * math.radians(28) * up - (1 - up) * side * 0.0
                ang = math.radians(-90 + side * 35 * up) if p["sit"] > 0.5 else -math.pi / 2
                ex = s0[0] + side * 26 * up
                ey = s0[1] - 62 * up
                capsule(dr, s0, (ex + side * 14, ey), 10 * BS, SWAD_D, S)
        elif arm > 0.02:
            wave_ = 0.25 * math.sin(t * 4.0) if 13.8 < t < 15.0 else 0.0
            a = math.radians(-90 - 30 * arm) + wave_
            e = (sh[0] + 64 * arm * math.cos(a), sh[1] + 64 * arm * math.sin(a))
            capsule(dr, sh, e, 10 * BS, SWAD_D, S)
        # tête
        hl = p["head"]
        neck = P(125, 0)
        hc = P(152 + 0 * hl, -6 - 26 * hl)
        rh = 33 * (1.0 + 0.12 * p["swell"])
        rhs = rh * BS
        ell(dr, hc[0], hc[1], rhs, rhs, SKIN, S)
        # la boucle, sur le dessus (dans l'axe du dos)
        tip = P(152 + rh + 2, -6 - 26 * hl)
        c2 = P(152 + rh + 12, -14 - 26 * hl)
        dr.line(poly_round([tip, c2, P(152 + rh + 6, -22 - 26 * hl)], S), fill=SKIN_D, width=int(5 * S))
        self._head = hc

    def parent_shape(self, dr, fx, fy, k, col, S, kind="mom", lean=0.0, sag=0.0, sit=0.0, turn=0.0):
        bw, bh, hr = (110, 380, 45) if kind == "mom" else (130, 420, 48)
        bw, bh, hr = bw * k, bh * k, hr * k
        bh = bh * (1 - 0.06 * sag) * (1 - 0.5 * sit)
        bw = bw * (1 + 0.15 * sit) * (1 - 0.15 * turn)
        a = math.radians(lean)
        ca, sa = math.cos(a), math.sin(a)
        def Pp(u, v):           # u : vers le haut depuis les pieds, v : à droite
            return (fx + v * ca + u * sa, fy - u * ca + v * sa)
        pts = []
        for i in range(9):
            ang = math.pi * i / 8
            pts.append(Pp(bh - bw / 2 + (bw / 2) * math.sin(ang), -(bw / 2) * math.cos(ang)))
        pts = [Pp(0, -bw / 2)] + pts + [Pp(0, bw / 2)]
        dr.polygon(poly_round(pts, S), fill=col)
        hc = Pp(bh + hr * (1.05 - 0.25 * sag), 0)
        ell(dr, hc[0], hc[1], hr, hr, col, S)
        # bras
        dark = dim(col, 0.8) if col != SIL else SIL
        for side in (-1, 1):
            s0 = Pp(bh - bw * 0.55, side * bw * 0.5)
            s1 = Pp(bh - bw * 0.55 - 150 * k * (1 - 0.4 * sit), side * (bw * 0.55 + 6 * sag))
            capsule(dr, s0, s1, 13 * k, dark, S)
        return hc

    def draw_parents(self, dr, t, S):
        pin = self.par_in(t) if hasattr(self, "par_in") else self.sc.par_in(t)
        if pin <= 0.0:
            return
        sc = self.sc
        k = lerp(0.78, 1.0, pin)
        colm = mix(SIL, MOM, clamp01((pin - 0.3) / 0.6))
        cold = mix(SIL, DAD, clamp01((pin - 0.3) / 0.6))
        dad_x = lerp(85, 130, pin) + 75 * sc.dad_sit(t)
        mom_x = lerp(140, 270, pin)
        self.dad_head = self.parent_shape(dr, dad_x, FL, k, cold, S, "dad", lean=sc.dad_lean(t), sag=sc.dad_sag(t),
                                          sit=sc.dad_sit(t), turn=sc.turn(t))
        self.mom_head = self.parent_shape(dr, mom_x, FL, k, colm, S, "mom", lean=sc.mom_lean(t), sag=sc.mom_sag(t),
                                          turn=sc.turn(t))

    def par_in(self, t):
        return self.sc.par_in(t)

    def draw_note(self, img, dr, t, S, falling):
        sc = self.sc
        is_fall = t >= sc.note_fall[0]
        if is_fall != falling:
            return
        nimg, pad = note_image(S)
        cx, cy, ang = sc.note_state(t)
        if is_fall:
            # en tombant, la feuille se plie en deux et se pose sur la tête du père
            u = clamp01((t - sc.note_fall[0]) / (sc.note_fall[1] - sc.note_fall[0]))
            k = lerp(1.0, 0.56, smooth(u))
            nimg = nimg.resize((max(2, int(nimg.width * k)), max(2, int(nimg.height * k))), Image.BILINEAR)
        rot = nimg.rotate(-ang, resample=Image.BICUBIC, expand=True)
        img.paste(rot, (int(cx * S - rot.width / 2), int(cy * S - rot.height / 2)), rot)
        if not is_fall:
            # les scotchs : gauche toujours, droit jusqu'à 16,6
            ar = math.radians(ang)
            def corner(dx, dy):
                return (cx + dx * math.cos(ar) - dy * math.sin(ar), cy + dx * math.sin(ar) + dy * math.cos(ar))
            tapes = [corner(-NOTE_W / 2 + 6, -NOTE_H / 2 + 4)]
            if t < 16.65:
                tapes.append(corner(NOTE_W / 2 - 6, -NOTE_H / 2 + 4))
            for (x, y) in tapes:
                dr.polygon(poly_round([(x - 26, y - 8), (x + 26, y - 14), (x + 28, y + 6), (x - 24, y + 12)], S),
                           fill=(200, 196, 170))

    def draw_bubbles(self, dr, t, S):
        for (who, text, a, b) in self.sc.bubbles:
            if not (a - 0.05 <= t <= b + 0.45):
                continue
            k = clamp01((t - a + 0.05) / 0.12)
            if who == "baby":
                hc = getattr(self, "_head", (760, 1100))
                cx, cy, fs = min(850.0, hc[0] + 40), hc[1] - 112, 58
                tail = (hc[0] + 6, hc[1] - 40)
            elif who == "mom":
                cx, cy, fs = 270.0, 900.0, 56
                tail = (335, 975)
            else:
                cx, cy, fs = 240.0, 810.0, 56
                hd = getattr(self, "dad_head", (150, 960))
                tail = (hd[0] + 10, hd[1] - 50)
            f = font(fs * S * (0.7 + 0.3 * k))
            tw = f.getbbox(text)[2] - f.getbbox(text)[0]
            bw, bh = tw / S + 56, fs * 1.6 * (0.7 + 0.3 * k)
            x0 = max(16.0, min(cx - bw / 2, 920 - bw))
            y0 = cy - bh / 2
            dr.polygon(poly_round([(cx - 22, y0 + bh - 2), (cx + 18, y0 + bh - 2), tail], S), fill=(250, 250, 252))
            rect(dr, x0, y0, x0 + bw, y0 + bh, (250, 250, 252), S, r=bh / 2.4)
            dr.text(((x0 + bw / 2) * S, (y0 + bh / 2) * S), text, fill=(18, 18, 24), anchor="mm", font=f)

    def draw_light_wall(self, dr, t, S):
        """La lumière du couloir quand la porte s'ouvre : un pinceau chaud sur le mur, jusqu'au lit."""
        o = self.sc.door_o(t)
        h = self.sc.hall(t)
        if o < 0.02 or h < 0.05:
            return
        x1 = DOOR[1]
        xa = x1 - (DOOR[1] - DOOR[0]) * o
        spread = min(1.0, o * 1.3)
        col = mix(WALL, (120, 100, 90), h * (0.5 + 0.5 * spread))
        dr.polygon(poly_round([(x1, DOOR[2] + 60), (930, 1130 - 60 * spread), (930, FL), (x1, FL)], S), fill=col)


# ------------------------------------------------------------------ audio, rendu
DEFAULTS = {
    "hook_text_s": 2.6, "hook_top": 0.085, "hook_font_size": 92,
    "narrator_voice": "am_michael", "narrator_length": 1.0, "narr_gap_s": 0.3,
    "sub_y": 1.5, "sub_font_size": 10,
    "watermark_y": 0.95, "end_hold_s": 0.02, "narr_tail_s": 0.0,
    "min_duration_s": 30.0, "max_duration_s": 70.0,
    "show_counter": False, "hook_voice": True,
}
LINE_GAIN = {"mom": 1.0, "b1": 0.9, "dad": 1.0, "b2": 0.95, "b3": 1.1}


def render_audio(sim, events, total_dur, cfg, path, narr):
    buf = np.zeros(int((total_dur + 2.0) * SR))
    rng = np.random.default_rng(int(cfg["seed"]))
    name = base.hero_word(cfg["hero_name"], cfg)
    react = base.hero_word(cfg["hero_lose"], cfg)
    said = 0
    if name is None:
        print(f"[{cfg['name']}] avertissement : aucune voix pour Bounce, rebonds muets", file=sys.stderr)
    else:
        words = base.place_words(events, total_dur, cfg, sim.payoff_t, "lose", narr, (),
                                 name_len=len(name) / SR, react_len=len(react) / SR if react is not None else 0.8)
        for (t0, kind, _d, tag) in words:
            if kind == "react":
                if react is not None:
                    ak.add(buf, react, t0, gain=1.0)
                continue
            g = sim.hit_gain(t0)
            gg = max(0.1, min(1.3, g)) ** 0.9 * 0.95
            ak.add(buf, base.pitch(name, 1.0 + rng.uniform(-0.03, 0.03)), t0, gain=gg)
            said += 1
    for n in narr:
        ak.add(buf, n["audio"], n["start"], gain=LINE_GAIN.get(n["key"], 1.0))
    v = cfg.get("_hook_voice")
    if v is not None:
        n = min(len(v), len(buf))
        duck = np.ones(len(buf))
        duck[:n] = 0.42
        m = min(int(0.3 * SR), len(buf) - n)
        duck[n:n + m] = np.linspace(0.42, 1.0, m)
        buf *= duck
        ak.add(buf, v, 0.15, gain=1.0)
    ak.write_wav(buf, path)
    return {"hero": cfg["hero_name"], "said": said}


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    theme = sys.modules[__name__]
    cfg = base.load_config(argv[0], DEFAULTS)
    states, events, dur, sim = base.simulate(theme, cfg)
    narr, replies = base.build_narration(sim, cfg)
    sim.sc.set_narr(narr)
    cfg["_sim"] = sim
    summary = {"name": cfg["name"], "duration_s": round(dur, 2), "payoff": bool(sim.payoff),
               "payoff_t": round(sim.payoff_t or -1, 2),
               "hits": sum(1 for e in events if e[1] == "hit"),
               "narration": [{"t": round(n["start"], 2), "e": round(n["end"], 2), "text": n["text"]} for n in narr]}
    name = base.hero_word(cfg["hero_name"], cfg)
    react = base.hero_word(cfg["hero_lose"], cfg)
    words = base.place_words(events, dur, cfg, sim.payoff_t, "lose", narr, (), name_len=len(name) / SR,
                             react_len=len(react) / SR)
    said = {round(w[0], 3) for w in words}
    hits = [round(e[0], 3) for e in events if e[1] == "hit"]
    summary["muets"] = [h for h in hits if h not in said]
    summary["react"] = [round(w[0], 2) for w in words if w[1] == "react"]
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
