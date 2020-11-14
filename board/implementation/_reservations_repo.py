import datetime
from typing import Dict, List, TYPE_CHECKING, Tuple

from django.db.models import Count
from django.utils import timezone
from returns.maybe import Maybe, Nothing, Some

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.models import (
    Reservation as ReservationModel, ReservationDay as ReservationDayModel, ReservationRoom as ReservationRoomModel
)
from board.repositories import ReservationsRepo
from common import functions as cf
from effective_tours.constants import Channels, ReservationSources, ReservationStatuses, RoomCloseReasons

if TYPE_CHECKING:
    from channels.entities import Connection


class ReservationsRepoOrm(ReservationsRepo):
    def accept(self, pk: int, price_ids: List[int] = None) -> Maybe[Reservation]:
        price_ids = [cf.get_int_or_none(x) for x in price_ids or []]
        price_ids = [x for x in price_ids if x is not None and x > 0]
        try:
            model = ReservationModel.objects.filter(id=pk)[0]
            if model.is_verified:
                return self.get(pk)
            model.checkin_original = model.checkin
            model.checkout_original = model.checkout
            model.price_accepted = model.price
            model.netto_price_accepted = model.netto_price
            model.is_verified = True
            model.verified_at = timezone.now()
            model.save(
                update_fields=[
                    'checkin_original',
                    'checkout_original',
                    'price_accepted',
                    'netto_price_accepted',
                    'is_verified',
                    'verified_at',
                ]
            )

            for room in model.rooms.active():
                is_changed = False
                if room.channel_rate_id != room.channel_rate_id_changed:
                    room.channel_rate_id = room.channel_rate_id_changed
                    is_changed = True
                if room.checkin_original != room.checkin:
                    room.checkin_original = room.checkin
                    is_changed = True
                if room.checkout_original != room.checkout:
                    room.checkout_original = room.checkout
                    is_changed = True
                if room.rate_plan_id_original != room.rate_plan_id:
                    room.rate_plan_id_original = room.rate_plan_id

                    # Change cancellation policy only if rate plan was changed
                    if room.policy_original != room.policy:
                        room.policy_original = room.policy
                    is_changed = True
                if room.price_accepted != room.price:
                    room.price_accepted = room.price
                    is_changed = True
                if room.netto_price_accepted != room.netto_price:
                    room.netto_price_accepted = room.netto_price
                    is_changed = True
                if is_changed:
                    room.save(
                        update_fields=[
                            'channel_rate_id',
                            'checkin_original',
                            'checkout_original',
                            'rate_plan_id_original',
                            'policy_original',
                            'price_accepted',
                            'netto_price_accepted',
                        ]
                    )

                # Update daily prices
                for price in room.day_prices.filter(id__in=price_ids):
                    is_changed = False
                    if price.price_original != price.price_changed:
                        price.price_original = price.price_changed
                        is_changed = True
                    if price.price_accepted != price.price_changed:
                        price.price_accepted = price.price_changed
                        is_changed = True
                    if is_changed:
                        price.save(update_fields=['price_original', 'price_accepted'])

            return self.get(pk)
        except IndexError:
            return Nothing

    def get(self, pk: int, with_deleted_rooms: bool = False) -> Maybe[Reservation]:
        queryset = ReservationModel.objects.prefetch_related('rooms', 'rooms__day_prices').filter(pk=pk)
        try:
            return Some(self.model_to_reservation(queryset[0], with_deleted_rooms=with_deleted_rooms))
        except IndexError:
            return Nothing

    def is_room_busy(
        self, room_id: int, start_date: datetime.date, end_date: datetime.date, exclude_rooms: List[int] = None
    ) -> bool:
        queryset = (
            ReservationDayModel.objects
            .filter(room_id=room_id, day__gte=start_date, day__lte=end_date)
            .exclude(reservation_room__is_deleted=True)
            .exclude(reservation_room__reservation__status=ReservationStatuses.CANCEL.name)
        )
        if exclude_rooms is not None and exclude_rooms:
            queryset = queryset.exclude(reservation_room_id__in=exclude_rooms)
        return queryset.exists()

    def save(self, reservation: Reservation, with_accepted_prices: bool = False) -> Tuple[Maybe[Reservation], bool]:
        if reservation.id is None:
            return self._create_reservation(reservation)
        elif reservation.status == ReservationStatuses.CANCEL:
            return self._cancel_reservation(reservation)
        return self._update_reservation(reservation, with_accepted_prices=with_accepted_prices)

    def select(
        self,
        connection: "Connection" = None,
        house_id: int = None,
        channel_ids: List[str] = None,
        start_date: datetime.date = None,
        end_date: datetime.date = None,
        pks: List[int] = None,
    ) -> List[Reservation]:
        queryset = ReservationModel.objects.prefetch_related('rooms', 'rooms__day_prices')
        if connection is not None:
            queryset = queryset.filter(connection_id=connection.id)
        elif house_id is not None:
            queryset = queryset.filter(house_id=house_id)
        else:
            raise AssertionError('Use connection or house_id for select reservations')
        if channel_ids is not None and channel_ids:
            queryset = queryset.filter(channel_id__in=channel_ids)
        if start_date is not None:
            queryset = queryset.filter(checkout__gt=start_date)
        if end_date is not None:
            queryset = queryset.filter(checkin__lte=end_date)
        if pks is not None and pks:
            queryset = queryset.filter(id__in=pks)
        return [self.model_to_reservation(x) for x in queryset]

    def select_busy_days(
        self, house_id: int, roomtype_ids: List[int], start_date: datetime.date = None, end_date: datetime.date = None
    ) -> Dict[int, Dict[datetime.date, int]]:
        if not roomtype_ids:
            return {}
        queryset = (
            ReservationDayModel.objects
            .filter(roomtype_id__in=roomtype_ids, reservation_room__reservation__house_id=house_id)
            .exclude(reservation_room__is_deleted=True)
            .exclude(reservation_room__reservation__status=ReservationStatuses.CANCEL.name)
        )
        if start_date is not None:
            queryset = queryset.filter(day__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(day__lte=end_date)
        queryset = queryset.values('roomtype_id', 'day').annotate(Count('id'))

        result = {}
        for item in queryset:
            if item['roomtype_id'] not in result:
                result[item['roomtype_id']] = {}
            result[item['roomtype_id']][item['day']] = item['id__count']
        return result

    def model_to_reservation(self, model: ReservationModel, with_deleted_rooms: bool = False) -> Reservation:
        if model.guest_contact_ids is not None and model.guest_contact_ids != '':
            contact_ids = [cf.get_int_or_none(x) for x in model.guest_contact_ids.split(',')]
            contact_ids = [x for x in contact_ids if x is not None and x > 0]
        else:
            contact_ids = []
        reservation = Reservation(
            id=model.pk,
            house_id=model.house_id,  # noqa
            connection_id=model.connection.id if model.connection is not None else None,
            source=ReservationSources.get_by_name(model.source),
            channel=Channels.get_by_name(model.channel),
            channel_id=model.channel_id,
            status=ReservationStatuses.get_by_name(model.status),
            close_reason=RoomCloseReasons.get_by_name(model.close_reason),
            checkin=model.checkin,
            checkout=model.checkout,
            room_count=model.room_count,
            currency=model.currency,
            price=model.price,
            price_accepted=model.price_accepted,
            tax=model.tax,
            fees=model.fees,
            netto_price=model.netto_price,
            netto_price_accepted=model.netto_price_accepted,
            guest_name=model.guest_name,
            guest_surname=model.guest_surname,
            guest_email=model.guest_email,
            guest_phone=model.guest_phone,
            guest_country=model.guest_country,
            guest_nationality=model.guest_nationality,
            guest_city=model.guest_city,
            guest_address=model.guest_address,
            guest_post_code=model.guest_post_code,
            guest_comments=model.guest_comments,
            guest_contact_id=model.guest_contact_id,
            guest_contact_ids=contact_ids,
            promo=model.promo,
            creditcard_info=model.creditcard_info,
            payment_info=model.payment_info,
            booked_at=model.booked_at,
            is_verified=model.is_verified,
            opportunity_id=model.opportunity_id,
            quotation_id=model.quotation_id,
        )

        queryset = model.rooms.all() if with_deleted_rooms else model.rooms.active()  # noqa
        for room in queryset:
            reservation.rooms.append(self.model_to_reservation_room(room))
        return reservation

    def model_to_reservation_room(self, model: ReservationRoomModel) -> ReservationRoom:
        room = ReservationRoom(
            id=model.pk,
            reservation_id=model.reservation.id,
            channel_id=model.channel_id,
            channel_rate_id=model.channel_rate_id,
            rate_plan_id=model.rate_plan_id,
            rate_id=model.rate_id,
            external_id=model.external_id,
            external_name=model.external_name,
            checkin=model.checkin,
            checkout=model.checkout,
            guest_name=model.guest_name,
            guest_count=model.guest_count,
            adults=model.adults,
            children=model.children,
            max_children=model.max_children,
            extra_bed=model.extra_bed,
            with_breakfast=model.with_breakfast,
            currency=model.currency,
            price=model.price,
            price_accepted=model.price_accepted,
            tax=model.tax,
            fees=model.fees,
            netto_price=model.netto_price,
            netto_price_accepted=model.netto_price_accepted,
            notes_extra=model.notes_extra,
            notes_facilities=model.notes_facilities,
            notes_info=model.notes_info,
            notes_meal=model.notes_meal,
            policy=model.policy or {},

            # Read-Only
            checkin_original=model.checkin_original,
            checkout_original=model.checkout_original,
            rate_plan_id_original=model.rate_plan_id_original,
            policy_original=model.policy_original,
            is_deleted=model.is_deleted,
            deleted_at=model.deleted_at,
        )
        for price in model.day_prices.all():  # noqa
            room.day_prices.append(self.model_to_reservation_day(price))
        return room

    @staticmethod
    def model_to_reservation_day(model: ReservationDayModel) -> ReservationDay:
        return ReservationDay(
            id=model.pk,
            reservation_room_id=model.reservation_room.id,
            day=model.day,
            price_changed=model.price_changed,
            price_accepted=model.price_accepted,
            tax=model.tax,
            currency=model.currency,
            roomtype_id=model.roomtype_id,
            room_id=model.room_id,  # noqa

            # Read-Only
            price_original=model.price_original,
        )

    def _create_reservation(self, reservation: Reservation) -> Tuple[Maybe[Reservation], bool]:
        model = ReservationModel.objects.create(
            house_id=reservation.house_id,
            connection_id=reservation.connection_id,
            source=reservation.source.name,
            channel=reservation.channel.name if reservation.channel is not None else None,
            channel_id=reservation.channel_id,
            status=reservation.status.name,
            close_reason=reservation.close_reason.name if reservation.close_reason is not None else None,
            checkin=reservation.checkin,
            checkin_original=reservation.checkin,
            checkout=reservation.checkout,
            checkout_original=reservation.checkout,
            room_count=reservation.room_count,
            currency=reservation.currency,
            price=reservation.price,
            price_accepted=reservation.price,
            tax=reservation.tax,
            fees=reservation.fees,
            netto_price=reservation.netto_price,
            netto_price_accepted=reservation.netto_price,
            guest_name=reservation.guest_name,
            guest_surname=reservation.guest_surname,
            guest_email=reservation.guest_email,
            guest_phone=reservation.guest_phone,
            guest_country=reservation.guest_country,
            guest_nationality=reservation.guest_nationality,
            guest_city=reservation.guest_city,
            guest_address=reservation.guest_address,
            guest_post_code=reservation.guest_post_code,
            guest_comments=reservation.guest_comments,
            guest_contact_id=reservation.guest_contact_id,
            guest_contact_ids=','.join([str(x) for x in reservation.guest_contact_ids]),
            promo=reservation.promo,
            creditcard_info=reservation.creditcard_info,
            payment_info=reservation.payment_info,
            booked_at=reservation.booked_at,
            opportunity_id=reservation.opportunity_id,
            quotation_id=reservation.quotation_id,
            is_verified=False,
        )
        if reservation.rooms:
            for room in reservation.rooms:
                self._create_reservation_room(model, room)

        return self.get(model.id), True  # return fresh data from DB

    def _create_reservation_room(self, model: ReservationModel, room: ReservationRoom) -> None:
        room_model = ReservationRoomModel.objects.create(
            reservation_id=model.pk,
            channel_id=room.channel_id,
            channel_rate_id=room.channel_rate_id,
            channel_rate_id_changed=room.channel_rate_id,
            rate_plan_id=room.rate_plan_id,
            rate_plan_id_original=room.rate_plan_id,
            rate_id=room.rate_id,
            external_id=room.external_id,
            external_name=room.external_name,
            checkin=room.checkin,
            checkin_original=room.checkin,
            checkout=room.checkout,
            checkout_original=room.checkout,
            guest_name=room.guest_name,
            guest_count=room.guest_count,
            adults=room.adults,
            children=room.children,
            max_children=room.max_children,
            extra_bed=room.extra_bed,
            with_breakfast=room.with_breakfast,
            currency=room.currency,
            price=room.price,
            price_accepted=room.price,
            tax=room.tax,
            fees=room.fees,
            netto_price=room.netto_price,
            netto_price_accepted=room.netto_price,
            notes_extra=room.notes_extra,
            notes_facilities=room.notes_facilities,
            notes_info=room.notes_info,
            notes_meal=room.notes_meal,
            policy=room.policy,
            policy_original=room.policy,
        )
        if room.day_prices:
            for price in room.day_prices:
                self._create_reservation_day(room_model, price)

    @staticmethod
    def _create_reservation_day(model: ReservationRoomModel, data: ReservationDay):
        ReservationDayModel.objects.create(
            reservation_room_id=model.pk,
            day=data.day,
            price_original=data.price_changed,
            price_changed=data.price_changed,
            price_accepted=data.price_changed,
            tax=data.tax,
            currency=data.currency,
            roomtype_id=data.roomtype_id,
            room_id=data.room_id,
        )

    def _cancel_reservation(self, reservation: Reservation) -> Tuple[Maybe[Reservation], bool]:
        try:
            model = ReservationModel.objects.filter(id=reservation.id)[0]

            mapping = {'status': 'status', 'is_verified': 'is_verified'}
            is_changed = False
            for field, source in mapping.items():
                value = reservation.status.name if source == "status" else getattr(reservation, source)
                if getattr(model, field) != value:
                    setattr(model, field, value)
                    is_changed = True
            if is_changed:
                model.save(update_fields=list(mapping.keys()))

            return self.get(model.id), is_changed  # return fresh data from DB
        except IndexError:
            return Nothing, False

    def _update_reservation(
        self, reservation: Reservation, with_accepted_prices: bool = False
    ) -> Tuple[Maybe[Reservation], bool]:
        try:
            model = ReservationModel.objects.filter(id=reservation.id)[0]

            mapping = {
                'status': 'status',
                'checkin': 'checkin',
                'checkout': 'checkout',
                'room_count': 'room_count',
                'currency': 'currency',
                'tax': 'tax',
                'fees': 'fees',
                'guest_name': 'guest_name',
                'guest_surname': 'guest_surname',
                'guest_email': 'guest_email',
                'guest_phone': 'guest_phone',
                'guest_country': 'guest_country',
                'guest_nationality': 'guest_nationality',
                'guest_city': 'guest_city',
                'guest_address': 'guest_address',
                'guest_post_code': 'guest_post_code',
                'guest_comments': 'guest_comments',
                'promo': 'promo',
                'creditcard_info': 'creditcard_info',
                'payment_info': 'payment_info',
                'close_reason': 'close_reason',
                'guest_contact_id': 'guest_contact_id',
                'guest_contact_ids': 'guest_contact_ids',
                'opportunity_id': 'opportunity_id',
                'quotation_id': 'quotation_id',
            }
            if with_accepted_prices:
                mapping['checkin_original'] = 'checkin'
                mapping['checkout_original'] = 'checkout'
                mapping['price_accepted'] = 'price_accepted'
                mapping['netto_price_accepted'] = 'netto_price_accepted'
            else:
                mapping['price'] = 'price'
                mapping['netto_price'] = 'netto_price'

            is_changed = False
            for field, source in mapping.items():
                if source == 'status':
                    value = (
                        reservation.status.name if reservation.status is not None else getattr(reservation, source)
                    )
                elif source == 'close_reason':
                    value = (
                        reservation.close_reason.name
                        if reservation.close_reason is not None
                        else getattr(reservation, source)
                    )
                elif source == 'guest_contact_ids':
                    value = ','.join([str(x) for x in reservation.guest_contact_ids])
                else:
                    value = getattr(reservation, source)
                if getattr(model, field) != value:
                    setattr(model, field, value)
                    is_changed = True
            if is_changed:
                model.save(update_fields=list(mapping.keys()))

            existed_external_ids = [x.external_id for x in model.rooms.only('external_id')]
            processed_external_ids = []
            for room in reservation.rooms:
                if room.external_id in existed_external_ids:
                    is_changed |= self._update_reservation_room(
                        model, room, with_accepted_prices=with_accepted_prices
                    )
                else:
                    self._create_reservation_room(model, room)
                    is_changed = True
                processed_external_ids.append(room.external_id)

            deleted_external_ids = [x for x in existed_external_ids if x not in processed_external_ids]
            for external_id in deleted_external_ids:
                self._delete_reservation_room(model, external_id)
                is_changed = True

            return self.get(model.id), is_changed  # return fresh data from DB

        except IndexError:
            return Nothing, False

    def _update_reservation_room(
        self, model: ReservationModel, data: 'ReservationRoom', with_accepted_prices: bool = False
    ) -> bool:
        try:
            room_model = ReservationRoomModel.objects.active().filter(
                reservation_id=model.pk, external_id=data.external_id
            )[0]

            mapping = {
                'channel_rate_id_changed': 'channel_rate_id',
                'external_name': 'external_name',
                'checkin': 'checkin',
                'checkout': 'checkout',
                'rate_plan_id': 'rate_plan_id',
                'policy': 'policy',
                'guest_name': 'guest_name',
                'guest_count': 'guest_count',
                'adults': 'adults',
                'children': 'children',
                'max_children': 'max_children',
                'extra_bed': 'extra_bed',
                'with_breakfast': 'with_breakfast',
                'currency': 'currency',
                'tax': 'tax',
                'fees': 'fees',
                'notes_extra': 'notes_extra',
                'notes_facilities': 'notes_facilities',
                'notes_info': 'notes_info',
                'notes_meal': 'notes_meal',
            }
            if with_accepted_prices:
                mapping['checkin_original'] = 'checkin'
                mapping['checkout_original'] = 'checkout'
                mapping['price_accepted'] = 'price_accepted'
                mapping['netto_price_accepted'] = 'netto_price_accepted'
            else:
                mapping['price'] = 'price'
                mapping['netto_price'] = 'netto_price'
            is_changed = False
            for field, source in mapping.items():
                value = getattr(data, source)
                if getattr(room_model, field) != value:
                    setattr(room_model, field, value)
                    is_changed = True
            if is_changed:
                room_model.save(update_fields=list(mapping.keys()))

            existed_days = [x.day for x in room_model.day_prices.only('day')]
            processed_days = []
            for price_data in data.day_prices:
                if price_data.day in existed_days:
                    is_changed |= self._update_reservation_day(
                        room_model, price_data, with_accepted_prices=with_accepted_prices
                    )
                else:
                    self._create_reservation_day(room_model, price_data)
                    is_changed = True
                processed_days.append(price_data.day)

            deleted_days = [x for x in existed_days if x not in processed_days]
            for day in deleted_days:
                self._delete_reservation_day(room_model, day)
                is_changed = True

            return is_changed

        except IndexError:
            return False

    @staticmethod
    def _update_reservation_day(
        model: ReservationDayModel, data: ReservationDay, with_accepted_prices: bool = False
    ) -> bool:
        try:
            day_model = ReservationDayModel.objects.filter(reservation_room_id=model.pk, day=data.day)[0]

            mapping = {'tax': 'tax', 'currency': 'currency', 'roomtype_id': 'roomtype_id', 'room_id': 'room_id'}
            if with_accepted_prices:
                mapping['price_accepted'] = 'price_accepted'
            else:
                mapping['price_changed'] = 'price_changed'
            is_changed = False
            for field, source in mapping.items():
                value = getattr(data, source)
                if getattr(day_model, field) != value:
                    setattr(day_model, field, value)
                    is_changed = True

            if is_changed:
                day_model.save(update_fields=list(mapping.keys()))
            return is_changed

        except IndexError:
            return False

    @staticmethod
    def _delete_reservation_room(model: ReservationModel, external_id: str) -> None:
        try:
            room_model = ReservationRoomModel.objects.active().filter(
                reservation_id=model.pk, external_id=external_id
            )[0]
            room_model.delete()
        except IndexError:
            pass

    @staticmethod
    def _delete_reservation_day(model: ReservationRoomModel, day: datetime.date) -> None:
        try:
            day_model = ReservationDayModel.objects.filter(reservation_room_id=model.pk, day=day)[0]
            day_model.delete()
        except IndexError:
            pass
