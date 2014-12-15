
jQuery(function($, undefined) {
    var ws;
    var term = {
        _term : $('#terminal'),
        _out : $('#terminal-output'),
        send : function(msg) {
            ws.send(msg);
        },
        echo : function(msg, fade, userinput) {
           fade = (fade === undefined) ? 500 : (fade || 0);
           var added = $('<div/>');
           if(userinput) {
               added.append($('<p class="user-input"/>').text('>' + msg));
           } else {
               added.html(msg);
           }
           added.hide().appendTo(this._out).fadeIn(fade);
           this.scrollBottom();
        },
        exec : function(msg) {
            this.echo(msg, 0, true);
            this.send(msg);
        },
        scrollBottom : function() {
            $(this._term).scrollTop($(this._term)[0].scrollHeight);
        },
    };
    
    cmd = $('#cmd').cmd({
        prompt: '>',
        width: '100%',
        commands: function(command) {
            term.exec(command);
        },
        keydown : function(e) {
            term.scrollBottom();
        }
    });
    
    // lose command line focus when click outside of terminal
    $('#terminal').click(function(e) {
        cmd.enable();
        e.preventDefault();
        e.stopPropagation();
    });
    $(document).click(function(e) {
        cmd.disable();
    });
    
    if ("WebSocket" in window) {
        ws = new WebSocket("ws://" + document.domain + ":" + WS_PORT +"/game");
        ws.onmessage = function(msg) {
            data = $.parseJSON(msg.data);
            $('.value-score').text(data.sessiondata.score);
            $('.value-moves').text(data.sessiondata.moves);
            term.echo(data.output);
        };
    } else {
        term.echo("WebSocket not supported.");
    }
    
    
    /* Compass rose commands */
   $('.compass-dir:not(.compass-center) a').click(function(e) {
       e.preventDefault();
       // bit of a hack for brevity, depends on 'compass-nw', etc class being last.
       var direction = $(this).closest('.compass-dir').attr('class').split('-').pop().toUpperCase();
       term.exec(direction);
   });
   $('.compass-center a').click(function(e) {
       e.preventDefault();
       term.exec('look');
   });
   
   /* expand help */
  $('.expand-link').click(function(e) {
     e.preventDefault();
     $($(this).attr('href')).fadeToggle(500);     
      
  });
  $('.expand-content').hide();
}); 