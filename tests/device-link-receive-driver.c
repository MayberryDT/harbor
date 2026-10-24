/* Review boundary cases, defined before this harness:
 * 1. A known-revoked exact Tox/Signal sender must not create fork state.
 * 2. A still-active sender carrying valid concurrent chains must retain fork detection.
 * This calls the decrypted receive boundary; it is not a network-delivery test. */
#include "device_link.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int send_noop(const char *peer,const char *plain){(void)peer;(void)plain;return 0;}
static void emit_noop(const char *json){(void)json;}
int main(int argc,char **argv) {
 if(argc!=8)return 2;
 struct harbor_link *l=calloc(1,sizeof(*l));
 struct harbor_devices *d=calloc(1,sizeof(*d));
 if(!l||!d)return 3;
 l->home=argv[1];snprintf(l->transport,65,"%s",argv[2]);snprintf(l->ratchet,65,"%s",argv[3]);l->send=send_noop;l->emit=emit_noop;
 const char *error=harbor_devices_operation(l->home,"device.status",l->transport,l->ratchet,"","","","",0,d);
 if(error){printf("initial state error: %s\n",error);return 4;}
 int active=-1;
 for(size_t i=0;i<d->count;i++){char key[65],pin[65];harbor_device_hex(d->devices[i].transport,32,key,65);harbor_device_hex(d->devices[i].ratchet,32,pin,65);if(!strcmp(key,argv[4])&&!strcmp(pin,argv[5]))active=d->devices[i].active;}
 char *roster=calloc(HARBOR_DEVICE_ROSTER_HEX+1,1),*wire=malloc(HARBOR_DEVICE_ROSTER_HEX+128);
 FILE *f=fopen(argv[7],"r");if(!f)return 5;
 size_t n=fread(roster,1,HARBOR_DEVICE_ROSTER_HEX,f);fclose(f);if(!n)return 6;
 snprintf(wire,HARBOR_DEVICE_ROSTER_HEX+128,"HD1|update|%s|%s",argv[6],roster);
 harbor_link_receive(l,argv[4],argv[5],wire);
 error=harbor_devices_operation(l->home,"device.status",l->transport,l->ratchet,"","","","",0,d);
 printf("{\"sender_active_before\":%d,\"status_after\":\"%s\"}\n",active,error?error:"ok");
 free(roster);free(wire);free(d);free(l);return 0;
}
