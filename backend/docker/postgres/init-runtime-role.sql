DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vantage_runtime') THEN
        CREATE ROLE vantage_runtime LOGIN PASSWORD 'vantage_runtime';
    END IF;
END
$$;
