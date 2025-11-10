# Multi-Strategy Trading System

Scalable algorithmic trading system supporting multiple Alpaca accounts with proper timezone handling, state persistence, and daily email logs.

## Features

- ✅ Multiple Alpaca accounts (one per strategy)
- ✅ Proper timezone handling (server UTC → market ET)
- ✅ State persistence (survives redeploys)
- ✅ Daily email logs
- ✅ Month-end rebalancing at 3:30 PM ET
- ✅ Easy to add new strategies

## Quick Start

### 1. Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your Alpaca credentials

# Run locally
python main.py
```

### 2. Deploy to Render
```bash
# Create GitHub repo
git init
git add .
git commit -m "Initial trading system"
git push origin main

# In Render dashboard:
# 1. New > Worker
# 2. Connect GitHub repo
# 3. Add environment variables from .env.example
# 4. Deploy
```

### 3. Adding New Strategies

**Step 1:** Create strategy file in `strategies/`

**Step 2:** Add to `config/strategies.yaml`:
```yaml
- name: my_new_strategy
  class: MyStrategy
  module: strategies.my_strategy
  enabled: true
  account:
    api_key_env: ALPACA_NEW_API_KEY
    secret_key_env: ALPACA_NEW_SECRET_KEY
    paper_env: ALPACA_NEW_PAPER
```

**Step 3:** Add credentials to Render

**Step 4:** Deploy

## Email Setup (Gmail)

1. Enable 2FA on Gmail
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use App Password as SENDER_PASSWORD

## Cost

- Render: $7/month
- Alpaca: Free (paper) or minimum $1,500 (live)

## Monitoring

- Logs: `/data/trading.log` on server
- Daily emails: Sent at 5 PM ET
- Render dashboard: Real-time logs