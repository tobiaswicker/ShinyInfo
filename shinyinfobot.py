#!/usr/bin/env python3
import json
import logging
import os
import pickle
import urllib.request

import requests

from lxml import html

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.error import BadRequest
from telegram.ext import CommandHandler, Updater, CallbackContext, PicklePersistence, CallbackQueryHandler
from telegram.utils.request import Request

from config import bot_token, log_file, shiny_data

# enable logging
logging.basicConfig(format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    handlers=[logging.FileHandler(filename=log_file, mode='a'),
                              logging.StreamHandler()])
logger = logging.getLogger(__name__)

shiny = {}

supported_sites = ['pogoapi.net', 'gamepress.gg']


def get_shinies_pogoapi_net():
    shiny_list = []

    url = "https://pogoapi.net//api/v1/shiny_pokemon.json"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())

        for dex_id in data.keys():
            dex_id = int(dex_id)
            if dex_id not in shiny_list:
                shiny_list.append(dex_id)

    shiny_list.sort()

    return shiny_list


def get_shinies_gamepress_gg():
    """Load all shiny pokemon"""
    url = 'https://pokemongo.gamepress.gg/pokemon-go-shinies-list'
    raw = requests.get(url)
    data = html.fromstring(raw.content)
    shiny_links = data.xpath("//tr[contains(@class, 'Raids') or contains(@class, 'Wild') "
                             "or contains(@class, 'Evolution') or contains(@class, 'Eggs') "
                             "or contains(@class, 'Research') or contains(@class, 'Nesting') "
                             "or contains(@class, 'Mystery')]//a")

    shiny_list = []

    for link_tag in shiny_links:
        link = link_tag.attrib['href']
        dex_id = int(link.replace('/pokemon/', '').replace('-alolan', ''))
        if dex_id not in shiny_list:
            shiny_list.append(dex_id)

    shiny_list.sort()

    return shiny_list


def check_shinies(context: CallbackContext):

    global shiny
    new_shiny = {}

    # noinspection PyProtectedMember
    dp = context._dispatcher
    chats = dp.chat_data.keys()

    new_shiny_info = ""

    for site in supported_sites:
        # init shiny list if it does not exist
        if site not in shiny:
            shiny[site] = []
        # init new shiny list
        new_shiny[site] = []
        # iterate shiny list for site
        for dex_id in globals()[f"get_shinies_{site.replace('.', '_')}"]():
            # add id if not previously added
            if dex_id not in shiny[site]:
                shiny[site].append(dex_id)
                new_shiny[site].append(dex_id)
        # inform about new shinies
        if new_shiny[site]:
            new_shiny_str = ", ".join(str(x) for x in new_shiny[site])
            new_shiny_info += f"New shiny pokémon in {site}:\n" \
                              f"{new_shiny_str}\n\n"

    # check if new shinies have been found
    if new_shiny_info:
        # store the changed data
        with open(shiny_data, 'wb') as f:
            pickle.dump(shiny, f)

        # check for differences in shiny sources
        for source in supported_sites:
            for other_source in supported_sites:
                diff = list(set(shiny[source]) - set(shiny[other_source]))
                diff.sort()
                # show differences
                if diff:
                    diff_str = ", ".join(str(x) for x in diff)
                    new_shiny_info += f"The following IDs are listed as shiny by {source}, but not by " \
                                      f"{other_source}:\n" \
                                      f"{diff_str}\n\n"
        # inform all subscribers about new shinies and differences in source
        for chat_id in chats:
            try:
                context.bot.send_message(chat_id=chat_id, text=new_shiny_info)
                logger.info(f"Sending shiny info to chat #{chat_id}.")
            except BadRequest as e:
                logger.warn(f"Failed to send shiny info to chat #{chat_id}.")
                pass


def list_shinies(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    chat_data = context.chat_data

    query = update.callback_query

    user_shiny_sources = list(set(supported_sites) - set(chat_data['source'] if 'source' in chat_data else []))
    if not user_shiny_sources:
        text = "You don't have any source selected."
        context.bot.answer_callback_query(callback_query_id=query.id, text=text, show_alert=True)
        return

    context.bot.answer_callback_query(callback_query_id=query.id, text="Listing shiny Pokémon.")

    for site in user_shiny_sources:
        shiny_str = f"*{site}*\n"
        if site in shiny and shiny[site]:
            shiny_str += "\n".join(str(x) for x in shiny[site])
        else:
            shiny_str += f"No information about shiny pokémon available."
        context.bot.send_message(chat_id=chat_id, text=shiny_str)


def select_source(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id

    chat_data = context.chat_data

    query = update.callback_query
    params = query.data.split()

    popup_text = None
    if len(params) == 2:
        site = params[1]
        if 'source' not in chat_data:
            chat_data['source'] = [site]
            popup_text = f"Source {site} removed."
        elif site in chat_data['source']:
            chat_data['source'].remove(site)
            popup_text = f"Source {site} added."
        else:
            chat_data['source'].append(site)
            popup_text = f"Source {site} removed."

    text = "Select the sources you would like me to use when informing you about shiny Pokémon.\n" \
           "You are automatically being subscribed to new sources when they come available."

    popup_text = popup_text if popup_text else text

    keyboard = []
    for site in supported_sites:
        button_text = site
        button_text += "" if 'source' in chat_data and site in chat_data['source'] else " ✅️"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"select_source {site}")])

    keyboard.append([InlineKeyboardButton(text="Overview", callback_data='overview')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.answer_callback_query(callback_query_id=query.id, text=popup_text)

    context.bot.edit_message_text(chat_id=chat_id,
                                  message_id=message_id,
                                  text=text,
                                  reply_markup=reply_markup,
                                  parse_mode=ParseMode.MARKDOWN)


def start(update: Update, context: CallbackContext):
    """Start the bot"""
    chat_id = update.effective_chat.id

    context.chat_data['id'] = chat_id

    text = "I will inform you about shiny Pokémon released in Pokémon GO.\n\n" \
           "I can show you information about those existing in the game as well as inform you about new shiny " \
           "Pokémon as soon as they get released.\n" \
           "You can also choose which source I should use to inform you."

    keyboard = [[InlineKeyboardButton(text="List Shiny Pokémon", callback_data="list_shinies")],
                [InlineKeyboardButton(text="Select Shiny Source", callback_data="select_source")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


def error(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    logger.info("Starting Bot.")

    # load shiny history
    global shiny
    if os.path.isfile(shiny_data):
        with open(shiny_data, 'rb') as f:
            shiny = pickle.load(f)

    # request object for bot
    request = Request(con_pool_size=8)
    bot = Bot(token=bot_token, request=request)

    persistence = PicklePersistence(filename='bot_data.pickle')

    # create the EventHandler and pass it the bot's instance
    updater = Updater(bot=bot, use_context=True, persistence=persistence)

    # jobs
    job_queue = updater.job_queue
    job_queue.run_repeating(callback=check_shinies, interval=60, first=0)

    # get the dispatcher to register handlers
    dp = updater.dispatcher

    # /start handler
    dp.add_handler(CommandHandler(callback=start, command='start'))
    dp.add_handler(CallbackQueryHandler(callback=start, pattern='^overview'))

    dp.add_handler(CallbackQueryHandler(callback=list_shinies, pattern='^list_shinies'))
    dp.add_handler(CallbackQueryHandler(callback=select_source, pattern='^select_source'))

    # error handler
    dp.add_error_handler(error)

    # start the bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
