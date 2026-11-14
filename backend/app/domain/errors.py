from pydantic import BaseModel, ConfigDict

RUN_ALREADY_FINALIZED = "RUN_ALREADY_FINALIZED"
RUN_ALREADY_FINALIZED_MESSAGE = "Research run has already been finalized."
RUN_CAPACITY_EXCEEDED = "RUN_CAPACITY_EXCEEDED"
RUN_CAPACITY_EXCEEDED_MESSAGE = (
    "Vantage is processing other research runs. Try again in a few seconds."
)
SERVICE_DRAINING = "SERVICE_DRAINING"
SERVICE_DRAINING_MESSAGE = "Vantage is restarting. Try again in a few seconds."
RUN_DEADLINE_EXCEEDED = "RUN_DEADLINE_EXCEEDED"
RUN_DEADLINE_EXCEEDED_MESSAGE = "The research run did not finish within its time limit."
RUN_INTERRUPTED = "RUN_INTERRUPTED"
RUN_INTERRUPTED_MESSAGE = (
    "The research run was interrupted by a server restart. Start it again."
)


class SafeError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    run_id: str | None = None
    request_id: str | None = None
    retryable: bool = False


class VantageError(Exception):
    def __init__(
        self,
        *,
        code: str,
        safe_message: str,
        retryable: bool = False,
        run_id: str | None = None,
        missing_value_count: int = 0,
        duplicate_session_count: int = 0,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.run_id = run_id
        self.missing_value_count = missing_value_count
        self.duplicate_session_count = duplicate_session_count
