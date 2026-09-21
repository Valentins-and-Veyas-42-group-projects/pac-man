#ifndef PACMAN_NATIVE_H
#define PACMAN_NATIVE_H

#include <stddef.h>
#include <stdint.h>

#if defined(__GNUC__) || defined(__clang__)
#define PAC_API __attribute__((visibility("default")))
#else
#define PAC_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define PACMAN_ABI_VERSION 2u

typedef enum pac_status {
    PAC_OK = 0,
    PAC_INVALID_ARGUMENT = 1,
    PAC_BUFFER_TOO_SMALL = 2,
    PAC_INTERNAL_ERROR = 3
} pac_status;

typedef uint8_t pac_direction;

#define PAC_DIRECTION_UP UINT8_C(0)
#define PAC_DIRECTION_RIGHT UINT8_C(1)
#define PAC_DIRECTION_DOWN UINT8_C(2)
#define PAC_DIRECTION_LEFT UINT8_C(3)

typedef struct pac_move {
    uint16_t destination;
    pac_direction direction;
    uint8_t wraparound;
} pac_move;

typedef struct pac_tile_neighbors {
    pac_move moves[4];
    uint8_t count;
    uint8_t reserved;
} pac_tile_neighbors;

typedef struct pac_ghost_origin {
    uint16_t tile;
    uint8_t ghost;
    uint8_t dangerous;
} pac_ghost_origin;

typedef struct pac_predicted_ghost {
    uint16_t tile;
    pac_direction direction;
    uint8_t ghost;
    uint8_t dangerous;
    uint8_t reserved[3];
} pac_predicted_ghost;

typedef struct pac_action_evaluation {
    uint32_t safe_tiles;
    uint32_t safe_intersections;
    uint32_t horizon_ticks;
    int32_t minimum_margin;
    uint16_t first_tile;
    uint8_t direction;
    uint8_t has_minimum_margin;
} pac_action_evaluation;

typedef struct pac_topology pac_topology;

/* Return the supported stable C ABI version. */
PAC_API uint32_t pac_abi_version(void);

/* Compute a multiword bitwise OR into caller-owned output storage. */
PAC_API pac_status pac_bitboard_or(const uint64_t *lhs, const uint64_t *rhs,
                                   size_t word_count, uint64_t *output);

/* Compute shortest distances, writing UINT32_MAX for unreachable tiles. */
PAC_API pac_status pac_bfs_distances(const pac_tile_neighbors *tiles,
                                     size_t tile_count, size_t maze_width,
                                     uint16_t origin, uint32_t *distances,
                                     size_t distance_capacity);

/* Create reusable immutable topology and BFS workspace. */
PAC_API pac_status pac_topology_create(const pac_tile_neighbors *tiles,
                                       size_t tile_count, size_t maze_width,
                                       pac_topology **output);

/* Release a topology created by pac_topology_create. Accepts NULL. */
PAC_API void pac_topology_destroy(pac_topology *topology);

/* Compute distances using a reusable topology. Calls are synchronized. */
PAC_API pac_status pac_topology_bfs_distances(pac_topology *topology,
                                              uint16_t origin,
                                              uint32_t *distances,
                                              size_t distance_capacity);

/* Compute distances through the cached graph-walking kernel. */
PAC_API pac_status pac_topology_bfs_distances_graph(pac_topology *topology,
                                                    uint16_t origin,
                                                    uint32_t *distances,
                                                    size_t distance_capacity);

/* Compute distances through the cached masked kernel. */
PAC_API pac_status pac_topology_bfs_distances_masked(pac_topology *topology,
                                                     uint16_t origin,
                                                     uint32_t *distances,
                                                     size_t distance_capacity);

/* Compute consecutive distance fields using the selected cached kernel. */
PAC_API pac_status pac_topology_bfs_many(pac_topology *topology,
                                         const uint16_t *origins,
                                         size_t origin_count,
                                         uint32_t *distance_fields,
                                         size_t distance_capacity);

/* Compute player distances and the earliest dangerous-ghost arrivals. */
PAC_API pac_status pac_topology_analyze_distances(
    pac_topology *topology, uint16_t player_origin,
    const pac_ghost_origin *ghosts, size_t ghost_count,
    uint32_t *player_distances, size_t player_distance_capacity,
    uint32_t *threat_eta, uint8_t *threat_owners, size_t threat_capacity);

/* Compute only the earliest dangerous-ghost arrivals. */
PAC_API pac_status pac_topology_threat_field(
    pac_topology *topology, const pac_ghost_origin *ghosts, size_t ghost_count,
    uint32_t *threat_eta, uint8_t *threat_owners, size_t threat_capacity);

/* Predict bounded ghost movement and combine earliest dangerous arrivals. */
PAC_API pac_status pac_topology_predict_threat(
    pac_topology *topology, const pac_predicted_ghost *ghosts,
    size_t ghost_count, size_t horizon, uint32_t *threat_eta,
    uint8_t *threat_owners, size_t threat_capacity);

/* Reachable output contains four tile_count-element slices in BFS order. */
PAC_API pac_status pac_topology_evaluate_actions(
    pac_topology *topology, uint16_t player_tile, const uint32_t *threat_eta,
    size_t threat_capacity, pac_action_evaluation *actions,
    size_t action_capacity, uint16_t *reachable, size_t reachable_capacity,
    size_t *action_count);

/* One-shot graph-walking BFS retained for measured comparisons. */
PAC_API pac_status pac_bfs_distances_graph(const pac_tile_neighbors *tiles,
                                           size_t tile_count, uint16_t origin,
                                           uint32_t *distances,
                                           size_t distance_capacity);

#ifdef __cplusplus
}
#endif

#endif
