# Project-Choice-Maxxing

A voting application for comparing and ranking options using various voting algorithms.

## Development (Recommended: Nix Flake)

### Prerequisites
- [Nix package manager](https://nixos.org/download.html) with flakes enabled
- Optional: [direnv](https://direnv.net/) for automatic environment loading

### Quick Start

1. **Enter development environment:**
   ```bash
   nix develop
   ```

2. **Start the app in development mode (with auto-reload):**
   ```bash
   dev-voting-app
   ```

3. **Or start normally:**
   ```bash
   launch-voting-app
   ```

The app will be available at http://localhost:5000

### Available Commands

Once in the Nix shell, you have access to:

- `dev-voting-app` - Start with auto-reload (recommended for development)
- `launch-voting-app` - Start normally 
- `build-docker` - Build Docker image
- `test-voting-app` - Run syntax tests
- `python` - Python with all dependencies (Flask, etc.)

### Auto Environment (Optional)

If you have `direnv` installed:

1. Allow the directory: `direnv allow`
2. The environment will automatically activate when you enter the project directory

## Traditional Development

If you prefer not to use Nix:

1. **Install Python dependencies:**
   ```bash
   cd voting-app
   pip3 install -r requirements.txt
   ```

2. **Run the app:**
   ```bash
   python3 app.py
   ```

## Docker Deployment

The app includes Docker support with persistent data volumes. See the modified Dockerfile that preserves poll data between deployments.

## Configuration

The app reads configuration from environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `5000` | Bind port |
| `FLASK_DEBUG` | `0` | `1` enables the Werkzeug debugger — **never** in production |
| `FLASK_SECRET_KEY` | auto-generated to `data/.secret_key` | Session signing key. Set explicitly in production |
| `FLASK_ADMIN_USER` | `admin` | Username seeded on first launch when `data/users.csv` is empty |
| `FLASK_ADMIN_PASS` | `admin` | Password seeded on first launch. **Change this immediately after first login.** |
| `MAX_POLLS_PER_USER` | `50` | Per-user poll cap. Admins are exempt. |

## Accounts

Anyone can sign up at `/signup` to create a regular (non-admin) account. New accounts can create up to `MAX_POLLS_PER_USER` polls (50 by default); when they hit the cap they're shown a popup telling them to delete an old poll. Admins are exempt from the cap and can manage every poll plus other users.

Admins can promote/demote/delete other users from **Users** in the dashboard header. Anyone can change their own password under **Change Password**.

## Testing

```bash
cd voting-app
python3 -m pytest
```

The suite covers auth, poll CRUD, voting (including the previously-crashing blank/duplicate username paths), and the five voting algorithms. Requires Python 3.12+ historically, but inner-quote f-strings have been rewritten so 3.10+ works.

