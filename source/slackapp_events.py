"""
slackapp_events.py

This module contains event handlers that process events received from
the Slack API, specifically those related to user interactions within
the chatbot app. It integrates with various components, including the
OpenAI API for text and image generation, a web browser function for
handling web searches by the model, and a summarisation function for
summarising channel events.

Functions:
- handle_reaction_added_events: Handle delete AI bot messages with the
    :x: reaction.
- handle_acknowledge_summary_warning: Acknowledge the summary warning
    message and delete the original ephemeral message.
- message: Handle messages sent by users to the Slack app.

Attributes:
    slackapp (App): The Slack app instance (from "slack_bolt").
    slack_bot_user_id (str): The user ID of the Slack bot.
    styler (Markdown2Slack): An instance of the Markdown to Slack
        converter for formatting messages.
"""

from envbase import slackapp, slack_bot_user_id
from event_calls.image_gen import handle_image_generation
from event_calls.text_gen import handle_text_processing
from event_calls.summarisation import handle_summarise_request
from agentic_workflow.threads_data import active_threads
from utils.llm_functions import classify_user_request, interpret_summary_bool
from utils.logging_utils import error_handler, log_error
from utils.message_utils import (
    extract_event_data,
    is_relevant_message,
    is_direct_message,
    preprocess_user_input,
    add_reaction,
    post_ephemeral_message_ok
)

@slackapp.event("reaction_added")
def handle_reaction_added_events(body: dict,) -> None:
    """
    Handle delete AI bot messages with the :x: reaction.

    Args:
        body (dict): body parameter provided by the Slack Bolt
            framework. A dictionary that contains the payload of
            the event sent by Slack.

    Returns:
        None
    """
    event = body["event"]
    item = event["item"]
    reaction = event["reaction"]

    if reaction == "x" and event["item_user"] == slack_bot_user_id:
        slackapp.client.chat_delete(channel=item["channel"], ts=item["ts"])


@slackapp.action("acknowledge_summary_warning")
def handle_acknowledge_summary_warning(
        ack: callable,
        respond: callable,
) -> None:
    """
    Acknowledge the summary warning message and delete the original
    ephemeral message.

    Args:
        ack (callable): The Slack Bolt acknowledge function.
        respond (callable): The Slack Bolt respond function.

    Returns:
        None
    """
    ack()

    respond({
        "delete_original": True
    })


@slackapp.event("message")
@slackapp.event("file_shared")
def message(
    args: dict,
    client: object,
    say: callable,
    ack: callable,
) -> None:
    """
    Handle messages sent by users to the Slack app.

    Args:
        args (dict): The arguments dictionary containing the event data.
        client (object): The Slack client object.
        say (callable): The say function.
        ack (callable): The ack function.

    Returns:
        None
    
    Raises:
        BadRequestError: Raised in case of errors during requests to
            the OpenAI API.
        Exception: Raised for any other errors that occur during the message
            handling process.
    """
    error_context = "Error: Message handling"
    try:
        ack()

        data = args.__dict__
        event_data = extract_event_data(data.get("event"))
        user_input = event_data["user_input"]
        event_ts = event_data["event_ts"]
        thread_ts = event_data["thread_ts"]
        channel_id = event_data["channel_id"]
        user_id = event_data["user_id"]
        files = event_data["files"]

        if not is_relevant_message(data.get("event")):
            return

        if active_threads.get(thread_ts):
            return

        if is_direct_message(client, user_input, user_id, channel_id):

            user_input, thread_ts = preprocess_user_input(
                user_input,
                event_ts,
                thread_ts
            )

            add_reaction(
                client,
                channel_id,
                event_ts,
                "hourglass_flowing_sand"
            )

            completion = classify_user_request(
                client,
                thread_ts,
                channel_id,
                slack_bot_user_id,
                user_input,
                files
            )

            if completion != "llm-query":
                # Interpret if a summary is requested
                try:
                    value = interpret_summary_bool(user_input)

                    if value is True:
                        post_ephemeral_message_ok(
                            client=client,
                            channel_id=channel_id,
                            user_id=user_id,
                            thread_ts=event_ts,
                            text=(
                                ":information_source: It seems that you may have "
                                "tried to request a summary of past channel events. "
                                "Please include the channel you wish to "
                                "summarise from in your message like this: "
                                "<#C06PG2GFUSC> (#channel)."
                            )
                        )
                except Exception as e:
                    log_error(e, context="Error: Interpret summary bool")

            if "llm-chat" in completion:
                error_context = "Error: Text processing"
                handle_text_processing(
                    client,
                    say,
                    event_ts,
                    thread_ts,
                    channel_id,
                    user_id
                )

            elif "llm-imagegen" in completion:
                error_context = "Error: Image generation"
                handle_image_generation(
                    client,
                    say,
                    thread_ts,
                    event_ts,
                    channel_id
            )

            elif "llm-query" in completion:
                error_context = "Error: Summarise request"
                handle_summarise_request(
                    client,
                    user_input,
                    event_ts,
                    channel_id,
                    user_id,
                    say
                )

    except Exception as e:
        error_handler(
            e, client, channel_id, say, thread_ts,
            event_ts, context=error_context
        )
