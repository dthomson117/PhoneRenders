import base64

import bpy

from render_lib.logging_utils import log


def _douglas_peucker(points, eps):
    """Iterative Douglas-Peucker polyline simplification."""
    n = len(points)
    if n < 3 or eps <= 0:
        return list(points)

    keep = [False] * n
    keep[0] = True
    keep[-1] = True
    stack = [(0, n - 1)]
    eps2 = eps * eps

    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        ax, ay = points[i0]
        bx, by = points[i1]
        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy

        max_d2 = 0.0
        max_i = -1
        for i in range(i0 + 1, i1):
            px, py = points[i]
            if seg_len_sq <= 0.0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                cross = dx * (ay - py) - dy * (ax - px)
                d2 = (cross * cross) / seg_len_sq
            if d2 > max_d2:
                max_d2 = d2
                max_i = i

        if max_i > 0 and max_d2 > eps2:
            keep[max_i] = True
            stack.append((i0, max_i))
            stack.append((max_i, i1))

    return [points[i] for i in range(n) if keep[i]]


def _trace_phone_outline(png_path, alpha_threshold, simplify_tol_px):
    """Read ``png_path`` and return ``(polygon, image_size, bbox)``."""
    import numpy as np

    img = bpy.data.images.load(png_path, check_existing=False)
    try:
        w, h = img.size
        if w <= 0 or h <= 0:
            raise RuntimeError(f"PNG has zero size: {png_path}")
        flat = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(flat)
        pixels = flat.reshape((h, w, 4))[::-1].copy()
    finally:
        bpy.data.images.remove(img)

    alpha = pixels[:, :, 3]
    mask = alpha > float(alpha_threshold)

    row_has_content = mask.any(axis=1)
    if not row_has_content.any():
        raise RuntimeError(
            f"no opaque pixels above alpha threshold "
            f"{alpha_threshold:.3f} in {png_path}"
        )

    rows = np.where(row_has_content)[0]
    left_idx_arr  = mask.argmax(axis=1)
    right_idx_arr = w - 1 - mask[:, ::-1].argmax(axis=1)

    lefts  = [(float(int(left_idx_arr[y])),         float(int(y)) + 0.5) for y in rows]
    rights = [(float(int(right_idx_arr[y])) + 1.0,  float(int(y)) + 0.5) for y in rows]

    eps = max(0.0, float(simplify_tol_px))
    left_simp  = _douglas_peucker(lefts, eps)
    right_simp = _douglas_peucker(rights, eps)

    polygon = left_simp + right_simp[::-1]

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    return polygon, (w, h), bbox


def generate_svg_from_png(png_path, svg_path,
                          alpha_threshold=0.5,
                          simplify_tol_px=0.75):
    """Trace the alpha silhouette of ``png_path`` and write an SVG at ``svg_path``."""
    polygon, (w, h), bbox = _trace_phone_outline(
        png_path, alpha_threshold, simplify_tol_px
    )
    min_x, min_y, max_x, max_y = bbox
    bbox_w = max_x - min_x
    bbox_h = max_y - min_y

    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    pts = " ".join(
        f"{(x - min_x):.2f},{(y - min_y):.2f}" for x, y in polygon
    )

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {bbox_w:.2f} {bbox_h:.2f}" '
        f'width="{bbox_w:.2f}" height="{bbox_h:.2f}">\n'
        '  <defs>\n'
        '    <clipPath id="phone-outline" clipPathUnits="userSpaceOnUse">\n'
        f'      <polygon points="{pts}"/>\n'
        '    </clipPath>\n'
        '  </defs>\n'
        f'  <image x="{(-min_x):.2f}" y="{(-min_y):.2f}" '
        f'width="{w}" height="{h}" preserveAspectRatio="none" '
        'clip-path="url(#phone-outline)" '
        f'xlink:href="data:image/png;base64,{b64}"/>\n'
        '</svg>\n'
    )

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    log(
        f"[svg] wrote {svg_path} "
        f"({bbox_w:.0f}x{bbox_h:.0f}, {len(polygon)} polygon vertices)"
    )
