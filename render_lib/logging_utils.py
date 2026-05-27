import sys


def log(message=""):
    """Write to stderr with an immediate flush.

    Blender buffers Python stdout in --background mode, so important script
    messages (settings loaded, render config banner, "Rendering ..." lines)
    can sit hidden until the run is nearly over. Routing them through stderr
    with flush=True puts them in the same stream as Blender's own
    warnings/errors and makes them appear in real time."""
    print(message, file=sys.stderr, flush=True)
