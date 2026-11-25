"""Review browser capture output, never publish it automatically."""
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFilter, ImageStat
import json,hashlib,math
root=Path('browser-capture')
manifest=json.loads((root/'manifest.json').read_text())
for source in manifest['sources']:
    candidates=[]; seen=[]
    for frame in source['frames']:
        p=root/frame['file']
        with Image.open(p) as raw: im=raw.convert('RGB')
        gray=ImageOps.grayscale(im).resize((128,128))
        sharp=ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).stddev[0]
        luma=ImageStat.Stat(gray).mean[0]
        tiny=list(gray.resize((8,8)).getdata()); avg=sum(tiny)/64
        bits=sum((v>avg)<<i for i,v in enumerate(tiny))
        dup=any((bits^old).bit_count()<=3 for old in seen)
        seen.append(bits)
        frame.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=im.size,edge_stddev=round(sharp,2),mean_luma=round(luma,2),near_duplicate=dup)
        if dup or luma<18 or luma>240 or sharp<5: continue
        candidates.append((sharp,frame,p))
    candidates=sorted(candidates,key=lambda x:x[0],reverse=True)[:12]
    source['candidate_count']=len(candidates)
    if not candidates: continue
    folder=root/source['id']
    sheet=Image.new('RGB',(960,math.ceil(len(candidates)/3)*240),'#101510'); draw=ImageDraw.Draw(sheet)
    for i,(_,frame,p) in enumerate(candidates):
        with Image.open(p) as raw: im=raw.convert('RGB')
        im=ImageEnhance.Brightness(im).enhance(1.05)
        im=ImageEnhance.Contrast(im).enhance(1.04)
        im.thumbnail((1280,1280))
        dest=folder/(p.stem+'.webp');im.save(dest,'WEBP',quality=86)
        frame['candidate']=str(dest.relative_to(root));frame['candidate_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
        thumb=ImageOps.contain(im,(310,210));x=i%3*320;y=i//3*240
        sheet.paste(thumb,(x+(320-thumb.width)//2,y));draw.text((x+5,y+215),f"{p.stem} {frame['second']:.1f}s",fill='white')
    sheet.save(folder/'contact-sheet.jpg',quality=88)
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
