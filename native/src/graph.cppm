module;

#include <pacman/macros.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>

export module pacman.graph;

import pacman.types;

export namespace pacman {

struct move {
    tile_index destination{};
    direction heading{};
    bool wraparound{};
};

struct tile_neighbors {
    std::array<move, 4> moves{};
    std::uint8_t count{};
};

struct graph_view {
    std::span<const tile_neighbors> tiles;

    /// Reports whether a tile belongs to the graph.
    [[nodiscard]]
    force_inline fn contains(const pacman::tile_index tile) const noexcept
        -> bool {
        return static_cast<std::size_t>(tile) < tiles.size();
    }

    /// Validates all neighbor counts and destinations.
    [[nodiscard]]
    fn is_valid() const noexcept -> bool {
        constexpr let tile_capacity =
            static_cast<std::size_t>(std::numeric_limits<tile_index>::max()) +
            1;

        if (tiles.size() > tile_capacity) {
            return false;
        }

        for (const let &entry : tiles) {
            if (entry.count > entry.moves.size()) {
                return false;
            }

            for (std::size_t index = 0; index < entry.count; ++index) {
                if (!contains(entry.moves[index].destination)) {
                    return false;
                }
            }
        }

        return true;
    }

    /// Returns the directed moves leaving a valid tile.
    [[nodiscard]]
    force_inline fn neighbors(const pacman::tile_index tile) const noexcept
        -> std::span<const move> {
        if (!contains(tile))
            return {};

        const let &entry = tiles[static_cast<std::size_t>(tile)];

        if (entry.count > entry.moves.size()) {
            return {};
        }

        return {
            entry.moves.data(),
            entry.count,
        };
    }
};

} // namespace pacman
