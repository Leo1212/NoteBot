import io
import os
from threading import Timer
import time
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import numpy as np
from datetime import datetime


class VoiceRecorder:
    def __init__(self, user, meeting_id, model_pipeline, settings, db_handler):
        self.user = user
        self.meeting_id = meeting_id
        self.buffer = io.BytesIO()
        self.last_spoken_time = time.time()
        self.silence_timer = None
        self.recording = AudioSegment.empty()
        self.model_pipeline = model_pipeline  # Hugging Face pipeline
        self.settings = settings  # Load settings from NoteBot
        self.db_handler = db_handler  # MongoDB handler instance

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
                # Transcribe the audio and save results in the database
                transcription = self.transcribe_recording(audio_segment)
                if transcription:
                    audio_path = None
                    if self.settings.get("saveAudio"):
                        audio_path = self.save_audio_file(audio_segment)

                    # Save transcription to the database
                    self.save_transcription_to_db(transcription, audio_path)

        # Reset buffer and audio data
        self.buffer = io.BytesIO()
        self.recording = AudioSegment.empty()

    def transcribe_recording(self, audio_segment):
        # Convert the audio to mono and resample to 16 kHz
        audio_segment = audio_segment.set_channels(1).set_frame_rate(16000)
        samples = np.array(audio_segment.get_array_of_samples())
        audio_array = samples.astype(np.float32) / 32768.0

        # Use Hugging Face pipeline to transcribe
        transcription = self.model_pipeline(
            audio_array,
            generate_kwargs={"task": "transcribe"},
            return_timestamps=False,
        )
        return transcription["text"]

    def save_audio_file(self, audio_segment):
        audio_path = self.settings.get("audioPath")
        filename = f"{self.user.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        filepath = os.path.join(audio_path, filename)
        audio_segment.export(filepath, format="mp3")
        print(f"Saved audio to {filepath}")
        return filepath

    def save_transcription_to_db(self, transcription, audio_path):
        # Prepare the data to save in the database
        timestamp = datetime.now()
        entry = {
            "user": self.user.name,
            "timestamp": timestamp,
            "transcription": transcription,
        }
        if audio_path:
            entry["audio_path"] = audio_path

        # Append the transcription to the 'transcriptions' array
        self.db_handler.update_entry(
            "meetings",
            {"meeting_id": self.meeting_id},  # Match meeting by ID
            {"$push": {"transcriptions": entry}}  # Use $push to append
        )
        print(f"Saved transcription to DB for meeting {self.meeting_id}")

