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

# Third-Party Imports
import pytz
import certifi
from openai import OpenAI
import google.generativeai as genai
from dotenv import load_dotenv # pylint: disable=E0611
from slack_bolt.app import App
from pymongo import MongoClient
from slack_sdk import WebClient

load_dotenv(override=True)

ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.set_ciphers("TLSv1.2")

# API Keys and Tokens
openai_api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
slack_app_token = os.getenv("SLACK_APP_TOKEN")
slack_bot_token = os.getenv("SLACK_BOT_TOKEN")

# Determine if running inside Docker
is_docker = os.getenv("IS_DOCKER", "false").lower() == "true"

# Use 'mongo' for Docker, 'localhost' for local development
if is_docker:
    mongo_uri = "mongodb://host.docker.internal:27017/"
else:
    mongo_uri = "mongodb://localhost:27017/"

serper_api_key = os.getenv("SERPER_API_KEY")

# Initialise clients and databases
slack_web_client = WebClient(token=slack_bot_token, ssl=ssl_context)
slackapp = App(token=slack_bot_token)
aiclient = OpenAI(api_key=openai_api_key)
genai.configure(api_key=gemini_api_key)
gemclient = genai
mongo_client = MongoClient(mongo_uri)

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

# Create the time series collection (if it doesn't exist)
if "Logging" not in informationdb.list_collection_names():
    informationdb.create_collection(
        "Logging",
        timeseries={
            "timeField": "timestamp",
            "granularity": "seconds",
        },
        expireAfterSeconds=3600 * 24 * 7  # Expire docs after 7 days
    )
    print("Time series collection 'Logging' created with TTL index.")

logging = informationdb["Logging"]

# Summarisation Openai models
BATCH_MODEL = "gpt-4o-mini"
SUMMARY_MODEL = "gpt-4o"

# Timezone
timezone = pytz.timezone("CET")

# Slack team domain
slack_team_domain = slackapp.client.team_info().data["team"]["domain"]

# Slack bot user ID
slack_bot_user_id = slackapp.client.auth_test()["user_id"]
