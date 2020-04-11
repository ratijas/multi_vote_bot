"""
Logger initializer for this app.

This module re-exports all content from the standard `logging` module,
so it can be used as a drop-in replacement
 - to ensure that logging was properly initialized, and
 - retain all functionality of the standard module with a single `import log`.
"""
from logging import *


def init():
    """ enable logging """
    basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                level=INFO)


# auto initialize when imported
init()
