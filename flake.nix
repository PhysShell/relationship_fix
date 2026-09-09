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

      # The activation choreography ships inside the same store path as the two
      # binaries it drives, which is what makes "release identity" a fact rather
      # than a convention. One `nix copy` moves the server, the migrator and the
      # script that sequences them; there is no way to end up running migration
      # 17 against application 18, because there is only ever one path.
      annotationWebFor = system:
        ((haskellFor system).callCabal2nix
          "relationship-fix-annotation-web"
          ./src/annotation-web
          { }).overrideAttrs (old: {
            postInstall = (old.postInstall or "") + ''
              install -Dm755 ${./deploy/activate.sh} \
                $out/libexec/annotation-web/activate.sh
              install -Dm644 ${./deploy/backends/systemd.sh} \
                $out/libexec/annotation-web/backends/systemd.sh
              mkdir -p $out/bin
              ln -s ../libexec/annotation-web/activate.sh \
                $out/bin/annotation-web-activate

              # What the pilot surface proves at start, shipped inside the same
              # release as the server that proves it: the package registry, the
              # sealed package's seal and presentation packets (never items.jsonl
              # or presentation-map/ -- the server must not hold canonical ids),
              # the instruction document and the pinned ontology. RF_REPO_ROOT
              # points here; issuance records stay host state (RF_ISSUANCE_DIR).
              share=$out/share/relationship-fix
              install -Dm644 ${./data/pilot/package-registry.json} \
                $share/data/pilot/package-registry.json
              install -Dm644 ${./data/pilot/v0.1/CHECKSUMS.sha256} \
                $share/data/pilot/v0.1/CHECKSUMS.sha256
              mkdir -p $share/data/pilot/v0.1/presentation
              cp ${./data/pilot/v0.1/presentation}/*.jsonl \
                $share/data/pilot/v0.1/presentation/
              install -Dm644 ${./docs/pilot-v0.1-instructions.md} \
                $share/docs/pilot-v0.1-instructions.md
              install -Dm644 ${./data/ontology/behavior-v0.1.json} \
                $share/data/ontology/behavior-v0.1.json
            '';
          });

      # justStaticExecutables here means the Haskell package dependencies are
      # linked statically — not "a single freestanding ELF with no libc": the
      # measured 28-path, 81.6 MiB closure below is a small self-contained
      # Nix closure, not one mystery file. This is the artifact meant for
      # `nix copy`/deployment; `annotation-web` above stays the normal
      # nixpkgs-dynamic build used for tests/check/dev/reference.
      annotationWebDeployFor = system:
        (pkgsFor system).haskell.lib.justStaticExecutables
          (annotationWebFor system);
    in
    {
      packages = forAllSystems (system: rec {
        annotation-web = annotationWebFor system;
        annotation-web-deploy = annotationWebDeployFor system;
        default = annotation-web;
      });

      apps = forAllSystems (system: rec {
        annotation-web = {
          type = "app";
          program = "${annotationWebFor system}/bin/annotation-web";
        };
        # The two halves of the migration contract are both runnable, because
        # "the server will not start until you have run the other one" is much
        # less annoying when the other one is one command away.
        annotation-web-migrate = {
          type = "app";
          program = "${annotationWebFor system}/bin/annotation-web-migrate";
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
