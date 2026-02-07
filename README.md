# TimeZoneSwapper
Converts selected text from ET to AWST or vice versa

I work with folks in Western Australia, and I frequently lament having to do the math for timezones between the ET and AWST, even though it should really not be that hard to just add 12 or 13 hours, depending on the time of year. So I thought it would be useful to have a tool that would convert a date from one timezone to another. This would come in handy especially when chatting with someone in the other timezone and talking about setting up a meeting... "how about my tuesday night, your wednesday morning" etc.
 
So here's how it works. There are two scripts. One is in Python (TimeZoneSwapper.py), and it will convert the text in your current timezone to the other timezone. This script is kicked off by an AutoHotKey script (TeamsToggleMute.ahk), using CTRL+ALT+T. So once you select text and hit the hotkey, it will copy the selected text, run the Python script to convert it, then paste it right over the top of the initial text. It will look for dates in formats like this (not case sensitive):
    - "3:30 PM", "15:30", "3pm", "3 PM"
    - "2026-02-03 8:00 AM"
    - "Mar 4 3:30pm"
    - "today 9am", "tomorrow 9am", "yesterday 9am"
    - "next tuesday 3pm", "this fri 10:30"
 
Example. Say you are having a Teams chat conversation with someone and want to set up a meeting for Tuesday night. So you would write:
Tuesday 9pm
and it will return 
Tuesday 9pm (10:00am Wed Feb 11 AWST)
 
The reason it pastes over the text you started with is that I wanted the user to just select text and do the hotkey and be able to keep typing without having to move the cursor before pasting the converted text.
 
Caveats/Notes:
- I entirely vibe coded this and have never worked with Python, so I take zero responsibility for the quality of this code :)
- This should convert from AWST to ET, but I have no way to test it since I am in ET 
- Change your paths in the top of the AHK script for the python executable and the python script
- There is logging available, it is off by default. Enable it if needed for troubleshooting. The line to enable it is near the top of the script
- I tried other approaches like using a Windows shortcut for the Python script with a keyboard shortcut, using PowerToys to handle the launching via keyboard shortcut, and even using Task Scheduler for this, but all those approaches were either not seamless, or ran into permission issues. AutoHotKey was the only way I...er, ChatGPT found that would be completely seamless.
- In the end the real motivation was to go through an exercise with ChatGPT to code something from scratch and work through the process to learn how to get better at prompting, resulting in a tool that should actually be useful (hopefully)
- This doesn't work with text in Obsidian for some reason. Chat GPT and I had some lively discussions trying to get it to work, but in the end I gave up because it is just after Friday 11pm (12:00pm Sat Feb 7 AWST) and I am tired
