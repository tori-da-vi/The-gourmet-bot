import logging
from typing import Dict
import pandas as pd
import re
import os
import requests
from dotenv import load_dotenv

from telegram import (
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    Update, 
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()
bot_token = os.getenv("Token")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

CHOOSING, INGRED_SEARCH, NAME_SEARCH = range(3)

reply_keyboard_start = [
    ["Let's go!", "About me"],
    ["Stop"],
]

reply_keyboard_choice = [
    ["Find a recipe by the ingredients"],
    ["Find a recipe by the name of the dish"],
    ["Stop", "Start over"],
]

reply_keyboard_ingredients = [
        [
            "Chicken", "Meat", "Fish", "Eggs",
        ],
        [
            "Buckwheat", "Rice", "Cheese", "Potato",
        ],
        [
            "Tomato", "Cucumber", "Zucchini", "Eggplant",
        ],
         [
            "Stop the bot", "Start over", "I'm done!", "Cancel the last",
         ]
    ]

reply_keyboard_dishes = [
        [
            "Lasagna", "Borscht", "Carbonara",
        ],
        [
            "Burger", "Meatballs", "Greek salad",
        ],
         [
            "Fried eggs", "Pilaf", "Ratatouille",
         ],
         [
            "Spaghetti bolognese", "Oatmeal", "Fish and chips",
         ],
         [
            "Stop the bot", "Start over",
         ]
    ]

reply_keyboard_dish_react = [
    ["One more recipe!"],
    ["Nice, thanks!", "Start over"],
]

markup_start = ReplyKeyboardMarkup(reply_keyboard_start, one_time_keyboard=True)
markup_choice = ReplyKeyboardMarkup(reply_keyboard_choice, one_time_keyboard=True)
markup_dish_react = ReplyKeyboardMarkup(reply_keyboard_dish_react, one_time_keyboard=True)
markup_ingredients = ReplyKeyboardMarkup(reply_keyboard_ingredients, one_time_keyboard=True)
markup_dishes = ReplyKeyboardMarkup(reply_keyboard_dishes, one_time_keyboard=True)


def ingred_to_str(user_data: Dict[str, str]) -> str:
    return ", ".join(user_data["food"])


def no_commas(text: str) -> list:
    lst = text.split(",")
    for i in range(len(lst)):
        lst[i] = lst[i].lower().strip()
    return lst

def no_repeat(text: list, lst: list) -> list:
    for word in text:
        if word in lst:
            text.remove(word)
    return text


async def find_dish_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.isfile("recipes.csv"):
        await update.message.reply_text("Downloading my database. It takes 5-20 minutes depending on the Internet connection")
        url = 'https://vk.com/s/v1/doc/EVMW2wemDp8TXO4csZ4qi5G77E-vW1qlNDovRhKVJJW9JmZ1ZZA'
        response = requests.get(url)
        with open('recipes.csv', 'wb') as f:
            f.write(response.content)
    user_data = context.user_data
    if "food" not in user_data:
        user_data["food"] = []
        user_data["food"].append(update.message.text.lower())
    user_request = ingred_to_str(user_data)
    if any(sign in user_request for sign in "()[]/}{"):
        await update.message.reply_text('The request must not contain bracket characters!', reply_markup = markup_dishes)
        user_data.clear()
        return NAME_SEARCH
    await update.message.reply_text(f'I\'m looking for "{user_request}". It might take some time')
    if "count" not in user_data:
        user_data["count"] = 0
        user_data["chunk_number"] = 0
        user_data["index_in_chunk"] = 0
    count = user_data["count"]
    last_ind = user_data["index_in_chunk"]
    last_chunk = user_data["chunk_number"]

    chunk_size = 10000
    current_chunk = 0
    chunks = pd.read_csv('recipes.csv', chunksize=chunk_size)
    for chunk in chunks:
        current_chunk += 1
        if current_chunk < last_chunk:
            continue
        if current_chunk == last_chunk:
            ind = last_ind
        else:
            ind = 0

        suit = chunk[chunk["title"].str.contains(f"(?i)(?:^|\s){user_request}(?:$|\s)", na = False, regex = True)]
        if not suit.dropna().empty:
            if count == 0:
                await update.message.reply_text(f'The recipes that match "{user_request}":')
            while count == user_data["count"] or too_much_words == True:
                try:
                    too_much_words = False
                    await update.message.reply_text(f"{count+1}. {suit.iloc[ind]['title']}")
                    count += 1
                    ingredients = str(suit.iloc[ind]['ingredients'])
                    ingredients = ingredients.replace('",', '\n').replace('"', '').replace('[', ' ').replace(']', '')
                    if len(ingredients) > 4096:
                        await update.message.reply_text("This recipe is too complicated for me. Use the Internet to learn about cooking it")
                        too_much_words = True
                        count += 1
                        continue
                    await update.message.reply_text(f"The ingredients you need:\n{ingredients}")
                    directions = str(suit.iloc[ind]['directions'])
                    directions = directions.replace('["', '').replace('"]', '').replace('"', '').replace("\\u00b0", chr(176)+"C").replace(".,", ".")
                    if len(directions) > 4096:
                        await update.message.reply_text("This recipe is too complicated for me. Use the Internet to learn about cooking it")
                        count += 1
                        too_much_words = True
                        continue
                    await update.message.reply_text(f"Follow these steps to prepare {suit.iloc[ind]['title']}:\n{directions}")
                    ind += 1
                except IndexError:
                    count = 0
                    break
        else:
            count = 0
        if count != user_data["count"]:
            break
    if count == 0:
        await update.message.reply_text(f'Unfortunately, nothing was found for "{user_request}".'
                                        ' If you want to try again, select the appropriate option.', reply_markup=markup_choice)
        return CHOOSING
    else:
        user_data["count"] = count
        user_data["chunk_number"] = current_chunk
        user_data["index_in_chunk"] = ind
    if count != 0 and too_much_words == False:
        await update.message.reply_text("What do you think?", reply_markup=markup_dish_react)

    return NAME_SEARCH


async def find_dish_by_ingreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.isfile("recipes.csv"):
        await update.message.reply_text("Downloading my database. It takes 5-20 minutes depending on the Internet connection")
        url = 'https://vk.com/s/v1/doc/EVMW2wemDp8TXO4csZ4qi5G77E-vW1qlNDovRhKVJJW9JmZ1ZZA'
        response = requests.get(url)
        with open('recipes.csv', 'wb') as f:
            f.write(response.content)
    user_data = context.user_data
    if "food" not in user_data or user_data["food"] == []:
        await update.message.reply_text("Pick something!", reply_markup=markup_ingredients)
        return INGRED_SEARCH
    user_request = user_data["food"]
    await update.message.reply_text(f'I\'m looking for "{ingred_to_str(user_data)}". It might take some time')
    if "count" not in user_data:
        user_data["count"] = 0
        user_data["chunk_number"] = 0
        user_data["index_in_chunk"] = 0
    count = user_data["count"]
    last_ind = user_data["index_in_chunk"]
    last_chunk = user_data["chunk_number"]

    chunk_size = 10000
    current_chunk = 0
    chunks = pd.read_csv('recipes.csv', chunksize=chunk_size)
    for chunk in chunks:
        current_chunk += 1
        if current_chunk < last_chunk:
            continue
        if current_chunk == last_chunk:
            ind = last_ind
        else:
            ind = 0
        suit = chunk
        for food in user_request:
            suit = suit[suit["ingredients"].str.contains(f'[ "]{food}s[" ]|[ "]{food}es[" ]|[ "]{food}[" ]', na = False, flags=re.IGNORECASE, regex=True)]
        if not suit.dropna().empty:
            if count == 0:
                await update.message.reply_text(f'The recipes that match "{ingred_to_str(user_data)}":')
            while count == user_data["count"] or too_much_words == True:
                try:
                    too_much_words = False
                    await update.message.reply_text(f"{count+1}. {suit.iloc[count]['title']}")
                    ingredients = str(suit.iloc[count]['ingredients'])
                    ingredients = ingredients.replace('",', '\n').replace('"', '').replace('[', ' ').replace(']', '')
                    if len(ingredients) > 4096:
                        await update.message.reply_text("This recipe is too complicated for me. Use the Internet to learn about cooking it")
                        count += 1
                        too_much_words = True
                        continue
                    await update.message.reply_text(f"The ingredients you need:\n{ingredients}")
                    directions = str(suit.iloc[count]['directions'])
                    directions = directions.replace('["', '').replace('"]', '').replace('"', '').replace("\\u00b0", chr(176)+"C").replace(".,", ".")
                    if len(directions) > 4096:
                        await update.message.reply_text("This recipe is too complicated for me. Use the Internet to learn about cooking it")
                        count += 1
                        too_much_words = True
                        continue
                    await update.message.reply_text(f"Follow these steps to prepare {suit.iloc[count]['title']}:\n{directions}")
                    count += 1
                    ind += 1
                except IndexError:
                    count = 0
                    break
        else:
            count = 0
        if count != user_data["count"]:
            break
    if count == 0:
        await update.message.reply_text(f'Unfortunately, nothing was found for "{ingred_to_str(user_data)}".'
                                        ' If you want to try again, select the appropriate option.', reply_markup=markup_choice)
        return CHOOSING
    else:
        user_data["count"] = count
        user_data["chunk_number"] = current_chunk
        user_data["index_in_chunk"] = ind
    if count != 0 and too_much_words == False:
        await update.message.reply_text("What do you think?", reply_markup=markup_dish_react)

    return INGRED_SEARCH


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data.clear()
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi, {user.mention_html()}! I'm Gourmet Bot. Glad to meet you on my cooking platform! 🎉",
        reply_markup=markup_start,
    )

    return CHOOSING


