"""
interview_agents.py

This module contains the functions for the interview process in the
research assistant workflow.

Functions:
- create_analysts: Creates a set of analysts based on the research
    topic and human feedback.
- slack_sender: Sends a message to Slack with detailed information
    about each analyst.
- human_feedback: Facilitates a feedback process with a user on Slack
    to determine if the currently proposed analysts are satisfactory
    or if new ones need to be generated.
- initiate_all_interviews: Initiates parallel interviews for each
    analyst using the Send API.
- generate_question: Generates a question based on the provided state
    and appends it to the message history.
- determine_search_path: Determines the next step in the interview
    process based on the choice of either browsing the web or
    accessing local files.
- search_web: Retrieves documents from a web search based on the state
    and processes them.
- read_files: Retrieve all documents from the thread_storage collection
    in MongoDB based on the provided thread timestamp and channel ID,
    without filtering by search query.
- generate_answer: Node to answer a question based on the provided
    context and analyst persona.
- route_messages: Route between question and answer in an interview.
- save_interview: Save the interview messages to the state as a string.
- write_section: Node to generate a section based on interview context.

Attributes:
    None
"""

import asyncio
import json

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    get_buffer_string,
)
from langchain_openai import ChatOpenAI
from langgraph.constants import Send
from langgraph.graph import END

from envbase import openai_api_key, thread_storage
from event_calls.web_search import web_browser
from utils.web_reader import process_urls_async
from utils.logging_utils import log_error
from utils.slack_utils import send_message_with_retry
from prompts.agent_prompts import (
    agent_creation_prompt,
    answer_instructions_prompt,
    question_prompt,
    search_instructions_prompt,
    section_writer_prompt,
)
from agentic_workflow.analyst_builder import (
    GenerateAnalystsState, Perspectives
)
from agentic_workflow.graph_classes import (
    InterviewState, ResearchGraphState, SearchQuery
)
from agentic_workflow.input_agents import wait_for_feedback_periodically

llm = ChatOpenAI(
    api_key=openai_api_key,
    model='gpt-5-mini',
    temperature=0
)

def create_analysts(state: GenerateAnalystsState,) -> dict:
    """
    Creates a set of analysts based on the research topic and
    human feedback.

    This function uses a language model (LLM) to generate a set of
    analysts who will contribute perspectives on the research topic.
    The analysts' roles and focus areas are dynamically defined based
    on the provided description and feedback.

    Args:
        state (GenerateAnalystsState): The state containing the
            research topic, the maximum number of analysts to generate, 
            and human feedback on the generated analysts.

    Returns:
        dict: A dictionary with the generated analysts in the
            'analysts' field.
    """
    human_analyst_feedback = state.get('human_analyst_feedback', '')
    if state.get("timeout", False):
        return {'analysts': ''
    }
    structured_llm = llm.with_structured_output(Perspectives)
    system_message = agent_creation_prompt(
        state["topic"],
        state["description"],
        human_analyst_feedback,
        state["max_analysts"]
    )
    analysts = structured_llm.invoke([
        SystemMessage(content=str(system_message)),
        HumanMessage(content="Generate the set of analysts")
    ])
    # Store the list of analysts in the state and return the result
    return {'analysts': analysts.analysts}


def slack_sender(
        state: ResearchGraphState,
        client: object,
        event_ts: str,
        channel_id: str,
) -> None:
    """
    Sends a message to Slack with detailed information about
    each analyst.
    
    Args:
        state (ResearchGraphState): The state containing the list of
            analysts to send to Slack.
        client (WebClient): The Slack client instance used to
            interact with Slack API.
        event_ts (str): The timestamp of the event that triggered
            the message.
        channel_id (str): The ID of the Slack channel to send
            the message to.
    
    Returns:
        None
    """
            # Prepare the message content
    message_parts = []
    for analyst in state["analysts"]:
        message_parts.append(
            f"Name: {analyst.name}\n"
            f"Affiliation: {analyst.affiliation}\n"
            f"Role: {analyst.role}\n"
            f"Description: {analyst.description}\n"
            + "-" * 50
        )
    message = "\n\n".join(message_parts)

    respond = send_message_with_retry(
        client,
        channel_id,
        event_ts,
        f"Analysts Created:\n\n{message}",
        log_context="Sending analyst details to Slack"
    )


