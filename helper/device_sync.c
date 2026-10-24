#define _GNU_SOURCE
#include "device_sync.h"
#ifdef HAVE_SIGNAL
#include "devices.h"
#include "message.h"
#include "text.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define PLAIN_MAX (HARBOR_APP_BODY_MAX + 512u)
#define WIRE_MAX HARBOR_WIRE_MAX
/* Replication events are immutable. Encrypted outboxes are durable before send.
 * Authenticated inbox plaintext is durable before Signal updates session state.
 * A recipient ACK means the event reached its durable replica journal. */
static int valid_hex(const char *value, size_t n) {
  if (strlen(value) != n)
    return 0;
  for (size_t i = 0; i < n; i++)
    if (!(value[i] >= '0' && value[i] <= '9') &&
        !(value[i] >= 'a' && value[i] <= 'f'))
      return 0;
  return 1;
}
static int conversation_ok(const char *value) {
  return strlen(value) == 66 &&
         (value[0] == 'd' || value[0] == 'g' || value[0] == 'p') &&
         value[1] == ':' && valid_hex(value + 2, 64);
}
static void error(struct harbor_sync *s, const char *request,
                  const char *code) {
  char escaped[481], line[768];
  if (omaq_json_escape(request, escaped, sizeof(escaped)))
    return;
  snprintf(line, sizeof(line),
           "{\"event\":\"sync.error\",\"request\":\"%s\",\"code\":\"%s\"}",
           escaped, code);
  s->emit(line);
}
static int private_fd(int fd, int directory) {
  struct stat st;
  return fstat(fd, &st) == 0 && st.st_uid == geteuid() &&
                 !(st.st_mode & 0077) &&
                 (directory ? S_ISDIR(st.st_mode) : S_ISREG(st.st_mode)) &&
                 (directory || st.st_nlink == 1)
             ? 0
             : -1;
}
static int child(int parent, const char *name) {
  if (mkdirat(parent, name, 0700) < 0 && errno != EEXIST)
    return -1;
  int fd =
      openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (fd >= 0 && (private_fd(fd, 1) || fsync(parent))) {
    close(fd);
    return -1;
  }
  return fd;
}
static int directory(const char *home, const char *name) {
  int h = open(home, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (h < 0)
    return -1;
  if (private_fd(h, 1)) {
    close(h);
    return -1;
  }
  int root = child(h, "sync");
  close(h);
  if (root < 0)
    return -1;
  int fd = child(root, name);
  close(root);
  return fd;
}
static int read_file(int dir, const char *name, char *out, size_t cap,
                     size_t *length) {
  int fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (fd < 0)
    return errno == ENOENT ? 1 : -1;
  struct stat st;
  int rc = -1;
  *length = 0;
  if (private_fd(fd, 0) || fstat(fd, &st) || st.st_size < 0 ||
      (uint64_t)st.st_size >= cap)
    goto done;
  while (*length < (size_t)st.st_size) {
    ssize_t n = read(fd, out + *length, (size_t)st.st_size - *length);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0)
      goto done;
    *length += (size_t)n;
  }
  char extra;
  if (read(fd, &extra, 1) != 0)
    goto done;
  if (memchr(out, 0, *length))
    goto done;
  out[*length] = 0;
  rc = 0;
done:
  close(fd);
  return rc;
}
static int kind_ok(const char *kind) {
  return !strcmp(kind, "note") || !strcmp(kind, "contact") ||
         !strcmp(kind, "message") || !strcmp(kind, "edit") ||
         !strcmp(kind, "delete") || !strcmp(kind, "read") ||
         !strcmp(kind, "reaction") || !strcmp(kind, "group") ||
         !strcmp(kind, "attachment") || !strcmp(kind, "profile");
}
static int parse(const char *plain, struct harbor_sync_event *out) {
  const char *newline = strchr(plain, '\n');
  if (!newline || (size_t)(newline - plain) >= 512 || strncmp(plain, "HS2|", 4))
    return -1;
  char header[512];
  memcpy(header, plain, (size_t)(newline - plain));
  header[newline - plain] = 0;
  char *save = NULL;
  char *version = strtok_r(header, "|", &save),
       *id = strtok_r(NULL, "|", &save), *clock = strtok_r(NULL, "|", &save),
       *person = strtok_r(NULL, "|", &save),
       *author = strtok_r(NULL, "|", &save),
       *conversation = strtok_r(NULL, "|", &save),
       *kind = strtok_r(NULL, "|", &save);
  if (!version || !id || !clock || !person || !author || !conversation ||
      !kind || strtok_r(NULL, "|", &save) || !valid_hex(id, 32) ||
      !valid_hex(clock, 16) || !valid_hex(person, 64) ||
      !valid_hex(author, 64) || !conversation_ok(conversation) ||
      !kind_ok(kind) ||
      !omaq_message_text_bytes_ok((const unsigned char *)newline + 1,
                                  strlen(newline + 1)) ||
      strlen(newline + 1) > HARBOR_APP_BODY_MAX)
    return -1;
  unsigned long long number;
  if (sscanf(clock, "%16llx", &number) != 1 || !number)
    return -1;
  char exact[512];
  int header_size = snprintf(exact, sizeof(exact), "HS2|%s|%016llx|%s|%s|%s|%s",
                             id, number, person, author, conversation, kind);
  if (header_size < 0 || (size_t)header_size != (size_t)(newline - plain) ||
      (size_t)header_size >= sizeof(exact) ||
      memcmp(exact, plain, (size_t)header_size))
    return -1;
  snprintf(out->id, sizeof(out->id), "%s", id);
  snprintf(out->person, sizeof(out->person), "%s", person);
  snprintf(out->author, sizeof(out->author), "%s", author);
  snprintf(out->conversation, sizeof(out->conversation), "%s", conversation);
  snprintf(out->kind, sizeof(out->kind), "%s", kind);
  out->clock = (uint64_t)number;
  out->text = newline + 1;
  return 0;
}
static struct harbor_devices *state(struct harbor_sync *s,
                                    const char **problem) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d) {
    *problem = "sync_unavailable";
    return NULL;
  }
  *problem = harbor_devices_operation(s->home, "device.status", s->transport,
                                      s->ratchet_key, "", "", "", "", 0, d);
  if (*problem) {
    free(d);
    return NULL;
  }
  for (size_t i = 0; i < d->count; i++)
    if (!memcmp(d->devices[i].signing, d->local, 32) && d->devices[i].active)
      return d;
  *problem = "device_revoked";
  free(d);
  return NULL;
}
static int authorized(struct harbor_sync *s, const struct harbor_devices *d,
                      const char *peer, const char *pin) {
  for (size_t i = 0; i < d->count; i++)
    if (d->devices[i].active) {
      char key[65], rk[65];
      harbor_device_hex(d->devices[i].transport, 32, key, sizeof(key));
      harbor_device_hex(d->devices[i].ratchet, 32, rk, sizeof(rk));
      if (!strcmp(key, peer) && !strcmp(rk, pin) &&
          memcmp(d->devices[i].signing, d->local, 32))
        return 1;
    }
  return s->peer_authorized && s->peer_authorized(s->application, peer, pin);
}
static int targets(struct harbor_sync *s, const struct harbor_devices *d,
                   const struct harbor_sync_event *event,
                   struct harbor_sync_target out[HARBOR_SYNC_TARGET_MAX]) {
  size_t count = 0;s->targets_incomplete=0;
  memset(out, 0, sizeof(*out) * HARBOR_SYNC_TARGET_MAX);
  for (size_t i = 0; i < d->count; i++)
    if (d->devices[i].active && memcmp(d->devices[i].signing, d->local, 32)) {
      if (count == HARBOR_SYNC_TARGET_MAX)
        return -1;
      harbor_device_hex(d->devices[i].transport, 32, out[count].transport, 65);
      harbor_device_hex(d->devices[i].ratchet, 32, out[count].ratchet, 65);
      count++;
    }
  if (s->targets) {
    int extra = s->targets(s->application, event, out + count,
                           HARBOR_SYNC_TARGET_MAX - count);
    if (extra < 0) s->targets_incomplete=1;
    else if ((size_t)extra > HARBOR_SYNC_TARGET_MAX - count) return -1;
    else count += (size_t)extra;
  }
  for (size_t i = 0; i < count; i++) {
    if (!valid_hex(out[i].transport, 64) || !valid_hex(out[i].ratchet, 64))
      return -1;
    for (size_t j = 0; j < i; j++)
      if (!strcmp(out[i].transport, out[j].transport)) {
        if (strcmp(out[i].ratchet, out[j].ratchet))
          return -1;
        memmove(out + i, out + i + 1, (count - i - 1) * sizeof(*out));
        count--;
        i--;
        break;
      }
  }
  return (int)count;
}
static void emit_item(struct harbor_sync *s, const struct harbor_sync_event *e,
                      const char *source) {
  if (strcmp(e->kind, "note"))
    return;
  char *text = malloc(HARBOR_ESC_MAX), *line = malloc(HARBOR_EVENT_MAX + 512);
  if (text && line && !omaq_json_escape(e->text, text, HARBOR_ESC_MAX)) {
    snprintf(line, HARBOR_EVENT_MAX + 512,
             "{\"event\":\"sync.item\",\"id\":\"%s\",\"conversation\":\"%s\","
             "\"author\":\"%s\",\"source\":\"%s\",\"clock\":\"%016llx\","
             "\"text\":\"%s\"}",
             e->id, e->conversation, e->author, source,
             (unsigned long long)e->clock, text);
    s->emit(line);
  }
  free(text);
  free(line);
}
void harbor_sync_close(struct harbor_sync *s) {
  harbor_journal_close(s->journal);s->journal=NULL;
  s->journal_owner[0]=0;s->replayed=0;s->importing=0;
}
static int index_event(struct harbor_sync *s,const struct harbor_sync_event *e,
                        struct harbor_journal_index *index) {
  memset(index,0,sizeof(*index));
  return s->index_event?s->index_event(s->application,e,index):0;
}
static int seal_legacy_journal(struct harbor_sync *s) {
  int fd=directory(s->home,"events");if(fd<0)return -1;
  int rc=fchmod(fd,0500) || fsync(fd);close(fd);
  return rc?-1:0;
}
static const char *ledger_buckets[]={"outbox","inbox","ack","rekey"};
static int seal_legacy_ledgers(struct harbor_sync *s) {
  for(size_t i=0;i<4;i++) {
    int fd=directory(s->home,ledger_buckets[i]);if(fd<0)return -1;
    int failed=fchmod(fd,0500) || fsync(fd);close(fd);if(failed)return -1;
  }
  return 0;
}
static int prepare_ledgers(struct harbor_sync *s) {
  int ready=harbor_journal_ledger_ready(s->journal);
  if(ready==1)return seal_legacy_ledgers(s);
  if(ready!=0 || harbor_journal_ledger_begin(s->journal))return -1;
  char *body=malloc(WIRE_MAX+80);if(!body)return -1;
  int failed=0;
  for(size_t i=0;i<4 && !failed;i++) {
    const char *bucket=ledger_buckets[i];
    int fd=directory(s->home,bucket),copy=fd<0?-1:openat(fd,".",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    DIR *dir=copy<0?NULL:fdopendir(copy);
    if(!dir){if(copy>=0)close(copy);if(fd>=0)close(fd);failed=1;break;}
    for(;;) {
      errno=0;struct dirent *entry=readdir(dir);
      if(!entry){if(errno)failed=1;break;}
      if(entry->d_name[0]=='.')continue;
      size_t length,cap=i==1?PLAIN_MAX+1:i>=2?1:WIRE_MAX+80;
      if(read_file(fd,entry->d_name,body,cap,&length)){failed=1;break;}
      if(i==0 && (strlen(entry->d_name)!=97 || strncmp(body,"HSX1|",5) ||
          length<43 || body[37]!='|' || memcmp(body+5,entry->d_name+65,32) || strncmp(body+38,"OQR1",4))) {failed=1;break;}
      if(i==1) {
        struct harbor_sync_event event;struct harbor_journal_index index;
        if(parse(body,&event) || index_event(s,&event,&index)){failed=1;break;}
      }
      if(harbor_journal_envelope_put(s->journal,bucket,entry->d_name,body,length)<0){failed=1;break;}
    }
    closedir(dir);close(fd);
  }
  free(body);
  if(failed || harbor_journal_ledger_finish(s->journal))return -1;
  return seal_legacy_ledgers(s);
}
static int ensure_journal(struct harbor_sync *s) {
  if(s->journal && harbor_journal_ready(s->journal)==1 && harbor_journal_ledger_ready(s->journal)==1)return 0;
  if(s->importing)return -1;
  harbor_sync_close(s);
  struct harbor_devices *d=calloc(1,sizeof(*d));
  if(!d)return -1;
  const char *error=harbor_devices_operation(s->home,"device.status",s->transport,
      s->ratchet_key,"","","","",0,d);
  char owner[65],head[65];unsigned char digest[32];unsigned digest_n=0;
  harbor_device_hex(d->root,32,owner,sizeof(owner));
  int hashed=!error && EVP_Digest(d->chain,d->records*HARBOR_DEVICE_RECORD_SIZE,
      digest,&digest_n,EVP_sha256(),NULL)==1 && digest_n==32;
  if(hashed)harbor_device_hex(digest,32,head,sizeof(head));
  free(d);
  if(error && !strcmp(error,"device_not_linked"))return 1;
  if(!hashed)return -1;
  s->journal=harbor_journal_open(s->home,owner);
  if(!s->journal)return -1;
  memcpy(s->journal_owner,owner,65);
  int ready=harbor_journal_ready(s->journal);
  if(ready==1){
    if(seal_legacy_journal(s) || prepare_ledgers(s) || harbor_journal_roster(s->journal,"",head)<0)goto bad;
    return 0;
  }
  if(ready!=0 || harbor_journal_begin_import(s->journal))goto bad;
  s->importing=1;
  int fd=directory(s->home,"events");
  int copy=fd<0?-1:openat(fd,".",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
  DIR *dir=copy<0?NULL:fdopendir(copy);
  char *plain=malloc(PLAIN_MAX+1);
  int failed=!dir || !plain;
  if(dir && plain) for(;;) {
    errno=0;struct dirent *entry=readdir(dir);
    if(!entry){if(errno)failed=1;break;}
    if(entry->d_name[0]=='.')continue;
    size_t length;struct harbor_sync_event e;struct harbor_journal_index index;
    int created;
    if(!valid_hex(entry->d_name,32) || read_file(fd,entry->d_name,plain,PLAIN_MAX+1,&length) ||
       parse(plain,&e) || strcmp(e.id,entry->d_name) || index_event(s,&e,&index) ||
       harbor_journal_put(s->journal,&e,plain,&index,&created)) {failed=1;break;}
  }
  free(plain);
  if(dir)closedir(dir);else if(copy>=0)close(copy);
  if(fd>=0)close(fd);
  if(failed || harbor_journal_finish_import(s->journal) || seal_legacy_journal(s))goto bad;
  s->importing=0;
  if(prepare_ledgers(s) || harbor_journal_roster(s->journal,"",head)<0)goto bad;
  return 0;
bad:
  harbor_sync_close(s);return -1;
}
/* Preserve the file engine's read convention for its callers: 0 present,
 * 1 absent, -1 unavailable. Every live envelope now has one SQLite authority. */
static int envelope_read(struct harbor_sync *s,const char *bucket,const char *name,
    char *out,size_t capacity,size_t *length) {
  *length=0;if(ensure_journal(s))return -1;
  char *body=NULL;size_t n;int found=harbor_journal_envelope_get(s->journal,bucket,name,&body,&n);
  if(found==1 && n<capacity){memcpy(out,body,n+1);*length=n;free(body);return 0;}
  free(body);return found==0?1:-1;
}
static int envelope_write(struct harbor_sync *s,const char *bucket,const char *name,
    const char *body,size_t length) {
  return ensure_journal(s)?-1:harbor_journal_envelope_put(s->journal,bucket,name,body,length);
}
int harbor_sync_roster_head(struct harbor_sync *s,const char *scope,const char *head) {
  if(ensure_journal(s))return -1;
  int changed=harbor_journal_roster(s->journal,scope,head);
  if(changed>0){s->retry=0;s->idle=0;}
  return changed<0?-1:0;
}
struct journal_walk {
  struct harbor_sync *sync;
  int list;
  void (*visitor)(const struct harbor_sync_event *,void *);
  void *context;
};
static int visit_wire(const char *plain,void *context) {
  struct journal_walk *walk=context;struct harbor_sync_event e;
  if(parse(plain,&e))return -1;
  if(walk->list==1)emit_item(walk->sync,&e,"local-replica");
  else if(walk->visitor)walk->visitor(&e,walk->context);
  else if(walk->sync->apply && walk->sync->apply(&e,1))return -1;
  return 0;
}
static int snapshot(struct harbor_sync *s,int list,uint64_t *latest,
                    const struct harbor_devices *owner,
                    void (*visitor)(const struct harbor_sync_event *,void *),
                    void *context) {
  if(ensure_journal(s))return -1;
  uint64_t own,observed;
  if(harbor_journal_clock(s->journal,&own,&observed))return -1;
  *latest=owner?own:observed;s->observed_clock=observed;
  int64_t count=harbor_journal_count(s->journal);
  if(count<0 || count>INT_MAX)return -1;
  if(list) {
    struct journal_walk walk={s,list,visitor,context};
    if(harbor_journal_visit(s->journal,NULL,visit_wire,&walk)<0)return -1;
  }
  return (int)count;
}
static void emit_state(struct harbor_sync *s,const char *request,int count) {
  char escaped[481],line[768];
  if(omaq_json_escape(request,escaped,sizeof(escaped)))return;
  int64_t pending=ensure_journal(s)?-1:harbor_journal_pending(s->journal);
  snprintf(line,sizeof(line),"{\"event\":\"sync.state\",\"request\":\"%s\",\"events\":%d,\"pending\":%lld}",escaped,count,(long long)pending);
  s->emit(line);
}
char *harbor_sync_get(struct harbor_sync *s,const char *id,
                      struct harbor_sync_event *event) {
  char *plain=NULL;
  if(!valid_hex(id,32) || ensure_journal(s) ||
     harbor_journal_get(s->journal,id,&plain)!=1)return NULL;
  if(parse(plain,event) || strcmp(event->id,id)){free(plain);return NULL;}
  return plain;
}
int harbor_sync_visit_contacts(struct harbor_sync *s,
    void (*visitor)(const struct harbor_sync_event *,void *),void *context) {
  if(ensure_journal(s))return -1;
  struct journal_walk walk={s,2,visitor,context};
  return harbor_journal_visit_contacts(s->journal,visit_wire,&walk);
}
int harbor_sync_visit(struct harbor_sync *s,
    void (*visitor)(const struct harbor_sync_event *,void *),void *context) {
  uint64_t latest;
  return snapshot(s,2,&latest,NULL,visitor,context);
}
int harbor_sync_visit_conversation(struct harbor_sync *s,const char *other,
    void (*visitor)(const struct harbor_sync_event *,void *),void *context) {
  if(!valid_hex(other,64) || ensure_journal(s))return -1;
  struct journal_walk walk={s,2,visitor,context};
  return harbor_journal_visit(s->journal,other,visit_wire,&walk);
}
int harbor_sync_find_request(struct harbor_sync *s,const char *person,
    const char *author,int request_class,const char *request,char id[33]) {
  id[0]=0;
  return ensure_journal(s)?-1:harbor_journal_request(s->journal,person,author,request_class,request,id);
}
int harbor_sync_content_id(const struct harbor_sync_event *e, char id[33]) {
  char *input = malloc(PLAIN_MAX + 64);
  if (!input)
    return -1;
  int n =
      snprintf(input, PLAIN_MAX + 64, "Harbor-event-v1|%016llx|%s|%s|%s|%s\n%s",
               (unsigned long long)e->clock, e->person, e->author,
               e->conversation, e->kind, e->text);
  unsigned char hash[32];
  unsigned length;
  int rc = n < 0 || (size_t)n >= PLAIN_MAX + 64 ||
                   EVP_Digest(input, (size_t)n, hash, &length, EVP_sha256(),
                              NULL) != 1 ||
                   length != 32 || harbor_device_hex(hash, 16, id, 33)
               ? -1
               : 0;
  free(input);
  return rc;
}
static const char *publish(struct harbor_sync *s, const char *requested,
                           char generated[33], const char *conversation,
                           const char *kind, const char *body, int *created) {
  *created = 0;
  if ((requested && !valid_hex(requested, 32)) ||
      !conversation_ok(conversation) || !kind_ok(kind) || !body || !body[0] ||
      strlen(body) > HARBOR_APP_BODY_MAX ||
      !omaq_message_text_bytes_ok((const unsigned char *)body, strlen(body)))
    return "sync_event_invalid";
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d)
    return problem;
  uint64_t latest,observed;
  if(ensure_journal(s) || harbor_journal_clock(s->journal,&latest,&observed) ||
     latest==UINT64_MAX) {
    free(d);
    return "sync_state_invalid";
  }
  s->observed_clock=observed;
  char *plain=malloc(PLAIN_MAX+1),author[65],person[65];
  if(!plain){free(d);return "sync_unavailable";}
  harbor_device_hex(d->local,32,author,sizeof(author));
  harbor_device_hex(d->root,32,person,sizeof(person));
  char *prior=NULL;
  int existing=requested?harbor_journal_get(s->journal,requested,&prior):0;
  if(existing==1) {
    struct harbor_sync_event e;struct harbor_journal_index index;
    int same=!parse(prior,&e) && !strcmp(e.person,person) && !strcmp(e.author,author) &&
      !strcmp(e.conversation,conversation) && !strcmp(e.kind,kind) && !strcmp(e.text,body);
    int ignored;
    int durable=same && !index_event(s,&e,&index) &&
      !harbor_journal_put(s->journal,&e,prior,&index,&ignored);
    int projected=durable && s->apply?s->apply(&e,0):0;
    if(durable && !projected && !strcmp(e.kind,"contact"))
      projected=harbor_journal_projected(s->journal,e.id);
    free(prior);free(plain);free(d);
    return !same?"sync_event_conflict":!durable?"sync_persist_failed":
      projected?"sync_projection_failed":NULL;
  }
  if(existing<0){free(prior);free(plain);free(d);return "sync_state_invalid";}
  /* Preserve normal Lamport causality while bounding a foreign contact's
   * ability to push this identity's clock towards integer exhaustion. */
  uint64_t advance =
      s->observed_clock > latest ? s->observed_clock - latest : 0;
  if (advance > UINT64_C(1048576))
    advance = UINT64_C(1048576);
  if (advance > UINT64_MAX - latest - 1)
    advance = UINT64_MAX - latest - 1;
  uint64_t next = latest + advance + 1;
  char id[33];
  if (requested)
    memcpy(id, requested, sizeof(id));
  else {
    struct harbor_sync_event e = {0};
    memcpy(e.person, person, 65);
    memcpy(e.author, author, 65);
    e.clock = next;
    e.text = body;
    snprintf(e.conversation, sizeof(e.conversation), "%s", conversation);
    snprintf(e.kind, sizeof(e.kind), "%s", kind);
    if (harbor_sync_content_id(&e, id)) {
      free(plain);
      free(d);
      return "sync_event_invalid";
    }
    memcpy(generated, id, 33);
  }
  int size = snprintf(plain, PLAIN_MAX + 1, "HS2|%s|%016llx|%s|%s|%s|%s\n%s",
                      id, (unsigned long long)next, person, author,
                      conversation, kind, body);
  struct harbor_sync_event stored;struct harbor_journal_index index;
  int fresh=0;
  int result=size<0 || (size_t)size>PLAIN_MAX || parse(plain,&stored) ||
    index_event(s,&stored,&index) ||
    harbor_journal_put(s->journal,&stored,plain,&index,&fresh)?-1:fresh;
  free(d);
  if (result < 0) {
    free(plain);
    return "sync_persist_failed";
  }
  struct harbor_sync_event e;
  if (parse(plain, &e)) {
    free(plain);
    return "sync_state_invalid";
  }
  *created = result > 0;
#ifdef HARBOR_SYNC_FAULTS
  const char *point=getenv("HARBOR_SYNC_CRASH_AT");
  const char *contact_crash=getenv("HARBOR_SYNC_CRASH_CONTACT_FILE");
  if(*created && !strcmp(e.kind,"contact") && contact_crash && !access(contact_crash,F_OK))_exit(78);
  if(*created && point && !strcmp(point,"after-local-action") &&
     (!strcmp(e.kind,"edit") || !strcmp(e.kind,"delete") ||
      !strcmp(e.kind,"reaction") || !strcmp(e.kind,"read")))_exit(78);
#endif
  if (*created) {
    if (s->apply && s->apply(&e, 1)) {
      free(plain);
      return "sync_projection_failed";
    }
    if(!strcmp(e.kind,"contact") && harbor_journal_projected(s->journal,e.id)) {
      free(plain);return "sync_projection_failed";
    }
    emit_item(s, &e, "local");
  }
  free(plain);
  if(s->idle){s->retry=0;s->idle=0;}
  return NULL;
}
const char *harbor_sync_publish(struct harbor_sync *s, const char *id,
                                const char *conversation, const char *kind,
                                const char *body, int *created) {
  return publish(s, id, NULL, conversation, kind, body, created);
}
const char *harbor_sync_publish_canonical(struct harbor_sync *s,
                                          const char *conversation,
                                          const char *kind, const char *body,
                                          char id[33], int *created) {
  return publish(s, NULL, id, conversation, kind, body, created);
}
#ifdef HARBOR_SYNC_FAULTS
static int encrypt(struct harbor_sync *s, const char *peer, const char *plain,
                   char *out, size_t size);
#endif
void harbor_sync_operation(struct harbor_sync *s, const omaq_op *op) {
  if (!omaq_message_id_ok(op->request)) {
    error(s, op->request, "request_required");
    return;
  }
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d) {
    error(s, op->request, problem);
    return;
  }
#ifdef HARBOR_SYNC_FAULTS
  if (!strcmp(op->op, "sync.inject")) {
    char pin[65];
    int allowed = valid_hex(op->key, 64) && valid_hex(op->id, 32) &&
                  op->has_text && !s->pin(op->key, pin) &&
                  (!strcmp(op->kind, "legacy") || authorized(s, d, op->key, pin));
    free(d);
    char stored[67];
    snprintf(stored,sizeof(stored),"d:%s",op->key);
    char *cipher = malloc(WIRE_MAX + 1), *wire = malloc(WIRE_MAX + 80);
    if (!allowed || !cipher || !wire ||
        (!strcmp(op->kind,"legacy")
          ? omaq_ratchet_encrypt(s->ratchet,stored,op->text,cipher,WIRE_MAX+1)
          : encrypt(s, op->key, op->text, cipher, WIRE_MAX + 1)))
      error(s, op->request, "sync_inject_failed");
    else {
      int n = !strcmp(op->kind, "legacy")
          ? snprintf(wire, WIRE_MAX + 80, "%s", cipher)
          : snprintf(wire, WIRE_MAX + 80, "HSX1|%s|%s", op->id, cipher);
      if (n < 0 || (size_t)n >= WIRE_MAX + 80 || s->send(op->key, wire))
        error(s, op->request, "sync_inject_failed");
      else {
        char line[256];
        snprintf(line, sizeof(line),
                 "{\"event\":\"sync.injected\",\"id\":\"%s\"}", op->id);
        s->emit(line);
      }
    }
    free(cipher);
    free(wire);
    return;
  }
#endif
  free(d);
  if (!strcmp(op->op, "sync.publish")) {
    if (!op->has_text || strlen(op->text) > HARBOR_TEXT_MAX) {
      error(s, op->request, "sync_event_invalid");
      return;
    }
    int created;
    problem = harbor_sync_publish(s, op->id, op->conversation,
                                  op->kind[0] ? op->kind : "note", op->text,
                                  &created);
    if (problem) {
      error(s, op->request, problem);
      return;
    }
  } else if (strcmp(op->op, "sync.status") && strcmp(op->op, "sync.list")) {
    error(s, op->request, "sync_operation_unsupported");
    return;
  }
  uint64_t latest;
  int count =
      snapshot(s, !strcmp(op->op, "sync.list"), &latest, NULL, NULL, NULL);
  if (count < 0)
    error(s, op->request, "sync_state_invalid");
  else
    emit_state(s, op->request, count);
}
static int hash(const char *text, char out[65]) {
  unsigned char digest[32];
  unsigned n;
  return EVP_Digest(text, strlen(text), digest, &n, EVP_sha256(), NULL) == 1 &&
                 n == 32
             ? harbor_device_hex(digest, 32, out, 65)
             : -1;
}
struct inbox_commit {
  char name[131], expected[33];
  struct harbor_sync *sync;
  const char *peer, *pin;
};
static int commit_inbox(void *context, const unsigned char *bytes,
                        size_t length) {
  struct inbox_commit *commit = context;
  if (length > PLAIN_MAX || memchr(bytes, 0, length))
    return -1;
  char *plain = malloc(length + 1);
  if (!plain)
    return -1;
  memcpy(plain, bytes, length);
  plain[length] = 0;
  struct harbor_sync_event e;struct harbor_journal_index index;
  int rc = (parse(plain, &e) || strcmp(e.id, commit->expected) || index_event(commit->sync,&e,&index) ||
            (commit->sync->accept_event &&
             !commit->sync->accept_event(commit->sync->application,
                                         commit->peer, commit->pin, &e)))
               ? -1
               : envelope_write(commit->sync,"inbox",commit->name,plain,length);
  free(plain);
#ifdef HARBOR_SYNC_FAULTS
  const char *point = getenv("HARBOR_SYNC_CRASH_AT");
  if (rc >= 0 && point && !strcmp(point, "after-inbox"))
    _exit(78);
#endif
  return rc < 0 ? -1 : 0;
}
static int encrypt(struct harbor_sync *s, const char *peer, const char *plain,
                   char *wire, size_t n) {
  char pin[65];
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d)
    return -1;
  int allowed = s->pin && s->pin(peer, pin) == 0 && authorized(s, d, peer, pin);
  free(d);
  if (!allowed)
    return -1;
  char stored[67];
  snprintf(stored, sizeof(stored), "d:%s", peer);
  return omaq_ratchet_encrypt(s->ratchet, stored, plain, wire, n);
}
int harbor_sync_receive(struct harbor_sync *s, const char *peer,
                        const char *pin, const char *wire) {
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d)
    return 0;
  int allowed = authorized(s, d, peer, pin);
  free(d);
  if (!allowed || ensure_journal(s))
    return 0;
  /* Outer id is not trusted; it is checked against authenticated plaintext. */
  if (strncmp(wire, "HSX1|", 5) || strlen(wire) < 43 || wire[37] != '|')
    return 0;
  char id[33];
  memcpy(id, wire + 5, 32);
  id[32] = 0;
  if (!valid_hex(id, 32))
    return 0;
  const char *cipher = wire + 38;
  if (strncmp(cipher, "OQR1", 4) || strlen(cipher) > WIRE_MAX)
    return 0;
  struct inbox_commit transaction;
  char digest[65];
  if (hash(cipher, digest))return 0;
  snprintf(transaction.name, sizeof(transaction.name), "%s.%s", peer, digest);
  memcpy(transaction.expected, id, sizeof(id));
  transaction.sync = s;
  transaction.peer = peer;
  transaction.pin = pin;
  char *plain = malloc(PLAIN_MAX + 1);
  size_t n = 0;
  if (!plain)return 0;
  int outcome = 0;
  int cached = envelope_read(s,"inbox",transaction.name,plain,PLAIN_MAX+1,&n);
  if (cached == 1) {
    char stored[67];
    snprintf(stored, sizeof(stored), "d:%s", peer);
    if (!omaq_ratchet_has_session(s->ratchet, stored)) {
      outcome = OMAQ_RATCHET_DECRYPT_RECOVER;
      goto done;
    }
    int decrypted = omaq_ratchet_decrypt_durable(s->ratchet, stored, cipher,
                                                 plain, PLAIN_MAX + 1, &n,
                                                 commit_inbox, &transaction);
    if (decrypted) {
      outcome = decrypted;
      goto done;
    }
  } else if (cached < 0)
    goto done;
  struct harbor_sync_event e;
  if (parse(plain, &e) || strcmp(id, e.id) ||
      (s->accept_event && !s->accept_event(s->application, peer, pin, &e)))
    goto done;
  struct harbor_journal_index index;int result=0;
  if(ensure_journal(s) || index_event(s,&e,&index) ||
     harbor_journal_put(s->journal,&e,plain,&index,&result))goto done;
  /* Journaled contact projection can fail independently. A retransmission must
   * retry it before acknowledging; message notifications remain new-only. */
  if (s->apply && s->apply(&e, result > 0))
    goto done;
  if(!strcmp(e.kind,"contact") && harbor_journal_projected(s->journal,e.id))goto done;
  if(s->idle){s->retry=0;s->idle=0;}
  if (result > 0)
    emit_item(s, &e, peer);
  char ack[64], encrypted[1024];
  snprintf(ack, sizeof(ack), "HSA1|%s", e.id);
  if (!encrypt(s, peer, ack, encrypted, sizeof(encrypted)))
    (void)s->send(peer, encrypted);
