# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django import forms
from django.utils.translation import gettext_lazy as _


class CreateConversationForm(forms.Form):
    title = forms.CharField(max_length=120, required=False, label=_('Conversation title'))
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)


class SendMessageForm(forms.Form):
    content = forms.CharField(max_length=4000, label=_('Message'), widget=forms.Textarea(attrs={'rows': 3}))
    model = forms.ChoiceField(label=_('Model'), choices=())
    connection_id = forms.UUIDField(widget=forms.HiddenInput)
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)
    location = forms.CharField(max_length=2048, required=False, widget=forms.HiddenInput)
    include_context = forms.BooleanField(required=False, initial=False,
                                        label=_('Include financial context from this page'))

    def __init__(self, *args, models=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model'].choices = [('', _('Choose a model'))] + [
            (item['slug'], item['display_name']) for item in models]
