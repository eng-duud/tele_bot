"""
Core utility functions for text sanitization, markdown formatting, and formatting helpers.
"""

def escape_md(text: str) -> str:
    """
    Safely escape legacy Telegram Markdown formatting characters (*, _, `, [)
    to prevent entity parsing crashes when rendering dynamic user input.
    """
    if not text:
        return ""
    text_str = str(text)
    for ch in ('*', '_', '`', '['):
        text_str = text_str.replace(ch, f'\\{ch}')
    return text_str
