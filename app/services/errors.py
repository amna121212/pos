"""Errors raised by POS services. Routes can turn these into flash messages later."""


class TenantAccessError(PermissionError):
    """Raised when a business tries to read or change another business's row."""


class StockPolicyError(ValueError):
    """Raised when a stock change would break the ledger rules."""


class PaymentError(ValueError):
    """Raised when a payment does not match the order total rules."""


class LifecycleError(ValueError):
    """Raised when a document is in the wrong status for the requested action."""
