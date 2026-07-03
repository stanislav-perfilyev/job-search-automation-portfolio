-- ClickHouse: схема аналитического хранилища job-search системы
-- Запускается автоматически при старте clickhouse-server через docker entrypoint

CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.vacancy_events
(
    event_date  Date,
    event_time  DateTime,
    vacancy_id  UInt32,
    action      LowCardinality(String),   -- applied | interview | offer | rejected | new
    source      LowCardinality(String),   -- hh.kz | корп. сайт | LinkedIn | hh.ru
    company     String,
    salary_from Nullable(UInt32),
    skill_gaps  Array(String)
)
ENGINE = MergeTree()
ORDER BY (event_date, source, action)
SETTINGS index_granularity = 8192;

-- Витрина: агрегированные конверсии по источникам (обновляется через MATERIALIZED VIEW)
CREATE TABLE IF NOT EXISTS analytics.source_conversion
(
    month       Date,
    source      LowCardinality(String),
    applied     UInt32  DEFAULT 0,
    interview   UInt32  DEFAULT 0,
    offer       UInt32  DEFAULT 0,
    rejected    UInt32  DEFAULT 0
)
ENGINE = SummingMergeTree()
ORDER BY (month, source);

-- Витрина: skill_gap тренды по месяцам
CREATE TABLE IF NOT EXISTS analytics.skill_gap_monthly
(
    month      Date,
    skill      String,
    cnt        UInt32  DEFAULT 0
)
ENGINE = SummingMergeTree()
ORDER BY (month, skill);
