#define _GNU_SOURCE
/* E2E syscall fault shim, loaded only into a disposable native helper. */
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int directory_suffix(int fd, const char *suffix) {
  char link[64], path[1024];
  snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
  ssize_t n = readlink(link, path, sizeof(path) - 1);
  if (n < 0)
    return 0;
  path[n] = 0;
  size_t length = (size_t)n;
  size_t wanted = strlen(suffix);
  return length >= wanted && !strcmp(path + length - wanted, suffix);
}
static int enabled(const char *name) {
  const char *path = getenv(name);
  return path && access(path, F_OK) == 0;
}
static int anchor_file(int fd) {
  char link[64], path[1024];
  snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
  ssize_t n = readlink(link, path, sizeof(path) - 1);
  if (n < 0)
    return 0;
  path[n] = 0;
  const char *name = strstr(path, "/endpoint-anchors/");
  return name && name[18] != 0;
}
static void fault_seen(const char *label) {
  const char *path = getenv("HARBOR_E2E_ANCHOR_FAULT_SEEN");
  if (!path)
    return;
  int fd =
      open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (fd >= 0) {
    ssize_t (*real_write)(int, const void *, size_t) =
        dlsym(RTLD_NEXT, "write");
    int (*real_fsync)(int) = dlsym(RTLD_NEXT, "fsync");
    (void)real_write(fd, label, strlen(label));
    (void)real_fsync(fd);
    close(fd);
  }
}
static void sqlite_fault_seen(const char *label) {
  fault_seen(label);
  const char *path=getenv("HARBOR_E2E_SQLITE_FAULT_HITS");if(!path)return;
  int fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW,0600);
  if(fd<0)return;
  ssize_t (*real_write)(int,const void *,size_t)=dlsym(RTLD_NEXT,"write");
  int (*real_sync)(int)=dlsym(RTLD_NEXT,"fsync");
  (void)real_write(fd,label,strlen(label));(void)real_write(fd,"\n",1);
  (void)real_sync(fd);close(fd);
}
ssize_t write(int fd, const void *bytes, size_t length) {
  int previous = errno;
  ssize_t (*real_write)(int, const void *, size_t) = dlsym(RTLD_NEXT, "write");
  static int partial = -1;
  int crash = enabled("HARBOR_E2E_CRASH_ANCHOR_WRITE"),
      fail = enabled("HARBOR_E2E_FAIL_ANCHOR_WRITE");
  if (!crash && !fail)
    partial = -1;
  if ((crash || fail) && anchor_file(fd)) {
    fault_seen(crash ? "partial-write-crash" : "partial-write");
    if (partial != fd && length > 8) {
      partial = fd;
      errno = previous;
      ssize_t n = real_write(fd, bytes, 8);
      if (crash)
        _exit(78);
      return n;
    }
    errno = ENOSPC;
    return -1;
  }
  errno = previous;
  return real_write(fd, bytes, length);
}
/* SQLite uses fdatasync for WAL commits on Linux. Exercise actual storage
 * errors; no helper production branch is altered by this shim. */
static int journal_file(int fd) {
  return directory_suffix(fd,"/sync/journal.sqlite") ||
    directory_suffix(fd,"/sync/journal.sqlite-wal");
}
int fdatasync(int fd) {
  int (*real_sync)(int)=dlsym(RTLD_NEXT,"fdatasync");
  if(journal_file(fd) && enabled("HARBOR_E2E_FAIL_EVENT_FSYNC")){
    sqlite_fault_seen(directory_suffix(fd,"/sync/journal.sqlite-wal")?"sqlite-wal-sync":"sqlite-main-sync");
    errno=EIO;return -1;
  }
  return real_sync(fd);
}
/* Force a query error after one returned row, including when SQLite's page
 * cache would otherwise avoid another disk read. This checks error propagation
 * at the public database cursor, rather than pretending readdir is still used. */
int sqlite3_step(void *statement) {
  int (*real_step)(void *)=dlsym(RTLD_NEXT,"sqlite3_step");
  const char *(*sql)(void *)=dlsym(RTLD_NEXT,"sqlite3_sql");
  static void *scan;static int seen;
  const char *query=sql(statement);
  if(!enabled("HARBOR_E2E_FAIL_EVENT_SCAN")){scan=NULL;seen=0;}
  else if(query && !strncmp(query,"SELECT wire FROM events",22)) {
    if(scan==statement && seen){sqlite_fault_seen("sqlite-query-error");return 10;} /* SQLITE_IOERR */
    scan=statement;seen=1;
  }
  return real_step(statement);
}
int fsync(int fd) {
  if(journal_file(fd) && enabled("HARBOR_E2E_FAIL_EVENT_FSYNC")){
    sqlite_fault_seen(directory_suffix(fd,"/sync/journal.sqlite-wal")?"sqlite-wal-sync":"sqlite-main-sync");
    errno=EIO;return -1;
  }
  int previous = errno;
  int (*real_fsync)(int) = dlsym(RTLD_NEXT, "fsync");
  if (directory_suffix(fd, "/sync/events") &&
      enabled("HARBOR_E2E_FAIL_EVENT_FSYNC")) {
    errno = EIO;
    return -1;
  }
  if (directory_suffix(fd, "/people") &&
      enabled("HARBOR_E2E_FAIL_CONTACT_FSYNC")) {
    errno = EIO;
    return -1;
  }
  if (anchor_file(fd) && enabled("HARBOR_E2E_FAIL_ANCHOR_FILE_FSYNC")) {
    fault_seen("file-fsync");
    errno = EIO;
    return -1;
  }
  if (directory_suffix(fd, "/endpoint-anchors") &&
      enabled("HARBOR_E2E_FAIL_ANCHOR_DIR_FSYNC")) {
    fault_seen("directory-fsync");
    errno = EIO;
    return -1;
  }
  if (directory_suffix(fd, "/devices") &&
      enabled("HARBOR_E2E_FAIL_DEVICES_FSYNC")) {
    fault_seen("devices-fsync");
    errno = EIO;
    return -1;
  }
  errno = previous;
  return real_fsync(fd);
}
struct dirent *readdir(DIR *dir) {
  int incoming_errno = errno;
  struct dirent *(*real_readdir)(DIR *) = dlsym(RTLD_NEXT, "readdir");
  static unsigned seen;
  int enabled_now = enabled("HARBOR_E2E_FAIL_EVENT_SCAN");
  int events = directory_suffix(dirfd(dir), "/sync/events");
  if (!enabled_now)
    seen = 0;
  else if (events && seen) {
    errno = EIO;
    return NULL;
  }
  errno = incoming_errno;
  struct dirent *entry = real_readdir(dir);
  int result_errno = errno;
  if (entry && entry->d_name[0] != '.' && events && enabled_now)
    seen++;
  errno = result_errno;
  return entry;
}
