import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const out=path.dirname(new URL(import.meta.url).pathname);
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--allow-file-access-from-files']});
for(const name of ['01_architecture','02_working_prototype']) {
 const page=await browser.newPage({viewport:{width:1600,height:name==='01_architecture'?660:900},deviceScaleFactor:2.4});
 await page.goto('file://'+path.join(out,name+'.html'));
 await page.evaluate(()=>document.fonts.ready);
 await page.locator('img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
 await page.screenshot({path:path.join(out,name+'.png')});
 const checks=await page.evaluate(()=>({fonts:document.fonts.check('23px Barlow'),overflow:[...document.querySelectorAll('.node,.tile,.abs')].filter(e=>e.scrollWidth>e.clientWidth+2||e.scrollHeight>e.clientHeight+2).map(e=>({id:e.id,text:e.innerText.slice(0,80),w:[e.clientWidth,e.scrollWidth],h:[e.clientHeight,e.scrollHeight]})),outside:[...document.querySelectorAll('.slide *')].filter(e=>!(e instanceof SVGElement)).filter(e=>{let b=e.getBoundingClientRect();return b.bottom>innerHeight+.5||b.right>1600.5||b.left<0||b.top<0}).map(e=>({text:e.innerText?.slice(0,60),rect:e.getBoundingClientRect().toJSON()})),images:[...document.images].map(i=>({loaded:i.complete&&i.naturalWidth>0,width:i.naturalWidth}))}));
 console.log(name,JSON.stringify(checks));
 await page.setViewportSize({width:1280,height:name==='01_architecture'?528:720});
 await page.screenshot({path:path.join(out,'_'+name+'_review.png'),scale:'css'});
 await page.close();
}
await browser.close();
