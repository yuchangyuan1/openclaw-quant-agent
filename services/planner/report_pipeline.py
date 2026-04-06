from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from services.common.audit import RunLogRepository
from services.common.paths import reports_dir
from services.common.retry import call_with_retry
from services.common.stocks import load_target_stocks
from services.critic.service import review_report
from services.quant.market_data import market_data_dir
from services.quant.service import daily_summary
from services.rag.knowledge_pipeline import build_evidence_pack
from services.report.service import build_report, finalize_report_with_critic
from services.risk.service import risk_check


@dataclass
class DailyReportResult:
    report_payload: dict
    critic_payload: dict
    evidence_payload: dict
    quant_payload: dict
    risk_payload: dict
    run_log_id: str | None = None
    attempts: dict[str, int] | None = None


@dataclass
class WeeklyReportResult:
    report_payload: dict
    critic_payload: dict
    evidence_payload: dict
    quant_payload: dict
    risk_payload: dict
    run_log_id: str | None = None
    attempts: dict[str, int] | None = None


def _run_logs() -> RunLogRepository:
    return RunLogRepository()


def execute_daily_report(report_date: str | None = None, stock_codes: list[str] | None = None) -> DailyReportResult:
    run_logs = _run_logs()
    resolved_date = report_date or date.today().isoformat()
    selected_codes = stock_codes or _default_stock_codes()
    weights = _equal_weights(selected_codes)
    run_record = run_logs.start_run(
        job_id=_build_job_id("daily_report", resolved_date),
        job_type="daily_report",
        input_params={"report_date": resolved_date, "stock_codes": selected_codes},
    )
    attempts: dict[str, int] = {}

    try:
        evidence_payload, attempts["knowledge"] = _run_step(
            lambda: build_evidence_pack(
                question="A股最新公告和新闻",
                stock_codes=selected_codes,
                doc_types=["news", "announcement"],
                days=7,
                top_k=5,
                min_score=0.1,
            )
        )
        quant_payload, attempts["quant"] = _run_step(lambda: daily_summary(selected_codes, resolved_date, indicators=[]))
        risk_payload, attempts["risk"] = _run_step(
            lambda: risk_check(
                portfolio=[{"code": code, "weight": weight} for code, weight in weights.items()],
                benchmark="000300",
                lookback_days=90,
                run_scenarios=True,
            )
        )
        report_payload, attempts["report"] = _run_step(
            lambda: build_report(
                report_type="daily",
                report_date=resolved_date,
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
                critic_status="PENDING",
            )
        )
        critic_payload, attempts["critic"] = _run_step(
            lambda: review_report(
                report_payload=report_payload,
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
            )
        )
        finalized_report, attempts["finalize"] = _run_step(lambda: finalize_report_with_critic(report_payload, critic_payload))
        run_logs.finish_run(
            run_record["id"],
            status="success",
            output_summary=_build_output_summary(
                report_payload=finalized_report,
                critic_payload=critic_payload,
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
                attempts=attempts,
            ),
        )
        return DailyReportResult(
            report_payload=finalized_report,
            critic_payload=critic_payload,
            evidence_payload=evidence_payload,
            quant_payload=quant_payload,
            risk_payload=risk_payload,
            run_log_id=run_record["id"],
            attempts=attempts,
        )
    except Exception as exc:
        run_logs.finish_run(
            run_record["id"],
            status="failed",
            output_summary={"attempts": attempts},
            error_message=str(exc),
        )
        raise


