"""
Defines classes for various levels of game objects and their properties.
"""
# (c) Leo Koppel 2014 

import copy
import re
import jinja2

import notea
import notea.util as util
from notea.util import EngineError
import notea.thingproxy as thingproxy

# set up logging
import logging
logger = logging.getLogger(__name__)

# Set up jinja2 environment, and syntax for templated properties
template_env = jinja2.Environment(block_start_string='[', block_end_string=']',
                                  variable_start_string='{', variable_end_string='}',
                                  comment_start_string='/*', comment_end_string='*/',
                                  lstrip_blocks=True)

class GameObject(object):
    """ An object with a Game reference """

    def __init__(self, game=None):
        super(GameObject, self).__init__()
        object.__setattr__(self, '_game', game or util._current_game)
        self._templates = {} # dict to store templates for TemplateProperties
        self._placeholders = {} # dict for PlaceheldProperties

    def _get_thing_by_uid(self, uid):
        return self._game.current_session._get_thing_by_uid(uid)

    def __getstate__(self):
        """
        Pickle the state, excluding the game reference
        """

        state = dict(self.__dict__)
        try:
            del state['_game']
        except KeyError:
            pass
        return state

    def __setstate__(self, d):
        self.__dict__.update(d)
        self._game = util._current_game


class TemplateProperty(object):
    """
    A property stored as a jinja2 template, meant to be printed in-game
    """

    def __init__(self, name, dedent=False):
        super(TemplateProperty, self).__init__()
        self.name = name
        self.dedent = dedent

    def __get__(self, obj, objtype):
        if obj is None:
            return self
        def thing_by_name(name):
            try:
                return obj._game.current_session._get_thing_by_name(name)
            except EngineError:
                return None
        keywords = {'obj'  : obj,
                    'T'     : thing_by_name,
                    'Thing' : thing_by_name,
                    'thing' : thing_by_name }
        try:
            return obj._templates[self.name].render(keywords)
        except KeyError:
            return obj._thingref._templates[self.name].render(keywords)

    def __set__(self, obj, val):
        val = val or ''
        # Kludgy replace of {self} -> {obj} to get around jinja2's special 'self' variable
        val = re.sub(r'({\s?)self(\W*?.*?})', r'\1obj\2', val)
        if self.dedent:
            # Remove repeated spaces allowing indentation in the argument
            val = util.dedent(val)
        obj._templates[self.name] = template_env.from_string(val)
        # Store the string as well, for pickling
        obj._templates[self.name]._orig_string = val


class PlaceheldProperty(object):
    """
    A data descriptor that stores a placeholder (currently _uid)
    but takes and returns Things
    Must be applied to a GameObject
    """

    def __init__(self, name):
        super(PlaceheldProperty, self).__init__()
        self.name = name

    def __get__(self, obj, objtype):
        if obj is None:
            return self
        try:
            uid = obj._placeholders[self.name]
        except KeyError:
            return obj._thingref._placeholders[self.name]
        
        return uid and obj._get_thing_by_uid(uid)

    def __set__(self, obj, val):
        obj._placeholders[self.name] = val and val._uid
        
    def __copy__(self):
        c = type(self)()
        c.__dict__.update(self.__dict__)
        raise Exception(self)


