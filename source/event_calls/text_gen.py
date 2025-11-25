"""
text_gen.py

This module contains functions that allow the chatbot to generate text
responses based on user input. The chatbot can process text-based
requests and generate responses based on the context provided.

Functions:
- handle_text_processing: Process text-based requests with the chatbot.

Attributes:
- slack_bot_user_id (str): The user ID of the Slack bot.
"""

import asyncio
import prompts.prompts as prompts
from threadreader import threadreader, process_thread, filter_and_clean_thread
from envbase import slack_bot_user_id
from utils.openai_utils import openai_request_stream_to_slack
from utils.logging_utils import log_message

def handle_text_processing(
        client: object,
        event_ts: str,
        thread_ts: str,
        channel_id: str,
        user_id: str,
) -> None:
    """
    Process text-based requests with the chatbot.

    This function processes text-based requests with the chatbot. It
    sends the user's prompt to the AI model for processing and posts the
    response to the Slack channel. The chatbot processes the user's
    prompt and generates a response based on the context provided.

    Args:
        client (object): The Slack client object.
        event_ts (str): The timestamp of the event.
        thread_ts (str): The timestamp of the thread.
        channel_id (str): The ID of the Slack channel.
        user_id (str): The ID of the user who sent the message.
        files (list): A list of files attached to the message.

    Returns:
        None

    Raises:
        BadRequestError: Raised in case of errors during requests to the
            OpenAI API.
    """
    text_prompt = prompts.main_llm_text_prompts(slack_bot_user_id, user_id)

    log_message("Bot chat response received", "info")

    response_thread, response_id, done_ts = asyncio.run(
        process_thread(client, channel_id, thread_ts)
    )

    p_thread, _ = filter_and_clean_thread(
        thread=response_thread,
        done_ts=done_ts,
        until_ts=event_ts,
    )

    openai_request_stream_to_slack(
        model="gpt-5.1",
        prompt=p_thread,
        response_id=response_id,
        instructions=text_prompt,
        channel_id=channel_id,
        thread_ts=thread_ts,
        event_ts=event_ts,
        client=client,
    )
    log_message("Bot chat response sent", "info")
