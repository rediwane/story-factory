"""
Prototype « l'entretien » : Bounce passe un entretien d'embauche. Le recruteur (une
silhouette sans visage derrière son bureau, la voix du narrateur) lui pose des questions ;
Bounce ne sait répondre que « Bounce ». Une bulle traduit ce qu'il voulait dire.

Il reste sagement assis pendant que le recruteur parle ; dès que c'est son tour, il
rebondit (et dit son nom à chaque retombée), puis répond d'un grand rebond qui secoue
tout le bureau. Les dégâts restent d'une question à l'autre.

    python3 src/stories/interview.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle
from chapters import StorySim
from listkit import Chapter, FLOOR_Y, SCENE_TOP, glow, mix, settle_body, separate, body_poly

R_BOUNCE = 68.0
G = 3000.0
SEAT_Y = 1250.0
DESK = (380.0, 760.0, 1180.0)          # x0, x1, dessus
BX = 210.0                             # Bounce sur sa chaise
ZONE = BX + R_BOUNCE + 40.0            # à gauche de ça : la place de Bounce, aucun objet n'y reste
XMAX = 760.0                           # à droite de ça : les boutons de TikTok
WIN = (400.0, 640.0, 700.0, 1010.0)    # la fenêtre, derrière le recruteur
STUB = 1400.0                          # le dessus du pied du bureau, une fois le plateau cassé
HOP_T = 0.92                           # un petit rebond : assez long pour dire son nom en entier
PAUSE = 0.35                           # le temps de se concentrer, avant le grand rebond
BIG_T = 0.95
WALL = (36, 38, 56)
CARPET = (52, 48, 60)
WOOD = (122, 86, 58)
PINK = (255, 60, 200)

# l'état du bureau, qui passe d'une question à la suivante (remis à zéro par Sim)
OFFICE = {}


def rr(dr, box, **kw):
    """Un rectangle qui accepte des coins dans le désordre (la caméra peut les retourner)."""
    x0, y0, x1, y1 = box
    dr.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], **kw)


def rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def new_obj(objs, kind, x, y, width, height, tier, col, a=0.0, rest=True, **kw):
    """Les objets allongés sont rangés « couchés » (le grand côté en largeur) : ils ne
    peuvent se poser qu'à plat, jamais sur la tranche."""
    if height > width:
        width, height, a = height, width, a + math.pi / 2
    o = {"id": kw.pop("oid", len(objs)), "kind": kind, "x": x, "y": y, "a": a, "vx": 0.0, "vy": 0.0, "w": 0.0,
         "wd": width, "ht": height, "tier": tier, "col": col, "rest": rest, "free": not rest, "ph": 0.0,
         "flat": math.pi if width / height >= 1.6 else math.pi / 2}
    o.update(kw)
    objs.append(o)
    return o


def fresh_office():
    objs = []
    top = DESK[2]
    new_obj(objs, "lamp", 402.0, top - 60, 30.0, 120.0, 7, (230, 190, 90))
    new_obj(objs, "mug", 452.0, top - 27, 44.0, 54.0, 1, (236, 236, 240))
    new_obj(objs, "plate", 535.0, top - 20, 120.0, 40.0, 2, (200, 170, 90))
    new_obj(objs, "laptop", 662.0, top - 52, 120.0, 104.0, 6, (150, 152, 166))
    new_obj(objs, "stack", 741.0, top - 23, 36.0, 46.0, 3, (238, 238, 230))
    return {"objs": objs, "papers": [], "chair": "ok", "desk": "ok", "spill": 0.0, "crack": None, "frame": "wall"}


