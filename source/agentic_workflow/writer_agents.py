"""
writer_agents.py

This module contains the agent functions for the writer workflow in the
research graph. These agents are responsible for generating the report
content, including the introduction, conclusion, and index, as well as
drafting the report, analysing it, and finalising it for export.

Functions:
- if_timeout: Check if the process has timed out and return the
    appropriate state.
- write_report: Generate the body text of a report based on the
    provided state.
- write_introduction: Generate the introduction section of a report
    based on the provided state.
- write_conclusion: Generate the conclusion section of a report based
    on the provided state.
- write_index: Generate an index for a research graph based on its
    sections and description.
- draft_report: Combine all selected sections of the report into a
    first draft.
- analyse_report: Analyses each section of the draft report against
    source documents and provides feedback for revision.
- final_report: Revises the draft report based on analysis feedback and
    formats it for .docx output.

Attributes:
- openai_api_key (str): The OpenAI API key used for the OpenAI LLM.
- gemini_api_key (str): The Gemini API key used for the Google
    Generative AI LLM.
"""

from langgraph.graph import END
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from utils.logging_utils import log_message
from envbase import openai_api_key, gemini_api_key
from prompts.agent_prompts import (
    generate_toc_prompt,
    report_writer_prompt,
    intro_conclusion_prompt,
    agent_analysis_prompt,
    agent_final_prompt,
)
from agentic_workflow.graph_classes import ResearchGraphState

llm = ChatOpenAI(
    api_key=openai_api_key,
    model='gpt-4o-mini',
    temperature=0
)

g_llm = ChatGoogleGenerativeAI(
    api_key=gemini_api_key,
    model='gemini-1.5-flash',
    temperature=0
)

def if_timeout(state: ResearchGraphState,) -> str:
    """
    Check if the process has timed out and return the appropriate state.
    
    Args:
        state (ResearchGraphState): The current state of the
            research graph.
        
    Returns:
        str: The next state to transition to based on the
            timeout status.
    """
    if state.get("timeout", False):
        return END
    else:
        return "create_analysts"


def write_report(
        state: ResearchGraphState,
        client: object,
        channel_id: str,
) -> dict:
    """
    Generate the body text of a report based on the provided state.

    This function processes the sections from the state, determines
    which sections to include or exclude based on specific keys, and
    uses an LLM to generate a well-formatted report adhering to the
    specified style and formatting guidelines.

    Args:
        state (ResearchGraphState): The state of the research graph
            containing sections, report type, description, and flags
            for inclusion/exclusion.
        client (WebClient): The Slack client instance used to
            interact with Slack API.
        channel_id (str): The Slack channel ID where the thread
            is located.

    Returns:
        dict: A dictionary containing the generated report content
            in the "content" field.
    """
    client.chat_update(
        channel=channel_id,
        ts=state["response_ts"],
        text="Writing the first draft of the report... :pencil:"
    )
    sections = state["sections"]
    report_type = state["report_type"]
    description = state["description"]

    formatted_str_sections = "\n\n".join([f"{section}" for
                                          section in sections]
    )
    source_str = ""
    if state.get("source", False):
        source_str = """
        Must include all the sources you use at the bottom of the text.
        - Use in-text citations with numbered sources (e.g., [1], [2])
            corresponding to the source list.
        - Ensure all sources are cited in APA format
        ```
        ### Sources
        [1] Link or Document name
        [2] Link or Document name
        ```
        """

    system_message = report_writer_prompt(
        report_type,
        description,
        source_str
    )

    user_message = (
        "Please generate the report based on the following "
        f"sections:\n\n{formatted_str_sections}"
    )
    report = llm.invoke([
        SystemMessage(content=str(system_message)),
        HumanMessage(content=user_message)
    ])
    return {"content": report.content}


def write_introduction(state: ResearchGraphState,) -> dict:
    """
    Generate the introduction section of a report based on the provided
    state.

    This function checks if the introduction section is enabled in the
    state. If enabled, it concatenates all sections, creates
    instructions using the 'intro_conclusion_prompt' function, and
    invokes the LLM to generate the introduction.

    Args:
        state (ResearchGraphState): The state of the research graph
            containing sections, description, and flags for
            inclusion/exclusion of the introduction.

    Returns:
        dict: A dictionary containing the generated introduction string
            in the "introduction_str" field. If the introduction is
            disabled, an empty string is returned.
    """
    if state["introduction"]:

        instructions = intro_conclusion_prompt(
            state["description"],
            state["content"],
            section_type="Introduction"
        )
        intro = llm.invoke([
            SystemMessage(content=str(instructions)),
            HumanMessage(content="Write the report introduction")
        ])
        return {"introduction_str": intro.content}

    return {"introduction_str": ""}


def write_conclusion(state: ResearchGraphState,) -> dict:
    """
    Generate the conclusion section of a report based on the provided
    state.

    This function checks if the conclusion section is enabled in the
    state. If enabled, it concatenates all sections, creates
    instructions using the 'intro_conclusion_prompt' function, and
    invokes the LLM to generate the conclusion.

    Args:
        state (ResearchGraphState): The state of the research graph
            containing sections, description, and flags for
            inclusion/exclusion of the conclusion.

    Returns:
        dict: A dictionary containing the generated conclusion string
            in the "conclusion_str" field. If the conclusion is
            disabled, an empty string is returned.
    """
    if state["conclusion"]:

        instructions = intro_conclusion_prompt(
            state["description"],
            state["content"], section_type="Conclusion"
        )
        conclusion = llm.invoke([
            SystemMessage(content=str(instructions)),
            HumanMessage(content="Write the report conclusion")
        ])
        return {"conclusion_str": conclusion.content}

    return {"conclusion_str": ""}


