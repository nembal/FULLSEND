-- Migration: Create qr_batch table for GTM plastic cups QR code generation
-- Purpose: Store batch-specific QR payloads with parent_id, AR_mural_id, badge_status
--          and short URLs generated via Cloudflare Workers for real-time lookup

-- Create qr_batch table
CREATE TABLE IF NOT EXISTS qr_batch (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id VARCHAR(255) NOT NULL,
    ar_mural_id VARCHAR(255) NOT NULL,
    badge_status VARCHAR(50) NOT NULL CHECK (badge_status IN ('active', 'inactive', 'pending', 'expired')),
    qr_payload JSONB NOT NULL,
    short_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_qr_batch_parent_id ON qr_batch(parent_id);
CREATE INDEX IF NOT EXISTS idx_qr_batch_ar_mural_id ON qr_batch(ar_mural_id);
CREATE INDEX IF NOT EXISTS idx_qr_batch_badge_status ON qr_batch(badge_status);
CREATE INDEX IF NOT EXISTS idx_qr_batch_short_url ON qr_batch(short_url);
CREATE INDEX IF NOT EXISTS idx_qr_batch_created_at ON qr_batch(created_at DESC);

-- Create a GIN index on qr_payload JSONB column for efficient JSONB queries
CREATE INDEX IF NOT EXISTS idx_qr_batch_payload_gin ON qr_batch USING GIN (qr_payload);

-- Create a composite index for common lookup patterns
CREATE INDEX IF NOT EXISTS idx_qr_batch_parent_ar_mural ON qr_batch(parent_id, ar_mural_id);

-- Add comment to table
COMMENT ON TABLE qr_batch IS 'Stores batch-specific QR code payloads for GTM plastic cups with parent_id, AR_mural_id, badge_status, and Cloudflare short URLs';

-- Add column comments
COMMENT ON COLUMN qr_batch.batch_id IS 'Primary key, auto-generated UUID for each QR batch';
COMMENT ON COLUMN qr_batch.parent_id IS 'Parent identifier for the QR batch';
COMMENT ON COLUMN qr_batch.ar_mural_id IS 'AR mural identifier associated with this batch';
COMMENT ON COLUMN qr_batch.badge_status IS 'Status of the badge: active, inactive, pending, or expired';
COMMENT ON COLUMN qr_batch.qr_payload IS 'JSONB payload containing QR code data';
COMMENT ON COLUMN qr_batch.short_url IS 'Short URL generated via Cloudflare Workers';
COMMENT ON COLUMN qr_batch.created_at IS 'Timestamp when the record was created';
COMMENT ON COLUMN qr_batch.updated_at IS 'Timestamp when the record was last updated';

-- Create trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_qr_batch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_qr_batch_updated_at
    BEFORE UPDATE ON qr_batch
    FOR EACH ROW
    EXECUTE FUNCTION update_qr_batch_updated_at();
