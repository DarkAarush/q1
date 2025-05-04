import logging
from telegram import Update
from telegram.ext import CallbackContext
# from bot import stop_quiz_for_chat
from chat_data_handler import load_chat_data
from leaderboard_handler import add_score
from pymongo import MongoClient
import random
import json
import os
from datetime import datetime, timedelta
from telegram.error import BadRequest, TimedOut, NetworkError, RetryAfter 

logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_collection = db["quizzes"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzes_collection = db["used_quizzes"]
message_status_collection = db["message_status"]

# def retry_on_failure(func):
#     """Decorator to retry function on transient errors"""
#     def wrapper(*args, **kwargs):
#         retries = 3
#         while retries > 0:
#             try:
#                 return func(*args, **kwargs)
#             except (TimedOut, NetworkError, RetryAfter) as e:
#                 logger.warning(f"Retryable error occurred: {e}. Retrying...")
#                 retries -= 1
#             except Exception as e:
#                 logger.error(f"Unrecoverable error occurred: {e}")
#                 break
#         logger.error(f"Function {func.__name__} failed after retries.")
#     return wrapper

# def load_quizzes(category):
#     """
#     Fetch quizzes from MongoDB based on category.
#     :param category: Quiz category (e.g., 'science', 'math').
#     :return: List of quizzes.
#     """
#     quizzes = list(quizzes_collection.find({"category": category}))
#     if not quizzes:
#         logger.error(f"No quizzes found for category '{category}'.")
#     return quizzes



def load_quizzes(category):
    file_path = os.path.join('quizzes', f'{category}.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        logger.error(f"Quiz file for category '{category}' not found.")
        return []

def get_daily_quiz_limit(chat_type):
    """
    Set daily quiz limit based on chat type.
    :param chat_type: Type of chat ('private', 'group', or 'supergroup').
    :return: Daily quiz limit.
    """
    if chat_type == 'private':
        return 5  # Daily limit for private chats
    else:
        return 10  # Daily limit for groups/supergroups



def send_quiz(context: CallbackContext):
    chat_id = context.job.context['chat_id']
    used_questions = context.job.context['used_questions']
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 10:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    else:
        if message_status is None or not message_status.get("limit_reached", False):
            context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "limit_reached": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"limit_reached": True}})
        next_quiz_time = datetime.combine(datetime.now() + timedelta(days=1), datetime.min.time())
        context.job_queue.run_once(send_quiz, next_quiz_time, context=context.job.context)
        return

    if not questions:
        if message_status is None or not message_status.get("no_questions", False):
            context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "no_questions": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"no_questions": True}})
        return

    used_question_ids = used_quizzes_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        if message_status is None or not message_status.get("no_new_questions", False):
            context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "no_new_questions": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"no_new_questions": True}})
        return

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzes_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

    message = context.bot.send_poll(
        chat_id=chat_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

def send_quiz_immediately(context: CallbackContext, chat_id: str):
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 10:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    else:
        context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
        return

    if not questions:
        context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        return

    used_question_ids = chat_data.get("used_questions", [])
    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
        return

    question = random.choice(available_questions)
    used_question_ids.append(question)
    chat_data["used_questions"] = used_question_ids
    save_chat_data(chat_id, chat_data)

    message = context.bot.send_poll(
        chat_id=chat_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

def handle_poll_answer(update: Update, context: CallbackContext):
    poll_answer = update.poll_answer
    user_id = str(poll_answer.user.id)
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None

    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(poll_id)

    if not poll_data:
        return

    correct_option_id = poll_data['correct_option_id']

    # Update the score
    if selected_option == correct_option_id:
        add_score(user_id, 1)
