module;

#include <pacman/macros.h>

#include <algorithm>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <span>
#include <utility>

export module pacman.branch_search;

import pacman.graph;
import pacman.simulation;
import pacman.types;

export namespace pacman {

/*
    require one first move
             │
             ▼
         frontier at tick 1
          /      |      \
     all legal next moves  ...  terminal branches

    Equal tactical states merge at each tick. Only the highest-scoring
    branch survives a merge, exactly as in the Python reference.
*/

enum class branch_search_status : std::uint8_t {
    ok,
    invalid_input,
    out_of_memory,
    capacity_exceeded,
};

struct branch_result {
    simulation_state best{};
    std::size_t path_length{};
};

/// Ghost state at (tick, ghost, tile): 0 absent, 1 dangerous,
/// 2 frightened, 3 eaten. All four ghosts have one contiguous tile slice.
struct prediction_grid {
    std::span<const std::uint8_t> states;
    std::size_t tile_count{};
    std::size_t tick_count{};

    [[nodiscard]]
    fn at(const std::size_t tick, const std::size_t ghost,
          const tile_index tile) const noexcept -> std::uint8_t {
        return states[(tick * 4 + ghost) * tile_count + tile];
    }
};

} // namespace pacman

namespace pacman::detail {

struct branch_slot {
    simulation_state state{};
};

[[nodiscard]]
fn hash_branch(const simulation_state &state,
               const std::span<const collectible> items) noexcept
    -> std::size_t {
    std::size_t hash = 2166136261u;
    const let mix = [&hash](const std::size_t value) noexcept {
        hash ^= value;
        hash *= 16777619u;
    };
    mix(state.tile);
    mix(static_cast<std::size_t>(state.heading));
    mix(state.tick);
    mix(state.frightened_remaining);
    mix(state.ghost_combo);
    mix(state.eaten_ghost_mask);
    mix(state.died);
    for (const let item : items) {
        mix(static_cast<std::size_t>(item));
    }
    return hash;
}

[[nodiscard]]
fn same_branch(const simulation_state &lhs, const simulation_state &rhs,
               const std::span<const collectible> lhs_items,
               const std::span<const collectible> rhs_items) noexcept -> bool {
    return lhs.tile == rhs.tile && lhs.heading == rhs.heading &&
           lhs.tick == rhs.tick &&
           lhs.frightened_remaining == rhs.frightened_remaining &&
           lhs.ghost_combo == rhs.ghost_combo &&
           lhs.eaten_ghost_mask == rhs.eaten_ghost_mask &&
           lhs.died == rhs.died &&
           std::equal(lhs_items.begin(), lhs_items.end(), rhs_items.begin());
}

[[nodiscard]]
fn better_terminal(const simulation_state &candidate,
                   const simulation_state &best) noexcept -> bool {
    if (candidate.died != best.died) {
        return !candidate.died;
    }
    if (candidate.tick != best.tick) {
        return candidate.tick > best.tick;
    }
    if (candidate.score_gained != best.score_gained) {
        return candidate.score_gained > best.score_gained;
    }
    const let candidate_ghosts = std::popcount(candidate.eaten_ghost_mask);
    const let best_ghosts = std::popcount(best.eaten_ghost_mask);
    if (candidate_ghosts != best_ghosts) {
        return candidate_ghosts > best_ghosts;
    }
    if (candidate.frightened_remaining != best.frightened_remaining) {
        return candidate.frightened_remaining > best.frightened_remaining;
    }
    return candidate.pacgums_eaten > best.pacgums_eaten;
}

fn contacts_for(const prediction_grid prediction, const tile_index origin,
                const tile_index destination, const std::size_t tick,
                ghost_contact (&output)[4]) noexcept -> std::size_t {
    std::size_t count = 0;
    for (std::size_t ghost = 0; ghost < 4; ++ghost) {
        let value = prediction.at(tick, ghost, destination);
        if (value == 0 && tick > 0 && prediction.at(tick, ghost, origin) != 0 &&
            prediction.at(tick - 1, ghost, destination) != 0) {
            value = prediction.at(tick, ghost, origin);
        }
        if (value != 0) {
            output[count++] = {
                .ghost = static_cast<std::uint8_t>(ghost),
                .kind = static_cast<contact_kind>(value - 1),
            };
        }
    }
    return count;
}

} // namespace pacman::detail

