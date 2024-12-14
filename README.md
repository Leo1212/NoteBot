# NoteBot
Your AI-Powered Meeting Assistant for Discord  

Welcome to NoteBot, the ultimate AI-driven note-taker for your Discord voice calls.  
Designed to streamline your conversations, NoteBot listens, transcribes, translates,   
and summarizes discussions in real time—perfect for productive meetings, gaming sessions, or casual catch-ups.

With its seamless Discord integration and advanced AI capabilities, NoteBot takes the hassle out of managing notes and lets you focus on what truly matters: the conversation.  
Whether you're working with English, Swiss German, or other supported languages, NoteBot adapts to your needs and even allows you to plug in your own transcription and summarization models.

## Getting started
1. run `python3 -m venv bot-env` or `conda create -n notebot python=3.11.5`
2. run `source bot-env/bin/activate` (or if you are on windows `bot-env\Scripts\activate.bat`) or `conda activate notebot`
3. run `pip install -r requirements.txt`
4. run `sudo apt update; sudo apt install ffmpeg`
5. create the `.env` file (see example.env) and paste your `DISCORD_BOT_TOKEN` token and the mongo DB config.
6. run `python3 ./notebot.py`

## Create mongo DB
Install [Docker]([https://www.docker.com/) on your computer.
1. run `docker pull mongodb/mongodb-community-server:latest`
2. run `docker run --name notebot-mongodb -d -p 27017:27017 -e MONGO_INITDB_ROOT_USERNAME=mongoadmin -e MONGO_INITDB_ROOT_PASSWORD=supersecretdbpassword mongodb/mongodb-community-server:latest`

## Settings
In the `settings.json` file you can configure your bot.
```
{
    "saveAudio": true, // should we save the audio locally? true/false
    "audioPath": "./recordings", // path where the recordings should be saved (only if saveAudio is true)
    "minimumMeetingParticipants": 2, // when do we start detecting a meeting? min amount of people in the call
    "model_id": "openai/whisper-large-v3", // base model to transcribe & translate (examples: notebotIE/whisper-large-v2-swiss-german or openai/whisper-large-v3)
    "summarizer_model_id": "gpt-3.5-turbo", // model to summarize the meeting. If gpt, OPENAI_API_KEY key must be set. But you can also use the model: facebook/bart-large-cnn
    "device": "auto", // should the model run on 'cpu', 'cuda' or 'auto' (we detect if a gpu us available)
    "useOriginalLanguage": true // should the summary be in english or the original spoken language?
}
```