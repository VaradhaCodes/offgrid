import fs from 'node:fs';
import path from 'node:path';
const out=path.dirname(new URL(import.meta.url).pathname);
const font=n=>fs.readFileSync(path.join(out,'../src/fonts',n)).toString('base64');
const today=[
 ['Runs on the phone','240 KB model with 10 Hz position updates.'],
 ['Corridor replay evidence','10/10 held-out route-2 rides below 10% drift.'],
 ['Works offline','Local inference and bundled road maps.']
];
const future=[
 ['Broader vehicle coverage','Train across more vehicles and phone models.'],
 ['Longer GPS outages','Refine calibration and road constraints.']
];
const benefits=[
 ['Navigation continuity','Position tracking through GPS blackouts.'],
 ['Delivery reliability','Fewer missed turns and avoidable delays.'],
 ['Emergency response','Position awareness where GPS is blocked.'],
 ['Lower adoption cost','Existing phones, without vehicle wiring.'],
 ['More efficient trips','Fewer detours could cut fuel use and emissions.']
];
const list=a=>`<ul>${a.map(([label,body])=>`<li><strong>${label}</strong><span>${body}</span></li>`).join('')}</ul>`;
const css=`@font-face{font-family:Barlow;src:url(data:font/ttf;base64,${font('barlow_regular.ttf')}) format('truetype');font-weight:400}@font-face{font-family:Barlow;src:url(data:font/woff2;base64,${font('barlow_600.woff2')}) format('woff2');font-weight:600}*{box-sizing:border-box}html,body{margin:0;background:white;font-family:Barlow,Arial,sans-serif;color:#202528}body{overflow:hidden}.slide{position:absolute;width:1600px;height:660px;transform-origin:top left;background:white}.content{position:absolute;inset:20px;display:grid;grid-template-columns:1fr 1fr;gap:28px}.panel{padding:27px 32px;border:1.6px solid #b8c2c3;border-radius:5px;min-height:0;min-width:0}.impact{background:#f7faf9;border-color:#579680}h2{font-size:37px;line-height:1.12;font-weight:600;letter-spacing:-.3px;margin:0 0 23px}.impact h2{color:#286b55}h3{font-size:22px;line-height:1.2;color:#58675f;font-weight:600;margin:0 0 16px}ul{margin:0;padding:0 0 0 23px;display:flex;flex-direction:column;gap:17px}li{padding-left:5px;color:#4d595c;line-height:1.24}li strong{display:block;font-weight:600;font-size:28px;color:#2f3d36;margin-bottom:4px}li span{display:block;font-size:26px}li::marker{color:#627b6c;font-size:17px}.future{border-top:1px solid #d1dad6;margin-top:20px;padding-top:16px}.future h3{margin-bottom:12px}.future ul{gap:15px}.impact li strong{color:#2d5f4d}.impact ul{height:449px;justify-content:space-between;gap:0}.impact h3{margin-bottom:19px}.impact li::marker{color:#347961}@media print{@page{size:1600px 660px;margin:0}.slide{position:relative;transform:none!important}body{overflow:visible}}`;
const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Feasibility and impact — wide PPT content</title><style>${css}</style></head><body><main class="slide" aria-label="Feasibility and viability, impact and benefits"><div class="content"><section class="panel feasibility"><h2>Feasibility and viability</h2>${list(today)}<div class="future"><h3>Next steps</h3>${list(future)}</div></section><section class="panel impact"><h2>Impact and benefits</h2><h3>Potential benefits</h3>${list(benefits)}</section></div></main><script>function fit(){const s=Math.min(innerWidth/1600,innerHeight/660),e=document.querySelector('.slide');e.style.transform='scale('+s+')';e.style.left=(innerWidth-1600*s)/2+'px';e.style.top=(innerHeight-660*s)/2+'px'}addEventListener('resize',fit);fit();</script></body></html>`;
fs.writeFileSync(path.join(out,'03_feasibility_impact.html'),html);
fs.writeFileSync(path.join(out,'03_feasibility_impact_content.md'),`## Feasibility and viability\n\n${today.map(([a,b])=>`- **${a}:** ${b}`).join('\n')}\n\n### Next steps\n\n${future.map(([a,b])=>`- **${a}:** ${b}`).join('\n')}\n\n## Impact and benefits\n\n### Potential benefits\n\n${benefits.map(([a,b])=>`- **${a}:** ${b}`).join('\n')}\n`);
console.log('Built wide 1600 × 660 PPT content.');
