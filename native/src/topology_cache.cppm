module;

#include "pacman/macros.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

export module pacman.topology_cache;

import pacman.bfs;
import pacman.bitboard;
import pacman.graph;
import pacman.types;

export namespace pacman {

using cached_distance = path_distance;

inline constexpr cached_distance cached_unreachable = unreachable_distance;

struct topology_cache {
    std::size_t tile_count{};
    std::size_t stride{};

    // A cache-line-sized stride keeps each source at the same alignment
    // within a line. Index each row by destination.
    std::vector<cached_distance> distances;

    // Keep every tied shortest first move, so callers need no tie-breaking BFS.
    // Bits follow direction order: up, right, down, left.
    std::vector<std::uint8_t> shortest_dirs;

    // Dense direction lookup avoids searching each tile's move list.
    // Read an entry only when legal_dirs[tile] contains that direction.
    std::vector<tile_index> neighbors;

    std::vector<std::uint8_t> legal_dirs;

    std::vector<std::uint8_t> degree;
    std::vector<std::uint8_t> intersection;

    /// Return a padded distance row for a valid source tile.
    [[nodiscard]]
    inline fn distance_row(const tile_index source) const noexcept
        -> const cached_distance * {
        return distances.data() + static_cast<std::size_t>(source) * stride;
    }

    /// Return first-move masks for a valid source tile.
    [[nodiscard]]
    inline fn dirs_row(const tile_index source) const noexcept
        -> const std::uint8_t * {
        return shortest_dirs.data() + static_cast<std::size_t>(source) * stride;
    }
};

/// Round row length to a cache-line-sized stride for predictable row layout.
[[nodiscard]]
inline fn cache_stride(const std::size_t tile_count) noexcept -> std::size_t {
    constexpr std::size_t entries_per_cache_line = 64 / sizeof(cached_distance);

    return (tile_count + entries_per_cache_line - 1) &
           ~(entries_per_cache_line - 1);
}

/// Precompute reusable graph lookups and all-pairs shortest path data.
/// Returns false if graph validation or cache allocation fails.
[[nodiscard]]
fn build_topology_cache(const graph_view graph, topology_cache &output) noexcept
    -> bool {
    if (!graph.is_valid() || graph.tiles.empty()) {
        return false;
    }

    try {
        const let tile_count = graph.tiles.size();
        const let stride = cache_stride(tile_count);
        const let word_count = words_for_tiles(tile_count);

        output.tile_count = tile_count;
        output.stride = stride;

        output.distances.assign(tile_count * stride, cached_unreachable);

        output.shortest_dirs.assign(tile_count * stride, std::uint8_t{0});

        output.neighbors.assign(tile_count * 4, tile_index{0});

        output.legal_dirs.assign(tile_count, std::uint8_t{0});

        output.degree.resize(tile_count);
        output.intersection.resize(tile_count);

        // Direction-indexed edges and tile degree serve later hot lookups.
        for (std::size_t source = 0; source < tile_count; ++source) {
            const let &tile = graph.tiles[source];

            if (tile.count > tile.moves.size()) {
                return false;
            }

            output.degree[source] = static_cast<std::uint8_t>(tile.count);

            output.intersection[source] =
                static_cast<std::uint8_t>(tile.count >= 3);

            for (std::size_t move_index = 0; move_index < tile.count;
                 ++move_index) {
                const let &move = tile.moves[move_index];

                const let heading = static_cast<std::size_t>(move.heading);

                if (heading >= 4) {
                    return false;
                }

                output.neighbors[source * 4 + heading] = move.destination;

                output.legal_dirs[source] |=
                    static_cast<std::uint8_t>(1u << heading);
            }
        }

        // Reuse one workspace across sources instead of allocating per BFS.
        std::vector<path_distance> temporary_distances(tile_count);

        std::vector<bitboard_word> visited_words(word_count);

        std::vector<bitboard_word> frontier_words(word_count);

        std::vector<bitboard_word> next_words(word_count);

        const let make_view = [&](std::vector<bitboard_word> &storage) {
            return tile_set_view{
                .words =
                    {
                        storage.data(),
                        storage.size(),
                    },
                .tile_count = tile_count,
            };
        };

        // Pay for each source BFS once, then answer distance queries by lookup.
        for (std::size_t source = 0; source < tile_count; ++source) {
            if (!bfs_distances(graph, static_cast<tile_index>(source),
                               temporary_distances, make_view(visited_words),
                               make_view(frontier_words),
                               make_view(next_words))) {
                return false;
            }

            let *destination_row = output.distances.data() + source * stride;

            for (std::size_t destination = 0; destination < tile_count;
                 ++destination) {
                destination_row[destination] = temporary_distances[destination];
            }
        }

        // A first move is shortest exactly when its remaining distance is
        // one less. Keep ties so later choices retain all valid routes.
        for (std::size_t source = 0; source < tile_count; ++source) {
            const let *source_distances =
                output.distance_row(static_cast<tile_index>(source));

            let *direction_row = output.shortest_dirs.data() + source * stride;

            for (std::size_t destination = 0; destination < tile_count;
                 ++destination) {
                const let distance = source_distances[destination];

                if (distance == 0 || distance == cached_unreachable) {
                    direction_row[destination] = 0;
                    continue;
                }

                let directions = std::uint8_t{0};

                const let &tile = graph.tiles[source];

                for (std::size_t move_index = 0; move_index < tile.count;
                     ++move_index) {
                    const let &move = tile.moves[move_index];

                    const let next_distance =
                        output.distance_row(move.destination)[destination];

                    if (next_distance == cached_unreachable) {
                        continue;
                    }

                    if (next_distance + 1 == distance) {
                        const let heading =
                            static_cast<std::size_t>(move.heading);

                        directions |= static_cast<std::uint8_t>(1u << heading);
                    }
                }

                direction_row[destination] = directions;
            }
        }

        return true;
    } catch (...) {
        return false;
    }
}

} // namespace pacman
