import calendar # Add this import at the top
from django.db.models import Func, IntegerField, Count
from calendar import month_name
# from django.forms import IntegerField
import jwt
from itertools import chain
from operator import attrgetter
from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.hashers import check_password
from admin.serializers import ConsumerRequirementsUpdateSerializer, ConsumerSerializer, GeneratorSerializer, GridTariffSerializer, HelpDeskQuerySerializer, MasterTableSerializer, NationalHolidaySerializer, PeakHoursSerializer, RETariffMasterTableSerializer, SubscriptionTypeSerializer, ESSPortfolioSerializer, SolarPortfolioSerializer, WindPortfolioSerializer
from energy.models import *
from accounts.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Sum, Q
from django.core.mail import send_mail
from accounts.serializers import UserSerializer
import logging
from django.db.models import Count
from django.db.models.functions import Extract
from django.utils import timezone
traceback_logger = logging.getLogger('django')
logger = logging.getLogger('debug_logger') 


# Create your views here.
class Dashboard(APIView):
    # Custom database function to extract month from a date field
    class Month(Func):
        function = 'MONTH'
        template = '%(function)s(%(expressions)s)'
        output_field = IntegerField()
        
    #   helper function to get monthly data
    def get_monthly_data(self, user_category, year):
        monthly_counts = {month: 0 for month in range(1, 13)}
        qs = (
            User.objects.filter(
                user_category=user_category,
                date_joined__year=year,
                date_joined__isnull=False
            )
            .annotate(month=self.Month('date_joined')) 
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        for item in qs:
            monthly_counts[item['month']] = item['count']

        data_with_names = [
            {"month": calendar.month_name[month], "count": count}
            for month, count in monthly_counts.items()
        ]
        
        return data_with_names
    
    # GET method for dashboard data
    def get(self, request):
        year = request.GET.get('year')
        try:
           year = int(year)
        except (ValueError, TypeError):
            year = timezone.now().year
        
        demand = ConsumerRequirements.objects.all() 
        total_demand = demand.aggregate(total_contracted_demand=Sum('contracted_demand'))
        HT_Commercial = demand.filter(tariff_category='HT Commercial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        HT_Industrial = demand.filter(tariff_category='HT Industrial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        LT_Commercial = demand.filter(tariff_category='LT Commercial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        LT_Industrial = demand.filter(tariff_category='LT Industrial').aggregate(total_contracted_demand=Sum('contracted_demand'))

        solar_projects = SolarPortfolio.objects.all().count()
        wind_projects = WindPortfolio.objects.all().count()
        ess_projects = ESSPortfolio.objects.all().count()
        total_projects = solar_projects + wind_projects + ess_projects

        offers = StandardTermsSheet.objects.all()
        total_offers = offers.count()
        offers_rejected = offers.filter(Q(consumer_status='Rejected') | Q(generator_status='Rejected')).count()
        offers_accepted = offers.filter(Q(consumer_status='Accepted') | Q(generator_status='Accepted')).count()
        offers_pending = offers.filter(~Q(consumer_status__in=['Accepted', 'Rejected', 'Withdrawn']) | ~Q(generator_status__in=['Accepted', 'Rejected', 'Withdrawn'])).count()
        
        monthly_consumers = self.get_monthly_data("Consumer", year)
        monthly_generators = self.get_monthly_data("Generator", year)
    
        total_consumers = User.objects.filter(user_category='Consumer').count()
        total_generators = User.objects.filter(user_category='Generator').count()

        response_data = {
            "total_demand": total_demand['total_contracted_demand'] or 0,
            "HT_Commercial": HT_Commercial['total_contracted_demand'] or 0,
            "HT_Industrial": HT_Industrial['total_contracted_demand'] or 0,
            "LT_Commercial": LT_Commercial['total_contracted_demand'] or 0,
            "LT_Industrial": LT_Industrial['total_contracted_demand'] or 0,
            "total_projects": total_projects,
            "solar_projects": solar_projects,
            "wind_projects": wind_projects,
            "ess_projects": ess_projects,
            "total_offers": total_offers,
            "offers_rejected": offers_rejected,
            "offers_accepted": offers_accepted,
            "offers_pending": offers_pending,
            "total_consumers": total_consumers,
            "total_generators": total_generators,
            "monthly_consumers" : monthly_consumers,
            "monthly_generators" : monthly_generators,
        }

        return Response(response_data, status=200)
    

class ListPagination(PageNumberPagination):
    page_size = 10  # default items per page
    max_page_size = 100  # prevent abuse by huge page sizes

class Consumer(APIView):

    def get(self, request):
        # filter only users with user_category = 'Consumer'
        consumers = User.objects.filter(user_category='Consumer', is_active=True).order_by('-id')

        paginator = ListPagination()
        result_page = paginator.paginate_queryset(consumers, request)
        serializer = ConsumerSerializer(result_page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def put(self, request, pk):
        consumer = User.objects.filter(pk=pk).first()
        if not consumer:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

        updated_status = request.data.get('status')
        if updated_status and updated_status == 'deactivate':
            consumer.is_active = False
            consumer.save()
            return Response({"message": "Consumer deactivated."}, status=status.HTTP_200_OK)
        elif updated_status and updated_status == 'activate':
            consumer.is_active = True
            consumer.save()
            return Response({"message": "Consumer activated."}, status=status.HTTP_200_OK)

        serializer = ConsumerSerializer(consumer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        consumer = User.objects.filter(pk=pk).first()
        if not consumer:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

        consumer.is_active = False
        consumer.deleted = True
        consumer.save()
        return Response({"detail": "Consumer deleted."}, status=status.HTTP_200_OK)


class Generator(APIView):

    def get(self, request):
        # filter only users with user_category = 'Consumer'
        generators = User.objects.filter(user_category='Generator', is_active=True).order_by('-id')

        paginator = ListPagination()
        result_page = paginator.paginate_queryset(generators, request)
        serializer = GeneratorSerializer(result_page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def put(self, request, pk):
        generator = User.objects.filter(pk=pk).first()
        if not generator:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        updated_status = request.data.get('status')
        if updated_status and updated_status == 'deactivate':
            generator.is_active = False
            generator.save()
            return Response({"message": "Generator deactivated."}, status=status.HTTP_200_OK)
        elif updated_status and updated_status == 'activate':
            generator.is_active = True
            generator.save()
            return Response({"message": "Generator activated."}, status=status.HTTP_200_OK)

        serializer = GeneratorSerializer(generator, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        generator = User.objects.filter(pk=pk).first()
        if not generator:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        generator.is_active = False
        generator.deleted = True
        generator.save()
        return Response({"detail": "Generator deleted."}, status=status.HTTP_200_OK)


class OnlineSubscriptions(APIView):
    def get(self, request):
        # Get all online payments
        online_payments = PaymentTransaction.objects.all()

        # Get all related users and subscriptions from the invoices
        invoice_users = online_payments.values_list('invoice__user', flat=True)
        invoice_subscriptions = online_payments.values_list('invoice__subscription', flat=True)

        # Filter enrolled subscriptions
        enrolled = SubscriptionEnrolled.objects.filter(
            user_id__in=invoice_users,
            subscription_id__in=invoice_subscriptions
        ).select_related('user', 'subscription')  # company only if separate model

        data = []
        for e in enrolled:
            data.append({
                "user_category": e.user.user_category,
                "user_name": e.user.company_representative,
                "company_name": e.user.company,
                "subscription_type": e.subscription.subscription_type,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "status": "Active" if e.status == "active" else "Inactive"
            })

        return Response(data)


class OfflineSubscriptions(APIView):

    def get(self, request):
        offline_payments = OfflinePayment.objects.select_related('invoice', 'invoice__user', 'invoice__subscription')
        data = []

        for payment in offline_payments:
            user = payment.invoice.user
            subscription_type = payment.invoice.subscription

            # Get the matching enrolled subscription (if any)
            enrolled = SubscriptionEnrolled.objects.filter(
                user=user,
                subscription=subscription_type
            ).select_related('user', 'subscription').first()

            if enrolled:
                data.append({
                    "id": payment.id,
                    "user_category": user.user_category,
                    "user_name": user.company_representative,
                    "company_name": user.company,
                    "subscription_type": subscription_type.subscription_type,
                    "start_date": enrolled.start_date,
                    "end_date": enrolled.end_date,
                    "transaction_id": payment.transaction_id,
                    "payment_date": payment.payment_date,
                    "payment_mode": payment.payment_mode,
                    "payment_status": payment.status,
                    "status": "Active" if enrolled.status == "active" else "Inactive"
                })

        return Response(data)
    
    # def post(self, request):

    
    def put(self, request, pk):
        payment = get_object_or_404(OfflinePayment, pk=pk)
        new_status = request.data.get("status")

        if new_status not in ["Pending", "Approved", "Rejected"]:
            return Response(
                {"error": "Invalid status value."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.status = new_status
        payment.save()

        if payment.status == 'Approved':
            subscription_enrolled = SubscriptionEnrolled(user=payment.invoice.user, subscription=payment.invoice.subscription, start_date=date.today(), end_date=date.today() + timedelta(payment.invoice.subscription.duration_in_days))
            subscription_enrolled.save()
            return Response(
                {"message": "Payment status updated and subscription activated successfully.", "new_status": payment.status},
                status=status.HTTP_200_OK
            )
        
        return Response(
            {"message": "Payment status updated successfully.", "new_status": payment.status},
            status=status.HTTP_200_OK
        )
    
class AssignPlan(APIView):

    def post(self, request):
        user_id = request.data.get('user_id')
        subscription_id = request.data.get('subscription_id')

        if not user_id or not subscription_id:
            return Response({"error": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
            subscription = SubscriptionType.objects.get(id=subscription_id)

            # Check if user already has an active subscription
            active_subscription = SubscriptionEnrolled.objects.filter(user=user, status='active').first()
            if active_subscription:
                return Response({"error": "User already has an active subscription."}, status=status.HTTP_400_BAD_REQUEST)

            # Assign new subscription
            new_subscription = SubscriptionEnrolled(
                user=user,
                subscription=subscription,
                start_date=date.today(),
                end_date=date.today() + timedelta(subscription.duration_in_days),
                status='active'
            )
            new_subscription.save()

            return Response({"message": "Subscription assigned successfully."}, status=status.HTTP_201_CREATED)

        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except SubscriptionType.DoesNotExist:
            return Response({"error": "Subscription type not found."}, status=status.HTTP_404_NOT_FOUND)


class SubscriptionPlans(APIView):

    def get(self, request):
        subscription_plans = SubscriptionType.objects.all()
        serializer = SubscriptionTypeSerializer(subscription_plans, many=True)
        return Response(serializer.data)

    def put(self, request, pk):
        subscription_plan = get_object_or_404(SubscriptionType, pk=pk)
        serializer = SubscriptionTypeSerializer(subscription_plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        subscription_plan = get_object_or_404(SubscriptionType, pk=pk)
        subscription_plan.delete()
        return Response({"message": "Subscription plan deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    
class DemandData(APIView):

    def get(self, request):

        requirements = ConsumerRequirements.objects.all().order_by('-id')

        paginator = ListPagination()
        paginated_requirements = paginator.paginate_queryset(requirements, request)

        demand_data = []
        for requirement in paginated_requirements:

            monthly_consumption_data = []
            monthly_consumption = MonthlyConsumptionData.objects.filter(requirement=requirement)
            for data in monthly_consumption:
                monthly_consumption_data.append({
                    "id": data.id,
                    "month": data.month,
                    "monthly_consumption": data.monthly_consumption,
                    "peak_consumption": data.peak_consumption,
                    "off_peak_consumption": data.off_peak_consumption,
                    "monthly_bill_amount": data.monthly_bill_amount
                })

            demand_data.append({
                "id": requirement.id,
                "username": requirement.user.username,
                "state": requirement.state,
                "industry": requirement.industry,
                "sub_industry": requirement.sub_industry,
                "contracted_demand": requirement.contracted_demand,
                "tariff_category": requirement.tariff_category,
                "voltage_level": requirement.voltage_level,
                "procurement_date": requirement.procurement_date,
                "consumption_unit": requirement.consumption_unit,
                "annual_electricity_consumption": requirement.annual_electricity_consumption,
                "roof_area": requirement.roof_area,
                "solar_rooftop_capacity": requirement.solar_rooftop_capacity,
                "location": requirement.location,
                "latitude": requirement.latitude,
                "monthly_consumption_data": monthly_consumption_data
            })

        return paginator.get_paginated_response(demand_data)
    
    def put(self, request, pk):

        requirement = ConsumerRequirements.objects.filter(pk=pk).first()
        if not requirement:
            return Response({"error": "Requirement not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConsumerRequirementsUpdateSerializer(requirement, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()

            # Update monthly consumption data
            monthly_data_list = request.data.get('monthly_consumption_data', [])
            for item in monthly_data_list:
                monthly_id = item.get('id')
                if not monthly_id:
                    continue

                monthly_instance = MonthlyConsumptionData.objects.filter(id=monthly_id, requirement=requirement).first()
                if monthly_instance:
                    monthly_instance.monthly_consumption = item.get('monthly_consumption', monthly_instance.monthly_consumption)
                    monthly_instance.peak_consumption = item.get('peak_consumption', monthly_instance.peak_consumption)
                    monthly_instance.off_peak_consumption = item.get('off_peak_consumption', monthly_instance.off_peak_consumption)
                    monthly_instance.monthly_bill_amount = item.get('monthly_bill_amount', monthly_instance.monthly_bill_amount)
                    monthly_instance.save()
                
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GenerationData(APIView):

    def get(self, request):
        try:
            solar_data = SolarPortfolio.objects.all().order_by('-id')
            wind_data = WindPortfolio.objects.all().order_by('-id')
            ess_data = ESSPortfolio.objects.all().order_by('-id')

            # Combine & sort by id desc
            combined_data = sorted(
                chain(solar_data, wind_data, ess_data),
                key=attrgetter('id'),
                reverse=True
            )

            # Paginate combined list
            paginator = ListPagination()
            paginated_data = paginator.paginate_queryset(combined_data, request)

            # Prepare grouped response
            response_data = {
                "solar": [],
                "wind": [],
                "ess": []
            }

            for obj in paginated_data:
                if isinstance(obj, SolarPortfolio):
                    response_data["solar"].append(SolarPortfolioSerializer(obj).data)
                elif isinstance(obj, WindPortfolio):
                    response_data["wind"].append(WindPortfolioSerializer(obj).data)
                elif isinstance(obj, ESSPortfolio):
                    response_data["ess"].append(ESSPortfolioSerializer(obj).data)

            # Return paginated response with grouped data
            return paginator.get_paginated_response(response_data)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class HelpDeskQueryAPI(APIView):

    def get(self, request):
        queries = HelpDeskQuery.objects.all().order_by('-date')
        response_data = []
        for query in queries:
            response_data.append({
                'id': query.id,
                'user': query.user.id, 
                'user_category': query.user.user_category,
                'company': query.user.company,
                'company_representative': query.user.company_representative,
                'query': query.query,
                'date': query.date,
                'status': query.status,
            })
        return Response(response_data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        query = get_object_or_404(HelpDeskQuery, pk=pk)
        serializer = HelpDeskQuerySerializer(query, data=request.data, partial=True)
        if serializer.is_valid():
            user=serializer.save()
            Notifications.objects.create(user=query.user, message=f'Your query status has been updated to {request.data.get("status")}.')
            send_mail(
                subject='EXG Query Update',
                message=f'Your query status has been updated to {request.data.get("status")}.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[query.user.email],
                fail_silently=False
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class SendNotificationAPI(APIView):
    
    def post(self, request):
        user_id = request.data.get('user_id')
        message = request.data.get('message')
        user_category = request.data.get('user_category')  # Only required if user_id is 'all'
        title = request.data.get('title')  # Only required if send_type is 'email'

        if not user_id or not message:
            return Response({"error": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Determine target users
        if user_id == 'all':
            if not user_category:
                return Response({"error": "User category is required when user_id is 'all'."}, status=status.HTTP_400_BAD_REQUEST)
            users = User.objects.filter(user_category=user_category)
        else:
            try:
                user = User.objects.get(id=user_id)
                users = [user]
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Send notifications or emails
        for user in users:
            Notifications.objects.create(user=user, message=message)
            if not title:
                return Response({"error": "Title is required for sending emails."}, status=status.HTTP_400_BAD_REQUEST)
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )
            
        return Response({"success": True, "sent_to": len(users)}, status=status.HTTP_200_OK)

class MasterTableAPI(APIView):
    def get(self, request):
        records = MasterTable.objects.all()
        serializer = MasterTableSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MasterTableSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(MasterTable, pk=pk)
        serializer = MasterTableSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(MasterTable, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class RETariffAPI(APIView):
    def get(self, request):
        records = RETariffMasterTable.objects.all()
        serializer = RETariffMasterTableSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = RETariffMasterTableSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(RETariffMasterTable, pk=pk)
        serializer = RETariffMasterTableSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(RETariffMasterTable, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class GridTariffAPI(APIView):
    def get(self, request):
        records = GridTariff.objects.all()
        serializer = GridTariffSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = GridTariffSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(GridTariff, pk=pk)
        serializer = GridTariffSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(GridTariff, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class PeakHoursAPI(APIView):
    def get(self, request):
        records = PeakHours.objects.all()
        response_data = []
        for i in records:
            response_data.append({
                "state": i.state.id,
                "name": i.state.name,
                "peak_start_1": i.peak_start_1,
                "peak_end_1": i.peak_end_1,
                "peak_start_2": i.peak_start_2,
                "peak_end_1": i.peak_end_2,
                "off_peak_start": i.off_peak_start,
                "off_peak_end": i.off_peak_end,
            })
        return Response(response_data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PeakHoursSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(PeakHours, pk=pk)
        serializer = PeakHoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(PeakHours, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class NationalHolidayAPI(APIView):
    def get(self, request):
        holidays = NationalHoliday.objects.all()
        serializer = NationalHolidaySerializer(holidays, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = NationalHolidaySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(NationalHoliday, pk=pk)
        serializer = NationalHolidaySerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(NationalHoliday, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)
    
class OffersAPI(APIView):

    def get(self, request):
        offers = StandardTermsSheet.objects.all().order_by('-id')

        paginator = ListPagination()
        paginated_offers = paginator.paginate_queryset(offers, request)

        response_data = []
        for offer in paginated_offers:
            response_data.append({
                "id": offer.id,
                "consumer": offer.consumer.id if offer.consumer else None,
                "generator": offer.combination.generator.id if offer.combination and offer.combination.generator else None,
                "contracted_energy": offer.contracted_energy,
                "consumer_status": offer.consumer_status,
                "generator_status": offer.generator_status,
                "from_whom": offer.from_whom,
                "consumer_is_read": offer.consumer_is_read,
                "generator_is_read": offer.generator_is_read
            })

        return paginator.get_paginated_response(response_data)

class CreditRating(APIView):

    def get(self, request):
        users = User.objects.all()
        response_data = []
        for user in users:
            response_data.append({
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
                "credit_rating": user.credit_rating,
                "credit_rating_proof": user.credit_rating_proof.url if user.credit_rating_proof else None,
                "credit_rating_status": user.credit_rating_status
            })
        return Response(response_data)

    def put(self, request):
        user_id = request.data.get('user_id')
        credit_rating_status = request.data.get('credit_rating_status')

        try:
            user = User.objects.get(id=user_id)
            user.credit_rating_status = credit_rating_status
            user.save()
            if user.credit_rating_status == 'Approved':
                Notifications.objects.create(user=user, message='Your credit rating has been approved.')
                send_mail(
                    subject='Credit Rating Status',
                    message='Your credit rating has been approved.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
            elif user.credit_rating_status == 'Rejected':
                Notifications.objects.create(user=user, message='Your credit rating has been rejected. Please upload a valid credit rating proof.')
                send_mail(
                    subject='Credit Rating Status',
                    message='Your credit rating has been rejected. Please upload a valid credit rating proof.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
            return Response({"message": "Credit rating status updated successfully."})
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)
        
class AdminLogin(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not email or not password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            admin = User.objects.get(email=email, user_category='Admin')
        except User.DoesNotExist:
            return Response(
                {"error": "Admin not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
            
        if not check_password(password, admin.password):
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        payload = {
            "user_id": admin.id,
            "email": admin.email,
            "exp": datetime.utcnow() + timedelta(days=1),  # expires in 1 day
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        user_data = UserSerializer(admin).data

        return Response(
            {
                "message": "Login successful",
                "token": token,
                "user": user_data,
            },
            status=status.HTTP_200_OK
        )
        
class AddAdmin(APIView):

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        role = request.data.get("role")

        if not email or not password or not role:
            return Response({"error": "Missing required fields."}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already exists."}, status=400)

        admin = User(email=email, user_category='Admin', role=role)
        admin.set_password(password)
        admin.save()
        return Response({"message": "Admin created successfully.", "admin_id": admin.id}, status=201)

class RooftopOffers(APIView):

    def get(self, request):
        offers = GeneratorQuotation.objects.filter(consumer_status='Accepted').select_related("rooftop_quotation__requirement__user", "generator").order_by('-id')


        response_data = []
        for offer in offers:
            response_data.append({
                "id": offer.id,
                "consumer": ConsumerSerializer(offer.rooftop_quotation.requirement.user).data,
                "generator": GeneratorSerializer(offer.generator).data,
                "offered_capacity": offer.offered_capacity,
                "price": offer.price,
                "consumer_status": offer.consumer_status,
                "generator_status": offer.generator_status,
                "consumer_is_read": offer.consumer_is_read,
                "generator_is_read": offer.generator_is_read,
            })

        return Response(response_data, status=status.HTTP_200_OK)

    def put(self, request):
        updated_status = request.data.get('status')
        pk = request.data.get('id')
        offer = GeneratorQuotation.objects.filter(id=pk)
        offer.consumer_status = updated_status
        offer.generator_status = updated_status
        offer.save()

        return Response({'message': 'Status updated successfully'}, status=status.HTTP_200_OK)


