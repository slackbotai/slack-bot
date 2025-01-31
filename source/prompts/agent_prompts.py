"""
agent_prompts.py

This module contains functions that generate prompts for the AI
agent to guide the user in providing information and together
completing a report.

Functions:
- agent_creation_prompt: Generates a prompt for creating AI analyst
	personas based on the research topic and feedback.
- question_prompt: Generates a prompt for an analyst to conduct an
	in-depth interview based on assigned goals.
- search_instructions_prompt: Generates a prompt for creating a
	search query based on an analyst-expert conversation.
- answer_instructions_prompt: Generates a prompt for an expert to
	answer questions using only the provided context.
- section_writer_prompt: Generates a prompt for writing a section of
	the report based on the focus area.
- generate_toc_prompt: Generates a prompt for creating a detailed
	Table of Contents (TOC).
- report_writer_prompt: Generates a prompt for writing the body of a
	report.
- intro_conclusion_prompt: Generates a prompt for writing an
	introduction or conclusion for the report.
- agent_analysis_prompt: Generates a prompt for analysing a report's
	alignment with source documents.
- agent_final_prompt: Generates a prompt for finalising a report based
	on analysis feedback.
- prompt_extract_info: Extracts specific fields from user-provided
	text based on given instructions.
- prompt_to_retrieve_users_choices: Generates a system prompt for
	querying the user about missing information.

Attributes:
	None
"""

def agent_creation_prompt(
      topic: str,
      description: str,
      human_analyst_feedback:str,
      max_analysts: int,
) -> list:
    """
    Generates a prompt for creating AI analyst personas based on the
	research topic and feedback.

    Args:
        topic (str): The main topic of research.
        description (str): Description of the research topic.
        human_analyst_feedback (str): Feedback from human analysts to
			guide persona creation.
        max_analysts (int): Maximum number of analysts to create.

    Returns:
        list: A list containing the prompt for creating
			analyst personas.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are tasked with creating a set of AI analyst "
				"personas who will each focus on a key theme related "
				"to the research topic. Follow these instructions "
				"carefully:\n\n"
                "1. **Review the Research Topic and Description**:\n"
                f"   - Topic: {topic}\n"
                f"   - Description: {description}\n\n"
                "2. **Examine Editorial Feedback** (if any) provided "
				"to guide the creation of the analysts:\n"
                f"   {human_analyst_feedback}\n\n"
                "3. **Identify Key Themes**:\n"
                "   - Analyse the research topic and feedback to "
				"determine the most significant themes.\n"
                "   - These themes will form the basis of the "
				"report's index and chapters.\n\n"
                "4. **Select Top Themes**:\n"
                f"   - Choose the top {max_analysts} themes most "
				"critical to the topic.\n\n"
                "5. **Assign Analysts**:\n"
                "   - Create one analyst persona for each selected "
				"theme.\n"
                "   - For each persona, define:\n"
                "       - **Name**: A fitting name for the persona.\n"
                "       - **Affiliation**: Their organisational or "
				"academic affiliation.\n"
                "       - **Role**: Their expertise or position "
				"related to the theme.\n"
                "       - **Description**: A brief overview of their "
				"focus area and its relevance.\n\n"
                "Ensure that each analyst is uniquely positioned to "
				"provide deep insights into their assigned theme."
            )
        }
    ]


def question_prompt(goals: str,) -> list:
    """
    Generates a prompt for an analyst to conduct an in-depth
	interview based on assigned goals.

    Args:
        goals (str): The specific goals for the interview.

    Returns:
        list: A list containing the prompt for conducting the interview.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are an analyst assigned to delve deep into a "
				"specific theme as part of a comprehensive report.\n\n"
                "**Your Objective**: To interview an expert and "
				"extract detailed, insightful, and specific "
				"information related to your assigned theme.\n\n"
                "**Goals**:\n"
                "1. **Depth and Specificity**: Obtain in-depth "
				"explanations and specific examples.\n"
                "2. **Relevance**: Focus on aspects directly relevant "
				"to the theme.\n"
                "3. **Clarity**: Ensure the gathered information is "
				"clear and usable for the report.\n\n"
                f"**Your Assigned Theme and Goals**:\n{goals}\n\n"
                "**Instructions**:\n"
                "- Begin by introducing yourself in a manner "
				"consistent with your persona.\n"
                "- Ask open-ended questions that encourage "
				"comprehensive answers.\n"
                "- Probe further based on responses to uncover deeper "
				"insights.\n"
                "- Cover various facets of the theme for a "
				"well-rounded understanding.\n"
                "- Conclude the interview politely when sufficient "
				"information is gathered: "
                "'Thank you so much for your help!'\n\n"
                "**Reminder**: Stay in character throughout the "
				"interview, reflecting your persona and goals. "
                "Your questions should facilitate creating a detailed "
				"index and content for the report."
            ),
        }
    ]


