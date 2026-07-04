from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
OUT = UI / "Previews"
PAGES = ["create","outputs","editor","help","settings","tools","images","reports","update"]
SIZES = [(1360,820),(1760,1040),(1920,1080),(2560,1440)]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env=os.environ.copy();env.setdefault("QT_QPA_PLATFORM","offscreen");env.setdefault("QT_QUICK_BACKEND","software");env.setdefault("QSG_RHI_BACKEND","software");env["KFPS_APP_ROOT"]=str(ROOT)
    failures=[]
    for w,h in SIZES:
        for page in PAGES:
            target=OUT/f"{page}_{w}x{h}.png"
            cmd=[sys.executable,str(UI/"app.py"),"--allow-unsupported-python","--demo","--page",page,"--width",str(w),"--height",str(h),"--screenshot",str(target)]
            run=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=45)
            if run.returncode or not target.exists(): failures.append((page,w,h,run.returncode,run.stdout))
    if failures:
        report="\n\n".join(f"{p} {w}x{h} exit={c}\n{o}" for p,w,h,c,o in failures);(OUT/"capture-errors.txt").write_text(report,encoding="utf-8");raise SystemExit(1)
if __name__=="__main__":main()
