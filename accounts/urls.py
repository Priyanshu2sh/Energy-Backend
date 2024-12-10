from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.UserRegistrationView.as_view(), name='registration'),
    path('login/', views.LoginAPIView.as_view(), name='login'),
    path('verify-otp/', views.VerifyOTPAPIView.as_view(), name='verify_otp'),
]
