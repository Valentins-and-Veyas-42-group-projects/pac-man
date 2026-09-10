module;

#include "pacman/macros.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

export module pacman.topology;

import pacman.graph;
import pacman.bitboard;
import pacman.types;

export namespace pacman {

/*
    Graph edges become cheap directional lookup data.

        north
          ↑
    west ← ● → east
          ↓
        south

    Regular neighboring tiles can eventually use bit shifts.
    Wraparound and unusual edges remain explicit source/destination pairs.
*/

struct topology_edge {
    tile_index source;
    tile_index destination;
};

struct topology_masks {
    std::size_t width;
    std::span<bitboard_word> north;
    std::span<bitboard_word> east;
    std::span<bitboard_word> south;
    std::span<bitboard_word> west;

    std::span<topology_edge> exceptional_edges;
    std::size_t exceptional_edge_count;
};

/// Expands one frontier using topology validated during construction.
inline fn expand_frontier_masked_unchecked(const topology_masks &topology,
                                           const const_tile_set_view frontier,
                                           tile_set_view scratch,
                                           tile_set_view output) noexcept
    -> void {
    for (let &word : output.words) {
        word = 0;
    }

    const let shift = [&](const std::span<const bitboard_word> mask,
                          const std::size_t distance, const bool left) {
        bitboard_and_unchecked(
            frontier, {.words = mask, .tile_count = frontier.tile_count},
            scratch);
        if (left) {
            or_shift_left_unchecked(scratch.as_const(), distance, output);
        } else {
            or_shift_right_unchecked(scratch.as_const(), distance, output);
        }
    };

    shift(topology.north, topology.width, false);
    shift(topology.east, 1, true);
    shift(topology.south, topology.width, true);
    shift(topology.west, 1, false);

    for (std::size_t index = 0; index < topology.exceptional_edge_count;
         ++index) {
        const let edge = topology.exceptional_edges[index];
        const let source = static_cast<std::size_t>(edge.source);
        if ((frontier.words[source / bits_per_word] &
             (bitboard_word{1} << (source % bits_per_word))) != 0) {
            const let destination = static_cast<std::size_t>(edge.destination);
            output.words[destination / bits_per_word] |=
                bitboard_word{1} << (destination % bits_per_word);
        }
    }
}

/// Return the writable mask corresponding to one movement direction.
inline fn direction_mask(topology_masks &topology,
                         const direction heading) noexcept
    -> std::span<bitboard_word> {
    switch (heading) {
    case direction::up:
        return topology.north;
    case direction::right:
        return topology.east;
    case direction::down:
        return topology.south;
    case direction::left:
        return topology.west;
    }

    return {};
}

/// Reports whether an edge matches the normal row-major directional shift.
[[nodiscard]]
inline fn is_regular_edge(const std::size_t source,
                          const std::size_t destination,
                          const direction heading, const std::size_t width,
                          const std::size_t tile_count) noexcept -> bool {
    switch (heading) {
    case direction::up:
        return source >= width && destination == source - width;
    case direction::right:
        return source % width + 1 < width && destination == source + 1;
    case direction::down:
        return source + width < tile_count && destination == source + width;
    case direction::left:
        return source % width != 0 && destination == source - 1;
    }

    return false;
}

/// Build directional source masks from the exact maze graph.
///
/// A set source bit means that movement in that direction is legal.
/// Wraparound edges are stored separately because an ordinary shift cannot
/// reliably reproduce them.
inline fn build_topology_masks(const graph_view graph, const std::size_t width,
                               topology_masks &output) noexcept -> bool {
    const let required_words = words_for_tiles(graph.tiles.size());

    if (width == 0 || graph.tiles.empty() || graph.tiles.size() % width != 0 ||
        output.north.size() != required_words ||
        output.east.size() != required_words ||
        output.south.size() != required_words ||
        output.west.size() != required_words) {
        return false;
    }

    for (let mask : {
             output.north,
             output.east,
             output.south,
             output.west,
         }) {
        for (let &word : mask) {
            word = 0;
        }
    }

    output.exceptional_edge_count = 0;
    output.width = width;

    for (std::size_t source = 0; source < graph.tiles.size(); ++source) {
        const let &neighbors = graph.tiles[source];

        if (neighbors.count > neighbors.moves.size()) {
            return false;
        }

        for (std::size_t index = 0; index < neighbors.count; ++index) {
            const let &move = neighbors.moves[index];

            if (static_cast<std::size_t>(move.destination) >=
                graph.tiles.size()) {
                return false;
            }

            if (move.heading > direction::left) {
                return false;
            }

            if (move.wraparound ||
                !is_regular_edge(source, move.destination, move.heading, width,
                                 graph.tiles.size())) {
                if (output.exceptional_edge_count >=
                    output.exceptional_edges.size()) {
                    return false;
                }

                output.exceptional_edges[output.exceptional_edge_count] = {
                    .source = static_cast<tile_index>(source),
                    .destination = move.destination,
                };
                ++output.exceptional_edge_count;
                continue;
            }

            let mask = direction_mask(output, move.heading);
            const let word_index = source / bits_per_word;
            const let bit_index = source % bits_per_word;
            mask[word_index] |= bitboard_word{1} << bit_index;
        }
    }

    return true;
}

} // namespace pacman
