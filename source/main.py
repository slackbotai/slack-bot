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

import time
import threading
from http.client import IncompleteRead

from slack_sdk.errors import SlackApiError
from slack_bolt.adapter.socket_mode import SocketModeHandler

from envbase import slackapp, slack_app_token
from channelreader import run_fetch_and_save_slack_data
from slackapp_events import handle_reaction_added_events, message
from slackapp_commands import (
    bug_report,
    feature_request,
    search_enable,
    search_disable,
    create_report
)
from utils.logging_utils import log_error, log_message

def main(retry=3,) -> None:
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
    # Add commands to the Slack app
    slackapp.command("/ai-bug-report")(bug_report)
    slackapp.command("/ai-feature-request")(feature_request)
    slackapp.command("/ai-search-enable")(search_enable)
    slackapp.command("/ai-search-disable")(search_disable)
    slackapp.global_shortcut("create_report")(create_report)
    # Add events to the Slack app
    slackapp.event("reaction_added")(handle_reaction_added_events)
    slackapp.message(message)

    scheduler_thread = threading.Thread(target=run_fetch_and_save_slack_data)
    # Ensures the thread will exit when the main program exits
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Retry connecting to Slack if there is an error
    while retry > 0:
        try:
            # Start the Slack App
            handler = SocketModeHandler(slackapp, slack_app_token)
            handler.start()
        except (SlackApiError, IncompleteRead):
            retry -= 1
            log_message(
                f"Failed to connect to Slack. Retrying... {retry} retries left.",
                "warning"
            )
            time.sleep(2)  # Short delay before retrying
        else:
            # Exit loop if handler starts successfully
            break
    else:
        # All retries failed
        log_message("Failed to connect to Slack after multiple retries.", "critical")

if __name__ == "__main__":
    main()
