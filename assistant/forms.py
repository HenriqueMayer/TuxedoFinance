# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django import forms
from django.utils.translation import gettext_lazy as _

from assistant.providers.base import REASONING_EFFORTS, reasoning_efforts


class CreateConversationForm(forms.Form):
    title = forms.CharField(max_length=120, required=False, label=_('Conversation title'))
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)


class ChatSettingsForm(forms.Form):
    """The same catalogue and pair validation for local settings and Send."""

    model = forms.ChoiceField(label=_('Model'), choices=())
    reasoning_effort = forms.ChoiceField(required=False, label=_('Reasoning effort'), choices=())
    connection_id = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, models=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.models = {item['slug']: item for item in models}
        self.fields['model'].choices = [('', _('Choose a model'))] + [
            (item['slug'], item['display_name']) for item in models]
        labels = {'none': _('None'), 'minimal': _('Minimal'), 'low': _('Low'), 'medium': _('Medium'),
                  'high': _('High'), 'xhigh': _('Extra high'), 'max': _('Maximum')}
        available = {effort for item in models for effort in reasoning_efforts(item.get('reasoning_efforts'))}
        # The native form retains the full catalogue union. JS narrows the same
        # select on model changes; the server still validates the selected pair.
        self.fields['reasoning_effort'].choices = [('', _('Model default'))] + [
            (effort, labels[effort]) for effort in REASONING_EFFORTS if effort in available]

    def clean(self):
        cleaned = super().clean()
        model = self.models.get(cleaned.get('model'))
        effort = cleaned.get('reasoning_effort')
        if model is not None and effort and effort not in reasoning_efforts(model.get('reasoning_efforts')):
            self.add_error('reasoning_effort', _('This effort is not available for the selected model.'))
        elif not cleaned.get('model') and effort:
            self.add_error('reasoning_effort', _('This effort is not available for the selected model.'))
        return cleaned


class SaveChatSettingsForm(ChatSettingsForm):
    model = forms.ChoiceField(required=False, label=_('Model'), choices=())


class SendMessageForm(ChatSettingsForm):
    content = forms.CharField(max_length=4000, label=_('Message'),
                             widget=forms.Textarea(attrs={'rows': 1, 'placeholder': _('Write a message…')}))
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)
    location = forms.CharField(max_length=2048, required=False, widget=forms.HiddenInput)
    include_context = forms.BooleanField(required=False, initial=False,
                                        label=_('Use page data'))
    field_order = ['content', 'model', 'reasoning_effort', 'connection_id', 'request_id', 'scope',
                   'location', 'include_context']
