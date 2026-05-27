import json
import os
import re
from dataclasses import dataclass

import bpy

from render_lib.logging_utils import log

SETTINGS_FILENAME = "render_settings.json"
PHONES_DIRNAME = "phones"

DEFAULT_BASIC = {
    "output_dir": "//renders/",
    "resolution": {"x": 1440, "y": 2560},
    "resolution_percentage": 100,
    "samples": 256,
    "transparent_background": True,
    "device": "GPU",
    "outputs": {
        "png_with_shadow": True,
        "png_no_shadow": False,
        "svg_no_shadow": False,
    },
    "key_light": False,
}

DEFAULT_ADVANCED = {
    "use_auto_tile": True,
    "tile_size": 1024,
    "use_persistent_data": True,
    "fit_margin": 1.08,
    "shadow_fit_margin": 1.3,
    "default_lens_mm": 50,
    "supported_extensions": [".png", ".jpg", ".jpeg", ".webp"],
    "view_transform": "Standard",
    "view_look": "None",
    "view_exposure": 0.0,
    "view_gamma": 1.0,
    "shadow_catcher_size_multiplier": 16.0,
    "shadow_catcher_z_offset": 0.0,
    "alpha_threshold": 0.05,
    "key_light_strength": 1.5,
    "key_light_elevation_deg": 50.0,
    "key_light_angle_deg": 65.0,
    "key_light_shadow_azimuth_deg": 315.0,
    "key_light_color": [1.0, 1.0, 1.0],
    "key_light_visible_glossy": False,
    "key_light_visible_transmission": False,
    "phone_isolate_indirect": True,
    "screen_emission_isolate": True,
    "screen_emission_allow_glossy": True,
    "svg_alpha_threshold": 0.5,
    "svg_outline_simplify_tolerance_px": 0.75,
    "angles": [
        {"name": "front",                  "tilt_deg": 15, "yaw_deg": 180, "distance_multiplier": 1.0},
        {"name": "threequarter_left",      "tilt_deg": 30, "yaw_deg": 215, "distance_multiplier": 1.0},
        {"name": "threequarter_right",     "tilt_deg": 30, "yaw_deg": 145, "distance_multiplier": 1.0},
        {"name": "threequarter_left_top",  "tilt_deg": 30, "yaw_deg": 325, "distance_multiplier": 1.0},
        {"name": "threequarter_right_top", "tilt_deg": 30, "yaw_deg":  35, "distance_multiplier": 1.0},
        {"name": "hero_top",               "tilt_deg":  0, "yaw_deg":   0, "distance_multiplier": 1.1},
    ],
}

DEFAULT_SCENES = {
    "iOS": {
        "phone_object":    "iPhone 17 ProMax",
        "screen_material": "17ProMax_Screen",
        "screens_dir":     "//screenshots/iOS/",
        "screen_node_id":  "ScreenTextureiOS",
    },
    "Android": {
        "phone_object":    "Google Pixel 9 Pro XL",
        "screen_material": "GP9XL_Screen",
        "screens_dir":     "//screenshots/Android/",
        "screen_node_id":  "ScreenTextureAndroid",
    },
}

DEFAULT_SETTINGS = {**DEFAULT_BASIC, **DEFAULT_ADVANCED, "scenes": DEFAULT_SCENES}


@dataclass(frozen=True)
class Outputs:
    png_with_shadow: bool
    png_no_shadow: bool
    svg_no_shadow: bool


@dataclass(frozen=True)
class Angle:
    name: str
    tilt_deg: float
    yaw_deg: float
    distance_multiplier: float = 1.0