class BaseThing(GameObject):
    """
    An object bound to a game. A flyweight copy of it is given to each Session and saved/restored.
    """
    __metaclass__ = thingproxy.ProxiableMeta
        
    def __init__(self, game=None, *args, **kwargs):
        super(BaseThing, self).__init__(game, *args, **kwargs)
        self._thingref = None

    def __copy__(self):
        """
        Return a "flyweight" reference to this Thing. This is an object of the
        same class (same methods) with an uninitialized dict referring to this
        instance.
        """
        try:
            return self._thingref.__copy__()
        except AttributeError: # either no _thingref or _thingref == None
            t = BaseThing.__new__(self.__class__)
            t._thingref = self
            t._templates = {}
            t._placeholders = copy.copy(self._placeholders)
            for k, v  in self.__dict__.iteritems():
                if isinstance(v, PlaceheldSet) or isinstance(v, PlaceheldProperty):
                    t.__dict__[k] = copy.copy(v)
            return t

    def __getattr__(self, name):
        try:
            return getattr(self._thingref, name)
        except (KeyError, AttributeError):
            raise AttributeError("'%s' object has no attribute '%s'" % (self.__class__.__name__, name))

    def __getstate__(self):
        state = super(BaseThing, self).__getstate__()
        # Don't pickle referenced things
        try:
            state['_thingref_uid'] = self._thingref._uid
            del state['_thingref']
        except AttributeError:
            pass
        # Pickle only the string (hand-set by us) for jinja2 templates
        if state['_templates']:
            state['_template_strings'] = {}
            for k,v in state['_templates'].iteritems():
                state['_template_strings'][k] = v._orig_string
            del state['_templates']
                
        return state

    def __setstate__(self, d):
        super(BaseThing, self).__setstate__(d)
        try:
            d['_thingref_uid']
        except KeyError:
            pass
        else:
            self._thingref = self._game._base_session._get_thing_by_uid(d['_thingref_uid'])
            del self._thingref_uid
        # Restore templates by going though property setter
        if '_template_strings' in d:
            self._templates = {}
            for k,v in d['_template_strings'].iteritems():
                setattr(self, k, v)
            del self._template_strings

    def __eq__(self, other):
        """
        Test if objects refer to the same in-game thing,
        not that the object attributes are actually equal
        """
        try:
            return self._uid == other._uid
        except AttributeError:
            return False
    def __ne__(self, other):
        return not self == other

    def __del__(self):
        if self._thingref:
            del self._thingref

    def __str__(self):
        return "{0}{2}('{1}')".format(self._uid[0], self._uid[1], '*' if self._thingref else '')

    def __repr__(self):
        try:
            return '{} at {}'.format(str(self), hex(id(self)))
        except:
            return super(BaseThing, self).__repr__()

class MountableThing(object):
    """
    Mixin which allows a thing to be "mounted" (or stood on, or sat in, etc) by the PC
    """
        
    def mountable(self, mount_action, dismount_action=None, reachable_things=[], sticky=False, sticky_string=None, exit_string=None, *args, **kwargs):
        """
        action: the verb, e.g. "sit"
        prep: the preposition, e.g. "on"
        """
        self.mountable = True
        self.sticky = sticky # whether the PC can get out of the position at will
        self.sticky_string = sticky_string or "You can't."
        self.exit_string = exit_string or "You stand."
        
        if not isinstance(mount_action, util.NonStringIterable):
            mount_action = [mount_action]
        if not isinstance(dismount_action, util.NonStringIterable):
            dismount_action = [dismount_action] if dismount_action else []
 
        if any(len(x.split()) != 2 for x in mount_action):
            raise EngineError('Provide both a verb and preposition.')
        
        self.prep = mount_action[0].split()[1]
                     
        # make a 'get on'/'get in', etc default handler
        for x in list(mount_action):
            words = x.split()
            if 'get' != words[0]: 
                mount_action.append('get '+ words[1])
            try:
                dismount_prep = self._game.get_opposite(words[1])
                if words in ['out']:
                    dismount_prep += ' of'
                if 'get' != words[0]:
                    dismount_action.append('get '+ dismount_prep)
            except IndexError:
                pass
        
        # set dismount prep for default message ("you'll have to get off the chair first")
        try:
            self.dismount_prep = dismount_action[0].split()[1]
        except IndexError:
            raise EngineError('Could not automatically find dismount_action for {}. Please provide one.').fornat(mount_action)
 
        
        
        for x in list(dismount_action):
            if 'get' != x.split()[0]: 
                dismount_action.append('get '+ x.split()[1])
        
        if not(dismount_action):
            dismount_action.append('get '+ self.dismount_prep)

        @self._game.on(mount_action, self, overwrite=True)
        def handler(t):
            t._game.pc.position = t
            t._game.pc.position_prep = t.prep
            t._game.pc.position_reachable_things = PlaceheldSet(reachable_things + [t])
            t._game.narrate('You are now {} {}.'.format(t.prep, t.the_str))
        
        @self._game.on(dismount_action, self, overwrite=True)
        def dismount_handler():
            self.try_exit()
    
    on_try_exit = util.replace_decorator('try_exit')
    
    def try_exit(self):
        """ If the PC is able to get out of the position, do it """
        if self.sticky:
            self._game.narrate(self.sticky_string)
        else:
            self._game.pc.set_position(None)
            self._game.narrate(self.exit_string)
        
            
    
