"""Shared accessible form rendering. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0"""
from django import forms, template

register = template.Library()


@register.filter
def is_checkbox(field):
    """Keep single boolean controls beside their label, preserving native input."""
    return isinstance(field.field.widget, forms.CheckboxInput)


@register.simple_tag
def form_control(field):
    """Enhance model choices automatically; retain their native POST control."""
    described_by = field.field.widget.attrs.get('aria-describedby', '').split()
    if field.help_text:
        described_by.append(f'{field.id_for_label}-help')
    described_by.extend(f'{field.id_for_label}-error-{i}' for i in range(1, len(field.errors) + 1))
    attrs = {'aria-describedby': ' '.join(dict.fromkeys(described_by))} if described_by else {}
    if field.errors:
        attrs['aria-invalid'] = 'true'
    # Styling belongs to the shared renderer, while widget types, native POST
    # values and numeric precision remain the owning form's responsibility.
    widget = field.field.widget
    if not isinstance(widget, (
        forms.HiddenInput, forms.CheckboxInput, forms.RadioSelect,
        forms.CheckboxSelectMultiple, forms.FileInput,
    )) and getattr(widget, 'input_type', '') != 'color':
        classes = widget.attrs.get('class', '')
        attrs['class'] = classes if 'entry-input' in classes.split() else f'{classes} entry-input'.strip()
    if isinstance(field.field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
        attrs['data-search-select'] = ''
        if field.auto_id == 'id_category':
            attrs['data-search-id'] = 'category-search'
        elif field.auto_id == 'id_parent_category':
            attrs['data-search-id'] = 'parent-category-search'
    return field.as_widget(attrs=attrs)
