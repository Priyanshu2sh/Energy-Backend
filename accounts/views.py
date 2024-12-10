from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User
from .serializers import UserSerializer
from django.core.mail import send_mail
import random
from django.utils.timezone import now

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
