"""
summarisation.py

This module contains functions that handle summarisation requests
from the Slack bot. The chatbot processes summarisation requests
from users and generates structured summaries based on the context
provided.

Functions:
    handle_summarise_request: Handles summarisation requests from
        the Slack bot.
    interpret_time_range: Interprets the time range from a
        natural language query.
    get_start_end_dates: Gets the start and end timestamps
        for the query.
    batching: Retrieves messages from MongoDB in batches based
        on the start and end timestamps.
    similarity: Calculates cosine similarity between the query
        and messages in the batch.
    create_message_link: Formats a Slack message URL correctly based
        on whether it's a root message or a thread reply.
    get_summary: Generates a structured summary from relevant messages.

Attributes:
    aiclient (object): The OpenAI API client object.
    slack_bot_user_id (str): The ID of the Slack bot user.
    mongodb (object): The MongoDB client object.
    BATCH_MODEL (str): The name of the batch summarisation model.
    SUMMARY_MODEL (str): The name of the summary summarisation model.
"""
# Standard library imports
import re
from datetime import datetime, timedelta

# Third-party library imports
import asyncio

# Local application imports
from envbase import (
    aiclient, slack_bot_user_id, mongodb, BATCH_MODEL, SUMMARY_MODEL,
    workspace_subdomain,
)
from prompts.prompts import main_llm_query_prompts
from utils.llm_functions import interpret_timerange
from utils.slack_markdown_converter import Markdown2Slack
from utils.message_utils import post_ephemeral_message_ok
from utils.cost_tracker import calculate_cost, save_cost_data, save_cost_graph
from utils.summarisation_utils import (
    channel_member_verification, tagged_collections,
    say_collections_time_ranges, get_model_batch_size, estimated_tokens
)
from utils.logging_utils import log_message, log_error
from utils.message_utils import remove_reaction

MODEL = "gpt-4o-mini"
FINAL_MODEL = "gpt-4o"


def handle_summarise_request(
        client: object,
        query: str,
        event_ts: str,
        channel_id: str,
        user_id: str,
        say: callable,
) -> None:
    """
    Handles summarisation requests by retrieving relevant messages
    from MongoDB in batches, calculating similarity, and posting a
    structured summary back to Slack.

    Args:
        query (str): The user's query.
        event_ts (str): The timestamp of the event.
        slack_channel_id (str): The ID of the Slack channel.
        user_id (str): The ID of the user making the request.
        say (callable): The function to send messages back to Slack.

    Returns:
        None
    """
    log_message(
        "Summarisation Activated",
        "info"
    )
    # Regular expression to extract channel ID from a Slack link
    slack_channel_id_pattern = r"<#([A-Za-z0-9]+)\|>"

    # Extract the channel ID
    tagged_channel_ids = re.findall(slack_channel_id_pattern, query)
    log_message(
        f"Channel IDs: {tagged_channel_ids}",
        "info"
    )

    if not tagged_channel_ids:
        # If no valid Slack channel is found, send an error message
        raise ValueError("No valid Slack channel found in the query.")
        # Exit the function if no valid channel is tagged in the query
        # (Should not be able to get here but just in case)

    # Check if the user is a member of the tagged channel(s)
    channel_member_verification(
        tagged_channel_ids, user_id, client
    )
    # Get MongoDB collection ids for each tagged channel
    collections = tagged_collections(
        tagged_channel_ids, mongodb, channel_id,
        event_ts, client, user_id
    )
    # Get the MongoDB collections for the channels
    collections = [mongodb[c] for c in tagged_channel_ids]

    # Prepare the query by removing bot mentions and tagged channel IDs
    query = query.replace(f"<@{slack_bot_user_id}>", "").strip()
    for tagged_channel_id in tagged_channel_ids:
        query = query.replace(f"<#{tagged_channel_id}|>", "").strip()

    # -------------------> START OF RAG WORKFLOW <------------------- #

    # Variables for batching
    batch_size = 500
    skip = 0

    # List to store all messages from all collections
    all_messages = []

    # Dictionary to store time ranges for each collection
    time_ranges = {}

    # Keep track of channels where the ephemeral message has been sent
    sent_messages = set()

    for collection in collections:

        # Get the tagged channel ID for the summary
        tagged_channel_id = collection.name

        log_message(
            f"Processing channel: {collection.name}",
            "info"
        )
        # Interpret the time range from the query
        time_range = interpret_time_range(
            query,
            collection,
        )
        # Get the start and end timestamps for the query
        start_timestamp, end_timestamp = get_start_end_dates(
            client, channel_id, user_id,
            event_ts, time_range, sent_messages,
        )
        # Save the time range for the collection
        time_ranges[collection.name] = (start_timestamp, end_timestamp)

        # Get relevant messages from MongoDB in batches
        batch = batching(
            start_timestamp,
            end_timestamp,
            collection,
            batch_size,
            skip,
            tagged_channel_ids,
        )
        # Unpack the batches of messages
        messages = batch_unpacking(
            batch,
            tagged_channel_id,
            batch_size,
            skip,
        )
        # Append messages to the full list for all collections
        all_messages.extend(messages)

    # Generate the summary and send it back to Slack
    formatted_summary = get_summary(  # pylint: disable=C0103
        all_messages,
        query,
        say,
        channel_id,
        user_id,
        event_ts,
        client,
    )
    # --------------------> END OF RAG WORKFLOW <-------------------- #

    # After processing all collections, report time ranges
    say_collections_time_ranges(
        time_ranges, client, channel_id, event_ts, say, user_id,
    )
    # Send the summary back to the Slack thread
    say(
        channel=channel_id,
        thread_ts=event_ts,
        text=formatted_summary,
    )
    remove_reaction(
        client,
        channel_id,
        event_ts,
        "hourglass_flowing_sand"
    )


