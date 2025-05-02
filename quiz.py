import os
import json
from pymongo import MongoClient

# MongoDB connection
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_collection = db["quizzes"]

def upload_quizzes(directory):
    """
    Upload all quizzes to MongoDB with categories.
    :param directory: Path to the quizzes folder.
    """
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            category = filename.split('.')[0]  # Extract category from filename
            file_path = os.path.join(directory, filename)
            
            with open(file_path, 'r', encoding='utf-8') as file:
                quizzes = json.load(file)
                if isinstance(quizzes, list):  # Ensure quizzes is a list
                    for quiz in quizzes:
                        if "question" in quiz:  # Check if 'question' key exists
                            quiz['category'] = category  # Add category to each quiz
                            quizzes_collection.update_one(
                                {"question": quiz["question"], "category": category},
                                {"$set": quiz},
                                upsert=True
                            )
                        else:
                            print(f"Skipped quiz in file '{filename}' because it lacks a 'question' key: {quiz}")
                    print(f"Uploaded {len(quizzes)} quizzes for category '{category}'")
                else:
                    print(f"Invalid format in file: {filename}")

if __name__ == "__main__":
    quizzes_directory = "./quizzes"  # Replace with your quizzes folder path
    upload_quizzes(quizzes_directory)
    print("All quizzes have been uploaded to MongoDB.")
