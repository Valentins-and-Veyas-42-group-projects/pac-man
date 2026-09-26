module;

#include <pacman/macros.h>

#include <bit>
#include <cstddef>
#include <span>

export module pacman.flood_fill;

// Expanding only the newest frontier avoids walking the full reachable region
// on every step. The graph's missing edges enforce walls and maze boundaries.
//
//       before              after one step
//
//     +---+---+---+         +---+---+---+
//     |   | F |   |         | F | V | F |
//     +---+---+---+   -->   +---+---+---+
//         frontier              V = visited
//                               F = new frontier

import pacman.bitboard;
import pacman.graph;
import pacman.types;

export namespace pacman::detail {

force_inline fn expand_frontier_unchecked(const graph_view graph,
                                          const const_tile_set_view frontier,
                                          tile_set_view next) noexcept -> void {
    for (let &word : next.words) {
        word = 0;
    }

    for (std::size_t word_index = 0; word_index < frontier.words.size();
         word_index++) {
        let pending = frontier.words[word_index];

        while (pending != 0) {
            let bit_index = static_cast<std::size_t>(std::countr_zero(pending));
            let index = word_index * bits_per_word + bit_index;

            if (index >= frontier.tile_count) {
                break;
            }

            const let &neighbors = graph.tiles[index];

            for (std::size_t neighbor_index = 0;
                 neighbor_index < neighbors.count; neighbor_index++) {
                const let &neighbor = neighbors.moves[neighbor_index];
                let destination =
                    static_cast<std::size_t>(neighbor.destination);
                next.words[destination / bits_per_word] |=
                    bitboard_word{1} << (destination % bits_per_word);
            }

            // Drop the tile just processed without scanning unset positions.
            pending &= pending - 1;
        }
    }
}

} // namespace pacman::detail

export namespace pacman {

/// Expand a checked frontier into a distinct output buffer.
[[nodiscard]]
fn expand_frontier(const graph_view graph, const const_tile_set_view frontier,
                   tile_set_view next) noexcept -> bool {
    if (!graph.is_valid() || !frontier.is_valid() || !next.is_valid()) {
        return false;
    }

    if (graph.tiles.size() != frontier.tile_count ||
        frontier.tile_count != next.tile_count) {
        return false;
    }

    if (frontier.words.data() == next.words.data()) {
        return false;
    }

    detail::expand_frontier_unchecked(graph, frontier, next);
    return true;
}

/// Fill visited with all tiles reachable from origin using distinct worksets.
/// Returns false when the graph, origin, or buffers violate that contract.
[[nodiscard]]
fn flood_reachable(const graph_view graph, const tile_index origin,
                   tile_set_view visited, tile_set_view frontier,
                   tile_set_view next) noexcept -> bool {
    if (!graph.is_valid() || !graph.contains(origin)) {
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

    if (!visited.clear() || !frontier.clear() || !next.clear()) {
        return false;
    }

    if (!visited.set(origin) || !frontier.set(origin)) {
        return false;
    }

    while (frontier.any()) {
        // Reuse the unchecked expansion after validating the graph and buffers.
        detail::expand_frontier_unchecked(graph, frontier.as_const(), next);

        if (!next.and_not_with(visited.as_const())) {
            return false;
        }

        if (!visited.or_with(next.as_const())) {
            return false;
        }

        if (!frontier.copy_from(next.as_const())) {
            return false;
        }
    }

    return true;
}

} // namespace pacman
