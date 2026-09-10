#include "pacman/native.h"
#include "pacman/macros.h"

import pacman.bitboard;

cfn PAC_API pac_abi_version(void) -> uint32_t { return PACMAN_ABI_VERSION; }

cfn PAC_API pac_bitboard_or(const uint64_t *lhs, const uint64_t *rhs,
                            const size_t word_count, uint64_t *output)
    -> pac_status {
    if (word_count != 0 &&
        (lhs == nullptr || rhs == nullptr || output == nullptr)) {
        return PAC_INVALID_ARGUMENT;
    }

    try {
        pacman::bitboard_or(lhs, rhs, word_count, output);
        return PAC_OK;
    } catch (...) {
        return PAC_INTERNAL_ERROR;
    }
}
