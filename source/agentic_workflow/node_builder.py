"""
node_builder.py

This module contains the language graph builders for the research
assistant workflow.

Functions:
- input_node_builder: Language graph for the input gathering process
    of the research assistant.
- interview_node_builder: Language graph for the interview process
    of the research assistant.
- main_node_builder: Language graph for the main workflow of the
    research assistant.

Attributes:
    None
"""

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agentic_workflow.graph_classes import (
    InputGraphState, InterviewState, ResearchGraphState
)
from agentic_workflow.interview_agents import (
    create_analysts,
    determine_search_path,
    generate_answer,
    generate_question,
    human_feedback,
    initiate_all_interviews,
    read_files,
    route_messages,
    save_interview,
    search_web,
    slack_sender,
    write_section,
)
from agentic_workflow.input_agents import (
    ask_user_for_info_with_ai,
    check_input_complete,
    extract_info,
)
from agentic_workflow.writer_agents import (
    analyse_report,
    draft_report,
    final_report,
    if_timeout,
    write_conclusion,
    write_index,
    write_introduction,
    write_report,
)

def input_node_builder(
        client: object,
        thread_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
        say: callable,
)-> StateGraph:
    """
    Language graph for the input gathering process of the
    research assistant.
    
    This function defines the language graph for the input gathering
    process of the research assistant. It includes the steps to extract
    information from the user's input and ask for missing information
    using AI.
    
    Args:
        client (object): The Slack client instance for API calls.
        thread_ts (str): The timestamp of the initial thread message.
        channel_id (str): The Slack channel ID.
        slack_bot_user_id (str): The user ID of the bot.
        say (callable): A parameter provided by the Slack Bolt
            framework. It is a function that allows the bot to send
            messages to the Slack channel or user.
    
    Returns:
        StateGraph: The compiled state graph for the input
            gathering process.
    """
    input_builder = StateGraph(InputGraphState)

    input_builder.add_node(
        "extract_info",
        partial(
            extract_info,
            client=client,
            thread_ts=thread_ts,
            channel_id=channel_id,
            slack_bot_user_id=slack_bot_user_id,
            ),
        )
    input_builder.add_node(
        "ai_answer",
        partial(
            ask_user_for_info_with_ai,
            client=client,
            thread_ts=thread_ts,
            channel_id=channel_id,
            slack_bot_user_id=slack_bot_user_id,
            say=say,
            ),
        )
    input_builder.add_edge(START, "extract_info")
    input_builder.add_edge("extract_info", "ai_answer")
    input_builder.add_conditional_edges(
        "ai_answer",
        check_input_complete,
        ["extract_info", END],
    )
    return input_builder


def interview_node_builder(
        client: object,
        thread_ts: str,
        event_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
) -> StateGraph:
    """
    Language graph for the interview process of the research assistant.
    
    This function defines the language graph for the interview process
    of the research assistant. It includes the steps to generate
    questions, read information, search the web, generate answers,
    save interviews, and write sections of the report.
    
    Args:
        client (object): The Slack client instance for API calls.
        thread_ts (str): The timestamp of the initial thread message.
        event_ts (str): The timestamp of the event that triggered the
            workflow.
        channel_id (str): The Slack channel ID.
        slack_bot_user_id (str): The user ID of the bot.
        
    Returns:
        StateGraph: The compiled state graph for the interview process.
    """
    interview_builder = StateGraph(InterviewState)

    interview_builder.add_node("ask_question", generate_question)
    interview_builder.add_node(
        "read_information", 
        partial(
            read_files,
            thread_ts=thread_ts,
            channel_id=channel_id
        )
    )
    interview_builder.add_node(
        "search_web",
        partial(
            search_web,
            client=client,
            channel_id=channel_id,
            event_ts=event_ts,
            slack_bot_user_id=slack_bot_user_id
            )
        )
    interview_builder.add_node("answer_question", generate_answer)
    interview_builder.add_node("save_interview", save_interview)
    interview_builder.add_node("write_section", write_section)

    interview_builder.add_edge(START, "ask_question")
    interview_builder.add_conditional_edges(
        "ask_question",
        determine_search_path,
        ["read_information", "search_web"]
    )
    interview_builder.add_edge("read_information", "answer_question")
    interview_builder.add_edge("search_web", "answer_question")
    interview_builder.add_conditional_edges(
        "answer_question",
        route_messages,
        ["ask_question", "save_interview"]
    )
    interview_builder.add_edge("save_interview", "write_section")
    interview_builder.add_edge("write_section", END)

    return interview_builder


