"""
slack_utils.py

This module provides utility functions for interacting with the
Slack API, focusing on retrieving conversation history, thread messages,
and managing error handling and retries effectively.

Key Features:
    - Supports **pagination** for fetching large volumes of messages.
    - Implements **exponential backoff** for retrying failed API calls.
    - Handles transient errors gracefully, including `SlackApiError`
      and `IncompleteRead`.
    - Provides both **asynchronous** and **synchronous wrappers** for
      flexibility.

Functions:
    - exponential_backoff:
        Calculate delay times using exponential backoff.
    - get_conversations_history_async:
        Fetch message history from a Slack channel asynchronously.
    - get_thread_messages_async:
        Retrieve all messages from a Slack thread asynchronously.
    - get_thread_ts_list_from_slack_async:
        Extract timestamps of all messages in a Slack thread.
    - get_channel_name: Fetch the channel name from its ID using
      Slack's API.
    - get_conversations_history:
        Synchronous wrapper for `get_conversations_history_async`.
    - get_thread_messages:
        Synchronous wrapper for `get_thread_messages_async`.
    - get_thread_ts_list_from_slack:
        Synchronous wrapper for `get_thread_ts_list_from_slack_async`.

Error Handling:
    - Retries transient errors with an exponential backoff strategy.
    - Gracefully handles Slack rate-limiting errors (`ratelimited`)
      by respecting retry headers.
    - Logs meaningful error messages for debugging purposes.

Dependencies:
    - `slack_sdk`: For interacting with the Slack API.
    - `asyncio`: For managing asynchronous operations.
"""

import asyncio
import time
from http.client import IncompleteRead
from slack_sdk.errors import SlackApiError
from utils.logging_utils import log_error, log_message
from envbase import slackapp

# Global event for rate-limiting
rate_limited_event = asyncio.Event()
rate_limited_event.clear()  # Ensure it's unset initially

# Global flag for logging to prevent duplicate log messages
rate_limit_active = False

def exponential_backoff(attempt: int) -> int:
    """
    Calculate delay time using exponential backoff strategy.

    Args:
        attempt (int): The current retry attempt number.

    Returns:
        int: Delay time in seconds, capped at 60 seconds.
    """
    return min(2 ** attempt, 60)

async def get_conversations_history_async(
        client: object,
        channel_id: str,
        cursor: str = None,
        oldest: str = None,
        limit: int = 100,
        max_retries: int = 5,
        timeout: int = 10
    ) -> dict:
    """
    Fetch the message history for a specific Slack channel
    asynchronously.

    This function supports pagination, retry mechanisms, and timeout
    settings to ensure robustness when interacting with the Slack API.

    Args:
        client (object): Slack WebClient instance for API interaction.
        channel_id (str): ID of the Slack channel.
        cursor (str, optional):
            Pagination cursor for fetching the next batch.
        oldest (str, optional):
            Timestamp to filter messages older than this value.
        limit (int, optional):
            Maximum number of messages per API request. Default is 100.
        max_retries (int, optional):
            Maximum number of retry attempts. Default is 5.
        timeout (int, optional):
            Timeout for API calls in seconds. Default is 10.

    Returns:
        dict: Slack API response containing the conversation history.

    Raises:
        ValueError: If `channel_id` is not provided.
        RuntimeError: If the maximum retries are exhausted.
    """

    if not channel_id:
        raise ValueError(
            "The 'channel_id' must be provided and cannot be empty."
    )

    retries = 0
    while retries < max_retries:
        try:
            params = {
                "channel": channel_id,
                "limit": limit
            }
            if cursor:
                params["cursor"] = cursor
            if oldest:
                params["oldest"] = oldest

            # Call Slack API asynchronously
            response = await asyncio.to_thread(
                client.conversations_history, timeout=timeout, **params
            )

            if not response["ok"]:
                raise SlackApiError("API response not OK", response=response)

            return response

        except IncompleteRead as e:
            # Handle incomplete reads by reducing the batch size and
            # retrying
            log_error(e, "IncompleteRead error")
            log_message("Retrying with a smaller batch size.", "info")
            # Reduce limit but ensure it's at least 10
            limit = max(10, limit // 2)
            retries += 1
            await asyncio.sleep(exponential_backoff(retries))

        except SlackApiError as e:
            # Handle Slack API-specific errors and retry
            log_error(e, "Slack API Error.")
            log_message(f"Retrying in {5} seconds...", "info")
            retries += 1
            time.sleep(5) # Wait before retrying

    raise RuntimeError(
        "Failed to retrieve conversation history after max retries."
    )


async def get_thread_messages_async(
        client: object,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
        max_retries: int = 5
    ) -> object:
    """
    Retrieve all messages from a Slack thread asynchronously.

    Args:
        client (object): Slack WebClient instance for API interaction.
        channel_id (str): ID of the Slack channel.
        thread_ts (str): Timestamp of the thread's root message.
        limit (int, optional):
            Maximum number of messages per API request. Default is 100.
        max_retries (int, optional):
            Maximum number of retries. Default is 5.

    Returns:
        object: Slack API response containing thread messages.

    Raises:
        ValueError: If `channel_id` or `thread_ts` is not provided.
        RuntimeError: If maximum retries are exceeded.
    """
    if not channel_id or not thread_ts:
        raise ValueError(
            "Both 'channel_id' and 'thread_ts' must be provided."
        )

    retries = 0
    while retries < max_retries:
        try:
            # Wait if the rate limit event is active
            if rate_limited_event.is_set():
                await rate_limited_event.wait()

            response = await asyncio.to_thread(
                client.conversations_replies,
                channel=channel_id,
                ts=thread_ts,
                limit=limit
            )

            if not response["ok"]:
                raise SlackApiError("API response not OK", response=response)

            return response

        except IncompleteRead as e:
            # Handle incomplete reads by reducing batch size and retry
            log_message("IncompleteRead error. Retrying with a smaller batch size.", "warning")
            # Reduce the batch size but ensure it's at least 10
            limit = max(10, limit // 2)  # Reduce batch size for retries
            retries += 1
            time.sleep(5) # Pause before retrying
            # Swap asyncio.sleep with handle_rate_limit to get error out
            await asyncio.sleep(exponential_backoff(retries))

        except SlackApiError as e:
            # Handle Slack API errors and retry
            log_message(
                "Slack API Error. Retrying in 5 seconds...",
                "warning"
            )
            time.sleep(5)
            retries += 1
            error_message = e.response.get("error", "Unknown error")
            if error_message == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 10))
                rate_limited_event.set()
                await handle_rate_limit(retry_after)
            else:
                retries += 1
                log_message(
                    f"Slack API Error: {error_message}. "
                    "Retrying...getting thread messages",
                    "warning"
                )
                await asyncio.sleep(exponential_backoff(retries))

    raise RuntimeError("Failed to retrieve thread messages after max retries.")


