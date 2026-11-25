"""One-time owner photo registration. Verify all input bytes before changing files."""
import hashlib,json,re,zipfile
from pathlib import Path
from PIL import Image
import io
ROOT=Path(".")
ARCHIVE=ROOT/"glendalough-site-photos.zip"
RECORDS=json.loads("[{\"path\":\"images/editorial/night-city-live.webp\",\"sha256\":\"b7fcad2820593923aba8958607961ad2dfca6c1403327ce475675ff4b2cb11be\",\"source_type\":\"owner_supplied_video_frame\",\"source_filename\":\"VID_20260708_105322_1.mp4\",\"source_video_sha256\":\"80052caf0bd2fd4fe3a4d6376406df294079049b3aaf48a78285ebd0de533f24\",\"nominal_second\":102.54,\"crop\":[0,650,1080,1920],\"grade\":{\"gamma\":0.77,\"contrast\":1.04,\"saturation\":0.94,\"unsharp_radius\":0.8,\"unsharp_percent\":38,\"unsharp_threshold\":5},\"dimensions\":[1080,1270],\"location_verified\":false},{\"path\":\"images/editorial/indoor-live-089s.webp\",\"sha256\":\"b320068e7586f6d01679cf3d4f6dac9a40bd22628cf917739c8143da7a0144f8\",\"source_type\":\"owner_supplied_video_frame\",\"source_filename\":\"2026-09-14-083940441.mp4\",\"source_video_sha256\":\"5b6418ae26fb6dec050d69daa365130092a197e7b86750922a17d7d3509737f6\",\"nominal_second\":89,\"crop\":[0,656,1080,1264],\"grade\":{\"gamma\":0.88,\"saturation\":0.93,\"contrast\":1.045,\"unsharp_radius\":0.9,\"unsharp_percent\":45,\"unsharp_threshold\":4},\"dimensions\":[1080,608],\"location_verified\":false,\"approved_by_user\":true},{\"path\":\"images/editorial/street-performance.webp\",\"sha256\":\"987b24413e379f0a8554e390cf2c5c78e637aea9fdbe69eb9a0cf71294f104d9\",\"source_type\":\"owner_supplied_video_frame\",\"source_filename\":\"VID_20260807_082420_898_bsl.mp4\",\"source_video_sha256\":\"d225bb7513e14f0b2c1fdd9d42579b058d6a1770272dac69b6cd40ea3e108aed\",\"nominal_second\":43.16,\"crop\":[0,1080,2160,3780],\"grade\":{\"gamma\":0.74,\"contrast\":1.04,\"saturation\":0.96,\"unsharp_radius\":0.8,\"unsharp_percent\":38,\"unsharp_threshold\":5},\"dimensions\":[1152,1440],\"location_verified\":false}]")
def sha(data): return hashlib.sha256(data).hexdigest()
def main():
    data=ARCHIVE.read_bytes()
    assert sha(data)=="abc8ab2a35f1a236951518ce78eb6d7e0a70f2132e7b1625507086fb7320d63e","Unexpected archive SHA"
    pending={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist())==sorted(Path(r["path"]).name for r in RECORDS)
        assert z.testzip() is None
        for r in RECORDS:
            p=Path(r["path"]); b=z.read(p.name)
            assert sha(b)==r["sha256"],p
            with Image.open(io.BytesIO(b)) as im:
                im.load()
                assert im.format=="WEBP" and list(im.size)==r["dimensions"],p
            assert not p.exists(),p
            pending[p]=b
    html=ROOT/"index.html"; body=html.read_bytes().decode("utf-8")
    labels=[("night-session.jpg","夜の街での屋外演奏","夜間の屋外演奏"),("indoor-session.jpg","木目調の会場で演奏する4人","室内ライブ"),("street-live.webp","街角で楽器を奏でる演奏者","路上演奏")]
    for r,(old,alt,label) in zip(RECORDS,labels):
        pattern=r'<figure class="gallery-item reveal"><img src="images/editorial/'+re.escape(old)+r'"[^>]*>.*?</figure>'
        w,h=r["dimensions"]
        replacement=f'<figure class="gallery-item reveal"><img src="{r["path"]}" alt="{alt}" width="{w}" height="{h}" loading="lazy"><figcaption>{label}｜演奏映像から</figcaption></figure>'
        body,n=re.subn(pattern,replacement,body,flags=re.S)
        assert n==1,old
    provenance=ROOT/"images/editorial/provenance.json"
    old=json.loads(provenance.read_text())
    assert len(old)==3 and all(x["source_type"]=="official_video_thumbnail_not_direct_frame" for x in old)
    archive_manifest=ROOT/"images/editorial/thumbnail-provenance-archive.json"
    assert not archive_manifest.exists()
    # Preserve historical files and original metadata; change only current gallery records.
    pending[archive_manifest]=provenance.read_bytes()
    pending[provenance]=(json.dumps(RECORDS,ensure_ascii=False,indent=2)+"\n").encode()
    pending[html]=body.encode()
    css=ROOT/"style.css"
    pending[css]=css.read_bytes()+b"\n/* Preserve complete documentary compositions. */\n.gallery-grid .gallery-item:nth-child(2) img,.gallery-grid .gallery-item:nth-child(3) img,.gallery-grid .gallery-item:nth-child(4) img{object-fit:contain;background:#101510}\n"
    for p,b in pending.items(): p.write_bytes(b)
    ARCHIVE.unlink()
    print("Exact source image SHA and dimensions verified: 3/3; gallery replacement staged")
if __name__=="__main__": main()
