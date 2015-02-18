"""
Defines actions, handlers, and their lookup methods
"""
# (c) Leo Koppel 2014

import collections
import inspect
import copy

import notea
import notea.things as things
import notea.util as util
from notea.util import EngineError, AmbiguityError

# set up logging
import logging
logger = logging.getLogger(__name__)

class TargetPair(object):
    """p
    A combination of a preposition and a noun target
    Currently simply wraps namedtuple
    Replacement for earlier (prep, target) tuples
    """
    def __init__(self, prep=None, nouns=util.sentinel):
        self.prep = prep
        if nouns is util.sentinel:
            self.nouns = []
        else:
            self.nouns = nouns

    def __str__(self):
        return "TargetPair(%s, %s)" % (self.prep, self.nouns)
    def __repr__(self):
        return '{} at {}'.format(str(self), hex(id(self)))

    def __eq__(self, other):
        try:
            return (self.prep == other.prep and
                    (self.nouns == other.nouns or (not self.nouns and not other.nouns)))
        except AttributeError:
            return False
    def __ne__(self, other):
        return not self == other

    def __nonzero__(self):
        return (bool(self.prep) or bool(self.nouns))

    def __hash__(self):
        try:
            return hash(self.prep) ^ hash(self.nouns)
        except TypeError:
            return reduce(lambda x, y: x ^ y, (hash(n) for n in self.nouns), hash(self.prep))

AnyTarget = (TargetPair('__anytarget__'),)

def conform_target_input(targets):
    """
    Accept targets in various forms and convert them into a tuple of tuples.
    """
    # Allow single TargetPair
    if isinstance(targets, TargetPair):
        targets = (targets,)

    # Allow a single tuples; convert to TargetPair
    elif (isinstance(targets, tuple) and
        not(isinstance(targets[0], tuple) or isinstance(targets[0], TargetPair))):
        targets = tuple([TargetPair(targets[0], targets[1])])

    # Allow a tuple of tuples; convert to tuple of TargetPairs
    elif isinstance(targets, tuple) and all([isinstance(t, tuple) for t in targets]):
        targets = tuple([TargetPair(t[0], t[1]) for t in targets])

    # Allow noun-only targets -- turn into tuple with 'None' preposition
    elif not isinstance(targets, util.NonStringIterable):
        targets = (TargetPair(None, targets),)

    return targets

