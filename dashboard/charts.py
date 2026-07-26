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
    }
