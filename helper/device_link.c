#define _DEFAULT_SOURCE
#include "device_link.h"
#ifdef HAVE_SIGNAL
#include "message.h"
#include "text.h"
#include <openssl/evp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static long long now(void) {
  struct timespec value;
  return clock_gettime(CLOCK_MONOTONIC, &value) == 0 ? value.tv_sec : -1;
}
static void failure(struct harbor_link *l, const char *request,
                    const char *code) {
  char escaped[481], event[768];
  if (omaq_json_escape(request, escaped, sizeof(escaped)))
    return;
  snprintf(event, sizeof(event),
           "{\"event\":\"devices.error\",\"request\":\"%s\",\"code\":\"%s\"}",
           escaped, code);
  l->emit(event);
}
static void state(struct harbor_link *l, struct harbor_link_pending *p,
                  const char *value) {
  char request[481], name[289], event[1536];
  if (omaq_json_escape(p->request, request, sizeof(request)) ||
      omaq_json_escape(p->name, name, sizeof(name)))
    return;
  snprintf(event, sizeof(event),
           "{\"event\":\"device.link\",\"state\":\"%s\",\"request\":\"%s\","
           "\"name\":\"%s\",\"person\":\"%s\",\"code\":\"%s\",\"key\":\"%s\",\"incoming\":%s}",
           value, request, name, p->person, p->code, p->peer,
           p == &l->incoming ? "true" : "false");
  l->emit(event);
}
static int hex_ok(const char *s, size_t n) {
  if (strlen(s) != n)
    return 0;
  for (size_t i = 0; i < n; i++)
    if (!(s[i] >= '0' && s[i] <= '9') && !(s[i] >= 'a' && s[i] <= 'f'))
      return 0;
  return 1;
}
static int hash_hex(const void *bytes, size_t n, char out[65]) {
  unsigned char digest[32];
  unsigned length;
  return EVP_Digest(bytes, n, digest, &length, EVP_sha256(), NULL) == 1 &&
                 length == 32
             ? harbor_device_hex(digest, 32, out, 65)
             : -1;
}
static struct harbor_devices *
read_state(struct harbor_link *l, const char *operation, const char **error) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d) {
    *error = "device_unavailable";
    return NULL;
  }
  *error = harbor_devices_operation(l->home, operation, l->transport,
                                    l->ratchet, "", "", "", "", 0, d);
  if (*error) {
    free(d);
    return NULL;
  }
  return d;
}
static void proposal(struct harbor_link *l, const struct harbor_devices *d,
                     char out[193]) {
  harbor_device_hex(d->local, 32, out, 65);
  memcpy(out + 64, l->transport, 64);
  memcpy(out + 128, l->ratchet, 65);
}
static int code(struct harbor_link_pending *p) {
  char bytes[768];
  int n = snprintf(bytes, sizeof(bytes), "Harbor-link-v1|%s|%s|%s|%s|%s",
                   p->request, p->person, p->head, p->owner, p->proposal);
  return n > 0 && n < (int)sizeof(bytes) ? hash_hex(bytes, (size_t)n, p->code)
                                         : -1;
}
static int active_local(const struct harbor_devices *d) {
  for (size_t i = 0; i < d->count; i++)
    if (!memcmp(d->local, d->devices[i].signing, 32))
      return d->devices[i].active;
  return 0;
}
static int head(const struct harbor_devices *d, char out[65]) {
  return d->records
             ? hash_hex(d->chain + (d->records - 1) * HARBOR_DEVICE_RECORD_SIZE,
                        HARBOR_DEVICE_RECORD_SIZE, out)
             : -1;
}
static int pending(struct harbor_link_pending *p, const char *request) {
  return p->used && now() >= 0 && now() < p->expires &&
         !strcmp(p->request, request);
}
static void adopt(struct harbor_link *l) {
  struct harbor_link_pending *p = &l->outgoing;
  if (!p->confirmed || !p->roster[0])
    return;
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d) {
    failure(l, p->request, "device_unavailable");
    return;
  }
  const char *error =
      harbor_devices_operation(l->home, "device.adopt", l->transport,
                               l->ratchet, "", "", p->person, p->roster, 1, d);
  if (error)
    failure(l, p->request, error);
  else {
    p->sent = 1;
    state(l, p, "linked");
    char wire[256];
    snprintf(wire, sizeof(wire), "HD1|linked|%s|%s", p->request, p->person);
    (void)l->send(p->peer, wire);
  }
  free(d);
}
void harbor_link_operation(struct harbor_link *l, const omaq_op *op,
                           const char *peer, const char *peer_ratchet) {
  if (!omaq_message_id_ok(op->request)) {
    failure(l, op->request, "request_required");
    return;
  }
  const char *error = NULL;
  if (!strcmp(op->op, "device.link.request")) {
    if (!peer || !peer_ratchet || !hex_ok(peer, 64) ||
        !hex_ok(peer_ratchet, 64)) {
      failure(l, op->request, "device_session_not_ready");
      return;
    }
    if (l->outgoing.used && now() < l->outgoing.expires &&
        strcmp(l->outgoing.request, op->request)) {
      failure(l, op->request, "device_link_busy");
      return;
    }
    struct harbor_devices *d = read_state(l, "device.propose", &error);
    if (!d) {
      failure(l, op->request, error);
      return;
    }
    if (d->records) {
      free(d);
      failure(l, op->request, "device_already_linked");
      return;
    }
    size_t namesize = strlen(op->nickname);
    if (!namesize || namesize >= 48 ||
        !omaq_utf8_bytes_ok((const unsigned char *)op->nickname, namesize, 1)) {
      free(d);
      failure(l, op->request, "device_name_invalid");
      return;
    }
    struct harbor_link_pending *p = &l->outgoing;
    memset(p, 0, sizeof(*p));
    p->used = 1;
    p->submitted_consent = op->has_accept && op->accept;
    p->expires = now() + 300;
    snprintf(p->request, sizeof(p->request), "%s", op->request);
    snprintf(p->peer, sizeof(p->peer), "%s", peer);
    snprintf(p->name, sizeof(p->name), "%s", op->nickname);
    proposal(l, d, p->proposal);
    free(d);
    char hexname[97], wire[512];
    harbor_device_hex((const unsigned char *)p->name, namesize, hexname,
                      sizeof(hexname));
    snprintf(wire, sizeof(wire), "HD1|request|%s|%s|%s", p->request,
             p->proposal, hexname);
    if (l->send(p->peer, wire)) {
      memset(p, 0, sizeof(*p));
      failure(l, op->request, "device_session_not_ready");
    } else {
      p->retry = now() + 3;
      p->attempts = 1;
      state(l, p, "pending");
    }
    return;
  }
  if (!strcmp(op->op, "device.link.confirm")) {
    struct harbor_link_pending *p = &l->outgoing;
    if (!pending(p, op->request) || !p->person[0] ||
        strcmp(op->key, p->person) || !op->has_accept || !op->accept) {
      failure(l, op->request, "device_confirmation_required");
      return;
    }
    error = harbor_device_consent(l->home, l->transport, l->ratchet, p->person,
                                  1, p->proof);
    if (error) {
      failure(l, op->request, error);
      return;
    }
    p->confirmed = 1;
    char wire[512];
    snprintf(wire, sizeof(wire), "HD1|consent|%s|%s|%s", p->request, p->code,
             p->proof);
    (void)l->send(p->peer, wire);
    p->retry = now() + 3;
    if (p->roster[0])
      adopt(l);
    else
      state(l, p, "waiting-for-owner");
    return;
  }
  struct harbor_link_pending *p = &l->incoming;
  if (!pending(p, op->request)) {
    failure(l, op->request, "device_link_expired");
    return;
  }
  if (!strcmp(op->op, "device.link.decline")) {
    char wire[160];
    snprintf(wire, sizeof(wire), "HD1|declined|%s", p->request);
    (void)l->send(p->peer, wire);
    state(l, p, "declined");
    memset(p, 0, sizeof(*p));
    return;
  }
  if (strcmp(op->op, "device.link.accept") || !op->has_accept || !op->accept) {
    failure(l, op->request, "device_confirmation_required");
    return;
  }
  p->approved = 1;
  if (!p->proof[0]) {
    state(l, p, "waiting-for-device");
    return;
  }
  struct harbor_devices *d = read_state(l, "device.status", &error);
  char current[65], root[65];
  if (!d) {
    failure(l, op->request, error);
    return;
  }
  harbor_device_hex(d->root, 32, root, sizeof(root));
  if (!active_local(d) || strcmp(root, p->person) || head(d, current)) {
    free(d);
    failure(l, op->request, "device_link_stale");
    return;
  }
  int found = -1;
  for (size_t i = 0; i < d->count; i++) {
    char binding[193];
    unsigned char bytes[96];
    memcpy(bytes, d->devices[i].signing, 32);
    memcpy(bytes + 32, d->devices[i].transport, 32);
    memcpy(bytes + 64, d->devices[i].ratchet, 32);
    harbor_device_hex(bytes, 96, binding, sizeof(binding));
    if (!strncmp(binding, p->proposal, 64)) {
      if (strcmp(binding, p->proposal) || !d->devices[i].active) {
        free(d);
        failure(l, op->request, "device_revoked");
        return;
      }
      found = (int)i;
    }
  }
  if (p->sent) {
    char *roster = malloc(HARBOR_DEVICE_ROSTER_HEX + 1);
    if (!roster) {
      free(d);
      failure(l, op->request, "device_unavailable");
      return;
    }
    harbor_device_hex(d->chain, d->records * HARBOR_DEVICE_RECORD_SIZE, roster,
                      HARBOR_DEVICE_ROSTER_HEX + 1);
    int stale = found < 0 || strcmp(roster, p->roster);
    free(roster);
    free(d);
    if (stale) {
      failure(l, op->request, "device_link_stale");
      return;
    }
  } else {
    if (strcmp(current, p->head)) {
      free(d);
      failure(l, op->request, "device_link_stale");
      return;
    }
    /* Re-consenting to the exact already-active binding resumes a link after
     * restart. A revoked or changed binding can never use this path. */
    if (found < 0)
      error = harbor_devices_operation(l->home, "device.authorize",
                                       l->transport, l->ratchet, p->proposal,
                                       p->name, "", p->proof, 1, d);
    if (!error)
      harbor_device_hex(d->chain, d->records * HARBOR_DEVICE_RECORD_SIZE,
                        p->roster, sizeof(p->roster));
    free(d);
    if (error) {
      failure(l, op->request, error);
      return;
    }
  }
  p->sent = 1;
  char *wire = malloc(HARBOR_DEVICE_ROSTER_HEX + 256);
  if (!wire) {
    failure(l, op->request, "device_unavailable");
    return;
  }
  snprintf(wire, HARBOR_DEVICE_ROSTER_HEX + 256, "HD1|roster|%s|%s|%s",
           p->request, p->person, p->roster);
  int rc = l->send(p->peer, wire);
  free(wire);
  /* Authorization is durable before send; retry this exact accepted roster. */
  p->sent = 1;
  p->retry = now() + 3;
  p->attempts++;
  if (rc)
    failure(l, op->request, "device_link_send_failed");
  else
    state(l, p, "sent");
}
void harbor_link_receive(struct harbor_link *l, const char *peer,
                         const char *peer_ratchet, const char *plain) {
  char *copy = strdup(plain), *save = NULL;
  if (!copy)
    return;
  char *version = strtok_r(copy, "|", &save),
       *kind = strtok_r(NULL, "|", &save),
       *request = strtok_r(NULL, "|", &save);
  if (!version || strcmp(version, "HD1") || !kind || !request ||
      !omaq_message_id_ok(request) || strlen(request) >= 80)
    goto done;
  if (!strcmp(kind, "update")) {
    char *roster = strtok_r(NULL, "|", &save);
    if (!roster || strtok_r(NULL, "|", &save) || !hex_ok(request, 64))
      goto done;
    const char *error = NULL;
    struct harbor_devices *d = read_state(l, "device.status", &error);
    if (!d)
      goto done;
    char root[65];
    harbor_device_hex(d->root, 32, root, sizeof(root));
    int authorized = 0;
    for (size_t i = 0; i < d->count; i++) {
      char key[65], pin[65];
      harbor_device_hex(d->devices[i].transport, 32, key, sizeof(key));
      harbor_device_hex(d->devices[i].ratchet, 32, pin, sizeof(pin));
      if (d->devices[i].active && !strcmp(key, peer) &&
          !strcmp(pin, peer_ratchet))
        authorized = 1;
    }
    if (authorized && !strcmp(root, request))
      (void)harbor_devices_operation(l->home, "device.adopt", l->transport,
                                     l->ratchet, "", "", root, roster, 1, d);
    free(d);
  } else if (!strcmp(kind, "request")) {
    char *binding = strtok_r(NULL, "|", &save),
         *hexname = strtok_r(NULL, "|", &save);
    if (!binding || !hexname || strtok_r(NULL, "|", &save) ||
        !hex_ok(binding, 192) || strncmp(binding + 64, peer, 64) ||
        strcmp(binding + 128, peer_ratchet) || strlen(hexname) % 2 ||
        !strlen(hexname) || strlen(hexname) >= 96 ||
        !hex_ok(hexname, strlen(hexname)))
      goto done;
    struct harbor_link_pending *p = &l->incoming;
    if (p->used && now() < p->expires &&
        (strcmp(p->request, request) || strcmp(p->peer, peer))) {
      failure(l, request, "device_link_busy");
      goto done;
    }
    /* A retransmission must not replace already displayed verification state.
     */
    if (pending(p, request)) {
      if (strcmp(p->proposal, binding))
        goto done;
    } else {
      const char *error = NULL;
      struct harbor_devices *d = read_state(l, "device.status", &error);
      if (!d) {
        failure(l, request, error);
        goto done;
      }
      if (!active_local(d)) {
        free(d);
        goto done;
      }
      memset(p, 0, sizeof(*p));
      p->used = 1;
      p->expires = now() + 300;
      snprintf(p->request, sizeof(p->request), "%s", request);
      snprintf(p->peer, sizeof(p->peer), "%s", peer);
      snprintf(p->proposal, sizeof(p->proposal), "%s", binding);
      for (size_t i = 0; i < strlen(hexname) / 2; i++) {
        unsigned byte;
        if (sscanf(hexname + i * 2, "%2x", &byte) != 1) {
          free(d);
          goto done;
        }
        p->name[i] = (char)byte;
      }
      if (!omaq_utf8_bytes_ok((const unsigned char *)p->name,
                              strlen(hexname) / 2, 1)) {
        memset(p, 0, sizeof(*p));
        free(d);
        goto done;
      }
      harbor_device_hex(d->root, 32, p->person, sizeof(p->person));
      proposal(l, d, p->owner);
      int rc = head(d, p->head);
      free(d);
      if (rc || code(p)) {
        memset(p, 0, sizeof(*p));
        goto done;
      }
    }
    char wire[768];
    snprintf(wire, sizeof(wire), "HD1|challenge|%s|%s|%s|%s|%s", p->request,
             p->person, p->head, p->owner, p->code);
    if (!l->send(peer, wire))
      state(l, p, "requested");
  } else if (!strcmp(kind, "challenge")) {
    struct harbor_link_pending *p = &l->outgoing;
    char *person = strtok_r(NULL, "|", &save),
         *digest = strtok_r(NULL, "|", &save),
         *owner = strtok_r(NULL, "|", &save),
         *verify = strtok_r(NULL, "|", &save);
    if (!pending(p, request) || strcmp(p->peer, peer) || !person || !digest ||
        !owner || !verify || strtok_r(NULL, "|", &save) ||
        !hex_ok(person, 64) || !hex_ok(digest, 64) || !hex_ok(owner, 192) ||
        !hex_ok(verify, 64) || strncmp(owner + 64, peer, 64) ||
        strcmp(owner + 128, peer_ratchet))
      goto done;
    /* A changed challenge requires a fresh link request and consent. */
    if (p->person[0] && (strcmp(p->person, person) || strcmp(p->head, digest) ||
                         strcmp(p->owner, owner)))
      goto done;
    snprintf(p->person, sizeof(p->person), "%s", person);
    snprintf(p->head, sizeof(p->head), "%s", digest);
    snprintf(p->owner, sizeof(p->owner), "%s", owner);
    if (code(p) || strcmp(p->code, verify)) {
      memset(p, 0, sizeof(*p));
      goto done;
    }
    if (p->submitted_consent) {
      /* The initiating Link action consents to this pinned peer's identity.
       * Reuse the manual path after validating the exact challenge above. */
      omaq_op *confirm = calloc(1, sizeof(*confirm));
      if (!confirm) { failure(l, p->request, "device_unavailable"); goto done; }
      snprintf(confirm->op, sizeof(confirm->op), "device.link.confirm");
      snprintf(confirm->request, sizeof(confirm->request), "%s", p->request);
      snprintf(confirm->key, sizeof(confirm->key), "%s", p->person);
      confirm->has_accept = confirm->accept = 1;
      harbor_link_operation(l, confirm, NULL, NULL);
      free(confirm);
    } else state(l, p, "verify");
  } else if (!strcmp(kind, "consent")) {
    struct harbor_link_pending *p = &l->incoming;
    char *verify = strtok_r(NULL, "|", &save),
         *proof = strtok_r(NULL, "|", &save);
    if (!pending(p, request) || strcmp(p->peer, peer) || !verify || !proof ||
        strtok_r(NULL, "|", &save) || strcmp(p->code, verify) ||
        !hex_ok(proof, 128) || strncmp(p->proposal + 64, peer, 64) ||
        strcmp(p->proposal + 128, peer_ratchet))
      goto done;
    snprintf(p->proof, sizeof(p->proof), "%s", proof);
    if (p->approved) {
      omaq_op *op = calloc(1, sizeof(*op));
      if (!op)
        goto done;
      snprintf(op->op, sizeof(op->op), "device.link.accept");
      snprintf(op->request, sizeof(op->request), "%s", p->request);
      op->has_accept = op->accept = 1;
      harbor_link_operation(l, op, NULL, NULL);
      free(op);
    }
  } else if (!strcmp(kind, "roster")) {
    struct harbor_link_pending *p = &l->outgoing;
    char *person = strtok_r(NULL, "|", &save),
         *roster = strtok_r(NULL, "|", &save);
    if (!pending(p, request) || strcmp(p->peer, peer) || !person || !roster ||
        strtok_r(NULL, "|", &save) || strcmp(p->person, person) ||
        !strlen(roster) || strlen(roster) > HARBOR_DEVICE_ROSTER_HEX ||
        strlen(roster) % (HARBOR_DEVICE_RECORD_SIZE * 2) ||
        !hex_ok(roster, strlen(roster)))
      goto done;
    struct harbor_devices *d = calloc(1, sizeof(*d));
    if (!d)
      goto done;
    if (harbor_devices_decode(roster, d)) {
      free(d);
      goto done;
    }
    char root[65], current[65];
    harbor_device_hex(d->root, 32, root, sizeof(root));
    if (strcmp(root, p->person) || head(d, current)) {
      free(d);
      goto done;
    }
    int owner_valid = 0;
    for (size_t i = 0; i < d->count; i++) {
      unsigned char bytes[96];
      char binding[193];
      memcpy(bytes, d->devices[i].signing, 32);
      memcpy(bytes + 32, d->devices[i].transport, 32);
      memcpy(bytes + 64, d->devices[i].ratchet, 32);
      harbor_device_hex(bytes, 96, binding, sizeof(binding));
      if (!strcmp(binding, p->owner) && d->devices[i].active)
        owner_valid = 1;
    }
    const char *last =
        roster + (d->records - 1) * HARBOR_DEVICE_RECORD_SIZE * 2;
    /* Initial authorization extends the shown head; resuming an existing
     * exact binding returns the unchanged shown head after fresh consent. */
    int extends = !strncmp(last + 10 * 2, p->head, 64) &&
                  !strncmp(last + 42 * 2, p->owner, 64) &&
                  !strncmp(last + 74 * 2, p->proposal, 192);
    free(d);
    if (!owner_valid || (strcmp(current, p->head) && !extends))
      goto done;
    snprintf(p->roster, sizeof(p->roster), "%s", roster);
    if (p->confirmed)
      adopt(l);
    else
      state(l, p, "awaiting-confirmation");
  } else if (!strcmp(kind, "linked")) {
    struct harbor_link_pending *p = &l->incoming;
    char *person = strtok_r(NULL, "|", &save);
    if (pending(p, request) && !strcmp(p->peer, peer) && person &&
        !strcmp(person, p->person) && !strtok_r(NULL, "|", &save)) {
      p->confirmed = 1;
      state(l, p, "linked");
    }
  } else if (!strcmp(kind, "declined")) {
    struct harbor_link_pending *p = &l->outgoing;
    if (pending(p, request) && !strcmp(p->peer, peer)) {
      state(l, p, "declined");
      memset(p, 0, sizeof(*p));
    }
  }
done:
  free(copy);
}
void harbor_link_replay(struct harbor_link *l) {
  long long time = now();
  if (time < 0) return;
  struct harbor_link_pending *p = &l->incoming;
  if (p->used && !p->sent && time < p->expires)
    state(l, p, p->approved ? "waiting-for-device" : "requested");
  p = &l->outgoing;
  if (p->used && !p->sent && time < p->expires)
    state(l, p, p->confirmed ? "waiting-for-owner" : p->person[0] ? "verify" : "pending");
}
void harbor_link_tick(struct harbor_link *l) {
  struct harbor_link_pending *out = &l->outgoing, *in = &l->incoming;
  long long time = now();
  if (time < 0)
    return;
  if (out->used && !out->sent && !out->person[0] && time >= out->retry &&
      time < out->expires && out->attempts < 30) {
    char hexname[97], wire[512];
    harbor_device_hex((const unsigned char *)out->name, strlen(out->name),
                      hexname, sizeof(hexname));
    snprintf(wire, sizeof(wire), "HD1|request|%s|%s|%s", out->request,
             out->proposal, hexname);
    (void)l->send(out->peer, wire);
    out->retry = time + 3;
    out->attempts++;
  }
  if (out->used && out->confirmed && !out->sent && out->proof[0] &&
      time >= out->retry && time < out->expires && out->attempts < 60) {
    char wire[512];
    snprintf(wire, sizeof(wire), "HD1|consent|%s|%s|%s", out->request,
             out->code, out->proof);
    (void)l->send(out->peer, wire);
    out->retry = time + 3;
    out->attempts++;
  }
  if (in->used && in->sent && !in->confirmed && time >= in->retry &&
      time < in->expires && in->attempts < 30) {
    omaq_op *op = calloc(1, sizeof(*op));
    if (!op)
      return;
    snprintf(op->op, sizeof(op->op), "device.link.accept");
    snprintf(op->request, sizeof(op->request), "%s", in->request);
    op->has_accept = 1;
    op->accept = 1;
    harbor_link_operation(l, op, NULL, NULL);
    free(op);
    in->retry = time + 3;
  }
}
#endif
