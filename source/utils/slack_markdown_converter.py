"""
slack_markdown_converter.py

A module to convert Markdown text into Slack-compatible formatting
using custom parsers and renderers. This module customises the mistune
markdown parser to handle Slack-specific features, such as mentions,
lists, and text styles.

Classes:
- SlackInlineLexer: Custom lexer for processing Slack mentions and
    inline text.
- SlackBlockLexer: Custom block lexer for handling Slack-specific
    list formats.
- SlackRenderer: Custom renderer to format Markdown elements
    (e.g., bold, lists) in Slack-compatible syntax.
- Markdown2Slack: Main interface for converting Markdown to Slack
    formatting using the custom lexer and renderer.

Attributes:
    None
"""

import re

import mistune
from bs4 import BeautifulSoup

class SlackInlineLexer(mistune.InlineLexer):
    """
    Custom InlineLexer for processing Slack mentions in Markdown text.
    
    This lexer adds a rule to match Slack mentions in the format of 
    @username or <@userID> and converts them to the appropriate Slack 
    mention format.
    """
    def __init__(self,
                 renderer: mistune.Renderer,
                 rules: dict = None,
                 **kwargs,
    ) -> None:
        """
        Initialise the SlackInlineLexer with custom rules for Slack 
        mentions.
        
        Args:
            renderer: The renderer to use for conversion.
            rules: The grammar rules to use.
            **kwargs: Additional arguments for the superclass.
        
        Returns:
            None
        """
        super().__init__(renderer, rules, **kwargs)
        self.rules.slack_mention = re.compile(
            r'(@[a-zA-Z0-9_]+|<@([A-Z0-9]+)>)'
        )
        self.default_rules.insert(0, 'slack_mention')

    def output_slack_mention(self, m,) -> str:
        """
        Convert matched Slack mention to the appropriate Slack format.
        
        Args:
            m: The regex match object containing the mention.
        
        Returns:
            str: The converted Slack mention in <@userID> format.
        """
        mention = m.group(0)
        if mention.startswith('@'):
            return f'<{mention}>'
        return mention

class SlackBlockLexer(mistune.BlockLexer):
    """
    A custom BlockLexer for Slack Markdown.

    The primary change is to the "list_item" rule, which is modified to
    match the behaviour of Slack's Markdown parser.
    """
    def __init__(self,
                 rules: dict = None,
                 **kwargs
    ) -> None:
        """
        Initialise the SlackBlockLexer instance.

        Args:
            rules: The grammar rules to use
                (default: mistune.BlockLexer.default_rules)
            **kwargs: Additional keyword arguments to pass
                to the superclass

        Returns:
            None
        """
        # Use the custom grammar
        super().__init__(rules, **kwargs)
        # Regular expression pattern to match list
        # items in Markdown text
        self.rules.list_item = re.compile(
            (r'^(( *)(?:[*+-]|\d+\.|[A-Z]\))\s.*'
            r'(?:\n(?!\2(?:[*+-]|\d+\.|[A-Z]\))).*)*)'),
            flags=re.M,)

class Markdown2Slack:
    """
    A class for converting Markdown text to Slack-compatible formatting.
    """
    def __init__(self,) -> None:
        """
        Initialise the Markdown2Slack instance.

        Args:
            None

        Return:
            None
        """
        self.markdown = mistune.Markdown(
            renderer=SlackRenderer(parent=self),
            inline=SlackInlineLexer,
            block=SlackBlockLexer
        )
        self.indentation_levels = None

    def convert(self, text: str,) -> str:
        """
        Convert Markdown text to Slack-compatible formatting.

        Args:
            text: The Markdown text to convert.

        Return:
            str: The converted Slack-formatted text.
        """
        # Calculate and save indentation levels
        self.indentation_levels = self.get_indentation_levels(text)
        # Convert the Markdown
        converted = self.markdown(text)
        return converted

    def get_indentation_levels(self, text: str,) -> list:
        """
        Get the indentation levels of the Markdown text.

        Args:
            text: The Markdown text.

        Return:
            list: A list of tuples containing the indentation level,
                the stripped line, and whether it's ordered or
                unordered.
        """
        lines = text.split('\n')
        indentation_levels = []

        for line in lines:
            stripped_line = line.lstrip()
            # Check if the line is part of an ordered or unordered list
            if (stripped_line.startswith(('-', '*')) or
                    re.match(r'(\d+\.|[A-Z]\))', stripped_line)):
                indentation_level = len(line) - len(stripped_line)
                is_ordered = False

                # Check if the list is ordered
                # (starts with a number followed by a dot)
                if re.match(r'(\d+\.|[A-Z]\))', stripped_line):
                    is_ordered = True

                # Append the indentation level,
                # the line, and whether it's ordered or unordered
                indentation_levels.append(
                    (indentation_level, stripped_line, is_ordered)
                )
        return indentation_levels

