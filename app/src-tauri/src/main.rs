// Esconde a consola extra no Windows em modo release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    friday_lib::run()
}
