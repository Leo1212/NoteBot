import io
import os
from threading import Timer
import time
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import numpy as np
from mongo_handler import MongoDBHandler
from datetime import datetime


class VoiceRecorder:
    def __init__(self, user, meeting_id, model_pipeline, settings):
        self.user = user
        self.meeting_id = meeting_id
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
        # Convert the audio to mono
        audio_segment = audio_segment.set_channels(1)

        # Resample to 16 kHz
        audio_segment = audio_segment.set_frame_rate(16000)

        # Convert the audio segment to a NumPy array
        samples = np.array(audio_segment.get_array_of_samples())

        # Normalize to float32 in the range [-1, 1]
        audio_array = samples.astype(np.float32) / 32768.0

        # Use Hugging Face pipeline to transcribe
        transcription = self.model_pipeline(
            audio_array,
            generate_kwargs={
                "task": "transcribe",
                # "language": "german",
            },
            # chunk_length_s=30,
            # batch_size=8,
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
