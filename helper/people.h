#ifndef HARBOR_PEOPLE_H
#define HARBOR_PEOPLE_H
#include "devices.h"
#define HARBOR_PEOPLE_MAX 64u
/* Every stored contact root is anchored through an existing pinned peer or an
 * already-authorized sibling. Public rosters never replace a transport binding.
 */
/* Strict complete HPC1 metadata validation, before durable journal admission. */
int harbor_people_card_decode(const char *body,struct harbor_devices *devices,char name[129]);
/* Validate admission without publishing roster/name or endpoint anchors.
 * A detected signed fork may still be durably quarantined. */
const char *harbor_people_check(const char *home,const char *peer,const char *pin,
    const char *roster,const char *name,char root[65]);
const char *harbor_people_install(const char *home, const char *peer,
                                  const char *pin, const char *roster,
                                  const char *name, char root[65]);
int harbor_people_get(const char *home, const char *root,
                      struct harbor_devices *devices, char name[129]);
int harbor_people_list(const char *home, char roots[][65], size_t capacity);
/* Returns active=1, historical/revoked=0, absent=-3, error=-1. */
/* Only a directly authenticated endpoint endorsement may create an anchor. */
int harbor_people_endorse(const char *home, const char *root,
                          const char *transport, const char *pin);
int harbor_people_find(const char *home, const char *transport, const char *pin,
                       char root[65], struct harbor_devices *devices);
#endif
