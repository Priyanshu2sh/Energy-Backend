import base64
import pandas as pd
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.utils.timezone import now, timedelta
from django.contrib.contenttypes.models import ContentType
from accounts.models import User
from energy.models import ConsumerRequirements, ESSPortfolio, SolarPortfolio, WindPortfolio
from .models import CleanData, ConsumerDayAheadDemand, ConsumerMonthAheadDemand, ConsumerMonthAheadDemandDistribution, DayAheadGeneration, MonthAheadGeneration, MonthAheadGenerationDistribution, MonthAheadPrediction, NextDayPrediction, Notifications
from .serializers import ConsumerMonthAheadDemandSerializer, DayAheadGenerationSerializer, MonthAheadGenerationSerializer, NextDayPredictionSerializer, ConsumerDayAheadDemandSerializer, NotificationsSerializer
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
from django.utils.dateparse import parse_time
from django.db.models import Avg, Max, Min
from django.db.models import Q
from channels.layers import get_channel_layer
from datetime import date
from asgiref.sync import async_to_sync
from powerx.AI_Model.model_scheduling import run_predictions, run_month_ahead_model
from powerx.AI_Model.manualdates import process_and_store_data
from rest_framework.decorators import api_view
from django.utils import timezone

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

    def get(self, request):
        next_day = now().date() + timedelta(days=1)
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
    def get(self, request):
        start_date = now().date() + timedelta(days=1)  # Next day
        end_date = start_date + timedelta(days=29)  # Next 30 days

        # Get data for the next 30 days
        predictions = MonthAheadPrediction.objects.filter(date__date__range=[start_date, end_date])

        if not predictions.exists():  # If no records found for the next 30 days
            latest_prediction = MonthAheadPrediction.objects.latest('date')  # Get latest record
            if latest_prediction:
                last_date = latest_prediction.date
                start_date = last_date - timedelta(days=30)  # Get 30 days before the latest date
                predictions = MonthAheadPrediction.objects.filter(date__range=[start_date, last_date])

        # Aggregate per day
        daily_stats = predictions.values('date').annotate(
            avg_mcv=Avg('mcv_prediction'),
            max_mcv=Max('mcv_prediction'),
            min_mcv=Min('mcv_prediction'),
            avg_mcp=Avg('mcp_prediction'),
            max_mcp=Max('mcp_prediction'),
            min_mcp=Min('mcp_prediction'),
        ).order_by('date')

        # Prepare daily aggregated data
        daily_data = []
        for record in daily_stats:
            daily_data.append({
                "date": record["date"],
                "mcv_prediction": {
                    "max": record["max_mcv"],
                    "min": record["min_mcv"],
                    "avg": round(record["avg_mcv"], 2) if record["avg_mcv"] else None,
                },
                "mcp_prediction": {
                    "max": record["max_mcp"],
                    "min": record["min_mcp"],
                    "avg": round(record["avg_mcp"], 2) if record["avg_mcp"] else None,
                }
            })

        # Find overall highest, lowest, and average across 30 days
        overall_stats = {
            "mcv_prediction": {
                "highest": max(d["mcv_prediction"]["avg"] for d in daily_data if d["mcv_prediction"]["avg"] is not None),
                "lowest": min(d["mcv_prediction"]["avg"] for d in daily_data if d["mcv_prediction"]["avg"] is not None),
                "average": round(sum(d["mcv_prediction"]["avg"] for d in daily_data if d["mcv_prediction"]["avg"] is not None) / len(daily_data), 2),
            },
            "mcp_prediction": {
                "highest": max(d["mcp_prediction"]["avg"] for d in daily_data if d["mcp_prediction"]["avg"] is not None),
                "lowest": min(d["mcp_prediction"]["avg"] for d in daily_data if d["mcp_prediction"]["avg"] is not None),
                "average": round(sum(d["mcp_prediction"]["avg"] for d in daily_data if d["mcp_prediction"]["avg"] is not None) / len(daily_data), 2),
            }
        }

        return Response({"daily_data": daily_data, "overall_stats": overall_stats}, status=status.HTTP_200_OK)

