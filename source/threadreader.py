"""
threadreader.py:

Processes Slack threads to extract and format messages, files, and URLs.

This module provides functionality to retrieve all replies from a
specified Slack thread, process each message, and extract relevant
information such as user messages, files, and URLs. It utilises the
Slack API for message retrieval and provides asynchronous processing
for handling files and URLs.

The main function, "threadreader", orchestrates the process of fetching
replies, building a user dictionary, and processing each message
sequentially. It also handles the asynchronous processing of files and
URLs within messages using helper functions.

Functions:
- fetch_replies: Fetches all replies in a Slack thread using Slack API.
- build_user_dict: Creates a dictionary mapping user IDs to usernames.
- process_message: Processes a single message, handling URLs and files.
- process_file_async: Asynchronously processes a single file.
- process_files_async: Asynchronously processes all files in a message.
- threadreader: Main function to process a Slack thread.

Attributes:
    slack_bot_token (str): Slack bot token used for authorisation.
"""

import asyncio
from datareader import datareader
from utils.web_reader import process_urls_async
from envbase import slack_bot_token
from utils.slack_utils import get_member_name


def fetch_replies(
        client: object,
        thread_ts: str,
        channel_id: str,
) -> object:
    """
    Fetch all replies in a Slack thread.

    Args:
        client (object): The Slack client instance.
        thread_ts (str): Timestamp of the thread.
        channel_id (str): Channel ID where the thread is.

    Returns:
        object: The data object containing all messages in the thread.
    """
    return client.conversations_replies(channel=channel_id, ts=thread_ts)


def build_user_dict(
        datathread: object,
        bot_user_id: str,
) -> dict:
    """
    Build a dictionary mapping user IDs to usernames.

    Args:
        datathread (object): The data object containing all
            messages in the thread.
        bot_user_id (str): The bot user ID.

    Returns:
        Dictionary of user IDs and usernames.
    """
    user_dict = {}
    for message in datathread.data["messages"]:
        user_id = message.get("user", bot_user_id)
        if user_id not in user_dict:
            user_name = get_member_name(user_id)
            user_dict[user_id] = user_name
    return user_dict


def process_message(
        search_term: str,
        message: dict,
        user_dict: dict,
        bot_user_id: str,
        formatted_messages: list,
        thread_ts: str,
        channel_id: str,
        function_state: str,
        browse_mode: bool,
        browse_executed: list,
) -> None:
    """
    Process a single message at a time and handle URLs and files.

    Args:
        search_term (str): The search term.
        message (dict): The message to process.
        user_dict (dict): Dictionary of user IDs and usernames.
        bot_user_id (str): The bot user ID.
        formatted_messages (list): List to store formatted messages.
        thread_ts (str): Timestamp of the thread.
        channel_id (str): Channel ID where the thread is.
        function_state (str): Current state of the function.
        browse_mode (bool): Flag for browsing mode.
        browse_executed (list): Flag for browsing execution.
    
    Returns:
        None
    """
    user_id = message.get("user", bot_user_id)
    user_name = user_dict[user_id]
    message_text = message["text"]
    if user_id != bot_user_id:
        # Process URLs in the message
        if not browse_executed[0]:
            asyncio.run(process_urls_async(
                search_term,
                formatted_messages,
                browse_mode
                )
            )
            browse_executed[0] = True
        # Process files in the message
        if ("files" in message and message["files"] and
                function_state != "preprocess"):
            asyncio.run(process_files_async(
                message,
                thread_ts,
                channel_id,
                user_id,
                formatted_messages
                )
            )
        # Append formatted user message
        formatted_messages.append({
            "role": "user",
            "content": f"{user_name} (UserID: <@{user_id}>): {message_text}"
        })
    else:
        # Append assistant response if the message is from the bot
        formatted_messages.append({
            "role": "assistant",
            "content": message_text
        })


