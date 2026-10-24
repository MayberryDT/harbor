#ifndef HARBOR_JOURNAL_H
#define HARBOR_JOURNAL_H
#ifdef HAVE_SIGNAL
#include <stddef.h>
#include <stdint.h>
struct harbor_sync_event;
struct harbor_journal;
struct harbor_journal_index {
  char origin[65], target[65], request[80], related[33];
  int request_class; /* 0 metadata, 1 message, 2 mutation. */
};
/* The caller validates protocol/authentication before insertion. SQLite is the
 * sole authority for imported events; public device/endpoint trust stays separate.
 * Opening completes a durable barrier before reads may authorize an ACK. */
struct harbor_journal *harbor_journal_open(const char *home,const char *owner);
void harbor_journal_close(struct harbor_journal *journal);
int harbor_journal_ready(struct harbor_journal *journal);
int harbor_journal_begin_import(struct harbor_journal *journal);
int harbor_journal_finish_import(struct harbor_journal *journal);
int harbor_journal_put(struct harbor_journal *journal,
    const struct harbor_sync_event *event,const char *wire,
    const struct harbor_journal_index *index,int *created);
/* 1 present, 0 absent, -1 unavailable; output is owned by the caller. */
struct harbor_journal_work {char id[33];unsigned cursor;int projected;};
int harbor_journal_work_batch(struct harbor_journal *journal,
    struct harbor_journal_work *work,size_t capacity);
int64_t harbor_journal_pending(struct harbor_journal *journal);
int harbor_journal_work_begin(struct harbor_journal *journal);
int harbor_journal_work_update(struct harbor_journal *journal,const char *id,
    unsigned cursor,int projected,int complete);
int harbor_journal_work_commit(struct harbor_journal *journal);
int harbor_journal_projected(struct harbor_journal *journal,const char *id);
/* A verified roster head changes delivery obligations, not event authority. */
int harbor_journal_roster(struct harbor_journal *journal,const char *scope,const char *head);
/* Crypto-ledger import is one transaction after event import. Existing legacy
 * files remain sealed inputs; these rows become sole durable authority. */
int harbor_journal_ledger_ready(struct harbor_journal *journal);
int harbor_journal_ledger_begin(struct harbor_journal *journal);
int harbor_journal_ledger_finish(struct harbor_journal *journal);
/* Buckets: outbox, inbox, ack, rekey. Get returns 1 present, 0 absent, -1 error;
 * put returns 1 inserted, 0 exact durable retry, -1 error/conflict. */
int harbor_journal_envelope_get(struct harbor_journal *journal,const char *bucket,
    const char *name,char **body,size_t *length);
int harbor_journal_envelope_put(struct harbor_journal *journal,const char *bucket,
    const char *name,const char *body,size_t length);
int harbor_journal_envelope_drop(struct harbor_journal *journal,const char *bucket,const char *name);
int64_t harbor_journal_envelope_count(struct harbor_journal *journal,const char *bucket,const char *peer);
/* Remove stale ciphertext and its rekey intent atomically, retaining events. */
int harbor_journal_envelope_rekey(struct harbor_journal *journal,const char *peer);
int harbor_journal_get(struct harbor_journal *journal,const char *id,char **wire);
int harbor_journal_request(struct harbor_journal *journal,const char *person,
    const char *author,int request_class,const char *request,char id[33]);
int harbor_journal_clock(struct harbor_journal *journal,uint64_t *own,uint64_t *observed);
int64_t harbor_journal_count(struct harbor_journal *journal);
/* NULL other visits all events, otherwise exactly this person's conversation.
 * Visits use a stable order and permit nested reads from the callback.
 * A positive callback result stops successfully; negative aborts. */
int harbor_journal_visit_contacts(struct harbor_journal *journal,
    int (*visitor)(const char *,void *),void *context);
int harbor_journal_visit(struct harbor_journal *journal,const char *other,
    int (*visitor)(const char *wire,void *context),void *context);
#endif
#endif
