#define _DEFAULT_SOURCE
#include "person_chat.h"
#ifdef HAVE_SIGNAL
#include "devices.h"
#include "message.h"
#include "people.h"
#include "message_action.h"
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define RESPONSE_MAX (HARBOR_EVENT_MAX - 1024u)
struct app_message {
  char origin[65], target[65], id[33], reply[97], request[80];
  int64_t timestamp;
  const char *text;
};
struct row {
  char id[33], reply[97], origin[65], event[33];
  uint64_t clock;
  int64_t timestamp;
  char edit[33], reaction_me[32], reaction_peer[32];
  int deleted, read;
};
struct model {
  struct harbor_person_chat *chat;
  const char *other;
  struct row *rows;
  size_t count,capacity;
  int failed;
};
static int hex_ok(const char *text, size_t n) {
  if (strlen(text) != n)
    return 0;
  for (size_t i = 0; i < n; i++)
    if (!(text[i] >= '0' && text[i] <= '9') &&
        !(text[i] >= 'a' && text[i] <= 'f'))
      return 0;
  return 1;
}
static int parse(const struct harbor_sync_event *event,
                 struct app_message *out) {
  if (strcmp(event->kind, "message"))
    return -1;
  char canonical[33];
  if (harbor_sync_content_id(event, canonical) || strcmp(canonical, event->id))
    return -1;
  const char *newline = strchr(event->text, '\n');
  if (!newline || (size_t)(newline - event->text) >= 512)
    return -1;
  char header[512];
  memcpy(header, event->text, (size_t)(newline - event->text));
  header[newline - event->text] = 0;
  char *save = NULL, *version = strtok_r(header, "|", &save),
       *origin = strtok_r(NULL, "|", &save),
       *target = strtok_r(NULL, "|", &save),
       *reply = strtok_r(NULL, "|", &save),
       *request = strtok_r(NULL, "|", &save),
       *timestamp = strtok_r(NULL, "|", &save);
  if (!version || strcmp(version, "HM2") || !origin || !target || !reply ||
      !request || !timestamp || strtok_r(NULL, "|", &save) ||
      !hex_ok(origin, 64) || strcmp(origin, event->person) ||
      !hex_ok(target, 64) || !strcmp(origin, target) ||
      (strcmp(reply, "-") &&
       (!omaq_message_id_ok(reply) || strlen(reply) > 96)) ||
      (strcmp(request, "-") &&
       (!omaq_message_id_ok(request) || strlen(request) >= 80)) ||
      !hex_ok(timestamp, 16) || strlen(newline + 1) > HARBOR_TEXT_MAX ||
      !omaq_message_text_bytes_ok((const unsigned char *)newline + 1,
                                  strlen(newline + 1)))
    return -1;
  char conversation[67];
  snprintf(conversation, sizeof(conversation), "p:%s", target);
  if (strcmp(conversation, event->conversation))
    return -1;
  unsigned long long seconds;
  if (sscanf(timestamp, "%16llx", &seconds) != 1 || !seconds ||
      seconds > UINT64_C(253402300799))
    return -1;
  memcpy(out->origin, origin, 65);
  memcpy(out->target, target, 65);
  memcpy(out->id, event->id, 33);
  snprintf(out->reply, sizeof(out->reply), "%s",
           strcmp(reply, "-") ? reply : "");
  snprintf(out->request, sizeof(out->request), "%s",
           strcmp(request, "-") ? request : "");
  out->timestamp = (int64_t)seconds;
  out->text = newline + 1;
  return 0;
}
/* Mutations are immutable person events. Authorization uses their actor and
 * conversation; projection separately binds the referenced message's origin. */
