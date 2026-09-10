#include <pacman/macros.h>

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>

import pacman.bitboard;
import pacman.flood_fill;
import pacman.graph;
import pacman.types;

[[nodiscard]]
fn flood_reachable_checked(const pacman::graph_view graph,
                           const pacman::tile_index origin,
                           pacman::tile_set_view visited,
                           pacman::tile_set_view frontier,
                           pacman::tile_set_view next) noexcept -> bool {
    if (!graph.is_valid() || !graph.contains(origin)) {
        return false;
    }

    if (!visited.clear() || !frontier.clear() || !next.clear() ||
        !visited.set(origin) || !frontier.set(origin)) {
        return false;
    }

    while (frontier.any()) {
        if (!pacman::expand_frontier(graph, frontier.as_const(), next) ||
            !next.and_not_with(visited.as_const()) ||
            !visited.or_with(next.as_const()) ||
            !frontier.copy_from(next.as_const())) {
            return false;
        }
    }

    return true;
}

fn main() -> int {
    constexpr let width = std::size_t{200};
    constexpr let height = std::size_t{200};
    constexpr let tile_count = width * height;
    constexpr let word_count = pacman::words_for_tiles(tile_count);

    std::array<pacman::tile_neighbors, tile_count> tiles{};

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

    std::array<std::uint64_t, word_count> visited_words{};
    std::array<std::uint64_t, word_count> frontier_words{};
    std::array<std::uint64_t, word_count> next_words{};

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
    let graph = pacman::graph_view{
        .tiles = tiles,
    };

    if (!flood_reachable_checked(graph, 0, visited, frontier, next) ||
        !pacman::flood_reachable(graph, 0, visited, frontier, next)) {
        return 1;
    }

    let checked_started = std::chrono::steady_clock::now();
    let checked_success =
        flood_reachable_checked(graph, 0, visited, frontier, next);
    let checked_elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - checked_started);
    let checked_words = visited_words;

    let unchecked_started = std::chrono::steady_clock::now();
    let unchecked_success =
        pacman::flood_reachable(graph, 0, visited, frontier, next);
    let unchecked_elapsed =
        std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - unchecked_started);

    if (!checked_success || !unchecked_success) {
        return 1;
    }

    let reachable = visited.count();
    if (reachable != tile_count) {
        return 2;
    }

    if (!visited.test(0) || !visited.test(tile_count - 1)) {
        return 3;
    }

    if (checked_words != visited_words) {
        return 4;
    }

    let checked_us = static_cast<long long>(checked_elapsed.count());
    let unchecked_us = static_cast<long long>(unchecked_elapsed.count());
    let speedup = unchecked_us == 0 ? 0.0
                                    : static_cast<double>(checked_us) /
                                          static_cast<double>(unchecked_us);

    std::printf("flood fill: %zux%zu maze, %zu reachable tiles\n", width,
                height, reachable);
    std::printf("checked expansion:   %lld us\n", checked_us);
    std::printf("unchecked expansion: %lld us\n", unchecked_us);
    std::printf("speedup: %.2fx\n", speedup);
    return 0;
}
