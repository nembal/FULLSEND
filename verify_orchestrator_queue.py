#!/usr/bin/env python3
"""
Verify that the roundtable agent is writing to the orchestrator queue.
Connects to RabbitMQ, reports queue existence and message count, and optionally peeks at one task.
Usage: python verify_orchestrator_queue.py [--peek]
"""

import argparse
import json
import os
import sys

import pika
from dotenv import load_dotenv

load_dotenv()

DEFAULT_QUEUE_NAME = "fullsend.orchestrator.tasks"
DEFAULT_URL = "amqp://localhost:5672/"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify orchestrator queue has tasks from roundtable")
    parser.add_argument("--peek", action="store_true", help="Peek at one message (requeue it)")
    parser.add_argument("--show-all", action="store_true", help="Print every message (requeue each so queue is unchanged)")
    args = parser.parse_args()

    url = os.getenv("RABBITMQ_URL", DEFAULT_URL)
    queue_name = os.getenv("ORCHESTRATOR_QUEUE_NAME", DEFAULT_QUEUE_NAME)

    if not os.getenv("RABBITMQ_URL"):
        print("RABBITMQ_URL not set in environment. Set it in .env or export it.", file=sys.stderr)
        sys.exit(1)

    try:
        params = pika.URLParameters(url)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        # passive=True: do not create queue; raises if queue does not exist
        decl = ch.queue_declare(queue=queue_name, passive=True)
        message_count = decl.method.message_count
    except pika.exceptions.AMQPChannelError as e:
        if "NOT_FOUND" in str(e) or "404" in str(e):
            print(f"Queue {queue_name!r} does not exist yet. Run the roundtable with RABBITMQ_URL set to create it and publish tasks.")
        else:
            print(f"Channel error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Queue: {queue_name}")
    print(f"Messages in queue: {message_count}")

    if message_count == 0:
        print("No messages. Run the roundtable (with RABBITMQ_URL set) to publish tasks.")
        conn.close()
        return

    if args.show_all:
        print("\n--- All messages (consumed then re-published so queue unchanged) ---\n")
        collected: list[bytes] = []
        for i in range(message_count):
            method, _, body = ch.basic_get(queue=queue_name, auto_ack=True)
            if method and body:
                collected.append(body)
                try:
                    task = json.loads(body.decode("utf-8"))
                    print(f"[{i + 1}] order={task.get('order', '?')} topic={task.get('topic', '')[:60]}...")
                    print(json.dumps(task, indent=2))
                    print()
                except Exception:
                    print(f"[{i + 1}] (raw):", body.decode("utf-8", errors="replace"), "\n")
        for body in collected:
            ch.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2),
            )
    elif args.peek:
        method, _, body = ch.basic_get(queue=queue_name, auto_ack=False)
        if method:
            ch.basic_nack(method.delivery_tag, requeue=True)
            try:
                task = json.loads(body.decode("utf-8"))
                print("\nPeek (one message, requeued):")
                print(json.dumps(task, indent=2))
            except Exception:
                print("\nPeek (raw body):", body.decode("utf-8", errors="replace"))
        else:
            print("Peek: no message available (race with consumer?)")

    conn.close()
    print("OK: Agent is writing to the queue.")


if __name__ == "__main__":
    main()
