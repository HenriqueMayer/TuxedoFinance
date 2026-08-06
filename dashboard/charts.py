"""SVG geometry for the report charts (FR16).

The project is deliberately zero-JS, so the charts are plain server-rendered
`<svg>` — no charting library, no `<canvas>`, no client-side data. These
helpers do the pixel arithmetic the Django Template Language cannot express
and hand the template ready-to-render coordinates.

Nothing here knows about money or the design system: callers pass plain
floats and semantic tone names, and the template maps tones to Tailwind
classes. That keeps `docs/frontend.md`'s design tokens in the template layer
where every other color decision already lives.

All coordinates are in the SVG's own viewBox units; the template scales the
whole drawing with `class="w-full"`, so the numbers below are a fixed
aspect-ratio canvas, not device pixels.
"""

WIDTH = 720
HEIGHT = 240

# Plot area. The left inset leaves room for the value axis, the bottom inset
# for the month labels underneath the baseline.
PLOT_LEFT = 64
PLOT_RIGHT = 708
PLOT_TOP = 16
PLOT_BOTTOM = 196
LABEL_Y = 220

# Horizontal reference lines (plus the top one) behind the data.
GRID_LINES = 4

# Headroom above/below the data so the line never touches the frame.
PADDING_RATIO = 0.08

# Share of a month's horizontal slot the grouped bars actually occupy; the
# remainder is the gutter that separates one month from the next.
GROUP_WIDTH_RATIO = 0.68

# Gap between the top of a bar and a caption drawn above it. `_bounds` keeps
# `PADDING_RATIO` of headroom over the tallest bar, so the caption always has
# room inside the canvas even when a bar nearly fills the plot.
VALUE_LABEL_OFFSET = 6

# Rough width of one character at the 11px axis font, used to say how many
# fit under a slot. Approximate on purpose — an exact answer needs font
# metrics the server does not have, and this only decides where a label is
# truncated. `LABEL_MAX_CHARS` stops a chart with one or two bars from
# allowing a label wider than the canvas.
LABEL_CHAR_WIDTH = 5.5
LABEL_MAX_CHARS = 28

import math

# Donut canvas — square so the ring sits centered, large enough that the
# share labels around it stay legible. Like the other canvases it is a
# fixed viewBox the template scales with `class="w-full"`.
DONUT_SIZE = 320
DONUT_PADDING = 28
DONUT_STROKE = 38

# Sparkline canvas — small enough to fit inside a currency card on the
# Investments list page, large enough that 12 monthly points stay
# individually visible. Each currency gets its own y-axis scale, so a
# BRL balance of 50000 and a USD balance of 100 are both readable
# inside their own sparkline.
SPARK_WIDTH = 120
SPARK_HEIGHT = 40
# Pixels of inset on every side so the line never touches the edge of
# the card. The y-axis is implicit (no labels), so a few pixels of
# headroom reads better than letting the line clip the box.
SPARK_PADDING = 4


def _bounds(values):
    """Value range to plot, always including zero so the axis is honest.

    A chart whose y-axis starts at the smallest value exaggerates every
    wobble into a cliff; anchoring to zero keeps the slope truthful.
    """
    lowest = min([*values, 0.0])
    highest = max([*values, 0.0])

    if lowest == highest:
        # Every value is zero (a brand-new account) — pick an arbitrary
        # symmetric range so the baseline lands in the middle and the flat
        # line is visible rather than dividing by zero below.
        return -1.0, 1.0

    padding = (highest - lowest) * PADDING_RATIO
    return lowest - padding, highest + padding


def _y(value, bounds):
    """Map a value onto its vertical pixel position inside the plot area."""
    lowest, highest = bounds
    ratio = (value - lowest) / (highest - lowest)
    return round(PLOT_BOTTOM - ratio * (PLOT_BOTTOM - PLOT_TOP), 2)


def _slot_width(count):
    """Horizontal space allotted to one month."""
    return (PLOT_RIGHT - PLOT_LEFT) / count


def _slot_center(index, count):
    """Center of month `index`'s slot — where its point/bar group sits."""
    return round(PLOT_LEFT + _slot_width(count) * (index + 0.5), 2)


def _grid(bounds):
    """Evenly spaced reference lines, each with its raw (unformatted) value."""
    lowest, highest = bounds
    step = (highest - lowest) / GRID_LINES
    return [
        {'y': _y(lowest + step * line, bounds), 'value': lowest + step * line}
        for line in range(GRID_LINES + 1)
    ]


def _frame(bounds):
    """Geometry every chart shares: canvas size, grid, and the zero line."""
    return {
        'width': WIDTH,
        'height': HEIGHT,
        'plot_left': PLOT_LEFT,
        'plot_right': PLOT_RIGHT,
        'plot_top': PLOT_TOP,
        'plot_bottom': PLOT_BOTTOM,
        'label_y': LABEL_Y,
        'grid': _grid(bounds),
        'zero_y': _y(0.0, bounds),
    }


