"""
structured_output_prompts.py

This module contains structured prompts for various tasks that require
structured output.

These prompts are designed to guide the model in generating structured
output based on the user's input. The prompts include instructions for
extracting information, generating images, suggesting search terms, and
more.

Functions:
- classify_user_request_prompt: Classifies user input into predefined
    categories.
- generate_image_request_prompt: Creates a prompt for generating images.
- suggest_search_term_prompt: Suggests a search term and extracts URLs.
- extract_new_info_prompt: Extracts new information and determines the
    maximum number of agents to use.
- interpret_summary_bool_prompt: Checks if the user is asking for a
    summary of Slack channel information.
- time_range_prompt: Extracts time ranges from natural language queries.
- update_info_prompt: Extracts new information and determines the field
    to be updated.

Attributes:
    None
"""

from datetime import datetime, timedelta


def generate_image_request_prompt(text: str) -> list:
    """
    Creates a prompt for generating images with appropriate
    dimensions and description.

    Args:
        text (str): User input describing the desired image.

    Returns:
        list: A list of system and user messages for image generation.
    """
    return [
        {
            "role": "system",
            "content": (
                """
                You are a helpful AI assistant specialised in
                generating images.
                When generating the prompt, prioritize the last message and
                see if they have a correalation with the previous messages.
                Analyse the user's input to determine if they want the
                image to be 'wide', 'square', or 'narrow'.
                If no ratio is mentioned, default to '1024x1024'
                (square). 
                
                Output a JSON object with two fields:
                1. 'ratio': '1792x1024' (wide), '1024x1024' (square),
                    or '1024x1792' (narrow).
                2. 'prompt': A brief description of the image to
                    generate (e.g., 'Image of a cat').
                """
            )
        },
        {
            "role": "user",
            "content": text
        },
    ]


def suggest_search_term_prompt(current_date: str, text: str) -> list:
    """
    Suggests a search term and extracts URLs from user input.

    Args:
        current_date (str): The current date.
        text (str): User input describing the search query.

    Returns:
        list: A list of system and user messages for search
            term suggestion.
    """
    return [
        {
            "role": "system",
            "content": (
                f"""
                You are an intelligent assistant capable of creating
                accurate and relevant search terms and extracting URLs
                when provided. Today's date is: {current_date}.
                When generating the search term, consider the entire
                conversation, prioritising the last user message. 
                If multiple topics are present, focus on the most
                recent user input.

                Structure your response as follows:
                - Search Term: [Provide the most relevant search term]
                - URLs:
                - [List any provided URLs, or return None if not applicable]
                """
            )
        },
        {
            "role": "user",
            "content": text
        }
    ]


def extract_new_info_prompt(text: str) -> list:
    """
    Extracts new information and determines the maximum number of
    agents to use.

    Args:
        text (str): User input describing any updates or changes.

    Returns:
        list: A list of system and user messages for extracting
        new information.
    """
    return [
        {
            "role": "system",
            "content": (
                """
                You are an AI assistant tasked with extracting new
                information from the user's input if there is any.
                Analyse the user's message and extract any new
                information provided. If the user provides new input,
                return the extracted information along with the maximum
                number of agents to be used for the task.
                
                If there is input like "It's good" or that they don't
                want to change anything, set new_input to None and
                max_agents to its default value of 3.
                
                Please provide the extracted information and the
                maximum number of agents.
                """
            )
        },
        {
            "role": "user",
            "content": text
        },
    ]


def interpret_summary_bool_prompt(text: str) -> list:
    """
    Constructs a prompt optimized for modern LLMs (GPT-4o, etc.) to 
    classify if a query requires Slack internal context.

    Args:
        text (str): User's query.

    Returns:
        list: The formatted messages payload.
    """
    return [
        {
            "role": "developer",
            "content": (
                "You are an Intent Classification Agent for a Slack bot. "
                "Your job is to determine if the user needs information from internal Slack history.\n\n"
                
                "### CLASSIFICATION RULES\n"
                "Return 'True' if the query matches ANY of these criteria:\n"
                "1. Explicitly mentions a Slack channel (starts with '#', e.g., '#general', '#updates').\n"
                "2. Asks for a summary, recap, or catch-up of recent conversations.\n"
                "3. Asks 'what happened' or 'what was said' regarding a specific topic internally.\n\n"
                
                "Return 'False' if the query falls into these categories:\n"
                "1. General Chit-Chat (e.g., 'Hello', 'Who are you?').\n"
                "2. Image Generation (e.g., 'Generate a picture', 'Draw this').\n"
                "3. Web Search / External Info (e.g., 'Google this', 'Summarize this URL...').\n"
                "4. Coding/Math tasks unrelated to team communication.\n\n"
                
                "### PRIORITY OVERRIDE\n"
                "If the input text contains a channel tag (e.g., <#C12345> or #channel-name), "
                "you MUST return 'True', regardless of other content.\n\n"
                
                "### OUTPUT FORMAT\n"
                "Respond ONLY with the boolean string: 'True' or 'False'."
            )
        },
        {
            "role": "user",
            "content": f"{text}"
        }
    ]


