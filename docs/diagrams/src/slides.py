"""Two slide contents, HTML + CSS boxes (natural text wrapping) with an SVG arrow layer.
Stage 1920 x 800 (2.4 : 1) = the content band of a 16:9 slide under a title. Calibri."""
import json, math, os, html

INK = "#1B1F26"; MUTED = "#4F5967"; FAINT = "#6E7887"; HAIR = "#C5CBD3"
AMBER_BG = "#FFF4E3"; AMBER_BD = "#E1A23F"; AMBER_TX = "#8A5300"
GREEN_BG = "#EAF7EF"; GREEN_BD = "#3AA36C"; GREEN_TX = "#1B6E45"
BLUE_BD = "#3A9AD9"

CSS = """
@font-face{font-family:'Calibri';font-weight:400;src:url('fonts/calibri.ttf')}
@font-face{font-family:'Calibri';font-weight:700;src:url('fonts/calibrib.ttf')}
@font-face{font-family:'Calibri';font-weight:300;src:url('fonts/calibril.ttf')}
@font-face{font-family:'Calibri';font-style:italic;src:url('fonts/calibrii.ttf')}
html,body{margin:0;background:#fff}
.stage{position:relative;width:1920px;height:800px;background:#fff;font-family:Calibri,Aptos,Arial,sans-serif;color:%(ink)s;overflow:hidden}
.box{position:absolute;box-sizing:border-box;border:2px solid %(hair)s;border-radius:12px;padding:16px 20px;background:#fff}
.box.ai{background:%(ambg)s;border-color:%(ambd)s}
.box.gnss{background:%(grbg)s;border-color:%(grbd)s}
.box.hub{border:3px solid %(ink)s;border-radius:14px}
.box.plain{border-color:transparent;padding:0}
.box h3{margin:0 0 6px;font-size:27px;font-weight:700;line-height:1.1;letter-spacing:-.005em}
.box p{margin:0;font-size:19px;line-height:1.28;color:%(muted)s}
.box p.k{color:%(ink)s;font-weight:700}
.box p.s{font-size:17px;color:%(faint)s;line-height:1.25}
.lane{position:absolute;font-size:16px;font-weight:700;letter-spacing:.14em;color:%(faint)s;text-transform:uppercase}
.tag{position:absolute;right:14px;top:12px;font-size:14px;font-weight:700;letter-spacing:.06em;border:1.5px solid %(ambd)s;color:%(amtx)s;border-radius:6px;padding:1px 8px;background:%(ambg)s}
.hr{position:absolute;left:20px;right:20px;height:0;border-top:1.5px solid %(hair)s}
.port{position:absolute;left:0;display:flex;align-items:center;gap:12px;font-size:18px;color:%(ink)s;white-space:nowrap}
.port .dot{width:12px;height:12px;border-radius:50%%;border:2.5px solid %(ink)s;background:#fff;margin-left:-8px;flex:none}
.port .role{font-size:14px;font-weight:700;letter-spacing:.06em;color:%(faint)s;border:1.5px solid %(hair)s;border-radius:5px;padding:1px 7px;margin-left:4px}
.abs{position:absolute}
svg.arrows{position:absolute;left:0;top:0;pointer-events:none}
.lbl{font-family:Calibri,Aptos,Arial,sans-serif;font-size:16px;font-weight:700;fill:%(faint)s}
.cap{position:absolute;font-size:18px;line-height:1.3;color:%(muted)s}
.phone{position:absolute;border-radius:22px;border:2.5px solid #8A939E;overflow:hidden;background:#111}
.phone img{display:block;width:100%%;height:100%%;object-fit:cover}
.plabel{position:absolute;font-size:21px;font-weight:700;color:%(ink)s;display:flex;align-items:center;gap:10px;white-space:nowrap}
.plabel .d{width:13px;height:13px;border-radius:50%%;flex:none}
.tile{position:absolute;box-sizing:border-box;border:2px solid %(hair)s;border-radius:12px;background:#fff;padding:16px 20px}
.tile h3{margin:0;font-size:26px;font-weight:700;line-height:1.1}
.tile p{margin:0;font-size:18px;line-height:1.28;color:%(muted)s}
.tile p.k{color:%(ink)s;font-weight:700}
.tile .cap{font-size:15px;color:%(faint)s}
.ts{position:absolute;box-sizing:border-box;padding:14px 18px;border-radius:12px;background:#F3F5F7}
.ts h4{margin:0 0 8px;font-size:15px;font-weight:700;letter-spacing:.14em;color:%(faint)s;text-transform:uppercase}
.ts p{margin:0 0 8px;font-size:17.5px;line-height:1.25;color:%(muted)s}
.ts p b{color:%(ink)s;font-weight:700}
""" % dict(ink=INK, muted=MUTED, faint=FAINT, hair=HAIR, ambg=AMBER_BG, ambd=AMBER_BD, amtx=AMBER_TX, grbg=GREEN_BG, grbd=GREEN_BD)