def main_node_builder(
        client: object,
        thread_ts: str,
        event_ts: str,
        channel_id: str,
        slack_bot_user_id: str,
        say: callable
) -> StateGraph:
    """
    Language graph for the main workflow of the research assistant.
    
    This function defines the main workflow of the research assistant,
    which includes gathering information, creating analysts, conducting
    interviews, writing the report, and finalising the report.

    Args:
        client(object): The Slack client instance for API calls.
        thread_ts(str): The timestamp of the initial thread message.
        event_ts(str): The timestamp of the event that triggered the
            workflow.
        channel_id(str): The Slack channel ID.
        slack_bot_user_id(str): The user ID of the bot.
        say(callable): A parameter provided by the Slack Bolt framework.
            It is a function that allows the bot to send messages to
            the Slack channel or user.

    Returns:
        StateGraph: The compiled state graph for the research
            assistant workflow.
    """
    input_builder = input_node_builder(
        client,
        thread_ts,
        channel_id,
        slack_bot_user_id,
        say
    )
    interview_builder = interview_node_builder(
        client,
        thread_ts,
        event_ts,
        channel_id,
        slack_bot_user_id
    )
    builder = StateGraph(ResearchGraphState)

    builder.add_node("gather_info", input_builder.compile())
    builder.add_node("create_analysts", create_analysts)
    builder.add_node(
        "send_slack",
        partial(
            slack_sender,
            client=client,
            event_ts=event_ts,
            channel_id=channel_id
        )
    )
    builder.add_node(
        "human_feedback",
        partial(
            human_feedback,
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_bot_user_id=slack_bot_user_id,
            say=say
        )
    )
    builder.add_node("conduct_interview", interview_builder.compile())
    builder.add_node(
        "write_report",
        partial(
            write_report,
            client=client,
            channel_id=channel_id,
        )
    )
    builder.add_node("write_introduction", write_introduction)
    builder.add_node("write_conclusion", write_conclusion)
    builder.add_node("write_index", write_index)
    builder.add_node("draft_report_gen", draft_report)
    builder.add_node(
        "analyse_report",
        partial(
            analyse_report,
            client=client,
            channel_id=channel_id,
        )
    )
    builder.add_node(
        "final_report_gen",
        partial(
            final_report,
            client=client,
            channel_id=channel_id,
        )
    )
    builder.add_edge(START, "gather_info")
    builder.add_conditional_edges(
        "gather_info",
        if_timeout,
        ["create_analysts", END]
    )
    builder.add_edge("create_analysts", "send_slack")
    builder.add_edge("send_slack", "human_feedback")
    builder.add_conditional_edges(
        "human_feedback",
        initiate_all_interviews,
        ["create_analysts",
         "conduct_interview",
         END]
    )
    builder.add_edge("conduct_interview", "write_report")
    builder.add_edge("write_report", "write_introduction")
    builder.add_edge("write_report", "write_conclusion")
    builder.add_edge(
        [
            "write_conclusion",
            "write_report",
            "write_introduction"
        ],
        "write_index"
    )
    builder.add_edge(
        [
            "write_conclusion",
            "write_report",
            "write_introduction",
            "write_index"
        ],
        "draft_report_gen"
    )
    builder.add_edge("draft_report_gen", "analyse_report")
    builder.add_edge("analyse_report", "final_report_gen")
    builder.add_edge("final_report_gen", END)

    memory = MemorySaver()

    return builder.compile(
        checkpointer=memory
    )
