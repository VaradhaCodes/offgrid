"""Slide C - Technologies + Methodology, redesigned for a 15-second read.
Stage 1920 x 800 (2.4:1) = the content band of a 16:9 slide under a title. Calibri."""
import html

INK="#1B1F26"; MUTED="#4F5967"; FAINT="#6E7887"; HAIR="#C8CED6"; PANEL="#F4F6F8"
AMBER_BG="#FFF4E3"; AMBER_BD="#E1A23F"; AMBER_TX="#8A5300"
GREEN_BG="#EAF7EF"; GREEN_BD="#3AA36C"; GREEN_TX="#1B6E45"

CSS = """
@font-face{font-family:'Calibri';font-weight:400;src:url('fonts/calibri.ttf')}
@font-face{font-family:'Calibri';font-weight:700;src:url('fonts/calibrib.ttf')}
html,body{margin:0;background:#fff}
.stage{position:relative;width:1920px;height:800px;background:#fff;
 font-family:Calibri,Aptos,Arial,sans-serif;color:%(ink)s;overflow:hidden}
.abs{position:absolute;box-sizing:border-box}
.box{position:absolute;box-sizing:border-box;border:2px solid %(hair)s;border-radius:14px;
 padding:18px 22px;background:#fff}
.box.ai{background:%(ambg)s;border-color:%(ambd)s}
.box.gnss{background:%(grbg)s;border-color:%(grbd)s}
.box.hub{border:3.5px solid %(ink)s}
.box h3{margin:0 0 8px;font-size:31px;font-weight:700;line-height:1.06;letter-spacing:-.006em}
.box p{margin:0;font-size:21px;line-height:1.24;color:%(muted)s}
.box p.s{font-size:18px;color:%(faint)s;margin-top:5px}
.tag{position:absolute;right:16px;top:14px;font-size:15px;font-weight:700;letter-spacing:.08em;
 border:2px solid %(ambd)s;color:%(amtx)s;border-radius:7px;padding:1px 9px;background:#fff}
.h1{position:absolute;font-size:39px;font-weight:700;line-height:1.05;letter-spacing:-.012em}
.h2{position:absolute;font-size:23px;line-height:1.2;color:%(muted)s}
.kpi{position:absolute;text-align:right}
.kpi b{display:block;font-size:44px;font-weight:700;line-height:1;letter-spacing:-.02em}
.kpi span{display:block;font-size:18px;line-height:1.25;color:%(faint)s;margin-top:6px}
.lane{position:absolute;font-size:16px;font-weight:700;letter-spacing:.15em;
 color:%(faint)s;text-transform:uppercase}
.rule{position:absolute;height:0;border-top:1.5px solid %(hair)s}
.step{position:absolute;box-sizing:border-box}
.step .n{width:34px;height:34px;border-radius:50%%;border:2.5px solid %(ink)s;font-size:19px;
 font-weight:700;display:flex;align-items:center;justify-content:center;margin-bottom:11px}
.step p{margin:0;font-size:19.5px;line-height:1.25;color:%(muted)s}
.step p b{color:%(ink)s;font-weight:700;display:block;font-size:21px;margin-bottom:3px}
.ts{position:absolute;box-sizing:border-box;padding:16px 22px 14px;border-radius:14px;background:%(pan)s}
.ts p{margin:0 0 9px;font-size:20px;line-height:1.22;color:%(muted)s}
.ts p:last-child{margin-bottom:0}
.ts p b{color:%(ink)s;font-weight:700}
.ts p i{font-style:normal;color:%(faint)s;font-size:15px;font-weight:700;letter-spacing:.11em;
 text-transform:uppercase;display:inline-block;width:96px}
.note{position:absolute;box-sizing:border-box;padding:16px 22px;border-radius:14px;background:%(pan)s}
.note p{margin:0 0 7px;font-size:20.5px;line-height:1.22;color:%(muted)s}
.note p:last-child{margin-bottom:0}
.note p b{color:%(ink)s;font-weight:700}
"""%dict(ink=INK,muted=MUTED,faint=FAINT,hair=HAIR,ambg=AMBER_BG,ambd=AMBER_BD,amtx=AMBER_TX,
         grbg=GREEN_BG,grbd=GREEN_BD,pan=PANEL)

