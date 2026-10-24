#!/usr/bin/env python3
"""Keep native E2E code/imports replayable while the working source evolves."""
import hashlib
import json
from pathlib import Path
import sys
source=Path(__file__).resolve().parent.parent
output=Path(sys.argv[1])
if not output.is_absolute():raise SystemExit('output must be an absolute Halla build path')
files={str(path.relative_to(source)):path.read_bytes()
       for folder in ('tests','mailbox') for path in sorted((source/folder).rglob('*'))
       if path.is_file() and path.suffix in ('.py','.c')}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
root=output/'runners'/digest
for name,data in files.items():
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():target.write_bytes(data);target.chmod(0o444)
    if target.read_bytes()!=data:raise SystemExit('frozen runner mismatch: '+name)
record=root/'manifest.json'
expected=json.dumps({'runner_bundle_sha256':digest,'files':manifest},sort_keys=True,indent=2)+'\n'
if not record.exists():record.write_text(expected);record.chmod(0o444)
if record.read_text()!=expected:raise SystemExit('frozen manifest mismatch')
print(root)
