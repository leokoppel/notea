"""
Text-only console UI
"""
# (c) Leo Koppel 2014 

import sys
import notea.util

# set up logging
import logging
logger = logging.getLogger(__name__)

class ConsoleUI(object):
    """
    Interface between user and game
    """

    def __init__(self, game, instream=sys.stdin, outstream=sys.stdout):
        self.prompt = '-->'
        self.stdin = instream
        self.stdout = outstream
        self._game = game

    def start(self, start_callback=None):
        """
        Start a game
        """
        if start_callback:
            start_callback()
        
        while(self._game.current_session.running):
            self._game.current_session.step_game(self.get_input())


    def get_input(self):
        if(self.stdin == sys.stdin):
            line = raw_input(self.prompt)
        else:
            line = self.stdin.readline()
        self.stdout.flush()

        logger.debug('Got input %s from %s' % (line, self.stdin))
        return line


    def output(self, msg, end='\n'):
        """
        Output a message to the user
        """
        self.stdout.flush()
        self.stdout.write(msg + end)
        self.stdout.flush()

    def narrate(self, msg, end='\n\n'):
        """
        Output an in-game message to user
        """
        self.output(notea.util.dedent(msg), end)


    def dialogue(self, char, msg):
        """
        Output a character's dialogue
        """
        self.output(char + ": " + msg)

    def stop(self):
        pass
