# Running Redis Without Docker

Docker Desktop isn't supported on older macOS. Use one of these instead.

---

## Option A: Homebrew (local Redis)

If you have [Homebrew](https://brew.sh):

```bash
# Install Redis
brew install redis

# Start Redis (runs in background until you stop it)
brew services start redis

# Or run in foreground for one session:
# redis-server
```

**Stop Redis:** `brew services stop redis`

**Test:** `redis-cli ping` → should reply `PONG`

Your app uses: `REDIS_URL=redis://localhost:6379`

---

## Option B: Upstash (hosted Redis, free tier)

No local install. You get a Redis URL and use it from anywhere.

1. Go to [upstash.com](https://upstash.com) and sign up (free).
2. Create a Redis database (choose a region).
3. Copy the **Redis URL** (e.g. `rediss://default:xxx@xxx.upstash.io:6379`).
4. Put it in your `.env`:
   ```
   REDIS_URL=rediss://default:YOUR_PASSWORD@YOUR_HOST.upstash.io:6379
   ```

Use that `REDIS_URL` in the orchestrator; no Docker or local Redis needed.

---

## Option C: Redis Cloud (hosted, free tier)

1. [Redis Cloud](https://redis.com/try-free/) – sign up and create a free database.
2. Get the public endpoint and password from the dashboard.
3. In `.env`:
   ```
   REDIS_URL=redis://default:YOUR_PASSWORD@YOUR_ENDPOINT:PORT
   ```
