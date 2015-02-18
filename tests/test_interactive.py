from notea import Game, Room, Thing, Character, PlayerCharacter, Item
import unittest



class TestGameInteractive(unittest.TestCase):

    def test_interactive_game(self):
        self.game = Game("Spam")

        bedroom = Room("Bedroom")
        self.game.pc.place(bedroom)


        g = self.game

        @self.game.episode()
        def crickets(ep):
            import random
            total = 0
            while True:
                yield ep.step()
                num = random.randint(0, 10)
                total += num
                ep._game.narrate("%d crickets chirp. In total, %d crickets have chirped." % (num, total))

        with bedroom:
            lighter = Item("lighter")
            book = Item("red book")
            book2 = Item("blue book")
            book3 = Item("thick book")
            toothbrush = Item(['toothbrush', 'tooth brush'])
            chair = Thing("chair")
            chair.mountable('sit on', reachable_things=['red book'])

        @self.game.on("use", toothbrush)
        def brush_teeth(brush):
            print ("You brush your teeth using the %s" % brush)


        crickets()
        self.game.start()



if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']

    unittest.main()
