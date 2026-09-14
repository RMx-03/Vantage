from pydantic import BaseModel, ConfigDict


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
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.run_id = run_id
