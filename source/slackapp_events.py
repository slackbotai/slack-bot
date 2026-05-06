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
import asyncio
import os
import re
from envbase import slackapp, slack_bot_user_id
from event_calls.text_gen import handle_text_processing
from event_calls.summarisation import handle_summarise_request
from agentic_workflow.threads_data import (
    active_threads,
    enter_agentic_workflow,
    exit_agentic_workflow,
)
from utils.llm_functions import interpret_summary_bool
from utils.logging_utils import error_handler, log_error
from utils.message_utils import (
    extract_event_data,
    is_relevant_message,
    is_direct_message,
    preprocess_user_input,
    add_reaction,
    remove_reaction,
    post_ephemeral_message_ok
)


REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))


async def notify_thread_busy(
        client: object,
        channel_id: str,
        user_id: str,
        thread_ts: str,
) -> None:
    """
    Let the user know a previous request in the same thread is still running.
    """
    try:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            thread_ts=thread_ts,
            text=(
                "I'm still working on the previous request in this thread. "
                "Please wait for that response to finish before sending another."
            ),
        )
    except Exception as e:
        await asyncio.to_thread(
            log_error,
            e,
            "Failed to send busy-thread notice.",
        )


async def notify_request_timeout(
        client: object,
        channel_id: str,
        thread_ts: str,
        event_ts: str,
) -> None:
    """
    Tell the user their request timed out and clean up the visible status.
    """
    try:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts or event_ts,
            text=(
                "This request took too long and was stopped after "
                f"{REQUEST_TIMEOUT_SECONDS // 60} minutes. "
                "Please try again with a smaller file, narrower summary range, "
                "or shorter prompt."
            ),
        )
    except Exception as e:
        await asyncio.to_thread(
            log_error,
            e,
            "Failed to send request-timeout notice.",
        )


@slackapp.event("reaction_added")
async def handle_reaction_added_events(body: dict,) -> None:
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
        await slackapp.client.chat_delete(channel=item["channel"], ts=item["ts"])


@slackapp.action("acknowledge_summary_warning")
async def handle_acknowledge_summary_warning(
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
    await ack()

    await respond({
        "delete_original": True
    })


@slackapp.event("message")
@slackapp.event("app_mention")
@slackapp.event("file_shared")
async def message(
    event: dict,
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
    channel_id = None
    event_ts = None
    thread_ts = None
    processing_thread = None
    try:
        await ack()

        event_data = extract_event_data(event)
        user_input = event_data["user_input"]
        event_ts = event_data["event_ts"]
        thread_ts = event_data["thread_ts"]
        channel_id = event_data["channel_id"]
        user_id = event_data["user_id"]
        files = event_data["files"]

        if not is_relevant_message(event):
            return

        channel_type = event.get("channel_type")
        event_type = event.get("type")
        mentions_bot = f"<@{slack_bot_user_id}>" in user_input
        if event_type == "message" and channel_type != "im" and not mentions_bot:
            return

        if await is_direct_message(user_input, user_id, channel_type):

            user_input, thread_ts, channel_detected = preprocess_user_input(
                user_input,
                event_ts,
                thread_ts
            )

            if active_threads.get(thread_ts):
                await notify_thread_busy(
                    client,
                    channel_id,
                    user_id,
                    thread_ts,
                )
                return

            processing_thread = thread_ts
            enter_agentic_workflow(processing_thread)

            await add_reaction(
                client,
                channel_id,
                event_ts,
                "hourglass_flowing_sand"
            )

            value = None
            if channel_detected:
                # Interpret if a summary is requested
                try:
                    value = await asyncio.to_thread(
                        interpret_summary_bool, user_input
                    )

                    if value is True:
                        await post_ephemeral_message_ok(
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
                    await asyncio.to_thread(
                        log_error,
                        e,
                        "Error: Interpret summary bool",
                    )

            if value:
                error_context = "Error: Summarise request"
                await asyncio.wait_for(
                    handle_summarise_request(
                        client,
                        user_input,
                        event_ts,
                        channel_id,
                        user_id,
                        say,
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            else:
                error_context = "Error: Text processing"
                await asyncio.wait_for(
                    handle_text_processing(
                        client,
                        event_ts,
                        thread_ts,
                        channel_id,
                        user_id,
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )


    except asyncio.TimeoutError:
        await notify_request_timeout(
            client,
            channel_id,
            thread_ts,
            event_ts,
        )
        try:
            await remove_reaction(
                client,
                channel_id,
                event_ts,
                "hourglass_flowing_sand",
            )
            await add_reaction(
                client,
                channel_id,
                event_ts,
                "x",
            )
        except Exception as reaction_error:
            await asyncio.to_thread(
                log_error,
                reaction_error,
                "Failed to update reactions after request timeout.",
            )
    except Exception as e:
        try:
            await error_handler(
                e, client, channel_id, say, thread_ts,
                event_ts, context=error_context
            )
        except Exception as handler_error:
            await asyncio.to_thread(
                log_error,
                handler_error,
                "Failed while handling a message-processing error.",
            )
    finally:
        if processing_thread:
            exit_agentic_workflow(processing_thread)
