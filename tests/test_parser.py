from notea import Game, PlayerCharacter, Thing, Item, Room
import notea
from notea.parser import ParseError
from notea.actions import TargetPair
import unittest, logging
from notea.util import AmbiguityError



class TestParser(unittest.TestCase):


    def setUp(self):
        print ("===== Setting up test %s  " % self._testMethodName).ljust(100, '=')
        self.game = Game("Spam", debug=True, proxy_things=False)
        self.game.pc = PlayerCharacter("Leo")
        self.hall = Room("Hall")
        self.game.pc.place(self.hall)

        # make a bunch of Things to provide nouns
        self.desk, self.vase = Thing(['desk', 'table'], location=self.hall), Item("vase")
        self.red, self.blue, self.green = Item("red book", location=self.hall), Item("blue book", location=self.hall), Item("green book", location=self.hall)


        self.game.start(startui=False)
        self.parse = self.game.parser.parse
        print ("===== Starting test %s  " % self._testMethodName).ljust(100, '=')

    def tearDown(self):
        del self.game
        print ("===== End test %s  " % self._testMethodName).ljust(100, '=')


    def test_lexer(self):
        lex = self.game.parser.lex

        # normal
        tokens = lex("go to the table")
        self.assertEqual(tokens, [['go', 'VB'], ['to', 'IN'], ['the', 'AT'], ['table', 'NN']])

        # nonsensical
        tokens = lex("book look blue in under red")
        self.assertEqual([t[1] for t in tokens], ['NN', 'VB', 'NN', 'IN', 'IN', 'NN'])

        # ambiguous: directions
        self.assertEqual([t[1] for t in lex('n')], ['DIR'])
        self.assertEqual([t[1] for t in lex('go up')], ['VB', 'DIR'])
        self.assertEqual([t[1] for t in lex('pick up')], ['VB', 'IN'])
        self.assertEqual([t[1] for t in lex('up')], ['DIR'])
        self.assertEqual([t[1] for t in lex('up', notea.parser.Ambiguity(0, 0, 'IN', 0, 0))], ['IN'])

        # ambiguous: verb and noun
        self.assertEqual([t[1] for t in lex('get pick')], ['VB', 'VB'])
        Thing("ice pick")
        self.game.parser.fill_word_lists(self.game.current_session)
        self.assertEqual([t[1] for t in lex('pick')], ['VB'])
        self.assertEqual([t[1] for t in lex('get pick')], ['VB', 'NN'])
        self.assertEqual([t[1] for t in lex('look at pick')], ['VB', 'IN', 'NN'])

        # invalid word
        self.assertRaises(ParseError, lex, 'get fragglywop')

    def test_tupler(self):

        verb, pairs = self.game.parser.form_tuples([['go', 'VB'], ['to', 'IN'], ['the', 'AT'], ['table', 'NN']])
        self.assertEqual(verb, 'go')
        self.assertEqual(pairs, [TargetPair('to', ['table'])])


        # noun combination
        _, pairs = self.game.parser.form_tuples([['get', 'VB'], ['a', 'NN'], [',', ','], ['b', 'NN'],
                                                    ['and', 'CC'], ['c', 'NN'], ['something', 'NN'], ['something', 'NN']])
        self.assertEqual(pairs, [ TargetPair(None, ['a', 'b', 'c something something']) ])

        # ignore articles
        verb, pairs = self.game.parser.form_tuples([['to', 'IN'], ['the', 'AT'], ['beach', 'NN']])
        self.assertEqual(verb, None)
        self.assertEqual(pairs, [TargetPair('to', ['beach'])])

        _, pairs = self.game.parser.form_tuples([['the', 'AT'], ['room', 'NN'], ['the', 'AT']])
        self.assertEqual(pairs, [TargetPair(None, ['room'])])

        # preposition ordering
        verb, pairs = self.game.parser.form_tuples([['pick', 'VB'], ['coat', 'NN'], ['up', 'IN']])
        _, pairs2 = self.game.parser.form_tuples([['pick', 'VB'], ['up', 'IN'], ['coat', 'NN']])
        self.assertEqual(verb, 'pick')
        self.assertEqual(pairs, [TargetPair('up', ['coat'])])
        self.assertEqual(pairs, pairs2)

        verb, pairs = self.game.parser.form_tuples([['deposit', 'VB'], ['the', 'AT'], ['blue', 'NN'], ['book', 'NN'],
                                                    ['and', 'CC'], ['green', 'NN'], ['book', 'NN'],
                                                    ['beside', 'IN'], ['the', 'AT'], ['red', 'NN'], ['book', 'NN']])
        self.assertEqual(pairs, [TargetPair(None, ['blue book', 'green book']), TargetPair('beside', ['red book'])])

        # two prepositions in a row won't work (even if it makes sense)
        self.assertRaises(ParseError, self.game.parser.form_tuples,
                          [['climb', 'VB'], ['up', 'IN'], ['over', 'IN'], ['hill', 'NN']])

        # keyword not used as a keyword
        self.assertRaises(ParseError, self.game.parser.form_tuples,
                          [['get', 'VB'], ['the', 'IN'], ['restore', 'KWD']])

    def test_replace_ambiguity(self):
        """
        Test noun or preposition ambiguity replacement (using mock Ambiguty objects)
        Don't actually check detection of ambiguities here.
        """
        # No noun provided
        a = notea.parser.Ambiguity('pick', [ TargetPair('up', []) ], 'NN', 0, 0)
        input_pairs = [TargetPair(None, ['box'])]
        v, p = self.game.parser.replace_ambiguity(None, input_pairs, a)
        self.assertEqual(v, 'pick')
        self.assertEqual(p, [TargetPair('up', ['box'])])

        # Multiple prepositions possible
        a = notea.parser.Ambiguity('look', [ TargetPair(None, ['desk']) ], 'IN')
        input_pairs = [TargetPair('in', [])]
        v, p = self.game.parser.replace_ambiguity(None, input_pairs, a)
        self.assertEqual(v, 'look')
        self.assertEqual(p, [TargetPair('in', ['desk'])])

        # Cancelled disambiguation
        a = notea.parser.Ambiguity('pick', [ TargetPair('up', []) ], 'NN', 0, 0)
        input_verb = 'do'
        input_pairs = [TargetPair('something', ['else'])]
        v, p = self.game.parser.replace_ambiguity(input_verb, input_pairs, a)
        self.assertEqual(v, input_verb)
        self.assertEqual(p, input_pairs)

    def test_words_to_objects(self):

        s = self.game.current_session

        # simple
        a, t = self.game.parser.words_to_objects('look', [ TargetPair('at', ['desk']) ], s)
        self.assertEqual(a, self.game.actions['look'])
        self.assertEqual(t, [ TargetPair('at', self.desk) ]) # note noun list is unwrapped for single element

        # synonyms
        _, t = self.game.parser.words_to_objects('look', [ TargetPair('at', ['table']) ], s)
        self.assertEqual(t, [ TargetPair('at', self.desk) ])

        # lists
        _, t = self.game.parser.words_to_objects('get', [ TargetPair(None, ['blue book', 'red']) ], s)
        self.assertEqual(t, [ TargetPair(None, [self.blue, self.red]) ])

        # vase is not in the same room
        self.assertRaises(ParseError, self.game.parser.words_to_objects, 'any', [ TargetPair(None, ['vase']) ], s)

        # direction special case
        a, t = self.game.parser.words_to_objects(None, [ TargetPair(None, ['ne']) ], s)
        self.assertEqual(a, self.game.actions['go'])
        direction_object = next(x for x in self.game.directions if x.name == 'ne')
        self.assertEqual(t, [ TargetPair(None, direction_object) ])

        # ambiguity
        try:
            v = 'get'
            p = [ TargetPair(None, ['desk', 'book']) ]
            self.game.parser.words_to_objects(v, p, s)
            self.fail('Expected AmbiguityError')
        except Exception as e:
            assert isinstance(e, notea.game.parser.AmbiguityError)
            assert 'Did you mean' in e.message
            assert 'red book' in e.message
            assert 'green book' in e.message
            self.assertEqual(e.ambiguity, notea.parser.Ambiguity(v, p, 'NN', 0, 1))

        # ambiguity filter: when 'get' is applicable to only one book
        self.red.get()
        self.blue.get()
        _, t = self.game.parser.words_to_objects('get', [ TargetPair(None, ['book']) ], s)
        self.assertEqual(t, [ TargetPair(None, self.green) ])

        # 'all'
        _, t = self.game.parser.words_to_objects('get', [ TargetPair(None, ['red', 'all']) ], s)
        # at this stage 'all' means literally everything in sight
        # the 'red' target should make no difference
        expected_list = notea.things.AllThingList([self.red, self.blue, self.green, self.desk, self.hall])
        result_list = t[0].nouns
        self.assertItemsEqual(expected_list, result_list)





    def test_parser(self):
        """
        Test overall parser, mainly the last (handler-finding) stage which is not covered by other tests
        """

        s = self.game.current_session

        try:
            next(self.parse("get"))
            self.fail('Expected AmbiguityError')
        except Exception as e:
            self.assertEquals(e.ambiguity, notea.parser.Ambiguity('get', [TargetPair()], 'NN', 0, 0))
            sentence, handler, targets = next(self.parse('red', s, e.ambiguity))
            self.assertEquals(sentence, 'red')
            self.assertEquals(handler, self.game.actions['get'].handlers[(TargetPair(None, Thing),)])
            self.assertEquals(targets, [TargetPair(None, self.red)])




if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']

    unittest.main()
