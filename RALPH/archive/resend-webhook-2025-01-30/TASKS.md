# RALPH Tasks - Resend Webhook & Email Tracking

Reference: `docs/RESEND.md`

**Goal**: Implement Resend webhooks to track email bounces, complaints, opens, clicks, and delivery status. Update admin dashboard to display this data.

---

## Phase 1: Types & Schema

- [x] TASK-001: Create Resend Webhook Types

**File**: `lib/types/resend-webhook.ts`

**Goal**: Define TypeScript types for all Resend webhook event payloads

**Changes**:
1. Create new file `lib/types/resend-webhook.ts`
2. Define `ResendWebhookEvent` union type covering all event types:
   - `email.sent`
   - `email.delivered`
   - `email.delivery_delayed`
   - `email.bounced`
   - `email.complained`
   - `email.opened`
   - `email.clicked`
3. Define `ResendWebhookPayload` interface with:
   - `type`: event type string
   - `created_at`: ISO timestamp
   - `data`: event-specific data object
4. Define data interfaces for each event type:
   - `ResendEmailData` (common: email_id, from, to, subject)
   - `ResendBounceData` (extends with bounce type, message)
   - `ResendClickData` (extends with link URL)
5. Export all types

**Test**: `pnpm lint` should pass with no type errors

---

- [x] TASK-002: Create Resend Webhook Zod Schemas

**File**: `lib/schemas/resend-webhook.ts`

**Goal**: Zod validation schemas for webhook payloads

**Changes**:
1. Create new file `lib/schemas/resend-webhook.ts`
2. Import types from `lib/types/resend-webhook.ts`
3. Create `resendWebhookPayloadSchema` that validates:
   - `type` as enum of valid event types
   - `created_at` as string (ISO date)
   - `data` as object with `email_id` required
4. Create `resendWebhookHeadersSchema` for:
   - `svix-id`: string
   - `svix-timestamp`: string
   - `svix-signature`: string
5. Export schemas

**Test**: `pnpm lint` should pass

---

## Phase 2: Database Migration

- [x] TASK-003: Add delivered_at Column to email_tracking

**File**: `supabase/migrations/20250130000001_add_email_tracking_delivered_at.sql`

**Goal**: Add column to track delivery timestamp from Resend webhooks

**Changes**:
1. Create migration file
2. Add `delivered_at TIMESTAMPTZ` column to `email_tracking` table
3. Add comment explaining it's populated by Resend webhook

**SQL**:
```sql
-- Add delivered_at column for Resend webhook tracking
ALTER TABLE public.email_tracking
ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;

COMMENT ON COLUMN public.email_tracking.delivered_at IS 'Timestamp when email was delivered, populated by Resend webhook';
```

**Test**: Migration should apply without errors

---

- [x] TASK-004: Create email_suppression_list Table

**File**: `supabase/migrations/20250130000002_create_email_suppression_list.sql`

**Goal**: Table to track bounced/complained emails that should not receive future emails

**Changes**:
1. Create migration file
2. Create `email_suppression_list` table with columns:
   - `id` UUID primary key
   - `email` TEXT unique not null
   - `reason` TEXT not null ('bounce_hard', 'bounce_soft', 'complaint', 'unsubscribe')
   - `source_event_id` TEXT (Resend email_id that caused suppression)
   - `metadata` JSONB (bounce details, complaint info)
   - `created_at` TIMESTAMPTZ default now()
   - `expires_at` TIMESTAMPTZ (for soft bounces that can retry later)
3. Add index on `email` column
4. Add RLS policy: service role can read/write, no public access

**Test**: Migration should apply without errors

---

## Phase 3: Webhook Utilities

- [x] TASK-005: Create Webhook Signature Verification Utility

**File**: `lib/resend/verify-webhook.ts`

**Goal**: Verify Resend webhook signatures using Svix

**Changes**:
1. Create new file `lib/resend/verify-webhook.ts`
2. Import `Webhook` from `svix` package (already in dependencies)
3. Create `verifyResendWebhook` function that:
   - Takes `payload` (string), `headers` object
   - Gets `RESEND_WEBHOOK_SECRET` from env
   - Uses Svix `Webhook.verify()` to validate signature
   - Returns parsed payload or throws error
