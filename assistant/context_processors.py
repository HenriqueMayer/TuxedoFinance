# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from assistant.context import ScopeError, normalize_location, scope_label, sign_normalized_scope


def assistant_shell(request):
    result = {'assistant_available': False, 'assistant_scope': '', 'assistant_scope_label': ''}
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return result
    try:
        scope = normalize_location(user, request.get_full_path())
        result.update(assistant_available=True, assistant_scope=sign_normalized_scope(user, scope),
                      assistant_scope_label=scope_label(scope))
    except (ScopeError, ValueError):
        pass
    return result
