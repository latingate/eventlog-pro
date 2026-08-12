"""URLconf for the test project — admin only, so ``reverse()`` has targets."""

from django.contrib import admin
from django.urls import path

urlpatterns = [path("admin/", admin.site.urls)]
