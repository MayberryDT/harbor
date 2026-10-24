#!/usr/bin/env python3
"""Keep the public native build inputs alongside executable evidence on Halla."""
import hashlib, json, sys
from pathlib import Path
source=Path(__file__).resolve().parent.parent
output=Path(sys.argv[1])
if not output.is_absolute():raise SystemExit('output must be an absolute Halla build path')
paths=[source/'Makefile',source/'tests/helper-hardening.sh']
paths+=sorted((source/'helper').glob('*.c'))+sorted((source/'helper').glob('*.h'))
files={str(p.relative_to(source)):p.read_bytes() for p in paths}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
root=output/'sources'/digest
for name,data in files.items():
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():target.write_bytes(data);target.chmod(0o444)
    if target.read_bytes()!=data:raise SystemExit('frozen source mismatch: '+name)
record=root/'manifest.json';expected=json.dumps({'source_bundle_sha256':digest,'files':manifest},sort_keys=True,indent=2)+'\n'
if not record.exists():record.write_text(expected);record.chmod(0o444)
if record.read_text()!=expected:raise SystemExit('frozen source manifest mismatch')
print(root)
