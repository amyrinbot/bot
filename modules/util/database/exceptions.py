class ErrorNotFound(Exception):
    pass


class ErrorAlreadyFixed(Exception):
    pass


class AlreadyFollowingError(Exception):
    pass


class NotFollowingError(Exception):
    pass


class MaximumErrorFollowersReached(Exception):
    pass
