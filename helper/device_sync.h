#ifndef HARBOR_DEVICE_SYNC_H
#define HARBOR_DEVICE_SYNC_H
#include "json_io.h"
#include "ratchet.h"
#include "journal.h"
#ifdef HAVE_SIGNAL
#define HARBOR_APP_BODY_MAX (HARBOR_TEXT_MAX + 512u)
#define HARBOR_SYNC_TARGET_MAX 64u
struct harbor_sync_target {
  char transport[65], ratchet[65];
  int blocked; /* Known delivery obligation awaiting endpoint endorsement. */
};
struct harbor_sync_event {
  char id[33], person[65], author[65], conversation[67], kind[16];
  uint64_t clock;
  const char *text;
};
struct harbor_sync {
  struct harbor_journal *journal;
  char journal_owner[65];
  int importing;
  int idle,targets_incomplete;
  const char *home;
  char transport[65], ratchet_key[65];
  struct omaq_ratchet *ratchet;
  int (*pin)(const char *peer, char out[65]);
  int (*send)(const char *peer, const char *ciphertext);
  int (*available)(const char *peer);
  void (*emit)(const char *json);
  int (*apply)(const struct harbor_sync_event *event, int fresh);
  int replayed;
  int replaying;
  void *application;
  int (*index_event)(void *context,const struct harbor_sync_event *event,
                     struct harbor_journal_index *index);
  int (*peer_authorized)(void *context, const char *peer, const char *pin);
  int (*accept_event)(void *context, const char *peer, const char *pin,
                      const struct harbor_sync_event *event);
  int (*targets)(void *context, const struct harbor_sync_event *event,
                 struct harbor_sync_target *out, size_t capacity);
  void (*acknowledged)(void *context, const char *peer, const char *id);
  long long retry;
  size_t cursor;
  uint64_t observed_clock;
};
void harbor_sync_close(struct harbor_sync *sync);
int harbor_sync_roster_head(struct harbor_sync *sync,const char *scope,const char *head);
int harbor_sync_visit_conversation(struct harbor_sync *sync,const char *other,
    void (*visitor)(const struct harbor_sync_event *,void *),void *context);
int harbor_sync_find_request(struct harbor_sync *sync,const char *person,
    const char *author,int request_class,const char *request,char id[33]);
int harbor_sync_content_id(const struct harbor_sync_event *event, char id[33]);
const char *harbor_sync_publish_canonical(struct harbor_sync *sync,
                                          const char *conversation,
                                          const char *kind, const char *body,
                                          char id[33], int *created);
const char *harbor_sync_publish(struct harbor_sync *sync, const char *id,
                                const char *conversation, const char *kind,
                                const char *body, int *created);
char *harbor_sync_get(struct harbor_sync *sync, const char *id,
                      struct harbor_sync_event *event);
int harbor_sync_visit_contacts(struct harbor_sync *sync,
    void (*visitor)(const struct harbor_sync_event *,void *),void *context);
int harbor_sync_visit(struct harbor_sync *sync,
                      void (*visitor)(const struct harbor_sync_event *, void *),
                      void *context);
int harbor_sync_is_acknowledged(struct harbor_sync *sync, const char *peer,
                                const char *id);
void harbor_sync_operation(struct harbor_sync *sync, const omaq_op *operation);
int harbor_sync_receive(struct harbor_sync *sync, const char *peer,
                        const char *pin, const char *wire);
#ifdef HARBOR_SYNC_FAULTS
int harbor_sync_outbox_pending(struct harbor_sync *sync, const char *peer);
#endif
int harbor_sync_session_begin(struct harbor_sync *sync, const char *peer,
                              const char *pin);
void harbor_sync_session_changed(struct harbor_sync *sync, const char *peer,
                                 const char *pin);
void harbor_sync_ack(struct harbor_sync *sync, const char *peer,
                     const char *pin, const char *id);
void harbor_sync_tick(struct harbor_sync *sync);
#endif
#endif
