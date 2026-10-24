#ifndef HARBOR_DEVICE_LINK_H
#define HARBOR_DEVICE_LINK_H
#include "devices.h"
#include "json_io.h"
struct harbor_link_pending {
  int used, confirmed, sent, approved, submitted_consent;
  long long expires, retry;
  unsigned attempts;
  char request[80], peer[65], proposal[193], name[49];
  char person[65], head[65], owner[193], code[65];
  char proof[129];
  char roster[HARBOR_DEVICE_ROSTER_HEX + 1];
};
struct harbor_link {
  const char *home;
  char transport[65], ratchet[65];
  int (*send)(const char *peer, const char *plain);
  void (*emit)(const char *json);
  struct harbor_link_pending incoming, outgoing;
};
void harbor_link_replay(struct harbor_link *link);
void harbor_link_tick(struct harbor_link *link);
void harbor_link_operation(struct harbor_link *link, const omaq_op *op,
                           const char *peer, const char *peer_ratchet);
/* Called only after successful Ratchet decryption and stable-key binding. */
void harbor_link_receive(struct harbor_link *link, const char *peer,
                         const char *peer_ratchet, const char *plain);
#endif
