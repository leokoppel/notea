import unittest
import websocket
import gevent

import notea.ui
from notea import Game, Room, Thing, ThingList, Character, PlayerCharacter, Item, TargetPair


class TestGame(unittest.TestCase):

    def setUp(self):
        print ("===== Setting up test %s  " % self._testMethodName).ljust(100, '=')
        self.game = Game("Spam", debug=True)
        self.room = Room("A room")
        self.game.pc.place(self.room)

        self.game.start(ui=notea.ui.WebUI, startui=False)
        self.app = self.game.ui.app.test_client()

        print ("===== Starting test %s  " % self._testMethodName).ljust(100, '=')


    def tearDown(self):
        self.game.stop
        del self.game
        print ("===== End test %s  " % self._testMethodName).ljust(100, '=')


    def step_input(self, cmd):
        """ Helper to call step_game with a given input line """
        self.game.current_session.step_game(cmd)


    def test_route(self):
        rv = self.app.get('/')
        assert rv._status_code == 200

        rv = self.app.get('/gameterminal')
        # should be for websockets only
        assert rv._status_code == 404

    def test_websocket(self):
        # TODO: figure out how to test and stop gevent wsgiserver properly

        def test_worker():
            gevent.sleep(0.05)
            ws = websocket.create_connection("ws://127.0.0.1:5000/game", timeout=1)
            ws.send("look")
            rv = ws.recv()
            print "Received '%s'" % rv
            assert "A room" in rv
            assert "sessiondata" in rv

            ws.close()

        import threading
        t = threading.Thread(target=test_worker)
        t.start()

        gevent.spawn_later(0.1, self.game.stop)
        self.game.start()

        assert self.game.ui.http_server.closed







if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
