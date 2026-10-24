#ifndef HARBOR_DEVICES_H
#define HARBOR_DEVICES_H
#include <stddef.h>
/* Public authorization records only. Private device keys never leave this
 * module. */
#define HARBOR_DEVICE_RECORD_SIZE 346u
#define HARBOR_DEVICE_RECORDS 64u
#define HARBOR_DEVICE_ROSTER_HEX                                               \
  (HARBOR_DEVICE_RECORD_SIZE * HARBOR_DEVICE_RECORDS * 2u)
#define HARBOR_DEVICE_MAX 32u
struct harbor_device {
  unsigned char signing[32], transport[32], ratchet[32];
  char name[49];
  int active;
};
struct harbor_devices {
  unsigned char root[32], local[32];
  struct harbor_device devices[HARBOR_DEVICE_MAX];
  size_t count, records;
  unsigned char chain[HARBOR_DEVICE_RECORD_SIZE * HARBOR_DEVICE_RECORDS];
};
/* Errors are stable user-facing IPC codes, no secret contents. */
const char *harbor_devices_operation(const char *home, const char *operation,
                                     const char *transport, const char *ratchet,
                                     const char *payload, const char *name,
                                     const char *key, const char *roster,
                                     int confirmed, struct harbor_devices *out);
/* Subject proof binds the person root and exact local Ed/Tox/Signal tuple. */
const char *harbor_device_consent(const char *home, const char *transport,
                                  const char *ratchet, const char *root,
                                  int confirmed, char proof[129]);
int harbor_devices_decode(const char *roster, struct harbor_devices *out);
int harbor_device_hex(const unsigned char *bytes, size_t length, char *out,
                      size_t size);
#endif
