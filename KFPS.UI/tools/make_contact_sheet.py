from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/"Previews";files=sorted(folder.glob("*_1760x1040.png"));thumbs=[]
for path in files:
 im=Image.open(path).convert("RGB");im.thumbnail((600,376));thumbs.append((path.stem,im.copy()))
if thumbs:
 cols=2;rows=(len(thumbs)+1)//2;sheet=Image.new("RGB",(cols*620,rows*416),(18,10,20));d=ImageDraw.Draw(sheet)
 for i,(name,im) in enumerate(thumbs):
  x=(i%cols)*620+10;y=(i//cols)*416+28;sheet.paste(im,(x,y));d.text((x,y-20),name,fill=(255,210,230))
 sheet.save(folder/"complete_app_contact_sheet.png")
