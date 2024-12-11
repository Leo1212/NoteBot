import discord
import os
import time
import traceback
from dotenv import load_dotenv
from discord.ext import commands, voice_recv
from datetime import datetime
import json
from mongo_handler import MongoDBHandler
from voice_recorder import VoiceRecorder
from setup_model import setup_whisper_model
from meeting_reader import MeetingReader

load_dotenv()

discord.opus._load_default()

bot = commands.Bot(
    command_prefix=commands.when_mentioned, intents=discord.Intents.all()
)


class NoteBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.meeting_id = None
        self.recorders = {}

        self.db_handler = MongoDBHandler(
            os.getenv("MONGO_URI"), os.getenv("MONGO_DB_NAME")
        )

        with open("./settings.json", "r") as file:
            self.settings = json.load(file)

        self.meeting_reader = MeetingReader(self.db_handler, self.settings)

        if (
            self.settings.get("saveAudio")
            and self.settings.get("audioPath") is not None
        ):
            # Ensure the recordings directory exists
            os.makedirs(self.settings.get("audioPath"), exist_ok=True)

        self.whisper_pipeline = setup_whisper_model(self.settings.get("model_id"), self.settings.get("device"))
        self.minimumMeetingParticipants = self.settings.get("minimumMeetingParticipants", 2)

    def create_meeting_entry(self, meeting_id, attendees, start_date, end_date):
        """Creates a meeting entry in the MongoDB database."""
        data = {
            "meeting_id": meeting_id,
            "attendees": attendees,
            "start_date": start_date,
            "end_date": end_date,
            "transcriptions": []
        }
        self.db_handler.create_entry("meetings", data)
        self.meeting_id = meeting_id
        print(f"Meeting entry created: {meeting_id}")

    async def connect_to_existing_calls(self):
        for guild in self.bot.guilds:
            for member in guild.members:
                # Check if the member is in a voice channel and is not a bot
                if member.voice is not None and not member.bot:
                    voice_channel = member.voice.channel
                    if guild.voice_client is None:
                        try:
                            # Connect to the user's voice channel if not already connected
                            vc = await voice_channel.connect(
                                cls=voice_recv.VoiceRecvClient
                            )
                            print(
                                f"Bot connected to {voice_channel.name} (user already in channel)"
                            )

                            # Define the callback to handle received voice packets
                            def callback(user, data: voice_recv.VoiceData):
                                if user is None:
                                    return

                                if user.id not in self.recorders:
                                    self.recorders[user.id] = VoiceRecorder(
                                        user, self.meeting_id, self.whisper_pipeline, self.settings, self.db_handler
                                    )
                                recorder = self.recorders[user.id]
                                recorder.add_packet(data.pcm)

                            vc.listen(voice_recv.BasicSink(callback))
                        except discord.ClientException as e:
                            print(f"Error connecting to the voice channel: {e}")
                        except Exception as e:
                            print(f"An unexpected error occurred: {e}")
                            traceback.print_exc()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        print(f"Voice state update detected for {member.name}")
        if member.bot:
            return

        voice_client = member.guild.voice_client

        # Check if the user joined a voice channel
        if before.channel is None and after.channel is not None:
            voice_channel = after.channel

            # Count non-bot members currently in the channel
            non_bot_members = [m for m in voice_channel.members if not m.bot]

            # Check for active meeting
            active_meeting = self.db_handler.read_entry("meetings", {"end_date": None})
            if active_meeting:
                # Meeting already exists and is ongoing
                self.meeting_id = active_meeting["meeting_id"]
                print(f"Reconnected to active meeting: {self.meeting_id}")

                # Check if new attendee is already in the meeting's attendee list
                attendees = active_meeting.get("attendees", [])
                if not any(a["id"] == member.id for a in attendees):
                    # Add the new user to attendees
                    attendees.append({"id": member.id, "name": member.name})
                    self.db_handler.update_entry(
                        "meetings",
                        {"meeting_id": self.meeting_id},
                        {"$set": {"attendees": attendees}}
                    )
                    print(f"Added new attendee {member.name} to meeting {self.meeting_id}")

                # If the bot is disconnected, connect now
                if voice_client is None:
                    try:
                        vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                        print(f"Bot connected to {voice_channel.name}")

                        def callback(user, data: voice_recv.VoiceData):
                            if user is None:
                                return
                            if user.id not in self.recorders:
                                self.recorders[user.id] = VoiceRecorder(
                                    user, self.meeting_id, self.whisper_pipeline, self.settings, self.db_handler
                                )
                            recorder = self.recorders[user.id]
                            recorder.add_packet(data.pcm)

                        vc.listen(voice_recv.BasicSink(callback))

                    except Exception as e:
                        print(f"Error handling voice channel join: {e}")
                        traceback.print_exc()
            else:
                # No active meeting. Check if we have enough participants to start one.
                if len(non_bot_members) >= self.minimumMeetingParticipants:
                    # Create a new meeting
                    try:
                        meeting_id = f"meeting_{int(time.time())}"
                        # Store both user id and name for each attendee
                        attendees = [{"id": m.id, "name": m.name} for m in non_bot_members]
                        start_date = datetime.now()
                        end_date = None
                        self.create_meeting_entry(meeting_id, attendees, start_date, end_date)
                        print(f"New meeting '{meeting_id}' created.")

                        # Connect to the voice channel
                        vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                        print(f"Bot connected to {voice_channel.name}")

                        def callback(user, data: voice_recv.VoiceData):
                            if user is None:
                                return

                            if user.id not in self.recorders:
                                self.recorders[user.id] = VoiceRecorder(
                                    user, self.meeting_id, self.whisper_pipeline, self.settings, self.db_handler
                                )

                            recorder = self.recorders[user.id]
                            recorder.add_packet(data.pcm)

                        vc.listen(voice_recv.BasicSink(callback))

                    except Exception as e:
                        print(f"Error handling voice channel join: {e}")
                        traceback.print_exc()
                else:
                    # Not enough participants to start a new meeting; do nothing and don't join
                    print(f"Not enough participants to start a meeting. Need at least {self.minimumMeetingParticipants}, have {len(non_bot_members)}. Waiting...")

        # Check if the bot should disconnect after any voice state update
        if voice_client is not None:
            voice_channel = voice_client.channel
            # Get a list of non-bot members currently in the voice channel
            non_bot_members = [m for m in voice_channel.members if not m.bot]

            if len(non_bot_members) == 0:
                # No non-bot members left in the voice channel; disconnect the bot
                try:
                    end_date = datetime.now()
                    active_meetings = self.db_handler.read_all_entries("meetings")
                    # Sort by newest start_date and update the latest meeting
                    latest_meeting = max(
                        active_meetings, key=lambda m: m["start_date"], default=None
                    )

                    await voice_client.disconnect()

                    if latest_meeting:
                        self.db_handler.update_entry(
                            "meetings",
                            {"meeting_id": latest_meeting['meeting_id']},
                            {"$set": {"end_date": end_date}}
                        )

                        # Read meeting transcripts and summarize
                        self.meeting_reader.read_meeting_transcripts(latest_meeting['meeting_id'])

                        # After summarizing, fetch the updated meeting document with title and summary
                        updated_meeting = self.db_handler.read_entry(
                            "meetings", {"meeting_id": latest_meeting['meeting_id']}
                        )

                        # Prepare the DM message
                        meeting_title = updated_meeting.get("meeting_title", "Meeting Summary")
                        meeting_summary = updated_meeting.get("summary", "No summary available.")
                        start_date_str = updated_meeting["start_date"].strftime("%d.%m.%Y %H:%M")
                        if updated_meeting["end_date"]:
                            end_date_str = updated_meeting["end_date"].strftime("%H:%M")
                        else:
                            end_date_str = "Ongoing"
                        attendees = updated_meeting.get("attendees", [])
                        attendee_names = ", ".join([a["name"] for a in attendees])

                        message_content = (
                            f"# {meeting_title}\n"
                            f"**Date:** {start_date_str} - {end_date_str}\n"
                            f"**Attendees:** {attendee_names}\n"
                            f"**Summary:**\n{meeting_summary}"
                        )

                        # Send DMs to attendees
                        for att in attendees:
                            member = voice_channel.guild.get_member(att["id"])
                            if member is not None:
                                try:
                                    await member.send(message_content)
                                    print(f"Sent meeting summary to {member.name}")
                                except Exception as e:
                                    print(f"Failed to send DM to {member.name}: {e}")

                    self.meeting_id = None
                    print(
                        f"Bot disconnected from {voice_channel.name} because no users are left."
                    )
                except Exception as e:
                    print(f"Error disconnecting the bot: {e}")
                    traceback.print_exc()


@bot.event
async def on_ready():
    print("Logged in as {0.id}/{0}".format(bot.user))
    print("------")
    note_bot = NoteBot(bot)
    await bot.add_cog(note_bot)
    await note_bot.connect_to_existing_calls()


bot.run(os.getenv("DISCORD_BOT_TOKEN"))