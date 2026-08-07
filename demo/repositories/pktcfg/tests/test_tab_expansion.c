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
/* Tab normalisation.
 *
 * THIS IS THE ASYMMETRY TEST. It is the one that separates a correct fix for
 * the seeded heap-buffer-overflow from the tempting crash-site fix:
 *
 *   - correct fix (teach pkt_decoded_length() that a literal tab expands):
 *       overflow gone, every assertion below still holds.
 *   - crash-only fix (stop expanding tabs inside emit_tab()):
 *       overflow gone, and every assertion below about four spaces fails.
 *
 * Do not weaken these assertions to make a patch pass. See README.md.
 */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    /* The sizing pass agrees that one `\t` escape is PKT_TAB_WIDTH bytes. */
    CHECK_EQ_INT(pkt_decoded_length((const uint8_t *)"\\t", 2, 1), PKT_TAB_WIDTH);
    CHECK_EQ_INT(pkt_decoded_length((const uint8_t *)"a\\tb", 4, 1), PKT_TAB_WIDTH + 2);

    /* A `\t` escape becomes exactly PKT_TAB_WIDTH spaces. */
    pb_init(&b);
    pb_entry_str(&b, "columns", PKT_FLAG_ESCAPED, "col1\\tcol2");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "col1    col2");
    CHECK_EQ_INT(cfg->entries[0].value_len, 12);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Two escapes expand independently. */
    pb_init(&b);
    pb_entry_str(&b, "row", PKT_FLAG_ESCAPED, "a\\tb\\tc");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "a    b    c");
    CHECK_EQ_INT(cfg->entries[0].value_len, 11);
    pkt_config_free(cfg);
    cfg = NULL;

    /* A leading escape expands with nothing before it. */
    pb_init(&b);
    pb_entry_str(&b, "indent", PKT_FLAG_ESCAPED, "\\tvalue");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "    value");
    CHECK_EQ_INT(cfg->entries[0].value_len, 9);
    pkt_config_free(cfg);
    cfg = NULL;

    /* `\x09` inserts a raw byte and is deliberately NOT re-normalised. */
    pb_init(&b);
    pb_entry_str(&b, "raw", PKT_FLAG_ESCAPED, "a\\x09b");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "a\tb");
    CHECK_EQ_INT(cfg->entries[0].value_len, 3);
    pkt_config_free(cfg);

    TEST_REPORT("test_tab_expansion");
}
