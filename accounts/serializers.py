from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import User
import random

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_category', 'name', 'email', 'mobile', 'company', 'cin_number', 'password', 'otp', 'verified_at']
        extra_kwargs = {'cin_number': {'required': False}, 'password': {'write_only': True}, 'otp': {'read_only': True}, 'verified_at': {'read_only': True}}

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
        # Hash the password using make_password
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "name",
            "user_category",
            "company",
            "company_representative",
            "cin_number",
            "mobile",
        ]