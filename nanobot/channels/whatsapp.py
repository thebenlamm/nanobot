"""WhatsApp channel implementation using Node.js bridge."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WhatsAppConfig

# Directory for storing monitored group message logs
GROUP_LOG_DIR = Path.home() / ".nanobot" / "group-logs"


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel that connects to a Node.js bridge.

    The bridge uses @whiskeysockets/baileys to handle the WhatsApp Web protocol.
    Communication between Python and Node.js is via WebSocket.

    Group messages from monitored groups are logged silently for daily digests.
    The bot never responds in group chats.
    """

    name = "whatsapp"

    def __init__(self, config: WhatsAppConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WhatsAppConfig = config
        self._ws = None
        self._connected = False
        GROUP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    async def start(self) -> None:
        """Start the WhatsApp channel by connecting to the bridge."""
        import websockets
        
        bridge_url = self.config.bridge_url
        
        logger.info(f"Connecting to WhatsApp bridge at {bridge_url}...")
        
        self._running = True
        
        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("Connected to WhatsApp bridge")
                    
                    # Listen for messages
                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error(f"Error handling bridge message: {e}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning(f"WhatsApp bridge connection error: {e}")
                
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
    
    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        self._running = False
        self._connected = False
        
        if self._ws:
            await self._ws.close()
            self._ws = None
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WhatsApp."""
        if not self._ws or not self._connected:
            logger.warning("WhatsApp bridge not connected")
            return
        
        try:
            payload = {
                "type": "send",
                "to": msg.chat_id,
                "text": msg.content
            }
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
    
    async def _handle_bridge_message(self, raw: str) -> None:
        """Handle a message from the bridge."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from bridge: {raw[:100]}")
            return
        
        msg_type = data.get("type")
        
        if msg_type == "message":
            # Incoming message from WhatsApp
            # Deprecated by whatsapp: old phone number style typically: <phone>@s.whatspp.net
            pn = data.get("pn", "")
            # New LID sytle typically: 
            sender = data.get("sender", "")
            content = data.get("content", "")
            
            # Extract just the phone number or lid as chat_id
            user_id = pn if pn else sender
            sender_id = user_id.split("@")[0] if "@" in user_id else user_id
            logger.info(f"Sender {sender}")
            
            # Group messages: log silently for digests, never respond
            if data.get("isGroup", False):
                group_jid = data.get("sender", "")
                monitored = self.config.monitor_groups
                # If monitor list is empty, log all groups; otherwise only monitored ones
                if not monitored or group_jid in monitored:
                    self._log_group_message(data)
                return

            # Handle voice transcription if it's a voice message
            if content == "[Voice Message]":
                logger.info(f"Voice message received from {sender_id}, but direct download from bridge is not yet supported.")
                content = "[Voice Message: Transcription not available for WhatsApp yet]"
            
            await self._handle_message(
                sender_id=sender_id,
                chat_id=sender,  # Use full LID for replies
                content=content,
                metadata={
                    "message_id": data.get("id"),
                    "timestamp": data.get("timestamp"),
                    "is_group": data.get("isGroup", False)
                }
            )
        
        elif msg_type == "status":
            # Connection status update
            status = data.get("status")
            logger.info(f"WhatsApp status: {status}")
            
            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False
        
        elif msg_type == "qr":
            # QR code for authentication
            logger.info("Scan QR code in the bridge terminal to connect WhatsApp")
        
        elif msg_type == "error":
            logger.error(f"WhatsApp bridge error: {data.get('error')}")

    def _log_group_message(self, data: dict) -> None:
        """Log a group message to disk for daily digest summaries."""
        group_jid = data.get("sender", "unknown")
        content = data.get("content", "")
        timestamp = data.get("timestamp", 0)
        pn = data.get("pn", "")

        # Use date-based log files per group: group-logs/<group_jid>/2026-02-10.jsonl
        group_dir = GROUP_LOG_DIR / group_jid.replace("@", "_at_")
        group_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = group_dir / f"{today}.jsonl"

        entry = {
            "ts": timestamp,
            "sender": pn,
            "content": content,
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        logger.debug(f"Logged group message from {group_jid}")
