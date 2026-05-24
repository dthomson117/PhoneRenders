# AppStoreImages

Batch-render beautiful 3D phone mockups for the App Store / Play Store from
flat screenshots, using Blender + a single Python script.

Drop your screenshots into `screenshots/iOS/` or `screenshots/Android/`, run
`render.bat` (or invoke Blender directly), and out pops a folder full of
`{screen}__{angle}.png` images - one per camera angle per screenshot, per
platform - rendered with Cycles and a transparent background so they composite
cleanly onto marketing backgrounds.

## Example output

The repo ships with one default screenshot per platform and the six rendered
angles produced for each:

| Angle | iOS | Android |
| --- | --- | --- |
| `front`                  | `renders/iOS/default_ios__front.png`                  | `renders/Android/default_android__front.png` |
| `threequarter_left`      | `renders/iOS/default_ios__threequarter_left.png`      | `renders/Android/default_android__threequarter_left.png` |
| `threequarter_right`     | `renders/iOS/default_ios__threequarter_right.png`     | `renders/Android/default_android__threequarter_right.png` |
| `threequarter_left_top`  | `renders/iOS/default_ios__threequarter_left_top.png`  | `renders/Android/default_android__threequarter_left_top.png` |
| `threequarter_right_top` | `renders/iOS/default_ios__threequarter_right_top.png` | `renders/Android/default_android__threequarter_right_top.png` |
| `hero_top`               | `renders/iOS/default_ios__hero_top.png`               | `renders/Android/default_android__hero_top.png` |

Default phones in the shipped `.blend`:

- **iOS** - iPhone 17 Pro Max
- **Android** - Google Pixel 9 Pro XL

Both are rendered at **2160 × 3840** (4K portrait) with a transparent background.

## Requirements

- **Blender 4.2+** (tested on 4.2 LTS and newer). Older versions may work, but
  the script uses GPU-side OpenImageDenoise and the light tree which need 4.2+.
- **Git LFS** - the `.blend` scene and `.exr` HDRI are stored via LFS, so a
  plain `git clone` without LFS will leave you with pointer files instead of
  the real assets.
- A discrete GPU is strongly recommended (OptiX / CUDA / HIP / oneAPI / Metal
  all auto-detected), but the script will fall back to CPU rendering.

## Quick start

```bash
# 1. Clone (Git LFS pulls the .blend + .exr automatically)
git lfs install
git clone https://github.com/<your-username>/AppStoreImages.git
cd AppStoreImages

# 2. Drop screenshots into the right folder.
#    Anything .png / .jpg / .jpeg / .webp works.
#    The filename (minus extension) becomes the output prefix.
cp ~/my-app/ios-screens/*.png    screenshots/iOS/
cp ~/my-app/android-screens/*.png screenshots/Android/

# 3. Render. On Windows just double-click render.bat.
#    On macOS / Linux, call Blender yourself:
blender --background phones.blend --python render_screens.py
```

Renders land in `renders/iOS/` and `renders/Android/`, one PNG per
`{screenshot}__{angle}` combination.

### Windows convenience launcher

`render.bat` auto-discovers `blender.exe` from (in order):

1. `BLENDER_EXE` environment variable
2. `PATH`
3. Common install locations (`Program Files\Blender Foundation`, Steam, Winget)
4. The `HKLM\Software\BlenderFoundation` registry key

If none of those work, set the env var:

```bat
set BLENDER_EXE=C:\path\to\blender.exe
render.bat
```

## How it works

`render_screens.py` runs inside Blender (it imports `bpy`). For each scene
defined in `render_settings.json`:

1. Finds the phone object and locates its **screen Image Texture node** -
   either by the explicit `screen_node_id` (matched against node name *or*
   label), or by falling back to the first image node in the screen material.
2. Computes a bounding box around the phone and builds **one camera per
   entry in `angles`**. Each angle is described in degrees - `tilt_deg` away
   from the screen normal, `yaw_deg` around the phone - and gets framed to
   the phone using a `fit_margin` so every render is composed identically.
3. Iterates over every image in the platform's `screens_dir`, swaps it into
   the screen texture node, and renders the full set of cameras.

A few quality details worth knowing about:

- **Cycles + OpenImageDenoise (GPU)** is preferred over OptiX denoising -
  OptiX tends to hallucinate asterisk-shaped artefacts on tiny dark features
  like speaker grilles.
- Adaptive sampling is tuned to keep fine detail crisp
  (`threshold=0.01`, `min_samples=64`).
- Caustics are off and `blur_glossy=1.0` to suppress fireflies on the
  chamfered phone edges and glass.
- Missing external image references in the shipped `.blend` are silently
  swapped out for a 1×1 transparent fallback, so an out-of-date texture
  path can't break your render.

