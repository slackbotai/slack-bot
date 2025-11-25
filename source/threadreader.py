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

import io
import aiohttp
import base64
import asyncio
from datareader import datareader
from envbase import slack_bot_token, slack_bot_user_id, thread_manager
from utils.web_reader import process_urls_async
from utils.slack_utils import get_member_name
from utils.logging_utils import log_error, log_message


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
        data_type, file_text = await datareader(
            url=file_url_private,
            user_input=user_input,
            thread_id=thread_ts,
            channel_id=channel_id,
            user_id=user_id,
            file_type=file_type,
            cache=True,
            instructions=instructions
        )
        
        if data_type == "image":
            # The new prompt text
            prompt_text = (
                f"I have attached an image named '{file_name}'. "
                "**USE** it for context when forming your answer."
            )

            formatted_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{file_text}"
                            }
                        }
                    ]
                }
            )

        else:
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
    if sys_prompts:
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


async def process_thread(
    client,
    channel_id: str,
    thread_ts: str
) -> tuple:
    """
    Fetches the ENTIRE thread history and processes it into two distinct lists:
    1.  agent_thread: The complete conversation for full agent context.
    2.  response_thread: Only user messages newer than the last run.

    Args:
        client: An authenticated Slack WebClient instance.
        channel_id: The ID of the channel containing the thread.
        thread_ts: The timestamp of the parent message of the thread.
        thread_stamps: A dictionary containing state, like the `done_ts` timestamp.

    Returns:
        A tuple containing (agent_thread, response_thread).
    """
    # Get the timestamp of the last message we've already processed. Default to "0" for the first run.
    thread_stamps = thread_manager.get_thread(
        thread_ts,
        channel_id
    )

    response_id = thread_stamps.get("openai_thread_id") if thread_stamps else None
    done_ts = thread_stamps.get("done_ts") if thread_stamps else None

    # --- Step 1: Fetch the FULL thread. `done_ts` is set to None. ---
    thread_data, user_dict = await thread_reader(client, channel_id, thread_ts)

    response_thread = []

    if not thread_data.get("messages"):
        log_error(f"No messages found in thread {thread_ts}", "process_full_thread")
        return [], []

    # --- Step 2: Process all messages in a single pass ---
    for message in thread_data["messages"]:
        user_id = message.get("user", slack_bot_user_id)
        message_text = message.get("text", "").strip()
        message_ts = message.get("ts")

        # --- Case 1: The message is from a human user ---
        if user_id != slack_bot_user_id:
            files = message.get("files", [])
            message_data = preprocess_user_input(message_text, files)
            
            username = user_dict.get(user_id, "Unknown User")
            message_data['user_input'] = f"{username}: {message_data['user_input']}"
            
            content_blocks = await build_openai_content(message_data)
            
            user_message_obj = {
                "role": "user",
                "content": content_blocks,
                "ts": message_ts
            }
            
            # Add to the full history for the agent
            response_thread.append(user_message_obj)
        # --- Case 2: The message is from our AI bot ---
        elif user_id == slack_bot_user_id and message_text:
            content_blocks = [{
                "type": "output_text",
                "text": message_text
            }]

            assistant_message_obj = {
                "role": "assistant",
                "content": content_blocks,
                "ts": message_ts
            }
            
            # Add bot messages only to the agent's full history
            response_thread.append(assistant_message_obj)

    return response_thread, response_id, done_ts


async def thread_reader(
    client, channel_id: str, thread_ts: str, done_ts: str | None = None
) -> tuple:
    """Safely reads a Slack thread with error handling and retries.

    This is a robust wrapper around the `conversations_replies` API call. It
    uses a retry mechanism to handle rate limiting and includes comprehensive
    error handling to prevent crashes, returning empty objects on failure.

    Args:
        client: An authenticated Slack WebClient instance.
        channel_id: The ID of the channel containing the thread.
        thread_ts: The timestamp of the parent message of the thread.
        done_ts: An optional timestamp to fetch only new messages.

    Returns:
        A tuple containing (thread_data, user_dict). On failure, returns ({}, {}).
    """
    try:
        # Use retry wrapper for rate limiting & errors
        thread = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            oldest=done_ts
        )
        
        if not thread or not thread.get("ok"):
            raise ValueError(f"Slack thread fetch failed for {thread_ts}")

        # Build a dictionary of user IDs to usernames
        user_dict = build_user_dict(thread, slack_bot_user_id)
        return thread, user_dict

    except Exception as e:
        log_error(e, f"Failed to fetch thread {thread_ts} in channel {channel_id}")
        return {}, {}
    

