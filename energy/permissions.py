from rest_framework.permissions import BasePermission
from django.conf import settings

class IsAuthenticatedOrInternal(BasePermission):
    def has_permission(self, request, view):
        # Allow if user is authenticated normally
        if request.user and request.user.is_authenticated:
            return True

        # Allow if internal token is valid
        internal_token = request.headers.get('X-Internal-Token')
        return internal_token == settings.INTERNAL_API_SECRET