done:
  free(plain);
  return outcome;
}
#ifdef HARBOR_SYNC_FAULTS
int harbor_sync_outbox_pending(struct harbor_sync *s, const char *peer) {
  return !ensure_journal(s) && harbor_journal_envelope_count(s->journal,"outbox",peer)>0;
}
#endif
int harbor_sync_session_begin(struct harbor_sync *s, const char *peer,
                              const char *pin) {
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d)
    return 0;
  int allowed = authorized(s, d, peer, pin);
  free(d);
  if (!allowed)
    return 0;
  return envelope_write(s,"rekey",peer,"",0)<0?-1:0;
}

void harbor_sync_session_changed(struct harbor_sync *s, const char *peer,
                                 const char *pin) {
  const char *problem = NULL;
  struct harbor_devices *d = state(s, &problem);
  if (!d)
    return;
  int allowed = authorized(s, d, peer, pin);
  free(d);
  if (!allowed)
    return;
  if(ensure_journal(s) || harbor_journal_envelope_rekey(s->journal,peer))
    error(s,"session-recovery","sync_persist_failed");
  s->retry=0;
}
/* ACKs arrive inside the ordinary authenticated Ratchet stream. */
int harbor_sync_is_acknowledged(struct harbor_sync *s,const char *peer,const char *id) {
  if(!valid_hex(peer,64) || !valid_hex(id,32))return -1;
  char name[99],empty[1];size_t length;
  snprintf(name,sizeof(name),"%s.%s",peer,id);
  int found=envelope_read(s,"ack",name,empty,sizeof(empty),&length);
  return found<0?-1:found==0?1:0;
}
void harbor_sync_ack(struct harbor_sync *s,const char *peer,const char *pin,const char *id) {
  if(!valid_hex(id,32))return;
  const char *problem=NULL;struct harbor_devices *d=state(s,&problem);
  if(!d)return;
  int allowed=authorized(s,d,peer,pin);free(d);
  if(!allowed || ensure_journal(s))return;
  char name[99],*body=NULL;size_t length;
  snprintf(name,sizeof(name),"%s.%s",peer,id);
  int found=harbor_journal_envelope_get(s->journal,"outbox",name,&body,&length);
  free(body);if(found!=1)return;
  if(envelope_write(s,"ack",name,"",0)>=0) {
    (void)harbor_journal_envelope_drop(s->journal,"outbox",name);
    if(s->acknowledged)s->acknowledged(s->application,peer,id);
  }
}
static int64_t sync_millis(void) {
  struct timespec value;
  return clock_gettime(CLOCK_MONOTONIC,&value)?-1:
    (int64_t)value.tv_sec*1000+value.tv_nsec/1000000;
}
void harbor_sync_tick(struct harbor_sync *s) {
  int64_t now=sync_millis();if(now<0 || now<s->retry)return;
  s->retry=now+25;
  int journal_state=ensure_journal(s);
  if(journal_state){
    s->retry=now+1000;
    /* An unlinked installation has no replicated journal yet. Retry after
     * setup, but keep actual storage/authorization failures visible. */
    if(journal_state<0)error(s,"replication","sync_state_invalid");
    return;
  }
  struct harbor_journal_work work[16];
  int count=harbor_journal_work_batch(s->journal,work,16);
  if(count<0){s->retry=now+1000;error(s,"replication","sync_state_invalid");return;}
  if(!count){s->idle=1;s->retry=now+250;return;}
  s->idle=0;
  const char *problem=NULL;struct harbor_devices *d=state(s,&problem);
  if(!d){s->retry=now+1000;return;}
  char *cipher=malloc(WIRE_MAX+1),*wire=malloc(WIRE_MAX+80);
  if(!cipher || !wire)goto done;
  /* Envelope writes must commit before network/Signal effects. Collect queue
   * outcomes first, then commit this derived work batch separately. */
  int failed=0,processed=0,complete_flags[16]={0};unsigned packets=0;
  for(int k=0;k<count;k++) {
    if(k && (packets>=16 || sync_millis()-now>=10))break;
    struct harbor_sync_event event;
    char *plain=NULL;
    if(harbor_journal_get(s->journal,work[k].id,&plain)!=1 || parse(plain,&event)) {
      free(plain);failed=1;break;
    }
    int projected=work[k].projected;
    if(!projected) {
      s->replaying=1;
      projected=!s->apply || !s->apply(&event,0);
      s->replaying=0;
    }
    struct harbor_sync_target destination[HARBOR_SYNC_TARGET_MAX];
    int n=targets(s,d,&event,destination),incomplete=s->targets_incomplete;
    if(n<0){free(plain);failed=1;break;}
    unsigned cursor=n?work[k].cursor%(unsigned)n:0;
    int complete=!incomplete && projected;
    int acknowledged[HARBOR_SYNC_TARGET_MAX]={0};
    for(int i=0;i<n;i++) {
      char name[99],empty[1];size_t length;
      snprintf(name,sizeof(name),"%.64s.%.32s",destination[i].transport,event.id);
      int present=envelope_read(s,"ack",name,empty,sizeof(empty),&length);
      if(present<0){acknowledged[i]=-1;complete=0;}
      else if(!present) {
        acknowledged[i]=1;
        if(harbor_journal_envelope_drop(s->journal,"outbox",name))complete=0;
      }
      else complete=0;
      if(destination[i].blocked)complete=0;
    }
    unsigned start_cursor=cursor;
    if(!complete)for(int j=0;j<n;j++) {
      unsigned i=(start_cursor+(unsigned)j)%(unsigned)n;
      if(acknowledged[i] || destination[i].blocked)continue;
      if(packets>=16 || (packets && sync_millis()-now>=10)){cursor=i;break;}
      const char *peer=destination[i].transport;
      if(s->available && !s->available(peer))continue;
      char pin[65],name[99],empty[1];size_t length;
      if(s->pin(peer,pin) || strcmp(pin,destination[i].ratchet))continue;
      int intent=envelope_read(s,"rekey",peer,empty,sizeof(empty),&length);
      if(intent<0)continue;
      if(!intent){harbor_sync_session_changed(s,peer,pin);continue;}
      snprintf(name,sizeof(name),"%s.%s",peer,event.id);
      int existing=envelope_read(s,"outbox",name,wire,WIRE_MAX+80,&length);
      if(existing<0){error(s,"replication","sync_outbox_invalid");continue;}
      if(existing==1) {
        if(encrypt(s,peer,plain,cipher,WIRE_MAX+1))continue;
        int size=snprintf(wire,WIRE_MAX+80,"HSX1|%s|%s",event.id,cipher);
        if(size<0 || (size_t)size>=WIRE_MAX+80 ||
           envelope_write(s,"outbox",name,wire,(size_t)size)<0) {
          error(s,"replication","sync_persist_failed");continue;
        }
      }
      (void)s->send(peer,wire);packets++;cursor=(i+1)%(unsigned)n;
    }
    work[k].cursor=cursor;work[k].projected=projected;complete_flags[k]=complete;
    processed=k+1;free(plain);
  }
  if(!failed && processed) {
    if(harbor_journal_work_begin(s->journal))failed=1;
    for(int k=0;!failed && k<processed;k++)
      if(harbor_journal_work_update(s->journal,work[k].id,work[k].cursor,work[k].projected,complete_flags[k]))failed=1;
    if(!failed && harbor_journal_work_commit(s->journal))failed=1;
  }
  if(failed) {
    harbor_sync_close(s);s->retry=now+1000;
    error(s,"replication","sync_state_invalid");
  }
done:
  free(cipher);free(wire);free(d);
}

#endif
