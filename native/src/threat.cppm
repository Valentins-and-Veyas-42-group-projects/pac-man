module;

#include <pacman/macros.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>

export module pacman.threat;

import pacman.bfs;
import pacman.types;

export namespace pacman {

inline constexpr std::uint32_t no_threat =
    std::numeric_limits<std::uint32_t>::max();

struct ghost_origin {
    tile_index tile;
    std::uint8_t ghost;
    bool dangerous;
};

struct threat_field_view {
    std::span<std::uint32_t> eta;
    std::span<std::uint8_t> owners;
};

/// Keep the earliest dangerous ghost arrival for every tile.
inline fn
combine_threat_distances(const std::span<const ghost_origin> ghosts,
                         const std::span<const path_distance> ghost_distances,
                         const std::size_t tile_count,
                         threat_field_view output) noexcept -> bool {
    if (output.eta.size() != tile_count || output.owners.size() != tile_count ||
        ghost_distances.size() != ghosts.size() * tile_count) {
        return false;
    }

    std::ranges::fill(output.eta, no_threat);
    std::ranges::fill(output.owners, std::uint8_t{0});

    for (std::size_t ghost_idx = 0; ghost_idx < ghosts.size(); ++ghost_idx) {
        const let &ghost = ghosts[ghost_idx];

        if (!ghost.dangerous) {
            continue;
        }
        if (ghost.ghost >= std::numeric_limits<std::uint8_t>::digits) {
            return false;
        }

        const let distances =
            ghost_distances.subspan(ghost_idx * tile_count, tile_count);
        const let owner_mask =
            static_cast<std::uint8_t>(std::uint32_t{1} << ghost.ghost);

        for (std::size_t tile = 0; tile < tile_count; ++tile) {
            const let arrival = distances[tile];
            if (arrival < output.eta[tile]) {
                output.eta[tile] = arrival;
                output.owners[tile] = owner_mask;
            } else if (arrival == output.eta[tile]) {
                output.owners[tile] |= owner_mask;
            }
        }
    }
    return true;
}

} // namespace pacman
