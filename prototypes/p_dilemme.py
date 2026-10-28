"""Dilemme : il peut effacer un seul souvenir. La video finit sur une question au public."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from lib import *

def build():
    st = Story([
        ("A stranger handed him a remote with one button.", 0.3),
        ("Press it. One memory. Gone forever. Your choice.", 0.5),
        ("He thought about the worst day of his life.", 0.4),
        ("Then about the thing he said, that he can't take back.", 0.5),
        ("Then about her.", 0.7),
        ("Erase her, and the pain goes away.", 0.4),
        ("But so does everything before the pain.", 0.6),
        ("He thought about the dog.", 0.3),
        ("No. Never.", 0.5),
        ("He held the remote for one hour.", 0.5),
        ("Then he pressed it.", 1.2),
        ("He doesn't remember what he chose.", 0.8),
        ("What would you erase?", 0.0),
    ], speed=1.04, end_hold=3.5)
    S, E, m = st.S, st.E, st.mouth
    st.hook, st.hook_until = "You can erase one memory. Only one.", 2.6

    def remote(x, y, s=1.0, press=0.0):
        return g(rect(-70, -160, 140, 320, "#343a40", 24, f'stroke="{K}" stroke-width="7"') + circ(0, -60, 44 - 6 * press, "#e03131", f'stroke="{K}" stroke-width="6"'), x, y, s)
    def street(tl, d, t):
        o = grad("#ced4da", "#868e96") + floor(1450, "#495057", .6)
        o += "".join(rect(k * 300 - 150, 600, 240, 850, cl("#adb5bd", "#000", .1 * (k % 3))) for k in range(5))
        u = eout(tl / 0.8)
        o += g(person(0, 0, 1.7, "#1f1f28", "up") + rect(-90, -330, 180, 60, "#1f1f28", 10), lerp(1100, 800, u), 1450)
        o += remote(lerp(1000, 660, u), lerp(1150, 1080, u), 0.8)
        o += char(t, 360, 1150, 1.5, "talk", "gest", "hip", mouth=0, cable=False, tilt=-5)
        o += moth_near(t, 480, 850, 1.8)
        return o, cam(1.0 + 0.05 * tl, 600, 1050)
    def rule(tl, d, t):
        o = grad("#212529", "#000")
        o += remote(540, 760, 2.4, 0.0)
        o += bigtext("ONE MEMORY.", 540, 1250, 130, "#fff", eout((tl - 0.3) / 0.2)) if tl > 0.3 else ""
        o += bigtext("GONE FOREVER.", 540, 1420, 120, "#ff6b6b", eout((tl - 1.0) / 0.2)) if tl > 1.0 else ""
        return o, cam(1.0 + 0.05 * tl)
    def memory(tl, d, t, kind):
        if kind == "worst":
            o = grad("#495057", "#212529") + floor(1450, "#000", .4)
            for k in range(60):
                x, y = (k * 97) % 1080, (k * 173 + t * 1500) % 2000 - 100
                o += ln(f"M{x},{y} L{x - 10},{y + 60}", 4, "#adb5bd", 'opacity=".6"')
            o += char(t, 540, 1150, 1.6, "sad", "hang", "hang", mouth=0, cable=False, tilt=14, lit=0.5)
            o += g(f'<path d="M-30,0 L-230,-60 L-180,-180 L-100,-150 L-40,-200 L30,-120 L100,-170 L200,-80 L160,10 L40,40 Z" fill="#343a40"/>', 540, 560)
            o += moth(700, 900 + 6 * math.sin(t * 2), 0, 1.8, 0.2)
        elif kind == "said":
            o = grad("#ffe3e3", "#ffa8a8") + floor(1450)
            o += char(t, 360, 1150, 1.5, "angry", "point", "hip", mouth=0.6, cable=False)
            o += g(person(0, 0, 1.6, "#1f1f28"), 820, 1450)
            o += speech(560, 700, "..........", 70, 520)
            u = eout((tl - 0.9) / 0.3)
            if u > 0: o += ln(f"M{540 - 300 * u:.0f},{700 - 120 * u:.0f} L{540 + 300 * u:.0f},{700 + 120 * u:.0f}", 24, "#e03131")
            if tl > 0.7: o = o.replace('translate(820.0,1450.0) rotate(0.00) scale(1.000)', f'translate({820 + 200 * eout((tl - 0.7) / 0.8):.1f},1450.0) rotate(0.00) scale(-1.000,1)')
        else:
            o = grad("#fff0f6", "#faa2c1") + floor(1450, "#d6336c", .3)
            o += sun(820, 420, 110)
            o += g(f'<path d="M-70,0 L-100,280 L100,280 L70,0 Z" fill="#f3d9fa" stroke="{K}" stroke-width="7"/>' + circ(0, -40, 40, K) + circ(-60, -40, 20, "#ffd43b"), 720, 1000)
            o += char(t, 400, 1150, 1.5, "happy", "rest", "hold", mouth=0, cable=False, tilt=-6)
            o += heart(560, 700 + 10 * math.sin(t * 3), 1.8)
            o += moth_near(t, 540, 850, 1.8)
        return o, cam(1.0 + 0.06 * tl, 540, 1000)
    def erase_her(tl, d, t):
        o, c = memory(tl, d, t, "her")
        u = ease((tl - 0.4) / 1.0)
        o += rect(0, 0, W, H, "#fff", extra=f'opacity="{0.85 * u:.2f}"')
        if u > 0.6: o += bigtext("gone.", 540, 960, 150, "#adb5bd", eout((u - 0.6) / 0.4))
        return o, c
    def before(tl, d, t):
        o = grad("#f8f9fa", "#e9ecef")
        cells = [("#ffd166", "beach"), ("#a5d8ff", "snow"), ("#b2f2bb", "picnic"), ("#ffc9c9", "movie"), ("#e5dbff", "road"), ("#ffe8cc", "cake")]
        for k, (col, nm) in enumerate(cells):
            x, y = 150 + (k % 2) * 480, 380 + (k // 2) * 440
            u = ease((tl - 0.2 - k * 0.18) / 0.5)
            o += g(rect(-200, -180, 400, 360, col, 24, f'stroke="{K}" stroke-width="7"') + circ(0, -20, 50, K) + circ(90, -40, 36, K) + heart(45, -120, 0.8) + f'<text x="0" y="140" text-anchor="middle" font-family="Inter" font-weight="900" font-size="40" fill="{K}">{nm}</text>', x + 200, y, 1.0, 0, 1 - u) + rect(x, y - 180, 400, 360, "#f1f3f5", 24, f'opacity="{u:.2f}" stroke="#ced4da" stroke-width="4"')
        return o, cam(1.0 + 0.05 * tl, 540, 900)
    def dog(tl, d, t):
        o = grad("#ffe8cc", "#ffd8a8") + floor(1450, "#e8590c", .3)
        wag = 25 * math.sin(t * 14)
        dg = f'<ellipse cx="0" cy="0" rx="130" ry="80" fill="#8d6e63" stroke="{K}" stroke-width="7"/>' + circ(-140, -60, 70, "#8d6e63", f'stroke="{K}" stroke-width="7"') + f'<ellipse cx="-170" cy="-110" rx="26" ry="50" fill="#5d4037" stroke="{K}" stroke-width="6"/>' + circ(-170, -70, 10, K) + circ(-200, -40, 16, K) + ln(f"M120,-30 Q{200 + wag:.0f},-90 {220 + wag:.0f},-140", 18, "#8d6e63") + ln("M-80,70 L-80,150 M-20,70 L-20,150 M60,70 L60,150 M110,70 L110,150", 24, "#8d6e63")
        o += g(dg + ln("M-150,-20 Q-130,0 -110,-20", 6, "#e03131"), 760, 1250, 1.2)
        o += char(t, 260, 1150, 1.5, "happy", "point", "hip", mouth=0, cable=False, tilt=6)
        o += moth_near(t, 420, 850, 1.8)
        if d > 1.0 and tl > 0.2: o += bigtext("NEVER.", 540, 500, 190, "#fff", eout((tl - 0.2) / 0.2), -4)
        return o, cam(1.0 + 0.05 * tl, 540, 1050)
    def hour(tl, d, t):
        o = grad("#2b2d42", "#1a1b2e") + floor(1450, "#000", .3)
        o += clock(840, 420, 3, int(tl * 60 / d * 1.0), 1.1)
        o += char(t, 480, 1150, 1.6, "sad", "hold", "hold", mouth=0, cable=False, tilt=10, lit=0.6)
        o += remote(500, 1240, 0.7)
        o += moth(300, 900 + 6 * math.sin(t * 2), 0, 1.8, 0.2)
        return o, cam(1.0 + 0.1 * ease(tl / d), 540, 1000)
    def press(tl, d, t):
        o = grad("#2b2d42", "#1a1b2e") + floor(1450, "#000", .3)
        u = ease((tl - 0.5) / 0.25)
        o += char(t, 480, 1150, 1.6, "fear", "hold", "hold", mouth=0, cable=False, tilt=4, lit=0.7, eyes="closed" if tl > 0.4 else None)
        o += remote(500, 1240, 0.7, u)
        if tl > 0.75: o += rect(0, 0, W, H, "#fff", extra=f'opacity="{clamp((tl - 0.75) / 0.15):.2f}"')
        return o, cam(1.0 + 0.3 * ease(tl / 0.8), 500, 1150, sh=3 * (tl > 0.7))
    def blank(tl, d, t):
        o = grad("#fff", "#f1f3f5")
        o += char(t, 540, 1100, 1.8, "talk", "shrug", "shrug", mouth=0, cable=False, lit=1.0)
        o += moth_near(t, 740, 780, 2.2)
        if tl > 0.3: o += bigtext("?", 540, 520, 300, "#adb5bd", eout((tl - 0.3) / 0.25))
        return o, cam(1.0 + 0.04 * tl, 540, 1000)
    def ask(tl, d, t):
        o = grad("#1a1b2e", "#000")
        o += char(t, 540, 1250, 1.6, "idea", "point", "hip", mouth=0, cable=False, rays=1.0)
        o += moth_near(t, 740, 950, 2.0)
        o += bigtext("What would", 540, 420, 130, "#fff", eout(tl / 0.25), -3) + bigtext("YOU erase?", 540, 580, 150, "#ffd43b", eout((tl - 0.2) / 0.25), 2)
        if tl > 1.0: o += label("comment it.", 540, 1700, 54, "#fff", K, 0.9) if (t * 2) % 1 < 0.75 else ""
        return o, cam(1.0 + 0.05 * ease(tl / 2))

    shots = [
        (0, S[1] - 0.05, street, "cut"),
        (S[1] - 0.05, S[2] - 0.05, rule, "zoom"),
        (S[2] - 0.05, S[3] - 0.05, lambda tl, d, t: memory(tl, d, t, "worst"), "whip"),
        (S[3] - 0.05, S[4] - 0.05, lambda tl, d, t: memory(tl, d, t, "said"), "whip"),
        (S[4] - 0.05, S[5] - 0.05, lambda tl, d, t: memory(tl, d, t, "her"), "whip"),
        (S[5] - 0.05, S[6] - 0.05, erase_her, "cut"),
        (S[6] - 0.05, S[7] - 0.05, before, "flash"),
        (S[7] - 0.05, S[8] - 0.05, lambda tl, d, t: dog(tl, 0.5, t), "whip"),
        (S[8] - 0.05, S[9] - 0.05, lambda tl, d, t: dog(tl, 2.0, t), "cut"),
        (S[9] - 0.05, S[10] - 0.05, hour, "whip"),
        (S[10] - 0.05, S[11] - 0.05, press, "cut"),
        (S[11] - 0.05, S[12] - 0.05, blank, "flash"),
        (S[12] - 0.05, st.TOTAL + 1, ask, "whip"),
    ]
    sfx = [(S[0] + 0.8, s_pop(400, 700, 0.1), 0.6), (S[1] + 0.3, s_thud(), 0.8), (S[1] + 1.0, s_thud(90, 30), 0.9), (S[2], s_drone(2.0, 40), 1.0),
           (S[3] + 0.9, s_zap(), 0.7), (S[4], s_sparkle(), 0.7), (S[5] + 0.4, s_riser(1.0), 0.7), (S[6] + 0.2, s_ticktock(6, 0.18), 0.5),
           (S[7] + 0.3, s_pop(500, 900, 0.1), 0.7), (S[8], s_thud(), 0.8), (S[9], s_ticktock(10, 0.33), 0.8), (S[10] + 0.5, s_click(), 1.0), (S[10] + 0.75, s_thud(150, 30, 0.8), 1.2), (S[10] + 0.75, s_ding(), 0.5),
           (S[11] + 0.3, s_pop(300, 500, 0.15), 0.6), (S[12], s_ding(), 0.8), (S[12] + 1.0, s_pop(800, 1200, 0.1), 0.6)]
    return st, shots, sfx, "tense", lambda t: 0.8 if t < S[11] else 0.3

if __name__ == "__main__": main(build)
