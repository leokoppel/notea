"""
Classes and functions with no internal depencies, which can be used across the package.
"""
# (c) Leo Koppel 2014 

import os
import abc
import re
import inflect as inflect_module
inflect = inflect_module.engine()

def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)

class EngineError(Exception):
    """ an exception to raise if something goes wrong while scripting the game """

class ParseError(Exception):
    """ used to break out of parsing loops on error """
    pass

class AmbiguityError(ParseError):
    """
    """
    def __init__(self, message, ambiguity):
        super(AmbiguityError, self).__init__(message)
        self.ambiguity = ambiguity



class WordCategory(dict):
    """
    Dict of iterables with nested "in" operator 
    
    """
    def __contains__(self, search):
        return any(search in self[a] for a in self)

_current_game = None # The current game being scripted (global)


class NonStringIterable:
    """ Use to check for iterables that aren't strings """
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __iter__(self):
        while False:
            yield None

    @classmethod
    def __subclasshook__(cls, C):
        if cls is NonStringIterable:
            if any("__iter__" in B.__dict__ for B in C.__mro__):
                return True
        return NotImplemented

def basest(collection):
    """ Determine the "basest" type in an iterable """

    # the basest element must be in the first element's MRO
    mro = type(collection[0]).__mro__
    current = 0

    for el in collection:
        while not isinstance(el, mro[current]):
            current += 1

    return mro[current]

def check_sublist(biglist, sublist):
    num = len(sublist)
    return any((sublist == biglist[i:i + num]) for i in xrange(len(biglist) - num + 1))

def list_str(l):
    """ print a list using elements' __str__'s instead of __repr__'s """
    return "[" + ", ".join([p.__str__() for p in l]) + "]"

def dedent(string):
    """
    Remove extra whitespace from a string.
    Remove single newlines but keep blank lines.
    """
    res = re.sub(r'(?<!.\n|  )\n(?!(\n))', r' ', string.strip())
    res = re.sub(r'[ \t]*\n[ \t]*' , r'\n', res)
    res = re.sub(r'  +', r' ', res)
    return res

def replace_decorator(methodname):
    """
    Returns a decorator method that can be used to set the instance's method
    """
    def replace_method(self):
        def decorator(f):
            setattr(self, methodname, f)
            return f
        return decorator
    return replace_method

def ensure_path_exists(path):
    """
    Create directories if a path doesn't exist
    From http://stackoverflow.com/a/14364249
    """
    try: 
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise
        
# default for keyword arguments where None is a valid input
sentinel = object()