@dataclass(frozen=True)
class Settings:
    output_dir: str
    res_x: int
    res_y: int
    res_percent: int
    samples: int
    transparent_bg: bool
    device: str
    use_auto_tile: bool
    tile_size: int
    use_persistent_data: bool
    fit_margin: float
    shadow_fit_margin: float
    default_lens_mm: float
    supported_exts: tuple[str, ...]
    view_transform: str
    view_look: str
    view_exposure: float
    view_gamma: float
    shadow_catcher_size: float
    shadow_catcher_z: float
    alpha_threshold: float
    key_light: bool
    key_light_strength: float
    key_light_elevation_deg: float
    key_light_angle_deg: float
    key_light_shadow_azimuth_deg: float
    key_light_color: tuple[float, float, float]
    key_light_visible_glossy: bool
    key_light_visible_transmission: bool
    phone_isolate_indirect: bool
    screen_emission_isolate: bool
    screen_emission_allow_glossy: bool
    svg_alpha_threshold: float
    svg_simplify_tol_px: float
    screen_node_id: str
    angles: tuple[Angle, ...]
    outputs: Outputs
    scenes: dict[str, dict]

    def for_scene(self, cfg: dict) -> "SceneSettings":
        """Resolve per-scene overrides and output flags against this global config."""
        overridden = []
        scene_outputs = resolve_outputs(cfg, fallback=self.outputs)

        def _resolve(key, global_val, coerce):
            if key not in cfg:
                return global_val
            try:
                value = coerce(cfg[key])
            except (TypeError, ValueError) as exc:
                log(
                    f"[warn] scene override for '{key}'={cfg[key]!r} could not be "
                    f"coerced ({exc}); using global default"
                )
                return global_val
            if value != global_val:
                overridden.append(f"{key}={value!r} (default {global_val!r})")
            return value

        resolved = SceneSettings(
            fit_margin=_resolve("fit_margin", self.fit_margin, float),
            shadow_fit_margin=_resolve("shadow_fit_margin", self.shadow_fit_margin, float),
            shadow_catcher_size=_resolve(
                "shadow_catcher_size_multiplier", self.shadow_catcher_size, float
            ),
            shadow_catcher_z=_resolve(
                "shadow_catcher_z_offset", self.shadow_catcher_z, float
            ),
            alpha_threshold=_resolve("alpha_threshold", self.alpha_threshold, float),
            key_light=_resolve("key_light", self.key_light, bool),
            key_light_strength=_resolve(
                "key_light_strength", self.key_light_strength, float
            ),
            key_light_elevation_deg=_resolve(
                "key_light_elevation_deg", self.key_light_elevation_deg, float
            ),
            key_light_angle_deg=_resolve(
                "key_light_angle_deg", self.key_light_angle_deg, float
            ),
            key_light_shadow_azimuth_deg=_resolve(
                "key_light_shadow_azimuth_deg", self.key_light_shadow_azimuth_deg, float
            ),
            key_light_color=_resolve("key_light_color", self.key_light_color, _as_color3),
            key_light_visible_glossy=_resolve(
                "key_light_visible_glossy", self.key_light_visible_glossy, bool
            ),
            key_light_visible_transmission=_resolve(
                "key_light_visible_transmission", self.key_light_visible_transmission, bool
            ),
            phone_isolate_indirect=_resolve(
                "phone_isolate_indirect", self.phone_isolate_indirect, bool
            ),
            screen_emission_isolate=_resolve(
                "screen_emission_isolate", self.screen_emission_isolate, bool
            ),
            screen_emission_allow_glossy=_resolve(
                "screen_emission_allow_glossy", self.screen_emission_allow_glossy, bool
            ),
            outputs=scene_outputs,
        )

        if overridden:
            log("[overrides] per-scene values in effect:")
            for line in overridden:
                log(f"  - {line}")

        return resolved


@dataclass(frozen=True)
class SceneSettings:
    fit_margin: float
    shadow_fit_margin: float
    shadow_catcher_size: float
    shadow_catcher_z: float
    alpha_threshold: float
    key_light: bool
    key_light_strength: float
    key_light_elevation_deg: float
    key_light_angle_deg: float
    key_light_shadow_azimuth_deg: float
    key_light_color: tuple[float, float, float]
    key_light_visible_glossy: bool
    key_light_visible_transmission: bool
    phone_isolate_indirect: bool
    screen_emission_isolate: bool
    screen_emission_allow_glossy: bool
    outputs: Outputs


def _as_color3(v):
    seq = list(v) + [1.0, 1.0, 1.0]
    return tuple(float(c) for c in seq[:3])


