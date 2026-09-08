class HubError(Exception):
    """An expected domain or request error exposed by the hub."""

    status_code = 400
    code = "hub_error"

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFoundError(HubError):
    status_code = 404
    code = "not_found"


class ForbiddenError(HubError):
    status_code = 403
    code = "forbidden"


class ShareExpiredError(ForbiddenError):
    code = "share_expired"


class ShareRevokedError(ForbiddenError):
    code = "share_revoked"


class AccessRestrictedError(ForbiddenError):
    code = "access_restricted"


class ConflictError(HubError):
    status_code = 409
    code = "conflict"


class ValidationError(HubError):
    status_code = 400
    code = "validation_error"
