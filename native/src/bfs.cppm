module;

#include <pacman/macros.h>

#include <algorithm>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>

export module pacman.bfs;

// BFS grows through the maze one ring at a time. That newest ring is called
// the frontier. Every tile in one frontier is the same distance from the
// start, so the first frontier that reaches a tile gives its shortest distance.
//
//                 +---+
//                 | 2 |
//             +---+---+---+---+---+
// distance    | 2 | 1 | 0 | 1 | 2 |    0 = starting tile
//             +---+---+---+---+---+
//                 | 2 |
//                 +---+

import pacman.bitboard;
import pacman.flood_fill;
import pacman.graph;
import pacman.topology;
import pacman.types;

export namespace pacman {

using path_distance = std::uint32_t;

inline constexpr path_distance unreachable_distance =
    std::numeric_limits<path_distance>::max();

/// Computes the shortest unweighted distance from an origin to every tile.
[[nodiscard]]
fn bfs_distances(const graph_view graph, const tile_index origin,
                 std::span<path_distance> distances, tile_set_view visited,
                 tile_set_view frontier, tile_set_view next) noexcept -> bool {
    if (!graph.is_valid() || !graph.contains(origin) ||
        distances.size() != graph.tiles.size()) {
        return false;
    }

    if (!visited.is_valid() || !frontier.is_valid() || !next.is_valid()) {
        return false;
    }

    let tile_count = graph.tiles.size();

    if (visited.tile_count != tile_count || frontier.tile_count != tile_count ||
        next.tile_count != tile_count) {
        return false;
    }

    if (visited.words.data() == frontier.words.data() ||
        visited.words.data() == next.words.data() ||
        frontier.words.data() == next.words.data()) {
        return false;
    }

    std::ranges::fill(distances, unreachable_distance);
    std::ranges::fill(visited.words, bitboard_word{0});
    std::ranges::fill(frontier.words, bitboard_word{0});
    std::ranges::fill(next.words, bitboard_word{0});

    let origin_index = static_cast<std::size_t>(origin);
    let origin_mask = bitboard_word{1} << (origin_index % bits_per_word);
    let origin_word = origin_index / bits_per_word;

    visited.words[origin_word] |= origin_mask;
    frontier.words[origin_word] |= origin_mask;
    distances[origin_index] = 0;

    let distance = path_distance{0};

    while (true) {
        detail::expand_frontier_unchecked(graph, frontier.as_const(), next);

        let has_next = false;

        // Fuse discovery, visited update, frontier copy, and distance writing.
        for (std::size_t word_index = 0; word_index < next.words.size();
             ++word_index) {
            let pending = next.words[word_index] & ~visited.words[word_index];

            next.words[word_index] = pending;
            visited.words[word_index] |= pending;
            frontier.words[word_index] = pending;
            has_next |= pending != 0;

            while (pending != 0) {
                let bit_index =
                    static_cast<std::size_t>(std::countr_zero(pending));
                let tile = word_index * bits_per_word + bit_index;

                if (tile >= tile_count) {
                    break;
                }

                distances[tile] = distance + 1;
                pending &= pending - 1;
            }
        }

        if (!has_next) {
            break;
        }

        ++distance;
    }

    return true;
}

/// Computes distances using directional masks built from a validated graph.
[[nodiscard]]
fn bfs_distances_masked(const topology_masks &topology,
                        const std::size_t tile_count, const tile_index origin,
                        std::span<path_distance> distances,
                        tile_set_view visited, tile_set_view frontier,
                        tile_set_view next, tile_set_view scratch) noexcept
    -> bool {
    const let words = words_for_tiles(tile_count);
    if (tile_count == 0 || static_cast<std::size_t>(origin) >= tile_count ||
        topology.width == 0 || tile_count % topology.width != 0 ||
        topology.north.size() != words || topology.east.size() != words ||
        topology.south.size() != words || topology.west.size() != words ||
        topology.exceptional_edge_count > topology.exceptional_edges.size() ||
        distances.size() != tile_count || !visited.is_valid() ||
        !frontier.is_valid() || !next.is_valid() || !scratch.is_valid() ||
        visited.tile_count != tile_count || frontier.tile_count != tile_count ||
        next.tile_count != tile_count || scratch.tile_count != tile_count) {
        return false;
    }

    const let visited_data = visited.words.data();
    const let frontier_data = frontier.words.data();
    const let next_data = next.words.data();
    const let scratch_data = scratch.words.data();
    if (visited_data == frontier_data || visited_data == next_data ||
        visited_data == scratch_data || frontier_data == next_data ||
        frontier_data == scratch_data || next_data == scratch_data) {
        return false;
    }

    std::ranges::fill(distances, unreachable_distance);
    std::ranges::fill(visited.words, bitboard_word{0});
    std::ranges::fill(frontier.words, bitboard_word{0});
    std::ranges::fill(next.words, bitboard_word{0});
    std::ranges::fill(scratch.words, bitboard_word{0});

    const let origin_index = static_cast<std::size_t>(origin);
    const let origin_mask = bitboard_word{1} << (origin_index % bits_per_word);
    const let origin_word = origin_index / bits_per_word;
    visited.words[origin_word] = origin_mask;
    frontier.words[origin_word] = origin_mask;
    distances[origin_index] = 0;

    let distance = path_distance{0};
    while (true) {
        expand_frontier_masked_unchecked(topology, frontier.as_const(), scratch,
                                         next);

        let has_next = false;
        for (std::size_t word_index = 0; word_index < words; ++word_index) {
            let pending = next.words[word_index] & ~visited.words[word_index];
            next.words[word_index] = pending;
            visited.words[word_index] |= pending;
            frontier.words[word_index] = pending;
            has_next |= pending != 0;

            while (pending != 0) {
                const let bit_index =
                    static_cast<std::size_t>(std::countr_zero(pending));
                const let tile = word_index * bits_per_word + bit_index;
                if (tile >= tile_count) {
                    break;
                }
                distances[tile] = distance + 1;
                pending &= pending - 1;
            }
        }

        if (!has_next) {
            break;
        }
        ++distance;
    }

    return true;
}

} // namespace pacman
