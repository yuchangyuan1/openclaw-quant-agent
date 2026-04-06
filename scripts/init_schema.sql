-- 量化投研系统 Postgres Schema v1.0
-- 由 docker-compose 自动执行（首次启动时）

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. stocks — 目标股票池
-- ============================================================
CREATE TABLE IF NOT EXISTS stocks (
    code        VARCHAR(10) PRIMARY KEY,          -- 6 位股票代码，如 600519
    name        VARCHAR(50) NOT NULL,
    industry    VARCHAR(50),                       -- 申万一级行业
    tier        VARCHAR(20) DEFAULT 'core',        -- core | watchlist
    is_active   BOOLEAN DEFAULT TRUE,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE stocks IS '目标股票池，对应 docs/target-stocks.md';
COMMENT ON COLUMN stocks.tier IS 'core=核心标的，watchlist=观察标的';

-- ============================================================
-- 2. documents — 原始文档元数据
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(100) NOT NULL,         -- eastmoney | sse | szse | 10jqka
    doc_type        VARCHAR(50) NOT NULL,           -- news | announcement | research_report
    title           TEXT NOT NULL,
    url             TEXT,
    file_path       TEXT,                           -- 本地存储路径
    content_hash    VARCHAR(64) UNIQUE,             -- SHA-256，用于去重
    company_code    VARCHAR(10),                    -- 关联股票代码，NULL 表示市场级内容
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    is_indexed      BOOLEAN DEFAULT FALSE,          -- 是否已建向量索引
    is_duplicate    BOOLEAN DEFAULT FALSE,          -- 语义去重标记
    CONSTRAINT fk_company FOREIGN KEY (company_code) REFERENCES stocks(code) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_company ON documents(company_code);
CREATE INDEX IF NOT EXISTS idx_documents_published ON documents(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source, doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(is_indexed) WHERE is_indexed = FALSE;

COMMENT ON TABLE documents IS '原始文档元数据，原始文件存储于 data/raw/';

-- ============================================================
-- 3. daily_metrics — 日度行情与量化指标
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_code      VARCHAR(10) NOT NULL,
    trade_date      DATE NOT NULL,
    open_price      DECIMAL(12, 4),
    close_price     DECIMAL(12, 4),
    high_price      DECIMAL(12, 4),
    low_price       DECIMAL(12, 4),
    pct_change      DECIMAL(8, 4),                 -- 涨跌幅（%）
    volume          BIGINT,                         -- 成交量（手）
    turnover        DECIMAL(18, 2),                 -- 成交额（元）
    turnover_rate   DECIMAL(8, 4),                  -- 换手率（%）
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, trade_date),
    CONSTRAINT fk_stock FOREIGN KEY (stock_code) REFERENCES stocks(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_stock ON daily_metrics(stock_code, trade_date DESC);

COMMENT ON TABLE daily_metrics IS '日度行情，从 Akshare 获取后存储，Parquet 文件为主存储，此表为索引';

-- ============================================================
-- 4. reports — 日报/周报归档
-- ============================================================
CREATE TABLE IF NOT EXISTS reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type     VARCHAR(20) NOT NULL,           -- daily | weekly
    report_date     DATE NOT NULL,
    content         TEXT,                           -- Markdown 全文
    file_path       TEXT,                           -- 文件系统归档路径
    critic_status   VARCHAR(20) DEFAULT 'pending',  -- pending | pass | pass_with_warnings | fail | timeout
    critic_notes    TEXT,                           -- Critic Agent 的校验备注
    feishu_sent     BOOLEAN DEFAULT FALSE,
    feishu_msg_id   VARCHAR(100),                   -- 飞书消息 ID，用于追踪
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(report_type, report_date)
);

CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date DESC);

COMMENT ON TABLE reports IS '生成的投研报告归档';

-- ============================================================
-- 5. run_logs — 任务运行记录（可审计）
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(50) NOT NULL,
    entity_key      VARCHAR(255) NOT NULL,
    name            TEXT NOT NULL,
    alias_json      JSONB DEFAULT '[]'::jsonb,
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_type, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS document_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    mention_text    TEXT,
    mention_type    VARCHAR(50) DEFAULT 'extracted',
    start_offset    INTEGER,
    end_offset      INTEGER,
    confidence      DECIMAL(6, 4) DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, entity_id, mention_type)
);

CREATE INDEX IF NOT EXISTS idx_document_entities_doc ON document_entities(document_id);
CREATE INDEX IF NOT EXISTS idx_document_entities_entity ON document_entities(entity_id);

CREATE TABLE IF NOT EXISTS relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_entity_id   UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type   VARCHAR(50) NOT NULL,
    dst_entity_id   UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    weight          DECIMAL(8, 4) DEFAULT 1.0,
    confidence      DECIMAL(6, 4) DEFAULT 1.0,
    source_doc_id   UUID REFERENCES documents(id) ON DELETE CASCADE,
    valid_from      TIMESTAMPTZ,
    valid_to        TIMESTAMPTZ,
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_entity_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_entity_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_source_doc ON relations(source_doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_relations_edge ON relations (
    src_entity_id,
    relation_type,
    dst_entity_id,
    COALESCE(source_doc_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

CREATE TABLE IF NOT EXISTS entity_metric_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    metric_name     VARCHAR(100) NOT NULL,
    metric_value    DECIMAL(20, 6) NOT NULL,
    metric_date     DATE NOT NULL,
    source          VARCHAR(100) NOT NULL,
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_id, metric_name, metric_date, source)
);

CREATE INDEX IF NOT EXISTS idx_metric_snapshots_entity ON entity_metric_snapshots(entity_id, metric_date DESC);

CREATE TABLE IF NOT EXISTS entity_risk_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    risk_type       VARCHAR(100) NOT NULL,
    risk_level      VARCHAR(20) NOT NULL,
    risk_value      DECIMAL(20, 6),
    risk_date       DATE NOT NULL,
    source          VARCHAR(100) NOT NULL,
    metadata_json   JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_id, risk_type, risk_date, source)
);

CREATE INDEX IF NOT EXISTS idx_risk_snapshots_entity ON entity_risk_snapshots(entity_id, risk_date DESC);

CREATE TABLE IF NOT EXISTS run_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          VARCHAR(100) NOT NULL,           -- cron job id 或自定义 id
    job_type        VARCHAR(50),                     -- daily_report | weekly_report | data_fetch | qa_session
    status          VARCHAR(20) NOT NULL DEFAULT 'running',  -- running | success | failed | timeout
    input_params    JSONB,                           -- 输入参数快照
    output_summary  JSONB,                           -- 输出摘要（非全文）
    error_message   TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    duration_seconds INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_run_logs_job ON run_logs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_logs_status ON run_logs(status, started_at DESC);

COMMENT ON TABLE run_logs IS '所有任务的运行记录，保障可追踪性';

-- ============================================================
-- 初始数据：写入部分核心股票（用于验收测试）
-- ============================================================
INSERT INTO stocks (code, name, industry, tier) VALUES
    ('600519', '贵州茅台', '食品饮料', 'core'),
    ('000001', '平安银行', '银行', 'watchlist'),
    ('300750', '宁德时代', '电力设备', 'core'),
    ('601318', '中国平安', '非银金融', 'core'),
    ('300059', '东方财富', '非银金融', 'core')
ON CONFLICT (code) DO NOTHING;
