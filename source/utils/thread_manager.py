class ThreadManager:
    """Handles all CRUD operations for the thread mapping collection in MongoDB.

    This class provides a structured API to manage the lifecycle of a thread
    document, using a composite key of channel_id and slack_thread_ts as its
    primary key (_id) to ensure uniqueness across all channels.
    """

    def __init__(self, collection):
        """Initializes the ThreadManager with a specific MongoDB collection.

        Args:
            collection: A PyMongo `Collection` object that the manager will
                operate on.
        """
        self.collection = collection

    def _get_doc_id(self, channel_id: str, slack_thread_ts: str) -> str:
        """Creates a composite document ID from channel and thread timestamp."""
        return f"{channel_id}-{slack_thread_ts}"

    def save_thread(
        self,
        slack_thread_ts: str,
        channel_id: str,
        openai_thread_id: str,
        done_ts: str = None,
        metadata: dict = None,
    ):
        """Saves or updates a thread mapping document in the collection.

        Args:
            slack_thread_ts: The unique timestamp of the Slack thread.
            channel_id: The Slack channel ID associated with the thread.
            openai_thread_id: The corresponding ID of the OpenAI Assistant thread.
            done_ts (str, optional): A timestamp indicating when the thread
                conversation was completed. Defaults to None.
            metadata (dict, optional): A dictionary of any additional fields
                to save with the thread document. Defaults to None.

        Returns:
            The `UpdateResult` object from the PyMongo `update_one` operation.
        """
        doc_id = self._get_doc_id(channel_id, slack_thread_ts)
        update_fields = {"openai_thread_id": openai_thread_id}

        if done_ts:
            update_fields["done_ts"] = done_ts

        if metadata:
            update_fields.update(metadata)

        # Use $setOnInsert to add key identifiers only when creating a new doc
        result = self.collection.update_one(
            {"_id": doc_id},
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "channel_id": channel_id,
                    "slack_thread_ts": slack_thread_ts,
                },
            },
            upsert=True,
        )
        return result

    def update_done_ts(self, slack_thread_ts: str, channel_id: str, done_ts: str) -> None:
        """Updates the completion timestamp ('done_ts') for a specific thread.

        Args:
            slack_thread_ts: The timestamp of the thread to update.
            channel_id: The Slack channel ID of the thread.
            done_ts: The completion timestamp to set.
        """
        doc_id = self._get_doc_id(channel_id, slack_thread_ts)
        self.collection.update_one({"_id": doc_id}, {"$set": {"done_ts": done_ts}})

    def update_thread_metadata(
        self, slack_thread_ts: str, channel_id: str, metadata: dict
    ) -> None:
        """Updates a thread document with a set of new or modified fields.

        Args:
            slack_thread_ts: The timestamp of the thread to update.
            channel_id: The Slack channel ID of the thread.
            metadata: A dictionary containing the fields and values to set.
        """
        doc_id = self._get_doc_id(channel_id, slack_thread_ts)
        self.collection.update_one({"_id": doc_id}, {"$set": metadata})

    def get_thread(self, thread_ts: str, channel_id: str) -> dict | None:
        """Retrieves a single thread document by its composite ID.

        Args:
            thread_ts: The Slack thread timestamp of the document.
            channel_id: The Slack channel ID of the document.

        Returns:
            The thread document as a dictionary if found, otherwise None.
        """
        doc_id = self._get_doc_id(channel_id, thread_ts)
        return self.collection.find_one({"_id": doc_id})