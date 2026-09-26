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

/*
    Branch search keeps the collectible bitset for exact state comparisons,
    but updates an XOR fingerprint only when a collectible is consumed.
    Hash matches are still checked against the full bitset.

    Frontier slots alternate between two buffers and are overwritten each
    tick. Persistent trace nodes preserve ancestry without copying each path;
    only the winning path is reconstructed at the end.
*/

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

struct prediction_grid {
    std::span<const std::uint8_t> states;
    std::span<const std::uint8_t> ghost_order;
    std::size_t tile_count{};
    std::size_t tick_count{};

    /// Return the ghost state at one tick, ghost index, and tile.
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
    // XORing consumed-tile fingerprints avoids rescanning the bitset per child.
    std::uint64_t collectible_hash{};
    std::size_t trace{};
};

struct trace_node {
    // Frontier slots are reused, so path ancestry must outlive each frontier.
    std::size_t parent{};
    tile_index tile{};
};

[[nodiscard]]
fn hash_branch(const branch_slot &slot) noexcept -> std::size_t {
    std::uint64_t hash = slot.collectible_hash ^ 1469598103934665603ull;
    const let mix = [&hash](const std::uint64_t value) noexcept {
        hash ^= value;
        hash *= 1099511628211ull;
    };
    const let &state = slot.state;
    mix(state.tile);
    mix(static_cast<std::uint64_t>(state.heading));
    mix(state.tick);
    mix(state.frightened_remaining);
    mix(state.ghost_combo);
    mix(state.eaten_ghost_mask);
    mix(state.died);
    return static_cast<std::size_t>(hash);
}

[[nodiscard]]
constexpr fn collectible_fingerprint(const std::size_t id) noexcept
    -> std::uint64_t {
    std::uint64_t value = static_cast<std::uint64_t>(id) + 0x9e3779b97f4a7c15ull;
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ull;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebull;
    return value ^ (value >> 31);
}

