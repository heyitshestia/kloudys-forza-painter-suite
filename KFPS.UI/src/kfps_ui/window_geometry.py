from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


PREFERRED_WIDTH = 1760
PREFERRED_HEIGHT = 1040
MINIMUM_WIDTH = 960
MINIMUM_HEIGHT = 600
FRESH_WINDOW_SCREEN_FRACTION = 0.92


@dataclass(frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class WindowPlacement:
    x: int
    y: int
    width: int
    height: int
    maximized: bool = False


def _integer(payload: Mapping[str, object], key: str, fallback: int = 0) -> int:
    try:
        return int(payload.get(key, fallback))
    except (TypeError, ValueError, OverflowError):
        return fallback


def _intersection_area(a: ScreenRect, b: ScreenRect) -> int:
    width = max(0, min(a.right, b.right) - max(a.x, b.x))
    height = max(0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return width * height


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _fresh_dimension(preferred: int, minimum: int, available: int) -> int:
    if available <= 0:
        return minimum
    floor = min(minimum, available)
    fitted = min(preferred, max(1, round(available * FRESH_WINDOW_SCREEN_FRACTION)))
    return _clamp(fitted, floor, available)


def _centered(screen: ScreenRect, width: int, height: int, maximized: bool = False) -> WindowPlacement:
    return WindowPlacement(
        x=screen.x + max(0, (screen.width - width) // 2),
        y=screen.y + max(0, (screen.height - height) // 2),
        width=width,
        height=height,
        maximized=maximized,
    )


def calculate_window_placement(
    screens: Sequence[ScreenRect],
    saved: Mapping[str, object] | None = None,
    requested_width: int | None = None,
    requested_height: int | None = None,
) -> WindowPlacement:
    available_screens = tuple(screen for screen in screens if screen.width > 0 and screen.height > 0)
    if not available_screens:
        available_screens = (ScreenRect(0, 0, PREFERRED_WIDTH, PREFERRED_HEIGHT),)
    primary = available_screens[0]

    # Explicit dimensions are used by deterministic screenshot/layout tools.
    # They intentionally may exceed the virtual offscreen platform's fake screen.
    if requested_width is not None or requested_height is not None:
        width = max(MINIMUM_WIDTH, int(requested_width or PREFERRED_WIDTH))
        height = max(MINIMUM_HEIGHT, int(requested_height or PREFERRED_HEIGHT))
        return _centered(primary, width, height)

    payload = saved if isinstance(saved, Mapping) else {}
    saved_width = _integer(payload, "width")
    saved_height = _integer(payload, "height")
    has_saved_geometry = saved_width > 0 and saved_height > 0

    if not has_saved_geometry:
        return _centered(
            primary,
            _fresh_dimension(PREFERRED_WIDTH, MINIMUM_WIDTH, primary.width),
            _fresh_dimension(PREFERRED_HEIGHT, MINIMUM_HEIGHT, primary.height),
        )

    saved_rect = ScreenRect(
        _integer(payload, "x"),
        _integer(payload, "y"),
        saved_width,
        saved_height,
    )
    target = max(available_screens, key=lambda screen: _intersection_area(saved_rect, screen))
    if _intersection_area(saved_rect, target) == 0:
        target = primary

    width = min(target.width, max(min(MINIMUM_WIDTH, target.width), saved_width))
    height = min(target.height, max(min(MINIMUM_HEIGHT, target.height), saved_height))
    x = _clamp(saved_rect.x, target.x, target.right - width)
    y = _clamp(saved_rect.y, target.y, target.bottom - height)
    return WindowPlacement(
        x=x,
        y=y,
        width=width,
        height=height,
        maximized=bool(payload.get("maximized", False)),
    )
