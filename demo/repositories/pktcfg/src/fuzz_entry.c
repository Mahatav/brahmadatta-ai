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
