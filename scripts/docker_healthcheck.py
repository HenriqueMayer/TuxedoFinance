#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Check HTTP locally without following redirects or trusting proxy variables."""
import http.client
import os


def main():
    hosts = [value.strip() for value in os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')]
    host = next((value for value in hosts if value), 'localhost')
    # Django's leading-dot wildcard also accepts the domain without the dot.
    host = 'localhost' if host == '*' else host.removeprefix('.')
    headers = {'Host': host}
    if os.environ.get('HTTPS') == 'True':
        headers['X-Forwarded-Proto'] = 'https'
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=3)
    try:
        connection.request('GET', '/', headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise SystemExit(f'Unhealthy HTTP status: {response.status}')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
