"""
datareader.py

This module contains functions to read data from a URL and process it
based on the file type. It supports various file types such as images,
audio, text, DOCX, PDF, and Excel files. The data is processed using
the OpenAI API for image analysis and audio transcription, and the
PDFMiner library for PDF text extraction.

Functions:
- datareader: Read data from a URL and process it based on the
    file type.
- process_file_type: Process the file based on its type.
- url_to_filename: Convert a URL into a safe filename.
- cache_db: Load or save data to MongoDB based on the given mode.
- handle_image: Process image data using the OpenAI API for image
    analysis.
- convert_image_to_base64: Convert image data into a base64 encoded
    string.
- handle_audio: Process audio data using the OpenAI Whisper API for
    transcription.
- handle_docx: Process DOCX files to extract text.
- handle_pdf: Process PDF files to extract text.
- handle_excel: Process Excel files to extract text.
- count_tokens: Count the number of tokens in the given text for the
    specified model.

Attributes:
    slack_bot_user_id (str): The user ID of the Slack bot.
    thread_storage (Collection): The MongoDB collection for storing
        thread information.
    url_storage (Collection): The MongoDB collection for storing URL
        information.
    aiclient (OpenAI): The OpenAI client instance.
    slack_web_client (WebClient): The Slack WebClient instance.
"""

import re
import base64
import asyncio
import tempfile
from io import BytesIO

import docx
import requests
import pandas as pd # pylint: disable=import-error
from PIL import Image # pylint: disable=import-error
from tiktoken import encoding_for_model
from pdfminer.high_level import extract_text # pylint: disable=import-error
from pillow_heif import register_heif_opener # pylint: disable=import-error

from prompts.prompts import image_analyse_prompt, gemini_pdf_summary
from utils.gemini_utils import gemini_request
from utils.openai_utils import openai_request
from utils.message_utils import post_ephemeral_message_ok
from utils.logging_utils import log_error
from envbase import (
    slack_bot_user_id,
    thread_storage,
    url_storage,
    aiclient,
    slack_web_client,
)

register_heif_opener()

async def datareader(
        url: str,
        urlheaders: dict,
        user_input: str,
        thread_id: str,
        channel_id: str,
        user_id: str,
        file_type: str,
        cache: bool,
        instructions: str,
) -> tuple[str, str]:
    """
    Read data from a URL and process it based on the file type.

    This function reads data from a URL, processes it based on the file
    type, and returns the processed text along with the data type.

    Args:
        url (str): The URL of the file to be processed.
        urlheaders (dict): The headers to be used for the URL request.
        user_input (str): The user input message.
        thread_id (str): The identifier for the thread handling the request.
        channel_id (str): The identifier for the channel.
        user_id (str): The identifier for the user.
        file_type (str): The type of the file (extension).
        cache (bool): Whether to cache the processed text.
        instructions (str): Instructions for processing the file.
    
    Returns:
        tuple[str, str]: A tuple containing the data type and the
            processed text.
    """
    # Default data type if none is matched
    data_type = ""
    text = ""

    # Define file type mapping
    file_type_mapping = {
        "image": ["jpg", "jpeg", "png", "gif",
                  "bmp", "tiff", "tif", "webp", "heif"],
        "audio": ["m4a", "mp3", "wav"],
        "text": ["c", "cpp", "java", "py", "txt", "html", "css", "js",
                 "json", "xml", "yaml", "yml", "sh", "bat", "quip"],
        "docx": ["docx"],
        "pdf": ["pdf"],
        "excel": ["xls", "xlsx", "xlsm", "xlsb", "odf"],
    }

    # Determine the data type
    for type_key, extensions in file_type_mapping.items():
        if file_type in extensions:
            data_type = type_key
            break

    # Cache handling logic
    if cache:
        text = cache_db(url, thread_id, channel_id, mode="load")
        if text:
            return data_type, text

    # Asynchronous request handling
    response = await asyncio.to_thread(
        requests.get, url, headers=urlheaders, timeout=10
    )
    text = await process_file_type(
        response, user_input, data_type, file_type,
        url, instructions, channel_id, user_id, thread_id
    )
    # If cache is enabled, save the processed text
    if cache:
        cache_db(url, thread_id, channel_id, text, "save")

    return data_type, text