async def get_thread_ts_list_from_slack_async(
        root_ts: str,
        channel_id: str,
        client
    ) -> list:
    """
    Retrieve a list of timestamps for all messages in a Slack thread.

    Args:
        root_ts (str): Timestamp of the root message in the thread.
        channel_id (str): ID of the Slack channel.
        client: Slack WebClient instance for API interaction.

    Returns:
        list: List of message timestamps in the thread.
    """

    try:
        thread_messages = await get_thread_messages_async(
            client, channel_id, root_ts
        )
        return [msg["ts"] for msg in thread_messages["messages"]]
    except SlackApiError as e:
        log_error(e, "Error fetching thread messages.")
        log_message(
            "Error fetching thread messages for root "
            f"message {root_ts}",
            "error"
        )
        return []
  

def send_message_with_retry(
        client: object,
        channel_id: str,
        thread_ts: str,
        text: str,
        max_retries: int = 3,
        retry_delay: int = 5,
        log_context: str = "Sending message to Slack"
    ):
    """
    Send a message to Slack with retry logic.

    Args:
        client (object): The Slack WebClient instance for sending messages.
        channel_id (str): The ID of the Slack channel.
        thread_ts (str): The thread timestamp where the message should be posted.
        text (str): The text of the message to be sent.
        max_retries (int): Maximum number of retries if sending the message fails. Default is 3.
        retry_delay (int): Delay (in seconds) between retries. Default is 5 seconds.
        log_context (str): A context message for logging purposes. Default is "Sending message to Slack".

    Returns:
        response (object): The response from the Slack API if successful.

    Raises:
        SlackApiError: If all retry attempts fail.
    """
    attempt = 0

    while attempt < max_retries:
        try:
            response = client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=text
            )
            return response  # Return response if successful
        except SlackApiError as e:
            attempt += 1
            log_error(e, f"{log_context}: Attempt {attempt} failed.")
            if attempt < max_retries:
                log_message(f"{log_context}: Retrying in {retry_delay} seconds...", level="warning")
                time.sleep(retry_delay)
            else:
                log_message(f"{log_context}: All {max_retries} attempts failed.", level="error")
                raise  # Rethrow the exception after all retries fail


