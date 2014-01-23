import notea
from notea import Game, Room, Thing, ThingList, Character, PlayerCharacter, Item, TargetPair, Inventory
import unittest
import sys
import io
import collections
from notea.util import EngineError


class TestGame(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.testout = TestOut()
        cls.testin = TestIn()

    def setUp(self):
        print ("===== Setting up test %s  " % self._testMethodName).ljust(100, '=')
        self.testout.truncate(0)
        self.game = Game("Spam", debug=True)
        self.room = Room("a room")
        self.game.pc.place(self.room)

        self.game.start(startui=False, instream=self.testin, outstream=self.testout)
        print ("===== Starting test %s  " % self._testMethodName).ljust(100, '=')


    def tearDown(self):
        del self.game
        print ("===== End test %s  " % self._testMethodName).ljust(100, '=')


    def step_input(self, cmd):
        """ Helper to call step_game with a given input line """
        self.game.current_session.step_game(cmd)

    def compare_objects(self, A, B):
        for k in A.__dict__:
            a = A.__dict__[k]
            b = B.__dict__[k]
            self.assertEqual(a, b, "%s: %s != %s" % (k, a, b))


    def test_game_create(self):
        self.assertEqual(self.game.title, "Spam")

    def test_game_setup(self):
        bedroom = Room("Bedroom")

        self.game.pc.place(bedroom)
        self.assertEqual(self.game.pc.location, bedroom)

        with bedroom:
            lighter = Item("lighter")
            book = Item("book")
        self.assertEqual(lighter.location, bedroom)

        self.step_input("examine room")
        res1 = self.testout.last
        self.step_input('look')
        res2 = self.testout.last
        self.assertEqual(res1, res2)

        desc = "It is a disposable lighter for igniting flames."
        lighter.description = desc
        lighter.do('examine')
        self.assertEqual(desc, self.testout.last)


    def test_action_handlers(self):

        with self.room:
            book = Thing('thick book')
            vase = Thing('priceless vase')
            pen = Thing('pen')

        # simple
        m_1 = "What on earth for?"
        m_2 = "You can eat off your reflection in it."
        self.game.on('polish', Thing)(lambda x: self.game.narrate(m_1))
        self.game.on('polish', vase)(lambda x: self.game.narrate(m_2))
        book.do('polish')
        self.assertEqual(self.testout.last, m_1)
        vase.do('polish')
        self.assertEqual(self.testout.last, m_2)

        # Action groups
        m_3 = "You can't do anything."
        @self.game.on_group('all')
        def some_inconvenient_event():
            self.game.narrate(m_3)
            return True

        vase.do('polish')
        self.assertEqual(self.testout.last, m_3)

        some_inconvenient_event.disable()
        vase.do('polish')
        self.assertEqual(self.testout.last, m_2)

        # Right now group handlers affect all targets, even if they wouldn't apply otherwise.
        @self.game.on('listen', vase)
        def listen(x):
            pass
        self.game.actions['listen'].groups.append('hearing')

        @self.game.on_group('hearing')
        def deafness(*args):
            self.game.narrate('You are too deaf to do that with {}.'.format(notea.util.inflect.join([k.the_str for k in args])))
            return True

        self.step_input('listen to pen with book') # Note targets completely different from handler's
        self.assertEqual(self.testout.last, "You are too deaf to do that with the pen and the thick book.")

        # precedence of first groups
        some_inconvenient_event.enable()
        vase.do('listen')
        self.assertEqual(self.testout.last, m_3)

        # Adding multiple actions with prepositions
        @self.game.on(['annoy', 'tick off'], Character)
        def annoy_handler():
            pass

        @self.game.on(['annoy', 'tick on'], Character)
        def something():
            pass

        self.assertIn('annoy', self.game.actions)
        self.assertIn('tick', self.game.actions)
        self.assertIs(annoy_handler, self.game.actions['annoy'].handlers[(TargetPair(None, Character),)][0])
        self.assertEqual([annoy_handler], self.game.actions['tick'].handlers[(TargetPair('off', Character),)])

        # max 2 words
        self.assertRaises(EngineError, self.game.on, ['one two three'], Character)
        # conflicting (even redundant) targetpairs and 2nd word
        self.assertRaises(EngineError, self.game.on, ['pick up'], TargetPair('up', Character))
        # providing synonyms for different two-word actions is too ambiguous
        self.assertRaises(EngineError, self.game.on, ['one two', 'three two'], Character, synonyms=['syn'])

    def test_conversation_init(self):
        # Game author code
        diner = Room("Diner")
        char = Character("Bob", location=diner)

        @self.game.conversation()
        def dinner_order(conv, testarg):
            self.game.narrate("Test: %s" % testarg)
            char.converse("Would you like a hamburger or hotdog?")
            yield conv.get_response()
            if(conv.response in ['hamburger', 'burger']):
                char.converse('pickles?')
                yield conv.get_response()
                if(conv.response in 'yes'):
                    self.game.narrate('ordered pickles')
            elif conv.response in ['hotdog']:
                self.game.narrate('ordered hotdog')
            else:
                yield conv.get_response()

        # Start
        dinner_order(345)

        # Player input
        dinner_order.switch("burger")
        self.assertRaises(StopIteration, dinner_order.switch, "yes")


    def test_conversation_interaction(self):

        # Game author code
        diner = Room("Diner")
        char = Character("Bob", location=diner)

        @self.game.conversation()
        def dinner_order(conv, testarg):
            self.game.narrate("Test: %s" % testarg)
            char.converse("Would you like a hamburger or hotdog?")
            yield conv.get_response()
            if(conv.response in ['hamburger', 'burger']):
                char.converse('pickles?')
                yield conv.get_response()
                if(conv.response in 'yes'):
                    self.game.narrate('ordered pickles')
            elif conv.response in ['hotdog']:
                self.game.narrate('ordered hotdog')
            else:
                yield conv.get_response()

        @self.game.on_start()
        def startup():
            dinner_order(345)

        # Queue up input
        self.testin.put("hamburger")
        self.testin.put("yes")

        # Start
        self.game.start(self.game.pc, instream=self.testin, outstream=self.testout)


    def test_thing_lists(self):
        """
        test actions that work on a list of things (in any order)
        Also tests subclassing Item
        """

        p = notea.util.inflect

        class Ingredient(Item):
            pass

        @self.game.on('enchant', Ingredient)
        def enchant(ing):
            self.game.narrate("You have enchanted %s" % ing)

        @self.game.on('combine', ThingList(Ingredient))
        def combine(ingredient_list):
            self.game.narrate("You have combined " + p.join([i.name for i in ingredient_list]) + ".")

        wolfsbane = Ingredient("wolfsbane")
        eye = Ingredient("eye of newt")
        nightshade = Ingredient("nightshade")

        wolfsbane.do('enchant')

        self.game.actions['combine'].do(TargetPair(None, [wolfsbane, eye, nightshade]))

        self.step_input("combine all")



    def test_get_drop(self):
        """
        Tests parsing of commands including ThingLists
        """
        bedroom = Room("Bedroom")
        self.game.pc.place(bedroom)

        with bedroom:
            lighter = Item("lighter")
            book = Item("book")
            toothbrush = Item("toothbrush")

        # Start
        self.step_input("get lighter")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter]))
        self.step_input("pick up book.")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter, book]))
        self.step_input("pick toothbrush up")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter, book, toothbrush]))

        self.step_input("drop book")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter, toothbrush]))

        self.step_input("drop toothbrush, book, lighter")
        self.assertEqual(self.game.pc.inventory, Inventory())

        self.step_input("take book, lighter, toothbrush")
        self.step_input("take lighter")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter, book, toothbrush]))

        self.step_input("drop all")
        self.assertEqual(self.game.pc.inventory, Inventory())

        self.step_input("take everything")
        self.assertEqual(self.game.pc.inventory, Inventory([lighter, book, toothbrush]))

        self.step_input("drop all except book")
        self.assertEqual(self.game.pc.inventory, Inventory([book]))


    def test_rooms(self):
        """ Test rooms, moving between rooms, and direction commands"""
        bedroom = Room("Bedroom")
        attic = Room("Attic")
        kitchen = Room("Kitchen")
        corridor = Room("Corridor", connections={'s':bedroom, 'e':kitchen, 'up':attic})
        self.game.pc.place(bedroom)