def search_instructions_prompt(
      browse_query: str,
      messages: str,
) -> list:
	"""
	Generates a prompt for creating a search query based on an
	analyst-expert conversation.

	Args:
		browse_query (str): The original search query provided by
			the user.
		messages (str): The conversation messages to analyse.

	Returns:
		list: A list containing the prompt for generating a search query.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You will be provided with a conversation between an "
				"analyst and an expert, focusing on a specific "
				"theme.\n\n"
				"**Your Task**:\n"
				"- Analyse the entire conversation to understand the "
				"context and key points discussed.\n"
				"- Pay special attention to the analyst's final "
				"question, as it encapsulates the current "
				"information gap.\n"
				"- Generate a well-structured and precise web search "
				"query to help retrieve relevant information "
				"for enriching the theme.\n\n"
				"**Instructions**:\n"
				f"- The original search query is: {browse_query}\n"
				"- Focus on the following conversation to extract the "
				f"search query:\n{messages}\n\n"
				"- Ensure the query is specific and targets "
				"authoritative sources.\n"
				"- Consider synonyms or related terms for more "
				"comprehensive results.\n"
				"- The goal is to find information that contributes "
				"meaningfully to the report's index and content."
			),
		}
	]


def answer_instructions_prompt(
      goals: str,
      context: str,
) -> list:
	"""
	Generates a prompt for an expert to answer questions using only
	the provided context.

	Args:
		goals (str): The specific goals of the analyst's questions.
		context (str): The contextual information to guide the answers.

	Returns:
		list: A list containing the prompt for answering questions.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You are an expert being interviewed by an analyst "
				"on a specific theme.\n\n"
				f"**Analyst's Focus Area**:\n{goals}\n\n"
				"**Your Task**:\n"
				"- Answer the analyst's questions using only the "
				"information provided below.\n"
				"- Provide clear, detailed, and informative responses "
				"to aid in creating the report's index and content.\n\n"
				f"**Context**:\n{context}\n\n"
				"**Guidelines**:\n"
				"1. **Use Only Provided Information**: Do not "
				"introduce external information or assumptions.\n"
				"2. **Citations**:\n"
				"   - Include citations next to relevant statements "
				"(e.g., [1], [2]).\n"
				"   - List all sources at the end under a 'Sources' "
				"section.\n"
				"3. **Formatting Sources**:\n"
				"   - If a source is "
				"'<Document source='assistant/docs/llama3_1.pdf' "
				"page='7'/>', cite it as:\n"
				"     [1] assistant/docs/llama3_1.pdf, page 7\n"
				"   - Exclude XML-like tags from citations.\n\n"
				"**Example**:\n"
				"- 'According to recent findings [1], quantum "
				"entanglement plays a crucial role...'\n\n"
				"**Sources**:\n"
				"- [1] assistant/docs/llama3_1.pdf, page 7\n"
				"- [2] www.example.com/article\n\n"
				"**Reminder**: Provide comprehensive answers that "
				"will help the analyst develop the report's "
				"structure and content."
			),
		}
	]


