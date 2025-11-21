"""
input_agents.py

This module contains the language graph for the input gathering process
of the research assistant.

Functions:
- extract_info: Extract new information from the user's input while
    preserving already filled variables.
- ask_user_for_info_with_ai: Dynamically use AI to identify and ask
    the user for missing information based on the current state.
- capture_human_feedback: Captures the last user message in a Slack
    thread, ignoring bot messages and the initial thread message.
- wait_for_feedback_periodically: Periodically checks for the latest
    user message in a Slack thread within a specified maximum wait time.
- check_input_complete: Check if all fields in the input graph
    are filled.
- exclude_document_blocks: Exclude messages within document blocks
    from the input thread and return document names.

Attributes:
    thread_storage: A MongoDB collection for storing thread data.
"""

import re
import time

from langgraph.graph import END
from slack_sdk.errors import SlackApiError

from envbase import thread_storage
from threadreader import threadreader
from utils.openai_utils import structured_output, openai_request
from utils.llm_functions import ExtractInfo, extract_new_info, extract_update_info
from prompts.agent_prompts import prompt_extract_info, prompt_to_retrieve_users_choices
from agentic_workflow.graph_classes import InputGraphState, ResearchGraphState
from utils.logging_utils import log_error
from utils.slack_utils import send_message_with_retry

def extract_info(
        state: InputGraphState,
        client: object,
        thread_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
) -> dict:
    """
    Extract new information from the user's input while preserving 
    already filled variables.

    This function utilizes the OpenAI API to extract structured data
    from the user's input message. It checks the current state for any
    filled values and adds new information extracted from the
    user's input, updating the state accordingly.

    Args:
        state (InputGraphState): The current state of the input graph,
            including previously filled variables.
        client (object): The Slack client instance for API calls.
        thread_ts (str): The timestamp of the initial thread message.
        channel_id (str): The Slack channel ID.
        slack_bot_user_id (str): The user ID of the Slack bot.

    Returns:
        dict: A dictionary containing the extracted information.
    """
    # Check if files are stored using the threadreader function
    _, thread = threadreader(client, thread_ts, channel_id, slack_bot_user_id)

    # Filtered thread
    filtered_thread, document_names = exclude_document_blocks(thread)

    additional_prompt = ""
    files = state.get("files", None)

    if state.get("files_urls_browse") == "files":
        # Check if files exist in MongoDB for this thread
        query = {"thread_id": thread_ts, "channel_id": channel_id}
        if thread_storage.count_documents(query) > 0:
            files = document_names

    elif state.get("files_pr_browse") == "urls":
        additional_prompt = f"""
        9. **Urls**: Extract urls or links from the text and return as a list
        (e.g., [https://www.example1.com/, https://www.example2.com/]).
        - *Current Value*: {state.get('urls', 'None')}
        """

    elif state.get("files_urls_browse") == "browse":
        additional_prompt = f"""
        9. **Browse Query**: The search query the user wants to browse the web.
        - *Current Value*: {state.get('browse_query', 'None')}
        """

    system_prompt = prompt_extract_info(
        topic=state.get("topic", "None"),
        description=state.get("description", "None"),
        report_type=state.get("report_type", "None"),
        files_urls_browse=state.get("files_urls_browse", "None"),
        index=state.get("index", "None"),
        introduction=state.get("introduction", "None"),
        conclusion=state.get("conclusion", "None"),
        source=state.get("source", "None"),
        additional_prompt=additional_prompt,
        text=f"{filtered_thread}"
    )
    extracted_data = structured_output(system_prompt, ExtractInfo)

    return {
        "topic": extracted_data.topic,
        "description": extracted_data.description,
        "report_type": extracted_data.report_type,
        "files_urls_browse": extracted_data.files_urls_browse,
        "index": extracted_data.index,
        "introduction": extracted_data.introduction,
        "conclusion": extracted_data.conclusion,
        "source": extracted_data.source,
        "urls": extracted_data.urls,
        "files": files,
        "browse_query": extracted_data.browse_query
    }