def interpret_time_range(
        query: str,
        collection: object,
) -> dict:
    """
    Uses GPT-4o to interpret the time range from a natural language
    query.

    Args:
        query (str): The user's query.

    Returns:
        dict: A dictionary containing the start and end dates.

    Raises:
        json.JSONDecodeError: If there is an error parsing the JSON.
    """
    # Get the current date in the format 'YYYY-MM-DD'
    current_date = datetime.now().strftime("%Y-%m-%d")

    # First timestamp in the channel history
    start_timestamp = datetime.fromtimestamp(
        float(
            list(collection.find().sort("ts", 1).limit(1))[0]["ts"]
        )
    ).timestamp()

    # Start date of the channel history
    ch_start_date = datetime.fromtimestamp(
        start_timestamp
    ).strftime("%Y-%m-%d")
    response = interpret_timerange(
        current_date,
        ch_start_date,
        query,
    )
    # Debug print to verify the raw response format
    log_message(
        "Raw response from GPT-4: Start Date: "
        f"{response.start_date} | End Date: {response.end_date}",
        "debug"
    )

    return response


def get_start_end_dates(
        client: object,
        channel_id: str,
        user_id: str,
        event_ts: str,
        time_range: object,
        sent_messages: set,
) -> tuple:
    """
    Gets the start and end timestamps for the query based on the
    interpreted time range from interpret_time_range func.

    Args:
        client (object): The Slack WebClient object.
        channel_id (str): The ID of the Slack channel.
        user_id (str): The ID of the user making the request.
        event_ts (str): The timestamp of the event.
        time_range (dict): The interpreted time range as
            "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"
            from the GPT-4o model output.
        sent_messages (set): A set to keep track of channels where
            the ephemeral message has been sent.

    Returns:
        tuple: A tuple containing the start and end float timestamps.

    Raises:
        ValueError: If there is an error parsing the dates.
    """
    # Initialise timestamps in a While loop until valid dates are parsed
    while True:

        log_message(
            f"Time range interpreted: {time_range}",
            "info"
        )

        # Get the start and end dates from the time range dictionary
        start_date = time_range.start_date
        end_date = time_range.end_date

        try:
            # Parse the dates and makes sure
            # end date is at the end of the day
            start_timestamp = datetime.strptime(start_date, "%Y-%m-%d")
            end_timestamp = (
                datetime.strptime(end_date, "%Y-%m-%d")
                + timedelta(hours=23, minutes=59, seconds=59)
            )
            # Convert dates to Unix timestamps
            start_timestamp = start_timestamp.timestamp()
            end_timestamp = end_timestamp.timestamp()

        except ValueError as e:
            log_error(
                e,
                "Error parsing dates"
            )
            start_timestamp, end_timestamp = None, None

        # Check if the time range is more than 6 months
        if end_timestamp - start_timestamp > 15778463:
            if channel_id not in sent_messages:
                post_ephemeral_message_ok(
                    client=client,
                    channel_id=channel_id,
                    user_id=user_id,
                    thread_ts=event_ts,
                    text=("⚠️ This timeframe might be too broad and could "
                        "incur high costs. For future reference, "
                        "consider specifying a narrower timeframe for "
                        "better performance and cost reduction "
                        "if possible."),
                )
                sent_messages.add(channel_id)
        log_message(
            f"Start Timestamp: {start_timestamp}, "
            f"End Timestamp: {end_timestamp}",
            "info"
        )
        # TO DATES
        log_message(
            f"Date: {datetime.fromtimestamp(start_timestamp)} "
            f"to {datetime.fromtimestamp(end_timestamp)}",
            "info"
        )
        return start_timestamp, end_timestamp


