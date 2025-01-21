import json
from django.conf import settings
import jwt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .models import User
from .serializers import UserSerializer, UserProfileUpdateSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import now
from datetime import datetime, timedelta
from rest_framework.permissions import IsAuthenticated
from twilio.rest import Client


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        # Get Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')

        try:
            user = User.objects.get(id=payload['user_id'])
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found')

        # Attach user to request for further use
        return (user, None)


class RegisterUser(APIView):

    @staticmethod
    def send_sms_otp(mobile_number, otp):
        print('otp sent')
        print(mobile_number)
        # Twilio Client initialization
        client = Client('AC3630d520a873fc8cb05fc3dac8529dfd', '7c83f127d3dc8b7caf5e432b1a494887')

        # Send OTP via SMS
        # try:
      
        message = client.messages.create(
            body=f'Your OTP for registration is {otp}',
            from_='+17084773632',
            to=f'+91{mobile_number}'
        )
        print(f"Message SID: {message.sid}")
        # except Exception as e:
        #     print(f"Failed to send OTP via SMS: {e}")

    def post(self, request):
        data = request.data
        print(data)
        email = data.get('email')
        user_category = data.get('user_category')
        serializer = UserSerializer(data=data)

        try:
            # Check if a user with this email already exists
            existing_user = User.objects.get(email=email)
            if existing_user.verified_at is None:
                # If the user exists but is not verified, update details and resend OTP
                email_otp = random.randint(100000, 999999)
                mobile_otp = random.randint(100000, 999999)

                existing_user.user_category = user_category
                existing_user.email_otp = email_otp
                existing_user.mobile_otp = mobile_otp
                existing_user.mobile = data.get('mobile')
                existing_user.save()

                # Save email to session
                request.session['email'] = existing_user.email

                # Send OTP via SMS using Twilio
                self.send_sms_otp(existing_user.mobile, otp=mobile_otp)

                # Resend OTP
                send_mail(
                    'Your OTP for Registration',
                    f'Your OTP is {email_otp}',
                    'noreply@example.com',
                    [existing_user.email],
                    fail_silently=False,
                )
                return Response({'message': 'OTP resent to your email and mobile.', 'user_id': existing_user.id}, status=status.HTTP_200_OK)
            else:
                # If the user is verified, inform the user they cannot register again
                return Response({'error': 'Email is already registered and verified. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            # If no existing user is found, proceed with registration
            if serializer.is_valid():
                user = serializer.save()
                email_otp = random.randint(100000, 999999)
                mobile_otp = random.randint(100000, 999999)
                user.email_otp = email_otp
                user.mobile_otp = mobile_otp
                user.save()

                # Save email to session
                request.session['email'] = user.email

                # Send OTP to the user's email
                send_mail(
                    'Your OTP for Registration',
                    f'Your OTP is {email_otp}',
                    'noreply@example.com',
                    [user.email],
                    fail_silently=False,
                )

                # Send OTP via SMS using Twilio
                self.send_sms_otp(user.mobile, mobile_otp)

                return Response({'message': 'OTP sent to your email', 'user_id': user.id}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTP(APIView):
    def post(self, request):
        user_id = request.data.get('user_id')
        email_otp = request.data.get('email_otp')
        mobile_otp = request.data.get('mobile_otp')
        

        try:
            user = User.objects.get(id=user_id, email_otp=email_otp, mobile_otp=mobile_otp, verified_at__isnull=True)
            user.verified_at = now()  # Set the verified timestamp
            user.email_otp = None  # Clear the OTP field
            user.save()
            return Response({'message': 'User verified successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Invalid OTP, or user already verified'}, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordOTP(APIView):
    def post(self, request):
        email_otp = request.data.get('email_otp')

        # Fetch email from session
        email = request.session.get('email')

        try:
            user = User.objects.get(email=email, email_otp=email_otp)
            user.email_otp = None  # Clear the OTP field
            user.save()
            return Response({'message': 'User verified successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP, or user already verified'}, status=status.HTTP_400_BAD_REQUEST)

class SetNewPassword(APIView):
    def post(self, request):
        password = request.data.get('password')

        # Fetch email from session
        email = request.session.get('email')

        try:
            user = User.objects.get(email=email)
            user.set_password(password)
            user.save()
            return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_400_BAD_REQUEST)

class LoginUser(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user_type = request.data.get('user_type')

        # Validate email and password fields
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        elif not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not user_type:
            return Response({'error': 'User Type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            if user.user_category != user_type:
                return Response({'error': f'You have not registered as {user_type}.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': f'Email ({email}) not found.'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify password
        if not check_password(password, user.password):
            return Response({'error': f'Email ({email}) found but password incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the user is verified (Consumer)
        if user.user_category == 'Consumer' and user.verified_at is None:
            return Response({'error': 'Please verify your email before logging in'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate JWT Token
        payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(days=1),  # Token expires in 1 day
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

        # Serialize user data using UserSerializer
        user_data = UserSerializer(user).data

        return Response({
            'message': 'Login successful',
            'token': token,
            'user': user_data
        }, status=status.HTTP_200_OK)
    
    def get(self, request, email):

        user = User.objects.filter(email=email).first()
        if user and user.verified_at is not None:
            email_otp = random.randint(100000, 999999)

            user.email_otp = email_otp
            user.save()

            # Save email to session
            request.session['email'] = user.email
            # Send OTP via SMS using Twilio
            RegisterUser.send_sms_otp(user.mobile, otp=email_otp)
            # Resend OTP
            send_mail(
                'Verification Code',
                f'Your OTP is {email_otp}',
                'noreply@example.com',
                [user.email],
                fail_silently=False,
            )
            return Response({'message': 'OTP sent to your email.'}, status=status.HTTP_200_OK)
        else:
            # If the user is verified, inform the user they cannot register again
            return Response({'error': 'Email not found.'}, status=status.HTTP_400_BAD_REQUEST)
    
class UpdateProfileAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        user = User.objects.get(id=pk)
        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "data": serializer.data}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)