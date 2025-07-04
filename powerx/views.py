import base64
import pandas as pd
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.utils.timezone import now, timedelta
from django.contrib.contenttypes.models import ContentType
from accounts.models import User
from energy.models import ConsumerRequirements, ESSPortfolio, NationalHoliday, SolarPortfolio, WindPortfolio
from .models import CleanData, ConsumerDayAheadDemand, ConsumerDayAheadDemandDistribution, ConsumerMonthAheadDemand, ConsumerMonthAheadDemandDistribution, DayAheadGeneration, DayAheadGenerationDistribution, ExecutedDayDemandTrade, ExecutedDayGenerationTrade, MonthAheadGeneration, MonthAheadGenerationDistribution, MonthAheadPrediction, NextDayPrediction, Notifications
from .serializers import ConsumerMonthAheadDemandSerializer, DayAheadGenerationSerializer, ExecutedDemandTradeSerializer, ExecutedGenerationTradeSerializer, MonthAheadGenerationSerializer, NextDayPredictionSerializer, ConsumerDayAheadDemandSerializer, NotificationsSerializer
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
from django.utils.dateparse import parse_time
from django.db.models import Avg, Max, Min
from django.db.models import Q
from channels.layers import get_channel_layer
from datetime import date
from django.utils.dateparse import parse_date
from asgiref.sync import async_to_sync
from powerx.AI_Model.model_scheduling import run_predictions, run_month_ahead_model
from powerx.AI_Model.manualdates import process_and_store_data
from rest_framework.decorators import api_view
from django.utils import timezone
from collections import defaultdict, Counter
from accounts.views import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
# Get the logger that is configured in the settings
import logging
traceback_logger = logging.getLogger('django')

logger = logging.getLogger('debug_logger')  # Use the new debug logger

