#define _GNU_SOURCE
#include "journal.h"
#ifdef HAVE_SIGNAL
/* Storage failure cases, specified before implementation:
 * - interrupted insertion/import must never expose a partial authoritative set;
 * - exact retries retain bytes/clock, conflicting IDs never overwrite;
 * - an uncertain commit must recover durability before any ACK/promotion;
 * - missing/corrupt/wrong-owner databases must not silently start new history;
 * - unsafe paths/sidecars, busy storage and allocation/I/O errors fail closed;
 * - indexed request lookup distinguishes absence, failure and duplicates;
 * - scans fail rather than returning an incomplete successful history.
 * Native capacity, journal-I/O, crash/rekey and migration journeys exercise the
 * process boundary. No cryptographic authorization is delegated to this module.
 */
#include "device_sync.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
struct harbor_journal {
  sqlite3 *db;
  char owner[65];
  int directory, importing,working,ledger_importing;
  int64_t attempt;
};
static int hex(const char *s,size_t n) {
  if(!s || strlen(s)!=n)return 0;
  for(size_t i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
  return 1;
}
static int private_file(int fd) {
  struct stat st;
  return fstat(fd,&st)==0 && S_ISREG(st.st_mode) && st.st_uid==geteuid() &&
    st.st_nlink==1 && !(st.st_mode&0077);
}
static int private_directory(int fd) {
  struct stat st;
  return fd>=0 && fstat(fd,&st)==0 && S_ISDIR(st.st_mode) &&
    st.st_uid==geteuid() && !(st.st_mode&0077);
}
static int exec(struct harbor_journal *j,const char *sql) {
  return j->db && sqlite3_exec(j->db,sql,NULL,NULL,NULL)==SQLITE_OK ? 0:-1;
}
static int bind(sqlite3_stmt *q,int at,const char *value) {
  return sqlite3_bind_text(q,at,value,-1,SQLITE_TRANSIENT)==SQLITE_OK?0:-1;
}
static sqlite3_stmt *prepare(struct harbor_journal *j,const char *sql) {
  sqlite3_stmt *q=NULL;
  if(!j->db || sqlite3_prepare_v2(j->db,sql,-1,&q,NULL)!=SQLITE_OK) {
    sqlite3_finalize(q);return NULL;
  }
  return q;
}
/* A failed write invalidates the connection. Reopening runs SQLite recovery
 * and a FULL synchronous write barrier before returning any readable event. */
static int failed(struct harbor_journal *j) {
  if(j->db){(void)exec(j,"ROLLBACK");sqlite3_close_v2(j->db);j->db=NULL;}
  j->importing=0;j->working=0;j->ledger_importing=0;return -1;
}
void harbor_journal_close(struct harbor_journal *j) {
  if(!j)return;
  if(j->db)sqlite3_close_v2(j->db);
  if(j->directory>=0)close(j->directory);
  free(j);
}
static int marker(struct harbor_journal *j) {
  int fd=openat(j->directory,"journal.present",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,0600);
  if(fd<0)return -1;
  struct stat st;
  int rc=!private_file(fd) || fstat(fd,&st) || st.st_size || fsync(fd) || fsync(j->directory);
  close(fd);return rc?-1:0;
}
struct harbor_journal *harbor_journal_open(const char *home,const char *owner) {
  if(!home || *home!='/' || !hex(owner,64))return NULL;
  struct harbor_journal *j=calloc(1,sizeof(*j));
  if(!j)return NULL;
  j->directory=-1;memcpy(j->owner,owner,65);
  int parent=open(home,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  if(!private_directory(parent)){if(parent>=0)close(parent);goto bad;}
  if(mkdirat(parent,"sync",0700) && errno!=EEXIST){close(parent);goto bad;}
  j->directory=openat(parent,"sync",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  int durable=fsync(parent);close(parent);
  if(durable || !private_directory(j->directory))goto bad;
  struct stat st;
  int had_marker=0;
  int proof=openat(j->directory,"journal.present",O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
  if(proof>=0) {
    int valid=private_file(proof) && fstat(proof,&st)==0 && st.st_size==0;
    close(proof);if(!valid)goto bad;
    had_marker=1;
  } else if(errno!=ENOENT)goto bad;
  int exists=fstatat(j->directory,"journal.sqlite",&st,AT_SYMLINK_NOFOLLOW)==0;
  if(!exists && errno!=ENOENT)goto bad;
  if((!exists && had_marker) || (exists && had_marker && st.st_size==0))goto bad;
  int fd=openat(j->directory,"journal.sqlite",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,0600);
  if(fd<0)goto bad;
  int safe=private_file(fd) && fsync(fd)==0 && fsync(j->directory)==0;
  close(fd);if(!safe)goto bad;
  const char *sidecars[]={"journal.sqlite-wal","journal.sqlite-shm","journal.sqlite-journal"};
  for(size_t i=0;i<sizeof(sidecars)/sizeof(*sidecars);i++) {
    fd=openat(j->directory,sidecars[i],O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
    if(fd<0){if(errno==ENOENT)continue;goto bad;}
    safe=private_file(fd);close(fd);if(!safe)goto bad;
  }
  char path[PATH_MAX];
  int n=snprintf(path,sizeof(path),"%s/sync/journal.sqlite",home);
  if(n<0 || (size_t)n>=sizeof(path) || sqlite3_open_v2(path,&j->db,
      SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_NOFOLLOW|SQLITE_OPEN_NOMUTEX,NULL)!=SQLITE_OK)goto bad;
  if(sqlite3_extended_result_codes(j->db,1)!=SQLITE_OK ||
     sqlite3_busy_timeout(j->db,100)!=SQLITE_OK)goto bad;
  sqlite3_limit(j->db,SQLITE_LIMIT_LENGTH,1024*1024);
  if(sqlite3_db_config(j->db,SQLITE_DBCONFIG_DEFENSIVE,1,NULL)!=SQLITE_OK ||
     sqlite3_db_config(j->db,SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,0,NULL)!=SQLITE_OK)goto bad;
  sqlite3_stmt *q=prepare(j,"PRAGMA application_id");
  int application=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);
  q=prepare(j,"PRAGMA user_version");
  int version=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);
  if((application!=0 && application!=0x484a5231) ||
     (application==0 && (had_marker || version!=0)) ||
     (application==0x484a5231 && version!=1 && version!=2 && version!=3))goto bad;
  if(application==0) {
    q=prepare(j,"SELECT count(*) FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'");
    safe=q && sqlite3_step(q)==SQLITE_ROW && sqlite3_column_int64(q,0)==0;
    sqlite3_finalize(q);if(!safe)goto bad;
  } else {
    q=prepare(j,"SELECT id,clock,person,author,conversation,kind,wire,origin,target,request_class,request,related FROM events LIMIT 0");
    safe=q && sqlite3_step(q)==SQLITE_DONE;
    sqlite3_finalize(q);if(!safe)goto bad;
    q=prepare(j,"SELECT owner,ready,barrier FROM journal_meta WHERE singleton=1");
    safe=q && sqlite3_step(q)==SQLITE_ROW &&
      sqlite3_column_text(q,0) && !strcmp((const char *)sqlite3_column_text(q,0),owner) &&
      (sqlite3_column_int(q,1)==0 || sqlite3_column_int(q,1)==1) &&
      (!had_marker || sqlite3_column_int(q,1)==1) &&
      (sqlite3_column_int(q,2)==0 || sqlite3_column_int(q,2)==1);
    sqlite3_finalize(q);if(!safe)goto bad;
  }
  q=prepare(j,"PRAGMA journal_mode=WAL");
  safe=q && sqlite3_step(q)==SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(q,0),"wal");
  sqlite3_finalize(q);if(!safe)goto bad;
  if(exec(j,"PRAGMA synchronous=FULL; PRAGMA trusted_schema=OFF; PRAGMA foreign_keys=ON; PRAGMA temp_store=MEMORY; BEGIN IMMEDIATE;"
    "PRAGMA application_id=1212830257;"
    "CREATE TABLE IF NOT EXISTS journal_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner TEXT NOT NULL,ready INTEGER NOT NULL CHECK(ready IN(0,1)),barrier INTEGER NOT NULL CHECK(barrier IN(0,1)),ledger_ready INTEGER NOT NULL DEFAULT 0 CHECK(ledger_ready IN(0,1)));"
    "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY CHECK(length(id)=32),clock TEXT NOT NULL CHECK(length(clock)=16),person TEXT NOT NULL,author TEXT NOT NULL,conversation TEXT NOT NULL,kind TEXT NOT NULL,wire BLOB NOT NULL,origin TEXT NOT NULL,target TEXT NOT NULL,request_class INTEGER NOT NULL,request TEXT NOT NULL,related TEXT NOT NULL) WITHOUT ROWID;"
    "CREATE INDEX IF NOT EXISTS event_order ON events(clock,author,id);"
    "CREATE INDEX IF NOT EXISTS event_person_clock ON events(person,clock);"
    "CREATE INDEX IF NOT EXISTS event_conversation ON events(origin,target,clock,author,id);"
    "CREATE INDEX IF NOT EXISTS event_request ON events(person,author,request_class,request);"
    "CREATE INDEX IF NOT EXISTS event_kind ON events(kind,clock,author,id);"
    "CREATE INDEX IF NOT EXISTS event_related ON events(related,kind,clock,author,id);"
    "CREATE TABLE IF NOT EXISTS pending_work(id TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,priority INTEGER NOT NULL,last_try INTEGER NOT NULL,cursor INTEGER NOT NULL,projected INTEGER NOT NULL CHECK(projected IN(0,1)),not_before INTEGER NOT NULL DEFAULT 0) WITHOUT ROWID;"
    "CREATE INDEX IF NOT EXISTS work_order ON pending_work(priority,last_try,id);"
    "CREATE TABLE IF NOT EXISTS roster_heads(scope TEXT PRIMARY KEY,head TEXT NOT NULL) WITHOUT ROWID;"
    "DROP TRIGGER IF EXISTS event_work; CREATE TRIGGER event_work AFTER INSERT ON events BEGIN INSERT INTO pending_work(id,priority,last_try,cursor,projected) VALUES(new.id,0,0,0,CASE WHEN new.kind='contact' THEN 0 ELSE 1 END); END;"
    "INSERT INTO pending_work(id,priority,last_try,cursor,projected) SELECT id,0,0,0,0 FROM events WHERE kind='contact' ON CONFLICT(id) DO UPDATE SET projected=0;"))goto bad;
  q=prepare(j,"SELECT count(*) FROM pragma_table_info('pending_work') WHERE name='not_before'");
  int delay_column=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);
  if(delay_column==0 && version==1) {
    if(exec(j,"ALTER TABLE pending_work ADD COLUMN not_before INTEGER NOT NULL DEFAULT 0"))goto bad;
  } else if(delay_column!=1)goto bad;
  if(exec(j,"CREATE INDEX IF NOT EXISTS work_due ON pending_work(priority,not_before,last_try,id)"))goto bad;
  q=prepare(j,"SELECT count(*) FROM pragma_table_info('journal_meta') WHERE name='ledger_ready'");
  int ledger_column=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);
  if(ledger_column==0 && (version==1 || version==2)) {
    if(exec(j,"ALTER TABLE journal_meta ADD COLUMN ledger_ready INTEGER NOT NULL DEFAULT 0 CHECK(ledger_ready IN(0,1))"))goto bad;
  } else if(ledger_column!=1)goto bad;
  if(exec(j,"CREATE TABLE IF NOT EXISTS envelopes(bucket TEXT NOT NULL,name TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(bucket,name)) WITHOUT ROWID"))goto bad;
  /* Retry timing is a scheduling hint, reset across process/boot recovery. */
  if(exec(j,"UPDATE pending_work SET not_before=0; PRAGMA user_version=3"))goto bad;
  q=prepare(j,"PRAGMA synchronous");
  safe=q && sqlite3_step(q)==SQLITE_ROW && sqlite3_column_int(q,0)==2;
  sqlite3_finalize(q);if(!safe)goto bad;
  q=prepare(j,"INSERT INTO journal_meta(singleton,owner,ready,barrier) VALUES(1,?,0,0) ON CONFLICT(singleton) DO NOTHING");
  safe=q && !bind(q,1,owner) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);if(!safe)goto bad;
  q=prepare(j,"SELECT owner FROM journal_meta WHERE singleton=1");
  safe=q && sqlite3_step(q)==SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(q,0),owner);
  sqlite3_finalize(q);
  if(!safe || exec(j,"UPDATE journal_meta SET barrier=1-barrier WHERE singleton=1; COMMIT") || fsync(j->directory))goto bad;
  if(harbor_journal_ready(j)==1 && marker(j))goto bad;
  q=prepare(j,"SELECT coalesce(max(last_try),0) FROM pending_work");
  safe=q && sqlite3_step(q)==SQLITE_ROW;
  if(safe)j->attempt=sqlite3_column_int64(q,0);
  sqlite3_finalize(q);if(!safe || j->attempt<0)goto bad;
  return j;
