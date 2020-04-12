from telegram.ext import Filters


class FiltersExt:
    non_command_text = ~Filters.command & Filters.text
    """
    Is a text message, but not starting with a bot command.
    
    Should be used literally anywhere, where regular text message is expected.
    """
