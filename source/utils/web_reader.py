"""
web_reader.py

This module contains functions for fetching and processing content
from URLs, including extracting text from PDFs and sanitising HTML
content. The module also includes functions for generating prompts,
running AI completions, and formatting messages based on
the completions.

Functions:
- clean_pdf_content: Cleans up extracted PDF text by removing unwanted
    patterns and excess whitespace.
- fetch_content: Fetches content from a URL using Playwright and returns
    the processed output.
- process_url_async: Asynchronously processes a single URL by fetching
    content, generating a prompt, obtaining an AI completion, and
    formatting messages.
- process_urls_async: Asynchronously extracts and processes URLs from
    message text, using either a browse mode JSON input or direct
    extraction from the message.

Attributes:
- slack_team_domain (str): The domain name of the Slack workspace.
"""

import re
import json
import asyncio
import tempfile
import datetime

import pypandoc # pylint: disable=import-error
import requests
import pdfplumber # pylint: disable=import-error
import playwright._impl._errors
from html_sanitizer import Sanitizer # pylint: disable=import-error
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright

from datareader import cache_db
from envbase import slack_team_domain
from prompts.prompts import url_prompt_gemini
from utils.gemini_utils import gemini_request
from utils.logging_utils import log_error

def clean_pdf_content(text: str,) -> str:
    """
    Cleans up extracted PDF text by removing unwanted
    patterns and excess whitespace.

    This function processes raw text extracted from PDFs or other
    sources, performing the following operations:
        - Removes extra newlines to create a cleaner text structure.
        - Strips Markdown-style links, replacing them with the
            linked text only.

    Args:
        text (str): The raw text content to be cleaned.

    Returns:
        str: The cleaned text with reduced whitespace and
            no markdown links.
    """
    text = re.sub(r"\s*\n\s*\n\s*", "\n", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    return text


async def fetch_content(
        url: str,
        timeout: int = 5000,
) -> str:
    """
    Fetches content from a URL using Playwright and returns
    the processed output.

    Depending on the file type (HTML or PDF), the function either
    extracts text from a PDF or sanitises the HTML content and converts
    it to markdown format.

    Args:
        url (str): The URL of the webpage or PDF to fetch.
        timeout (int): The timeout in milliseconds for navigation
            and actions within Playwright.

    Returns:
        str: The processed output, either extracted text from
            the PDF or sanitized Markdown content.
    
    Raises:
        TargetClosedError: An exception is raised if the target is
            closed during the content fetching process.
        Exception: An exception is raised if an error occurs during
            the content fetching process.
    """
    async with async_playwright() as p:
        sanitizer = Sanitizer()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
        try:
            if ".pdf" in url:
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".pdf"
                ) as temp_pdf:
                    response = requests.get(
                        url,
                        stream=True,
                        timeout=30
                    )
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_pdf.write(chunk)
                    temp_pdf_path = temp_pdf.name

                output = ""
                with pdfplumber.open(temp_pdf_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            output += page_text + "\n"

                cleaned_output = clean_pdf_content(output)
                return cleaned_output

            browser = await p.chromium.launch()
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent=ua
            )
            page = await context.new_page()
            page.set_default_navigation_timeout(timeout)
            page.set_default_timeout(timeout)

            async def abort_route(route):
                try:
                    await route.abort()
                except playwright._impl._errors.TargetClosedError:
                    pass

            await page.route(
                "**/*.{png,jpg,jpeg,gif,css}",
                lambda route: asyncio.create_task(abort_route(route))
            )

            await page.goto(
                url, timeout=timeout, wait_until='domcontentloaded'
            )
            content = await page.content()

            soup = BeautifulSoup(content, "html.parser")
            for tag in soup(["script", "style", "noscript",
                            "header", "footer", "aside"]):
                tag.decompose()

            for cookie_banner in soup.find_all(
                class_=re.compile(r'cookie|consent|banner'),
                id=re.compile(r'cookie|consent|banner')
            ):
                cookie_banner.decompose()

            for comment in soup.find_all(
                string=lambda text:
                isinstance(text, Comment)
            ):
                comment.extract()

            for a in soup.find_all("a"):
                a.replace_with(a.get_text())

            cleaned_html = str(soup)
            sanitized_html = sanitizer.sanitize(cleaned_html)
            output = pypandoc.convert_text(
                sanitized_html,
                to="gfm-raw_html",
                format="html",
                extra_args=["--wrap=none"]
            )

            output = re.sub(r"\s*\n\s*\n\s*", "\n", output)
            output = re.sub(r"\(data:image/svg\+xml;base64,[^\)]+\)",
                            "", output)
            output = re.sub(r"\(data:image/png;base64,[^\)]+\)", "", output)
            output = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", output)

            word_count = len(output.split())
            min_word_count = 100
            if word_count < min_word_count:
                return ""

            await page.unroute_all()
            await context.close()
            await browser.close()
            return output

        except Exception as e:
            log_error(e, f"Error fetching content from {url}")
            return ""


