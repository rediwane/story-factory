"""Conte en voix off : il recoit des textos d'un inconnu."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from lib import *

def build():
    st = Story([
        ("He got a text from a number he didn't know.", 0.25),
        ("Don't take the 8:15 bus.", 0.45),
        ("He laughed. And took the bus.", 0.3),
        ("Nothing happened.", 0.4),
        ("The next day: don't eat the sandwich.", 0.3),
        ("He ate it. It was fine.", 0.4),
        ("Day three: say hi to the girl in the red coat.", 0.3),
        ("He almost didn't.", 0.5),
        ("He did.", 0.6),
        ("Ten years later, at their wedding,", 0.2),
        ("his phone buzzed. Same number.", 0.4),
        ("You're welcome.", 0.6),
        ("He typed back: who are you?", 0.5),
        ("The answer came in one second.", 0.7),
        ("Ask your wife.", 0.0),
    ], end_hold=3.2)
    S, E, m = st.S, st.E, st.mouth
    st.hook, st.hook_until = "He ignored the first two texts.", 2.4
    st.sub_mute = [(S[1], E[1] + 0.4), (S[11], E[11] + 0.5), (S[14], st.TOTAL)]

    def screen(txt, u, tl, dark=False):
        o = grad("#2b2d42" if dark else "#dfe7f2", "#14151f" if dark else "#9fb3c8") + phone(540, 960, 2.2)
        o += rect(300, 480, 480, 100, "#e9ecef", 20) + f'<text x="540" y="548" text-anchor="middle" font-family="Inter" font-weight="900" font-size="44" fill="#495057">Unknown number</text>'
        o += rect(255, 760, 570, 300, "#e9ecef", 40)
        o += typed(txt, 290, 850, 52, u, K, "Inter", maxw=520)
        return o
    def bus_stop(tl, d, t):
        o = grad("#a5d8ff", "#e7f5ff") + floor(1450, "#495057", .5) + rect(-800, 1450, 2400, 40, "#868e96")
        o += ln("M820,1450 L820,900", 16) + rect(740, 820, 160, 100, "#1c7ed6", 10, f'stroke="{K}" stroke-width="7"') + f'<text x="820" y="888" text-anchor="middle" font-family="Inter" font-weight="900" font-size="54" fill="#fff">8:15</text>'
        bx = lerp(-900, 180, eout(tl / 1.2))
        o += g(rect(0, 0, 700, 380, "#fab005", 30, f'stroke="{K}" stroke-width="9"') + "".join(rect(40 + k * 130, 50, 100, 120, "#a5d8ff", 10, f'stroke="{K}" stroke-width="6"') for k in range(5)) + circ(130, 390, 60, K) + circ(570, 390, 60, K), bx, 1080)
        walk = t * 9 if tl < 1.2 else None
        hx = lerp(360, 560, ease((tl - 1.0) / 0.8)) if tl > 1.0 else 360 + 0 * tl
        o += char(t, hx, 1150, 1.5, "happy", walk=t * 9 if tl > 1.0 else None, mouth=0, cable=False)
        o += moth_near(t, hx + 130, 900, 1.8)
        return o, cam(1.0 + 0.04 * tl, 540, 1000)
    def in_bus(tl, d, t):
        o = grad("#fab005", "#f08c00") + rect(-800, 1000, 2400, 1000, "#e67700") + "".join(rect(k * 420 - 300 + (tl * 400) % 420, 300, 300, 420, "#a5d8ff", 16, f'stroke="{K}" stroke-width="8"') for k in range(5))
        o += rect(200, 1000, 680, 60, "#495057", 12)
        o += char(t, 540, 1120, 1.7, "talk", "shrug", "shrug", mouth=0, cable=False, tilt=3)
        o += moth_near(t, 760, 760, 2.0)
        return o, cam(1.0 + 0.05 * tl)
    def sandwich(tl, d, t):
        o = grad("#ffe8cc", "#ffd8a8") + floor(1450) + table(540, 1250, 700)
        sw = g(f'<path d="M-160,0 Q0,-90 160,0 Z" fill="#f4a261" stroke="{K}" stroke-width="7"/>' + rect(-170, 0, 340, 26, "#2f9e44", 8) + rect(-150, 26, 300, 20, "#e63946", 6) + rect(-160, 46, 320, 40, "#f4a261", 10, f'stroke="{K}" stroke-width="7"'), 540, 1150, 1.2)
        o += sw
        if tl > 1.1:
            u = eout((tl - 1.1) / 0.5)
            o += char(t, 540, 1060, 1.5, "happy", "hold", "hold", mouth=0.4 * abs(math.sin(t * 9)), cable=False, tilt=-4)
            o += g(sw, 0, 0).replace('translate(540.0,1150.0)', f'translate({540 - 40 * u:.0f},{1150 - 40 * u:.0f})')
        else:
            o += char(t, 300, 1060, 1.5, "talk", "point", "hip", mouth=0, cable=False, tilt=-6)
        o += moth_near(t, 820, 760, 2.0)
        return o, cam(1.0 + 0.06 * tl, 540, 1050)
    def street_red(tl, d, t):
        o = grad("#dee2e6", "#adb5bd") + floor(1450, "#495057", .6) + "".join(rect(k * 260 - 100, 700, 220, 750, cl("#868e96", "#000000", .15 * (k % 3)), 0) for k in range(6))
        o += "".join(rect(k * 260 - 60, 760 + (k % 2) * 90, 60, 90, "#fff3bf", 4) for k in range(6))
        gx = 800
        o += g(f'<path d="M-70,0 L-90,220 L90,220 L70,0 Z" fill="#e03131" stroke="{K}" stroke-width="7"/>' + circ(0, -40, 40, K) + ln("M-30,230 L-34,330 M30,230 L34,330", 22), gx, 1050)
        hes = 0.5 + 0.5 * math.sin(t * 2.5)
        o += char(t, 300 + 30 * hes, 1150, 1.5, "fear" if d > 1.5 else "happy", "chest" if d > 1.5 else "up", "chest" if d > 1.5 else "hip", mouth=0, cable=False, shiver=0.5 if d > 1.5 else 0, face=1)
        o += moth_near(t, 430, 850, 1.8)
        return o, cam(1.0 + 0.05 * tl, 560, 1050)
    def hi(tl, d, t):
        o, c = street_red(tl, 1.0, t)
        o += g(ln("M0,0 L60,-120", 22) + ln("M-30,30 L-40,180", 22), 800 + 90, 1270).replace('opacity="1.00"', 'opacity="1.00"')
        u = eout((tl - 0.3) / 0.4)
        if u > 0: o += heart(560, 800 - 60 * u, 1.6 * back(u), "#ff6b6b")
        return o, cam(1.08 + 0.04 * tl, 560, 1000, sh=0)
    def wedding(tl, d, t):
        o = grad("#fff0f6", "#faa2c1") + floor(1450, "#d6336c", .35)
        for k in range(12): o += circ((k * 97) % 1080, (k * 211 + tl * 250) % 1600, 8 + k % 3, ["#fff", "#ffd43b", "#ff8787"][k % 3])
        o += g(ln("M-120,0 Q0,-200 120,0", 14, "#2f9e44") + "".join(circ(-100 + k * 40, -120 - 60 * math.sin(k * .8), 22, ["#ff6b6b", "#ffd43b", "#fff"][k % 3]) for k in range(6)), 540, 560)
        o += g(f'<path d="M-90,0 L-120,300 L120,300 L90,0 Z" fill="#fff" stroke="{K}" stroke-width="7"/>' + circ(0, -40, 40, K) + circ(0, -110, 50, "#fff", 'opacity=".6"'), 740, 980)
        o += char(t, 360, 1140, 1.5, "happy", "rest", "hold", mouth=0, cable=False, tilt=-5)
        o += moth(560, 1000 + 10 * math.sin(t * 3), 0, 2.2, abs(math.sin(t * 36))) + g(f'<path d="M-14,-7 L0,0 L-14,7 Z M14,-7 L0,0 L14,7 Z" fill="{K}"/>', 560, 1020, 1.6)
        return o, cam(1.0 + 0.04 * tl, 540, 980)
    def buzz(tl, d, t):
        o, c = wedding(tl, d, t)
        sh = 6 * (1 if (t * 18) % 1 < 0.5 else -1) if tl < 1.0 else 0
        o += phone(840 + sh, 1250, 0.9, "")
        o += g(ln("M-40,-80 L-40,-120 M40,-80 L40,-120", 8, K), 840, 1150) if tl < 1.0 else ""
        return o, cam(1.0 + 0.04 * tl, 540, 1000)
    def wife(tl, d, t):
        o = grad("#fff0f6", "#faa2c1") + floor(1450, "#d6336c", .35)
        o += g(f'<path d="M-90,0 L-120,300 L120,300 L90,0 Z" fill="#fff" stroke="{K}" stroke-width="7"/>' + circ(0, -40, 40, K), 700, 980)
        o += phone(300, 1080, 0.6, "") + g(f'<text x="0" y="0" text-anchor="middle" font-family="Inter" font-weight="900" font-size="22" fill="{K}">Ask your wife.</text>', 300, 1080)
        o += char(t, 400, 1140, 1.5, "idea", "up", "hold", mouth=0, cable=False, tilt=-8, rays=clamp(tl / 0.3), halo_boost=0.3 * math.exp(-tl))
        if tl > 0.8:
            o += g(phone(0, 0, 0.5, "") + heart(0, 0, 0.6), 820, 900)
        o += moth_near(t, 600, 780, 2.0)
        if tl > 1.2: o += bigtext("Ask your wife.", 540, 420, 118, "#fff", eout((tl - 1.2) / 0.25), -3)
        return o, cam(1.0 + 0.08 * ease(tl / 2), 540, 980)

    shots = [
        (0, S[1] - 0.05, lambda tl, d, t: (room("#2b2d42", "#1a1b2e") + char(t, 540, 1100, 1.8, "talk", "hold", "hold", mouth=0, cable=False, tilt=14) + phone(560, 1300, 0.5, "") + moth_near(t, 760, 740, 2.2) + (g(ln("M-40,-80 L-40,-120 M40,-80 L40,-120", 8, "#fff"), 560, 1180) if (t * 14) % 1 < .5 else ""), cam(1 + 0.06 * tl, 540, 1000)), "cut"),
        (S[1] - 0.05, S[2] - 0.05, lambda tl, d, t: (screen("Don't take the 8:15 bus.", tl / 1.0, tl), cam(1.0 + 0.03 * tl)), "zoom"),
        (S[2] - 0.05, S[3] - 0.05, bus_stop, "whip"),
        (S[3] - 0.05, S[4] - 0.05, in_bus, "whip"),
        (S[4] - 0.05, S[5] - 0.05, lambda tl, d, t: (screen("Don't eat the sandwich.", tl / 0.9, tl), cam(1.0 + 0.03 * tl)), "zoom"),
        (S[5] - 0.05, S[6] - 0.05, sandwich, "whip"),
        (S[6] - 0.05, S[7] - 0.05, lambda tl, d, t: (screen("Say hi to the girl in the red coat.", tl / 1.4, tl), cam(1.0 + 0.03 * tl)), "zoom"),
        (S[7] - 0.05, S[8] - 0.05, lambda tl, d, t: street_red(tl, 2.0, t), "whip"),
        (S[8] - 0.05, S[9] - 0.05, hi, "cut"),
        (S[9] - 0.05, S[10] - 0.05, wedding, "flash"),
        (S[10] - 0.05, S[11] - 0.05, buzz, "cut"),
        (S[11] - 0.05, S[12] - 0.05, lambda tl, d, t: (screen("You're welcome.", tl / 0.7, tl), cam(1.0 + 0.03 * tl)), "zoom"),
        (S[12] - 0.05, S[13] - 0.05, lambda tl, d, t: (screen("Who are you?", (tl - 0.3) / 0.8, tl), cam(1.0 + 0.03 * tl)), "cut"),
        (S[13] - 0.05, S[14] - 0.1, lambda tl, d, t: (screen("...", (tl * 2) % 1.0, tl, True) + (rect(0, 0, W, H, "#000", extra='opacity=".3"')), cam(1.0 + 0.05 * tl)), "cut"),
        (S[14] - 0.1, st.TOTAL + 1, wife, "flash"),
    ]
    buzz_s = np.concatenate([s_buzz(0.12, 60), np.zeros(int(0.1 * SR))] * 3)
    sfx = [(0.3, buzz_s, 1.0), (S[1], s_ticktock(6, 0.1), 0.4), (S[2] + 0.9, s_whoosh(0.5), 0.8), (S[2] + 0.1, s_laugh(), 0.6),
           (S[4], buzz_s, 0.8), (S[5] + 0.4, s_pop(300, 200, 0.15), 0.8), (S[6], buzz_s, 0.8), (S[7], s_heart(), 0.8), (S[7] + 0.7, s_heart(), 0.8),
           (S[8] + 0.3, s_sparkle(), 1.0), (S[9], s_sparkle(), 0.8), (S[10], buzz_s, 1.0), (S[11], s_ticktock(4, 0.1), 0.4), (S[12] + 0.3, s_ticktock(8, 0.08), 0.5),
           (S[13] + 0.2, s_ticktock(6, 0.45), 0.7), (S[14] - 0.1, s_ding(), 0.9), (S[14] + 0.9, s_pop(600, 900), 0.6)]
    return st, shots, sfx, "gentle", None

if __name__ == "__main__": main(build)
