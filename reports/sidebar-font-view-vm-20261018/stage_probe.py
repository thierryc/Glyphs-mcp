"""Stage the next hashed source probe for this disposable VM investigation."""
from pathlib import Path
import hashlib,json,zipfile
import sys
stage=Path('/private/tmp/beztrace-milestone-7-v0.2.0-20261012/sidebar')
number=int(sys.argv[1]); port=8766+number
with zipfile.ZipFile(stage/'source8.zip') as old, zipfile.ZipFile(stage/('source'+str(number)+'.zip'),'w',zipfile.ZIP_DEFLATED) as new:
    for item in old.infolist():
        data=old.read(item.filename)
        if item.filename=='scripts/qualify_sidebar_counts_native.py':data=Path(item.filename).read_bytes()
        new.writestr(item,data)
sha=hashlib.sha256((stage/('source'+str(number)+'.zip')).read_bytes()).hexdigest()
p=Path(__file__).with_name('vm_driver_startup_timeout.py')
s=p.read_text().replace('8773',str(port)).replace('source6.zip','source'+str(number)+'.zip').replace('678c45d73c8495903545214aac508ad704b32693b8aea24c4e08d54f3cb29133',sha)
p.with_name('vm_driver_'+str(number)+'.py').write_text(s)
(stage/('driver'+str(number)+'.py')).write_text(s)
print(json.dumps(dict(port=port,sourceSha256=sha)))
