#!/usr/bin/env python3
"""
Test script to verify bot setup and run a single poll cycle
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "8563728034:AAEoDs-ojaO2h-6pAlpuZTd9NXZGKiJFHRo"

print("🤖 DexScreener Alert Bot - Test Mode")
print("=" * 50)

# Step 1: Check for messages to get chat ID
print("\n📱 Checking for Telegram messages...")
url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url)
data = response.json()

if data.get("ok") and data.get("result"):
    latest = data["result"][-1]
    chat_id = latest.get("message", {}).get("chat", {}).get("id")
    username = latest.get("message", {}).get("from", {}).get("username", "Unknown")
    
    print(f"✅ Found chat with @{username}")
    print(f"   Chat ID: {chat_id}")
    
    # Update .env file
    print(f"\n📝 Updating .env file with chat ID...")
    with open(".env", "r") as f:
        lines = f.readlines()
    
    with open(".env", "w") as f:
        for line in lines:
            if line.startswith("TELEGRAM_CHAT_ID="):
                f.write(f"TELEGRAM_CHAT_ID={chat_id}\n")
            else:
                f.write(line)
    
    print("✅ .env file updated!")
    
    # Send test message
    print(f"\n📤 Sending test message to confirm setup...")
    test_msg = "✅ Bot setup complete!\n\nI will now monitor DexScreener for:\n• Solana tokens\n• BNB Chain tokens\n\nYou'll receive alerts when new ads or boosts are detected."
    
    msg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    msg_response = requests.post(msg_url, json={
        "chat_id": chat_id,
        "text": test_msg,
        "parse_mode": "HTML"
    })
    
    if msg_response.status_code == 200:
        print("✅ Test message sent successfully!")
    else:
        print(f"❌ Failed to send test message: {msg_response.text}")
    
    print("\n" + "=" * 50)
    print("🎉 Setup complete! You can now run the bot with:")
    print("   python bot.py")
    print("=" * 50)
    
else:
    print("❌ No messages found!")
    print("\nPlease:")
    print("1. Open Telegram")
    print("2. Search for your bot")
    print("3. Send it a message (like 'hi')")
    print("4. Run this script again")
    print("\nBot link: https://t.me/YOUR_BOT_USERNAME")
