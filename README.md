# DexScreener Monitor Bot

A Telegram bot that monitors DexScreener for new ads, token profiles, boosts, and paid orders across all blockchain networks.

## Features

- 📢 **Banner Ads** monitoring via `/ads/latest/v1`
- 📝 **Token Profiles** monitoring via `/token-profiles/latest/v1`
- 🚀 **Token Boosts** monitoring via `/token-boosts/latest/v1`
- 💰 **Paid Orders** monitoring via `/orders/v1`
- 🌐 **All chains supported** - No filtering, monitors all blockchains
- 📱 **Telegram integration** with beautiful formatted messages
- 📊 **Chart images** included with each alert
- 📍 **Tap-to-copy** contract addresses
- 🔗 **Direct DexScreener links**

## Bot Commands

- `/start` - Welcome message and bot information
- `/status` - Current bot statistics and runtime

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from BotFather
   - `TELEGRAM_CHAT_ID` - Your Telegram chat ID
4. Run the bot: `python dexscreener_bot.py`

## Deployment

The bot can be deployed on Render, Heroku, or any Python-supporting platform.

### Environment Variables

- `TELEGRAM_BOT_TOKEN` - Required: Telegram bot token
- `TELEGRAM_CHAT_ID` - Required: Telegram chat ID to send alerts to

## Monitoring

The bot monitors:
- Banner advertisements
- Token profile creations
- Token boost increases
- All types of paid orders (tokenProfile, tokenAd, communityTakeover)

Alerts are sent in real-time when new events are detected.
