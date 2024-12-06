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