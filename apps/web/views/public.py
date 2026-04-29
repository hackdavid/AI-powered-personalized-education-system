"""Public (unauthenticated) template views."""

from django.shortcuts import render


def home(request):
    """Landing / home page."""
    return render(request, 'base/home.html')
