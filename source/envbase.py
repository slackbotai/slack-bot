"""
envbase.py

Handles environment variables, Slack workspace members,
and member ID-to-name conversions.

This module contains functions to fetch and store Slack workspace
members, and to convert user IDs to real names. It also initialises
the OpenAI and Gemini clients, and sets up connections to the MongoDB
databases for storing information.

Functions:
- populate_members: Fetches all users in the Slack workspace and
    saves them to a list including all workspace members.
- get_member_name: Finds and returns the real name of a user by their
    user ID.

Attributes:
    slack_members (list): A list of all Slack members retrieved from
        the workspace.
    slack_team_domain (str): The domain of the Slack workspace.
    slack_bot_user_id (str): The user ID of the Slack bot.
    slack_web_client (WebClient): The Slack WebClient instance.
    slackapp (App): The Slack app instance (from "slack_bolt").
    aiclient (OpenAI): The OpenAI client instance.
    gemclient (Gemini): The Gemini client instance.
    mongo_client (MongoClient): The MongoDB client instance.
    mongodb (MongoClient): The MongoDB database instance.
    collection (Collection): The MongoDB collection for storing
        channel information.
    informationdb (MongoClient): The MongoDB database instance for
        storing information.
    bug_reports (Collection): The MongoDB collection for storing bug
        reports.
    feature_requests (Collection): The MongoDB collection for storing
        feature requests.
    summarisation (Collection): The MongoDB collection for storing
        summarisation data.
    channels (Collection): The MongoDB collection for storing channel
        information.
    thread_storage (Collection): The MongoDB collection for storing
        thread information.
    url_storage (Collection): The MongoDB collection for storing URL
        information.
    BATCH_MODEL (str): The OpenAI model for batch processing.
    SUMMARY_MODEL (str): The OpenAI model for summarisation.
    timezone (timezone): The timezone for the Slack workspace.

"""

# Standard Library Imports
import os
import ssl
import time
from urllib.parse import urlparse

# Third-Party Imports
import pytz
from openai import AsyncOpenAI, OpenAI
import google.generativeai as genai
from dotenv import load_dotenv  # pylint: disable=E0611
from slack_bolt.async_app import AsyncApp
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid, PyMongoError
from slack_sdk import WebClient
from slack_sdk.web.async_client import AsyncWebClient
from utils.thread_manager import ThreadManager

# Load environment variables
load_dotenv(override=True)

# Secure SSL context configuration
ssl_context = ssl.create_default_context()
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

# API Keys and Tokens
openai_api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
slack_app_token = os.getenv("SLACK_APP_TOKEN")
slack_bot_token = os.getenv("SLACK_BOT_TOKEN")

# Serper API Key
serper_api_key = os.getenv("SERPER_API_KEY", None)

# Slack Workspace Subdomain
workspace_subdomain = os.getenv("WORKSPACE_SUBDOMAIN")

# Determine if running inside Docker
is_docker = os.getenv("IS_DOCKER", "false").lower() == "true"
print(f"Running in Docker: {is_docker}")

if is_docker:
    # In docker-compose, MongoDB is reachable by the service name "mongo".
    # Allow env overrides, but do not fall back to host.docker.internal here:
    # that points outside the compose network and can make the bot appear stuck.
    MONGO_URI = (
        os.getenv("MONGO_URI_DOCKER")
        or os.getenv("MONGO_URI")
        or "mongodb://mongo:27017/"
    )
elif os.getenv("MONGODB_CLOUD_URI"):
    MONGO_URI = os.getenv("MONGODB_CLOUD_URI")
elif os.getenv("MONGO_URI"):
    MONGO_URI = os.getenv("MONGO_URI")
else:
    MONGO_URI = "mongodb://localhost:27017/"

def create_mongo_client(uri: str) -> MongoClient:
    """
    Create a MongoDB client and wait briefly for the server to be reachable.
    """
    attempts = int(os.getenv("MONGO_CONNECT_RETRIES", "6"))
    delay = int(os.getenv("MONGO_CONNECT_RETRY_DELAY_SECONDS", "5"))
    last_error = None

    for attempt in range(1, attempts + 1):
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=30000,
        )
        try:
            print(
                f"Connecting to MongoDB at: {uri} "
                f"(attempt {attempt}/{attempts})"
            )
            client.admin.command("ping")
            return client
        except PyMongoError as e:
            last_error = e
            print(f"MongoDB connection failed: {e}")
            client.close()
            if attempt < attempts:
                time.sleep(delay)

    raise last_error


def create_mongo_client_with_fallbacks(uri: str) -> MongoClient:
    """
    Connect to MongoDB, trying a small set of Docker-safe host aliases.
    """
    uris = [uri]
    parsed_uri = urlparse(uri)

    if is_docker and parsed_uri.hostname in {"mongo", "mongodb"}:
        alternate_host = "mongodb" if parsed_uri.hostname == "mongo" else "mongo"
        alternate_uri = uri.replace(
            f"://{parsed_uri.hostname}",
            f"://{alternate_host}",
            1,
        )
        uris.append(alternate_uri)

    last_error = None
    for candidate_uri in dict.fromkeys(uris):
        try:
            return create_mongo_client(candidate_uri)
        except PyMongoError as e:
            last_error = e
            print(f"MongoDB URI failed: {candidate_uri}")

    raise last_error


def ensure_logging_collection() -> None:
    """
    Create the logging collection if possible.

    If MongoDB is temporarily unavailable later, logging_utils already falls
    back to console output.
    """
    try:
        if "Logging" not in informationdb.list_collection_names():
            informationdb.create_collection(
                "Logging",
                timeseries={
                    "timeField": "timestamp",
                    "granularity": "seconds",
                },
                expireAfterSeconds=3600 * 24 * 7
            )
            print("Time series collection 'Logging' created with TTL index.")
    except CollectionInvalid:
        pass
    except PyMongoError as e:
        print(f"Could not prepare MongoDB logging collection: {e}")


# Initialise clients and databases

slack_web_client = AsyncWebClient(
    token=slack_bot_token,
    ssl=ssl_context,
    timeout=30,
)
slackapp = AsyncApp(client=slack_web_client)
aiclient = OpenAI(api_key=openai_api_key)
async_aiclient = AsyncOpenAI(api_key=openai_api_key)
genai.configure(api_key=gemini_api_key)
gemclient = genai
mongo_client = create_mongo_client_with_fallbacks(MONGO_URI)

# Channels DB
mongodb = mongo_client["Channels"]
collection = mongodb["Channels"]

# Information DB
informationdb = mongo_client["Information"]
bug_reports = informationdb["BugReports"]
feature_requests = informationdb["FeatureRequests"]
summarisation = informationdb["Summarisation"]
channels = informationdb["Channels"]
thread_storage = informationdb["ThreadStorage"]
url_storage = informationdb["URLStorage"]
threads = informationdb["Threads"]

thread_manager = ThreadManager(
    threads
)

logging = informationdb["Logging"]
ensure_logging_collection()

# Summarisation Openai models
BATCH_MODEL = "gpt-4.1-mini"
SUMMARY_MODEL = "gpt-4.1"

# Timezone
timezone = pytz.timezone("Europe/Stockholm") # Change as needed

# Slack team domain and bot user ID are bootstrap metadata used across modules.
# Runtime Slack API calls use AsyncWebClient/AsyncApp above.
bootstrap_slack_client = WebClient(
    token=slack_bot_token,
    ssl=ssl_context,
    timeout=30,
)
slack_team_domain = bootstrap_slack_client.team_info().data["team"]["domain"]
slack_bot_user_id = bootstrap_slack_client.auth_test()["user_id"]
