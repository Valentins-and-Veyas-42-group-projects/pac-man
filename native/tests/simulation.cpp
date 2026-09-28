#include <array>
#include <cstdint>

import pacman.simulation;
import pacman.types;

namespace {

bool test_power_pellet_precedes_contact() {
    using namespace pacman;
    const std::array before{collectible::none, collectible::power_pellet,
                            collectible::pacgum};
    std::array<std::uint64_t, 1> after_consumed{};
    const std::array contacts{
        ghost_contact{.ghost = 0, .kind = contact_kind::dangerous}};
    simulation_state after{};
    const auto advanced = advance_simulation_state(
        simulation_state{.tile = 0}, before, {}, 1, direction::right,
        contacts, simulation_rules{}, after_consumed, after);
    return advanced && !after.died && after.score_gained == 250 &&
           after.power_pellets_eaten == 1 && after.frightened_remaining == 8 &&
           after.eaten_ghost_mask == 1 && (after_consumed[0] & 2) != 0 &&
           before[1] == collectible::power_pellet;
}

bool test_death_and_consumption() {
    using namespace pacman;
    const std::array before{collectible::none, collectible::pacgum};
    std::array<std::uint64_t, 1> after_consumed{};
    const std::array contacts{
        ghost_contact{.ghost = 2, .kind = contact_kind::dangerous}};
    simulation_state after{};
    const auto advanced = advance_simulation_state(
        simulation_state{.tile = 0}, before, {}, 1, direction::right,
        contacts, simulation_rules{}, after_consumed, after);
    return advanced && after.died && after.score_gained == 10 &&
           after.pacgums_eaten == 1 && (after_consumed[0] & 2) != 0;
}

} // namespace

int run_simulation_tests() {
    if (!test_power_pellet_precedes_contact()) {
        return 40;
    }
    if (!test_death_and_consumption()) {
        return 41;
    }
    return 0;
}