4. Export function

**Dependencies**: `svix` package (check if installed, add if needed)

**Test**: `pnpm lint` should pass

---

- [x] TASK-006: Create Email Suppression Check Utility

**File**: `lib/resend/check-suppression.ts`

**Goal**: Utility to check if an email is on the suppression list before sending

**Changes**:
1. Create new file `lib/resend/check-suppression.ts`
2. Create `isEmailSuppressed` async function that:
   - Takes `email` string and Supabase admin client
   - Queries `email_suppression_list` for matching email
   - For soft bounces, checks if `expires_at` has passed
   - Returns `{ suppressed: boolean, reason?: string }`
3. Create `addToSuppressionList` function that:
   - Takes suppression details and admin client
   - Upserts into `email_suppression_list`
   - Handles duplicate emails gracefully
4. Export both functions

**Test**: `pnpm lint` should pass

---

## Phase 4: Webhook API Route

- [x] TASK-007: Create Resend Webhook API Route

**File**: `app/api/webhooks/resend/route.ts`

**Goal**: Handle incoming Resend webhook events

**Changes**:
1. Create directory `app/api/webhooks/resend/`
2. Create `route.ts` with POST handler
3. Import verification utility and schemas
4. Handler logic:
   - Extract Svix headers from request
   - Get raw body text
   - Verify signature using utility
   - Parse and validate payload with Zod
   - Switch on event type:
     - `email.delivered`: update `delivered_at` in email_tracking
     - `email.opened`: update `opened_at` in email_tracking
     - `email.clicked`: update `clicked_at` in email_tracking
     - `email.bounced`: update status='bounced', `bounced_at`, add to suppression list
     - `email.complained`: update status='complained', add to suppression list
   - Match records by `resend_id` column in email_tracking
   - Return 200 OK on success, 400 on validation error, 500 on processing error
5. Add logging to `debug_logs` table for troubleshooting

**Test**: Deploy and test with Resend webhook tester

---

- [x] TASK-008: Add Webhook Event Logging

**File**: `app/api/webhooks/resend/route.ts`

**Goal**: Log all webhook events for debugging and audit

**Changes**:
1. At start of handler, log raw event to `debug_logs`:
   - `context`: 'resend_webhook'
   - `message`: event type
   - `data`: full payload (sanitized)
2. On successful processing, log outcome
3. On error, log error details
4. Ensure PII (email addresses) is handled appropriately in logs

**Test**: Check debug_logs after sending test webhook

---

## Phase 5: Admin Dashboard Updates

- [x] TASK-009: Update Admin Stats RPC for Email Metrics

**File**: `supabase/migrations/20250130000003_update_admin_dashboard_email_stats.sql`

**Goal**: Extend admin_dashboard_v2 RPC to include delivery/open/bounce rates

**Changes**:
1. Create migration file
2. Add to stats object returned by `admin_dashboard_v2`:
   - `emails_sent`: count of email_tracking records
   - `emails_delivered`: count where delivered_at is not null
   - `emails_opened`: count where opened_at is not null
   - `emails_bounced`: count where status = 'bounced'
   - `emails_complained`: count where status = 'complained'
   - `suppressed_count`: count from email_suppression_list
3. Calculate rates: `delivery_rate`, `open_rate`, `bounce_rate`

**Test**: Call RPC and verify new fields are present

---

- [x] TASK-010: Create EmailMetricsCard Component

**File**: `components/admin/components/EmailMetricsCard.tsx`

**Goal**: Card showing email delivery metrics

**Props**:
```typescript
interface EmailMetricsCardProps {
  stats: {
    emails_sent: number;
    emails_delivered: number;
    emails_opened: number;
    emails_bounced: number;
    emails_complained: number;
    suppressed_count: number;
  };
}
```

**Display**:
- Total Sent / Delivered / Opened as numbers
- Delivery rate, open rate as percentages
- Bounce + complaint count with warning styling if > 0
- Suppressed email count

**Uses**: Shadcn Card, existing admin styles

**Test**: Component renders without errors

---

