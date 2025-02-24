from datetime import datetime
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .AI_Model import manualdates
from rest_framework.exceptions import APIException
from powerx.AI_Model.model_scheduling import run_models_sequentially

# Create your views here.
class DayAheadAPI(APIView):
    def get(self, request):
        try:
            current_date = datetime.today()

            date_input = request.data.get('date')
            # If no date is provided, use current date
            if not date_input:
                date_input = datetime.today().strftime("%Y-%m-%d")

            # Validate date format
            try:
                datetime.strptime(date_input, "%Y-%m-%d")
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)


            result = manualdates.process_and_store_data(date_input)

            if "error" in result:
                return Response({"error": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": result["message"], "data": result["data"]}, status=status.HTTP_200_OK)

        except APIException as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
run_models_sequentially()