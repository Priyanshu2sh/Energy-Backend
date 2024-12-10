import random
from rest_framework import serializers
from accounts.models import User
from django.contrib.auth import authenticate


class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['name', 'company', 'mobile', 'email', 'password', 'user_category']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def generate_unique_username(self, user_category):
        prefix = "con" if user_category == "Consumer" else "gen"
        while True:
            # Generate a random number and create a username
            random_number = random.randint(100, 999)
            username = f"{prefix}{random_number}"
            # Check if this username already exists
            if not User.objects.filter(username=username).exists():
                return username

    def create(self, validated_data):
        # Generate a username based on user_category
        user_category = validated_data.get('user_category')
        validated_data['username'] = self.generate_unique_username(user_category)

        # Create the user
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            **{k: v for k, v in validated_data.items() if k not in ['email', 'password']}
        )
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        elif not user.is_active:
            raise serializers.ValidationError("User account is inactive.")

        data['user'] = user
        return data
    
class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        otp = data.get('otp')

        if not otp:
            raise serializers.ValidationError("OTP is required.")

        return data