def time_range_prompt(
        current_date: str,
        start_date: str,
        query: str
) -> list:
    """
    Extracts time ranges from natural language queries.

    Args:
        current_date (str): The current date.
        start_date (str): The start date of the channel history.
        query (str): User's query.

    Returns:
        list: A list of system and user messages for extracting
            time ranges.
    """
    today = datetime.strptime(current_date, "%Y-%m-%d").date()
    this_week_start = (
        today - timedelta(days=today.weekday())).strftime("%Y-%m-%d"
    )
    last_week_start = (
        today - timedelta(days=today.weekday() + 7)).strftime("%Y-%m-%d"
    )
    last_week_end = (
        today - timedelta(days=today.weekday() + 1)).strftime("%Y-%m-%d"
    )
    last_month_start = (
        today.replace(day=1) - timedelta(days=1)).replace(
            day=1).strftime("%Y-%m-%d"
    )
    last_month_end = (
        today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d"
    )
    current_year = today.year
    last_year = current_year - 1
    # week 47 of last year
    week_47_start = datetime.strptime(f"{last_year}-11-20", "%Y-%m-%d").date()
    week_47_end = datetime.strptime(f"{last_year}-11-26", "%Y-%m-%d").date()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a concise assistant that extracts time ranges "
                "from natural language queries in various languages. "
                "For the given query, return the following and "
                "nothing else:\n"
                "1. start_date: format = 'YYYY-MM-DD'"
                "2. end_date: format = 'YYYY-MM-DD'"
            )
        },
        {
            "role": "system",
            "content": (
                "Use the current date as a point of reference: "
                f"'{current_date}'. If a year is not explicitly "
                "mentioned, assume the user is referring to the most "
                "recent occurrence of the specified day, week, month, "
                "quarter (Q1, Q2, Q3, Q4), or year."
            )
        },
        {
            "role": "system",
            "content": (
                "If the query requests information or summarisation "
                "based on the start of the channel history, "
                "the whole channel, or if no specific "
                "time range can be extracted from the query, "
                f"return 'start_date' as: '{start_date}', as it is the "
                "start of the channel history."
                f"return 'end_date' as: '{current_date}', as it is the "
                "end of the channel history."
            )
        },
        {
            "role": "system",
            "content": "Here are some examples:",
        },
        {
            "role": "user",
            "content": "Recap this week",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{this_week_start}'\nend_date: '{current_date}'",
        },
        {
            "role": "user",
            "content": "Show me the data from last week",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{last_week_start}'\nend_date: '{last_week_end}'",
        },
        {
            "role": "user",
            "content": "Summarise last month",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{last_month_start}'\nend_date: '{last_month_end}'",
        },
        {
            "role": "user",
            "content": "Summarise week 47 of last year",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{week_47_start}'\nend_date: '{week_47_end}'",
        },
        {
            "role": "user",
            "content": "What happened on January 15th, 2024?",
        },
        {
            "role": "assistant",
            "content": "start_date: '2024-01-15'\nend_date: '2024-01-15'",
        },
        {
            "role": "user",
            "content": "Summarise the whole channel",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{start_date}'\nend_date: '{current_date}'",
        },
        {
            "role": "user",
            "content": "Summarise",
        },
        {
            "role": "assistant",
            "content": f"start_date: '{start_date}'\nend_date: '{current_date}'",
        },
        {
            "role": "user",
            "content": (
                f"Extract and return a time range from the query: {query}"
            )
        }
    ]

    return messages


def update_info_prompt(fields: dict, text: str) -> list:
    """
    Extracts new information and determines the maximum number of
    agents to use.

    Args:
        text (str): User input describing any updates or changes.

    Returns:
        list: A list of system and user messages for extracting
            new information.
    """
    return [
        {
            "role": "system",
            "content": (
                f"""
                You are an AI assistant tasked with extracting new
                information from the user's input if there is any.
                Analyse the user's message and extract any new
                information provided. If the user provides new input,
                return the extracted information along with the field
                to be changed.
                
                If there is input like "It's good" or that they don't
                want to change anything, set update_text to None and
                field to None.
                
                Please provide the extracted information and which
                field it handles about.
                Only choose from 1 of these fields: {fields}
                """
            )
        },
        {
            "role": "user",
            "content": text
        },
    ]
