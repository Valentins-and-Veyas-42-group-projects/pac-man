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

#define PACMAN_ABI_VERSION 1u

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

/* Return the supported stable C ABI version. */
PAC_API uint32_t pac_abi_version(void);

/* Compute a multiword bitwise OR into caller-owned output storage. */
PAC_API pac_status pac_bitboard_or(const uint64_t *lhs, const uint64_t *rhs,
                                   size_t word_count, uint64_t *output);

/* Compute shortest distances, writing UINT32_MAX for unreachable tiles. */
PAC_API pac_status pac_bfs_distances(const pac_tile_neighbors *tiles,
                                     size_t tile_count, uint16_t origin,
                                     uint32_t *distances,
                                     size_t distance_capacity);

#ifdef __cplusplus
}
#endif

#endif
