"""
Prototype « 1000 chats » : Bounce doit traverser des pièces pleines de chats endormis,
de plus en plus nombreux (1, 10, 100, 1000). Il ne peut pas s'empêcher de rebondir ni de
dire son nom, et chaque retombée réveille les chats autour de lui. Un chat réveillé voit
une balle qui rebondit : il se tapit, remue l'arrière-train, et saute dessus.

Les chats sont des dizaines d'agents indépendants (seuil de réveil, délai, saut visé sur
la position de Bounce) : personne ne sait d'avance qui se réveille ni quand.

    python3 src/stories/cats.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, RED, GREEN, AMBER, FLOOR_Y, SCENE_TOP, glow, mix

R_BOUNCE = 52.0
G = 3000.0
SCREEN_CY = 1000.0
EYE = (205, 238, 96)
FURS = [((226, 138, 62), (176, 92, 38)),      # roux tigré
        ((132, 132, 146), (96, 96, 110)),     # gris tigré
        ((30, 30, 38), (30, 30, 38)),         # noir : la nuit, on ne voit que ses yeux
        ((226, 224, 220), (200, 198, 196)),   # blanc
        ((206, 176, 136), (166, 132, 96)),    # crème
        ((96, 74, 62), (66, 50, 42))]         # brun


def ell(x, y, a, b, ang=0.0, n=16):
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for k in range(n):
        u = 2 * math.pi * k / n
        px, py = a * math.cos(u), b * math.sin(u)
        out.append((x + px * ca - py * sa, y + px * sa + py * ca))
    return out


def clamp(v, a, b):
    return max(a, min(b, v))


class CatRoom(Chapter):
    """Une pièce : Bounce part de la gauche et doit atteindre la porte éclairée à droite."""
    title = None
    stamp = None
    stamp_y = 0.27
    mood = None
    hold_s = 1.6
    bodies_exit_ok = True              # la caméra suit Bounce : des chats sortent du cadre

    # réglages par pièce (surchargés par les sous-classes)
    hall_w = 1080.0
    exit_x = 830.0
    start_x = 120.0
    hop_h = (230.0, 320.0)
    hop_len = (140.0, 200.0)
    loud = 0.55
    lam = 260.0
    reach = 520.0
    p_pin = 0.5
    decay = 0.10
    bat_back = 0.4                      # part des coups de patte qui le renvoient en arrière
    bat_v = (300.0, 700.0)
    follow = (1.0,)                     # zoom de la caméra qui suit Bounce
    tilt = None                         # (cy de départ, durée) : panoramique vertical d'ouverture

    def setup(self):
        self.rng = np.random.default_rng(int(self.cfg.get("cat_seed", 1)))
        self.R = R_BOUNCE
        self.bx, self.by = self.start_x, FLOOR_Y - self.R - 200
        self.vx, self.vy = 0.0, 0.0
        self.on = "air"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.pin = None
        self.pile = []
        self.rings = []
        self.events_said = set()
        self.cats = []
        self.build()
        for i, c in enumerate(self.cats):
            c.setdefault("id", i)
            c.setdefault("st", "sleep")
            c.setdefault("w", 0.0)
            c.setdefault("x", c["hx"]); c.setdefault("y", c["hy"]); c.setdefault("sc", c["hsc"])
            c.setdefault("vx", 0.0); c.setdefault("vy", 0.0)
            c.setdefault("f", 1 if self.rng.random() < 0.5 else -1)
            c.setdefault("fur", int(self.rng.integers(len(FURS))))
            c.setdefault("ph", float(self.rng.uniform(0, 6.28)))
            c.setdefault("th", float(self.rng.uniform(0.8, 1.7)))
            c.setdefault("t_st", 0.0)
            c.setdefault("twitch", -9.0)
            c.setdefault("cool", 0.0)
            c.setdefault("lane", False)
        # caméra
        self.cx = self.cam_target()[0]
        self.cvx = 0.0
        self.cam = self.cam_at()
        self.lines_setup()

    # -- à écrire par la pièce
    def build(self):
        pass

    def lines_setup(self):
        pass

    def decor(self, dr, X, Y, Q, s):
        pass

    # ------------------------------------------------------------------ caméra
    def cam_target(self):
        Z = self.follow[0]
        cy = FLOOR_Y - (1440.0 - SCREEN_CY) / Z
        tx = self.bx + 140.0
        lo = 540.0 / Z - 40
        hi = self.exit_x - (640.0 - 540.0) / Z           # la porte jamais sous les boutons
        return clamp(tx, lo, max(lo, hi)), cy, Z

    def cam_at(self):
        tx, ty, Z = self.cam_target()
        k = clamp(self.t / 1.6, 0.0, 1.0)
        push = 0.9 + 0.1 * k * k * (3 - 2 * k)                     # chaque pièce s'ouvre sur un léger travelling avant
        if self.end_t is not None:
            push *= 1.0 + 0.05 * min(7.0, self.t - self.end_t)     # après la chute, la caméra avance doucement
        if self.tilt:
            # l'ouverture : la caméra descend le long du mur de chats jusqu'à Bounce
            cy_top, dur = self.tilt
            k = clamp(self.t / dur, 0.0, 1.0)
            k = k * k * (3 - 2 * k)
            return (self.cx, cy_top * (1 - k) + ty * k, Z * push)
        return (self.cx, ty, Z * push)

    def cam_step(self, dt):
        tx, _, _ = self.cam_target()
        w = 3.2
        a = w * w * (tx - self.cx) - 2 * w * self.cvx
        self.cvx += a * dt
        self.cx += self.cvx * dt

    # ------------------------------------------------------------------ physique
    def step(self, dt):
        self.t += dt
        evs = []
        self.bounce_step(dt, evs)
        self.cats_step(dt, evs)
        self.spread(dt)
        self.cam_step(dt)
        self.cam = self.cam_at()
        self.story(evs)
        return evs

    def land(self, evs, on_cat=None):
        if self.t - self.last_hit >= 0.15:
            self.last_hit = self.t
            self.hits += 1
            evs.append(("hit", "floor"))
        self.hit_t = self.t
        self.rings.append((self.t, self.bx, self.by + self.R))
        h = float(self.rng.uniform(*self.hop_h))
        if on_cat is not None:
            h += 90.0
        self.noise(h, on_cat)
        if self.on == "out":
            # dehors : il rebondit sur place dans la lumière de la porte
            T = 2 * math.sqrt(2 * h / G)
            self.vy = -math.sqrt(2 * G * h)
            self.vx = (self.exit_x + 35 - self.bx) / T
            return
        T = 2 * math.sqrt(2 * h / G)
        L = float(self.rng.uniform(*self.hop_len))
        self.vy = -math.sqrt(2 * G * h)
        self.vx = L / T

    def noise(self, h, on_cat):
        L = self.loud * (0.75 + 0.5 * h / 300.0)
        for c in self.cats:
            if c["st"] != "sleep":
                continue
            d = math.hypot(c["x"] - self.bx, (c["y"] - FLOOR_Y) * 0.75)
            add = L * math.exp(-d / self.lam) * float(self.rng.uniform(0.6, 1.4))
            if c is on_cat:
                add += 3.0
            if add > 0.04:
                c["twitch"] = self.t
            c["w"] += add

    def cat_circles(self, c):
        """Les formes d'un chat pour les contacts : trois cercles le long d'un chat couché."""
        sc, x, y, f = c["sc"], c["x"], c["y"], c.get("f", 1)
        if c["st"] == "sleep":
            return [(x - f * 26 * sc, y - 20 * sc, 21 * sc), (x, y - 24 * sc, 24 * sc), (x + f * 32 * sc, y - 22 * sc, 21 * sc)]
        return [self.cat_circle(c)]

    def cat_circle(self, c):
        """Le corps d'un chat au sol ou en vol, pour les contacts avec Bounce."""
        sc = c["sc"]
        if c["st"] == "leap":
            return c["x"], c["y"] - 22 * sc, 30 * sc
        if c["st"] in ("sit",):
            return c["x"], c["y"] - 34 * sc, 30 * sc
        return c["x"], c["y"] - 22 * sc, 32 * sc

    def bounce_step(self, dt, evs):
        if self.on == "pinned":
            # coincé sous les chats, il ne peut toujours pas s'empêcher de dire son nom
            if self.t - self.last_hit >= 0.95:
                self.last_hit = self.t
                self.hits += 1
                evs.append(("hit", "floor"))
                self.hit_t = self.t
            return
        self.vy += G * dt
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if self.bx < self.R + 10:
            self.bx = self.R + 10; self.vx = abs(self.vx)
        if self.bx > self.hall_w - self.R - 10:
            self.bx = self.hall_w - self.R - 10; self.vx = -abs(self.vx)
        # les chats au sol, sur le passage : il rebondit sur leur dos
        for c in self.cats:
            if not c["lane"] or c["st"] in ("leap", "pin", "pile"):
                continue
            for (x, y, r) in self.cat_circles(c):
                dx, dy = self.bx - x, self.by - y
                d = math.hypot(dx, dy)
                if d < self.R + r and d > 1e-6:
                    nx, ny = dx / d, dy / d
                    self.bx = x + nx * (self.R + r + 0.5)
                    self.by = y + ny * (self.R + r + 0.5)
                    if ny < -0.35 and self.vy > 0:
                        self.land(evs, on_cat=c)
                        self.vy = -abs(self.vy)
                    else:
                        vn = self.vx * nx + self.vy * ny
                        if vn < 0:
                            self.vx -= 1.6 * vn * nx; self.vy -= 1.6 * vn * ny
        if self.vy > 0 and self.by >= FLOOR_Y - self.R:
            self.by = FLOOR_Y - self.R
            self.land(evs)
        if self.on == "air" and self.bx >= self.exit_x and not self.payoff:
            self.on = "out"
            self.finish("SAFE")
            self.on_safe()

    def wake(self, c):
        c["st"] = "sit"
        c["t_st"] = self.t
        c["t_wake"] = self.t
        c["delay"] = float(self.rng.uniform(0.25, 1.1))
        c["f"] = 1 if self.bx >= c["x"] else -1

    def leap(self, c, short=False):
        c["st"] = "leap"
        c["t_st"] = self.t
        c["x0"], c["y0"], c["sc0"] = c["x"], c["y"], c["sc"]
        if self.pin is not None:
            px = self.pin[0] + float(self.rng.uniform(-60, 60))
        else:
            px = self.bx + self.vx * float(self.rng.uniform(0.25, 0.55))
        vy0 = -float(self.rng.uniform(650, 900)) if short or c["lane"] else -float(self.rng.uniform(250, 520))
        drop = FLOOR_Y - c["y"]
        tau = (-vy0 + math.sqrt(vy0 * vy0 + 2 * G * max(0.0, drop))) / G
        c["vy"] = vy0
        c["vx"] = clamp((px - c["x"]) / tau, -1300.0, 1300.0)
        c["tau"] = tau
        c["f"] = 1 if c["vx"] >= 0 else -1

    def cats_step(self, dt, evs):
        t = self.t
        for c in self.cats:
            st = c["st"]
            if st == "sleep":
                c["w"] = max(0.0, c["w"] - self.decay * dt)
                if c.get("lazy"):
                    c["w"] = min(c["w"], 0.95 * c["th"])        # il ouvre un œil, et c'est tout
                elif c["w"] >= c["th"]:
                    self.wake(c)
            elif st == "sit":
                c["f"] = 1 if self.bx >= c["x"] else -1
                near = abs(self.bx - c["x"]) < self.reach and self.on != "out"
                if t - c["t_st"] > c["delay"] and near and t >= c["cool"]:
                    c["st"] = "crouch"; c["t_st"] = t
                    c["dur"] = float(self.rng.uniform(0.45, 0.9))
            elif st == "crouch":
                c["f"] = 1 if self.bx >= c["x"] else -1
                if t - c["t_st"] > c["dur"]:
                    if self.on == "out":
                        c["st"] = "sit"; c["t_st"] = t; c["delay"] = 9.0
                    else:
                        self.leap(c)
                        self.cat_contact(c, evs)
            elif st == "leap":
                c["vy"] += G * dt
                c["x"] += c["vx"] * dt
                c["y"] += c["vy"] * dt
                k = clamp((t - c["t_st"]) / max(0.05, c["tau"]), 0.0, 1.0)
                c["sc"] = c["sc0"] + (1.0 - c["sc0"]) * k
                self.cat_contact(c, evs)
                if c["st"] == "leap" and c["vy"] > 0 and c["y"] >= FLOOR_Y:
                    c["y"] = FLOOR_Y
                    c["sc"] = 1.0
                    c["lane"] = True
                    # en retombant, il réveille ses voisins
                    for o in self.cats:
                        if o["st"] == "sleep" and abs(o["x"] - c["x"]) < 170 and abs(o["y"] - c["y"]) < 260:
                            o["w"] += 0.45; o["twitch"] = t
                    if self.pin is not None and abs(c["x"] - self.pin[0]) < 150 and self.join_ok():
                        self.join_pile(c)
                    else:
                        c["st"] = "hunt"; c["t_st"] = t; c["vx"] = 0.0
                        c["cool"] = t + float(self.rng.uniform(0.3, 0.8))
            elif st == "hunt":
                c["f"] = 1 if self.bx >= c["x"] else -1
                if self.pin is not None:
                    tx = self.pin[0]
                    if self.join_ok() and abs(tx - c["x"]) < 260 and t >= c["cool"]:
                        self.leap(c, short=True)
                        continue
                    if not self.join_ok():
                        dx = tx - c["x"]
                        if abs(dx) > self.R + 90:
                            c["x"] += math.copysign(min(200.0 * dt, abs(dx) - self.R - 90), dx)
                        continue
                else:
                    tx = self.bx
                dx = tx - c["x"]
                if self.on == "out":
                    continue
                sp = 330.0
                stop = 170.0 + (c["id"] * 7919 % 290)              # chacun s'arrête à sa distance
                if abs(dx) > stop:
                    c["x"] += math.copysign(min(sp * dt, abs(dx) - stop), dx)
                elif t >= c["cool"] and self.pin is None:
                    c["st"] = "crouch"; c["t_st"] = t; c["dur"] = float(self.rng.uniform(0.3, 0.6))
            elif st in ("pin", "pile"):
                # il gagne sa place sur Bounce ou sur la pile en glissant, jamais d'un saut
                dx, dy = c["gx"] - c["x"], c["gy"] - c["y"]
                d = math.hypot(dx, dy)
                stp = 900.0 * dt
                if d > stp:
                    c["x"] += dx / d * stp; c["y"] += dy / d * stp
                else:
                    c["x"], c["y"] = c["gx"], c["gy"]

    def spread(self, dt):
        """Les chasseurs au sol ne s'entassent pas au même endroit : chacun garde un peu de
        place derrière celui qui est plus près de Bounce (sans jamais sauter)."""
        hs = [c for c in self.cats if c["st"] in ("hunt", "crouch") and c["lane"]]
        for side in (-1, 1):
            row = sorted([c for c in hs if (c["x"] - self.bx) * side >= 0], key=lambda c: abs(c["x"] - self.bx))
            for a, b in zip(row, row[1:]):
                need = 58.0 * max(a["sc"], b["sc"])
                gap = (b["x"] - a["x"]) * side
                if gap < need and b["st"] == "hunt":
                    b["x"] += side * min(need - gap, 260.0 * dt)

    def cat_contact(self, c, evs):
        if self.on in ("pinned",):
            return
        x, y, r = self.cat_circle(c)
        dx, dy = self.bx - x, self.by - y
        d0 = math.hypot(dx, dy)
        if d0 < self.R + r and d0 > 1e-6:
            # jamais l'un dans l'autre : Bounce est repoussé hors du chat
            self.bx = x + dx / d0 * (self.R + r + 0.5)
            self.by = min(FLOOR_Y - self.R, y + dy / d0 * (self.R + r + 0.5))
        if self.on == "out" or self.t < c["cool"]:
            return
        fx = x + c["f"] * 26 * c["sc"]
        d = math.hypot(fx - self.bx, y - self.by)
        if d >= self.R + r * 1.05 and d0 >= self.R + r + 1.0:
            return
        low = self.by > FLOOR_Y - self.R - 70
        if low and c["vy"] > 0 and self.rng.random() < self.p_pin_now():
            self.pin_bounce(c)
            if self.t - self.last_hit >= 0.15:
                self.last_hit = self.t
                self.hits += 1
                evs.append(("hit", "floor"))
            self.hit_t = self.t
            return
        # la patte le renvoie en l'air, dans le sens du saut (le hasard décide)
        s = 1.0 if c["vx"] >= 0 else -1.0
        if self.rng.random() < self.bat_back:
            s = -s
        self.vx = s * float(self.rng.uniform(*self.bat_v))
        self.vy = -float(self.rng.uniform(950, 1350))
        self.by = min(self.by, FLOOR_Y - self.R - 2)
        c["vx"] *= 0.3
        c["cool"] = self.t + 0.6
        self.bat_t = self.t
        # un coup de patte est un choc : Bounce dit son nom
        if self.t - self.last_hit >= 0.15:
            self.last_hit = self.t
            self.hits += 1
            evs.append(("hit", "floor"))
        self.hit_t = self.t
        self.on_bat(c)

    def p_pin_now(self):
        return self.p_pin

    def join_ok(self):
        """Les autres chats viennent-ils s'empiler sur Bounce une fois pris ?"""
        return False

    def pin_bounce(self, c):
        self.on = "pinned"
        self.by = FLOOR_Y - self.R
        self.vx = self.vy = 0.0
        self.pin = (self.bx, self.by)
        c["st"] = "pin"
        c["gx"], c["gy"] = self.bx + c["f"] * 6, FLOOR_Y - self.R * 1.25
        c["sc"] = 1.0
        c["lane"] = True
        self.finish("CAUGHT")
        self.on_caught()

    def join_pile(self, c):
        """Un monticule : chaque chat se pose sur la colonne la plus basse près du centre."""
        if not hasattr(self, "mound"):
            self.mound = {}
        best = None
        for b in range(-6, 7):
            h = self.mound.get(b, 0.0) + abs(b) * 14.0 + float(self.rng.uniform(0, 10))
            if best is None or h < best[0]:
                best = (h, b)
        b = best[1]
        hgt = self.mound.get(b, 0.0)
        self.mound[b] = hgt + 30.0
        for nb in (b - 1, b + 1):
            self.mound[nb] = max(self.mound.get(nb, 0.0), self.mound[b] - 45.0)
        c["st"] = "pile"
        c["gx"] = self.pin[0] + b * 44 + float(self.rng.uniform(-8, 8))
        base_y = FLOOR_Y - (self.R * 1.25 if abs(b) <= 1 else 0.0)
        c["gy"] = base_y - hgt + float(self.rng.uniform(-4, 4))
        c["f"] = 1 if self.rng.random() < 0.5 else -1
        c["sc"] = 1.0
        self.pile.append(c)

    # ------------------------------------------------------------------ récit
    def story(self, evs):
        pass

    def on_safe(self):
        pass

    def on_caught(self):
        pass

    def on_bat(self, c):
        pass

    def once(self, key):
        if key in self.events_said:
            return False
        self.events_said.add(key)
        return True

    # ------------------------------------------------------------------ contrat du contrôle
    def snapshot(self):
        s = self.base_snap()
        s["cam"] = self.cam
        s["cats"] = [(c["id"], c["st"], c["x"], c["y"], c["sc"], c["f"], c["fur"], c["ph"],
                      c["w"] / c["th"], c["twitch"], c["t_st"], c.get("dur", 0.6), c["vx"], c["vy"], c.get("t_wake", -9.0)) for c in self.cats]
        s["rings"] = [r for r in self.rings if self.t - r[0] < 0.65]
        s["prog"] = clamp((self.bx - self.start_x) / (self.exit_x - self.start_x), 0.0, 1.0)
        s["pin"] = self.pin
        return s

    def xf(self, s):
        cx, cy, Z = s["cam"]
        X = lambda x: (x - cx) * Z + self.W / 2
        Y = lambda y: (y - cy) * Z + SCREEN_CY
        return X, Y, Z

    def hero(self, s):
        X, Y, Z = self.xf(s)
        if self.tilt and s["t"] < self.tilt[1] and Y(s["by"]) + self.R * Z > self.H:
            return None                    # le panoramique ne l'a pas encore atteint
        return (X(s["bx"]), Y(s["by"]), self.R * Z)

    def solids(self, s):
        X, Y, Z = self.xf(s)
        out = []
        if s.get("on") == "pinned":
            return out                     # pris sous les chats : c'est la chute
        for (cid, st, x, y, sc, f, fur, ph, wk, tw, tst, dur, vx, vy, twk) in s["cats"]:
            if st in ("pin", "pile"):
                continue
            c = {"st": st, "x": x, "y": y, "sc": sc, "f": f}
            lane = y >= FLOOR_Y - 1 or st == "leap"
            if not lane:
                continue
            for (cx_, cy_, r) in self.cat_circles(c):
                out.append(("circle", X(cx_), Y(cy_), r * Z * 0.85))
        return out

    def focus(self, s):
        X, Y, Z = self.xf(s)
        bx, by = X(s["bx"]), Y(s["by"])
        r = self.R * Z
        return (bx - r - 20 * Z, by - r - 20 * Z, bx + r + 20 * Z, by + r + 6)

    def bodies(self, s):
        X, Y, Z = self.xf(s)
        return [(cid, X(x), Y(y), 0.0) for (cid, st, x, y, sc, f, fur, ph, wk, tw, tst, dur, vx, vy, twk) in s["cats"]
                if st in ("leap", "hunt", "crouch", "pin", "pile") and y >= FLOOR_Y - 400]

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, s, t, S):
        W, H = self.W, self.H
        X0, Y0, Z = self.xf(s)
        X = lambda x: X0(x) * S
        Y = lambda y: Y0(y) * S
        Q = lambda v: v * Z * S
        P = lambda v: v * S
        wall = self.wall_col
        dr.rectangle([0, P(SCENE_TOP), P(W), P(H)], fill=wall)
        x0, x1 = self.exit_x - 40, self.exit_x + 110
        glow(dr, lambda v: v, (X(x0) + X(x1)) / 2, Y(FLOOR_Y - 170), Q(230), (255, 214, 150), wall, 0.10, rings=10)
        self.decor(dr, X, Y, Q, s)
        # le sol
        if Y(FLOOR_Y) < P(H):
            dr.rectangle([0, Y(FLOOR_Y), P(W), P(H)], fill=self.floor_col)
            dr.rectangle([0, Y(FLOOR_Y), P(W), min(P(H), Y(FLOOR_Y + 8))], fill=dim(self.floor_col, 1.35))
        dr.rectangle([X(-400), Y(FLOOR_Y - 24), X(0), Y(FLOOR_Y)], fill=dim(wall, 0.6))
        self.door(dr, X, Y, Q, s)
        cats = s["cats"]
        back = [c for c in cats if c[1] not in ("leap", "pin", "pile") and c[3] < FLOOR_Y - 1]
        lane = [c for c in cats if c[1] not in ("leap", "pin", "pile") and c[3] >= FLOOR_Y - 1]
        air = [c for c in cats if c[1] == "leap"]
        pile = [c for c in cats if c[1] in ("pin", "pile")]
        xl, xr = s["cam"][0] - (W / 2 + 120) / Z, s["cam"][0] + (W / 2 + 120) / Z
        # pendant le panoramique, on voit les mille ; ensuite les dormeurs du fond s'effacent
        k = 1.0
        if self.tilt:
            k = clamp((self.t - self.tilt[1]) / 1.2, 0.0, 1.0)
        far = 1.0 + (self.far_dim - 1.0) * k
        for c in back:
            if xl < c[2] < xr:
                self.cat(dr, X, Y, Q, c, t, far=far)
        for c in sorted(lane, key=lambda c: c[2]):
            if xl < c[2] < xr:
                self.cat(dr, X, Y, Q, c, t)
        # l'onde de chaque rebond : c'est ça qui réveille les chats
        for (t0, rx, ry) in s.get("rings", []):
            age = self.t - t0
            if age < 0 or age > 0.6:
                continue
            for k2 in (0, 1):
                a2 = age - k2 * 0.12
                if a2 <= 0:
                    continue
                rad = Q(self.R * 0.9 + 480 * a2)
                col = mix((255, 236, 180), wall, min(1.0, a2 / 0.6) ** 1.5)
                cxp, cyp = X(rx), Y(ry)
                dr.arc([cxp - rad, cyp - rad * 0.55, cxp + rad, cyp + rad * 0.55], 180, 360, fill=col, width=max(1, int(Q(8))))
        self.marks(dr, X, Y, Q, s, t, xl, xr)
        if s.get("on") == "pinned":
            base.HERO["expr"] = "lose" if s["end"] is not None and self.t - s["end"] > 0.6 else "shock"
        bump = 0.0
        if s.get("on") == "pinned":
            bump = max(0.0, 1.0 - (self.t - s["hit_t"]) / 0.3)      # chaque « Bounce » soulève la pile
        lift = lambda c: c[:3] + (c[3] - 16 * bump,) + c[4:]
        for c in sorted([c for c in pile if c[1] == "pile"], key=lambda c: c[3]):
            self.cat(dr, X, Y, Q, lift(c), t)
        base.ball(dr, X(s["bx"]), Y(s["by"]), Q(self.R))
        for c in pile:
            if c[1] == "pin":
                self.cat(dr, X, Y, Q, lift(c), t)
        for c in air:
            self.cat(dr, X, Y, Q, c, t)
        dr.rectangle([0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))
        self.progress(dr, P, s, t)

    def progress(self, dr, P, s, t):
        """La distance jusqu'à la porte : Bounce (rose) sur une barre, la porte au bout."""
        if s["end"] is not None or t < self.cfg["hook_text_s"] + 0.1 and self.first:
            return
        x0, x1, y = 200.0, 880.0, 452.0
        dr.rounded_rectangle([P(x0), P(y - 7), P(x1), P(y + 7)], radius=int(P(7)), fill=(60, 60, 80))
        dr.rounded_rectangle([P(x0), P(y - 7), P(x0 + (x1 - x0) * s["prog"]), P(y + 7)], radius=int(P(7)), fill=(255, 120, 200))
        dr.rectangle([P(x1 + 10), P(y - 26), P(x1 + 40), P(y + 16)], fill=(255, 220, 160))
        circle(dr, P(x0 + (x1 - x0) * s["prog"]), P(y), P(17), tuple(self.cfg["hero_color"]))

    first = False

    def marks(self, dr, X, Y, Q, s, t, xl, xr):
        """Des « z » au-dessus des dormeurs proches, un « ! » sur chaque chat qui se réveille."""
        for c in s["cats"]:
            (cid, st, x, y, sc, f, fur, ph, wk, tw, tst, dur, vx, vy, twk) = c
            if not (xl < x < xr):
                continue
            if st == "sleep" and sc >= 0.6:
                u = ((t * 0.45 + ph) % 1.0)
                size = int(Q(22 * sc * (0.7 + 0.5 * u)))
                if size >= 6:
                    col = mix(self.wall_col, (200, 200, 230), 0.8 * (1 - u) * (1.0 if wk < 0.5 else 0.3))
                    dr.text((X(x + f * (40 + 30 * u) * sc), Y(y - (50 + 70 * u) * sc)), "z", fill=col, anchor="mm", font=self.fnt(size))
            if 0.0 <= t - twk < 0.8 and st != "sleep":
                size = int(Q(44 * max(sc, 0.6)))
                if size >= 8:
                    hy = y - (120 if st == "sit" else 70) * sc
                    dr.text((X(x), Y(hy)), "!", fill=(255, 210, 70), anchor="mb", font=self.fnt(size), stroke_width=max(1, int(size * 0.08)), stroke_fill=(10, 8, 12))

    _fonts = {}

    def fnt(self, size):
        f = CatRoom._fonts.get(size)
        if f is None:
            f = CatRoom._fonts[size] = base.font(size)
        return f

    wall_col = (28, 28, 46)
    floor_col = (52, 40, 36)

    def door(self, dr, X, Y, Q, s):
        x0, x1 = self.exit_x - 40, self.exit_x + 110
        top = FLOOR_Y - 330
        dr.rectangle([X(x0 - 14), Y(top - 14), X(x1 + 14), Y(FLOOR_Y)], fill=(70, 54, 44))
        dr.rectangle([X(x0), Y(top), X(x1), Y(FLOOR_Y)], fill=(255, 220, 160))
        dr.polygon([(X(x0), Y(FLOOR_Y)), (X(x1), Y(FLOOR_Y)), (X(x1 + 90), Y(FLOOR_Y + 60)), (X(x0 - 60), Y(FLOOR_Y + 60))], fill=mix(self.floor_col, (255, 220, 160), 0.35))

    far_dim = 1.0

    def cat(self, dr, X, Y, Q, c, t, far=1.0):
        (cid, st, x, y, sc, f, fur, ph, wk, tw, tst, dur, vx, vy, twk) = c
        col, stripe = FURS[fur]
        dark = fur == 2
        if st == "sleep" and far < 1.0:
            # au fond, dans le noir : les dormeurs s'effacent, les réveillés ressortent
            col, stripe = mix(self.wall_col, col, far), mix(self.wall_col, stripe, far)
        out = dim(col, 0.7) if not dark else (16, 16, 22)
        ear_in = (200, 120, 120) if not dark else (60, 40, 46)

        def E(px, py, a, b, ang=0.0, fill=col):
            pts = [(X(x + f * u), Y(y + v)) for (u, v) in ell(px * sc, py * sc, a * sc, b * sc, ang)]
            dr.polygon(pts, fill=fill)

        def tri(pts, fill):
            dr.polygon([(X(x + f * u * sc), Y(y + v * sc)) for (u, v) in pts], fill=fill)

        def eye(px, py, open_k, look=0.0, wide=False):
            ex, ey = X(x + f * px * sc), Y(y + py * sc)
            r = Q(6.5 * sc)
            if open_k <= 0.05:
                dr.line([(ex - r, ey), (ex + r, ey)], fill=(12, 12, 16) if not dark else (70, 70, 80), width=max(1, int(Q(2.2 * sc))))
                return
            h = r * open_k
            if r > 3:
                glow(dr, lambda v: v, ex, ey, r * 2.6, EYE, col if not dark else (30, 30, 38), 0.35, rings=2)
            dr.ellipse([ex - r, ey - h, ex + r, ey + h], fill=EYE)
            pw = r * (0.75 if wide else 0.28)
            dr.ellipse([ex + look * r * 0.3 - pw, ey - h * 0.9, ex + look * r * 0.3 + pw, ey + h * 0.9], fill=(10, 10, 12))

        breathe = 1.0 + 0.05 * math.sin(t * 2.2 + ph)
        if st == "sleep":
            twitch = t - tw < 0.35
            peek = clamp((wk - 0.55) / 0.3, 0.0, 1.0)
            # la queue enroulée devant
            E(-6, -8, 50, 12, 0.0, fill=dim(col, 0.85))
            E(0, -22 * breathe, 48, 23 * breathe)
            if stripe != col:
                for k in (-22, -6, 10):
                    E(k, -36, 4, 10, 0.3, fill=stripe)
            # la tête, posée sur les pattes
            E(36, -20, 21, 18)
            ea = 8 if twitch else 0
            tri([(26, -32), (32, -50 - ea), (40, -34)], col)
            tri([(42, -34), (52, -48), (54, -30)], col)
            tri([(29, -34), (32, -44 - ea), (37, -35)], ear_in)
            eye(32, -20, 0.0)
            eye(46, -20, peek * 0.9)
            return
        if st == "sit":
            look = 1.0
            E(-30, -6, 30, 7, 0.0, fill=dim(col, 0.85))          # la queue au sol
            E(0, -34, 26, 34)
            E(0, -12, 30, 14)
            E(6, -76, 22, 19)
            tri([(-8, -88), (-4, -112), (8, -92)], col)
            tri([(6, -92), (20, -110), (24, -86)], col)
            tri([(-4, -92), (-3, -104), (4, -93)], ear_in)
            eye(-1, -78, 0.9, look)
            eye(15, -78, 0.9, look)
            return
        if st == "crouch":
            age = t - tst
            wig = 7 * math.sin(age * 26) * min(1.0, age * 3)
            E(-30 + wig, -30, 30, 20, -0.25)                    # l'arrière-train relevé, qui remue
            E(4, -20, 44, 17)
            E(-64 + wig, -36, 26, 6, -0.5, fill=dim(col, 0.85))
            E(46, -18, 21, 17)
            tri([(34, -28), (38, -48), (48, -32)], col)
            tri([(50, -32), (62, -46), (62, -26)], col)
            eye(42, -19, 1.0, 1.0, wide=True)
            eye(56, -19, 1.0, 1.0, wide=True)
            return
        if st == "leap":
            ang = math.atan2(vy, abs(vx) + 1e-6) * 0.6
            E(0, -22, 52, 17, ang)
            ca, sa = math.cos(ang), math.sin(ang)
            hx, hy = 48 * ca, -22 + 48 * sa
            E(hx, hy, 20, 17)
            tri([(hx - 10, hy - 10), (hx - 6, hy - 30), (hx + 4, hy - 14)], col)
            tri([(hx + 6, hy - 14), (hx + 16, hy - 30), (hx + 18, hy - 8)], col)
            E(hx + 22, hy + 16, 8, 6, 0.0, fill=dim(col, 0.9))
            E(hx + 14, hy + 20, 8, 6, 0.0, fill=dim(col, 0.9))
            E(-56 * ca, -22 - 56 * sa - 10, 30, 6, ang - 0.4, fill=dim(col, 0.85))
            eye(hx - 4, hy - 2, 1.0, 1.0, wide=True)
            eye(hx + 9, hy - 2, 1.0, 1.0, wide=True)
            return
        if st == "hunt":
            run = math.sin(t * 18 + ph)
            E(0, -20, 46, 16)
            E(-14 + 6 * run, -8, 6, 7, 0.0, fill=dim(col, 0.85))
            E(18 - 6 * run, -8, 6, 7, 0.0, fill=dim(col, 0.85))
            E(-56, -30, 28, 6, -0.4, fill=dim(col, 0.85))
            E(44, -26, 21, 17)
            tri([(32, -36), (36, -56), (46, -40)], col)
            tri([(48, -40), (60, -54), (60, -34)], col)
            eye(40, -27, 1.0, 1.0, wide=True)
            eye(54, -27, 1.0, 1.0, wide=True)
            return
        # sur Bounce, ou sur la pile : couché, pattes en avant, ravi
        E(0, -16, 46, 20)
        E(-50, -16, 26, 6, 0.3, fill=dim(col, 0.85))
        E(40, -26, 21, 18)
        tri([(28, -36), (32, -56), (42, -40)], col)
        tri([(44, -40), (56, -54), (56, -32)], col)
        E(30, 2, 9, 7, 0.0, fill=dim(col, 0.9))
        E(50, 2, 9, 7, 0.0, fill=dim(col, 0.9))
        eye(36, -28, 0.55)
        eye(50, -28, 0.55)


