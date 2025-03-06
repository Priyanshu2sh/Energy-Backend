from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import ConsumerMonthAheadDemand, ConsumerMonthAheadDemandDistribution, DayAheadGeneration, MonthAheadGeneration, MonthAheadGenerationDistribution, NextDayPrediction, ConsumerDayAheadDemand, Notifications

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

class DayAheadGenerationSerializer(serializers.ModelSerializer):
    content_type = serializers.SlugRelatedField(
        queryset=ContentType.objects.filter(app_label='energy', model__in=['solarportfolio', 'windportfolio']),
        slug_field='model'
    )

    class Meta:
        model = DayAheadGeneration
        fields = ['id', 'content_type', 'object_id', 'date', 'start_time', 'end_time', 'generation', 'price']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['portfolio'] = f"{instance.content_type.app_label.capitalize()} - {instance.content_type.model.capitalize()} (ID {instance.object_id})"
        return data

class MonthAheadGenerationSerializer(serializers.ModelSerializer):
    content_type = serializers.SlugRelatedField(
        queryset=ContentType.objects.filter(app_label='energy', model__in=['solarportfolio', 'windportfolio']),
        slug_field='model'
    )

    class Meta:
        model = MonthAheadGeneration
        fields = ['id', 'content_type', 'object_id', 'date', 'generation', 'price']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['portfolio'] = f"{instance.content_type.app_label.capitalize()} - {instance.content_type.model.capitalize()} (ID {instance.object_id})"
        return data

class MonthAheadGenerationDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthAheadGenerationDistribution
        fields = ['id', 'month_ahead_generation', 'start_time', 'end_time', 'distributed_generation']
