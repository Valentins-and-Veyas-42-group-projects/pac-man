module;

#include <pacman/macros.h>

#include <cstddef>
#include <cstdint>

export module pacman.types;

export namespace pacman {

using bitboard_word = std::uint64_t;
using word_count = std::size_t;

using tile_index = std::uint16_t;

enum class direction : std::uint8_t {
    up,
    right,
    down,
    left,
};

inline constexpr std::size_t bits_per_word = 64;

/// Returns the storage words required for a tile count.
[[nodiscard]]
constexpr fn words_for_tiles(const std::size_t tile_count) noexcept
    -> std::size_t {
    return tile_count / bits_per_word +
           static_cast<std::size_t>(tile_count % bits_per_word != 0);
}
} // namespace pacman
