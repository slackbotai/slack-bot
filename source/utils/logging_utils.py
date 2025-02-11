"""
This module provides utilities for handling errors and logging in a
Slack integration. It includes functionalities to log errors to MongoDB,
handle Slack message reactions, and communicate errors to users via
OpenAI responses.

Functions:
- log_error: Log error details to MongoDB.
- log_message: Log messages to MongoDB.
- error_handler: Handle errors by reacting, sending an error message,
    and logging.
"""

from datetime import datetime
import logging
import time
import traceback
import pytz

from envbase import logging as mongo_logging, timezone
from utils.message_utils import add_reaction, remove_reaction
from utils.openai_utils import openai_request
from prompts.prompts import error_message_prompt

# Create a logger (for console logging)
logger = logging.getLogger("slackbot")
logger.setLevel(logging.INFO)  # Set the overall logging level

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Log all messages to console

# Making sure envbase.timezone is defined, otherwise use a default
if timezone is None:  # Add this check
    timezone = pytz.utc
    print("WARNING: envbase.timezone is not set. Using UTC.")

def time_in_timezone(*args):
    """
    Converts the current time to the specified timezone.

    Args:
        timezone (str): The timezone to convert the time to.

    Returns:
        time.struct_time: A struct_time object representing the
            current time in the specified timezone.
    """
    return datetime.now(timezone).timetuple()

# Set the converter for the logging.Formatter
logging.Formatter.converter = time_in_timezone

# Define a logging format
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %Z%z",
)
console_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(console_handler)

def log_error(e: object, context: str):
    """
    Log error details to MongoDB.

    This function logs the exception type, message, and stack trace
    to a MongoDB collection. It also includes a custom context message
    to describe the situation in which the error occurred.

    Args:
        e (object): The exception object that was raised.
        context (str): A descriptive message providing context about
                       where and why the error occurred.

    Returns:
        None
    """
    stack_trace = traceback.format_exc()

    current_time = datetime.now(timezone)

    log_entry = {
        "timestamp": current_time,
        "context": context,
        "exception_type": type(e).__name__,
        "exception_message": str(e),
        "stack_trace": stack_trace,
        "level": "error"
    }
    try:
        mongo_logging.insert_one(log_entry)
    except Exception as db_error:
        print(f"Failed to log error to MongoDB: {db_error}")

    # Log to the console as a fallback
    logger.error(f"{context}")
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error(f"Exception message: {e}", exc_info=True)


def log_message(message: str, level: str = "info"):
    """
    Log a message to MongoDB at the specified log level.

    This function provides a consistent way to log messages.
    The log level can be adjusted based on the context.

    Args:
        message (str): The message to log.
        level (str): The log level for the message. Options are
                     'debug', 'info', 'warning', 'error', and 'critical'.
                     Default is 'info'.

    Returns:
        None
    """
    level = level.lower()

    current_time = datetime.now(timezone)

    log_entry = {
        "timestamp": current_time,
        "message": message,
        "level": level
    }
    try:
        mongo_logging.insert_one(log_entry)
    except Exception as db_error:
        print(f"Failed to log message to MongoDB: {db_error}")

    # Console logging for fallback
    if level == "debug":
        logger.debug(message)
    elif level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "critical":
        logger.critical(message)
    else:
        logger.info(message)

def error_handler(
    e: object,
    client: object,
    channel_id: str,
    say: callable,
    thread_ts: str,
    event_ts: str,
    sleep_time: int = 4,
    context: str = "Error",
) -> None:
    """
    Handle errors by reacting, sending an error message, and logging.

    This function handles errors by sending a reaction to the Slack message
    (an "x" reaction) and removing any existing "hourglass" reaction. The
    exception is logged to MongoDB with additional context. After handling
    the error, the user is informed with a message in the thread.

    Args:
        e (object): The raised Error.
        client (object): The Slack WebClient instance.
        channel_id (str): The ID of the Slack channel.
        say (callable): A function to send a message in the thread.
        thread_ts (str): The timestamp of the thread.
        event_ts (str): The timestamp of the event.
        sleep_time (int): Time to wait before sending the error message.
        context (str): Context string about the error.

    Returns:
        None
    """
    time.sleep(sleep_time)
    log_error(e, context)

    try:
        remove_reaction(
            client,
            channel_id,
            event_ts,
            "hourglass_flowing_sand"
        )
    except Exception as reaction_error:
        log_error(reaction_error, "Failed to remove reaction")

    try:
        add_reaction(
            client,
            channel_id,
            event_ts,
            "x"
        )
    except Exception as reaction_error:
        log_error(reaction_error, "Failed to add reaction")

    try:
        prompt = error_message_prompt(context, e)

        completion = openai_request(
            model="gpt-4o-mini",
            prompt=prompt
        )
        say(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"{completion.choices[0].message.content}"
        )
    except Exception as openai_error:
        log_error(
            openai_error, "Error during OpenAI request or sending message"
        )
    return