class Thing(BaseThing, MountableThing):
    """
    A Thing is a game object with a name and location
    """

    # default strings
    # (define here to avoid saving unless they're changed)
    string_get = 'Gotten.'
    string_failed_get = "You can't be serious."
    string_drop = 'Dropped.'
    string_too_far = "You can't reach it."

    def __init__(self, name, description=None, location=None, container=False,
                 count=1, synonyms=None, a_str=None, the_str=None, game=None, 
                 *args, **kwargs):
        super(Thing, self).__init__(game, *args, **kwargs)

        synonyms = synonyms or []
        if isinstance(name, list):
            synonyms.extend(name[1:])
            self.name = name[0]
        else:
            self.name = name

        self.synonyms = frozenset(synonyms)

        self._game.current_session.bind(self)

        self.location = location or self._game.current_session._current_location
        if self.location: self.location.inventory.add(self)

        if container:
            self.inventory = Inventory()

        self.count = count

        self.a_str = a_str or util.inflect.a(util.inflect.plural(self.name, self.count), self.count) # eg "an owl" or "owls"
        self.the_str = the_str or "the {self.name}"
        self.description = description or "You see nothing special about {self.the_str}."

        self.gettable = False # whether it can be picked up
        self.standout = False # whether it is emphasized in the room description
        self.always_visible = False
        self.moved = False # whether it moved from initial location (even if put back)

    location  = PlaceheldProperty('location')
    a_str = TemplateProperty('a_str')
    the_str = TemplateProperty('the_str')
    description = TemplateProperty('description', dedent=True)
    
    @property
    def reachable(self):
        if self._game.pc.position and self._game.pc.position_reachable_things is not None:
            if self not in self._game.pc.position_reachable_things:
                return False
        return True

    def __unicode__(self):
        # used by templates
        return unicode(self.name)

    def on(self, action, limit=None):
        """
        Shortcut to add a one-argument action for a Thing instance
        """
        return self._game.on(action=action, targets=self, limit=limit)

    def do(self, action):
        """
        Shortcut to call an action for this target
        """
        action, targets = notea.actions.form_action_targets([action], [notea.actions.TargetPair(None, self)])[0]
        return self._game.actions[action].do(targets)

    def place(self, new_location):
        """
        Move the thing somewhere else Note this does only what is necessary. If
        the thing is a player, the enter() method on the place will not be
        called here.
        """
        try:
            self.location.inventory.remove(self)
        except (KeyError, AttributeError):
            pass
        if self.location != None:
            self.moved = True
        self.location = new_location
        self.location.inventory.add(self)

    def get(self):
        """
        Called when player tries to take it.
        Thing subclasses can override this, or change gettable.
        """
        if not self.reachable:
            self._game.narrate(self.string_too_far)
        elif self.gettable:
            self.place(self._game.pc)
            self._game.narrate(self.string_get)
        else:
            self._game.narrate(self.string_failed_get)

    def drop(self):
        """
        Called when player tries to drop
        (caller should check if in inventory already)
        """
        self.place(self._game.pc.location)
        self._game.narrate(self.string_drop)

    def examine(self):
        self._game.narrate(self.description)


    @property
    def visible(self):
        """
        Called to determine if Thing is accessible in current situation.
        (i.e., whether actions work or the game says "you see no *** here!")
        """
        return (self.location == self._game.pc.location or
                self.location == self._game.pc or
                self.always_visible == True)
        
        
    def __enter__(self):
        """ Allow using 'with thing' to automatically place items in it's inventory """
        self._game.current_session._current_location = self
        return self
    def __exit__(self, type, value, tb):
        if self._game.current_session._current_location == self:
            self._game.current_session._current_location = None


class AllThingList(list):
    """
    A target representing "all", which also serves as list
    This requires parser and step_game cooperation
    """
    pass

