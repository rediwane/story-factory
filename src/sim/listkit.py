"""
La boîte à outils des vidéos « liste » : la classe de base d'un chapitre et le contrat
qu'il doit remplir pour que le contrôle automatique (src/tools/controle.py) puisse le
juger sans le regarder.

Un chapitre hérite de `Chapter` et écrit :
- `setup()` : sa mise en place (Bounce, décor, objets), et ses répliques par `line()` ;
- `on_land(k, evs)` : ce que fait une retombée de Bounce (k = hauteur relative) ;
- `after(dt, evs)` : la physique de ses objets, et `finish(outcome)` au moment de la chute ;
- `snapshot()` : l'état à dessiner (partir de `base_snap()`) ;
- `draw(dr, s, t, S)` : le dessin, coordonnées multipliées par S ;
- `solids(s)` : **tous les objets que Bounce pourrait toucher**, dans l'état `s`, en
  formes simples : ("rect", x0, y0, x1, y1), ("circle", x, y, r), ("poly", [(x, y), ...]).
  Le contrôle refuse toute image où Bounce entre dans l'un d'eux. Un objet absent de
  cette liste n'existe pas pour le contrôle : ne pas l'y mettre, c'est s'exposer à ce
  qu'il le traverse à l'image ;
- `hero(s)` (facultatif) : (x, y, r) de Bounce, ou None s'il est volontairement caché ;
- `focus(s)` : le rectangle (x0, y0, x1, y1) de **ce qui montre la chute** (l'objet qui
  tombe, le tirage, la toile...), dans l'état `s`. Le contrôle exige qu'il soit dans le
  cadre, hors des zones que l'interface TikTok recouvre (`ZONES_UI`) et hors du tampon,
  de la chute à la fin du chapitre ;
- `bodies(s)` : tous les objets qui bougent, en [(id, x, y, angle)] ou
  [(id, x, y, angle, polygone)], id stable d'une image à l'autre. Le contrôle refuse un
  objet qui se téléporte, qui pivote d'un coup, ou qui sort du cadre (sauf
  `bodies_exit_ok`, quand partir hors champ est la chute). Le polygone (sommets convexes,
  coordonnées de l'image) se donne pour un objet **libre** (qui vole, tombe, glisse) : deux
  objets libres ne doivent jamais s'interpénétrer (`separate()` les écarte) ;
- attributs : `title` (en haut pendant le chapitre), `stamp` (texte, couleur) à la chute,
  `stamp_y` (hauteur du tampon, en fraction de l'image), `mood` ("win"/"lose"),
  `hold_s` (tenue après la chute), `exit_ok` (vrai seulement si sortir du cadre est le gag).

Pour dessiner une lumière, `glow()` : un halo mélangé vers la lumière à partir de la couleur
du fond. Jamais `dim(lumière, petit facteur)`, qui donne un disque plus sombre que le mur.
"""
import math
import base
from base import dim, circle
from chapters import Hopper

RED = (226, 54, 66)
GREEN = (90, 210, 130)
AMBER = (240, 190, 70)
FLOOR_Y = 1500.0
SCENE_TOP = 430.0
# ce que l'interface TikTok recouvre sur 1080x1920 : la colonne des boutons à droite, la
# légende et le nom du compte en bas. La chute ne s'y joue jamais.
ZONES_UI = ((940.0, 820.0, 1080.0, 1700.0), (0.0, 1650.0, 1080.0, 1920.0))
HOP = dict(start_h=300.0, gain=(0.9, 1.15), min_h=220.0, max_h=520.0, h_ref=300.0)