def resolve_outputs(raw: dict, fallback: Outputs | None = None) -> Outputs:
    """Single source of truth for output-flag resolution.

    Priority:
      1. explicit ``outputs`` dict (missing keys inherit from ``fallback``)
      2. legacy ``shadow_catcher`` boolean when no ``outputs`` key is present
      3. ``fallback`` (or all-off if no fallback supplied)
    """
    fb = fallback or Outputs(False, False, False)

    raw_outputs = raw.get("outputs")
    if isinstance(raw_outputs, dict):
        return Outputs(
            png_with_shadow=bool(raw_outputs.get("png_with_shadow", fb.png_with_shadow)),
            png_no_shadow=bool(raw_outputs.get("png_no_shadow", fb.png_no_shadow)),
            svg_no_shadow=bool(raw_outputs.get("svg_no_shadow", fb.svg_no_shadow)),
        )

    if "shadow_catcher" in raw:
        legacy_shadow = bool(raw["shadow_catcher"])
        return Outputs(
            png_with_shadow=legacy_shadow,
            png_no_shadow=not legacy_shadow,
            svg_no_shadow=False,
        )

    return fb


OUTPUT_ALIASES = {
    "png_with_shadow": "png_with_shadow",
    "with_shadow":     "png_with_shadow",
    "shadow":          "png_with_shadow",
    "png_no_shadow":   "png_no_shadow",
    "no_shadow":       "png_no_shadow",
    "noshadow":        "png_no_shadow",
    "flat":            "png_no_shadow",
    "svg_no_shadow":   "svg_no_shadow",
    "svg":             "svg_no_shadow",
}


def _parse_outputs_env(value: str) -> dict | None:
    """Parse RENDER_OUTPUTS into a {png_with_shadow, png_no_shadow, svg_no_shadow} dict.

    Accepts a comma- or whitespace-separated list. Listed outputs become True,
    everything else False. ``all`` enables all three; ``none`` disables all three.
    Returns ``None`` if the value is empty / nothing recognisable was found.
    """
    tokens = [t.strip().lower() for t in re.split(r"[,\s]+", value) if t.strip()]
    if not tokens:
        return None

    result = {"png_with_shadow": False, "png_no_shadow": False, "svg_no_shadow": False}

    if any(t == "all" for t in tokens):
        return {k: True for k in result}
    if tokens == ["none"]:
        return result

    unknown: list[str] = []
    matched = False
    for tok in tokens:
        if tok in ("all", "none"):
            continue
        key = OUTPUT_ALIASES.get(tok)
        if key is None:
            unknown.append(tok)
            continue
        result[key] = True
        matched = True

    if unknown:
        log(
            f"[warn] RENDER_OUTPUTS contained unknown token(s): "
            f"{', '.join(unknown)}; valid: "
            f"png_with_shadow|with_shadow|shadow, "
            f"png_no_shadow|no_shadow|noshadow|flat, "
            f"svg_no_shadow|svg, all, none"
        )

    return result if matched else None


def _apply_env_overrides(flat: dict) -> None:
    """Apply CLI/env overrides on top of the loaded settings dict (in place)."""
    out_dir = os.environ.get("RENDER_OUTPUT_DIR")
    if out_dir:
        log(f"[env] RENDER_OUTPUT_DIR override: output_dir={out_dir!r}")
        flat["output_dir"] = out_dir

    outputs_env = os.environ.get("RENDER_OUTPUTS")
    if outputs_env is not None and outputs_env.strip():
        parsed = _parse_outputs_env(outputs_env)
        if parsed is not None:
            enabled = [k for k, v in parsed.items() if v] or ["<none>"]
            log(f"[env] RENDER_OUTPUTS override: {', '.join(enabled)}")
            flat["outputs"] = parsed
            # CLI wins over per-phone outputs / legacy shadow_catcher blocks too.
            scenes = flat.get("scenes")
            if isinstance(scenes, dict):
                for scene_cfg in scenes.values():
                    if isinstance(scene_cfg, dict):
                        scene_cfg.pop("outputs", None)
                        scene_cfg.pop("shadow_catcher", None)


