"""Review authorized official video footage. Never publish or bypass access controls."""
import hashlib, json, math, os, subprocess, tempfile, argparse, re
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFilter, ImageStat

OUT=Path("video-review")
OUT.mkdir(exist_ok=True)
SOURCES=[
 ("street-merry-blacksmith","https://www.youtube.com/watch?v=9d2jLKTgQtk"),
 ("night-session","https://www.youtube.com/watch?v=-btG-2M4QXQ"),
 ("indoor-session","https://www.youtube.com/watch?v=L26X01zSNgo"),
 ("instagram-01","https://www.instagram.com/reel/Dbzb1vHzqWn/"),
 ("instagram-02","https://www.instagram.com/reel/DYT5gg_TQML/"),
]
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""): h.update(chunk)
    return h.hexdigest()
def run(args,timeout=90):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout)
def version(cmd):
    return run(cmd,15).stdout.splitlines()[0]
def extract(path,folder,limit=90):
    folder.mkdir(parents=True,exist_ok=True)
    meta=json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]).stdout)
    duration=float(meta["format"]["duration"])
    assert math.isfinite(duration) and duration>0
    step=max(1,math.ceil(duration/limit))
    run(["ffmpeg","-nostdin","-v","error","-i",str(path),"-map","0:v:0","-vf",f"fps=1/{step}:start_time=0,scale=1280:1280:force_original_aspect_ratio=decrease","-frames:v",str(limit),"-q:v","2",str(folder/"frame-%04d.jpg")],120)
    frames=sorted(folder.glob("frame-*.jpg"))
    assert frames,"No extracted frames"
    return frames,step,duration
