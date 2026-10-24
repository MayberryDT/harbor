#define _DEFAULT_SOURCE
#include "endpoint.h"
#ifdef HAVE_SIGNAL
#include "people.h"
#include <openssl/rand.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static int hex(const char *text, size_t length) {
  if (!text || strlen(text) != length)
    return 0;
  for (size_t i = 0; i < length; i++)
    if (!((text[i] >= '0' && text[i] <= '9') ||
          (text[i] >= 'a' && text[i] <= 'f')))
      return 0;
  return 1;
}
static uint64_t now(void) {
  time_t n = time(NULL);
  return n > 0 ? (uint64_t)n : 0;
}
static int current(struct harbor_endpoint *e,
                   const struct harbor_probe_record *r) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return -1;
  if (harbor_people_get(e->home, r->root, d, NULL)) {
    free(d);
    return -1;
  }
  int match = 0;
  for (size_t i = 0; i < d->count; i++) {
    char proposal[193];
    harbor_device_hex(d->devices[i].signing, 32, proposal, 65);
    harbor_device_hex(d->devices[i].transport, 32, proposal + 64, 65);
    harbor_device_hex(d->devices[i].ratchet, 32, proposal + 128, 65);
    if (d->devices[i].active && !strcmp(r->proposal, proposal))
      match = 1;
  }
  free(d);
  return match;
}
static void transport_key(const struct harbor_probe_record *r, char key[65]) {
  memcpy(key, r->proposal + 64, 64);
  key[64] = 0;
}
int harbor_endpoint_candidate(struct harbor_endpoint *e, const char *root,
                              const struct harbor_device *device) {
  if (!e->home || !hex(root, 64) || !device->active)
    return -1;
  struct harbor_probe_record r;
  memset(&r, 0, sizeof(r));
  snprintf(r.root, sizeof(r.root), "%s", root);
  harbor_device_hex(device->signing, 32, r.proposal, 65);
  harbor_device_hex(device->transport, 32, r.proposal + 64, 65);
  harbor_device_hex(device->ratchet, 32, r.proposal + 128, 65);
  char key[65], id[65], pin[65], anchored[65];
  transport_key(&r, key);
  if (!strcmp(key, e->transport) || harbor_probe_id(root, r.proposal, id))
    return -1;
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return -1;
  int found = harbor_people_find(e->home, key, NULL, anchored, d);
  free(d);
  if (found >= 0)
    return found == 1 && !strcmp(root, anchored) ? 0 : -1;
  int pinned = e->pin(key, pin);
  if (pinned < 0 || (pinned == 1 && strcmp(pin, r.proposal + 128)))
    return -1;
  struct harbor_probe_record existing;
  int present = harbor_probe_get(e->home, id, &existing);
  if (present < 0)
    return -1;
  if (!present) {
    if (!existing.closed || existing.owned || now() <= existing.expires + 3600)
      return 0;
    if (harbor_probe_drop(e->home, id))
      return -1;
  }
  char ids[HARBOR_PROBE_MAX][65];
  int count = harbor_probe_list(e->home, ids), per_root = 0, retained = count;
  if (count < 0)
    return -1;
  for (int i = 0; i < count; i++) {
    struct harbor_probe_record other;
    if (harbor_probe_get(e->home, ids[i], &other))
      return -1;
    if (other.closed && !other.owned && now() > other.expires + 3600) {
      if (harbor_probe_drop(e->home, ids[i]))
        return -1;
      retained--;
      continue;
    }
    if (!other.closed && !strcmp(other.root, root))
      per_root++;
  }
  if (per_root >= 4 || retained >= (int)HARBOR_PROBE_MAX || !now())
    return -1;
  for (size_t i = 0; i < HARBOR_PROBE_MAX; i++)
    if (!strcmp(e->pending[i].key, id))
      memset(&e->pending[i], 0, sizeof(e->pending[i]));
  r.expires = now() + 300;
  r.owned = e->exists(key) == 0;
  return harbor_probe_put(e->home, id, &r);
}
void harbor_endpoint_tick(struct harbor_endpoint *e) {
  if (!e->home || !now() || now() < e->next_tick)
    return;
  e->next_tick = now() + 1;
  struct harbor_devices *own = calloc(1, sizeof(*own));
  e->person[0] = e->proposal[0] = 0;
  if (own && !harbor_devices_operation(e->home, "device.status", e->transport,
                                       e->ratchet, "", "", "", "", 0, own)) {
    harbor_device_hex(own->root, 32, e->person, 65);
    harbor_device_hex(own->local, 32, e->proposal, 65);
    memcpy(e->proposal + 64, e->transport, 64);
    memcpy(e->proposal + 128, e->ratchet, 65);
  }
  free(own);
  char ids[HARBOR_PROBE_MAX][65];
  int count = harbor_probe_list(e->home, ids);
  if (count < 0)
    return;
  for (int i = 0; i < count; i++) {
    struct harbor_probe_record r;
    if (harbor_probe_get(e->home, ids[i], &r) || r.closed)
      continue;
    char key[65], pin[65], root[65];
    transport_key(&r, key);
    int pinned = e->pin(key, pin);
    struct harbor_devices *d = calloc(1, sizeof(*d));
    if (!d)
      return;
    int endorsed = harbor_people_find(e->home, key, NULL, root, d);
    free(d);
    if (endorsed == 1 && !strcmp(root, r.root)) {
      if (!e->promote(key, r.proposal + 128))
        (void)harbor_probe_drop(e->home, ids[i]);
      continue;
    }
    if (now() >= r.expires || r.expires > now() + 300) {
      r.closed = 1;
      (void)harbor_probe_put(e->home, ids[i], &r);
      continue;
    }
    int membership = current(e, &r);
    if (membership < 0 || pinned < 0)
      continue;
    if (membership == 0 || endorsed >= 0 ||
        (pinned == 1 && strcmp(pin, r.proposal + 128))) {
      r.closed = 1;
      (void)harbor_probe_put(e->home, ids[i], &r);
      continue;
    }
    size_t slot = HARBOR_PROBE_MAX;
    for (size_t j = 0; j < HARBOR_PROBE_MAX; j++)
      if (!strcmp(e->pending[j].key, ids[i])) {
        slot = j;
        break;
      }
    if (slot == HARBOR_PROBE_MAX)
      for (size_t j = 0; j < HARBOR_PROBE_MAX; j++) {
        struct harbor_probe_record old;
        if (!e->pending[j].key[0] ||
            harbor_probe_get(e->home, e->pending[j].key, &old) != 0 ||
            old.closed) {
          unsigned char random[16];
          if (RAND_bytes(random, sizeof(random)) != 1)
            return;
          memset(&e->pending[j], 0, sizeof(e->pending[j]));
          memcpy(e->pending[j].key, ids[i], 65);
          harbor_device_hex(random, sizeof(random), e->pending[j].nonce, 33);
          slot = j;
          break;
        }
      }
    if (slot == HARBOR_PROBE_MAX || now() < e->pending[slot].retry)
      continue;
    e->pending[slot].retry = now() + 5;
    if (e->connect(key))
      continue;
    char wire[384];
    snprintf(wire, sizeof(wire), "HPE2|query|%s|%s|%s", e->pending[slot].nonce,
             r.root, r.proposal);
    (void)e->send(key, wire);
  }
  /* Ownership is physical-key scoped across every competing proposal. An
   * expired claim cannot remove a transport while another claim still uses it.
   */
  count = harbor_probe_list(e->home, ids);
  for (int i = 0; i < count; i++) {
    struct harbor_probe_record r;
    if (harbor_probe_get(e->home, ids[i], &r) || !r.owned)
      continue;
    char key[65], pin[65];
    transport_key(&r, key);
    int pinned = e->pin(key, pin), active = 0;
    if (pinned < 0)
      continue;
    for (int j = 0; j < count; j++) {
      struct harbor_probe_record other;
      if (harbor_probe_get(e->home, ids[j], &other)) {
        active = 1;
        break;
      }
      if (!other.closed && !strncmp(other.proposal + 64, key, 64))
        active = 1;
    }
    if (pinned == 0 && (active || e->remove(key)))
      continue;
    r.owned = 0;
    (void)harbor_probe_put(e->home, ids[i], &r);
  }
}
void harbor_endpoint_receive(struct harbor_endpoint *e, const char *peer,
                             const char *wire) {
  if (!e->home || !hex(peer, 64) || !wire[0] || strlen(wire) > 512 ||
      wire[strlen(wire) - 1] == '|')
    return;
  char copy[513];
  snprintf(copy, sizeof(copy), "%s", wire);
  char *save = NULL;
  char *version = strtok_r(copy, "|", &save),
       *kind = strtok_r(NULL, "|", &save), *nonce = strtok_r(NULL, "|", &save),
       *root = strtok_r(NULL, "|", &save),
       *proposal = strtok_r(NULL, "|", &save),
       *proof = strtok_r(NULL, "|", &save);
  if (!version || strcmp(version, "HPE2") || !kind || !hex(nonce, 32) ||
      !hex(root, 64) || !hex(proposal, 192) || strtok_r(NULL, "|", &save))
    return;
  if (!strcmp(kind, "query")) {
    /* Incorrect claims must not consume the real tuple's response budget. */
    if (proof || strcmp(root, e->person) || strcmp(proposal, e->proposal))
      return;
    size_t reply = HARBOR_PROBE_MAX;
    for (size_t i = 0; i < HARBOR_PROBE_MAX; i++)
      if (!strcmp(e->replies[i].key, peer)) {
        reply = i;
        break;
      }
    if (reply < HARBOR_PROBE_MAX && now() < e->replies[reply].after)
      return;
    if (reply == HARBOR_PROBE_MAX)
      for (size_t i = 0; i < HARBOR_PROBE_MAX; i++)
        if (now() >= e->replies[i].after) {
          reply = i;
          break;
        }
    if (reply == HARBOR_PROBE_MAX)
      return;
    char signature[129], response[512];
    if (harbor_endpoint_signature(e->home, e->transport, e->ratchet, root,
                                  nonce, proposal, signature))
      return;
    memcpy(e->replies[reply].key, peer, 65);
    e->replies[reply].after = now() + 1;
    snprintf(response, sizeof(response), "HPE2|proof|%s|%s|%s|%s", nonce, root,
             proposal, signature);
    (void)e->send(peer, response);
    return;
  }
  if (strcmp(kind, "proof") || !hex(proof, 128) ||
      strncmp(proposal + 64, peer, 64))
    return;
  char id[65];
  if (harbor_probe_id(root, proposal, id))
    return;
  int pending = 0;
  for (size_t i = 0; i < HARBOR_PROBE_MAX; i++)
    if (!strcmp(e->pending[i].key, id) && !strcmp(e->pending[i].nonce, nonce))
      pending = 1;
  struct harbor_probe_record r;
  char pin[65];
  int pinned = e->pin(peer, pin);
  if (!pending || harbor_probe_get(e->home, id, &r) || r.closed ||
      now() >= r.expires || strcmp(root, r.root) ||
      strcmp(proposal, r.proposal) || pinned < 0 ||
      (pinned == 1 && strcmp(pin, proposal + 128)) || current(e, &r) != 1 ||
      harbor_endpoint_verify(root, nonce, proposal, proof))
    return;
  /* The exact endpoint endorsement is durable before pin/session promotion. */
  if (harbor_people_endorse(e->home, root, peer, proposal + 128))
    return;
#ifdef HARBOR_SYNC_FAULTS
  const char *fault = getenv("HARBOR_SYNC_CRASH_AT");
  if (fault && !strcmp(fault, "after-endorsement"))
    _exit(78);
#endif
  if (!e->promote(peer, proposal + 128))
    (void)harbor_probe_drop(e->home, id);
}
#endif
