import base64
from rest_framework import serializers

from accounts.models import User
from .models import CapacitySizingCombination, HourlyDemand, OfflinePayment, PaymentTransaction, PerformaInvoice, ScadaFile, SolarPortfolio, StateTimeSlot, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, StandardTermsSheet, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs
from django.utils.timezone import timedelta, now
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

class SolarPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )

    class Meta:
        model = SolarPortfolio
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'expected_tariff',
                  'hourly_data', 'annual_generation_potential', 'updated', 'banking_available'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'expected_tariff': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
            'banking_available': {'required': False},
        }
    
    def update(self, instance, validated_data):
        # Remove hourly_data if it's None
        if 'hourly_data' in validated_data and validated_data['hourly_data'] is None:
            validated_data.pop('hourly_data')
            
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
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'expected_tariff',
                  'hourly_data', 'annual_generation_potential', 'updated', 'banking_available'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'expected_tariff': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
            'banking_available': {'required': False},
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
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'capital_cost', 'expected_tariff',
                  'efficiency_of_storage', 'efficiency_of_dispatch', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'capital_cost': {'required': False},
            'expected_tariff': {'required': False},
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
        fields = ['id', 'user', 'state', 'industry', 'sub_industry', 'contracted_demand', 'tariff_category', 'voltage_level', 'procurement_date', 'consumption_unit', 'annual_electricity_consumption', 'roof_area', 'solar_rooftop_capacity', 'location']
        extra_kwargs = {
            'sub_industry': {'required': False}
        }

    def validate_user(self, user):
        if user.user_category != 'Consumer':
            raise serializers.ValidationError("Only users with user_category='Consumer' are allowed.")
        return user
    
class ScadaFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScadaFile
        fields = ['id', 'requirement', 'file', 'uploaded_at']
        read_only_fields = ['uploaded_at']

class CSVFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourlyDemand
        fields = ['id', 'requirement', 'hourly_demand', 'csv_file']

        extra_kwargs = {
            'hourly_demand': {'required': False}
        }
        

class MonthlyConsumptionDataSerializer(serializers.ModelSerializer):
    requirement = serializers.SlugRelatedField(
        queryset=ConsumerRequirements.objects.all(),
        slug_field='id'  # Map the requirement field to the id field
    )
    class Meta:
        model = MonthlyConsumptionData
        fields = ['id', 'requirement', 'month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount']

    def validate_user(self, requirement):
        if requirement.user.user_category != 'Consumer':
            raise serializers.ValidationError("Only users with user_category='Consumer' are allowed.")
        return requirement

class StandardTermsSheetSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandardTermsSheet
        fields = '__all__'

class SubscriptionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionType
        fields = ['id', 'user_type', 'subscription_type', 'description', 'price', 'duration_in_days']

class SubscriptionEnrolledSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionEnrolled
        fields = ['id', 'user', 'subscription', 'start_date', 'end_date', 'status']
        extra_kwargs = {
            'end_date': {'required': False},
            'status': {'required': False}
        }

    def validate(self, attrs):
        user = attrs.get('user')
        subscription = attrs.get('subscription')

        # Check if the user is already enrolled in this subscription
        existing_subscription = SubscriptionEnrolled.objects.filter(user=user, subscription=subscription).first()
        if existing_subscription:
            if existing_subscription.end_date >= now().date():
                raise serializers.ValidationError("You have already taken this subscription and it is still active.")
        
        return attrs

    def create(self, validated_data):
        # Calculate `end_date` from `start_date` and `duration_in_days`
        subscription = validated_data['subscription']
        duration_days = subscription.duration_in_days
        start_date = validated_data['start_date']
        end_date = start_date + timedelta(days=duration_days)

        validated_data['end_date'] = end_date

        # Create and return the SubscriptionEnrolled object
        return super().create(validated_data)
    
class NotificationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifications
        fields = ['id', 'user', 'message', 'timestamp']  # Include the necessary fields

class TariffsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariffs
        fields = '__all__'

class CreateOrderSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    currency = serializers.CharField()

class PaymentTransactionSerializer(serializers.ModelSerializer):

    class Meta:
        model = PaymentTransaction
        fields = ["invoice", "payment_id", "order_id", "signature", "amount"]
        
class PerformaInvoiceSerializer(serializers.ModelSerializer):
    subscription = SubscriptionTypeSerializer()
    class Meta:
        model = PerformaInvoice
        fields = ['id', 'user', 'invoice_number', 'company_name', 'company_address', 'gst_number', 'cgst', 'sgst', 'igst', 'total_amount', 'subscription', 'payment_status', 'issue_date', 'due_date']
        extra_kwargs = {
            'issue_date': {'required': False},
            'due_date': {'required': False}
        }
class PerformaInvoiceCreateSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PerformaInvoice
        fields = ['id', 'user', 'invoice_number', 'company_name', 'company_address', 'gst_number', 'cgst', 'sgst', 'igst', 'total_amount', 'subscription', 'payment_status', 'issue_date', 'due_date']
        extra_kwargs = {
            'issue_date': {'required': False},
            'due_date': {'required': False}
        }
        
class StateTimeSlotSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)

    class Meta:
        model = StateTimeSlot
        fields = ["state_name", "peak_hours", "off_peak_hours"]

class CapacitySizingCombinationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapacitySizingCombination
        fields = '__all__'

class OfflinePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflinePayment
        fields = '__all__'