AUDIT = """<script>
if(location.search.indexOf('audit')>=0){document.querySelectorAll('.box,.tile,.ts,.plabel,.cap').forEach(function(b){
 if(b.scrollHeight>b.clientHeight+1||b.scrollWidth>b.clientWidth+1){b.style.outline='4px solid red';b.setAttribute('data-ovf',b.scrollHeight+'/'+b.clientHeight+' '+b.scrollWidth+'/'+b.clientWidth);}});}
</script>"""


def esc(s): return html.escape(s, quote=True)


class Stage:
    def __init__(self, w=1920, h=800):
        self.w, self.h = w, h; self.el = []; self.svg = []
        self.boxes = {}

    def add(self, s): self.el.append(s)

    def box(self, key, x, y, w, h, title, paras, kind="", tag=None, extra=""):
        self.boxes[key] = (x, y, w, h)
        body = "".join(f'<p class="{c}">{t}</p>' if c else f'<p>{t}</p>' for c, t in [(p if isinstance(p, tuple) else ("", p)) for p in paras])
        t = f'<span class="tag">{esc(tag)}</span>' if tag else ""
        self.add(f'<div class="box {kind}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">{t}<h3>{title}</h3>{body}{extra}</div>')

    def lane(self, x, y, t): self.add(f'<div class="lane" style="left:{x}px;top:{y}px">{esc(t)}</div>')

    # arrows ---------------------------------------------------------------
    def path(self, d, color=INK, w=2.2, dash=None, head=True, halo=False):
        mk = {GREEN_BD: "ag", AMBER_BD: "aa"}.get(color, "ai")
        if halo: self.svg.append(f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{w + 8}"/>')
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        hh = f' marker-end="url(#{mk})"' if head else ""
        self.svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linejoin="round"{dd}{hh}/>')

    def line(self, x1, y1, x2, y2, **k): self.path(f"M{x1},{y1} L{x2},{y2}", **k)

    def elbow(self, x1, y1, x2, y2, xm=None, **k):
        xm = (x1 + x2) / 2 if xm is None else xm
        self.path(f"M{x1},{y1} L{xm},{y1} L{xm},{y2} L{x2},{y2}", **k)

    def vline(self, x, y1, y2, **k): self.path(f"M{x},{y1} L{x},{y2}", **k)

    def label(self, x, y, t, anchor="start", color=FAINT):
        self.svg.append(f'<text class="lbl" x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}">{esc(t)}</text>')

    def right(self, key): x, y, w, h = self.boxes[key]; return x + w
    def left(self, key): return self.boxes[key][0]
    def top(self, key): return self.boxes[key][1]
    def bottom(self, key): x, y, w, h = self.boxes[key]; return y + h
    def cy(self, key): x, y, w, h = self.boxes[key]; return y + h / 2
    def cx(self, key): x, y, w, h = self.boxes[key]; return x + w / 2

    def html(self, title):
        defs = "".join(f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for i, c in (("ai", INK), ("ag", GREEN_BD), ("aa", AMBER_BD)))
        svg = f'<svg class="arrows" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}"><defs>{defs}</defs>{"".join(self.svg)}</svg>'
        return f'<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)}</title><style>{CSS}</style></head><body><div class="stage">{"".join(self.el)}{svg}</div>{AUDIT}</body></html>'


# =====================================================================
# SLIDE A — the architecture (what runs on the phone)
# =====================================================================
def slide_a():
    S = Stage()
    L0, W0 = 40, 260          # inputs
    L1, W1 = 346, 330         # estimation 1
    L2, W2 = 722, 330         # estimation 2
    LH, WH = 1108, 380        # hub
    LO, WO = 1538, 342        # output
    T = 56
    S.lane(L0, 20, "Inputs"); S.lane(L1, 20, "Estimation · 100 Hz"); S.lane(LH, 20, "Fusion · 10 Hz"); S.lane(LO, 20, "Output")

    # inputs
    S.box("imu", L0, T, W0, 118, "Accelerometer + gyroscope", ["419 Hz, phone frame"])
    S.box("gnss", L0, 404, W0, 150, "GNSS receiver", ["1 Hz position + Doppler speed", ("s", "C/N0 · satellites · accuracy")], kind="gnss")
    S.box("road", L0, 598, W0, 142, "Offline road data", ["corridor polylines", "campus road graph + map tiles"])

    # estimation 1
    S.box("align", L1, T, W1, 314, "Resample + align", [
        "causal 40 Hz filter → 100 Hz grid",
        "15 s still stand → gyro bias, gravity",
        "gravity → roll, pitch",
        "pedalling sway → forward axis",
        "phone frame → vehicle frame"])
    S.box("gate", L1, 404, W1, 176, "GNSS quality gate", [
        "drops a fix on: gap > 1.5 s, accuracy > 30 m, < 4 satellites, low C/N0",
        ("s", "test mode withholds fixes in a marked band")], kind="gnss")
    S.box("corr", L1, 600, W1, 140, "Corridor recognition", [
        "first fixes near a known road → its polyline and direction",
        ("s", "else: HMM map match, display only")])

    # estimation 2
    S.box("cnn", L2, T, W2, 150, "Speed CNN", [
        "2.56 s window → speed ± σ",
        "57 k parameters · LiteRT · 0.07 ms",
        ("s", "a physical stop rule forces v = 0")], kind="ai", tag="AI")
    S.box("head", L2, 230, W2, 150, "Heading filter", [
        "100 Hz quaternion, tilt corrected",
        "yaw trimmed by GNSS course while locked, 5σ gated"])

    # hub
    HH = 684
    S.box("hub", LH, T, WH, HH, "Fusion filter", [], kind="hub")
    x0 = LH + 20
    S.add(f'<p class="abs s" style="left:{x0}px;top:{T + 50}px;width:{WH - 40}px;margin:0;font-size:17px;color:{FAINT};line-height:1.25">10 Hz · 5σ innovation gate on every update</p>')
    S.add(f'<div class="hr" style="left:{x0}px;top:{T + 82}px;width:{WH - 40}px"></div>')
    S.add(f'<p class="abs" style="left:{x0}px;top:{T + 94}px;width:{WH - 40}px;margin:0;font-size:20px;line-height:1.3;color:{MUTED}"><b style="color:{INK}">State</b>&nbsp; corridor mode: s along the road, v<br>general mode: x, y, v</p>')
    S.add(f'<p class="abs" style="left:{x0}px;top:{T + 158}px;margin:0;font-size:16px;font-weight:700;letter-spacing:.12em;color:{FAINT}">MEASUREMENTS IN</p>')
    ports = [("p_cnn", 250, "speed v ± σ; v = 0 when stopped", "update"),
             ("p_head", 300, "heading ψ", "predict"),
             ("p_gnss", 350, "GNSS position + speed, if trusted", "update"),
             ("p_road", 400, "road polyline + travel direction", "track")]
    P = {}
    for key, y, t, role in ports:
        S.add(f'<div class="port" style="left:{LH}px;top:{y - 14}px"><span class="dot"></span><span>{esc(t)}</span><span class="role">{role}</span></div>')
        P[key] = y
    S.add(f'<div class="hr" style="left:{x0}px;top:{T + 380}px;width:{WH - 40}px"></div>')
    S.add(f'<p class="abs" style="left:{x0}px;top:{T + 394}px;width:{WH - 40}px;margin:0;font-size:20px;line-height:1.3;color:{MUTED}">'
          f'<b style="color:{INK}">GNSS lost</b>&nbsp; predict only; σ grows; trail drawn dashed with a 2σ ribbon<br>'
          f'<b style="color:{INK}">GNSS back</b>&nbsp; updates inflated ×4 for 3 s, so the marker glides, never jumps<br>'
          f'<b style="color:{INK}">Modes</b>&nbsp; GNSS+INS · inertial · recovering</p>')
    S.add(f'<div class="hr" style="left:{x0}px;top:{T + 560}px;width:{WH - 40}px"></div>')
    S.add(f'<p class="abs" style="left:{x0}px;top:{T + 574}px;width:{WH - 40}px;margin:0;font-size:20px;line-height:1.3;color:{MUTED}"><b style="color:{INK}">Out</b>&nbsp; position, heading, speed, mode, σ — 10 times a second<br><span style="font-size:17px;color:{FAINT}">tick 0.16 ms on a Galaxy S23 Ultra</span></p>')

    # output
    S.box("ui", LO, T, WO, 212, "Navigation screen", [
        "marker always moving, course-up map",
        "trail solid when locked; dashed with a 2σ ribbon when dead reckoning",
        "re-lock reveal with the miss distance"])
    S.box("log", LO, 278, WO, 144, "Logs + replay", [
        "engine state at 10 Hz plus all 22 sensor streams; any ride replays through the same engine"])
    # tech stack
    S.add(f'''<div class="ts" style="left:{LO}px;top:446px;width:{WO}px;height:294px">
<h4>Tech stack</h4>
<p><b>Android</b> · Kotlin · Jetpack Compose</p>
<p><b>LiteRT</b> (TensorFlow Lite) · XNNPACK</p>
<p><b>MapLibre</b> · OpenStreetMap · PMTiles, offline</p>
<p><b>PyTorch</b> · NumPy · SciPy for training and evaluation</p>
<p><b>Engine</b> pure-Kotlin module, matches the Python reference to 7 mm</p>
</div>''')

    # arrows ------------------------------------------------------------
    S.line(S.right("imu"), S.cy("imu"), S.left("align") - 3, S.cy("imu"))
    S.line(S.right("align"), S.cy("cnn"), S.left("cnn") - 3, S.cy("cnn"))
    S.line(S.right("align"), S.cy("head"), S.left("head") - 3, S.cy("head"))
    # cnn / head -> hub ports
    S.elbow(S.right("cnn"), S.cy("cnn"), LH - 8, P["p_cnn"], xm=LH - 16, color=AMBER_BD, w=2.6)
    S.elbow(S.right("head"), S.cy("head"), LH - 8, P["p_head"], xm=LH - 28)
    # gnss -> gate -> hub ; gate -> heading (course) ; gate -> corridor (first fixes)
    S.line(S.right("gnss"), S.cy("gnss"), S.left("gate") - 3, S.cy("gnss"), color=GREEN_BD, w=2.6)
    S.elbow(S.right("gate"), S.cy("gate") + 16, LH - 8, P["p_gnss"], xm=LH - 40, color=GREEN_BD, w=2.6)
    S.label(S.right("gate") + 8, S.cy("gate") + 8, "accepted fixes")
    hx = S.cx("head") + 40
    S.path(f"M{S.right('gate')},{S.cy('gate') - 22} L{hx},{S.cy('gate') - 22} L{hx},{S.bottom('head') + 3}", color=GREEN_BD, w=2.6)
    S.label(hx - 10, S.bottom("head") + 26, "course, while locked", anchor="end")
    gx = S.cx("gate")
    S.vline(gx, S.bottom("gate"), S.top("corr") - 3, color=GREEN_BD, w=2.6)
    S.label(gx + 8, S.bottom("gate") + 28, "first fixes")
    # road -> corridor -> hub
    S.line(S.right("road"), S.cy("road"), S.left("corr") - 3, S.cy("road"))
    S.elbow(S.right("corr"), S.cy("corr"), LH - 8, P["p_road"], xm=LH - 52)
    # hub -> outputs
    S.line(LH + WH, S.cy("ui"), S.left("ui") - 3, S.cy("ui"), w=2.6)
    S.line(LH + WH, S.cy("log"), S.left("log") - 3, S.cy("log"))
    # legend
    S.add(f'<div class="abs" style="left:40px;top:764px;font-size:16px;color:{FAINT};display:flex;gap:36px;align-items:center">'
          f'<span><span style="display:inline-block;width:18px;height:12px;background:{AMBER_BG};border:1.5px solid {AMBER_BD};border-radius:3px;vertical-align:-1px;margin-right:8px"></span>learned model</span>'
          f'<span><span style="display:inline-block;width:18px;height:12px;background:{GREEN_BG};border:1.5px solid {GREEN_BD};border-radius:3px;vertical-align:-1px;margin-right:8px"></span>GNSS path — used only while trusted</span>'
          f'<span><span style="display:inline-block;width:11px;height:11px;border:2.5px solid {INK};border-radius:50%;vertical-align:-1px;margin-right:8px"></span>measurement into the filter</span></div>')
    return S.html("Architecture")


# =====================================================================
# SLIDE B — the working prototype
# =====================================================================
def slide_b():
    S = Stage()
    d = json.load(open("imu_window.json"))
    rows = [("acc", 0), ("acc", 1), ("acc", 2), ("gyr", 0), ("gyr", 1), ("gyr", 2)]

    TW, TH = 404, 354
    TX = [40, 476]; TY = [40, 424]

    def tile(x, y, title, inner):
        S.add(f'<div class="tile" style="left:{x}px;top:{y}px;width:{TW}px;height:{TH}px"><h3>{esc(title)}</h3>{inner}</div>')

    # --- 1 Ride ---------------------------------------------------------
    k = 1.55
    def P(px, py, ox, oy): return (ox + px * k, oy + py * k)
    ox, oy = 60, 50
    parts = []
    for cx, cy in ((30, 66), (118, 66)):
        X, Y = P(cx, cy, ox, oy); parts.append(f'<circle cx="{X}" cy="{Y}" r="{24 * k}" fill="none" stroke="{INK}" stroke-width="2.4"/><circle cx="{X}" cy="{Y}" r="{2.2 * k}" fill="{INK}"/>')
    for a, b in [((64, 68), (56, 30)), ((64, 68), (100, 34)), ((56, 30), (100, 34)), ((30, 66), (64, 68)), ((30, 66), (56, 30)), ((100, 34), (118, 66)), ((100, 34), (104, 24)), ((56, 30), (54, 22))]:
        (x1, y1), (x2, y2) = P(*a, ox, oy), P(*b, ox, oy); parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="2.4"/>')
    for a, b in [((46, 22), (62, 22)), ((98, 22), (110, 20))]:
        (x1, y1), (x2, y2) = P(*a, ox, oy), P(*b, ox, oy); parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="3.6" stroke-linecap="round"/>')
    mx, my = P(83, 51, ox, oy); ang = math.degrees(math.atan2(34 - 68, 100 - 64))
    parts.append(f'<g transform="translate({mx},{my}) rotate({ang:.1f})"><rect x="{-11 * k}" y="{-6 * k}" width="{22 * k}" height="{12 * k}" rx="3" fill="{AMBER_BG}" stroke="{AMBER_BD}" stroke-width="2"/></g>')
    parts.append(f'<text x="{mx + 4}" y="{my + 34}" font-size="15" font-weight="700" fill="{AMBER_TX}" text-anchor="middle">phone</text>')
    bike = f'<svg width="{TW - 40}" height="192" viewBox="0 0 {TW - 40} 192" style="position:absolute;left:20px;top:44px">{"".join(parts)}</svg>'
    photo = '<img src="img/bike.jpg" style="position:absolute;left:20px;top:46px;width:%dpx;height:184px;object-fit:cover;border-radius:8px">' % (TW - 40) if os.path.exists("img/bike.jpg") else bike
    tile(TX[0], TY[0], "Ride", photo + f'<p style="position:absolute;left:20px;top:246px;width:{TW - 40}px">A bicycle on campus roads. A Galaxy S23 Ultra sits in the bottle cage, frame-fixed. No wheel sensor, no link to the vehicle.</p>')

    # --- 2 Log ----------------------------------------------------------
    gw, gh = 236, 150
    pl = []
    for i, (kk, ch) in enumerate(rows):
        v = [r[ch] for r in d[kk]][::3]
        lo, hi = min(v), max(v); rng = (hi - lo) or 1; rh = gh / 6
        pts = " ".join(f"{6 + (j / (len(v) - 1)) * (gw - 12):.1f},{i * rh + rh - 3 - (val - lo) / rng * (rh - 6):.1f}" for j, val in enumerate(v))
        pl.append(f'<polyline points="{pts}" fill="none" stroke="{INK if kk == "acc" else MUTED}" stroke-width="1.1" opacity="{0.95 if kk == "acc" else 0.7}"/>')
    trace = f'<svg width="{gw}" height="{gh}" viewBox="0 0 {gw} {gh}" style="position:absolute;left:146px;top:48px;background:#F3F5F7;border-radius:6px">{"".join(pl)}</svg>'
    tile(TX[1], TY[0], "Log",
         f'<img src="img/hp_logger.png" style="position:absolute;left:20px;top:48px;width:108px;height:232px;object-fit:cover;border-radius:8px;border:1.5px solid {HAIR}">'
         + trace + f'<p class="cap" style="position:absolute;left:146px;top:204px;width:236px">2.56 s of a real ride, 6 channels</p>'
         + f'<p style="position:absolute;left:146px;top:232px;width:236px">Logger app: 22 sensor streams, IMU 419 Hz, GNSS 1 Hz, one clock. 15 s still stand at both ends.</p>')

    # --- 3 Thirty rides --------------------------------------------------
    r1 = json.load(open("corridor_route1.json")); r2 = json.load(open("corridor_route2.json"))
    r1 = [(px + 340.3, py - 351.3) for px, py in r1]
    allp = r1 + r2
    minx, maxx = min(p[0] for p in allp), max(p[0] for p in allp); miny, maxy = min(p[1] for p in allp), max(p[1] for p in allp)
    mw, mh = 176, 176; sc = min(mw / (maxx - minx), mh / (maxy - miny))
    def M(p): return (6 + (p[0] - minx) * sc, 6 + (maxy - p[1]) * sc)
    def poly(pts, col, sw): return f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in map(M, pts))}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>'
    mp = [poly(r1, MUTED, 3), poly(r2, INK, 4)]
    for pts, col in ((r2, INK), (r1, MUTED)):
        for p in (pts[0], pts[-1]):
            X, Y = M(p); mp.append(f'<circle cx="{X}" cy="{Y}" r="5" fill="#fff" stroke="{col}" stroke-width="2.4"/>')
    a2, b2, a1 = M(r2[0]), M(r2[-1]), M(r1[0])
    mp.append(f'<text x="{a2[0] - 9}" y="{a2[1] + 5}" font-size="15" font-weight="700" fill="{INK}" text-anchor="end">A</text>')
    mp.append(f'<text x="{b2[0] + 10}" y="{b2[1] + 5}" font-size="15" font-weight="700" fill="{INK}">B</text>')
    lp = M(r2[27]); mp.append(f'<text x="{lp[0] - 10}" y="{lp[1] + 5}" font-size="15" font-weight="700" fill="{INK}" text-anchor="end">road 2</text>')
    tp = M(r2[10]); mp.append(f'<text x="{tp[0] + 9}" y="{tp[1] + 5}" font-size="14" fill="{MUTED}">120° turn</text>')
    mp.append(f'<text x="{a1[0] + 11}" y="{a1[1] + 5}" font-size="15" font-weight="700" fill="{MUTED}">road 1</text>')
    mp.append(f'<line x1="6" y1="{mh + 22}" x2="{6 + 100 * sc:.1f}" y2="{mh + 22}" stroke="{INK}" stroke-width="2"/><text x="{12 + 100 * sc:.1f}" y="{mh + 27}" font-size="14" fill="{MUTED}">100 m</text>')
    mapsvg = f'<svg width="{mw + 60}" height="{mh + 40}" viewBox="0 0 {mw + 60} {mh + 40}" style="position:absolute;left:20px;top:56px">{"".join(mp)}</svg>'
    tile(TX[0], TY[1], "30 rides", mapsvg + f'<p style="position:absolute;left:226px;top:60px;width:156px">2 campus roads, ridden A→B and B→A as separate runs.</p>'
         + f'<p style="position:absolute;left:226px;top:160px;width:156px">30 kept rides, 265 m and 660 m legs. Road 2 has the 120° turn.</p>')

    # --- 4 Train and test -------------------------------------------------
    cx0, cy0 = 0, 0
    cn = [f'<rect x="0" y="0" width="60" height="90" rx="4" fill="#F3F5F7"/>']
    for i, (kk, ch) in enumerate(rows):
        v = [r[ch] for r in d[kk]][::8]
        lo, hi = min(v), max(v); rng = (hi - lo) or 1; rh = 90 / 6
        pts = " ".join(f"{4 + (j / (len(v) - 1)) * 52:.1f},{i * rh + rh - 2 - (val - lo) / rng * (rh - 4):.1f}" for j, val in enumerate(v))
        cn.append(f'<polyline points="{pts}" fill="none" stroke="{INK if kk == "acc" else MUTED}" stroke-width="0.9"/>')
    cn.append(f'<text x="30" y="110" font-size="14" fill="{MUTED}" text-anchor="middle">256 × 6</text>')
    cn.append(f'<line x1="66" y1="45" x2="82" y2="45" stroke="{INK}" stroke-width="2" marker-end="url(#ak)"/>')
    for i, h_ in enumerate([80, 62, 48, 36]):
        cn.append(f'<rect x="{88 + i * 21}" y="{45 - h_ / 2}" width="15" height="{h_}" rx="3" fill="{AMBER_BG}" stroke="{AMBER_BD}" stroke-width="1.5"/>')
    cn.append(f'<text x="128" y="110" font-size="14" font-weight="700" fill="{AMBER_TX}" text-anchor="middle">conv × 4</text>')
    cn.append(f'<line x1="176" y1="45" x2="192" y2="45" stroke="{INK}" stroke-width="2" marker-end="url(#ak)"/>')
    cn.append(f'<text x="200" y="52" font-size="22" font-weight="700" fill="{INK}">v ± σ</text>')
    cnn = f'<svg width="270" height="118" viewBox="0 0 270 118" style="position:absolute;left:20px;top:50px"><defs><marker id="ak" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>{"".join(cn)}</svg>'
    tile(TX[1], TY[1], "Train and test", cnn
         + f'<p style="position:absolute;left:20px;top:176px;width:{TW - 40}px">Speed CNN, 57 k parameters, 240 KB, with GNSS speed as the label.</p>'
         + f'<p style="position:absolute;left:20px;top:226px;width:{TW - 40}px">Held out on road 2, 10 rides, GNSS withheld from 30 s after motion start (600–850 m):</p>'
         + f'<p class="k" style="position:absolute;left:20px;top:280px;width:{TW - 40}px;font-size:20px">drift 1.52 % median · 5.73 % worst<br>10 of 10 under 10 %</p>')

    # arrow: tiles -> phones
    S.path(f"M896,400 L940,400", w=2.6)

    # --- phones -----------------------------------------------------------
    PW, PH = 296, 541
    PX = [968, 1290, 1612]; PY = 84
    shots = [("img/hp_locked.png", GREEN_BD, "GNSS locked · test band ahead"),
             ("img/hp_dr.png", AMBER_BD, "GNSS withheld · dead reckoning"),
             ("img/hp_reveal.png", GREEN_BD, "GNSS back · off by 17.3 m")]
    for (src, col, cap), px in zip(shots, PX):
        S.add(f'<div class="plabel" style="left:{px}px;top:46px"><span class="d" style="background:{col}"></span>{esc(cap)}</div>')
        S.add(f'<div class="phone" style="left:{px}px;top:{PY}px;width:{PW}px;height:{PH}px"><img src="{src}"></div>')
    for i in range(2):
        S.path(f"M{PX[i] + PW + 4},{PY + PH / 2} L{PX[i + 1] - 6},{PY + PH / 2}", w=2)
    S.add(f'<p class="cap" style="left:{PX[0]}px;top:{PY + PH + 22}px;width:{PX[2] + PW - PX[0]}px;margin:0">'
          f'The app on a Galaxy S23 Ultra, replaying a recorded ride on road 2. GNSS is withheld for 569 m through the 120° turn (the SIM tag); the marker keeps moving on motion sensors alone. '
          f'When GNSS returns, the withheld track is revealed and the miss is printed. A live ride uses the same engine and screens.</p>')
    return S.html("Working prototype")


open("A_architecture.html", "w").write(slide_a())
open("B_prototype.html", "w").write(slide_b())
print("ok")