def human_feedback(
        state: ResearchGraphState,
        client: object,
        channel_id: str,
        thread_ts: str,
        slack_bot_user_id: str,
        say: callable,
) -> dict:
    """
    This function facilitates a feedback process with a user on Slack
    to determine if the currently proposed analysts are satisfactory
    or if new ones need to be generated. It waits for user feedback
    and takes appropriate action based on the feedback.

    Args:
        state (ResearchGraphState): The current state containing the
            list of analysts and the feedback from the user.
        client (object): The Slack client instance for API calls.
        channel_id (str): The ID of the Slack channel.
        thread_ts (str): The timestamp of the thread message.
        slack_bot_user_id (str): The user ID of the bot.
        say (callable): A function to send messages to Slack.

    Returns:
        dict: A dictionary containing the human feedback on
            the analysts or a timeout flag.
    """
    response = say(
        channel=channel_id,
        thread_ts=thread_ts,
        text="Please let me know if these analysts look "
            "alright or if you want to generate new ones."
    )
    latest_ts = response['ts']

    feedback_text, max_analysts = wait_for_feedback_periodically(
        client,
        channel_id,
        thread_ts,
        latest_ts,
        slack_bot_user_id,
        state = "analysts"
    )
    if feedback_text is None:
        say(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Great! We're happy with the current analysts. Moving on."
        )
        response = say(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Searching and gathering information... :mag:"
        )
        return {"human_analyst_feedback": None, "response_ts": response["ts"]}

    elif feedback_text is False:
        return {"timeout": True}

    else:
        say(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Understood! Generating new analysts based on "
                    "your feedback..."
        )
        return {"human_analyst_feedback": feedback_text,
                "max_analysts": max_analysts}


def initiate_all_interviews(state: ResearchGraphState,) -> list:
    """
    This is the "map" step where we run each interview sub-graph
    using Send API.

    This function checks if human analyst feedback is available.
    If so, it returns to the analyst creation step. Otherwise, it
    initiates parallel interviews for each analyst using the Send API.

    Args:
        state (ResearchGraphState): The current state containing
            information about the research graph, including analysts,
            files, and URLs.

    Returns:
        list: A list of Send API calls to conduct interviews for
            each analyst.
    """
    human_analyst_feedback = state.get('human_analyst_feedback')

    if human_analyst_feedback:
        return "create_analysts"
    elif state.get("timeout", False):
        return END

    description = state["description"]
    topic = state["topic"]
    files_urls_browse = state["files_urls_browse"]
    urls = state["urls"]
    browse_query = state["browse_query"]
    return [
        Send(
            "conduct_interview", 
            {
                "files_urls_browse": files_urls_browse,
                "urls": urls,
                "browse_query": browse_query,
                "analyst": analyst,
                "messages": [
                    HumanMessage(
                        content=(
                            f"So you said you were writing an article on the"
                            f"topic: {topic}. Description: {description}?"
                        )
                    )
                ]
            }
        )
        for analyst in state["analysts"]
    ]


def generate_question(state: InterviewState,) -> dict:
    """
    Generates a question based on the provided state and appends it
    to the message history.

    This node generates a question by leveraging an analyst's persona
    and a predefined system message. The generated question is then
    appended to the existing list of messages in the state.

    Args:
        state (InterviewState): The current state of the interview,
            containing the analyst's persona and message history.

    Returns:
        dict: Updated state with the new question appended to
            the messages.
    """
    analyst = state["analyst"]
    messages = state["messages"]

    system_message = question_prompt(goals=analyst.persona)

    question = llm.invoke([
        SystemMessage(content=str(system_message)),
        str(messages)
    ])
    messages.append(question)

    return {"messages": messages}


