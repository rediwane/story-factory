"""
Histoire : le phare. Le gardien prend sa nuit, il laisse Bounce devant la lampe avec
une seule consigne : rester assis. En haut de l'image, la chambre de la lampe : une
lampe pendue au plafond, Bounce sur le plancher. En bas, la mer : le phare, son
faisceau, des rochers à gauche, le port à droite, et un bateau qui suit la lumière.

Chaque retombée de Bounce secoue la lampe : elle se balance, le faisceau balaie la
mer, le bateau le suit ; le crochet s'use à chaque coup. C'est lui qui envoie le bateau
vers les rochers : il suffirait qu'il reste assis.

Fins : WRECK si le bateau touche les rochers pendant que la lampe se balance encore ;
SAVED si la lampe tombe avant : la lentille casse, la lumière inonde la mer, le
capitaine voit les rochers et rentre au port ; HARBOR si le bateau atteint le port
pendant que la lampe se balance encore. Le narrateur raconte ce qui arrive, calé sur
les événements de la simulation ; Bounce ne dit que son nom.

    python3 src/stories/lighthouse.py configs/<name>.json [--simulate]
"""
import math, sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import base
from base import dim, circle

DEFAULTS = {
    "ball_r": 58.0,
    "gravity": 3000.0,
    # la chambre de la lampe (haut)
    "room_top": 440.0, "room_floor": 1040.0, "wall_l": 40.0, "wall_r": 1040.0,
    "hook_x": 560.0, "hook_y": 470.0, "chain_len": 250.0, "lamp_r": 58.0,
    "start_x": 300.0, "hop_start_s": 12.5,
    "start_h": 170.0, "gain": [0.88, 1.18], "min_h": 100.0, "max_h": 380.0, "x_wobble": 90.0,
    "kick": 0.26, "kick_rand": [0.5, 1.5], "damping": 0.35,
    "wear": 0.028, "wear_rand": [0.5, 1.5], "h_ref": 200.0,
    # la mer (bas)
    "sea_top": 1130.0, "horizon": 1250.0, "water_y": 1640.0,
    "tower_x0": 905.0, "tower_x1": 985.0, "tower_top": 1180.0,
    "rocks_x1": 360.0, "dock_x0": 800.0,
    "aim_center": 540.0, "aim_gain": 800.0,
    "ship_x0": 540.0, "ship_k": 1.8, "ship_damp": 0.7, "ship_vmax": 150.0, "ship_half": 48.0,
    "saved_speed": 150.0,
    "post_s": 2.6,
    # couleurs
    "wall": [44, 30, 34], "wall_dark": [30, 20, 24], "floor": [66, 46, 40], "beam_in": [120, 96, 60],
    "brass": [200, 160, 80], "lens": [255, 226, 150], "chain": [150, 140, 120], "crack": [16, 10, 14],
    "sky": [8, 10, 24], "sea": [12, 24, 52], "sea_lit": [40, 62, 100], "beam": [70, 66, 46], "flood": [60, 58, 44],
    "tower": [214, 216, 226], "tower_band": [170, 40, 60], "rock": [34, 36, 48], "rock_lit": [120, 118, 108],
    "foam": [170, 180, 200], "hull": [78, 56, 44], "sail": [220, 214, 200], "dock": [60, 48, 40], "dock_lamp": [255, 200, 120],
    "moon": [226, 228, 236], "divider": [20, 16, 22],
    "counter_y": 0.2,
}


