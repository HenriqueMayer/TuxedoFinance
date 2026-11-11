"""Helpers for the validation errors that the API returns."""

from django.core.exceptions import ValidationError


def renamed(error, names):
    """Return ``error`` with model field names replaced by request field names.

    ``names`` maps a model field to the request field. A value of None drops
    the messages of that field.
    """
    if not hasattr(error, "error_dict"):
        return error
    errors = {}
    for field, messages in error.message_dict.items():
        if names.get(field, field) is None:
            continue
        target = errors.setdefault(names.get(field, field), [])
        target.extend(message for message in messages if message not in target)
    return ValidationError(errors)