async def process_url_async(
        url: str,
        search_term: str,
        formatted_messages: list,
        agent_state: bool = False,
) -> list:
    """
    Asynchronously processes a single URL by fetching content,
    generating a prompt, obtaining an AI completion,
    and formatting messages.

    This function performs the following steps:
        - Fetches data from a cache or directly from the URL.
        - Generates a prompt using the retrieved content.
        - Runs an AI completion asynchronously.
        - Formats and appends messages based on the completion.
        - Saves URL statistics asynchronously.

    Args:
        url (str): The URL to be processed.
        search_term (str): The search term used to generate the prompt.
        formatted_messages (list): List to store formatted messages
            for output.

    Returns:
        list: A list of formatted messages, each represented
            as a dictionary.
    """
    try:
        content = cache_db(url=url, mode="load", url_bool=True)
        if not content:
            content = await fetch_content(url)
            if content.strip():
                cache_db(url=url, text=content, mode="save", url_bool=True)
            else:
                return []

        if agent_state:
            formatted_messages.append([
                {"role": "user", "content": f'<Website URL: "{url}">'},
                {"role": "user", "content": content}
            ])
            return formatted_messages

        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        prompt = url_prompt_gemini(search_term, current_date)

        completion = await asyncio.to_thread(
            gemini_request,
            model="gemini-1.5-flash",
            text=content,
            prompt=prompt,
            temperature=0.1
        )

        formatted_messages.extend([
            {"role": "user", "content": f'<Website URL: "{url}">'},
            {"role": "user", "content": "<Web Document Start>"},
            {"role": "user", "content": completion.text},
            {"role": "user", "content": "<Web Document End>"}
        ])

        return formatted_messages

    except Exception as e:
        log_error(e, f"Error processing URL {url}")
        return []


async def process_urls_async(
        search_term: str,
        formatted_messages: list,
        browse_mode: bool,
        agent_state: bool = False,
) -> None:
    """
    Asynchronously extracts and processes URLs from message text,
    using either a browse mode JSON input or direct extraction
    from the message.

    Args:
        search_term (str): The search term to be used for
            generating prompts.
        formatted_messages (list): A list to store formatted
            messages from processed URLs.
        browse_mode (bool): If True, URLs are loaded from a JSON format
            instead of message text.
        agent_state (bool): If True, the function is in agent state.

    Returns:
        None
    """
    urls = []

    if browse_mode:
        try:
            urls_dict = json.loads(browse_mode)
            urls = list(urls_dict.values())
        except json.JSONDecodeError:
            raise

    urls = [url for url in urls if f"{slack_team_domain}.slack.com" not in url]

    tasks = [
        process_url_async(url, search_term, formatted_messages, agent_state)
        for url in urls
    ]

    await asyncio.gather(*tasks)
