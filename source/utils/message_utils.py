"""
message_utils.py

This module contains utility functions for processing Slack messages
and extracting relevant information from them.

Functions:
- is_relevant_message: Determine if the message event is relevant for
    further processing.
- extract_event_data: Extract essential data fields from a Slack event.
- is_direct_message: Check if the message is a direct message to the bot
    or mentions the bot.
- log_user_info: Log user information for debugging purposes.
- preprocess_user_input: Clean and prepare the user's input message and
    timestamp for processing.
- add_reaction: Add a specified reaction emoji to a message.
- remove_reaction: Remove a specified reaction emoji from a message.
- post_ephemeral_message_ok: Post an ephemeral message to the user.

Attributes:
    CHANNEL_PATTERN: A regular expression pattern for matching channel
        mentions in messages.
    slack_bot_user_id: The user ID of the Slack bot.
"""

import re

from slack_sdk.errors import SlackApiError

from envbase import slack_bot_user_id

CHANNEL_PATTERN = re.compile(r"<#([A-Z0-9]+)\|([a-z0-9_åäö\-]*)>")

def is_relevant_message(event: dict,) -> bool:
    """
    Determine if the message event is relevant for further processing.
    
    Args:
        event (dict): The Slack event data.
        
    Returns:
        bool: True if the message is relevant, otherwise False.
    """
    subtype = event.get("subtype")
    return subtype not in {"bot_message", "message_changed", "message_deleted"}


def extract_event_data(event: dict,) -> dict:
    """
    Extract essential data fields from a Slack event.
    
    Args:
        event (dict): The Slack event data.
        
    Returns:
        dict: A dictionary with extracted fields, such as 
        'user_input', 'event_ts', 'thread_ts', 'channel_id',
        and 'user_id'.
    """
    return {
        "user_input": event.get("text", "").strip(),
        "event_ts": event.get("ts"),
        "thread_ts": event.get("thread_ts"),
        "channel_id": event.get("channel"),
        "user_id": event.get("user"),
        "files": event.get("files", []),
    }


def is_direct_message(
        client: object,
        user_input: str,
        user_id: str,
        channel_id: str,
) -> bool:
    """
    Check if the message is a direct message to the bot or
    mentions the bot.

    Args:
        client (object): The Slack client instance.
        user_input (str): The content of the message.
        user_id (str): The Slack user ID of the message sender.
        channel_id (str): The Slack channel ID where the
            message was sent.

    Returns:
        bool: True if the message is a direct message to the
            bot or mentions the bot.
    
    Raises:
        Exception: If an error occurs while checking the message.
    """
    try:
        # Ignore messages from the bot itself
        if user_id == slack_bot_user_id:
            return False

        # Check if the message is from a DM or if it mentions the bot
        im_channel_id = client.conversations_open(
            users=[user_id]
            )["channel"]["id"]
        enable_dm_mode = channel_id == im_channel_id
        mentions_bot = user_input.startswith(f"<@{slack_bot_user_id}>")
        return bool(user_input) and (mentions_bot or enable_dm_mode)
    except SlackApiError as e:
        if e.response["error"] == "cannot_dm_bot":
            return False


def preprocess_user_input(
        user_input: str, 
        event_ts: str, 
        thread_ts: str
) -> tuple:
    """
    Clean the bot mention and check if a channel is tagged immediately after.
    
    Logic:
    1. Remove Bot mention.
    2. Check if the very first remaining characters are a channel tag.
    3. Return the cleaned text (keeping the channel tag) and a boolean flag.

    Returns:
        tuple: (cleaned_input, thread_ts, channel_detected)
    """
    # 1. Remove bot's mention
    # We strip() to ensure the channel tag moves to index 0 if it exists
    cleaned_input = user_input.replace(f"<@{slack_bot_user_id}>", "", 1).strip()

    # 2. Check for channel match at the START of the string
    # Pattern: <# followed by ID, optional name, ending with >
    match = re.match(r"<#[A-Z0-9]+(?:\|.*?)?>", cleaned_input)
    
    # Convert the match object to a simple True/False
    channel_detected = bool(match)

    # 3. Use event timestamp as thread timestamp if not provided
    if thread_ts is None:
        thread_ts = event_ts

    # Note: cleaned_input still contains the <#C123> tag if it was present
    return cleaned_input, thread_ts, channel_detected


def add_reaction(
        client: object,
        channel_id: str,
        timestamp: str,
        reaction_name: str,
) -> None:
    """
    Add a specified reaction emoji to a message.
    
    Args:
        client (object): The Slack client instance.
        channel_id (str): The channel ID where the message is located.
        timestamp (str): The message timestamp.
        reaction_name (str): The name of the reaction emoji.
        
    Returns:
        None
    """
    client.reactions_add(
        channel=channel_id,
        timestamp=timestamp,
        name=reaction_name
    )


def remove_reaction(
        client: object,
        channel_id: str,
        timestamp: str,
        reaction_name: str,
) -> None:
    """
    Remove a specified reaction emoji from a message.
    
    Args:
        client (object): The Slack client instance.
        channel_id (str): The channel ID where the message is located.
        timestamp (str): The message timestamp.
        reaction_name (str): The name of the reaction emoji.
        
    Returns:
        None
    """
    client.reactions_remove(
        channel=channel_id,
        timestamp=timestamp,
        name=reaction_name
    )


def post_ephemeral_message_ok(
        client:object,
        channel_id:str,
        user_id:str,
        thread_ts:str,
        text:str,
) -> None:
    """
    Post an ephemeral message to the user.

    Post an ephemeral message to the user in a thread with the
    specified text. Underneath the text, an "OK" button is displayed
    for the user to acknowledge. If the user clicks the button,
    the message will be dismissed.
    
    Args:
        client (object): The Slack client instance.
        channel_id (str): The channel ID where the message is located.
        user_id (str): The user ID to send the message to.
        thread_ts (str): The timestamp of the thread where the
            message is located.
        text (str): The text content of the message.
        
    Returns:
        None
    """
    client.chat_postEphemeral(
        channel=channel_id,
        user=user_id,
        thread_ts=thread_ts,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "OK"},
                        "action_id": "acknowledge_summary_warning",
                    }
                ],
            },
        ],
        text=text,
    )
