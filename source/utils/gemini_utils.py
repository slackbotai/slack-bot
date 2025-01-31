"""
gemini_utils.py

This module contains utility functions for generating content using
the Gemini generative model.

Functions:
- gemini_request: Generate content using the Gemini generative model.

Attributes:
    gemclient: An instance of the GenerativeModel class
        from the Gemini API.
"""

from envbase import gemclient

def gemini_request(
        model: str,
        text: str,
        prompt: list,
        temperature: float = 1.4,
        stream: bool = False,
) -> str:
    """
    Generates content using the Gemini generative model.

    This function calls the Gemini API to generate text based on the
    given prompt and a specified temperature for controlling the
    creativity of the response.

    Args:
        model (str): The model name supported by GenerativeModel.
        prompt (str): The input text prompt to guide the content
            generation.
        temperature (float): The temperature setting for generation.
            Higher values produce more creative and diverse outputs,
            while lower values yield more deterministic responses.

    Returns:
        str: The generated text response from the Gemini model.
    """
    model = gemclient.GenerativeModel(
        model, system_instruction=str(prompt)
    )
    # Set the temperature for the content generation
    generation_config = {"temperature": temperature}
    # Call the Gemini API to generate content
    response = model.generate_content(
        text,
        generation_config=generation_config, 
        stream=stream
    )
    # Return the generated text response
    return response
