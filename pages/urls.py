from django.urls import path

from pages.views import LandingView, RoadmapView

app_name = 'pages'

urlpatterns = [
    path('', LandingView.as_view(), name='landing'),
    path('roadmap/', RoadmapView.as_view(), name='roadmap'),
]