# ---------------------------------------------------------------- 1 chat
class OneCat(CatRoom):
    title = "1 CAT"
    hall_w = 1080.0
    exit_x = 800.0
    start_x = 130.0
    hop_len = (112.0, 126.0)
    hop_h = (265.0, 300.0)
    hold_s = 2.4
    follow = (1.25,)
    first = True

    def build(self):
        # un seul chat, mais énorme, couché en travers du passage
        self.cats.append({"hx": 480.0, "hy": FLOOR_Y, "hsc": 4.2, "lane": True, "th": 0.5, "lazy": True, "fur": 0, "f": -1})

    lam = 160.0

    def lines_setup(self):
        self.line("One cat.", "title", 0.0)

    def on_safe(self):
        self.stamp = ("SAFE", GREEN)
        self.mood = "win"
        self.line("Easy.", "easy", self.t + 1.5)

    def decor(self, dr, X, Y, Q, s):
        # une fenêtre et la lune, un tapis rond sous le chat
        dr.rectangle([X(200), Y(980), X(420), Y(1230)], fill=(16, 22, 44))
        circle(dr, X(370), Y(1050), Q(28), (226, 228, 236))
        dr.rectangle([X(306), Y(980), X(314), Y(1230)], fill=(46, 46, 66))
        dr.rectangle([X(200), Y(1100), X(420), Y(1108)], fill=(46, 46, 66))
        dr.ellipse([X(360), Y(FLOOR_Y - 12), X(590), Y(FLOOR_Y + 24)], fill=(90, 50, 60))


