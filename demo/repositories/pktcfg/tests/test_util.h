/* Minimal assertion harness. No external test framework: this target has to
 * configure and build from clean with nothing but a C compiler and CMake.
 */
#ifndef PKTCFG_TEST_UTIL_H
#define PKTCFG_TEST_UTIL_H

#include <stdio.h>
#include <string.h>

static int pkt_test_failures = 0;
static int pkt_test_checks   = 0;

#define CHECK(cond)                                                            \
    do {                                                                       \
        pkt_test_checks++;                                                     \
        if (!(cond)) {                                                         \
            pkt_test_failures++;                                               \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);    \
        }                                                                      \
    } while (0)

#define CHECK_EQ_INT(actual, expected)                                         \
    do {                                                                       \
        long long a_ = (long long)(actual);                                    \
        long long e_ = (long long)(expected);                                  \
        pkt_test_checks++;                                                     \
        if (a_ != e_) {                                                        \
            pkt_test_failures++;                                               \
            fprintf(stderr, "FAIL %s:%d: %s == %lld, expected %lld\n",         \
                    __FILE__, __LINE__, #actual, a_, e_);                      \
        }                                                                      \
    } while (0)

#define CHECK_EQ_STR(actual, expected)                                         \
    do {                                                                       \
        const char *a_ = (actual);                                             \
        const char *e_ = (expected);                                           \
        pkt_test_checks++;                                                     \
        if (a_ == NULL || strcmp(a_, e_) != 0) {                               \
            pkt_test_failures++;                                               \
            fprintf(stderr, "FAIL %s:%d: %s == \"%s\", expected \"%s\"\n",     \
                    __FILE__, __LINE__, #actual, a_ ? a_ : "(null)", e_);      \
        }                                                                      \
    } while (0)

#define CHECK_EQ_MEM(actual, expected, n)                                      \
    do {                                                                       \
        pkt_test_checks++;                                                     \
        if ((actual) == NULL || memcmp((actual), (expected), (n)) != 0) {      \
            pkt_test_failures++;                                               \
            fprintf(stderr, "FAIL %s:%d: %s does not match %s over %zu bytes\n",\
                    __FILE__, __LINE__, #actual, #expected, (size_t)(n));      \
        }                                                                      \
    } while (0)

#define TEST_REPORT(name)                                                      \
    do {                                                                       \
        printf("%s: %d checks, %d failure(s)\n", (name), pkt_test_checks,      \
               pkt_test_failures);                                             \
        return pkt_test_failures == 0 ? 0 : 1;                                 \
    } while (0)

#endif /* PKTCFG_TEST_UTIL_H */
