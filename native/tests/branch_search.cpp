#include <array>
#include <cstdint>

import pacman.branch_search;
import pacman.graph;
import pacman.simulation;
import pacman.types;

namespace {

constexpr std::array<pacman::tile_neighbors, 3> corridor{{
    {.moves = {{{.destination = 1, .heading = pacman::direction::right}}},
     .count = 1},
    {.moves = {{{.destination = 0, .heading = pacman::direction::left},
                {.destination = 2, .heading = pacman::direction::right}}},
     .count = 2},
    {.moves = {{{.destination = 1, .heading = pacman::direction::left}}},
     .count = 1},
}};

bool test_collectibles() {
    using namespace pacman;
    const std::array items{collectible::none, collectible::pacgum,
                           collectible::power_pellet};
    const std::array<std::uint8_t, 4 * 4 * 3> ghosts{};
    std::array<tile_index, 4> path{};
    branch_result result{};
    const auto status = search_action(
        {.tiles = corridor}, items,
        {.states = ghosts, .tile_count = 3, .tick_count = 4}, 0,
        direction::right, 3, simulation_rules{}, 32, path, result);
    return status == branch_search_status::ok && !result.best.died &&
           result.best.score_gained == 60 && result.best.tick == 3 &&
           result.best.pacgums_eaten == 1 &&
           result.best.power_pellets_eaten == 1 && result.path_length == 4;
}

bool test_contact() {
    using namespace pacman;
    const std::array items{collectible::none, collectible::none,
                           collectible::none};
    std::array<std::uint8_t, 2 * 4 * 3> ghosts{};
    ghosts[(1 * 4) * 3 + 1] = 1;
    std::array<tile_index, 2> path{};
    branch_result result{};
    const auto status =
        search_action({.tiles = corridor}, items,
                      {.states = ghosts, .tile_count = 3, .tick_count = 2}, 0,
                      direction::right, 1, simulation_rules{}, 8, path, result);
    return status == branch_search_status::ok && result.best.died &&
           result.path_length == 2 && path[0] == 0 && path[1] == 1;
}

} // namespace

int run_branch_search_tests() {
    if (!test_collectibles()) {
        return 50;
    }
    if (!test_contact()) {
        return 51;
    }
    return 0;
}
