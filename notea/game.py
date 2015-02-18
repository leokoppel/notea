"""
Defines a Game, which is a story with rooms, things, and action handlers, and a
Session, which holds in-progress game state.
"""
# (c) Leo Koppel 2014

import os, sys
import time, datetime
import copy
import greenlet
import shelve
import inspect

import notea.ui
import notea.parser as parser
import notea.actions as actions
import notea.util as util
import notea.things as things
import notea.default_actions as default_actions

from notea.actions import Handler, Action, ActionDict, TargetPair
from notea.episode import Episode, Conversation
from notea.things import Thing, PlaceheldSet
from notea.util import EngineError


# set up logging
import logging
logging.basicConfig(format='[%(levelname)-8s] %(name)15s: %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Session(things.GameObject):
    """
    Container for a Game's session variables
    (i.e, those which are saved with saved games
    """

    def __init__(self, game):
        """
        Initialize a new session: a "new game".
        """
        super(Session, self).__init__(game)

        self.register_current_greenlet()

        self.running = False
        self.steps = 0
        self.gametime = datetime.datetime.fromtimestamp(0)
        self.move_minutes = 1
        self.time_passed = False # whether pass_time was called yet this move (instance attribute)

        self.verbosity = 'brief'

        self.points = 0

        # step_game inputs
        self.current_input = None
        self.current_ambiguity = None
        self.last_good_input = None


        self._uids = dict()
        self.things = PlaceheldSet()
        self._current_location = None

        self._live_episodes = []
        self._blocking_episode = None

    pc = things.PlaceheldProperty('pc')


    def bind(self, target, uidstr=None):
        """ Make a uid for the target and register it """


        # Make a unique uid
        # TODO: could use hash for efficiency if it turns out to be necessary;
        # using strings for ease of debugging for now.
        uidstr = uidstr or target.name
        try:
            uid = (uidstr, max(x[1] for x in self._uids if x[0] == uidstr) + 1)
        except ValueError:
            uid = (uidstr, 0)

        target._uid = uid
        self._uids[target._uid] = target

        if isinstance(target, Thing):
            self.things.add(target)
        logger.debug('Bound {} to {}'.format(target._uid, self))

    def _get_thing_by_name(self, name):
        try:
            return next(x for x in self.things if x.name == name)
        except StopIteration:
            raise EngineError("No thing '{}' found".format(name))

    def _get_thing_by_uid(self, uid):
        try:
            return self._uids[uid]
        except KeyError:
            raise EngineError("No thing '{}' found".format(uid))

    def validate_filename(self, filename):
        if filename != os.path.basename(filename):
                return False

        return True

    def save_to_file(self, filename):
        if not self.validate_filename(filename):
            raise EngineError("Invalid filename.")

        savepath = os.path.join(self._game.savedir, filename)

        util.ensure_path_exists(self._game.savedir)
        shelf = shelve.open(savepath, protocol=0)

        shelf['timestamp'] = time.time()
        shelf['session'] = self

        shelf.close()

    def restore_from_file(self, filename):
        if not self.validate_filename(filename):
            raise EngineError("Invalid filename.")

        shelf = shelve.open(os.path.join(self._game.savedir, filename), protocol=0)

        self.__dict__.update(shelf['session'].__dict__)

        shelf.close()

    def __deepcopy__(self, _):
        """ Make a full copy of the session with lightweight Thing references"""
        res = Session.__new__(type(self))

        for k, v in self.__dict__.iteritems():
            setattr(res, k, copy.copy(v))

        res._uids = {copy.copy(x):copy.copy(y) for x, y in self._uids.iteritems()}
        return res

    def get_copy(self):
        return copy.deepcopy(self)

    # Magic session globals -- rely on greenlet.getcurrent()
    # TODO: change
    def register_greenlet(self, gr):
        self._game._greenlet_sessions[gr] = self
    def register_current_greenlet(self):
        self.register_greenlet(greenlet.getcurrent())
    def unregister_current_greenlet(self):
        del self._game._greenlet_sessions[greenlet.getcurrent()]

    def __enter__(self):
        self.register_current_greenlet()
        return self
    def __exit__(self, type, value, tb):
        self.unregister_current_greenlet()

    def add_quest(self, quest):
        self.quests.add(quest)

    def pass_time(self, minutes=1, hours=0):
        """ """
        self.gametime += datetime.timedelta(minutes=minutes, hours=hours)
        _time_passed = True

    def episode_yield(self, episode, steps=None, time=None, resume=None, block=False):
        """
        Called on yield from an Episode greenlet
        Re-schedule the episode to be picked up on a later step
        """
        episode.unschedule()

        # If episode blocks, go right back into it with input.
        # Time doesn't advance for blocking episodes.
        if block:
            self._blocking_episode = episode
            steps = 0
        elif steps != None:
            episode._scheduled_step = self.steps + steps
        elif time != None:
            episode._scheduled_time = self.gametime + time
        elif resume != None:
            episode._scheduled_time = resume
        else:
            # assume one step
            episode._scheduled_step = self.steps + 1

        logger.debug("Scheduled episode %s for step: %s, time:%s, block:%d" % (episode.name, episode._scheduled_step, episode._scheduled_time, block))


    def step_game(self, user_input):
        """
        Run one game "step": take input, parse it, call the correct handler, and
        assign points and time.
        
        This function is called once for every user input, but that may include
        more than one command.
        """

        self._no_move = False
        self.current_input = user_input

        # Go right back into a blocking episode
        if self._blocking_episode:
            e = self._blocking_episode
            try:
                data = e.switch(self.current_input)
                self.episode_yield(e, *data)
            except StopIteration:
                e._dead = True
            self._blocking_episode = None
            return

        # Since parse() is a generator, this line does not raise exceptions
        parser_output = self._game.parser.parse(self.current_input, self, self.current_ambiguity)
        self.current_ambiguity = None

        # Loop through all sentences in input, but discard remaining sentences after a parse error
        try:
            for input_sentence, handlers, targets in parser_output:
                # Truncate the arguments we collected to the needed number (just in case)
                logger.debug("step_game (%d) got parsed input: %s, %s" % (self.steps, handlers, [p.__str__() for p in targets]))

                # Call each handler in the order they were added
                # Break on true return value
                for h in handlers:
                    if h.call_with_targets(targets):
                        break

                # call any episodes due
                for e in self._live_episodes :
                    # exit if an episode is scheduled to block
                    if self._blocking_episode:
                        break

                    if ((e._scheduled_step is not None and e._scheduled_step <= self.steps)
                        or (e._scheduled_time and e._scheduled_time <= self.gametime)):
                        logger.debug("Switching to %s with '%s'" % (repr(e), self.current_input))
                        try:
                            data = e.switch(self.current_input)
                            logger.debug("Got yield from episode %s (%s): %s" % (e.name, hex(id(e)), data))
                            self.episode_yield(e, *data)
                        except StopIteration:
                            e._dead = True

                # Make time pass in the game for a successful move, if a handler didn't already
                if not self._no_move:
                    self.pass_time(self.move_minutes)
                    self.steps += 1

            # Remove dead episodes
            self._live_episodes = [e for e in self._live_episodes if not e._dead]


        except parser.ParseError as e:
            # failed to parse but raised a message for the user
            self._game.output(e.message)

            try: # If AmbiguityError, save data to pass to parser on next step_game call
                self.current_ambiguity = e.ambiguity
            except AttributeError: # not an AmbiguityError
                pass
        else:
            try:
                self.last_good_input = input_sentence
            except UnboundLocalError: # input was empty
                pass



class Game(object):
    """
    The game
    """

    def __init__(self, title, debug=False, proxy_things=True):
        logger.info("Initializing game %s" % title)

        self.title = title
        self.debug = debug
        self.proxy_things = proxy_things

        self.actions = ActionDict()
        self.action_groups = ActionDict()
        self.on_start_handler = None

        # ui not initialized until start(). Use placeholder
        self.ui = SilentUI()

        # Implicitly bind all Things after this to this game
        self.activate()

        self.quests = set()

        # Session globals (TODO: remove?)
        self._base_session = Session(self)

        self.episodes = set()

        # Special Thing for player character
        self._base_session.pc = things.PlayerCharacter("Player", proxy=False)

        # For Americans
        self.dialog = self.dialogue

        # Directions can be used as commands ('north') or as adverbs ('go north')
        # This is an instance variable as an author may want to add more
        # (e.g. 'fore' and 'aft')
        self.directions = util.WordCategory({
                                        things.Direction('north'): {'north', 'n'},
                                        things.Direction('east') : {'east', 'e'},
                                        things.Direction('south'): {'south', 's'},
                                        things.Direction('west') : {'west', 'w'},
                                        things.Direction('ne')   : {'northeast', 'ne'},
                                        things.Direction('nw')   : {'northwest', 'nw'},
                                        things.Direction('se')   : {'southeast', 'se'},
                                        things.Direction('sw')   : {'southwest', 'sw'},
                                        things.Direction('up')   : {'up', 'u'},
                                        things.Direction('down') : {'down', 'd'},
                                        things.Direction('in') : {'in'},
                                        things.Direction('out') : {'out'},
                                        })

        # Set opposite directions for automatic 2-way connections
        self.opposites = {'north':'south', 'east':'west', 'up':'down', 'ne':'sw', 'se':'nw', 'up':'down', 'in':'out', 'on':'off'}
        self._opposites_inv = {v:k for k, v in self.opposites.iteritems()}
        for d in self.directions:
            d.opposite = self.get_opposite(d.name)

        # Verbs that accept directions. Currently needed for parser tagging
        # TODO: special case
        self.direction_verbs = {'go', 'walk', 'run'}
        # Nouns that refer to the current room
        # TODO: special case
        self.room_nouns = {'room', 'area'}


        # Initialize game keywords and default actions
        default_actions.init_keywords(self)
        default_actions.init_actions(self)

        # Directory for save files (under script dir by default)
        self.savedir = os.path.join(os.path.dirname(sys.argv[0]), 'save')

    # Convenience property for special player character Thing
    @property
    def pc(self):
        return self.current_session.pc
    @pc.setter
    def pc(self, value):
        self.current_session.pc = value

    # Magic session globals
    # TODO: change?
    _greenlet_sessions = dict()
    @property
    def current_session(self):
        try:
            return self._greenlet_sessions[greenlet.getcurrent()]
        except KeyError:
            raise EngineError("Current greenlet not registered with game session.")

    def activate(self):
        """
        Switch this game to current
        (all Things initialized after this are implicitly bound to this game)
        """
        util._current_game = self


    def add_action(self, name, synonyms=[], action_dict=None, *args, **kwargs):
        """
        Add an action to those allowed in-game
        """

        if action_dict is None:
            action_dict = self.actions

        if name in action_dict:
            # already in the dict
            return

        logger.debug("Adding new action {} to {}".format(name, action_dict))
        action_dict[name] = Action(name, *args, **kwargs)

        for s in synonyms:
            if s in action_dict:
                raise EngineError("synonym {} already exists in actions dict".format(s))
            action_dict[s] = action_dict[name]


    def on(self, action, targets=None, any_target=False, synonyms=[],
            limit=None, action_dict=None, overwrite=False, pre_handler=None,
            allow_multiple=False, all_filter=None, list_handler=None, **action_kwargs):
        """
        Decorator to set an event handler f to be run when one of the actions in
        action_list is performed on the Thing. This method could be called
        through another which fills in 'target' for the writer.
        
        Return the handler object.

        action:
        A single string naming the action
        
        targets:
        A tuple of TargetPairs. Call the handler if the arg to the action is this.
        This is somewhat liberal in allowed input, and also accepts a tuple of
        tuples, a single Thing, etc., and converts these to TargetPairs.
        
        limit:
        How many times the handler can be called before it's deleted.
        (this is of questionable usefulness)
        
        action_dict:
        The action dict to insert into, if not game.actions
        
        allow_multiple: Set True to allow an action to be used on a list of
        items, or on "all". It can only be applied to handlers with exactly one
        noun-containing TargetPair.
        
        This could also be implemented manually using the ThingList target.(?)
        
        The handler will be applicable to lists of things which are instances
        of the original noun. E.g.
        
            @game.on('take', Item, allow_multiple=True)
            def take_something(game, item): ...
        
        will apply take_something to TargetPair(None, ThingList(Item)), including
        "take all" and "take all ... except" commands.
        
        all_filter:
        If allow_multiple==True, this is a filter expression used when the
        action is used on "all" or "all except ...". It is passed to the
        filter() built-in. E.g. maybe "take all" should only apply to items
        which are gettable. If it's not specified a default filter is used.
        
        list_handler:
        If the regular handler function should not automatically be called for each item
        in a filtered list, this should give a reference to a function taking a list argument.

        """

        # transform input targets into tuple of TargetPairs
        targets = actions.conform_target_input(targets)

        # Turn Thing references into identifiers
        for t in targets:
            try:
                t.nouns = t.nouns._uid
            except AttributeError:
                pass

        if action_dict is None:
            action_dict = self.actions

        # Do some bug-warning
        if not allow_multiple and (all_filter or list_handler):
            raise EngineError("all_filter and list_handler have no effect since allow_multiple was not set to True")

        if all_filter and list_handler:
            raise EngineError("all_filter has no effect if list_handler is given")

        if isinstance(action, util.NonStringIterable):
            # Allow passing list of synonyms only if a single action is given (not a list)
            if synonyms and not all(x.split()[0] == action[0].split()[0] for x in action):
                raise EngineError("Synonyms can only be provided for a single action. Multiple synonyms and multiple actions is ambiguous.")
        else:
            action = [action]

        # Validate actions and take prepositions from two-word actions
        # Then add each pair to an (action_word,targets) list
        action_targets = actions.form_action_targets(action, targets)


        def decorator(f, action_targets=action_targets, all_filter=all_filter, list_handler=list_handler):
            """
            Construct the event handler based on the decorated function f
            Return the same function f -- that function should not be replaced
            """

            # Initialize handler
            h = Handler(f, limit, pre_handler)

            # Handler function must accept an argument for each targetpair with a noun,
            # or none at all
            try:
                expected = len(k for k in action_targets[0][1] if k.nouns)
                given = len(inspect.getargspec(h.func).args)
                if(given != 0 and expected != given):
                    raise EngineError("Handler '{}' takes {} {}; must take {}"
                                      .format(h.func.__name__, given, util.inflect.plural('argument', given), expected))
            except TypeError:
                # Skip the check if handler is not a real function (e.g. an episode)
                pass

            for action, targets in action_targets:
                self.add_action(action, synonyms, action_dict, **action_kwargs)

                # Add to allowed actions dict
                action_dict[action].add_handler(targets, h, overwrite)

                # Add handlers for handling lists of Things
                if allow_multiple:
                    action_dict[action].add_multiple_handler(targets, h, all_filter, list_handler, overwrite)

            return h
        return decorator

    def on_group(self, group, targets=util.sentinel, **kwargs):
        """ Shortcut to set action group handlers """
        if targets is util.sentinel:
            targets = actions.AnyTarget
        return self.on(group, action_dict=self.action_groups, targets=targets, **kwargs)

    def remove_handler(self, f, action_dict=None):
        """ Remove a handler function from all actions """
        _action_dict = action_dict or self.actions
        for a in _action_dict:
            a.discard(f)

    def clear_events(self, action_dict=None, remove_same=False):
        """
        Remove all handlers added with the @on decorator.
        TODO: Remove same
        """
        _action_dict = action_dict or self.actions
        for a in _action_dict:
            a.clear()

    def do(self, action):
        """
        Shortcut to call a game action
        """
        return self.actions[action].do([TargetPair(None, None)])

    # Create decorator to set special startup method
    on_start = util.replace_decorator('on_start_handler')

    # Add an episode
    def episode(self, nosave=False):
        """
        Decorator to add an episode
        """
        def decorator(f):
            e = Episode(f, nosave, self)
            self.episodes.add(e)
            return e
        return decorator

    def conversation(self, nosave=False):
        """
        Decorator to add a conversation
        """
        def decorator(f):
            e = Conversation(f, nosave, self)
            self.episodes.add(e)
            return e
        return decorator



    # UI calls
    def output(self, message, *args, **kwargs):
        self.ui.output(message, *args, **kwargs)

    def narrate(self, message, *args, **kwargs):
        self.ui.narrate(message, *args, **kwargs)

    def dialogue(self, char, message):
        self.ui.dialogue(char.name, message)

    def start(self, startui=True, ui=None, location=None, **ui_kwargs):
        """
        Initialize UI and start taking player input
        """

        logger.info("Starting game %s" % self.title)
        self.parser = parser.Parser(self)
        if location:
            self.pc.location = location
        if not self.pc.location:
            raise EngineError("PC must have location before game start.")
        
        self.current_session.running = True

        if not self.ui or isinstance(self.ui, SilentUI):
            # Initialize a new UI
            new_ui = ui or notea.ui.default_ui
            self.ui = new_ui(self, **ui_kwargs)
            if startui:
                self.ui.start(self.on_start_handler, **ui_kwargs)
        else:
            # UI already initialized
            if startui:
                self.ui.start(self.on_start_handler)



    def stop(self):
        if self.ui:
            self.ui.stop()

    def get_opposite(self, dir_name):
        try:
            return self.opposites[dir_name]
        except KeyError:
            return self._opposites_inv[dir_name]


class SilentUI(object):
    """ Handles UI calls before the game's start """
    def _noop(self, *args, **kwargs):
        return None
    def __getattr__(self, attr):
        return self._noop
    def __setattr__(self, val):
        raise EngineError('UI has not been initialized')




