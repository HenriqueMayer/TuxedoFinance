# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.urls import path
from assistant import views
from assistant import connection_views
from assistant import action_views
from assistant import export_views

app_name = 'assistant'
urlpatterns = [
    path('', views.index, name='index'),
    path('connections/', connection_views.index, name='connections'),
    path('connections/start/', connection_views.start, name='connection-start'),
    path('connections/callback/', connection_views.callback, name='connection-callback'),
    path('connections/callback/result/', connection_views.callback_result, name='connection-callback-result'),
    path('connections/attempts/<uuid:pk>/finish/', connection_views.finish, name='connection-finish'),
    path('connections/attempts/<uuid:pk>/cancel/', connection_views.cancel, name='connection-cancel'),
    path('connections/<uuid:pk>/authorize/', connection_views.start, name='connection-authorize'),
    path('connections/<uuid:pk>/activate/', connection_views.activate, name='connection-activate'),
    path('connections/<uuid:pk>/disconnect/', connection_views.disconnect, name='connection-disconnect'),
    path('context/', views.context_snapshot, name='context'),
    path('models/', views.models, name='models'),
    path('preferences/', views.preferences, name='preferences'),
    path('messages/', views.send_new, name='send-new'),
    path('runs/<uuid:pk>/cancel/', views.cancel_run, name='cancel-run'),
    path('actions/<uuid:pk>/confirm/', action_views.confirm, name='action-confirm'),
    path('actions/<uuid:pk>/cancel/', action_views.cancel, name='action-cancel'),
    path('conversations/new/', views.create, name='create'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/export/', export_views.conversation, name='export-conversation'),
    path('<uuid:pk>/messages/<uuid:message_pk>/export/', export_views.message, name='export-message'),
    path('<uuid:pk>/delete/', views.delete, name='delete'),
    path('<uuid:pk>/messages/', views.send, name='send'),
]
