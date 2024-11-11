import discord
import os
import torch
import io
import time
import traceback
from dotenv import load_dotenv
from discord.ext import commands, voice_recv
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from datetime import datetime
import json
import numpy as np
from transformers import pipeline
from threading import Timer
from mongo_handler import MongoDBHandler  # Import your MongoDB handler

load_dotenv()

discord.opus._load_default()

bot = commands.Bot(
    command_prefix=commands.when_mentioned, intents=discord.Intents.all()
)


class VoiceRecorder:
    def __init__(self, user, model_pipeline, settings):
        self.user = user
        self.buffer = io.BytesIO()
        self.last_spoken_time = time.time()
        self.silence_timer = None
        self.recording = AudioSegment.empty()
        self.model_pipeline = model_pipeline  # Hugging Face pipeline
        self.settings = settings  # Load settings from NoteBot

    def add_packet(self, data):
        # Add the received packet data to the buffer
        self.buffer.write(data)
        self.last_spoken_time = time.time()

        # Reset the silence detection timer
        if self.silence_timer:
            self.silence_timer.cancel()

        self.silence_timer = Timer(5.0, self.save_recording)
        self.silence_timer.start()

    def save_recording(self):
        # Save the audio data to a buffer and transcribe directly
        if self.buffer.getvalue():
            self.buffer.seek(0)
            audio_segment = AudioSegment.from_raw(
                self.buffer, sample_width=2, frame_rate=48000, channels=2
            )

            # Detect nonsilent parts to avoid transcribing empty audio
            nonsilent_ranges = detect_nonsilent(
                audio_segment, min_silence_len=1000, silence_thresh=-40
            )

            if nonsilent_ranges:
                # Transcribe directly from audio data without saving to a file
                transcription = self.transcribe_recording(audio_segment)
                print(f"{self.user.name}: {transcription}")

                # Check if settings allow saving audio
                if self.settings.get("saveAudio"):
                    self.save_audio_file(audio_segment)

                return transcription

        # Reset buffer and audio data
        self.buffer = io.BytesIO()
        self.recording = AudioSegment.empty()

    def transcribe_recording(self, audio_segment):
        # Convert the audio segment to a NumPy array
        samples = np.array(audio_segment.get_array_of_samples())
        # Convert the samples to float32 for Whisper model
        audio_array = samples.astype(np.float32) / 32768.0  # normalize to [-1, 1]

        # Use Hugging Face pipeline to transcribe
        transcription = self.model_pipeline(
            audio_array,
            generate_kwargs={
                "task": "transcribe",
                # "language": "english",
            },
            return_timestamps=False,
        )
        return transcription["text"]

    def save_audio_file(self, audio_segment):
        # Get the path from settings
        audio_path = self.settings.get("audioPath")

        # Generate a timestamped filename for uniqueness
        filename = f"{self.user.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        filepath = os.path.join(audio_path, filename)

        # Export the audio to an MP3 file
        audio_segment.export(filepath, format="mp3")
        print(f"Saved audio to {filepath}")


class NoteBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recorders = {}
        self.db_handler = MongoDBHandler()  # Instantiate the MongoDB handler

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
            model="openai/whisper-large-v3",
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
                self.recorders[user.id] = VoiceRecorder(user, self.whisper_pipeline)
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

            # Check if the bot is already connected to a voice channel
            if member.guild.voice_client is None:
                try:
                    vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                    print(f"Bot connected to {voice_channel.name}")

                    # Define the callback to handle received voice packets
                    def callback(user, data: voice_recv.VoiceData):
                        # Check if user is None
                        if user is None:
                            print("User is None, skipping this packet.")
                            return

                        if user.id not in self.recorders:
                            self.recorders[user.id] = VoiceRecorder(
                                user, self.whisper_pipeline
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
