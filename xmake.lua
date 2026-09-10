set_project("pacman-native")
set_version("0.1.0")
set_languages("c++23")
set_toolchains("clang")

add_rules("mode.debug", "mode.release")
set_policy("build.across_targets_in_parallel", true)

set_warnings("all", "extra")
add_cxxflags("-Wpedantic", "-Wconversion", "-Wshadow", {tools = {"gcc", "clang"}})

add_rules(
    "plugin.compile_commands.autoupdate",
    {outputdir = ".build"}
)

if is_plat("wasm") then
    target("pacman-wasm")
        set_kind("shared")
        set_toolchains("emcc")
        add_includedirs("native/include", "native/src")
        add_files("native/abi/**.cpp")
        add_files("native/src/**.cppm")
        add_files("native/kernels/scalar/**.cppm")
        add_cxflags("-fvisibility=hidden")
else
    target("pacman-kernel-scalar")
        set_kind("static")
        set_default(false)
        add_files("native/kernels/scalar/**.cppm", {public = true})
        add_cxflags("-fvisibility=hidden")

    target("pacman-core")
        set_kind("static")
        set_default(false)
        add_deps("pacman-kernel-scalar")
        add_includedirs("native/src")
        add_files("native/src/**.cppm", {public = true})
        add_cxflags("-fvisibility=hidden")

    target("pacman-native")
        set_kind("shared")
        add_deps("pacman-core")
        add_includedirs("native/include")
        add_headerfiles("native/include/(pacman/*.h)")
        add_files("native/abi/**.cpp")
        add_cxflags("-fvisibility=hidden")
        add_rules("utils.symbols.export_list", {symbols = {
            "pac_abi_version",
            "pac_bitboard_or"
        }})
end
