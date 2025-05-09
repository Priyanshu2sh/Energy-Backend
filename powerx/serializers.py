from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import ConsumerDayAheadDemandDistribution, ConsumerMonthAheadDemand, ConsumerMonthAheadDemandDistribution, DayAheadGeneration, DayAheadGenerationDistribution, ExecutedDayDemandTrade, ExecutedDayGenerationTrade, MonthAheadGeneration, MonthAheadGenerationDistribution, NextDayPrediction, ConsumerDayAheadDemand, Notifications

class NextDayPredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NextDayPrediction
        fields = '__all__'

class ConsumerDayAheadDemandDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerDayAheadDemandDistribution
        fields = ['start_time', 'end_time', 'distributed_demand']
    
class ConsumerDayAheadDemandSerializer(serializers.ModelSerializer):
    day_ahead_distributions = ConsumerDayAheadDemandDistributionSerializer(many=True, read_only=True)

    class Meta:
        model = ConsumerDayAheadDemand
        fields = ['id', 'requirement', 'date', 'demand', 'price_details', 'status', 'day_ahead_distributions']


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

class DayAheadGenerationDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DayAheadGenerationDistribution
        fields = ['start_time', 'end_time', 'distributed_generation']


class DayAheadGenerationSerializer(serializers.ModelSerializer):
    portfolio = serializers.SerializerMethodField()
    content_type = serializers.CharField(source='content_type.model')  # Lowercase model name
    distributions = DayAheadGenerationDistributionSerializer(source='day_generation_distributions', many=True)

    class Meta:
        model = DayAheadGeneration
        fields = [
            'id', 'content_type', 'object_id', 'date',
            'generation', 'price', 'portfolio', 'distributions'
        ]

    def get_portfolio(self, obj):
        return f"{obj.content_type.app_label.capitalize()} - {obj.content_type.model.capitalize()} (ID {obj.object_id})"


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

class ExecutedDemandTradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutedDayDemandTrade
        fields = '__all__'

class ExecutedGenerationTradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutedDayGenerationTrade
        fields = '__all__'