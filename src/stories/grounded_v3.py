"""
Grounded v3 : « How do you ground Bounce? »

Grounded (perso de fan, boule rose aux couleurs inversées de Bounce) est perché sur une armoire et
veut clouer Bounce au sol. Il lui lâche des charges de plus en plus lourdes : un livre, une pile de
livres, un panier à linge, des briques, un poids d'une tonne, puis lui-même. Bounce continue de
rebondir avec tout sur la tête (contacts durs sur le bois : « Bounce » ; contacts mous sur un matelas :
muets). La pile finit par basculer : le panier retombe sur Grounded.

Grounded ne dit que son nom (banque hors dépôt, cfg["voice_bank"]) ; le sous-titre traduit.

    python3 src/stories/grounded_v3.py configs/grounded_v3.json [--simulate]
"""
import math, sys, os, wave
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, font
import audio_kit as ak
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import voice as narr_voice

SR = ak.SR

# ------------------------------------------------------------------ la voix de Grounded (banque)
WHO = "Grounded"
LINES = {"dit": "dit.wav", "fort": "fort.wav", "las": "las.wav"}
GAIN = {"fort": 1.15}
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


def bank_say(text, voice=narr_voice.DEFAULT_VOICE, length_scale=None, sr=SR):
    if text in BANK:
        return BANK[text].copy()
    return _orig_say(text, voice, length_scale, sr)


narr_voice.say = bank_say
base.subtitle_at = lambda narr, t, n_words: None          # les sous-titres sont dessinés par le thème

_orig_build = base.build_narration


def build_narration_keep(sim, cfg):
    narr, replies = _orig_build(sim, cfg)
    sim.narr = narr
    return narr, replies


base.build_narration = build_narration_keep

# le mot de Bounce : la prise la plus courte parmi quelques essais (toujours la même ensuite)
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


def fft_reverb(x, sr, tail_s=0.8, wet=0.5):
    """base.reverb à l'identique, avec une convolution par FFT (np.convolve est trop lent sous charge)."""
    n = int(tail_s * sr)
    ir = np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / (sr * tail_s / 4))
    ir[0] = 0.0
    ir /= (np.sum(np.abs(ir)) + 1e-9) / 3.0
    m = len(x) + n - 1
    size = 1 << (m - 1).bit_length()
    wetx = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:m]
    out = np.zeros(len(wetx))
    out[:len(x)] += x * (1 - wet)
    out += wetx * wet
    return out / (np.max(np.abs(out)) + 1e-9)


base.reverb = fft_reverb

# ------------------------------------------------------------------ géométrie
W, H = 1080, 1920
G = 2600.0
RB = 120.0                     # Bounce
RG = 95.0                      # Grounded
FLOOR = 1180.0
BY_FLOOR = FLOOR - RB          # centre de Bounce posé sur le bois
WARD = (120.0, 340.0, 800.0)   # armoire : x0, x1, dessus
GTOP = (230.0, WARD[2] - RG)   # Grounded sur l'armoire
MAT = (610.0, 890.0, 1100.0)   # matelas : x0, x1, dessus (80 px d'épaisseur)
MAT_X = 735.0
G_FINAL_X = 400.0
SIGN = (405.0, 875.0, 560.0, 710.0)
WALL, WALL2 = (20, 26, 44), (26, 33, 54)
FLOOR_C, FLOOR_L = (58, 44, 36), (44, 33, 27)
G_HALO, G_DISC, G_INK = (240, 168, 214), (228, 100, 172), (252, 250, 252)
BOOKC = [(70, 110, 190), (190, 80, 70), (80, 150, 100), (200, 160, 60)]
BASKET_C, BRICK_C, IRON = (226, 222, 200), (170, 74, 52), (64, 66, 76)

# dimensions des charges (hauteur posée)
BOOK_H, BOOK_W = 36.0, 150.0
BASK_W, BASK_H = 300.0, 240.0       # panier retourné : bande du haut 18, barreaux, bord de 20
BRICK_H, BRICK_W = 50.0, 220.0
TON_H, TON_W = 110.0, 210.0

# ------------------------------------------------------------------ le déroulé
HARD = [0.40, 2.10, 4.45, 5.75, 7.00, 9.40, 10.75, 12.30, 13.90, 15.35, 17.20, 18.70, 20.30, 21.80, 23.40,
        24.75, 26.60, 28.00, 30.40, 31.85, 33.30, 35.00, 36.40, 38.20, 39.40, 41.15, 42.95, 44.30, 45.30,
        46.95, 47.95, 48.95, 49.95, 51.55, 52.50, 54.00, 55.80, 56.80, 57.80, 58.75, 59.70, 60.65]
SOFT_EXTRA = [61.52, 62.45, 63.45]          # libre, il rebondit sur le matelas
T_P = {"P1": 4.45, "P2": 9.40, "P3": 17.20, "P4": 23.40, "P5": 30.40, "P6": 42.95, "P7": 48.95}
T_FLING, T_FLING_LAND = 10.75, 11.30
T_PRESQUE, T_PRESQUE_END = 35.00, 36.40
T_SQUASH, T_RELAUNCH = 42.95, 44.30
SLOMO = (43.45, 44.20)
T_SIGNFALL = 44.30
T_DOOR = 52.50
T_TIP, T_ISSUE = 60.65, 61.85
T_WIN = T_ISSUE + 1.0
PAYOFF_AT = T_ISSUE + 0.95
END = T_ISSUE + 2.0
LINES_AT = [(3.05, "dit", "GROUNDED! ONE WEEK."), (7.95, "dit", "GROUNDED! ONE MONTH."),
            (16.30, "dit", "GROUNDED! ONE YEAR!"), (25.70, "dit", "GROUNDED! TEN YEARS!"),
            (29.60, "fort", "GROUNDED!! A CENTURY!"), (42.10, "dit", "GROUNDED. FOREVER."),
            (54.95, "fort", "GROUNDED!! STOP BOUNCING!")]


def lerp(a, b, s):
    return a + (b - a) * s


def clamp(s, a=0.0, b=1.0):
    return max(a, min(b, s))


def ease(s):
    s = clamp(s)
    return s * s * (3 - 2 * s)


def rot(dx, dy, th):
    """vecteur (dx, dy) tourné de th (th > 0 : penche vers la gauche quand dy < 0)."""
    c, s = math.cos(th), math.sin(th)
    return dx * c + dy * s, -dx * s + dy * c