def _candidate_settings_paths(script_dir: str | None):
    paths = []
    env_path = os.environ.get("RENDER_SETTINGS")
    if env_path:
        paths.append(env_path)
    if script_dir:
        paths.append(os.path.join(script_dir, SETTINGS_FILENAME))
    blend_path = bpy.data.filepath
    if blend_path:
        paths.append(os.path.join(os.path.dirname(blend_path), SETTINGS_FILENAME))
    return paths


def _flatten_settings(raw):
    """Collapse nested basic/advanced sections into a flat dict over defaults."""
    user_outputs = "outputs" in raw
    user_shadow = "shadow_catcher" in raw
    legacy_shadow = raw.get("shadow_catcher")
    for section_name in ("basic", "advanced"):
        section = raw.get(section_name)
        if not isinstance(section, dict):
            continue
        if "outputs" in section:
            user_outputs = True
        if "shadow_catcher" in section:
            user_shadow = True
            legacy_shadow = section["shadow_catcher"]

    merged = dict(DEFAULT_SETTINGS)

    if user_shadow and not user_outputs:
        legacy_on = bool(legacy_shadow)
        merged["outputs"] = {
            "png_with_shadow": legacy_on,
            "png_no_shadow":   not legacy_on,
            "svg_no_shadow":   False,
        }

    for key, value in raw.items():
        if key in ("basic", "advanced"):
            continue
        merged[key] = value

    for section_name in ("basic", "advanced"):
        section = raw.get(section_name) or {}
        if not isinstance(section, dict):
            log(
                f"[warn] settings section '{section_name}' is not an object "
                f"(got {type(section).__name__}); ignoring"
            )
            continue
        for key, value in section.items():
            merged[key] = value

    return merged


def _settings_from_flat(flat: dict) -> Settings:
    fit_margin = float(flat["fit_margin"])
    kl_color = flat.get("key_light_color", [1.0, 1.0, 1.0])
    outputs = resolve_outputs(flat)
    angles = tuple(
        Angle(
            name=a["name"],
            tilt_deg=a["tilt_deg"],
            yaw_deg=a["yaw_deg"],
            distance_multiplier=float(a.get("distance_multiplier", 1.0)),
        )
        for a in flat["angles"]
    )
    return Settings(
        output_dir=flat["output_dir"],
        res_x=int(flat["resolution"]["x"]),
        res_y=int(flat["resolution"]["y"]),
        res_percent=int(flat.get("resolution_percentage", 100)),
        samples=int(os.environ.get("RENDER_SAMPLES", flat["samples"])),
        transparent_bg=bool(flat["transparent_background"]),
        device=str(flat.get("device", "GPU")).upper(),
        use_auto_tile=bool(flat.get("use_auto_tile", True)),
        tile_size=int(flat.get("tile_size", 1024)),
        use_persistent_data=bool(flat.get("use_persistent_data", True)),
        fit_margin=fit_margin,
        shadow_fit_margin=float(flat.get("shadow_fit_margin", fit_margin)),
        default_lens_mm=float(flat["default_lens_mm"]),
        supported_exts=tuple(ext.lower() for ext in flat["supported_extensions"]),
        view_transform=str(flat.get("view_transform", "Standard")),
        view_look=str(flat.get("view_look", "None")),
        view_exposure=float(flat.get("view_exposure", 0.0)),
        view_gamma=float(flat.get("view_gamma", 1.0)),
        shadow_catcher_size=float(flat.get("shadow_catcher_size_multiplier", 16.0)),
        shadow_catcher_z=float(flat.get("shadow_catcher_z_offset", 0.0)),
        alpha_threshold=float(flat.get("alpha_threshold", 0.0)),
        key_light=bool(flat.get("key_light", False)),
        key_light_strength=float(flat.get("key_light_strength", 1.5)),
        key_light_elevation_deg=float(flat.get("key_light_elevation_deg", 50.0)),
        key_light_angle_deg=float(flat.get("key_light_angle_deg", 65.0)),
        key_light_shadow_azimuth_deg=float(flat.get("key_light_shadow_azimuth_deg", 315.0)),
        key_light_color=tuple(float(c) for c in (list(kl_color) + [1.0, 1.0, 1.0])[:3]),
        key_light_visible_glossy=bool(flat.get("key_light_visible_glossy", False)),
        key_light_visible_transmission=bool(flat.get("key_light_visible_transmission", False)),
        phone_isolate_indirect=bool(flat.get("phone_isolate_indirect", True)),
        screen_emission_isolate=bool(flat.get("screen_emission_isolate", True)),
        screen_emission_allow_glossy=bool(flat.get("screen_emission_allow_glossy", True)),
        svg_alpha_threshold=float(flat.get("svg_alpha_threshold", 0.5)),
        svg_simplify_tol_px=float(flat.get("svg_outline_simplify_tolerance_px", 0.75)),
        screen_node_id=str(flat.get("screen_node_id", "ScreenTexture")),
        angles=angles,
        outputs=outputs,
        scenes=flat["scenes"],
    )