def build_line_chart(labels, values):
    """Area-and-line geometry for one series (the balance evolution).

    `labels` are passed through untouched — the template formats them, so
    they can be `date` objects and stay locale-aware.
    """
    bounds = _bounds(values)
    count = len(values)

    points = [
        {
            'label': label,
            'value': value,
            'x': _slot_center(index, count),
            'y': _y(value, bounds),
        }
        for index, (label, value) in enumerate(zip(labels, values))
    ]

    line = ' '.join(f'{point["x"]},{point["y"]}' for point in points)
    # The filled area is the same path closed along the baseline, so it reads
    # as volume under the curve rather than a second, thicker line.
    area = (
        f'{points[0]["x"]},{PLOT_BOTTOM} {line} {points[-1]["x"]},{PLOT_BOTTOM}'
        if points
        else ''
    )

    return {**_frame(bounds), 'points': points, 'line': line, 'area': area}


def build_bar_chart(labels, series):
    """Grouped-bar geometry: one group per label, one bar per series entry.

    `series` is a list of `{'name': ..., 'tone': ..., 'values': [...]}`. All
    values are totals, so they are never negative and every bar grows upward
    from the baseline.

    Callers must pass at least one label: with none there is no slot to divide
    the plot into, and the caller has an empty state to render anyway.
    """
    values = [value for entry in series for value in entry['values']]
    bounds = (0.0, max([*values, 0.0]) * (1 + PADDING_RATIO) or 1.0)
    count = len(labels)

    group_width = _slot_width(count) * GROUP_WIDTH_RATIO
    bar_width = group_width / len(series) if series else group_width

    groups = []
    for index, label in enumerate(labels):
        center = _slot_center(index, count)
        bars = []
        for position, entry in enumerate(series):
            value = entry['values'][index]
            y = _y(value, bounds)
            bars.append(
                {
                    'name': entry['name'],
                    'tone': entry['tone'],
                    'value': value,
                    'x': round(center - group_width / 2 + bar_width * position, 2),
                    'y': y,
                    # Baseline for a caption sitting just above the bar; only
                    # single-series charts have the room to use it.
                    'value_y': round(y - VALUE_LABEL_OFFSET, 2),
                    # Leave a hairline gutter between bars in a group.
                    'width': round(bar_width * 0.86, 2),
                    'height': round(PLOT_BOTTOM - y, 2),
                }
            )
        groups.append({'label': label, 'center': center, 'bars': bars})

    return {
        **_frame(bounds),
        'groups': groups,
        'legend': [{'name': e['name'], 'tone': e['tone']} for e in series],
        # How long a label may be before it starts colliding with its
        # neighbour. Charts labelled by month ignore it ('Jul' always fits);
        # the payment-method chart truncates to it, so names stay whole while
        # there are few bars and shorten as bars are added.
        'label_chars': min(LABEL_MAX_CHARS, int(_slot_width(count) / LABEL_CHAR_WIDTH)),
    }


def build_sparkline(labels, values):
    """Mini line-chart geometry for the per-currency sparklines.

    The Investments list page renders one sparkline per supported
    currency in a small-multiples grid, because plotting every currency
    on a single axis collapses the smaller balances (e.g. a USD balance
    of 100 against a BRL balance of 50 000) into a flat line at the
    bottom. Each sparkline gets its own `_bounds`, so a BRL 50 000 and
    a USD 100 each draw a meaningful line on their own scale.

    Returns a dict shaped like a slimmed-down `build_line_chart`:

      - `width`, `height`: SVG viewBox, fixed to `SPARK_WIDTH`/`SPARK_HEIGHT`.
      - `points`: list of `{label, value, x, y}` dicts.
      - `line`: a polyline `points` string ready to drop into a
        `<polyline points="…">` attribute.
      - `last`: the same shape as one element of `points`, the
        right-most one — the template draws a small filled circle
        there as the "now" marker.

    No grid, no axis labels, no area fill — the page already shows
    the current balance in big type next to each sparkline, so the
    chart itself only needs to communicate the *shape* of the trend.
    Tooltips are still native `<title>` elements the template can
    attach to the last-point circle.
    """
    if not values:
        return {
            'width': SPARK_WIDTH,
            'height': SPARK_HEIGHT,
            'points': [],
            'line': '',
            'last': None,
        }

    # Reuse the same bounds policy as the main line chart: always
    # include zero so the line starts at the right vertical position
    # for a brand-new account (cumulative balance of 0). The padding
    # gives the line room above/below the extreme values.
    bounds = _bounds(values)
    count = len(values)
    inner_width = SPARK_WIDTH - 2 * SPARK_PADDING
    inner_height = SPARK_HEIGHT - 2 * SPARK_PADDING
    slot_width = inner_width / count

    points = []
    for index, (label, value) in enumerate(zip(labels, values)):
        lowest, highest = bounds
        ratio = (value - lowest) / (highest - lowest)
        y = round(SPARK_PADDING + inner_height - ratio * inner_height, 2)
        x = round(SPARK_PADDING + slot_width * (index + 0.5), 2)
        points.append({'label': label, 'value': value, 'x': x, 'y': y})

    line = ' '.join(f'{p["x"]},{p["y"]}' for p in points)
    return {
        'width': SPARK_WIDTH,
        'height': SPARK_HEIGHT,
        'points': points,
        'line': line,
        'last': points[-1],
    }


