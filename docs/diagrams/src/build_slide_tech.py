"""Builds ../slide_technical_approach.html - one self-contained 1280x720 SIH slide.
Header / body / footer are three separate divs; the body works alone as 1280x530."""
import base64, io, os
from PIL import Image

SCR   = "/private/tmp/claude-501/-Users-lokkeshayyappan-HACKATHON/a87e2c47-0afe-4db5-88a2-6ce786ef3eca/scratchpad"
MEDIA = f"{SCR}/logos/ppt/media"      # brand logos, from "logo slide (organised).pptx"
DECK  = f"{SCR}/deck/ppt/media"       # SIH logo, from the user's own SIH template deck

def b64(path, w=None, h=None):
    im = Image.open(path).convert("RGBA")
    if h: im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
    elif w: im = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

SIH   = b64(f"{DECK}/image1.png", h=192)          # 96 px tall on the slide, 2x
IMU   = b64(f"{SCR}/imu_clean.png", h=400)        # cropped, de-labelled, palette-unified
LIVE  = b64(f"{SCR}/live_crop.png", h=420)        # the evidence: real app, 9:16 crop

CHIPS = [("Android","image15.png",30),("Kotlin","image11.png",21),("PyTorch","image2.png",24),
         ("LiteRT","image10.png",21),("MapLibre","image16.png",22),("OpenStreetMap","image17.png",24)]
chips = "".join(f'        <img class="chip" alt="{n}" style="height:{h}px" src="{b64(f"{MEDIA}/{f}", h=h*3)}">\n'
                for n, f, h in CHIPS)

# ---------------------------------------------------------------- card 2 art
BLOCKS = ('<svg class="art-svg" viewBox="0 0 112 84" width="112" height="84">'
          + "".join(f'<rect x="{i*28}" y="{(84-hh)/2:.0f}" width="18" height="{hh}" rx="4" '
                    f'fill="#fff" stroke="var(--accent-2)" stroke-width="2.5"/>'
                    for i, hh in enumerate((74, 56, 40, 28)))
          + '</svg>'
          '<svg class="art-svg" viewBox="0 0 26 84" width="26" height="84">'
          '<path d="M2,42 L17,42" stroke="var(--ink)" stroke-width="2.5"/>'
          '<path d="M14,36 L23,42 L14,48 z" fill="var(--ink)"/></svg>')

# ---------------------------------------------------------------- card 3 art
FUSE = f'''<svg class="art-svg" viewBox="0 0 232 176" width="232" height="176">
  <g fill="none" stroke-linecap="round">
    <!-- gauge : speed -->
    <path d="M20,44 A26,26 0 1,1 62,44" stroke="var(--accent-2)" stroke-width="6"/>
    <path d="M41,42 L54,26" stroke="var(--accent-2)" stroke-width="5"/>
    <path d="M22,26 L27,30 M41,15 L41,21 M60,26 L55,30" stroke="var(--accent-2)" stroke-width="3.5"/>
    <!-- compass : heading -->
    <circle cx="116" cy="30" r="26" stroke="var(--ink)" stroke-width="5"/>
    <path d="M116,10 L124,34 L116,29 L108,34 z" fill="var(--ink)" stroke="none"/>
    <!-- satellite : GNSS, the optional one -->
    <rect x="182" y="22" width="17" height="17" rx="3" stroke="var(--faint)" stroke-width="4"/>
    <path d="M165,25 L179,20 L182,29 L168,34 z M202,29 L216,24 L219,33 L205,38 z"
          stroke="var(--faint)" stroke-width="4" stroke-linejoin="round"/>
    <!-- three signals, weighted by how much the filter trusts each one -->
    <path d="M41,72 C41,96 92,86 108,100" stroke="var(--accent-2)" stroke-width="5.5"/>
    <path d="M116,62 L116,100" stroke="var(--ink)" stroke-width="3.5" opacity=".8"/>
    <path d="M195,48 C195,90 140,84 124,100" stroke="var(--faint)" stroke-width="2.5"
          stroke-dasharray="6 5"/>
  </g>
  <path d="M100,91 L112,103 L98,104 z" fill="var(--accent-2)"/>
  <path d="M111,95 L116,105 L121,95 z" fill="var(--ink)" opacity=".8"/>
  <path d="M127,96 L120,103 L129,104 z" fill="var(--faint)"/>
  <!-- the road, and the belief standing on it -->
  <path d="M0,152 C60,140 172,140 232,152 L232,168 C172,156 60,156 0,168 z" fill="#D2D8DE"/>
  <ellipse cx="116" cy="151" rx="52" ry="13" fill="#B9C2CC" opacity=".55"/>
  <path d="M116,108 c-15,0 -27,12 -27,27 c0,18 27,36 27,36 c0,0 27,-18 27,-36
           c0,-15 -12,-27 -27,-27 z" fill="var(--accent)"/>
  <circle cx="116" cy="134" r="11" fill="#fff"/>
</svg>'''