async def process_file_async(
        file: dict,
        headers: dict,
        user_input: str,
        thread_ts: str,
        channel_id: str,
        user_id: str,
        formatted_messages: list,
        instructions: str,
) -> None:
    """
    Asynchronously process a single file.

    Args:
        file (dict): The file to process.
        headers (dict): The headers for the request.
        user_input (str): The user input.
        thread_ts (str): Timestamp of the thread.
        channel_id (str): Channel ID where the thread is.
        user_id (str): The user ID.
        formatted_messages (list): List to store formatted messages.
        instructions (str): The instructions for the request.
    
    Returns:
        None
    
    Raises:
        Exception: Raised when an error occurs processing a file.
    """
    file_url_private = file.get("url_private")
    file_type = file.get("filetype")
    file_name = file.get("name")

    if file_type not in [
        "pdf", "docx", "c", "cpp", "java", "py", "txt", "html", "quip",
        "xls", "xlsx", "xlsm", "xlsb", "odf", "css", "js", "json", "xml",
        "yaml", "yml", "sh", "bat", "m4a", "mp3", "wav", "jpg", "jpeg",
        "png", "gif", "bmp", "tiff", "tif", "webp", "heif", "csv"
    ]:
        return

    try:
        # Simulating datareader as an async call
        _, file_text = await datareader(
            url=file_url_private,
            urlheaders=headers,
            user_input=user_input,
            thread_id=thread_ts,
            channel_id=channel_id,
            user_id=user_id,
            file_type=file_type,
            cache=True,
            instructions=instructions
        )

        # Append formatted messages for output
        formatted_messages.append(
            {"role": "user", "content": f"<Document Name: {file_name}>"}
        )
        formatted_messages.append(
            {"role": "user", "content": f"<Document URL: {file_url_private}>"}
        )
        formatted_messages.append(
            {"role": "user", "content": "<Document Start:>"}
        )
        formatted_messages.append(
            {"role": "user", "content": file_text}
        )
        formatted_messages.append(
            {"role": "user", "content": "<Document End:>"}
        )

    except Exception:
        raise


async def process_files_async(
        message: dict,
        thread_ts: str,
        channel_id: str,
        user_id: str,
        formatted_messages: list,
) -> None:
    """
    Asynchronously process all files attached to a message.

    Args:
        message (dict): The message containing the files.
        thread_ts (str): Timestamp of the thread.
        channel_id (str): Channel ID where the thread is.
        user_id (str): The user ID.
        formatted_messages (list): List to store formatted messages.
    
    Returns:
        None
    """
    headers = {"Authorization": f"Bearer {slack_bot_token}"}
    instructions = message.get("text", "")
    user_input = message["text"]
    # Launch async tasks for each file
    tasks = [
        process_file_async(
            file,
            headers,
            user_input,
            thread_ts,
            channel_id,
            user_id,
            formatted_messages,
            instructions
        )
        for file in message["files"]
    ]
    # Run all tasks concurrently
    await asyncio.gather(*tasks)


def threadreader(
        client: object,
        thread_ts: str,
        channel_id: str,
        bot_user_id: str,
        sys_prompts: list = None,
        function_state:str = None,
        browse_mode:bool = False,
        search_term: str = None,
) -> tuple:
    """
    Processes a Slack thread by extracting messages, files, and URLs.

    Args:
        client (object): The Slack client instance.
        thread_ts (str): Timestamp of the thread.
        channel_id (str): Channel ID where the thread is.
        bot_user_id (str): The bot user ID.
        sys_prompts (list): List of system prompts.
            Defaults to None.
        function_state (str): Current state of the function.
            Defaults to None.
        browse_mode (bool): Flag for browsing mode.
            Defaults to False.
        search_term (str): The search term.
            Defaults to None.

    Returns:
        tuple: Tuple containing an empty string and formatted messages.
    """
    datathread = fetch_replies(
        client,
        thread_ts,
        channel_id
    )

    user_dict = build_user_dict(
        datathread,
        bot_user_id
    )

    formatted_messages = []
    if sys_prompts is not None:
        formatted_messages.extend(sys_prompts)

    browse_executed = [False]

    for message in datathread.data["messages"]:
        process_message(
            search_term,
            message,
            user_dict,
            bot_user_id,
            formatted_messages,
            thread_ts,
            channel_id,
            function_state,
            browse_mode,
            browse_executed
        )

    return "", formatted_messages
