"""
Prototype « le nouveau » : une vidéo courte, en réponse au commentaire d'un fan qui a
dessiné son propre personnage dans le style de Bounce. Le personnage n'a pas encore de nom :
la vidéo le présente et demande aux gens de le nommer en commentaire.

Une scène unique. Le personnage du fan est posé au sol, sous une lumière, et ne dit rien :
il ne réagit qu'avec le visage (il suit Bounce des yeux, grimace quand Bounce lui tombe sur
la tête, finit par regarder la caméra). Bounce rebondit autour de lui et sur lui sans jamais
s'arrêter. Le narrateur le présente en trois phrases.

Tout est calculé d'avance sur une horloge : les points de contact de Bounce (sol ou tête du
personnage) et des arcs paraboliques qui les relient.

    python3 src/stories/nameoc.py configs/<name>.json [--simulate]
"""
import math, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim

# la voix de Bounce ne rend pas « Bounce » deux fois à la même longueur : on garde un tirage
# court (<= 0,78 s), une fois par processus, pour que chaque mot tienne entre deux phrases.
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
            if len(v) / base.ak.SR <= 0.78:
                break
        _hero_memo[key] = best
    v = _hero_memo[key]
    return None if v is None else v.copy()


base.hero_word = steady_hero_word

DEFAULTS = {
    "fps": 60,
    "min_duration_s": 8.0,
    "end_hold_s": 0.0,
    "hook_text_s": 2.4,
    "narrator_length": 1.05,
    "sub_y": 0.83,
    "sub_font_size": 60,
    "oc_x": 540.0, "oc_r": 115.0,
    "floor_y": 1360.0,
    "bounce_r": 110.0,
    # les contacts de Bounce : (t, "floor"|"head", x) ; il entre en l'air depuis la gauche.
    # Ceux qui tombent pendant l'accroche ou une phrase du narrateur restent muets (base) :
    # les autres sont calés entre les phrases pour que chaque « Bounce » s'entende.
    "contacts": [
        [0.75, "floor", 150.0],
        [1.45, "head", 540.0],
        [2.45, "floor", 930.0],
        [3.62, "head", 560.0],
        [4.60, "floor", 150.0],
        [5.97, "head", 520.0],
        [6.95, "floor", 930.0],
        [8.05, "floor", 700.0],
        [9.30, "head", 545.0],
        [10.40, "floor", 150.0],
        [11.50, "head", 540.0],
        [12.60, "floor", 930.0],
        [13.70, "floor", 240.0],
    ],
    "end_s": 14.9,
    # les répliques du narrateur : (déclencheur, texte)
    "lines": [
        [2.35, "This is the new guy."],
        [4.50, "He doesn't have a name yet."],
        [7.90, "Name him in the comments."],
    ],
    "look_camera_s": 7.9,
}

# le personnage du fan, d'après son dessin
OC_OUT = (152, 166, 56)
OC_IN = (238, 250, 178)
OC_INK = (14, 14, 12)
HAT_FILL = (142, 146, 244)
HAT_LINE = (84, 86, 214)
BOW_FILL = (234, 246, 176)
BOW_LINE = (92, 98, 34)
FLOOR_COL = (40, 40, 54)
LIGHT_COL = (26, 26, 36)


def lerp(a, b, s):
    return a + (b - a) * s


def ease(s):
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


