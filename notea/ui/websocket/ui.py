"""
Flask app UI using websockets as a game terminal
"""
# (c) Leo Koppel 2014 

import sys, os
import re
from cStringIO import StringIO
import json

import flask
import greenlet
import gevent.wsgi
import geventwebsocket
from geventwebsocket.exceptions import WebSocketError

# Monkey-patch gevent for pypy
if "__pypy__" in sys.builtin_module_names:
    def _reuse(self):
        self._sock._reuse()

    def _drop(self):
        self._sock._drop()

    gevent.socket.socket._reuse = _reuse
    gevent.socket.socket._drop = _drop
    gevent.hub.Hub.loop_class = 'pypycore.loop'

import notea.things
import notea.util

# set up logging
import logging
logger = logging.getLogger(__name__)

class WebUI(notea.things.GameObject):
    """
    Interface between user and game
    """

    def __init__(self, game=None):
        super(WebUI, self).__init__(game)
        ui_path = os.path.dirname(__file__)
        self.app = flask.Flask(self._game.title,
                               template_folder=ui_path + '/templates',
                               static_folder=ui_path + '/static')

        self.http_server = gevent.wsgi.WSGIServer(('', 5000), self.app,
            handler_class=geventwebsocket.handler.WebSocketHandler)

        if self._game.debug:
            self.app.debug = True


        @self.app.route('/game')
        def game_socket():
            """
            Websocket handler:
            Creates a new game session, then uses the websocket as a terminal for the game
            """
            if flask.request.environ.get('wsgi.websocket'):
                ws = flask.request.environ['wsgi.websocket']
                logger.info("New websocket connection: {}".format(ws.environ.get('HTTP_USER_AGENT')))
                logger.debug("{}".format(greenlet.getcurrent()))


                with self._game._base_session.get_copy() as session:
                    session.out_buffer = StringIO()
                    logger.debug("Using session {} copy of {}".format(session, self._game.current_session))
                    try:
                        if self.start_callback:
                            self.start_callback()

                        while True:
                            session.out_buffer.seek(0)
                            ws.send(self.prepare_output(session))
                            session.out_buffer.truncate(0)

                            message = ws.receive()
                            session.step_game(message)

                    except WebSocketError: # socket closed, etc.
                        flask.abort(500)
            else:
                flask.abort(404)


        @self.app.route('/')
        def game_ui():
            return flask.render_template('game.html')


    def start(self, start_callback=None):
        self.start_callback = start_callback
        self.http_server.serve_forever()

    def stop(self):
        self.http_server.stop()


    def output(self, msg, end='\n'):
        """
        Output a message over the websocket handling the session
        """

        self._game.current_session.out_buffer.write(msg + end)

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

    def prepare_output(self, session):
        """ Prepare JSON output """
        resp = {'sessiondata' : {'score': session.points,
                                 'moves': session.steps
                                 },
                'output' : self.format_output(session.out_buffer.read())
                }
        return json.dumps(resp)


    def format_output(self, msg):
        """
        Format game output as HTML
        """
        return self.newlines_to_paragraphs(msg.strip());

        
    def newlines_to_paragraphs(self, msg):
        """
        Convert paragraphs separated by an empty line to <p> tags
        Convert single newlines to <br/>
        """
        msg = re.sub('[\r\n]','<br/>\n', msg)
        return ('<p>' + re.sub('<br/>\s?<br/>','</p><p>', msg) + '</p>')
        
