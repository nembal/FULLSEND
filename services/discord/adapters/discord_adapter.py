"""Discord bot adapter using discord.py."""

import asyncio
import json
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Settings, get_settings
from ..core.bus import RedisBus, publish_to_agent, subscribe_from_agent
from ..core.router import MessageRouter
from ..core.messages import (
    ActionRequest,
    AgentMessage,
    AgentMessageType,
    HumanMessage,
    HumanMessageType,
    IdeaSubmission,
)

logger = logging.getLogger(__name__)


class DiscordAdapter:
    """Discord bot adapter for Fullsend GTM agent communication."""

    def __init__(
        self,
        settings: Settings | None = None,
        redis_bus: RedisBus | None = None,
        message_router: MessageRouter | None = None,
    ) -> None:
        """Initialize the Discord adapter.

        Args:
            settings: Application settings. If None, loads from environment.
            redis_bus: Redis bus for publishing messages. If None, creates one.
            message_router: Message router for centralized subscriptions.
        """
        self.settings = settings or get_settings()
        self.paused = False  # Agent paused state
        self.redis_bus = redis_bus
        self.message_router = message_router
        self.reacted_messages: set[int] = set()  # Track messages we've reacted to
        self.pending_actions: dict[int, str] = {}  # Map message_id -> action_id for tracking action requests

        # Reaction emojis for action requests
        self.action_complete_emoji = "✅"
        self.action_reject_emoji = "❌"

        # Rate limiting for status posts (max 1 per 5 seconds)
        self._last_status_post_time: float = 0
        self._status_rate_limit_seconds: float = 5.0

        # Configure intents
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.reactions = True
        intents.message_content = True

        # Create bot instance
        self.bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            description="Fullsend GTM Agent Bot",
        )

        # Register event handlers
        self._register_events()

        # Register slash commands
        self._register_commands()

    def _register_events(self) -> None:
        """Register bot event handlers."""

        @self.bot.event
        async def on_ready() -> None:
            """Handle bot ready event."""
            logger.info(f"Bot logged in as {self.bot.user} (ID: {self.bot.user.id})")
            logger.info(f"Connected to {len(self.bot.guilds)} guild(s)")

            # Log connected guilds
            for guild in self.bot.guilds:
                logger.info(f"  - {guild.name} (ID: {guild.id})")

            # Sync slash commands with Discord
            try:
                synced = await self.bot.tree.sync()
                logger.info(f"Synced {len(synced)} slash command(s)")
            except Exception as e:
                logger.error(f"Failed to sync slash commands: {e}")

            logger.info("Discord adapter is ready")

            # Subscribe to agent messages from Redis
            await self._subscribe_to_agent_messages()

        @self.bot.event
        async def on_disconnect() -> None:
            """Handle bot disconnect event."""
            logger.warning("Bot disconnected from Discord")

        @self.bot.event
        async def on_resumed() -> None:
            """Handle bot resume event after disconnect."""
            logger.info("Bot connection resumed")

        @self.bot.event
        async def on_message(message: discord.Message) -> None:
            """Handle incoming messages for idea detection in listening channels."""
            # Ignore bot messages (including our own)
            if message.author.bot:
                return

            # Only process messages from configured listening channels
            channel_name = getattr(message.channel, "name", None)
            if not channel_name or channel_name not in self.settings.listening_channels_list:
                return

            # Ignore empty messages
            if not message.content or not message.content.strip():
                return

            # Check if we've already reacted to this message
            if message.id in self.reacted_messages:
                return

            # Log the detected potential idea
            logger.info(
                f"Potential idea detected in #{channel_name} from {message.author}: "
                f"{message.content[:100]}{'...' if len(message.content) > 100 else ''}"
            )

            # React with emoji (no text response in listening channels)
            try:
                await message.add_reaction(self.settings.idea_react_emoji)
                self.reacted_messages.add(message.id)
                logger.debug(f"Reacted to message {message.id} with {self.settings.idea_react_emoji}")
            except Exception as e:
                logger.error(f"Failed to add reaction to message {message.id}: {e}")

            # Process commands (if any prefix commands are used)
            await self.bot.process_commands(message)

        @self.bot.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None:
            """Handle reaction adds for action completion."""
            # Ignore bot reactions (including our own)
            if user.bot:
                return

            # Check if this is a pending action message
            message_id = reaction.message.id
            if message_id not in self.pending_actions:
                return

            action_id = self.pending_actions[message_id]
            emoji_str = str(reaction.emoji)

            # Determine completion status based on emoji
            if emoji_str == self.action_complete_emoji:
                status = "completed"
            elif emoji_str == self.action_reject_emoji:
                status = "rejected"
            else:
                return  # Not an action-related reaction

            logger.info(f"Action {action_id} marked as {status} by {user}")

            # Publish action_complete to Redis
            if self.redis_bus and self.redis_bus.is_connected:
                try:
                    human_message = HumanMessage(
                        type=HumanMessageType.ACTION_COMPLETE,
                        payload={
                            "action_id": action_id,
                            "status": status,
                            "completed_by": str(user.id),
                            "username": str(user),
                        },
                        source="discord",
                        user_id=str(user.id),
                    )
                    await publish_to_agent(self.redis_bus, human_message)
                    logger.info(f"Published action_complete for {action_id}")

                    # Update the message to show completion
                    try:
                        if status == "completed":
                            await reaction.message.reply(f"✅ Action marked as completed by {user.mention}")
                        else:
                            await reaction.message.reply(f"❌ Action rejected by {user.mention}")
                    except Exception as e:
                        logger.error(f"Failed to send completion reply: {e}")

                    # Remove from pending actions
                    del self.pending_actions[message_id]

                except Exception as e:
                    logger.error(f"Failed to publish action_complete: {e}")
            else:
                logger.warning(f"Cannot publish action_complete - Redis not connected")

    def _register_commands(self) -> None:
        """Register slash commands."""

        @self.bot.tree.command(name="status", description="Check if the agent is running")
        async def status(interaction: discord.Interaction) -> None:
            """Return agent status."""
            if self.paused:
                await interaction.response.send_message("⏸️ Agent is paused. Use `/go` to resume.")
            else:
                await interaction.response.send_message("✅ Agent is running...")

        @self.bot.tree.command(name="pause", description="Pause the agent")
        async def pause(interaction: discord.Interaction) -> None:
            """Pause the agent."""
            if self.paused:
                await interaction.response.send_message("⏸️ Agent is already paused.")
            else:
                self.paused = True
                logger.info(f"Agent paused by {interaction.user}")
                await interaction.response.send_message("⏸️ Agent paused. Use `/go` to resume.")

        @self.bot.tree.command(name="go", description="Resume the agent")
        async def go(interaction: discord.Interaction) -> None:
            """Resume the agent."""
            if not self.paused:
                await interaction.response.send_message("✅ Agent is already running.")
            else:
                self.paused = False
                logger.info(f"Agent resumed by {interaction.user}")
                await interaction.response.send_message("▶️ Agent resumed!")

        @self.bot.tree.command(name="idea", description="Submit an idea to the agent")
        @app_commands.describe(text="Your idea text")
        async def idea(interaction: discord.Interaction, text: str) -> None:
            """Submit an idea to the agent."""
            # Create IdeaSubmission
            idea_submission = IdeaSubmission(
                content=text,
                source_channel=str(interaction.channel_id),
                submitted_by=str(interaction.user.id),
                context={
                    "username": str(interaction.user),
                    "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
                    "channel_name": interaction.channel.name if hasattr(interaction.channel, "name") else None,
                },
            )

            # Wrap in HumanMessage for publishing
            human_message = HumanMessage(
                type=HumanMessageType.IDEA_SUBMIT,
                payload=idea_submission.model_dump(),
                source="discord",
                user_id=str(interaction.user.id),
            )

            # Publish to Redis if connected
            if self.redis_bus and self.redis_bus.is_connected:
                try:
                    await publish_to_agent(self.redis_bus, human_message)
                    logger.info(f"Idea submitted by {interaction.user}: {text[:50]}...")
                    await interaction.response.send_message(f"🎯 Idea received! Thanks for sharing.\n> {text}")
                except Exception as e:
                    logger.error(f"Failed to publish idea: {e}")
                    await interaction.response.send_message("❌ Failed to submit idea. Please try again later.")
            else:
                # No Redis connection, just acknowledge locally
                logger.info(f"Idea submitted (no Redis) by {interaction.user}: {text[:50]}...")
                await interaction.response.send_message(f"🎯 Idea noted! (offline mode)\n> {text}")

    async def _handle_agent_message(self, data: str) -> None:
        """Handle incoming messages from the agent/orchestrator via Redis.

        Args:
            data: JSON string of the message
        """
        try:
            message_data = json.loads(data)
            agent_message = AgentMessage(**message_data)

            # Handle action_request messages
            if agent_message.type == AgentMessageType.ACTION_REQUEST:
                await self._post_action_request(agent_message.payload)
            # Handle status_update, learning_share, win_alert (proactive posting)
            elif agent_message.type in (
                AgentMessageType.STATUS_UPDATE,
                AgentMessageType.LEARNING_SHARE,
                AgentMessageType.WIN_ALERT,
            ):
                await self._post_status_update(agent_message)
            else:
                logger.debug(f"Received agent message type: {agent_message.type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse agent message JSON: {e}")
        except Exception as e:
            logger.error(f"Error handling agent message: {e}")

    async def _post_action_request(self, payload: dict) -> None:
        """Post an action request to the status channel.

        Args:
            payload: Action request payload data
        """
        try:
            action = ActionRequest(**payload)
        except Exception as e:
            logger.error(f"Failed to parse action request payload: {e}")
            return

        # Find the status channel
        status_channel = None
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name == self.settings.status_channel:
                    status_channel = channel
                    break
            if status_channel:
                break

        if not status_channel:
            logger.error(f"Status channel '{self.settings.status_channel}' not found")
            return

        # Format the action request message
        assignee_text = f"\n**Assignee:** <@{action.assignee}>" if action.assignee else ""
        deadline_text = f"\n**Deadline:** {action.deadline.strftime('%Y-%m-%d %H:%M')}" if action.deadline else ""
        details_text = ""
        if action.details:
            details_items = "\n".join(f"  • {k}: {v}" for k, v in action.details.items())
            details_text = f"\n**Details:**\n{details_items}"

        message_content = (
            f"📋 **Action Request** [{action.action_type.value}]\n\n"
            f"**Description:** {action.description}"
            f"{assignee_text}"
            f"{deadline_text}"
            f"{details_text}\n\n"
            f"React with {self.action_complete_emoji} when done or {self.action_reject_emoji} to reject."
        )

        try:
            # Post the message
            message = await status_channel.send(message_content)

            # Add reaction buttons
            await message.add_reaction(self.action_complete_emoji)
            await message.add_reaction(self.action_reject_emoji)

            # Track the pending action
            self.pending_actions[message.id] = action.id
            logger.info(f"Posted action request {action.id} to #{status_channel.name}")

        except Exception as e:
            logger.error(f"Failed to post action request: {e}")

    def _can_post_status(self) -> bool:
        """Check if we can post a status update (rate limiting).

        Returns:
            True if enough time has passed since last post.
        """
        current_time = time.time()
        return (current_time - self._last_status_post_time) >= self._status_rate_limit_seconds

    async def _post_status_update(self, agent_message: AgentMessage) -> None:
        """Post a proactive status update to the status channel.

        Handles status_update, learning_share, and win_alert message types.
        Rate limited to max 1 post per 5 seconds.

        Args:
            agent_message: The agent message to post
        """
        # Rate limit check
        if not self._can_post_status():
            logger.debug(f"Rate limited status post: {agent_message.type}")
            return

        # Find the status channel
        status_channel = None
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name == self.settings.status_channel:
                    status_channel = channel
                    break
            if status_channel:
                break

        if not status_channel:
            logger.error(f"Status channel '{self.settings.status_channel}' not found")
            return

        # Format the message based on type
        payload = agent_message.payload
        timestamp_str = agent_message.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        if agent_message.type == AgentMessageType.STATUS_UPDATE:
            emoji = "📊"
            title = "Status Update"
            message_text = payload.get("message", payload.get("status", "Agent status updated"))
        elif agent_message.type == AgentMessageType.LEARNING_SHARE:
            emoji = "🧠"
            title = "Learning Share"
            message_text = payload.get("insight", payload.get("message", "New insight discovered"))
        elif agent_message.type == AgentMessageType.WIN_ALERT:
            emoji = "🎉"
            title = "Win Alert"
            message_text = payload.get("achievement", payload.get("message", "Achievement unlocked!"))
        else:
            emoji = "ℹ️"
            title = "Update"
            message_text = payload.get("message", str(payload))

        # Build the formatted message
        message_content = (
            f"{emoji} **{title}**\n\n"
            f"{message_text}\n\n"
            f"_🕐 {timestamp_str}_"
        )

        try:
            await status_channel.send(message_content)
            self._last_status_post_time = time.time()
            logger.info(f"Posted {agent_message.type.value} to #{status_channel.name}")
        except Exception as e:
            logger.error(f"Failed to post status update: {e}")

    async def _subscribe_to_agent_messages(self) -> None:
        """Subscribe to messages from the agent via Redis.

        Uses the message router if available, otherwise subscribes directly.
        """
        # Prefer using the message router for centralized subscription
        if self.message_router:
            self.message_router.register_handler(self._handle_agent_message)
            logger.info("Registered Discord adapter with message router")
            return

        # Fallback: subscribe directly to Redis
        if self.redis_bus and self.redis_bus.is_connected:
            try:
                await subscribe_from_agent(self.redis_bus, self._handle_agent_message)
                logger.info("Subscribed to agent messages from Redis (direct)")
            except Exception as e:
                logger.error(f"Failed to subscribe to agent messages: {e}")
        else:
            logger.warning("Cannot subscribe to agent messages - Redis not connected")

    async def start(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord adapter...")
        await self.bot.start(self.settings.discord_token)

    async def stop(self) -> None:
        """Stop the Discord bot gracefully."""
        logger.info("Stopping Discord adapter...")
        await self.bot.close()

    def run(self) -> None:
        """Run the Discord bot (blocking)."""
        logger.info("Running Discord adapter...")
        self.bot.run(self.settings.discord_token, log_handler=None)


async def run_discord_adapter(
    settings: Settings | None = None,
    redis_bus: RedisBus | None = None,
    message_router: MessageRouter | None = None,
) -> None:
    """Run the Discord adapter as an async task.

    Args:
        settings: Application settings. If None, loads from environment.
        redis_bus: Redis bus for publishing messages. If None, creates one.
        message_router: Message router for centralized subscriptions.
    """
    adapter = DiscordAdapter(settings, redis_bus, message_router)
    try:
        await adapter.start()
    except asyncio.CancelledError:
        await adapter.stop()
    except Exception as e:
        logger.error(f"Discord adapter error: {e}")
        await adapter.stop()
        raise
