import discord
import os
import torch
import time
import traceback
from dotenv import load_dotenv
from discord.ext import commands, voice_recv
from datetime import datetime
import json
from transformers import pipeline
from mongo_handler import MongoDBHandler
from voice_recorder import VoiceRecorder

load_dotenv()

discord.opus._load_default()

bot = commands.Bot(
    command_prefix=commands.when_mentioned, intents=discord.Intents.all()
)


class NoteBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recorders = {}

        self.db_handler = MongoDBHandler(
            os.getenv("MONGO_URI"), os.getenv("MONGO_DB_NAME")
        )  # Instantiate the MongoDB handler

        with open("./settings.json", "r") as file:
            self.settings = json.load(file)

        if (
            self.settings.get("saveAudio")
            and self.settings.get("audioPath") is not None
        ):
            # Ensure the recordings directory exists
            os.makedirs(self.settings.get("audioPath"), exist_ok=True)

        device = 0 if torch.cuda.is_available() else -1
        self.whisper_pipeline = pipeline(
            model=self.settings.get("modelName"),
            task="automatic-speech-recognition",
            device=device,
        )

    def create_meeting_entry(self, meeting_id, attendees, start_date, end_date):
        """Creates a meeting entry in the MongoDB database."""
        data = {
            "meeting_id": meeting_id,
            "attendees": attendees,
            "start_date": start_date,
            "end_date": end_date,
        }
        self.db_handler.create_entry("meetings", data)
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
                                    print("User is None, skipping this packet.")
                                    return

                                if user.id not in self.recorders:
                                    self.recorders[user.id] = VoiceRecorder(
                                        user, self.whisper_pipeline, self.settings
                                    )

                                recorder = self.recorders[user.id]
                                recorder.add_packet(data.pcm)

                            vc.listen(voice_recv.BasicSink(callback))
                        except discord.ClientException as e:
                            print(f"Error connecting to the voice channel: {e}")
                        except Exception as e:
                            print(f"An unexpected error occurred: {e}")
                            traceback.print_exc()

    @commands.command()
    async def test(self, ctx):
        def callback(user, data: voice_recv.VoiceData):
            if user.id not in self.recorders:
                self.recorders[user.id] = VoiceRecorder(
                    user, self.whisper_pipeline, self.settings
                )
            recorder = self.recorders[user.id]
            recorder.add_packet(data.pcm)

        # Check if the bot is already connected to a voice channel
        if ctx.voice_client is None:
            vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
            vc.listen(voice_recv.BasicSink(callback))

    @commands.command()
    async def stop(self, ctx):
        await ctx.voice_client.disconnect()

    @commands.command()
    async def die(self, ctx):
        ctx.voice_client.stop()
        await ctx.bot.close()

    @commands.command()
    async def create_meeting(self, ctx, meeting_id: str):
        """Command to manually create a meeting entry."""
        start_date = datetime.now()
        end_date = None  # Update later when the meeting ends
        attendees = [
            member.name for member in ctx.author.voice.channel.members if not member.bot
        ]

        # Create the meeting entry in the database
        self.create_meeting_entry(meeting_id, attendees, start_date, end_date)
        await ctx.send(
            f"Meeting '{meeting_id}' created with attendees: {', '.join(attendees)}"
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        print(f"Voice state update detected for {member.name}")
        if member.bot:
            return

        # Check if the user joined a voice channel
        if before.channel is None and after.channel is not None:
            voice_channel = after.channel

            # Create a unique meeting ID (you can customize this logic)
            meeting_id = f"meeting_{int(time.time())}"

            # Get a list of non-bot members in the channel
            attendees = [m.name for m in voice_channel.members if not m.bot]

            # Create the meeting entry in the database
            start_date = datetime.now()
            end_date = None  # Set end date when the meeting ends
            self.create_meeting_entry(meeting_id, attendees, start_date, end_date)
            print(f"Meeting '{meeting_id}' created for channel '{voice_channel.name}'")

            # Check if the bot is already connected to a voice channel
            if member.guild.voice_client is None:
                try:
                    vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                    print(f"Bot connected to {voice_channel.name}")

                    # Define the callback to handle received voice packets
                    def callback(user, data: voice_recv.VoiceData):
                        if user is None:
                            print("User is None, skipping this packet.")
                            return

                        if user.id not in self.recorders:
                            self.recorders[user.id] = VoiceRecorder(
                                user, self.whisper_pipeline, self.settings
                            )

                        recorder = self.recorders[user.id]
                        recorder.add_packet(data.pcm)

                    vc.listen(voice_recv.BasicSink(callback))

                except discord.ClientException as e:
                    print(f"Error connecting to the voice channel: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
                    traceback.print_exc()

        # Check if the bot should disconnect after any voice state update
        voice_client = member.guild.voice_client
        if voice_client is not None:
            voice_channel = voice_client.channel

            # Get a list of non-bot members currently in the voice channel
            non_bot_members = [m for m in voice_channel.members if not m.bot]

            if len(non_bot_members) == 0:
                # No non-bot members left in the voice channel; disconnect the bot
                try:
                    # Update meeting's end date before disconnecting
                    end_date = datetime.now()
                    meeting_filter = {
                        "attendees": {"$in": [member.name]},
                        "end_date": None,
                    }
                    update_data = {"$set": {"end_date": end_date}}
                    self.db_handler.update_entry(
                        "meetings", meeting_filter, update_data
                    )
                    print(f"Updated meeting end date for '{voice_channel.name}'")

                    await voice_client.disconnect()
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
