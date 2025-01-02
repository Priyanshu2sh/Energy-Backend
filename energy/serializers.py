from rest_framework import serializers

from accounts.models import User
from .models import SolarPortfolio, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, StandardTermsSheet

class SolarPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )
    class Meta:
        model = SolarPortfolio
        fields = ['id', 'user', 'state', 'capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'marginal_cost',
                  'hourly_data', 'annual_generation_potential', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'marginal_cost': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
        }
    
    def update(self, instance, validated_data):
        # Set 'updated' to True on PUT method
        validated_data['updated'] = True
        return super().update(instance, validated_data)
    
    def validate_user(self, user):
        if user.user_category != 'Generator':
            raise serializers.ValidationError("Only users with user_category='Generator' are allowed.")
        return user
    
class WindPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )
    class Meta:
        model = WindPortfolio
        fields = ['id', 'user', 'state', 'capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'marginal_cost',
                  'hourly_data', 'annual_generation_potential', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'marginal_cost': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
        }
    
    def update(self, instance, validated_data):
        # Set 'updated' to True on PUT method
        validated_data['updated'] = True
        return super().update(instance, validated_data)
    
    def validate_user(self, user):
        if user.user_category != 'Generator':
            raise serializers.ValidationError("Only users with user_category='Generator' are allowed.")
        return user
    
class ESSPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )
    class Meta:
        model = ESSPortfolio
        fields = ['id', 'user', 'state', 'capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'marginal_cost',
                  'efficiency_of_storage', 'efficiency_of_dispatch', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'marginal_cost': {'required': False},
            'efficiency_of_storage': {'required': False},
            'efficiency_of_dispatch': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
        }
    
    def update(self, instance, validated_data):
        # Set 'updated' to True on PUT method
        validated_data['updated'] = True
        return super().update(instance, validated_data)
    
    def validate_user(self, user):
        if user.user_category != 'Generator':
            raise serializers.ValidationError("Only users with user_category='Generator' are allowed.")
        return user

class ConsumerRequirementsSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )
    class Meta:
        model = ConsumerRequirements
        fields = ['id', 'user', 'state', 'industry', 'contracted_demand', 'tariff_category', 'voltage_level', 'procurement_date']

    def validate_user(self, user):
        if user.user_category != 'Consumer':
            raise serializers.ValidationError("Only users with user_category='Consumer' are allowed.")
        return user

class MonthlyConsumptionDataSerializer(serializers.ModelSerializer):
    requirement = serializers.SlugRelatedField(
        queryset=ConsumerRequirements.objects.all(),
        slug_field='id'  # Map the requirement field to the id field
    )
    class Meta:
        model = MonthlyConsumptionData
        fields = ['requirement', 'month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount']

    def validate_user(self, requirement):
        if requirement.user.user_category != 'Consumer':
            raise serializers.ValidationError("Only users with user_category='Consumer' are allowed.")
        return requirement

class StandardTermsSheetSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandardTermsSheet
        fields = '__all__'