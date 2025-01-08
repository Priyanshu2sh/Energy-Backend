import json
from datetime import datetime, time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GeneratorOffer, Tariffs

class NegotiationWindowConsumer(AsyncWebsocketConsumer):
    ALLOWED_START_TIME = time(10, 0)  # 10:00 AM
    ALLOWED_END_TIME = time(11, 0)   # 11:00 AM

    async def connect(self):
        # Extract query parameters
        query_params = self.scope['query_string'].decode()
        self.user_id = self.get_query_param(query_params, 'user_id')
        self.tariff_id = self.get_query_param(query_params, 'tariff_id')

        if not self.user_id or not self.tariff_id:
            await self.close()
            return

        self.room_name = f"negotiation_{self.tariff_id}"  # Room specific to tariff_id
        self.room_group_name = self.room_name

        # Join the WebSocket group based on tariff_id
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Notify the client about the connection status and time restrictions
        current_time = datetime.now().time()
        window_status = "open" if self.is_within_allowed_time(current_time) else "closed"
        await self.send(text_data=json.dumps({
            'status': 'connected',
            'message': f'Negotiation window is currently {window_status}.',
            'window_status': window_status
        }))

    async def disconnect(self, close_code):
        # Leave the WebSocket group when the user disconnects
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Parse the incoming message
        text_data_json = json.loads(text_data)
        updated_tariff = text_data_json.get('updated_tariff')

        # Allow only record viewing after the window closes
        current_time = datetime.now().time()
        if not self.is_within_allowed_time(current_time):
            if updated_tariff is not None:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Negotiation window is closed. Updates are not allowed.'
                }))
                return

        if updated_tariff is not None:
            try:
                tariff = await self.get_tariff(self.tariff_id)
                generator_offer, created = await self.get_or_create_generator_offer(self.user_id, tariff)
                generator_offer.updated_tariff = updated_tariff
                await self.save_generator_offer(generator_offer)

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'offer_update',
                        'message': {
                            'status': 'success',
                            'generator_id': self.user_id,
                            'tariff_id': self.tariff_id,
                            'updated_tariff': updated_tariff,
                            'timestamp': generator_offer.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                        }
                    }
                )
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
            # Handle a request to view records
            try:
                tariff = await self.get_tariff(self.tariff_id)
                generator_offers = await self.get_generator_offers(self.tariff_id)
                offers_data = [
                    {
                        'generator_id': offer.generator_id,
                        'updated_tariff': offer.updated_tariff,
                        'timestamp': offer.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for offer in generator_offers
                ]
                await self.send(text_data=json.dumps({
                    'status': 'success',
                    'message': 'Fetched generator offers.',
                    'offers': offers_data
                }))
            except Tariffs.DoesNotExist:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Tariff not found'
                }))

    async def offer_update(self, event):
        # Send the updated offer details to all connected clients in the group (for the same tariff)
        await self.send(text_data=json.dumps(event['message']))

    # Helper method to check if the current time is within the allowed window
    def is_within_allowed_time(self, current_time):
        return self.ALLOWED_START_TIME <= current_time <= self.ALLOWED_END_TIME

    # Helper method to extract query parameters
    def get_query_param(self, query_string, param):
        from urllib.parse import parse_qs
        parsed_params = parse_qs(query_string)
        return parsed_params.get(param, [None])[0]

    # Database interaction methods
    @database_sync_to_async
    def get_tariff(self, tariff_id):
        return Tariffs.objects.get(id=tariff_id)

    @database_sync_to_async
    def get_generator_offers(self, tariff_id):
        return GeneratorOffer.objects.filter(tariff_id=tariff_id)

    @database_sync_to_async
    def get_or_create_generator_offer(self, user_id, tariff):
        return GeneratorOffer.objects.get_or_create(generator_id=user_id, tariff=tariff)

    @database_sync_to_async
    def save_generator_offer(self, generator_offer):
        generator_offer.save()
