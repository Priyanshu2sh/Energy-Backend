from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('register', views.RegisterUser.as_view(), name='registration'),
    path('verify-otp', views.VerifyOTP.as_view(), name='verify_otp'),
    path('login', views.LoginUser.as_view(), name='login'),
    path('login/<int:pk>', views.LoginUser.as_view(), name='forgot_password'),
    path('verify-forgot-password-otp/<int:pk>', views.ForgotPasswordOTP.as_view(), name='verify_forgot_password_otp'),
    path('set-new-password/<int:pk>', views.SetNewPassword.as_view(), name='set_new_password'),
    path('update-profile/<int:pk>', views.UpdateProfileAPI.as_view(), name='update-profile'),
]
