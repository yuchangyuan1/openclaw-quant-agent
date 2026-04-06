from services.planner.pipeline import (
    classify_intent,
    execute_daily_report_request,
    execute_doc_qa,
    execute_message,
    execute_quant_query,
    execute_risk_query,
    execute_weekly_report_request,
    format_doc_qa_reply,
)


def test_classify_intent_defaults_to_doc_qa():
    assert classify_intent("贵州茅台近期公告") == "DOC_QA"


def test_classify_intent_risk_query():
    assert classify_intent("当前组合最大回撤风险如何？") == "RISK_QUERY"


def test_classify_intent_daily_and_weekly_report():
    assert classify_intent("请生成今日日报") == "DAILY_REPORT"
    assert classify_intent("请生成本周周报") == "WEEKLY_REPORT"


def test_format_doc_qa_reply_contains_required_fields():
    reply = format_doc_qa_reply(
        "测试问题",
        {
            "synthesis": "根据现有证据...[E001]",
            "coverage_warning": None,
            "latest_evidence_date": "2026-04-05",
            "company_terms": ["贵州茅台"],
            "matched_companies": ["600519"],
            "matched_themes": ["AI算力"],
            "evidence_pack": [{"source": "eastmoney"}],
            "graph_context": {
                "companies": [{"name": "贵州茅台"}],
                "themes": [{"name": "AI算力"}],
                "industries": [{"name": "食品饮料"}],
                "relations": [{"src": "贵州茅台", "relation_type": "has_theme", "dst": "AI算力"}],
            },
        },
    )
    assert "**查询公司词项**" in reply
    assert "**研究命中公司**" in reply
    assert "贵州茅台(600519)" in reply
    assert "**研究命中主题**" in reply
    assert "**图谱关联公司**" in reply
    assert "**图谱关联行业**" in reply
    assert "**证据数量**" in reply
    assert "**数据来源**" in reply
    assert "**Critic 校验**" in reply
    assert "**协作路径**：Planner -> Knowledge" in reply