AUDIT = """<script>
if(location.search.indexOf('audit')>=0){document.querySelectorAll('.box,.ts,.note,.step,.h1,.h2').forEach(function(b){
 if(b.scrollHeight>b.clientHeight+1||b.scrollWidth>b.clientWidth+1){b.style.outline='4px solid red';}});}
</script>"""

E=[]; SVG=[]
def esc(s): return html.escape(s,quote=True)
def add(s): E.append(s)
def box(x,y,w,h,title,paras,kind="",tag=None):
    body="".join(f'<p class="{c}">{t}</p>' if c else f'<p>{t}</p>'
                 for c,t in [(p if isinstance(p,tuple) else ("",p)) for p in paras])
    t=f'<span class="tag">{esc(tag)}</span>' if tag else ""
    add(f'<div class="box {kind}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">{t}<h3>{title}</h3>{body}</div>')
def path(d,color=INK,w=3,head=True):
    mk={GREEN_BD:"ag",AMBER_BD:"aa"}.get(color,"ai")
    hh=f' marker-end="url(#{mk})"' if head else ""
    SVG.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linejoin="round"{hh}/>')
def label(x,y,t,anchor="start",color=FAINT,size=17):
    SVG.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="{size}" '
               f'font-weight="700" font-family="Calibri,Arial,sans-serif">{esc(t)}</text>')

# ---------------------------------------------------------------- headline
add(f'<div class="h1" style="left:40px;top:6px;width:1240px">GNSS drops. The marker keeps moving.</div>')
add(f'<div class="h2" style="left:40px;top:54px;width:1240px">'
    f'A learned speed model and inertial heading carry the rider along the road &mdash; phone only, fully offline.</div>')
add(f'<div class="kpi" style="left:1300px;top:8px;width:580px">'
    f'<b>1.52 %</b><span>median drift, GNSS withheld for 600&ndash;850 m &middot; 10 of 10 rides under 10 %</span></div>')

# ---------------------------------------------------------------- the spine
SY, SH, HY, HH = 128, 158, 108, 198       # spine boxes / hub box
X  = [40, 376, 732, 1144, 1580]
W  = [296, 316, 372, 396, 300]
add(f'<div class="lane" style="left:40px;top:104px">Runs on the phone &middot; 10 times a second</div>')
SY, HY = 136, 116; SH, HH = 158, 198       # spine centre = 215
box(X[0], SY, W[0], SH, "Phone sensors", ["Accelerometer + gyroscope", ("s","419 Hz, frame-mounted")])
box(X[1], SY, W[1], SH, "Align to the bike", ["Resample to 100 Hz; remove gravity and gyro bias; find the forward axis"])
box(X[2], SY, W[2], SH, "Speed CNN", ["2.56 s of motion &rarr; speed &plusmn; &sigma;", ("s","57 k parameters &middot; 240 KB &middot; 0.07 ms per step")], kind="ai", tag="AI")
box(X[3], HY, W[3], HH, "Fusion filter", ["Kalman filter tracks distance along the road and heading, and folds GNSS in only while it is trustworthy"], kind="hub")
box(X[4], SY, W[4], SH, "Live map", ["Marker never freezes; the trail goes dashed with a 2&sigma; band while dead reckoning"])
for i in range(4):
    x1 = X[i]+W[i]+4; x2 = X[i+1]-7
    path(f"M{x1},215 L{x2},215", w=3.2)

# ------------------------------------------------------- supporting sources
RY, RH = 396, 108
box(732, RY, 372, RH, "", ["<b style=\"color:%s\">GNSS</b> &nbsp;1 Hz fix + Doppler speed"%INK,
    ("s","dropped on gap &gt; 1.5 s, &lt; 4 satellites, accuracy &gt; 30 m")], kind="gnss")
