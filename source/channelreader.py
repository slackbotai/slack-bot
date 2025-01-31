"""
channelreader.py

Handles the fetching, processing, and storage of messages from Slack
channels.

This module contains functions to fetch messages from Slack channels,
process and clean the messages, append thread messages to root messages,
and store the processed data into MongoDB. It also includes functions
to clean up missing messages in MongoDB and update existing threads with
new replies.

Functions:
    - channelreader: Main function to fetch, process, and save messages
      for a channel.
    - process_messages: Clean and process all fetched messages.
    - remove_blocks_with_key: Filter out blocks containing a
      specific key.
    - remove_specified_keys: Remove specified keys from nested
      dictionaries or lists.
    - clean_files_data: Retain only essential keys in message file data.
    - order_messages_keys: Reorder message keys for consistency.
    - append_thread_messages_batched: Synchronous wrapper for async 
      thread message fetching.
    - append_thread_messages_batched_async: Asynchronously fetch and
      append thread messages to root messages.
    - fetch_thread_messages: Fetch thread messages asynchronously
      from Slack.
    - fetch_and_save_slack_data: Fetch and save data for all channels.
    - fetch_all_channel_ids: Retrieve IDs of all Slack channels the bot
      has access to.
    - fetch_all_channel_ids_async: Asynchronously fetch channel IDs.
    - fetch_channel_page: Fetch a page of channels from Slack API.
    - process_channel_cleanup: Validate channel IDs and clean
      unused collections.
    - save_channel_info_to_mongodb: Save channel metadata to MongoDB.
    - run_fetch_and_save_slack_data: Schedule periodic data fetch/save.

Raises:
    - ValueError: For invalid or missing arguments.
    - RuntimeError: For general runtime errors.
    - Exception: For unexpected exceptions.
"""

# Standard library imports
import time
import asyncio
from math import ceil
from collections import OrderedDict

# Third-party library imports
import schedule

# Application-specific imports
from utils.slack_utils import get_member_name
from envbase import (
    slack_web_client,
    mongodb,
    summarisation,
    channels
)
from utils.mongodb_utils import (
    save_messages_to_mongodb,
    cleanup_missing_messages,
    update_existing_threads
)
from utils.slack_utils import (
    get_conversations_history,
    get_thread_messages,
    get_channel_name
)
from utils.logging_utils import log_error, log_message

def channelreader(client: object, channel_id: str) -> None:
    """
    Fetches, processes, and stores messages from a specified
    Slack channel.

    This function:
    1. Fetches the channel's name and messages using the Slack API.
    2. Processes and cleans the retrieved messages.
    3. Appends thread messages to root messages.
    4. Stores processed data into MongoDB.
    5. Cleans up missing root and thread messages in MongoDB.
    6. Updates existing threads with new replies.

    Args:
        client (object): 
            The Slack WebClient instance for API interactions.
        channel_id (str): The ID of the Slack channel to process.

    Returns:
        None

    Raises:
        SlackApiError: If there are issues fetching data from Slack.
    """
    # Adding idle to let bolt app fully start up before running this.
    time.sleep(5)

    # Retrieve the name of the Slack channel
    channel_name = get_channel_name(client, channel_id)
    log_message(
        f"Indexing channel: {channel_name} ({channel_id})",
        'info'
    )

    # Access the MongoDB collection for this channel
    collection = mongodb[channel_id]

    # Fetch the most recent message's timestamp from MongoDB
    last_message = collection.find_one(sort=[('ts', -1)])
    last_message_ts = last_message['ts'] if last_message else None

    # Calculate the oldest timestamp for fetching new messages
    oldest_ts = f"{float(last_message_ts):.6f}" if last_message_ts else None

    all_messages = [] # To store all fetched messages
    cursor = None # For pagination of Slack API results
    batch_count = 0 # Track the number of fetched batches

    # Fetch messages in batches using Slack's pagination
    while True:
        result = get_conversations_history(
            client, channel_id, cursor, oldest=oldest_ts, limit=100
        )
        # Extract messages from the result
        messages = result.data.get("messages", [])
        # Increment the batch counter
        batch_count += 1  # Track the batch number
        log_message(
            f"Batch {batch_count}: Retrieved {len(messages)} messages",
            'info'
        )

        # Exit loop if no messages are fetched
        if not messages:
            log_message("No more messages to fetch.", 'info')
            break

        # Fetch existing message timestamps from MongoDB
        message_timestamps = [msg["ts"] for msg in messages]
        existing_messages = collection.find(
            {"ts": {"$in": message_timestamps}}
        )
        existing_timestamps =  {
            f"{float(doc['ts']):.6f}" for doc in existing_messages
        }

        # Filter out messages that already exist in MongoDB
        new_messages = [
            msg for msg in messages
            if f"{float(msg['ts']):.6f}" not in existing_timestamps
        ]

        # Accumulate new messages
        all_messages.extend(new_messages)
        cursor = result.data.get("response_metadata", {}).get("next_cursor")

        if not cursor: # Exit if there are no more results
            break

    # If no new messages are fetched, log and exit. Else process
    if not all_messages:
        log_message("No new root messages found.", 'info')
    else:
        all_messages = process_messages(
            all_messages, client, channel_id, channel_name
        )
        all_messages = append_thread_messages_batched(
            all_messages, client, channel_id, channel_name
        )
        save_messages_to_mongodb(all_messages, channel_id, channel_name)

    # Clean up missing root and thread messages in MongoDB
    cleanup_missing_messages(channel_id, channel_name, client)

    # Update threads with new replies for recent root messages
    update_existing_threads(client, channel_id)

    # Log the completion of the indexing process
    log_message(
        f"Channel {channel_name} ({channel_id}) has been "
        "indexed and saved to MongoDB.",
        'info'
    )


