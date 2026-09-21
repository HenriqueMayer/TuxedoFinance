# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Exact monetary data for progressive chart selection, separate from SVG floats."""
from decimal import Decimal
from django.utils.formats import date_format


def selection_data(rows, series, *, label='date', mode='sum', opening=0, chart=None):
    def cents(value):
        return str(int(Decimal(value).quantize(Decimal('0.01')) * 100))

    points = []
    for index, row in enumerate(rows):
        row['selection_index'] = index
        name = date_format(row[label], 'M Y') if label == 'date' else str(row[label])
        point = {'label': name, 'values': [cents(row[key]) for key, _ in series]}
        if chart:
            geometry = chart.get('groups', chart.get('points', []))[index]
            geometry['selection_index'] = index
            for series_index, bar in enumerate(geometry.get('bars', [])):
                bar['selection_series'] = series_index
            point['x'] = geometry.get('center', geometry.get('x'))
        points.append(point)
    return {'mode': mode, 'series': [str(name) for _, name in series], 'points': points, 'opening': cents(opening)}


def attach_details(data, user, scope, rows, keys, **options):
    """Sign the exact chart scope; the read-only endpoint always checks its owner."""
    from django.core import signing
    from django.urls import reverse
    for point, row in zip(data['points'], rows):
        point['details'] = []
        for key in keys:
            payload = {'user': user.pk, 'scope': scope, 'series': key, **options}
            if 'date' in row:
                payload['period'] = row['date'].strftime('%Y-%m')
            for source, target in [('key', 'instrument'), ('tone', 'recurrence'), ('id', 'category')]:
                if source in row:
                    payload[target] = row[source]
            token = signing.dumps(payload, salt='chart-details', compress=True)
            point['details'].append(reverse('dashboard:chart_details') + '?token=' + token)
    return data
