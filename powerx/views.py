import base64
import pandas as pd
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.utils.timezone import now, timedelta

from accounts.models import User
from .models import ConsumerDayAheadDemand, MonthAheadPrediction, NextDayPrediction, Notifications
from .serializers import NextDayPredictionSerializer, ConsumerDayAheadDemandSerializer, NotificationsSerializer
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
from django.utils.dateparse import parse_time
from django.db.models import Avg, Max, Min
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

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

        if predictions.exists():
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
                "predictions": serializer.data,
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
        else:
            return Response({"message": "No data available for the next day"}, status=status.HTTP_404_NOT_FOUND)

class MonthAheadPredictionAPI(APIView):
    def get(self, request):
        start_date = now().date() + timedelta(days=1)  # Next day
        end_date = start_date + timedelta(days=29)  # Next 30 days

        # Get data for the next 30 days
        predictions = MonthAheadPrediction.objects.filter(date__date__range=[start_date, end_date])

        if not predictions.exists():
            return Response({"message": "No data available for the next 30 days"}, status=status.HTTP_404_NOT_FOUND)

        # Aggregate per day
        daily_stats = predictions.values('date__date').annotate(
            avg_mcv=Avg('mcv_prediction'),
            avg_mcp=Avg('mcp_prediction'),
        ).order_by('date__date')

        # Prepare daily aggregated data
        daily_data = []
        for record in daily_stats:
            daily_data.append({
                "date": record["date__date"],
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

        return Response({
            "daily_data": daily_data,
            "overall_stats": overall_stats
        }, status=status.HTTP_200_OK)



class ConsumerDayAheadDemandAPI(APIView):

    def get(self, request, user_id):

        next_day = datetime.now().date() + timedelta(days=1)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

        demand_records = ConsumerDayAheadDemand.objects.filter(
            consumer=user,
            date=next_day
        ).order_by("start_time")

        if not demand_records.exists():
            return Response({"message": "No demand data available for the next day."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConsumerDayAheadDemandSerializer(demand_records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        consumer = request.data.get("consumer")
        file_data = request.data.get("file")
        energy_type = request.data.get("energy_type")
        demand_data = request.data.get("demand_data", [])  # List of demand entries

        # Validate energy type
        if energy_type not in dict(ConsumerDayAheadDemand.ENERGY_CHOICES):
            return Response({"error": "Invalid energy type."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            consumer = User.objects.get(id=consumer)
        except User.DoesNotExist:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

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
                            consumer=consumer,
                            energy_type=energy_type,
                            date=next_day,
                            start_time=parse_time(start_time),
                            end_time=parse_time(end_time),
                            demand=demand
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
                        consumer=consumer,
                        energy_type=energy_type,
                        date=next_day,
                        start_time=parse_time(start_time),
                        end_time=parse_time(end_time),
                        demand=demand
                    ))

            except Exception as e:
                return Response({"error": f"Invalid manual data: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"error": "No file or demand data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Bulk insert the data
        ConsumerDayAheadDemand.objects.bulk_create(data_list)

        return Response({"message": "Data uploaded successfully"}, status=status.HTTP_201_CREATED)

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