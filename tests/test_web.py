import unittest
import websocket
from flask.ext import socketio
import gevent, json

import notea.ui
from notea import Game, Room, Thing, ThingList, Character, PlayerCharacter, Item, TargetPair


class TestGame(unittest.TestCase):

    def setUp(self):
        print ("===== Setting up test %s  " % self._testMethodName).ljust(100, '=')
        self.game = Game("Spam", debug=True)
        self.room = Room("A room")
        self.game.pc.place(self.room)

        self.game.ui = notea.ui.WebUI()
        self.game.ui.app.config['SECRET_KEY'] = 'secret'
                
        print ("===== Starting test %s  " % self._testMethodName).ljust(100, '=')


    def tearDown(self):
        self.game.stop()
        del self.game
        print ("===== End test %s  " % self._testMethodName).ljust(100, '=')


    def step_input(self, cmd):
        """ Helper to call step_game with a given input line """
        self.game.current_session.step_game(cmd)


    def test_route(self):
        test_client =  self.game.ui.app.test_client()
        rv = test_client.get('/')
        self.assertEqual(rv._status_code, 200)

        rv = test_client.get('/game')
        # should be for websockets only
        self.assertEqual(rv._status_code, 404)

    def test_websocket(self):
        
        def test_worker():
            gevent.sleep(0.05)
            test_client = self.game.ui.socketio.test_client(self.game.ui.app, namespace='/game')
            test_client.get_received('/game') # clear buffer
            
            test_client.send('look', namespace='/game')
            rv = test_client.get_received('/game')
            self.assertEqual(len(rv), True)
            rv_data = json.loads(rv[0]['args'])
            
            self.assertEqual(rv_data['sessiondata']['moves'], 1)
            
        import threading
        t = threading.Thread(target=test_worker)
        t.start()
        
        gevent.spawn_later(0.1, self.game.stop)
        self.game.start()
        
        self.assertTrue(self.game.ui.server.closed)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