class Chapter(Hopper):
    title = None
    stamp = None
    stamp_y = 0.52
    mood = None
    hold_s = 1.2
    exit_ok = False
    bodies_exit_ok = False

    def __init__(self, cfg, rng):
        self.cfg, self.rng = cfg, rng
        self.W, self.H = cfg["width"], cfg["height"]
        self.R, self.g = cfg["ball_r"], cfg["gravity"]
        self.t = 0.0
        self.lines, self.replies = [], []
        self.done = self.payoff = False
        self.outcome = None
        self.end_t = None
        self.setup()

    # --- à écrire par le chapitre
    def setup(self):
        pass

    def on_land(self, k, evs):
        pass

    def after(self, dt, evs):
        pass

    def solids(self, s):
        return []

    def focus(self, s):
        return None

    def bodies(self, s):
        return []

    def hero(self, s):
        if s.get("on") in ("gone", "hidden"):
            return None
        return (s["bx"], s["by"], self.R * s.get("scale", 1.0))

    # --- commun
    def line(self, text, key, when=None):
        self.lines.append((self.t if when is None else when, text, key))

    def reply(self, key, delay=0.35):
        """Bounce répond « Bounce » après la réplique `key` du narrateur."""
        self.replies.append((key, delay))

    def finish(self, outcome):
        if self.payoff:
            return
        self.payoff, self.outcome, self.end_t = True, outcome, self.t

    def counter(self, s):
        return None if s.get("end") is not None else self.title

    def step(self, dt):
        self.t += dt
        evs = []
        self.hop_step(dt, evs)
        self.after(dt, evs)
        return evs

    def settle(self):
        """Après la chute : Bounce se pose au prochain contact et reste là."""
        if self.payoff and self.on == "air" and self.vy > 0 and self.by >= self.floor_y - self.R - 2:
            self.on = "still"; self.by = self.floor_y - self.R

    def base_snap(self):
        return {"t": self.t, "bx": self.bx, "by": self.by, "end": self.end_t, "hit_t": self.hit_t, "on": self.on}

    # --- décor commun
    def figure(self, dr, P, x, y_floor, col, h=260, w=96, tilt=0.0):
        """Un personnage sans visage : tronc, tête, deux jambes. (x, y_floor) = pieds."""
        dr.rectangle([P(x - w / 2), P(y_floor - h), P(x + w / 2), P(y_floor - 12)], fill=col)
        dr.rectangle([P(x - w / 2), P(y_floor - 12), P(x - 10), P(y_floor)], fill=dim(col, 0.7))
        dr.rectangle([P(x + 10), P(y_floor - 12), P(x + w / 2), P(y_floor)], fill=dim(col, 0.7))
        circle(dr, P(x + tilt * 24), P(y_floor - h - 46), P(42), col)

    def figure_box(self, x, y_floor, h=260, w=96):
        """La forme d'un personnage pour solids()."""
        return [("rect", x - w / 2, y_floor - h, x + w / 2, y_floor), ("circle", x, y_floor - h - 46, 42)]

    def room(self, dr, P, wall, floor, top=SCENE_TOP, floor_y=FLOOR_Y, skirting=True):
        W, H = self.W, self.H
        dr.rectangle([0, P(top), P(W), P(floor_y)], fill=wall)
        dr.rectangle([0, P(floor_y), P(W), P(H)], fill=floor)
        if skirting:
            dr.rectangle([0, P(floor_y - 26), P(W), P(floor_y)], fill=dim(wall, 0.75))
        dr.rectangle([0, P(floor_y), P(W), P(floor_y + 8)], fill=dim(floor, 1.35))

    def bounce(self, dr, P, s):
        base.ball(dr, P(s["bx"]), P(s["by"]), P(self.R * s.get("scale", 1.0)))


def settle_body(c, gy, flat_step, dt, corners, rest_ok=True):
    """Pose un corps rigide c = {x, y, a, vx, vy, w, rest} sur le sol gy. `corners` : les
    sommets de sa forme réelle, en coordonnées locales (dx, dy), saillies comprises
    (cheminée, roues...) : le point bas se calcule sur eux, rien ne s'enfonce. Le corps
    rebondit un peu, puis glisse et se couche progressivement sur le côté le plus proche
    (multiple de `flat_step`), jamais d'un coup. Renvoie vrai s'il touche le sol."""
    def low(a):
        ca, sa = math.cos(a), math.sin(a)
        return max(dx * sa + dy * ca for dx, dy in corners)
    if c["y"] + low(c["a"]) < gy - 1:
        return False
    if c["vy"] > 320:
        c["vy"] = -0.28 * c["vy"]; c["w"] *= 0.5; c["vx"] *= 0.7
        c["y"] = gy - low(c["a"])
        return False
    c["vy"] = 0.0
    c["w"] = 0.0
    target = round(c["a"] / flat_step) * flat_step
    da = target - c["a"]
    stepa = 7.0 * dt
    c["a"] += max(-stepa, min(stepa, da))
    c["y"] = gy - low(c["a"])
    c["vx"] *= max(0.0, 1 - 6.0 * dt)
    if rest_ok and abs(target - c["a"]) < 1e-3 and abs(c["vx"]) < 8:
        c["rest"] = True
    return True


def body_poly(c, corners):
    """Le polygone d'un corps rigide c = {x, y, a} dont la forme est `corners` (local)."""
    ca, sa = math.cos(c["a"]), math.sin(c["a"])
    return [(c["x"] + dx * ca - dy * sa, c["y"] + dx * sa + dy * ca) for dx, dy in corners]


