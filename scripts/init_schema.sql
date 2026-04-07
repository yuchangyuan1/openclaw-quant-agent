CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS stocks (
    code        VARCHAR(10) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    industry    VARCHAR(100),
    tier        VARCHAR(20) DEFAULT 'core',
    is_active   BOOLEAN DEFAULT TRUE,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(100) NOT NULL,
    doc_type        VARCHAR(50) NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT,
    file_path       TEXT,
    content_hash    VARCHAR(64) UNIQUE,
    company_code    VARCHAR(10),
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    is_indexed      BOOLEAN DEFAULT FALSE,
    is_duplicate    BOOLEAN DEFAULT FALSE,
    CONSTRAINT fk_documents_company FOREIGN KEY (company_code) REFERENCES stocks(code) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_company ON documents(company_code);
CREATE INDEX IF NOT EXISTS idx_documents_published ON documents(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source, doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(is_indexed) WHERE is_indexed = FALSE;

CREATE TABLE IF NOT EXISTS daily_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_code      VARCHAR(10) NOT NULL,
    trade_date      DATE NOT NULL,
    open_price      DECIMAL(18, 6),
    close_price     DECIMAL(18, 6),
    high_price      DECIMAL(18, 6),
    low_price       DECIMAL(18, 6),
    pct_change      DECIMAL(12, 6),
    volume          BIGINT,
    turnover        DECIMAL(20, 2),
    turnover_rate   DECIMAL(12, 6),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stock_code, trade_date),
    CONSTRAINT fk_daily_metrics_stock FOREIGN KEY (stock_code) REFERENCES stocks(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_stock ON daily_metrics(stock_code, trade_date DESC);

CREATE TABLE IF NOT EXISTS reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type     VARCHAR(20) NOT NULL,
    report_date     DATE NOT NULL,
    content         TEXT,
    file_path       TEXT,
    critic_status   VARCHAR(20) DEFAULT 'pending',
    critic_notes    TEXT,
    feishu_sent     BOOLEAN DEFAULT FALSE,
    feishu_msg_id   VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(report_type, report_date)
);

CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date DESC);

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
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           VARCHAR(100) NOT NULL,
    job_type         VARCHAR(50),
    status           VARCHAR(20) NOT NULL DEFAULT 'running',
    input_params     JSONB,
    output_summary   JSONB,
    error_message    TEXT,
    started_at       TIMESTAMPTZ DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    duration_seconds INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_run_logs_job ON run_logs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_logs_status ON run_logs(status, started_at DESC);

INSERT INTO stocks (code, name, industry, tier) VALUES
    ('AAPL', 'Apple', 'Consumer Electronics', 'core'),
    ('MSFT', 'Microsoft', 'Software & Cloud', 'core'),
    ('GOOGL', 'Alphabet', 'Internet Platforms', 'core'),
    ('AMZN', 'Amazon', 'E-Commerce & Cloud', 'core'),
    ('META', 'Meta Platforms', 'Digital Advertising', 'core'),
    ('NVDA', 'NVIDIA', 'Semiconductors & AI Hardware', 'core'),
    ('TSLA', 'Tesla', 'EVs & Clean Energy', 'core')
ON CONFLICT (code) DO NOTHING;