def process_messages(
        all_messages: list, client: object,
        channel_id: str, channel_name: str
) -> list:
    """
    Cleans and processes Slack messages by removing unnecessary data, 
    reordering keys, replacing user IDs with usernames, and appending
    thread messages.

    Args:
        all_messages (list): A list of Slack messages to process.
        client (object): The Slack WebClient instance.
        channel_id (str): The ID of the Slack channel.
        channel_name (str): The name of the Slack channel.

    Returns:
        list: Processed and cleaned messages.
    """
    # Remove blocks with "subtype" key
    all_messages = remove_blocks_with_key(all_messages, "subtype")

    # Remove unnecessary keys from messages
    remove_specified_keys(
        all_messages,
        ["reactions", "edited", "upload", "x_files", "blocks",
         "attachments", "team", "client_msg_id", "reply_count", 
         "reply_users_count", "latest_reply", "reply_users", 
         "is_locked", "subscribed", "display_as_bot", "type", 
         "pinned_info", "pinned_to"])

    # Clean the "files" data for each message
    all_messages = clean_files_data(all_messages)

    # Reverse order of messages to ensure the oldest messages come first
    all_messages.reverse()

    # Reorder keys for each message for consistency
    key_order = ["ts", "user", "text", "files", "thread_messages"]
    all_messages = order_messages_keys(all_messages, key_order)

    # Replace user IDs with usernames in message text
    for message in all_messages:
        user_id = message.get("user")
        if user_id:
            user_name = get_member_name(user_id)
            message["text"] = (
                f"{user_name} (UserID: <@{user_id}>): {message.get('text')}"
            )

    # Remove user ID from final output
    remove_specified_keys(all_messages, ["user"])

    # Append thread messages
    all_messages = append_thread_messages_batched(
        all_messages, client, channel_id, channel_name
    )

    return all_messages


def remove_blocks_with_key(blocks: list, key_to_check: str) -> list:
    """
    Remove all blocks that contain a specific key.

    Args:
        blocks (list): A list of blocks to process.
        key_to_check (str): The key to search for in each block.

    Returns:
        list: A list of blocks without the specified key.

    Raises:
        ValueError: If the 'blocks' argument is not a list.
    """
    # Validate input types
    if not isinstance(blocks, list):
        raise ValueError("The 'blocks' argument must be a list.")

    # Return a list of blocks that do not contain the specified key
    filtered_blocks = [
        block for block in blocks if key_to_check not in block]

    return filtered_blocks


def remove_specified_keys(obj: dict|list, keys_to_remove: list) -> None:
    """
    Recursively remove specified keys from a nested dictionary or list.

    Args:
        obj (dict|list):
            A nested dictionary or list of dictionaries to process.
        keys_to_remove (list):
            A list of keys to remove from the dictionary.

    Returns:
        None:
            The input object is modified in place.
    """
    # If object is a dictionary, iterate through keys and remove
    # specified ones
    if isinstance(obj, dict):
        for key in keys_to_remove:
            obj.pop(key, None)

        # Recursively process nested values
        for value in obj.values():
            if isinstance(value, (dict, list)):
                remove_specified_keys(value, keys_to_remove)

    # If object is a list, apply the function to each item
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                remove_specified_keys(item, keys_to_remove)


