"""
Defines a class for tracking game progress.
TODO: not yet used
"""
# (c) Leo Koppel 2014

import collections

import notea.things as things

class Quest(things.BaseThing):
    """
    Used for tracking progress. Has a status and steps (also Quests).
    should be stored in a dict
    """

    def __init__(self, step_names=[], parent=None, handler=None, game=None):

        self.parent = parent
        super(Quest, self).__init__(game)

        self._complete = False
        self._complete_handler = handler
        self.steps = collections.OrderedDict()
        for k in step_names:
            self.add(k)



    def add_step(self, name):
        """ add to steps """
        self.steps[name] = Quest(parent=self, handler=None, game=self._game)

    def update(self):
        """ check if complete """
        if len(self.steps) > 0 and all(s.complete for s in self.steps.values()):
            self.finish()

    @property
    def completed_steps(self):
        """ return number of completed steps """
        return len(filter(None, [s.complete for s in self.steps.values()]))

    @property
    def total_steps(self):
        return len(self.steps)

    @property
    def complete(self):
        return self._complete

    @complete.setter
    def complete(self, val=True):
        self._complete = val
        if self.complete:
            try:
                self._complete_handler
            except NameError:
                pass
            else:
                self._complete_handler(self._game)

            try:
                self.parent.update
            except AttributeError:
                pass
            else:
                self.parent.update()

    def finish(self, val=True):
        self.complete = val

    def on_complete(self, f):
        """ decorator: sets function to call on complete """
        self._complete_handler = f
        return f
