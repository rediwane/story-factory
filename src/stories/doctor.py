"""
Prototype « chez le docteur » : Bounce passe une visite médicale. Le docteur (une
silhouette sans visage en blouse, la voix du narrateur) pose ses questions ; Bounce ne
sait répondre que « Bounce ». Une bulle traduit ce qu'il voulait dire.

Bounce ne s'arrête jamais : de petits rebonds continus sur la table d'examen (muets,
il ne dit son nom qu'aux vrais contacts), des rebonds parlés quand c'est son tour,
puis un grand rebond qui secoue tout le cabinet. Les dégâts restent d'une question à
l'autre. Au test des réflexes, le marteau le lance dans toute la pièce ; il retombe
sur la table, qui cède. Diagnostic, ordonnance, et le docteur lâche lui-même un
« ...Bounce. ».

    python3 src/stories/doctor.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, FLOOR_Y, SCENE_TOP, mix, settle_body, separate, body_poly

R_B = 68.0
G = 3000.0
TABLE = (60.0, 300.0, 1230.0)          # x0, x1, dessus du coussin
CUSH_H = 34.0                          # épaisseur du coussin (il finit au sol)
BX = 180.0                             # Bounce sur la table
DOC_X = 470.0                          # le docteur
COUNTER = (570.0, 690.0, 1210.0)       # le meuble à droite : x0, x1, dessus
CHART = (590.0, 680.0, 842.0, 1012.0)  # le tableau de lettres, au-dessus du meuble
WL, WR, CEIL = 20.0, 760.0, 660.0      # la pièce, pour le test des réflexes
OBJ_LO = BX + R_B + 40.0               # les objets ne viennent jamais sur la place de Bounce
HOP_T = 0.92                           # un rebond parlé : assez long pour dire son nom
BIG_T = 0.95                           # le grand rebond de la réponse
WALL = (30, 42, 52)
FLOOR = (44, 50, 60)
CUSHION = (62, 128, 140)
METAL = (120, 126, 140)
COAT = (204, 210, 222)
HEAD = (88, 92, 116)
WOOD = (150, 112, 72)
PINK = (255, 60, 200)

# l'état du cabinet, qui passe d'une question à la suivante (remis à zéro par Sim)
CLINIC = {}


def rr(dr, box, **kw):
    x0, y0, x1, y1 = box
    dr.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], **kw)


def rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def new_obj(objs, kind, x, y, width, height, col, a=0.0, rest=True, **kw):
    if height > width:
        width, height, a = height, width, a + math.pi / 2
    o = {"id": kw.pop("oid", len(objs)), "kind": kind, "x": x, "y": y, "a": a, "vx": 0.0, "vy": 0.0, "w": 0.0,
         "wd": width, "ht": height, "col": col, "rest": rest, "free": not rest,
         "flat": math.pi if width / height >= 1.6 else math.pi / 2}
    o.update(kw)
    objs.append(o)
    return o


def fresh_clinic():
    objs = []
    top = COUNTER[2]
    new_obj(objs, "jar", 600.0, top - 36, 64.0, 72.0, (170, 200, 214))
    new_obj(objs, "tissue", 660.0, top - 21, 56.0, 42.0, (120, 170, 220))
    return {"objs": objs, "sticks": [], "table": "ok", "cush_y": TABLE[2], "cush_v": 0.0, "legs": 0.0,
            "chart": "wall", "chart_a": 0.0, "chart_w": 0.0, "chart_rest": 0.0, "crack": None, "jar_full": True}


def surf_y():
    """Le dessus sur lequel Bounce rebondit hors du test des réflexes."""
    return CLINIC["cush_y"] - R_B if CLINIC else TABLE[2] - R_B


class Visit(Chapter):
    """Une question : le docteur demande, Bounce rebondit sans cesse, répond d'un grand
    rebond ; la bulle traduit ; le cabinet encaisse."""
    hold_s = 0.6
    stamp = None
    level = 1
    label = ""
    q = ""
    tr = ""
    react = ""
    nhops = 1
    prop = None
    kind = "question"

    def setup(self):
        self.R = R_B
        self.bx, self.by = BX, TABLE[2] - self.R
        self.vx = self.vy = 0.0
        self.on = "ground"
        self.mode = "hop"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.reply_local = None
        self.q_end_local = None
        self.q_start_local = None
        self.hop = None                  # (départ, durée, genre)
        self.plan = []
        self.started = False
        self.impact_t = -9.0
        self.answer_at = None
        self.tap_t = None
        self.land_t = None
        self.aimed = False
        self.title = f"{self.n}/{self.N} · {self.label}"
        if self.q:
            self.line(self.q, "title", 2.45 if self.n == 1 else 0.0)
        self.rng2 = np.random.default_rng(100 + self.level)
        self._pending = []

    @classmethod
    def reply_delay(cls):
        return 0.15 + cls.nhops * HOP_T + 0.4 + BIG_T

    # ------------------------------------------------------------------ Bounce
    def make_plan(self):
        if self.kind == "question":
            t0 = self.q_end_local + 0.15
            self.plan = [(t0 + k * HOP_T, HOP_T, "talk") for k in range(self.nhops)]
            self.plan.append((self.reply_local - BIG_T, BIG_T, "big"))
        elif self.kind == "reflex":
            self.tap_t = self.q_end_local + 0.85
            self.plan = [(self.tap_t, 0.0, "tap")]

    def next_hop(self):
        """Au contact : le prochain rebond. Jamais immobile : entre deux rebonds prévus,
        de petits rebonds (muets) qui retombent pile à l'heure du suivant."""
        tp = self.plan[0][0] if self.plan else 1e9
        if self.plan and self.t >= tp - 1e-6:
            t0, T, kind = self.plan.pop(0)
            if kind == "tap":
                self.launch()
                return
            self.hop = (self.t, T, kind)
            return
        rem = tp - self.t
        TI = float(self.rng2.uniform(0.25, 0.31))
        if rem >= 1.7 * TI:
            T = TI
        elif rem >= 0.4:
            T = rem / 2
        else:
            T = max(rem, 1e-3)
        self.hop = (self.t, T, "idle")

    def step(self, dt):
        self.t += dt
        evs = []
        if not self.started:
            self.started = True
            if not CLINIC:
                CLINIC.update(fresh_clinic())
            self.make_plan()
            self.by = surf_y()
            self.next_hop()
        if self.mode == "chaos":
            self.chaos(dt, evs)
        elif self.mode == "hop":
            t0, T, kind = self.hop
            te = self.t - t0
            sy = surf_y()
            if te >= T - 1e-9:
                self.by = sy
                if kind != "idle":
                    if self.t - self.last_hit >= 0.15:
                        self.last_hit = self.t; self.hits += 1
                        evs.append(("hit", kind))
                    self.hit_t = self.t
                self.hop = None
                if kind == "big":
                    self.impact()
                    self.answer_at = self.t + 0.3
                self.next_hop()
            else:
                v = G * T / 2
                self.by = sy - (v * te - 0.5 * G * te * te)
            self.bx = BX
        if self.answer_at is not None and self.t >= self.answer_at and self.end_t is None:
            self.finish("ANSWER")
            self.on_answer()
        self.tick()
        self.physics(dt)
        if self._pending:
            evs = list(evs) + self._pending
            self._pending = []
        return evs

    def tick(self):
        pass

    # ------------------------------------------------------------------ les réflexes
    def launch(self):
        """Le marteau touche son flanc droit : il part vers la gauche, vers le haut."""
        self.mode = "chaos"
        self.last_hit = self.t; self.hits += 1; self.hit_t = self.t
        self._pending.append(("hit", "tap"))
        self.chaos_t0 = self.t
        self.shake_room(300, objs=False)
        self.build_route()

    def solid_rects(self):
        out = [("rect", DOC_X - 75, 1000.0, DOC_X + 75, FLOOR_Y), ("circle", DOC_X, 945.0, 46.0),
               ("rect", COUNTER[0], COUNTER[2], COUNTER[1], FLOOR_Y)]
        if CLINIC["table"] == "ok":
            out.append(("rect", TABLE[0], TABLE[2], TABLE[1], FLOOR_Y))
        else:
            out.append(("rect", TABLE[0], CLINIC["cush_y"], TABLE[1], FLOOR_Y))
        for o in CLINIC["objs"]:
            if o["rest"]:
                x0, y0, x1, y1 = self.aabb(o)
                out.append(("rect", x0, y0, x1, y1))
        return out

    def collide(self, x, y, vx, vy, E, shapes):
        """Un disque contre la pièce et les solides. Renvoie la nouvelle position, la
        vitesse et la liste des contacts (genre, vitesse normale)."""
        R = self.R
        hits = []
        if x < WL + R:
            x = WL + R
            if vx < 0:
                hits.append(("wall", -vx)); vx = -vx * E
        if x > WR - R:
            x = WR - R
            if vx > 0:
                hits.append(("wall", vx)); vx = -vx * E
        if y < CEIL + R:
            y = CEIL + R
            if vy < 0:
                hits.append(("ceil", -vy)); vy = -vy * E
        if y > FLOOR_Y - R:
            y = FLOOR_Y - R
            if vy > 0:
                hits.append(("floor", vy)); vy = -vy * E
        for sh in shapes:
            if sh[0] == "rect":
                _, x0, y0, x1, y1 = sh
                px, py = min(max(x, x0), x1), min(max(y, y0), y1)
                dx, dy = x - px, y - py
                d = math.hypot(dx, dy)
                if d >= R:
                    continue
                if d < 1e-6:
                    nx, ny, d = 0.0, -1.0, 0.0
                    y = y0 - R
                else:
                    nx, ny = dx / d, dy / d
                    x, y = px + nx * R, py + ny * R
            else:
                _, cx, cy, cr = sh
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy)
                if d >= R + cr or d < 1e-6:
                    continue
                nx, ny = dx / d, dy / d
                x, y = cx + nx * (R + cr), cy + ny * (R + cr)
            vn = vx * nx + vy * ny
            if vn < 0:
                vx -= (1 + E) * vn * nx; vy -= (1 + E) * vn * ny
                hits.append((sh[0] + ("top" if ny < -0.7 else ""), -vn, sh))
        return x, y, vx, vy, hits

    def aim(self):
        """Le dernier rebond : vers la table, sans rien toucher en route."""
        x0, y0 = self.bx, self.by
        tx, ty = BX, TABLE[2] - self.R
        shapes = [s for s in self.solid_rects() if not (s[0] == "rect" and s[1] == TABLE[0])]
        for T in np.arange(0.75, 1.5, 0.05):
            vx = (tx - x0) / T
            vy = (ty - y0) / T - 0.5 * G * T
            ok = True
            for k in range(1, 60):
                tt = T * k / 60
                x, y = x0 + vx * tt, y0 + vy * tt + 0.5 * G * tt * tt
                if x < WL + self.R or x > WR - self.R or y < CEIL + self.R + 4:
                    ok = False; break
                if k > 6 and any(self.pen((x, y), s) > -6 for s in shapes):
                    ok = False; break
                if k < 54 and TABLE[0] - self.R < x < TABLE[1] + self.R and y > TABLE[2] - self.R - 2:
                    ok = False; break
            if ok:
                self.vx, self.vy = vx, vy
                self.aimed = True
                return True
        return False

    def pen(self, p, sh):
        x, y = p
        if sh[0] == "rect":
            _, x0, y0, x1, y1 = sh
            px, py = min(max(x, x0), x1), min(max(y, y0), y1)
            return self.R - math.hypot(x - px, y - py)
        _, cx, cy, cr = sh
        return self.R + cr - math.hypot(x - cx, y - cy)

    def counter_top(self, x):
        g = COUNTER[2]
        for o in CLINIC["objs"]:
            if o["rest"]:
                x0, y0, x1, y1 = self.aabb(o)
                if x0 - self.R < x < x1 + self.R and y1 >= COUNTER[2] - 2 and y0 < g and y1 <= COUNTER[2] + 2:
                    g = y0
        return g

    def build_route(self):
        """Le parcours du test des réflexes : une suite d'arcs balistiques entre de vrais
        contacts (murs, plafond, meuble, tête du docteur, table), aucun ne traversant rien.
        Chaque arc dure assez pour que Bounce dise son nom à chaque contact."""
        R = self.R
        targets = [
            ("wallL", (WL + R, 930.0)),
            ("ceil", (380.0, CEIL + R)),
            ("counter", (664.0, None)),
            ("wallR", (WR - R, 880.0)),
            ("head", (DOC_X, 945.0 - 46.0 - R)),
            ("ceil", (240.0, CEIL + R)),
            ("wallL", (WL + R, 1010.0)),
        ]
        shapes = [("rect", DOC_X - 75, 1000.0, DOC_X + 75, FLOOR_Y), ("circle", DOC_X, 945.0, 46.0),
                  ("rect", COUNTER[0], COUNTER[2], COUNTER[1], FLOOR_Y), ("rect", TABLE[0], TABLE[2], TABLE[1], FLOOR_Y)]
        for o in CLINIC["objs"]:
            if o["rest"]:
                x0, y0, x1, y1 = self.aabb(o)
                shapes.append(("rect", x0, y0, x1, y1))
        self.route = []
        p, kind0 = (self.bx, self.by), "tap"
        t = self.t
        for kind, (tx, ty) in targets:
            if ty is None:
                ty = self.counter_top(tx) - R
            arc = self.solve_arc(p, kind0, (tx, ty), kind, shapes)
            if arc is None:
                continue
            v0, T = arc
            self.route.append((t, p, v0, T, kind, (tx, ty)))
            t += T
            p, kind0 = (tx, ty), kind
        # le dernier arc retombe toujours sur la table : on recule jusqu'à ce qu'il existe
        goal = (BX, TABLE[2] - R)
        while True:
            arc = self.solve_arc(p, kind0, goal, "table", shapes)
            if arc is not None or not self.route:
                break
            last = self.route.pop()
            t, p = last[0], last[1]
            kind0 = self.route[-1][4] if self.route else "tap"
        if arc is None:
            arc = ((0.0, -0.5 * G * 0.8), 0.8)       # repli : un rebond sur place
        self.route.append((t, p, arc[0], arc[1], "table", goal))
        self.arc_i = 0

    def solve_arc(self, p0, k0, p1, k1, shapes, T_pref=0.78):
        R = self.R
        cands = sorted(np.arange(0.2, 1.3, 0.01), key=lambda T: abs(T - T_pref))
        for T in cands:
            vx = (p1[0] - p0[0]) / T
            vy0 = (p1[1] - p0[1]) / T - 0.5 * G * T
            vy1 = vy0 + G * T
            # partir en s'éloignant de la surface quittée, arriver en allant vers la suivante
            if k0 == "tap" and not (vx <= 0 and vy0 < 0): continue
            if k0 == "wallL" and vx <= 50: continue
            if k0 == "wallR" and vx >= -50: continue
            if k0 == "ceil" and vy0 <= 0: continue
            if k0 in ("counter", "head", "table") and vy0 >= 0: continue
            if k1 == "wallL" and vx >= -50: continue
            if k1 == "wallR" and vx <= 50: continue
            if k1 == "ceil" and vy1 >= 0: continue
            if k1 in ("counter", "head", "table") and vy1 <= 0: continue
            ok = True
            for k in range(1, 80):
                tt = T * k / 80
                x, y = p0[0] + vx * tt, p0[1] + vy0 * tt + 0.5 * G * tt * tt
                near = min(math.hypot(x - p0[0], y - p0[1]), math.hypot(x - p1[0], y - p1[1])) < 24
                if x < WL + R - 0.5 or x > WR - R + 0.5 or y < CEIL + R - 0.5 or y > FLOOR_Y - R:
                    ok = False; break
                if not near and any(self.pen((x, y), sh) > -2 for sh in shapes):
                    ok = False; break
            if ok:
                return (vx, vy0), T
        return None

    def chaos(self, dt, evs):
        if CLINIC["table"] != "ok":
            # la table a cédé : il remonte, puis retombe sur le coussin, qui tombe aussi
            self.vy += G * dt
            y = self.by + self.vy * dt
            floor = CLINIC["cush_y"] - self.R
            if y >= floor and self.vy > 0 and CLINIC["cush_v"] == 0.0:
                self.by = floor
                self.mode = "hop"
                self.land_t = self.t
                if self.t - self.last_hit >= 0.15:
                    self.last_hit = self.t; self.hits += 1
                    evs.append(("hit", "cushion"))
                self.hit_t = self.t
                self.finish("REFLEX")
                self.line(self.react, "react", self.t + 0.5)
                self.hop = None
                self.next_hop()
                return
            self.by = min(y, floor)
            return
        while self.arc_i < len(self.route):
            t0, p0, v0, T, kind, p1 = self.route[self.arc_i]
            te = self.t - t0
            if te < T:
                self.bx = p0[0] + v0[0] * te
                self.by = p0[1] + v0[1] * te + 0.5 * G * te * te
                self.vx, self.vy = v0[0], v0[1] + G * te
                return
            # le contact
            self.bx, self.by = p1
            self.arc_i += 1
            if self.t - self.last_hit >= 0.15:
                self.last_hit = self.t; self.hits += 1
                evs.append(("hit", kind))
            self.hit_t = self.t
            if kind == "ceil" and CLINIC["crack"] is None:
                CLINIC["crack"] = self.bx
            if kind == "head":
                self.bonk_t = self.t
            if kind == "counter":
                for o in CLINIC["objs"]:
                    if o["rest"] and o["y"] < COUNTER[2]:
                        self.kick(o, 520, 0.5, w=float(self.rng2.uniform(-3, 3)))
            self.shake_room(160, objs=False)
            if kind == "table":
                self.break_table()
                self.bx = BX
                self.vy = -900.0
                return


    def break_table(self):
        CLINIC["table"] = "broken"
        CLINIC["cush_v"] = 1.0
        for o in CLINIC["objs"]:
            if o["rest"]:
                self.kick(o, 260, 0.5)

    def shake_room(self, power, objs=True):
        for o in (CLINIC["objs"] if objs else []):
            if o["rest"] and o["kind"] in ("jar", "tissue", "chart"):
                self.kick(o, power, 0.5)
        for p in CLINIC["sticks"]:
            if p["rest"]:
                p["rest"] = False
                p["vy"] = -float(self.rng2.uniform(0.5, 1.0)) * power
                p["vx"] = float(self.rng2.uniform(-80, 80))
                p["w"] = float(self.rng2.uniform(-8, 8))

    # ------------------------------------------------------------------ le cabinet
    def kick(self, o, power, side_bias=0.8, vx=None, w=None):
        side = 1.0 if self.rng2.random() < side_bias else -1.0
        o["rest"] = False
        o["free"] = True
        o["vy"] = -power * float(self.rng2.uniform(0.85, 1.15))
        o["vx"] = vx if vx is not None else side * float(self.rng2.uniform(40, 140))
        o["w"] = w if w is not None else float(self.rng2.uniform(-4, 4))

    def obj(self, kind):
        for o in CLINIC["objs"]:
            if o["kind"] == kind:
                return o
        return None

    def spill(self, n):
        jar = self.obj("jar")
        CLINIC["jar_full"] = False
        for k in range(n):
            CLINIC["sticks"].append({"id": 100 + len(CLINIC["sticks"]), "x": jar["x"] + float(self.rng2.uniform(-10, 10)),
                                     "y": jar["y"] - 30, "vx": float(self.rng2.uniform(-120, 260)),
                                     "vy": -float(self.rng2.uniform(500, 900)), "a": float(self.rng2.uniform(0, 3)),
                                     "w": float(self.rng2.uniform(-9, 9)), "rest": False})

    def impact(self):
        """Le grand rebond : tout le cabinet saute, de plus en plus fort."""
        self.impact_t = self.t
        L = self.level
        jar, tis = self.obj("jar"), self.obj("tissue")
        if L == 1:
            self.kick(jar, 260, 0.5, vx=0.0, w=0.0); self.kick(tis, 300, 0.5, vx=10.0, w=0.0)
        elif L == 2:
            self.kick(jar, 520, vx=40.0, w=-5.0)
            self.spill(7)
            self.kick(tis, 340, 0.5, vx=-10.0)
        elif L == 3:
            CLINIC["chart_w"] = 2.4; CLINIC["chart_rest"] = 0.12
            self.kick(tis, 420, vx=30.0)
            for p in CLINIC["sticks"]:
                p["rest"] = False; p["vy"] = -320.0; p["vx"] = float(self.rng2.uniform(-60, 120)); p["w"] = 5.0
        elif L == 4:
            self.kick(tis, 820, vx=210.0, w=4.0)
            self.kick(jar, 360, 0.5, vx=-20.0)
        elif L == 5:
            self.kick(jar, 900, vx=230.0, w=6.0)
            CLINIC["chart_w"] += 3.0; CLINIC["chart_rest"] = 0.27
        elif L == 6:
            CLINIC["chart"] = "down"
            new_obj(CLINIC["objs"], "chart", (CHART[0] + CHART[1]) / 2, (CHART[2] + CHART[3]) / 2,
                    CHART[1] - CHART[0], CHART[3] - CHART[2], (236, 236, 228), a=CLINIC["chart_a"], rest=False,
                    oid=50, vx=-30.0, vy=-260.0, w=-1.5)
            self.shake_room(300)
        else:
            self.shake_room(260)

    @staticmethod
    def aabb(o):
        pts = body_poly(o, rect(o["wd"], o["ht"]))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def ground(self, o):
        x0, x1, top = COUNTER
        g = top if (x0 <= o["x"] <= x1 and o["y"] < top) else FLOOR_Y
        ax0, ay0, ax1, ay1 = self.aabb(o)
        for r in CLINIC["objs"]:
            if r is o or not r["rest"]:
                continue
            bx0, by0, bx1, by1 = self.aabb(r)
            flat = abs(math.sin(2 * r["a"])) < 0.05
            wide = (bx1 - bx0) >= 0.9 * (ax1 - ax0)
            tol = 8.0 + max(0.0, o["vy"]) / 60.0
            if flat and wide and bx0 + 6 <= o["x"] <= bx1 - 6 and ay1 <= by0 + tol and by0 < g:
                g = by0
        return g

    def bounds(self, o):
        x0, y0, x1, y1 = self.aabb(o)
        hw = 0.5 * (x1 - x0)
        return OBJ_LO + hw, WR - hw

    def physics(self, dt):
        # le coussin de la table qui tombe au sol
        if CLINIC["cush_v"] > 0:
            CLINIC["cush_v"] += G * dt
            CLINIC["cush_y"] += CLINIC["cush_v"] * dt
            CLINIC["legs"] = min(1.0, CLINIC["legs"] + dt * 4.0)
            if CLINIC["cush_y"] >= FLOOR_Y - CUSH_H:
                CLINIC["cush_y"] = FLOOR_Y - CUSH_H
                CLINIC["cush_v"] = 0.0
                CLINIC["legs"] = 1.0
        # le tableau qui se balance sur son clou
        if CLINIC["chart"] == "wall":
            a = CLINIC["chart_a"]
            CLINIC["chart_w"] += (-(a - CLINIC["chart_rest"]) * 60.0 - CLINIC["chart_w"] * 2.2) * dt
            CLINIC["chart_a"] += CLINIC["chart_w"] * dt
        objs = CLINIC["objs"]
        for o in objs:
            if o["rest"]:
                continue
            o["vy"] += G * 0.85 * dt
            o["x"] += o["vx"] * dt
            o["y"] += o["vy"] * dt
            o["a"] += o["w"] * dt
            lo, hi = self.bounds(o)
            if o["x"] < lo:
                o["x"] = lo; o["vx"] = abs(o["vx"]) * 0.4
            if o["x"] > hi:
                o["x"] = hi; o["vx"] = -abs(o["vx"]) * 0.4
            settle_body(o, self.ground(o), o["flat"], dt, rect(o["wd"], o["ht"]))
        sep = [o for o in objs if o["free"]]
        for _ in range(3):
            flags = [o["rest"] for o in sep]
            for o in sep:
                o["rest"] = False
            separate(sep, lambda o: rect(o["wd"], o["ht"]), iters=4, max_step=2.5)
            for o, f in zip(sep, flags):
                o["rest"] = f
            for o in sep:
                lo, hi = self.bounds(o)
                o["x"] = min(max(o["x"], lo), hi)
                ca, sa = math.cos(o["a"]), math.sin(o["a"])
                low = max(dx * sa + dy * ca for dx, dy in rect(o["wd"], o["ht"]))
                g = self.ground(o)
                if o["y"] + low > g + 0.5:
                    o["y"] = g - low
                elif o["rest"] and o["y"] + low < g - 2:
                    o["rest"] = False
        for p in CLINIC["sticks"]:
            if p["rest"]:
                tgt = round(p["a"] / math.pi) * math.pi
                p["a"] += max(-6 * dt, min(6 * dt, tgt - p["a"]))
                continue
            p["vy"] += G * 0.85 * dt
            p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt
            p["a"] += p["w"] * dt
            p["x"] = min(WR - 30, max(OBJ_LO + 30, p["x"]))
            x0, x1, top = COUNTER
            gy = top if (x0 + 4 <= p["x"] <= x1 - 4 and p["y"] < top - 1) else FLOOR_Y
            if p["vy"] > 0 and p["y"] >= gy - 4:
                p["y"] = gy - 4
                if p["vy"] > 350:
                    p["vy"] = -0.3 * p["vy"]; p["vx"] *= 0.6; p["w"] *= 0.5
                else:
                    p["rest"] = True; p["vy"] = 0.0; p["vx"] = 0.0

    # ------------------------------------------------------------------ récit
    def on_answer(self):
        if self.react:
            self.line(self.react, "react", self.t + 0.85)

    def snapshot(self):
        s = self.base_snap()
        s["objs"] = [dict(o) for o in CLINIC.get("objs", [])]
        s["sticks"] = [dict(p) for p in CLINIC.get("sticks", [])]
        for k in ("table", "cush_y", "legs", "chart", "chart_a", "crack", "jar_full"):
            s[k] = CLINIC.get(k)
        s["impact"] = self.impact_t
        s["ans"] = self.end_t if self.kind == "question" else None
        s["mode"] = self.mode
        s["tap"] = self.tap_t
        s["land"] = self.land_t
        return s

    # ------------------------------------------------------------------ caméra
    def qcam(self, t):
        if self.n == 1:
            k = min(1.0, t / 2.6)
            k = k * k * (3 - 2 * k)
            Z = 2.3 - 1.0 * k + 0.08 * min(1.0, max(0.0, t - 2.6) / 5.0)
            return Z, 190.0 + 240.0 * k, 1160.0 + 80.0 * k
        k = min(1.0, t / 8.0)
        Z = 1.22 + 0.18 * k
        low = 0.0 if CLINIC.get("table", "ok") == "ok" or self.kind == "reflex" else 60.0
        return Z, 430.0 - 30.0 * k + 14.0 * math.sin(t * 1.4), 1240.0 - 20.0 * k + low

    def cam(self, s):
        t = s["t"]
        Z, cx, cy = self.qcam(t)
        if s.get("tap") is not None and t >= s["tap"]:
            k = min(1.0, (t - s["tap"]) / 0.5)
            k = k * k * (3 - 2 * k)
            Z = Z + (1.05 - Z) * k
            cx = cx + (390.0 - cx) * k
            cy = cy + (1231.0 - cy) * k
        dy = 0.0
        age = t - s["impact"]
        if 0 <= age < 0.5:
            dy = 9.0 * math.exp(-age * 7) * math.sin(age * 50)
        age = t - s["hit_t"] if s.get("mode") == "chaos" else 9.0
        if 0 <= age < 0.3:
            dy += 6.0 * math.exp(-age * 9) * math.sin(age * 60)
        return Z, cx, cy, dy

    def xf(self, s):
        Z, cx, cy, dy = self.cam(s)
        X = lambda x: (x - cx) * Z + 540
        Y = lambda y: (y - cy) * Z + 1100 + dy
        return X, Y, Z

    # ------------------------------------------------------------------ le docteur
    def hands(self, s, t):
        """Les deux mains du docteur (gauche vers Bounce, droite vers le tableau) et ce
        qu'il tient."""
        lrest = (DOC_X - 74, 1205.0)
        rrest = (DOC_X + 74, 1205.0)
        L, Rh = lrest, rrest
        prop = self.prop
        by = s["by"]
        qe = self.q_end_local or 99.0

        def ease(a, b, t0, t1):
            k = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
            k = k * k * (3 - 2 * k)
            return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)

        def reach(target, t0, t1, t2, t3, rest=lrest):
            if t < t2:
                return ease(rest, target, t0, t1)
            return ease(target, rest, t2, t3)
        qs = self.q_start_local if self.q_start_local is not None else 0.0
        if prop == "stick":
            L = reach((BX + self.R + 96, by + 6), qs - 0.3, qs + 0.3, qe + 0.05, qe + 0.4)
        elif prop == "steth":
            L = reach((BX + self.R + 16 + 12, by), qs - 0.2, qs + 0.4, qe + 0.05, qe + 0.4)
        elif prop == "hammer":
            tap = s["tap"] if s["tap"] is not None else 99.0
            wind = (BX + self.R + 83 + 90, surf_y() - 50)
            hit = (BX + self.R + 83, surf_y())
            if t < tap - 0.14:
                L = ease(lrest, wind, qe - 0.2, tap - 0.3)
            elif t < tap:
                L = ease(wind, hit, tap - 0.14, tap)
            else:
                L = ease(hit, lrest, tap + 0.05, tap + 0.6)
        elif prop == "point":
            Rh = reach((CHART[0] + 6, CHART[2] + 40), qs - 0.2, qs + 0.4, qe + 0.3, qe + 0.8, rest=rrest)
        elif prop in ("clip", "write"):
            Rh = (DOC_X + 30, 1130.0)
            if prop == "write" and t < (self.q_start_local or 99.0) + 0.1:
                L = (DOC_X + 22 + 16 * math.sin(t * 9.0), 1118.0 + 8 * math.sin(t * 23.0))
            else:
                L = (DOC_X - 30, 1170.0)
        return L, Rh

    def draw_doctor(self, dr, X, Y, Q, s, t):
        qe = self.q_end_local or 0.0
        qs = self.q_start_local or 0.0
        talking = qs <= t < qe
        if s["ans"] is not None and self.react:
            talking = talking or 0.9 <= t - s["ans"] < 2.0
        if self.kind == "reflex" and s.get("land") is not None:
            talking = 0.5 <= t - s["land"] < 1.7
        talk = 3.0 * math.sin(t * 22) if talking else 0.0
        ba = t - getattr(self, "bonk_t", -9.0)
        if 0 <= ba < 0.6:
            talk += 14.0 * math.exp(-ba * 6) * abs(math.cos(ba * 18))
        lean = 14.0 * math.sin(t * 3.4) if talking else 0.0
        hop = getattr(self, "doc_hop", lambda t: 0.0)(t)
        x = DOC_X + lean * 0.5
        yo = -hop
        # jambes, blouse, tête (sans visage), miroir frontal
        rr(dr, [X(x - 42), Y(1430 + yo), X(x - 10), Y(FLOOR_Y + yo)], fill=(40, 44, 60))
        rr(dr, [X(x + 10), Y(1430 + yo), X(x + 42), Y(FLOOR_Y + yo)], fill=(40, 44, 60))
        rr(dr, [X(x - 58), Y(1000 + yo), X(x + 58), Y(1440 + yo)], fill=COAT)
        dr.polygon([(X(x - 22), Y(1000 + yo)), (X(x + 22), Y(1000 + yo)), (X(x), Y(1090 + yo))], fill=(70, 110, 130))
        dr.line([(X(x - 22), Y(1000 + yo)), (X(x), Y(1180 + yo))], fill=dim(COAT, 0.75), width=max(1, int(Q(4))))
        dr.line([(X(x + 22), Y(1000 + yo)), (X(x), Y(1180 + yo))], fill=dim(COAT, 0.75), width=max(1, int(Q(4))))
        rr(dr, [X(x + 18), Y(1110 + yo), X(x + 46), Y(1116 + yo)], fill=dim(COAT, 0.75))
        circle(dr, X(x), Y(945 + talk + yo), Q(44), HEAD)
        hx, hy = x - 4, 912 + talk + yo
        dr.line([(X(x - 42), Y(hy + 4)), (X(x + 42), Y(hy + 4))], fill=(50, 54, 70), width=max(1, int(Q(6))))
        circle(dr, X(hx), Y(hy), Q(17), (200, 204, 214))
        circle(dr, X(hx), Y(hy), Q(7), (120, 124, 140))
        Lh, Rh = self.hands(s, t)
        Lh = (Lh[0], Lh[1] + yo); Rh = (Rh[0], Rh[1] + yo)
        # le stéthoscope autour du cou
        dr.line([(X(x - 26), Y(1004 + yo)), (X(x - 30), Y(1060 + yo)), (X(x - 16), Y(1100 + yo))], fill=(30, 32, 40), width=max(1, int(Q(6))), joint="curve")
        dr.line([(X(x + 26), Y(1004 + yo)), (X(x + 30), Y(1060 + yo)), (X(x + 16), Y(1100 + yo))], fill=(30, 32, 40), width=max(1, int(Q(6))), joint="curve")
        if self.prop == "steth":
            dr.line([(X(x - 16), Y(1100 + yo)), (X(x - 50), Y(1170 + yo)), (X(Lh[0]), Y(Lh[1]))], fill=(30, 32, 40), width=max(1, int(Q(6))), joint="curve")
        else:
            dr.line([(X(x - 16), Y(1100 + yo)), (X(x), Y(1130 + yo)), (X(x + 16), Y(1100 + yo))], fill=(30, 32, 40), width=max(1, int(Q(6))), joint="curve")
            circle(dr, X(x), Y(1134 + yo), Q(12), (170, 176, 190))
        # le bras droit, le presse-papiers
        rsh = (x + 50, 1020 + yo)
        if self.prop in ("clip", "write"):
            cx_, cy_ = Rh
            rr(dr, [X(cx_ - 44), Y(cy_ - 56), X(cx_ + 44), Y(cy_ + 56)], fill=WOOD)
            rr(dr, [X(cx_ - 36), Y(cy_ - 44), X(cx_ + 36), Y(cy_ + 50)], fill=(240, 240, 236))
            rr(dr, [X(cx_ - 16), Y(cy_ - 62), X(cx_ + 16), Y(cy_ - 50)], fill=METAL)
            for k in range(4):
                rr(dr, [X(cx_ - 26), Y(cy_ - 26 + k * 18), X(cx_ + 22 - 10 * (k % 2)), Y(cy_ - 22 + k * 18)], fill=(150, 150, 160))
        dr.line([(X(rsh[0]), Y(rsh[1])), (X(Rh[0]), Y(Rh[1]))], fill=dim(COAT, 0.9), width=max(1, int(Q(24))))
        circle(dr, X(Rh[0]), Y(Rh[1]), Q(14), HEAD)
        # le bras gauche et ce qu'il tient
        lsh = (x - 50, 1020 + yo)
        dr.line([(X(lsh[0]), Y(lsh[1])), (X(Lh[0]), Y(Lh[1]))], fill=dim(COAT, 0.9), width=max(1, int(Q(24))))
        hx, hy = Lh
        if self.prop == "stick":
            rr(dr, [X(hx - 92), Y(hy - 7), X(hx - 4), Y(hy + 7)], fill=(222, 196, 150))
        elif self.prop == "steth":
            circle(dr, X(hx - 14), Y(hy), Q(14), (176, 182, 196))
            circle(dr, X(hx - 14), Y(hy), Q(8), (120, 126, 140))
        elif self.prop == "hammer":
            rr(dr, [X(hx - 72), Y(hy - 4), X(hx + 6), Y(hy + 4)], fill=(200, 200, 210))
            dr.polygon([(X(hx - 83), Y(hy)), (X(hx - 64), Y(hy - 24)), (X(hx - 64), Y(hy + 24))], fill=(210, 60, 60))
        elif self.prop == "write":
            rr(dr, [X(hx - 3), Y(hy - 40), X(hx + 3), Y(hy)], fill=(40, 40, 50))
        circle(dr, X(hx), Y(hy), Q(14), HEAD)

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, s, t, S):
        X0, Y0, Z = self.xf(s)
        X = lambda x: X0(x) * S
        Y = lambda y: Y0(y) * S
        Q = lambda v: v * Z * S
        P = lambda v: v * S
        W, H = self.W, self.H
        rr(dr, [0, P(SCENE_TOP), P(W), P(H)], fill=dim(WALL, 0.7))
        rr(dr, [X(WL), Y(CEIL), X(WR), Y(FLOOR_Y)], fill=WALL)
        rr(dr, [X(WL), Y(CEIL), X(WR), Y(CEIL + 10)], fill=dim(WALL, 1.4))
        # la lampe du plafond (elle se fend si on la touche)
        lx0, lx1 = 300.0, 480.0
        rr(dr, [X(lx0), Y(CEIL), X(lx1), Y(CEIL + 18)], fill=(220, 214, 180))
        if s["crack"] is not None:
            c = min(lx1 - 10, max(lx0 + 10, s["crack"]))
            dr.line([(X(c - 30), Y(CEIL + 2)), (X(c - 6), Y(CEIL + 12)), (X(c + 12), Y(CEIL + 4)), (X(c + 34), Y(CEIL + 16))], fill=(60, 60, 60), width=max(1, int(Q(3))))
        # la toise, au mur derrière la table
        rr(dr, [X(30), Y(780), X(54), Y(FLOOR_Y)], fill=(70, 84, 96))
        for k in range(15):
            yy = FLOOR_Y - 40 - k * 48
            rr(dr, [X(30), Y(yy), X(30 + (20 if k % 2 == 0 else 12)), Y(yy + 4)], fill=(170, 180, 190))
        # le tableau de lettres
        if s["chart"] == "wall":
            ch = {"x": (CHART[0] + CHART[1]) / 2, "y": (CHART[2] + CHART[3]) / 2, "a": s["chart_a"]}
            self.draw_chart(dr, X, Y, Q, ch, CHART[1] - CHART[0], CHART[3] - CHART[2], pivot=True)
            circle(dr, X((CHART[0] + CHART[1]) / 2), Y(CHART[2] - 6), Q(5), (40, 40, 50))
        # le sol
        rr(dr, [0, Y(FLOOR_Y), P(W), P(H)], fill=FLOOR)
        rr(dr, [0, Y(FLOOR_Y), P(W), Y(FLOOR_Y + 6)], fill=dim(FLOOR, 1.35))
        # le meuble
        x0, x1, top = COUNTER
        rr(dr, [X(x0), Y(top), X(x1), Y(FLOOR_Y)], fill=(70, 78, 92))
        rr(dr, [X(x0 - 6), Y(top), X(x1 + 6), Y(top + 12)], fill=(150, 156, 168))
        for k in range(2):
            yy = top + 40 + k * 130
            rr(dr, [X(x0 + 10), Y(yy), X(x1 - 10), Y(yy + 110)], outline=(52, 58, 70), width=max(1, int(Q(4))))
            rr(dr, [X((x0 + x1) / 2 - 16), Y(yy + 10), X((x0 + x1) / 2 + 16), Y(yy + 16)], fill=(150, 156, 168))
        # les objets tombés, puis le docteur devant
        for o in s["objs"]:
            self.draw_obj(dr, X, Y, Q, o, s)
        for p in s["sticks"]:
            pts = body_poly({"x": p["x"], "y": p["y"], "a": p["a"]}, rect(54, 8))
            dr.polygon([(X(x), Y(y)) for (x, y) in pts], fill=(222, 196, 150))
        self.draw_doctor(dr, X, Y, Q, s, t)
        # la table d'examen
        tx0, tx1, ttop = TABLE
        if s["table"] == "ok":
            for lx in (tx0 + 20, tx1 - 20):
                rr(dr, [X(lx - 7), Y(ttop + CUSH_H), X(lx + 7), Y(FLOOR_Y)], fill=METAL)
            rr(dr, [X(tx0 + 14), Y(ttop + CUSH_H), X(tx1 - 14), Y(ttop + CUSH_H + 14)], fill=dim(METAL, 0.8))
        else:
            k = s["legs"]
            for sg, lx in ((-1, tx0 + 20), (1, tx1 - 20)):
                a = sg * k * 1.45
                L = FLOOR_Y - ttop - CUSH_H
                fx = lx + sg * 0.0
                ex, ey = fx + math.sin(a) * L, FLOOR_Y - math.cos(a) * L
                pts = [(fx - 7 * math.cos(a), FLOOR_Y - 7 * math.sin(a) - 7), (fx + 7 * math.cos(a), FLOOR_Y + 7 * math.sin(a) - 7),
                       (ex + 7 * math.cos(a), ey + 7 * math.sin(a) - 7), (ex - 7 * math.cos(a), ey - 7 * math.sin(a) - 7)]
                dr.polygon([(X(px), Y(py)) for (px, py) in pts], fill=METAL)
        cy_ = s["cush_y"]
        rr(dr, [X(tx0), Y(cy_), X(tx1), Y(cy_ + CUSH_H)], fill=CUSHION)
        rr(dr, [X(tx0 + 10), Y(cy_), X(tx1 - 10), Y(cy_ + 6)], fill=(232, 232, 226))
        base.ball(dr, X(s["bx"]), Y(s["by"]), Q(self.R))
        self.extra(dr, X, Y, Q, P, s, t)
        self.bubble(dr, X, Y, Q, P, s, t)
        rr(dr, [0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))

    def extra(self, dr, X, Y, Q, P, s, t):
        pass

    def draw_chart(self, dr, X, Y, Q, o, w, h, pivot=False):
        if pivot:
            # il pend à son clou : rotation autour du haut
            px, py = o["x"], CHART[2]
            ca, sa = math.cos(o["a"]), math.sin(o["a"])
            def tr(dx, dy):
                dy2 = dy + h / 2
                return (px + dx * ca - dy2 * sa, py + dx * sa + dy2 * ca)
        else:
            ca, sa = math.cos(o["a"]), math.sin(o["a"])
            def tr(dx, dy):
                return (o["x"] + dx * ca - dy * sa, o["y"] + dx * sa + dy * ca)
        poly = [tr(-w / 2, -h / 2), tr(w / 2, -h / 2), tr(w / 2, h / 2), tr(-w / 2, h / 2)]
        dr.polygon([(X(x), Y(y)) for (x, y) in poly], fill=(236, 236, 228))
        if abs(math.sin(o["a"])) > 0.5 and not pivot:
            for dy, ln in ((-52, 14), (-14, 26), (16, 36), (40, 46), (60, 56)):
                a_, b_ = tr(-ln / 2, dy), tr(ln / 2, dy)
                dr.line([(X(a_[0]), Y(a_[1])), (X(b_[0]), Y(b_[1]))], fill=(40, 40, 50), width=max(1, int(Q(9 if dy < 0 else 5))))
            return
        # les lettres, de plus en plus petites : un gros E en haut
        rows = [("E", 44, -52), ("F P", 24, -10), ("T O Z", 16, 20), ("L P E D", 11, 44), ("P E C F D", 8, 62)]
        for txt, sz, dy in rows:
            cx, cy = tr(0, dy)
            dr.text((X(cx), Y(cy)), txt, fill=(30, 30, 40), anchor="mm", font=base.font(Q(sz)))

    def draw_obj(self, dr, X, Y, Q, o, s):
        k = o["kind"]
        if k == "chart":
            o2 = {"x": o["x"], "y": o["y"], "a": o["a"] - math.pi / 2}
            self.draw_chart(dr, X, Y, Q, o2, o["ht"], o["wd"])
            return
        poly = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"], o["ht"]))]
        if k == "jar":
            dr.polygon(poly, fill=dim(o["col"], 0.55))
            inner = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"] - 10, o["ht"] - 10))]
            dr.polygon(inner, fill=dim(o["col"], 0.38))
            if s["jar_full"]:
                for j in range(5):
                    p = body_poly(o, [(-22 + j * 11, -o["ht"] / 2 - 18), (-22 + j * 11 + 6, -o["ht"] / 2 - 18), (-22 + j * 11 + 6, 10), (-22 + j * 11, 10)])
                    dr.polygon([(X(x), Y(y)) for (x, y) in p], fill=(222, 196, 150))
            lid = body_poly(o, [(-o["wd"] / 2 - 3, -o["ht"] / 2), (o["wd"] / 2 + 3, -o["ht"] / 2), (o["wd"] / 2 + 3, -o["ht"] / 2 + 8), (-o["wd"] / 2 - 3, -o["ht"] / 2 + 8)])
            dr.polygon([(X(x), Y(y)) for (x, y) in lid], fill=dim(o["col"], 0.8))
            return
        if k == "tissue":
            dr.polygon(poly, fill=o["col"])
            p = body_poly(o, [(-8, -o["ht"] / 2), (8, -o["ht"] / 2), (14, -o["ht"] / 2 - 18), (-12, -o["ht"] / 2 - 14)])
            dr.polygon([(X(x), Y(y)) for (x, y) in p], fill=(244, 244, 248))
            return
        dr.polygon(poly, fill=o["col"])

    def bubble(self, dr, X, Y, Q, P, s, t):
        """Ce qu'il a dit (« BOUNCE. », en gros), puis ce qu'il voulait dire."""
        if s["ans"] is None or not self.tr:
            return
        age = s["t"] - s["ans"]
        k = min(1.0, age / 0.15)
        x0, x1, y0 = 30.0, 610.0, 448.0
        f2 = base.font(P(58))
        rows, cur = [], ""
        for w in self.tr.split():
            cand = (cur + " " + w).strip()
            if base.text_w(f2, cand) <= P(x1 - x0 - 90) or not cur:
                cur = cand
            else:
                rows.append(cur); cur = w
        rows.append(cur)
        row0 = y0 + 236
        y1 = row0 + (len(rows) - 1) * 70 + 52
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sc = 0.6 + 0.4 * k
        bx0, bx1 = cx - (cx - x0) * sc, cx + (x1 - cx) * sc
        by0, by1 = cy - (cy - y0) * sc, cy + (y1 - cy) * sc
        tx, ty = X(s["bx"]), Y(s["by"]) - Q(self.R) - P(6)
        dr.polygon([(P(150), P(by1 - 4)), (P(250), P(by1 - 4)), (tx, max(ty, P(by1 + 30)))], fill=(250, 250, 252))
        dr.rounded_rectangle([P(bx0), P(by0), P(bx1), P(by1)], radius=int(P(30)), fill=(250, 250, 252), outline=(20, 20, 26), width=max(1, int(P(5))))
        if k < 1.0:
            return
        f1 = base.font(P(80))
        dr.text((P(cx), P(y0 + 72)), "“BOUNCE.”", fill=PINK, anchor="mm", font=f1, stroke_width=max(1, int(P(3))), stroke_fill=(120, 0, 80))
        if age < 0.45:
            return
        dr.text((P(cx), P(y0 + 158)), "means:", fill=(110, 110, 130), anchor="mm", font=base.font(P(38)))
        for i, row in enumerate(rows):
            dr.text((P(cx), P(row0 + i * 70)), row, fill=(20, 20, 26), anchor="mm", font=f2)