def ask_user_for_info_with_ai(
        state: InputGraphState,
        client: object,
        thread_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
        say: callable,
) -> str:
    """
    Dynamically use AI to identify and ask the user for missing
    information based on the current state. The function identifies
    missing fields in the state, determines what to ask about first,
    and uses AI to generate a question. It then sends the question
    to Slack and waits for a response from the user.

    Args:
        state (Dict[str, Any]): Current state dictionary, which may
            contain 'None' values for missing fields.
        client (SlackClient): The Slack client used to send and
            receive messages.
        thread_ts (str): The timestamp of the current thread in Slack.
        channel_id (str): The ID of the Slack channel to send the
            message to.
        slack_bot_user_id (str): The bot's user ID for the Slack app.
        say (callable): A Slack message sending function.

    Returns:
        str: A question generated by AI to ask the user about missing
            information, or the updated state with the user's
            responses to the question.
    """
    missing_fields = [key for key, value in state.items() if value is None]

    if missing_fields:
        if state.get("files_urls_browse") == "files":
            missing_fields = [
                field for field in missing_fields
                if field not in ["urls", "browse_query"]
            ]
            state["urls"] = False
            state["browse_query"] = False

        elif state.get("files_urls_browse") == "urls":
            missing_fields = [
                field for field in missing_fields
                if field not in ["files", "browse_query"]
            ]
            state["files"] = False
            state["browse_query"] = False

        elif state.get("files_urls_browse") == "browse":
            missing_fields = [
                field for field in missing_fields
                if field not in ["files", "urls"]
            ]
            state["urls"] = False
            state["files"] = False

        if missing_fields:
            field_to_ask = missing_fields[0]

            prompt = prompt_to_retrieve_users_choices(state, field_to_ask)

            ai_question = openai_request("gpt-4o-mini", prompt, 100, 0.2)
            latest_ts = None

            response = send_message_with_retry(
                client,
                channel_id,
                thread_ts,
                ai_question,
                log_context="Asking user for missing information."
            )

            latest_ts = response['ts']
            text, _ = wait_for_feedback_periodically(
                client,
                channel_id,
                thread_ts,
                latest_ts,
                slack_bot_user_id,
                state = "info"
            )
            if text is False:
                return {"timeout": True}

            q_and_a = f"Ai: {ai_question} | User: {text}"
            return {"u_input": q_and_a}

    field_name_mapping = {
        "topic": "Topic",
        "description": "Description",
        "report_type": "Report Type",
        "files_urls_browse": "Method (Files/URLs/Browse)",
        "index": "Index",
        "introduction": "Introduction",
        "conclusion": "Conclusion",
        "source": "Source",
        "urls": "URLs",
        "files": "Files",
        "browse_query": "Browse Query"
    }
    # Remove 'user_input' and create the formatted message
    filled_fields = {
    key: value
    for key, value in state.items()
    if value is not None and key != 'u_input'
    }
    # Prepare confirmation message
    confirmation_message = "Here is the information I have gathered:\n\n"

    for key, value in filled_fields.items():
        # Get the user-friendly name for the key
        # Default to the key if not found in mapping
        user_friendly_name = field_name_mapping.get(key, key)
        confirmation_message += f"• *{user_friendly_name}*: {value}\n"

    confirmation_message += ("\nDoes everything look correct? "
                             "If not, please tell me what to change. :blush:")

    # Send the confirmation message
    response = send_message_with_retry(
        client,
        channel_id,
        thread_ts,
        confirmation_message,
        log_context="Sending confirmation message."
    )

    # Wait for the confirmation from the user
    latest_ts = response['ts']
    text, _ = wait_for_feedback_periodically(
        client,
        channel_id,
        thread_ts,
        latest_ts,
        slack_bot_user_id,
        state="info"
    )
    if text is False:
        return {"timeout": True}
    field, text = extract_update_info(list(filled_fields.keys()), text)
    if not text:
        return filled_fields
    else:
        return {field: None}


