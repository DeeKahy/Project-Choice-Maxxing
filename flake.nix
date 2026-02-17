{
  description = "Project Choice Maxxing - Voting App Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        # Python with Flask and other dependencies
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          flask
          werkzeug
          jinja2
          click
          itsdangerous
          blinker
          markupsafe
        ]);

        # Launch script for the voting app
        launchScript = pkgs.writeShellScriptBin "launch-voting-app" ''
          #!/usr/bin/env bash
          cd voting-app
          echo "🚀 Starting Voting App on http://localhost:5000"
          export FLASK_ENV=development
          export FLASK_DEBUG=1
          ${pythonEnv}/bin/python app.py
        '';

        # Development script that launches with auto-reload
        devScript = pkgs.writeShellScriptBin "dev-voting-app" ''
          #!/usr/bin/env bash
          cd voting-app
          echo "🔄 Starting Voting App in development mode with auto-reload"
          export FLASK_ENV=development
          export FLASK_DEBUG=1
          export FLASK_APP=app.py
          ${pythonEnv}/bin/flask run --host=0.0.0.0 --port=5000 --reload
        '';

        # Docker build script
        buildDockerScript = pkgs.writeShellScriptBin "build-docker" ''
          #!/usr/bin/env bash
          cd voting-app
          echo "🐳 Building Docker image for voting app"
          ${pkgs.docker}/bin/docker build -t voting-app:latest .
        '';

        # Test script
        testScript = pkgs.writeShellScriptBin "test-voting-app" ''
          #!/usr/bin/env bash
          cd voting-app
          echo "🧪 Running tests for voting app"
          ${pythonEnv}/bin/python -m py_compile *.py
          echo "✅ Syntax check passed"
        '';

      in
      {
        devShells.default = pkgs.mkShell {
          name = "voting-app-dev";
          
          buildInputs = with pkgs; [
            pythonEnv
            launchScript
            devScript
            buildDockerScript
            testScript
            
            # Development tools
            git
            docker
            docker-compose
            
            # Optional: VS Code for development
            # vscode
          ];

          shellHook = ''
            echo "🎯 Project Choice Maxxing - Development Environment"
            echo "================================================"
            echo ""
            echo "Available commands:"
            echo "  launch-voting-app  - Start the app normally"
            echo "  dev-voting-app     - Start with auto-reload (recommended)"
            echo "  build-docker       - Build Docker image"
            echo "  test-voting-app    - Run syntax tests"
            echo ""
            echo "Python version: $(${pythonEnv}/bin/python --version)"
            echo "Flask available: $(${pythonEnv}/bin/python -c 'import flask; print(flask.__version__)' 2>/dev/null || echo 'Not found')"
            echo ""
            echo "To start developing: run 'dev-voting-app'"
            echo ""
            
            # Set up aliases for this session
            alias python="${pythonEnv}/bin/python"
            alias pip="${pythonEnv}/bin/pip"
            
            # Make sure we're in the right directory context
            export PYTHONPATH="$PWD/voting-app:$PYTHONPATH"
          '';

          # Environment variables
          FLASK_ENV = "development";
          FLASK_DEBUG = "1";
        };

        # Apps for direct running
        apps = {
          launch = flake-utils.lib.mkApp {
            drv = launchScript;
          };
          
          dev = flake-utils.lib.mkApp {
            drv = devScript;
          };
          
          build-docker = flake-utils.lib.mkApp {
            drv = buildDockerScript;
          };
          
          test = flake-utils.lib.mkApp {
            drv = testScript;
          };
        };

        # Default app
        defaultApp = self.apps.${system}.dev;
      });
}