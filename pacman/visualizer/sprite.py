"""Antialiased sprites, prebuilt once per size and color."""

import math

import pygame

from ..models import Direction
from .layout import SUPERSAMPLE

# Half-angle of the mouth in degrees, in animation order (open, half, closed, half).
MOUTH_CYCLE = (40, 20, 0, 20)
Color = tuple[int, int, int]


def build_pacman(cell: int, color: Color) -> dict[Direction, list[pygame.Surface]]:
    """Return `MOUTH_CYCLE`-many frames per direction, drawn big and smoothscaled.

    Needs an initialized display (for `convert_alpha`).
    """
    size = max(6, cell * 3 // 4)
    big = size * SUPERSAMPLE
    r = big / 2
    frames: dict[Direction, list[pygame.Surface]] = {}
    for direction in Direction:
        facing = math.atan2(direction.value[1], direction.value[0])
        frames[direction] = []
        for half_deg in MOUTH_CYCLE:
            surf = pygame.Surface((big, big), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (r, r), r)
            if half_deg:
                half = math.radians(half_deg)
                wedge = [(r, r)] + [
                    (r + 2 * r * math.cos(facing + a), r + 2 * r * math.sin(facing + a))
                    for a in (-half, 0.0, half)
                ]
                pygame.draw.polygon(surf, (0, 0, 0, 0), wedge)  # punches a transparent mouth
            frames[direction].append(pygame.transform.smoothscale(surf, (size, size)).convert_alpha())
    return frames


def build_pellet(cell: int, color: Color) -> pygame.Surface:
    """Return one antialiased pellet; blit it per tile instead of redrawing circles."""
    size = max(3, cell // 5)
    big = size * SUPERSAMPLE
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    pygame.draw.circle(surf, color, (big / 2, big / 2), big / 2)
    return pygame.transform.smoothscale(surf, (size, size)).convert_alpha()
