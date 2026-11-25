// Method C: capture only normally playable official posts, without bypassing restrictions.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const OUT=path.resolve('browser-capture');
const sources=[
 ['youtube-street','https://www.youtube.com/watch?v=9d2jLKTgQtk'],
 ['youtube-night','https://www.youtube.com/watch?v=-btG-2M4QXQ'],
 ['youtube-indoor','https://www.youtube.com/watch?v=L26X01zSNgo'],
 ['instagram-01','https://www.instagram.com/reel/Dbzb1vHzqWn/'],
 ['instagram-02','https://www.instagram.com/reel/DYT5gg_TQML/'],
 ['tiktok-01','https://www.tiktok.com/@glendalough.jp/video/7685398773727497493']
];
fs.mkdirSync(OUT,{recursive:true});
const report={method:'visible_browser_screenshot',head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),smoke:null,sources:[]};
function save(){fs.writeFileSync(path.join(OUT,'manifest.json'),JSON.stringify(report,null,2))}
const readVideo=v=>v.evaluate(e=>({time:e.currentTime,paused:e.paused,ready:e.readyState,width:e.videoWidth,height:e.videoHeight,ended:e.ended}));
async function capture(page,id,url,fixture=false){
 const result={id,url:fixture?'local-test-fixture':url,status:'NOT_RUN',frames:[],location_verified:false};
 let phase='navigation';
 const restricted=/sign in to confirm|confirm you.re not a bot|verify (that )?you are human|captcha|video unavailable|log in to (continue|watch)|login required|age.restricted|ログインして.*確認|ロボットではない|この動画は再生できません|ログインが必要|動画を再生できません|not available|access denied|unusual traffic/i;
 try{
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});
  result.http=response?.status()||null;
  if(result.http>=400){result.status='HTTP_BLOCKED';return result}
  await page.waitForTimeout(3000);
  phase='page-inspection';
  // Ordinary privacy-choice buttons only. Never interact with login or challenge prompts.
  const consent=page.getByRole('button',{name:/^(Reject all|すべて拒否|すべて拒否する)$/i}).first();
  if(await consent.isVisible().catch(()=>false)){await consent.click({timeout:5000});await page.waitForTimeout(2500)}
  const gate=async()=>{
   for(const frame of page.frames()){
    const body=await frame.locator('body').innerText({timeout:1500}).catch(()=>'');
    if(restricted.test(body)||/\/(login|challenge|checkpoint)(\/|\?|$)/i.test(new URL(frame.url(),'https://example.invalid').pathname))return true;
   }
   return false
  };
  if(await gate()){result.status='ACCESS_OR_PLAYBACK_RESTRICTED';return result}
  // The prior evidence shows an optional registration overlay (Instagram)
  // and an explicit Skip control (TikTok). Use only these normal UI controls.
  if(!fixture&&id==='instagram-01'){
   const modal=page.getByRole('dialog').filter({hasText:/投稿を見逃さず|登録して|Sign up/i}).first();
   const close=modal.getByRole('button',{name:/^(Close|閉じる|閉じるボタン)$/i}).first();
   if(await close.isVisible().catch(()=>false)){await close.click({timeout:5000});result.optional_prompt='dismissed'}
   else result.optional_prompt='no_accessible_close_control';
  }
  if(!fixture&&id==='tiktok-01'){
   const skip=page.getByText('スキップ',{exact:true}).first();
   if(await skip.isVisible().catch(()=>false)){await skip.click({timeout:5000});result.optional_prompt='skipped'}
   else result.optional_prompt='no_skip_control';
  }
  if(!fixture)await page.waitForTimeout(2000);
  phase='video-discovery';
  await page.waitForTimeout(6000);
  if(await gate()){result.status='ACCESS_OR_PLAYBACK_RESTRICTED';return result}
  if(!fixture){
   const text=await page.locator('body').innerText({timeout:3000}).catch(()=>null);
   if(!text||/この動画の再生にエラー|動画を読み込めません|動画の再生に失敗|error playing this video|could not play|couldn.t play/i.test(text)){result.status='PLAYBACK_ERROR';return result}
  }
  const videos=[];
  for(const frame of page.frames())for(const v of await frame.locator('video:visible').all())videos.push(v);
  result.visible_video_count=videos.length;
  if(!videos.length){result.status='NO_VISIBLE_VIDEO';return result}
  // Choose the largest visible video in normal page layout, not hidden media.
  let video=null,area=0;
  for(const v of videos){
   const box=await v.boundingBox();
   if(box&&box.width*box.height>area){video=v;area=box.width*box.height}
  }
  if(!fixture&&videos.length!==1){result.status='AMBIGUOUS_VIDEO_TARGET';return result}
  if(!video||area<40000){result.status='VIDEO_TOO_SMALL';return result}
  phase='playback';
  await video.scrollIntoViewIfNeeded({timeout:5000});
  const initial=await readVideo(video);
  if(initial.paused){
   // A normal user-visible click only. No autoplay override, hidden player or challenge interaction.
   const play=page.getByRole('button',{name:/^play$|^再生$/i}).first();
   if(await play.isVisible().catch(()=>false))await play.click({timeout:5000});
   else await video.click({timeout:5000});
  }
  await page.mouse.move(2,2);
  await page.waitForTimeout(2500);
  const before=await readVideo(video);
  await page.waitForTimeout(1800);
  const after=await readVideo(video);
  if(after.ready<2||after.width<160||after.paused||after.time<=before.time+0.25){
   result.status='PLAYBACK_NOT_CONFIRMED';result.playback=after;return result
  }
  result.playback=after;
  phase='capture';
  const dir=path.join(OUT,id);fs.mkdirSync(dir,{recursive:true});
  let last=-1;
  for(let i=0;i<18;i++){
   if(await gate()){result.status='ACCESS_OR_PLAYBACK_RESTRICTED';for(const frame of result.frames)fs.rmSync(path.join(OUT,frame.file),{force:true});result.frames=[];return result}
   const state=await readVideo(video);
   if(state.ended||state.paused)break;
   if(state.ready>=2&&state.time>last+0.6){
    // Screenshot the actual video element, preserving the page's visible rendered pixels.
    const name='frame-'+String(result.frames.length+1).padStart(3,'0')+'.png';
    await video.screenshot({path:path.join(dir,name),timeout:5000});
    result.frames.push({file:id+'/'+name,second:state.time});
    last=state.time;
   }
   await page.waitForTimeout(1500);
  }
  result.status=result.frames.length>=10?'CAPTURED_REVIEW_REQUIRED':result.frames.length?'PARTIAL_CAPTURE':'NO_CAPTURE';
 }catch(e){result.status='BROWSER_ERROR';result.error=String(e.name||'Error')}
 finally{
  result.phase=phase;
  if(!fixture&&!result.frames.length){
   result.page_title=await page.title().catch(()=>null);
   try{const u=new URL(page.url());result.final_host=u.hostname;result.final_path=u.pathname}catch{}
   result.frame_count=page.frames().length;
   const dir=path.join(OUT,'diagnostics');fs.mkdirSync(dir,{recursive:true});
   await page.screenshot({path:path.join(dir,id+'.png'),timeout:5000}).catch(()=>{});
  }
 }
 return result
}
(async()=>{
 const browser=await chromium.launch({headless:false});
 try{
  const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,locale:'ja-JP'});
  const fixture=await context.newPage();
  report.smoke=await capture(fixture,'smoke','http://127.0.0.1:8766/',true);
  await fixture.close();save();
  if(report.smoke.frames.length<10)throw Error('Local playback screenshot smoke failed');
  // One diagnostic attempt per platform after the first failed batch.
  for(const [id,url] of sources.filter(([id])=>['instagram-01','tiktok-01'].includes(id))){
   // Fresh browser context per source; no stored credentials or anti-detection measures.
   const ctx=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,locale:'ja-JP'});
   const page=await ctx.newPage();
   report.sources.push(await capture(page,id,url));
   await ctx.close();save();
  }
  console.log(JSON.stringify(report.sources.map(s=>({id:s.id,status:s.status,frames:s.frames.length}))));
 }finally{await browser.close()}
})().catch(e=>{save();console.error(e);process.exitCode=1});
