module;

#include <pacman/macros.h>

#include <bit>
#include <cstddef>

export module pacman.flood_fill;

import pacman.bitboard;
import pacman.graph;
import pacman.types;

namespace pacman {

[[nodiscard]]
force_inline fn expand_frontier_unchecked(const graph_view graph,
                                          const const_tile_set_view frontier,
                                          tile_set_view next) noexcept -> bool {
    if (!next.clear()) {
        return false;
    }

    for (std::size_t word_index = 0; word_index < frontier.words.size();
         ++word_index) {
        let pending = frontier.words[word_index];

        while (pending != 0) {
            let bit_index = static_cast<std::size_t>(std::countr_zero(pending));
            let index = word_index * bits_per_word + bit_index;

            if (index >= frontier.tile_count) {
                break;
            }

            let tile = static_cast<tile_index>(index);

            for (const let &neighbor : graph.neighbors(tile)) {
                if (!next.set(neighbor.destination)) {
                    return false;
                }
            }

            // Clear the lowest set bit to visit frontier tiles only.
            pending &= pending - 1;
        }
    }

    return true;
}

} // namespace pacman

export namespace pacman {

/// Expands one checked frontier into its directly reachable neighbors.
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

    return expand_frontier_unchecked(graph, frontier, next);
}

/// Computes every tile reachable from an origin using reusable buffers.
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
        // All graph and buffer validation happens before this hot loop.
        if (!expand_frontier_unchecked(graph, frontier.as_const(), next)) {
            return false;
        }

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
