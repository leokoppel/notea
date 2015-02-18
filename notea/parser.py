"""
Handles tagging, parsing, and handling ambiguities in user input, and defines
English-language parts of speech for the current game.
"""
# (c) Leo Koppel 2014

import collections
import itertools
import re

import notea.util as util
from notea.util import ParseError, AmbiguityError, WordCategory
import notea.actions as actions
import notea.things as things
from notea.things import AllThingList

# set up logging
import logging
logger = logging.getLogger(__name__)

class DynamicList(list):
    """
    List bound to a getter function for easy updating
    """
    def __init__(self, f):
        self.get_contents = f
    def fill(self, session):
        del self[:]
        try:
            self.extend(self.get_contents(session))
        except TypeError: # allow argument-less lambdas
            self.extend(self.get_contents())



class Parser(object):
    """
    Convert text input to game commands
    """

    # Prepositions are used for relating actions to words
    #
    # This is just on the parser-side. Any actual relationships still have to be
    # added using action handlers.
    #
    # Note that prepositions don't have a unique meaning: "look through desk" is
    # probably the same as "look in desk", but different from "look through
    # window".

    def __init__(self, parent_game):
        '''
        Constructor
        '''
        self._game = parent_game


        self.global_keywords = set()
        self.keywords = collections.defaultdict(set)


        self.pos = {
            # Nouns: get all names possible split into single words
            # note this includes all Things including characters
            'NN'  : DynamicList(lambda session: list(itertools.chain.from_iterable(
                                [k.split() for k in self.get_game_nouns(session)]))),
            'VB'  : DynamicList(lambda: self._game.actions),
            'CC'  : {'and'},
            'AT'  : {'a', 'an', 'the'},
            'IGNORE' : {'am', 'is', 'are', 'of'}, # tricky but non-essential words we just throw away
#            'QDT' : {'who', 'what', 'where', 'when', 'why', 'how'}, # replaced by actions
            'IN'  : WordCategory({ # Prepositions (and other words considered prepositions for convenience)
                                  'to'     : {'to', 'toward', 'towards'},
                                  'from'   : {'from'},
                                  'at'     : {'at'},
                                  'in'     : {'in', 'inside', 'within'},
                                  'through': {'through'},
                                  'above'  : {'above'},
                                  'over'   : {'over'}, # separate from 'above': consider 'look over a desk'
                                  'under'  : {'under', 'below', 'beneath', 'underneath'},
                                  'up'     : {'up'},
                                  'down'   : {'down'}, # note 'up' and 'down' here are distinct from the navigation directions
                                  'behind' : {'behind'}, # and of course they are not true prepositions
                                  'around' : {'around'},
                                  'out'    : {'out', 'outside'},
                                  'about'  : {'about'},
                                  # On and off could also be used for switches, though not prepositions in that sense
                                  'on'     : {'on'},
                                  'off'    : {'off'},
                                  'with'   : {'with', 'using'}
                                 }),
            'DIR'  : self._game.directions,
            'ANS' : WordCategory({
                                  'yes': {'yes', 'y', 'yea', 'yeah', 'yay'},
                                  'no' : {'no', 'n', 'nay', 'never'} # note 'n' can only mean no if the 'North' direction doesn't apply
                                  }),
            'PPO' : WordCategory({
                                  'it'  : {'it', 'this', 'that'}, # again, only the same POS for game purposes
                                  'him' : {'him'},
                                  'her' : {'her'},
                                  'them': {'them'}
                                  }),
            # Special tags for lists
            'all'  : {'all', 'everything'},
            'except' : {'except', 'excluding'},
            # Punctuation
            ','   : {','},
            '.'   : {'.'},
            '!'   : {'!'},
            # Special game keywords like 'save' which don't count as verbs
            'KWD'  : DynamicList(lambda: self._game.keywords),
        }

        self.fill_word_lists(self._game.current_session)


    def fill_word_lists(self, session):
        """ Update dynamic word lists """
        for l in self.pos:
            try:
                self.pos[l].fill(session)
            except AttributeError:
                pass


    def get_game_nouns(self, session):
        """
        return a list of Thing names and anything else acceptable as a nouns
        """
        return ([k.name for k in session.things] +
                [s for k in session.things for s in k.synonyms] +
                [k for k in session._game.room_nouns])


    def lex(self, sentence, ambiguity=None):
        """
        Given a single sentence command, split into tokens and assign parts of
        speech (noun, verb) based on POS table and names of game objects.
        
        Return a list of tagged tokens, where:
        tok[0] = the word
        tok[1] = part of speech ('NN', 'VB')
        
        """

        # Split sentence into alphanumeric tokens and limited punctuation
        # Currently question marks & exclamation points are thrown out
        tokens = re.findall('\.|,|[a-z]+', sentence.lower())

        logger.debug("parsing tokens %s" % tokens)

        if len(tokens) < 1:
            # presumably no alphabetic characters in the input
            raise ParseError("I don't understand that.")

        # Check for valid words
        # Tag the words (and check for invalid words)
        tags = []
        for tok in tokens:
            # Assign POS tag using the self.pos dict
            # Just find all the possible tags. Ambiguities can be solved
            # later when looking at sentence as a whole. We can still
            # check for invalid words.
            possible_tags = [p for p in self.pos if tok in self.pos[p]]
            logger.debug("Possible tags for token %s: %s" % (tok, possible_tags))
            if not possible_tags:
                raise ParseError("What kind of a word is %s?" % tok)
            else:
                tags.append([tok, possible_tags])

        # We now have to account for ambiguities (e.g. 'n' for 'no' vs
        # 'north', 'save' as a game keyword or verb, maybe 'light' as a verb
        # or noun).
        #
        # For example, for the input "Go n. poke at albatross with stick",
        # we should now have a list that looks like this:
        # [ ('go', ['VB']), ('n', ['ANS', 'DIR']), ('.',['.']) ], or
        # [ ('poke', ['VB']), ('at', ['IN']), ('albatross', ['NN']), ('with', ['IN']), ('stick', ['NN', 'VB']) ]
        #
        # Our goal is to turn this list into a list of (prep,target) tuples (see Action):
        # 'go': [(None, <direction 'north'>)], or
        # 'poke': [('at', <Thing 'albatross'>), ('with', <Thing 'stick'>)]
        #
        # This can always be improved, but it's not a disaster to have ambiguities.
        # The game will just complain to the user!
        # It follows that it's okay to assume the author did not name Things or
        # actions after prepositions or pronouns.

        for i, tok in enumerate(tags):
            if len(tok[1]) == 1:
                continue
            # For each ambiguous token
            if 'KWD' in tok[1]:
                if len(tags) == 1:
                    # Easy case: game keywords should be the only word.
                    # Also, ANSwers are usually be consumed by a blocking conversation
                    tok[1] = ['KWD']
                else:
                    # Keyword not first
                    tok[1].remove('KWD')

            if 'VB' in tok[1] and 'NN' in tok[1]:
                # confusion between verb and noun
                if i == 0:
                    # if first word, probably a verb
                    tok[1] = ['VB']
                elif 'VB' in tags[i - 1][1] or 'IN' in tags[i - 1][1]:
                    # if preceding word is verb or preposition, probably a noun
                    tok[1] = ['NN']
            elif 'DIR' in tok[1] and 'ANS' in tok[1]:
                # confusion between 'n' meaning 'north' and 'no', probably
                tok[1] = ['DIR'] # for now -- TODO
            elif 'DIR' in tok[1] and 'IN' in tok[1]:
                # confusion between direction and preposition
                # e.g. 'go up' (RB) and 'pick up x' (IN)
                # assume it's a direction only if it's last and follows a 'go' verb or nothing,
                # except when disambiguating
                if (all(t[1] == [','] for t in tags[i + 1:]) and (i == 0 or tags[i - 1][0] in self._game.direction_verbs)
                     and not (ambiguity and ambiguity.word_type == 'IN')):
                    tok[1] = ['DIR']
                else:
                    tok[1] = ['IN']

        # Now collapse the lists (['VB'] => 'VB')
        # If there is still ambiguity, give up
        for tok in tags:
            if len(tok[1]) != 1:
                raise ParseError("I don't understand.")
            tok[1] = tok[1][0]

        return tags


    def form_tuples(self, tags):
        """
        Take tagged tokens (with tok[0] = 'word', tok[1] = 'POS') and form a 
        verb and list of TargetPairs
        
        """

        verb = None # the action to perform
        pairs = [actions.TargetPair()] # list of (prep, nouns) pairs

        # Just remove all articles and some other words
        tags = [t for t in tags if t[1] not in ['AT', 'IGNORE']]

        # Treat simple case of one keyword first
        if len(tags) == 1:
            if tags[0][1] == 'KWD':
                verb = tags[0][0] # a "non-verb" here doesn't trigger the "no verbs" exception
                logger.debug('parsed as single keyword')
                pass

        if not verb:
            # Now basically put the VB, NN, and IN together in the order they appear
            # use the last element in pairs to store the next preposition and/or noun as they are parsed
            # when both are filled, add a new element.
            noun_tags = ['NN', 'PPO', 'all', 'except', 'DIR'] # noun or pronoun or 'all' or compass direction

            for i, t in enumerate(tags):

                if t[1] in noun_tags:
                    if not pairs[-1].nouns:
                        logger.debug("Setting noun '{}'".format(t[0]))
                        pairs[-1].nouns.append(t[0])
                    else:
                        # check for past nouns to add to the list
                        try:
                            if (tags[i - 1][1] in ['CC', ','] and tags[i - 2][1] in noun_tags
                                or tags[i - 1][1] in ['all', 'except']):
                                logger.debug("Adding noun '{}' to noun list".format(t[0]))
                                pairs[-1].nouns.append(t[0])

                            elif tags[i - 1][1] in noun_tags and pairs[-1].nouns:
                                # 2 nouns in a row without conjunctions, etc
                                logger.debug("found second name word in a row: '{}'".format(t[0]))
                                # append to previous noun word; check later in Thing-matching stage
                                pairs[-1].nouns[-1] += (' ' + t[0])
                                logger.debug("appended to make {}".format(pairs[-1].nouns))


                        except IndexError:
                            logger.debug("Skipping noun '{}': IndexError on backward glance".format(t[0]))
                            pass

                elif t[1] in ['IN']: # preposition or adverb (e.g. 'up')
                    # If sandwiched between nouns ("pour water IN cup"), add to second noun's pair
                    # Otherwise, put in preceding pair
                    if pairs[-1].nouns and i + 1 < len(tags) and tags[i + 1][1] in noun_tags:
                        logger.debug("Noun-prep-noun sandwich, adding prep to next pair")
                        pairs.append(actions.TargetPair(t[0], []))
                    elif pairs[-1].prep is None:
                        logger.debug("Adding prep '{}' to current pair".format(t[0]))
                        pairs[-1].prep = t[0]
                        if pairs[-1].nouns: # if noun is already filled
                            pairs.append(actions.TargetPair())
                    elif not pairs[-1].nouns: # two prepositions in a row
                        logger.debug("Two prepositions in a row")
                        raise ParseError("Can you say that another way?")
                    else:
                        logger.debug("Skipping prep '{}'".format(t[0]))

                elif t[1] in [',', 'CC']:
                    # ignore or handled elsewhere
                    pass

                elif t[1] == 'VB':
                    if not verb:
                        verb = t[0]

                elif t[1] == 'KWD': # keyword not as single command
                    raise ParseError("I don't understand the keyword %s used that way." % t[0])

                else:
                    # unexpected
                    raise ParseError("I don't understand \"{}\" there.".format(t[0]))

                # end for loop
            # end if not verb
        # remove last empty pair if needed
        if len(pairs) > 1 and not pairs[-1]:
            pairs.pop()

        return verb, pairs


    def replace_ambiguity(self, verb, new_pairs, ambiguity):
        """
        Try to replace an ambiguous word (as described by the Ambiguity) in the
        last input with the new input. If it fits, return replaced verb and pairs.
        Otherwise, return new input as-is.
        """
        new_word = None
        if ambiguity.word_type == 'NN':
            # E.g. "what do you want to get?"
            # response: "pen"
            if not verb and len(new_pairs) == 1 and len(new_pairs[0].nouns) == 1:
                # Construct updated input, replacing noun.
                new_word = new_pairs[0].nouns[0]
                new_pairs = list(ambiguity.pairs)
                try:
                    new_pairs[ambiguity.index].nouns[ambiguity.noun_index] = new_word
                except IndexError:
                    new_pairs[ambiguity.index].nouns = [new_word]
                verb = ambiguity.verb
        elif ambiguity.word_type == 'IN':
            # E.g. "Do you want to look AT the table or look IN the table?"
            # response: "at" or "look at" (verb is allowed but must match)
            if (verb == None or verb == ambiguity.verb) and len(new_pairs) == 1 and new_pairs[0].prep and not new_pairs[0].nouns:
                new_word = new_pairs[0].prep
                new_pairs = list(ambiguity.pairs)
                new_pairs[ambiguity.index].prep = new_word
                verb = ambiguity.verb
        if new_word:
            logger.debug("Disambiguated past input to %s %s" % (verb, util.list_str(new_pairs)))
        else:
            logger.debug("Skipping ambiguity, treating input as new.")
        return verb, new_pairs


    def words_to_objects(self, verb, pairs, session):
        """
        Take a verb and list of TargetPairs containing plain strings,
        and find the corresponding game objects.
        
        Return an Action and list of TargetPairs containing Things.
        
        Raise ParseError and AmbiguityError as needed.
        """
        # Don't change input pairs as original words could be needed to disambiguate
        targets = []

        # Special case: compass directions
        # If a direction is used as a command, prepend the 'go' action
        if (not verb and len(pairs) == 1 and not pairs[0].prep
            and len(pairs[0].nouns) == 1 and pairs[0].nouns[0] in self._game.directions):
                logger.debug("Special-casing direction command '%s'" % pairs[0].nouns)
                verb = 'go'

        # Need a verb at this point
        if not verb:
            raise ParseError("There was no verb in that sentence!")

        # Get Action from verb string
        try:
            action = self._game.actions[verb]
        except KeyError:
            try:
                action = self._game.keywords[verb]
                action_is_keyword = True
            except KeyError:
                # This should never happen -- parser shouldn't have tagged it as a verb in this case.
                raise ParseError("I don't understand.")


        # Get Things from noun string
        for i, p in enumerate(pairs):
            targets.append(actions.TargetPair(p.prep, []))
            all_flag = False
            except_flag = False
            exceptions = set()

            for j, n in enumerate(p.nouns):
                if n in self.pos['all']:
                    all_flag = True
                    n = None
                elif all_flag and n in self.pos['except']:
                    except_flag = True
                    n = None
                else:
                    # Convert noun to list of Things
                    matches = self.things_from_noun(n, session)

                    if not matches:
                        raise ParseError("You see no %s here!" % n)

                    if len(matches) > 1:
                        # Disambiguify
                        logger.debug("More than one choice for %s: %s" % (n, [m.name for m in matches]))

                        # Check if action has a filter that helps narrow it down
                        # e.g. the 'get' action could ignore what's in the inventory, only in ambiguous cases
                        if action.ambiguity_filter:
                            matches[:] = action.ambiguity_filter(matches)
                            logger.debug("%s ambiguity filter used to narrow matches down to %s" % (action, [m.name for m in matches]))

                    if len(matches) > 1:
                        # Quit the parser, passing back info about the ambiguity
                        s = "Did you mean %s?" % util.inflect.join([m.the_str for m in matches], conj='or')
                        raise AmbiguityError(s, Ambiguity(verb, pairs, 'NN', i, j))

                    else:
                        # A single match
                        n = matches[0]

                    if except_flag:
                        exceptions.add(n)
                targets[i].nouns.append(n)

            # remove 'None' items
            targets[i].nouns = filter(None, targets[i].nouns)

            if all_flag:
                logger.debug("got 'all' command with exceptions %s:" % exceptions)
                # construct a set of all currently visible things
                all_things = things.PlaceheldSet(k for k in session.things if k.visible)
                all_things.remove(self._game.pc)
                all_things.update(targets[i].nouns)

                for e in exceptions:
                    try:
                        all_things.remove(e)
                    except ValueError: # excepted item not present
                        pass
                targets[i].nouns = AllThingList(all_things)


            # expand single noun lists
            if len(targets[i].nouns) == 1:
                targets[i].nouns = targets[i].nouns[0]
            elif not targets[i].nouns:
                targets[i].nouns = None

        # Special case: action is a game keyword -- add session as target
        try:
            if action_is_keyword and len(targets) == 1 and not targets[0].nouns and not targets[0].prep:
                targets[0].nouns = session
        except NameError:
            pass

        return action, targets



    def parse(self, line, session=None, ambiguity=None):
        """
        Parse the input. Either yield a tuple of action and arguments to call,
        or raise a ParseError with a message for the user.
        
        This is a generator that will yield one command at a time. However,
        a ParseError will discard all following sentences.
        
        ambiguity: an Ambiguity object with info about a previous ambiguous
        statement.
        
        """

        session = session or self._game.current_session

        if line:
            line = line.strip()
        if not line:
            raise ParseError("What?")

        # Split input up into sentences. Evaluate each sentence as a separate
        # command, but stop on an unrecognized / ineffective command
        # For now split on periods and the word "then"
        # TODO: it may be desirable to split differently, e.g. some commas could have the same meaning as periods.
        # TODO: 'then' could be used in character commands
        for sentence in re.split('\.+|,?then +', line):

            if not sentence:
                continue

            self.fill_word_lists(session)

            # Convert sentence into tagged tokens
            tags = self.lex(sentence, ambiguity)
            logger.debug("Have tags %s" % tags)

            # Everything now has a POS. Try to form the tuples.
            verb, pairs = self.form_tuples(tags)
            logger.debug('Have verb %s, pairs %s' % (verb, pairs))

            # Should now have verb, prepositions, and nouns as TargetPairs of plain strings
            # Check if the input could be disambiguating
            # If so, substitute the word and parse the new input
            if ambiguity:
                logger.debug('Trying to disambiguate for {}'.format(ambiguity.word_type))
                verb, pairs = self.replace_ambiguity(verb, pairs, ambiguity)
                ambiguity = None # remove ambiguity for subsequent sentences

            # Now convert strings in target pairs to Actions and Things
            action, targets = self.words_to_objects(verb, pairs, session)
            logger.debug('Have action %s, targets %s' % (action, targets))

            # Find a handler for the action
            try:
                handlers = action.find_handlers(targets)
            except AmbiguityError as e:
                # ambiguous preposition
                e.ambiguity.pairs = pairs
                raise AmbiguityError(e.message, e.ambiguity)

            if not handlers and len(pairs) == 1:
                # Check if we could ask about target, if none was given
                # for now this only works for handlers with one target pair
                if not any(p.nouns for p in pairs):
                    # check if there is a handler with some single noun in any place
                    possible = [h for h in action.handlers if len(h) == 1
                                and (targets[i].prep == k.prep for i, k in enumerate(h))]
                    if(possible):
                        s = action.interrogative.format(action=verb + (''.join((' ' + p.prep if p.prep else '') for p in pairs)))
                        raise AmbiguityError(s, Ambiguity(verb, pairs, 'NN', 0, 0))

                # check if user tried to pass a list to a handler that won't accept multiples
                elif isinstance(targets[0].nouns, list) and action.find_handlers([actions.TargetPair(targets[0].prep, targets[0].nouns[0])]):
                    raise ParseError('You can\'t use multiple objects with "%s".' % verb)

            if not handlers:
                raise ParseError("You can't do that.")


            yield sentence, handlers, targets




    def things_from_noun(self, noun, session):
        """
        Get a list of possible Thing references from a noun string.
        
        Usually this should give a list of length 1, but in ambiguous cases
        multiple Things will be returned.
        
        In rare cases where the noun is not a Thing at all, raise a ParseError.
        If such a Thing is merely not visible in the given location, return an
        empty list.
        """

        if not noun:
            return None

        matches = set()

        for thing in session.things:
            names = [thing.name] + [s for s in thing.synonyms]
            if noun in names:
                matches.add(thing)
            else:
                # maybe it's a partial match
                # e.g. "brush" when "hair brush" is a name
                noun_words = noun.split()
                for name in names:
                    # check if noun words exist as a sublist of the name's words
                    if util.check_sublist(name.split(), noun_words):
                        matches.add(thing)

        # Special cases: directions and room nouns
        if noun in self._game.room_nouns:
            matches.add(self._game.pc.location)

        if not matches:
            for d in self._game.directions:
                if noun in self._game.directions[d]:
                    matches.add(d)

        if not matches:
            # This should rarely happen
            # it could happen if "except" comes before "all" for example
            raise ParseError("I don't understand '%s' used that way." % noun)

        # Narrow down to things currently within reach
        matches = [c for c in matches if c.visible]
        return matches



class Ambiguity(object):
    """ 
    Structure to hold information about a previous ambiguous command, which the
    parser is trying to clarify
    """

    def __init__(self, verb, pairs, word_type, index=0, noun_index=0):
        self.verb = verb # the verb from the original command
        self.pairs = pairs # the TargetPairs from the original command
        self.index = index # the position of the TargetPair containing the first ambiguous word
        self.noun_index = noun_index # if the ambiguous word is a noun, its position in the nouns list
        self.word_type = word_type # the part of speech (can be 'NN' for noun or 'IN' for preposition)

    def __eq__(self, other):
        try:
            return self.__dict__ == other.__dict__
        except AttributeError:
            return False
    def __ne__(self, other):
        return not self == other