def batching(
        start_timestamp: float,
        end_timestamp: float,
        collection: object,
        batch_size: int,
        skip: int,
        tagged_channel_ids: list,
) -> list:
    """
    Func to retrieve messages from MongoDB in batches based on
    the start and end timestamps.

    Args:
        start_timestamp (float): The start timestamp for the query.
        end_timestamp (float): The end timestamp for the query.
        collection (object): The MongoDB collection object.
        batch_size (int): The batch size for fetching messages.
        skip (int): The number of documents to skip in MongoDB.

    Returns:
        list: A list of batched documents from MongoDB.
    """
    log_message(
        f"Retrieving root and thread messages from "
        f"MongoDB in batches for channels: {tagged_channel_ids}",
        "info"
    )

    # Store all batches
    all_batches = []

    # While loop to fetch messages in batches from MongoDB
    while True:

        # Time filter if start and end timestamps are available
        time_filter = {}

        # Logic to apply time filter if valid timestamps are available
        if start_timestamp and end_timestamp:
            time_filter = {"ts": {
                "$gte": str(start_timestamp),
                "$lte": str(end_timestamp),
                }
            }
            log_message(
                f"MongoDB Time Filter: {time_filter}",
                "info"
            )
        else:
            log_message(
                "No time filter applied.",
                "info"
            )

        # Specifically retrieve the root ts, thread_messages.ts,
        # thread_messages.text, and thread_messages.embedding fields
        # for each document in the collection based on the time filter
        batch = list(collection.find(time_filter, {
            "ts": 1,
            "root_message.ts": 1,
            "root_message.text": 1,
            "root_message.embedding": 1,
            "thread_messages.ts": 1,
            "thread_messages.text": 1,
            "thread_messages.embedding": 1
        }).skip(skip).limit(batch_size))

        if not batch:
            log_message(
                "No more documents to retrieve.",
                "info"
            )
            break  # Exit when no more documents are fetched

        # Append to results
        all_batches.extend(batch)
        log_message(
            f"Fetched batch of {len(batch)} documents (skip={skip})",
            "info"
        )

        # Increment the skip to avoid fetching the same batch
        skip += batch_size

        # Stop the loop if fewer documents than batch_size are retrieved
        if len(batch) < batch_size:
            break

        log_message(
            f"Fetched batch of {len(batch)} "
            f"documents from MongoDB (skip={skip})",
            "info"
        )

    return all_batches


def batch_unpacking(
        batch: list,
        tagged_channel_id: str,
        batch_size: int,
        skip: int,
) -> list:
    """
    Unpacks the batch of messages and retrieves the root and thread
    messages for summarisation.

    Args:
        batch (list): A batch of messages from MongoDB.
        tagged_channel_id (str): The ID of the tagged Slack channel.
        batch_size (int): The batch size for fetching messages.
        skip (int): The number of documents to skip in MongoDB.

    Returns:
        list: A list of messages to be summarised.
    """
    # Initialise list to store messages
    messages = []

    # Define the regex pattern to match the specific UserID structure
    bot_pattern = re.compile(
        rf"\(UserID: <@{re.escape(slack_bot_user_id)}>\)")

    for doc in batch:
        # Process the root_message
        root_message = doc.get("root_message")
        if root_message:
            messages.append({
                "text": root_message["text"],
                "channel_id": tagged_channel_id,
                "timestamp": root_message["ts"],
                "root_ts": root_message["ts"],
            })
        # Process each thread_message within the document
        for thread_message in doc.get("thread_messages", []):
            if not bot_pattern.search(thread_message["text"]):
                messages.append({
                    "text": thread_message["text"],
                    "channel_id": tagged_channel_id,
                    "timestamp": thread_message["ts"],
                    "root_ts": doc["ts"],
                })
        # Increment the skip counter for the next batch
        skip += batch_size

    return messages