HTML = """<!doctype html>
<!--
  SIH 2026 / PS 26168 - OFFGRID - TECHNICAL APPROACH
  1280 x 720, self-contained. Chrome -> Print -> Save as PDF, "Background graphics" ON.

  THREE ZONES, each deletable:
    .slide-header  0-130    .slide-body  130-660    .slide-footer  660-720
  To reuse .slide-body alone inside an existing PowerPoint template: delete
  .slide-header and .slide-footer and set .slide{height:530px}.

  WHAT TO EDIT
    Team logo ..... <div class="brand">      swap for <img class="brand-img" src="...">
    Deck title .... <h2 class="deck-title">
    Page number ... <span class="page-no">
    Headline ...... <h1 class="headline">
    Hero stat ..... <div class="stat"> / <div class="stat-sub">
    Card labels ... <div class="card-title">   (4 words max)
    Card numbers .. <div class="card-metric">  (one line each)
    GNSS aside .... <div class="gnss-note">    (5 words max)
    Build line .... <p class="step">
    Tech chips .... <img class="chip">
    Palette ....... :root  - two accents, everything else neutral
-->
<html lang="en">
<head>
<meta charset="utf-8">
<title>OFFGRID - Technical approach</title>
<style>
:root{
  --accent:      #1B7F4B;   /* result / evidence  */
  --accent-2:    #C9821F;   /* the learned model  */
  --accent-2-bg: #FDF6EA;
  --ink:   #14181F;
  --muted: #58626F;
  --faint: #9AA3AE;
  --rule:  #DEE3E8;
  --page:  #FFFFFF;
  --chrome: #0070C0;

  --font: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", Arial, sans-serif;
  --title-font: "Times New Roman", Times, serif;
  --brand-font: "Century Gothic", Futura, "Avenir Next", "Segoe UI", sans-serif;
  --fs-headline: 33px;
  --fs-stat:     46px;
  --fs-card:     22px;
  --fs-body:     19px;

  --pad:  48px;
  --gap:  24px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#5A6472}
body{display:flex;align-items:center;justify-content:center;min-height:100vh}
.slide{position:relative;width:1280px;height:720px;overflow:hidden;background:var(--page);
  color:var(--ink);font-family:var(--font);display:flex;flex-direction:column}

/* ---------------- header ---------------- */
.slide-header{height:130px;flex:none;position:relative;display:flex;align-items:center;
  justify-content:center;padding:0 var(--pad)}
.brand{position:absolute;left:var(--pad);top:50%;transform:translateY(-50%);
  font-family:var(--brand-font);font-size:33px;font-weight:700;letter-spacing:-.015em}
.brand-img{position:absolute;left:var(--pad);top:50%;transform:translateY(-50%);height:60px;width:auto}
.deck-title{font-family:var(--title-font);font-size:44px;font-weight:700;letter-spacing:.005em}
.sih{position:absolute;right:var(--pad);top:50%;transform:translateY(-50%);height:96px;width:auto}

/* ---------------- body ---------------- */
.slide-body{height:530px;flex:none;padding:0 var(--pad);display:flex;flex-direction:column}

.top{display:flex;justify-content:space-between;align-items:flex-start;gap:40px}
.headline{font-size:var(--fs-headline);font-weight:700;line-height:1.1;letter-spacing:-.015em;max-width:720px}
.stat-wrap{text-align:right;flex:none}
.stat{font-size:var(--fs-stat);font-weight:700;line-height:.94;letter-spacing:-.02em;color:var(--accent)}
.stat-sub{font-size:var(--fs-body);color:var(--muted);line-height:1.25;margin-top:6px;
  max-width:380px;margin-left:auto}

.gnss-lane{height:34px;position:relative}
.gnss-note{position:absolute;left:0;right:0;top:2px;text-align:center;
  font-size:var(--fs-body);color:var(--faint)}

.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--gap)}
.card{position:relative;border:2px solid var(--rule);border-radius:16px;padding:16px 16px 14px;
  height:316px;display:flex;flex-direction:column;background:#fff}
.card--model{border-color:var(--accent-2);background:var(--accent-2-bg)}
.card--evidence{border-color:var(--ink);border-width:2.5px}
.card-title{font-size:var(--fs-card);font-weight:700;line-height:1.1;letter-spacing:-.006em}
.card-metric{font-size:var(--fs-body);color:var(--muted);line-height:1.28;margin-top:auto}
.badge{position:absolute;top:14px;right:14px;font-size:13px;font-weight:700;letter-spacing:.09em;
  color:var(--accent-2);border:2px solid var(--accent-2);border-radius:6px;padding:0 6px;background:#fff}

.art{flex:1;display:flex;align-items:center;justify-content:center;gap:4px;padding:10px 0 8px;min-height:0}
.art-svg{display:block;flex:none}
.art-img{display:block;max-width:100%;max-height:100%;object-fit:contain}
.cnn-out{font-size:23px;font-weight:700;white-space:nowrap;margin-left:2px}
.phone{border:5px solid #15181D;border-radius:15px;overflow:hidden;background:#15181D;
  height:100%;display:flex}
.phone img{display:block;height:100%;width:auto}

/* the one dashed thing on the slide: GNSS is optional */
.card--fusion::before{content:"";position:absolute;left:50%;top:-30px;height:28px;width:0;
  border-left:2.5px dashed var(--faint);opacity:.75}
.card--fusion::after{content:"";position:absolute;left:50%;top:-6px;transform:translateX(-50%);
  border-top:9px solid var(--faint);border-left:6px solid transparent;
  border-right:6px solid transparent;opacity:.75}

.steps{margin-top:16px;font-size:var(--fs-body);color:var(--faint)}
.steps b{color:var(--muted);font-weight:700}
.steps .n{color:var(--accent);font-weight:700}

.stack{margin-top:auto;padding-top:16px;border-top:1.5px solid var(--rule);
  display:flex;justify-content:center;align-items:center;gap:46px}
.chip{display:block;width:auto;opacity:.9}

/* ---------------- footer ---------------- */
.slide-footer{height:60px;flex:none;position:relative;background:var(--chrome);
  display:flex;align-items:center;justify-content:center}
.footer-text{font-size:16px;color:#fff}
.page-no{position:absolute;right:var(--pad);font-size:16px;font-weight:700;color:#fff}

@page{size:1280px 720px;margin:0}
@media print{
  html,body{background:#fff}
  body{display:block;min-height:0}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
</style>
</head>
<body>

<div class="slide">

  <div class="slide-header">
    <div class="brand">offgrid</div>
    <h2 class="deck-title">TECHNICAL APPROACH</h2>
    <img class="sih" alt="Smart India Hackathon 2026" src="__SIH__">
  </div>

  <div class="slide-body">

    <div class="top">
      <h1 class="headline">GNSS drops. Navigation keeps working.</h1>
      <div class="stat-wrap">
        <div class="stat">1.52&thinsp;%</div>
        <div class="stat-sub">median drift, GNSS withheld&nbsp;600&ndash;850&nbsp;m</div>
      </div>
    </div>

    <div class="gnss-lane"><div class="gnss-note">GNSS only when it is trusted</div></div>

    <div class="cards">

      <div class="card">
        <div class="card-title">Phone sensors</div>
        <div class="art"><img class="art-img" alt="" src="__IMU__"></div>
        <div class="card-metric">Accel + gyro at 419&nbsp;Hz</div>
      </div>

      <div class="card card--model">
        <span class="badge">AI</span>
        <div class="card-title">1&#8209;D CNN</div>
        <div class="art">__BLOCKS__<div class="cnn-out">v&nbsp;&plusmn;&nbsp;&sigma;</div></div>
        <div class="card-metric">57&nbsp;k weights &middot; 240&nbsp;KB</div>
      </div>

      <div class="card card--fusion">
        <div class="card-title">Fusion filter</div>
        <div class="art">__FUSE__</div>
        <div class="card-metric">10&nbsp;Hz, every fix 5&sigma;-gated</div>
      </div>

      <div class="card card--evidence">
        <div class="card-title">Live map</div>
        <div class="art"><div class="phone"><img alt="OFFGRID running on the phone" src="__LIVE__"></div></div>
        <div class="card-metric">17.3&nbsp;m off after 569&nbsp;m</div>
      </div>

    </div>

    <p class="steps">
      <span class="n">1</span> <b>Log 30 rides</b> &nbsp;&rarr;&nbsp;
      <span class="n">2</span> <b>Train the CNN</b> &nbsp;&rarr;&nbsp;
      <span class="n">3</span> <b>Test on a held-out road</b> &nbsp;&rarr;&nbsp;
      <span class="n">4</span> <b>Ship on-device</b>
    </p>

    <div class="stack">
__CHIPS__    </div>

  </div>

  <div class="slide-footer">
    <span class="footer-text">@SIH Idea submission- Template</span>
    <span class="page-no">4</span>
  </div>

</div>

</body>
</html>
"""

out = (HTML.replace("__SIH__", SIH).replace("__IMU__", IMU).replace("__LIVE__", LIVE)
           .replace("__BLOCKS__", BLOCKS).replace("__FUSE__", FUSE).replace("__CHIPS__", chips))
open("../slide_technical_approach.html", "w").write(out)
print("written", len(out) // 1024, "KB")