# ---------------------------------------------------------------- 10 chats
class TenCats(CatRoom):
    title = "10 CATS"
    hall_w = 1080.0
    exit_x = 820.0
    start_x = 110.0
    hop_len = (80.0, 120.0)
    bat_v = (150.0, 400.0)
    loud = 0.62
    lam = 300.0
    reach = 480.0
    p_pin = 0.55
    hold_s = 2.6
    follow = (1.3,)

    def build(self):
        P = [(150.0, 1090.0, 0.8), (190.0, 880.0, 0.8),          # la bibliothèque
             (340.0, 1180.0, 0.8), (330.0, 970.0, 0.8),          # l'arbre à chat
             (520.0, 1300.0, 0.85), (640.0, 1300.0, 0.85), (720.0, 1150.0, 0.8),   # le canapé
             (600.0, 930.0, 0.75),                                # le rebord de la fenêtre
             (360.0, FLOOR_Y, 1.0), (590.0, FLOOR_Y, 1.0)]        # le tapis, sur son passage
        for (x, y, sc) in P:
            self.cats.append({"hx": x, "hy": y, "hsc": sc, "lane": y >= FLOOR_Y})

    def lines_setup(self):
        self.line("Ten cats.", "title", 0.0)

    def story(self, evs):
        if any(c["st"] == "crouch" for c in self.cats) and self.once("wiggle"):
            self.line("That's the butt wiggle.", "wiggle", self.t)

    def on_caught(self):
        self.stamp = ("CAUGHT", RED)
        self.mood = "lose"
        self.line("Caught.", "caught", self.t + 1.0)

    def on_safe(self):
        self.stamp = ("SAFE", GREEN)
        self.mood = "win"
        self.line("Barely.", "barely", self.t + 0.9)

    def decor(self, dr, X, Y, Q, s):
        dr.rectangle([X(520), Y(740), X(800), Y(920)], fill=(16, 22, 44))
        circle(dr, X(760), Y(790), Q(24), (226, 228, 236))
        dr.rectangle([X(500), Y(930), X(820), Y(946)], fill=(70, 56, 46))
        # la bibliothèque
        dr.rectangle([X(90), Y(700), X(270), Y(FLOOR_Y)], fill=(60, 44, 36))
        for yy in (880, 1090, 1300):
            dr.rectangle([X(90), Y(yy), X(270), Y(yy + 14)], fill=(84, 62, 48))
        for k in range(6):
            dr.rectangle([X(104 + k * 26), Y(1210), X(124 + k * 26), Y(1300)], fill=[(110, 60, 70), (60, 90, 120), (120, 110, 60)][k % 3])
        # l'arbre à chat
        dr.rectangle([X(326), Y(970), X(352), Y(FLOOR_Y)], fill=(170, 150, 120))
        for (yy, w) in ((970, 70), (1180, 80)):
            dr.rectangle([X(340 - w), Y(yy), X(340 + w), Y(yy + 16)], fill=(120, 100, 130))
        # le canapé
        dr.rectangle([X(440), Y(1150), X(800), Y(1300)], fill=(70, 60, 110))
        dr.rectangle([X(430), Y(1300), X(810), Y(1420)], fill=(84, 72, 130))
        dr.rectangle([X(420), Y(1240), X(470), Y(1420)], fill=(64, 54, 100))
        dr.rectangle([X(770), Y(1240), X(820), Y(1420)], fill=(64, 54, 100))
        dr.ellipse([X(260), Y(FLOOR_Y - 10), X(700), Y(FLOOR_Y + 30)], fill=(90, 50, 60))


