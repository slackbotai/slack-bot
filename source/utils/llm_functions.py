"""
llm_functions.py

This module provides functionalities for classifying user requests 
into predefined categories, generating image requests, and suggesting 
search terms based on user input using OpenAI's GPT models.

Classes:
- FunctionResponse: Classify the user's input based on their needs
    into predefined categories.
- ImageGenerationRequest: Represent a request for image generation
    with specific parameters.
- ExtractInfo: Extract specific information from the user's input
    for report generation.
- BrowseRequest: Represent a request for browsing based on user input.
- MoreInfo: Classify the user's input based on their needs into
    predefined categories.
- InterpretSummaryBool: A model for interpreting a summary result
    as a boolean value.
- InterpretTimeRange: A model for interpreting a time range with
    specified start and end dates.
- UpdateInfo: A model for extracting new information from the user's
    input.

Functions:
- classify_user_request: Classify the user's input based on their needs 
    into predefined categories.
- generate_image_request: Generate a structured request for image
    generation based on user input.
- suggest_search_term: Generate a structured request for browsing and
    searching based on user input.
- extract_new_info: Extract new information from the user's input.
- interpret_summary_bool: Extract a boolean value from the user's input
    indicating whether the condition is met.
- interpret_timerange: Interpret a time range based on the provided
    dates and user query.
- extract_update_info: Extract new information from the user's input.

Attributes:
    None
"""

import re
import json
import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from threadreader import threadreader
from utils.openai_utils import structured_output
from prompts.structured_output_prompts import (
    classify_user_request_prompt,
    generate_image_request_prompt,
    suggest_search_term_prompt,
    extract_new_info_prompt,
    interpret_summary_bool_prompt,
    time_range_prompt,
    update_info_prompt
)

class FunctionResponse(BaseModel):
    """
    Classify the user's input based on their needs into predefined
    categories.

    Args:
        content (str): The user's input message.
    """
    function: Literal['llm-chat']


class ImageGenerationRequest(BaseModel):
    """
    Represent a request for image generation with specific parameters.

    Args:
        ratio (Literal["1792x1024", "1024x1024", "1024x1792"]):
            The aspect ratio for the image (wide, square, or narrow).
        prompt (str): A description of the image to be generated.
    """
    ratio: Literal["1792x1024", "1024x1024", "1024x1792"]
    prompt: str


class ExtractInfo(BaseModel):
    """
    Extract specific information from the user's input for
    report generation.

    Args:
        topic (Optional[str]): The topic of the report.
        description (Optional[str]): The description of the report.
        report_type (Optional[str]): The type of report.
        files_urls_browse (Optional[Literal["files", "urls", "browse"]]):
            Whether to include files, urls, or browse.
        index (Optional[bool]): Whether to include a table of contents.
        introduction (Optional[bool]): Whether to include an introduction.
        conclusion (Optional[bool]): Whether to include a conclusion.
        source (Optional[bool]): Whether to include sources.
        urls (Optional[list[str]]): Extract URLs if any.
        files (Optional[bool]): Whether there are files attached.
        browse_query (Optional[str]): If the user wants to search the web.
    """
    topic: Optional[str] = None
    description: Optional[str] = None
    report_type: Optional[str] = None
    files_urls_browse: Optional[Literal["files", "urls", "browse"]] = None
    index: Optional[bool] = None
    introduction: Optional[bool] = None
    conclusion: Optional[bool] = None
    source: Optional[bool] = None
    urls: Optional[list[str]] = None
    files: Optional[bool] = None
    browse_query: Optional[str] = None


class BrowseRequest(BaseModel):
    """
    Represent a request for browsing based on user input.

    Args:
        search_term (str): The search term entered by the user.
        urls (list[str]): A list of URLs provided by the user
            for indexing.
    """
    search_term: str
    urls: list[str]


class MoreInfo(BaseModel):
    """
    Classify the user's input based on their needs into
    predefined categories.

    Args:
        max_agents (int): The maximum number of agents to be used.
        new_input (Optional[str]): The user's new input message.
    """
    max_agents: int
    new_input: Optional[str] = None


class InterpretSummaryBool(BaseModel):
    """
    A model for interpreting a summary result as a boolean value.

    Args:
        result (bool): The result of the interpretation,
            indicating whether the condition or query was met.
    """
    result: bool


class InterpretTimeRange(BaseModel):
    """
    A model for interpreting a time range with specified start
    and end dates.

    Args:
        start_date (str): The start date of the interpreted time
            range in ISO 8601 format (e.g., 'YYYY-MM-DD').
        end_date (str): The end date of the interpreted time
            range in ISO 8601 format (e.g., 'YYYY-MM-DD').
    """
    start_date: str
    end_date: str