struct app_action {
  struct app_message route;
  char original[65], message[33], request[80];
};
static int parse_action(const struct harbor_sync_event *event,
                        struct app_action *out) {
  if (strcmp(event->kind, "edit") && strcmp(event->kind, "delete") &&
      strcmp(event->kind, "reaction") && strcmp(event->kind, "read")) return -1;
  char canonical[33], header[512], exact[512];
  const char *newline = strchr(event->text, '\n');
  if (harbor_sync_content_id(event, canonical) || strcmp(canonical, event->id) ||
      !newline || (size_t)(newline-event->text) >= sizeof(header)) return -1;
  memcpy(header, event->text, (size_t)(newline-event->text));
  header[newline-event->text] = 0;
  char *save=NULL, *version=strtok_r(header,"|",&save),
       *actor=strtok_r(NULL,"|",&save), *target=strtok_r(NULL,"|",&save),
       *original=strtok_r(NULL,"|",&save), *message=strtok_r(NULL,"|",&save),
       *request=strtok_r(NULL,"|",&save);
  if (!version || strcmp(version,"HA1") || !actor || !target || !original ||
      !message || !request || strtok_r(NULL,"|",&save) ||
      !hex_ok(actor,64) || strcmp(actor,event->person) || !hex_ok(target,64) ||
      !strcmp(actor,target) || !hex_ok(original,64) || !hex_ok(message,32) ||
      !omaq_message_id_ok(request) || strlen(request)>=80 ||
      (strcmp(original,actor) && strcmp(original,target))) return -1;
  snprintf(exact,sizeof(exact),"HA1|%s|%s|%s|%s|%s",actor,target,original,message,request);
  if (strlen(exact)!=(size_t)(newline-event->text) ||
      memcmp(exact,event->text,strlen(exact))) return -1;
  char conversation[67];snprintf(conversation,sizeof(conversation),"p:%s",target);
  if (strcmp(conversation,event->conversation)) return -1;
  const char *body=newline+1;
  if ((!strcmp(event->kind,"edit") &&
       (strcmp(actor,original) || strlen(body)>HARBOR_TEXT_MAX ||
        !omaq_message_text_bytes_ok((const unsigned char *)body,strlen(body)))) ||
      (!strcmp(event->kind,"delete") && (strcmp(actor,original) || *body)) ||
      (!strcmp(event->kind,"read") && (strcmp(target,original) || *body)) ||
      (!strcmp(event->kind,"reaction") && *body && !omaq_message_reaction_ok(body))) return -1;
  memset(out,0,sizeof(*out));
  memcpy(out->route.origin,actor,65);memcpy(out->route.target,target,65);
  memcpy(out->original,original,65);memcpy(out->message,message,33);
  snprintf(out->request,sizeof(out->request),"%s",request);
  out->route.text=body;
  return 0;
}
static int parse_route(const struct harbor_sync_event *event, struct app_message *out) {
  if (!parse(event,out)) return 0;
  struct app_action action;
  if (parse_action(event,&action)) return -1;
  *out=action.route;
  return 0;
}
int harbor_person_chat_index(void *context,const struct harbor_sync_event *event,
                              struct harbor_journal_index *index) {
  struct harbor_person_chat *chat=context;
  memset(index,0,sizeof(*index));
  if(!strcmp(event->kind,"note"))return strcmp(event->person,chat->own)?-1:0;
  if(!strcmp(event->kind,"contact")) {
    if(strcmp(event->person,chat->own))return -1;
    struct harbor_devices *d=calloc(1,sizeof(*d));char name[129];
    int valid=d && !harbor_people_card_decode(event->text,d,name);
    free(d);return valid?0:-1;
  }
  struct app_message message;
  if(!parse(event,&message)) {
    if(strcmp(message.origin,chat->own) && strcmp(message.target,chat->own))return -1;
    memcpy(index->origin,message.origin,65);memcpy(index->target,message.target,65);
    snprintf(index->request,sizeof(index->request),"%s",message.request);
    index->request_class=1;
    return 0;
  }
  struct app_action action;
  if(parse_action(event,&action) ||
     (strcmp(action.route.origin,chat->own) && strcmp(action.route.target,chat->own)))return -1;
  memcpy(index->origin,action.route.origin,65);memcpy(index->target,action.route.target,65);
  memcpy(index->related,action.message,33);
  snprintf(index->request,sizeof(index->request),"%s",action.request);
  index->request_class=2;
  return 0;
}
void harbor_person_chat_bind(struct harbor_person_chat *chat,
                             struct harbor_sync *sync) {
  chat->sync = sync;
  chat->own[0] = chat->local[0] = 0;
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return;
  if (!harbor_devices_operation(sync->home, "device.status", sync->transport,
                                sync->ratchet_key, "", "", "", "", 0, d)) {
    harbor_device_hex(d->root, 32, chat->own, sizeof(chat->own));
    if(sync->journal && strcmp(sync->journal_owner,chat->own))harbor_sync_close(sync);
    harbor_device_hex(d->local, 32, chat->local, sizeof(chat->local));
  }
  free(d);
}
int harbor_person_chat_peer(void *context, const char *peer, const char *pin) {
  struct harbor_person_chat *chat = context;
  char root[65];
  if (!chat->own[0])
    return 0;
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return 0;
  int valid = harbor_people_find(chat->sync->home, peer, pin, root, d) == 1;
  free(d);
  return valid;
}
static int own_peer(struct harbor_person_chat *chat, const char *peer,
                    const char *pin) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return 0;
  int valid = 0;
  if (!harbor_devices_operation(chat->sync->home, "device.status",
                                chat->sync->transport, chat->sync->ratchet_key,
                                "", "", "", "", 0, d))
    for (size_t i = 0; i < d->count; i++)
      if (d->devices[i].active) {
        char key[65], rk[65];
        harbor_device_hex(d->devices[i].transport, 32, key, sizeof(key));
        harbor_device_hex(d->devices[i].ratchet, 32, rk, sizeof(rk));
        if (!strcmp(key, peer) && !strcmp(rk, pin))
          valid = 1;
      }
  free(d);
  return valid;
}
static int reserved_author(struct harbor_person_chat *chat,
                           const char *author) {
  struct harbor_devices *own = calloc(1, sizeof(*own));
  if (!own)
    return 1;
  int reserved = 1;
  if (!harbor_devices_operation(chat->sync->home, "device.status",
                                chat->sync->transport, chat->sync->ratchet_key,
                                "", "", "", "", 0, own)) {
    reserved = 0;
    for (size_t i = 0; i < own->count; i++) {
      char key[65];
      harbor_device_hex(own->devices[i].signing, 32, key, sizeof(key));
      if (!strcmp(author, key))
        reserved = 1;
    }
  }
  free(own);
  return reserved;
}
int harbor_person_chat_accept(void *context, const char *peer, const char *pin,
                              const struct harbor_sync_event *event) {
  struct harbor_person_chat *chat = context;
  if (strcmp(event->person, chat->own) && reserved_author(chat, event->author))
    return 0;
  if (own_peer(chat, peer, pin)) {
    /* Currently authorized siblings may import previously accepted history.
     * This is synchronization provenance, not a remote public signature. */
    if (!strcmp(event->kind, "contact") || !strcmp(event->kind, "note"))
      return !strcmp(event->person, chat->own);
    struct app_message message;
    return !parse_route(event, &message) && (!strcmp(message.origin, chat->own) ||
                                       !strcmp(message.target, chat->own));
  }
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return 0;
  struct app_message message;
  char root[65];
  int valid = 0;
  if (harbor_people_find(chat->sync->home, peer, pin, root, d) == 1 &&
      parse_route(event, &message) == 0 && !strcmp(message.origin, root) &&
      !strcmp(message.target, chat->own)) {
    /* An active device endorses its person's historical device label. A
     * revoked physical source is rejected before decryption by the engine. */
    for (size_t i = 0; i < d->count; i++) {
      char key[65];
      harbor_device_hex(d->devices[i].signing, 32, key, sizeof(key));
      if (!strcmp(key, event->author))
        valid = 1;
    }
  }
  free(d);
  return valid;
}
int harbor_person_chat_targets(void *context,
                               const struct harbor_sync_event *event,
                               struct harbor_sync_target *out,
                               size_t capacity) {
  struct harbor_person_chat *chat = context;
  struct app_message message;
  if (parse_route(event, &message) || strcmp(message.origin, chat->own))
    return 0;
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return -1;
  if (harbor_people_get(chat->sync->home, message.target, d, NULL)) {
    free(d);
    return -1;
  }
  size_t count = 0;
  struct harbor_devices *endorsed = calloc(1, sizeof(*endorsed));
  if (!endorsed) {
    free(d);
    return -1;
  }
  for (size_t i = 0; i < d->count; i++)
    if (d->devices[i].active) {
      char transport[65], pin[65], root[65];
      harbor_device_hex(d->devices[i].transport, 32, transport, 65);
      harbor_device_hex(d->devices[i].ratchet, 32, pin, 65);
      int blocked = harbor_people_find(chat->sync->home, transport, pin, root,
                                       endorsed) != 1 ||
                    strcmp(root, message.target);
      if (count == capacity) {
        free(endorsed);
        free(d);
        return -1;
      }
      out[count].blocked = blocked;
      memcpy(out[count].transport, transport, 65);
      memcpy(out[count].ratchet, pin, 65);
      count++;
    }
  free(endorsed);
  free(d);
  return count ? (int)count : -1;
}
static void collect(const struct harbor_sync_event *event, void *context) {
  struct model *model = context;
  if(model->failed)return;
  struct app_message message;
  if (parse(event, &message))
    return;
  const char *own = model->chat->own, *other = model->other;
  if (!((!strcmp(message.origin, own) && !strcmp(message.target, other)) ||
        (!strcmp(message.origin, other) && !strcmp(message.target, own))))
    return;
  /* The authoritative journal has a unique immutable ID primary key. */
  if(model->failed)return;
  if(model->count==model->capacity) {
    size_t capacity=model->capacity?model->capacity*2:128;
    if(capacity<model->capacity || capacity>SIZE_MAX/sizeof(*model->rows)) {
      model->failed=1;return;
    }
    struct row *rows=realloc(model->rows,capacity*sizeof(*rows));
    if(!rows){model->failed=1;return;}
    model->rows=rows;model->capacity=capacity;
  }
  struct row *row = &model->rows[model->count++];
  memset(row,0,sizeof(*row));
  memcpy(row->id, message.id, 33);
  memcpy(row->reply, message.reply, 97);
  memcpy(row->origin, message.origin, 65);
  memcpy(row->event, event->id, 33);
  row->clock = event->clock;
  row->timestamp = message.timestamp;
}
static void project_action(const struct harbor_sync_event *event, void *context) {
  struct model *model=context;struct app_action action;
  if (parse_action(event,&action)) return;
  const char *own=model->chat->own,*other=model->other;
  if (!((!strcmp(action.route.origin,own) && !strcmp(action.route.target,other)) ||
        (!strcmp(action.route.origin,other) && !strcmp(action.route.target,own)))) return;
  struct row *referenced=NULL;
  for(size_t i=0;i<model->count;i++)
    if(!strcmp(model->rows[i].id,action.message) &&
       !strcmp(model->rows[i].origin,action.original)) referenced=&model->rows[i];
  if(!referenced)return;
  if(!strcmp(event->kind,"read")) {
    size_t through=(size_t)(referenced-model->rows);
    for(size_t i=0;i<=through;i++)
      if(!strcmp(model->rows[i].origin,action.original))model->rows[i].read=1;
  } else if(!strcmp(event->kind,"delete")) referenced->deleted=1;
  else if(!strcmp(event->kind,"edit"))memcpy(referenced->edit,event->id,33);
  else {
    char *reaction=!strcmp(action.route.origin,own)?referenced->reaction_me:referenced->reaction_peer;
    snprintf(reaction,32,"%s",action.route.text);
  }
}
static void free_model(struct model *model) {
  if(model){free(model->rows);free(model);}
}
static struct model *load_model(struct harbor_person_chat *chat,
                                const char *other) {
  struct model *model = calloc(1, sizeof(*model));
  if (!model)
    return NULL;
  model->chat = chat;
  model->other = other;
  if (harbor_sync_visit_conversation(chat->sync,other,collect,model) < 0 || model->failed ||
      harbor_sync_visit_conversation(chat->sync,other,project_action,model) < 0) {
    free_model(model);
    return NULL;
  }
  return model;
}
static int delivered(struct harbor_person_chat *chat, const char *target,
                     const char *id) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return 0;
  int result = 0;
  if (!harbor_people_get(chat->sync->home, target, d, NULL))
    for (size_t i = 0; i < d->count; i++) {
      char peer[65];
      harbor_device_hex(d->devices[i].transport, 32, peer, sizeof(peer));
      if (harbor_sync_is_acknowledged(chat->sync, peer, id) == 1)
        result = 1;
    }
  free(d);
  return result;
}
static char *row_json(struct harbor_person_chat *chat,
                      const struct harbor_sync_event *event,
                      const struct app_message *message, const struct row *row) {
  char *edited=NULL;
  struct harbor_sync_event edit; struct app_action action;
  const char *content=message->text;
  if(row && row->edit[0]) {
    edited=harbor_sync_get(chat->sync,row->edit,&edit);
    if(!edited || parse_action(&edit,&action)) {free(edited);return NULL;}
    content=action.route.text;
  }
  if(row && row->deleted)content="";
  char *text = malloc(HARBOR_ESC_MAX), *line = malloc(HARBOR_EVENT_MAX + 512);
  if (!text || !line || omaq_json_escape(content, text, HARBOR_ESC_MAX)) {
    free(text);
    free(line);
    free(edited);
    return NULL;
  }
  int outgoing = !strcmp(message->origin, chat->own);
  snprintf(line, HARBOR_EVENT_MAX + 512,
           "{\"id\":\"%s\",\"ts\":%lld,\"from\":\"%s\",\"text\":\"%s\",\"dir\":"
           "\"%s\",\"reply\":\"%s\",\"state\":\"%s\",\"edited\":%s,\"deleted\":%s,\"reactionMe\":\"%s\",\"reactionPeer\":\"%s\"}",
           event->id, (long long)message->timestamp, outgoing ? "me" : "peer",
           text, outgoing ? "out" : "in", message->reply,
           outgoing ? (row && row->read ? "read" : delivered(chat, message->target, event->id) ? "delivered"
                                                                   : "queued")
                    : "received", row && row->edit[0] ? "true":"false",
           row && row->deleted ? "true":"false",row?row->reaction_me:"",row?row->reaction_peer:"");
  free(text);
  free(edited);
  return line;
}
static void emit_updated(struct harbor_person_chat *chat,const char *other,
                           const struct row *item,const char *request) {
  struct harbor_sync_event original;struct app_message message;
  char *plain=harbor_sync_get(chat->sync,item->event,&original);
  char *row=plain && !parse(&original,&message)?row_json(chat,&original,&message,item):NULL;
  char escaped[481];
  if(row && !omaq_json_escape(request,escaped,sizeof(escaped))) {
    size_t size=strlen(row)+1024;char *line=malloc(size);
    if(line) {
      snprintf(line,size,"{\"event\":\"message.updated\",\"conversation\":\"p:%s\",\"key\":\"%s\",\"request\":\"%s\",%s",other,other,escaped,row+1);
      chat->sync->emit(line);free(line);
    }
  }
  free(row);free(plain);
}
static void apply_action(struct harbor_person_chat *chat,
                          const struct harbor_sync_event *event) {
  struct app_action action;
  if(parse_action(event,&action))return;
  int own=!strcmp(action.route.origin,chat->own);
  if(!own && strcmp(action.route.target,chat->own))return;
  const char *other=own?action.route.target:action.route.origin;
  struct model *model=load_model(chat,other);
  if(!model)return;
  const char *request=own && !strcmp(event->author,chat->local)?action.request:"";
  size_t through=model->count;
  for(size_t i=0;i<model->count;i++)if(!strcmp(model->rows[i].id,action.message))through=i;
  if(through==model->count){free_model(model);return;}
  for(size_t i=0;i<model->count;i++) {
    int affected=!strcmp(model->rows[i].id,action.message) ||
      (!strcmp(event->kind,"read") && i<=through &&
       !strcmp(model->rows[i].origin,action.original));
    if(!affected)continue;
    emit_updated(chat,other,&model->rows[i],request);
  }
  free_model(model);
}
void harbor_person_chat_apply(struct harbor_person_chat *chat,
                              const struct harbor_sync_event *event) {
  struct app_message message;
  if (chat->sync->replaying || !chat->own[0]) return;
  if (parse(event, &message)) {
    apply_action(chat,event);
    return;
  }
  int outgoing = !strcmp(message.origin, chat->own);
  if (!outgoing && strcmp(message.target, chat->own))
    return;
  const char *other = outgoing ? message.target : message.origin;
  struct model *model=load_model(chat,other);
  if(!model)return;
  for(size_t i=0;i<model->count;i++) if(!strcmp(model->rows[i].id,event->id)) {
    char *row=row_json(chat,event,&message,&model->rows[i]);
    if(row) {
      char request[481];
      size_t size=strlen(row)+1024;char *line=malloc(size);
      if(line && !omaq_json_escape(outgoing && !strcmp(event->author,chat->local)?message.request:"",request,sizeof(request))) {
        snprintf(line,size,"{\"event\":\"message\",\"conversation\":\"p:%s\",\"key\":\"%s\",\"request\":\"%s\",%s",other,other,request,row+1);
        chat->sync->emit(line);
      }
      free(line);free(row);
    }
    if(outgoing && model->rows[i].read)
      for(size_t j=0;j<i;j++)
        if(model->rows[j].read && !strcmp(model->rows[j].origin,message.origin))
          emit_updated(chat,other,&model->rows[j],"");
    break;
  }
  free_model(model);
}
void harbor_person_chat_ack(void *context, const char *peer, const char *id) {
  struct harbor_person_chat *chat = context;
  struct harbor_sync_event event;
  char *plain = harbor_sync_get(chat->sync, id, &event);
  if (!plain)
    return;
  struct app_message message;
  char root[65];
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (d && !parse(&event, &message) && !strcmp(message.origin, chat->own) &&
      harbor_people_find(chat->sync->home, peer, NULL, root, d) >= 0 &&
      !strcmp(root, message.target)) {
    struct model *model=load_model(chat,message.target);
    if(model) {
      int read=0;
      for(size_t i=0;i<model->count;i++)
        if(!strcmp(model->rows[i].id,id))read=model->rows[i].read;
      char line[512];
      snprintf(line, sizeof(line),
               "{\"event\":\"receipt\",\"conversation\":\"p:%s\",\"key\":\"%s\","
               "\"id\":\"%s\",\"state\":\"%s\"}",
               root, root, id,read?"read":"delivered");
      chat->sync->emit(line);
      free_model(model);
    }
  }
  free(d);
  free(plain);
}
static void fail(struct harbor_person_chat *chat, const omaq_op *op,
                 const char *code) {
  char request[481], id[481], conversation[481], key[481], line[4096];
  if (omaq_json_escape(op->request, request, sizeof(request)) ||
      omaq_json_escape(op->id, id, sizeof(id)) ||
      omaq_json_escape(op->conversation, conversation, sizeof(conversation)) ||
      omaq_json_escape(op->key, key, sizeof(key)))
    return;
  const char *type = !strcmp(op->op, "msg.send")  ? "message.failed"
                     : !strcmp(op->op, "history") ? "history.failed"
                                                  : "error";
  snprintf(
      line, sizeof(line),
      "{\"event\":\"%s\",\"conversation\":\"%s\",\"key\":\"%s\",\"request\":\"%"
      "s\",\"id\":\"%s\",\"code\":\"%s\",\"retryable\":false}",
      type, conversation, key, (!strcmp(op->op, "history") || !strcmp(op->op,"msg.send")) ? id : request, id,
      code);
  chat->sync->emit(line);
}
static void history(struct harbor_person_chat *chat, const omaq_op *op) {
  struct model *model = load_model(chat, op->conversation + 2);
  if (!model) {
    fail(chat, op, "history_failed");
    return;
  }
  size_t end = model->count;
  if(op->payload[0]) {
    int found=0;
    for(size_t i=0;i<model->count;i++)if(!strcmp(model->rows[i].id,op->payload)) {
      end=i;found=1;break;
    }
    if(!found){free_model(model);fail(chat,op,"history_cursor_invalid");return;}
  }
  int limit = op->has_limit ? op->limit : 50;
  if (limit < 1)
    limit = 1;
  if (limit > 100)
    limit = 100;
  size_t start = end > (size_t)limit ? end - (size_t)limit : 0,
         count = end - start;
  char **rows = calloc(count ? count : 1, sizeof(*rows));
  size_t total = 0;
  if (!rows) {
    free_model(model);
    fail(chat, op, "history_failed");
    return;
  }
  for (size_t i = 0; i < count; i++) {
    struct harbor_sync_event event;
    struct app_message message;
    char *plain =
        harbor_sync_get(chat->sync, model->rows[start + i].event, &event);
    if (plain && !parse(&event, &message))
      rows[i] = row_json(chat, &event, &message, &model->rows[start+i]);
    free(plain);
    if (!rows[i]) {
      for (size_t j = 0; j < count; j++)
        free(rows[j]);
      free(rows);
      free_model(model);
      fail(chat, op, "history_failed");
      return;
    }
    total += strlen(rows[i]) + 1;
  }
  size_t first = 0;
  while (total > RESPONSE_MAX && first < count) {
    total -= strlen(rows[first]) + 1;
    free(rows[first]);
    rows[first++] = NULL;
  }
  char request[481], *result = malloc(total + 2048);
  if (!result) {
    for (size_t i = 0; i < count; i++)
      free(rows[i]);
    free(rows);
    free_model(model);
    return;
  }
  omaq_json_escape(op->id, request, sizeof(request));
  int n = snprintf(result, total + 2048,
                   "{\"event\":\"history\",\"conversation\":\"%s\",\"key\":\"%"
                   "s\",\"request\":\"%s\",\"hasMore\":%s,\"items\":[",
                   op->conversation, op->key, request,
                   start + first ? "true" : "false");
  size_t used = (size_t)n;
  for (size_t i = first; i < count; i++) {
    size_t length = strlen(rows[i]);
    if (i > first)
      result[used++] = ',';
    memcpy(result + used, rows[i], length);
    used += length;
  }
  memcpy(result + used, "]}", 3);
  chat->sync->emit(result);
  for (size_t i = 0; i < count; i++)
    free(rows[i]);
  free(rows);
  free_model(model);
  free(result);
}
static void action_operation(struct harbor_person_chat *chat,const omaq_op *op,
                              const char *kind) {
  if(!omaq_message_id_ok(op->request) || strlen(op->request)>=80 || !hex_ok(op->id,32)) {
    fail(chat,op,"message_invalid");return;
  }
  struct harbor_sync_event event;struct app_message original;
  char *plain=harbor_sync_get(chat->sync,op->id,&event);
  if(!plain || parse(&event,&original) ||
     !((!strcmp(original.origin,chat->own) && !strcmp(original.target,op->key)) ||
       (!strcmp(original.origin,op->key) && !strcmp(original.target,chat->own)))) {
    free(plain);fail(chat,op,"message_unavailable");return;
  }
  if(((!strcmp(kind,"edit") || !strcmp(kind,"delete")) && strcmp(original.origin,chat->own)) ||
     (!strcmp(kind,"read") && strcmp(original.origin,op->key))) {
    free(plain);fail(chat,op,"forbidden");return;
  }
  const char *text=(!strcmp(kind,"edit") || !strcmp(kind,"reaction"))?op->text:"";
  if((!strcmp(kind,"edit") && (!op->has_text || strlen(text)>HARBOR_TEXT_MAX ||
      !omaq_message_text_bytes_ok((const unsigned char *)text,strlen(text)))) ||
     (!strcmp(kind,"reaction") && !omaq_message_reaction_ok(text))) {
    free(plain);fail(chat,op,"message_invalid");return;
  }
  char *body=malloc(HARBOR_APP_BODY_MAX+1);
  if(!body){free(plain);fail(chat,op,"message_failed");return;}
  int n=snprintf(body,HARBOR_APP_BODY_MAX+1,"HA1|%s|%s|%s|%s|%s\n%s",
    chat->own,op->key,original.origin,op->id,op->request,text);
  free(plain);
  if(n<0 || (size_t)n>HARBOR_APP_BODY_MAX){free(body);fail(chat,op,"message_too_long");return;}
  char retry[33];
  if(harbor_sync_find_request(chat->sync,chat->own,chat->local,2,op->request,retry)<0) {
    free(body);fail(chat,op,"message_state_invalid");return;
  }
  int created=0;const char *problem=NULL;
  if(retry[0]) {
    char *previous=harbor_sync_get(chat->sync,retry,&event);
    if(!previous)problem="message_retry_unavailable";
    else if(strcmp(event.kind,kind) || strcmp(event.text,body) ||
            strcmp(event.conversation,op->conversation))problem="message_id_conflict";
    else {
      problem=harbor_sync_publish(chat->sync,event.id,event.conversation,event.kind,event.text,&created);
      if(!problem)apply_action(chat,&event);
    }
    free(previous);
  } else {
    struct model *model=load_model(chat,op->key);
    if(!model)problem="history_failed";
    else {
      for(size_t i=0;i<model->count;i++)
        if(!strcmp(model->rows[i].id,op->id) && model->rows[i].deleted && !strcmp(kind,"edit"))
          problem="message_deleted";
      free_model(model);
    }
    if(!problem){char id[33];problem=harbor_sync_publish_canonical(chat->sync,op->conversation,kind,body,id,&created);}
  }
  free(body);
  if(problem)fail(chat,op,problem);
  else if(!strcmp(kind,"read")) {
    char request[481],line[1024];
    if(!omaq_json_escape(op->request,request,sizeof(request))) {
      snprintf(line,sizeof(line),"{\"event\":\"conversation.read\",\"conversation\":\"%s\",\"key\":\"%s\",\"request\":\"%s\"}",op->conversation,op->key,request);
      chat->sync->emit(line);
    }
  }
}
int harbor_person_chat_operation(struct harbor_person_chat *chat,
                                 const omaq_op *op) {
  if (strncmp(op->conversation, "p:", 2))
    return 0;
  if (!hex_ok(op->conversation + 2, 64) || !hex_ok(op->key, 64) ||
      strcmp(op->conversation + 2, op->key) || !chat->own[0]) {
    fail(chat, op, "person_binding_mismatch");
    return 1;
  }
  struct harbor_devices *contact = calloc(1, sizeof(*contact));
  if (!contact || harbor_people_get(chat->sync->home, op->key, contact, NULL)) {
    free(contact);
    fail(chat, op, "person_unavailable");
    return 1;
  }
  free(contact);
  if (!strcmp(op->op, "history")) {
    history(chat, op);
    return 1;
  }
  const char *action = !strcmp(op->op,"message.edit") ? "edit" :
      !strcmp(op->op,"message.delete") ? "delete" :
      !strcmp(op->op,"message.react") ? "reaction" :
      !strcmp(op->op,"conversation.read") ? "read" : NULL;
  if(action) {action_operation(chat,op,action);return 1;}
  if (strcmp(op->op, "msg.send")) {
    fail(chat, op, "person_operation_not_implemented");
    return 1;
  }
  if (!omaq_message_id_ok(op->id) || !strcmp(op->id, "-") || !op->has_text ||
      strlen(op->text) > HARBOR_TEXT_MAX ||
      !omaq_message_text_bytes_ok((const unsigned char *)op->text,
                                  strlen(op->text)) ||
      (op->reply[0] && !omaq_message_id_ok(op->reply))) {
    fail(chat, op, "message_invalid");
    return 1;
  }
  char match[33];
  if(harbor_sync_find_request(chat->sync,chat->own,chat->local,1,op->id,match)<0) {
    fail(chat, op, "message_state_invalid");
    return 1;
  }
  char id[33];
  struct harbor_sync_event existing;
  int skip_reread = 0;
#ifdef HARBOR_SYNC_FAULTS
  const char *failure = getenv("HARBOR_SYNC_FAIL_REQUEST_REREAD_FILE");
  skip_reread = match[0] && failure && access(failure, F_OK) == 0;
#endif
  char *prior = match[0] && !skip_reread
                    ? harbor_sync_get(chat->sync, match, &existing)
                    : NULL;
  if (match[0] && !prior) {
    fail(chat, op, "message_retry_unavailable");
    return 1;
  }
  if (prior) {
    struct app_message old;
    if (parse(&existing, &old) || strcmp(old.origin, chat->own) ||
        strcmp(old.target, op->key) || strcmp(old.text, op->text) ||
        strcmp(old.reply, op->reply))
      fail(chat, op, "message_id_conflict");
    else {
      int created;
      const char *problem =
          harbor_sync_publish(chat->sync, existing.id, existing.conversation,
                              existing.kind, existing.text, &created);
      if (problem)
        fail(chat, op, problem);
      else
        harbor_person_chat_apply(chat, &existing);
    }
    free(prior);
    return 1;
  }
  int64_t now = (int64_t)time(NULL);
  if (now <= 0 || now > INT64_C(253402300799)) {
    fail(chat, op, "clock_invalid");
    return 1;
  }
  char *body = malloc(HARBOR_APP_BODY_MAX + 1);
  if (!body) {
    fail(chat, op, "message_failed");
    return 1;
  }
  int size =
      snprintf(body, HARBOR_APP_BODY_MAX + 1, "HM2|%s|%s|%s|%s|%016llx\n%s",
               chat->own, op->key, op->reply[0] ? op->reply : "-", op->id,
               (unsigned long long)now, op->text);
  if (size < 0 || (size_t)size > HARBOR_APP_BODY_MAX) {
    free(body);
    fail(chat, op, "message_too_long");
    return 1;
  }
  int created;
  const char *problem = harbor_sync_publish_canonical(
      chat->sync, op->conversation, "message", body, id, &created);
  if (problem)
    fail(chat, op, problem);
  free(body);
  return 1;
}
#endif
