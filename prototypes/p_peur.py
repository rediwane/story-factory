"""Histoire qui fait peur, voix off : a 3 h 07, son telephone detecte un mouvement. Il vit seul."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from lib import *

def build():
    st = Story([
        ("3:07 AM. His phone lit up.", 0.4),
        ("Motion detected. Living room.", 0.5),
        ("He lived alone.", 0.6),
        ("He opened the camera feed.", 0.4),
        ("Someone was standing in his living room.", 0.4),
        ("Not moving. Just standing.", 0.7),
        ("He called the police.", 0.3),
        ("They searched every room.", 0.3),
        ("Nobody.", 0.8),
        ("The next night. 3:07.", 0.5),
        ("Same alert. Same figure.", 0.5),
        ("This time, he zoomed in.", 0.8),
        ("It was wearing his clothes.", 0.9),
        ("He checked the app.", 0.4),
        ("He had never installed a camera.", 0.0),
    ], speed=1.0, end_hold=3.6)
    S, E, m = st.S, st.E, st.mouth
    st.hook, st.hook_until = "He lives alone. His phone disagreed.", 2.6
    st.sub_mute = [(S[1], E[1] + 0.5)]

    def bedroom(tl, d, t, glow=0.0, sit=False, mood="fear", shiver=0.0):
        o = grad("#0b0c12", "#000") + rect(-800, 1300, 2400, 900, "#07070a")
        o += window(120, 300, 300, 380, "#0e1230", True, 0, t)
        o += rect(150, 1100, 780, 260, "#1a1b26", 30, f'stroke="{K}" stroke-width="8"') + rect(150, 1000, 780, 120, "#23243a", 30, f'stroke="{K}" stroke-width="8"')
        if glow > 0: o += circ(760, 1080, 220 * glow, "#9fc8ff", f'opacity="{.18 * glow:.2f}"')
        if sit: o += char(t, 420, 1000, 1.4, mood, "chest", "chest", mouth=0, cable=False, lit=0.25 + 0.5 * glow, shiver=shiver, eyes="wide")
        else: o += f'<g transform="rotate(-90 520 1140)">' + char(t, 520, 1140, 1.1, "off", "rest", "rest", cable=False, lit=0.15) + '</g>'
        o += phone(760, 1080, 0.55, "") + (rect(702, 962, 116, 236, "#dbe9ff", 10, f'opacity="{glow:.2f}"') if glow > 0 else "")
        o += moth(300, 900 + 6 * math.sin(t * 2), 0, 1.6, 0.2)
        return o
    def feed(tl, d, t, zoom=1.0, figure=True, label_txt="LIVING ROOM  CAM 1", clothes=False, shake=0.0):
        o = grad("#1a1a1a", "#050505")
        cx, cy = 540, 900
        o += f'<g transform="translate({cx},{cy}) scale({zoom:.3f}) translate({-cx},{-cy})">'
        o += rect(40, 420, 1000, 1000, "#2a2a2a") + rect(40, 1100, 1000, 320, "#1e1e1e") + rect(120, 560, 240, 300, "#333", 8) + rect(620, 480, 360, 420, "#303030", 8)
        if figure:
            fx = 540 + shake * 3 * math.sin(t * 50)
            fig = f'<ellipse cx="0" cy="-130" rx="36" ry="62" fill="#0a0a0a"/>' + ln("M-14,-80 L-20,60", 24, "#0a0a0a") + ln("M14,-80 L20,60", 24, "#0a0a0a") + ln("M-30,-160 L-40,-50", 18, "#0a0a0a") + ln("M30,-160 L40,-50", 18, "#0a0a0a")
            fig += f'<path d="M-16,-190 C-20,-210 -54,-230 -54,-280 A54,54 0 1,1 54,-280 C54,-230 20,-210 16,-190 Z" fill="#141414" stroke="#000" stroke-width="4"/>' + rect(-18, -192, 36, 30, "#0a0a0a", 4)
            if clothes:
                fig += rect(-36, -170, 72, 110, "#e03131", 10, 'opacity=".9"') + f'<text x="0" y="-100" text-anchor="middle" font-family="Inter" font-weight="900" font-size="26" fill="#fff">ME</text>'
            o += g(fig, fx, 1100, 1.4)
        o += '</g>'
        for k in range(0, H, 6): o += rect(0, k, W, 2, "#000", extra='opacity=".25"')
        for k in range(60):
            x, y = (k * 193 + int(t * 1000)) % W, (k * 311 + int(t * 7000)) % H
            o += rect(x, y, 3 + k % 4, 3, "#fff", extra='opacity=".12"')
        o += rect(0, 0, W, H, "#9fc8ff", extra='opacity=".06"')
        o += f'<text x="60" y="140" font-family="JetBrains Mono" font-weight="800" font-size="46" fill="#fff" opacity=".85">{esc(label_txt)}</text>'
        o += f'<text x="1020" y="140" text-anchor="end" font-family="JetBrains Mono" font-weight="800" font-size="46" fill="#fff" opacity=".85">03:07:{int(tl * 1.3 + 12):02d}</text>'
        o += circ(80, 220, 14, "#ff2b2b" if (t * 2) % 1 < 0.6 else "#5a1010") + f'<text x="110" y="234" font-family="JetBrains Mono" font-weight="800" font-size="40" fill="#ff5f5f">REC</text>'
        return o
    def police(tl, d, t):
        o = grad("#0b0c12", "#000") + floor(1450, "#000", .4)
        for k, x in enumerate([200, 540, 880]):
            u = clamp((tl - k * 0.35) / 0.4)
            o += g(person(0, 0, 1.6, "#0d0f1a") + g(rect(-20, -90, 40, 24, "#1c7ed6", 6), 0, -120), x, 1450 - 0 * u)
            a = math.radians(-60 + 25 * math.sin(t * 1.7 + k))
            o += f'<path d="M{x},{1240} L{x + 900 * math.cos(a):.0f},{1240 + 900 * math.sin(a):.0f} L{x + 900 * math.cos(a + .3):.0f},{1240 + 900 * math.sin(a + .3):.0f} Z" fill="#fff6d5" opacity=".18"/>'
        rb = (t * 2) % 1 < 0.5
        o += rect(0, 0, W, H, "#1c7ed6" if rb else "#e03131", extra='opacity=".10"')
        return o, cam(1.0 + 0.04 * tl, 540, 1050, sh=1)
    def nobody(tl, d, t):
        o = grad("#15161e", "#07070a") + floor(1450, "#000", .4)
        o += rect(120, 1150, 560, 300, "#2a2b3d", 30, f'stroke="{K}" stroke-width="8"') + rect(760, 700, 240, 750, "#1e1f2c", 10) + window(300, 400, 420, 420, "#0e1230", True, 0, t)
        o += char(t, 800, 1270, 1.2, "fear", "chest", "chest", mouth=0, cable=False, lit=0.5, shiver=0.3, face=-1)
        o += moth_near(t, 760, 1000, 1.6)
        return o, cam(1.0 + 0.06 * tl, 540, 1050)
    def app(tl, d, t):
        o = grad("#f1f3f5", "#dee2e6") + phone(540, 960, 2.2)
        rows = [("Camera", "Living room"), ("Status", "Online"), ("Installed", "—")]
        for k, (a, b) in enumerate(rows):
            y = 700 + k * 160
            if tl > 0.25 * k:
                o += rect(280, y - 70, 520, 120, "#fff", 18, f'stroke="#ced4da" stroke-width="4"') + f'<text x="310" y="{y}" font-family="Inter" font-weight="900" font-size="40" fill="#868e96">{a}</text>'
                o += f'<text x="770" y="{y}" text-anchor="end" font-family="Inter" font-weight="900" font-size="40" fill="{"#e03131" if k == 2 and tl > 1.4 else K}">{esc("NEVER" if k == 2 and tl > 1.4 else b)}</text>'
        if tl > 1.2: o += rect(280, 950, 520, 120, "#ffe3e3", 18) + f'<text x="540" y="1025" text-anchor="middle" font-family="Inter" font-weight="900" font-size="38" fill="#e03131">No camera registered.</text>'
        return o, cam(1.0 + 0.03 * tl)
    def final(tl, d, t):
        o = bedroom(tl, d, t, glow=clamp((tl - 1.6) / 0.2) if tl > 1.6 else 0.0, sit=True, mood="fear", shiver=0.6)
        if tl > 1.6: o += digital(760, 760, "3:07", 120, "#9fc8ff")
        return o, cam(1.0 + 0.1 * ease(tl / 3), 540, 1000)

    shots = [
        (0, S[1] - 0.05, lambda tl, d, t: (bedroom(tl, d, t, glow=clamp((tl - 0.9) / 0.15)) + (digital(540, 700, "3:07", 240, "#9fc8ff") if tl < 0.9 else ""), cam(1.0 + 0.04 * tl, 540, 1000)), "cut"),
        (S[1] - 0.05, S[2] - 0.05, lambda tl, d, t: (grad("#0b0c12", "#000") + phone(540, 960, 2.2) + rect(255, 400, 570, 1120, "#0d0e1a", 20) + rect(280, 520, 520, 220, "#1f2130", 24) + typed("Motion detected", 310, 600, 48, tl / 0.6, "#fff", "Inter") + typed("Living room", 310, 690, 48, (tl - 0.5) / 0.4, "#9fc8ff", "Inter") + circ(760, 450, 18, "#ff2b2b"), cam(1.0 + 0.05 * tl, sh=3 * (tl < 0.15))), "cut"),
        (S[2] - 0.05, S[3] - 0.05, lambda tl, d, t: (bedroom(tl, d, t, glow=1.0, sit=True, shiver=0.3) + bigtext("ALONE.", 540, 600, 170, "#9fc8ff", eout((tl - 0.6) / 0.2)) if tl > 0.6 else bedroom(tl, d, t, glow=1.0, sit=True, shiver=0.3), cam(1.0 + 0.1 * ease(tl / d), 540, 1000)), "cut"),
        (S[3] - 0.05, S[4] - 0.05, lambda tl, d, t: (feed(tl, d, t, 1.0, figure=tl > 0.6), cam(1.0)), "flash"),
        (S[4] - 0.05, S[5] - 0.05, lambda tl, d, t: (feed(tl, d, t, 1.0 + 0.08 * tl), cam(1.0, sh=1)), "cut"),
        (S[5] - 0.05, S[6] - 0.05, lambda tl, d, t: (feed(tl, d, t, 1.25 + 0.12 * tl), cam(1.0, sh=1.5)), "cut"),
        (S[6] - 0.05, S[7] - 0.05, lambda tl, d, t: (bedroom(tl, d, t, glow=1.0, sit=True, shiver=0.6) + (speech(760, 700, "911", 60, tail="right") if tl > 0.3 else ""), cam(1.05, 540, 1000)), "whip"),
        (S[7] - 0.05, S[8] - 0.05, police, "whip"),
        (S[8] - 0.05, S[9] - 0.05, nobody, "cut"),
        (S[9] - 0.05, S[10] - 0.05, lambda tl, d, t: (grad("#000", "#000") + digital(540, 1000, "3:07", 300, "#ff3b30" if (t * 1.5) % 1 < .8 else "#5a1010"), cam(1.0 + 0.08 * tl)), "black"),
        (S[10] - 0.05, S[11] - 0.05, lambda tl, d, t: (feed(tl, d, t, 1.0), cam(1.0, sh=1)), "flash"),
        (S[11] - 0.05, S[12] - 0.05, lambda tl, d, t: (feed(tl, d, t, 1.0 + 2.2 * ease(tl / (d - 0.3))), cam(1.0, sh=2)), "cut"),
        (S[12] - 0.05, S[13] - 0.05, lambda tl, d, t: (feed(tl, d, t, 3.2, clothes=tl > 0.5, shake=1.0) + (bigtext("HIS CLOTHES.", 540, 1650, 110, "#ff5f5f", eout((tl - 0.9) / 0.2)) if tl > 0.9 else ""), cam(1.0, sh=4 * (tl > 0.5))), "cut"),
        (S[13] - 0.05, S[14] - 0.05, app, "whip"),
        (S[14] - 0.05, S[14] + 1.9, lambda tl, d, t: (app(tl + 1.5, d, t)[0], cam(1.0 + 0.25 * ease(tl / 1.8), 540, 1000)), "cut"),
        (S[14] + 1.9, st.TOTAL + 1, final, "black"),
    ]
    buzz_s = np.concatenate([s_buzz(0.12, 60), np.zeros(int(0.1 * SR))] * 2)
    sfx = [(0.9, buzz_s, 1.0), (S[1], s_pop(800, 1200, 0.1), 0.6), (S[2] + 0.6, s_thud(80, 30, 0.6), 1.0), (S[3] + 0.5, s_zap(), 0.6),
           (S[4], s_heart(), 1.0), (S[4] + 0.8, s_heart(), 1.0), (S[5], s_heart(), 1.0), (S[5] + 0.8, s_heart(), 1.1), (S[5] + 1.6, s_heart(), 1.2),
           (S[6] + 0.3, s_pop(600, 900, 0.1), 0.6), (S[7], s_steps(6, 0.3), 1.2), (S[8], s_creak(1.4), 0.8), (S[9], s_thud(60, 25, 0.8), 1.2),
           (S[10], buzz_s, 1.0), (S[11], s_heart(), 1.0), (S[11] + 0.7, s_heart(), 1.1), (S[11] + 1.4, s_heart(), 1.2), (S[12] + 0.5, s_zap(), 1.0), (S[12] + 0.5, s_thud(100, 30, 0.7), 1.2),
           (S[13], s_click(), 0.6), (S[13] + 0.3, s_click(), 0.6), (S[14] + 1.4, s_thud(70, 25, 0.9), 1.2), (st.TOTAL - 1.9, buzz_s, 1.2), (st.TOTAL - 1.9, s_riser(0.8), 0.8)]
    return st, shots, sfx, "creepy", None

if __name__ == "__main__": main(build)