class ConsumerDayAheadDemandAPI(APIView):

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
        ).order_by("start_time")

        if not demand_records.exists():
            return Response({"message": "No demand data available for the next day."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConsumerDayAheadDemandSerializer(demand_records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        next_day = datetime.now().date() + timedelta(days=1)
        data_list = []

        if file_data:
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
                        data_list.append(ConsumerDayAheadDemand(
                            requirement=requirement,
                            date=next_day,
                            start_time=parse_time(start_time),
                            end_time=parse_time(end_time),
                            demand=demand,
                            price_details=price_details
                        ))

                    except Exception as e:
                        return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        elif demand_data:
            # Process Manual JSON Data
            try:
                for entry in demand_data:
                    start_time = entry.get("start_time")
                    end_time = entry.get("end_time")
                    demand = entry.get("demand")

                    # Validate time format
                    if not start_time or not end_time or not demand:
                        return Response({"error": "Missing start_time, end_time, or demand."}, status=status.HTTP_400_BAD_REQUEST)

                    data_list.append(ConsumerDayAheadDemand(
                        requirement=requirement,
                        date=next_day,
                        start_time=parse_time(start_time),
                        end_time=parse_time(end_time),
                        demand=demand,
                        price_details=price_details
                    ))

            except Exception as e:
                return Response({"error": f"Invalid manual data: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"error": "No file or demand data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk insert the data
        ConsumerDayAheadDemand.objects.bulk_create(data_list)
        send_notification(requirement.user.id, f'Your trade will execute tomorrow at 10 AM.')
        return Response({"message": "Data uploaded successfully"}, status=status.HTTP_201_CREATED)
    
class ConsumerMonthAheadDemandAPI(APIView):

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

        # If it's a new demand entry, create 15-minute distributions
        if created:
            distributions = []
            start_time = datetime.strptime("00:00", "%H:%M")
            demand_per_slot = demand / 96  # 96 slots (15 min each)

            for i in range(96):
                slot_start = (start_time + timedelta(minutes=15 * i)).time()
                slot_end = (start_time + timedelta(minutes=15 * (i + 1))).time()

                distributions.append(
                    ConsumerMonthAheadDemandDistribution(
                        month_ahead_demand=demand_record,
                        start_time=slot_start,
                        end_time=slot_end,
                        distributed_demand=demand_per_slot
                    )
                )

            # Bulk insert for efficiency
            ConsumerMonthAheadDemandDistribution.objects.bulk_create(distributions)

        return Response({"message": "Data added successfully"}, status=status.HTTP_201_CREATED)

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

    def get(self, request, user_id):
        next_day = datetime.now().date() + timedelta(days=1)

        solar_content_type = ContentType.objects.get_for_model(SolarPortfolio)
        wind_content_type = ContentType.objects.get_for_model(WindPortfolio)

        # Fetch all portfolios linked to the user
        solar_portfolios = SolarPortfolio.objects.filter(user=user_id)
        wind_portfolios = WindPortfolio.objects.filter(user=user_id)

        
        if not solar_portfolios.exists() and not wind_portfolios.exists():
            return Response({"error": "No portfolios found for this user"}, status=status.HTTP_404_NOT_FOUND)

        # Fetch generation records for the next day
        generation_records = DayAheadGeneration.objects.filter(
            (
                Q(content_type=solar_content_type, object_id__in=solar_portfolios.values_list('id', flat=True)) |
                Q(content_type=wind_content_type, object_id__in=wind_portfolios.values_list('id', flat=True))
            ),
            date=next_day
        ).order_by("start_time")

        if not generation_records.exists():
            return Response({"message": "No generation data available for the next day."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DayAheadGenerationSerializer(generation_records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    
    def post(self, request):
        model = request.data.get("model")
        object_id = request.data.get("object_id")
        price = request.data.get("price")
        file_data = request.data.get("file")
        generation_data = request.data.get("generation_data", [])

        # Validate content type
        try:
            content_type = ContentType.objects.get(app_label='energy', model=model)
        except (ValueError, ContentType.DoesNotExist):
            return Response({"error": "Invalid content_type format or not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate object_id existence
        try:
            portfolio = content_type.get_object_for_this_type(id=object_id)
        except Exception:
            return Response({"error": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get tomorrow's date
        next_day = datetime.now().date() + timedelta(days=1)
        data_list = []

        if file_data:
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
                        generation = int(row['Generation'])

                        # Create an entry
                        data_list.append(DayAheadGeneration(
                            content_type=content_type,
                            object_id=object_id,
                            date=next_day,
                            start_time=parse_time(start_time),
                            end_time=parse_time(end_time),
                            generation=generation,
                            price=price
                        ))

                    except Exception as e:
                        return Response({"error": f"Data processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        elif generation_data:
            # Process Manual JSON Data
            try:
                for entry in generation_data:
                    start_time = entry.get("start_time")
                    end_time = entry.get("end_time")
                    generation = entry.get("generation")

                    # Validate required fields
                    if not start_time or not end_time or generation is None:
                        return Response({"error": "Missing start_time, end_time, or generation."}, status=status.HTTP_400_BAD_REQUEST)

                    data_list.append(DayAheadGeneration(
                        content_type=content_type,
                        object_id=object_id,
                        date=next_day,
                        start_time=parse_time(start_time),
                        end_time=parse_time(end_time),
                        generation=generation,
                        price=price
                    ))

            except Exception as e:
                return Response({"error": f"Invalid manual data: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"error": "No file or generation data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk insert the data
        DayAheadGeneration.objects.bulk_create(data_list)

        return Response({"message": "Data uploaded successfully"}, status=status.HTTP_201_CREATED)
    
class MonthAheadGenerationAPI(APIView):

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
        portfolio_type = data.get("portfolio_type")  # "solar" or "wind"
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
        elif portfolio_type.lower() == "wind":
            try:
                content_type = ContentType.objects.get_for_model(WindPortfolio)
                portfolio = WindPortfolio.objects.get(id=portfolio_id)
            except WindPortfolio.DoesNotExist:
                return Response({"error": "Invalid WindPortfolio ID"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Invalid portfolio type"}, status=status.HTTP_400_BAD_REQUEST)

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

class ConsumerDashboardAPI(APIView):
    def get(self, request, user_id):
        requirements = ConsumerRequirements.objects.filter(user=user_id).values()
        return Response(list(requirements), status=status.HTTP_200_OK)

class GeneratorDashboardAPI(APIView):
    def get(self, request, user_id):
        solar_portfolios = SolarPortfolio.objects.filter(user=user_id).values()
        wind_portfolios = WindPortfolio.objects.filter(user=user_id).values()
        ess_portfolios = ESSPortfolio.objects.filter(user=user_id).values()
        return Response({"solar": list(solar_portfolios), "wind": list(wind_portfolios), "ess": list(ess_portfolios)}, status=status.HTTP_200_OK)

class ModelStatisticsAPI(APIView):
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
                    "mcv_prediction": round(entry.mcv_prediction, 2),
                    "mcp_prediction": round(entry.mcp_prediction, 2)
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