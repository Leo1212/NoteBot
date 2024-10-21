import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

class MongoDBHandler:
    def __init__(self):
        # Load MongoDB connection settings from environment variables
        self.mongo_uri = os.getenv('MONGO_URI')
        self.database_name = os.getenv('MONGO_DB_NAME')
        
        # Connect to MongoDB
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.database_name]
        print(f"Connected to MongoDB database: {self.database_name}")

    def create_entry(self, collection_name, data):
        """Inserts a new entry into the specified collection."""
        collection = self.db[collection_name]
        result = collection.insert_one(data)
        print(f"Entry created with ID: {result.inserted_id}")
        return result.inserted_id

    def read_entry(self, collection_name, query):
        """Finds and returns an entry based on the provided query."""
        collection = self.db[collection_name]
        result = collection.find_one(query)
        if result:
            print(f"Entry found: {result}")
        else:
            print("No matching entry found.")
        return result

    def update_entry(self, collection_name, query, update_data):
        """Updates an existing entry based on the provided query."""
        collection = self.db[collection_name]
        result = collection.update_one(query, {'$set': update_data})
        if result.matched_count:
            print(f"Successfully updated {result.modified_count} entry/entries.")
        else:
            print("No matching entry found to update.")
        return result.modified_count

    def delete_entry(self, collection_name, query):
        """Deletes an entry based on the provided query."""
        collection = self.db[collection_name]
        result = collection.delete_one(query)
        if result.deleted_count:
            print(f"Successfully deleted {result.deleted_count} entry/entries.")
        else:
            print("No matching entry found to delete.")
        return result.deleted_count

    def read_all_entries(self, collection_name):
        """Reads all entries from the specified collection."""
        collection = self.db[collection_name]
        results = collection.find()
        entries = list(results)
        print(f"Found {len(entries)} entries.")
        return entries

    def close_connection(self):
        """Closes the MongoDB connection."""
        self.client.close()
        print("MongoDB connection closed.")