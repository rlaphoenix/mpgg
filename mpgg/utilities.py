from __future__ import annotations

import math
from itertools import groupby
from typing import Any, Union


def get_aspect_ratio(width: int, height: int) -> str:
    """Calculate the aspect-ratio gcd string from resolution."""
    r = math.gcd(width, height)
    return "%d:%d" % (int(width / r), int(height / r))


def get_par(width: int, height: int, aspect_ratio_w: int, aspect_ratio_h: int) -> str:
    """Calculate the pixel-aspect-ratio string from resolution."""
    par_w = height * aspect_ratio_w
    par_h = width * aspect_ratio_h
    par_gcd = math.gcd(par_w, par_h)
    par_w = int(par_w / par_gcd)
    par_h = int(par_h / par_gcd)
    return "%d:%d" % (par_w, par_h)


def get_standard(aspect: float) -> str:
    """Convert an aspect float to a standard string."""
    return {
        0: "?",
        24 / 1: "FILM",
        25 / 1: "PAL",
        50 / 1: "PALi",
        30000 / 1001: "NTSC",
        60000 / 1001: "NTSCi",
        24000 / 1001: "NTSC (FILM)"
    }[aspect]


def group_numbers(numbers: list[int]) -> list[list[int]]:
    """
    Group consecutive numbers into sub-lists.

    Note: It does not pre-sort the input numbers.

    For example:
    >>> group_numbers([1, 2, 3, 5, 6, 7, 9])
    [[1, 2, 3], [5, 6, 7], [9]]

    Parameters:
        numbers: list of numbers to group.
    """
    for k, g in groupby(enumerate(numbers), lambda x: x[0] - x[1]):
        yield list(map(lambda x: x[1], g))


def list_select_every(data: list[Any], cycle: int, offsets: list[int], inverse: Union[bool, int] = False) -> list[Any]:
    """
    VapourSynth's SelectEvery for generic list data, and inverse.

    Parameters:
        data: data to select entries from.
        cycle: number of entries to assess at a time.
        offsets: offsets of entries to take per cycle (zero-indexed).
        inverse: invert the offsets and take the entries it did not want.
    """
    if not isinstance(cycle, int) or cycle < 1:
        raise ValueError("Cycle must be an int greater than or equal to 1.")

    if not isinstance(offsets, list):
        raise TypeError(f"Expected offsets to be a {list!r}, not {offsets}")
    if not offsets:
        raise ValueError("Offsets must not be empty.")
    if any(not isinstance(x, int) for x in offsets):
        raise TypeError(f"Expected offsets to be a {list!r} of {int!r}, not {offsets}")

    if not isinstance(inverse, (bool, int)) or (isinstance(inverse, int) and inverse not in (0, 1)):
        raise TypeError(f"Expected inverse to be a {bool!r} or boolean-like {int!r}, not {inverse}")

    # TODO: Should this be removed to allow duplicates?
    offsets = set(offsets)

    return [
        x
        for n, x in enumerate(data)
        if (n % cycle in offsets) ^ inverse
    ]


__ALL__ = (get_aspect_ratio, get_par, get_standard, group_numbers, list_select_every)