box(1144, RY, 396, RH, "", ["<b style=\"color:%s\">Offline road data</b> &nbsp;corridor polyline"%INK,
    ("s","OpenStreetMap graph + PMTiles, no network needed")])
path("M918,392 L918,352 L1234,352 L1234,320", color=GREEN_BD, w=3.2)
path("M1342,392 L1342,320", w=3.2)
# break symbol on the GNSS feed
SVG.append('<rect x="1000" y="336" width="42" height="32" fill="#fff"/>')
for dx in (0,16):
    SVG.append(f'<line x1="{1006+dx}" y1="366" x2="{1020+dx}" y2="338" stroke="{GREEN_BD}" stroke-width="3.2" stroke-linecap="round"/>')
label(1021, 330, "cut", "middle", GREEN_TX)

add(f'<div class="note" style="left:40px;top:{RY}px;width:652px;height:{RH}px">'
    f'<p><b>GNSS lost</b> &nbsp;predict only &middot; uncertainty grows &middot; trail turns dashed</p>'
    f'<p><b>GNSS back</b> &nbsp;de-weighted for 3 s &mdash; the marker glides, never jumps</p></div>')

# ---------------------------------------------------------------- bottom band
add(f'<div class="rule" style="left:40px;top:540px;width:1840px"></div>')
add(f'<div class="lane" style="left:40px;top:558px">How it was built</div>')
add(f'<div class="lane" style="left:1180px;top:558px">Technologies</div>')

steps = [("Ride and log","A bicycle on campus roads, phone in the bottle cage, 22 sensor streams"),
         ("30 rides","Two roads, ridden both ways, 265 m and 660 m legs, one with a 120&deg; turn"),
         ("Train","A small CNN learns speed from motion alone, with GNSS speed as the label"),
         ("Hold out","Test on a road the model never trained on, GNSS withheld mid-ride"),
         ("Ship on-device","240 KB model in the app; the same engine runs live and replays any ride")]
for i,(t,p) in enumerate(steps):
    x = 40 + i*224
    add(f'<div class="step" style="left:{x}px;top:596px;width:204px;height:190px">'
        f'<div class="n">{i+1}</div><p><b>{t}</b>{p}</p></div>')
    if i < 4:
        path(f"M{x+204+2},614 L{x+218},614", w=2.4)

add(f'<div class="ts" style="left:1180px;top:592px;width:700px;height:194px">'
    f'<p><i>App</i><b>Kotlin</b> &middot; Jetpack Compose &middot; Android</p>'
    f'<p><i>Model</i><b>PyTorch</b> to train &rarr; <b>LiteRT</b> + XNNPACK on the phone</p>'
    f'<p><i>Maps</i><b>MapLibre</b> &middot; OpenStreetMap &middot; PMTiles, all offline</p>'
    f'<p><i>Engine</i>Pure-Kotlin module, matches the Python reference to <b>7 mm</b></p>'
    f'<p><i>Hardware</i>A stock Android phone. <b>Nothing is added to the vehicle.</b></p>'
    f'</div>')

# ---------------------------------------------------------------- render
defs="".join(f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.2" markerHeight="5.2" '
             f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
             for i,c in (("ai",INK),("ag",GREEN_BD),("aa",AMBER_BD)))
svg=f'<svg style="position:absolute;left:0;top:0;pointer-events:none" width="1920" height="800" viewBox="0 0 1920 800"><defs>{defs}</defs>{"".join(SVG)}</svg>'
open("C_tech_method.html","w").write(
 f'<!doctype html><html><head><meta charset="utf-8"><title>Technologies and methodology</title>'
 f'<style>{CSS}</style></head><body><div class="stage">{"".join(E)}{svg}</div>{AUDIT}</body></html>')
print("ok")