class UpdateInfo(BaseModel):
    """
    A model for extracting new information from the user's input.

    Args:
        field (Optional[str]): The field to be updated.
        update_text (Optional[str]): The new text to be updated.
    """
    field: Optional[str]= None
    update_text: Optional[str] = None


def classify_user_request(
        client,
        thread_ts,
        channel_id,
        slack_bot_user_id,
        text: str,
        files: bool,
) -> FunctionResponse:
    """
    Classify the user's input based on their needs into predefined categories.

    Args:
        client: The Slack client instance.
        thread_ts: The timestamp of the Slack thread.
        channel_id: The ID of the Slack channel.
        slack_bot_user_id: The user ID of the Slack bot.
        text (str): The user's input message.
        files (bool): Whether the input includes files.

    Returns:
        FunctionResponse: The classified function response.
    """
    slack_channel_id_pattern = r"<#([A-Za-z0-9]+)\|>"
    match = re.search(slack_channel_id_pattern, text)

    if match:
        return "llm-query"

    elif files:
        return "llm-chat"

    system_prompt = classify_user_request_prompt()
    _, formatted_text = threadreader(
        client,
        thread_ts,
        channel_id,
        slack_bot_user_id,
        system_prompt
    )

    response = structured_output(
        formatted_text[-10:],
        FunctionResponse,
    )

    return response.function


def generate_image_request(text: str,) -> tuple[str, str]:
    """
    Generate a structured request for image generation
    based on user input.

    Args:
        text (str): The user's input message related to image
            generation.

    Returns:
        tuple (str, str): A tuple where the first element is the
            image aspect ratio, and the second element is a
            description of the image to be generated.
    """
    system_prompt = generate_image_request_prompt(text)
    response = structured_output(system_prompt, ImageGenerationRequest)
    return response.ratio, response.prompt


def suggest_search_term(text: str,) -> tuple[str, str]:
    """
    Generate a structured request for browsing and searching
    based on user input.

    Args:
        text (str): The user's input message related to
            browsing or search.

    Returns:
        tuple[str, str]: A tuple where the first element is the
            search term classification, and the second element is
            a JSON string with indexed URLs or an empty JSON object.
    """
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    system_prompt = suggest_search_term_prompt(current_date, text)

    response = structured_output(system_prompt, BrowseRequest)

    if response.urls:
        json_urls = json.dumps(
            {str(i): url.strip() for i, url in enumerate(response.urls)})
    else:
        json_urls = json.dumps({})

    return response.search_term, json_urls


def extract_new_info(text: str,) -> tuple[int, Optional[str]]:
    """
    Extract new information from the user's input.

    Args:
        text (str): The user's input message.

    Returns:
        tuple[int, Optional[str]]: A tuple where the first element
            is the number of agents to be used, and the second
            element is the new input message (if any).
    """
    system_prompt = extract_new_info_prompt(text)
    response = structured_output(system_prompt, MoreInfo)

    return response.max_agents, response.new_input


def interpret_summary_bool(text: str,) -> bool:
    """
    Extract a boolean value from the user's input indicating
    whether the condition is met.

    Args:
        text (str): The user's input message.

    Returns:
        bool: A boolean value indicating whether the summary
            condition is met.
    """
    system_prompt = interpret_summary_bool_prompt(text)
    response = structured_output(system_prompt, InterpretSummaryBool)

    return response.result


def interpret_timerange(
        current_date: str,
        start_date: str,
        query: str,
)-> tuple[str, str]:
    """
    Interpret a time range based on the provided dates and user query.

    Args:
        current_date (str): The current date in ISO 8601 format
            (e.g., 'YYYY-MM-DD').
        start_date (str): The start date of the time range in
            ISO 8601 format (e.g., 'YYYY-MM-DD').
        query (str): The user's query related to the time range.

    Returns:
        tuple[str, str]: A tuple containing the interpreted
            time range's start and end dates.
    """
    system_prompt = time_range_prompt(current_date, start_date, query)
    response = structured_output(system_prompt, InterpretTimeRange)

    return response


def extract_update_info(
        fields: dict,
        text: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Extract new information from the user's input.

    Args:
        text (str): The user's input message.

    Returns:
        tuple[int, Optional[str]]: A tuple where the first element
            is the number of agents to be used, and the second
            element is the new input message (if any).
    """
    system_prompt = update_info_prompt(fields, text)
    response = structured_output(system_prompt, UpdateInfo)

    return response.field, response.update_text
