"""
cost_tracker.py

This module contains utility functions for tracking and calculating
the cost of summarisation tasks based on token usage for
different models.

Functions:
- calculate_cost: Calculates the cost of a summarisation based on token
    usage for two models.
- save_cost_data: Saves detailed cost data to a CSV file.
- save_cost_graph: Generates and saves a graph of summarisation total
    costs over time.

Attributes:
    MODEL_PRICES: A dictionary containing the prices for different
        models based on input and output token usage.
"""
import os
import pandas as pd # pylint: disable=import-error

import matplotlib # pylint: disable=import-error
import matplotlib.pyplot as plt # pylint: disable=import-error

from utils.logging_utils import log_error, log_message

matplotlib.use('Agg')

MODEL_PRICES = {
    "gpt-4o-mini": {
        "cached_input": 0.075,
        "input": 0.15,
        "output": 0.3,
    },
    "gpt-4o": {
        "cached_input": 1.25,
        "input": 2.50,
        "output": 5.00,
    },
}

def calculate_cost(
    batch_prompt_tokens: int,
    batch_completion_tokens: int,
    final_completion_tokens: int,
    batch_model: str,
    final_model: str,
    cached: bool = False,
) -> dict:
    """
    Calculates the cost of a summarisation based on token usage for
    two models.

    Args:
        prompt_tokens (int): Number of tokens used in the
            initial prompt.
        completion_tokens (int): Number of tokens used in the
            final completion.
        batch_model (str): The model used for the batching
            (e.g., "4o-mini").
        final_model (str): The final model used for the completion
            (e.g., "gpt-4o").
        cached (bool): Whether the initial input tokens were cached.

    Returns:
        dict: A dictionary containing costs for each model and the total cost.

    Raises:
        ValueError: If the specified model is unsupported.
    """
    # Check if the specified models are supported
    if batch_model not in MODEL_PRICES or final_model not in MODEL_PRICES:
        raise ValueError(f"Unsupported model(s): {batch_model}, {final_model}")

    # Get the prices for the specified models
    batch_prices = MODEL_PRICES[batch_model]
    final_prices = MODEL_PRICES[final_model]

    # Calculate the cost for the batch completion
    batch_input_cost = (
        (batch_prompt_tokens / 1_000_000) *
        (batch_prices["cached_input"] if cached else batch_prices["input"])
    )
    batch_output_cost = (
        (batch_completion_tokens / 1_000_000) *
        batch_prices["output"]
    )
    # Calculate the cost for the final completion
    final_input_cost = (
        (batch_completion_tokens / 1_000_000) *
        final_prices["input"]
    )
    final_output_cost = (
        (final_completion_tokens / 1_000_000) *
        final_prices["output"]
    )
    # Calculate the total cost
    total_cost = (batch_input_cost +
                  batch_output_cost +
                  final_input_cost +
                  final_output_cost
    )
    # Return the cost details
    return {
        "batch_input_cost": batch_input_cost,
        "batch_output_cost": batch_output_cost,
        "final_input_cost": final_input_cost,
        "final_output_cost": final_output_cost,
        "total_cost": total_cost,
    }


