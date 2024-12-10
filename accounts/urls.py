from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.RegisterUser.as_view(), name='registration'),
    path('verify-otp/', views.VerifyOTP.as_view(), name='verify_otp'),
    # path('login/', views.LoginAPIView.as_view(), name='login'),
]
