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

import prompts.prompts as prompts
from threadreader import threadreader
from envbase import slack_bot_user_id
from utils.openai_utils import openai_request_stream_to_slack
from utils.logging_utils import log_message

def handle_text_processing(
        client: object,
        say: callable,
        event_ts: str,
        thread_ts: str,
        channel_id: str,
        user_id:str,
) -> None:
    """
    Process text-based requests with the chatbot.

    This function processes text-based requests with the chatbot. It
    sends the user's prompt to the AI model for processing and posts the
    response to the Slack channel. The chatbot processes the user's
    prompt and generates a response based on the context provided.

    Args:
        client (object): The Slack WebClient object used to interact
            with the Slack Web API. This client allows the bot to send
            messages, delete messages, retrieve information about
            channels and users, and perform other operations
            through Slack's Web API.
        say (callable): A parameter provided by the Slack Bolt
            framework. It is a function that allows the bot to send
            messages to the Slack channel or user. It is used to
            respond to events or commands.
        event_ts (str): The timestamp of the event that triggered the
            text processing.
        user_id (str): The user ID of the user who triggered the text
            processing.
        thread_ts (str): The timestamp of the thread where the text
            processing was requested.
        channel_id (str): The ID of the Slack channel where the response
            will be posted.
        input_history (list): The list of messages in the thread history
            leading up to the text processing request.
        completion (object): The completion object from the AI client
            containing the response from the AI model.
        browse_mode (bool): A boolean flag indicating whether the
            chatbot is in browse mode.

    Returns:
        None

    Raises:
        BadRequestError: Raised in case of errors during requests to the
            OpenAI API.
    """
    text_prompt = prompts.main_llm_text_prompts(slack_bot_user_id, user_id)

    log_message("Bot chat response received", "info")

    _, formatted_messages = threadreader(
        client,
        thread_ts,
        channel_id,
        slack_bot_user_id,
        text_prompt,
        function_state="chat"
    )

    openai_request_stream_to_slack(
        model="gpt-5",
        prompt=formatted_messages,
        channel_id=channel_id,
        thread_ts=thread_ts,
        event_ts=event_ts,
        client=client,
        say=say
    )
    log_message("Bot chat response sent", "info")
