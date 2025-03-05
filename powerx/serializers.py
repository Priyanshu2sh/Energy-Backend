from rest_framework import serializers
from .models import ConsumerMonthAheadDemand, ConsumerMonthAheadDemandDistribution, NextDayPrediction, ConsumerDayAheadDemand, Notifications

class NextDayPredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NextDayPrediction
        fields = '__all__'

class ConsumerDayAheadDemandSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerDayAheadDemand
        fields = '__all__'

class NotificationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifications
        fields = ['id', 'user', 'message', 'timestamp']  # Include the necessary fields

class ConsumerMonthAheadDemandSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerMonthAheadDemand
        fields = '__all__'

class ConsumerMonthAheadDemandDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerMonthAheadDemandDistribution
        fields = '__all__'