def section_writer_prompt(
      focus: str,
      interview: str,
) -> list:
	"""
	Generates a prompt for writing a section of the report based on
	the focus area.

	Args:
		focus (str): The specific focus area for the section.
		interview (str): Content of the interview between analysts.

	Returns:
		list: A list containing the prompt for writing the section.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You are an expert technical writer assigned to create "
				"a comprehensive section for a report on a specific "
				"theme.\n\n"
				"**Your Task**:\n"
				"- Analyse the provided interview between analysts.\n"
				"- Write a well-structured and informative section "
				"based on the focus area.\n"
				"- Ensure the section contributes meaningfully to the "
				"report and aligns with the index.\n\n"
				f"**Interview**:\n{interview}\n\n"
				f"**Focus Area**:\n{focus}\n\n"
				"**Instructions**:\n"
				"1. **Analyse Source Documents**:\n"
				"- Review the content carefully.\n"
				"- Note that each source document is introduced with "
				"a '<Document>' tag.\n\n"
				"2. **Structure**:\n"
				"- Use Markdown formatting.\n"
				"- **Section Title**: Use '##' for the main section "
				"title.\n"
				"- **Summary**: Use '### Summary' as a sub-header.\n"
				"- **Content**: Under the summary, provide detailed "
				"information, including key findings.\n"
				"- **Sources**: Use '### Sources' as a sub-header to "
				"list all referenced materials.\n\n"
				"3. **Writing Guidelines**:\n"
				"- Begin with background information relevant to the "
				"focus area.\n"
				"- Highlight novel or surprising insights.\n"
				"- Use in-text citations with numbered sources "
				"(e.g., [1], [2]).\n"
				"- Do not mention interviewers or experts by name; "
				"focus solely on the insights.\n\n"
				"4. **Final Review**:\n"
				"- Ensure the section flows logically and adheres to "
				"guidelines.\n"
				"- Aim for approximately 800 words.\n\n"
				"Now, proceed to write the section based on the focus "
				"area and interview provided."
			),
		}
	]


def generate_toc_prompt(text_report: str,) -> list:
	"""
	Generates a prompt for creating a detailed Table of Contents (TOC).

	Args:
		text_report (str): The full text or report containing
			headings and subheadings.

	Returns:
		list: A list containing the prompt for TOC generation.
	"""
	return [
		{
			"role": "system",
			"content": (
				"Analyse the following document and create a "
				"comprehensive Table of Contents (TOC) reflecting "
				"its structure. "
				"The TOC should list all headings and subheadings in "
				"the correct hierarchical order.\n\n"
				"**Document Text**:\n"
				f"{text_report}\n\n"
				"**Instructions**:\n"
				"- Identify all headings and subheadings.\n"
				"- Maintain the correct numbering format "
				"(e.g., 1, 1.1, 1.1.1).\n"
				"- Do not include content from the body text; "
				"only list the headings.\n"
				"- Ensure the TOC has proper indentation to represent "
				"hierarchy.\n"
				"- Use 'Sources' as the last bullet point if "
				"applicable.\n"
				"Present the TOC in a clear and organised format."
			),
		}
	]


def report_writer_prompt(
      report_type: str,
      description: str,
      sources: str,
) -> list:
	"""
	Generates a prompt for writing the body of a report.

	Args:
		report_type (str): The type of report (e.g., research paper,
			analysis).
		description (str): A detailed description of the report topic.
		sources (str): A list of sources or references to include.

	Returns:
		list: A list containing the prompt for report writing.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You are an expert writer specialising in creating "
				f"{report_type}s. Your task is to generate the body "
				f"text for a {report_type} on the topic:\n\n**"
				f"{description}**\n\n"
				"**Requirements**:\n"
				f"{sources}\n\n"
				"**Formatting Guidelines**:\n"
				f"- Format according to {report_type} style "
				"conventions.\n"
				"- Use appropriate headings and subheadings.\n"
				"- Ensure logical flow and coherence.\n\n"
				"**Instructions**:\n"
				"1. Read the provided text carefully.\n"
				"2. Do not include an introduction or conclusion.\n"
				"3. Apply the specified formatting guidelines.\n"
				"4. Prepare the content so it integrates seamlessly "
				"with other sections.\n\n"
				"Use the provided information to generate the body "
				"text for the report."
			),
		}
	]


