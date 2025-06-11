import base64
import json
from django.conf import settings
import jwt
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from django.core.files.base import ContentFile
from energy.models import GeneratorOffer
from .models import User
from .serializers import UserSerializer, UserProfileUpdateSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import now
from datetime import datetime, timedelta
from rest_framework.permissions import IsAuthenticated
from twilio.rest import Client
from django.utils.crypto import get_random_string
from thefuzz import fuzz
# Get the logger that is configured in the settings
import logging
logger = logging.getLogger('debug_logger')


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
        
        # Twilio Client initialization
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Send OTP via SMS
        # try:
      
        message = client.messages.create(
            body=f'Your OTP for registration is {otp}',
            from_=settings.TWILIO_PHONE_NUMBER,
            to=f'+91{mobile_number}'
        )
        

    def post(self, request):
        data = request.data
        email = data.get('email')
        user_category = data.get('user_category')
        domain = email.split('@')[-1] if email else None

        if not domain:
            return Response({'error': 'Invalid email format.'}, status=status.HTTP_400_BAD_REQUEST)

        # Extract company and CIN from the request data
        company_name = data.get('company')
        cin_number = data.get('cin_number')

        # Verify CIN and company name using Surepass API
        # if cin_number and company_name:
        #     api_url = "https://sandbox.surepass.io/api/v1/corporate/company-details"
        #     headers = {
        #         "Content-Type": "application/json",
        #         "Authorization": f"Bearer {settings.SUREPASS_API_KEY}"  # Ensure you have your API key in settings
        #     }
        #     payload = {"id_number": cin_number}

        #     try:
        #         response = requests.post(api_url, json=payload, headers=headers)
        #         if response.status_code == 200:
        #             response_data = response.json()
        #             # Assuming the API returns a 'company_name' field in the response
        #             response_data = response_data['data']
        #             
        #             company_from_api = response_data['company_name'].strip().lower()
        #             company_name = company_name.strip().lower()

        #             similarity_score = fuzz.ratio(company_name, company_from_api)
        #             
        #             if similarity_score <= 95:
        #                 return Response(
        #                 {'error': 'The provided CIN does not match the company name.'},
        #                 status=status.HTTP_400_BAD_REQUEST
        #             )

        #         elif response.status_code == 422:
        #             return Response(
        #                 {'error': 'Invalid CIN number.'},
        #                 status=status.HTTP_400_BAD_REQUEST
        #             )
        #         else:
        #             return Response(
        #                 {'error': 'Failed to verify CIN. Please try again later.'},
        #                 status=status.HTTP_400_BAD_REQUEST
        #             )
            # except requests.RequestException as e:
            #     return Response(
            #         {'error': 'An error occurred while verifying CIN.', 'details': str(e)},
            #         status=status.HTTP_500_INTERNAL_SERVER_ERROR
            #     )
        # else:
        #     return Response(
        #         {'error': 'Company name and CIN number are required.'},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )

        serializer = UserSerializer(data=data)

        try:
            # Check if a user with this email already exists
            existing_user = User.objects.get(email=email)
            if existing_user.verified_at is None:
                # If the user exists but is not verified, update details and resend OTP
                # email_otp = random.randint(100000, 999999)
                # mobile_otp = random.randint(100000, 999999)
                email_otp = 9876
                mobile_otp = 2748

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
                    f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                    [existing_user.email],
                    fail_silently=False,
                )
                return Response({'message': 'OTP resent to your email and mobile.', 'user_id': existing_user.id}, status=status.HTTP_200_OK)
            else:
                # If the user is verified, inform the user they cannot register again
                return Response({'error': 'Email is already registered and verified. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            # If no existing user is found, proceed with registration

            # Check if any existing user has the same email domain
            existing_user_with_domain = User.objects.filter(email__icontains=f'@{domain}').first()
            # if existing_user_with_domain:
            #     return Response(
            #         {'error': f"An admin for the domain '{domain}' already exists. Please contact them to add sub-users."},
            #         status=status.HTTP_400_BAD_REQUEST
            #     )

            if serializer.is_valid():
                user = serializer.save()
                user.parent = None  # Root of the hierarchy

                # Send OTP
                # email_otp = random.randint(100000, 999999)
                # mobile_otp = random.randint(100000, 999999)
                email_otp = 9876
                mobile_otp = 2748
                user.email_otp = email_otp
                user.mobile_otp = mobile_otp
                user.save()

                # Save email to session
                request.session['email'] = user.email

                # Send OTP to the user's email
                send_mail(
                    'Your OTP for Registration',
                    f'Your OTP is {email_otp}',
                    f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
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

        # Check if the user is verified
        if user.verified_at is None:
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

        if user.user_category == 'Generator':
            if user.elite_generator == False:
                offers = GeneratorOffer.objects.filter(generator=user, is_accepted=True)
                if offers:
                    total_capacity = 0
                    for offer in offers:
                        total_capacity += offer.tariff.terms_sheet.combination.optimal_solar_capacity + offer.tariff.terms_sheet.combination.optimal_wind_capacity + offer.tariff.terms_sheet.combination.optimal_battery_capacity

                    if total_capacity > 100:
                        user.elite_generator = True
                        user.save()

        return Response({
            'message': 'Login successful',
            'token': token,
            'user': user_data
        }, status=status.HTTP_200_OK)
    
    def get(self, request, email):

        user = User.objects.filter(email=email).first()
        registration_token = get_random_string(64)
        if user and user.verified_at is not None:
            # email_otp = random.randint(100000, 999999)
            email_otp = 9876

            user.email_otp = email_otp
            user.registration_token = registration_token
            user.save()

            # Send email to sub-user with a registration link
            if settings.ENVIRONMENT == 'local':
                registration_link = f"http://localhost:3001/email/{registration_token}"
            else:
                registration_link = f"https://exgglobal.com/email/{registration_token}"
            send_mail(
                'Set Up Your Account Password',
                f'Please set your new password using the following link:\n\n{registration_link}\n\nIf you did not request this, please ignore this email.\n\nThank You',
                f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                [email],
                fail_silently=False,
            )

            return Response({'message': 'Link sent on your email.', 'user_id': user.id}, status=status.HTTP_200_OK)
        else:
            # If the user is verified, inform the user they cannot register again
            return Response({'error': 'Email not found.'}, status=status.HTTP_400_BAD_REQUEST)
    
class UpdateProfileAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        user = User.objects.get(id=pk)
        data = request.data.copy()

        # Decode credit_rating_proof if provided in Base64
        encoded_proof = data.get("credit_rating_proof")
        if encoded_proof:
            try:
                decoded_file = base64.b64decode(encoded_proof)

                # Check if it's a valid PDF (starts with %PDF)
                if not decoded_file.startswith(b"%PDF"):
                    return Response(
                        {"error": "Uploaded file is not a valid PDF."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Optional: You can perform validation like checking file headers/types
                file_name = f"credit_rating_proof_{pk}.pdf"  # or .jpg, .png, etc. based on your expected type

                # Convert to ContentFile
                file_content = ContentFile(decoded_file, name=file_name)

                # Replace encoded string with actual file in data
                data["credit_rating_proof"] = file_content

            except Exception as e:
                return Response({"error": "Invalid Base64 for credit_rating_proof", "details": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)
            
        serializer = UserProfileUpdateSerializer(user, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "data": serializer.data}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class AddSubUser(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        try:
            admin = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Invalid user id.'}, status=status.HTTP_404_NOT_FOUND)

        if admin.role != "Admin":
            return Response({'error': 'Only admins can add sub-users.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        email = data.get('email')
        company_representative = data.get('company_representative')
        designation = data.get('designation')
        role = data.get('role')

        if not email or not email or not designation or not role :
            return Response({'error': 'Email and role are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if a user with the given email already exists
        if User.objects.filter(email=email).exists():
            return Response({'error': 'A user with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create a temporary user with a registration token
        registration_token = get_random_string(64)
        if admin.user_category == 'Consumer':
            username = UserSerializer.generate_username(self, 'Consumer')
            sub_user = User.objects.create(
                email=email,
                company_representative=company_representative,
                designation=designation,
                role=role,
                parent=admin,  # Link sub-user to the admin
                user_category="Consumer",  # Assuming all sub-users are consumers
                username=username,
                registration_token=registration_token,
                is_active=False,  # User will be inactive until they set their password
            )
        else:
            username = UserSerializer.generate_username(self, 'Generator')
            sub_user = User.objects.create(
                email=email,
                role=role,
                user_category="Generator",  # Assuming all sub-users are consumers
                username=username,
                registration_token=registration_token,
                is_active=False,  # User will be inactive until they set their password
            )

        # Send email to sub-user with a registration link
        if settings.ENVIRONMENT == 'local':
            registration_link = f"http://localhost:3001/email/{registration_token}"
        else:
            registration_link = f"https://ext.exgglobal.com/email/{registration_token}"
        send_mail(
            'Complete Your Registration',
            f'You have been added as a {role}. Please set your password using the following link: {registration_link}',
            f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
            [email],
            fail_silently=False,
        )

        return Response({'message': f'Sub-user {email} added successfully. An email has been sent to set their password.'}, status=status.HTTP_201_CREATED)

class SetPassword(APIView):

    def post(self, request, token):
        data = request.data
        password = data.get('password')
        token = data.get('token')

        if not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Find user by registration token
        try:
            user = User.objects.get(registration_token=token)
        except User.DoesNotExist:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)

        # Set password and activate user
        user.set_password(password)
        user.is_active = True
        user.verified_at = now()  # Set the verified timestamp
        user.registration_token = None  # Clear token
        user.save()

        return Response({'message': 'Password set successfully. You can now log in.'}, status=status.HTTP_200_OK)

class SubUsersAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            sub_users = user.children.all()  # Fetch all sub-users using the related_name 'children'
            serializer = UserSerializer(sub_users, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)