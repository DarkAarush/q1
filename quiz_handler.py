import logging
from telegram import Update
from telegram.ext import CallbackContext
# from bot import stop_quiz_for_chat
from chat_data_handler import load_chat_data
from leaderboard_handler import add_score
from pymongo import MongoClient
import random
from datetime import datetime
from telegram.error import BadRequest, TimedOut, NetworkError, RetryAfter 

logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_collection = db["quizzes"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzes_collection = db["used_quizzes"]

def retry_on_failure(func):
    """Decorator to retry function on transient errors"""
    def wrapper(*args, **kwargs):
        retries = 3
        while retries > 0:
            try:
                return func(*args, **kwargs)
            except (TimedOut, NetworkError, RetryAfter) as e:
                logger.warning(f"Retryable error occurred: {e}. Retrying...")
                retries -= 1
            except Exception as e:
                logger.error(f"Unrecoverable error occurred: {e}")
                break
        logger.error(f"Function {func.__name__} failed after retries.")
    return wrapper

def load_quizzes(category):
    """
    Fetch quizzes from MongoDB based on category.
    :param category: Quiz category (e.g., 'science', 'math').
    :return: List of quizzes.
    """
    quizzes = list(quizzes_collection.find({"category": category}))
    if not quizzes:
        logger.error(f"No quizzes found for category '{category}'.")
    return quizzes

def get_daily_quiz_limit():
    """Set daily quiz limit (constant value)."""
    return 10

@retry_on_failure
def send_quiz(context: CallbackContext):
    """
    Send a quiz to the chat based on the category and daily limits.
    """
    chat_id = context.job.context['chat_id']
    send_quiz_logic(context, chat_id)

def should_ignore_chat(chat_id):
    """
    Check if a chat should be ignored.
    """
    ignored_chat = db["ignored_chats"].find_one({"chat_id": chat_id})
    return ignored_chat is not None

def add_to_ignored_chats(chat_id):
    """
    Add a chat to the ignored chats collection.
    """
    db["ignored_chats"].update_one({"chat_id": chat_id}, {"$set": {"ignored": True}}, upsert=True)


@retry_on_failure
def send_quiz_logic(context: CallbackContext, chat_id: int):
    """
    Core logic for sending a quiz to the chat.
    """
    chat_data = load_chat_data(chat_id)
    category = chat_data.get('category')  # Default category if not set
    questions = load_quizzes(category)

    if not questions:
        context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        return

    today = datetime.now().date().isoformat()
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    
    if not quizzes_sent:
        # Initialize tracking for this chat and date if not already present
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 0, "limit_reached": False})
        quizzes_sent = {"count": 0, "limit_reached": False}

    daily_limit = get_daily_quiz_limit()

    # Check if the daily limit has been reached
    if quizzes_sent["count"] >= daily_limit:
        # If the limit is reached, send the message (whether it's the first time or subsequent attempts)
        context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. Tomorrow you will receive new quizzes.")

        # Mark limit as reached if not already marked
        if not quizzes_sent.get("limit_reached"):
            quizzes_sent_collection.update_one(
                {"chat_id": chat_id, "date": today},
                {"$set": {"limit_reached": True}}
            )
        return  # Stop further processing

    # Continue with quiz selection and sending logic
    used_question_ids = used_quizzes_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q["_id"] not in used_question_ids]
    if not available_questions:
        context.bot.send_message(chat_id=chat_id, text="All quizzes have been used. No more quizzes are available.")
        return

    # Select a random question
    question = random.choice(available_questions)

    # Mark the question as used
    used_quizzes_collection.update_one(
        {"chat_id": chat_id},
        {"$push": {"used_questions": question["_id"]}},
        upsert=True
    )

    try:
        # Send the quiz as a poll
        message = context.bot.send_poll(
            chat_id=chat_id,
            question=question["question"],
            options=question["options"],
            type="quiz",
            correct_option_id=question["correct_option_id"],
            is_anonymous=False
        )

        # Increment the count of quizzes sent today
        quizzes_sent_collection.update_one(
            {"chat_id": chat_id, "date": today},
            {"$inc": {"count": 1}}
        )

        # Store the poll ID to handle answers
        context.bot_data[message.poll.id] = {
            "chat_id": chat_id,
            "correct_option_id": question["correct_option_id"]
        }
    except BadRequest as e:
        logger.error(f"Failed to send quiz to chat {chat_id}: {e}")
        context.bot.send_message(chat_id=chat_id, text="Failed to send quiz. Please check the chat ID and permissions.")

@retry_on_failure
def send_quiz_immediately(context: CallbackContext, chat_id: int):
    """
    Send a quiz immediately to the specified chat.
    :param context: CallbackContext
    :param chat_id: Chat ID where the quiz needs to be sent.
    """
    send_quiz_logic(context, chat_id)

@retry_on_failure
def handle_poll_answer(update: Update, context: CallbackContext):
    """
    Handle poll answers submitted by users.
    """
    poll_answer = update.poll_answer
    user_id = str(poll_answer.user.id)
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None

    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(poll_id)

    if not poll_data:
        return

    correct_option_id = poll_data['correct_option_id']

    # Update the score only if the answer is correct
    if selected_option == correct_option_id:
        add_score(user_id, 1)
