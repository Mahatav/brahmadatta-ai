/* Lifetime and lookup helpers for a parsed PKTC configuration. */

#include "pktcfg/pktcfg.h"

#include <stdlib.h>
#include <string.h>

void pkt_config_free(pkt_config *cfg)
{
    size_t i;

    if (cfg == NULL) {
        return;
    }
    if (cfg->entries != NULL) {
        for (i = 0; i < cfg->count; i++) {
            free(cfg->entries[i].value);
        }
        free(cfg->entries);
    }
    free(cfg);
}

size_t pkt_config_count(const pkt_config *cfg)
{
    return cfg == NULL ? 0u : cfg->count;
}

const char *pkt_config_get(const pkt_config *cfg, const char *name)
{
    size_t i;

    if (cfg == NULL || name == NULL) {
        return NULL;
    }
    for (i = 0; i < cfg->count; i++) {
        if (strcmp(cfg->entries[i].name, name) == 0) {
            return cfg->entries[i].value;
        }
    }
    return NULL;
}

const char *pkt_status_str(pkt_status status)
{
    switch (status) {
    case PKT_OK:                return "ok";
    case PKT_ERR_BAD_MAGIC:     return "bad magic";
    case PKT_ERR_BAD_VERSION:   return "bad version";
    case PKT_ERR_BAD_RESERVED:  return "reserved field not zero";
    case PKT_ERR_TRUNCATED:     return "truncated packet";
    case PKT_ERR_BAD_NAME_LEN:  return "bad name length";
    case PKT_ERR_NOMEM:         return "out of memory";
    }
    return "unknown";
}
