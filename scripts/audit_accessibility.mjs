import { chromium } from 'playwright';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
const require=createRequire(import.meta.url);
const axePath=require.resolve('axe-core/axe.min.js');
const base=process.env.AUDIT_URL || 'http://127.0.0.1:8765/glendalough/';
const pages=['','en/','events/christmas-2026-24.html','events/christmas-2026-25.html'];
await mkdir('audit',{recursive:true});
const browser=await chromium.launch();
const summary=[];
try {
  for(const width of [390,1440]){
    for(const path of pages){
      const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
      const response=await page.goto(new URL(path,base).href,{waitUntil:'domcontentloaded'});
      if(!response?.ok()) throw Error('Page unavailable: '+path);
      await page.evaluate(async()=>{await document.fonts.ready;for(const i of document.images)i.loading='eager';await Promise.allSettled([...document.images].map(i=>i.decode()));});
      await page.addScriptTag({path:axePath});
      const key=(path||'home').replace(/[^a-z0-9-]/gi,'-')+'-'+width;
      const scan=async state=>{
        const result=await page.evaluate(async()=>window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
        const data={key,state,url:page.url(),version:result.testEngine.version,passes:result.passes.length,incomplete:result.incomplete.map(r=>({id:r.id,description:r.description,nodes:r.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),violations:result.violations.map(r=>({id:r.id,impact:r.impact,help:r.help,nodes:r.nodes.map(n=>({target:n.target,html:n.html,summary:n.failureSummary}))}))};
        summary.push({key,state,passes:data.passes,violations:data.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length})),incomplete:data.incomplete.map(v=>({id:v.id,nodes:v.nodes.length}))});
        await writeFile('audit/axe-'+key+'-'+state+'.json',JSON.stringify(data,null,2));
      };
      await scan('default');
      if(!path && width===390){
        await page.locator('#menuButton').click();
        await scan('menu-open');
        await page.keyboard.press('Escape');
      }
      await page.close();
    }
  }
} finally {await browser.close();}
await writeFile('audit/axe-summary.json',JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