class Sim:
    scene_top = 0.24

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.t = 0.0
        self.done = False
        self.payoff = False
        R, rb, fy = cfg["oc_r"], cfg["bounce_r"], cfg["floor_y"]
        self.ocy = fy - R
        pts = [(-0.35, -60.0, 700.0)]          # entrée : en l'air, hors champ à gauche
        for (t, kind, x) in cfg["contacts"]:
            y = (self.ocy - R - rb + 4) if kind == "head" else (fy - rb)
            pts.append((t, x, y, kind))
        self.pts = pts
        self.contacts = [(p[0], p[3]) for p in pts[1:]]
        self.ci = 0
        self.lines = [(t, txt, f"l{i}") for i, (t, txt) in enumerate(cfg["lines"])]
        self.head_hits = [t for (t, k) in self.contacts if k == "head"]

    # ---- la trajectoire de Bounce
    def bounce_at(self, t):
        pts = self.pts
        if t <= pts[0][0]:
            return pts[0][1], pts[0][2]
        for a, b in zip(pts, pts[1:]):
            if a[0] <= t <= b[0]:
                s = (t - a[0]) / (b[0] - a[0])
                d = b[0] - a[0]
                h = 0.5 * 2600.0 * (d / 2) ** 2      # une seule gravité : hauteur ~ durée²
                h = min(h, 620.0)
                x = lerp(a[1], b[1], s)
                y = lerp(a[2], b[2], s) - 4 * h * s * (1 - s)
                return x, y
        # après le dernier contact : il repart vers le haut
        a = pts[-1]
        s = (t - a[0]) / 1.1
        x = a[1] + (a[1] - pts[-2][1]) * 0.03 * s
        y = a[2] - 4 * 520 * s * (1 - s)
        return x, y

    def step(self, dt):
        evs = []
        self.t += dt
        while self.ci < len(self.contacts) and self.contacts[self.ci][0] <= self.t:
            evs.append(("hit", self.contacts[self.ci][1]))
            self.ci += 1
        if self.t >= self.cfg["end_s"] and not self.payoff:
            self.payoff = True
            self.done = True
            evs.append(("payoff", "fin"))
        return evs

    def snapshot(self):
        return self.t

    def counter(self, snap):
        return None

    # ---- le personnage du fan
    def oc_state(self, t):
        """Écrasement, grimace et regard du personnage à l'instant t."""
        squash, wince = 0.0, 0.0
        for th in self.head_hits:
            dt = t - th
            if 0 <= dt < 0.6:
                squash = max(squash, 0.16 * math.exp(-dt * 7) * math.cos(dt * 22))
                wince = max(wince, 1.0 if dt < 0.28 else (0.6 - dt) / 0.32)
        bx, by = self.bounce_at(t)
        cx, cy = self.cfg["oc_x"], self.ocy
        dx, dy = bx - cx, by - (cy - 40)
        n = math.hypot(dx, dy) or 1.0
        gx, gy = dx / n, dy / n
        k = ease((t - self.cfg["look_camera_s"]) / 0.35)
        gx, gy = lerp(gx, 0.0, k), lerp(gy, 0.15, k)
        annoy = min(1.0, max(0.0, (t - 1.7) / 7.0))
        return squash, wince, (gx, gy), annoy, k

    def draw_oc(self, dr, t, S):
        """Le perso du fan aux proportions de nos persos (comme Bounce : un disque, un halo,
        un visage au trait noir), avec ses couleurs : disque clair, halo olive ; son bandeau
        bleu et son nœud ; ses yeux mi-clos sous des sourcils qui tombent vers la droite."""
        cfg = self.cfg
        R = cfg["oc_r"]
        squash, wince, (gx, gy), annoy, cam = self.oc_state(t)
        sx, sy = 1 + squash, 1 - squash
        cx = cfg["oc_x"]
        fy = cfg["floor_y"]
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

        # le regard : seules les pupilles bougent, sous la paupière
        px, pv = gx * 0.05, max(-0.01, min(0.03, gy * 0.03))
        lo = 0.05 * annoy + 0.06 * wince
        # sourcils : plats et lourds, qui tombent vers la droite ; plus bas quand il s'agace
        stroke([(-0.60, -0.50 + lo * 0.4), (-0.18, -0.40 + lo)], 0.12)
        stroke([(0.14, -0.44 + lo), (0.60, -0.30 + lo * 0.4)], 0.12)
        if wince > 0.5:
            stroke([(-0.52, -0.14), (-0.20, -0.12)], 0.10)
            stroke([(0.16, -0.10), (0.50, -0.07)], 0.10)
        else:
            # les yeux mi-clos : la moitié basse d'une pupille noire, coupée par une paupière droite ;
            # le gauche allongé avec un cil vers l'extérieur, le droit plus grand qui coule en bas
            for (eu, ev, ru, rv) in ((-0.36, -0.16, 0.17, 0.13), (0.33, -0.12, 0.17, 0.15)):
                poly([(eu - ru, ev)] + ell(eu + px, ev + pv * 0.5, ru, rv, 24, 0.0, math.pi)[::-1] + [(eu + ru, ev)], fill=OC_INK)
                stroke([(eu - ru - 0.02, ev), (eu + ru + 0.02, ev)], 0.07)
            stroke([(-0.53, -0.16), (-0.62, -0.22)], 0.06)
            poly([(0.42, -0.02), (0.52, 0.07), (0.46, 0.10), (0.37, 0.02)], fill=OC_INK)
        # bouche : petit trait en biais ; ondulé pendant la grimace
        if wince > 0.5:
            stroke([(-0.20, 0.42), (-0.10, 0.37), (0.0, 0.43), (0.10, 0.38)], 0.08)
        else:
            stroke([(-0.20, 0.38), (0.10, 0.46)], 0.09)

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

    def draw(self, dr, snap, t, S):
        cfg = self.cfg
        W, H = cfg["width"], cfg["height"]
        fy = cfg["floor_y"]
        # la lumière : un cône pâle sur le personnage, un ovale au sol
        cx = cfg["oc_x"]
        dr.polygon([((cx - 70) * S, 0), ((cx + 70) * S, 0), ((cx + 330) * S, fy * S), ((cx - 330) * S, fy * S)], fill=LIGHT_COL)
        dr.rectangle([0, fy * S, W * S, H * S], fill=(12, 12, 18))
        dr.ellipse([(cx - 360) * S, (fy - 40) * S, (cx + 360) * S, (fy + 60) * S], fill=(30, 30, 42))
        dr.line([(0, fy * S), (W * S, fy * S)], fill=FLOOR_COL, width=int(6 * S))
        # Bounce passe derrière le personnage quand il est plus haut que sa tête et de l'autre côté
        bx, by = self.bounce_at(t)
        rb = cfg["bounce_r"]
        self.draw_oc(dr, t, S)
        base.ball(dr, bx * S, by * S, rb * S)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
