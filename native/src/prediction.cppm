module;

#include <pacman/macros.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <utility>

export module pacman.prediction;

import pacman.graph;
import pacman.threat;
import pacman.types;

/*
    Prediction branches are unique by (tile, heading). A tile/heading pair
    maps directly to one seen-array index, so a generation stamp replaces a
    scan of the current frontier when rejecting duplicates.
*/

export namespace pacman {

/*
    tick 0              tick 1              tick 2

      [A ->]       [B ->]     [D v]      [C ->] [E v]
         \          /           \          /
          movement branches carry their direction

    States are unique by (tile, direction), not merely by tile.
*/

inline constexpr std::uint32_t no_prediction =
    std::numeric_limits<std::uint32_t>::max();

struct ghost_prediction_input {
    tile_index tile;
    direction heading;
    std::uint8_t ghost;
    bool dangerous;
};

struct prediction_state {
    tile_index tile;
    direction heading;
};

struct prediction_workspace {
    std::span<std::uint32_t> earliest_arrival;
    std::span<prediction_state> current;
    std::span<prediction_state> next;
    std::span<std::uint32_t> seen;
};

/// Return the direction opposite to `heading`.
[[nodiscard]]
constexpr fn opposite(const direction heading) noexcept -> direction {
    switch (heading) {
    case direction::up:
        return direction::down;
    case direction::right:
        return direction::left;
    case direction::down:
        return direction::up;
    case direction::left:
        return direction::right;
    }
    return direction::up;
}

} // namespace pacman

namespace pacman::detail {

fn append_unique(const move candidate, std::span<prediction_state> output,
                 std::size_t &output_count,
                 const std::span<std::uint32_t> seen,
                 const std::uint32_t generation) noexcept -> bool {
    // A stamped tile/heading lookup avoids scanning the current frontier.
    const let state_id = static_cast<std::size_t>(candidate.destination) * 4 +
                         static_cast<std::size_t>(candidate.heading);
    if (seen[state_id] == generation) {
        return true;
    }
    if (output_count >= output.size()) {
        return false;
    }
    output[output_count++] = {
        .tile = candidate.destination,
        .heading = candidate.heading,
    };
    seen[state_id] = generation;
    return true;
}

fn append_legal_moves(const graph_view graph, const prediction_state state,
                      std::span<prediction_state> output,
                      std::size_t &output_count,
                      const std::span<std::uint32_t> seen,
                      const std::uint32_t generation) noexcept -> bool {
    const let moves = graph.neighbors(state.tile);
    const let reverse = opposite(state.heading);
    const let has_forward =
        std::ranges::any_of(moves, [reverse](const move candidate) noexcept {
            return candidate.heading != reverse;
        });

    for (const let candidate : moves) {
        if (has_forward && candidate.heading == reverse) {
            continue;
        }
        if (!append_unique(candidate, output, output_count, seen,
                           generation)) {
            return false;
        }
    }
    return true;
}

} // namespace pacman::detail

export namespace pacman {

/// Fill earliest arrival ticks for all ghost-reachable tiles through horizon.
/// Returns false when the graph or caller-owned workspace is invalid.
[[nodiscard]]
fn predict_ghost(const graph_view graph, const ghost_prediction_input ghost,
                 const std::size_t horizon,
                 prediction_workspace workspace) noexcept -> bool {
    const let tile_count = graph.tiles.size();
    const let state_capacity = tile_count * 4;
    if (horizon > std::numeric_limits<std::uint32_t>::max() ||
        !graph.is_valid() || !graph.contains(ghost.tile) ||
        workspace.earliest_arrival.size() != tile_count ||
        workspace.current.size() < state_capacity ||
        workspace.next.size() < state_capacity ||
        workspace.seen.size() < state_capacity) {
        return false;
    }

    std::ranges::fill(workspace.earliest_arrival, no_prediction);
    std::ranges::fill(workspace.seen.first(state_capacity), 0);
    workspace.earliest_arrival[ghost.tile] = 0;
    workspace.current[0] = {
        .tile = ghost.tile,
        .heading = ghost.heading,
    };

    let current = workspace.current;
    let next = workspace.next;
    std::size_t current_count = 1;

    for (std::size_t tick = 1; tick <= horizon; ++tick) {
        std::size_t next_count = 0;
        for (std::size_t index = 0; index < current_count; ++index) {
            if (!detail::append_legal_moves(
                    graph, current[index], next, next_count,
                    workspace.seen.first(state_capacity),
                    static_cast<std::uint32_t>(tick))) {
                return false;
            }
        }

        for (std::size_t index = 0; index < next_count; ++index) {
            const let tile = static_cast<std::size_t>(next[index].tile);
            workspace.earliest_arrival[tile] =
                std::min(workspace.earliest_arrival[tile],
                         static_cast<std::uint32_t>(tick));
        }

        std::swap(current, next);
        current_count = next_count;
    }

    return true;
}

/// Combine ghost predictions into the earliest dangerous-arrival field.
/// Returns false when an input, prediction, or output buffer is invalid.
[[nodiscard]]
fn build_predicted_threat_field(
    const graph_view graph,
    const std::span<const ghost_prediction_input> ghosts,
    const std::size_t horizon, prediction_workspace workspace,
    threat_field_view output) noexcept -> bool {
    const let tile_count = graph.tiles.size();
    if (output.eta.size() != tile_count || output.owners.size() != tile_count) {
        return false;
    }

    std::ranges::fill(output.eta, no_threat);
    std::ranges::fill(output.owners, std::uint8_t{0});

    for (const let ghost : ghosts) {
        if (ghost.ghost >= std::numeric_limits<std::uint8_t>::digits ||
            !graph.contains(ghost.tile)) {
            return false;
        }
        if (!predict_ghost(graph, ghost, horizon, workspace)) {
            return false;
        }
        if (!ghost.dangerous) {
            continue;
        }

        const let owner_mask =
            static_cast<std::uint8_t>(std::uint32_t{1} << ghost.ghost);
        for (std::size_t tile = 0; tile < tile_count; ++tile) {
            const let arrival = workspace.earliest_arrival[tile];
            if (arrival < output.eta[tile]) {
                output.eta[tile] = arrival;
                output.owners[tile] = owner_mask;
            } else if (arrival == output.eta[tile] &&
                       arrival != no_prediction) {
                output.owners[tile] |= owner_mask;
            }
        }
    }
    return true;
}

} // namespace pacman