async def first_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data.clear()
    await update.message.reply_text("Before we start, let's make it clear: are you going to "
                                    "find a recipe by the ingredients or by the name of the dish?\n"
                                    "Please, select the appropriate button!", reply_markup = markup_choice)
    
    return CHOOSING

async def name_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data.clear()
    await update.message.reply_text("Great! Type the name of your dish or "
                                    "choose from the suggested 😊", 
                                    reply_markup = markup_dishes)

    return NAME_SEARCH


async def ingred_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data.clear()
    await update.message.reply_text("Nice! Choose "
                                    "the ingredients you want to use or type them separated by commas 😌", 
                                    reply_markup = markup_ingredients)

    return INGRED_SEARCH


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        'Wow, you want to know more about me! '
        'I\'m Gourmet Bot developed by the team of NRU HSE students tired of the constant search for the delicious recipes. '
        "If you want to cook something speacial or just looking for the inspiration, you're in the right place! 🍽️\n"
        "I'm ready to help you find the right recipe for any occasion. Just tell me what you're interested in - "
        "whether it's sweet or salty, meat or vegetable, a quick dinner or a holiday treat - "
        "and we'll find the perfect recipe together!\nSo let our cooking adventure begin! 💌\n\n"
        "You can simply type what you've got in a fridge and I'll find the dish with these ingredients and tell you what else to buy. "
        "But if you already know what to cook and are looking for a specific recipe,"
        "type the name of the dish and I'll try to find the right one.\n\n"
        "Come on, choose something and let's start cooking!", reply_markup=markup_start,
    )


    return CHOOSING


