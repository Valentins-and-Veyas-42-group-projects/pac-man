#include "pacman/native.h"
#include "pacman/macros.h"

#include <cstddef>
#include <limits>
#include <memory>
#include <new>
#include <span>

import pacman.bitboard;
import pacman.bfs;
import pacman.graph;
import pacman.topology;
import pacman.types;

struct pac_topology {
    size_t tile_count{};
    std::unique_ptr<pacman::tile_neighbors[]> tiles{};
    std::unique_ptr<pacman::bitboard_word[]> masks{};
    std::unique_ptr<pacman::topology_edge[]> exceptional_edges{};
    std::unique_ptr<pacman::bitboard_word[]> workspace{};
    pacman::topology_masks topology{};
};

namespace {

fn copy_graph_tiles(const pac_tile_neighbors *source, const size_t tile_count,
                    std::unique_ptr<pacman::tile_neighbors[]> &output) noexcept
    -> pac_status {
    output.reset(new (std::nothrow) pacman::tile_neighbors[tile_count]{});
    if (output == nullptr) {
        return PAC_INTERNAL_ERROR;
    }

    for (size_t tile = 0; tile < tile_count; ++tile) {
        if (source[tile].count > 4) {
            return PAC_INVALID_ARGUMENT;
        }
        output[tile].count = source[tile].count;
        for (size_t index = 0; index < source[tile].count; ++index) {
            const let &move = source[tile].moves[index];
            if (static_cast<size_t>(move.destination) >= tile_count ||
                move.direction > PAC_DIRECTION_LEFT || move.wraparound > 1) {
                return PAC_INVALID_ARGUMENT;
            }
            output[tile].moves[index] = {
                .destination = move.destination,
                .heading = static_cast<pacman::direction>(move.direction),
                .wraparound = move.wraparound != 0,
            };
        }
    }
    return PAC_OK;
}

fn workspace_view(pac_topology &topology, const size_t index) noexcept
    -> pacman::tile_set_view {
    const let words = pacman::words_for_tiles(topology.tile_count);
    return {
        .words = {topology.workspace.get() + words * index, words},
        .tile_count = topology.tile_count,
    };
}

} // namespace

cfn PAC_API pac_abi_version(void) -> uint32_t { return PACMAN_ABI_VERSION; }

cfn PAC_API pac_bitboard_or(const uint64_t *lhs, const uint64_t *rhs,
                            const size_t word_count, uint64_t *output)
    -> pac_status {
    if (word_count != 0 &&
        (lhs == nullptr || rhs == nullptr || output == nullptr)) {
        return PAC_INVALID_ARGUMENT;
    }

    pacman::bitboard_or(lhs, rhs, word_count, output);
    return PAC_OK;
}

cfn PAC_API pac_topology_create(const pac_tile_neighbors *tiles,
                                const size_t tile_count,
                                const size_t maze_width, pac_topology **output)
    -> pac_status {
    if (output == nullptr) {
        return PAC_INVALID_ARGUMENT;
    }
    *output = nullptr;
    constexpr let tile_capacity =
        static_cast<size_t>(std::numeric_limits<uint16_t>::max()) + size_t{1};
    if (tiles == nullptr || tile_count == 0 || tile_count > tile_capacity ||
        maze_width == 0 || tile_count % maze_width != 0) {
        return PAC_INVALID_ARGUMENT;
    }

    std::unique_ptr<pac_topology> owned{new (std::nothrow) pac_topology{}};
    if (owned == nullptr) {
        return PAC_INTERNAL_ERROR;
    }
    owned->tile_count = tile_count;
    const let copied = copy_graph_tiles(tiles, tile_count, owned->tiles);
    if (copied != PAC_OK) {
        return copied;
    }

    const let words = pacman::words_for_tiles(tile_count);
    owned->masks.reset(new (std::nothrow) pacman::bitboard_word[words * 4]{});
    owned->exceptional_edges.reset(new (std::nothrow)
                                       pacman::topology_edge[tile_count * 4]{});
    owned->workspace.reset(new (std::nothrow)
                               pacman::bitboard_word[words * 4]{});
    if (owned->masks == nullptr || owned->exceptional_edges == nullptr ||
        owned->workspace == nullptr) {
        return PAC_INTERNAL_ERROR;
    }

    owned->topology = {
        .width = 0,
        .north = {owned->masks.get(), words},
        .east = {owned->masks.get() + words, words},
        .south = {owned->masks.get() + words * 2, words},
        .west = {owned->masks.get() + words * 3, words},
        .exceptional_edges = {owned->exceptional_edges.get(), tile_count * 4},
        .exceptional_edge_count = 0,
    };
    if (!pacman::build_topology_masks(
            {.tiles = {owned->tiles.get(), tile_count}}, maze_width,
            owned->topology)) {
        return PAC_INVALID_ARGUMENT;
    }

    *output = owned.release();
    return PAC_OK;
}

cfn PAC_API pac_topology_destroy(pac_topology *topology) -> void {
    delete topology;
}

cfn PAC_API pac_topology_bfs_distances(pac_topology *topology,
                                       const uint16_t origin,
                                       uint32_t *distances,
                                       const size_t distance_capacity)
    -> pac_status {
    if (topology == nullptr || distances == nullptr ||
        static_cast<size_t>(origin) >= topology->tile_count) {
        return PAC_INVALID_ARGUMENT;
    }
    if (distance_capacity < topology->tile_count) {
        return PAC_BUFFER_TOO_SMALL;
    }
    if (!pacman::bfs_distances_masked(
            topology->topology, topology->tile_count, origin,
            {distances, topology->tile_count}, workspace_view(*topology, 0),
            workspace_view(*topology, 1), workspace_view(*topology, 2),
            workspace_view(*topology, 3))) {
        return PAC_INTERNAL_ERROR;
    }
    return PAC_OK;
}

