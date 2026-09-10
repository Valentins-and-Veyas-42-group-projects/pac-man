#include <pacman/macros.h>

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>

import pacman.bitboard;
import pacman.bfs;
import pacman.flood_fill;
import pacman.graph;
import pacman.topology;
import pacman.types;

[[nodiscard]]
fn test_cross_word_bitboard_operations() noexcept -> bool {
    constexpr let tile_count = std::size_t{130};
    std::array<pacman::bitboard_word, 3> source{};
    std::array<pacman::bitboard_word, 3> mask{};
    std::array<pacman::bitboard_word, 3> output{};

    let source_view = pacman::tile_set_view{source, tile_count};
    let mask_view = pacman::tile_set_view{mask, tile_count};
    let output_view = pacman::tile_set_view{output, tile_count};

    source_view.set(63);
    source_view.set(64);
    mask_view.set(64);
    pacman::bitboard_and_unchecked(source_view.as_const(), mask_view.as_const(),
                                   output_view);
    if (!output_view.test(64) || output_view.count() != 1) {
        return false;
    }

    output_view.clear();
    pacman::or_shift_left_unchecked(source_view.as_const(), 1, output_view);
    if (!output_view.test(64) || !output_view.test(65) ||
        output_view.count() != 2) {
        return false;
    }

    output_view.clear();
    pacman::or_shift_right_unchecked(source_view.as_const(), 1, output_view);
    if (!output_view.test(62) || !output_view.test(63) ||
        output_view.count() != 2) {
        return false;
    }

    source_view.clear();
    output_view.clear();
    source_view.set(1);
    pacman::or_shift_left_unchecked(source_view.as_const(), 64, output_view);
    if (!output_view.test(65) || output_view.count() != 1) {
        return false;
    }

    source_view.clear();
    output_view.clear();
    source_view.set(65);
    pacman::or_shift_right_unchecked(source_view.as_const(), 64, output_view);
    return output_view.test(1) && output_view.count() == 1;
}

[[nodiscard]]
fn test_topology_masks() noexcept -> bool {
    std::array<pacman::tile_neighbors, 3> tiles{};
    tiles[0] = {
        .moves = {{{.destination = 1, .heading = pacman::direction::right}}},
        .count = 1,
    };
    tiles[1] = {
        .moves = {{{.destination = 0, .heading = pacman::direction::left},
                   {.destination = 2, .heading = pacman::direction::right}}},
        .count = 2,
    };
    tiles[2] = {
        .moves = {{{.destination = 1, .heading = pacman::direction::left},
                   {.destination = 0,
                    .heading = pacman::direction::right,
                    .wraparound = true}}},
        .count = 2,
    };

    std::array<pacman::bitboard_word, 1> north{};
    std::array<pacman::bitboard_word, 1> east{};
    std::array<pacman::bitboard_word, 1> south{};
    std::array<pacman::bitboard_word, 1> west{};
    std::array<pacman::topology_edge, 1> exceptional{};
    let output = pacman::topology_masks{
        .width = 0,
        .north = north,
        .east = east,
        .south = south,
        .west = west,
        .exceptional_edges = exceptional,
        .exceptional_edge_count = 0,
    };

    if (!pacman::build_topology_masks({.tiles = tiles}, 3, output) ||
        output.width != 3 || east[0] != 0b011 || west[0] != 0b110 ||
        north[0] != 0 || south[0] != 0 || output.exceptional_edge_count != 1 ||
        exceptional[0].source != 2 || exceptional[0].destination != 0) {
        return false;
    }

    std::array<pacman::bitboard_word, 1> frontier_words{};
    std::array<pacman::bitboard_word, 1> scratch_words{};
    std::array<pacman::bitboard_word, 1> graph_words{};
    std::array<pacman::bitboard_word, 1> masked_words{};
    let frontier = pacman::tile_set_view{frontier_words, 3};
    let scratch = pacman::tile_set_view{scratch_words, 3};
    let graph_result = pacman::tile_set_view{graph_words, 3};
    let masked_result = pacman::tile_set_view{masked_words, 3};

    for (std::size_t tile = 0; tile < tiles.size(); ++tile) {
        frontier.clear();
        frontier.set(tile);
        pacman::detail::expand_frontier_unchecked(
            {.tiles = tiles}, frontier.as_const(), graph_result);
        pacman::expand_frontier_masked_unchecked(output, frontier.as_const(),
                                                 scratch, masked_result);
        if (graph_words != masked_words) {
            return false;
        }
    }

    tiles[0].moves[0].destination = 3;
    if (pacman::build_topology_masks({.tiles = tiles}, 3, output)) {
        return false;
    }

    tiles[0].moves[0].destination = 1;
    tiles[0].moves[0].heading = static_cast<pacman::direction>(255);
    if (pacman::build_topology_masks({.tiles = tiles}, 3, output)) {
        return false;
    }

    tiles[0].moves[0].heading = pacman::direction::right;
    output.exceptional_edges = {};
    if (pacman::build_topology_masks({.tiles = tiles}, 3, output)) {
        return false;
    }

    output.exceptional_edges = exceptional;
    output.east = {};
    return !pacman::build_topology_masks({.tiles = tiles}, 3, output);
}

