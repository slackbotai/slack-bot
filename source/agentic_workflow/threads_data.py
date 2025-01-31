"""
threads_data.py

This module contains functions to track active threads in the
agentic workflow.

Functions:
- enter_agentic_workflow: Mark a thread as active in the
    agentic workflow.
- exit_agentic_workflow: Unmark a thread once the agentic
    workflow is complete.
- is_thread_active: Check if a thread is currently active in
    the agentic workflow.
"""

# Dictionary to track active threads in agentic workflow
active_threads = {}

def enter_agentic_workflow(thread_ts: str,) -> None:
    """
    Function to mark a thread as active in the agentic workflow.
    
    Args:
        thread_ts (str): The timestamp of the thread message.
        
    Returns:
        None
    """
    active_threads[thread_ts] = True


def exit_agentic_workflow(thread_ts: str,) -> None:
    """
    Function to unmark a thread once the agentic workflow is complete.
    
    Args:
        thread_ts (str): The timestamp of the thread message.
    
    Returns:
        None
    """
    active_threads.pop(thread_ts, None)


def is_thread_active(thread_ts: str,) -> bool:
    """
    Function to check if a thread is currently active in the agentic workflow.
    
    Args:
        thread_ts (str): The timestamp of the thread message.
        
    Returns:
        bool: True if the thread is active, False otherwise.
    """
    return active_threads.get(thread_ts, False)
