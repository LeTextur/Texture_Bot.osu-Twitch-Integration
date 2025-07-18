from twitchAPI.chat import Chat, EventData, ChatMessage, ChatCommand
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, ChatEvent
import os
import asyncio
from dotenv import load_dotenv
from IRC import IrcBot
import re
from osu import Client
from threading import Thread
import logging
from pathlib import Path
from lang_utils import Translator


class TwitchBot:
    def __init__(self, loop=None):
        self.env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=self.env_path, override=True)
        self.TARGET_CHANNEL = os.getenv("TWITCH_TARGET_CHANNEL")
        self.translator = Translator(os.getenv("LANGUAGE", "en"))

    
        self.osu_api = Client.from_credentials(
            client_id=os.getenv("OSU_CLIENT_ID"),
            client_secret=os.getenv("OSU_CLIENT_SECRET"),
            redirect_url=os.getenv("REDIRECT_URL"),
        )
        self.queue = asyncio.Queue()
        self.irc_bot_thread = None
        self.loop = loop
                
   # If bot connected successfully    
    async def on_ready(self, ready_event: EventData):
        # Join the channel
        await ready_event.chat.join_room(self.TARGET_CHANNEL)
        logging.info(self.translator.t("main-gui-twitch-console-info1", target_channel = self.TARGET_CHANNEL))
        
        
    # Listening to the chat messages
    async def on_massage(self, msg: ChatMessage):
        logging.info(f"{msg.user.display_name} - {msg.text}")
    
        # Detecting osu beatmap link
        beatmap_link_pattern = re.compile(r'(https://)?osu.ppy.sh/(b/\d+|beatmapsets/\d+#osu/\d+)')
        match = beatmap_link_pattern.search(msg.text)
    
        if match:
            logging.info(self.translator.t("main-gui-twitch-console-info2", link = match[0]))
            # Preparing to send the beatmap_id to the OSUAPI
            beatmap_id = str(match.group(2)).split("/")[-1]
            
                
            # Add beatmap_id to the queue
            asyncio.run_coroutine_threadsafe(
            self.add_to_queue(os.getenv("IRC_NICK"), beatmap_id, msg.user.display_name),
            self.loop
            )
            
    # just to see how big is Queue after adding a request
    async def add_to_queue(self, nick, beatmap_id, display_name):
        await self.queue.put((nick, beatmap_id, display_name))
        logging.info(self.translator.t("main-gui-twitch-console-info3") , queue_size = self.queue.qsize())


    async def start_TwitchBot(self):
        auth_dict = {
            "TWITCH_ID": os.getenv("TWITCH_CLIENT_ID"),
            "TWITCH_SECRET": os.getenv("TWITCH_CLIENT_SECRET"),
            "USER_SCOPE": [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.CHANNEL_MANAGE_BROADCAST],
        }

        self.bot = await Twitch(auth_dict["TWITCH_ID"], auth_dict["TWITCH_SECRET"])
        auth = UserAuthenticator(self.bot, auth_dict["USER_SCOPE"])
        token, refresh_token = await auth.authenticate()
        await self.bot.set_user_authentication(token, auth_dict["USER_SCOPE"], refresh_token)

        # Initialize chat class
        self.chat = await Chat(self.bot, no_message_reset_time=2)

        # Listen to events
        self.chat.register_event(ChatEvent.READY, self.on_ready)
        self.chat.register_event(ChatEvent.MESSAGE, self.on_massage)

        # Register commands
        self.chat.register_command("np", self.np_command)
        self.chat.register_command("pp", self.pp_command)

        # Start Twitch bot
        self.chat.start()
        self.chat_state = True
        
        # Start worker
        self.worker_task = asyncio.create_task(self.request_worker())
        
        
        if self.irc_bot_thread is None:
            self.irc_bot = IrcBot()
            self.irc_bot_thread = Thread(target=self.irc_bot.start, name="IRC_BOT_THREAD", daemon=True)
            self.irc_bot_thread.start()
        
        
    async def stop_TwitchBot(self):
        # cancel if worker task is running
        logging.info(self.translator.t("main-gui-twitch-console-info4"))
        if self.worker_task and not self.worker_task.done():
            loop = self.worker_task.get_loop()
            def cancel_task():
                self.worker_task.cancel()
            loop.call_soon_threadsafe(cancel_task)

        self.chat_state = False

        try:
            logging.info(self.translator.t("main-gui-twitch-console-info5"))
            await self.chat.send_message(self.TARGET_CHANNEL, self.translator.t("twitch-send-message1"))
        except Exception as e:
            logging.error(self.translator.t("main-gui-twitch-console-error1", error = e))

        try:
            logging.info(self.translator.t("main-gui-twitch-console-info6"))
            self.chat.stop()
        except Exception as e:
            logging.error(self.translator.t("main-gui-twitch-console-error2", error = e))

        try:
            logging.info(self.translator.t("main-gui-twitch-console-info7"))
            await self.bot.close()
        except Exception as e:
            logging.error(self.translator.t("main-gui-twitch-console-error3", error = e))
        
    # commands
    
    # !np command
    async def np_command(self, msg: ChatCommand):
        load_dotenv(dotenv_path=self.env_path, override=True)
        if os.getenv("NP_ENABLED") == "true":
            try:
                id_map = open(os.getenv("NP_FILE_PATH"), "r")
                
                await msg.chat.send_message(self.TARGET_CHANNEL, id_map.read())
                id_map.close()
                logging.info(self.translator.t("main-gui-twitch-console-info8"))
            except Exception as e:
                logging.error(self.translator.t("main-gui-twitch-console-error4", error = e))
                await msg.chat.send_message(self.TARGET_CHANNEL, self.translator.t("twitch-send-messag2"))
        else: logging.warning(self.translator.t("main-gui-twitch-console-warn1"))
        
        
    # !pp command
    async def pp_command(self , msg: ChatCommand):
        load_dotenv(dotenv_path=self.env_path, override=True)
        if os.getenv("PP_ENABLED") == "true":
            try:
                pp_status = open(os.getenv("PP_FILE_PATH"), "r")
                await msg.chat.send_message(self.TARGET_CHANNEL, pp_status.read())
                pp_status.close()
                logging.info(self.translator.t("main-gui-twitch-console-info9"))
            except Exception as e:
                logging.error(self.translator.t("main-gui-twitch-console-error5", error = e))
                await msg.chat.send_message(self.TARGET_CHANNEL, self.translator.t("twitch-send-message3"))
        else: logging.warning(self.translator.t("main-gui-twitch-console-warn2"))
        
        
    # Function to handle requests
    async def request_worker(self):
        logging.info(self.translator.t("main-gui-twitch-console-info10"))

        try:
            while True:
                target, beatmap_id, name = await self.queue.get()
        
                load_dotenv(dotenv_path=self.env_path, override=True)
                
                
                diff_limit_str = os.getenv("DIFF_LIMIT")
                try:
                    difficulty_limit = diff_limit_str.split(",")
                except Exception:
                    difficulty_limit = [0,15]
                
                
                
                min_diff = float(difficulty_limit[0])
                max_diff = float(difficulty_limit[1])
        
                logging.info(self.translator.t("main-gui-twitch-console-info11", name=name))
                
                # Treat 15 as infinity for max
                is_infinite = max_diff == 15 
                try:
                    # Process the beatmap
                    beatmap_properties_list = self.get_beatmap_properties(beatmap_id)
                    beatmap_sr = beatmap_properties_list[3]

                    # Checking the difficulty limit
                    if beatmap_sr < min_diff or (not is_infinite and beatmap_sr > max_diff):
                        max_display = "∞" if is_infinite else f"{max_diff}★"
                        await self.chat.send_message(self.TARGET_CHANNEL, self.translator.t("twitch-send-message5", name = name, min_diff = min_diff, max_display = max_display, beatmap_sr = beatmap_sr))
                    else:
                        osu_msg = (
                            f"{name}  »  "
                            f"[{beatmap_properties_list[4]} {beatmap_properties_list[0]} - {beatmap_properties_list[1]} "
                            f"[{beatmap_properties_list[2]}]]   ({beatmap_properties_list[5]} BPM, {beatmap_sr}★, "
                            f"{beatmap_properties_list[6]})"
                        )
                        
                        # Send the message
                        self.irc_bot.send_message(target, osu_msg)
                        await self.chat.send_message(self.TARGET_CHANNEL, self.translator.t("twitch-send-message4", name=name))
                except Exception as e:
                    logging.error(self.translator.t("main-gui-twitch-console-error6", error = e))
                finally:
                    
                    # Mark the task as done in the queue
                    self.queue.task_done()
        except asyncio.CancelledError:
            logging.info(self.translator.t("main-gui-twitch-console-info12"))
            return    
            
    # Function to get beatmap properties
    def get_beatmap_properties(self, id):
        
        logging.info(self.translator.t("main-gui-osuapi-console-info1", id = id))
        client = self.osu_api         
        # Getting beatmap properties
        
        beatmap_SR = round(client.get_beatmap_attributes(id).star_rating, 2)
        beatmap_artist = client.get_beatmap(id).beatmapset.artist
        beatmap_title = client.get_beatmap(id).beatmapset.title
        beatmap_diff = client.get_beatmap(id).version
        beatmap_bpm = client.get_beatmap(id).bpm
        beatmap_length = self.convert_seconds_to_readable(client.get_beatmap(id).total_length)
        beatmap_link = f"https://osu.ppy.sh/b/{id}"
        
        logging.info(self.translator.t("main-gui-osuapi-console-info2", id = id))
        return beatmap_artist, beatmap_title, beatmap_diff, beatmap_SR, beatmap_link, beatmap_bpm , beatmap_length
        
    

    """ Made by aticie """
    # Function to convert seconds to readable time
    def convert_seconds_to_readable(self, seconds: str) -> str:
        seconds = int(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours == 0:
            return f'{minutes:g}:{seconds:02g}'
        else:
            return f'{hours:g}:{minutes:02g}:{seconds:02g}'

