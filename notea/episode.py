"""
Provides a class to wrap game episodes
"""
# (c) Leo Koppel 2014

import notea.things as things

# set up logging
import logging
logger = logging.getLogger(__name__)

class Episode(things.GameObject):
    """
    Wraps a generator with game hooks
    """

    def __init__(self, f, nosave=False, game=None):
        """
        Called when decorated function f is defined
        """
        super(Episode, self).__init__(game)

        self.name = f.__name__
        self.nosave = nosave
        self.response = None
        self._scheduled_step = None
        self._scheduled_time = None
        self._dead = True
        self.steps = 0
        self._f = f

        logger.debug("Initialized episode %s (%s) for %s" % (self.name, hex(id(self)), f))


    def __getstate__(self):
        # Episode.__getstate__ is only called when the state needs to be saved
        # (i.e. when the episode is running)
        # Thus, override to save more than _thingref
        state = super(Episode, self).__getstate__()
        
        if self.nosave:
            state['_scheduled_step'] = None
            state['_scheduled_time'] = None
            del state['_generator']
            del state['_f']
        return state
    
    def __setstate__(self, d):
        super(Episode, self).__setstate__(d)
        
        if self.nosave:
            # Mark for removal next step
            self._dead = True
            

    def __copy__(self):
        state = things.GameObject.__getstate__(self)
        res = type(self).__new__(type(self))
        res.__dict__ = state

    def __call__(self, *args, **kwargs):
        """
        Start the episode now
        Called when decorated function name is called
        """
        logger.debug("Starting episode %s (%s)" % (self.name, hex(id(self))))
        
        self._dead = False
        
        session = self._game.current_session
        session._live_episodes.append(self)
        self._generator = self._f(self, *args, **kwargs)
        
        res = next(self._generator)
        return session.episode_yield(self, *res if res else None)

    def step(self, steps=None, time=None, resume=None, block=False):
        """ Call from inside: yield back to parent until further input """
        self.steps += 1
        res = (steps, time, resume, block)
        logger.debug("%s to yield with %s" % (repr(self), res))
        
        # Return so it can be yielded
        return res
        
    def switch(self, msg):
        """
        Call from outside
        """
        self.response = msg
        return self._generator.send(msg)
    
    def unschedule(self):
        self._scheduled_step = None
        self._scheduled_time = None
        

class Conversation(Episode):
    """
    An Episode meant for blocking ("modal") conversations
    """
    def get_response(self):
        return self.step(steps=0, block=True)

