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
/* Multi-entry framing: names, values, ordering, and byte-exact value lengths. */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    pb_entry_str(&b, "region", 0, "ap-south-1");
    pb_entry_str(&b, "retries", 0, "3");

    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(pkt_config_count(cfg), 3);

    CHECK_EQ_STR(cfg->entries[0].name, "mode");
    CHECK_EQ_STR(cfg->entries[0].value, "strict");
    CHECK_EQ_INT(cfg->entries[0].value_len, 6);

    CHECK_EQ_STR(cfg->entries[1].name, "region");
    CHECK_EQ_STR(cfg->entries[1].value, "ap-south-1");
    CHECK_EQ_INT(cfg->entries[1].value_len, 10);

    CHECK_EQ_STR(cfg->entries[2].name, "retries");
    CHECK_EQ_STR(cfg->entries[2].value, "3");
    CHECK_EQ_INT(cfg->entries[2].value_len, 1);

    pkt_config_free(cfg);
    cfg = NULL;

    /* An empty value is legal and distinct from a missing entry. */
    pb_init(&b);
    pb_entry_str(&b, "banner", 0, "");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(pkt_config_count(cfg), 1);
    CHECK_EQ_STR(cfg->entries[0].value, "");
    CHECK_EQ_INT(cfg->entries[0].value_len, 0);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Bytes past the declared entries are ignored, not rejected. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    b.buf[b.len++] = 0xde;
    b.buf[b.len++] = 0xad;
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(pkt_config_count(cfg), 1);
    CHECK_EQ_STR(cfg->entries[0].value, "strict");
    pkt_config_free(cfg);

    TEST_REPORT("test_entries");
}
