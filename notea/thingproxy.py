"""
Allows game objects to return a proxy object on init, while storing the 'real
thing' with the Game. These variables can be used transparently in game logic
across Sessions. This is needed to save and restore games.
"""
# (c) Leo Koppel 2014 (with exception of recipe code referenced below)

import util

class ProxiableMeta(type):
    def __call__(cls, *args, **kwargs):
        """
        Create and initialize a BaseThing, binding it to the Session.
        Return a proxy object if possible, unless proxy=False is given or
        the game's proxy_things setting is false.
        """
        proxy = kwargs.pop('proxy', True)

        thing = cls.__new__(cls, *args, **kwargs)
        thing.__init__(*args, **kwargs)

        # Only proxy objects which do set _uid, and if Game settings allow it
        if proxy and hasattr(thing, '_uid') and thing._game.proxy_things:
            return ThingProxy(thing)

        return thing


class ThingProxy(object):
    """
    A proxy with lazy evaluation of it's target, based on _uid.
    
    Giving the game author proxies allows them to use (proxy) Thing variables
    in game logic across Sessions.
    
    Based on (non-lazy) proxy recipe at http://code.activestate.com/recipes/496741-object-proxying/
    """
    def __init__(self, thing, game=None):
        object.__setattr__(self, '_game', game or util._current_game)
        object.__setattr__(self, '_proxy_uid', thing._uid)

    def _get_proxy_target(self):
        return object.__getattribute__(self, '_game').current_session._get_thing_by_uid(object.__getattribute__(self, '_proxy_uid'))

    #
    # proxying (special cases)
    #
    def __getattribute__(self, name):
        return getattr(object.__getattribute__(self, '_get_proxy_target')(), name)
    def __delattr__(self, name):
        return delattr(object.__getattribute__(self, '_get_proxy_target')(), name)
    def __setattr__(self, name, value):
        return setattr(object.__getattribute__(self, '_get_proxy_target')(), name, value)

    def __nonzero__(self):
        return bool(object.__getattribute__(self, '_get_proxy_target')())
    def __str__(self):
        return str(object.__getattribute__(self, '_get_proxy_target')())
    def __unicode__(self):
        return unicode(object.__getattribute__(self, '_get_proxy_target')())
    def __repr__(self):
        return 'p*' + repr(object.__getattribute__(self, '_get_proxy_target')())
    def __isinstance__(self, t):
        return isinstance(object.__getattribute__(self, '_get_proxy_target')(), t)

    #
    # factories
    #
    _special_names = [
        '__abs__', '__add__', '__and__', '__call__', '__cmp__', '__coerce__',
        '__contains__', '__delitem__', '__delslice__', '__div__', '__divmod__',
        '__eq__', '__float__', '__floordiv__', '__ge__', '__getitem__',
        '__getslice__', '__gt__', '__hash__', '__hex__', '__iadd__', '__iand__',
        '__idiv__', '__idivmod__', '__ifloordiv__', '__ilshift__', '__imod__',
        '__imul__', '__int__', '__invert__', '__ior__', '__ipow__', '__irshift__',
        '__isub__', '__iter__', '__itruediv__', '__ixor__', '__le__', '__len__',
        '__long__', '__lshift__', '__lt__', '__mod__', '__mul__', '__ne__',
        '__neg__', '__oct__', '__or__', '__pos__', '__pow__', '__radd__',
        '__rand__', '__rdiv__', '__rdivmod__', '__reduce__', '__reduce_ex__',
        '__repr__', '__reversed__', '__rfloorfiv__', '__rlshift__', '__rmod__',
        '__rmul__', '__ror__', '__rpow__', '__rrshift__', '__rshift__', '__rsub__',
        '__rtruediv__', '__rxor__', '__setitem__', '__setslice__', '__sub__',
        '__truediv__', '__xor__', 'next',
        '__enter__', '__exit__'
    ]

    @classmethod
    def _create_class_proxy(cls, theclass):
        """creates a proxy for the given class"""

        def make_method(name):
            def method(self, *args, **kw):
                return getattr(object.__getattribute__(self, '_get_proxy_target')(), name)(*args, **kw)
            return method

        namespace = {}
        for name in cls._special_names:
            if hasattr(theclass, name) and not hasattr(cls, name):
                namespace[name] = make_method(name)
        return type("%s(%s)" % (cls.__name__, theclass.__name__), (cls,), namespace)

    def __new__(cls, obj, *args, **kwargs):
        """
        creates an proxy instance referencing `obj`. (obj, *args, **kwargs) are
        passed to this class' __init__, so deriving classes can define an 
        __init__ method of their own.
        note: _class_proxy_cache is unique per deriving class (each deriving
        class must hold its own cache)
        """
        try:
            cache = cls.__dict__["_class_proxy_cache"]
        except KeyError:
            cls._class_proxy_cache = cache = {}
        try:
            theclass = cache[obj.__class__]
        except KeyError:
            cache[obj.__class__] = theclass = cls._create_class_proxy(obj.__class__)
        ins = object.__new__(theclass)
        return ins
