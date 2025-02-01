import json
from datetime import datetime, time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GeneratorOffer, Tariffs
from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.utils.timezone import localtime

User = get_user_model()

class NegotiationWindowConsumer(AsyncWebsocketConsumer):
    ALLOWED_START_TIME = time(9, 0)  # 10:00 AM
    ALLOWED_END_TIME = time(23, 0)   # 11:00 AM    

    async def connect(self):
        # Check if current time is within the allowed window
        current_time = datetime.now().time()
        if not self.is_within_allowed_time(current_time):
            await self.close()
            return
        
        query_params = parse_qs(self.scope['query_string'].decode())
        self.user_id = query_params.get('user_id', [None])[0]
        self.tariff_id = query_params.get('tariff_id', [None])[0]

        if not self.user_id or not self.tariff_id:
            # Close the WebSocket connection if parameters are missing
            await self.close()
            return

        self.room_name = f"negotiation_{self.tariff_id}"  # Room specific to tariff_id
        self.room_group_name = self.room_name

        # Store channel_name in cache
        cache.set(f"user_channel_{self.user_id}", self.channel_name, timeout=None)

        # Join the WebSocket group based on tariff_id
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # Send previous offers to the user
        previous_offers = await self.get_previous_offers(self.tariff_id)
        print(previous_offers) 
        await self.send_previous_offers(previous_offers)


    async def send_previous_offers(self, offers):
        message = {
            'type': 'previous_offers',
            'offers': offers
        }
        print(message)
        await self.send(text_data=json.dumps(message))

    @database_sync_to_async
    def get_previous_offers(self, tariff_id):
        # Retrieve all previous offers for the given tariff
        offers = GeneratorOffer.objects.filter(tariff_id=tariff_id).values( 
        'generator__username', # Assuming you want the generator's username
        'updated_tariff', 
        'updated_at',
        'generator_id'
        )

        # Convert QuerySet to list and format datetime
        formatted_offers = {}
        for offer in offers:
            formatted_offers[str(offer['generator_id'])] = {
                'generator_username': offer['generator__username'],
                'updated_tariff': offer['updated_tariff'],
                'timestamp': localtime(offer['updated_at']).strftime('%Y-%m-%d %H:%M:%S'),  # Format datetime
            }
            # formatted_offers.append(formatted_offer)

        # return formatted_offers
        return formatted_offers

    async def disconnect(self, close_code):
        # Remove channel_name from cache
        cache.delete(f"user_channel_{self.user_id}")

        # Leave the WebSocket group when the user disconnects
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def close_connection(self, event):
        # Close the WebSocket connection
        await self.close()

    async def receive(self, text_data):
        # Check if the negotiation window is still open
        current_time = datetime.now().time()
        if not self.is_within_allowed_time(current_time):
            await self.send(text_data=json.dumps({
                'status': 'error',
                'message': 'Negotiation window is closed.'
            }))
            await self.close()
            return
        
        # Parse the incoming message
        text_data_json = json.loads(text_data)
        action = text_data_json.get('action')

        if action == 'select_generator':
            selected_generator_id = text_data_json.get('selected_generator_id')
            consumer_id = self.user_id # Get the consumer id


            try:
                tariff = await self.get_tariff(self.tariff_id)
                await self.finalize_negotiation(tariff, selected_generator_id, consumer_id)
                await self.send_final_messages(tariff, selected_generator_id)
                await self.close()  # Close the consumer's connection
            except Tariffs.DoesNotExist:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Tariff not found'
                }))
            except GeneratorOffer.DoesNotExist:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Selected Generator Offer not found.'
                }))
            except Exception as e:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': str(e)
                }))
            return

        # Extract the data from the incoming request
        # user_id = text_data_json.get('user_id')

        # Process the update only when 'updated_tariff' is provided (triggered by button click)
        updated_tariff = text_data_json.get('updated_tariff')
        if updated_tariff is not None:
            try:
                tariff = await self.get_tariff(self.tariff_id)
                generator_offer, created = await self.get_or_create_generator_offer(self.user_id, tariff)
                generator_offer.updated_tariff = updated_tariff
                await self.save_generator_offer(generator_offer)

                # Send confirmation message (Corrected):
                message = await self.build_offer_update_message(generator_offer)
                await self.channel_layer.group_send(self.room_group_name, message)

            
            except Tariffs.DoesNotExist:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Tariff not found'
                }))
            except Exception as e:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': str(e)
                }))
        else:
            # If no tariff update, send a simple response or ignore
            await self.send(text_data=json.dumps({
                'status': 'waiting',
                'message': 'Waiting for tariff update.'
            }))

    async def build_offer_update_message(self, generator_offer):
        generator_username = await self.get_generator_username(generator_offer.generator_id)
        return {
            'type': 'offer_update',
            'message': {
                str(generator_offer.generator_id): {
                    'generator_username': generator_username,
                    'tariff_id': generator_offer.tariff_id,
                    'updated_tariff': generator_offer.updated_tariff,
                    'timestamp': localtime(generator_offer.updated_at).strftime('%Y-%m-%d %H:%M:%S'),
                }
            }
        }

    async def send_final_messages(self, tariff, selected_generator_id):
        accepted_by_id = await self.get_accepted_by_id(tariff, selected_generator_id)
        selected_offer_updated_tariff = await self.get_updated_tariff(tariff, selected_generator_id)
        consumer = await self.get_user(accepted_by_id)
       

        generator_offers = await self.get_generator_offers(tariff)

        for offer in generator_offers:
            group_name = f"negotiation_{self.tariff_id}"
            message = {
                'type': 'negotiation_finalized',
                'message': {
                    'tariff_id': self.tariff_id,
                    'updated_tariff': offer.updated_tariff,
                    'consumer_username': consumer.username,
                    'consumer_id': consumer.id,
                }
            }
            generator = await self.get_generator(offer)
            generator_channel_name = cache.get(f"user_channel_{generator.id}")

            if generator_channel_name:
                if generator.id == selected_generator_id:
                    message['message']['is_selected'] = True
                    message['message']['message'] = "Your offer has been accepted!"  # Specific message for selected generator
                else:
                    message['message']['is_selected'] = False
                    message['message']['message'] = "Another generator's offer has been accepted. Thank you for participating."
                
                # Send message directly to the generator's channel
                await self.channel_layer.send(generator_channel_name, message)
            else:
                print(f"No channel name found for generator {generator.id}")
        
        # Disconnect all group members
        await self.channel_layer.group_send(
            group_name,
            {
                'type': 'close_connection',
                'message': 'The negotiation group is being closed.',
            }
        )

        # Remove the current WebSocket connection from the group
        await self.channel_layer.group_discard(group_name, self.channel_name)


        # Send message to consumer
        consumer_message = {
            'type': 'negotiation_finalized',
            'message': {
                'tariff_id': self.tariff_id,
                'selected_generator_id': selected_generator_id,
                'selected_generator_username': (await self.get_user(selected_generator_id)).username,
                'updated_tariff': selected_offer_updated_tariff,
                'consumer_username': consumer.username,
                'consumer_id': consumer.id,
            }
        }
        await self.send(text_data=json.dumps(consumer_message['message']))
        await self.close()

    @database_sync_to_async
    def get_generator(self, offer):
        return offer.generator

    @database_sync_to_async
    def get_generator_username(self, generator_id):
        try:
            user = User.objects.get(id=generator_id)
            return user.username
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_accepted_by_id(self, tariff, generator_id):
        try:
            selected = GeneratorOffer.objects.get(tariff=tariff, generator_id=generator_id)
            return selected.accepted_by.id
        except GeneratorOffer.DoesNotExist:
            return None  # Return None if not found

    @database_sync_to_async
    def get_updated_tariff(self, tariff, generator_id):
        try:
            selected = GeneratorOffer.objects.get(tariff=tariff, generator_id=generator_id)
            return selected.updated_tariff
        except GeneratorOffer.DoesNotExist:
            return None  # Return None if not found

    @database_sync_to_async
    def get_generator_offers(self, tariff):
        return list(GeneratorOffer.objects.filter(tariff=tariff).order_by('-updated_at'))

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None # Handle case where user does not exist

    async def negotiation_finalized(self, event):
        await self.send(text_data=json.dumps(event['message']))

    @database_sync_to_async
    def finalize_negotiation(self, tariff, selected_generator_id, consumer_id):
        try:
            print(consumer_id)
            consumer = User.objects.get(id=consumer_id)
            selected_offer = GeneratorOffer.objects.get(tariff=tariff, generator__id=selected_generator_id)
            selected_offer.is_accepted = True
            selected_offer.accepted_by = consumer # Set the consumer
            selected_offer.save()
            print(selected_offer.accepted_by)

            # Optionally, you might want to mark other offers for this tariff as rejected:
            GeneratorOffer.objects.filter(tariff=tariff).exclude(id=selected_offer.id).update(is_accepted=False)
        except GeneratorOffer.DoesNotExist:
            raise  # Re-raise the exception to be handled in the caller

    async def offer_update(self, event):
        # Send the updated offer details to all connected clients in the group (for the same tariff)
        await self.send(text_data=json.dumps(event['message']))

    # Helper method to check if the current time is within the allowed window
    def is_within_allowed_time(self, current_time):
        return self.ALLOWED_START_TIME <= current_time <= self.ALLOWED_END_TIME

    # Database interaction methods
    @database_sync_to_async
    def get_tariff(self, tariff_id):
        return Tariffs.objects.get(id=tariff_id)

    @database_sync_to_async
    def get_or_create_generator_offer(self, user_id, tariff):
        # Fetch the GeneratorOffer object or create it
        return GeneratorOffer.objects.get_or_create(
            generator_id=user_id,
            tariff=tariff
        )

    @database_sync_to_async
    def save_generator_offer(self, generator_offer):
        generator_offer.save()

# Store channel name in Redis
async def store_channel_name(user_id, channel_name):
    cache.set(f"user_channel_{user_id}", channel_name, timeout=None)

# Retrieve channel name from Redis
async def get_channel_name(user_id):
    return cache.get(f"user_channel_{user_id}")

# Remove channel name from Redis
async def remove_channel_name(user_id):
    cache.delete(f"user_channel_{user_id}")