class Sim:
    def __init__(self, cfg, rng):
        c = self.cfg = cfg
        self.rng = rng
        self.W, self.H = cfg["width"], cfg["height"]
        self.R = c["ball_r"]
        self.g = c["gravity"]
        self.scene_top = 0.22
        self.t = 0.0
        self.bx = c["start_x"] + rng.uniform(-20, 20)
        self.h = c["start_h"]
        self.by = c["room_floor"] - self.R
        self.vx = self.vy = 0.0
        self.on = "sit"
        self.theta = 0.0
        self.omega = 0.0
        self.wear = 0.0
        self.fallen = None            # (x, y, vy) de la lampe en chute, puis posée
        self.flood = False
        self.ship_x = c["ship_x0"]
        self.ship_vx = 0.0
        self.ship_state = "sail"      # sail | wreck | docked
        self.dust = []
        self.hits = 0
        self.last_hit = -9.0
        self.hit_t = -9.0
        self.outcome = None
        self.end_t = None
        self.done = False
        self.payoff = False
        self.lines = [(0.0, "The keeper needed one night off. He left Bounce in charge of the lamp.", "job"),
                      (2.5, "One rule. Sit by the lamp. Do not bounce.", "rule")]
        self.replies = [("rule", 0.35)]
        self.flags = set()

    # ---- événements
    def hit(self, evs, kind):
        if self.t - self.last_hit < 0.15:
            return
        self.last_hit = self.t
        self.hits += 1
        evs.append(("hit", kind))

    def line(self, key, text, when=None):
        if key in self.flags:
            return
        self.flags.add(key)
        self.lines.append((self.t if when is None else when, text, key))

    def finish(self, evs, outcome):
        self.outcome = outcome
        self.end_t = self.t
        self.payoff = True
        evs.append(("event", "%s t %.2f hits %d ship %.0f" % (outcome, self.t, self.hits, self.ship_x)))
        evs.append(("payoff", outcome))
        if outcome == "WRECK":
            self.line("end", "Bounce had one job.")
        elif outcome == "SAVED":
            self.line("end", "The light spilled over the whole sea. The captain saw the rocks just in time.")
            self.line("asked", "At dawn the keeper asked what happened.", self.t + 4.0)
            self.replies.append(("asked", 0.35))
        else:
            self.line("end", "The ship made it to the harbor. Nobody knows how.")

    def hero_mood(self):
        if self.outcome == "WRECK":
            return "lose"
        if self.outcome in ("SAVED", "HARBOR"):
            return "win"
        return None

    # ---- la lampe
    def lamp_pos(self):
        c = self.cfg
        if self.fallen is not None:
            return self.fallen[0], self.fallen[1]
        return c["hook_x"] + math.sin(self.theta) * c["chain_len"], c["hook_y"] + math.cos(self.theta) * c["chain_len"]

    def aim_x(self):
        c = self.cfg
        if self.flood:
            return None
        return max(60.0, min(1020.0, c["aim_center"] + self.theta * c["aim_gain"]))

    # ---- les sauts
    def jump(self, tx):
        s = math.sqrt(2 * self.g * self.h)
        T = 2 * s / self.g
        self.vx = (tx - self.bx) / T
        self.vy = -s
        self.on = "air"

    def land(self, evs):
        c, rng = self.cfg, self.rng
        self.hit(evs, "floor")
        self.hit_t = self.t
        k = self.h / c["h_ref"]
        kick = c["kick"] * k * rng.uniform(*c["kick_rand"])
        sign = 1.0 if self.omega >= 0 else -1.0
        if abs(self.omega) < 0.05:
            sign = rng.choice([-1.0, 1.0])
        if self.fallen is None:
            self.omega += sign * kick
            self.wear = min(1.0, self.wear + c["wear"] * (0.5 + 0.5 * k) * rng.uniform(*c["wear_rand"]))
            for i in range(2 + int(5 * self.wear)):
                self.dust.append((self.t + rng.uniform(0, 0.2), c["hook_x"] + rng.uniform(-30, 30) * (0.5 + self.wear), c["hook_y"] + 8))
            if self.wear >= 0.7 and "hook" not in self.flags:
                self.line("hook", "The hook was not built for this.")
            if self.wear >= 1.0:
                lx, ly = self.lamp_pos()
                self.fallen = [lx, ly, 0.0]
                evs.append(("event", "lamp falls t %.2f theta %.2f" % (self.t, self.theta)))
                self.line("fall", "Then the lamp fell.")
        self.h = min(c["max_h"], max(c["min_h"], self.h * rng.uniform(*c["gain"])))
        tx = min(c["wall_r"] - 260, max(c["wall_l"] + 90, self.bx + rng.uniform(-1, 1) * c["x_wobble"]))
        self.jump(tx)

    def step(self, dt):
        c = self.cfg
        evs = []
        self.t += dt
        # la lampe : pendule, puis chute
        if self.fallen is None:
            g_eff = self.g / c["chain_len"] * 0.3
            self.omega += -g_eff * math.sin(self.theta) * dt - c["damping"] * self.omega * dt
            self.theta += self.omega * dt
            if abs(self.theta) > 1.1:
                self.theta = math.copysign(1.1, self.theta)
                self.omega = -self.omega * 0.4
            if abs(self.theta) > 0.12 and "shake" not in self.flags:
                self.line("shake", "Every hop shook the lamp. Every shake turned the light.")
        else:
            f = self.fallen
            if not self.flood:
                f[2] += self.g * dt
                f[1] += f[2] * dt
                if f[1] + c["lamp_r"] >= c["room_floor"]:
                    f[1] = c["room_floor"] - c["lamp_r"]
                    f[2] = 0.0
                    self.flood = True
                    self.hit(evs, "lamp")
                    evs.append(("event", "lens breaks t %.2f" % self.t))
                    for i in range(14):
                        self.dust.append((self.t + self.rng.uniform(0, 0.3), f[0] + self.rng.uniform(-160, 160), c["room_floor"] - 16))
        # le bateau
        if self.ship_state == "sail":
            if self.flood:
                target = c["dock_x0"] + 60
                self.ship_vx += (target - self.ship_x) * 1.6 * dt - self.ship_vx * 1.0 * dt
                vmax = c["saved_speed"]
            else:
                target = self.aim_x()
                self.ship_vx += (target - self.ship_x) * c["ship_k"] * dt - self.ship_vx * c["ship_damp"] * dt
                vmax = c["ship_vmax"]
            self.ship_vx = max(-vmax, min(vmax, self.ship_vx))
            self.ship_x += self.ship_vx * dt
            if abs(self.ship_x - c["ship_x0"]) > 70 and "ship" not in self.flags:
                self.line("ship", "Out at sea, a ship was following that light.")
            if self.ship_x < 470 and "rocks" not in self.flags and not self.flood:
                self.line("rocks", "Straight toward the rocks.")
            if "rocks" in self.flags and not self.flood:
                if self.ship_vx > 25 and self.ship_x < 560 and "turn1" not in self.flags:
                    self.line("turn1", "Then the light moved. So did the ship.")
                if "turn1" in self.flags and self.ship_vx < -25 and self.ship_x < 520 and "turn2" not in self.flags:
                    self.line("turn2", "Back toward the rocks.")
            if self.t > c["hop_start_s"] + 9.0 and "busy" not in self.flags and self.outcome is None:
                self.line("busy", "Bounce did not notice. Bounce was busy.")
            if self.ship_x - c["ship_half"] <= c["rocks_x1"] and self.outcome is None:
                self.ship_state = "wreck"
                self.ship_x = c["rocks_x1"] + c["ship_half"]
                self.hit(evs, "wreck")
                self.finish(evs, "WRECK")
            elif self.ship_x + c["ship_half"] >= c["dock_x0"] and self.outcome is None:
                self.ship_state = "docked"
                self.finish(evs, "SAVED" if self.flood else "HARBOR")
        # Bounce
        if self.on == "sit":
            if self.t >= c["hop_start_s"]:
                self.jump(self.bx + self.rng.uniform(-30, 30))
        elif self.on == "air":
            self.vy += self.g * dt
            self.bx += self.vx * dt
            self.by += self.vy * dt
            ly = c["room_floor"] - self.R
            if self.vy > 0 and self.by >= ly:
                self.by = ly
                self.land(evs)
        if self.outcome is not None and not self.done and self.t - self.end_t >= c["post_s"]:
            self.done = True
        return evs

    def snapshot(self):
        return {"t": self.t, "bx": self.bx, "by": self.by, "on": self.on, "theta": self.theta,
                "wear": self.wear, "fallen": list(self.fallen) if self.fallen else None, "flood": self.flood,
                "ship_x": self.ship_x, "ship_vx": self.ship_vx, "ship_state": self.ship_state,
                "outcome": self.outcome, "end_t": self.end_t, "hit_t": self.hit_t,
                "aim": self.aim_x(), "dust": [d for d in self.dust if 0 <= self.t - d[0] < 1.2]}

    def counter(self, s):
        return None

    # ---- dessin
    def draw(self, dr, s, t, S):
        c = self.cfg
        W, H, R = self.W, self.H, self.R
        P = lambda v: v * S
        st = s["t"]
        RT, RF, WL, WR = c["room_top"], c["room_floor"], c["wall_l"], c["wall_r"]
        HX, HY, L, LR = c["hook_x"], c["hook_y"], c["chain_len"], c["lamp_r"]

        # ---------------- la chambre de la lampe
        wall, wdark, floor = tuple(c["wall"]), tuple(c["wall_dark"]), tuple(c["floor"])
        dr.rectangle([0, P(RT - 20), P(W), P(RF)], fill=wall)
        for k in range(0, W, 90):
            dr.line([(P(k), P(RT)), (P(k), P(RF))], fill=wdark, width=int(P(3)))
        dr.rectangle([0, P(RF), P(W), P(RF + 60)], fill=floor)
        dr.rectangle([0, P(RF), P(W), P(RF + 8)], fill=dim(floor, 1.3))
        # la fenêtre
        dr.rectangle([P(820), P(560), P(980), P(780)], fill=tuple(c["sky"]))
        dr.rectangle([P(812), P(552), P(988), P(566)], fill=wdark)
        dr.rectangle([P(896), P(560), P(904), P(780)], fill=wdark)
        circle(dr, P(862), P(600), P(3), (220, 220, 230))
        circle(dr, P(940), P(640), P(2.5), (220, 220, 230))
        # la lumière de la lampe sur le mur
        if s["fallen"] is None:
            lx = HX + math.sin(s["theta"]) * L
            ly = HY + math.cos(s["theta"]) * L
        else:
            lx, ly = s["fallen"][0], s["fallen"][1]
        bi = tuple(c["beam_in"])
        if not s["flood"]:
            dr.polygon([(P(lx), P(ly)), (P(lx - 420 + s["theta"] * 300), P(RF)), (P(lx + 420 + s["theta"] * 300), P(RF))], fill=dim(bi, 0.45))
        else:
            dr.rectangle([0, P(RT - 20), P(W), P(RF)], fill=dim(bi, 0.75))
            for k in range(0, W, 90):
                dr.line([(P(k), P(RT)), (P(k), P(RF))], fill=dim(bi, 0.55), width=int(P(3)))
        # la fissure et la poussière au crochet
        crack = tuple(c["crack"])
        w = s["wear"]
        n = int(2 + 6 * w)
        for k in range(n):
            ang = -0.3 - k * (2.5 / max(1, n - 1))
            ln = 24 + 110 * w
            dr.line([(P(HX), P(HY - 6)), (P(HX + math.cos(ang) * ln), P(HY - 6 + math.sin(ang) * ln * 0.5))], fill=crack, width=int(P(4)))
        for (dt0, dx, dy) in s["dust"]:
            age = st - dt0
            circle(dr, P(dx + 8 * math.sin(age * 5 + dx)), P(dy + 700 * age * age), P(4), dim((190, 180, 170), 1 - 0.6 * age))
        # la lampe
        chain, brass, lens = tuple(c["chain"]), tuple(c["brass"]), tuple(c["lens"])
        if s["fallen"] is None:
            dr.line([(P(HX), P(HY)), (P(lx), P(ly))], fill=chain, width=int(P(8)))
            circle(dr, P(HX), P(HY), P(12), brass)
        else:
            dr.line([(P(lx), P(ly)), (P(lx + 40), P(ly - 110))], fill=chain, width=int(P(8)))
        for k in range(3, 0, -1):
            circle(dr, P(lx), P(ly), P(LR + 26 * k), dim(lens, 0.12 + 0.05 * (3 - k)))
        circle(dr, P(lx), P(ly), P(LR + 10), brass)
        circle(dr, P(lx), P(ly), P(LR), lens if not s["flood"] else dim(lens, 0.8))
        if s["flood"]:
            for k in range(5):
                a = k * 1.3
                dr.line([(P(lx), P(ly)), (P(lx + math.cos(a) * LR), P(ly + math.sin(a) * LR))], fill=brass, width=int(P(4)))
        dr.rectangle([P(lx - 14), P(ly - LR - 24), P(lx + 14), P(ly - LR - 4)], fill=brass)
        # Bounce
        base.ball(dr, P(s["bx"]), P(s["by"]), P(R))

        # ---------------- le mur entre les deux
        dr.rectangle([0, P(RF + 60), P(W), P(c["sea_top"])], fill=tuple(c["divider"]))

        # ---------------- la mer
        ST, HZ, WY = c["sea_top"], c["horizon"], c["water_y"]
        TX0, TX1, TT = c["tower_x0"], c["tower_x1"], c["tower_top"]
        sky, sea = tuple(c["sky"]), tuple(c["sea"])
        dr.rectangle([0, P(ST), P(W), P(WY)], fill=sky)
        dr.rectangle([0, P(WY), P(W), P(H)], fill=sea)
        circle(dr, P(150), P(ST + 110), P(46), tuple(c["moon"]))
        circle(dr, P(172), P(ST + 98), P(42), sky)
        for i in range(30):
            x = (i * 7919 + 311) % W
            y = ST + 20 + (i * 104729 + 97) % 330
            circle(dr, P(x), P(y), P(2), (170, 175, 200))
        # le faisceau
        lamp_sea = ((TX0 + TX1) / 2, TT + 30)
        beam = tuple(c["beam"])
        if s["flood"]:
            dr.polygon([(P(lamp_sea[0]), P(lamp_sea[1])), (0, P(WY - 160)), (0, P(H)), (P(W), P(H)), (P(W), P(WY - 160))], fill=tuple(c["flood"]))
            dr.rectangle([0, P(WY), P(W), P(H)], fill=tuple(c["sea_lit"]))
        elif s["aim"] is not None:
            ax = s["aim"]
            dr.polygon([(P(lamp_sea[0]), P(lamp_sea[1])), (P(ax - 110), P(WY)), (P(ax + 110), P(WY))], fill=beam)
            dr.polygon([(P(ax - 150), P(WY)), (P(ax + 150), P(WY)), (P(ax + 190), P(H)), (P(ax - 190), P(H))], fill=tuple(c["sea_lit"]))
        # les rochers
        rock = tuple(c["rock"])
        lit = s["flood"] or (s["aim"] is not None and s["aim"] < 420)
        rc = tuple(c["rock_lit"]) if lit else rock
        dr.polygon([(P(60), P(WY + 20)), (P(120), P(WY - 70)), (P(180), P(WY - 30)), (P(240), P(WY - 110)), (P(300), P(WY - 40)), (P(c["rocks_x1"] + 10), P(WY + 20))], fill=rc)
        dr.polygon([(P(0), P(WY + 20)), (P(40), P(WY - 40)), (P(90), P(WY + 20))], fill=dim(rc, 0.8))
        foam = tuple(c["foam"])
        for k in range(4):
            x = 90 + k * 70 + 10 * math.sin(st * 2 + k)
            dr.line([(P(x), P(WY + 6)), (P(x + 40), P(WY + 6))], fill=dim(foam, 0.6 + 0.4 * lit), width=int(P(3)))
        # le port et le phare
        dock = tuple(c["dock"])
        dr.rectangle([P(c["dock_x0"]), P(WY - 24), P(TX0 + 20), P(WY + 10)], fill=dock)
        for x in (c["dock_x0"] + 20, c["dock_x0"] + 80):
            dr.rectangle([P(x), P(WY - 24), P(x + 12), P(WY + 60)], fill=dim(dock, 0.8))
        dl = tuple(c["dock_lamp"])
        circle(dr, P(c["dock_x0"] + 30), P(WY - 70), P(26), dim(dl, 0.25))
        circle(dr, P(c["dock_x0"] + 30), P(WY - 70), P(9), dl)
        dr.line([(P(c["dock_x0"] + 30), P(WY - 62)), (P(c["dock_x0"] + 30), P(WY - 24))], fill=dim(dock, 1.4), width=int(P(5)))
        tower, band = tuple(c["tower"]), tuple(c["tower_band"])
        dr.polygon([(P(TX0 - 60), P(WY + 30)), (P(TX0 - 20), P(WY - 40)), (P(TX1 + 40), P(WY - 30)), (P(W), P(WY + 30))], fill=rock)
        dr.rectangle([P(TX0), P(TT), P(TX1), P(WY - 30)], fill=tower)
        for y in (TT + 90, TT + 230):
            dr.rectangle([P(TX0), P(y), P(TX1), P(y + 55)], fill=band)
        dr.rectangle([P(TX0 - 14), P(TT - 60), P(TX1 + 14), P(TT + 10)], fill=(60, 60, 76))
        dr.polygon([(P(TX0 - 22), P(TT - 60)), (P((TX0 + TX1) / 2), P(TT - 100)), (P(TX1 + 22), P(TT - 60))], fill=(80, 80, 96))
        circle(dr, P(lamp_sea[0]), P(TT - 25), P(22), lens)
        # le bateau
        hull, sail = tuple(c["hull"]), tuple(c["sail"])
        sx = s["ship_x"]
        tilt = 0.0
        sy = WY - 6 + 4 * math.sin(st * 2.2)
        if s["ship_state"] == "wreck":
            age = min(1.0, (st - s["end_t"]) / 2.0) if s["end_t"] else 0.0
            tilt = -0.5 * age
            sy = WY - 6 + 50 * age
        ca, sa = math.cos(tilt), math.sin(tilt)
        hh = c["ship_half"]

        def rp(dx, dy):
            return (P(sx + dx * ca - dy * sa), P(sy + dx * sa + dy * ca))
        dr.polygon([rp(-hh, -8), rp(hh, -8), rp(hh - 16, 24), rp(-hh + 16, 24)], fill=hull)
        dr.polygon([rp(-4, -10), rp(-4, -80), rp(34, -22)], fill=sail)
        dr.line([rp(-4, -10), rp(-4, -86)], fill=dim(hull, 1.3), width=int(P(5)))
        circle(dr, *rp(hh - 10, -16), P(5), dl)
        if s["ship_state"] == "docked":
            circle(dr, *rp(0, -40), P(0.1), hull)


if __name__ == "__main__":
    sys.exit(base.run(sys.modules[__name__]))
