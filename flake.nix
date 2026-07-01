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
          ${pythonEnv}/bin/flask run --host=0.0.0.0 --port=5001 --reload
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

        # The app packaged into the Nix store: source + templates + static,
        # plus a `voting-app` launcher that runs it with the pinned Python env.
        # This is the single source of truth the OCI image is built from.
        votingApp = pkgs.stdenv.mkDerivation {
          pname = "voting-app";
          version = "1.0.0";
          src = ./voting-app;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontBuild = true;
          installPhase = ''
            runHook preInstall
            mkdir -p $out/share/voting-app
            # Ship code + assets, but NOT the checked-in data/ dir — the running
            # container writes its CSV store to a fresh, writable /data instead.
            cp -r app.py algorithms.py templates static $out/share/voting-app/
            makeWrapper ${pythonEnv}/bin/python $out/bin/voting-app \
              --add-flags "$out/share/voting-app/app.py"
            runHook postInstall
          '';
        };

        # A ready-to-run Docker/OCI image built straight from the flake — no
        # Dockerfile. Consumers `docker pull` / `docker run`; they never touch
        # Nix. Layered so shared deps (Python, glibc) dedupe across rebuilds.
        dockerImage = pkgs.dockerTools.buildLayeredImage {
          name = "deekahy/voting-app";
          tag = "latest";
          # cacert so any outbound TLS works; the app itself is self-contained.
          contents = [ votingApp pkgs.cacert ];
          config = {
            Cmd = [ "${votingApp}/bin/voting-app" ];
            ExposedPorts = { "5000/tcp" = { }; };
            # DATA_DIR points at a writable volume because the app's own dir
            # lives in the read-only Nix store. HOST/PORT match the Dockerfile.
            Env = [
              "DATA_DIR=/data"
              "HOST=0.0.0.0"
              "PORT=5000"
              "FLASK_ENV=production"
              "FLASK_DEBUG=0"
            ];
            WorkingDir = "/data";
            Volumes = { "/data" = { }; };
          };
          # Create the mount point (and a world-writable /tmp) inside the image.
          extraCommands = ''
            mkdir -p data tmp
            chmod 1777 tmp
          '';
        };

      in
      {
        packages = {
          default = votingApp;
          voting-app = votingApp;
          inherit dockerImage;
        };

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