[[nodiscard]]
fn test_bfs_distances() noexcept -> bool {
    constexpr let tile_count = std::size_t{5};
    std::array<pacman::tile_neighbors, tile_count> tiles{};

    tiles[0] = {
        .moves = {{{.destination = 1}, {.destination = 3, .wraparound = true}}},
        .count = 2,
    };
    tiles[1] = {
        .moves = {{{.destination = 0}, {.destination = 2}}},
        .count = 2,
    };
    tiles[2] = {
        .moves = {{{.destination = 1}}},
        .count = 1,
    };
    tiles[3] = {
        .moves = {{{.destination = 0, .wraparound = true}}},
        .count = 1,
    };

    std::array<pacman::path_distance, tile_count> distances{};
    std::array<pacman::bitboard_word, 1> visited_words{};
    std::array<pacman::bitboard_word, 1> frontier_words{};
    std::array<pacman::bitboard_word, 1> next_words{};

    let make_view = [](std::span<pacman::bitboard_word> words) {
        return pacman::tile_set_view{
            .words = words,
            .tile_count = tile_count,
        };
    };

    if (!pacman::bfs_distances(
            {.tiles = tiles}, 0, distances, make_view(visited_words),
            make_view(frontier_words), make_view(next_words))) {
        return false;
    }

    constexpr std::array expected{
        pacman::path_distance{0},     pacman::path_distance{1},
        pacman::path_distance{2},     pacman::path_distance{1},
        pacman::unreachable_distance,
    };

    return distances == expected;
}

