#!/usr/bin/env python3
import json
import logging
import os

import telegram
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.error import BadRequest
from telegram.ext import CommandHandler, Updater, CallbackContext, PicklePersistence, CallbackQueryHandler
from telegram.utils.request import Request

from config import bot_token, log_file
from shiny import ShinyManager

# enable logging
logging.basicConfig(format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    handlers=[logging.FileHandler(filename=log_file, mode='a'),
                              logging.StreamHandler()])
logger = logging.getLogger(__name__)


_pokemon = {}


def _load_pokemon():
    """Load all pokemon for various languages"""
    if not _pokemon:
        current_directory = os.path.dirname(os.path.realpath(__file__))
        pokemon_directory = os.path.join(current_directory, 'pokemon')
        for filename in os.listdir(pokemon_directory):
            if filename.endswith(".json"):
                lang_id = filename.replace('.json', '')
                file_path = os.path.join(pokemon_directory, filename)
                with open(file=file_path, mode='r', encoding='utf-8') as f:
                    _pokemon[lang_id] = json.load(f)


def get_pokemon(lang, dex_id):
    """Get pokemon name for a certain language by id"""
    _load_pokemon()

    dex_id = int(dex_id)
    if lang in _pokemon and dex_id < len(_pokemon[lang]) + 1:
        return _pokemon[lang][dex_id - 1]

    return "unknown_pokemon"


