"""
Prototype « Detonate » : le personnage d'un fan (Detonate, une balle orange, furieuse, dans une coque
orange foncé faite de huit segments) et Bounce, sur un grand tapis de trampoline qu'ils partagent.
Chaque fois que Bounce retombe sur le tapis (« Bounce »), le tapis se creuse et fait sauter Detonate
malgré lui ; chaque saut forcé lui arrache un segment de coque. Les segments qui restent sont le compte
à rebours. Detonate prévient (« Detonate… »), de plus en plus fort ; deux segments tiennent de justesse ;
Bounce essaie de rebondir tout doucement, et n'y arrive pas. Le dernier segment tombe : Detonate gonfle,
rougit, tremble… et éclate en confettis, entier et toujours furieux ; une coque neuve repousse, Bounce,
couvert de confettis, rebondit, et le premier segment de la coque neuve saute.

Detonate ne dit que son nom (banque de voix hors dépôt, cfg["voice_bank"]), sans sous-titre ; ses
répliques sont placées dans les vols de Bounce, jamais sur un contact. Bounce ne s'arrête jamais et
n'est dessiné que par base.ball(). Une seule gravité pour tout (Bounce, Detonate, segments, confettis,
ces derniers freinés par l'air). Rien n'est ajouté au moteur.

    python3 src/stories/detonate.py configs/<name>.json [--simulate]
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

# ------------------------------------------------------------------ la voix de Detonate
WHO = "Detonate"
LINES = {"grogne": "grogne.wav", "warn": "warn.wav", "furax": "furax.wav", "hurle": "hurle.wav",
         "gonfle": "gonfle.wav", "lent": "lent.wav", "boude": "boude.wav", "fin": "fin.wav"}
GAIN = {"grogne": 0.75, "warn": 0.9, "furax": 1.05, "hurle": 1.2, "gonfle": 1.05, "lent": 1.25,
        "boude": 0.8, "fin": 1.2}
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
        x *= 0.2 * GAIN.get(key, 1.0)
        BANK[WHO + " " + key] = x
        hop = SR // 60
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        ENV[WHO + " " + key] = e / (e.max() + 1e-9)


def detonate_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = detonate_say
base.subtitle_at = lambda narr, t, n_words: None          # aucun sous-titre

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr                                         # la bouche de Detonate suit sa voix
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
G = 1400.0                       # la seule gravité de la scène
RB = 100.0                       # Bounce
RD = 105.0                       # Detonate, coque comprise (comme Bounce : disque R, halo 1,6 R)
RI = 0.76 * RD                   # le disque orange, sous la coque
DX = 800.0                       # Detonate, assis sur le tapis à droite
MAT_Y = 1330.0                   # le tapis au repos
X0, X1 = 60.0, 1020.0            # ses bords (les ressorts)
LEG_Y = 1610.0                   # le sol de la salle
CONTACT = 0.16                   # durée d'un contact de Bounce avec le tapis
PILE_R, PILE_L = 975.0, 615.0    # là où s'empilent les segments tombés
PIECE_STEP = 24.0
PRE, PRE_D = 0.12, 36.0          # un segment sort d'abord de sa place, tout droit

D_ORANGE, D_SHELL, D_HALO = (255, 106, 0), (190, 72, 6), (44, 20, 8)
D_RED, D_SHELL_HI = (232, 34, 26), (196, 86, 18)
INK = (16, 14, 20)
WALL, FLOOR_COL = (16, 16, 26), (24, 20, 26)
MAT_COL, MAT_EDGE = (36, 36, 50), (96, 98, 130)
PAD, FRAME = (44, 92, 170), (70, 74, 90)
CONF_COLS = [(255, 80, 170), (255, 220, 60), (70, 220, 255), (120, 240, 110), (250, 250, 250),
             (255, 150, 40), (180, 110, 255)]

# les 8 segments, par angle (écran : 90° = en bas) ; l'ordre de chute, et où chacun s'empile
SEG_ANG = [90 + 45 * k for k in range(8)]          # k=0 bas, 2 gauche, 4 haut, 6 droite
FALL_ORDER = [4, 7, 5, 1, 6, 3, 2, 0]
PILE_OF = {4: "L", 7: "R", 5: "R", 1: "L", 6: "R", 3: "L", 2: "L", 0: "R"}


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def shape(x, xc):
    """Le creux du tapis sous une charge en xc : une tente entre les deux bords, adoucie."""
    if x <= X0 or x >= X1:
        return 0.0
    v = (x - X0) / (xc - X0) if x < xc else (X1 - x) / (X1 - xc)
    return max(0.0, min(1.0, v)) ** 0.7


def pulse(s):
    """Réponse du tapis à un choc : il descend pendant le contact, puis remonte en oscillant."""
    if s < 0:
        return 0.0
    if s < CONTACT:
        return math.sin(math.pi * s / CONTACT)
    u = s - CONTACT
    if u > 1.6:
        return 0.0
    return -0.55 * math.exp(-u / 0.28) * math.sin(math.pi * u / 0.2)


def ballistic(t, t0, x0, y0, t1, x1, y1):
    T = max(1e-6, t1 - t0)
    s = t - t0
    vy = (y1 - y0) / T - 0.5 * G * T
    return lerp(x0, x1, s / T), y0 + vy * s + 0.5 * G * s * s


# ------------------------------------------------------------------ le plan
# Bounce : (écart depuis le contact précédent, x, genre, réplique de Detonate dans le vol qui suit)
#   n : contact ordinaire ; Detonate tangue sur le tapis
#   J : retombée forte, Detonate est projeté et perd un segment en retombant
#   F : petit rebond, petit saut de Detonate, un segment se fend et tient (fausse alerte)
#   P : Detonate n'a plus de coque, chaque retombée de Bounce le fait gonfler
#   X : le petit rebond de trop : Detonate éclate (en confettis)
PLAN = [
    (0.97, 240, "n", None),
    (1.30, 300, "J", None),
    (1.00, 250, "n", None),
    (1.00, 320, "n", "grogne"),
    (2.20, 270, "J", None),
    (1.00, 330, "n", None),
    (1.05, 260, "n", None),
    (0.95, 290, "n", None),
    (0.92, 240, "n", None),
    (0.90, 200, "F", None),
    (0.90, 185, "n", None),
    (1.10, 230, "n", "warn"),
    (2.20, 300, "J", None),
    (1.00, 260, "n", None),
    (1.15, 330, "n", None),
    (1.30, 280, "J", None),
    (1.00, 330, "n", None),
    (1.00, 260, "n", "furax"),
    (2.20, 300, "J", None),
    (1.00, 250, "n", None),
    (1.00, 320, "n", None),
    (0.95, 260, "n", None),
    (0.92, 215, "n", None),
    (0.90, 180, "n", None),
    (0.90, 165, "F", None),
    (0.90, 170, "n", None),
    (0.95, 200, "n", None),
    (1.10, 260, "n", "hurle"),
    (2.20, 310, "J", None),
    (1.00, 260, "n", None),
    (1.05, 330, "n", None),
    (1.60, 280, "J", None),
    (1.00, 320, "n", None),
    (1.10, 260, "n", None),
    (1.90, 300, "J", None),          # le dernier segment, celui du dessous
    (1.00, 260, "n", None),
    (1.00, 320, "P", None),
    (1.00, 270, "P", "gonfle"),
    (2.45, 300, "P", None),
    (0.95, 245, "P", None),
    (0.95, 205, "P", "lent"),
    (2.45, 225, "P", None),
    (0.92, 190, "n", None),
    (0.90, 172, "X", None),
    (0.90, 180, "n", None),
    (1.00, 240, "n", None),
    (1.00, 300, "n", "boude"),
    (2.20, 280, "J", None),
    (1.00, 330, "n", "fin"),
    (2.00, 260, "n", None),
]
D_FLIGHT = [1.25, 1.3, 1.35, 1.4, 1.45, 1.5, 1.55, 1.65, 1.3]     # les sauts forcés, de plus en plus hauts
PUMPS = [1.10, 1.22, 1.38, 1.50, 1.62, 1.72]                  # le gonflement, retombée après retombée
POP_DELAY = 0.34                                               # l'onde du tapis met ce temps à l'atteindre


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.rng = np.random.default_rng(int(cfg["seed"]) + 11)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        nm = base.hero_word(cfg["hero_name"], cfg)
        self.name_len = len(nm) / SR if nm is not None else 0.78
        dlen = {k: len(BANK[WHO + " " + k]) / SR for k in LINES}

        # ---- Bounce : ses contacts avec le tapis
        self.touch = []               # (t, x, genre)
        t = 0.0
        L = []
        for gap, x, kind, line in PLAN:
            t += gap
            self.touch.append((t, float(x), kind))
            if line:
                L.append((t + self.name_len + 0.14, line, t))
        self.lines = [(tl, WHO + " " + k, f"d{i}") for i, (tl, k, _) in enumerate(L)]
        self.line_plan = [(tl, k, dlen[k], tc) for (tl, k, tc) in L]
        self.hits = [(tc, "tapis") for (tc, _, _) in self.touch]
        self.hi = 0

        # ---- les chocs sur le tapis : (t, x, amplitude)
        self.imp = []
        prev = None
        for (tc, x, kind) in self.touch:
            T = (tc - prev - CONTACT) if prev is not None else 0.97
            v = G * T / 2
            self.imp.append((tc, x, min(95.0, 0.052 * v * 1.3)))
            prev = tc

        # ---- Detonate : ses sauts forcés, les segments
        self.dflights = []            # (t_dep, t_arr, genre)
        self.seg_fall = {}            # k -> (t_depart, genre "land"/"left")
        self.cracks = []              # (k, t0, t1, fort)
        self.pumps = []               # (t, niveau)
        ji, fi, pi = 0, 0, 0
        n_fallen = 0
        self.t_s8 = None
        self.t_pop = None
        self.regrow = []
        for (tc, x, kind) in self.touch:
            if kind == "J":
                fd = D_FLIGHT[min(ji, len(D_FLIGHT) - 1)]
                t0 = tc + 0.22
                self.dflights.append((t0, t0 + fd, "J"))
                self.imp.append((t0 + fd, DX, 26.0 + 14.0 * fd))
                if self.t_pop is None:
                    k = FALL_ORDER[n_fallen]
                    if k == 0:                                   # celui du dessous reste sur le tapis
                        self.seg_fall[k] = (t0 + 0.07, "left")
                        self.t_s8 = t0 + fd
                    else:
                        self.seg_fall[k] = (t0 + fd, "land")
                    n_fallen += 1
                else:                                            # la coque neuve : ça recommence
                    self.t_again = t0 + fd
                ji += 1
            elif kind == "F":
                fd = 0.5 if fi == 0 else 0.42
                t0 = tc + 0.2
                self.dflights.append((t0, t0 + fd, "F"))
                self.imp.append((t0 + fd, DX, 18.0))
                k = FALL_ORDER[n_fallen]
                self.cracks.append((k, t0 + fd, fi == 1))
                fi += 1
            elif kind == "P":
                self.pumps.append((tc + 0.18, PUMPS[min(pi, len(PUMPS) - 1)]))
                pi += 1
            elif kind == "X":
                self.t_pop = tc + POP_DELAY
                self.regrow = [self.t_pop + 0.55 + 0.19 * i for i in range(8)]
        self.payoff_at = self.t_pop
        last = self.touch[-1][0]
        self.end_s = last + self.name_len + 0.45

        # ---- les segments tombés : trajectoires
        self.pieces = []              # dict(k, t0, t1, p0, p1, r0, r1, pile)
        count = {"R": 0, "L": 0}
        for k in FALL_ORDER:
            if k not in self.seg_fall:
                continue
            t0, how = self.seg_fall[k]
            side = PILE_OF[k]
            n = count[side]; count[side] += 1
            px = PILE_R if side == "R" else PILE_L
            px += 8.0 * n * (1 if side == "R" else -1)       # la pile penche vers l'extérieur
            a = math.radians(SEG_ANG[k])
            rc = 0.5 * (RD + RI)
            if how == "left":
                p0 = (DX, MAT_Y + 4 - 0.5 * (RD - RI))
                dr0 = (1.0, 0.0)
            else:
                t0 += CONTACT / 2                                  # au fond du creux, la coque lâche
                self.seg_fall[k] = (t0, how)
                ddx, ddy = self.det_at(t0)
                p0 = (ddx + rc * math.cos(a), ddy + rc * math.sin(a))
                dr0 = (math.cos(a), math.sin(a))
                if math.sin(a) > 0.3:                              # ceux du bas sortent à l'horizontale
                    dr0 = (1.0 if math.cos(a) > 0 else -1.0, 0.0)
            r0 = math.radians(SEG_ANG[k] + 90)
            r1 = 0.08 * (1 if n % 2 else -1)
            piece = {"k": k, "t0": t0, "p0": p0, "dir": dr0, "x1": px, "n": n, "ride": how == "land",
                     "off": (rc * math.cos(a), rc * math.sin(a)),
                     "r0": r0, "r1": r1 + (2 * math.pi if r0 > math.pi else 0.0)}
            piece["t1"] = t0 + self._best_flight(piece, how)
            self.pieces.append(piece)

        if hasattr(self, "t_again"):                               # le premier segment de la coque neuve
            k = FALL_ORDER[0]
            a = math.radians(SEG_ANG[k])
            rc = 0.5 * (RD + RI)
            self.again_piece = {"k": k, "t0": self.t_again, "t1": self.t_again + 0.85,
                                "p0": (DX + rc * math.cos(a), MAT_Y - RD + rc * math.sin(a)), "x1": PILE_R + 5,
                                "n": 0, "r0": math.radians(SEG_ANG[k] + 90), "r1": 2 * math.pi + 0.06}
        else:
            self.again_piece = None

        # ---- les confettis (simulés pas à pas après l'éclatement)
        self.conf = None
        self.conf_on_b_cool = None
        self.next_touch_i = 0

    def _best_flight(self, p, how):
        """La durée de vol d'un segment qui le fait sortir de sa place sans jamais toucher Detonate."""
        best, best_T = -1e9, 0.8
        for T in [0.45 + 0.05 * i for i in range(14)]:
            p["t1"] = p["t0"] + T
            worst = 1e9
            for j in range(1, 41):
                tt = p["t0"] + T * j / 40
                cx, cy = self.det_at(tt)
                px, py, rot = self.piece_pos(p, tt, still=True)
                pts = self.seg_poly(px, py, RI - 1, RD, -math.pi / 2, math.radians(19.0), 1, rot=rot)
                dmin = min(math.hypot(u - cx, v - cy) for u, v in pts)
                need = RI * self.swell(tt) if (tt - p["t0"] < PRE or how == "left") else RD + 3
                worst = min(worst, dmin - need)
            score = worst * 100 - T if worst < 0 else -abs(T - 0.75)
            if score > best:
                best, best_T = score, T
        return best_T

    # ---------------------------------------------------------------- le tapis
    def d_on_mat(self, t):
        """1 quand Detonate pèse sur le tapis, 0 en l'air (avec une petite rampe)."""
        for (a, b, _) in self.dflights:
            if a - 0.05 <= t <= b:
                if t < a:
                    return (a - t) / 0.05
                return 0.0
        return 1.0

    def dip(self, x, t):
        d = 0.0
        for (te, xc, A) in self.imp:
            s = t - te
            if 0 <= s < 1.8:
                d += A * shape(x, xc) * pulse(s)
        d += 16.0 * self.d_on_mat(t) * shape(x, DX)
        return d

    def mat_y(self, x, t):
        return MAT_Y + self.dip(x, t)

    # ---------------------------------------------------------------- Bounce
    def bounce_at(self, t):
        T = self.touch
        if t < T[0][0]:
            t1, x1, _ = T[0]
            y1 = self.mat_y(x1, t1) - RB
            s = t1 - t
            return x1 - 40 * s, y1 - 0.5 * G * s * s
        for i, (tc, x, _) in enumerate(T):
            if tc <= t <= tc + CONTACT:
                return x, self.mat_y(x, t) - RB
            if i + 1 < len(T) and tc + CONTACT < t < T[i + 1][0]:
                t1, x1, _ = T[i + 1]
                a = tc + CONTACT
                y0 = self.mat_y(x, a) - RB
                y1 = self.mat_y(x1, t1) - RB
                bx, by = ballistic(t, a, x, y0, t1, x1, y1)
                return bx, min(by, self.mat_y(bx, t) - RB)
        tc, x, _ = T[-1]
        a = tc + CONTACT
        s = t - a
        y0 = self.mat_y(x, a) - RB
        by = y0 - 700 * s + 0.5 * G * s * s
        return x + 30 * s, min(by, self.mat_y(x, t) - RB)

    # ---------------------------------------------------------------- Detonate
    def n_shell(self, t):
        """Les segments encore en place (ensemble des k)."""
        if self.t_pop is not None and t >= self.t_pop:
            on = {FALL_ORDER[i] for i, tr in enumerate(self.regrow) if t >= tr}
            if t >= getattr(self, "t_again", 1e9):
                on.discard(FALL_ORDER[0])
            return on
        return {k for k in range(8) if k not in self.seg_fall or t < self.seg_fall[k][0]}

    def swell(self, t):
        if self.t_s8 is None or t < self.t_s8:
            return 1.0
        if self.t_pop is not None and t >= self.t_pop:
            u = t - self.t_pop                                  # il retrouve sa taille, d'un coup, en tremblant
            return 1.0 + 0.10 * math.exp(-u * 5) * math.cos(u * 26)
        lv = 1.0
        for (tp, v) in self.pumps:
            if t >= tp:
                k = min(1.0, (t - tp) / 0.12)
                over = 0.04 * math.sin(math.pi * min(1.0, (t - tp) / 0.3)) if t - tp < 0.3 else 0.0
                lv = lerp(lv, v, k) + over
        return lv

    def redness(self, t):
        if self.t_pop is not None and t >= self.t_pop:
            return max(0.0, 0.35 * (1 - (t - self.t_pop) / 1.2))
        s = self.swell(t)
        base_r = 0.0
        n_lost = 8 - len(self.n_shell(t))
        base_r = 0.05 * n_lost
        return max(base_r, min(1.0, (s - 1.0) / 0.72))

    def grow(self, k, t):
        """Après l'éclatement : où en est la repousse du segment k (0..1)."""
        tr = self.regrow[FALL_ORDER.index(k)]
        return max(0.0, min(1.0, (t - tr) / 0.16))

    def radius_body(self, t):
        """Rayon de contact de Detonate : la coque tant que le segment du dessous tient, puis le disque."""
        if 0 in self.n_shell(t):
            if self.t_pop is not None and t >= self.t_pop:
                return RI + (RD - RI) * self.grow(0, t)
            return RD
        return RI * self.swell(t)

    def det_at(self, t):
        rc = self.radius_body(t)
        rest = self.mat_y(DX, t) - rc
        for (a, b, _) in self.dflights:
            if a <= t <= b:
                y0 = MAT_Y + 10 - self.radius_body(a - 0.01)
                y1 = MAT_Y + 16 - self.radius_body(b + 0.01)
                _, y = ballistic(t, a, DX, y0, b, DX, y1)
                return DX, min(y, rest)
        return DX, rest

    # ---------------------------------------------------------------- pas de simulation
    def step(self, dt):
        evs = []
        self.t += dt
        t = self.t
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= t:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
            if self.conf is not None:
                self._shake_off()
        for k, (tf, _) in self.seg_fall.items():
            if tf <= t < tf + dt:
                evs.append(("event", f"segment {k}"))
        if not self.payoff and self.t_pop is not None and t >= self.t_pop:
            self.payoff = True
            evs.append(("payoff", "confettis"))
            self._burst()
        if self.conf is not None:
            self._conf_step(dt)
        if t >= self.end_s:
            self.done = True
        return evs

    def _burst(self):
        rng = self.rng
        n = 260
        dx, dy = self.det_at(self.t_pop)
        R = RI * PUMPS[-1]
        ang = rng.uniform(-math.pi, math.pi, n)
        ang = np.where(np.sin(ang) > 0.35, -ang, ang)          # surtout vers le haut et les côtés
        spd = rng.uniform(500, 2100, n)
        rr = rng.uniform(0.2, 0.9, n) * R
        C = {
            "x": dx + rr * np.cos(ang), "y": dy + rr * np.sin(ang),
            "vx": spd * np.cos(ang), "vy": spd * np.sin(ang) - 300,
            "col": rng.integers(0, len(CONF_COLS), n), "sz": rng.uniform(0.7, 1.25, n),
            "rot": rng.uniform(0, math.pi, n), "spin": rng.uniform(-9, 9, n), "ph": rng.uniform(0, 6.3, n),
            "st": np.zeros(n, dtype=int), "rx": np.zeros(n), "ry": np.zeros(n), "born": np.full(n, self.t_pop),
        }
        # les segments empilés partent en confettis eux aussi
        extra = []
        for p in self.pieces:
            px, py = self.piece_pos(p, self.t_pop)[:2]
            for _ in range(10):
                a = rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
                s = rng.uniform(250, 800)
                extra.append((px, py, s * math.cos(a), s * math.sin(a)))
        if extra:
            ex = np.array(extra)
            m = len(ex)
            for key, val in (("x", ex[:, 0]), ("y", ex[:, 1]), ("vx", ex[:, 2]), ("vy", ex[:, 3]),
                             ("col", rng.integers(0, len(CONF_COLS), m)), ("sz", rng.uniform(0.6, 1.0, m)),
                             ("rot", rng.uniform(0, math.pi, m)), ("spin", rng.uniform(-9, 9, m)),
                             ("ph", rng.uniform(0, 6.3, m)), ("st", np.zeros(m, dtype=int)), ("rx", np.zeros(m)),
                             ("ry", np.zeros(m)), ("born", np.full(m, self.t_pop))):
                C[key] = np.concatenate([C[key], val])
        self.conf = C

    def _shake_off(self):
        """À chaque retombée, Bounce perd une partie des confettis collés sur lui."""
        C = self.conf
        idx = np.where(C["st"] == 2)[0]
        if not len(idx):
            return
        drop = idx[self.rng.random(len(idx)) < 0.3]
        bx, by = self.bounce_at(self.t)
        for i in drop:
            nx, ny = C["rx"][i], C["ry"][i]
            nrm = math.hypot(nx, ny) + 1e-9
            C["st"][i] = 0
            C["x"][i], C["y"][i] = bx + nx / nrm * (RB + 8), by + ny / nrm * (RB + 8)
            C["vx"][i], C["vy"][i] = nx / nrm * 260, ny / nrm * 260 - 260
            C["born"][i] = self.t + 0.5                          # ne se recolle pas tout de suite

    def _conf_step(self, dt):
        C = self.conf
        t = self.t
        free = C["st"] == 0
        if free.any():
            k = 3.0
            C["vy"][free] += G * dt
            dec = math.exp(-k * dt)
            C["vx"][free] *= dec
            C["vy"][free] *= dec
            sway = 60 * np.sin(C["ph"][free] + t * 5.0)
            C["x"][free] += (C["vx"][free] + sway) * dt
            C["y"][free] += C["vy"][free] * dt
            C["rot"][free] += C["spin"][free] * dt
        bx, by = self.bounce_at(t)
        dx, dy = self.det_at(t)
        rd = self.radius_body(t) if t > self.t_pop + 0.25 else 0.0
        for i in np.where(free)[0]:
            x, y = C["x"][i], C["y"][i]
            if x < -40 or x > W + 40 or y > H:
                C["st"][i] = 4
                continue
            ddx, ddy = x - bx, y - by
            if ddx * ddx + ddy * ddy < (RB * 0.98) ** 2 and t >= C["born"][i]:
                n = math.hypot(ddx, ddy) + 1e-9
                C["st"][i] = 2
                C["rx"][i], C["ry"][i] = ddx / n * RB * 0.9, ddy / n * RB * 0.9
                continue
            if rd > 0:
                ddx, ddy = x - dx, y - dy
                if ddx * ddx + ddy * ddy < (rd * 0.98) ** 2 and ddy < 0:
                    n = math.hypot(ddx, ddy) + 1e-9
                    C["st"][i] = 3
                    C["rx"][i], C["ry"][i] = ddx / n * 0.92, ddy / n * 0.92
                    continue
            if X0 < x < X1 and y >= self.mat_y(x, t) - 4 and C["vy"][i] > 0:
                C["st"][i] = 1
            elif y >= LEG_Y - 4 and C["vy"][i] > 0:
                C["st"][i] = 5
                C["y"][i] = LEG_Y - 4

    def snapshot(self):
        if self.conf is None:
            return (self.t, None)
        C = self.conf
        return (self.t, {k: C[k].copy() for k in ("x", "y", "rot", "ph", "st", "rx", "ry", "col", "sz")})

    def hero_mood(self):
        return None

    def counter(self, snap):
        return None

    # ---------------------------------------------------------------- dessin
    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                if e is None:
                    return 0.0, None
                i = int((t - n["start"]) * 60)
                return float(e[min(i, len(e) - 1)]), n["text"].split(" ", 1)[1]
        return 0.0, None

    def piece_pos(self, p, t, still=False):
        """Un segment tombé : en vol jusqu'à sa pile, puis posé (il suit le tapis)."""
        side_x = p["x1"]
        rest_y = (MAT_Y if still else self.mat_y(side_x, t)) - 13 - PIECE_STEP * p["n"]
        if t >= p["t1"]:
            return side_x, rest_y, p["r1"]
        ux, uy = p.get("dir", (0.0, 0.0))

        def anchor(tt):                                         # sa place, qui suit Detonate dans le tapis
            if p.get("ride"):
                ddx, ddy = self.det_at(tt)
                return ddx + p["off"][0], ddy + p["off"][1]
            return p["p0"]
        if t < p["t0"] + PRE:                                   # il sort d'abord de sa place
            k = ease((t - p["t0"]) / PRE)
            x0, y0 = anchor(t)
            return x0 + ux * PRE_D * k, y0 + uy * PRE_D * k, p["r0"]
        x0, y0 = anchor(p["t0"] + PRE)
        x0, y0 = x0 + ux * PRE_D, y0 + uy * PRE_D
        y1 = MAT_Y - 13 - PIECE_STEP * p["n"]
        x, y = ballistic(t, p["t0"] + PRE, x0, y0, p["t1"], side_x, y1)
        s = (t - p["t0"] - PRE) / (p["t1"] - p["t0"] - PRE)
        return x, y, lerp(p["r0"], p["r1"], ease(s))

    def seg_poly(self, cx, cy, ri, ro, a_mid, half, S, rot=None, off=(0, 0)):
        """Un segment d'anneau. Sur Detonate : centré sur lui, à l'angle a_mid. Hors de lui (rot donné) :
        la même forme, ramenée à son centre, tournée de rot."""
        pts = []
        n = 7
        for j in range(n + 1):
            a = a_mid - half + 2 * half * j / n
            pts.append((ro * math.cos(a), ro * math.sin(a)))
        for j in range(n, -1, -1):
            a = a_mid - half + 2 * half * j / n
            pts.append((ri * math.cos(a), ri * math.sin(a)))
        if rot is None:
            return [((cx + u + off[0]) * S, (cy + v + off[1]) * S) for u, v in pts]
        # forme de référence : segment du haut (a_mid = -90°), ramenée à son centre
        mx = sum(u for u, _ in pts) / len(pts)
        my = sum(v for _, v in pts) / len(pts)
        ca, sa = math.cos(rot), math.sin(rot)
        return [((cx + (u - mx) * ca - (v - my) * sa) * S, (cy + (u - mx) * sa + (v - my) * ca) * S) for u, v in pts]

    def draw_detonate(self, dr, t, S, part="body"):
        x, y = self.det_at(t)
        sw = self.swell(t)
        red = self.redness(t)
        shake = 0.0
        if self.t_s8 is not None and t >= self.t_s8 and (self.t_pop is None or t < self.t_pop):
            shake = 1.5 + 7.0 * max(0.0, (sw - 1.0) / 0.72) ** 1.5
        x += shake * math.sin(t * 61.0) * 0.8
        y += shake * math.sin(t * 47.0 + 1.3) * 0.5
        ri = RI * sw
        # écrasement à l'atterrissage
        sq = 0.0
        for (a, b, _) in self.dflights:
            if 0 <= t - b < 0.35:
                sq = 0.14 * math.exp(-(t - b) * 9) * math.cos((t - b) * 20)
        if self.t_pop is not None and 0 <= t - self.t_pop < 0.6:
            sq = 0.12 * math.exp(-(t - self.t_pop) * 6) * math.cos((t - self.t_pop) * 24)
        sx, sy = 1 + sq, 1 - sq
        on = self.n_shell(t)
        halo_r = 1.6 * max(ri, RD if on else 0.0)
        if part == "halo":
            dr.ellipse([(x - halo_r * sx) * S, (y - halo_r * sy) * S, (x + halo_r * sx) * S, (y + halo_r * sy) * S],
                       fill=mix(D_HALO, (90, 14, 10), red))
            return x, y
        dr.ellipse([(x - ri * sx) * S, (y - ri * sy) * S, (x + ri * sx) * S, (y + ri * sy) * S],
                   fill=mix(D_ORANGE, D_RED, red))
        # la coque : les segments en place, ceux qui se fendent, ceux qui repoussent
        half = math.radians(19.0)
        for k in range(8):
            if k not in on:
                continue
            a = math.radians(SEG_ANG[k])
            grow = 1.0
            if self.t_pop is not None and t >= self.t_pop:
                grow = self.grow(k, t)
            off = (0.0, 0.0)
            tilt = 0.0
            for (kc, tcr, strong) in self.cracks:
                if kc == k and t >= tcr:
                    u = t - tcr
                    if strong:                                     # il pend de travers jusqu'à sa chute
                        amp = 14.0 + 3.0 * math.sin(u * 9) * math.exp(-u * 1.2)
                        tilt = 0.20 + 0.05 * math.sin(u * 11) * math.exp(-u * 0.8)
                    else:                                          # il sort, tremble, et se recolle
                        amp = 12.0 * (1 - ease((u - 1.4) / 0.25)) if u > 1.4 else 12.0
                        amp += 3.0 * math.sin(u * 30) * math.exp(-u * 2)
                        tilt = 0.12 * (1 - ease((u - 1.4) / 0.25)) if u > 1.4 else 0.12
                        if u > 1.8:
                            amp, tilt = 0.0, 0.0
                    off = (amp * math.cos(a), amp * math.sin(a))
            ro = ri + (RD - RI) * sw * grow
            a_mid = a + tilt
            pts = self.seg_poly(x, y, ri - 1, ro, a_mid, half * (0.4 + 0.6 * grow), S, off=off)
            pts = [(((px / S - x) * sx + x) * S, ((py / S - y) * sy + y) * S) for (px, py) in pts]
            dr.polygon(pts, fill=mix(D_SHELL, (120, 30, 18), red * 0.6))
        # le visage furieux du dessin du fan : deux grands traits en V, une grimace tordue
        talk, line = self.talking(t)
        self.draw_face(dr, x, y, ri, S, talk, line, red, sx, sy)
        return x, y

    def draw_face(self, dr, x, y, r, S, talk, line, red, sx, sy):
        def P(u, v):
            return ((x + u * r * sx) * S, (y + v * r * sy) * S)
        w = max(2, int(0.11 * r * S))
        deep = 0.06 * red
        dr.line([P(-0.82, -0.66 - deep), P(-0.10, -0.08)], fill=INK, width=w)
        dr.line([P(0.80, -0.72 - deep), P(0.12, -0.10)], fill=INK, width=w)
        er = 0.085 + 0.02 * red
        for ex in (-0.34, 0.34):
            ey = -0.12
            dr.ellipse([P(ex - er, ey - er)[0], P(ex - er, ey - er)[1], P(ex + er, ey + er)[0], P(ex + er, ey + er)[1]],
                       fill=INK)
        if talk > 0.08:
            op = 0.10 + 0.32 * talk * (1.25 if line in ("hurle", "lent", "furax", "fin") else 1.0)
            top = [(-0.42, 0.40), (-0.24, 0.34), (-0.06, 0.38), (0.12, 0.33), (0.30, 0.36), (0.44, 0.33)]
            bot = [(0.40, 0.36 + op), (0.20, 0.40 + op), (0.0, 0.42 + op), (-0.22, 0.40 + op), (-0.40, 0.42 + 0.4 * op)]
            dr.polygon([P(u, v) for u, v in top + bot], fill=INK)
            dr.polygon([P(-0.30, 0.37), P(0.30, 0.355), P(0.28, 0.40), P(-0.28, 0.41)], fill=(240, 236, 228))
        else:
            pts = [(-0.46, 0.54), (-0.40, 0.45), (-0.26, 0.39), (-0.12, 0.40), (-0.02, 0.45), (0.10, 0.44),
                   (0.20, 0.36), (0.34, 0.33), (0.52, 0.33), (0.54, 0.38)]
            dr.line([P(u, v) for u, v in pts], fill=INK, width=max(2, int(0.075 * r * S)), joint="curve")
            dr.line([P(-0.22, 0.66), P(-0.14, 0.58), P(-0.02, 0.53)], fill=INK, width=max(2, int(0.06 * r * S)),
                    joint="curve")

    def draw_conf_piece(self, dr, x, y, rot, ph, col, sz, S, t):
        flut = abs(math.cos(ph + t * 7.0))
        w2, h2 = 9 * sz * (0.25 + 0.75 * flut), 5 * sz
        ca, sa = math.cos(rot), math.sin(rot)
        pts = [((x + u * ca - v * sa) * S, (y + u * sa + v * ca) * S) for u, v in
               ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2))]
        dr.polygon(pts, fill=CONF_COLS[int(col)])

    def draw(self, dr, snap, t, S):
        t, C = snap

        def rect(x0, y0, x1, y1, col):
            dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        # la salle
        rect(0, 470, W, LEG_Y, WALL)
        rect(0, 462, W, 470, dim(WALL, 0.6))
        rect(0, LEG_Y, W, H, FLOOR_COL)
        # le trampoline : pieds, cadre, ressorts, toile
        for (xa, xb) in ((120, 96), (960, 984), (420, 410), (660, 670)):
            dr.line([(xa * S, (MAT_Y + 26) * S), (xb * S, LEG_Y * S)], fill=FRAME, width=int(12 * S))
        rect(40, MAT_Y + 18, 1040, MAT_Y + 34, FRAME)
        N = 64
        xs = [X0 + (X1 - X0) * i / N for i in range(N + 1)]
        ys = [self.mat_y(xx, t) for xx in xs]
        for side in (0, 1):                                       # les ressorts
            xa = 26 if side == 0 else 1054
            xe = X0 if side == 0 else X1
            ye = ys[0] if side == 0 else ys[-1]
            zz = []
            for j in range(9):
                u = j / 8
                zz.append((lerp(xa, xe, u) * S, (lerp(MAT_Y + 4, ye, u) + (7 if j % 2 else -7) * (0 < j < 8)) * S))
            dr.line(zz, fill=(150, 150, 170), width=int(3 * S))
        poly = [(xx * S, yy * S) for xx, yy in zip(xs, ys)] + [(xx * S, (yy + 12) * S) for xx, yy in
                                                                 reversed(list(zip(xs, ys)))]
        dr.polygon(poly, fill=MAT_COL)
        dr.line([(xx * S, yy * S) for xx, yy in zip(xs, ys)], fill=MAT_EDGE, width=int(4 * S))
        rect(10, MAT_Y - 10, 40, MAT_Y + 34, PAD)
        rect(1040, MAT_Y - 10, 1070, MAT_Y + 34, PAD)

        self.draw_detonate(dr, t, S, "halo")             # le halo derrière les segments tombés
        # les segments tombés (avant l'éclatement)
        if self.t_pop is None or t < self.t_pop:
            half = math.radians(19.0)
            for p in self.pieces:
                if t < p["t0"]:
                    continue
                px, py, rot = self.piece_pos(p, t)
                pts = self.seg_poly(px, py, RI - 1, RD, -math.pi / 2, half, S, rot=rot)
                dr.polygon(pts, fill=D_SHELL)
                dr.line(pts[:8], fill=D_SHELL_HI, width=max(1, int(2 * S)))

        p = self.again_piece
        if p is not None and t >= p["t0"]:
            px, py, rot = self.piece_pos(p, t)
            pts = self.seg_poly(px, py, RI - 1, RD, -math.pi / 2, math.radians(19.0), S, rot=rot)
            dr.polygon(pts, fill=D_SHELL)

        # les confettis posés sur le tapis ou par terre (derrière les personnages)
        if C is not None:
            for i in np.where((C["st"] == 1) | (C["st"] == 5))[0]:
                x = C["x"][i]
                y = (self.mat_y(x, t) - 4) if C["st"][i] == 1 else C["y"][i]
                self.draw_conf_piece(dr, x, y, C["rot"][i], 0.0, C["col"][i], C["sz"][i], S, 0.0)

        # Detonate
        dx, dy = self.draw_detonate(dr, t, S)
        # l'éclatement : un anneau de lumière, pas de feu
        if self.t_pop is not None and 0 <= t - self.t_pop < 0.22:
            u = (t - self.t_pop) / 0.22
            rr = RI * PUMPS[-1] * (1.0 + 1.6 * u)
            dr.ellipse([(dx - rr) * S, (dy - rr) * S, (dx + rr) * S, (dy + rr) * S],
                       outline=mix(WALL, (255, 240, 200), 1 - u), width=int((14 - 10 * u) * S))
        if C is not None:
            sd = self.radius_body(t)
            for i in np.where(C["st"] == 3)[0]:
                self.draw_conf_piece(dr, dx + C["rx"][i] * sd, dy + C["ry"][i] * sd, C["rot"][i], 0.0,
                                     C["col"][i], C["sz"][i], S, 0.0)

        # Bounce, dessiné par le moteur seulement
        bx, by = self.bounce_at(t)
        base.ball(dr, bx * S, by * S, RB * S)
        if C is not None:
            for i in np.where(C["st"] == 2)[0]:
                self.draw_conf_piece(dr, bx + C["rx"][i], by + C["ry"][i], C["rot"][i], 0.0,
                                     C["col"][i], C["sz"][i], S, 0.0)
            for i in np.where(C["st"] == 0)[0]:
                self.draw_conf_piece(dr, C["x"][i], C["y"][i], C["rot"][i], C["ph"][i], C["col"][i],
                                     C["sz"][i], S, t)


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0, "hook_text_s": 2.4}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
