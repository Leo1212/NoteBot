
from pymongo import MongoClient

class MongoDBHandler:
    def __init__(self, mongo_uri, database_name):
        # Load MongoDB connection settings from environment variables
        self.mongo_uri = mongo_uri
        self.database_name = database_name
        
        # Connect to MongoDB
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.database_name]
        # client = MongoClient(DB_MACHINE, DB_PORT)
        
        self.ping = self.client.admin.command("ping")
        if self.ping.get("ok") == 1.0:
            print(f"Connected to MongoDB database: {self.database_name}")
        else:
            raise Exception("Authentication failed")
        
    def sanitize_data(self, data):
        """Recursively removes or renames keys starting with '$' unless they are valid MongoDB operators."""
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if key.startswith('$') and key in ['$set', '$push', '$inc', '$pull']:
                    # Allow MongoDB operators
                    sanitized[key] = self.sanitize_data(value)
                elif key.startswith('$'):
                    # Rename invalid keys
                    sanitized[f"_{key[1:]}"] = self.sanitize_data(value)
                else:
                    sanitized[key] = self.sanitize_data(value)
            return sanitized
        elif isinstance(data, list):
            return [self.sanitize_data(item) for item in data]
        else:
            return data



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
        # Comment out sanitization to verify raw data:
        # update_data = self.sanitize_data(update_data)  
        
        print(f"Update Query: {query}")
        print(f"Update Data: {update_data}")
        
        collection = self.db[collection_name]
        result = collection.update_one(query, update_data)
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