def report_frames(frames,step,folder):
    rows=[]; accepted=[]; prev=None
    for i,p in enumerate(frames):
        with Image.open(p) as img:
            im=img.convert("RGB")
        small=ImageOps.grayscale(im).resize((128,128))
        sharp=ImageStat.Stat(small.filter(ImageFilter.FIND_EDGES)).stddev[0]
        lum=ImageStat.Stat(small).mean[0]
        # simple average hash: reject near identical frames, retain review candidates
        tiny=small.resize((8,8)); pix=list(tiny.getdata()); avg=sum(pix)/64
        bits=sum((x>avg)<<j for j,x in enumerate(pix))
        duplicate=prev is not None and (prev^bits).bit_count()<=3
        prev=bits
        rec={"file":p.name,"sample_index":i,"nominal_second":i*step,"sha256":sha(p),"width":im.width,"height":im.height,"edge_stddev":round(sharp,2),"mean_luma":round(lum,2),"near_previous":duplicate}
        rows.append(rec)
        if not duplicate: accepted.append((p,rec))
    # Sharpness is a sorting hint, not a visual or privacy verdict.
    selected=sorted(accepted,key=lambda item:item[1]["edge_stddev"],reverse=True)[:24]
    selected.sort(key=lambda item:item[1]["sample_index"])
    sheet=Image.new("RGB",(4*320,max(1,math.ceil(len(selected)/4))*224),"#101510")
    draw=ImageDraw.Draw(sheet)
    for j,(p,rec) in enumerate(selected):
        x,y=j%4*320,j//4*224
        with Image.open(p) as img:
            thumb=ImageOps.contain(img.convert("RGB"),(312,194))
        sheet.paste(thumb,(x+(320-thumb.width)//2,y+(194-thumb.height)//2))
        draw.text((x+6,y+199),f'{p.name} ~{rec["nominal_second"]}s',fill="white")
    sheet.save(folder/"contact-sheet.jpg",quality=88)
    return rows

# Official Instagram Login API; never log token, signed CDN URLs or raw errors.
def graph(path, params, token):
    url="https://graph.instagram.com/v27.0/"+path+"?"+urlencode(params)
    req=Request(url,headers={"Authorization":"Bearer "+token})
    with urlopen(req,timeout=20) as response:
        return json.load(response)
def cdn_allowed(url):
    u=urlsplit(url)
    return u.scheme=="https" and u.port in (None,443) and not u.username and not u.password and any(u.hostname==d or (u.hostname or "").endswith("."+d) for d in ("cdninstagram.com","fbcdn.net"))
class SafeCDNRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not cdn_allowed(newurl): raise ValueError("Unexpected CDN redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def download_media(url,dest):
    if not cdn_allowed(url): raise ValueError("Unexpected media host")
    opener=build_opener(SafeCDNRedirect())
    with opener.open(Request(url),timeout=25) as response,dest.open("wb") as fp:
        if not cdn_allowed(response.geturl()): raise ValueError("Unexpected media host")
        n=0
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            n+=len(chunk)
            if n>80*1024*1024: raise ValueError("Video exceeds 80 MiB")
            fp.write(chunk)
    if not n: raise ValueError("Empty media")
def process(source,key,metadata,report):
    dest=OUT/key
    frames,step,duration=extract(source,dest)
    return dict(metadata,status="FRAMES_READY_FOR_REVIEW",source_sha256=sha(source),duration=duration,interval_seconds=step,frames=report_frames(frames,step,dest))
def safe_error(e):
    # Do not leak credentials, signed media URLs, local paths or raw API responses.
    if isinstance(e,HTTPError): return "HTTP "+str(e.code)
    if isinstance(e,subprocess.CalledProcessError): return "FFmpeg/FFprobe failed: exit "+str(e.returncode)
    return type(e).__name__
def instagram(tmp,report):
    token=os.environ.get("INSTAGRAM_ACCESS_TOKEN","").strip()
    if not token:
        report["sources"].append({"platform":"instagram","status":"AUTH_NOT_CONFIGURED"})
        return
    try:
        profile=graph("me",{"fields":"user_id,username"},token)
        if profile.get("username","").lower()!="glendalough_nagoya":
            report["sources"].append({"platform":"instagram","status":"ACCOUNT_MISMATCH"})
            return
        uid=str(profile["user_id"])
        if not re.fullmatch(r"[0-9]+",uid): raise ValueError("Invalid account id")
        data=graph(uid+"/media",{"fields":"id,media_type,media_url,permalink,timestamp","limit":25},token)
        videos=[m for m in data.get("data",[]) if m.get("media_type")=="VIDEO" and m.get("media_url") and re.fullmatch(r"[0-9]+",str(m.get("id","")))]
        targets={"Dbzb1vHzqWn","DYT5gg_TQML"}
        videos.sort(key=lambda m:not any(x in m.get("permalink","") for x in targets))
        report["instagram_video_count_first_page"]=len(videos)
        for m in videos[:5]:
            key="instagram-"+str(m["id"])
            item={"platform":"instagram","id":key,"url":m.get("permalink"),"timestamp":m.get("timestamp"),"source_type":"official_authenticated_media","location_verified":False}
            try:
                source=tmp/(key+".mp4")
                download_media(m["media_url"],source)
                item=process(source,key,item,report)
            except (HTTPError,URLError,ValueError,OSError,AssertionError,subprocess.SubprocessError) as e:
                item.update(status="MEDIA_BLOCKED",error=safe_error(e))
            report["sources"].append(item)
        if not videos: report["sources"].append({"platform":"instagram","status":"NO_VIDEO_ON_FIRST_PAGE"})
    except (HTTPError,URLError,ValueError,KeyError,OSError) as e:
        report["sources"].append({"platform":"instagram","status":"API_BLOCKED","error":safe_error(e)})
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--local",type=Path,nargs="*",default=[])
    parser.add_argument("--instagram",action="store_true")
    args=parser.parse_args()
    report={"ffmpeg":version(["ffmpeg","-version"]),"ffprobe":version(["ffprobe","-version"]),"sources":[]}
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        fixture=tmp/"smoke.mp4"
        run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","testsrc2=size=640x360:rate=25","-t","3","-c:v","mpeg4",str(fixture)])
        frames,step,duration=extract(fixture,tmp/"smoke-frames")
        assert len(frames)==3
        report["smoke_test"]={"status":"PASS","frames":len(frames),"synthetic_test_only":True}
        for i,source in enumerate(args.local):
            item={"platform":"owner_export","id":f"local-{i+1:02d}","source_type":"owner_supplied_video","location_verified":False}
            try:
                if not source.is_file(): raise ValueError("Missing input")
                item=process(source,item["id"],item,report)
            except (ValueError,OSError,AssertionError,subprocess.SubprocessError) as e:
                item.update(status="EXTRACTION_BLOCKED",error=safe_error(e))
            report["sources"].append(item)
        if args.instagram: instagram(tmp,report)
        report["owner_export_routes"]={"youtube":"YouTube Studio or Google Takeout","tiktok":"Save own video in TikTok app","status":"INPUT_REQUIRED"}
    (OUT/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({"smoke":report["smoke_test"],"sources":[{"id":s.get("id",s.get("platform")),"status":s["status"],"error":s.get("error")} for s in report["sources"]]},ensure_ascii=False))
if __name__=="__main__":
    main()