def build_donut_chart(slices):
    """Donut (ring) geometry for a proportion chart (FR16).

    `slices` is a list of `{'name': ..., 'tone': ..., 'value': ...,
    'share': ...}` ordered the way the caller wants the ring drawn —
    slices are placed clockwise starting at 12 o'clock, and the order is
    kept fixed so the ring does not reshuffle when the month changes.

    Returns a dict with the canvas size, ring center/radii, and a
    `segments` list where each entry carries a ready-to-render SVG arc
    `<path d="...">`. The last slice absorbs any rounding remainder so
    the ring closes exactly at 360° rather than leaving a hairline gap.
    """
    size = DONUT_SIZE
    padding = DONUT_PADDING
    stroke = DONUT_STROKE
    cx = size / 2
    cy = size / 2
    radius = (size - 2 * padding - stroke) / 2

    total = sum(slice['value'] for slice in slices)
    if not total:
        return {
            'width': size,
            'height': size,
            'cx': cx,
            'cy': cy,
            'radius': radius,
            'stroke': stroke,
            'total': 0.0,
            'segments': [],
        }

    segments = []
    start_angle = -90.0  # 12 o'clock, in degrees
    for index, slice in enumerate(slices):
        # Let the final slice sweep whatever is left so the ring closes
        # exactly at 360°, absorbing the rounding error from the others.
        # Ring starts at -90° (12 o'clock) and must close at 270°, so the
        # remaining sweep is `270 - start_angle` (NOT `360 + 90 - ...`).
        remaining = 270.0 - start_angle
        if index == len(slices) - 1:
            sweep = remaining
        else:
            sweep = slice['share'] / 100.0 * 360.0

        end_angle = start_angle + sweep

        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)

        x1 = round(cx + radius * math.cos(start_rad), 2)
        y1 = round(cy + radius * math.sin(start_rad), 2)
        x2 = round(cx + radius * math.cos(end_rad), 2)
        y2 = round(cy + radius * math.sin(end_rad), 2)

        # Outer arc, then line in to the inner radius, inner arc back,
        # then close — a donut wedge. `sweep_flag` is 1 for the outer
        # arc (clockwise) and 0 for the inner (counter-clockwise).
        inner_radius = radius - stroke
        ix1 = round(cx + inner_radius * math.cos(start_rad), 2)
        iy1 = round(cy + inner_radius * math.sin(start_rad), 2)
        ix2 = round(cx + inner_radius * math.cos(end_rad), 2)
        iy2 = round(cy + inner_radius * math.sin(end_rad), 2)

        # A full 360° sweep (a single slice covering the whole ring)
        # collapses to start == end, and the SVG `A` command needs two
        # distinct points to draw anything — otherwise the path renders
        # nothing and the slice just vanishes. Split it into two
        # semicircle arcs, which together still cover 360° but each has
        # distinct endpoints.
        if sweep >= 359.999:
            mid_angle = start_angle + sweep / 2.0
            mid_rad = math.radians(mid_angle)
            mx = round(cx + radius * math.cos(mid_rad), 2)
            my = round(cy + radius * math.sin(mid_rad), 2)
            imx = round(cx + inner_radius * math.cos(mid_rad), 2)
            imy = round(cy + inner_radius * math.sin(mid_rad), 2)
            path = (
                f'M {x1},{y1} '
                f'A {radius},{radius} 0 0 1 {mx},{my} '
                f'A {radius},{radius} 0 0 1 {x1},{y1} '
                f'L {ix1},{iy1} '
                f'A {inner_radius},{inner_radius} 0 0 0 {imx},{imy} '
                f'A {inner_radius},{inner_radius} 0 0 0 {ix1},{iy1} '
                f'Z'
            )
        else:
            large_arc = 1 if sweep > 180.0 else 0
            path = (
                f'M {x1},{y1} '
                f'A {radius},{radius} 0 {large_arc} 1 {x2},{y2} '
                f'L {ix2},{iy2} '
                f'A {inner_radius},{inner_radius} 0 {large_arc} 0 {ix1},{iy1} '
                f'Z'
            )

        segments.append(
            {
                'name': slice['name'],
                'tone': slice['tone'],
                'value': slice['value'],
                'share': slice['share'],
                'd': path,
            }
        )
        start_angle = end_angle

    return {
        'width': size,
        'height': size,
        'cx': cx,
        'cy': cy,
        'radius': radius,
        'stroke': stroke,
        'total': total,
        'segments': segments,
    }
