"""
chiChi - A cozy Discord bot for small friend servers
Fast, cozy, low-pressure, socially connective
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
import os
from typing import Optional, Dict, List, Tuple
import json
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
tree = app_commands.CommandTree(bot)

# Database setup
DB_NAME = 'chichi.db'

def init_db():
    """Initialize the database with all required tables"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Birthdays
    c.execute('''CREATE TABLE IF NOT EXISTS birthdays
                 (user_id INTEGER PRIMARY KEY, birthday TEXT, wishes TEXT)''')
    
    # Vibe points
    c.execute('''CREATE TABLE IF NOT EXISTS vibe_points
                 (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0)''')
    
    # Game states
    c.execute('''CREATE TABLE IF NOT EXISTS game_states
                 (channel_id INTEGER, game_type TEXT, state TEXT, PRIMARY KEY (channel_id, game_type))''')
    
    # Check-in tracking
    c.execute('''CREATE TABLE IF NOT EXISTS check_ins
                 (channel_id INTEGER PRIMARY KEY, last_check_in TEXT, last_activity TEXT)''')
    
    # Blacklist
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (user_id INTEGER PRIMARY KEY)''')
    
    conn.commit()
    conn.close()

# Personality system
class Personality:
    """Handles chiChi's personality and responses"""
    
    @staticmethod
    def format_message(text: str) -> str:
        """Format message in chiChi's style (lowercase, casual)"""
        return text.lower()
    
    @staticmethod
    def react_win() -> str:
        reactions = [
            "NO WAY 😭 ok you ate that",
            "WAIT THAT WAS CRAZY",
            "ok gg that was actually insane",
            "nah you're too good at this 😭",
            "okay okay you got me there"
        ]
        return Personality.format_message(random.choice(reactions))
    
    @staticmethod
    def react_loss() -> str:
        reactions = [
            "dang... that was close tho 😔",
            "okay okay next time for sure",
            "nah that was still fun tho",
            "ok gg that was close",
            "aw man 😔 but you'll get em next time"
        ]
        return Personality.format_message(random.choice(reactions))
    
    @staticmethod
    def react_tie() -> str:
        reactions = [
            "WAIT NO WAY A TIE 😭",
            "ok that's actually wild",
            "nah that's too close to call",
            "okay okay we're both winners here"
        ]
        return Personality.format_message(random.choice(reactions))
    
    @staticmethod
    def react_mistake() -> str:
        reactions = [
            "WAIT I WAS WRONG my bad 😔",
            "ok hold up i messed that up",
            "nah wait that's on me",
            "okay okay i was wrong there 😭"
        ]
        return Personality.format_message(random.choice(reactions))
    
    @staticmethod
    def react_birthday(user_mention: str) -> str:
        return Personality.format_message(f"ITS {user_mention} DAY 🎉 everyone say something nice or i WILL cry")
    
    @staticmethod
    def react_checkin() -> str:
        prompts = [
            "hey... how's everyone doin lately? 😊\nrandom thought: what song are you stuck on rn?",
            "okay okay who's still alive here? 👀\nwhat's everyone up to?",
            "hey friends 😊 been quiet lately... what's good?",
            "ok random check in time 👀 how's everyone's week been?"
        ]
        return Personality.format_message(random.choice(prompts))

# Database helper
class Database:
    @staticmethod
    def get_connection():
        return sqlite3.connect(DB_NAME)
    
    @staticmethod
    def get_vibe_points(user_id: int) -> int:
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('SELECT points FROM vibe_points WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    
    @staticmethod
    def add_vibe_points(user_id: int, points: int):
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO vibe_points (user_id, points) VALUES (?, 0)', (user_id,))
        c.execute('UPDATE vibe_points SET points = points + ? WHERE user_id = ?', (points, user_id))
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_birthday(user_id: int, birthday: str):
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO birthdays (user_id, birthday, wishes) VALUES (?, ?, ?)',
                  (user_id, birthday, json.dumps([])))
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_birthday(user_id: int) -> Optional[str]:
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('SELECT birthday FROM birthdays WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    
    @staticmethod
    def add_birthday_wish(user_id: int, wisher_id: int, wish: str):
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('SELECT wishes FROM birthdays WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        wishes = json.loads(result[0]) if result and result[0] else []
        wishes.append({'wisher_id': wisher_id, 'wish': wish, 'timestamp': datetime.now().isoformat()})
        c.execute('UPDATE birthdays SET wishes = ? WHERE user_id = ?', (json.dumps(wishes), user_id))
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_birthday_wishes(user_id: int) -> List[Dict]:
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('SELECT wishes FROM birthdays WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result and result[0]:
            return json.loads(result[0])
        return []
    
    @staticmethod
    def is_blacklisted(user_id: int) -> bool:
        conn = Database.get_connection()
        c = conn.cursor()
        c.execute('SELECT 1 FROM blacklist WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None

# Game implementations
class Game21:
    """21 vibes - blackjack-lite game"""
    
    def __init__(self):
        self.deck = list(range(1, 11)) * 4  # Simple deck 1-10
        random.shuffle(self.deck)
        self.player_hand = []
        self.dealer_hand = []
        self.dealer_bold = True
    
    def draw_card(self):
        if not self.deck:
            self.deck = list(range(1, 11)) * 4
            random.shuffle(self.deck)
        return self.deck.pop()
    
    def start_game(self):
        self.player_hand = [self.draw_card(), self.draw_card()]
        self.dealer_hand = [self.draw_card(), self.draw_card()]
        return self.get_state()
    
    def get_state(self):
        player_total = sum(self.player_hand)
        dealer_visible = self.dealer_hand[0]
        return {
            'player_hand': self.player_hand,
            'player_total': player_total,
            'dealer_visible': dealer_visible,
            'game_over': False
        }
    
    def hit(self):
        self.player_hand.append(self.draw_card())
        total = sum(self.player_hand)
        if total > 21:
            return self.end_game()
        return self.get_state()
    
    def stand(self):
        return self.end_game()
    
    def end_game(self):
        player_total = sum(self.player_hand)
        dealer_total = sum(self.dealer_hand)
        
        # Dealer plays (bold strategy)
        while dealer_total < 17 and self.dealer_bold:
            self.dealer_hand.append(self.draw_card())
            dealer_total = sum(self.dealer_hand)
        
        result = 'win' if (player_total <= 21 and (dealer_total > 21 or player_total > dealer_total)) else \
                 'loss' if (dealer_total <= 21 and (player_total > 21 or dealer_total > player_total)) else 'tie'
        
        return {
            'player_hand': self.player_hand,
            'player_total': player_total,
            'dealer_hand': self.dealer_hand,
            'dealer_total': dealer_total,
            'result': result,
            'game_over': True
        }

class Magic8Ball:
    """Magic 8-ball responses"""
    
    responses = [
        "yeah lowkey yes",
        "nah i wouldn't risk it 😬",
        "ask again after snacks",
        "okay okay probably",
        "nah that's a no from me",
        "yeah go for it",
        "ok wait let me think... maybe?",
        "nah that's sus",
        "yeah that sounds good",
        "okay okay i'm not sure but probably yes",
        "nah i'm too sleepy to answer properly 😴",
        "yeah lowkey that's a good idea",
        "okay okay i think so",
        "nah that's not it",
        "yeah probably",
        "ok wait that's actually a maybe",
        "nah i don't think so",
        "yeah go ahead",
        "okay okay i'm feeling yes on this one",
        "nah that's a hard pass"
    ]
    
    @staticmethod
    def respond() -> str:
        return Personality.format_message(random.choice(Magic8Ball.responses))

class TriviaGame:
    """Sudden-death trivia"""
    
    questions = [
        {"q": "what's the capital of france?", "a": "paris", "options": ["paris", "london", "berlin", "madrid"]},
        {"q": "how many sides does a triangle have?", "a": "3", "options": ["3", "4", "5", "6"]},
        {"q": "what planet do we live on?", "a": "earth", "options": ["earth", "mars", "venus", "jupiter"]},
        {"q": "what's 2 + 2?", "a": "4", "options": ["3", "4", "5", "6"]},
        {"q": "what color do you get when you mix red and blue?", "a": "purple", "options": ["purple", "green", "orange", "yellow"]},
        {"q": "how many hours are in a day?", "a": "24", "options": ["12", "24", "36", "48"]},
        {"q": "what's the largest ocean?", "a": "pacific", "options": ["atlantic", "pacific", "indian", "arctic"]},
        {"q": "what animal says 'meow'?", "a": "cat", "options": ["dog", "cat", "bird", "cow"]},
    ]
    
    def __init__(self):
        self.question = random.choice(self.questions)
        self.answered = False
        self.winner = None
    
    def get_question(self):
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(self.question['options'])])
        return f"{self.question['q']}\n{options_text}"
    
    def check_answer(self, answer: str, user_id: int) -> Tuple[bool, str]:
        if self.answered:
            return False, Personality.format_message("okay okay someone already got it 😔")
        
        # Check if answer matches (number or text)
        answer_lower = answer.lower().strip()
        correct_answer = self.question['a'].lower()
        
        # Check by number
        try:
            answer_num = int(answer_lower)
            if answer_num >= 1 and answer_num <= len(self.question['options']):
                selected = self.question['options'][answer_num - 1].lower()
                if selected == correct_answer:
                    self.answered = True
                    self.winner = user_id
                    return True, Personality.react_win()
        except:
            pass
        
        # Check by text
        if answer_lower == correct_answer:
            self.answered = True
            self.winner = user_id
            return True, Personality.react_win()
        
        return False, Personality.format_message("nah that's not it 😔")

# Active game states
active_games: Dict[int, any] = {}

# Bot events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    init_db()
    try:
        synced = await tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')
    check_in_task.start()
    birthday_check_task.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Check blacklist
    if Database.is_blacklisted(message.author.id):
        return
    
    # Check if message is an answer to active trivia (can answer via regular message or slash command)
    if message.channel.id in active_games:
        game = active_games[message.channel.id]
        if isinstance(game, TriviaGame) and not game.answered:
            # Try to parse as answer (ignore slash commands and bot commands)
            content = message.content.strip().lower()
            if content and not content.startswith('/') and not content.startswith('!'):
                correct, response = game.check_answer(content, message.author.id)
                if correct:
                    Database.add_vibe_points(message.author.id, 15)
                    await message.channel.send(f"{message.author.mention} {response}")
                    if message.channel.id in active_games:
                        del active_games[message.channel.id]
                elif "not it" in response.lower():
                    await message.channel.send(response)
    
    # React to messages with emojis occasionally
    if random.random() < 0.1:  # 10% chance
        emojis = ['😊', '👀', '😭', '😔', '🎉', '👋']
        try:
            await message.add_reaction(random.choice(emojis))
        except:
            pass  # Ignore reaction errors
    
    # Slash commands are handled automatically, but keep this for any legacy prefix commands
    await bot.process_commands(message)

# Slash Commands
@tree.command(name="help", description="show all chiChi commands")
async def help_command(interaction: discord.Interaction):
    help_text = """
**chiChi commands:**

`/birthday-set` - set your birthday
`/birthday-wish` - leave a birthday wish
`/game21` - play 21 vibes (blackjack-lite)
`/8ball` - ask the magic 8-ball
`/trivia` - start sudden-death trivia
`/rps` - rock paper scissors
`/tictactoe` - challenge someone to tic-tac-toe
`/vibes` - check your vibe points
`/checkin` - manually trigger a check-in

that's it! keep it simple 😊
"""
    await interaction.response.send_message(Personality.format_message(help_text))

@tree.command(name="birthday-set", description="set your birthday")
@app_commands.describe(date="your birthday in format month/day (e.g., 12/25)")
async def birthday_set(interaction: discord.Interaction, date: str):
    try:
        month, day = map(int, date.split('/'))
        if month < 1 or month > 12 or day < 1 or day > 31:
            raise ValueError
        Database.set_birthday(interaction.user.id, date)
        await interaction.response.send_message(Personality.format_message(f"okay okay your birthday is set to {date} 🎉"))
    except:
        await interaction.response.send_message(Personality.format_message("okay okay that's not a valid date 😔 try like 12/25"))

@tree.command(name="birthday-wish", description="leave a birthday wish for someone")
@app_commands.describe(user="the user to wish a happy birthday", message="your birthday wish message")
async def birthday_wish(interaction: discord.Interaction, user: discord.Member, message: str):
    Database.add_birthday_wish(user.id, interaction.user.id, message)
    await interaction.response.send_message(Personality.format_message(f"okay okay wish saved! 🎉"))

@tree.command(name="game21", description="play 21 vibes (blackjack-lite)")
async def game_21(interaction: discord.Interaction):
    if interaction.channel.id in active_games:
        await interaction.response.send_message(Personality.format_message("okay okay there's already a game going 😔"))
        return
    
    game = Game21()
    active_games[interaction.channel.id] = game
    state = game.start_game()
    
    msg = f"okay okay let's play 21 vibes! 🎮\n"
    msg += f"your hand: {state['player_hand']} (total: {state['player_total']})\n"
    msg += f"dealer shows: {state['dealer_visible']}\n"
    msg += f"use `/hit` to draw or `/stand` to stop"
    
    await interaction.response.send_message(Personality.format_message(msg))

@tree.command(name="hit", description="draw a card in 21 vibes")
async def hit_command(interaction: discord.Interaction):
    if interaction.channel.id not in active_games:
        await interaction.response.send_message(Personality.format_message("okay okay no game active 😔 start with /game21"))
        return
    
    game = active_games[interaction.channel.id]
    if not isinstance(game, Game21):
        await interaction.response.send_message(Personality.format_message("okay okay that's not a 21 game 😔"))
        return
    
    state = game.hit()
    
    if state['game_over']:
        del active_games[interaction.channel.id]
        msg = f"game over!\n"
        msg += f"your hand: {state['player_hand']} (total: {state['player_total']})\n"
        msg += f"dealer hand: {state['dealer_hand']} (total: {state['dealer_total']})\n"
        
        if state['result'] == 'win':
            msg += Personality.react_win()
            Database.add_vibe_points(interaction.user.id, 10)
        elif state['result'] == 'loss':
            msg += Personality.react_loss()
            Database.add_vibe_points(interaction.user.id, 5)
        else:
            msg += Personality.react_tie()
            Database.add_vibe_points(interaction.user.id, 7)
        
        await interaction.response.send_message(Personality.format_message(msg))
    else:
        msg = f"you drew a card!\n"
        msg += f"your hand: {state['player_hand']} (total: {state['player_total']})\n"
        msg += f"use `/hit` or `/stand`"
        await interaction.response.send_message(Personality.format_message(msg))

@tree.command(name="stand", description="stop drawing cards in 21 vibes")
async def stand_command(interaction: discord.Interaction):
    if interaction.channel.id not in active_games:
        await interaction.response.send_message(Personality.format_message("okay okay no game active 😔"))
        return
    
    game = active_games[interaction.channel.id]
    if not isinstance(game, Game21):
        await interaction.response.send_message(Personality.format_message("okay okay that's not a 21 game 😔"))
        return
    
    state = game.stand()
    del active_games[interaction.channel.id]
    
    msg = f"game over!\n"
    msg += f"your hand: {state['player_hand']} (total: {state['player_total']})\n"
    msg += f"dealer hand: {state['dealer_hand']} (total: {state['dealer_total']})\n"
    
    if state['result'] == 'win':
        msg += Personality.react_win()
        Database.add_vibe_points(interaction.user.id, 10)
    elif state['result'] == 'loss':
        msg += Personality.react_loss()
        Database.add_vibe_points(interaction.user.id, 5)
    else:
        msg += Personality.react_tie()
        Database.add_vibe_points(interaction.user.id, 7)
    
    await interaction.response.send_message(Personality.format_message(msg))

@tree.command(name="8ball", description="ask the magic 8-ball a question")
@app_commands.describe(question="your question for the magic 8-ball")
async def magic_8ball(interaction: discord.Interaction, question: str):
    response = Magic8Ball.respond()
    await interaction.response.send_message(response)
    Database.add_vibe_points(interaction.user.id, 2)

@tree.command(name="trivia", description="start sudden-death trivia")
async def trivia_command(interaction: discord.Interaction):
    if interaction.channel.id in active_games:
        await interaction.response.send_message(Personality.format_message("okay okay there's already a game going 😔"))
        return
    
    game = TriviaGame()
    active_games[interaction.channel.id] = game
    
    msg = f"okay okay sudden-death trivia! 🎮\n"
    msg += f"first to answer correctly wins!\n\n"
    msg += game.get_question()
    msg += f"\n\nanswer with the number or the answer itself!"
    
    await interaction.response.send_message(Personality.format_message(msg))
    
    # Auto-cleanup after 90 seconds
    await asyncio.sleep(90)
    if interaction.channel.id in active_games and isinstance(active_games[interaction.channel.id], TriviaGame):
        if not active_games[interaction.channel.id].answered:
            await interaction.channel.send(Personality.format_message("okay okay time's up! no one got it 😔"))
        del active_games[interaction.channel.id]

@tree.command(name="answer", description="answer the trivia question")
@app_commands.describe(answer="your answer to the trivia question")
async def answer_trivia(interaction: discord.Interaction, answer: str):
    if interaction.channel.id not in active_games:
        await interaction.response.send_message(Personality.format_message("okay okay no trivia active 😔"))
        return
    
    game = active_games[interaction.channel.id]
    if not isinstance(game, TriviaGame):
        await interaction.response.send_message(Personality.format_message("okay okay that's not trivia 😔"))
        return
    
    correct, response = game.check_answer(answer, interaction.user.id)
    
    if correct:
        Database.add_vibe_points(interaction.user.id, 15)
        await interaction.response.send_message(f"{interaction.user.mention} {response}")
        if interaction.channel.id in active_games:
            del active_games[interaction.channel.id]
    else:
        await interaction.response.send_message(response)

@tree.command(name="rps", description="play rock paper scissors")
@app_commands.describe(choice="your choice")
@app_commands.choices(choice=[
    app_commands.Choice(name="rock", value="rock"),
    app_commands.Choice(name="paper", value="paper"),
    app_commands.Choice(name="scissors", value="scissors")
])
async def rock_paper_scissors(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(['rock', 'paper', 'scissors'])
    
    # Determine winner
    if choice == bot_choice:
        result = "tie"
        reaction = Personality.react_tie()
    elif (choice == 'rock' and bot_choice == 'scissors') or \
         (choice == 'paper' and bot_choice == 'rock') or \
         (choice == 'scissors' and bot_choice == 'paper'):
        result = "win"
        reaction = Personality.react_win()
        Database.add_vibe_points(interaction.user.id, 5)
    else:
        result = "loss"
        reaction = Personality.react_loss()
        Database.add_vibe_points(interaction.user.id, 3)
    
    msg = f"you chose: {choice}\n"
    msg += f"i chose: {bot_choice}\n"
    msg += reaction
    
    await interaction.response.send_message(Personality.format_message(msg))

@tree.command(name="tictactoe", description="challenge someone to tic-tac-toe")
@app_commands.describe(opponent="the person to challenge")
async def tic_tac_toe(interaction: discord.Interaction, opponent: discord.Member):
    if opponent == interaction.user:
        await interaction.response.send_message(Personality.format_message("okay okay you can't play yourself 😔"))
        return
    
    # Simple tic-tac-toe implementation
    await interaction.response.send_message(Personality.format_message(f"okay okay {opponent.mention} you've been challenged to tic-tac-toe! (coming soon - use /rps for now 😊)"))

@tree.command(name="vibes", description="check vibe points")
@app_commands.describe(user="the user to check (leave empty for yourself)")
async def vibe_points(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    points = Database.get_vibe_points(target.id)
    await interaction.response.send_message(Personality.format_message(f"{target.mention} has {points} vibe points 😊"))

@tree.command(name="checkin", description="manually trigger a check-in (admin only)")
async def manual_checkin(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(Personality.format_message("okay okay only admins can do that 😔"))
        return
    
    await interaction.response.send_message(Personality.react_checkin())

# Scheduled tasks
@tasks.loop(hours=24)
async def check_in_task():
    """Check for inactivity and trigger check-ins"""
    await bot.wait_until_ready()
    
    # Check if it's Friday
    if datetime.now().weekday() == 4:  # Friday
        for guild in bot.guilds:
            # Only check-in in one channel per guild (usually the first text channel)
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(Personality.react_checkin())
                    await asyncio.sleep(1)  # Rate limit protection
                    break  # Only one channel per guild

@tasks.loop(hours=24)
async def birthday_check_task():
    """Check for birthdays and announce them"""
    await bot.wait_until_ready()
    
    now = datetime.now()
    # Try both formats (with and without leading zeros)
    today = f"{now.month}/{now.day}"
    today_alt = f"{now.month:02d}/{now.day:02d}"
    
    conn = Database.get_connection()
    c = conn.cursor()
    # Check both formats
    c.execute('SELECT user_id, wishes FROM birthdays WHERE birthday = ? OR birthday = ?', (today, today_alt))
    results = c.fetchall()
    conn.close()
    
    for user_id, wishes_json in results:
        wishes = json.loads(wishes_json) if wishes_json else []
        wishes_text = "\n".join([f"- {w['wish']}" for w in wishes]) if wishes else "no wishes yet 😔"
        
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        msg = Personality.react_birthday(member.mention)
                        if wishes:
                            msg += f"\n\nwishes:\n{wishes_text}"
                        await channel.send(msg)
                        await asyncio.sleep(1)  # Rate limit protection
                        break
                break

# Admin commands
@tree.command(name="blacklist", description="blacklist a user (admin only)")
@app_commands.describe(user="the user to blacklist")
async def blacklist_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(Personality.format_message("okay okay only admins can do that 😔"))
        return
    
    conn = Database.get_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO blacklist (user_id) VALUES (?)', (user.id,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(Personality.format_message(f"okay okay {user.mention} is blacklisted"))

@tree.command(name="unblacklist", description="remove a user from blacklist (admin only)")
@app_commands.describe(user="the user to unblacklist")
async def unblacklist_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(Personality.format_message("okay okay only admins can do that 😔"))
        return
    
    conn = Database.get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM blacklist WHERE user_id = ?', (user.id,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(Personality.format_message(f"okay okay {user.mention} is unblacklisted"))

# Run the bot
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set!")
        print("Create a .env file with: DISCORD_TOKEN=your_token_here")
    else:
        bot.run(token)