fn main() -> int {
    if (!test_cross_word_bitboard_operations()) {
        return 1;
    }

    if (!test_topology_masks()) {
        return 2;
    }

    if (!test_bfs_distances()) {
        return 3;
    }

    constexpr let width = std::size_t{200};
    constexpr let height = std::size_t{200};
    constexpr let tile_count = width * height;
    constexpr let word_count = pacman::words_for_tiles(tile_count);

    static std::array<pacman::tile_neighbors, tile_count> tiles{};

    let index_of = [](const std::size_t x,
                      const std::size_t y) -> pacman::tile_index {
        return static_cast<pacman::tile_index>(y * width + x);
    };

    for (std::size_t y = 0; y < height; ++y) {
        for (std::size_t x = 0; x < width; ++x) {
            let index = y * width + x;
            let up = (y + height - 1) % height;
            let right = (x + 1) % width;
            let down = (y + 1) % height;
            let left = (x + width - 1) % width;

            tiles[index].moves[0] = {
                .destination = index_of(x, up),
                .heading = pacman::direction::up,
                .wraparound = y == 0,
            };
            tiles[index].moves[1] = {
                .destination = index_of(right, y),
                .heading = pacman::direction::right,
                .wraparound = x == width - 1,
            };
            tiles[index].moves[2] = {
                .destination = index_of(x, down),
                .heading = pacman::direction::down,
                .wraparound = y == height - 1,
            };
            tiles[index].moves[3] = {
                .destination = index_of(left, y),
                .heading = pacman::direction::left,
                .wraparound = x == 0,
            };
            tiles[index].count = 4;
        }
    }

    static std::array<std::uint64_t, word_count> visited_words{};
    static std::array<std::uint64_t, word_count> frontier_words{};
    static std::array<std::uint64_t, word_count> next_words{};
    static std::array<std::uint64_t, word_count> scratch_words{};
    static std::array<pacman::path_distance, tile_count> distances{};
    static std::array<pacman::path_distance, tile_count> masked_distances{};
    static std::array<pacman::bitboard_word, word_count * 4> topology_words{};
    static std::array<pacman::topology_edge, tile_count * 4>
        exceptional_edges{};

    let visited = pacman::tile_set_view{
        .words = visited_words,
        .tile_count = tile_count,
    };
    let frontier = pacman::tile_set_view{
        .words = frontier_words,
        .tile_count = tile_count,
    };
    let next = pacman::tile_set_view{
        .words = next_words,
        .tile_count = tile_count,
    };
    let scratch = pacman::tile_set_view{
        .words = scratch_words,
        .tile_count = tile_count,
    };
    let graph = pacman::graph_view{
        .tiles = tiles,
    };
    let topology = pacman::topology_masks{
        .width = 0,
        .north = {topology_words.data(), word_count},
        .east = {topology_words.data() + word_count, word_count},
        .south = {topology_words.data() + word_count * 2, word_count},
        .west = {topology_words.data() + word_count * 3, word_count},
        .exceptional_edges = exceptional_edges,
        .exceptional_edge_count = 0,
    };

    if (!pacman::build_topology_masks(graph, width, topology)) {
        return 2;
    }

    if (!pacman::flood_reachable(graph, 0, visited, frontier, next)) {
        return 2;
    }

    let flood_started = std::chrono::steady_clock::now();
    let flood_success =
        pacman::flood_reachable(graph, 0, visited, frontier, next);
    let flood_elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - flood_started);

    if (!flood_success) {
        return 2;
    }

    let reachable = visited.count();
    if (reachable != tile_count) {
        return 3;
    }

    if (!visited.test(0) || !visited.test(tile_count - 1)) {
        return 4;
    }

    if (!pacman::bfs_distances(graph, 0, distances, visited, frontier, next)) {
        return 5;
    }

    let bfs_started = std::chrono::steady_clock::now();
    let bfs_success =
        pacman::bfs_distances(graph, 0, distances, visited, frontier, next);
    let bfs_elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - bfs_started);

    if (!bfs_success || distances[0] != 0 ||
        distances[index_of(width / 2, height / 2)] != width ||
        distances[index_of(width - 1, height - 1)] != 2) {
        return 6;
    }

    let masked_started = std::chrono::steady_clock::now();
    let masked_success =
        pacman::bfs_distances_masked(topology, tile_count, 0, masked_distances,
                                     visited, frontier, next, scratch);
    let masked_elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - masked_started);

    if (!masked_success || masked_distances != distances) {
        return 7;
    }

    std::printf("flood fill: %zux%zu maze, %zu reachable tiles\n", width,
                height, reachable);
    std::printf("flood fill time: %lld us\n",
                static_cast<long long>(flood_elapsed.count()));
    std::printf("BFS distance time: %lld us\n",
                static_cast<long long>(bfs_elapsed.count()));
    std::printf("masked BFS time: %lld us\n",
                static_cast<long long>(masked_elapsed.count()));
    return 0;
}
