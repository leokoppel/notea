"""
Example replicating the start of the great Hitchhiker's Guide text adventure
"""

import notea
from notea import Game, Thing, Item, Room, Character, PlayerCharacter

game = Game("H2G2 Example")
game.pc = PlayerCharacter("Arthur Dent")

# We'll use an attribute of Rooms to keep track of whether it's bright enough to
# see, though we can do this in other ways
Room.dark = True


@game.on_group('sight')
def too_dark(*things):
    """
    This handler is called before any actions in the 'sight' group.
    If it returns True, no further handlers are called.
    """
    if game.pc.location.dark:
        if things: # player tried to target a thing
            game.narrate("It's too dark to see!")
        else: # player used action by itself
            game.narrate("It is pitch black.")
        return True

# Create a room, which is automatically bound to the Game.
# The description can use template logic, and extra whitespace is automatically removed
# Enclosing words with angle brackets automatically creates a non-interactive Thing (useful for "background" items)
bedroom = Room('Bedroom',
               """
               The bedroom is a mess. It is a small bedroom with a <faded carpet>
               and <old wallpaper>. There is a <washbasin>, a <chair>
               [- if not T('tatty dressing gown').moved] with a tatty dressing gown slung over it[endif],
               and a window with the curtains drawn. Near the exit leading south is a phone.
               """)


# Using 'with' automatically places the items in the room (unless we provide a contradicting 'location' argument!)
with bedroom:
    bedroom.dark = True

    # Create an object that's placed in the bedroom. We can list several synonyms for it's name
    lamp = Thing(['light', 'lamp'])

    # Define custom action handlers for turning the lamp on and off
    @game.on(['turn on', 'switch on', 'activate'], lamp)
    def turn_on_lamp(l):
        if game.pc.location.dark:
            game.pc.location.dark = False
            game.narrate("Good start to the day. Pity it's going to be the worst one of your life. The light is now on.")
            game.do('look')
        else:
            game.narrate("It is.")
    @game.on(['turn off', 'switch off', 'activate'], lamp)
    def turn_off_lamp():
        game.narrate("Useless.")

    gown = Item(['tatty dressing gown', 'robe', 'pocket'],
                # Note the cheat - 'pocket' is a synonym for 'gown' to easily allow either 'look in pocket' or 'look in gown',
                # but this does allow 'put on pocket' (as in the original game). That's OK.
                """
                The dressing gown is faded and battered, and is clearly a garment which has
                seen better decades. It has a pocket and a small loop at the
                back of the collar.
                """,
                container=True,
                a_str='your gown', the_str='your gown')
    gown.standout = False # since we mentioned the gown in the room description, we don't want it to automatically be listed


    bed = Thing('bed')
    bed.mountable(['lie on', 'lie in', 'sit on', 'sit in'], reachable_things=[lamp])
    bed.exit_string = "Very difficult, but you manage it. The room is still spinning. It dips and sways a little."

# Define the gown's contents. Again, 'with' automatically places the objects in the gown.s
with gown:
    Item("a thing your aunt gave you which you don't know what it is")
    Item(['a buffered analgesic', 'pill'])
    Item('pocket fluff')


porch = Room('Front Porch', 'The front!', {'n':bedroom},)
front = Room('Front of House', connections={'n':porch})
rear = Room('Back of House', connections={'se':front, 'sw':front})


@game.on_start()
def on_start():
    game.narrate("""
                No Tea: pure Python text adventure engine (<a href="https://github.com/leokoppel/notea/">github.com/leokoppel/notea</a>).
                This example replicates the beginning of The Hitchhiker's Guide to the Galaxy (Infocom 1984).
                It is a work in progress!
                                
    
                You wake up. The room is spinning very gently round your head.
                Or at least it would be if you could see it which you can't.
                """)
    game.do('look')

def main():
    game.pc.place(bedroom)
    bed.do('lie in') # start the game in the bed

#     game.start()
    game.ui = notea.ui.WebUI()
    game.ui.app.config['SECRET_KEY'] = 'secret'
    game.start(port=5000)



if __name__ == '__main__':
    exit(main())