def execute_weekly_report(report_date: str | None = None, stock_codes: list[str] | None = None) -> WeeklyReportResult:
    run_logs = _run_logs()
    week_end = date.fromisoformat(report_date) if report_date else date.today()
    week_start = week_end - timedelta(days=6)
    selected_codes = stock_codes or _default_stock_codes()
    weights = _equal_weights(selected_codes)
    run_record = run_logs.start_run(
        job_id=_build_job_id("weekly_report", week_end.isoformat()),
        job_type="weekly_report",
        input_params={
            "report_date": week_end.isoformat(),
            "week_range": f"{week_start.isoformat()} to {week_end.isoformat()}",
            "stock_codes": selected_codes,
        },
    )
    attempts: dict[str, int] = {}

    try:
        archived_reports = _load_daily_archives(week_start, week_end)
        if not archived_reports:
            generated_daily = execute_daily_report(report_date=week_end.isoformat(), stock_codes=selected_codes)
            archived_reports = [
                {
                    "report_date": week_end.isoformat(),
                    "file_path": generated_daily.report_payload["file_path"],
                    "full_content": generated_daily.report_payload["full_content"],
                }
            ]

        evidence_payload, attempts["knowledge"] = _run_step(
            lambda: _build_weekly_evidence_payload(archived_reports, week_start, week_end, selected_codes)
        )
        quant_payload, attempts["quant"] = _run_step(lambda: daily_summary(selected_codes, week_end.isoformat(), indicators=[]))
        quant_payload = dict(quant_payload)
        market_summary = dict(quant_payload.get("market_summary", {}))
        market_summary["data_source"] = f"{len(archived_reports)}份日报归档 + 周末量化快照"
        quant_payload["market_summary"] = market_summary
        quant_payload["style_rotation"] = _build_weekly_style_rotation(quant_payload)
        risk_payload, attempts["risk"] = _run_step(
            lambda: risk_check(
                portfolio=[{"code": code, "weight": weight} for code, weight in weights.items()],
                benchmark="000300",
                lookback_days=90,
                run_scenarios=True,
            )
        )
        report_payload, attempts["report"] = _run_step(
            lambda: build_report(
                report_type="weekly",
                report_date=week_end.isoformat(),
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
                critic_status="PENDING",
            )
        )
        critic_payload, attempts["critic"] = _run_step(
            lambda: review_report(
                report_payload=report_payload,
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
            )
        )
        finalized_report, attempts["finalize"] = _run_step(lambda: finalize_report_with_critic(report_payload, critic_payload))
        run_logs.finish_run(
            run_record["id"],
            status="success",
            output_summary=_build_output_summary(
                report_payload=finalized_report,
                critic_payload=critic_payload,
                evidence_payload=evidence_payload,
                quant_payload=quant_payload,
                risk_payload=risk_payload,
                attempts=attempts,
            ),
        )
        return WeeklyReportResult(
            report_payload=finalized_report,
            critic_payload=critic_payload,
            evidence_payload=evidence_payload,
            quant_payload=quant_payload,
            risk_payload=risk_payload,
            run_log_id=run_record["id"],
            attempts=attempts,
        )
    except Exception as exc:
        run_logs.finish_run(
            run_record["id"],
            status="failed",
            output_summary={"attempts": attempts},
            error_message=str(exc),
        )
        raise


