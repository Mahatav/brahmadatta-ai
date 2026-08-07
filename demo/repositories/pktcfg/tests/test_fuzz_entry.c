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
/* The fuzzable entry point survives malformed input and leaks nothing.
 *
 * These are the seed-corpus shapes. The literal-tab crash input is
 * deliberately NOT in here: the baseline suite has to be green, and the
 * defect's discovery belongs to the fuzzing stage, not to this file.
 */

#include "packet_builder.h"
#include "test_util.h"

static const uint8_t empty[]        = { 0 };
static const uint8_t magic_only[]   = { 'P', 'K', 'T', 'C' };
static const uint8_t short_header[] = { 'P', 'K', 'T', 'C', 1, 1, 0 };
static const uint8_t lying_count[]  = { 'P', 'K', 'T', 'C', 1, 255, 0, 0 };
static const uint8_t garbage[]      = { 0xff, 0x00, 0x7f, 0x80, 0x41, 0x41, 0x00, 0x09,
                                        0x5c, 0x74, 0x01, 0x02 };
static const uint8_t zero_name[]    = { 'P', 'K', 'T', 'C', 1, 1, 0, 0,
                                        0, 0, 0, 0 };

int main(void)
{
    pkt_builder b;

    CHECK_EQ_INT(pktcfg_fuzz_one_input(empty, 0), 0);
    CHECK_EQ_INT(pktcfg_fuzz_one_input(magic_only, sizeof(magic_only)), 0);
    CHECK_EQ_INT(pktcfg_fuzz_one_input(short_header, sizeof(short_header)), 0);
    CHECK_EQ_INT(pktcfg_fuzz_one_input(lying_count, sizeof(lying_count)), 0);
    CHECK_EQ_INT(pktcfg_fuzz_one_input(garbage, sizeof(garbage)), 0);
    CHECK_EQ_INT(pktcfg_fuzz_one_input(zero_name, sizeof(zero_name)), 0);

    /* A well-formed packet through the same door. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    pb_entry_str(&b, "banner", PKT_FLAG_ESCAPED, "hello\\nworld");
    CHECK_EQ_INT(pktcfg_fuzz_one_input(b.buf, b.len), 0);

    /* Every prefix of a well-formed packet, which is where truncation bugs
     * usually surface. */
    {
        size_t n;
        for (n = 0; n <= b.len; n++) {
            CHECK_EQ_INT(pktcfg_fuzz_one_input(b.buf, n), 0);
        }
    }

    TEST_REPORT("test_fuzz_entry");
}
