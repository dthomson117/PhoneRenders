import os

from render_lib.gpu import setup_gpu
from render_lib.logging_utils import log
from render_lib.orchestrator import render_scene
from render_lib.settings import Settings, load_settings


def _selected_scene_configs(settings: Settings):
    """Filter scenes via the RENDER_PLATFORMS env var (case-insensitive, comma-separated)."""
    requested = os.environ.get("RENDER_PLATFORMS", "").strip()
    if not requested:
        return settings.scenes

    wanted = {name.strip().lower() for name in requested.split(",") if name.strip()}
    selected = {
        scene_name: cfg
        for scene_name, cfg in settings.scenes.items()
        if scene_name.lower() in wanted
    }

    if not selected:
        raise RuntimeError(
            f"RENDER_PLATFORMS={requested!r} matched no scenes. "
            f"Valid options: {', '.join(settings.scenes)}"
        )
    return selected


def run(script_dir=None):
    if script_dir is None:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    settings = load_settings(script_dir)
    log(
        "[outputs] "
        f"png_with_shadow={settings.outputs.png_with_shadow}, "
        f"png_no_shadow={settings.outputs.png_no_shadow}, "
        f"svg_no_shadow={settings.outputs.svg_no_shadow}"
    )

    setup_gpu()

    scenes_to_render = _selected_scene_configs(settings)
    log(f"Rendering platforms: {', '.join(scenes_to_render)}")

    for scene_name, cfg in scenes_to_render.items():
        try:
            render_scene(scene_name, cfg, settings)
        except Exception as e:
            log(f"[error] scene '{scene_name}' failed: {e}")

    log("\nAll scenes done.")
