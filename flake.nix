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
          python3 = prev.python3.override {
            packageOverrides = python-final: python-prev: {
              rassumfrassum = final.python3Packages.buildPythonPackage rec {
                pname = "rassumfrassum";
                version = "0.3.3";
                pyproject = true;

                # disabled = final.python3Packages.pythonOlder "3.10";

                src = final.pkgs.fetchFromGitHub {
                  owner = "joaotavora";
                  repo = "rassumfrassum";
                  tag = "v${version}";
                  hash = "sha256-3Hcews5f7o45GUmFdpLwkAHf0bthC1tUikkxau952Ec=";
                };

                build-system = [ final.python3Packages.setuptools ];

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
              pythonEnv = pkgs.python3.withPackages (ps: with ps; [
                ruff
                uv
                rassumfrassum
                # pyproject.toml stuff
                installer
                packaging
                pyproject-hooks
                wheel
                build
                setuptools
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
