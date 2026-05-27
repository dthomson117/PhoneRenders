import bpy

from render_lib.logging_utils import log
from render_lib.settings import SceneSettings


def log_render_config(scene, resolved: SceneSettings, shadow_catcher_on=None, pass_label=None):
    """Print a prominent banner of what the next render(s) will actually use."""
    engine = scene.render.engine
    res_x = int(scene.render.resolution_x * scene.render.resolution_percentage / 100)
    res_y = int(scene.render.resolution_y * scene.render.resolution_percentage / 100)

    log("-" * 60)
    if pass_label:
        log(f"Pass:             {pass_label}")
    log(f"Render engine:    {engine}")
    log(f"Resolution:       {res_x} x {res_y}")
    log(f"Film transparent: {scene.render.film_transparent}")
    log(
        f"Color management: view={scene.view_settings.view_transform} "
        f"look={scene.view_settings.look or 'None'} "
        f"exposure={scene.view_settings.exposure:+.2f} "
        f"gamma={scene.view_settings.gamma:.2f} "
        f"display={scene.display_settings.display_device}"
    )
    fit_m       = resolved.fit_margin
    sfit_m      = resolved.shadow_fit_margin
    sc_size     = resolved.shadow_catcher_size
    sc_z        = resolved.shadow_catcher_z
    alpha_th    = resolved.alpha_threshold
    kl_on       = resolved.key_light
    kl_str      = resolved.key_light_strength
    kl_elev     = resolved.key_light_elevation_deg
    kl_ang      = resolved.key_light_angle_deg
    kl_az       = resolved.key_light_shadow_azimuth_deg

    if shadow_catcher_on is None:
        log(
            f"Fit margin:       fit_margin={fit_m:.3f}, "
            f"shadow_fit_margin={sfit_m:.3f} (active value depends on pass)"
        )
        log(
            "Shadow catcher:   depends on pass "
            f"(size_x={sc_size:.1f}, z_offset={sc_z:+.4f})"
        )
    else:
        active_fit = sfit_m if shadow_catcher_on else fit_m
        log(
            f"Fit margin:       {active_fit:.3f} "
            f"(fit_margin={fit_m:.3f}, shadow_fit_margin={sfit_m:.3f}, "
            f"shadow_catcher={'on' if shadow_catcher_on else 'off'})"
        )
        log(
            f"Shadow catcher:   {'on' if shadow_catcher_on else 'off'} "
            f"(size_x={sc_size:.1f}, z_offset={sc_z:+.4f})"
        )
    log(
        f"Alpha threshold:  "
        f"{('off' if alpha_th <= 0 else f'{alpha_th:.3f}')}"
    )
    log(
        f"Key light:        {'on' if kl_on else 'off'} "
        f"(strength={kl_str:.2f}W/m², elev={kl_elev:.1f}°, "
        f"angle={kl_ang:.1f}°, shadow_az={kl_az:.0f}°)"
    )

    if engine == 'CYCLES':
        prefs = bpy.context.preferences.addons['cycles'].preferences
        active_gpus = [
            f"{d.type}: {d.name}" for d in prefs.devices
            if d.use and d.type != 'CPU'
        ]
        cdt = prefs.compute_device_type
        device_label = scene.cycles.device
        if device_label == 'GPU' and active_gpus:
            device_label = f"GPU ({cdt})"
        elif device_label == 'GPU':
            device_label = f"GPU ({cdt}) - NO ACTIVE DEVICES, will fall back to CPU"
        log(f"Device:           {device_label}")
        for g in active_gpus:
            log(f"  - {g}")
        log(f"Samples (max):    {scene.cycles.samples}")
        log(
            f"Adaptive:         threshold={scene.cycles.adaptive_threshold} "
            f"min_samples={scene.cycles.adaptive_min_samples}"
        )
        if scene.cycles.use_denoising:
            denoiser = getattr(scene.cycles, 'denoiser', '?')
            quality = getattr(scene.cycles, 'denoising_quality', '?')
            prefilter = getattr(scene.cycles, 'denoising_prefilter', '?')
            passes = getattr(scene.cycles, 'denoising_input_passes', '?')
            use_gpu = getattr(scene.cycles, 'denoising_use_gpu', False)
            log(
                f"Denoiser:         {denoiser} "
                f"(quality={quality}, prefilter={prefilter}, "
                f"passes={passes}, gpu={use_gpu})"
            )
        else:
            log("Denoiser:         OFF")
        try:
            log(
                f"Tiling:           auto_tile={scene.cycles.use_auto_tile} "
                f"tile_size={scene.cycles.tile_size}"
            )
        except AttributeError:
            pass
        log(f"Persistent data:  {scene.render.use_persistent_data}")
    elif engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        log(f"Samples:          {scene.eevee.taa_render_samples}")
    log("-" * 60)