class ThingList(object):
    """
    A target representing a list of things, for use in action handlers'
    TargetPairs.
    
    This class is needed to allow actions to have an unlimited number of
    targets. E.g., the standard:
    
        @game.on('drop', TargetPair(None, ThingList(Item))) def drop(game,
        items): ...
    
    would allow the 'drop' action to handle any list of items (separated with
    commas, conjunctions, etc. as defined in the parser module).
    
    Note: for the case of a limited list of items, a sequence of TargetPairs
    can be used. E.g.:
        @game.on('combine', TargetPair(None, Item), TargetPair(None, Item))
            
    """

    def __init__(self, t):
        self.type = t

    def __eq__(self, comparison_list):
        try:
            return all(isinstance(p, self.type) for p in comparison_list)
        except TypeError: # not iterable
            return False

    def __ne__(self, other):
        return not self == other

class Item(Thing):
    """
    An item
    """
    string_failed_get = "That's not important; leave it alone."
    def __init__(self, *args, **kwargs):
        super(Item, self).__init__(*args, **kwargs)
        self.gettable = True
        self.standout = True

class BackgroundItem(Thing):
    """
    A non-interactive item
    """
    pass

class Container(Item):
    """
    A thing you can put other things in
    """

    @property
    def contents_description(self):
        """ Return a description of notable things lying around in the room """
        return '  \n'.join("There {} {} here.{}".format(util.inflect.plural_verb('is', item.count),
                                                      item.a_str,
                                                      ' (outside {})'.format(self._game.pc.position.the_str) if self._game.pc.position else ''
                                                      )
                         for item in self.inventory if (item.gettable and item.moved) or item.standout)


class Character(Thing):
    """ A character """
    def __init__(self, *args, **kwargs):
        super(Character, self).__init__(*args, **kwargs)
        self.inventory = Inventory()
        self.set_position(None)
        
        
    def set_position(self, position=None, prep=None, action=None, reachable_things=None):
        self.position = position
        self.position_prep = prep
        self.position_action = action
        self.position_reachable_things = reachable_things
            

    def converse(self, msg, clear_responses=True):
        """ Shortcut to say something"""
        self._game.dialogue(self, msg)

    def dont_understand(self):
        self.game.narrate("%s doesn't seem to understand." % self.the_str)

class PlayerCharacter(Character):
    """ A PC """
    def __init__(self, name, location=None):
        super(PlayerCharacter, self).__init__(name, location,
                                              synonyms=['self', 'me', 'myself', 'i'],
                                              the_str='yourself',
                                              a_str='you')
        # as opposed to location, position refers to position within the room 
        # e.g. on a chair
        
    position = PlaceheldProperty('position')