def poly(dr, pts, S, fill, outline=None, width=0):
    dr.polygon([(x * S, y * S) for x, y in pts], fill=fill, outline=outline, width=width)


def rect_pts(cx, cy, w, h, th):
    out = []
    for u, v in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        a, b = rot(u, v, th)
        out.append((cx + a, cy + b))
    return out


class Sim:
    scene_top = 0.27

    def __init__(self, cfg, rng):
        self.cfg = cfg
        load_bank(cfg)
        self.t = 0.0
        self.done = False
        self.payoff = False
        self.narr = []
        self.payoff_at = PAYOFF_AT
        self.end_s = END
        # charge sur la tête (pour le creux du matelas et la hauteur des arcs)
        # contacts : (t, kind, x, y)
        C = []
        hx = [500, 535, 505, 550, 520, 495, 540, 510, 530, 500]
        for i, t in enumerate(HARD):
            x = hx[i % len(hx)]
            if t >= 48.9:                             # la pile le repousse vers l'armoire
                x = lerp(545, 490, clamp((t - 48.9) / (T_TIP - 48.9)))
            C.append((t, "H", float(x)))
        # contacts mous : un ou deux sur le matelas entre deux durs éloignés
        soft = []
        STACK_H = [0, BOOK_H, 4 * BOOK_H, 18, 18 + BRICK_H, 18 + BRICK_H + TON_H]

        def top_ok(t0, y0, t1, y1, load, ceil):
            T = t1 - t0
            vy = (y1 - y0) / T - 0.5 * G * T
            apex = y0 - vy * vy / (2 * G) if vy < 0 else y0
            return apex - RB - STACK_H[load] >= ceil

        for a, b in zip(HARD, HARD[1:]):
            g = b - a
            if T_SQUASH <= a < T_RELAUNCH:
                continue
            if a >= T_RELAUNCH:                       # toute la pile : arcs courts
                if g > 1.0:
                    soft.append(a + g * (0.47 if len(soft) % 2 else 0.52))
                continue
            ceil = 485.0                             # l'accroche reste affichée : rien au-dessus
            L = self.load(a + 1e-3)
            for n in range(0, 5):
                fr = [k / (n + 1) + ((0.03 if (len(soft) + k) % 2 else -0.03) if n else 0) for k in range(1, n + 1)]
                ts = [a] + [a + g * f for f in fr] + [b]
                ys = [BY_FLOOR] + [MAT[2] - RB + [22, 26, 34, 42, 52, 70][L] for _ in fr] + [BY_FLOOR]
                if all(top_ok(ts[i], ys[i], ts[i + 1], ys[i + 1], L, ceil) for i in range(len(ts) - 1)):
                    soft += ts[1:-1]
                    break
        for t in soft + SOFT_EXTRA:
            C.append((t, "S", MAT_X + (10 if int(t * 10) % 2 else -15)))
        C.sort()
        self.C = [(t, k, x, self.contact_y(t, k)) for t, k, x in C]
        self.soft = [c[0] for c in self.C if c[1] == "S"]
        self.hits = [(t, "dur") for t in HARD]
        self.hi = 0
        self.lines = [(t, WHO + " " + k, f"g{i}") for i, (t, k, _) in enumerate(LINES_AT)]
        self.subs = {f"g{i}": s for i, (_, _, s) in enumerate(LINES_AT)}

    # ---------------------------------------------------------- charge et hauteurs
    def load(self, t):
        if t < T_P["P1"]:
            return 0
        if t < T_P["P2"]:
            return 1
        if t < T_P["P3"]:
            return 2
        if t < T_P["P4"]:
            return 3
        if t < T_P["P5"]:
            return 4
        if t < T_P["P6"]:
            return 5
        if t < T_TIP:
            return 6
        return 0

    def contact_y(self, t, kind):
        if kind == "H":
            return BY_FLOOR
        dent = [22, 26, 34, 42, 52, 70, 80][self.load(t - 1e-3)]
        if t > T_TIP:
            dent = 26
        return MAT[2] - RB + dent

    # ---------------------------------------------------------- Bounce
    def bounce_raw(self, t):
        """(x, y) du centre, trajectoire balistique entre contacts (une seule gravité)."""
        C = self.C
        if T_SQUASH <= t <= T_RELAUNCH:
            return C_x(C, T_SQUASH), BY_FLOOR
        prev = (-0.62, "S", MAT_X, MAT[2] - RB + 22)
        nxt = None
        for c in C:
            if c[0] > t:
                nxt = c
                break
            prev = c
        if nxt is None:
            nxt = (64.55, "S", MAT_X, MAT[2] - RB + 26)
        t0, _, x0, y0 = prev
        t1, _, x1, y1 = nxt
        if abs(t0 - T_SQUASH) < 1e-6:
            t0 = T_RELAUNCH
            for c in C:
                if abs(c[0] - T_RELAUNCH) < 1e-6:
                    x0 = c[2]
        T = t1 - t0
        s = t - t0
        vy = (y1 - y0) / T - 0.5 * G * T
        y = y0 + vy * s + 0.5 * G * s * s
        x = lerp(x0, x1, s / T)
        return x, y

    def squash(self, t):
        """(sx, sy) de Bounce : écrasé au contact dur, enfoncé au contact mou, aplati sous Grounded."""
        if T_SQUASH <= t <= T_RELAUNCH:
            k = ease((t - T_SQUASH) / 0.12)
            sy = lerp(1.0, 0.6, k)
            if t >= SLOMO[0]:                       # ralenti : il regonfle d'un cheveu
                sy = 0.6 + 0.07 * ease((t - SLOMO[0]) / (SLOMO[1] - SLOMO[0]))
                pulse = 0.012 * math.sin((t - SLOMO[0]) * 2 * math.pi * 1.2)
            else:
                pulse = 0.03 * math.sin((t - T_SQUASH) * 2 * math.pi * 3.2)
            if t > SLOMO[1]:
                sy = lerp(0.67, 1.0, ease((t - SLOMO[1]) / (T_RELAUNCH - SLOMO[1])))
                pulse = 0.0
            sy += pulse
            return 1.0 / max(0.55, sy) ** 0.5 * (1.0 + 0.25 * (1 - sy)), sy
        best = 1.0
        for c in self.C:
            d = t - c[0]
            if -0.05 <= d <= 0.1:
                amp = 0.16 if c[1] == "H" else 0.10
                amp = min(0.22, amp + 0.012 * self.load(c[0] - 1e-3))
                k = 1 - abs(d - 0.0) / (0.1 if d >= 0 else 0.05)
                best = min(best, 1 - amp * clamp(k))
        return 1.0 / best ** 0.5, best

    def bounce_at(self, t):
        x, y = self.bounce_raw(t)
        sx, sy = self.squash(t)
        if sy < 1.0:
            # le bas reste sur la surface (sol ou matelas creusé)
            bottom = y + RB
            y = bottom - RB * sy
        return x, y, sx, sy

    # ---------------------------------------------------------- la pile
    def lean(self, t):
        if t < T_RELAUNCH + 1.0:
            return 0.0
        keys = [(T_RELAUNCH + 1.0, 0.0), (47.95, 0.10), (48.95, 0.26), (52.5, 0.21), (56.8, 0.33),
                (58.75, 0.42), (T_TIP, 0.56)]
        th = keys[-1][1]
        for (a, va), (b, vb) in zip(keys, keys[1:]):
            if a <= t <= b:
                th = lerp(va, vb, ease((t - a) / (b - a)))
                break
        # chaque contact fait osciller la pile
        for c in HARD:
            d = t - c
            if 0 <= d < 0.6 and c >= T_RELAUNCH:
                th += 0.05 * math.sin(d * 18) * math.exp(-d * 5)
        return th

    def jolt(self, t, k):
        """petit décollement de la charge k (0..) juste après un contact."""
        for c in self.C:
            d = t - c[0]
            if 0 <= d < 0.22:
                a = (10 + 4 * k) if c[1] == "H" else 6
                return -a * math.sin(math.pi * d / 0.22)
        return 0.0

    def presque_dx(self, t):
        if T_PRESQUE <= t <= T_PRESQUE_END:
            s = (t - T_PRESQUE) / (T_PRESQUE_END - T_PRESQUE)
            if s < 0.55:
                return 175 * ease(s / 0.55)
            return 175 * (1 - ease((s - 0.55) / 0.45))
        return 0.0

    def stack_layout(self, t):
        """positions des charges posées sur Bounce : dict nom -> (cx, cy, th)."""
        bx, by, sx, sy = self.bounce_at(t)
        th = self.lean(t)
        top = by - RB * sy
        out = {}
        h = 0.0
        L = self.load(t)
        dxp = self.presque_dx(t)
        tilt_p = 0.0
        if dxp:
            tilt_p = -0.18 * dxp / 175.0
        if L >= 3:
            j = self.jolt(t, 0) * 0.6
            hb = min(BASK_H, FLOOR - top + 18)
            cy = top - 18 + hb / 2 + j
            out["basket"] = (bx + dxp, cy, th + tilt_p, hb)
            px, py = bx + dxp, cy - hb / 2            # le dessus du panier : pivot de la pile
            h = 0.0
            if L >= 4:
                j = self.jolt(t, 1)
                a, b = rot(0, -(h + BRICK_H / 2) + j, th + tilt_p)
                out["bricks"] = (px + a, py + b, th + tilt_p)
                h += BRICK_H
            if L >= 5:
                j = self.jolt(t, 2)
                a, b = rot(0, -(h + TON_H / 2) + j, th + 1.4 * tilt_p)
                out["ton"] = (px + dxp * 0.1 + a, py + b, th + 1.4 * tilt_p)
                h += TON_H
            if L >= 6:
                j = self.jolt(t, 3) * 1.3
                a, b = rot(0, -(h + RG) + j, th)
                out["grounded"] = (px + a, py + b, th)
        elif L >= 1:
            n = 1 if L == 1 else 4
            for i in range(n):
                if L == 2 and i == 3 and t >= T_FLING:
                    continue
                j = self.jolt(t, i) * (1 + 0.5 * i)
                wob = 0.0
                if L == 2:
                    wob = 0.06 * i * math.sin(t * 7.0 + i)
                rot0 = 0.0 if L == 1 else wob
                if L == 1 and t > 7.1:
                    rot0 = 0.30 * ease((t - 7.1) / 0.3)
                a, b = rot(8 * ((i * 5) % 3 - 1), -(i * BOOK_H + BOOK_H / 2) + j, rot0)
                out[f"book{i}"] = (bx + a, top + b, rot0)
        return out

    # ---------------------------------------------------------- Grounded
    def grounded_at(self, t):
        """(x, y, humeur, écrasement, porte, visible_derrière_l_armoire)."""
        gx, gy = GTOP
        mood, sq, carry = "furieux", 0.0, None
        # le transport des charges
        if t < 3.85:
            carry = "book1"
        elif 7.0 <= t < 8.75:
            carry = "books3"
        elif 14.1 <= t < 16.70:
            carry = "basket"
        elif 21.0 <= t < 22.85:
            carry = "bricks"
        elif 28.3 <= t < 29.85:
            carry = "ton"
        if T_FLING_LAND <= t < 12.30:
            carry = "flung"
        # positions
        def behind(a, b):            # se baisse derrière l'armoire, puis remonte
            s = (t - a) / (b - a)
            d = 210 * (ease(s / 0.3) if s < 0.5 else 1 - ease((s - 0.7) / 0.3))
            return gx, gy + d

        def away(a, b, slow=False):  # sort par la gauche, revient
            s = (t - a) / (b - a)
            if s < 0.25:
                u = s / 0.25
                return lerp(gx, -170, u), gy - 60 * math.sin(math.pi * u)
            if s < 0.7:
                return -300, gy
            u = (s - 0.7) / 0.3
            hop = 40 if slow else 60
            return lerp(-170, gx, u), gy - hop * math.sin(math.pi * u)
        if 3.72 <= t < 4.1:
            gx += 50 * math.sin(math.pi * (t - 3.72) / 0.38)
        elif 8.67 <= t < 9.0:
            gx += 50 * math.sin(math.pi * (t - 8.67) / 0.33)
        elif 16.55 <= t < 16.95:
            gx += 55 * math.sin(math.pi * (t - 16.55) / 0.40)
        elif 22.75 <= t < 23.1:
            gx += 50 * math.sin(math.pi * (t - 22.75) / 0.35)
        elif 29.75 <= t < 30.15:
            gx += 45 * math.sin(math.pi * (t - 29.75) / 0.40)
        if 6.0 <= t < 7.0:
            gx, gy = behind(6.0, 7.0)
        elif 12.7 <= t < 14.1:
            gx, gy = behind(12.7, 14.1)
        elif 19.0 <= t < 21.0:
            gx, gy = away(19.0, 21.0)
        elif 26.6 <= t < 28.3:
            gx, gy = away(26.6, 28.3)
        elif 28.3 <= t < 29.3:                  # il revient lentement sous le poids
            s = (t - 28.3) / 1.0
            gx, gy = lerp(-60, GTOP[0], ease(s)), GTOP[1] - 25 * abs(math.sin(s * math.pi * 3))
        if 27.9 <= t < 30.0:
            sq = 0.22
        # l'élan et le saut sur la pile
        if 39.4 <= t < 42.05:
            gx = lerp(GTOP[0], 175, ease((t - 39.4) / 1.0))
        if 42.05 <= t < T_SQUASH:
            s = (t - 42.05) / (T_SQUASH - 42.05)
            lay = self.stack_layout(T_SQUASH + 0.001)
            tx, ty = lay["grounded"][0], lay["grounded"][1]
            T = T_SQUASH - 42.05
            vy = (ty - GTOP[1]) / T - 0.5 * G * T
            u = t - 42.05
            gx, gy = lerp(175, tx, s), GTOP[1] + vy * u + 0.5 * G * u * u
        if T_SQUASH <= t < T_TIP:
            lay = self.stack_layout(t)
            gx, gy, _ = lay["grounded"]
        if t >= T_TIP:
            lay = self.stack_layout(T_TIP - 0.001)
            sx0, sy0, _ = lay["grounded"]
            T = 0.70
            u = clamp(t - T_TIP, 0, T)
            tx, ty = G_FINAL_X, FLOOR - RG
            vy = (ty - sy0) / T - 0.5 * G * T
            gx, gy = lerp(sx0, tx, u / T), sy0 + vy * u + 0.5 * G * u * u
        # humeurs
        windows = [(4.45, 5.45, "satisfait"), (5.75, 6.0, "stupefait"), (9.40, 10.4, "satisfait"),
                   (10.75, 12.3, "stupefait"), (17.2, 18.2, "satisfait"), (18.7, 19.0, "stupefait"),
                   (23.4, 24.4, "satisfait"), (24.75, 26.5, "stupefait"), (30.4, 31.4, "satisfait"),
                   (31.85, 32.8, "stupefait"), (35.0, 36.6, "stupefait"), (T_SQUASH, SLOMO[0], "satisfait"),
                   (SLOMO[0], T_RELAUNCH, "stupefait"), (T_RELAUNCH, T_TIP + 0.6, "panique"),
                   (T_TIP + 0.6, 99, "las")]
        for a, b, m in windows:
            if a <= t < b:
                mood = m
        if T_SQUASH <= t < T_TIP and mood == "furieux":
            mood = "panique"
        return gx, gy, mood, sq, carry

    # ---------------------------------------------------------- moteur
    def step(self, dt):
        evs = []
        self.t += dt
        # le mot part à l'image du contact (ou juste après), jamais avant
        while self.hi < len(self.hits) and self.hits[self.hi][0] <= self.t - dt + 1e-6:
            evs.append(("hit", self.hits[self.hi][1]))
            self.hi += 1
        if not self.payoff and self.t >= self.payoff_at:
            self.payoff = True
            evs.append(("payoff", "panier"))
        if self.t >= self.end_s:
            self.done = True
        return evs

    def hero_mood(self):
        return "win"

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    def talking(self, t):
        for n in self.narr:
            if n["start"] <= t <= n["end"]:
                e = ENV.get(n["text"])
                return 0.0 if e is None else float(e[min(int((t - n["start"]) * 60), len(e) - 1)])
        return 0.0

    # ---------------------------------------------------------- dessin
    def draw(self, dr, snap, t, S):
        img = dr._image
        # mur sur toute la hauteur, plinthe, sol en lattes
        dr.rectangle([0, 0, W * S, FLOOR * S], fill=WALL)
        for i in range(0, int(FLOOR), 96):
            dr.rectangle([0, i * S, W * S, (i + 48) * S], fill=WALL2)
        dr.rectangle([0, (FLOOR - 14) * S, W * S, FLOOR * S], fill=(34, 40, 62))
        dr.rectangle([0, FLOOR * S, W * S, H * S], fill=FLOOR_C)
        for k, yy in enumerate(range(int(FLOOR) + 70, H, 90)):
            dr.line([(0, yy * S), (W * S, yy * S)], fill=FLOOR_L, width=int(4 * S))
            off = 180 * (k % 3)
            for xx in range(off, W, 540):
                dr.line([(xx * S, yy * S), (xx * S, (yy + 90) * S)], fill=FLOOR_L, width=int(4 * S))
        self.draw_floor_decor(dr, S)
        # l'accroche reste au mur toute la vidéo (dessinée derrière la scène : la pile passe devant)
        lines, hf, lh, hook_top = base.layout_hook(self.cfg, S, W * S, H * S, self.scene_top * H * S - 30 * S)
        for i, line in enumerate(lines):
            dr.text((W * S / 2, hook_top + (i + 0.5) * lh), line, fill=(255, 255, 255), anchor="mm", font=hf)
        shake = 0.0
        for c in HARD:
            d = t - c
            if 0 <= d < 0.3:
                shake = 4 * math.sin(d * 60) * (1 - d / 0.3)
        self.draw_sign(dr, t, S, shake)
        # matelas
        self.draw_mattress(dr, t, S)
        # Grounded (derrière l'armoire quand il s'y cache)
        gx, gy, mood, gsq, carry = self.grounded_at(t)
        on_ward = t < 42.05
        jump = 0.0
        if on_ward:
            for c in HARD:
                d = t - c
                if 0 <= d < 0.35:
                    jump = -16 * math.sin(math.pi * d / 0.35)
            if 2.10 <= t < 2.7:
                gx += 5 * math.sin(t * 70)
        gy += jump
        talk = self.talking(t)
        if any(n["start"] <= t <= n["end"] + 0.2 for n in self.narr):
            if mood in ("satisfait",):
                mood = "furieux"
        under_basket = t >= T_ISSUE - 0.02
        early = t < 42.05
        if early:
            draw_grounded(dr, gx, gy, RG, S, mood=mood, talk=talk, sq=gsq)
            self.draw_carry(dr, carry, gx, gy - RG * (1 - gsq), t, S)
        # armoire (devant Grounded quand il se baisse)
        x0, x1, top = WARD
        wx = shake * 0.6 if on_ward else 0.0
        dr.rectangle([(x0 + wx) * S, top * S, (x1 + wx) * S, FLOOR * S], fill=(92, 62, 44))
        dr.rectangle([(x0 + 14 + wx) * S, (top + 16) * S, ((x0 + x1) / 2 - 4 + wx) * S, (FLOOR - 20) * S],
                     fill=(108, 74, 52))
        dr.rectangle([((x0 + x1) / 2 + 4 + wx) * S, (top + 16) * S, (x1 - 14 + wx) * S, (FLOOR - 20) * S],
                     fill=(108, 74, 52))
        if t >= T_DOOR:
            # la porte de droite s'ouvre d'un coup : il n'en reste qu'une tranche, des chaussettes tombent
            k = ease((t - T_DOOR) / 0.15)
            mx = (x0 + x1) / 2 + 4
            dr.rectangle([(mx + wx) * S, (top + 16) * S, (x1 - 14 + wx) * S, (FLOOR - 20) * S], fill=(40, 30, 26))
            dr.rectangle([(x1 - 14 + wx) * S, (top + 16) * S, (x1 - 14 + 22 * k + wx) * S, (FLOOR - 20) * S], fill=(120, 84, 60))
            for i, (c, vx, vy0) in enumerate((((230, 230, 240), 260, -500), ((90, 170, 220), 340, -300),
                                              ((230, 120, 150), 200, -150))):
                u = clamp(t - T_DOOR - 0.05 * i, 0, 9)
                yy0 = 900 + 60 * i
                land = FLOOR - 14
                tt = u
                y = yy0 + vy0 * tt + 0.5 * G * tt * tt
                xx = x1 - 30 + vx * tt
                if y >= land:
                    # posée : on résout l'instant d'atterrissage
                    a = 0.5 * G; b = vy0; cc = yy0 - land
                    tl = (-b + math.sqrt(b * b - 4 * a * cc)) / (2 * a)
                    xx, y = x1 - 30 + vx * tl, land
                dr.rounded_rectangle([(xx - 26) * S, (y - 12) * S, (xx + 26) * S, (y + 12) * S], radius=int(10 * S), fill=c)
        for hx in ((x0 + x1) / 2 - 18, (x0 + x1) / 2 + 18):
            dr.ellipse([(hx - 6 + wx) * S, 990 * S, (hx + 6 + wx) * S, 1002 * S], fill=(200, 170, 110))
        # charges tombées au sol (fin)
        self.draw_fallen(dr, t, S)
        if under_basket:
            draw_grounded(dr, gx, gy, RG, S, mood=mood, talk=0.0, sq=0.0)
        # charges en chute
        self.draw_falling(dr, t, S)
        # Bounce, puis ce qu'il a sur la tête
        bx, by, sx, sy = self.bounce_at(t)
        lay = self.stack_layout(t) if t < T_TIP else {}
        if "basket" in lay:
            bk = lay["basket"]
            self.draw_basket(dr, bk[0], bk[1], bk[2], bk[3], S, back=True)
        self.draw_bounce(img, dr, bx, by, sx, sy, t, S)
        for k in ("book0", "book1", "book2", "book3"):
            if k in lay:
                self.draw_book(dr, *lay[k], int(k[-1]), S)
        if "basket" in lay:
            bk = lay["basket"]
            self.draw_basket(dr, bk[0], bk[1], bk[2], bk[3], S)
        if "bricks" in lay:
            self.draw_bricks(dr, *lay["bricks"], S)
        if "ton" in lay:
            self.draw_ton(dr, *lay["ton"], S)
        if 42.05 <= t < T_TIP:
            rr = lay["grounded"][2] * 0.5 if "grounded" in lay else 0.0
            draw_grounded(dr, gx, gy, RG, S, mood=mood, talk=talk, sq=0.0, rot=rr)
        if t >= T_TIP:
            self.draw_tip(dr, t, S)
            if not under_basket:
                draw_grounded(dr, gx, gy, RG, S, mood=mood, talk=talk, sq=0.0)
        if under_basket:
            bxk, byk, thk = self.basket_final(t)
            self.draw_basket(dr, bxk, byk, thk, BASK_H, S)
        self.reflect(img, S)
        self.draw_sub(dr, t, S)

    def draw_bounce(self, img, dr, bx, by, sx, sy, t, S):
        # le visage : choc tenu 1 s après chaque charge, blasé sous la pile, « win » 1 s après l'issue
        for k in ("P1", "P2", "P3", "P4", "P5"):
            if T_P[k] <= t < T_P[k] + 1.0:
                base.HERO["expr"] = "shock"
        if T_SQUASH + 0.15 <= t < T_RELAUNCH:
            base.HERO["expr"] = "calm"
        if T_TIP + 0.3 <= t < T_WIN:
            base.HERO["expr"] = "calm"
        if t >= T_WIN:
            base.HERO["expr"] = "win"
        if abs(sx - 1) < 0.01 and abs(sy - 1) < 0.01:
            base.HERO["pos"] = None
            base.ball(dr, bx * S, by * S, RB * S)
            return
        r = RB * S
        size = int(2 * 1.6 * r) + 4
        lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        base.HERO["pos"] = None
        base.ball(ld, size / 2, size / 2, r)
        nw, nh = max(1, int(size * sx)), max(1, int(size * sy))
        lay = lay.resize((nw, nh), Image.BILINEAR)
        img.paste(lay, (int(bx * S - nw / 2), int(by * S - nh / 2)), lay)
        base.HERO["pos"] = (bx * S, by * S)

    def draw_floor_decor(self, dr, S):
        # quelques jouets tout en bas, loin de l'action (décor)
        for (x, y, c) in ((170, 1740, (70, 120, 170)), (242, 1752, (200, 160, 60)), (206, 1680, (170, 70, 60))):
            dr.rectangle([(x - 34) * S, (y - 34) * S, (x + 34) * S, (y + 34) * S], fill=c)
            dr.rectangle([(x - 20) * S, (y - 20) * S, (x + 20) * S, (y + 20) * S], fill=dim(c, 0.8))
        dr.rounded_rectangle([760 * S, 1715 * S, 920 * S, 1765 * S], radius=int(14 * S), fill=(60, 140, 120))
        dr.rounded_rectangle([795 * S, 1680 * S, 885 * S, 1720 * S], radius=int(12 * S), fill=(80, 165, 140))
        for x in (795, 885):
            dr.ellipse([(x - 20) * S, 1750 * S, (x + 20) * S, 1790 * S], fill=(30, 30, 36))

    def reflect(self, img, S):
        """parquet ciré : la scène se reflète sous la ligne du sol, de plus en plus pâle."""
        hgt = 520
        src = img.crop((0, int((FLOOR - hgt) * S), int(W * S), int(FLOOR * S))).transpose(Image.FLIP_TOP_BOTTOM)
        dst = img.crop((0, int(FLOOR * S), int(W * S), int((FLOOR + hgt) * S)))
        mask = Image.linear_gradient("L").resize((int(W * S), int(hgt * S))).point(lambda v: int(95 * (1 - v / 255.0)))
        dst.paste(src, (0, 0), mask)
        img.paste(dst, (0, int(FLOOR * S)))

    def draw_mattress(self, dr, t, S):
        x0, x1, top = MAT
        bx, by, sx, sy = self.bounce_at(t)
        bottom = by + RB * sy
        dent = max(0.0, bottom - top) if (x0 - 40 < bx < x1 + 40) else 0.0
        pts = [(x0, FLOOR), (x0, top + 10), (x0 + 12, top)]
        for i in range(41):
            x = lerp(x0 + 12, x1 - 12, i / 40)
            d = dent * math.exp(-((x - bx) / (RB * 0.95)) ** 2) if dent else 0.0
            pts.append((x, top + d))
        pts += [(x1, top + 10), (x1, FLOOR)]
        poly(dr, pts, S, (196, 206, 226))
        dr.rectangle([x0 * S, (FLOOR - 26) * S, x1 * S, FLOOR * S], fill=(150, 160, 186))
        for xx in range(int(x0) + 40, int(x1), 70):
            dr.line([(xx * S, (FLOOR - 26) * S), (xx * S, (FLOOR - 4) * S)], fill=(130, 140, 166), width=int(3 * S))

    def draw_sign(self, dr, t, S, shake):
        x0, x1, y0, y1 = SIGN
        cx = (x0 + x1) / 2
        w, h = x1 - x0, y1 - y0
        if t >= T_SIGNFALL:
            u = clamp(t - T_SIGNFALL, 0, 0.7)
            dy = min(0.5 * G * u * u, FLOOR - 26 - y1)
            y0, y1 = y0 + dy, y1 + dy
        # clou et ficelle
        if t < T_SIGNFALL:
            dr.line([(cx * S, (y0 - 40) * S), ((x0 + 40) * S, y0 * S)], fill=(150, 150, 160), width=int(4 * S))
            dr.line([(cx * S, (y0 - 40) * S), ((x1 - 40) * S, y0 * S)], fill=(150, 150, 160), width=int(4 * S))
            dr.ellipse([(cx - 7) * S, (y0 - 47) * S, (cx + 7) * S, (y0 - 33) * S], fill=(190, 190, 200))
        if t < 2.10:
            th = 0.0
            if t >= 0.40:
                th = 0.17 * (1 - math.exp(-(t - 0.40) * 6)) + 0.03 * math.sin((t - 0.4) * 9) * math.exp(-(t - 0.4) * 2)
            th += shake * 0.004
            pts = rect_pts(cx, (y0 + y1) / 2, w, h, th)
            poly(dr, pts, S, (120, 92, 64), outline=(80, 60, 42), width=int(5 * S))
            return
        s = clamp((t - 2.10) / 0.35)
        if s < 1:
            k = abs(math.cos(math.pi * s))
            ww = max(4.0, w * k)
            col = (120, 92, 64) if s < 0.5 else (236, 230, 214)
            dr.rectangle([(cx - ww / 2) * S, y0 * S, (cx + ww / 2) * S, y1 * S], fill=col)
            return
        dr.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=(236, 230, 214), outline=(170, 40, 40), width=int(8 * S))
        dr.text((cx * S, ((y0 + y1) / 2) * S), "NO BOUNCING", fill=(200, 30, 30), anchor="mm", font=font(int(52 * S)))

    def draw_book(self, dr, cx, cy, th, i, S, open_=False):
        poly(dr, rect_pts(cx, cy, BOOK_W, BOOK_H, th), S, BOOKC[i % 4])
        a, b = rot(0, BOOK_H / 2 - 7, th)
        p = rect_pts(cx + a, cy + b, BOOK_W - 14, 8, th)
        poly(dr, p, S, (236, 232, 220))

    def draw_basket(self, dr, cx, cy, th, hb, S, back=False):
        """panier à linge retourné : bande du haut, 4 barreaux fins loin du visage, bord du bas."""
        if back:
            for u in (-115, 0, 115):
                a0 = rot(u, -hb / 2 + 18, th); a1 = rot(u, hb / 2 - 20, th)
                dr.line([((cx + a0[0]) * S, (cy + a0[1]) * S), ((cx + a1[0]) * S, (cy + a1[1]) * S)],
                        fill=dim(BASKET_C, 0.45), width=int(4 * S))
            return
        poly(dr, rect_pts(*rot_c(cx, cy, 0, -hb / 2 + 9, th), BASK_W, 18, th), S, BASKET_C)
        poly(dr, rect_pts(*rot_c(cx, cy, 0, hb / 2 - 10, th), BASK_W + 10, 20, th), S, BASKET_C)
        for u in (-147, -82, 82, 147):
            a0 = rot(u, -hb / 2 + 18, th); a1 = rot(u, hb / 2 - 20, th)
            dr.line([((cx + a0[0]) * S, (cy + a0[1]) * S), ((cx + a1[0]) * S, (cy + a1[1]) * S)],
                    fill=BASKET_C, width=int(5 * S))

    def draw_bricks(self, dr, cx, cy, th, S):
        for u in (-BRICK_W / 4, BRICK_W / 4):
            a, b = rot(u, 0, th)
            poly(dr, rect_pts(cx + a, cy + b, BRICK_W / 2 - 6, BRICK_H, th), S, BRICK_C, outline=(120, 50, 36), width=int(3 * S))

    def draw_ton(self, dr, cx, cy, th, S):
        pts = []
        for u, v in ((-TON_W / 2, TON_H / 2), (TON_W / 2, TON_H / 2), (TON_W / 2 - 30, -TON_H / 2 + 20),
                     (-TON_W / 2 + 30, -TON_H / 2 + 20)):
            a, b = rot(u, v, th)
            pts.append((cx + a, cy + b))
        poly(dr, pts, S, IRON)
        poly(dr, rect_pts(*rot_c(cx, cy, 0, -TON_H / 2 + 10, th), 70, 20, th), S, IRON)
        a, b = rot(0, 18, th)
        dr.text(((cx + a) * S, (cy + b) * S), "1 TON", fill=(232, 232, 238), anchor="mm", font=font(int(44 * S)))

    def draw_carry(self, dr, carry, gx, gtop, t, S):
        """la charge en équilibre sur la tête de Grounded."""
        if carry == "book1":
            self.draw_book(dr, gx, gtop - BOOK_H / 2, 0.0, 0, S)
        elif carry == "books3":
            for i in range(3):
                self.draw_book(dr, gx + 6 * (i - 1), gtop - BOOK_H / 2 - i * BOOK_H, 0.03 * (i - 1), i + 1, S)
        elif carry == "flung":
            self.draw_book(dr, gx, gtop - BOOK_H / 2, 0.08 * math.sin(t * 9), 3, S)
        elif carry == "basket":
            self.draw_basket(dr, gx, gtop - 170 / 2 + 50, 0.0, 170, S, back=True)
            self.draw_basket(dr, gx, gtop - 170 / 2 + 50, 0.0, 170, S)
        elif carry == "bricks":
            self.draw_bricks(dr, gx, gtop - BRICK_H / 2, 0.0, S)
        elif carry == "ton":
            self.draw_ton(dr, gx, gtop - TON_H / 2 + 8, 0.0, S)

    def falling_items(self):
        """(nom, t0, t1, départ, arrivée) : chute balistique d'une charge."""
        out = []
        for name, t0, t1 in (("book1", 3.85, 4.45), ("books3", 8.75, 9.40), ("basket", 16.70, 17.20),
                             ("bricks", 22.85, 23.40), ("ton", 29.85, 30.40)):
            out.append((name, t0, t1))
        return out

    def draw_falling(self, dr, t, S):
        for name, t0, t1 in self.falling_items():
            if not (t0 <= t < t1):
                continue
            gx, gy, _, gsq, _ = self.grounded_at(t0 - 0.001)
            sx0, sy0 = gx + 70, gy - RG - 40
            lay = self.stack_layout(t1 + 0.001)
            if name == "book1":
                tx, ty, _ = lay["book0"]
            elif name == "books3":
                tx, ty = lay["book2"][0], lay["book2"][1]
            elif name == "basket":
                tx, ty = lay["basket"][0], lay["basket"][1]
                sy0 = gy - RG - 170 / 2 + 50
            elif name == "bricks":
                tx, ty, _ = lay["bricks"]
            else:
                tx, ty, _ = lay["ton"]
            T = t1 - t0
            u = t - t0
            vy = (ty - sy0) / T - 0.5 * G * T
            x, y = lerp(sx0, tx, u / T), sy0 + vy * u + 0.5 * G * u * u
            spin = 0.6 * math.sin(math.pi * u / T) if name.startswith("book") else 0.15 * math.sin(math.pi * u / T)
            if name == "book1":
                self.draw_book(dr, x, y, spin, 0, S)
            elif name == "books3":
                for i in range(3):
                    self.draw_book(dr, x + 6 * (i - 1), y - (i - 1) * BOOK_H, spin * (1 + 0.3 * i), i + 1, S)
            elif name == "basket":
                hbf = lerp(170, BASK_H, u / T)
                self.draw_basket(dr, x, y, spin, hbf, S, back=True)
                self.draw_basket(dr, x, y, spin, hbf, S)
            elif name == "bricks":
                self.draw_bricks(dr, x, y, spin, S)
            else:
                self.draw_ton(dr, x, y, spin, S)
        # le livre renvoyé à Grounded (10,75 -> 11,30), puis jeté (12,30 ->)
        if T_FLING <= t < T_FLING_LAND:
            lay = self.stack_layout(T_FLING - 0.001)
            sx0, sy0, _ = lay["book3"]
            gx, gy = GTOP
            tx, ty = gx, gy - RG - BOOK_H / 2
            T = T_FLING_LAND - T_FLING
            u = t - T_FLING
            vy = (ty - sy0) / T - 0.5 * G * T
            self.draw_book(dr, lerp(sx0, tx, u / T), sy0 + vy * u + 0.5 * G * u * u, 6.283 * u / T, 3, S)
        if 12.30 <= t < 12.9:
            u = t - 12.30
            gx, gy = GTOP
            self.draw_book(dr, gx - 520 * u, gy - RG - 20 - 700 * u + 0.5 * G * u * u, -8 * u, 3, S)
        # quand le panier arrive, les livres s'envolent hors du cadre
        if T_P["P3"] <= t < T_P["P3"] + 1.2:
            lay = self.stack_layout(T_P["P3"] - 0.001)
            u = t - T_P["P3"]
            for i, (vx, vy0) in enumerate(((-620, -600), (-420, -700), (560, -650), (760, -500))):
                k = f"book{i}"
                if k not in lay:
                    continue
                x0, y0, _ = lay[k]
                self.draw_book(dr, x0 + vx * u, y0 + vy0 * u + 0.5 * G * u * u, (5 if vx > 0 else -5) * u, i, S)

    def tip_paths(self, t):
        """la bascule : positions des briques, du poids et du panier entre T_TIP et l'issue."""
        lay = self.stack_layout(T_TIP - 0.001)
        out = {}
        u = t - T_TIP
        for name, tx, ty, T in (("ton", 60.0, FLOOR - TON_H / 2, 0.36), ("bricks", 60.0, FLOOR - TON_H - BRICK_H / 2, 0.44)):
            x0, y0, th0 = lay[name]
            uu = clamp(u, 0, T)
            vy = (ty - y0) / T - 0.5 * G * T
            out[name] = (lerp(x0, tx, uu / T), y0 + vy * uu + 0.5 * G * uu * uu, th0 * (1 - uu / T))
        out["basket"] = self.basket_final(t)
        return out

    def basket_final(self, t):
        """le panier lancé vers le haut par le dernier rebond : Bounce retombe par l'ouverture (le bord
        lui frôle la tête), puis le panier se rabat sur Grounded."""
        lay = self.stack_layout(T_TIP - 0.001)
        x0, y0, th0, _ = lay["basket"]
        ty = FLOOR - BASK_H / 2
        T = T_ISSUE - T_TIP
        u = clamp(t - T_TIP, 0, T)
        vy = (ty - y0) / T - 0.5 * G * T
        y = y0 + vy * u + 0.5 * G * u * u
        th = th0 * (1 - ease(u / (T * 0.8)))
        T_OUT = self.t_out()
        if t <= T_OUT:
            x = self.bounce_raw(t)[0]
        else:
            xo = self.bounce_raw(T_OUT)[0]
            q = clamp((t - T_OUT) / (T_ISSUE - 0.12 - T_OUT))
            x = lerp(xo, G_FINAL_X, 1 - (1 - q) ** 2.2)
        return x, y, th

    def t_out(self):
        if getattr(self, "_t_out", None) is None:
            lay = self.stack_layout(T_TIP - 0.001)
            x0, y0, th0, _ = lay["basket"]
            ty = FLOOR - BASK_H / 2
            T = T_ISSUE - T_TIP
            vy = (ty - y0) / T - 0.5 * G * T
            self._t_out = T_ISSUE
            for i in range(1, 600):
                t = T_TIP + i / 600
                u = t - T_TIP
                y = y0 + vy * u + 0.5 * G * u * u
                th = th0 * (1 - ease(u / (T * 0.8)))
                rim = max(y + rot(a, b, th)[1] for a, b in ((-150, 120), (150, 120)))
                bx, by = self.bounce_raw(t)
                if rim < by - RB - 22:
                    self._t_out = t
                    break
        return self._t_out

    def draw_tip(self, dr, t, S):
        p = self.tip_paths(t)
        self.draw_ton(dr, *p["ton"], S)
        self.draw_bricks(dr, *p["bricks"], S)
        if t < T_ISSUE - 0.02:
            bx, by, th = p["basket"]
            self.draw_basket(dr, bx, by, th, BASK_H, S, back=True)
            self.draw_basket(dr, bx, by, th, BASK_H, S)

    def draw_fallen(self, dr, t, S):
        pass

    def draw_sub(self, dr, t, S):
        for n in self.narr:
            txt = self.subs.get(n["key"])
            if not txt:
                continue
            dur = max(n["end"] - n["start"] + 0.2, 0.5 + 0.3 * len(txt.split()))
            if n["start"] <= t <= n["start"] + dur:
                f = font(int(56 * S))
                dr.text((540 * S, 1226 * S), txt, fill=(255, 255, 255), anchor="mm", font=f,
                        stroke_width=max(2, int(56 * S * 0.09)), stroke_fill=(0, 0, 0))