class Rx(Visit):
    """L'ordonnance : le docteur écrit, et lâche lui-même un « ...Bounce. »."""
    kind = "rx"
    prop = "write"
    mood = "win"
    hold_s = 1.9
    stamp = None
    RX_TEXT = "Stop bouncing."

    def make_plan(self):
        self.plan = []

    def tick(self):
        if self.q_end_local is not None and self.t >= self.q_end_local + 0.15 and self.end_t is None:
            self.finish("CONTAGIOUS")

    def doc_hop(self, t):
        qs = self.q_start_local
        if qs is None:
            return 0.0
        te = t - (qs + 0.05)
        T = 0.42
        if 0 <= te <= T:
            return 4.0 * 34.0 * te * (T - te) / (T * T)
        return 0.0

    def extra(self, dr, X, Y, Q, P, s, t):
        """La feuille d'ordonnance, en haut à gauche, qui s'écrit."""
        k = min(1.0, max(0.0, (t - 0.2) / 0.25))
        if k <= 0:
            return
        x0, x1, y0, y1 = 30.0, 540.0, 450.0, 690.0
        sc = 0.7 + 0.3 * k
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dr.rounded_rectangle([P(cx - (cx - x0) * sc), P(cy - (cy - y0) * sc), P(cx + (x1 - cx) * sc), P(cy + (y1 - cy) * sc)],
                             radius=int(P(18)), fill=(246, 246, 240), outline=(20, 20, 26), width=max(1, int(P(5))))
        if k < 1.0:
            return
        dr.text((P(x0 + 30), P(y0 + 30)), "PRESCRIPTION", fill=(110, 110, 130), anchor="lm", font=base.font(P(30)))
        dr.text((P(x0 + 30), P(y0 + 100)), "Rx", fill=(30, 60, 140), anchor="lm", font=base.font(P(64)))
        n = int(max(0.0, (t - 0.55) / 0.07))
        txt = self.RX_TEXT[:n]
        dr.text((P(x0 + 130), P(y0 + 104)), txt, fill=(30, 60, 140), anchor="lm", font=base.font(P(40)))
        dr.line([(P(x0 + 30), P(y0 + 148)), (P(x1 - 30), P(y0 + 148))], fill=(180, 180, 190), width=max(1, int(P(3))))
        # le tampon, quand le « ...Bounce. » lui a échappé
        if s.get("end") is not None:
            age = t - s["end"]
            kk = min(1.0, age / 0.2)
            size = 58 + 24 * (1 - kk)
            f = base.font(P(size))
            while base.text_w(f, "CONTAGIOUS.") > P(x1 - x0 - 40) and size > 30:
                size -= 2; f = base.font(P(size))
            dr.text((P((x0 + x1) / 2), P(y0 + 196)), "CONTAGIOUS.", fill=(235, 70, 80), anchor="mm", font=f,
                    stroke_width=max(1, int(P(4))), stroke_fill=(90, 10, 20))


