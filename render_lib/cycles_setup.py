from render_lib._compat import set_attr_safe
from render_lib.logging_utils import log
from render_lib.settings import Settings


def configure_render_engine(scene, settings: Settings):
    """Apply resolution, colour management, and engine-specific sampling."""
    scene.render.resolution_x = settings.res_x
    scene.render.resolution_y = settings.res_y
    scene.render.resolution_percentage = settings.res_percent
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = settings.transparent_bg
    scene.render.use_persistent_data = settings.use_persistent_data

    if not set_attr_safe(scene.view_settings, 'view_transform', settings.view_transform):
        log(f"[warn] could not set view_transform={settings.view_transform!r}")
    if not set_attr_safe(scene.view_settings, 'look', settings.view_look):
        log(f"[warn] could not set look={settings.view_look!r}")
    try:
        scene.view_settings.exposure = settings.view_exposure
        scene.view_settings.gamma    = settings.view_gamma
    except AttributeError:
        pass

    if scene.render.engine == 'CYCLES':
        _configure_cycles(scene, settings)
    elif scene.render.engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        scene.eevee.taa_render_samples = settings.samples


def _configure_cycles(scene, settings: Settings):
    scene.cycles.samples = settings.samples
    scene.cycles.device = settings.device
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.01
    scene.cycles.adaptive_min_samples = 16
    scene.cycles.use_denoising = True
    scene.cycles.sample_clamp_indirect = 0.0

    scene.cycles.pixel_filter_type = 'BLACKMAN_HARRIS'
    scene.cycles.filter_width = 1.5

    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 8
    scene.cycles.volume_bounces = 0
    scene.cycles.transparent_max_bounces = 8

    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.cycles.blur_glossy = 1.0

    set_attr_safe(scene.cycles, 'use_light_tree', True)
    set_attr_safe(scene.cycles, 'use_auto_tile', settings.use_auto_tile)
    set_attr_safe(scene.cycles, 'tile_size', settings.tile_size)

    denoiser_set = False
    for denoiser_name in ('OPENIMAGEDENOISE', 'OPTIX'):
        try:
            scene.cycles.denoiser = denoiser_name
            denoiser_set = True
            break
        except TypeError:
            continue
    if denoiser_set:
        set_attr_safe(scene.cycles, 'denoising_input_passes', 'RGB_ALBEDO_NORMAL')
        set_attr_safe(scene.cycles, 'denoising_prefilter', 'ACCURATE')
        set_attr_safe(scene.cycles, 'denoising_quality', 'HIGH')
        set_attr_safe(scene.cycles, 'denoising_use_gpu', True)

    set_attr_safe(scene.render, 'compositor_device', 'GPU')