class Question(Chapter):
    """Une question : le recruteur demande, Bounce attend son tour, rebondit, répond
    d'un grand rebond ; la bulle traduit ; le bureau encaisse."""
    hold_s = 0.6
    stamp = None
    level = 1
    q = ""
    tr = ""
    react = ""
    nhops = 1

    def setup(self):
        self.R = R_BOUNCE
        self.bx, self.by = BX, SEAT_Y - self.R
        self.vx = self.vy = 0.0
        self.on = "sit"
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.reply_local = None
        self.q_end_local = None
        self.hop = None                  # (départ, durée, grand ?)
        self.plan = []
        self.started = False
        self.impact_t = -9.0
        self.answer_at = None
        self.title = f"QUESTION {self.n} / {self.N}"
        self.line(self.q, "title", 2.45 if self.n == 1 else 0.0)
        self.rng2 = np.random.default_rng(100 + self.level)

    @classmethod
    def reply_delay(cls):
        """De la fin de la question à sa réponse : un temps, ses petits rebonds, une
        pause, le grand rebond."""
        return 0.15 + cls.nhops * HOP_T + (0.25 if cls.n == 1 else PAUSE) + BIG_T

    # ------------------------------------------------------------------ Bounce
    def floor_y(self):
        return (SEAT_Y if OFFICE["chair"] == "ok" else FLOOR_Y) - self.R

    def make_plan(self):
        t0 = self.q_end_local + 0.15
        self.plan = [(t0 + k * HOP_T, HOP_T, False) for k in range(self.nhops)]
        self.plan.append((self.reply_local - BIG_T, BIG_T, True))

    def step(self, dt):
        self.t += dt
        evs = []
        if not self.started:
            self.started = True
            if not OFFICE:
                OFFICE.update(fresh_office())
            self.make_plan()
        if self.hop is None and self.plan and self.t >= self.plan[0][0]:
            self.hop = self.plan.pop(0)
        if self.hop is not None:
            t0, T, big = self.hop
            te = self.t - t0
            if te >= T - 1e-9:
                self.by = self.floor_y()
                if self.t - self.last_hit >= 0.15:
                    self.last_hit = self.t; self.hits += 1
                    evs.append(("hit", "floor"))
                self.hit_t = self.t
                self.hop = None
                if big:
                    self.impact()
                    self.answer_at = self.t + 0.3       # la bulle de traduction, juste après son « Bounce »
            else:
                v = G * T / 2
                self.by = self.floor_y() - (v * te - 0.5 * G * te * te)
        else:
            self.by = self.floor_y()
        wait = self.hop is None
        self.bx = BX + (5.0 * math.sin(self.t * 37.0) if wait else 0.0)       # l'impatience
        if self.answer_at is not None and self.t >= self.answer_at and self.end_t is None:
            self.finish("ANSWER")
            self.on_answer()
        self.physics(dt)
        return evs

    # ------------------------------------------------------------------ le bureau
    def kick(self, o, power, side_bias=0.8, vx=None):
        side = 1.0 if self.rng2.random() < side_bias else -1.0
        o["rest"] = False
        o["free"] = True
        o["vy"] = -power * float(self.rng2.uniform(0.8, 1.2))
        o["vx"] = vx if vx is not None else side * float(self.rng2.uniform(60, 220)) * (0.6 + 0.1 * self.level)
        o["w"] = float(self.rng2.uniform(-7, 7))

    def impact(self):
        """Le grand rebond : tout ce qui est sur le bureau saute, de plus en plus fort."""
        self.impact_t = self.t
        L = self.level
        for o in OFFICE["objs"]:
            if o.get("gone"):
                continue
            if o["tier"] == L:
                if o["kind"] == "lamp":
                    self.kick(o, 1100, vx=170.0)          # la lampe part droit dans la vitre
                else:
                    self.kick(o, 700 + 60 * L, 0.5)
            elif o["tier"] < L and o["free"] and o["kind"] not in ("wood", "slab"):
                self.kick(o, 260 + 40 * L, 0.5)
        if L == 1:
            OFFICE["spill_on"] = True
        if L == 3:
            st = [o for o in OFFICE["objs"] if o["kind"] == "stack"][0]
            st["gone"] = True
            for k in range(14):
                OFFICE["papers"].append({"id": 100 + k, "x": st["x"] + float(self.rng2.uniform(-20, 20)), "y": st["y"] - 10,
                                         "vx": float(self.rng2.uniform(-420, 120)), "vy": -float(self.rng2.uniform(600, 1000)),
                                         "a": 0.0, "ph": float(self.rng2.uniform(0, 6)), "rest": False})
        if L == 4:
            OFFICE["frame"] = "down"
            new_obj(OFFICE["objs"], "frame", 300.0 + 75.0, 980.0, 110.0, 84.0, 4, (150, 120, 60), rest=False,
                    oid=50, vx=60.0, vy=-200.0, w=2.5)
        if L == 5:
            self.break_chair()
        if L == 9:
            self.break_desk()
        for p in OFFICE["papers"]:
            if p["rest"] and L > 3:
                p["rest"] = False
                p["vy"] = -float(self.rng2.uniform(250, 500)); p["vx"] = float(self.rng2.uniform(-150, 150))

    def break_chair(self):
        OFFICE["chair"] = "broken"
        objs = OFFICE["objs"]
        # l'assise se fend : une moitié part à gauche, l'autre et le dossier à droite
        new_obj(objs, "wood", BX - 50, SEAT_Y + 10, 96.0, 18.0, 5, WOOD, rest=False, oid=60, vx=-760.0, vy=-380.0, w=-6.0)
        new_obj(objs, "wood", BX + 50, SEAT_Y + 10, 96.0, 18.0, 5, WOOD, rest=False, oid=61, vx=330.0, vy=-420.0, w=6.0)
        # le dossier est trop long pour la place à gauche : il part à droite
        new_obj(objs, "wood", BX + 20, 1150.0, 18.0, 200.0, 5, WOOD, rest=False, oid=62, vx=700.0, vy=-420.0, w=4.0)

    def break_desk(self):
        """Le plateau casse en deux planches, le pied du bureau s'écrase en tas."""
        OFFICE["desk"] = "broken"
        x0, x1, top = DESK
        mid = (x0 + x1) / 2
        objs = OFFICE["objs"]
        for k, cx in enumerate(((x0 + mid) / 2, (mid + x1) / 2)):
            new_obj(objs, "slab", cx, top + 13, (x1 - x0) / 2 - 10, 26.0, 9, WOOD,
                    rest=False, oid=70 + k, vx=(-1 if k == 0 else 1) * 60.0, vy=-380.0, w=(-1 if k == 0 else 1) * 3.0)
        for o in objs:
            if o["kind"] not in ("slab",) and not o.get("gone") and o["rest"]:
                o["rest"] = False; o["free"] = True

    @staticmethod
    def aabb(o):
        pts = body_poly(o, rect(o["wd"], o["ht"]))
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def ground(self, o):
        """Le sol d'un objet : le bureau (ou ce qu'il en reste), la moquette, ou le dessus
        d'un objet posé juste en dessous, seulement si son centre de gravité est au-dessus
        de cet appui."""
        x0, x1, top = DESK
        if o["kind"] == "wood":
            return FLOOR_Y                    # les planches de la chaise tombent devant le bureau, au sol
        if OFFICE["desk"] == "ok":
            g = top if (x0 <= o["x"] <= x1 and o["y"] < top) else FLOOR_Y
        else:
            g = STUB if (x0 + 16 <= o["x"] <= x1 - 16 and o["y"] < STUB) else FLOOR_Y
        if o["kind"] in ("slab",):
            return g                          # les gros débris reposent sur le bureau ou le sol, jamais en équilibre
        ax0, ay0, ax1, ay1 = self.aabb(o)
        for r in OFFICE["objs"]:
            if r is o or not r["rest"] or r.get("gone"):
                continue
            bx0, by0, bx1, by1 = self.aabb(r)
            flat = abs(math.sin(2 * r["a"])) < 0.05            # un dessus horizontal
            wide = (bx1 - bx0) >= 0.9 * (ax1 - ax0)             # et assez large pour le porter
            tol = 6.0 + max(0.0, o["vy"]) / 60.0 + 2.0
            if flat and wide and bx0 + 6 <= o["x"] <= bx1 - 6 and ay1 <= by0 + tol and by0 < g:
                g = by0
        return g

    def bounds(self, o):
        x0, y0, x1, y1 = self.aabb(o)
        hw = 0.5 * (x1 - x0)
        if o["kind"] == "wood" and o["x"] < BX:
            # une planche partie à gauche de Bounce reste à gauche de sa place
            return 30.0 + hw, max(30.0 + hw, BX - self.R - 30.0 - hw)
        return ZONE + hw, XMAX - hw

    def physics(self, dt):
        objs = [o for o in OFFICE["objs"] if not o.get("gone")]
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
            if o["y"] < 560 and o["vy"] < 0:
                o["vy"] = -o["vy"] * 0.3
            # la vitre se fend quand un objet la traverse
            if OFFICE["crack"] is None and WIN[0] < o["x"] < WIN[2] and WIN[1] < o["y"] < WIN[3] and o["vy"] < -300:
                OFFICE["crack"] = (o["x"], o["y"])
            settle_body(o, self.ground(o), o["flat"], dt, rect(o["wd"], o["ht"]))
        sep = [o for o in objs if o["free"]]
        fixed = [o for o in objs if not o["free"]]
        for _ in range(3):
            flags = [o["rest"] for o in sep]
            for o in sep:
                o["rest"] = False
            separate(sep + fixed, lambda o: rect(o["wd"], o["ht"]), iters=4, max_step=2.5)
            for o, f in zip(sep, flags):
                o["rest"] = f
            for o in objs:
                if not o["free"]:
                    continue
                lo, hi = self.bounds(o)
                if o["x"] < lo:
                    o["x"] = min(lo, o["x"] + 6.0)
                if o["x"] > hi:
                    o["x"] = max(hi, o["x"] - 6.0)
                # contre un bord, plus rien ne pousse dans le bord
                if o["x"] <= lo + 1.0 and o["vx"] < 0:
                    o["vx"] = 0.0
                if o["x"] >= hi - 1.0 and o["vx"] > 0:
                    o["vx"] = 0.0
                ca, sa = math.cos(o["a"]), math.sin(o["a"])
                low = max(dx * sa + dy * ca for dx, dy in rect(o["wd"], o["ht"]))
                g = self.ground(o)
                if o["y"] + low > g + 0.5:
                    o["y"] = g - low
                elif o["rest"] and o["y"] + low < g - 2:
                    o["rest"] = False
        if OFFICE.get("spill_on"):
            OFFICE["spill"] = min(1.0, OFFICE["spill"] + dt * 0.8)
        for p in OFFICE["papers"]:
            if p["rest"]:
                continue
            p["age"] = p.get("age", 0.0) + dt
            p["vy"] = min(p["vy"] + G * 0.5 * dt, 230.0)
            p["vx"] += math.sin(p["age"] * 5 + p["ph"]) * 420 * dt - p["vx"] * 0.8 * dt
            p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt
            p["a"] = 0.5 * math.sin(p["age"] * 5 + p["ph"]) * min(1.0, p["age"] * 3)
            p["x"] = min(XMAX - 30, max(ZONE + 30, p["x"]))
            gy = FLOOR_Y
            if OFFICE["desk"] == "ok" and DESK[0] <= p["x"] <= DESK[1] and p["y"] < DESK[2] - 2 and p["vy"] > 0:
                gy = DESK[2]
            if p["vy"] > 0 and p["y"] >= gy - 3 and (gy == FLOOR_Y or p["y"] < gy + 6):
                p["y"] = gy - 3; p["rest"] = True; p["a"] = 0.0

    # ------------------------------------------------------------------ récit
    def on_answer(self):
        if self.react:
            self.line(self.react, "react", self.t + 0.85)

    def snapshot(self):
        s = self.base_snap()
        s["objs"] = [dict(o) for o in OFFICE.get("objs", []) if not o.get("gone")]
        s["papers"] = [dict(p) for p in OFFICE.get("papers", [])]
        for k in ("chair", "desk", "spill", "crack", "frame"):
            s[k] = OFFICE.get(k)
        s["impact"] = self.impact_t
        s["ans"] = self.end_t
        return s

    # ------------------------------------------------------------------ caméra et contrôle
    def cam(self, s):
        t = s["t"]
        if self.n == 1:
            k = min(1.0, t / 2.6)
            k = k * k * (3 - 2 * k)
            Z = 2.3 - 1.0 * k + 0.08 * min(1.0, max(0.0, t - 2.6) / 5.0)   # l'ouverture : gros plan sur Bounce, puis tout le bureau
            cx = 250.0 + 210.0 * k
            cyf = 1180.0 + 58.5 * k
        else:
            k = min(1.0, t / 8.0)
            Z = 1.22 + 0.18 * k                      # une lente poussée pendant chaque question
            cx, cyf = 480.0 - 40.0 * k, 1255.0 - 25.0 * k
        dy = 0.0
        age = t - s["impact"]
        if 0 <= age < 0.5:
            dy = 9.0 * math.exp(-age * 7) * math.sin(age * 50)
        return Z, cx, cyf, dy

    def xf(self, s):
        Z, cx, cy, dy = self.cam(s)
        X = lambda x: (x - cx) * Z + 540
        Y = lambda y: (y - cy) * Z + 1100 + dy
        return X, Y, Z

    def hero(self, s):
        X, Y, Z = self.xf(s)
        return (X(s["bx"]), Y(s["by"]), self.R * Z)

    def solids(self, s):
        X, Y, Z = self.xf(s)
        out = []
        if s["desk"] == "ok":
            out.append(("rect", X(DESK[0]), Y(DESK[2]), X(DESK[1]), Y(FLOOR_Y)))
        else:
            out.append(("rect", X(DESK[0] + 16), Y(STUB), X(DESK[1] - 16), Y(FLOOR_Y)))
        if s["chair"] == "ok":
            out.append(("rect", X(116), Y(1040), X(134), Y(SEAT_Y)))
            out.append(("rect", X(116), Y(SEAT_Y), X(304), Y(SEAT_Y + 20)))
        for o in s["objs"]:
            out.append(("poly", [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"], o["ht"]))]))
        return out

    def focus(self, s):
        X, Y, Z = self.xf(s)
        r = self.R * Z
        return (X(s["bx"]) - r - 10, Y(s["by"]) - r - 10, X(s["bx"]) + r + 10, Y(s["by"]) + r + 6)

    def bodies(self, s):
        X, Y, Z = self.xf(s)
        out = []
        for o in s["objs"]:
            if o["free"]:
                poly = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"] - 8, o["ht"] - 8))]
                out.append((o["id"], X(o["x"]), Y(o["y"]), o["a"], poly if o["kind"] not in ("wood",) else None))
        for p in s["papers"]:
            out.append((p["id"], X(p["x"]), Y(p["y"]), p["a"]))
        return out

    # ------------------------------------------------------------------ dessin
    def draw(self, dr, s, t, S):
        X0, Y0, Z = self.xf(s)
        X = lambda x: X0(x) * S
        Y = lambda y: Y0(y) * S
        Q = lambda v: v * Z * S
        P = lambda v: v * S
        W, H = self.W, self.H
        rr(dr, [0, P(SCENE_TOP), P(W), P(H)], fill=WALL)
        # la fenêtre, derrière le recruteur : la ville la nuit
        x0, y0, x1, y1 = WIN
        rr(dr, [X(x0 - 8), Y(y0 - 8), X(x1 + 8), Y(y1 + 8)], fill=(80, 80, 98))
        rr(dr, [X(x0), Y(y0), X(x1), Y(y1)], fill=(16, 22, 44))
        for k, (bx_, bw, bh) in enumerate(((410, 60, 220), (480, 50, 300), (535, 70, 180), (610, 80, 260))):
            rr(dr, [X(bx_), Y(y1 - bh), X(bx_ + bw), Y(y1)], fill=(26, 30, 52))
            for r_ in range(3):
                for c in range(2):
                    if (k + r_ + c) % 2 == 0:
                        rr(dr, [X(bx_ + 10 + c * 22), Y(y1 - bh + 20 + r_ * 40), X(bx_ + 22 + c * 22), Y(y1 - bh + 34 + r_ * 40)], fill=(150, 130, 70))
        rr(dr, [X(547), Y(y0), X(553), Y(y1)], fill=(60, 60, 80))
        rr(dr, [X(x0), Y(820), X(x1), Y(826)], fill=(60, 60, 80))
        if s["crack"]:
            cx, cy = s["crack"]
            for ang in (0.3, 1.4, 2.6, 3.7, 4.9):
                pts = [(cx, cy)]
                for k in range(1, 4):
                    pts.append((cx + 40 * k * math.cos(ang + 0.2 * k), cy + 40 * k * math.sin(ang + 0.2 * k)))
                pts = [(min(x1, max(x0, a)), min(y1, max(y0, b))) for (a, b) in pts]
                dr.line([(X(a), Y(b)) for (a, b) in pts], fill=(210, 220, 240), width=max(1, int(Q(3))))
        # « employé du mois », au mur (il tombe à la question 4)
        if s["frame"] == "wall":
            rr(dr, [X(320), Y(900), X(430), Y(984)], fill=(150, 120, 60))
            rr(dr, [X(328), Y(908), X(422), Y(976)], fill=(60, 64, 84))
            circle(dr, X(375), Y(935), Q(12), (90, 94, 116))
        # l'horloge, qui tourne
        cx, cy = 250.0, 880.0
        circle(dr, X(cx), Y(cy), Q(40), (220, 220, 228))
        circle(dr, X(cx), Y(cy), Q(34), (240, 240, 244))
        a = (t * 6.0) % (2 * math.pi)
        dr.line([(X(cx), Y(cy)), (X(cx + 28 * math.sin(a)), Y(cy - 28 * math.cos(a)))], fill=(200, 40, 40), width=max(1, int(Q(3))))
        dr.line([(X(cx), Y(cy)), (X(cx + 18 * math.sin(1.1)), Y(cy - 18 * math.cos(1.1)))], fill=(30, 30, 40), width=max(1, int(Q(5))))
        # le sol
        rr(dr, [0, Y(FLOOR_Y), P(W), P(H)], fill=CARPET)
        rr(dr, [0, Y(FLOOR_Y), P(W), Y(FLOOR_Y + 6)], fill=dim(CARPET, 1.3))
        # le recruteur : une silhouette sans visage, en costume, derrière le bureau
        talking = s["ans"] is None and t < (self.q_end_local or 0)
        if s["ans"] is not None and self.react:
            talking = 0.9 <= t - s["ans"] < 2.2
        talk = 3.0 * math.sin(t * 22) if talking else 0.0
        lean = 20.0 * math.sin(t * 3.0) if talking else 0.0
        rc = (74, 78, 100)
        rx = 640.0
        rr(dr, [X(rx + 70), Y(1000), X(rx + 86), Y(FLOOR_Y)], fill=(50, 50, 64))
        lx_ = rx - lean
        rr(dr, [X(lx_ - 60), Y(930), X(lx_ + 60), Y(FLOOR_Y)], fill=(46, 50, 70))
        dr.polygon([(X(lx_ - 20), Y(930)), (X(lx_ + 20), Y(930)), (X(lx_), Y(990))], fill=(232, 232, 236))
        dr.polygon([(X(lx_ - 6), Y(940)), (X(lx_ + 6), Y(940)), (X(lx_ + 10), Y(1010)), (X(lx_), Y(1024)), (X(lx_ - 10), Y(1010))], fill=(190, 40, 50))
        rr(dr, [X(lx_ - 70), Y(950), X(lx_ - 48), Y(1150)], fill=(46, 50, 70))
        rr(dr, [X(lx_ + 48), Y(950 - 1.5 * lean), X(lx_ + 70), Y(1150)], fill=(46, 50, 70))   # il gesticule
        circle(dr, X(lx_), Y(880 + talk), Q(44), rc)
        # le bureau
        if s["desk"] == "ok":
            x0, x1, top = DESK
            rr(dr, [X(x0 + 16), Y(top + 24), X(x1 - 16), Y(FLOOR_Y)], fill=dim(WOOD, 0.7))
            rr(dr, [X(x0), Y(top), X(x1), Y(top + 26)], fill=WOOD)
            rr(dr, [X(x0), Y(top), X(x1), Y(top + 5)], fill=mix(WOOD, (255, 230, 190), 0.3))
            if s["spill"] > 0:
                w = 80 * s["spill"]
                dr.ellipse([X(458 - w * 0.3), Y(top - 6), X(458 + w), Y(top + 4)], fill=(96, 60, 36))
        else:
            x0, x1, top = DESK
            pts = [(X(x0 + 16), Y(FLOOR_Y))]
            for k in range(9):
                xx = x0 + 16 + k * (x1 - x0 - 32) / 8
                pts.append((X(xx), Y(STUB - (14 if k % 2 else 0))))
            pts.append((X(x1 - 16), Y(FLOOR_Y)))
            dr.polygon(pts, fill=dim(WOOD, 0.7))
        # la chaise
        if s["chair"] == "ok":
            rr(dr, [X(116), Y(1040), X(134), Y(SEAT_Y)], fill=WOOD)
            rr(dr, [X(116), Y(SEAT_Y), X(304), Y(SEAT_Y + 20)], fill=WOOD)
            for lx in (126, 294):
                rr(dr, [X(lx - 6), Y(SEAT_Y + 20), X(lx + 6), Y(FLOOR_Y)], fill=dim(WOOD, 0.7))
        for o in s["objs"]:
            self.obj(dr, X, Y, Q, o)
        for p in s["papers"]:
            pts = body_poly({"x": p["x"], "y": p["y"], "a": p["a"]}, rect(56, 6))
            dr.polygon([(X(x), Y(y)) for (x, y) in pts], fill=(238, 238, 230))
        base.ball(dr, X(s["bx"]), Y(s["by"]), Q(self.R))
        self.bubble(dr, X, Y, Q, P, s, t)
        rr(dr, [0, 0, P(W), P(SCENE_TOP) - 1], fill=tuple(self.cfg["bg_color"]))

    def obj(self, dr, X, Y, Q, o):
        poly = [(X(x), Y(y)) for (x, y) in body_poly(o, rect(o["wd"], o["ht"]))]
        k = o["kind"]
        if k == "mug":
            dr.polygon(poly, fill=o["col"])
            ca, sa = math.cos(o["a"]), math.sin(o["a"])
            hx, hy = o["x"] + 28 * ca, o["y"] + 28 * sa
            circle(dr, X(hx), Y(hy), Q(12), o["col"])
            circle(dr, X(hx), Y(hy), Q(6), WALL)
            return
        if k == "plate":
            dr.polygon(poly, fill=o["col"])
            if abs(math.sin(o["a"])) < 0.3:
                dr.text((X(o["x"]), Y(o["y"])), "HR", fill=(40, 30, 10), anchor="mm", font=base.font(Q(26)))
            return
        if k == "laptop":
            base_ = body_poly(o, [(-60, 34), (60, 34), (60, 52), (-60, 52)])
            scr = body_poly(o, [(-54, -52), (54, -52), (54, 34), (-54, 34)])
            dr.polygon([(X(x), Y(y)) for (x, y) in scr], fill=(120, 122, 136))
            dr.polygon([(X(x), Y(y)) for (x, y) in base_], fill=o["col"])
            c = body_poly(o, [(0, -10)])[0]
            circle(dr, X(c[0]), Y(c[1]), Q(9), (170, 172, 186))
            return
        if k == "lamp":
            # rangée couchée : son pied est le long côté
            dr.polygon(poly, fill=(80, 80, 90))
            c = body_poly(o, [(-60, 0)])[0]
            circle(dr, X(c[0]), Y(c[1]), Q(26), o["col"])
            return
        if k == "frame":
            dr.polygon(poly, fill=o["col"])
            inner = body_poly(o, rect(o["wd"] - 16, o["ht"] - 16))
            dr.polygon([(X(x), Y(y)) for (x, y) in inner], fill=(60, 64, 84))
            c = body_poly(o, [(0, -8)])[0]
            circle(dr, X(c[0]), Y(c[1]), Q(12), (90, 94, 116))
            return
        if k == "slab":
            dr.polygon(poly, fill=WOOD)
            return
        dr.polygon(poly, fill=o["col"])

    def bubble(self, dr, X, Y, Q, P, s, t):
        """Ce qu'il a dit (« BOUNCE. », en gros), puis ce qu'il voulait dire."""
        if s["ans"] is None:
            return
        age = s["t"] - s["ans"]
        k = min(1.0, age / 0.15)
        x0, y0, x1, y1 = 50.0, 452.0, 740.0, 800.0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sc = 0.6 + 0.4 * k
        bx0, bx1 = cx - (cx - x0) * sc, cx + (x1 - cx) * sc
        by0, by1 = cy - (cy - y0) * sc, cy + (y1 - cy) * sc
        tx, ty = X(s["bx"]), Y(s["by"]) - Q(self.R) - P(6)
        dr.polygon([(P(150), P(by1 - 4)), (P(250), P(by1 - 4)), (tx, max(ty, P(by1 + 30)))], fill=(250, 250, 252))
        dr.rounded_rectangle([P(bx0), P(by0), P(bx1), P(by1)], radius=int(P(30)), fill=(250, 250, 252), outline=(20, 20, 26), width=max(1, int(P(5))))
        if k < 1.0:
            return
        f1 = base.font(P(84))
        dr.text((P(cx), P(y0 + 70)), "“BOUNCE.”", fill=PINK, anchor="mm", font=f1, stroke_width=max(1, int(P(3))), stroke_fill=(120, 0, 80))
        if age < 0.45:
            return
        dr.text((P(cx), P(y0 + 142)), "means:", fill=(110, 110, 130), anchor="mm", font=base.font(P(40)))
        words = self.tr.split()
        size = 64
        f2 = base.font(P(size))
        rows, cur = [], ""
        for w in words:
            cand = (cur + " " + w).strip()
            if base.text_w(f2, cand) <= P(x1 - x0 - 70) or not cur:
                cur = cand
            else:
                rows.append(cur); cur = w
        rows.append(cur)
        for i, row in enumerate(rows):
            yy = y0 + 222 + (i - (len(rows) - 1) / 2) * 72
            dr.text((P(cx), P(yy)), row, fill=(20, 20, 26), anchor="mm", font=f2)


# ---------------------------------------------------------------- les questions
QUESTIONS = [
    ("What's your name?", "Bounce.", "Great start.", 1),
    ("Why do you want to work here?", "Your floor looked bouncy.", "It's carpet.", 2),
    ("What's your biggest weakness?", "I can't sit still.", "I noticed.", 1),
    ("Where do you see yourself in five years?", "Higher.", "Noted.", 2),
    ("How do you handle pressure?", "Like this.", "That was a chair.", 3),
    ("What's a challenge you've overcome?", "Gravity.", "Clearly not.", 1),
    ("Are you a team player?", "I am the team.", "Okay.", 3),
    ("What are your salary expectations?", "A trampoline.", "We can do that.", 1),
    ("Can you start Monday?", "I already started.", "You're hired.", 2),
]


def make(n, q, tr, react, nhops):
    class Q_(Question):
        pass
    Q_.n, Q_.N, Q_.level = n, len(QUESTIONS), n
    Q_.q, Q_.tr, Q_.react, Q_.nhops = q, tr, react, nhops
    Q_.__name__ = f"Q{n}"
    if n == len(QUESTIONS):
        Q_.mood = "win"
        Q_.hold_s = 1.0
    return Q_


CHAPTERS = [(make(i + 1, *qq), {}) for i, qq in enumerate(QUESTIONS)]

DEFAULTS = {
    "ball_r": R_BOUNCE, "gravity": G,
    "chapter_max_s": 12.0,
    "counter_font_size": 72, "counter_y": 0.19, "hook_text_s": 2.4,
    "sub_y": 0.80, "watermark_y": 0.93, "end_hold_s": 1.9, "narr_tail_s": 0.3, "narr_gap_s": 0.3,
}


class Sim(StorySim):
    def __init__(self, cfg, rng):
        OFFICE.clear()
        cfg["_chapters"] = CHAPTERS
        super().__init__(cfg, rng)

    def _open(self, i):
        s = self.sims[i]
        delay = s.reply_delay()
        s.replies = [("title", delay)]
        start = max(self.t, self.narr_free + self.cfg["narr_gap_s"])
        q_end = start + self.narr_dur(s.q)
        super()._open(i)
        end = self._line_end.get(f"{i}:title", q_end)
        s.q_end_local = end - self.t0
        # (+1 image : le contrôle date les événements au début du pas)
        s.reply_local = end + delay - self.t0 + 1.0 / self.cfg["fps"]


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
