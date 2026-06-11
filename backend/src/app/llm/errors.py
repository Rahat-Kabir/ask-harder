class LlmError(Exception):
    """Base class for provider failures the app surfaces or recovers from."""


class IntakeParseError(LlmError):
    """JD/resume could not be parsed into a usable Profile — do not run plan-gen."""


class LlmEmptyResponse(LlmError):
    """Provider returned no usable content after retries."""


class LlmValidationError(LlmError):
    """Provider JSON did not validate against our schema after retries."""
