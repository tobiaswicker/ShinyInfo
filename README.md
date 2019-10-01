# ShinyInfo Telegram Bot
ShinyInfo is a [Telegram](https://telegram.org) bot that informs you about shiny Pokémon in Pokémon GO.
It gathers information from different data sources and informs you about new shiny Pokémon as soon as these are added 
to any of the sources. You can request a list of shiny Pokémon and see how each shiny can be obtained. 

Currently [Gamepress.gg](https://pokemongo.gamepress.gg/pokemon-go-shinies-list) and 
[Pogoapi.net](https://pogoapi.net//api/v1/shiny_pokemon.json) are supported. If you know of any other detailed shiny
info page, please create an issue or - even better - a pull request. 

If you don't want to set up your own bot, feel free to use [@ShineInfoBot](https://t.me/ShineInfoBot).

##Features
- list all shiny Pokémon by source and see how they can be obtained.
- automatically subscribe to information about new shiny Pokémon as soon as they get added.

## Installation
1. Clone this repository: `git clone https://github.com/tobiaswicker/ShinyInfo.git`
2. [Download Python 3.x](https://www.python.org/downloads/) if you haven't already
3. Install [Python-Telegram-Bot](https://python-telegram-bot.org) by running `pip install python-telegram-bot` from a 
terminal.
4. Talk to [@BotFather](https://t.me/BotFather) to get a `token`.
5. Rename `config-bot.ini.example` to `config-bot.ini` and edit it. 
   - Replace `BOT_TOKEN` with your bots `token`.
6. Run the bot from a terminal: `python3 shinyinfobot.py`
