from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('register', views.RegisterUser.as_view(), name='registration'),
    path('verify-otp', views.VerifyOTP.as_view(), name='verify_otp'),
    path('login', views.LoginUser.as_view(), name='login'),
    path('forgot-password/<str:email>', views.LoginUser.as_view(), name='forgot_password'),
    path('verify-forgot-password-otp', views.ForgotPasswordOTP.as_view(), name='verify_forgot_password_otp'),
    path('set-new-password', views.SetNewPassword.as_view(), name='set_new_password'),
    path('update-profile/<int:pk>', views.UpdateProfileAPI.as_view(), name='update-profile'),
    path('add-sub-user/<int:user_id>', views.AddSubUser.as_view(), name='add_sub_user'),
    path('email/<str:token>', views.SetPassword.as_view(), name='set_password'),
    path('sub-users/<int:user_id>/', views.SubUsersAPI.as_view(), name='sub_users'),
]