// Hashes filter candidates; same_branch still checks exact state equality.
[[nodiscard]]
fn same_branch(const simulation_state &lhs, const simulation_state &rhs,
               const std::span<const std::uint64_t> lhs_consumed,
               const std::span<const std::uint64_t> rhs_consumed) noexcept -> bool {
    return lhs.tile == rhs.tile && lhs.heading == rhs.heading &&
           lhs.tick == rhs.tick &&
           lhs.frightened_remaining == rhs.frightened_remaining &&
           lhs.ghost_combo == rhs.ghost_combo &&
           lhs.eaten_ghost_mask == rhs.eaten_ghost_mask &&
           lhs.died == rhs.died &&
           std::equal(lhs_consumed.begin(), lhs_consumed.end(),
                      rhs_consumed.begin());
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
    for (const let ghost : prediction.ghost_order) {
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

/// Search continuations after the required first action.
///
/// On success, writes the best terminal state to `result` and its path to
/// `best_path`. Returns `invalid_input`, `out_of_memory`, or
/// `capacity_exceeded` when the search cannot complete.
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
    if (tile_count == 0 || !graph.is_valid() || !graph.contains(origin) ||
        horizon == 0 ||
        horizon == std::numeric_limits<std::size_t>::max() ||
        state_capacity == 0 ||
        state_capacity >= std::numeric_limits<std::size_t>::max() / 4 ||
        initial_collectibles.size() != tile_count ||
        prediction.tile_count != tile_count ||
        prediction.ghost_order.size() > 4 ||
        prediction.tick_count < horizon + 1 ||
        prediction.tick_count >
            std::numeric_limits<std::size_t>::max() / (4 * tile_count) ||
        prediction.states.size() < prediction.tick_count * 4 * tile_count ||
        best_path.size() < horizon + 1 ||
        tile_count >
            std::numeric_limits<std::size_t>::max() / (state_capacity * 2) ||
        horizon + 1 >
            std::numeric_limits<std::size_t>::max() / (state_capacity * 2)) {
        return branch_search_status::invalid_input;
    }
    std::uint8_t seen_ghosts = 0;
    for (const let ghost : prediction.ghost_order) {
        if (ghost >= 4 || (seen_ghosts & (1u << ghost)) != 0) {
            return branch_search_status::invalid_input;
        }
        seen_ghosts |= static_cast<std::uint8_t>(1u << ghost);
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
    const let consumed_words = tile_count / 64 + (tile_count % 64 != 0);
    if (consumed_words != 0 &&
        slots_count > std::numeric_limits<std::size_t>::max() /
                          consumed_words) {
        return branch_search_status::invalid_input;
    }
    std::unique_ptr<std::uint64_t[]> consumed{
        new (std::nothrow) std::uint64_t[slots_count * consumed_words]{}};
    if (horizon > (std::numeric_limits<std::size_t>::max() - 2) /
                      (state_capacity * 4)) {
        return branch_search_status::invalid_input;
    }
    const let trace_capacity = horizon * state_capacity * 4 + 2;
    std::unique_ptr<detail::trace_node[]> traces{
        new (std::nothrow) detail::trace_node[trace_capacity]{}};
    const let table_size = state_capacity * 4 + 1;
    std::unique_ptr<std::size_t[]> table{new (std::nothrow)
                                             std::size_t[table_size]{}};
    if (!slots || !consumed || !traces || !table) {
        return branch_search_status::out_of_memory;
    }

    const let consumed_span = [&](const std::size_t slot) noexcept {
        return std::span<std::uint64_t>{
            consumed.get() + slot * consumed_words, consumed_words};
    };
    const let no_trace = std::numeric_limits<std::size_t>::max();
    traces[0] = {.parent = no_trace, .tile = origin};
    ghost_contact contact_buffer[4]{};
    const let first_contacts = detail::contacts_for(
        prediction, origin, first->destination, 1, contact_buffer);
    if (!advance_simulation_state({.tile = origin, .heading = action},
                                  initial_collectibles, {}, first->destination,
                                  action, {contact_buffer, first_contacts},
                                  rules, consumed_span(0), slots[0].state)) {
        return branch_search_status::invalid_input;
    }
    slots[0].collectible_hash = 0;
    const let first_word = static_cast<std::size_t>(first->destination) / 64;
    const let first_bit = std::uint64_t{1} << (first->destination % 64);
    if (initial_collectibles[first->destination] != collectible::none &&
        (consumed[0 * consumed_words + first_word] & first_bit) != 0) {
        slots[0].collectible_hash ^=
            detail::collectible_fingerprint(first->destination);
    }
    traces[1] = {.parent = 0, .tile = first->destination};
    slots[0].trace = 1;
    std::size_t trace_count = 2;

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
                    let trace = slots[current_slot].trace;
                    std::size_t path_index = result.path_length;
                    while (trace != no_trace) {
                        best_path[--path_index] = traces[trace].tile;
                        trace = traces[trace].parent;
                    }
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
                        current, initial_collectibles,
                        consumed_span(current_slot), candidate.destination,
                        candidate.heading, {contact_buffer, contacts}, rules,
                        consumed_span(candidate_slot),
                        slots[candidate_slot].state)) {
                    return branch_search_status::invalid_input;
                }
                slots[candidate_slot].collectible_hash =
                    slots[current_slot].collectible_hash;
                const let word = static_cast<std::size_t>(candidate.destination) / 64;
                const let bit = std::uint64_t{1} << (candidate.destination % 64);
                if (initial_collectibles[candidate.destination] != collectible::none &&
                    (consumed_span(candidate_slot)[word] & bit) != 0 &&
                    (consumed_span(current_slot)[word] & bit) == 0) {
                    slots[candidate_slot].collectible_hash ^=
                        detail::collectible_fingerprint(candidate.destination);
                }
                if (trace_count >= trace_capacity) {
                    return branch_search_status::capacity_exceeded;
                }
                traces[trace_count] = {
                    .parent = slots[current_slot].trace,
                    .tile = candidate.destination,
                };
                slots[candidate_slot].trace = trace_count++;

                const let hash = detail::hash_branch(slots[candidate_slot]);
                let table_index = hash % table_size;
                while (table[table_index] != 0) {
                    const let existing_slot =
                        next_base + table[table_index] - 1;
                    if (detail::same_branch(slots[candidate_slot].state,
                                            slots[existing_slot].state,
                                            consumed_span(candidate_slot),
                                            consumed_span(existing_slot))) {
                        if (slots[candidate_slot].state.score_gained >
                            slots[existing_slot].state.score_gained) {
                            slots[existing_slot].state =
                                slots[candidate_slot].state;
                            std::copy(consumed_span(candidate_slot).begin(),
                                      consumed_span(candidate_slot).end(),
                                      consumed_span(existing_slot).begin());
                            slots[existing_slot].collectible_hash =
                                slots[candidate_slot].collectible_hash;
                            slots[existing_slot].trace =
                                slots[candidate_slot].trace;
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
