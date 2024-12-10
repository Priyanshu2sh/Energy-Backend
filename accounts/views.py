from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .serializers import LoginSerializer, UserRegistrationSerializer, VerifyOTPSerializer
import random
from django.core.mail import send_mail
from .models import OTP, User

# Create your views here.
def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(user):
    otp = generate_otp()
    OTP.objects.update_or_create(user=user, defaults={'otp': otp})
    subject = "Your Login OTP"
    message = f"Your OTP for login is: {otp}. It is valid for 5 minutes."
    send_mail(subject, message, 'your-email@gmail.com', [user.email])

class UserRegistrationView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        send_otp_email(user)

        return Response({
            "message": "OTP sent to your email. Please verify to continue."
        }, status=status.HTTP_200_OK)


class VerifyOTPAPIView(APIView):
    permission_classes = [IsAuthenticated]  # Ensure the user is authenticated

    def post(self, request, *args, **kwargs):
        # We don't need email in the request anymore, as it's attached to the user session or token
        user = request.user
        
        # Check if the OTP exists for the user
        try:
            otp_obj = OTP.objects.get(user=user)

            # Validate OTP
            serializer = VerifyOTPSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp = serializer.validated_data['otp']

            if otp_obj.otp == otp and otp_obj.is_valid():
                # OTP is valid, issue tokens
                refresh = RefreshToken.for_user(user)
                otp_obj.delete()  # Clean up used OTP
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'message': "Login successful"
                }, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
        except OTP.DoesNotExist:
            return Response({"error": "OTP not found. Request a new OTP."}, status=status.HTTP_404_NOT_FOUND)