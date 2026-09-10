export module pacman.bitboard;

import pacman.kernel.scalar;
import pacman.types;

export namespace pacman {

void bitboard_or(
    const bitboard_word *lhs,
    const bitboard_word *rhs,
    word_count words,
    bitboard_word *output
) noexcept {
    kernel::scalar::bitboard_or(lhs, rhs, words, output);
}

}
