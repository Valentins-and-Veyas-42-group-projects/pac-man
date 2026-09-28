#include "pacman/native.h"

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>

int main() {
    constexpr std::size_t tile_count = 128;
    constexpr std::size_t rounds = 10;
    std::array<pac_tile_neighbors, tile_count> tiles{};
    for (std::size_t tile = 0; tile < tile_count; tile++) {
        tiles[tile].moves[0] = {
            .destination = static_cast<std::uint16_t>((tile + 1) % tile_count),
            .direction = PAC_DIRECTION_RIGHT,
            .wraparound = static_cast<std::uint8_t>(tile + 1 == tile_count),
        };
        tiles[tile].moves[1] = {
            .destination = static_cast<std::uint16_t>((tile + tile_count - 1) %
                                                      tile_count),
            .direction = PAC_DIRECTION_LEFT,
            .wraparound = static_cast<std::uint8_t>(tile == 0),
        };
        tiles[tile].count = 2;
    }

    pac_topology *raw = nullptr;
    if (pac_topology_create(tiles.data(), tile_count, tile_count, &raw) !=
        PAC_OK) {
        std::fputs("could not create benchmark topology\n", stderr);
        return 1;
    }
    const std::unique_ptr<pac_topology, decltype(&pac_topology_destroy)>
        topology(raw, &pac_topology_destroy);
    std::array<std::uint32_t, tile_count> cached{};
    std::array<std::uint32_t, tile_count> graph{};

    // Warm the all-pairs table before timing its lookup fast path.
    if (pac_topology_bfs_distances(topology.get(), 0, cached.data(),
                                   cached.size()) != PAC_OK ||
        cached[0] != 0 || cached[tile_count / 2] != tile_count / 2) {
        std::fputs("invalid benchmark distance table\n", stderr);
        return 1;
    }
    for (std::size_t origin = 0; origin < tile_count; origin++) {
        const auto tile = static_cast<std::uint16_t>(origin);
        if (pac_topology_bfs_distances(topology.get(), tile, cached.data(),
                                       cached.size()) != PAC_OK ||
            pac_topology_bfs_distances_graph(topology.get(), tile, graph.data(),
                                             graph.size()) != PAC_OK ||
            cached != graph) {
            std::fprintf(stderr, "distance mismatch at origin %zu\n", origin);
            return 1;
        }
    }

    std::uint64_t checksum = 0;
    const auto started = std::chrono::steady_clock::now();
    for (std::size_t round = 0; round < rounds; round++) {
        for (std::size_t origin = 0; origin < tile_count; origin++) {
            if (pac_topology_bfs_distances(
                    topology.get(), static_cast<std::uint16_t>(origin),
                    cached.data(), cached.size()) != PAC_OK) {
                std::fputs("cached distance lookup failed\n", stderr);
                return 1;
            }
            checksum += cached[(origin + tile_count / 2) % tile_count];
        }
    }
    const auto elapsed = std::chrono::duration<double, std::micro>(
        std::chrono::steady_clock::now() - started);
    std::printf("cached distance lookup: %.2f us/call, checksum=%llu\n",
                elapsed.count() / static_cast<double>(rounds * tile_count),
                static_cast<unsigned long long>(checksum));
    return 0;
}
