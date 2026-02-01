# Running RabbitMQ (no Docker)

The roundtable publishes tasks to a RabbitMQ queue (`fullsend.orchestrator.tasks`). You need a RabbitMQ server and `RABBITMQ_URL` in `.env`.

## Option 1: Local RabbitMQ with Homebrew (macOS)

1. **Install RabbitMQ** (installs Erlang if needed):
   ```bash
   brew update
   brew install rabbitmq
   ```

2. **Start RabbitMQ** (runs in background):
   ```bash
   brew services start rabbitmq
   ```

3. **Check it's running**: AMQP on `localhost:5672`. Management UI: http://localhost:15672 (default user/pass: `guest`/`guest`).

4. **In your `.env`** (or leave unset to use default):
   ```
   RABBITMQ_URL=amqp://localhost:5672/
   ```

To stop: `brew services stop rabbitmq`

---

## Option 2: Hosted RabbitMQ (no local install)

Use a free-tier hosted broker so you don’t run RabbitMQ on your machine.

1. Sign up for **CloudAMQP** (or similar): https://www.cloudamqp.com/ — create a small free instance.
2. Copy the **AMQP URL** (e.g. `amqp://user:pass@goose.rmq.cloudamqp.com/your-vhost`).
3. **In your `.env`**:
   ```
   RABBITMQ_URL=amqp://user:pass@goose.rmq.cloudamqp.com/your-vhost
   ```

No Docker or Homebrew required; the roundtable and future orchestrator use this URL.

---

## Optional

- `ORCHESTRATOR_QUEUE_NAME` — default `fullsend.orchestrator.tasks`. Only change if you want a different queue name.
- If `RABBITMQ_URL` is **not** set, the roundtable still runs but does **not** publish tasks to the queue (no error).
