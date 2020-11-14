from effective_tours.constants import Groups, Permissions as BasePermissions, PermissionActions


class Permissions(BasePermissions):
    ALL = 'board.*'

    BOARD = 'board.calendar.*'
    BOARD_READ = 'board.calendar.read'

    RESERVATION = 'board.reservation.*'
    RESERVATION_READ = 'board.reservation.read'
    RESERVATION_CREATE = 'board.reservation.create'
    RESERVATION_UPDATE = 'board.reservation.update'
    RESERVATION_DELETE = 'board.reservation.delete'


DefaultGroupPermissions = {
    Groups.GOD: [Permissions.ALL],
    Groups.ADMIN: [
        Permissions.BOARD_READ,
        Permissions.RESERVATION_READ,
        Permissions.RESERVATION_CREATE,
        Permissions.RESERVATION_DELETE,
        Permissions.RESERVATION_DELETE,
    ],
    Groups.MANAGER: [Permissions.BOARD_READ, Permissions.RESERVATION_READ],
    Groups.STAFF: [Permissions.BOARD_READ],
}

EditablePermissions = {
    Permissions.BOARD_READ: {'label': 'Calendar', 'action': PermissionActions.READ},
    Permissions.RESERVATION_READ: {'label': 'Reservation', 'action': PermissionActions.READ},
    Permissions.RESERVATION_CREATE: {'label': 'Reservation', 'action': PermissionActions.CREATE},
    Permissions.RESERVATION_UPDATE: {'label': 'Reservation', 'action': PermissionActions.UPDATE},
    Permissions.RESERVATION_DELETE: {'label': 'Reservation', 'action': PermissionActions.DELETE},
}
