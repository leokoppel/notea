"""
Flask app UI using websockets as a game terminal
"""
# (c) Leo Koppel 2014 

import sys, os
import re
from cStringIO import StringIO
import json

import flask
from flask.ext import socketio
import greenlet
import gevent.event

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

    def __init__(self, game=None, port=5000):
        super(WebUI, self).__init__(game)
        ui_path = os.path.dirname(__file__)
        self.port = port
        self.app = flask.Flask(self._game.title,
                               template_folder=ui_path + '/templates',
                               static_folder=ui_path + '/static')
        self.server_stop_event = gevent.event.Event()
        self.socketio = socketio.SocketIO(self.app)

        if self._game.debug:
            self.app.debug = True
        
        self.start_callback = None
        
        def send_buffer_over_socket(game_session):
            """ Empty buffer into socket - called from socket handlers, not the game """
            game_session.out_buffer.seek(0)
            socketio.send(self.prepare_output(game_session))
            game_session.out_buffer.truncate(0)

        @self.socketio.on('connect', namespace='/game')
        def socket_connect():
            logger.info('New websocket connection: {}'.format(flask.request.remote_addr))
            logger.debug("gr: {}".format(greenlet.getcurrent()))
                        
            game_session = flask.session.get('game_session')
            if not game_session:
                # Create a new game session
                game_session = self._game._base_session.get_copy()
                game_session.register_current_greenlet()
                game_session.out_buffer = StringIO()
                
                logger.debug("Using new game_session {}, copy of {}".format(game_session,
                                                                            self._game._base_session))

                flask.session['game_session'] = game_session

                if self.start_callback:
                    self.start_callback()
            
            send_buffer_over_socket(game_session)
                    


        @self.socketio.on('message', namespace='/game')
        def game_socket(message):
            """
            Websocket handler:
            Creates a new game game_session, then uses the websocket as a terminal for the game
            """

            logger.info('Websocket message: {}'.format(message))
            logger.debug("gr: {}".format(greenlet.getcurrent()))

            
            game_session = flask.session.get('game_session')
            game_session.step_game(message)
            
            game_session.out_buffer.seek(0)
            
            send_buffer_over_socket(game_session)

        @self.app.route('/')
        def game_ui():
            return flask.render_template('game.html')
    

    def start(self, start_callback=None, host=None, port=None):
        self.start_callback = start_callback
        port = port or self.port
#         self.socketio.run(self.app, port=port)

        # Don't call self.socketio.run as we don't want to run forever
        # Instead, run the server only until a stop event is set
        if host is None:
            host = '127.0.0.1'
        if port is None:
            server_name = self.app.config['SERVER_NAME']
            if server_name and ':' in server_name:
                port = int(server_name.rsplit(':', 1)[1])
            else:
                port = self.port

        self.server = socketio.SocketIOServer((host, port), self.app, resource='socket.io')
        logger.info(' * Running on http://%s:%d/' % (host, port))
        self.server.start()
        
        try:
            self.server_stop_event.wait()
        except KeyboardInterrupt:
            # Don't print stack trace on Ctrl-C 
            pass


    def stop(self):
        self.server_stop_event.set()
        try:
            self.server.stop()
        except AttributeError:
            pass


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
        
