class BackendError(Exception):
    '''Anything that goes wrong talking to a legacy system.'''


class TransientError(BackendError):
    '''Timeouts, 5xx, 429. Worth retrying.'''


class PermanentError(BackendError):
    '''4xx such as not found. Retrying will not help.'''


class DataQualityError(BackendError):
    '''We got a response but it is unusable: ambiguous or malformed.'''
