"""
mongodb_utils.py

This module contains utility functions for handling MongoDB operations
related to Slack messages.

Functions:
- save_messages_to_mongodb: Save messages and their associated thread
    messages to MongoDB efficiently.
- setup_mongodb_collection: Initialise and configure a MongoDB
    collection for a specific Slack channel.
- fetch_existing_messages: Fetch existing messages and their associated
    thread messages from a database collection.
- process_messages_for_embedding: Collect texts and file attachments
    for embedding and create a mapping to their source messages.
- generate_embeddings_parallel: Generate embeddings in parallel using
    a thread pool.
- attach_embeddings_to_messages: Attach generated embeddings to their
    respective messages.
- prepare_bulk_operations: Prepare bulk operations for updating MongoDB
    with new or updated messages.
- execute_bulk_operations: Execute MongoDB bulk operations.
- update_existing_threads: Update existing threads by fetching new
    replies for root messages within a cutoff period.
- cleanup_missing_messages: Synchronise MongoDB with Slack data by
    removing missing root and thread messages.

Attributes:
    mongodb: A MongoDB client instance for database operations.
"""

# Standard library imports
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor

# Third-party library imports
from pymongo import UpdateOne

# Application-specific imports
from envbase import mongodb
from utils.openai_utils import generate_embedding_batch, generate_embedding
from utils.slack_utils import (
    get_member_name,
    get_conversations_history,
    get_thread_ts_list_from_slack,
    get_thread_messages,
)
from utils.logging_utils import log_message

def save_messages_to_mongodb(
        all_messages: list,
        channel_id: str,
        channel_name: str,
) -> None:
    """
    Save messages and their associated thread messages to
    MongoDB efficiently.

    This function processes a list of messages from a Slack channel,
    generates embeddings for their content, and updates MongoDB. It
    ensures efficient updates using bulk operations and handles new and
    existing messages seamlessly.

    Args:
        all_messages (list): List of message dictionaries from the
            Slack API.
        channel_id (str): Unique identifier of the Slack channel.
        channel_name (str): Name of the Slack channel, used for
            logging purposes.

    Returns:
        None
    """
    start_time = time.time()
    log_message("Starting save_messages_to_mongodb...", "info")

    # Initialize MongoDB collection for the given channel
    collection = setup_mongodb_collection(channel_id)

    # Retrieve existing messages from the database
    existing_messages = fetch_existing_messages(collection)

    # Process all messages to collect texts that need embeddings
    texts_to_embed, text_map = process_messages_for_embedding(all_messages)

    # Generate embeddings for new messages and attach them to the
    # respective messages
    if texts_to_embed:
        embeddings = generate_embeddings_parallel(
            texts_to_embed, batch_size=32, num_workers=8
        )
        attach_embeddings_to_messages(embeddings, text_map)

    # Prepare bulk operations for efficient MongoDB update
    bulk_operations = prepare_bulk_operations(
        all_messages, existing_messages # text_map
    )

    # Execute the prepared bulk operations
    execute_bulk_operations(collection, bulk_operations)

    log_message(
        f"Processed and saved messages for channel "
        f"{channel_name} in {time.time() - start_time:.2f} seconds.",
        "info"
    )


def setup_mongodb_collection(channel_id: str,) -> object:
    """
    Initialise and configure a MongoDB collection for a specific
    Slack channel.

    This function retrieves the MongoDB collection associated with the
    given channel IDand ensures that the collection has an index on the
    "ts" (timestamp) field for efficient lookups and to enforce
    uniqueness of messages.

    Args:
        channel_id (str): The unique identifier for the Slack channel.

    Returns:
        object: The MongoDB collection object for the specified channel.
    """
    # Access the MongoDB collection for the specified channel ID
    collection = mongodb[channel_id]

    # Ensure a unique index exists on the 'ts'
    # field for efficient queries
    collection.create_index("ts", unique=True)

    return collection