#         self.game.pc.place(bedroom)

        self.step_input("go n")
        self.assertEqual(self.game.pc.location, corridor)

        self.step_input("e")
        self.assertEqual(self.game.pc.location, kitchen)

        self.step_input("up")
        self.assertEqual(self.testout.last, kitchen.connections['up'].string_impassable)

        self.step_input("w. u. go down, then go s")
        self.step_input('')
        self.assertEqual(self.game.pc.location, bedroom)

    def test_ambiguity(self):
        """
        Test three forms of ambiguity:
        1. "what would you like to get?"
        2. "do you mean the red book or the blue book?"
        3. "do you want to look AT the desk or look IN the desk?"
        """


        bedroom = Room("Bedroom")
        self.game.pc.place(bedroom)

        with bedroom:
            lighter = Item("lighter")
            book = Item("red book")
            book2 = Item("blue book")
            toothbrush = Item(['toothbrush', 'tooth brush'])
            desk = Item('desk')
            desk.gettable = False

        self.step_input("pick up brush.")
        self.assertEqual(self.game.pc.inventory, Inventory([toothbrush]))

        self.step_input("pick up red book.")
        self.assertEqual(self.game.pc.inventory, Inventory([toothbrush, book]))

        self.step_input("drop all. pick up red.")
        self.assertEqual(self.game.pc.inventory, Inventory([book]))

        self.step_input("drop all. pick up blue.")
        self.assertEqual(self.game.pc.inventory, Inventory([book2]))

        self.step_input("drop all. pick up book.")
        # expect ambiguity; not picked up yet
        self.assertEqual(self.game.pc.inventory, Inventory())
        self.step_input("red")
        self.assertEqual(self.game.pc.inventory, Inventory([book]))
        self.step_input("look")

        # uses ambiguity_filter to get the remaining one
        self.step_input("get book")
        self.assertEqual(self.game.pc.inventory, Inventory([book, book2]))

        self.step_input("drop all. pick up.")
        self.step_input("book.")
        self.step_input("blue. get red")
        self.assertEqual(self.game.pc.inventory, Inventory([book2, book]))

        self.step_input("pick up all.")
        self.assertEqual(self.game.pc.inventory, Inventory([book, book2, toothbrush, lighter]))


        # Test preposition ambiguity
        @self.game.on('look', Thing)
        def look_at_thing(thing):
            self.game.narrate("looked at thing")

        self.step_input("look desk")
        self.assertEqual(self.testout.last, "looked at thing")


        @self.game.on('look', ('at', desk))
        def look_at_desk(desk):
            self.game.narrate("looked at desk!")

        @self.game.on('look', ('in', desk))
        def look_in_desk(desk):
            self.game.narrate("You see something inside the desk.")

        self.step_input("look desk")
        self.step_input("in")
        self.assertEqual(self.testout.last, "You see something inside the desk.")



