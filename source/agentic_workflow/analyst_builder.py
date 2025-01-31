"""
analyst_builder.py

This module contains classes and functions to generate analyst personas
based on a research topic.

Classes:
- Analyst: Represents an analyst persona with details about their
    affiliation, role, and focus area.
- Perspectives: Represents a collection of analysts with their roles
    and affiliations.
- GenerateAnalystsState: Represents the state of generating analysts,
    containing the research topic, maximum number of analysts, human
    feedback, and the list of generated analysts.

Attributes:
    None
"""

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class Analyst(BaseModel):
    """
    Represents an analyst persona with details about their affiliation, role,
    and focus area. This class is used to define each analyst's attributes
    in a research context.

    Attributes:
        affiliation (str): Primary affiliation of the analyst.
        name (str): Name of the analyst.
        role (str): Role of the analyst in the context of the topic.
        description (str): Description of the analyst's focus, concerns,
            and motives.
    """
    affiliation: str = Field(
        description="Primary affiliation of the analyst."
    )
    name: str = Field(
        description="Name of the analyst."
    )
    role: str = Field(
        description="Role of the analyst in the context of the topic."
    )
    description: str = Field(
        description=("Description of the analyst's focus, "
                     "concerns, and motives.")
    )
    @property
    def persona(self) -> str:
        """
        Creates a string representation of the analyst persona,
        summarising their name, role, affiliation, and description.

        Returns:
            str: A formatted string representing the analyst's persona.
        """
        return (
            f"Name: {self.name}\nRole: {self.role}\n"
            f"Affiliation: {self.affiliation}\nDescription: {self.description}"
        )


class Perspectives(BaseModel):
    """
    Represents a collection of analysts with their roles and affiliations.
    This class is used to hold a list of analysts in the context of a
    specific research topic.

    Attributes:
    
            analysts (list[Analyst]): Comprehensive list of analysts with
                their roles and affiliations.
    """
    analysts: list[Analyst] = Field(
        description="Comprehensive list of analysts with their roles and affiliations."
    )


class GenerateAnalystsState(TypedDict):
    """
    Represents the state of generating analysts, containing the
    research topic, maximum number of analysts, human feedback,
    and the list of generated analysts.

    Attributes:
            topic (str): Research topic for generating analysts.
            description (str): Description of the research topic.
            max_analysts (int): Maximum number of analysts to generate.
            human_analyst_feedback (str): Human feedback on the
                generated analysts.
            analysts (list[Analyst]): List of analysts generated for
                the research topic
    """
    topic: str
    description: str
    max_analysts: int
    human_analyst_feedback: str
    analysts: list[Analyst]