def _resolve_phones_dir(flat: dict, base_dir: str | None) -> str | None:
    """Resolve where to look for per-phone config files.

    Accepts Blender-style ``//foo`` paths (relative to the loaded .blend),
    absolute paths, and bare names (relative to ``base_dir``).
    """
    raw = flat.get("phones_dir", PHONES_DIRNAME)
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    if raw.startswith("//"):
        try:
            return bpy.path.abspath(raw)
        except (AttributeError, RuntimeError):
            if base_dir is None:
                return None
            return os.path.join(base_dir, raw[2:])
    if os.path.isabs(raw):
        return raw
    if base_dir is None:
        return None
    return os.path.join(base_dir, raw)


def _load_phone_configs(phones_dir: str | None) -> dict[str, dict]:
    """Load every ``*.json`` file in ``phones_dir`` as a per-phone scene config.

    Scene name defaults to the filename stem, but an explicit ``"name"`` key
    inside the file wins. Files are merged in sorted-name order so duplicates
    are deterministic and easy to debug.
    """
    if not phones_dir or not os.path.isdir(phones_dir):
        return {}

    scenes: dict[str, dict] = {}
    for filename in sorted(os.listdir(phones_dir)):
        if not filename.lower().endswith(".json"):
            continue
        full_path = os.path.join(phones_dir, filename)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log(f"[warn] could not parse phone config at {full_path}: {exc}")
            continue
        if not isinstance(cfg, dict):
            log(
                f"[warn] phone config at {full_path} is not an object "
                f"(got {type(cfg).__name__}); skipping"
            )
            continue
        cfg = dict(cfg)
        explicit_name = cfg.pop("name", None)
        scene_name = str(explicit_name) if explicit_name else os.path.splitext(filename)[0]
        if scene_name in scenes:
            log(
                f"[phones] '{scene_name}' from {full_path} overrides an "
                f"earlier phone config with the same name"
            )
        scenes[scene_name] = cfg
        log(f"[phones] loaded '{scene_name}' from {full_path}")
    return scenes


def load_settings(script_dir: str | None = None) -> Settings:
    flat: dict | None = None
    base_dir: str | None = None
    for path in _candidate_settings_paths(script_dir):
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                log(f"[warn] could not parse settings at {path}: {exc}")
                continue
            log(f"Loaded settings from: {path}")
            flat = _flatten_settings(data)
            base_dir = os.path.dirname(path)
            break

    if flat is None:
        log(f"[warn] {SETTINGS_FILENAME} not found - using built-in defaults.")
        flat = dict(DEFAULT_SETTINGS)
        if script_dir:
            base_dir = script_dir
        elif bpy.data.filepath:
            base_dir = os.path.dirname(bpy.data.filepath)

    phones_dir = _resolve_phones_dir(flat, base_dir)
    file_scenes = _load_phone_configs(phones_dir)
    if file_scenes:
        log(
            f"[phones] {len(file_scenes)} phone config(s) loaded from "
            f"'{phones_dir}' (fully replaces any inline 'scenes' block)"
        )
        flat["scenes"] = file_scenes
    elif phones_dir and os.path.isdir(phones_dir):
        log(f"[phones] '{phones_dir}' exists but contains no .json files")

    _apply_env_overrides(flat)

    return _settings_from_flat(flat)