class Reflex(Visit):
    kind = "reflex"
    prop = "hammer"


# ---------------------------------------------------------------- la visite
# (label, question, traduction, réplique du docteur, rebonds parlés, accessoire)
VISIT = [
    ("MOUTH", "Say ahh.", "Ahh.", "Close enough.", 1, "stick"),
    ("SYMPTOMS", "Any symptoms?", "None.", "I see one.", 2, "clip"),
    ("PAIN", "Does this hurt?", "No. Does this?", "A little.", 2, "steth"),
    ("FITNESS", "Do you exercise?", "Constantly.", "Clearly.", 2, "clip"),
    ("FAMILY", "Any family history?", "Dad was a trampoline.", "That explains it.", 2, "clip"),
    ("EYES", "Read the top line.", "It says Bounce.", "It said E.", 1, "point"),
    ("REFLEXES", "Let's check your reflexes.", "", "Reflexes: excellent.", 0, "hammer"),
    ("DIAGNOSIS", "Diagnosis: chronic bouncing.", "Is it serious?", "Very.", 2, "clip"),
    ("PRESCRIPTION", "...Bounce.", "", "", 0, "write"),
]


def make(n, label, q, tr, react, nhops, prop):
    base_cls = Reflex if prop == "hammer" else Rx if prop == "write" else Visit
    cls = type(f"V{n}", (base_cls,), {})
    cls.n, cls.N, cls.level = n, len(VISIT), n
    cls.label, cls.q, cls.tr, cls.react, cls.nhops, cls.prop = label, q, tr, react, nhops, prop
    return cls


CHAPTERS = [(make(i + 1, *v), ({"chapter_max_s": 17.0} if v[5] == "hammer" else {})) for i, v in enumerate(VISIT)]

DEFAULTS = {
    "ball_r": R_B, "gravity": G,
    "chapter_max_s": 12.0,
    "counter_font_size": 66, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.6, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        CLINIC.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)

    def _open(self, i):
        s = self.sims[i]
        if s.kind == "question":
            s.replies = [("title", s.reply_delay())]
        start = max(self.t + (2.45 if s.n == 1 else 0.0), self.narr_free + self.cfg["narr_gap_s"])
        if s.kind == "rx":
            # il écrit d'abord ; le « ...Bounce. » lui échappe ensuite
            s.lines = [(2.6, s.q, "title")]
            start = max(self.t + 2.6, self.narr_free + self.cfg["narr_gap_s"])
        q_end = start + self.narr_dur(s.q)
        super()._open(i)
        end = self._line_end.get(f"{i}:title", q_end)
        s.q_end_local = end - self.t0
        s.q_start_local = end - self.narr_dur(s.q) - self.t0
        if s.kind == "question":
            s.reply_local = end + s.reply_delay() - self.t0 + 1.0 / self.cfg["fps"]


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