def capture_human_feedback(
        client: object,
        channel_id: str,
        thread_ts: str,
        slack_bot_user_id: str,
        latest_ts: str = None,
        state: str = "info",
) -> tuple:
    """
    Captures the last user message in a Slack thread, ignoring bot
    messages and the initial thread message. Only processes new
    messages since the last timestamp (latest_ts). 

    This function filters out messages sent by the bot, the initial
    thread message, and messages that have already been processed.
    It returns the user's message content if there is a new message.

    Args:
        client (SlackClient): The Slack client instance used
            for API calls.
        channel_id (str): The ID of the Slack channel where the
            conversation is taking place.
        thread_ts (str): The timestamp of the initial thread message.
        slack_bot_user_id (str): The user ID of the bot that should
            be ignored in the thread.
        latest_ts (str, optional): The timestamp of the most recent
            processed message (default is None).
        state (str, optional): The state of the process 
            (default is "info", can be "analysts"
            for specific processing).

    Returns:
        tuple: A tuple containing the following:
            - found (bool): A flag indicating whether a new message
              was found.
            - user_message (str): The latest user message if found.
              This is the unprocessed message content.
            - max_analysts (int or None): The number of analysts if
              'state' is "analysts", or 'None' if 'state' is "info".
    """
    try:
        response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts
        )

        for message in reversed(response['messages']):
            message_ts = message['ts']

            if (
                message.get("user")
                and message["user"] != slack_bot_user_id
                and message_ts != thread_ts
                and (latest_ts is None or message_ts > latest_ts)
            ):
                user_message = message.get('text')

                if state == "analysts":
                    max_agents, text = extract_new_info(user_message)
                    return True, text, max_agents

                return True, user_message, None

    except SlackApiError as e:
        log_error(e, f"Error fetching replies.")

    return False, None, None


def wait_for_feedback_periodically(
        client: object,
        channel_id: str,
        thread_ts: str,
        latest_ts: str,
        slack_bot_user_id: str,
        max_wait_time: int = 180,
        check_interval: int = 3,
        state: str = "info",
) -> tuple:
    """
    Periodically checks for the latest user message in a Slack thread
    within a specified maximum wait time. If a new user message is
    found, returns the message text.
    
    Args:
        client (SlackClient): The Slack client instance used
            for API calls.
        channel_id (str): The ID of the Slack channel.
        thread_ts (str): The timestamp of the Slack thread.
        latest_ts (str): The timestamp of the last processed message.
        slack_bot_user_id (str): The user ID of the bot
            (to exclude bot messages).
        max_wait_time (int, optional): Maximum wait time in seconds
            (default 180 seconds).
        check_interval (int, optional): Interval in seconds between
            each feedback check (default 3 seconds).
        state (str, optional): State of the process; can be
            "analysts" or "info" (default is "info").

    Returns:
        tuple: A tuple containing the following:
            - user_message (str): The latest user message if found. 
              This is the unprocessed message content.
            - max_analysts (int or None): The number of analysts if
                'state' is 'analysts', or 'None' if 'state' is 'info'.
            - (False, None): If no message is found or a timeout occurs.
    """
    elapsed_time = 0

    while elapsed_time < max_wait_time:
        found, user_message, max_analysts = capture_human_feedback(
            client,
            channel_id,
            thread_ts,
            slack_bot_user_id,
            latest_ts,
            state
        )
        if found and state == "analysts":
            return user_message, max_analysts
        elif found and state == "info":
            return user_message, None

        time.sleep(check_interval)
        elapsed_time += check_interval

    timeout_message =(":information_source: Timeout, no feedback "
    "received within the maximum wait time.")

    response = send_message_with_retry(
        client,
        channel_id,
        thread_ts,
        timeout_message,
        log_context="Sending timeout message to Slack."
    )
    return False, None


def check_input_complete(state: ResearchGraphState,):
    """
    Check if all fields in the input graph are filled.

    Args:
        state (ResearchGraphState): The current state of the
            input graph.

    Returns:
        str: The next state to transition to.
    """
    if state.get("timeout", False):
        return END

    elif any(value is None for value in state.values()):
        return "extract_info"

    else:
        return END


def exclude_document_blocks(messages: list,) -> tuple:
    """
    Exclude messages within document blocks from the input thread
    and return document names.

    This function filters out messages that are part of a document block
    in the input thread, allowing the system to focus on the user's
    input and ignore document-related content. It also returns the
    names of documents found in the document blocks.

    Args:
        messages (list[dict]): A list of messages in the input thread.

    Returns:
        tuple: A filtered list of messages excluding document blocks
            and a list of document names.
    """
    in_document_block = False
    filtered_messages = []
    document_names = []

    for message in messages:
        content = message['content']

        # If the document start tag is found
        if '<Document Name:' in content:
            in_document_block = True
            # Extract the document name(s) using regular expression
            document_names_in_message = re.findall(
                r'<Document Name:\s*(.*?)>', content
            )
            document_names.extend(document_names_in_message)

        # If the document end tag is found
        elif '<Document End:>' in content:
            in_document_block = False
            continue

        # Only add messages that are not part of a document block
        if not in_document_block:
            filtered_messages.append(message)

    return filtered_messages, document_names
