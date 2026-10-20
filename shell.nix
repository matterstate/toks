{
  pkgs ? import <nixpkgs> { },
}:
pkgs.mkShell {
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
  CC = "${pkgs.clang}/bin/clang";
  ASM_CC = "${pkgs.llvmPackages.clang-unwrapped}/bin/clang";
}
