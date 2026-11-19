CREATE SCHEMA IF NOT EXISTS local_search;

CREATE TABLE IF NOT EXISTS local_search.indexed_files (
    catalog_id text NOT NULL,
    path text NOT NULL,
    name text NOT NULL,
    extension text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    modified_at timestamptz NOT NULL,
    root text NOT NULL,
    PRIMARY KEY (catalog_id, path)
);
