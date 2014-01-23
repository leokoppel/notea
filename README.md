No Tea is an experimental interactive fiction engine and interpreter for Python.

If you want to write a text adventure, use a framework such as [Inform][1], [TADS][2] or [Hugo][3]. Those are mature systems which include not only compilers and interpreters but map editors, debuggers, and IDEs. This is just a personal project. 

  [1]: http://inform7.com/
  [2]: http://www.tads.org/
  [3]: http://www.generalcoffee.com/index_noflash.php?content=hugo
  
The idea was simply to write a Python text game interpreter, where the games themselves were written in Python. This removes the need for a compiler and saves the game author (programmer) from having to learn a new language (even if it tries to use English, as with Inform). It also lets the author use arbitrary code in runtime logic, instead of relying on engine functionality.

Take this [example](http://inform7.com/learn/eg/dm/source_26.html) from Inform:

> The haystack is a fixed in place thing in the outdoors. "A heap of grubby hay is piled against one wall." Understand "heap" or "hay" or "grubby" or "heap of grubby hay" as the haystack. The haystack is flammable.

In No Tea you would define:

	haystack = Thing(['haystack', 'heap of grubby hay'], "A heap of grubby hay is piled against one wall.", location=outdoors)
    haystack.flammable = True
    

##Engine Basics
Initialize a game:

    from notea import Game
    mygame = Game('My game')


Create a room and fill it with items:

    from notea import Room, Thing, Item
	bedroom = Room('Bedroom',
                   """
                   Your bedroom is as messy as ever.
                   """)
    with bedroom:
    	bed = Thing('bed')
        desk = Thing('desk')
        cube = Item("Rubik's cube", 'One of those multi-coloured cube puzzles from your childhood.')

Descriptions can span multiple lines; extra  whitespace is removed. Using the `with` keyword lets you place things in the room without supplying a `location` argument. Note that Item is a subclass of Thing which is by default gettable by the player.

Place the player character in the bedroom to start:

	mygame.pc.place(bedroom)
    
Define a custom action:

	@cube.on('solve')
    def solve_cube():
    	mygame.narrate("You never could solve the stupid thing.")

Create some more rooms and connect them:

	kitchen = Room('kitchen', 'This is where you make food.')
	hall = Room(['Hall', 'Hallway'], 'The hallway is rather plain. Your bedroom is to the north, and the kitchen is east.', {'n':bedroom, 'e':kitchen})

Run some code on game start:

	@game.on_start()
	def on_start():
		game.narrate('You wake up.')
        game.do('look')
        
Then start the game:

	mygame.start()
    
By default, this will start the console UI, giving this output (with example input):

>You wake up.
>
>Bedroom  
>Your bedroom is as messy as ever.
>
>\>_examine cube_  
>One of those multi-coloured cube puzzles from your childhood.
>
>\>_get cube. solve cube._  
>Gotten.  
>You never could solve the stupid thing. 

###Advanced example: extending the default actions

Let's say we wanted the room to be dark, and the player unable to see, until they turned on the light. No Tea currently doesn't have this functionality built in, but it can be added:

First, extend the Room class with a 'dark' property. Let's make only the bedroom dark:
	
    Room.dark = False
	bedroom.dark = True
    
Now we'll use a *group handler*: actions can be assigned *groups* and those groups can have handlers which are called before the individual action handlers. One group which is already assigned to actions by default (in `default_actions.py`) is `'sight'`, which applies to the `look` and `examine` actions.

	@game.on_group('sight')
	def too_dark(*things):
 	   if game.pc.location.dark:
			if things:
            	# player tried to target a thing
    	    	game.narrate("It's too dark to see!")
        	else: # player used action by itself
            	game.narrate("It is pitch black.")
            return True  # Cancel any subsequent handlers
    
Then, make an object which toggles the darkness:
	
    lamp = Thing(['light', 'lamp'], location=bedroom)
    
    @game.on(['turn on', 'switch on', 'activate'], lamp)
    def turn_on_lamp(l):
        if game.pc.location.dark:
            game.pc.location.dark = False
            game.narrate("Good idea. The light is now on.")
            game.do('look')
        else:
            game.narrate("It's already on.")
            
    @game.on(['turn off', 'switch off', 'deactivate'], lamp)
    def turn_off_lamp():
        game.narrate("What would be the point?")
        
Our game might now produce the following output:

>You wake up.
>
>It is pitch black.
> 
>\>_examine cube_   
>It's too dark to see!  
>
>\>_turn on light_  
>Good idea. The light is now on.
>
>Bedroom  
>Your bedroom is as messy as ever.
>
>\>_examine cube_  
>One of those multi-coloured cube puzzles from your childhood.


###Episodes
###UIs
###Saving the game

Further examples to be added. See the source and tests/ directory for some more functionality.

