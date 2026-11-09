-- Начальная миграция схемы plugin_test_plugin
CREATE TABLE IF NOT EXISTS plugin_test_plugin.test_items (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_plugin_test_plugin_created ON plugin_test_plugin.test_items(created_at);