async def more_ingred(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_request = update.message.text
    if any(sign in user_request for sign in "()[]/}{"):
        await update.message.reply_text('The request must not contain bracket characters!', reply_markup = markup_ingredients)
        return INGRED_SEARCH
    text = no_commas(user_request)
    user_data = context.user_data
    if "food" not in user_data:
        user_data["food"] = []
    text = no_repeat(text, user_data["food"])
    user_data["food"].extend(text)

    await update.message.reply_text(
        f"Awesome! Here's what I already have: {ingred_to_str(user_data)}\nWant to choose anything else?\n",
        reply_markup=markup_ingredients)
    return INGRED_SEARCH



async def cancel_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    if "food" not in user_data or user_data["food"] == []:
        await update.message.reply_text(
        "Nothing to remove! Pick something!",
        reply_markup=markup_ingredients)
    else:
        user_data["food"].pop()
        if len(user_data["food"]) > 0:
            await update.message.reply_text(
                f"Removed the last ingredient. Here's what I've got: {ingred_to_str(user_data)}\nWant to choose anything else?\n",
                reply_markup=markup_ingredients)
        else:
            await update.message.reply_text(
                f"Removed the last ingredient. Nothing's chosen now!\n",
                reply_markup=markup_ingredients)
    return INGRED_SEARCH



async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    if "choice" in user_data:
        del user_data["choice"]
    await update.message.reply_text(
        f"See you! Happy cooking! 😉",
        reply_markup=ReplyKeyboardRemove(),
    )

    user_data.clear()
    return CHOOSING



def main() -> None:
    application = Application.builder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                MessageHandler(
                    filters.Regex("(?i)^Find a recipe by the name of the dish$"), name_choice
                ),
                MessageHandler(
                    filters.Regex("(?i)^Find a recipe by the ingredients$"), ingred_choice
                ),
                MessageHandler(filters.Regex("(?i)^About me$"), help),
                MessageHandler(filters.Regex("(?i)^Let's go!$"), first_choice),

            ],

            NAME_SEARCH: [
                MessageHandler(filters.TEXT & ~ (filters.Regex("(?i)^Stop$") | filters.Regex("(?i)^Start over$") |
                                                 filters.Regex("(?i)^Find a recipe by the ingredients$") |
                                                 filters.Regex("(?i)^Stop the bot$") | 
                                                 filters.Regex("(?i)^One more recipe!$") |
                                                 filters.Regex("(?i)^Nice, thanks!$") |
                                                 filters.Regex("(?i)^Find a recipe by the name of the dish$") |
                                                 filters.Regex("^/.*$")), find_dish_by_name),
                MessageHandler(filters.Regex("(?i)^One more recipe!$"), find_dish_by_name),
                MessageHandler(filters.Regex("(?i)^Nice, thanks!$"), stop),
            ],

            INGRED_SEARCH: [
                MessageHandler(filters.TEXT & ~ (filters.Regex("(?i)^I'm done!$") | filters.Regex("(?i)^Start over$") |
                                                 filters.Regex("(?i)^Stop the bot$") | 
                                                 filters.Regex("(?i)^Nice, thanks!$") |
                                                 filters.Regex("(?i)^One more recipe!$") |
                                                 filters.Regex("(?i)^Cancel the last$") | filters.Regex("^/.*$")),
                                                 more_ingred),
                MessageHandler(filters.Regex("(?i)^Cancel the last$"), cancel_last),
                MessageHandler(filters.Regex("(?i)^I'm done!$") | filters.Regex("(?i)^One more recipe!$"), find_dish_by_ingreds),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("(?i)^Start over$"), first_choice),
            MessageHandler(filters.Regex("/start"), start),
            MessageHandler(filters.Regex("/help"), help),
            MessageHandler(filters.Regex("/stop" ) | filters.Regex("(?i)^Stop the bot$"), stop),
            MessageHandler(filters.Regex("(?i)^Stop$"), stop),
            MessageHandler(filters.Regex("(?i)^Nice, thanks!$"), stop),
            ],
    )

    application.add_handler(conv_handler)

    application.run_polling(allowed_updates = Update.ALL_TYPES)


if __name__ == "__main__":
    main()