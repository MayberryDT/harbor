#ifndef HARBOR_ENDPOINT_H
#define HARBOR_ENDPOINT_H
#include "devices.h"
#include <stdint.h>
#define HARBOR_PROBE_MAX 64u
struct harbor_probe_record {
  char root[65], proposal[193];
  uint64_t expires;
  int owned, closed;
};
/* Intents are keyed by the hash of root+tuple, so competing claims cannot
 * reserve a physical endpoint. Ownership debt stays until no claim uses it. */
int harbor_probe_id(const char *root, const char *proposal, char id[65]);
int harbor_probe_list(const char *home, char keys[][65]);
int harbor_probe_get(const char *home, const char *key,
                     struct harbor_probe_record *out);
int harbor_probe_put(const char *home, const char *key,
                     const struct harbor_probe_record *record);
int harbor_probe_drop(const char *home, const char *key);
int harbor_endpoint_signature(const char *home, const char *transport,
                              const char *ratchet, const char *root,
                              const char *nonce, const char *proposal,
                              char proof[129]);
int harbor_endpoint_verify(const char *root, const char *nonce,
                           const char *proposal, const char *proof);
struct harbor_rendezvous {
  char invite[65];
  uint64_t expires;
};
int harbor_rendezvous_list(const char *home, char keys[][65]);
int harbor_rendezvous_get(const char *home, const char *key,
                          struct harbor_rendezvous *out);
int harbor_rendezvous_put(const char *home, const char *key, const char *invite,
                          uint64_t expires);
int harbor_rendezvous_drop(const char *home, const char *key);
struct harbor_endpoint {
  const char *home;
  uint64_t next_tick;
  char transport[65], ratchet[65], person[65], proposal[193];
  int (*exists)(const char *key);
  int (*pin)(const char *key, char out[65]);
  int (*connect)(const char *key);
  int (*promote)(const char *key, const char *pin);
  int (*remove)(const char *key);
  int (*send)(const char *key, const char *metadata);
  struct {
    char key[65];
    uint64_t after;
  } replies[HARBOR_PROBE_MAX];
  struct {
    char key[65], nonce[33];
    uint64_t retry;
  } pending[HARBOR_PROBE_MAX];
};
int harbor_endpoint_candidate(struct harbor_endpoint *endpoint,
                              const char *root,
                              const struct harbor_device *device);
void harbor_endpoint_tick(struct harbor_endpoint *endpoint);
void harbor_endpoint_receive(struct harbor_endpoint *endpoint, const char *peer,
                             const char *wire);
#endif
