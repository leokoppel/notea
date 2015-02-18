"""
Defines default game actions and keywords 
"""
# (c) Leo Koppel 2014

import functools

import notea
from notea.actions import ActionDict
import notea.things as things
from notea.things import Thing

# set up logging
import logging
logging.basicConfig(format='[%(levelname)-8s] %(name)15s: %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


def init_keywords(self):

        # Have a separate dict for keywords (one-word special game actions)
        self.keywords = ActionDict()
        def kwd_pre_handler(session):
            """ don't count this step as a 'move' """
            session._no_move = True

        kwd = functools.partial(self.on, targets=notea.Session, action_dict=self.keywords,
                                pre_handler=kwd_pre_handler)

        @kwd('quit')
        def quit_game(session):
            session.running = False

        self.quit = quit_game


        @kwd('save')
        @self.conversation(nosave=True)
        def save(conv, session):
            # Start episode to get filename
            self.narrate("What would you like to call your saved game?")
            resp = yield conv.get_response()
            logger.debug("Saving to file %s" % resp)


            try:
                session.save_to_file(resp)
                self.narrate("Saved.")
            except Exception as e:
                logger.error('Failed to save "%s": %s' % (resp, e.message))
                self.narrate("Sadly, I can't save a game of that name.\nFailed.")
                if self.debug:
                    raise

        @kwd(['restore', 'load'])
        @self.conversation(nosave=True)
        def restore(conv, session):
            self.narrate("Which saved game would you like to restore?")
            resp = yield conv.get_response()

            logger.debug("Restoring from file %s" % resp)
            try:
                session.restore_from_file(resp)
                self.narrate("Restored.")
            except Exception as e:
                logger.error('Failed to load "%s": %s' % (resp, e.message))
                self.narrate("Sadly, I can't open a game of that name.\nFailed.")
                if self.debug:
                    raise


        @kwd('restart')
        def restart(session):
            pass
        @kwd('brief')
        def brief(session):
            self.narrate('Brief descriptions.')
            self.verbosity = 'brief'
        @kwd('superbrief')
        def superbrief(session):
            self.narrate('Superbrief descriptions.')
            self.verbosity = 'superbrief'
        @kwd('verbose')
        def verbose(session):
            self.narrate('Verbose descriptions.')
            self.verbosity = 'verbose'
        @kwd('diagnose')
        def diagnose(session):
            pass

        @kwd('inventory', synonyms=['i'])
        def inventory(session):

            def narrate_contents(inv, indent):
                for item in inv:
                    self.narrate(' ' * indent + item.a_str)
                    try:
                        if item.inv.accessible:
                            self.narrate(' ' * indent + "It looks like %s contains:", item.the_str)
                            narrate_contents(item.inv, indent + 2)
                    except AttributeError:
                        pass

            if not self.pc.inventory:
                self.narrate('You have nothing.')
            else:
                self.narrate('You have:')
                narrate_contents(self.pc.inventory, 2)

        @kwd('time')
        def time(session):
            pass
        @kwd('score')
        def score(session):
            pass
        @kwd('version')
        def version(session):
            pass

def init_actions(self):
        # Default actions

        @self.on_group('all', notea.things.BackgroundItem)
        def leave_it_alone():
            self.narrate("That's not important; leave it alone.")
            return True

        @self.on(['look', 'look around'], None, groups=['sight'], synonyms=['l'])
        def look():
            self.actions['examine'].do(self.pc.location)

        @self.on(['look', 'look at'], Thing)
        def look_at_thing(thing):
            thing.examine()

        @self.on('wait')
        def wait():
            pass

        @self.on('examine', Thing, synonyms=['x'], groups='sight')
        def default_examine(thing):
            self.narrate(thing.description)

        @self.on('examine', things.Room)
        def default_examine_room(room):
            room.examine()

        @self.on('drop', Thing, synonyms=['discard'], allow_multiple=True,
                 all_filter=(lambda k: k.gettable and k in self.pc.inventory))
        def drop(item):
            if item in self.pc.inventory:
                item.drop()
            else:
                self.narrate("You're not holding %s." % item.the_str)


        get_filter = lambda k: k.gettable and k not in self.pc.inventory
        @self.on('get', Thing, synonyms=["take"], allow_multiple=True, all_filter=get_filter, groups=['touch'])
        @self.on('pick', ('up', Thing), allow_multiple=True, all_filter=get_filter, groups=['touch'])
        def try_to_get(item):
            if(item in self.pc.inventory):
                self.narrate("You're already holding %s." % item.the_str)
            else:
                item.get()

        self.actions['get'].ambiguity_filter = functools.partial(filter, lambda t: t.location == self.pc.location)


        @self.on('go', things.Direction, synonyms=list(x for x in self.direction_verbs if x != 'go'),
                 interrogative='Where do you want to {action}?', groups=['movement'])
        def go_in_direction(direction):
            if self.pc.position:
                if self.pc.position.dismount_prep:
                    self.narrate("You'll have to get {} {} first.".format(self.pc.position.dismount_prep, self.pc.position.the_str))
                else:
                    self.narrate("You'll have to move from {} first.").format(self.pc.position.the_str)
            else:
                connection = self.pc.location.connections[direction.name]
                connection.follow()

        @self.on(['stand', 'stand up'], None)
        def stand():
            if self.pc.position and not self.pc.position_action == 'stand':
                self.pc.position.try_exit()
            else:
                self.narrate("You are.")

        @self.on(['sit on', 'stand on', 'climb on'], Thing,
                 interrogative='What do you want to {action} on?')
        def no_climbing(t):
            self.narrate("You can't climb on {}".format(t.the_str))

        @self.on_start()
        def default_on_start():
            """ Default startup method """
            self.do('look')