export namespace pacman {

/// Search every bounded continuation after one required legal first action.
/// State capacity is a resource limit; callers can retry or use Python on
/// `capacity_exceeded`. The best path is written into caller-owned storage.
[[nodiscard]]
fn search_action(const graph_view graph,
                 const std::span<const collectible> initial_collectibles,
                 const prediction_grid prediction, const tile_index origin,
                 const direction action, const std::size_t horizon,
                 const simulation_rules &rules,
                 const std::size_t state_capacity,
                 const std::span<tile_index> best_path,
                 branch_result &result) noexcept -> branch_search_status {
    const let tile_count = graph.tiles.size();
    if (!graph.is_valid() || !graph.contains(origin) || horizon == 0 ||
        horizon == std::numeric_limits<std::size_t>::max() ||
        state_capacity == 0 ||
        state_capacity > std::numeric_limits<std::size_t>::max() / 4 ||
        initial_collectibles.size() != tile_count ||
        prediction.tile_count != tile_count ||
        prediction.tick_count < horizon + 1 ||
        prediction.states.size() < prediction.tick_count * 4 * tile_count ||
        best_path.size() < horizon + 1 ||
        tile_count >
            std::numeric_limits<std::size_t>::max() / (state_capacity * 2) ||
        horizon + 1 >
            std::numeric_limits<std::size_t>::max() / (state_capacity * 2)) {
        return branch_search_status::invalid_input;
    }

    const move *first = nullptr;
    for (const let &candidate : graph.neighbors(origin)) {
        if (candidate.heading == action) {
            first = &candidate;
            break;
        }
    }
    if (first == nullptr) {
        return branch_search_status::invalid_input;
    }

    const let slots_count = state_capacity * 2;
    std::unique_ptr<detail::branch_slot[]> slots{
        new (std::nothrow) detail::branch_slot[slots_count]{}};
    std::unique_ptr<collectible[]> items{
        new (std::nothrow) collectible[slots_count * tile_count]{}};
    std::unique_ptr<tile_index[]> paths{
        new (std::nothrow) tile_index[slots_count * (horizon + 1)]{}};
    const let table_size = state_capacity * 4 + 1;
    std::unique_ptr<std::size_t[]> table{new (std::nothrow)
                                             std::size_t[table_size]{}};
    if (!slots || !items || !paths || !table) {
        return branch_search_status::out_of_memory;
    }

    const let item_span = [&](const std::size_t slot) noexcept {
        return std::span<collectible>{items.get() + slot * tile_count,
                                      tile_count};
    };
    const let path_span = [&](const std::size_t slot) noexcept {
        return std::span<tile_index>{paths.get() + slot * (horizon + 1),
                                     horizon + 1};
    };
    ghost_contact contact_buffer[4]{};
    const let first_contacts = detail::contacts_for(
        prediction, origin, first->destination, 1, contact_buffer);
    if (!advance_simulation_state({.tile = origin, .heading = action},
                                  initial_collectibles, first->destination,
                                  action, {contact_buffer, first_contacts},
                                  rules, item_span(0), slots[0].state)) {
        return branch_search_status::invalid_input;
    }
    path_span(0)[0] = origin;
    path_span(0)[1] = first->destination;

    std::size_t current_base = 0;
    std::size_t current_count = 1;
    bool has_best = false;
    while (current_count != 0) {
        const let next_base = current_base == 0 ? state_capacity : 0;
        std::fill_n(table.get(), table_size, std::size_t{0});
        std::size_t next_count = 0;
        for (std::size_t index = 0; index < current_count; ++index) {
            const let current_slot = current_base + index;
            const let &current = slots[current_slot].state;
            const let moves = graph.neighbors(current.tile);
            if (current.died || current.tick >= horizon || moves.empty()) {
                if (!has_best ||
                    detail::better_terminal(current, result.best)) {
                    result.best = current;
                    result.path_length = current.tick + 1;
                    std::copy_n(path_span(current_slot).begin(),
                                result.path_length, best_path.begin());
                    has_best = true;
                }
                continue;
            }
            for (const let &candidate : moves) {
                if (next_count >= state_capacity) {
                    return branch_search_status::capacity_exceeded;
                }
                const let candidate_slot = next_base + next_count;
                const let contacts = detail::contacts_for(
                    prediction, current.tile, candidate.destination,
                    current.tick + 1, contact_buffer);
                if (!advance_simulation_state(
                        current, item_span(current_slot), candidate.destination,
                        candidate.heading, {contact_buffer, contacts}, rules,
                        item_span(candidate_slot),
                        slots[candidate_slot].state)) {
                    return branch_search_status::invalid_input;
                }
                let candidate_path = path_span(candidate_slot);
                std::copy_n(path_span(current_slot).begin(), current.tick + 1,
                            candidate_path.begin());
                candidate_path[current.tick + 1] = candidate.destination;

                const let hash = detail::hash_branch(
                    slots[candidate_slot].state, item_span(candidate_slot));
                let table_index = hash % table_size;
                while (table[table_index] != 0) {
                    const let existing_slot =
                        next_base + table[table_index] - 1;
                    if (detail::same_branch(slots[candidate_slot].state,
                                            slots[existing_slot].state,
                                            item_span(candidate_slot),
                                            item_span(existing_slot))) {
                        if (slots[candidate_slot].state.score_gained >
                            slots[existing_slot].state.score_gained) {
                            slots[existing_slot].state =
                                slots[candidate_slot].state;
                            std::copy(item_span(candidate_slot).begin(),
                                      item_span(candidate_slot).end(),
                                      item_span(existing_slot).begin());
                            std::copy_n(candidate_path.begin(),
                                        current.tick + 2,
                                        path_span(existing_slot).begin());
                        }
                        break;
                    }
                    table_index = (table_index + 1) % table_size;
                }
                if (table[table_index] == 0) {
                    table[table_index] = next_count + 1;
                    ++next_count;
                }
            }
        }
        current_base = next_base;
        current_count = next_count;
    }
    return has_best ? branch_search_status::ok
                    : branch_search_status::invalid_input;
}

} // namespace pacman
