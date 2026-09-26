#include <array>
#include <cstdint>

#include <pacman/macros.h>

import pacman.graph;
import pacman.prediction;
import pacman.types;

namespace {

struct prediction_fixture {
    std::array<std::uint32_t, 3> arrivals{};
    std::array<pacman::prediction_state, 12> current{};
    std::array<pacman::prediction_state, 12> next{};
    std::array<std::uint32_t, 12> seen{};

    fn workspace() noexcept -> pacman::prediction_workspace {
        return {
            .earliest_arrival = arrivals,
            .current = current,
            .next = next,
            .seen = seen,
        };
    }
};

fn corridor() -> std::array<pacman::tile_neighbors, 3> {
    using enum pacman::direction;
    return {{
        {.moves = {{{.destination = 1, .heading = right}}}, .count = 1},
        {.moves = {{{.destination = 0, .heading = left},
                    {.destination = 2, .heading = right}}},
         .count = 2},
        {.moves = {{{.destination = 1, .heading = left}}}, .count = 1},
    }};
}

fn predict(const std::array<pacman::tile_neighbors, 3> &tiles,
           const pacman::tile_index tile, const pacman::direction heading,
           prediction_fixture &fixture) -> bool {
    return pacman::predict_ghost(
        {.tiles = tiles},
        {.tile = tile, .heading = heading, .ghost = 0, .dangerous = true}, 1,
        fixture.workspace());
}

fn test_continues_forward() -> bool {
    const let tiles = corridor();
    prediction_fixture fixture{};

    return predict(tiles, 1, pacman::direction::right, fixture) &&
           fixture.arrivals[0] == pacman::no_prediction &&
           fixture.arrivals[1] == 0 && fixture.arrivals[2] == 1;
}

fn test_reverses_at_dead_end() -> bool {
    const let tiles = corridor();
    prediction_fixture fixture{};

    return predict(tiles, 2, pacman::direction::right, fixture) &&
           fixture.arrivals[1] == 1 &&
           fixture.next[0].heading == pacman::direction::left;
}

fn test_uses_wraparound_edge() -> bool {
    using enum pacman::direction;
    const std::array<pacman::tile_neighbors, 3> tiles{{
        {.moves = {{{.destination = 1, .heading = right},
                    {.destination = 2, .heading = left, .wraparound = true}}},
         .count = 2},
        {.moves = {{{.destination = 0, .heading = left},
                    {.destination = 2, .heading = right}}},
         .count = 2},
        {.moves = {{{.destination = 1, .heading = left},
                    {.destination = 0, .heading = right, .wraparound = true}}},
         .count = 2},
    }};
    prediction_fixture fixture{};

    return predict(tiles, 0, left, fixture) && fixture.arrivals[2] == 1;
}

fn test_combines_predicted_threats() -> bool {
    const let tiles = corridor();
    prediction_fixture fixture{};
    std::array<std::uint32_t, 3> eta{};
    std::array<std::uint8_t, 3> owners{};
    const std::array ghosts{
        pacman::ghost_prediction_input{
            .tile = 0,
            .heading = pacman::direction::right,
            .ghost = 0,
            .dangerous = true,
        },
        pacman::ghost_prediction_input{
            .tile = 2,
            .heading = pacman::direction::left,
            .ghost = 1,
            .dangerous = true,
        },
    };

    return pacman::build_predicted_threat_field(
               {.tiles = tiles}, ghosts, 1, fixture.workspace(),
               {.eta = eta, .owners = owners}) &&
           eta == std::array<std::uint32_t, 3>{0, 1, 0} &&
           owners == std::array<std::uint8_t, 3>{1, 3, 2};
}

} // namespace

fn run_prediction_tests() -> int {
    if (!test_continues_forward()) {
        return 20;
    }
    if (!test_reverses_at_dead_end()) {
        return 21;
    }
    if (!test_uses_wraparound_edge()) {
        return 22;
    }
    if (!test_combines_predicted_threats()) {
        return 23;
    }
    return 0;
}
