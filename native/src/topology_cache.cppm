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

    // [source * stride + destination]
    std::vector<cached_distance> distances;

    // [source * stride + destination]
    //
    // bit 0 = up
    // bit 1 = right
    // bit 2 = down
    // bit 3 = left
    std::vector<std::uint8_t> shortest_dirs;

    // [tile * 4 + direction]
    //
    // Only valid when the corresponding bit in legal_dirs[tile]
    // is set.
    std::vector<tile_index> neighbors;

    // One 4-bit mask per tile.
    std::vector<std::uint8_t> legal_dirs;

    std::vector<std::uint8_t> degree;
    std::vector<std::uint8_t> intersection;

    [[nodiscard]]
    inline fn distance_row(const tile_index source) const noexcept
        -> const cached_distance * {
        return distances.data() + static_cast<std::size_t>(source) * stride;
    }

    [[nodiscard]]
    inline fn dirs_row(const tile_index source) const noexcept
        -> const std::uint8_t * {
        return shortest_dirs.data() + static_cast<std::size_t>(source) * stride;
    }
};

[[nodiscard]]
inline fn cache_stride(const std::size_t tile_count) noexcept -> std::size_t {
    // 16 uint32_t distances = one 64-byte cache line.
    constexpr std::size_t entries_per_cache_line = 64 / sizeof(cached_distance);

    return (tile_count + entries_per_cache_line - 1) &
           ~(entries_per_cache_line - 1);
}

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

        /*
         * Precompute direct topology information.
         */
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

        /*
         * One reusable BFS workspace.
         *
         * We allocate these ONCE, then reuse them for every source.
         */
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

        /*
         * Precompute ALL shortest distances.
         *
         * BFS is now startup work rather than per-frame work.
         */
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

        /*
         * Precompute which directions preserve a shortest path.
         *
         * Example:
         *
         * 0010 = right
         * 0101 = up OR down
         */
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