def C_x(C, t):
    for c in C:
        if abs(c[0] - t) < 1e-6:
            return c[2]
    return 500.0


def rot_c(cx, cy, u, v, th):
    a, b = rot(u, v, th)
    return cx + a, cy + b


def draw_grounded(dr, x, y, r, S, mood="furieux", talk=0.0, sq=0.0, rot=0.0):
    """Grounded, d'après le dessin du fan : halo rose pâle, disque rose, traits blancs."""
    sx, sy = 1 + sq, 1 - sq
    yc = y + r * sq
    dr.ellipse([(x - 1.6 * r * sx) * S, (yc - 1.6 * r * sy) * S, (x + 1.6 * r * sx) * S, (yc + 1.6 * r * sy) * S],
               fill=dim(G_HALO, 0.42))
    dr.ellipse([(x - r * sx) * S, (yc - r * sy) * S, (x + r * sx) * S, (yc + r * sy) * S], fill=G_HALO)
    rr = 0.74 * r
    dr.ellipse([(x - rr * sx) * S, (yc - rr * sy) * S, (x + rr * sx) * S, (yc + rr * sy) * S], fill=G_DISC)
    ca, sa = math.cos(rot), math.sin(rot)

    def P(u, v):
        return ((x + (u * ca - v * sa) * r * sx) * S, (yc + (u * sa + v * ca) * r * sy) * S)
    w = max(2, int(0.075 * r * S))
    o = 0.10 * talk
    if mood == "las":
        dr.line([P(-0.44, -0.24), P(-0.14, -0.20)], fill=G_INK, width=w); dr.line([P(0.14, -0.20), P(0.44, -0.24)], fill=G_INK, width=w)
        for ex in (-0.28, 0.28):
            dr.line([P(ex - 0.1, -0.04), P(ex + 0.1, -0.04)], fill=G_INK, width=w)
        dr.line([P(-0.18, 0.36), P(0.18, 0.36)], fill=G_INK, width=w)
        return
    if mood == "satisfait":
        dr.line([P(-0.46, -0.36), P(-0.14, -0.24)], fill=G_INK, width=w)
        dr.line([P(0.14, -0.24), P(0.46, -0.36)], fill=G_INK, width=w)
        for ex in (-0.28, 0.28):
            dr.chord([*P(ex - 0.13, -0.16), *P(ex + 0.13, 0.06)], 0, 180, fill=G_INK)
        dr.line([P(-0.24, 0.36), P(0.0, 0.42), P(0.24, 0.34)], fill=G_INK, width=w, joint="curve")
        return
    if mood in ("stupefait", "panique"):
        dr.line([P(-0.46, -0.50), P(-0.14, -0.54)], fill=G_INK, width=w)
        dr.line([P(0.14, -0.54), P(0.46, -0.50)], fill=G_INK, width=w)
        for ex in (-0.28, 0.28):
            rr2 = 0.15
            dr.ellipse([*P(ex - rr2, -0.10 - rr2), *P(ex + rr2, -0.10 + rr2)], fill=G_INK)
        dr.ellipse([*P(-0.12, 0.24), *P(0.12, 0.50 + o)], fill=G_INK)
        return
    # furieux
    dr.line([P(-0.48, -0.42), P(-0.14, -0.26)], fill=G_INK, width=w)
    dr.line([P(0.14, -0.26), P(0.48, -0.42)], fill=G_INK, width=w)
    for ex in (-0.28, 0.28):
        rr2 = 0.11
        dr.ellipse([*P(ex - rr2, -0.10 - rr2), *P(ex + rr2, -0.10 + rr2)], fill=G_INK)
    dr.line([P(-0.26, 0.46), P(-0.1, 0.32 - o), P(0.12, 0.30 - o), P(0.28, 0.44)], fill=G_INK, width=w, joint="curve")


DEFAULTS = {"fps": 60, "min_duration_s": 8.0, "max_duration_s": 75.0, "end_hold_s": 0.0,
            "hook_text_s": 0.0, "hook_top": 0.125, "hook_font_size": 96}

if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
