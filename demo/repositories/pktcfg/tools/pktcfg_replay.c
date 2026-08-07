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
/* Replay one input file through the fuzzable entry point.
 *
 * This is the deterministic reproducer runner: no fuzzing engine required, so
 * it works on any toolchain, with or without a sanitizer linked in.
 *
 *   pktcfg_replay <file> [repeat-count]
 *
 * Exit status: 0 on a clean run, 1 on usage/IO error. A sanitizer build aborts
 * with its own report before returning if the input trips a memory defect.
 */

#include "pktcfg/pktcfg.h"

#include <stdio.h>
#include <stdlib.h>

#define PKT_REPLAY_MAX (1u << 20)

int main(int argc, char **argv)
{
    FILE    *fp;
    uint8_t *buf;
    size_t   size;
    long     repeats = 1;
    long     i;

    if (argc < 2 || argc > 3) {
        fprintf(stderr, "usage: %s <input-file> [repeat-count]\n", argv[0]);
        return 1;
    }
    if (argc == 3) {
        repeats = strtol(argv[2], NULL, 10);
        if (repeats < 1) {
            fprintf(stderr, "repeat-count must be >= 1\n");
            return 1;
        }
    }

    fp = fopen(argv[1], "rb");
    if (fp == NULL) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }

    buf = malloc(PKT_REPLAY_MAX);
    if (buf == NULL) {
        fprintf(stderr, "out of memory\n");
        fclose(fp);
        return 1;
    }

    size = fread(buf, 1, PKT_REPLAY_MAX, fp);
    fclose(fp);

    for (i = 0; i < repeats; i++) {
        (void)pktcfg_fuzz_one_input(buf, size);
    }

    printf("replayed %s (%zu bytes) %ld time(s), no fault reported\n",
           argv[1], size, repeats);
    free(buf);
    return 0;
}
