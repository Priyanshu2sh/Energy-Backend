from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import User
import random

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'user_category', 'role', 'email', 'mobile', 'company', 'company_representative', 'cin_number', 'designation', 'password', 'verified_at', 'last_visited_page', 'selected_requirement_id', 'is_new_user', 'solar_template_downloaded', 'wind_template_downloaded', 'credit_rating', 'credit_rating_proof']
        extra_kwargs = {'cin_number': {'required': False}, 'last_visited_page': {'required': False}, 'selected_requirement_id': {'required': False}, 'password': {'write_only': True}, 'otp': {'read_only': True}, 'verified_at': {'read_only': True}, 'role': {'read_only': True}, 'credit_rating': {'read_only': True}, 'credit_rating_proof': {'read_only': True}}

    def generate_username(self, user_category):
        prefix = 'CUD' if user_category == 'Consumer' else 'IPP'
        while True:
            random_number = random.randint(1000, 9999)
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
            "email",
            "mobile",
            "company",
            "company_representative",
            "credit_rating",
            "credit_rating_proof",
        ]