def test_execute_doc_qa_returns_planner_response(monkeypatch):
    monkeypatch.setattr("services.planner.pipeline.build_index", lambda *_args, **_kwargs: {"status": "completed"})
    captured = {}

    def fake_run_knowledge_agent(**kwargs):
        captured.update(kwargs)
        return type(
            "KnowledgeResult",
            (),
            {
                "agent_id": "knowledge",
                "payload": {
                    "evidence_pack": [
                        {
                            "source": "eastmoney",
                            "title": "测试标题",
                            "published_at": "2026-04-05",
                            "company_code": "600519",
                            "matched_themes": ["白酒"],
                        }
                    ],
                    "synthesis": "根据现有证据，[E001] 提供了直接说明。",
                    "latest_evidence_date": "2026-04-05",
                    "company_terms": kwargs["company_terms"],
                    "matched_companies": ["600519"],
                    "matched_themes": ["白酒"],
                    "graph_context": {
                        "companies": [{"name": "贵州茅台"}],
                        "themes": [{"name": "白酒"}],
                        "industries": [{"name": "食品饮料"}],
                        "relations": [{"src": "贵州茅台", "relation_type": "belongs_to_industry", "dst": "食品饮料"}],
                    },
                    "coverage_warning": None,
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_knowledge_agent", fake_run_knowledge_agent)

    result = execute_doc_qa("贵州茅台近期公告")
    assert result.intent == "DOC_QA"
    assert result.reply_markdown
    assert "图谱关联公司" in result.reply_markdown
    assert captured["company_terms"] == ["贵州茅台"]
    assert result.company_terms == ["贵州茅台"]
    assert result.matched_companies == ["600519"]
    assert result.matched_company_names == ["贵州茅台"]
    assert result.matched_themes == ["白酒"]
    assert result.collaboration_agents == ["planner", "knowledge"]


def test_execute_doc_qa_extracts_non_pool_company_terms(monkeypatch):
    monkeypatch.setattr("services.planner.pipeline.build_index", lambda *_args, **_kwargs: {"status": "completed"})
    captured = {}

    def fake_run_knowledge_agent(**kwargs):
        captured.update(kwargs)
        return type(
            "KnowledgeResult",
            (),
            {
                "agent_id": "knowledge",
                "payload": {
                    "evidence_pack": [],
                    "synthesis": "根据现有证据，暂未检索到直接相关资料。",
                    "latest_evidence_date": None,
                    "company_terms": kwargs["company_terms"],
                    "matched_companies": [],
                    "matched_themes": [],
                    "graph_context": {"companies": [], "themes": [], "industries": [], "relations": []},
                    "coverage_warning": "未找到相关文档",
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_knowledge_agent", fake_run_knowledge_agent)

    result = execute_doc_qa("兴发集团利润分配预案公告")
    assert result.company_terms == ["兴发集团", "兴发"]
    assert captured["stock_codes"] == []


def test_execute_quant_query_uses_quant_collaboration(monkeypatch):
    def fake_run_quant_agent(**kwargs):
        return type(
            "QuantResult",
            (),
            {
                "agent_id": "quant",
                "payload": {
                    "trade_date": "2026-04-03",
                    "stocks": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "close": 1460.0,
                            "pct_change": 0.01,
                            "pe_ttm": 21.2,
                            "roe": 24.6,
                            "composite_signal": "POSITIVE",
                        }
                    ],
                },
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_quant_agent", fake_run_quant_agent)
    result = execute_quant_query("贵州茅台量化指标")
    assert result.intent == "QUANT_QUERY"
    assert "协作路径：Planner -> Quant" in result.reply_markdown
    assert result.collaboration_agents == ["planner", "quant"]


def test_execute_risk_query_uses_risk_collaboration(monkeypatch):
    def fake_run_risk_agent(**kwargs):
        return type(
            "RiskResult",
            (),
            {
                "agent_id": "risk",
                "payload": {"risk_level": "MEDIUM", "alerts": ["行业集中度偏高"]},
            },
        )()

    monkeypatch.setattr("services.planner.pipeline.run_risk_agent", fake_run_risk_agent)
    result = execute_risk_query("贵州茅台持仓风险")
    assert result.intent == "RISK_QUERY"
    assert "协作路径：Planner -> Risk" in result.reply_markdown
    assert result.collaboration_agents == ["planner", "risk"]


def test_execute_message_routes_daily_report(monkeypatch):
    monkeypatch.setattr(
        "services.planner.pipeline.execute_daily_report",
        lambda stock_codes=None: type(
            "DailyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/daily.md",
                    "feishu_summary": "daily summary",
                },
                "critic_payload": {"status": "PASS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "daily_report_archive"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["600519"],
                    "matched_themes": [],
                },
            },
        )(),
    )
    result = execute_message("请生成贵州茅台日报", refresh_index=False)
    assert result.intent == "DAILY_REPORT"
    assert result.critic_status == "PASS"
    assert "日报已生成" in result.reply_markdown
    assert result.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]


def test_execute_daily_and_weekly_report_request(monkeypatch):
    monkeypatch.setattr(
        "services.planner.pipeline.execute_daily_report",
        lambda stock_codes=None: type(
            "DailyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/daily.md",
                    "feishu_summary": "daily summary",
                },
                "critic_payload": {"status": "PASS_WITH_WARNINGS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "eastmoney"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["600519"],
                    "matched_themes": [],
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "services.planner.pipeline.execute_weekly_report",
        lambda stock_codes=None: type(
            "WeeklyResult",
            (),
            {
                "report_payload": {
                    "report_date": "2026-04-06",
                    "file_path": "D:/tmp/weekly.md",
                    "feishu_summary": "weekly summary",
                },
                "critic_payload": {"status": "PASS"},
                "evidence_payload": {
                    "evidence_pack": [{"source": "daily_report_archive"}],
                    "latest_evidence_date": "2026-04-06",
                    "matched_companies": ["600519", "300750"],
                    "matched_themes": [],
                    "data_dates_label": "2026-03-30 to 2026-04-05",
                },
            },
        )(),
    )

    daily = execute_daily_report_request("请生成贵州茅台日报")
    weekly = execute_weekly_report_request("请生成本周周报")
    assert daily.intent == "DAILY_REPORT"
    assert weekly.intent == "WEEKLY_REPORT"
    assert "D:/tmp/daily.md" in daily.reply_markdown
    assert "D:/tmp/weekly.md" in weekly.reply_markdown
    assert daily.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]
    assert weekly.collaboration_agents == ["planner", "knowledge", "quant", "risk", "report", "critic"]