class Room(Thing):
    """
    An area which can contain things
    """

    _desc_thing_re = re.compile(r'<\s*[\'\"]?([\s\w]+)[\'\"]?\s*>')

    def __init__(self, name, description=None, connections={}):
        """
        Initialize a room and connections, given as a dict of 
        dir:target keys. e.g.:
            Room('Corridor', {'n':street})
        means the corridor is SOUTH of the street.
        
        These connections go both ways.
        """
        super(Room, self).__init__(name)

        self.inventory = Inventory()
        self.connections = {d.name:Connection(None) for d in self._game.directions}
        self.visited = False
        self.location = self

        for direction, target in connections.iteritems():
            self.connect(target, direction, both_ways=True)

        if description:
            # For room descriptions only, use the <thing> syntax to create generic non-interactive things
            for name in self._desc_thing_re.findall(description):
                BackgroundItem(name, location=self)
            description = self._desc_thing_re.sub(r'\1', description)
            self.description = description


    def __contains__(self, item):
        """ Shortcut to checking inventory membership """
        return item in self.inventory
    

    @property
    def characters(self):
        """ Return list of present characters """
        return [m for m in self.inventory if isinstance(m, Character)]

    @property
    def contents_description(self):
        """ Return a description of notable things lying around in the room """
        return '  \n'.join("There {} {} here.{}".format(util.inflect.plural_verb('is', item.count),
                                                      item.a_str,
                                                      ' (outside {})'.format(self._game.pc.position.the_str) if self._game.pc.position else ''
                                                      )
                         for item in self.inventory if (item.gettable and item.moved) or item.standout)

    def examine(self):
        if self._game.pc.position:
            pos_desc = ', {} {}'.format(getattr(self._game.pc, 'position_prep', ''),
                                       self._game.pc.position.the_str)
        else:
            pos_desc = ''
        self._game.narrate(self.name + pos_desc, '\n')
        self._game.narrate(self.description, '\n')
        self._game.narrate(self.contents_description)

    def enter(self):
        """
        Should be called when user enters the room through a connection
        Traditionally narrates the description (depending on verbosity mode)
        """
        v = self._game.current_session.verbosity

        self._game.narrate(self.name, '\n')

        if v == 'verbose' or (v == 'brief' and not self.visited):
            self._game.narrate(self.description, '\n')

        if not (v == 'superbrief' and self.visited):
            self._game.narrate(self.contents_description)

        self.visited = True


    def connect(self, target, direction, both_ways=False):
        """ Connect a room to another """

        # Get dict key from given (e.g. 'n' to 'north')
        try:
            dir_obj = next(d for d in self._game.directions if direction in self._game.directions[d])
        except StopIteration:
            raise util.EngineError("Invalid direction: '{}'".format(direction))
        [d for d in self._game.directions if direction in self._game.directions[d]][0]
        direction = dir_obj.name
        try:
            if self.connections[direction].end:
                logger.info("Overwriting an existing connection to {}! This may not be desired.".format(self.connections[direction].end))
            self.connections[direction] = Connection(target)
            logger.debug("Room %s connected %s to %s" % (self.name, direction, target.name))
        except KeyError:
            # maybe the author tried giving something else in game.directions, like 'back'
            raise util.EngineError("Connect direction must be one of {}".format(self.connections.keys()))

        if both_ways:
            if dir_obj.opposite:
                target.connect(self, dir_obj.opposite, both_ways=False)
            else:
                raise util.EngineError("Can't automatically make two-way connection for direction '{}'".format(direction.name))

    connect_both = lambda self, t, d: self.connect(t, d, True)


class Direction(object):
    """ Use as a target for compass directions """
    def __init__(self, name, opposite=None):
        self.name = name
        self.opposite = opposite
        self.visible = True



class Connection(BaseThing):
    """
    unidirectional passage between one Room and another
    """

    # default strings
    string_impassable = "You can't go that way."

    def __init__(self, end):
        super(Connection, self).__init__()
        self.end = end
        self.passable = True


    def __str__(self):
        return "Connection(end=%s)" % self.end

    def follow(self):
        """
        Called when user tries to follow the path. Can be overridden.
        """

        if self.end and self.passable:
            self._game.pc.place(self.end)
            self.end.enter()
        else:
            self._game.narrate(self.string_impassable)

class PlaceheldSet(GameObject):
    """ A set used to store BaseThings by uid """

    def __init__(self, contents=[], game=None):
        super(PlaceheldSet, self).__init__(game)
        self._set = set(x._uid for x in contents)

    def names(self):
        return [x.name for x in self]

    def add(self, x):
        return self._set.add(x._uid)

    def remove(self, x):
        return self._set.remove(x._uid)

    def pop(self):
        return self._get_thing_by_uid(self._set.pop())

    def update(self, other):
        return self._set.update(x._uid for x in other)

    def __contains__(self, item):
        """ Membership test which allows Things, names, or uids """
        if isinstance(item, basestring):
            # Check for name
            return item in self.names()
        elif isinstance(item, tuple):
            # Check for uid
            return item in self._set
        else:
            # Check for Thing
            return item._uid in self._set

    def __iter__(self):
        return (self._get_thing_by_uid(x) for x in self._set)

    def __len__(self):
        return len(self._set)

    def __eq__(self, other):
        # Allow comparison with both PlaceheldSets and normal sets
        try:
            return self._game == other._game and self._set == other._set
        except AttributeError:
            return self._set == other
    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        return '{}({})'.format(self.__class__.__name__, [x for x in self._set])

    def __copy__(self):
        c = type(self)()
        c._set = copy.copy(self._set)
        return c

class Inventory(PlaceheldSet):
    """ A set used to store Things """
    pass


