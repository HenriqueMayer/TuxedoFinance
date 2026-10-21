# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit disposable-browser fixtures, never an installation configuration.

Only ``npm run test:e2e -- --assistant-fixtures`` may select this module. Its
runner owns the private runtime and empty .env. No credentials are created or
read. The two model choices and all responses are synthetic; external sockets,
OAuth and inference transports are blocked inside the test server process.
"""
import ipaddress
import os
from pathlib import Path
import stat

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME = (_ROOT / '.local/test-results/runtime').resolve()
_DIRECTORY = Path(os.environ.get('TUXEDO_DATA_DIR', '/not-a-test-runtime'))
_ENV_FILE = Path(os.environ.get('TUXEDO_ENV_FILE', '/not-a-test-env'))


def _guard():
    try:
        directory = _DIRECTORY.resolve(strict=True)
        info = _DIRECTORY.lstat()
        environment = _ENV_FILE.resolve(strict=True)
        env_info = _ENV_FILE.lstat()
        valid = (
            os.environ.get('E2E_ASSISTANT_FIXTURES') == '1'
            and _DIRECTORY.is_absolute() and str(_DIRECTORY) == str(directory)
            and directory.parent == _RUNTIME and directory.name.startswith('tuxedo-e2e-')
            and len(directory.name) > len('tuxedo-e2e-')
            and stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700
            and environment == directory / '.env' and _ENV_FILE == environment
            and stat.S_ISREG(env_info.st_mode) and env_info.st_nlink == 1
            and env_info.st_uid == os.getuid() and env_info.st_size == 0
            and _ENV_FILE.read_bytes() == b''
        )
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise ImproperlyConfigured('Assistant browser fixtures require the runner-owned disposable runtime.')


_guard()

# Import ordinary settings only after verifying that their environment/data
# sources are disposable. Copy without mutating the production settings module.
from core import settings as _ordinary_settings  # noqa: E402

globals().update({name: getattr(_ordinary_settings, name) for name in dir(_ordinary_settings) if name.isupper()})
ASSISTANT_OPENAI_AUTH_ENABLED = True
ASSISTANT_OPENAI_INFERENCE_ENABLED = True
ASSISTANT_PRIVATE_DIR = _DIRECTORY / 'assistant-private-unused'
INSTALLED_APPS = [*_ordinary_settings.INSTALLED_APPS,
                  'tests.e2e.assistant_mock_settings.AssistantFixturesConfig']


class AssistantFixturesConfig(AppConfig):
    name = 'tests.e2e'
    label = 'assistant_e2e_fixtures'
    path = str(Path(__file__).resolve().parent)

    def ready(self):
        import json
        import socket
        from threading import Event

        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_save

        from assistant.connections import oauth
        from assistant.models import ProviderConnection
        from assistant import providers
        from assistant.providers import openai
        from assistant.providers.base import DisconnectedProvider, ProviderEvent

        def blocked(*args, **kwargs):
            raise AssertionError('External network is disabled in assistant browser fixtures.')

        original_connect, original_getaddrinfo = socket.socket.connect, socket.getaddrinfo

        def loopback(value):
            if value == 'localhost':
                return True
            try:
                return ipaddress.ip_address(value).is_loopback
            except (ValueError, TypeError):
                return False

        def connect(sock, address):
            if not isinstance(address, tuple) or not address or not loopback(address[0]):
                return blocked()
            return original_connect(sock, address)

        def getaddrinfo(host, *args, **kwargs):
            if not loopback(host):
                return blocked()
            return original_getaddrinfo(host, *args, **kwargs)

        socket.socket.connect = connect
        socket.getaddrinfo = getaddrinfo
        oauth.HTTPTransport.__call__ = blocked
        openai.HTTPTransport.__call__ = blocked

        class FixtureProvider:
            available = True

            def list_models(self, cancellation=None):
                if cancellation:
                    cancellation.raise_if_cancelled()
                return [{'slug': 'mock-standard', 'display_name': 'Mock Standard',
                         'reasoning_efforts': ['low', 'medium', 'high'], 'default_reasoning_effort': 'medium'},
                        {'slug': 'mock-mini', 'display_name': 'Mock Mini with a deliberately long model name for a narrow screen',
                         'reasoning_efforts': ['low', 'high'], 'default_reasoning_effort': 'low'}]

            def stream(self, generation, cancellation):
                cancellation.raise_if_cancelled()
                content = generation.history[-1].content if generation.history else ''
                if content == '[references]':
                    result = generation.tool_runner('simulate_month', {
                        'planning_month': '2026-10', 'gross_salary': '6000', 'clt_dependents': 0,
                        'clt_pension': '0', 'clt_transport': '0', 'clt_food': '0', 'clt_health': '0',
                        'clt_other': '700', 'extra_expenses': [], 'category_reductions': [],
                    })
                    if result.get('error'):
                        yield ProviderEvent('text', text='Synthetic reference fixture failed: ' + result['error'])
                    else:
                        # These are the actual calculation's owned references,
                        # deliberately repeated in a model-like Markdown footer.
                        # Only the presentation layer should deduplicate them.
                        footer = ' · '.join(f'[{row["label"]}]({row["url"]})' for row in result['references'])
                        text = ('Premissas sintéticas: **desconto em folha BRL 700,00**, salário bruto BRL 6.000,00; '
                                'cálculo hipotético. <estimativa>\n\n' + footer)
                        for offset in range(0, len(text), 23):
                            cancellation.raise_if_cancelled()
                            yield ProviderEvent('text', text=text[offset:offset + 23])
                    yield ProviderEvent('done')
                    return
                if content.startswith('[consult]'):
                    # Return only a synthetic rendering of the real read/simulation
                    # result. Prerequisites are ordinary POSTs in the browser test;
                    # this provider never creates records during generation.
                    payload = json.loads(content[len('[consult]'):])
                    if payload['name'] not in {'read_financial_data', 'simulate_month'}:
                        raise ValueError('Unsupported synthetic consultation.')
                    result = generation.tool_runner(payload['name'], payload['arguments'])
                    text = 'Synthetic consultation result.\n\n```json\n' + json.dumps(result, ensure_ascii=False) + '\n```'
                    for offset in range(0, len(text), 2000):
                        cancellation.raise_if_cancelled()
                        yield ProviderEvent('text', text=text[offset:offset + 2000])
                    yield ProviderEvent('done')
                    return
                marker = '[failed_action]' if content.startswith('[failed_action]') else '[action]'
                if content.startswith(marker):
                    # Exercise the real dispatcher and canonical validation.
                    # Fixtures never create financial prerequisites or bypass
                    # the separate human-confirmation HTTP boundary.
                    payload = json.loads(content[len(marker):])
                    result = generation.tool_runner(payload['name'], payload['arguments'])
                    if result.get('error'):
                        yield ProviderEvent('text', text='Synthetic action validation: ' + result['error'])
                        yield ProviderEvent('done')
                        return
                    release = Event()
                    unregister = cancellation.register_close(release.set)
                    try:
                        release.wait(.7)
                        cancellation.raise_if_cancelled()
                    finally:
                        unregister()
                    yield ProviderEvent('text', text='Synthetic proposal. **Review** its details before saving.')
                    yield ProviderEvent('error', code='transport_error') if marker == '[failed_action]' else ProviderEvent('done')
                    return
                if '[thinking]' in content:
                    release = Event()
                    unregister = cancellation.register_close(release.set)
                    try:
                        # Distinguish waiting from actual output without a live
                        # provider, and keep both phases observable by keyboard.
                        release.wait(1.2)
                        cancellation.raise_if_cancelled()
                        yield ProviderEvent('text', text='Synthetic **value**')
                        release.wait(1.2)
                        cancellation.raise_if_cancelled()
                        yield ProviderEvent('text', text=' is ready.')
                        yield ProviderEvent('done')
                    finally:
                        unregister()
                    return
                if '[markdown]' in content:
                    text = (
                        '# Resumo\n\n**Valor**: `BRL 100,00`; *estimativa*.\n\n'
                        '- Receita\n- Despesa\n\n> Dados sintéticos.\n\n'
                        '| Tipo | Valor |\n| --- | ---: |\n| Previsto | **10,00** |\n\n'
                        '```html\n<img src=x onerror="window.__assistantInjected=true">\n```\n\n'
                        '<img src=x onerror="window.__assistantInjected=true">\n\n'
                        '[Conta](/banking/123/) ![pixel](https://example.test/pixel) '
                        '[x](javascript:alert(1))')
                    for offset in range(0, len(text), 17):
                        yield ProviderEvent('text', text=text[offset:offset + 17])
                    yield ProviderEvent('done')
                    return
                if '[cancel]' in content:
                    release = Event()
                    unregister = cancellation.register_close(release.set)
                    try:
                        yield ProviderEvent('text', text='Synthetic pending response. ')
                        release.wait(2)
                        cancellation.raise_if_cancelled()
                    finally:
                        unregister()
                if '[error]' in content:
                    yield ProviderEvent('text', text='Synthetic partial response. ')
                    yield ProviderEvent('error', code='transport_error')
                    return
                if '[tail]' in content:
                    # A bounded, paced fixture lets a reader scroll away from
                    # the live tail without an external model or network call.
                    release = Event()
                    unregister = cancellation.register_close(release.set)
                    try:
                        for index in range(30):
                            yield ProviderEvent('text', text=(
                                f'Synthetic streamed paragraph {index + 1}. '
                                'Reading earlier messages should keep the reader in place.\n\n'))
                            release.wait(.12)
                            cancellation.raise_if_cancelled()
                    finally:
                        unregister()
                    yield ProviderEvent('done')
                    return
                if '[long]' in content:
                    text = (
                        'Synthetic long conversation. ' + 'W' * 120 + '\n\n'
                        + '\n\n'.join(
                            f'Paragraph {index + 1}. Account and transaction details here are entirely synthetic. '
                            'The composer stays available while this transcript scrolls.'
                            for index in range(52)))
                    for offset in range(0, len(text), 2000):
                        yield ProviderEvent('text', text=text[offset:offset + 2000])
                    yield ProviderEvent('done')
                    return
                if '[settings]' in content:
                    yield ProviderEvent('text', text=(
                        f'Synthetic request: {generation.model}; effort: {generation.reasoning_effort or "default"}.'))
                    yield ProviderEvent('done')
                    return
                text = ('<img src=x onerror="window.__assistantInjected=true"><strong>Untrusted model text</strong>'
                        if '[html]' in content else
                        'Synthetic assistant fixture response. No provider request was sent.')
                yield ProviderEvent('text', text=text)
                yield ProviderEvent('done')

        def fixture_provider(user=None, connection_id=None):
            if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
                return DisconnectedProvider()
            selected = ProviderConnection.objects.filter(user=user, provider='openai', is_active=True, status='ready')
            if connection_id is not None:
                selected = selected.filter(pk=connection_id)
            return FixtureProvider() if selected.exists() else DisconnectedProvider()

        # Patch the public factory before chat captures its import, then patch
        # its lookup explicitly if another app imported chat earlier in setup.
        providers.get_provider = fixture_provider
        from assistant import chat
        chat.get_provider = fixture_provider

        def account_created(sender, instance, created, raw=False, **kwargs):
            if created and not raw:
                ProviderConnection.objects.create(
                    user=instance, issuer=oauth.ISSUER, subject='synthetic-' + str(instance.pk),
                    client_id='mock-registration-' + str(instance.pk), email='fixture@example.test',
                    scopes=['resource.invoke', 'chatgpt.tokens.use.direct'],
                    status=ProviderConnection.Status.READY, is_active=True)

        post_save.connect(account_created, sender=get_user_model(), weak=False,
                          dispatch_uid='assistant-e2e-fixture-connection-v1')
