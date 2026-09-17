#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Check HTTP locally without following redirects or trusting proxy variables."""
import http.client
import os


def main():
    host = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')[0].strip()
    if not host or host.startswith('.') or host == '*':
        host = 'localhost'
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
