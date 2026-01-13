#!/usr/bin/env python3
"""
DexScreener Monitor Bot - Tracks ads, boosts, and paid orders
"""
import os
import time
import json
import logging
from typing import Any, Dict, Optional, Set
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# DexScreener API endpoints
DEX_ADS_URL = "https://api.dexscreener.com/ads/latest/v1"
DEX_BOOST_URL = "https://api.dexscreener.com/token-boosts/latest/v1"
DEX_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_ORDERS_URL = "https://api.dexscreener.com/orders/v1/{chain_id}/{token_address}"
DEX_TOKENS_URL = "https://api.dexscreener.com/tokens/v1/{chain_id}/{token_address}"

# Configuration
POLL_INTERVAL_SECONDS = 2.0  # Poll every 2 seconds to avoid rate limits

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
USE_TELEGRAM = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Track bot start time
BOT_START_TIME = datetime.now(timezone.utc)

# Statistics
stats = {
    "start_time": datetime.now(),
    "polls": 0,
    "ads_detected": 0,
    "boosts_detected": 0,
    "orders_detected": 0,
    "errors": 0,
}

# Memory of what we've seen
seen_ads: Set[tuple] = set()  # (chain_id, token_address)
seen_boosts: Dict[str, float] = {}  # token_address -> totalAmount
seen_orders: Dict[str, int] = {}  # token_address -> latest_payment_timestamp
seen_profiles: Set[tuple] = set()  # (chain_id, token_address)

# Store higher-resolution header images for profiles when available
profile_headers: Dict[tuple, str] = {}  # (chain_id, token_address) -> header URL

# Store social links for profiles
profile_socials: Dict[tuple, list] = {}  # (chain_id, token_address) -> list of social links

# Track all known tokens to check for orders
known_tokens: Set[tuple] = set()  # (chain_id, token_address)


def fetch_json(url: str, *, timeout: float = 10.0) -> Optional[Any]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as exc:
        stats["errors"] += 1
        return None