#         self.compare_objects(sessioncopy, self.game.session)

        self.step_input("look. wait.")

        c = self.game.current_session.get_copy()
        print c

    def test_z_mountable(self):
        study = Room('study')
        self.game.pc.place(study)

        with study:
            chair = Thing('chair')
            book = Item('book')
            lamp = Item('pen')

        chair.mountable('sit on', reachable_things=[book])
        self.step_input("sit on chair")
        self.assertEqual(self.game.pc.position, chair)
        self.assertEqual(self.game.pc.position_prep, 'on')
        self.step_input("go w")
        self.assertEqual(self.testout.last, "You'll have to get off the chair first.")

        self.step_input('get book, pen')
        self.assertEqual(self.game.pc.inventory, Inventory([book]))

        self.step_input('get off chair')
        self.assertEqual(self.game.pc.position, None)

        self.step_input("sit on chair")
        self.assertEqual(self.game.pc.position, chair)

        self.step_input("stand")
        self.assertEqual(self.game.pc.position, None)


class TestOut(io.StringIO):
    lastbuf = ''
    last = None

    def write(self, string):
        self.lastbuf += string.strip()
        sys.stdout.write(string)

    def flush(self):
        self.last = self.lastbuf
        self.lastbuf = ''
        sys.stdout.flush()

class TestIn(collections.deque):
    def readline(self):
        try:
            return self.popleft()
        except IndexError:
            return(u'quit')
    def put(self, line):
        self.append(unicode(line))

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
