"""
slackapp_commands.py

Handles slash commands for the Slack AI Chatbot application.

This module defines and registers handlers for various slash commands
that users can invoke within the Slack workspace. These commands provide
functionality for reporting bugs, requesting features, enabling/
disabling channel summarisation, and initiating the creation of reports.

The module uses the "slack_bolt" framework for handling commands and
interacts with MongoDB to store and retrieve data related to bug
reports, feature requests, and summarisation settings.

Functions:
- bug_report: Handles the "/ai-bug-report" command to
    submit a bug report.
- feature_request: Handles the "/ai-feature-request" command to submit
    a feature request.
- search_enable: Handles the "/ai-search-enable" command to allow
  summarisation of a private channel.
- search_disable: Handles the "/ai-search-disable" command to disallow
  summarisation of a private channel.
- create_report: Handles the "create_report" action through a shortcut.

Attributes:
    slackapp (App): The Slack app instance (from "slack_bolt").
    timezone (pytz.timezone): The timezone for the application.
    bug_reports (Collection): MongoDB collection for storing
        bug reports.
    feature_requests (Collection): MongoDB collection for storing
        feature requests.
    summarisation (Collection): MongoDB collection for storing
        summarisation settings for channels.
    slack_bot_user_id (str): The user ID of the Slack bot.
"""

import datetime

from utils.logging_utils import log_message
from utils.logging_utils import error_handler
from agentic_workflow.workflow import report_agentic_workflow
from agentic_workflow.threads_data import enter_agentic_workflow
from agentic_workflow.input_agents import wait_for_feedback_periodically
from envbase import (
    slackapp,
    timezone,
    bug_reports,
    feature_requests,
    summarisation,
    slack_bot_user_id
)

@slackapp.command("/ai-bug-report")
def bug_report(
        ack: callable,
        body: dict,
        client: object,
) -> None:
    """
    Slack command to report a bug.

    When the command is used with a text after it, the text is
    appended to the bug report collection.

    Args:
        ack (callable): Acknowledges the command.
        body (dict): The body of the command.
        client (object): The Slack client.

    Returns:
        None
    """
    ack()

    # If a text is not provided, send a message to the user
    if not body.get("text", "").strip():
        client.chat_postMessage(
            channel=body["user_id"],
            text="Please provide a bug report."
        )
        return

    # Get the text after the command
    text = body["text"].strip()

    # Current time (YYYY-MM-DD-HH:MM:SS) in the timezone
    current_time = datetime.datetime.now(timezone).strftime(
        "%Y-%m-%d %H:%M:%S")

    # Create a document to insert
    bug_report_data = {
        "user_id": body["user_id"],
        "user_name": body["user_name"],
        "text": text,
        "timestamp": current_time,
    }

    # Insert the bug report into the collection
    bug_reports.insert_one(bug_report_data)

    # Send a response back to the user's private messages
    client.chat_postMessage(
        channel=body["user_id"],
        text=f"Bug report added: {text}"
    )


@slackapp.command("/ai-feature-request")
def feature_request(
        ack: callable,
        body: dict,
        client: object,
) -> None:
    """
    Slack command to request a feature.

    When the command is used with a text after it, the text is
    appended to the feature request collection.

    Args:
        ack (callable): Acknowledges the command.
        body (dict): The body of the command.
        client (object): The Slack client.

    Returns:
        None
    """
    ack()

    # Current time (YYYY-MM-DD-HH:MM:SS) in the timezone
    current_time = datetime.datetime.now(timezone).strftime(
        "%Y-%m-%d %H:%M:%S")

    # If a text is not provided, send a message to the user
    if not body.get("text", "").strip():
        client.chat_postMessage(
            channel=body["user_id"],
            text="Please provide a feature request."
        )
        return

    # Get the text after the command
    text = body["text"].strip()

    # Create a document to insert
    feature_request_data = {
        "user_id": body["user_id"],
        "user_name": body["user_name"],
        "text": text,
        "timestamp": current_time
    }

    # Insert the bug report into the collection
    feature_requests.insert_one(feature_request_data)

    # Send a response back to the user's private messages
    client.chat_postMessage(
        channel=body["user_id"],
        text=f"Feature request added: {text}"
    )


