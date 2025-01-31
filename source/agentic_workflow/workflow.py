"""
workflow.py

This module contains the main function to run the interview process
and handle Slack interactions.

Functions:
- report_agentic_workflow: Main function to run the interview process
    and handle Slack interactions.

Attributes:
    None
"""

from pathlib import Path

from utils.logging_utils import log_message, log_error
from agentic_workflow.node_builder import main_node_builder
from agentic_workflow.threads_data import exit_agentic_workflow
from agentic_workflow.markdown_to_docx import (
    save_report_to_docx, send_docx_to_slack
)

def report_agentic_workflow(
        client: object,
        user_input: str,
        thread_ts: str,
        event_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
        say: callable,
) -> None:
    """
    Main function to run the interview process and handle
    Slack interactions.

    Args:
        client (object): The Slack client instance.
        user_input (str): The user input to start the workflow.
        thread_ts (str): The timestamp of the initial thread message.
        event_ts (str): The timestamp of the event that triggered
            the workflow.
        channel_id (str): The ID of the Slack channel.
        slack_bot_user_id (str): The user ID of the bot.
        say (callable): A function to send messages to Slack.
    """
    log_message("Report creation activated", "info")

    graph = main_node_builder(
        client,
        thread_ts,
        event_ts,
        channel_id,
        slack_bot_user_id,
        say
    )
    config = {"configurable": {"thread_id": thread_ts}, "recursion_limit": 50}
    max_analysts = 3
    input_dict = {"u_input": user_input, "max_analysts": max_analysts}


    graph.invoke(input_dict, config)

    timeout = graph.get_state(config)
    if timeout.values.get('timeout'):
        exit_agentic_workflow(thread_ts)
        return

    final_state = graph.get_state(config)
    response_ts = final_state.values.get('response_ts')
    final_report = final_state.values.get('final_report')
    client.chat_update(
        channel=channel_id,
        ts=response_ts,
        text="Here is the finalised document. :arrow_down:"
    )
    if final_report:
        docx_file_path = save_report_to_docx(final_report)

        send_docx_to_slack(
            client,
            channel_id,
            thread_ts,
            docx_file_path
        )
    Path(docx_file_path).unlink()

    log_message("Report creation completed", "info")

    exit_agentic_workflow(thread_ts)
    return