- [x] TASK-011: Create SuppressionListTable Component

**File**: `components/admin/components/SuppressionListTable.tsx`

**Goal**: Table showing suppressed email addresses

**Props**:
```typescript
interface SuppressionListTableProps {
  suppressions: Array<{
    email: string;
    reason: string;
    created_at: string;
    expires_at: string | null;
  }>;
  isLoading: boolean;
}
```

**Display**:
- Table with columns: Email (masked: j***@example.com), Reason, Date, Expires
- Reason badges: hard bounce (red), soft bounce (yellow), complaint (orange), unsubscribe (gray)
- Empty state if no suppressions

**Test**: Component renders without errors

---

- [x] TASK-012: Add Suppression List API Route

**File**: `app/api/admin/suppressions/route.ts`

**Goal**: API to fetch suppression list for admin dashboard

**Changes**:
1. Create directory and route file
2. GET handler:
   - Check admin auth with `requireAdmin()`
   - Query `email_suppression_list` ordered by created_at desc
   - Limit to 100 most recent
   - Return JSON array
3. DELETE handler (optional):
   - Remove email from suppression list (for false positives)
   - Require admin auth

**Test**: `curl` endpoint with admin session

---

- [x] TASK-013: Update AdminDashboard with Email Metrics

**File**: `components/admin/AdminDashboard.tsx`

**Goal**: Integrate new email metrics components

**Changes**:
1. Update data fetching to include email stats from API
2. Add `<EmailMetricsCard />` in collapsible "Email Delivery" section
3. Add `<SuppressionListTable />` in collapsible "Suppressed Emails" section
4. Fetch suppression list from `/api/admin/suppressions`
5. Add refresh capability for email stats

**Test**: Admin dashboard loads with new sections

---

## Phase 6: Integration & Environment

- [x] TASK-014: Add RESEND_WEBHOOK_SECRET Environment Variable

**File**: `.env.example` and documentation

**Goal**: Document required environment variable

**Changes**:
1. Add to `.env.example`:
   ```
   # Resend webhook verification (get from Resend dashboard)
   RESEND_WEBHOOK_SECRET=whsec_...
   ```
2. Update `docs/RESEND.md` with webhook setup instructions:
   - Go to Resend dashboard > Webhooks
   - Create webhook pointing to `https://yourdomain.com/api/webhooks/resend`
   - Select events: delivered, opened, clicked, bounced, complained
   - Copy signing secret to env var
3. Add to Supabase dashboard env vars for production

**Test**: Verify env var is accessible in route handler

---

- [x] TASK-015: Add svix Package Dependency

**File**: `package.json`

**Goal**: Ensure svix package is installed for webhook verification

**Changes**:
1. Check if `svix` is in dependencies
2. If not, run `pnpm add svix`
3. Verify types are available

**Test**: `pnpm install` succeeds, no type errors

---

## Testing Checklist

After completing all tasks:

- [ ] Webhook endpoint returns 200 for valid signed requests
- [ ] Webhook endpoint returns 401 for invalid signatures
- [ ] email_tracking updates correctly for each event type
- [ ] Bounced emails are added to suppression list
- [ ] Admin dashboard shows email metrics
- [ ] Suppression list displays in admin dashboard
- [ ] All lint checks pass
- [ ] Build succeeds

---

## File Summary

**New Files**:
- `lib/types/resend-webhook.ts`
- `lib/schemas/resend-webhook.ts`
- `lib/resend/verify-webhook.ts`
- `lib/resend/check-suppression.ts`
- `app/api/webhooks/resend/route.ts`
- `app/api/admin/suppressions/route.ts`
- `components/admin/components/EmailMetricsCard.tsx`
- `components/admin/components/SuppressionListTable.tsx`
- `supabase/migrations/20250130000001_add_email_tracking_delivered_at.sql`
- `supabase/migrations/20250130000002_create_email_suppression_list.sql`
- `supabase/migrations/20250130000003_update_admin_dashboard_email_stats.sql`

**Modified Files**:
- `components/admin/AdminDashboard.tsx`
- `.env.example`
- `docs/RESEND.md`
- `package.json` (if svix not present)
