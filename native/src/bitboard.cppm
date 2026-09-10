module;

#include <pacman/macros.h>

#include <bit>
#include <cstddef>
#include <span>

export module pacman.bitboard;

// One bit tells us whether a maze tile belongs to a set.
// The bits sit next to each other in 64-bit words, ready for fast set math.
//
// tile      0   1   2   3          63     64  65
//          +---+---+---+---+       +---+  +---+---+
// present  | 1 | 0 | 1 | 1 |  ...  | 0 |  | 1 | 0 | ...
//          +---+---+---+---+       +---+  +---+---+
//          <---------- word 0 ---------->  <-- word 1

import pacman.kernel.scalar;
import pacman.types;

export namespace pacman {
struct const_tile_set_view {
    std::span<const bitboard_word> words;
    std::size_t tile_count;

    /// Reports whether storage size matches the tile count.
    [[nodiscard]]
    force_inline fn is_valid() const noexcept -> bool {
        return words.size() == words_for_tiles(tile_count);
    }

    /// Reports whether a valid tile is present.
    [[nodiscard]]
    force_inline fn test(const std::size_t tile) const noexcept -> bool {
        if (!is_valid() || tile >= tile_count) {
            return false;
        }

        let word_index = tile / bits_per_word;
        let bit_index = tile % bits_per_word;
        let mask = bitboard_word{1} << bit_index;

        return (words[word_index] & mask) != 0;
    }

    /// Reports whether at least one tile is present.
    [[nodiscard]]
    force_inline fn any() const noexcept -> bool {
        if (!is_valid()) {
            return false;
        }

        for (const let word : words) {
            if (word != 0) {
                return true;
            }
        }

        return false;
    }

    /// Returns the number of present tiles.
    [[nodiscard]]
    force_inline fn count() const noexcept -> std::size_t {
        if (!is_valid()) {
            return 0;
        }

        let total = std::size_t{0};

        for (const let word : words) {
            total += static_cast<std::size_t>(std::popcount(word));
        }

        return total;
    }
};

struct tile_set_view {
    std::span<bitboard_word> words;
    std::size_t tile_count;

    /// Reports whether storage size matches the tile count.
    [[nodiscard]]
    force_inline fn is_valid() const noexcept -> bool {
        return words.size() == words_for_tiles(tile_count);
    }

    /// Reports whether a valid tile is present.
    [[nodiscard]]
    force_inline fn test(const std::size_t tile) const noexcept -> bool {
        return as_const().test(tile);
    }

    /// Adds a valid tile to the set.
    force_inline fn set(const std::size_t tile) noexcept -> bool {
        if (!is_valid() || tile >= tile_count) {
            return false;
        }

        let word_index = tile / bits_per_word;
        let bit_index = tile % bits_per_word;
        let mask = bitboard_word{1} << bit_index;

        words[word_index] |= mask;
        return true;
    }

    /// Removes a valid tile from the set.
    force_inline fn reset(const std::size_t tile) noexcept -> bool {
        if (!is_valid() || tile >= tile_count) {
            return false;
        }

        let word_index = tile / bits_per_word;
        let bit_index = tile % bits_per_word;
        let mask = bitboard_word{1} << bit_index;

        words[word_index] &= ~mask;
        return true;
    }

    /// Removes every tile from the set.
    force_inline fn clear() noexcept -> bool {
        if (!is_valid()) {
            return false;
        }

        for (let &word : words) {
            word = 0;
        }

        return true;
    }

    /// Replaces this set with an equally sized set.
    force_inline fn copy_from(const const_tile_set_view other) noexcept
        -> bool {
        if (!is_valid() || !other.is_valid() ||
            tile_count != other.tile_count) {
            return false;
        }

        for (std::size_t index = 0; index < words.size(); ++index) {
            words[index] = other.words[index];
        }

        return true;
    }

    /// Adds every tile from an equally sized set.
    force_inline fn or_with(const const_tile_set_view other) noexcept -> bool {
        if (!is_valid() || !other.is_valid() ||
            tile_count != other.tile_count) {
            return false;
        }

        for (std::size_t index = 0; index < words.size(); ++index) {
            words[index] |= other.words[index];
        }

        return true;
    }

    /// Removes every tile found in an equally sized set.
    force_inline fn and_not_with(const const_tile_set_view other) noexcept
        -> bool {
        if (!is_valid() || !other.is_valid() ||
            tile_count != other.tile_count) {
            return false;
        }

        for (std::size_t index = 0; index < words.size(); ++index) {
            words[index] &= ~other.words[index];
        }

        return true;
    }

    /// Reports whether at least one tile is present.
    [[nodiscard]]
    force_inline fn any() const noexcept -> bool {
        return as_const().any();
    }

    /// Returns the number of present tiles.
    [[nodiscard]]
    force_inline fn count() const noexcept -> std::size_t {
        return as_const().count();
    }

    /// Returns a read-only view over the same storage.
    [[nodiscard]]
    force_inline fn as_const() const noexcept -> const_tile_set_view {
        return {
            .words = words,
            .tile_count = tile_count,
        };
    }
};

/// Computes a multiword bitwise OR with the selected scalar kernel.
void bitboard_or(const bitboard_word *lhs, const bitboard_word *rhs,
                 word_count words, bitboard_word *output) noexcept {
    kernel::scalar::bitboard_or(lhs, rhs, words, output);
}

} // namespace pacman
