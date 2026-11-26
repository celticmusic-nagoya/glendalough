import {readFile,writeFile} from 'node:fs/promises';
const result=[];
for(const profile of ['mobile','desktop']){
  const l=JSON.parse(await readFile('audit/lighthouse-'+profile+'.json','utf8'));
  if(l.runtimeError)throw Error(JSON.stringify(l.runtimeError));
  const scores=Object.fromEntries(Object.entries(l.categories).map(([k,v])=>[k,Math.round(v.score*100)]));
  const metrics=Object.fromEntries(['first-contentful-paint','largest-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index'].map(k=>[k,l.audits[k]?.numericValue]));
  result.push({profile,version:l.lighthouseVersion,url:l.finalDisplayedUrl,scores,metrics,failedAudits:Object.values(l.audits).filter(a=>typeof a.score==='number'&&a.score<1).map(a=>({id:a.id,title:a.title,score:a.score,displayValue:a.displayValue}))});
}
await writeFile('audit/lighthouse-summary.json',JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