## Configuration: `render_settings.json`

Every tweakable parameter lives in `render_settings.json`. The file is
loaded from one of these locations (first match wins):

1. The path in the `RENDER_SETTINGS` environment variable
2. The folder containing `render_screens.py`
3. The folder containing the loaded `.blend` file

Top-level keys:

| Key | Type | What it does |
| --- | --- | --- |
| `output_dir` | path | Where renders are written. `//` is Blender-relative. |
| `resolution.x` / `resolution.y` | int | Render size in pixels. |
| `resolution_percentage` | int | Scales the render (50 = half-res preview). |
| `samples` | int | Cycles samples (override with `RENDER_SAMPLES` env var). |
| `transparent_background` | bool | Film alpha for compositing. |
| `device` | `"GPU"` / `"CPU"` | Cycles render device. |
| `use_auto_tile` / `tile_size` | bool / int | Cycles tiling. |
| `use_persistent_data` | bool | Reuses BVH between frames - faster. |
| `fit_margin` | float | Extra room around the phone when framing (1.08 = 8% padding). |
| `default_lens_mm` | float | Starting focal length before auto-fit. |
| `supported_extensions` | string[] | Filename extensions treated as screenshots. |
| `angles` | array | Camera angles, see below. |
| `scenes` | object | Per-platform setup, see below. |

### `angles`

Each angle is a small object:

```json
{ "name": "threequarter_left", "tilt_deg": 30, "yaw_deg": 215, "distance_multiplier": 1.0 }
```

- `name` becomes the filename suffix (`{screen}__{name}.png`).
- `tilt_deg` is the angle between the camera and the screen normal
  (0 = straight on, 90 = edge-on).
- `yaw_deg` is the rotation around the phone (0 = top, 90 = right edge,
  180 = bottom, 270 = left edge).
- `distance_multiplier` scales the auto-computed camera distance.

Add, remove, or reorder angles freely - the script just iterates the list.

### `scenes`

```json
"iOS": {
  "phone_object":    "iPhone 17 ProMax",
  "screen_material": "17ProMax_Screen",
  "screens_dir":     "//screenshots/iOS/",
  "screen_node_id":  "ScreenTextureiOS"
}
```

- `phone_object` - the Blender object name (in the scene's outliner).
- `screen_material` - the material whose image-texture node holds the screen
  content.
- `screens_dir` - folder of screenshots to iterate (`//` is .blend-relative).
- `screen_node_id` - **recommended**. Set this to a unique name/label on the
  screen Image Texture node so the script never has to guess which image
  node is the screen. If you skip it, the script falls back to "the first
  image node in the screen material".

Each scene in `scenes` must correspond to a Blender scene of the same name
inside `phones.blend`. You can rename / duplicate scenes inside Blender
to add e.g. an iPad or a second Android device - just mirror the rename
in `render_settings.json`.

## Customising the .blend

The shipped scenes assume the **phone screen faces +Z, with the UI top at
-Y and the UI right at +X**. If you swap in a different phone model, rotate
it in object mode so the local axes match - the camera math relies on it.

For each new phone:

1. Drop the model into the right Blender scene (`iOS`, `Android`, or a new
   scene you define in `render_settings.json`).
2. Make sure the screen face has its own material.
3. Add an **Image Texture** node to that material, connect its `Color`
   output to both `Base Color` and `Emission Color` on the BSDF, and give
   the node a unique **name** *or* **label** (e.g. `ScreenTextureiOS`).
4. Put that same string into `scenes.<name>.screen_node_id`.

## Environment-variable overrides

| Variable | Effect |
| --- | --- |
| `RENDER_SETTINGS` | Path to an alternative settings JSON. |
| `RENDER_SAMPLES` | Overrides `samples` for a single run (handy for previews). |
| `BLENDER_EXE` *(Windows)* | Skip `render.bat`'s auto-discovery. |

Example - low-sample preview pass with a custom settings file:

```bash
RENDER_SETTINGS=./render_settings.preview.json \
RENDER_SAMPLES=64 \
blender --background phones.blend --python render_screens.py
```

## Repository layout

```
.
├── phones.blend          # Phone models + scenes (Git LFS)
├── render_screens.py     # The Blender-side rendering script
├── render_settings.json  # All tweakable parameters
├── render.bat            # Windows launcher with Blender auto-discovery
├── hdr/                  # Studio HDRI used in the .blend (Git LFS)
├── screenshots/
│   ├── iOS/              # Drop your iOS screens here
│   └── Android/          # Drop your Android screens here
└── renders/
    ├── iOS/              # Renders land here
    └── Android/
```

## Contributing

PRs welcome - especially for new phone models, additional camera angles, or
backgrounds / studio setups. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## License

[MIT](./LICENSE) © David Thomson
