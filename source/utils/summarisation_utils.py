"""
summarisation_utils.py

This module contains utility functions for the summarisation feature.

Functions:
- channel_member_verification: Verify that the user is a member
    of the channel.
- tagged_collections: Get MongoDB collections for tagged channels.
- say_collections_time_ranges: Display the time ranges of the
    tagged collections.
- get_model_batch_size: Determine the batch size based on the
    estimated number of tokens in the input context.
- estimated_tokens: Estimate the number of tokens in the input
    context.

Attributes:
    None
"""

import time
from datetime import datetime

import tiktoken
from slack_sdk.errors import SlackApiError

from utils.message_utils import post_ephemeral_message_ok
from utils.logging_utils import log_message

def channel_member_verification(
        tagged_channel_ids: list,
        user_id: str,
        client: object
) -> None:
    """
    Support func to verify that the user is a member of the channel
    that is requested for summarisation.

    Args:
        tagged_channel_ids (list): List of tagged channel IDs.
        user_id (str): User ID of the user requesting the summarisation.
        client (object): Slack client object.
        channel_id (str): Channel ID where the request was made.
        event_ts (str): Event timestamp of the request.
        say (object): Slack say method to send messages.

    Returns:
        None
    
    Raises:
        SlackApiError: If there is an error fetching members
            of the channel.
        Exception: If there is an error checking channel membership.
    """
    for tagged_channel_id in tagged_channel_ids:
        try:
            all_members = []
            cursor = None
            while True:
                response = client.conversations_members(
                    channel=tagged_channel_id, cursor=cursor
                )
                members = response.get('members', [])
                all_members.extend(members)

                if user_id in members:
                    log_message(
                        f"User {user_id} found in channel "
                        f"{tagged_channel_id} (in this batch).",
                        "info"
                    )
                    break #User found, no need to continue

                metadata = response.get('response_metadata', {})
                cursor = metadata.get('next_cursor')
                if not cursor:
                    break

                time.sleep(1) # To avoid rate limiting
                log_message(
                    f"Members in channel {tagged_channel_id}: {all_members}",
                    "debug"
                )
                log_message(
                    f"Found {len(all_members)} members "
                    f"in channel {tagged_channel_id}",
                    "debug"
                )
            if user_id not in all_members:
                raise PermissionError(
                    f"User {user_id} needs to be a member of the tagged "
                    f"channels to access the data. Ensure that you are a "
                    f"member of the channel <#{tagged_channel_id}|>."
                )
            else:
                log_message(
                    f"User {user_id} found in channel "
                    f"{tagged_channel_id} (after checking all pages).",
                    "debug"
                )
        except SlackApiError:
            raise SlackApiError(
                f"Error fetching members of channel <#{tagged_channel_id}|>."
            )

        except PermissionError:
            raise

        except Exception:
            raise Exception(
                "Error checking channel membership."
            )


def tagged_collections(
        tagged_channel_ids: list,
        mongodb: object,
        channel_id: str,
        event_ts: str,
        client: object,
        user_id: str,
) -> list:
    """
    Support func to get mongodb collections for tagged channels.

    Args:
        tagged_channel_ids (list): List of tagged channel IDs.
        mongodb (object): MongoDB client object.
        channel_id (str): Channel ID where the request was made.
        event_ts (str): Event timestamp of the request.
        say (object): Slack say method to send messages.
        client (object): Slack client object.
        user_id (str): User ID of the user requesting the summarisation.
    
    Returns:
        list: List of MongoDB collections for the tagged channels.
    
    Raises:
        Exception: If there is an error fetching collections for
            the tagged channels.
    """
    collections = []
    for tagged_channel_id in tagged_channel_ids:
        if tagged_channel_id in mongodb.list_collection_names():
            collections.append(mongodb[tagged_channel_id])
            return collections
        else:
            raise Exception(
                    "I could not access data for one or more "
                    "tagged channels. Please ensure that I am a member "
                    "of the tagged channels. If you've recently added "
                    "me to the channel, I won't be able to download the "
                    "data until tonight."
                )