def fetch_existing_messages(
        collection: object,
) -> dict[str, list[dict[str, str]]]:
    """
    Fetch existing messages and their associated thread messages from a
    database collection.

    This function retrieves documents from the specified collection and
    extracts the root message timestamps ("ts") and their corresponding
    thread messages(with timestamps and text). It constructs and returns
    a dictionary that maps each root message timestamp to a list of
    thread messages.

    Args:
        collection (object): The database collection object from which
            documents are fetched.This object should support the
            "find()" method.

    Returns:
        dict[str, list[dict[str, str]]]:
            A dictionary where each key is a root message
            timestamp ("ts"), and the value is a list of dictionaries,
            each representing a thread message with:
            - "ts" (timestamp of the thread message)
            - "text" (text content of the thread message, defaulting to
            an empty string if not present in the document).
    """
    # Fetch documents with root and thread message timestamps and text
    existing_docs = collection.find(
        {}, {"ts": 1, "thread_messages.ts": 1, "thread_messages.text": 1}
    )
    # Map root message timestamps to their associated thread messages
    return {
        doc["ts"]: [
            {"ts": t["ts"], "text": t.get("text", "")}
            for t in doc.get("thread_messages", [])
        ]
        for doc in existing_docs
    }


def process_messages_for_embedding(
        all_messages: list[dict]
) -> tuple[list[str], dict[tuple[str, str], dict]]:
    """
    Collect texts and file attachments for embedding and create a
    mapping to their source messages.

    Args:
        all_messages (list[dict]):
            A list of message dictionaries from Slack.

    Returns:
        tuple[list[str], dict[tuple[str, str], dict]]:
            A tuple containing:
            - A list of texts (including file descriptions) for
              embedding.
            - A dictionary mapping `(text, ts)` tuples to their
              respective message dictionaries.
    """
    texts_to_embed = [] # List to store texts for embedding
    text_map = {} # Map texts to their source messages

    def collect_texts(message: dict) -> None:
        ts = message.get("ts")
        if not ts:
            return

        # Add root message text to the map
        if "text" in message:
            text_map[(message["text"], ts)] = message
            texts_to_embed.append(message["text"])

        # Process file attachments in the root message
        if "files" in message:
            for file in message["files"]:
                file_name = file.get("name", "Unknown file")
                file_text = file_name
                text_map[(file_text, ts)] = message
                texts_to_embed.append(file_text)

        # Process texts in thread messages
        if "thread_messages" in message:
            for thread_message in message["thread_messages"]:
                thread_ts = thread_message.get("ts")
                if not thread_ts:
                    continue

                # Add thread message text
                if "text" in thread_message:
                    text_map[
                        (thread_message["text"], thread_ts)
                    ] = thread_message
                    texts_to_embed.append(thread_message["text"])

                # Process file attachments in the thread message
                if "files" in thread_message:
                    for file in thread_message["files"]:
                        file_name = file.get("name", "Unknown file")
                        file_text = file_name
                        text_map[(file_text, thread_ts)] = thread_message
                        texts_to_embed.append(file_text)

    for message in all_messages:
        collect_texts(message)

    log_message(
        f"Collected {len(texts_to_embed)} texts "
        "(including file descriptions) for embedding.",
        "info"
    )
    return texts_to_embed, text_map


def generate_embeddings_parallel(
        texts: list[str],
        batch_size: int = 32,
        num_workers: int = 8,
) -> list:
    """
    Generate embeddings in parallel using a thread pool.

    This function splits the input texts into smaller batches and
    processes them concurrently using a thread pool. Each batch is 
    passed to `generate_embedding_batch`.

    Args:
        texts (list[str]): A list of texts to generate embeddings for.
        batch_size (int, optional):
            The size of each batch. Defaults to 32.
        num_workers (int, optional):
            The number of threads to use. Defaults to 8.

    Returns:
        list: A list of embeddings corresponding to the input texts.
    """
    def worker(chunk: list[str]) -> list:
        """
        Generate embeddings for a single chunk of texts.

        Args:
            chunk (list[str]): A list of texts in the chunk.

        Returns:
            list: A list of embeddings for the texts in the chunk.
        """
        return generate_embedding_batch(chunk, batch_size=len(chunk))

    # Split texts into smaller chunks for parallel processing
    chunks = [
        texts[i:i + batch_size] for i in range(0, len(texts), batch_size)
    ]

    # Use a thread pool to process the chunks concurrently
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = executor.map(worker, chunks)

    # Flatten the list of results into a single list of embeddings
    return [embedding for result in results for embedding in result]


