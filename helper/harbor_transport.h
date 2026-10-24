#ifndef HARBOR_TRANSPORT_H
#define HARBOR_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>
#define HARBOR_TEXT_MAX 65536u
#define HARBOR_PLAIN_MAX (HARBOR_TEXT_MAX + 1024u)
#define HARBOR_WIRE_MAX (HARBOR_PLAIN_MAX * 2u + 2048u)
#define HARBOR_ESC_MAX (HARBOR_TEXT_MAX * 6u + 1u)
#define HARBOR_EVENT_MAX (HARBOR_ESC_MAX + 2048u)
typedef struct harbor_transport harbor_transport;
typedef int (*harbor_send_fn)(void *, int, uint32_t, const char *,
                              const char *);
harbor_transport *harbor_transport_new(void);
void harbor_transport_free(harbor_transport *t);
int harbor_transport_pending(const harbor_transport *t);
/* 1 = queued, 0 = use legacy packet, -1 = queue full/invalid. */
int harbor_transport_send(harbor_transport *t, int group, uint32_t target,
                          const char *binding, const char *text);
void harbor_transport_pump(harbor_transport *t, harbor_send_fn send,
                           void *context);
/* Consumes HB1 frames. A completed string is owned by caller. */
int harbor_transport_receive(harbor_transport *t, const char *binding,
                             const uint8_t *packet, size_t length,
                             char **complete);
#endif
