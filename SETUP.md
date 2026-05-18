# Vantage Point — Setup Guide

## Quick Deploy (Netlify Drop)
1. Go to https://app.netlify.com/drop
2. Drag the **entire `vantage-point-deploy` folder** onto the page
3. Your site goes live instantly at a URL like `https://random-name.netlify.app`
4. Optional: set a custom subdomain in Site Settings → Domain management

## Files
| File | Purpose |
|------|---------|
| `index.html` | Full single-file React app |
| `vp-data.js` | Real insider trade data (1,063 transactions, refreshed by pipeline) |
| `netlify.toml` | Security headers & cache rules |

## Refreshing Data
Run the Python pipeline to pull fresh data from yfinance + HouseStockTrades:
```bash
pip install yfinance requests
python3 build_vp_snapshot.py --source index.html --out vp-data.js
```
Then re-deploy by dragging the folder again to Netlify Drop, or push to GitHub + connect repo.

## Supabase Auth (optional — enables watchlists & email alerts)
1. Create a free project at https://supabase.com
2. In `index.html` replace:
   ```js
   const SUPABASE_URL = 'YOUR_SUPABASE_URL';
   const SUPABASE_ANON_KEY = 'YOUR_SUPABASE_ANON_KEY';
   ```
3. Run this SQL in Supabase SQL Editor:
   ```sql
   create table watchlists (
     id uuid default gen_random_uuid() primary key,
     user_id uuid references auth.users not null,
     ticker text not null,
     created_at timestamptz default now()
   );
   alter table watchlists enable row level security;
   create policy "Users manage own watchlist"
     on watchlists for all using (auth.uid() = user_id);
   ```
4. Enable Email auth in Supabase Authentication → Providers

## Resend Email Alerts (optional)
1. Create account at https://resend.com (free: 3,000 emails/month)
2. Deploy a Supabase Edge Function that calls `https://api.resend.com/emails`
3. Trigger it from a Supabase Database Webhook on your watchlists/alerts table

## Custom Domain
- In Netlify: Site Settings → Domain management → Add custom domain
- Point your DNS CNAME to `[site-name].netlify.app`
