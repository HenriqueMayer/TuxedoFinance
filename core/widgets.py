"""Shared native presentation widgets. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0"""
from django import forms


class _ChoiceMetadata:
    """Decorate native options without replacing their values or ownership scope."""

    choice_data = None

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if self.choice_data and value:
            # The iterator carries its queried instance, avoiding per-option lookups.
            if callable(self.choice_data):
                instance = getattr(value, 'instance', None)
                data = self.choice_data(instance) if instance is not None else {}
            else:
                data = self.choice_data.get(str(value), {})
            option['attrs'].update(data)
        return option


class SelectWithMetadata(_ChoiceMetadata, forms.Select):
    pass


class SelectMultipleWithMetadata(_ChoiceMetadata, forms.SelectMultiple):
    pass


class SegmentedChoice(forms.RadioSelect):
    """A small set of choices, with native radio submission and keyboard use."""

    is_segmented_choice = True

    def id_for_label(self, id_, index=None):
        # Help and errors address the group; option labels retain unique IDs.
        # The shared field renderer supplies its real fieldset and legend.
        return id_ if index is None else super().id_for_label(id_, index)

    def create_option(self, *args, **kwargs):
        option = super().create_option(*args, **kwargs)
        option['attrs']['class'] = 'entry-choice-input'
        return option
