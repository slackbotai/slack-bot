"""
main.py

Entry point for the Slack AI Chatbot application.

This module serves as the main entry point for starting the Slack app.
It initialises the "slack_bolt" app, registers event and command
handlers from other modules, sets up a background thread for periodic
data fetching, and establishes a connection to Slack using Socket Mode.

Functions:
- main: Initialises the Slack app, registers handlers, starts the
    background thread, and connects to Slack using Socket Mode
    with retry logic.

Attributes:
    slackapp (App): The Slack app instance (from "slack_bolt").
    slack_app_token (str): The Slack app-level token.
"""

import os
import asyncio
import threading
from http.client import IncompleteRead

from slack_sdk.errors import SlackApiError
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from envbase import slackapp, slack_app_token
from channelreader import run_fetch_and_save_slack_data
# Import modules for their Bolt decorator registrations.
import slackapp_events
import slackapp_commands
from utils.logging_utils import log_error, log_message


def run_scheduler_or_exit() -> None:
    """
    Run the background Slack indexer and terminate the process on failure.

    Docker only restarts containers when the main process exits. Without
    this wrapper, the scheduler thread can crash while Socket Mode keeps the
    process alive, leaving the bot half-running and hard to diagnose.
    """
    try:
        run_fetch_and_save_slack_data()
    except Exception as e:
        log_error(e, "Background Slack indexing thread crashed.")
        os._exit(1)

async def main(retry=3,) -> None:
    """
    Main function to start the Slack app and connect to Slack.

    Args:
        retry (int): Number of retries to connect to Slack.
    
    Returns:
        None
    
    Raises:
        SlackApiError: If there is an error connecting to Slack.
        IncompleteRead: If the connection is incomplete.
    """
    scheduler_thread = threading.Thread(target=run_scheduler_or_exit)
    # Ensures the thread will exit when the main program exits
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Retry connecting to Slack if there is an error
    while retry > 0:
        try:
            # Start the Slack App
            handler = AsyncSocketModeHandler(slackapp, slack_app_token)
            await handler.start_async()
        except (SlackApiError, IncompleteRead):
            retry -= 1
            log_message(
                f"Failed to connect to Slack. "
                f"Retrying... {retry} retries left.",
                "warning"
            )
            await asyncio.sleep(2)  # Short delay before retrying
        else:
            # Exit loop if handler starts successfully
            break
    else:
        # All retries failed
        log_message(
            "Failed to connect to Slack after multiple retries.", "critical"
        )
if __name__ == "__main__":
    asyncio.run(main())
