/*
 * ============================================================================
 * StreetVulkan Concurrent Logging Subsystem (include/logger.h)
 * ============================================================================
 * - Thread-safe logging protected by pthread_mutex_t across worker/render paths
 * - Six severity levels: TRACE, DEBUG, INFO, WARN, ERROR, and FATAL
 * - Runtime override via LOG_LEVEL environment variable or logger_set_level()
 * - Dual persistent output: human-readable log + structured NDJSON (.jsonl)
 * - Automatic log size rotation (up to 5 MiB x 3 backup files per stream)
 * - ISO-8601 UTC millisecond timestamps and optional ANSI TTY coloring
 * - Complies with ISO/IEC 25010 diagnosability & ISO/IEC 27001 audit controls
 * ============================================================================
 */
#ifndef LOGGER_H
#define LOGGER_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    LOG_LEVEL_TRACE = 0,
    LOG_LEVEL_DEBUG = 1,
    LOG_LEVEL_INFO  = 2,
    LOG_LEVEL_WARN  = 3,
    LOG_LEVEL_ERROR = 4,
    LOG_LEVEL_FATAL = 5
} LogLevel;

/* Initialize the logging subsystem.
 * Creates log_dir if needed and opens street_vulkan.log and street_vulkan.jsonl.
 * If LOG_LEVEL env var is set, it overrides min_level.
 * Returns 1 on success, 0 on failure (console logging still works).
 */
int logger_init(const char *log_dir, LogLevel min_level);

/* Flush and close log files. Safe to call multiple times. */
void logger_shutdown(void);

/* Runtime log level control. */
void logger_set_level(LogLevel level);
LogLevel logger_get_level(void);

/* Core logging function (prefer the LOG_* macros below). */
void logger_log(LogLevel level, const char *tag, const char *file, int line,
                const char *fmt, ...)
#if defined(__GNUC__) || defined(__clang__)
    __attribute__((format(printf, 5, 6)))
#endif
;

#define LOG_TRACE(tag, fmt, ...) logger_log(LOG_LEVEL_TRACE, (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)
#define LOG_DEBUG(tag, fmt, ...) logger_log(LOG_LEVEL_DEBUG, (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)
#define LOG_INFO(tag, fmt, ...)  logger_log(LOG_LEVEL_INFO,  (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)
#define LOG_WARN(tag, fmt, ...)  logger_log(LOG_LEVEL_WARN,  (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)
#define LOG_ERROR(tag, fmt, ...) logger_log(LOG_LEVEL_ERROR, (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)
#define LOG_FATAL(tag, fmt, ...) logger_log(LOG_LEVEL_FATAL, (tag), __FILE__, __LINE__, (fmt), ##__VA_ARGS__)

#ifdef __cplusplus
}
#endif

#endif /* LOGGER_H */
