#define _DEFAULT_SOURCE
#include "harbor_transport.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <time.h>

#define SLOTS 16
#define CHUNK 640u
#define HEADER 55u
#define TTL 300
struct transfer {
  char *data;
  size_t size, offset;
  char id[33], binding[129];
  int group;
  uint32_t target;
  time_t touched;
  uint64_t seq;
};
struct harbor_transport {
  struct transfer tx[SLOTS], rx[SLOTS];
  uint64_t sequence;
};
static time_t now(void) {
  struct timespec ts;
  return clock_gettime(CLOCK_MONOTONIC, &ts) == 0 ? ts.tv_sec : 0;
}
static void clear(struct transfer *p) {
  if (p->data) {
    explicit_bzero(p->data, p->size + 1);
    free(p->data);
  }
  memset(p, 0, sizeof(*p));
}
static int nibble(unsigned char c) {
  return c >= '0' && c <= '9'   ? c - '0'
         : c >= 'a' && c <= 'f' ? c - 'a' + 10
                                : -1;
}
static int decode(const char *s, size_t n, unsigned char *out) {
  for (size_t i = 0; i < n; i++) {
    int a = nibble(s[i * 2]), b = nibble(s[i * 2 + 1]);
    if (a < 0 || b < 0)
      return -1;
    out[i] = (unsigned char)((a << 4) | b);
  }
  return 0;
}
static void encode(const unsigned char *s, size_t n, char *out) {
  const char *hex = "0123456789abcdef";
  for (size_t i = 0; i < n; i++) {
    out[2 * i] = hex[s[i] >> 4];
    out[2 * i + 1] = hex[s[i] & 15];
  }
  out[2 * n] = 0;
}
harbor_transport *harbor_transport_new(void) {
  return calloc(1, sizeof(harbor_transport));
}
void harbor_transport_free(harbor_transport *t) {
  if (!t)
    return;
  for (int i = 0; i < SLOTS; i++) {
    clear(&t->tx[i]);
    clear(&t->rx[i]);
  }
  free(t);
}
int harbor_transport_pending(const harbor_transport *t) {
  if (!t)
    return 0;
  for (int i = 0; i < SLOTS; i++)
    if (t->tx[i].data)
      return 1;
  return 0;
}
int harbor_transport_send(harbor_transport *t, int group, uint32_t target,
                          const char *binding, const char *text) {
  if (!t || !binding || !binding[0] || strlen(binding) > 128 || !text)
    return -1;
  size_t n = strlen(text);
  int pending = 0, slot = -1;
  if (n > HARBOR_WIRE_MAX || !n)
    return -1;
  for (int i = 0; i < SLOTS; i++) {
    if (t->tx[i].data && t->tx[i].group == group && t->tx[i].target == target)
      pending = 1;
    if (!t->tx[i].data && slot < 0)
      slot = i;
  }
  if (n <= 1372 && !pending)
    return 0;
  if (slot < 0)
    return -1;
  struct transfer *p = &t->tx[slot];
  unsigned char id[16];
  if (getrandom(id, sizeof(id), 0) != (ssize_t)sizeof(id))
    return -1;
  p->data = strdup(text);
  if (!p->data)
    return -1;
  p->size = n;
  p->group = group;
  p->target = target;
  p->seq = ++t->sequence;
  p->touched = now();
  strcpy(p->binding, binding);
  encode(id, sizeof(id), p->id);
  return 1;
}
void harbor_transport_pump(harbor_transport *t, harbor_send_fn send,
                           void *context) {
  if (!t)
    return;
  for (int i = 0; i < SLOTS; i++) {
    struct transfer *p = &t->tx[i];
    if (!p->data)
      continue;
    if (now() - p->touched >= TTL) {
      /* The receiver may have expired an incomplete assembly. Retain accepted
       * messages during an outage and restart them from byte zero. */
      p->offset = 0;
      p->touched = now();
    }
    int blocked = 0;
    for (int j = 0; j < SLOTS; j++)
      if (t->tx[j].data && t->tx[j].group == p->group &&
          t->tx[j].target == p->target && t->tx[j].seq < p->seq)
        blocked = 1;
    if (blocked)
      continue;
    for (int batch = 0; batch < 4 && p->data; batch++) {
      char packet[HEADER + CHUNK * 2 + 1];
      size_t n = p->size - p->offset;
      if (n > CHUNK)
        n = CHUNK;
      int h = snprintf(packet, sizeof(packet), "HB1|%s|%08x|%08x|", p->id,
                       (unsigned)p->size, (unsigned)p->offset);
      if (h != HEADER) {
        clear(p);
        break;
      }
      encode((unsigned char *)p->data + p->offset, n, packet + HEADER);
      int rc = send(context, p->group, p->target, p->binding, packet);
      if (rc < 0) {
        if (rc == -2)
          clear(p);
        break;
      }
      p->offset += n;
      p->touched = now();
      if (p->offset == p->size)
        clear(p);
    }
  }
}
int harbor_transport_receive(harbor_transport *t, const char *binding,
                             const uint8_t *packet, size_t length,
                             char **complete) {
  *complete = NULL;
  if (length < 4 || memcmp(packet, "HB1|", 4))
    return 0;
  if (!t || !binding || strlen(binding) > 128 || length <= HEADER ||
      length > HEADER + CHUNK * 2 || packet[36] != '|' || packet[45] != '|' ||
      packet[54] != '|' || (length - HEADER) % 2)
    return 1;
  unsigned char id[16], sizebytes[4], offsetbytes[4];
  if (decode((const char *)packet + 4, 16, id) ||
      decode((const char *)packet + 37, 4, sizebytes) ||
      decode((const char *)packet + 46, 4, offsetbytes))
    return 1;
  size_t size = 0, offset = 0, n = (length - HEADER) / 2;
  for (int i = 0; i < 4; i++) {
    size = (size << 8) | sizebytes[i];
    offset = (offset << 8) | offsetbytes[i];
  }
  if (!size || size > HARBOR_WIRE_MAX || offset > size || n > size - offset)
    return 1;
  int slot = -1, free_slot = -1;
  for (int i = 0; i < SLOTS; i++) {
    struct transfer *p = &t->rx[i];
    if (p->data && now() - p->touched >= TTL)
      clear(p);
    if (!p->data && free_slot < 0)
      free_slot = i;
    if (p->data && !strcmp(p->binding, binding) &&
        !memcmp(p->id, packet + 4, 32))
      slot = i;
  }
  if (slot >= 0 && offset == 0) {
    clear(&t->rx[slot]);
    free_slot = slot;
    slot = -1;
  }
  if (slot < 0) {
    if (offset || free_slot < 0)
      return 1;
    slot = free_slot;
    struct transfer *p = &t->rx[slot];
    p->data = calloc(size + 1, 1);
    if (!p->data)
      return 1;
    p->size = size;
    strcpy(p->binding, binding);
    memcpy(p->id, packet + 4, 32);
  }
  struct transfer *p = &t->rx[slot];
  if (p->size != size || p->offset != offset ||
      decode((const char *)packet + HEADER, n,
             (unsigned char *)p->data + offset)) {
    clear(p);
    return 1;
  }
  p->offset += n;
  p->touched = now();
  if (p->offset == p->size) {
    if (memchr(p->data, 0, p->size)) {
      clear(p);
      return 1;
    }
    *complete = p->data;
    p->data = NULL;
    memset(p, 0, sizeof(*p));
  }
  return 1;
}
