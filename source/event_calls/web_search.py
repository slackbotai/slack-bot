"""
web_search.py

This module contains functions that allow the chatbot to perform web
searches using the Serper API. The chatbot can browse the web based on
user input and generate responses based on the search results.

Functions:
- perform_web_search: Perform web search and post results to Slack.
- web_browser: Browse the web and generate a response based on search
    results.

Attributes:
- serper_api_key (str): The API key used to access the Serper API.
"""

import json
import datetime

import requests

from envbase import serper_api_key
from threadreader import threadreader
from utils.llm_functions import suggest_search_term
from prompts.prompts import summarisation_llm_text_prompts
from utils.openai_utils import openai_request_stream_to_slack
from utils.logging_utils import log_message

def perform_web_search(
        client: object,
        channel_id: str,
        event_ts: str,
        search_term: str,
        max_results: int,
) -> None:
    """
    Perform web search and post results to Slack.

    This function performs a web search using the Serper API and posts
    the search results to the Slack channel. The search results are
    limited to the top 10 organic search results. The search term is
    displayed in the Slack channel before the search results are posted.

    Args:
        client (object): The Slack WebClient object used to interact
            with the Slack Web API. This client allows the bot to send
            messages, delete messages, retrieve information about
            channels and users, and perform other operations
            through Slack's Web API.
        channel_id (str): The ID of the Slack channel where the search
            results will be posted.
        event_ts (str): The timestamp of the event that triggered the
            search.
        search_term (str): The search term to be used for the web
            search.

    Returns:
        None
    """
    log_message("Web search activated", "info")

    if not search_term:
        raise Exception("Error: No search term provided")

    if max_results == 10:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=event_ts,
            text=f"Searching for: '{search_term}'"
        )

    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": search_term})
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json"
    }

    response = requests.post(
        url,
        headers=headers,
        data=payload,
        timeout=10
    )
    response.raise_for_status()

    search_results = json.loads(response.text)
    organic_links = [item["link"] for item in search_results["organic"]]
    organic_links = organic_links[:max_results]
    browse_mode = json.dumps({str(i): organic_links[i] for i in
                              range(len(organic_links))})
    return browse_mode


def web_browser(
        client: object,
        channel_id: str,
        event_ts: str,
        slack_bot_user_id: str,
        say: callable = None,
        thread_ts: str = None,
        browse_mode = False,
        search_term: str = None,
        max_results: int = 10,
) -> None:
    """
    With a search term, browse the web and generate a response.
    
    The function uses the Serper API to perform a web search based
    on the user's input. It then generates a response based on the
    search results and posts the response to the Slack channel.
    
    Args:
        client (object): The Slack WebClient object used to interact
            with the Slack Web API. 
        channel_id (str): The ID of the Slack channel where the response
            will be posted.
        thread_ts (str): The timestamp of the thread where the browsing
            was requested.
        event_ts (str): The timestamp of the event that triggered the
            browsing.
        slack_bot_user_id (str): The user ID of the bot.
        say (callable): A parameter provided by the Slack Bolt
            framework. It is a function that allows the bot to send
            messages to the Slack channel or user.
        browse_mode (bool): A boolean flag indicating whether the
            chatbot is in browse mode.
            
        Returns:
            None
    """
    if not search_term:
        _, input_history = threadreader(
            client,
            thread_ts,
            channel_id,
            slack_bot_user_id,
            function_state="preprocess"
        )

        message_string = '\n'.join([message['content'] for 
                                    message in input_history])
        search_term, browse_mode = suggest_search_term(message_string)


    if search_term and (browse_mode == "{}" or browse_mode is False):
        browse_mode = perform_web_search(
            client,
            channel_id,
            event_ts,
            search_term,
            max_results
        )

    return browse_mode