def say_collections_time_ranges(
        time_ranges: dict,
        client: object,
        channel_id: str,
        event_ts: str,
        say: object,
        user_id: str,
) -> None:
    """
    Support func to display the time ranges of the tagged collections.

    Args:
        time_ranges (dict): Dictionary of time ranges for
            the collections.
        client (object): Slack client object.
        channel_id (str): Channel ID where the request was made.
        event_ts (str): Event timestamp of the request.
        say (object): Slack say method to send messages.
        user_id (str): User ID of the user requesting the summarisation.
    
    Returns:
        None
    """
    print("Time Ranges:", time_ranges)

    # If there are multiple time ranges in the time_ranges dict and
    # they have the same start and end time
    if len(time_ranges.values()) > 1 and len(set(time_ranges.values())) == 1:
        start_timestamp, end_timestamp = next(iter(time_ranges.values()))
        start_date = datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(end_timestamp).strftime('%Y-%m-%d')

        say(
            channel=channel_id,
            thread_ts=event_ts,
            text=f"Time Range: [{start_date} - {end_date}] for all tagged channels"
        )
    # If there is only one time range in the time_ranges dict
    elif len(time_ranges.values()) == 1:
        for collection_name, (start_timestamp, end_timestamp) in time_ranges.items():
            start_date = datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(end_timestamp).strftime('%Y-%m-%d')

            # Find the respective channel name for collection_name
            channel_name = client.conversations_info(channel=collection_name)["channel"]["name"]

            say(
                channel=channel_id,
                thread_ts=event_ts,
                text=f"Time Range: [{start_date} - {end_date}] for {channel_name}"
            )
    # If there are multiple time ranges in the time_ranges dict and
    # they have different start and end times
    else:
        post_ephemeral_message_ok(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=event_ts,
            text=(
                "⚠️ You have received multiple time ranges. This is likely "
                "due to inconsistencies with the AI model or because one time "
                "range falls outside the creation date of the other "
                "channel(s). Please consider this discrepancy if it affects "
                "your intended summary. If necessary, try again or clarify "
                "the time range using terms like "
                "'last week', 'last month', 'past 6 months', etc."
            ),
        )
        for collection_name, (start_timestamp, end_timestamp) in time_ranges.items():
            start_date = datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(end_timestamp).strftime('%Y-%m-%d')

            # Find the respective channel name for collection_name
            channel_name = client.conversations_info(channel=collection_name)["channel"]["name"]

            say(
                channel=channel_id,
                thread_ts=event_ts,
                text=f"Time Range: [{start_date} - {end_date}] for {channel_name}"
            )


def get_model_batch_size(est_tokens: int,
                         client: object,
                         channel_id: str,
                         user_id: str,
                         event_ts: str,
) -> int:
    """
    Support func to determine the batch size based on the estimated
    number of tokens in the input context.

    Args:
        est_tokens (int): Estimated number of tokens in the
            input context.
        client (object): Slack client object.
        channel_id (str): Channel ID where the request was made.
        user_id (str): User ID of the user requesting the summarisation.
        event_ts (str): Event timestamp of the request.
    
    Returns:
        int: Batch size for the summarisation request.
    """
    if est_tokens < 100000:
        batch_size = 150
    elif est_tokens < 400000:
        batch_size = 450
    elif est_tokens < 800000:
        batch_size = 650
        post_ephemeral_message_ok(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=event_ts,
            text=("⚠️ The input context is quite large, will take "
                  "a bit longer to go through, and will not be as "
                  "qualitative as a smaller time range. Consider "
                  "specifying a narrower timeframe in the future "
                  "whenever possible. It's also good practise to "
                  "be specific about the information you're looking "
                  "for in a summarisation request."),
        )
    elif est_tokens > 800000:
        batch_size = 1200
        post_ephemeral_message_ok(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=event_ts,
            text=("⚠️ The input context is very large, will take "
                  "longer to go through, and will not be as "
                  "qualitative as a smaller time range. Consider "
                  "specifying a narrower timeframe in the future "
                  "whenever possible. It's also good practise to "
                  "be specific about the information you're looking "
                  "for in a request."),
        )
    else:
        batch_size = 2000
        post_ephemeral_message_ok(
            client=client,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=event_ts,
            text=("⚠️ Something went wrong when selecting a "
                  "batch_size, and it's set to the highest value. "
                  "This will most likely result in low "
                  "quality details in the end-result."),
        )
    return batch_size


def estimated_tokens(
        query: str,
        summary_input: str,
) -> int:
    """
    Support func to estimate the number of tokens in the input context.

    Args:
        query (str): Query text.
        summary_input (str): Summary text.
    
    Returns:
        int: Estimated number of tokens in the input context.
    """
    # Model we're using for token encoding
    encoding = tiktoken.encoding_for_model("gpt-4o-mini")

    # Combine query and text
    full_input = query + "\n" + summary_input

    # Estimated token count for the FULL input (query + texts)
    est_tokens = len(encoding.encode(full_input))
    log_message(
        f"Tiktoken estimated input tokens (Text + Query): {est_tokens}",
        "info"
    )

    return est_tokens
