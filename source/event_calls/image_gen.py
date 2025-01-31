"""
image_gen.py

This module contains functions that allow the chatbot to generate images
using the DALL-E model. The chatbot can process image generation
requests based on user input and generate images using the DALL-E model.

Functions:
- handle_image_generation: Handle image generation requests with DALL-E.
- handle_image_error: Handle errors in the image generation process.

Attributes:
- aiclient (object): The OpenAI API client used to interact with the
    OpenAI API. This client allows the bot to send requests to the API
    and receive responses from the API.
- slack_bot_user_id (str): The user ID of the Slack bot.
"""

import tempfile
import requests

from PIL import Image

from threadreader import threadreader
from envbase import aiclient, slack_bot_user_id
from utils.llm_functions import generate_image_request
from utils.message_utils import remove_reaction
from utils.logging_utils import log_message

def handle_image_generation(
        client: object,
        say: callable,
        thread_ts: str,
        event_ts:str,
        channel_id: str,
) -> None:
    """
    Handle image generation requests with DALL-E.

    This function processes image generation requests using DALL-E based
    on the user's prompt. It generates an image using the DALL-E model
    and posts the image to the Slack channel along with the revised
    prompt.

    Args:
        client (object): The Slack WebClient object used to interact
            with the Slack Web API. This client allows the bot to send
            messages, delete messages, retrieve information about
            channels and users, and perform other operations
            through Slack's Web API.
        say (callable): A parameter provided by the Slack Bolt
            framework. It is a function that allows the bot to send
            messages to the Slack channel or user. It is used to
            respond to events or commands.
        event_ts (str): The timestamp of the event that triggered the
            image generation.
        user_id (str): The user ID of the user who triggered the image
            generation.
        thread_ts (str): The timestamp of the thread where the image
            generation was requested.
        channel_id (str): The ID of the Slack channel where the image
            will be posted.
        input_history (list): The list of messages in the thread history
            leading up to the image generation request.
        completion (object): The completion object from the AI client
            containing the response from the AI model.

    Returns:
        None

    """
    _,input_history = threadreader(
        client,
        thread_ts,
        channel_id,
        slack_bot_user_id,
        function_state="preprocess"
    )
    user_contents = [item['content'] for item in
                     input_history if item['role'] == 'user']
    combined_user_content = "\n".join(user_contents)
    ratio, prompt = generate_image_request(combined_user_content)
    log_message("Generating image with DALL-E...", "info")

    response = aiclient.images.generate(
        model="dall-e-3", prompt=str(prompt), n=1,
        size=ratio
    )
    # Fetch the image URL and process the image
    fileresponse = requests.get(
        response.data[0].url, stream=True, timeout=10
    )
    # Process the image and upload it to Slack
    if fileresponse.status_code == 200:
        with tempfile.NamedTemporaryFile(
            suffix=".png", delete=False
        ) as temp_image:
            temp_image.write(fileresponse.content)
            img = Image.open(temp_image.name).convert("RGB")
            img.save(temp_image.name, "JPEG")

            client.files_upload_v2(
                channel=channel_id,
                file=temp_image.name,
                thread_ts=event_ts,
            )
        remove_reaction(
            client=client, channel_id=channel_id, timestamp=event_ts,
            reaction_name="hourglass_flowing_sand"
        )
        say(
            channel=channel_id, thread_ts=event_ts,
            text=f"DALLE PROMPT: {response.data[0].revised_prompt}"
        )
        log_message("Image generated successfully.", "info")
    else:
        raise Exception("Error fetching image.", fileresponse)