def clean_files_data(messages: list) -> list:
    """
    Clean the 'files' data in messages by retaining only essential
    fields.

    Args:
        messages (list):
            A list of messages, each potentially containing files.

    Returns:
        list: Messages with cleaned file data.
    """
    cleaned_messages = []

    for message in messages:
        cleaned_message = message.copy()

        # Check if the message contains a "files" key and is a list
        if "files" in message and isinstance(message["files"], list):
            # List comprehension to retain only necessary keys
            cleaned_files = [
                {key: file[key] for key in (
                    "url_private", "filetype", "name") if key in file}
                for file in message["files"]
            ]
            cleaned_message["files"] = cleaned_files

        cleaned_messages.append(cleaned_message)

    return cleaned_messages


def order_messages_keys(messages: list, key_order: list) -> list:
    """
    Reorder the keys in each message in a list of messages based on a
    specified key order. Keys not in the specified order will be added 
    at the end in their original order.

    Args:
        messages (list): A list of dictionaries representing messages.
        key_order (list): The desired order of keys.

    Returns:
        list: Messages with keys reordered.

    Raises:
        ValueError: If input messages or key_order are invalid.
    """
    # Validate input types
    if not isinstance(
        messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError(
            "The 'messages' argument must be a list of dictionaries."
        )
    if not isinstance(
        key_order, list) or not all(isinstance(k, str) for k in key_order):
        raise ValueError(
            "The 'key_order' argument must be a list of strings."
        )

    ordered_messages = []

    # Iterate over each message in the provided list
    for message in messages:
        # Create an ordered dictionary for the specified key order
        ordered_message = OrderedDict()

        # Add keys from key_order that exist in the message
        for key in key_order:
            if key in message:
                ordered_message[key] = message[key]

        # Add remaining keys that are not in the key_order
        for key in message:
            if key not in ordered_message:
                ordered_message[key] = message[key]

        ordered_messages.append(ordered_message)

    return ordered_messages


def append_thread_messages_batched(
        *args: tuple, **kwargs: dict
) -> list[dict]:
    """
    Synchronous wrapper for the asynchronous
    append_thread_messages_batched_async.

    Args:
        *args (tuple):
            Positional arguments passed to the asynchronous function.
        **kwargs (dict):
            Keyword arguments passed to the asynchronous function.

    Returns:
        list[dict]: A list of messages with appended thread content.
    """
    return asyncio.run(
        append_thread_messages_batched_async(*args, **kwargs)
    )


async def append_thread_messages_batched_async(
        all_messages: list[dict], client: object,
        channel_id: str, channel_name: str,
        batch_size: int = 50
) -> list[dict]:
    """
    Appends thread messages to their respective root messages
    in batches.

    Args:
        all_messages (list[dict]): List of root messages.
        client (object): Slack WebClient instance.
        channel_id (str): Channel ID.
        channel_name (str): Channel name.
        batch_size (int): Number of threads processed per batch.

    Returns:
        list[dict]: Messages with appended thread content.
    """
    thread_messages_map = {}
    thread_ts_list = []

    # Collect all thread_ts for messages with threads
    for message in all_messages:
        if "thread_ts" in message and "thread_messages" not in message:
            thread_ts_list.append(message["thread_ts"])

    # Split the thread_ts_list into batches
    total_batches = ceil(len(thread_ts_list) / batch_size)
    for batch_index in range(total_batches):
        start = batch_index * batch_size
        end = start + batch_size
        batch = thread_ts_list[start:end]

        # Use asyncio.gather to fetch thread messages concurrently
        results = await asyncio.gather(*[
            fetch_thread_messages(client, channel_id, thread_ts)
            for thread_ts in batch
        ])

        # Update the thread_messages_map with results
        for thread_ts, thread_messages in results:
            thread_messages_map[thread_ts] = thread_messages

        log_message(
            f"Batch {batch_index + 1}/{total_batches} processed with "
            f"{len(batch)} threads in {channel_name}.",
            'info'
        )

    # Append thread messages to their respective root messages
    for message in all_messages:
        thread_ts = message.get("thread_ts")
        if thread_ts and thread_ts in thread_messages_map:
            message["thread_messages"] = thread_messages_map[thread_ts]

    if total_batches > 0:
        log_message(
            f"All {total_batches} batches processed for {channel_name}.",
            'info'
        )
    return all_messages


async def fetch_thread_messages(
        client: object, channel_id: str, thread_ts: str
) -> tuple[str, list[dict]]:
    """
    Fetches thread messages asynchronously from Slack.

    Args:
        client (object): Slack WebClient instance.
        channel_id (str): ID of the Slack channel.
        thread_ts (str): Thread timestamp.

    Returns:
        tuple[str, list[dict]]:
            - Thread timestamp.
            - A list of thread messages as dictionaries.
    """
    try:
        thread_messages = await asyncio.to_thread(
            get_thread_messages, client, channel_id, thread_ts
        )
        # Process fetched thread messages
        thread_messages.data["messages"].pop(0)  # Remove duplicate
        thread_messages.data["messages"] = remove_blocks_with_key(
            thread_messages.data["messages"], "subtype")
        remove_specified_keys(
            thread_messages.data["messages"],
            [
                "bot_id", "bot_profile", "app_id", 
                "team", "client_msg_id", "parent_user_id",
                "reactions", "edited", "upload", 
                "x_files", "blocks", "attachments",
                "reply_count", "reply_users_count", 
                "latest_reply", "reply_users",
                "is_locked", "subscribed", 
                "thread_ts", "type"
            ]
        )
        thread_messages.data["messages"] = clean_files_data(
            thread_messages.data["messages"])

        key_order = ["ts", "user", "text", "files"]
        thread_messages.data["messages"] = order_messages_keys(
            thread_messages.data["messages"], key_order)

        # Replace user IDs with usernames
        for msg in thread_messages.data["messages"]:
            user_id = msg.get("user")
            if user_id:
                user_name = get_member_name(user_id)
                msg["text"] = (
                    f"{user_name} (UserID: <@{user_id}>): " +
                    f"{msg.get('text')}")

        # Remove user ID from thread messages
        remove_specified_keys(
            thread_messages.data["messages"], ["user"]
        )

        return thread_ts, thread_messages.data["messages"]

    except Exception as e:
        log_error(e, f"Error fetching thread messages for thread {thread_ts}.")
        return thread_ts, []


def fetch_and_save_slack_data() -> None:
    """
    Fetches messages from all Slack channels and saves them to MongoDB.

    Workflow:
        1. Fetch all channel IDs.
        2. Iterate through each channel and fetch messages.
        3. Process and store each channel's messages.
        4. Mark completed channels to avoid repetition.
    """
    channel_ids = fetch_all_channel_ids(slack_web_client)
    parsing_done = []

    while True:
        for index, (channel_id, channel_name) in enumerate(
            channel_ids, start=1
        ):
            if channel_id not in parsing_done:
                log_message(
                    f"Channel: {channel_name} | {index}/{len(channel_ids)}",
                    'info'
                )
                channelreader(slack_web_client, channel_id)
                parsing_done.append(channel_id)
                log_message(
                    f"Channel finished: {channel_name}",
                    'info'
                )

        # Check if all channels are processed
        if len(parsing_done) == len(channel_ids):
            log_message(
                "All channels are processed. "
                "Indexing complete. Slackbot is ready.",
                'info'
            )
            break

        # Optional: Add a delay to prevent busy waiting
        time.sleep(1)


def fetch_all_channel_ids(client: object) -> list[tuple[str, str]]:
    """
    Wrapper to call the asynchronous fetch_all_channel_ids_async
    function synchronously.

    Args:
        client (object): The Slack WebClient instance.

    Returns:
        list[tuple[str, str]]:
            A list of tuples containing channel IDs and names.
    """
    return asyncio.run(fetch_all_channel_ids_async(client))


async def fetch_all_channel_ids_async(client: object) -> list[tuple[str, str]]:
    """
    Asynchronously fetch all Slack channels (public and private)
    where the bot is a member.

    Args:
        client (object): The Slack WebClient instance.

    Returns:
        list[tuple[str, str]]:
            A list of tuples containing channel IDs and names.
    """
    all_channels_info = []
    next_cursor = None

    try:
        while True:
            # Fetch a page of channels
            response = await fetch_channel_page(client, next_cursor)
            if not response:
                break

            channels = response.get("channels", [])
            log_message(
                f"Fetched {len(channels)} channels in this batch.",
                'info'
            )

            # Process channels
            for channel in channels:
                if channel.get("is_member"):
                    log_message(
                        f"Bot is a member of channel {channel['name']} "
                        f"(ID: {channel['id']}).",
                        'info'
                    )
                    all_channels_info.append({
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_private": channel["is_private"]
                    })
                else:
                    log_message(
                        f"Bot is not a member of channel {channel['name']} "
                        f"(ID: {channel['id']}).",
                        'info'
                    )

            # Update cursor for pagination
            next_cursor = response.get("response_metadata", {}).get(
                "next_cursor"
            )
            if not next_cursor:
                break

        # Separate public and private channels
        public_channels = [
            (channel["id"], channel["name"])
            for channel in all_channels_info
            if not channel["is_private"]
        ]
        private_channels = [
            (channel["id"], channel["name"])
            for channel in all_channels_info
            if channel["is_private"]
        ]

        log_message(
            "Public Channels:",
            'info'
        )
        for channel_id, channel_name in public_channels:
            log_message(
                f"{channel_name} (ID: {channel_id})",
                'info'
            )
        log_message(    
            "Private Channels:",
            'info'
        )
        for channel_id, channel_name in private_channels:
            log_message(
                f"{channel_name} (ID: {channel_id})",
                'info'
            )

        # Process private channels (if needed)
        included_channel_ids = process_channel_cleanup(private_channels)
        filtered_private_channels = [
            (channel_id, channel_name)
            for channel_id, channel_name in private_channels
            if channel_id in included_channel_ids
        ]
        log_message(
            f"Filtered Private Channels: {filtered_private_channels}",
            'info'
        )

        all_channels = public_channels + filtered_private_channels

        save_channel_info_to_mongodb(all_channels)

        return all_channels

    except Exception as e:
        log_error(e, "Error in fetch_all_channel_ids_async.")
        return []


async def fetch_channel_page(client: object, cursor=None) -> dict:
    """
    Fetch a single page of channels using the Slack API.

    Args:
        client (object): The Slack WebClient instance.
        cursor (str, optional): The cursor for pagination.

    Returns:
        dict: A dictionary containing the response data.
    """
    try:
        response = await asyncio.to_thread(
            client.conversations_list,
            types="public_channel,private_channel",
            cursor=cursor,
            limit=100,
        )
        return response
    except Exception as e:
        log_error(e, "Error fetching channel page.")
        return {}


def process_channel_cleanup(
        channel_info: list[tuple[str, str]]
    ) -> list[str]:
    """
    Checks if channels should be included based on the 'summarisation' 
    collection in MongoDB. If a channel ID is not in the collection, 
    its corresponding collection is removed from MongoDB.

    Args:
        channel_info (list[tuple[str, str]]):
            A list of tuples containing channel IDs and names.

    Returns:
        list[str]: 
            A list of channel IDs that are to be included.
    """
    included_channel_ids = []

    try:
        # Get all channel IDs from the "summarisation" collection
        db_channel_ids = {doc["channel_id"] for doc in summarisation.find()}

        # Process each channel
        for channel_id, channel_name in channel_info:
            if channel_id in db_channel_ids:
                # Channel is in the collection, include it
                included_channel_ids.append(channel_id)
            else:
                # Channel is not in the collection, remove its
                # collection from MongoDB
                try:
                    db = mongodb
                    if channel_id in db.list_collection_names():
                        db[channel_id].drop()  # Drop the collection
                        log_message(
                            f"Removed MongoDB collection for channel: "
                            f"{channel_name} ({channel_id}).",
                            'info'
                        )
                except Exception as e:
                    log_error(
                        e,
                        "Error removing collection. "
                        f"{channel_name} ({channel_id})"
                    )
    except Exception as e:
        log_error(e, "Error in process_channel_cleanup.")

    return included_channel_ids


def save_channel_info_to_mongodb(
        channel_info: list[tuple[str, str]]
) -> None:
    """
    Saves Slack channel information to the 'channel_info'
    MongoDB collection.

    Args:
        channel_info (list):
            A list of tuples containing channel IDs and names.

    Workflow:
        1. Clears existing channel data in MongoDB.
        2. Inserts updated channel information.
    """
    try:
        # Clear existing data in the collection
        channels.delete_many({})

        # Prepare the data for insertion
        channel_data = [
            {"channel_id": channel_id, "channel_name": channel_name}
            for channel_id, channel_name in channel_info
        ]
        channels.insert_many(channel_data)
        log_message(
            "Channel information saved to MongoDB",
            'info'
        )

    except Exception as e:
        log_error(e, "Error saving channel information to MongoDB.")


def run_fetch_and_save_slack_data() -> None:
    """
    Runs the Slack data fetching process immediately and schedules
    daily updates.

    Workflow:
        1. Immediate execution of `fetch_and_save_slack_data`.
        2. Schedule the function to run daily at midnight.
        3. Keep the scheduler running indefinitely.
    """
    # NOTE Run immediately on program start (Remove later)
    fetch_and_save_slack_data()

    # Schedule the task to run daily at midnight
    schedule.every().day.at("00:00").do(fetch_and_save_slack_data)

    # Keep the scheduler running
    while True:
        schedule.run_pending()
        time.sleep(1)
