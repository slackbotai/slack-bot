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

from prompts.prompts import gemini_pdf_summary
from utils.gemini_utils import gemini_request
from utils.message_utils import post_ephemeral_message_ok
from utils.logging_utils import log_error
from envbase import (
    thread_storage,
    url_storage,
    aiclient,
    slack_web_client,
)

register_heif_opener()

async def datareader(
        response: object,
        file_type: str,
) -> tuple[str, str]:
    """
    Read data from a URL and process it based on the file type.

    This function reads data from a URL, processes it based on the file
    type, and returns the processed text along with the data type.

    Args:
        response (object): The HTTP response object containing the file.
        file_type (str): The type of the file (extension).
    
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
        "excel": ["xls", "xlsx", "xlsm", "xlsb", "odf", "csv"],
    }

    # Determine the data type
    for type_key, extensions in file_type_mapping.items():
        if file_type in extensions:
            data_type = type_key
            break

    text = await process_file_type(
        response, data_type, file_type,
    )

    return data_type, text


async def process_file_type(
        response: object,
        data_type: str,
        file_type: str,
) -> str:
    """
    This function processes the file based on its type asynchronously
    and returns the processed text.

    Args:
        response (object): The HTTP response object containing the file.
        data_type (str): The type of the file.
        file_type (str): The extension of the file.

    Returns:
        str: The processed text from the file.
    
    Raises:
        ValueError: If the file type is not supported.
    """
    tasks = []

    if data_type == "audio":
        tasks.append(handle_audio(response, file_type))
    elif data_type == "text":
        tasks.append(response.text())
    elif data_type == "docx":
        tasks.append(handle_docx(response, file_type))
    elif data_type == "excel":
        tasks.append(handle_excel_and_csv(response, file_type))
    else:
        raise ValueError(f"Unsupported file type: {data_type}")

    result = await asyncio.gather(*tasks)

    # In this case, there should be only one result per task,
    # so return the first result
    return result[0]


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
    

async def handle_image(response: object) -> str:
    """
    Process an image from an HTTP response into a base64 encoded string.

    This function opens the image, standardizes it to JPEG format,
    and encodes it as a base64 string. The image processing is
    run in a separate thread to be async-friendly.

    Args:
        response (object): The HTTP response object containing the image.

    Returns:
        str: The base64 encoded string of the image, or a message
             if no image data is found.
    """
    if not response.content:
        return "No image data found."

    def _convert_to_base64(image_bytes: bytes) -> str:
        """Synchronous helper to perform the image conversion."""
        # Open the image from raw bytes
        img = Image.open(BytesIO(image_bytes))

        # Convert the image to RGB to ensure compatibility
        img = img.convert("RGB")

        # Save the image to a BytesIO object to avoid filesystem I/O
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format="JPEG")
        img_byte_arr.seek(0)

        # Encode the bytes as a base64 string
        return base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

    # Run the synchronous conversion function in a separate thread
    base64_image = await asyncio.to_thread(_convert_to_base64, response.content)
    return base64_image


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


async def handle_excel_and_csv(
        response: object,
        file_type: str,
) -> str:
    """
    Process tabular data files (Excel, CSV) to extract text.

    Args:
        response (object): The HTTP response object containing
            the file.
        file_type (str): The type of the file (extension).

    Returns:
        str: The extracted text from the file as a string.
    """
    with tempfile.NamedTemporaryFile(
        suffix=f".{file_type}",
        delete=False) as temp_file:
        temp_file.write(response.content)
        temp_file_path = temp_file.name

    # Use the correct pandas reader based on the file extension
    if file_type == 'csv':
        df = pd.read_csv(temp_file_path)
    else:
        df = pd.read_excel(temp_file_path)
    
    return df.to_string()


def count_tokens(
        text: str,
        model: str = "gpt-4.1",
) -> int:
    """
    Count the number of tokens in the given text for
    the specified model.

    Args:
        text (str): The text to tokenise.
        model (str): The model name to use for tokenisation
            (default: gpt-4.1).

    Returns:
        int: The number of tokens in the text.
    """
    # Select encoding based on model
    encoding = encoding_for_model(model)
    return len(encoding.encode(text))
