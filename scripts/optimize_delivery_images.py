"""Create or verify delivery-only WebP variants. Never modify source photographs."""
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageChops, ImageStat, ImageDraw, ImageCms

SOURCES = {
    "image.jpg": ("ensemble-stone", (640, 1280, 1920)),
    "music-breton.jpg": ("music-breton", (640, 1280)),
    "music-scottish.jpg": ("music-scottish", (640, 1280)),
    "music-world.jpg": ("music-world", (640, 1280)),
}
REPORT = Path("delivery-image-report.json")
OUT = Path("images/web")
VERIFY = "--verify" in sys.argv
COMPARISONS = "--comparisons" in sys.argv
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(src):
    with Image.open(src) as raw:
        im=ImageOps.exif_transpose(raw)
        icc=raw.info.get("icc_profile")
        if im.mode in ("RGBA","LA"):
            assert im.getchannel("A").getextrema()==(255,255), f"Nonopaque source {src}"
        if icc:
            im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile("sRGB"),outputMode="RGB")
        else:
            im=im.convert("RGB")
        return im
def psnr(a,b):
    rms=ImageStat.Stat(ImageChops.difference(a,b)).rms
    mse=sum(v*v for v in rms)/len(rms)
    return 100.0 if mse==0 else 10*math.log10(255*255/mse)
def measure(dst,target):
    with Image.open(dst) as raw:
        assert raw.format=="WEBP" and raw.size==target.size,dst
        b=raw.convert("RGB")
    return round(psnr(target,b),3),b
def main():
    OUT.mkdir(exist_ok=True)
    if VERIFY:
        old=json.loads(REPORT.read_text())
        assert len(old)==9
        old={r["output"]:r for r in old}
    else:
        assert not REPORT.exists(),"Report exists; use --verify"
    rows=[]
    for name,(stem,widths) in SOURCES.items():
        src=Path("images")/name
        original=prepare(src)
        digest=sha(src)
        for width in widths:
            assert original.width>=width,(name,original.size,width)
            target=original.resize((width,round(original.height*width/original.width)),Image.Resampling.LANCZOS)
            dst=OUT/f"{stem}-{width}.webp"
            if VERIFY:
                quality=old[str(dst)]["quality"]
                score,b=measure(dst,target)
            else:
                assert not dst.exists(),dst
                for quality in (87,90,93,96):
                    target.save(dst,"WEBP",quality=quality,method=6)
                    score,b=measure(dst,target)
                    if score>=32: break
            assert score>=32,(dst,score)
            row=dict(source=str(src),source_sha256=digest,source_bytes=src.stat().st_size,source_size=list(original.size),output=str(dst),size=list(target.size),bytes=dst.stat().st_size,sha256=sha(dst),quality=quality,psnr_db=score)
            if VERIFY: assert row==old[str(dst)],dst
            rows.append(row)
            if COMPARISONS and width==1280:
                a=target.copy(); bb=b.copy()
                a.thumbnail((800,800),Image.Resampling.LANCZOS);bb.thumbnail((800,800),Image.Resampling.LANCZOS)
                w,h=a.size
                sheet=Image.new("RGB",(w*2,h+38),"#161b16")
                sheet.paste(a,(0,38));sheet.paste(bb,(w,38))
                d=ImageDraw.Draw(sheet);d.text((10,12),"Original resized",fill="white");d.text((w+10,12),f"WebP | PSNR {score:.2f} dB",fill="white")
                path=Path("screenshots/optimization")/f"{stem}.jpg"
                path.parent.mkdir(parents=True,exist_ok=True);sheet.save(path,quality=95)
        assert sha(src)==digest,src
    largest=[x for x in rows if x["size"][0]==max(SOURCES[Path(x["source"]).name][1])]
    original_bytes=sum(x["source_bytes"] for x in largest)
    delivery_bytes=sum(x["bytes"] for x in largest)
    assert delivery_bytes <= original_bytes*.20,(delivery_bytes,original_bytes)
    if not VERIFY: REPORT.write_text(json.dumps(rows,indent=2)+"\n")
    print(f"Delivery WebP: {len(rows)} validated; largest variants {original_bytes} -> {delivery_bytes} bytes; min PSNR {min(x['psnr_db'] for x in rows):.2f} dB")
if __name__=="__main__": main()
