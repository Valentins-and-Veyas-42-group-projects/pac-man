module;

#include <pacman/macros.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>

export module pacman.options;

import pacman.graph;
import pacman.threat;
import pacman.types;

export namespace pacman {

/*
                  danger arrives at tick 2
                             x
    Pac-Man -> first tile -> safe region -> intersection

    Each legal first move receives its own bounded safe flood fill.
*/

struct action_evaluation {
    direction action{};
    tile_index first_tile{};
    std::size_t safe_tiles{};
    std::size_t safe_intersections{};
    std::size_t horizon_ticks{};
    std::int64_t minimum_margin{};
    bool has_minimum_margin{};
};

struct options_workspace {
    std::span<std::int32_t> arrivals;
    std::span<tile_index> queue;
};

struct action_evaluation_buffer {
    std::span<action_evaluation> actions;
    std::span<tile_index> reachable;
};

/// Evaluate every legal first move against an earliest-arrival threat field.
[[nodiscard]]
fn evaluate_actions(const graph_view graph,
                    const std::span<const std::uint32_t> threat_eta,
                    const tile_index player_tile, options_workspace workspace,
                    action_evaluation_buffer output,
                    std::size_t &action_count) noexcept -> bool {
    const let tile_count = graph.tiles.size();
    if (!graph.is_valid() || !graph.contains(player_tile) ||
        threat_eta.size() != tile_count ||
        workspace.arrivals.size() != tile_count ||
        workspace.queue.size() < tile_count || output.actions.size() < 4 ||
        output.reachable.size() < output.actions.size() * tile_count) {
        return false;
    }

    action_count = 0;
    for (const let first_move : graph.neighbors(player_tile)) {
        if (action_count >= output.actions.size()) {
            return false;
        }
        let &result = output.actions[action_count];
        result = {
            .action = first_move.heading,
            .first_tile = first_move.destination,
        };
        let reachable =
            output.reachable.subspan(action_count * tile_count, tile_count);
        ++action_count;

        const let first_eta = threat_eta[first_move.destination];
        if (first_eta != no_threat && first_eta <= 1) {
            continue;
        }

        std::ranges::fill(workspace.arrivals, std::int32_t{-1});
        workspace.arrivals[first_move.destination] = 1;
        workspace.queue[0] = first_move.destination;
        std::size_t head = 0;
        std::size_t tail = 1;

        while (head < tail) {
            const let current = workspace.queue[head++];
            const let current_index = static_cast<std::size_t>(current);
            const let arrival = workspace.arrivals[current_index];
            reachable[result.safe_tiles] = current;
            ++result.safe_tiles;
            result.horizon_ticks = std::max(result.horizon_ticks,
                                            static_cast<std::size_t>(arrival));
            if (graph.neighbors(current).size() >= 3) {
                ++result.safe_intersections;
            }

            const let ghost_eta = threat_eta[current_index];
            if (ghost_eta != no_threat) {
                const let margin = static_cast<std::int64_t>(ghost_eta) -
                                   static_cast<std::int64_t>(arrival);
                if (!result.has_minimum_margin ||
                    margin < result.minimum_margin) {
                    result.minimum_margin = margin;
                    result.has_minimum_margin = true;
                }
            }

            for (const let move : graph.neighbors(current)) {
                const let neighbor = static_cast<std::size_t>(move.destination);
                if (workspace.arrivals[neighbor] != -1) {
                    continue;
                }
                const let neighbor_arrival = arrival + 1;
                const let neighbor_threat = threat_eta[neighbor];
                if (neighbor_threat != no_threat &&
                    static_cast<std::uint32_t>(neighbor_arrival) >=
                        neighbor_threat) {
                    continue;
                }
                workspace.arrivals[neighbor] = neighbor_arrival;
                workspace.queue[tail++] = move.destination;
            }
        }
    }
    return true;
}

} // namespace pacman
