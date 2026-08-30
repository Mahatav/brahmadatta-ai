tell application "Keynote"
	activate
	set deckTheme to theme "Basic White"
	set deckDocument to make new document with properties {document theme:deckTheme}
	tell deckDocument
		set base layout of slide 1 to master slide "Blank"
		tell slide 1
			set bg to make new shape with properties {shape type:rectangle, position:{0, 0}, width:1920, height:1080}
			set object text of bg to ""
		end tell
	end tell
end tell
