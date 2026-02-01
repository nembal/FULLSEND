-- Example SQL queries and operations for qr_batch table
-- This file demonstrates common operations for the QR batch system

-- ============================================================
-- INSERT EXAMPLES
-- ============================================================

-- Example 1: Insert a single QR batch record
INSERT INTO qr_batch (parent_id, ar_mural_id, badge_status, qr_payload, short_url)
VALUES (
    'parent_001',
    'ar_mural_123',
    'active',
    '{"campaign": "summer_2026", "product": "plastic_cup", "batch_number": 1001, "metadata": {"location": "warehouse_a"}}'::jsonb,
    'https://qr.ly/abc123'
);

-- Example 2: Insert multiple QR batch records
INSERT INTO qr_batch (parent_id, ar_mural_id, badge_status, qr_payload, short_url)
VALUES 
    ('parent_001', 'ar_mural_123', 'active', '{"campaign": "summer_2026", "batch_number": 1002}'::jsonb, 'https://qr.ly/abc124'),
    ('parent_002', 'ar_mural_124', 'pending', '{"campaign": "summer_2026", "batch_number": 1003}'::jsonb, 'https://qr.ly/abc125'),
    ('parent_003', 'ar_mural_125', 'active', '{"campaign": "fall_2026", "batch_number": 1004}'::jsonb, 'https://qr.ly/abc126');

-- Example 3: Insert with explicit batch_id
INSERT INTO qr_batch (batch_id, parent_id, ar_mural_id, badge_status, qr_payload, short_url)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'parent_004',
    'ar_mural_126',
    'active',
    '{"campaign": "winter_2026", "batch_number": 1005, "special": true}'::jsonb,
    'https://qr.ly/abc127'
);

-- ============================================================
-- SELECT/QUERY EXAMPLES
-- ============================================================

-- Example 4: Get all QR batches
SELECT * FROM qr_batch ORDER BY created_at DESC;

-- Example 5: Get QR batch by batch_id
SELECT * FROM qr_batch WHERE batch_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

-- Example 6: Get QR batches by parent_id
SELECT * FROM qr_batch WHERE parent_id = 'parent_001' ORDER BY created_at DESC;

-- Example 7: Get QR batches by AR mural ID
SELECT * FROM qr_batch WHERE ar_mural_id = 'ar_mural_123';

-- Example 8: Get QR batches by badge status
SELECT * FROM qr_batch WHERE badge_status = 'active' ORDER BY created_at DESC;

-- Example 9: Lookup QR batch by short URL (for real-time lookup)
SELECT * FROM qr_batch WHERE short_url = 'https://qr.ly/abc123';

-- Example 10: Get QR batches with specific JSONB payload values
SELECT * FROM qr_batch 
WHERE qr_payload->>'campaign' = 'summer_2026';

-- Example 11: Get QR batches with nested JSONB queries
SELECT * FROM qr_batch 
WHERE qr_payload->'metadata'->>'location' = 'warehouse_a';

-- Example 12: Get QR batches with JSONB array contains
SELECT * FROM qr_batch 
WHERE qr_payload ? 'special';

-- Example 13: Join-style query (parent_id and AR mural)
SELECT * FROM qr_batch 
WHERE parent_id = 'parent_001' AND ar_mural_id = 'ar_mural_123';

-- Example 14: Count batches by status
SELECT badge_status, COUNT(*) as count 
FROM qr_batch 
GROUP BY badge_status;

-- Example 15: Get recent batches (last 24 hours)
SELECT * FROM qr_batch 
WHERE created_at >= NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- ============================================================
-- UPDATE EXAMPLES
-- ============================================================

-- Example 16: Update badge status
UPDATE qr_batch 
SET badge_status = 'inactive'
WHERE batch_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

-- Example 17: Update short URL
UPDATE qr_batch 
SET short_url = 'https://qr.ly/new_abc123'
WHERE parent_id = 'parent_001' AND ar_mural_id = 'ar_mural_123';

-- Example 18: Update JSONB payload (merge)
UPDATE qr_batch 
SET qr_payload = qr_payload || '{"updated": true, "updated_date": "2026-02-01"}'::jsonb
WHERE batch_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

-- Example 19: Update specific JSONB field
UPDATE qr_batch 
SET qr_payload = jsonb_set(qr_payload, '{batch_number}', '2001')
WHERE parent_id = 'parent_001';

-- Example 20: Bulk update badge status
UPDATE qr_batch 
SET badge_status = 'expired'
WHERE created_at < NOW() - INTERVAL '30 days' 
  AND badge_status = 'active';

-- ============================================================
-- DELETE EXAMPLES
-- ============================================================

-- Example 21: Delete specific batch
DELETE FROM qr_batch WHERE batch_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

-- Example 22: Delete old expired batches
DELETE FROM qr_batch 
WHERE badge_status = 'expired' 
  AND created_at < NOW() - INTERVAL '90 days';

-- ============================================================
-- ADVANCED QUERIES
-- ============================================================

-- Example 23: Get statistics per parent_id
SELECT 
    parent_id,
    COUNT(*) as total_batches,
    COUNT(CASE WHEN badge_status = 'active' THEN 1 END) as active_batches,
    COUNT(CASE WHEN badge_status = 'inactive' THEN 1 END) as inactive_batches,
    COUNT(CASE WHEN badge_status = 'pending' THEN 1 END) as pending_batches,
    COUNT(CASE WHEN badge_status = 'expired' THEN 1 END) as expired_batches,
    MIN(created_at) as first_created,
    MAX(created_at) as last_created
FROM qr_batch
GROUP BY parent_id
ORDER BY total_batches DESC;

-- Example 24: Get batches with pagination
SELECT * FROM qr_batch 
ORDER BY created_at DESC 
LIMIT 10 OFFSET 0;

-- Example 25: Full-text search in JSONB payload
SELECT * FROM qr_batch 
WHERE qr_payload::text ILIKE '%summer_2026%';

-- Example 26: Get batches without short URLs (need generation)
SELECT * FROM qr_batch 
WHERE short_url IS NULL;

-- Example 27: Upsert (insert or update if exists)
INSERT INTO qr_batch (batch_id, parent_id, ar_mural_id, badge_status, qr_payload, short_url)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'parent_004',
    'ar_mural_126',
    'active',
    '{"campaign": "winter_2026", "batch_number": 1005}'::jsonb,
    'https://qr.ly/abc127'
)
ON CONFLICT (batch_id) DO UPDATE 
SET 
    badge_status = EXCLUDED.badge_status,
    qr_payload = EXCLUDED.qr_payload,
    short_url = EXCLUDED.short_url;

-- ============================================================
-- UTILITY QUERIES
-- ============================================================

-- Example 28: Check table size and row count
SELECT 
    pg_size_pretty(pg_total_relation_size('qr_batch')) as total_size,
    COUNT(*) as row_count
FROM qr_batch;

-- Example 29: Get index usage statistics
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE tablename = 'qr_batch'
ORDER BY idx_scan DESC;

-- Example 30: Validate badge_status constraint
SELECT DISTINCT badge_status FROM qr_batch;