def attach_embeddings_to_messages(
        embeddings: list,
        text_map: dict[tuple[str, str], dict],
) -> None:
    """
    Attach generated embeddings to their respective messages.

    This function takes a list of embeddings and a mapping of texts
    (with their timestamps) to messages, then assigns each embedding to
    its corresponding message in the "text_map".

    Args:
        embeddings (list): A list of generated embeddings,
            one for each text in "text_map".
        text_map (dict[tuple[str, str], dict]): A dictionary mapping
            "(text, ts)" tuples to the respective message dictionaries.
            Each message dictionary is updated with the corresponding
            embedding.

    Returns:
        None
    """
    # Iterate over embeddings and attach to its corresponding message
    for (text, ts), embedding in zip(text_map.keys(), embeddings):
        text_map[(text, ts)]["embedding"] = embedding

    log_message(
        f"Generated and attached embeddings to "
        f"{len(embeddings)} messages.",
        "info"
    )


def prepare_bulk_operations(
        all_messages: list,
        existing_messages: dict,
) -> list: # text_map
    """
    Prepare bulk operations for updating MongoDB with new or
    updated messages.

    Args:
        all_messages (list): A list of all messages from Slack.
        existing_messages (dict):
            A mapping of root message timestamps (`ts`) to
            thread messages from MongoDB.

    Returns:
        list: A list of MongoDB `UpdateOne` operations for bulk write.
    """
    bulk_operations = []

    def append_filenames_to_text(text: str, files: list) -> str:
        """
        Append filenames to the text if files exist.

        Args:
            text (str): The message text.
            files (list): The list of file dictionaries.

        Returns:
            str: The updated text with appended filenames.
        """
        if files:
            file_descriptions = ", ".join([
                file.get("name", "Unnamed file")
                for file in files
            ])
            return f"{text}{file_descriptions}"
        return text

    def create_update_operation(message: dict) -> UpdateOne:
        """
        Create a MongoDB `UpdateOne` operation for a single message.

        Args:
            message (dict): A message dictionary.

        Returns:
            UpdateOne: The MongoDB update operation.
        """
        ts = message["ts"]
        new_threads = []

        # Prepare a new root message if it does not exist in MongoDB
        if ts not in existing_messages:
            root_text_with_files = append_filenames_to_text(
                message.get("text", ""),
                message.get("files", [])
            )
            root_message = {
                "ts": ts,
                "text": root_text_with_files,
                "embedding": message.get("embedding"),
            }

            # Prepare thread messages for the root message
            thread_messages = [
                {
                    "ts": t["ts"],
                    "text": append_filenames_to_text(
                        t["text"],
                        t.get("files", [])
                    ),
                    "embedding": t.get("embedding"),
                }
                for t in message.get("thread_messages", [])
                if t["ts"] != ts
            ]

            return UpdateOne(
                {"ts": ts},
                {
                    "$set": {
                        "root_message": root_message,
                        "thread_messages": thread_messages
                    }
                },
                upsert=True
            )

        # Handle new thread messages for existing root message
        existing_thread_messages = existing_messages.get(ts, [])
        for thread_message in message.get("thread_messages", []):
            if not any(
                t["ts"] == thread_message["ts"]
                and t["text"] == thread_message["text"]
                for t in existing_thread_messages
            ):
                thread_text_with_files = append_filenames_to_text(
                    thread_message["text"], thread_message.get("files", [])
                )
                new_threads.append({
                    "ts": thread_message["ts"],
                    "text": thread_text_with_files,
                    "embedding": thread_message.get("embedding"),
                })

        if new_threads:
            return UpdateOne(
                {"ts": ts},
                {"$push": {"thread_messages": {"$each": new_threads}}}
            )
        return None

    # Iterate through all messages and prepare bulk operations
    for message in all_messages:
        operation = create_update_operation(message)
        if operation:
            bulk_operations.append(operation)

    return bulk_operations


