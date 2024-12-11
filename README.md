# NoteBot
An AI powered note taker for discord calls

## Getting started
1. run `python3 -m venv bot-env` or `conda create -n notebot python=3.11.5`
2. run `source bot-env/bin/activate` (or if you are on windows `bot-env\Scripts\activate.bat`) or `conda activate notebot`
3. run `pip install -r requirements.txt`
4. run `sudo apt update; sudo apt install ffmpeg`
5. create the `.env` file (see example.env) and paste your `DISCORD_BOT_TOKEN` token and the mongo DB config.
6. run `python3 ./notebot.py`

## Create mongo DB
1. run `docker pull mongodb/mongodb-community-server:latest`
2. run `docker run --name notebot-mongodb -d -p 27017:27017 -e MONGO_INITDB_ROOT_USERNAME=mongoadmin -e MONGO_INITDB_ROOT_PASSWORD=supersecretdbpassword mongodb/mongodb-community-server:latest`

## Settings
In the `settings.json` file you can configure your bot.
```
{
    "saveAudio": true, // should we save the audio locally? true/false
    "audioPath": "./recordings", // path where the recordings should be saved (only if saveAudio is true)
    "minimumMeetingParticipants": 2, // when do we start detecting a meeting? min amount of people in the call
    "model_id": "openai/whisper-large-v3", // base model to transcribe & translate
    "summarizer_model_id": "gpt-3.5-turbo", // model to summarize the meeting. If gpt, OPENAI_API_KEY key must be set. But you can also use the model: facebook/bart-large-cnn
    "device": "auto" // should the model run on 'cpu', 'cuda' or 'auto' (we detect if a gpu us available)
}
```