def check_shinies(context: CallbackContext):
    # noinspection PyProtectedMember
    dp = context._dispatcher
    chats = dp.chat_data.keys()

    shiny_manager = ShinyManager()
    shiny_manager.load_all_shinies()

    new_shiny_info = ""
    new_shiny = shiny_manager.get_all_new_shinies()

    for site, mons in new_shiny.items():
        if mons:
            new_shiny_str = "\n".join(f"{dex_id} {get_pokemon('en', dex_id)} / {get_pokemon('de', dex_id)}"
                                      for dex_id in mons.keys())
            new_shiny_info += f"Information about new shiny Pokémon have been added to {site}:\n" \
                              f"{new_shiny_str}\n\n"

    # check if new shinies have been found
    if new_shiny_info:
        # inform all subscribers about new shinies and differences in source
        for chat_id in chats:
            try:
                context.bot.send_message(chat_id=chat_id, text=new_shiny_info)
                logger.info(f"Sending info about new shiny pokémon to chat #{chat_id}.")
            except BadRequest as e:
                logger.warning(f"Failed to send info about new shiny pokémon to chat #{chat_id}: {e}.")
                pass

    changed_shiny_info = ""
    changed_shiny = shiny_manager.get_all_changed_shinies()

    for site, mons in changed_shiny.items():
        if mons:
            changed_shiny_info += f"Shiny info on {site} changed for the following Pokémon:\n"

            for dex_id, changed_info in mons.items():
                changed_shiny_info += f"#{dex_id} {get_pokemon('en', dex_id)} / {get_pokemon('de', dex_id)}:\n"
                for attr, old_new_val in changed_info.items():
                    changed_shiny_info += f"`{attr}`{shiny_manager.get_emoji(attr)} changed from " \
                                          f"`{old_new_val[0]}` to `{old_new_val[1]}`\n"

            changed_shiny_info += "\n"

    # check for changed shinies
    if changed_shiny_info:
        for chat_id in chats:
            try:
                context.bot.send_message(chat_id=chat_id, text=changed_shiny_info, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Sending info about changed shiny pokémon to chat #{chat_id}.")
            except BadRequest as e:
                logger.warning(f"Failed to send info about changed shiny pokémon to chat #{chat_id}: {e}.")
                pass


def list_shinies(update: Update, context: CallbackContext):
    """List all shinies for all sources"""
    chat_id = update.effective_chat.id
    user = update.effective_user

    logger.info(f"Listing shinies in chat #{chat_id} for user #{user.id} (@{user.username})")

    chat_data = context.chat_data

    query = update.callback_query

    disabled_sources = chat_data['disabled_sources'] if 'disabled_sources' in chat_data else []

    user_shiny_sources = list(set(ShinyManager.supported_sites) - set(disabled_sources))
    if not user_shiny_sources:
        text = "You don't have any source selected."
        context.bot.answer_callback_query(callback_query_id=query.id, text=text, show_alert=True)
        return

    context.bot.answer_callback_query(callback_query_id=query.id, text="Listing shiny Pokémon.")

    shiny_manager = ShinyManager()

    legend = f"*Legend*\n\n" \
             f"The following emojis symbolize how you can obtain the shiny form of that Pokémon:\n" \
             f"• {shiny_manager.get_emoji('wild')} in the wild\n" \
             f"• {shiny_manager.get_emoji('raid')} through raids\n" \
             f"• {shiny_manager.get_emoji('evolution')} by evolving the pre-stage\n" \
             f"• {shiny_manager.get_emoji('egg')} by hatching eggs\n" \
             f"• {shiny_manager.get_emoji('research')} through quests\n" \
             f"• {shiny_manager.get_emoji('mystery')} by opening a mystery box"
    context.bot.send_message(chat_id=chat_id, text=legend, parse_mode=ParseMode.MARKDOWN)

    for site in user_shiny_sources:
        shinies = shiny_manager.get_shinies(site)
        shiny_str = f"*{site}*\n"
        if shinies:
            shiny_str += "\n".join(f"#{dex_id} {get_pokemon('en', dex_id)} / {get_pokemon('de', dex_id)} "
                                   f"{shiny_manager.get_emojis_for_shiny(pokemon)}"
                                   for dex_id, pokemon in shinies.items())
        else:
            shiny_str += f"No information about shiny pokémon available."

        # ensure message does not exceed telegrams max message length
        while len(shiny_str) > telegram.constants.MAX_MESSAGE_LENGTH:
            # find last line break within bounds
            cut_off_index = shiny_str[:telegram.constants.MAX_MESSAGE_LENGTH].rfind("\n")
            # make sure there is a line break
            if cut_off_index < 0:
                # otherwise just do a hard cut
                cut_off_index = telegram.constants.MAX_MESSAGE_LENGTH
            # get what fits
            fitting_message = shiny_str[:cut_off_index]
            # remove fitting message from original message text
            shiny_str = shiny_str[cut_off_index:]

            context.bot.send_message(chat_id=chat_id, text=fitting_message, parse_mode=ParseMode.MARKDOWN)

        # send whats left
        context.bot.send_message(chat_id=chat_id, text=shiny_str, parse_mode=ParseMode.MARKDOWN)


def select_source(update: Update, context: CallbackContext):
    """Callback for selecting shiny sources"""
    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id
    user = update.effective_user

    chat_data = context.chat_data

    query = update.callback_query
    params = query.data.split()

    popup_text = None
    if len(params) == 2:
        site = params[1]

        logger.info(f"Button for source '{site}' pressed by user #{user.id} (@{user.username})")

        if 'disabled_sources' not in chat_data:
            chat_data['disabled_sources'] = [site]
            popup_text = f"Source {site} removed."
        elif site in chat_data['disabled_sources']:
            chat_data['disabled_sources'].remove(site)
            popup_text = f"Source {site} added."
        else:
            chat_data['disabled_sources'].append(site)
            popup_text = f"Source {site} removed."
    else:
        logger.info(f"Showing source options to user #{user.id} (@{user.username})")

    text = "Select the sources you would like me to use when informing you about shiny Pokémon.\n" \
           "You are automatically being subscribed to new sources when they come available."

    popup_text = popup_text if popup_text else text

    keyboard = []
    for site in ShinyManager.supported_sites:
        button_text = site
        button_text += "" if 'disabled_sources' in chat_data and site in chat_data['disabled_sources'] else " ✅️"
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
