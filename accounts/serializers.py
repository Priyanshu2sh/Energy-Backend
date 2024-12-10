from rest_framework import serializers
from .models import User
import random

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_category', 'name', 'email', 'mobile', 'company', 'password', 'otp', 'verified_at']
        extra_kwargs = {'password': {'write_only': True}, 'otp': {'read_only': True}, 'verified_at': {'read_only': True}}

    def generate_username(self, user_category):
        prefix = 'con' if user_category == 'Consumer' else 'gen'
        while True:
            random_number = random.randint(100, 999)
            username = f"{prefix}{random_number}"
            if not User.objects.filter(username=username).exists():
                return username

    def create(self, validated_data):
        user_category = validated_data['user_category']
        validated_data['username'] = self.generate_username(user_category)
        validated_data.pop('password')  # Password should be hashed and saved securely
        return super().create(validated_data)
