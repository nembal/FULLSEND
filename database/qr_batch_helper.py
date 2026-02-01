"""
QR Batch Helper Module
Provides Python utilities for interacting with the qr_batch PostgreSQL table.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor, Json


class QRBatchDB:
    """Helper class for QR batch database operations."""
    
    def __init__(self, connection_string: str):
        """
        Initialize database connection.
        
        Args:
            connection_string: PostgreSQL connection string
                e.g., "postgresql://user:password@localhost:5432/dbname"
        """
        self.connection_string = connection_string
        self.conn = None
    
    def connect(self):
        """Establish database connection."""
        self.conn = psycopg2.connect(self.connection_string)
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def create_batch(
        self,
        parent_id: str,
        ar_mural_id: str,
        badge_status: str,
        qr_payload: Dict[str, Any],
        short_url: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new QR batch record.
        
        Args:
            parent_id: Parent identifier
            ar_mural_id: AR mural identifier
            badge_status: Status ('active', 'inactive', 'pending', 'expired')
            qr_payload: JSONB payload as dictionary
            short_url: Optional short URL
            batch_id: Optional explicit UUID
        
        Returns:
            Dict containing the created record
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if batch_id:
                query = """
                    INSERT INTO qr_batch 
                    (batch_id, parent_id, ar_mural_id, badge_status, qr_payload, short_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *;
                """
                cur.execute(query, (
                    batch_id, parent_id, ar_mural_id, badge_status,
                    Json(qr_payload), short_url
                ))
            else:
                query = """
                    INSERT INTO qr_batch 
                    (parent_id, ar_mural_id, badge_status, qr_payload, short_url)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *;
                """
                cur.execute(query, (
                    parent_id, ar_mural_id, badge_status,
                    Json(qr_payload), short_url
                ))
            
            self.conn.commit()
            result = cur.fetchone()
            return dict(result) if result else None
    
    def get_batch_by_id(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get QR batch by batch_id."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM qr_batch WHERE batch_id = %s;", (batch_id,))
            result = cur.fetchone()
            return dict(result) if result else None
    
    def get_batches_by_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """Get all QR batches for a given parent_id."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM qr_batch WHERE parent_id = %s ORDER BY created_at DESC;",
                (parent_id,)
            )
            return [dict(row) for row in cur.fetchall()]
    
    def get_batches_by_ar_mural(self, ar_mural_id: str) -> List[Dict[str, Any]]:
        """Get all QR batches for a given AR mural ID."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM qr_batch WHERE ar_mural_id = %s ORDER BY created_at DESC;",
                (ar_mural_id,)
            )
            return [dict(row) for row in cur.fetchall()]
    
    def get_batch_by_short_url(self, short_url: str) -> Optional[Dict[str, Any]]:
        """Get QR batch by short URL (for real-time lookup)."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM qr_batch WHERE short_url = %s;", (short_url,))
            result = cur.fetchone()
            return dict(result) if result else None
    
    def get_batches_by_status(self, badge_status: str) -> List[Dict[str, Any]]:
        """Get all QR batches with a specific status."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM qr_batch WHERE badge_status = %s ORDER BY created_at DESC;",
                (badge_status,)
            )
            return [dict(row) for row in cur.fetchall()]
    
    def update_badge_status(self, batch_id: str, new_status: str) -> bool:
        """Update the badge status of a QR batch."""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE qr_batch SET badge_status = %s WHERE batch_id = %s;",
                (new_status, batch_id)
            )
            self.conn.commit()
            return cur.rowcount > 0
    
    def update_short_url(self, batch_id: str, short_url: str) -> bool:
        """Update the short URL of a QR batch."""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE qr_batch SET short_url = %s WHERE batch_id = %s;",
                (short_url, batch_id)
            )
            self.conn.commit()
            return cur.rowcount > 0
    
    def update_payload(self, batch_id: str, payload_updates: Dict[str, Any]) -> bool:
        """
        Update (merge) QR payload fields.
        
        Args:
            batch_id: Batch ID to update
            payload_updates: Dictionary of fields to merge into existing payload
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE qr_batch SET qr_payload = qr_payload || %s WHERE batch_id = %s;",
                (Json(payload_updates), batch_id)
            )
            self.conn.commit()
            return cur.rowcount > 0
    
    def delete_batch(self, batch_id: str) -> bool:
        """Delete a QR batch."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM qr_batch WHERE batch_id = %s;", (batch_id,))
            self.conn.commit()
            return cur.rowcount > 0
    
    def get_batches_without_short_url(self) -> List[Dict[str, Any]]:
        """Get all batches that don't have a short URL yet."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM qr_batch WHERE short_url IS NULL ORDER BY created_at DESC;"
            )
            return [dict(row) for row in cur.fetchall()]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics for QR batches."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_batches,
                    COUNT(CASE WHEN badge_status = 'active' THEN 1 END) as active_count,
                    COUNT(CASE WHEN badge_status = 'inactive' THEN 1 END) as inactive_count,
                    COUNT(CASE WHEN badge_status = 'pending' THEN 1 END) as pending_count,
                    COUNT(CASE WHEN badge_status = 'expired' THEN 1 END) as expired_count,
                    COUNT(CASE WHEN short_url IS NULL THEN 1 END) as missing_short_url,
                    MIN(created_at) as earliest_batch,
                    MAX(created_at) as latest_batch
                FROM qr_batch;
            """)
            result = cur.fetchone()
            return dict(result) if result else {}
    
    def bulk_create_batches(self, batches: List[Dict[str, Any]]) -> int:
        """
        Bulk insert multiple QR batches.
        
        Args:
            batches: List of batch dictionaries with keys:
                    parent_id, ar_mural_id, badge_status, qr_payload, short_url (optional)
        
        Returns:
            Number of records inserted
        """
        with self.conn.cursor() as cur:
            query = """
                INSERT INTO qr_batch 
                (parent_id, ar_mural_id, badge_status, qr_payload, short_url)
                VALUES (%s, %s, %s, %s, %s);
            """
            data = [
                (
                    batch['parent_id'],
                    batch['ar_mural_id'],
                    batch['badge_status'],
                    Json(batch['qr_payload']),
                    batch.get('short_url')
                )
                for batch in batches
            ]
            cur.executemany(query, data)
            self.conn.commit()
            return cur.rowcount


# Example usage
if __name__ == "__main__":
    # Example connection string (replace with your actual credentials)
    conn_str = "postgresql://user:password@localhost:5432/gtm_db"
    
    # Using context manager
    with QRBatchDB(conn_str) as db:
        # Create a new batch
        new_batch = db.create_batch(
            parent_id="parent_001",
            ar_mural_id="ar_mural_123",
            badge_status="active",
            qr_payload={
                "campaign": "summer_2026",
                "product": "plastic_cup",
                "batch_number": 1001,
                "metadata": {
                    "location": "warehouse_a",
                    "quantity": 1000
                }
            },
            short_url="https://qr.ly/abc123"
        )
        print(f"Created batch: {new_batch['batch_id']}")
        
        # Get batch by ID
        batch = db.get_batch_by_id(new_batch['batch_id'])
        print(f"Retrieved batch: {batch}")
        
        # Get batches by parent
        parent_batches = db.get_batches_by_parent("parent_001")
        print(f"Found {len(parent_batches)} batches for parent_001")
        
        # Lookup by short URL (real-time lookup scenario)
        batch_by_url = db.get_batch_by_short_url("https://qr.ly/abc123")
        print(f"Lookup by URL: {batch_by_url['batch_id']}")
        
        # Update badge status
        db.update_badge_status(new_batch['batch_id'], "inactive")
        print("Updated badge status to inactive")
        
        # Get statistics
        stats = db.get_statistics()
        print(f"Statistics: {stats}")
        
        # Bulk create example
        bulk_batches = [
            {
                "parent_id": f"parent_{i:03d}",
                "ar_mural_id": f"ar_mural_{i:03d}",
                "badge_status": "pending",
                "qr_payload": {
                    "campaign": "bulk_campaign",
                    "batch_number": 2000 + i
                },
                "short_url": f"https://qr.ly/bulk{i:03d}"
            }
            for i in range(1, 11)
        ]
        inserted = db.bulk_create_batches(bulk_batches)
        print(f"Bulk inserted {inserted} batches")
