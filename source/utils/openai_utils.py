"""
openai_utils.py

This module contains utility functions for generating embeddings
and structured outputs using OpenAI's API.

Functions:
- generate_embedding: Generate an embedding for the query or message
    using OpenAI's embedding API.
- structured_output: Call the OpenAI API to generate a structured
    output from the AI model.
- openai_request_stream_to_slack: Send a request to OpenAI's API to
    generate a response based on the input history.
- openai_request: Send a request to OpenAI's API to generate a response
    based on the input history.
- generate_embedding_batch: Generate embeddings for a batch of texts
    using OpenAIEmbeddings from LangChain.

Attributes:
    aiclient: An instance of the OpenAI API client.
    openai_api_key: The API key for the OpenAI API.
"""

from langchain_openai import OpenAIEmbeddings
from slack_sdk import WebClient

from envbase import aiclient, openai_api_key
from utils.stream_utils import update_chat_stream
from utils.message_utils import remove_reaction

def generate_embedding(text: str,) -> list:
    """
    Generate an embedding for the query or message using OpenAI's
    embedding API (v1.0+).

    Args:
        text (str): The text to generate an embedding for.
    
    Returns:
        list: The embedding for the input text.
    """
    embedding_generator = OpenAIEmbeddings(
        model="text-embedding-ada-002",
        api_key=openai_api_key
    )

    embeddings = embedding_generator.embed_query(text)

    return embeddings


def structured_output(
        messages:list,
        structured_class:object,
        model:str="gpt-5-mini",
) -> object:
    """
    Call the OpenAI API to generate a structured output from
    the AI model.
    
    This function sends a system prompt and user input to the OpenAI API
    to generate a structured output.
    
    Args:
        system_prompt (str): The system prompt for the AI model.
        text (str): The user input text.
        structured_class (object): The structured class object
            for the response.
        model (str): The model identifier for the OpenAI API.
        
    Returns:
        object: The structured_class object with the response
            from the AI model.
    """
    response = aiclient.responses.parse(
        model=model,
        input=messages,
        text_format=structured_class,
    )
    response = response.output_parsed
    return response


def openai_request_stream_to_slack(
        model: str,
        prompt: str,
        channel_id: str,
        thread_ts: str,
        event_ts: str,
        client: WebClient,
        response_id: str = None,
        max_tokens: int = None,
        temperature: float = None,
) -> None:
    """
    Send a request to OpenAI's API to generate a response and stream it to Slack.

    Args:
        model (str): Identifier for the OpenAI model to be used.
        prompt (str): Input or conversation history for the model.
        channel_id (str): Slack channel ID where the response will be posted.
        thread_ts (str): Timestamp of the Slack thread for the response.
        event_ts (str): Timestamp of the Slack event triggering the function.
        client (object): Slack client instance for interacting with Slack API.
        say (callable): Function to send messages to Slack.
        max_tokens (int, optional): Maximum tokens for the model's response.
        temperature (float, optional): Sampling temperature for the model.

    Returns:
        None
    """
    # Initiate a streamed response from the AI model
    repsonse_stream = aiclient.responses.create(
        model=model,
        input=prompt,
        stream=True,
        previous_response_id=response_id,
        max_output_tokens=max_tokens,
        temperature=temperature,
        tool_choice="auto",
        tools=[
            {"type": "web_search"},
            {"type": "image_generation"}
        ],
        truncation="auto",
    )
    # Send an initial message to notify the user of an incoming response
    response = client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text="*_Thinking :loading:_*"
    )

    # Process and update the message stream
    update_chat_stream(
        client,
        channel_id,
        repsonse_stream,
        response,
        aistream=""
    )

    # Remove the hourglass reaction after processing is done
    remove_reaction(
        client,
        channel_id,
        event_ts,
        "hourglass_flowing_sand"
    )


def openai_request(
        model: str,
        prompt: list,
        max_tokens: int = None,
        temperature: float = None,
        stream: bool = False,
        top_p: float = None,
) -> str:
    """
    Send a request to OpenAI's API to generate a response based
    on the input history.

    Args:
        model (str): The model identifier for OpenAI's API.
        prompt (list): The conversation history or input for the model
            in the form of a list of messages.
        max_tokens (int, optional): The maximum number of
            tokens to generate.
        temperature (float, optional): The temperature for the model.
        stream (bool, optional): Whether to stream the response or not.
        top_p (float, optional): The nucleus sampling parameter.

    Returns:
        str or iterator: The response from the AI model. If
            "stream=True", returns the raw generator for streaming;
            otherwise, returns the full response as a string.
    """
    response = aiclient.responses.create(
        model=model,
        top_p=top_p,
        stream=stream,
        input=prompt,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )
    return response.output if not stream else response


def generate_embedding_batch(
        texts,
        model="text-embedding-ada-002",
        batch_size=16,
):
    """
    Generate embeddings for a batch of texts using OpenAIEmbeddings
    from LangChain.

    Args:
        texts (list): List of text strings to embed.
        model (str): The embedding model to use.
        batch_size (int): Number of texts to process per batch.

    Returns:
        list: A list of embeddings corresponding to the input texts.
    """
    embedding_generator = OpenAIEmbeddings(
        model=model,
        api_key=openai_api_key
    )
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = embedding_generator.embed_documents(batch)
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
