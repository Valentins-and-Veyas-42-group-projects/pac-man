#include <pacman/macros.h>

#include <array>
#include <cstdint>

import pacman.graph;
import pacman.options;
import pacman.threat;
import pacman.types;

fn run_options_tests() -> int {
    using enum pacman::direction;
    const std::array<pacman::tile_neighbors, 6> tiles{{
        {.moves = {{{.destination = 1, .heading = right},
                    {.destination = 3, .heading = down}}},
         .count = 2},
        {.moves = {{{.destination = 0, .heading = left},
                    {.destination = 2, .heading = right}}},
         .count = 2},
        {.moves = {{{.destination = 1, .heading = left}}}, .count = 1},
        {.moves = {{{.destination = 0, .heading = up},
                    {.destination = 4, .heading = right}}},
         .count = 2},
        {.moves = {{{.destination = 3, .heading = left},
                    {.destination = 5, .heading = right}}},
         .count = 2},
        {.moves = {{{.destination = 4, .heading = left}}}, .count = 1},
    }};
    const std::array<std::uint32_t, 6> threats{0, 3, 2, 10, 10, 10};
    std::array<std::int32_t, 6> arrivals{};
    std::array<pacman::tile_index, 6> queue{};
    std::array<pacman::action_evaluation, 4> actions{};
    std::array<pacman::tile_index, 24> reachable{};
    std::size_t action_count = 0;

    if (!pacman::evaluate_actions({.tiles = tiles}, threats, 0,
                                  {.arrivals = arrivals, .queue = queue},
                                  {.actions = actions, .reachable = reachable},
                                  action_count)) {
        return 30;
    }
    if (action_count != 2 || actions[0].action != right ||
        actions[0].safe_tiles != 1 || actions[0].horizon_ticks != 1 ||
        !actions[0].has_minimum_margin || actions[0].minimum_margin != 2) {
        return 31;
    }
    if (actions[1].action != down || actions[1].safe_tiles != 3 ||
        actions[1].horizon_ticks != 3 || !actions[1].has_minimum_margin ||
        actions[1].minimum_margin != 7) {
        return 32;
    }
    return 0;
}
