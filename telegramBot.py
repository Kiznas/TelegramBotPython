import logging
import telegram
from enum import Enum
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Tuple, Type
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ApplicationBuilder, ContextTypes

# Enable logging for debugging (optional)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

plus_minus_markup = InlineKeyboardMarkup([[InlineKeyboardButton("+", callback_data="+"),InlineKeyboardButton("-", callback_data="-")]])

class CurrentMode(Enum):
    NoneMode = 0
    Header = 1
    Description = 2
    Send = 3
    Card = 4
    Amount = 5
    Cancel = 6

class Filters(Enum):
    group = 0,
    private = 1,
    supergroup = 2

class UserData:
    def __init__(self, user_id, chat_id, message_id, user_first_name=None, user_second_name=None):
        self.UserId = user_id
        self.ChatId = chat_id
        self.MessageId = message_id
        self.UserFirstName = user_first_name
        self.UserSecondName = user_second_name
        self.Header = None
        self.Description = None
        self.CardData = None
        self.CurrentMod = CurrentMode.NoneMode
        self.IsEditing = False
        pass

class LastEventData:
    def __init__(self, chat_id, message_id, header=None, description=None, card_data=None):
        self.ChatId = chat_id
        self.MessageId = message_id
        self.Header = header
        self.Description = description
        self.CardData = card_data

class CardData:
    def __init__(self, card_number=None, money_amount=None):
        self.CardNumber = card_number
        self.MoneyAmount = money_amount
        pass

@dataclass
class RespondData:
    Responds: List[str]
    UserId: int
    ChatId: int
    MessageId: int
    StartingTime: datetime

# Initialize dictionaries to store data
userData = {}
LastEvent = {}
RespondsOnEvent: Dict[Tuple[int, int], 'RespondData'] = {}