class Action(things.GameObject):
    """
    A verb that is valid in the game as a special game command or a way to
    interact with Things.
    
    Actions are organized "top-down", with the notea having a dict of actions,
    each having handlers for applicable targets (as opposed to each Thing having
    a list of applicable actions).
    
    The tree is as follows:
    Game has a dict { 'verb': Action }
    Action has a dict of tuples { (prep, taget, [prep, target...]) : Handler }
    
    It is also possible for a handler to apply to n things: for example, "take
    leaf, pinecone, rock". In that case the target should be a ThingList. 
    
    prep can be one of the prepositions in the parser module, or None, meaning a
    direct relationship. target is a Thing instance or subclass. The
    default_prep property is used if a handler for a preposition is not defined.
    A (None, None) tuple implies (None, self._game).
    
    In order to be called by the parser a Handler must match in both preposition
    and target, always matching preposition first. See examples in do().    
    
    """

    Default = object()

    def __init__(self, name, default_prep=None, groups=None, interrogative=None, game=None):
        super(Action, self).__init__(game)

        if not name.isalpha():
            raise EngineError('Action names must be alphabetic.')

        self.name = name
        self.default_prep = default_prep
        self.handlers = collections.defaultdict(list)
        self.ambiguity_filter = None

        # allow leaving out the [] for a single group
        if isinstance(groups, basestring):
            groups = [groups]
        elif not groups:
            groups = []
        self.groups = ['all'] + groups

        self.interrogative = interrogative or 'What do you want to {action}?'

    def add_handler(self, targets, h, overwrite=False):
        """
        Add a handler for a tuple of (prep, target) tuples
        """

        logger.debug("Adding %s handler for target %s" % (self, targets))

        # Need action list to be an n-tuple of Target Pairs
        targets = conform_target_input(targets)

        if not isinstance(targets[0], TargetPair):
            raise EngineError("Given argument %s is not a tuple of TargetPairs" % targets)

        if overwrite:
            self.handlers[targets] = []
        self.handlers[targets].append(h)

    def add_multiple_handler(self, targets, h, all_filter=None, list_handler=None, overwrite=False):
        """
        Add a handlers targeting multiple things
        """
        m_targets = copy.deepcopy(targets)

                    # keep track of index of the new ThingList target, in the args passed to the handler
        m_pair = None
        hargs_index = -1
        # convert last noun in targets to a ThingList target
        for k in m_targets:
            if k.nouns:
                hargs_index += 1
                m_pair = k
                if isinstance(k.nouns, things.ThingList):
                    raise EngineError("Cannot have ThingList in targets with allow_multiple set.")

        try:
            m_pair.nouns
        except AttributeError:
            raise EngineError("allow_multiple set but no nouns in targets")

        logger.debug("Creating multiple handler using nouns %s" % m_pair.nouns)

        m_pair.nouns = things.ThingList(m_pair.nouns)


        # add handler for list
        def default_multiple_handler(*args):
            logger.debug("starting default multiple handler for %s:%s" % (self.name, h))
            thinglist = list(args[hargs_index])
            args = list(args)

            for item in thinglist:
                # call the handler for a single Thing
                self._game.narrate(item.the_str.capitalize() + ": ", end='')
                args[hargs_index] = item
                h(*args)
            return

        # Set default filter if none given
        all_filter = all_filter or (lambda thing: thing.gettable)
        list_handler = list_handler or default_multiple_handler

        def m_pre_handler(*args):
            logger.debug("starting multiple pre-handler for %s:%s" % (self.name, h))
            thinglist = args[hargs_index]
            args = list(args)

            if isinstance(thinglist, things.AllThingList):
                # an "all" command was given -- filter it now
                thinglist[:] = filter(all_filter, thinglist)

            # Call the actual handler
            list_handler(*args)

        # Finally, create the extra handler for list targets
        m_h = Handler(m_pre_handler, h.limit, pre_handler=None)
        self.add_handler(tuple(m_targets), m_h)

    def find_handlers(self, targets, visited_actions=None):
        """
        Find the correct handlers, if there are any, for a given sequence of
        TargetPairs. Otherwise, return None.
        
        See do() for more info.
        
        This is called recursively for each Action group the current Action
        belongs to, and visited_groups is a list of already visited groups to avoid
        adding the same handlers twice (in case of groups belonging to groups).
        """

        res = []
        visited_actions = visited_actions or []

        # First, check if there's a handler for an action group
        # This uses the special groups ActionDict
        visited_actions.append(self)
        for g in self.groups:
            try:
                group_action = self._game.action_groups[g]
                if group_action not in visited_actions:
                    # Recurse
                    r = group_action.find_handlers(targets, visited_actions)
                    if r:
                        res.extend(r)
            except KeyError: # group is not in action_groups dict
                pass

        # Consider only the handlers of the same number of pairs as the input, or the special 'any' target
        all_possible = [h for h in self.handlers if len(h) >= len(targets) or h is AnyTarget]

        # consider one pair at a time
        for i, pair in enumerate(targets):

            if not all_possible:
                break

            pair = targets[i]

            # Narrow down possibilities -- must match target
            try:
                nouns_uid = pair.nouns._uid
            except AttributeError:
                nouns_uid = pair.nouns

            possible = [h for h in all_possible if h is AnyTarget or (h[i].nouns == nouns_uid or not h[i].nouns and not pair.nouns)] # check exact match
            if not possible:
                # If no exact match, proceed up class parents (using MRO)
                for cls in pair.nouns.__class__.__mro__:
                    possible = [h for h in all_possible if h[i].nouns == cls]
                    if possible:
                        break

            all_possible = possible

            # Look for possible handlers which match preposition
            possible = [h for h in all_possible if h is AnyTarget or h[i].prep == pair.prep]
            if not possible and len(targets) == 1:
                possible = list(all_possible)
                if len(possible) > 1 and isinstance(targets[0].nouns, things.BaseThing):
                    # ambiguity: e.g. given "look desk" when "look at desk" and "look in desk" are options
                    s = "Do you want to %s?" % util.inflect.join([self.name + ' ' + (h[0].prep.upper() if h[0].prep else '')
                        + ' ' + targets[0].nouns.the_str for h in possible], conj='or')
                    raise AmbiguityError(s, notea.parser.Ambiguity(self.name, targets, 'IN', 0))


            all_possible = possible

        # should now have a list of handlers
        res.extend(h for x in all_possible for h in self.handlers[x] if h.enabled)

        logger.debug("Found handlers {} for {}".format(res, all_possible))
        return res


    def do(self, pairs):
        """
        Call the most specific handler available for the target, given args 'pairs' as
        a list of tuples [(prep, taget), (prep, target)]
        Realistically there will be one or two pairs.
        
        Match preposition before target.
        More than one prep-target pair requires the first to match before moving
        to the next.
        
        E.g. input is "look under table"
        action 'look' has handlers for (None, None), ('under', Thing), and ('at', Table)
        the handler called will be ('under', Thing).
        
        E.g. input is "look table"
        action 'look' has handlers for (None, None), ('under', Thing), and ('at', Table)
        and default=='at'
        the handler called will be ('at', Table). 
        
        E.g. input is "look behind table"
        action 'look' has handlers for (None, None), ('under', Thing), and ('at', Table)
        and default=='at'
        This will cause a ParseError. Normally though, there would be some kind of
        ineffective action defined at the Thing level for all prepositions.
        
        """

        # Accept various inputs and convert them to a list of tuples
        pairs = conform_target_input(pairs)

        # Find the correct handler list
        handlers = self.find_handlers(pairs)

        if not handlers:
            raise EngineError("No handler for %s" % pairs)
        # Call handlers. Stop on true response value
        for h in handlers:
            if h.call_with_targets(pairs):
                break

    def __str__(self):
        return "Action('{}')".format(self.name)
    def __repr__(self):
        return '{} at {}'.format(str(self), hex(id(self)))


