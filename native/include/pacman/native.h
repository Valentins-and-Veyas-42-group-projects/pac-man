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

/* Return the supported stable C ABI version. */
PAC_API uint32_t pac_abi_version(void);

/* Compute a multiword bitwise OR into caller-owned output storage. */
PAC_API pac_status pac_bitboard_or(const uint64_t *lhs, const uint64_t *rhs,
                                   size_t word_count, uint64_t *output);

#ifdef __cplusplus
}
#endif

#endif