def create_message_link(
        channel_id: str,
        reply_ts: str,
        root_ts=None,
) -> str:
    """
    Helper func that formats a Slack message URL correctly based on
    whether it's a root message or a thread reply.

    Args:
        channel_id (str): The ID of the Slack channel.
        reply_ts (str): The timestamp of the reply message.
        root_ts (str): The timestamp of the root message if it's a
            thread reply.

    Returns:
        str: The formatted message URL.
    """
    reply_ts_formatted = reply_ts.replace(".", "")

    # Convert timestamp to readable time
    reply_date = datetime.fromtimestamp(float(reply_ts)).strftime('%Y-%m-%d')

    # Thread reply message
    if root_ts:
        root_ts_formatted = root_ts.replace(".", "")

        return (f"https://{workspace_subdomain}.slack.com/archives/"
                f"{channel_id}/p{reply_ts_formatted}"
                f"?thread_ts={root_ts_formatted}"
                f"&cid={channel_id}|"
                f"View [{reply_date}]")
    # Root message
    else:
        return (f"https://{workspace_subdomain}.slack.com/archives/"
                f"{channel_id}/p{reply_ts_formatted}|"
                f"View [{reply_date}]")


async def summarise_batch(
        model: str,
        query: str,
        batch: str = None,
        previous_summary: str = None,
) -> tuple:
    """
    Summarises a single batch of messages and
    returns the summary and token usage.

    Args:
        model (str): The name of the language model.
        query (str): The query for the summarisation.
        batch (str): The batch of messages to be summarised.
        previous_summary (str): The previous summary to be included
            in the summarisation.

    Returns:
        tuple: A tuple containing the summary, prompt tokens,
            completion tokens, and total tokens.

    Raises:
        Exception: If there is an error generating the summary.
    """
    try:
        # Running the summarisation in a separate thread
        response = await asyncio.to_thread(
            aiclient.chat.completions.create,
            model=model,
            messages=main_llm_query_prompts(
                slack_bot_user_id, query, batch, previous_summary,
            ),
            stream=False,
            top_p=0.1,
        )
        # Extract token usage
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

        return (
            response.choices[0].message.content.strip(),
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )
    except Exception as e:
        log_error(e, "Error generating summary")
        # Return None for summary and 0 for token counts
        return None, 0, 0, 0


