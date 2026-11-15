/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef LG6851F_BOOT_TRACE_H
#define LG6851F_BOOT_TRACE_H

#ifdef LG6851F_BOOT_TRACE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#ifndef LG6851F_TRACE_PATH
#define LG6851F_TRACE_PATH "/tmp/lg6851f-boot-stages.log"
#endif
#ifndef LG6851F_KMSG_PATH
#define LG6851F_KMSG_PATH "/dev/kmsg"
#endif
#ifndef LG6851F_READY_PATH
#define LG6851F_READY_PATH "/tmp/lg6851f-init-complete"
#endif
#ifndef LG6851F_BOOT_ID_PATH
#define LG6851F_BOOT_ID_PATH "/proc/sys/kernel/random/boot_id"
#endif

/* A passive PID-1 readiness receipt, independent of the optional trace file.
 * Boot-control writes stay in the late, guarded userspace worker. */
static inline void lg6851f_boot_ready(int running)
{
 struct timespec stamp;
 char boot_id[38], line[80];
 int fd, length, saved_errno = errno;
 ssize_t count;
 size_t i;

 if (getpid() != 1)
  goto out;
 if (!running) {
  (void)unlink(LG6851F_READY_PATH);
  goto out;
 }
 fd = open(LG6851F_BOOT_ID_PATH, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
 if (fd < 0)
  goto out;
 count = read(fd, boot_id, sizeof(boot_id));
 close(fd);
 if (count != 37 || boot_id[36] != '\n')
  goto out;
 boot_id[36] = '\0';
 for (i = 0; i < 36; i++) {
  if (i == 8 || i == 13 || i == 18 || i == 23) {
   if (boot_id[i] != '-')
    goto out;
  } else if (!((boot_id[i] >= '0' && boot_id[i] <= '9') ||
               (boot_id[i] >= 'a' && boot_id[i] <= 'f'))) {
   goto out;
  }
 }
 if (clock_gettime(CLOCK_BOOTTIME, &stamp))
  goto out;
 length = snprintf(line, sizeof(line), "%s %lld\n", boot_id,
                   (long long)stamp.tv_sec);
 if (length <= 0 || (size_t)length >= sizeof(line))
  goto out;
 fd = open(LG6851F_READY_PATH,
           O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
 if (fd < 0)
  goto out;
 count = write(fd, line, length);
 close(fd);
 if (count != length)
  (void)unlink(LG6851F_READY_PATH);
out:
 errno = saved_errno;
}

/* Only append to the private file initialized by the board preinit helper.
 * No filesystem creation, waiting, fsync, RPC, extra child or errno changes. */
static inline void lg6851f_boot_trace(const char *phase, const char *fmt, ...)
{
 struct timespec stamp;
 struct stat st;
 char detail[160], line[320];
 va_list args;
 int fd, kfd, length, saved_errno = errno;

 fd = open(LG6851F_TRACE_PATH,
           O_WRONLY | O_APPEND | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
 if (fd < 0)
  goto out;
 if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
     (st.st_mode & (S_IWGRP | S_IWOTH)) || st.st_size > 1048576 ||
     clock_gettime(CLOCK_BOOTTIME, &stamp))
  goto close_file;
 va_start(args, fmt);
 vsnprintf(detail, sizeof(detail), fmt, args);
 va_end(args);
 length = snprintf(line, sizeof(line),
                   "LG6851F_BOOT_STAGE uptime=%lld.%03ld phase=%s %s\n",
                   (long long)stamp.tv_sec, stamp.tv_nsec / 1000000,
                   phase, detail);
 if (length <= 0 || (size_t)length >= sizeof(line))
  goto close_file;
 if (write(fd, line, length) != length)
  goto close_file;
 kfd = open(LG6851F_KMSG_PATH, O_WRONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
 if (kfd >= 0) {
  if (!fstat(kfd, &st) && S_ISCHR(st.st_mode)) {
   char message[sizeof(line) + 3];
   int count = snprintf(message, sizeof(message), "<7>%s", line);
   if (count > 0 && (size_t)count < sizeof(message))
    (void)write(kfd, message, count);
  }
  close(kfd);
 }
close_file:
 close(fd);
out:
 errno = saved_errno;
}
#else
#define lg6851f_boot_trace(...) ((void)0)
#define lg6851f_boot_ready(...) ((void)0)
#endif
#endif
