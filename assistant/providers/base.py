# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synchronous streaming boundary, without credentials or persistence.

Adapters own bounded I/O timeouts and register a transport closer for active
cancellation. Cancellation also runs between events; it cannot undo a separately
confirmed operation.
"""
from collections.abc import Iterator
from dataclasses import dataclass
import json
import re
from threading import Event, Lock
from typing import Literal, Protocol

from django.db import connections

from assistant.prompts import INSTRUCTIONS_VERSION, SUPPORTED_INSTRUCTIONS_VERSIONS, load_instructions


class ProviderError(Exception):
    code = 'provider_error'

    def __init__(self, code='provider_error'):
        self.code = code if isinstance(code, str) and code in ERROR_CODES else 'provider_error'
        super().__init__(self.code)


class ProviderUnavailable(ProviderError):
    code = 'unavailable'

    def __init__(self):
        super().__init__('unavailable')


class ProviderCancelled(ProviderError):
    code = 'cancelled'

    def __init__(self):
        super().__init__('cancelled')


class ProviderTransactionError(RuntimeError):
    pass


class CancellationToken:
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._closers = set()

    def cancel(self):
        self._event.set()
        with self._lock:
            closers = tuple(self._closers)
        for close in closers:
            try:
                close()
            except Exception:
                pass

    def register_close(self, close):
        with self._lock:
            self._closers.add(close)
            cancelled = self._event.is_set()
        if cancelled:
            try:
                close()
            except Exception:
                pass
        return lambda: self._remove_close(close)

    def _remove_close(self, close):
        with self._lock:
            self._closers.discard(close)

    def raise_if_cancelled(self):
        if self._event.is_set():
            raise ProviderCancelled()


@dataclass(frozen=True)
class ChatTurn:
    role: Literal['user', 'assistant']
    content: str

    def __post_init__(self):
        if (self.role not in {'user', 'assistant'} or not isinstance(self.content, str)
                or len(self.content) > (16000 if self.role == 'assistant' else 4000)):
            raise ValueError('Invalid bounded chat turn.')


@dataclass(frozen=True)
class GenerationRequest:
    """An explicit, bounded copy of authorized context and selected history."""
    context_json: str
    history: tuple[ChatTurn, ...] = ()
    language: Literal['en', 'pt-br'] = 'en'
    instructions_version: str = INSTRUCTIONS_VERSION
    model: str = ''

    def __post_init__(self):
        if (not isinstance(self.context_json, str) or len(self.context_json) > 32000
                or not isinstance(json.loads(self.context_json), dict)
                or not isinstance(self.history, tuple) or len(self.history) > 20
                or not all(isinstance(turn, ChatTurn) for turn in self.history)
                or self.language not in {'en', 'pt-br'}
                or self.instructions_version not in SUPPORTED_INSTRUCTIONS_VERSIONS
                or not isinstance(self.model, str) or self.model and not valid_model(self.model)):
            raise ValueError('Invalid bounded generation request.')

    @property
    def instructions(self):
        return load_instructions(self.instructions_version) + f'\nSelected user language: {self.language}.\n'


ERROR_CODES = frozenset({'unavailable', 'cancelled', 'provider_error', 'transport_error', 'rate_limited',
                         'unauthorized', 'limit_exceeded', 'incomplete', 'interrupted', 'timeout', 'invalid_model',
                         'request_rejected', 'invalid_response', 'permission_denied'})


def valid_model(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}', value))


@dataclass(frozen=True)
class ProviderEvent:
    kind: Literal['text', 'error', 'done']
    text: str = ''
    code: str = ''

    def __post_init__(self):
        if (self.kind not in {'text', 'error', 'done'} or not isinstance(self.text, str)
                or not isinstance(self.code, str) or len(self.text) > 4000
                or (self.kind == 'error' and (self.text or self.code not in ERROR_CODES))
                or (self.kind != 'error' and self.code)
                or (self.kind == 'done' and self.text)):
            raise ValueError('Invalid provider event.')


class Provider(Protocol):
    def stream(self, request: GenerationRequest, cancellation: CancellationToken) -> Iterator[ProviderEvent]:
        ...


class DisconnectedProvider:
    available = False

    def stream(self, request, cancellation):
        cancellation.raise_if_cancelled()
        raise ProviderUnavailable()


def _outside_transaction():
    if any(database.in_atomic_block for database in connections.all(initialized_only=True)):
        raise ProviderTransactionError('Provider generation must run outside database transactions.')


def stream_response(provider, request, cancellation):
    """Yield typed events and a single terminal event; never save model output.

Transport failures expose a stable code, never the exception text (which could
contain credentials). The caller owns authorization and explicit persistence.
No HTTP streaming endpoint is exposed while the provider is disconnected.
"""
    iterator = None
    output_chars = 0
    try:
        _outside_transaction()
        cancellation.raise_if_cancelled()
        iterator = iter(provider.stream(request, cancellation))
        while True:
            _outside_transaction()
            cancellation.raise_if_cancelled()
            try:
                event = next(iterator)
            except StopIteration:
                yield ProviderEvent('error', code='interrupted')
                return
            if not isinstance(event, ProviderEvent):
                raise ProviderError()
            output_chars += len(event.text)
            if output_chars > 16000:
                yield ProviderEvent('error', code='limit_exceeded')
                return
            yield event
            if event.kind in {'done', 'error'}:
                return
    except ProviderError as error:
        yield ProviderEvent('error', code=error.code)
    except (OSError, TimeoutError):
        yield ProviderEvent('error', code='transport_error')
    except ProviderTransactionError:
        raise
    except Exception:
        yield ProviderEvent('error', code='provider_error')
    finally:
        if iterator is not None and callable(getattr(iterator, 'close', None)):
            try:
                iterator.close()
            except Exception:
                # A transport close error must not replace a terminal result
                # or expose an adapter's raw exception/credential material.
                pass
