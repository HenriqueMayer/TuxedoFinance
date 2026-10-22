"""Shared native presentation widgets. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0"""
import re

from django import forms
from django.utils.translation import gettext_lazy as _


class ColorPicker(forms.TextInput):
    """A native color field with optional progressive preset shortcuts."""

    input_type = 'color'
    is_color_picker = True
    color_presets = (
        ('#111111', _('Black')),
        ('#64788C', _('Blue gray')),
        ('#820AD1', _('Purple')),
        ('#245FBA', _('Blue')),
        ('#E87524', _('Orange')),
        ('#C6A173', _('Gold')),
    )

    def __init__(self, attrs=None, *, presets=True):
        super().__init__(attrs)
        if not presets:
            self.color_presets = ()

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        control_attrs = context['widget']['attrs']
        # Browsers replace malformed native color values with black. Retain an
        # invalid bound value as editable text beside its server error instead.
        if value and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)):
            context['widget']['type'] = 'text'
            control_attrs['class'] = f"{control_attrs.get('class', '')} entry-input color-picker-recovery".strip()
        elif self.color_presets and control_attrs.get('id'):
            control_attrs['list'] = f"{control_attrs['id']}-palette"
        return context


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
