"""Inspect/mutate only disposable native E2E journals, across storage versions.
Failure cases: never treat a broken SQLite store as legacy absence, never touch a
real profile, preserve exact wire bytes, and commit attacker-fixture writes before
letting the real helper process them. This is not an application storage adapter.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

def paths(peer):
    home=Path(peer.home)
    if not home.name.startswith('home-') or not home.parent.name.startswith(('harbor-','omaq-')):
        raise RuntimeError('journal fixture requires a disposable native profile')
    root=home/'sync';db=root/'journal.sqlite'
    modern=db.exists() or db.is_symlink() or (root/'journal.present').exists()
    return root,db,modern

def events(peer):
    root,db,modern=paths(peer)
    if modern:
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=1)) as connection:
            if connection.execute('SELECT ready FROM journal_meta WHERE singleton=1').fetchone()!=(1,):
                raise RuntimeError('journal migration is not committed')
            return {identifier:bytes(wire) for identifier,wire in connection.execute('SELECT id,wire FROM events')}
    if not (root/'events').exists():return {}
    return {path.name:path.read_bytes() for path in (root/'events').iterdir() if not path.name.startswith('.')}

def get(peer,identifier):
    return events(peer).get(identifier)

def delete(peer,identifier):
    root,db,modern=paths(peer)
    if modern:
        with closing(sqlite3.connect(db,timeout=2)) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('DELETE FROM events WHERE id=?',(identifier,))
            connection.commit()
    else:(root/'events'/identifier).unlink()

def put(peer,wire):
    raw=wire.encode() if isinstance(wire,str) else wire
    head,body=raw.decode().split('\n',1)
    version,identifier,clock,person,author,conversation,kind=head.split('|')
    if version!='HS2' or len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):
        raise RuntimeError('invalid controlled fixture wire')
    root,db,modern=paths(peer)
    if modern:
        origin=target=request=related='';request_class=0
        parts=body.split('\n',1)[0].split('|')
        if kind=='message' and parts[0]=='HM2':
            origin,target=parts[1:3];request='' if parts[4]=='-' else parts[4];request_class=1
        elif kind in ('edit','delete','reaction','read') and parts[0]=='HA1':
            origin,target=parts[1:3];related=parts[4];request=parts[5];request_class=2
        with closing(sqlite3.connect(db,timeout=2)) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('INSERT INTO events(id,clock,person,author,conversation,kind,wire,origin,target,request_class,request,related) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (identifier,clock,person,author,conversation,kind,raw,origin,target,request_class,request,related))
            connection.commit()
    else:
        path=root/'events'/identifier;path.write_bytes(raw);path.chmod(0o600)
    return identifier

def ledger_modern(peer):
    root,db,modern=paths(peer)
    if not modern:return root,db,False
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=1)) as connection:
        fields={row[1] for row in connection.execute('PRAGMA table_info(journal_meta)')}
        if 'ledger_ready' not in fields:return root,db,False
        if connection.execute('SELECT ledger_ready FROM journal_meta').fetchone()!=(1,):
            raise RuntimeError('crypto ledger migration is not committed')
    return root,db,True

def envelopes(peer,bucket):
    if bucket not in ('outbox','inbox','ack','rekey'):raise RuntimeError('unknown fixture bucket')
    root,db,modern=ledger_modern(peer)
    if modern:
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=1)) as connection:
            return {name:bytes(body) for name,body in connection.execute('SELECT name,body FROM envelopes WHERE bucket=?',(bucket,))}
    return {path.name:path.read_bytes() for path in (root/bucket).glob('*') if not path.name.startswith('.')}

def envelope_delete(peer,bucket,name):
    if bucket not in ('outbox','inbox','ack','rekey'):raise RuntimeError('unknown fixture bucket')
    root,db,modern=ledger_modern(peer)
    if modern:
        with closing(sqlite3.connect(db,timeout=2)) as connection:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('DELETE FROM envelopes WHERE bucket=? AND name=?',(bucket,name));connection.commit()
    else:(root/bucket/name).unlink(missing_ok=True)