async def process_file_type(
        response: object,
        user_input: str,
        data_type: str,
        file_type: str,
        url: str,
        instructions: str,
        channel_id: str,
        user_id: str,
        thread_ts: str,
) -> str:
    """
    This function processes the file based on its type asynchronously
    and returns the processed text.

    Args:
        response (object): The HTTP response object containing the file.
        user_input (str): The user input message.
        data_type (str): The type of the file.
        file_type (str): The extension of the file.
        url (str): The URL of the file.
        instructions (str): Instructions for processing the file.
        channel_id (str): The identifier for the channel.
        user_id (str): The identifier for the user.
        thread_ts (str): The timestamp of the thread.

    Returns:
        str: The processed text from the file.
    
    Raises:
        ValueError: If the file type is not supported.
    """
    tasks = []

    if data_type == "image":
        tasks.append(handle_image(response, instructions))
    elif data_type == "audio":
        tasks.append(handle_audio(response, file_type))
    elif data_type == "text":
        tasks.append(response.text())
    elif data_type == "docx":
        tasks.append(handle_docx(response, file_type))
    elif data_type == "pdf":
        tasks.append(handle_pdf(
            response, user_input, file_type,
            channel_id, user_id, thread_ts))
    elif data_type == "excel":
        tasks.append(handle_excel(response, file_type))
    else:
        raise ValueError(f"Unsupported file type: {data_type}")

    result = await asyncio.gather(*tasks)

    # In this case, there should be only one result per task,
    # so return the first result
    return result[0]


def url_to_filename(url: str,) -> str:
    """
    Convert a URL into a safe filename by removing special characters.

    Args:
        url (str): The URL to be converted into a filename.

    Returns:
        str: The sanitized filename based on the URL.

    Raises:
        ValueError: If the URL is empty or invalid.
    """
    # Remove the protocol (http or https) from the URL
    url = re.sub(r"https?://", "", url)

    # Replace slashes / with underscores _ to make the filename valid
    url = url.replace("/", "_")

    # Remove any characters that are not alphanumeric, dashes, or underscores
    url = re.sub(r"[^a-zA-Z0-9-_]", "", url)

    # Append the '.md' extension to the sanitized filename
    url += ".md"

    return url


def cache_db(
        url: str = None,
        thread_id: str = None,
        channel_id: str = None,
        text: str = None,
        mode: str = "save",
        url_bool: bool = False,
) -> str:
    """
    Function to either load or save data to MongoDB based
    on the given mode.

    This function handles the caching of data by either loading
    the content from MongoDB or saving the content to MongoDB.
    The collection is determined by the url_storage flag.

    Args:
        url (str): The URL of the data to be cached.
        thread_id (str): The identifier for the thread handling the
            request, used as part of the unique identifier.
        channel_id (str): The identifier for the channel.
        text (str): The text content to be saved. Defaults to None.
        mode (str): The mode of operation, either 'load' or 'save'
            ('save' by default).
        url_storage (bool): If True, use the url_storage collection.
            Defaults to False, which uses the thread_storage collection.

    Returns:
        str: The text loaded from the database if in 'load' mode,
            otherwise None.

    Raises:
        ValueError: If an invalid mode is specified.
        Exception: If an error occurs while accessing MongoDB.
    """
    try:
        if url_bool:
            # Use the url_storage collection
            collection = url_storage
            query = {"url": url}
        else:
            # Use the thread_storage collection
            collection = thread_storage
            query = {"thread_id": thread_id,
                     "channel_id": channel_id,
                     "url": url,
            }
        if mode == "save" and text is not None:
            # Save the text to the specified collection
            data = {**query, "text": text}
            collection.update_one(query, {"$set": data}, upsert=True)
            return

        elif mode == "load":
            # Load the text from the specified collection
            document = collection.find_one(query)
            if document:
                return document.get("text")
            else:
                return None

        else:
            raise ValueError("Invalid mode specified. Use 'load' or 'save'.")

    except Exception as e:
        log_error(e, "Error accessing MongoDB.")
        return None


async def handle_image(
        response: object,
        instructions: str,
) -> str:
    """
    Process image data using the OpenAI API for image analysis.

    Args:
        response (object): The HTTP response object containing
            the image.
        instructions (str): Instructions for processing the image.

    Returns:
        str: The analysis text for the image.
    """
    # Check if the response content is empty
    if not response.content:
        return "No image data found."

    # Convert image to base64 asynchronously
    base64_image = await asyncio.to_thread(
        convert_image_to_base64, response.content)

    # Strip "<@{slack_bot_user_id}> " from the instructions
    instructions = instructions.replace(f"<@{slack_bot_user_id}> ", "")

    # Call the OpenAI API to analyse the image
    prompt = image_analyse_prompt(instructions, base64_image)
    api_response = await asyncio.to_thread(openai_request,
                                            model="gpt-4o",
                                            prompt=prompt,
                                            max_tokens=4000)

    # Extract the analysis results from the API response
    text = "%%% ANALYSIS RESULTS %%%\n\n"
    text += api_response.choices[0].message.content
    text += "\n\n%%% END OF ANALYSIS RESULTS %%%"

    return text


