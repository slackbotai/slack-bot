"""
streamutils.py

This module contains utility functions for handling large amounts
of text and splitting the message up into chunks if the AI model's
response exceeds 3500 characters.

Functions:
- num_tokens_from_string: Returns the number of tokens in a text string.
- safe_split: Splits a text string into chunks of text that are less
    than or equal to a maximum size.
- update_chat_stream: Handles large amounts of text and splits the
    message up into chunks if the AI model's response exceeds 3500
    characters.
- split_aistream: Splits the aistream into chunks that are less than
    or equal to the Slack message limit.
- replace_emojis_with_placeholder: Replaces emojis with a placeholder
    string.

Attributes:
    styler: An instance of the Markdown2Slack class for converting
        markdown to Slack formatting.
"""

import re
import tiktoken

from utils.slack_markdown_converter import Markdown2Slack

styler = Markdown2Slack()

def num_tokens_from_string(
        string: str,
        encoding_name: str,
) -> int:
    """
    Returns the number of tokens in a text string.

    Calculates the number of tokens in a text string using the specified
    encoding. This is necessary because the number of tokens in a string
    can be different from the number of characters due to encoding. It's
    also a maximum limit for the number of tokens that can be processed.

    Args:
        string (str): The text string to calculate the number of
            tokens for.
        encoding_name (str): The name of the encoding to use.

    Returns:
        int: The number of tokens in the text string.
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def safe_split(
        input_string: str,
        max_size: int,
) -> list:
    """
    Splits a text string into chunks of text that are less than or equal
    to a maximum size.

    Takes in input_string and returns chunks of text that are less than
    or equal to max_size. It will split the text at the last space
    before the max_size if possible. If no space is found, it will split
    at the current point.

    Args:
        input_string (str): The input string to split.
        max_size (int): The maximum size of each chunk.

    Returns:
        list: A list of split chunks.
    """
    chunks = []
    current_chunk = ""

    for char in input_string:
        if (
            len(current_chunk.encode("utf-8"))
            + len(char.encode("utf-8"))
            < max_size
        ):
            current_chunk += char
        else:
            # Find a safe point to split (e.g., the last space)
            last_space = current_chunk.rfind(" ")
            if last_space != -1:
                # Split at the last space to avoid breaking words
                chunks.append(current_chunk[:last_space])
                current_chunk = current_chunk[last_space + 1 :] + char
            else:
                # If no space found, split at the current point
                chunks.append(current_chunk)
                current_chunk = char

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def update_chat_stream(
        client: object,
        channel_id: str,
        completion: list,
        response: dict,
        aistream: str,
) -> str:
    """
    Handles large amounts of text and splits the message up into
    chunks if the AI model's response exceeds 3500 characters.

    Args:
        client (object): The Slack client object.
        channel_id (str): The ID of the Slack channel.
        completion (list): A list of completions from the AI model.
        response (dict): The response dictionary from the Slack API.
        aistream (str): The current text stream.

    Returns:
        str: The updated text stream
    """
    slack_msg_limit = 3500  # Slack message character limit == 4000

    for count, chunk in enumerate(completion):

        if chunk.choices[0].delta.content is not None:
            # Concatenate the response to the aistream
            aistream += chunk.choices[0].delta.content
        aistream_placeholder = replace_emojis_with_placeholder(aistream)
        if len(aistream_placeholder) > slack_msg_limit:
            split_point = split_aistream(aistream, slack_msg_limit)

            fix_aistream = aistream[:split_point]

            client.chat_update(
                channel=channel_id,
                ts=response["ts"],
                text=f"{styler.convert(fix_aistream)}"
            )

            aistream = aistream[split_point:]

            # If there's still content, continue streaming
            # it in smaller chunks
            if len(aistream) > 0:
                # Post a new message to continue the conversation
                response = client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=response["ts"],
                    text="response..."
                )

        # Update the chat every 15 chunks
        if aistream and count % 15 == 0:
            if len(aistream_placeholder) < slack_msg_limit:
                client.chat_update(
                    channel=channel_id,
                    ts=response["ts"],
                    text=f"{styler.convert(aistream)}"
                )
            else:
                # Stop the loop to handle splitting
                # in the next iteration
                break

        # Look for finish signal to end streaming
        if chunk.choices[0].finish_reason == "stop":
            break

    # Check if the message exceeds Slack's character limit
    if len(aistream_placeholder) < slack_msg_limit:
        client.chat_update(
            channel=channel_id,
            ts=response["ts"],
            text=f"{styler.convert(aistream)}"
        )
    return


def split_aistream(aistream: str, slack_msg_limit: int,) -> int:
    """
    Splits the aistream into chunks that are less than or equal to the
    Slack message limit.

    Args:
        aistream (str): The input text stream to split.
        slack_msg_limit (int): The maximum size of each chunk.
    
    Returns:
        int: The split point for the aistream.
    """
    # Find the last occurrence of a newline within the message limit
    split_point = aistream.rfind("\n", 0, slack_msg_limit)

    # Track whether we are inside a code block
    inside_code_block = False
    code_block_pattern = re.compile(r'^```')

    # Split the text into lines to process for code block detection
    lines = aistream[:split_point].split("\n")
    for line in lines:
        if code_block_pattern.match(line.strip()):
            # Toggle the code block state on encountering " ``` "
            inside_code_block = not inside_code_block

    # If the split point is inside a code block,
    # move the split point backwards
    if inside_code_block:
        # Search for the start of the current code block
        split_point = aistream[:split_point].rfind("\n```")
        if split_point == -1:
            # If no suitable split point is found,
            # avoid splitting entirely
            split_point = 0

    # If no newline is found,
    # find the last space within the message limit
    if split_point == -1:
        split_point = aistream.rfind(" ", 0, slack_msg_limit)

    # If no space is found either, split at the character limit
    if split_point == -1:
        split_point = slack_msg_limit

    # Extract the content after the split point (next content)
    next_content = aistream[split_point:]

    # Check the last two lines in the next
    # content for unwanted whitespace
    lines = next_content.split("\n")
    if len(lines) > 1:
        last_line = lines[-1]
        second_last_line = lines[-2]

        # If both the last and second last
        # lines don't start with whitespace
        if not last_line.lstrip() and not second_last_line.lstrip():
            # Split point should happen before the second to last line
            # Go back to the last clean line
            split_point = aistream.rfind("\n", 0, split_point)

    return split_point


def replace_emojis_with_placeholder(
        message: str,
        placeholder_length: int = 7,
) -> str:
    """
    Function to replace emojis with a placeholder string.

    Args:
        message (str): The message to replace emojis in.
        placeholder_length (int): The length of the placeholder string.

    Returns:
        str: The message with emojis replaced by placeholders.
    """
    # Regular expression pattern to match emojis
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)

    # Replace emojis with a string of a fixed length
    message_with_placeholders = emoji_pattern.sub(
        'x' * placeholder_length, message
    )
    return message_with_placeholders