class Handler(object):
    """
    A function wrapper called on an action
    Handles the number of arguments the handler should take
    """

    def __init__(self, func, limit=None, pre_handler=util.sentinel):
        self.func = func
        self.limit = limit
        self.enabled = True
        self.pre_handler = pre_handler if pre_handler is not util.sentinel else self.default_pre_handler
        # get arg count to give AnyAction handlers the option of taking no args
        # just ignore if not a normal function
        try:
            spec = inspect.getargspec(func)
            self.argcount = None if spec.varargs else len(spec.args)
        except TypeError:
            self.argcount = None

    def disable(self):
        self.enabled = False
    def enable(self):
        self.enabled = True

    def __call__(self, *args, **kwargs):
        if(self.limit > 0 or self.limit == None):
            logger.debug('Calling handler {}({})'.format(self.func, args))

            if(self.limit != None):
                self.limit -= 1

            # pre-handler can cancel handler by returning true
            if self.pre_handler and self.pre_handler(*args):
                return True
            return self.func(*args[:self.argcount], **kwargs)

        if self.limit == 0:
            del(self)

    def call_with_targets(self, pairs):
        """ Call with TargetPairs as arguments """
        hargs = [k.nouns for k in pairs if k.nouns]
        return self.__call__(*hargs)

    def default_pre_handler(self, *things):
        """
        By default, this is called before the handler function for each action
        The purpose is to "filter" Things which are too far to reach, etc.
        """
        for x in things:
            try:
                if not x.reachable:
                    x._game.narrate("You can't reach it.")
                    return True
            except AttributeError:
                try:
                    for y in x:
                        if not y.reachable:
                            y._game.narrate("You can't reach it.")
                            return True
                except TypeError:
                    pass
        return None


    def __str__(self):
        return "Handler('{}')".format(self.func)
    def __repr__(self):
        return '{} at {}'.format(str(self), hex(id(self)))


class ActionDict(dict):
    """ Maps action strings to a set of associated handlers """
    pass


def form_action_targets(action, targets):
    """
    Validate actions and take prepositions from two-word actions
    Then add each pair to form an (action_word,targets) list
    """
    action_targets = []
    for x in action:
        words = x.split()
        wc = len(words)
        if wc == 1:
            action_targets.append((x, targets))
        elif wc == 2:
            # two words given -- put preposition into target pairs (unless it has one already!)
            if targets[0].prep:
                raise EngineError('Invalid input: two-word action with preposition in target pairs')
            new_targets = copy.deepcopy(targets)
            new_targets[0].prep = words[1]
            action_targets.append((words[0], new_targets))

        else:
            raise EngineError('Actions must be given as one or two words \
            (more complex structures are possible using TargetPairs).')

    return action_targets
