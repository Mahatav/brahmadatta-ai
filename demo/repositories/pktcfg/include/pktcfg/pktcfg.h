/* pktcfg - a small parser for the PKTC binary configuration packet format.
 *
 * Purpose-built controlled demo target for Brahmadatta AI. See README.md.
 */
#ifndef PKTCFG_PKTCFG_H
#define PKTCFG_PKTCFG_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Wire format constants. */
#define PKT_MAGIC        "PKTC"
#define PKT_MAGIC_LEN    4u
#define PKT_HEADER_LEN   8u
#define PKT_VERSION      1u
#define PKT_ENTRY_HDR    4u
#define PKT_MAX_NAME     63u

/* A literal tab byte, and the `\t` escape, both normalise to this many spaces. */
#define PKT_TAB_WIDTH    4u

/* Entry flags. */
#define PKT_FLAG_ESCAPED 0x01u

typedef enum {
    PKT_OK = 0,
    PKT_ERR_BAD_MAGIC,
    PKT_ERR_BAD_VERSION,
    PKT_ERR_BAD_RESERVED,
    PKT_ERR_TRUNCATED,
    PKT_ERR_BAD_NAME_LEN,
    PKT_ERR_NOMEM
} pkt_status;

typedef struct {
    char    name[PKT_MAX_NAME + 1]; /* NUL-terminated */
    char   *value;                  /* NUL-terminated, heap-allocated */
    size_t  value_len;              /* decoded length, excluding the NUL */
    uint8_t flags;                  /* wire flags for this entry */
} pkt_entry;

typedef struct {
    pkt_entry *entries;
    size_t     count;
} pkt_config;

/* Parse a complete PKTC packet. On PKT_OK, *out owns a config the caller must
 * release with pkt_config_free(). On any error *out is set to NULL. */
pkt_status pkt_parse(const uint8_t *data, size_t size, pkt_config **out);

void        pkt_config_free(pkt_config *cfg);
size_t      pkt_config_count(const pkt_config *cfg);
const char *pkt_config_get(const pkt_config *cfg, const char *name);
const char *pkt_status_str(pkt_status status);

/* ---- The single fuzzable entry point --------------------------------------
 * Takes a raw byte buffer and its length, parses it, and releases everything.
 * Always returns 0; it exists to be driven by a fuzzer or a replay tool, and
 * reports defects through the sanitizer, not through its return value. */
int pktcfg_fuzz_one_input(const uint8_t *data, size_t size);

/* ---- Internal decoder, exposed for unit testing --------------------------- */

/* Predicted size, in bytes, of the decoded form of `src` (excluding the NUL). */
size_t pkt_decoded_length(const uint8_t *src, size_t len, int escaped);

/* Decode `src` into `dst`, which the caller sized from pkt_decoded_length()
 * plus one byte for the NUL terminator. Returns the number of bytes written,
 * excluding the NUL. */
size_t pkt_decode_into(char *dst, const uint8_t *src, size_t len, int escaped);

#ifdef __cplusplus
}
#endif

#endif /* PKTCFG_PKTCFG_H */
