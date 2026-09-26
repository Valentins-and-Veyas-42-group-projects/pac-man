module;

#include <pacman/macros.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

export module pacman.simulation;

import pacman.types;

export namespace pacman {

/*
    before move                 after move

    Pac-Man at A  ────────────> Pac-Man at B
                                    │
                           eat item, then resolve
                           ghost contact at B

    One step owns no buffers. The caller keeps each branch's consumed-item
    bitset and supplies contact facts from the exact ghost prediction.
*/

enum class collectible : std::uint8_t {
    none = 0,
    pacgum = 1,
    power_pellet = 2,
};

enum class contact_kind : std::uint8_t {
    dangerous = 0,
    frightened = 1,
    eaten = 2,
};

struct ghost_contact {
    std::uint8_t ghost;
    contact_kind kind;
};

inline constexpr std::array<std::uint32_t, 4> default_ghost_combo_scores{
    200, 400, 800, 1600};

struct simulation_rules {
    std::uint32_t pacgum_score{10};
    std::uint32_t power_pellet_score{50};
    std::uint32_t frightened_ticks{8};
    std::span<const std::uint32_t> ghost_combo_scores{
        default_ghost_combo_scores};
};

struct simulation_state {
    tile_index tile{};
    direction heading{};
    std::size_t tick{};
    std::uint32_t frightened_remaining{};
    std::size_t ghost_combo{};
    std::uint64_t score_gained{};
    std::size_t pacgums_eaten{};
    std::size_t power_pellets_eaten{};
    std::uint8_t eaten_ghost_mask{};
    bool died{};
};

/// Advance one branch, consuming the destination item before ghost contact.
/// The output snapshot must not overlap the input snapshot.
[[nodiscard]]
fn advance_simulation_state(
    const simulation_state &before,
    const std::span<const collectible> initial_collectibles,
    const std::span<const std::uint64_t> before_consumed,
    const tile_index destination, const direction heading,
    const std::span<const ghost_contact> contacts,
    const simulation_rules &rules,
    const std::span<std::uint64_t> after_consumed,
    simulation_state &after) noexcept -> bool {
    const let word_count = initial_collectibles.size() / 64 +
                           (initial_collectibles.size() % 64 != 0);
    if (destination >= initial_collectibles.size() ||
        after_consumed.size() != word_count ||
        (!before_consumed.empty() &&
         (before_consumed.size() != word_count ||
          before_consumed.data() == after_consumed.data()))) {
        return false;
    }
    for (const let contact : contacts) {
        if (contact.ghost >= 4 || contact.kind > contact_kind::eaten) {
            return false;
        }
    }

    if (before_consumed.empty()) {
        std::fill(after_consumed.begin(), after_consumed.end(), 0);
    } else {
        std::copy(before_consumed.begin(), before_consumed.end(),
                  after_consumed.begin());
    }
    after = before;
    after.tile = destination;
    after.heading = heading;
    ++after.tick;
    after.frightened_remaining =
        before.frightened_remaining > 0 ? before.frightened_remaining - 1 : 0;
    if (after.frightened_remaining == 0) {
        after.ghost_combo = 0;
    }

    const let word = static_cast<std::size_t>(destination) / 64;
    const let bit = std::uint64_t{1} << (destination % 64);
    const bool already_consumed = (before_consumed.empty()
                                       ? std::uint64_t{0}
                                       : before_consumed[word]) & bit;
    if (!already_consumed) {
        switch (initial_collectibles[destination]) {
        case collectible::none:
            break;
        case collectible::pacgum:
            after_consumed[word] |= bit;
            after.score_gained += rules.pacgum_score;
            ++after.pacgums_eaten;
            break;
        case collectible::power_pellet:
            after_consumed[word] |= bit;
            after.score_gained += rules.power_pellet_score;
            ++after.power_pellets_eaten;
            after.frightened_remaining = rules.frightened_ticks;
            after.ghost_combo = 0;
            break;
        }
    }

    std::uint8_t contacted_ghosts = 0;
    for (const let contact : contacts) {
        const let ghost_bit = static_cast<std::uint8_t>(1u << contact.ghost);
        if ((contacted_ghosts & ghost_bit) != 0) {
            continue;
        }
        contacted_ghosts |= ghost_bit;
        if ((after.eaten_ghost_mask & ghost_bit) != 0 ||
            contact.kind == contact_kind::eaten) {
            continue;
        }
        if (after.frightened_remaining > 0 ||
            contact.kind == contact_kind::frightened) {
            if (!rules.ghost_combo_scores.empty()) {
                const let reward_index = std::min(
                    after.ghost_combo, rules.ghost_combo_scores.size() - 1);
                after.score_gained += rules.ghost_combo_scores[reward_index];
            }
            ++after.ghost_combo;
            after.eaten_ghost_mask |= ghost_bit;
        } else {
            after.died = true;
        }
    }
    return true;
}

} // namespace pacman