def determine_search_path(state: InterviewState,) -> str:
    """
    Determines the next step in the interview process based on the
    choice of either browsing the web or accessing local files.

    This function checks the value of the "files_urls_browse" field
    in the state and returns the corresponding next node for processing.
    If the choice involves browsing the web or using urls, it returns
    the path for a web search. If the choice involves local files, it
    returns the path for reading the information locally. If neither
    choice is specified, it defaults to reading information locally.

    Args:
        state (InterviewState): The current state of the interview,
            containing the "files_urls_browse" choice.

    Returns:
        str: The next node to execute, either "search_web" or
            "read_information".
    """
    choice = state.get("files_urls_browse", "")

    if "browse" in choice or "urls" in choice:
        return "search_web"
    elif "files" in choice:
        return "read_information"


def search_web(
        state: InterviewState,
        client,
        channel_id,
        event_ts,
        slack_bot_user_id,
) -> dict:
    """
    Retrieves documents from a web search based on the state and
    processes them.

    This function performs a web search using the provided URLs or
    search query. If URLs are provided, it processes the URLs directly.
    If no URLs are given, it constructs a search query and performs a
    search using a web browser client. The retrieved documents are
    then processed asynchronously.

    Args:
        state (InterviewState): The current state of the interview,
            containing the URLs or search query for retrieving
            documents.
        client: The Slack client used for interacting with Slack.
        channel_id (str): The Slack channel ID where the result will
            be sent.
        event_ts (str): The timestamp of the event that triggered
            the search.
        slack_bot_user_id (str): The bot's user ID for performing
            actions in Slack.

    Returns:
        dict: A dictionary containing the "context", which is a list
            of formatted messages or documents retrieved
            from the search.
    """
    urls = state.get("urls", [])
    messages = state["messages"]

    if urls:
        
        context = state["context"]

        processed_files = set()

        for doc_list in context:
            if isinstance(doc_list, list):
                for doc in doc_list:
                    if isinstance(doc, dict) and doc.get("role") == "user":
                        content = doc.get("content", "")
                        if content.startswith('<Website URL: "'):
                            file_name = content.split('"')[1]
                            processed_files.add(file_name)

        new_urls = [url for url in urls if url not in processed_files]
        if not new_urls:
            return

        formatted_messages = []
        browse_mode = json.dumps(
            {str(i): url.strip() for i, url in enumerate(new_urls)}
        )
        asyncio.run(process_urls_async(
            "",
            formatted_messages,
            browse_mode,
            True
        ))
        return {"context": formatted_messages}

    else:
        structured_llm = llm.with_structured_output(SearchQuery)
        contents = []
        for message in messages:
            if isinstance(message, HumanMessage):
                contents.append(message.content)

            elif isinstance(message, AIMessage):
                contents.append(message.content)

        combined_context = "\n".join(contents)
        search_query = structured_llm.invoke(
            search_instructions_prompt(
                state.get("browse_query", ''), combined_context)
        )
        browse_mode = web_browser(
            client=client,
            channel_id=channel_id,
            event_ts=event_ts,
            slack_bot_user_id=slack_bot_user_id,
            search_term=search_query.search_query,
            max_results=3
        )
        formatted_messages = []
        asyncio.run(process_urls_async(
            search_query,
            formatted_messages,
            browse_mode
        ))
        return {"context": [formatted_messages]}


