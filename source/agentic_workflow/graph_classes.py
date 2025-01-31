"""
graph_classes.py

This module contains the classes representing the state of the
input graph, research graph, and interview process.

Classes:
- InputGraphState: Represents the state of the input graph.
- ResearchGraphState: Represents the state of a research graph.
- InterviewState: Represents the state of an interview process.
- SearchQuery: Represents a search query for external sources.

Attributes:
    None
"""

import operator
from typing import Annotated, Optional, TypedDict, Union

from pydantic import BaseModel, Field

from langgraph.graph import MessagesState
from agentic_workflow.analyst_builder import Analyst

class InputGraphState(TypedDict):
    """
    Represents the state of the input graph, containing user inputs and
    related configurations.
    
    Attributes:
        u_input (str): The user's input for the graph.
        topic (str): The topic of the report or analysis.
        description (str): The description of the topic or analysis.
        report_type (str): The type of report
            (e.g., analytical, summary).
        files_urls_browse (str): Indicates whether files or browsing
            is required.
        index (bool): Whether a Table of Contents (TOC) is included in
            the report.
        introduction (bool): Whether an introduction is included
            in the report.
        conclusion (bool): Whether a conclusion is included in
            the report.
        source (bool): Whether to include sources in the report.
        urls (Optional[Union[bool, list[str]]]): A list of URLs for
            external references or browsing.
        files (Optional[bool]): Whether files are included or not.
        browse_query (Optional[str]): The search query for browsing
            if applicable.
        timeout (bool): Whether the process should time out.
    """
    u_input: str
    topic: str
    description: str
    report_type: str
    files_urls_browse: str
    index: bool
    introduction: bool
    conclusion: bool
    source: bool
    urls: Optional[Union[bool, list[str]]]
    files: Optional[Union[bool, list[str]]]
    browse_query: Optional[str]
    timeout: bool


class ResearchGraphState(TypedDict):
    """
    Represents the state of a research graph, containing the detailed
    progress, analysts' inputs, and report status.
    
    Attributes:
        max_analysts (int): The maximum number of analysts allowed
            in the process.
        human_analyst_feedback (str): Feedback from the human analyst.
        analysts (list[Analyst]): List of analysts participating
            in the research.
        sections (Annotated[list, operator.add]): Sections of the
            report to be included.
        introduction_str (str): The introduction section of the report.
        index_str (str): Index for the report.
        content (str): Main content of the report.
        conclusion_str (str): Conclusion section of the report.
        draft_report (str): The draft version of the report.
        context (Annotated[list[str], operator.add]): Context or
            background information for the research.
        analysis_feedback (str): Feedback on the analysis.
        final_report (str): The final version of the report.
        u_input (str): The user's input for the research process.
        topic (str): The topic of the research.
        description (str): The description of the research topic.
        report_type (str): The type of report being created.
        files_urls_browse (Annotated[Optional[str], operator.add]):
            Whether files, urls or browsing is involved in the research.
        index (bool): Whether to include a Table of Contents
            in the report.
        introduction (bool): Whether to include an introduction
            in the report.
        conclusion (bool): Whether to include a conclusion
            in the report.
        source (bool): Whether to include sources in the report.
        urls (Annotated[Optional[Union[bool, list[str]]], operator.add]): 
            URLs for references or browsing.
        files (bool): If there are files attached.
        browse_query (Annotated[Optional[str], operator.add]):
            The search query used for browsing external resources.
        timeout (bool): Whether the process should time out.
        response_ts (str): For update of bot messages.
    """
    max_analysts: int
    human_analyst_feedback: str
    analysts: list[Analyst]
    sections: Annotated[list, operator.add]
    introduction_str: str
    index_str: str
    content: str
    conclusion_str: str
    draft_report: str
    context: Annotated[list[str], operator.add]
    analysis_feedback: str
    final_report: str
    u_input: str
    topic: str
    description: str
    report_type: str
    files_urls_browse: Annotated[Optional[str], operator.add]
    index: bool
    introduction: bool
    conclusion: bool
    source: bool
    urls: Annotated[Optional[Union[bool, list[str]]], operator.add]
    files: Annotated[Optional[Union[bool, list[str]]], operator.add]
    browse_query: Annotated[Optional[str], operator.add]
    timeout: bool
    response_ts: str


class InterviewState(MessagesState):
    """
    Represents the state of an interview process, including details
    about the interview, the analyst conducting it, and the context
    of the conversation.
    
    Attributes:
        max_num_turns (int): The maximum number of conversation turns
            allowed in the interview.
        context (Annotated[list[str], operator.add]): A list of source
            documents relevant to the interview.
        analyst (Analyst): The analyst conducting the interview.
        interview (str): The full transcript of the interview.
        sections (list[str]): The final sections to be output after
            the interview.
        search_path (Optional[str]): The search path to be used
            (e.g., 'read', 'web', 'both').
        query (str): The search query string used during the interview.
        urls (list[str]): A list of URLs used or referenced during
            the interview.
        topic (str): The topic of the interview.
        files_urls_browse (str): Indicates if files or browsing is
            involved in the interview.
        browse_query (str): The search query used for browsing
            during the interview.
    """
    max_num_turns: int
    context: Annotated[list[str], operator.add]
    analyst: Analyst
    interview: str
    sections: list[str]
    urls: list[str]
    topic: str
    files_urls_browse: str
    browse_query: str


class SearchQuery(BaseModel):
    """
    Represents a search query used for retrieving information from
    external sources.
    
    Attributes:
        search_query (str): The search query string for
        information retrieval.
    """
    search_query: str = Field(None, description="Search query for retrieval.")