# ---------------------------------------------------------------- 100 chats
class HundredCats(CatRoom):
    title = "100 CATS"
    hall_w = 1900.0
    exit_x = 1760.0
    start_x = 120.0
    hop_len = (110.0, 160.0)
    bat_v = (150.0, 400.0)
    loud = 0.62
    lam = 280.0
    reach = 440.0
    p_pin = 0.0
    follow = (1.05,)
    hold_s = 2.4
    far_dim = 0.6
    wall_col = (26, 30, 44)

    def build(self):
        rows = [1230.0, 1060.0, 890.0, 720.0]
        for r, yy in enumerate(rows):
            for k in range(22):
                self.cats.append({"hx": 210.0 + k * 68 + float(self.rng.uniform(-8, 8)), "hy": yy, "hsc": 0.62})
        xs = sorted(float(v) for v in self.rng.uniform(420, 1640, 12))
        for x in xs:
            self.cats.append({"hx": x, "hy": FLOOR_Y, "hsc": 1.0, "lane": True})

    def lines_setup(self):
        self.line("A hundred cats.", "title", 0.0)

    def on_bat(self, c):
        if self.once("bat"):
            self.line("Now it's a game.", "game", self.t + 0.1)

    def on_safe(self):
        self.stamp = ("SAFE", GREEN)
        self.mood = "win"
        if self.t - getattr(self, "bat_t", -9.0) < 1.6:
            self.line("Thanks, cat.", "thanks", self.t + 0.9)       # c'est un coup de patte qui l'a envoyé dehors
        else:
            self.line("Somehow.", "somehow", self.t + 0.9)

    def on_caught(self):
        self.stamp = ("CAUGHT", RED)
        self.mood = "lose"
        self.line("Caught.", "caught", self.t + 1.0)

    def decor(self, dr, X, Y, Q, s):
        for yy in (1230.0, 1060.0, 890.0, 720.0):
            dr.rectangle([X(170), Y(yy), X(1720), Y(yy + 12)], fill=(78, 60, 48))
        for xx in range(170, 1740, 390):
            dr.rectangle([X(xx), Y(680), X(xx + 12), Y(FLOOR_Y)], fill=(62, 48, 40))
        for k in range(3):
            x0 = 260 + k * 560
            dr.rectangle([X(x0), Y(540), X(x0 + 200), Y(660)], fill=(16, 22, 44))
            pass