def list_recent_runs(limit: int = 20, job_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    return _run_logs().list_runs(limit=limit, job_type=job_type, status=status)


def replay_run(run_id: str) -> dict[str, Any]:
    run = _run_logs().get_run(run_id)
    input_params = run.get("input_params") or {}
    if run["job_type"] == "daily_report":
        result = execute_daily_report(
            report_date=input_params.get("report_date"),
            stock_codes=input_params.get("stock_codes") or None,
        )
        return {
            "source_run_id": run_id,
            "replayed_job_type": "daily_report",
            "new_run_log_id": result.run_log_id,
            "report_type": result.report_payload.get("report_type"),
            "report_date": result.report_payload.get("report_date"),
            "file_path": result.report_payload.get("file_path"),
            "critic_status": result.critic_payload.get("status"),
        }
    if run["job_type"] == "weekly_report":
        result = execute_weekly_report(
            report_date=input_params.get("report_date"),
            stock_codes=input_params.get("stock_codes") or None,
        )
        return {
            "source_run_id": run_id,
            "replayed_job_type": "weekly_report",
            "new_run_log_id": result.run_log_id,
            "report_type": result.report_payload.get("report_type"),
            "report_date": result.report_payload.get("report_date"),
            "file_path": result.report_payload.get("file_path"),
            "critic_status": result.critic_payload.get("status"),
        }
    raise ValueError(f"Replay is not supported for job_type={run['job_type']}")


def summarize_alerts(limit: int = 50) -> dict[str, Any]:
    runs = list_recent_runs(limit=limit)
    failed = [item for item in runs if item.get("status") == "failed"]
    running = [item for item in runs if item.get("status") == "running"]
    warning_runs = [
        item
        for item in runs
        if (item.get("output_summary") or {}).get("critic_status") in {"PASS_WITH_WARNINGS", "FAIL", "TIMEOUT"}
    ]
    latest_failure = failed[0] if failed else None
    latest_warning = warning_runs[0] if warning_runs else None
    return {
        "total_runs": len(runs),
        "failed_runs": len(failed),
        "running_runs": len(running),
        "warning_runs": len(warning_runs),
        "latest_failure": latest_failure,
        "latest_warning": latest_warning,
        "needs_attention": bool(failed or running or warning_runs),
    }


def _default_stock_codes() -> list[str]:
    available = []
    data_root = market_data_dir()
    for code in load_target_stocks():
        if (data_root / f"{code}_daily.parquet").exists() or (data_root / f"{code}_1y.parquet").exists():
            available.append(code)
    return available[:5] if available else ["600519", "000001", "300750", "601318", "300059"]


def _equal_weights(stock_codes: list[str]) -> dict[str, float]:
    if not stock_codes:
        return {}
    weight = round(1 / len(stock_codes), 4)
    weights = {code: weight for code in stock_codes}
    drift = round(1 - sum(weights.values()), 4)
    weights[stock_codes[0]] = round(weights[stock_codes[0]] + drift, 4)
    return weights


def _run_step(func: Callable[[], Any], attempts: int = 2) -> tuple[Any, int]:
    return call_with_retry(func, attempts=attempts)


def _build_job_id(job_type: str, report_date: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{job_type}:{report_date}:{stamp}"


def _build_output_summary(
    *,
    report_payload: dict,
    critic_payload: dict,
    evidence_payload: dict,
    quant_payload: dict,
    risk_payload: dict,
    attempts: dict[str, int],
) -> dict[str, Any]:
    return {
        "report_type": report_payload.get("report_type"),
        "report_date": report_payload.get("report_date"),
        "file_path": report_payload.get("file_path"),
        "critic_status": critic_payload.get("status"),
        "evidence_count": len(evidence_payload.get("evidence_pack", [])),
        "latest_evidence_date": evidence_payload.get("latest_evidence_date"),
        "trade_date": quant_payload.get("trade_date"),
        "risk_level": risk_payload.get("risk_level"),
        "attempts": attempts,
    }


def _load_daily_archives(week_start: date, week_end: date) -> list[dict]:
    archive_dir = reports_dir() / "daily"
    if not archive_dir.exists():
        return []

    archived_reports: list[dict] = []
    current = week_start
    while current <= week_end:
        path = archive_dir / f"{current.isoformat()}.md"
        if path.exists():
            archived_reports.append(
                {
                    "report_date": current.isoformat(),
                    "file_path": str(path),
                    "full_content": path.read_text(encoding="utf-8"),
                }
            )
        current += timedelta(days=1)
    return archived_reports


def _build_weekly_evidence_payload(
    archived_reports: list[dict],
    week_start: date,
    week_end: date,
    stock_codes: list[str],
) -> dict:
    evidence_pack = []
    for index, report in enumerate(archived_reports, start=1):
        evidence_pack.append(
            {
                "evidence_id": f"DR{index:03d}",
                "title": f"日报归档 {report['report_date']}",
                "source": "daily_report_archive",
                "published_at": report["report_date"],
                "snippet": _extract_summary_preview(report["full_content"]),
                "file_path": report["file_path"],
            }
        )

    latest_date = max((report["report_date"] for report in archived_reports), default=week_end.isoformat())
    return {
        "evidence_pack": evidence_pack,
        "synthesis": _build_weekly_synthesis(archived_reports, week_start, week_end),
        "matched_companies": stock_codes,
        "matched_themes": [],
        "latest_evidence_date": latest_date,
        "week_range": f"{week_start.isoformat()} to {week_end.isoformat()}",
        "report_week": week_end.isoformat(),
        "data_dates_label": f"{week_start.isoformat()} to {week_end.isoformat()}",
        "daily_report_count": len(archived_reports),
    }


def _extract_summary_preview(content: str) -> str:
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("##") or stripped.startswith("---"):
            continue
        lines.append(stripped)
        if len(lines) == 3:
            break
    return " | ".join(lines) if lines else "暂无摘要"


def _build_weekly_synthesis(archived_reports: list[dict], week_start: date, week_end: date) -> str:
    if not archived_reports:
        return f"{week_start.isoformat()} 至 {week_end.isoformat()} 未找到已归档日报。"

    report_dates = [report["report_date"] for report in archived_reports]
    return (
        f"本周周报基于 {len(archived_reports)} 份已归档日报汇总生成，"
        f"覆盖区间 {week_start.isoformat()} 至 {week_end.isoformat()}，"
        f"已纳入日报日期：{', '.join(report_dates)}。"
    )


def _build_weekly_style_rotation(quant_payload: dict) -> str:
    stocks = quant_payload.get("stocks", [])
    bullish = [item["name"] for item in stocks if item.get("ma_signal") == "bullish"]
    bearish = [item["name"] for item in stocks if item.get("ma_signal") == "bearish"]
    if bullish and bearish:
        return f"偏强：{', '.join(bullish[:3])}；偏弱：{', '.join(bearish[:3])}"
    if bullish:
        return f"偏强：{', '.join(bullish[:3])}"
    if bearish:
        return f"偏弱：{', '.join(bearish[:3])}"
    return "暂无明显风格切换"