@slackapp.command("/ai-search-enable")
def search_enable(
        ack: callable,
        body: dict,
        client: object,
) -> None:
    """
    Slack command to allow for summarisation of a private channel.

    When the command is used, the channel ID is appended to the 
    "summarisation" collection in MongoDB. This allows private Slack
    channels to be summarised.

    Args:
        ack (callable): Acknowledges the command.
        body (dict): The body of the command.
        client (object): The Slack client.

    Returns:
        None
    
    Raises:
        Exception: Raised in case of errors while
            updating the collection.
    """
    ack()

    # Current time (YYYY-MM-DD-HH:MM:SS) in the timezone
    current_time = datetime.datetime.now(timezone).strftime(
        "%Y-%m-%d %H:%M:%S")

    # Get public channels
    response_public = client.conversations_list(types="public_channel")
    public_channels = {channel["id"] for channel in response_public.get(
        "channels", [])}

    # Get private channels
    response_private = client.conversations_list(types="private_channel")
    private_channels = {channel["id"] for channel in response_private.get(
        "channels", [])}

    # If the channel is a public_channel, reject the command
    if body["channel_id"] in public_channels:
        client.chat_postMessage(
            channel=body["user_id"],
            text="Public channels are always summarised"
        )
        return

    # If the channel is not a private_channel, reject the command
    # (Most likely a direct message or group chat)
    elif body["channel_id"] not in private_channels:
        client.chat_postMessage(
            channel=body["user_id"],
            text="Direct messages and group chats are always ignored."
        )
        return

    try:
        # Check if the channel is already allowed for summarisation
        existing_channel = summarisation.find_one(
            {"channel_id": body["channel_id"]})
        if existing_channel:
            client.chat_postMessage(
                channel=body["user_id"],
                text="This channel is already allowed for summarisation."
            )
            return

        # Add the channel to the "summarisation" collection
        summarisation_data = {
            "channel_id": body["channel_id"],
            "channel_name": body["channel_name"],
            "user_id": body["user_id"],
            "user_name": body["user_name"],
            "timestamp": current_time
        }
        summarisation.insert_one(summarisation_data)

        client.chat_postMessage(
            channel=body["user_id"],
            text="Channel will now be allowed for summarisation."
        )
    except Exception as e:
        client.chat_postMessage(
            channel=body["user_id"],
            text=("An error occurred while updating the "
                  f"summarisation collection: {str(e)}")
        )


@slackapp.command("/ai-search-disable")
def search_disable(
        ack: callable,
        body: dict,
        client: object,
) -> None:
    """
    Slack command to disallow summarisation of a private channel.

    When the command is used, the channel ID is removed from the
    "summarisation" collection in MongoDB.

    Args:
        ack (callable): Acknowledges the command.
        body (dict): The body of the command.
        client (object): The Slack client.

    Returns:
        None
    
    Raises:
        Exception: Raised in case of errors while
            updating the collection.
    """
    ack()

    try:
        # Check if the channel is already disallowed for summarisation
        existing_channel = summarisation.find_one(
            {"channel_id": body["channel_id"]})
        if not existing_channel:
            client.chat_postMessage(
                channel=body["user_id"],
                text="This channel is already disallowed for summarisation."
            )
            return

        # Remove the channel from the "summarisation" collection
        summarisation.delete_one({"channel_id": body["channel_id"]})

        client.chat_postMessage(
            channel=body["user_id"],
            text="Channel will no longer be allowed for summarisation."
        )
    except Exception as e:
        client.chat_postMessage(
            channel=body["user_id"],
            text=("An error occurred while updating the "
                  f"summarisation collection: {str(e)}")
        )


@slackapp.action("create_report")
def create_report(
        ack: callable,
        body: dict,
        client: object,
        say: callable,
) -> None:
    """
    DEPRECATED: Slack command to create a report.
    This function now only returns a deprecation message.
    """
    try:
        ack()
    except Exception:
        return

    try:
        user_id = body['user']['id']
        
        channel_id = body.get('container', {}).get('channel_id')

        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=":warning: **Feature Deprecated:** The 'Create Report' workflow is no longer available via this button."
        )

    except Exception as e:
        log_message(f"Error sending deprecation notice: {e}")

    # ---------------------------------------------------------
    # ORIGINAL LOGIC (Preserved but disabled)
    # ---------------------------------------------------------
    """
    try:
        # Extract user ID from the body
        user_id = body['user']['id']

        try:
            dm_channel_id = client.conversations_open(
                users=user_id)["channel"]["id"]
            message_response = client.chat_postMessage(
                channel=dm_channel_id,
                text="So you wanted to create a report?"
            )
            thread_ts = message_response["ts"]
            # Send a message in the thread
            response = client.chat_postMessage(
                channel=dm_channel_id,
                text=("Please write a brief description of what "
                    "you want to create. :pencil2:"),
                thread_ts=thread_ts
            )
            enter_agentic_workflow(thread_ts)
            latest_ts = response['ts']
            text, _ = wait_for_feedback_periodically(
                client,
                dm_channel_id,
                thread_ts,
                latest_ts,
                slack_bot_user_id,
                max_wait_time=300,
                state = "info"
            )
            if text is False:
                client.chat_postMessage(
                    channel=dm_channel_id,
                    text="Timeout - No response.",
                    thread_ts=thread_ts
                )
                return

        except Exception as e:
            raise

        # Extract the event_ts and channel_id from the body,
        # handling missing keys
        event_ts = body.get('container', {}).get('message_ts', None)

        # If event_ts is missing, fallback to using
        # message_response's timestamp
        if event_ts is None:
            event_ts = message_response['ts']

        # Report the agentic workflow
        report_agentic_workflow(
            client,
            text,
            thread_ts,
            event_ts,
            dm_channel_id,
            slack_bot_user_id,
            say
        )

    except Exception as e:
        error_handler(e, client, dm_channel_id, say, thread_ts,
                      event_ts, context="Error: Report creation.")
    """