def intro_conclusion_prompt(
      topic: str,
      formatted_str_sections: str,
      section_type: str,
) -> list:
	"""
	Generates a prompt for writing an introduction or conclusion "
	"for the report.

	Args:
		topic (str): The main topic of the report.
		formatted_str_sections (str): A string containing formatted
			report sections.
		section_type (str): Either "Introduction" or "Conclusion".

	Returns:
		list: A list containing the prompt for writing the
			introduction or conclusion.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You are a technical writer finalizing a report on "
				f"the topic:\n\n**{topic}**\n\n"
				"**Your Task**:\n"
				f"Write a concise and compelling **{section_type}** "
				"for the report. "
				"The section should either provide an overview "
				"(for introduction) or summarize findings and "
				"implications (for conclusion).\n\n"
				"**Instructions**:\n"
				"1. **Content**:\n"
				"- For Introduction: Introduce the topic and preview "
				"main themes.\n"
				"- For Conclusion: Summarize key findings and discuss "
				"implications.\n\n"
				"2. **Length**: Approximately 100-150 words.\n"
				"3. **Formatting**: Use Markdown formatting with '## "
				"Introduction' or '## Conclusion' as appropriate.\n"
				"4. **Style**: Maintain a professional tone and ensure "
				"clarity.\n\n"
				"**Report**:\n"
				f"{formatted_str_sections}\n\n"
				f"Now, proceed to write the {section_type.lower()} "
				"for the report."
			),
		}
	]


def agent_analysis_prompt(
      report_text: str,
      source_documents: str,
) -> list:
	"""
	Generates a prompt for analysing a report's alignment with
	source documents.

	Args:
		report_text (str): The text of the report to analyse.
		source_documents (str): Source documents to compare against.

	Returns:
		list: A list containing the prompt for report analysis.
	"""
	return [
		{
			"role": "system",
			"content": (
				"You are tasked with analysing a report to ensure "
				"its accuracy and alignment with provided source "
				"documents. Your role is to analyse and provide "
				"feedback only; you will NOT make any changes to the "
				"report.\n\n"
				"**Materials Provided**:\n"
				f"1. **Report Text**:\n{report_text}\n\n"
				f"2. **Source Documents**:\n{source_documents}\n\n"
				"**Instructions**:\n"
				"1. Review each section of the report thoroughly.\n"
				"2. Compare the content with the relevant information "
				"in the source documents.\n"
				"3. Identify inaccuracies, omissions, or "
				"discrepancies.\n"
				"4. Assign a score between **0 and 1** for each "
				"section:\n"
				"- **0**: No changes needed; perfectly aligns with "
				"the sources.\n"
				"- **1**: Major changes needed; significant deviation "
				"from the sources.\n\n"
				"**Feedback**:\n"
				"- For each section, include:\n"
				"   - **Section Title**\n"
				"   - **Score**\n"
				"   - **Feedback**:\n"
				"       - Issues Identified: Briefly describe the "
				"problems.\n"
				"       - Suggested Changes: Summarize potential "
				"improvements.\n\n"
				"Focus on actionable feedback to improve alignment "
				"with the sources."
			),
		}
	]


def agent_final_prompt(
      report_text: str,
      analysis_feedback: str,
      sections_to_include: list,
) -> list:
	"""
	Generates a prompt for finalising a report based on
	analysis feedback.

	Args:
		report_text (str): Original report text.
		analysis_feedback (str): Feedback for revisions.
		sections_to_include (list): Sections to include in the
			final report.

	Returns:
		list: A list of system prompts for report revision and
			finalisation.
	"""
	index_text = ""
	if "Index" in sections_to_include:
		index_text = (
			"4. **Add Index to Text**:\n"
			"- Integrate the provided index into the report by "
			"numbering each section and subsection as outlined in "
			"the index.\n"
			"- Ensure the numbering precedes the section title and "
			"aligns with its hierarchical position in the document.\n"
			"- Retain the hierarchical structure (e.g., 1, 1.1, 1.1.1) "
			"in numbering for subsections.\n"
			"- Ensure the section titles in the report match exactly "
			"with those provided in the index.\n"
			"- Keep the original index in the text as well as adding "
			"it to the corresponding titles.\n"
		)
	source_text = ""
	if "Source" in sections_to_include:
		source_text = (
			"- Ensure that all **citations and references** "
			"are correctly formatted and correspond to the "
			"source documents."
		)
	return [
		{
			"role": "system",
			"content": (
				"You are tasked with revising a report based on "
				"detailed analysis feedback. Your goal is to create "
				"a polished final version "
				"that incorporates necessary changes for sections "
				"with significant issues. Ensure the document "
				"structure is logical and "
				"consistent, and move all sources to an appropriate "
				"location while removing duplicates.\n\n"
				"**Materials Provided**:\n"
				f"1. **Original Report Text**:\n{report_text}\n\n"
				f"2. **Analysis Feedback**:\n{analysis_feedback}\n\n"
				f"3. **Sections To Include**:\n{sections_to_include}\n\n"
				"**Your Task**:\n"
				"1. **Review Feedback**:\n"
				"- Carefully read the feedback for each section.\n"
				"- Identify sections with a score over 0.7 for "
				"significant revisions.\n\n"
				"2. **Implement Revisions**:\n"
				"- Revise sections as per the suggested changes in "
				"the feedback.\n"
				"- Retain original text for sections scoring 0.7 or "
				"below.\n\n"
				"3. **Address Structural Issues**:\n"
				"- **Source Placement**: Move all sources to the end "
				"of the document and format in APA style.\n"
				"- **Remove Duplicates**: Eliminate redundant "
				"information.\n"
				"- **Ensure Logical Flow**: Adjust section "
				"transitions for coherence.\n\n"
				f"{index_text}\n"
				"5. **Integrate Changes Seamlessly**:\n"
				"- Ensure revisions blend smoothly with the report.\n"
				"- Adjust transitional sentences or paragraphs if "
				"needed.\n\n"
				"6. **Formatting for .docx File**:\n"
				"- Use consistent formatting (e.g., Heading 1 for "
				"main titles, Heading 2 for subsections).\n"
				"- Apply **Times New Roman, 12pt font**.\n"
				"- Maintain single-line spacing within paragraphs and "
				"double spacing between paragraphs.\n"
				"- Include page numbers, headers, or footers if "
				"necessary.\n\n"
				"7. **Final Review**:\n"
				"- Proofread for grammar, punctuation, and spelling "
				"errors.\n"
				f"{source_text}\n"
				"- Ensure the document is professional and ready for "
				"submission."
			),
		}
	]


def prompt_extract_info(
      topic: str,
      description: str,
      report_type: str,
      files_urls_browse: bool,
      index: bool,
      introduction: bool,
      conclusion: bool,
      source: bool,
      additional_prompt: str,
      text: str,
) -> list:
	"""
	Extracts specific fields from user-provided text based on
	given instructions.

	Args:
		topic (str): Current topic of the report.
		description (str): Current description of the report topic.
		report_type (str): Preferred format or type of the report.
		files_urls_browse (str): Source preference
			(files, urls or browse).
		index (bool): Whether to include a table of contents.
		introduction (bool): Whether to include an introduction section.
		conclusion (bool): Whether to include a conclusion section.
		source (bool): Whether to include a sources/references section.
		additional_prompt (str): Any additional instructions for
			the extraction.
		text (str): User-provided input.

	Returns:
		list: A list of system and user messages for processing and
			completing fields.
	"""
	return [
		{
			"role": "system",
			"content": (
			f"""
			Extract specific information from user-provided text,
			completing each field accurately without inference.

			**Guidelines**

			- **Objective**: Populate only missing fields in the
			provided list, based exclusively on explicit content
			from the user input.
			- **Retention of Data**: Do not modify existing field
			values if they already contain information.
			- **Explicitness**: Only fill fields when the user's
			input provides a direct, clear value. If uncertain or
			if the input lacks needed information, leave the field
			as None if it not already has information/values.
			- **Boolean Interpretation**: For fields marked as
			True/False, interpret user intent to decide on inclusion,
			based on user preferences or instructions.

			# Fields to Complete

			1. **Topic**: The primary subject or theme of the report.  
			- *Current Value*: {topic}
			2. **Description**: A concise overview or detailed
			description of the topic.  
			- *Current Value*: {description}
			3. **Report Type**: The preferred format or style of the
			report, such as research paper, analysis, or summary.  
			- *Current Value*: {report_type}
			4. **Files or Browse**: Source preference for information.  
			- **files**: The user wants to use their own files.  
			- **urls**: The user wants to use their own sources.  
			- **browse**: The user prefers external sources/browse
			the web.  
			- *Current Value*: {files_urls_browse}
			5. **Table of Contents**: Whether the report should
			include a table of contents.  
			- **True**: Include a TOC.  
			- **False**: Exclude a TOC.  
			- *Current Value*: {index}
			6. **Introduction**: Whether the report should include
			an introductory section.  
			- **True**: Include introduction.  
			- **False**: Exclude introduction.  
			- *Current Value*: {introduction}
			7. **Conclusion**: Whether the report should include a
			conclusion section.  
			- **True**: Include conclusion.  
			- **False**: Exclude conclusion.  
			- *Current Value*: {conclusion}
			8. **Source**: Whether the report should include a sources
			or references section.  
			- **True**: Include sources.  
			- **False**: Exclude sources.  
			- *Current Value*: {source}
			{additional_prompt}

			# Output Format

			Produce a clear, concise output for each field as
			specified. For Boolean fields, use only **True** or
			**False** as instructed by user input. Leave fields as
			'None' if user input does not address them explicitly
			or if there is uncertainty. 

			# Example

			*User Input*: "I'd like an analysis on renewable energy, 
			with a TOC and conclusion but no introduction or sources. 
			I'll be using my own files."

			*Result*:
			- **Topic**: Renewable energy
			- **Description**: None
			- **Report Type**: Analysis
			- **Files or Browse**: files
			- **Table of Contents**: True
			- **Introduction**: False
			- **Conclusion**: True
			- **Source**: False

			---

			Apply these instructions to ensure accurate, context-based 
			extraction with minimal interpretation beyond what's 
			explicitly given.
			"""
			)
		},
		{
			"role": "user",
			"content": text
		},
	]


def prompt_to_retrieve_users_choices(
    state: str,
    field_to_ask: str,
) -> list:
    """
    Generates a system prompt for querying the user about
	missing information.

    Args:
        state (str): The current state of known information.
        field_to_ask (str): The specific field to gather
		information about.

    Returns:
        list: A list containing the prompt for user clarification.
    """
    return [
        {
            "role": "system",
            "content": (
                "The current state of information is as follows: "
				f"{state}\n\n"
                f"Your task is to ask the user a specific question "
				f"to gather information for the '{field_to_ask}' "
				"field. Please make sure your question directly "
				"addresses the missing field, phrasing it in a way "
				"that leaves no room for interpretation.\n\n"
                "Here are the guidelines for how to form each "
				"question:\n\n"
                "1. **Topic**: If 'topic' is missing, ask the user, "
				"'What is the topic or main subject of the report?' "
                "Be clear that we need the central theme or focus "
				"of the report.\n\n"
                "2. **Description**: If 'description' is missing, "
				"ask, 'Could you provide a brief overview or detailed "
                "explanation of the topic?' Ensure they understand "
				"we're looking for a concise summary or detailed "
				"breakdown.\n\n"
                "3. **Report Type**: If 'report_type' is missing, "
				"ask, 'What format or style would you prefer for "
				"the report? For example, should it be a research "
				"paper, analysis, or summary?'\n\n"
                "4. **Files, URLs or Browse**: If 'files_urls_browse' "
				"is missing, ask, 'Would you like to use your own "
				"files or URLs as sources, or would you like me to "
				"browse for external information?'\n"
                "   - Make sure they understand this choice is about "
				"the source of information: their own files versus "
				"external sources.\n\n"
                "5. **Table of Contents**: If 'index' is missing, "
				"ask, 'Would you like the report to include a "
				"table of contents?' "
                "Make it clear that this choice determines if a "
				"TOC section should be part of the report.\n\n"
                "6. **Introduction**: If 'introduction' is missing, "
				"ask, 'Do you want the report to begin with an "
				"introduction section?' Be explicit that an "
				"introduction provides context and sets up the "
				"report's purpose.\n\n"
                "7. **Conclusion**: If 'conclusion' is missing, "
				"ask, 'Should the report end with a conclusion "
				"section summarising key points?' Highlight that this "
				"section wraps up the report with final insights.\n\n"
                "8. **Source**: If 'source' is missing, ask, 'Do you "
				"want a list of sources or references to be included "
				"in the report?' Make sure they understand that this "
				"choice impacts whether citations or references appear "
				"at the end.\n\n"
                "9. **URLs**: If 'urls' is missing, ask, 'Are there "
				"any specific URLs you would like to include as "
				"references or sources for the report?' Emphasise that "
				"this can help guide the report content with specific "
				"urls.\n\n"
                "10. **Files**: If 'files' is missing, ask, "
				"'Could you please attach the documents you would "
				"like to include as part of the report's source "
				"materials?' Be clear that this involves using files "
				"they provide for generating content.\n\n"
                "11. **Browse Query**: If 'browse_query' is missing, "
				"ask, 'Do you have a specific query or keywords for "
				"browsing information to include in the report?' "
                "Explain that this would determine the focus of "
				"external searches for content.\n\n"
                "Use these questions as templates, adjusting only "
				"as needed to ensure clarity based on the context. "
				"Remember, the goal is to prompt the user "
                "to provide each missing piece of information "
				"directly, with no ambiguity."
            )
        }
    ]
