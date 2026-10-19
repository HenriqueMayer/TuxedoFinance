# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django import forms
from django.utils.translation import gettext_lazy as _


class CreateConversationForm(forms.Form):
    title = forms.CharField(max_length=120, required=False, label=_('Conversation title'))
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)


class SendMessageForm(forms.Form):
    content = forms.CharField(max_length=4000, label=_('Message'), widget=forms.Textarea)
    scope = forms.CharField(max_length=4096, required=False, widget=forms.HiddenInput)
