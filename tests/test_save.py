import unittest
import os
import copy, pickle

import notea
from notea import Game, PlayerCharacter, Thing, Item, Room
from notea.things import Inventory

SAVE_DIR = 'tests/save/'

class SaveTestCase(unittest.TestCase):

    def setUp(self):
        print ("===== Setting up test %s  " % self._testMethodName).ljust(100, '=')
        
        try:
            os.remove(SAVE_DIR + self._testMethodName + '.db')
        except OSError:
            pass
        
        self.game = Game("Spam", debug=True)
        self.game.pc.name="Leo"
        self.hall = Room("Hall")
        self.game.pc.place(self.hall)

        self.game.start(startui=False)
        self.parse = self.game.parser.parse
        print ("===== Starting test %s  " % self._testMethodName).ljust(100, '=')

    def tearDown(self):
        del self.game
        print ("===== End test %s  " % self._testMethodName).ljust(100, '=')

    def step_input(self, cmd):
        self.game.current_session.step_game(cmd)
    
    
    def test_basething(self):
        from notea.things import BaseThing
        # Don't test proxies here
        a = BaseThing()
        a.x = 3
        b = BaseThing()
        b.x = 3
        c = BaseThing()
        c.x = 5
        
#         # BaseThing cannot be hashed until a subclass sets _uid
#         self.assertRaises(notea.EngineError, hash, a)
        
        # These calls would normally be in the __init__ of a subclass
        self.game.current_session.bind(a, a.x)
        self.game.current_session.bind(b, b.x)
        self.game.current_session.bind(c, c.x)
        
        acopy = a.__copy__()
        bcopy = b.__copy__()
        ccopy = c.__copy__()

        a.x = 20
        acopy.x
        a.x
        assert acopy.x == a.x and a.x == 20
        acopy.x = 9
        assert acopy.x != a.x and a.x == 20
        
                
        assert a == acopy._thingref
        assert a == acopy
        assert a is not acopy
                
        # pickle (using __getstate___ does copy changes from the original
        # This works differently from __copy__
        c = pickle.loads(pickle.dumps(acopy))
        d = acopy.__copy__()
        self.assertEqual(c.x, acopy.x)
        self.assertEqual(d.x, a.x)
        
        
    def test_proxy(self):
        A = Thing('A')
        A_prox = notea.thingproxy.ThingProxy(A)
         
        self.assertEqual(A.name, A_prox.name)
        self.assertIs(A.name, A_prox.name)
         
        
    def test_thing(self):
        a = Thing('thing A', proxy=False)
        a.x = 100
        a.y = 30
        a.the_str = 'the A thing'
        self.assertEqual(a.the_str, 'the A thing')
        b = Thing('second thing')
        self.assertNotEqual(a, b)
                
        # Non-unique names are allowed but have different uids, and could cause problems
        z = Thing('thing A')
        self.assertNotEqual(a._uid, z._uid)
        
        
        a1 = copy.copy(a)
        a1.y = 42
        self.assertNotEqual(id(a), id(a1))
        self.assertEqual(a1._thingref, a)
        
        # Test descriptor property
        self.assertEqual(a.the_str, 'the A thing')
        self.assertEqual(a1.the_str, 'the A thing')
        a1.the_str = 'the copy'
        self.assertEqual(a.the_str, 'the A thing')
        self.assertEqual(a1.the_str, 'the copy')

        
        # Test copy with getstate
        astate = a.__getstate__()
        self.assertEqual(astate['x'], 100)
        
        a1state = a1.__getstate__()
        self.assertNotIn('x', a1state)
        self.assertEqual(a1state['y'], 42)        
        
        # Note equality in the game does not mean dicts are equal, just
        # that objects refer to the same in-game Thing
        # Also, only one level of _thingrefs is currently allowed: a.__copy__().__copy__() returns a.__copy__()
        c = copy.copy(a1)
        self.assertEqual(a, c._thingref)
        self.assertEqual(a.y, 30)
        self.assertEqual(c.y, 30)
        self.assertNotIn('y', c.__dict__)
    
    def test_inventory(self):
        
        # Test that copied placeheld sets (inventory parent) are decoupled
        ps1 = notea.things.PlaceheldSet()        
        ps2 = copy.copy(ps1)
        
        x = Thing('a')
        ps1.add(x)
        
        self.assertNotEqual(ps1, ps2)
        self.assertIsNot(ps1, ps2)
        self.assertIn(x, ps1)
        self.assertNotIn(x, ps2)
    
    def test_session_pickle(self):
        
        a = Item('thing A', proxy=False)
        a.x = 'spam'
        a.get()

        
        # Test session copy
        s = self.game.current_session
        self.assertIs(a, next(x for x in s.things if x.name == 'thing A'))
    
        sstate = s.__getstate__()
        sstate_a = next(x for x in sstate['things'] if getattr(x,'name',None) == 'thing A')
        self.assertEqual(sstate_a, a)
        self.assertEqual(sstate_a.x, a.x)
        self.assertIn('x', sstate_a.__dict__)

        # Test copy of session flyweight from get_copy()
        # Now we expect the things set to only include a flyweight of 'a'
        s1 = self.game.current_session.get_copy()

        self.assertEqual(s1._uids[a._uid]._thingref, a)
        self.assertEqual(s.things, s1.things)
        self.assertIsNot(s.things, s1.things)
        self.assertTrue(a in s1.things)
        self.assertIn(a, s1.things)


        s1state = s1.__getstate__()
        s1state_a = next(x for x in s1state['_uids'].values() if x.name == 'thing A')
        self.assertEqual(s1state_a._thingref, a)
        self.assertEqual(s1state_a.x, 'spam')
        self.assertNotIn('x', s1state_a.__dict__)

        # Test decoupling of inventory (a PlaceheldSet) between sessions
        b = Thing('test')
        s.pc.inventory.add(b)
        self.assertIn(b, s.pc.inventory)
        self.assertNotIn(b, s1.pc.inventory)
        self.assertNotEqual(s.pc.inventory, s1.pc.inventory)
        
        # Test decoupling of position (a PlaceheldProperty) between sessions 
        s1.pc.position = a
        self.assertEqual(s1.pc.position, a)
        self.assertEqual(s.pc.position, None)
        

        # Test pickle of original session
        # This is only useful to check for exceptions on pickling, not for data integrity
        s_pickle = pickle.dumps(s)
        s_restored = pickle.loads(s_pickle)
        s_restored_a = next(x for x in s_restored.things if x.name == 'thing A')
        self.assertEqual(s_restored_a.x, 'spam')
                
        # Test pickle of flyweight session, the real test
        s1_pickle = pickle.dumps(s1)
        
        s1._get_thing_by_uid(a._uid).x = 'changed_after_dump'

        s1_restored = pickle.loads(s1_pickle)
        s1_restored_a = next(x for x in s1_restored.things if x.name == 'thing A')
        self.assertEqual(s1_restored_a.x, 'spam')
        self.assertIs(s1state_a._thingref, a)
        
        
        # Test unpickling with completely restarted game object
        # Dump to file for next test:
        with open(SAVE_DIR + '/session_pickle.db', 'wb') as f:
            f.write(s1_pickle)
    
    def test_session_pickle_restore(self):
        with open(SAVE_DIR + '/session_pickle.db', 'rb') as f:
            # Thing A is made in between game.start() and the session copy
            # it is expected NOT to work after restore, as restarted game state is not the same
            self.assertRaises(notea.EngineError, pickle.load, f)
            
            # bring back the same initial state
            f.seek(0)
            z = Item('thing A', proxy=False)
            z.x = 'spam'
            s = pickle.load(f)
            s.register_current_greenlet()
            
            s_a = next(x for x in s.things if x.name == 'thing A')
            self.assertEqual(s_a.x, 'spam')
            self.assertIs(s_a._thingref, z)
            
       
    
    def test_save_new_session(self):
        
        self.game.savedir = SAVE_DIR
        
        @self.game.episode()
        def crickets(ep):
            """ episode to count turns """
            global chirped
            chirped = 0
            internal = 0
            while True:
                internal +=1
                chirped = internal
                ep._game.narrate("A cricket chirps. In total, {} crickets have chirped.".format(chirped))
                yield ep.step()
        
        
        m1 = 'Ha ha ha'
        @self.game.on('laugh', groups=['humour'])
        def laugh():
            global test_out
            self.game.narrate(m1)
            test_out = m1
         
        m2 = "You don't find anything very funny."
        @self.game.on_group('humour')
        def humourless():
            global test_out
            self.game.narrate(m2)
            test_out = m2
            return True
                
        bedroom = Room("Bedroom")
        self.game.pc.place(bedroom)
        
        crickets()
        
        lighter = Item("lighter", location=bedroom)
        book = Item("red book", location=bedroom)
        toothbrush = Item(['toothbrush', 'tooth brush'], location=bedroom)
        
        s = self.game.current_session.get_copy()
        assert s != self.game.current_session
        s.register_current_greenlet()
        assert s is self.game.current_session

        self.step_input('get toothbrush')
        self.assertEqual(self.game.pc.inventory, Inventory([toothbrush]))
        
        self.step_input('look at brush. look at book.')
        
        self.step_input('laugh')
        self.assertEqual(test_out, m2)
        
        chirped_before = chirped
        self.step_input("save")
        self.step_input(self._testMethodName)
        
        self.step_input('get all.')
        self.assertEqual(self.game.pc.inventory, Inventory([book, toothbrush, lighter]))
        
        self.step_input("look. go north.")
        
        humourless.disable()
        self.step_input('laugh')
        self.assertEqual(test_out, m1)
        
        self.step_input("restore")
        self.step_input(self._testMethodName)
        
        self.step_input("look.")
        self.assertEqual(chirped_before+1, chirped)
        
        self.assertEqual(self.game.pc.inventory, Inventory([toothbrush]))
        
        # Uncomment to test saving action handlers with session (currently not done)
#         self.step_input('laugh')
#         self.assertEqual(test_out, m2)
        

if __name__ == "__main__":
#     suite = unittest.TestSuite([SaveTestCase("test_thing")])
#     runner = unittest.TextTestRunner()
#     runner.run(suite)
    unittest.main()