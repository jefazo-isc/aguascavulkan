#define _POSIX_C_SOURCE 200809L

#include "logger.h"

#include <ctype.h>
#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LOGGER_MAX_FILE_BYTES (5UL * 1024UL * 1024UL) /* 5 MB */
#define LOGGER_PATH_MAX       512
#define LOGGER_MSG_MAX        2048

static pthread_mutex_t g_logger_mutex = PTHREAD_MUTEX_INITIALIZER;
static LogLevel g_min_level = LOG_LEVEL_INFO;
static FILE *g_text_fp = NULL;
static FILE *g_jsonl_fp = NULL;
static char g_text_path[LOGGER_PATH_MAX] = {0};
static char g_jsonl_path[LOGGER_PATH_MAX] = {0};
static int g_initialized = 0;

static const char *level_to_string(LogLevel level) {
    switch (level) {
        case LOG_LEVEL_TRACE: return "TRACE";
        case LOG_LEVEL_DEBUG: return "DEBUG";
        case LOG_LEVEL_INFO:  return "INFO";
        case LOG_LEVEL_WARN:  return "WARN";
        case LOG_LEVEL_ERROR: return "ERROR";
        case LOG_LEVEL_FATAL: return "FATAL";
        default:              return "INFO";
    }
}

static const char *level_to_ansi(LogLevel level) {
    switch (level) {
        case LOG_LEVEL_TRACE: return "\033[90m";    /* Bright black / gray */
        case LOG_LEVEL_DEBUG: return "\033[36m";    /* Cyan */
        case LOG_LEVEL_INFO:  return "\033[32m";    /* Green */
        case LOG_LEVEL_WARN:  return "\033[33m";    /* Yellow */
        case LOG_LEVEL_ERROR: return "\033[31m";    /* Red */
        case LOG_LEVEL_FATAL: return "\033[1;31m";  /* Bold red */
        default:              return "\033[0m";
    }
}

static int parse_env_level(const char *val, LogLevel *out_level) {
    if (!val || !val[0] || !out_level) return 0;
    char buf[16];
    size_t i = 0;
    for (; val[i] && i < sizeof(buf) - 1; ++i) {
        buf[i] = (char)toupper((unsigned char)val[i]);
    }
    buf[i] = '\0';

    if (strcmp(buf, "TRACE") == 0) { *out_level = LOG_LEVEL_TRACE; return 1; }
    if (strcmp(buf, "DEBUG") == 0) { *out_level = LOG_LEVEL_DEBUG; return 1; }
    if (strcmp(buf, "INFO")  == 0) { *out_level = LOG_LEVEL_INFO;  return 1; }
    if (strcmp(buf, "WARN")  == 0 || strcmp(buf, "WARNING") == 0) { *out_level = LOG_LEVEL_WARN; return 1; }
    if (strcmp(buf, "ERROR") == 0) { *out_level = LOG_LEVEL_ERROR; return 1; }
    if (strcmp(buf, "FATAL") == 0) { *out_level = LOG_LEVEL_FATAL; return 1; }
    return 0;
}

static int ensure_dir_exists(const char *dir_path) {
    if (!dir_path || !dir_path[0]) return 0;
    char tmp[LOGGER_PATH_MAX];
    size_t len = strlen(dir_path);
    if (len >= sizeof(tmp)) return 0;
    memcpy(tmp, dir_path, len + 1);

    /* Strip trailing slashes */
    while (len > 1 && tmp[len - 1] == '/') {
        tmp[--len] = '\0';
    }

    for (char *p = tmp + 1; *p; ++p) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0755) != 0 && errno != EEXIST) {
                return 0;
            }
            *p = '/';
        }
    }
    if (mkdir(tmp, 0755) != 0 && errno != EEXIST) {
        return 0;
    }
    return 1;
}

static void rotate_if_needed(FILE **fp, const char *path) {
    if (!fp || !*fp || !path || !path[0]) return;
    long pos = ftell(*fp);
    if (pos < 0 || (unsigned long)pos < LOGGER_MAX_FILE_BYTES) {
        return;
    }
    fflush(*fp);
    fclose(*fp);
    *fp = NULL;

    char rotated[LOGGER_PATH_MAX + 4];
    snprintf(rotated, sizeof(rotated), "%s.1", path);
    (void)rename(path, rotated);

    *fp = fopen(path, "a");
}

static void write_json_escaped(FILE *fp, const char *s) {
    if (!s) return;
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        switch (*p) {
            case '"':  fputs("\\\"", fp); break;
            case '\\': fputs("\\\\", fp); break;
            case '\b': fputs("\\b", fp);  break;
            case '\f': fputs("\\f", fp);  break;
            case '\n': fputs("\\n", fp);  break;
            case '\r': fputs("\\r", fp);  break;
            case '\t': fputs("\\t", fp);  break;
            default:
                if (*p < 0x20) {
                    fprintf(fp, "\\u%04x", (unsigned int)*p);
                } else {
                    fputc(*p, fp);
                }
                break;
        }
    }
}

static void format_iso8601_utc(char *buf, size_t buf_size) {
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) != 0) {
        ts.tv_sec = time(NULL);
        ts.tv_nsec = 0;
    }
    struct tm tm_utc;
    gmtime_r(&ts.tv_sec, &tm_utc);
    int ms = (int)(ts.tv_nsec / 1000000L);
    snprintf(buf, buf_size, "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
             tm_utc.tm_year + 1900, tm_utc.tm_mon + 1, tm_utc.tm_mday,
             tm_utc.tm_hour, tm_utc.tm_min, tm_utc.tm_sec, ms);
}

