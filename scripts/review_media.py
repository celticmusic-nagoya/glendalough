"""Read-only review assets; never publish unreviewed media."""
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageDraw
from urllib.request import urlopen, Request
from io import BytesIO
import hashlib, json
out=Path('media-review'); out.mkdir(exist_ok=True)
records=[]; previews=[]
def sha(data): return hashlib.sha256(data).hexdigest()
def add(data, name, source, kind):
    with Image.open(BytesIO(data)) as raw:
        im=ImageOps.exif_transpose(raw).convert('RGB')
    if min(im.size)<180: raise ValueError('Image too small')
    im.thumbnail((1280,1280))
    original=im.copy()
    # restrained grading only, no synthetic subjects
    im=ImageEnhance.Color(im).enhance(.84)
    im=ImageEnhance.Contrast(im).enhance(1.04)
    im=ImageEnhance.Brightness(im).enhance(1.06)
    name=name+'.webp'; path=out/name
    im.save(path,'WEBP',quality=85)
    with Image.open(path) as check: check.load()
    records.append(dict(name=name,source=source,kind=kind,source_sha256=sha(data),output_sha256=sha(path.read_bytes()),size=im.size,status='REVIEW_REQUIRED'))
    previews.append((name,original,im))
for p in sorted(Path('images').iterdir()):
    if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png'} and not any(s in p.name.lower() for s in ('logo','favicon','icon','back-black')):
        try: add(p.read_bytes(),'local-'+p.stem,str(p),'local_unclassified')
        except Exception as e: records.append(dict(source=str(p),status='FAILED',error=str(e)))
for vid in ('-btG-2M4QXQ','L26X01zSNgo','9d2jLKTgQtk'):
    for variant in ('maxresdefault','hqdefault'):
        url=f'https://i.ytimg.com/vi/{vid}/{variant}.jpg'
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as res: data=res.read(8_000_001)
            if len(data)>8_000_000: raise ValueError('Too large')
            add(data,'youtube-'+vid,url,'official_video_thumbnail_not_verified_frame')
            break
        except Exception as e: records.append(dict(source=url,status='FAILED',error=str(e)))
# Side by side: source vs graded version; labels and provenance in manifest.
w,h=320,240
sheet=Image.new('RGB',(2*w, max(1,len(previews))*(h+28)), '#101510')
d=ImageDraw.Draw(sheet)
for i,(name,a,b) in enumerate(previews):
    y=i*(h+28)
    for j,img in enumerate((a,b)):
        thumb=ImageOps.contain(img,(w,h)); sheet.paste(thumb,(j*w+(w-thumb.width)//2,y+(h-thumb.height)//2))
    d.text((8,y+h+4),name+' | ORIGINAL / GRADED',fill='white')
sheet.save(out/'contact-sheet.jpg',quality=88)
(out/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
