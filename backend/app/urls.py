from django.urls import path
from app.views.lineups import LineupsLeagueSummary

urlpatterns = [path("api/v1/lineups", LineupsLeagueSummary.as_view(), name="lineups_summary")]