async def summarise_in_batches(
        query: str,
        summary_input: str,
        est_tokens: int,
        client: object,
        channel_id: str,
        user_id: str,
        event_ts: str,
) -> str:
    """
    Summarises text in batches of messages concurrently using asyncio.

    Args:
        query (str): The user's query.
        summary_input (str): The input text to be summarised.
        est_tokens (int): The estimated number of tokens for the input.
        client (object): The Slack WebClient object.
        channel_id (str): The ID of the Slack channel.
        user_id (str): The ID of the user making the request.
        event_ts (str): The timestamp of the event.

    Returns:
        str: The formatted summary text.
    """
    # Get the batch size based on the estimated token count
    batch_size = get_model_batch_size(
        est_tokens, client, channel_id, user_id, event_ts
    )

    # Initialise token count
    batch_prompt_tokens = 0  # Tokens for the original batch model input
    batch_completion_tokens = 0  # Total batch model completion tokens
    final_completion_tokens = 0  # Completion tokens from final model
    total_tokens_used = 0  # Total tokens from all operations

    batch_summaries = []
    messages = summary_input.split("\n")
    tasks = []

    # Generate summaries for each batch of messages
    for i in range(0, len(messages), batch_size):
        batch = "\n".join(messages[i: i + batch_size])
        log_message(
            f"Generating summary for batch {i // batch_size + 1}...",
            "info"
        )
        tasks.append(summarise_batch(
            model=BATCH_MODEL,
            query=query,
            batch=batch,
            previous_summary=None,
            )
        )  # A task per batch

    # Run the tasks concurrently
    results = await asyncio.gather(*tasks)

    # Extract summaries and token usage from results
    batch_summaries = []
    for summary, p_tokens, c_tokens, total_tokens in results:
        if summary:
            log_message(
                f"Batch Summary: {summary}",
                "debug"
            )
            batch_summaries.append(summary)
            batch_prompt_tokens += p_tokens
            batch_completion_tokens += c_tokens
            total_tokens_used += total_tokens
            log_message(
                f"Batch Prompt Tokens: {p_tokens}",
                "debug"
            )

    # Summarise the batch summaries into a final summary
    (final_summary,
     final_p_tokens,
     final_c_tokens,
     final_total_tokens) = await summarise_batch(
        model=SUMMARY_MODEL,
        query=query,
        batch=None,
        previous_summary="\n".join(batch_summaries),
    )
    final_completion_tokens = final_c_tokens
    total_tokens_used += final_total_tokens
    log_message(
        f"FINAL INPUT TOKENS: {final_p_tokens}"
        f"FINAL OUTPUT TOKENS: {final_c_tokens}"
        f"FINAL TOTAL TOKENS: {final_total_tokens}",
        "debug"
    )

    # Calculate costs based on token usage
    cost_details = calculate_cost(
        batch_prompt_tokens,
        batch_completion_tokens,
        final_completion_tokens,
        BATCH_MODEL,
        SUMMARY_MODEL,
        cached=False,
    )
    # Get the current timestamp from logging
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save the cost details to the summarisation costs CSV file
    save_cost_data(
        cost_details,
        timestamp,
        batch_prompt_tokens,
        batch_completion_tokens,
        final_completion_tokens,
        BATCH_MODEL,
        SUMMARY_MODEL,
    )
    # Generate and save graph of summarisation costs
    save_cost_graph()

    log_message(
        f"Total tokens used (request + response): {total_tokens_used}",
        "info"
    )
    if final_summary:  # Check if final_summary is not None
        return final_summary.strip()  # Return the final summary
    else:
        return "Error generating summary."


def get_summary(
        all_messages: list,
        query: str,
        say: callable,
        channel_id: str,
        user_id: str,
        event_ts: str,
        client: object,
) -> tuple[str, bool]:
    """
    Func to generate a structured summary from relevant messages
    and send it back to Slack.

    Args:
        all_relevant_messages (list): A list of all relevant messages.
        query (str): The user's query.
        say (callable): The function to send messages back to Slack.
        channel_id (str): The ID of the Slack channel.

    Returns:
        str: The formatted summary text.

    Raises:
        Exception: If there is an error generating the summary.
        AttributeError: If token usage data is not available
            in the response.
    """
    # Initialise the Markdown to Slack converter
    styler = Markdown2Slack()
    # Initialise the final text list and message placeholders
    final_texts = []
    # Maps placeholder -> (link, message_index)
    message_placeholders = {}

    # Create placeholders and the mapping:
    for i, msg in enumerate(all_messages):
        root_ts = msg.get("root_ts", None)
        thread_ts = msg.get("timestamp", None)
        message_link = create_message_link(
            msg["channel_id"], thread_ts, root_ts
        )
        placeholder = f"[link{i}]"
        # Store link AND index
        message_placeholders[placeholder] = (message_link, i)
        final_texts.append(f"{msg['text']} {placeholder}")

    # Join the final texts to create the summary input
    summary_input = "\n".join(final_texts)
    # Estimate the number of tokens for the summary input
    est_tokens = estimated_tokens(query, summary_input)

    # Generate the summary using the summarisation models
    try:
        summary = asyncio.run(summarise_in_batches(
            query,
            summary_input,
            est_tokens,
            client,
            channel_id,
            user_id,
            event_ts,
            )
        )
        # Precise Replacement using the mapping:
        for placeholder, (link, _) in message_placeholders.items():
            summary = summary.replace(placeholder, link)

        # Convert the summary to Slack-compatible format
        formatted_summary = styler.convert(summary)

    # Handle exceptions and errors
    except Exception as e:
        log_error(e, "Error generating summary")
        say(
            channel=channel_id,
            text="Sorry, there was an error generating the summary."
        )
        return "", False
    # Log the summary
    log_message(
        "Sending the summary back to Slack...",
        "info"
    )
    # Return the formatted summary
    return formatted_summary
