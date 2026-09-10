module;

#include <cstddef>
#include <cstdint>

export module pacman.kernel.scalar;

export namespace pacman::kernel::scalar {

/// Computes a baseline multiword bitwise OR.
void bitboard_or(const std::uint64_t *lhs, const std::uint64_t *rhs,
                 const std::size_t word_count, std::uint64_t *output) noexcept {
    for (std::size_t index = 0; index < word_count; ++index) {
        output[index] = lhs[index] | rhs[index];
    }
}

} // namespace pacman::kernel::scalar
