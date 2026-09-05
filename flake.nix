{
  description = "Relationship Fix — annotation instrument";

  # The git transport rather than the more usual github: shorthand, because
  # that shorthand resolves through api.github.com, which is not reachable from
  # every environment this repository is built in. A git ref locks to a
  # revision in flake.lock exactly the same way.
  inputs.nixpkgs.url = "git+https://github.com/NixOS/nixpkgs?ref=nixos-unstable&shallow=1";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: nixpkgs.legacyPackages.${system};

      # The default package set, not haskell.packages.ghc9103, even though the
      # two are the same compiler at this pin: only the default set is covered
      # by cache.nixos.org, and the difference is minutes against hours. The
      # package's own `base >=4.20 && <4.21` bound fails loudly if that ever
      # stops being GHC 9.10.
      haskellFor = system: (pkgsFor system).haskellPackages;

      annotationWebFor = system:
        (haskellFor system).callCabal2nix
          "relationship-fix-annotation-web"
          ./src/annotation-web
          { };
    in
    {
      packages = forAllSystems (system: rec {
        annotation-web = annotationWebFor system;
        default = annotation-web;
      });

      apps = forAllSystems (system: rec {
        annotation-web = {
          type = "app";
          program = "${annotationWebFor system}/bin/annotation-web";
        };
        default = annotation-web;
      });

      # Builds the package and runs its test suite.
      checks = forAllSystems (system: {
        annotation-web = annotationWebFor system;
      });

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          haskell = haskellFor system;
        in
        {
          default = pkgs.mkShell {
            packages = [
              haskell.ghc
              pkgs.cabal-install
              pkgs.sqlite
            ];
          };
        });
    };
}
