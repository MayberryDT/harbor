#define _DEFAULT_SOURCE
#include "devices.h"
#include "endpoint.h"
#include "people.h"
#include "text.h"
#ifdef HAVE_SIGNAL
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Roster v2: version, operation, BE sequence, predecessor SHA256,
 * signer Ed25519, subject Ed25519, Tox key, Signal key, zero-padded UTF8 name,
 * subject consent, issuer Ed25519 signature. Issuer signatures bind the domain
 * and person root; subject consent binds the exact root and endpoint tuple. */
#define RECORD HARBOR_DEVICE_RECORD_SIZE
#define CONSENT 218u
#define SIGNED 282u
#define PREV 10u
#define SIGNER 42u
#define SUBJECT 74u
#define TOXKEY 106u
#define SIGNALKEY 138u
#define NAME 170u
static const char domain[] = "Harbor-device-roster-v2";

int harbor_device_hex(const unsigned char *bytes, size_t length, char *out,
                      size_t size) {
  static const char digits[] = "0123456789abcdef";
  if (length > (size - 1) / 2)
    return -1;
  for (size_t i = 0; i < length; i++) {
    out[i * 2] = digits[bytes[i] >> 4];
    out[i * 2 + 1] = digits[bytes[i] & 15];
  }
  out[length * 2] = 0;
  return 0;
}
static int unhex(const char *text, unsigned char *out, size_t n) {
  if (!text || strlen(text) != n * 2)
    return -1;
  for (size_t i = 0; i < n; i++) {
    unsigned value = 0;
    for (size_t j = 0; j < 2; j++) {
      char c = text[i * 2 + j];
      unsigned v = c >= '0' && c <= '9'   ? (unsigned)(c - '0')
                   : c >= 'a' && c <= 'f' ? (unsigned)(c - 'a' + 10)
                                          : 16;
      if (v > 15)
        return -1;
      value = value * 16 + v;
    }
    out[i] = (unsigned char)value;
  }
  return 0;
}
static int digest(const void *bytes, size_t n, unsigned char out[32]) {
  unsigned length = 0;
  return EVP_Digest(bytes, n, out, &length, EVP_sha256(), NULL) == 1 &&
                 length == 32
             ? 0
             : -1;
}
static int public_key(const unsigned char seed[32], unsigned char public[32]) {
  EVP_PKEY *key =
      EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32);
  size_t n = 32;
  int rc = key && EVP_PKEY_get_raw_public_key(key, public, &n) == 1 && n == 32
               ? 0
               : -1;
  EVP_PKEY_free(key);
  return rc;
}
static int subject_consent(const unsigned char root[32],
                           const unsigned char binding[96],
                           unsigned char proof[64], const unsigned char *seed) {
  static const char label[] = "Harbor-device-consent-v2";
  unsigned char message[sizeof(label) + 128];
  memcpy(message, label, sizeof(label));
  memcpy(message + sizeof(label), root, 32);
  memcpy(message + sizeof(label) + 32, binding, 96);
  EVP_PKEY *key =
      seed ? EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32)
           : EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, NULL, binding, 32);
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  size_t n = 64;
  int ok = ctx && key &&
           (seed ? EVP_DigestSignInit(ctx, NULL, NULL, NULL, key) == 1 &&
                       EVP_DigestSign(ctx, proof, &n, message,
                                      sizeof(message)) == 1 &&
                       n == 64
                 : EVP_DigestVerifyInit(ctx, NULL, NULL, NULL, key) == 1 &&
                       EVP_DigestVerify(ctx, proof, 64, message,
                                        sizeof(message)) == 1);
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(key);
  return ok ? 0 : -1;
}
static int signature(unsigned char *record, const unsigned char root[32],
                     const unsigned char *seed) {
  unsigned char message[sizeof(domain) + 32 + SIGNED];
  memcpy(message, domain, sizeof(domain));
  memcpy(message + sizeof(domain), root, 32);
  memcpy(message + sizeof(domain) + 32, record, SIGNED);
  EVP_PKEY *key =
      seed ? EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32)
           : EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, NULL,
                                         record + SIGNER, 32);
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  int ok = 0;
  if (ctx && key) {
    if (seed) {
      size_t n = 64;
      ok = EVP_DigestSignInit(ctx, NULL, NULL, NULL, key) == 1 &&
           EVP_DigestSign(ctx, record + SIGNED, &n, message, sizeof(message)) ==
               1 &&
           n == 64;
    } else {
      ok = EVP_DigestVerifyInit(ctx, NULL, NULL, NULL, key) == 1 &&
           EVP_DigestVerify(ctx, record + SIGNED, 64, message,
                            sizeof(message)) == 1;
    }
  }
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(key);
  return ok ? 0 : -1;
}
static int secure_stat(int fd, int directory) {
  struct stat st;
  return fstat(fd, &st) == 0 && st.st_uid == geteuid() &&
                 !(st.st_mode & 0077) &&
                 (directory ? S_ISDIR(st.st_mode) : S_ISREG(st.st_mode)) &&
                 (directory || st.st_nlink == 1)
             ? 0
             : -1;
}
static int directory_named(const char *home, const char *name) {
  int parent = open(home, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (parent < 0 || secure_stat(parent, 1) != 0) {
    if (parent >= 0)
      close(parent);
    return -1;
  }
  if (mkdirat(parent, name, 0700) < 0 && errno != EEXIST) {
    close(parent);
    return -1;
  }
  int fd =
      openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (fd >= 0 && (secure_stat(fd, 1) != 0 || fsync(parent) != 0)) {
    close(fd);
    fd = -1;
  }
  close(parent);
  return fd;
}
static int directory(const char *home) {
  return directory_named(home, "devices");
}
static int read_file(int dir, const char *name, unsigned char *out, size_t cap,
                     size_t *n) {
  int fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  *n = 0;
  if (fd < 0)
    return errno == ENOENT ? 1 : -1;
  struct stat st;
  int rc = -1;
  if (secure_stat(fd, 0) != 0 || fstat(fd, &st) != 0 || st.st_size < 0 ||
      (uint64_t)st.st_size > cap)
    goto done;
  while (*n < (size_t)st.st_size) {
    ssize_t got = read(fd, out + *n, (size_t)st.st_size - *n);
    if (got < 0 && errno == EINTR)
      continue;
    if (got <= 0)
      goto done;
    *n += (size_t)got;
  }
  unsigned char extra;
  if (read(fd, &extra, 1) != 0)
    goto done;
  /* Readable bytes may be the result of an earlier failed commit. Authority
   * and intent readers must finish both barriers before reporting success. */
  if (fsync(fd) || fsync(dir))
    goto done;
  rc = 0;
done:
  close(fd);
  return rc;
}
static int write_all(int fd, const unsigned char *bytes, size_t n) {
  while (n) {
    ssize_t sent = write(fd, bytes, n);
    if (sent < 0 && errno == EINTR)
      continue;
    if (sent <= 0)
      return -1;
    bytes += sent;
    n -= (size_t)sent;
  }
  return fsync(fd);
}
static int create_file(int dir, const char *name, const unsigned char *bytes,
                       size_t n) {
  int fd = openat(dir, name,
                  O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0)
    return -1;
  int rc = write_all(fd, bytes, n);
  if (close(fd) != 0)
    rc = -1;
  if (fsync(dir) != 0)
    rc = -1;
  return rc;
}
static int create_anchor(int dir, const char *name,
                         const unsigned char binding[128]) {
  unsigned char random[16];
  char nonce[33], temporary[48];
  if (RAND_bytes(random, sizeof(random)) != 1)
    return -1;
  harbor_device_hex(random, sizeof(random), nonce, sizeof(nonce));
  snprintf(temporary, sizeof(temporary), ".anchor.%s", nonce);
  int fd = openat(dir, temporary,
                  O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0)
    return -1;
  int rc = write_all(fd, binding, 128);
  if (close(fd))
    rc = -1;
  if (!rc &&
      syscall(SYS_renameat2, dir, temporary, dir, name, RENAME_NOREPLACE))
    rc = -1;
  if (rc) {
    (void)unlinkat(dir, temporary, 0);
    (void)fsync(dir);
    return -1;
  }
  return fsync(dir);
}
static int replace_named(int dir, const char *name, const unsigned char *bytes,
                         size_t n) {
  unsigned char random[16];
  char hex[33], temporary[48];
  if (RAND_bytes(random, sizeof(random)) != 1)
    return -1;
  harbor_device_hex(random, 16, hex, sizeof(hex));
  snprintf(temporary, sizeof(temporary), ".roster.%s", hex);
  if (create_file(dir, temporary, bytes, n) != 0) {
    (void)unlinkat(dir, temporary, 0);
    (void)fsync(dir);
    return -1;
  }
  if (renameat(dir, temporary, dir, name) != 0) {
    unlinkat(dir, temporary, 0);
    return -1;
  }
  return fsync(dir);
}
static int replace_roster(int dir, const unsigned char *bytes, size_t n) {
  return replace_named(dir, "roster", bytes, n);
}
static int index_of(const struct harbor_devices *d,
                    const unsigned char key[32]) {
  for (size_t i = 0; i < d->count; i++)
    if (!memcmp(d->devices[i].signing, key, 32))
      return (int)i;
  return -1;
}
static int name_ok(const unsigned char *name) {
  size_t n = strnlen((const char *)name, 48);
  if (!n || n == 48 || !omaq_utf8_bytes_ok(name, n, 1))
    return 0;
  /* Keep names simple, bounded and unambiguous across IPC/terminal surfaces. */
  for (size_t i = 0; i < n; i++)
    if (name[i] < 32 || name[i] == 127)
      return 0;
  for (size_t i = n; i < 48; i++)
    if (name[i])
      return 0;
  return 1;
}
static int validate(struct harbor_devices *d) {
  d->count = 0;
  if (!d->records || d->records > HARBOR_DEVICE_RECORDS)
    return -1;
  memcpy(d->root, d->chain + SIGNER, 32);
  unsigned char previous[32] = {0};
  for (size_t i = 0; i < d->records; i++) {
    unsigned char *r = d->chain + i * RECORD;
    uint64_t sequence = 0;
    for (size_t j = 2; j < 10; j++)
      sequence = sequence * 256 + r[j];
    int signer = index_of(d, r + SIGNER), target = index_of(d, r + SUBJECT);
    if (r[0] != 2 || sequence != i || memcmp(r + PREV, previous, 32) ||
        !name_ok(r + NAME) || signature(r, d->root, NULL) != 0 ||
        subject_consent(d->root, r + SUBJECT, r + CONSENT, NULL))
      return -1;
    if (i == 0) {
      if (r[1] != 0 || signer != -1)
        return -1;
    } else if (signer < 0 || !d->devices[signer].active || r[1] == 0)
      return -1;
    if (r[1] == 0 || r[1] == 1) {
      if (target >= 0 || d->count == HARBOR_DEVICE_MAX)
        return -1;
      for (size_t j = 0; j < d->count; j++)
        if (!memcmp(d->devices[j].transport, r + TOXKEY, 32) ||
            !memcmp(d->devices[j].ratchet, r + SIGNALKEY, 32))
          return -1;
      struct harbor_device *entry = &d->devices[d->count++];
      memcpy(entry->signing, r + SUBJECT, 32);
      memcpy(entry->transport, r + TOXKEY, 32);
      memcpy(entry->ratchet, r + SIGNALKEY, 32);
      memcpy(entry->name, r + NAME, 48);
      entry->name[48] = 0;
      entry->active = 1;
    } else if (r[1] == 2) {
      if (target < 0 || !d->devices[target].active ||
          memcmp(d->devices[target].transport, r + TOXKEY, 32) ||
          memcmp(d->devices[target].ratchet, r + SIGNALKEY, 32))
        return -1;
      d->devices[target].active = 0;
    } else
      return -1;
    if (digest(r, RECORD, previous) != 0)
      return -1;
  }
  return 0;
}
int harbor_devices_decode(const char *roster, struct harbor_devices *out) {
  size_t chars = strlen(roster);
  memset(out, 0, sizeof(*out));
  if (!chars || chars % (RECORD * 2) || chars > HARBOR_DEVICE_ROSTER_HEX)
    return -1;
  out->records = chars / (RECORD * 2);
  return unhex(roster, out->chain, chars / 2) || validate(out) ? -1 : 0;
}
static int append_record(struct harbor_devices *d, const unsigned char seed[32],
                         int kind, const unsigned char binding[96],
                         const char *name, const unsigned char proof[64]) {
  if (d->records == HARBOR_DEVICE_RECORDS || !name || strlen(name) >= 48)
    return -1;
  unsigned char *r = d->chain + d->records * RECORD;
  memset(r, 0, RECORD);
  r[0] = 2;
  r[1] = (unsigned char)kind;
  uint64_t seq = d->records;
  for (size_t j = 10; j-- > 2;) {
    r[j] = (unsigned char)seq;
    seq >>= 8;
  }
  if (d->records && digest(r - RECORD, RECORD, r + PREV) != 0)
    return -1;
  if (public_key(seed, r + SIGNER) != 0)
    return -1;
  if (!d->records)
    memcpy(d->root, r + SIGNER, 32);
  memcpy(r + SUBJECT, binding, 96);
  memcpy(r + NAME, name, strlen(name));
  memcpy(r + CONSENT, proof, 64);
  if (signature(r, d->root, seed) != 0)
    return -1;
  d->records++;
  return validate(d);
}

const char *harbor_device_consent(const char *home, const char *transport,
                                  const char *ratchet, const char *root,
                                  int confirmed, char proof[129]) {
  if (!confirmed)
    return "device_confirmation_required";
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return "device_unavailable";
  const char *error = harbor_devices_operation(
      home, "device.propose", transport, ratchet, "", "", "", "", 0, d);
  unsigned char person[32], binding[96], seed[32] = {0}, bytes[64];
  int fd = -1;
  size_t n;
  if (!error &&
      (unhex(root, person, 32) || (d->records && memcmp(person, d->root, 32))))
    error = "device_person_mismatch";
  if (!error) {
    memcpy(binding, d->local, 32);
    if (unhex(transport, binding + 32, 32) ||
        unhex(ratchet, binding + 64, 32) || (fd = directory(home)) < 0 ||
        read_file(fd, "key", seed, sizeof(seed), &n) || n != 32 ||
        subject_consent(person, binding, bytes, seed) ||
        harbor_device_hex(bytes, 64, proof, 129))
      error = "device_state_invalid";
  }
  if (fd >= 0)
    close(fd);
  OPENSSL_cleanse(seed, sizeof(seed));
  free(d);
  return error;
}

const char *harbor_devices_operation(const char *home, const char *operation,
                                     const char *transport, const char *ratchet,
                                     const char *payload, const char *name,
                                     const char *key, const char *roster,
                                     int confirmed,
                                     struct harbor_devices *out) {
  const char *error = "device_state_invalid";
  unsigned char seed[32] = {0}, binding[96], rootseed[32] = {0}, proof[64];
  size_t n = 0;
  memset(out, 0, sizeof(*out));
  if (unhex(transport, binding + 32, 32) || unhex(ratchet, binding + 64, 32))
    return error;
  int dir = directory(home);
  if (dir < 0)
    return error;
  /* A valid conflicting successor is security state, never a transient error.
   */
  int fork =
      openat(dir, "fork", O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (fork >= 0) {
    close(fork);
    error = "device_roster_conflict";
    goto done;
  }
  if (errno != ENOENT)
    goto done;
  int rc = read_file(dir, "key", seed, sizeof(seed), &n);
  if (rc == 1) {
    if (RAND_bytes(seed, 32) != 1 || create_file(dir, "key", seed, 32) != 0)
      goto done;
  } else if (rc < 0 || n != 32)
    goto done;
  if (public_key(seed, out->local) != 0)
    goto done;
  memcpy(binding, out->local, 32);
  rc = read_file(dir, "roster", out->chain, sizeof(out->chain), &n);
  if (rc < 0 || (rc == 0 &&
                 (n % RECORD || !(out->records = n / RECORD) || validate(out))))
    goto done;
  unsigned char committed[32];
  size_t committed_n;
  int committed_rc =
      read_file(dir, "committed", committed, sizeof(committed), &committed_n);
  if (committed_rc < 0 || (committed_rc == 0 && committed_n != 32))
    goto done;
  if (committed_rc == 0 && !out->records) {
    error = "device_roster_missing";
    goto done;
  }
  if (out->records && committed_rc == 0 && memcmp(committed, out->root, 32))
    goto done;
  if (out->records && committed_rc == 1 &&
      create_file(dir, "committed", out->root, 32))
    goto done;
  if (strcmp(operation, "device.propose") == 0) {
    error = NULL;
    goto done;
  }
  if (strcmp(operation, "device.initialize") == 0) {
    if (out->records) {
      int local = index_of(out, out->local);
      if (local < 0 ||
          memcmp(binding + 32, out->devices[local].transport, 32) ||
          memcmp(binding + 64, out->devices[local].ratchet, 32)) {
        error = "device_binding_mismatch";
        goto done;
      }
      error = out->devices[local].active ? NULL : "device_revoked";
      goto done;
    }
    rc = read_file(dir, "recovery-key", rootseed, sizeof(rootseed), &n);
    if (rc < 0 || (rc == 0 && n != 32))
      goto done;
    if (rc == 1 && (RAND_bytes(rootseed, 32) != 1 ||
                    create_file(dir, "recovery-key", rootseed, 32) != 0))
      goto done;
    rc = read_file(dir, "initial", out->chain, RECORD, &n);
    if (rc < 0 || (rc == 0 && n != RECORD))
      goto done;
    if (rc == 0) {
      unsigned char root[32];
      out->records = 1;
      if (public_key(rootseed, root) || validate(out) ||
          memcmp(root, out->root, 32) ||
          memcmp(out->devices[0].signing, binding, 32) ||
          memcmp(out->devices[0].transport, binding + 32, 32) ||
          memcmp(out->devices[0].ratchet, binding + 64, 32))
        goto done;
    } else {
      if (public_key(rootseed, out->root) ||
          subject_consent(out->root, binding, proof, seed) ||
          append_record(out, rootseed, 0, binding, name, proof) != 0 ||
          create_file(dir, "initial", out->chain, RECORD))
        goto done;
    }
    /* Root key is distinct and never distributed through ordinary linking.
     * Recovery export will handle its separate authority explicitly. */
    if (replace_roster(dir, out->chain, out->records * RECORD) != 0 ||
        create_file(dir, "committed", out->root, 32))
      goto done;
    error = NULL;
    goto done;
  }
  if (strcmp(operation, "device.adopt") == 0) {
    if (!confirmed) {
      error = "device_confirmation_required";
      goto done;
    }
    struct harbor_devices *incoming = calloc(1, sizeof(*incoming));
    if (!incoming)
      goto done;
    size_t chars = strlen(roster);
    incoming->records = chars / (RECORD * 2);
    unsigned char expected[32];
    if (!chars || chars % (RECORD * 2) || chars > HARBOR_DEVICE_ROSTER_HEX ||
        unhex(key, expected, 32) || unhex(roster, incoming->chain, chars / 2) ||
        validate(incoming) || memcmp(expected, incoming->root, 32) ||
        (out->records && memcmp(out->root, incoming->root, 32))) {
      free(incoming);
      error = "device_roster_invalid";
      goto done;
    }
    size_t common =
        out->records < incoming->records ? out->records : incoming->records;
    if (memcmp(out->chain, incoming->chain, common * RECORD)) {
      /* Both chains validated under the same root. Preserve the competing
       * chain before returning; failure to persist is itself fail-closed. */
      if (create_file(dir, "fork", incoming->chain,
                      incoming->records * RECORD) == 0)
        error = "device_roster_conflict";
      free(incoming);
      goto done;
    }
    int local = index_of(incoming, out->local);
    if (local < 0 || memcmp(binding, incoming->devices[local].signing, 32) ||
        memcmp(binding + 32, incoming->devices[local].transport, 32) ||
        memcmp(binding + 64, incoming->devices[local].ratchet, 32)) {
      free(incoming);
      error = "device_binding_mismatch";
      goto done;
    }
    if (incoming->records < out->records) {
      free(incoming);
      error = "device_roster_stale";
      goto done;
    }
    if (replace_roster(dir, incoming->chain, incoming->records * RECORD) != 0 ||
        (committed_rc == 1 &&
         create_file(dir, "committed", incoming->root, 32))) {
      free(incoming);
      goto done;
    }
    memcpy(incoming->local, out->local, 32);
    *out = *incoming;
    free(incoming);
    error = NULL;
    goto done;
  }
  if (!out->records) {
    error = "device_not_linked";
    goto done;
  }
  int local = index_of(out, out->local);
  if (local < 0 || memcmp(binding + 32, out->devices[local].transport, 32) ||
      memcmp(binding + 64, out->devices[local].ratchet, 32)) {
    error = "device_binding_mismatch";
    goto done;
  }
  if (!strcmp(operation, "device.status")) {
    error = NULL;
    goto done;
  }
  if (!out->devices[local].active) {
    error = "device_revoked";
    goto done;
  }
  if (!confirmed) {
    error = "device_confirmation_required";
    goto done;
  }
  if (!strcmp(operation, "device.authorize")) {
    if (unhex(payload, binding, sizeof(binding)) || unhex(roster, proof, 64) ||
        subject_consent(out->root, binding, proof, NULL) ||
        append_record(out, seed, 1, binding, name, proof)) {
      error = "device_authorization_invalid";
      goto done;
    }
  } else if (!strcmp(operation, "device.revoke")) {
    unsigned char target[32];
    if (unhex(key, target, 32)) {
      error = "device_authorization_invalid";
      goto done;
    }
    int found = index_of(out, target);
    if (found < 0) {
      error = "device_authorization_invalid";
      goto done;
    }
    memcpy(binding, out->devices[found].signing, 32);
    memcpy(binding + 32, out->devices[found].transport, 32);
    memcpy(binding + 64, out->devices[found].ratchet, 32);
    for (size_t i = 0; i < out->records; i++) {
      const unsigned char *record = out->chain + i * RECORD;
      if (!memcmp(record + SUBJECT, binding, 96)) {
        memcpy(proof, record + CONSENT, 64);
        break;
      }
    }
    if (append_record(out, seed, 2, binding, out->devices[found].name, proof)) {
      error = "device_authorization_invalid";
      goto done;
    }
  } else {
    error = "device_operation_unsupported";
    goto done;
  }
  if (replace_roster(dir, out->chain, out->records * RECORD) == 0)
    error = NULL;
done:
  OPENSSL_cleanse(seed, sizeof(seed));
  OPENSSL_cleanse(rootseed, sizeof(rootseed));
  close(dir);
  return error;
}

int harbor_people_list(const char *home, char roots[][65], size_t capacity) {
  int fd = directory_named(home, "people");
  if (fd < 0)
    return -1;
  DIR *directory = fdopendir(fd);
  if (!directory) {
    close(fd);
    return -1;
  }
  struct dirent *entry;
  size_t count = 0;
  int result = -1;
  for (;;) {
    errno = 0;
    entry = readdir(directory);
    if (!entry) {
      if (!errno)
        result = (int)count;
      break;
    }
    if (strlen(entry->d_name) != 64)
      continue;
    unsigned char key[32];
    if (unhex(entry->d_name, key, 32))
      continue;
    if (count >= capacity || count >= HARBOR_PEOPLE_MAX)
      break;
    memcpy(roots[count++], entry->d_name, 65);
  }
  closedir(directory);
  return result;
}
int harbor_people_get(const char *home, const char *root,
                      struct harbor_devices *out, char name[129]) {
  unsigned char key[32];
  if (unhex(root, key, 32))
    return -1;
  memset(out, 0, sizeof(*out));
  int fd = directory_named(home, "people");
  if (fd < 0)
    return -1;
  size_t n = 0;
  int rc = read_file(fd, root, out->chain, sizeof(out->chain), &n);
  if (rc || !n || n % RECORD || !(out->records = n / RECORD) || validate(out) ||
      memcmp(out->root, key, 32)) {
    close(fd);
    return -1;
  }
  char path[80];
  snprintf(path, sizeof(path), "%s.fork", root);
  int fork = openat(fd, path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (fork >= 0) {
    close(fork);
    close(fd);
    return -2;
  }
  if (errno != ENOENT) {
    close(fd);
    return -1;
  }
  if (name) {
    snprintf(path, sizeof(path), "%s.name", root);
    unsigned char bytes[129];
    rc = read_file(fd, path, bytes, 128, &n);
    if (rc == 1) {
      snprintf(name, 129, "Contact");
    } else if (rc || !n || memchr(bytes, 0, n) ||
               !omaq_utf8_bytes_ok(bytes, n, 1)) {
      close(fd);
      return -1;
    } else {
      memcpy(name, bytes, n);
      name[n] = 0;
    }
  }
  close(fd);
  return 0;
}
int harbor_people_find(const char *home, const char *transport, const char *pin,
                       char root[65], struct harbor_devices *out) {
  unsigned char key[32], ratchet[32], binding[128];
  if (unhex(transport, key, 32) || (pin && unhex(pin, ratchet, 32)))
    return -1;
  int fd = directory_named(home, "endpoint-anchors");
  char path[80];
  size_t n;
  snprintf(path, sizeof(path), "%s", transport);
  if (fd < 0)
    return -1;
  int found = read_file(fd, path, binding, sizeof(binding), &n);
  close(fd);
  if (found == 1)
    return -3; /* No managed binding: explicit legacy compatibility. */
  if (found || n != sizeof(binding))
    return -1;
  harbor_device_hex(binding, 32, root, 65);
  if (harbor_people_get(home, root, out, NULL))
    return -1;
  for (size_t j = 0; j < out->count; j++)
    if (!memcmp(out->devices[j].transport, key, 32)) {
      if (memcmp(out->devices[j].signing, binding + 32, 32) ||
          memcmp(key, binding + 64, 32) ||
          memcmp(out->devices[j].ratchet, binding + 96, 32))
        return -1;
      if (pin && memcmp(out->devices[j].ratchet, ratchet, 32))
        return -1;
      return out->devices[j].active ? 1 : 0;
    }
  return -1;
}
int harbor_people_endorse(const char *home, const char *root,
                          const char *transport, const char *pin) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  unsigned char key[32], ratchet[32], binding[128];
  int valid = 0;
  if (d && !unhex(transport, key, 32) && !unhex(pin, ratchet, 32) &&
      !harbor_people_get(home, root, d, NULL))
    for (size_t i = 0; i < d->count; i++)
      if (d->devices[i].active && !memcmp(d->devices[i].transport, key, 32) &&
          !memcmp(d->devices[i].ratchet, ratchet, 32)) {
        memcpy(binding, d->root, 32);
        memcpy(binding + 32, d->devices[i].signing, 32);
        memcpy(binding + 64, key, 32);
        memcpy(binding + 96, ratchet, 32);
        valid = 1;
      }
  int fd = valid ? directory_named(home, "endpoint-anchors") : -1;
  char path[80];
  unsigned char previous[128];
  size_t n;
  snprintf(path, sizeof(path), "%s", transport);
  int rc = -1;
  if (fd >= 0) {
    int found = read_file(fd, path, previous, sizeof(previous), &n);
    if (found == 1)
      rc = create_anchor(fd, path, binding);
    else if (!found && n == sizeof(binding) &&
             !memcmp(previous, binding, sizeof(binding)))
      rc = fsync(fd);
    close(fd);
  }
  free(d);
  return rc;
}
int harbor_people_card_decode(const char *body,struct harbor_devices *d,char name[129]) {
  if(!body || strncmp(body,"HPC1|",5))return -1;
  const char *separator=strchr(body+5,'|');
  size_t length=separator?(size_t)(separator-body-5):0;
  if(!length || length>256 || length%2)return -1;
  char encoded[257];memcpy(encoded,body+5,length);encoded[length]=0;
  if(unhex(encoded,(unsigned char *)name,length/2) ||
     !omaq_utf8_bytes_ok((const unsigned char *)name,length/2,1))return -1;
  name[length/2]=0;
  return harbor_devices_decode(separator+1,d);
}
static const char *people_install(const char *home, const char *peer,
                                  const char *pin, const char *roster,
                                  const char *name, char root[65],int publish) {
  const char *error = "person_state_invalid";
  struct harbor_devices *incoming = calloc(1, sizeof(*incoming)),
                        *current = calloc(1, sizeof(*current));
  if (!incoming || !current) {
    free(incoming);
    free(current);
    return error;
  }
  int fd = -1;
  size_t name_n = name ? strlen(name) : 0;
  if (!name_n || name_n > 128 ||
      !omaq_utf8_bytes_ok((const unsigned char *)name, name_n, 1) ||
      harbor_devices_decode(roster, incoming)) {
    error = "person_roster_invalid";
    goto done;
  }
  if (peer) {
    unsigned char transport[32], ratchet[32];
    int match = 0;
    if (unhex(peer, transport, 32) || !pin || unhex(pin, ratchet, 32)) {
      error = "person_binding_mismatch";
      goto done;
    }
    for (size_t i = 0; i < incoming->count; i++)
      if (incoming->devices[i].active &&
          !memcmp(incoming->devices[i].transport, transport, 32) &&
          !memcmp(incoming->devices[i].ratchet, ratchet, 32))
        match = 1;
    if (!match) {
      error = "person_binding_mismatch";
      goto done;
    }
  }
  harbor_device_hex(incoming->root, 32, root, 65);
  fd = directory_named(home, "people");
  if (fd < 0)
    goto done;
  char fork_path[80];
  snprintf(fork_path, sizeof(fork_path), "%s.fork", root);
  int fork =
      openat(fd, fork_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (fork >= 0) {
    close(fork);
    error = "person_roster_conflict";
    goto done;
  }
  if (errno != ENOENT)
    goto done;
  size_t n;
  int found = read_file(fd, root, current->chain, sizeof(current->chain), &n);
  if (found < 0)
    goto done;
  if (found == 0) {
    if (!n || n % RECORD || !(current->records = n / RECORD) ||
        validate(current) || memcmp(current->root, incoming->root, 32))
      goto done;
    size_t common = current->records < incoming->records ? current->records
                                                         : incoming->records;
    if (memcmp(current->chain, incoming->chain, common * RECORD)) {
      if (!create_file(fd, fork_path, incoming->chain,
                       incoming->records * RECORD))
        error = "person_roster_conflict";
      goto done;
    }
    if (incoming->records < current->records) {
      error = "person_roster_stale";
      goto done;
    }
  } else {
    char roots[HARBOR_PEOPLE_MAX][65];
    int count = harbor_people_list(home, roots, HARBOR_PEOPLE_MAX);
    if (count < 0 || count >= (int)HARBOR_PEOPLE_MAX) {
      error = "person_capacity";
      goto done;
    }
  }
  /* Validate every conflict before writing any immutable anchor. */
  int ownfd = directory(home);
  if (ownfd < 0)
    goto done;
  int ownfound =
      read_file(ownfd, "roster", current->chain, sizeof(current->chain), &n);
  close(ownfd);
  if (ownfound < 0)
    goto done;
  if (ownfound == 0) {
    if (!n || n % RECORD || !(current->records = n / RECORD) ||
        validate(current))
      goto done;
    for (size_t i = 0; i < incoming->count; i++)
      for (size_t j = 0; j < current->count; j++)
        if (!memcmp(incoming->devices[i].transport,
                    current->devices[j].transport, 32) ||
            !memcmp(incoming->devices[i].ratchet, current->devices[j].ratchet,
                    32) ||
            !memcmp(incoming->devices[i].signing, current->devices[j].signing,
                    32)) {
          error = "person_binding_mismatch";
          goto done;
        }
  }
  int anchors = directory_named(home, "endpoint-anchors");
  if (anchors < 0)
    goto done;
  int conflict = 0;
  for (size_t i = 0; i < incoming->count; i++) {
    char transport[65];
    unsigned char anchored[128];
    harbor_device_hex(incoming->devices[i].transport, 32, transport,
                      sizeof(transport));
    int bound = read_file(anchors, transport, anchored, sizeof(anchored), &n);
    if (bound < 0 || (!bound && n != sizeof(anchored))) {
      conflict = 1;
      break;
    }
    /* Unendorsed roster overlaps reserve nothing. */
    if (!bound && (memcmp(anchored, incoming->root, 32) ||
                   memcmp(anchored + 32, incoming->devices[i].signing, 32) ||
                   memcmp(anchored + 96, incoming->devices[i].ratchet, 32))) {
      conflict = 1;
      error = "person_identity_changed";
      break;
    }
  }
  close(anchors);
  if (conflict)
    goto done;
  if(!publish){error=NULL;goto done;}
  if (replace_named(fd, root, incoming->chain, incoming->records * RECORD))
    goto done;
  char path[80];
  snprintf(path, sizeof(path), "%s.name", root);
  if (replace_named(fd, path, (const unsigned char *)name, name_n))
    goto done;
  if (peer && harbor_people_endorse(home, root, peer, pin))
    goto done;
  error = NULL;
done:
  if (fd >= 0)
    close(fd);
  free(incoming);
  free(current);
  return error;
}
const char *harbor_people_check(const char *home,const char *peer,const char *pin,
    const char *roster,const char *name,char root[65]) {
  return people_install(home,peer,pin,roster,name,root,0);
}
const char *harbor_people_install(const char *home,const char *peer,const char *pin,
    const char *roster,const char *name,char root[65]) {
  return people_install(home,peer,pin,roster,name,root,1);
}


/* Probe files are fixed canonical public metadata inside a private directory.
 */
int harbor_probe_id(const char *root, const char *proposal, char id[65]) {
  unsigned char tuple[128], hash[32];
  return unhex(root, tuple, 32) || unhex(proposal, tuple + 32, 96) ||
                 digest(tuple, sizeof(tuple), hash) ||
                 harbor_device_hex(hash, 32, id, 65)
             ? -1
             : 0;
}
int harbor_probe_get(const char *home, const char *key,
                     struct harbor_probe_record *out) {
  unsigned char bytes[137], transport[32];
  size_t n;
  if (unhex(key, transport, 32))
    return -1;
  int fd = directory_named(home, "endpoint-probes");
  if (fd < 0)
    return -1;
  int rc = read_file(fd, key, bytes, sizeof(bytes), &n);
  close(fd);
  if (rc)
    return rc;
  if (n != sizeof(bytes) || bytes[136] > 3)
    return -1;
  memset(out, 0, sizeof(*out));
  harbor_device_hex(bytes, 32, out->root, sizeof(out->root));
  harbor_device_hex(bytes + 32, 96, out->proposal, sizeof(out->proposal));
  char expected[65];
  if (harbor_probe_id(out->root, out->proposal, expected) ||
      strcmp(expected, key))
    return -1;
  for (size_t i = 128; i < 136; i++)
    out->expires = out->expires * 256 + bytes[i];
  if (!out->expires || out->expires > UINT64_C(253402300799))
    return -1;
  out->owned = bytes[136] & 1;
  out->closed = (bytes[136] >> 1) & 1;
  return 0;
}
static int private_list(const char *home, const char *name, char keys[][65]) {
  int fd = directory_named(home, name);
  if (fd < 0)
    return -1;
  DIR *dir = fdopendir(fd);
  if (!dir) {
    close(fd);
    return -1;
  }
  int count = 0;
  for (;;) {
    errno = 0;
    struct dirent *entry = readdir(dir);
    if (!entry) {
      if (errno)
        count = -1;
      break;
    }
    const char *nonce =
        !strncmp(entry->d_name, "roster.", 7)    ? entry->d_name + 7
        : !strncmp(entry->d_name, ".roster.", 8) ? entry->d_name + 8
                                                 : NULL;
    unsigned char staging_nonce[16];
    if (nonce && !unhex(nonce, staging_nonce, 16)) {
      struct stat st;
      if (fstatat(fd, entry->d_name, &st, AT_SYMLINK_NOFOLLOW) ||
          !S_ISREG(st.st_mode) || st.st_uid != getuid() || st.st_nlink != 1 ||
          (st.st_mode & 077) || unlinkat(fd, entry->d_name, 0) || fsync(fd)) {
        count = -1;
        break;
      }
      continue;
    }
    if (entry->d_name[0] == '.')
      continue;
    unsigned char key[32];
    if (unhex(entry->d_name, key, 32) || count >= (int)HARBOR_PROBE_MAX) {
      count = -1;
      break;
    }
    memcpy(keys[count++], entry->d_name, 65);
  }
  closedir(dir);
  return count;
}
int harbor_probe_list(const char *home, char keys[][65]) {
  return private_list(home, "endpoint-probes", keys);
}
int harbor_rendezvous_list(const char *home, char keys[][65]) {
  return private_list(home, "invite-rendezvous", keys);
}
int harbor_probe_put(const char *home, const char *key,
                     const struct harbor_probe_record *record) {
  unsigned char bytes[137], transport[32];
  char expected[65];
  if (unhex(key, transport, 32) || unhex(record->root, bytes, 32) ||
      unhex(record->proposal, bytes + 32, 96) ||
      harbor_probe_id(record->root, record->proposal, expected) ||
      strcmp(key, expected))
    return -1;
  uint64_t expiry = record->expires;
  for (size_t i = 136; i-- > 128;) {
    bytes[i] = (unsigned char)expiry;
    expiry >>= 8;
  }
  bytes[136] = (record->owned ? 1 : 0) | (record->closed ? 2 : 0);
  char keys[HARBOR_PROBE_MAX][65];
  int count = harbor_probe_list(home, keys);
  if (count < 0)
    return -1;
  int present = 0;
  for (int i = 0; i < count; i++)
    if (!strcmp(keys[i], key))
      present = 1;
  if (!present && count >= (int)HARBOR_PROBE_MAX)
    return -1;
  int fd = directory_named(home, "endpoint-probes");
  if (fd < 0)
    return -1;
  int rc = replace_named(fd, key, bytes, sizeof(bytes));
  close(fd);
  return rc;
}
int harbor_probe_drop(const char *home, const char *key) {
  unsigned char bytes[32];
  if (unhex(key, bytes, 32))
    return -1;
  int fd = directory_named(home, "endpoint-probes");
  if (fd < 0)
    return -1;
  int rc = unlinkat(fd, key, 0);
  if (rc && errno == ENOENT)
    rc = 0;
  if (!rc)
    rc = fsync(fd);
  close(fd);
  return rc;
}
static int endpoint_signature(const char *root, const char *nonce,
                              const char *proposal, unsigned char proof[64],
                              const unsigned char *seed) {
  static const char label[] = "Harbor-endpoint-endorsement-v2";
  unsigned char message[sizeof(label) + 144];
  memcpy(message, label, sizeof(label));
  if (unhex(nonce, message + sizeof(label), 16) ||
      unhex(root, message + sizeof(label) + 16, 32) ||
      unhex(proposal, message + sizeof(label) + 48, 96))
    return -1;
  EVP_PKEY *key =
      seed ? EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32)
           : EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, NULL,
                                         message + sizeof(label) + 48, 32);
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  size_t n = 64;
  int ok = ctx && key &&
           (seed ? EVP_DigestSignInit(ctx, NULL, NULL, NULL, key) == 1 &&
                       EVP_DigestSign(ctx, proof, &n, message,
                                      sizeof(message)) == 1 &&
                       n == 64
                 : EVP_DigestVerifyInit(ctx, NULL, NULL, NULL, key) == 1 &&
                       EVP_DigestVerify(ctx, proof, 64, message,
                                        sizeof(message)) == 1);
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(key);
  return ok ? 0 : -1;
}
int harbor_endpoint_verify(const char *root, const char *nonce,
                           const char *proposal, const char *proof) {
  unsigned char signature[64];
  return unhex(proof, signature, 64) ||
                 endpoint_signature(root, nonce, proposal, signature, NULL)
             ? -1
             : 0;
}
int harbor_endpoint_signature(const char *home, const char *transport,
                              const char *ratchet, const char *root,
                              const char *nonce, const char *proposal,
                              char proof[129]) {
  struct harbor_devices *d = calloc(1, sizeof(*d));
  if (!d)
    return -1;
  unsigned char person[32], binding[96], seed[32] = {0}, signature[64];
  size_t n;
  int rc = -1, fd = -1;
  if (harbor_devices_operation(home, "device.status", transport, ratchet, "",
                               "", "", "", 0, d) ||
      unhex(root, person, 32) || unhex(proposal, binding, 96) ||
      memcmp(person, d->root, 32) || memcmp(binding, d->local, 32) ||
      strncmp(proposal + 64, transport, 64) || strcmp(proposal + 128, ratchet))
    goto done;
  int active = 0;
  for (size_t i = 0; i < d->count; i++)
    if (!memcmp(binding, d->devices[i].signing, 32))
      active = d->devices[i].active;
  if (!active || (fd = directory(home)) < 0 ||
      read_file(fd, "key", seed, sizeof(seed), &n) || n != 32 ||
      endpoint_signature(root, nonce, proposal, signature, seed) ||
      harbor_device_hex(signature, 64, proof, 129))
    goto done;
  rc = 0;
done:
  if (fd >= 0)
    close(fd);
  OPENSSL_cleanse(seed, sizeof(seed));
  free(d);
  return rc;
}

int harbor_rendezvous_get(const char *home, const char *key,
                          struct harbor_rendezvous *out) {
  unsigned char transport[32], bytes[73];
  size_t n;
  if (unhex(key, transport, 32))
    return -1;
  int fd = directory_named(home, "invite-rendezvous");
  if (fd < 0)
    return -1;
  int rc = read_file(fd, key, bytes, sizeof(bytes), &n);
  close(fd);
  if (rc)
    return rc;
  if (n != sizeof(bytes) || !bytes[0] || !memchr(bytes, 0, 65))
    return -1;
  memset(out, 0, sizeof(*out));
  memcpy(out->invite, bytes, 65);
  size_t length = strlen(out->invite);
  for (size_t i = 0; i < 65; i++)
    if (i < length ? !((bytes[i] >= 'a' && bytes[i] <= 'z') ||
                       (bytes[i] >= 'A' && bytes[i] <= 'Z') ||
                       (bytes[i] >= '0' && bytes[i] <= '9') ||
                       bytes[i] == '-' || bytes[i] == '_')
                   : bytes[i] != 0)
      return -1;
  for (size_t i = 65; i < 73; i++)
    out->expires = out->expires * 256 + bytes[i];
  return !out->expires || out->expires > UINT64_C(253402300799) ? -1 : 0;
}
int harbor_rendezvous_put(const char *home, const char *key, const char *invite,
                          uint64_t expires) {
  unsigned char transport[32], bytes[73] = {0};
  size_t length = strlen(invite);
  if (unhex(key, transport, 32) || !length || length > 64 || !expires ||
      expires > UINT64_C(253402300799))
    return -1;
  for (size_t i = 0; i < length; i++)
    if (!((invite[i] >= 'a' && invite[i] <= 'z') ||
          (invite[i] >= 'A' && invite[i] <= 'Z') ||
          (invite[i] >= '0' && invite[i] <= '9') || invite[i] == '-' ||
          invite[i] == '_'))
      return -1;
  memcpy(bytes, invite, length);
  for (size_t i = 73; i-- > 65;) {
    bytes[i] = (unsigned char)expires;
    expires >>= 8;
  }
  char keys[HARBOR_PROBE_MAX][65];
  int count = harbor_rendezvous_list(home, keys), found = 0;
  if (count < 0)
    return -1;
  for (int i = 0; i < count; i++)
    if (!strcmp(keys[i], key))
      found = 1;
  if (!found && count >= (int)HARBOR_PROBE_MAX)
    return -1;
  int fd = directory_named(home, "invite-rendezvous");
  if (fd < 0)
    return -1;
  int rc = replace_named(fd, key, bytes, sizeof(bytes));
  close(fd);
  return rc;
}
int harbor_rendezvous_drop(const char *home, const char *key) {
  unsigned char transport[32];
  if (unhex(key, transport, 32))
    return -1;
  int fd = directory_named(home, "invite-rendezvous");
  if (fd < 0)
    return -1;
  int rc = unlinkat(fd, key, 0);
  if (rc && errno == ENOENT)
    rc = 0;
  if (!rc)
    rc = fsync(fd);
  close(fd);
  return rc;
}
#endif