def save_cost_data(
    cost_details: dict,
    timestamp: str,
    batch_prompt_tokens: int,  # Original prompt tokens
    batch_completion_tokens: int, # Completion tokens from batch models
    final_completion_tokens: int, # Completion tokens from final model
    batch_model: str,
    final_model: str,
) -> None:
    """
    Saves detailed cost data to a CSV.

    Args:
        cost_details (dict): A dictionary containing the cost details.
        timestamp (str): The timestamp of the cost calculation.
        batch_prompt_tokens (int): Number of tokens used in the
            initial prompt.
        batch_completion_tokens (int): Number of tokens used in the
            batch completion.
        final_completion_tokens (int): Number of tokens used in the
            final completion.
        batch_model (str): The model used for the batching
            (e.g., "4o-mini").
        final_model (str): The final model used for the completion
            (e.g., "gpt-4o").
    
    Returns:
        None

    Raises:
        ValueError: If the costs or token counts are negative.
        ValueError: If the timestamp is empty.
        FileNotFoundError: If the CSV file is not found.
    """
    # Define the directory for 'your/summarisation_costs'
    summarisation_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'your', 'summarisation_costs')
    )

    # Ensure the directory exists
    os.makedirs(summarisation_dir, exist_ok=True)

    # Define the file path for the CSV
    file_path = os.path.join(summarisation_dir, "summarisation_costs.csv")

    batch_input_cost = cost_details["batch_input_cost"]
    batch_output_cost = cost_details["batch_output_cost"]
    final_input_cost = cost_details["final_input_cost"]
    final_output_cost = cost_details["final_output_cost"]
    total_cost = cost_details["total_cost"]

    if (
    total_cost < 0
    or batch_prompt_tokens < 0
    or batch_completion_tokens < 0
    or final_completion_tokens < 0):
        raise ValueError(
            "Costs and token counts must be non-negative."
        )
    if not timestamp:
        raise ValueError("Timestamp cannot be empty.")

    total_batch_tokens = batch_prompt_tokens + batch_completion_tokens
    total_final_tokens = batch_completion_tokens + final_completion_tokens
    total_tokens = total_batch_tokens + total_final_tokens

    data = {
        "timestamp": [timestamp],
        "batch_prompt_tokens": [batch_prompt_tokens],
        "batch_completion_tokens": [batch_completion_tokens],
        "final_completion_tokens": [final_completion_tokens],
        "batch_model": [batch_model],
        "batch_input_cost": [batch_input_cost],
        "batch_output_cost": [batch_output_cost],
        "final_model": [final_model],
        "final_input_cost": [final_input_cost],
        "final_output_cost": [final_output_cost],
        "total_batch_tokens": [total_batch_tokens],
        "total_final_tokens": [total_final_tokens],
        "total_tokens": [total_tokens], # Total of all tokens
        "total_cost": [total_cost],
    }
    df = pd.DataFrame(data)

    try:
        existing_df = pd.read_csv(file_path)
        updated_df = pd.concat([existing_df, df], ignore_index=True)
    except FileNotFoundError:
        updated_df = df

    updated_df.to_csv(file_path, index=False)


def save_cost_graph() -> None:
    """
    Generates and saves a graph of summarisation total costs over time.

    Returns:
        None
    
    Raises:
        FileNotFoundError: If the CSV file is not found.
        Exception: If an error occurs while generating the graph.
    """

    # Define the directory for 'your/summarisation_costs'
    summarisation_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'your', 'summarisation_costs')
    )

    # Ensure the directory exists
    os.makedirs(summarisation_dir, exist_ok=True)

    # Define paths for the CSV file and graph image
    file_path = os.path.join(summarisation_dir, "summarisation_costs.csv")
    graph_file = os.path.join(summarisation_dir, "summarisation_costs_graph.png")

    try:
        df = pd.read_csv(file_path)

        if 'total_cost' not in df.columns: # Changed to total_cost
            log_message(
                "The required column 'total_cost' is missing in the data.",
                "warning")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        plt.figure(figsize=(10, 6))
        plt.plot(
            df['timestamp'],
            df['total_cost'], # Changed to total_cost
            marker='o',
            linestyle='-',
            label='Total Cost (USD)'
        )
        plt.title('Summarisation Total Costs Over Time')
        plt.xlabel('Time')
        plt.ylabel('Total Cost (USD)')
        plt.grid(True)
        plt.legend()

        plt.savefig(graph_file, format="png", dpi=300)
        plt.close()

    except FileNotFoundError:
        log_message(
            f"No cost data available in '{file_path}' to generate a graph.",
            "warning"
        )
    except Exception as e:
        log_error(e, "An error occurred while generating the graph.")