def convert_image_to_base64(image_content: bytes,) -> str:
    """
    Helper function to convert image data into a base64 encoded string.
    This function is run in a separate thread to make it async-friendly.

    Args:
        image_content (bytes): The raw image content.

    Returns:
        str: The base64 encoded string representing the image.
    """
    # Open the image from raw bytes
    img = Image.open(BytesIO(image_content))

    # Convert the image to RGB if it is not in that mode
    img = img.convert("RGB")

    # Save the image to a BytesIO object to avoid filesystem I/O
    img_byte_arr = BytesIO()
    # Save in JPEG format to standardise
    img.save(img_byte_arr, format="JPEG")
    # Reset the pointer to the start of the BytesIO buffer
    img_byte_arr.seek(0)

    # Convert the image to base64
    return base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")


async def handle_audio(
        response: object,
        file_type: str,
) -> str:
    """
    Process audio data using the OpenAI Whisper API for transcription.

    Args:
        response (object): The HTTP response object containing
            the audio.
        file_type (str): The type of the file (extension).

    Returns:
        str: The transcription text for the audio.
    """
    # Write the bytes to a temporary file
    with tempfile.NamedTemporaryFile(suffix=f".{file_type}",
                                     delete=False) as temp_audio:
        temp_audio.write(response.content)
        temp_audio_path = temp_audio.name

    # Transcribe the audio file
    audio_file = open(temp_audio_path, "rb")
    transcript = aiclient.audio.transcriptions.create(
                                model="whisper-1", file=audio_file)

    text = "*** THIS IS A TEXT TRANSCRIPTION OF THE AUDIO FILE ***\n\n"
    text += transcript.text
    text += "\n\n*** END OF TRANSCRIPTION. ***"

    return text


async def handle_docx(
        response: object,
        file_type: str,
) -> str:
    """
    Process DOCX files to extract text.

    Args:
        response (object): The HTTP response object containing
            the DOCX file.
        file_type (str): The type of the file (extension).

    Returns:
        str: The extracted text from the DOCX file.
    """
    file_bytes = BytesIO(response.content)

    with tempfile.NamedTemporaryFile(suffix=f".{file_type}",
                                     delete=False) as temp_docx:
        temp_docx.write(file_bytes.getbuffer())
        temp_docx_path = temp_docx.name

    doc = docx.Document(temp_docx_path)
    return "\n\n".join([p.text for p in doc.paragraphs])


async def handle_pdf(
        response: object,
        user_input: str,
        file_type: str,
        channel_id: str,
        user_id: str,
        thread_ts: str,
) -> str:
    """
    Process PDF files to extract text.

    Args:
        response (object): The HTTP response object containing
            the PDF file.
        file_type (str): The type of the file (extension).

    Returns:
        str: The extracted text from the PDF file.
    """
    file_bytes = BytesIO(response.content)

    with tempfile.NamedTemporaryFile(suffix=f".{file_type}",
                                     delete=False) as temp_pdf:
        temp_pdf.write(file_bytes.getbuffer())
        temp_pdf_path = temp_pdf.name
    text = extract_text(temp_pdf_path)
    # Clean the text
    # Replace newlines with spaces
    text = text.replace("\n", " ")
    # Replace tabs with spaces
    text = text.replace("\t", " ")
    # Remove leading and trailing whitespace
    text = text.strip()
    # multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    # special characters and punctuation
    text = re.sub(r'[^\w\s]', '', text)
    token_count = count_tokens(text)
    if token_count > 50000:
        post_ephemeral_message_ok(
            slack_web_client, channel_id,
            user_id, thread_ts,
            (":information_source: The PDF is too large to process "
             "fully. The summary will prioritise the message "
             "you provided."),
        )
        prompt = gemini_pdf_summary(user_input)

        response = gemini_request(
            model="gemini-1.5-flash",
            text=text,
            prompt=prompt,
            temperature=0.1,
        )
        return response.text
    return text


async def handle_excel(
        response: object,
        file_type: str,
) -> str:
    """
    Process Excel files to extract text.

    Args:
        response (object): The HTTP response object containing
            the Excel file.
        file_type (str): The type of the file (extension).

    Returns:
        str: The extracted text from the Excel file.
    """
    with tempfile.NamedTemporaryFile(
        suffix=f".{file_type}",
        delete=False) as temp_excel:
        temp_excel.write(response.content)
        temp_excel_path = temp_excel.name

    excel = pd.read_excel(temp_excel_path)
    return excel.to_string()


def count_tokens(text: str,
                 model: str = "gpt-4o",
) -> int:
    """
    Count the number of tokens in the given text for
    the specified model.

    Args:
        text (str): The text to tokenise.
        model (str): The model name to use for tokenisation
            (default: gpt-4o-mini).

    Returns:
        int: The number of tokens in the text.
    """
    # Select encoding based on model
    encoding = encoding_for_model(model)
    return len(encoding.encode(text))
