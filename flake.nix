{
  description = "Shell for Slurming Firesim Simulations";

  # Nixpkgs version to use
  inputs.nixpkgs.url = "nixpkgs/nixos-25.11";

  outputs = { self, nixpkgs }:
    let
      # System types to support.
      # I have only ever tested this on x86_64-linux, so we limit to that.
      supportedSystems = [ "x86_64-linux" ]; # "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      # Helper function to generate an attrset '{ x86_64-linux = f "x86_64-linux"; ... }'.
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Nixpkgs instantiated for supported system types.
      nixpkgsFor = forAllSystems (system: import nixpkgs {
        inherit system;
        overlays = [
          self.overlays.default
        ];
      });

    in
      {
        # Overlay nixpkgs
        overlays.default = final: prev: {
          # Downgrade slurm to what we have on the cheese cluster
          slurm = prev.slurm.overrideAttrs (prevAttrs: rec {
            version = "21.08.8.2";
            src = prev.fetchFromGitHub {
              owner = "SchedMD";
              repo = "slurm";
              # Slurm's tags use - instead of .
              tag = "slurm-${builtins.replaceStrings [ "." ] [ "-" ] version}";
              hash = "sha256-3Q9h7XgnMTqn0F0C+CJ2r3rOxHbDhOjFjsM5mg6yL9k=";
            };
            configureFlags = prevAttrs.configureFlags ++ ([
              "--without-rpath"
              # Disable pmix for MPI. There are build issues with pmix and this
              # version of Slurm. Since we only want the development headers out
              # of Slurm's core anyways, this is not really a loss for us.
              # This also avoids us from needing to deal with the pmix patch
              # that used to be needed for this version of Slurm.
              "--with-pmix=no"
            ]);
          });
          # So we can build an older version of pyslurm
          python312 = prev.python312.override {
            packageOverrides = python-final: python-prev: {
              pyslurm = python-prev.pyslurm.overridePythonAttrs (prevAttrs: rec {
                version = "21.8.0";
                src = prev.fetchFromGitHub {
                  owner = "PySlurm";
                  repo = "pyslurm";
                  tag = "v${version}";
                  hash = "sha256-9ZYTBO8g+5B9D8Ll5JjkJYFyh0RQNIjxg958UZoCNmA=";
                };
                # According to the docs, buildPythonPackage falls back to using
                # setup.py when pyproject = true and no pyproject.toml exists.
                # However, this actually uses Nixpkgs' pypa build tooling, which
                # is slightly incompatible with the way flags get passed to
                # setup.py.
                # Overriding pyproject to null and setting the format to
                # "setuptools" yields Nixpkgs' old setuptools-build-hook.
                pyproject = null;
                format = "setuptools";
                build-system = [ python-prev.setuptools ];
                buildInputs = [
                  final.slurm
                  python-prev.cython_0
                ];
                setupPyBuildFlags = [
                  # NOTE: The slurm package here points to our older version's
                  # checkout in this overlay.
                  "--slurm-lib=${final.slurm}/lib"
                  "--slurm-inc=${final.slurm.dev}/include"
                ];
              });

              rassumfrassum = python-prev.buildPythonPackage rec {
                pname = "rassumfrassum";
                version = "0.3.3";
                pyproject = true;

                disabled = final.python3Packages.pythonOlder "3.10";

                src = final.pkgs.fetchFromGitHub {
                  owner = "joaotavora";
                  repo = "rassumfrassum";
                  tag = "v${version}";
                  hash = "sha256-3Hcews5f7o45GUmFdpLwkAHf0bthC1tUikkxau952Ec=";
                };

                build-system = [ python-prev.setuptools ];

                meta = {
                  homepage = "";
                  description = "";
                  license = final.lib.licenses.gpl3Plus;
                  maintainers = [];
                };
              };
            };
          };
          # Make the packages in the override set above show up in Python3Packages
          # so withPackages can see them too.
          python3Packages = final.python3.pkgs;
        };

        # This flake does not provide any packages
        packages = {};

        # This flake does not provide any packages, so it cannot have apps
        # either.
        # apps is meant to play with the "nix run" command.
        apps = {};

        # What we really want
        devShells = forAllSystems (system:
          let pkgs = nixpkgsFor.${system};
              pythonEnv = pkgs.python312.withPackages (ps: with ps; [
                ruff
                uv
                rassumfrassum
                pytest
                # pyproject.toml stuff
                installer
                packaging
                pyproject-hooks
                wheel
                build
                setuptools
                # Work with Slurm from Python
                pyslurm
              ]);

          in {
            default = pkgs.mkShell {
              # nativeBuildInputs = riscvNativeBuildInputs;
              buildInputs = with pkgs; [
                pythonEnv
                ty
                pre-commit

                # keep this line if you use bash
                bashInteractive
              ];

              # Ensure locales are present
              LOCALE_ARCHIVE = "${pkgs.glibcLocales}/lib/locale/locale-archive";
            };
          });
      };
}
