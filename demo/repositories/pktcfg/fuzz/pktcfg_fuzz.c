/* libFuzzer harness. Built only with -DPKTCFG_FUZZ=ON, which requires a
 * toolchain that ships libFuzzer (LLVM clang; Apple clang does not).
 */

#include "pktcfg/pktcfg.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    return pktcfg_fuzz_one_input(data, size);
}
