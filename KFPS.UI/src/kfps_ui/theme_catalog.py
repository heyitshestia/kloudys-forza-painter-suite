from __future__ import annotations

from dataclasses import dataclass


DEFAULT_THEME = "Night Blossom"
COMMAND_PROMPT_THEME = "Command Prompt"
WINDOWS_94_THEME = "Windows 94"
PATRONS_ATELIER_THEME = "Patron's Atelier"
CARBON_DARK_THEME = "Carbon Dark"
OVERDRIVE_200X_THEME = "Overdrive 200X"


@dataclass(frozen=True)
class ThemePreset:
    """Python-side registry entry for selectable QML theme presets.

    QML owns the actual palette tokens. Python owns persistence, validation,
    QML component identity for contract checks, and entitlement-gated
    visibility in Settings.
    """

    name: str
    qml_component: str
    supporter_only: bool = False
    reduced_motion_on_entry: bool | None = None
    ambient_motion_on_entry: bool | None = None
    glass_effects_on_entry: bool | None = None


THEME_PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset(DEFAULT_THEME, "PaletteNightBlossom"),
    ThemePreset(COMMAND_PROMPT_THEME, "PaletteCommandPrompt"),
    ThemePreset(
        WINDOWS_94_THEME,
        "PaletteWindows94",
        supporter_only=True,
        reduced_motion_on_entry=False,
        ambient_motion_on_entry=False,
        glass_effects_on_entry=False,
    ),
    ThemePreset(PATRONS_ATELIER_THEME, "PalettePatronsAtelier", supporter_only=True),
    ThemePreset(CARBON_DARK_THEME, "PaletteCarbonDark", supporter_only=True),
    ThemePreset(OVERDRIVE_200X_THEME, "PaletteOverdrive200X", supporter_only=True),
)

KNOWN_THEME_NAMES = frozenset(preset.name for preset in THEME_PRESETS)
PUBLIC_THEME_NAMES = tuple(preset.name for preset in THEME_PRESETS if not preset.supporter_only)
SUPPORTER_THEME_NAMES = tuple(preset.name for preset in THEME_PRESETS if preset.supporter_only)


def normalize_theme(value: object) -> str:
    text = str(value or "").strip()
    return text if text in KNOWN_THEME_NAMES else DEFAULT_THEME


def is_supporter_theme(value: object) -> bool:
    return normalize_theme(value) in SUPPORTER_THEME_NAMES


def available_theme_names(supporter_unlocked: bool) -> list[str]:
    names = list(PUBLIC_THEME_NAMES)
    if supporter_unlocked:
        names.extend(SUPPORTER_THEME_NAMES)
    return names


def theme_entry_preferences(value: object) -> dict[str, bool]:
    name = normalize_theme(value)
    preset = next(preset for preset in THEME_PRESETS if preset.name == name)
    preferences: dict[str, bool] = {}
    if preset.reduced_motion_on_entry is not None:
        preferences["reducedMotion"] = preset.reduced_motion_on_entry
    if preset.ambient_motion_on_entry is not None:
        preferences["ambientMotion"] = preset.ambient_motion_on_entry
    if preset.glass_effects_on_entry is not None:
        preferences["glassEffects"] = preset.glass_effects_on_entry
    return preferences