def execute_bulk_operations(
        collection: object,
        bulk_operations: list
) -> None:
    """
    Execute MongoDB bulk operations.

    Args:
        collection (object):
            The MongoDB collection to execute operations on.
        bulk_operations (list):
            A list of `UpdateOne` operations for bulk execution.

    Returns:
        None
    """
    if bulk_operations:
        # Start the bulk write operation
        bulk_write_start = time.time()
        collection.bulk_write(bulk_operations)
        log_message(
            "Bulk write completed in "
            f"{time.time() - bulk_write_start:.2f} seconds.",
            "info"
        )


def update_existing_threads(
        client: object,
        channel_id: str,
        days_ago: int = 3,
) -> None:
    """
    Updates existing threads by fetching new replies for root messages
    within a cutoff period.

    Args:
        client (object):
            The Slack WebClient instance for API interactions.
        channel_id (str): The ID of the Slack channel.
        days_ago (int): The number of days to look back for root
            messages. Defaults to 3.

    Returns:
        None
    """
    # Get the MongoDB collection for the channel
    collection = mongodb[channel_id]

    # Calculate the cutoff timestamp
    cutoff_datetime = datetime.now() - timedelta(days=days_ago)
    cutoff_timestamp = cutoff_datetime.timestamp()

    # Find all root messages with thread messages in MongoDB
    root_messages_with_threads = collection.find(
        {"thread_messages": {"$exists": True}}
    )

    for root_message in root_messages_with_threads:
        root_ts = root_message["ts"]

        # Skip updating threads for root messages older than the cutoff
        if float(root_ts) < cutoff_timestamp:
            continue

        # Fetch the latest replies for the thread
        thread_messages = get_thread_messages(client, channel_id, root_ts)
        if not thread_messages or "messages" not in thread_messages.data:
            continue

        # Exclude the root message from the fetched messages
        thread_replies = [
            msg
            for msg in thread_messages.data["messages"]
            if msg["ts"] != root_ts
        ]

        # Process each thread message to check if it's new
        existing_thread_ts = {
            msg["ts"]
            for msg in root_message.get("thread_messages", [])
        }
        new_thread_messages = []

        # Identify and process new thread messages
        for msg in thread_replies:
            # Avoid duplicates and bot messages
            if (
                msg["ts"] not in existing_thread_ts
                and msg.get("user") != "bot_user_id"
            ):
                # Ensure each message has text and embedding
                processed_message = {
                    "ts": msg["ts"],
                    "text": (
                        f"{get_member_name(msg['user'])} "
                        f"(UserID: <@{msg['user']}>): {msg['text']}"
                    ),
                    "embedding": (
                        generate_embedding(
                            msg["text"]
                        ) if "text" in msg else None
                    )
                }
                new_thread_messages.append(processed_message)

        # Add new thread messages to the root message only if there are
        # new messages
        if new_thread_messages:
            collection.update_one(
                {"ts": root_ts},
                {"$push": {"thread_messages": {"$each": new_thread_messages}}}
            )
            log_message(
                f"Updated thread for root "
                f"message {root_ts} with new replies.",
                "info"
            )