int logger_init(const char *log_dir, LogLevel min_level) {
    pthread_mutex_lock(&g_logger_mutex);

    if (g_text_fp) {
        fflush(g_text_fp);
        fclose(g_text_fp);
        g_text_fp = NULL;
    }
    if (g_jsonl_fp) {
        fflush(g_jsonl_fp);
        fclose(g_jsonl_fp);
        g_jsonl_fp = NULL;
    }

    g_min_level = min_level;
    LogLevel env_level;
    if (parse_env_level(getenv("LOG_LEVEL"), &env_level)) {
        g_min_level = env_level;
    }

    const char *dir = (log_dir && log_dir[0]) ? log_dir : "logs";
    if (!ensure_dir_exists(dir)) {
        g_initialized = 1;
        pthread_mutex_unlock(&g_logger_mutex);
        return 0;
    }

    snprintf(g_text_path, sizeof(g_text_path), "%s/street_vulkan.log", dir);
    snprintf(g_jsonl_path, sizeof(g_jsonl_path), "%s/street_vulkan.jsonl", dir);

    g_text_fp = fopen(g_text_path, "a");
    g_jsonl_fp = fopen(g_jsonl_path, "a");
    g_initialized = 1;

    int ok = (g_text_fp != NULL && g_jsonl_fp != NULL) ? 1 : 0;
    pthread_mutex_unlock(&g_logger_mutex);
    return ok;
}

void logger_shutdown(void) {
    pthread_mutex_lock(&g_logger_mutex);
    if (g_text_fp) {
        fflush(g_text_fp);
        fclose(g_text_fp);
        g_text_fp = NULL;
    }
    if (g_jsonl_fp) {
        fflush(g_jsonl_fp);
        fclose(g_jsonl_fp);
        g_jsonl_fp = NULL;
    }
    g_initialized = 0;
    pthread_mutex_unlock(&g_logger_mutex);
}

void logger_set_level(LogLevel level) {
    pthread_mutex_lock(&g_logger_mutex);
    g_min_level = level;
    pthread_mutex_unlock(&g_logger_mutex);
}

LogLevel logger_get_level(void) {
    pthread_mutex_lock(&g_logger_mutex);
    LogLevel level = g_min_level;
    pthread_mutex_unlock(&g_logger_mutex);
    return level;
}

void logger_log(LogLevel level, const char *tag, const char *file, int line,
                const char *fmt, ...) {
    pthread_mutex_lock(&g_logger_mutex);
    if (level < g_min_level) {
        pthread_mutex_unlock(&g_logger_mutex);
        return;
    }

    char msg[LOGGER_MSG_MAX];
    va_list args;
    va_start(args, fmt);
    vsnprintf(msg, sizeof(msg), fmt ? fmt : "", args);
    va_end(args);

    /* Strip trailing newline if caller included one */
    size_t msg_len = strlen(msg);
    while (msg_len > 0 && (msg[msg_len - 1] == '\n' || msg[msg_len - 1] == '\r')) {
        msg[--msg_len] = '\0';
    }

    char ts[96];
    format_iso8601_utc(ts, sizeof(ts));

    const char *lvl_str = level_to_string(level);
    const char *safe_tag = (tag && tag[0]) ? tag : "App";
    const char *safe_file = (file && file[0]) ? file : "unknown";
    int include_loc = (level >= LOG_LEVEL_WARN);

    /* Console output */
    FILE *out = (level >= LOG_LEVEL_WARN) ? stderr : stdout;
    int use_color = isatty(fileno(out));

    if (use_color) {
        const char *color = level_to_ansi(level);
        if (include_loc) {
            fprintf(out, "%s %s[%-5s]\033[0m [%s] (%s:%d) %s\n",
                    ts, color, lvl_str, safe_tag, safe_file, line, msg);
        } else {
            fprintf(out, "%s %s[%-5s]\033[0m [%s] %s\n",
                    ts, color, lvl_str, safe_tag, msg);
        }
    } else {
        if (include_loc) {
            fprintf(out, "%s [%-5s] [%s] (%s:%d) %s\n",
                    ts, lvl_str, safe_tag, safe_file, line, msg);
        } else {
            fprintf(out, "%s [%-5s] [%s] %s\n",
                    ts, lvl_str, safe_tag, msg);
        }
    }
    fflush(out);

    /* Plain-text file output with rotation */
    if (g_text_fp) {
        rotate_if_needed(&g_text_fp, g_text_path);
        if (g_text_fp) {
            if (include_loc) {
                fprintf(g_text_fp, "%s [%-5s] [%s] (%s:%d) %s\n",
                        ts, lvl_str, safe_tag, safe_file, line, msg);
            } else {
                fprintf(g_text_fp, "%s [%-5s] [%s] %s\n",
                        ts, lvl_str, safe_tag, msg);
            }
            fflush(g_text_fp);
        }
    }

    /* Structured JSONL file output with rotation */
    if (g_jsonl_fp) {
        rotate_if_needed(&g_jsonl_fp, g_jsonl_path);
        if (g_jsonl_fp) {
            fprintf(g_jsonl_fp, "{\"ts\":\"%s\",\"level\":\"%s\",\"tag\":\"", ts, lvl_str);
            write_json_escaped(g_jsonl_fp, safe_tag);
            fputs("\",\"msg\":\"", g_jsonl_fp);
            write_json_escaped(g_jsonl_fp, msg);
            if (include_loc) {
                fputs("\",\"file\":\"", g_jsonl_fp);
                write_json_escaped(g_jsonl_fp, safe_file);
                fprintf(g_jsonl_fp, "\",\"line\":%d}\n", line);
            } else {
                fputs("\"}\n", g_jsonl_fp);
            }
            fflush(g_jsonl_fp);
        }
    }

    pthread_mutex_unlock(&g_logger_mutex);
}