# ---------------------------------------------------------------- 1000 chats
class ThousandCats(CatRoom):
    title = "1000 CATS"
    hall_w = 2350.0
    exit_x = 2200.0
    start_x = 240.0
    hop_len = (120.0, 175.0)
    bat_v = (150.0, 450.0)
    loud = 0.66
    lam = 240.0
    reach = 380.0
    p_pin = 0.0
    follow = (1.0,)
    tilt = (300.0, 2.4)
    far_dim = 0.42
    hold_s = 5.6
    wall_col = (22, 24, 40)
    ROWS = 25
    COLS = 40

    def build(self):
        self.on = "wait"
        self.bx = -400.0
        for r in range(self.ROWS):
            yy = 1390.0 - r * 57.0
            for k in range(self.COLS):
                self.cats.append({"hx": 150.0 + k * 50 + float(self.rng.uniform(-4, 4)), "hy": yy, "hsc": 0.42,
                                  "th": float(self.rng.uniform(0.9, 1.9))})
        self.waiting = True

    def lines_setup(self):
        self.line("A thousand cats.", "title", 0.0)
        self.line("All asleep.", "asleep", 1.5)

    def bounce_step(self, dt, evs):
        # le plan large d'ouverture : il rebondit sur place à l'entrée
        if self.on == "wait":
            if self.t < self.tilt[1] - 0.5:
                return
            # il entre par la gauche, en l'air, quand la caméra arrive en bas
            self.on = "air"
            self.bx = self.cx - 540.0 / self.follow[0] - self.R - 10
            self.by = FLOOR_Y - self.R - 260
            self.vx, self.vy = 420.0, -300.0
        super().bounce_step(dt, evs)

    def hero(self, s):
        X, Y, Z = self.xf(s)
        if s.get("on") == "wait" or X(s["bx"]) - self.R * Z < 0:
            return None                    # pas encore entré dans le cadre
        return (X(s["bx"]), Y(s["by"]), self.R * Z)

    def join_ok(self):
        return True

    def p_pin_now(self):
        # loin de la porte, les pattes le renvoient ; près d'elle, ils sont trop nombreux
        return 0.0 if self.bx < 0.72 * self.exit_x else 0.6

    def story(self, evs):
        if self.pin is not None:
            return
        awake = sum(1 for c in self.cats if c["st"] != "sleep")
        _ = awake
        if self.bx > self.exit_x * 0.55 and self.once("half"):
            self.line("Halfway.", "half", self.t)
        if self.bx > self.exit_x * 0.8 and "wrong" not in self.events_said and self.once("almost"):
            self.line("Almost.", "almost", self.t)
        if "wrong" in self.events_said and self.bx > self.exit_x * 0.75 and self.once("close"):
            self.line("So close.", "close", self.t)
        # renvoyé en arrière par les pattes, puis reparti
        if "half" in self.events_said:
            if self.bx < self.exit_x * 0.45 and self.once("wrong"):
                self.line("Wrong way.", "wrong", self.t)
            if self.bx < self.exit_x * 0.15 and self.once("start"):
                self.line("Back to the start.", "start", self.t)
            if "start" in self.events_said and self.bx > self.exit_x * 0.3 and self.vx > 0 and self.once("again"):
                self.line("Here we go again.", "again", self.t)

    def on_caught(self):
        self.stamp = ("CAUGHT", RED)
        self.mood = "lose"
        # tous les chats réveillés viennent sur la pile
        for c in self.cats:
            if c["st"] in ("sit", "crouch", "hunt"):
                c["cool"] = self.t + float(self.rng.uniform(0.1, 1.2))
                if c["st"] == "sit":
                    c["delay"] = 0.0
        self.line("Best toy they ever had.", "toy", self.t + 1.2)

    def on_safe(self):
        self.stamp = ("SAFE", GREEN)
        self.mood = "win"
        self.line("A thousand cats. Zero.", "zero", self.t + 0.75)

    def cats_step(self, dt, evs):
        if self.pin is not None:
            # après la prise : les chats réveillés convergent vers la pile
            for c in self.cats:
                if c["st"] == "sit" and abs(c["x"] - self.pin[0]) < 700:
                    c["st"] = "crouch"; c["t_st"] = self.t; c["dur"] = float(self.rng.uniform(0.2, 0.8))
        super().cats_step(dt, evs)

    def decor(self, dr, X, Y, Q, s):
        # les étagères géantes de l'entrepôt
        for r in range(self.ROWS):
            yy = 1390.0 - r * 57.0
            dr.rectangle([X(120), Y(yy), X(2130), Y(yy + 7)], fill=(70, 54, 44))
        for xx in range(120, 2140, 400):
            dr.rectangle([X(xx), Y(1390 - (self.ROWS - 1) * 57 - 40), X(xx + 10), Y(FLOOR_Y)], fill=(56, 44, 38))


DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": G,
    "chapter_max_s": 12.0,
    "counter_font_size": 84, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 2.0, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}

CHAPTERS = [(OneCat, {"cat_seed": 11}), (TenCats, {"cat_seed": 52}), (HundredCats, {"cat_seed": 79}),
            (ThousandCats, {"cat_seed": 30, "chapter_max_s": 40.0})]


class Sim(StorySim):
    def __init__(self, cfg, rng):
        chs = []
        for (cls, over) in CHAPTERS:
            o = dict(over)
            k = cls.__name__.lower() + "_seed"
            if k in cfg:
                o["cat_seed"] = cfg[k]
            chs.append((cls, o))
        cfg["_chapters"] = chs
        super().__init__(cfg, rng)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
