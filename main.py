import discord
from discord.ext import commands, voice_recv
import os
from dotenv import load_dotenv
import asyncio
import wave
import numpy as np
from openai import OpenAI
import mutagen
from mutagen.oggopus import OggOpus

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=";", intents=intents)
load_dotenv()

client = OpenAI()
discord.opus.load_opus('/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.dylib')

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! Latency is `{round(bot.latency * 1000, 2)}ms`.")

@bot.command()
async def join(ctx):
    conversation = [
        {"role": "developer", "content": "You are having a conversation with this user and answer in short, simple sentences (unless required to expand)."}
    ]
    files = []
    fname = os.urandom(4).hex() + ".raw"
    files.append(fname)
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel to use this command!")
        return

    silence_threshold = 100
    silence_duration = 5
    silence_timer = 0

    def callback(_, data: voice_recv.VoiceData):
        nonlocal silence_timer
        audio_level = np.linalg.norm(np.frombuffer(data.pcm, dtype=np.int16))
        if audio_level > silence_threshold:
            silence_timer = 0
            with open(files[-1], "ab") as f:
                f.write(data.pcm)
        else:
            silence_timer += 1

    vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)

    talking = True
    while talking:
        try:
            vc.listen(voice_recv.BasicSink(callback))
            while True:
                await asyncio.sleep(1)

                if silence_timer > silence_duration:
                    vc.stop_listening()
                    break

            fname = os.urandom(4).hex() + ".wav"
            with wave.open(fname, 'wb') as wav_file:
                wav_file.setnchannels(2)
                wav_file.setsampwidth(2)
                wav_file.setframerate(48000)

                try:
                    with open(files[-1], 'rb') as f:
                        wav_file.writeframes(f.read())
                except:
                    pass
            
            transcription = client.audio.transcriptions.create(
                model="whisper-1", 
                file=open(fname, "rb")
            )
            os.remove(fname)
            if "goodbye" in transcription.text.lower():
                talking = False
            
            conversation.append({"role": "user", "content": transcription.text})

            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=conversation
            )
            reply = completion.choices[0].message.content
            conversation.append({"role": "assistant", "content": reply})
            response = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=reply,
            )

            fname = os.urandom(4).hex() + ".opus"
            response.stream_to_file(fname)
            # length = OggOpus(open(fname, "rb")).info.length
            vc.play(source=discord.FFmpegPCMAudio(source=fname))
            
            while ctx.voice_client.is_playing():
                await asyncio.sleep(0.1)

            fname = os.urandom(4).hex() + ".raw"
            files.append(fname)
            for file in files:
                os.remove(file)
        except Exception as e:
            print(e)
            continue

    await vc.disconnect()

bot.run(os.getenv("BOT"))