def read_files(
        state: InterviewState,
        thread_ts: str,
        channel_id: str,
) -> dict:
    """
    Retrieve all documents from the thread_storage collection in MongoDB
    based on the provided thread timestamp and channel ID, without 
    filtering by search query.

    Args:
        state (InterviewState): The current state of the interview.
        thread_ts (str): The timestamp of the thread.
        channel_id (str): The Slack channel ID.

    Returns:
        dict: A dictionary containing the "context" key with a list of 
              formatted document contents or an error message if no 
              documents are found.
    """
    context = state["context"]
    processed_files = set()

    for doc_list in context:
        if isinstance(doc_list, list):
            for doc in doc_list:
                if isinstance(doc, dict) and doc.get("role") == "user":
                    content = doc.get("content", "")
                    if content.startswith('<Document href="'):
                        file_name = content.split('"')[1]
                        processed_files.add(file_name)

    all_docs = []

    try:
        # Query MongoDB for documents matching thread_ts and channel_id
        query = {"thread_id": thread_ts, "channel_id": channel_id}
        documents = thread_storage.find(query)

        for document in documents:
            # Assuming 'url' field stores the file name
            file_name = document.get("url")
            if file_name and file_name not in processed_files:
                # Format the content with a custom document wrapper
                formatted_doc = [
                    {
                        "role": "user",
                        "content": f'<Document href="{file_name}">'
                    },
                    {
                        "role": "user",
                        "content": document.get("text", "")
                    },
                    {
                        "role": "user",
                        "content": "</Document>"
                    }
                ]
                all_docs.append(formatted_doc)

        if not all_docs:
            return

        context.extend(all_docs)
        return {"context": context}

    except Exception as e:
        log_error(e, "Error accessing MongoDB.")
        return


def generate_answer(state: InterviewState,) -> dict:
    """
    Node to answer a question based on the provided context and
    analyst persona.

    Args:
        state (InterviewState): The state of the interview, containing
            the analyst's persona, messages, and context.

    Returns:
        dict: The updated state with the new "messages" list,
                including the answer from the expert.
    """
    analyst = state["analyst"]
    messages = state["messages"]
    context = state["context"]

    combined_context = "\n".join(
        [message["content"] for sublist in context for message in sublist]
    )
    system_message = answer_instructions_prompt(
        goals=analyst.persona,
        context=combined_context
    )
    answer = llm.invoke(
        [SystemMessage(content=str(system_message))] + messages
    )
    answer.name = "expert"
    messages.append(answer)

    return {"messages": messages}


def route_messages(
        state: InterviewState,
        name: str = "expert",
) -> str:
    """
    Route between question and answer in an interview.

    This function determines whether to proceed with asking a question
    or saving the interview.
    It tracks the number of responses from the expert and ensures the
    conversation does not exceed maximum number of turns.
    It also checks if the conversation has ended based on the content of 
    the last question.

    Args:
        state (InterviewState): The current state of the interview,
            including messages and settings.
        name (str): The name of the AI model providing answers.
            Defaults to "expert".

    Returns:
        str: The next action to take, either "save_interview" or
            "ask_question".
    """
    messages = state["messages"]

    max_num_turns = state.get('max_num_turns', 4)

    num_responses = len(
        [m for m in messages if isinstance(m, AIMessage) and m.name == name]
    )
    if num_responses >= max_num_turns:
        return 'save_interview'

    if len(messages) >= 4:

        last_question = messages[-2]
        if "Thank you so much for your help" in last_question.content:
            return 'save_interview'

    return "ask_question"


def save_interview(state: InterviewState,) -> dict:
    """
    Save the interview messages to the state as a string.

    Args:
        state (InterviewState): The state of the interview, which
            includes the messages exchanged during the interview.

    Returns:
        dict: A dictionary containing the saved interview string
            under the "interview" key.
    """
    messages = state["messages"]

    interview = get_buffer_string(messages)

    return {"interview": interview}


def write_section(state: InterviewState,) -> dict:
    """
    Node to generate a section based on interview context.

    This function uses the interview context or the full interview to
    write a section, based on the analyst's focus. It sends a prompt
    to the language model to generate the section and appends it to
    the state for further processing.

    Args:
        state (InterviewState): The current state of the interview,
            including interview data, context, and analyst info.

    Returns:
        dict: The state updated with the generated section.
    """
    interview = state["interview"]
    context = state["context"]
    analyst = state["analyst"]

    system_message = section_writer_prompt(analyst.description, interview)

    section = llm.invoke([
        SystemMessage(content=str(system_message)),
        HumanMessage(
            content=f"Use this source to write your section: {context}"
        )
    ])
    return {"sections": [section.content]}