def sat_mtv(p1, p2):
    """Interpénétration de deux polygones convexes : (profondeur, nx, ny), la normale allant
    de p1 vers p2 ; (0, 0, 0) s'ils ne se touchent pas."""
    best, bn = 1e18, (0.0, 0.0)
    c1 = (sum(x for x, y in p1) / len(p1), sum(y for x, y in p1) / len(p1))
    c2 = (sum(x for x, y in p2) / len(p2), sum(y for x, y in p2) / len(p2))
    for poly in (p1, p2):
        n = len(poly)
        for i in range(n):
            (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
            nx, ny = -(by - ay), bx - ax
            L = math.hypot(nx, ny) or 1e-9
            nx, ny = nx / L, ny / L
            a = [x * nx + y * ny for x, y in p1]
            b = [x * nx + y * ny for x, y in p2]
            o = min(max(a), max(b)) - max(min(a), min(b))
            if o <= 0:
                return 0.0, 0.0, 0.0
            if o < best:
                best, bn = o, (nx, ny)
    nx, ny = bn
    if (c2[0] - c1[0]) * nx + (c2[1] - c1[1]) * ny < 0:
        nx, ny = -nx, -ny
    return best, nx, ny


def sat_depth(p1, p2):
    """Profondeur d'interpénétration de deux polygones convexes (0 s'ils ne se touchent pas)."""
    return sat_mtv(p1, p2)[0]


def separate(bodies, shape_of, iters=3, max_step=3.0):
    """Écarte doucement les corps libres qui s'interpénètrent (cartes, wagons, débris) : chaque
    paire en contact est repoussée le long de son axe de contact, d'au plus `max_step` px par
    passe (jamais de saut visible), et les vitesses de rapprochement sont annulées.
    `shape_of(c)` donne les sommets locaux de c ; un corps `rest` ne bouge plus."""
    for _ in range(iters):
        moved = False
        polys = [body_poly(c, shape_of(c)) for c in bodies]
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                c1, c2 = bodies[i], bodies[j]
                if c1.get("rest") and c2.get("rest"):
                    continue
                d, nx, ny = sat_mtv(polys[i], polys[j])
                if d <= 0.5:
                    continue
                m1 = 0.0 if c1.get("rest") else 1.0
                m2 = 0.0 if c2.get("rest") else 1.0
                tot = m1 + m2
                k = min(d, max_step)
                c1["x"] -= nx * k * m1 / tot; c1["y"] -= ny * k * m1 / tot
                c2["x"] += nx * k * m2 / tot; c2["y"] += ny * k * m2 / tot
                rel = (c2["vx"] - c1["vx"]) * nx + (c2["vy"] - c1["vy"]) * ny
                if rel < 0:
                    if m1:
                        c1["vx"] += nx * rel * m1 / tot; c1["vy"] += ny * rel * m1 / tot
                    if m2:
                        c2["vx"] -= nx * rel * m2 / tot; c2["vy"] -= ny * rel * m2 / tot
                moved = True
        if not moved:
            break


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def glow(dr, P, x, y, r, light, bg, strength=0.25, rings=4):
    """Un halo de lumière sur le fond `bg` : des anneaux de plus en plus clairs vers le centre."""
    for k in range(rings, 0, -1):
        circle(dr, P(x), P(y), P(r * k / rings), mix(bg, light, strength * (rings + 1 - k) / rings))


# ---------------------------------------------------------------- géométrie du contrôle
def penetration(cx, cy, r, shape):
    """De combien le disque (cx, cy, r) entre dans la forme (px, > 0 = il entre)."""
    kind = shape[0]
    if kind == "rect":
        _, x0, y0, x1, y1 = shape
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        dx = max(x0 - cx, 0, cx - x1)
        dy = max(y0 - cy, 0, cy - y1)
        if dx == 0 and dy == 0:
            inside = min(cx - x0, x1 - cx, cy - y0, y1 - cy)
            return r + inside
        return r - math.hypot(dx, dy)
    if kind == "circle":
        _, x, y, rr = shape
        return r + rr - math.hypot(cx - x, cy - y)
    if kind == "poly":
        pts = shape[1]
        inside = False
        dmin = 1e18
        n = len(pts)
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            if ((ay > cy) != (by > cy)) and cx < (bx - ax) * (cy - ay) / ((by - ay) or 1e-9) + ax:
                inside = not inside
            vx, vy = bx - ax, by - ay
            L = vx * vx + vy * vy or 1e-9
            u = max(0.0, min(1.0, ((cx - ax) * vx + (cy - ay) * vy) / L))
            dmin = min(dmin, math.hypot(ax + u * vx - cx, ay + u * vy - cy))
        return r + dmin if inside else r - dmin
    return -1e9


def disc_rect_overlap(cx, cy, r, x0, y0, x1, y1):
    return penetration(cx, cy, r, ("rect", x0, y0, x1, y1)) > 0