def get_token_info(chain_id: str, token_address: str) -> Dict[str, Any]:
    url = DEX_TOKENS_URL.format(chain_id=chain_id, token_address=token_address)
    data = fetch_json(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return {}

    pair = data[0]
    base = pair.get("baseToken") or {}

    return {
        "name": base.get("name") or token_address[:8] + "...",
        "symbol": base.get("symbol") or "",
        "price_usd": pair.get("priceUsd"),
        "market_cap": pair.get("marketCap") or pair.get("fdv"),
    }


def format_price(price: Any) -> str:
    try:
        p = float(price)
        if p >= 1:
            return f"{p:,.2f}"
        return f"{p:.8f}".rstrip("0").rstrip(".")
    except:
        return "N/A"


def format_market_cap(mc: Any) -> str:
    try:
        return f"{int(float(mc)):,}"
    except:
        return "N/A"


def send_telegram_photo(photo_url: str, caption: str) -> bool:
    """Send photo with caption to Telegram"""
    if not USE_TELEGRAM:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            return True
        else:
            # Fallback to text message if photo fails
            return send_telegram_message(caption)
    except Exception as e:
        logger.warning(f"Telegram photo send error: {e}")
        # Fallback to text message
        return send_telegram_message(caption)


def send_telegram_message(text: str) -> bool:
    """Send message to Telegram"""
    if not USE_TELEGRAM:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logger.warning(f"Telegram send failed: {response.status_code}")
            return False
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


def format_telegram_alert(event_type: str, token_info: dict, chain_id: str, token_address: str, extra_info: dict = None) -> tuple:
    """Format a beautiful Telegram alert message and return (message, image_url)"""
    
    # Choose emoji based on event type
    emojis = {
        "AD": "📢",
        "PROFILE": "📝",
        "BOOST": "🚀",
        "ORDER": "💰"
    }
    emoji = emojis.get(event_type, "🔔")
    
    # Build the message with better formatting
    lines = []
    lines.append(f"<b>{emoji} {event_type} ALERT</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━")
    
    # Token info section
    name = token_info.get('name', 'Unknown')
    symbol = token_info.get('symbol', '')
    lines.append(f"💎 <b>{name}</b> {f'({symbol})' if symbol else ''}")
    lines.append(f"⛓️ Chain: <b>{chain_id.upper()}</b>")
    
    # Price info
    price = token_info.get('price_usd')
    if price:
        lines.append(f"💰 Price: <b>${format_price(price)}</b>")
    
    market_cap = token_info.get('market_cap')
    if market_cap:
        lines.append(f"📊 Market Cap: <b>${format_market_cap(market_cap)}</b>")
    
    lines.append("")
    
    # Extra info based on event type
    if extra_info:
        if event_type == "BOOST":
            if 'amount' in extra_info:
                lines.append(f"⚡ New Boost: <b>{extra_info['amount']}</b>")
            if 'total' in extra_info:
                lines.append(f"📈 Total Boosts: <b>{extra_info['total']}</b>")
        elif event_type == "ORDER":
            if 'order_type' in extra_info:
                lines.append(f"📋 Order Type: <b>{extra_info['order_type']}</b>")
            if 'status' in extra_info:
                lines.append(f"✅ Status: <b>{extra_info['status']}</b>")
            if 'paid_at' in extra_info:
                lines.append(f"🕐 Paid: {extra_info['paid_at']}")
        elif event_type == "AD":
            if 'duration' in extra_info:
                lines.append(f"⏱️ Duration: <b>{extra_info['duration']} hours</b>")
            if 'date' in extra_info:
                lines.append(f"📅 Started: {extra_info['date']}")
    
    # Add description if available
    if 'description' in extra_info and extra_info['description']:
        lines.append("")
        lines.append(f"📄 Description: {extra_info['description'][:200]}")
    
    # Add social links if available
    if 'social_links' in extra_info and extra_info['social_links']:
        lines.append("")
        lines.append("🔗 <b>Socials:</b>")
        for link in extra_info['social_links'][:5]:  # Limit to 5 links
            link_type = link.get('type', 'link')
            link_url = link.get('url', '')
            if link_url:
                # Use appropriate emoji for each social type
                emoji_map = {
                    'twitter': '𝕏',
                    'telegram': '✈️',
                    'discord': '💬',
                    'website': '🌐',
                    'reddit': '🔴'
                }
                emoji = emoji_map.get(link_type.lower(), '🔗')
                label = link.get('label', link_type.title())
                lines.append(f"  {emoji} <a href='{link_url}'>{label}</a>")
    
    lines.append("")
    
    # Contract address (copyable)
    lines.append("📍 <b>Contract (tap to copy):</b>")
    lines.append(f"<code>{token_address}</code>")
    lines.append("")
    
    # DexScreener link
    dex_url = f"https://dexscreener.com/{chain_id}/{token_address}"
    lines.append(f"🔗 <a href='{dex_url}'>View on DexScreener</a>")
    lines.append("━━━━━━━━━━━━━━━━━")
    
    message = "\n".join(lines)
    
    # Image priority: stored profile image > full chart > thumbnail
    image_url = None
    
    # First try: high-res image from profile (openGraph/header/icon)
    if extra_info and isinstance(extra_info, dict):
        image_url = extra_info.get("header_image")
    
    # Second try: full-size chart (much better than thumbnail)
    if not image_url:
        # Try to get a full-size chart image
        image_url = f"https://api.dexscreener.com/token-chart-img/{chain_id}/{token_address}"
        # Add size parameters for better quality
        image_url += "?w=800&h=450"
    
    # Last resort: small thumbnail (will be blurry)
    if not image_url:
        image_url = f"https://dd.dexscreener.com/ds-data/tokens/{chain_id}/{token_address}.png"
    
    return message, image_url


def print_alert(title: str, lines: list, emoji: str = "🚨") -> None:
    # Console output (keep as is)
    print("\n" + "=" * 70)
    print(f"{emoji} {title} {emoji}")
    print("=" * 70)
    for line in lines:
        print(f"  {line}")
    print("=" * 70)
    print()
    
    # Telegram output with new formatting
    if USE_TELEGRAM:
        # Extract key information from lines
        token_info = {}
        chain_id = ""
        token_address = ""
        extra_info = {}
        
        for line in lines:
            if line.startswith("Chain:"):
                chain_id = line.replace("Chain: ", "").strip()
            elif line.startswith("Token:"):
                parts = line.replace("Token: ", "").strip()
                if "(" in parts:
                    token_info['name'] = parts.split("(")[0].strip()
                    token_info['symbol'] = parts.split("(")[1].rstrip(")")
                else:
                    token_info['name'] = parts
            elif line.startswith("Address:"):
                token_address = line.replace("Address: ", "").strip()
            elif line.startswith("Price:"):
                # Extract raw price value without formatting
                price_str = line.replace("Price: ", "").replace("$", "").strip()
                token_info['price_usd'] = price_str
            elif line.startswith("Market Cap:"):
                # Extract raw market cap value without formatting
                mc_str = line.replace("Market Cap: ", "").replace("$", "").replace(",", "").strip()
                token_info['market_cap'] = mc_str
            elif line.startswith("Description:"):
                extra_info['description'] = line.replace("Description: ", "").strip()
            elif line.startswith("New Boost:"):
                parts = line.replace("New Boost: ", "").split("(Total:")
                extra_info['amount'] = parts[0].strip()
                if len(parts) > 1:
                    extra_info['total'] = parts[1].rstrip(")")
            elif line.startswith("Order Type:"):
                extra_info['order_type'] = line.replace("Order Type: ", "").strip()
            elif line.startswith("Status:"):
                extra_info['status'] = line.replace("Status: ", "").strip()
            elif line.startswith("Paid At:"):
                extra_info['paid_at'] = line.replace("Paid At: ", "").strip()
            elif line.startswith("Duration:"):
                extra_info['duration'] = line.replace("Duration: ", "").replace(" hours", "").strip()
            elif line.startswith("Started:"):
                extra_info['date'] = line.replace("Started: ", "").strip()
            elif line.startswith("URL:"):
                extra_info['url'] = line.replace("URL: ", "").strip()

        # Attach header image from stored profile data, if available
        if chain_id and token_address:
            key = (chain_id, token_address)
            header_img = profile_headers.get(key)
            if header_img:
                extra_info["header_image"] = header_img
            
            # Attach social links if available
            social_links = profile_socials.get(key)
            if social_links:
                extra_info["social_links"] = social_links
        
        # Determine event type from title
        event_type = "ALERT"
        if "PROFILE" in title:
            event_type = "PROFILE"
        elif "BOOST" in title:
            event_type = "BOOST"
        elif "ORDER" in title:
            event_type = "ORDER"
        elif "AD" in title:
            event_type = "AD"
        
        # Format and send the beautiful message
        message, chart_url = format_telegram_alert(event_type, token_info, chain_id, token_address, extra_info)
        
        # Try to send with image, fallback to text
        if not send_telegram_photo(chart_url, message):
            send_telegram_message(message)


def process_ads(ads: Any) -> None:
    """Process banner ads from /ads/latest/v1"""
    global seen_ads
    
    if not isinstance(ads, list):
        return

    for ad in ads:
        chain_id = ad.get("chainId")
        token_address = ad.get("tokenAddress")
        
        if not chain_id or not token_address:
            continue
        
        # Track token for order checking
        known_tokens.add((chain_id, token_address))
        
        key = (chain_id, token_address)
        if key in seen_ads:
            continue
        
        # New ad detected!
        seen_ads.add(key)
        stats["ads_detected"] += 1
        
        token_info = get_token_info(chain_id, token_address)
        
        lines = [
            f"Type: BANNER AD",
            f"Chain: {chain_id}",
            f"Token: {token_info.get('name')} ({token_info.get('symbol')})",
            f"Address: {token_address}",
            f"Started: {ad.get('date')}",
            f"Duration: {ad.get('durationHours')} hours",
            f"Price: ${format_price(token_info.get('price_usd'))}",
            f"Market Cap: ${format_market_cap(token_info.get('market_cap'))}",
        ]
        
        if ad.get("url"):
            lines.append(f"URL: {ad.get('url')}")
        
        print_alert("NEW AD", lines, "📢")
        logger.info(f"New ad: {token_address} on {chain_id}")


def process_profiles(profiles: Any) -> None:
    """Process token profiles from /token-profiles/latest/v1"""
    global seen_profiles, known_tokens, profile_headers, profile_socials
    
    if not isinstance(profiles, list):
        return
    
    for profile in profiles:
        chain_id = profile.get("chainId")
        token_address = profile.get("tokenAddress")
        
        if not chain_id or not token_address:
            continue
        
        key = (chain_id, token_address)
        
        # Track this token for order checking
        known_tokens.add(key)
        
        # Store high-resolution images from profile
        # Priority: openGraph > header > icon
        image_url = None
        if profile.get("openGraph"):
            image_url = profile.get("openGraph")
        elif profile.get("header"):
            image_url = profile.get("header")
        elif profile.get("icon"):
            image_url = profile.get("icon")
        
        if image_url:
            profile_headers[key] = image_url
        
        # Store social links if available
        if profile.get("links"):
            profile_socials[key] = profile.get("links")
        
        # Check if this is a new profile
        if key in seen_profiles:
            continue
        
        # New profile detected!
        seen_profiles.add(key)
        stats["orders_detected"] += 1
        
        token_info = get_token_info(chain_id, token_address)
        
        lines = [
            f"Type: TOKEN PROFILE",
            f"Chain: {chain_id}",
            f"Token: {token_info.get('name')} ({token_info.get('symbol')})",
            f"Address: {token_address}",
            f"Price: ${format_price(token_info.get('price_usd'))}",
            f"Market Cap: ${format_market_cap(token_info.get('market_cap'))}",
        ]
        
        if profile.get("description"):
            lines.append(f"Description: {profile.get('description')[:100]}...")
        
        if profile.get("url"):
            lines.append(f"URL: {profile.get('url')}")
        
        print_alert("NEW TOKEN PROFILE", lines, "📝")
        logger.info(f"New profile: {token_address} on {chain_id}")


def process_boosts(boosts: Any) -> None:
    """Process token boosts"""
    global seen_boosts, profile_headers
    
    if not isinstance(boosts, list):
        return
    
    for boost in boosts:
        chain_id = boost.get("chainId")
        token_address = boost.get("tokenAddress")
        total_amount = boost.get("totalAmount")
        
        if not chain_id or not token_address or total_amount is None:
            continue
        
        # Track token for order checking
        key = (chain_id, token_address)
        known_tokens.add(key)
        
        previous_amount = seen_boosts.get(token_address, 0)
        
        if total_amount <= previous_amount:
            continue
        
        # New or increased boost!
        seen_boosts[token_address] = total_amount
        stats["boosts_detected"] += 1
        
        token_info = get_token_info(chain_id, token_address)
        
        lines = [
            f"Type: TOKEN BOOST",
            f"Chain: {chain_id}",
            f"Token: {token_info.get('name')} ({token_info.get('symbol')})",
            f"Address: {token_address}",
            f"New Boost: {boost.get('amount')} (Total: {total_amount})",
        ]
        
        if previous_amount > 0:
            lines.append(f"Previous: {previous_amount} (+{total_amount - previous_amount})")
        
        lines.extend([
            f"Price: ${format_price(token_info.get('price_usd'))}",
            f"Market Cap: ${format_market_cap(token_info.get('market_cap'))}",
        ])
        
        print_alert("NEW BOOST", lines, "🚀")
        logger.info(f"New boost: {token_address} on {chain_id} - Total: {total_amount}")


def check_orders() -> None:
    """Check for new paid orders on known tokens"""
    global seen_orders, known_tokens
    
    # IMPORTANT: We need to discover NEW tokens with orders
    # The current approach only checks tokens we already know about
    # This misses tokens that ONLY have orders (no ads/boosts)
    
    # For now, check orders for all known tokens
    # TODO: Need a way to discover new tokens with orders
    for chain_id, token_address in list(known_tokens):
        url = DEX_ORDERS_URL.format(chain_id=chain_id, token_address=token_address)
        data = fetch_json(url)
        
        if not data:
            continue
        
        # Check for new orders
        orders = data.get("orders", [])
        for order in orders:
            payment_timestamp = order.get("paymentTimestamp", 0)
            
            # Skip orders that happened before bot started
            bot_start_ms = int(BOT_START_TIME.timestamp() * 1000)
            if payment_timestamp < bot_start_ms:
                continue
            
            # Check if this is a new order
            last_seen = seen_orders.get(token_address, 0)
            
            if payment_timestamp > last_seen:
                # New order detected!
                seen_orders[token_address] = payment_timestamp
                stats["orders_detected"] += 1
                
                token_info = get_token_info(chain_id, token_address)
                
                order_type = order.get("type", "unknown")
                status = order.get("status", "unknown")
                
                # Convert timestamp to readable date
                try:
                    payment_date = datetime.fromtimestamp(payment_timestamp / 1000, tz=timezone.utc)
                    date_str = payment_date.strftime("%Y-%m-%d %H:%M:%S UTC")
                except:
                    date_str = str(payment_timestamp)
                
                lines = [
                    f"Type: PAID ORDER - {order_type.upper()}",
                    f"Chain: {chain_id}",
                    f"Token: {token_info.get('name')} ({token_info.get('symbol')})",
                    f"Address: {token_address}",
                    f"Order Type: {order_type}",
                    f"Status: {status}",
                    f"Paid At: {date_str}",
                    f"Price: ${format_price(token_info.get('price_usd'))}",
                    f"Market Cap: ${format_market_cap(token_info.get('market_cap'))}",
                ]
                
                print_alert(f"NEW ORDER - {order_type.upper()}", lines, "💰")
                logger.info(f"New order: {token_address} on {chain_id} - Type: {order_type}")


def initialize():
    """Initialize the bot with current state"""
    print("🔍 Initializing bot...")
    
    # Get initial ads
    ads = fetch_json(DEX_ADS_URL)
    if isinstance(ads, list):
        for ad in ads:
            chain_id = ad.get("chainId")
            token_address = ad.get("tokenAddress")
            if chain_id and token_address:
                seen_ads.add((chain_id, token_address))
                known_tokens.add((chain_id, token_address))
        print(f"✅ Found {len(seen_ads)} active ads")
    
    # Load existing profiles
    profiles = fetch_json(DEX_PROFILES_URL)
    if profiles and isinstance(profiles, list):
        for profile in profiles:
            chain_id = profile.get("chainId")
            token_address = profile.get("tokenAddress")
            if chain_id and token_address:
                key = (chain_id, token_address)
                seen_profiles.add(key)
                known_tokens.add(key)
                
                # Store high-resolution images from profile
                # Priority: openGraph > header > icon
                image_url = None
                if profile.get("openGraph"):
                    image_url = profile.get("openGraph")
                elif profile.get("header"):
                    image_url = profile.get("header")
                elif profile.get("icon"):
                    image_url = profile.get("icon")
                
                if image_url:
                    profile_headers[key] = image_url
                
                # Store social links if available
                if profile.get("links"):
                    profile_socials[key] = profile.get("links")
        print(f"✅ Found {len(profiles)} token profiles")
    
    # Get initial boosts
    boosts = fetch_json(DEX_BOOST_URL)
    if isinstance(boosts, list):
        for boost in boosts:
            chain_id = boost.get("chainId")
            token_address = boost.get("tokenAddress")
            total_amount = boost.get("totalAmount")
            if chain_id and token_address and total_amount:
                seen_boosts[token_address] = total_amount
                known_tokens.add((chain_id, token_address))
        print(f"✅ Found {len(seen_boosts)} tokens with boosts")
    
    # Initialize order timestamps to avoid alerting on existing orders
    print(f"✅ Tracking {len(known_tokens)} tokens for new orders")
    bot_start_ms = int(BOT_START_TIME.timestamp() * 1000)
    
    # For all known tokens, record their latest order timestamp
    # This prevents alerting on orders that existed before bot started
    for chain_id, token_address in list(known_tokens):
        url = DEX_ORDERS_URL.format(chain_id=chain_id, token_address=token_address)
        data = fetch_json(url)
        if data:
            orders = data.get("orders", [])
            for order in orders:
                payment_timestamp = order.get("paymentTimestamp", 0)
                # Record all existing orders (even old ones) to prevent false alerts
                if payment_timestamp:
                    seen_orders[token_address] = max(seen_orders.get(token_address, 0), payment_timestamp)


def handle_telegram_updates():
    """Check for Telegram updates (commands) and respond"""
    if not USE_TELEGRAM:
        return
    
    try:
        # Get updates from Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    # Process commands
                    if "message" in update and "text" in update["message"]:
                        text = update["message"]["text"]
                        chat_id = update["message"]["chat"]["id"]
                        
                        if text.startswith("/start"):
                            # Send welcome message
                            welcome_msg = """
<b>🤖 DexScreener Monitor Bot Active!</b>

━━━━━━━━━━━━━━━━━
📊 <b>Currently Monitoring:</b>
• Banner Ads
• Token Profiles  
• Token Boosts
• Paid Orders

🌐 <b>All chains supported</b>

⚡ <b>Features:</b>
• Real-time alerts with charts
• Tap-to-copy contract addresses
• Direct DexScreener links
• Beautiful formatted messages

✅ <b>Bot is running and will alert you when new events are detected!</b>
━━━━━━━━━━━━━━━━━
"""
                            send_telegram_message(welcome_msg)
                        
                        elif text.startswith("/status"):
                            # Send status message
                            runtime = int((datetime.now() - stats["start_time"]).total_seconds())
                            status_msg = f"""
<b>📊 Bot Status</b>

⏱️ Runtime: {runtime}s
📢 Ads Detected: {stats['ads_detected']}
🚀 Boosts Detected: {stats['boosts_detected']}
💰 Orders Detected: {stats['orders_detected']}
📊 Total Polls: {stats['polls']}

✅ Bot is active and monitoring!
"""
                            send_telegram_message(status_msg)
                
                # Mark updates as read
                if data["result"]:
                    last_update_id = data["result"][-1]["update_id"]
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                    requests.get(url, params={"offset": last_update_id + 1}, timeout=5)
    except:
        pass  # Silently ignore errors in update handling


def main():
    print("\n🤖 DexScreener Monitor Bot")
    print("=" * 70)
    print("📊 Monitoring:")
    print("   • Banner Ads (/ads/latest/v1)")
    print("   • Token Profiles (/token-profiles/latest/v1)")
    print("   • Token Boosts (/token-boosts/latest/v1)")
    print("   • Paid Orders (/orders/v1)")
    print("🌐 All chains supported")
    print(f"🔄 Poll interval: {POLL_INTERVAL_SECONDS} seconds")
    
    if USE_TELEGRAM:
        print(f"📱 Telegram: Connected (Chat ID: {TELEGRAM_CHAT_ID})")
        # Send startup message
        startup_msg = "🟢 <b>Bot Started!</b>\n\nDexScreener Monitor is now active and watching for new events."
        send_telegram_message(startup_msg)
    else:
        print("📱 Telegram: Not configured")
    
    print("=" * 70)
    
    initialize()
    
    print("\n⏳ Monitoring for new events...\n")
    
    try:
        while True:
            stats["polls"] += 1
            
            # Check for Telegram commands every few polls
            if stats["polls"] % 3 == 0:
                handle_telegram_updates()
            
            # Fetch all endpoints
            ads = fetch_json(DEX_ADS_URL)
            profiles = fetch_json(DEX_PROFILES_URL)
            boosts = fetch_json(DEX_BOOST_URL)
            
            # Process them
            if ads:
                process_ads(ads)
            if profiles:
                process_profiles(profiles)
            if boosts:
                process_boosts(boosts)
            
            # Check orders every 5 polls to avoid rate limits
            if stats["polls"] % 5 == 0:
                check_orders()
            
            # Status update every 10 polls
            if stats["polls"] % 10 == 0:
                runtime = int((datetime.now() - stats["start_time"]).total_seconds())
                print(f"\r⏱️ {runtime}s | 📊 Polls: {stats['polls']} | 📢 Ads: {stats['ads_detected']} | 🚀 Boosts: {stats['boosts_detected']} | 💰 Orders: {stats['orders_detected']}", end="", flush=True)
            
            time.sleep(POLL_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n\n✅ Bot stopped!")
        print(f"Final stats: Ads: {stats['ads_detected']}, Boosts: {stats['boosts_detected']}, Orders: {stats['orders_detected']}")


if __name__ == "__main__":
    main()
