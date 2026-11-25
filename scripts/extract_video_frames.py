"""Review authorized official video footage. Never publish or bypass access controls."""
import hashlib, json, math, os, subprocess, tempfile
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
report={"ffmpeg":version(["ffmpeg","-version"]),"ffprobe":version(["ffprobe","-version"]),"yt_dlp":version(["yt-dlp","--version"]),"sources":[]}
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    fixture=tmp/"smoke.mp4"
    run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","testsrc2=size=640x360:rate=25","-t","3","-c:v","mpeg4",str(fixture)])
    frames,step,duration=extract(fixture,tmp/"smoke-frames")
    assert len(frames)==3
    report["smoke_test"]={"status":"PASS","frames":len(frames),"synthetic_test_only":True}
    # Restrict scope to the existing authorized official video links.
    for key,url in SOURCES:
        item={"id":key,"url":url,"location_verified":False}
        try:
            folder=tmp/key;folder.mkdir()
            run(["yt-dlp","--ignore-config","--no-playlist","--no-progress","--no-warnings","--socket-timeout","12","--retries","0","--fragment-retries","0","--max-filesize","80M","--match-filters","duration <= 300","-f","best[height<=1080]/bestvideo[height<=1080]","-o",str(folder/"source.%(ext)s"),url],65)
            files=[p for p in folder.glob("source.*") if p.suffix not in {".part",".ytdl",".json"}]
            assert len(files)==1,"Video unavailable or exceeds acquisition limits"
            source=files[0]
            assert source.stat().st_size<=80*1024*1024
            dest=OUT/key
            frames,step,duration=extract(source,dest)
            item.update(status="FRAMES_READY_FOR_REVIEW",source_sha256=sha(source),duration=duration,interval_seconds=step,frames=report_frames(frames,step,dest))
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,AssertionError,ValueError,OSError) as e:
            item.update(status="ACQUISITION_OR_EXTRACTION_BLOCKED",error=(getattr(e,"stderr",None) or str(e))[-1500:])
        report["sources"].append(item)
        (OUT/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({"smoke":report["smoke_test"],"sources":[{"id":s["id"],"status":s["status"]} for s in report["sources"]]},ensure_ascii=False))
