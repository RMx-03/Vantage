from datetime import date, datetime, timedelta
import logging
from uuid import UUID

from app.agents.research_graph import create_research_graph
from app.core.config import settings
from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    EvidenceSource,
    ModelInfo,
    NewsSnapshot,
    ResearchRun,
    VersionInfo,
)
from app.providers.contracts import (
    InterpretationProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.providers.llm import build_interpretation_provider
from app.providers.yfinance_provider import (
    YFinanceSnapshotProvider,
    latest_completed_xnys_session,
)
from app.repositories.research_runs import ResearchRunRepository
from app.services.metrics import METRICS_VERSION
from app.services.policy import POLICY_VERSION, PolicyResult

from typing import Literal

logger = logging.getLogger(__name__)

CODE_VERSION = settings.APP_VERSION
RESPONSE_SCHEMA_VERSION: Literal["research-run-response-v1"] = "research-run-response-v1"
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
            code=CODE_VERSION,
        )
        self.workflow = create_research_graph(self.llm)

    @staticmethod
    def start_for(completed: date) -> date:
        return completed - timedelta(days=45)

    def create(self, *, user_id: UUID, symbol: str, now: datetime) -> ResearchRun:
        norm_symbol = symbol.strip().upper()
        row = self.repo.create_running(
            user_id=user_id, symbol=norm_symbol, versions=self.versions
        )
        try:
            completed = latest_completed_xnys_session(now)
            start_date = self.start_for(completed)
            market = self.market.fetch_daily_snapshot(
                norm_symbol, start_date, completed
            )
            try:
                news = self.news.fetch_company_news(norm_symbol, now, 10)
            except VantageError as exc:
                news = NewsSnapshot(
                    symbol=norm_symbol,
                    items=[],
                    provider=self.news.name,
                    retrieved_at=now,
                    quality=ComponentQuality.FAILED,
                    error_code=exc.code,
                )

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
            self.repo.save_snapshot(row.id, market, sources)

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
            model_info = ModelInfo(
                provider=self.llm.name,
                model=getattr(self.llm, "model", "default"),
                prompt_version="research-interpretation-v1",
                failure_code=failure_code,
            )

            return self.repo.finalize_success(
                internal_id=row.id,
                user_id=user_id,
                research_status=policy.research_status,
                as_of=market.as_of,
                reasons=policy.reasons,
                metrics=policy.metrics,
                data_quality=policy.data_quality,
                warnings=policy.warnings,
                summary=policy.summary,
                model_info=model_info,
            )
        except VantageError as exc:
            self.repo.finalize_failure(
                internal_id=row.id,
                user_id=user_id,
                error_code=exc.code,
                error_message_safe=exc.safe_message,
            )
            raise VantageError(
                code=exc.code,
                safe_message=exc.safe_message,
                retryable=exc.retryable,
                run_id=str(row.public_id),
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error in research run: %s", exc)
            code = "INTERNAL_ERROR"
            safe_message = "An internal error occurred while processing research run."
            self.repo.finalize_failure(
                internal_id=row.id,
                user_id=user_id,
                error_code=code,
                error_message_safe=safe_message,
            )
            raise VantageError(
                code=code,
                safe_message=safe_message,
                retryable=False,
                run_id=str(row.public_id),
            ) from exc


def get_research_service() -> ResearchRunService:
    return ResearchRunService()
