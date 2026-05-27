import bpy

from render_lib.logging_utils import log


def setup_gpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dev_type in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            break
        except TypeError:
            continue
    enabled = []
    for device in prefs.devices:
        device.use = (device.type != 'CPU')
        if device.use:
            enabled.append(f"{device.type}: {device.name}")
    log(f"Cycles compute_device_type = {prefs.compute_device_type}")
    for line in enabled:
        log(f"  - {line}")
    if not enabled:
        log("  (no GPU detected - falling back to CPU)")
