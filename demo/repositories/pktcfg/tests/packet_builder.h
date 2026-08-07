/* ============================================================================
 * DELIBERATELY VULNERABLE - Brahmadatta AI controlled demo target.
 *
 * This file is part of `pktcfg`, a fixture authored for Brahmadatta AI's own
 * testing. It contains a SEEDED heap-buffer-overflow on purpose. It is not a
 * library, it is not maintained, and it must never be vendored, packaged, or
 * copied into anything that parses real input.
 *
 * The defect, its location and its bug class are documented in
 * demo/repositories/pktcfg/README.md.
 * ============================================================================
 */
/* Builds well-formed PKTC packets for the tests, so the test bodies read as
 * intent rather than as hex dumps.
 */
#ifndef PKTCFG_PACKET_BUILDER_H
#define PKTCFG_PACKET_BUILDER_H

#include "pktcfg/pktcfg.h"

#include <string.h>

#define PB_CAP 4096

typedef struct {
    uint8_t  buf[PB_CAP];
    size_t   len;
    unsigned entries;
} pkt_builder;

static inline void pb_init(pkt_builder *b)
{
    memset(b, 0, sizeof(*b));
    memcpy(b->buf, PKT_MAGIC, PKT_MAGIC_LEN);
    b->buf[4] = PKT_VERSION;
    b->buf[5] = 0;
    b->buf[6] = 0;
    b->buf[7] = 0;
    b->len = PKT_HEADER_LEN;
    b->entries = 0;
}

/* Append an entry. `value` may contain NUL bytes; `value_len` is authoritative. */
static inline void pb_entry(pkt_builder *b, const char *name, unsigned flags,
                     const void *value, size_t value_len)
{
    size_t name_len = strlen(name);

    b->buf[b->len++] = (uint8_t)name_len;
    b->buf[b->len++] = (uint8_t)flags;
    b->buf[b->len++] = (uint8_t)(value_len & 0xffu);
    b->buf[b->len++] = (uint8_t)((value_len >> 8) & 0xffu);
    memcpy(b->buf + b->len, name, name_len);
    b->len += name_len;
    if (value_len > 0) {
        memcpy(b->buf + b->len, value, value_len);
        b->len += value_len;
    }
    b->entries++;
    b->buf[5] = (uint8_t)b->entries;
}

static inline void pb_entry_str(pkt_builder *b, const char *name, unsigned flags,
                         const char *value)
{
    pb_entry(b, name, flags, value, strlen(value));
}

/* Override the declared entry count, for the truncation tests. */
static inline void pb_set_count(pkt_builder *b, unsigned count)
{
    b->buf[5] = (uint8_t)count;
}

#endif /* PKTCFG_PACKET_BUILDER_H */
