import os
import torch
from openai import OpenAI
from transformers import pipeline
from mongo_handler import MongoDBHandler
from dotenv import load_dotenv

load_dotenv()

class MeetingReader:
    def __init__(self, db_handler: MongoDBHandler, settings):
        """
        Initialize MeetingReader with an existing MongoDBHandler instance.
        :param db_handler: Instance of MongoDBHandler to interact with the database.
        """
        self.settings = settings
        self.db_handler = db_handler
        self.summarizer_model_id = self.settings.get("summarizer_model_id")

        device = self.settings.get("device")
        if device == 'auto':
            device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

        # Determine if we're using a ChatGPT-like model
        self.use_chatgpt = self.summarizer_model_id and "gpt" in self.summarizer_model_id.lower()

        if not self.use_chatgpt:
            # Use Hugging Face pipeline
            self.summarizer = pipeline("summarization", model=self.summarizer_model_id, device=device)
            self.client = None
        else:
            # Create the OpenAI client
            api_key = os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=api_key)

    def read_meeting_transcripts(self, meeting_id):
        """
        Reads a meeting from the database and lists its transcripts ordered by timestamp,
        then summarizes the meeting and updates the database with the summary and meeting title.
        """
        # Fetch the meeting document
        meeting = self.db_handler.read_entry("meetings", {"meeting_id": meeting_id})

        if not meeting:
            print(f"No meeting found with ID: {meeting_id}")
            return

        # Extract and sort transcriptions by timestamp
        transcripts = meeting.get("transcriptions", [])
        sorted_transcripts = sorted(transcripts, key=lambda t: t["timestamp"])

        # Display the transcripts
        meeting_transcripts = ""
        for transcript in sorted_transcripts:
            user = transcript["user"]
            transcription = transcript["transcription"]
            meeting_transcripts += f"{user}: \"{transcription}\"\n"

        summary_text = "No summary available for this meeting."

        # Summarize using the appropriate method
        if self.use_chatgpt and self.client is not None:
            # Use OpenAI client
            chat_prompt = (
                "You are given transcripts from a meeting.\n\n"
                "Dont make any information up or assume anything. Only summarize the existing transcripts.\n\n"
                "Generate the response in the language that was spoken in the meeting. So if the transcripts are in german, sumamrize in germand and create a german title. If the languag is englisch, do everything in english and so on. \n\n"
                "1. Invent a brief, fitting meeting title that captures the overall theme or purpose of the meeting.\n"
                "2. Summarize the key points, decisions, and action items from the transcripts.\n\n"
                "3. Create a to-do list of action items that need to be completed after the meeting.\n\n"
                "The first line of your response should be the newly created meeting title.\n\n"
                f"Transcripts:\n{meeting_transcripts}"
            )

            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes meeting transcripts."},
                    {"role": "user", "content": chat_prompt}
                ],
                model=self.summarizer_model_id,
                max_tokens=300,
                temperature=0.7,
            )
            summary_text = response.choices[0].message.content.strip()

            # Extract the meeting title from the first line of the summary (if present)
            lines = summary_text.split('\n')
            meeting_title = lines[0].strip() if lines else "Untitled Meeting"

            meeting_title = meeting_title.replace("Meeting Title: ", "").strip()
            meeting_title = meeting_title.replace("Title:", "").strip()
            # Update the database with the generated summary and meeting title
            self.db_handler.update_entry(
                "meetings",
                {"meeting_id": meeting_id},
                {"$set": {"meeting_title": meeting_title, "summary": summary_text}}
            )

        else:
            # Use the Hugging Face summarizer pipeline
            summary = self.summarizer(meeting_transcripts, max_length=130, min_length=30, do_sample=False)
            if summary and len(summary) > 0:
                summary_text = summary[0]['summary_text']

            # Update the database with the summary (no meeting title from Hugging Face)
            self.db_handler.update_entry(
                "meetings",
                {"meeting_id": meeting_id},
                {"$set": {"summary": summary_text}}
            )

        return summary_text
