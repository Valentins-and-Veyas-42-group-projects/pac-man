set_project("pacman-native")
set_version("0.1.0")
set_languages("c++23")

set_toolchains("clang")

add_rules("mode.debug", "mode.release")
set_policy("build.across_targets_in_parallel", true)
-- Sanitizer and release builds must not reuse incompatible module artifacts.
set_policy("build.c++.modules.reuse", false)

set_warnings("all", "extra")
add_cxxflags("-Wpedantic", "-Wconversion", "-Wshadow", { tools = { "gcc", "clang" } })

local function update_compile_commands()
	import("core.base.task")
	import("core.project.config")

	local lockpath = path.join(config.builddir(), ".gens", "pacman-compile-commands")
	local lock = io.openlock(lockpath .. ".lock")
	if not lock:trylock() then
		return
	end

	task.run("project", {
		kind = "compile_commands",
		outputdir = ".build",
		lsp = "clangd",
		target = false,
	})
	lock:close()
end

if is_plat("wasm") then
	target("pacman-wasm")
	set_kind("binary")
	set_extension(".mjs")
	set_default(false)
	set_toolchains("emcc")
	-- Xmake asks the wrapper for Emscripten's version instead of its
	-- underlying Clang version. The adapter fixes that probe only.
	set_toolset("cxx", "clangxx@tools/emscripten/clang++")
	set_policy("build.c++.modules.fallbackscanner", true)
	after_build(update_compile_commands)
	add_includedirs("native/include", "native/src")
	add_files("native/abi/**.cpp")
	add_files("native/src/**.cppm")
	add_files("native/kernels/scalar/**.cppm")
	add_cxflags("-fvisibility=hidden")
	add_ldflags(
		"--no-entry",
		"-sMODULARIZE=1",
		"-sEXPORT_ES6=1",
		"-sEXPORT_NAME=createPacmanNative",
		"-sALLOW_MEMORY_GROWTH=1",
		"-sEXPORTED_FUNCTIONS=['_malloc','_free','_pac_abi_version','_pac_bitboard_or','_pac_bfs_distances','_pac_topology_create','_pac_topology_destroy','_pac_topology_bfs_distances','_pac_topology_bfs_distances_graph','_pac_topology_bfs_distances_masked','_pac_topology_bfs_many','_pac_topology_analyze_distances','_pac_topology_threat_field','_pac_topology_predict_threat','_pac_topology_evaluate_actions','_pac_topology_simulate_action']",
		"-sEXPORTED_RUNTIME_METHODS=['HEAPU8','HEAPU32']",
		{ force = true }
	)

	target("pacman-wasm-tests")
	set_kind("binary")
	set_default(false)
	set_extension(".js")
	set_toolchains("emcc")
	set_toolset("cxx", "clangxx@tools/emscripten/clang++")
	set_policy("build.c++.modules.fallbackscanner", true)
	after_build(update_compile_commands)
	add_includedirs("native/include", "native/src")
	add_files("native/abi/**.cpp")
	add_files("native/src/**.cppm")
	add_files("native/kernels/scalar/**.cppm")
	add_files("native/tests/**.cpp")
	on_run(function(target)
		os.execv("node", { target:targetfile() })
	end)
else
	target("pacman-core")
	set_kind("static")
	set_default(false)
	add_includedirs("native/include", "native/src")
	add_files("native/kernels/scalar/**.cppm", { public = true })
	add_files("native/src/**.cppm", { public = true })
	add_cxflags("-fvisibility=hidden")

	target("pacman-native")
	set_kind("shared")
	add_deps("pacman-core")
	after_build(update_compile_commands)
	add_includedirs("native/include")
	add_headerfiles("native/include/(pacman/*.h)")
	add_files("native/abi/**.cpp")
	add_cxflags("-fvisibility=hidden")
	add_rules(
		"utils.symbols.export_list",
		{
			symbols = {
				"pac_abi_version",
				"pac_bitboard_or",
				"pac_bfs_distances",
				"pac_bfs_distances_graph",
				"pac_topology_create",
				"pac_topology_destroy",
				"pac_topology_bfs_distances",
				"pac_topology_bfs_distances_graph",
				"pac_topology_bfs_distances_masked",
				"pac_topology_bfs_many",
				"pac_topology_analyze_distances",
				"pac_topology_threat_field",
				"pac_topology_predict_threat",
				"pac_topology_evaluate_actions",
				"pac_topology_simulate_action",
			},
		}
	)

	target("pacman-native-tests")
	set_kind("binary")
	set_default(false)
	add_deps("pacman-core")
	after_build(update_compile_commands)
	add_includedirs("native/include")
	add_files("native/abi/**.cpp")
	add_files("native/tests/**.cpp")
end