class CleanDataAPI(APIView):
    def post(self, request):
        date = request.data.get("date")
        try:
            process_and_store_data(date)
            return Response({"message": "Data processed and stored successfully."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def run_day_ahead_model(request):
    # Run the MCV model
    run_predictions()
    return Response({"message": "Day Ahead model executed successfully."}, status=status.HTTP_200_OK)

@api_view(['GET'])
def run_month_ahead_model_mcv_mcp(request):
    # Run the MCV model
    run_month_ahead_model()
    return Response({"message": "MCV model executed successfully."}, status=status.HTTP_200_OK)

# Create your views here.
# Get the logged-in user
def get_admin_user(user_id):
        logged_in_user = User.objects.get(id=user_id)
        # Determine the admin user for the logged-in user
        admin_user_id = logged_in_user.parent if logged_in_user.parent else logged_in_user
        # admin_user = User.objects.get(id=admin_user_id)

        return admin_user_id

class NextDayPredictionAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        next_day = now().date() + timedelta(days=1)
        logger.debug(f"Next day date: {next_day}")
        predictions = NextDayPrediction.objects.filter(date__date=next_day).order_by('hour')
        if not predictions.exists():  # If no records found for next day
            # Get last entry's UTC datetime and convert to IST date
            last_entry = NextDayPrediction.objects.latest('date')
            # Find all entries matching last available IST date
            predictions = NextDayPrediction.objects.filter(date=last_entry.date).order_by('hour')

        serializer = NextDayPredictionSerializer(predictions, many=True)
        # Aggregate statistics
        stats = predictions.aggregate(
            max_mcv=Max('mcv_prediction'),
            min_mcv=Min('mcv_prediction'),
            avg_mcv=Avg('mcv_prediction'),
            max_mcp=Max('mcp_prediction'),
            min_mcp=Min('mcp_prediction'),
            avg_mcp=Avg('mcp_prediction')
        )
        # Format response
        response_data = {
            "predictions": [
                {
                    "id": entry["id"],
                    "date": entry["date"],
                    "hour": entry["hour"],
                    "mcv_prediction": round(entry["mcv_prediction"], 2) if entry["mcv_prediction"] is not None else None,
                    "mcp_prediction": round(entry["mcp_prediction"], 2) if entry["mcp_prediction"] is not None else None
                }
                for entry in serializer.data
            ],
            "statistics": {
                "mcv": {
                    "max": stats["max_mcv"],
                    "min": stats["min_mcv"],
                    "avg": round(stats["avg_mcv"], 2) if stats["avg_mcv"] is not None else None
                },
                "mcp": {
                    "max": stats["max_mcp"],
                    "min": stats["min_mcp"],
                    "avg": round(stats["avg_mcp"], 2) if stats["avg_mcp"] is not None else None
                }
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

class MonthAheadPredictionAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Calculate date range: next day to 30 days ahead (inclusive)
        start_date = now().date() + timedelta(days=1)           # e.g. 2025-07-05
        end_date = start_date + timedelta(days=30)              # e.g. 2025-08-04

        logger.debug(f'start date for month ahead prediction - {start_date}')
        logger.debug(f'end date for month ahead prediction - {end_date}')

        # Fetch records in date range
        predictions = MonthAheadPrediction.objects.filter(date__date__range=[start_date, end_date])

        logger.debug(f'data fetched - {predictions}')

        if not predictions.exists():
            # If no data found in target range, fall back to latest 30 days from latest record
            latest_prediction = MonthAheadPrediction.objects.latest('date')
            if latest_prediction:
                last_date = latest_prediction.date
                start_date = last_date - timedelta(days=30)
                predictions = MonthAheadPrediction.objects.filter(date__range=[start_date, last_date])

        # Aggregate daily statistics
        daily_stats = predictions.values('date').annotate(
            avg_mcv=Avg('mcv_prediction'),
            max_mcv=Max('mcv_prediction'),
            min_mcv=Min('mcv_prediction'),
            avg_mcp=Avg('mcp_prediction'),
            max_mcp=Max('mcp_prediction'),
            min_mcp=Min('mcp_prediction'),
        ).order_by('date')

        # Build daily_data list
        daily_data = []
        for record in daily_stats:
            daily_data.append({
                "date": record["date"],
                "mcv_prediction": {
                    "max": record["max_mcv"],
                    "min": record["min_mcv"],
                    "avg": round(record["avg_mcv"], 2) if record["avg_mcv"] is not None else None,
                },
                "mcp_prediction": {
                    "max": record["max_mcp"],
                    "min": record["min_mcp"],
                    "avg": round(record["avg_mcp"], 2) if record["avg_mcp"] is not None else None,
                }
            })

        # Find highest and lowest values based on daily max/min
        mcv_max_values = [
            (d["date"], d["mcv_prediction"]["max"])
            for d in daily_data
            if d["mcv_prediction"]["max"] is not None
        ]

        mcv_min_values = [
            (d["date"], d["mcv_prediction"]["min"])
            for d in daily_data
            if d["mcv_prediction"]["min"] is not None
        ]

        mcp_max_values = [
            (d["date"], d["mcp_prediction"]["max"])
            for d in daily_data
            if d["mcp_prediction"]["max"] is not None
        ]

        mcp_min_values = [
            (d["date"], d["mcp_prediction"]["min"])
            for d in daily_data
            if d["mcp_prediction"]["min"] is not None
        ]

        highest_mcv = max(mcv_max_values, key=lambda x: x[1]) if mcv_max_values else (None, None)
        lowest_mcv = min(mcv_min_values, key=lambda x: x[1]) if mcv_min_values else (None, None)

        highest_mcp = max(mcp_max_values, key=lambda x: x[1]) if mcp_max_values else (None, None)
        lowest_mcp = min(mcp_min_values, key=lambda x: x[1]) if mcp_min_values else (None, None)

        # Compute averages only over valid days
        mcv_avg_values = [
            d["mcv_prediction"]["avg"]
            for d in daily_data
            if d["mcv_prediction"]["avg"] is not None
        ]

        mcp_avg_values = [
            d["mcp_prediction"]["avg"]
            for d in daily_data
            if d["mcp_prediction"]["avg"] is not None
        ]

        overall_avg_mcv = round(sum(mcv_avg_values) / len(mcv_avg_values), 2) if mcv_avg_values else None
        overall_avg_mcp = round(sum(mcp_avg_values) / len(mcp_avg_values), 2) if mcp_avg_values else None

        # Prepare overall stats
        overall_stats = {
            "mcv_prediction": {
                "highest": highest_mcv[1],
                "highest_date": highest_mcv[0],
                "lowest": lowest_mcv[1],
                "lowest_date": lowest_mcv[0],
                "average": overall_avg_mcv,
            },
            "mcp_prediction": {
                "highest": highest_mcp[1],
                "highest_date": highest_mcp[0],
                "lowest": lowest_mcp[1],
                "lowest_date": lowest_mcp[0],
                "average": overall_avg_mcp,
            }
        }

        return Response(
            {
                "daily_data": daily_data,
                "overall_stats": overall_stats
            },
            status=status.HTTP_200_OK
        )

class ConsumerDayAheadDemandAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        
        next_day = datetime.now().date() + timedelta(days=1)

        # Fetch all requirements linked to the user
        requirements = ConsumerRequirements.objects.filter(user=user_id)

        if not requirements.exists():
            return Response({"error": "No requirements found for this user"}, status=status.HTTP_404_NOT_FOUND)

        # Fetch demand records for the next day
        demand_records = ConsumerDayAheadDemand.objects.filter(
            requirement__in=requirements,
            date=next_day
        ).prefetch_related("day_ahead_distributions")

        if not demand_records.exists():
            return Response({"message": "No demand data available for the next day."}, status=status.HTTP_404_NOT_FOUND)

        # Flattened response
        flattened_data = []
        for demand in demand_records:
            for dist in demand.day_ahead_distributions.all():
                flattened_data.append({
                    "id": dist.id,
                    "date": demand.date,
                    "start_time": dist.start_time,
                    "end_time": dist.end_time,
                    "demand": dist.distributed_demand,
                    "price_details": demand.price_details,
                    "status": demand.status,
                    "requirement": demand.requirement.id if demand.requirement else None,
                })

        return Response(flattened_data, status=status.HTTP_200_OK)

    def post(self, request):

        requirement_id = request.data.get("requirement")
        price_details = request.data.get("price_details", {})
        file_data = request.data.get("file")
        demand_data = request.data.get("demand_data", [])

        # Validate requirement
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Requirement not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get tomorrow's date
        tz = timezone.get_current_timezone()
        next_day = timezone.now().astimezone(tz).date() + timedelta(days=1)

        # Check for Sunday
        if next_day.weekday() == 6:
            return Response({"status": "error", "message": "Trade cannot be executed on Sunday."})

        # Check for National Holiday
        if NationalHoliday.objects.filter(date=next_day).exists():
            return Response({"status": "error", "message": "Trade cannot be executed on a national holiday."})

        # Parse input data
        distribution_entries = []
        total_demand = 0

        if file_data:
            try:
                decoded_file = base64.b64decode(file_data)
                file_name = "uploaded_demand_file.xlsx"
                file_content = ContentFile(decoded_file, name=file_name)

                # Read Excel file
                df = pd.read_excel(file_content)

                required_columns = {'Time Interval', 'Demand'}
                if not required_columns.issubset(df.columns):
                    return Response({"error": f"Missing required columns: {required_columns}"}, status=status.HTTP_400_BAD_REQUEST)

                for _, row in df.iterrows():
                    try:
                        start_time_str, end_time_str = row['Time Interval'].split(" - ")
                        start_time = parse_time(start_time_str.strip())
                        end_time = parse_time(end_time_str.strip())
                        demand = float(row['Demand'])

                        total_demand += demand

                        distribution_entries.append({
                            "start_time": start_time,
                            "end_time": end_time,
                            "distributed_demand": demand
                        })
                    except Exception as e:
                        return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        elif demand_data:
            try:
                for entry in demand_data:
                    start_time = parse_time(entry.get("start_time"))
                    end_time = parse_time(entry.get("end_time"))
                    demand = float(entry.get("demand"))

                    if not start_time or not end_time or demand is None:
                        return Response({"error": "Missing start_time, end_time, or demand."}, status=status.HTTP_400_BAD_REQUEST)

                    total_demand += demand

                    distribution_entries.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "distributed_demand": demand
                    })

            except Exception as e:
                return Response({"error": f"Invalid manual data: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"error": "No file or demand data provided."}, status=status.HTTP_400_BAD_REQUEST)

        print(price_details)
        # Create the main day-ahead demand entry
        main_demand = ConsumerDayAheadDemand.objects.create(
            requirement=requirement,
            date=next_day,
            demand=total_demand,
            price_details=price_details
        )

        # Create related 15-minute distribution entries
        distribution_objects = [
            ConsumerDayAheadDemandDistribution(
                day_ahead_demand=main_demand,
                start_time=item["start_time"],
                end_time=item["end_time"],
                distributed_demand=item["distributed_demand"]
            )
            for item in distribution_entries
        ]

        ConsumerDayAheadDemandDistribution.objects.bulk_create(distribution_objects)

        send_notification(requirement.user.id, f'Your trade will execute tomorrow at 10 AM.')

        return Response({"message": "Data uploaded successfully."}, status=status.HTTP_201_CREATED)

    
class ConsumerMonthAheadDemandAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            # Fetch all requirements linked to the user
            requirements = ConsumerRequirements.objects.filter(user=user_id)

            if not requirements.exists():
                return Response({"error": "No requirements found for this user"}, status=status.HTTP_404_NOT_FOUND)

            # Fetch all month-ahead demand records for these requirements
            demands = ConsumerMonthAheadDemand.objects.filter(requirement__in=requirements)

            if not demands.exists():
                return Response({"error": "No demand records found"}, status=status.HTTP_404_NOT_FOUND)

            # Format response
            response_data = [
                {
                    "requirement": demand.requirement.id,
                    "date": demand.date.strftime("%Y-%m-%d"),
                    "demand": demand.demand,
                    "price": demand.price_details  # Already stored as JSON
                }
                for demand in demands
            ]

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        data = request.data
        requirement_id = data.get("requirement")
        date = data.get("date")
        demand = data.get("demand")
        price_details = data.get("price", {})  # JSON: {"Solar": 20, "Non-Solar": 10}

        if not (requirement_id and date and demand and price_details):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure requirement exists
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Invalid requirement ID"}, status=status.HTTP_400_BAD_REQUEST)

        date = parse_date(date)
        # Check if it's Sunday
        if date.weekday() == 6:
            return Response({
                "status": "error",
                "message": "Trade cannot be executed on Sunday."
            })

        # Check if it's a National Holiday
        if NationalHoliday.objects.filter(date=date).exists():
            return Response({
                "status": "error",
                "message": "Trade cannot be executed on a national holiday."
            })

        # Check if demand entry already exists for requirement and date
        demand_record, created = ConsumerMonthAheadDemand.objects.get_or_create(
            requirement=requirement,
            date=date,
            defaults={"demand": demand, "price_details": price_details}
        )

        # If existing, update demand and prices
        if not created:
            demand_record.demand = demand
            demand_record.price_details = price_details
            demand_record.save()

        return Response({"message": "Data added successfully"}, status=status.HTTP_201_CREATED)

    def put(self, request):
        data = request.data
        requirement = data.get("requirement")
        file_data = data.get("file")

        try:
            month_ahead_demand = ConsumerMonthAheadDemand.objects.get(requirement=requirement)
        except ConsumerMonthAheadDemand.DoesNotExist:
            return Response({"error": "Month ahead demand not found."}, status=status.HTTP_404_NOT_FOUND)

        data_list = []

        if not file_data:
            return Response({"error": "No file data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Process Excel File
        try:
            decoded_file = base64.b64decode(file_data)
            file_name = "uploaded_demand_file.xlsx"
            file_content = ContentFile(decoded_file, name=file_name)
            # Read Excel file
            df = pd.read_excel(file_content)
            # Required columns in the Excel file
            required_columns = {'Time Interval', 'Demand'}
            if not required_columns.issubset(df.columns):
                return Response({"error": f"Missing required columns: {required_columns}"}, status=status.HTTP_400_BAD_REQUEST)
            # Extract data from Excel
            for _, row in df.iterrows():
                try:
                    start_time, end_time = row['Time Interval'].split(" - ")
                    demand = int(row['Demand'])
                    # Create an entry
                    data_list.append(ConsumerMonthAheadDemandDistribution(
                        month_ahead_demand=month_ahead_demand,
                        start_time=parse_time(start_time),
                        end_time=parse_time(end_time),
                        distributed_demand=demand,
                    ))
                except Exception as e:
                    return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            # Bulk insert the data
            ConsumerMonthAheadDemandDistribution.objects.bulk_create(data_list)
            return Response({"message": "File uploaded successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

def send_notification(user_id, message):
    """
    Ensures notification is created and triggers WebSocket update only for new notifications.
    """
    notification, created = Notifications.objects.get_or_create(
        user_id=user_id,
        message=message,
        defaults={"is_read": False}
    )

    # Only trigger WebSocket update if a new notification was created
    if created:
        unread_count = Notifications.objects.filter(user_id=user_id, is_read=False).count()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_notification",
                "unread_count": unread_count,
            }
        )

    return notification
        
class NotificationsAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            user_id = user.id
            # Fetch notifications based on user_id
            notifications = Notifications.objects.filter(user_id=user_id).order_by('-timestamp')
            # Serialize the notifications data
            serializer = NotificationsSerializer(notifications, many=True)

            # Mark notifications as read
            Notifications.objects.filter(user_id=user_id, is_read=False).update(is_read=True)

            # Send real-time update to WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {
                    "type": "mark_notifications_read",
                    "unread_count": 0,
                }
            )
            
            # Return the response with serialized data
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Notifications.DoesNotExist:
            # Handle the case where no notifications are found
            return Response({"message": "No notifications found for this user."}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            # Handle any other exceptions
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class DayAheadGenerationAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        next_day = datetime.now().date() + timedelta(days=1)

        solar_content_type = ContentType.objects.get_for_model(SolarPortfolio)
        wind_content_type = ContentType.objects.get_for_model(WindPortfolio)

        solar_portfolios = SolarPortfolio.objects.filter(user=user_id)
        wind_portfolios = WindPortfolio.objects.filter(user=user_id)

        if not solar_portfolios.exists() and not wind_portfolios.exists():
            return Response({"error": "No portfolios found for this user"}, status=status.HTTP_404_NOT_FOUND)

        generation_records = DayAheadGeneration.objects.filter(
            (
                Q(content_type=solar_content_type, object_id__in=solar_portfolios.values_list('id', flat=True)) |
                Q(content_type=wind_content_type, object_id__in=wind_portfolios.values_list('id', flat=True))
            ),
            date=next_day
        ).prefetch_related('day_generation_distributions', 'content_type')

        if not generation_records.exists():
            return Response({"message": "No generation data available for the next day."}, status=status.HTTP_404_NOT_FOUND)

        final_data = []

        for gen in generation_records:
            for dist in gen.day_generation_distributions.all():
                final_data.append({
                    "id": dist.id,
                    "content_type": gen.content_type.model,
                    "object_id": gen.object_id,
                    "date": gen.date,
                    "start_time": dist.start_time,
                    "end_time": dist.end_time,
                    "generation": dist.distributed_generation,
                    "price": gen.price,
                    "portfolio": f"Energy - {gen.content_type.model.capitalize()} (ID {gen.object_id})"
                })

        return Response(final_data, status=status.HTTP_200_OK)

    
    def post(self, request):
        model = request.data.get("model")
        object_id = request.data.get("object_id")
        price = request.data.get("price")
        file_data = request.data.get("file")
        generation_data = request.data.get("generation_data", [])

        try:
            content_type = ContentType.objects.get(app_label='energy', model=model)
        except (ValueError, ContentType.DoesNotExist):
            return Response({"error": "Invalid content_type format or not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            portfolio = content_type.get_object_for_this_type(id=object_id)
        except Exception:
            return Response({"error": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)

        tz = timezone.get_current_timezone()
        next_day = timezone.now().astimezone(tz).date() + timedelta(days=1)

        if next_day.weekday() == 6:
            return Response({"status": "error", "message": "Trade cannot be executed on Sunday."})

        if NationalHoliday.objects.filter(date=next_day).exists():
            return Response({"status": "error", "message": "Trade cannot be executed on a national holiday."})

        distribution_list = []

        try:
            if file_data:
                decoded_file = base64.b64decode(file_data)
                file_name = "uploaded_generation_file.xlsx"
                file_content = ContentFile(decoded_file, name=file_name)
                df = pd.read_excel(file_content)

                required_columns = {'Time Interval', 'Generation'}
                if not required_columns.issubset(df.columns):
                    return Response({"error": f"Missing required columns: {required_columns}"}, status=status.HTTP_400_BAD_REQUEST)

                for _, row in df.iterrows():
                    start_time_str, end_time_str = row['Time Interval'].split(" - ")
                    generation = float(row['Generation'])
                    distribution_list.append({
                        "start_time": parse_time(start_time_str),
                        "end_time": parse_time(end_time_str),
                        "distributed_generation": generation
                    })

            elif generation_data:
                for entry in generation_data:
                    start_time = entry.get("start_time")
                    end_time = entry.get("end_time")
                    generation = entry.get("generation")

                    if not start_time or not end_time or generation is None:
                        return Response({"error": "Missing start_time, end_time, or generation."}, status=status.HTTP_400_BAD_REQUEST)

                    distribution_list.append({
                        "start_time": parse_time(start_time),
                        "end_time": parse_time(end_time),
                        "distributed_generation": float(generation)
                    })

            else:
                return Response({"error": "No file or generation data provided."}, status=status.HTTP_400_BAD_REQUEST)

            total_generation = sum(d["distributed_generation"] for d in distribution_list)

            # Create parent record
            day_gen = DayAheadGeneration.objects.create(
                content_type=content_type,
                object_id=object_id,
                date=next_day,
                generation=total_generation,
                price=price
            )

            # Create distribution entries
            distributions = [
                DayAheadGenerationDistribution(
                    day_ahead_generation=day_gen,
                    start_time=dist["start_time"],
                    end_time=dist["end_time"],
                    distributed_generation=dist["distributed_generation"]
                ) for dist in distribution_list
            ]
            DayAheadGenerationDistribution.objects.bulk_create(distributions)

            return Response({"message": "Day Ahead Generation data uploaded successfully."}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    
class MonthAheadGenerationAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            # Fetch content types for Solar and Wind
            solar_content_type = ContentType.objects.get_for_model(SolarPortfolio)
            wind_content_type = ContentType.objects.get_for_model(WindPortfolio)

            # Fetch all portfolios linked to the user
            solar_portfolios = SolarPortfolio.objects.filter(user=user_id)
            wind_portfolios = WindPortfolio.objects.filter(user=user_id)

            if not solar_portfolios.exists() and not wind_portfolios.exists():
                return Response({"error": "No portfolios found for this user"}, status=status.HTTP_404_NOT_FOUND)

            # Fetch month-ahead generation records for these portfolios
            generation_records = MonthAheadGeneration.objects.filter(
                (Q(content_type=solar_content_type) & Q(object_id__in=solar_portfolios.values_list('id', flat=True))) |
                (Q(content_type=wind_content_type) & Q(object_id__in=wind_portfolios.values_list('id', flat=True)))
            )

            if not generation_records.exists():
                return Response({"error": "No generation records found"}, status=status.HTTP_404_NOT_FOUND)

            # Serialize response
            serializer = MonthAheadGenerationSerializer(generation_records, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        data = request.data
        portfolio_id = data.get("portfolio_id")  # Object ID (Solar/Wind)
        portfolio_type = data.get("portfolio_type")  # "solar" or "non_solar"
        date = data.get("date")
        generation = data.get("generation")
        price = data.get("price")

        if not (portfolio_id and portfolio_type and date and generation and price):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        # Get the correct content type
        if portfolio_type.lower() == "solar":
            try:
                content_type = ContentType.objects.get_for_model(SolarPortfolio)
                portfolio = SolarPortfolio.objects.get(id=portfolio_id)
            except SolarPortfolio.DoesNotExist:
                return Response({"error": "Invalid SolarPortfolio ID"}, status=status.HTTP_400_BAD_REQUEST)
        elif portfolio_type.lower() == "non_solar":
            try:
                content_type = ContentType.objects.get_for_model(WindPortfolio)
                portfolio = WindPortfolio.objects.get(id=portfolio_id)
            except WindPortfolio.DoesNotExist:
                return Response({"error": "Invalid WindPortfolio ID"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Invalid portfolio type"}, status=status.HTTP_400_BAD_REQUEST)

        date = parse_date(date)
        # Check if it's Sunday
        if date.weekday() == 6:
            return Response({
                "status": "error",
                "message": "Trade cannot be executed on Sunday."
            })

        # Check if it's a National Holiday
        if NationalHoliday.objects.filter(date=date).exists():
            return Response({
                "status": "error",
                "message": "Trade cannot be executed on a national holiday."
            })

        # Check if generation entry already exists
        generation_record, created = MonthAheadGeneration.objects.get_or_create(
            content_type=content_type,
            object_id=portfolio.id,
            date=date,
            defaults={"generation": generation, "price": price}
        )

        # If existing, update generation and price
        if not created:
            generation_record.generation = generation
            generation_record.price = price
            generation_record.save()

        # If it's a new generation entry, create 15-minute distributions
        if created:
            distributions = []
            start_time = datetime.strptime("00:00", "%H:%M")
            generation_per_slot = generation / 96  # 96 slots (15 min each)

            for i in range(96):
                slot_start = (start_time + timedelta(minutes=15 * i)).time()
                slot_end = (start_time + timedelta(minutes=15 * (i + 1))).time()

                distributions.append(
                    MonthAheadGenerationDistribution(
                        month_ahead_generation=generation_record,
                        start_time=slot_start,
                        end_time=slot_end,
                        distributed_generation=generation_per_slot
                    )
                )

            # Bulk insert for efficiency
            MonthAheadGenerationDistribution.objects.bulk_create(distributions)

        return Response({"message": "Data processed successfully"}, status=status.HTTP_201_CREATED)

    def put(self, request):
        data = request.data
        id = data.get("id")
        file_data = data.get("file")

        try:
            month_ahead_generation = MonthAheadGeneration.objects.get(id=id)
        except MonthAheadGeneration.DoesNotExist:
            return Response({"error": "Month ahead generation not found."}, status=status.HTTP_404_NOT_FOUND)

        data_list = []

        if not file_data:
            return Response({"error": "No file data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Process Excel File
        try:
            decoded_file = base64.b64decode(file_data)
            file_name = "uploaded_generation_file.xlsx"
            file_content = ContentFile(decoded_file, name=file_name)
            # Read Excel file
            df = pd.read_excel(file_content)
            # Required columns in the Excel file
            required_columns = {'Time Interval', 'Generation'}
            if not required_columns.issubset(df.columns):
                return Response({"error": f"Missing required columns: {required_columns}"}, status=status.HTTP_400_BAD_REQUEST)
            # Extract data from Excel
            for _, row in df.iterrows():
                try:
                    start_time, end_time = row['Time Interval'].split(" - ")
                    distributed_generation = int(row['Generation'])
                    # Create an entry
                    data_list.append(MonthAheadGenerationDistribution(
                        month_ahead_generation=month_ahead_generation,
                        start_time=parse_time(start_time),
                        end_time=parse_time(end_time),
                        distributed_generation=distributed_generation,
                    ))
                except Exception as e:
                    return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            # Bulk insert the data
            MonthAheadGenerationDistribution.objects.bulk_create(data_list)
            return Response({"message": "File uploaded successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

class ConsumerDashboardAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        requirements = ConsumerRequirements.objects.filter(user=user_id).values()
        return Response(list(requirements), status=status.HTTP_200_OK)

class GeneratorDashboardAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        solar_portfolios = SolarPortfolio.objects.filter(user=user_id).values()
        wind_portfolios = WindPortfolio.objects.filter(user=user_id).values()
        ess_portfolios = ESSPortfolio.objects.filter(user=user_id).values()
        return Response({"solar": list(solar_portfolios), "wind": list(wind_portfolios), "ess": list(ess_portfolios)}, status=status.HTTP_200_OK)

class ModelStatisticsAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()

        # Get today's data from both models
        next_day_data = NextDayPrediction.objects.filter(date=today)
        clean_data = CleanData.objects.filter(date=today)

        if not (next_day_data.exists() and clean_data.exists()):  # If today's data is missing in any model
            # Find the last available date in both models
            last_clean_date = CleanData.objects.aggregate(max_date=Max('date'))['max_date']
            last_next_day_date = NextDayPrediction.objects.aggregate(max_date=Max('date'))['max_date']

            # Determine the common latest date
            if last_clean_date and last_next_day_date:
                common_latest_date = min(last_clean_date, last_next_day_date)
            else:
                common_latest_date = last_clean_date or last_next_day_date  # Use whichever is available

            # Fetch data from the common latest date
            next_day_data = NextDayPrediction.objects.filter(date=common_latest_date)
            clean_data = CleanData.objects.filter(date=common_latest_date)

        # Prepare response
        response_data = {
            "date": next_day_data.first().date.date() if next_day_data.exists() else clean_data.first().date.date(),
            "next_day_predictions": [
                {
                    "hour": entry.hour,
                    "mcv_prediction": round(entry.mcv_prediction, 2) if entry.mcv_prediction else None,
                    "mcp_prediction": round(entry.mcp_prediction, 2) if entry.mcp_prediction else None
                }
                for entry in next_day_data
            ],
            "clean_data": [
                {
                    "hour": entry.hour,
                    "mcv_total": entry.mcv_total,
                    "mcp": entry.mcp
                }
                for entry in clean_data
            ]
        }

        return Response(response_data)

class ModelStatisticsMonthAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()

        # Find the last available date in both models
        last_clean_date = CleanData.objects.aggregate(max_date=Max('date'))['max_date']
        last_month_date = MonthAheadPrediction.objects.aggregate(max_date=Max('date'))['max_date']

        # Determine the common latest date
        if last_clean_date and last_month_date:
            common_latest_date = min(last_clean_date, last_month_date)
        else:
            common_latest_date = last_clean_date or last_month_date  # Use whichever is available

        if not common_latest_date:
            return Response({"error": "No data available"}, status=404)

        # Calculate the start date for the last 30 days
        start_date = common_latest_date - timedelta(days=30)

        # Fetch data for the last 30 days
        month_data = MonthAheadPrediction.objects.filter(date__range=[start_date, common_latest_date])
        clean_data = CleanData.objects.filter(date__range=[start_date, common_latest_date])

        # Prepare response
        response_data = {
            "start_date": start_date.date(),
            "end_date": common_latest_date.date(),
            "month_predictions": [
                {
                    "date": entry.date.date(),
                    "hour": entry.hour,
                    "mcv_prediction": round(entry.mcv_prediction, 2) if entry.mcv_prediction else None,
                    "mcp_prediction": round(entry.mcp_prediction, 2) if entry.mcp_prediction else None
                }
                for entry in month_data
            ],
            "clean_data": [
                {
                    "date": entry.date.date(),
                    "hour": entry.hour,
                    "mcv_total": entry.mcv_total,
                    "mcp": entry.mcp
                }
                for entry in clean_data
            ]
        }

        return Response(response_data)
    
class TrackDemandStatusAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        result = []

        # === Group Day Ahead by Date ===
        grouped_day_ahead = defaultdict(list)
        day_ahead = ConsumerDayAheadDemand.objects.filter(requirement__user=user)

        for entry in day_ahead:
            date_key = entry.date.strftime("%d-%m-%Y")
            grouped_day_ahead[date_key].append(entry)

        for date_key, entries in grouped_day_ahead.items():
            statuses = [entry.status.lower() for entry in entries]
            status_counts = Counter(statuses)

            # Decide on status
            if len(status_counts) == 1:
                status_to_show = statuses[0]
            else:
                status_to_show = "conflict"  # or use: Counter(statuses).most_common(1)[0][0]

            avg_demand = sum(entry.demand for entry in entries) / len(entries)
            first_req = entries[0].requirement

            result.append({
                "demand_date": date_key,
                "average_demand": round(avg_demand, 2),
                "status": status_to_show,
                "type": "Day Ahead",
                "consumption_unit_details": {
                    "state": first_req.state,
                    "industry": first_req.industry,
                    "contracted_demand": first_req.contracted_demand,
                    "consumption_unit": first_req.consumption_unit
                }
            })

        # === Add Month Ahead Demands (No Grouping) ===
        month_ahead = ConsumerMonthAheadDemand.objects.filter(requirement__user=user)
        for entry in month_ahead:
            date_key = entry.date.strftime("%d-%m-%Y")
            req = entry.requirement

            result.append({
                "demand_date": date_key,
                "average_demand": entry.demand,
                "status": entry.status.lower(),
                "type": "Month Ahead",
                "consumption_unit_details": {
                    "state": req.state,
                    "industry": req.industry,
                    "contracted_demand": req.contracted_demand,
                    "consumption_unit": req.consumption_unit
                }
            })

        # Sort by date
        result.sort(key=lambda x: datetime.strptime(x['demand_date'], "%d-%m-%Y"))

        return Response(result, status=status.HTTP_200_OK)

class TrackGenerationStatusAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        result = []

        # Get all portfolios of the user
        solar_portfolios = SolarPortfolio.objects.filter(user=user)
        wind_portfolios = WindPortfolio.objects.filter(user=user)

        # Get content types
        solar_ct = ContentType.objects.get_for_model(SolarPortfolio)
        wind_ct = ContentType.objects.get_for_model(WindPortfolio)

        # ===== Grouped Day Ahead Generation =====
        grouped_day_ahead = defaultdict(list)
        day_ahead = DayAheadGeneration.objects.filter(
            Q(content_type=solar_ct, object_id__in=solar_portfolios.values_list('id', flat=True)) |
            Q(content_type=wind_ct, object_id__in=wind_portfolios.values_list('id', flat=True))
        )

        for entry in day_ahead:
            date_key = entry.date.strftime("%d-%m-%Y")
            portfolio = entry.portfolio
            technology = "solar" if isinstance(portfolio, SolarPortfolio) else "wind"
            grouped_day_ahead[date_key].append({
                "generation": entry.generation,
                "price": entry.price,
                "status": entry.status.lower(),
                "technology": technology,
                "state": portfolio.state,
                "site_name": portfolio.site_name,
                "connectivity": portfolio.connectivity,
                "available_capacity": portfolio.available_capacity
            })

        for date_key, entries in grouped_day_ahead.items():
            avg_generation = sum(e['generation'] for e in entries) / len(entries)
            avg_price = sum(e['price'] for e in entries) / len(entries)
            most_common_status = Counter(e['status'] for e in entries).most_common(1)[0][0]
            first = entries[0]

            result.append({
                "generation_date": date_key,
                "generation": round(avg_generation, 2),
                "price": round(avg_price, 2),
                "status": most_common_status,
                "type": "Day Ahead",
                "portfolio_details": {
                    "technology": first['technology'],
                    "state": first['state'],
                    "connectivity": first['connectivity'],
                    "available_capacity": first['available_capacity']
                }
            })

        # ===== Ungrouped Month Ahead Generation =====
        month_ahead = MonthAheadGeneration.objects.filter(
            Q(content_type=solar_ct, object_id__in=solar_portfolios.values_list('id', flat=True)) |
            Q(content_type=wind_ct, object_id__in=wind_portfolios.values_list('id', flat=True))
        )

        for entry in month_ahead:
            date_key = entry.date.strftime("%d-%m-%Y")
            portfolio = entry.portfolio
            technology = "solar" if isinstance(portfolio, SolarPortfolio) else "wind"

            result.append({
                "generation_date": date_key,
                "generation": round(entry.generation, 2),
                "price": round(entry.price, 2),
                "status": entry.status.lower(),
                "type": "Month Ahead",
                "portfolio_details": {
                    "technology": technology,
                    "state": portfolio.state,
                    "connectivity": portfolio.connectivity,
                    "available_capacity": portfolio.available_capacity
                }
            })

        # Sort by date
        result.sort(key=lambda x: datetime.strptime(x['generation_date'], "%d-%m-%Y"))

        return Response(result, status=status.HTTP_200_OK)

class ExecutedDayAheadDemandTrade(APIView):
    def get(self, request, user_id):
        # Get all requirements for the user
        user_requirements = ConsumerRequirements.objects.filter(user=user_id)

        if not user_requirements.exists():
            return Response({"error": "No requirements found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Get all day-ahead demands for those requirements
        user_demands = ConsumerDayAheadDemand.objects.filter(requirement__in=user_requirements)

        if not user_demands.exists():
            return Response({"error": "No demand records found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Get all executed trades linked to those demands
        executed_trades = ExecutedDayDemandTrade.objects.filter(demand__in=user_demands)

        if not executed_trades.exists():
            return Response({"message": "No executed trades found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Serialize and return
        serializer = ExecutedDemandTradeSerializer(executed_trades, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ExecutedDayAheadGenerationTrade(APIView):
    def get(self, request, user_id):
        # Get content types for Solar and Wind portfolio
        solar_type = ContentType.objects.get(app_label='energy', model='solarportfolio')
        wind_type = ContentType.objects.get(app_label='energy', model='windportfolio')

        # Get all generation records linked to this user (via Solar or Wind portfolios)
        generation_qs = DayAheadGeneration.objects.filter(
            content_type__in=[solar_type, wind_type]
        ).select_related('content_type')

        # Filter only those where the portfolio.user == user_id
        generation_for_user = []
        for gen in generation_qs:
            portfolio = gen.portfolio
            if hasattr(portfolio, 'user') and portfolio.user.id == int(user_id):
                generation_for_user.append(gen.id)

        if not generation_for_user:
            return Response({"error": "No generation records found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Fetch executed generation trades
        executed_trades = ExecutedDayGenerationTrade.objects.filter(generation_id__in=generation_for_user)

        if not executed_trades.exists():
            return Response({"message": "No executed generation trades found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Serialize and return
        serializer = ExecutedGenerationTradeSerializer(executed_trades, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)