def populate_members() -> list:
    """
    Fetches all users in the Slack workspace and saves them to a list
    including all workspace members through pagination.

    Returns:
        list: A list of all Slack members retrieved from the workspace.
    """
    log_message("Fetching members...", "info")
    members = []
    max_retries = 3

    while max_retries > 0:
        try:
            result = slackapp.client.users_list()

            if result and "members" in result.data:
                members.extend(result.data["members"])
                count = 0
                while ("response_metadata" in result.data and
                       "next_cursor" in result.data["response_metadata"]):
                    cursor = result.data["response_metadata"]["next_cursor"]
                    if not cursor:
                        break
                    result = slackapp.client.users_list(cursor=cursor)
                    if result and "members" in result.data:
                        members.extend(result.data["members"])
                        log_message(f"Page {count} fetched.", "info")
                        count += 1
            else:
                log_message(
                    "Failed to fetch members or unexpected response format.",
                    "error"
                )
            break

        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 5))
                log_error(e, "Rate limited by Slack API.")
                log_message(
                    f" Retrying after {retry_after} seconds...",
                    "warning"
                )
                time.sleep(retry_after)
                max_retries -= 1
            else:
                log_error(e, "Slack API error.")
                raise

        except Exception as e:
            log_error(e, "Unexpected error while fetching members.")
            raise

    if max_retries == 0:
        log_message(
            "Failed to fetch members after "
            "multiple retries due to rate limiting.",
            "critical"
        )

    # Not currently needed.
    # # Save members to a local file "members.json" for future access
    # with open(file="members.json", mode="w", encoding="utf-8") as f:
    #     json.dump(members, f, indent=2)

    return members


slack_members = populate_members()


def get_member_name(user_id: str) -> str:
    """
    Finds and returns the real name of a user by their user ID.

    Args:
        user_id (str): The unique ID of the user.

    Returns:
        str: The real name of the user, or "Unknown User" if not found.
    """
    for member in slack_members:
        if member["id"] == user_id:
            return member.get("real_name", "Unknown User")

    return None
def get_channel_name(client: object, channel_id: str) -> str:
    """
    Retrieves the name of a Slack channel by its ID.

    Args:
        client (object):
            The Slack WebClient instance for API interactions.
        channel_id (str): The Slack channel ID.

    Returns:
        str: The name of the Slack channel.

    Raises:
        ValueError: If the channel_id is not provided.
        SlackApiError: If the Slack API encounters an error.
        Exception: For any unexpected errors.
    """
    if not channel_id:
        raise ValueError(
            "The 'channel_id' must be provided and cannot be empty."
        )

    try:
        response = client.conversations_info(channel=channel_id)
        return response["channel"]["name"]

    except SlackApiError:
        log_message(
            "Slack API Error retrieving channel name.",
            "error"
        )
        raise

    except Exception:
        log_message(
            "Unexpected error retrieving channel name.",
            "error"
        )
        raise


# Synchronous Wrappers
def get_conversations_history(*args, **kwargs):
    """
    Synchronous wrapper for get_conversations_history_async.

    This function allows synchronous code to fetch Slack channel 
    conversation history by running the asynchronous 
    `get_conversations_history_async` function using `asyncio.run`.

    Args:
        *args: Positional arguments forwarded to 
               `get_conversations_history_async`.
        **kwargs: Keyword arguments forwarded to 
                  `get_conversations_history_async`.

    Returns:
        dict: The conversation history response from the Slack API.
    """

    return asyncio.run(get_conversations_history_async(*args, **kwargs))


def get_thread_messages(*args, **kwargs):
    """
    Synchronous wrapper for get_thread_messages_async.

    This function fetches all messages from a specific Slack thread 
    synchronously by running the asynchronous 
    `get_thread_messages_async` function with `asyncio.run`.

    Args:
        *args: Positional arguments forwarded to 
               `get_thread_messages_async`.
        **kwargs: Keyword arguments forwarded to 
                  `get_thread_messages_async`.

    Returns:
        object: The Slack API response containing thread messages.
    """

    return asyncio.run(get_thread_messages_async(*args, **kwargs))


def get_thread_ts_list_from_slack(
        root_ts: str, channel_id: str, client
    ) -> list:
    """
    Synchronous wrapper for get_thread_ts_list_from_slack_async.

    This function retrieves a list of timestamps for all messages 
    in a Slack thread synchronously by executing the asynchronous 
    `get_thread_ts_list_from_slack_async` function via `asyncio.run`.

    Args:
        root_ts (str): The timestamp of the root message in the thread.
        channel_id (str):
            The ID of the Slack channel containing the thread.
        client: The Slack WebClient instance for API interaction.

    Returns:
        list: A list of timestamps for all messages in the thread.
    """
    return asyncio.run(
        get_thread_ts_list_from_slack_async(root_ts, channel_id, client)
    )


async def handle_rate_limit(retry_after: int):
    """
    Handles Slack's rate limit by waiting and resetting the rate limit event.

    Args:
        retry_after (int): The number of seconds to wait before retrying.
    """
    global rate_limit_active

    if not rate_limit_active:
        rate_limit_active = True
        log_message(
            f"⚠️ Slack API Rate-Limited. Pausing for {retry_after} seconds...",
            "warning"
        )

    await asyncio.sleep(retry_after)

    rate_limited_event.clear()
    rate_limit_active = False
    log_message(
        "✅ Rate limit cleared. Resuming operations...",
        "info"
    )