bad:
  harbor_journal_close(j);return NULL;
}
int harbor_journal_ready(struct harbor_journal *j) {
  sqlite3_stmt *q=prepare(j,"SELECT ready FROM journal_meta WHERE singleton=1");
  int rc=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);return rc;
}
int harbor_journal_begin_import(struct harbor_journal *j) {
  if(j->importing || harbor_journal_ready(j)!=0 || exec(j,"BEGIN IMMEDIATE"))return -1;
  j->importing=1;return 0;
}
int harbor_journal_finish_import(struct harbor_journal *j) {
  if(!j->importing || exec(j,"UPDATE pending_work SET priority=CASE WHEN id IN(SELECT id FROM events WHERE kind='contact') THEN 0 ELSE 1 END; UPDATE journal_meta SET ready=1 WHERE singleton=1; COMMIT"))return failed(j);
  j->importing=0;
  if(marker(j))return failed(j);
  return 0;
}
int harbor_journal_get(struct harbor_journal *j,const char *id,char **wire) {
  *wire=NULL;if(!hex(id,32))return -1;
  sqlite3_stmt *q=prepare(j,"SELECT wire FROM events WHERE id=?");
  int rc=-1;
  if(q && !bind(q,1,id)) {
    int step=sqlite3_step(q);
    if(step==SQLITE_DONE)rc=0;
    else if(step==SQLITE_ROW) {
      int n=sqlite3_column_bytes(q,0);const void *bytes=sqlite3_column_blob(q,0);
      if(n>0 && n<=HARBOR_PLAIN_MAX && bytes && !memchr(bytes,0,(size_t)n)) {
        *wire=malloc((size_t)n+1);
        if(*wire){memcpy(*wire,bytes,(size_t)n);(*wire)[n]=0;rc=1;}
      }
    }
  }
  sqlite3_finalize(q);return rc;
}
int harbor_journal_put(struct harbor_journal *j,const struct harbor_sync_event *e,
    const char *wire,const struct harbor_journal_index *index,int *created) {
  *created=0;
  if(!j->db || !hex(e->id,32) || !hex(e->person,64) || !hex(e->author,64) ||
     !wire || !*wire || strlen(wire)>HARBOR_PLAIN_MAX)return -1;
  int own_transaction=!j->importing;
  if(own_transaction && exec(j,"BEGIN IMMEDIATE"))return failed(j);
  char *existing=NULL;int found=harbor_journal_get(j,e->id,&existing);
  if(found<0 || (found==1 && strcmp(existing,wire))) {free(existing);return failed(j);}
  free(existing);
  if(!found) {
    struct harbor_journal_index empty={0};if(!index)index=&empty;
    sqlite3_stmt *q=prepare(j,"INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)");
    char clock[17];snprintf(clock,sizeof(clock),"%016llx",(unsigned long long)e->clock);
    int safe=q && !bind(q,1,e->id) && !bind(q,2,clock) && !bind(q,3,e->person) &&
      !bind(q,4,e->author) && !bind(q,5,e->conversation) && !bind(q,6,e->kind) &&
      sqlite3_bind_blob(q,7,wire,(int)strlen(wire),SQLITE_TRANSIENT)==SQLITE_OK &&
      !bind(q,8,index->origin) && !bind(q,9,index->target) &&
      sqlite3_bind_int(q,10,index->request_class)==SQLITE_OK &&
      !bind(q,11,index->request) && !bind(q,12,index->related) && sqlite3_step(q)==SQLITE_DONE;
    sqlite3_finalize(q);if(!safe)return failed(j);
  }
  if(own_transaction && exec(j,"UPDATE journal_meta SET barrier=1-barrier WHERE singleton=1; COMMIT"))return failed(j);
  *created=!found;return 0;
}
int64_t harbor_journal_count(struct harbor_journal *j) {
  sqlite3_stmt *q=prepare(j,"SELECT count(*) FROM events");
  int64_t count=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int64(q,0):-1;
  sqlite3_finalize(q);return count;
}
int harbor_journal_clock(struct harbor_journal *j,uint64_t *own,uint64_t *observed) {
  sqlite3_stmt *q=prepare(j,"SELECT coalesce((SELECT max(clock) FROM events WHERE person=?),'0000000000000000'),coalesce(max(clock),'0000000000000000') FROM events");
  int safe=q && !bind(q,1,j->owner) && sqlite3_step(q)==SQLITE_ROW;
  if(safe) {
    const char *a=(const char *)sqlite3_column_text(q,0),*b=(const char *)sqlite3_column_text(q,1);
    safe=hex(a,16)&&hex(b,16);
    if(safe){*own=strtoull(a,NULL,16);*observed=strtoull(b,NULL,16);}
  }
  sqlite3_finalize(q);return safe?0:-1;
}
int harbor_journal_request(struct harbor_journal *j,const char *person,
    const char *author,int request_class,const char *request,char id[33]) {
  id[0]=0;
  sqlite3_stmt *q=prepare(j,"SELECT id FROM events WHERE person=? AND author=? AND request_class=? AND request=? LIMIT 2");
  int rc=-1;
  if(q && !bind(q,1,person) && !bind(q,2,author) &&
     sqlite3_bind_int(q,3,request_class)==SQLITE_OK && !bind(q,4,request)) {
    int step=sqlite3_step(q);
    if(step==SQLITE_DONE)rc=0;
    else if(step==SQLITE_ROW) {
      const char *value=(const char *)sqlite3_column_text(q,0);
      if(hex(value,32)){memcpy(id,value,33);if(sqlite3_step(q)==SQLITE_DONE)rc=1;}
    }
  }
  sqlite3_finalize(q);return rc;
}
int harbor_journal_visit(struct harbor_journal *j,const char *other,
    int (*visitor)(const char *,void *),void *context) {
  sqlite3_stmt *q=prepare(j,other?
    "SELECT wire FROM events WHERE (origin=? AND target=?) OR (origin=? AND target=?) ORDER BY clock,author,id":
    "SELECT wire FROM events ORDER BY clock,author,id");
  if(!q)return -1;
  if(other && (bind(q,1,j->owner)||bind(q,2,other)||bind(q,3,other)||bind(q,4,j->owner))) {sqlite3_finalize(q);return -1;}
  int count=0,step;
  while((step=sqlite3_step(q))==SQLITE_ROW) {
    int n=sqlite3_column_bytes(q,0);const char *wire=sqlite3_column_blob(q,0);
    if(n<=0 || n>HARBOR_PLAIN_MAX || !wire || memchr(wire,0,(size_t)n) || count==INT_MAX) {count=-1;break;}
    char *copy=malloc((size_t)n+1);
    if(!copy){count=-1;break;}
    memcpy(copy,wire,(size_t)n);copy[n]=0;
    int rc=visitor(copy,context);free(copy);
    if(rc<0){count=-1;break;}
    count++;
    if(rc>0){step=SQLITE_DONE;break;}
  }
  if(step!=SQLITE_DONE)count=-1;
  sqlite3_finalize(q);return count;
}
int harbor_journal_visit_contacts(struct harbor_journal *j,
    int (*visitor)(const char *,void *),void *context) {
  sqlite3_stmt *q=prepare(j,"SELECT wire FROM events WHERE kind='contact' ORDER BY clock,author,id");
  if(!q)return -1;
  int count=0,step;
  while((step=sqlite3_step(q))==SQLITE_ROW) {
    int n=sqlite3_column_bytes(q,0);const char *wire=sqlite3_column_blob(q,0);
    if(n<=0 || n>HARBOR_PLAIN_MAX || !wire || memchr(wire,0,(size_t)n) || count==INT_MAX){count=-1;break;}
    char *copy=malloc((size_t)n+1);if(!copy){count=-1;break;}
    memcpy(copy,wire,(size_t)n);copy[n]=0;
    int rc=visitor(copy,context);free(copy);
    if(rc<0){count=-1;break;}count++;
  }
  if(step!=SQLITE_DONE)count=-1;
  sqlite3_finalize(q);return count;
}
int64_t harbor_journal_pending(struct harbor_journal *j) {
  sqlite3_stmt *q=prepare(j,"SELECT count(*) FROM pending_work");
  int64_t count=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int64(q,0):-1;
  sqlite3_finalize(q);return count;
}
static int64_t work_millis(void) {
  struct timespec now;
  return clock_gettime(CLOCK_MONOTONIC,&now)?-1:(int64_t)now.tv_sec*1000+now.tv_nsec/1000000;
}
static int work_priority(struct harbor_journal *j,int priority,
    struct harbor_journal_work *out,size_t limit) {
  if(!limit)return 0;
  int64_t now=work_millis();if(now<0)return -1;
  sqlite3_stmt *q=prepare(j,"SELECT id,cursor,projected FROM pending_work WHERE priority=? AND not_before<=? ORDER BY not_before,last_try,id LIMIT ?");
  int count=0;
  if(!q || sqlite3_bind_int(q,1,priority)!=SQLITE_OK ||
     sqlite3_bind_int64(q,2,now)!=SQLITE_OK ||
     sqlite3_bind_int(q,3,(int)limit)!=SQLITE_OK){sqlite3_finalize(q);return -1;}
  int step;
  while((step=sqlite3_step(q))==SQLITE_ROW) {
    const char *id=(const char *)sqlite3_column_text(q,0);
    int64_t cursor=sqlite3_column_int64(q,1);
    int projected=sqlite3_column_int(q,2);
    if(!hex(id,32) || cursor<0 || cursor>=HARBOR_SYNC_TARGET_MAX ||
       (projected!=0 && projected!=1)){count=-1;break;}
    memcpy(out[count].id,id,33);out[count].cursor=(unsigned)cursor;
    out[count].projected=projected;count++;
  }
  if(step!=SQLITE_DONE)count=-1;
  sqlite3_finalize(q);return count;
}
int harbor_journal_work_batch(struct harbor_journal *j,
    struct harbor_journal_work *out,size_t capacity) {
  if(!capacity || capacity>64)return -1;
  struct harbor_journal_work fresh[64],backlog[64];
  int n=work_priority(j,0,fresh,capacity),m=work_priority(j,1,backlog,capacity);
  if(n<0 || m<0)return -1;
  int a=0,b=0;size_t count=0;
  while(count<capacity && (a<n || b<m)) {
    for(int i=0;i<3 && a<n && count<capacity;i++)out[count++]=fresh[a++];
    if(b<m && count<capacity)out[count++]=backlog[b++];
  }
  return (int)count;
}
int harbor_journal_work_begin(struct harbor_journal *j) {
  if(j->working || j->importing)return -1;
  if(exec(j,"BEGIN IMMEDIATE"))return failed(j);
  j->working=1;return 0;
}
int harbor_journal_work_update(struct harbor_journal *j,const char *id,
    unsigned cursor,int projected,int complete) {
  if(!j->working || !hex(id,32) || cursor>=HARBOR_SYNC_TARGET_MAX ||
     j->attempt==INT64_MAX)return -1;
  int64_t now=work_millis();if(now<0)return -1;
  sqlite3_stmt *q=prepare(j,complete?"DELETE FROM pending_work WHERE id=?":
    "UPDATE pending_work SET priority=1,last_try=?,cursor=?,projected=?,not_before=? WHERE id=?");
  int safe=0;
  if(q && complete)safe=!bind(q,1,id) && sqlite3_step(q)==SQLITE_DONE;
  else if(q) safe=sqlite3_bind_int64(q,1,++j->attempt)==SQLITE_OK &&
    sqlite3_bind_int64(q,2,cursor)==SQLITE_OK &&
    sqlite3_bind_int(q,3,projected?1:0)==SQLITE_OK && sqlite3_bind_int64(q,4,now+2000)==SQLITE_OK && !bind(q,5,id) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);return safe?0:-1;
}
int harbor_journal_work_commit(struct harbor_journal *j) {
  if(!j->working || exec(j,"COMMIT"))return failed(j);
  j->working=0;return 0;
}
int harbor_journal_projected(struct harbor_journal *j,const char *id) {
  if(j->working || j->importing || exec(j,"BEGIN IMMEDIATE"))return failed(j);
  sqlite3_stmt *q=prepare(j,"UPDATE pending_work SET projected=1 WHERE id=?");
  int safe=q && !bind(q,1,id) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);
  if(!safe || exec(j,"UPDATE journal_meta SET barrier=1-barrier WHERE singleton=1; COMMIT"))return failed(j);
  return 0;
}
int harbor_journal_roster(struct harbor_journal *j,const char *scope,const char *head) {
  if(!head || !hex(head,64) || (scope[0] && (strncmp(scope,"p:",2) || !hex(scope+2,64))))return -1;
  sqlite3_stmt *q=prepare(j,"SELECT head FROM roster_heads WHERE scope=?");
  int same=0,safe=q && !bind(q,1,scope),step=safe?sqlite3_step(q):SQLITE_ERROR;
  if(step==SQLITE_ROW) {
    const char *value=(const char *)sqlite3_column_text(q,0);
    safe=hex(value,64);same=safe && !strcmp(value,head);
  } else safe=step==SQLITE_DONE;
  sqlite3_finalize(q);if(!safe)return -1;if(same)return 0;
  if(j->working || j->importing || exec(j,"BEGIN IMMEDIATE"))return failed(j);
  q=prepare(j,scope[0]?
    "INSERT OR IGNORE INTO pending_work(id,priority,last_try,cursor,projected) SELECT id,1,0,0,CASE WHEN kind='contact' THEN 0 ELSE 1 END FROM events WHERE origin=? AND conversation=? AND request_class IN(1,2)":
    "INSERT OR IGNORE INTO pending_work(id,priority,last_try,cursor,projected) SELECT id,CASE WHEN kind='contact' THEN 0 ELSE 1 END,0,0,CASE WHEN kind='contact' THEN 0 ELSE 1 END FROM events");
  safe=q && (!scope[0] || (!bind(q,1,j->owner) && !bind(q,2,scope))) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);if(!safe)return failed(j);
  q=prepare(j,"INSERT INTO roster_heads VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET head=excluded.head");
  safe=q && !bind(q,1,scope) && !bind(q,2,head) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);
  if(!safe || exec(j,"COMMIT"))return failed(j);
  return 1;
}

