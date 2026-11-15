from datetime import datetime
from functools import lru_cache
import logging
from typing import Any, Literal, cast
from uuid import UUID
from opentelemetry import trace

from app.agents.research_graph import create_research_graph
from app.core.config import settings
from app.domain.errors import RUN_ALREADY_FINALIZED, VantageError
from app.domain.research import (
    ComponentQuality,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    ModelQuality,
    NewsSnapshot,
    ProviderRecord,
    ResearchRun,
    RoleQuality,
    VersionInfo,
)
from app.providers.contracts import (
    InterpretationProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.prompts.research_interpretation import PROMPT_VERSION
from app.providers.registry import ProviderSet, build_providers
from app.providers.yfinance_provider import (
    latest_completed_xnys_close,
    snapshot_hash as market_snapshot_hash,
    trailing_xnys_sessions,
)
from app.repositories.research_runs import ResearchRunRepository, RunningResearchRun
from app.services.metrics import METRICS_VERSION
from app.services.policy import POLICY_VERSION, PolicyResult
from app.services.run_executor import RunExecutor
from app.telemetry.redaction import user_hash
from app.telemetry.tracing import get_tracer

logger = logging.getLogger(__name__)

RESPONSE_SCHEMA_VERSION: Literal["research-run-response-v2"] = (
    "research-run-response-v2"
)
WORKFLOW_VERSION: Literal["eod-research-v1"] = "eod-research-v1"


def _recording_root_span(root_span: Any) -> Any:
    """Fall back to the current span when it records, as ``create`` always has."""
    if root_span is None:
        current_span = trace.get_current_span()
        if current_span.is_recording():
            return current_span
    return root_span


class ResearchRunService:
    def __init__(
        self,
        repo: ResearchRunRepository | None = None,
        market_provider: MarketDataProvider | None = None,
        news_provider: NewsProvider | None = None,
        interpretation_provider: InterpretationProvider | None = None,
        versions: VersionInfo | None = None,
        providers: ProviderSet | None = None,
    ) -> None:
        self.repo = repo or ResearchRunRepository()
        if (
            providers is None
            and market_provider is not None
            and news_provider is not None
            and interpretation_provider is not None
        ):
            # Fully explicit wiring never touches settings or the registry.
            providers = ProviderSet(
                market=market_provider,
                news=(news_provider,),
                filings=None,
                fundamentals=None,
                macro=None,
                crosscheck=None,
                llm=interpretation_provider,
                not_configured=("filings", "fundamentals", "macro", "crosscheck"),
            )
        self.providers = providers or build_providers(settings)
        self.market: MarketDataProvider | None = (
            market_provider or self.providers.market
        )
        self.news: NewsProvider | None = news_provider or (
            self.providers.news[0] if self.providers.news else None
        )
        self.llm = interpretation_provider or self.providers.llm
        self.versions = versions or VersionInfo(
            response_schema=RESPONSE_SCHEMA_VERSION,
            workflow=WORKFLOW_VERSION,
            metrics=METRICS_VERSION,
            policy=POLICY_VERSION,
            code=settings.CODE_REVISION,
        )
        self.workflow = create_research_graph(self.llm)

    def create(
        self,
        *,
        user_id: UUID,
        symbol: str,
        now: datetime,
        root_span: Any = None,
    ) -> ResearchRun:
        norm_symbol = symbol.strip().upper()
        root_span = _recording_root_span(root_span)
        row = self._create_row(
            user_id=user_id, norm_symbol=norm_symbol, root_span=root_span
        )
        return self._execute(
            row,
            user_id=user_id,
            norm_symbol=norm_symbol,
            now=now,
            root_span=root_span,
        )

    def start_async(
        self,
        *,
        user_id: UUID,
        symbol: str,
        now: datetime,
        executor: RunExecutor,
        root_span: Any = None,
    ) -> ResearchRun:
        """Create a running row and execute it on ``executor``, off the request.

        Capacity is reserved before the row exists, so a refused start leaves
        nothing behind. The returned run is read before launch, so it is always
        ``running``.
        """
        slot = executor.reserve()
        try:
            norm_symbol = symbol.strip().upper()
            request_span_context = (
                root_span.get_span_context()
                if root_span is not None
                else trace.get_current_span().get_span_context()
            )
            root_span = _recording_root_span(root_span)
            row = self._create_row(
                user_id=user_id, norm_symbol=norm_symbol, root_span=root_span
            )
            # Read back before launching, so the caller always gets the run as
            # `running`, however quickly the detached execution finishes.
            run = self.repo.get_owned(user_id, row.public_id)
            if run is None:
                raise VantageError(
                    code="RUN_NOT_FOUND",
                    safe_message="Research run not found.",
                    run_id=str(row.public_id),
                )
        except BaseException:
            slot.release()
            raise

        def run_detached() -> None:
            self._execute_detached(
                row,
                user_id=user_id,
                norm_symbol=norm_symbol,
                now=now,
                request_span_context=request_span_context,
            )

        slot.launch(row.public_id, run_detached)
        return run

    def _create_row(
        self,
        *,
        user_id: UUID,
        norm_symbol: str,
        root_span: Any,
    ) -> RunningResearchRun:
        tracer = get_tracer()
        trace_id_hex = None
        if root_span is not None:
            span_ctx = root_span.get_span_context()
            if span_ctx and span_ctx.trace_id:
                trace_id_hex = f"{span_ctx.trace_id:032x}"
            self._tag_root_span(root_span, user_id=user_id, norm_symbol=norm_symbol)

        with tracer.start_as_current_span("create_run_record") as c_span:
            row = self.repo.create_running(
                user_id=user_id,
                symbol=norm_symbol,
                versions=self.versions,
                trace_id=trace_id_hex,
            )
            c_span.set_attribute("vantage.run_id", str(row.public_id))

        if root_span is not None:
            root_span.set_attribute("vantage.run_id", str(row.public_id))
        return row

    def _tag_root_span(self, span: Any, *, user_id: UUID, norm_symbol: str) -> None:
        span.set_attribute(
            "vantage.user_hash", user_hash(user_id, settings.TELEMETRY_USER_SALT)
        )
        span.set_attribute("vantage.instrument_symbol", norm_symbol)
        span.set_attribute("vantage.workflow_version", self.versions.workflow)
        span.set_attribute(
            "vantage.response_schema_version", self.versions.response_schema
        )
        span.set_attribute("gen_ai.provider.name", self.llm.name)
        span.set_attribute(
            "gen_ai.request.model", getattr(self.llm, "model", "default")
        )

    def _execute_detached(
        self,
        row: RunningResearchRun,
        *,
        user_id: UUID,
        norm_symbol: str,
        now: datetime,
        request_span_context: Any,
    ) -> None:
        """Run ``_execute`` on a worker thread under its own linked root span.

        ``_execute`` persists every ``VantageError`` before raising it, and a
        late finish after the stale sweep surfaces as ``RUN_ALREADY_FINALIZED``,
        so those end here. Anything else propagates to the slot's logger.
        """
        links = (
            [trace.Link(request_span_context)]
            if request_span_context is not None and request_span_context.is_valid
            else []
        )
        with get_tracer().start_as_current_span(
            "research_run_execute", links=links
        ) as span:
            self._tag_root_span(span, user_id=user_id, norm_symbol=norm_symbol)
            span.set_attribute("vantage.run_id", str(row.public_id))
            try:
                self._execute(
                    row,
                    user_id=user_id,
                    norm_symbol=norm_symbol,
                    now=now,
                    root_span=span,
                )
            except VantageError as exc:
                logger.info(
                    "detached research run ended with error code run_id=%s error_code=%s",
                    row.public_id,
                    exc.code,
                )

    def _execute(
        self,
        row: RunningResearchRun,
        *,
        user_id: UUID,
        norm_symbol: str,
        now: datetime,
        root_span: Any,
    ) -> ResearchRun:
        tracer = get_tracer()
        try:
            if self.market is None:
                raise VantageError(
                    code="MARKET_DATA_PROVIDER_FAILED",
                    safe_message="Market data provider was unavailable.",
                )
            analysis_cutoff = latest_completed_xnys_close(now)
            sessions = trailing_xnys_sessions(analysis_cutoff.date())
            start_date = sessions[0]
            completed = sessions[-1]

            with tracer.start_as_current_span("fetch_market_snapshot") as m_span:
                m_span.set_attribute("vantage.run_id", str(row.public_id))
                with tracer.start_as_current_span("provider_request") as p_span:
                    p_span.set_attribute("vantage.run_id", str(row.public_id))
                    try:
                        market = self.market.fetch_daily_snapshot(
                            norm_symbol, start_date, completed, now
                        )
                    except VantageError as exc:
                        if exc.code != "INVALID_PRICE_SERIES":
                            raise
                        market = MarketSnapshot(
                            symbol=norm_symbol,
                            bars=[],
                            provider=self.market.name,
                            retrieved_at=now,
                            as_of=analysis_cutoff,
                            latest_completed_session=completed,
                            content_hash=market_snapshot_hash(norm_symbol, []),
                            quality=ComponentQuality.FAILED,
                            error_code="INVALID_PRICE_SERIES",
                            missing_value_count=exc.missing_value_count,
                            duplicate_session_count=exc.duplicate_session_count,
                        )
                    market = market.model_copy(
                        update={
                            "as_of": analysis_cutoff,
                            "latest_completed_session": completed,
                        }
                    )
                with tracer.start_as_current_span("validate_price_quality") as v_span:
                    v_span.set_attribute("vantage.run_id", str(row.public_id))

            with tracer.start_as_current_span("fetch_news_snapshot") as n_span:
                n_span.set_attribute("vantage.run_id", str(row.public_id))
                with tracer.start_as_current_span("provider_request") as p_span:
                    p_span.set_attribute("vantage.run_id", str(row.public_id))
                    if self.news is None:
                        news = NewsSnapshot(
                            symbol=norm_symbol,
                            items=[],
                            provider="none",
                            retrieved_at=now,
                            quality=ComponentQuality.FAILED,
                            error_code="NEWS_PROVIDER_FAILED",
                        )
                    else:
                        try:
                            news = self.news.fetch_company_news(
                                norm_symbol,
                                analysis_cutoff,
                                now,
                                settings.NEWS_LOOKBACK_DAYS,
                                10,
                            )
                        except VantageError as exc:
                            news = NewsSnapshot(
                                symbol=norm_symbol,
                                items=[],
                                provider=self.news.name,
                                retrieved_at=now,
                                quality=ComponentQuality.FAILED,
                                error_code=exc.code,
                            )
                with tracer.start_as_current_span("validate_news_quality") as v_span:
                    v_span.set_attribute("vantage.run_id", str(row.public_id))

            sources = [
                EvidenceSource(
                    evidence_id=item.evidence_id,
                    provider=item.provider,
                    publisher=item.publisher,
                    title=item.title,
                    url=item.url,
                    event_time=item.event_time,
                    retrieved_at=item.retrieved_at,
                    content_hash=item.content_hash,
                    source_type=item.source_type,
                    summary=item.summary,
                    details=item.details,
                )
                for item in news.items
            ]
            # Persist snapshot before invoking graph
            provider_records = [
                ProviderRecord(
                    role="market",
                    provider=market.provider,
                    retrieved_at=market.retrieved_at,
                    quality=RoleQuality(market.quality.value),
                    error_code=market.error_code,
                    content_hash=market.content_hash,
                ),
                ProviderRecord(
                    role="news",
                    provider=None if self.news is None else news.provider,
                    retrieved_at=news.retrieved_at,
                    quality=RoleQuality(news.quality.value),
                    error_code=news.error_code,
                ),
                *(
                    ProviderRecord(
                        role=cast(Any, role),
                        provider=None,
                        retrieved_at=None,
                        quality=RoleQuality.NOT_CONFIGURED,
                    )
                    for role in self.providers.not_configured
                    if role not in ("market", "news")
                ),
            ]
            snapshot_hash = self.repo.save_snapshot(
                row.id, user_id, market, news, sources, providers=provider_records
            )
            if root_span is not None:
                root_span.set_attribute("vantage.snapshot_hash", snapshot_hash)

            # Invoke research workflow
            state = self.workflow.invoke(
                {
                    "run_id": row.public_id,
                    "user_id": user_id,
                    "symbol": norm_symbol,
                    "market": market,
                    "news": news,
                }
            )

            policy: PolicyResult = state["policy"]
            failure_code = state.get("model_failure_code")
            # The graph keeps a safe placeholder interpretation on the skip path
            # so policy and quality can derive `not_run` from it. Nothing the
            # model never produced may be persisted or published, so both the
            # placeholder and the model provenance that would imply an
            # invocation stop at this persistence boundary.
            model_was_attempted = policy.data_quality.model != ModelQuality.NOT_RUN
            interpretation = (
                state.get("interpretation") if model_was_attempted else None
            )
            model_info = (
                ModelInfo(
                    provider=self.llm.name,
                    model=self.llm.model,
                    prompt_version=PROMPT_VERSION,
                    failure_code=failure_code,
                )
                if model_was_attempted and self.llm.enabled
                else None
            )

            with tracer.start_as_current_span("persist_result") as p_span:
                p_span.set_attribute("vantage.run_id", str(row.public_id))
                res = self.repo.finalize_success(
                    internal_id=row.id,
                    user_id=user_id,
                    research_status=policy.research_status,
                    as_of=analysis_cutoff,
                    reasons=policy.reasons,
                    metrics=policy.metrics,
                    data_quality=policy.data_quality,
                    warnings=policy.warnings,
                    summary=policy.summary,
                    model_info=model_info,
                    interpretation=interpretation,
                )

            if root_span is not None:
                root_span.set_attribute(
                    "vantage.workflow_status", res.workflow_status.value
                )
                if res.research_status:
                    root_span.set_attribute(
                        "vantage.research_status", res.research_status.value
                    )
                if res.data_quality:
                    root_span.set_attribute(
                        "vantage.quality.overall", res.data_quality.overall.value
                    )
                if res.model_info:
                    root_span.set_attribute(
                        "vantage.prompt_version", res.model_info.prompt_version
                    )

            return res

        except VantageError as exc:
            if exc.code == RUN_ALREADY_FINALIZED:
                raise VantageError(
                    code=exc.code,
                    safe_message=exc.safe_message,
                    retryable=exc.retryable,
                    run_id=str(row.public_id),
                ) from exc
            with tracer.start_as_current_span("persist_result") as p_span:
                p_span.set_attribute("vantage.run_id", str(row.public_id))
                try:
                    self.repo.finalize_failure(
                        internal_id=row.id,
                        user_id=user_id,
                        error_code=exc.code,
                        error_message_safe=exc.safe_message,
                    )
                except VantageError as finalization_exc:
                    if finalization_exc.code == RUN_ALREADY_FINALIZED:
                        raise VantageError(
                            code=finalization_exc.code,
                            safe_message=finalization_exc.safe_message,
                            retryable=finalization_exc.retryable,
                            run_id=str(row.public_id),
                        ) from finalization_exc
                    raise
            if root_span is not None:
                root_span.set_attribute("vantage.workflow_status", "failed")
                root_span.set_attribute("vantage.research_status", "failed")
                root_span.set_attribute("error.type", exc.code)
            raise VantageError(
                code=exc.code,
                safe_message=exc.safe_message,
                retryable=exc.retryable,
                run_id=str(row.public_id),
            ) from exc
        except Exception as exc:
            logger.error("Unexpected internal error in research run")
            code = "INTERNAL_ERROR"
            safe_message = "An internal error occurred while processing research run."
            with tracer.start_as_current_span("persist_result") as p_span:
                p_span.set_attribute("vantage.run_id", str(row.public_id))
                try:
                    self.repo.finalize_failure(
                        internal_id=row.id,
                        user_id=user_id,
                        error_code=code,
                        error_message_safe=safe_message,
                    )
                except VantageError as finalization_exc:
                    if finalization_exc.code == RUN_ALREADY_FINALIZED:
                        raise VantageError(
                            code=finalization_exc.code,
                            safe_message=finalization_exc.safe_message,
                            retryable=finalization_exc.retryable,
                            run_id=str(row.public_id),
                        ) from finalization_exc
                    raise
            if root_span is not None:
                root_span.set_attribute("vantage.workflow_status", "failed")
                root_span.set_attribute("vantage.research_status", "failed")
                root_span.set_attribute("error.type", code)
            raise VantageError(
                code=code,
                safe_message=safe_message,
                retryable=False,
                run_id=str(row.public_id),
            ) from exc


@lru_cache(maxsize=1)
def get_research_service() -> ResearchRunService:
    """Build the process-local stateless research service once.

    Per-run data is passed to ``create`` and graph invocation state; the cached
    service contains only reusable providers, repository behavior, versions,
    and the compiled workflow.
    """
    return ResearchRunService()
