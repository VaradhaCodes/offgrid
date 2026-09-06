"""Renders two 1254x1254 square graphics for the PowerPoint deck: the CNN and the fusion filter.
Same palette and line weights as the rest of the slide, so all four cards look like one family."""
import json, subprocess, os

INK="#14181F"; MUTED="#58626F"; FAINT="#9AA3AE"; RULE="#DEE3E8"
AMBER="#C9821F"; AMBER_BG="#FDF6EA"; GREEN="#1B7F4B"
CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

CSS = """html,body{margin:0;background:#fff}
.sq{width:627px;height:627px;background:#fff;display:flex;align-items:center;justify-content:center}
svg{display:block}
text{font-family:"Segoe UI",-apple-system,Helvetica,Arial,sans-serif}"""

# ---------------------------------------------------------------- the CNN
d = json.load(open("imu_window.json"))
W, H, rows = 300, 116, [("acc",0),("acc",1),("acc",2),("gyr",0),("gyr",1),("gyr",2)]
rh = H/6; traces=[]
for i,(k,ch) in enumerate(rows):
    v=[r[ch] for r in d[k]][::7]
    lo,hi=min(v),max(v); rng=(hi-lo) or 1
    pts=" ".join(f"{(j/(len(v)-1))*W:.1f},{i*rh+rh-3-(val-lo)/rng*(rh-6):.1f}" for j,val in enumerate(v))
    traces.append(f'<polyline points="{pts}" fill="none" stroke="{INK if k=="acc" else FAINT}" '
                  f'stroke-width="3" stroke-linejoin="round"/>')

blocks="".join(f'<rect x="{113+i*48}" y="{254-hh/2:.0f}" width="30" height="{hh}" rx="7" '
               f'fill="#fff" stroke="{AMBER}" stroke-width="5.5"/>' for i,hh in enumerate((96,74,56,40)))

CNN = f'''<svg viewBox="0 0 400 400" width="400" height="400">
  <rect x="44" y="36" width="312" height="128" rx="16" fill="#F4F6F8"/>
  <g transform="translate(50,42)">{"".join(traces)}</g>
  <path d="M200,176 L200,196" stroke="{INK}" stroke-width="5.5"/>
  <path d="M187,192 L200,212 L213,192 z" fill="{INK}"/>
  {blocks}
  <path d="M200,312 L200,330" stroke="{INK}" stroke-width="5.5"/>
  <path d="M187,326 L200,346 L213,326 z" fill="{INK}"/>
  <text x="200" y="394" text-anchor="middle" font-size="58" font-weight="700" fill="{INK}">v &#177; &#963;</text>
</svg>'''

# ---------------------------------------------------------------- the fusion filter
FUSE = f'''<svg viewBox="0 0 400 400" width="400" height="400">
  <g fill="none" stroke-linecap="round">
    <path d="M42,96 A44,44 0 1,1 114,96" stroke="{AMBER}" stroke-width="10"/>
    <path d="M78,92 L100,64" stroke="{AMBER}" stroke-width="9"/>
    <path d="M45,66 L54,73 M78,45 L78,56 M111,66 L102,73" stroke="{AMBER}" stroke-width="6"/>
    <circle cx="200" cy="76" r="44" stroke="{INK}" stroke-width="9"/>
    <path d="M200,42 L214,84 L200,75 L186,84 z" fill="{INK}" stroke="none"/>
    <rect x="310" y="62" width="29" height="29" rx="5" stroke="{FAINT}" stroke-width="7"/>
    <path d="M281,68 L305,59 L310,74 L286,83 z M344,74 L368,65 L373,80 L349,89 z"
          stroke="{FAINT}" stroke-width="7" stroke-linejoin="round"/>
  </g>
  <g fill="none" stroke-linecap="round">
    <path d="M78,144 C78,196 168,180 190,208" stroke="{AMBER}" stroke-width="13"/>
    <path d="M200,128 L200,208" stroke="{INK}" stroke-width="8" opacity=".85"/>
    <path d="M325,104 C325,186 232,176 210,208" stroke="{FAINT}" stroke-width="5" stroke-dasharray="13 11"/>
  </g>
  <path d="M176,192 L198,214 L172,216 z" fill="{AMBER}"/>
  <path d="M189,196 L200,220 L211,196 z" fill="{INK}" opacity=".85"/>
  <path d="M228,196 L206,214 L232,216 z" fill="{FAINT}"/>
  <path d="M0,318 C104,296 296,296 400,318 L400,350 C296,328 104,328 0,350 z" fill="{RULE}"/>
  <ellipse cx="200" cy="316" rx="104" ry="26" fill="#AFB9C4" opacity=".5"/>
  <path d="M200,224 c-30,0 -54,24 -54,54 c0,36 54,72 54,72 c0,0 54,-36 54,-72
           c0,-30 -24,-54 -54,-54 z" fill="{GREEN}"/>
  <circle cx="200" cy="276" r="22" fill="#fff"/>
</svg>'''

for name, svg in (("sq_cnn", CNN), ("sq_fusion", FUSE)):
    open(f"{name}.html","w").write(
        f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><div class="sq">{svg}</div>')
    subprocess.run([CHROME,"--headless=new","--disable-gpu","--hide-scrollbars",
                    "--force-device-scale-factor=2","--window-size=627,627",
                    "--virtual-time-budget=3000",
                    f"--screenshot={os.getcwd()}/img/{name}.png",
                    f"file://{os.getcwd()}/{name}.html"],
                   capture_output=True)
    print(name, "ok")
