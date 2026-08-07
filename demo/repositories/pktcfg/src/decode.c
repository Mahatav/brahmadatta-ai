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
/* Value decoding and normalisation for the PKTC format.
 *
 * Two passes over the same bytes:
 *   pkt_decoded_length()  sizes the output buffer
 *   pkt_decode_into()     writes it
 *
 * The two passes must agree on every byte they consume and produce. They do
 * not. See README.md for the write-up; the divergence is on the literal-tab
 * branch and it is the seeded defect for this target.
 */

#include "pktcfg/pktcfg.h"

static int is_hex(uint8_t c)
{
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

static uint8_t hex_val(uint8_t c)
{
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    return (uint8_t)(c - 'A' + 10);
}

/* Expand one tab into PKT_TAB_WIDTH spaces. Shared by the escape branch and
 * the literal branch so both forms normalise identically. */
static size_t emit_tab(char *dst, size_t out)
{
    for (unsigned k = 0; k < PKT_TAB_WIDTH; k++) {
        dst[out++] = ' ';
    }
    return out;
}

size_t pkt_decoded_length(const uint8_t *src, size_t len, int escaped)
{
    size_t need = 0;
    size_t i = 0;

    while (i < len) {
        uint8_t c = src[i];

        if (escaped && c == '\\' && i + 1 < len) {
            uint8_t e = src[i + 1];
            switch (e) {
            case 'n':
            case 'r':
            case '0':
            case '\\':
                need += 1;
                i += 2;
                break;
            case 't':
                need += PKT_TAB_WIDTH;
                i += 2;
                break;
            case 'x':
                if (i + 3 < len && is_hex(src[i + 2]) && is_hex(src[i + 3])) {
                    need += 1;
                    i += 4;
                } else {
                    need += 1;
                    i += 1;
                }
                break;
            default:
                need += 1;
                i += 2;
                break;
            }
            continue;
        }

        /* Every remaining byte is copied through as-is. */
        need += 1;
        i += 1;
    }

    return need;
}

size_t pkt_decode_into(char *dst, const uint8_t *src, size_t len, int escaped)
{
    size_t out = 0;
    size_t i = 0;

    while (i < len) {
        uint8_t c = src[i];

        if (escaped && c == '\\' && i + 1 < len) {
            uint8_t e = src[i + 1];
            switch (e) {
            case 'n':
                dst[out++] = '\n';
                i += 2;
                break;
            case 'r':
                dst[out++] = '\r';
                i += 2;
                break;
            case '0':
                dst[out++] = '\0';
                i += 2;
                break;
            case '\\':
                dst[out++] = '\\';
                i += 2;
                break;
            case 't':
                out = emit_tab(dst, out);
                i += 2;
                break;
            case 'x':
                if (i + 3 < len && is_hex(src[i + 2]) && is_hex(src[i + 3])) {
                    dst[out++] = (char)((hex_val(src[i + 2]) << 4) | hex_val(src[i + 3]));
                    i += 4;
                } else {
                    dst[out++] = '\\';
                    i += 1;
                }
                break;
            default:
                dst[out++] = (char)e;
                i += 2;
                break;
            }
            continue;
        }

        if (c == '\t') {
            /* A literal tab is normalised the same way the `\t` escape is.
             * pkt_decoded_length() above counts this byte as one, so the
             * buffer allocated by pkt_parse() is PKT_TAB_WIDTH - 1 bytes
             * short for every literal tab in the value. */
            out = emit_tab(dst, out);
            i += 1;
            continue;
        }

        dst[out++] = (char)c;
        i += 1;
    }

    dst[out] = '\0';
    return out;
}
