from django.conf import settings
import jwt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .models import User
from .serializers import UserSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import now
from datetime import datetime, timedelta
from rest_framework.permissions import IsAuthenticated


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
    def post(self, request):
        data = request.data
        user_category = data.get('user_category')
        serializer = UserSerializer(data=data)

        if serializer.is_valid():
            user = serializer.save()
            if user_category == 'Consumer':
                otp = random.randint(100000, 999999)
                user.otp = otp
                user.save()

                # Save email to session
                request.session['email'] = user.email

                # Send OTP to the user's email
                send_mail(
                    'Your OTP for Registration',
                    f'Your OTP is {otp}',
                    'noreply@example.com',
                    [user.email],
                    fail_silently=False,
                )
                return Response({'message': 'OTP sent to your email'}, status=status.HTTP_200_OK)
            
            return Response({'message': 'User registered successfully', 'data': serializer.data}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTP(APIView):
    def post(self, request):
        otp = request.data.get('otp')

        # Fetch email from session
        email = request.session.get('email')

        try:
            user = User.objects.get(email=email, otp=otp, verified_at__isnull=True)
            user.verified_at = now()  # Set the verified timestamp
            user.otp = None  # Clear the OTP field
            user.save()
            return Response({'message': 'User verified successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP, or user already verified'}, status=status.HTTP_400_BAD_REQUEST)

class LoginUser(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        # Validate email and password fields
        if not email or not password:
            return Response({'error': 'Email and password are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or password'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify password
        if not check_password(password, user.password):
            return Response({'error': 'Invalid email or password'}, status=status.HTTP_400_BAD_REQUEST)

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

        return Response({
            'message': 'Login successful',
            'token': token,
            'user': {
                'username': user.username,
                'email': user.email,
            }
        }, status=status.HTTP_200_OK)