{
  pkgs ? import <nixpkgs> { },
}:
(pkgs.mkShell.override { stdenv = pkgs.clangStdenv; }) {
  packages = with pkgs; [
    binutils
    cargo
    clang
    gnumake
    llvm
    python313
    rustc
    rustfmt
    uv
  ];
  ASM_CC = "${pkgs.llvmPackages.clang-unwrapped}/bin/clang";
}
