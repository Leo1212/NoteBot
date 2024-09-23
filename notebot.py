import discord
import whisper
import os
import io
import time
import traceback
from dotenv import load_dotenv
from discord.ext import commands, voice_recv
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from datetime import datetime
from threading import Timer

load_dotenv()

# Ensure the recordings directory exists
os.makedirs("recordings", exist_ok=True)

discord.opus._load_default()

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=discord.Intents.all())

class VoiceRecorder:
    def __init__(self, user, model):
        self.user = user
        self.buffer = io.BytesIO()
        self.last_spoken_time = time.time()
        self.silence_timer = None
        self.recording = AudioSegment.empty()
        self.model = model

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
        # Save the audio data to an MP3 file
        if self.buffer.getvalue():
            self.buffer.seek(0)
            audio_segment = AudioSegment.from_raw(self.buffer, sample_width=2, frame_rate=48000, channels=2)

            # Detect nonsilent parts to avoid saving empty audio
            nonsilent_ranges = detect_nonsilent(audio_segment, min_silence_len=1000, silence_thresh=-40)

            if nonsilent_ranges:
                # Use the current timestamp for the filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"recordings/{self.user.id}_recording_{timestamp}.mp3"
                audio_segment.export(output_filename, format="mp3")
                print(f"Saved recording as {output_filename}")
                return output_filename

        # Reset buffer and audio data
        self.buffer = io.BytesIO()
        self.recording = AudioSegment.empty()

    def transcribe_recording(self, mp3_file_path):
        # Transcribe the given MP3 file using OpenAI's Whisper
        if os.path.exists(mp3_file_path):
            result = self.model.transcribe(mp3_file_path)
            return result['text']
        else:
            print(f"File {mp3_file_path} not found.")
            return None


class NoteBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recorders = {}
        self.model = whisper.load_model("large-v2")

    @commands.command()
    async def test(self, ctx):
        def callback(user, data: voice_recv.VoiceData):
            if user.id not in self.recorders:
                self.recorders[user.id] = VoiceRecorder(user)
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
                            self.recorders[user.id] = VoiceRecorder(user)

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
                    print(f"Bot disconnected from {voice_channel.name} because no users are left.")
                except Exception as e:
                    print(f"Error disconnecting the bot: {e}")
                    traceback.print_exc()

@bot.event
async def on_ready():
    print('Logged in as {0.id}/{0}'.format(bot.user))
    print('------')
    await bot.add_cog(NoteBot(bot))

bot.run(os.getenv('DISCORD_BOT_TOKEN'))
