from datetime import datetime
import logging
from typing import Any, Literal
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
    ResearchRun,
    VersionInfo,
)
from app.providers.contracts import (
    InterpretationProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.prompts.research_interpretation import PROMPT_VERSION
from app.providers.llm import build_interpretation_provider
from app.providers.yfinance_provider import (
    YFinanceSnapshotProvider,
    latest_completed_xnys_close,
    snapshot_hash as market_snapshot_hash,
    trailing_xnys_sessions,
)
from app.repositories.research_runs import ResearchRunRepository
from app.services.metrics import METRICS_VERSION
from app.services.policy import POLICY_VERSION, PolicyResult
from app.telemetry.redaction import user_hash
from app.telemetry.tracing import get_tracer

logger = logging.getLogger(__name__)

RESPONSE_SCHEMA_VERSION: Literal["research-run-response-v2"] = (
    "research-run-response-v2"
)
WORKFLOW_VERSION: Literal["eod-research-v1"] = "eod-research-v1"


class ResearchRunService:
    def __init__(
        self,
        repo: ResearchRunRepository | None = None,
        market_provider: MarketDataProvider | None = None,
        news_provider: NewsProvider | None = None,
        interpretation_provider: InterpretationProvider | None = None,
        versions: VersionInfo | None = None,
    ) -> None:
        self.repo = repo or ResearchRunRepository()
        self.market = market_provider or YFinanceSnapshotProvider()
        self.news = news_provider or YFinanceSnapshotProvider()
        self.llm = interpretation_provider or build_interpretation_provider(settings)
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
        tracer = get_tracer()
        norm_symbol = symbol.strip().upper()

        if root_span is None:
            current_span = trace.get_current_span()
            if current_span.is_recording():
                root_span = current_span

        trace_id_hex = None
        if root_span is not None:
            span_ctx = root_span.get_span_context()
            if span_ctx and span_ctx.trace_id:
                trace_id_hex = f"{span_ctx.trace_id:032x}"
            root_span.set_attribute(
                "vantage.user_hash", user_hash(user_id, settings.TELEMETRY_USER_SALT)
            )
            root_span.set_attribute("vantage.instrument_symbol", norm_symbol)
            root_span.set_attribute("vantage.workflow_version", self.versions.workflow)
            root_span.set_attribute(
                "vantage.response_schema_version", self.versions.response_schema
            )
            root_span.set_attribute("gen_ai.provider.name", self.llm.name)
            root_span.set_attribute(
                "gen_ai.request.model", getattr(self.llm, "model", "default")
            )

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

        try:
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
                    source_type="news",
                )
                for item in news.items
            ]
            # Persist snapshot before invoking graph
            snapshot_hash = self.repo.save_snapshot(
                row.id, user_id, market, news, sources
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


def get_research_service() -> ResearchRunService:
    return ResearchRunService()
