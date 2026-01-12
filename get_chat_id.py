#!/usr/bin/env python3
"""
Helper script to get your Telegram chat ID
"""
import requests
import json

BOT_TOKEN = "8563728034:AAEoDs-ojaO2h-6pAlpuZTd9NXZGKiJFHRo"

print("📱 Getting your Telegram Chat ID...")
print("-" * 50)
print("\n1. Open Telegram")
print("2. Search for your bot and start a chat")
print("3. Send any message to the bot (e.g., 'hi')")
print("4. Then press Enter here to continue...")
input()

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url)
data = response.json()

if not data.get("ok"):
    print("❌ Error getting updates from Telegram")
    exit(1)

updates = data.get("result", [])
if not updates:
    print("❌ No messages found. Please send a message to your bot first!")
    exit(1)

# Get the most recent message
latest_update = updates[-1]
chat = latest_update.get("message", {}).get("chat", {})
chat_id = chat.get("id")
chat_type = chat.get("type")
username = chat.get("username", "N/A")
first_name = chat.get("first_name", "N/A")

print("\n✅ Found your chat ID!")
print("-" * 50)
print(f"Chat ID: {chat_id}")
print(f"Chat Type: {chat_type}")
print(f"Username: {username}")
print(f"First Name: {first_name}")
print("-" * 50)
print(f"\n📝 Add this to your .env file:")
print(f"TELEGRAM_CHAT_ID={chat_id}")
