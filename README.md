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

