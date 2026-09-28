#include <pacman/native.h>

#include <array>
#include <cstdint>

int run_abi_simulation_tests() {
    std::array<pac_tile_neighbors, 3> tiles{};
    tiles[0].moves[0] = {
        .destination = 1, .direction = PAC_DIRECTION_RIGHT, .wraparound = 0};
    tiles[0].count = 1;
    tiles[1].moves[0] = {
        .destination = 0, .direction = PAC_DIRECTION_LEFT, .wraparound = 0};
    tiles[1].moves[1] = {
        .destination = 2, .direction = PAC_DIRECTION_RIGHT, .wraparound = 0};
    tiles[1].count = 2;
    tiles[2].moves[0] = {
        .destination = 1, .direction = PAC_DIRECTION_LEFT, .wraparound = 0};
    tiles[2].count = 1;
    pac_topology *topology = nullptr;
    if (pac_abi_version() != 3 ||
        pac_topology_create(tiles.data(), tiles.size(), 3, &topology) !=
            PAC_OK) {
        return 60;
    }
    const std::array<std::uint8_t, 3> items{0, 1, 2};
    const std::array<std::uint8_t, 4 * 4 * 3> ghosts{};
    const std::array<std::uint32_t, 4> combo{200, 400, 800, 1600};
    const pac_simulation_input input{
        .collectibles = items.data(),
        .collectible_count = items.size(),
        .prediction_grid = ghosts.data(),
        .prediction_count = ghosts.size(),
        .ghost_combo_scores = combo.data(),
        .ghost_combo_score_count = combo.size(),
        .horizon = 3,
        .state_capacity = 32,
        .pacgum_score = 10,
        .power_pellet_score = 50,
        .frightened_ticks = 8,
        .origin = 0,
        .action = PAC_DIRECTION_RIGHT,
        .ghost_count = 0,
        .ghost_order = {},
        .reserved = {},
    };
    pac_simulation_result result{};
    std::array<std::uint16_t, 4> path{};
    const auto status = pac_topology_simulate_action(topology, &input, &result,
                                                     path.data(), path.size());
    pac_topology_destroy(topology);
    return status == PAC_OK && result.score_gained == 60 &&
                   result.survival_horizon == 3 && result.path_length == 4 &&
                   path == std::array<std::uint16_t, 4>{0, 1, 2, 1}
               ? 0
               : 61;
}