# Function to handle the /create command
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name
    user_second_name = update.effective_user.last_name
    chat_id = update.effective_chat.id
    
    # Check if the user is an admin in the group or supergroup
    chat_administrators = await context.bot.get_chat_administrators(chat_id)
    is_admin = any(admin.user.id == user_id for admin in chat_administrators)

    if not is_admin:
        return

    # Ask the user something in private messages with buttons
    keyboard = [
        [InlineKeyboardButton("Заголовок", callback_data="Header"),
         InlineKeyboardButton("Опис", callback_data="Description")],
        [InlineKeyboardButton("Данні карти", callback_data="Card data")],
        [InlineKeyboardButton("✅", callback_data="Yes"),
         InlineKeyboardButton("❌", callback_data="No")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(user_id, "Виберіть опцію:", reply_markup=reply_markup)

    # Store the state that the user is expected to answer
    user_data = UserData(user_id, chat_id, None, user_first_name, user_second_name)
    userData[user_id] = user_data
    
    await try_delete_message(update._bot, update.message.chat_id, update.message.message_id)

# Function to handle the /edit command
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if the user is an admin in the group or supergroup
    chat_administrators = await context.bot.get_chat_administrators(chat_id)
    is_admin = any(admin.user.id == user_id for admin in chat_administrators)

    if not is_admin:
        return
    
    # Check if there is a last event to edit
    if chat_id not in LastEvent or not LastEvent[chat_id]:
        context.bot.send_message(chat_id, "Немає івентів для зміни")
        return

    # Ask the user what to edit
    keyboard = [
        [InlineKeyboardButton("Заголовок", callback_data="Header"),
         InlineKeyboardButton("Опис", callback_data="Description")],
        [InlineKeyboardButton("Данні карти", callback_data="Card Data")],
        [InlineKeyboardButton("Завершити зміни", callback_data="End Edit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(user_id, "Що ви хочете змінити?", reply_markup=reply_markup)

    # Store the state for editing
    user_data = UserData(user_id, chat_id, LastEvent[chat_id].MessageId)
    user_data.CurrentMod = "None"  # Set the mode to "None" initially for editing
    userData[user_id] = user_data
    
    await try_delete_message(update._bot, update.message.chat_id, update.message.message_id)

# Function to handle the /delete command
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if the user is an admin in the group or supergroup
    chat_administrators = await context.bot.get_chat_administrators(chat_id)
    is_admin = any(admin.user.id == user_id for admin in chat_administrators)

    if not is_admin:
        return

    if user_id in userData:
        user_data = userData[user_id]
        if user_data.ChatId == chat_id and user_data.MessageId in LastEvent:
            last_event_data = LastEvent[user_data.MessageId]
            context.bot.delete_message(chat_id=last_event_data.ChatId, message_id=last_event_data.MessageId)
            
    await try_delete_message(update._bot, update.message.chat_id, update.message.message_id)

# Function to handle messages
async def handle_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id if update.message is not None else update.callback_query.message.message_id

    if user_id not in userData:
        userData[user_id] = UserData(user_id, chat_id, message_id)

    user_data: Type[UserData] = userData[user_id]

    if update.message:
        message_text = update.message.text

        if user_data.IsEditing:
            await context.bot.send_message(chat_id=user_id, text="You are currently editing, please finish the previous action.")
            return
            
        if update.message.chat.type == 'private':
            if user_id not in userData:
                await context.bot.send_message(chat_id=chat_id, text="Вибачаюсь, немає подій, які ви зараз налаштовуєте.")
                return

            if user_data.CurrentMod == CurrentMode.NoneMode:
                await context.bot.send_message(chat_id=chat_id, text="Наразі не налаштовується подій")

            elif user_data.CurrentMod == CurrentMode.Header:
                user_data.Header = message_text
                await context.bot.send_message(chat_id=chat_id, text="Заголовок збережено")
                user_data.CurrentMod = CurrentMode.NoneMode

            elif user_data.CurrentMod == CurrentMode.Description:
                user_data.Description = message_text
                await context.bot.send_message(chat_id=chat_id, text="Опис збережено")
                user_data.CurrentMod = CurrentMode.NoneMode

            elif user_data.CurrentMod == CurrentMode.Card:
                user_data.CardData = CardData(card_number=message_text)
                await context.bot.send_message(chat_id=chat_id, text="Будь ласка, введіть сумму:")
                user_data.CurrentMod = CurrentMode.Amount

            elif user_data.CurrentMod == CurrentMode.Amount:
                user_data.CardData.MoneyAmount = message_text
                await context.bot.send_message(chat_id=chat_id, text="Сумма збережена")
                user_data.CurrentMod = CurrentMode.NoneMode

# Function to handle callbacks
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    user_response = update.callback_query.data
    
    if update.callback_query.message.chat.type == Filters.private.name:
        user_data: Type[UserData] = userData[user_id]

        if user_data is None:
            return
        
        if user_response == "Header":
            await context.bot.send_message(chat_id=user_id, text="Будь ласка, введіть текст Заголовку:")
            user_data.CurrentMod = CurrentMode.Header
        elif user_response == "Description":
            await context.bot.send_message(chat_id=user_id, text="Будь ласка, введіть текст Опису:")
            user_data.CurrentMod = CurrentMode.Description
        elif user_response == "Card data":
            await context.bot.send_message(chat_id=user_id, text="Будь ласка, введіть номер карти:")
            user_data.CurrentMod = CurrentMode.Card
        elif user_response == "Yes" or user_response == "End Edit":
            
            
            
            if(user_response == "Yes"):
                header_text = user_data.Header if user_data.Header is not None else ""
                description_text = user_data.Description if user_data.Description is not None else ""
                card_data = user_data.CardData if user_data.CardData is not None else None
                message_text = await formating_method(header_text, description_text)
                sent_message = await context.bot.send_message(user_data.ChatId, text=message_text, reply_markup=plus_minus_markup, parse_mode='HTML')
                last_event_data = LastEventData(user_data.ChatId, sent_message.message_id, header_text, description_text, card_data)
            
            elif(user_response == "End Edit"):
                last_event = LastEvent[user_data.ChatId]
                header_text = user_data.Header if user_data.Header is not None else last_event.Header
                description_text = user_data.Description if user_data.Description is not None else last_event.Description
                card_data = user_data.CardData if user_data.CardData is not None else None
                message_text = await format_for_editing(user_data, header_text, description_text, card_data, response_text = None)
                edited_message = await context.bot.edit_message_text(message_text, last_event.ChatId, last_event.MessageId, reply_markup=plus_minus_markup, parse_mode='HTML')
                last_event_data = LastEventData(user_data.ChatId, edited_message.message_id, header_text, description_text, card_data)
            
            LastEvent[user_data.ChatId] = last_event_data

            user_data.CurrentMod = CurrentMode.NoneMode
            user_data.IsEditing = False
            
            await try_delete_message(update._bot, update.effective_chat.id, update.effective_message.id)
        elif user_response == "No":
            await context.bot.send_message(chat_id=chat_id, text="Ви відмінили створення події")
            userData.pop(user_id)
            return
        
    elif update.callback_query.message.chat.type == Filters.group.name or update.callback_query.message.chat.type == Filters.supergroup.name:
        query = update.callback_query
        user_response = query.data
        
        some_user_data = UserData(
        user_id = query.from_user.id,
        chat_id = query.message.chat.id,
        message_id= query.message.message_id,
        user_first_name= query.from_user.first_name,
        user_second_name= query.from_user.last_name)
        
        response_text = ''
        if user_response == '+':
            response_text = 'yes'
        elif user_response == '-':
            response_text = 'no'
        
        last_event_data: Type[LastEventData] = LastEvent[query.message.chat.id]
        try:
            await context.bot.edit_message_text(
                chat_id=last_event_data.ChatId,
                message_id=last_event_data.MessageId,
                text=await format_for_editing(some_user_data, last_event_data.Header, last_event_data.Description, last_event_data.CardData, response_text),
                parse_mode='HTML',
                reply_markup=plus_minus_markup,)
        except:
            print("Cant change message")

# Function to handle first formating
async def formating_method(header_text, description_text):
    
    separator_line = "──────────────────────────"

    if description_text is not None:
        return f"<b>{header_text}</b>\n{separator_line}\n{description_text}\n{separator_line}\nВсього: <strong> X </strong> людей\nПодію створено - X"
    else:
        return f"<b>{header_text}</b>\n{separator_line}\nВсього: <strong> X </strong> людей \nПодію створено - X"

# Function to handle formating
async def format_for_editing(user_data: UserData, header_text: str, description_text: str, card_data: CardData, response_text: str) -> str:
    
    user_mention = f"<a href=\"tg://user?id={user_data.UserId}\">{user_data.UserFirstName} {user_data.UserSecondName if user_data.UserSecondName else ''}</a>"

    current_time = datetime.now()
    formatted_date = current_time.strftime("%d %B %H:%M")
    formatted_user_response = f"{user_mention} <i>{formatted_date}</i>"

    tuple_key = (user_data.ChatId, user_data.MessageId)

    if response_text is not None:
        if tuple_key not in RespondsOnEvent:
            RespondsOnEvent[tuple_key] = RespondData([], user_data.UserId, user_data.ChatId, user_data.MessageId, datetime.now())

        respond = RespondsOnEvent[tuple_key]

        if respond.Responds and any(response.startswith(user_mention) for response in respond.Responds) and response_text.lower() == "no":
            respond.Responds = [response for response in respond.Responds if not response.startswith(user_mention) and not response.startswith(f"<s>{user_mention}")]
            formatted_user_response = f"<s>{user_mention} <i>{formatted_date}</i></s>"
            respond.Responds.append(formatted_user_response)
        elif response_text and response_text.lower() == "yes":
            respond.Responds = [response for response in respond.Responds if not response.startswith(user_mention) and not response.startswith(f"<s>{user_mention}")]
            respond.Responds.append(formatted_user_response)
            print("respond text" + formatted_user_response)

    final_text_list_responses = ""
    if tuple_key in RespondsOnEvent and RespondsOnEvent[tuple_key].Responds:
        counter = 1
        for item in RespondsOnEvent[tuple_key].Responds:
            final_text_list_responses += f"{counter}. {item}\n"
            counter += 1

    separator_line = "──────────────────────────"
    starting_time_formatted = RespondsOnEvent[tuple_key].StartingTime.strftime("%d %B %H:%M")

    if description_text and card_data and card_data.CardNumber and card_data.MoneyAmount:
        return f"<b>{header_text}</b>\n{separator_line}\n{description_text}\n{separator_line}\n{final_text_list_responses}{separator_line}\nВсього: <strong>{len(RespondsOnEvent[tuple_key].Responds)}</strong> людей\nПодію створено - {starting_time_formatted}\n[Номер карти: <code>{card_data.CardNumber}</code> Сумма: <code>{card_data.MoneyAmount}</code>₴]"
    elif description_text:
        return f"<b>{header_text}</b>\n{separator_line}\n{description_text}\n{separator_line}\n{final_text_list_responses}{separator_line}\nВсього: <strong>{len(RespondsOnEvent[tuple_key].Responds)}</strong> людей\nПодію створено - {starting_time_formatted}"
    elif card_data and card_data.CardNumber and card_data.MoneyAmount:
        return f"<b>{header_text}</b>\n{separator_line}\n{final_text_list_responses}{separator_line}\nВсього: <strong>{len(RespondsOnEvent[tuple_key].Responds)}</strong> людей\nПодію створено - {starting_time_formatted}\n[Номер карти: <code>{card_data.CardNumber}</code> Сумма: <code>{card_data.MoneyAmount}</code>₴]"
    else:
        return f"<b>{header_text}</b>\n{separator_line}\n{final_text_list_responses}{separator_line}\nВсього: <strong>{len(RespondsOnEvent[tuple_key].Responds)}</strong> людей\nПодію створено - {starting_time_formatted}"

# Function to handle deliting messages
async def try_delete_message(bot : telegram.Bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as ex:
        logging.error(f"Error deleting message: {ex}")


if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # Initialize the Telegram Bot with your bot token
    application = ApplicationBuilder().token('6439816408:AAEO2FCwGz7lqONQAw5u4gcnBbc_Euv38YE').build()

    # Add handlers for commands and messages
    application.add_handler(CommandHandler("create", create))
    application.add_handler(CommandHandler("edit", edit))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(None, handle_update))

    # Start the Bot
    application.run_polling()
    logging.info("Bot started!")
