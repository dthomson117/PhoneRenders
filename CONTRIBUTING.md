# Contributing

Thanks for your interest! This is a small project, so the process is
deliberately lightweight.

## Reporting bugs / asking questions

Open an issue with:

- Blender version (`blender --version`)
- OS + GPU / render device
- A copy of `render_settings.json` if you've changed anything
- The full Blender console output (it's usually pretty descriptive)

## Pull requests

1. Fork the repo and create a topic branch.
2. Keep changes focused - one PR per logical change.
3. Test by rendering at least one screenshot per platform locally:
   `blender --background phones.blend --python render_screens.py`
4. If you change `render_screens.py` defaults, please update the matching
   keys in `render_settings.json` and the README's settings table.
5. Don't commit large output dumps under `renders/`. The `.gitignore`
   only tracks the `default_ios__*` / `default_android__*` sample set.

## Adding a new phone model

1. Add the model to a new (or existing) scene in `phones.blend`.
2. Make sure the screen face has a material with an Image Texture node.
   Name or label that node uniquely (e.g. `ScreenTextureiPadMini`).
3. Register the scene in `render_settings.json` under `scenes`:

   ```json
   "iPadMini": {
     "phone_object":    "iPad mini",
     "screen_material": "iPadMini_Screen",
     "screens_dir":     "//screenshots/iPadMini/",
     "screen_node_id":  "ScreenTextureiPadMini"
   }
   ```

4. Add a matching `screenshots/iPadMini/` folder with at least one default
   screenshot so the README's example output table can be updated.

## Large binary assets

`.blend`, `.exr`, and `.hdr` files are tracked via Git LFS - see
`.gitattributes`. Make sure `git lfs install` has been run in your clone
before committing new ones.
