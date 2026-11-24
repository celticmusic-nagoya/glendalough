from pathlib import Path
from PIL import Image, ImageOps
import json, hashlib
root=Path("images")
out=root/"web"
out.mkdir(exist_ok=True)
report=[]
for name in ["hero2.jpg","hero.jpg","music-jigs.jpg","music-airs.jpg","music-reels.jpg"]:
    src=root/name
    with Image.open(src) as raw:
        im=ImageOps.exif_transpose(raw).convert("RGB")
        for width in (640,1280,1920):
            target=im.copy()
            target.thumbnail((width, width*2),Image.Resampling.LANCZOS)
            dst=out/f"{src.stem}-{width}.webp"
            quality=85
            if name=="hero.jpg":
                target.thumbnail((960, 960),Image.Resampling.LANCZOS)
            for quality in (85,82,79,76,73,70):
                target.save(dst,"WEBP",quality=quality,method=6)
                if dst.stat().st_size<=src.stat().st_size*.2:
                    break
            with Image.open(dst) as check:
                assert check.size==target.size
                check.load()
            report.append(dict(source=name,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),source_bytes=src.stat().st_size,output=str(dst),bytes=dst.stat().st_size,size=target.size,quality=quality,sha256=hashlib.sha256(dst.read_bytes()).hexdigest()))
Path("image-optimization-report.json").write_text(json.dumps(report,indent=2))
for row in report:
    if row["output"].endswith("-1920.webp"):
        assert row["bytes"] <= row["source_bytes"]*.2, row
