/* PKTC packet framing.
 *
 * Layout:
 *
 *   header (8 bytes)
 *     0..3  magic "PKTC"
 *     4     version, must be PKT_VERSION
 *     5     entry_count
 *     6..7  reserved, little-endian u16, must be zero
 *
 *   entry (4-byte header, then name, then value)
 *     0     name_len,  1..PKT_MAX_NAME
 *     1     flags
 *     2..3  value_len, little-endian u16
 *     4..   name bytes, then value bytes
 *
 * Trailing bytes after the declared entry count are ignored.
 */

#include "pktcfg/pktcfg.h"

#include <stdlib.h>
#include <string.h>

static uint16_t read_u16le(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

pkt_status pkt_parse(const uint8_t *data, size_t size, pkt_config **out)
{
    pkt_config *cfg;
    size_t      off;
    unsigned    count;
    unsigned    i;

    if (out == NULL) {
        return PKT_ERR_NOMEM;
    }
    *out = NULL;

    if (data == NULL || size < PKT_HEADER_LEN) {
        return PKT_ERR_TRUNCATED;
    }
    if (memcmp(data, PKT_MAGIC, PKT_MAGIC_LEN) != 0) {
        return PKT_ERR_BAD_MAGIC;
    }
    if (data[4] != PKT_VERSION) {
        return PKT_ERR_BAD_VERSION;
    }
    if (read_u16le(data + 6) != 0) {
        return PKT_ERR_BAD_RESERVED;
    }

    count = data[5];

    cfg = calloc(1, sizeof(*cfg));
    if (cfg == NULL) {
        return PKT_ERR_NOMEM;
    }
    if (count > 0) {
        cfg->entries = calloc(count, sizeof(*cfg->entries));
        if (cfg->entries == NULL) {
            free(cfg);
            return PKT_ERR_NOMEM;
        }
    }

    off = PKT_HEADER_LEN;

    for (i = 0; i < count; i++) {
        unsigned       name_len;
        unsigned       flags;
        unsigned       value_len;
        const uint8_t *name;
        const uint8_t *value;
        pkt_entry     *entry;
        size_t         need;

        if (size - off < PKT_ENTRY_HDR) {
            pkt_config_free(cfg);
            return PKT_ERR_TRUNCATED;
        }

        name_len  = data[off];
        flags     = data[off + 1];
        value_len = read_u16le(data + off + 2);

        if (name_len == 0 || name_len > PKT_MAX_NAME) {
            pkt_config_free(cfg);
            return PKT_ERR_BAD_NAME_LEN;
        }
        if (size - off - PKT_ENTRY_HDR < (size_t)name_len + value_len) {
            pkt_config_free(cfg);
            return PKT_ERR_TRUNCATED;
        }

        name  = data + off + PKT_ENTRY_HDR;
        value = name + name_len;
        entry = &cfg->entries[i];

        memcpy(entry->name, name, name_len);
        entry->name[name_len] = '\0';
        entry->flags = (uint8_t)flags;

        need = pkt_decoded_length(value, value_len, (flags & PKT_FLAG_ESCAPED) != 0);

        entry->value = malloc(need + 1);
        if (entry->value == NULL) {
            pkt_config_free(cfg);
            return PKT_ERR_NOMEM;
        }

        entry->value_len = pkt_decode_into(entry->value, value, value_len,
                                           (flags & PKT_FLAG_ESCAPED) != 0);

        cfg->count = (size_t)i + 1;
        off += PKT_ENTRY_HDR + name_len + value_len;
    }

    cfg->count = count;
    *out = cfg;
    return PKT_OK;
}
