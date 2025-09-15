# BMM - Brawl Stars Matchmaking Bot

A Discord bot designed to facilitate random ranked matches in Brawl Stars, providing matchmaking, leaderboards, and map management features.

## Features

- **Matchmaking System**: Organize and manage ranked matches between players.
- **Leaderboards**: Track player rankings and statistics.
- **Map Pools**: Customize and manage available maps for matches.
- **Guild Settings**: Configure bot behavior per Discord server.
- **Admin Controls**: Manage admins, blocked users, and server-specific options.

## Installation

### Prerequisites
- Python 3.8 or higher
- MongoDB database
- Discord Bot Token
- Brawl Stars API Key

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/shegyo/BMM.git
   cd BMM
   ```

2. Install dependencies:
   ```bash
   pip install discord.py pymongo requests
   ```

3. Set up environment variables:
   - Copy `data/env.json.example` to `data/env.json` (if exists, otherwise create)
   - Fill in your Discord bot token, Brawl Stars API key, MongoDB connection string, etc.

4. Run the bot:
   ```bash
   python BMM.py
   ```

## Usage

1. Invite the bot to your Discord server using the OAuth2 URL with appropriate permissions.
2. Use slash commands to interact with the bot:
   - `/maps`: View current map pool
   - `/map_add <map>`: Add a map to the pool (admin only)
   - `/map_remove <map>`: Remove a map from the pool (admin only)
   - And more commands available in the cogs.

## Configuration

- Sensitive data like API keys are stored in `data/env.json` (ignored by git).
- Admin lists are in `admins.json`, `allowed.json`, `blockedAdmins.json` (also ignored).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
