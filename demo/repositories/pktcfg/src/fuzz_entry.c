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
/* The single fuzzable entry point for this target.
 *
 * Everything a fuzzer, a replay tool, or Brahmadatta's harness drives goes
 * through here: one byte buffer in, no state left behind.
 */

#include "pktcfg/pktcfg.h"

int pktcfg_fuzz_one_input(const uint8_t *data, size_t size)
{
    pkt_config *cfg = NULL;
    pkt_status  status;

    status = pkt_parse(data, size, &cfg);
    if (status == PKT_OK) {
        /* Touch the parsed result so nothing above is optimised away. */
        (void)pkt_config_count(cfg);
        (void)pkt_config_get(cfg, "mode");
    }
    pkt_config_free(cfg);
    return 0;
}