cfn PAC_API pac_bfs_distances_graph(const pac_tile_neighbors *tiles,
                                    const size_t tile_count,
                                    const uint16_t origin, uint32_t *distances,
                                    const size_t distance_capacity)
    -> pac_status {
    if (tiles == nullptr || tile_count == 0 || distances == nullptr ||
        static_cast<size_t>(origin) >= tile_count) {
        return PAC_INVALID_ARGUMENT;
    }
    if (distance_capacity < tile_count) {
        return PAC_BUFFER_TOO_SMALL;
    }
    std::unique_ptr<pacman::tile_neighbors[]> graph_tiles{};
    const let copied = copy_graph_tiles(tiles, tile_count, graph_tiles);
    if (copied != PAC_OK) {
        return copied;
    }
    const let words = pacman::words_for_tiles(tile_count);
    std::unique_ptr<pacman::bitboard_word[]> workspace{
        new (std::nothrow) pacman::bitboard_word[words * 3]{}};
    if (workspace == nullptr) {
        return PAC_INTERNAL_ERROR;
    }
    const let view = [&](const size_t index) {
        return pacman::tile_set_view{
            .words = {workspace.get() + words * index, words},
            .tile_count = tile_count,
        };
    };
    if (!pacman::bfs_distances({.tiles = {graph_tiles.get(), tile_count}},
                               origin, {distances, tile_count}, view(0),
                               view(1), view(2))) {
        return PAC_INVALID_ARGUMENT;
    }
    return PAC_OK;
}

cfn PAC_API pac_bfs_distances(const pac_tile_neighbors *tiles,
                              const size_t tile_count, const size_t maze_width,
                              const uint16_t origin, uint32_t *distances,
                              const size_t distance_capacity) -> pac_status {
    if (tile_count == 0 || maze_width == 0 || tile_count % maze_width != 0 ||
        tiles == nullptr || distances == nullptr) {
        return PAC_INVALID_ARGUMENT;
    }

    if (distance_capacity < tile_count) {
        return PAC_BUFFER_TOO_SMALL;
    }

    constexpr let tile_capacity =
        static_cast<size_t>(std::numeric_limits<uint16_t>::max()) + size_t{1};

    if (tile_count > tile_capacity ||
        static_cast<size_t>(origin) >= tile_count) {
        return PAC_INVALID_ARGUMENT;
    }

    std::unique_ptr<pacman::tile_neighbors[]> graph_tiles{
        new (std::nothrow) pacman::tile_neighbors[tile_count]{},
    };

    if (graph_tiles == nullptr) {
        return PAC_INTERNAL_ERROR;
    }

    for (size_t tile = 0; tile < tile_count; ++tile) {
        const let &source = tiles[tile];

        if (source.count > 4) {
            return PAC_INVALID_ARGUMENT;
        }

        let &destination = graph_tiles[tile];
        destination.count = source.count;

        for (size_t index = 0; index < source.count; ++index) {
            const let &source_move = source.moves[index];

            if (static_cast<size_t>(source_move.destination) >= tile_count ||
                source_move.direction > PAC_DIRECTION_LEFT ||
                source_move.wraparound > 1) {
                return PAC_INVALID_ARGUMENT;
            }

            destination.moves[index] = {
                .destination = source_move.destination,
                .heading =
                    static_cast<pacman::direction>(source_move.direction),
                .wraparound = source_move.wraparound != 0,
            };
        }
    }

    let words = pacman::words_for_tiles(tile_count);
    std::unique_ptr<pacman::bitboard_word[]> visited_words{
        new (std::nothrow) pacman::bitboard_word[words]{},
    };
    std::unique_ptr<pacman::bitboard_word[]> frontier_words{
        new (std::nothrow) pacman::bitboard_word[words]{},
    };
    std::unique_ptr<pacman::bitboard_word[]> next_words{
        new (std::nothrow) pacman::bitboard_word[words]{},
    };
    std::unique_ptr<pacman::bitboard_word[]> scratch_words{
        new (std::nothrow) pacman::bitboard_word[words]{},
    };
    std::unique_ptr<pacman::bitboard_word[]> topology_words{
        new (std::nothrow) pacman::bitboard_word[words * 4]{},
    };
    std::unique_ptr<pacman::topology_edge[]> exceptional_edges{
        new (std::nothrow) pacman::topology_edge[tile_count * 4]{},
    };

    if (visited_words == nullptr || frontier_words == nullptr ||
        next_words == nullptr || scratch_words == nullptr ||
        topology_words == nullptr || exceptional_edges == nullptr) {
        return PAC_INTERNAL_ERROR;
    }

    let make_view = [tile_count, words](pacman::bitboard_word *storage) {
        return pacman::tile_set_view{
            .words = {storage, words},
            .tile_count = tile_count,
        };
    };

    let graph = pacman::graph_view{.tiles = {graph_tiles.get(), tile_count}};
    let topology = pacman::topology_masks{
        .width = 0,
        .north = {topology_words.get(), words},
        .east = {topology_words.get() + words, words},
        .south = {topology_words.get() + words * 2, words},
        .west = {topology_words.get() + words * 3, words},
        .exceptional_edges = {exceptional_edges.get(), tile_count * 4},
        .exceptional_edge_count = 0,
    };

    if (!pacman::build_topology_masks(graph, maze_width, topology) ||
        !pacman::bfs_distances_masked(
            topology, tile_count, origin,
            std::span<uint32_t>{distances, tile_count},
            make_view(visited_words.get()), make_view(frontier_words.get()),
            make_view(next_words.get()), make_view(scratch_words.get()))) {
        return PAC_INVALID_ARGUMENT;
    }

    return PAC_OK;
}