def write_index(state: ResearchGraphState,) -> dict:
    """
    Generate an index for a research graph based on its sections and
    description.

    If the table of contents (TOC) is enabled in the state, this
    function concatenates all the sections, uses the
    'report_write_index_prompt' function to generate instructions,
    and invokes the LLM to create the index.

    Args:
        state (ResearchGraphState): The state of the research graph
            containing sections, description, and TOC flag.

    Returns:
        dict: A dictionary containing the generated index. If TOC is
            disabled, an empty string is returned in the "index" field.
    """
    if state["index"]:
        content = state["content"]

        parts = content.split("## Sources")
        main_content = parts[0].strip()

        sources = []
        for part in parts[1:]:
            sources_section = part.strip()
            sources.append(sources_section)

        index_input = []

        if state["introduction"]:
            index_input.extend([
                "\n\n## Introduction\n",
                state["introduction_str"]
            ])
        index_input.extend([
            "\n\n## Main Insights\n",
            main_content.strip()
        ])
        if state["conclusion"]:
            index_input.extend([
                "\n\n## Conclusion\n",
                state["conclusion_str"]
            ])
        if sources:
            sources_content = "\n\n".join(sources).strip()
            index_input.extend([
                "\n\n## Sources",
                "\n\n",
                sources_content
            ])
        text_report = "\n".join(index_input)

        instructions = generate_toc_prompt(text_report)

        index = llm.invoke([
            SystemMessage(content=str(instructions)),
            HumanMessage(content="Write the report index")
        ])
        return {"index_str": index.content}

    return {"index_str": ""}


def draft_report(state: ResearchGraphState,) -> dict:
    """
    Combine all selected sections of the report into a first draft.

    This function dynamically constructs a draft report based on the
    state, including or excluding sections such as the table of
    contents (TOC), introduction, and conclusion as specified in
    the state.

    Args:
        state (ResearchGraphState): The state of the research graph
            containing content, index, introduction, conclusion,
            and other components.

    Returns:
        dict: A dictionary containing the draft report string in the 
              "draft_report" field.
    """
    content = state["content"]

    if content.startswith("## Insights"):
        content = content.removeprefix("## Insights").strip()

    parts = content.split("## Sources")

    main_content = parts[0].strip()

    sources = []
    for part in parts[1:]:
        sources_section = part.strip()
        sources.append(sources_section)

    draft_sections = [
        "# Draft Report",
        "\n",
    ]
    if state["index"]:
        draft_sections.extend([state["index_str"], "\n"])

    if state["introduction"]:
        draft_sections.extend([
            "\n\n## Introduction\n",
            state["introduction_str"]
        ])
    draft_sections.extend([
        "\n\n## Main Insights\n",
        main_content.strip()
    ])
    if state["conclusion"]:
        draft_sections.extend([
            "\n\n## Conclusion\n",
            state["conclusion_str"]
        ])
    if sources:
        sources_content = "\n\n".join(sources).strip()
        draft_sections.extend([
            "\n\n## Sources",
            "\n\n",
            sources_content
        ])
    combined_draft_report = "\n".join(draft_sections)

    return {"draft_report": combined_draft_report}


def analyse_report(
        state: ResearchGraphState,
        client: object,
        channel_id: str,
) -> dict:
    """
    Analyses each section of the draft report against source documents 
    and provides feedback for revision.

    This function compares the report sections to the source documents, 
    assigns a score to each section, and generates feedback with
    necessary corrections.

    Args:
        state (ResearchGraphState): The current state of the research
            graph.
        client (WebClient): The Slack client instance used to interact
            with Slack API.
        channel_id (str): The Slack channel ID where the thread
            is located.

    Returns:
        dict: Updated state with analysis feedback and section scores.
    """
    client.chat_update(
        channel=channel_id,
        ts=state["response_ts"],
        text=("Analysing the draft and checking for improvements... "
              ":male-detective:")
    )
    draft_report_text = state["draft_report"]
    context = state["context"]

    if not context:
        log_message("No context documents found for analysis.", "warning")
        return {"analysis_feedback": "No context documents available."}

    analysis_prompt = agent_analysis_prompt(draft_report_text, context)

    analysis_feedback = g_llm.invoke(str(analysis_prompt))

    return {"analysis_feedback": analysis_feedback.content}


def final_report(
        state: ResearchGraphState,
        client: object,
        channel_id: str,
) -> dict:
    """
    Revises the draft report based on analysis feedback and formats it 
    for .docx output.

    This function uses the analysis feedback to make necessary changes, 
    ensuring the report is finalized and ready for saving as a
    .docx file.

    Args:
        state (ResearchGraphState): The current state of the
            research graph.
        client (WebClient): The Slack client instance used to
            interact with Slack API.
        channel_id (str): The Slack channel ID where the thread
            is located.

    Returns:
        dict: The finalized report ready for export in .docx format.
    """
    client.chat_update(
        channel=channel_id,
        ts=state["response_ts"],
        text="Writing the final report... :bookmark_tabs:"
    )
    sections = {
        "Index": state["index_str"],
        "Introduction": state["introduction"],
        "Report": True,
        "Conclusion": state["conclusion"],
        "Source": state["source"]
        }

    sections_to_include = [key for key, value in sections.items() if value]
    draft_report_text = state["draft_report"]
    analysis_feedback = state["analysis_feedback"]

    revision_prompt = agent_final_prompt(
        draft_report_text,
        analysis_feedback,
        sections_to_include
    )

    finalised_report = llm.invoke([
        SystemMessage(content=str(revision_prompt))
    ])

    return {"final_report": finalised_report.content}
