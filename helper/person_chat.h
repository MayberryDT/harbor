#ifndef HARBOR_PERSON_CHAT_H
#define HARBOR_PERSON_CHAT_H
#include "device_sync.h"
#ifdef HAVE_SIGNAL
struct harbor_person_chat {
  struct harbor_sync *sync;
  char own[65], local[65];
};
void harbor_person_chat_bind(struct harbor_person_chat *chat,
                             struct harbor_sync *sync);
int harbor_person_chat_operation(struct harbor_person_chat *chat,
                                 const omaq_op *operation);
void harbor_person_chat_apply(struct harbor_person_chat *chat,
                              const struct harbor_sync_event *event);
int harbor_person_chat_peer(void *chat, const char *peer, const char *pin);
int harbor_person_chat_accept(void *chat, const char *peer, const char *pin,
                              const struct harbor_sync_event *event);
int harbor_person_chat_targets(void *chat,
                               const struct harbor_sync_event *event,
                               struct harbor_sync_target *out, size_t capacity);
int harbor_person_chat_index(void *chat,const struct harbor_sync_event *event,
                              struct harbor_journal_index *index);
void harbor_person_chat_ack(void *chat, const char *peer, const char *id);
#endif
#endif