/* Ledger failure cases: import is all-or-nothing; exact envelopes never change
 * across retries; inbox commit precedes Signal advancement; an ACK and rekey
 * survive crashes; malformed/unsafe legacy input never enables fallback. Native
 * migration/crash/rekey journeys exercise these boundaries through real crypto. */
static int envelope_name(const char *bucket,const char *name) {
  if(!bucket || !name)return 0;
  if(!strcmp(bucket,"rekey"))return hex(name,64);
  size_t suffix=!strcmp(bucket,"inbox")?64:
    (!strcmp(bucket,"ack") || !strcmp(bucket,"outbox"))?32:0;
  if(!suffix || strlen(name)!=65+suffix || name[64]!='.')return 0;
  char peer[65];memcpy(peer,name,64);peer[64]=0;
  return hex(peer,64) && hex(name+65,suffix);
}
int harbor_journal_ledger_ready(struct harbor_journal *j) {
  sqlite3_stmt *q=prepare(j,"SELECT ledger_ready FROM journal_meta WHERE singleton=1");
  int ready=q && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int(q,0):-1;
  sqlite3_finalize(q);return ready==0 || ready==1?ready:-1;
}
int harbor_journal_ledger_begin(struct harbor_journal *j) {
  if(j->working || j->importing || j->ledger_importing ||
     harbor_journal_ledger_ready(j)!=0)return -1;
  if(exec(j,"BEGIN IMMEDIATE"))return failed(j);
  j->ledger_importing=1;return 0;
}
int harbor_journal_ledger_finish(struct harbor_journal *j) {
  if(!j->ledger_importing || exec(j,"UPDATE journal_meta SET ledger_ready=1,barrier=1-barrier WHERE singleton=1; COMMIT"))return failed(j);
  j->ledger_importing=0;return 0;
}
int harbor_journal_envelope_get(struct harbor_journal *j,const char *bucket,
    const char *name,char **body,size_t *length) {
  *body=NULL;*length=0;if(!envelope_name(bucket,name))return -1;
  sqlite3_stmt *q=prepare(j,"SELECT body FROM envelopes WHERE bucket=? AND name=?");
  int result=-1;
  if(q && !bind(q,1,bucket) && !bind(q,2,name)) {
    int step=sqlite3_step(q);
    if(step==SQLITE_DONE)result=0;
    else if(step==SQLITE_ROW) {
      int n=sqlite3_column_bytes(q,0);const void *bytes=sqlite3_column_blob(q,0);
      int empty=!strcmp(bucket,"ack") || !strcmp(bucket,"rekey");
      if(n>=0 && n<=(int)HARBOR_WIRE_MAX+80 && (empty?n==0:n>0) &&
         (!n || (bytes && !memchr(bytes,0,(size_t)n)))) {
        *body=malloc((size_t)n+1);
        if(*body){if(n)memcpy(*body,bytes,(size_t)n);(*body)[n]=0;*length=(size_t)n;result=1;}
      }
    }
  }
  sqlite3_finalize(q);return result;
}
int harbor_journal_envelope_put(struct harbor_journal *j,const char *bucket,
    const char *name,const char *body,size_t length) {
  int empty=bucket && (!strcmp(bucket,"ack") || !strcmp(bucket,"rekey"));
  if(j->working || j->importing || !envelope_name(bucket,name) ||
     length>HARBOR_WIRE_MAX+80 || (empty?length!=0:(!length || !body)) ||
     (length && memchr(body,0,length)))return -1;
  int transaction=!j->ledger_importing;
  if(transaction && exec(j,"BEGIN IMMEDIATE"))return failed(j);
  char *prior=NULL;size_t prior_n=0;
  int found=harbor_journal_envelope_get(j,bucket,name,&prior,&prior_n);
  int same=found==1 && prior_n==length && (!length || !memcmp(prior,body,length));
  free(prior);
  if(found<0 || (found==1 && !same))return failed(j);
  if(!found) {
    sqlite3_stmt *q=prepare(j,"INSERT INTO envelopes VALUES(?,?,?)");
    int safe=q && !bind(q,1,bucket) && !bind(q,2,name) &&
      sqlite3_bind_blob(q,3,length?body:"",(int)length,SQLITE_TRANSIENT)==SQLITE_OK && sqlite3_step(q)==SQLITE_DONE;
    sqlite3_finalize(q);if(!safe)return failed(j);
  }
  if(transaction && exec(j,"UPDATE journal_meta SET barrier=1-barrier WHERE singleton=1; COMMIT"))return failed(j);
#ifdef HARBOR_SYNC_FAULTS
  const char *point=getenv("HARBOR_SYNC_CRASH_AT");
  if(transaction && !found && !strcmp(bucket,"inbox") && point && !strcmp(point,"after-envelope-commit"))_exit(78);
#endif
  return found?0:1;
}
int harbor_journal_envelope_drop(struct harbor_journal *j,const char *bucket,const char *name) {
  if(j->working || j->importing || j->ledger_importing || !envelope_name(bucket,name))return -1;
  if(exec(j,"BEGIN IMMEDIATE"))return failed(j);
  sqlite3_stmt *q=prepare(j,"DELETE FROM envelopes WHERE bucket=? AND name=?");
  int safe=q && !bind(q,1,bucket) && !bind(q,2,name) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);
  if(!safe || exec(j,"COMMIT"))return failed(j);
  return 0;
}
int64_t harbor_journal_envelope_count(struct harbor_journal *j,const char *bucket,const char *peer) {
  if(!bucket || (strcmp(bucket,"outbox") && strcmp(bucket,"inbox") && strcmp(bucket,"ack") && strcmp(bucket,"rekey")) ||
     (peer && !hex(peer,64)))return -1;
  sqlite3_stmt *q=prepare(j,peer?"SELECT count(*) FROM envelopes WHERE bucket=? AND name>=? AND name<?":
    "SELECT count(*) FROM envelopes WHERE bucket=?");
  char low[66],high[66];
  if(peer){snprintf(low,sizeof(low),"%s.",peer);snprintf(high,sizeof(high),"%s/",peer);}
  int safe=q && !bind(q,1,bucket) && (!peer || (!bind(q,2,low) && !bind(q,3,high)));
  int64_t count=safe && sqlite3_step(q)==SQLITE_ROW?sqlite3_column_int64(q,0):-1;
  sqlite3_finalize(q);return count;
}
int harbor_journal_envelope_rekey(struct harbor_journal *j,const char *peer) {
  if(j->working || j->importing || j->ledger_importing || !hex(peer,64))return -1;
  if(exec(j,"BEGIN IMMEDIATE"))return failed(j);
  char low[66],high[66];snprintf(low,sizeof(low),"%s.",peer);snprintf(high,sizeof(high),"%s/",peer);
  sqlite3_stmt *q=prepare(j,"DELETE FROM envelopes WHERE bucket='outbox' AND name>=? AND name<?");
  int safe=q && !bind(q,1,low) && !bind(q,2,high) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);if(!safe)return failed(j);
#ifdef HARBOR_SYNC_FAULTS
  const char *point=getenv("HARBOR_SYNC_CRASH_AT");
  if(point && !strcmp(point,"during-rekey"))_exit(78);
#endif
  q=prepare(j,"DELETE FROM envelopes WHERE bucket='rekey' AND name=?");
  safe=q && !bind(q,1,peer) && sqlite3_step(q)==SQLITE_DONE;
  sqlite3_finalize(q);
  if(!safe || exec(j,"UPDATE journal_meta SET barrier=1-barrier WHERE singleton=1; COMMIT"))return failed(j);
  return 0;
}

#endif
