from logging import *

def init():
    """ enable logging """
    basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                level=INFO)

# auto initialize when imported
init()
