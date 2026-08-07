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
/* pkt_config_get / pkt_config_count behaviour, including the null cases. */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    pb_entry_str(&b, "region", 0, "ap-south-1");
    pb_entry_str(&b, "banner", PKT_FLAG_ESCAPED, "line1\\nline2");

    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);

    CHECK_EQ_STR(pkt_config_get(cfg, "mode"), "strict");
    CHECK_EQ_STR(pkt_config_get(cfg, "region"), "ap-south-1");
    CHECK_EQ_STR(pkt_config_get(cfg, "banner"), "line1\nline2");

    CHECK(pkt_config_get(cfg, "missing") == NULL);
    CHECK(pkt_config_get(cfg, "") == NULL);
    CHECK(pkt_config_get(cfg, "Mode") == NULL);   /* lookup is case-sensitive */
    CHECK(pkt_config_get(cfg, NULL) == NULL);
    CHECK(pkt_config_get(NULL, "mode") == NULL);

    CHECK_EQ_INT(pkt_config_count(cfg), 3);
    CHECK_EQ_INT(pkt_config_count(NULL), 0);

    pkt_config_free(cfg);
    pkt_config_free(NULL);   /* must be a no-op */

    TEST_REPORT("test_lookup");
}