class SlackRenderer(mistune.Renderer):
    """
    A custom renderer for Slack Markdown.

    This renderer extends the mistune Renderer class to provide custom
    rendering for Slack-specific Markdown syntax.
    """
    def __init__(self, parent=None,) -> None:
        """
        Initialise the SlackRenderer instance.

        Args:
            parent: The parent Markdown2Slack instance.
        
        Returns:
            None
        """
        super().__init__()
        self.parent = parent

    def header(self, text: str, level: int, raw: str = None,) -> str:
        """
        Render a header element.

        Args:
            text: The header text.
            level: The header level (1-6).
            raw: The raw header text (optional).

        Return:
            str: The rendered header element.
        """
        # Handle numbered headers or lettered headers
        if raw:
            # Match numbered, lettered, or bold headers
            match = re.match(r'(\d+\.|[A-Z]\))?\s*(\*\*.*\*\*)', raw)
            if match:
                # Capture "1.", "A)", etc., or leave empty
                prefix = match.group(1) or ""
                # Capture the bolded text
                bold_text = match.group(2) or ""
                # Remove Markdown bold indicators
                bold_text = bold_text.replace("**", "")
                if prefix:
                    return f"*{prefix.strip()} {bold_text}*\n"
                return f"*{bold_text}*\n"
        return f"*{text}*\n"

    def bold(self, text: str,) -> str:
        """
        Render bold text.

        Args:
            text: The text to render as bold.

        Return:
            str: The rendered bold text.
        """
        return '*' + text + '*'

    def italic(self, text: str,) -> str:
        """
        Render italic text.

        Args:
            text: The text to render as italic.

        Return:
            str: The rendered italic text.
        """
        return '_' + text + '_'

    def bold_italic(self, text: str,) -> str:
        """
        Render bold and italic text.

        Args:
            text: The text to render as bold and italic.

        Return:
            str: The rendered bold and italic text.
        """
        return '*' + '_' + text + '_' + '*'

    def strikethrough(self, text: str,) -> str:
        """
        Render strikethrough text.

        Args:
            text: The text to render as strikethrough.

        Return:
            str: The rendered strikethrough text.
        """
        return '~' + text + '~'

    def codespan(self, text: str,) -> str:
        """
        Render a code span.

        Args:
            text: The text to render as a code span.

        Return:
            str: The rendered code span.
        """
        return '`' + text + '`'

    def block_code(self, code: str, lang: str = None,) -> str:
        """
        Render a code block.

        Args:
            code: The code to render as a block.
            lang: The language identifier (optional).

        Return:
            str: The rendered code block.
        """
        code = code.rstrip('\n')  # Remove any trailing newlines
        if lang:
            # Add the language identifier after the opening backticks
            return f"```{lang}\n{code}\n```\n"
        # Default to plain code block if no language is specified
        return f"```\n{code}\n```\n"

    def link(self, link: str, title: str = None, text: str = None,) -> str:
        """
        Render a link.

        Args:
            link: The link URL.
            title: The link title (optional).
            text: The link content (optional).

        Return:
            str: The rendered link.
        """
        if text:
            return f'<{link}|{text}>'
        if title:
            return f'<{link}|{title}>'
        return f'<{link}>'

    def block_quote(self, text: str,) -> str:
        """
        Render a block quote.

        Args:
            text: The text to render as a block quote.

        Return:
            str: The rendered block quote.
        """
        return '> ' + text.replace('\n', '\n> ')

    def hrule(self,) -> str:
        """
        Render a horizontal rule.

        Args:
            text (str): The text to render as a horizontal rule.

        Return:
            str: The rendered horizontal rule.
        """
        return "\n\n"

    def table(self, header: str, body: str,) -> str:
        """
        Render a table.

        Args:
            header: The table header.
            body: The table body.

        Return:
            str: The rendered table.
        """
        # Parse HTML strings using BeautifulSoup
        soup_header = BeautifulSoup(header, "html.parser")
        soup_body = BeautifulSoup(body, "html.parser")

        # Extract header columns without bold formatting
        header_cells = soup_header.find_all("th")
        header_texts = [cell.get_text(strip=True) for cell in header_cells]

        # Find the maximum width of each column
        body_rows = soup_body.find_all("tr")
        body_data = []
        column_widths = [len(text) for text in header_texts]

        for row in body_rows:
            cells = row.find_all("td")
            cell_texts = [cell.get_text(strip=True) for cell in cells]

            # Update column widths based on the current row
            for i, text in enumerate(cell_texts):
                if i >= len(column_widths):
                    column_widths.append(len(text))
                else:
                    column_widths[i] = max(column_widths[i], len(text))

            # Append row data
            body_data.append(cell_texts)

        # Format the header row with dynamic column alignment
        formatted_header = " | ".join(
            header_text.ljust(
                column_widths[i]) for i, header_text in enumerate(header_texts)
        )
        # Create a separator line that matches the total table width
        separator_line = '-' * (sum(column_widths) + 3 * (len(
            column_widths) - 1)
        )
        # Format each row with dynamic column alignment
        formatted_body_rows = []
        for row in body_data:
            formatted_row = " | ".join(
                row[i].ljust(column_widths[i]) if i < len(row) else "".ljust(
                    column_widths[i])
                for i in range(len(column_widths))
            )
            formatted_body_rows.append(formatted_row)

        # Combine header, separator, and body
        slack_table = (
            formatted_header + "\n" +
            separator_line + "\n" +
            "\n".join(formatted_body_rows)
        )
        return "```" + "\n" + slack_table + "\n" + "```"

    def emphasis(self, text: str,) -> str:
        """
        Render emphasis text.

        Args:
            text: The text to render as emphasis.

        Return:
            str: The rendered emphasis text.
        """
        return '_' + text + '_'

    def double_emphasis(self, text: str,) -> str:
        """
        Render double emphasis text.

        Args:
            text: The text to render as double emphasis.

        Return:
            str: The rendered double emphasis text.
        """
        return '*' + text + '*'

    def list(self, body: str, ordered: bool,) -> str:
        """
        Render a list.

        Args:
            body: The list text.

        Return:
            str: The rendered list.
        """
        lines = body.split('\n')
        formatted_lines = []
        for line in lines:
            # Calculate indentation
            indent_level = len(line) - len(line.lstrip())
            stripped_line = line.strip()
            formatted_lines.append(' ' * indent_level + stripped_line)
        return '\n'.join(formatted_lines)

    def list_item(self, text: str,) -> str:
        """
        Render a list item.

        Args:
            text: The list item text.

        Return:
            str: The rendered list item
        """
        if self.parent and self.parent.indentation_levels:
            # Retrieve lines from indentation_levels
            indentation_data = self.parent.indentation_levels

            for level, line, ordered in indentation_data:
                stripped_line_1 = line.strip()
                # Replace single * with _ for italic text
                #stripped_line = self.bold(stripped_line_1)
                stripped_line = re.sub(
                    r'(?<!\*)\*(?!\*)(.+?)\*', r'_\1_', stripped_line_1
                )
                # Replace ** with * for bold text
                #stripped_line = self.italic(stripped_line)
                stripped_line = re.sub(
                    r'\*\*(.+?)\*\*', r'*\1*', stripped_line
                )
                if ordered:
                    stripped_line = re.sub(r'^\d+\.\s*', '', stripped_line)
                else:
                    if stripped_line.startswith('- '):
                        stripped_line = stripped_line.replace('- ', '', 1)
                first_part_of_text = re.split(
                    r'\s{2,}', text.strip(), maxsplit=1,
                )[0]
                if stripped_line in first_part_of_text:
                    indentation_level = level
                    break
            else:
                # If no match is found, use default indentation level
                indentation_level = 0
        else:
            indentation_level = 0
        # Replace all instances of '**' with '*' in the text itself
        text = text.replace('**', '*')
        text = re.sub(r'([:.*_]) {2}', r'\1\n  ', text)

        if ordered:
        # Match the number at the beginning of the
        # ordered list item (e.g., "1.")
            match = re.match(r"^(\d+\.|[A-Z]\))", stripped_line_1.strip())
            if match:
                # Get the number from the match (e.g., "1")
                number = match.group(1)
                # Remove the old number and re-apply
                # it with proper formatting
                # Remove the old number part
                text = re.sub(r"^(\d+\.|[A-Z]\))\s*", "", text.strip())
                return f"{' ' * indentation_level}{number} {text.strip()}\n\n"
        return f"{' ' * indentation_level}• {text.strip()}\n\n"

    def image(self, src: str, title: str = None, text: str = None,) -> str:
        """
        Render an image.

        Args:
            src: The image source.
            title: The image title.
            text: The image text.

        Return:
            str: The rendered image.
        """
        if title or text:
            return f'<{src}|{title if title else text}>'
        return f'<{src}>'

    def paragraph(self, text: str,) -> str:
        """
        Render a paragraph.

        Args:
            text: The paragraph text.

        Return:
            str: The rendered paragraph.
        """
        # Replace <br> tags with newline characters
        text = text.replace('<br>', '\n')
        return text + '\n'

    def autolink(self, link: str, is_email: bool,) -> str:
        """
        Render an autolink.

        Args:
            link: The link URL.
            is_email: Whether the link is an email.

        Return:
            str: The rendered autolink.
        """
        if is_email:
            return link
        else:
            return self.link(link, None, None)

    def text(self, text: str,) -> str:
        """
        Render plain text.

        Args:
            text: The plain text.

        Return:
            str: The rendered text.
        """
        return text

    def linebreak(self) -> str:
        """
        Render a linebreak.

        Return:
            str: The rendered linebreak.
        """
        return '\n'
