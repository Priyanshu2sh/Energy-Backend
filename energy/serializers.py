from rest_framework import serializers

from accounts.models import User
from .models import GenerationPortfolio, ConsumerRequirements, MonthlyConsumptionData

class GenerationPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='email'  # Map the user field to the email field
    )
    class Meta:
        model = GenerationPortfolio
        fields = ['id', 'user', 'energy_type', 'state', 'capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'marginal_cost',
                  'hourly_data', 'annual_generation_potential',
                  'efficiency_of_storage', 'efficiency_of_dispatch', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'marginal_cost': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'efficiency_of_storage': {'required': False},
            'efficiency_of_dispatch': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
        }
    
    def update(self, instance, validated_data):
        # Set 'updated' to True on PUT method
        validated_data['updated'] = True
        return super().update(instance, validated_data)

class ConsumerRequirementsSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='email'  # Map the user field to the email field
    )
    class Meta:
        model = ConsumerRequirements
        fields = ['id', 'user', 'state', 'industry', 'contracted_demand', 'tariff_category', 'voltage_level', 'procurement_date']

class MonthlyConsumptionDataSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='email'  # Map the user field to the email field
    )
    class Meta:
        model = MonthlyConsumptionData
        fields = ['user', 'month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount']