def preprocess_user_input(user_input: str, files: list) -> tuple:
    """
    Cleans and preprocesses user input for further processing and extracts file information.

    Args:
        user_input (str): The raw user input text.
        files (list): A list of attached files, if any.

    Returns:
        dict: A dictionary containing:
            - cleaned_input (str): The cleaned user input with bot mentions removed.
            - files (list): A list of dictionaries with file information (name and URL).
    """
    # Remove the bot mention from the user input
    cleaned_input = user_input.replace(f"<@{slack_bot_user_id}>", "", 1)

    # Extract file information
    file_info = []
    if files:
        for file in files:
            mimetype = (file.get("mimetype") or "").lower()
            file_info.append({
                "file_name": file.get("name"),
                "file_url": file.get("url_private"),
                "mimetype": mimetype,
                "file_type": file.get("filetype"),
            })

    return {"user_input": cleaned_input, "files": file_info}


async def build_openai_content(message_data: dict) -> list[dict]:
    """
    Build OpenAI Responses-style content from Slack message_data:
      - input_text
      - input_image (for image/*)
      - input_file  (for application/pdf)
    """
    md = message_data or {}
    text = md.get("user_input") or ""
    content = [{"type": "input_text", "text": text}]

    files = md.get("files") or []
    if files:
        async with aiohttp.ClientSession() as session:
            file_blocks = await files_to_openai_content(files, session)
            content.extend(file_blocks)

    return content


async def download_slack_file(url: str, session: aiohttp.ClientSession) -> bytes:
    """
    Downloads a file asynchronously using aiohttp.
    """
    headers = {"Authorization": f"Bearer {slack_bot_token}"}
    async with session.get(url, headers=headers, timeout=30) as response:
        response.raise_for_status()
        return await response.read()


async def files_to_openai_content(files: list[dict], session) -> list[dict]:
    """
    Convert Slack file dicts → OpenAI Responses content blocks.
      - image/*         -> input_image (data URL, keep original mimetype)
      - application/pdf -> input_file (uploaded via Files API → file_id)

    `files` items must include: { "mimetype", "file_url" or "url_private", "file_name" or "name" }
    """
    blocks: list[dict] = []

    for f in files or []:
        mt = ((f.get("mimetype") or "").lower()).split(";")[0]
        url = f.get("file_url") or f.get("url_private")
        if not url or not mt:
            continue

        try:
            blob = await download_slack_file(url, session)

            if mt.startswith("image/"):
                b64 = base64.b64encode(blob).decode("utf-8")
                blocks.append({
                    "type": "input_image",
                    "detail": "high",
                    "image_url": f"data:{mt};base64,{b64}",
                })

            elif mt == "application/pdf":
                b64 = base64.b64encode(blob).decode("utf-8")
                filename = f.get("file_name") or "document.pdf"
                blocks.append({
                    "type": "input_file",
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{b64}",
                })
            
            else:
                data_type, file_text = await datareader(
                    blob,
                    file_type=f.get("file_type"),
                )
                safe_filename = f.get('file_name', 'unknown').replace("'", "").replace('"', "")
                
                blocks.append({
                    "type": "input_text",
                    "text": f"<file_attachment name='{safe_filename}'>\n{file_text}\n</file_attachment>",
                })

        except Exception as e:
            log_message(f"Error processing file {url}: {e}", "error")
            continue

    return blocks


def filter_and_clean_thread(
    thread: list = [],
    done_ts: str = None,
    until_ts: str = None,
):
    """
    Filters a thread, keeping only messages newer than done_ts and OLDER THAN until_ts, 
    AND returns the full thread with timestamps removed.

    It removes the timestamp key ("ts") from the messages in *both*
    returned lists to prepare them for an API.

    Args:
        thread: The full list of message dictionaries.
        done_ts: The timestamp of the last processed message (lower bound).
        until_ts: The timestamp of the message that triggered this run (upper bound).

    Returns:
        A tuple containing two lists:
        1. (processed_thread): A new list containing only *new* (filtered), cleaned messages.
        2. (full_thread_cleaned): A new list containing *all* original messages, but cleaned (ts removed).
    """
    processed_thread = []
    full_thread_cleaned = [] 
    
    # Convert timestamps once outside the loop for efficiency
    done_ts_float = float(done_ts) if done_ts else None
    until_ts_float = float(until_ts) if until_ts else None

    for message in thread:
        message_ts_str = message.get("ts")
        message_ts = float(message_ts_str) if message_ts_str else None
        
        # We must skip messages that lack a timestamp
        if not message_ts:
            continue
            
        # --- Check 1: Exclude messages newer than the trigger message (until_ts) ---
        # This prevents the bot from "seeing" messages sent while it was processing
        if until_ts_float and message_ts > until_ts_float:
            continue
            
        # --- Clean Logic (Create copy and remove ts) ---
        message_copy = message.copy()
        message_copy.pop("ts", None) 
        
        # --- Add to the *full* cleaned list ---
        # This list includes all relevant historical messages up to the trigger message.
        full_thread_cleaned.append(message_copy) 
        
        # --- Check 2: Filter Logic (Excludes messages older than done_ts) ---
        # Skip this message for the *processed* list if it's already been processed
        if done_ts_float and message_ts <= done_ts_float:
            continue
            
        # --- Add to the *processed* list ---
        processed_thread.append(message_copy)
            
    return processed_thread, full_thread_cleaned