def cleanup_missing_messages(
        channel_id: str,
        channel_name: str,
        client: object,
        days_ago: int = 3,
) -> None:
    """
    Synchronise MongoDB with Slack data by removing missing root and
    thread messages.

    This function performs the following:
    1. Fetches recent messages from Slack and identifies root and
       thread messages.
    2. Removes placeholder root messages ("This message was deleted.")
       while retaining associated thread messages.
    3. Deletes root messages from MongoDB that no longer exist in Slack
       within the specified cutoff date.
    4. Verifies and removes thread messages in MongoDB that no longer
       exist in Slack.

    Args:
        channel_id (str):
            The ID of the Slack channel.
        channel_name (str):
            The name of the Slack channel.
        client:
            Slack WebClient for interacting with the Slack API.
        days_ago (int):
            The number of days to look back for recent messages.
            Defaults to 3 days.

    Returns:
        None
    """
    # Calculate the cutoff timestamp for filtering recent messages
    cutoff_datetime = datetime.now() - timedelta(days=days_ago)
    cutoff_timestamp = cutoff_datetime.timestamp()

    # Access the MongoDB collection for the specified Slack channel
    collection = mongodb[channel_id]

    # Step 1: Fetch root messages from Slack that are within the
    # cutoff date
    fetched_root_messages = get_conversations_history(client, channel_id)
    fetched_root_ts_list = [
        msg["ts"] for msg in fetched_root_messages.data.get("messages", [])
        if float(msg["ts"]) >= cutoff_timestamp
    ]

    # Handle placeholder root messages ("This message was deleted.")
    for msg in fetched_root_messages.data.get("messages", []):
        # Skip messages older than the cutoff
        if float(msg["ts"]) < cutoff_timestamp:
            continue

        # Check if the root message is a placeholder
        if msg.get("text") == "This message was deleted.":
            # Find the document in MongoDB to ensure it still has the
            # root_message field
            existing_doc = collection.find_one(
                {"ts": msg["ts"], "thread_ts": {"$exists": False}},
                {"root_message": 1}
            )

            # Skip if the root_message field is already removed
            if existing_doc and "root_message" not in existing_doc:
                continue

            # Remove the root_message field while retaining
            # thread_messages
            result = collection.update_one(
                {"ts": msg["ts"], "thread_ts": {"$exists": False}},
                {"$unset": {"root_message": ""}}
            )
            # Log the update only if a change occurred
            if result.modified_count > 0:
                log_message(
                    f"Removed root message but retained thread messages "
                    f"for ts: {msg['ts']} in MongoDB.",
                    "info"
                )
    # Step 2: Retrieve root and thread messages stored in MongoDB
    # within the cutoff date
    mongo_docs = list(
        collection.find(
            {
                "thread_ts": {"$exists": False},
                "ts": {"$gte": str(cutoff_timestamp)}
            },
            {
                "ts": 1,
                "root_message": 1,
                "thread_messages": 1
            }
        ).sort("ts", 1) # Sort documents by timestamp in ascending order
    )
    # Extract the timestamps of root and thread messages from MongoDB
    mongo_root_ts_list = [doc["ts"] for doc in mongo_docs]

    # Step 3: Delete root messages in MongoDB that no longer exist
    # in Slack
    missing_root_ts_list = set(mongo_root_ts_list) - set(fetched_root_ts_list)
    for root_ts in missing_root_ts_list:
        # Ensure the root message timestamp is within the cutoff
        if float(root_ts) >= cutoff_timestamp:
            result = collection.delete_one(
                {"ts": root_ts, "thread_ts": {"$exists": False}}
            )
            log_message(
                f"Removed root message with ts {root_ts} from "
                f"MongoDB for channel {channel_id}.",
                "info"
            )

    # Step 4: Verify and remove thread messages in MongoDB that no
    # longer exist in Slack
    for root_doc in mongo_docs:
        root_ts = root_doc["ts"]

        # Skip if the root message is missing from Slack
        if root_ts not in fetched_root_ts_list:
            continue

        # Fetch thread message timestamps from Slack for the current
        # root message
        slack_thread_ts_list = get_thread_ts_list_from_slack(
            root_ts, channel_id, client
        )

        # Identify thread messages in MongoDB that no longer exist
        # in Slack
        missing_thread_ts_list = set(
            [msg["ts"] for msg in root_doc.get("thread_messages", [])]
        ) - set(slack_thread_ts_list)

        if missing_thread_ts_list:
            # Remove missing thread messages from MongoDB
            collection.update_one(
                {"ts": root_ts},
                {
                    "$pull": {
                        "thread_messages": {
                            "ts": {
                                "$in": list(missing_thread_ts_list)
                            }
                        }
                    }
                }
            )
            log_message(
                f"Removed {len(missing_thread_ts_list)} thread "
                f"messages for root message {root_ts} in channel "
                f"{channel_name} ({channel_id}).",
                "info"
            )

    log_message(
        f"Cleanup completed for channel "
        f"{channel_name} ({channel_id}).",
        "info"
    )
