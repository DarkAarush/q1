import os
from pymongo import MongoClient

# MongoDB connection
# MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
# MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
chat_data_collection = db["chat_data"]
served_chats_collection = db["served_chats"]
served_users_collection = db["served_users"]



def load_chat_data(chat_id):
    """
    Load chat data from MongoDB and set default values if not present.
    """
    chat_data = chat_data_collection.find_one({"chat_id": chat_id})
    if not chat_data:
        return {"is_anonymous": False}  # Default values

    # Ensure the 'is_anonymous' flag is always present
    if "is_anonymous" not in chat_data:
        chat_data["is_anonymous"] = False

    return chat_data


# Load chat data
def load_chat_data(chat_id=None):
    if chat_id:
        chat_data = chat_data_collection.find_one({"chat_id": chat_id})
        if chat_data:
            return chat_data["data"]
        return {}
    else:
        return {chat["chat_id"]: chat["data"] for chat in chat_data_collection.find()}

# Save chat data
def save_chat_data(chat_id, data):
    chat_data_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"data": data}},
        upsert=True
    )

# Get served chats
def get_served_chats():
    return list(served_chats_collection.find({}, {"_id": 0, "chat_id": 1}))

# Get served users
def get_served_users():
    return list(served_users_collection.find({}, {"_id": 0, "user_id": 1}))

# Add served chat
def add_served_chat(chat_id):
    served_chats_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id}},
        upsert=True
    )

# Add served user
def add_served_user(user_id):
    served_users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id}},
        upsert=True
    )

# Get all active quizzes
def get_active_quizzes():
    return chat_data_collection.find({"data.active": True})
